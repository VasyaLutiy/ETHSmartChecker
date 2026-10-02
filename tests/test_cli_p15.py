"""Smoke tests for the phase-15 dashboard subcommand of ethsc.cli.

Patches ethsc.dashboard.make_server (the CLI reaches it through the
module attribute), so no socket is opened here except in the busy-port
tolerance case, which binds 127.0.0.1 port 0 only. Every file goes into
a tempfile.mkdtemp() directory.
"""

import os
import socket
import sqlite3
import tempfile
import unittest.mock as mock

import ethsc.cli
from ethsc.cli import main


def _fresh_db_path():
    directory = tempfile.mkdtemp(prefix="ethsc-cli-p15-")
    path = os.path.join(directory, "ethsc.sqlite")
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE t (x)")
    connection.commit()
    connection.close()
    return path


class _StubServer(object):
    """A make_server stand-in: serve_forever raises KeyboardInterrupt."""

    def __init__(self, host, port):
        self.server_address = (host, port)
        self.serve_calls = 0
        self.close_calls = 0

    def serve_forever(self):
        self.serve_calls += 1
        raise KeyboardInterrupt

    def server_close(self):
        self.close_calls += 1


def test_dashboard_missing_db_is_exit_2_without_server():
    directory = tempfile.mkdtemp(prefix="ethsc-cli-p15-")
    missing = os.path.join(directory, "nope.sqlite")
    made = []
    with mock.patch("ethsc.dashboard.make_server",
                    side_effect=lambda *a: made.append(a)):
        code = main(["--db", missing, "dashboard"])
    assert code == 2
    assert made == []
    assert not os.path.exists(missing)


def test_dashboard_happy_path_ctrl_c_exit_0():
    db = _fresh_db_path()
    stub = _StubServer("127.0.0.1", 8080)
    calls = []
    with mock.patch("ethsc.dashboard.make_server",
                    side_effect=lambda *a: calls.append(a) or stub):
        code = main(["--db", db, "dashboard"])
    assert code == 0
    assert calls == [(db, "127.0.0.1", 8080, "dashboard/dist")]
    assert stub.serve_calls == 1
    assert stub.close_calls == 1


def test_dashboard_forwards_host_port_static():
    db = _fresh_db_path()
    stub = _StubServer("127.0.0.1", 9000)
    calls = []
    with mock.patch("ethsc.dashboard.make_server",
                    side_effect=lambda *a: calls.append(a) or stub):
        code = main(["--db", db, "dashboard", "--host", "127.0.0.1",
                     "--port", "9000", "--static", "/tmp/x"])
    assert code == 0
    assert calls == [(db, "127.0.0.1", 9000, "/tmp/x")]


def test_dashboard_module_attribute_reached_through_ethsc_cli():
    db = _fresh_db_path()
    stub = _StubServer("127.0.0.1", 8080)
    with mock.patch.object(ethsc.dashboard, "make_server",
                           return_value=stub) as maker:
        code = main(["--db", db, "dashboard"])
    assert code == 0
    assert maker.call_count == 1


def test_dashboard_busy_port_is_exit_2():
    db = _fresh_db_path()
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        code = main(["--db", db, "dashboard", "--port", str(port)])
    finally:
        blocker.close()
    assert code == 2
