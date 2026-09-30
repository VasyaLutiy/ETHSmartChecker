"""Example-based tests for ethsc/evm.py, one per example of the contour.

Every test's docstring names the Function and the example number it
checks. All data comes from tests/fixtures/; no test opens the network.
"""

import unittest

import ethsc.evm as evm

from helpers import block_codes, load_hex


def distinct_block_codes():
    """The distinct code byte strings of block 26077729 (130 of them)."""
    seen = set()
    out = []
    for text in block_codes().values():
        if text == "0x":
            continue
        code = bytes.fromhex(text[2:])
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


class DisassembleTests(unittest.TestCase):
    def test_example_1_weth9_first_instructions(self):
        """Disassemble example 1: the first three instructions of WETH9."""
        code = load_hex("code_weth9.hex")
        ins = evm.disassemble(code)
        self.assertEqual(
            ins[:3],
            [(0, 0x60, b"\x60"), (2, 0x60, b"\x40"), (4, 0x52, b"")],
            msg="first three instructions must be 0x6060604052",
        )

    def test_example_2_weth9_body_instruction_count(self):
        """Disassemble example 2: 1555 instructions over the 3081-byte body."""
        code = load_hex("code_weth9.hex")
        body = code[:len(code) - 43]
        self.assertEqual(len(body), 3081, msg="body must be 3081 bytes")
        self.assertEqual(len(evm.disassemble(body)), 1555,
                         msg="the body disassembles to 1555 instructions")

    def test_example_3_truncated_push2(self):
        """Disassemble example 3: 0x600161ff, a PUSH2 with one byte left."""
        result = evm.disassemble(bytes.fromhex("600161ff"))
        self.assertEqual(
            result,
            [(0, 0x60, b"\x01"), (2, 0x61, b"\xff")],
            msg="truncated PUSH2 takes the remaining byte and ends",
        )

    def test_example_4_empty_code(self):
        """Disassemble example 4: empty code gives []."""
        self.assertEqual(evm.disassemble(b""), [],
                         msg="empty code gives []")


class StripMetadataTests(unittest.TestCase):
    def test_example_1_weth9_bzzr0(self):
        """Strip Metadata example 1: WETH9 bzzr0 trailer of 43 bytes."""
        body, trailer = evm.strip_metadata(load_hex("code_weth9.hex"))
        self.assertEqual(len(body), 3081, msg="body is 3081 bytes")
        self.assertEqual(len(trailer), 43, msg="trailer is 43 bytes")
        self.assertTrue(trailer.startswith(bytes.fromhex(
            "a165627a7a72305820")), msg="bzzr0 trailer header")

    def test_example_2_univ2_solc0516(self):
        """Strip Metadata example 2: UniswapV2Pair solc 0.5.16 trailer."""
        body, trailer = evm.strip_metadata(load_hex("code_univ2_usdc_weth.hex"))
        self.assertEqual(len(body), 11241, msg="body is 11241 bytes")
        self.assertEqual(len(trailer), 52, msg="trailer is 52 bytes")
        self.assertTrue(trailer.startswith(bytes.fromhex(
            "a265627a7a72315820")), msg="bzzr1 trailer header")
        self.assertIn(bytes.fromhex("64736f6c6343000510"), trailer,
                      msg="trailer contains solc 0.5.16")

    def test_example_3_univ3_bytecodehash_none(self):
        """Strip Metadata example 3: UniswapV3Pool, 12-byte solc trailer."""
        body, trailer = evm.strip_metadata(
            load_hex("code_univ3_usdc_weth_005.hex"))
        self.assertEqual(len(body), 22130, msg="body is 22130 bytes")
        self.assertEqual(trailer, bytes.fromhex("a164736f6c6343000706000a"),
                         msg="trailer is exactly 12 bytes, solc 0.7.6")

    def test_example_4_clone_and_empty(self):
        """Strip Metadata example 4: whole clone back, empty code."""
        clone = load_hex("code_clone_270df012.hex")
        self.assertEqual(len(clone), 45, msg="clone is 45 bytes")
        body, trailer = evm.strip_metadata(clone)
        self.assertEqual((body, trailer), (clone, b""),
                         msg="clone comes back whole with empty trailer")
        self.assertEqual(evm.strip_metadata(b""), (b"", b""),
                         msg="empty code gives (b\"\", b\"\")")


class ExtractSelectorsTests(unittest.TestCase):
    def test_example_1_weth9(self):
        """Extract Selectors example 1: the 11 WETH9 selectors."""
        self.assertEqual(
            evm.extract_selectors(load_hex("code_weth9.hex")),
            ["0x06fdde03", "0x095ea7b3", "0x18160ddd", "0x23b872dd",
             "0x2e1a7d4d", "0x313ce567", "0x70a08231", "0x95d89b41",
             "0xa9059cbb", "0xd0e30db0", "0xdd62ed3e"],
            msg="exactly the 11 published WETH9 selectors",
        )

    def test_example_2_usdt(self):
        """Extract Selectors example 2: the 32 TetherToken selectors."""
        self.assertEqual(
            evm.extract_selectors(load_hex("code_usdt.hex")),
            ["0x06fdde03", "0x0753c30c", "0x095ea7b3", "0x0e136b19",
             "0x0ecb93c0", "0x18160ddd", "0x23b872dd", "0x26976e3f",
             "0x27e235e3", "0x313ce567", "0x35390714", "0x3eaaf86b",
             "0x3f4ba83a", "0x59bf1abe", "0x5c658165", "0x5c975abb",
             "0x70a08231", "0x8456cb59", "0x893d20e8", "0x8da5cb5b",
             "0x95d89b41", "0xa9059cbb", "0xc0324c77", "0xcc872b66",
             "0xdb006a75", "0xdd62ed3e", "0xdd644f72", "0xe47d6060",
             "0xe4997dc5", "0xe5b5019a", "0xf2fde38b", "0xf3bdc228"],
            msg="exactly the 32 TetherToken selectors",
        )

    def test_example_3_univ2(self):
        """Extract Selectors example 3: 27 UniswapV2Pair selectors."""
        sel = evm.extract_selectors(load_hex("code_univ2_usdc_weth.hex"))
        self.assertEqual(len(sel), 27, msg="27 selectors")
        self.assertIn("0x022c0d9f", sel, msg="swap selector present")
        self.assertIn("0x0902f1ac", sel, msg="getReserves selector present")

    def test_example_4_belle(self):
        """Extract Selectors example 4: 14 BELLE selectors."""
        sel = evm.extract_selectors(load_hex("code_belle.hex"))
        self.assertEqual(len(sel), 14, msg="14 selectors")
        self.assertIn("0xf7e58a63", sel,
                      msg="Blacklist(address,bool) selector present")
        self.assertIn("0x78051f4d", sel,
                      msg="RenounceOwnership(address) selector present")

    def test_example_5_clone_and_empty(self):
        """Extract Selectors example 5: clone and empty code give []."""
        self.assertEqual(
            evm.extract_selectors(load_hex("code_clone_270df012.hex")), [],
            msg="the EIP-1167 clone has no dispatcher")
        self.assertEqual(evm.extract_selectors(b""), [],
                         msg="empty code gives []")


class DetectProxyTests(unittest.TestCase):
    def test_example_1_two_clones_same_target(self):
        """Detect Proxy example 1: two clones of the same implementation."""
        expected = {"kind": "eip1167",
                    "target": "0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb"}
        self.assertEqual(evm.detect_proxy(load_hex("code_clone_270df012.hex")),
                         expected, msg="first clone target HolderDistributor")
        self.assertEqual(evm.detect_proxy(load_hex("code_clone_3b2fac8e.hex")),
                         expected, msg="second clone, same target")

    def test_example_2_clone_of_launchtoken(self):
        """Detect Proxy example 2: clone of a different implementation."""
        self.assertEqual(
            evm.detect_proxy(load_hex("code_clone_2ca7b61b.hex")),
            {"kind": "eip1167",
             "target": "0x8b72b9b8e544f944cdcdf0cdb6194f917ac1eba5"},
            msg="target is LaunchToken")

    def test_example_3_eip7702(self):
        """Detect Proxy example 3: the EIP-7702 delegated EOA."""
        self.assertEqual(
            evm.detect_proxy(load_hex("code_7702_04cfab85.hex")),
            {"kind": "eip7702",
             "target": "0x0000fb7702036ff9f76044a501ac1aa74cbab16b"},
            msg="ef0100 designator + delegate address")

    def test_example_4_none_cases(self):
        """Detect Proxy example 4: truncated clone, WETH9, empty code."""
        clone = load_hex("code_clone_270df012.hex")
        self.assertIsNone(evm.detect_proxy(clone[:44]),
                          msg="truncated clone gives None")
        self.assertIsNone(evm.detect_proxy(load_hex("code_weth9.hex")),
                          msg="WETH9 is no proxy")
        self.assertIsNone(evm.detect_proxy(b""),
                          msg="empty code gives None")


class BuildSkeletonTests(unittest.TestCase):
    def test_example_1_univ3_two_deployments(self):
        """Build Skeleton example 1: two UniswapV3Pool deployments."""
        a = load_hex("code_univ3_usdc_weth_005.hex")
        b = load_hex("code_univ3_pool_e0554a47.hex")
        self.assertEqual(len(a), 22142, msg="both are 22142 bytes")
        self.assertEqual(len(b), 22142, msg="both are 22142 bytes")
        diff = sum(1 for x, y in zip(a, b) if x != y)
        self.assertEqual(diff, 74, msg="the raw codes differ in 74 bytes")
        self.assertEqual(evm.build_skeleton(a), evm.build_skeleton(b),
                         msg="the two skeletons are equal")

    def test_example_2_launchtoken_two_deployments(self):
        """Build Skeleton example 2: two LaunchToken deployments."""
        a = load_hex("code_launchtoken_4e67db19.hex")
        b = load_hex("code_launchtoken_40676634.hex")
        self.assertEqual(len(a), 2383, msg="both are 2383 bytes")
        self.assertEqual(len(b), 2383, msg="both are 2383 bytes")
        diff = sum(1 for x, y in zip(a, b) if x != y)
        self.assertEqual(diff, 58, msg="the raw codes differ in 58 bytes")
        self.assertEqual(evm.build_skeleton(a), evm.build_skeleton(b),
                         msg="the two skeletons are equal")

    def test_example_3_metadata_trailer_flip(self):
        """Build Skeleton example 3: a flipped metadata byte changes nothing."""
        code = load_hex("code_weth9.hex")
        copy = bytearray(code)
        copy[-5] ^= 0xFF
        copy = bytes(copy)
        sk1 = evm.build_skeleton(code)
        sk2 = evm.build_skeleton(copy)
        self.assertEqual(sk1, sk2, msg="both skeletons are equal")
        self.assertEqual(len(sk1), 3081, msg="each skeleton is 3081 bytes")
        self.assertEqual(len(sk2), 3081, msg="each skeleton is 3081 bytes")

    def test_example_4_weth9_vs_usdt(self):
        """Build Skeleton example 4: WETH9 and USDT skeletons differ."""
        self.assertNotEqual(
            evm.build_skeleton(load_hex("code_weth9.hex")),
            evm.build_skeleton(load_hex("code_usdt.hex")),
            msg="the skeletons differ")


class FlagRiskTests(unittest.TestCase):
    def test_example_1_weth9(self):
        """Flag Risk example 1: WETH9 has no flag."""
        self.assertEqual(
            evm.risk_flags(load_hex("code_weth9.hex")),
            {"selfdestruct": False, "mutable_delegatecall": False},
            msg="both flags are False",
        )

    def test_example_2_eip1167_clone(self):
        """Flag Risk example 2: an eip1167 clone is never mutable_delegatecall."""
        self.assertEqual(
            evm.risk_flags(load_hex("code_clone_270df012.hex")),
            {"selfdestruct": False, "mutable_delegatecall": False},
            msg="both flags are False",
        )

    def test_example_3_ff_opcode_vs_push_data(self):
        """Flag Risk example 3: 0xff as opcode vs 0xff inside a PUSH."""
        self.assertEqual(
            evm.risk_flags(b"\xff"),
            {"selfdestruct": True, "mutable_delegatecall": False},
            msg="a lone 0xff opcode is selfdestruct",
        )
        self.assertEqual(
            evm.risk_flags(b"\x60\xff"),
            {"selfdestruct": False, "mutable_delegatecall": False},
            msg="0xff inside a PUSH immediate never counts",
        )

    def test_example_4_block_26077729_counts(self):
        """Flag Risk example 4: flag counts over block 26077729."""
        codes = distinct_block_codes()
        self.assertEqual(len(codes), 130, msg="130 distinct codes")
        sd = [c for c in codes if evm.risk_flags(c)["selfdestruct"]]
        md = [c for c in codes if evm.risk_flags(c)["mutable_delegatecall"]]
        both = [c for c in codes if evm.risk_flags(c) ==
                {"selfdestruct": True, "mutable_delegatecall": True}]
        self.assertEqual(len(sd), 1, msg="exactly 1 code has selfdestruct")
        self.assertEqual(len(md), 29, msg="29 codes have mutable_delegatecall")
        self.assertEqual(len(both), 0, msg="no code has both")
        addresses = {a: text for a, text in block_codes().items()
                     if text != "0x"}
        md_addresses = sum(1 for text in addresses.values()
                           if evm.risk_flags(bytes.fromhex(text[2:]))
                           ["mutable_delegatecall"])
        self.assertEqual(md_addresses, 33,
                         msg="33 addresses carry mutable_delegatecall")
        self.assertIn("0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc", addresses,
                      msg="the selfdestruct address is in the block")
        self.assertTrue(
            evm.risk_flags(bytes.fromhex(
                addresses["0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc"][2:]))
            ["selfdestruct"],
            msg="0xfeeeeee4… is the one selfdestruct code")

    def test_example_5_empty_code(self):
        """Flag Risk example 5: empty code gives both False, no exception."""
        self.assertEqual(
            evm.risk_flags(b""),
            {"selfdestruct": False, "mutable_delegatecall": False},
            msg="both flags are False and nothing raises",
        )


if __name__ == "__main__":
    unittest.main()
