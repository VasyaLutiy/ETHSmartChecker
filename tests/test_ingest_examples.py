"""Example-based tests for ethsc/ingest.py, taken from the examples of
docs/TASK_PHASE4.md, contour.yaml and tests/fixtures/README.md.

One test per example, offline: receipts, codes and a fake rpc come from
tests/fixtures/. No network (and the acceptance wrapper blocks it).
"""

import json
import os
import tempfile
import unittest

from ethsc.ingest import discover_candidates, ingest_block, follow_chain
from ethsc.store import Store

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

BLOCK = 26077729
UNIV2_PAIR = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
UNIV2_SIBLINGS = [
    "0x22052a1a0f5a3d2839d71c458f177e68b0e73963",
    "0x2621cc0b3f3c079c1db0e80794aa24976f0b9e3c",
    "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f",
]

PRICES = {
    "eth_blockNumber": 80,
    "eth_getBlockReceipts": 1000,
    "eth_getCode": 80,
}


def _load(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


def _receipts():
    return _load("receipts_26077729.json")["result"]


def _codes():
    return _load("codes_26077729.json")


def _fresh_store():
    return Store(os.path.join(tempfile.mkdtemp(), "t.db"))


class FakeRpc(object):
    """Fake rpc for follow_chain: duck-types call(method, params)."""

    def __init__(self, receipts, codes, head_hex):
        self.receipts = receipts
        self.codes = codes
        self.head_hex = head_hex
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, list(params)))
        if method == "eth_blockNumber":
            return self.head_hex
        if method == "eth_getBlockReceipts":
            return self.receipts
        if method == "eth_getCode":
            return self.codes[params[0]]
        raise AssertionError("unexpected method: %s" % method)

    def count(self, method):
        return len([entry for entry in self.calls if entry[0] == method])


class DiscoverCandidatesExamples(unittest.TestCase):
    maxDiff = None

    def test_discover_candidates_example_1(self):
        """Discover Candidates example 1: the receipts of block
        26077729 give 206 candidates; 135 distinct to, 119 distinct log
        addresses, one contractAddress 0xb53c071bdb35d21aa1216b084f79c372d71053d5."""
        receipts = _receipts()
        candidates = discover_candidates(receipts)
        to_set = set()
        log_set = set()
        contract_set = set()
        for receipt in receipts:
            if receipt.get("to") is not None:
                to_set.add(receipt["to"].lower())
            for log in receipt.get("logs", []):
                log_set.add(log["address"].lower())
            if receipt.get("contractAddress") is not None:
                contract_set.add(receipt["contractAddress"].lower())
        self.assertEqual(len(receipts), 218, msg="218 receipts in the fixture")
        self.assertEqual(len(candidates), 206,
                         msg="206 distinct candidates over the fixture")
        self.assertEqual(len(to_set), 135, msg="135 distinct to")
        self.assertEqual(len(log_set), 119, msg="119 distinct log addresses")
        self.assertEqual(contract_set,
                         {"0xb53c071bdb35d21aa1216b084f79c372d71053d5"},
                         msg="one contractAddress, 0xb53c071b…")
        self.assertIn("0xb53c071bdb35d21aa1216b084f79c372d71053d5", candidates,
                      msg="the deployment is a candidate")
        self.assertEqual(candidates, sorted(candidates),
                         msg="the list is sorted")
        for address in candidates:
            self.assertEqual(address, address.lower(),
                             msg="all candidates lowercase")
        self.assertEqual(len(_codes()), 206,
                         msg="the 206 candidates are exactly the fixture keys")

    def test_discover_candidates_example_2(self):
        """Discover Candidates example 2: an empty list of receipts gives []."""
        self.assertEqual(discover_candidates([]), [],
                         msg="an empty receipt list gives []")


class IngestBlockExamples(unittest.TestCase):
    maxDiff = None

    def test_ingest_block_example_1(self):
        """Ingest Block example 1: receipts_26077729, a fresh store and a
        fake get_code serving codes_26077729.json give candidates 206,
        fetched 206, contracts 147, eoas 59, failed 0, complete True;
        the store holds 130 codes."""
        store = _fresh_store()
        codes = _codes()
        stats = ingest_block(BLOCK, _receipts(),
                             lambda a, b: codes[a], store)
        self.assertEqual(stats["candidates"], 206, msg="candidates 206")
        self.assertEqual(stats["fetched"], 206, msg="fetched 206")
        self.assertEqual(stats["contracts"], 147, msg="contracts 147")
        self.assertEqual(stats["eoas"], 59, msg="eoas 59")
        self.assertEqual(stats["failed"], 0, msg="failed 0")
        self.assertEqual(stats["deferred"], 0, msg="deferred 0")
        self.assertTrue(stats["complete"], msg="complete True")
        self.assertEqual(stats["known"], 0, msg="known 0 on a fresh store")
        self.assertEqual(len(store.fingerprints()), 130,
                         msg="the store has 130 distinct codes")
        self.assertEqual(stats["contracts"] + stats["eoas"] + stats["failed"],
                         stats["fetched"],
                         msg="fetched == contracts + eoas + failed")

    def test_ingest_block_example_2(self):
        """Ingest Block example 2: the same block again on the same store
        gives known 206, fetched 0, complete True."""
        codes = _codes()
        store = _fresh_store()
        ingest_block(BLOCK, _receipts(), lambda a, b: codes[a], store)
        stats = ingest_block(BLOCK, _receipts(), lambda a, b: codes[a], store)
        self.assertEqual(stats["known"], 206, msg="known 206")
        self.assertEqual(stats["fetched"], 0, msg="fetched 0")
        self.assertTrue(stats["complete"], msg="complete True")

    def test_ingest_block_example_3(self):
        """Ingest Block example 3: a fresh store with max_calls=50, five
        ingest_block calls, give fetched 50, 50, 50, 50, 6; complete
        False four times, then True."""
        codes = _codes()
        store = _fresh_store()
        fetched_seq = []
        complete_seq = []
        for _ in range(5):
            stats = ingest_block(BLOCK, _receipts(), lambda a, b: codes[a],
                                 store, max_calls=50)
            fetched_seq.append(stats["fetched"])
            complete_seq.append(stats["complete"])
        self.assertEqual(fetched_seq, [50, 50, 50, 50, 6],
                         msg="fetched 50, 50, 50, 50, 6")
        self.assertEqual(complete_seq,
                         [False, False, False, False, True],
                         msg="complete False four times, then True")
        self.assertEqual(len(store.fingerprints()), 130,
                         msg="after the fifth call the store has 130 codes")

    def test_ingest_block_example_4(self):
        """Ingest Block example 4: a get_code raising OSError for
        0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc only gives failed 1,
        fetched 206, contracts 146; the other three UniswapV2Pair
        addresses are stored (Tolerant Parser)."""

        def get_code(address, block):
            if address == UNIV2_PAIR:
                raise OSError("boom")
            return _codes()[address]

        store = _fresh_store()
        stats = ingest_block(BLOCK, _receipts(), get_code, store)
        self.assertEqual(stats["failed"], 1, msg="failed 1")
        self.assertEqual(stats["fetched"], 206, msg="fetched 206")
        self.assertEqual(stats["contracts"], 146, msg="contracts 146")
        self.assertTrue(stats["complete"], msg="a failure keeps the block")
        for address in UNIV2_SIBLINGS:
            self.assertTrue(store.has_address(address),
                            msg="%s is stored" % address)
            self.assertIsNotNone(store.code_of(address),
                                 msg="%s has code" % address)
        self.assertFalse(store.has_address(UNIV2_PAIR),
                         msg="the failed address is not stored")


class FollowChainExamples(unittest.TestCase):
    maxDiff = None

    def _rpc(self):
        return FakeRpc(_receipts(), _codes(), "0x18dea21")

    def test_follow_chain_example_1(self):
        """Follow Chain example 1: fake rpc with head 0x18dea21,
        receipts_26077729 and codes_26077729, progress 26077728, the
        Infura prices and daily_budget 3000000 give blocks 1, progress
        26077729, spent 17560 (80 + 1000 + 206 * 80)."""
        store = _fresh_store()
        store.set_progress(BLOCK - 1)
        rpc = self._rpc()
        summary = follow_chain(rpc, store, daily_budget=3000000,
                               day="2026-09-28", prices=PRICES)
        self.assertEqual(summary["blocks"], 1, msg="one block completed")
        self.assertEqual(summary["progress"], BLOCK,
                         msg="progress moved to 26077729")
        self.assertIsNone(summary["stopped"], msg="no stop")
        self.assertEqual(store.spent("2026-09-28"), 17560,
                         msg="spent 80 + 1000 + 206 * 80 = 17560")

    def test_follow_chain_example_2(self):
        """Follow Chain example 2: the same with daily_budget 10000 stops
        with stopped "budget" after 111 eth_getCode calls, spent 9960
        (80 + 1000 + 111 * 80), progress still 26077728."""
        store = _fresh_store()
        store.set_progress(BLOCK - 1)
        rpc = self._rpc()
        summary = follow_chain(rpc, store, daily_budget=10000,
                               day="2026-09-28", prices=PRICES)
        self.assertEqual(rpc.count("eth_getCode"), 111,
                         msg="stopped after 111 eth_getCode calls")
        self.assertEqual(store.spent("2026-09-28"), 9960,
                         msg="spent 80 + 1000 + 111 * 80 = 9960")
        self.assertEqual(summary["stopped"], "budget", msg='stopped "budget"')
        self.assertEqual(summary["progress"], BLOCK - 1,
                         msg="progress still 26077728")
        self.assertEqual(summary["blocks"], 0,
                         msg="no block completed within the budget")

    def test_follow_chain_example_3(self):
        """Follow Chain example 3: the example-2 store with a new day and
        daily_budget 3000000 finishes the block: 95 eth_getCode calls on
        the resume, progress 26077729."""
        store = _fresh_store()
        store.set_progress(BLOCK - 1)
        follow_chain(self._rpc(), store, daily_budget=10000,
                     day="2026-09-28", prices=PRICES)
        rpc = self._rpc()  # a fresh rpc: count only this run's calls
        summary = follow_chain(rpc, store, daily_budget=3000000,
                               day="2026-09-29", prices=PRICES)
        self.assertEqual(rpc.count("eth_getCode"), 95,
                         msg="95 eth_getCode calls on the new day (206 - 111)")
        self.assertEqual(summary["progress"], BLOCK,
                         msg="progress 26077729 after the resume")
        self.assertIsNone(summary["stopped"], msg="no stop on the resume")
        self.assertEqual(summary["blocks"], 1,
                         msg="the resumed block completed")
        self.assertEqual(store.spent("2026-09-29"), 80 + 1000 + 95 * 80,
                         msg="the new day pays blockNumber, receipts and "
                             "the 95 remaining codes: 80 + 1000 + 7600 = 8680")


if __name__ == "__main__":
    unittest.main()
