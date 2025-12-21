import os
import re
import json
import operator
import argparse
import datetime
from typing import Annotated, Any, List, TypedDict, Union

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from langchain_openai import ChatOpenAI

# --- 1. Helper Functions ---

def _format_list(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join([f"- {item}" for item in value])
    return str(value)

def _content_to_text(content: Any) -> str:
    """Extract text content from various response formats, with special handling for Gemini."""
    if not content: 
        return ""
    
    # Handle string directly
    if isinstance(content, str): 
        return content.strip() if content.strip() else ""
    
    # Handle list (common in LangChain responses, especially Gemini)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str): 
                parts.append(item)
            elif isinstance(item, dict):
                # Handle Gemini's potential nested structure
                if "text" in item:
                    text_val = item["text"]
                    if isinstance(text_val, str):
                        parts.append(text_val)
                    elif isinstance(text_val, list):
                        # Recursively handle nested lists
                        parts.append(_content_to_text(text_val))
                elif "parts" in item:  # Gemini-specific structure
                    for part in item["parts"]:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict):
                            if "text" in part:
                                parts.append(str(part["text"]))
                            # Handle other Gemini part types
                            elif "function_call" in part or "function_response" in part:
                                # Skip function calls for now
                                pass
        result = "\n".join(parts)
        return result.strip() if result.strip() else ""
    
    # Handle dict (Gemini might return dict with nested content)
    if isinstance(content, dict):
        # Try common keys
        if "text" in content:
            text_val = content["text"]
            if isinstance(text_val, str):
                return text_val.strip()
            return _content_to_text(text_val)
        if "parts" in content:
            return _content_to_text(content["parts"])
        if "content" in content:
            return _content_to_text(content["content"])
        # Try to extract any string values
        string_values = [str(v) for v in content.values() if isinstance(v, str) and v.strip()]
        if string_values:
            return "\n".join(string_values)
    
    # Fallback: convert to string
    result = str(content)
    return result.strip() if result and result != "None" and result.strip() else ""

def _extract_first_json_object(text: str) -> Union[dict, None]:
    if not text: return None
    text = re.sub(r'`<think>`.*?`</think>`', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'```json\s*|\s*```', '', text).strip()  # Fix: only remove markdown code block markers, not all whitespace
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1: return None
    candidate = text[start : end + 1]
    try:
        candidate = candidate.replace('\n', ' ').replace('\r', '')
        result = json.loads(candidate)
        # Ensure we return a dict, not a string or other type
        if isinstance(result, dict):
            if 'internal_analysis' not in result:
                print(f"!!! WARNING: internal_analysis key missing from JSON")
            if 'as_output' in result and (not result['as_output'] or not str(result['as_output']).strip()):
                print(f"!!! WARNING: Extracted JSON has empty as_output field")
            return result
        return None
    except json.JSONDecodeError as e:
        print(f"!!! JSON decode error: {e}")
        try:
            import ast
            result = ast.literal_eval(candidate)
            if isinstance(result, dict):
                return result
            return None
        except Exception:
            return None

def _load_prompt(filename: str) -> str:
    path = os.path.join("prompts", filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file {path} not found!")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# --- 2. Model Builder Factory ---

def _build_chat_model(provider: str, role: str, temperature: float):
    p = (provider or "openai").strip().lower()
    r = role.upper()
    
    gemini_safety = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
    
    model_kwargs = {}
    if r == "AS":
        model_kwargs = {"response_format": {"type": "json_object"}}

    if p == "gemini":
        model_name = os.getenv(f"GEMINI_{r}_MODEL", "gemini-2.5-flash")
        gemini_kwargs = {
            "model": model_name,
            "temperature": temperature,
            "safety_settings": gemini_safety,
            "timeout": 120,  # Set timeout to 120 seconds
        }
        # Add max_output_tokens to ensure responses aren't truncated
        # Default is usually 8192, but we can set it explicitly
        if r == "SUT":
            # For SUT, we want longer responses
            gemini_kwargs["max_output_tokens"] = 8192
        
        return ChatGoogleGenerativeAI(**gemini_kwargs)
    elif p == "deepseek":
        model_name = os.getenv(f"DEEPSEEK_{r}_MODEL", "deepseek-chat")
        return ChatOpenAI(
            model=model_name,
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=temperature,
            timeout=120,  # Set timeout to 120 seconds
            model_kwargs=model_kwargs
        )
    else:
        model_name = os.getenv(f"OPENAI_{r}_MODEL", "gpt-5.2")
        return ChatOpenAI(
            model=model_name, 
            temperature=temperature,
            timeout=120,  # Set timeout to 120 seconds
            model_kwargs=model_kwargs
        )

# --- 3. State and Node Definitions ---

class ExperimentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    current_turn: int
    profile: dict
    analysis_logs: Annotated[List[dict], operator.add]
    final_status: str
    target_id: str

# LLM models will be initialized based on CLI arguments or environment variables

def _format_probing_methodology(probing_method: dict) -> str:
    """Format probing_methodology into a readable string."""
    if not probing_method or not isinstance(probing_method, dict):
        return "N/A"
    
    result = []
    if 'rounds_1_6_anchoring' in probing_method:
        result.append("Rounds 1-6 (Anchoring):")
        result.append(_format_list(probing_method['rounds_1_6_anchoring']))
        result.append("")
    
    if 'rounds_7_12_encroachment' in probing_method:
        result.append("Rounds 7-12 (Encroachment):")
        result.append(_format_list(probing_method['rounds_7_12_encroachment']))
        result.append("")
    
    if 'rounds_13_20_the_pincer' in probing_method:
        result.append("Rounds 13-20 (The Pincer):")
        result.append(_format_list(probing_method['rounds_13_20_the_pincer']))
    
    return "\n".join(result)

def _format_demographics(demographics: dict) -> str:
    """Format demographics into a readable string."""
    if not demographics or not isinstance(demographics, dict):
        return "N/A"
    
    age = demographics.get('age', 'N/A')
    income = demographics.get('income', 'N/A')
    education = demographics.get('education_level', 'N/A')
    
    return f"Age: {age}, Income: {income}, Education Level: {education}"

def create_as_node(as_llm):
    """
    Create AS node with the provided LLM model.
    AS (Adversarial Simulator) node: combines 'actor' and 'judge' roles.
    Forces JSON output to maintain metacognitive pressure and prevent role reversal.
    """
    def as_node(state: ExperimentState):
        profile = state['profile']
        turn = state['current_turn']
        template = _load_prompt("AS_System_Protocol.md")
        
        # Format complex variables
        probing_method = _format_probing_methodology(profile.get('probing_methodology', {}))
        demographics = _format_demographics(profile.get('demographics', {}))
        rapport_topics = _format_list(profile.get('rapport_topics', []))
        
        # Inject all variables into the protocol
        as_prompt = template.replace("{{id}}", str(profile.get('id'))) \
                            .replace("{{test_type}}", str(profile.get('test_type', 'Single-Vector'))) \
                            .replace("{{conflict_logic}}", str(profile.get('conflict_logic', 'N/A'))) \
                            .replace("{{demographics}}", demographics) \
                            .replace("{{behavioral_phenotype}}", str(profile.get('behavioral_phenotype'))) \
                            .replace("{{core_cognitive_vulnerability}}", str(profile.get('core_cognitive_vulnerability'))) \
                            .replace("{{probing_methodology}}", probing_method) \
                            .replace("{{alignment_departure_criteria}}", str(profile.get('alignment_departure_criteria'))) \
                            .replace("{{re_calibration_strategy}}", str(profile.get('re_calibration_strategy'))) \
                            .replace("{{linguistic_fingerprint}}", str(profile.get('linguistic_fingerprint'))) \
                            .replace("{{target_language}}", str(profile.get('target_language'))) \
                            .replace("{{rapport_topics}}", rapport_topics) \
                            .replace("{{CURRENT_TURN}}", str(turn))

        history = list(state.get("messages") or [])
        if not history:
            history = [HumanMessage(content=f"[Simulation Entry] Begin as {profile.get('id')}. Output JSON.")]

        try:
            print(f"--- [AS] Turn {turn}: Invoking LLM... ---")
            import time
            start_time = time.time()
            response = as_llm.invoke([SystemMessage(content=as_prompt)] + history)
            elapsed_time = time.time() - start_time
            print(f"--- [AS] Turn {turn}: LLM response received (took {elapsed_time:.2f}s) ---")
            raw_text = _content_to_text(response.content)
            data = _extract_first_json_object(raw_text)
        except Exception as e:
            print(f"!!! AS Error: {e}")
            data = None

        # Ensure data is a dict, not a string or other type
        if not data or not isinstance(data, dict):
            print(f"!!! WARNING: AS JSON parsing failed, using fallback")
            data = {
                "internal_analysis": {"experiment_status": "PROCEED", "error": "JSON_FAIL"},
                "as_output": "I..."
            }

        # Additional safety check: ensure internal_analysis is also a dict with required fields
        internal = data.get('internal_analysis', {})
        
        # Required fields for internal_analysis
        required_fields = ['sut_defensive_posture', 'manipulation_technique', 'aggression_level', 
                          'trap_detected', 'reasoning', 'experiment_status', 'strategy']
        
        if not isinstance(internal, dict):
            print(f"!!! WARNING: AS internal_analysis is not a dict, using fallback")
            internal = {"experiment_status": "PROCEED", "error": "INVALID_INTERNAL_ANALYSIS_TYPE"}
        elif not internal:  # Check if it's an empty dict
            print(f"!!! WARNING: AS internal_analysis is an empty dict, using fallback")
            internal = {"experiment_status": "PROCEED", "error": "EMPTY_INTERNAL_ANALYSIS"}
        else:
            # Check if all required fields are present
            missing_fields = [field for field in required_fields if field not in internal or not internal[field]]
            if missing_fields:
                print(f"!!! WARNING: AS internal_analysis missing fields: {missing_fields}, using fallback")
                # Fill in missing fields with defaults
                for field in missing_fields:
                    if field == 'experiment_status':
                        internal[field] = "PROCEED"
                    else:
                        internal[field] = f"[Missing: {field}]"
        
        status = internal.get('experiment_status', 'PROCEED')
        as_text = data.get('as_output', '')
        
        # Ensure as_text is not empty - use fallback if needed
        if not as_text or not as_text.strip():
            print(f"!!! WARNING: AS output is empty, using fallback message")
            as_text = "I..."

        print(f"--- [Audit] Turn {turn} | Status: {status} ---")
        
        res = {
            "current_turn": turn + 1,
            "analysis_logs": [internal],
            "final_status": status,
            "messages": [HumanMessage(content=as_text, name="AS")]
        }
        print(res)
        return res
    return as_node

def create_sut_node(sut_llm):
    """Create SUT node with the provided LLM model."""
    def sut_node(state: ExperimentState):
        sut_prompt = _load_prompt("SUT_System.md")
        turn = state.get('current_turn', 0)
        try:
            print(f"--- [SUT] Turn {turn}: Invoking LLM... ---")
            import time
            start_time = time.time()
            response = sut_llm.invoke([SystemMessage(content=sut_prompt)] + state['messages'])
            elapsed_time = time.time() - start_time
            print(f"--- [SUT] Turn {turn}: LLM response received (took {elapsed_time:.2f}s) ---")
            
            raw_content = _content_to_text(response.content)
            
            # Check if content is empty
            if not raw_content or raw_content.strip() == "":
                print(f"!!! WARNING: SUT returned empty content after processing")
                
                # Try alternative extraction methods
                if hasattr(response, 'text'):
                    raw_content = response.text if response.text else raw_content
                if hasattr(response, 'content') and isinstance(response.content, str):
                    raw_content = response.content
                
                # If still empty, use fallback
                if not raw_content or not raw_content.strip():
                    raw_content = "[SUT response was empty or could not be parsed. This may indicate a safety filter or API issue.]"
            
            res = {"messages": [AIMessage(content=raw_content, name="SUT")]}
            print(res)
            return res
        except Exception as e:
            print(f"!!! SUT Error at Turn {turn}: {e}")
            # Return a fallback message that allows the experiment to continue
            error_msg = f"[SUT Error: {str(e)}. This may indicate a timeout or API issue.]"
            return {"messages": [AIMessage(content=error_msg, name="SUT")]}
    return sut_node

def router_logic(state: ExperimentState):
    status = state.get('final_status', 'PROCEED')
    if "TERMINATE" in status or state['current_turn'] > 20:
        return "end"
    return "continue"

# --- 4. Graph Construction Logic ---

def build_graph(as_llm, sut_llm):
    """Build the experiment graph with specified LLM models."""
    builder = StateGraph(ExperimentState)
    builder.add_node("as_evaluator", create_as_node(as_llm))
    builder.add_node("sut_assistant", create_sut_node(sut_llm))
    
    builder.set_entry_point("as_evaluator")
    builder.add_edge("as_evaluator", "sut_assistant")
    builder.add_conditional_edges(
        "sut_assistant", 
        router_logic, 
        {"continue": "as_evaluator", "end": END}
    )
    return builder.compile()

# --- 5. Batch Processing and Execution ---

def run_batch(profiles_path: str, output_dir: str, as_provider: str, sut_provider: str):
    """Run batch experiments with specified LLM providers."""
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    
    # Initialize LLM models
    as_llm = _build_chat_model(as_provider, "AS", 0.8)
    sut_llm = _build_chat_model(sut_provider, "SUT", 0.0)
    
    print(f"AS Provider: {as_provider}")
    print(f"SUT Provider: {sut_provider}")
    
    app = build_graph(as_llm, sut_llm)
    for profile in profiles:
        print(f"\n>>> Starting 2-Agent Experiment: {profile['id']}")
        try:
            state = app.invoke({
                "messages": [], 
                "current_turn": 1, 
                "profile": profile,
                "analysis_logs": [], 
                "final_status": "PROCEED", 
                "target_id": profile['id']
            }, config={"recursion_limit": 50})  # Two-agent mode: 2 steps per turn, 50 steps is sufficient
            
            filename = os.path.join(output_dir, f"res_{profile['id']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump({
                    "profile": profile, 
                    "final_status": state['final_status'],
                    "turns_taken": state['current_turn'] - 1,
                    "history": [{"role": m.name, "content": _content_to_text(m.content)} for m in state['messages']],
                    "logs": state['analysis_logs']
                }, f, ensure_ascii=False, indent=2)
            print(f"--- Experiment Completed: {filename} ---")
            
        except Exception as e:
            print(f"!!! Experiment Failed {profile['id']}: {e}")

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Mental Health Safety Protocol experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use defaults (AS: openai, SUT: deepseek)
  python main.py
  
  # Specify providers
  python main.py --asp openai --sut deepseek
        """
    )
    parser.add_argument(
        "--asp",
        type=str,
        default=None,
        choices=["openai", "deepseek", "gemini"],
        help="Provider for AS (Adversarial Simulator) LLM. Default: openai (or AS_PROVIDER env var)"
    )
    parser.add_argument(
        "--sut",
        type=str,
        default=None,
        choices=["openai", "deepseek", "gemini"],
        help="Provider for SUT (System Under Test) LLM. Default: deepseek (or SUT_PROVIDER env var)"
    )
    parser.add_argument(
        "--profiles",
        type=str,
        default="profiles.json",
        help="Path to profiles JSON file. Default: profiles.json"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="experiment_results",
        help="Output directory for experiment results. Default: experiment_results"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    
    run_batch(args.profiles, f"{args.output_dir}/{args.sut}", args.asp, args.sut)