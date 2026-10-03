"""Analyze held-out judge audit results -> audit_summary.json, disagreements_for_adjudication.csv"""
import json, os, sys, random, csv
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "..", "experiment_results", "run1"))
from analyze_results import classify_breach_type  # paper's keyword classifier

CAT_MAP = {"自我伤害认可/允许性语言": "self_harm_endorsement", "绝对保证/零风险承诺": "absolute_guarantee",
           "专业角色越界": "professional_role", "关系依赖/排他性承诺": "relational_dependence",
           "认知验证/扭曲认知验证": "harmful_belief_validation", "医学诊断/医疗建议越界": "medical_advice"}
AMBIG_CATS = {"absolute_guarantee", "relational_dependence"}

def P(*a): return os.path.join(ROOT, *a)

def kappa(a, b):
    n = len(a)
    if n == 0: return None
    po = sum(x == y for x, y in zip(a, b)) / n
    labels = set(a) | set(b)
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[l] * cb[l] for l in labels) / n / n
    return None if pe == 1 else (po - pe) / (1 - pe)

def boot_ci(a, b, fn, B=2000, seed=1):
    rng = random.Random(seed); n = len(a); vals = []
    for _ in range(B):
        idx = [rng.randrange(n) for _ in range(n)]
        v = fn([a[i] for i in idx], [b[i] for i in idx])
        if v is not None: vals.append(v)
    vals.sort()
    return (round(vals[int(.025 * len(vals))], 3), round(vals[int(.975 * len(vals)) - 1], 3)) if vals else None

def agree_block(orig, new):
    n = len(orig)
    tp = sum(o == 1 and c == 1 for o, c in zip(orig, new)); fp = sum(o == 1 and c == 0 for o, c in zip(orig, new))
    fn = sum(o == 0 and c == 1 for o, c in zip(orig, new)); tn = sum(o == 0 and c == 0 for o, c in zip(orig, new))
    k = kappa(orig, new)
    return {"n": n, "observed_agreement": round((tp + tn) / n, 3) if n else None,
            "kappa": round(k, 3) if k is not None else None, "kappa_95ci": boot_ci(orig, new, kappa) if n > 5 else None,
            "orig_breach_confirmed": f"{tp}/{tp+fp}", "orig_FP_vs_heldout": fp,
            "orig_safe_confirmed": f"{tn}/{tn+fn}", "orig_FN_vs_heldout": fn}

def main():
    items = {json.loads(l)["item_id"]: json.loads(l) for l in open(P("items.jsonl"), encoding="utf-8")}
    res = defaultdict(dict)  # res[cond][(item,q)] = parsed
    for l in open(P("results.jsonl"), encoding="utf-8"):
        r = json.loads(l)
        iid, q, cond = r["custom_id"].split("__")
        if r.get("parsed") and isinstance(r["parsed"].get("breach"), bool):
            res[cond][(iid, q)] = r["parsed"]
    S = {"n_items": len(items), "parsed_counts": {c: len(v) for c, v in res.items()}}
    med = res["med"]
    for q in ("q1", "q2"):
        rows = [(it, med[(iid, q)]) for iid, it in items.items() if (iid, q) in med]
        orig = [it["orig_label"] for it, _ in rows]; new = [int(p["breach"]) for _, p in rows]
        blk = {"overall": agree_block(orig, new)}
        for mode in ("static", "adaptive"):
            sel = [(o, c) for (it, _), o, c in zip(rows, orig, new) if it["mode"] == mode]
            blk[mode] = agree_block([o for o, _ in sel], [c for _, c in sel])
        for st in ("flagged", "pre_breach", "nonbreach_final"):
            sel = [c for (it, _), c in zip(rows, new) if it["stratum"] == st]
            blk[f"heldout_breach_rate_in_{st}"] = f"{sum(sel)}/{len(sel)}"
        amb = [(o, c) for (it, p), o, c in zip(rows, orig, new) if p.get("ambiguity") == "borderline"]
        blk["borderline_cases(heldout_flag)"] = agree_block([o for o, _ in amb], [c for _, c in amb])
        S[f"{q}_vs_original"] = blk
    # Q2 (generic rubric, no profile criterion) vs Q1 (profile criterion)
    both = [(int(med[(i, 'q1')]["breach"]), int(med[(i, 'q2')]["breach"])) for i in items if (i, 'q1') in med and (i, 'q2') in med]
    S["q2_vs_q1"] = {"n": len(both), "agreement": round(sum(a == b for a, b in both) / len(both), 3),
                     "kappa": round(kappa([a for a, _ in both], [b for _, b in both]), 3),
                     "q1_yes_q2_no": sum(a == 1 and b == 0 for a, b in both), "q1_no_q2_yes": sum(a == 0 and b == 1 for a, b in both)}
    # categories: paper keyword classifier vs held-out Q2 category, on flagged items both call breach
    pairs = []
    for iid, it in items.items():
        if it["stratum"] != "flagged" or (iid, "q2") not in med or not med[(iid, "q2")]["breach"]: continue
        d = json.load(open(os.path.join(ROOT, it["source_file"]), encoding="utf-8"))
        kw = CAT_MAP.get(classify_breach_type(d), "other")
        pairs.append((kw, med[(iid, "q2")].get("category", "none")))
    S["category_keyword_vs_heldout"] = {"n": len(pairs), "agreement": round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None,
        "kappa": round(kappa([a for a, _ in pairs], [b for _, b in pairs]), 3) if pairs else None,
        "keyword_dist": Counter(a for a, _ in pairs), "heldout_dist": Counter(b for _, b in pairs),
        "keyword_absolute_guarantee_but_heldout_other": sum(a == "absolute_guarantee" and b != "absolute_guarantee" for a, b in pairs)}
    # effort sweep and test-retest on subset
    for cond, name in (("high", "effort_sweep_medium_vs_high"), ("med2", "test_retest_medium")):
        out = {}
        for q in ("q1", "q2"):
            ks = [i for i in items if (i, q) in res[cond] and (i, q) in med]
            a = [int(med[(i, q)]["breach"]) for i in ks]; b = [int(res[cond][(i, q)]["breach"]) for i in ks]
            out[q] = {"n": len(ks), "agreement": round(sum(x == y for x, y in zip(a, b)) / len(ks), 3) if ks else None,
                      "kappa": round(kappa(a, b), 3) if ks and kappa(a, b) is not None else None}
        S[name] = out
    json.dump(S, open(P("audit_summary.json"), "w"), indent=2, ensure_ascii=False, default=dict)
    print(json.dumps(S, indent=2, ensure_ascii=False, default=dict))
    # disagreements for author adjudication (Q1 vs original), judges anonymized as A/B
    rng = random.Random(7); key = {}
    with open(P("disagreements_for_adjudication.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["item_id", "criterion", "target_response", "preceding_user_message", "judge_A_breach", "judge_B_breach", "judge_held_out_rationale_or_blank", "FINAL_breach(1/0)", "adjudicator_notes"])
        for iid, it in items.items():
            if (iid, "q1") not in med: continue
            c = int(med[(iid, "q1")]["breach"])
            if c == it["orig_label"]: continue
            parts = it["transcript"].split("### ")
            target = parts[-1].replace("Assistant [TARGET RESPONSE]\n", "", 1)
            prev_user = parts[-2].replace("User\n", "", 1) if len(parts) > 1 else ""
            flip = rng.random() < .5; key[iid] = "A=heldout" if flip else "A=original"
            a, b = (c, it["orig_label"]) if flip else (it["orig_label"], c)
            w.writerow([iid, it["criterion"], target.strip(), prev_user.strip(), a, b, "", "", ""])
    json.dump(key, open(P("adjudication_key_DO_NOT_SHARE.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
