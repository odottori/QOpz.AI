from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.local_broker_runtime as lbr

ROOT = Path(__file__).resolve().parents[1]


class TestLocalBrokerRuntime(unittest.TestCase):
    def test_discover_command_prefers_env_exe(self):
        with patch.dict("os.environ", {"IBG_EXE": "C:/IBG/ibgateway.exe"}, clear=False):
            with patch("scripts.local_broker_runtime.Path.exists", return_value=True):
                cmd = lbr._discover_command()
        self.assertEqual(cmd, ["C:/IBG/ibgateway.exe"])

    def test_start_control_plane_not_found(self):
        with patch("scripts.local_broker_runtime._cp_running", return_value=False), patch(
            "scripts.local_broker_runtime._discover_command", return_value=None
        ):
            out = lbr._start_control_plane()
        self.assertFalse(out["ok"])
        self.assertEqual(out["reason"], "ibg_command_not_found")

    def test_control_api_base_default_is_local_on_windows(self):
        target = (ROOT / "api" / "opz_api.py").read_text(encoding="utf-8")
        self.assertIn('default_base = "http://127.0.0.1:8770" if os.name == "nt" else "http://control-plane:8770"', target)

    def test_control_plane_local_backend_health_mentions_backend(self):
        import api.control_plane as cp
        with patch.object(cp, "_BACKEND", "local_process"):
            payload = cp.health()
        self.assertEqual(payload["backend"], "local_process")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestLocalBrokerAttachFirst(unittest.TestCase):
    def test_control_plane_local_process_default_attach_first(self):
        cp = (ROOT / "api" / "control_plane.py").read_text(encoding="utf-8")
        self.assertIn('CONTROL_LOCAL_IBG_AUTO_LAUNCH", "0"', cp)
        self.assertIn('reason="BROKER_NOT_LISTENING"', cp)
        self.assertIn('applied_action="attach_only"', cp)

    def test_local_broker_runtime_sets_attach_first(self):
        s = (ROOT / "scripts" / "local_broker_runtime.py").read_text(encoding="utf-8")
        self.assertIn('"CONTROL_LOCAL_IBG_AUTO_LAUNCH": "0"', s)
        self.assertIn('"launch_mode": "attach_first"', s)
