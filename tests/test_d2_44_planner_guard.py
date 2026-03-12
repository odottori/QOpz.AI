from __future__ import annotations

import subprocess
import sys
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
        script = ROOT / 'tools' / 'planner_guard.py'
        active = ROOT / 'tests' / '.tmp_missing_active_step.json'
        if active.exists():
            active.unlink()
        proc = subprocess.run(
            [
                sys.executable,
                str(script),
                '--active',
                str(active),
                'check',
                '--check-target',
                'index',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('missing', ((proc.stdout or '') + (proc.stderr or '')).lower())


if __name__ == '__main__':
    unittest.main()
