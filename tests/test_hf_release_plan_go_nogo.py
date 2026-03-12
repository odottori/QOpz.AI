import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestReleaseStatus(unittest.TestCase):
    def test_release_plan_exists(self):
        p = ROOT / "config" / "release_plan_go_nogo.json"
        self.assertTrue(p.exists())
        obj = json.loads(p.read_text(encoding="utf-8"))
        self.assertIn("milestones", obj)
        self.assertGreaterEqual(len(obj["milestones"]), 3)

    def test_release_status_runs(self):
        # Import tool as module
        import tools.release_status as rs
        step_index = json.loads((ROOT / ".step_index.json").read_text(encoding="utf-8"))
        plan = json.loads((ROOT / "config" / "release_plan_go_nogo.json").read_text(encoding="utf-8"))
        completed = rs._completed_step_ids(step_index)
        milestones = [rs._milestone_status(m, completed) for m in plan["milestones"]]
        self.assertTrue(any(m.id == "R0_BASELINE" for m in milestones))
        # next_milestone line format should be stable
        line = rs._fmt_line(milestones)
        self.assertIn("RELEASE_STATUS", line)

if __name__ == "__main__":
    unittest.main()
