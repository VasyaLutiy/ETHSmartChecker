"""Smoke tests for the ethsc CLI: exit codes and short output strings.

Completeness lives in the acceptance probe and the judge card; this
file only checks imports, one happy path per subcommand family and one
usage/tolerant case. Fakes and fixture loaders come from tests.helpers;
no network is opened.
"""

import contextlib
import io
import os
import tempfile
import unittest

from ethsc.cli import main
from ethsc.rpc import RpcError
from ethsc.store import Store
from tests.helpers import FakeRpc, block_codes, load_hex

_PAIR = "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"
_BELLE = "0x34c6211621f2763c60eb007dc2ae91090a2d22f6"
_COPY = "0x1807090dd15a6f58e00fd769e32ebf20ee610385"


def _run(argv, rpc, sleep=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv, rpc=rpc, sleep=sleep)
    return code, out.getvalue(), err.getvalue()


def _fill(path):
    """Fill the db at path with every candidate of block 26077729."""
    store = Store(path)
    codes = block_codes()
    for address in sorted(codes):
        text = codes[address]
        if text == "0x":
            store.put_address(address, None, 26077729)
        else:
            store.put_address(
                address, store.put_code(bytes.fromhex(text[2:])), 26077729
            )
    store.close()


class CliSmoke(unittest.TestCase):
    maxDiff = None

    def test_main_importable(self):
        self.assertTrue(callable(main), msg="ethsc.cli.main missing")

    def test_backfill_prints_alert(self):
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        store = Store(path)
        store.put_address(
            _BELLE, store.put_code(load_hex("code_belle.hex")), 1
        )
        store.add_seed(_BELLE, "BELLE honeypot")
        store.close()
        rpc = FakeRpc(
            codes={_COPY: "0x" + load_hex("code_belle_copy_1807090d.hex").hex()},
            receipts=[{"to": _COPY}],
        )
        code, out, err = _run(
            ["--db", path, "backfill", "--from", "26077729",
             "--to", "26077729"],
            rpc,
        )
        self.assertEqual(code, 0, msg="backfill exit %d, err=%r" % (code, err))
        self.assertEqual(
            out,
            "ALERT\t%s\t%s\tBELLE honeypot\t0.8667\n" % (_COPY, _BELLE),
            msg="alert line wrong",
        )

    def test_read_commands(self):
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        code, out, err = _run(["--db", path, "clusters", "top"], FakeRpc())
        self.assertEqual(code, 0, msg="clusters top exit")
        self.assertEqual(len(out.strip().splitlines()), 15,
                         msg="clusters top lines")
        code, out, err = _run(
            ["--db", path, "similar", _PAIR, "--min", "0.8"], FakeRpc()
        )
        self.assertEqual(code, 0, msg="similar exit")
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 4, msg="similar lines")
        self.assertEqual(lines[-1].split("\t")[-1], "0.8125",
                         msg="similar last score")
        self.assertEqual(err, "", msg="stderr not empty")

    def test_usage_and_tolerant(self):
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        _fill(path)
        code, out, err = _run(
            ["--db", path, "similar", "not-an-address"], FakeRpc()
        )
        self.assertEqual(code, 2, msg="bad address exit")
        self.assertEqual(out, "", msg="stdout on usage error")
        code, out, err = _run(["--db", path], FakeRpc())
        self.assertEqual(code, 2, msg="missing command exit")
        code, out, err = _run(
            ["--db", path, "cluster", "0x" + "11" * 20], FakeRpc()
        )
        self.assertEqual(code, 0, msg="unknown cluster addr exit")
        self.assertEqual(out, "", msg="unknown cluster addr output")

    def test_listen_interrupt(self):
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        store = Store(path)
        store.set_progress(26077728)
        store.close()
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            raise KeyboardInterrupt()

        code, out, err = _run(
            ["--db", path, "listen"], FakeRpc(head="0x18dea21"),
            sleep=fake_sleep,
        )
        self.assertEqual(code, 0, msg="listen interrupt exit")
        self.assertEqual(sleeps, [12], msg="sleep calls")
        again = Store(path)
        progress = again.get_progress()
        again.close()
        self.assertEqual(progress, 26077729, msg="listen progress")

    def test_listen_interrupt_inside_ingest(self):
        """Ctrl-C on the first eth_getCode: exit 0, no pause, no output."""
        path = os.path.join(tempfile.mkdtemp(), "ethsc.sqlite")
        store = Store(path)
        store.set_progress(26077728)
        store.close()

        class _InterruptingCodes(dict):
            def __getitem__(self, key):
                raise KeyboardInterrupt()

        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            return None

        code, out, err = _run(
            ["--db", path, "listen"],
            FakeRpc(codes=_InterruptingCodes(block_codes()),
                    head="0x18dea21"),
            sleep=fake_sleep,
        )
        self.assertEqual(code, 0, msg="interrupt inside ingest exit")
        self.assertEqual(err, "", msg="stderr on interrupt inside ingest")
        self.assertEqual(out, "", msg="stdout on interrupt inside ingest")
        self.assertEqual(sleeps, [], msg="sleep not reached after Ctrl-C")
        again = Store(path)
        progress = again.get_progress()
        again.close()
        self.assertEqual(progress, 26077728, msg="progress unchanged")
