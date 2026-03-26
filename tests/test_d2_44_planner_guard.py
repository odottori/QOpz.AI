from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import uuid
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

    def test_planner_guard_complete_still_requires_lock(self) -> None:
        script = ROOT / 'tools' / 'planner_guard.py'
        active = ROOT / 'tests' / '.tmp_missing_active_step_complete.json'
        if active.exists():
            active.unlink()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as tf:
            json.dump({'progress': {'next_step': 'COMPLETE', 'steps_completed': []}}, tf)
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
        self.assertIn('start-maint', ((proc.stdout or '') + (proc.stderr or '')).lower())

    def test_start_maintenance_and_scope_check(self) -> None:
        script = ROOT / 'tools' / 'planner_guard.py'
        tmp_root = ROOT / 'tests' / '.tmp'
        tmp_root.mkdir(parents=True, exist_ok=True)
        tdp = tmp_root / f'guard_{uuid.uuid4().hex[:8]}'
        tdp.mkdir(parents=True, exist_ok=True)
        plan_path = tdp / 'plan.json'
        state_path = tdp / 'state.json'
        active_path = tdp / 'active.json'
        maint_path = tdp / 'maintenance.json'

        plan_path.write_text(
            json.dumps(
                {
                    'policy': {
                        'state_next_step_must_match_active': True,
                        'default_check_target': 'index',
                    },
                    'always_allowed_paths': [],
                    'scope_profiles': {
                        'F6': ['api/**', 'ui/**'],
                    },
                    'steps': {
                        'F6-T3': {'scope_profile': 'F6'},
                    },
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        state_path.write_text(
            json.dumps({'progress': {'next_step': 'COMPLETE', 'steps_completed': ['F6-T3']}}, ensure_ascii=False),
            encoding='utf-8',
        )

        start = subprocess.run(
            [
                sys.executable,
                str(script),
                '--plan',
                str(plan_path),
                '--state',
                str(state_path),
                '--active',
                str(active_path),
                '--maintenance',
                str(maint_path),
                'start-maint',
                '--step-id',
                'MNT-TEST-001',
                '--owner',
                'tester',
                '--paths',
                'api/**',
                'ui/**',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(start.returncode, 0, msg=(start.stdout or '') + (start.stderr or ''))

        in_scope = subprocess.run(
            [
                sys.executable,
                str(script),
                '--plan',
                str(plan_path),
                '--state',
                str(state_path),
                '--active',
                str(active_path),
                '--maintenance',
                str(maint_path),
                'check',
                '--files',
                'api/opz_api.py',
                'ui/src/App.tsx',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(in_scope.returncode, 0, msg=(in_scope.stdout or '') + (in_scope.stderr or ''))

        out_scope = subprocess.run(
            [
                sys.executable,
                str(script),
                '--plan',
                str(plan_path),
                '--state',
                str(state_path),
                '--active',
                str(active_path),
                '--maintenance',
                str(maint_path),
                'check',
                '--files',
                'execution/ibkr_connection.py',
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(out_scope.returncode, 0)
        self.assertIn('scope violation', (out_scope.stdout or '').lower())


if __name__ == '__main__':
    unittest.main()
