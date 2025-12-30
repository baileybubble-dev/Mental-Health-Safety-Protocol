#!/usr/bin/env python3
"""
Plot cumulative breach rates by dialogue round for run2 results.

For each model (deepseek, gemini, xai), this script:
- loads all result JSON files in experiment_results/run2/<model>/
- finds the first round that hit TERMINATE_BREACH (if any)
- computes the cumulative percentage of profiles that have breached
  by each round
- saves a PNG plot and prints a brief table (including round 5).

Usage:
    python experiment_results/run2/plot_breach_curves.py

Notes:
- matplotlib is optional; if it is missing the script will still print
  the cumulative percentages. Install with:
      pip install matplotlib
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import matplotlib.pyplot as plt
except ImportError:  # pragma: no cover - optional dependency
    plt = None


BASE_DIR = Path(__file__).resolve().parent
RUN1_DIR = BASE_DIR.parent / "run1"
MODELS = ["deepseek", "gemini", "xai"]
OUTPUT_FIG = BASE_DIR / "breach_curves.png"


@dataclass
class RunRecord:
    profile_id: str
    breach_turn: Optional[int]
    turns_taken: int
    source_file: Path


def find_breach_turn(run: Dict) -> Optional[int]:
    """Return the first turn where research_status == TERMINATE_BREACH."""
    logs = run.get("logs", [])
    for entry in logs:
        if entry.get("research_status") == "TERMINATE_BREACH":
            turn_val = entry.get("turn")
            if turn_val is not None:
                return turn_val
            # if the marker lacks a turn, fall back to overall turns_taken
            break
    # Fallback: if final_status says breach but logs lack the marker.
    if run.get("final_status") == "TERMINATE_BREACH":
        return run.get("turns_taken")
    return None


def load_model_runs(model: str) -> List[RunRecord]:
    """Load all run JSONs for a model and extract breach metadata."""
    model_dir = BASE_DIR / model
    records: List[RunRecord] = []

    for path in sorted(model_dir.glob("res_*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        breach_turn = find_breach_turn(data)
        turns_taken = data.get("turns_taken") or len(data.get("logs", []))
        profile_id = data.get("profile", {}).get("id", path.stem)

        records.append(
            RunRecord(
                profile_id=profile_id,
                breach_turn=breach_turn,
                turns_taken=turns_taken,
                source_file=path,
            )
        )

    return records


def load_breach_turns(run_dir: Path, model: str) -> List[int]:
    """Collect breach turns for a model in the given run directory."""
    turns: List[int] = []
    model_dir = run_dir / model
    for path in sorted(model_dir.glob("res_*.json")):
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        if data.get("final_status") != "TERMINATE_BREACH":
            continue
        breach_turn = find_breach_turn(data)
        if breach_turn is not None:
            turns.append(int(breach_turn))
    return turns


def cumulative_curve(records: List[RunRecord]) -> List[Tuple[int, float]]:
    """Compute cumulative breach percentage per round."""
    if not records:
        return []

    max_turn = max(r.turns_taken for r in records)
    total = len(records)
    curve: List[Tuple[int, float]] = []

    for turn in range(1, max_turn + 1):
        breached = sum(
            1
            for r in records
            if r.breach_turn is not None and r.breach_turn <= turn
        )
        curve.append((turn, breached / total * 100))

    return curve


def print_snapshot(curves: Dict[str, List[Tuple[int, float]]], target_turn: int) -> None:
    """Print cumulative breach rates at a specific round."""
    print(f"\nCumulative breach rate by round <= {target_turn}:")
    for model, curve in curves.items():
        if not curve:
            print(f"- {model}: no data")
            continue
        # Find the last point with turn <= target_turn
        pct = next((pct for turn, pct in reversed(curve) if turn <= target_turn), 0.0)
        print(f"- {model:<8}: {pct:5.2f}%")


def bootstrap_delta(
    turns_static: List[int], turns_adaptive: List[int], iters: int = 5000
) -> Optional[Tuple[float, float, float]]:
    """
    Bootstrap delta of mean time-to-breach (adaptive - static).
    Returns (delta_mean, ci_low, ci_high) or None if insufficient data.
    """
    if not turns_static or not turns_adaptive:
        return None
    n_static = len(turns_static)
    n_adaptive = len(turns_adaptive)
    deltas: List[float] = []
    for _ in range(iters):
        sample_static = [turns_static[random.randrange(n_static)] for _ in range(n_static)]
        sample_adaptive = [turns_adaptive[random.randrange(n_adaptive)] for _ in range(n_adaptive)]
        deltas.append(
            (sum(sample_adaptive) / n_adaptive) - (sum(sample_static) / n_static)
        )
    deltas.sort()
    delta_mean = sum(deltas) / len(deltas)
    ci_low = deltas[int(0.025 * len(deltas))]
    ci_high = deltas[int(0.975 * len(deltas)) - 1]
    return delta_mean, ci_low, ci_high


def compute_delta_stats() -> Dict[str, Optional[Tuple[float, float, float]]]:
    """Return bootstrap delta stats per model (adaptive - static)."""
    stats: Dict[str, Optional[Tuple[float, float, float]]] = {}
    if not RUN1_DIR.exists():
        return stats
    for model in MODELS:
        turns_static = load_breach_turns(RUN1_DIR, model)
        turns_adaptive = load_breach_turns(BASE_DIR, model)
        stats[model] = bootstrap_delta(turns_static, turns_adaptive)
    return stats


def print_delta_summary(stats: Dict[str, Optional[Tuple[float, float, float]]]) -> None:
    """Print bootstrap ∆turns (adaptive - static) with 95% CI per model."""
    if not stats:
        print("\n[delta] run1 directory missing; skip regime comparison.")
        return

    print("\n∆turns (Adaptive - Static) with bootstrap 95% CI (breach cases only):")
    for model in MODELS:
        item = stats.get(model)
        if item is None:
            print(f"- {model:<8}: insufficient data")
            continue
        delta_mean, ci_low, ci_high = item
        print(
            f"- {model:<8}: {delta_mean:5.2f} turns "
            f"[{ci_low:5.2f}, {ci_high:5.2f}]"
        )


def plot_curves(
    curves: Dict[str, List[Tuple[int, float]]],
    delta_stats: Optional[Dict[str, Optional[Tuple[float, float, float]]]] = None,
) -> None:
    """Plot cumulative breach curves for each model."""
    if plt is None:
        print("matplotlib not installed; skipping plot generation.")
        return

    label_map = {
        "deepseek": "deepseek-chat",
        "gemini": "gemini-2.5-flash",
        "xai": "grok-3",
    }

    fig, ax = plt.subplots(figsize=(8, 5))
    for model, curve in curves.items():
        if not curve:
            continue
        turns, pct = zip(*curve)
        ax.plot(turns, pct, marker="o", label=label_map.get(model, model))

    ax.set_xlabel("Dialogue round", fontsize=12)
    ax.set_ylabel("Cumulative breach (%)", fontsize=12)
    ax.set_title("Cumulative breach rate by round (w/ Adaptive Probing)", fontsize=14)
    ax.set_xticks(range(1, max((turn for curve in curves.values() for turn, _ in curve), default=0) + 1))
    ax.set_yticks(range(0, 101, 10))
    ax.set_ylim(0, 100)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(title="SUT Model")

    if delta_stats:
        lines = []
        for model in MODELS:
            item = delta_stats.get(model)
            if item is None:
                lines.append(f"{model}: n/a")
            else:
                dm, lo, hi = item
                lines.append(f"{model}: Δ={dm:.2f} [{lo:.2f}, {hi:.2f}]")
        text = "\n".join(lines)
        ax.text(
            0.02,
            0.98,
            text,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=10,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "#999999", "linewidth": 0.5},
        )

    fig.tight_layout()
    OUTPUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_FIG, dpi=200)
    print(f"Saved plot to {OUTPUT_FIG}")


def main(target_turn: int = 5) -> None:
    curves: Dict[str, List[Tuple[int, float]]] = {}

    for model in MODELS:
        records = load_model_runs(model)
        curves[model] = cumulative_curve(records)
        print(f"Loaded {len(records)} runs for {model}")

    print_snapshot(curves, target_turn)
    delta_stats = compute_delta_stats()
    plot_curves(curves, delta_stats)
    print_delta_summary(delta_stats)


if __name__ == "__main__":
    main(target_turn=5)

