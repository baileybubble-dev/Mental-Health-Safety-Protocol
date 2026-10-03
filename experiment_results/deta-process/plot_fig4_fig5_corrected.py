#!/usr/bin/env python3
"""Figures 4 and 5 (revision) with corrected static-progression time-to-breach.

In the static (2-node) runs, the Judge verdict on SUT reply k is produced in the AS call
of turn k+1, so the flagged reply is turns_taken - 1. Adaptive (3-node) runs: turns_taken.
Outputs: fig4_breach_turns_corrected.png, fig5_breach_curves_corrected.png
"""
import json, random, statistics
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

HERE = Path(__file__).resolve().parent
RES = HERE.parent
MODELS = ["deepseek", "gemini", "xai"]
LABEL = {"deepseek": "deepseek-chat", "gemini": "gemini-2.5-flash", "xai": "grok-3"}

def breach_turns(run):
    out = {}
    for m in MODELS:
        t = []
        for p in sorted((RES / run / m).glob("res_*.json")):
            d = json.load(open(p, encoding="utf-8"))
            if d.get("final_status") != "TERMINATE_BREACH":
                continue
            k = d["turns_taken"] - 1 if run == "run1" else d["turns_taken"]
            t.append(int(k))
        out[m] = t
    return out

static, adaptive = breach_turns("run1"), breach_turns("run2")

def boot(s, a, iters=5000, seed=2026):
    rng = random.Random(seed); ds = []
    for _ in range(iters):
        ss = [s[rng.randrange(len(s))] for _ in s]; aa = [a[rng.randrange(len(a))] for _ in a]
        ds.append(sum(aa) / len(aa) - sum(ss) / len(ss))
    ds.sort()
    return statistics.mean(a) - statistics.mean(s), ds[int(.025 * iters)], ds[int(.975 * iters) - 1]

summary = {}
for m in MODELS:
    summary[m] = {"static_mean": round(statistics.mean(static[m]), 2), "adaptive_mean": round(statistics.mean(adaptive[m]), 2),
                  "delta_ci": [round(v, 2) for v in boot(static[m], adaptive[m])]}
alls = sum(static.values(), []); alla = sum(adaptive.values(), [])
summary["overall"] = {"static_mean": round(statistics.mean(alls), 2), "adaptive_mean": round(statistics.mean(alla), 2),
                      "n_static": len(alls), "n_adaptive": len(alla),
                      "relative_reduction_pct": round((statistics.mean(alls) - statistics.mean(alla)) / statistics.mean(alls) * 100, 1)}
json.dump(summary, open(HERE / "time_to_breach_corrected.json", "w"), indent=2)
print(json.dumps(summary, indent=1))

# Figure 4: same style as the original boxplot
fig, ax = plt.subplots(figsize=(7, 4)); x = range(len(MODELS)); w = 0.3
def bp(data, pos, col):
    return ax.boxplot(data, positions=pos, widths=w, patch_artist=True, boxprops=dict(facecolor=col, alpha=0.6),
                      medianprops=dict(color="black"), whiskerprops=dict(color=col), capprops=dict(color=col),
                      flierprops=dict(markerfacecolor=col, markeredgecolor=col, markersize=4))
b1 = bp([static[m] for m in MODELS], [i - w / 2 for i in x], "#4C9AFF")
b2 = bp([adaptive[m] for m in MODELS], [i + w / 2 for i in x], "#FFB347")
ax.set_xticks(list(x)); ax.set_xticklabels([LABEL[m] for m in MODELS])
ax.set_ylabel("Turns (breach cases)", fontsize=12); ax.set_title("Breach turns by model", fontsize=14)
ax.yaxis.set_major_locator(MaxNLocator(integer=True)); ax.grid(True, axis="y", linestyle="--", alpha=0.4)
ax.legend([b1["boxes"][0], b2["boxes"][0]], ["Static Progression", "Adaptive Probing"], title="Strategy")
plt.tight_layout(); plt.savefig(HERE / "fig4_breach_turns_corrected.png", dpi=200); plt.close()

# Figure 5: adaptive cumulative curves (unchanged) + corrected delta box
fig, ax = plt.subplots(figsize=(8, 5))
for m in MODELS:
    files = sorted((RES / "run2" / m).glob("res_*.json")); n = len(files)
    bt = [t for t in adaptive[m]]
    curve = [(r, sum(1 for t in bt if t <= r) / n * 100) for r in range(1, 21)]
    ax.plot(*zip(*curve), marker="o", label=LABEL[m])
ax.set_xlabel("Dialogue round", fontsize=12); ax.set_ylabel("Cumulative breach (%)", fontsize=12)
ax.set_title("Cumulative breach rate by round (w/ Adaptive Probing)", fontsize=14)
ax.set_xticks(range(1, 21)); ax.set_yticks(range(0, 101, 10)); ax.set_ylim(0, 100)
ax.grid(True, linestyle="--", alpha=0.4); ax.legend(title="SUT Model", loc="lower right")
txt = "\n".join(f"{LABEL[m]}: Δ={summary[m]['delta_ci'][0]:.2f} [{summary[m]['delta_ci'][1]:.2f}, {summary[m]['delta_ci'][2]:.2f}]" for m in MODELS)
ax.text(0.02, 0.98, txt, transform=ax.transAxes, va="top", ha="left", fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "#999999", "linewidth": 0.5})
fig.tight_layout(); fig.savefig(HERE / "fig5_breach_curves_corrected.png", dpi=200); plt.close()
print("saved")
