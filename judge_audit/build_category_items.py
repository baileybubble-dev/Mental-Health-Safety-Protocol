"""Flagged breach turns of the 30 VPs not in the audit sample -> items_cat.jsonl
(the 111 flagged turns of the 20 audited VPs already have a held-out category from q2/med)."""
import json, glob, os, random, hashlib
from build_items import load_conv, transcript_upto, MODES, SUTS, ROOT
audited = set(json.load(open(os.path.join(ROOT, "sample_manifest.json")))["chosen_vps"])
ids = sorted(p["id"] for p in json.load(open(os.path.join(ROOT, "..", "profiles.json"), encoding="utf-8")))
items = []
for run, mode in MODES.items():
    for sut in SUTS:
        for pid in ids:
            if pid in audited: continue
            path, d = load_conv(run, sut, pid)
            b = [i for i, l in enumerate(d["logs"]) if l.get("research_status") == "TERMINATE_BREACH"]
            if not b: continue
            k = b[0] if run == "run1" else b[0] + 1
            raw = f"{run}|{sut}|{pid}|{k}"
            items.append({"item_id": "it" + hashlib.sha1(raw.encode()).hexdigest()[:10], "profile_id": pid, "mode": mode,
                          "sut": sut, "source_file": os.path.relpath(path, ROOT), "reply_no": k, "stratum": "flagged",
                          "orig_label": 1, "in_subset": False, "criterion": d["profile"]["alignment_departure_criteria"],
                          "transcript": transcript_upto(d["history"], k)})
random.Random(20261004).shuffle(items)
with open(os.path.join(ROOT, "items_cat.jsonl"), "w", encoding="utf-8") as f:
    for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")
print("flagged turns (non-audited VPs):", len(items), {m: sum(i["mode"] == m for i in items) for m in ("static", "adaptive")})
