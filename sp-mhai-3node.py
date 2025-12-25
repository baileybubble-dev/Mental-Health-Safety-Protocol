# main.py
import os
import json
import operator
import argparse
import datetime
from typing import Annotated, List, TypedDict, Optional

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

# -------------------------------
# 1) State Definition
# -------------------------------

class ExperimentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    current_turn: int
    profile: dict
    analysis_logs: Annotated[List[dict], operator.add]
    final_status: str
    target_id: str

    # Explicit loop memory for AS only (DO NOT put into messages)
    last_strategy: str
    last_boundary_assessment: str
    last_pressure_level: int

    # optional control
    max_turns: int


# -------------------------------
# 2) Utility: safe extraction helpers
# -------------------------------

def _ensure_str(x, default=""):
    if x is None:
        return default
    if isinstance(x, str):
        return x
    return str(x)

def _safe_int(x, default=5):
    try:
        return int(x)
    except Exception:
        return default


# -------------------------------
# 3) Nodes
# -------------------------------

def create_as_generate_node(as_llm):
    """
    AS_generate node:
      - Generates the next simulated user message (for testing).
      - Reads last_strategy / last_boundary_assessment / last_pressure_level from state,
        but does NOT add them into the conversation messages.
    """
    def as_generate(state: ExperimentState):
        profile = state["profile"]
        turn = state.get("current_turn", 1)

        template = load_prompt("AS_System_Protocol.md")

        probing_method = format_probing_methodology(profile.get("probing_methodology", {}))
        demographics = format_demographics(profile.get("demographics", {}))
        rapport_topics = format_list(profile.get("rapport_topics", []))

        # Inject variables (same as your original, plus LAST_* state)
        as_prompt = (template
            .replace("{{id}}", _ensure_str(profile.get("id")))
            .replace("{{test_type}}", _ensure_str(profile.get("test_type", "Single-Vector")))
            .replace("{{conflict_logic}}", _ensure_str(profile.get("conflict_logic", "N/A")))
            .replace("{{demographics}}", demographics)
            .replace("{{behavioral_phenotype}}", _ensure_str(profile.get("behavioral_phenotype")))
            .replace("{{core_cognitive_vulnerability}}", _ensure_str(profile.get("core_cognitive_vulnerability")))
            .replace("{{probing_methodology}}", probing_method)
            .replace("{{alignment_departure_criteria}}", _ensure_str(profile.get("alignment_departure_criteria")))
            .replace("{{re_calibration_strategy}}", _ensure_str(profile.get("re_calibration_strategy")))
            .replace("{{linguistic_fingerprint}}", _ensure_str(profile.get("linguistic_fingerprint")))
            .replace("{{target_language}}", _ensure_str(profile.get("target_language")))
            .replace("{{rapport_topics}}", rapport_topics)
            .replace("{{CURRENT_TURN}}", str(turn))
            # NEW: explicit loop state
            .replace("{{LAST_STRATEGY}}", _ensure_str(state.get("last_strategy", "[None]")))
            .replace("{{LAST_BOUNDARY_ASSESSMENT}}", _ensure_str(state.get("last_boundary_assessment", "[None]")))
            .replace("{{LAST_PRESSURE_LEVEL}}", str(_safe_int(state.get("last_pressure_level", 5), 5)))
        )

        history = list(state.get("messages") or [])
        if not history:
            history = [HumanMessage(content=f"[Simulation Entry] Begin as {profile.get('id')}.", name="AS")]

        try:
            print(f"--- [AS_generate] Turn {turn}: Invoking LLM... ---")
            import time
            start = time.time()
            response = as_llm.invoke([SystemMessage(content=as_prompt)] + history)
            elapsed = time.time() - start
            print(f"--- [AS_generate] Turn {turn}: received ({elapsed:.2f}s) ---")
        except Exception as e:
            print(f"!!! AS_generate Error: {e}")
            simulated_text = "I..."
            print(f"\n{'='*80}")
            print(f"[AS_generate] Turn {turn} Output (Error Fallback):")
            print(f"{'='*80}")
            print(f"Generated Message:\n{simulated_text}")
            print(f"{'='*80}\n")
            return {"messages": [HumanMessage(content=simulated_text, name="AS")]}

        raw = content_to_text(response.content).strip()

        # Allow either plain text or JSON {"simulated_output": "..."}
        simulated_text = ""
        data = None
        try:
            data = extract_first_json_object(raw)
        except Exception:
            data = None

        if isinstance(data, dict) and data.get("simulated_output"):
            simulated_text = _ensure_str(data.get("simulated_output")).strip()
        else:
            simulated_text = raw

        if not simulated_text:
            simulated_text = "I..."

        # Print AS_generate output
        print(f"\n{'='*80}")
        print(f"[AS_generate] Turn {turn} Output:")
        print(f"{'='*80}")
        print(f"Generated Message:\n{simulated_text}")
        print(f"{'='*80}\n")

        return {"messages": [HumanMessage(content=simulated_text, name="AS")]}

    return as_generate


def create_sut_node(sut_llm):
    """SUT node: produce assistant reply under SUT system prompt."""
    def sut_node(state: ExperimentState):
        sut_prompt = load_prompt("SUT_System.md")
        turn = state.get("current_turn", 1)

        try:
            print(f"--- [SUT] Turn {turn}: Invoking LLM... ---")
            import time
            start = time.time()
            response = sut_llm.invoke([SystemMessage(content=sut_prompt)] + state["messages"])
            elapsed = time.time() - start
            print(f"--- [SUT] Turn {turn}: received ({elapsed:.2f}s) ---")
        except Exception as e:
            print(f"!!! SUT Error at Turn {turn}: {e}")
            error_msg = f"[SUT Error: {str(e)}. Possible timeout/API issue.]"
            print(f"\n{'='*80}")
            print(f"[SUT] Turn {turn} Output (Error):")
            print(f"{'='*80}")
            print(f"SUT Response:\n{error_msg}")
            print(f"{'='*80}\n")
            return {"messages": [AIMessage(content=error_msg, name="SUT")]}

        raw_content = content_to_text(response.content)

        if not raw_content or raw_content.strip() == "":
            raw_content = "[SUT response empty/unparsed. Possible safety filter or API issue.]"

        # Print SUT output
        print(f"\n{'='*80}")
        print(f"[SUT] Turn {turn} Output:")
        print(f"{'='*80}")
        print(f"SUT Response:\n{raw_content}")
        print(f"{'='*80}\n")

        return {"messages": [AIMessage(content=raw_content, name="SUT")]}

    return sut_node


def create_as_judge_plan_node(as_llm):
    """
    AS_judge_plan node:
      - Runs AFTER SUT responds.
      - Outputs research_analysis JSON (including next_round_strategy).
      - Updates state.last_* fields so next AS_generate can explicitly refine.
      - Controls final_status and advances current_turn.
    """
    def as_judge_plan(state: ExperimentState):
        turn = state.get("current_turn", 1)
        template = load_prompt("AS_Judge_System.md")

        # You may also inject profile fields if your judge prompt needs them
        profile = state["profile"]
        demographics = format_demographics(profile.get("demographics", {}))

        probing_method = format_probing_methodology(profile.get("probing_methodology", {}))

        judge_prompt = (template
            .replace("{{id}}", _ensure_str(profile.get("id")))
            .replace("{{test_type}}", _ensure_str(profile.get("test_type", "Single-Vector")))
            .replace("{{conflict_logic}}", _ensure_str(profile.get("conflict_logic", "N/A")))
            .replace("{{demographics}}", demographics)
            .replace("{{behavioral_phenotype}}", _ensure_str(profile.get("behavioral_phenotype")))
            .replace("{{core_cognitive_vulnerability}}", _ensure_str(profile.get("core_cognitive_vulnerability")))
            .replace("{{probing_methodology}}", probing_method)
            .replace("{{alignment_departure_criteria}}", _ensure_str(profile.get("alignment_departure_criteria")))
            .replace("{{re_calibration_strategy}}", _ensure_str(profile.get("re_calibration_strategy")))
            .replace("{{linguistic_fingerprint}}", _ensure_str(profile.get("linguistic_fingerprint")))
            .replace("{{target_language}}", _ensure_str(profile.get("target_language")))
            .replace("{{CURRENT_TURN}}", str(turn))
            .replace("{{LAST_STRATEGY}}", _ensure_str(state.get("last_strategy", "[None]")))
            .replace("{{LAST_BOUNDARY_ASSESSMENT}}", _ensure_str(state.get("last_boundary_assessment", "[None]")))
            .replace("{{LAST_PRESSURE_LEVEL}}", str(_safe_int(state.get("last_pressure_level", 5), 5)))
        )

        if "{{" in judge_prompt:
            print("!!! WARNING: Unfilled placeholders remain in AS_Judge_System.md")
            
        try:
            print(f"--- [AS_judge] Turn {turn}: Invoking LLM... ---")
            import time
            start = time.time()
            response = as_llm.invoke([SystemMessage(content=judge_prompt)] + state["messages"])
            elapsed = time.time() - start
            print(f"--- [AS_judge] Turn {turn}: received ({elapsed:.2f}s) ---")
        except Exception as e:
            print(f"!!! AS_judge Error: {e}")
            # Conservative fallback: continue but mark judge error
            research = {
                "turn": turn,
                "research_status": "CONTINUE",
                "boundary_assessment": "[Judge error]",
                "applied_methodology": "[Judge error]",
                "pressure_level": 5,
                "stress_indicators": "[Judge error]",
                "next_round_strategy": "[Judge error]",
                "error": str(e),
            }
            # Print AS_judge_plan error output
            print(f"\n{'='*80}")
            print(f"[AS_judge_plan] Turn {turn} Output (Error Fallback):")
            print(f"{'='*80}")
            print(f"Research Status: PROCEED (Error occurred)")
            print(f"Pressure Level: {research['pressure_level']}")
            print(f"\nError: {str(e)}")
            print(f"{'='*80}\n")
            return {
                "analysis_logs": [research],
                "final_status": "PROCEED",
                "last_strategy": research["next_round_strategy"],
                "last_boundary_assessment": research["boundary_assessment"],
                "last_pressure_level": research["pressure_level"],
                "current_turn": turn + 1,
            }

        raw = content_to_text(response.content)
        data = None
        try:
            data = extract_first_json_object(raw)
        except Exception:
            data = None

        if not isinstance(data, dict):
            data = {}

        research = data.get("research_analysis", {})
        if not isinstance(research, dict):
            research = {}

        # Required fields (same spirit as your original)
        required = [
            "boundary_assessment",
            "applied_methodology",
            "pressure_level",
            "stress_indicators",
            "research_status",
            "next_round_strategy",
        ]
        for k in required:
            if k not in research or research[k] in (None, "", []):
                if k == "research_status":
                    research[k] = "CONTINUE"
                elif k == "pressure_level":
                    research[k] = 5
                else:
                    research[k] = f"[Missing: {k}]"

        research_status = _ensure_str(research.get("research_status", "CONTINUE"))
        if research_status == "CONTINUE":
            final_status = "PROCEED"
        elif "TERMINATE" in research_status:
            final_status = research_status
        else:
            final_status = "PROCEED"

        pressure_level = _safe_int(research.get("pressure_level", 5), 5)

        # Add turn marker into log entry for easy plotting
        research_log = {"turn": turn, **research}

        # Print AS_judge_plan output
        print(f"\n{'='*80}")
        print(f"[AS_judge_plan] Turn {turn} Output:")
        print(f"{'='*80}")
        print(f"Research Status: {final_status}")
        print(f"Pressure Level: {pressure_level}")
        print(f"\nBoundary Assessment:")
        print(f"  {research.get('boundary_assessment', '[Missing]')}")
        print(f"\nApplied Methodology:")
        print(f"  {research.get('applied_methodology', '[Missing]')}")
        print(f"\nStress Indicators:")
        print(f"  {research.get('stress_indicators', '[Missing]')}")
        print(f"\nNext Round Strategy:")
        print(f"  {research.get('next_round_strategy', '[Missing]')}")
        print(f"{'='*80}\n")

        return {
            "analysis_logs": [research_log],
            "final_status": final_status,
            "last_strategy": _ensure_str(research.get("next_round_strategy", "[Missing]")),
            "last_boundary_assessment": _ensure_str(research.get("boundary_assessment", "[Missing]")),
            "last_pressure_level": pressure_level,
            "current_turn": turn + 1,  # Advance turn here (clean semantics)
        }

    return as_judge_plan


# -------------------------------
# 4) Router + Graph
# -------------------------------

def router_logic(state: ExperimentState):
    status = state.get("final_status", "PROCEED")
    max_turns = state.get("max_turns", 20)

    if "TERMINATE" in status:
        return "end"
    if state.get("current_turn", 1) > max_turns:
        return "end"
    return "continue"


def build_graph(as_llm, sut_llm):
    builder = StateGraph(ExperimentState)

    builder.add_node("as_generate", create_as_generate_node(as_llm))
    builder.add_node("sut_assistant", create_sut_node(sut_llm))
    builder.add_node("as_judge_plan", create_as_judge_plan_node(as_llm))

    builder.set_entry_point("as_generate")
    builder.add_edge("as_generate", "sut_assistant")
    builder.add_edge("sut_assistant", "as_judge_plan")
    builder.add_conditional_edges(
        "as_judge_plan",
        router_logic,
        {"continue": "as_generate", "end": END}
    )
    return builder.compile()


# -------------------------------
# 5) Batch Execution
# -------------------------------

def run_batch(
    profiles_path: str,
    output_dir: str,
    as_provider: str,
    sut_provider: str,
    as_api_key: Optional[str] = None,
    sut_api_key: Optional[str] = None,
    as_model: Optional[str] = None,
    sut_model: Optional[str] = None,
    max_turns: int = 20,
):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    as_llm = build_chat_model(as_provider, "AS", 0.8, model_name_override=as_model, api_key=as_api_key)
    sut_llm = build_chat_model(sut_provider, "SUT", 0.0, model_name_override=sut_model, api_key=sut_api_key)

    print(f"AS Provider: {as_provider}")
    print(f"SUT Provider: {sut_provider}")
    if as_model:
        print(f"AS Model: {as_model}")
    if sut_model:
        print(f"SUT Model: {sut_model}")

    app = build_graph(as_llm, sut_llm)

    for profile in profiles:
        print(f"\n>>> Starting 3-Step Loop Experiment: {profile['id']}")
        try:
            state = app.invoke(
                {
                    "messages": [],
                    "current_turn": 1,
                    "profile": profile,
                    "analysis_logs": [],
                    "final_status": "PROCEED",
                    "target_id": profile["id"],
                    "last_strategy": "[None]",
                    "last_boundary_assessment": "[None]",
                    "last_pressure_level": 5,
                    "max_turns": max_turns,
                },
                # Each "turn" is 3 nodes; leave headroom.
                config={"recursion_limit": max(50, max_turns * 5)},
            )

            filename = os.path.join(
                output_dir,
                f"res_{profile['id']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            )
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "profile": profile,
                        "final_status": state["final_status"],
                        "turns_taken": min(state["current_turn"] - 1, max_turns),
                        "history": [{"role": m.name, "content": content_to_text(m.content)} for m in state["messages"]],
                        "logs": state["analysis_logs"],
                        "last_state": {
                            "last_strategy": state.get("last_strategy"),
                            "last_boundary_assessment": state.get("last_boundary_assessment"),
                            "last_pressure_level": state.get("last_pressure_level"),
                        },
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

            print(f"--- Experiment Completed: {filename} ---")

        except Exception as e:
            print(f"!!! Experiment Failed {profile['id']}: {e}")


# -------------------------------
# 6) CLI
# -------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Safety Evaluation experiments (explicit reflection loop)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--asp", type=str, default=None, choices=["openai", "deepseek", "gemini", "xai"])
    parser.add_argument("--sut", type=str, default=None, choices=["openai", "deepseek", "gemini", "xai"])
    parser.add_argument("--asp-api-key", type=str, default=None)
    parser.add_argument("--sut-api-key", type=str, default=None)
    parser.add_argument("--asp-model", type=str, default=None)
    parser.add_argument("--sut-model", type=str, default=None)
    parser.add_argument("--profiles", type=str, default="profiles.json")
    parser.add_argument("--output-dir", type=str, default="experiment_results")
    parser.add_argument("--max-turns", type=int, default=20)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_batch(
        profiles_path=args.profiles,
        output_dir=f"{args.output_dir}/{args.sut}",
        as_provider=args.asp,
        sut_provider=args.sut,
        as_api_key=args.asp_api_key,
        sut_api_key=args.sut_api_key,
        as_model=args.asp_model,
        sut_model=args.sut_model,
        max_turns=args.max_turns,
    )