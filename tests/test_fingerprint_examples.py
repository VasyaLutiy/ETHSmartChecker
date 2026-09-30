"""Example-based tests for ethsc/fingerprint.py.

One test per example of the functions Fingerprint Code and Similarity
Score, as pinned in contour.yaml and docs/TASK_PHASE9.md. Every number
comes from tests/fixtures, never from the network. Standard library
only.
"""

import unittest

import ethsc.fingerprint
from tests.helpers import load_hex

WETH9 = load_hex("code_weth9.hex")
USDT = load_hex("code_usdt.hex")
UNIV2_USDC_WETH = load_hex("code_univ2_usdc_weth.hex")
UNIV2_WETH_USDT = load_hex("code_univ2_weth_usdt.hex")
UNIV3_USDC_WETH_005 = load_hex("code_univ3_usdc_weth_005.hex")
UNIV3_POOL_E0554A47 = load_hex("code_univ3_pool_e0554a47.hex")
CLONE_270DF012 = load_hex("code_clone_270df012.hex")
CLONE_2CA7B61B = load_hex("code_clone_2ca7b61b.hex")
PROXY_SEED_0C010533 = load_hex("code_proxy_seed_0c010533.hex")
PROXY_046EEE2C = load_hex("code_proxy_046eee2c.hex")
BELLE = load_hex("code_belle.hex")
BELLE_COPY_1807090D = load_hex("code_belle_copy_1807090d.hex")


class TestFingerprintCode(unittest.TestCase):
    """Examples of Function Fingerprint Code."""

    maxDiff = None

    def test_fingerprint_code_example_1(self):
        """Fingerprint Code example 1: the two byte-identical UniswapV2Pair
        fixtures give the same code_id 8b5db55f..., size 11293, 27 selectors."""
        fa = ethsc.fingerprint.fingerprint(UNIV2_USDC_WETH)
        fb = ethsc.fingerprint.fingerprint(UNIV2_WETH_USDT)
        self.assertIsNotNone(fa, msg="fingerprint(usdc/weth) must not be None")
        self.assertIsNotNone(fb, msg="fingerprint(weth/usdt) must not be None")
        want_id = "8b5db55fa9ab3b9527508d4abe0b39eb588bf310270c8e04b3f38214e8ba63b4"
        self.assertEqual(fa["code_id"], want_id, msg="usdc/weth code_id mismatch")
        self.assertEqual(fb["code_id"], want_id, msg="weth/usdt code_id mismatch")
        self.assertEqual(fa["size"], 11293, msg="usdc/weth size mismatch")
        self.assertEqual(fb["size"], 11293, msg="weth/usdt size mismatch")
        self.assertEqual(len(fa["selectors"]), 27, msg="usdc/weth selector count")
        self.assertEqual(len(fb["selectors"]), 27, msg="weth/usdt selector count")

    def test_fingerprint_code_example_2(self):
        """Fingerprint Code example 2: WETH9 gives code_id
        5566bf50..., size 3124, proxy None."""
        got = ethsc.fingerprint.fingerprint(WETH9)
        self.assertIsNotNone(got, msg="fingerprint(weth9) must not be None")
        self.assertEqual(
            got["code_id"],
            "5566bf50796faf93c9b6f6adacd3b32c70bfe16b48ffc59db6cd144cbdc89739",
            msg="weth9 code_id mismatch (sha256 of the fixture bytes)")
        self.assertEqual(got["size"], 3124, msg="weth9 size mismatch")
        self.assertIsNone(got["proxy"], msg="weth9 proxy must be None")

    def test_fingerprint_code_example_3(self):
        """Fingerprint Code example 3: the two UniswapV3Pool deployments have
        different code_id but equal skeleton_hash."""
        fa = ethsc.fingerprint.fingerprint(UNIV3_USDC_WETH_005)
        fb = ethsc.fingerprint.fingerprint(UNIV3_POOL_E0554A47)
        self.assertIsNotNone(fa, msg="fingerprint(univ3 005) must not be None")
        self.assertIsNotNone(fb, msg="fingerprint(univ3 e0554a47) must not be None")
        self.assertNotEqual(
            fa["code_id"], fb["code_id"],
            msg="the two UniswapV3Pool code_id must differ")
        self.assertEqual(
            fa["skeleton_hash"], fb["skeleton_hash"],
            msg="the two UniswapV3Pool skeleton_hash must be equal")

    def test_fingerprint_code_example_4(self):
        """Fingerprint Code example 4: fingerprint(b"") is None."""
        self.assertIsNone(
            ethsc.fingerprint.fingerprint(b""),
            msg="empty code must give None (Tolerant Parser)")


class TestSimilarityScore(unittest.TestCase):
    """Examples of Function Similarity Score."""

    maxDiff = None

    def test_similarity_score_example_1(self):
        """Similarity Score example 1: WETH9 (11 selectors) vs USDT (32)
        gives 9/34 = 0.2647; the 9 shared are the ERC-20 core."""
        got = ethsc.fingerprint.similarity(WETH9, USDT)
        self.assertIsInstance(got, float, msg="similarity must return float")
        self.assertEqual(
            round(got, 4), 0.2647, msg="weth9/usdt similarity must be 9/34")

    def test_similarity_score_example_2(self):
        """Similarity Score example 2: UniswapV2Pair (27 selectors) vs WETH9
        (11) gives 9/29 = 0.3103."""
        got = ethsc.fingerprint.similarity(UNIV2_USDC_WETH, WETH9)
        self.assertIsInstance(got, float, msg="similarity must return float")
        self.assertEqual(
            round(got, 4), 0.3103, msg="univ2/weth9 similarity must be 9/29")

    def test_similarity_score_example_3(self):
        """Similarity Score example 3: BELLE vs its ALPHA copy
        code_belle_copy_1807090d.hex gives 13/15 = 0.8667; the copy swaps
        BotBlacklist (0x8f5db675) for Blacklist (0xf7e58a63)."""
        got = ethsc.fingerprint.similarity(BELLE, BELLE_COPY_1807090D)
        self.assertIsInstance(got, float, msg="similarity must return float")
        self.assertEqual(
            round(got, 4), 0.8667, msg="belle/copy similarity must be 13/15")

    def test_similarity_score_example_4(self):
        """Similarity Score example 4: two EIP-1167 clones of different
        targets (270df012 vs 2ca7b61b) give 0.0 -- different implementations,
        however alike the 45-byte proxy bytecode is."""
        got = ethsc.fingerprint.similarity(CLONE_270DF012, CLONE_2CA7B61B)
        self.assertEqual(
            got, 0.0,
            msg="rule (1): clones with different targets must score 0.0 "
                "(the old opcode-3gram 1.0 was a false positive)")

    def test_similarity_score_example_5(self):
        """Similarity Score example 5: code_clone_270df012.hex against itself
        scores 1.0 -- same kind and same target."""
        got = ethsc.fingerprint.similarity(CLONE_270DF012, CLONE_270DF012)
        self.assertEqual(
            got, 1.0,
            msg="rule (1): the same EIP-1167 kind and target match exactly")

    def test_similarity_score_example_6(self):
        """Similarity Score example 6: code_proxy_seed_0c010533.hex and
        code_proxy_046eee2c.hex (two distinct standard EIP-1967 proxies)
        score 0.0 -- a standard proxy never matches another."""
        got = ethsc.fingerprint.similarity(PROXY_SEED_0C010533, PROXY_046EEE2C)
        self.assertEqual(
            got, 0.0,
            msg="rule (2): both are opaque standard proxies "
                "(is_std_proxy True on both), so 0.0 -- the 380-alert "
                "false positive of the live 30.09 base")

    def test_similarity_score_example_7(self):
        """Similarity Score example 7: the standard proxy
        code_proxy_seed_0c010533.hex vs WETH9 scores 0.0 -- one side is an
        opaque standard proxy."""
        got = ethsc.fingerprint.similarity(PROXY_SEED_0C010533, WETH9)
        self.assertEqual(
            got, 0.0,
            msg="rule (2): is_std_proxy on one side forces 0.0 even against "
                "a real contract with 11 selectors")


if __name__ == "__main__":
    unittest.main()
