import subprocess
import unittest

from scripts import repo_sync_status


class TestD2_35_RepoSyncStatus(unittest.TestCase):
    def test_parse_ahead_behind(self):
        ahead, behind = repo_sync_status._parse_ahead_behind("2 5")
        self.assertEqual(ahead, 5)
        self.assertEqual(behind, 2)

    def test_collect_sync_status_with_upstream(self):
        outputs = {
            "rev-parse --abbrev-ref HEAD": subprocess.CompletedProcess([], 0, "work\n", ""),
            "remote": subprocess.CompletedProcess([], 0, "origin\n", ""),
            "fetch --prune": subprocess.CompletedProcess([], 0, "", ""),
            "rev-parse --abbrev-ref --symbolic-full-name @{u}": subprocess.CompletedProcess([], 0, "origin/work\n", ""),
            "rev-list --left-right --count HEAD...@{u}": subprocess.CompletedProcess([], 0, "1 3\n", ""),
        }

        def fake_run(cmd):
            key = " ".join(cmd)
            return outputs[key]

        payload = repo_sync_status.collect_sync_status(run=fake_run, do_fetch=True)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["branch"], "work")
        self.assertEqual(payload["upstream"], "origin/work")
        self.assertEqual(payload["ahead"], 3)
        self.assertEqual(payload["behind"], 1)
        self.assertTrue(payload["needs_realign"])
        self.assertTrue(payload["push_ready"])
        self.assertEqual(payload["push_hint"], "git push")

    def test_collect_sync_status_without_upstream(self):
        outputs = {
            "rev-parse --abbrev-ref HEAD": subprocess.CompletedProcess([], 0, "work\n", ""),
            "remote": subprocess.CompletedProcess([], 0, "origin\n", ""),
            "rev-parse --abbrev-ref --symbolic-full-name @{u}": subprocess.CompletedProcess([], 1, "", "fatal"),
        }

        def fake_run(cmd):
            key = " ".join(cmd)
            return outputs[key]

        payload = repo_sync_status.collect_sync_status(run=fake_run, do_fetch=False)
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["upstream"])
        self.assertFalse(payload["needs_realign"])
        self.assertFalse(payload["push_ready"])
        self.assertIn("set upstream", payload["push_hint"])
        self.assertIn("warning", payload)

    def test_to_line_includes_push_readiness(self):
        line = repo_sync_status.to_line({
            "ok": True,
            "branch": "work",
            "upstream": "origin/work",
            "ahead": 1,
            "behind": 0,
            "needs_realign": False,
            "push_ready": True,
        })
        self.assertIn("push_ready=True", line)


if __name__ == "__main__":
    unittest.main()
