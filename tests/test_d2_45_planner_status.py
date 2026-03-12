from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, check=True, capture_output=True, text=True)
    return (proc.stdout or '').strip()


class TestPlannerStatusSmoke(unittest.TestCase):
    def test_planner_status_line_smoke(self) -> None:
        script = ROOT / 'scripts' / 'planner_status.py'
        out = _run([sys.executable, str(script), '--format', 'line'])
        self.assertTrue(out.startswith('PLANNER_STATUS'))
        self.assertIn('next=', out)

    def test_planner_status_md_smoke(self) -> None:
        script = ROOT / 'scripts' / 'planner_status.py'
        out = _run([sys.executable, str(script), '--format', 'md'])
        self.assertIn('## PLANNER STATUS', out)
        self.assertIn('## PRIMARY TARGETS', out)


if __name__ == '__main__':
    unittest.main()
