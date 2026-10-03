"""Judge: phase 18, group cluster -- the Contour examples of Interface
Hits (1-2), Match Watchlist (5) and Recheck Watchlist (12).

One test per example; the values are the ones written in contour.yaml,
measured 2026-10-03 over the belle_block_db() base of Interface Hits
example 1. Offline: the store comes from tests.helpers, the bytecode
from the fixtures; no network anywhere.
"""

import unittest

from ethsc import cluster
from ethsc.store import Store

from tests.helpers import belle_block_db, block_codes, load_hex

_BELLE_ADDR = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_BELLE_ID = "8571d00b598627ac40e1ae7bc4d0cb3fd5a77a0d663763fdfc1cd9127b63cb4d"
_DEPLOY_ID = (
    "ee3b081294ee0f2f1804d8aa0204848d1d0f58efe81fae42998e81f1170c9ef9")
_SHIB_ADDR = "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce"
_COPY_ADDRS = [
    "0x1807090dd15a6f58e00fd769e32ebf20ee610385",
    "0x2141be5f2afa674c94167ab167a478a56cb539f5",
    "0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a",
    "0x6411bed82614b91ef655d82486e0bd3a13d2eb8c",
]
_COPY_SCORE = 13.0 / 15.0  # 0.8666666666666667


def _shib_code():
    text = block_codes()[_SHIB_ADDR]
    return bytes.fromhex(text[2:])


class TestInterfaceHitsExample1(unittest.TestCase):
    """Interface Hits example 1: B and D at four min_scores."""

    def test_interface_hits_b_and_d_at_four_min_scores(self):
        store = Store(belle_block_db())
        try:
            self.assertEqual(
                cluster.interface_hits(store, _BELLE_ID, min_score=0.5), 8)
            self.assertEqual(
                cluster.interface_hits(store, _BELLE_ID, min_score=0.7), 1)
            self.assertEqual(
                cluster.interface_hits(store, _BELLE_ID), 0)
            self.assertEqual(
                cluster.interface_hits(store, _BELLE_ID, min_score=0.8), 0)
            self.assertEqual(
                cluster.interface_hits(store, _DEPLOY_ID, min_score=0.5), 23)
            self.assertEqual(
                cluster.interface_hits(store, _DEPLOY_ID, min_score=0.7), 4)
            self.assertEqual(
                cluster.interface_hits(store, _DEPLOY_ID), 4)
            self.assertEqual(
                cluster.interface_hits(store, _DEPLOY_ID, min_score=0.8), 2)
        finally:
            store.close()


class TestInterfaceHitsExample2(unittest.TestCase):
    """Interface Hits example 2: unknown code_id, and code_min 1.0."""

    def test_unknown_code_id_and_code_min_one(self):
        store = Store(belle_block_db())
        try:
            self.assertEqual(
                cluster.interface_hits(store, "00" * 32), 0)
            self.assertEqual(
                cluster.interface_hits(store, _BELLE_ID, code_min=1.0), 4)
        finally:
            store.close()


class TestMatchWatchlistExample5(unittest.TestCase):
    """Match Watchlist example 5: the strict gate on the loose seed."""

    def test_strict_seed_demands_the_code(self):
        store = Store(belle_block_db())
        try:
            store.add_seed(_BELLE_ADDR, "BELLE honeypot")
            code = _shib_code()
            self.assertEqual(cluster.match_watchlist(store, code), [])
            alerts = cluster.match_watchlist(store, code, min_score=0.7)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["seed_address"], _BELLE_ADDR)
            self.assertEqual(alerts[0]["label"], "BELLE honeypot")
            self.assertEqual(alerts[0]["score"], 0.7333333333333333)
            self.assertTrue(store.set_seed_strict(_BELLE_ADDR, True))
            self.assertEqual(
                cluster.match_watchlist(store, code, min_score=0.7), [])
            alerts = cluster.match_watchlist(
                store, load_hex("code_belle_copy_1807090d.hex"))
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["seed_address"], _BELLE_ADDR)
            self.assertEqual(alerts[0]["score"], _COPY_SCORE)
        finally:
            store.close()


class TestRecheckWatchlistExample12(unittest.TestCase):
    """Recheck Watchlist example 12: strict cuts the interface-only hit."""

    def test_strict_seed_drops_the_interface_alert(self):
        store = Store(belle_block_db())
        try:
            store.add_seed(_BELLE_ADDR, "BELLE honeypot")

            alerts = cluster.recheck_watchlist(store)
            self.assertEqual(
                [a["address"] for a in alerts], _COPY_ADDRS)
            for alert in alerts:
                self.assertEqual(alert["seed_address"], _BELLE_ADDR)
                self.assertEqual(alert["label"], "BELLE honeypot")
                self.assertEqual(alert["score"], _COPY_SCORE)
                self.assertEqual(alert["origin"], "unknown")

            alerts = cluster.recheck_watchlist(store, min_score=0.7)
            self.assertEqual(
                [a["address"] for a in alerts],
                _COPY_ADDRS + [_SHIB_ADDR])
            fifth = alerts[4]
            self.assertEqual(fifth["address"], _SHIB_ADDR)
            self.assertEqual(fifth["seed_address"], _BELLE_ADDR)
            self.assertEqual(fifth["label"], "BELLE honeypot")
            self.assertEqual(fifth["score"], 0.7333333333333333)

            self.assertTrue(store.set_seed_strict(_BELLE_ADDR, True))
            alerts = cluster.recheck_watchlist(store, min_score=0.7)
            self.assertEqual(
                [a["address"] for a in alerts], _COPY_ADDRS)
            for alert in alerts:
                self.assertEqual(alert["score"], _COPY_SCORE)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
