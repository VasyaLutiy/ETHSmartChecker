"""Tests for ethsc/rpc.py: RpcClient and infura_url, fully offline.

Every test names the contour.yaml example or the TASK_PHASE4 rule it checks.
"""

import json
import os
import tempfile
import traceback
import unittest
from unittest import mock

from ethsc.config import PRICES
from ethsc.rpc import RpcClient, RpcError, infura_url

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

TESTKEY = "TESTKEY-0000"


def fixture_text(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return handle.read()


def weth9_hex():
    return fixture_text("code_weth9.hex")


def rpc_429():
    return json.loads(fixture_text("rpc_429.json"))


class RecordingTransport(object):
    """Fake transport: serves queued answers, records (url, body)."""

    def __init__(self, answers, url="https://mainnet.infura.io/v3/" + TESTKEY):
        self.answers = list(answers)
        self.calls = []
        self.url = url

    def __call__(self, url, body):
        self.calls.append((url, body))
        return self.answers.pop(0)


class RepeatingTransport(object):
    """Fake transport: always answers the same way; records (url, body)."""

    def __init__(self, answer, url="https://mainnet.infura.io/v3/" + TESTKEY):
        self.answer = answer
        self.calls = []
        self.url = url

    def __call__(self, url, body):
        self.calls.append((url, body))
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


def body_response(result):
    return (200, json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode("utf-8"))


def error_response(code, message):
    return (200, json.dumps({"jsonrpc": "2.0", "id": 1,
                             "error": {"code": code, "message": message}}).encode("utf-8"))


class Example1RetryThenSuccess(unittest.TestCase):
    """Example 1: 429 then 200 -> the result, 2 calls, sleep once with 1."""

    maxDiff = None

    def test_retry_then_success(self):
        msg = "429 must be retried once with sleep(1), then the result returned"
        limited = rpc_429()
        transport = RecordingTransport([
            (limited["status"], limited["body"].encode("utf-8")),
            body_response(weth9_hex()),
        ])
        sleeps = []
        client = RpcClient(transport.url, transport=transport,
                           sleep=sleeps.append, prices=dict(PRICES))
        result = client.call("eth_getCode",
                             ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "latest"])
        self.assertEqual(result, weth9_hex(), msg=msg)
        self.assertEqual(len(transport.calls), 2, msg=msg)
        self.assertEqual(sleeps, [1], msg=msg)
        url, body = transport.calls[0]
        self.assertEqual(url, transport.url, msg="the transport gets the client url")
        sent = json.loads(body.decode("utf-8"))
        self.assertEqual(sent["jsonrpc"], "2.0", msg="request carries jsonrpc 2.0")
        self.assertEqual(sent["method"], "eth_getCode", msg="request carries the method")
        self.assertEqual(sent["params"],
                         ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "latest"],
                         msg="request carries the params")
        self.assertIsInstance(sent["id"], int, msg="request id is an int")


class Example2ExhaustedRetries(unittest.TestCase):
    """Example 2: always 429 -> RpcError after 4 calls, sleeps [1, 2, 4]."""

    def test_exhausted_retries(self):
        msg = "always 429 must raise RpcError(429) after max_retries + 1 calls"
        limited = rpc_429()
        answer = (limited["status"], limited["body"].encode("utf-8"))
        transport = RepeatingTransport(answer)
        sleeps = []
        client = RpcClient(transport.url, transport=transport,
                           sleep=sleeps.append, prices=dict(PRICES), max_retries=3)
        with self.assertRaises(RpcError, msg=msg) as caught:
            client.call("eth_getCode", ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                        "latest"])
        self.assertEqual(len(transport.calls), 4, msg=msg)
        self.assertEqual(sleeps, [1, 2, 4], msg=msg)
        self.assertEqual(caught.exception.code, 429, msg=msg)

    def test_503_is_retried_like_429(self):
        msg = "5xx must be retried like 429, then RpcError(status)"
        transport = RepeatingTransport((503, b"Service Unavailable"))
        sleeps = []
        client = RpcClient(transport.url, transport=transport, sleep=sleeps.append,
                           max_retries=3)
        with self.assertRaises(RpcError, msg=msg) as caught:
            client.call("eth_getCode", ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                        "latest"])
        self.assertEqual(len(transport.calls), 4, msg=msg)
        self.assertEqual(sleeps, [1, 2, 4], msg=msg)
        self.assertEqual(caught.exception.code, 503, msg=msg)

    def test_max_retries_zero(self):
        msg = "max_retries=0 must make exactly one transport call, no sleep"
        limited = rpc_429()
        answer = (limited["status"], limited["body"].encode("utf-8"))
        transport = RepeatingTransport(answer)
        sleeps = []
        client = RpcClient(transport.url, transport=transport, sleep=sleeps.append,
                           max_retries=0)
        with self.assertRaises(RpcError, msg=msg):
            client.call("eth_getCode", ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                        "latest"])
        self.assertEqual(len(transport.calls), 1, msg=msg)
        self.assertEqual(sleeps, [], msg=msg)

    def test_max_retries_one(self):
        msg = "max_retries=1 must make two transport calls with sleep(1)"
        limited = rpc_429()
        answer = (limited["status"], limited["body"].encode("utf-8"))
        transport = RepeatingTransport(answer)
        sleeps = []
        client = RpcClient(transport.url, transport=transport, sleep=sleeps.append,
                           max_retries=1)
        with self.assertRaises(RpcError, msg=msg):
            client.call("eth_getCode", ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                        "latest"])
        self.assertEqual(len(transport.calls), 2, msg=msg)
        self.assertEqual(sleeps, [1], msg=msg)


class Example3JsonRpcError(unittest.TestCase):
    """Example 3: a JSON-RPC error object raises RpcError at once, no retry."""

    def test_json_rpc_error_no_retry(self):
        msg = ("a JSON-RPC error object must raise RpcError(code, message) "
               "after one transport call, with no sleep")
        transport = RecordingTransport([
            error_response(-32001, "block not found: 0x18deac1")])
        sleeps = []
        client = RpcClient(transport.url, transport=transport, sleep=sleeps.append)
        with self.assertRaises(RpcError, msg=msg) as caught:
            client.call("eth_getBlockReceipts", ["0x18deac1"])
        self.assertEqual(len(transport.calls), 1, msg=msg)
        self.assertEqual(sleeps, [], msg=msg)
        self.assertEqual(caught.exception.code, -32001, msg=msg)
        self.assertEqual(caught.exception.message, "block not found: 0x18deac1",
                         msg=msg)
        self.assertIn("block not found: 0x18deac1", str(caught.exception), msg=msg)

    def test_404_no_retry(self):
        msg = "any other HTTP status must raise RpcError at once"
        transport = RepeatingTransport((404, b"not found"))
        sleeps = []
        client = RpcClient(transport.url, transport=transport, sleep=sleeps.append)
        with self.assertRaises(RpcError, msg=msg) as caught:
            client.call("eth_blockNumber", [])
        self.assertEqual(len(transport.calls), 1, msg=msg)
        self.assertEqual(sleeps, [], msg=msg)
        self.assertEqual(caught.exception.code, 404, msg=msg)

    def test_non_json_body_no_retry(self):
        msg = "a body that is not JSON must raise RpcError at once"
        transport = RepeatingTransport((200, b"<html>"))
        sleeps = []
        client = RpcClient(transport.url, transport=transport, sleep=sleeps.append)
        with self.assertRaises(RpcError, msg=msg):
            client.call("eth_blockNumber", [])
        self.assertEqual(len(transport.calls), 1, msg=msg)
        self.assertEqual(sleeps, [], msg=msg)

    def test_no_result_no_error(self):
        msg = "a 200 body with neither result nor error must raise RpcError at once"
        transport = RepeatingTransport((200, b'{"jsonrpc":"2.0","id":1}'))
        sleeps = []
        client = RpcClient(transport.url, transport=transport, sleep=sleeps.append)
        with self.assertRaises(RpcError, msg=msg):
            client.call("eth_blockNumber", [])
        self.assertEqual(len(transport.calls), 1, msg=msg)


class Example4SecretHygiene(unittest.TestCase):
    """Example 4: a transport OSError gives RpcError without the URL or key."""

    def test_transport_failure_retried_then_no_secret(self):
        msg = ("a transport OSError must be retried, then RpcError(None) whose "
               "str, repr and traceback never contain the key or the URL")
        url = "https://mainnet.infura.io/v3/" + TESTKEY
        transport = RepeatingTransport(OSError("boom " + url))
        sleeps = []
        client = RpcClient(url, transport=transport, sleep=sleeps.append,
                           max_retries=3)
        with self.assertRaises(RpcError, msg=msg) as caught:
            client.call("eth_blockNumber", [])
        self.assertEqual(len(transport.calls), 4, msg=msg)
        self.assertEqual(sleeps, [1, 2, 4], msg=msg)
        self.assertIsNone(caught.exception.code, msg=msg)
        err = caught.exception
        texts = [str(err), repr(err), repr(err.args),
                 "".join(traceback.format_exception(type(err), err, err.__traceback__))]
        for i, text in enumerate(texts):
            self.assertNotIn(TESTKEY, text,
                             msg="the key must not show in text %d" % i)
            self.assertNotIn(url, text,
                             msg="the URL must not show in text %d" % i)

    def test_default_transport_fails_silently(self):
        msg = "the default urllib transport must fail as RpcError, not leak secrets"
        url = "https://mainnet.infura.io/v3/" + TESTKEY
        client = RpcClient(url, sleep=lambda s: None, max_retries=1)
        with self.assertRaises(RpcError, msg=msg) as caught:
            client.call("eth_blockNumber", [])
        err = caught.exception
        texts = [str(err), repr(err), repr(err.args),
                 "".join(traceback.format_exception(type(err), err, err.__traceback__))]
        for i, text in enumerate(texts):
            self.assertNotIn(TESTKEY, text,
                             msg="the key must not show in text %d" % i)
            self.assertNotIn(url, text,
                             msg="the URL must not show in text %d" % i)


class Example5OnSpend(unittest.TestCase):
    """Example 5: on_spend(method, price) once per successful call."""

    maxDiff = None

    def test_on_spend_sums_1160(self):
        msg = "one receipts call and two getCode calls must sum to 1160 credits"
        got = []
        transport = RecordingTransport([body_response([]), body_response("0x6060"),
                                        body_response("0x6060")])
        client = RpcClient(transport.url, transport=transport, sleep=lambda s: None,
                           prices={"eth_getBlockReceipts": 1000, "eth_getCode": 80},
                           on_spend=lambda m, c: got.append((m, c)))
        client.call("eth_getBlockReceipts", ["0x18dea21"])
        client.call("eth_getCode",
                    ["0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", "0x18dea21"])
        client.call("eth_getCode",
                    ["0xdac17f958d2ee523a2206206994597c13d831ec7", "0x18dea21"])
        self.assertEqual(got, [("eth_getBlockReceipts", 1000),
                               ("eth_getCode", 80), ("eth_getCode", 80)], msg=msg)
        self.assertEqual(sum(c for _, c in got), 1160, msg=msg)

    def test_on_spend_silent_on_error(self):
        msg = "on_spend must not be called for a failed call"
        got = []
        transport = RecordingTransport([
            error_response(-32001, "block not found: 0x18deac1")])
        client = RpcClient(transport.url, transport=transport, sleep=lambda s: None,
                           prices={"eth_getCode": 80},
                           on_spend=lambda m, c: got.append((m, c)))
        with self.assertRaises(RpcError, msg=msg):
            client.call("eth_getCode", ["0x00", "latest"])
        self.assertEqual(got, [], msg=msg)

    def test_prices_default_to_config(self):
        msg = "prices=None must fall back to ethsc.config.PRICES"
        got = []
        transport = RecordingTransport([body_response("0x18dea21")])
        client = RpcClient(transport.url, transport=transport, sleep=lambda s: None,
                           on_spend=lambda m, c: got.append((m, c)))
        result = client.call("eth_blockNumber", [])
        self.assertEqual(result, "0x18dea21", msg=msg)
        self.assertEqual(got, [("eth_blockNumber", 80)], msg=msg)

    def test_unpriced_method_spends_zero(self):
        msg = "a method absent from prices must spend 0"
        got = []
        transport = RecordingTransport([body_response("0x1")])
        client = RpcClient(transport.url, transport=transport, sleep=lambda s: None,
                           prices={"eth_getCode": 80},
                           on_spend=lambda m, c: got.append((m, c)))
        client.call("eth_chainId", [])
        self.assertEqual(got, [("eth_chainId", 0)], msg=msg)


class ConfigPrices(unittest.TestCase):
    """ethsc/config.py holds the credit table exactly."""

    def test_prices_table(self):
        msg = "PRICES must be exactly the Infura credit table of TASK_PHASE4"
        self.assertEqual(PRICES, {"eth_blockNumber": 80,
                                  "eth_getBlockReceipts": 1000,
                                  "eth_getCode": 80}, msg=msg)


class InfuraUrlTests(unittest.TestCase):
    """infura_url: environment, file, priority, missing key."""

    def test_from_environment(self):
        msg = "the environment variable must win"
        with mock.patch.dict(os.environ, {"INFURA_API_KEY": TESTKEY}, clear=True):
            self.assertEqual(infura_url(env_path=os.path.join(tempfile.mkdtemp(),
                                                              "missing.env")),
                             "https://mainnet.infura.io/v3/" + TESTKEY, msg=msg)

    def test_from_env_file_plain(self):
        msg = "the key must be read from a .env file when the variable is absent"
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, ".env")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# comment\nOTHER=1\nINFURA_API_KEY=TESTKEY-FILE-0000\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(infura_url(path),
                             "https://mainnet.infura.io/v3/TESTKEY-FILE-0000", msg=msg)

    def test_from_env_file_quoted(self):
        msg = "spaces around the value and one pair of quotes must be stripped"
        directory = tempfile.mkdtemp()
        path_dq = os.path.join(directory, "dq.env")
        path_sq = os.path.join(directory, "sq.env")
        with open(path_dq, "w", encoding="utf-8") as handle:
            handle.write('INFURA_API_KEY="TESTKEY-FILE-0000"\n')
        with open(path_sq, "w", encoding="utf-8") as handle:
            handle.write("INFURA_API_KEY= 'TESTKEY-FILE-0000' \n")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(infura_url(path_dq),
                             "https://mainnet.infura.io/v3/TESTKEY-FILE-0000",
                             msg=msg)
            self.assertEqual(infura_url(path_sq),
                             "https://mainnet.infura.io/v3/TESTKEY-FILE-0000",
                             msg=msg)

    def test_environment_wins_over_file(self):
        msg = "the environment must win over the .env file"
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, ".env")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("INFURA_API_KEY=TESTKEY-FILE-0000\n")
        with mock.patch.dict(os.environ, {"INFURA_API_KEY": TESTKEY}):
            self.assertEqual(infura_url(path),
                             "https://mainnet.infura.io/v3/" + TESTKEY, msg=msg)

    def test_missing_key_raises(self):
        msg = "no key anywhere must raise RpcError(None, ...)"
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "missing.env")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RpcError, msg=msg) as caught:
                infura_url(path)
            self.assertIsNone(caught.exception.code, msg=msg)
            self.assertIn("INFURA_API_KEY is not set", caught.exception.message,
                          msg=msg)

    def test_commented_key_only_raises(self):
        msg = "a key only inside a comment line must not count"
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "nokey.env")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# INFURA_API_KEY=TESTKEY-9999\nOTHER=1\n")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RpcError, msg=msg):
                infura_url(path)


if __name__ == "__main__":
    unittest.main()
