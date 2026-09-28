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

    Args are dropped; truncated PUSHes are tolerated by the parser.
    """
    body, _ = strip_metadata(code)
    ops = [op for _, op, _ in disassemble(body)]
    grams = set()
    for i in range(len(ops) - 2):
        grams.add((ops[i], ops[i + 1], ops[i + 2]))
    return grams


def similarity(code_a: bytes, code_b: bytes) -> float:
    """Jaccard index in [0, 1] between two codes.

    Selector sets when both are non-empty, otherwise the opcode 3-gram
    sets of the two stripped bodies. 0.0 when both sets are empty.
    Symmetric; identical code gives 1.0.
    """
    sel_a = set(extract_selectors(code_a))
    sel_b = set(extract_selectors(code_b))
    if sel_a and sel_b:
        union = len(sel_a | sel_b)
        if union == 0:
            return 0.0
        return float(len(sel_a & sel_b)) / float(union)
    gram_a = _opcode_trigrams(code_a)
    gram_b = _opcode_trigrams(code_b)
    union = len(gram_a | gram_b)
    if union == 0:
        return 0.0
    return float(len(gram_a & gram_b)) / float(union)
