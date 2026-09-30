"""Judge for the phase-10 Command Line examples: one test per example.

Offline: the rpc is a FakeRpc from tests/helpers, no network module is
imported, and every db lives in a tempfile.mkdtemp directory. The db is
read back through read-only sqlite3 row counts and value scans, so no
private store attribute is touched.
"""

import datetime
import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ethsc.cli import main
from ethsc.config import PRICES
from ethsc.store import Store
from tests.helpers import FakeRpc, temp_store


def _today():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def _no_key():
    """A started patcher whose environment has no INFURA_API_KEY."""
    patcher = mock.patch.dict(os.environ)
    environ = patcher.start()
    environ.pop("INFURA_API_KEY", None)
    return patcher


def _one_line(text):
    return text.strip().split("\n")


def _table_counts(path):
    """A {table: row count} map of the sqlite file at path."""
    conn = sqlite3.connect(path)
    try:
        names = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        return dict(
            (name, conn.execute(
                "SELECT COUNT(*) FROM '%s'" % name).fetchone()[0])
            for name in names)
    finally:
        conn.close()


def _db_has_value(path, value):
    """True when some cell of some table equals value (int or its text)."""
    conn = sqlite3.connect(path)
    try:
        names = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
        for name in names:
            for row in conn.execute("SELECT * FROM '%s'" % name):
                for cell in row:
                    if cell == value or cell == str(value):
                        return True
        return False
    finally:
        conn.close()


class _RecorderClient(object):
    """A stand-in for ethsc.cli.RpcClient: records, returns a FakeRpc."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, prices=None, max_retries=None):
        self.calls.append((url, prices, max_retries))
        return FakeRpc()


class _FollowRecorder(object):
    """A stand-in for ethsc.cli.follow_chain: records kwargs."""

    def __init__(self):
        self.kwargs = []

    def __call__(self, rpc, store, **kwargs):
        self.kwargs.append(kwargs)
        return {"blocks": 0, "stopped": None, "progress": None,
                "alerts": [], "day": "2026-09-30"}


class TestCliExamplesP10(unittest.TestCase):
    def test_command_line_21(self):
        """Command Line 21: publicnode backfill, keyless, code at latest."""
        patcher = _no_key()
        try:
            db = os.path.join(tempfile.mkdtemp(prefix="ethsc-p10-"),
                              "ethsc.sqlite")
            fake = FakeRpc()
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(["--db", db, "backfill", "--from", "26077729",
                             "--to", "26077729", "--source", "publicnode"],
                            rpc=fake)
            self.assertEqual(code, 0, msg="exit code")
            self.assertEqual(out.getvalue(), "", msg="stdout empty")
            self.assertEqual(err.getvalue(), "", msg="stderr empty")
            counts = _table_counts(db)
            self.assertIn(206, list(counts.values()), msg="206 addresses")
            self.assertIn(130, list(counts.values()), msg="130 codes")
            code_calls = [params for method, params in fake.calls
                          if method == "eth_getCode"]
            self.assertEqual(len(code_calls), 206, msg="getCode calls")
            for params in code_calls:
                self.assertEqual(params[1], "latest", msg="block param")
            store = Store(db)
            try:
                spent = store.spent(_today())
            finally:
                store.close()
            self.assertEqual(spent, 0, msg="spent today")
        finally:
            patcher.stop()

    def test_command_line_22(self):
        """Command Line 22: default backfill stays Infura, prices apply."""
        db = os.path.join(tempfile.mkdtemp(prefix="ethsc-p10-"),
                          "ethsc.sqlite")
        fake = FakeRpc()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--db", db, "backfill", "--from", "26077729",
                         "--to", "26077729"], rpc=fake)
        self.assertEqual(code, 0, msg="exit code")
        counts = _table_counts(db)
        self.assertIn(206, list(counts.values()), msg="206 addresses")
        self.assertIn(130, list(counts.values()), msg="130 codes")
        code_calls = [params for method, params in fake.calls
                      if method == "eth_getCode"]
        self.assertEqual(len(code_calls), 206, msg="getCode calls")
        for params in code_calls:
            self.assertEqual(params[1], "0x18dea21", msg="block param")
        store = Store(db)
        try:
            spent = store.spent(_today())
        finally:
            store.close()
        self.assertEqual(spent, 17560, msg="spent today")

    def test_command_line_23(self):
        """Command Line 23: --source resolution reaches follow_chain."""
        db = os.path.join(tempfile.mkdtemp(prefix="ethsc-p10-"),
                          "ethsc.sqlite")
        rec = _FollowRecorder()
        fake = FakeRpc()
        runs = (
            ["--db", db, "backfill", "--from", "26077729", "--to",
             "26077729"],
            ["--db", db, "backfill", "--from", "26077729", "--to",
             "26077729", "--source", "publicnode"],
            ["--db", db, "backfill", "--from", "26077729", "--to",
             "26077729", "--source", "publicnode", "--workers", "3"],
        )
        for argv in runs:
            out, err = io.StringIO(), io.StringIO()
            with mock.patch("ethsc.cli.follow_chain", rec):
                with redirect_stdout(out), redirect_stderr(err):
                    code = main(argv, rpc=fake)
            self.assertEqual(code, 0, msg="exit code for %s" % argv)
        self.assertEqual(len(rec.kwargs), 3, msg="three follow_chain calls")
        self.assertEqual(rec.kwargs[0]["workers"], 1, msg="workers infura")
        self.assertIsNone(rec.kwargs[0]["code_tag"], msg="tag infura")
        self.assertEqual(rec.kwargs[0]["prices"], PRICES, msg="prices infura")
        self.assertEqual(rec.kwargs[1]["workers"], 8, msg="workers default")
        self.assertEqual(rec.kwargs[1]["code_tag"], "latest",
                         msg="tag publicnode")
        self.assertEqual(rec.kwargs[1]["prices"], {}, msg="prices publicnode")
        self.assertEqual(rec.kwargs[2]["workers"], 3, msg="workers 3")
        self.assertEqual(rec.kwargs[2]["code_tag"], "latest", msg="tag 3")
        self.assertEqual(rec.kwargs[2]["prices"], {}, msg="prices 3")

    def test_command_line_24(self):
        """Command Line 24: publicnode client built keylessly in cli."""
        patcher = _no_key()
        try:
            db = os.path.join(tempfile.mkdtemp(prefix="ethsc-p10-"),
                              "ethsc.sqlite")
            recorder = _RecorderClient()
            url_mock = mock.MagicMock(side_effect=AssertionError)
            with mock.patch("ethsc.cli.RpcClient", recorder):
                with mock.patch("ethsc.cli.infura_url", url_mock):
                    out, err = io.StringIO(), io.StringIO()
                    with redirect_stdout(out), redirect_stderr(err):
                        code = main(
                            ["--db", db, "backfill", "--from", "26077729",
                             "--to", "26077729", "--source", "publicnode"])
            self.assertEqual(code, 0, msg="exit code")
            self.assertEqual(len(recorder.calls), 1, msg="one construction")
            url, prices, retries = recorder.calls[0]
            self.assertEqual(
                url, "https://ethereum-rpc.publicnode.com", msg="url")
            self.assertEqual(prices, {}, msg="prices")
            self.assertEqual(retries, 5, msg="max_retries")
            self.assertEqual(url_mock.call_count, 0, msg="infura_url unused")
        finally:
            patcher.stop()

    def test_command_line_25(self):
        """Command Line 25: --daily-budget with publicnode refused."""
        db = os.path.join(tempfile.mkdtemp(prefix="ethsc-p10-"),
                          "ethsc.sqlite")
        fake = FakeRpc()
        runs = (
            ["--db", db, "backfill", "--from", "26077729", "--to",
             "26077729", "--source", "publicnode", "--daily-budget",
             "3000000"],
            ["--db", db, "listen", "--source", "publicnode",
             "--daily-budget", "3000000"],
        )
        for argv in runs:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(argv, rpc=fake)
            self.assertEqual(code, 2, msg="exit code for %s" % argv)
            self.assertEqual(out.getvalue(), "", msg="stdout empty")
            self.assertEqual(len(_one_line(err.getvalue())), 1,
                             msg="one stderr line")
        self.assertEqual(fake.calls, [], msg="no rpc call")

    def test_command_line_26(self):
        """Command Line 26: --workers 0 and --source alchemy refused."""
        db = os.path.join(tempfile.mkdtemp(prefix="ethsc-p10-"),
                          "ethsc.sqlite")
        fake = FakeRpc()
        for argv in (
            ["--db", db, "backfill", "--from", "26077729", "--to",
             "26077729", "--workers", "0"],
            ["--db", db, "backfill", "--from", "26077729", "--to",
             "26077729", "--source", "alchemy"],
        ):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(argv, rpc=fake)
            self.assertEqual(code, 2, msg="exit code for %s" % argv)
            self.assertEqual(out.getvalue(), "", msg="stdout empty")
            self.assertEqual(len(_one_line(err.getvalue())), 1,
                             msg="one stderr line")
        self.assertEqual(fake.calls, [], msg="no rpc call")

    def test_command_line_27(self):
        """Command Line 27: null receipts on publicnode listen, exit 1."""
        db = os.path.join(temp_store().db_path
                          if hasattr(temp_store(), "db_path")
                          else os.path.join(
                              tempfile.mkdtemp(prefix="ethsc-p10-"),
                              "ethsc.sqlite"))
        setup = Store(db)
        setup.set_progress(26077728)
        self.assertTrue(_db_has_value(db, 26077728), msg="progress set")
        setup.close()
        fake = FakeRpc(null_receipts=True)
        sleeps = []
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--db", db, "listen", "--source", "publicnode"],
                        rpc=fake, sleep=sleeps.append)
        self.assertEqual(code, 1, msg="exit code")
        self.assertEqual(out.getvalue(), "", msg="stdout empty")
        lines = _one_line(err.getvalue())
        self.assertEqual(len(lines), 1, msg="one stderr line")
        self.assertIn("eth_getBlockReceipts returned null", lines[0],
                      msg="null message")
        self.assertNotIn("Traceback", err.getvalue(), msg="no traceback")
        self.assertTrue(_db_has_value(db, 26077728), msg="progress kept")
        self.assertFalse(_db_has_value(db, 26077729), msg="no new progress")
        self.assertEqual(sleeps, [], msg="sleep never called")
