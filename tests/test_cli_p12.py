"""Smoke tests for the phase-12 CLI: seed add --fetch and seed remove.

Smoke only, four tests: the --fetch happy path that stores a contract
not in the base, the --fetch EOA refusal, and seed remove keeping the
code and address rows. Completeness lives in the acceptance probe and
the judge card. Every stub is imported from tests/helpers.py; no
network anywhere; every db lives in its own tempfile.mkdtemp()
directory.
"""

import contextlib
import io
import os
import tempfile
import unittest

from ethsc.cli import main
from ethsc.store import Store
from tests.helpers import FakeRpc, load_hex

_BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_EOA = "0x023697eda1dfbe331c2cf791ef2f6089e73e3230"


def _db_path():
    directory = tempfile.mkdtemp(prefix="ethsc-p12-")
    return os.path.join(directory, "ethsc.sqlite")


def _run(argv, rpc=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, rpc=rpc)
    return code, out.getvalue(), err.getvalue()


class CliP12Smoke(unittest.TestCase):

    def test_seed_add_fetch_new_contract(self):
        """Command Line 28: --fetch stores and seeds a fresh contract."""
        db = _db_path()
        belle_text = "0x" + load_hex("code_belle.hex").hex()
        rpc = FakeRpc(codes={_BELLE: belle_text}, head="0x18dea21")
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", _BELLE,
             "--label", "BELLE honeypot"],
            rpc=rpc,
        )
        self.assertEqual(code, 0, msg="exit %d, stderr %r" % (code, err))
        self.assertEqual(err, "", msg="stderr not empty")
        self.assertEqual(
            rpc.calls,
            [("eth_blockNumber", []), ("eth_getCode", [_BELLE, "latest"])],
            msg="unexpected rpc calls %r" % (rpc.calls,),
        )
        store = Store(db)
        try:
            self.assertEqual(
                store.code_of(_BELLE), load_hex("code_belle.hex"),
                msg="stored code does not match the fixture",
            )
            self.assertEqual(
                [s["address"] for s in store.seeds()], [_BELLE],
                msg="seed not recorded",
            )
        finally:
            store.close()

    def test_seed_add_fetch_eoa(self):
        """Command Line 30: --fetch on an EOA answers exit 2, one line."""
        db = _db_path()
        rpc = FakeRpc(codes={_EOA: "0x"}, head="0x18dea21")
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", _EOA, "--label", "L"],
            rpc=rpc,
        )
        self.assertEqual(code, 2, msg="exit %d" % code)
        self.assertEqual(out, "", msg="stdout not empty")
        self.assertEqual(
            err, "unknown address or no code: %s\n" % _EOA,
            msg="unexpected stderr %r" % err,
        )
        store = Store(db)
        try:
            self.assertTrue(store.has_address(_EOA), msg="EOA not stored")
            self.assertIsNone(store.code_of(_EOA), msg="EOA has code")
        finally:
            store.close()

    def test_seed_remove(self):
        """Manage Watchlist 3 / Command Line 34: remove, then recheck."""
        db = _db_path()
        store = Store(db)
        try:
            code_id = store.put_code(load_hex("code_belle.hex"))
            store.put_address(_BELLE, code_id, 26077729)
            store.add_seed(_BELLE, "BELLE honeypot")
        finally:
            store.close()
        code, out, err = _run(["--db", db, "seed", "remove", _BELLE])
        self.assertEqual(code, 0, msg="exit %d, stderr %r" % (code, err))
        self.assertEqual(out, "", msg="stdout not empty")
        self.assertEqual(err, "", msg="stderr not empty")
        store = Store(db)
        try:
            self.assertEqual(store.seeds(), [], msg="seed still present")
            self.assertTrue(store.has_address(_BELLE),
                            msg="address row was deleted")
        finally:
            store.close()

    def test_seed_remove_twice(self):
        """Command Line 34: a second remove exits 2, "not a seed"."""
        db = _db_path()
        store = Store(db)
        try:
            code_id = store.put_code(load_hex("code_belle.hex"))
            store.put_address(_BELLE, code_id, 26077729)
            store.add_seed(_BELLE, "BELLE honeypot")
        finally:
            store.close()
        first = _run(["--db", db, "seed", "remove", _BELLE])
        second = _run(["--db", db, "seed", "remove", _BELLE])
        self.assertEqual(first[0], 0, msg="first remove exit %d" % first[0])
        self.assertEqual(
            second, (2, "", "not a seed: %s\n" % _BELLE),
            msg="second remove %r" % (second,),
        )


if __name__ == "__main__":
    unittest.main()
