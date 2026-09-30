"""One fingerprint per distinct code, and the L2 similarity between codes.

Pure functions over bytes; uses ethsc.evm. No I/O: the module reads no
files, no environment and no network. Every function is a Tolerant
Parser: on garbage or empty input it returns None or a float, never an
exception.
"""

import hashlib
from typing import Optional

from ethsc.evm import (
    build_skeleton,
    detect_proxy,
    disassemble,
    extract_selectors,
    is_std_proxy,
    strip_metadata,
)


def fingerprint(code: bytes) -> Optional[dict]:
    """The analysed identity of one distinct code.

    Returns None for empty code; otherwise a dict with exactly the keys
    code_id (sha256 hex of the raw code), size, skeleton_hash (sha256 hex
    of build_skeleton), selectors (extract_selectors) and proxy
    (detect_proxy). Never raises on garbage bytes.
    """
    if len(code) == 0:
        return None
    return {
        "code_id": hashlib.sha256(code).hexdigest(),
        "size": len(code),
        "skeleton_hash": hashlib.sha256(build_skeleton(code)).hexdigest(),
        "selectors": extract_selectors(code),
        "proxy": detect_proxy(code),
    }


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
    1.0.
    """
    proxy_a = detect_proxy(code_a)
    proxy_b = detect_proxy(code_b)
    if proxy_a is not None or proxy_b is not None:
        if proxy_a is not None and proxy_b is not None \
                and proxy_a["kind"] == proxy_b["kind"] \
                and proxy_a["target"] == proxy_b["target"]:
            return 1.0
        return 0.0
    sel_a = set(extract_selectors(code_a))
    sel_b = set(extract_selectors(code_b))
    if is_std_proxy(code_a) or is_std_proxy(code_b) \
            or not sel_a or not sel_b:
        return 0.0
    union = len(sel_a | sel_b)
    if union == 0:
        return 0.0
    return float(len(sel_a & sel_b)) / float(union)

