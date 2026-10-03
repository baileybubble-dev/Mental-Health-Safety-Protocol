"""Final labels after author adjudication -> final_summary.json"""
import json, csv, random
from analyze_audit import kappa, boot_ci
items = {json.loads(l)["item_id"]: json.loads(l) for l in open("items.jsonl", encoding="utf-8")}
med = {}
for l in open("results.jsonl", encoding="utf-8"):
    r = json.loads(l); i, q, c = r["custom_id"].split("__")
    if c == "med" and r.get("parsed"): med[(i, q)] = r["parsed"]
adj = {r["item_id"]: int(float(r["Rater 1 (1/0)"])) for r in csv.DictReader(open("adjudication_rater1.csv", encoding="utf-8"))}
rows = []
for iid, it in items.items():
    o = it["orig_label"]; c = int(med[(iid, "q1")]["breach"])
    if o != c: assert iid in adj, iid
    f = adj[iid] if o != c else o
    rows.append(dict(iid=iid, mode=it["mode"], stratum=it["stratum"], orig=o, claude=c, final=f,
                     borderline=med[(iid, "q1")].get("ambiguity") == "borderline"))
assert len(adj) == sum(r["orig"] != r["claude"] for r in rows) == 54
def block(sel, a, b):
    x = [r[a] for r in sel]; y = [r[b] for r in sel]; n = len(sel)
    k = kappa(x, y)
    return {"n": n, "agree": sum(i == j for i, j in zip(x, y)), "pct": round(sum(i == j for i, j in zip(x, y)) / n * 100, 1),
            "kappa": round(k, 2) if k is not None else None, "ci": boot_ci(x, y, kappa),
            "FP(a=1,b=0)": sum(i == 1 and j == 0 for i, j in zip(x, y)), "FN(a=0,b=1)": sum(i == 0 and j == 1 for i, j in zip(x, y))}
S = {}
for a in ("orig", "claude"):
    S[f"{a}_vs_final"] = {"overall": block(rows, a, "final")}
    for m in ("static", "adaptive"):
        S[f"{a}_vs_final"][m] = block([r for r in rows if r["mode"] == m], a, "final")
    S[f"{a}_vs_final"]["borderline"] = block([r for r in rows if r["borderline"]], a, "final")
S["adjudication"] = {"n": 54, "sided_with_original": sum(adj[r["iid"]] == r["orig"] for r in rows if r["iid"] in adj and r["orig"] != r["claude"]),
                     "sided_with_claude": sum(adj[r["iid"]] == r["claude"] for r in rows if r["iid"] in adj and r["orig"] != r["claude"])}
for st in ("flagged", "pre_breach", "nonbreach_final"):
    for m in ("static", "adaptive", None):
        sel = [r for r in rows if r["stratum"] == st and (m is None or r["mode"] == m)]
        S[f"final_breach_in_{st}_{m or 'all'}"] = f"{sum(r['final'] for r in sel)}/{len(sel)}"
json.dump(S, open("final_summary.json", "w"), indent=2)
print(json.dumps(S, indent=1))
