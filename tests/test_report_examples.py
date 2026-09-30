# tests/test_report_examples.py
# -*- coding: utf-8 -*-
"""Example-based tests for ethsc/report.py (docs/TASK_PHASE8.md).

One test per Contour example (some large examples are split into two
tests, each naming the example it checks). The block base is loaded
from tests.helpers.block_store (the fixture of block 26077729: 206
addresses, 147 with code, 130 codes). No network is opened, no Fake
classes are defined here, and matplotlib is never imported by the
tests: the numbers are read out of the collected payload and the
charts are stubs, never a picture.
"""

import json
import os
import sys
import tempfile
import unittest

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

SIZE, OPCODES, SELECTORS, ADDRESSES, L1FAMILY, ISPROXY = range(6)


def _coef(matrix, i, j, msg):
    value = matrix[i][j]
    assert value is not None, msg
    return value


class CollectReportDataTests(unittest.TestCase):
    """Collect Report Data, examples 1 to 6."""

    def test_collect_levels_block_base(self):
        """Collect Report Data example 1: levels over the block base."""
        store = block_store()
        data = report.collect(store)
        levels = data["levels"]
        # L0 7 clusters over 16 addresses, L1 2 over 13, proxy 6 over 14.
        self.assertEqual(levels["L0"]["clusters"], 7,
                         msg="L0 cluster count")
        self.assertEqual(levels["L1"]["clusters"], 2,
                         msg="L1 cluster count")
        self.assertEqual(levels["proxy"]["clusters"], 6,
                         msg="proxy cluster count")
        self.assertEqual(levels["L0"]["addresses"], 16, msg="L0 addresses")
        self.assertEqual(levels["L1"]["addresses"], 13, msg="L1 addresses")
        self.assertEqual(levels["proxy"]["addresses"], 14,
                         msg="proxy addresses")
        # shares 16/147, 13/147 and 14/147
        self.assertAlmostEqual(levels["L0"]["share"], 16.0 / 147.0,
                               places=12, msg="L0 share is 16/147")
        self.assertAlmostEqual(levels["L1"]["share"], 13.0 / 147.0,
                               places=12, msg="L1 share is 13/147")
        self.assertAlmostEqual(levels["proxy"]["share"], 14.0 / 147.0,
                               places=12, msg="proxy share is 14/147")
        self.assertEqual(levels["proxy_codes"], 12, msg="proxy codes")
        # proxy_code_share 12/130
        self.assertAlmostEqual(levels["proxy_code_share"], 12.0 / 130.0,
                               places=12, msg="proxy_code_share is 12/130")

    def test_collect_skeletons_block_base(self):
        """Collect Report Data example 2: skeleton uniqueness, block base."""
        store = block_store()
        data = report.collect(store)
        skeletons = data["skeletons"]
        self.assertEqual(skeletons["non_proxy_codes"], 118,
                         msg="non_proxy_codes")
        self.assertEqual(skeletons["unique_codes"], 105,
                         msg="unique_codes")
        # unique_share 105/118 = 0.8898
        self.assertAlmostEqual(skeletons["unique_share"], 105.0 / 118.0,
                               places=12,
                               msg="unique_share is 105/118 = 0.8898")
        self.assertEqual(skeletons["non_proxy_addresses"], 127,
                         msg="non_proxy_addresses")
        self.assertEqual(skeletons["unique_addresses"], 114,
                         msg="unique_addresses")
        # unique_address_share 114/127 = 0.8976
        self.assertAlmostEqual(
            skeletons["unique_address_share"], 114.0 / 127.0, places=12,
            msg="unique_address_share is 114/127 = 0.8976")

    def test_collect_code_sizes_block_base(self):
        """Collect Report Data example 3 (sizes): bytecode size stats."""
        store = block_store()
        data = report.collect(store)
        size = data["codes"]["size"]
        self.assertEqual(size["min"], 20, msg="size min")
        # median 4442.5 (4369 and 4516 averaged)
        self.assertEqual(size["median"], 4442.5, msg="size median 4442.5")
        self.assertEqual(size["max"], 24313, msg="size max")
        self.assertEqual(size["histogram"]["counts"],
                         [22, 5, 36, 19, 23, 25, 0], msg="size histogram")

    def test_collect_selector_counts_block_base(self):
        """Collect Report Data example 3 (selectors): selector stats."""
        store = block_store()
        data = report.collect(store)
        selectors = data["codes"]["selectors"]
        self.assertEqual(selectors["min"], 0, msg="selector min")
        # median 12.5 (12 and 13 averaged)
        self.assertEqual(selectors["median"], 12.5,
                         msg="selector median 12.5")
        self.assertEqual(selectors["max"], 72, msg="selector max")
        self.assertEqual(selectors["histogram"]["counts"],
                         [28, 2, 3, 16, 27, 35, 17, 2],
                         msg="selector histogram")

    def test_collect_alerts_block_base(self):
        """Collect Report Data example 4: alerts folded per seed."""
        store = block_store()
        store.add_seed("0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
                       "UniV2 pair seed")
        data = report.collect(store)
        alerts = data["alerts"]
        self.assertEqual(alerts["total"], 4, msg="alerts total")
        self.assertEqual(len(alerts["seeds"]), 1, msg="one seed entry")
        seed = alerts["seeds"][0]
        self.assertEqual(seed["address"],
                         "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
                         msg="the seed address")
        self.assertEqual(seed["label"], "UniV2 pair seed",
                         msg="the seed label")
        self.assertEqual(seed["count"], 4, msg="four alerts of the seed")

    def test_collect_risk_block_base(self):
        """Collect Report Data example 5: risk flags over the block base."""
        store = block_store()
        data = report.collect(store)
        risk = data["risk"]
        # selfdestruct codes 1, addresses 1, code_share 1/130,
        # address_share 1/147
        self.assertEqual(risk["selfdestruct"]["codes"], 1,
                         msg="selfdestruct codes")
        self.assertEqual(risk["selfdestruct"]["addresses"], 1,
                         msg="selfdestruct addresses")
        self.assertAlmostEqual(risk["selfdestruct"]["code_share"],
                               1.0 / 130.0, places=12,
                               msg="selfdestruct code_share is 1/130")
        self.assertAlmostEqual(risk["selfdestruct"]["address_share"],
                               1.0 / 147.0, places=12,
                               msg="selfdestruct address_share is 1/147")
        # mutable_delegatecall codes 29, addresses 33, code_share 29/130,
        # address_share 33/147
        self.assertEqual(risk["mutable_delegatecall"]["codes"], 29,
                         msg="mutable_delegatecall codes")
        self.assertEqual(risk["mutable_delegatecall"]["addresses"], 33,
                         msg="mutable_delegatecall addresses")
        self.assertAlmostEqual(risk["mutable_delegatecall"]["code_share"],
                               29.0 / 130.0, places=12,
                               msg="mutable_delegatecall code_share is 29/130")
        self.assertAlmostEqual(
            risk["mutable_delegatecall"]["address_share"], 33.0 / 147.0,
            places=12, msg="mutable_delegatecall address_share is 33/147")

    def test_collect_empty_structure(self):
        """Collect Report Data example 6: an empty database, structure."""
        store = temp_store()
        data = report.collect(store)
        self.assertEqual(sorted(data.keys()), sorted([
            "summary", "levels", "skeletons", "clusters", "codes",
            "ledger", "alerts", "spearman", "risk"]),
            msg="all nine keys present")
        self.assertEqual(data["summary"], {
            "addresses": 0, "addresses_with_code": 0,
            "addresses_without_code": 0, "codes": 0, "blocks": 0},
            msg="summary all zeros")
        self.assertEqual(data["clusters"]["top"], [],
                         msg="cluster list empty")
        self.assertEqual(data["ledger"]["days"], [], msg="ledger empty")
        self.assertEqual(data["alerts"]["seeds"], [], msg="alerts empty")

    def test_collect_empty_risk(self):
        """Collect Report Data example 6: an empty database, risk zeros."""
        store = temp_store()
        data = report.collect(store)
        for name in ("selfdestruct", "mutable_delegatecall"):
            entry = data["risk"][name]
            self.assertEqual(entry["codes"], 0,
                             msg="%s codes 0 on an empty base" % name)
            self.assertEqual(entry["addresses"], 0,
                             msg="%s addresses 0 on an empty base" % name)
            self.assertEqual(entry["code_share"], 0.0,
                             msg="%s code_share 0.0" % name)
            self.assertEqual(entry["address_share"], 0.0,
                             msg="%s address_share 0.0" % name)


class SpearmanMatrixTests(unittest.TestCase):
    """Spearman Matrix, examples 1 to 4."""

    def test_spearman_block_base(self):
        """Spearman Matrix example 1: the six coefficients, block base."""
        store = block_store()
        sp = report.collect(store)["spearman"]
        self.assertEqual(sp["n"], 130, msg="n = 130 codes")
        matrix = sp["matrix"]
        expected = {
            (SIZE, OPCODES): 0.9893,
            (SIZE, SELECTORS): 0.8422,
            (SIZE, ADDRESSES): -0.3368,
            (OPCODES, SELECTORS): 0.8559,
            (ADDRESSES, ISPROXY): 0.4289,
            (L1FAMILY, ISPROXY): 0.2326,
        }
        for (i, j), value in expected.items():
            coefficient = _coef(matrix, i, j,
                                "matrix[%d][%d] is defined" % (i, j))
            self.assertAlmostEqual(coefficient, value, delta=COEF_TOL,
                                   msg="matrix[%d][%d] = %.4f" % (i, j, value))

    def test_spearman_tie_handling(self):
        """Spearman Matrix example 2: correct tie handling, not the shortcut."""
        store = block_store()
        matrix = report.collect(store)["spearman"]["matrix"]
        by_address = _coef(matrix, SIZE, ADDRESSES,
                           "bytecode_size~address_count is defined")
        proxy = _coef(matrix, ADDRESSES, ISPROXY,
                      "address_count~is_proxy is defined")
        # the correct values -0.3368 and 0.4289; the tie-blind shortcut
        # would give 0.1898 and 0.8509, which must not appear
        self.assertAlmostEqual(by_address, -0.3368, delta=COEF_TOL,
                               msg="bytecode_size~address_count is -0.3368")
        self.assertAlmostEqual(proxy, 0.4289, delta=COEF_TOL,
                               msg="address_count~is_proxy is 0.4289")
        self.assertFalse(abs(by_address - 0.1898) < 1e-3,
                         msg="the shortcut value 0.1898 is not used")
        self.assertFalse(abs(proxy - 0.8509) < 1e-3,
                         msg="the shortcut value 0.8509 is not used")

    def test_spearman_hand_rows(self):
        """Spearman Matrix example 3: the four-row hand case."""
        result = report.spearman([(1, 10), (2, 20), (2, 30), (3, 40)])
        self.assertEqual(result["n"], 4, msg="n = 4 rows")
        coefficient = _coef(result["matrix"], 0, 1,
                            "the coefficient is defined")
        self.assertEqual(coefficient, 0.9486832980505138,
                         msg="the four-row coefficient")
        self.assertEqual(result["matrix"][0][0], 1.0,
                         msg="diagonal is 1.0")
        self.assertEqual(result["matrix"][1][0],
                         result["matrix"][0][1],
                         msg="the matrix is symmetric")

    def test_spearman_no_proxy_base(self):
        """Spearman Matrix example 4: a base of non-proxy codes only."""
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
        ]
        block = 26077729
        for address, fixture in placements:
            code_id = store.put_code(load_hex(fixture))
            store.put_address(address, code_id, block)
        sp = report.collect(store)["spearman"]
        matrix = sp["matrix"]
        for i in range(6):
            self.assertIsNone(matrix[ISPROXY][i],
                              msg="is_proxy column cell %d is null" % i)
            self.assertIsNone(matrix[i][ISPROXY],
                              msg="is_proxy row cell %d is null" % i)
        # the other four features keep their coefficients
        self.assertIsNotNone(matrix[SIZE][OPCODES],
                             msg="bytecode_size~opcode_count stays defined")
        self.assertIsNotNone(matrix[SIZE][SELECTORS],
                             msg="bytecode_size~selector_count stays defined")
        self.assertIsNotNone(matrix[OPCODES][SELECTORS],
                             msg="opcode_count~selector_count stays defined")
        self.assertIsNotNone(matrix[SIZE][ADDRESSES],
                             msg="bytecode_size~address_count stays defined")


class RenderReportTests(unittest.TestCase):
    """Render Report, examples 1 to 3."""

    def test_render_html_stubs(self):
        """Render Report example 1: render_html with stub SVGs, twice."""
        store = block_store()
        data = report.collect(store)
        page1 = report.render_html(data, STUBS)
        page2 = report.render_html(data, STUBS)
        self.assertEqual(page1, page2, msg="the two strings are equal")
        for key in ("cluster_sizes", "top_clusters", "code_sizes",
                    "selector_counts", "spearman"):
            self.assertIn("stub-" + key, page1,
                          msg="the %s stub appears in the page" % key)
        for banned in ("<script", "<link", "<img", "http"):
            self.assertNotIn(banned, page1,
                             msg="%s does not appear in the page" % banned)

    def test_build_report_deterministic(self):
        """Render Report example 2: build_report twice, byte-identical."""
        try:
            import ethsc.charts  # noqa: F401
        except ImportError:
            self.skipTest("matplotlib is not installed")
        store = block_store()
        directory = tempfile.mkdtemp(prefix="ethsc-report-test-")
        prefix = os.path.join(directory, "r")
        html1, json1 = report.build_report(store, prefix)
        html2, json2 = report.build_report(store, prefix)
        self.assertEqual(html1, prefix + ".html", msg="html path")
        self.assertEqual(json1, prefix + ".json", msg="json path")
        with open(html1, "rb") as handle:
            html1_bytes = handle.read()
        with open(html2, "rb") as handle:
            html2_bytes = handle.read()
        with open(json1, "rb") as handle:
            json1_bytes = handle.read()
        with open(json2, "rb") as handle:
            json2_bytes = handle.read()
        self.assertEqual(html1_bytes, html2_bytes,
                         msg="html byte-identical between the runs")
        self.assertEqual(json1_bytes, json2_bytes,
                         msg="json byte-identical between the runs")
        with open(json2, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        self.assertEqual(loaded, report.collect(store),
                         msg="json.load of the second gives collect(store)")

    def test_build_report_charts_unavailable(self):
        """Render Report example 3: ImportError becomes ChartsUnavailable."""
        store = block_store()
        directory = tempfile.mkdtemp(prefix="ethsc-report-test-")
        prefix = os.path.join(directory, "r")

        class _FailFinder(object):
            def find_spec(self, name, path=None, target=None):
                if name == "ethsc.charts":
                    raise ImportError("no matplotlib")
                return None

        finder = _FailFinder()
        saved = sys.modules.pop("ethsc.charts", None)
        sys.meta_path.insert(0, finder)
        try:
            with self.assertRaises(report.ChartsUnavailable,
                                   msg="ChartsUnavailable is raised"):
                report.build_report(store, prefix)
        finally:
            sys.meta_path.remove(finder)
            if saved is not None:
                sys.modules["ethsc.charts"] = saved
        self.assertFalse(os.path.exists(prefix + ".html"),
                         msg="no html file written")
        self.assertFalse(os.path.exists(prefix + ".json"),
                         msg="no json file written")


if __name__ == "__main__":
    unittest.main()
