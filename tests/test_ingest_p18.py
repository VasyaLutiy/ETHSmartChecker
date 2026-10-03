"""Phase 18 smoke: follow_chain passes watch down to ingest_block.

Smoke only -- the orchestrator's probe judges completeness. FakeRpc()
serves block 26077729 from the fixtures (head 0x18dea21); temp_store()
is a fresh Store in a fresh temporary directory.
"""

import inspect
import unittest
from unittest import mock

import ethsc.ingest
from tests.helpers import FakeRpc, temp_store


def _run(watch_kwargs):
    """One follow_chain pass with ingest_block wrapped by a watch spy."""
    seen = []
    original = ethsc.ingest.ingest_block

    def spy(*args, **kwargs):
        seen.append(kwargs.get("watch"))
        return original(*args, **kwargs)

    store = temp_store()
    with mock.patch.object(ethsc.ingest, "ingest_block", spy):
        summary = ethsc.ingest.follow_chain(FakeRpc(), store, **watch_kwargs)
    return seen, summary


class WatchPassThroughTest(unittest.TestCase):
    def test_watch_is_last_parameter(self):
        params = list(
            inspect.signature(ethsc.ingest.follow_chain).parameters)
        self.assertEqual(params[-1], "watch")
        self.assertEqual(
            params[-2], "on_upgrades")

    def test_watch_reaches_ingest_block(self):
        seen, summary = _run({"watch": 0.8})
        self.assertGreater(len(seen), 0)
        self.assertEqual(set(seen), {0.8})
        self.assertEqual(summary["stopped"], None)
        self.assertEqual(summary["blocks"], 1)

    def test_watch_defaults_to_none(self):
        seen, summary = _run({})
        self.assertGreater(len(seen), 0)
        self.assertEqual(set(seen), {None})
        self.assertEqual(summary["blocks"], 1)


if __name__ == "__main__":
    unittest.main()
