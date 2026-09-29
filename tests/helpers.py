"""Shared test helpers for ETHSmartChecker: fixture loaders and stubs.

A plain module, not a pytest test file: no test_* functions and no
Test* classes, so pytest does not collect it. No network here: the
module imports neither urllib, http nor socket. FakeRpc and
FakeTransport answer from tests/fixtures/ and from queued values, so
tests never open the network.
"""

import json
import os
import tempfile

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

    FakeRpc(codes=None, receipts=None, head="0x18dea21", fail=None) --
    .call(method, params) answers from the fixture data: codes=None
    defaults to block_codes(), receipts=None to block_receipts();
    eth_blockNumber returns head; eth_getBlockReceipts returns the
    receipt list; eth_getCode returns codes[params[0]] (KeyError for an
    address outside the fixture map, which ingest_block counts as a
    failed call). If fail is not None, every call raises it instead of
    answering. Every call, answered or not, is recorded in self.calls
    as a (method, list(params)) pair.
    """

    def __init__(self, codes=None, receipts=None, head="0x18dea21",
                 fail=None):
        self._codes = codes
        self._receipts = receipts
        self._head = head
        self._fail = fail
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, list(params)))
        if self._fail is not None:
            raise self._fail
        if method == "eth_blockNumber":
            return self._head
        if method == "eth_getBlockReceipts":
            if self._receipts is None:
                return block_receipts()
            return self._receipts
        if method == "eth_getCode":
            if self._codes is None:
                codes = block_codes()
            else:
                codes = self._codes
            return codes[params[0]]
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
