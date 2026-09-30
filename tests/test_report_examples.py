# tests/test_report_examples.py
# -*- coding: utf-8 -*-
"""Judge tests: one test per Contour example of the report group.

Twelve tests -- five of Collect Report Data, four of Spearman Matrix,
three of Render Report. The block base is loaded from tests.helpers
(block_store, the fixture of block 26077729: 206 addresses, 147 with
code, 130 codes); no network, no Fake classes, and matplotlib is never
imported: the numbers are read out of the collected payload and the
charts are stubs, never a picture.
"""

import json
import os
import sys
import tempfile

from ethsc import report
from tests.helpers import block_store, load_hex, temp_store


STUBS = {
    "cluster_sizes": "<svg><text>stub-cluster_sizes</text></svg>",
    "top_clusters": "<svg><text>stub-top_clusters</text></svg>",
    "code_sizes": "<svg><text>stub-code_sizes</text></svg>",
    "selector_counts": "<svg><text>stub-selector_counts</text></svg>",
    "spearman": "<svg><text>stub-spearman</text></svg>",
}

# The Contour pins the six coefficients of the block base at four
# decimal places from an independent computation, so the comparison is
# against the printed figures at the precision they are given.
COEF_TOL = 5e-5

# Feature order fixed by the Contour.
SIZE, OPCODES, SELECTORS, ADDRESSES, L1FAMILY, ISPROXY = range(6)


def _approx(value, expected, tol=1e-9):
    return value is not None and abs(value - expected) <= tol


def _coef(matrix, i, j):
    value = matrix[i][j]
    assert value is not None, "matrix[%d][%d] is defined, not n/a" % (i, j)
    return value


def _proxy_free_store():
    """A base of non-proxy codes only, built from the named fixtures.

    Nine addresses over eight distinct codes; the UniswapV3Pool pair
    shares a skeleton (l1_family_size 2) and the UniswapV2Pair code has
    two addresses, so every non-proxy feature has variance and only
    is_proxy is degenerate.
    """
    store = temp_store()
    placements = [
        ("0x" + "a1" * 20, "code_weth9.hex"),
        ("0x" + "a2" * 20, "code_usdt.hex"),
        ("0x" + "a3" * 20, "code_univ2_usdc_weth.hex"),
        ("0x" + "a4" * 20, "code_univ2_usdc_weth.hex"),
        ("0x" + "a5" * 20, "code_univ3_usdc_weth_005.hex"),
        ("0x" + "a6" * 20, "code_univ3_pool_e0554a47.hex"),
        ("0x" + "a7" * 20, "code_launchtoken_4e67db19.hex"),
        ("0x" + "a8" * 20, "code_launchtoken_40676634.hex"),
        ("0x" + "a9" * 20, "code_belle.hex"),
    ]
    for address, name in placements:
        code_id = store.put_code(load_hex(name))
        store.put_address(address, code_id, 26077729)
    return store


# -- Collect Report Data -----------------------------------------------------


def test_example_levels_of_block_base():
    """levels: 7/16, 2/13, 6/14 over 147 with code; 12 proxy codes of 130."""
    data = report.collect(block_store())
    levels = data["levels"]
    what = "levels of the counted base (206 addresses, 147 with code)"
    assert levels["L0"]["clusters"] == 7, what + ": L0 clusters 7"
    assert levels["L1"]["clusters"] == 2, what + ": L1 clusters 2"
    assert levels["proxy"]["clusters"] == 6, what + ": proxy clusters 6"
    assert levels["L0"]["addresses"] == 16, what + ": L0 addresses 16"
    assert levels["L1"]["addresses"] == 13, what + ": L1 addresses 13"
    assert levels["proxy"]["addresses"] == 14, what + ": proxy addresses 14"
    assert _approx(levels["L0"]["share"], 16 / 147), what + ": L0 share 16/147"
    assert _approx(levels["L1"]["share"], 13 / 147), what + ": L1 share 13/147"
    assert _approx(levels["proxy"]["share"], 14 / 147), \
        what + ": proxy share 14/147"
    assert levels["proxy_codes"] == 12, what + ": proxy_codes 12"
    assert _approx(levels["proxy_code_share"], 12 / 130), \
        what + ": proxy_code_share 12/130"


def test_example_skeleton_shares():
    """skeletons: 105/118 = 0.8898 by code_id, 114/127 = 0.8976 by address."""
    data = report.collect(block_store())
    sk = data["skeletons"]
    what = "skeleton section of the counted base"
    assert sk["non_proxy_codes"] == 118, what + ": 118 non-proxy codes"
    assert sk["unique_codes"] == 105, what + ": 105 unique codes"
    assert _approx(sk["unique_share"], 105 / 118), \
        what + ": unique share by code_id is 105/118 = 0.8898"
    assert sk["non_proxy_addresses"] == 127, what + ": 127 non-proxy addresses"
    assert sk["unique_addresses"] == 114, what + ": 114 unique addresses"
    assert _approx(sk["unique_address_share"], 114 / 127), \
        what + ": unique share by address is 114/127 = 0.8976"


def test_example_code_distributions():
    """codes: size median 4442.5, selector median 12.5, the two histograms."""
    data = report.collect(block_store())
    size = data["codes"]["size"]
    sel = data["codes"]["selectors"]
    what = "code distributions of the counted base (130 codes)"
    assert size["min"] == 20, what + ": size min 20"
    assert size["median"] == 4442.5, \
        what + ": size median 4442.5 (mean of 4369 and 4516)"
    assert size["max"] == 24313, what + ": size max 24313"
    assert size["histogram"]["edges"] == report.SIZE_EDGES, \
        what + ": size edges are the fixed ones"
    assert size["histogram"]["counts"] == [22, 5, 36, 19, 23, 25, 0], \
        what + ": size histogram [22, 5, 36, 19, 23, 25, 0]"
    assert sel["min"] == 0, what + ": selector min 0"
    assert sel["median"] == 12.5, \
        what + ": selector median 12.5 (mean of 12 and 13)"
    assert sel["max"] == 72, what + ": selector max 72"
    assert sel["histogram"]["edges"] == report.SELECTOR_EDGES, \
        what + ": selector edges are the fixed ones"
    assert sel["histogram"]["counts"] == [28, 2, 3, 16, 27, 35, 17, 2], \
        what + ": selector histogram [28, 2, 3, 16, 27, 35, 17, 2]"
    assert isinstance(size["median"], float) and \
        isinstance(sel["median"], float), "both medians are floats"


def test_example_alerts_univ2_seed():
    """seed 0xb4e16d01... labelled UniV2 pair seed: 4 alerts, one seed entry."""
    store = block_store()
    seed = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
    store.add_seed(seed, "UniV2 pair seed")
    alerts = report.collect(store)["alerts"]
    what = "alerts of the UniV2 pair seed on the counted base"
    assert alerts["total"] == 4, what + ": 4 alerts in total"
    assert len(alerts["seeds"]) == 1, what + ": one seed entry"
    entry = alerts["seeds"][0]
    assert entry["address"] == seed, what + ": the entry is the seed address"
    assert entry["label"] == "UniV2 pair seed", what + ": label kept"
    assert entry["count"] == 4, what + ": count 4"


def test_example_empty_database():
    """an empty database: eight keys, zeros, empty lists, no exception."""
    data = report.collect(temp_store())
    what = "collect on an empty database"
    assert sorted(data) == sorted(
        ["summary", "levels", "skeletons", "clusters", "codes",
         "ledger", "alerts", "spearman"]), what + ": exactly eight keys"
    summary = data["summary"]
    for key in ("addresses", "addresses_with_code", "addresses_without_code",
                "codes", "blocks"):
        assert summary[key] == 0, what + ": summary %s is 0" % key
    assert data["ledger"] == {"days": [], "total": 0}, \
        what + ": ledger is empty"
    assert data["clusters"]["top"] == [], what + ": no top clusters"
    assert data["alerts"]["seeds"] == [] and data["alerts"]["total"] == 0, \
        what + ": no alerts"
    matrix = data["spearman"]["matrix"]
    assert data["spearman"]["n"] == 0, what + ": n 0"
    assert all(cell is None for row in matrix for cell in row), \
        what + ": the whole matrix is None"


# -- Spearman Matrix ---------------------------------------------------------


def test_example_spearman_block_base():
    """the six coefficients of the block base, symmetric, 1.0 diagonal."""
    sp = report.collect(block_store())["spearman"]
    what = "Spearman matrix of the counted base (n = 130)"
    assert sp["n"] == 130, what + ": n 130"
    assert tuple(sp["features"]) == report.FEATURES, \
        what + ": features in the fixed order"
    matrix = sp["matrix"]
    n = len(matrix)
    for i in range(n):
        for j in range(n):
            if i == j:
                assert _approx(matrix[i][j], 1.0), \
                    what + ": diagonal is 1.0 at %d" % i
            else:
                assert matrix[i][j] == matrix[j][i], \
                    what + ": symmetric at (%d, %d)" % (i, j)
    assert _approx(_coef(matrix, SIZE, OPCODES), 0.9893, COEF_TOL), \
        what + ": bytecode_size~opcode_count 0.9893"
    assert _approx(_coef(matrix, SIZE, SELECTORS), 0.8422, COEF_TOL), \
        what + ": bytecode_size~selector_count 0.8422"
    assert _approx(_coef(matrix, SIZE, ADDRESSES), -0.3368, COEF_TOL), \
        what + ": bytecode_size~address_count -0.3368"
    assert _approx(_coef(matrix, OPCODES, SELECTORS), 0.8559, COEF_TOL), \
        what + ": opcode_count~selector_count 0.8559"
    assert _approx(_coef(matrix, ADDRESSES, ISPROXY), 0.4289, COEF_TOL), \
        what + ": address_count~is_proxy 0.4289"
    assert _approx(_coef(matrix, L1FAMILY, ISPROXY), 0.2326, COEF_TOL), \
        what + ": l1_family_size~is_proxy 0.2326"


def test_example_tie_blind_shortcut_wrong():
    """the shortcut gives 0.1898 and 0.8509; the matrix must not."""
    sp = report.collect(block_store())["spearman"]
    matrix = sp["matrix"]
    by_size = _coef(matrix, SIZE, ADDRESSES)
    addr_proxy = _coef(matrix, ADDRESSES, ISPROXY)
    assert _approx(by_size, -0.3368, COEF_TOL), \
        "bytecode_size~address_count is -0.3368 with average ranks"
    assert _approx(addr_proxy, 0.4289, COEF_TOL), \
        "address_count~is_proxy is 0.4289 with average ranks"
    assert not _approx(by_size, 0.1898, COEF_TOL), \
        "the tie-blind shortcut's 0.1898 for bytecode_size~address_count " \
        "must not appear"
    assert not _approx(addr_proxy, 0.8509, COEF_TOL), \
        "the tie-blind shortcut's 0.8509 for address_count~is_proxy " \
        "must not appear"


def test_example_four_row_hand_case():
    """[(1,10),(2,20),(2,30),(3,40)] with average ranks gives
    0.9486832980505138 (ranks [1.0, 2.5, 2.5, 4.0])."""
    result = report.spearman([(1, 10), (2, 20), (2, 30), (3, 40)])
    what = "the four-row hand case"
    assert result["n"] == 4, what + ": n 4"
    assert result["features"] == ["f0", "f1"], what + ": generic names"
    value = result["matrix"][0][1]
    assert value is not None and \
        abs(value - 0.9486832980505138) <= 1e-12, \
        what + ": the coefficient is 0.9486832980505138"
    assert abs(result["matrix"][1][0] - value) == 0.0, what + ": symmetric"


def test_example_proxy_free_base_null_row():
    """a base without proxies: the is_proxy row and column are None
    including the diagonal; the other features keep their coefficients
    and their diagonal 1.0."""
    sp = report.collect(_proxy_free_store())["spearman"]
    matrix = sp["matrix"]
    what = "Spearman matrix of a proxy-free base"
    assert sp["n"] == 8, what + ": n is the number of codes (8)"
    for j in range(len(report.FEATURES)):
        assert matrix[ISPROXY][j] is None, \
            what + ": the is_proxy row is None at column %d" % j
        assert matrix[j][ISPROXY] is None, \
            what + ": the is_proxy column is None at row %d" % j
    for i in range(len(report.FEATURES)):
        if i == ISPROXY:
            continue
        for j in range(len(report.FEATURES)):
            if j == ISPROXY:
                continue
            assert matrix[i][j] is not None, \
                "non-proxy features keep their coefficients at (%d, %d)" \
                % (i, j)
            if i == j:
                assert _approx(matrix[i][j], 1.0), \
                    "non-proxy features keep their diagonal 1.0 at %d" % i


# -- Render Report -----------------------------------------------------------


def test_example_page_deterministic_and_self_contained():
    """render_html twice is equal, all five stubs in it, and no
    script, link, img or http anywhere."""
    data = report.collect(block_store())
    first = report.render_html(data, STUBS)
    second = report.render_html(data, STUBS)
    assert first == second, "two renders of the same data are equal"
    for key in report.CHART_KEYS:
        assert STUBS[key] in first, "the %s stub appears in the page" % key
    for forbidden in ("<script", "<link", "<img", "http"):
        assert forbidden not in first, \
            "%r does not appear in the page" % forbidden


def test_example_files_byte_identical_and_json_matches_collect():
    """build_report twice: byte-identical files, json equals collect."""
    store = block_store()
    directory = tempfile.mkdtemp(prefix="ethsc-report-examples-")
    prefix = os.path.join(directory, "r")
    html_path, json_path = report.build_report(store, prefix, charts=STUBS)
    with open(html_path, "rb") as handle:
        html_first = handle.read()
    with open(json_path, "rb") as handle:
        json_first = handle.read()
    html_path2, json_path2 = report.build_report(store, prefix, charts=STUBS)
    assert (html_path, json_path) == (prefix + ".html", prefix + ".json"), \
        "the returned paths are prefix + .html and prefix + .json"
    with open(html_path2, "rb") as handle:
        assert handle.read() == html_first, "the html is byte-identical"
    with open(json_path2, "rb") as handle:
        assert handle.read() == json_first, "the json is byte-identical"
    with open(json_path2, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    assert loaded == report.collect(store), \
        "the json holds exactly what collect returns"


def test_example_charts_unavailable_writes_nothing():
    """a drawing layer that will not import: ChartsUnavailable, no file."""
    store = block_store()
    directory = tempfile.mkdtemp(prefix="ethsc-report-examples-")
    prefix = os.path.join(directory, "r")
    saved = sys.modules.pop("ethsc.charts", None)
    sys.modules["ethsc.charts"] = None  # None in sys.modules -> ImportError
    try:
        raised = False
        try:
            report.build_report(store, prefix)
        except report.ChartsUnavailable:
            raised = True
        assert raised, "ChartsUnavailable is raised"
    finally:
        if saved is None:
            sys.modules.pop("ethsc.charts", None)
        else:
            sys.modules["ethsc.charts"] = saved
    assert os.listdir(directory) == [], "no file was written"
