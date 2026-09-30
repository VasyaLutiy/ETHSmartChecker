"""Tests for the bulk-read methods Store.fingerprints and Store.code_by_id."""

import json
import os
import tempfile
import unittest

from ethsc.fingerprint import fingerprint
from ethsc.store import Store


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

THREE_FILES = [
    "code_weth9.hex",
    "code_clone_270df012.hex",
    "code_belle.hex",
]


def read_code(fname):
    """Decode a code_*.hex fixture into bytes."""
    path = os.path.join(FIXTURES, fname)
    text = open(path).read().strip()
    return bytes.fromhex(text[2:])


def load_block_codes():
    """The {address: code-or-None} map of codes_26077729.json."""
    path = os.path.join(FIXTURES, "codes_26077729.json")
    data = json.load(open(path))
    out = {}
    for address, value in data.items():
        if value == "0x":
            out[address] = None
        else:
            out[address] = bytes.fromhex(value[2:])
    return out


def make_store():
    """A fresh Store in a temporary directory."""
    return Store(os.path.join(tempfile.mkdtemp(), "t.db"))


class TestStoreRead(unittest.TestCase):
    maxDiff = None

    def test_empty_db_fingerprints(self):
        store = make_store()
        try:
            self.assertEqual(store.fingerprints(), [], "empty db gives []")
            self.assertIsNone(
                store.code_by_id("deadbeef"), "unknown id gives None")
        finally:
            store.close()

    def test_three_codes_reverse_order(self):
        codes = [read_code(fname) for fname in THREE_FILES]
        store = make_store()
        try:
            for code in reversed(codes):
                store.put_code(code)
            want = sorted(
                [fingerprint(c) for c in codes],
                key=lambda fp: fp["code_id"],
            )
            got = store.fingerprints()
            self.assertEqual(got, want, "fingerprints equal sorted list")
            self.assertEqual(len(got), 3, "three rows")
            # exactly the keys, and types
            for fp in got:
                self.assertEqual(
                    sorted(fp.keys()),
                    ["code_id", "proxy", "selectors", "size",
                     "skeleton_hash", "std_proxy"],
                    "exact keys",
                )
                self.assertIsInstance(fp["selectors"], list, "selectors list")
        finally:
            store.close()

    def test_clone_proxy_shape(self):
        clone = read_code("code_clone_270df012.hex")
        store = make_store()
        try:
            store.put_code(clone)
            fps = store.fingerprints()
            self.assertEqual(len(fps), 1, "one row")
            proxy = fps[0]["proxy"]
            self.assertIsNotNone(proxy, "clone has a proxy")
            self.assertEqual(
                sorted(proxy.keys()), ["kind", "target"], "proxy keys")
        finally:
            store.close()

    def test_code_by_id_round_trip(self):
        weth = read_code("code_weth9.hex")
        belle = read_code("code_belle.hex")
        store = make_store()
        try:
            id_weth = store.put_code(weth)
            id_belle = store.put_code(belle)
            self.assertEqual(
                store.code_by_id(id_weth), weth, "weth round trip")
            self.assertEqual(
                store.code_by_id(id_belle), belle, "belle round trip")
        finally:
            store.close()

    def test_repeated_put_code_no_duplicate(self):
        weth = read_code("code_weth9.hex")
        store = make_store()
        try:
            first = store.put_code(weth)
            second = store.put_code(weth)
            self.assertEqual(first, second, "same code_id twice")
            self.assertEqual(len(store.fingerprints()), 1, "one row only")
        finally:
            store.close()

    def test_survives_close_and_reopen(self):
        codes = [read_code(fname) for fname in THREE_FILES]
        path = os.path.join(tempfile.mkdtemp(), "t.db")
        store = Store(path)
        stored = []
        for code in reversed(codes):
            stored.append((store.put_code(code), code))
        store.close()
        store2 = Store(path)
        try:
            self.assertEqual(
                len(store2.fingerprints()), 3, "three rows after reopen")
            for code_id, code in stored:
                self.assertEqual(
                    store2.code_by_id(code_id), code, "code survives reopen")
        finally:
            store2.close()

    def test_block_26077729(self):
        store = make_store()
        try:
            codes = load_block_codes()
            for address, code in codes.items():
                code_id = None
                if code is not None:
                    code_id = store.put_code(code)
                store.put_address(address, code_id, 26077729)
            fps = store.fingerprints()
            self.assertEqual(len(fps), 130, "130 distinct codes")
            proxies = [fp for fp in fps if fp["proxy"] is not None]
            self.assertEqual(len(proxies), 12, "12 proxies")
            ids = [fp["code_id"] for fp in fps]
            self.assertEqual(ids, sorted(ids), "sorted by code_id")
            # spot check: the USDC/WETH pair's fingerprint matches its code
            pair_code = codes["0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"]
            pair_fp = fingerprint(pair_code)
            self.assertIn(pair_fp, fps, "pair fingerprint present")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
