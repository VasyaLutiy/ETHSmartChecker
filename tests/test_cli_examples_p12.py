"""Judge for the phase-12 examples: Command Line 28-35, Manage Watchlist 3-4.

One test per example, asserting every value its 'then' states: exit
codes, full stdout/stderr, the recorded rpc calls and the store rows
left behind. Offline: FakeRpc and load_hex come from tests/helpers.py,
no stub class is defined here, no network module is imported, and
every db lives in its own tempfile.mkdtemp() directory.
"""

import contextlib
import datetime
import io
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from ethsc.cli import main
from ethsc.rpc import RpcError
from ethsc.store import Store
from tests.helpers import FakeRpc, load_hex, temp_store

_BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_BELLE_MIXED_CASE = "0x34C6211621F2763C60EB007DC2AE91090A2D22F6"
_EOA = "0x023697eda1dfbe331c2cf791ef2f6089e73e3230"
_BLOCK = 26077729
_HEAD = "0x18dea21"

# The four BELLE copies, sorted ascending by address (also their
# "given" order in the contour example).
_COPIES = (
    ("0x1807090dd15a6f58e00fd769e32ebf20ee610385",
     "code_belle_copy_1807090d.hex"),
    ("0x2141be5f2afa674c94167ab167a478a56cb539f5",
     "code_belle_copy_2141be5f.hex"),
    ("0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a",
     "code_belle_copy_46cadea5.hex"),
    ("0x6411bed82614b91ef655d82486e0bd3a13d2eb8c",
     "code_belle_copy_6411bed8.hex"),
)


def _db_path():
    directory = tempfile.mkdtemp(prefix="ethsc-p12-judge-")
    return os.path.join(directory, "ethsc.sqlite")


def _no_key():
    """A started patcher whose environment has no INFURA_API_KEY."""
    patcher = mock.patch.dict(os.environ)
    environ = patcher.start()
    environ.pop("INFURA_API_KEY", None)
    return patcher


def _run(argv, rpc=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, rpc=rpc)
    return code, out.getvalue(), err.getvalue()


def _today():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def _address_block(path, address):
    """The stored block of address, read directly (no private attribute)."""
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT block FROM addresses WHERE address = ?",
            (address.lower(),),
        ).fetchone()
        return None if row is None else row[0]
    finally:
        conn.close()


def _store_belle_copies(db):
    """A db holding the four BELLE copies at _BLOCK, no seed."""
    store = Store(db)
    try:
        for address, fixture in _COPIES:
            code_id = store.put_code(load_hex(fixture))
            store.put_address(address, code_id, _BLOCK)
    finally:
        store.close()


def _copies_alert_lines(label):
    return "".join(
        "ALERT\t%s\t%s\t%s\t0.8667\n" % (address, _BELLE, label)
        for address, _ in _COPIES
    )


class _RecorderClient(object):
    """A stand-in for ethsc.cli.RpcClient: records, returns a fixed rpc."""

    def __init__(self, rpc):
        self._rpc = rpc
        self.calls = []

    def __call__(self, url, prices=None, max_retries=None):
        self.calls.append((url, prices, max_retries))
        return self._rpc


class TestCliExamplesP12(unittest.TestCase):

    def test_command_line_example_28_seed_add_fetch_new_contract_alerts(self):
        """Command Line 28: --fetch stores BELLE, alerts the four copies."""
        db = _db_path()
        _store_belle_copies(db)
        belle_text = "0x" + load_hex("code_belle.hex").hex()
        fake = FakeRpc(codes={_BELLE: belle_text}, head=_HEAD)
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", _BELLE_MIXED_CASE,
             "--label", "BELLE honeypot"],
            rpc=fake,
        )
        self.assertEqual(code, 0, msg="example 28: exit code, stderr %r" % err)
        self.assertEqual(err, "", msg="example 28: stderr not empty")
        self.assertEqual(
            out, _copies_alert_lines("BELLE honeypot"),
            msg="example 28: unexpected stdout %r" % out,
        )
        self.assertEqual(
            fake.calls,
            [("eth_blockNumber", []),
             ("eth_getCode", [_BELLE, "latest"])],
            msg="example 28: unexpected rpc calls %r" % (fake.calls,),
        )
        self.assertEqual(
            _address_block(db, _BELLE), _BLOCK,
            msg="example 28: address not stored with block %d" % _BLOCK,
        )
        store = Store(db)
        try:
            self.assertEqual(
                store.code_of(_BELLE), load_hex("code_belle.hex"),
                msg="example 28: stored code does not match the fixture",
            )
            seeds = store.seeds()
            self.assertEqual(len(seeds), 1, msg="example 28: seeds() count")
            self.assertEqual(seeds[0]["address"], _BELLE,
                             msg="example 28: seed address")
            self.assertEqual(seeds[0]["label"], "BELLE honeypot",
                             msg="example 28: seed label")
            self.assertEqual(store.spent(_today()), 0,
                             msg="example 28: ledger of today")
        finally:
            store.close()

    def test_command_line_example_29_seed_add_fetch_stored_no_rpc(self):
        """Command Line 29: --fetch on a stored address makes no rpc call."""
        db = _db_path()
        _store_belle_copies(db)
        belle_text = "0x" + load_hex("code_belle.hex").hex()
        first_fake = FakeRpc(codes={_BELLE: belle_text}, head=_HEAD)
        first_code, _, _ = _run(
            ["--db", db, "seed", "add", "--fetch", _BELLE_MIXED_CASE,
             "--label", "BELLE honeypot"],
            rpc=first_fake,
        )
        self.assertEqual(first_code, 0, msg="example 29: first add exit code")

        second_fake = FakeRpc(fail=AssertionError("no rpc"))
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", _BELLE_MIXED_CASE,
             "--label", "BELLE again"],
            rpc=second_fake,
        )
        self.assertEqual(code, 0, msg="example 29: exit code, stderr %r" % err)
        self.assertEqual(
            out, _copies_alert_lines("BELLE again"),
            msg="example 29: unexpected stdout %r" % out,
        )
        self.assertEqual(second_fake.calls, [],
                         msg="example 29: rpc was called")
        store = Store(db)
        try:
            seeds = store.seeds()
            self.assertEqual(len(seeds), 1, msg="example 29: seeds() count")
            self.assertEqual(seeds[0]["label"], "BELLE again",
                             msg="example 29: seed label")
        finally:
            store.close()

    def test_command_line_example_30_seed_add_fetch_eoa_no_code_twice(self):
        """Command Line 30: an EOA ("0x") is stored and refused, twice."""
        db = _db_path()
        first_fake = FakeRpc(codes={_EOA: "0x"}, head=_HEAD)
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", _EOA, "--label", "L"],
            rpc=first_fake,
        )
        self.assertEqual(code, 2, msg="example 30: first exit code")
        self.assertEqual(out, "", msg="example 30: first stdout not empty")
        self.assertEqual(
            err, "unknown address or no code: %s\n" % _EOA,
            msg="example 30: first stderr %r" % err,
        )
        store = Store(db)
        try:
            self.assertTrue(store.has_address(_EOA),
                            msg="example 30: EOA not stored")
            self.assertIsNone(store.code_of(_EOA),
                             msg="example 30: EOA has code")
            self.assertEqual(store.seeds(), [],
                             msg="example 30: seeds() not empty")
        finally:
            store.close()
        self.assertEqual(
            _address_block(db, _EOA), _BLOCK,
            msg="example 30: address row has the wrong block",
        )

        second_fake = FakeRpc(fail=AssertionError("no rpc"))
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", _EOA, "--label", "L"],
            rpc=second_fake,
        )
        self.assertEqual(code, 2, msg="example 30: second exit code")
        self.assertEqual(out, "", msg="example 30: second stdout not empty")
        self.assertEqual(
            err, "unknown address or no code: %s\n" % _EOA,
            msg="example 30: second stderr %r" % err,
        )
        self.assertEqual(second_fake.calls, [],
                         msg="example 30: second fake was called")

    def test_command_line_example_31_seed_add_fetch_rpc_error(self):
        """Command Line 31: an RpcError on the first call exits 1."""
        db = _db_path()
        fake = FakeRpc(fail=RpcError(-32000, "header not found"))
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", _BELLE, "--label", "L"],
            rpc=fake,
        )
        self.assertEqual(code, 1, msg="example 31: exit code")
        self.assertEqual(out, "", msg="example 31: stdout not empty")
        self.assertEqual(err, "header not found\n",
                         msg="example 31: stderr %r" % err)
        self.assertEqual(len(fake.calls), 1, msg="example 31: call count")
        self.assertEqual(fake.calls[0][0], "eth_blockNumber",
                         msg="example 31: recorded method")
        store = Store(db)
        try:
            counts = store.counts()
            self.assertEqual(counts["addresses"], 0,
                             msg="example 31: addresses count")
            self.assertEqual(counts["codes"], 0, msg="example 31: codes count")
            self.assertEqual(store.seeds(), [], msg="example 31: seeds count")
        finally:
            store.close()

    def test_command_line_example_32_seed_add_fetch_bad_code_answer(self):
        """Command Line 32: a null or odd-length code answer exits 1."""
        for bad_answer in (None, "0x123"):
            db = _db_path()
            fake = FakeRpc(codes={_BELLE: bad_answer}, head=_HEAD)
            code, out, err = _run(
                ["--db", db, "seed", "add", "--fetch", _BELLE,
                 "--label", "L"],
                rpc=fake,
            )
            self.assertEqual(
                code, 1, msg="example 32: exit code for %r" % (bad_answer,))
            self.assertEqual(
                out, "",
                msg="example 32: stdout for %r" % (bad_answer,))
            self.assertEqual(
                err, "eth_getCode returned no code: %s\n" % _BELLE,
                msg="example 32: stderr for %r is %r" % (bad_answer, err),
            )
            store = Store(db)
            try:
                counts = store.counts()
                self.assertEqual(
                    counts["addresses"], 0,
                    msg="example 32: addresses count for %r" % (bad_answer,))
                self.assertEqual(
                    counts["codes"], 0,
                    msg="example 32: codes count for %r" % (bad_answer,))
                self.assertEqual(
                    store.seeds(), [],
                    msg="example 32: seeds for %r" % (bad_answer,))
            finally:
                store.close()

    def test_command_line_example_33_seed_add_fetch_publicnode_keyless(self):
        """Command Line 33: the public node client is built once, keyless."""
        patcher = _no_key()
        try:
            belle_text = "0x" + load_hex("code_belle.hex").hex()
            fake = FakeRpc(codes={_BELLE: belle_text}, head=_HEAD)
            recorder = _RecorderClient(fake)
            url_mock = mock.MagicMock(side_effect=AssertionError)
            db = _db_path()
            with mock.patch("ethsc.cli.RpcClient", recorder):
                with mock.patch("ethsc.cli.infura_url", url_mock):
                    first_code, _, _ = _run(
                        ["--db", db, "seed", "add", "--fetch", _BELLE,
                         "--label", "BELLE honeypot"])
                    second_code, _, _ = _run(
                        ["--db", db, "seed", "add", "--fetch", _BELLE,
                         "--label", "x"])
                    db2 = _db_path()
                    third_code, _, _ = _run(
                        ["--db", db2, "seed", "add", _BELLE, "--label", "x"])
            self.assertEqual(first_code, 0, msg="example 33: first exit code")
            self.assertEqual(second_code, 0,
                             msg="example 33: second exit code")
            self.assertEqual(third_code, 2, msg="example 33: third exit code")
            self.assertEqual(len(recorder.calls), 1,
                             msg="example 33: RpcClient construction count")
            url, prices, retries = recorder.calls[0]
            self.assertEqual(
                url, "https://ethereum-rpc.publicnode.com",
                msg="example 33: url")
            self.assertEqual(prices, {}, msg="example 33: prices")
            self.assertEqual(retries, 5, msg="example 33: max_retries")
            self.assertEqual(url_mock.call_count, 0,
                             msg="example 33: infura_url was called")
        finally:
            patcher.stop()

    def test_command_line_example_34_seed_remove_then_recheck(self):
        """Manage Watchlist 3 / Command Line 34: remove, recheck, re-seed."""
        db = _db_path()
        store = Store(db)
        try:
            code_id = store.put_code(load_hex("code_belle.hex"))
            store.put_address(_BELLE, code_id, _BLOCK)
            store.add_seed(_BELLE, "BELLE honeypot")
            for address, fixture in _COPIES:
                copy_id = store.put_code(load_hex(fixture))
                store.put_address(address, copy_id, _BLOCK)
        finally:
            store.close()

        fake = FakeRpc()
        code, out, err = _run(
            ["--db", db, "seed", "remove", _BELLE_MIXED_CASE], rpc=fake)
        self.assertEqual(code, 0, msg="example 34: remove exit code")
        self.assertEqual(out, "", msg="example 34: remove stdout")
        self.assertEqual(err, "", msg="example 34: remove stderr")

        code, out, err = _run(["--db", db, "recheck"], rpc=fake)
        self.assertEqual(code, 0, msg="example 34: recheck exit code")
        self.assertEqual(out, "", msg="example 34: recheck stdout")

        code, out, err = _run(
            ["--db", db, "seed", "remove", _BELLE_MIXED_CASE], rpc=fake)
        self.assertEqual(code, 2, msg="example 34: second remove exit code")
        self.assertEqual(out, "", msg="example 34: second remove stdout")
        self.assertEqual(
            err, "not a seed: %s\n" % _BELLE_MIXED_CASE,
            msg="example 34: second remove stderr %r" % err,
        )
        self.assertEqual(fake.calls, [], msg="example 34: rpc was called")

        store = Store(db)
        try:
            counts = store.counts()
            self.assertEqual(counts["addresses"], 5,
                             msg="example 34: addresses count")
            self.assertEqual(counts["codes"], 5, msg="example 34: codes count")
        finally:
            store.close()

        code, out, err = _run(
            ["--db", db, "seed", "add", _BELLE, "--label", "BELLE honeypot"],
            rpc=fake,
        )
        self.assertEqual(code, 0, msg="example 34: re-add exit code")
        self.assertEqual(
            out, _copies_alert_lines("BELLE honeypot"),
            msg="example 34: re-add stdout %r" % out,
        )

    def test_command_line_example_35_seed_remove_invalid_address(self):
        """Command Line 35: an invalid address is a usage error, no rpc."""
        db = _db_path()
        code, out, err = _run(["--db", db, "seed", "remove", "0x12"])
        self.assertEqual(code, 2, msg="example 35: remove exit code")
        self.assertEqual(out, "", msg="example 35: remove stdout")
        self.assertEqual(len(err.strip().split("\n")), 1,
                         msg="example 35: remove stderr not one line: %r" % err)

        fake = FakeRpc(fail=AssertionError("no rpc"))
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", "0x12", "--label", "L"],
            rpc=fake,
        )
        self.assertEqual(code, 2, msg="example 35: add exit code")
        self.assertEqual(out, "", msg="example 35: add stdout")
        self.assertEqual(len(err.strip().split("\n")), 1,
                         msg="example 35: add stderr not one line: %r" % err)
        self.assertEqual(fake.calls, [], msg="example 35: rpc was called")

    def test_manage_watchlist_example_3_remove_seed_keeps_code_and_address(
        self,
    ):
        """Manage Watchlist 3: remove_seed keeps the code and address rows."""
        store = temp_store()
        try:
            code_id = store.put_code(load_hex("code_belle.hex"))
            store.put_address(_BELLE, code_id, _BLOCK)
            store.add_seed(_BELLE, "BELLE honeypot")

            first = store.remove_seed(_BELLE_MIXED_CASE)
            self.assertIs(first, True, msg="example 3: first remove_seed")
            self.assertEqual(store.seeds(), [], msg="example 3: seeds()")
            self.assertTrue(store.has_address(_BELLE),
                            msg="example 3: has_address after remove")
            self.assertEqual(
                store.code_of(_BELLE), load_hex("code_belle.hex"),
                msg="example 3: code_of after remove",
            )

            second = store.remove_seed(_BELLE_MIXED_CASE)
            self.assertIs(second, False, msg="example 3: second remove_seed")

            store.add_seed(_BELLE, "BELLE again")
            seeds = store.seeds()
            self.assertEqual(len(seeds), 1, msg="example 3: seeds() count")
            self.assertEqual(seeds[0]["label"], "BELLE again",
                             msg="example 3: re-seeded label")
        finally:
            store.close()

    def test_manage_watchlist_example_4_remove_seed_unknown_or_unseeded(self):
        """Manage Watchlist 4: remove_seed is False, never raises, no-op."""
        fresh_store = temp_store()
        try:
            result = fresh_store.remove_seed(_BELLE)
            self.assertIs(result, False,
                         msg="example 4: remove_seed on an unknown address")
        finally:
            fresh_store.close()

        store = temp_store()
        try:
            code_id = store.put_code(load_hex("code_belle.hex"))
            store.put_address(_BELLE, code_id, _BLOCK)
            before = store.counts()
            result = store.remove_seed(_BELLE)
            self.assertIs(
                result, False,
                msg="example 4: remove_seed on a stored, unseeded address",
            )
            after = store.counts()
            self.assertEqual(
                before["addresses"], after["addresses"],
                msg="example 4: addresses count changed",
            )
            self.assertEqual(
                before["codes"], after["codes"],
                msg="example 4: codes count changed",
            )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
