"""Minimal JSON-RPC client over an injected transport, with retry, backoff,
credit accounting and secret hygiene.

Only this module may import urllib, http or socket (No Network In Core).
"""

import json
import os
import time
import urllib.error
import urllib.request

from ethsc.config import PRICES


class RpcError(Exception):
    """A failed RPC call.

    .code is the JSON-RPC error code, the HTTP status after retries are
    exhausted (429, 503), or None for a transport or parse failure.
    .message is a human-readable reason. The message never carries the URL
    or the API key.
    """

    def __init__(self, code, message):
        super(RpcError, self).__init__(message)
        self.code = code
        self.message = message

    def __repr__(self):
        return "RpcError(%r, %r)" % (self.code, self.message)


def _default_transport(url, body):
    """POST body to url with urllib; HTTPError becomes (status, body)."""
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


class RpcClient(object):
    """JSON-RPC client. transport(url, body: bytes) -> (status, body).

    429, 5xx and transport OSErrors are retried after sleep(1), sleep(2),
    sleep(4) ... (doubling from 1), at most max_retries retries, i.e. at most
    max_retries + 1 transport calls, then RpcError. A JSON-RPC error object
    raises RpcError(code, message) at once, with no retry. After every
    successful call, on_spend(method, prices[method]) is called once.
    """

    def __init__(self, url, transport=None, sleep=time.sleep, prices=None,
                 on_spend=None, max_retries=3):
        self.url = url
        self.transport = transport if transport is not None else _default_transport
        self.sleep = sleep
        self.prices = dict(PRICES) if prices is None else prices
        self.on_spend = on_spend
        self.max_retries = max_retries

    def call(self, method, params):
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                              "params": params}).encode("utf-8")
        retries = 0
        while True:
            try:
                status, body = self.transport(self.url, payload)
            except OSError:
                # The transport error text carries the URL; it is not carried.
                if retries < self.max_retries:
                    retries += 1
                    self.sleep(2 ** (retries - 1))
                    continue
                raise RpcError(None, "transport failed") from None
            if status == 200:
                try:
                    parsed = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    raise RpcError(None, "response is not valid JSON")
                if not isinstance(parsed, dict):
                    raise RpcError(None, "response is not a JSON object")
                if "error" in parsed:
                    err = parsed["error"]
                    raise RpcError(err.get("code"), err.get("message", "error"))
                if "result" not in parsed:
                    raise RpcError(None, "response has no result")
                result = parsed["result"]
                if self.on_spend is not None:
                    self.on_spend(method, self.prices.get(method, 0))
                return result
            if status == 429 or 500 <= status < 600:
                if retries < self.max_retries:
                    retries += 1
                    self.sleep(2 ** (retries - 1))
                    continue
                raise RpcError(status, "HTTP %d after %d retries" % (status, retries))
            raise RpcError(status, "unexpected HTTP status %d" % status)


def infura_url(env_path=".env"):
    """https://mainnet.infura.io/v3/<key> from the environment or a .env file.

    The environment wins over the file. In the file, lines starting with #
    are skipped, spaces around values and one pair of quotes are stripped.
    Without the key anywhere, RpcError(None, "INFURA_API_KEY is not set").
    """
    key = os.environ.get("INFURA_API_KEY")
    if key is None or key == "":
        try:
            with open(env_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("INFURA_API_KEY="):
                        key = line[len("INFURA_API_KEY="):].strip()
                        if len(key) >= 2 and key[0] == key[-1] and key[0] in ('"', "'"):
                            key = key[1:-1]
                        break
        except OSError:
            key = None
    if not key:
        raise RpcError(None, "INFURA_API_KEY is not set")
    return "https://mainnet.infura.io/v3/" + key
