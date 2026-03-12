import json
import unittest
from pathlib import Path

from tools.hf_progress_tracking_alignment import align_state


class TestHFProgressTrackingAlignment(unittest.TestCase):
    def test_state_has_f1_t2_and_idempotent(self):
        state_path = Path(".qoaistate.json")
        self.assertTrue(state_path.exists())
        state = json.loads(state_path.read_text(encoding="utf-8"))
        progress = state.get("progress", {})
        steps = progress.get("steps_completed", [])
        self.assertIsInstance(steps, list)

        # Must already contain F1-T2 after patch apply
        ids = []
        for it in steps:
            if isinstance(it, str):
                ids.append(it)
            elif isinstance(it, dict):
                ids.append(it.get("id") or it.get("step"))
        self.assertIn("F1-T2", ids)

        # Ordering: F1-T1 < F1-T2 < F1-T3 (if present)
        if "F1-T1" in ids and "F1-T3" in ids:
            self.assertLess(ids.index("F1-T1"), ids.index("F1-T2"))
            self.assertLess(ids.index("F1-T2"), ids.index("F1-T3"))

        # Idempotent: no further changes
        before = json.dumps(state, sort_keys=True)
        changed = align_state(state)
        after = json.dumps(state, sort_keys=True)
        self.assertFalse(changed)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
