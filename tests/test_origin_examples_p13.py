"""Judge for the phase-13 examples: origin of a candidate.

One test per new Contour example (17 of them), asserting every value its
'then' states, exactly: group ingest, Discover Candidates 3-4 and Ingest
Block 11-13; group store, Store Codes And Contracts 10-12; group cluster,
Recheck Watchlist 8; group cli, Command Line 36-43. Written from
contour.yaml and tests/fixtures/README.md and the finished code, not from
how the code was written. Offline: FakeRpc, load_hex, block_codes,
block_receipts, temp_store and block_store come from tests/helpers.py; no
stub class is defined here, no network module is imported, and every db
lives in its own tempfile.mkdtemp() directory.
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
from ethsc.cluster import recheck_watchlist
from ethsc.fingerprint import fingerprint
from ethsc.ingest import candidate_origins, discover_candidates, ingest_block
from ethsc.store import Store
from tests.helpers import (FakeRpc, block_codes, block_receipts, block_store,
                           load_hex, temp_store)

_BLOCK = 26077729
_HEAD = "0x18dea21"

# The one deploy and the two byte-identical/near-identical candidates of
# block 26077729, used by Ingest Block 12 and Command Line 36-39.
_B53C = "0xb53c071bdb35d21aa1216b084f79c372d71053d5"
_C02AAA = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
_FF7431 = "0xff74317e948695297acb79cb2de06111f5cc16b3"
_DEPLOY_SEED = "0x1111111111111111111111111111111111111111"

# The UniswapV2Pair seed and its siblings (Recheck Watchlist 8).
_UNIV2_PAIR = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
_UNIV2_SIBLINGS = [
    "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
    "0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c",
    "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f",
]
_SOLC6_PAIR = "0xcf6daab95c476106eca715d48de4b13287ffdeaa"

# The BELLE seed and its four copies (Command Line 41, 43).
_BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_COPIES = (
    ("0x1807090dd15a6f58e00fd769e32ebf20ee610385",
     "code_belle_copy_1807090d.hex"),
    ("0x2141be5f2afa674c94167ab167a478a56cb539f5",
     "code_belle_copy_2141be5f.hex"),
    ("0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a",
     "code_belle_copy_46cadea5.hex"),
    ("0x6411bed82614b91ef655d82486e0bd3a13d2eb8c",
     "code_belle_copy_6411bed8.hex"),
)

# The ALERT lines of the deploy-seed setup of Command Line 36, reused by
# examples 37, 38 and 39.
_CREATED_LINE = (
    "ALERT\t%s\t%s\tdeployed in 26077729\t1.0000\tcreated\n"
    % (_B53C, _DEPLOY_SEED)
)
_SEEN_LINE_1 = (
    "ALERT\t%s\t%s\tdeployed in 26077729\t0.8182\tseen\n"
    % (_C02AAA, _DEPLOY_SEED)
)
_SEEN_LINE_2 = (
    "ALERT\t%s\t%s\tdeployed in 26077729\t1.0000\tseen\n"
    % (_FF7431, _DEPLOY_SEED)
)
_ALL_LINES = _CREATED_LINE + _SEEN_LINE_1 + _SEEN_LINE_2

# The phase-12 schema: codes already has std_proxy and addresses already
# has the index addresses_code_id (both phase 11), but addresses has no
# origin column yet.
_PHASE12_SCHEMA = """
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
    block INTEGER
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


def _db_path():
    directory = tempfile.mkdtemp(prefix="ethsc-origin-judge-")
    return os.path.join(directory, "ethsc.sqlite")


def _insert_code(conn, code):
    """Plain INSERT of one code into a _PHASE12_SCHEMA codes table."""
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
    return fp["code_id"]


def _build_phase12_db(path):
    """A hand-built phase-12 database of block 26077729: 130 codes, 206
    addresses (59 with code_id NULL), addresses with no origin column,
    written by plain INSERTs."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_PHASE12_SCHEMA)
        codes = block_codes()
        for text in codes.values():
            if text != "0x":
                _insert_code(conn, bytes.fromhex(text[2:]))
        for address, text in sorted(codes.items()):
            if text == "0x":
                conn.execute(
                    "INSERT INTO addresses (address, code_id, block)"
                    " VALUES (?, NULL, ?)", (address.lower(), _BLOCK))
            else:
                code_id = fingerprint(bytes.fromhex(text[2:]))["code_id"]
                conn.execute(
                    "INSERT INTO addresses (address, code_id, block)"
                    " VALUES (?, ?, ?)", (address.lower(), code_id, _BLOCK))
        conn.commit()
    finally:
        conn.close()


def _build_phase12_belle_db(path):
    """A phase-12 database holding code_belle.hex at _BELLE, seeded
    "BELLE honeypot", and the four BELLE copies, written by plain
    INSERTs; addresses has no origin column."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_PHASE12_SCHEMA)
        belle_code = load_hex("code_belle.hex")
        belle_id = _insert_code(conn, belle_code)
        conn.execute(
            "INSERT INTO addresses (address, code_id, block)"
            " VALUES (?, ?, ?)", (_BELLE, belle_id, _BLOCK))
        for address, fixture in _COPIES:
            code_id = _insert_code(conn, load_hex(fixture))
            conn.execute(
                "INSERT INTO addresses (address, code_id, block)"
                " VALUES (?, ?, ?)", (address, code_id, _BLOCK))
        conn.execute(
            "INSERT INTO seeds (address, code_id, label) VALUES (?, ?, ?)",
            (_BELLE, belle_id, "BELLE honeypot"),
        )
        conn.commit()
    finally:
        conn.close()


def _run(argv, rpc=None, sleep=None):
    """main(argv, rpc=rpc, sleep=sleep) with INFURA_API_KEY removed."""
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


def _interrupting_sleep(_seconds):
    raise KeyboardInterrupt


def _setup_deploy_seed_db(db):
    """A fresh db holding at _DEPLOY_SEED the code of _B53C (block 1, no
    origin), seeded "deployed in 26077729" -- the setup of Command Line
    36, 37, 38 and 39."""
    store = Store(db)
    try:
        codes = block_codes()
        code_id = store.put_code(bytes.fromhex(codes[_B53C][2:]))
        store.put_address(_DEPLOY_SEED, code_id, 1)
        store.add_seed(_DEPLOY_SEED, "deployed in 26077729")
    finally:
        store.close()


class DiscoverCandidatesOriginExamples(unittest.TestCase):
    """Discover Candidates examples 3-4 (phase 13: candidate_origins)."""

    def test_discover_candidates_example_3_full_fixture(self):
        """Discover Candidates example 3: candidate_origins over the 218
        receipts of block 26077729 gives a dict of 206 entries whose keys
        equal discover_candidates of the same list; exactly one value is
        "created" (0xb53c071b…, the contractAddress of receipt 207, which
        also emits a log in the block), the other 205 are "seen"."""
        receipts = block_receipts()
        got = candidate_origins(receipts)
        self.assertEqual(
            set(got.keys()), set(discover_candidates(receipts)),
            msg="example 3: keys differ from discover_candidates",
        )
        self.assertEqual(len(got), 206, msg="example 3: 206 entries")
        created = [addr for addr, origin in got.items()
                  if origin == "created"]
        self.assertEqual(
            created, [_B53C],
            msg="example 3: exactly one created address, %s" % _B53C,
        )
        seen_count = sum(1 for origin in got.values() if origin == "seen")
        self.assertEqual(seen_count, 205, msg="example 3: 205 seen")

    def test_discover_candidates_example_4_tolerant_parser(self):
        """Discover Candidates example 4: a tolerant list -- None, "x", a
        dict with null to/contractAddress, a to with null logs, and a
        dict whose contractAddress wins over a log of the same address --
        gives {0x1807090d…: "seen", 0xb53c071b…: "created"}, no
        exception; and {} for an empty list."""
        receipts = [
            None,
            "x",
            {"to": None, "contractAddress": None},
            {"to": "0x1807090DD15A6F58E00FD769E32EBF20EE610385",
             "logs": None},
            {
                "to": None,
                "contractAddress": "0xB53C071BDB35D21AA1216B084F79C372D71053D5",
                "logs": [
                    {"address": "0xb53c071bdb35d21aa1216b084f79c372d71053d5"},
                    "y",
                    {"address": None},
                ],
            },
        ]
        got = candidate_origins(receipts)
        expected = {
            "0x1807090dd15a6f58e00fd769e32ebf20ee610385": "seen",
            "0xb53c071bdb35d21aa1216b084f79c372d71053d5": "created",
        }
        self.assertEqual(got, expected,
                         msg="example 4: unexpected dict %r" % got)
        self.assertEqual(candidate_origins([]), {},
                         msg="example 4: [] must give {}")


class IngestBlockOriginExamples(unittest.TestCase):
    """Ingest Block examples 11-13 (phase 13: origin stored and alerted)."""

    def test_ingest_block_example_11_sequential_and_workers_agree(self):
        """Ingest Block example 11: receipts_26077729.json into a fresh
        store, then the same with workers=8 into a second fresh store --
        store.origins() has 206 entries both times, equal dicts:
        0xb53c071b… "created", the other 205 "seen" (eoas included); the
        stats are those of example 1 (candidates 206, fetched 206,
        contracts 147, eoas 59, failed 0, complete True; 130 codes)."""
        codes = block_codes()
        get_code = lambda address, block: codes[address]

        store_seq = temp_store()
        stats_seq = ingest_block(_BLOCK, block_receipts(), get_code,
                                 store_seq)
        store_par = temp_store()
        stats_par = ingest_block(_BLOCK, block_receipts(), get_code,
                                 store_par, workers=8)

        origins_seq = store_seq.origins()
        origins_par = store_par.origins()
        self.assertEqual(len(origins_seq), 206,
                         msg="example 11: 206 entries (sequential)")
        self.assertEqual(origins_seq, origins_par,
                         msg="example 11: sequential and workers=8 differ")
        self.assertEqual(origins_seq.get(_B53C), "created",
                         msg="example 11: %s must be created" % _B53C)
        seen_count = sum(1 for o in origins_seq.values() if o == "seen")
        self.assertEqual(seen_count, 205, msg="example 11: 205 seen")

        for stats in (stats_seq, stats_par):
            self.assertEqual(stats["candidates"], 206,
                             msg="example 11: candidates 206")
            self.assertEqual(stats["fetched"], 206,
                             msg="example 11: fetched 206")
            self.assertEqual(stats["contracts"], 147,
                             msg="example 11: contracts 147")
            self.assertEqual(stats["eoas"], 59, msg="example 11: eoas 59")
            self.assertEqual(stats["failed"], 0, msg="example 11: failed 0")
            self.assertTrue(stats["complete"],
                            msg="example 11: complete True")
        self.assertEqual(len(store_seq.fingerprints()), 130,
                         msg="example 11: 130 codes stored")

    def test_ingest_block_example_12_created_and_seen_alerts(self):
        """Ingest Block example 12: a store with 0x1111… holding the code
        of 0xb53c071b…, seeded "deployed in 26077729", and a fake
        get_code serving codes_26077729.json -- ingest_block over the
        fixture block gives alerts exactly [0xb53c071b… 1.0 created,
        0xc02aaa39… 0.8182 seen, 0xff74317e… 1.0 seen], each dict with
        exactly the five keys; on_alerts was called once with an equal
        list."""
        codes = block_codes()
        store = temp_store()
        code_id = store.put_code(bytes.fromhex(codes[_B53C][2:]))
        store.put_address(_DEPLOY_SEED, code_id, 1)
        store.add_seed(_DEPLOY_SEED, "deployed in 26077729")

        sink_calls = []
        get_code = lambda address, block: codes[address]
        stats = ingest_block(_BLOCK, block_receipts(), get_code, store,
                             watch=0.8, on_alerts=sink_calls.append)

        self.assertEqual(len(sink_calls), 1,
                         msg="example 12: on_alerts called once")
        self.assertEqual(stats["alerts"], sink_calls[0],
                         msg="example 12: on_alerts got an unequal list")
        alerts = stats["alerts"]
        self.assertEqual(len(alerts), 3, msg="example 12: 3 alerts")
        self.assertEqual(
            [alert["address"] for alert in alerts],
            [_B53C, _C02AAA, _FF7431],
            msg="example 12: alerts not ordered by address",
        )
        for alert in alerts:
            self.assertEqual(
                set(alert.keys()),
                {"address", "seed_address", "label", "score", "origin"},
                msg="example 12: alert keys %r" % alert,
            )
            self.assertEqual(alert["seed_address"], _DEPLOY_SEED,
                             msg="example 12: seed_address")
            self.assertEqual(alert["label"], "deployed in 26077729",
                             msg="example 12: label")
        self.assertEqual(alerts[0]["origin"], "created",
                         msg="example 12: 0xb53c071b… is created")
        self.assertAlmostEqual(alerts[0]["score"], 1.0, places=9,
                               msg="example 12: 0xb53c071b… score 1.0")
        self.assertEqual(alerts[1]["origin"], "seen",
                         msg="example 12: 0xc02aaa39… is seen")
        self.assertAlmostEqual(alerts[1]["score"], 9 / 11, places=9,
                               msg="example 12: 0xc02aaa39… score 9/11")
        self.assertEqual(alerts[2]["origin"], "seen",
                         msg="example 12: 0xff74317e… is seen")
        self.assertAlmostEqual(alerts[2]["score"], 1.0, places=9,
                               msg="example 12: 0xff74317e… score 1.0")

    def test_ingest_block_example_13_created_vs_seen_same_candidate(self):
        """Ingest Block example 13: a store seeded with code_belle.hex
        "BELLE honeypot", and a fake get_code serving the BELLE copy at
        0x1807090d… -- ingest_block with that address as a
        contractAddress gives origin "created", as a to gives "seen";
        store.origins() maps the copy to the same origin."""
        copy_address = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
        copy_text = "0x" + load_hex("code_belle_copy_1807090d.hex").hex()
        get_code = lambda address, block: copy_text

        def _belle_store():
            store = temp_store()
            code_id = store.put_code(load_hex("code_belle.hex"))
            store.put_address(_BELLE, code_id, _BLOCK)
            store.add_seed(_BELLE, "BELLE honeypot")
            return store

        store_created = _belle_store()
        stats_created = ingest_block(
            1, [{"contractAddress": copy_address}], get_code, store_created)
        store_seen = _belle_store()
        stats_seen = ingest_block(
            1, [{"to": copy_address}], get_code, store_seen)

        self.assertEqual(len(stats_created["alerts"]), 1,
                         msg="example 13: one alert (created path)")
        self.assertEqual(stats_created["alerts"][0]["origin"], "created",
                         msg="example 13: contractAddress gives created")
        self.assertEqual(len(stats_seen["alerts"]), 1,
                         msg="example 13: one alert (seen path)")
        self.assertEqual(stats_seen["alerts"][0]["origin"], "seen",
                         msg="example 13: to gives seen")
        self.assertAlmostEqual(
            stats_created["alerts"][0]["score"], 13 / 15, places=9,
            msg="example 13: score 13/15 (created path)")
        self.assertAlmostEqual(
            stats_seen["alerts"][0]["score"], 13 / 15, places=9,
            msg="example 13: score 13/15 (seen path)")
        self.assertEqual(
            store_created.origins().get(copy_address), "created",
            msg="example 13: store.origins() disagrees with the alert"
                " (created path)",
        )
        self.assertEqual(
            store_seen.origins().get(copy_address), "seen",
            msg="example 13: store.origins() disagrees with the alert"
                " (seen path)",
        )


class StoreOriginExamples(unittest.TestCase):
    """Store Codes And Contracts examples 10-12 (phase 13: the column
    origin, put_address(..., origin=None), origins())."""

    def test_store_example_10_fresh_schema_and_empty_origins(self):
        """Store Codes And Contracts example 10: a fresh temp db --
        PRAGMA table_info(addresses) gives address, code_id, block,
        origin in that order; origins() is {}."""
        path = _db_path()
        store = Store(path)
        try:
            empty = store.origins()
        finally:
            store.close()
        self.assertEqual(empty, {}, msg="example 10: origins() not {}")

        conn = sqlite3.connect(path)
        try:
            columns = [row[1] for row in
                       conn.execute("PRAGMA table_info(addresses)").fetchall()]
        finally:
            conn.close()
        self.assertEqual(
            columns, ["address", "code_id", "block", "origin",
                      "implementation"],
            msg="example 10: addresses columns %r" % columns,
        )

    def test_store_example_11_put_address_origin_first_record_wins(self):
        """Store Codes And Contracts example 11: a fresh temp db and the
        code_id of code_belle.hex -- put_address with origin "created",
        "seen", no origin, then a known address with a different origin
        -- origins() is {EOA: "seen", created-addr: "created",
        unknown-addr: "unknown"} both before and after a reopen; the
        second put_address on the known address changes nothing."""
        path = _db_path()
        store = Store(path)
        code_id = store.put_code(load_hex("code_belle.hex"))
        addr_created = "0x1807090DD15A6F58E00FD769E32EBF20EE610385"
        addr_eoa_seen = "0x023697eda1dfbe331c2cf791ef2f6089e73e3230"
        addr_unknown = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
        store.put_address(addr_created, code_id, 1, origin="created")
        store.put_address(addr_eoa_seen, None, 1, origin="seen")
        store.put_address(addr_unknown, code_id, 1)
        store.put_address(addr_created.lower(), code_id, 2, origin="seen")
        got = store.origins()
        store.close()

        expected = {
            "0x023697eda1dfbe331c2cf791ef2f6089e73e3230": "seen",
            "0x1807090dd15a6f58e00fd769e32ebf20ee610385": "created",
            "0x34c6211621f2763c60eb007dc2ae91090a2d22f6": "unknown",
        }
        self.assertEqual(got, expected,
                         msg="example 11: origins() before reopen")

        reopened = Store(path)
        try:
            got_again = reopened.origins()
        finally:
            reopened.close()
        self.assertEqual(got_again, expected,
                         msg="example 11: origins() after reopen")

        conn = sqlite3.connect(path)
        try:
            row = conn.execute(
                "SELECT block, origin FROM addresses WHERE address = ?",
                (addr_created.lower(),),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(
            row, (1, "created"),
            msg="example 11: the second put_address changed the row",
        )

    def test_store_example_12_phase12_migration_no_rewrite(self):
        """Store Codes And Contracts example 12: a phase-12 database (no
        origin column) of block 26077729 -- the first open adds the
        column origin last; origins() has 206 entries, all "unknown";
        the file still holds 206 rows with origin NULL (nothing
        rewritten); has_address and addresses_of answer as before; the
        second open adds no column and changes nothing."""
        path = _db_path()
        _build_phase12_db(path)

        conn = sqlite3.connect(path)
        try:
            before_columns = [row[1] for row in conn.execute(
                "PRAGMA table_info(addresses)").fetchall()]
        finally:
            conn.close()
        self.assertNotIn("origin", before_columns,
                         msg="example 12: the phase-12 db must start"
                             " without origin")

        store = Store(path)
        try:
            origins = store.origins()
        finally:
            store.close()
        self.assertEqual(len(origins), 206,
                         msg="example 12: origins() must have 206 entries")
        self.assertTrue(
            all(value == "unknown" for value in origins.values()),
            msg="example 12: every legacy origin must read as unknown",
        )

        conn = sqlite3.connect(path)
        try:
            after_columns = [row[1] for row in conn.execute(
                "PRAGMA table_info(addresses)").fetchall()]
            self.assertEqual(
                after_columns[-2:], ["origin", "implementation"],
                msg="example 12: origin then implementation (phase 14) last",
            )
            null_count = conn.execute(
                "SELECT COUNT(*) FROM addresses WHERE origin IS NULL"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(
            null_count, 206,
            msg="example 12: no row may be rewritten on open",
        )

        codes = block_codes()
        sibling_code_id = fingerprint(
            bytes.fromhex(codes[_UNIV2_PAIR][2:]))["code_id"]
        reopened = Store(path)
        try:
            self.assertTrue(
                reopened.has_address(_UNIV2_PAIR),
                msg="example 12: has_address must still work",
            )
            members = reopened.addresses_of(sibling_code_id)
        finally:
            reopened.close()
        self.assertEqual(
            members, sorted([_UNIV2_PAIR] + _UNIV2_SIBLINGS),
            msg="example 12: addresses_of must still work",
        )

        conn = sqlite3.connect(path)
        try:
            columns_before_second_open = [row[1] for row in conn.execute(
                "PRAGMA table_info(addresses)").fetchall()]
        finally:
            conn.close()
        third = Store(path)
        third.close()
        conn = sqlite3.connect(path)
        try:
            columns_after_second_open = [row[1] for row in conn.execute(
                "PRAGMA table_info(addresses)").fetchall()]
        finally:
            conn.close()
        self.assertEqual(
            columns_before_second_open, columns_after_second_open,
            msg="example 12: the second open must add no column",
        )


class RecheckWatchlistOriginExamples(unittest.TestCase):
    """Recheck Watchlist example 8 (phase 13: the key origin)."""

    def test_recheck_watchlist_example_8_origin_from_store_origins(self):
        """Recheck Watchlist example 8: a store filled by ingest_block
        (seed added after) and the store of example 1 (filled by
        put_address, no origin), both seeded with the UniV2 pair seed --
        recheck_watchlist(store) gives the same 4 alerts on each (the
        three siblings at 1.0, then the solc 0.6.12 pair at 0.8125),
        each with exactly the five keys: origin "seen" on every alert of
        the ingested store, "unknown" on every alert of the put_address
        store; store.origins() was called once per recheck_watchlist
        call."""
        codes = block_codes()
        get_code = lambda address, block: codes[address]
        store_ingested = temp_store()
        ingest_block(_BLOCK, block_receipts(), get_code, store_ingested)
        store_ingested.add_seed(_UNIV2_PAIR, "UniV2 pair seed")

        store_put = block_store()
        store_put.add_seed(_UNIV2_PAIR, "UniV2 pair seed")

        expected_addresses = sorted(_UNIV2_SIBLINGS) + [_SOLC6_PAIR]
        for store, expected_origin in (
            (store_ingested, "seen"),
            (store_put, "unknown"),
        ):
            with mock.patch.object(
                store, "origins", wraps=store.origins,
            ) as origins_mock:
                alerts = recheck_watchlist(store)
            self.assertEqual(
                origins_mock.call_count, 1,
                msg="example 8 (%s): origins() must be called once"
                    % expected_origin,
            )
            self.assertEqual(
                len(alerts), 4,
                msg="example 8 (%s): 4 alerts" % expected_origin,
            )
            self.assertEqual(
                [alert["address"] for alert in alerts], expected_addresses,
                msg="example 8 (%s): addresses out of order"
                    % expected_origin,
            )
            for alert in alerts:
                self.assertEqual(
                    set(alert.keys()),
                    {"address", "seed_address", "label", "score", "origin"},
                    msg="example 8 (%s): alert keys %r"
                        % (expected_origin, alert),
                )
                self.assertEqual(
                    alert["origin"], expected_origin,
                    msg="example 8 (%s): wrong origin on %r"
                        % (expected_origin, alert),
                )
            for alert in alerts[:3]:
                self.assertAlmostEqual(
                    alert["score"], 1.0, places=9,
                    msg="example 8 (%s): sibling score 1.0"
                        % expected_origin,
                )
            self.assertAlmostEqual(
                alerts[3]["score"], 26 / 32, places=9,
                msg="example 8 (%s): solc 0.6.12 score 26/32"
                    % expected_origin,
            )


class CommandLineOriginExamples(unittest.TestCase):
    """Command Line examples 36-43 (phase 13: Origin of an alert)."""

    def test_command_line_example_36_six_field_alert_created_and_seen(self):
        """Command Line example 36: a fresh db holding the deploy-seed
        setup, backfilled over the fixture block -- exit 0, stderr
        empty, stdout exactly the three ALERT lines (created, seen,
        seen); store.origins() then has 207 entries: 0xb53c071b…
        "created", 205 "seen", 0x1111… "unknown"."""
        db = _db_path()
        _setup_deploy_seed_db(db)
        fake = FakeRpc(head=_HEAD)
        code, out, err = _run(
            ["--db", db, "backfill", "--from", str(_BLOCK), "--to",
             str(_BLOCK), "--min", "0.8"], rpc=fake)
        self.assertEqual(code, 0, msg="example 36: exit code, stderr %r" % err)
        self.assertEqual(err, "", msg="example 36: stderr not empty")
        self.assertEqual(out, _ALL_LINES,
                         msg="example 36: unexpected stdout %r" % out)

        store = Store(db)
        try:
            origins = store.origins()
        finally:
            store.close()
        self.assertEqual(len(origins), 207,
                         msg="example 36: origins() count")
        self.assertEqual(origins.get(_B53C), "created",
                         msg="example 36: %s must be created" % _B53C)
        self.assertEqual(origins.get(_DEPLOY_SEED), "unknown",
                         msg="example 36: %s must be unknown" % _DEPLOY_SEED)
        other_origins = [
            value for address, value in origins.items()
            if address not in (_B53C, _DEPLOY_SEED)
        ]
        self.assertEqual(len(other_origins), 205,
                         msg="example 36: 205 other addresses")
        self.assertTrue(all(value == "seen" for value in other_origins),
                        msg="example 36: every other address must be seen")

    def test_command_line_example_37_alert_on_filters_stdout_only(self):
        """Command Line example 37: the deploy-seed setup in three fresh
        dbs, backfilled with --alert-on created, seen and all -- exit 0
        each time; stdout is the created line only, the two seen lines
        only, and all three lines; store.origins() is the same 207-entry
        dict in all three dbs and progress is 26077729."""
        for alert_on, expected_out in (
            ("created", _CREATED_LINE),
            ("seen", _SEEN_LINE_1 + _SEEN_LINE_2),
            ("all", _ALL_LINES),
        ):
            db = _db_path()
            _setup_deploy_seed_db(db)
            fake = FakeRpc(head=_HEAD)
            code, out, err = _run(
                ["--db", db, "backfill", "--from", str(_BLOCK), "--to",
                 str(_BLOCK), "--alert-on", alert_on, "--min", "0.8"], rpc=fake)
            self.assertEqual(
                code, 0, msg="example 37 (%s): exit code, stderr %r"
                % (alert_on, err))
            self.assertEqual(err, "",
                             msg="example 37 (%s): stderr not empty"
                             % alert_on)
            self.assertEqual(
                out, expected_out,
                msg="example 37 (%s): unexpected stdout %r" % (alert_on, out))

            store = Store(db)
            try:
                origins = store.origins()
                progress = store.get_progress()
            finally:
                store.close()
            self.assertEqual(
                len(origins), 207,
                msg="example 37 (%s): origins() count" % alert_on)
            self.assertEqual(
                progress, _BLOCK,
                msg="example 37 (%s): progress" % alert_on)

    def test_command_line_example_38_listen_alert_on_created_publicnode(self):
        """Command Line example 38: the deploy-seed setup, progress
        26077728, a listen pass over the public node with --alert-on
        created and a sleep that raises KeyboardInterrupt -- exit 0,
        stderr empty, stdout exactly the one created line, progress
        26077729."""
        db = _db_path()
        _setup_deploy_seed_db(db)
        store = Store(db)
        try:
            store.set_progress(_BLOCK - 1)
        finally:
            store.close()

        fake = FakeRpc(head=_HEAD)
        code, out, err = _run(
            ["--db", db, "listen", "--source", "publicnode", "--alert-on",
             "created"],
            rpc=fake, sleep=_interrupting_sleep,
        )
        self.assertEqual(code, 0, msg="example 38: exit code, stderr %r" % err)
        self.assertEqual(err, "", msg="example 38: stderr not empty")
        self.assertEqual(out, _CREATED_LINE,
                         msg="example 38: unexpected stdout %r" % out)

        store = Store(db)
        try:
            progress = store.get_progress()
        finally:
            store.close()
        self.assertEqual(progress, _BLOCK, msg="example 38: progress")

    def test_command_line_example_39_recheck_origin_filters(self):
        """Command Line example 39: the db of the plain backfill of
        example 36 -- recheck prints the same three lines byte for byte;
        --origin created the created line only; --origin seen the two
        seen lines; --origin fetched and --origin unknown give an empty
        stdout (the seed's own address never alerts)."""
        db = _db_path()
        _setup_deploy_seed_db(db)
        fake = FakeRpc(head=_HEAD)
        backfill_code, backfill_out, backfill_err = _run(
            ["--db", db, "backfill", "--from", str(_BLOCK), "--to",
             str(_BLOCK), "--min", "0.8"], rpc=fake)
        self.assertEqual(backfill_code, 0,
                         msg="example 39: backfill exit code")
        self.assertEqual(backfill_out, _ALL_LINES,
                         msg="example 39: backfill stdout")

        for extra_args, expected_out in (
            ([], _ALL_LINES),
            (["--origin", "created"], _CREATED_LINE),
            (["--origin", "seen"], _SEEN_LINE_1 + _SEEN_LINE_2),
            (["--origin", "fetched"], ""),
            (["--origin", "unknown"], ""),
        ):
            code, out, err = _run(["--db", db, "recheck", "--min", "0.8"] + extra_args)
            self.assertEqual(
                code, 0, msg="example 39 %r: exit code" % extra_args)
            self.assertEqual(
                err, "", msg="example 39 %r: stderr not empty" % extra_args)
            self.assertEqual(
                out, expected_out,
                msg="example 39 %r: unexpected stdout %r" % (extra_args, out))

    def test_command_line_example_40_usage_errors_no_rpc_call(self):
        """Command Line example 40: an unknown --alert-on/--origin value
        is a usage error -- exit 2, stdout empty, stderr one line, no rpc
        call."""
        argv_list = (
            ["--db", _db_path(), "backfill", "--from", str(_BLOCK), "--to",
             str(_BLOCK), "--alert-on", "deployed"],
            ["--db", _db_path(), "listen", "--alert-on", "fetched"],
            ["--db", _db_path(), "recheck", "--origin", "all"],
        )
        for argv in argv_list:
            fake = FakeRpc(fail=AssertionError("no rpc"))
            code, out, err = _run(argv, rpc=fake)
            self.assertEqual(code, 2, msg="example 40 %r: exit code" % argv)
            self.assertEqual(out, "", msg="example 40 %r: stdout" % argv)
            self.assertEqual(
                len(err.rstrip("\n").split("\n")), 1,
                msg="example 40 %r: stderr not one line: %r" % (argv, err),
            )
            self.assertEqual(fake.calls, [],
                             msg="example 40 %r: rpc was called" % argv)

    def test_command_line_example_41_fetched_seed_alerts_as_fetched(self):
        """Command Line example 41: a db holding code_belle.hex, no
        origin, seeded "BELLE honeypot"; seed add --fetch a BELLE copy
        labelled "BELLE copy" -- the seed add line names the copy as
        seed_address and origin unknown; recheck then also gives the
        reverse line with origin fetched; --origin fetched keeps only
        that line; store.origins() is {copy: fetched, BELLE: unknown}."""
        db = _db_path()
        store = Store(db)
        try:
            belle_id = store.put_code(load_hex("code_belle.hex"))
            store.put_address(_BELLE, belle_id, _BLOCK)
            store.add_seed(_BELLE, "BELLE honeypot")
        finally:
            store.close()

        copy_address = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
        copy_text = "0x" + load_hex("code_belle_copy_1807090d.hex").hex()
        fake = FakeRpc(codes={copy_address: copy_text}, head=_HEAD)
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", copy_address, "--label",
             "BELLE copy"], rpc=fake)
        self.assertEqual(code, 0, msg="example 41: seed add exit code")
        self.assertEqual(err, "", msg="example 41: seed add stderr")
        seed_add_line = (
            "ALERT\t%s\t%s\tBELLE copy\t0.8667\tunknown\n"
            % (_BELLE, copy_address)
        )
        self.assertEqual(out, seed_add_line,
                         msg="example 41: seed add stdout %r" % out)

        code, out, err = _run(["--db", db, "recheck"])
        self.assertEqual(code, 0, msg="example 41: recheck exit code")
        fetched_line = (
            "ALERT\t%s\t%s\tBELLE honeypot\t0.8667\tfetched\n"
            % (copy_address, _BELLE)
        )
        self.assertEqual(
            out, fetched_line + seed_add_line,
            msg="example 41: recheck stdout %r" % out,
        )

        code, out, err = _run(["--db", db, "recheck", "--origin", "fetched"])
        self.assertEqual(code, 0,
                         msg="example 41: recheck --origin fetched exit code")
        self.assertEqual(
            out, fetched_line,
            msg="example 41: recheck --origin fetched stdout %r" % out,
        )

        store = Store(db)
        try:
            origins = store.origins()
        finally:
            store.close()
        self.assertEqual(
            origins, {copy_address: "fetched", _BELLE: "unknown"},
            msg="example 41: store.origins() %r" % origins,
        )

    def test_command_line_example_42_fetch_eoa_stores_fetched_origin(self):
        """Command Line example 42: seed add --fetch on an eth_getCode
        "0x" answer exits 2 as in phase 12, and stores the address with
        origin "fetched"."""
        db = _db_path()
        eoa = "0x023697eda1dfbe331c2cf791ef2f6089e73e3230"
        fake = FakeRpc(codes={eoa: "0x"}, head=_HEAD)
        code, out, err = _run(
            ["--db", db, "seed", "add", "--fetch", eoa, "--label", "L"],
            rpc=fake)
        self.assertEqual(code, 2, msg="example 42: exit code")
        self.assertEqual(out, "", msg="example 42: stdout not empty")
        self.assertEqual(
            err, "unknown address or no code: %s\n" % eoa,
            msg="example 42: stderr %r" % err,
        )
        store = Store(db)
        try:
            origins = store.origins()
        finally:
            store.close()
        self.assertEqual(
            origins, {eoa: "fetched"},
            msg="example 42: store.origins() %r" % origins,
        )

    def test_command_line_example_43_phase12_db_recheck_reads_unknown(self):
        """Command Line example 43: a phase-12 db (no origin column)
        holding the BELLE seed and its four copies, written by plain
        INSERTs -- recheck prints the 4 copy alerts, each origin
        "unknown"; --origin unknown gives the same 4 lines; --origin
        seen gives an empty stdout."""
        db = _db_path()
        _build_phase12_belle_db(db)

        expected_lines = "".join(
            "ALERT\t%s\t%s\tBELLE honeypot\t0.8667\tunknown\n"
            % (address, _BELLE)
            for address, _ in _COPIES
        )
        for extra_args, expected_out in (
            ([], expected_lines),
            (["--origin", "unknown"], expected_lines),
            (["--origin", "seen"], ""),
        ):
            code, out, err = _run(["--db", db, "recheck"] + extra_args)
            self.assertEqual(
                code, 0, msg="example 43 %r: exit code" % extra_args)
            self.assertEqual(
                err, "", msg="example 43 %r: stderr not empty" % extra_args)
            self.assertEqual(
                out, expected_out,
                msg="example 43 %r: unexpected stdout %r" % (extra_args, out))


if __name__ == "__main__":
    unittest.main()
