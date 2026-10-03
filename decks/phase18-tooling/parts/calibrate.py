from tests.helpers import belle_block_db, write_labels
try:
    from ethsc import calibrate as K
except Exception as e:
    bad.append("import ethsc.calibrate: %r" % (e,))
    finish()
from ethsc.store import Store
def rows(r):
    return [(x["threshold"], x["recall"], x["negatives"], x["benign"], x["interface_only"]) for x in r["rows"]]
def counts(p):
    c = sqlite3.connect(p); n = tuple(c.execute("SELECT COUNT(*) FROM " + t).fetchone()[0] for t in ("seeds", "codes", "addresses")); c.close(); return n
def ev1():
    p = belle_block_db(); s = Store(p); before = counts(p)
    r = K.evaluate(s, LAB, (0.7, 0.75, 0.8, 0.9))
    chk("Evaluate Calibration 1: keys", sorted(r.keys()), ["benign_total", "missing", "rows"])
    chk("Evaluate Calibration 1: row keys", sorted(r["rows"][0].keys()), ["benign", "interface_only", "negatives", "recall", "threshold"])
    chk("Evaluate Calibration 1: rows", rows(r), [(0.7, 1.0, 1, 6, 5), (0.75, 1.0, 0, 6, 2), (0.8, 1.0, 0, 4, 0), (0.9, 0.5, 0, 3, 0)])
    chk("Evaluate Calibration 1: missing", r["missing"], [X9999])
    chk("Evaluate Calibration 1: benign_total", r["benign_total"], 131)
    s.close()
    chk("Evaluate Calibration: no row written", counts(p), before)
def ev2():
    s = Store(belle_block_db())
    lab = dict(LAB, strict=[])
    chk("Evaluate Calibration 2: strict []", rows(K.evaluate(s, lab, (0.7,))), [(0.7, 1.0, 2, 6, 5)])
    lab = dict(LAB, strict=[BELLE.upper().replace("0X", "0x")])
    chk("Evaluate Calibration 2: strict upper case", rows(K.evaluate(s, lab, (0.7,))), [(0.7, 1.0, 1, 6, 5)])
    s.close()
def ev3():
    chk("Evaluate Calibration 3: DEFAULT_GRID", tuple(K.DEFAULT_GRID), (0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0))
    s = Store(belle_block_db())
    chk("Evaluate Calibration 3: default thresholds", rows(K.evaluate(s, LAB)),
        [(0.5, 1.0, 1, 19, 18), (0.6, 1.0, 1, 9, 8), (0.7, 1.0, 1, 6, 5), (0.75, 1.0, 0, 6, 2), (0.8, 1.0, 0, 4, 0), (0.9, 0.5, 0, 3, 0), (1.0, 0.5, 0, 3, 0)])
    s.close()
def ev4():
    s = Store(belle_block_db())
    r = K.evaluate(s, {}, (0.5, 1.0))
    chk("Evaluate Calibration 4: empty labels", (rows(r), r["missing"], r["benign_total"]), ([(0.5, 0.0, 0, 0, 0), (1.0, 0.0, 0, 0, 0)], [], 135))
    r = K.evaluate(s, {"positives": [[BELLE, X9999]]}, (0.75,))
    chk("Evaluate Calibration 4: missing pair", (rows(r), r["missing"], r["benign_total"]), ([(0.75, 0.0, 0, 4, 0)], [X9999], 134))
    s.close()
def ll1():
    p = write_labels({"positives": [["0xAB000000000000000000000000000000000000CD", "0x0000000000000000000000000000000000000001"]], "note": "x"})
    chk("Load Labels 1", K.load_labels(p), {"positives": [["0xab000000000000000000000000000000000000cd", "0x0000000000000000000000000000000000000001"]], "negatives": [], "strict": []})
def ll2():
    d = tempfile.mkdtemp(prefix="p18-probe-")
    def f(text):
        p = os.path.join(d, "l%d.json" % len(os.listdir(d)))
        with open(p, "w") as h:
            h.write(text)
        return p
    cases = [("missing path", os.path.join(d, "nope.json")), ("[]", f("[]")), ("{", f("{")),
             ("bad address", f(json.dumps({"negatives": [["0x12", "0x0000000000000000000000000000000000000001"]]}))),
             ("strict not a list", f(json.dumps({"strict": "0x0000000000000000000000000000000000000001"}))),
             ("one-element pair", f(json.dumps({"positives": [["0x0000000000000000000000000000000000000001"]]})))]
    for name, p in cases:
        try:
            K.load_labels(p)
            bad.append("Load Labels 2 (%s): no ValueError" % name)
        except ValueError as e:
            chk("Load Labels 2 (%s): one-line message" % name, "\n" in str(e), False)
def ll3():
    chk("Load Labels 3: parse_grid good", (K.parse_grid("0.7,0.75, 0.8"), K.parse_grid("1,0")), ((0.7, 0.75, 0.8), (1.0, 0.0)))
    for t in ("", "0.5,", "0.5,abc", "1.5", "-0.1"):
        try:
            K.parse_grid(t)
            bad.append("Load Labels 3: parse_grid(%r) did not raise ValueError" % t)
        except ValueError:
            pass
def ll4():
    l = K.load_labels("tests/fixtures/calibration_labels.json")
    chk("Load Labels 4: corpus", (len(l["positives"]), len(l["negatives"]), l["strict"]),
        (95, 8, ["0xa0ff0e694275023f4986dc3ca12a6eb5d6056c62", "0xc0a6b8c534fad86df8fa1abb17084a70f86eddc1"]))
for n, f in [("Evaluate Calibration 1", ev1), ("Evaluate Calibration 2", ev2), ("Evaluate Calibration 3", ev3), ("Evaluate Calibration 4", ev4),
             ("Load Labels 1", ll1), ("Load Labels 2", ll2), ("Load Labels 3", ll3), ("Load Labels 4", ll4)]:
    run(n, f)
finish()
