"""Smoke tests for the phase-15 dashboard backend (ethsc/dashboard.py).

Offline: respond is called directly, and one test starts make_server on
127.0.0.1 port 0 and talks to it over a raw socket (never urllib or
http.client). Fixtures come from tests/helpers.py; every file a test
writes goes into a tempfile.mkdtemp() directory.
"""

import datetime
import json
import os
import socket
import tempfile
import threading

from ethsc.dashboard import make_server, respond
from ethsc.store import Store
from tests.helpers import block_codes

_BLOCK = 26077729


def _filled_db(with_progress=False):
    """A fresh db filled from block_codes(); returns its path."""
    directory = tempfile.mkdtemp(prefix="ethsc-dash-")
    path = os.path.join(directory, "ethsc.sqlite")
    store = Store(path)
    for address, text in sorted(block_codes().items()):
        if text == "0x":
            store.put_address(address, None, _BLOCK)
        else:
            code_id = store.put_code(bytes.fromhex(text[2:]))
            store.put_address(address, code_id, _BLOCK)
    if with_progress:
        store.set_progress(_BLOCK)
    store.close()
    return path


def _read_json(body):
    return json.loads(body.decode("utf-8"))


def test_health_happy_path():
    path = _filled_db(with_progress=True)
    reader = Store(path, readonly=True)
    stamp = reader.progress_at()
    reader.close()
    now = datetime.datetime.strptime(
        stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=7)
    status, ctype, body = respond(path, "/api/health", now=now)
    assert status == 200
    assert ctype == "application/json; charset=utf-8"
    obj = _read_json(body)
    assert obj["progress"] == _BLOCK
    assert obj["progress_at"] == stamp
    assert obj["seconds_since_progress"] == 7
    # an unknown query parameter is ignored
    status2, _, body2 = respond(path, "/api/health?x=1", now=now)
    assert status2 == 200 and body2 == body


def test_events_and_summary_shapes():
    path = _filled_db()
    status, _, body = respond(path, "/api/events")
    assert status == 200
    obj = _read_json(body)
    assert obj["events"] == []
    assert obj["last_id"] == 0
    status, _, body = respond(path, "/api/summary")
    assert status == 200
    obj = _read_json(body)
    assert set(obj["origins"].keys()) == {
        "created", "seen", "impl", "fetched", "unknown"}
    assert obj["recent"]["blocks"] == 300
    assert obj["alerts_by_seed"] == []


def test_errors_are_json():
    path = _filled_db()
    for target in ("/api/nope", "/api/health/", "/favicon.ico",
                   "/api/events?limit=0", "/api/events?after=-1",
                   "/api/clusters", "/api/clusters?level=L9"):
        status, ctype, body = respond(path, target, cache={})
        assert status in (400, 404), target
        assert ctype == "application/json; charset=utf-8", target
        assert set(_read_json(body).keys()) == {"error"}, target
    missing = os.path.join(
        tempfile.mkdtemp(prefix="ethsc-missing-"), "nope.sqlite")
    status, _, body = respond(missing, "/api/health")
    assert status == 500
    assert set(_read_json(body).keys()) == {"error"}
    assert b"Traceback" not in body


def test_clusters_and_placeholder():
    path = _filled_db()
    status, _, body = respond(path, "/api/clusters?level=L0", cache={})
    assert status == 200
    obj = _read_json(body)
    assert obj["level"] == "L0"
    assert obj["n"] == 20
    assert len(obj["clusters"]) == 7
    status, ctype, body = respond(path, "/", static_dir=None)
    assert status == 200
    assert ctype == "text/html; charset=utf-8"
    text = body.decode("utf-8")
    for endpoint in ("/api/health", "/api/events", "/api/summary",
                     "/api/clusters"):
        assert endpoint in text
    status, _, body = respond(path, "/assets/app.js", static_dir=None)
    assert status == 404


def test_make_server_raw_socket():
    path = _filled_db(with_progress=True)
    server = make_server(path, "127.0.0.1", 0)
    assert server.daemon_threads is True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(("127.0.0.1", port))
        sock.sendall(b"GET /api/health HTTP/1.0\r\n\r\n")
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
        sock.close()
        head, _, body = data.partition(b"\r\n\r\n")
        assert head.startswith(b"HTTP/1.0 200")
        assert b"application/json; charset=utf-8" in head
        assert _read_json(body)["progress"] == _BLOCK
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
