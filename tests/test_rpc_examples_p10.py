"""Judge tests for ethsc/rpc.py, phase 10: the five examples of Function
RPC Client (examples 6-10) recorded from the public node on 2026-09-30.

Offline: the default transport's urlopen is replaced by the FakeUrlopen
stub from tests/helpers.py; no test opens a network connection.
"""

import json
import unittest
from unittest import mock

from ethsc.config import PRICES, PUBLICNODE_URL
from ethsc.rpc import RpcClient, RpcError
from tests.helpers import FakeTransport, FakeUrlopen


def body(result):
    return json.dumps(
        {"jsonrpc": "2.0", "id": 1, "result": result}
    ).encode("utf-8")


class RpcClientPhase10Examples(unittest.TestCase):
    """One test per phase-10 example of Function RPC Client."""

    def test_rpc_client_example_6_default_transport_user_agent(self):
        """RPC Client 6: with urlopen replaced by a recorder answering
        200 {"result": "0x1"}, call("eth_chainId", []) returns "0x1" and
        the recorded Request carries User-Agent "ethsc/0.1" and
        Content-Type "application/json"."""
        recorder = FakeUrlopen(status=200, body=body("0x1"))
        client = RpcClient("https://ethereum-rpc.publicnode.com")
        with mock.patch("urllib.request.urlopen", recorder):
            result = client.call("eth_chainId", [])
        self.assertEqual(result, "0x1", "the chain id result is the string 0x1")
        self.assertEqual(len(recorder.requests), 1, "exactly 1 Request recorded")
        req = recorder.requests[0]
        self.assertEqual(req.get_header("User-agent"), "ethsc/0.1",
                         msg="the User-Agent header must be ethsc/0.1")
        self.assertEqual(req.get_header("Content-type"), "application/json",
                         msg="the Content-Type header must be application/json")

    def test_rpc_client_example_7_null_then_receipts(self):
        """RPC Client 7: two null results then the fixture receipt list;
        call("eth_getBlockReceipts", ["0x18dea21"]) returns 218 receipts
        after 3 transport calls with sleeps [1, 2] and one on_spend of
        ("eth_getBlockReceipts", 1000)."""
        receipts = json.loads(open(
            "tests/fixtures/receipts_26077729.json", "r", encoding="utf-8"
        ).read())["result"]
        transport = FakeTransport([
            (200, body(None)),
            (200, body(None)),
            (200, body(receipts)),
        ])
        sleeps = []
        spent = []
        client = RpcClient(
            "http://fake/",
            transport=transport,
            sleep=lambda s: sleeps.append(s),
            prices={"eth_getBlockReceipts": 1000},
            on_spend=lambda m, p: spent.append((m, p)),
        )
        result = client.call("eth_getBlockReceipts", ["0x18dea21"])
        self.assertEqual(len(result), 218, msg="a list of 218 receipts")
        self.assertEqual(len(transport.calls), 3, msg="3 transport calls")
        self.assertEqual(sleeps, [1, 2], msg="backoff sleeps [1, 2]")
        self.assertEqual(spent, [("eth_getBlockReceipts", 1000)],
                         msg="on_spend called once with (method, 1000)")

    def test_rpc_client_example_8_always_null_exhausts_retries(self):
        """RPC Client 8: always null with max_retries=5 gives RpcError
        (None, "eth_getBlockReceipts returned null") after 6 transport
        calls, sleeps [1, 2, 4, 8, 16], on_spend never called."""
        transport = FakeTransport([(200, body(None))] * 6)
        sleeps = []
        spent = []
        client = RpcClient(
            "http://fake/",
            transport=transport,
            sleep=lambda s: sleeps.append(s),
            prices={"eth_getBlockReceipts": 1000},
            on_spend=lambda m, p: spent.append((m, p)),
            max_retries=5,
        )
        with self.assertRaises(RpcError,
                               msg="always-null exhausts the retries") as ctx:
            client.call("eth_getBlockReceipts", ["0x1312d00"])
        self.assertIsNone(ctx.exception.code, msg="the error code is None")
        self.assertEqual(ctx.exception.message, "eth_getBlockReceipts returned null",
                         msg="the error message names the null receipts")
        self.assertEqual(len(transport.calls), 6, msg="6 transport calls")
        self.assertEqual(sleeps, [1, 2, 4, 8, 16], msg="backoff sleeps [1, 2, 4, 8, 16]")
        self.assertEqual(spent, [], msg="on_spend is never called")

    def test_rpc_client_example_9_null_get_code_is_returned_as_is(self):
        """RPC Client 9: a null eth_getCode result is returned as None
        after 1 transport call, with no sleep and no retry."""
        transport = FakeTransport([(200, body(None))])
        sleeps = []
        client = RpcClient(
            "http://fake/",
            transport=transport,
            sleep=lambda s: sleeps.append(s),
        )
        result = client.call(
            "eth_getCode", ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "latest"]
        )
        self.assertIsNone(result, msg="the null result is returned as None")
        self.assertEqual(len(transport.calls), 1, msg="exactly 1 transport call")
        self.assertEqual(sleeps, [], msg="no sleep for a non-receipts null")

    def test_rpc_client_example_10_config_publicnode_url_prices(self):
        """RPC Client 10: ethsc.config.PUBLICNODE_URL equals the public
        node URL and PRICES is the unchanged Infura price table."""
        self.assertEqual(
            PUBLICNODE_URL, "https://ethereum-rpc.publicnode.com",
            msg="PUBLICNODE_URL is the keyless public node")
        self.assertEqual(
            PRICES,
            {"eth_blockNumber": 80, "eth_getBlockReceipts": 1000,
             "eth_getCode": 80},
            msg="PRICES is unchanged: 80 / 1000 / 80")


if __name__ == "__main__":
    unittest.main()
