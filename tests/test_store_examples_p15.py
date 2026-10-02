# tests/test_store_examples_p15.py
"""Judge: one test per Contour example, phase 15 store group.

Store Codes And Contracts examples 16-17, Track Progress example 2,
Base Counts example 4, Record Events examples 1-5, Open Read Only
examples 1-4. The code under test is finished; these tests only call
it. Builders and stubs come from tests/helpers.py.
"""

import hashlib
import json
import os
import re
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone

from ethsc.store import ReadOnlyStoreError, Store

from tests.helpers import block_codes, legacy_db, load_hex


_ALERT_AT = "2026-10-02T08:00:00Z"

_EX1_ALERT = {
    "kind": "ALERT",
    "block": 26077729,
    "at": _ALERT_AT,
    "address": "0x1807090DD15A6F58E00FD769E32EBF20EE610385",
    "seed_address": "0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
    "label": "BELLE honeypot",
    "score": 0.8666666666666667,
    "origin": "seen",
}

_EX1_UPGRADE = {
    "kind": "UPGRADE",
    "block": 26077729,
    "at": _ALERT_AT,
    "address": "0x0c0105334a50db16b51b2911c9956539753a2cf8",
    "old_impl": "0x72b971717e088b59f26d4236be222adb6acd393b",
    "new_impl": "0xe440cc08a71694c8229323803f59024e3144630e",
}

_EX1_ALERT_EVENT = {
    "id": 1,
    "kind": "ALERT",
    "block": 26077729,
    "at": _ALERT_AT,
    "address": "0x1807090dd15a6f58e00fd769e32ebf20ee610385",
    "seed_address": "0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
    "label": "BELLE honeypot",
    "score": 0.8666666666666667,
    "origin": "seen",
    "old_impl": None,
    "new_impl": None,
}

_EX1_UPGRADE_EVENT = {
    "id": 2,
    "kind": "UPGRADE",
    "block": 26077729,
    "at": _ALERT_AT,
    "address": "0x0c0105334a50db16b51b2911c9956539753a2cf8",
    "seed_address": None,
    "label": None,
    "score": None,
    "origin": None,
    "old_impl": "0x72b971717e088b59f26d4236be222adb6acd393b",
    "new_impl": "0xe440cc08a71694c8229323803f59024e3144630e",
}


def _fresh_path():
    directory = tempfile.mkdtemp(prefix="ethsc-judge-p15-")
    return os.path.join(directory, "ethsc.sqlite")


def _block_store_at(path):
    """A Store at path filled from block_codes() at block 26077729."""
    store = Store(path)
    block = 26077729
    for address, text in sorted(block_codes().items()):
        if text == "0x":
            store.put_address(address, None, block)
        else:
            code_id = store.put_code(bytes.fromhex(text[2:]))
            store.put_address(address, code_id, block)
    return store


def _pragma(store, statement):
    return store.execute(statement).fetchone()[0]


def _table_names(path):
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return sorted(row[0] for row in rows)
    finally:
        connection.close()


def _columns(path, table):
    connection = sqlite3.connect(path)
    try:
        return [row[1] for row in connection.execute(
            "PRAGMA table_info(%s)" % table).fetchall()]
    finally:
        connection.close()


def _journal_mode(path):
    connection = sqlite3.connect(path)
    try:
        return _pragma(connection, "PRAGMA journal_mode")
    finally:
        connection.close()


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class TestStoreExamplesP15(unittest.TestCase):

    # -- Store Codes And Contracts example 16 ------------------------------

    def test_store_16(self):
        path = _fresh_path()
        store = Store(path)
        store.close()
        self.assertEqual(_journal_mode(path), "wal")
        store = Store(path)
        store.close()
        self.assertEqual(_journal_mode(path), "wal")
        self.assertEqual(_table_names(path),
                         ["addresses", "codes", "events", "ledger",
                          "progress", "seeds"])
        self.assertEqual(_columns(path, "progress"),
                         ["key", "block", "updated_at"])
        self.assertEqual(
            _columns(path, "events"),
            ["id", "kind", "block", "at", "address", "seed_address",
             "label", "score", "origin", "old_impl", "new_impl"])

    # -- Store Codes And Contracts example 17 ------------------------------

    def test_store_17(self):
        path = legacy_db(14)
        self.assertEqual(_journal_mode(path), "delete")
        self.assertNotIn("events", _table_names(path))
        store = Store(path)
        self.assertEqual(store.get_progress(), 26077729)
        self.assertIsNone(store.progress_at())
        self.assertEqual(store.counts()["addresses"], 206)
        store.close()
        self.assertIn("events", _table_names(path))
        self.assertEqual(_columns(path, "progress"),
                         ["key", "block", "updated_at"])
        self.assertEqual(_journal_mode(path), "wal")
        connection = sqlite3.connect(path)
        try:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM events").fetchone()[0], 0)
        finally:
            connection.close()
        store = Store(path)
        try:
            self.assertEqual(_columns_at(store, "progress"),
                             ["key", "block", "updated_at"])
            self.assertEqual(store.get_progress(), 26077729)
            self.assertEqual(store.counts()["addresses"], 206)
        finally:
            store.close()

    # -- Track Progress example 2 -------------------------------------------

    def test_track_progress_2(self):
        path = _fresh_path()
        store = Store(path)
        self.assertIsNone(store.progress_at())
        t0 = datetime.now(timezone.utc).replace(microsecond=0)
        store.set_progress(26077729)
        t1 = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = store.progress_at()
        self.assertIsInstance(stamp, str)
        self.assertEqual(len(stamp), 20)
        self.assertIsNotNone(re.match(
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
            stamp))
        parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
        parsed = parsed.replace(tzinfo=timezone.utc)
        self.assertTrue(t0 <= parsed <= t1)
        self.assertEqual(store.get_progress(), 26077729)
        store.close()
        store = Store(path)
        try:
            self.assertEqual(store.progress_at(), stamp)
            self.assertEqual(store.get_progress(), 26077729)
        finally:
            store.close()

    # -- Base Counts example 4 ----------------------------------------------

    def test_base_counts_4(self):
        store = Store(_fresh_path())
        try:
            self.assertEqual(store.origin_counts(), {})
            store.put_address(
                "0x00000000000000000000000000000000000000a1", None, 100,
                "created")
            store.put_address(
                "0x00000000000000000000000000000000000000a2", None, 200,
                "seen")
            store.put_address(
                "0x00000000000000000000000000000000000000a3", None, 300)
            store.put_address(
                "0x00000000000000000000000000000000000000a4", None, 300,
                "seen")
            self.assertEqual(store.origin_counts(),
                             {"created": 1, "seen": 2, "unknown": 1})
            self.assertEqual(store.origin_counts(since_block=200),
                             {"seen": 2, "unknown": 1})
            self.assertEqual(store.origin_counts(since_block=301), {})
        finally:
            store.close()

    # -- Record Events example 1 ---------------------------------------------

    def test_record_events_1(self):
        path = _fresh_path()
        store = Store(path)
        try:
            store.add_events([_EX1_ALERT, _EX1_UPGRADE])
            events = store.events()
            self.assertEqual(events,
                             [_EX1_UPGRADE_EVENT, _EX1_ALERT_EVENT])
        finally:
            store.close()
        store = Store(path)
        try:
            self.assertEqual(store.events(),
                             [_EX1_UPGRADE_EVENT, _EX1_ALERT_EVENT])
        finally:
            store.close()

    # -- Record Events example 2 ---------------------------------------------

    def test_record_events_2(self):
        store = Store(_fresh_path())
        try:
            batch = []
            for block in (1, 2, 3, 4, 5):
                event = dict(_EX1_ALERT)
                event["block"] = block
                batch.append(event)
            store.add_events(batch)
            check = [(store.events(),
                      [5, 4, 3, 2, 1]),
                     (store.events(limit=3), [5, 4, 3]),
                     (store.events(after_id=2), [5, 4, 3]),
                     (store.events(after_id=2, limit=2), [5, 4]),
                     (store.events(after_id=5), [])]
            for events, ids in check:
                self.assertEqual([event["id"] for event in events], ids)
                for event in events:
                    self.assertEqual(event["block"], event["id"])
        finally:
            store.close()

    # -- Record Events example 3 ---------------------------------------------

    def test_record_events_3(self):
        store = Store(_fresh_path())
        try:
            self.assertEqual(
                store.event_counts(),
                {"kinds": {"ALERT": 0, "UPGRADE": 0}, "seeds": []})
            belle_seed = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
            other_seed = "0x1111111111111111111111111111111111111111"
            alerts = [
                dict(_EX1_ALERT, block=1,
                     address="0x" + "a1" * 20),
                dict(_EX1_ALERT, block=2,
                     address="0x" + "a2" * 20),
                {"kind": "ALERT", "block": 3, "at": _ALERT_AT,
                 "address": "0x" + "a3" * 20,
                 "seed_address": other_seed,
                 "label": "impl copy seed",
                 "score": 1.0, "origin": "seen"},
            ]
            upgrade = dict(_EX1_UPGRADE, block=4)
            store.add_events(alerts + [upgrade])
            self.assertEqual(
                store.event_counts(),
                {"kinds": {"ALERT": 3, "UPGRADE": 1},
                 "seeds": [
                     {"label": "BELLE honeypot",
                      "seed_address": belle_seed, "count": 2},
                     {"label": "impl copy seed",
                      "seed_address": other_seed, "count": 1}]})
        finally:
            store.close()

    # -- Record Events example 4 ---------------------------------------------

    def test_record_events_4(self):
        store = Store(_fresh_path())
        try:
            store.add_events([_EX1_ALERT])
            with self.assertRaises(ValueError):
                store.add_events([
                    dict(_EX1_ALERT, block=2,
                         address="0x" + "b1" * 20),
                    {"kind": "BOGUS", "block": 1, "at": _ALERT_AT},
                ])
            self.assertEqual(store.events(), [_EX1_ALERT_EVENT])
        finally:
            store.close()

    # -- Record Events example 5 ---------------------------------------------

    def test_record_events_5(self):
        store = Store(_fresh_path())
        try:
            store.add_events([])
            self.assertEqual(store.events(), [])
            self.assertEqual(store.event_counts()["kinds"],
                             {"ALERT": 0, "UPGRADE": 0})
        finally:
            store.close()

    # -- Open Read Only example 1 ---------------------------------------------

    def test_open_read_only_1(self):
        path = _fresh_path()
        store = _block_store_at(path)
        store.set_progress(26077729)
        store.close()
        readonly = Store(path, readonly=True)
        try:
            self.assertEqual(readonly.counts(),
                             {"addresses": 206,
                              "addresses_with_code": 147,
                              "addresses_without_code": 59,
                              "codes": 130,
                              "blocks": 1})
            self.assertEqual(readonly.get_progress(), 26077729)
            self.assertEqual(len(readonly.fingerprints()), 130)
            self.assertEqual(len(readonly.origins()), 206)
            self.assertEqual(readonly.events(), [])
            writes = [
                ("put_code", (load_hex("code_weth9.hex"),)),
                ("put_address",
                 ("0x" + "11" * 20, None, 1)),
                ("set_implementation",
                 ("0x" + "22" * 20, "0x" + "33" * 20)),
                ("set_progress", (1,)),
                ("add_seed", ("0x" + "44" * 20, "L")),
                ("remove_seed", ("0x" + "44" * 20,)),
                ("spend", ("2026-01-01", "eth_getCode", 1)),
                ("add_events", ([_EX1_ALERT],)),
            ]
            for name, args in writes:
                with self.assertRaises(ReadOnlyStoreError):
                    getattr(readonly, name)(*args)
        finally:
            readonly.close()
        store = Store(path)
        try:
            self.assertEqual(store.counts()["addresses"], 206)
            self.assertEqual(store.seeds(), [])
        finally:
            store.close()

    # -- Open Read Only example 2 ---------------------------------------------

    def test_open_read_only_2(self):
        path = legacy_db(13)
        before_sha = _sha256(path)
        before_listing = sorted(os.listdir(os.path.dirname(path)))
        readonly = Store(path, readonly=True)
        try:
            self.assertEqual(readonly.get_progress(), 26077729)
            self.assertIsNone(readonly.progress_at())
            self.assertEqual(readonly.events(), [])
            self.assertEqual(
                readonly.event_counts(),
                {"kinds": {"ALERT": 0, "UPGRADE": 0}, "seeds": []})
            implementations = readonly.implementations()
            self.assertEqual(len(implementations), 20)
            for entry in implementations.values():
                self.assertEqual(entry,
                                 {"implementation": None,
                                  "code_id": None})
            self.assertIsNone(readonly.implementation(
                "0x0000000000000000000000000000000000000001"))
            origins = readonly.origins()
            self.assertEqual(len(origins), 206)
            for origin in origins.values():
                self.assertEqual(origin, "unknown")
            self.assertEqual(readonly.counts()["addresses"], 206)
        finally:
            readonly.close()
        self.assertEqual(_sha256(path), before_sha)
        self.assertEqual(sorted(os.listdir(os.path.dirname(path))),
                         before_listing)

    # -- Open Read Only example 3 ---------------------------------------------

    def test_open_read_only_3(self):
        directory = tempfile.mkdtemp(prefix="ethsc-judge-p15-")
        path = os.path.join(directory, "missing.sqlite")
        with self.assertRaises(sqlite3.OperationalError):
            Store(path, readonly=True)
        self.assertEqual(os.listdir(directory), [])

    # -- Open Read Only example 4 ---------------------------------------------

    def test_open_read_only_4(self):
        path = _fresh_path()
        writer = Store(path)
        reader = Store(path, readonly=True)
        try:
            writer.add_events([_EX1_ALERT])
            writer.set_progress(26077729)
            events = reader.events()
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["id"], 1)
            self.assertEqual(events[0], _EX1_ALERT_EVENT)
            self.assertEqual(reader.get_progress(), 26077729)
            self.assertIsNotNone(reader.progress_at())
        finally:
            reader.close()
            writer.close()


def _columns_at(store, table):
    return [row[1] for row in store._conn.execute(
        "PRAGMA table_info(%s)" % table).fetchall()]


if __name__ == "__main__":
    unittest.main()
