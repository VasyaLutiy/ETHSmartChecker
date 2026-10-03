"""Smoke tests for phase 18: opcode_shingles and code_similarity."""

from ethsc.fingerprint import (
    ALERT_MIN,
    CODE_MIN,
    code_similarity,
    opcode_shingles,
    similarity,
)
from tests.helpers import load_hex


def test_constants():
    assert ALERT_MIN == 0.75
    assert CODE_MIN == 0.6


def test_opcode_shingles_happy_path():
    sh = opcode_shingles(load_hex("code_weth9.hex"))
    assert isinstance(sh, frozenset)
    assert len(sh) > 0
    # five simple opcodes give exactly one 5-tuple of ints
    body = b"\x01\x02\x03\x04\x05"
    grams = opcode_shingles(body)
    assert grams == {(1, 2, 3, 4, 5)}


def test_opcode_shingles_short_and_empty():
    assert opcode_shingles(b"") == frozenset()
    assert opcode_shingles(b"\x60\x00\x60\x00") == frozenset()  # 2 opcodes
    assert len(opcode_shingles(b"\x60\x00" * 5)) == 1  # exactly 5 opcodes
    assert len(opcode_shingles(b"\xfe\xff\x7f")) == 0  # truncated PUSH32


def test_code_similarity_happy_path():
    belle = load_hex("code_belle.hex")
    copy = load_hex("code_belle_copy_1807090d.hex")
    weth = load_hex("code_weth9.hex")
    assert code_similarity(belle, copy) == 920 / 929
    assert code_similarity(belle, copy) == code_similarity(copy, belle)
    assert code_similarity(belle, weth) == 209 / 1291
    assert code_similarity(belle, belle) == 1.0


def test_code_similarity_tolerant_and_independent():
    assert code_similarity(b"", load_hex("code_weth9.hex")) == 0.0
    assert code_similarity(b"\x60\x00\x60\x00",
                           b"\x60\x00\x60\x00") == 0.0
    # similarity does not call code_similarity: the selector rules stand
    assert similarity(load_hex("code_clone_270df012.hex"),
                      load_hex("code_clone_2ca7b61b.hex")) == 0.0
