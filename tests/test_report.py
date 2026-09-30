"""Smoke tests for ethsc/report.py: at most five test functions.

The full contract is judged by the acceptance probe of phase 7.2 §3.3;
these tests cover one happy path per public function, one tolerant
case, and the import surface. No Fake classes: the store helpers come
from tests.helpers and the charts layer is stubbed with plain strings
passed through the charts= parameter, so matplotlib is never needed.
"""

import json
import os
import sys
import tempfile

from ethsc import report
from tests.helpers import block_store


def test_import_surface():
    """Import surface: names, fixed edges and chart keys."""
    assert report.ChartsUnavailable is not None, "ChartsUnavailable missing"
    assert len(report.FEATURES) == 6, "FEATURES must hold six features"
    assert report.FEATURES[0] == "bytecode_size", "wrong first feature"
    assert report.FEATURES[-1] == "is_proxy", "wrong last feature"
    assert len(report.SIZE_EDGES) == 7, "SIZE_EDGES length"
    assert len(report.SELECTOR_EDGES) == 8, "SELECTOR_EDGES length"
    assert len(report.CLUSTER_EDGES) == 8, "CLUSTER_EDGES length"
    assert len(report.CHART_KEYS) == 5, "CHART_KEYS length"


def test_collect_block_store():
    """Collect Report Data examples 1-5: the fixture store's numbers,
    the risk section included."""
    store = block_store()
    data = report.collect(store)
    assert sorted(data.keys()) == sorted(
        ["summary", "levels", "skeletons", "clusters", "codes",
         "ledger", "alerts", "spearman", "risk"]
    ), "collect must hold exactly the nine section keys"
    assert data["summary"]["addresses"] == 206, "addresses count"
    assert data["summary"]["codes"] == 130, "codes count"
    levels = data["levels"]
    assert levels["L0"]["clusters"] == 7, "L0 cluster count"
    assert levels["L0"]["addresses"] == 16, "L0 address count"
    assert levels["L1"]["clusters"] == 2, "L1 cluster count"
    assert levels["L1"]["addresses"] == 13, "L1 address count"
    assert levels["proxy"]["clusters"] == 6, "proxy cluster count"
    assert levels["proxy"]["addresses"] == 14, "proxy address count"
    assert abs(levels["L0"]["share"] - 16.0 / 147.0) < 1e-12, "L0 share"
    assert abs(levels["L1"]["share"] - 13.0 / 147.0) < 1e-12, "L1 share"
    assert abs(levels["proxy"]["share"] - 14.0 / 147.0) < 1e-12, "proxy share"
    assert levels["proxy_codes"] == 12, "proxy_codes"
    assert abs(levels["proxy_code_share"] - 12.0 / 130.0) < 1e-12, \
        "proxy_code_share"
    skeletons = data["skeletons"]
    assert skeletons["non_proxy_codes"] == 118, "non_proxy_codes"
    assert skeletons["unique_codes"] == 105, "unique_codes"
    assert abs(skeletons["unique_share"] - 105.0 / 118.0) < 1e-12, \
        "unique_share"
    assert skeletons["non_proxy_addresses"] == 127, "non_proxy_addresses"
    assert skeletons["unique_addresses"] == 114, "unique_addresses"
    assert abs(skeletons["unique_address_share"] - 114.0 / 127.0) < 1e-12, \
        "unique_address_share"
    assert data["clusters"]["histogram"]["counts"] == \
        [10, 2, 1, 2, 0, 0, 0, 0], "cluster histogram"
    assert len(data["clusters"]["top"]) == 15, "top cluster count"
    assert data["codes"]["size"]["min"] == 20, "size min"
    assert data["codes"]["size"]["median"] == 4442.5, "size median"
    assert data["codes"]["size"]["max"] == 24313, "size max"
    assert data["codes"]["size"]["histogram"]["counts"] == \
        [22, 5, 36, 19, 23, 25, 0], "size histogram"
    assert data["codes"]["selectors"]["min"] == 0, "selector min"
    assert data["codes"]["selectors"]["median"] == 12.5, "selector median"
    assert data["codes"]["selectors"]["max"] == 72, "selector max"
    assert data["codes"]["selectors"]["histogram"]["counts"] == \
        [28, 2, 3, 16, 27, 35, 17, 2], "selector histogram"
    assert data["ledger"] == {"days": [], "total": 0}, "empty ledger"
    assert data["spearman"]["n"] == 130, "spearman n"
    assert data["spearman"]["matrix"][0][0] == 1.0, "spearman diagonal"
    # alerts on a seeded store (example 4)
    seeded = block_store()
    seeded.add_seed(
        "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc", "UniV2 pair seed")
    alerts = report.collect(seeded)["alerts"]
    assert alerts["total"] == 4, "alert total"
    assert len(alerts["seeds"]) == 1, "one seed entry"
    entry = alerts["seeds"][0]
    assert entry["address"] == \
        "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc", "seed address"
    assert entry["label"] == "UniV2 pair seed", "seed label"
    assert entry["count"] == 4, "seed alert count"
    # risk section (example 5)
    risk = data["risk"]
    assert risk["selfdestruct"]["codes"] == 1, "selfdestruct codes"
    assert risk["selfdestruct"]["addresses"] == 1, "selfdestruct addresses"
    assert abs(risk["selfdestruct"]["code_share"] - 1.0 / 130.0) < 1e-12, \
        "selfdestruct code_share"
    assert abs(risk["selfdestruct"]["address_share"] - 1.0 / 147.0) < 1e-12, \
        "selfdestruct address_share"
    assert risk["mutable_delegatecall"]["codes"] == 29, "mut dc codes"
    assert risk["mutable_delegatecall"]["addresses"] == 33, "mut dc addresses"
    assert abs(risk["mutable_delegatecall"]["code_share"]
               - 29.0 / 130.0) < 1e-12, "mut dc code_share"
    assert abs(risk["mutable_delegatecall"]["address_share"]
               - 33.0 / 147.0) < 1e-12, "mut dc address_share"
    # empty database (example 6)
    from tests.helpers import temp_store
    empty = report.collect(temp_store())
    assert sorted(empty.keys()) == sorted(
        ["summary", "levels", "skeletons", "clusters", "codes",
         "ledger", "alerts", "spearman", "risk"]), "empty keys"
    assert empty["summary"]["addresses"] == 0, "empty addresses"
    assert empty["clusters"]["top"] == [], "empty clusters"
    assert empty["alerts"] == {"seeds": [], "total": 0}, "empty alerts"
    for name in report.RISK_FLAGS:
        assert empty["risk"][name]["codes"] == 0, "empty risk codes"
        assert empty["risk"][name]["code_share"] == 0.0, "empty code share"
        assert empty["risk"][name]["addresses"] == 0, "empty risk addresses"
        assert empty["risk"][name]["address_share"] == 0.0, \
            "empty address share"


def test_spearman_ranks_and_degenerate():
    """Spearman Matrix examples 3-4: average ranks, zero-variance and
    the fewer-than-two-rows case."""
    result = report.spearman([(1, 10), (2, 20), (2, 30), (3, 40)])
    assert result["n"] == 4, "n"
    assert abs(result["matrix"][0][1] - 0.9486832980505138) < 1e-12, \
        "tied coefficient"
    # a zero-variance feature is None across row and column, diagonal too
    degenerate = report.spearman([(1, 5), (2, 5), (3, 5)])
    assert degenerate["matrix"][1][1] is None, "degenerate diagonal"
    assert degenerate["matrix"][0][1] is None, "degenerate off-diagonal"
    assert degenerate["matrix"][1][0] is None, "degenerate symmetric cell"
    assert degenerate["matrix"][0][0] == 1.0, "non-degenerate diagonal"
    # fewer than two rows: the whole matrix is None
    tiny = report.spearman([(1, 2, 3, 4, 5, 6)])
    assert all(cell is None for row in tiny["matrix"] for cell in row), \
        "one row gives null everywhere"


def test_render_html_deterministic():
    """Render Report example 1: deterministic page, all five stubs
    inlined, no external resource, risk table present."""
    store = block_store()
    data = report.collect(store)
    stubs = dict((key, "<svg id=\"%s\"></svg>" % key)
                 for key in report.CHART_KEYS)
    first = report.render_html(data, stubs)
    second = report.render_html(data, stubs)
    assert first == second, "render_html must be deterministic"
    for key in report.CHART_KEYS:
        assert stubs[key] in first, "stub %s must appear verbatim" % key
    assert "<script" not in first, "no script tag"
    assert "<link" not in first, "no link tag"
    assert "<img" not in first, "no img tag"
    assert "http" not in first, "no http reference"
    assert "1.0000" in first, "the fixture matrix has no degenerate cell"
    assert "selfdestruct" in first, "risk table present"
    assert "mutable_delegatecall" in first, "risk table present"


def test_build_report_files_and_no_matplotlib():
    """Render Report examples 2-3: file paths, JSON round-trip and the
    tolerant case of a missing drawing layer."""
    store = block_store()
    directory = tempfile.mkdtemp(prefix="ethsc-report-test-")
    prefix = os.path.join(directory, "r")
    stubs = dict((key, "<svg id=\"%s\"></svg>" % key)
                 for key in report.CHART_KEYS)
    html_path, json_path = report.build_report(store, prefix, charts=stubs)
    html_path2, json_path2 = report.build_report(store, prefix, charts=stubs)
    assert html_path == html_path2 == prefix + ".html", "html path"
    assert json_path == json_path2 == prefix + ".json", "json path"
    with open(json_path, "r", encoding="utf-8") as handle:
        assert json.load(handle)["summary"]["codes"] == 130, "json content"

    # tolerant case: the drawing layer missing gives ChartsUnavailable
    # (the message names matplotlib) and no file is written.
    missing_prefix = os.path.join(directory, "missing")
    saved = sys.modules.get("ethsc.charts", False)
    sys.modules["ethsc.charts"] = None  # import raises ImportError
    try:
        report.build_report(store, missing_prefix)
        raise AssertionError("ChartsUnavailable was not raised")
    except report.ChartsUnavailable as error:
        assert "matplotlib" in str(error), "message must name matplotlib"
    finally:
        if saved is False:
            sys.modules.pop("ethsc.charts", None)
        else:
            sys.modules["ethsc.charts"] = saved
    assert not os.path.exists(missing_prefix + ".html"), "no html written"
    assert not os.path.exists(missing_prefix + ".json"), "no json written"
