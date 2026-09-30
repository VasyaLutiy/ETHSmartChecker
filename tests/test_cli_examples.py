"""Judge tests for the cli card: one test per contour.yaml example of
Command Line, plus the exit-code, stop-line and ALERT-line contracts of
docs/TASK_PHASE5.md section 2.2 as amended by docs/TASK_PHASE6.md 2.2,
plus the three phase 7.2 examples (report determinism, lazy rpc, report
without matplotlib) of docs/TASK_PHASE7_2.md section 3.6.

Offline: every rpc is a tests.helpers.FakeRpc; no fixture loaders or
fakes are written here. INFURA_API_KEY is set to TESTKEY-0000 and the
assertions check it never leaks into stdout or stderr.
"""

import contextlib
import io
import os
import sqlite3
import sys
import tempfile
import unittest

from ethsc.rpc import RpcError
from ethsc.cli import main
from ethsc.store import Store

from tests.helpers import (FakeRpc, InterruptAfter, block_codes, load_hex,
                           temp_store)

_BELLE_SEED = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_BELLE_SEED_UPPER = "0x34C6211621F2763C60EB007DC2AE91090A2D22F6"
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
# The four BELLE copies, in address order; only the first address is a
# real fixture address, the other three carry the fixture-name prefixes.
_BELLE_COPY_ADDRESSES = [
    "0x1807090dd15a6f58e00fd769e32ebf20ee610385",
    "0x2141be5f00000000000000000000000000000000",
    "0x46cadea500000000000000000000000000000000",
    "0x6411bed800000000000000000000000000000000",
]
_BELLE_COPY_FILES = [
    "code_belle_copy_1807090d.hex",
    "code_belle_copy_2141be5f.hex",
    "code_belle_copy_46cadea5.hex",
    "code_belle_copy_6411bed8.hex",
]


class _KIMap(dict):
    """A codes map whose __getitem__ raises KeyboardInterrupt.

    FakeRpc(codes=...) answers eth_getCode with codes[params[0]], so a
    dict subclass raising from __getitem__ puts the interrupt inside
    the pass, at the first code fetch.
    """

    def __getitem__(self, key):
        raise KeyboardInterrupt()


class _Capture(object):
    """Run main() with captured stdout/stderr and an injectable sleep."""

    def __init__(self, sleep=None):
        self.out = io.StringIO()
        self.err = io.StringIO()
        self._sleep = sleep

    def run(self, argv, rpc):
        with contextlib.redirect_stdout(self.out):
            with contextlib.redirect_stderr(self.err):
                code = main(argv, rpc=rpc, sleep=self._sleep)
        return code


class _SleepSpy(object):
    """A sleep stand-in: records the seconds, optionally interrupts."""

    def __init__(self, raise_after=None):
        self.calls = []
        self._raise_after = raise_after

    def __call__(self, seconds):
        self.calls.append(seconds)
        if self._raise_after is not None and \
                len(self.calls) > self._raise_after:
            raise KeyboardInterrupt()


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

    def run_main(self, argv, rpc, sleep=None):
        cap = _Capture(sleep=sleep)
        code = cap.run(argv, rpc)
        return code, cap.out.getvalue(), cap.err.getvalue()

    def _set_progress(self, block):
        store = Store(self.db)
        try:
            store.set_progress(block)
        finally:
            store.close()

    def _progress(self):
        store = Store(self.db)
        try:
            return store.get_progress()
        finally:
            store.close()

    def _seed_belle(self):
        """Store code_belle.hex under the seed address and mark it bad."""
        store = Store(self.db)
        try:
            code_belle = load_hex("code_belle.hex")
            code_id = store.put_code(code_belle)
            store.put_address(_BELLE_SEED, code_id, 26077728)
            store.add_seed(_BELLE_SEED, "BELLE honeypot")
        finally:
            store.close()

    def _fill_block(self):
        """Backfill block 26077729 into self.db via main()."""
        rpc = FakeRpc(codes=block_codes(), head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729"], rpc)
        self.assertEqual(0, code,
                         msg="backfill setup: got %r; stderr=%r"
                             % (code, err))

    def _fill_belle_copies(self):
        """Store code_belle.hex and its four copies, no seed yet."""
        store = Store(self.db)
        try:
            seed_id = store.put_code(load_hex("code_belle.hex"))
            store.put_address(_BELLE_SEED, seed_id, 26077728)
            for address, name in zip(_BELLE_COPY_ADDRESSES,
                                     _BELLE_COPY_FILES):
                store.put_address(
                    address, store.put_code(load_hex(name)), 26077729)
        finally:
            store.close()

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
        self._seed_belle()

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

    def test_listen_interrupted_after_complete_block_keeps_its_alert(self):
        """contour example: the alert of a block completed inside an
        interrupted listen pass.

        Progress 26077728; the rpc interrupts on its fourth call -- the
        eth_getBlockReceipts of block 26077730. Exit 0, stdout exactly
        the one ALERT line of block 26077729, empty stderr, progress
        26077729, sleep never called.
        """
        self._seed_belle()
        self._set_progress(26077728)
        codes = {
            _BELLE_COPY: "0x" + load_hex(
                "code_belle_copy_1807090d.hex").hex(),
        }
        receipts = [{"to": _BELLE_COPY, "contractAddress": None,
                     "logs": []}]
        inner = FakeRpc(codes=codes, receipts=receipts, head="0x18dea22")
        rpc = InterruptAfter(inner, 3)
        sleep = _SleepSpy()
        code, out, err = self.run_main(["--db", self.db, "listen"], rpc,
                                       sleep=sleep)
        self.assertEqual(0, code,
                         msg="interrupted listen exit code: got %r, want 0"
                             % (code,))
        self.assertEqual(_EXPECTED_ALERT, out,
                         msg="alert stdout: got %r, want %r"
                             % (out, _EXPECTED_ALERT))
        self.assertEqual("", err,
                         msg="interrupted listen stderr: got %r, want empty"
                             % (err,))
        self.assertNotIn("Traceback", out + err,
                         msg="traceback leaked: stdout=%r stderr=%r"
                             % (out, err))
        self.assertEqual(26077729, self._progress(),
                         msg="progress after interrupt: got %r, want 26077729"
                             % (self._progress(),))
        self.assertEqual([], sleep.calls,
                         msg="sleep calls after interrupt: got %r, want []"
                             % (sleep.calls,))

    def test_backfill_cap_stop_prints_alert_before_stop_line(self):
        """contour example: the alert of a block stopped by the cap.

        A seeded db, no progress, two candidates (the BELLE copy and the
        pair), --max-calls-per-block 1: exit 3, stdout exactly the one
        ALERT line, stderr exactly the cap stop line with spent 1160 and
        progress none. The alert is printed before the stop line.
        """
        self._seed_belle()
        codes = {
            _BELLE_COPY: "0x" + load_hex(
                "code_belle_copy_1807090d.hex").hex(),
            _PAIR: block_codes()[_PAIR],
        }
        receipts = [
            {"to": _BELLE_COPY, "contractAddress": None, "logs": []},
            {"to": _PAIR, "contractAddress": None, "logs": []},
        ]
        rpc = FakeRpc(codes=codes, receipts=receipts, head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729", "--max-calls-per-block", "1"], rpc)
        self.assertEqual(3, code,
                         msg="cap-stop exit code: got %r, want 3" % (code,))
        self.assertEqual(_EXPECTED_ALERT, out,
                         msg="alert stdout: got %r, want %r"
                             % (out, _EXPECTED_ALERT))
        self.assertEqual(
            "stopped: cap, spent 1160 credits, progress none\n",
            err,
            msg="cap-stop stderr: got %r, want %r"
                % (err, "stopped: cap, spent 1160 credits, progress none\n"))

    def test_listen_with_failing_rpc_no_secret_no_traceback(self):
        """contour example: listen with an RpcError-ing rpc.

        Exit 1, no traceback, and TESTKEY-0000 nowhere in stdout or
        stderr.
        """
        rpc = FakeRpc(fail=RpcError(None, "transport failed"))
        code, out, err = self.run_main(["--db", self.db, "listen"], rpc)
        self.assertEqual(1, code,
                         msg="listen exit code on RpcError: got %r, want 1"
                             % (code,))
        self.assertNotIn("Traceback", out + err,
                         msg="traceback leaked: stdout=%r stderr=%r"
                             % (out, err))
        self.assertNotIn("TESTKEY-0000", out,
                         msg="secret in stdout: %r" % (out,))
        self.assertNotIn("TESTKEY-0000", err,
                         msg="secret in stderr: %r" % (err,))

    def test_backfill_budget_stop_exit_code_3_stop_line(self):
        """phase 6 contract: budget stop before any work -> exit 3 with
        the stop line.

        --daily-budget 79 (< the 80-credit eth_blockNumber price) stops
        follow_chain before the first call: exit 3, stdout empty, stderr
        exactly the one stop line with progress none.
        """
        rpc = FakeRpc(codes=block_codes(), head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729", "--daily-budget", "79"], rpc)
        self.assertEqual(3, code,
                         msg="budget-stop exit code: got %r, want 3" % (code,))
        self.assertEqual("", out,
                         msg="budget-stop stdout: got %r, want empty" % (out,))
        self.assertEqual("stopped: budget, spent 0 credits, progress none\n",
                         err,
                         msg="budget-stop stderr: got %r, want %r"
                             % (err,
                                "stopped: budget, spent 0 credits,"
                                " progress none\n"))

    def test_backfill_budget_stop_reports_spent_and_progress(self):
        """phase 6 table row: budget cut mid-block reports the real count.

        Progress 26077728, --daily-budget 10000: 80 + 1000 + 111 x 80 =
        9960 credits spent, the block left incomplete, so progress stays
        26077728.
        """
        self._set_progress(26077728)
        rpc = FakeRpc(codes=block_codes(), head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729", "--daily-budget", "10000"], rpc)
        self.assertEqual(3, code,
                         msg="budget-stop exit code: got %r, want 3" % (code,))
        self.assertEqual("stopped: budget, spent 9960 credits,"
                         " progress 26077728\n",
                         err,
                         msg="stop line: got %r, want %r"
                             % (err,
                                "stopped: budget, spent 9960 credits,"
                                " progress 26077728\n"))
        self.assertEqual("", out,
                         msg="stop-line stdout: got %r, want empty" % (out,))

    def test_listen_interrupt_inside_pass_at_first_code_fetch(self):
        """contour example: Ctrl-C inside the pass, at the first
        eth_getCode.

        Progress 26077728, a codes map raising KeyboardInterrupt from
        __getitem__: exit 0, empty stdout and stderr, progress still
        26077728, sleep never called.
        """
        self._set_progress(26077728)
        sleep = _SleepSpy()
        rpc = FakeRpc(codes=_KIMap(), head="0x18dea21")
        code, out, err = self.run_main(["--db", self.db, "listen"], rpc,
                                       sleep=sleep)
        self.assertEqual(0, code,
                         msg="interrupted listen exit code: got %r, want 0"
                             % (code,))
        self.assertEqual("", out,
                         msg="interrupted listen stdout: got %r, want empty"
                             % (out,))
        self.assertEqual("", err,
                         msg="interrupted listen stderr: got %r, want empty"
                             % (err,))
        self.assertEqual(26077728, self._progress(),
                         msg="progress after interrupt: got %r, want 26077728"
                             % (self._progress(),))
        self.assertEqual([], sleep.calls,
                         msg="sleep calls after interrupt: got %r, want []"
                             % (sleep.calls,))

    def test_listen_interrupt_in_sleep_after_full_pass(self):
        """contour example: Ctrl-C in the sleep between passes.

        Progress 26077728, block 26077729 completes, then the sleep
        raises KeyboardInterrupt: exit 0, sleep called once with 12,
        progress 26077729.
        """
        self._set_progress(26077728)
        sleep = _SleepSpy(raise_after=0)
        rpc = FakeRpc(codes=block_codes(), head="0x18dea21")
        code, out, err = self.run_main(["--db", self.db, "listen"], rpc,
                                       sleep=sleep)
        self.assertEqual(0, code,
                         msg="interrupted listen exit code: got %r, want 0"
                             % (code,))
        self.assertEqual("", err,
                         msg="interrupted listen stderr: got %r, want empty"
                             % (err,))
        self.assertEqual([12], sleep.calls,
                         msg="sleep calls: got %r, want [12]"
                             % (sleep.calls,))
        self.assertEqual(26077729, self._progress(),
                         msg="progress after interrupt: got %r, want 26077729"
                             % (self._progress(),))

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

    def test_seed_add_then_recheck_twice_deterministic(self):
        """contour example: seed add over the filled block db, then
        recheck twice.

        The db of the backfill above (206 addresses), seeded with
        seed add 0xb4e16d01... --label "UniV2 pair seed". seed add
        exits 0 with four ALERT lines on stdout; recheck then exits 0
        twice with byte-identical stdout holding exactly those four
        lines -- 0x22052a1a..., 0x2621cc0b..., 0x3041cbd3... with
        1.0000, then 0xcf6daab9... with 0.8125, all naming the seed
        address and the label; stderr empty.
        """
        self._fill_block()
        seed_lines = [
            "ALERT\t%s\t%s\tUniV2 pair seed\t1.0000\n" % (addr, _PAIR)
            for addr in _SIMILAR_L0
        ] + [
            "ALERT\t0xcf6daab95c476106eca715d48de4b13287ffdeaa\t%s"
            "\tUniV2 pair seed\t0.8125\n" % _PAIR
        ]
        want = "".join(seed_lines)
        code, out, err = self.run_main(
            ["--db", self.db, "seed", "add", _PAIR,
             "--label", "UniV2 pair seed"], FakeRpc())
        self.assertEqual(0, code,
                         msg="seed add exit code: got %r, want 0; stderr=%r"
                             % (code, err))
        self.assertEqual(want, out,
                         msg="seed add stdout: got %r, want %r" % (out, want))
        self.assertEqual("", err,
                         msg="seed add stderr: got %r, want empty" % (err,))

        code, out, err = self.run_main(["--db", self.db, "recheck"],
                                       FakeRpc())
        self.assertEqual(0, code,
                         msg="first recheck exit code: got %r, want 0"
                             % (code,))
        self.assertEqual(want, out,
                         msg="first recheck stdout: got %r, want %r"
                             % (out, want))
        self.assertEqual("", err,
                         msg="first recheck stderr: got %r, want empty"
                             % (err,))
        first = out
        code, out, err = self.run_main(["--db", self.db, "recheck"],
                                       FakeRpc())
        self.assertEqual(0, code,
                         msg="second recheck exit code: got %r, want 0"
                             % (code,))
        self.assertEqual(first, out,
                         msg="recheck not deterministic: first %r, second %r"
                             % (first, out))
        self.assertEqual("", err,
                         msg="second recheck stderr: got %r, want empty"
                             % (err,))
        self.assertNotIn(_BELLE_SEED, out,
                         msg="seed address among the alerts: %r" % (out,))

    def test_seed_add_uppercase_finds_four_belle_copies(self):
        """contour example: seed add over the BELLE db with four copies.

        The BELLE db with no seed yet, the seed address given in upper
        case: exit 0 and exactly four ALERT lines with 0.8667, one per
        copy in address order, the seed address lowercase in each, the
        seed's own address absent.
        """
        self._fill_belle_copies()
        want = "".join(
            "ALERT\t%s\t%s\tBELLE honeypot\t0.8667\n"
            % (addr, _BELLE_SEED)
            for addr in _BELLE_COPY_ADDRESSES)
        code, out, err = self.run_main(
            ["--db", self.db, "seed", "add", _BELLE_SEED_UPPER,
             "--label", "BELLE honeypot"], FakeRpc())
        self.assertEqual(0, code,
                         msg="seed add exit code: got %r, want 0" % (code,))
        self.assertEqual(want, out,
                         msg="seed add stdout: got %r, want %r"
                             % (out, want))
        self.assertEqual("", err,
                         msg="seed add stderr: got %r, want empty" % (err,))
        self.assertNotIn(_BELLE_SEED_UPPER, out,
                         msg="uppercase seed address echoed: %r" % (out,))
        self.assertNotIn(
            "ALERT\t%s\t" % _BELLE_SEED, out,
            msg="seed's own address among the alerts: %r" % (out,))

    def test_recheck_empty_without_seeds_and_min_one_filters(self):
        """contour example: recheck with no seeds, then recheck --min 1.0.

        recheck on a db with addresses but no seeds: exit 0 and empty
        stdout. recheck --min 1.0 on the seeded db of the block: only
        the three 1.0000 lines.
        """
        self._fill_block()
        code, out, err = self.run_main(["--db", self.db, "recheck"],
                                       FakeRpc())
        self.assertEqual(0, code,
                         msg="unseeded recheck exit code: got %r, want 0"
                             % (code,))
        self.assertEqual("", out,
                         msg="unseeded recheck stdout: got %r, want empty"
                             % (out,))
        self.assertEqual("", err,
                         msg="unseeded recheck stderr: got %r, want empty"
                             % (err,))

        # The same db, now seeded as in the pair-seed example above;
        # recheck --min 1.0 keeps only the three score-1.0 alerts.
        code, out, err = self.run_main(
            ["--db", self.db, "seed", "add", _PAIR,
             "--label", "UniV2 pair seed"], FakeRpc())
        self.assertEqual(0, code,
                         msg="seed add setup: got %r; stderr=%r"
                             % (code, err))
        want = "".join(
            "ALERT\t%s\t%s\tUniV2 pair seed\t1.0000\n" % (addr, _PAIR)
            for addr in _SIMILAR_L0)
        code, out, err = self.run_main(
            ["--db", self.db, "recheck", "--min", "1.0"], FakeRpc())
        self.assertEqual(0, code,
                         msg="recheck --min 1.0 exit code: got %r, want 0"
                             % (code,))
        self.assertEqual(want, out,
                         msg="recheck --min 1.0 stdout: got %r, want %r"
                             % (out, want))
        self.assertEqual("", err,
                         msg="recheck --min 1.0 stderr: got %r, want empty"
                             % (err,))

    # -- phase 7.2 examples (docs/TASK_PHASE7_2.md section 3.6) ---------

    def test_report_twice_exit_0_two_lines_byte_identical_files(self):
        """contour example: report --out run twice on the block db.

        The db of block 26077729 and an empty output directory: exit 0
        both times, stderr empty, stdout exactly two lines -- the html
        path then the json path -- and both files byte-identical between
        the two runs.
        """
        self._fill_block()
        outdir = tempfile.mkdtemp(prefix="ethsc-report-judge-")
        prefix = os.path.join(outdir, "r")
        html_path = prefix + ".html"
        json_path = prefix + ".json"
        files = []
        for run in (1, 2):
            code, out, err = self.run_main(
                ["--db", self.db, "report", "--out", prefix], None)
            self.assertEqual(
                0, code,
                msg="report run %d exit code: got %r, want 0; stderr=%r"
                    % (run, code, err))
            self.assertEqual(
                "", err,
                msg="report run %d stderr: got %r, want empty" % (run, err))
            self.assertEqual(
                "%s\n%s\n" % (html_path, json_path),
                out,
                msg="report run %d stdout: got %r, want the html path then"
                    " the json path" % (run, out))
            with open(html_path, "rb") as handle:
                html_bytes = handle.read()
            with open(json_path, "rb") as handle:
                json_bytes = handle.read()
            files.append((html_bytes, json_bytes))
        self.assertEqual(
            files[0], files[1],
            msg="report files not byte-identical between the two runs:"
                " html %d vs %d bytes, json %d vs %d bytes"
                % (len(files[0][0]), len(files[1][0]),
                   len(files[0][1]), len(files[1][1])))

    def test_report_clusters_recheck_run_without_infura_key(self):
        """contour example: report, clusters top and recheck with no key.

        INFURA_API_KEY removed from the environment, the working
        directory changed to one holding no .env: each of report,
        clusters top and recheck exits 0 with rpc=None and raises no
        RpcError (no traceback in stdout or stderr).
        """
        self._fill_block()
        saved_key = os.environ.pop("INFURA_API_KEY", None)
        saved_cwd = os.getcwd()
        nodir = tempfile.mkdtemp(prefix="ethsc-noenv-judge-")
        os.chdir(nodir)
        try:
            code, out, err = self.run_main(
                ["--db", self.db, "report", "--out",
                 os.path.join(nodir, "r")], None)
            self.assertEqual(0, code,
                             msg="report without key exit code: got %r,"
                                 " want 0; stderr=%r" % (code, err))
            self.assertNotIn("Traceback", out + err,
                             msg="report without key raised: stdout=%r"
                                 " stderr=%r" % (out, err))
            code, out, err = self.run_main(
                ["--db", self.db, "clusters", "top"], None)
            self.assertEqual(0, code,
                             msg="clusters top without key exit code:"
                                 " got %r, want 0; stderr=%r"
                                 % (code, err))
            self.assertNotIn("Traceback", out + err,
                             msg="clusters top without key raised:"
                                 " stdout=%r stderr=%r" % (out, err))
            code, out, err = self.run_main(["--db", self.db, "recheck"],
                                           None)
            self.assertEqual(0, code,
                             msg="recheck without key exit code: got %r,"
                                 " want 0; stderr=%r" % (code, err))
            self.assertNotIn("Traceback", out + err,
                             msg="recheck without key raised: stdout=%r"
                                 " stderr=%r" % (out, err))
        finally:
            os.chdir(saved_cwd)
            if saved_key is not None:
                os.environ["INFURA_API_KEY"] = saved_key

    def test_report_without_matplotlib_exit_2_one_stderr_line(self):
        """contour example: report with an unimportable ethsc.charts.

        sys.modules["ethsc.charts"] = None (restored afterwards): exit
        2, stdout empty, no file written, stderr exactly one line
        containing the literal word matplotlib, and no traceback.
        """
        self._fill_block()
        outdir = tempfile.mkdtemp(prefix="ethsc-nompl-judge-")
        prefix = os.path.join(outdir, "r")
        saved = sys.modules.get("ethsc.charts")
        sys.modules["ethsc.charts"] = None
        try:
            code, out, err = self.run_main(
                ["--db", self.db, "report", "--out", prefix], None)
        finally:
            if saved is None:
                sys.modules.pop("ethsc.charts", None)
            else:
                sys.modules["ethsc.charts"] = saved
        self.assertEqual(2, code,
                         msg="report without matplotlib exit code: got %r,"
                             " want 2" % (code,))
        self.assertEqual("", out,
                         msg="report without matplotlib stdout: got %r,"
                             " want empty" % (out,))
        err_lines = err.splitlines()
        self.assertEqual(
            1, len(err_lines),
            msg="report without matplotlib stderr: got %r, want exactly"
                " one line" % (err,))
        self.assertIn(
            "matplotlib", err_lines[0],
            msg="report without matplotlib stderr line: got %r, want the"
                " literal word matplotlib" % (err_lines[0],))
        self.assertNotIn(
            "Traceback", out + err,
            msg="report without matplotlib printed a traceback:"
                " stdout=%r stderr=%r" % (out, err))
        self.assertFalse(
            os.path.exists(prefix + ".html"),
            msg="html file written despite missing matplotlib: %s"
                % (prefix + ".html",))
        self.assertFalse(
            os.path.exists(prefix + ".json"),
            msg="json file written despite missing matplotlib: %s"
                % (prefix + ".json",))


if __name__ == "__main__":
    unittest.main()
