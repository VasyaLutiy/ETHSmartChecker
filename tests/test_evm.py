"""Tests for ethsc.evm: one test per example of the contour component evm.

Offline: all chain data comes from tests/fixtures/*.hex, decoded verbatim
from the eth_getCode result strings. unittest with msg= on every assert.
"""

import os
import unittest

from ethsc import evm

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "tests", "fixtures")


def code_of(name):
    """Runtime Code: decode a tests/fixtures/code_*.hex file."""
    path = os.path.join(FIXTURES, name)
    with open(path, "r") as fh:
        text = fh.read()
    return bytes.fromhex(text.strip()[2:])

WETH9 = code_of("code_weth9.hex")
USDT = code_of("code_usdt.hex")
UNIV2_USDC = code_of("code_univ2_usdc_weth.hex")
UNIV2_WETH_USDT = code_of("code_univ2_weth_usdt.hex")
UNIV3_005 = code_of("code_univ3_usdc_weth_005.hex")
UNIV3_POOL = code_of("code_univ3_pool_e0554a47.hex")
LAUNCH_A = code_of("code_launchtoken_4e67db19.hex")
LAUNCH_B = code_of("code_launchtoken_40676634.hex")
CLONE_A = code_of("code_clone_270df012.hex")
CLONE_B = code_of("code_clone_3b2fac8e.hex")
CLONE_C = code_of("code_clone_2ca7b61b.hex")
DELEGATED = code_of("code_7702_04cfab85.hex")
BELLE = code_of("code_belle.hex")

TRUNCATED_CLONE = CLONE_A[:44]


class DisassembleTests(unittest.TestCase):
    maxDiff = None

    def test_weth9_first_three_instructions(self):
        """Example 1: first three instructions of code_weth9.hex."""
        ins = evm.disassemble(WETH9)
        self.assertEqual(ins[0], (0, 0x60, b"\x60"), msg="instruction 0")
        self.assertEqual(ins[1], (2, 0x60, b"\x40"), msg="instruction 1")
        self.assertEqual(ins[2], (4, 0x52, b""), msg="instruction 2")

    def test_weth9_body_instruction_count(self):
        """Example 2: 1555 instructions over the 3081-byte body of WETH9."""
        body, _ = evm.strip_metadata(WETH9)
        self.assertEqual(len(body), 3081, msg="body length")
        ins = evm.disassemble(body)
        self.assertEqual(len(ins), 1555, msg="instruction count over body")

    def test_truncated_push2_takes_short_arg(self):
        """Example 3: 0x600161ff -> [(0, 0x60, b"\x01"), (2, 0x61, b"\xff")]."""
        ins = evm.disassemble(bytes.fromhex("600161ff"))
        self.assertEqual(ins, [(0, 0x60, b"\x01"), (2, 0x61, b"\xff")],
                         msg="short PUSH2 arg, no exception")

    def test_empty_code(self):
        """Example 4: empty code b"" gives []."""
        self.assertEqual(evm.disassemble(b""), [], msg="empty code")

    def test_garbage_never_raises(self):
        """Guardrail Tolerant Parser: garbage inputs return, never raise."""
        for garbage in (bytes(range(256)), b"\xff" * 10, b"\x7f", b"\x5f"):
            try:
                result = evm.disassemble(garbage)
            except Exception as exc:
                self.fail(msg="disassemble raised on garbage: %r" % (exc,))
            self.assertIsInstance(result, list, msg="result is a list")


class StripMetadataTests(unittest.TestCase):
    maxDiff = None

    def test_weth9_bzzr0_trailer(self):
        """Example 1: WETH9 body 3081, 43-byte trailer a165627a7a72305820."""
        body, trailer = evm.strip_metadata(WETH9)
        self.assertEqual(len(body), 3081, msg="body length")
        self.assertEqual(len(trailer), 43, msg="trailer length")
        self.assertTrue(trailer.hex().startswith("a165627a7a72305820"),
                        msg="bzzr0 trailer start: %s" % trailer.hex())

    def test_univ2_solc_0516_trailer(self):
        """Example 2: Univ2 body 11241, trailer with solc 0.5.16 marker."""
        body, trailer = evm.strip_metadata(UNIV2_USDC)
        self.assertEqual(len(body), 11241, msg="body length")
        self.assertEqual(len(trailer), 52, msg="trailer length")
        h = trailer.hex()
        self.assertTrue(h.startswith("a265627a7a72315820"),
                        msg="bzzr1 trailer start: %s" % h)
        self.assertIn("64736f6c6343000510", h, msg="solc 0.5.16 marker inside")

    def test_univ3_hashless_trailer(self):
        """Example 3: Univ3 body 22130, 12-byte trailer a164...0706000a."""
        body, trailer = evm.strip_metadata(UNIV3_005)
        self.assertEqual(len(body), 22130, msg="body length")
        self.assertEqual(trailer, bytes.fromhex("a164736f6c6343000706000a"),
                         msg="exact 12-byte trailer")

    def test_clone_whole_and_empty_code(self):
        """Example 4: clone of 45 bytes stays whole; b"" gives (b"", b"")."""
        body, trailer = evm.strip_metadata(CLONE_A)
        self.assertEqual(body, CLONE_A, msg="clone body is the whole code")
        self.assertEqual(trailer, b"", msg="clone trailer empty")
        self.assertEqual(evm.strip_metadata(b""), (b"", b""),
                         msg="empty code")

    def test_garbage_never_raises(self):
        """Guardrail Tolerant Parser: garbage inputs never raise."""
        for garbage in (bytes(range(256)), b"\x00\x29", b"\xab\xcd"):
            try:
                result = evm.strip_metadata(garbage)
            except Exception as exc:
                self.fail(msg="strip_metadata raised on %r: %r" % (garbage, exc))
            self.assertIsInstance(result, tuple, msg="result is a tuple")


class ExtractSelectorsTests(unittest.TestCase):
    maxDiff = None

    WETH9_SELECTORS = [
        "0x06fdde03", "0x095ea7b3", "0x18160ddd", "0x23b872dd", "0x2e1a7d4d",
        "0x313ce567", "0x70a08231", "0x95d89b41", "0xa9059cbb", "0xd0e30db0",
        "0xdd62ed3e",
    ]
    USDT_SELECTORS = [
        "0x06fdde03", "0x0753c30c", "0x095ea7b3", "0x0e136b19", "0x0ecb93c0",
        "0x18160ddd", "0x23b872dd", "0x26976e3f", "0x27e235e3", "0x313ce567",
        "0x35390714", "0x3eaaf86b", "0x3f4ba83a", "0x59bf1abe", "0x5c658165",
        "0x5c975abb", "0x70a08231", "0x8456cb59", "0x893d20e8", "0x8da5cb5b",
        "0x95d89b41", "0xa9059cbb", "0xc0324c77", "0xcc872b66", "0xdb006a75",
        "0xdd62ed3e", "0xdd644f72", "0xe47d6060", "0xe4997dc5", "0xe5b5019a",
        "0xf2fde38b", "0xf3bdc228",
    ]

    def test_weth9_published_selectors(self):
        """Example 1: exactly the 11 published WETH9 selectors."""
        got = evm.extract_selectors(WETH9)
        self.assertEqual(got, self.WETH9_SELECTORS,
                         msg="WETH9 selectors (11 published)")

    def test_usdt_32_selectors(self):
        """Example 2: exactly the 32 TetherToken selectors."""
        got = evm.extract_selectors(USDT)
        self.assertEqual(got, self.USDT_SELECTORS, msg="USDT selectors")

    def test_univ2_27_selectors(self):
        """Example 3: 27 selectors incl. 0x022c0d9f and 0x0902f1ac."""
        got = evm.extract_selectors(UNIV2_USDC)
        self.assertEqual(len(got), 27, msg="count: %d" % len(got))
        self.assertIn("0x022c0d9f", got, msg="swap selector present")
        self.assertIn("0x0902f1ac", got, msg="getReserves selector present")

    def test_belle_14_selectors(self):
        """Example 4: 14 selectors incl. 0xf7e58a63 and 0x78051f4d."""
        got = evm.extract_selectors(BELLE)
        self.assertEqual(len(got), 14, msg="count: %d" % len(got))
        self.assertIn("0xf7e58a63", got, msg="Blacklist(address,bool)")
        self.assertIn("0x78051f4d", got, msg="RenounceOwnership(address)")

    def test_clone_and_empty_give_empty(self):
        """Example 5: clone and b"" give []."""
        self.assertEqual(evm.extract_selectors(CLONE_A), [],
                         msg="clone has no dispatcher")
        self.assertEqual(evm.extract_selectors(b""), [], msg="empty code")


class DetectProxyTests(unittest.TestCase):
    maxDiff = None

    def test_two_clones_same_target(self):
        """Example 1: clones 270df012 and 3b2fac8e -> target 0x4181f370..."""
        want = {"kind": "eip1167", "target": "0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb"}
        for name, code in (("270df012", CLONE_A), ("3b2fac8e", CLONE_B)):
            got = evm.detect_proxy(code)
            self.assertEqual(got, want, msg="clone %s" % name)

    def test_third_clone_other_target(self):
        """Example 2: clone 2ca7b61b -> target 0x8b72b9b8..."""
        got = evm.detect_proxy(CLONE_C)
        self.assertEqual(
            got,
            {"kind": "eip1167", "target": "0x8b72b9b8e544f944cdcdf0cdb6194f917ac1eba5"},
            msg="clone 2ca7b61b target")

    def test_eip7702_designator(self):
        """Example 3: 23-byte ef0100 code -> eip7702 target."""
        got = evm.detect_proxy(DELEGATED)
        self.assertEqual(
            got,
            {"kind": "eip7702", "target": "0x0000fb7702036ff9f76044a501ac1aa74cbab16b"},
            msg="EIP-7702 delegate")

    def test_none_cases(self):
        """Example 4: truncated clone, WETH9 and b"" all give None."""
        self.assertIsNone(evm.detect_proxy(TRUNCATED_CLONE),
                          msg="truncated 44-byte clone")
        self.assertIsNone(evm.detect_proxy(WETH9), msg="WETH9")
        self.assertIsNone(evm.detect_proxy(b""), msg="empty code")


class BuildSkeletonTests(unittest.TestCase):
    maxDiff = None

    def _byte_diff(self, a, b):
        return sum(1 for x, y in zip(a, b) if x != y)

    def test_univ3_skeletons_equal(self):
        """Example 1: two UniswapV3Pool deployments -> equal skeletons."""
        self.assertEqual(len(UNIV3_005), 22142, msg="fixture size 005")
        self.assertEqual(len(UNIV3_POOL), 22142, msg="fixture size pool")
        self.assertEqual(self._byte_diff(UNIV3_005, UNIV3_POOL), 74,
                         msg="raw codes differ in 74 bytes")
        self.assertEqual(evm.build_skeleton(UNIV3_005), evm.build_skeleton(UNIV3_POOL),
                         msg="skeletons equal")

    def test_launchtoken_skeletons_equal(self):
        """Example 2: two LaunchToken deployments -> equal skeletons."""
        self.assertEqual(len(LAUNCH_A), 2383, msg="fixture size A")
        self.assertEqual(len(LAUNCH_B), 2383, msg="fixture size B")
        self.assertEqual(self._byte_diff(LAUNCH_A, LAUNCH_B), 58,
                         msg="raw codes differ in 58 bytes")
        self.assertEqual(evm.build_skeleton(LAUNCH_A), evm.build_skeleton(LAUNCH_B),
                         msg="skeletons equal")

    def test_metadata_flip_same_skeleton(self):
        """Example 3: WETH9 with one flipped trailer byte -> same skeleton."""
        flipped = bytearray(WETH9)
        flipped[-5] ^= 0xFF
        sk1 = evm.build_skeleton(WETH9)
        sk2 = evm.build_skeleton(bytes(flipped))
        self.assertEqual(sk1, sk2, msg="skeleton ignores metadata")
        self.assertEqual(len(sk1), 3081, msg="skeleton length equals body")

    def test_weth9_vs_usdt_skeletons_differ(self):
        """Example 4: WETH9 and USDT skeletons differ."""
        self.assertNotEqual(evm.build_skeleton(WETH9), evm.build_skeleton(USDT),
                            msg="different skeletons")

    def test_garbage_never_raises(self):
        """Guardrail Tolerant Parser: garbage inputs never raise."""
        for garbage in (bytes(range(256)), b"", b"\x73\x01\x7f"):
            try:
                result = evm.build_skeleton(garbage)
            except Exception as exc:
                self.fail(msg="build_skeleton raised on %r: %r" % (garbage, exc))
            self.assertIsInstance(result, bytes, msg="result is bytes")


if __name__ == "__main__":
    unittest.main()
