"""Judge tests for the cli card: one test per contour.yaml example of
Command Line, plus the exit-code and ALERT-line contract of
docs/TASK_PHASE5.md section 2.2.

Offline: every rpc is a tests.helpers.FakeRpc; no fixture loaders or
fakes are written here. INFURA_API_KEY is set to TESTKEY-0000 and the
assertions check it never leaks into stdout or stderr.
"""

import contextlib
import io
import os
import sqlite3
import tempfile
import unittest

from ethsc.rpc import RpcError
from ethsc.cli import main
from ethsc.store import Store

from tests.helpers import (FakeRpc, block_codes, load_hex, temp_store)

_BELLE_SEED = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_BELLE_COPY = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
_PAIR = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
_SIMILAR_L0 = [
    "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
    "0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c",
    "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f",
]
_EXPECTED_ALERT = (
    "ALERT\t%s\t%s\tBELLE honeypot\t0.8667\n" % (_BELLE_COPY, _BELLE_SEED)
)


class _Capture(object):
    """Run main() with captured stdout/stderr; record both as text."""

    def __init__(self):
        self.out = io.StringIO()
        self.err = io.StringIO()

    def run(self, argv, rpc):
        out, err = sys_out_err()
        try:
            with contextlib.redirect_stdout(self.out):
                with contextlib.redirect_stderr(self.err):
                    code = main(argv, rpc=rpc)
        finally:
            restore_out_err(out, err)
        return code


def sys_out_err():
    import sys
    return sys.stdout, sys.stderr


def restore_out_err(out, err):
    import sys
    sys.stdout = out
    sys.stderr = err


class CliExamplesTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self._saved_env = os.environ.get("INFURA_API_KEY")
        os.environ["INFURA_API_KEY"] = "TESTKEY-0000"
        self.dir = tempfile.mkdtemp(prefix="ethsc-judge-")
        self.db = os.path.join(self.dir, "ethsc.sqlite")

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("INFURA_API_KEY", None)
        else:
            os.environ["INFURA_API_KEY"] = self._saved_env

    def run_main(self, argv, rpc):
        cap = _Capture()
        code = cap.run(argv, rpc)
        return code, cap.out.getvalue(), cap.err.getvalue()

    def test_backfill_block_stores_206_addresses_130_codes(self):
        """contour example: backfill 26077729..26077729 with a fake rpc.

        exit 0 and the db holds 206 addresses and 130 codes.
        """
        rpc = FakeRpc(codes=block_codes(), head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729"], rpc)
        self.assertEqual(0, code,
                         msg="backfill exit code: got %r, want 0; stderr=%r"
                             % (code, err))
        self.assertEqual("", err, msg="unexpected stderr: %r" % (err,))
        conn = sqlite3.connect(self.db)
        try:
            addresses = conn.execute(
                "SELECT COUNT(*) FROM addresses").fetchone()[0]
            codes = conn.execute(
                "SELECT COUNT(*) FROM codes").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(206, addresses,
                         msg="addresses in db: got %d, want 206" % addresses)
        self.assertEqual(130, codes,
                         msg="codes in db: got %d, want 130" % codes)

    def test_similar_pair_finds_three_copies_and_one_partial(self):
        """contour example: similar <pair> --min 0.8 on the filled db.

        4 lines: three UniswapV2Pair addresses with 1.0000 first in
        address order, then 0xcf6daab9... with 0.8125.
        """
        rpc = FakeRpc(codes=block_codes(), head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729"], rpc)
        self.assertEqual(0, code, msg="backfill setup: got %r" % (code,))
        code, out, err = self.run_main(
            ["--db", self.db, "similar", _PAIR, "--min", "0.8"], rpc)
        self.assertEqual(0, code,
                         msg="similar exit code: got %r, want 0; stderr=%r"
                             % (code, err))
        lines = out.splitlines()
        want_addresses = _SIMILAR_L0 + [
            "0xcf6daab95c476106eca715d48de4b13287ffdeaa"]
        want = ["%s\t1.0000" % addr for addr in _SIMILAR_L0] + [
            "0xcf6daab95c476106eca715d48de4b13287ffdeaa\t0.8125"]
        self.assertEqual(4, len(lines),
                         msg="similar lines: got %r, want 4 lines" % (lines,))
        self.assertEqual(want, lines,
                         msg="similar output lines: got %r, want %r"
                             % (lines, want))
        self.assertEqual(want_addresses,
                         [line.split("\t")[0] for line in lines],
                         msg="similar address order: got %r" % (lines,))

    def test_backfill_of_belle_copy_prints_exactly_one_alert_line(self):
        """contour example: ALERT for the BELLE copy against the seed.

        One stdout line, exactly ALERT\t0x1807090d...\t0x34c6...\tBELLE
        honeypot\t0.8667.
        """
        store = temp_store()
        store.close()
        db = os.path.join(os.path.dirname(store._conn.database
                                          if False else self.db), self.db)
        # Build the seeded store on a known path: re-open on self.db.
        store = Store(self.db)
        code_belle = load_hex("code_belle.hex")
        store.put_code(code_belle)
        store.put_address(_BELLE_SEED, store.put_code(code_belle),
                          26077728)
        store.add_seed(_BELLE_SEED, "BELLE honeypot")
        store.close()

        receipts = [{
            "to": _BELLE_COPY,
            "contractAddress": None,
            "logs": [],
        }]
        codes = {
            _BELLE_COPY: "0x" + load_hex(
                "code_belle_copy_1807090d.hex").hex(),
        }
        rpc = FakeRpc(codes=codes, receipts=receipts, head="0x18dea22")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729"], rpc)
        self.assertEqual(0, code,
                         msg="backfill exit code: got %r, want 0; stderr=%r"
                             % (code, err))
        self.assertEqual(_EXPECTED_ALERT, out,
                         msg="alert stdout: got %r, want %r"
                             % (out, _EXPECTED_ALERT))
        self.assertEqual("", err, msg="unexpected stderr: %r" % (err,))

    def test_listen_with_failing_rpc_no_secret_no_traceback(self):
        """contour example: listen with an RpcError-ing rpc.

        Nonzero exit, no traceback, and TESTKEY-0000 nowhere in stdout
        or stderr.
        """
        rpc = FakeRpc(fail=RpcError(None, "transport failed"))
        code, out, err = self.run_main(["--db", self.db, "listen"], rpc)
        self.assertNotEqual(0, code,
                            msg="listen exit code: got 0, want nonzero")
        self.assertNotIn("Traceback", out + err,
                         msg="traceback leaked: stdout=%r stderr=%r"
                             % (out, err))
        self.assertNotIn("TESTKEY-0000", out,
                         msg="secret in stdout: %r" % (out,))
        self.assertNotIn("TESTKEY-0000", err,
                         msg="secret in stderr: %r" % (err,))

    def test_backfill_budget_stop_exit_code_3_empty_stdout(self):
        """section 2.2 contract: budget stop after no work -> exit 3.

        --daily-budget 79 (< the 80-credit eth_blockNumber price) stops
        follow_chain before the first call: exit 3, stdout empty.
        """
        rpc = FakeRpc(codes=block_codes(), head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729", "--daily-budget", "79"], rpc)
        self.assertEqual(3, code,
                         msg="budget-stop exit code: got %r, want 3" % (code,))
        self.assertEqual("", out,
                         msg="budget-stop stdout: got %r, want empty" % (out,))
        self.assertEqual("", err, msg="unexpected stderr: %r" % (err,))

    def test_usage_error_no_subcommand_exit_code_2(self):
        """section 2.2 contract: argparse usage error -> exit code 2."""
        code, out, err = self.run_main(["--db", self.db], FakeRpc())
        self.assertEqual(2, code,
                         msg="usage-error exit code: got %r, want 2"
                             % (code,))
        self.assertNotEqual("", err,
                            msg="usage error should say why; stderr empty")
        self.assertNotIn("Traceback", err,
                         msg="usage error printed a traceback: %r" % (err,))

    def test_usage_error_bad_address_exit_code_2(self):
        """section 2.2 contract: malformed address argument -> exit 2."""
        code, out, err = self.run_main(
            ["--db", self.db, "similar", "not-an-address"], FakeRpc())
        self.assertEqual(2, code,
                         msg="bad-address exit code: got %r, want 2"
                             % (code,))
        self.assertNotIn("Traceback", err,
                         msg="bad address printed a traceback: %r" % (err,))


if __name__ == "__main__":
    unittest.main()
