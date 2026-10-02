"""Shared test helpers for ETHSmartChecker: fixture loaders and stubs.

A plain module, not a pytest test file: no test_* functions and no
Test* classes, so pytest does not collect it. No network here: the
module imports neither urllib, http nor socket. FakeRpc and
FakeTransport answer from tests/fixtures/ and from queued values, so
tests never open the network.
"""

import json
import os
import sqlite3
import tempfile
import threading
import time

from ethsc.fingerprint import fingerprint
from ethsc.store import Store

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures")


def load_hex(name):
    """The code bytes of a fixture `code_*.hex` (or any hex fixture).

    Reads tests/fixtures/<name>, strips whitespace, drops the leading
    "0x" and returns bytes.fromhex of the rest. The file must contain a
    verbatim eth_getCode result string: "0x" + an even number of hex
    digits, no newline.
    """
    with open(os.path.join(_FIXTURES, name), "r", encoding="utf-8") as handle:
        text = handle.read().strip()
    if not text.startswith("0x"):
        raise ValueError("%s is not a 0x-hex code string" % name)
    return bytes.fromhex(text[2:])


def block_codes():
    """The address -> eth_getCode-result map of block 26077729.

    A fresh dict each call: json.load of
    tests/fixtures/codes_26077729.json, 206 keys (59 of them "0x").
    """
    with open(os.path.join(_FIXTURES, "codes_26077729.json"), "r",
              encoding="utf-8") as handle:
        return json.load(handle)


def block_receipts():
    """The receipt list of block 26077729 (a fresh list each call).

    json.load of tests/fixtures/receipts_26077729.json, element
    "result": a list of 218 receipt dicts, verbatim mainnet data.
    """
    with open(os.path.join(_FIXTURES, "receipts_26077729.json"), "r",
              encoding="utf-8") as handle:
        return json.load(handle)["result"]


def temp_store():
    """A fresh Store in a brand-new temporary directory.

    Every call creates a new tempfile.mkdtemp() directory and opens a
    Store on a sqlite file inside it, so two calls never share a
    database. The caller owns the directory (nobody cleans it up
    automatically).
    """
    directory = tempfile.mkdtemp(prefix="ethsc-test-")
    return Store(os.path.join(directory, "ethsc.sqlite"))


class FakeTransport(object):
    """A canned transport for ethsc.rpc.RpcClient.

    FakeTransport(answers, url="http://fake/") -- a callable object
    satisfying RpcClient's transport contract. Each invocation pops the
    next (status, body) pair off the answers list, in order, and
    returns it; every invocation is recorded as a (url, body) pair in
    self.calls. An empty list answers with (500, b"no more answers").
    """

    def __init__(self, answers, url="http://fake/"):
        self.answers = list(answers)
        self.url = url
        self.calls = []

    def __call__(self, url, body):
        self.calls.append((url, body))
        if not self.answers:
            return 500, b"no more answers"
        return self.answers.pop(0)


class FakeRpc(object):
    """A duck-typed rpc for ethsc.ingest.follow_chain, offline.

    FakeRpc(codes=None, receipts=None, head="0x18dea21", fail=None,
    null_receipts=False, storage=None) -- .call(method, params) answers
    from the fixture data: codes=None defaults to block_codes(),
    receipts=None to block_receipts(); eth_blockNumber returns head;
    eth_getBlockReceipts returns the receipt list, or None when
    null_receipts is True (the call is still recorded); eth_getCode
    returns codes[params[0]] (KeyError for an address outside the
    fixture map, which ingest_block counts as a failed call). If fail
    is not None, every call raises it instead of answering. Every
    call, answered or not, is recorded in self.calls as a
    (method, list(params)) pair, appended under a lock, because
    phase-10 code calls this object from worker threads.

    Phase 14: eth_getStorageAt answers storage[params[0]][params[1]]
    when storage is a dict, the zero word ("0x" + 64 zeros) when the
    address or the slot is absent from it, and raises KeyError(method)
    -- as every other unhandled method already did -- when storage is
    None (the default: a node that refuses the slot, keeping phase 9).
    """

    _ZERO_WORD = "0x" + "0" * 64

    def __init__(self, codes=None, receipts=None, head="0x18dea21",
                 fail=None, null_receipts=False, storage=None):
        self._codes = codes
        self._receipts = receipts
        self._head = head
        self._fail = fail
        self._null_receipts = null_receipts
        self._storage = storage
        self.calls = []
        self._lock = threading.Lock()

    def call(self, method, params):
        with self._lock:
            self.calls.append((method, list(params)))
        if self._fail is not None:
            raise self._fail
        if method == "eth_blockNumber":
            return self._head
        if method == "eth_getBlockReceipts":
            if self._null_receipts:
                return None
            if self._receipts is None:
                return block_receipts()
            return self._receipts
        if method == "eth_getCode":
            if self._codes is None:
                codes = block_codes()
            else:
                codes = self._codes
            return codes[params[0]]
        if method == "eth_getStorageAt":
            if self._storage is None:
                raise KeyError(method)
            return self._storage.get(params[0], {}).get(
                params[1], self._ZERO_WORD)
        raise KeyError(method)


class InterruptAfter(object):
    """Wraps an rpc: answers the first n calls, raises KeyboardInterrupt after.

    InterruptAfter(inner, n) -- .call(method, params) forwards to
    inner.call for the first n calls and raises KeyboardInterrupt from
    call n+1 on, forever. The wrapped object stays reachable as .inner,
    so its .calls log remains usable.
    """

    def __init__(self, inner, n):
        self.inner = inner
        self.n = n
        self._answered = 0

    def call(self, method, params):
        if self._answered >= self.n:
            raise KeyboardInterrupt
        self._answered += 1
        return self.inner.call(method, params)


def block_store():
    """A fresh Store filled from block_codes() at block 26077729.

    Takes no arguments, builds on temp_store() (a brand-new temporary
    directory each call, so two calls never share a database) and
    stores every entry of block_codes(): 206 addresses of block
    26077729, 147 of them with code, 130 distinct code_id, 59 stored
    with code_id None (their eth_getCode result is "0x").
    """
    store = temp_store()
    block = 26077729
    for address, text in sorted(block_codes().items()):
        if text == "0x":
            store.put_address(address, None, block)
        else:
            code_id = store.put_code(bytes.fromhex(text[2:]))
            store.put_address(address, code_id, block)
    return store


class CodeServer(object):
    """A get_code(address, block) callable with concurrency bookkeeping.

    CodeServer(codes=None, hold=0.0, raises=None) -- __call__(address,
    block) serves codes (None means block_codes(), loaded once in
    __init__): when address is a key of raises (None meaning {}), the
    mapped exception instance is raised (it may be KeyboardInterrupt),
    after the call is recorded; otherwise it sleeps hold seconds when
    hold > 0 and returns codes[address] (KeyError for an unknown
    address is fine). All bookkeeping lives under one lock: calls, the
    list of (address, block) in call order; peak, the largest number
    of calls in flight at once; threads, the set of
    threading.get_ident() of every caller.
    """

    def __init__(self, codes=None, hold=0.0, raises=None):
        self._codes = codes
        self._hold = hold
        self._raises = raises if raises is not None else {}
        self.calls = []
        self.peak = 0
        self.threads = set()
        self._lock = threading.Lock()
        self._in_flight = 0

    def __call__(self, address, block):
        with self._lock:
            self.calls.append((address, block))
            self.threads.add(threading.get_ident())
            self._in_flight += 1
            if self._in_flight > self.peak:
                self.peak = self._in_flight
        try:
            if address in self._raises:
                raise self._raises[address]
            if self._hold > 0:
                time.sleep(self._hold)
            if self._codes is None:
                return block_codes()[address]
            return self._codes[address]
        finally:
            with self._lock:
                self._in_flight -= 1


class FakeUrlopen(object):
    """A stand-in for urllib.request.urlopen: records, never opens.

    FakeUrlopen(status=200, body=b'{"jsonrpc":"2.0","id":1,
    "result":"0x1"}') -- a callable object: __call__(request, *args,
    **kwargs) appends request to self.requests and returns a response
    object usable in a with statement (__enter__ returns itself,
    __exit__ returns False) whose getcode() is status and read() is
    body. The module imports neither urllib, http nor socket, so this
    stub never touches the network.
    """

    def __init__(self, status=200,
                 body=b'{"jsonrpc":"2.0","id":1,"result":"0x1"}'):
        self.status = status
        self.body = body
        self.requests = []

    def __call__(self, request, *args, **kwargs):
        self.requests.append(request)
        return _FakeResponse(self.status, self.body)


class _FakeResponse(object):
    """The with-able response returned by FakeUrlopen."""

    def __init__(self, status, body):
        self._status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self):
        return self._status

    def read(self):
        return self._body


def legacy_db(phase):
    """A phase-13 or phase-14 schema sqlite file, built without Store.

    legacy_db(phase) -- phase is 13 or 14. Creates a brand-new
    tempfile.mkdtemp() directory and in it one sqlite file written
    with plain sqlite3 (never ethsc.store.Store, never PRAGMA
    journal_mode: the file stays in the default rollback journal mode
    "delete"), with the schema of that phase and no events table:
    codes (code_id, size, skeleton_hash, selectors, proxy_kind,
    proxy_target, code, std_proxy), addresses (address, code_id,
    block, origin -- plus implementation for phase 14), the index
    addresses_code_id, progress (key, block) with no updated_at
    column, seeds and ledger. Filled from block_codes(): all 206
    addresses lowercased at block 26077729, origin NULL (and
    implementation NULL); an address whose eth_getCode result is "0x"
    gets code_id NULL, every other code once in codes with its columns
    from ethsc.fingerprint.fingerprint (selectors as JSON text,
    std_proxy 1 or 0). Then the row ("progress", 26077729). Over the
    fixture: 130 codes (17 with std_proxy 1) and 206 addresses, 147
    with code. The connection is committed and closed before the path
    is returned; the caller owns the directory.
    """
    if phase not in (13, 14):
        raise ValueError("legacy_db: phase must be 13 or 14")
    directory = tempfile.mkdtemp(prefix="ethsc-legacy-")
    path = os.path.join(directory, "ethsc.sqlite")
    connection = sqlite3.connect(path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "CREATE TABLE codes (code_id TEXT PRIMARY KEY, size INTEGER,"
            " skeleton_hash TEXT, selectors TEXT, proxy_kind TEXT,"
            " proxy_target TEXT, code BLOB, std_proxy INTEGER)")
        address_columns = ("address TEXT PRIMARY KEY, code_id TEXT,"
                           " block INTEGER, origin TEXT")
        if phase == 14:
            address_columns += ", implementation TEXT"
        cursor.execute("CREATE TABLE addresses (%s)" % address_columns)
        cursor.execute(
            "CREATE INDEX addresses_code_id ON addresses(code_id)")
        cursor.execute(
            "CREATE TABLE progress (key TEXT PRIMARY KEY, block INTEGER)")
        cursor.execute(
            "CREATE TABLE seeds (address TEXT PRIMARY KEY, code_id TEXT,"
            " label TEXT)")
        cursor.execute(
            "CREATE TABLE ledger (day TEXT, method TEXT, credits INTEGER)")
        block = 26077729
        seen = set()
        for address, text in sorted(block_codes().items()):
            address = address.lower()
            if text == "0x":
                if phase == 14:
                    cursor.execute(
                        "INSERT INTO addresses VALUES (?, NULL, ?, NULL,"
                        " NULL)", (address, block))
                else:
                    cursor.execute(
                        "INSERT INTO addresses VALUES (?, NULL, ?, NULL)",
                        (address, block))
                continue
            code = bytes.fromhex(text[2:])
            fp = fingerprint(code)
            if fp["code_id"] not in seen:
                seen.add(fp["code_id"])
                cursor.execute(
                    "INSERT INTO codes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (fp["code_id"], fp["size"], fp["skeleton_hash"],
                     json.dumps(fp["selectors"]),
                     fp["proxy"]["kind"] if fp["proxy"] is not None else None,
                     fp["proxy"]["target"] if fp["proxy"] is not None
                     else None,
                     code, 1 if fp["std_proxy"] else 0))
            if phase == 14:
                cursor.execute(
                    "INSERT INTO addresses VALUES (?, ?, ?, NULL, NULL)",
                    (address, fp["code_id"], block))
            else:
                cursor.execute(
                    "INSERT INTO addresses VALUES (?, ?, ?, NULL)",
                    (address, fp["code_id"], block))
        cursor.execute("INSERT INTO progress VALUES (?, ?)",
                       ("progress", block))
        connection.commit()
    finally:
        connection.close()
    return path
