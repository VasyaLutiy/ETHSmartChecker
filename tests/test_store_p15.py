"""Smoke tests for the phase-15 store: events, heartbeat, origin_counts,
read-only."""

import os
import re
import tempfile

from ethsc.store import ReadOnlyStoreError, Store

from tests.helpers import load_hex, temp_store


def _db_path():
    return os.path.join(tempfile.mkdtemp(), "e.sqlite")


def test_events_roundtrip():
    store = temp_store()
    store.add_events([])
    alert = {
        "kind": "ALERT", "block": 26077729, "at": "2026-10-02T08:00:00Z",
        "address": "0x1807090DD15A6F58E00FD769E32EBF20EE610385",
        "seed_address": "0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
        "label": "BELLE honeypot", "score": 0.8666666666666667,
        "origin": "seen",
    }
    upgrade = {
        "kind": "UPGRADE", "block": 26077729, "at": "2026-10-02T08:00:00Z",
        "address": "0x0c0105334a50db16b51b2911c9956539753a2cf8",
        "old_impl": "0x72b971717e088b59f26d4236be222adb6acd393b",
        "new_impl": "0xe440cc08a71694c8229323803f59024e3144630e",
    }
    store.add_events([alert, upgrade])
    rows = store.events()
    assert [r["id"] for r in rows] == [2, 1]
    assert rows[1]["kind"] == "ALERT"
    assert rows[1]["address"] == "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
    assert rows[1]["score"] == 0.8666666666666667
    assert rows[0]["seed_address"] is None
    assert store.event_counts()["kinds"] == {"ALERT": 1, "UPGRADE": 1}
    store.close()


def test_events_bad_kind_writes_nothing():
    store = temp_store()
    alert = {"kind": "ALERT", "block": 1, "at": "t", "address": "0x" + "a" * 40}
    try:
        store.add_events([alert, {"kind": "BOGUS", "block": 1, "at": "t"}])
        raised = False
    except ValueError:
        raised = True
    assert raised
    assert store.events() == []
    store.close()


def test_progress_at_heartbeat():
    store = temp_store()
    assert store.progress_at() is None
    store.set_progress(26077729)
    stamp = store.progress_at()
    assert isinstance(stamp, str) and len(stamp) == 20
    assert re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
                    stamp)
    assert store.get_progress() == 26077729
    store.close()


def test_origin_counts():
    store = temp_store()
    assert store.origin_counts() == {}
    store.put_address("0x" + "a" * 40, None, 100, "created")
    store.put_address("0x" + "b" * 40, None, 200, "seen")
    store.put_address("0x" + "c" * 40, None, 300)
    assert store.origin_counts() == {"created": 1, "seen": 1, "unknown": 1}
    assert store.origin_counts(since_block=200) == {"seen": 1, "unknown": 1}
    store.close()


def test_readonly_store():
    path = _db_path()
    store = Store(path)
    code_id = store.put_code(load_hex("code_belle.hex"))
    store.put_address("0x34c6211621f2763c60eb007dc2ae91090a2d22f6", code_id, 1)
    store.set_progress(26077729)
    store.close()
    ro = Store(path, readonly=True)
    assert ro.counts()["codes"] == 1
    assert ro.get_progress() == 26077729
    assert ro.events() == []
    assert ro.event_counts()["kinds"] == {"ALERT": 0, "UPGRADE": 0}
    writes = [
        lambda: ro.put_code(b"\x00"),
        lambda: ro.put_address("0x" + "d" * 40, None, 1),
        lambda: ro.set_implementation("0x" + "d" * 40, "0x" + "e" * 40),
        lambda: ro.set_progress(1),
        lambda: ro.add_seed("0x34c6211621f2763c60eb007dc2ae91090a2d22f6", "L"),
        lambda: ro.remove_seed("0x" + "d" * 40),
        lambda: ro.spend("2026-10-02", "eth_getCode", 80),
        lambda: ro.add_events([]),
    ]
    for write in writes:
        try:
            write()
            raised = False
        except ReadOnlyStoreError:
            raised = True
        assert raised
    ro.close()
