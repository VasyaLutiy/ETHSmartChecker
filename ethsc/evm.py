"""Pure bytecode analysis over runtime code given as bytes.

No I/O: the module reads no files, no environment and no network.
Every function is a Tolerant Parser: on truncated, garbage or empty
input it returns [] or None or keeps the bytes, and never raises.
"""

from typing import List, Optional, Tuple


def disassemble(code: bytes) -> List[Tuple[int, int, bytes]]:
    """Disassemble runtime code into (pc, op, arg) tuples, in code order.

    Every byte that is not a PUSH immediate is an instruction, including
    undefined opcodes. PUSH1..PUSH32 are 0x60..0x7f, the immediate length
    is n = op - 0x5f; a PUSH whose immediate runs past the end of the code
    takes the bytes that are there (a shorter arg) and ends the list.
    PUSH0 (0x5f) has no immediate. Empty code gives [].
    """
    out = []  # type: List[Tuple[int, int, bytes]]
    i = 0
    n = len(code)
    while i < n:
        op = code[i]
        if 0x60 <= op <= 0x7F:
            k = op - 0x5F
            arg = code[i + 1:i + 1 + k]
            out.append((i, op, arg))
            i += 1 + len(arg)
            if len(arg) < k:
                break
        else:
            out.append((i, op, b""))
            i += 1
    return out


def strip_metadata(code: bytes) -> Tuple[bytes, bytes]:
    """Split off the solc CBOR metadata appended at the end of runtime code.

    Let n be the big-endian value of the last 2 bytes. When len(code) >= 2,
    0 < n <= len(code) - 2 and the byte at len(code) - 2 - n is a CBOR map
    header 0xa1..0xa5, the trailer is the last n + 2 bytes and the body is
    everything before it. Otherwise body is the whole code and trailer is
    b"". No CBOR decoding. Never raises.
    """
    if len(code) < 2:
        return (code, b"")
    n = (code[-2] << 8) | code[-1]
    if n <= 0 or n > len(code) - 2:
        return (code, b"")
    pos = len(code) - 2 - n
    header = code[pos]
    if not (0xA1 <= header <= 0xA5):
        return (code, b"")
    return (code[:pos], code[pos:])


def extract_selectors(code: bytes) -> List[str]:
    """Extract the distinct 4-byte selectors of the dispatcher, sorted.

    A selector is the arg of a PUSH4 (0x63) instruction with a 4-byte arg
    when one of the next two instructions is EQ (0x14); this covers both
    the DUP1 PUSH4 s EQ and the PUSH4 s DUP2 EQ dispatcher shapes and skips
    the PUSH4 used by GT/LT binary-search splits and by masks. Code with
    no dispatcher gives [].
    """
    body, _ = strip_metadata(code)
    ins = disassemble(body)
    selectors = set()
    for idx, (pc, op, arg) in enumerate(ins):
        if op == 0x63 and len(arg) == 4:
            nxt = ins[idx + 1][1] if idx + 1 < len(ins) else None
            nxt2 = ins[idx + 2][1] if idx + 2 < len(ins) else None
            if nxt == 0x14 or nxt2 == 0x14:
                selectors.add("0x" + arg.hex())
    return sorted(selectors)


def detect_proxy(code: bytes) -> Optional[dict]:
    """Recognize the exact EIP-1167 minimal proxy and the EIP-7702 designator.

    eip1167: exactly 45 bytes, 363d3d373d3d3d363d73 + 20 address bytes +
    5af43d82803e903d91602b57fd5bf3. eip7702: exactly 23 bytes, ef0100 +
    20 address bytes. Anything else, including a truncated clone and the
    shortened vanity-address variants of EIP-1167, gives None.
    """
    EIP1167_HEAD = bytes.fromhex("363d3d373d3d3d363d73")
    EIP1167_TAIL = bytes.fromhex("5af43d82803e903d91602b57fd5bf3")
    if len(code) == 45 and code[:10] == EIP1167_HEAD and code[30:] == EIP1167_TAIL:
        return {"kind": "eip1167", "target": "0x" + code[10:30].hex()}
    if len(code) == 23 and code[:3] == bytes.fromhex("ef0100"):
        return {"kind": "eip7702", "target": "0x" + code[3:].hex()}
    return None


def build_skeleton(code: bytes) -> bytes:
    """Re-serialize the stripped body with PUSH20/PUSH32 immediates zeroed.

    The length equals the body length. A truncated PUSH20 or PUSH32 masks
    only the bytes present. Same compiler output with a different metadata
    trailer gives the same skeleton.
    """
    body, _ = strip_metadata(code)
    ins = disassemble(body)
    out = bytearray()
    pos = 0
    for pc, op, arg in ins:
        # padding bytes skipped by the tolerant parser stay verbatim
        out.extend(body[pos:pc])
        pos = pc
        out.append(op)
        pos += 1
        if op in (0x73, 0x7F):
            out.extend(b"\x00" * len(arg))
        else:
            out.extend(arg)
        pos += len(arg)
    out.extend(body[pos:])
    return bytes(out)
