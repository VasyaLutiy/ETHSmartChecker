"""Judge tests, phase 18: contour group fingerprint, Code Similarity 1-6.

One unittest test per example; every 'then' checked against the exact
values written in the Contour. Offline, stdlib only, Python 3.9.
"""

import unittest

from ethsc.fingerprint import (
    ALERT_MIN,
    CODE_MIN,
    code_similarity,
    opcode_shingles,
    similarity,
)
from tests.helpers import load_hex


class TestCodeSimilarityExamples(unittest.TestCase):
    # Example 1
    def test_example1_belle_copy_symmetric(self):
        belle = load_hex("code_belle.hex")
        copy = load_hex("code_belle_copy_1807090d.hex")
        expected = 920.0 / 929.0
        self.assertEqual(opcode_shingles(belle), frozenset([]) |
                         opcode_shingles(belle))  # sanity: a set value
        self.assertEqual(len(opcode_shingles(belle)), 924)
        self.assertEqual(len(opcode_shingles(copy)), 925)
        self.assertEqual(code_similarity(belle, copy), expected)
        self.assertEqual(code_similarity(copy, belle), expected)
        self.assertEqual(code_similarity(belle, copy), 0.9903121636167922)

    # Example 2
    def test_example2_immutables_only_pairs(self):
        univ3_a = load_hex("code_univ3_usdc_weth_005.hex")
        univ3_b = load_hex("code_univ3_pool_e0554a47.hex")
        launch_a = load_hex("code_launchtoken_40676634.hex")
        launch_b = load_hex("code_launchtoken_4e67db19.hex")
        self.assertEqual(len(opcode_shingles(univ3_a) &
                            opcode_shingles(univ3_b)), 7352)
        self.assertEqual(len(opcode_shingles(univ3_a) |
                            opcode_shingles(univ3_b)), 7352)
        self.assertEqual(code_similarity(univ3_a, univ3_b), 1.0)
        self.assertEqual(len(opcode_shingles(launch_a) &
                            opcode_shingles(launch_b)), 768)
        self.assertEqual(len(opcode_shingles(launch_a) |
                            opcode_shingles(launch_b)), 768)
        self.assertEqual(code_similarity(launch_a, launch_b), 1.0)

    # Example 3
    def test_example3_cross_family_values(self):
        belle = load_hex("code_belle.hex")
        weth9 = load_hex("code_weth9.hex")
        usdt = load_hex("code_usdt.hex")
        proxy_a = load_hex("code_proxy_seed_0c010533.hex")
        proxy_b = load_hex("code_proxy_046eee2c.hex")
        self.assertEqual(code_similarity(belle, weth9),
                         209.0 / 1291.0)
        self.assertEqual(code_similarity(belle, weth9),
                         0.16189000774593337)
        self.assertEqual(code_similarity(weth9, usdt),
                         430.0 / 1311.0)
        self.assertEqual(code_similarity(weth9, usdt),
                         0.32799389778794813)
        self.assertEqual(code_similarity(proxy_a, proxy_b),
                         197.0 / 1221.0)
        self.assertEqual(code_similarity(proxy_a, proxy_b),
                         0.16134316134316135)

    # Example 4
    def test_example4_clones_code_vs_similarity(self):
        clone_a = load_hex("code_clone_270df012.hex")
        clone_b = load_hex("code_clone_2ca7b61b.hex")
        self.assertEqual(len(opcode_shingles(clone_a) &
                            opcode_shingles(clone_b)), 20)
        self.assertEqual(len(opcode_shingles(clone_a) |
                            opcode_shingles(clone_b)), 20)
        self.assertEqual(code_similarity(clone_a, clone_b), 1.0)
        self.assertEqual(similarity(clone_a, clone_b), 0.0)

    # Example 5
    def test_example5_tolerant_parser(self):
        weth9 = load_hex("code_weth9.hex")
        self.assertEqual(code_similarity(b"", weth9), 0.0)
        self.assertEqual(code_similarity(b"\x60\x00\x60\x00",
                                         b"\x60\x00\x60\x00"), 0.0)
        self.assertEqual(len(opcode_shingles(b"")), 0)
        self.assertEqual(len(opcode_shingles(b"\x60\x00\x60\x00")), 0)
        self.assertEqual(len(opcode_shingles(b"\x60\x00" * 5)), 1)
        self.assertEqual(len(opcode_shingles(b"\xfe\xff\x7f")), 0)
        sh = opcode_shingles(b"\x60\x00" * 5)
        self.assertEqual(len(sh), 1)

    # Example 6
    def test_example6_constants(self):
        import ethsc.fingerprint as module
        self.assertIs(ALERT_MIN, module.ALERT_MIN)
        self.assertEqual(ALERT_MIN, 0.75)
        self.assertEqual(CODE_MIN, 0.6)


if __name__ == "__main__":
    unittest.main()
