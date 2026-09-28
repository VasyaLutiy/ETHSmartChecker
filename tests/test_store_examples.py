"""Example-based tests for ethsc/store.py.

One test per example of the Functions Store Codes And Contracts,
Track Progress, Manage Watchlist and Budget Ledger in
docs/TASK_PHASE2.md (component `store`, Data Object `Code Database`),
checked against the fixtures in tests/fixtures/ (see
tests/fixtures/README.md). The author of this file is not the author
of ethsc/store.py.
"""

import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from ethsc.fingerprint import fingerprint
from ethsc.store import Store

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def read_code_hex(name):
    """Decode a `code_*.hex` fixture: verbatim `0x` + hex, no newline."""
    with open(os.path.join(FIXTURES, name), "r") as handle:
        text = handle.read().strip()
    return bytes.fromhex(text[2:])


def load_codes_block():
    """Load tests/fixtures/codes_26077729.json: {address: eth_getCode result}."""
    with open(os.path.join(FIXTURES, "codes_26077729.json"), "r") as handle:
        return json.load(handle)


class StoreCodesAndContractsExamples(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ethsc-store-examples-")
        self.path = os.path.join(self.tmpdir, "t.db")
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _univ2_addresses(self):
        """The block-26077729 addresses holding the UniswapV2Pair code.

        Store Codes And Contracts example 1 names four such addresses
        (0x22052a1a..., 0x2621cc0b..., 0x3041cbd3..., 0xb4e16d01...);
        they are found here by matching code_id against the fixture
        code_univ2_usdc_weth.hex, whose code is byte-identical to
        code_univ2_weth_usdt.hex (README).
        """
        univ2_code = read_code_hex("code_univ2_usdc_weth.hex")
        univ2_id = fingerprint(univ2_code)["code_id"]
        codes = load_codes_block()
        addresses = []
        for address, result in codes.items():
            if result == "0x":
                continue
            if fingerprint(bytes.fromhex(result[2:]))["code_id"] == univ2_id:
                addresses.append(address)
        return sorted(addresses), univ2_id

    def test_example_1_put_code_and_put_address_four_univ2_pairs(self):
        """Store Codes And Contracts example 1: four block-26077729
        addresses with code_id 8b5db55f... (UniswapV2Pair); put_code and
        put_address for each leave 1 row in codes, 4 in addresses, and
        addresses_of returns the four sorted."""
        addresses, code_id = self._univ2_addresses()
        self.assertEqual(
            len(addresses), 4,
            msg="the block fixture must hold exactly four UniswapV2Pair "
                "addresses, got {0}: {1!r}".format(len(addresses), addresses))
        code = read_code_hex("code_univ2_usdc_weth.hex")
        self.assertEqual(
            fingerprint(code)["code_id"], code_id,
            msg="the shared code_id of the four addresses must be the "
                "code_id of code_univ2_usdc_weth.hex")
        returned_id = self.store.put_code(code)
        self.assertEqual(
            returned_id, code_id,
            msg="put_code must return the fingerprint's code_id")
        for address in addresses:
            self.store.put_address(address, code_id, 26077729)
        counted = self.store._conn.execute(
            "SELECT COUNT(*) FROM codes").fetchone()[0]
        self.assertEqual(
            counted, 1,
            msg="put_code for the four identical codes must leave exactly "
                "1 row in codes, got {0}".format(counted))
        counted = self.store._conn.execute(
            "SELECT COUNT(*) FROM addresses").fetchone()[0]
        self.assertEqual(
            counted, 4,
            msg="put_address for four addresses must leave exactly 4 rows "
                "in addresses, got {0}".format(counted))
        self.assertEqual(
            self.store.addresses_of(code_id), sorted(addresses),
            msg="addresses_of must return the four UniswapV2Pair addresses "
                "sorted (ref: counted over codes_26077729.json)")

    def test_example_2_eoa_has_address_true_code_of_none(self):
        """Store Codes And Contracts example 2: an address stored with
        code_id None (an EOA, eth_getCode "0x"); has_address is True and
        code_of is None."""
        address = "0x22052a1a39b223fe8d0a0e5c4f27ead9083c756c1"
        self.store.put_address(address, None, 26077729)
        self.assertTrue(
            self.store.has_address(address),
            msg="has_address must be True for a stored EOA")
        self.assertIsNone(
            self.store.code_of(address),
            msg="code_of must be None for a stored EOA "
                "(eth_getCode returned '0x')")

    def test_example_3_reopened_db_returns_same_addresses(self):
        """Store Codes And Contracts example 3: after the db file is
        closed and reopened, addresses_of returns the same four
        addresses."""
        addresses, code_id = self._univ2_addresses()
        self.assertEqual(
            len(addresses), 4,
            msg="the block fixture must hold exactly four UniswapV2Pair "
                "addresses, got {0}: {1!r}".format(len(addresses), addresses))
        self.store.put_code(read_code_hex("code_univ2_usdc_weth.hex"))
        for address in addresses:
            self.store.put_address(address, code_id, 26077729)
        before = self.store.addresses_of(code_id)
        self.store.close()
        self.store = Store(self.path)
        after = self.store.addresses_of(code_id)
        self.assertEqual(
            after, before,
            msg="after close and reopen, addresses_of must return the same "
                "four addresses: {0!r}".format(before))


class TrackProgressExamples(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ethsc-store-examples-")
        self.path = os.path.join(self.tmpdir, "t.db")
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_example_1_progress_none_then_set_then_reopen(self):
        """Track Progress example 1: a fresh db reports None from
        get_progress; set_progress(26077729) makes get_progress return
        26077729; the reopened db still returns 26077729."""
        self.assertIsNone(
            self.store.get_progress(),
            msg="get_progress on a fresh temp db must be None")
        self.store.set_progress(26077729)
        self.assertEqual(
            self.store.get_progress(), 26077729,
            msg="get_progress after set_progress(26077729) must be 26077729")
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(
            self.store.get_progress(), 26077729,
            msg="get_progress after the db is reopened must still be "
                "26077729")


class ManageWatchlistExamples(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ethsc-store-examples-")
        self.path = os.path.join(self.tmpdir, "t.db")
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_example_1_add_seed_belle_twice_one_entry(self):
        """Manage Watchlist example 1: code_belle.hex stored at
        0x34c6211621f2763c60eb007dc2ae91090a2d22f6 (Etherscan: "This
        token is reported to be a honeypot token"); add_seed called twice
        leaves exactly one seed with label "BELLE honeypot" and the
        fingerprint's code_id."""
        address = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
        belle = read_code_hex("code_belle.hex")
        belle_id = self.store.put_code(belle)
        self.store.put_address(address, belle_id, 26077729)
        self.store.add_seed(address, "BELLE honeypot")
        self.store.add_seed(address, "BELLE honeypot")
        seeds = self.store.seeds()
        self.assertEqual(
            len(seeds), 1,
            msg="adding the same seed twice must keep exactly 1 entry, "
                "got {0}: {1!r}".format(len(seeds), seeds))
        self.assertEqual(
            seeds,
            [{"address": address, "label": "BELLE honeypot",
              "code_id": belle_id}],
            msg="the seed entry must hold the address, the label and the "
                "code_id of fingerprint(code_belle) "
                "(ref: Etherscan warning on the address, checked 2026-09-28)")

    def test_example_2_add_seed_unknown_address_raises_keyerror(self):
        """Manage Watchlist example 2: add_seed on an address that is not
        in the db raises KeyError."""
        with self.assertRaises(KeyError, msg="add_seed on an address that "
                "is not in the db must raise KeyError"):
            self.store.add_seed(
                "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                "BELLE honeypot")


class BudgetLedgerExamples(unittest.TestCase):

    maxDiff = None

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ethsc-store-examples-")
        self.path = os.path.join(self.tmpdir, "t.db")
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_example_1_spent_block_day_17480_other_day_0(self):
        """Budget Ledger example 1: spend("2026-09-28", "eth_getBlockReceipts",
        1000) once and spend("2026-09-28", "eth_getCode", 80) 206 times;
        spent("2026-09-28") is 17480 and spent("2026-09-29") is 0
        (ref: 206 candidates of block 26077729; prices 1000 and 80 from
        Infura's credit table)."""
        self.store.spend("2026-09-28", "eth_getBlockReceipts", 1000)
        for _ in range(206):
            self.store.spend("2026-09-28", "eth_getCode", 80)
        spent_block_day = self.store.spent("2026-09-28")
        self.assertEqual(
            spent_block_day, 17480,
            msg="spent('2026-09-28') must be 1000 + 80*206 = 17480, "
                "got {0!r}".format(spent_block_day))
        self.assertIs(
            type(spent_block_day), int,
            msg="spent must return an int")
        self.assertEqual(
            self.store.spent("2026-09-29"), 0,
            msg="spent('2026-09-29') must be 0 for a day with no entries")


if __name__ == "__main__":
    unittest.main()
