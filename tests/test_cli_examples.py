"""Judge tests for the cli card: one test per contour.yaml example of
Command Line (docs/TASK_PHASE9.md), examples 1..20: the phase-8 set with
the cap-stop and the budget mid-block examples added, and the risk and
cluster listings re-counted after is_std_proxy dropped the standard
proxies.

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

from tests.helpers import FakeRpc, InterruptAfter, block_codes, load_hex

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
# The four BELLE copies, in address order; each address carries the
# fixture-name prefix of its code_belle_copy_*.hex file.
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
_BELLE_CODES = {
    _BELLE_COPY: "0x" + load_hex("code_belle_copy_1807090d.hex").hex(),
}
_BELLE_RECEIPTS = [{"to": _BELLE_COPY, "contractAddress": None, "logs": []}]


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
            code_id = store.put_code(load_hex("code_belle.hex"))
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

    def _fill_belle_block(self):
        """BELLE-seeded db, progress 26077728, one candidate block."""
        self._seed_belle()
        self._set_progress(26077728)
        return FakeRpc(codes=_BELLE_CODES, receipts=_BELLE_RECEIPTS,
                       head="0x18dea22")

    def test_command_line_example_1_backfill_block(self):
        """Command Line example 1: a fake rpc over receipts_26077729.json
        and codes_26077729.json; backfill 26077729..26077729 gives exit 0
        and the db holds 206 addresses and 130 codes.
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

    def test_command_line_example_2_similar_pair(self):
        """Command Line example 2: that db; similar <pair> --min 0.8
        gives 4 lines, the three UniswapV2Pair addresses with 1.0000
        first, 0xcf6daab9... with 0.8125 last (each line ends in the
        always-present "-" flags field).
        """
        self._fill_block()
        code, out, err = self.run_main(
            ["--db", self.db, "similar", _PAIR, "--min", "0.8"], FakeRpc())
        self.assertEqual(0, code,
                         msg="similar exit code: got %r, want 0; stderr=%r"
                             % (code, err))
        lines = out.splitlines()
        want = ["%s\t1.0000\t-" % addr for addr in _SIMILAR_L0] + [
            "0xcf6daab95c476106eca715d48de4b13287ffdeaa\t0.8125\t-"]
        self.assertEqual(4, len(lines),
                         msg="similar lines: got %r, want 4 lines" % (lines,))
        self.assertEqual(want, lines,
                         msg="similar output lines: got %r, want %r"
                             % (lines, want))
        self.assertEqual(_SIMILAR_L0 + [
            "0xcf6daab95c476106eca715d48de4b13287ffdeaa"],
            [line.split("\t")[0] for line in lines],
            msg="similar address order: got %r" % (lines,))

    def test_command_line_example_3_belle_copy_alert(self):
        """Command Line example 3: a db holding code_belle.hex seeded
        "BELLE honeypot"; a backfill over a fake block whose only
        candidate is 0x1807090d... serving code_belle_copy_1807090d.hex
        gives one stdout line starting "ALERT" and naming the address,
        the label and 0.8667.
        """
        self._seed_belle()
        rpc = FakeRpc(codes=_BELLE_CODES, receipts=_BELLE_RECEIPTS,
                      head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729"], rpc)
        self.assertEqual(0, code,
                         msg="backfill exit code: got %r, want 0; stderr=%r"
                             % (code, err))
        lines = out.splitlines()
        self.assertEqual(1, len(lines),
                         msg="stdout lines: got %r, want 1" % (lines,))
        self.assertTrue(lines[0].startswith("ALERT"),
                        msg="line does not start with ALERT: %r" % (lines,))
        self.assertIn(_BELLE_COPY, lines[0],
                      msg="line does not name the copy: %r" % (lines,))
        self.assertIn("BELLE honeypot", lines[0],
                      msg="line does not name the label: %r" % (lines,))
        self.assertIn("0.8667", lines[0],
                      msg="line does not carry 0.8667: %r" % (lines,))
        self.assertEqual("", err, msg="unexpected stderr: %r" % (err,))

    def test_command_line_example_4_listen_rpc_error_secret_hygiene(self):
        """Command Line example 4: INFURA_API_KEY=TESTKEY-0000 and an
        rpc that raises RpcError; listen gives exit 1, no traceback, and
        "TESTKEY-0000" nowhere in stdout or stderr (Secret Hygiene).
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

    def test_command_line_example_5_budget_79_exit_3(self):
        """Command Line example 5: a fresh db, the fake rpc over block
        26077729, --daily-budget 79; exit 3, stdout empty, stderr
        exactly one line starting "stopped: budget" (eth_blockNumber
        costs 80 > 79; the cli acceptance of phase 5).
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

    def test_command_line_cap_stop_alert_before_stop_line(self):
        """Command Line example: a BELLE-seeded db with no progress yet,
        a fake rpc over block 26077729 whose two candidates are the copy
        0x1807090d... (code_belle_copy_1807090d.hex) and the UniV2 pair;
        backfill --max-calls-per-block 1 gives exit 3, stdout exactly
        the one ALERT line at 0.8667, stderr exactly "stopped: cap,
        spent 1160 credits, progress none" (80 + 1000 + 1 x 80); the
        alert is printed before the stop line, checked on one merged
        stream since the two records go to different channels.
        """
        self._seed_belle()
        receipts = [
            {"to": _BELLE_COPY, "contractAddress": None, "logs": []},
            {"to": _PAIR, "contractAddress": None, "logs": []},
        ]
        rpc = FakeRpc(codes=_BELLE_CODES, receipts=receipts,
                      head="0x18dea21")
        merged = io.StringIO()
        with contextlib.redirect_stdout(merged):
            with contextlib.redirect_stderr(merged):
                code = main(["--db", self.db, "backfill", "--from",
                             "26077729", "--to", "26077729",
                             "--max-calls-per-block", "1"], rpc)
        self.assertEqual(3, code,
                         msg="cap-stop exit code: got %r, want 3" % (code,))
        want = _EXPECTED_ALERT + \
            "stopped: cap, spent 1160 credits, progress none\n"
        self.assertEqual(
            want, merged.getvalue(),
            msg="cap-stop output: got %r, want %r -- the ALERT line ahead"
                " of the stop line" % (merged.getvalue(), want))
        self.assertIsNone(self._progress(),
                          msg="progress after cap stop: got %r, want None"
                              % (self._progress(),))

    def test_command_line_budget_mid_block_stop_line(self):
        """Command Line example: progress 26077728 and the fake rpc over
        block 26077729; backfill --daily-budget 10000 gives exit 3,
        stdout empty, stderr exactly "stopped: budget, spent 9960
        credits, progress 26077728" -- the budget cut the block mid-way
        (80 + 1000 + 111 x 80 = 9960) and progress stayed at the last
        complete block.
        """
        self._set_progress(26077728)
        rpc = FakeRpc(codes=block_codes(), head="0x18dea21")
        code, out, err = self.run_main(
            ["--db", self.db, "backfill", "--from", "26077729",
             "--to", "26077729", "--daily-budget", "10000"], rpc)
        self.assertEqual(3, code,
                         msg="budget mid-block exit code: got %r, want 3"
                             % (code,))
        self.assertEqual("", out,
                         msg="budget mid-block stdout: got %r, want empty"
                             % (out,))
        self.assertEqual(
            "stopped: budget, spent 9960 credits, progress 26077728\n",
            err,
            msg="budget mid-block stderr: got %r, want %r"
                % (err,
                   "stopped: budget, spent 9960 credits,"
                   " progress 26077728\n"))
        self.assertEqual(26077728, self._progress(),
                         msg="progress after budget stop: got %r, want"
                             " 26077728" % (self._progress(),))

    def test_command_line_example_6_interrupt_at_first_code_fetch(self):
        """Command Line example 6: a fake rpc whose eth_getCode raises
        KeyboardInterrupt on its first call, progress 26077728; listen
        gives exit 0, no traceback, progress still 26077728, sleep never
        called (live smoke 2026-09-29: Ctrl-C during a block gave a
        traceback, TASK_PHASE5 §13).
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
        self.assertNotIn("Traceback", out + err,
                         msg="traceback leaked: stdout=%r stderr=%r"
                             % (out, err))
        self.assertEqual(26077728, self._progress(),
                         msg="progress after interrupt: got %r, want 26077728"
                             % (self._progress(),))
        self.assertEqual([], sleep.calls,
                         msg="sleep calls after interrupt: got %r, want []"
                             % (sleep.calls,))

    def test_command_line_example_7_interrupt_in_sleep(self):
        """Command Line example 7: the fake rpc over block 26077729,
        progress 26077728, a sleep that raises KeyboardInterrupt; exit
        0, sleep called once with 12, progress 26077729.
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
        self.assertNotIn("Traceback", out + err,
                         msg="traceback leaked: stdout=%r stderr=%r"
                             % (out, err))
        self.assertEqual([12], sleep.calls,
                         msg="sleep calls: got %r, want [12]"
                             % (sleep.calls,))
        self.assertEqual(26077729, self._progress(),
                         msg="progress after interrupt: got %r, want 26077729"
                             % (self._progress(),))

    def test_command_line_example_8_interrupt_keeps_completed_alert(self):
        """Command Line example 8: a BELLE-seeded db, progress 26077728,
        a fake rpc with head 0x18dea22 whose only candidate in block
        26077729 is 0x1807090d... with code_belle_copy_1807090d.hex,
        raising KeyboardInterrupt on its fourth call (the
        eth_getBlockReceipts of block 26077730); exit 0, no traceback,
        stdout holds the one ALERT line of block 26077729, progress
        26077729, sleep never called (the alert of a block completed
        inside an interrupted pass must reach stdout).
        """
        rpc = self._fill_belle_block()
        rpc = InterruptAfter(rpc, 3)
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

    def test_command_line_example_9_recheck_twice_deterministic(self):
        """Command Line example 9: the db of the backfill (206
        addresses), seeded with seed add 0xb4e16d01... --label "UniV2
        pair seed"; recheck twice: exit 0 both times and byte-identical
        stdout -- 4 ALERT lines, 0x22052a1a..., 0x2621cc0b...,
        0x3041cbd3... with 1.0000, then 0xcf6daab9... with 0.8125, all
        naming the seed and the label; stderr empty (Deterministic
        Output; no network, the whole check is the stored codes).
        """
        self._fill_block()
        want = "".join(
            "ALERT\t%s\t%s\tUniV2 pair seed\t1.0000\n" % (addr, _PAIR)
            for addr in _SIMILAR_L0
        ) + "ALERT\t0xcf6daab95c476106eca715d48de4b13287ffdeaa\t%s" \
            "\tUniV2 pair seed\t0.8125\n" % _PAIR
        code, out, err = self.run_main(
            ["--db", self.db, "seed", "add", _PAIR,
             "--label", "UniV2 pair seed"], FakeRpc())
        self.assertEqual(0, code,
                         msg="seed add exit code: got %r, want 0; stderr=%r"
                             % (code, err))
        first = None
        for run in (1, 2):
            code, out, err = self.run_main(["--db", self.db, "recheck"],
                                           FakeRpc())
            self.assertEqual(0, code,
                             msg="recheck run %d exit code: got %r, want 0"
                                 % (run, code))
            self.assertEqual(want, out,
                             msg="recheck run %d stdout: got %r, want %r"
                                 % (run, out, want))
            self.assertEqual("", err,
                             msg="recheck run %d stderr: got %r, want empty"
                                 % (run, err))
            if first is None:
                first = out
        self.assertEqual(first, out,
                         msg="recheck not byte-identical between the two"
                             " runs: first %r, second %r" % (first, out))

    def test_command_line_example_10_seed_add_uppercase_four_copies(self):
        """Command Line example 10: a db holding code_belle.hex at
        0x34c6... and its four copies code_belle_copy_*.hex, no seed
        yet; seed add with the seed address in upper case gives exit 0
        and exactly 4 ALERT lines on stdout, one per copy in address
        order, each with 0.8667 and the seed address lowercase; the
        seed's own address is not among them (TASK_PHASE6_2 §7: copies
        already in the base never produced an alert).
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

    def test_command_line_example_11_recheck_empty_then_min_1(self):
        """Command Line example 11: a db with addresses but no seeds, and
        then the same db with --min 1.0; recheck gives exit 0 and empty
        stdout in the first case; in the second only the alerts with
        score exactly 1.0000.
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

    def test_command_line_example_12_report_twice_byte_identical(self):
        """Command Line example 12: the db of the backfill and an empty
        temp directory; report --out run twice gives exit 0 both times,
        stderr empty, stdout exactly two lines -- the html path then the
        json path -- and both files byte-identical between the two runs
        (Deterministic Output).
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

    def test_command_line_example_13_no_key_still_runs(self):
        """Command Line example 13: INFURA_API_KEY unset, no .env in the
        working directory, a db holding block 26077729; report,
        clusters top and recheck run with rpc=None give exit 0 each time
        and no RpcError, because infura_url() is never called outside
        listen and backfill.
        """
        self._fill_block()
        saved_key = os.environ.pop("INFURA_API_KEY", None)
        saved_cwd = os.getcwd()
        nodir = tempfile.mkdtemp(prefix="ethsc-noenv-judge-")
        os.chdir(nodir)
        try:
            for run, argv in enumerate((
                    ["--db", self.db, "report", "--out",
                     os.path.join(nodir, "r")],
                    ["--db", self.db, "clusters", "top"],
                    ["--db", self.db, "recheck"]), 1):
                code, out, err = self.run_main(argv, None)
                self.assertEqual(0, code,
                                 msg="subcommand %r exit code: got %r, want"
                                     " 0; stderr=%r" % (argv, code, err))
                self.assertNotIn("Traceback", out + err,
                                 msg="subcommand %r raised: stdout=%r"
                                     " stderr=%r" % (argv, out, err))
        finally:
            os.chdir(saved_cwd)
            if saved_key is not None:
                os.environ["INFURA_API_KEY"] = saved_key

    def test_command_line_example_14_report_without_matplotlib(self):
        """Command Line example 14: the same db and an import of
        ethsc.charts that raises ImportError; report gives exit 2,
        stdout empty, no file written, and stderr exactly one line
        naming matplotlib, with no traceback.
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

    def test_command_line_example_15_risk_listing_14_lines(self):
        """Command Line example 15: the db of the backfill (206
        addresses of block 26077729); risk run twice gives exit 0 both
        times and byte-identical stdout: 14 lines, the first
        "0x11b74d6995904232ad5cdf78b421f7bba1e8e646 mutable_delegatecall"
        and the last
        "0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc selfdestruct";
        stderr empty (13 addresses mutable_delegatecall + 1
        selfdestruct, no overlap; the block's standard EIP-1967 proxies
        are excluded by is_std_proxy -- it was 34 lines, first
        0x07696dcab55e..., before; Deterministic Output).
        """
        self._fill_block()
        code, out, err = self.run_main(["--db", self.db, "risk"], FakeRpc())
        self.assertEqual(0, code,
                         msg="risk exit code: got %r, want 0" % (code,))
        lines = out.splitlines()
        self.assertEqual(14, len(lines),
                         msg="risk line count: got %d, want 14"
                             % (len(lines),))
        self.assertEqual(
            "0x11b74d6995904232ad5cdf78b421f7bba1e8e646"
            "\tmutable_delegatecall",
            lines[0],
            msg="first risk line: got %r, want the mutable_delegatecall"
                " address" % (lines[0],))
        self.assertEqual(
            "0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc\tselfdestruct",
            lines[-1],
            msg="last risk line: got %r, want the selfdestruct address"
                % (lines[-1],))
        self.assertEqual("", err,
                         msg="risk stderr: got %r, want empty" % (err,))
        first = out
        code, out, err = self.run_main(["--db", self.db, "risk"], FakeRpc())
        self.assertEqual(0, code,
                         msg="second risk exit code: got %r, want 0"
                             % (code,))
        self.assertEqual(first, out,
                         msg="risk not byte-identical between the two runs:"
                             " first %r, second %r" % (first, out))
        self.assertEqual("", err,
                         msg="second risk stderr: got %r, want empty"
                             % (err,))

    def test_command_line_example_16_risk_flag_selfdestruct(self):
        """Command Line example 16: the same db; risk --flag
        selfdestruct gives exit 0 and exactly one line,
        "0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc\tselfdestruct"
        (the one code with a SELFDESTRUCT opcode in the block).
        """
        self._fill_block()
        code, out, err = self.run_main(
            ["--db", self.db, "risk", "--flag", "selfdestruct"], FakeRpc())
        self.assertEqual(0, code,
                         msg="risk --flag exit code: got %r, want 0"
                             % (code,))
        lines = out.splitlines()
        self.assertEqual(
            ["0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc\tselfdestruct"],
            lines,
            msg="risk --flag selfdestruct lines: got %r, want exactly the"
                " one selfdestruct line" % (lines,))
        self.assertEqual("", err,
                         msg="risk --flag stderr: got %r, want empty"
                             % (err,))

    def test_command_line_example_17_cluster_line_flags_field(self):
        """Command Line example 17: the same db; cluster
        0xe6b738da243e8fa2a0ed5915645789add5de5152 gives exit 0 and one
        line whose fourth tab field is "mutable_delegatecall": an L0
        cluster of two addresses 0xe6b738da243e8fa2a0ed5915645789add5de5152
        and 0xf40bcc0845528873784f36e5c105e62a93ff7021 sharing one code
        (two addresses of one non-proxy code that has DELEGATECALL and
        SLOAD and is no eip1167 and no standard proxy; the old example
        0x28b5a0e9... is now a standard proxy, no longer
        mutable_delegatecall).
        """
        self._fill_block()
        code, out, err = self.run_main(
            ["--db", self.db, "cluster",
             "0xe6b738da243e8fa2a0ed5915645789add5de5152"], FakeRpc())
        self.assertEqual(0, code,
                         msg="cluster exit code: got %r, want 0" % (code,))
        lines = out.splitlines()
        self.assertEqual(1, len(lines),
                         msg="cluster line count: got %r, want 1" % (lines,))
        fields = lines[0].split("\t")
        self.assertEqual(4, len(fields),
                         msg="cluster field count: got %r, want 4"
                             % (fields,))
        self.assertEqual("L0", fields[0],
                         msg="cluster level: got %r, want L0" % (fields[0],))
        self.assertEqual(
            "0xe6b738da243e8fa2a0ed5915645789add5de5152,"
            "0xf40bcc0845528873784f36e5c105e62a93ff7021",
            fields[2],
            msg="cluster members: got %r, want the two addresses"
                " comma-joined" % (fields[2],))
        self.assertEqual("mutable_delegatecall", fields[3],
                         msg="cluster flags field: got %r, want"
                             " mutable_delegatecall" % (fields[3],))

    def test_command_line_example_18_similar_lines_end_in_dash(self):
        """Command Line example 18: the same db; similar <pair> --min 0.8
        gives exit 0 and 4 lines, each ending in a "-" field (the flag
        column is always present; UniswapV2Pair has no SELFDESTRUCT and
        no DELEGATECALL opcode), the score still the field before it.
        """
        self._fill_block()
        code, out, err = self.run_main(
            ["--db", self.db, "similar", _PAIR, "--min", "0.8"], FakeRpc())
        self.assertEqual(0, code,
                         msg="similar exit code: got %r, want 0" % (code,))
        lines = out.splitlines()
        self.assertEqual(4, len(lines),
                         msg="similar line count: got %r, want 4"
                             % (lines,))
        want = ["%s\t1.0000\t-" % addr for addr in _SIMILAR_L0] + [
            "0xcf6daab95c476106eca715d48de4b13287ffdeaa\t0.8125\t-"]
        self.assertEqual(want, lines,
                         msg="similar lines: got %r, want %r"
                             % (lines, want))
        for line in lines:
            fields = line.split("\t")
            self.assertEqual(3, len(fields),
                             msg="field count of %r: got %d, want 3"
                                 % (line, len(fields)))
            self.assertEqual("-", fields[2],
                             msg="flag field of %r: got %r, want -"
                                 % (line, fields[2]))


if __name__ == "__main__":
    unittest.main()
