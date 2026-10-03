"""Held-out category classification (q2 prompt, effort=medium) for flagged turns of non-audited VPs.
Usage: python3 run_category.py submit | status | collect"""
import json, os, sys
import run_audit as A
ITEMS, BID, OUT = A.P("items_cat.jsonl"), A.P("batch_id_cat.txt"), A.P("results_cat.jsonl")
def load(): return [json.loads(l) for l in open(ITEMS, encoding="utf-8")]
def submit(client):
    if os.path.exists(BID): sys.exit("already submitted: " + open(BID).read())
    items = load()
    reqs = []
    for it in items:
        p = A.build_params(it, "q2", "medium")
        p["messages"][0]["content"][0].pop("cache_control", None)  # single call per item: no caching premium
        reqs.append((f"{it['item_id']}__q2__med", p))
    tin = 0
    for _, p in reqs:
        tin += client.messages.count_tokens(model=p["model"], system=p["system"], messages=p["messages"]).input_tokens
    est = tin / 1e6 * A.PRICE["batch"]["in"] + len(reqs) * 600 / 1e6 * A.PRICE["batch"]["out"]
    spent = A.ledger()["spent_usd"]
    print(f"requests={len(reqs)} input_tokens={tin:,} est_cost=${est:.2f} spent=${spent:.2f} budget=${A.BUDGET_USD}")
    if spent + est > A.BUDGET_USD - 0.3: sys.exit("ABORT: would exceed budget")
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    b = client.messages.batches.create(requests=[Request(custom_id=c, params=MessageCreateParamsNonStreaming(**p)) for c, p in reqs])
    open(BID, "w").write(b.id); print("submitted", b.id)
def status(client):
    b = client.messages.batches.retrieve(open(BID).read().strip()); print(b.processing_status, b.request_counts)
def collect(client):
    bid = open(BID).read().strip(); b = client.messages.batches.retrieve(bid)
    if b.processing_status != "ended": sys.exit(f"not finished: {b.processing_status}")
    if os.path.exists(OUT): sys.exit("results_cat.jsonl exists")
    us, ok = [], 0
    with open(OUT, "w", encoding="utf-8") as f:
        for r in client.messages.batches.results(bid):
            rec = {"custom_id": r.custom_id, "type": r.result.type}
            if r.result.type == "succeeded":
                m = r.result.message; u = A.usage_dict(m.usage); us.append(u); t = A.text_of(m); js = A.parse_json(t)
                rec.update(usage=u, parsed=js, raw_text=t, model=m.model); ok += js is not None
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    c = A.add_cost("batch", us, f"category batch {bid}")
    print(f"parsed {ok}/{len(us)}; cost ${c:.2f}; total spent ${A.ledger()['spent_usd']:.2f}")
if __name__ == "__main__":
    cl = A.anthropic.Anthropic(api_key=A.api_key())
    {"submit": submit, "status": status, "collect": collect}[sys.argv[1]](cl)
