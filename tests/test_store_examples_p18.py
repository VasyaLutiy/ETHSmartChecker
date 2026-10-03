"""Judge tests for phase 18, group store: Manage Watchlist examples 6-8.

One unittest test per example, checking the example's "then" with the
exact values written in the Contour. The code under test is finished;
this file only calls it. All data comes from tests/fixtures/ through
tests/helpers.py; no test opens the network.
"""

import sqlite3
import unittest

try:
    from tests.helpers import load_hex, temp_store
except ImportError:  # pragma: no cover - direct execution fallback
    from helpers import load_hex, temp_store

from ethsc.store import ReadOnlyStoreError, Store

BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
BELLE_UPPER = "0x34C6211621F2763C60EB007DC2AE91090A2D22F6"
COPY_ADDR = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
OTHER_ADDR = "0x1111111111111111111111111111111111111111"


def _belle_store():
    """A fresh store holding code_belle.hex at BELLE (block 1), unseeded."""
    store = temp_store()
    code_id = store.put_code(load_hex("code_belle.hex"))
    store.put_address(BELLE, code_id, 1)
    return store


class TestManageWatchlistExample6(unittest.TestCase):
    """Example 6: strict flag set, kept across add_seed, cleared."""

    def test_example6_strict_flag_roundtrip(self):
        store = _belle_store()
        store.add_seed(BELLE, "BELLE honeypot")
        self.assertEqual(store.strict_seeds(), [])
        self.assertTrue(store.set_seed_strict(BELLE_UPPER, True))
        self.assertEqual(store.strict_seeds(), [BELLE])
        seeds = store.seeds()
        self.assertEqual(len(seeds), 1)
        self.assertEqual(sorted(seeds[0].keys()),
                         ["address", "code_id", "label"])
        self.assertEqual(seeds[0]["address"], BELLE)
        self.assertEqual(seeds[0]["label"], "BELLE honeypot")
        self.assertEqual(seeds[0]["code_id"],
                         "8571d00b598627ac40e1ae7bc4d0cb3fd5a77a0d663763fdf"
                         "c1cd9127b63cb4d")
        store.add_seed(BELLE, "BELLE again")
        self.assertEqual(store.strict_seeds(), [BELLE])
        self.assertEqual(store.seeds()[0]["label"], "BELLE again")
        self.assertTrue(store.set_seed_strict(BELLE, False))
        self.assertEqual(store.strict_seeds(), [])
        store.close()


class TestManageWatchlistExample7(unittest.TestCase):
    """Example 7: set_seed_strict creates no row; remove takes the flag."""

    def test_example7_no_row_created_remove_takes_flag(self):
        store = _belle_store()
        store.add_seed(BELLE, "BELLE honeypot")
        store.set_seed_strict(BELLE, True)
        copy_code_id = store.put_code(load_hex("code_belle_copy_1807090d.hex"))
        store.put_address(COPY_ADDR, copy_code_id, 1)
        self.assertFalse(store.set_seed_strict(COPY_ADDR, True))
        self.assertFalse(store.set_seed_strict(OTHER_ADDR, True))
        self.assertEqual(len(store.seeds()), 1)
        self.assertTrue(store.remove_seed(BELLE))
        store.add_seed(BELLE, "BELLE")
        self.assertEqual(store.strict_seeds(), [])
        store.close()


class TestManageWatchlistExample8(unittest.TestCase):
    """Example 8: a legacy_db(14) file, read-only then writable open."""

    def test_example8_legacy14_readonly_then_migrate(self):
        from tests import helpers as _helpers
        path = _helpers.legacy_db(14)
        ro = Store(path, readonly=True)
        try:
            self.assertEqual(ro.strict_seeds(), [])
            with self.assertRaises(ReadOnlyStoreError):
                ro.set_seed_strict(BELLE, True)
        finally:
            ro.close()
        writable = Store(path)
        try:
            self.assertEqual(writable.strict_seeds(), [])
            columns = [row[1] for row in writable._conn.execute(
                "PRAGMA table_info(seeds)").fetchall()]
        finally:
            writable.close()
        self.assertEqual(columns[-1], "strict")


if __name__ == "__main__":
    unittest.main()
