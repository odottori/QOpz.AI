import subprocess
import unittest

from scripts import git_eol_policy


class TestD2_39_GitEolPolicy(unittest.TestCase):
    def test_compliant_true(self):
        current = {"core.autocrlf": "true", "core.safecrlf": "false", "core.eol": "crlf"}
        self.assertTrue(git_eol_policy._compliant(current))

    def test_compliant_false(self):
        current = {"core.autocrlf": "false", "core.safecrlf": "true", "core.eol": "lf"}
        self.assertFalse(git_eol_policy._compliant(current))

    def test_enforce_calls_git_config(self):
        calls = []

        def fake_run(cmd):
            # cmd is without leading "git"
            calls.append(" ".join(cmd))
            # simulate "git config --get" returning desired after set
            if cmd[:3] == ["config", "--local", "--get"]:
                key = cmd[3]
                val = git_eol_policy.DESIRED[key]
                return subprocess.CompletedProcess([], 0, val + "\n", "")
            return subprocess.CompletedProcess([], 0, "", "")

        got = git_eol_policy.enforce(run=fake_run)
        self.assertEqual(got["core.autocrlf"], "true")
        self.assertEqual(got["core.safecrlf"], "false")
        self.assertEqual(got["core.eol"], "crlf")

        # ensure setters were called
        self.assertIn("config --local core.autocrlf true", calls)
        self.assertIn("config --local core.safecrlf false", calls)
        self.assertIn("config --local core.eol crlf", calls)
