"""Judge for phase 18, group ingest: Follow Chain example 18.

Example 18 pins that follow_chain's watch parameter reaches every
ingest_block call of the pass unchanged: the store of Ingest Block
example 12 (0x1111111111111111111111111111111111111111 holding the code
of 0xb53c071bdb35d21aa1216b084f79c372d71053d5, seeded "deployed in
26077729") over block 26077729 gives its 3 alerts at watch=0.8, and 5
alerts at the default threshold (watch=None), the two extra ERC-20
tokens (LINK, SHIB) sharing 9/12 of the seed's selectors at exactly
0.75. No network: FakeRpc answers from tests/fixtures.
"""

import inspect
import unittest

from ethsc.ingest import follow_chain

from tests.helpers import FakeRpc, block_codes, temp_store

SEED = "0x1111111111111111111111111111111111111111"
DEPLOYED = "0xb53c071bdb35d21aa1216b084f79c372d71053d5"
LABEL = "deployed in 26077729"
LINK = "0x514910771af9ca656af840dff83e8264ecf986ca"
SHIB = "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce"
WETH9 = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
COPY = "0xff74317e948695297acb79cb2de06111f5cc16b3"


def _seed_store():
    """The store of Ingest Block example 12: seed + progress 26077728."""
    store = temp_store()
    text = block_codes()[DEPLOYED]
    code_id = store.put_code(bytes.fromhex(text[2:]))
    store.put_address(SEED, code_id, 1)
    store.add_seed(SEED, LABEL)
    store.set_progress(26077728)
    return store


def _alert(address, score, origin):
    return {
        "address": address,
        "seed_address": SEED,
        "label": LABEL,
        "score": score,
        "origin": origin,
    }


class TestFollowChainWatchP18(unittest.TestCase):

    def test_example_18_watch_0_8_gives_the_three_alerts(self):
        store = _seed_store()
        rpc = FakeRpc()
        summary = follow_chain(rpc, store, prices={}, watch=0.8)
        self.assertEqual(summary["blocks"], 1)
        self.assertIsNone(summary["stopped"])
        self.assertEqual(
            summary["alerts"],
            [
                _alert(DEPLOYED, 1.0, "created"),
                _alert(WETH9, 9.0 / 11.0, "seen"),
                _alert(COPY, 1.0, "seen"),
            ],
        )
        self.assertEqual(summary["progress"], 26077729)

    def test_example_18_default_watch_gives_five_alerts(self):
        store = _seed_store()
        rpc = FakeRpc()
        summary = follow_chain(rpc, store, prices={})
        self.assertEqual(
            summary["alerts"],
            [
                _alert(LINK, 0.75, "seen"),
                _alert(SHIB, 0.75, "seen"),
                _alert(DEPLOYED, 1.0, "created"),
                _alert(WETH9, 9.0 / 11.0, "seen"),
                _alert(COPY, 1.0, "seen"),
            ],
        )
        self.assertEqual(summary["progress"], 26077729)

    def test_watch_is_the_last_parameter_of_follow_chain(self):
        parameters = list(inspect.signature(follow_chain).parameters)
        self.assertEqual(parameters[-1], "watch")


if __name__ == "__main__":
    unittest.main()
