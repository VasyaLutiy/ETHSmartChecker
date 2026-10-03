"""Judge tests for group calibrate, phase 18 (TASK_PHASE18 §3.2).

One test per Contour example: Evaluate Calibration examples 1-4 and
Load Labels examples 1-4. The store under evaluate() is the phase-18
helper belle_block_db() (block 26077729 plus the BELLE family: 211
addresses, 135 codes); labels files are written by write_labels() into
fresh tempfile.mkdtemp() directories. Offline, stdlib only.
"""

import os
import unittest

from ethsc.calibrate import evaluate, load_labels, parse_grid
from ethsc.store import Store

from tests.helpers import belle_block_db, write_labels

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures")

# The addresses of the Contour examples.
BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
COPY_1807 = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"
UNIV2_A = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
UNIV2_B = "0x22052a1a0f5a3d2839d71c458f177e68b0e73963"
MISSING = "0x9999999999999999999999999999999999999999"
SHIB = "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce"


def example_labels(strict):
    """The labels of Evaluate Calibration examples 1-3."""
    return {
        "positives": [
            [BELLE, COPY_1807],
            [UNIV2_A, UNIV2_B],
            [BELLE, MISSING],
        ],
        "negatives": [[BELLE, SHIB]],
        "strict": strict,
    }


class EvaluateCalibrationExamples(unittest.TestCase):
    """Evaluate Calibration examples 1-4 over belle_block_db()."""

    def test_example_1_strict_grid(self):
        path = belle_block_db()
        store = Store(path)
        try:
            result = evaluate(store, example_labels([BELLE]),
                              (0.7, 0.75, 0.8, 0.9))
        finally:
            store.close()
        self.assertEqual(result["missing"],
                         ["0x9999999999999999999999999999999999999999"])
        self.assertEqual(result["benign_total"], 131)
        rows = result["rows"]
        self.assertEqual(len(rows), 4)
        expected = [
            (0.7, 1.0, 1, 6, 5),
            (0.75, 1.0, 0, 6, 2),
            (0.8, 1.0, 0, 4, 0),
            (0.9, 0.5, 0, 3, 0),
        ]
        for row, (threshold, recall, negatives, benign, iface) in \
                zip(rows, expected):
            self.assertEqual(row["threshold"], threshold)
            self.assertEqual(row["recall"], recall)
            self.assertEqual(row["negatives"], negatives)
            self.assertEqual(row["benign"], benign)
            self.assertEqual(row["interface_only"], iface)
        self.assertEqual([row["threshold"] for row in rows],
                         [0.7, 0.75, 0.8, 0.9])

    def test_example_2_strict_lowercased(self):
        path = belle_block_db()
        store = Store(path)
        try:
            loose = evaluate(store, example_labels([]), (0.7,))
            strict = evaluate(
                store,
                example_labels(
                    ["0x34C6211621F2763C60EB007DC2AE91090A2D22F6"]),
                (0.7,))
        finally:
            store.close()
        self.assertEqual(loose["rows"],
                         [{"threshold": 0.7, "recall": 1.0,
                           "negatives": 2, "benign": 6,
                           "interface_only": 5}])
        self.assertEqual(strict["rows"],
                         [{"threshold": 0.7, "recall": 1.0,
                           "negatives": 1, "benign": 6,
                           "interface_only": 5}])

    def test_example_3_default_grid(self):
        path = belle_block_db()
        store = Store(path)
        try:
            result = evaluate(store, example_labels([BELLE]))
        finally:
            store.close()
        rows = result["rows"]
        self.assertEqual([row["threshold"] for row in rows],
                         [0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0])
        expected = [
            (0.5, 1.0, 1, 19, 18),
            (0.6, 1.0, 1, 9, 8),
            (0.7, 1.0, 1, 6, 5),
            (0.75, 1.0, 0, 6, 2),
            (0.8, 1.0, 0, 4, 0),
            (0.9, 0.5, 0, 3, 0),
            (1.0, 0.5, 0, 3, 0),
        ]
        for row, (threshold, recall, negatives, benign, iface) in \
                zip(rows, expected):
            self.assertEqual(row["threshold"], threshold)
            self.assertEqual(row["recall"], recall)
            self.assertEqual(row["negatives"], negatives)
            self.assertEqual(row["benign"], benign)
            self.assertEqual(row["interface_only"], iface)
        self.assertEqual(result["benign_total"], 131)

    def test_example_4_empty_and_skipped_labels(self):
        path = belle_block_db()
        store = Store(path)
        try:
            empty = evaluate(store, {}, (0.5, 1.0))
            skipped = evaluate(
                store,
                {"positives": [[BELLE, MISSING]]},
                (0.75,))
        finally:
            store.close()
        self.assertEqual(empty["rows"],
                         [{"threshold": 0.5, "recall": 0.0,
                           "negatives": 0, "benign": 0,
                           "interface_only": 0},
                          {"threshold": 1.0, "recall": 0.0,
                           "negatives": 0, "benign": 0,
                           "interface_only": 0}])
        self.assertEqual(empty["missing"], [])
        self.assertEqual(empty["benign_total"], 135)
        self.assertEqual(skipped["rows"],
                         [{"threshold": 0.75, "recall": 0.0,
                           "negatives": 0, "benign": 4,
                           "interface_only": 0}])
        self.assertEqual(skipped["missing"],
                         ["0x9999999999999999999999999999999999999999"])
        self.assertEqual(skipped["benign_total"], 134)


class LoadLabelsExamples(unittest.TestCase):
    """Load Labels examples 1-4."""

    def test_example_1_lowercase_and_unknown_keys(self):
        path = write_labels({
            "positives": [
                ["0xAB000000000000000000000000000000000000CD",
                 "0x0000000000000000000000000000000000000001"]],
            "note": "x",
        })
        self.assertEqual(
            load_labels(path),
            {"positives": [
                ["0xab000000000000000000000000000000000000cd",
                 "0x0000000000000000000000000000000000000001"]],
             "negatives": [],
             "strict": []})

    def test_example_2_bad_inputs(self):
        bad_paths = [
            os.path.join(os.path.realpath(
                write_labels({})), "no-such-labels.json"),
        ]
        # A path that does not exist, inside a fresh mkdtemp directory.
        bad_paths = [write_labels({}) + ".missing"]
        contents = [
            "[]",
            "{",
            '{"negatives": [["0x12",'
            ' "0x0000000000000000000000000000000000000001"]]}',
            '{"strict":'
            ' "0x0000000000000000000000000000000000000001"}',
            '{"positives":'
            ' [["0x0000000000000000000000000000000000000001"]]}',
        ]
        paths = [write_labels_raw(text) for text in contents]
        for path in bad_paths + paths:
            with self.assertRaises(ValueError) as caught:
                load_labels(path)
            message = str(caught.exception)
            self.assertTrue(message)
            self.assertNotIn("\n", message)

    def test_example_3_parse_grid(self):
        self.assertEqual(parse_grid("0.7,0.75, 0.8"), (0.7, 0.75, 0.8))
        self.assertEqual(parse_grid("1,0"), (1.0, 0.0))
        for text in ("", "0.5,", "0.5,abc", "1.5", "-0.1"):
            with self.assertRaises(ValueError):
                parse_grid(text)

    def test_example_4_fixture_labels(self):
        path = os.path.join(_FIXTURES, "calibration_labels.json")
        labels = load_labels(path)
        self.assertEqual(len(labels["positives"]), 95)
        self.assertEqual(len(labels["negatives"]), 8)
        self.assertEqual(
            labels["strict"],
            ["0xa0ff0e694275023f4986dc3ca12a6eb5d6056c62",
             "0xc0a6b8c534fad86df8fa1abb17084a70f86eddc1"])


def write_labels_raw(text):
    """A labels file holding exactly the given text, in a fresh dir."""
    import tempfile
    directory = tempfile.mkdtemp(prefix="ethsc-labels-raw-")
    path = os.path.join(directory, "labels.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


if __name__ == "__main__":
    unittest.main()
