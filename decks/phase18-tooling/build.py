"""Phase 18 deck builder: one acceptance builder for every card (outside the tree)."""
import json, os, sys
ROOT = "/home/john/Documents/Work2026/ETHSmartChecker"
PARTS = "/tmp/p18/parts"
SPEC = "docs/TASK_PHASE18.md"
DESELECT = [
    "tests/test_origin_examples_p13.py::CommandLineOriginExamples::test_command_line_example_36_six_field_alert_created_and_seen",
    "tests/test_origin_examples_p13.py::CommandLineOriginExamples::test_command_line_example_37_alert_on_filters_stdout_only",
    "tests/test_origin_examples_p13.py::CommandLineOriginExamples::test_command_line_example_39_recheck_origin_filters",
]
def part(name):
    return open(os.path.join(PARTS, name + ".py")).read()

HEAD = r'''D=/tmp/morph/{card}-p18; mkdir -p $D; S=$(date +%s)-$$; L=$D/acc-$S.log
{snap}
export INFURA_API_KEY=TESTKEY-ENV-0000
pyt() {{ venv/bin/python -c "import socket, sys, pytest
_o = socket.socket.connect
def _b(*a, **k):
    raise OSError('network blocked')
def _c(self, addr, *a, **k):
    if isinstance(addr, tuple) and addr and addr[0] == '127.0.0.1':
        return _o(self, addr, *a, **k)
    raise OSError('network blocked')
socket.getaddrinfo = _b; socket.create_connection = _b; socket.socket.connect = _c
sys.exit(pytest.main(sys.argv[1:]))" "$@"; }}
(
 set -e
 venv/bin/python -c "import ast,sys; [ast.parse(open(f).read(), f, feature_version=(3,9)) for f in sys.argv[1:]]" {py_targets}
'''

GUARD = r''' venv/bin/python - {role} {tf} {lo} {hi} {targets} <<'PY'
import ast, glob, subprocess, sys
role, tf, lo, hi = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
targets = set(sys.argv[5:])
STD = set(sys.stdlib_module_names)
NET = ("urllib", "http", "socket")
def tree(p):
    return ast.parse(open(p, encoding="utf-8").read(), p)
def imports(p):
    out = []
    for n in ast.walk(tree(p)):
        if isinstance(n, ast.Import):
            out += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.level == 0:
            out.append(n.module or "")
    return [m for m in out if m]
bad = []
for p in sorted(glob.glob("ethsc/*.py")):
    for full in imports(p):
        t = full.split(".")[0]
        if t in NET:
            if p == "ethsc/rpc.py" or (p == "ethsc/dashboard.py" and full == "http.server"):
                continue
            bad.append("No Network In Core: %s imports %s" % (p, full))
        elif t not in STD and t != "ethsc" and not (p == "ethsc/charts.py" and t == "matplotlib"):
            bad.append("Stdlib Only: %s imports %s" % (p, full))
for p in ("ethsc/cli.py", "ethsc/cluster.py", "ethsc/dashboard.py", "ethsc/calibrate.py"):
    try:
        t = tree(p)
    except FileNotFoundError:
        continue
    for n in ast.walk(t):
        if isinstance(n, ast.Attribute) and n.attr.startswith("_") and not n.attr.startswith("__") and not (isinstance(n.value, ast.Name) and n.value.id == "self"):
            bad.append("%s:%d touches a private attribute %s; read the store through its public methods" % (p, n.lineno, n.attr))
for p in ("ethsc/cluster.py", "ethsc/calibrate.py"):
    try:
        mods = imports(p)
    except FileNotFoundError:
        continue
    if "sqlite3" in [m.split(".")[0] for m in mods]:
        bad.append("%s imports sqlite3; read the store through its public methods" % p)
try:
    if "ethsc.cluster" in imports("ethsc/calibrate.py"):
        bad.append("ethsc/calibrate.py imports ethsc.cluster; it imports from ethsc.fingerprint only (Evaluate Calibration)")
except FileNotFoundError:
    pass
changed = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True).stdout.splitlines()
paths = set(l[3:].strip() for l in changed if l[3:].strip() != "venv")
paths = set(p for p in paths if not p.startswith("venv") and not p.startswith(".morph/"))
extra = sorted(paths - targets)
if extra:
    bad.append("changed or added files outside this card's targets: %s" % ", ".join(extra))
head = subprocess.run(["git", "show", "HEAD:tests/helpers.py"], capture_output=True, text=True).stdout
names = lambda src: set(n.name for n in ast.parse(src).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)))
lost = sorted(names(head) - names(open("tests/helpers.py", encoding="utf-8").read()))
if lost:
    bad.append("tests/helpers.py lost %s" % ", ".join(lost))
for p in ("tests/helpers.py",) + ((tf,) if tf != "-" else ()):
    for full in imports(p):
        if full.split(".")[0] in NET:
            bad.append("%s imports %s" % (p, full))
if tf != "-":
    t = tree(tf)
    tests = [n.name for n in ast.walk(t) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]
    if not (lo <= len(tests) <= hi):
        bad.append("%s has %d test_* functions; want %d..%d (%s)" % (tf, len(tests), lo, hi, role))
    for n in ast.walk(t):
        if isinstance(n, ast.ClassDef) and n.name.startswith("Fake"):
            bad.append("%s defines its own stub %s; import stubs from tests/helpers.py" % (tf, n.name))
        if isinstance(n, ast.Attribute) and n.attr == "maxDiff" and not role.startswith("judge"):
            bad.append("%s touches maxDiff; smoke tests compare short values" % tf)
    if role.startswith("judge"):
        try:
            subprocess.check_call(["git", "cat-file", "-e", "HEAD:" + tf], stderr=subprocess.DEVNULL)
            bad.append("%s exists at HEAD; the judge writes a NEW file" % tf)
        except subprocess.CalledProcessError:
            pass
print("\n".join(bad) if bad else "guard OK")
sys.exit(1 if bad else 0)
PY
'''

def acceptance(card, targets, role, tf, lo, hi, probe, module_tests, deselect):
    snap = "\n".join("cp %s $D/%d-$S.py 2>/dev/null" % (t, i) for i, t in enumerate(targets))
    py_targets = " ".join(targets)
    s = HEAD.format(card=card, snap=snap, py_targets=py_targets)
    s += GUARD.format(role=role, tf=tf, lo=lo, hi=hi, targets=" ".join(targets))
    if probe:
        s += " venv/bin/python - <<'PY'\n" + part("pre") + part(probe) + "PY\n"
    if tf != "-":
        s += " pyt %s -q --tb=short -p no:cacheprovider\n" % tf
    if module_tests:
        s += " pyt %s -q --tb=line -p no:cacheprovider\n" % " ".join(module_tests)
    des = "".join(" --deselect %s" % d for d in DESELECT) if deselect else ""
    # The full suite (~340 s serial) in 9 parallel shards by file: Morph's acceptance timeout is 300 s.
    s += ' P=$D/par-$S; mkdir -p $P; i=0\n'
    s += ' for f in $(ls tests/test_*.py); do echo $f >> $P/s$((i % 9)); i=$((i+1)); done\n'
    s += ' for s in $P/s?; do ( pyt $(cat $s) -q --tb=line -p no:cacheprovider%s > $s.log 2>&1 && echo 0 > $s.rc || echo 1 > $s.rc ) & done; wait\n' % des
    s += ' grep -hE "passed|failed|^FAILED|^ERROR" $P/s?.log || true\n'
    s += ' for r in $P/s?.rc; do [ "$(cat $r)" = 0 ] || { echo "full suite: shard ${r%.rc} failed"; tail -25 ${r%.rc}.log; exit 1; }; done\n'
    grep = " ".join("-e %s" % t for t in ["venv"] + targets)
    s += ' X=$(git ls-files --others --exclude-standard | grep -vxF %s || true); [ -z "$X" ] || { echo "tests left files: $X"; exit 1; }\n' % grep
    s += ") > $L 2>&1; rc=$?; cat $L; exit $rc"
    return s

HELPERS_NAMES = "temp_store, block_store, block_codes, block_receipts, load_hex, FakeRpc, InterruptAfter, legacy_db"
COMMON = ("Python 3.9 syntax, standard library only. Your own test file is SMOKE ONLY: at most five test_* functions "
          "(an import, one happy path per new function, one tolerant case), comparing scalars and short values -- never "
          "whole fixture-sized lists, no maxDiff; the orchestrator's probe judges completeness. Import stubs and builders "
          "from tests/helpers.py; do not define Fake* classes. Every file a test writes goes into a tempfile.mkdtemp() "
          "directory. Do not change any file outside your targets.")

CARDS = {}
def code(card, comp, targets, ctx, deps, instr, probe, module_tests, deselect=True, variants=2, max_tokens=48000):
    CARDS[card] = dict(intent="patch" if os.path.exists(os.path.join(ROOT, targets[0])) else "generate",
                       targets=targets, context_slice=ctx, depends_on=deps, variants=variants, max_tokens=max_tokens,
                       reasoning_max_tokens=2500,
                       acceptance=acceptance(card, targets, "code", targets[-1] if targets[-1].startswith("tests/test_") else "-",
                                             1, 5, probe, module_tests, deselect),
                       instruction=instr + " " + COMMON)
def judge(card, target, ctx, deps, n, instr, deselect=True):
    CARDS[card] = dict(intent="generate", targets=[target], context_slice=ctx, depends_on=deps, variants=1, max_tokens=56000,
                       reasoning_max_tokens=2500,
                       acceptance=acceptance(card, [target], "judge", target, n, 3 * n, None, None, deselect),
                       instruction=("Read %s FIRST (sections 2 and 3.2), then in contour.yaml: %s. You are the judge: you write ONE NEW "
                                    "test file %s with one unittest test per example listed (%d examples, so %d..%d test_* functions), "
                                    "each named after its example and checking the example's 'then' completely, with the exact values "
                                    "written in the Contour. You do not change any other file: the code under test is finished, read it "
                                    "only to learn how to call it. Import stubs and builders from tests/helpers.py (%s, belle_block_db, "
                                    "write_labels) -- do not define Fake* classes. Every file a test writes goes into a "
                                    "tempfile.mkdtemp() directory. No network. Python 3.9 syntax, standard library only.")
                                   % (SPEC, instr, target, n, n, 3 * n, HELPERS_NAMES))

C = "contour.yaml"
code("fingerprint", "fingerprint", ["ethsc/fingerprint.py", "tests/test_fingerprint_p18.py"],
     [SPEC, C, "ethsc/evm.py", "tests/fixtures/README.md"], [],
     "Read %s FIRST (sections 1, 2 and 4), then in contour.yaml group fingerprint the Function Code Similarity (whole: description, behavior, every example). You own ethsc/fingerprint.py and tests/test_fingerprint_p18.py. Add to ethsc/fingerprint.py, leaving every existing function unchanged: the module constants ALERT_MIN = 0.75 and CODE_MIN = 0.6; opcode_shingles(code) -> frozenset of 5-tuples of consecutive opcodes (the op ints of disassemble over the body of strip_metadata(code), arguments dropped; empty frozenset under 5 opcodes; never raises); code_similarity(code_a, code_b) -> 0.0 when either set is empty, else float(len(a & b)) / float(len(a | b)), unrounded. similarity and score_fingerprints do not call it. The smoke file imports load_hex from tests.helpers (load_hex(name) returns the bytes of tests/fixtures/<name>; do not read tests/helpers.py, another card rewrites it in your generation)." % SPEC,
     "fingerprint", ["tests/test_fingerprint.py", "tests/test_fingerprint_examples.py", "tests/test_fingerprint_examples_p11.py"])
code("store", "store", ["ethsc/store.py", "tests/test_store_p18.py"], [SPEC, C], [],
     "Read %s FIRST (sections 1, 2 and 4), then in contour.yaml group store the Function Manage Watchlist (the paragraph 'Strict seeds (phase 18)' and examples 6-8) and Open Read Only. You own ethsc/store.py and tests/test_store_p18.py. In ethsc/store.py: (1) a writable open adds the column strict INTEGER to seeds when PRAGMA table_info(seeds) lacks it (ALTER TABLE seeds ADD COLUMN strict INTEGER, commit, no UPDATE), the same pattern as the existing migrations; (2) a read-only open records whether seeds has the column, like its other _ro_no_* flags; (3) set_seed_strict(address, strict) -> bool: _guard_write first, lowercase the address, UPDATE seeds SET strict = 1 or 0 WHERE address = ?, commit, return cursor.rowcount > 0 (False writes nothing); (4) strict_seeds() -> sorted list of the addresses whose strict is 1, [] on a read-only store whose seeds table has no strict column; (5) add_seed keeps an existing seed's strict flag: replace INSERT OR REPLACE by an upsert that updates code_id and label in place (INSERT ... ON CONFLICT(address) DO UPDATE SET code_id = excluded.code_id, label = excluded.label); seeds() and remove_seed do not change. The smoke file imports temp_store and load_hex from tests.helpers (temp_store() returns a Store on a fresh temp file; load_hex(name) returns fixture bytes) -- do not read tests/helpers.py, another card rewrites it in your generation." % SPEC,
     "store", ["tests/test_store.py", "tests/test_store_examples.py", "tests/test_store_read.py", "tests/test_store_p11.py", "tests/test_store_examples_p11.py", "tests/test_store_p15.py", "tests/test_store_examples_p15.py"])
code("ingest", "ingest", ["ethsc/ingest.py", "tests/test_ingest_p18.py"], [SPEC, C], [],
     "Read %s FIRST (sections 1, 2 and 4), then in contour.yaml group ingest the Function Follow Chain (description: the sentence on watch) and Ingest Block (the watch sentence). You own ethsc/ingest.py and tests/test_ingest_p18.py. The whole change: follow_chain gains a LAST keyword parameter watch=None (after on_upgrades) and passes it, unchanged, as watch=watch to every ingest_block call it makes; its docstring says so in one sentence. Nothing else in ingest.py changes. The smoke file imports temp_store, block_codes and FakeRpc from tests.helpers (FakeRpc() answers block 26077729 from the fixtures, head 0x18dea21; temp_store() is a fresh Store) -- do not read tests/helpers.py, another card rewrites it in your generation; a smoke test may patch ethsc.ingest.ingest_block with a wrapper that records its watch argument." % SPEC,
     "ingest", [])
code("helpers-p18", "cluster", ["tests/helpers.py"], [SPEC, C, "tests/fixtures/README.md"], [],
     "Read %s FIRST (section 2.3: belle_block_db and write_labels). You own tests/helpers.py: keep every existing function and class exactly as it is and ADD two functions at the end. belle_block_db() -> str: a brand-new tempfile.mkdtemp() directory, a Store on <dir>/ethsc.sqlite filled exactly as block_store() fills its store (every entry of block_codes() at block 26077729: put_address(address, None, 26077729) for a '0x' answer, else put_code then put_address), plus code_belle.hex at 0x34c6211621f2763c60eb007dc2ae91090a2d22f6 and code_belle_copy_1807090d.hex, code_belle_copy_2141be5f.hex, code_belle_copy_46cadea5.hex, code_belle_copy_6411bed8.hex at 0x1807090dd15a6f58e00fd769e32ebf20ee610385, 0x2141be5f2afa674c94167ab167a478a56cb539f5, 0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a, 0x6411bed82614b91ef655d82486e0bd3a13d2eb8c, each with put_address(address, code_id, 1) and no origin; no seed, no progress; the store is closed and the path returned. write_labels(obj) -> str: json.dump(obj) into labels.json inside a brand-new tempfile.mkdtemp() directory, the path returned. Docstrings in the style of the module. Python 3.9 syntax, standard library only, no network import. Do not change any other file." % SPEC,
     "helpers", [], variants=1)
code("cluster", "cluster", ["ethsc/cluster.py", "tests/test_cluster_p18.py"],
     [SPEC, C, "tests/helpers.py", "tests/fixtures/README.md", "ethsc/fingerprint.py", "ethsc/store.py"], ["fingerprint", "store", "helpers-p18"],
     "Read %s FIRST (sections 1, 2, 4 and 7), then in contour.yaml group cluster: Interface Hits (new, whole), Match Watchlist (the paragraph 'Phase 18', example 5) and Recheck Watchlist (the paragraph 'Phase 18', examples 6 and 12). You own ethsc/cluster.py and tests/test_cluster_p18.py. In ethsc/cluster.py: (1) import ALERT_MIN, CODE_MIN and code_similarity from ethsc.fingerprint; (2) the default min_score of match_watchlist and recheck_watchlist becomes ALERT_MIN (find_similar keeps 0.8); (3) both read store.strict_seeds() once per call; for a strict seed a candidate that reached min_score also needs code_similarity(candidate code, store.code_by_id(seed code_id)) >= CODE_MIN (in recheck_watchlist the candidate code is store.code_by_id(effective code_id)); a None code means no alert; the alert keeps the Similarity Score; code_by_id is never called for a loose seed, so a store with no strict seed is read exactly as before; (4) new interface_hits(store, code_id, min_score=ALERT_MIN, code_min=CODE_MIN) -> int as the Contour describes, calling code_by_id only for code_id and for the codes that reach min_score. Update the module docstring's phase-11 sentence on code_by_id accordingly. The smoke file uses belle_block_db() from tests.helpers (a path; open it with Store(path))." % SPEC,
     "cluster", ["tests/test_cluster.py", "tests/test_cluster_examples.py", "tests/test_cluster_p11.py", "tests/test_cluster_examples_p11.py"])
code("calibrate", "calibrate", ["ethsc/calibrate.py", "tests/test_calibrate_p18.py"],
     [SPEC, C, "tests/helpers.py", "ethsc/fingerprint.py", "ethsc/store.py", "tests/fixtures/calibration_labels.json"], ["fingerprint", "store", "helpers-p18"],
     "Read %s FIRST (sections 1, 2, 4 and 6), then in contour.yaml the new group calibrate: Evaluate Calibration and Load Labels (whole, every example) and the dataObject Calibration Labels. You create ethsc/calibrate.py and tests/test_calibrate_p18.py. ethsc/calibrate.py: a module docstring; DEFAULT_GRID = (0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0); evaluate(store, labels, thresholds=DEFAULT_GRID, code_min=CODE_MIN); load_labels(path); parse_grid(text). It imports from ethsc.fingerprint only (fingerprint, score_fingerprints, opcode_shingles or code_similarity, CODE_MIN) -- never ethsc.cluster, never sqlite3 -- and reads the store through fingerprints(), code_of() and code_by_id(). Compute each (labelled code_id, stored code_id) Fingerprint score once and each code's opcode shingles once per call, then apply every threshold to those numbers (night2: 46 labelled addresses x 19 804 codes must take seconds). Follow the behavior text literally: directed checks both ways, missing sorted, benign = stored code_ids that are not a labelled address's code_id, interface_only counted through a loose seed with code similarity below code_min. load_labels/parse_grid raise ValueError with a one-line message. The smoke file uses belle_block_db() and write_labels() from tests.helpers." % SPEC,
     "calibrate", [])
code("cli", "cli", ["ethsc/cli.py", "tests/test_cli_p18.py"],
     [SPEC, C, "tests/helpers.py", "ethsc/cluster.py", "ethsc/calibrate.py"], ["cluster", "calibrate", "ingest", "store", "helpers-p18"],
     "Read %s FIRST (sections 1, 2, 3.0 and 4), then in contour.yaml group cli, Command Line: the subcommand list, the paragraph 'Calibration (phase 18)', examples 36, 37, 39 (now at --min 0.8) and 57-62. You own ethsc/cli.py and tests/test_cli_p18.py. In ethsc/cli.py: (1) listen and backfill take --min (float, default ALERT_MIN from ethsc.fingerprint) and pass it to follow_chain as watch=; a value that is not a float or lies outside [0, 1] is a usage error (exit 2, one stderr line, no rpc call -- validate before any client is built); (2) recheck --min defaults to ALERT_MIN; similar keeps 0.8; the seed add preview calls recheck_watchlist with its default; (3) seed strict <addr> {on,off}: address check as elsewhere, store.set_seed_strict(address, mode == 'on'); False -> stderr 'not a seed: <address lowercase>', exit 2; (4) seed audit: for every seed of store.seeds() one record '<address>\\t<label>\\t<interface_hits(store, code_id)>\\t<strict|loose>' (strict when in store.strict_seeds()); (5) calibrate --labels FILE [--grid LIST]: load_labels and parse_grid from ethsc.calibrate (ValueError -> exit 2 with str(err) as the one stderr line, before the store is read), then evaluate(store, labels, thresholds) and one record per row '%%.4f\\t%%.4f\\t%%d\\t%%d\\t%%d\\t%%d' (threshold, recall, negatives, benign, interface_only, benign_total), then 'missing: <comma-joined>' on stderr when missing is not empty; exit 0; no rpc. Keep every other subcommand byte-identical. The smoke file uses belle_block_db, write_labels and FakeRpc from tests.helpers and calls main(argv, rpc=...) with redirected stdout/stderr." % SPEC,
     "cli", ["tests/test_origin_examples_p13.py"],
     deselect=False)

judge("fingerprint-judge", "tests/test_fingerprint_examples_p18.py", [SPEC, C, "tests/helpers.py", "ethsc/fingerprint.py", "tests/fixtures/README.md"],
      ["fingerprint", "helpers-p18"], 6, "group fingerprint, Code Similarity examples 1-6")
judge("store-judge", "tests/test_store_examples_p18.py", [SPEC, C, "tests/helpers.py", "ethsc/store.py"],
      ["store", "helpers-p18"], 3, "group store, Manage Watchlist examples 6-8 (example 1 defines the BELLE db they start from)")
judge("ingest-judge", "tests/test_ingest_examples_p18.py", [SPEC, C, "tests/helpers.py", "ethsc/ingest.py"],
      ["ingest", "cluster", "helpers-p18"], 1, "group ingest, Follow Chain example 18 (Ingest Block example 12 defines the store; the default watch is the cluster default ALERT_MIN 0.75)")
judge("cluster-judge", "tests/test_cluster_examples_p18.py", [SPEC, C, "tests/helpers.py", "ethsc/cluster.py", "ethsc/store.py"],
      ["cluster", "helpers-p18"], 4, "group cluster, Interface Hits examples 1-2, Match Watchlist example 5, Recheck Watchlist example 12 (belle_block_db() is the store of Interface Hits example 1)")
judge("calibrate-judge", "tests/test_calibrate_examples_p18.py", [SPEC, C, "tests/helpers.py", "ethsc/calibrate.py"],
      ["calibrate", "helpers-p18"], 8, "group calibrate, Evaluate Calibration examples 1-4 and Load Labels examples 1-4 (belle_block_db() is the store; write_labels writes a labels file)")
judge("cli-judge", "tests/test_cli_examples_p18.py", [SPEC, C, "tests/helpers.py", "ethsc/cli.py", "ethsc/calibrate.py"],
      ["cli", "helpers-p18"], 6, "group cli, Command Line examples 57-62 (example 36 defines the deploy-seed setup that 57 reuses; belle_block_db() plus add_seed is the db of 59-62). Call main(argv, rpc=...) with sys.stdout and sys.stderr captured by contextlib.redirect_stdout / redirect_stderr into io.StringIO objects and compare their getvalue() with the exact expected text, newlines included. An address the Contour writes in upper case keeps the lower-case prefix: '0x' + hex.upper(), never address.upper() (0X... is an invalid address, exit 2)",
      deselect=False)

if __name__ == "__main__":
    mp = os.path.join(ROOT, "morph-map.json")
    m = json.load(open(mp))
    m["groups"]["fingerprint"] = ["Fingerprint Code", "Score Fingerprints", "Code Similarity", "Similarity Score"]
    m["groups"]["cluster"] = ["Build Clusters", "Find Similar", "Interface Hits", "Match Watchlist", "Recheck Watchlist"]
    m["groups"]["calibrate"] = ["Evaluate Calibration", "Load Labels"]
    for k, v in CARDS.items():
        if k == "helpers-p18":
            continue
        m["cards"][k] = v
    h = dict(CARDS["helpers-p18"]); h["custom_id"] = "helpers-p18"; h["component"] = "cluster"
    m["extra_cards"] = [h]
    json.dump(m, open(mp, "w"), indent=2, ensure_ascii=False)
    open(mp, "a").write("\n")
    for k, v in CARDS.items():
        open("/tmp/p18/acc-%s.sh" % k, "w").write(v["acceptance"])
    print("cards:", len(CARDS))
