# tests/test_report_examples.py
# -*- coding: utf-8 -*-
"""Example-based tests for ethsc/report.py (docs/TASK_PHASE9.md).

One test per Contour example of TWO functions: Collect Report Data
(examples 1-6) and Spearman Matrix (examples 7-10). Render Report is
NOT tested here (the report code card owns it, and it needs
matplotlib, which this judge must never import): every number is read
straight out of the collect() / spearman() payload.

The block base comes from tests.helpers.block_store (block 26077729:
206 addresses, 147 with code, 130 codes). No network, no Fake classes
defined here, no matplotlib, standard library only, Python 3.9.
"""

import unittest

from ethsc import report
from ethsc.fingerprint import fingerprint

from tests.helpers import block_codes, block_store, temp_store


FEATURES = report.FEATURES
IDX = dict((name, i) for i, name in enumerate(FEATURES))


def _non_proxy_store():
    """A store holding only the non-proxy codes of the block base.

    Every distinct code of codes_26077729.json whose fingerprint has
    proxy None is put in the store with its addresses; the eip1167 and
    eip7702 proxy codes are left out, so is_proxy is 0 for every code
    and the spearman section must mark it null.
    """
    store = temp_store()
    block = 26077729
    for address, text in sorted(block_codes().items()):
        if text == "0x":
            continue
        code = bytes.fromhex(text[2:])
        if fingerprint(code)["proxy"] is not None:
            continue
        code_id = store.put_code(code)
        store.put_address(address, code_id, block)
    return store


def _levels_checks(test, levels):
    """Collect Report Data example 1, phase-9 numbers."""
    test.assertEqual(levels["L0"]["clusters"], 7, msg="L0 clusters")
    test.assertEqual(levels["L0"]["addresses"], 16, msg="L0 addresses")
    test.assertAlmostEqual(levels["L0"]["share"], 16 / 147, places=12,
                           msg="L0 share 16/147")
    test.assertEqual(levels["L1"]["clusters"], 2, msg="L1 clusters")
    test.assertEqual(levels["L1"]["addresses"], 13, msg="L1 addresses")
    test.assertAlmostEqual(levels["L1"]["share"], 13 / 147, places=12,
                           msg="L1 share 13/147")
    # the proxy level counts eip1167 only: 2 clusters over 5 addresses
    test.assertEqual(levels["proxy"]["clusters"], 2, msg="proxy clusters (2/5)")
    test.assertEqual(levels["proxy"]["addresses"], 5,
                     msg="proxy addresses (2/5)")
    test.assertAlmostEqual(levels["proxy"]["share"], 5 / 147, places=12,
                           msg="proxy share 5/147")
    # the eip7702 delegations are a level of their own: 4 clusters over 9
    test.assertEqual(levels["eip7702"]["clusters"], 4, msg="eip7702 clusters")
    test.assertEqual(levels["eip7702"]["addresses"], 9, msg="eip7702 addresses")
    test.assertAlmostEqual(levels["eip7702"]["share"], 9 / 147, places=12,
                           msg="eip7702 share 9/147")
    test.assertEqual(levels["proxy_codes"], 5, msg="proxy_codes 5")
    test.assertAlmostEqual(levels["proxy_code_share"], 5 / 130, places=12,
                           msg="proxy_code_share 5/130")
    test.assertEqual(levels["eip7702_codes"], 7, msg="eip7702_codes 7")
    test.assertAlmostEqual(levels["eip7702_code_share"], 7 / 130, places=12,
                           msg="eip7702_code_share 7/130")


class CollectReportDataTests(unittest.TestCase):
    """Collect Report Data, examples 1 to 6."""

    def setUp(self):
        self.maxDiff = None

    def test_1_levels_block_base(self):
        """Collect Report Data example 1: levels over the block base."""
        data = report.collect(block_store())
        _levels_checks(self, data["levels"])

    def test_2_skeletons_block_base(self):
        """Collect Report Data example 2: the unique-skeleton shares."""
        data = report.collect(block_store())
        s = data["skeletons"]
        self.assertEqual(s["non_proxy_codes"], 118, msg="non_proxy_codes")
        self.assertEqual(s["unique_codes"], 105, msg="unique_codes")
        self.assertAlmostEqual(s["unique_share"], 105 / 118, places=12,
                               msg="unique_share 105/118 = 0.8898")
        self.assertAlmostEqual(s["unique_share"], 0.8898, places=4,
                               msg="the unique-skeleton share by code_id "
                                   "0.8898")
        self.assertEqual(s["non_proxy_addresses"], 127,
                         msg="non_proxy_addresses")
        self.assertEqual(s["unique_addresses"], 114, msg="unique_addresses")
        self.assertAlmostEqual(s["unique_address_share"], 114 / 127,
                               places=12,
                               msg="unique_address_share 114/127")
        self.assertAlmostEqual(s["unique_address_share"], 0.8976, places=4,
                               msg="the unique-skeleton share by address "
                                   "0.8976")

    def test_3_code_distributions_block_base(self):
        """Collect Report Data example 3: size and selector histograms."""
        data = report.collect(block_store())
        size = data["codes"]["size"]
        self.assertEqual(size["min"], 20, msg="size min 20")
        self.assertEqual(size["median"], 4442.5,
                         msg="the size median 4442.5 (4369 and 4516 averaged)")
        self.assertIsInstance(size["median"], float, msg="median is a float")
        self.assertEqual(size["max"], 24313, msg="size max 24313")
        self.assertEqual(size["histogram"]["edges"],
                         [0, 256, 1024, 4096, 8192, 16384, 24576],
                         msg="size edges fixed")
        self.assertEqual(size["histogram"]["counts"],
                         [22, 5, 36, 19, 23, 25, 0], msg="size histogram")
        sel = data["codes"]["selectors"]
        self.assertEqual(sel["min"], 0, msg="selector min 0")
        self.assertEqual(sel["median"], 12.5,
                         msg="the selector median 12.5 (12 and 13 averaged)")
        self.assertIsInstance(sel["median"], float, msg="median is a float")
        self.assertEqual(sel["max"], 72, msg="selector max 72")
        self.assertEqual(sel["histogram"]["edges"],
                         [0, 1, 2, 4, 8, 16, 32, 64],
                         msg="selector edges fixed")
        self.assertEqual(sel["histogram"]["counts"],
                         [28, 2, 3, 16, 27, 35, 17, 2],
                         msg="selector histogram")

    def test_4_alerts_univ2_seed(self):
        """Collect Report Data example 4: alerts folded per seed."""
        store = block_store()
        store.add_seed("0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
                       "UniV2 pair seed")
        alerts = report.collect(store)["alerts"]
        self.assertEqual(alerts["total"], 4, msg="total 4 alerts")
        self.assertEqual(len(alerts["seeds"]), 1, msg="one seed entry")
        seed = alerts["seeds"][0]
        self.assertEqual(seed["address"],
                         "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc",
                         msg="the seed address")
        self.assertEqual(seed["label"], "UniV2 pair seed", msg="the label")
        self.assertEqual(seed["count"], 4, msg="count 4")

    def test_5_risk_flags_block_base(self):
        """Collect Report Data example 5: the risk reach over the base."""
        data = report.collect(block_store())
        risk = data["risk"]
        sd = risk["selfdestruct"]
        self.assertEqual(sd["codes"], 1,
                         msg="the selfdestruct flag: 1 code")
        self.assertEqual(sd["addresses"], 1,
                         msg="the selfdestruct flag: 1 address")
        self.assertAlmostEqual(sd["code_share"], 1 / 130, places=12,
                               msg="the selfdestruct code share 1/130")
        self.assertAlmostEqual(sd["address_share"], 1 / 147, places=12,
                               msg="the selfdestruct address share 1/147")
        md = risk["mutable_delegatecall"]
        self.assertEqual(md["codes"], 12,
                         msg="the mutable_delegatecall flag: 12 codes")
        self.assertEqual(md["addresses"], 13,
                         msg="the mutable_delegatecall flag: 13 addresses")
        self.assertAlmostEqual(md["code_share"], 12 / 130, places=12,
                               msg="the mutable_delegatecall code share "
                                   "12/130")
        self.assertAlmostEqual(md["address_share"], 13 / 147, places=12,
                               msg="the mutable_delegatecall address share "
                                   "13/147")

    def test_6_empty_database(self):
        """Collect Report Data example 6: an empty database, no exception."""
        data = report.collect(temp_store())
        self.assertEqual(
            set(data.keys()),
            {"summary", "levels", "skeletons", "clusters", "codes",
             "ledger", "alerts", "spearman", "risk"},
            msg="all nine keys present")
        summary = data["summary"]
        self.assertEqual(
            set(summary.keys()),
            {"addresses", "addresses_with_code", "addresses_without_code",
             "codes", "blocks"},
            msg="summary keys")
        for key in sorted(summary):
            self.assertEqual(summary[key], 0, msg="summary %s is 0" % key)
        self.assertEqual(data["clusters"]["top"], [], msg="no top clusters")
        self.assertEqual(data["clusters"]["histogram"]["counts"],
                         [0] * len(report.CLUSTER_EDGES),
                         msg="empty cluster histogram")
        self.assertEqual(data["ledger"]["days"], [], msg="empty ledger")
        self.assertEqual(data["ledger"]["total"], 0, msg="ledger total 0")
        self.assertEqual(data["alerts"]["seeds"], [], msg="no alert seeds")
        self.assertEqual(data["alerts"]["total"], 0, msg="alerts total 0")
        for name in ("selfdestruct", "mutable_delegatecall"):
            entry = data["risk"][name]
            self.assertEqual(entry["codes"], 0,
                             msg="risk %s codes 0" % name)
            self.assertEqual(entry["addresses"], 0,
                             msg="risk %s addresses 0" % name)
            self.assertEqual(entry["code_share"], 0.0,
                             msg="risk %s code_share 0.0" % name)
            self.assertEqual(entry["address_share"], 0.0,
                             msg="risk %s address_share 0.0" % name)
        sp = data["spearman"]
        self.assertEqual(sp["n"], 0, msg="spearman n 0")
        self.assertEqual(len(sp["matrix"]), 6, msg="6x6 matrix")
        for row in sp["matrix"]:
            self.assertEqual(len(row), 6, msg="6x6 matrix")
            for cell in row:
                self.assertIsNone(cell, msg="empty base: null everywhere")


class SpearmanMatrixTests(unittest.TestCase):
    """Spearman Matrix, examples 7 to 10."""

    def setUp(self):
        self.maxDiff = None

    def _matrix(self, store):
        """The spearman section of collect(store), features in order."""
        section = report.collect(store)["spearman"]
        self.assertEqual(section["features"], list(report.FEATURES),
                         msg="features in the fixed order")
        self.assertEqual(section["n"], 130, msg="the counted base: n = 130 "
                                                "codes")
        return section

    def test_7_coefficients_block_base(self):
        """Spearman Matrix, example 7: the six pinned coefficients."""
        m = self._matrix(block_store())["matrix"]
        pairs = [
            ("bytecode_size", "opcode_count", 0.9893),
            ("bytecode_size", "selector_count", 0.8422),
            ("bytecode_size", "address_count", -0.3368),
            ("opcode_count", "selector_count", 0.8559),
            ("address_count", "is_proxy", 0.4289),
            ("l1_family_size", "is_proxy", 0.2326),
        ]
        for a, b, expected in pairs:
            value = m[IDX[a]][IDX[b]]
            self.assertIsNotNone(value, msg="%s~%s is not null" % (a, b))
            self.assertAlmostEqual(value, expected, places=4,
                                   msg="%s~%s = %.4f" % (a, b, expected))
            self.assertAlmostEqual(m[IDX[b]][IDX[a]], expected, places=4,
                                   msg="%s~%s symmetric" % (b, a))
        # the diagonal is 1.0 on every non-degenerate feature
        for name in report.FEATURES:
            self.assertAlmostEqual(m[IDX[name]][IDX[name]], 1.0, places=9,
                                   msg="diagonal %s is 1.0" % name)

    def test_8_tie_handling(self):
        """Spearman Matrix, example 8: the tie-blind shortcut refuted.

        bytecode_size~address_count is -0.3368 and
        address_count~is_proxy 0.4289, while the shortcut
        1 - 6*sum(d^2)/(n(n^2-1)) gives 0.1898 and 0.8509; the payload
        must carry the tie-averaged values, never the shortcut's.
        """
        m = self._matrix(block_store())["matrix"]
        self.assertAlmostEqual(m[IDX["bytecode_size"]][IDX["address_count"]],
                               -0.3368, places=4,
                               msg="bytecode_size~address_count tie-averaged")
        self.assertAlmostEqual(m[IDX["address_count"]][IDX["is_proxy"]],
                               0.4289, places=4,
                               msg="address_count~is_proxy tie-averaged")
        self.assertNotAlmostEqual(
            m[IDX["bytecode_size"]][IDX["address_count"]], 0.1898, places=4,
            msg="not the shortcut for bytecode_size~address_count")
        self.assertNotAlmostEqual(
            m[IDX["address_count"]][IDX["is_proxy"]], 0.8509, places=4,
            msg="not the shortcut for address_count~is_proxy")

    def test_9_small_rows(self):
        """Spearman Matrix, example 9: the four-row hand case.

        Rows [(1, 10), (2, 20), (2, 30), (3, 40)] as two features give
        0.9486832980505138, the average ranks being
        [1.0, 2.5, 2.5, 4.0].
        """
        result = report.spearman([(1, 10), (2, 20), (2, 30), (3, 40)])
        self.assertEqual(result["n"], 4, msg="n = 4")
        self.assertAlmostEqual(result["matrix"][0][1],
                               0.9486832980505138, places=12,
                               msg="the four-row hand case coefficient")
        self.assertAlmostEqual(result["matrix"][1][0],
                               0.9486832980505138, places=12,
                               msg="symmetric")
        self.assertAlmostEqual(result["matrix"][0][0], 1.0, places=9,
                               msg="diagonal 1.0")

    def test_10_zero_variance_feature(self):
        """Spearman Matrix, example 10: a zero-variance feature.

        On a base of non-proxy codes only (the 118 non-proxy codes of
        the block base), every cell of the is_proxy row and column is
        null, the diagonal included, and the other features keep their
        coefficients.
        """
        store = _non_proxy_store()
        fps = store.fingerprints()
        self.assertEqual(len(fps), 118, msg="118 non-proxy codes stored")
        for fp in fps:
            self.assertIsNone(fp["proxy"], msg="no proxy code in the base")
        section = report.collect(store)["spearman"]
        self.assertEqual(section["features"], list(report.FEATURES),
                         msg="features in the fixed order")
        m = section["matrix"]
        ip = IDX["is_proxy"]
        for i in range(len(report.FEATURES)):
            self.assertIsNone(m[i][ip],
                              msg="matrix[%d][is_proxy] is null" % i)
            self.assertIsNone(m[ip][i],
                              msg="matrix[is_proxy][%d] is null" % i)
        # the other four features keep their coefficients
        others = [("bytecode_size", "opcode_count"),
                  ("bytecode_size", "selector_count"),
                  ("opcode_count", "selector_count")]
        for a, b in others:
            self.assertIsNotNone(m[IDX[a]][IDX[b]],
                                 msg="%s~%s keeps its coefficient" % (a, b))


if __name__ == "__main__":
    unittest.main()
