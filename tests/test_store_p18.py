"""Smoke tests for the phase-18 seeds.strict column (ethsc/store.py)."""

import os
import sqlite3
import tempfile

from ethsc.store import ReadOnlyStoreError, Store

from tests.helpers import load_hex, temp_store


def test_strict_set_unset_and_readd_keeps_flag():
    store = temp_store()
    code_id = store.put_code(load_hex("code_belle.hex"))
    store.put_address("0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                      code_id, 1)
    store.add_seed("0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                   "BELLE honeypot")
    assert store.strict_seeds() == []
    assert store.set_seed_strict(
        "0x34C6211621F2763C60EB007DC2AE91090A2D22F6", True) is True
    assert store.strict_seeds() == [
        "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"]
    # Re-add updates label in place and keeps the flag.
    store.add_seed("0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                   "BELLE again")
    assert store.strict_seeds() == [
        "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"]
    assert store.seeds()[0]["label"] == "BELLE again"
    assert store.set_seed_strict(
        "0x34c6211621f2763c60eb007dc2ae91090a2d22f6", False) is True
    assert store.strict_seeds() == []
    store.close()


def test_set_seed_strict_on_non_seed_writes_nothing():
    store = temp_store()
    code_id = store.put_code(load_hex("code_belle.hex"))
    store.put_address("0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                      code_id, 1)
    assert store.set_seed_strict("0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                                 True) is False
    assert store.set_seed_strict(
        "0x1111111111111111111111111111111111111111", True) is False
    assert store.strict_seeds() == []
    store.close()


def test_remove_seed_takes_flag_with_it():
    store = temp_store()
    code_id = store.put_code(load_hex("code_belle.hex"))
    address = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
    store.put_address(address, code_id, 1)
    store.add_seed(address, "BELLE honeypot")
    store.set_seed_strict(address, True)
    assert store.remove_seed(address) is True
    store.add_seed(address, "BELLE honeypot")
    assert store.strict_seeds() == []
    store.close()


def test_flag_survives_reopen_and_schema_migration():
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "db.sqlite")
    # A phase-15 file: seeds without the strict column.
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE seeds (address TEXT PRIMARY KEY, code_id TEXT,"
        " label TEXT);"
    )
    conn.execute(
        "INSERT INTO seeds (address, code_id, label) VALUES (?, ?, ?)",
        ("0x34c6211621f2763c60eb007dc2ae91090a2d22f6", "c", "old"),
    )
    conn.commit()
    conn.close()
    store = Store(path)
    assert store.strict_seeds() == []  # NULL reads as loose
    store.set_seed_strict("0x34c6211621f2763c60eb007dc2ae91090a2d22f6", True)
    store.close()
    reopened = Store(path)
    assert reopened.strict_seeds() == [
        "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"]
    reopened.close()
    # Read-only open of a file without the column: [] and write raises.
    ro = Store(path, readonly=True)
    assert isinstance(ro.strict_seeds(), list)
    try:
        ro.set_seed_strict("0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                           True)
        assert False, "expected ReadOnlyStoreError"
    except ReadOnlyStoreError:
        pass
    ro.close()
