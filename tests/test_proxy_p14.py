"""Smoke tests for seeing through standard proxies (phase 14).

Does not re-derive the 28 Contour examples (the probe inlined in the
card's acceptance does that, and tests/test_proxy_examples_p14.py, the
judge's file, covers them one by one): this module only checks that
the four new surfaces -- ingest.slot_address, Store.set_implementation
/implementations, ingest_block's get_storage path and the cli's
seed add --fetch implementation resolution -- are wired up at all,
with short, scalar comparisons. Every stub is imported from
tests/helpers.py; no network anywhere; every db lives in its own
tempfile.mkdtemp() directory.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest

from ethsc.cli import main
from ethsc.ingest import IMPL_SLOT, ingest_block, slot_address
from tests.helpers import (
    FakeRpc, block_codes, block_receipts, load_hex, temp_store,
)

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "fixtures")
with open(os.path.join(_FIXTURES, "storage_26077729.json"),
          "r", encoding="utf-8") as _handle:
    _STORAGE = json.load(_handle)

PROXY = "0x0c0105334a50db16b51b2911c9956539753a2cf8"
IMPL = "0x72b971717e088b59f26d4236be222adb6acd393b"
_IMPL_WORD = "0x" + "00" * 12 + IMPL[2:]
_ZERO_WORD = "0x" + "0" * 64


def _db_path():
    directory = tempfile.mkdtemp(prefix="ethsc-p14-")
    return os.path.join(directory, "ethsc.sqlite")


def _run(argv, rpc=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, rpc=rpc)
    return code, out.getvalue(), err.getvalue()


class SlotAddressTest(unittest.TestCase):

    def test_a_resolving_word_and_the_zero_word(self):
        """Ingest Block 20: slot_address decodes a word, rejects the zero one."""
        self.assertEqual(
            slot_address(_IMPL_WORD), IMPL,
            msg="24 zero digits then an address must decode to that address",
        )
        self.assertIsNone(
            slot_address(_ZERO_WORD),
            msg="the all-zero word must give None (no implementation set)",
        )


class StoreImplementationTest(unittest.TestCase):

    def test_set_implementation_implementations_round_trip(self):
        """Store Codes And Contracts 14: set_implementation then implementations()."""
        store = temp_store()
        try:
            proxy_code_id = store.put_code(
                load_hex("code_proxy_seed_0c010533.hex"))
            store.put_address(PROXY, proxy_code_id, 1, origin="fetched")
            store.put_code(load_hex("code_impl_72b97171.hex"))
            # Mixed case in: implementation() must read back lowercased.
            store.set_implementation(PROXY, IMPL.upper())
            got = store.implementation(PROXY)
        finally:
            store.close()
        self.assertEqual(
            got, IMPL,
            msg="implementation() must read back the lowercased address",
        )


_BLOCK_PROXY = "0x07696dcab55e62cfef953666b29fe1970518cb00"
_BLOCK_PROXY_IMPL = "0xfd03064ff0f29e3113a1198c2694fc8c10bd35e5"


class IngestBlockGetStorageTest(unittest.TestCase):

    def test_ingest_block_resolves_a_candidates_implementation(self):
        """Ingest Block 15: a candidate standard proxy's implementation is fetched too."""
        store = temp_store()
        codes = block_codes()

        def get_code(address, block):
            return codes[address]

        def get_storage(address, slot, block):
            return _STORAGE.get(address, {}).get(slot, _ZERO_WORD)

        try:
            stats = ingest_block(
                26077729, block_receipts(), get_code, store,
                get_storage=get_storage,
            )
            implementation = store.implementation(_BLOCK_PROXY)
        finally:
            store.close()
        self.assertEqual(
            stats["upgrades"], [],
            msg="a first resolution of a known candidate's slot is not an upgrade",
        )
        self.assertEqual(
            implementation, _BLOCK_PROXY_IMPL,
            msg="ingest_block must resolve the block's standard proxy implementation",
        )


class SeedAddFetchImplTest(unittest.TestCase):

    def test_seed_add_fetch_prints_the_implementation_alert(self):
        """Command Line 44: seed add --fetch on a proxy alerts on its impl."""
        rpc = FakeRpc(
            codes={
                PROXY: "0x" + load_hex("code_proxy_seed_0c010533.hex").hex(),
                IMPL: "0x" + load_hex("code_impl_72b97171.hex").hex(),
            },
            storage={PROXY: {IMPL_SLOT: _IMPL_WORD}},
        )
        code, out, err = _run(
            ["--db", _db_path(), "seed", "add", "--fetch", PROXY,
             "--label", "proxy-seed"],
            rpc=rpc,
        )
        self.assertEqual(
            (code, err), (0, ""),
            msg="seed add --fetch on a standard proxy must exit 0, no stderr",
        )
        self.assertEqual(
            out,
            "ALERT\t%s\t%s\tproxy-seed\t1.0000\timpl\n" % (IMPL, PROXY),
            msg="the implementation must alert at 1.0000 with origin impl",
        )
