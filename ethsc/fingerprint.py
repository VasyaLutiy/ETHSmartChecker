"""One fingerprint per distinct code, and the L2 similarity between codes.

Pure functions over bytes; uses ethsc.evm. No I/O: the module reads no
files, no environment and no network. Every function is a Tolerant
Parser: on garbage or empty input it returns None or a float, never an
exception.
"""

import hashlib
from typing import FrozenSet, Optional, Tuple

from ethsc.evm import (
    build_skeleton,
    detect_proxy,
    disassemble,
    extract_selectors,
    is_std_proxy,
    strip_metadata,
)

# The alert thresholds of phase 18: ALERT_MIN is the production alert
# threshold on the Similarity Score (the default min_score of Match
# Watchlist and Recheck Watchlist, of recheck --min and of
# listen/backfill --min); CODE_MIN is the code_similarity a strict seed
# demands on top of it.
ALERT_MIN = 0.75
CODE_MIN = 0.6


def fingerprint(code: bytes) -> Optional[dict]:
    """The analysed identity of one distinct code.

    Returns None for empty code; otherwise a dict with exactly the keys
    code_id (sha256 hex of the raw code), size, skeleton_hash (sha256 hex
    of build_skeleton), selectors (extract_selectors), proxy
    (detect_proxy) and std_proxy (is_std_proxy, a bool). Never raises on
    garbage bytes.
    """
    if len(code) == 0:
        return None
    return {
        "code_id": hashlib.sha256(code).hexdigest(),
        "size": len(code),
        "skeleton_hash": hashlib.sha256(build_skeleton(code)).hexdigest(),
        "selectors": extract_selectors(code),
        "proxy": detect_proxy(code),
        "std_proxy": is_std_proxy(code),
    }


def score_fingerprints(fp_a: Optional[dict], fp_b: Optional[dict]) -> float:
    """The Similarity Score of two Fingerprint dicts, without their bytes.

    The three rules of similarity, in order, each read from the dict:
    (1) if either proxy is not None, 1.0 when both are not None with equal
    kind AND equal target, else 0.0; (2) otherwise 0.0 if either std_proxy
    is true or either selectors list is empty; (3) otherwise the Jaccard
    index of the two selector sets, the float of the division, never
    rounded. None on either side scores 0.0. Symmetric; never raises on
    two dicts of the Fingerprint schema or None; never reads code.
    """
    if fp_a is None or fp_b is None:
        return 0.0
    proxy_a = fp_a["proxy"]
    proxy_b = fp_b["proxy"]
    if proxy_a is not None or proxy_b is not None:
        if proxy_a is not None and proxy_b is not None \
                and proxy_a["kind"] == proxy_b["kind"] \
                and proxy_a["target"] == proxy_b["target"]:
            return 1.0
        return 0.0
    sel_a = set(fp_a["selectors"])
    sel_b = set(fp_b["selectors"])
    if fp_a["std_proxy"] or fp_b["std_proxy"] or not sel_a or not sel_b:
        return 0.0
    return float(len(sel_a & sel_b)) / float(len(sel_a | sel_b))


def _opcode_trigrams(code: bytes) -> set:
    """The set of opcode 3-grams (tuples of consecutive ops) of the body.

    Kept only as a helper for callers outside similarity; the Similarity
    Score no longer calls it. Args are dropped; truncated PUSHes are
    tolerated by the parser.
    """
    body, _ = strip_metadata(code)
    ops = [op for _, op, _ in disassemble(body)]
    grams = set()
    for i in range(len(ops) - 2):
        grams.add((ops[i], ops[i + 1], ops[i + 2]))
    return grams


def opcode_shingles(code: bytes) -> FrozenSet[Tuple[int, ...]]:
    """The set of 5-tuples of consecutive opcodes of the stripped body.

    The op ints of disassemble over the body strip_metadata(code) gives,
    PUSH arguments dropped. A body of fewer than 5 opcodes gives the
    empty frozenset; a truncated PUSH is tolerated as disassemble
    tolerates it. Never raises on empty or garbage bytes.
    """
    body, _ = strip_metadata(code)
    ops = [op for _, op, _ in disassemble(body)]
    grams = set()
    for i in range(len(ops) - 4):
        grams.add((ops[i], ops[i + 1], ops[i + 2], ops[i + 3], ops[i + 4]))
    return frozenset(grams)


def code_similarity(code_a: bytes, code_b: bytes) -> float:
    """Jaccard index in [0, 1] of the opcode 5-gram sets of two codes.

    How alike two codes are as code, not as an interface. 0.0 when
    either shingle set is empty, otherwise the Jaccard index of the two
    sets, the float of the division, never rounded. Symmetric;
    code_similarity(x, x) is 1.0 for any x with a non-empty set. It
    applies none of the three rules of the Similarity Score and is only
    ever a second gate behind it, never a score of its own: similarity()
    and score_fingerprints() do not call it.
    """
    sh_a = opcode_shingles(code_a)
    sh_b = opcode_shingles(code_b)
    if not sh_a or not sh_b:
        return 0.0
    return float(len(sh_a & sh_b)) / float(len(sh_a | sh_b))


def similarity(code_a: bytes, code_b: bytes) -> float:
    """Jaccard index in [0, 1] between two codes, by identity not shape.

    The rule, in order:
    (1) if either code is a recognized delegation (detect_proxy not None),
        the score is 1.0 when both are the same detect_proxy kind AND
        target, else 0.0;
    (2) otherwise, if either code is a standard upgradeable proxy
        (is_std_proxy) or either selector set is empty, the score is 0.0;
    (3) otherwise the Jaccard index of the two non-empty selector sets,
        the float of the division, never rounded.
    Symmetric; similarity(b"", b"") == 0.0; no exception on empty or
    garbage bytes. Two codes with the same non-empty selector set score
    1.0. Since phase 11 this is score_fingerprints of the two
    fingerprints: the rules live in one place.
    """
    return score_fingerprints(fingerprint(code_a), fingerprint(code_b))
