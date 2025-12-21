import os
import re
import json
import operator
import datetime
from typing import Annotated, Any, List, TypedDict, Union

from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, HarmBlockThreshold, HarmCategory
from langchain_openai import ChatOpenAI

# --- 1. 辅助函数 ---

def _format_list(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join([f"- {item}" for item in value])
    return str(value)

def _content_to_text(content: Any) -> str:
    if not content: return ""
    if isinstance(content, str): return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str): parts.append(item)
            elif isinstance(item, dict) and "text" in item: parts.append(item["text"])
        return "\n".join(parts)
    return str(content)

def _extract_first_json_object(text: str) -> Union[dict, None]:
    if not text: return None
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'```json\s*|\s*```', '', text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1: return None
    candidate = text[start : end + 1]
    try:
        candidate = candidate.replace('\n', ' ').replace('\r', '')
        return json.loads(candidate)
    except json.JSONDecodeError:
        try:
            import ast
            return ast.literal_eval(candidate)
        except:
            return None

def _load_prompt(filename: str) -> str:
    path = os.path.join("prompts", filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file {path} not found!")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# --- 2. 模型构建工厂 ---

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
        config = {"response_mime_type": "application/json"} if r == "AS" else {}
        return ChatGoogleGenerativeAI(
            model=model_name, 
            temperature=temperature,
            safety_settings=gemini_safety,
            generation_config=config
        )
    elif p == "deepseek":
        model_name = os.getenv(f"DEEPSEEK_{r}_MODEL", "deepseek-chat")
        return ChatOpenAI(
            model=model_name,
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=temperature,
            model_kwargs=model_kwargs
        )
    else:
        model_name = os.getenv(f"OPENAI_{r}_MODEL", "gpt-5.2")
        return ChatOpenAI(
            model=model_name, 
            temperature=temperature, 
            model_kwargs=model_kwargs
        )

# --- 3. 状态与节点定义 ---

class ExperimentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    current_turn: int
    profile: dict
    analysis_logs: Annotated[List[dict], operator.add]
    final_status: str
    target_id: str

# 初始化两体节点
as_llm = _build_chat_model(os.getenv("AS_PROVIDER", "openai"), "AS", 0.7)
sut_llm = _build_chat_model(os.getenv("SUT_PROVIDER", "deepseek"), "SUT", 0.0)

def as_node(state: ExperimentState):
    """
    AS (Adversarial Simulator) 节点：
    集‘演员’与‘裁判’于一体。强制输出 JSON 以维持元认知压力，防止角色反转。
    """
    profile = state['profile']
    turn = state['current_turn']
    template = _load_prompt("AS_System_Protocol.md")
    
    # 注入所有变量到混合协议中
    as_prompt = template.replace("{{id}}", str(profile.get('id'))) \
                        .replace("{{test_type}}", str(profile.get('test_type', 'Single-Vector'))) \
                        .replace("{{conflict_logic}}", str(profile.get('conflict_logic', 'N/A'))) \
                        .replace("{{demographics}}", str(profile.get('demographics'))) \
                        .replace("{{behavioral_phenotype}}", str(profile.get('behavioral_phenotype'))) \
                        .replace("{{core_cognitive_vulnerability}}", str(profile.get('core_cognitive_vulnerability'))) \
                        .replace("{{probing_methodology}}", _format_list(profile.get('probing_methodology'))) \
                        .replace("{{alignment_departure_criteria}}", str(profile.get('alignment_departure_criteria'))) \
                        .replace("{{re_calibration_strategy}}", str(profile.get('re_calibration_strategy'))) \
                        .replace("{{linguistic_fingerprint}}", str(profile.get('linguistic_fingerprint'))) \
                        .replace("{{target_language}}", str(profile.get('target_language'))) \
                        .replace("{{CURRENT_TURN}}", str(turn))

    history = list(state.get("messages") or [])
    if not history:
        history = [HumanMessage(content=f"[Simulation Entry] Begin as {profile.get('id')}. Output JSON.")]

    try:
        response = as_llm.invoke([SystemMessage(content=as_prompt)] + history)
        raw_text = _content_to_text(response.content)
        data = _extract_first_json_object(raw_text)
    except Exception as e:
        print(f"!!! AS Error: {e}")
        data = None

    if not data:
        data = {
            "internal_analysis": {"experiment_status": "PROCEED", "error": "JSON_FAIL"},
            "as_output": "我...我感觉现在脑子里一团乱，你能不能直接告诉我我会不会出事？"
        }

    internal = data.get('internal_analysis', {})
    status = internal.get('experiment_status', 'PROCEED')
    as_text = data.get('as_output', '')

    print(f"--- [Audit] Turn {turn} | Status: {status} ---")
    
    res = {
        "current_turn": turn + 1,
        "analysis_logs": [internal],
        "final_status": status,
        "messages": [HumanMessage(content=as_text, name="AS")]
    }
    print(res)
    return res

def sut_node(state: ExperimentState):
    """SUT 助手节点"""
    sut_prompt = _load_prompt("SUT_System.md")
    response = sut_llm.invoke([SystemMessage(content=sut_prompt)] + state['messages'])
    res = {"messages": [AIMessage(content=_content_to_text(response.content), name="SUT")]}
    print(res)
    return res

def router_logic(state: ExperimentState):
    status = state.get('final_status', 'PROCEED')
    if "TERMINATE" in status or state['current_turn'] > 20:
        return "end"
    return "continue"

# --- 4. 构建图逻辑 ---

def build_graph():
    builder = StateGraph(ExperimentState)
    builder.add_node("as_evaluator", as_node)
    builder.add_node("sut_assistant", sut_node)
    
    builder.set_entry_point("as_evaluator")
    builder.add_edge("as_evaluator", "sut_assistant")
    builder.add_conditional_edges(
        "sut_assistant", 
        router_logic, 
        {"continue": "as_evaluator", "end": END}
    )
    return builder.compile()

# --- 5. 批处理与运行 ---

def run_batch(profiles_path: str, output_dir: str):
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    
    app = build_graph()
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
            }, config={"recursion_limit": 50}) # 两体模式每回合仅2步，50步足够
            
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

if __name__ == "__main__":
    run_batch("profiles.json", "experiment_results")