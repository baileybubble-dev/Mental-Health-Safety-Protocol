#!/usr/bin/env python3
"""Figures 6 and 7 (revision): breach categories assigned by the held-out auditor.
Input : judge_audit/categories_all.csv (263 breaches; column 'heldout')
Output: fig6_condition_category_heatmap.png, fig7_category_distribution.png
"""
import csv, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "run1"))
from analyze_results import extract_main_condition  # noqa: E402

CATS = ["absolute_guarantee", "relational_dependence", "professional_role",
        "harmful_belief_validation", "medical_advice", "self_harm_endorsement"]
LABEL = {"absolute_guarantee": "Certainty / zero-risk\nreassurance",
         "relational_dependence": "Relational\ndependence",
         "professional_role": "Professional role\nsubstitution",
         "harmful_belief_validation": "Harmful belief\nvalidation",
         "medical_advice": "Direct medical\nadvice",
         "self_harm_endorsement": "Self-harm\nendorsement",
         "none": "Not assigned to a\ngeneral category"}
MODES = [("static", "Static progression"), ("adaptive", "Adaptive probing")]
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e4e3df", "#ffffff"
SERIES = {"static": "#2a78d6", "adaptive": "#eb6834"}   # categorical slots 1-2

def normalize_condition(c):
    l = str(c).lower()
    for key, name in [("c-ptsd", "C-PTSD")]:
        if key in l: return name
    for pre, name in [("mdd", "MDD"), ("ocd", "OCD"), ("gad", "GAD"), ("panic disorder", "Panic disorder"),
                      ("bpd", "BPD traits"), ("bipolar", "Bipolar"), ("alcohol use disorder", "AUD"),
                      ("substance use", "SUD (stimulants)"), ("eating disorder", "Eating disorder"),
                      ("delusional disorder", "Delusional/paranoid"), ("body dysmorphic", "Body dysmorphic")]:
        if l.startswith(pre): return name
    if "hypervigilance" in l: return "Trauma hypervigilance"
    if "paranoid ideation" in l: return "Delusional/paranoid"
    return "Other"

rows = list(csv.DictReader(open(ROOT / "judge_audit" / "categories_all.csv", encoding="utf-8")))
for r in rows:
    r["cond"] = normalize_condition(extract_main_condition(r["phenotype"]))

plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": INK2, "axes.labelcolor": INK,
                     "xtick.color": INK2, "ytick.color": INK, "text.color": INK})

# ---------------- Figure 7: category distribution by mode ----------------
fig, ax = plt.subplots(figsize=(10, 6.2), dpi=300)
y = np.arange(len(CATS)); h = 0.36
summary = {}
for k, (mode, title) in enumerate(MODES):
    sel = [r["heldout"] for r in rows if r["mode"] == mode]
    cls = [c for c in sel if c != "none"]; n = len(cls); cnt = Counter(cls)
    summary[mode] = (len(sel), n, sel.count("none"))
    pct = np.array([cnt[c] / n * 100 for c in CATS])
    off = -h / 2 - 0.02 if k == 0 else h / 2 + 0.02
    ax.barh(y + off, pct, height=h, color=SERIES[mode], label=f"{title} (n = {n})", zorder=2)
    for yi, p, c in zip(y + off, pct, CATS):
        ax.text(p + 0.6, yi, f"{cnt[c]} ({p:.1f}%)", va="center", ha="left", fontsize=9, color=INK2)
ax.set_yticks(y); ax.set_yticklabels([LABEL[c] for c in CATS], fontsize=10)
ax.invert_yaxis()
ax.set_xlabel("Share of classifiable breaches (%)", fontsize=10)
ax.set_xlim(0, 45)
ax.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0); ax.set_axisbelow(True)
for s in ("top", "right"): ax.spines[s].set_visible(False)
ax.legend(loc="lower right", frameon=False, fontsize=10)
s, a = summary["static"], summary["adaptive"]
fig.text(0.01, 0.01, f"Categories assigned by the held-out auditor. Not assigned to any general category: "
         f"{s[2]}/{s[0]} static and {a[2]}/{a[0]} adaptive breaches (excluded from percentages).",
         fontsize=8, color=INK2)
fig.tight_layout(rect=[0, 0.04, 1, 1])
fig.savefig(HERE / "fig7_category_distribution.png", facecolor=SURF)
plt.close(fig)

# ---------------- Figure 6: condition x category heatmap ----------------
cols = CATS + ["none"]
tot = Counter(r["cond"] for r in rows)
conds = [c for c, _ in tot.most_common()]
cmap = LinearSegmentedColormap.from_list("blue_seq", ["#f4f8fd", "#b7d3f2", "#5b9be3", "#2a78d6", "#123f80"])
fig, axes = plt.subplots(1, 2, figsize=(17, 8.8), dpi=300, sharey=True)
for ax, (mode, title) in zip(axes, MODES):
    M = np.zeros((len(conds), len(cols))); N = np.zeros(len(conds))
    for r in rows:
        if r["mode"] != mode: continue
        i = conds.index(r["cond"]); M[i, cols.index(r["heldout"])] += 1; N[i] += 1
    P = np.divide(M, N[:, None], out=np.zeros_like(M), where=N[:, None] > 0) * 100
    im = ax.imshow(P, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(cols))); ax.set_xticklabels([LABEL[c] for c in cols], rotation=40, ha="right", fontsize=9.5)
    ax.set_yticks(range(len(conds))); ax.set_yticklabels(conds, fontsize=11)
    ax.set_title(title, fontsize=14, pad=10)
    ax.set_xticks(np.arange(-.5, len(cols)), minor=True); ax.set_yticks(np.arange(-.5, len(conds)), minor=True)
    ax.grid(which="minor", color=SURF, linewidth=2); ax.tick_params(which="minor", length=0)
    for sp in ax.spines.values(): sp.set_visible(False)
    for i in range(len(conds)):
        for j in range(len(cols)):
            if M[i, j] > 0:
                ax.text(j, i, f"{int(M[i, j])}/{int(N[i])}", ha="center", va="center", fontsize=8.5,
                        color="#ffffff" if P[i, j] >= 55 else INK)
    ax.tick_params(axis="y", length=0)
    if ax is axes[1]:
        ax.tick_params(axis="y", left=False, labelleft=False)
cb = fig.colorbar(im, ax=axes.ravel().tolist(), fraction=0.025, pad=0.02)
cb.set_label("Share of breaches within condition (%)", fontsize=10); cb.outline.set_visible(False)
fig.subplots_adjust(left=0.15, right=0.88, bottom=0.17, top=0.94, wspace=0.05)
fig.text(0.15, 0.015, "Cells show breaches of each type / all breaches for that condition and pressure mode. Categories assigned by the held-out auditor.", fontsize=9, color=INK2)
fig.savefig(HERE / "fig6_condition_category_heatmap.png", facecolor=SURF)
plt.close(fig)
print("saved fig6/fig7")
