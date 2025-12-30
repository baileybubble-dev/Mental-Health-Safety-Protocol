#!/usr/bin/env python3
"""
Plot profile distributions (main condition and demographics) from profiles.json.

Outputs (saved under experiment_results/profile_plots/):
- main_condition.png (Top-N + Other, horizontal percent bars)
- demographics_small_multiples.png (6-panel small multiples: age, gender,
  marital status, has children, education, income)

Usage:
    OMP_NUM_THREADS=1 KMP_DUPLICATE_LIB_OK=TRUE MPLBACKEND=Agg python experiment_results/plot_profiles.py
"""

import json
import re
from collections import Counter
from pathlib import Path
import matplotlib.pyplot as plt

# ---------------- Config ----------------
PROFILES_PATH = Path("../profiles.json")
OUT_DIR = Path("./")
TOP_N_COND = 12
FIG_W, FIG_H = 8, 5          # single chart
SMALL_MULT_FIG = (3.6, 7.8)  # small multiples grid for single-column layout
STACKED_DIM_FIG = (4.2, 5.5)  # 100% stacked bar chart for key demographics
DOT_FIG = (4.0, 4.0)         # dot plot alternative (shorter vertically)


def ensure_out_dir():
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_main_condition(phenotype: str) -> str:
    if not phenotype or phenotype == "Unknown":
        return "Unknown"
    main = re.sub(r"\s+with\s+.*$", "", phenotype, flags=re.IGNORECASE)
    main = re.sub(r"\s+伴随.*$", "", main)
    main = re.sub(r"（.*$", "", main)
    if "(" in main:
        main = main.split("(")[0].strip()
    return main.strip() if main.strip() else phenotype


def bucket_age(age):
    try:
        a = int(age)
    except Exception:
        return "Unknown"
    if a < 25:
        return "18-24"
    if a < 35:
        return "25-34"
    if a < 45:
        return "35-44"
    if a < 55:
        return "45-54"
    if a < 65:
        return "55-64"
    return "65+"


def bucket_income(income: str) -> str:
    if not income or income == "Unknown":
        return "Unknown"
    # expect formats like "$45,000-$60,000" or "$120,000+"
    nums = re.findall(r"\d[\d,]*", income)
    if not nums:
        return "Unknown"
    try:
        vals = [int(n.replace(",", "")) for n in nums]
        if len(vals) == 1:
            v = vals[0]
        else:
            v = sum(vals) / len(vals)
    except Exception:
        return "Unknown"
    if v < 50000:
        return "Low"
    if v < 100000:
        return "Medium"
    return "High"


def topn_with_other(counter: Counter, top_n: int):
    if len(counter) <= top_n:
        return counter
    items = counter.most_common(top_n)
    top_sum = sum(v for _, v in items)
    other_sum = sum(counter.values()) - top_sum
    items.append(("Other", other_sum))
    return Counter(dict(items))


def plot_bar_pct(counter: Counter, title: str, outfile: Path, xlim100=True):
    total = sum(counter.values())
    labels, counts = zip(*counter.most_common())
    pct = [c / total * 100 for c in counts]
    plt.figure(figsize=(FIG_W, FIG_H))
    plt.barh(labels, pct, color="#4e79a7")
    plt.gca().invert_yaxis()
    for i, v in enumerate(pct):
        plt.text(v + (0.5 if xlim100 else max(pct) * 0.01), i, f"{v:.1f}%", va="center", fontsize=9)
    plt.xlabel("Percentage")
    plt.title(f"{title} (N={total})", fontsize=12)
    if xlim100:
        plt.xlim(0, 100)
    plt.tight_layout()
    plt.savefig(outfile, dpi=200)
    plt.close()

def normalize_counter(counter: Counter) -> list:
    """Return list of (label, pct) sorted by pct desc."""
    total = sum(counter.values())
    return [(k, v / total * 100 if total else 0) for k, v in counter.most_common()]

def plot_stacked_100(dims_data, outfile: Path):
    """
    dims_data: list of tuples (dim_name, counter)
    Each counter will be turned into a 100% stacked horizontal bar (one bar per dim).
    """
    fig, ax = plt.subplots(figsize=STACKED_DIM_FIG)
    y_labels = []
    bar_data = []
    all_cats = set()
    for dim_name, counter in dims_data:
        norm = normalize_counter(counter)
        y_labels.append(dim_name)
        bar_data.append(dict(norm))
        all_cats.update([k for k, _ in norm])
    all_cats = sorted(all_cats, key=lambda x: x)  # stable order; could be frequency-based

    # Colors + hatches consistent across all dims
    cmap = plt.get_cmap("tab20")
    hatch_patterns = ["", "//", "\\\\", "xx", "..", "**", "++", "--", "||", "oo", "OO", "++.."]
    colors = {cat: cmap(i % 20) for i, cat in enumerate(all_cats)}
    hatches = {cat: hatch_patterns[i % len(hatch_patterns)] for i, cat in enumerate(all_cats)}

    y_positions = list(range(len(y_labels)))
    lefts = [0.0] * len(y_labels)

    for cat in all_cats:
        widths = []
        for bd in bar_data:
            widths.append(bd.get(cat, 0.0))
        ax.barh(
            y_positions,
            widths,
            left=lefts,
            color=colors[cat],
            edgecolor="white",
            hatch=hatches[cat],
            label=cat,
            height=0.7,
        )
        lefts = [l + w for l, w in zip(lefts, widths)]

    # No in-bar text to avoid overlap; legend carries category info

    ax.set_yticks(y_positions)
    ax.set_yticklabels(y_labels, fontsize=9)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Percentage", fontsize=9)
    ax.set_title("Key demographics (100% stacked)", fontsize=11)
    ax.invert_yaxis()

    # Place legend below
    handles, labels = ax.get_legend_handles_labels()
    # Deduplicate while preserving order
    seen = set()
    uniq_handles = []
    uniq_labels = []
    for h, l in zip(handles, labels):
        if l in seen:
            continue
        seen.add(l)
        uniq_handles.append(h)
        uniq_labels.append(l)
    lgd = ax.legend(
        uniq_handles,
        uniq_labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),  # below the bars
        fontsize=7.0,
        ncol=6,  # one category per column up to 6 cols
        title="Categories",
        title_fontsize=8.0,
    )

    plt.tight_layout()
    plt.subplots_adjust(bottom=0.26)
    plt.savefig(outfile, dpi=200)
    plt.close()


def plot_dot(dims_data, tail_dims, outfile: Path):
    """
    Dot plot:
    - Regular dims: show all categories with percentage.
    - Tail dims: only one dot showing uniq count (labelled uniq=XX).
    """
    regular_dims = [d for d in dims_data if d[0] not in tail_dims]
    tail_data = [d for d in dims_data if d[0] in tail_dims]

    rows = []
    # regular dims: per-category percent
    for dim_name, counter in regular_dims:
        total = sum(counter.values())
        for cat, cnt in counter.most_common():
            pct = cnt / total * 100 if total else 0
            rows.append((dim_name, cat, pct, "pct"))
    # tail dims: one dot per dim with uniq count
    for dim_name, counter in tail_data:
        rows.append((dim_name, f"{len(counter)} unique values", len(counter), "uniq"))

    dims = list(dict.fromkeys([r[0] for r in rows]))  # preserve order
    y_positions = {}
    y = 0
    gap = 0.6  # larger gap to reduce vertical overlap
    for dim in dims:
        cats = [r for r in rows if r[0] == dim]
        for cat in cats:
            y_positions[(dim, cat[1])] = y
            y -= 0.5
        y -= gap

    fig, ax = plt.subplots(figsize=DOT_FIG)

    dim_palette = plt.get_cmap("tab10")
    dim_colors = {d: dim_palette(i % 10) for i, d in enumerate(dims)}

    # bands per dimension
    for dim in dims:
        ys = [pos for (d, _), pos in y_positions.items() if d == dim]
        if not ys:
            continue
        band_min = min(ys) - 0.25
        band_max = max(ys) + 0.25
        ax.axhspan(band_min, band_max, color=dim_colors[dim], alpha=0.10, zorder=0)

    for dim, cat, val, kind in rows:
        y = y_positions[(dim, cat)]
        c = dim_colors.get(dim, "#4e79a7")
        ax.plot(val, y, "o", color=c)
        if kind == "pct":
            label = f"{cat} {val:.1f}%"
        else:
            label = f"{cat}"
        ax.text(val + 3.0, y, label, va="center", ha="left", fontsize=7, color=c)

    for dim in dims:
        ys = [pos for (d, _), pos in y_positions.items() if d == dim]
        if ys:
            mid = sum(ys) / len(ys)
            ax.text(105, mid, dim, va="center", ha="left", fontsize=8, fontweight="bold", color=dim_colors.get(dim, "#000"))

    x_max = max([val for _, _, val, _ in rows] + [100])
    ax.set_xlim(0, x_max * 1.25)
    ax.set_ylim(min(y_positions.values()) - 0.5, 0.5)
    ax.set_xlabel("Value (percentage or distinct count)", fontsize=8)
    ax.set_yticks([])
    ax.set_title("Key demographics distributions", fontsize=11)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(outfile, dpi=200)
    plt.close()


def main():
    ensure_out_dir()

    profiles = json.load(open(PROFILES_PATH, "r", encoding="utf-8"))

    # -------- Main condition --------
    main_cond_counter = Counter(extract_main_condition(p.get("behavioral_phenotype", "Unknown")) for p in profiles)
    main_cond_counter = topn_with_other(main_cond_counter, TOP_N_COND)
    plot_bar_pct(main_cond_counter, "Main Condition (Top 12 + Other)", OUT_DIR / "main_condition.png", xlim100=False)

    # -------- Demographics --------
    age_counter = Counter(bucket_age(p.get("demographics", {}).get("age")) for p in profiles)
    gender_counter = Counter(p.get("demographics", {}).get("gender", "Unknown") for p in profiles)
    marital_counter = Counter(p.get("demographics", {}).get("marital_status", "Unknown") for p in profiles)
    has_child_counter = Counter(
        "Yes"
        if p.get("demographics", {}).get("has_children") is True
        else "No"
        if p.get("demographics", {}).get("has_children") is False
        else "Unknown"
        for p in profiles
    )
    edu_counter = Counter(p.get("demographics", {}).get("education_level", "Unknown") for p in profiles)
    income_counter = Counter(p.get("demographics", {}).get("income", "Unknown") for p in profiles)
    income_counter = Counter(bucket_income(k) for k in income_counter.elements())
    occupation_counter = Counter(p.get("demographics", {}).get("occupation", "Unknown") for p in profiles)
    ethnicity_counter = Counter(p.get("demographics", {}).get("ethnicity", "Unknown") for p in profiles)
    location_counter = Counter(p.get("demographics", {}).get("location", "Unknown") for p in profiles)

    fig, axes = plt.subplots(3, 2, figsize=SMALL_MULT_FIG)
    dims = [
        ("Age Group", age_counter, True),
        ("Gender", gender_counter, True),
        ("Marital Status", marital_counter, True),
        ("Has Children", has_child_counter, True),
        ("Education", edu_counter, False),
        ("Income", income_counter, False),
    ]

    for ax, (title, counter, xlim100) in zip(axes.flatten(), dims):
        total = sum(counter.values())
        labels, counts = zip(*counter.most_common())
        pct = [c / total * 100 for c in counts]
        ax.barh(labels, pct, color="#4e79a7")
        ax.invert_yaxis()
        for i, v in enumerate(pct):
            ax.text(v + (0.5 if xlim100 else max(pct) * 0.01), i, f"{v:.1f}%", va="center", fontsize=8)
        ax.set_title(f"{title} (N={total})", fontsize=9)
        ax.set_xlabel("Percentage", fontsize=8)
        ax.tick_params(axis="both", labelsize=8)
        if xlim100:
            ax.set_xlim(0, 100)

    plt.tight_layout(h_pad=1.0, w_pad=0.8)
    plt.savefig(OUT_DIR / "demographics_small_multiples.png", dpi=200)
    plt.close()

    # -------- 100% stacked for key demographics --------
    key_dims = [
        ("Age", age_counter),
        ("Gender", gender_counter),
        ("Marital", marital_counter),
        ("Children", has_child_counter),
        ("Education", edu_counter),
        ("Income", income_counter),
    ]
    tail_dims_data = [
        ("Occupation", occupation_counter),
        ("Ethnicity", ethnicity_counter),
        ("Location", location_counter),
    ]
    tail_dim_names = [d[0] for d in tail_dims_data]

    # Dot plot: key dims show per-category points; tail dims show only uniq count
    plot_dot(key_dims + tail_dims_data, tail_dim_names, OUT_DIR / "demographics_dot.png")
    # 100% stacked bars (labels only for segments >7% to reduce overlap)
    plot_stacked_100(key_dims, OUT_DIR / "demographics_stacked_100.png")

    print("Saved plots to", OUT_DIR.resolve())


if __name__ == "__main__":
    main()

