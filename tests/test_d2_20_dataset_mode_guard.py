import unittest

import validator


class TestD2_20_DatasetModeGuard(unittest.TestCase):
    def test_paper_rejects_synthetic_mode(self):
        check = validator._check_synth()
        cfg = {"dataset": {"seed": 42, "mode": "synthetic"}}
        res = check(cfg, "paper")
        self.assertEqual(res.status, "FAIL")
        self.assertEqual(res.severity, "CRITICAL")

    def test_live_rejects_synthetic_mode(self):
        check = validator._check_synth()
        cfg = {"dataset": {"seed": 42, "mode": "synthetic"}}
        res = check(cfg, "live")
        self.assertEqual(res.status, "FAIL")
        self.assertEqual(res.severity, "CRITICAL")

    def test_dev_allows_synthetic_mode(self):
        check = validator._check_synth()
        cfg = {"dataset": {"seed": 42, "mode": "synthetic"}}
        res = check(cfg, "dev")
        self.assertEqual(res.status, "PASS")

    def test_paper_accepts_non_synthetic_mode(self):
        check = validator._check_synth()
        cfg = {"dataset": {"seed": 42, "mode": "paper"}}
        res = check(cfg, "paper")
        self.assertEqual(res.status, "PASS")


if __name__ == "__main__":
    unittest.main()
