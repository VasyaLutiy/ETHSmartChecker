"""Judge tests for Follow Chain examples 14-17 (phase 15: events).

One test per example, written against the Contour only; the code under
test is finished and read only to learn how to call it. All fixtures and
builders come from tests/helpers.py; every file a test writes goes into
a tempfile.mkdtemp() directory; no network anywhere.
"""

import datetime
import re
import unittest

from ethsc.ingest import follow_chain

from tests.helpers import FakeRpc, InterruptAfter, load_hex, temp_store

_BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_BELLE_COPY = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
_PAIR = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
_BLOCK = 26077729
_PROGRESS = 26077728
_HEAD = "0x18dea21"
_AT_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_EVENT_KEYS = [
    "id", "kind", "block", "at", "address", "seed_address", "label",
    "score", "origin", "old_impl", "new_impl",
]
_BELLE_ALERT = {
    "address": _BELLE_COPY,
    "seed_address": _BELLE,
    "label": "BELLE honeypot",
    "score": 0.8666666666666667,
    "origin": "seen",
}


def _hex_text(name):
    """A fixture's code as the verbatim eth_getCode result string."""
    return "0x" + load_hex(name).hex()


def _belle_setup():
    """The store and FakeRpc of Follow Chain example 14, made afresh."""
    store = temp_store()
    code_id = store.put_code(load_hex("code_belle.hex"))
    store.put_address(_BELLE, code_id, 1)
    store.add_seed(_BELLE, "BELLE honeypot")
    store.set_progress(_PROGRESS)
    rpc = FakeRpc(
        codes={
            _BELLE_COPY: _hex_text("code_belle_copy_1807090d.hex"),
            _PAIR: _hex_text("code_weth9.hex"),
        },
        receipts=[{"to": _BELLE_COPY}, {"to": _PAIR}],
        head=_HEAD,
    )
    return store, rpc


class FollowChainEventsP15(unittest.TestCase):
    """Follow Chain examples 14-17 of the Contour, group ingest."""

    def _check_belle_event(self, event, t0, t1):
        """The 'then' of examples 14-16 for the one recorded event."""
        expected = {
            "id": 1,
            "kind": "ALERT",
            "block": _BLOCK,
            "address": _BELLE_COPY,
            "seed_address": _BELLE,
            "label": "BELLE honeypot",
            "score": 0.8666666666666667,
            "origin": "seen",
            "old_impl": None,
            "new_impl": None,
        }
        self.assertEqual(sorted(event), sorted(_EVENT_KEYS))
        for key in _EVENT_KEYS:
            if key == "at":
                continue
            self.assertEqual(event[key], expected[key], key)
        self.assertIsInstance(event["at"], str)
        self.assertEqual(len(event["at"]), 20)
        self.assertTrue(_AT_RE.match(event["at"]), event["at"])
        stamp = datetime.datetime.strptime(
            event["at"], "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=datetime.timezone.utc)
        self.assertTrue(t0 <= stamp <= t1, (t0, event["at"], t1))

    def test_follow_chain_14(self):
        """Example 14: one ALERT line printed, exactly one event recorded."""
        store, rpc = _belle_setup()
        t0 = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0
        )
        got = []

        def sink(alerts):
            got.extend(alerts)

        summary = follow_chain(rpc, store, on_alerts=sink)
        t1 = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(summary["blocks"], 1)
        self.assertIsNone(summary["stopped"])
        self.assertEqual(summary["progress"], _BLOCK)
        self.assertEqual(got, [_BELLE_ALERT])
        events = store.events()
        self.assertEqual(len(events), 1)
        self._check_belle_event(events[0], t0, t1)
        self.assertIsNotNone(store.progress_at())

    def test_follow_chain_15(self):
        """Example 15: the alert of an incomplete block is still recorded."""
        store, rpc = _belle_setup()
        t0 = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0
        )
        summary = follow_chain(
            rpc, store, max_calls_per_block=1, on_alerts=None
        )
        t1 = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(summary["stopped"], "cap")
        self.assertEqual(summary["progress"], _PROGRESS)
        events = store.events()
        self.assertEqual(len(events), 1)
        self._check_belle_event(events[0], t0, t1)

    def test_follow_chain_16(self):
        """Example 16: a Ctrl-C mid-block keeps its printed alert."""
        store, rpc = _belle_setup()
        interrupted = InterruptAfter(rpc, 3)
        t0 = datetime.datetime.now(datetime.timezone.utc).replace(
            microsecond=0
        )
        got = []

        def sink(alerts):
            got.extend(alerts)

        with self.assertRaises(KeyboardInterrupt):
            follow_chain(interrupted, store, on_alerts=sink)
        t1 = datetime.datetime.now(datetime.timezone.utc)
        self.assertEqual(got, [_BELLE_ALERT])
        events = store.events()
        self.assertEqual(len(events), 1)
        self._check_belle_event(events[0], t0, t1)
        self.assertEqual(store.get_progress(), _PROGRESS)

    def test_follow_chain_17(self):
        """Example 17: no seeds, no upgrades -- no events, heartbeat only."""
        first = temp_store()
        first.set_progress(_PROGRESS)
        summary = follow_chain(FakeRpc(head=_HEAD), first, prices={})
        self.assertEqual(summary["blocks"], 1)
        self.assertEqual(first.events(), [])
        self.assertEqual(
            first.event_counts()["kinds"], {"ALERT": 0, "UPGRADE": 0}
        )
        self.assertIsNotNone(first.progress_at())

        second = temp_store()
        second.set_progress(_PROGRESS)
        summary = follow_chain(FakeRpc(head="0x18dea22"), second, prices={})
        self.assertEqual(summary["blocks"], 2)
        self.assertEqual(second.events(), [])
        self.assertEqual(
            second.event_counts()["kinds"], {"ALERT": 0, "UPGRADE": 0}
        )
        self.assertIsNotNone(second.progress_at())


if __name__ == "__main__":
    unittest.main()
