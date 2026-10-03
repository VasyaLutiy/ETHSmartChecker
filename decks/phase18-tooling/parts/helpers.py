from tests import helpers as HP
from tests.helpers import load_hex
from ethsc.store import Store
def bb():
    p = HP.belle_block_db()
    chk("belle_block_db returns a str", isinstance(p, str), True)
    chk("belle_block_db file exists", os.path.isfile(p), True)
    s = Store(p)
    chk("belle_block_db codes", len(s.fingerprints()), 135)
    chk("belle_block_db BELLE code", s.code_of(BELLE), load_hex("code_belle.hex"))
    chk("belle_block_db copies", [s.code_of(a) == load_hex(h) for a, h in zip(COPIES, COPY_HEX)], [True] * 4)
    chk("belle_block_db no seed", s.seeds(), [])
    chk("belle_block_db no progress", s.get_progress(), None)
    o = s.origins()
    chk("belle_block_db 211 addresses", len(o), 211)
    chk("belle_block_db origins unknown", sorted(set(o.values())), ["unknown"])
    s.close()
    c = sqlite3.connect(p); blocks = dict(c.execute("SELECT address, block FROM addresses WHERE address IN (?,?,?,?,?)", [BELLE] + COPIES).fetchall()); c.close()
    chk("belle_block_db BELLE and copies at block 1", sorted(set(blocks.values())), [1])
    p2 = HP.belle_block_db()
    chk("belle_block_db fresh directory per call", os.path.dirname(p2) != os.path.dirname(p), True)
def wl():
    obj = {"positives": [[BELLE, COPIES[0]]], "x": 1}
    p = HP.write_labels(obj)
    chk("write_labels round trip", json.load(open(p)), obj)
    chk("write_labels file name", os.path.basename(p), "labels.json")
    chk("write_labels fresh directory per call", os.path.dirname(HP.write_labels({})) != os.path.dirname(p), True)
for n, f in [("belle_block_db", bb), ("write_labels", wl)]:
    run(n, f)
finish()
