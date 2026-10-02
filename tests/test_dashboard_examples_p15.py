"""Judge tests for the phase-15 dashboard group: one test per Contour example.

Answer Request examples 1-12 and Serve Dashboard examples 1-2 of
contour.yaml, group dashboard. Every expected value is taken from the
Contour. Offline: the two serving tests bind ('127.0.0.1', 0) and talk
over a raw socket.socket (never getaddrinfo, never urllib or
http.client); nothing else touches a socket. Stubs and builders come
from tests.helpers; every file a test writes lives in a fresh
tempfile.mkdtemp() directory.
"""

import hashlib
import io
import itertools
import json
import mimetypes
import os
import socket
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from ethsc.dashboard import ThreadingHTTPServer, make_server, respond
from ethsc.store import Store

from tests.helpers import block_codes, legacy_db, load_hex

_FMT = "%Y-%m-%dT%H:%M:%SZ"
_BLOCK = 26077729
_JSON_TYPE = "application/json; charset=utf-8"
_HTML_TYPE = "text/html; charset=utf-8"

_EVENT_KEYS = {"id", "kind", "block", "at", "address", "seed_address",
               "label", "score", "origin", "old_impl", "new_impl"}


def _alert(block, seed, label):
    """The ALERT event of Record Events example 1, at the given block."""
    return {"kind": "ALERT", "block": block, "at": "2026-10-02T08:00:00Z",
            "address": "0x1807090DD15A6F58E00FD769E32EBF20EE610385",
            "seed_address": seed, "label": label,
            "score": 0.8666666666666667, "origin": "seen"}


def _upgrade(block):
    """The UPGRADE event of Record Events example 1, at the given block."""
    return {"kind": "UPGRADE", "block": block, "at": "2026-10-02T08:00:00Z",
            "address": "0x0c0105334a50db16b51b2911c9956539753a2cf8",
            "old_impl": "0x72b971717e088b59f26d4236be222adb6acd393b",
            "new_impl": "0xe440cc08a71694c8229323803f59024e3144630e"}


def _fresh_path():
    return os.path.join(tempfile.mkdtemp(prefix="ethsc-judge-"),
                        "ethsc.sqlite")


def _fresh_db():
    """A fresh db file: Store opened and closed, nothing written."""
    path = _fresh_path()
    Store(path).close()
    return path


def _block_db(with_progress=False):
    """A db filled like tests.helpers.block_store(), at a path we own."""
    path = _fresh_path()
    store = Store(path)
    try:
        for address, text in sorted(block_codes().items()):
            if text == "0x":
                store.put_address(address, None, _BLOCK)
            else:
                code_id = store.put_code(bytes.fromhex(text[2:]))
                store.put_address(address, code_id, _BLOCK)
        if with_progress:
            store.set_progress(_BLOCK)
    finally:
        store.close()
    return path


def _json_of(body):
    return json.loads(body.decode("utf-8"))


def _raw_request(port, request):
    """One raw-socket HTTP/1.0 request to 127.0.0.1:port; the full reply."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect(("127.0.0.1", port))
        sock.sendall(request)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        sock.close()
    return b"".join(chunks)


class TestDashboardExamplesP15(unittest.TestCase):
    """One test per Contour example, Answer Request 1-12 then Serve 1-2."""

    def test_answer_request_1(self):
        path = _block_db(with_progress=True)
        store = Store(path)
        try:
            p = store.progress_at()
        finally:
            store.close()
        now = (datetime.strptime(p, _FMT).replace(tzinfo=timezone.utc)
               + timedelta(seconds=7))
        expected = json.dumps(
            {"now": now.strftime(_FMT), "progress": 26077729,
             "progress_at": p, "seconds_since_progress": 7},
            sort_keys=True).encode("utf-8")
        for target in ("/api/health", "/api/health?x=1"):
            status, content_type, body = respond(path, target, now=now)
            self.assertEqual(status, 200)
            self.assertEqual(content_type, _JSON_TYPE)
            self.assertEqual(body, expected)

    def test_answer_request_2(self):
        path = _fresh_db()
        now = datetime(2026, 10, 2, 8, 0, 0, tzinfo=timezone.utc)
        status, ctype, body = respond(path, "/api/health", now=now)
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        self.assertEqual(_json_of(body),
                         {"now": "2026-10-02T08:00:00Z", "progress": None,
                          "progress_at": None,
                          "seconds_since_progress": None})
        status, ctype, body = respond(path, "/api/events", now=now)
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        self.assertEqual(_json_of(body), {"events": [], "last_id": 0})
        status, ctype, body = respond(path, "/api/summary", now=now)
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        zero = {"created": 0, "seen": 0, "impl": 0, "fetched": 0,
                "unknown": 0}
        self.assertEqual(_json_of(body),
                         {"addresses": 0, "codes": 0, "seeds": 0,
                          "origins": dict(zero),
                          "implementations_resolved": 0,
                          "alerts_by_seed": [],
                          "recent": {"blocks": 300, "by_origin": dict(zero)}})

    def test_answer_request_3(self):
        path = _block_db()
        store = Store(path)
        try:
            store.add_events([_alert(i,
                                     "0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                                     "BELLE honeypot")
                              for i in range(1, 6)])
        finally:
            store.close()
        expected = [([5, 4, 3, 2, 1], 5), ([5, 4], 5), ([], 5),
                    ([5, 4, 3, 2, 1], 5)]
        targets = ("/api/events", "/api/events?after=2&limit=2",
                   "/api/events?after=5", "/api/events?limit=500")
        for target, (ids, last_id) in zip(targets, expected):
            status, ctype, body = respond(path, target)
            self.assertEqual((status, ctype), (200, _JSON_TYPE), target)
            payload = _json_of(body)
            self.assertEqual([event["id"] for event in payload["events"]],
                             ids, target)
            self.assertEqual(payload["last_id"], last_id, target)
            for event in payload["events"]:
                self.assertEqual(set(event), _EVENT_KEYS)

    def test_answer_request_4(self):
        path = _block_db()
        bad = ["/api/events?limit=0", "/api/events?limit=501",
               "/api/events?limit=x", "/api/events?after=-1",
               "/api/events?after=1.5", "/api/clusters",
               "/api/clusters?level=L9", "/api/clusters?level=L0&n=0",
               "/api/clusters?level=L0&n=101"]
        for target in bad:
            status, ctype, body = respond(path, target)
            self.assertEqual(status, 400, target)
            self.assertEqual(ctype, _JSON_TYPE)
            payload = _json_of(body)
            self.assertEqual(list(payload), ["error"], target)
            self.assertIsInstance(payload["error"], str)
            self.assertTrue(payload["error"])
            self.assertNotIn("Traceback", payload["error"])

    def test_answer_request_5(self):
        path = _block_db()
        store = Store(path)
        try:
            store.add_events([
                _alert(1, "0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                       "BELLE honeypot"),
                _alert(2, "0x34c6211621f2763c60eb007dc2ae91090a2d22f6",
                       "BELLE honeypot"),
                _alert(3, "0x1111111111111111111111111111111111111111",
                       "impl copy seed"),
                _upgrade(4),
            ])
            store.set_progress(_BLOCK)
        finally:
            store.close()
        status, ctype, body = respond(path, "/api/summary")
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        self.assertEqual(_json_of(body), {
            "addresses": 206, "codes": 130, "seeds": 0,
            "origins": {"created": 0, "fetched": 0, "impl": 0, "seen": 0,
                        "unknown": 206},
            "implementations_resolved": 0,
            "alerts_by_seed": [
                {"count": 2, "label": "BELLE honeypot",
                 "seed_address": "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"},
                {"count": 1, "label": "impl copy seed",
                 "seed_address": "0x1111111111111111111111111111111111111111"},
            ],
            "recent": {"blocks": 300,
                       "by_origin": {"created": 0, "fetched": 0, "impl": 0,
                                     "seen": 0, "unknown": 206}},
        })

    def test_answer_request_6(self):
        path = _fresh_path()
        store = Store(path)
        try:
            store.put_address("0x00000000000000000000000000000000000000a1",
                              None, 100, "created")
            store.put_address("0x00000000000000000000000000000000000000a2",
                              None, 26077430, "seen")
            store.put_address("0x00000000000000000000000000000000000000a3",
                              None, 26077429, "seen")
            store.put_address("0x00000000000000000000000000000000000000a4",
                              None, 26077729)
            store.set_progress(26077729)
        finally:
            store.close()
        status, ctype, body = respond(path, "/api/summary")
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        payload = _json_of(body)
        self.assertEqual(payload["addresses"], 4)
        self.assertEqual(payload["codes"], 0)
        self.assertEqual(payload["origins"],
                         {"created": 1, "fetched": 0, "impl": 0, "seen": 2,
                          "unknown": 1})
        self.assertEqual(payload["recent"],
                         {"blocks": 300,
                          "by_origin": {"created": 0, "fetched": 0,
                                        "impl": 0, "seen": 1, "unknown": 1}})

    def test_answer_request_7(self):
        path = _block_db()
        status, ctype, body = respond(path, "/api/clusters?level=L0",
                                      cache={})
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        payload = _json_of(body)
        self.assertEqual(payload["level"], "L0")
        self.assertEqual(payload["n"], 20)
        self.assertEqual(len(payload["clusters"]), 7)
        first = payload["clusters"][0]
        self.assertEqual(first["key"],
                         "8b5db55fa9ab3b9527508d4abe0b39eb588bf310270c8e04b3f38214e8ba63b4")
        self.assertEqual(len(first["members"]), 4)
        status, ctype, body = respond(path, "/api/clusters?level=L1&n=1",
                                      cache={})
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        payload = _json_of(body)
        self.assertEqual(payload["level"], "L1")
        self.assertEqual(payload["n"], 1)
        self.assertEqual(len(payload["clusters"]), 1)
        self.assertEqual(payload["clusters"][0]["key"],
                         "29ec9639b8fa8f759c993d77fe43ccfb471dd596d23b3b098965ebb64e56235f")
        self.assertEqual(len(payload["clusters"][0]["members"]), 8)
        status, ctype, body = respond(path, "/api/clusters?level=impl",
                                      cache={})
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        payload = _json_of(body)
        self.assertEqual((payload["level"], payload["n"], payload["clusters"]),
                         ("impl", 20, []))

    def test_answer_request_8(self):
        path = _block_db()
        cache = {}
        ticks = itertools.chain([1000.0, 1030.0, 1061.0],
                                itertools.repeat(1062.0))
        belle_id = ("8571d00b598627ac40e1ae7bc4d0cb3fd5a77a0d663763fdfc1cd"
                    "9127b63cb4d")
        members = ["0x00000000000000000000000000000000000000b1",
                   "0x00000000000000000000000000000000000000b2"]

        def l0_rows():
            status, _, body = respond(path, "/api/clusters?level=L0",
                                      cache=cache)
            self.assertEqual(status, 200)
            return _json_of(body)["clusters"]

        with mock.patch("ethsc.dashboard.time") as fake_time:
            fake_time.monotonic.side_effect = lambda: next(ticks)
            self.assertEqual(len(l0_rows()), 7)
            store = Store(path)
            try:
                code_id = store.put_code(load_hex("code_belle.hex"))
                for address in members:
                    store.put_address(address, code_id, 26077729)
            finally:
                store.close()
            self.assertEqual(code_id, belle_id)
            self.assertEqual(len(l0_rows()), 7)  # T + 30: the cached list
            rows = l0_rows()  # T + 61: rebuilt
            self.assertEqual(len(rows), 8)
        row = [r for r in rows if r["key"] == belle_id]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["members"], members)
        status, _, body = respond(path, "/api/clusters?level=L0", cache={})
        self.assertEqual(status, 200)
        self.assertEqual(len(_json_of(body)["clusters"]), 8)

    def test_answer_request_9(self):
        path = legacy_db(13)
        directory = os.path.dirname(path)

        def snapshot():
            with open(path, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            return digest, sorted(os.listdir(directory))

        before = snapshot()
        status, ctype, body = respond(path, "/api/health")
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        payload = _json_of(body)
        self.assertEqual(payload["progress"], 26077729)
        self.assertIsNone(payload["progress_at"])
        self.assertIsNone(payload["seconds_since_progress"])
        status, ctype, body = respond(path, "/api/events")
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        self.assertEqual(_json_of(body), {"events": [], "last_id": 0})
        status, ctype, body = respond(path, "/api/summary")
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        payload = _json_of(body)
        self.assertEqual(payload["addresses"], 206)
        self.assertEqual(payload["codes"], 130)
        self.assertEqual(payload["implementations_resolved"], 0)
        self.assertEqual(payload["alerts_by_seed"], [])
        self.assertEqual(payload["origins"]["unknown"], 206)
        status, ctype, body = respond(path, "/api/clusters?level=impl",
                                      cache={})
        self.assertEqual((status, ctype), (200, _JSON_TYPE))
        self.assertEqual(_json_of(body)["clusters"], [])
        self.assertEqual(snapshot(), before)

    def test_answer_request_10(self):
        path = _block_db()
        missing = os.path.join(tempfile.mkdtemp(prefix="ethsc-judge-"),
                               "nope")
        for static_dir in (missing, None):
            status, ctype, body = respond(path, "/", static_dir=static_dir)
            self.assertEqual((status, ctype), (200, _HTML_TYPE))
            text = body.decode("utf-8")
            for endpoint in ("/api/health", "/api/events", "/api/summary",
                             "/api/clusters"):
                self.assertIn(endpoint, text)
            status, ctype, body = respond(path, "/assets/app.js",
                                          static_dir=static_dir)
            self.assertEqual(status, 404)
            self.assertEqual(ctype, _JSON_TYPE)
            self.assertIn("error", _json_of(body))

    def test_answer_request_11(self):
        root = tempfile.mkdtemp(prefix="ethsc-judge-")
        with open(os.path.join(root, "secret.txt"), "w",
                  encoding="utf-8") as handle:
            handle.write("top secret")
        dist = os.path.join(root, "dist")
        os.makedirs(os.path.join(dist, "assets"))
        with open(os.path.join(dist, "index.html"), "wb") as handle:
            handle.write(b"<html>ok</html>")
        with open(os.path.join(dist, "assets", "app.js"), "wb") as handle:
            handle.write(b"console.log(1)")
        path = _block_db()
        status, ctype, body = respond(path, "/", static_dir=dist)
        self.assertEqual((status, ctype), (200, _HTML_TYPE))
        self.assertEqual(body, b"<html>ok</html>")
        status, ctype, body = respond(path, "/assets/app.js",
                                      static_dir=dist)
        self.assertEqual(status, 200)
        self.assertEqual(ctype, mimetypes.guess_type("app.js")[0])
        self.assertEqual(body, b"console.log(1)")
        for target in ("/assets/missing.js", "/assets/../../secret.txt",
                       "/assets/%2e%2e/%2e%2e/secret.txt",
                       "/assets/..%2f..%2fsecret.txt", "/../secret.txt"):
            status, ctype, body = respond(path, target, static_dir=dist)
            self.assertEqual(status, 404, target)
            self.assertNotIn(b"top secret", body)

    def test_answer_request_12(self):
        path = _block_db()
        for target in ("/api/nope", "/api/health/", "/favicon.ico"):
            status, ctype, body = respond(path, target)
            self.assertEqual(status, 404, target)
            self.assertEqual(ctype, _JSON_TYPE)
            self.assertEqual(_json_of(body), {"error": "not found"})
        missing_dir = tempfile.mkdtemp(prefix="ethsc-judge-")
        missing = os.path.join(missing_dir, "ethsc.sqlite")
        status, ctype, body = respond(missing, "/api/health")
        self.assertEqual(status, 500)
        self.assertEqual(ctype, _JSON_TYPE)
        payload = _json_of(body)
        self.assertEqual(list(payload), ["error"])
        self.assertNotIn("Traceback", payload["error"])
        self.assertEqual(os.listdir(missing_dir), [])

    def test_serve_dashboard_1(self):
        path = _block_db(with_progress=True)
        server = make_server(path, "127.0.0.1", 0, None)
        self.assertIsInstance(server, ThreadingHTTPServer)
        self.assertTrue(server.daemon_threads)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            got = self._serve(server)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            captured = sys.stderr.getvalue()
            sys.stderr = old_stderr
        get_reply, post_reply = got
        head, _, payload = get_reply.partition(b"\r\n\r\n")
        self.assertTrue(head.startswith(b"HTTP/1.0 200"))
        self.assertIn(b"Content-Type: application/json; charset=utf-8",
                      head)
        self.assertEqual(json.loads(payload.decode("utf-8"))["progress"],
                         26077729)
        phead, _, ppayload = post_reply.partition(b"\r\n\r\n")
        self.assertTrue(phead.startswith(b"HTTP/1.0 405"))
        self.assertIn("error", json.loads(ppayload.decode("utf-8")))
        self.assertEqual(captured, "")

    def _serve(self, server):
        port = server.server_address[1]
        get_reply = _raw_request(port, b"GET /api/health HTTP/1.0\r\n\r\n")
        post_reply = _raw_request(
            port, b"POST /api/health HTTP/1.0\r\nContent-Length: 0\r\n\r\n")
        return get_reply, post_reply

    def test_serve_dashboard_2(self):
        path = _fresh_db()
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen(1)
            port = blocker.getsockname()[1]
            with self.assertRaises(OSError):
                make_server(path, "127.0.0.1", port, None)
        finally:
            blocker.close()


if __name__ == "__main__":
    unittest.main()
