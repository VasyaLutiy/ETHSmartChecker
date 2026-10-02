"""Smoke tests for the phase-15 event recording in follow_chain.

Three checks only: an ALERT is recorded as an event on a complete
block, it is still recorded when the pass is interrupted inside the
block, and nothing is recorded when nothing was delivered. The full
contract lives in the judge cards and the acceptance probe.
"""

from ethsc import ingest
from tests.helpers import (
    FakeRpc,
    InterruptAfter,
    block_codes,
    block_receipts,
    load_hex,
    temp_store,
)

BELLE_ADDRESS = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
COPY_ADDRESS = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
PAIR_ADDRESS = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"


def _belle_store():
    store = temp_store()
    code_id = store.put_code(load_hex("code_belle.hex"))
    store.put_address(BELLE_ADDRESS, code_id, 1)
    store.add_seed(BELLE_ADDRESS, "BELLE honeypot")
    return store


def _belle_rpc(**kwargs):
    codes = {
        COPY_ADDRESS: "0x" + load_hex("code_belle_copy_1807090d.hex").hex(),
        PAIR_ADDRESS: "0x" + load_hex("code_weth9.hex").hex(),
    }
    receipts = [{"to": COPY_ADDRESS}, {"to": PAIR_ADDRESS}]
    return FakeRpc(codes=codes, receipts=receipts, head="0x18dea21",
                   **kwargs)


def test_alert_event_recorded_on_complete_block():
    store = _belle_store()
    received = []
    summary = ingest.follow_chain(_belle_rpc(), store,
                                  on_alerts=received.append)
    assert summary["blocks"] == 1
    assert len(received) == 1
    events = store.events()
    assert len(events) == 1
    event = events[0]
    assert event["kind"] == "ALERT"
    assert event["block"] == 26077729
    assert event["address"] == COPY_ADDRESS
    assert event["seed_address"] == BELLE_ADDRESS
    assert event["label"] == "BELLE honeypot"
    assert event["origin"] == "seen"
    assert event["old_impl"] is None
    assert event["at"].endswith("Z") and len(event["at"]) == 20
    # Events of a complete block are written before set_progress.
    assert store.get_progress() == 26077729
    assert store.progress_at() is not None


def test_interrupted_block_still_records_its_alert():
    store = _belle_store()
    rpc = InterruptAfter(_belle_rpc(), 3)
    raised = False
    try:
        ingest.follow_chain(rpc, store, on_alerts=lambda alerts: None)
    except KeyboardInterrupt:
        raised = True
    assert raised
    events = store.events()
    assert len(events) == 1
    assert events[0]["kind"] == "ALERT"
    assert events[0]["address"] == COPY_ADDRESS
    assert store.get_progress() is None


def test_no_events_when_nothing_delivered():
    store = temp_store()
    summary = ingest.follow_chain(FakeRpc(), store)
    assert summary["blocks"] == 1
    assert summary["alerts"] == []
    assert store.events() == []
    assert store.event_counts()["kinds"] == {"ALERT": 0, "UPGRADE": 0}
    assert len(block_receipts()) > 0 and len(block_codes()) == 206
