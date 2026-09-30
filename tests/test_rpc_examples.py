"""Judge tests for ethsc/rpc.py: the five examples of Function RPC Client
from contour.yaml (recorded from Infura on 2026-09-28).

Offline: every network answer comes from tests/fixtures/ and an injected
transport; no test opens a socket.
"""

import json
import os
import unittest

from ethsc.rpc import RpcClient, RpcError

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_429():
    """(status, body_bytes) from tests/fixtures/rpc_429.json."""
    with open(os.path.join(FIXTURES, "rpc_429.json"), "r", encoding="utf-8") as h:
        d = json.load(h)
    return d["status"], d["body"].encode("utf-8")


def weth9_text():
    """The verbatim eth_getCode result string of code_weth9.hex."""
    with open(os.path.join(FIXTURES, "code_weth9.hex"), "r", encoding="utf-8") as h:
        return h.read().strip()


def ok_body(result_text):
    return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result_text}).encode("utf-8")


class FakeTransport(object):
    """Answers from a scripted list, records (url, body) calls."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def __call__(self, url, body):
        self.calls.append((url, body))
        status, resp = self.answers.pop(0)
        return status, resp


class RpcClientExamples(unittest.TestCase):
    maxDiff = None

    def test_rpc_client_example_1_429_then_success(self):
        """RPC Client example 1: one 429 from rpc_429.json, then success
        returning the text of code_weth9.hex; 2 transport calls; sleep
        called once with 1."""
        status429, body429 = load_429()
        weth = weth9_text()
        transport = FakeTransport([(status429, body429), (200, ok_body(weth))])
        sleeps = []
        client = RpcClient(
            "https://mainnet.infura.io/v3/TESTKEY-0000",
            transport=transport,
            sleep=lambda s: sleeps.append(s),
            prices={"eth_getCode": 80},
        )
        result = client.call(
            "eth_getCode", ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "latest"]
        )
        self.assertEqual(result, weth, "result must equal the code_weth9.hex text")
        self.assertEqual(len(transport.calls), 2, "exactly 2 transport calls")
        self.assertEqual(sleeps, [1], "sleep called once, with 1")

    def test_rpc_client_example_2_always_429_exhausts_retries(self):
        """RPC Client example 2: transport always answers rpc_429.json;
        max_retries=3; then RpcError after 4 transport calls; sleeps [1, 2, 4]."""
        status429, body429 = load_429()
        transport = FakeTransport(
            [(status429, body429)] * 4 + [(status429, body429)]
        )
        sleeps = []
        client = RpcClient(
            "https://mainnet.infura.io/v3/TESTKEY-0000",
            transport=transport,
            sleep=lambda s: sleeps.append(s),
            max_retries=3,
        )
        with self.assertRaises(RpcError, msg="RpcError after exhausting retries"):
            client.call("eth_getCode", ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"])
        self.assertEqual(len(transport.calls), 4, "4 transport calls total")
        self.assertEqual(sleeps, [1, 2, 4], "backoff sleeps [1, 2, 4]")

    def test_rpc_client_example_3_jsonrpc_error_no_retry(self):
        """RPC Client example 3: a 200 response carrying the Infura error
        object {"code":-32001,"message":"block not found: 0x18deac1"};
        RpcError with code -32001 after 1 transport call and no sleep."""
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32001, "message": "block not found: 0x18deac1"},
        }).encode("utf-8")
        transport = FakeTransport([(200, body)])
        sleeps = []
        client = RpcClient(
            "https://mainnet.infura.io/v3/TESTKEY-0000",
            transport=transport,
            sleep=lambda s: sleeps.append(s),
        )
        with self.assertRaises(RpcError, msg="RpcError on a JSON-RPC error object") as ctx:
            client.call("eth_getBlockReceipts", ["0x18deac1"])
        self.assertEqual(ctx.exception.code, -32001, "error code is -32001")
        self.assertEqual(len(transport.calls), 1, "exactly 1 transport call")
        self.assertEqual(sleeps, [], "no sleep on a JSON-RPC error")

    def test_rpc_client_example_4_transport_error_hides_key(self):
        """RPC Client example 4: transport raising OSError("boom " + url);
        RpcError whose str and repr do not contain "TESTKEY-0000"."""
        url = "https://mainnet.infura.io/v3/TESTKEY-0000"
        key = "TESTKEY-0000"

        def bad_transport(u, body):
            raise OSError("boom " + u)

        client = RpcClient(url, transport=bad_transport, max_retries=0)
        with self.assertRaises(RpcError, msg="transport failure gives RpcError") as ctx:
            client.call("eth_blockNumber", [])
        err = ctx.exception
        self.assertNotIn(key, str(err), "str(e) must not contain the key")
        self.assertNotIn(key, repr(err), "repr(e) must not contain the key")
        for arg in err.args:
            self.assertNotIn(key, str(arg), "e.args must not contain the key")

    def test_rpc_client_example_5_on_spend_sums_to_1160(self):
        """RPC Client example 5: prices {eth_getBlockReceipts: 1000,
        eth_getCode: 80} with an on_spend collector; one successful
        eth_getBlockReceipts and two eth_getCode sum to 1160."""
        spent = []

        def on_spend(method, price):
            spent.append((method, price))

        transport = FakeTransport([
            (200, ok_body([])),
            (200, ok_body(None)),
            (200, ok_body(None)),
        ])
        client = RpcClient(
            "https://mainnet.infura.io/v3/TESTKEY-0000",
            transport=transport,
            sleep=lambda s: None,
            prices={"eth_getBlockReceipts": 1000, "eth_getCode": 80},
            on_spend=on_spend,
        )
        client.call("eth_getBlockReceipts", ["0x18dea21"])
        client.call("eth_getCode", ["0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"])
        client.call("eth_getCode", ["0xdAC17F958D2ee523a2206206994597C13D831ec7"])
        self.assertEqual(len(spent), 3, "on_spend called once per successful call")
        total = sum(price for _, price in spent)
        self.assertEqual(total, 1160, "1000 + 80 + 80 = 1160 credits")
        self.assertEqual(
            spent,
            [("eth_getBlockReceipts", 1000), ("eth_getCode", 80), ("eth_getCode", 80)],
            "method and price pairs in call order",
        )


if __name__ == "__main__":
    unittest.main()
