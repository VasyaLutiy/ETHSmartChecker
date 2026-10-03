"""Judge tests for Command Line examples 57-62 (phase 18, contour.yaml, group cli).

One unittest test per Contour example; every expected value is taken
verbatim from the Contour. Each run calls ethsc.cli.main(argv, rpc=...)
with stdout and stderr captured, and the exact expected text (newlines
included) is compared. No network: FakeRpc never answers and only
records; every file a test writes lives in a tempfile.mkdtemp()
directory.
"""

import contextlib
import io
import os
import tempfile
import unittest

try:
    from tests.helpers import (
        FakeRpc,
        belle_block_db,
        block_codes,
        write_labels,
    )
except ImportError:  # pragma: no cover - pytest layout fallback
    from helpers import (
        FakeRpc,
        belle_block_db,
        block_codes,
        write_labels,
    )

from ethsc.cli import main as cli_main
from ethsc.store import Store

DEPLOY_SEED = "0x1111111111111111111111111111111111111111"
DEPLOYED = "0xb53c071bdb35d21aa1216b084f79c372d71053d5"
BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
# The Contour writes this address in upper case: '0x' + hex.upper().
BELLE_UPPER = "0x" + BELLE[2:].upper()
COPIES = [
    "0x1807090dd15a6f58e00fd769e32ebf20ee610385",
    "0x2141be5f2afa674c94167ab167a478a56cb539f5",
    "0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a",
    "0x6411bed82614b91ef655d82486e0bd3a13d2eb8c",
]
SHIB = "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce"
MISSING_ADDRESS = "0x9999999999999999999999999999999999999999"

# The labels of Evaluate Calibration example 1 (strict BELLE).
LABELS = {
    "positives": [
        [BELLE, COPIES[0]],
        ["0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
         "0x22052a1a0f5a3d2839d71c458f177e68b0e73963"],
        [BELLE, MISSING_ADDRESS],
    ],
    "negatives": [
        [BELLE, SHIB],
    ],
    "strict": [BELLE],
}


def _run(argv, rpc=None):
    """One main() call with stdout/stderr captured; (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main(argv, rpc=rpc)
    return code, out.getvalue(), err.getvalue()


def _deploy_seed_db():
    """Example 36's setup: the deploy seed over the block's deploy code."""
    directory = tempfile.mkdtemp(prefix="ethsc-p18-judge-")
    path = os.path.join(directory, "ethsc.sqlite")
    store = Store(path)
    text = block_codes()[DEPLOYED]
    code_id = store.put_code(bytes.fromhex(text[2:]))
    store.put_address(DEPLOY_SEED, code_id, 1)
    store.add_seed(DEPLOY_SEED, "deployed in 26077729")
    store.close()
    return path


def _belle_loose_db():
    """belle_block_db() plus the loose BELLE seed, closed; the path."""
    path = belle_block_db()
    store = Store(path)
    store.add_seed(BELLE, "BELLE honeypot")
    store.close()
    return path


class TestCommandLineExamplesP18(unittest.TestCase):

    def test_example_57_min_validation_is_usage_error(self):
        """--min outside [0, 1] or not a float: exit 2, one stderr line."""
        directory = tempfile.mkdtemp(prefix="ethsc-p18-judge-")
        db = os.path.join(directory, "ethsc.sqlite")
        fake = FakeRpc(fail=AssertionError("no rpc"))
        argvs = [
            ["--db", db, "backfill", "--from", "26077729",
             "--to", "26077729", "--min", "1.5"],
            ["--db", db, "listen", "--min", "-0.1"],
            ["--db", db, "backfill", "--from", "26077729",
             "--to", "26077729", "--min", "x"],
        ]
        for argv in argvs:
            code, out, err = _run(argv, rpc=fake)
            self.assertEqual(code, 2, argv)
            self.assertEqual(out, "", argv)
            self.assertTrue(err, argv)
            self.assertEqual(err.count("\n"), 1, argv)
            self.assertTrue(err.endswith("\n"), argv)
        self.assertEqual(fake.calls, [])

    def test_example_58_default_min_is_alert_min(self):
        """The deploy seed, backfill with no --min then recheck: 5 lines."""
        db = _deploy_seed_db()
        alert = "ALERT\t%s\t%s\tdeployed in 26077729\t%s\t%s"
        lines = [
            alert % ("0x514910771af9ca656af840dff83e8264ecf986ca",
                     DEPLOY_SEED, "0.7500", "seen"),
            alert % (SHIB, DEPLOY_SEED, "0.7500", "seen"),
            alert % (DEPLOYED, DEPLOY_SEED, "1.0000", "created"),
            alert % ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
                     DEPLOY_SEED, "0.8182", "seen"),
            alert % ("0xff74317e948695297acb79cb2de06111f5cc16b3",
                     DEPLOY_SEED, "1.0000", "seen"),
        ]
        expected = "\n".join(lines) + "\n"
        code, out, err = _run(
            ["--db", db, "backfill", "--from", "26077729",
             "--to", "26077729"], rpc=FakeRpc())
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, expected)
        code, out, err = _run(["--db", db, "recheck"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, expected)

    def test_example_59_seed_audit_and_strict_recheck(self):
        """seed audit, seed strict on/off and recheck --min 0.7."""
        db = _belle_loose_db()
        audit_line = BELLE + "\tBELLE honeypot\t0\t%s\n"

        code, out, err = _run(["--db", db, "seed", "audit"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, audit_line % "loose")

        code, out, err = _run(
            ["--db", db, "seed", "strict", BELLE_UPPER, "on"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

        code, out, err = _run(["--db", db, "seed", "audit"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, audit_line % "strict")

        code, out, err = _run(["--db", db, "seed", "list"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, BELLE + "\tBELLE honeypot\n")

        strict_expected = "".join(
            "ALERT\t%s\t%s\tBELLE honeypot\t0.8667\tunknown\n" % (copy, BELLE)
            for copy in COPIES)
        code, out, err = _run(["--db", db, "recheck", "--min", "0.7"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, strict_expected)

        code, out, err = _run(
            ["--db", db, "seed", "strict", BELLE, "off"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

        loose_expected = strict_expected + (
            "ALERT\t%s\t%s\tBELLE honeypot\t0.7333\tunknown\n"
            % (SHIB, BELLE))
        code, out, err = _run(["--db", db, "recheck", "--min", "0.7"])
        self.assertEqual(code, 0)
        self.assertEqual(err, "")
        self.assertEqual(out, loose_expected)

    def test_example_60_seed_strict_usage_errors(self):
        """seed strict on a non-seed, a bad address and a bad mode."""
        db = _belle_loose_db()
        cases = [
            (["--db", db, "seed", "strict", COPIES[0], "on"],
             "not a seed: %s\n" % COPIES[0]),
            (["--db", db, "seed", "strict", "0x12", "on"], None),
            (["--db", db, "seed", "strict", BELLE, "maybe"], None),
        ]
        for argv, exact in cases:
            code, out, err = _run(argv)
            self.assertEqual(code, 2, argv)
            self.assertEqual(out, "", argv)
            self.assertTrue(err, argv)
            self.assertEqual(err.count("\n"), 1, argv)
            self.assertTrue(err.endswith("\n"), argv)
            if exact is not None:
                self.assertEqual(err, exact, argv)
        store = Store(db)
        try:
            self.assertEqual(store.strict_seeds(), [])
        finally:
            store.close()

    def test_example_61_calibrate(self):
        """calibrate over the labelled pairs: 4 rows, then the 7 defaults."""
        db = _belle_loose_db()
        labels_path = write_labels(LABELS)
        fake = FakeRpc(fail=AssertionError("no rpc"))
        store = Store(db)
        try:
            before = (store.counts(), len(store.seeds()),
                      store.strict_seeds())
        finally:
            store.close()

        expected4 = (
            "0.7000\t1.0000\t1\t6\t5\t131\n"
            "0.7500\t1.0000\t0\t6\t2\t131\n"
            "0.8000\t1.0000\t0\t4\t0\t131\n"
            "0.9000\t0.5000\t0\t3\t0\t131\n"
        )
        missing_line = "missing: %s\n" % MISSING_ADDRESS

        code, out, err = _run(
            ["--db", db, "calibrate", "--labels", labels_path,
             "--grid", "0.7,0.75,0.8,0.9"], rpc=fake)
        self.assertEqual(code, 0)
        self.assertEqual(out, expected4)
        self.assertEqual(err, missing_line)

        code, out, err = _run(
            ["--db", db, "calibrate", "--labels", labels_path], rpc=fake)
        self.assertEqual(code, 0)
        lines = out.split("\n")
        self.assertEqual(lines[-1], "")
        lines = lines[:-1]
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[0], "0.5000\t1.0000\t1\t19\t18\t131")
        self.assertEqual(lines[-1], "1.0000\t0.5000\t0\t3\t0\t131")
        self.assertEqual(err, missing_line)
        self.assertEqual(fake.calls, [])

        store = Store(db)
        try:
            after = (store.counts(), len(store.seeds()),
                     store.strict_seeds())
        finally:
            store.close()
        self.assertEqual(before, after)

    def test_example_62_calibrate_usage_errors(self):
        """Bad labels or a bad --grid: exit 2, one stderr line, no rpc."""
        db = _belle_loose_db()
        good = write_labels(LABELS)
        missing = os.path.join(
            tempfile.mkdtemp(prefix="ethsc-p18-judge-"), "nope.json")
        empty = os.path.join(
            tempfile.mkdtemp(prefix="ethsc-p18-judge-"), "empty.json")
        with open(empty, "w", encoding="utf-8") as handle:
            handle.write("[]")
        fake = FakeRpc(fail=AssertionError("no rpc"))
        argvs = [
            ["--db", db, "calibrate", "--labels", missing],
            ["--db", db, "calibrate", "--labels", empty],
            ["--db", db, "calibrate", "--labels", good,
             "--grid", "0.5,abc"],
            ["--db", db, "calibrate", "--labels", good, "--grid", "1.5"],
        ]
        for argv in argvs:
            code, out, err = _run(argv, rpc=fake)
            self.assertEqual(code, 2, argv)
            self.assertEqual(out, "", argv)
            self.assertTrue(err, argv)
            self.assertEqual(err.count("\n"), 1, argv)
            self.assertTrue(err.endswith("\n"), argv)
        self.assertEqual(fake.calls, [])


if __name__ == "__main__":
    unittest.main()
