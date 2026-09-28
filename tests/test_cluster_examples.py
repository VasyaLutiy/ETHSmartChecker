"""Judge tests: the examples of TASK_PHASE3.md as acceptance criterion.

This file does not touch the implementation: it only builds stores from
the fixtures and compares what ethsc.cluster returns against the
examples given for Build Clusters, Find Similar and Match Watchlist.
"""

import json
import os
import tempfile
import unittest

from ethsc.cluster import build_clusters, find_similar, match_watchlist
from ethsc.store import Store

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

BELLE_SEED = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
BELLE_COPIES = [
    "0x1807090dd15a6f58e00fd769e32ebf20ee610385",
    "0x2141be5f2afa674c94167ab167a478a56cb539f5",
    "0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a",
    "0x6411bed82614b91ef655d82486e0bd3a13d2eb8c",
]


def _temp_db():
    return os.path.join(tempfile.mkdtemp(), "t.db")


def _read_hex(fname):
    with open(os.path.join(FIXTURES, fname), "r") as handle:
        return bytes.fromhex(handle.read().strip()[2:])


def _block_store(reverse=False):
    """Store filled from codes_26077729.json (206 candidates)."""
    store = Store(_temp_db())
    with open(
        os.path.join(FIXTURES, "codes_26077729.json"), "r"
    ) as handle:
        raw = json.load(handle)
    items = sorted(raw.items())
    if reverse:
        items = list(reversed(items))
    for address, value in items:
        if value == "0x":
            store.put_address(address, None, 26077729)
        else:
            store.put_address(
                address, store.put_code(bytes.fromhex(value[2:])), 26077729
            )
    return store


def _belle_store():
    """Store with BELLE, its four copies and WETH9 at their addresses."""
    store = Store(_temp_db())
    pairs = [("code_belle.hex", BELLE_SEED)]
    for addr in BELLE_COPIES:
        pairs.append(("code_belle_copy_%s.hex" % addr[2:10], addr))
    pairs.append(
        ("code_weth9.hex", "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2")
    )
    for fname, addr in pairs:
        store.put_address(addr, store.put_code(_read_hex(fname)), 26077729)
    return store


def _find_cluster(clusters, level, key_prefix):
    """The cluster with the given level and key prefix, or None."""
    for cluster in clusters:
        if cluster["level"] == level and cluster["key"].startswith(key_prefix):
            return cluster
    return None


class TestBuildClustersExamples(unittest.TestCase):
    maxDiff = None

    def test_build_clusters_example_1_counts(self):
        """Build Clusters example 1: cluster counts and sizes."""
        store = _block_store()
        clusters = build_clusters(store)
        self.assertEqual(len(clusters), 15, "total clusters must be 15")
        l0 = [c for c in clusters if c["level"] == "L0"]
        l1 = [c for c in clusters if c["level"] == "L1"]
        proxy = [c for c in clusters if c["level"] == "proxy"]
        self.assertEqual(len(l0), 7, "seven L0 clusters")
        self.assertEqual(
            sorted((len(c["members"]) for c in l0), reverse=True),
            [4, 2, 2, 2, 2, 2, 2],
            "L0 sizes 4,2,2,2,2,2,2",
        )
        self.assertEqual(len(l1), 2, "two L1 clusters")
        self.assertEqual(
            sorted((len(c["members"]) for c in l1), reverse=True),
            [8, 5],
            "L1 clusters: 8 UniswapV3Pool and 5 LaunchToken addresses",
        )
        self.assertEqual(len(proxy), 6, "six proxy clusters")
        eip1167 = [c for c in proxy if c["key"].startswith("eip1167:")]
        eip7702 = [c for c in proxy if c["key"].startswith("eip7702:")]
        self.assertEqual(len(eip1167), 2, "two eip1167 proxy clusters")
        self.assertEqual(len(eip7702), 4, "four eip7702 proxy clusters")
        self.assertEqual(
            sorted(len(c["members"]) for c in eip1167), [2, 3],
            "eip1167 sizes: 3 (target 0x4181f370...) and 2 (0x8b72b9b8...)",
        )
        self.assertEqual(
            sorted(len(c["members"]) for c in eip7702), [2, 2, 2, 3],
            "eip7702 sizes: one 3 (target 0xd2e28229...) and three 2",
        )
        for cluster in proxy:
            self.assertEqual(
                sorted(cluster.keys()), ["key", "level", "members"],
                "proxy cluster has exactly the keys level/key/members",
            )
            self.assertEqual(
                cluster["members"],
                sorted(cluster["members"]),
                "proxy cluster members sorted",
            )
            for member in cluster["members"]:
                self.assertEqual(
                    member, member.lower(), "members lowercase"
                )
        big1167 = _find_cluster(clusters, "proxy", "eip1167:0x4181f370")
        self.assertIsNotNone(
            big1167, "eip1167 proxy cluster of target 0x4181f370... exists"
        )
        self.assertEqual(
            len(big1167["members"]), 3,
            "eip1167:0x4181f370... has 3 members",
        )

    def test_build_clusters_example_2_order(self):
        """Build Clusters example 2: first cluster is L1/8 members, first L0."""
        store = _block_store()
        clusters = build_clusters(store)
        self.assertTrue(clusters, "non-empty store gives clusters")
        first = clusters[0]
        self.assertEqual(
            first["level"], "L1", "the first cluster is L1 (8 members)"
        )
        self.assertEqual(
            len(first["members"]), 8, "the first cluster has 8 members"
        )
        self.assertIn(
            "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
            first["members"],
            "the UniswapV3Pool USDC/WETH 0.05% is in the first cluster",
        )
        l0 = [c for c in clusters if c["level"] == "L0"]
        first_l0 = _find_cluster(clusters, "L0", "8b5db55f")
        self.assertIsNotNone(
            first_l0, "L0 cluster with key 8b5db55f... exists"
        )
        self.assertEqual(
            len(first_l0["members"]), 4, "that L0 cluster has 4 members"
        )
        self.assertEqual(
            len(l0[0]["members"]), 4, "the first L0 in the list has 4 members"
        )

    def test_build_clusters_example_3_deterministic(self):
        """Build Clusters example 3: reverse insertion gives equal result."""
        forward = build_clusters(_block_store())
        backward = build_clusters(_block_store(reverse=True))
        self.assertEqual(
            forward, backward, "Deterministic Output: reverse insert order"
        )


class TestFindSimilarExamples(unittest.TestCase):
    maxDiff = None

    def test_find_similar_example_1_univ2_pair(self):
        """Find Similar example 1: three twins 1.0 and one 26/32."""
        store = _block_store()
        got = find_similar(
            store, "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
        )
        want = [
            ("0x22052a1a0f5a3d2839d71c458f177e68b0e73963", 1.0),
            ("0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c", 1.0),
            ("0x3041cbd36888becc7bbcbc0045e3b1f144466f5f", 1.0),
            ("0xcf6daab95c476106eca715d48de4b13287ffdeaa", 26 / 32),
        ]
        self.assertEqual(got, want, "exact example 1 result list")
        for _, score in got:
            self.assertIsInstance(score, float, "score is a float")

    def test_find_similar_example_2_belle_copies(self):
        """Find Similar example 2: four BELLE copies at 13/15."""
        store = _belle_store()
        got = find_similar(store, BELLE_SEED)
        want = [(addr, 13 / 15) for addr in BELLE_COPIES]
        self.assertEqual(got, want, "four copies, each 13/15, address order")


class TestMatchWatchlistExamples(unittest.TestCase):
    maxDiff = None

    def test_match_watchlist_example_1_belle_alert(self):
        """Match Watchlist example 1: BELLE copy raises one alert 13/15."""
        store = _belle_store()
        store.add_seed(BELLE_SEED, "BELLE honeypot")
        alerts = match_watchlist(
            store, _read_hex("code_belle_copy_1807090d.hex")
        )
        self.assertEqual(
            alerts,
            [
                {
                    "seed_address": BELLE_SEED,
                    "label": "BELLE honeypot",
                    "score": 13 / 15,
                }
            ],
            "exactly one alert with label and score 13/15",
        )

    def test_match_watchlist_example_2_weth9_silent(self):
        """Match Watchlist example 2: WETH9 gives no alert (9/16 < 0.8)."""
        store = _belle_store()
        store.add_seed(BELLE_SEED, "BELLE honeypot")
        self.assertEqual(
            match_watchlist(store, _read_hex("code_weth9.hex")),
            [],
            "WETH9 at 9/16 stays below the threshold",
        )

    def test_match_watchlist_example_3_tolerant(self):
        """Match Watchlist example 3: no seeds and b\"\" both give []."""
        store = _belle_store()
        self.assertEqual(
            match_watchlist(store, b""), [], "no seeds -> []"
        )
        store.add_seed(BELLE_SEED, "BELLE honeypot")
        self.assertEqual(
            match_watchlist(store, b""), [], "empty code -> []"
        )


if __name__ == "__main__":
    unittest.main()
