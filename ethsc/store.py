"""SQLite persistence for ETHSmartChecker.

Store(path) opens or creates the Code Database (CREATE TABLE IF NOT
EXISTS): distinct codes with their fingerprints, addresses pointing at
codes, the follow progress, the security watchlist and the daily credit
ledger. One file, stdlib sqlite3. Every write commits before returning;
every list the store returns is sorted; addresses are stored lowercase.
Origin (phase 13): the store only carries the text a caller gives it
(put_address's origin) and reads it back through origins(); it never
decides what "created" or "seen" means, and it never rewrites the
origin of a row already stored.
"""

import json
import sqlite3
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
    origin TEXT
);
CREATE INDEX IF NOT EXISTS addresses_code_id ON addresses(code_id);
CREATE TABLE IF NOT EXISTS progress (
    key TEXT PRIMARY KEY,
    block INTEGER
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
"""


class Store(object):
    """One SQLite file holding the Code Database."""

    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
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
        self._fill_std_proxy()
        self._conn.commit()

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
        """Store (overwrite) the last fully ingested block."""
        self._conn.execute(
            "INSERT OR REPLACE INTO progress (key, block) VALUES (?, ?)",
            ("progress", block),
        )
        self._conn.commit()

    # -- Manage Watchlist ---------------------------------------------------

    def add_seed(self, address: str, label: str) -> None:
        """Mark the stored code of address as a known-bad seed.

        Raises KeyError(address) when the address has no stored code
        (unknown, or an EOA). Adding twice keeps one seed with the
        latest label.
        """
        address = address.lower()
        row = self._conn.execute(
            "SELECT code_id FROM addresses WHERE address = ?", (address,)
        ).fetchone()
        if row is None or row[0] is None:
            raise KeyError(address)
        self._conn.execute(
            "INSERT OR REPLACE INTO seeds (address, code_id, label)"
            " VALUES (?, ?, ?)",
            (address, row[0], label),
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
        address = address.lower()
        cursor = self._conn.execute(
            "DELETE FROM seeds WHERE address = ?", (address,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Budget Ledger ------------------------------------------------------

    def spend(self, day: str, method: str, credits: int) -> None:
        """Add credits to the ledger of a UTC day ("YYYY-MM-DD")."""
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
