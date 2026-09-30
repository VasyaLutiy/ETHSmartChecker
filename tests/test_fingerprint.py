"""Tests for ethsc.fingerprint: Fingerprint Code and Similarity Score.

Every test names the example or rule of contour.yaml it checks. All
numbers come from tests/fixtures (verbatim mainnet bytes).
"""

import os
import unittest

from ethsc.evm import build_skeleton, detect_proxy, extract_selectors
from ethsc.fingerprint import fingerprint, similarity

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def load_code(name):
    """Decode a code_*.hex fixture: the verbatim '0x' + hex string."""
    with open(os.path.join(FIXTURES, name), "r") as f:
        return bytes.fromhex(f.read().strip()[2:])


def load_json(name):
    import json
    with open(os.path.join(FIXTURES, name), "r") as f:
        return json.load(f)


class FingerprintCodeTests(unittest.TestCase):
    """Function Fingerprint Code: the 4 examples plus the schema rules."""

    maxDiff = None

    def test_example_1_univ2_pair_identical_codes(self):
        """Example 1: two byte-identical UniswapV2Pair deployments share
        code_id 8b5db55f..., size 11293, 27 selectors."""
        a = load_code("code_univ2_usdc_weth.hex")
        b = load_code("code_univ2_weth_usdt.hex")
        fa = fingerprint(a)
        fb = fingerprint(b)
        self.assertIsNotNone(fa, "the code must give a fingerprint")
        self.assertIsNotNone(fb, "the code must give a fingerprint")
        self.assertEqual(
            fa["code_id"],
            "8b5db55fa9ab3b9527508d4abe0b39eb588bf310270c8e04b3f38214e8ba63b4",
            msg="code_id is the sha256 of the decoded fixture bytes",
        )
        self.assertEqual(fb["code_id"], fa["code_id"],
                         msg="byte-identical codes share one code_id")
        self.assertEqual(fa["size"], 11293, msg="the fixture is 11293 bytes")
        self.assertEqual(len(fa["selectors"]), 27,
                         msg="the UniswapV2Pair dispatcher has 27 selectors")

    def test_example_2_weth9_id_size_no_proxy(self):
        """Example 2: WETH9 has code_id 5566bf50..., size 3124, proxy None."""
        fp = fingerprint(load_code("code_weth9.hex"))
        self.assertIsNotNone(fp, "the code must give a fingerprint")
        self.assertEqual(
            fp["code_id"],
            "5566bf50796faf93c9b6f6adacd3b32c70bfe16b48ffc59db6cd144cbdc89739",
            msg="sha256 of the decoded WETH9 fixture bytes",
        )
        self.assertEqual(fp["size"], 3124, msg="WETH9 runtime is 3124 bytes")
        self.assertIsNone(fp["proxy"], msg="WETH9 is not a proxy")

    def test_example_3_univ3_same_skeleton_hash(self):
        """Example 3: two UniswapV3Pool deployments have different code_id
        and equal skeleton_hash (Build Skeleton example 1)."""
        fa = fingerprint(load_code("code_univ3_usdc_weth_005.hex"))
        fb = fingerprint(load_code("code_univ3_pool_e0554a47.hex"))
        self.assertIsNotNone(fa, "the code must give a fingerprint")
        self.assertIsNotNone(fb, "the code must give a fingerprint")
        self.assertNotEqual(fa["code_id"], fb["code_id"],
                            msg="the raw codes differ (74 bytes, PUSH32)")
        self.assertEqual(fa["skeleton_hash"], fb["skeleton_hash"],
                         msg="the skeletons coincide once PUSH32 is masked")

    def test_example_4_empty_code_gives_none(self):
        """Example 4: fingerprint(b"") is None (Tolerant Parser)."""
        self.assertIsNone(fingerprint(b""), msg="empty code gives None")

    def test_schema_exact_keys_and_derivation(self):
        """Schema: exactly the five keys; each value derived from evm."""
        code = load_code("code_weth9.hex")
        fp = fingerprint(code)
        self.assertEqual(
            sorted(fp.keys()),
            ["code_id", "proxy", "selectors", "size", "skeleton_hash",
             "std_proxy"],
            msg="the Fingerprint dict has exactly the five schema keys",
        )
        import hashlib
        self.assertEqual(fp["code_id"], hashlib.sha256(code).hexdigest(),
                         msg="code_id is the sha256 hex of the raw code")
        self.assertEqual(fp["skeleton_hash"],
                         hashlib.sha256(build_skeleton(code)).hexdigest(),
                         msg="skeleton_hash is the sha256 of the skeleton")
        self.assertEqual(fp["selectors"], extract_selectors(code),
                         msg="selectors come from extract_selectors")
        self.assertEqual(fp["proxy"], detect_proxy(code),
                         msg="proxy comes from detect_proxy")
        self.assertEqual(fp["size"], len(code), msg="size is len(code)")

    def test_tolerant_garbage_never_raises(self):
        """Tolerant Parser: garbage and truncated bytes give a dict, no
        exception."""
        for garbage in (b"\xff" * 40, b"\x7f" * 3, b"\x60", b"\xa1\x02",
                        bytes(range(256))):
            try:
                fp = fingerprint(garbage)
            except Exception as exc:  # noqa: BLE001 - the rule under test
                self.fail("fingerprint raised on garbage bytes: %r" % (exc,))
            self.assertIsNotNone(fp, msg="non-empty garbage gives a dict")
            self.assertEqual(len(fp["code_id"]), 64,
                             msg="code_id is 64 hex chars")


class SimilarityScoreTests(unittest.TestCase):
    """Function Similarity Score: the 7 examples plus the rules."""

    maxDiff = None

    def _assert_close(self, got, num, den, msg):
        want = float(num) / float(den)
        self.assertAlmostEqual(got, want, places=4, msg=msg)

    def test_example_1_weth9_usdt(self):
        """Example 1: WETH9 (11) vs USDT (32): 9/34 = 0.2647."""
        got = similarity(load_code("code_weth9.hex"),
                         load_code("code_usdt.hex"))
        self._assert_close(got, 9, 34,
                           "9 shared ERC-20 core selectors out of 34")

    def test_example_2_univ2_weth9(self):
        """Example 2: UniswapV2Pair (27) vs WETH9 (11): 9/29 = 0.3103."""
        got = similarity(load_code("code_univ2_usdc_weth.hex"),
                         load_code("code_weth9.hex"))
        self._assert_close(got, 9, 29, "9 shared selectors out of 29")

    def test_example_3_belle_copy(self):
        """Example 3: BELLE vs its copy ALPHA: 13/15 = 0.8667."""
        got = similarity(load_code("code_belle.hex"),
                         load_code("code_belle_copy_1807090d.hex"))
        self._assert_close(got, 13, 15,
                           "one selector differs out of 15 union")

    def test_example_4_clones_different_targets_zero(self):
        """Example 4: two EIP-1167 clones with different targets: 0.0 --
        rule (1); the 45-byte proxy bytecode itself never matches."""
        got = similarity(load_code("code_clone_270df012.hex"),
                         load_code("code_clone_2ca7b61b.hex"))
        self.assertEqual(got, 0.0,
                         msg="different targets give 0.0, not 1.0 by trigrams")

    def test_example_5_clone_against_itself_one(self):
        """Example 5: code_clone_270df012.hex against itself: 1.0 -- same
        kind and same target (rule 1)."""
        clone = load_code("code_clone_270df012.hex")
        self.assertEqual(similarity(clone, clone), 1.0,
                         msg="same kind and same target gives 1.0")
        twin = load_code("code_clone_3b2fac8e.hex")
        self.assertEqual(similarity(clone, twin), 1.0,
                         msg="two clones of one implementation also 1.0")

    def test_example_6_two_std_proxies_zero(self):
        """Example 6: the seed proxy vs 046eee2c: 0.0 -- rule (2), both
        standard EIP-1967 proxies, no comparable surface."""
        got = similarity(load_code("code_proxy_seed_0c010533.hex"),
                         load_code("code_proxy_046eee2c.hex"))
        self.assertEqual(got, 0.0,
                         msg="a standard proxy never matches another")

    def test_example_7_std_proxy_vs_weth9_zero(self):
        """Example 7: the seed proxy vs WETH9: 0.0 -- rule (2), one side
        is an opaque standard proxy."""
        got = similarity(load_code("code_proxy_seed_0c010533.hex"),
                         load_code("code_weth9.hex"))
        self.assertEqual(got, 0.0,
                         msg="one side an opaque standard proxy gives 0.0")

    def test_same_nonempty_selector_set_one(self):
        """Rule: two codes with the same non-empty selector set score
        exactly 1.0 (example 5 of the spec, selector form)."""
        weth = load_code("code_weth9.hex")
        self.assertEqual(similarity(weth, weth), 1.0,
                         msg="identical code gives exactly 1.0")

    def test_symmetry_exact(self):
        """Rule: similarity(a, b) == similarity(b, a) exactly."""
        pairs = [
            ("code_weth9.hex", "code_usdt.hex"),
            ("code_belle.hex", "code_belle_copy_1807090d.hex"),
            ("code_clone_270df012.hex", "code_clone_2ca7b61b.hex"),
            ("code_weth9.hex", "code_univ2_usdc_weth.hex"),
            ("code_proxy_seed_0c010533.hex", "code_weth9.hex"),
            ("code_clone_270df012.hex", "code_weth9.hex"),
        ]
        for a_name, b_name in pairs:
            a, b = load_code(a_name), load_code(b_name)
            self.assertEqual(similarity(a, b), similarity(b, a),
                             msg="symmetry for %s / %s" % (a_name, b_name))

    def test_empty_code_gives_zero(self):
        """Rule: similarity(b"", b"") is 0.0, and empty against a real
        code is 0.0 too (empty-set rule, no exception)."""
        weth = load_code("code_weth9.hex")
        self.assertEqual(similarity(b"", b""), 0.0,
                         msg="both sets empty gives 0.0")
        self.assertEqual(similarity(b"", weth), 0.0,
                         msg="empty against real code gives 0.0")

    def test_result_is_float_in_unit_interval(self):
        """Rule: the result is a float in [0, 1] for varied inputs, no
        exception on empty or garbage bytes."""
        cases = [
            ("code_weth9.hex", "code_usdt.hex"),
            ("code_univ2_usdc_weth.hex", "code_weth9.hex"),
            ("code_belle.hex", "code_belle_copy_1807090d.hex"),
            ("code_weth9.hex", "code_belle.hex"),
            ("code_clone_270df012.hex", "code_weth9.hex"),
            ("code_weth9.hex", "code_clone_270df012.hex"),
            ("code_univ3_usdc_weth_005.hex", "code_launchtoken_4e67db19.hex"),
        ]
        for a_name, b_name in cases:
            got = similarity(load_code(a_name), load_code(b_name))
            self.assertIs(type(got), float,
                          msg="float result for %s / %s" % (a_name, b_name))
            self.assertTrue(0.0 <= got <= 1.0,
                            msg="in [0, 1] for %s / %s" % (a_name, b_name))
        for garbage in (b"\xff" * 40, b"\x7f" * 3, b"\x60"):
            try:
                got = similarity(garbage, load_code("code_weth9.hex"))
            except Exception as exc:  # noqa: BLE001 - the rule under test
                self.fail("similarity raised on garbage bytes: %r" % (exc,))
            self.assertEqual(got, 0.0,
                             msg="garbage has no selectors, so 0.0")

    def test_weth9_belle_nine_sixteenths(self):
        """Rule: the WETH9 vs BELLE score is 9/16 = 0.5625 (used by the
        match_watchlist example), never rounded."""
        got = similarity(load_code("code_weth9.hex"),
                         load_code("code_belle.hex"))
        self._assert_close(got, 9, 16, "9 shared selectors out of 16")


if __name__ == "__main__":
    unittest.main()

