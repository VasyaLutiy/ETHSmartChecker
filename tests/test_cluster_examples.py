"""Judge tests: the examples of the cluster group in contour.yaml.

This file does not touch the implementation: it only builds stores from
the fixtures and compares what ethsc.cluster returns against the
examples given for Build Clusters, Find Similar, Match Watchlist and
Recheck Watchlist (phase-9 shapes: level "eip7702", proxy = eip1167
only, a standard-proxy seed alerts on nothing).
"""

import json
import os
import tempfile
import unittest

from ethsc.cluster import build_clusters, find_similar, match_watchlist
from ethsc.cluster import recheck_watchlist
from ethsc.store import Store

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

BELLE_SEED = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
BELLE_COPIES = [
    "0x1807090dd15a6f58e00fd769e32ebf20ee610385",
    "0x2141be5f2afa674c94167ab167a478a56cb539f5",
    "0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a",
    "0x6411bed82614b91ef655d82486e0bd3a13d2eb8c",
]

UNIV2_SEED = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
UNIV2_ADDRESSES = [
    "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
    "0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c",
    "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f",
]

PROXY_SEED = "0x0c0105334a50db16b51b2911c9956539753a2cf8"

EIP1167_KEYS = [
    "eip1167:0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb",
    "eip1167:0x8b72b9b8e544f944cdcdf0cdb6194f917ac1eba5",
]
EIP7702_BIG = "eip7702:0xd2e28229f6f2c235e57de2ebc727025a1d0530fb"
EIP7702_SMALL = [
    "eip7702:0x0000fb7702036ff9f76044a501ac1aa74cbab16b",
    "eip7702:0x490aac77c960b0569c8e446ac7e12490bd44ca1d",
    "eip7702:0x63c0c19a282a1b52b07dd5a65b58948a07dae32b",
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


def _proxy_seed_store():
    """Store holding code_proxy_seed_0c010533.hex at two addresses."""
    store = Store(_temp_db())
    code_id = store.put_code(_read_hex("code_proxy_seed_0c010533.hex"))
    store.put_address(PROXY_SEED, code_id, 26077729)
    store.put_address(
        "0x1111111111111111111111111111111111111111", code_id, 26077729
    )
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
        """Build Clusters example 1: counts, sizes and full keys."""
        store = _block_store()
        clusters = build_clusters(store)
        self.assertEqual(len(clusters), 15, "total clusters must be 15")
        l0 = [c for c in clusters if c["level"] == "L0"]
        l1 = [c for c in clusters if c["level"] == "L1"]
        proxy = [c for c in clusters if c["level"] == "proxy"]
        eip7702 = [c for c in clusters if c["level"] == "eip7702"]
        self.assertEqual(len(l0), 7, "seven L0 clusters")
        self.assertEqual(
            sorted((len(c["members"]) for c in l0), reverse=True),
            [4, 2, 2, 2, 2, 2, 2],
            "L0 sizes 4,2,2,2,2,2,2",
        )
        self.assertEqual(
            sum(len(c["members"]) for c in l0), 16,
            "L0 clusters cover 16 addresses",
        )
        self.assertEqual(len(l1), 2, "two L1 clusters")
        self.assertEqual(
            sorted((len(c["members"]) for c in l1), reverse=True),
            [8, 5],
            "L1 clusters: 8 UniswapV3Pool and 5 LaunchToken addresses",
        )
        self.assertEqual(
            sum(len(c["members"]) for c in l1), 13,
            "L1 clusters cover 13 addresses",
        )
        self.assertEqual(len(proxy), 2, "two proxy clusters (eip1167 only)")
        self.assertEqual(len(eip7702), 4, "four eip7702 clusters")
        self.assertEqual(
            sorted(c["key"] for c in proxy), EIP1167_KEYS,
            "the proxy keys carry the FULL 40-hex targets",
        )
        self.assertEqual(
            sorted(len(c["members"]) for c in proxy), [2, 3],
            "proxy sizes: 3 (eip1167:0x4181f370...) and 2 (0x8b72b9b8...)",
        )
        self.assertEqual(
            sum(len(c["members"]) for c in proxy), 5,
            "proxy clusters cover 5 addresses",
        )
        # every proxy/eip7702 key is "<kind>:0x" + 40 lowercase hex
        for cluster in proxy + eip7702:
            self.assertEqual(
                sorted(cluster.keys()), ["key", "level", "members"],
                "cluster has exactly the keys level/key/members",
            )
            kind, _, target = cluster["key"].partition(":")
            self.assertEqual(
                (len(cluster["key"]), kind, len(target)),
                (50, kind, 42),
                "the key carries the FULL 40-hex target, not an ellipsis",
            )
            self.assertEqual(
                target, target.lower(), "proxy key target lowercase"
            )
            self.assertEqual(
                cluster["members"], sorted(cluster["members"]),
                "cluster members sorted",
            )
            for member in cluster["members"]:
                self.assertEqual(
                    member, member.lower(), "members lowercase"
                )
        big1167 = _find_cluster(clusters, "proxy", EIP1167_KEYS[0])
        self.assertIsNotNone(
            big1167, "eip1167 proxy cluster of target 0x4181f370... exists"
        )
        self.assertEqual(
            len(big1167["members"]), 3,
            "eip1167:0x4181f370... has 3 members",
        )
        big7702 = _find_cluster(clusters, "eip7702", EIP7702_BIG)
        self.assertIsNotNone(
            big7702, "eip7702 cluster of target 0xd2e28229... exists"
        )
        self.assertEqual(
            len(big7702["members"]), 3,
            "eip7702:0xd2e28229... has 3 members",
        )
        for target in EIP7702_SMALL:
            small = _find_cluster(clusters, "eip7702", target)
            self.assertIsNotNone(
                small, "eip7702 cluster %s exists" % target
            )
            self.assertEqual(
                len(small["members"]), 2,
                "%s has 2 members" % target,
            )
        self.assertEqual(
            sum(len(c["members"]) for c in eip7702), 9,
            "eip7702 clusters cover 9 addresses",
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
        first_l0 = _find_cluster(clusters, "L0", "8b5db55f")
        self.assertIsNotNone(
            first_l0, "L0 cluster with key 8b5db55f... exists"
        )
        self.assertEqual(
            len(first_l0["members"]), 4, "that L0 cluster has 4 members"
        )
        l0 = [c for c in clusters if c["level"] == "L0"]
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
        """Match Watchlist example 3: no seeds and b"" both give []."""
        store = _belle_store()
        self.assertEqual(
            match_watchlist(store, b""), [], "no seeds -> []"
        )
        store.add_seed(BELLE_SEED, "BELLE honeypot")
        self.assertEqual(
            match_watchlist(store, b""), [], "empty code -> []"
        )


class TestRecheckWatchlistExamples(unittest.TestCase):
    maxDiff = None

    def test_recheck_example_1_univ2_seed(self):
        """Recheck Watchlist example 1: 4 alerts, the seed's own absent."""
        store = _block_store()
        store.add_seed(UNIV2_SEED, "UniV2 pair seed")
        alerts = recheck_watchlist(store)
        want = [
            {
                "address": addr,
                "seed_address": UNIV2_SEED,
                "label": "UniV2 pair seed",
                "score": 1.0,
                "origin": "unknown",
            }
            for addr in UNIV2_ADDRESSES
        ]
        want.append(
            {
                "address": "0xcf6daab95c476106eca715d48de4b13287ffdeaa",
                "seed_address": UNIV2_SEED,
                "label": "UniV2 pair seed",
                "score": 26 / 32,
                "origin": "unknown",
            }
        )
        self.assertEqual(
            alerts, want,
            "exactly 4 alerts: three 1.0 of the same code, then 0xcf6daab9... "
            "at 26/32",
        )
        self.assertNotIn(
            UNIV2_SEED,
            [alert["address"] for alert in alerts],
            "the seed's own address is not among the alerts",
        )

    def test_recheck_example_2_min_score_and_seed_addresses(self):
        """Recheck Watchlist example 2: min_score=1.0 and upper-case seed."""
        store = _block_store()
        store.add_seed(UNIV2_SEED, "UniV2 pair seed")
        alerts = recheck_watchlist(store, min_score=1.0)
        want = [
            {
                "address": addr,
                "seed_address": UNIV2_SEED,
                "label": "UniV2 pair seed",
                "score": 1.0,
                "origin": "unknown",
            }
            for addr in UNIV2_ADDRESSES
        ]
        self.assertEqual(
            alerts, want, "min_score=1.0 gives only the three 1.0 alerts"
        )
        upper = recheck_watchlist(
            store, seed_addresses=[UNIV2_SEED.upper()]
        )
        self.assertEqual(
            upper, recheck_watchlist(store),
            "seed_addresses with the upper-case seed equals the default call",
        )

    def test_recheck_example_3_belle_copies_twice(self):
        """Recheck Watchlist example 3: two equal runs, 4 alerts at 13/15."""
        store = _belle_store()
        store.add_seed(BELLE_SEED, "BELLE honeypot")
        first = recheck_watchlist(store)
        second = recheck_watchlist(store)
        self.assertEqual(
            first, second, "two calls on the same store give equal lists"
        )
        want = [
            {
                "address": addr,
                "seed_address": BELLE_SEED,
                "label": "BELLE honeypot",
                "score": 13 / 15,
                "origin": "unknown",
            }
            for addr in BELLE_COPIES
        ]
        self.assertEqual(
            first, want, "the 4 copies, each 13/15, in address order"
        )

    def test_recheck_example_4_empty(self):
        """Recheck Watchlist example 4: no seeds and unknown seed give []."""
        store = _belle_store()
        self.assertEqual(
            recheck_watchlist(store), [], "no seeds -> []"
        )
        self.assertEqual(
            recheck_watchlist(
                store,
                seed_addresses=["0x1111111111111111111111111111111111111111"],
            ),
            [],
            "seed_addresses naming nothing known -> []",
        )

    def test_recheck_example_5_std_proxy_seed_matches_nothing(self):
        """Recheck Watchlist example 5: a standard-proxy seed alerts on [].

        The seed's own bytecode sits at a second address too, and even
        that byte-identical copy must not alert: similarity rule 2
        scores an opaque standard proxy 0.0 against everything.
        """
        store = _proxy_seed_store()
        store.add_seed(PROXY_SEED, "TransparentUpgradeableProxy")
        alerts = recheck_watchlist(store)
        self.assertEqual(
            alerts, [],
            "a standard-proxy seed matches nothing: not the other stored "
            "copy of its own bytecode, not anything else in the store",
        )


if __name__ == "__main__":
    unittest.main()
