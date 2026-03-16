from __future__ import annotations

import unittest
from pathlib import Path


class BatSanityTests(unittest.TestCase):
    def test_opz_f3_t2_bat_has_no_bare_backslash_lines(self) -> None:
        p = Path(__file__).resolve().parents[1] / "scripts" / "OPZ_F3_T2_RUN.bat"
        text = p.read_text(encoding="utf-8", errors="replace").splitlines()
        self.assertTrue(text, "OPZ_F3_T2_RUN.bat is empty")
        for line in text:
            self.assertNotEqual(line.strip(), "\\", "OPZ_F3_T2_RUN.bat contains a bare backslash line")
        # Avoid bash-style line continuations in cmd
        for line in text:
            self.assertFalse(line.rstrip().endswith("\\"), "OPZ_F3_T2_RUN.bat contains trailing backslash line continuation")


if __name__ == "__main__":
    unittest.main()
