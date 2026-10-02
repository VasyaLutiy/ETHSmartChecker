"""Judge tests for the phase-15 CLI examples (Command Line 51-56).

One unittest test per Contour example, in order:

- 51: backfill --alert-on created prints no ALERT lines, yet the
  store's events hold the unfiltered list -- the two ALERT events of
  the plain run of example 48, newest first.
- 52: the UPGRADE backfill (the FakeRpc of example 49) on the db of
  example 48 after its plain run prints exactly one UPGRADE line and
  records it as event id 3, after the two ALERT events.
- 53: recheck and seed add are not the live stream: they print ALERT
  lines and write no events.
- 54: dashboard on a --db path that is not an existing file: exit 2,
  one stderr line, empty stdout, no file created.
- 55: dashboard blocks until Ctrl-C through the patched make_server,
  announces the address on stderr and never touches a phase-13 file.
- 56: a busy port and a non-integer --port are usage-level failures:
  exit 2, one stderr line each, no traceback.

Every db a test builds lives in its own tempfile.mkdtemp() directory.
The only network a test touches is a TCP socket bound to 127.0.0.1
(test 56), never getaddrinfo, never a remote host.
"""

import contextlib
import hashlib
import io
import json
import os
import re
import socket
import tempfile
import unittest
from unittest import mock

try:
    from tests.helpers import block_codes, load_hex, legacy_db, temp_store
    from tests.helpers import FakeRpc
except ImportError:  # pragma: no cover - direct execution layout
    from helpers import block_codes, load_hex, legacy_db, temp_store
    from helpers import FakeRpc

from ethsc import dashboard
from ethsc.cli import main
from ethsc.store import Store

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures")

_BLOCK = 26077729
_HEAD = "0x18dea21"
_PROXY_ADDR = "0x0c0105334a50db16b51b2911c9956539753a2cf8"
_IMPL_ADDR = "0x72b971717e088b59f26d4236be222adb6acd393b"
_SEED_ADDR = "0x1111111111111111111111111111111111111111"
_NEW_IMPL = "0xe440cc08a71694c8229323803f59024e3144630e"
_IMPL_SLOT = ("0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3"
              "ca505d382bbc")
_BELLE_ADDR = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_BELLE_COPY_ADDR = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"

_EVENT_KEYS = {"id", "kind", "block", "at", "address", "seed_address",
               "label", "score", "origin", "old_impl", "new_impl"}
_AT_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def _code_text(name):
    """The verbatim eth_getCode result string of a code_*.hex fixture."""
    with open(os.path.join(_FIXTURES, name), "r", encoding="utf-8") as handle:
        return handle.read().strip()


def _load_storage():
    """The {address: {slot: word}} slot fixture storage_26077729.json."""
    with open(os.path.join(_FIXTURES, "storage_26077729.json"), "r",
              encoding="utf-8") as handle:
        return json.load(handle)


def _impl_copy_db():
    """The db of Command Line example 48: the implementation of the
    seed proxy stored at 0x1111...1111 (block 1) and seeded
    "impl copy seed". Returns the db path."""
    directory = tempfile.mkdtemp(prefix="ethsc-p15-judge-")
    db = os.path.join(directory, "ethsc.sqlite")
    store = Store(db)
    code_id = store.put_code(load_hex("code_impl_72b97171.hex"))
    store.put_address(_SEED_ADDR, code_id, 1)
    store.add_seed(_SEED_ADDR, "impl copy seed")
    store.close()
    return db


def _fake_impl_copy():
    """The FakeRpc of example 48: one candidate, the seed proxy, whose
    EIP-1967 slot reads the implementation 0x72b9...393b."""
    return FakeRpc(
        codes={
            _PROXY_ADDR: _code_text("code_proxy_seed_0c010533.hex"),
            _IMPL_ADDR: _code_text("code_impl_72b97171.hex"),
        },
        receipts=[{"to": _PROXY_ADDR}],
        storage=_load_storage(),
        head=_HEAD,
    )


def _fake_upgrade():
    """The FakeRpc of example 49: the same proxy candidate, but its
    implementation slot now reads 0xe440...630e (served WETH9)."""
    return FakeRpc(
        codes={
            _PROXY_ADDR: _code_text("code_proxy_seed_0c010533.hex"),
            _NEW_IMPL: _code_text("code_weth9.hex"),
        },
        receipts=[{"to": _PROXY_ADDR}],
        storage={_PROXY_ADDR: {_IMPL_SLOT: "0x" + "0" * 24 + _NEW_IMPL[2:]}},
        head=_HEAD,
    )


def _belle_copy_db():
    """The db of example 53: BELLE at block 1 and its copy at block 2,
    stored by put_code and put_address, no seed."""
    directory = tempfile.mkdtemp(prefix="ethsc-p15-judge-")
    db = os.path.join(directory, "ethsc.sqlite")
    store = Store(db)
    seed_id = store.put_code(load_hex("code_belle.hex"))
    store.put_address(_BELLE_ADDR, seed_id, 1)
    copy_id = store.put_code(load_hex("code_belle_copy_1807090d.hex"))
    store.put_address(_BELLE_COPY_ADDR, copy_id, 2)
    store.close()
    return db


def _block_db():
    """A db filled from block_codes() like block_store(), path returned."""
    directory = tempfile.mkdtemp(prefix="ethsc-p15-judge-")
    db = os.path.join(directory, "ethsc.sqlite")
    store = Store(db)
    for address, text in sorted(block_codes().items()):
        if text == "0x":
            store.put_address(address, None, _BLOCK)
        else:
            store.put_address(address, store.put_code(
                bytes.fromhex(text[2:])), _BLOCK)
    store.close()
    return db


def _run_main(argv, rpc=None):
    """main(argv[, rpc]) with stdout and stderr captured.

    Returns (exit code, stdout text, stderr text).
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if rpc is None:
            code = main(argv)
        else:
            code = main(argv, rpc=rpc)
    return code, out.getvalue(), err.getvalue()


def _sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


class _StubServer(object):
    """The server ethsc.dashboard.make_server is patched to return.

    server_address is fixed at ("127.0.0.1", 8080); serve_forever
    raises KeyboardInterrupt (a Ctrl-C); server_close counts its calls.
    """

    def __init__(self):
        self.server_address = ("127.0.0.1", 8080)
        self.closed = 0

    def serve_forever(self):
        raise KeyboardInterrupt

    def server_close(self):
        self.closed += 1


class TestCliExamplesP15(unittest.TestCase):

    def test_command_line_51(self):
        """Example 51: --alert-on created hides stdout; events hold the
        unfiltered list, in the order of the plain run of example 48."""
        db = _impl_copy_db()
        fake = _fake_impl_copy()
        code, out, err = _run_main(
            ["--db", db, "backfill",
             "--from", str(_BLOCK), "--to", str(_BLOCK),
             "--alert-on", "created"],
            rpc=fake)
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertEqual(err, "")

        store = Store(db)
        try:
            events = store.events()
        finally:
            store.close()
        self.assertEqual([event["id"] for event in events], [2, 1])
        for event in events:
            self.assertEqual(set(event.keys()), _EVENT_KEYS)
            self.assertEqual(event["kind"], "ALERT")
            self.assertEqual(event["block"], _BLOCK)
            self.assertTrue(_AT_RE.match(event["at"]))
            self.assertEqual(event["seed_address"], _SEED_ADDR)
            self.assertEqual(event["label"], "impl copy seed")
            self.assertEqual(event["score"], 1.0)
            self.assertIsNone(event["old_impl"])
            self.assertIsNone(event["new_impl"])
        self.assertEqual(events[0]["at"], events[1]["at"])
        self.assertEqual(events[0]["address"], _IMPL_ADDR)
        self.assertEqual(events[0]["origin"], "impl")
        self.assertEqual(events[1]["address"], _PROXY_ADDR)
        self.assertEqual(events[1]["origin"], "seen")

    def test_command_line_52(self):
        """Example 52: the UPGRADE backfill of example 49 on the first db
        of example 48 after its plain run -- one UPGRADE line on stdout,
        one UPGRADE event as id 3 after the two ALERT events."""
        db = _impl_copy_db()
        code, out, err = _run_main(
            ["--db", db, "backfill",
             "--from", str(_BLOCK), "--to", str(_BLOCK)],
            rpc=_fake_impl_copy())
        self.assertEqual(code, 0)
        store = Store(db)
        try:
            self.assertEqual(len(store.events()), 2)
        finally:
            store.close()

        code, out, err = _run_main(
            ["--db", db, "backfill",
             "--from", str(_BLOCK), "--to", str(_BLOCK),
             "--alert-on", "created"],
            rpc=_fake_upgrade())
        self.assertEqual(code, 0)
        self.assertEqual(
            out,
            "UPGRADE\t%s\t%s\t%s\t%d\n"
            % (_PROXY_ADDR, _IMPL_ADDR, _NEW_IMPL, _BLOCK))
        self.assertEqual(err, "")

        store = Store(db)
        try:
            events = store.events()
        finally:
            store.close()
        self.assertEqual([event["id"] for event in events], [3, 2, 1])
        upgrade = events[0]
        self.assertEqual(set(upgrade.keys()), _EVENT_KEYS)
        self.assertEqual(upgrade["kind"], "UPGRADE")
        self.assertEqual(upgrade["block"], _BLOCK)
        self.assertTrue(_AT_RE.match(upgrade["at"]))
        self.assertEqual(upgrade["address"], _PROXY_ADDR)
        self.assertEqual(upgrade["old_impl"], _IMPL_ADDR)
        self.assertEqual(upgrade["new_impl"], _NEW_IMPL)
        self.assertIsNone(upgrade["seed_address"])
        self.assertIsNone(upgrade["label"])
        self.assertIsNone(upgrade["score"])
        self.assertIsNone(upgrade["origin"])
        self.assertEqual(events[1]["kind"], "ALERT")
        self.assertEqual(events[1]["id"], 2)
        self.assertEqual(events[2]["kind"], "ALERT")
        self.assertEqual(events[2]["id"], 1)

    def test_command_line_53(self):
        """Example 53: recheck and seed add print the ALERT line of the
        copy but write no events."""
        db = _belle_copy_db()
        expected = ("ALERT\t%s\t%s\tBELLE honeypot\t0.8667\tunknown\n"
                    % (_BELLE_COPY_ADDR, _BELLE_ADDR))

        code, out, err = _run_main(
            ["--db", db, "seed", "add", _BELLE_ADDR,
             "--label", "BELLE honeypot"])
        self.assertEqual(code, 0)
        self.assertEqual(out, expected)
        self.assertEqual(err, "")

        code, out, err = _run_main(["--db", db, "recheck"])
        self.assertEqual(code, 0)
        self.assertEqual(out, expected)
        self.assertEqual(err, "")

        store = Store(db)
        try:
            self.assertEqual(store.events(), [])
            self.assertEqual(store.event_counts(),
                             {"kinds": {"ALERT": 0, "UPGRADE": 0},
                              "seeds": []})
        finally:
            store.close()

    def test_command_line_54(self):
        """Example 54: dashboard on a missing db file -- exit 2, one
        stderr line naming the path, the directory still empty."""
        directory = tempfile.mkdtemp(prefix="ethsc-p15-judge-")
        path = os.path.join(directory, "missing.sqlite")
        code, out, err = _run_main(["--db", path, "dashboard", "--port", "0"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(err.count("\n"), 1)
        self.assertIn(path, err)
        self.assertEqual(os.listdir(directory), [])

    def test_command_line_55(self):
        """Example 55: dashboard through a patched make_server -- blocks
        until the stub's Ctrl-C, exit 0, one serving line per run, the
        phase-13 file byte-identical and its directory unchanged."""
        db = legacy_db(13)
        before_hash = _sha256(db)
        before_listing = sorted(os.listdir(os.path.dirname(db)))

        calls = []
        stubs = []

        def fake_make(db_path, host, port, static):
            calls.append((db_path, host, port, static))
            stub = _StubServer()
            stubs.append(stub)
            return stub

        with mock.patch.object(dashboard, "make_server", fake_make):
            code1, out1, err1 = _run_main(["--db", db, "dashboard"])
            code2, out2, err2 = _run_main(
                ["--db", db, "dashboard",
                 "--host", "127.0.0.1", "--port", "9000",
                 "--static", "/tmp/x"])

        self.assertEqual(code1, 0)
        self.assertEqual(code2, 0)
        self.assertEqual(out1, "")
        self.assertEqual(out2, "")
        self.assertEqual(err1, "serving http://127.0.0.1:8080/\n")
        self.assertEqual(err2, "serving http://127.0.0.1:8080/\n")
        self.assertEqual(
            calls,
            [(db, "127.0.0.1", 8080, "dashboard/dist"),
             (db, "127.0.0.1", 9000, "/tmp/x")])
        self.assertEqual(len(stubs), 2)
        for stub in stubs:
            self.assertEqual(stub.closed, 1)
        self.assertEqual(_sha256(db), before_hash)
        self.assertEqual(sorted(os.listdir(os.path.dirname(db))),
                         before_listing)

    def test_command_line_56(self):
        """Example 56: a busy port and a non-integer --port are both
        usage-level failures -- exit 2, one stderr line, no traceback."""
        db = _block_db()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        try:
            code, out, err = _run_main(
                ["--db", db, "dashboard", "--port", str(port)])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertEqual(err.count("\n"), 1)
            self.assertNotIn("Traceback", err)
        finally:
            sock.close()

        code, out, err = _run_main(["--db", db, "dashboard", "--port", "x"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertEqual(err.count("\n"), 1)
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
