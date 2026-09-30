"""Smoke tests for phase 11: cluster scores from fingerprints only.

Verifies, on small scalars, that find_similar, match_watchlist and
recheck_watchlist no longer read stored codes: a store whose
code_by_id raises still gives the phase-10 answers over the block
fixtures, because the three functions score stored fingerprints with
score_fingerprints and never touch code_by_id.
"""

import unittest

from ethsc import cluster

from tests.helpers import block_store, load_hex


class StubStore(object):
    """Wraps a store; code_by_id raises, as phase 11 never calls it."""

    def __init__(self, inner):
        self._inner = inner

    def code_by_id(self, code_id):
        raise AssertionError("code_by_id called in phase 11")

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TestClusterP11(unittest.TestCase):
    def test_recheck_stubbed_gives_four_alerts(self):
        store = block_store()
        seed = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
        store.add_seed(seed, "UniV2 pair seed")
        alerts = cluster.recheck_watchlist(StubStore(store))
        self.assertEqual(len(alerts), 4, msg="recheck over the block store")
        self.assertEqual(
            alerts[0]["address"],
            "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
            msg="first alert address ascending",
        )
        self.assertEqual(alerts[0]["score"], 1.0, msg="same-code score 1.0")
        self.assertEqual(alerts[3]["score"], 0.8125, msg="26/32 float exact")

    def test_find_similar_stubbed_gives_four_results(self):
        store = block_store()
        results = cluster.find_similar(
            StubStore(store), "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
        )
        self.assertEqual(len(results), 4, msg="similar over the block store")
        self.assertEqual(results[0][1], 1.0, msg="same-code score 1.0")
        self.assertEqual(results[3][1], 0.8125, msg="26/32 float exact")
        self.assertEqual(
            results[3][0],
            "0xcf6daab95c476106eca715d48de4b13287ffdeaa",
            msg="solc 0.6.12 pair last",
        )

    def test_match_watchlist_stubbed_one_alert(self):
        store = block_store()
        seed = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
        store.add_seed(seed, "UniV2 pair seed")
        alerts = cluster.match_watchlist(
            StubStore(store), load_hex("code_univ2_usdc_weth.hex")
        )
        self.assertEqual(len(alerts), 1, msg="identical code, one alert")
        self.assertEqual(alerts[0]["score"], 1.0, msg="score 1.0")
        self.assertEqual(alerts[0]["seed_address"], seed, msg="seed address")

    def test_match_watchlist_empty_code_min_zero(self):
        store = block_store()
        seed = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
        store.add_seed(seed, "UniV2 pair seed")
        alerts = cluster.match_watchlist(store, b"", min_score=0.0)
        self.assertEqual(len(alerts), 1, msg="one 0.0 alert per seed")
        self.assertEqual(alerts[0]["score"], 0.0, msg="None scores 0.0")

    def test_empty_code_no_seeds_and_unknown(self):
        store = block_store()
        self.assertEqual(
            cluster.match_watchlist(store, b"\xfe\x60"),
            [],
            msg="no seeds, no alerts",
        )
        self.assertEqual(
            cluster.recheck_watchlist(
                store, seed_addresses=["0x1111111111111111111111111111111111111111"]
            ),
            [],
            msg="unknown seed address matches nothing",
        )


if __name__ == "__main__":
    unittest.main()
