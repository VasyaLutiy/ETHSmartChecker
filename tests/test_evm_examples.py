"""Example-based tests for ethsc/evm.py, written as the independent judge.

Each test docstring names the Function and the example number it checks.
The examples come from docs/TASK_PHASE1.md (contour.yaml examples), with
fixtures described in tests/fixtures/README.md. The code under test is
ethsc/evm.py; this file is written without touching it.
"""

import unittest

from ethsc import evm

FIXTURES_DIR = "tests/fixtures"


def load_code(name):
    """Read a code_*.hex fixture verbatim and decode to bytes."""
    with open("{}/{}".format(FIXTURES_DIR, name), "r") as fh:
        text = fh.read().strip()
    return bytes.fromhex(text[2:])


def count_diff_bytes(a, b):
    assert len(a) == len(b)
    return sum(1 for x, y in zip(a, b) if x != y)


class TestDisassemble(unittest.TestCase):
    maxDiff = None

    def test_disassemble_ex1_weth9_first_three(self):
        """Disassemble example 1: first three instructions of code_weth9.hex."""
        code = load_code("code_weth9.hex")
        ins = evm.disassemble(code)
        self.assertEqual(len(code), 3124, msg="WETH9 code must be 3124 bytes")
        self.assertEqual(
            ins[:3],
            [(0, 0x60, b"\x60"), (2, 0x60, b"\x40"), (4, 0x52, b"")],
            msg="first three instructions must be (0,0x60,'60'), (2,0x60,'40'), (4,0x52,'')",
        )

    def test_disassemble_ex2_weth9_body_count(self):
        """Disassemble example 2: 3081-byte WETH9 body disassembles to 1555 instructions."""
        code = load_code("code_weth9.hex")
        body = code[:-43]
        self.assertEqual(len(body), 3081, msg="body after 43-byte trailer must be 3081 bytes")
        ins = evm.disassemble(body)
        self.assertEqual(len(ins), 1555, msg="3081-byte WETH9 body must give 1555 instructions")

    def test_disassemble_ex3_truncated_push2(self):
        """Disassemble example 3: truncated PUSH2 0x600161ff gives two instructions."""
        code = bytes.fromhex("600161ff")
        ins = evm.disassemble(code)
        self.assertEqual(
            ins,
            [(0, 0x60, b"\x01"), (2, 0x61, b"\xff")],
            msg="0x600161ff must give [(0,0x60,'\\x01'), (2,0x61,'\\xff')]",
        )

    def test_disassemble_ex4_empty_code(self):
        """Disassemble example 4: empty code gives []."""
        ins = evm.disassemble(b"")
        self.assertEqual(ins, [], msg="empty code must disassemble to []")


class TestStripMetadata(unittest.TestCase):
    maxDiff = None

    def test_strip_metadata_ex1_weth9_bzzr0(self):
        """Strip Metadata example 1: WETH9 body 3081, 43-byte bzzr0 trailer."""
        code = load_code("code_weth9.hex")
        self.assertEqual(code[-2:], b"\x00\x29", msg="WETH9 code must end 0x0029")
        body, trailer = evm.strip_metadata(code)
        self.assertEqual(len(body), 3081, msg="WETH9 body must be 3081 bytes")
        self.assertEqual(len(trailer), 43, msg="WETH9 trailer must be 43 bytes")
        self.assertTrue(
            trailer.hex().startswith("a165627a7a72305820"),
            msg="WETH9 trailer must start with a165627a7a72305820 (bzzr0)",
        )

    def test_strip_metadata_ex2_univ2_solc0516(self):
        """Strip Metadata example 2: UniswapV2Pair body 11241, 52-byte trailer with solc 0.5.16."""
        code = load_code("code_univ2_usdc_weth.hex")
        self.assertEqual(len(code), 11293, msg="univ2 pair code must be 11293 bytes")
        body, trailer = evm.strip_metadata(code)
        self.assertEqual(len(body), 11241, msg="univ2 pair body must be 11241 bytes")
        self.assertEqual(len(trailer), 52, msg="univ2 pair trailer must be 52 bytes")
        self.assertTrue(
            trailer.hex().startswith("a265627a7a72315820"),
            msg="univ2 pair trailer must start with a265627a7a72315820",
        )
        self.assertIn(
            bytes.fromhex("64736f6c6343000510"),
            trailer,
            msg="univ2 pair trailer must contain solc 0.5.16 marker 64736f6c6343000510",
        )

    def test_strip_metadata_ex3_univ3_no_hash(self):
        """Strip Metadata example 3: UniswapV3Pool body 22130, trailer a164736f6c6343000706000a."""
        code = load_code("code_univ3_usdc_weth_005.hex")
        self.assertEqual(len(code), 22142, msg="univ3 pool code must be 22142 bytes")
        body, trailer = evm.strip_metadata(code)
        self.assertEqual(len(body), 22130, msg="univ3 pool body must be 22130 bytes")
        self.assertEqual(
            trailer,
            bytes.fromhex("a164736f6c6343000706000a"),
            msg="univ3 pool trailer must be exactly a164736f6c6343000706000a (12 bytes)",
        )

    def test_strip_metadata_ex4_clone_and_empty(self):
        """Strip Metadata example 4: 45-byte clone comes back whole; empty gives (b'', b'')."""
        clone = load_code("code_clone_270df012.hex")
        self.assertEqual(len(clone), 45, msg="clone fixture must be 45 bytes")
        self.assertEqual(clone[-2:], bytes.fromhex("5bf3"), msg="clone must end 0x5bf3")
        body, trailer = evm.strip_metadata(clone)
        self.assertEqual(trailer, b"", msg="clone must have no recognized trailer")
        self.assertEqual(body, clone, msg="clone body must be the whole 45 bytes")
        body2, trailer2 = evm.strip_metadata(b"")
        self.assertEqual((body2, trailer2), (b"", b""), msg="empty code must give (b'', b'')")


class TestExtractSelectors(unittest.TestCase):
    maxDiff = None

    def test_extract_selectors_ex1_weth9_11(self):
        """Extract Selectors example 1: WETH9 gives exactly its 11 published selectors."""
        code = load_code("code_weth9.hex")
        got = evm.extract_selectors(code)
        want = sorted(
            [
                "0x06fdde03", "0x095ea7b3", "0x18160ddd", "0x23b872dd",
                "0x2e1a7d4d", "0x313ce567", "0x70a08231", "0x95d89b41",
                "0xa9059cbb", "0xd0e30db0", "0xdd62ed3e",
            ]
        )
        self.assertEqual(got, want, msg="WETH9 selectors must equal the 11 ABI selectors")

    def test_extract_selectors_ex2_usdt_32(self):
        """Extract Selectors example 2: USDT gives exactly its 32 ABI selectors."""
        code = load_code("code_usdt.hex")
        got = evm.extract_selectors(code)
        want = sorted(
            [
                "0x06fdde03", "0x0753c30c", "0x095ea7b3", "0x0e136b19",
                "0x0ecb93c0", "0x18160ddd", "0x23b872dd", "0x26976e3f",
                "0x27e235e3", "0x313ce567", "0x35390714", "0x3eaaf86b",
                "0x3f4ba83a", "0x59bf1abe", "0x5c658165", "0x5c975abb",
                "0x70a08231", "0x8456cb59", "0x893d20e8", "0x8da5cb5b",
                "0x95d89b41", "0xa9059cbb", "0xc0324c77", "0xcc872b66",
                "0xdb006a75", "0xdd62ed3e", "0xdd644f72", "0xe47d6060",
                "0xe4997dc5", "0xe5b5019a", "0xf2fde38b", "0xf3bdc228",
            ]
        )
        self.assertEqual(got, want, msg="USDT selectors must equal the 32 ABI selectors")

    def test_extract_selectors_ex3_univ2_27(self):
        """Extract Selectors example 3: UniswapV2Pair gives 27 selectors incl. swap and getReserves."""
        code = load_code("code_univ2_usdc_weth.hex")
        got = evm.extract_selectors(code)
        self.assertEqual(len(got), 27, msg="univ2 pair must yield 27 selectors")
        self.assertIn("0x022c0d9f", got, msg="univ2 pair must contain swap 0x022c0d9f")
        self.assertIn("0x0902f1ac", got, msg="univ2 pair must contain getReserves 0x0902f1ac")

    def test_extract_selectors_ex4_belle_14(self):
        """Extract Selectors example 4: BELLE gives 14 selectors incl. Blacklist and RenounceOwnership."""
        code = load_code("code_belle.hex")
        got = evm.extract_selectors(code)
        self.assertEqual(len(got), 14, msg="BELLE must yield 14 selectors")
        self.assertIn("0xf7e58a63", got, msg="BELLE must contain Blacklist 0xf7e58a63")
        self.assertIn("0x78051f4d", got, msg="BELLE must contain RenounceOwnership 0x78051f4d")

    def test_extract_selectors_ex5_clone_and_empty(self):
        """Extract Selectors example 5: clone code and empty code both give []."""
        clone = load_code("code_clone_270df012.hex")
        self.assertEqual(
            evm.extract_selectors(clone),
            [],
            msg="EIP-1167 clone must give [] selectors",
        )
        self.assertEqual(
            evm.extract_selectors(b""),
            [],
            msg="empty code must give [] selectors",
        )


class TestDetectProxy(unittest.TestCase):
    maxDiff = None

    def test_detect_proxy_ex1_two_clones_same_target(self):
        """Detect Proxy example 1: two clones of block 26077729 point to 0x4181f370...."""
        clone1 = load_code("code_clone_270df012.hex")
        clone2 = load_code("code_clone_3b2fac8e.hex")
        want = {"kind": "eip1167", "target": "0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb"}
        got1 = evm.detect_proxy(clone1)
        self.assertEqual(got1, want, msg="clone 0x270df012 must be eip1167 to 0x4181f370...")
        got2 = evm.detect_proxy(clone2)
        self.assertEqual(got2, want, msg="clone 0x3b2fac8e must be eip1167 to 0x4181f370...")

    def test_detect_proxy_ex2_clone_launchtoken_target(self):
        """Detect Proxy example 2: clone 0x2ca7b61b points to 0x8b72b9b8... (LaunchToken)."""
        clone = load_code("code_clone_2ca7b61b.hex")
        got = evm.detect_proxy(clone)
        self.assertEqual(
            got,
            {"kind": "eip1167", "target": "0x8b72b9b8e544f944cdcdf0cdb6194f917ac1eba5"},
            msg="clone 0x2ca7b61b must be eip1167 to 0x8b72b9b8...",
        )

    def test_detect_proxy_ex3_eip7702(self):
        """Detect Proxy example 3: 23-byte EIP-7702 designator gives ef0100 target."""
        code = load_code("code_7702_04cfab85.hex")
        self.assertEqual(len(code), 23, msg="7702 designator must be 23 bytes")
        self.assertEqual(
            code[:3],
            bytes.fromhex("ef0100"),
            msg="7702 designator must start with ef0100",
        )
        got = evm.detect_proxy(code)
        self.assertEqual(
            got,
            {"kind": "eip7702", "target": "0x0000fb7702036ff9f76044a501ac1aa74cbab16b"},
            msg="code_7702_04cfab85 must be eip7702 to 0x0000fb77...",
        )

    def test_detect_proxy_ex4_non_proxies_give_none(self):
        """Detect Proxy example 4: truncated clone, WETH9 and empty code all give None."""
        clone = load_code("code_clone_270df012.hex")
        weth = load_code("code_weth9.hex")
        self.assertIsNone(
            evm.detect_proxy(clone[:44]),
            msg="44-byte truncated clone must give None",
        )
        self.assertIsNone(
            evm.detect_proxy(weth),
            msg="WETH9 runtime code must give None",
        )
        self.assertIsNone(
            evm.detect_proxy(b""),
            msg="empty code must give None",
        )


class TestBuildSkeleton(unittest.TestCase):
    maxDiff = None

    def test_build_skeleton_ex1_univ3_immutable_diff(self):
        """Build Skeleton example 1: two UniswapV3Pool codes differ in 74 PUSH32 bytes; skeletons equal."""
        code1 = load_code("code_univ3_usdc_weth_005.hex")
        code2 = load_code("code_univ3_pool_e0554a47.hex")
        self.assertEqual(len(code1), 22142, msg="first univ3 code must be 22142 bytes")
        self.assertEqual(len(code2), 22142, msg="second univ3 code must be 22142 bytes")
        self.assertEqual(
            count_diff_bytes(code1, code2),
            74,
            msg="raw univ3 codes must differ in exactly 74 bytes",
        )
        sk1 = evm.build_skeleton(code1)
        sk2 = evm.build_skeleton(code2)
        self.assertEqual(sk1, sk2, msg="univ3 skeletons must be equal")

    def test_build_skeleton_ex2_launchtoken_immutable_diff(self):
        """Build Skeleton example 2: two LaunchToken codes differ in 58 bytes of 3 PUSH32; skeletons equal."""
        code1 = load_code("code_launchtoken_4e67db19.hex")
        code2 = load_code("code_launchtoken_40676634.hex")
        self.assertEqual(len(code1), 2383, msg="first launchtoken code must be 2383 bytes")
        self.assertEqual(len(code2), 2383, msg="second launchtoken code must be 2383 bytes")
        self.assertEqual(
            count_diff_bytes(code1, code2),
            58,
            msg="raw launchtoken codes must differ in exactly 58 bytes",
        )
        sk1 = evm.build_skeleton(code1)
        sk2 = evm.build_skeleton(code2)
        self.assertEqual(sk1, sk2, msg="launchtoken skeletons must be equal")

    def test_build_skeleton_ex3_metadata_flip_irrelevant(self):
        """Build Skeleton example 3: flipping a trailer byte does not change the WETH9 skeleton."""
        code = load_code("code_weth9.hex")
        mutated = bytearray(code)
        mutated[-5] ^= 0xFF
        sk1 = evm.build_skeleton(code)
        sk2 = evm.build_skeleton(bytes(mutated))
        self.assertEqual(len(sk1), 3081, msg="WETH9 skeleton must be 3081 bytes")
        self.assertEqual(sk1, sk2, msg="skeleton must ignore the flipped metadata byte")

    def test_build_skeleton_ex4_weth_vs_usdt_differ(self):
        """Build Skeleton example 4: WETH9 and USDT skeletons differ."""
        sk_weth = evm.build_skeleton(load_code("code_weth9.hex"))
        sk_usdt = evm.build_skeleton(load_code("code_usdt.hex"))
        self.assertNotEqual(sk_weth, sk_usdt, msg="WETH9 and USDT skeletons must differ")


if __name__ == "__main__":
    unittest.main()
