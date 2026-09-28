"""Example-based tests for ethsc.fingerprint (the judge's card).

One test per example from contour.yaml / docs/TASK_PHASE2.md / fixtures
README. The module under test is imported; fixtures are read from
tests/fixtures/. Standard library only.
"""

import os
import unittest

from ethsc.fingerprint import fingerprint, similarity

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _load(name):
    """Decode a code_*.hex fixture verbatim (0x + hex, no newline)."""
    path = os.path.join(FIXTURES, name)
    with open(path, "r", encoding="ascii") as fh:
        text = fh.read().strip()
    return bytes.fromhex(text[2:])


class FingerprintCodeExamples(unittest.TestCase):
    maxDiff = None

    def test_example_1_univ2_pair_identical_code_id(self):
        """Fingerprint Code example 1: the two byte-identical UniswapV2Pair
        fixtures give the same code_id 8b5db55f…, size 11293, 27 selectors."""
        a = _load("code_univ2_usdc_weth.hex")
        b = _load("code_univ2_weth_usdt.hex")
        fa = fingerprint(a)
        fb = fingerprint(b)
        want_id = "8b5db55fa9ab3b9527508d4abe0b39eb588bf310270c8e04b3f38214e8ba63b4"
        self.assertIsNotNone(fa, msg="fingerprint(univ2 usdc/weth) must not be None")
        self.assertIsNotNone(fb, msg="fingerprint(univ2 weth/usdt) must not be None")
        self.assertEqual(fa["code_id"], want_id, msg="usdc/weth code_id mismatch")
        self.assertEqual(fb["code_id"], want_id, msg="weth/usdt code_id mismatch")
        self.assertEqual(fa["size"], 11293, msg="usdc/weth size mismatch")
        self.assertEqual(fb["size"], 11293, msg="weth/usdt size mismatch")
        self.assertEqual(
            len(fa["selectors"]), 27, msg="usdc/weth selector count mismatch"
        )
        self.assertEqual(
            len(fb["selectors"]), 27, msg="weth/usdt selector count mismatch"
        )

    def test_example_2_weth9_code_id_and_no_proxy(self):
        """Fingerprint Code example 2: WETH9 gives code_id 5566bf50…, size
        3124, proxy None."""
        f = fingerprint(_load("code_weth9.hex"))
        self.assertIsNotNone(f, msg="fingerprint(weth9) must not be None")
        self.assertEqual(
            f["code_id"],
            "5566bf50796faf93c9b6f6adacd3b32c70bfe16b48ffc59db6cd144cbdc89739",
            msg="weth9 code_id mismatch",
        )
        self.assertEqual(f["size"], 3124, msg="weth9 size mismatch")
        self.assertIsNone(f["proxy"], msg="weth9 proxy must be None")

    def test_example_3_univ3_pools_differ_code_id_equal_skeleton(self):
        """Fingerprint Code example 3: the two UniswapV3Pool deployments have
        different code_id but equal skeleton_hash."""
        f1 = fingerprint(_load("code_univ3_usdc_weth_005.hex"))
        f2 = fingerprint(_load("code_univ3_pool_e0554a47.hex"))
        self.assertIsNotNone(f1, msg="fingerprint(univ3 005) must not be None")
        self.assertIsNotNone(f2, msg="fingerprint(univ3 e0554a47) must not be None")
        self.assertNotEqual(
            f1["code_id"],
            f2["code_id"],
            msg="the two UniswapV3Pool code_ids must differ",
        )
        self.assertEqual(
            f1["skeleton_hash"],
            f2["skeleton_hash"],
            msg="the two UniswapV3Pool skeleton_hashes must be equal",
        )

    def test_example_4_empty_code_gives_none(self):
        """Fingerprint Code example 4: fingerprint(b"") returns None."""
        self.assertIsNone(fingerprint(b""), msg="fingerprint(b'') must be None")


class SimilarityScoreExamples(unittest.TestCase):
    maxDiff = None

    def test_example_1_weth9_usdt_nine_of_34(self):
        """Similarity Score example 1: WETH9 (11 selectors) vs USDT (32)
        gives 9/34 = 0.2647, the ERC-20 core shared selectors."""
        got = similarity(_load("code_weth9.hex"), _load("code_usdt.hex"))
        self.assertIsInstance(got, float, msg="similarity must return float")
        self.assertEqual(
            round(got, 4), 0.2647, msg="weth9/usdt similarity must be 9/34"
        )

    def test_example_2_univ2_weth9_nine_of_29(self):
        """Similarity Score example 2: UniswapV2Pair (27 selectors) vs WETH9
        (11) gives 9/29 = 0.3103."""
        got = similarity(
            _load("code_univ2_usdc_weth.hex"), _load("code_weth9.hex")
        )
        self.assertIsInstance(got, float, msg="similarity must return float")
        self.assertEqual(
            round(got, 4), 0.3103, msg="univ2/weth9 similarity must be 9/29"
        )

    def test_example_3_belle_copy_thirteen_of_15(self):
        """Similarity Score example 3: BELLE vs its ALPHA copy
        (code_belle_copy_1807090d.hex) gives 13/15 = 0.8667; the copy swaps
        BotBlacklist for Blacklist."""
        got = similarity(_load("code_belle.hex"), _load("code_belle_copy_1807090d.hex"))
        self.assertIsInstance(got, float, msg="similarity must return float")
        self.assertEqual(
            round(got, 4), 0.8667, msg="belle/copy similarity must be 13/15"
        )

    def test_example_4_two_clones_trigram_jaccard_one(self):
        """Similarity Score example 4: two EIP-1167 clones of different
        targets (270df012 vs 2ca7b61b, no selectors) give 1.0 via the same
        22 opcode 3-grams."""
        got = similarity(
            _load("code_clone_270df012.hex"), _load("code_clone_2ca7b61b.hex")
        )
        self.assertIsInstance(got, float, msg="similarity must return float")
        self.assertEqual(got, 1.0, msg="the two clones must score 1.0")


if __name__ == "__main__":
    unittest.main()
