"""Example-based tests for ethsc/evm.py, from the contour and fixtures.

One test per example. unittest only, stdlib only, no network: every
input comes from tests/fixtures/ or a literal.
"""

import unittest

from ethsc.evm import (build_skeleton, detect_proxy, disassemble,
                       extract_selectors, is_std_proxy, risk_flags,
                       strip_metadata)

from helpers import block_codes, load_hex

WETH9 = "code_weth9.hex"


class DisassembleTests(unittest.TestCase):
    def test_example_1_first_three_instructions_weth9(self):
        """Disassemble example 1: WETH9 fixture starts 0x6060604052."""
        code = load_hex(WETH9)
        self.assertEqual(len(code), 3124,
                         msg="WETH9 fixture is 3124 bytes")
        ins = disassemble(code)
        self.assertEqual(ins[0], (0, 0x60, b"\x60"),
                         msg="first instruction is PUSH1 0x60 at pc 0")
        self.assertEqual(ins[1], (2, 0x60, b"\x40"),
                         msg="second instruction is PUSH1 0x40 at pc 2")
        self.assertEqual(ins[2], (4, 0x52, b""),
                         msg="third instruction is SSTORE at pc 4")

    def test_example_2_instruction_count_weth9_body(self):
        """Disassemble example 2: the 3081-byte body gives 1555 instructions."""
        code, _ = strip_metadata(load_hex(WETH9))
        self.assertEqual(len(code), 3081, msg="the body is 3081 bytes")
        self.assertEqual(len(disassemble(code)), 1555,
                         msg="1555 instructions counted over the fixture")

    def test_example_3_truncated_push2_tolerated(self):
        """Disassemble example 3: PUSH2 with one byte left does not raise."""
        self.assertEqual(disassemble(bytes.fromhex("600161ff")),
                         [(0, 0x60, b"\x01"), (2, 0x61, b"\xff")],
                         msg="the short PUSH2 takes the byte present")

    def test_example_4_empty_code(self):
        """Disassemble example 4: empty code gives []."""
        self.assertEqual(disassemble(b""), [], msg="empty code gives []")


class StripMetadataTests(unittest.TestCase):
    def test_example_1_weth9_bzzr0_trailer(self):
        """Strip Metadata example 1: WETH9 body 3081, trailer 43, bzzr0."""
        body, trailer = strip_metadata(load_hex(WETH9))
        self.assertEqual(len(body), 3081, msg="body is 3081 bytes")
        self.assertEqual(len(trailer), 43, msg="trailer is 43 bytes")
        self.assertTrue(trailer.hex().startswith("a165627a7a72305820"),
                        msg="trailer starts with the bzzr0 CBOR header")

    def test_example_2_univ2_solc0516_trailer(self):
        """Strip Metadata example 2: UniV2 pair body 11241, trailer 52."""
        body, trailer = strip_metadata(load_hex("code_univ2_usdc_weth.hex"))
        self.assertEqual(len(body), 11241, msg="body is 11241 bytes")
        self.assertEqual(len(trailer), 52, msg="trailer is 52 bytes")
        self.assertTrue(trailer.hex().startswith("a265627a7a72315820"),
                        msg="trailer starts with the bzzr1 CBOR header")
        self.assertIn(bytes.fromhex("64736f6c6343000510"), trailer,
                      msg="trailer names solc 0.5.16")

    def test_example_3_univ3_solc0706_no_bytecodehash(self):
        """Strip Metadata example 3: UniV3 pool trailer exactly 12 bytes."""
        body, trailer = strip_metadata(load_hex("code_univ3_usdc_weth_005.hex"))
        self.assertEqual(len(body), 22130, msg="body is 22130 bytes")
        self.assertEqual(trailer,
                         bytes.fromhex("a164736f6c6343000706000a"),
                         msg="trailer is exactly a164...000a")

    def test_example_4_clone_and_empty(self):
        """Strip Metadata example 4: clone whole, trailer b""; empty code."""
        clone = load_hex("code_clone_270df012.hex")
        self.assertEqual(len(clone), 45, msg="the clone is 45 bytes")
        body, trailer = strip_metadata(clone)
        self.assertEqual(body, clone, msg="the clone comes back whole")
        self.assertEqual(trailer, b"", msg="trailer is b\"\"")
        self.assertEqual(strip_metadata(b""), (b"", b""),
                         msg="empty code gives (b\"\", b\"\")")


class ExtractSelectorsTests(unittest.TestCase):
    def test_example_1_weth9_11_selectors(self):
        """Extract Selectors example 1: exactly the 11 WETH9 selectors."""
        got = extract_selectors(load_hex(WETH9))
        self.assertEqual(got, [
            "0x06fdde03", "0x095ea7b3", "0x18160ddd", "0x23b872dd",
            "0x2e1a7d4d", "0x313ce567", "0x70a08231", "0x95d89b41",
            "0xa9059cbb", "0xd0e30db0", "0xdd62ed3e",
        ], msg="exactly the 11 published WETH9 selectors")

    def test_example_2_usdt_32_selectors(self):
        """Extract Selectors example 2: exactly the 32 USDT selectors."""
        got = extract_selectors(load_hex("code_usdt.hex"))
        self.assertEqual(len(got), 32, msg="exactly 32 selectors")
        self.assertEqual(got, [
            "0x06fdde03", "0x0753c30c", "0x095ea7b3", "0x0e136b19",
            "0x0ecb93c0", "0x18160ddd", "0x23b872dd", "0x26976e3f",
            "0x27e235e3", "0x313ce567", "0x35390714", "0x3eaaf86b",
            "0x3f4ba83a", "0x59bf1abe", "0x5c658165", "0x5c975abb",
            "0x70a08231", "0x8456cb59", "0x893d20e8", "0x8da5cb5b",
            "0x95d89b41", "0xa9059cbb", "0xc0324c77", "0xcc872b66",
            "0xdb006a75", "0xdd62ed3e", "0xdd644f72", "0xe47d6060",
            "0xe4997dc5", "0xe5b5019a", "0xf2fde38b", "0xf3bdc228",
        ], msg="exactly the TetherToken selectors")

    def test_example_3_univ2_27_selectors(self):
        """Extract Selectors example 3: 27 selectors incl. swap, getReserves."""
        got = extract_selectors(load_hex("code_univ2_usdc_weth.hex"))
        self.assertEqual(len(got), 27, msg="27 selectors")
        self.assertIn("0x022c0d9f", got, msg="swap is among them")
        self.assertIn("0x0902f1ac", got, msg="getReserves is among them")

    def test_example_4_belle_14_selectors(self):
        """Extract Selectors example 4: 14 selectors incl. Blacklist."""
        got = extract_selectors(load_hex("code_belle.hex"))
        self.assertEqual(len(got), 14, msg="14 selectors")
        self.assertIn("0xf7e58a63", got,
                      msg="Blacklist(address,bool) is among them")
        self.assertIn("0x78051f4d", got,
                      msg="RenounceOwnership(address) is among them")

    def test_example_5_clone_and_empty_give_empty(self):
        """Extract Selectors example 5: clone and empty code both []."""
        self.assertEqual(extract_selectors(load_hex("code_clone_270df012.hex")),
                         [], msg="the clone has no dispatcher")
        self.assertEqual(extract_selectors(b""), [],
                         msg="empty code gives []")


class DetectProxyTests(unittest.TestCase):
    def test_example_1_two_clones_same_target(self):
        """Detect Proxy example 1: both clones point to 0x4181f370…."""
        expected = {"kind": "eip1167",
                    "target": "0x4181f37093e3a21a4e0d5ef355c5b1938cba5bfb"}
        self.assertEqual(detect_proxy(load_hex("code_clone_270df012.hex")),
                         expected, msg="first clone target")
        self.assertEqual(detect_proxy(load_hex("code_clone_3b2fac8e.hex")),
                         expected, msg="second clone, same target")

    def test_example_2_third_clone_different_target(self):
        """Detect Proxy example 2: clone of 0x8b72b9b8… (LaunchToken)."""
        self.assertEqual(detect_proxy(load_hex("code_clone_2ca7b61b.hex")),
                         {"kind": "eip1167",
                          "target": "0x8b72b9b8e544f944cdcdf0cdb6194f917ac1eba5"},
                         msg="a different implementation")

    def test_example_3_eip7702_designator(self):
        """Detect Proxy example 3: 7702 delegated EOA."""
        self.assertEqual(detect_proxy(load_hex("code_7702_04cfab85.hex")),
                         {"kind": "eip7702",
                          "target": "0x0000fb7702036ff9f76044a501ac1aa74cbab16b"},
                         msg="ef0100 + delegate")

    def test_example_4_truncated_weth_empty_none(self):
        """Detect Proxy example 4: truncated clone, WETH9, empty all None."""
        self.assertIsNone(detect_proxy(load_hex("code_clone_270df012.hex")[:44]),
                          msg="a truncated clone is None")
        self.assertIsNone(detect_proxy(load_hex(WETH9)),
                          msg="WETH9 is not a proxy")
        self.assertIsNone(detect_proxy(b""), msg="empty code is None")


class StandardProxyTests(unittest.TestCase):
    def test_example_1_seed_proxy_true(self):
        """Standard Proxy example 1: the seed proxy has the impl slot."""
        code = load_hex("code_proxy_seed_0c010533.hex")
        self.assertEqual(len(code), 2059, msg="2059 bytes")
        self.assertTrue(is_std_proxy(code),
                        msg="the EIP-1967 impl slot appears as a PUSH32")

    def test_example_2_second_proxy_true(self):
        """Standard Proxy example 2: the second standard proxy is True."""
        code = load_hex("code_proxy_046eee2c.hex")
        self.assertEqual(len(code), 2227, msg="2227 bytes")
        self.assertTrue(is_std_proxy(code),
                        msg="same audited slot, different bytecode")

    def test_example_3_beacon_slot_true(self):
        """Standard Proxy example 3: a body with the beacon slot is True."""
        beacon = bytes.fromhex(
            "a3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50")
        code = b"\x7f" + beacon + b"\x54\xf4"
        self.assertTrue(is_std_proxy(code),
                        msg="the beacon slot is recognized as well")

    def test_example_4_weth_clone_empty_false(self):
        """Standard Proxy example 4: WETH9, clone and empty all False."""
        self.assertFalse(is_std_proxy(load_hex(WETH9)),
                         msg="no audited slot immediate")
        self.assertFalse(is_std_proxy(load_hex("code_clone_270df012.hex")),
                         msg="a clone bakes its target in, not a slot")
        self.assertFalse(is_std_proxy(b""), msg="empty code is False")


class BuildSkeletonTests(unittest.TestCase):
    def test_example_1_univ3_skeletons_equal(self):
        """Build Skeleton example 1: two UniV3Pool skeletons are equal."""
        a = load_hex("code_univ3_usdc_weth_005.hex")
        b = load_hex("code_univ3_pool_e0554a47.hex")
        self.assertEqual(len(a), 22142, msg="first is 22142 bytes")
        self.assertEqual(len(b), 22142, msg="second is 22142 bytes")
        diff = sum(1 for x, y in zip(a, b) if x != y)
        self.assertEqual(diff, 74,
                         msg="the raw codes differ in 74 bytes")
        self.assertEqual(build_skeleton(a), build_skeleton(b),
                         msg="the two skeletons are equal")

    def test_example_2_launchtoken_skeletons_equal(self):
        """Build Skeleton example 2: two LaunchToken skeletons are equal."""
        a = load_hex("code_launchtoken_4e67db19.hex")
        b = load_hex("code_launchtoken_40676634.hex")
        self.assertEqual(len(a), 2383, msg="first is 2383 bytes")
        self.assertEqual(len(b), 2383, msg="second is 2383 bytes")
        diff = sum(1 for x, y in zip(a, b) if x != y)
        self.assertEqual(diff, 58,
                         msg="58 bytes differ inside 3 PUSH32 immediates")
        self.assertEqual(build_skeleton(a), build_skeleton(b),
                         msg="the two skeletons are equal")

    def test_example_3_metadata_flip_same_skeleton(self):
        """Build Skeleton example 3: flipping a trailer byte changes nothing."""
        code = load_hex(WETH9)
        flipped = code[:-5] + bytes([code[-5] ^ 0xFF]) + code[-4:]
        skel = build_skeleton(code)
        self.assertEqual(build_skeleton(flipped), skel,
                         msg="both skeletons are equal")
        self.assertEqual(len(skel), 3081, msg="each skeleton is 3081 bytes")

    def test_example_4_weth_vs_usdt_differ(self):
        """Build Skeleton example 4: WETH9 and USDT skeletons differ."""
        self.assertNotEqual(build_skeleton(load_hex(WETH9)),
                            build_skeleton(load_hex("code_usdt.hex")),
                            msg="different contracts, different skeletons")


class FlagRiskTests(unittest.TestCase):
    def test_example_1_weth9_both_false(self):
        """Flag Risk example 1: WETH9 has neither flag."""
        flags = risk_flags(load_hex(WETH9))
        self.assertFalse(flags["selfdestruct"],
                         msg="no SELFDESTRUCT in the WETH9 body")
        self.assertFalse(flags["mutable_delegatecall"],
                         msg="no DELEGATECALL in the WETH9 body")

    def test_example_2_clone_both_false(self):
        """Flag Risk example 2: an eip1167 clone is never mutable_delegatecall."""
        flags = risk_flags(load_hex("code_clone_270df012.hex"))
        self.assertFalse(flags["selfdestruct"], msg="no SELFDESTRUCT")
        self.assertFalse(flags["mutable_delegatecall"],
                         msg="the clone bakes its target into the code")

    def test_example_3_ff_opcode_vs_push_data(self):
        """Flag Risk example 3: 0xff as opcode counts, as PUSH data does not."""
        self.assertTrue(risk_flags(b"\xff")["selfdestruct"],
                        msg="a bare SELFDESTRUCT opcode")
        flags = risk_flags(b"\x60\xff")
        self.assertFalse(flags["selfdestruct"],
                         msg="0xff as PUSH1 data never counts")
        self.assertFalse(flags["mutable_delegatecall"],
                         msg="no delegatecall either way")

    def test_example_4_std_proxy_both_false(self):
        """Flag Risk example 4: a standard EIP-1967 proxy is excluded."""
        flags = risk_flags(load_hex("code_proxy_seed_0c010533.hex"))
        self.assertFalse(flags["selfdestruct"], msg="no SELFDESTRUCT")
        self.assertFalse(flags["mutable_delegatecall"],
                         msg="is_std_proxy excludes the audited slot proxy")

    def test_example_5_block_26077729_counts(self):
        """Flag Risk example 5: 1 selfdestruct code, 12 mutable_delegatecall."""
        codes = {}
        for address, text in sorted(block_codes().items()):
            if text != "0x":
                codes.setdefault(bytes.fromhex(text[2:]), []).append(address)
        selfd = []
        mutable = []
        for code, addresses in codes.items():
            flags = risk_flags(code)
            if flags["selfdestruct"]:
                selfd.append(addresses)
            if flags["mutable_delegatecall"]:
                mutable.append(addresses)
        self.assertEqual(len(selfd), 1, msg="exactly 1 selfdestruct code")
        self.assertEqual(selfd[0],
                         ["0xfeeeeee44046c3f61a8cc081e0918ef0de0a7ffc"],
                         msg="the selfdestruct address")
        self.assertEqual(len(mutable), 12,
                         msg="exactly 12 mutable_delegatecall codes")
        self.assertEqual(sum(len(a) for a in mutable), 13,
                         msg="over 13 addresses")
        for addresses in selfd:
            for addr in addresses:
                for other in mutable:
                    self.assertNotIn(addr, other,
                                     msg="no code has both flags")

    def test_example_6_empty_code(self):
        """Flag Risk example 6: empty code is both False, nothing raises."""
        flags = risk_flags(b"")
        self.assertFalse(flags["selfdestruct"], msg="selfdestruct False")
        self.assertFalse(flags["mutable_delegatecall"],
                         msg="mutable_delegatecall False")


if __name__ == "__main__":
    unittest.main()
