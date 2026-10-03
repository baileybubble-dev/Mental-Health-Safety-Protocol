"""Build the blinded audit sample for the held-out judge.

Sample: 20 VPs drawn at random (fixed seed) from the 50 profiles; for each VP,
all 6 conversations (3 SUTs x 2 pressure modes).
Items per conversation:
  - breached:     the reply flagged by the original Judge (orig_label=1)
                  and the reply immediately before it (orig_label=0, if any)
  - not breached: the last reply that the original Judge evaluated (orig_label=0)

Turn indexing note:
  run1 (static, 2-node): the Judge verdict for SUT reply k is produced in the
      AS call of turn k+1, so the flagged reply is #(turns_taken - 1) and the
      final SUT reply in the transcript was never judged.
  run2 (adaptive, 3-node): the Judge evaluates SUT reply k in turn k, so the
      flagged reply is #turns_taken.
"""
import json, glob, random, hashlib, os, csv

SEED = 20261003
N_VP = 20
SUBSET_PER_STRATUM = 20  # for effort sweep / test-retest
ROOT = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(ROOT, "..", "experiment_results")
MODES = {"run1": "static", "run2": "adaptive"}
SUTS = ["deepseek", "gemini", "xai"]

def load_conv(run, sut, pid):
    files = sorted(glob.glob(os.path.join(RES, run, sut, f"res_{pid}_*.json")))
    assert len(files) == 1, (run, sut, pid, files)
    return files[0], json.load(open(files[0], encoding="utf-8"))

def transcript_upto(history, k):
    """History up to and including SUT reply k (1-indexed), with the target marked."""
    out, n_sut = [], 0
    for m in history:
        if m["role"] == "AS":
            out.append(("User", m["content"]))
        else:
            n_sut += 1
            tag = "Assistant [TARGET RESPONSE]" if n_sut == k else "Assistant"
            out.append((tag, m["content"]))
            if n_sut == k:
                break
    assert n_sut == k
    return "\n\n".join(f"### {who}\n{txt.strip()}" for who, txt in out)

def main():
    profiles = json.load(open(os.path.join(ROOT, "..", "profiles.json"), encoding="utf-8"))
    ids = sorted(p["id"] for p in profiles)
    rng = random.Random(SEED)
    chosen = sorted(rng.sample(ids, N_VP))
    items = []
    for run, mode in MODES.items():
        for sut in SUTS:
            for pid in chosen:
                path, d = load_conv(run, sut, pid)
                logs, hist = d["logs"], d["history"]
                breach_idx = [i for i, l in enumerate(logs) if l.get("research_status") == "TERMINATE_BREACH"]
                if breach_idx:
                    i = breach_idx[0]
                    k = i if run == "run1" else i + 1
                    targets = [(k, 1, "flagged")]
                    if k >= 2:
                        targets.append((k - 1, 0, "pre_breach"))
                else:
                    k = len(logs) - 1 if run == "run1" else len(logs)
                    targets = [(k, 0, "nonbreach_final")]
                for k, lab, stratum in targets:
                    raw = f"{run}|{sut}|{pid}|{k}"
                    items.append({
                        "item_id": "it" + hashlib.sha1(raw.encode()).hexdigest()[:10],
                        "profile_id": pid, "mode": mode, "sut": sut,
                        "source_file": os.path.relpath(path, ROOT),
                        "reply_no": k, "turns_taken": d["turns_taken"],
                        "stratum": stratum, "orig_label": lab,
                        "target_language": d["profile"].get("target_language"),
                        "criterion": d["profile"]["alignment_departure_criteria"],
                        "transcript": transcript_upto(hist, k),
                    })
    rng2 = random.Random(SEED + 1)
    rng2.shuffle(items)  # blinded, random order
    pos = [it["item_id"] for it in items if it["orig_label"] == 1]
    neg = [it["item_id"] for it in items if it["orig_label"] == 0]
    subset = set(rng2.sample(pos, SUBSET_PER_STRATUM) + rng2.sample(neg, SUBSET_PER_STRATUM))
    for it in items:
        it["in_subset"] = it["item_id"] in subset
    with open(os.path.join(ROOT, "items.jsonl"), "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    with open(os.path.join(ROOT, "sample_manifest.json"), "w") as f:
        json.dump({"seed": SEED, "chosen_vps": chosen, "n_items": len(items),
                   "n_flagged": len(pos), "n_negative": len(neg),
                   "strata": {s: sum(it["stratum"] == s for it in items) for s in ["flagged", "pre_breach", "nonbreach_final"]},
                   "subset_size": len(subset)}, f, indent=2)
    print(json.dumps(json.load(open(os.path.join(ROOT, "sample_manifest.json"))), indent=2))
    chars = [len(it["transcript"]) for it in items]
    print("transcript chars: mean", sum(chars) // len(chars), "max", max(chars), "total", sum(chars))

if __name__ == "__main__":
    main()
