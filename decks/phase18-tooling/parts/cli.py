from tests.helpers import belle_block_db, write_labels, block_codes, FakeRpc
from ethsc.cli import main
from ethsc.store import Store
def go(argv, rpc=None, sleep=None):
    o, e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        code = main(argv, rpc=rpc, sleep=sleep)
    return code, o.getvalue(), e.getvalue()
def deploy_db():
    p = os.path.join(tempfile.mkdtemp(prefix="p18-probe-"), "e.sqlite"); s = Store(p)
    cid = s.put_code(bytes.fromhex(block_codes()[B53C][2:])); s.put_address(SEED1, cid, 1); s.add_seed(SEED1, "deployed in 26077729"); s.close()
    return p
L = lambda addr, score, origin: "ALERT\t%s\t%s\tdeployed in 26077729\t%s\t%s\n" % (addr, SEED1, score, origin)
THREE = L(B53C, "1.0000", "created") + L(C02A, "0.8182", "seen") + L(FF74, "1.0000", "seen")
FIVE = L(LINK, "0.7500", "seen") + L(SHIB, "0.7500", "seen") + THREE
def cl57():
    db = deploy_db()
    chk("Command Line 57: backfill without --min", go(["--db", db, "backfill", "--from", "26077729", "--to", "26077729"], rpc=FakeRpc()), (0, FIVE, ""))
    chk("Command Line 57: recheck default", go(["--db", db, "recheck"]), (0, FIVE, ""))
    db = deploy_db()
    chk("Command Line 36 at --min 0.8", go(["--db", db, "backfill", "--from", "26077729", "--to", "26077729", "--min", "0.8"], rpc=FakeRpc()), (0, THREE, ""))
def sleeper(_):
    raise KeyboardInterrupt
def cl58():
    for argv in (["backfill", "--from", "26077729", "--to", "26077729", "--min", "1.5"], ["listen", "--min", "-0.1"],
                 ["backfill", "--from", "26077729", "--to", "26077729", "--min", "x"]):
        fake = FakeRpc(fail=AssertionError("no rpc"))
        code, out, err = go(["--db", os.path.join(tempfile.mkdtemp(prefix="p18-probe-"), "e.sqlite")] + argv, rpc=fake, sleep=sleeper)
        chk("Command Line 58 %r" % argv, (code, out, len(err.rstrip("\n").split("\n")), fake.calls), (2, "", 1, []))
def belle_db():
    p = belle_block_db(); s = Store(p); s.add_seed(BELLE, "BELLE honeypot"); s.close(); return p
A = lambda addr, score: "ALERT\t%s\t%s\tBELLE honeypot\t%s\tunknown\n" % (addr, BELLE, score)
FOUR = "".join(A(a, "0.8667") for a in COPIES)
def cl59():
    db = belle_db()
    chk("Command Line 59: seed audit loose", go(["--db", db, "seed", "audit"]), (0, BELLE + "\tBELLE honeypot\t0\tloose\n", ""))
    chk("Command Line 59: seed strict on", go(["--db", db, "seed", "strict", BELLE.upper().replace("0X", "0x"), "on"]), (0, "", ""))
    chk("Command Line 59: seed audit strict", go(["--db", db, "seed", "audit"]), (0, BELLE + "\tBELLE honeypot\t0\tstrict\n", ""))
    chk("Command Line 59: seed list unchanged", go(["--db", db, "seed", "list"]), (0, BELLE + "\tBELLE honeypot\n", ""))
    chk("Command Line 59: recheck --min 0.7 strict", go(["--db", db, "recheck", "--min", "0.7"]), (0, FOUR, ""))
    chk("Command Line 59: seed strict off", go(["--db", db, "seed", "strict", BELLE, "off"]), (0, "", ""))
    chk("Command Line 59: recheck --min 0.7 loose", go(["--db", db, "recheck", "--min", "0.7"]), (0, FOUR + A(SHIB, "0.7333"), ""))
def cl60():
    db = belle_db()
    chk("Command Line 60: not a seed", go(["--db", db, "seed", "strict", COPIES[0], "on"]), (2, "", "not a seed: %s\n" % COPIES[0]))
    for argv in (["seed", "strict", "0x12", "on"], ["seed", "strict", BELLE, "maybe"]):
        code, out, err = go(["--db", db] + argv)
        chk("Command Line 60 %r" % argv, (code, out, len(err.rstrip("\n").split("\n"))), (2, "", 1))
    s = Store(db); chk("Command Line 60: strict_seeds", s.strict_seeds(), []); s.close()
def cl61():
    db = belle_db(); lp = write_labels(LAB)
    s = Store(db); before = (len(s.seeds()), len(s.fingerprints()), len(s.origins()), s.strict_seeds()); s.close()
    fake = FakeRpc(fail=AssertionError("no rpc"))
    chk("Command Line 61: --grid", go(["--db", db, "calibrate", "--labels", lp, "--grid", "0.7,0.75,0.8,0.9"], rpc=fake),
        (0, "0.7000\t1.0000\t1\t6\t5\t131\n0.7500\t1.0000\t0\t6\t2\t131\n0.8000\t1.0000\t0\t4\t0\t131\n0.9000\t0.5000\t0\t3\t0\t131\n",
         "missing: %s\n" % X9999))
    code, out, err = go(["--db", db, "calibrate", "--labels", lp], rpc=fake)
    lines = out.splitlines()
    chk("Command Line 61: default grid", (code, len(lines), lines[:1], lines[-1:], err),
        (0, 7, ["0.5000\t1.0000\t1\t19\t18\t131"], ["1.0000\t0.5000\t0\t3\t0\t131"], "missing: %s\n" % X9999))
    chk("Command Line 61: no rpc call", fake.calls, [])
    s = Store(db); after = (len(s.seeds()), len(s.fingerprints()), len(s.origins()), s.strict_seeds()); s.close()
    chk("Command Line 61: nothing written", after, before)
def cl62():
    db = belle_db(); good = write_labels(LAB)
    d = tempfile.mkdtemp(prefix="p18-probe-"); arr = os.path.join(d, "a.json")
    with open(arr, "w") as h:
        h.write("[]")
    for argv in (["--labels", os.path.join(d, "nope.json")], ["--labels", arr], ["--labels", good, "--grid", "0.5,abc"], ["--labels", good, "--grid", "1.5"]):
        fake = FakeRpc(fail=AssertionError("no rpc"))
        code, out, err = go(["--db", db, "calibrate"] + argv, rpc=fake)
        chk("Command Line 62 %r" % argv[-1], (code, out, len(err.rstrip("\n").split("\n")), fake.calls), (2, "", 1, []))
def similar_kept():
    db = belle_db()
    code, out, err = go(["--db", db, "similar", BELLE])
    chk("unchanged: similar stays at 0.8 (the copies, not SHIB)", (code, [l.split("\t")[0] for l in out.splitlines()]), (0, COPIES))
def seed_add_loose():
    p = belle_block_db()
    code, out, err = go(["--db", p, "seed", "add", BELLE, "--label", "BELLE honeypot"])
    s = Store(p); st = s.strict_seeds(); s.close()
    chk("seed add sets no strict flag", (code, out, st), (0, FOUR, []))
for n, f in [("Command Line 57", cl57), ("Command Line 58", cl58), ("Command Line 59", cl59), ("Command Line 60", cl60),
             ("Command Line 61", cl61), ("Command Line 62", cl62), ("similar", similar_kept), ("seed add", seed_add_loose)]:
    run(n, f)
finish()
