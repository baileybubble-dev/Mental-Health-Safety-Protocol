"""Held-out judge audit with Claude (Anthropic API).

Usage:
  python3 run_audit.py estimate        # exact input-token count (free endpoint) + cost estimate
  python3 run_audit.py pilot [N]       # synchronous test on N items (default 2), both questions
  python3 run_audit.py submit          # submit one batch: main + effort sweep + test-retest
  python3 run_audit.py status          # poll the batch
  python3 run_audit.py collect         # download results, parse, update cost ledger

Conditions (custom_id suffix):
  med  : all items, effort=medium            (primary)
  high : 40-item subset, effort=high         (effort sweep)
  med2 : 40-item subset, effort=medium again (test-retest)
"""
import json, os, re, sys, time
import anthropic

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL = "claude-opus-5-5"
MAX_TOKENS = 8000
BUDGET_USD = 20.0
# USD per million tokens
PRICE = {"sync": {"in": 4.0, "out": 20.0}, "batch": {"in": 2.0, "out": 10.0}}
OUT_TOKENS_ASSUMED = 1500  # per call, for pre-submission estimates (replaced by pilot measurement)

def P(*a): return os.path.join(ROOT, *a)

def api_key():
    raw = open(P("..", ".anthropic_key")).read().strip()
    m = re.search(r"(sk-ant-[A-Za-z0-9_\-]+)", raw)
    return m.group(1) if m else raw.split("=")[-1].strip()

def load_items():
    return [json.loads(l) for l in open(P("items.jsonl"), encoding="utf-8")]

SYSTEM = open(P("prompts", "system.md"), encoding="utf-8").read().strip()
RUBRIC = open(P("prompts", "rubric_generic.md"), encoding="utf-8").read().strip()
T_Q1 = open(P("prompts", "task_q1.md"), encoding="utf-8").read().strip()
T_Q2 = open(P("prompts", "task_q2.md"), encoding="utf-8").read().strip()

def build_params(item, q, effort):
    task = T_Q1.format(criterion=item["criterion"]) if q == "q1" else T_Q2.format(rubric=RUBRIC)
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
        "system": SYSTEM,
        "messages": [{"role": "user", "content": [
            # transcript first so Q1/Q2 (and reruns) share a cacheable prefix
            {"type": "text", "text": "Conversation:\n\n" + item["transcript"], "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": task},
        ]}],
    }

def requests_for(items):
    reqs = []
    for it in items:
        for q in ("q1", "q2"):
            reqs.append((f"{it['item_id']}__{q}__med", build_params(it, q, "medium")))
            if it["in_subset"]:
                reqs.append((f"{it['item_id']}__{q}__high", build_params(it, q, "high")))
                reqs.append((f"{it['item_id']}__{q}__med2", build_params(it, q, "medium")))
    return reqs

def ledger():
    f = P("cost_ledger.json")
    return json.load(open(f)) if os.path.exists(f) else {"spent_usd": 0.0, "entries": []}

def add_cost(kind, usage_list, note):
    L = ledger()
    pr = PRICE[kind]
    cost = 0.0
    for u in usage_list:
        inp = u.get("input_tokens", 0) + 1.25 * u.get("cache_creation_input_tokens", 0) + 0.1 * u.get("cache_read_input_tokens", 0)
        cost += inp / 1e6 * pr["in"] + u.get("output_tokens", 0) / 1e6 * pr["out"]
    L["spent_usd"] = round(L["spent_usd"] + cost, 4)
    L["entries"].append({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "n": len(usage_list), "usd": round(cost, 4), "note": note})
    json.dump(L, open(P("cost_ledger.json"), "w"), indent=2)
    return cost

def parse_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

def usage_dict(u):
    d = u.model_dump() if hasattr(u, "model_dump") else dict(u)
    return {k: (d.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}

def text_of(msg):
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

def cmd_estimate(client):
    items = load_items()
    tok = {}
    cache = P("token_counts.json")
    if os.path.exists(cache): tok = json.load(open(cache))
    for it in items:
        for q in ("q1", "q2"):
            key = f"{it['item_id']}__{q}"
            if key in tok: continue
            p = build_params(it, q, "medium")
            r = client.messages.count_tokens(model=p["model"], system=p["system"], messages=p["messages"])
            tok[key] = r.input_tokens
        json.dump(tok, open(cache, "w"))
    reqs = requests_for(items)
    meas = ledger().get("measured_out_tokens_per_call", OUT_TOKENS_ASSUMED)
    tin = sum(tok[cid.rsplit("__", 1)[0]] for cid, _ in reqs)
    tout = meas * len(reqs)
    cost = tin / 1e6 * PRICE["batch"]["in"] + tout / 1e6 * PRICE["batch"]["out"]
    print(f"requests={len(reqs)}  input_tokens={tin:,}  est_output_tokens={tout:,} (assumed {meas}/call)")
    print(f"estimated batch cost (no caching credit): ${cost:.2f}   already spent: ${ledger()['spent_usd']:.2f}   budget: ${BUDGET_USD}")
    return cost

def cmd_pilot(client, n):
    items = load_items()
    picks = [it for it in items if it["orig_label"] == 1][: (n + 1) // 2] + [it for it in items if it["orig_label"] == 0][: n // 2]
    usages, outs = [], []
    for it in picks:
        for q in ("q1", "q2"):
            p = build_params(it, q, "medium")
            msg = client.messages.create(**p)
            u = usage_dict(msg.usage); usages.append(u)
            t = text_of(msg); js = parse_json(t)
            outs.append({"custom_id": f"{it['item_id']}__{q}__pilot", "stop_reason": msg.stop_reason, "usage": u, "parsed": js, "raw_text": t})
            print(f"{it['item_id']} {q} stop={msg.stop_reason} in={u['input_tokens']} cw={u['cache_creation_input_tokens']} cr={u['cache_read_input_tokens']} out={u['output_tokens']} parsed={'OK' if js else 'FAIL'}")
            print("   ", json.dumps(js, ensure_ascii=False)[:300] if js else t[:300])
    cost = add_cost("sync", usages, f"pilot {len(usages)} calls")
    L = ledger(); L["measured_out_tokens_per_call"] = int(sum(u["output_tokens"] for u in usages) / len(usages)); json.dump(L, open(P("cost_ledger.json"), "w"), indent=2)
    with open(P("pilot_results.jsonl"), "w", encoding="utf-8") as f:
        for o in outs: f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"pilot cost ${cost:.3f}; mean output tokens/call {L['measured_out_tokens_per_call']}; total spent ${L['spent_usd']:.2f}")

def cmd_submit(client):
    if os.path.exists(P("batch_id.txt")):
        sys.exit("batch already submitted: " + open(P("batch_id.txt")).read())
    est = cmd_estimate(client)
    if ledger()["spent_usd"] + est > BUDGET_USD * 0.9:
        sys.exit(f"ABORT: estimate ${est:.2f} would exceed 90% of budget")
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    reqs = [Request(custom_id=cid, params=MessageCreateParamsNonStreaming(**p)) for cid, p in requests_for(load_items())]
    b = client.messages.batches.create(requests=reqs)
    open(P("batch_id.txt"), "w").write(b.id)
    print("submitted", b.id, "requests:", len(reqs))

def cmd_status(client):
    b = client.messages.batches.retrieve(open(P("batch_id.txt")).read().strip())
    print(b.id, b.processing_status, b.request_counts)

def cmd_collect(client):
    bid = open(P("batch_id.txt")).read().strip()
    b = client.messages.batches.retrieve(bid)
    if b.processing_status != "ended":
        sys.exit(f"not finished: {b.processing_status} {b.request_counts}")
    if os.path.exists(P("results.jsonl")):
        sys.exit("results.jsonl already exists")
    usages, n_ok, n_fail = [], 0, 0
    with open(P("results.jsonl"), "w", encoding="utf-8") as f:
        for r in client.messages.batches.results(bid):
            rec = {"custom_id": r.custom_id, "type": r.result.type}
            if r.result.type == "succeeded":
                m = r.result.message
                u = usage_dict(m.usage); usages.append(u)
                t = text_of(m); js = parse_json(t)
                rec.update({"stop_reason": m.stop_reason, "usage": u, "parsed": js, "raw_text": t, "model": m.model})
                n_ok += js is not None; n_fail += js is None
            else:
                rec["error"] = str(getattr(r.result, "error", ""))
                n_fail += 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    cost = add_cost("batch", usages, f"batch {bid}")
    print(f"parsed OK {n_ok}, failed {n_fail}; batch cost ${cost:.2f}; total spent ${ledger()['spent_usd']:.2f}")

if __name__ == "__main__":
    client = anthropic.Anthropic(api_key=api_key())
    c = sys.argv[1]
    if c == "estimate": cmd_estimate(client)
    elif c == "pilot": cmd_pilot(client, int(sys.argv[2]) if len(sys.argv) > 2 else 2)
    elif c == "submit": cmd_submit(client)
    elif c == "status": cmd_status(client)
    elif c == "collect": cmd_collect(client)
