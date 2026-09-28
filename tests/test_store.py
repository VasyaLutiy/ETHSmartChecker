"""Tests for ethsc.store: the four Functions of the store component.

Each test docstring names the example or rule of contour.yaml it
checks. All chain data comes from tests/fixtures; no network. Databases
live in temporary directories only.
"""

import json
import os
import sqlite3
import tempfile
import unittest

from ethsc.fingerprint import fingerprint
from ethsc.store import Store


def _fixture(name):
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "fixtures", name)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _code_bytes(name):
    text = _fixture(name)
    return bytes.fromhex(text.strip()[2:])


# The four addresses of block 26077729 whose code is the shared
# UniswapV2Pair code (code_id 8b5db55f...), per codes_26077729.json.
_PAIR_ADDRESSES = [
    "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
    "0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c",
    "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f",
    "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
]

_BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_BELLE_CODE_ID = fingerprint(_code_bytes("code_belle.hex"))["code_id"]


class StoreCodesAndContractsTest(unittest.TestCase):
    """Function Store Codes And Contracts, examples 1-3 and rules."""

    maxDiff = None

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "t.db")
        self.store = Store(self.path)
        self.univ2 = _code_bytes("code_univ2_usdc_weth.hex")
        self.code_id = fingerprint(self.univ2)["code_id"]
        self.assertTrue(
            self.code_id.startswith("8b5db55f"),
            msg="the UniswapV2Pair fixture code_id must be 8b5db55f...",
        )

    def tearDown(self):
        self.store.close()

    def test_example_1_four_addresses_one_code(self):
        """Ex.1: 4 addresses of one code -> 1 codes row, 4 addresses rows."""
        for address in _PAIR_ADDRESSES:
            got_id = self.store.put_code(self.univ2)
            self.assertEqual(
                got_id, self.code_id,
                msg="put_code must return the fingerprint code_id",
            )
            self.store.put_address(address, self.code_id, 26077729)
        second = sqlite3.connect(self.path)
        try:
            self.assertEqual(
                second.execute("SELECT COUNT(*) FROM codes").fetchone()[0],
                1,
                msg="codes table must have exactly 1 row",
            )
            self.assertEqual(
                second.execute("SELECT COUNT(*) FROM addresses").fetchone()[0],
                4,
                msg="addresses table must have exactly 4 rows",
            )
        finally:
            second.close()
        self.assertEqual(
            self.store.addresses_of(self.code_id),
            sorted(_PAIR_ADDRESSES),
            msg="addresses_of must return the 4 addresses sorted",
        )

    def test_example_2_eoa_address(self):
        """Ex.2: an address with code_id None -> has_address True,
        code_of None."""
        self.store.put_address(
            "0x00000000000000000000000000000000000000EA", None, 26077729
        )
        self.assertTrue(
            self.store.has_address("0x00000000000000000000000000000000000000EA"),
            msg="has_address must be True for a stored EOA",
        )
        self.assertIsNone(
            self.store.code_of("0x00000000000000000000000000000000000000EA"),
            msg="code_of must be None for an account without code",
        )

    def test_example_3_reopen(self):
        """Ex.3: db closed and reopened -> the same 4 addresses come back."""
        for address in _PAIR_ADDRESSES:
            self.store.put_address(address, self.code_id, 26077729)
        self.store.close()
        reopened = Store(self.path)
        try:
            self.assertEqual(
                reopened.addresses_of(self.code_id),
                sorted(_PAIR_ADDRESSES),
                msg="reopened store must return the same 4 addresses",
            )
        finally:
            reopened.close()

    def test_lowercase_and_mixed_case_lookup(self):
        """Rule: addresses are stored lowercase and found case-insensitively."""
        self.store.put_code(self.univ2)
        self.store.put_address(
            "0xB4E16D0168E52D35CACD2C6185B44281EC28C9DC", self.code_id, 1
        )
        row = sqlite3.connect(self.path).execute(
            "SELECT address FROM addresses"
        ).fetchone()
        self.assertEqual(
            row[0], _PAIR_ADDRESSES[3],
            msg="the stored address must be lowercase",
        )
        self.assertTrue(
            self.store.has_address(
                "0xB4E16D0168E52D35CaCD2c6185b44281Ec28C9Dc"
            ),
            msg="has_address must match any input case",
        )
        self.assertEqual(
            self.store.addresses_of(self.code_id),
            [_PAIR_ADDRESSES[3]],
            msg="addresses_of must return the lowercase address",
        )

    def test_put_code_repeat_is_noop(self):
        """Rule: put_code on a known code_id changes nothing, does not raise."""
        first = self.store.put_code(self.univ2)
        self.store.put_address(_PAIR_ADDRESSES[3], first, 1)
        again = self.store.put_code(self.univ2)
        self.assertEqual(
            again, first, msg="put_code must return the same code_id"
        )
        second = sqlite3.connect(self.path)
        try:
            self.assertEqual(
                second.execute("SELECT COUNT(*) FROM codes").fetchone()[0],
                1,
                msg="a repeat put_code must add no codes row",
            )
        finally:
            second.close()

    def test_put_address_repeat_first_wins(self):
        """Rule: put_address on a known address changes nothing (first wins)."""
        self.store.put_code(self.univ2)
        self.store.put_address(_PAIR_ADDRESSES[3], self.code_id, 111)
        self.store.put_address(_PAIR_ADDRESSES[3], None, 222)
        second = sqlite3.connect(self.path)
        try:
            rows = second.execute(
                "SELECT code_id, block FROM addresses WHERE address = ?",
                (_PAIR_ADDRESSES[3],),
            ).fetchall()
        finally:
            second.close()
        self.assertEqual(
            len(rows), 1, msg="a repeat put_address must add no row"
        )
        self.assertEqual(
            rows[0], (self.code_id, 111),
            msg="the first record must win",
        )

    def test_code_of_roundtrip_and_unknown(self):
        """Rule: code_of returns the stored bytes; unknown address -> None."""
        self.store.put_code(self.univ2)
        self.store.put_address(_PAIR_ADDRESSES[3], self.code_id, 1)
        self.assertEqual(
            self.store.code_of(_PAIR_ADDRESSES[3]), self.univ2,
            msg="code_of must return the stored code bytes",
        )
        self.assertIsNone(
            self.store.code_of("0x1234500000000000000000000000000000006789"),
            msg="code_of must be None for an unknown address",
        )

    def test_addresses_of_unknown_code_id(self):
        """Rule: addresses_of of an unknown code_id gives []."""
        self.assertEqual(
            self.store.addresses_of("ff" * 32),
            [],
            msg="addresses_of must give [] for an unknown code_id",
        )

    def test_code_row_schema_and_clone_proxy(self):
        """Rule: codes columns per PRAGMA; selectors JSON; proxy fields."""
        clone = _code_bytes("code_clone_270df012.hex")
        clone_id = self.store.put_code(clone)
        conn = sqlite3.connect(self.path)
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(codes)")]
            self.assertEqual(
                cols,
                ["code_id", "size", "skeleton_hash", "selectors",
                 "proxy_kind", "proxy_target", "code"],
                msg="codes columns must follow the Code Database schema",
            )
            row = conn.execute(
                "SELECT size, selectors, proxy_kind, proxy_target"
                " FROM codes WHERE code_id = ?", (clone_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(
            row[0], len(clone), msg="size must be the code length"
        )
        self.assertEqual(
            json.loads(row[1]), [],
            msg="selectors must be stored as a JSON list",
        )
        self.assertEqual(
            (row[2], row[3]),
            ("eip1167", "0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb"),
            msg="the clone's proxy kind and target must be stored",
        )


class TrackProgressTest(unittest.TestCase):
    """Function Track Progress, example 1."""

    maxDiff = None

    def test_example_1_set_get_reopen(self):
        """Ex.1: None, then 26077729, and 26077729 after the reopen."""
        path = os.path.join(tempfile.mkdtemp(), "t.db")
        store = Store(path)
        self.assertIsNone(
            store.get_progress(), msg="a fresh db must give None"
        )
        store.set_progress(26077729)
        self.assertEqual(
            store.get_progress(), 26077729,
            msg="set_progress must store the block",
        )
        store.close()
        reopened = Store(path)
        try:
            self.assertEqual(
                reopened.get_progress(), 26077729,
                msg="progress must survive the reopen",
            )
        finally:
            reopened.close()

    def test_set_progress_overwrites(self):
        """Rule: set_progress overwrites the stored block."""
        store = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
        try:
            store.set_progress(1)
            store.set_progress(26077729)
            self.assertEqual(
                store.get_progress(), 26077729,
                msg="set_progress must overwrite",
            )
        finally:
            store.close()


class ManageWatchlistTest(unittest.TestCase):
    """Function Manage Watchlist, examples 1-2 and rules."""

    maxDiff = None

    def setUp(self):
        self.store = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
        belle = _code_bytes("code_belle.hex")
        self.code_id = self.store.put_code(belle)
        self.assertEqual(
            self.code_id, _BELLE_CODE_ID,
            msg="the BELLE fixture code_id must equal the fingerprint",
        )
        self.store.put_address(_BELLE, self.code_id, 26077729)

    def tearDown(self):
        self.store.close()

    def test_example_1_add_seed_twice(self):
        """Ex.1: add_seed twice -> 1 entry, latest label, the BELLE code_id."""
        self.store.add_seed(_BELLE, "first label")
        self.store.add_seed(_BELLE, "BELLE honeypot")
        seeds = self.store.seeds()
        self.assertEqual(
            len(seeds), 1, msg="a repeat add_seed must keep one seed"
        )
        self.assertEqual(
            seeds[0],
            {"address": _BELLE, "label": "BELLE honeypot",
             "code_id": _BELLE_CODE_ID},
            msg="the seed must carry the latest label and the code_id",
        )

    def test_example_2_unknown_address_keyerror(self):
        """Ex.2: add_seed on an address not in the db raises KeyError."""
        try:
            self.store.add_seed(
                "0x9999999999999999999999999999999999999999", "nope"
            )
        except KeyError as exc:
            self.assertEqual(
                exc.args[0],
                "0x9999999999999999999999999999999999999999",
                msg="KeyError must carry the address",
            )
        else:
            self.fail(msg="add_seed on an unknown address must raise KeyError")

    def test_add_seed_eoa_keyerror(self):
        """Rule: add_seed on an address whose code_id is None raises KeyError."""
        self.store.put_address(
            "0x00000000000000000000000000000000000000EA", None, 1
        )
        try:
            self.store.add_seed(
                "0x00000000000000000000000000000000000000EA", "eoa"
            )
        except KeyError:
            pass
        else:
            self.fail(msg="add_seed on an EOA must raise KeyError")

    def test_seeds_sorted_by_address_reverse_insert(self):
        """Rule: seeds() is sorted by address regardless of insertion order."""
        code_ids = [
            self.store.put_code(_code_bytes("code_clone_270df012.hex")),
            self.store.put_code(_code_bytes("code_clone_2ca7b61b.hex")),
        ]
        addrs = [
            "0x270df01200e2f9fffd1c3d56f5b0a4b1c3eaaa5f",
            "0x2ca7b61b23b15e75ac7ab60dd6f627895d64a46e",
        ]
        for code_id, addr in zip(code_ids, addrs):
            self.store.put_address(addr, code_id, 1)
        # insert in reverse address order, mixed case
        self.store.add_seed(addrs[1].upper(), "LaunchToken impl")
        self.store.add_seed(addrs[0], "HolderDistributor impl")
        got = self.store.seeds()
        self.assertEqual(
            [s["address"] for s in got], sorted(addrs),
            msg="seeds() must be sorted by address",
        )
        self.assertEqual(
            sorted(s["label"] for s in got),
            ["HolderDistributor impl", "LaunchToken impl"],
            msg="both labels must be present",
        )


class BudgetLedgerTest(unittest.TestCase):
    """Function Budget Ledger, example 1."""

    maxDiff = None

    def test_example_1_spend_17480(self):
        """Ex.1: 1000 + 206*80 = 17480 on 2026-09-28; 0 on 2026-09-29."""
        store = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
        try:
            store.spend("2026-09-28", "eth_getBlockReceipts", 1000)
            for _ in range(206):
                store.spend("2026-09-28", "eth_getCode", 80)
            self.assertEqual(
                store.spent("2026-09-28"), 17480,
                msg="the day total must be 1000 + 206*80 = 17480",
            )
            self.assertIsInstance(
                store.spent("2026-09-29"), int,
                msg="spent must return an int",
            )
            self.assertEqual(
                store.spent("2026-09-29"), 0,
                msg="a day with no entries must give 0",
            )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
