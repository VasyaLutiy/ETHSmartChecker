"""The eval harness of the similarity alert rule (phase 18).

Given labelled address pairs (Calibration Labels) and a store, evaluate
counts, threshold by threshold, how many same-family pairs alert, how
many must-not pairs alert, and how many unlabelled codes of the store
would alert. Pure orchestration over the Store's public methods and
ethsc.fingerprint: it imports nothing from ethsc.cluster, never from
sqlite3, and reads the store through fingerprints(), code_of() and
code_by_id() only. No I/O of its own, no network, no writes: it never
adds a row to the store.

The alert rule applied here is exactly the production rule of Match
Watchlist: the Similarity Score of the seed's and the candidate's
fingerprints must reach the threshold, and a strict seed additionally
demands a code_similarity of at least CODE_MIN between the two codes.
A benign code counts as interface-only when it alerts on a loose seed
at the threshold while its code_similarity with that seed is below
CODE_MIN (it shares the interface, not the code). Each (labelled
code_id, stored code_id) Fingerprint score is computed at most once per
call and each code's opcode shingles at most once per call, whatever
the number of thresholds, so one call over a large base takes seconds,
not minutes.
"""

import json
import re

from ethsc.fingerprint import (
    CODE_MIN,
    fingerprint,
    opcode_shingles,
    score_fingerprints,
)

# The thresholds evaluate scores by default, in this order.
DEFAULT_GRID = (0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1.0)

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _pair_key(cid_a, cid_b):
    """An unordered cache key for a symmetric pair of code_ids."""
    if cid_a <= cid_b:
        return (cid_a, cid_b)
    return (cid_b, cid_a)


def evaluate(store, labels, thresholds=DEFAULT_GRID, code_min=CODE_MIN):
    """Score the alert rule over the labelled pairs, threshold by threshold.

    labels is a Calibration Labels dict (absent keys mean []). Returns
    {"rows": [...], "missing": [...], "benign_total": int}: one row per
    threshold, in the order given, each {"threshold", "recall",
    "negatives", "benign", "interface_only"}.

    Every address is lowercased first. missing is the sorted list of the
    labelled addresses (of every positive and negative pair) whose
    store.code_of is None, and a pair with a missing side is skipped.
    The code_id of a labelled address is the code_id of
    fingerprint(store.code_of(address)) -- its own bytes, no
    implementation fan-out. Each kept pair is checked in both directions
    (a as the seed, then b); a directed check passes at a threshold when
    score_fingerprints(fp of the seed, fp of the candidate) >= threshold
    and, when the seed is strict, code_similarity of the two codes >=
    code_min. recall is the passing directed checks over all directed
    checks of the kept positive pairs, 0.0 when there is none;
    negatives counts the passing directed checks over the kept negative
    pairs. The benign codes are the code_ids of store.fingerprints()
    that are not the code_id of a labelled address with code;
    benign_total is their number; benign counts those that pass the rule
    for at least one labelled address with code as the seed, and
    interface_only counts those that pass for at least one such seed
    that is not strict while their code_similarity with it is below
    code_min. Fingerprint scores are computed at most once per (labelled
    code_id, stored code_id) pair and opcode shingles at most once per
    code_id in one call, whatever the number of thresholds. Reads the
    store through fingerprints(), code_of() and code_by_id() only;
    writes nothing; never raises on labels of the schema.
    """
    positives = labels.get("positives") or []
    negatives = labels.get("negatives") or []
    strict = set(a.lower() for a in (labels.get("strict") or []))

    labelled = set()
    for pair in positives:
        labelled.add(pair[0].lower())
        labelled.add(pair[1].lower())
    for pair in negatives:
        labelled.add(pair[0].lower())
        labelled.add(pair[1].lower())

    codes = {}
    fps = {}
    id_of = {}
    missing = set()
    for address in sorted(labelled):
        code = store.code_of(address)
        if code is None:
            missing.add(address)
            continue
        fp = fingerprint(code)
        id_of[address] = fp["code_id"]
        codes[fp["code_id"]] = code
        fps[fp["code_id"]] = fp
    labelled_ids = set(fps)

    # The benign stored codes: every code_id of the store that is not a
    # labelled address's code_id.
    benign_ids = []
    for fp in store.fingerprints():
        cid = fp["code_id"]
        if cid in labelled_ids:
            continue
        benign_ids.append(cid)
        fps[cid] = fp
    benign_total = len(benign_ids)

    scores = {}

    def score(cid_a, cid_b):
        key = _pair_key(cid_a, cid_b)
        if key not in scores:
            scores[key] = score_fingerprints(fps[key[0]], fps[key[1]])
        return scores[key]

    shingles = {}

    def shingles_of(cid):
        if cid not in shingles:
            code = codes.get(cid)
            if code is None:
                code = store.code_by_id(cid)
            shingles[cid] = opcode_shingles(code if code else b"")
        return shingles[cid]

    sims = {}

    def sim(cid_a, cid_b):
        key = _pair_key(cid_a, cid_b)
        if key not in sims:
            sh_a = shingles_of(key[0])
            sh_b = shingles_of(key[1])
            if not sh_a or not sh_b:
                value = 0.0
            else:
                value = float(len(sh_a & sh_b)) / float(len(sh_a | sh_b))
            sims[key] = value
        return sims[key]

    def check_passes(seed_addr, cand_addr, threshold):
        """The production rule of Match Watchlist at one threshold."""
        seed_id = id_of[seed_addr]
        cand_id = id_of[cand_addr]
        if score(seed_id, cand_id) < threshold:
            return False
        if seed_addr in strict:
            return sim(seed_id, cand_id) >= code_min
        return True

    # Directed checks of the kept pairs, both ways.
    pos_checks = []
    for pair in positives:
        a = pair[0].lower()
        b = pair[1].lower()
        if a in missing or b in missing:
            continue
        pos_checks.append((a, b))
        pos_checks.append((b, a))
    neg_checks = []
    for pair in negatives:
        a = pair[0].lower()
        b = pair[1].lower()
        if a in missing or b in missing:
            continue
        neg_checks.append((a, b))
        neg_checks.append((b, a))
    seed_addrs = sorted(id_of)

    rows = []
    for threshold in thresholds:
        passed = 0
        for seed_addr, cand_addr in pos_checks:
            if check_passes(seed_addr, cand_addr, threshold):
                passed += 1
        recall = (float(passed) / float(len(pos_checks))
                  if pos_checks else 0.0)
        negs = 0
        for seed_addr, cand_addr in neg_checks:
            if check_passes(seed_addr, cand_addr, threshold):
                negs += 1
        benign = 0
        iface = 0
        for benign_id in benign_ids:
            benign_passes = False
            benign_iface = False
            for seed_addr in seed_addrs:
                seed_id = id_of[seed_addr]
                if score(seed_id, benign_id) < threshold:
                    continue
                if seed_addr in strict:
                    if sim(seed_id, benign_id) >= code_min:
                        benign_passes = True
                else:
                    benign_passes = True
                    if sim(seed_id, benign_id) < code_min:
                        benign_iface = True
                if benign_passes and benign_iface:
                    break
            if benign_passes:
                benign += 1
            if benign_iface:
                iface += 1
        rows.append({
            "threshold": threshold,
            "recall": recall,
            "negatives": negs,
            "benign": benign,
            "interface_only": iface,
        })
    return {
        "rows": rows,
        "missing": sorted(missing),
        "benign_total": benign_total,
    }


def load_labels(path):
    """A Calibration Labels dict from a JSON file, addresses lowercased.

    Returns a dict with exactly the keys positives, negatives and
    strict; absent keys become [] and unknown keys are ignored. A file
    that cannot be read, text that is not JSON, a JSON value that is
    not an object, a positives/negatives value that is not a list of
    two-element lists of address strings matching ^0x[0-9a-fA-F]{40}$,
    or a strict value that is not a list of such strings raise
    ValueError whose str is one line naming the path or the key.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as err:
        raise ValueError("cannot read labels file %s: %s" % (path, err))
    try:
        obj = json.loads(text)
    except ValueError:
        raise ValueError("labels file %s is not valid JSON" % path)
    if not isinstance(obj, dict):
        raise ValueError("labels file %s must hold a JSON object" % path)

    labels = {}
    for key in ("positives", "negatives"):
        value = obj.get(key, [])
        if not isinstance(value, list):
            raise ValueError("%s must be a list in %s" % (key, path))
        pairs = []
        for pair in value:
            if (not isinstance(pair, list) or len(pair) != 2
                    or not all(isinstance(a, str) and ADDRESS_RE.match(a)
                               for a in pair)):
                raise ValueError(
                    "%s must hold [address, address] pairs in %s"
                    % (key, path))
            pairs.append([pair[0].lower(), pair[1].lower()])
        labels[key] = pairs

    strict = obj.get("strict", [])
    if not isinstance(strict, list) or not all(
            isinstance(a, str) and ADDRESS_RE.match(a) for a in strict):
        raise ValueError("strict must be a list of addresses in %s" % path)
    labels["strict"] = [a.lower() for a in strict]
    return labels


def parse_grid(text):
    """A tuple of floats from a comma-separated list, order and duplicates kept.

    Each comma-separated, stripped part goes through float() and must
    lie inside [0, 1]. An empty text, an empty part, a non-float or an
    out-of-range value raise ValueError.
    """
    values = []
    for part in text.split(","):
        part = part.strip()
        try:
            value = float(part)
        except ValueError:
            raise ValueError("invalid threshold %r in grid" % part)
        if value < 0.0 or value > 1.0:
            raise ValueError("threshold %r outside [0, 1]" % part)
        values.append(value)
    return tuple(values)
