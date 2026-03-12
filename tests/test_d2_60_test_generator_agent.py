import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from scripts import test_generator_agent


class TestD2_60_TestGeneratorAgent(unittest.TestCase):
    def test_infer_test_modules_known_files(self):
        tests, unmapped = test_generator_agent.infer_test_modules([
            "scripts/progress_report.py",
            "scripts/healthcheck.py",
            "config/dev.toml",
        ])
        self.assertIn("tests/test_d2_23_progress_report.py", tests)
        self.assertIn("tests/test_d2_19_healthcheck.py", tests)
        self.assertIn("tests/test_d2_20_dataset_mode_guard.py", tests)
        self.assertEqual(unmapped, [])

    def test_infer_test_modules_collects_unmapped_python(self):
        tests, unmapped = test_generator_agent.infer_test_modules([
            "scripts/new_tool.py",
            "README.md",
        ])
        self.assertEqual(tests, [])
        self.assertEqual(unmapped, ["scripts/new_tool.py"])

    def test_build_unittest_command(self):
        cmd = test_generator_agent.build_unittest_command([
            "tests/test_d2_23_progress_report.py",
            "tests/test_d2_19_healthcheck.py",
        ])
        self.assertEqual(
            cmd,
            "python -m unittest -v tests/test_d2_23_progress_report.py tests/test_d2_19_healthcheck.py",
        )

    def test_write_stub_tests(self):
        with tempfile.TemporaryDirectory() as td:
            cwd = Path.cwd()
            try:
                import os

                os.chdir(td)
                created = test_generator_agent.write_stub_tests(["scripts/foo_bar.py"])
                self.assertEqual(created, ["tests/test_auto_foo_bar.py"])
                content = Path("tests/test_auto_foo_bar.py").read_text(encoding="utf-8")
                self.assertIn("class TestAuto_foo_bar", content)
            finally:
                import os

                os.chdir(cwd)

    def test_main_json_payload(self):
        with tempfile.TemporaryDirectory():
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = test_generator_agent.main([
                    "--changed-file",
                    "scripts/progress_report.py",
                    "--changed-file",
                    "scripts/repo_sync_status.py",
                ])
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue().strip())
            self.assertIn("tests/test_d2_23_progress_report.py", payload["selected_test_modules"])
            self.assertIn("tests/test_d2_35_repo_sync_status.py", payload["selected_test_modules"])
            self.assertEqual(payload["final_exit_code"], 0)

    def test_fail_on_unmapped_returns_10(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = test_generator_agent.main([
                "--changed-file",
                "scripts/new_tool.py",
                "--fail-on-unmapped",
            ])
        self.assertEqual(code, 10)
        payload = json.loads(buf.getvalue().strip())
        self.assertEqual(payload["final_exit_code"], 10)
        self.assertEqual(payload["unmapped_python_files"], ["scripts/new_tool.py"])

    def test_run_executes_recommended_command(self):
        import subprocess as _sp

        original_run = test_generator_agent.subprocess.run

        def fake_run(cmd, check=False, capture_output=True, text=True):
            if cmd[:3] == ["python", "-m", "unittest"]:
                return _sp.CompletedProcess(cmd, 0, "ok", "")
            return original_run(cmd, check=check, capture_output=capture_output, text=text)

        test_generator_agent.subprocess.run = fake_run
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = test_generator_agent.main([
                    "--changed-file",
                    "README.md",
                    "--run",
                ])
        finally:
            test_generator_agent.subprocess.run = original_run

        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue().strip())
        self.assertTrue(payload["run_requested"])
        self.assertIsNotNone(payload["run_result"])
        self.assertEqual(payload["run_result"]["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
