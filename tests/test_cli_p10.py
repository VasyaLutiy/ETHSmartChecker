"""Smoke tests for the phase-10 CLI: --source and --workers.

Smoke only, five tests: the publicnode backfill at "latest" with an
empty ledger, the unchanged default infura backfill, the usage errors
(--daily-budget with publicnode, --workers 0), and the clean RpcError
exit on a null receipts answer under listen --source publicnode. Every
stub is imported from tests/helpers.py; no network anywhere.
"""

import contextlib
import io
import os
import tempfile
import unittest

from ethsc.config import PRICES
from ethsc.store import Store

from tests.helpers import FakeRpc, temp_store


def _db_path():
    directory = tempfile.mkdtemp(prefix="ethsc-p10-")
    return os.path.join(directory, "ethsc.sqlite")


def _run(argv, rpc=None, sleep=None):
    from ethsc.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, rpc=rpc, sleep=sleep)
    return code, out.getvalue(), err.getvalue()


class CliSourceSmoke(unittest.TestCase):

    def test_import(self):
        """import: ethsc.cli imports and knows the publicnode pieces."""
        import ethsc.cli

        self.assertTrue(hasattr(ethsc.cli, "main"), msg="no main")
        self.assertTrue(hasattr(ethsc.cli, "PUBLICNODE_URL"),
                        msg="no PUBLICNODE_URL import")

    def test_publicnode_backfill(self):
        """Command Line: publicnode backfill -- "latest", spent 0."""
        from tests.helpers import FakeRpc

        db = _db_path()
        rpc = FakeRpc()
        code, out, err = _run(
            ["--db", db, "backfill", "--from", "26077729",
             "--to", "26077729", "--source", "publicnode"],
            rpc=rpc,
        )
        self.assertEqual(code, 0, msg="exit %d, stderr %r" % (code, err))
        self.assertEqual(out, "", msg="stdout not empty")
        self.assertEqual(err, "", msg="stderr not empty")
        store = Store(db)
        try:
            counts = store.counts()
            self.assertEqual(counts["addresses"], 206, msg="addresses")
            self.assertEqual(counts["codes"], 130, msg="codes")
            self.assertEqual(store.spent("2026-09-30"), 0, msg="ledger")
        finally:
            store.close()
        code_calls = [p for m, p in rpc.calls if m == "eth_getCode"]
        self.assertEqual(len(code_calls), 206, msg="eth_getCode count")
        self.assertTrue(all(p[-1] == "latest" for p in code_calls),
                        msg="not all eth_getCode at latest")

    def test_default_backfill_infura(self):
        """Command Line: the default source stays infura -- hex block."""
        from tests.helpers import FakeRpc

        db = _db_path()
        rpc = FakeRpc()
        code, out, err = _run(
            ["--db", db, "backfill", "--from", "26077729",
             "--to", "26077729"],
            rpc=rpc,
        )
        self.assertEqual(code, 0, msg="exit %d, stderr %r" % (code, err))
        store = Store(db)
        try:
            self.assertEqual(store.counts()["addresses"], 206,
                             msg="addresses")
        finally:
            store.close()
        code_calls = [p for m, p in rpc.calls if m == "eth_getCode"]
        self.assertEqual(len(code_calls), 206, msg="eth_getCode count")
        self.assertTrue(all(p[-1] == "0x18dea21" for p in code_calls),
                        msg="not all eth_getCode at the block")

    def test_usage_errors(self):
        """Command Line: budget with publicnode and --workers 0 exit 2."""
        from tests.helpers import FakeRpc

        rpc = FakeRpc()
        for argv in (
            ["--db", _db_path(), "backfill", "--from", "26077729",
             "--to", "26077729", "--source", "publicnode",
             "--daily-budget", "1000"],
            ["--db", _db_path(), "listen", "--source", "publicnode",
             "--daily-budget", "1000"],
            ["--db", _db_path(), "backfill", "--from", "26077729",
             "--to", "26077729", "--workers", "0"],
        ):
            code, out, err = _run(argv, rpc=rpc)
            self.assertEqual(code, 2, msg="exit %d for %r" % (code, argv))
            self.assertEqual(out, "", msg="stdout not empty")
            lines = err.strip().splitlines()
            self.assertEqual(len(lines), 1, msg="stderr lines for %r"
                             % (argv,))
        self.assertEqual(rpc.calls, [], msg="rpc was called on a usage error")

    def test_listen_publicnode_null_receipts(self):
        """Command Line: null receipts under publicnode exit 1, one line."""
        from tests.helpers import FakeRpc

        calls = []

        def fake_sleep(_seconds):
            calls.append(_seconds)

        rpc = FakeRpc(null_receipts=True)
        code, out, err = _run(
            ["--db", _db_path(), "listen", "--source", "publicnode"],
            rpc=rpc,
            sleep=fake_sleep,
        )
        self.assertEqual(code, 1, msg="exit %d" % code)
        self.assertEqual(out, "", msg="stdout not empty")
        self.assertIn("eth_getBlockReceipts returned null", err,
                      msg="no null message on stderr")
        self.assertNotIn("Traceback", err, msg="traceback on stderr")
        self.assertEqual(len(err.strip().splitlines()), 1,
                         msg="stderr is not one line")
        self.assertEqual(calls, [], msg="sleep was called")
        self.assertTrue(any(m == "eth_blockNumber" for m, _ in rpc.calls),
                        msg="eth_blockNumber never called")
