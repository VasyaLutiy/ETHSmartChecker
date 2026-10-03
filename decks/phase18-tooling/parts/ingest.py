from tests.helpers import temp_store, block_codes, FakeRpc
import ethsc.ingest as I
from ethsc.ingest import follow_chain
def mk():
    s = temp_store(); codes = block_codes()
    cid = s.put_code(bytes.fromhex(codes[B53C][2:])); s.put_address(SEED1, cid, 1)
    s.add_seed(SEED1, "deployed in 26077729"); s.set_progress(26077728)
    return s
def view(summary):
    return [(a["address"], round(a["score"], 4), a["origin"]) for a in summary["alerts"]]
def fc18():
    s = mk(); out = follow_chain(FakeRpc(), s, prices={}, watch=0.8)
    chk("Follow Chain 18: watch=0.8", view(out), [(B53C, 1.0, "created"), (C02A, 0.8182, "seen"), (FF74, 1.0, "seen")])
    s = mk(); out = follow_chain(FakeRpc(), s, prices={}, watch=0.75)
    chk("Follow Chain 18: watch=0.75 (the phase-18 default, given explicitly)", view(out),
        [(LINK, 0.75, "seen"), (SHIB, 0.75, "seen"), (B53C, 1.0, "created"), (C02A, 0.8182, "seen"), (FF74, 1.0, "seen")])
def spy():
    real = I.ingest_block
    sig = inspect.signature(real)
    seen = []
    def wrap(*a, **k):
        seen.append(sig.bind(*a, **k).arguments.get("watch", None))
        return real(*a, **k)
    with mock.patch.object(I, "ingest_block", wrap):
        follow_chain(FakeRpc(), mk(), prices={}, watch=0.42)
        follow_chain(FakeRpc(), mk(), prices={})
    chk("Follow Chain: watch reaches ingest_block, None by default", seen, [0.42, None])
def sig():
    ps = list(inspect.signature(follow_chain).parameters.values())
    chk("Follow Chain: watch is the last parameter, default None", (ps[-1].name, ps[-1].default), ("watch", None))
    chk("Follow Chain: the old parameters keep their order", [p.name for p in ps[:-1]],
        ["rpc", "store", "start", "stop", "max_calls_per_block", "daily_budget", "day", "prices", "on_alerts", "workers", "code_tag", "on_upgrades"])
for n, f in [("Follow Chain 18", fc18), ("spy", spy), ("signature", sig)]:
    run(n, f)
finish()
