"""Judge tests for the phase-11 examples of the fingerprint group.

One test per example in contour.yaml, group fingerprint:
Fingerprint Code example 5, Score Fingerprints examples 1-5.
Docstrings name the Function and the example number. Every value is
read from tests/fixtures and compared exactly.
"""

import copy
import glob
import os
import unittest

from ethsc.fingerprint import fingerprint, score_fingerprints, similarity
from tests.helpers import load_hex

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures")


class TestFingerprintExamplesP11(unittest.TestCase):

    def test_fingerprint_code_example_5(self):
        """Fingerprint Code example 5: std_proxy True, True, False;
        the dict has exactly the six keys."""
        expected_keys = {"code_id", "size", "skeleton_hash", "selectors",
                         "proxy", "std_proxy"}
        for name, expected in [
                ("code_proxy_seed_0c010533.hex", True),
                ("code_proxy_046eee2c.hex", True),
                ("code_weth9.hex", False)]:
            fp = fingerprint(load_hex(name))
            self.assertEqual(set(fp.keys()), expected_keys,
                             msg="Fingerprint Code example 5: keys of %s" % name)
            self.assertIs(fp["std_proxy"], expected,
                          msg="Fingerprint Code example 5: std_proxy of %s" % name)

    def test_score_fingerprints_example_1(self):
        """Score Fingerprints example 1: BELLE vs its copy is 13/15,
        exactly 0.8666666666666667, and equals similarity of the codes."""
        fp_a = fingerprint(load_hex("code_belle.hex"))
        fp_b = fingerprint(load_hex("code_belle_copy_1807090d.hex"))
        score = score_fingerprints(fp_a, fp_b)
        self.assertEqual(score, 0.8666666666666667,
                         msg="Score Fingerprints example 1: score 13/15")
        self.assertEqual(score, similarity(load_hex("code_belle.hex"),
                                           load_hex("code_belle_copy_1807090d.hex")),
                         msg="Score Fingerprints example 1: equals similarity")

    def test_score_fingerprints_example_2(self):
        """Score Fingerprints example 2: the seed proxy against the second
        standard proxy, and against code_weth9, both 0.0."""
        fp_seed = fingerprint(load_hex("code_proxy_seed_0c010533.hex"))
        fp_other = fingerprint(load_hex("code_proxy_046eee2c.hex"))
        fp_weth9 = fingerprint(load_hex("code_weth9.hex"))
        self.assertEqual(score_fingerprints(fp_seed, fp_other), 0.0,
                         msg="Score Fingerprints example 2: proxy vs proxy")
        self.assertEqual(score_fingerprints(fp_seed, fp_weth9), 0.0,
                         msg="Score Fingerprints example 2: proxy vs weth9")

    def test_score_fingerprints_example_3(self):
        """Score Fingerprints example 3: rule (2) reads the dict's std_proxy
        (0.0), and with std_proxy forced False on both sides the five equal
        admin selectors score 1.0."""
        fp_seed = fingerprint(load_hex("code_proxy_seed_0c010533.hex"))
        fp_forced = copy.deepcopy(fp_seed)
        fp_forced["std_proxy"] = True
        self.assertEqual(score_fingerprints(fp_seed, fp_forced), 0.0,
                         msg="Score Fingerprints example 3: rule 2 reads the dict")
        fp_false_a = copy.deepcopy(fp_seed)
        fp_false_b = copy.deepcopy(fp_seed)
        fp_false_a["std_proxy"] = False
        fp_false_b["std_proxy"] = False
        self.assertEqual(score_fingerprints(fp_false_a, fp_false_b), 1.0,
                         msg="Score Fingerprints example 3: 5 equal selectors")

    def test_score_fingerprints_example_4(self):
        """Score Fingerprints example 4: None against a fingerprint, a
        fingerprint against None, and None against None, all 0.0."""
        fp_weth9 = fingerprint(load_hex("code_weth9.hex"))
        self.assertEqual(score_fingerprints(None, fp_weth9), 0.0,
                         msg="Score Fingerprints example 4: None first")
        self.assertEqual(score_fingerprints(fp_weth9, None), 0.0,
                         msg="Score Fingerprints example 4: None second")
        self.assertEqual(score_fingerprints(None, None), 0.0,
                         msg="Score Fingerprints example 4: None both")

    def test_score_fingerprints_example_5(self):
        """Score Fingerprints example 5: over all 361 ordered pairs of the
        19 code_*.hex fixtures, score_fingerprints(fingerprint(a),
        fingerprint(b)) == similarity(a, b)."""
        paths = sorted(glob.glob(os.path.join(FIXTURES, "code_*.hex")))
        self.assertEqual(len(paths), 19, msg="Score Fingerprints example 5: 19 fixtures")
        codes = [load_hex(os.path.basename(path)) for path in paths]
        fingerprints = [fingerprint(code) for code in codes]
        count = 0
        for fp_a in fingerprints:
            for fp_b in fingerprints:
                self.assertEqual(score_fingerprints(fp_a, fp_b),
                                 similarity(codes[fingerprints.index(fp_a)],
                                            codes[fingerprints.index(fp_b)]),
                                 msg="Score Fingerprints example 5: pair %d" % count)
                count += 1
        self.assertEqual(count, 361, msg="Score Fingerprints example 5: 361 pairs")


if __name__ == "__main__":
    unittest.main()
