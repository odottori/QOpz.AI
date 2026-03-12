import json
import tempfile
import unittest
from pathlib import Path

from scripts import healthcheck


class TestD2_19_Healthcheck(unittest.TestCase):
    def test_build_plan_default_has_only_unit_tests(self):
        plan = healthcheck.build_plan(include_validator=False, validator_profile="dev", validator_config="config/dev.toml")
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][0], "unit_tests")

    def test_build_plan_with_validator_adds_validator_command(self):
        plan = healthcheck.build_plan(include_validator=True, validator_profile="paper", validator_config="config/paper.toml")
        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[1][0], "validator")
        self.assertIn("paper", plan[1][1])
        self.assertIn("config/paper.toml", plan[1][1])

    def test_healthcheck_exit_zero_when_all_ok(self):
        code, results = healthcheck.healthcheck(
            include_validator=True,
            validator_profile="dev",
            validator_config="config/dev.toml",
            runner=lambda _cmd: 0,
        )
        self.assertEqual(code, 0)
        self.assertTrue(all(r.exit_code == 0 for r in results))

    def test_healthcheck_exit_10_when_any_fails(self):
        def fake_runner(cmd):
            if "validator.py" in cmd:
                return 10
            return 0

        code, results = healthcheck.healthcheck(
            include_validator=True,
            validator_profile="dev",
            validator_config="config/dev.toml",
            runner=fake_runner,
        )
        self.assertEqual(code, 10)
        self.assertEqual([r.name for r in results], ["unit_tests", "validator"])

    def test_build_plan_with_progress_report_adds_step(self):
        plan = healthcheck.build_plan(
            include_validator=False,
            validator_profile="dev",
            validator_config="config/dev.toml",
            include_progress_report=True,
        )
        self.assertEqual([p[0] for p in plan], ["unit_tests", "progress_report"])

    def test_build_plan_with_compact_progress_and_target(self):
        plan = healthcheck.build_plan(
            include_validator=False,
            validator_profile="dev",
            validator_config="config/dev.toml",
            include_progress_report=True,
            progress_compact=True,
            progress_target_steps=40,
            progress_state="state/custom.json",
        )
        progress_cmd = plan[1][1]
        self.assertIn("--compact", progress_cmd)
        self.assertIn("--project-target-steps", progress_cmd)
        self.assertIn("40", progress_cmd)
        self.assertIn("--state", progress_cmd)
        self.assertIn("state/custom.json", progress_cmd)

    def test_build_plan_with_repo_sync_adds_step(self):
        plan = healthcheck.build_plan(
            include_validator=False,
            validator_profile="dev",
            validator_config="config/dev.toml",
            include_repo_sync=True,
            repo_sync_no_fetch=True,
        )
        self.assertEqual([p[0] for p in plan], ["unit_tests", "repo_sync"])
        self.assertIn("--no-fetch", plan[1][1])

    def test_healthcheck_includes_progress_report_step(self):
        code, results = healthcheck.healthcheck(
            include_validator=False,
            validator_profile="dev",
            validator_config="config/dev.toml",
            include_progress_report=True,
            runner=lambda _cmd: 0,
        )
        self.assertEqual(code, 0)
        self.assertEqual([r.name for r in results], ["unit_tests", "progress_report"])

    def test_get_progress_snapshot_compact_fields(self):
        state = {
            "project": "QuantOptionAI",
            "progress": {
                "next_step": "D2.28",
                "steps_completed": [{"step": "D2.27"}, {"step": "F4.1"}],
                "last_validation": {"unit_tests": {"exit_code": 0}},
            },
        }
        with tempfile.TemporaryDirectory() as td:
            st = Path(td) / "state.json"
            st.write_text(json.dumps(state), encoding="utf-8")
            snap = healthcheck.get_progress_snapshot(str(st), project_target_steps=40)

        self.assertIn("phase_completion", snap)
        self.assertIn("current_phase", snap)
        self.assertIn("project_completion", snap)
        self.assertEqual(snap["next_step"], "D2.28")
        self.assertEqual(snap["project_completion"]["target_steps"], 40)
        self.assertEqual(snap["project_target_source"], "cli")

    def test_get_repo_sync_snapshot(self):
        import subprocess as _sp

        original_run = healthcheck.subprocess.run

        def fake_run(_cmd, check=False, capture_output=True, text=True):
            payload = {"ok": True, "ahead": 1, "behind": 0, "needs_realign": False}
            return _sp.CompletedProcess([], 0, json.dumps(payload), "")

        healthcheck.subprocess.run = fake_run
        try:
            snap = healthcheck.get_repo_sync_snapshot(repo_sync_no_fetch=True)
        finally:
            healthcheck.subprocess.run = original_run

        self.assertTrue(snap["ok"])
        self.assertEqual(snap["ahead"], 1)

    def test_validate_progress_snapshot_source(self):
        ok, error = healthcheck.validate_progress_snapshot_source(
            {"project_target_source": "progress.project_target_steps"},
            "progress.project_target_steps",
        )
        self.assertTrue(ok)
        self.assertIsNone(error)

        ok2, error2 = healthcheck.validate_progress_snapshot_source(
            {"project_target_source": "default"},
            "progress.project_target_steps",
        )
        self.assertFalse(ok2)
        self.assertIn("mismatch", error2)

    def test_validate_args_requires_progress_report_for_source_guard(self):
        ns = healthcheck.parse_args(["--expected-progress-target-source", "progress.project_target_steps"])
        ok, error = healthcheck.validate_args(ns)
        self.assertFalse(ok)
        self.assertIn("requires --include-progress-report", error)

        ns_ok = healthcheck.parse_args([
            "--include-progress-report",
            "--expected-progress-target-source",
            "progress.project_target_steps",
        ])
        ok2, error2 = healthcheck.validate_args(ns_ok)
        self.assertTrue(ok2)
        self.assertIsNone(error2)

    def test_validate_args_requires_repo_sync_for_behind_guard(self):
        ns = healthcheck.parse_args(["--fail-on-repo-behind"])
        ok, error = healthcheck.validate_args(ns)
        self.assertFalse(ok)
        self.assertIn("requires --include-repo-sync", error)

        ns_ok = healthcheck.parse_args(["--include-repo-sync", "--fail-on-repo-behind"])
        ok2, error2 = healthcheck.validate_args(ns_ok)
        self.assertTrue(ok2)
        self.assertIsNone(error2)


if __name__ == "__main__":
    unittest.main()
