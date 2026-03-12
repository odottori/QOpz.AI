from __future__ import annotations

import unittest

from tools.opz_state_normalize import normalize_state


class OpzStateNormalizeTests(unittest.TestCase):
    def test_mirrors_next_step(self) -> None:
        st = {"progress": {"next_step": "F6-T1"}, "next_step": "F3-T2"}
        changed = normalize_state(st)
        self.assertTrue(changed)
        self.assertEqual(st["next_step"], "F6-T1")


if __name__ == "__main__":
    unittest.main()
