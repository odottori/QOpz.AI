from __future__ import annotations

import socket
import threading
import time
import unittest
from unittest import mock

from execution.ibkr_tws import IbkrConnectivityError, IbkrDependencyError, run_f3_t1_probe


def _start_dummy_listener() -> tuple[int, threading.Thread, socket.socket]:
    """Start a short-lived TCP listener to satisfy TCP pre-check."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def _accept_once():
        try:
            conn, _ = srv.accept()
            conn.close()
        except Exception:
            pass

    th = threading.Thread(target=_accept_once, daemon=True)
    th.start()
    return port, th, srv


class F3T1IbkrProbeTests(unittest.TestCase):
    def test_tcp_precheck_fails_fast(self):
        # Port 1 is usually closed; should fail at TCP pre-check without long timeouts.
        with self.assertRaises(IbkrConnectivityError) as ctx:
            run_f3_t1_probe(host="127.0.0.1", port=1, client_id=7, timeout_sec=0.2, tcp_precheck=True)
        self.assertIn("TCP_CONNECT_FAIL", str(ctx.exception))

    def test_missing_dependency_raises(self):
        # Ensure TCP pre-check passes by using a dummy listener.
        port, th, srv = _start_dummy_listener()

        orig_import = __import__

        def import_side_effect(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "ib_insync" or name.startswith("ib_insync."):
                raise ImportError("simulated missing ib_insync")
            return orig_import(name, globals, locals, fromlist, level)

        try:
            with mock.patch("builtins.__import__", side_effect=import_side_effect):
                with self.assertRaises(IbkrDependencyError) as ctx:
                    run_f3_t1_probe(host="127.0.0.1", port=port, client_id=7, timeout_sec=0.2, tcp_precheck=True)
                self.assertIn("MISSING_DEPENDENCY", str(ctx.exception))
        finally:
            try:
                srv.close()
            except Exception:
                pass
