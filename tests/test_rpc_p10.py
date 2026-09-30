"""Phase-10 smoke tests for ethsc.rpc: User-Agent header and null receipts.

Smoke only: five tests, scalars and short values. The full behaviour is
judged by the orchestrator probe and by tests/test_rpc_examples_p10.py.
No network: FakeUrlopen replaces urllib.request.urlopen through its
dotted name.
"""

import json
import unittest
from unittest import mock

from ethsc import config
from ethsc.rpc import RpcClient, RpcError

from tests.helpers import FakeTransport, FakeUrlopen


def _ok_body(result):
    return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode("utf-8")


class TestUserAgentHeader(unittest.TestCase):
    def test_default_transport_sends_user_agent(self):
        fake = FakeUrlopen()
        with mock.patch("urllib.request.urlopen", fake):
            result = RpcClient("https://ethereum-rpc.publicnode.com").call(
                "eth_chainId", [])
        self.assertEqual(result, "0x1", msg="result passthrough")
        self.assertEqual(len(fake.requests), 1, msg="one request")
        request = fake.requests[0]
        self.assertEqual(request.get_header("User-agent"), "ethsc/0.1",
                         msg="User-Agent header")
        self.assertEqual(request.get_header("Content-type"),
                         "application/json", msg="Content-Type header")


class TestNullReceipts(unittest.TestCase):
    def test_null_then_receipts_is_retried(self):
        transport = FakeTransport([
            (200, _ok_body(None)),
            (200, _ok_body(None)),
            (200, _ok_body([1, 2, 3])),
        ])
        sleeps = []
        spends = []
        client = RpcClient("http://fake/", transport=transport,
                           sleep=sleeps.append,
                           prices={"eth_getBlockReceipts": 1000},
                           on_spend=lambda m, c: spends.append((m, c)),
                           max_retries=3)
        result = client.call("eth_getBlockReceipts", ["0x18dea21"])
        self.assertEqual(result, [1, 2, 3], msg="receipts after retries")
        self.assertEqual(len(transport.calls), 3, msg="3 transport calls")
        self.assertEqual(sleeps, [1, 2], msg="sleeps 1 then 2")
        self.assertEqual(spends, [("eth_getBlockReceipts", 1000)],
                         msg="one charge, after the nulls")

    def test_null_exhausted_raises(self):
        transport = FakeTransport([(200, _ok_body(None))] * 6)
        sleeps = []
        spends = []
        client = RpcClient("http://fake/", transport=transport,
                           sleep=sleeps.append,
                           on_spend=lambda m, c: spends.append((m, c)),
                           max_retries=5)
        with self.assertRaises(RpcError) as caught:
            client.call("eth_getBlockReceipts", ["0x1312d00"])
        self.assertIsNone(caught.exception.code, msg="code None")
        self.assertEqual(caught.exception.message,
                         "eth_getBlockReceipts returned null",
                         msg="exact message")
        self.assertEqual(len(transport.calls), 6, msg="6 transport calls")
        self.assertEqual(sleeps, [1, 2, 4, 8, 16], msg="five sleeps")
        self.assertEqual(spends, [], msg="never charged")

    def test_null_other_method_returned_as_is(self):
        transport = FakeTransport([(200, _ok_body(None))])
        sleeps = []
        client = RpcClient("http://fake/", transport=transport,
                           sleep=sleeps.append)
        result = client.call("eth_getCode",
                             ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                              "latest"])
        self.assertIsNone(result, msg="null passthrough for eth_getCode")
        self.assertEqual(len(transport.calls), 1, msg="no retry")
        self.assertEqual(sleeps, [], msg="no sleep")


class TestConfigPublicnode(unittest.TestCase):
    def test_publicnode_url_and_prices_unchanged(self):
        self.assertEqual(config.PUBLICNODE_URL,
                         "https://ethereum-rpc.publicnode.com",
                         msg="PUBLICNODE_URL value")
        self.assertEqual(config.PRICES,
                         {"eth_blockNumber": 80,
                          "eth_getBlockReceipts": 1000,
                          "eth_getCode": 80},
                         msg="PRICES unchanged")


if __name__ == "__main__":
    unittest.main()
