"""Tests for ethsc.cluster: Build Clusters, Find Similar, Match Watchlist.

Every test proves an example or a rule from contour.yaml / the card,
over the real fixtures of tests/fixtures/. No network, stores live in
temporary directories only. Helpers are not named test_*.
"""

import json
import os
import tempfile
import unittest

from ethsc.cluster import (
    build_clusters,
    find_similar,
    match_watchlist,
    recheck_watchlist,
)
from ethsc.fingerprint import fingerprint, similarity
from ethsc.store import Store

FIXTURES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures"
)
CODES_BLOCK = os.path.join(FIXTURES, "codes_26077729.json")

BELLE_SEED = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
BELLE_COPY_1807 = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
BELLE_COPY_2141 = "0x2141be5f2afa674c94167ab167a478a56cb539f5"
BELLE_COPY_46CA = "0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a"
BELLE_COPY_6411 = "0x6411bed82614b91ef655d82486e0bd3a13d2eb8c"

UNIV2_ADDRESSES = [
    "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
    "0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c",
    "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f",
    "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
]


def load_code(name):
    """Decoded bytes of a code_*.hex fixture."""
    path = os.path.join(FIXTURES, name)
    with open(path, "r") as handle:
        text = handle.read().strip()
    return bytes.fromhex(text[2:])


def load_block_codes():
    """The {address: getCode result} map of block 26077729."""
    with open(CODES_BLOCK, "r") as handle:
        return json.load(handle)


def fill_from_block(store, codes=None, reverse=False):
    """Fill a store from codes_26077729.json (optionally reversed)."""
    if codes is None:
        codes = load_block_codes()
    items = list(codes.items())
    if reverse:
        items = list(reversed(items))
    for address, result in items:
        if result == "0x":
            store.put_address(address, None, 26077729)
        else:
            store.put_address(
                address, store.put_code(bytes.fromhex(result[2:])), 26077729
            )
    return store


def make_block_store(reverse=False):
    """A temp store filled from codes_26077729.json."""
    store = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
    return fill_from_block(store, reverse=reverse)


def make_belle_store(with_weth9=False):
    """A store with BELLE, its four copies and their addresses."""
    store = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
    entries = [
        (BELLE_SEED, "code_belle.hex"),
        (BELLE_COPY_1807, "code_belle_copy_1807090d.hex"),
        (BELLE_COPY_2141, "code_belle_copy_2141be5f.hex"),
        (BELLE_COPY_46CA, "code_belle_copy_46cadea5.hex"),
        (BELLE_COPY_6411, "code_belle_copy_6411bed8.hex"),
    ]
    if with_weth9:
        entries.append(
            ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "code_weth9.hex")
        )
    for address, name in entries:
        store.put_address(address, store.put_code(load_code(name)), 1)
    return store


def as_triple(cluster):
    """(level, key, len(members)) of one Cluster dict."""
    return (cluster["level"], cluster["key"], len(cluster["members"]))


# The exact expected cluster list of block 26077729, in sort order:
# member count descending, level L0 < L1 < proxy, key ascending.
EXPECTED_TRIPLES = [
    ("L1", "29ec9639b8fa8f759c993d77fe43ccfb471dd596d23b3b098965ebb64e56235f", 8),
    ("L1", "7ce24a99dd96320ff172118ca968fe518c7236b6b1d9e563f8f781135e8c5fa3", 5),
    ("L0", "8b5db55fa9ab3b9527508d4abe0b39eb588bf310270c8e04b3f38214e8ba63b4", 4),
    ("proxy", "eip1167:0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb", 3),
    ("proxy", "eip7702:0xd2e28229f6f2c235e57de2ebc727025a1d0530fb", 3),
    ("L0", "501b4a60e24ea82032b7442d75995dee3bdbfc17b25caffc3c955eadc8c2a418", 2),
    ("L0", "5b8bff324e02136edb0775bd77aa0fe773c1e23092305fe63f50a9e92f5b8faf", 2),
    ("L0", "6060dd38da4f6b8a88c46c019ee34a863b3db7b0df25ecdf7af71d0339fdb314", 2),
    ("L0", "6ea7d1dc71b2921d9ce44ae6dae480ed26cf751338584ecfcdc29a20e2f86583", 2),
    ("L0", "e518057ee9772b6d5ad104f0c0cbae96d42e5543dcaaff3b39257089ab5fe699", 2),
    ("L0", "ef82dac27e8156885d056a57c71e69cbdd4a1f345095161053df92240f0350f3", 2),
    ("proxy", "eip1167:0x8b72b9b8e544f944cdcdf0cdb6194f917ac1eba5", 2),
    ("proxy", "eip7702:0x0000fb7702036ff9f76044a501ac1aa74cbab16b", 2),
    ("proxy", "eip7702:0x490aac77c960b0569c8e446ac7e12490bd44ca1d", 2),
    ("proxy", "eip7702:0x63c0c19a282a1b52b07dd5a65b58948a07dae32b", 2),
]


class BuildClustersBlockTest(unittest.TestCase):
    """Build Clusters over the full block 26077729 store."""

    maxDiff = None

    def test_block_example_1(self):
        """Example 1: 7 L0 (4,2,2,2,2,2,2), 2 L1 (8, 5), 6 proxy."""
        store = make_block_store()
        try:
            clusters = build_clusters(store)
            self.assertEqual(len(clusters), 15, "15 clusters total")
            self.assertEqual(
                [as_triple(c) for c in clusters],
                EXPECTED_TRIPLES,
                "exact levels, keys and member counts in sort order",
            )
            l0_sizes = [
                len(c["members"]) for c in clusters if c["level"] == "L0"
            ]
            self.assertEqual(
                l0_sizes, [4, 2, 2, 2, 2, 2, 2], "L0 sizes"
            )
            l1_sizes = [
                len(c["members"]) for c in clusters if c["level"] == "L1"
            ]
            self.assertEqual(l1_sizes, [8, 5], "L1 sizes (V3 pools, tokens)")
            proxy_sizes = [
                len(c["members"]) for c in clusters if c["level"] == "proxy"
            ]
            self.assertEqual(
                proxy_sizes, [3, 3, 2, 2, 2, 2], "proxy sizes"
            )
        finally:
            store.close()

    def test_block_example_2(self):
        """Example 2: first cluster is the L1 with 8 members incl. the
        0x88e6a0c2 pool; the first L0 has key 8b5db55f... and the four
        UniswapV2Pair addresses."""
        store = make_block_store()
        try:
            clusters = build_clusters(store)
            first = clusters[0]
            self.assertEqual(first["level"], "L1", "first cluster is L1")
            self.assertEqual(len(first["members"]), 8, "8 members")
            self.assertIn(
                "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640",
                first["members"],
                "the 0x88e6a0c2 pool is a member",
            )
            l0 = [c for c in clusters if c["level"] == "L0"][0]
            self.assertEqual(
                l0["key"], EXPECTED_TRIPLES[2][1], "first L0 key 8b5db55f..."
            )
            self.assertEqual(
                l0["members"],
                UNIV2_ADDRESSES,
                "the four UniswapV2Pair addresses, sorted",
            )
        finally:
            store.close()

    def test_block_example_3_reverse_insertion_order(self):
        """Example 3: the same codes inserted in reverse order give the
        equal cluster list (Deterministic Output)."""
        forward = build_clusters(make_block_store(reverse=False))
        try:
            reverse_store = make_block_store(reverse=True)
            try:
                self.assertEqual(
                    build_clusters(reverse_store),
                    forward,
                    "reverse insertion order gives the equal list",
                )
            finally:
                reverse_store.close()
        finally:
            pass

    def test_cluster_keys_and_members_form(self):
        """Cluster dicts carry exactly level/key/members; members are
        sorted lowercase addresses; proxy members of the eip1167
        0x4181f370 cluster are the three clones."""
        store = make_block_store()
        try:
            clusters = build_clusters(store)
            for cluster in clusters:
                self.assertEqual(
                    sorted(cluster),
                    ["key", "level", "members"],
                    "exactly the three keys",
                )
                members = cluster["members"]
                self.assertEqual(
                    members, sorted(m.lower() for m in members),
                    "members sorted lowercase",
                )
            px = [
                c
                for c in clusters
                if c["key"] == "eip1167:0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb"
            ]
            self.assertEqual(len(px), 1, "one eip1167 0x4181f370 cluster")
            self.assertEqual(
                px[0]["members"],
                [
                    "0x270df01200e2f9fffd1c3d56f5b0a4b1c3eaaa5f",
                    "0x3b2fac8e18e9d354cf1f4770ad0e80b797095a2d",
                    "0x5285024806d9d3802298f861f0535d81b824dda4",
                ],
                "the three clone addresses",
            )
        finally:
            store.close()

    def test_empty_store(self):
        """An empty store gives [] (tolerant, no exception)."""
        store = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
        try:
            self.assertEqual(
                build_clusters(store), [], "empty store"
            )
        finally:
            store.close()

    def test_l1_key_from_fingerprints(self):
        """The L1 keys are skeleton hashes of >= 2 distinct code_id
        (checked against fingerprints()); proxy codes never enter
        L0 or L1."""
        store = make_block_store()
        try:
            fps = store.fingerprints()
            self.assertEqual(len(fps), 130, "130 distinct codes")
            proxy_fps = [fp for fp in fps if fp["proxy"] is not None]
            self.assertEqual(len(proxy_fps), 12, "12 proxy codes")
            clusters = build_clusters(store)
            keys_by_level = {}
            for cluster in clusters:
                keys_by_level.setdefault(cluster["level"], set()).add(
                    cluster["key"]
                )
            skel_counts = {}
            for fp in fps:
                if fp["proxy"] is not None:
                    continue
                skel_counts.setdefault(fp["skeleton_hash"], set()).add(
                    fp["code_id"]
                )
            shared = {
                h
                for h, ids in skel_counts.items()
                if len(ids) >= 2
            }
            self.assertEqual(
                keys_by_level.get("L1"), shared, "L1 keys = shared skeletons"
            )
            for cluster in clusters:
                if cluster["level"] in ("L0", "L1"):
                    self.assertNotIn(
                        cluster["key"],
                        [fp["code_id"] for fp in proxy_fps],
                        "proxy code_id never an L0 key",
                    )
        finally:
            store.close()


class FindSimilarTest(unittest.TestCase):
    """Find Similar over the block store and the BELLE store."""

    maxDiff = None

    def test_block_example_1(self):
        """Example 1: from the USDC/WETH pair, the three same-code
        addresses with 1.0, then 0xcf6daab9... with 26/32."""
        store = make_block_store()
        try:
            result = find_similar(
                store, "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
            )
            self.assertEqual(
                result,
                [
                    ("0x22052a1a0f5a3d2839d71c458f177e68b0e73963", 1.0),
                    ("0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c", 1.0),
                    ("0x3041cbd36888becc7bbcbc0045e3b1f144466f5f", 1.0),
                    (
                        "0xcf6daab95c476106eca715d48de4b13287ffdeaa",
                        26.0 / 32.0,
                    ),
                ],
                "exact result of example 1",
            )
            self.assertIsInstance(result[3][1], float, "score is a float")
            self.assertEqual(
                result[3][1], similarity(
                    store.code_of("0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"),
                    store.code_of("0xcf6daab95c476106eca715d48de4b13287ffdeaa"),
                ),
                "score equals similarity()",
            )
        finally:
            store.close()

    def test_query_mixed_case_same_result(self):
        """The query address is lowercased; a mixed-case query gives the
        same answer (Deterministic Output)."""
        store = make_block_store()
        try:
            lower = find_similar(
                store, "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
            )
            upper = find_similar(
                store, "0xB4E16D0168E52D35CACD2C6185B44281EC28C9DC"
            )
            self.assertEqual(upper, lower, "case-insensitive query")
        finally:
            store.close()

    def test_min_score_1_0(self):
        """min_score=1.0 keeps only the three same-code addresses."""
        store = make_block_store()
        try:
            result = find_similar(
                store,
                "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
                min_score=1.0,
            )
            self.assertEqual(
                [address for address, _ in result],
                UNIV2_ADDRESSES[:3],
                "only the three pairs of the same code",
            )
        finally:
            store.close()

    def test_unknown_address_and_eoa(self):
        """An unknown address or one without code gives []."""
        store = make_block_store()
        try:
            self.assertEqual(
                find_similar(store, "0x" + "11" * 20),
                [],
                "unknown address",
            )
            eoa = "0x023697eda1dfbe331c2cf791ef2f6089e73e3230"
            self.assertTrue(
                store.has_address(eoa), "the EOA is stored without code"
            )
            self.assertEqual(
                find_similar(store, eoa), [], "EOA gives []"
            )
        finally:
            store.close()

    def test_belle_example_2(self):
        """Example 2: from BELLE, the four copies each at 13/15, in
        address order 0x1807..., 0x2141..., 0x46ca..., 0x6411...."""
        store = make_belle_store()
        try:
            result = find_similar(store, BELLE_SEED)
            self.assertEqual(
                [address for address, _ in result],
                [
                    BELLE_COPY_1807,
                    BELLE_COPY_2141,
                    BELLE_COPY_46CA,
                    BELLE_COPY_6411,
                ],
                "the four copies in address order",
            )
            self.assertTrue(
                all(
                    abs(score - 13.0 / 15.0) < 1e-12
                    for _, score in result
                ),
                "each score is 13/15",
            )
        finally:
            store.close()

    def test_self_excluded_same_code_included(self):
        """The queried address itself never appears; the other addresses
        of its own code come back with 1.0 (find_similar rules)."""
        store = make_block_store()
        try:
            result = find_similar(
                store, "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
            )
            self.assertNotIn(
                "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
                [address for address, _ in result],
                "the query address is excluded",
            )
            self.assertEqual(
                [score for _, score in result[:3]],
                [1.0, 1.0, 1.0],
                "same-code addresses give 1.0",
            )
        finally:
            store.close()


class MatchWatchlistTest(unittest.TestCase):
    """Match Watchlist over the BELLE store and its seeds."""

    maxDiff = None

    def test_example_1(self):
        """Example 1: the BELLE seed alerts on the ALPHA copy with
        label 'BELLE honeypot' and score 13/15."""
        store = make_belle_store()
        try:
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            alerts = match_watchlist(
                store, load_code("code_belle_copy_1807090d.hex")
            )
            self.assertEqual(
                alerts,
                [
                    {
                        "seed_address": BELLE_SEED,
                        "label": "BELLE honeypot",
                        "score": 13.0 / 15.0,
                    }
                ],
                "one alert, label and exact score",
            )
        finally:
            store.close()

    def test_example_2_weth9_below_default_threshold(self):
        """Example 2: WETH9 against the BELLE seed is 9/16 = 0.5625 and
        gives [] at the default threshold."""
        store = make_belle_store()
        try:
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            self.assertEqual(
                similarity(
                    load_code("code_weth9.hex"),
                    load_code("code_belle.hex"),
                ),
                9.0 / 16.0,
                "WETH9 vs BELLE is exactly 9/16",
            )
            self.assertEqual(
                match_watchlist(store, load_code("code_weth9.hex")),
                [],
                "no alert below the default threshold",
            )
        finally:
            store.close()

    def test_example_3_no_seeds_and_empty_code(self):
        """Example 3 / Tolerant Parser: a store with no seeds gives [],
        and empty code b"" against the BELLE seed gives []; neither
        raises."""
        store = make_belle_store()
        try:
            self.assertEqual(
                match_watchlist(store, load_code("code_belle.hex")),
                [],
                "no seeds",
            )
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            self.assertEqual(
                match_watchlist(store, b""), [], "empty code"
            )
            self.assertEqual(
                match_watchlist(store, b"\xff\xffgarbage"), [],
                "garbage bytes",
            )
        finally:
            store.close()

    def test_min_score_0_5_lets_weth9_through(self):
        """min_score=0.5 admits the WETH9 alert at 9/16 (acceptance rule)."""
        store = make_belle_store()
        try:
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            alerts = match_watchlist(
                store, load_code("code_weth9.hex"), min_score=0.5
            )
            self.assertEqual(len(alerts), 1, "one alert")
            self.assertEqual(alerts[0]["score"], 9.0 / 16.0, "9/16 exact")
            self.assertEqual(alerts[0]["seed_address"], BELLE_SEED, "seed")
        finally:
            store.close()

    def test_two_seeds_sorted_by_score(self):
        """With two seeds the alerts sort by score desc, then address."""
        store = make_belle_store()
        try:
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            store.add_seed(BELLE_COPY_1807, "ALPHA copy")
            alerts = match_watchlist(store, load_code("code_belle.hex"))
            self.assertEqual(len(alerts), 2, "two alerts")
            self.assertEqual(
                [a["seed_address"] for a in alerts],
                [BELLE_SEED, BELLE_COPY_1807],
                "identical code 1.0 first, copy 13/15 second",
            )
            self.assertEqual(alerts[0]["score"], 1.0, "seed vs itself 1.0")
            self.assertEqual(alerts[1]["score"], 13.0 / 15.0, "13/15")
        finally:
            store.close()

    def test_alert_keys_exact(self):
        """Alert dicts carry exactly seed_address, label and score, and
        the score is the raw similarity float, never rounded."""
        store = make_belle_store()
        try:
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            alerts = match_watchlist(
                store, load_code("code_belle_copy_6411bed8.hex")
            )
            for alert in alerts:
                self.assertEqual(
                    sorted(alert),
                    ["label", "score", "seed_address"],
                    "exactly the three keys",
                )
                self.assertIsInstance(alert["score"], float, "score type")
            self.assertEqual(
                alerts[0]["score"], 13.0 / 15.0, "13/15 not rounded"
            )
        finally:
            store.close()

    def test_junk_codes_never_raise(self):
        """Garbage and truncated codes never raise (Tolerant Parser)."""
        store = make_belle_store()
        try:
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            for junk in (b"\x7f\x01", b"\xfe" * 7, bytes(range(256))):
                alerts = match_watchlist(store, junk)
                self.assertIsInstance(
                    alerts, list, "junk gives a list"
                )
        finally:
            store.close()


class RecheckWatchlistTest(unittest.TestCase):
    """Recheck Watchlist: the copies already in the database."""

    def test_belle_copies_already_in_store(self):
        """Four BELLE copies already in the db alert at 13/15, the seed
        address itself does not appear; WETH9 stays below threshold."""
        store = make_belle_store(with_weth9=True)
        try:
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            alerts = recheck_watchlist(store)
            self.assertEqual(len(alerts), 4, "four copy alerts")
            self.assertEqual(
                [a["address"] for a in alerts][:1],
                [BELLE_COPY_1807],
                "first alert address ascending",
            )
            self.assertNotIn(
                BELLE_SEED,
                [a["address"] for a in alerts],
                "the seed never alerts on itself",
            )
            self.assertEqual(
                alerts[0]["score"], 13.0 / 15.0, "score 13/15 unrounded"
            )
            self.assertEqual(
                sorted(alerts[0]),
                ["address", "label", "score", "seed_address"],
                "exactly the four Alert keys",
            )
        finally:
            store.close()

    def test_univ2_seed_same_code_alerts_at_1_0(self):
        """Seeding one UniswapV2Pair address gives 1.0 alerts on the
        other three same-code addresses; min_score=1.0 keeps three."""
        store = make_block_store()
        try:
            store.add_seed(
                "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
                "UniV2 pair seed",
            )
            alerts = recheck_watchlist(store, min_score=1.0)
            self.assertEqual(len(alerts), 3, "three 1.0 alerts")
            self.assertEqual(
                alerts[0]["address"], UNIV2_ADDRESSES[0],
                "first is the smallest pair address",
            )
            self.assertEqual(alerts[0]["score"], 1.0, "same-code 1.0")
        finally:
            store.close()

    def test_empty_cases_and_seed_addresses_filter(self):
        """No seeds, an empty store and an unknown seed_addresses entry
        give []; a mixed-case seed_addresses filters to that seed."""
        empty = Store(os.path.join(tempfile.mkdtemp(), "t.db"))
        try:
            self.assertEqual(recheck_watchlist(empty), [], "empty store")
        finally:
            empty.close()
        store = make_belle_store()
        try:
            self.assertEqual(
                recheck_watchlist(store), [], "no seeds"
            )
            store.add_seed(BELLE_SEED, "BELLE honeypot")
            self.assertEqual(
                recheck_watchlist(
                    store, seed_addresses=["0x" + "11" * 20]
                ),
                [],
                "unknown seed address matches nothing",
            )
            upper = recheck_watchlist(
                store, seed_addresses=[BELLE_SEED.upper()]
            )
            self.assertEqual(
                len(upper), 4, "mixed-case seed filter still finds the 4"
            )
            again = recheck_watchlist(store)
            self.assertEqual(upper, again, "deterministic on repeat calls")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
