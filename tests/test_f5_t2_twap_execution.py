import json
import shutil
import unittest
from pathlib import Path

from execution.execution_plan import build_twap_slices, select_execution_plan
from tools import f5_t2_twap_execution as tool


class TestF5T2TwapExecution(unittest.TestCase):
    def setUp(self):
        Path("reports").mkdir(parents=True, exist_ok=True)

    def test_twap_triggers_for_wide_spread_on_4_legs(self):
        plan = select_execution_plan(
            bid=10.0,
            ask=10.7,
            enable_twap=True,
            twap_trigger_abs=0.5,
            twap_slices=3,
            twap_slice_interval_sec=300,
            legs_count=4,
            order_quantity=7,
        )
        self.assertEqual(plan.kind, "TWAP")
        self.assertEqual(plan.reason, "WIDE_SPREAD_TWAP")
        self.assertEqual(plan.details["twap_slices"], 3)
        self.assertEqual(plan.details["twap_slice_interval_sec"], 300)
        self.assertEqual(len(plan.details["slices"]), 3)

    def test_twap_slices_have_correct_intervals_and_quantity(self):
        slices = build_twap_slices(total_quantity=7, twap_slices=3, twap_slice_interval_sec=300)
        self.assertEqual([s.offset_sec for s in slices], [0, 300, 600])
        self.assertEqual(sum(s.quantity for s in slices), 7)

    def test_tool_writes_reports_and_passes(self):
        outdir = Path("reports") / "f5_t2_test_out"
        if outdir.exists():
            shutil.rmtree(outdir, ignore_errors=True)
        outdir.mkdir(parents=True, exist_ok=True)

        rc = tool.main(
            [
                "--bid",
                "10.0",
                "--ask",
                "10.7",
                "--legs-count",
                "4",
                "--quantity",
                "6",
                "--outdir",
                str(outdir),
            ]
        )
        self.assertEqual(rc, 0)
        self.assertTrue((outdir / "f5_t2_twap_execution.json").exists())
        self.assertTrue((outdir / "f5_t2_twap_execution.md").exists())

        payload = json.loads((outdir / "f5_t2_twap_execution.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["plan"]["kind"], "TWAP")


if __name__ == "__main__":
    unittest.main()
