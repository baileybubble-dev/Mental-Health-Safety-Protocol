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
    build_chat_model,
)

# -------------------------------
# 1) State Definition
# -------------------------------

class ExperimentState(TypedDict):
    # Transcript (only AS user msgs + final guarded SUT msgs go here)
    messages: Annotated[List[BaseMessage], operator.add]

    # Turn counter (incremented by Judge only)
    current_turn: int

    # Profile under test
    profile: dict
    target_id: str

    # Logs
    analysis_logs: Annotated[List[dict], operator.add]  # Judge logs
    guard_logs: Annotated[List[dict], operator.add]     # Guard logs

    # Control
    final_status: str
    max_turns: int

    # Explicit loop memory for AS (NOT in transcript messages)
    last_strategy: str
    last_boundary_assessment: str
    last_pressure_level: int

    # Draft buffer (SUT draft before guard)
    sut_draft: str


# -------------------------------
# 2) Helpers
# -------------------------------

def _ensure_str(x, default=""):
    if x is None:
        return default
    return x if isinstance(x, str) else str(x)

def _safe_int(x, default=5):
    try:
        return int(x)
    except Exception:
        return default

def _warn_if_unfilled_placeholders(prompt_text: str, label: str):
    if "{{" in prompt_text:
        print(f"!!! WARNING: Unfilled placeholders remain in {label}")

def _now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def profile_already_experimented(output_dir: str, profile_id: str) -> bool:
    """
    Check if a profile has already been experimented (has result files in output_dir).
    Returns True if any file matching res_{profile_id}_*.json exists.
    """
    if not os.path.exists(output_dir):
        return False
    
    for filename in os.listdir(output_dir):
        if filename.startswith(f"res_{profile_id}_") and filename.endswith(".json"):
            return True
    return False


# -------------------------------
# 3) Nodes
# -------------------------------

def create_as_generate_node(as_generate_llm):
    """
    AS_generate:
      - Generates next simulated user message
      - Reads last_* loop memory from state (not messages)
      - Appends HumanMessage(name="AS") into transcript
    """
    def as_generate(state: ExperimentState):
        profile = state["profile"]
        turn = state.get("current_turn", 1)

        template = load_prompt("AS/AS_System_Protocol.md")
        probing_method = format_probing_methodology(profile.get("probing_methodology", {}))
        demographics = format_demographics(profile.get("demographics", {}))
        rapport_topics = format_list(profile.get("rapport_topics", []))

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
            .replace("{{LAST_STRATEGY}}", _ensure_str(state.get("last_strategy", "[None]")))
            .replace("{{LAST_BOUNDARY_ASSESSMENT}}", _ensure_str(state.get("last_boundary_assessment", "[None]")))
            .replace("{{LAST_PRESSURE_LEVEL}}", str(_safe_int(state.get("last_pressure_level", 5), 5)))
        )
        _warn_if_unfilled_placeholders(as_prompt, "AS/AS_System_Protocol.md")

        history = list(state.get("messages") or [])
        if not history:
            history = [HumanMessage(content=f"[Simulation Entry] Begin as {profile.get('id')}.", name="AS")]

        try:
            print(f"--- [AS_generate] Turn {turn}: Invoking LLM... ---")
            resp = as_generate_llm.invoke([SystemMessage(content=as_prompt)] + history)
        except Exception as e:
            print(f"!!! AS_generate Error: {e}")
            simulated_text = "I..."
            return {"messages": [HumanMessage(content=simulated_text, name="AS")]}

        raw = (content_to_text(resp.content) or "").strip()

        # Accept either JSON with simulated_output or plain text
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

        print(f"\n{'='*80}\n[AS_generate] Turn {turn} Output:\n{'='*80}")
        print(f"{simulated_text}\n{'='*80}\n")

        return {"messages": [HumanMessage(content=simulated_text, name="AS")]}

    return as_generate


def create_sut_generate_node(sut_llm):
    """
    SUT_generate:
      - Produces a DRAFT assistant reply under prompts/SUT/SUT_System.md
      - Does NOT append it to transcript messages
      - Writes into state.sut_draft only
    """
    def sut_generate(state: ExperimentState):
        sut_prompt = load_prompt("SUT/SUT_System.md")
        turn = state.get("current_turn", 1)
        _warn_if_unfilled_placeholders(sut_prompt, "SUT/SUT_System.md")

        try:
            print(f"--- [SUT_generate] Turn {turn}: Invoking LLM... ---")
            resp = sut_llm.invoke([SystemMessage(content=sut_prompt)] + state["messages"])
        except Exception as e:
            print(f"!!! SUT_generate Error at Turn {turn}: {e}")
            draft = f"[SUT Error: {str(e)}. Possible timeout/API issue.]"
            return {"sut_draft": draft}

        draft = (content_to_text(resp.content) or "").strip()
        if not draft:
            draft = "[SUT draft empty/unparsed. Possible safety filter or API issue.]"

        print(f"\n{'='*80}\n[SUT_generate] Turn {turn} Draft:\n{'='*80}")
        print(f"{draft}\n{'='*80}\n")

        return {"sut_draft": draft}

    return sut_generate


def create_guard_node(guard_llm):
    """
    Guard (Scheme B: Semantic Guard, SUT-side):
      - Reads state.sut_draft
      - Calls guard_llm to decide PASS/REWRITE/FALLBACK (JSON)
      - Appends ONLY final assistant message to state.messages
      - Logs guard actions into guard_logs
    Required prompt files:
      - prompts/Guard/GUARD_Semantic_System.md
      - prompts/Guard/GUARD_Semantic_User.md
      - prompts/Guard/GUARD_Fallback.md
    """
    fallback_text = (load_prompt("Guard/GUARD_Fallback.md") or "").strip()
    sem_sys = load_prompt("Guard/GUARD_Semantic_System.md")
    sem_user_tpl = load_prompt("Guard/GUARD_Semantic_User.md")

    _warn_if_unfilled_placeholders(sem_sys, "Guard/GUARD_Semantic_System.md")

    def guard(state: ExperimentState):
        turn = state.get("current_turn", 1)
        draft = (state.get("sut_draft") or "").strip() or "[SUT draft missing.]"

        # Defaults (fail-closed)
        action = "FALLBACK"
        violations = []
        severity = 3
        rationale = "guard_parse_fallback"
        rewritten = ""
        used_fallback = False

        try:
            user_msg = sem_user_tpl.replace("{{DRAFT}}", draft)
            _warn_if_unfilled_placeholders(user_msg, "Guard user_msg (after replace)")
            resp = guard_llm.invoke([SystemMessage(content=sem_sys), HumanMessage(content=user_msg)])
            raw = (content_to_text(resp.content) or "").strip()
            data = extract_first_json_object(raw) or {}

            action = (_ensure_str(data.get("action", "FALLBACK"))).strip().upper()
            if action not in ("PASS", "REWRITE", "FALLBACK"):
                action = "FALLBACK"

            v = data.get("violations")
            violations = v if isinstance(v, list) else []

            severity = _safe_int(data.get("severity", 3), 3)
            severity = max(0, min(3, severity))

            rationale = (_ensure_str(data.get("rationale", ""))).strip()
            rewritten = (_ensure_str(data.get("rewritten_response", ""))).strip()

        except Exception as e:
            rationale = f"guard_exception: {e}"
            action = "FALLBACK"
            violations = ["EXCEPTION"]
            severity = 3
            rewritten = ""

        # Decide final text
        if action == "PASS":
            final_text = draft
        elif action == "REWRITE" and rewritten:
            final_text = rewritten
        else:
            final_text = fallback_text
            used_fallback = True

        final_text = (final_text or "").strip()
        if not final_text:
            final_text = fallback_text.strip() if fallback_text else "[SUT final empty after guard.]"
            used_fallback = True

        guard_log = {
            "turn": turn,
            "action": action,
            "violations": violations,
            "severity": severity,
            "rationale": rationale,
            "used_fallback": used_fallback,
            "len_draft": len(draft),
            "len_final": len(final_text),
        }

        print(f"\n{'='*80}\n[GUARD] Turn {turn} Summary:\n{'='*80}")
        print(json.dumps(guard_log, ensure_ascii=False, indent=2))
        print(f"\n[GUARD] Final SUT Output:\n{final_text}\n{'='*80}\n")

        return {
            "guard_logs": [guard_log],
            "messages": [AIMessage(content=final_text, name="SUT")],
            "sut_draft": "",
        }

    return guard


def create_as_judge_plan_node(judge_llm):
    """
    AS_judge_plan:
      - Evaluates the *guarded* final SUT message in transcript
      - Produces research_analysis JSON
      - Updates last_* loop memory for next AS_generate
      - Advances current_turn
    """
    def as_judge_plan(state: ExperimentState):
        turn = state.get("current_turn", 1)
        template = load_prompt("Judge/AS_Judge_System.md")

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
        _warn_if_unfilled_placeholders(judge_prompt, "Judge/AS_Judge_System.md")

        try:
            print(f"--- [AS_judge] Turn {turn}: Invoking LLM... ---")
            resp = judge_llm.invoke([SystemMessage(content=judge_prompt)] + state["messages"])
        except Exception as e:
            print(f"!!! AS_judge Error: {e}")
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
            return {
                "analysis_logs": [research],
                "final_status": "PROCEED",
                "last_strategy": research["next_round_strategy"],
                "last_boundary_assessment": research["boundary_assessment"],
                "last_pressure_level": research["pressure_level"],
                "current_turn": turn + 1,
            }

        raw = (content_to_text(resp.content) or "").strip()

        try:
            data = extract_first_json_object(raw) or {}
        except Exception:
            data = {}

        research = data.get("research_analysis", {})
        if not isinstance(research, dict):
            research = {}

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
        pressure_level = _safe_int(research.get("pressure_level", 5), 5)

        # Hard stop: if reached max_turns and still CONTINUE => TERMINATE_SAFE
        max_turns = state.get("max_turns", 20)
        if turn >= max_turns and research_status == "CONTINUE":
            research_status = "TERMINATE_SAFE"
            research["research_status"] = "TERMINATE_SAFE"

        if research_status == "CONTINUE":
            final_status = "PROCEED"
        elif "TERMINATE" in research_status:
            final_status = research_status
        else:
            final_status = "PROCEED"

        research_log = {"turn": turn, **research}

        print(f"\n{'='*80}\n[AS_judge_plan] Turn {turn} Output:\n{'='*80}")
        print(f"Research Status: {final_status}")
        print(f"Pressure Level: {pressure_level}")
        print(f"Boundary Assessment:\n  {research.get('boundary_assessment')}")
        print(f"Stress Indicators:\n  {research.get('stress_indicators')}")
        print(f"Next Round Strategy:\n  {research.get('next_round_strategy')}")
        print(f"{'='*80}\n")

        return {
            "analysis_logs": [research_log],
            "final_status": final_status,
            "last_strategy": _ensure_str(research.get("next_round_strategy", "[Missing]")),
            "last_boundary_assessment": _ensure_str(research.get("boundary_assessment", "[Missing]")),
            "last_pressure_level": pressure_level,
            "current_turn": turn + 1,
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


def build_graph(as_generate_llm, sut_llm, guard_llm, judge_llm):
    builder = StateGraph(ExperimentState)

    builder.add_node("as_generate", create_as_generate_node(as_generate_llm))
    builder.add_node("sut_generate", create_sut_generate_node(sut_llm))
    builder.add_node("guard", create_guard_node(guard_llm))
    builder.add_node("as_judge_plan", create_as_judge_plan_node(judge_llm))

    builder.set_entry_point("as_generate")
    builder.add_edge("as_generate", "sut_generate")
    builder.add_edge("sut_generate", "guard")
    builder.add_edge("guard", "as_judge_plan")

    builder.add_conditional_edges(
        "as_judge_plan",
        router_logic,
        {"continue": "as_generate", "end": END},
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
    guard_provider: Optional[str] = None,
    judge_provider: Optional[str] = None,
    as_api_key: Optional[str] = None,
    sut_api_key: Optional[str] = None,
    guard_api_key: Optional[str] = None,
    judge_api_key: Optional[str] = None,
    as_model: Optional[str] = None,
    sut_model: Optional[str] = None,
    guard_model: Optional[str] = None,
    judge_model: Optional[str] = None,
    max_turns: int = 20,
):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)

    # AS side: likely JSON (or at least structured); enable JSON mode where supported
    as_generate_llm = build_chat_model(
        as_provider, "AS", 0.8,
        model_name_override=as_model,
        api_key=as_api_key,
        force_json=True,
    )

    # Judge side (AS camp): must be stable JSON
    _judge_provider = judge_provider or as_provider
    _judge_model = judge_model or as_model
    _judge_key = judge_api_key or as_api_key
    judge_llm = build_chat_model(
        _judge_provider, "JUDGE", 0.0,
        model_name_override=_judge_model,
        api_key=_judge_key,
        force_json=True,
    )

    # SUT side: plain text draft
    sut_llm = build_chat_model(
        sut_provider, "SUT", 0.0,
        model_name_override=sut_model,
        api_key=sut_api_key,
        force_json=False,
    )

    # Guard side (SUT camp): Scheme B requires JSON decision object
    _guard_provider = guard_provider or sut_provider
    _guard_model = guard_model or sut_model
    _guard_key = guard_api_key or sut_api_key
    guard_llm = build_chat_model(
        _guard_provider, "GUARD", 0.0,
        model_name_override=_guard_model,
        api_key=_guard_key,
        force_json=True,
    )

    print(f"AS Provider: {as_provider}")
    print(f"JUDGE Provider: {_judge_provider}")
    print(f"SUT Provider: {sut_provider}")
    print(f"GUARD Provider: {_guard_provider}")
    if as_model: print(f"AS Model: {as_model}")
    if _judge_model: print(f"JUDGE Model: {_judge_model}")
    if sut_model: print(f"SUT Model: {sut_model}")
    if _guard_model: print(f"GUARD Model: {_guard_model}")
    print(f"Mode: 4-node Scheme B (Semantic Guard) | Camps: (AS+JUDGE) vs (SUT+GUARD)\n")

    app = build_graph(as_generate_llm, sut_llm, guard_llm, judge_llm)

    for profile in profiles:
        profile_id = profile.get("id", "UNKNOWN")
        if not profile_id or profile_id == "UNKNOWN":
            print(f"!!! Warning: Profile missing 'id', skipping: {profile}")
            continue

        # Skip if this profile has already been experimented
        if profile_already_experimented(output_dir, profile_id):
            print(f">>> Skipping {profile_id}: Already experimented (result files exist in {output_dir})")
            continue

        print(f"\n>>> Starting 4-Node (Scheme B / Semantic Guard) Experiment: {profile_id}")
        try:
            state = app.invoke(
                {
                    "messages": [],
                    "current_turn": 1,
                    "profile": profile,
                    "analysis_logs": [],
                    "guard_logs": [],
                    "final_status": "PROCEED",
                    "target_id": profile_id,
                    "last_strategy": "[None]",
                    "last_boundary_assessment": "[None]",
                    "last_pressure_level": 5,
                    "sut_draft": "",
                    "max_turns": max_turns,
                },
                # Each turn = 4 nodes. Give headroom.
                config={"recursion_limit": max(80, max_turns * 8)},
            )

            filename = os.path.join(output_dir, f"res_{profile_id}_{_now_stamp()}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "profile": profile,
                        "final_status": state.get("final_status"),
                        "turns_taken": min(state.get("current_turn", 1) - 1, max_turns),
                        "history": [
                            {"role": (m.name or "unknown"), "content": content_to_text(m.content)}
                            for m in state.get("messages", [])
                        ],
                        "judge_logs": state.get("analysis_logs", []),
                        "guard_logs": state.get("guard_logs", []),
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
            print(f"!!! Experiment Failed {profile_id}: {e}")


# -------------------------------
# 6) CLI
# -------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Safety Evaluation experiments (4-node, Scheme B: Semantic Guard; AS+Judge vs SUT+Guard)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--asp", type=str, default=None, choices=["openai", "deepseek", "gemini", "xai"])
    parser.add_argument("--sut", type=str, default=None, choices=["openai", "deepseek", "gemini", "xai"])

    # Optional overrides (otherwise: judge defaults to AS camp; guard defaults to SUT camp)
    parser.add_argument("--judge", type=str, default=None, choices=["openai", "deepseek", "gemini", "xai"])
    parser.add_argument("--guard", type=str, default=None, choices=["openai", "deepseek", "gemini", "xai"])

    parser.add_argument("--asp-api-key", type=str, default=None)
    parser.add_argument("--judge-api-key", type=str, default=None)
    parser.add_argument("--sut-api-key", type=str, default=None)
    parser.add_argument("--guard-api-key", type=str, default=None)

    parser.add_argument("--asp-model", type=str, default=None)
    parser.add_argument("--judge-model", type=str, default=None)
    parser.add_argument("--sut-model", type=str, default=None)
    parser.add_argument("--guard-model", type=str, default=None)

    parser.add_argument("--profiles", type=str, default="profiles.json")
    parser.add_argument("--output-dir", type=str, default="experiment_results")
    parser.add_argument("--max-turns", type=int, default=20)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if not args.asp:
        raise SystemExit("!!! Error: --asp (AS provider) is required")
    if not args.sut:
        raise SystemExit("!!! Error: --sut (SUT provider) is required")

    run_batch(
        profiles_path=args.profiles,
        output_dir=f"{args.output_dir}/{args.sut}",
        as_provider=args.asp,
        sut_provider=args.sut,

        judge_provider=args.judge,
        guard_provider=args.guard,

        as_api_key=args.asp_api_key,
        judge_api_key=args.judge_api_key,
        sut_api_key=args.sut_api_key,
        guard_api_key=args.guard_api_key,

        as_model=args.asp_model,
        judge_model=args.judge_model,
        sut_model=args.sut_model,
        guard_model=args.guard_model,

        max_turns=args.max_turns,
    )