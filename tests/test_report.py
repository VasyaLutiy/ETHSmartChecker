"""Smoke tests for ethsc.report: at most five test functions.

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
    assert report.ChartsUnavailable is not None
    assert len(report.FEATURES) == 6
    assert report.FEATURES[0] == "bytecode_size"
    assert report.FEATURES[-1] == "is_proxy"
    assert len(report.SIZE_EDGES) == 7
    assert len(report.SELECTOR_EDGES) == 8
    assert len(report.CLUSTER_EDGES) == 8
    assert len(report.CHART_KEYS) == 5


def test_collect_block_store():
    store = block_store()
    data = report.collect(store)
    assert sorted(data.keys()) == sorted(
        ["summary", "levels", "skeletons", "clusters", "codes",
         "ledger", "alerts", "spearman"]
    )
    assert data["summary"]["addresses"] == 206
    assert data["summary"]["codes"] == 130
    assert data["levels"]["L0"]["clusters"] == 7
    assert data["skeletons"]["non_proxy_codes"] == 118
    assert data["clusters"]["histogram"]["counts"] == [10, 2, 1, 2, 0, 0, 0, 0]
    assert len(data["clusters"]["top"]) == 15
    assert data["ledger"] == {"days": [], "total": 0}
    assert data["spearman"]["n"] == 130
    assert data["spearman"]["matrix"][0][0] == 1.0
    assert data["codes"]["size"]["median"] == 4442.5


def test_spearman_ranks_and_degenerate():
    result = report.spearman([(1, 10), (2, 20), (2, 30), (3, 40)])
    assert result["n"] == 4
    assert abs(result["matrix"][0][1] - 0.9486832980505138) < 1e-12
    # a zero-variance feature is None across row and column, diagonal too
    degenerate = report.spearman([(1, 5), (2, 5), (3, 5)])
    assert degenerate["matrix"][1][1] is None
    assert degenerate["matrix"][0][1] is None
    assert degenerate["matrix"][1][0] is None
    assert degenerate["matrix"][0][0] == 1.0
    # fewer than two rows: the whole matrix is None
    tiny = report.spearman([(1, 2, 3, 4, 5, 6)])
    assert all(cell is None for row in tiny["matrix"] for cell in row)


def test_render_html_deterministic():
    store = block_store()
    data = report.collect(store)
    stubs = dict((key, "<svg id=\"%s\"></svg>" % key)
                 for key in report.CHART_KEYS)
    first = report.render_html(data, stubs)
    second = report.render_html(data, stubs)
    assert first == second
    for key in report.CHART_KEYS:
        assert stubs[key] in first
    assert "<script" not in first
    assert "<link" not in first
    assert "<img" not in first
    assert "http" not in first
    assert "1.0000" in first  # the fixture matrix has no degenerate cell


def test_build_report_files_and_no_matplotlib():
    store = block_store()
    directory = tempfile.mkdtemp(prefix="ethsc-report-test-")
    prefix = os.path.join(directory, "r")
    stubs = dict((key, "<svg id=\"%s\"></svg>" % key)
                 for key in report.CHART_KEYS)
    html_path, json_path = report.build_report(store, prefix, charts=stubs)
    html_path2, json_path2 = report.build_report(store, prefix, charts=stubs)
    assert html_path == html_path2 == prefix + ".html"
    assert json_path == json_path2 == prefix + ".json"
    with open(json_path, "r", encoding="utf-8") as handle:
        assert json.load(handle)["summary"]["codes"] == 130

    # tolerant case: the drawing layer missing gives ChartsUnavailable
    # (the message names matplotlib) and no file is written.
    missing_prefix = os.path.join(directory, "missing")
    saved = sys.modules.get("ethsc.charts", False)
    sys.modules["ethsc.charts"] = None  # import raises ImportError
    try:
        report.build_report(store, missing_prefix)
        raise AssertionError("ChartsUnavailable was not raised")
    except report.ChartsUnavailable as error:
        assert "matplotlib" in str(error)
    finally:
        if saved is False:
            sys.modules.pop("ethsc.charts", None)
        else:
            sys.modules["ethsc.charts"] = saved
    assert not os.path.exists(missing_prefix + ".html")
    assert not os.path.exists(missing_prefix + ".json")
