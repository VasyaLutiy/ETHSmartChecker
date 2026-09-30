"""Smoke tests for phase 11: the std_proxy key, column and migration."""

import sqlite3
import tempfile
import unittest

from ethsc.fingerprint import fingerprint
from ethsc.store import Store

from tests.helpers import load_hex, temp_store


class TestStoreP11(unittest.TestCase):
    def test_fingerprint_has_std_proxy_key(self):
        fp = fingerprint(load_hex("code_proxy_seed_0c010533.hex"))
        self.assertTrue(fp["std_proxy"],
                        msg="the seed proxy must be a std proxy")
        self.assertEqual(len(fp), 6, msg="six keys exactly")
        self.assertFalse(fingerprint(load_hex("code_weth9.hex"))["std_proxy"],
                         msg="WETH9 is not a std proxy")

    def test_fresh_db_schema(self):
        store = temp_store()
        cols = [r[1] for r in store._conn.execute(
            "PRAGMA table_info(codes)")]
        self.assertEqual(
            cols[-1], "std_proxy",
            msg="std_proxy must be the last codes column")
        idx = [r[1] for r in store._conn.execute(
            "PRAGMA index_list(addresses)")]
        self.assertIn("addresses_code_id", idx,
                      msg="the addresses_code_id index must exist")

    def test_fingerprints_roundtrip(self):
        store = temp_store()
        code = load_hex("code_proxy_046eee2c.hex")
        code_id = store.put_code(code)
        fps = store.fingerprints()
        self.assertEqual(len(fps), 1, msg="one row")
        self.assertTrue(fps[0]["std_proxy"],
                        msg="std_proxy stored from the fingerprint")
        self.assertEqual(fps[0], fingerprint(code),
                         msg="fingerprints() equals fingerprint(code)")

    def test_migration_of_phase10_db(self):
        directory = tempfile.mkdtemp(prefix="ethsc-p11-")
        path = "%s/old.sqlite" % directory
        code = load_hex("code_proxy_seed_0c010533.hex")
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE codes (code_id TEXT PRIMARY KEY, size INTEGER,"
            " skeleton_hash TEXT, selectors TEXT, proxy_kind TEXT,"
            " proxy_target TEXT, code BLOB)")
        fp = fingerprint(code)
        conn.execute(
            "INSERT INTO codes VALUES (?, ?, ?, ?, ?, ?, ?)",
            (fp["code_id"], fp["size"], fp["skeleton_hash"],
             '["0x2e1a7d4d"]', None, None, sqlite3.Binary(code)))
        conn.commit()
        conn.close()
        store = Store(path)
        self.assertTrue(store.fingerprints()[0]["std_proxy"],
                        msg="the migration filled std_proxy")
        store.close()
        store2 = Store(path)
        self.assertTrue(store2.fingerprints()[0]["std_proxy"],
                        msg="reopening keeps the filled value")
        store2.close()


if __name__ == "__main__":
    unittest.main()
