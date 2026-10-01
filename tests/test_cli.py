"""Smoke tests for the ethsc CLI: exit codes and short output strings.

Completeness lives in the acceptance probe and the judge card; this
file only checks imports, one happy path per subcommand family, one
usage/tolerant case, and the phase 8/9 additions (the risk filter and
the fixed <flags> column of cluster and similar; the risk counts after
is_std_proxy dropped the standard proxies, and the cluster example on a
non-proxy L0 pair). Fakes and fixture loaders come from tests.helpers;
no network is opened.
"""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from ethsc.cli import main
from ethsc.rpc import RpcError
from ethsc.store import Store
from tests.helpers import (
    FakeRpc,
    InterruptAfter,
    block_codes,
    load_hex,
)

_PAIR = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
_BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_COPY = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"


def _run(argv, rpc, sleep=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, rpc=rpc, sleep=sleep)
    return code, out.getvalue(), err.getvalue()


def _fill(path):
    """Fill the db at path with every candidate of block 26077729."""
    store = Store(path)
    codes = block_codes()
    for address in sorted(codes):
        text = codes[address]
        if text == "0x":
            store.put_address(address, None, 26077729)
        else:
            store.put_address(
                address, store.put_code(bytes.fromhex(text[2:])), 26077729
            )
    store.close()


class _BoomStderr(object):
    """A stderr whose write raises KeyboardInterrupt (a Ctrl-C on I/O)."""

    def write(self, text):
        raise KeyboardInterrupt()

    def flush(self):
        pass


class CliSmoke(unittest.TestCase):
    def test_main_importable(self):
        """ethsc.cli.main is importable and callable."""
        self.assertTrue(callable(main), msg="ethsc.cli.main missing")

    def test_backfill_prints_alert(self):
        """Example 3: a backfill over a seeded db prints one ALERT line."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        store = Store(path)
        store.put_address(
            _BELLE, store.put_code(load_hex("code_belle.hex")), 1
        )
        store.add_seed(_BELLE, "BELLE honeypot")
        store.close()
        rpc = FakeRpc(
            codes={_COPY: "0x" + load_hex("code_belle_copy_1807090d.hex").hex()},
            receipts=[{"to": _COPY}],
        )
        code, out, err = _run(
            ["--db", path, "backfill", "--from", "26077729",
             "--to", "26077729"],
            rpc,
        )
        self.assertEqual(code, 0, msg="backfill exit %d, err=%r" % (code, err))
        self.assertEqual(
            out,
            "ALERT\t%s\t%s\tBELLE honeypot\t0.8667\tseen\n" % (_COPY, _BELLE),
            msg="alert line wrong",
        )

    def test_backfill_fills_db(self):
        """Example 1: backfill exit 0, db holds 206 addresses, 130 codes."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        code, out, err = _run(
            ["--db", path, "backfill", "--from", "26077729",
             "--to", "26077729"],
            FakeRpc(),
        )
        self.assertEqual(code, 0, msg="backfill exit %d, err=%r" % (code, err))
        store = Store(path)
        counts = store.counts()
        store.close()
        self.assertEqual(counts["addresses"], 206, msg="addresses stored")
        self.assertEqual(counts["codes"], 130, msg="codes stored")

    def test_read_commands(self):
        """Examples 2/17/18: clusters top, cluster and similar with flags."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        code, out, err = _run(["--db", path, "clusters", "top"], FakeRpc())
        self.assertEqual(code, 0, msg="clusters top exit")
        self.assertEqual(len(out.strip().splitlines()), 15,
                         msg="clusters top lines")
        code, out, err = _run(
            ["--db", path, "cluster", "0xe6b738da243e8fa2a0ed5915645789add5de5152"],
            FakeRpc(),
        )
        self.assertEqual(code, 0, msg="cluster exit")
        fields = out.strip().split("\t")
        self.assertEqual(len(fields), 4, msg="cluster field count")
        self.assertEqual(fields[-1], "mutable_delegatecall",
                         msg="cluster flags field")
        self.assertIn("0xf40bcc0845528873784f36e5c105e62a93ff7021", fields[2],
                      msg="cluster members")
        code, out, err = _run(
            ["--db", path, "similar", _PAIR, "--min", "0.8"], FakeRpc()
        )
        self.assertEqual(code, 0, msg="similar exit")
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 4, msg="similar lines")
        self.assertEqual(lines[-1].split("\t")[-2], "0.8125",
                         msg="similar last score")
        for line in lines:
            self.assertEqual(line.split("\t")[-1], "-",
                             msg="similar flags field: %r" % line)
        self.assertEqual(err, "", msg="stderr not empty")

    def test_risk_filter(self):
        """Examples 15/16: risk prints 14 lines; --flag filters to one."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        code, out, err = _run(["--db", path, "risk"], FakeRpc())
        self.assertEqual(code, 0, msg="risk exit")
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 14, msg="risk line count")
        self.assertEqual(lines[0],
                         "0x11b74d6995904232ad5cdf78b421f7bba1e8e646"
                         "\tmutable_delegatecall",
                         msg="risk first line")
        self.assertEqual(lines[-1],
                         "0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc"
                         "\tselfdestruct",
                         msg="risk last line")
        code, out2, err = _run(["--db", path, "risk"], FakeRpc())
        self.assertEqual(out2, out, msg="risk deterministic")
        code, out, err = _run(
            ["--db", path, "risk", "--flag", "selfdestruct"], FakeRpc()
        )
        self.assertEqual(code, 0, msg="risk --flag exit")
        self.assertEqual(
            out,
            "0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc\tselfdestruct\n",
            msg="risk --flag output",
        )
        code, out, err = _run(
            ["--db", path, "risk", "--flag", "mutable_delegatecall"], FakeRpc()
        )
        self.assertEqual(code, 0, msg="risk --flag mutable exit")
        self.assertEqual(len(out.strip().splitlines()), 13,
                         msg="risk --flag mutable line count")
        for line in out.strip().splitlines():
            self.assertEqual(line.split("\t")[-1], "mutable_delegatecall",
                             msg="risk --flag mutable field: %r" % line)
        self.assertEqual(err, "", msg="risk stderr")

    def test_usage_and_tolerant(self):
        """Usage errors exit 2; unknown cluster address prints nothing."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        code, out, err = _run(
            ["--db", path, "similar", "not-an-address"], FakeRpc()
        )
        self.assertEqual(code, 2, msg="bad address exit")
        self.assertEqual(out, "", msg="stdout on usage error")
        code, out, err = _run(["--db", path], FakeRpc())
        self.assertEqual(code, 2, msg="missing command exit")
        code, out, err = _run(
            ["--db", path, "cluster", "0x" + "11" * 20], FakeRpc()
        )
        self.assertEqual(code, 0, msg="unknown cluster addr exit")
        self.assertEqual(out, "", msg="unknown cluster addr output")

    def test_listen_interrupt(self):
        """Example 7: Ctrl-C in the sleep: exit 0, progress advanced."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        store = Store(path)
        store.set_progress(26077728)
        store.close()
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            raise KeyboardInterrupt()

        code, out, err = _run(
            ["--db", path, "listen"], FakeRpc(head="0x18dea21"),
            sleep=fake_sleep,
        )
        self.assertEqual(code, 0, msg="listen interrupt exit")
        self.assertEqual(sleeps, [12], msg="sleep calls")
        again = Store(path)
        progress = again.get_progress()
        again.close()
        self.assertEqual(progress, 26077729, msg="listen progress")

    def test_listen_interrupt_inside_ingest(self):
        """Example 6: Ctrl-C on the first eth_getCode: exit 0, no pause."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        store = Store(path)
        store.set_progress(26077728)
        store.close()

        class _InterruptingCodes(dict):
            def __getitem__(self, key):
                raise KeyboardInterrupt()

        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            return None

        code, out, err = _run(
            ["--db", path, "listen"],
            FakeRpc(codes=_InterruptingCodes(block_codes()),
                    head="0x18dea21"),
            sleep=fake_sleep,
        )
        self.assertEqual(code, 0, msg="interrupt inside ingest exit")
        self.assertEqual(err, "", msg="stderr on interrupt inside ingest")
        self.assertEqual(out, "", msg="stdout on interrupt inside ingest")
        self.assertEqual(sleeps, [], msg="sleep not reached after Ctrl-C")
        again = Store(path)
        progress = again.get_progress()
        again.close()
        self.assertEqual(progress, 26077728, msg="progress unchanged")

    def test_alert_survives_interrupted_pass(self):
        """Example 8: Ctrl-C on the next block's receipts: ALERT printed."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        store = Store(path)
        store.put_address(
            _BELLE, store.put_code(load_hex("code_belle.hex")), 1
        )
        store.add_seed(_BELLE, "BELLE honeypot")
        store.set_progress(26077728)
        store.close()
        rpc = InterruptAfter(
            FakeRpc(
                codes={
                    _COPY: "0x" + load_hex("code_belle_copy_1807090d.hex").hex()
                },
                receipts=[{"to": _COPY}],
                head="0x18dea22",
            ),
            3,
        )
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        code, out, err = _run(
            ["--db", path, "listen"], rpc, sleep=fake_sleep
        )
        self.assertEqual(code, 0, msg="interrupted listen exit")
        self.assertEqual(
            out,
            "ALERT\t%s\t%s\tBELLE honeypot\t0.8667\tseen\n" % (_COPY, _BELLE),
            msg="alert lost across interrupt",
        )
        self.assertEqual(err, "", msg="stderr on interrupted pass")
        self.assertEqual(sleeps, [], msg="sleep after interrupt")
        again = Store(path)
        progress = again.get_progress()
        again.close()
        self.assertEqual(progress, 26077729, msg="progress after interrupt")

    def test_interrupt_during_stop_line(self):
        """Ctrl-C while the stopped line is written: exit 0, no traceback."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with contextlib.redirect_stderr(_BoomStderr()):
                code = main(
                    ["--db", path, "backfill", "--from", "26077729",
                     "--to", "26077729", "--daily-budget", "79"],
                    FakeRpc(),
                )
        self.assertEqual(code, 0, msg="interrupt during stop line exit")
        self.assertEqual(out.getvalue(), "", msg="stdout on stop-line Ctrl-C")

    def test_recheck_and_seed_add(self):
        """Examples 9/10: recheck prints stored copies; seed add prints too."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        code, out, err = _run(
            ["--db", path, "seed", "add", _PAIR,
             "--label", "UniV2 pair seed"],
            FakeRpc(),
        )
        self.assertEqual(code, 0, msg="seed add exit %d, err=%r" % (code, err))
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 4, msg="seed add alert lines")
        self.assertEqual(lines[0].split("\t")[1],
                         "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
                         msg="seed add first alert address")
        self.assertEqual(lines[-1].split("\t")[4], "0.8125",
                         msg="seed add last score")
        code, out2, err = _run(["--db", path, "recheck"], FakeRpc())
        self.assertEqual(code, 0, msg="recheck exit")
        self.assertEqual(out2, out, msg="recheck output equals seed add")
        self.assertEqual(err, "", msg="recheck stderr")

    def test_recheck_empty(self):
        """Example 11: recheck without seeds: exit 0, no output anywhere."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        code, out, err = _run(["--db", path, "recheck"], FakeRpc())
        self.assertEqual(code, 0, msg="recheck no-seed exit")
        self.assertEqual(out, "", msg="recheck no-seed stdout")
        self.assertEqual(err, "", msg="recheck no-seed stderr")
        empty = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        code, out, err = _run(["--db", empty, "recheck"], FakeRpc())
        self.assertEqual(code, 0, msg="recheck empty-db exit")
        self.assertEqual(out, "", msg="recheck empty-db stdout")

    def test_seed_add_failure(self):
        """A failed seed add: exit 2, empty stdout, one stderr line."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        code, out, err = _run(
            ["--db", path, "seed", "add", "0x" + "11" * 20,
             "--label", "nothing"],
            FakeRpc(),
        )
        self.assertEqual(code, 2, msg="failed seed add exit")
        self.assertEqual(out, "", msg="failed seed add stdout")
        self.assertEqual(err.strip(),
                         "unknown address or no code: 0x%s" % ("11" * 20),
                         msg="failed seed add stderr")

    def test_rpc_error_exit_one(self):
        """Example 4: an RpcError out of listen exits 1, no traceback."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        code, out, err = _run(
            ["--db", path, "listen"],
            FakeRpc(fail=RpcError(-32005, "Too Many Requests")),
            sleep=lambda seconds: None,
        )
        self.assertEqual(code, 1, msg="rpc error exit")
        self.assertEqual(out, "", msg="rpc error stdout")
        self.assertEqual(err.strip(), "Too Many Requests",
                         msg="rpc error stderr line")

    def test_no_rpc_built_outside_listen_backfill(self):
        """Example 13: infura_url() is never called outside listen/backfill."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        prefix = os.path.join(tempfile.mkdtemp(), "r")
        with mock.patch("ethsc.cli.infura_url",
                        side_effect=AssertionError("infura_url called")):
            for argv in (
                ["--db", path, "report", "--out", prefix],
                ["--db", path, "clusters", "top"],
                ["--db", path, "recheck"],
            ):
                code, out, err = _run(argv, None)
                self.assertEqual(code, 0, msg="exit for %r" % argv)

    def test_report_writes_two_files(self):
        """Example 12: report prints html then json; runs are identical."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        prefix = os.path.join(tempfile.mkdtemp(), "r")
        code, out, err = _run(["--db", path, "report", "--out", prefix],
                              None)
        self.assertEqual(code, 0, msg="report exit %d, err=%r" % (code, err))
        self.assertEqual(err, "", msg="report stderr")
        self.assertEqual(
            out, "%s.html\n%s.json\n" % (prefix, prefix),
            msg="report stdout lines",
        )
        self.assertTrue(os.path.exists(prefix + ".html"),
                        msg="html file missing")
        self.assertTrue(os.path.exists(prefix + ".json"),
                        msg="json file missing")
        html1 = open(prefix + ".html", "rb").read()
        json1 = open(prefix + ".json", "rb").read()
        code2, out2, err2 = _run(["--db", path, "report", "--out", prefix],
                                 None)
        self.assertEqual(code2, 0, msg="report second run exit")
        self.assertEqual(open(prefix + ".html", "rb").read(), html1,
                         msg="html not byte-identical")
        self.assertEqual(open(prefix + ".json", "rb").read(), json1,
                         msg="json not byte-identical")

    def test_report_default_prefix_and_empty_db(self):
        """--out defaults to the relative name ethsc-report; empty db ok."""
        workdir = tempfile.mkdtemp()
        path = os.path.join(workdir, "ethsc.sqlite")
        here = os.getcwd()
        os.chdir(workdir)
        try:
            code, out, err = _run(["--db", path, "report"], None)
            self.assertEqual(code, 0, msg="report default exit %d, err=%r"
                             % (code, err))
            self.assertEqual(err, "", msg="report default stderr")
            self.assertEqual(
                out, "ethsc-report.html\nethsc-report.json\n",
                msg="report default stdout",
            )
            self.assertTrue(os.path.exists("ethsc-report.html"),
                            msg="default html file missing")
            self.assertTrue(os.path.exists("ethsc-report.json"),
                            msg="default json file missing")
        finally:
            os.chdir(here)

    def test_report_without_matplotlib(self):
        """Example 14: no matplotlib: exit 2, no file, one stderr line."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        prefix = os.path.join(tempfile.mkdtemp(), "r")
        with mock.patch("ethsc.report.importlib.import_module",
                        side_effect=ImportError("no matplotlib")):
            code, out, err = _run(
                ["--db", path, "report", "--out", prefix], None
            )
        self.assertEqual(code, 2, msg="report no-matplotlib exit")
        self.assertEqual(out, "", msg="report no-matplotlib stdout")
        self.assertEqual(len(err.strip().splitlines()), 1,
                         msg="one stderr line expected")
        self.assertIn("matplotlib", err, msg="stderr must name matplotlib")
        self.assertFalse(os.path.exists(prefix + ".html"),
                         msg="no html file without matplotlib")
        self.assertFalse(os.path.exists(prefix + ".json"),
                         msg="no json file without matplotlib")
