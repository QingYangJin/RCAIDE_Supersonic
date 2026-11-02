"""P4 元学习代理模块（surrogate）测试。

覆盖：特征编码（设计 + 任务 context，不按数据统计重标定）；回归指标（RMSE/MAE/R²/
最大绝对误差/Spearman/ top-k 重合）；目标与约束列选择；numpy MLP 代理可拟合且
不声明不确定度（未标定必须 None）。
"""
import unittest

import numpy as np

from research.concorde_metaopt.meta_learning import surrogate
from research.concorde_metaopt.meta_learning.data_contract import CONSTRAINT_NAMES, CONTEXT_NAMES


class EncodeFeaturesTests(unittest.TestCase):
    def test_01_shapes_and_context(self):
        designs = np.linspace(0.0, 1.0, 24).reshape(4, 6)
        context = {"context_1": 1.1, "context_2": 0.9}
        features = surrogate.encode_features(designs, context, CONTEXT_NAMES)
        self.assertEqual(features.shape, (4, 8))
        np.testing.assert_array_equal(features[:, :6], designs)
        np.testing.assert_allclose(features[:, 6], 1.1)
        np.testing.assert_allclose(features[:, 7], 0.9)

    def test_02_rejects_missing_context_and_nonfinite(self):
        designs = np.zeros((3, 6))
        with self.assertRaises(surrogate.SurrogateError):
            surrogate.encode_features(designs, {"context_1": 1.0}, CONTEXT_NAMES)
        with self.assertRaises(surrogate.SurrogateError):
            surrogate.encode_features(np.full((3, 6), np.nan), {"context_1": 1.0, "context_2": 1.0}, CONTEXT_NAMES)


class RegressionMetricsTests(unittest.TestCase):
    def test_03_perfect_prediction(self):
        target = np.linspace(-1.0, 1.0, 20)
        metrics = surrogate.regression_metrics(surrogate.SurrogatePrediction(mean=target.copy()), target)
        self.assertAlmostEqual(metrics["rmse"], 0.0)
        self.assertAlmostEqual(metrics["mae"], 0.0)
        self.assertAlmostEqual(metrics["max_abs_err"], 0.0)
        self.assertAlmostEqual(metrics["r2"], 1.0)
        self.assertAlmostEqual(metrics["spearman"], 1.0)
        self.assertAlmostEqual(metrics["top_k_overlap"], 1.0)

    def test_04_nan_targets_counted_not_imputed(self):
        target = np.array([0.0, 1.0, np.nan, 3.0])
        prediction = surrogate.SurrogatePrediction(mean=np.array([0.0, 2.0, 99.0, 3.0]))
        metrics = surrogate.regression_metrics(prediction, target)
        self.assertEqual(metrics["n_total"], 4)
        self.assertEqual(metrics["n_nonfinite"], 1)
        self.assertEqual(metrics["n_finite"], 3)
        self.assertTrue(np.isfinite(metrics["rmse"]))

    def test_05_uncertainty_must_be_none_when_uncalibrated(self):
        prediction = surrogate.SurrogatePrediction(mean=np.zeros(3))
        self.assertIsNone(prediction.uncertainty)


class TargetSelectionAndModelTests(unittest.TestCase):
    def test_06_target_selection(self):
        names = ("objective",) + tuple(CONSTRAINT_NAMES[:2])
        objective_index, constraint_indices = surrogate.select_objective_and_constraint_targets(names)
        self.assertEqual(objective_index, 0)
        self.assertEqual(constraint_indices, (1, 2))
        with self.assertRaises(surrogate.SurrogateError):
            surrogate.select_objective_and_constraint_targets(tuple(CONSTRAINT_NAMES[:2]))

    def test_07_mlp_fit_and_predict(self):
        rng = np.random.default_rng(0)
        features = rng.normal(size=(40, 6))
        weights = np.array([1.0, -2.0, 0.5, 0.0, 0.0, 3.0])
        target = features @ weights + 0.1
        model = surrogate.MLPRegressorSurrogate(input_dim=6, hidden_sizes=(8, 8), epochs=400, seed=0)
        model.fit(features, target)
        prediction = model.predict(features)
        self.assertEqual(prediction.mean.shape, (40,))
        self.assertIsNone(prediction.uncertainty)
        metrics = surrogate.regression_metrics(prediction, target)
        self.assertLess(metrics["rmse"], 0.15)
        self.assertGreater(metrics["r2"], 0.95)


if __name__ == "__main__":
    unittest.main()
