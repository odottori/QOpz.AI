from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, check=True, capture_output=True, text=True)
    return (proc.stdout or '').strip()


class TestPlannerGuardSmoke(unittest.TestCase):
    def test_planner_guard_status_smoke(self) -> None:
        script = ROOT / 'tools' / 'planner_guard.py'
        out = _run([sys.executable, str(script), 'status', '--format', 'line'])
        self.assertIn('PLANNER_GUARD STATUS', out)

    def test_planner_guard_check_fails_without_lock(self) -> None:
        """Guard must fail when active_step.json is absent and next_step is not COMPLETE."""
        script = ROOT / 'tools' / 'planner_guard.py'
        active = ROOT / 'tests' / '.tmp_missing_active_step.json'
        if active.exists():
            active.unlink()
        # Use a temporary state file with a real in-progress next_step so the
        # COMPLETE short-circuit is not triggered.
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as tf:
            json.dump({'next_step': 'F1-T5', 'steps_completed': []}, tf)
            tmp_state = tf.name
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                '--active',
                str(active),
                '--state',
                tmp_state,
                'check',
                '--check-target',
                'index',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        Path(tmp_state).unlink(missing_ok=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('missing', ((proc.stdout or '') + (proc.stderr or '')).lower())


if __name__ == '__main__':
    unittest.main()
