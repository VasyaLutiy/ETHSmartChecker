"""Judge for the phase-11 examples of group store, Function Store Codes
And Contracts: examples 6, 7, 8 and 9 (schema, fingerprints, migration,
NULL fill). Exact values from the fixtures; no network."""

import json
import os
import sqlite3
import tempfile
import unittest

from ethsc.fingerprint import fingerprint
from ethsc.store import Store
from tests.helpers import block_codes, block_store, temp_store

BLOCK = 26077729

_COLUMNS = ["code_id", "size", "skeleton_hash", "selectors",
            "proxy_kind", "proxy_target", "code", "std_proxy"]

_FP_KEYS = {"code_id", "size", "skeleton_hash", "selectors",
            "proxy", "std_proxy"}

_PHASE10_SCHEMA = """
CREATE TABLE codes (
    code_id TEXT PRIMARY KEY,
    size INTEGER,
    skeleton_hash TEXT,
    selectors TEXT,
    proxy_kind TEXT,
    proxy_target TEXT,
    code BLOB
);
CREATE TABLE addresses (
    address TEXT PRIMARY KEY,
    code_id TEXT,
    block INTEGER
);
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


def _distinct_codes():
    """The distinct code bytes of block_codes(), keyed by code_id."""
    seen = {}
    for text in block_codes().values():
        if text != "0x":
            code = bytes.fromhex(text[2:])
            seen[fingerprint(code)["code_id"]] = code
    return seen


def _expected_fingerprints():
    """The Fingerprint dicts of every distinct code of block_codes(),
    sorted by code_id."""
    fps = [fingerprint(code) for code in _distinct_codes().values()]
    return sorted(fps, key=lambda fp: fp["code_id"])


def _fill_store(store):
    """put_code every distinct code of block_codes() into store."""
    for code in _distinct_codes().values():
        store.put_code(code)


def _index_names(conn, table):
    """The names of every index on table, explicit and automatic."""
    rows = conn.execute(
        "PRAGMA index_list(%s)" % table).fetchall()
    return [row[1] for row in rows]


def _build_phase10_db(path):
    """A hand-built phase-10 database of block 26077729.

    The five CREATE TABLE statements of the phase-10 schema, no index,
    then plain INSERTs of the 130 distinct codes (values from
    fingerprint()) and the 147 addresses with code, at block 26077729.
    """
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_PHASE10_SCHEMA)
        for code in _distinct_codes().values():
            fp = fingerprint(code)
            conn.execute(
                "INSERT INTO codes (code_id, size, skeleton_hash,"
                " selectors, proxy_kind, proxy_target, code)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    fp["code_id"],
                    fp["size"],
                    fp["skeleton_hash"],
                    json.dumps(fp["selectors"]),
                    fp["proxy"]["kind"] if fp["proxy"] else None,
                    fp["proxy"]["target"] if fp["proxy"] else None,
                    sqlite3.Binary(code),
                ),
            )
        addresses = 0
        for address, text in sorted(block_codes().items()):
            if text == "0x":
                continue
            code_id = fingerprint(bytes.fromhex(text[2:]))["code_id"]
            conn.execute(
                "INSERT INTO addresses (address, code_id, block)"
                " VALUES (?, ?, ?)",
                (address.lower(), code_id, BLOCK),
            )
            addresses += 1
        conn.commit()
        assert addresses == 147
    finally:
        conn.close()


class TestStoreExamplesP11(unittest.TestCase):
    """One test per phase-11 example of Store Codes And Contracts."""

    def test_store_codes_and_contracts_example_6(self):
        """Store Codes And Contracts example 6: a fresh temp db, then
        PRAGMA table_info(codes) and PRAGMA index_list(addresses) -- the
        columns are code_id, size, skeleton_hash, selectors, proxy_kind,
        proxy_target, code, std_proxy in that order; addresses has an
        index named addresses_code_id on the one column code_id."""
        store = temp_store()
        try:
            conn = store._conn
            columns = [row[1] for row in
                       conn.execute("PRAGMA table_info(codes)").fetchall()]
            self.assertEqual(columns, _COLUMNS,
                             msg="the codes columns in phase-11 order")
            names = _index_names(conn, "addresses")
            self.assertIn("addresses_code_id", names,
                          msg="addresses has an index addresses_code_id")
            infos = [row[2] for row in conn.execute(
                "PRAGMA index_info(addresses_code_id)").fetchall()]
            self.assertEqual(infos, ["code_id"],
                             msg="the index is on the one column code_id")
        finally:
            store.close()

    def test_store_codes_and_contracts_example_7(self):
        """Store Codes And Contracts example 7: a store filled from
        codes_26077729.json, then fingerprints() -- 130 fingerprints,
        17 of them with std_proxy True; each equals fingerprint(code) of
        its stored code, all six keys."""
        store = block_store()
        try:
            fps = store.fingerprints()
            self.assertEqual(len(fps), 130,
                             msg="130 fingerprints")
            self.assertEqual(
                sum(1 for fp in fps if fp["std_proxy"]), 17,
                msg="17 of them with std_proxy True")
            expected = _expected_fingerprints()
            self.assertEqual(sorted(fp["code_id"] for fp in fps),
                             sorted(fp["code_id"] for fp in expected),
                             msg="the same 130 code_id as fingerprint gives")
            by_id = {fp["code_id"]: fp for fp in expected}
            for fp in fps:
                self.assertEqual(set(fp.keys()), _FP_KEYS,
                                 msg="exactly the six keys of the"
                                     " Fingerprint schema")
                self.assertEqual(fp, by_id[fp["code_id"]],
                                 msg="fingerprints()[%s] equals"
                                     " fingerprint(code)" % fp["code_id"])
        finally:
            store.close()

    def test_store_codes_and_contracts_example_8(self):
        """Store Codes And Contracts example 8: a phase-10 database made
        with the phase-10 schema (codes with the seven columns
        code_id .. code, no std_proxy, no index on addresses) holding
        the 130 codes and 147 addresses with code of
        codes_26077729.json, written by plain INSERTs -- Store(path)
        opens it, and fingerprints() is called; then the same codes go
        through put_code into a fresh db -- after the open the codes
        table has the column std_proxy last and addresses the index
        addresses_code_id; fingerprints() of the migrated db equals
        fingerprints() of the fresh db, 130 dicts, 17 with std_proxy
        True; no row has std_proxy NULL."""
        directory = tempfile.mkdtemp(prefix="ethsc-test-p11-")
        path = os.path.join(directory, "phase10.sqlite")
        _build_phase10_db(path)

        conn = sqlite3.connect(path)
        try:
            columns = [row[1] for row in
                       conn.execute("PRAGMA table_info(codes)").fetchall()]
            self.assertNotIn("std_proxy", columns,
                             msg="the phase-10 db starts without std_proxy")
            self.assertNotIn("addresses_code_id", _index_names(conn,
                             "addresses"),
                             msg="the phase-10 db starts without the index")
        finally:
            conn.close()

        store = Store(path)
        try:
            columns = [row[1] for row in
                       store._conn.execute(
                           "PRAGMA table_info(codes)").fetchall()]
            self.assertEqual(columns, _COLUMNS,
                             msg="std_proxy is the last column after the open")
            self.assertIn("addresses_code_id",
                          _index_names(store._conn, "addresses"),
                          msg="the index exists after the open")
            nulls = store._conn.execute(
                "SELECT COUNT(*) FROM codes WHERE std_proxy IS NULL"
            ).fetchone()[0]
            self.assertEqual(nulls, 0,
                             msg="no row has std_proxy NULL after the open")
            migrated = store.fingerprints()
            self.assertEqual(len(migrated), 130,
                             msg="130 fingerprints in the migrated db")
            self.assertEqual(
                sum(1 for fp in migrated if fp["std_proxy"]), 17,
                msg="17 of them with std_proxy True")
        finally:
            store.close()

        fresh = temp_store()
        try:
            _fill_store(fresh)
            self.assertEqual(
                fresh.fingerprints(), migrated,
                msg="fingerprints() of the migrated db equals that of a"
                    " fresh db filled by put_code")
        finally:
            fresh.close()

    def test_store_codes_and_contracts_example_9(self):
        """Store Codes And Contracts example 9: a phase-11 db of the 130
        codes whose std_proxy was set back to NULL on every row (a fill
        interrupted after the ALTER) -- the db is reopened with
        Store(path) and fingerprints() is called -- no row has std_proxy
        NULL and fingerprints() equals that of a fresh db of the same
        codes."""
        directory = tempfile.mkdtemp(prefix="ethsc-test-p11-")
        path = os.path.join(directory, "nullfill.sqlite")

        builder = Store(path)
        try:
            _fill_store(builder)
        finally:
            builder.close()

        conn = sqlite3.connect(path)
        try:
            conn.execute("UPDATE codes SET std_proxy = NULL")
            conn.commit()
            nulls = conn.execute(
                "SELECT COUNT(*) FROM codes WHERE std_proxy IS NULL"
            ).fetchone()[0]
            self.assertEqual(nulls, 130,
                             msg="130 rows reset to NULL before the reopen")
        finally:
            conn.close()

        store = Store(path)
        try:
            nulls = store._conn.execute(
                "SELECT COUNT(*) FROM codes WHERE std_proxy IS NULL"
            ).fetchone()[0]
            self.assertEqual(nulls, 0,
                             msg="no NULL left after the reopen")
            migrated = store.fingerprints()
            self.assertEqual(len(migrated), 130,
                             msg="130 fingerprints after the refill")
        finally:
            store.close()

        fresh = temp_store()
        try:
            _fill_store(fresh)
            self.assertEqual(
                fresh.fingerprints(), migrated,
                msg="fingerprints() equals that of a fresh db")
            again = Store(path)
            try:
                self.assertEqual(
                    again.fingerprints(), migrated,
                    msg="a second open changes nothing")
            finally:
                again.close()
        finally:
            fresh.close()


if __name__ == "__main__":
    unittest.main()
