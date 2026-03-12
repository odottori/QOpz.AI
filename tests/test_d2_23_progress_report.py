import unittest

from scripts import progress_report


class TestD2_23_ProgressReport(unittest.TestCase):
    def test_phase_mapping(self):
        self.assertEqual(progress_report._phase_from_step("D2.22"), "F3")
        self.assertEqual(progress_report._phase_from_step("F4.1"), "F4")
        self.assertEqual(progress_report._phase_from_step("F2-T1"), "F2")

    def test_markdown_render(self):
        payload = {
            "project": "QuantOptionAI",
            "next_step": "D2.24",
            "project_progress": {
                "steps_completed_total": 10,
                "latest_step": "D2.23",
                "last_validation": {"ts_utc": "2026-02-27T00:00:00Z"},
                "completion": {"completed_steps": 10, "target_steps": 40, "percent": 25.0},
                "completion_target_source": "progress.project_target_steps",
            },
            "phase_progress": [
                {"phase": "F3", "completed_steps": 8, "latest_step": "D2.23"},
            ],
            "phase_plan_progress": [
                {"phase": "F3", "completed_tasks": 1, "total_tasks": 4, "latest_task": "F3-T4"},
            ],
            "phase_plan_completion": {"completed_tasks_total": 1, "total_tasks_total": 28, "percent": 3.6},
            "phase_completion": {"completed": 1, "total": 6, "percent": 16.7},
            "current_phase": {"phase": "F3", "index": 3, "total": 6, "percent": 50.0},
        }
        md = progress_report.to_markdown(payload)
        self.assertIn("## PER FASI (piano canonico)", md)
        self.assertIn("## PER FASE (steps loggati)", md)
        self.assertIn("## PER TRACK D2", md)
        self.assertIn("D2.24", md)
        self.assertIn("Avanzamento piano", md)
        self.assertIn("Avanzamento D2", md)

    def test_build_payload_includes_plan(self):
        state = {
            "project": "QuantOptionAI",
            "progress": {
                "next_step": "D2.23",
                "last_validation": {"unit_tests": {"exit_code": 0}},
                "steps_completed": [
                    {"step": "D2.5", "title": "Orders ledger canonico (F3-T4)"},
                    {"step": "F4.1", "summary": "Implement score + tests (F4-T1/F4-T2)."},
                ],
                "project_target_steps": 40,
            },
        }
        payload = progress_report.build_progress_payload(state)
        self.assertEqual(payload["project_progress"]["steps_completed_total"], 2)
        self.assertEqual(payload["project_progress"]["latest_step"], "F4.1")
        self.assertIn("phase_plan_progress", payload)
        self.assertIn("phase_plan_completion", payload)
        # Should count canonical tasks mentioned in summaries
        plan_f3 = next(x for x in payload["phase_plan_progress"] if x["phase"] == "F3")
        self.assertGreaterEqual(plan_f3["completed_tasks"], 1)
        plan_f4 = next(x for x in payload["phase_plan_progress"] if x["phase"] == "F4")
        self.assertGreaterEqual(plan_f4["completed_tasks"], 2)

    def test_build_payload_uses_target_steps_override(self):
        state = {
            "project": "QuantOptionAI",
            "progress": {
                "next_step": "D2.29",
                "steps_completed": [{"step": "D2.21"}, {"step": "D2.22"}],
                "project_target_steps": 40,
            },
        }
        payload = progress_report.build_progress_payload(state)
        self.assertEqual(payload["project_progress"]["completion"]["target_steps"], 40)
        self.assertEqual(payload["project_progress"]["completion_target_source"], "progress.project_target_steps")

        payload_cli = progress_report.build_progress_payload(state, project_target_steps=50)
        self.assertEqual(payload_cli["project_progress"]["completion"]["target_steps"], 50)
        self.assertEqual(payload_cli["project_progress"]["completion_target_source"], "cli")

    def test_line_render(self):
        payload = {
            "project": "QuantOptionAI",
            "next_step": "D2.31",
            "project_progress": {
                "steps_completed_total": 13,
                "completion": {"completed_steps": 13, "target_steps": 40, "percent": 32.5},
                "completion_target_source": "unknown",
            },
            "phase_plan_completion": {"completed_tasks_total": 3, "total_tasks_total": 28, "percent": 10.7},
        }
        line = progress_report.to_line(payload)
        self.assertIn("PER FASI(plan)", line)
        self.assertIn("PER TRACK D2", line)
        self.assertIn("target_source=unknown", line)
        self.assertIn("next=D2.31", line)

    def test_markdown_compact(self):
        payload = {
            "project": "QuantOptionAI",
            "next_step": "D2.29",
            "project_progress": {
                "steps_completed_total": 12,
                "latest_step": "D2.28",
                "completion": {"completed_steps": 12, "target_steps": 30, "percent": 40.0},
            },
            "phase_plan_completion": {"completed_tasks_total": 2, "total_tasks_total": 28, "percent": 7.1},
            "phase_completion": {"completed": 2, "total": 6, "percent": 33.3},
            "current_phase": {"phase": "F3", "index": 3, "total": 6, "percent": 50.0},
            "phase_progress": [
                {"phase": "F1", "completed_steps": 1, "latest_step": "F1.1"},
            ],
            "phase_plan_progress": [
                {"phase": "F1", "completed_tasks": 0, "total_tasks": 5, "latest_task": None},
            ],
        }
        md = progress_report.to_markdown(payload, compact=True)
        self.assertIn("Avanzamento piano", md)
        self.assertIn("Avanzamento D2", md)
        self.assertNotIn("| Fase | Steps completati | Ultimo step |", md)


if __name__ == "__main__":
    unittest.main()
