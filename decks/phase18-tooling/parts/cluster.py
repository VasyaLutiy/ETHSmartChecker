from tests.helpers import belle_block_db, load_hex, block_codes
from ethsc import cluster as C
from ethsc.store import Store
from ethsc.fingerprint import fingerprint, score_fingerprints
def S():
    return Store(belle_block_db())
def ih1():
    s = S()
    chk("Interface Hits 1: BELLE at 0.5, 0.7, default, 0.8",
        [C.interface_hits(s, B_ID, min_score=0.5), C.interface_hits(s, B_ID, min_score=0.7), C.interface_hits(s, B_ID), C.interface_hits(s, B_ID, min_score=0.8)], [8, 1, 0, 0])
    chk("Interface Hits 1: deploy code at 0.5, 0.7, default, 0.8",
        [C.interface_hits(s, D_ID, min_score=0.5), C.interface_hits(s, D_ID, min_score=0.7), C.interface_hits(s, D_ID), C.interface_hits(s, D_ID, min_score=0.8)], [23, 4, 4, 2])
    s.close()
def ih2():
    s = S()
    chk("Interface Hits 2: unknown code_id", C.interface_hits(s, "00" * 32), 0)
    chk("Interface Hits 2: code_min=1.0", C.interface_hits(s, B_ID, code_min=1.0), 4)
    fps = {f["code_id"]: f for f in s.fingerprints()}
    seen = []
    real = s.code_by_id
    def rec(cid):
        seen.append(cid); return real(cid)
    s.code_by_id = rec
    C.interface_hits(s, D_ID)
    extra = sorted(set(c for c in seen if c != D_ID and score_fingerprints(fps[D_ID], fps[c]) < 0.75))
    chk("Interface Hits: code_by_id only for code_id and the codes reaching min_score", extra, [])
    s.close()
def mw5():
    s = S(); s.add_seed(BELLE, "BELLE honeypot")
    shib = bytes.fromhex(block_codes()[SHIB][2:])
    chk("Match Watchlist 5: SHIB at the default", C.match_watchlist(s, shib), [])
    chk("Match Watchlist 5: SHIB at 0.7, BELLE loose", C.match_watchlist(s, shib, min_score=0.7),
        [{"seed_address": BELLE, "label": "BELLE honeypot", "score": 11 / 15}])
    s.set_seed_strict(BELLE, True)
    chk("Match Watchlist 5: SHIB at 0.7, BELLE strict", C.match_watchlist(s, shib, min_score=0.7), [])
    chk("Match Watchlist 5: the copy, BELLE strict", C.match_watchlist(s, load_hex(COPY_HEX[0])),
        [{"seed_address": BELLE, "label": "BELLE honeypot", "score": 13 / 15}])
    s.close()
def rw12():
    s = S(); s.add_seed(BELLE, "BELLE honeypot")
    v = lambda r: [(a["address"], a["score"]) for a in r]
    four = [(a, 13 / 15) for a in COPIES]
    chk("Recheck Watchlist 12: default, loose", v(C.recheck_watchlist(s)), four)
    chk("Recheck Watchlist 12: 0.7, loose", v(C.recheck_watchlist(s, min_score=0.7)), four + [(SHIB, 11 / 15)])
    s.set_seed_strict(BELLE, True)
    chk("Recheck Watchlist 12: 0.7, strict", v(C.recheck_watchlist(s, min_score=0.7)), four)
    s.close()
def defaults():
    d = lambda f: inspect.signature(f).parameters["min_score"].default
    chk("defaults: match_watchlist, recheck_watchlist, find_similar", (d(C.match_watchlist), d(C.recheck_watchlist), d(C.find_similar)), (0.75, 0.75, 0.8))
def loose_reads():
    s = S(); s.add_seed(BELLE, "BELLE honeypot")
    def boom(cid):
        raise AssertionError("code_by_id called with no strict seed")
    s.code_by_id = boom
    chk("no strict seed: recheck reads no code", len(C.recheck_watchlist(s, min_score=0.7)), 5)
    chk("no strict seed: match reads no code", len(C.match_watchlist(s, load_hex(COPY_HEX[0]))), 1)
    s.close()
def strict_none():
    s = S(); s.add_seed(BELLE, "BELLE honeypot"); s.set_seed_strict(BELLE, True)
    s.code_by_id = lambda cid: None
    chk("strict seed without code: match", C.match_watchlist(s, load_hex(COPY_HEX[0])), [])
    chk("strict seed without code: recheck", C.recheck_watchlist(s), [])
    s.close()
def once():
    s = S(); s.add_seed(BELLE, "BELLE honeypot"); s.set_seed_strict(BELLE, True)
    n = [0]; real = s.strict_seeds
    def cnt():
        n[0] += 1; return real()
    s.strict_seeds = cnt
    C.match_watchlist(s, load_hex(COPY_HEX[0])); chk("strict_seeds read once per match_watchlist call", n[0], 1)
    n[0] = 0; C.recheck_watchlist(s); chk("strict_seeds read once per recheck_watchlist call", n[0], 1)
    s.close()
for n, f in [("Interface Hits 1", ih1), ("Interface Hits 2", ih2), ("Match Watchlist 5", mw5), ("Recheck Watchlist 12", rw12),
             ("defaults", defaults), ("no strict seed", loose_reads), ("strict seed without code", strict_none), ("strict_seeds once", once)]:
    run(n, f)
finish()
