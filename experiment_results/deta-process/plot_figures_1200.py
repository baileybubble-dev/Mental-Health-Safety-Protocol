#!/usr/bin/env python3
"""Export Figures 4-7 for JMIR upload (max 1200 x 1200 px). Same data as the manuscript figures."""
import csv, json, sys, random, statistics
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import MaxNLocator

HERE = Path(__file__).resolve().parent; RES = HERE.parent; ROOT = RES.parent
OUT = ROOT / "figures_jmir_1200"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(RES / "run1"))
from analyze_results import extract_main_condition  # noqa
plt.rcParams.update({"font.family": "DejaVu Sans"})
MODELS = ["deepseek", "gemini", "xai"]; LAB = {"deepseek": "deepseek-chat", "gemini": "gemini-2.5-flash", "xai": "grok-3"}

def breach_turns(run):
    out = {}
    for m in MODELS:
        t = []
        for p in sorted((RES / run / m).glob("res_*.json")):
            d = json.load(open(p, encoding="utf-8"))
            if d.get("final_status") == "TERMINATE_BREACH":
                t.append(d["turns_taken"] - 1 if run == "run1" else d["turns_taken"])
        out[m] = t
    return out
static, adaptive = breach_turns("run1"), breach_turns("run2")

# ---- Figure 4 (7x4 in @170 dpi -> 1190x680) ----
fig, ax = plt.subplots(figsize=(7, 4)); x = range(3); w = 0.3
def bp(data, pos, col):
    return ax.boxplot(data, positions=pos, widths=w, patch_artist=True, boxprops=dict(facecolor=col, alpha=0.6),
                      medianprops=dict(color="black"), whiskerprops=dict(color=col), capprops=dict(color=col),
                      flierprops=dict(markerfacecolor=col, markeredgecolor=col, markersize=4))
b1 = bp([static[m] for m in MODELS], [i - w / 2 for i in x], "#4C9AFF"); b2 = bp([adaptive[m] for m in MODELS], [i + w / 2 for i in x], "#FFB347")
ax.set_xticks(list(x)); ax.set_xticklabels([LAB[m] for m in MODELS]); ax.set_ylabel("Turns (breach cases)", fontsize=12)
ax.yaxis.set_major_locator(MaxNLocator(integer=True)); ax.grid(True, axis="y", linestyle="--", alpha=0.4)
ax.legend([b1["boxes"][0], b2["boxes"][0]], ["Static Progression", "Adaptive Probing"], title="Strategy")
plt.tight_layout(); plt.savefig(OUT / "Figure4.png", dpi=170); plt.close()

# ---- Figure 5 (8x5 in @150 dpi -> 1200x750) ----
def boot(s, a, iters=5000, seed=2026):
    rng = random.Random(seed); ds = []
    for _ in range(iters):
        ss = [s[rng.randrange(len(s))] for _ in s]; aa = [a[rng.randrange(len(a))] for _ in a]; ds.append(sum(aa)/len(aa) - sum(ss)/len(ss))
    ds.sort(); return statistics.mean(a) - statistics.mean(s), ds[int(.025*iters)], ds[int(.975*iters)-1]
fig, ax = plt.subplots(figsize=(8, 5))
for m in MODELS:
    n = len(list((RES / "run2" / m).glob("res_*.json")))
    ax.plot(range(1, 21), [sum(1 for t in adaptive[m] if t <= r) / n * 100 for r in range(1, 21)], marker="o", label=LAB[m])
ax.set_xlabel("Dialogue round", fontsize=12); ax.set_ylabel("Cumulative breach (%)", fontsize=12)
ax.set_xticks(range(1, 21)); ax.set_yticks(range(0, 101, 10)); ax.set_ylim(0, 100); ax.grid(True, linestyle="--", alpha=0.4); ax.legend(title="SUT Model", loc="lower right")
txt = "\n".join(f"{LAB[m]}: Δ={d:.2f} [{lo:.2f}, {hi:.2f}]" for m in MODELS for d, lo, hi in [boot(static[m], adaptive[m])])
ax.text(0.02, 0.98, txt, transform=ax.transAxes, va="top", ha="left", fontsize=10, bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "#999999", "linewidth": 0.5})
fig.tight_layout(); fig.savefig(OUT / "Figure5.png", dpi=150); plt.close()

# ---- shared category data ----
CATS = ["absolute_guarantee", "relational_dependence", "professional_role", "harmful_belief_validation", "medical_advice", "self_harm_endorsement"]
LABEL = {"absolute_guarantee": "Certainty / zero-risk\nreassurance", "relational_dependence": "Relational\ndependence",
         "professional_role": "Professional role\nsubstitution", "harmful_belief_validation": "Harmful belief\nvalidation",
         "medical_advice": "Direct medical\nadvice", "self_harm_endorsement": "Self-harm\nendorsement", "none": "Not assigned to a\ngeneral category"}
MODES = [("static", "Static progression"), ("adaptive", "Adaptive probing")]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
def norm(c):
    l = str(c).lower()
    if "c-ptsd" in l: return "C-PTSD"
    for pre, nm in [("mdd","MDD"),("ocd","OCD"),("gad","GAD"),("panic disorder","Panic disorder"),("bpd","BPD traits"),("bipolar","Bipolar"),
                    ("alcohol use disorder","AUD"),("substance use","SUD (stimulants)"),("eating disorder","Eating disorder"),
                    ("delusional disorder","Delusional/paranoid"),("body dysmorphic","Body dysmorphic")]:
        if l.startswith(pre): return nm
    if "hypervigilance" in l: return "Trauma hypervigilance"
    if "paranoid ideation" in l: return "Delusional/paranoid"
    return "Other"
rows = list(csv.DictReader(open(ROOT / "judge_audit" / "categories_all.csv", encoding="utf-8")))
for r in rows: r["cond"] = norm(extract_main_condition(r["phenotype"]))

# ---- Figure 7 (10x6.2 in @120 dpi -> 1200x744) ----
fig, ax = plt.subplots(figsize=(10, 6.2)); y = np.arange(len(CATS)); h = 0.36; summ = {}
for k, (mode, title) in enumerate(MODES):
    sel = [r["heldout"] for r in rows if r["mode"] == mode]; cls = [c for c in sel if c != "none"]; n = len(cls); cnt = Counter(cls)
    summ[mode] = (len(sel), sel.count("none")); pct = np.array([cnt[c] / n * 100 for c in CATS]); off = -h/2 - .02 if k == 0 else h/2 + .02
    ax.barh(y + off, pct, height=h, color={"static": "#2a78d6", "adaptive": "#eb6834"}[mode], label=f"{title} (n = {n})", zorder=2)
    for yi, p, c in zip(y + off, pct, CATS): ax.text(p + .6, yi, f"{cnt[c]} ({p:.1f}%)", va="center", fontsize=10, color=INK2)
ax.set_yticks(y); ax.set_yticklabels([LABEL[c] for c in CATS], fontsize=11); ax.invert_yaxis()
ax.set_xlabel("Share of classifiable breaches (%)", fontsize=11); ax.set_xlim(0, 45)
ax.xaxis.grid(True, color=GRID, linewidth=.8, zorder=0); ax.set_axisbelow(True)
for s in ("top", "right"): ax.spines[s].set_visible(False)
ax.legend(loc="lower right", frameon=False, fontsize=11)
fig.tight_layout(); fig.savefig(OUT / "Figure7.png", dpi=120, facecolor="white"); plt.close()

# ---- Figure 6: panels stacked vertically (10x10 in @120 dpi -> 1200x1200) ----
cols = CATS + ["none"]; conds = [c for c, _ in Counter(r["cond"] for r in rows).most_common()]
cmap = LinearSegmentedColormap.from_list("b", ["#f4f8fd", "#b7d3f2", "#5b9be3", "#2a78d6", "#123f80"])
fig, axes = plt.subplots(2, 1, figsize=(10, 10), sharex=True)
for ax, (mode, title) in zip(axes, MODES):
    M = np.zeros((len(conds), len(cols))); N = np.zeros(len(conds))
    for r in rows:
        if r["mode"] == mode: i = conds.index(r["cond"]); M[i, cols.index(r["heldout"])] += 1; N[i] += 1
    P = np.divide(M, N[:, None], out=np.zeros_like(M), where=N[:, None] > 0) * 100
    im = ax.imshow(P, cmap=cmap, vmin=0, vmax=100, aspect="auto")
    ax.set_yticks(range(len(conds))); ax.set_yticklabels(conds, fontsize=10); ax.tick_params(axis="y", length=0)
    ax.set_title(title, fontsize=13, pad=6)
    ax.set_xticks(np.arange(-.5, len(cols)), minor=True); ax.set_yticks(np.arange(-.5, len(conds)), minor=True)
    ax.grid(which="minor", color="white", linewidth=2); ax.tick_params(which="minor", length=0)
    for sp in ax.spines.values(): sp.set_visible(False)
    for i in range(len(conds)):
        for j in range(len(cols)):
            if M[i, j] > 0: ax.text(j, i, f"{int(M[i,j])}/{int(N[i])}", ha="center", va="center", fontsize=9, color="white" if P[i, j] >= 55 else INK)
axes[1].set_xticks(range(len(cols))); axes[1].set_xticklabels([LABEL[c] for c in cols], rotation=35, ha="right", fontsize=9.5)
cb = fig.colorbar(im, ax=axes, fraction=.03, pad=.02); cb.set_label("Share of breaches within condition (%)", fontsize=10); cb.outline.set_visible(False)
fig.subplots_adjust(left=.2, right=.86, top=.96, bottom=.15, hspace=.12)
fig.savefig(OUT / "Figure6.png", dpi=120, facecolor="white"); plt.close()
print("ok")
