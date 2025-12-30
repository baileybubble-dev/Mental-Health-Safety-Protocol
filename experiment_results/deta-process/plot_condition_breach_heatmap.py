#!/usr/bin/env python3
"""
Plot heatmap of breach type distribution by main condition for run1 & run2.
Outputs: experiment_results/condition_breach_heatmap.png
"""

import json
import sys
from collections import Counter
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
RUN1_DIR = SCRIPT_DIR / "run1"
RUN2_DIR = SCRIPT_DIR / "run2"
ANALYZE_DIR = SCRIPT_DIR / "run1"  # for classify_breach_type
OUT_PNG = SCRIPT_DIR / "condition_breach_heatmap.png"
TOP_N_CONDITIONS = 12

BREACH_LABELS_EN = {
    "绝对保证/零风险承诺": "Absolute Guarantee",
    "自我伤害认可/允许性语言": "Self-Harm Endorsement",
    "认知验证/扭曲认知验证": "Cognitive Validation",
    "专业角色越界": "Professional Role",
    "关系依赖/排他性承诺": "Relationship Dependency",
    "医学诊断/医疗建议越界": "Medical Advice",
    "其他越界": "Other",
    "未知类型": "Unknown",
    "N/A": "N/A",
}

CONDITION_SHORT = {
    "Other disorder: trauma-related hypervigilance": "Trauma hypervigilance",
    "C-PTSD from past abusive relationship; hypervigilance and anger spikes. Legal work language shapes how she frames revenge as 'accountability'.": "C-PTSD (abusive relationship)",
    "C-PTSD traits from chronic workplace discrimination and a high-conflict divorce; hypervigilance, anger control efforts, and insomnia; distrust of therapists due to prior invalidation; seeks ‘professional-grade’ guidance without vulnerability.": "C-PTSD (work+divorce)",
    "Alcohol use disorder in early remission": "AUD (remission)",
    "Alcohol use disorder in early attempts at sobriety": "AUD (early sobriety)",
    "C-PTSD": "C-PTSD",
    "MDD": "MDD",
    "OCD": "OCD",
    "GAD": "GAD",
    "Panic disorder": "Panic disorder",
    "BPD traits": "BPD traits",
    "Bipolar": "Bipolar",
    "AUD": "AUD",
    "SUD (stimulants)": "SUD (stimulants)",
    "Eating disorder": "Eating disorder",
    "Trauma hypervigilance": "Trauma hypervigilance",
    "Delusional/paranoid": "Delusional/paranoid",
    "Body dysmorphic": "Body dysmorphic",
    "Unknown": "Unknown",
    "Other": "Other",
}

def load_classifiers():
    sys.path.insert(0, str(ANALYZE_DIR))
    from analyze_results import classify_breach_type, extract_main_condition
    return classify_breach_type, extract_main_condition

def load_data(run_dir, classify_breach_type, extract_main_condition):
    rows = []
    for path in Path(run_dir).rglob("res_*.json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if "profile" not in data:
            continue
        main = extract_main_condition(data.get("profile", {}).get("behavioral_phenotype", "Unknown"))
        if data.get("final_status") != "TERMINATE_BREACH":
            continue
        bt = data.get("breach_type")
        if not bt or bt in ("未知类型", "N/A", "其他越界"):
            bt = classify_breach_type(data)
        rows.append((main, bt))
    return rows

def build_matrix(rows, cond_set):
    bt_set = sorted({bt for _, bt in rows})
    mat = pd.DataFrame(0, index=cond_set, columns=bt_set, dtype=float)
    for cond, bt in rows:
        cond_mapped = cond if cond in cond_set else "Other"
        if cond_mapped not in mat.index:
            continue
        mat.loc[cond_mapped, bt] += 1
    mat_pct = mat.div(mat.sum(axis=1), axis=0).fillna(0) * 100
    return mat_pct

def plot_heatmap(mat1_pct, mat2_pct, outfile):
    matplotlib.rcParams["font.sans-serif"] = [
        "Arial Unicode MS", "Noto Sans CJK SC", "Microsoft YaHei",
        "PingFang SC", "Heiti SC", "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False

    all_cols = sorted(set(mat1_pct.columns) | set(mat2_pct.columns))
    mat1 = mat1_pct.reindex(columns=all_cols, fill_value=0)
    mat2 = mat2_pct.reindex(columns=all_cols, fill_value=0)

    n_rows = max(len(mat1), len(mat2))
    fig, axes = plt.subplots(
        1, 2, figsize=(18, max(8, n_rows * 0.5)), sharey=True
    )
    for ax, mat_pct, title in zip(
        axes, [mat1, mat2], ["Static Progression", "Adaptive Probing"]
    ):
        im = ax.imshow(mat_pct.values, cmap="YlOrRd", aspect="auto", vmin=0, vmax=100)
        xlabels = [BREACH_LABELS_EN.get(x, x) for x in mat_pct.columns]
        ax.set_xticks(np.arange(mat_pct.shape[1]))
        ax.set_xticklabels(xlabels, rotation=35, ha="right", fontsize=16)
        ax.set_yticks(np.arange(mat_pct.shape[0]))
        ax.set_yticklabels(mat_pct.index, fontsize=16)
        ax.set_title(title, fontsize=20)
        for i in range(mat_pct.shape[0]):
            for j in range(mat_pct.shape[1]):
                val = mat_pct.iat[i, j]
                if val > 0:
                    ax.text(j, i, f"{val:.0f}%", ha="center", va="center", fontsize=15, color="black")

    # shared colorbar on the right, vertical
    cbar = fig.colorbar(
        im, ax=axes.ravel().tolist(), orientation="vertical",
        fraction=0.045, pad=0.02, label="Percentage"
    )
    cbar.ax.tick_params(labelsize=16)
    cbar.ax.set_ylabel(cbar.ax.get_ylabel(), fontsize=16)
    # nudge colorbar upward to align with heatmaps
    bbox = cbar.ax.get_position()
    cbar.ax.set_position([bbox.x0, bbox.y0 + 0.08, bbox.width, bbox.height])

    # leave room for long x-labels and colorbar
    plt.subplots_adjust(left=0.13, right=0.86, bottom=0.24, top=0.93, wspace=0.12)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(outfile, dpi=200)
    plt.close()

def main():
    clf_bt, extract_main_condition = load_classifiers()
    rows1 = load_data(RUN1_DIR, clf_bt, extract_main_condition)
    rows2 = load_data(RUN2_DIR, clf_bt, extract_main_condition)

    def normalize_condition(cond: str) -> str:
        """Map long behavioral_phenotype strings into concise buckets for plotting."""
        if cond is None:
            return "Other"
        cond_str = str(cond)
        lower = cond_str.lower()
        if "c-ptsd" in lower:
            return "C-PTSD"
        if lower.startswith("mdd"):
            return "MDD"
        if lower.startswith("ocd"):
            return "OCD"
        if lower.startswith("gad"):
            return "GAD"
        if lower.startswith("panic disorder"):
            return "Panic disorder"
        if lower.startswith("bpd"):
            return "BPD traits"
        if lower.startswith("bipolar"):
            return "Bipolar"
        if lower.startswith("alcohol use disorder"):
            return "AUD"
        if lower.startswith("substance use"):
            return "SUD (stimulants)"
        if lower.startswith("eating disorder"):
            return "Eating disorder"
        if "hypervigilance" in lower or "trauma-related hypervigilance" in lower:
            return "Trauma hypervigilance"
        if lower.startswith("delusional disorder") or "paranoid ideation" in lower:
            return "Delusional/paranoid"
        if lower.startswith("body dysmorphic"):
            return "Body dysmorphic"
        return "Other"

    rows1 = [(normalize_condition(c), bt) for c, bt in rows1]
    rows2 = [(normalize_condition(c), bt) for c, bt in rows2]
    if not rows1 or not rows2:
        print("No TERMINATE_BREACH records found.")
        return
    combined = rows1 + rows2
    cond_counts = Counter([r[0] for r in combined])
    top_conditions = [c for c, _ in cond_counts.most_common(TOP_N_CONDITIONS)]
    cond_set = top_conditions + (["Other"] if any(c not in top_conditions for c in cond_counts) else [])
    cond_display = [CONDITION_SHORT.get(c, c) for c in cond_set]

    mat1_pct = build_matrix(rows1, cond_set)
    mat2_pct = build_matrix(rows2, cond_set)
    mat1_pct.index = cond_display
    mat2_pct.index = cond_display

    plot_heatmap(mat1_pct, mat2_pct, OUT_PNG)

if __name__ == "__main__":
    main()