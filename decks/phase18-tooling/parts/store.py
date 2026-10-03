from tests.helpers import load_hex, legacy_db
from ethsc.store import Store, ReadOnlyStoreError
def newpath():
    return os.path.join(tempfile.mkdtemp(prefix="p18-probe-"), "e.sqlite")
def mk():
    p = newpath(); s = Store(p)
    cid = s.put_code(load_hex("code_belle.hex")); s.put_address(BELLE, cid, 26077729); s.add_seed(BELLE, "BELLE honeypot")
    return s, p
def mw6():
    s, p = mk()
    chk("Manage Watchlist 6: strict_seeds() of a fresh seed", s.strict_seeds(), [])
    chk("Manage Watchlist 6: set_seed_strict(upper case, True)", s.set_seed_strict(BELLE.upper().replace("0X", "0x"), True), True)
    chk("Manage Watchlist 6: strict_seeds() after on", s.strict_seeds(), [BELLE])
    seeds = s.seeds()
    chk("Manage Watchlist 6: seeds() entries", len(seeds), 1)
    chk("Manage Watchlist 6: seeds() keys", sorted(seeds[0].keys()), ["address", "code_id", "label"])
    s.add_seed(BELLE, "BELLE again")
    chk("Manage Watchlist 6: re-add keeps the flag", s.strict_seeds(), [BELLE])
    chk("Manage Watchlist 6: re-add relabels", [x["label"] for x in s.seeds()], ["BELLE again"])
    chk("Manage Watchlist 6: set_seed_strict(False)", s.set_seed_strict(BELLE, False), True)
    chk("Manage Watchlist 6: strict_seeds() after off", s.strict_seeds(), [])
    s.close()
def mw7():
    s, p = mk()
    s.set_seed_strict(BELLE, True)
    s.put_address(COPIES[0], s.put_code(load_hex(COPY_HEX[0])), 26077729)
    chk("Manage Watchlist 7: stored non-seed", s.set_seed_strict(COPIES[0], True), False)
    chk("Manage Watchlist 7: unknown address", s.set_seed_strict(SEED1, True), False)
    c = sqlite3.connect(p); n = c.execute("SELECT COUNT(*) FROM seeds").fetchone()[0]; c.close()
    chk("Manage Watchlist 7: seeds row count", n, 1)
    chk("Manage Watchlist 7: strict_seeds unchanged", s.strict_seeds(), [BELLE])
    s.remove_seed(BELLE); s.add_seed(BELLE, "BELLE")
    chk("Manage Watchlist 7: remove then add starts loose", s.strict_seeds(), [])
    s.close()
def mw8():
    p = legacy_db(14)
    r = Store(p, readonly=True)
    chk("Manage Watchlist 8: read-only legacy strict_seeds", r.strict_seeds(), [])
    try:
        r.set_seed_strict(BELLE, True)
        bad.append("Manage Watchlist 8: read-only set_seed_strict did not raise")
    except ReadOnlyStoreError:
        pass
    r.close()
    w = Store(p)
    chk("Manage Watchlist 8: writable legacy strict_seeds", w.strict_seeds(), [])
    w.close()
    c = sqlite3.connect(p); cols = [row[1] for row in c.execute("PRAGMA table_info(seeds)")]; c.close()
    chk("Manage Watchlist 8: seeds columns end with strict", cols[-1:], ["strict"])
    chk("Manage Watchlist 8: old seeds columns kept", cols[:3], ["address", "code_id", "label"])
def reopen():
    s, p = mk(); s.set_seed_strict(BELLE, True); s.close()
    s = Store(p); chk("persist: the flag survives a reopen", s.strict_seeds(), [BELLE]); s.close()
    r = Store(p, readonly=True); chk("persist: a read-only store reads the flag", r.strict_seeds(), [BELLE]); r.close()
for n, f in [("Manage Watchlist 6", mw6), ("Manage Watchlist 7", mw7), ("Manage Watchlist 8", mw8), ("persist", reopen)]:
    run(n, f)
finish()
