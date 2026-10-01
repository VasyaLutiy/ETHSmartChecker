"""Judge for the phase-11 cluster examples: Recheck Watchlist examples 6-7.

Each test pins one example of contour.yaml, group cluster, with the exact
values given there.
"""

import tempfile
import unittest
from unittest import mock

from tests.helpers import load_hex, block_codes, temp_store, block_store

SEED = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
UNIV2_PAIRS = [
    "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
    "0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c",
    "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f",
]
SOLC6_PAIR = "0xcf6daab95c476106eca715d48de4b13287ffdeaa"
BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"

from ethsc import cluster


class NoCodeStore(object):
    """Forwards every attribute to the store; code_by_id raises."""

    def __init__(self, store):
        self._store = store

    def code_by_id(self, code_id):
        raise AssertionError("code_by_id must not be called in phase 11")

    def __getattr__(self, name):
        return getattr(self._store, name)


class TestClusterExamplesP11(unittest.TestCase):
    maxDiff = None

    def test_recheck_watchlist_example_6(self):
        """Recheck Watchlist example 6: stubbed code_by_id and similarity."""
        store = block_store()
        store.add_seed(SEED, "UniV2 pair seed")
        guarded = NoCodeStore(store)
        with mock.patch.object(
            cluster, "similarity", create=True,
            side_effect=AssertionError("similarity must not be called"),
        ):
            alerts = cluster.recheck_watchlist(guarded)
            expected = [
                {"address": UNIV2_PAIRS[0], "seed_address": SEED,
                 "label": "UniV2 pair seed", "score": 1.0, "origin": "unknown"},
                {"address": UNIV2_PAIRS[1], "seed_address": SEED,
                 "label": "UniV2 pair seed", "score": 1.0, "origin": "unknown"},
                {"address": UNIV2_PAIRS[2], "seed_address": SEED,
                 "label": "UniV2 pair seed", "score": 1.0, "origin": "unknown"},
                {"address": SOLC6_PAIR, "seed_address": SEED,
                 "label": "UniV2 pair seed", "score": 26 / 32, "origin": "unknown"},
            ]
            self.assertEqual(alerts, expected,
                             msg="recheck_watchlist alerts differ")
            self.assertEqual(
                alerts[3]["score"], 0.8125, msg="26/32 == 0.8125")
            similar = cluster.find_similar(guarded, SEED)
            self.assertEqual(
                similar,
                [(UNIV2_PAIRS[0], 1.0), (UNIV2_PAIRS[1], 1.0),
                 (UNIV2_PAIRS[2], 1.0), (SOLC6_PAIR, 26 / 32)],
                msg="find_similar tuples differ",
            )
            matched = cluster.match_watchlist(
                guarded, load_hex("code_univ2_usdc_weth.hex"))
            self.assertEqual(
                matched,
                [{"seed_address": SEED, "label": "UniV2 pair seed",
                  "score": 1.0}],
                msg="match_watchlist alert differs",
            )

    def test_match_watchlist_example_7(self):
        """Match Watchlist example 7: empty code against the BELLE seed."""
        store = temp_store()
        code_id = store.put_code(load_hex("code_belle.hex"))
        store.put_address(BELLE, code_id, 26077729)
        store.add_seed(BELLE, "BELLE honeypot")
        self.assertEqual(
            cluster.match_watchlist(store, b"", min_score=0.0),
            [{"seed_address": BELLE, "label": "BELLE honeypot",
              "score": 0.0}],
            msg="one 0.0 alert at min_score 0.0",
        )
        self.assertEqual(
            cluster.match_watchlist(store, b""), [],
            msg="[] at the default min_score",
        )
