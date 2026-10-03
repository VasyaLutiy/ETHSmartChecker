"""Phase 18 smoke tests for ethsc.cluster: strict seeds, interface_hits.

Import, one happy path per new behaviour and one tolerant case, all
offline over tests.helpers.belle_block_db(). The orchestrator's probe
judges completeness; this file is the smoke card only.
"""

from ethsc import cluster
from ethsc.fingerprint import ALERT_MIN, CODE_MIN, fingerprint
from ethsc.store import Store

from tests.helpers import belle_block_db, block_codes, load_hex

BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
COPY = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
SHIB = "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce"


def test_defaults_p18():
    assert ALERT_MIN == 0.75 and CODE_MIN == 0.6
    assert cluster.match_watchlist.__defaults__[-1] == ALERT_MIN
    assert cluster.recheck_watchlist.__defaults__[0] == ALERT_MIN
    assert cluster.interface_hits.__defaults__ == (ALERT_MIN, CODE_MIN)


def test_match_watchlist_strict_p18():
    store = Store(belle_block_db())
    store.add_seed(BELLE, "BELLE honeypot")
    shib_code = bytes.fromhex(block_codes()[SHIB][2:])
    # SHIB shares 11/15 selectors with BELLE: passes 0.7, below default.
    loose = cluster.match_watchlist(store, shib_code, min_score=0.7)
    assert len(loose) == 1 and loose[0]["seed_address"] == BELLE
    assert store.set_seed_strict(BELLE, True)
    # Strict: SHIB's code is unlike BELLE's (0.23 < CODE_MIN): no alert.
    assert cluster.match_watchlist(store, shib_code, min_score=0.7) == []
    # The copy shares the code (0.99 >= CODE_MIN): still alerts.
    copy = cluster.match_watchlist(store, load_hex(
        "code_belle_copy_1807090d.hex"), min_score=0.7)
    assert len(copy) == 1 and copy[0]["score"] == 13 / 15
    store.close()


def test_interface_hits_p18():
    store = Store(belle_block_db())
    belle = fingerprint(load_hex("code_belle.hex"))["code_id"]
    assert cluster.interface_hits(store, belle, min_score=0.5) == 8
    assert cluster.interface_hits(store, belle, min_score=0.7) == 1
    assert cluster.interface_hits(store, belle) == 0
    assert cluster.interface_hits(store, belle, code_min=1.0) == 4
    assert cluster.interface_hits(store, "00" * 32) == 0
    store.close()


def test_recheck_strict_p18():
    store = Store(belle_block_db())
    store.add_seed(BELLE, "BELLE honeypot")
    # Loose at 0.7: the four copies plus SHIB (0.7333 >= 0.7).
    assert len(cluster.recheck_watchlist(store, min_score=0.7)) == 5
    assert store.set_seed_strict(BELLE, True)
    # Strict: SHIB drops (code 0.23), the copies stay (code 0.99).
    strict_alerts = cluster.recheck_watchlist(store, min_score=0.7)
    assert len(strict_alerts) == 4
    for alert in strict_alerts:
        assert set(alert) == {
            "address", "seed_address", "label", "score", "origin"}
        assert alert["address"] != SHIB
    store.close()


def test_tolerant_p18():
    store = Store(belle_block_db())
    store.add_seed(BELLE, "BELLE")
    store.set_seed_strict(BELLE, True)
    # Empty code scores 0.0 < min_score: no alert, no exception.
    assert cluster.match_watchlist(store, b"") == []
    # A strict seed whose code_by_id gives None alerts on nothing.
    store.code_by_id = lambda code_id: None
    assert cluster.recheck_watchlist(store) == []
    store.close()
