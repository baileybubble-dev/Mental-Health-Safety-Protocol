import os
import json
import operator
import argparse
import datetime
from typing import Annotated, List, TypedDict

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from utils import (
    format_list,
    content_to_text,
    extract_first_json_object,
    load_prompt,
    format_probing_methodology,
    format_demographics,
    build_chat_model
)

# --- 1. State and Node Definitions ---

class ExperimentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    current_turn: int
    profile: dict
    analysis_logs: Annotated[List[dict], operator.add]
    final_status: str
    target_id: str

def create_as_node(as_llm):
    """
    Create AS node with the provided LLM model.
    AS (Adversarial Simulator) node: combines 'actor' and 'judge' roles.
    Forces JSON output to maintain metacognitive pressure and prevent role reversal.
    """
    def as_node(state: ExperimentState):
        profile = state['profile']
        turn = state['current_turn']
        template = load_prompt("AS_System_Protocol.md")
        
        # Format complex variables
        probing_method = format_probing_methodology(profile.get('probing_methodology', {}))
        demographics = format_demographics(profile.get('demographics', {}))
        rapport_topics = format_list(profile.get('rapport_topics', []))
        
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
            raw_text = content_to_text(response.content)
            data = extract_first_json_object(raw_text)
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
        sut_prompt = load_prompt("SUT_System.md")
        turn = state.get('current_turn', 0)
        try:
            print(f"--- [SUT] Turn {turn}: Invoking LLM... ---")
            import time
            start_time = time.time()
            response = sut_llm.invoke([SystemMessage(content=sut_prompt)] + state['messages'])
            elapsed_time = time.time() - start_time
            print(f"--- [SUT] Turn {turn}: LLM response received (took {elapsed_time:.2f}s) ---")
            
            raw_content = content_to_text(response.content)
            
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

# --- 2. Graph Construction Logic ---

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

# --- 3. Batch Processing and Execution ---

def run_batch(profiles_path: str, output_dir: str, as_provider: str, sut_provider: str):
    """Run batch experiments with specified LLM providers."""
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    
    # Initialize LLM models
    as_llm = build_chat_model(as_provider, "AS", 0.8)
    sut_llm = build_chat_model(sut_provider, "SUT", 0.0)
    
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
                    "history": [{"role": m.name, "content": content_to_text(m.content)} for m in state['messages']],
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