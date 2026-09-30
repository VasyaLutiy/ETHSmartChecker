"""Phase-10 example-based tests for ethsc/ingest.py (workers, code_tag,
null receipts), from contour.yaml.

One test per example, offline: receipts and codes come from
tests/fixtures/, the fakes from tests/helpers.py. No network (and the
acceptance wrapper blocks it).
"""

import unittest

from ethsc.ingest import discover_candidates, ingest_block, follow_chain
from ethsc.rpc import RpcError
from tests.helpers import (FakeRpc, block_codes, block_receipts, load_hex,
                           CodeServer, temp_store)

BLOCK = 26077729
UNIV2_PAIR = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
BELLE_SEED = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
BELLE_COPY = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
BELLE_RECEIPTS = [{"to": BELLE_COPY}, {"to": UNIV2_PAIR}]

PRICES = {
    "eth_blockNumber": 80,
    "eth_getBlockReceipts": 1000,
    "eth_getCode": 80,
}


def _codes():
    return block_codes()


def _receipts():
    return block_receipts()


def _belle_codes():
    codes = dict(_codes())
    codes[BELLE_COPY] = "0x" + load_hex(
        "code_belle_copy_1807090d.hex").hex()
    return codes


def _belle_store():
    store = temp_store()
    code_id = store.put_code(load_hex("code_belle.hex"))
    store.put_address(BELLE_SEED, code_id, BLOCK)
    store.add_seed(BELLE_SEED, "BELLE honeypot")
    return store


class IngestBlockParallelExamples(unittest.TestCase):

    def test_ingest_block_example_6_parallel_equals_sequential(self):
        """Ingest Block 6: with workers=8 the stats equal the sequential
        ones (candidates 206, fetched 206, contracts 147, eoas 59,
        failed 0, deferred 0, complete True, alerts []) and the store
        counts match a sequential ingest."""
        sequential_store = temp_store()
        codes = _codes()
        seq = ingest_block(BLOCK, _receipts(), lambda a, b: codes[a],
                           sequential_store)
        parallel_store = temp_store()
        server = CodeServer()
        par = ingest_block(BLOCK, _receipts(), server, parallel_store,
                           workers=8)
        expected = (206, 0, 206, 147, 59, 0, 0, True, [])
        self.assertEqual(
            (par["candidates"], par["known"], par["fetched"],
             par["contracts"], par["eoas"], par["failed"],
             par["deferred"], par["complete"], par["alerts"]),
            expected, msg="parallel stats equal the sequential ones")
        self.assertEqual(
            (seq["candidates"], seq["known"], seq["fetched"],
             seq["contracts"], seq["eoas"], seq["failed"],
             seq["deferred"], seq["complete"], seq["alerts"]),
            expected, msg="the sequential run gives the same numbers")
        self.assertEqual(parallel_store.counts(), sequential_store.counts(),
                         msg="the store counts match (206/147/130)")

    def test_ingest_block_example_7_cap_under_workers(self):
        """Ingest Block 7: max_calls=50 with workers=8 gives fetched 50,
        deferred 156, complete False, and the 50 called addresses are
        exactly the first 50 of discover_candidates."""
        server = CodeServer()
        store = temp_store()
        stats = ingest_block(BLOCK, _receipts(), server, store,
                             max_calls=50, workers=8)
        self.assertEqual(stats["fetched"], 50, msg="fetched 50")
        self.assertEqual(stats["deferred"], 156, msg="deferred 156")
        self.assertFalse(stats["complete"], msg="complete False")
        first_50 = discover_candidates(_receipts())[:50]
        self.assertEqual([call[0] for call in server.calls], first_50,
                         msg="the called addresses are the first 50 "
                             "candidates")

    def test_ingest_block_example_8_bounded_parallelism(self):
        """Ingest Block 8: workers=4 with a 10 ms hold gives fetched 206
        and a peak of calls in flight between 2 and 4."""
        server = CodeServer(hold=0.01)
        store = temp_store()
        stats = ingest_block(BLOCK, _receipts(), server, store, workers=4)
        self.assertEqual(stats["fetched"], 206, msg="fetched 206")
        self.assertGreaterEqual(server.peak, 2,
                                msg="at least 2 calls in flight")
        self.assertLessEqual(server.peak, 4,
                             msg="at most 4 calls in flight")

    def test_ingest_block_example_9_failure_under_workers(self):
        """Ingest Block 9: an OSError for 0xb4e16d01… under workers=8
        gives failed 1, fetched 206, contracts 146."""
        server = CodeServer(raises={UNIV2_PAIR: OSError("boom")})
        store = temp_store()
        stats = ingest_block(BLOCK, _receipts(), server, store, workers=8)
        self.assertEqual(stats["failed"], 1, msg="failed 1")
        self.assertEqual(stats["fetched"], 206, msg="fetched 206")
        self.assertEqual(stats["contracts"], 146, msg="contracts 146")

    def test_ingest_block_example_10_interrupt_under_workers(self):
        """Ingest Block 10: a KeyboardInterrupt for 0xb4e16d01… under
        workers=8 propagates, on_alerts is called once with the single
        alert for 0x1807090d… at 0.8667, and that address is stored."""
        store = _belle_store()
        server = CodeServer(codes=_belle_codes(),
                            raises={UNIV2_PAIR: KeyboardInterrupt("boom")})
        sink_calls = []
        with self.assertRaises(KeyboardInterrupt,
                               msg="the interrupt propagates"):
            ingest_block(BLOCK, BELLE_RECEIPTS, server, store,
                         on_alerts=sink_calls.append, workers=8)
        self.assertEqual(len(sink_calls), 1,
                         msg="on_alerts was called exactly once")
        self.assertEqual(len(sink_calls[0]), 1,
                         msg="exactly one alert before the interrupt")
        alert = sink_calls[0][0]
        self.assertEqual(alert["address"], BELLE_COPY,
                         msg="the alert names 0x1807090d…")
        self.assertEqual(alert["seed_address"], BELLE_SEED,
                         msg="the seed is the BELLE address")
        self.assertEqual(alert["label"], "BELLE honeypot",
                         msg='the label is "BELLE honeypot"')
        self.assertAlmostEqual(alert["score"], 13 / 15, places=12,
                               msg="the score is 13/15 (0.8667)")
        self.assertTrue(store.has_address(BELLE_COPY),
                        msg="0x1807090d… is stored")


class FollowChainParallelExamples(unittest.TestCase):

    def test_follow_chain_example_6_code_tag(self):
        """Follow Chain 6: with code_tag "latest" the 206 eth_getCode
        calls carry [address, "latest"]; with code_tag None they carry
        [address, "0x18dea21"]; eth_getBlockReceipts gets
        ["0x18dea21"] both times; blocks 1 and progress 26077729."""
        for code_tag, expected_tag in (("latest", "latest"),
                                       (None, "0x18dea21")):
            rpc = FakeRpc()
            store = temp_store()
            store.set_progress(BLOCK - 1)
            summary = follow_chain(rpc, store, prices={},
                                   code_tag=code_tag)
            self.assertEqual(summary["blocks"], 1, msg="one block")
            self.assertEqual(summary["progress"], BLOCK,
                             msg="progress 26077729")
            code_calls = [entry for entry in rpc.calls
                          if entry[0] == "eth_getCode"]
            self.assertEqual(len(code_calls), 206,
                             msg="206 eth_getCode calls")
            for method, params in code_calls:
                self.assertEqual(params, [params[0], expected_tag],
                                 msg="the tag param is %r" % expected_tag)
            receipt_calls = [entry for entry in rpc.calls
                             if entry[0] == "eth_getBlockReceipts"]
            self.assertEqual(receipt_calls,
                             [("eth_getBlockReceipts", ["0x18dea21"])],
                             msg="receipts called with [\"0x18dea21\"]")

    def test_follow_chain_example_7_budget_under_workers(self):
        """Follow Chain 7: Infura prices, daily_budget 3000000 and
        workers=8 give blocks 1, progress 26077729, spent 17560
        (80 + 1000 + 206 * 80)."""
        rpc = FakeRpc()
        store = temp_store()
        store.set_progress(BLOCK - 1)
        summary = follow_chain(rpc, store, daily_budget=3000000,
                               day="2026-09-28", prices=PRICES, workers=8)
        self.assertEqual(summary["blocks"], 1, msg="one block completed")
        self.assertEqual(summary["progress"], BLOCK,
                         msg="progress 26077729")
        self.assertIsNone(summary["stopped"], msg="no stop")
        self.assertEqual(store.spent("2026-09-28"), 17560,
                         msg="spent 80 + 1000 + 206 * 80 = 17560")

    def test_follow_chain_example_8_budget_cap_under_workers(self):
        """Follow Chain 8: daily_budget 10000 with workers=8 stops with
        "budget" after exactly 111 eth_getCode calls, spent 9960,
        progress still 26077728."""
        rpc = FakeRpc()
        store = temp_store()
        store.set_progress(BLOCK - 1)
        summary = follow_chain(rpc, store, daily_budget=10000,
                               day="2026-09-28", prices=PRICES, workers=8)
        self.assertEqual(summary["stopped"], "budget",
                         msg='stopped "budget"')
        self.assertEqual(
            len([entry for entry in rpc.calls
                 if entry[0] == "eth_getCode"]), 111,
            msg="exactly 111 eth_getCode calls")
        self.assertEqual(store.spent("2026-09-28"), 9960,
                         msg="spent 80 + 1000 + 111 * 80 = 9960")
        self.assertEqual(summary["progress"], BLOCK - 1,
                         msg="progress still 26077728")

    def test_follow_chain_example_9_null_receipts(self):
        """Follow Chain 9: null receipts raise RpcError(None, "eth_
        getBlockReceipts returned null"); progress still 26077728, no
        eth_getCode call, spent 80 (only eth_blockNumber)."""
        rpc = FakeRpc(null_receipts=True)
        store = temp_store()
        store.set_progress(BLOCK - 1)
        with self.assertRaises(RpcError, msg="RpcError is raised") as ctx:
            follow_chain(rpc, store, daily_budget=3000000,
                         day="2026-09-28", prices=PRICES)
        self.assertEqual(ctx.exception.code, None, msg="code is None")
        self.assertEqual(ctx.exception.message,
                         "eth_getBlockReceipts returned null",
                         msg="the message names the null answer")
        self.assertEqual(store.get_progress(), BLOCK - 1,
                         msg="progress still 26077728")
        self.assertEqual(
            [entry for entry in rpc.calls
             if entry[0] == "eth_getCode"], [],
            msg="no eth_getCode call")
        self.assertEqual(store.spent("2026-09-28"), 80,
                         msg="spent 80 (only eth_blockNumber)")

    def test_follow_chain_example_10_no_prices(self):
        """Follow Chain 10: prices {} with workers=8 gives blocks 1,
        progress 26077729, spent 0 for the day of the pass."""
        rpc = FakeRpc()
        store = temp_store()
        store.set_progress(BLOCK - 1)
        summary = follow_chain(rpc, store, prices={}, workers=8)
        self.assertEqual(summary["blocks"], 1, msg="one block completed")
        self.assertEqual(summary["progress"], BLOCK,
                         msg="progress 26077729")
        self.assertEqual(store.spent("2026-09-28"), 0,
                         msg="spent 0 for the day of the pass")


if __name__ == "__main__":
    unittest.main()
