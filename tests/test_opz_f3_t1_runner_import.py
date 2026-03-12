from __future__ import annotations

import importlib
import unittest


class OpzF3T1RunnerImportTests(unittest.TestCase):
    def test_import_opz_f3_t1_runner(self) -> None:
        importlib.import_module("tools.opz_f3_t1_runner")


if __name__ == "__main__":
    unittest.main()
