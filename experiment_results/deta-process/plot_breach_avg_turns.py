#!/usr/bin/env python3
"""
Plot average turns-to-breach for each model across run1 and run2.

Output:
- Saves PNG to experiment_results/breach_avg_turns.png
- Prints a small table with the averages.

Usage:
    python experiment_results/plot_breach_avg_turns.py

Notes:
- matplotlib is optional; if missing, the script will still print the table.
"""

import json
import statistics
from pathlib import Path
from typing import Dict, List, Optional

try:
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
except ImportError:  # pragma: no cover - optional dependency
    plt = None
    MaxNLocator = None


ROOT = Path(__file__).resolve().parent
RUNS = ["run1", "run2"]
MODELS = ["deepseek", "gemini", "xai"]
# Display labels for models and runs
MODEL_LABELS = {
    "deepseek": "deepseek-chat",
    "gemini": "gemini-2.5-flash",
    "xai": "grok-3",
}
RUN_LABELS = {
    "run1": "Static Pgrogression",
    "run2": "Adaptive Probing",
}
OUT_FIG = ROOT / "breach_avg_turns.png"


def load_breach_turns(run_dir: Path, model: str) -> List[int]:
    """Return turn counts for breach cases of a model in a given run directory."""
    model_dir = run_dir / model
    turns: List[int] = []
    for path in model_dir.glob("res_*.json"):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if data.get("final_status") != "TERMINATE_BREACH":
            continue
        turn = data.get("turns_taken")
        if turn is None:
            # fallback to logs length
            turn = len(data.get("logs", []))
        if isinstance(turn, (int, float)):
            turns.append(int(turn))
    return turns


def compute_avg_turns() -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    """Compute average and std-dev of breach turns per model for each run."""
    results: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {run: {} for run in RUNS}
    for run in RUNS:
        run_dir = ROOT / run
        for model in MODELS:
            turns = load_breach_turns(run_dir, model)
            avg = statistics.mean(turns) if turns else None
            # population std-dev so len==1 -> 0.0; keep None if no data
            std = statistics.pstdev(turns) if turns else None
            results[run][model] = {"mean": avg, "std": std, "turns": turns}
    return results


def print_table(avgs: Dict[str, Dict[str, Dict[str, Optional[float]]]]) -> None:
    print("Average turns (breach cases) with std-dev:")
    for run in RUNS:
        print(f"- {run}:")
        for model in MODELS:
            metrics = avgs[run].get(model, {})
            mean_val = metrics.get("mean")
            std_val = metrics.get("std")
            mean_display = f"{mean_val:.2f}" if mean_val is not None else "N/A"
            std_display = f"{std_val:.2f}" if std_val is not None else "N/A"
            print(f"    {model:8}: {mean_display} (± {std_display})")


def plot(avgs: Dict[str, Dict[str, Dict[str, Optional[float]]]]) -> None:
    if plt is None:
        print("matplotlib not installed; skipping plot.")
        return

    x_labels = [MODEL_LABELS.get(m, m) for m in MODELS]
    x = range(len(x_labels))
    width = 0.3

    run1_data = [avgs["run1"].get(m, {}).get("turns", []) for m in MODELS]
    run2_data = [avgs["run2"].get(m, {}).get("turns", []) for m in MODELS]

    fig, ax = plt.subplots(figsize=(7, 4))
    box_run1 = ax.boxplot(
        run1_data,
        positions=[i - width / 2 for i in x],
        widths=width,
        patch_artist=True,
        boxprops=dict(facecolor="#4C9AFF", alpha=0.6),
        medianprops=dict(color="black"),
        whiskerprops=dict(color="#4C9AFF"),
        capprops=dict(color="#4C9AFF"),
        flierprops=dict(markerfacecolor="#4C9AFF", markeredgecolor="#4C9AFF", markersize=4),
    )
    box_run2 = ax.boxplot(
        run2_data,
        positions=[i + width / 2 for i in x],
        widths=width,
        patch_artist=True,
        boxprops=dict(facecolor="#FFB347", alpha=0.6),
        medianprops=dict(color="black"),
        whiskerprops=dict(color="#FFB347"),
        capprops=dict(color="#FFB347"),
        flierprops=dict(markerfacecolor="#FFB347", markeredgecolor="#FFB347", markersize=4),
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(x_labels)
    ax.set_ylabel("Turns (breach cases)", fontsize=12)
    ax.set_title("Breach turns by model", fontsize=14)
    if MaxNLocator is not None:
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(True, axis="y", linestyle="--", alpha=0.4)
    ax.legend(
        [box_run1["boxes"][0], box_run2["boxes"][0]],
        [RUN_LABELS["run1"], RUN_LABELS["run2"]],
        title="Strategy",
    )

    plt.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(OUT_FIG, dpi=200)
    print(f"Saved plot to {OUT_FIG}")


def main() -> None:
    avgs = compute_avg_turns()
    print_table(avgs)
    plot(avgs)


if __name__ == "__main__":
    main()

