"""SQLite persistence for ETHSmartChecker.

Store(path) opens or creates the Code Database (CREATE TABLE IF NOT
EXISTS): distinct codes with their fingerprints, addresses pointing at
codes, the follow progress, the security watchlist and the daily credit
ledger. One file, stdlib sqlite3. Every write commits before returning;
every list the store returns is sorted; addresses are stored lowercase.
Origin (phase 13): the store only carries the text a caller gives it
(put_address's origin) and reads it back through origins(); it never
decides what "created" or "seen" means, and it never rewrites the
origin of a row already stored. Implementation (phase 14): the
"implementation" column carries whatever address a caller gives
set_implementation; the store never reads a slot and never decides
what the value means -- that is ingest's job. Phase 15: a writable
open switches the file to journal_mode=WAL, records the live stream
in the events table (add_events / events / event_counts), stamps
set_progress with the UTC time read back by progress_at, aggregates
origins through origin_counts, and Store(path, readonly=True) opens
an existing file for reading only, raising ReadOnlyStoreError from
every write method and never migrating the file.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from ethsc.evm import is_std_proxy
from ethsc.fingerprint import fingerprint


_SCHEMA = """
CREATE TABLE IF NOT EXISTS codes (
    code_id TEXT PRIMARY KEY,
    size INTEGER,
    skeleton_hash TEXT,
    selectors TEXT,
    proxy_kind TEXT,
    proxy_target TEXT,
    code BLOB,
    std_proxy INTEGER
);
CREATE TABLE IF NOT EXISTS addresses (
    address TEXT PRIMARY KEY,
    code_id TEXT,
    block INTEGER,
    origin TEXT,
    implementation TEXT
);
CREATE INDEX IF NOT EXISTS addresses_code_id ON addresses(code_id);
CREATE TABLE IF NOT EXISTS progress (
    key TEXT PRIMARY KEY,
    block INTEGER,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS seeds (
    address TEXT PRIMARY KEY,
    code_id TEXT,
    label TEXT
);
CREATE TABLE IF NOT EXISTS ledger (
    day TEXT,
    method TEXT,
    credits INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    kind TEXT,
    block INTEGER,
    at TEXT,
    address TEXT,
    seed_address TEXT,
    label TEXT,
    score REAL,
    origin TEXT,
    old_impl TEXT,
    new_impl TEXT
);
"""

_EVENT_KINDS = ("ALERT", "UPGRADE")


class ReadOnlyStoreError(Exception):
    """Raised by a write method of a Store opened with readonly=True."""


def _low(value):
    """Lowercase an address-like text; pass None through."""
    if isinstance(value, str):
        return value.lower()
    return value


class Store(object):
    """One SQLite file holding the Code Database."""

    def __init__(self, path: str, readonly: bool = False) -> None:
        self._readonly = readonly
        if readonly:
            self._conn = sqlite3.connect(
                "file:" + path + "?mode=ro", uri=True)
            # Tolerate exactly the three newest additions missing from an
            # older file: a read cannot add them, so the readers ask these
            # flags instead of writing. Detected once, at open.
            self._ro_no_events = not self._has_table("events")
            self._ro_no_updated = (
                "updated_at" not in self._columns("progress"))
            self._ro_no_impl = (
                "implementation" not in self._columns("addresses"))
            return
        self._conn = sqlite3.connect(path)
        # WAL first, before anything else touches the file: a reader then
        # never blocks the listener's writes and the listener never blocks
        # a reader. The pragma is persistent in the file; an already-WAL
        # file is left as it is.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        columns = [row[1] for row in
                   self._conn.execute("PRAGMA table_info(codes)").fetchall()]
        if "std_proxy" not in columns:
            self._conn.execute(
                "ALTER TABLE codes ADD COLUMN std_proxy INTEGER")
            self._conn.commit()
        address_columns = [row[1] for row in self._conn.execute(
            "PRAGMA table_info(addresses)").fetchall()]
        if "origin" not in address_columns:
            # Phase 13: no UPDATE of old rows -- their origin stays NULL
            # in the file and reads back as "unknown" through origins().
            self._conn.execute(
                "ALTER TABLE addresses ADD COLUMN origin TEXT")
            self._conn.commit()
            address_columns.append("origin")
        if "implementation" not in address_columns:
            # Phase 14: no UPDATE of old rows -- their implementation
            # stays NULL in the file; set_implementation is the one
            # write that changes a stored row.
            self._conn.execute(
                "ALTER TABLE addresses ADD COLUMN implementation TEXT")
            self._conn.commit()
        progress_columns = [row[1] for row in self._conn.execute(
            "PRAGMA table_info(progress)").fetchall()]
        if "updated_at" not in progress_columns:
            # Phase 15: no UPDATE of old rows -- the progress row keeps
            # NULL until the next set_progress stamps it.
            self._conn.execute(
                "ALTER TABLE progress ADD COLUMN updated_at TEXT")
            self._conn.commit()
        self._fill_std_proxy()
        self._conn.commit()

    def _columns(self, table: str) -> List[str]:
        return [row[1] for row in
                self._conn.execute(
                    "PRAGMA table_info(%s)" % table).fetchall()]

    def _has_table(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,),
        ).fetchone()
        return row is not None

    def _guard_write(self) -> None:
        if self._readonly:
            raise ReadOnlyStoreError("store opened read-only")

    def _fill_std_proxy(self) -> None:
        """Fill every NULL std_proxy from is_std_proxy of the stored code.

        Runs on every open, so a fill interrupted after the ALTER, or a
        row written by an older ethsc, is repaired instead of scoring as
        a non-proxy forever. Commits once it is done.
        """
        rows = self._conn.execute(
            "SELECT code_id, code FROM codes WHERE std_proxy IS NULL"
        ).fetchall()
        if not rows:
            return
        for code_id, code in rows:
            value = 1 if is_std_proxy(bytes(code)) else 0
            self._conn.execute(
                "UPDATE codes SET std_proxy = ? WHERE code_id = ?",
                (value, code_id),
            )
        self._conn.commit()

    def close(self) -> None:
        """Close the connection; a reopened Store(path) sees everything."""
        self._conn.close()

    # -- Store Codes And Contracts ----------------------------------------

    def put_code(self, code: bytes) -> str:
        """Store a code and its Fingerprint once per code_id.

        Repeated calls with the same code return the same code_id, add
        no rows and do not raise.
        """
        self._guard_write()
        fp = fingerprint(code)
        code_id = fp["code_id"]
        self._conn.execute(
            "INSERT OR IGNORE INTO codes (code_id, size, skeleton_hash,"
            " selectors, proxy_kind, proxy_target, code, std_proxy)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                code_id,
                fp["size"],
                fp["skeleton_hash"],
                json.dumps(fp["selectors"]),
                fp["proxy"]["kind"] if fp["proxy"] else None,
                fp["proxy"]["target"] if fp["proxy"] else None,
                sqlite3.Binary(code),
                1 if fp["std_proxy"] else 0,
            ),
        )
        self._conn.commit()
        return code_id

    def put_address(self, address: str, code_id: Optional[str],
                    block: int, origin: Optional[str] = None) -> None:
        """Record an address (code_id None for an account without code).

        Known addresses are not changed (the first record wins, origin
        included) and do not raise. origin is stored verbatim (None as
        NULL); the store does not validate the text.
        """
        self._guard_write()
        self._conn.execute(
            "INSERT OR IGNORE INTO addresses (address, code_id, block,"
            " origin) VALUES (?, ?, ?, ?)",
            (address.lower(), code_id, block, origin),
        )
        self._conn.commit()

    def has_address(self, address: str) -> bool:
        """True iff the address (case-insensitive) is stored."""
        row = self._conn.execute(
            "SELECT 1 FROM addresses WHERE address = ?",
            (address.lower(),),
        ).fetchone()
        return row is not None

    def code_of(self, address: str) -> Optional[bytes]:
        """The stored code of the address, or None (no code / unknown)."""
        row = self._conn.execute(
            "SELECT code FROM codes c JOIN addresses a"
            " ON a.code_id = c.code_id WHERE a.address = ?",
            (address.lower(),),
        ).fetchone()
        if row is None:
            return None
        return bytes(row[0])

    def addresses_of(self, code_id: str) -> List[str]:
        """Sorted lowercase addresses pointing at code_id; [] if unknown."""
        rows = self._conn.execute(
            "SELECT address FROM addresses WHERE code_id = ? ORDER BY address",
            (code_id,),
        ).fetchall()
        return [row[0] for row in rows]

    def origins(self) -> dict:
        """{address: origin} for every stored address (phase 13).

        One SELECT over addresses; a NULL origin (a row stored before
        phase 13, or with origin=None) reads back as "unknown". An
        empty database gives {}.
        """
        rows = self._conn.execute(
            "SELECT address, origin FROM addresses"
        ).fetchall()
        return {
            address: ("unknown" if origin is None else origin)
            for address, origin in rows
        }

    def origin_counts(self, since_block: Optional[int] = None) -> dict:
        """{origin: count} over the addresses table (phase 15).

        One SELECT ... GROUP BY; a NULL origin counts under "unknown".
        With since_block given, only the rows whose block >= since_block
        count. Every addresses row counts, with or without code. An
        empty database gives {}.
        """
        if since_block is None:
            rows = self._conn.execute(
                "SELECT COALESCE(origin, 'unknown') AS o, COUNT(*)"
                " FROM addresses GROUP BY o"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT COALESCE(origin, 'unknown') AS o, COUNT(*)"
                " FROM addresses WHERE block >= ? GROUP BY o",
                (since_block,),
            ).fetchall()
        return {origin: int(count) for origin, count in rows}

    def set_implementation(self, address: str, implementation: str) -> None:
        """Write the implementation address a proxy delegates through.

        The one write that changes a stored row (phase 14): UPDATE, both
        values lowercased, committed. Nothing is decided here -- the
        caller gives the address exactly as it means it (an
        EIP-1967/UUPS implementation or a beacon address). An address
        the store does not hold changes nothing and does not raise; a
        later call overwrites (the upgrade case).
        """
        self._guard_write()
        self._conn.execute(
            "UPDATE addresses SET implementation = ? WHERE address = ?",
            (implementation.lower(), address.lower()),
        )
        self._conn.commit()

    def implementation(self, address: str) -> Optional[str]:
        """The stored implementation of address, or None.

        None for an unknown address, a stored NULL, or an address whose
        code is not a standard proxy -- the column is written for
        standard proxies only, but this reader does not check that.
        """
        if self._readonly and self._ro_no_impl:
            return None
        row = self._conn.execute(
            "SELECT implementation FROM addresses WHERE address = ?",
            (address.lower(),),
        ).fetchone()
        if row is None:
            return None
        return row[0]

    def implementations(self) -> dict:
        """{address: {"implementation", "code_id"}} over standard proxies.

        One SELECT joining addresses with codes (std_proxy = 1) and, by
        implementation, with addresses again for the implementation's
        code_id (None when the implementation is unknown, not stored,
        or stored without code). An address without code, or whose code
        is not a standard proxy, is absent. An empty database gives {}.
        """
        if self._readonly and self._ro_no_impl:
            # A phase-13 file read-only: the column cannot be added, so
            # every standard-proxy address reads as unresolved.
            rows = self._conn.execute(
                "SELECT a.address FROM addresses a"
                " JOIN codes c ON a.code_id = c.code_id"
                " WHERE c.std_proxy = 1"
            ).fetchall()
            return {
                address: {"implementation": None, "code_id": None}
                for (address,) in rows
            }
        rows = self._conn.execute(
            "SELECT a.address, a.implementation, i.code_id"
            " FROM addresses a JOIN codes c ON a.code_id = c.code_id"
            " LEFT JOIN addresses i ON i.address = a.implementation"
            " WHERE c.std_proxy = 1"
        ).fetchall()
        return {
            address: {"implementation": implementation, "code_id": code_id}
            for address, implementation, code_id in rows
        }

    # -- Read Codes In Bulk --------------------------------------------------

    def fingerprints(self) -> List[dict]:
        """One Fingerprint dict per row of codes, sorted by code_id.

        Each dict has exactly the keys code_id, size, skeleton_hash,
        selectors (a list), proxy ({"kind", "target"} or None) and
        std_proxy (a bool); it equals fingerprint(code) of the stored
        code. Empty db gives [].
        """
        rows = self._conn.execute(
            "SELECT code_id, size, skeleton_hash, selectors,"
            " proxy_kind, proxy_target, std_proxy FROM codes"
            " ORDER BY code_id"
        ).fetchall()
        result = []
        for code_id, size, skeleton_hash, selectors, kind, target, std in rows:
            proxy = None
            if kind is not None:
                proxy = {"kind": kind, "target": target}
            result.append(
                {
                    "code_id": code_id,
                    "size": size,
                    "skeleton_hash": skeleton_hash,
                    "selectors": json.loads(selectors),
                    "proxy": proxy,
                    "std_proxy": bool(std),
                }
            )
        return result

    def code_by_id(self, code_id: str) -> Optional[bytes]:
        """The stored code as bytes, or None for an unknown code_id."""
        row = self._conn.execute(
            "SELECT code FROM codes WHERE code_id = ?", (code_id,)
        ).fetchone()
        if row is None:
            return None
        return bytes(row[0])

    # -- Track Progress ----------------------------------------------------

    def get_progress(self) -> Optional[int]:
        """The last fully ingested block, or None on a fresh db."""
        row = self._conn.execute(
            "SELECT block FROM progress WHERE key = ?", ("progress",)
        ).fetchone()
        if row is None:
            return None
        return row[0]

    def set_progress(self, block: int) -> None:
        """Store (overwrite) the last fully ingested block.

        Phase 15: also writes updated_at, the UTC time of the call as
        text "YYYY-MM-DDTHH:MM:SSZ" -- the listener's heartbeat.
        """
        self._guard_write()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._conn.execute(
            "INSERT OR REPLACE INTO progress (key, block, updated_at)"
            " VALUES (?, ?, ?)",
            ("progress", block, now),
        )
        self._conn.commit()

    def progress_at(self) -> Optional[str]:
        """The updated_at of the progress row, or None (phase 15).

        None on a fresh db, and None for a progress row written before
        phase 15 until the next set_progress stamps it.
        """
        if self._readonly and self._ro_no_updated:
            return None
        row = self._conn.execute(
            "SELECT updated_at FROM progress WHERE key = ?", ("progress",)
        ).fetchone()
        if row is None:
            return None
        return row[0]

    # -- Manage Watchlist ---------------------------------------------------

    def add_seed(self, address: str, label: str) -> None:
        """Mark the stored code of address as a known-bad seed.

        Raises KeyError(address) when the address has no stored code
        (unknown, or an EOA). Adding twice keeps one seed with the
        latest label.

        Seeding through the implementation (phase 14): when address is a
        standard proxy whose implementations() entry carries a code_id
        (its implementation is stored with code), the seed's code_id is
        the implementation's -- the seed row's address stays the
        proxy's address. Otherwise the address's own code_id, as
        before. Read at the time of the call; a later set_implementation
        does not move the seed.
        """
        self._guard_write()
        address = address.lower()
        row = self._conn.execute(
            "SELECT code_id FROM addresses WHERE address = ?", (address,)
        ).fetchone()
        if row is None or row[0] is None:
            raise KeyError(address)
        code_id = row[0]
        impl_entry = self.implementations().get(address)
        if impl_entry is not None and impl_entry["code_id"] is not None:
            code_id = impl_entry["code_id"]
        self._conn.execute(
            "INSERT OR REPLACE INTO seeds (address, code_id, label)"
            " VALUES (?, ?, ?)",
            (address, code_id, label),
        )
        self._conn.commit()

    def seeds(self) -> List[dict]:
        """List of {address, label, code_id}, sorted by address."""
        rows = self._conn.execute(
            "SELECT address, label, code_id FROM seeds ORDER BY address"
        ).fetchall()
        return [
            {"address": row[0], "label": row[1], "code_id": row[2]}
            for row in rows
        ]

    def remove_seed(self, address: str) -> bool:
        """Delete the seed of address; True iff a row was deleted.

        Takes the address in any case. Never raises for an address the
        db does not know or one that is stored but not a seed: both
        give False and change nothing. The codes and addresses rows of
        that address stay as they were, so the address can be seeded
        again with add_seed and no rpc call.
        """
        self._guard_write()
        address = address.lower()
        cursor = self._conn.execute(
            "DELETE FROM seeds WHERE address = ?", (address,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Budget Ledger ------------------------------------------------------

    def spend(self, day: str, method: str, credits: int) -> None:
        """Add credits to the ledger of a UTC day ("YYYY-MM-DD")."""
        self._guard_write()
        self._conn.execute(
            "INSERT INTO ledger (day, method, credits) VALUES (?, ?, ?)",
            (day, method, credits),
        )
        self._conn.commit()

    def spent(self, day: str) -> int:
        """The day's total credits; 0 for a day with no entries."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(credits), 0) FROM ledger WHERE day = ?",
            (day,),
        ).fetchone()
        return int(row[0])

    # -- Base Counts ---------------------------------------------------------

    def counts(self) -> dict:
        """Read-only aggregates: exactly five int keys.

        addresses is the row count of the addresses table, split into
        addresses_with_code (code_id not NULL) and addresses_without_code
        (code_id NULL); codes is the row count of codes; blocks is the
        number of DISTINCT block values in addresses. Pure read: no
        write, no commit. Empty db: all five keys are 0.
        """
        addresses, with_code = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(code_id IS NOT NULL), 0)"
            " FROM addresses"
        ).fetchone()
        codes = self._conn.execute(
            "SELECT COUNT(*) FROM codes"
        ).fetchone()[0]
        blocks = self._conn.execute(
            "SELECT COUNT(DISTINCT block) FROM addresses"
        ).fetchone()[0]
        return {
            "addresses": int(addresses),
            "addresses_with_code": int(with_code),
            "addresses_without_code": int(addresses) - int(with_code),
            "codes": int(codes),
            "blocks": int(blocks),
        }

    def ledger_days(self) -> List[dict]:
        """[{day, credits}] summing every method of one day, by day asc.

        Pure read: no write, no commit. Empty ledger gives [].
        """
        rows = self._conn.execute(
            "SELECT day, COALESCE(SUM(credits), 0) FROM ledger"
            " GROUP BY day ORDER BY day ASC"
        ).fetchall()
        return [{"day": row[0], "credits": int(row[1])} for row in rows]

    # -- Record Events -------------------------------------------------------

    def add_events(self, events: List[dict]) -> None:
        """Write a list of Event dicts in one transaction (phase 15).

        Each element carries kind ("ALERT" or "UPGRADE"), block and at,
        plus the fields of its kind: an ALERT carries address,
        seed_address, label, score, origin; an UPGRADE carries address,
        old_impl, new_impl. A key the element lacks is stored NULL;
        extra keys are ignored. Addresses are stored lowercase. The
        rows get increasing ids in list order. The whole list is one
        transaction: a kind other than ALERT or UPGRADE anywhere in it
        raises ValueError and nothing of the list is written.
        add_events([]) writes nothing and does not raise.
        """
        self._guard_write()
        if not events:
            return
        rows = []
        for event in events:
            kind = event.get("kind")
            if kind not in _EVENT_KINDS:
                raise ValueError("bad event kind: %r" % (kind,))
            rows.append(
                (
                    kind,
                    event.get("block"),
                    event.get("at"),
                    _low(event.get("address")),
                    _low(event.get("seed_address")),
                    event.get("label"),
                    event.get("score"),
                    event.get("origin"),
                    _low(event.get("old_impl")),
                    _low(event.get("new_impl")),
                )
            )
        self._conn.executemany(
            "INSERT INTO events (kind, block, at, address, seed_address,"
            " label, score, origin, old_impl, new_impl)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def events(self, after_id: int = 0, limit: int = 100) -> List[dict]:
        """The newest `limit` events with id > after_id, id descending.

        Each Event is a dict with exactly the eleven keys id, kind,
        block, at, address, seed_address, label, score, origin,
        old_impl, new_impl; a stored NULL reads back as None, score as
        a float. A file without the events table (read-only open of an
        older db) gives [].
        """
        if self._readonly and self._ro_no_events:
            return []
        rows = self._conn.execute(
            "SELECT id, kind, block, at, address, seed_address, label,"
            " score, origin, old_impl, new_impl FROM events"
            " WHERE id > ? ORDER BY id DESC LIMIT ?",
            (after_id, limit),
        ).fetchall()
        return [
            {
                "id": row[0],
                "kind": row[1],
                "block": row[2],
                "at": row[3],
                "address": row[4],
                "seed_address": row[5],
                "label": row[6],
                "score": None if row[7] is None else float(row[7]),
                "origin": row[8],
                "old_impl": row[9],
                "new_impl": row[10],
            }
            for row in rows
        ]

    def event_counts(self) -> dict:
        """Counts per kind and per seed of the events table (phase 15).

        {"kinds": {"ALERT": a, "UPGRADE": u}, "seeds": [{"label",
        "seed_address", "count"}, ...]}: kinds has both keys always
        (0 when absent); seeds groups the ALERT rows by (seed_address,
        label), sorted by count descending, then label, then
        seed_address. A file without the events table gives zeros.
        """
        no_events = self._readonly and self._ro_no_events
        if no_events:
            kinds = {}
        else:
            kinds = dict(self._conn.execute(
                "SELECT kind, COUNT(*) FROM events GROUP BY kind"
            ).fetchall())
        if no_events:
            seeds = []
        else:
            rows = self._conn.execute(
                "SELECT seed_address, label, COUNT(*) FROM events"
                " WHERE kind = 'ALERT' GROUP BY seed_address, label"
            ).fetchall()
            seeds = [
                {"label": label, "seed_address": seed_address,
                 "count": int(count)}
                for seed_address, label, count in rows
            ]
        seeds.sort(key=lambda s: (-s["count"], s["label"],
                                  s["seed_address"]))
        return {
            "kinds": {
                "ALERT": int(kinds.get("ALERT", 0)),
                "UPGRADE": int(kinds.get("UPGRADE", 0)),
            },
            "seeds": seeds,
        }
