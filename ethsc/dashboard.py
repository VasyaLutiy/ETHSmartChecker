"""The live dashboard backend (phase 15): JSON over the store on localhost.

ethsc/dashboard.py answers GET requests about the database a running
listener fills, and serves the static frontend built in dashboard/dist.
Read-only: every /api/ request opens Store(db_path, readonly=True) and
closes it before the answer returns (try/finally), so the listener
never waits on the dashboard.

The whole HTTP behaviour for one GET lives in respond(db_path, target,
...), without a socket, so every endpoint is testable offline;
make_server wraps it in a http.server.ThreadingHTTPServer. The only
network-family import is http.server (Guardrail No Network In Core):
the query string is split by hand on '&' and '=' and the path is
percent-decoded by a small hand-written function -- urllib.parse is not
importable outside rpc. The store is read only through its public
methods. The clusters are cached per db_path for 60 s, keyed on
time.monotonic() read through "import time", so a test can patch the
clock. Any exception inside respond becomes 500 {"error": one line} --
never a traceback in a body.
"""

import json
import mimetypes
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ethsc.cluster import build_clusters
from ethsc.store import Store

_JSON_TYPE = "application/json; charset=utf-8"
_HTML_TYPE = "text/html; charset=utf-8"

_LEVELS = ("L0", "L1", "proxy", "eip7702", "impl")
_ORIGINS = ("created", "seen", "impl", "fetched", "unknown")

_CACHE_TTL = 60.0  # seconds a clusters build stays fresh, per db_path

# The module's own cache; respond(cache=...) may pass another dict.
_CACHE = {}

_PLACEHOLDER = """<!doctype html>
<html><head><title>ethsc dashboard</title></head>
<body>
<h1>ethsc dashboard</h1>
<p>The static frontend is not built. The JSON endpoints are:</p>
<ul>
<li><a href="/api/health">/api/health</a> -- listener heartbeat</li>
<li><a href="/api/events">/api/events</a> -- the live ALERT/UPGRADE stream</li>
<li><a href="/api/summary">/api/summary</a> -- base counters</li>
<li><a href="/api/clusters">/api/clusters</a> -- L0/L1/proxy/eip7702/impl clusters</li>
</ul>
</body></html>
"""


class _BadRequest(Exception):
    """A bad query value: answered 400 {"error": ...} by respond."""


def _json_body(obj):
    return json.dumps(obj, sort_keys=True).encode("utf-8")


def _json(status, obj):
    return status, _JSON_TYPE, _json_body(obj)


def _error(status, message):
    return _json(status, {"error": message})


def _percent_decode(text):
    """Decode %XX escapes by hand; '+' stays a literal plus (a path).

    A malformed escape (a bare '%' or a short tail) is kept as text.
    """
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "%" and i + 3 <= n:
            try:
                out.append(chr(int(text[i + 1:i + 3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        out.append(text[i])
        i += 1
    return "".join(out)


def _parse_query(query):
    """The query string -> {key: value}, split by hand on '&' and '='."""
    result = {}
    if not query:
        return result
    for part in query.split("&"):
        if not part:
            continue
        key, sep, value = part.partition("=")
        if not sep:
            value = ""
        result[key] = value
    return result


def _decimal(value, name, low, high):
    """A decimal integer in [low, high], or _BadRequest when it is bad."""
    if not value or not all(ch in "0123456789" for ch in value):
        raise _BadRequest("bad %s: %r" % (name, value))
    number = int(value)
    if number < low or number > high:
        raise _BadRequest("bad %s: %r" % (name, value))
    return number


def _timestamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc)


def _api_health(db_path, now):
    store = Store(db_path, readonly=True)
    try:
        progress = store.get_progress()
        progress_at = store.progress_at()
    finally:
        store.close()
    seconds = None
    if progress_at is not None:
        seconds = int((now - _parse_timestamp(progress_at)).total_seconds())
    return _json(200, {
        "progress": progress,
        "progress_at": progress_at,
        "seconds_since_progress": seconds,
        "now": _timestamp(now),
    })


def _api_events(db_path, params):
    after = _decimal(params.get("after", "0"), "after", 0,
                     10 ** 18)
    limit = _decimal(params.get("limit", "100"), "limit", 1, 500)
    store = Store(db_path, readonly=True)
    try:
        rows = store.events(after, limit)
    finally:
        store.close()
    last_id = after
    for row in rows:
        if row["id"] > last_id:
            last_id = row["id"]
    return _json(200, {"events": rows, "last_id": last_id})


def _origin_view(counts):
    view = dict.fromkeys(_ORIGINS, 0)
    for name, count in counts.items():
        if name in view:
            view[name] = count
    return view


def _api_summary(db_path, now):
    del now  # the summary needs no clock; the parameter keeps one shape
    store = Store(db_path, readonly=True)
    try:
        counts = store.counts()
        seeds = store.seeds()
        origins = _origin_view(store.origin_counts())
        implementations = store.implementations()
        resolved = 0
        for info in implementations.values():
            if info["implementation"] is not None:
                resolved += 1
        alerts_by_seed = store.event_counts()["seeds"]
        progress = store.get_progress()
        if progress is None:
            recent = dict.fromkeys(_ORIGINS, 0)
        else:
            recent = _origin_view(
                store.origin_counts(since_block=progress - 299))
    finally:
        store.close()
    return _json(200, {
        "addresses": counts["addresses"],
        "codes": counts["codes"],
        "seeds": len(seeds),
        "origins": origins,
        "implementations_resolved": resolved,
        "alerts_by_seed": alerts_by_seed,
        "recent": {"blocks": 300, "by_origin": recent},
    })


def _clusters_from_cache(db_path, cache):
    """The full build_clusters list for db_path, built at most once/60 s.

    cache maps db_path to (time.monotonic() at the build, the list);
    an entry younger than _CACHE_TTL is reused. The clock is read
    through the time module so a test can patch time.monotonic.
    """
    entry = cache.get(db_path)
    now = time.monotonic()
    if entry is not None and now - entry[0] < _CACHE_TTL:
        return entry[1]
    store = Store(db_path, readonly=True)
    try:
        clusters = build_clusters(store)
    finally:
        store.close()
    cache[db_path] = (now, clusters)
    return clusters


def _api_clusters(db_path, params, cache):
    level = params.get("level")
    if level not in _LEVELS:
        raise _BadRequest("bad level: %r" % (level,))
    n = _decimal(params.get("n", "20"), "n", 1, 100)
    clusters = _clusters_from_cache(db_path, cache)
    rows = [c for c in clusters if c["level"] == level]
    return _json(200, {"level": level, "n": n, "clusters": rows[:n]})


def _read_file(path):
    with open(path, "rb") as handle:
        return handle.read()


def _serve_static(static_dir, path):
    """GET / -> index.html; GET /assets/<rel> -> that file; else 404.

    The path is resolved with os.path.realpath and refused when it
    leaves the static directory (.., an encoded .., a symlink out).
    """
    root = os.path.realpath(static_dir)
    if path == "/":
        full = os.path.join(root, "index.html")
        if not os.path.isfile(full):
            return _error(404, "not found")
        return 200, _HTML_TYPE, _read_file(full)
    if path.startswith("/assets/") and len(path) > len("/assets/"):
        rel = path[len("/assets/"):]
        base = os.path.join(root, "assets")
        full = os.path.realpath(os.path.join(base, rel))
        inside = full == base or full.startswith(base + os.sep)
        if not inside or not os.path.isfile(full):
            return _error(404, "not found")
        kind = mimetypes.guess_type(full)[0] or "application/octet-stream"
        return 200, kind, _read_file(full)
    return _error(404, "not found")


def respond(db_path, target, static_dir=None, now=None, cache=None):
    """The whole HTTP behaviour for one GET, without a socket.

    target is the request target as the server receives it (path plus
    an optional "?query"). Returns (status, content_type, body bytes).
    JSON bodies are json.dumps(obj, sort_keys=True) in UTF-8. now is an
    aware UTC datetime (None: datetime.now(timezone.utc)); cache is the
    dict holding the clusters cache (None: the module's own dict). Any
    exception becomes 500 {"error": one line} -- never a traceback.
    """
    if cache is None:
        cache = _CACHE
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        path, _, query = target.partition("?")
        path = _percent_decode(path)
        params = _parse_query(query)

        if path == "/api/health":
            return _api_health(db_path, now)
        if path == "/api/events":
            return _api_events(db_path, params)
        if path == "/api/summary":
            return _api_summary(db_path, now)
        if path == "/api/clusters":
            return _api_clusters(db_path, params, cache)
        if path.startswith("/api/") or path == "/favicon.ico":
            return _error(404, "not found")

        if static_dir is None or not os.path.isdir(static_dir):
            if path == "/":
                return 200, _HTML_TYPE, _PLACEHOLDER.encode("utf-8")
            return _error(404, "not found")
        return _serve_static(static_dir, path)
    except _BadRequest as bad:
        return _error(400, str(bad))
    except Exception as error:  # noqa: BLE001 - one line, never a traceback
        text = str(error).splitlines()[0] if str(error) else ""
        if not text:
            text = error.__class__.__name__
        return _error(500, text)


class _Handler(BaseHTTPRequestHandler):
    """Calls respond for GET; 405 JSON for every other method."""

    db_path = None
    static_dir = None
    cache = None

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler naming
        status, content_type, body = respond(
            self.db_path, self.path, self.static_dir, cache=self.cache)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        self._reject()

    def do_PUT(self):  # noqa: N802
        self._reject()

    def do_DELETE(self):  # noqa: N802
        self._reject()

    def do_HEAD(self):  # noqa: N802
        self._reject()

    def do_PATCH(self):  # noqa: N802
        self._reject()

    def _reject(self):
        body = _json_body({"error": "method not allowed"})
        self.send_response(405)
        self.send_header("Content-Type", _JSON_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        """Silenced: stderr stays clean under a 1-second poller."""


def make_server(db_path, host="127.0.0.1", port=8080, static_dir=None):
    """A bound ThreadingHTTPServer (daemon_threads True); not started.

    The caller calls serve_forever. A port that cannot be bound raises
    OSError (the CLI turns it into exit 2).
    """
    handler = type("BoundHandler", (_Handler,), {
        "db_path": db_path,
        "static_dir": static_dir,
        "cache": _CACHE,
    })
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
