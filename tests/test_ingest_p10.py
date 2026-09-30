"""Phase-10 smoke tests for ethsc.ingest: workers, code_tag, null receipts.

At most five test_* functions, scalars and short values only; the
complete contract is judged by the orchestrator probe and the judge
card. Every stub comes from tests/helpers.py; no network anywhere.
"""

import unittest

from ethsc.ingest import discover_candidates, follow_chain, ingest_block
from ethsc.rpc import RpcError

try:
    from tests.helpers import (CodeServer, FakeRpc, block_codes,
                               block_receipts, temp_store)
except ImportError:  # pragma: no cover - depends on how pytest is invoked
    from helpers import (CodeServer, FakeRpc, block_codes, block_receipts,
                         temp_store)

BLOCK = 26077729
DAY = "2026-09-28"
PRICES = {"eth_blockNumber": 80, "eth_getBlockReceipts": 1000,
          "eth_getCode": 80}


class TestIngestP10(unittest.TestCase):

    def test_parallel_matches_sequential(self):
        receipts = block_receipts()
        seq_store = temp_store()
        seq_stats = ingest_block(BLOCK, receipts, CodeServer(), seq_store)
        par_store = temp_store()
        par_stats = ingest_block(BLOCK, receipts, CodeServer(), par_store,
                                 workers=8)
        self.assertEqual(par_stats["candidates"], 206, msg="candidates")
        self.assertEqual(par_stats["fetched"], seq_stats["fetched"],
                         msg="fetched equal")
        self.assertEqual(par_stats["contracts"], 147, msg="contracts")
        self.assertEqual(par_stats["eoas"], 59, msg="eoas")
        self.assertEqual(par_stats["failed"], 0, msg="failed")
        self.assertTrue(par_stats["complete"], msg="complete")
        self.assertEqual(par_stats["alerts"], [], msg="no alerts")
        self.assertEqual(par_store.counts(), seq_store.counts(),
                         msg="counts equal")

    def test_parallel_max_calls(self):
        receipts = block_receipts()
        server = CodeServer()
        stats = ingest_block(BLOCK, receipts, server, temp_store(),
                             max_calls=50, workers=8)
        self.assertEqual(stats["fetched"], 50, msg="fetched 50")
        self.assertEqual(stats["deferred"], 156, msg="deferred 156")
        self.assertFalse(stats["complete"], msg="incomplete")
        candidates = discover_candidates(receipts)
        self.assertEqual(len(server.calls), 50, msg="50 get_code calls")
        self.assertEqual(server.calls[0][0], candidates[0],
                         msg="first candidate fetched first")
        self.assertEqual(server.calls[-1][0], candidates[49],
                         msg="50th candidate fetched last")

    def test_null_receipts_raises_rpc_error(self):
        rpc = FakeRpc(null_receipts=True)
        store = temp_store()
        store.set_progress(26077728)
        with self.assertRaises(RpcError) as ctx:
            follow_chain(rpc, store, day=DAY, prices=PRICES,
                         daily_budget=3000000)
        self.assertIsNone(ctx.exception.code, msg="code None")
        self.assertEqual(str(ctx.exception),
                         "eth_getBlockReceipts returned null",
                         msg="message")
        self.assertEqual(store.get_progress(), 26077728,
                         msg="progress unchanged")
        self.assertEqual(store.spent(DAY), 80, msg="only blockNumber spent")
        methods = [method for method, _ in rpc.calls]
        self.assertNotIn("eth_getCode", methods, msg="no eth_getCode call")

    def test_code_tag_latest(self):
        rpc = FakeRpc()
        store = temp_store()
        store.set_progress(26077728)
        summary = follow_chain(rpc, store, day=DAY, prices=PRICES,
                               daily_budget=3000000, code_tag="latest")
        self.assertEqual(summary["blocks"], 1, msg="one block")
        code_params = [params for method, params in rpc.calls
                       if method == "eth_getCode"]
        self.assertEqual(len(code_params), 206, msg="206 eth_getCode calls")
        self.assertEqual(set(params[1] for params in code_params),
                         {"latest"}, msg="every tag is latest")

    def test_failed_under_workers(self):
        bad = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
        server = CodeServer(codes=dict(block_codes()),
                            raises={bad: OSError("x")})
        stats = ingest_block(BLOCK, block_receipts(), server, temp_store(),
                             workers=8)
        self.assertEqual(stats["fetched"], 206, msg="fetched 206")
        self.assertEqual(stats["failed"], 1, msg="failed 1")
        self.assertEqual(stats["contracts"], 146, msg="contracts 146")
        self.assertEqual(stats["eoas"], 59, msg="eoas 59")


if __name__ == "__main__":
    unittest.main()
