"""Breach-category distribution over all 263 original breaches:
held-out (Claude, general rubric) vs the paper's keyword classifier -> category_summary.json, categories_all.csv"""
import json, os, csv, sys
from collections import Counter
from analyze_audit import kappa, CAT_MAP, classify_breach_type
ROOT = os.path.dirname(os.path.abspath(__file__))
rows = []
def add(items_file, results_file):
    items = {json.loads(l)["item_id"]: json.loads(l) for l in open(os.path.join(ROOT, items_file), encoding="utf-8")}
    for l in open(os.path.join(ROOT, results_file), encoding="utf-8"):
        r = json.loads(l); iid, q, c = r["custom_id"].split("__")
        if q != "q2" or c != "med" or iid not in items or items[iid]["stratum"] != "flagged": continue
        it = items[iid]; p = r.get("parsed") or {}
        cat = p.get("category", "unparsed") if p.get("breach") else "none"
        d = json.load(open(os.path.join(ROOT, it["source_file"]), encoding="utf-8"))
        rows.append({"item_id": iid, "profile_id": it["profile_id"], "mode": it["mode"], "sut": it["sut"],
                     "phenotype": d["profile"]["behavioral_phenotype"], "keyword": CAT_MAP.get(classify_breach_type(d), "other"),
                     "heldout": cat, "severity": p.get("severity")})
add("items.jsonl", "results.jsonl")
add("items_cat.jsonl", "results_cat.jsonl")
S = {"n_breaches": len(rows), "by_mode_n": Counter(r["mode"] for r in rows)}
for src in ("heldout", "keyword"):
    for m in ("static", "adaptive"):
        sel = [r[src] for r in rows if r["mode"] == m]
        S[f"{src}_{m}"] = {k: f"{v}/{len(sel)} ({v/len(sel)*100:.1f}%)" for k, v in Counter(sel).most_common()}
pairs = [(r["keyword"], r["heldout"]) for r in rows if r["heldout"] not in ("none", "unparsed")]
S["agreement_keyword_vs_heldout"] = {"n": len(pairs), "agree": round(sum(a == b for a, b in pairs) / len(pairs), 3), "kappa": round(kappa(*zip(*pairs)), 3)}
json.dump(S, open(os.path.join(ROOT, "category_summary.json"), "w"), indent=2, default=dict)
with open(os.path.join(ROOT, "categories_all.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(json.dumps(S, indent=1, default=dict))
