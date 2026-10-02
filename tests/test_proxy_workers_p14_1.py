"""Phase 14.1: the slot reads of a block run in the worker pool.

Phase 14 resolved implementations one eth_getStorageAt at a time after
the pooled eth_getCode calls; on the public node that made a block take
18.8 s against the chain's 12 s. These tests check that with workers > 1
the reads leave the calling thread, and that stores, alerts, upgrades
and the credit ledger stay exactly those of the sequential run.
Offline, fixtures only, every db in its own temp directory.
"""

import json
import os
import threading
import unittest

from ethsc.config import PRICES
from ethsc.ingest import IMPL_SLOT, follow_chain, ingest_block
from tests.helpers import FakeRpc, block_codes, block_receipts, temp_store

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
with open(os.path.join(_FIXTURES, "storage_26077729.json"), "r",
          encoding="utf-8") as _handle:
    _STORAGE = json.load(_handle)

_BLOCK = 26077729
_ZERO = "0x" + "0" * 64
_UPGRADED = "0x" + "00" * 12 + "11" * 20


def _run(workers, storage, store=None):
    codes = block_codes()
    threads = []

    def get_code(address, block):
        return codes.get(address, "0x")

    def get_storage(address, slot, block):
        threads.append(threading.get_ident())
        return storage.get(address, {}).get(slot, _ZERO)

    store = store or temp_store()
    stats = ingest_block(_BLOCK, block_receipts(), get_code, store,
                         workers=workers, get_storage=get_storage)
    return stats, store, threads


class PooledSlotReadsTest(unittest.TestCase):

    def test_reads_leave_the_calling_thread_with_workers(self):
        _, _, threads = _run(8, _STORAGE)
        self.assertGreater(len(threads), 0, msg="slot reads happened")
        self.assertNotIn(threading.get_ident(), threads,
                         msg="with workers=8 no slot read runs in the caller")

    def test_sequential_reads_stay_in_the_calling_thread(self):
        _, _, threads = _run(None, _STORAGE)
        self.assertEqual(set(threads), {threading.get_ident()},
                         msg="workers=None keeps phase 14 behaviour")

    def test_same_store_alerts_and_upgrades_as_sequential(self):
        seq_stats, seq_store, _ = _run(None, _STORAGE)
        par_stats, par_store, _ = _run(8, _STORAGE)
        self.assertEqual(par_store.implementations(), seq_store.implementations())
        self.assertEqual(par_store.counts(), seq_store.counts())
        self.assertEqual(par_stats["alerts"], seq_stats["alerts"])
        self.assertEqual(par_stats["upgrades"], seq_stats["upgrades"])

        # second pass over the same block: every proxy is known and re-read;
        # one implementation changed on-chain -> one UPGRADE either way
        moved = sorted(a for a, row in seq_store.implementations().items()
                       if row["implementation"] is not None
                       and _STORAGE.get(a, {}).get(IMPL_SLOT, _ZERO) != _ZERO)[0]
        storage2 = json.loads(json.dumps(_STORAGE))
        storage2[moved][IMPL_SLOT] = _UPGRADED
        seq2, seq_store, _ = _run(None, storage2, seq_store)
        par2, par_store, _ = _run(8, storage2, par_store)
        self.assertEqual(len(seq2["upgrades"]), 1, msg=str(seq2["upgrades"]))
        self.assertEqual(par2["upgrades"], seq2["upgrades"])
        self.assertEqual(par_store.implementations(), seq_store.implementations())


class FollowChainLedgerTest(unittest.TestCase):

    def test_pooled_reads_are_charged_like_sequential_ones(self):
        spent = []
        for workers in (None, 8):
            store = temp_store()
            store.set_progress(_BLOCK - 1)
            rpc = FakeRpc(storage=_STORAGE, head=hex(_BLOCK))
            summary = follow_chain(rpc, store, daily_budget=3000000,
                                   day="2026-10-02", prices=PRICES,
                                   workers=workers)
            self.assertEqual(summary["blocks"], 1, msg=str(summary))
            reads = sum(1 for m, _ in rpc.calls if m == "eth_getStorageAt")
            spent.append((store.spent("2026-10-02"), reads))
        self.assertEqual(spent[0], spent[1], msg=f"(spent, reads) per mode: {spent}")


if __name__ == "__main__":
    unittest.main()
