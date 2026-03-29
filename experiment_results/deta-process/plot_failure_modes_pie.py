#!/usr/bin/env python3
"""
Plot failure modes (breach_type) as separate pie charts for run1 and run2.

Output:
- Saves PNG to experiment_results/failure_modes_pie.png
- Prints a table of counts and percentages (per run).

Usage:
    python experiment_results/plot_failure_modes_pie.py

Notes:
- matplotlib is optional; if missing, the script will still print the tables.
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

try:
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover - optional dependency
    plt = None


ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT.parent
RUNS = ["run1", "run2"]
MODELS = ["deepseek", "gemini", "xai"]
OUT_FIG = ROOT / "failure_modes_pie.png"
# Which statuses to count as a "failure" event
INCLUDED_STATUSES = {"TERMINATE_BREACH", "PROCEED"}

# Run display labels
RUN_LABELS = {
    "run1": "Static Progression",
    "run2": "Adaptive Probing",
}

# Mapping breach type to English
BREACH_TYPE_EN = {
    "绝对保证/零风险承诺": "Absolute Guarantee/Zero-Risk Promise",
    "自我伤害认可/允许性语言": "Self-Harm Endorsement/Permissive Language",
    "认知验证/扭曲认知验证": "Cognitive Validation/Distorted Cognition Validation",
    "专业角色越界": "Professional Role Boundary Breach",
    "关系依赖/排他性承诺": "Relationship Dependency/Exclusive Commitment",
    "医学诊断/医疗建议越界": "Medical Diagnosis/Medical Advice Boundary Breach",
    "其他越界": "Other Boundary Breaches",
    "未知类型": "Unknown Type",
    "N/A": "N/A",
}

# Optional: import classify_breach_type for fallback when breach_type is missing
CLASSIFIER = None
try:
    sys.path.insert(0, str(RESULTS_DIR / "run1"))
    from analyze_results import classify_breach_type  # type: ignore

    CLASSIFIER = classify_breach_type
except Exception:
    CLASSIFIER = None


def iter_json_files(run_dir: Path) -> Iterable[Path]:
    """Yield all res_*.json files under the given run directory for known models."""
    for model in MODELS:
        for path in (run_dir / model).glob("res_*.json"):
            yield path


def translate_breach_type(breach_type: str) -> str:
    return BREACH_TYPE_EN.get(breach_type, breach_type)


def load_breach_types_run(run: str) -> Counter:
    """Collect breach_type counts for one run."""
    counter: Counter = Counter()
    run_dir = RESULTS_DIR / run
    for path in iter_json_files(run_dir):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        status = data.get("final_status")
        if status not in INCLUDED_STATUSES:
            continue
        # PROCEED = no breach; exclude from failure-mode pie
        if status == "PROCEED":
            continue

        breach_type = data.get("breach_type")
        # For PROCEED or missing type, try to classify; otherwise label Unknown
        if (not breach_type or breach_type == "未知类型" or breach_type == "N/A") and CLASSIFIER:
            try:
                breach_type = CLASSIFIER(data)
            except Exception:
                breach_type = None
        if not breach_type:
            breach_type = "Unknown Type"
        counter[breach_type] += 1
    return counter


def load_breach_types_by_run() -> Dict[str, Counter]:
    return {run: load_breach_types_run(run) for run in RUNS}


def print_tables(by_run: Dict[str, Counter]) -> None:
    for run in RUNS:
        counter = by_run.get(run, Counter())
        total = sum(counter.values())
        print(f"Failure modes (breach_type) for {run} ({RUN_LABELS.get(run, run)}):")
        for breach_type, count in counter.most_common():
            pct = count / total * 100 if total else 0
            print(f"- {translate_breach_type(breach_type)}: {count} ({pct:.2f}%)")
        print("")


def plot_pies(by_run: Dict[str, Counter]) -> None:
    if plt is None:
        print("matplotlib not installed; skipping pie chart.")
        return

    # Reset to default style
    try:
        plt.style.use("default")
    except Exception:
        pass

    # Improve font rendering (English labels, but keep unicode-safe minus)
    try:
        import matplotlib

        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:
        pass

    fig, axes = plt.subplots(1, len(RUNS), figsize=(12, 7.5))
    if len(RUNS) == 1:
        axes = [axes]

    legend_handles = []
    legend_labels = []

    for ax, run in zip(axes, RUNS):
        counter = by_run.get(run, Counter())
        total = sum(counter.values())
        if total == 0:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12)
            ax.axis("off")
            continue

        labels: List[str] = []
        sizes: List[int] = []
        for breach_type, count in counter.most_common():
            labels.append(translate_breach_type(breach_type))
            sizes.append(count)

        # Guard against empty sizes (shouldn't happen after total==0 check)
        if not sizes:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=12)
            ax.axis("off")
            continue

        res = ax.pie(
            sizes,
            startangle=120,
            wedgeprops={"linewidth": 0.8, "edgecolor": "white"},
            autopct=None,
        )
        # matplotlib may return 2 or 3 items depending on version
        if len(res) == 3:
            wedges, _texts, _autotexts = res
        else:
            wedges, _texts = res
        if not legend_handles:
            legend_handles = wedges
            legend_labels = labels
        ax.set_title(f"{RUN_LABELS.get(run, run)}", fontsize=14)

        # Add percentage labels with callouts for small slices
        for wedge, label, count in zip(wedges, labels, sizes):
            pct = count / total * 100 if total else 0
            ang = (wedge.theta2 + wedge.theta1) / 2.0
            x = wedge.r * 0.7 * np.cos(np.deg2rad(ang))
            y = wedge.r * 0.7 * np.sin(np.deg2rad(ang))
            display = f"{count}/{total}\n({pct:.1f}%)"
            if pct < 8:
                # place outside with arrow
                offset = 1.15
                ox = offset * np.cos(np.deg2rad(ang))
                oy = offset * np.sin(np.deg2rad(ang))
                ax.annotate(
                    display,
                    xy=(np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang))),
                    xytext=(ox, oy),
                    ha="center",
                    va="center",
                    fontsize=9,
                    arrowprops=dict(arrowstyle="-", connectionstyle="arc3,rad=0.2", color="gray"),
                )
            else:
                ax.text(x, y, display, ha="center", va="center", fontsize=9, color="black")

    fig.suptitle("Failure modes by strategy", fontsize=18)
    if legend_handles:
        fig.legend(
            legend_handles,
            legend_labels,
            title="Breach Modes",
            loc="lower center",
            bbox_to_anchor=(0.5, 0.02),  # place inside figure area
            fontsize=14,
            title_fontsize=16,
            ncol=2,
            handlelength=1.0,
            handletextpad=0.6,
            columnspacing=0.8,
        )
    fig.tight_layout(rect=[0, 0.12, 1, 0.93])
    # Adjust bottom to keep legend inside the image
    fig.subplots_adjust(bottom=0.16)
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=200)
    print(f"Saved pie chart to {OUT_FIG}")


def main() -> None:
    by_run = load_breach_types_by_run()
    print_tables(by_run)
    plot_pies(by_run)


if __name__ == "__main__":
    main()
