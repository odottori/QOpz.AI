from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import regime_classifier as rc


class TestF2T1RegimeClassifier(unittest.TestCase):
    def setUp(self) -> None:
        self.csv = Path("samples/regime_features_2010_2014.csv")
        self.assertTrue(self.csv.exists(), "missing fixture CSV")

    def test_train_predict_oos_metrics(self) -> None:
        rows = rc.load_dataset_csv(self.csv)
        features = ["vix", "vix3m", "ret_5d"]
        train_rows, oos_rows = rc.split_by_year(rows, train_years=range(2010, 2014), oos_year=2014)

        # calibration slice: 2013
        cal_rows = [r for r in train_rows if r["date"].year == 2013]
        base_rows = [r for r in train_rows if r["date"].year != 2013]

        model = rc.train_gaussian_nb(rc.featurize(base_rows, features), rc.labels(base_rows), features)
        model = rc.fit_platt_scaling(model, rc.featurize(cal_rows, features), rc.labels(cal_rows), iters=150, lr=0.05)

        X_oos = rc.featurize(oos_rows, features)
        y_oos = rc.labels(oos_rows)
        proba = rc.predict_proba(model, X_oos)
        y_pred = rc.predict(model, X_oos)

        self.assertEqual(len(y_pred), len(y_oos))
        self.assertTrue(all(y in rc.CLASSES for y in y_pred))
        acc = rc.accuracy(y_oos, y_pred)
        brier = rc.brier_score(y_oos, proba)

        # Pass criteria from canonici/02_TEST.md (offline fixture is separable)
        self.assertGreater(acc, 0.65)
        self.assertLess(brier, 0.20)

        # "SHAP top3" proxy: vix/vix3m must be in top3
        importance = rc.fisher_feature_importance(
            rc.featurize(base_rows + cal_rows, features),
            rc.labels(base_rows + cal_rows),
            features,
        )
        top3 = [f for f, _ in importance[:3]]
        self.assertIn("vix", top3)
        self.assertIn("vix3m", top3)

    def test_cli_writes_outputs(self) -> None:
        # import tool module and run main with temp dirs
        from tools import f2_t1_train_regime_classifier as cli  # type: ignore

        with tempfile.TemporaryDirectory() as td:
            outdir = Path(td) / "reports"
            model_out = Path(td) / "model.json"
            rc_path = str(self.csv)
            rc_args = ["--csv", rc_path, "--outdir", str(outdir), "--model-out", str(model_out)]
            rc_ret = cli.main(rc_args)
            self.assertEqual(rc_ret, 0)
            self.assertTrue(model_out.exists())
            self.assertTrue((outdir / "f2_t1_metrics.json").exists())
            metrics = json.loads((outdir / "f2_t1_metrics.json").read_text(encoding="utf-8"))
            self.assertIn("accuracy", metrics)
            self.assertIn("brier", metrics)


if __name__ == "__main__":
    unittest.main()
