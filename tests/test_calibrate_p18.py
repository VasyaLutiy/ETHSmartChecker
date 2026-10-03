"""Smoke tests for ethsc.calibrate (phase 18).

An import, one happy path per new function, one tolerant case. The
completeness probe is the orchestrator's; this file only checks that
the module is importable and answers scalars as the Contour pins them.
"""

import pytest

from ethsc import calibrate
from ethsc.calibrate import DEFAULT_GRID, evaluate, load_labels, parse_grid
from ethsc.store import Store
from tests.helpers import belle_block_db, write_labels

BELLE = "0x34C6211621F2763C60EB007DC2AE91090A2D22F6"
COPY = "0x1807090DD15A6F58E00FD769E32EBF20EE610385"
SHIB = "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce"
UNIV2 = "0xb4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc"
PAIR = "0x22052A1A0F5A3D2839D71C458F177E68B0E73963"
UNKNOWN = "0x" + "99" * 20


def test_constants_and_parse_grid():
    assert calibrate.DEFAULT_GRID == (0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0)
    assert parse_grid("0.7,0.75, 0.8") == (0.7, 0.75, 0.8)
    assert parse_grid("1,0") == (1.0, 0.0)
    with pytest.raises(ValueError):
        parse_grid("")
    with pytest.raises(ValueError):
        parse_grid("1.5")


def test_load_labels():
    path = write_labels({"positives": [[BELLE, COPY]], "note": "x"})
    labels = load_labels(path)
    assert sorted(labels) == ["negatives", "positives", "strict"]
    assert labels["positives"] == [[BELLE.lower(), COPY.lower()]]
    assert labels["negatives"] == []
    assert labels["strict"] == []
    bad = write_labels("[]")
    with pytest.raises(ValueError):
        load_labels(bad)
    with pytest.raises(ValueError):
        load_labels(path + ".missing")


def _labels(strict):
    return {
        "positives": [[BELLE, COPY], [UNIV2, PAIR]],
        "negatives": [[BELLE, SHIB]],
        "strict": strict,
    }


def test_evaluate_happy():
    path = belle_block_db()
    store = Store(path)
    result = evaluate(store, _labels([]), (0.75,))
    assert result["missing"] == []
    assert result["benign_total"] == 131
    row = result["rows"][0]
    assert row["threshold"] == 0.75
    assert row["recall"] == 1.0
    assert row["negatives"] == 0
    # The interface-only alerts are a subset of the benign passes.
    assert 0 <= row["interface_only"] <= row["benign"]
    # Loose at 0.7, the SHIB negative passes both ways.
    loose = evaluate(store, _labels([]), (0.7,))
    assert loose["rows"][0]["negatives"] == 2
    store.close()


def test_evaluate_strict_seed():
    path = belle_block_db()
    store = Store(path)
    strict = evaluate(store, _labels([BELLE]), (0.7,))
    assert strict["rows"][0]["recall"] == 1.0
    # A strict BELLE blocks SHIB as the seed (code similarity 0.23 < 0.6);
    # SHIB as the seed against BELLE is loose and still passes.
    assert strict["rows"][0]["negatives"] == 1
    store.close()


def test_evaluate_tolerant():
    path = belle_block_db()
    store = Store(path)
    empty = evaluate(store, {}, (0.5, 1.0))
    assert empty["missing"] == []
    assert empty["benign_total"] == 135
    assert [row["benign"] for row in empty["rows"]] == [0, 0]
    labels = {"positives": [[BELLE, UNKNOWN]], "negatives": [],
              "strict": []}
    result = evaluate(store, labels, (0.75,))
    assert result["missing"] == [UNKNOWN]
    row = result["rows"][0]
    assert row["recall"] == 0.0
    assert row["negatives"] == 0
    assert 0 <= row["benign"] <= 4
    assert result["benign_total"] == 134
    store.close()
