import unittest

import validator


class TestD2_21_DatasetProfileConsistency(unittest.TestCase):
    def test_dev_requires_synthetic_warning_if_not(self):
        check = validator._check_dataset_mode_profile()
        res = check({"dataset": {"mode": "paper"}}, "dev")
        self.assertEqual(res.status, "FAIL")
        self.assertEqual(res.severity, "WARNING")

    def test_dev_passes_with_synthetic(self):
        check = validator._check_dataset_mode_profile()
        res = check({"dataset": {"mode": "synthetic"}}, "dev")
        self.assertEqual(res.status, "PASS")

    def test_paper_requires_paper_mode(self):
        check = validator._check_dataset_mode_profile()
        res = check({"dataset": {"mode": "live"}}, "paper")
        self.assertEqual(res.status, "FAIL")
        self.assertEqual(res.severity, "CRITICAL")

    def test_live_requires_live_mode(self):
        check = validator._check_dataset_mode_profile()
        res = check({"dataset": {"mode": "paper"}}, "live")
        self.assertEqual(res.status, "FAIL")
        self.assertEqual(res.severity, "CRITICAL")

    def test_paper_live_pass_with_matching_mode(self):
        check = validator._check_dataset_mode_profile()
        self.assertEqual(check({"dataset": {"mode": "paper"}}, "paper").status, "PASS")
        self.assertEqual(check({"dataset": {"mode": "live"}}, "live").status, "PASS")


if __name__ == "__main__":
    unittest.main()
