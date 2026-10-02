"""Judge for the phase-14 examples: seeing through standard proxies.

One test per new Contour example (28 of them), asserting every value its
'then' states, exactly: group store, Store Codes And Contracts examples
13-15 and Manage Watchlist example 5; group cluster, Build Clusters
examples 4-5, Find Similar example 3, Match Watchlist example 4, Recheck
Watchlist examples 9-11; group ingest, Ingest Block examples 14-20 and
Follow Chain examples 11-13; group cli, Command Line examples 44-50.
Written from contour.yaml, tests/fixtures/README.md and the finished
code (ethsc/ingest.py, ethsc/store.py, ethsc/cluster.py, ethsc/cli.py),
not from how the code was written.

Offline: FakeRpc, load_hex, block_codes, block_receipts, temp_store and
block_store come from tests/helpers.py; no stub class is defined here,
no network module is imported, and every db lives in its own
tempfile.mkdtemp() directory (helpers.temp_store() and _db_path() below
both go through tempfile.mkdtemp()).
"""

import contextlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from ethsc.cli import main
from ethsc.cluster import build_clusters, find_similar, match_watchlist, \
    recheck_watchlist
from ethsc.fingerprint import fingerprint
from ethsc.ingest import (BEACON_SLOT, IMPL_SLOT, follow_chain, ingest_block,
                          slot_address)
from ethsc.config import PRICES
from ethsc.store import Store
from tests.helpers import (FakeRpc, block_codes, block_receipts, block_store,
                           load_hex, temp_store)

_BLOCK = 26077729
_HEAD = "0x18dea21"

# The seed proxy, its live sibling (same bytecode, same implementation)
# and the implementation itself (tests/fixtures/README.md).
PROXY = "0x0c0105334a50db16b51b2911c9956539753a2cf8"
SIBLING = "0x069c4c579671f8c120b1327a73217d01ea2ec5ea"
IMPL = "0x72b971717e088b59f26d4236be222adb6acd393b"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"

DANGLING_TARGET = "0x1111111111111111111111111111111111111111"
DEAD_ADDRESS = "0xdead00000000000000000000000000000000dead"

# code_id of code_proxy_seed_0c010533.hex and of code_impl_72b97171.hex
# (fingerprint(load_hex(...))["code_id"]), as named by the examples.
PROXY_CODE_ID = "30ccc4ce49c00fae11d7118fc244f29a13788fb32cd4022ee69acc2f15c0e2f5"
IMPL_CODE_ID = "148d598b091197e8547a99bb62fb69d3003cfcad58124c5d847b1de213ecbf28"

# The second-largest implementation group of the seed proxy's bytecode
# (Ingest Block example 18, Command Line example 48).
NEW_IMPL = "0xe440cc08a71694c8229323803f59024e3144630e"
NEW_IMPL_WORD = "0x" + "00" * 12 + NEW_IMPL[2:]

_ZERO_WORD = "0x" + "0" * 64

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures")
with open(os.path.join(_FIXTURES, "storage_26077729.json"), "r",
          encoding="utf-8") as _handle:
    _STORAGE = json.load(_handle)

# The 20 standard-proxy addresses of block 26077729 inside _STORAGE (it
# also carries PROXY and SIBLING, which are not part of the block).
_BLOCK_STD_PROXIES = sorted(
    address for address in _STORAGE if address not in (PROXY, SIBLING)
)


def _implementation_from_storage(address):
    """slot_address of the IMPL_SLOT word, falling back to BEACON_SLOT.

    Mirrors ethsc.ingest.fetch_implementation's own fallback, applied by
    hand to the storage_26077729.json fixture (no get_code involved).
    """
    slots = _STORAGE.get(address, {})
    value = slot_address(slots.get(IMPL_SLOT))
    if value is not None:
        return value
    return slot_address(slots.get(BEACON_SLOT))


def _expected_block_implementations():
    """{address: {"implementation", "code_id": None}} over _BLOCK_STD_PROXIES.

    code_id is always None here: the implementation addresses are not
    present in codes_26077729.json / block_codes(), so a fake get_code
    serving them raises KeyError and nothing is fetched (Ingest Block
    example 15, Follow Chain example 11).
    """
    return {
        address: {"implementation": _implementation_from_storage(address),
                  "code_id": None}
        for address in _BLOCK_STD_PROXIES
    }


def _db_path():
    directory = tempfile.mkdtemp(prefix="ethsc-proxy-judge-")
    return os.path.join(directory, "ethsc.sqlite")


def _setup_proxy_seed_db(path):
    """A fresh db holding the four addresses of Store example 14.

    code_proxy_seed_0c010533.hex at PROXY (block 1, origin "fetched")
    and at SIBLING (block 1, origin "seen"); code_impl_72b97171.hex at
    IMPL (block 1, origin "impl"); code_weth9.hex at WETH (block 1, no
    origin). No set_implementation call here -- callers add their own.
    """
    store = Store(path)
    proxy_code_id = store.put_code(load_hex("code_proxy_seed_0c010533.hex"))
    store.put_address(PROXY, proxy_code_id, 1, origin="fetched")
    store.put_address(SIBLING, proxy_code_id, 1, origin="seen")
    impl_code_id = store.put_code(load_hex("code_impl_72b97171.hex"))
    store.put_address(IMPL, impl_code_id, 1, origin="impl")
    weth_code_id = store.put_code(load_hex("code_weth9.hex"))
    store.put_address(WETH, weth_code_id, 1)
    return store


# The phase-13 schema: addresses has origin but not implementation.
_PHASE13_SCHEMA = """
CREATE TABLE codes (
    code_id TEXT PRIMARY KEY,
    size INTEGER,
    skeleton_hash TEXT,
    selectors TEXT,
    proxy_kind TEXT,
    proxy_target TEXT,
    code BLOB,
    std_proxy INTEGER
);
CREATE TABLE addresses (
    address TEXT PRIMARY KEY,
    code_id TEXT,
    block INTEGER,
    origin TEXT
);
CREATE INDEX addresses_code_id ON addresses(code_id);
CREATE TABLE progress (
    key TEXT PRIMARY KEY,
    block INTEGER
);
CREATE TABLE seeds (
    address TEXT PRIMARY KEY,
    code_id TEXT,
    label TEXT
);
CREATE TABLE ledger (
    day TEXT,
    method TEXT,
    credits INTEGER
);
"""


def _insert_code(conn, code):
    """Plain INSERT of one code into a _PHASE13_SCHEMA codes table."""
    fp = fingerprint(code)
    conn.execute(
        "INSERT OR IGNORE INTO codes (code_id, size, skeleton_hash,"
        " selectors, proxy_kind, proxy_target, code, std_proxy)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            fp["code_id"], fp["size"], fp["skeleton_hash"],
            json.dumps(fp["selectors"]),
            fp["proxy"]["kind"] if fp["proxy"] else None,
            fp["proxy"]["target"] if fp["proxy"] else None,
            sqlite3.Binary(code),
            1 if fp["std_proxy"] else 0,
        ),
    )


def _build_phase13_db(path):
    """A phase-13 database: the 130 codes and 206 addresses of
    codes_26077729.json (addresses with origin, no implementation),
    written by plain INSERTs, origin left NULL."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_PHASE13_SCHEMA)
        codes = block_codes()
        for text in codes.values():
            if text != "0x":
                _insert_code(conn, bytes.fromhex(text[2:]))
        for address, text in sorted(codes.items()):
            if text == "0x":
                conn.execute(
                    "INSERT INTO addresses (address, code_id, block, origin)"
                    " VALUES (?, NULL, ?, NULL)", (address.lower(), _BLOCK))
            else:
                code_id = fingerprint(bytes.fromhex(text[2:]))["code_id"]
                conn.execute(
                    "INSERT INTO addresses (address, code_id, block, origin)"
                    " VALUES (?, ?, ?, NULL)",
                    (address.lower(), code_id, _BLOCK))
        conn.commit()
    finally:
        conn.close()


def _run(argv, rpc=None, sleep=None):
    """main(argv, rpc=rpc, sleep=sleep) with INFURA_API_KEY removed.

    Every Command Line example here passes its own FakeRpc, so main()
    never reaches _chain_rpc()/infura_url(); the removal just keeps the
    test from depending on whatever key happens to be in the shell.
    """
    patcher = mock.patch.dict(os.environ)
    environ = patcher.start()
    environ.pop("INFURA_API_KEY", None)
    try:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv, rpc=rpc, sleep=sleep)
        return code, out.getvalue(), err.getvalue()
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# Store Codes And Contracts examples 13-15, Manage Watchlist example 5.
# ---------------------------------------------------------------------------


class StoreImplementationExamples(unittest.TestCase):

    def test_store_example_13_fresh_schema_and_empty_implementations(self):
        """Store Codes And Contracts example 13: a fresh temp db --
        PRAGMA table_info(addresses) gives address, code_id, block,
        origin, implementation in that order; implementations() is
        {}."""
        path = _db_path()
        store = Store(path)
        try:
            implementations = store.implementations()
        finally:
            store.close()
        conn = sqlite3.connect(path)
        try:
            columns = [row[1] for row in
                      conn.execute("PRAGMA table_info(addresses)").fetchall()]
        finally:
            conn.close()
        self.assertEqual(
            columns, ["address", "code_id", "block", "origin",
                      "implementation"],
            msg="example 13: addresses columns %r" % columns,
        )
        self.assertEqual(
            implementations, {},
            msg="example 13: implementations() must be {} on a fresh db",
        )

    def test_store_example_14_set_implementation_round_trip(self):
        """Store Codes And Contracts example 14: the four-address db --
        implementations() first is {SIBLING, PROXY: both None/None} (the
        WETH9 and implementation rows are not standard proxies and are
        absent); after set_implementation(PROXY, IMPL),
        set_implementation(SIBLING, DANGLING_TARGET) and
        set_implementation(DEAD_ADDRESS, IMPL) (mixed case in),
        implementation() of the three addresses and implementations()
        read back lowercased; DEAD_ADDRESS stays unknown (nothing
        inserted); the reopened db gives the same dict; the four rows
        keep their block and origin."""
        path = _db_path()
        store = _setup_proxy_seed_db(path)
        first = store.implementations()

        store.set_implementation(PROXY.upper(), IMPL.upper())
        store.set_implementation(SIBLING, DANGLING_TARGET)
        store.set_implementation(DEAD_ADDRESS, IMPL)

        impl_of_proxy = store.implementation(PROXY)
        impl_of_sibling = store.implementation(SIBLING)
        impl_of_dead = store.implementation(DEAD_ADDRESS)
        has_dead = store.has_address(DEAD_ADDRESS)
        second = store.implementations()
        store.close()

        self.assertEqual(
            first,
            {
                SIBLING: {"implementation": None, "code_id": None},
                PROXY: {"implementation": None, "code_id": None},
            },
            msg="example 14: implementations() before set_implementation",
        )
        self.assertEqual(
            impl_of_proxy, IMPL,
            msg="example 14: implementation(PROXY) must read back lowercased",
        )
        self.assertEqual(
            impl_of_sibling, DANGLING_TARGET,
            msg="example 14: implementation(SIBLING)",
        )
        self.assertIsNone(
            impl_of_dead,
            msg="example 14: implementation() of an address never stored"
                " must be None",
        )
        self.assertFalse(
            has_dead,
            msg="example 14: set_implementation on an unknown address must"
                " insert nothing",
        )
        self.assertEqual(
            second,
            {
                SIBLING: {"implementation": DANGLING_TARGET, "code_id": None},
                PROXY: {"implementation": IMPL, "code_id": IMPL_CODE_ID},
            },
            msg="example 14: implementations() after set_implementation",
        )

        conn = sqlite3.connect(path)
        try:
            blocks = dict(
                conn.execute("SELECT address, block FROM addresses"))
            origins = dict(
                conn.execute("SELECT address, origin FROM addresses"))
        finally:
            conn.close()
        self.assertEqual(
            blocks, {PROXY: 1, SIBLING: 1, IMPL: 1, WETH: 1},
            msg="example 14: the four rows must keep their block",
        )
        self.assertEqual(
            origins,
            {PROXY: "fetched", SIBLING: "seen", IMPL: "impl", WETH: None},
            msg="example 14: the four rows must keep their origin",
        )

        reopened = Store(path)
        try:
            third = reopened.implementations()
        finally:
            reopened.close()
        self.assertEqual(
            third, second,
            msg="example 14: a reopened db must give the same"
                " implementations() dict",
        )

    def test_store_example_15_phase13_migration_implementations(self):
        """Store Codes And Contracts example 15: a phase-13 database (no
        implementation column) of block 26077729 -- the first open adds
        the column implementation last; implementations() has exactly
        20 entries (the 20 standard-proxy addresses, 17 distinct
        codes), every one {"implementation": None, "code_id": None};
        the file holds 206 rows with implementation NULL (nothing
        rewritten); the second open adds no column and changes
        nothing."""
        path = _db_path()
        _build_phase13_db(path)

        conn = sqlite3.connect(path)
        try:
            before_columns = [row[1] for row in conn.execute(
                "PRAGMA table_info(addresses)").fetchall()]
        finally:
            conn.close()
        self.assertNotIn(
            "implementation", before_columns,
            msg="example 15: the phase-13 db must start without"
                " implementation",
        )

        store = Store(path)
        try:
            implementations = store.implementations()
        finally:
            store.close()
        self.assertEqual(
            len(implementations), 20,
            msg="example 15: implementations() must have 20 entries",
        )
        self.assertTrue(
            all(v == {"implementation": None, "code_id": None}
                for v in implementations.values()),
            msg="example 15: every entry must be unresolved",
        )

        conn = sqlite3.connect(path)
        try:
            after_columns = [row[1] for row in conn.execute(
                "PRAGMA table_info(addresses)").fetchall()]
            null_count = conn.execute(
                "SELECT COUNT(*) FROM addresses WHERE implementation IS NULL"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(
            after_columns[-1], "implementation",
            msg="example 15: implementation must be the last column",
        )
        self.assertEqual(
            null_count, 206,
            msg="example 15: no row may be rewritten on open",
        )

        third = Store(path)
        third.close()
        conn = sqlite3.connect(path)
        try:
            columns_after_second_open = [row[1] for row in conn.execute(
                "PRAGMA table_info(addresses)").fetchall()]
        finally:
            conn.close()
        self.assertEqual(
            after_columns, columns_after_second_open,
            msg="example 15: the second open must add no column",
        )


class ManageWatchlistImplementationExample(unittest.TestCase):

    def test_manage_watchlist_example_5_seed_through_implementation(self):
        """Manage Watchlist example 5: the four-address db after
        set_implementation(PROXY -> IMPL, whose code is stored) and
        set_implementation(SIBLING -> DANGLING_TARGET, which is not
        stored) -- add_seed(PROXY, "proxy-seed"),
        add_seed(SIBLING, "dangling") and add_seed(IMPL, "impl-seed")
        give seeds() with 3 entries sorted by address: SIBLING
        "dangling" with code_id PROXY_CODE_ID (its own, the proxy's
        code), PROXY "proxy-seed" with code_id IMPL_CODE_ID (the
        implementation's), IMPL "impl-seed" with the same
        IMPL_CODE_ID."""
        path = _db_path()
        store = _setup_proxy_seed_db(path)
        store.set_implementation(PROXY, IMPL)
        store.set_implementation(SIBLING, DANGLING_TARGET)

        store.add_seed(PROXY, "proxy-seed")
        store.add_seed(SIBLING, "dangling")
        store.add_seed(IMPL, "impl-seed")
        seeds = store.seeds()
        store.close()

        expected = [
            {"address": SIBLING, "label": "dangling",
             "code_id": PROXY_CODE_ID},
            {"address": PROXY, "label": "proxy-seed",
             "code_id": IMPL_CODE_ID},
            {"address": IMPL, "label": "impl-seed", "code_id": IMPL_CODE_ID},
        ]
        self.assertEqual(seeds, expected, msg="example 5: seeds() %r" % seeds)


# ---------------------------------------------------------------------------
# Build Clusters examples 4-5, Find Similar example 3, Match Watchlist
# example 4, Recheck Watchlist examples 9-11.
# ---------------------------------------------------------------------------


class BuildClustersImplementationExamples(unittest.TestCase):

    def test_build_clusters_example_4_impl_cluster_alongside_the_others(
        self,
    ):
        """Build Clusters example 4: the store from codes_26077729.json
        with set_implementation applied to its 20 standard-proxy
        addresses from storage_26077729.json -- the 15 clusters of
        example 1 unchanged and in the same order, plus exactly one
        impl cluster, last of all: key the shared beacon
        0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598, members the two
        beacon proxies 0xc9eef266... and 0xf6b1117e...; 16 clusters."""
        baseline_store = block_store()
        baseline = build_clusters(baseline_store)
        baseline_store.close()
        self.assertEqual(
            len(baseline), 15,
            msg="example 4: Build Clusters example 1 must give 15 clusters",
        )

        store = block_store()
        for address in _BLOCK_STD_PROXIES:
            implementation = _implementation_from_storage(address)
            self.assertIsNotNone(
                implementation,
                msg="example 4: %s must resolve (README: 0 neither)"
                    % address,
            )
            store.set_implementation(address, implementation)
        clusters = build_clusters(store)
        store.close()

        self.assertEqual(
            clusters[:-1], baseline,
            msg="example 4: the 15 non-impl clusters must be unchanged"
                " and in the same order",
        )
        self.assertEqual(
            len(clusters), 16, msg="example 4: 16 clusters total",
        )
        self.assertEqual(
            clusters[-1],
            {
                "level": "impl",
                "key": "0x985462c9aa4d6c3ad59ae6e1e9c0c11347ed1598",
                "members": [
                    "0xc9eef266834730340a55b6cc24621b31baf55581",
                    "0xf6b1117ec07684d3958cad8beb1b302bfd21103f",
                ],
            },
            msg="example 4: the one impl cluster must be last",
        )

    def test_build_clusters_example_5_two_live_proxies_of_one_implementation(
        self,
    ):
        """Build Clusters example 5: a store holding
        code_proxy_seed_0c010533.hex at PROXY and SIBLING, both with
        implementation IMPL, and code_impl_72b97171.hex at IMPL --
        build_clusters gives exactly [L0 PROXY_CODE_ID {SIBLING, PROXY},
        impl IMPL {SIBLING, PROXY}] both in forward and in reverse
        insertion order; the implementation address is not a member of
        either cluster."""

        def build(reverse):
            store = temp_store()
            proxy_code_id = store.put_code(
                load_hex("code_proxy_seed_0c010533.hex"))
            impl_code_id = store.put_code(load_hex("code_impl_72b97171.hex"))
            pairs = [(PROXY, proxy_code_id), (SIBLING, proxy_code_id)]
            if reverse:
                pairs = list(reversed(pairs))
            for address, code_id in pairs:
                store.put_address(address, code_id, 1)
            store.put_address(IMPL, impl_code_id, 1)
            for address, _ in pairs:
                store.set_implementation(address, IMPL)
            return store

        expected = [
            {"level": "L0", "key": PROXY_CODE_ID,
             "members": [SIBLING, PROXY]},
            {"level": "impl", "key": IMPL, "members": [SIBLING, PROXY]},
        ]

        store_forward = build(False)
        forward = build_clusters(store_forward)
        store_forward.close()
        store_reverse = build(True)
        backward = build_clusters(store_reverse)
        store_reverse.close()

        self.assertEqual(
            forward, expected, msg="example 5: forward insertion order",
        )
        self.assertEqual(
            backward, expected,
            msg="example 5: reverse insertion order must give the same"
                " result",
        )
        self.assertNotIn(
            IMPL, forward[1]["members"],
            msg="example 5: the implementation address must not be a"
                " member of its own impl cluster",
        )


class FindSimilarImplementationExample(unittest.TestCase):

    def test_find_similar_example_3_through_the_implementation(self):
        """Find Similar example 3: the store of Build Clusters example 5
        (both proxies resolved) and a second store made the same way
        but without set_implementation for SIBLING -- on the first
        store, find_similar(PROXY) and find_similar(IMPL) each give the
        other two addresses at 1.0; on the second store, find_similar
        of PROXY gives IMPL only (the unresolved sibling is absent) and
        find_similar of SIBLING gives []."""

        def build(resolve_sibling):
            store = temp_store()
            proxy_code_id = store.put_code(
                load_hex("code_proxy_seed_0c010533.hex"))
            impl_code_id = store.put_code(load_hex("code_impl_72b97171.hex"))
            store.put_address(PROXY, proxy_code_id, 1)
            store.put_address(SIBLING, proxy_code_id, 1)
            store.put_address(IMPL, impl_code_id, 1)
            store.set_implementation(PROXY, IMPL)
            if resolve_sibling:
                store.set_implementation(SIBLING, IMPL)
            return store

        first_store = build(True)
        proxy_similar = find_similar(first_store, PROXY)
        impl_similar = find_similar(first_store, IMPL)
        first_store.close()

        second_store = build(False)
        proxy_similar_2 = find_similar(second_store, PROXY)
        sibling_similar_2 = find_similar(second_store, SIBLING)
        second_store.close()

        self.assertEqual(
            proxy_similar, [(SIBLING, 1.0), (IMPL, 1.0)],
            msg="example 3: find_similar(PROXY) on the first store",
        )
        self.assertEqual(
            impl_similar, [(SIBLING, 1.0), (PROXY, 1.0)],
            msg="example 3: find_similar(IMPL) on the first store",
        )
        self.assertEqual(
            proxy_similar_2, [(IMPL, 1.0)],
            msg="example 3: find_similar(PROXY) on the second store must"
                " give IMPL only",
        )
        self.assertEqual(
            sibling_similar_2, [],
            msg="example 3: find_similar(SIBLING) on the second store must"
                " be [] (unresolved standard proxy)",
        )


class MatchWatchlistImplementationExample(unittest.TestCase):

    def test_match_watchlist_example_4_seed_carries_implementation_code_id(
        self,
    ):
        """Match Watchlist example 4: the store of Build Clusters
        example 5 with add_seed(PROXY, "proxy-seed") -- one alert
        {seed_address: PROXY, label: "proxy-seed", score: 1.0} for the
        implementation bytes; [] for the proxy's own bytes."""
        store = temp_store()
        proxy_code_id = store.put_code(load_hex("code_proxy_seed_0c010533.hex"))
        impl_code_id = store.put_code(load_hex("code_impl_72b97171.hex"))
        store.put_address(PROXY, proxy_code_id, 1)
        store.put_address(SIBLING, proxy_code_id, 1)
        store.put_address(IMPL, impl_code_id, 1)
        store.set_implementation(PROXY, IMPL)
        store.set_implementation(SIBLING, IMPL)
        store.add_seed(PROXY, "proxy-seed")

        impl_alerts = match_watchlist(store, load_hex("code_impl_72b97171.hex"))
        proxy_alerts = match_watchlist(
            store, load_hex("code_proxy_seed_0c010533.hex"))
        store.close()

        self.assertEqual(
            impl_alerts,
            [{"seed_address": PROXY, "label": "proxy-seed", "score": 1.0}],
            msg="example 4: the implementation bytes must alert at 1.0",
        )
        self.assertEqual(
            proxy_alerts, [],
            msg="example 4: a proxy's own bytes must still score 0.0",
        )


def _build_recheck_store(resolve_sibling=True):
    """code_proxy_seed_0c010533.hex at PROXY (origin "fetched") and
    SIBLING (origin "seen"), code_impl_72b97171.hex at IMPL (origin
    "impl"); PROXY's implementation is always set to IMPL, SIBLING's
    only when resolve_sibling (Recheck Watchlist examples 9-11)."""
    store = temp_store()
    proxy_code_id = store.put_code(load_hex("code_proxy_seed_0c010533.hex"))
    impl_code_id = store.put_code(load_hex("code_impl_72b97171.hex"))
    store.put_address(PROXY, proxy_code_id, 1, origin="fetched")
    store.put_address(SIBLING, proxy_code_id, 1, origin="seen")
    store.put_address(IMPL, impl_code_id, 1, origin="impl")
    store.set_implementation(PROXY, IMPL)
    if resolve_sibling:
        store.set_implementation(SIBLING, IMPL)
    return store


class RecheckWatchlistImplementationExamples(unittest.TestCase):

    def test_recheck_watchlist_example_9_proxies_of_a_seeded_implementation(
        self,
    ):
        """Recheck Watchlist example 9: the store of Build Clusters
        example 5 with add_seed(IMPL, "impl-seed") -- recheck_watchlist
        called twice gives, both times, exactly [SIBLING at 1.0 origin
        "seen", PROXY at 1.0 origin "fetched"] against seed IMPL."""
        store = _build_recheck_store()
        store.add_seed(IMPL, "impl-seed")
        first = recheck_watchlist(store)
        second = recheck_watchlist(store)
        store.close()

        expected = [
            {"address": SIBLING, "seed_address": IMPL, "label": "impl-seed",
             "score": 1.0, "origin": "seen"},
            {"address": PROXY, "seed_address": IMPL, "label": "impl-seed",
             "score": 1.0, "origin": "fetched"},
        ]
        self.assertEqual(
            first, expected, msg="example 9: first recheck_watchlist call",
        )
        self.assertEqual(
            second, expected,
            msg="example 9: second recheck_watchlist call must give the"
                " same list",
        )

    def test_recheck_watchlist_example_10_proxy_seed_alerts_on_impl_and_siblings(
        self,
    ):
        """Recheck Watchlist example 10: the same store seeded instead
        with add_seed(PROXY, "proxy-seed") -- exactly [SIBLING at 1.0
        origin "seen", IMPL at 1.0 origin "impl"]; the seed itself is
        absent."""
        store = _build_recheck_store()
        store.add_seed(PROXY, "proxy-seed")
        alerts = recheck_watchlist(store)
        store.close()

        expected = [
            {"address": SIBLING, "seed_address": PROXY,
             "label": "proxy-seed", "score": 1.0, "origin": "seen"},
            {"address": IMPL, "seed_address": PROXY, "label": "proxy-seed",
             "score": 1.0, "origin": "impl"},
        ]
        self.assertEqual(
            alerts, expected,
            msg="example 10: recheck_watchlist must exclude the seed itself",
        )

    def test_recheck_watchlist_example_11_unresolved_sibling_keeps_phase_9(
        self,
    ):
        """Recheck Watchlist example 11: the second store of Find
        Similar example 3 (SIBLING with NULL implementation), seeded
        "impl-seed" at IMPL gives one alert for PROXY at 1.0 (the
        unresolved sibling is absent); seeded "dangling" at SIBLING
        instead gives []."""
        store_impl_seed = _build_recheck_store(resolve_sibling=False)
        store_impl_seed.add_seed(IMPL, "impl-seed")
        first = recheck_watchlist(store_impl_seed)
        store_impl_seed.close()

        store_dangling_seed = _build_recheck_store(resolve_sibling=False)
        store_dangling_seed.add_seed(SIBLING, "dangling")
        second = recheck_watchlist(store_dangling_seed)
        store_dangling_seed.close()

        self.assertEqual(
            first,
            [{"address": PROXY, "seed_address": IMPL, "label": "impl-seed",
              "score": 1.0, "origin": "fetched"}],
            msg="example 11: the unresolved sibling must be absent from"
                " the alert list",
        )
        self.assertEqual(
            second, [],
            msg="example 11: seeding the unresolved sibling itself must"
                " alert on nothing",
        )


# ---------------------------------------------------------------------------
# Ingest Block examples 14-20, Follow Chain examples 11-13.
# ---------------------------------------------------------------------------


class IngestBlockImplementationExamples(unittest.TestCase):

    def test_ingest_block_example_14_get_storage_none_reads_no_slot(self):
        """Ingest Block example 14: receipts_26077729.json, a fresh
        store and a fake get_code serving codes_26077729.json,
        get_storage left None -- the stats of example 1 with upgrades
        [] (ten keys exactly); implementations() has 20 entries, every
        one unresolved; counts() addresses 206, codes 130."""
        codes = block_codes()

        def get_code(address, block):
            return codes[address]

        store = temp_store()
        stats = ingest_block(_BLOCK, block_receipts(), get_code, store,
                             get_storage=None)
        implementations = store.implementations()
        counts = store.counts()
        store.close()

        self.assertEqual(
            sorted(stats.keys()),
            sorted(["candidates", "known", "fetched", "contracts", "eoas",
                    "failed", "deferred", "complete", "alerts", "upgrades"]),
            msg="example 14: stats must have exactly ten keys",
        )
        self.assertEqual(
            stats["upgrades"], [], msg="example 14: upgrades must be []",
        )
        self.assertEqual(
            stats["candidates"], 206, msg="example 14: candidates 206",
        )
        self.assertEqual(
            stats["contracts"], 147, msg="example 14: contracts 147",
        )
        self.assertEqual(
            len(implementations), 20,
            msg="example 14: implementations() must have 20 entries",
        )
        self.assertTrue(
            all(v == {"implementation": None, "code_id": None}
                for v in implementations.values()),
            msg="example 14: every entry must be unresolved (get_storage"
                " left None)",
        )
        self.assertEqual(
            counts["addresses"], 206, msg="example 14: counts() addresses",
        )
        self.assertEqual(
            counts["codes"], 130, msg="example 14: counts() codes",
        )

    def test_ingest_block_example_15_resolves_the_blocks_proxies(self):
        """Ingest Block example 15: receipts_26077729.json, a fresh
        store, a fake get_code serving codes_26077729.json and a fake
        get_storage serving storage_26077729.json; then the same with
        workers=8 into a second fresh store -- both give upgrades []
        and the same implementations() (the 20 fixture entries, code_id
        None); get_storage was called 23 times, 20 IMPL_SLOT and 3
        BEACON_SLOT, every call block 26077729; a second ingest into
        the first store gives known 206, fetched 0, upgrades [] and 23
        more get_storage calls, implementations() unchanged."""
        codes = block_codes()

        def get_code(address, block):
            return codes[address]

        calls = []

        def get_storage(address, slot, block):
            calls.append((address, slot, block))
            return _STORAGE.get(address, {}).get(slot, _ZERO_WORD)

        store = temp_store()
        stats = ingest_block(_BLOCK, block_receipts(), get_code, store,
                             get_storage=get_storage)
        implementations = store.implementations()
        counts = store.counts()

        expected_implementations = _expected_block_implementations()
        self.assertEqual(
            stats["upgrades"], [], msg="example 15: upgrades must be []",
        )
        self.assertEqual(
            implementations, expected_implementations,
            msg="example 15: implementations() must equal the fixture"
                " resolution",
        )
        self.assertEqual(
            implementations.get("0x07696dcab55e62cfef953666b29fe1970518cb00"),
            {"implementation": "0xfd03064ff0f29e3113a1198c2694fc8c10bd35e5",
             "code_id": None},
            msg="example 15: 0x07696dcab... must resolve to its fixture"
                " implementation",
        )
        self.assertEqual(
            implementations.get("0x28b5a0e9c621a5badaa536219b3a228c8168cf5d"),
            {"implementation": "0x555e272506c06e7e559d57418563742afe363ec8",
             "code_id": None},
            msg="example 15: 0x28b5a0e9... must resolve to its fixture"
                " implementation",
        )
        self.assertEqual(
            counts["addresses"], 206, msg="example 15: counts() addresses",
        )
        self.assertEqual(
            counts["codes"], 130, msg="example 15: counts() codes",
        )
        impl_calls = [c for c in calls if c[1] == IMPL_SLOT]
        beacon_calls = [c for c in calls if c[1] == BEACON_SLOT]
        self.assertEqual(
            len(calls), 23, msg="example 15: get_storage call count",
        )
        self.assertEqual(
            len(impl_calls), 20, msg="example 15: IMPL_SLOT call count",
        )
        self.assertEqual(
            len(beacon_calls), 3, msg="example 15: BEACON_SLOT call count",
        )
        self.assertTrue(
            all(c[2] == _BLOCK for c in calls),
            msg="example 15: every get_storage call must carry block"
                " 26077729",
        )

        workers_calls = []

        def get_storage_workers(address, slot, block):
            workers_calls.append((address, slot, block))
            return _STORAGE.get(address, {}).get(slot, _ZERO_WORD)

        store_workers = temp_store()
        stats_workers = ingest_block(
            _BLOCK, block_receipts(), get_code, store_workers,
            get_storage=get_storage_workers, workers=8)
        self.assertEqual(
            stats_workers["upgrades"], [],
            msg="example 15: workers=8 upgrades must be []",
        )
        self.assertEqual(
            store_workers.implementations(), implementations,
            msg="example 15: workers=8 must give an equal implementations()",
        )
        self.assertEqual(
            store_workers.counts(), counts,
            msg="example 15: workers=8 must give equal counts()",
        )
        store_workers.close()

        second_calls = []

        def get_storage_second(address, slot, block):
            second_calls.append((address, slot, block))
            return _STORAGE.get(address, {}).get(slot, _ZERO_WORD)

        stats_second = ingest_block(
            _BLOCK, block_receipts(), get_code, store,
            get_storage=get_storage_second)
        self.assertEqual(
            stats_second["known"], 206, msg="example 15: second call known",
        )
        self.assertEqual(
            stats_second["fetched"], 0, msg="example 15: second call fetched",
        )
        self.assertEqual(
            stats_second["upgrades"], [],
            msg="example 15: second call upgrades",
        )
        self.assertEqual(
            len(second_calls), 23,
            msg="example 15: the known proxies must be re-read (23 more"
                " get_storage calls)",
        )
        self.assertEqual(
            store.implementations(), implementations,
            msg="example 15: implementations() must be unchanged after the"
                " second call",
        )
        store.close()

    def test_ingest_block_example_16_candidate_proxy_alerts_on_known_impl(
        self,
    ):
        """Ingest Block example 16: a store holding
        code_impl_72b97171.hex at IMPL (origin "fetched") seeded
        "impl-seed"; a block whose receipts are [{"to": PROXY}]; a fake
        get_code serving the proxy and the implementation; get_storage
        from storage_26077729.json -- candidates 1, known 0, fetched 1,
        contracts 1, upgrades []; one alert for PROXY against seed IMPL
        at 1.0, origin "seen"; on_alerts and on_upgrades each called
        once with an equal value; implementations() has PROXY resolved
        to IMPL with its code_id; get_code called once (PROXY only);
        get_storage called once (IMPL_SLOT only); counts() addresses
        2."""
        store = temp_store()
        impl_code_id = store.put_code(load_hex("code_impl_72b97171.hex"))
        store.put_address(IMPL, impl_code_id, 1, origin="fetched")
        store.add_seed(IMPL, "impl-seed")

        get_code_calls = []

        def get_code(address, block):
            get_code_calls.append((address, block))
            if address == PROXY:
                return "0x" + load_hex("code_proxy_seed_0c010533.hex").hex()
            if address == IMPL:
                return "0x" + load_hex("code_impl_72b97171.hex").hex()
            raise KeyError(address)

        get_storage_calls = []

        def get_storage(address, slot, block):
            get_storage_calls.append((address, slot, block))
            return _STORAGE.get(address, {}).get(slot, _ZERO_WORD)

        alerts_sink = []
        upgrades_sink = []
        stats = ingest_block(
            _BLOCK, [{"to": PROXY}], get_code, store, get_storage=get_storage,
            on_alerts=alerts_sink.append, on_upgrades=upgrades_sink.append)
        implementations = store.implementations()
        counts = store.counts()
        store.close()

        self.assertEqual(stats["candidates"], 1, msg="example 16: candidates")
        self.assertEqual(stats["known"], 0, msg="example 16: known")
        self.assertEqual(stats["fetched"], 1, msg="example 16: fetched")
        self.assertEqual(stats["contracts"], 1, msg="example 16: contracts")
        self.assertEqual(stats["eoas"], 0, msg="example 16: eoas")
        self.assertEqual(stats["failed"], 0, msg="example 16: failed")
        self.assertEqual(stats["deferred"], 0, msg="example 16: deferred")
        self.assertTrue(stats["complete"], msg="example 16: complete")
        self.assertEqual(stats["upgrades"], [], msg="example 16: upgrades")
        self.assertEqual(
            stats["alerts"],
            [{"address": PROXY, "seed_address": IMPL, "label": "impl-seed",
              "score": 1.0, "origin": "seen"}],
            msg="example 16: alerts",
        )
        self.assertEqual(
            len(alerts_sink), 1, msg="example 16: on_alerts call count",
        )
        self.assertEqual(
            alerts_sink[0], stats["alerts"],
            msg="example 16: on_alerts must get an equal list",
        )
        self.assertEqual(
            len(upgrades_sink), 1, msg="example 16: on_upgrades call count",
        )
        self.assertEqual(
            upgrades_sink[0], [],
            msg="example 16: on_upgrades must get an equal (empty) list",
        )
        self.assertEqual(
            implementations,
            {PROXY: {"implementation": IMPL, "code_id": IMPL_CODE_ID}},
            msg="example 16: implementations()",
        )
        self.assertEqual(
            get_code_calls, [(PROXY, _BLOCK)],
            msg="example 16: get_code must be called once, for PROXY only",
        )
        self.assertEqual(
            get_storage_calls, [(PROXY, IMPL_SLOT, _BLOCK)],
            msg="example 16: get_storage must be called once, IMPL_SLOT"
                " only",
        )
        self.assertEqual(
            counts["addresses"], 2, msg="example 16: counts() addresses",
        )

    def test_ingest_block_example_17_implementation_stored_like_a_candidate(
        self,
    ):
        """Ingest Block example 17: the block, get_code and get_storage
        of example 16 into a fresh store with no seeds, and into a
        second fresh store seeded "impl copy seed" at
        DANGLING_TARGET holding code_impl_72b97171.hex -- first store:
        fetched 1, contracts 1, alerts [], upgrades []; get_code called
        twice in order (PROXY, IMPL); origins() {PROXY: "seen", IMPL:
        "impl"}; code_of(IMPL) equals the fixture bytes; counts()
        addresses 2, codes 2. Second store: the same stats, and alerts
        exactly [PROXY at 1.0 origin "seen", IMPL at 1.0 origin
        "impl"] against seed DANGLING_TARGET."""

        def get_code(address, block):
            if address == PROXY:
                return "0x" + load_hex("code_proxy_seed_0c010533.hex").hex()
            if address == IMPL:
                return "0x" + load_hex("code_impl_72b97171.hex").hex()
            raise KeyError(address)

        def get_storage(address, slot, block):
            return _STORAGE.get(address, {}).get(slot, _ZERO_WORD)

        store1 = temp_store()
        get_code_calls = []

        def get_code_1(address, block):
            get_code_calls.append((address, block))
            return get_code(address, block)

        stats1 = ingest_block(_BLOCK, [{"to": PROXY}], get_code_1, store1,
                              get_storage=get_storage)
        self.assertEqual(stats1["fetched"], 1, msg="example 17: store1 fetched")
        self.assertEqual(
            stats1["contracts"], 1, msg="example 17: store1 contracts")
        self.assertEqual(stats1["alerts"], [], msg="example 17: store1 alerts")
        self.assertEqual(
            stats1["upgrades"], [], msg="example 17: store1 upgrades")
        self.assertEqual(
            get_code_calls, [(PROXY, _BLOCK), (IMPL, _BLOCK)],
            msg="example 17: get_code must be called twice, PROXY then IMPL",
        )
        self.assertEqual(
            store1.origins(), {PROXY: "seen", IMPL: "impl"},
            msg="example 17: store1 origins()",
        )
        self.assertEqual(
            store1.code_of(IMPL), load_hex("code_impl_72b97171.hex"),
            msg="example 17: store1 code_of(IMPL)",
        )
        counts1 = store1.counts()
        store1.close()
        self.assertEqual(
            counts1["addresses"], 2, msg="example 17: store1 counts addresses")
        self.assertEqual(
            counts1["codes"], 2, msg="example 17: store1 counts codes")

        store2 = temp_store()
        impl_code_id = store2.put_code(load_hex("code_impl_72b97171.hex"))
        store2.put_address(DANGLING_TARGET, impl_code_id, 1)
        store2.add_seed(DANGLING_TARGET, "impl copy seed")
        stats2 = ingest_block(_BLOCK, [{"to": PROXY}], get_code, store2,
                              get_storage=get_storage)
        store2.close()
        self.assertEqual(stats2["fetched"], 1, msg="example 17: store2 fetched")
        self.assertEqual(
            stats2["contracts"], 1, msg="example 17: store2 contracts")
        self.assertEqual(
            stats2["alerts"],
            [
                {"address": PROXY, "seed_address": DANGLING_TARGET,
                 "label": "impl copy seed", "score": 1.0, "origin": "seen"},
                {"address": IMPL, "seed_address": DANGLING_TARGET,
                 "label": "impl copy seed", "score": 1.0, "origin": "impl"},
            ],
            msg="example 17: store2 alerts",
        )

    def test_ingest_block_example_18_upgrade_alert(self):
        """Ingest Block example 18: the first store of example 17
        (PROXY resolved to IMPL); the same block; a fake get_code
        serving the proxy for PROXY and code_weth9.hex for NEW_IMPL; a
        fake get_storage answering NEW_IMPL_WORD for (PROXY, IMPL_SLOT)
        -- first call: known 1, fetched 0, alerts [], upgrades exactly
        [{"address": PROXY, "old": IMPL, "new": NEW_IMPL, "block":
        26077730}]; on_upgrades called once with an equal list;
        implementation(PROXY) becomes NEW_IMPL; NEW_IMPL is stored with
        the WETH9 bytes and origin "impl"; get_code called once, for
        NEW_IMPL. Second and third calls (get_storage raising OSError,
        then answering the zero word for both slots): upgrades [], the
        implementation stays NEW_IMPL, nothing stored."""
        store = temp_store()
        proxy_code_id = store.put_code(load_hex("code_proxy_seed_0c010533.hex"))
        store.put_address(PROXY, proxy_code_id, 1)
        store.set_implementation(PROXY, IMPL)

        get_code_calls = []

        def get_code(address, block):
            get_code_calls.append((address, block))
            if address == PROXY:
                return "0x" + load_hex("code_proxy_seed_0c010533.hex").hex()
            if address == NEW_IMPL:
                return "0x" + load_hex("code_weth9.hex").hex()
            raise KeyError(address)

        def get_storage(address, slot, block):
            return NEW_IMPL_WORD

        upgrades_sink = []
        stats1 = ingest_block(
            26077730, [{"to": PROXY}], get_code, store, get_storage=get_storage,
            on_upgrades=upgrades_sink.append)
        self.assertEqual(stats1["known"], 1, msg="example 18: first call known")
        self.assertEqual(
            stats1["fetched"], 0, msg="example 18: first call fetched")
        self.assertEqual(
            stats1["alerts"], [], msg="example 18: first call alerts")
        self.assertEqual(
            stats1["upgrades"],
            [{"address": PROXY, "old": IMPL, "new": NEW_IMPL,
              "block": 26077730}],
            msg="example 18: first call upgrades",
        )
        self.assertEqual(
            len(upgrades_sink), 1,
            msg="example 18: on_upgrades call count",
        )
        self.assertEqual(
            upgrades_sink[0], stats1["upgrades"],
            msg="example 18: on_upgrades must get an equal list",
        )
        self.assertEqual(
            store.implementation(PROXY), NEW_IMPL,
            msg="example 18: implementation(PROXY) must be NEW_IMPL",
        )
        self.assertEqual(
            store.origins().get(NEW_IMPL), "impl",
            msg="example 18: NEW_IMPL must be stored with origin impl",
        )
        self.assertEqual(
            store.code_of(NEW_IMPL), load_hex("code_weth9.hex"),
            msg="example 18: NEW_IMPL must be stored with the WETH9 bytes",
        )
        self.assertEqual(
            get_code_calls, [(NEW_IMPL, 26077730)],
            msg="example 18: get_code must be called once, for NEW_IMPL",
        )

        def get_storage_raise(address, slot, block):
            raise OSError("no slot")

        stats2 = ingest_block(26077731, [{"to": PROXY}], get_code, store,
                              get_storage=get_storage_raise)
        self.assertEqual(
            stats2["upgrades"], [], msg="example 18: second call upgrades")
        self.assertEqual(
            store.implementation(PROXY), NEW_IMPL,
            msg="example 18: second call must not change the implementation",
        )

        def get_storage_zero(address, slot, block):
            return _ZERO_WORD

        stats3 = ingest_block(26077732, [{"to": PROXY}], get_code, store,
                              get_storage=get_storage_zero)
        store.close()
        self.assertEqual(
            stats3["upgrades"], [], msg="example 18: third call upgrades")

    def test_ingest_block_example_19_pre_phase14_row_resolved_silently(self):
        """Ingest Block example 19: a store holding
        code_proxy_seed_0c010533.hex at PROXY by put_address with no
        implementation (a row from before phase 14); the block,
        get_code and get_storage of example 16 -- known 1, fetched 0,
        upgrades [] and on_upgrades called once with [] (the first
        resolution of a NULL row is silent); implementation(PROXY)
        becomes IMPL, stored with the fixture bytes and origin "impl";
        alerts [] (the proxy was known: no match for it)."""
        store = temp_store()
        proxy_code_id = store.put_code(load_hex("code_proxy_seed_0c010533.hex"))
        store.put_address(PROXY, proxy_code_id, 1)

        def get_code(address, block):
            if address == PROXY:
                return "0x" + load_hex("code_proxy_seed_0c010533.hex").hex()
            if address == IMPL:
                return "0x" + load_hex("code_impl_72b97171.hex").hex()
            raise KeyError(address)

        def get_storage(address, slot, block):
            return _STORAGE.get(address, {}).get(slot, _ZERO_WORD)

        upgrades_sink = []
        stats = ingest_block(_BLOCK, [{"to": PROXY}], get_code, store,
                             get_storage=get_storage,
                             on_upgrades=upgrades_sink.append)
        implementation = store.implementation(PROXY)
        origin_of_impl = store.origins().get(IMPL)
        code_of_impl = store.code_of(IMPL)
        store.close()

        self.assertEqual(stats["known"], 1, msg="example 19: known")
        self.assertEqual(stats["fetched"], 0, msg="example 19: fetched")
        self.assertEqual(stats["upgrades"], [], msg="example 19: upgrades")
        self.assertEqual(
            upgrades_sink, [[]],
            msg="example 19: on_upgrades must be called once with []",
        )
        self.assertEqual(
            implementation, IMPL,
            msg="example 19: implementation(PROXY) must become IMPL",
        )
        self.assertEqual(
            origin_of_impl, "impl",
            msg="example 19: IMPL must be stored with origin impl",
        )
        self.assertEqual(
            code_of_impl, load_hex("code_impl_72b97171.hex"),
            msg="example 19: IMPL must be stored with the fixture bytes",
        )
        self.assertEqual(
            stats["alerts"], [],
            msg="example 19: the proxy was known; no alert for it",
        )

    def test_ingest_block_example_20_tolerant_parser_over_get_storage(self):
        """Ingest Block example 20: the block and get_code of example
        16; four get_storage variants -- raising OSError; answering the
        zero word for both slots; answering "garbage" for IMPL_SLOT and
        the zero word for BEACON_SLOT; answering a word with a non-zero
        prefix for IMPL_SLOT -- every time: fetched 1, contracts 1,
        upgrades [], alerts [], implementations() unresolved, get_code
        called once, counts() addresses 1; get_storage called once in
        the OSError case, twice in the other three; slot_address of the
        zero word, "garbage" and the malformed word is None, and
        slot_address of a correctly formed word is the address it
        carries."""
        malformed_prefix = (
            "0x01" + "00" * 22 + "72b971717e088b59f26d4236be222adb6acd393b"
        )

        def get_code(address, block):
            return "0x" + load_hex("code_proxy_seed_0c010533.hex").hex()

        def run_case(get_storage):
            store = temp_store()
            get_code_calls = []

            def gc(address, block):
                get_code_calls.append((address, block))
                return get_code(address, block)

            get_storage_calls = []

            def gs(address, slot, block):
                get_storage_calls.append((address, slot, block))
                return get_storage(address, slot, block)

            stats = ingest_block(_BLOCK, [{"to": PROXY}], gc, store,
                                 get_storage=gs)
            implementations = store.implementations()
            counts = store.counts()
            store.close()
            return stats, implementations, get_code_calls, get_storage_calls, counts

        def gs_raise(address, slot, block):
            raise OSError("no slot")

        def gs_zero(address, slot, block):
            return _ZERO_WORD

        def gs_garbage(address, slot, block):
            return "garbage" if slot == IMPL_SLOT else _ZERO_WORD

        def gs_malformed(address, slot, block):
            return malformed_prefix if slot == IMPL_SLOT else _ZERO_WORD

        cases = (
            ("raising", gs_raise, 1),
            ("zero word", gs_zero, 2),
            ("garbage", gs_garbage, 2),
            ("malformed prefix", gs_malformed, 2),
        )
        for name, get_storage, expected_gs_calls in cases:
            stats, implementations, get_code_calls, get_storage_calls, counts = (
                run_case(get_storage)
            )
            self.assertEqual(
                stats["fetched"], 1, msg="example 20 (%s): fetched" % name)
            self.assertEqual(
                stats["contracts"], 1, msg="example 20 (%s): contracts" % name)
            self.assertEqual(
                stats["upgrades"], [], msg="example 20 (%s): upgrades" % name)
            self.assertEqual(
                stats["alerts"], [], msg="example 20 (%s): alerts" % name)
            self.assertEqual(
                implementations,
                {PROXY: {"implementation": None, "code_id": None}},
                msg="example 20 (%s): implementations()" % name,
            )
            self.assertEqual(
                len(get_code_calls), 1,
                msg="example 20 (%s): get_code call count" % name,
            )
            self.assertEqual(
                counts["addresses"], 1,
                msg="example 20 (%s): counts() addresses" % name,
            )
            self.assertEqual(
                len(get_storage_calls), expected_gs_calls,
                msg="example 20 (%s): get_storage call count" % name,
            )

        self.assertIsNone(
            slot_address(_ZERO_WORD),
            msg="example 20: slot_address of the zero word must be None",
        )
        self.assertIsNone(
            slot_address("garbage"),
            msg="example 20: slot_address of a malformed string must be"
                " None",
        )
        self.assertIsNone(
            slot_address(malformed_prefix),
            msg="example 20: slot_address of a non-zero-prefix word must"
                " be None",
        )
        self.assertEqual(
            slot_address("0x" + "00" * 12 + IMPL[2:]), IMPL,
            msg="example 20: slot_address of a correctly formed word must"
                " decode the address",
        )


class FollowChainImplementationExamples(unittest.TestCase):

    def test_follow_chain_example_11_storage_at_80_credits(self):
        """Follow Chain example 11: FakeRpc(storage=storage_26077729.json)
        over the fixtures, progress 26077728, the Infura prices,
        daily_budget 3000000, day "2026-10-01"; then the same with
        workers=8 into a second fresh store; then with code_tag
        "latest" into a third -- blocks 1, progress 26077729, upgrades
        [] and spent("2026-10-01") 19400 all three times;
        implementations() equals Ingest Block example 15;
        eth_getStorageAt carries tag "0x18dea21" in the first two
        passes and "latest" in the third; the summary has exactly the
        keys blocks, stopped, progress, alerts, day, upgrades."""

        def run(workers=None, code_tag=None):
            store = temp_store()
            store.set_progress(_BLOCK - 1)
            rpc = FakeRpc(storage=_STORAGE, head=_HEAD)
            summary = follow_chain(rpc, store, daily_budget=3000000,
                                   day="2026-10-01", prices=PRICES,
                                   workers=workers, code_tag=code_tag)
            return summary, store, rpc

        summary1, store1, rpc1 = run()
        self.assertEqual(summary1["blocks"], 1, msg="example 11: blocks")
        self.assertEqual(
            summary1["progress"], _BLOCK, msg="example 11: progress")
        self.assertEqual(
            summary1["upgrades"], [], msg="example 11: upgrades")
        self.assertEqual(
            store1.spent("2026-10-01"), 19400,
            msg="example 11: spent(2026-10-01)",
        )
        self.assertEqual(
            sorted(summary1.keys()),
            sorted(["blocks", "stopped", "progress", "alerts", "day",
                    "upgrades"]),
            msg="example 11: summary must have exactly six keys",
        )
        expected_implementations = _expected_block_implementations()
        self.assertEqual(
            store1.implementations(), expected_implementations,
            msg="example 11: implementations() must equal Ingest Block"
                " example 15",
        )
        storage_calls_1 = [c for c in rpc1.calls if c[0] == "eth_getStorageAt"]
        self.assertTrue(
            all(call[1][2] == _HEAD for call in storage_calls_1),
            msg="example 11: tag must be the head hex in the first pass",
        )

        summary2, store2, rpc2 = run(workers=8)
        self.assertEqual(summary2["blocks"], 1, msg="example 11: workers=8 blocks")
        self.assertEqual(
            summary2["upgrades"], [], msg="example 11: workers=8 upgrades")
        self.assertEqual(
            store2.spent("2026-10-01"), 19400,
            msg="example 11: workers=8 spent(2026-10-01)",
        )
        self.assertEqual(
            store2.implementations(), expected_implementations,
            msg="example 11: workers=8 implementations()",
        )

        summary3, store3, rpc3 = run(code_tag="latest")
        self.assertEqual(
            summary3["upgrades"], [], msg="example 11: code_tag latest upgrades")
        self.assertEqual(
            store3.spent("2026-10-01"), 19400,
            msg="example 11: code_tag latest spent(2026-10-01)",
        )
        storage_calls_3 = [c for c in rpc3.calls if c[0] == "eth_getStorageAt"]
        self.assertTrue(
            all(call[1][2] == "latest" for call in storage_calls_3),
            msg="example 11: tag must be \"latest\" in the third pass",
        )
        store1.close()
        store2.close()
        store3.close()

    def test_follow_chain_example_12_budget_respected_over_slot_reads(self):
        """Follow Chain example 12: the fake rpc of example 11, progress
        26077728, the same prices, daily_budget 18000, day
        "2026-10-01", workers None -- blocks 1, progress 26077729,
        stopped None, spent 17880: 17560 after the candidates, then
        exactly 4 successful slot reads (320 credits) -- the three
        proxies 0x07696dcab..., 0x11457ef2... (IMPL_SLOT zero, then
        BEACON_SLOT) and 0x28b5a0e9... -- none for the other 17
        proxies; implementations() has those three resolved and 17
        None; exactly 4 eth_getStorageAt calls."""
        store = temp_store()
        store.set_progress(_BLOCK - 1)
        rpc = FakeRpc(storage=_STORAGE, head=_HEAD)
        summary = follow_chain(rpc, store, daily_budget=18000,
                               day="2026-10-01", prices=PRICES, workers=None)
        implementations = store.implementations()
        spent = store.spent("2026-10-01")
        store.close()

        self.assertEqual(summary["blocks"], 1, msg="example 12: blocks")
        self.assertEqual(
            summary["progress"], _BLOCK, msg="example 12: progress")
        self.assertIsNone(summary["stopped"], msg="example 12: stopped")
        self.assertEqual(spent, 17880, msg="example 12: spent")

        storage_calls = [c for c in rpc.calls if c[0] == "eth_getStorageAt"]
        self.assertEqual(
            len(storage_calls), 4,
            msg="example 12: exactly 4 eth_getStorageAt calls",
        )
        resolved = {
            address: value["implementation"]
            for address, value in implementations.items()
            if value["implementation"] is not None
        }
        self.assertEqual(
            resolved,
            {
                "0x07696dcab55e62cfef953666b29fe1970518cb00":
                    "0xfd03064ff0f29e3113a1198c2694fc8c10bd35e5",
                "0x11457ef2b71087d18651106f23ed59dd8ec0da6c":
                    "0x365e8991d29d79dc6b56df59858f25fee1601f70",
                "0x28b5a0e9c621a5badaa536219b3a228c8168cf5d":
                    "0x555e272506c06e7e559d57418563742afe363ec8",
            },
            msg="example 12: only the three affordable proxies may resolve",
        )
        unresolved = sum(
            1 for value in implementations.values()
            if value["implementation"] is None
        )
        self.assertEqual(
            unresolved, 17, msg="example 12: 17 proxies must stay unresolved",
        )

    def test_follow_chain_example_13_node_refusing_the_slot_keeps_phase_9(
        self,
    ):
        """Follow Chain example 13: FakeRpc() without storage (so
        eth_getStorageAt raises KeyError) over the fixtures, progress
        26077728, the Infura prices, daily_budget 3000000, day
        "2026-10-01" -- blocks 1, progress 26077729, spent 17560 (a
        raising read is not charged), implementations() has 20 entries,
        all None, upgrades []."""
        store = temp_store()
        store.set_progress(_BLOCK - 1)
        rpc = FakeRpc(head=_HEAD)
        summary = follow_chain(rpc, store, daily_budget=3000000,
                               day="2026-10-01", prices=PRICES)
        implementations = store.implementations()
        spent = store.spent("2026-10-01")
        store.close()

        self.assertEqual(summary["blocks"], 1, msg="example 13: blocks")
        self.assertEqual(
            summary["progress"], _BLOCK, msg="example 13: progress")
        self.assertEqual(spent, 17560, msg="example 13: spent")
        self.assertEqual(
            summary["upgrades"], [], msg="example 13: upgrades")
        self.assertEqual(
            len(implementations), 20,
            msg="example 13: implementations() must have 20 entries",
        )
        self.assertTrue(
            all(value["implementation"] is None
                for value in implementations.values()),
            msg="example 13: every entry must stay unresolved",
        )


# ---------------------------------------------------------------------------
# Command Line examples 44-50.
# ---------------------------------------------------------------------------


def _impl_copy_seed_db():
    """A fresh db holding code_impl_72b97171.hex at DANGLING_TARGET
    (put_address, block 1) seeded "impl copy seed" (Command Line
    examples 47-48)."""
    path = _db_path()
    store = Store(path)
    impl_code_id = store.put_code(load_hex("code_impl_72b97171.hex"))
    store.put_address(DANGLING_TARGET, impl_code_id, 1)
    store.add_seed(DANGLING_TARGET, "impl copy seed")
    store.close()
    return path


class CommandLineImplementationExamples(unittest.TestCase):

    def test_command_line_example_44_seed_add_fetch_resolves_implementation(
        self,
    ):
        """Command Line example 44: a fresh db and FakeRpc(codes={PROXY:
        proxy text, IMPL: implementation text}, storage=storage
        fixture, head="0x18dea21") -- seed add --fetch PROXY
        "proxy-seed" exits 0; fake.calls is exactly [eth_blockNumber,
        eth_getCode(PROXY), eth_getStorageAt(PROXY, IMPL_SLOT),
        eth_getCode(IMPL)]; the store holds implementation(PROXY) ==
        IMPL, origins() {PROXY: "fetched", IMPL: "impl"}, code_of(IMPL)
        the fixture bytes, and seeds() [{PROXY, "proxy-seed",
        IMPL_CODE_ID}]; stdout is exactly one ALERT line."""
        db = _db_path()
        fake = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
            },
            storage=_STORAGE, head=_HEAD,
        )
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", PROXY, "--label",
             "proxy-seed"], rpc=fake)
        self.assertEqual(code, 0, msg="example 44: exit code, stderr %r" % err)
        self.assertEqual(err, "", msg="example 44: stderr not empty")
        self.assertEqual(
            fake.calls,
            [
                ("eth_blockNumber", []),
                ("eth_getCode", [PROXY, "latest"]),
                ("eth_getStorageAt", [PROXY, IMPL_SLOT, "latest"]),
                ("eth_getCode", [IMPL, "latest"]),
            ],
            msg="example 44: fake.calls %r" % fake.calls,
        )
        store = Store(db)
        try:
            implementation = store.implementation(PROXY)
            origins = store.origins()
            code_of_impl = store.code_of(IMPL)
            seeds = store.seeds()
        finally:
            store.close()
        self.assertEqual(
            implementation, IMPL, msg="example 44: implementation(PROXY)")
        self.assertEqual(
            origins, {PROXY: "fetched", IMPL: "impl"},
            msg="example 44: origins()",
        )
        self.assertEqual(
            code_of_impl, load_hex("code_impl_72b97171.hex"),
            msg="example 44: code_of(IMPL)",
        )
        self.assertEqual(
            seeds,
            [{"address": PROXY, "label": "proxy-seed",
              "code_id": IMPL_CODE_ID}],
            msg="example 44: seeds()",
        )
        self.assertEqual(
            out, "ALERT\t%s\t%s\tproxy-seed\t1.0000\timpl\n" % (IMPL, PROXY),
            msg="example 44: stdout %r" % out,
        )

    def test_command_line_example_45_second_live_proxy_alerts_at_1(self):
        """Command Line example 45: the db of example 44, then seed add
        --fetch SIBLING "sibling" (whose slot also reads IMPL) -- exit
        0, three more calls (eth_blockNumber, eth_getCode(SIBLING),
        eth_getStorageAt(SIBLING, IMPL_SLOT)), no eth_getCode of IMPL
        (held); stdout the two sibling ALERT lines; recheck gives
        exactly four lines in order; recheck --origin impl gives the
        last two only."""
        db = _db_path()
        fake1 = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
            },
            storage=_STORAGE, head=_HEAD,
        )
        _run(["--db", db, "seed", "add", "--fetch", PROXY, "--label",
              "proxy-seed"], rpc=fake1)

        fake2 = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
                SIBLING: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
            },
            storage=_STORAGE, head=_HEAD,
        )
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", SIBLING, "--label",
             "sibling"], rpc=fake2)
        self.assertEqual(code, 0, msg="example 45: seed add exit code")
        self.assertEqual(err, "", msg="example 45: seed add stderr")
        self.assertEqual(
            fake2.calls,
            [
                ("eth_blockNumber", []),
                ("eth_getCode", [SIBLING, "latest"]),
                ("eth_getStorageAt", [SIBLING, IMPL_SLOT, "latest"]),
            ],
            msg="example 45: fake2.calls %r (no eth_getCode of IMPL, held)"
                % fake2.calls,
        )
        self.assertEqual(
            out,
            (
                "ALERT\t%s\t%s\tsibling\t1.0000\tfetched\n"
                "ALERT\t%s\t%s\tsibling\t1.0000\timpl\n"
            ) % (PROXY, SIBLING, IMPL, SIBLING),
            msg="example 45: seed add stdout %r" % out,
        )

        code, out, err = _run(["--db", db, "recheck"])
        self.assertEqual(code, 0, msg="example 45: recheck exit code")
        expected_recheck = (
            "ALERT\t%s\t%s\tproxy-seed\t1.0000\tfetched\n"
            "ALERT\t%s\t%s\tsibling\t1.0000\tfetched\n"
            "ALERT\t%s\t%s\tsibling\t1.0000\timpl\n"
            "ALERT\t%s\t%s\tproxy-seed\t1.0000\timpl\n"
        ) % (SIBLING, PROXY, PROXY, SIBLING, IMPL, SIBLING, IMPL, PROXY)
        self.assertEqual(
            out, expected_recheck, msg="example 45: recheck stdout %r" % out,
        )

        code, out, err = _run(["--db", db, "recheck", "--origin", "impl"])
        self.assertEqual(
            code, 0, msg="example 45: recheck --origin impl exit code")
        expected_impl_only = (
            "ALERT\t%s\t%s\tsibling\t1.0000\timpl\n"
            "ALERT\t%s\t%s\tproxy-seed\t1.0000\timpl\n"
        ) % (IMPL, SIBLING, IMPL, PROXY)
        self.assertEqual(
            out, expected_impl_only,
            msg="example 45: recheck --origin impl stdout %r" % out,
        )

    def test_command_line_example_46_tolerant_parser_phase_9_stands(self):
        """Command Line example 46: a fresh db and FakeRpc(codes={PROXY:
        proxy text}, storage={}) (every slot reads the zero word); then
        a fresh db and FakeRpc(codes=the same, head="0x18dea21") with no
        storage (eth_getStorageAt raises KeyError) -- exit 0 both times,
        empty stdout and stderr; implementation(PROXY) is None; seeds()
        code_id is PROXY_CODE_ID (the proxy's own); the first fake saw
        4 calls, the second 3; origins() is {PROXY: "fetched"} both
        times."""
        codes = {PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex()}

        db1 = _db_path()
        fake1 = FakeRpc(codes=codes, storage={}, head=_HEAD)
        code1, out1, err1 = _run(
            ["--db", db1, "seed", "add", "--fetch", PROXY, "--label", "L"],
            rpc=fake1)
        self.assertEqual(code1, 0, msg="example 46: first exit code")
        self.assertEqual(out1, "", msg="example 46: first stdout")
        self.assertEqual(err1, "", msg="example 46: first stderr")
        self.assertEqual(
            len(fake1.calls), 4, msg="example 46: first fake call count",
        )
        store1 = Store(db1)
        try:
            self.assertIsNone(
                store1.implementation(PROXY),
                msg="example 46: first implementation(PROXY)",
            )
            self.assertEqual(
                store1.seeds(),
                [{"address": PROXY, "label": "L", "code_id": PROXY_CODE_ID}],
                msg="example 46: first seeds()",
            )
            self.assertEqual(
                store1.origins(), {PROXY: "fetched"},
                msg="example 46: first origins()",
            )
        finally:
            store1.close()

        db2 = _db_path()
        fake2 = FakeRpc(codes=codes, head=_HEAD)
        code2, out2, err2 = _run(
            ["--db", db2, "seed", "add", "--fetch", PROXY, "--label", "L"],
            rpc=fake2)
        self.assertEqual(code2, 0, msg="example 46: second exit code")
        self.assertEqual(out2, "", msg="example 46: second stdout")
        self.assertEqual(err2, "", msg="example 46: second stderr")
        self.assertEqual(
            len(fake2.calls), 3, msg="example 46: second fake call count",
        )
        store2 = Store(db2)
        try:
            self.assertIsNone(
                store2.implementation(PROXY),
                msg="example 46: second implementation(PROXY)",
            )
            self.assertEqual(
                store2.origins(), {PROXY: "fetched"},
                msg="example 46: second origins()",
            )
        finally:
            store2.close()

    def test_command_line_example_47_backfill_proxy_and_impl_alerts(self):
        """Command Line example 47: a db holding code_impl_72b97171.hex
        at DANGLING_TARGET seeded "impl copy seed"; backfill over the
        block carrying PROXY -- exit 0 each time; the plain run prints
        the PROXY alert (origin "seen") then the IMPL alert (origin
        "impl"); --alert-on created prints nothing; --alert-on seen
        prints the first line only; every db holds IMPL with origin
        "impl" and implementation(PROXY) == IMPL."""

        def make_fake():
            return FakeRpc(
                codes={
                    PROXY: "0x"
                           + load_hex("code_proxy_seed_0c010533.hex").hex(),
                    IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
                },
                receipts=[{"to": PROXY}], storage=_STORAGE, head=_HEAD,
            )

        plain_line = (
            "ALERT\t%s\t%s\timpl copy seed\t1.0000\tseen\n"
            % (PROXY, DANGLING_TARGET)
        )
        impl_line = (
            "ALERT\t%s\t%s\timpl copy seed\t1.0000\timpl\n"
            % (IMPL, DANGLING_TARGET)
        )
        for alert_on, expected_out in (
            (None, plain_line + impl_line),
            ("created", ""),
            ("seen", plain_line),
        ):
            db = _impl_copy_seed_db()
            argv = ["--db", db, "backfill", "--from", str(_BLOCK), "--to",
                   str(_BLOCK)]
            if alert_on is not None:
                argv += ["--alert-on", alert_on]
            code, out, err = _run(argv, rpc=make_fake())
            self.assertEqual(
                code, 0, msg="example 47 (%r): exit code, stderr %r"
                % (alert_on, err))
            self.assertEqual(
                err, "", msg="example 47 (%r): stderr" % alert_on)
            self.assertEqual(
                out, expected_out,
                msg="example 47 (%r): stdout %r" % (alert_on, out),
            )
            store = Store(db)
            try:
                self.assertEqual(
                    store.origins().get(IMPL), "impl",
                    msg="example 47 (%r): IMPL origin" % alert_on,
                )
                self.assertEqual(
                    store.implementation(PROXY), IMPL,
                    msg="example 47 (%r): implementation(PROXY)" % alert_on,
                )
            finally:
                store.close()

    def test_command_line_example_48_backfill_upgrade_alert(self):
        """Command Line example 48: the first db of example 47 (PROXY
        resolved to IMPL) and FakeRpc over a slot that now reads
        NEW_IMPL -- backfill --alert-on created -- exit 0; stdout is
        exactly one UPGRADE line (--alert-on does not touch it; no
        ALERT: the proxy is known); the store holds implementation(
        PROXY) == NEW_IMPL and NEW_IMPL with the WETH9 bytes, origin
        "impl"."""
        db = _impl_copy_seed_db()
        fake1 = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
            },
            receipts=[{"to": PROXY}], storage=_STORAGE, head=_HEAD,
        )
        _run(["--db", db, "backfill", "--from", str(_BLOCK), "--to",
              str(_BLOCK)], rpc=fake1)

        fake2 = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                NEW_IMPL: "0x" + load_hex("code_weth9.hex").hex(),
            },
            receipts=[{"to": PROXY}],
            storage={PROXY: {IMPL_SLOT: NEW_IMPL_WORD}}, head=_HEAD,
        )
        code, out, err = _run(
            ["--db", db, "backfill", "--from", str(_BLOCK), "--to",
             str(_BLOCK), "--alert-on", "created"], rpc=fake2)
        self.assertEqual(code, 0, msg="example 48: exit code, stderr %r" % err)
        self.assertEqual(err, "", msg="example 48: stderr")
        self.assertEqual(
            out,
            "UPGRADE\t%s\t%s\t%s\t%d\n" % (PROXY, IMPL, NEW_IMPL, _BLOCK),
            msg="example 48: stdout %r" % out,
        )
        store = Store(db)
        try:
            self.assertEqual(
                store.implementation(PROXY), NEW_IMPL,
                msg="example 48: implementation(PROXY)",
            )
            self.assertEqual(
                store.origins().get(NEW_IMPL), "impl",
                msg="example 48: NEW_IMPL origin",
            )
            self.assertEqual(
                store.code_of(NEW_IMPL), load_hex("code_weth9.hex"),
                msg="example 48: NEW_IMPL code",
            )
        finally:
            store.close()

    def test_command_line_example_49_resolving_a_pre_phase14_seed_by_hand(
        self,
    ):
        """Command Line example 49: a db holding
        code_proxy_seed_0c010533.hex at PROXY by put_address (block 1,
        origin "fetched", no implementation), and the FakeRpc of
        example 44 -- seed add --fetch PROXY "proxy-seed" exits 0;
        fake.calls is exactly [eth_blockNumber, eth_getStorageAt(PROXY,
        IMPL_SLOT), eth_getCode(IMPL)] -- no eth_getCode of the held
        proxy; the store and stdout line are those of example 44; a
        second identical call makes no rpc call at all and prints the
        same line."""
        db = _db_path()
        store = Store(db)
        proxy_code_id = store.put_code(load_hex("code_proxy_seed_0c010533.hex"))
        store.put_address(PROXY, proxy_code_id, 1, origin="fetched")
        store.close()

        fake1 = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
            },
            storage=_STORAGE, head=_HEAD,
        )
        code1, out1, err1 = _run(
            ["--db", db, "seed", "add", "--fetch", PROXY, "--label",
             "proxy-seed"], rpc=fake1)
        self.assertEqual(code1, 0, msg="example 49: first exit code")
        self.assertEqual(err1, "", msg="example 49: first stderr")
        self.assertEqual(
            fake1.calls,
            [
                ("eth_blockNumber", []),
                ("eth_getStorageAt", [PROXY, IMPL_SLOT, "latest"]),
                ("eth_getCode", [IMPL, "latest"]),
            ],
            msg="example 49: fake1.calls %r (no eth_getCode of the held"
                " proxy)" % fake1.calls,
        )
        expected_line = (
            "ALERT\t%s\t%s\tproxy-seed\t1.0000\timpl\n" % (IMPL, PROXY)
        )
        self.assertEqual(
            out1, expected_line, msg="example 49: first stdout %r" % out1,
        )
        store2 = Store(db)
        try:
            self.assertEqual(
                store2.implementation(PROXY), IMPL,
                msg="example 49: implementation(PROXY)",
            )
            self.assertEqual(
                store2.origins().get(IMPL), "impl",
                msg="example 49: IMPL origin",
            )
        finally:
            store2.close()

        fake2 = FakeRpc(fail=AssertionError("no rpc call expected"))
        code2, out2, err2 = _run(
            ["--db", db, "seed", "add", "--fetch", PROXY, "--label",
             "proxy-seed"], rpc=fake2)
        self.assertEqual(code2, 0, msg="example 49: second exit code")
        self.assertEqual(err2, "", msg="example 49: second stderr")
        self.assertEqual(
            fake2.calls, [],
            msg="example 49: the second identical call must make no rpc"
                " call at all",
        )
        self.assertEqual(
            out2, expected_line, msg="example 49: second stdout %r" % out2,
        )

    def test_command_line_example_50_cluster_clusters_top_similar_through_impl(
        self,
    ):
        """Command Line example 50: the db after example 45 (PROXY and
        SIBLING resolved to IMPL) -- cluster PROXY prints the L0 line
        then the impl line, both with flags "-"; clusters top prints
        the matching two-member lines; similar PROXY prints SIBLING
        then IMPL, both at 1.0000, flags "-"."""
        db = _db_path()
        fake1 = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
            },
            storage=_STORAGE, head=_HEAD,
        )
        _run(["--db", db, "seed", "add", "--fetch", PROXY, "--label",
              "proxy-seed"], rpc=fake1)
        fake2 = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
                SIBLING: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
            },
            storage=_STORAGE, head=_HEAD,
        )
        _run(["--db", db, "seed", "add", "--fetch", SIBLING, "--label",
              "sibling"], rpc=fake2)

        code, out, err = _run(["--db", db, "cluster", PROXY])
        self.assertEqual(code, 0, msg="example 50: cluster exit code")
        self.assertEqual(
            out,
            (
                "L0\t%s\t%s,%s\t-\n"
                "impl\t%s\t%s,%s\t-\n"
            ) % (PROXY_CODE_ID, SIBLING, PROXY, IMPL, SIBLING, PROXY),
            msg="example 50: cluster stdout %r" % out,
        )

        code, out, err = _run(["--db", db, "clusters", "top"])
        self.assertEqual(code, 0, msg="example 50: clusters top exit code")
        self.assertEqual(
            out,
            "L0\t%s\t2\nimpl\t%s\t2\n" % (PROXY_CODE_ID, IMPL),
            msg="example 50: clusters top stdout %r" % out,
        )

        code, out, err = _run(["--db", db, "similar", PROXY])
        self.assertEqual(code, 0, msg="example 50: similar exit code")
        self.assertEqual(
            out,
            "%s\t1.0000\t-\n%s\t1.0000\t-\n" % (SIBLING, IMPL),
            msg="example 50: similar stdout %r" % out,
        )


if __name__ == "__main__":
    unittest.main()
