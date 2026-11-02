"""P4 元学习快速适应测试（设计 §9 / §12-7）。

覆盖：K=0/1/5/10 四种适应方法可跑通；losses 长度=inner_steps；
K=0 零样本 losses 为空；physical_call_count 恒 0；指标有限；seed 复现；
AdaptationResult 合同校验。
"""
import unittest

import numpy as np

from research.concorde_metaopt.meta_learning import adaptation, maml, task_family as tf
from research.concorde_metaopt.meta_learning.data_contract import CONTEXT_NAMES


def tiny_config(seed=5):
    return maml.MAMLConfig(
        input_dim=14,
        output_dim=1,
        hidden_sizes=(8, 8),
        inner_lr=0.05,
        inner_steps=3,
        outer_lr=1e-2,
        tasks_per_batch=2,
        seed=seed,
        backend="torch",
    )


def make_artifact(seed=0):
    config = tiny_config(seed=seed)
    parameters = maml.init_parameters(config, seed=seed)
    return {
        "parameters": parameters,
        "config": config,
        "context_names": tuple(CONTEXT_NAMES),
        "adaptation_method": "maml",
        "fine_tuning_steps": 10,
        "backend": "torch",
        "equivalence_claimed": False,
    }


def make_blocks(seed=0, support_size=10, query_size=6):
    rng = np.random.default_rng(seed)
    support = {
        "features": rng.normal(size=(support_size, 14)),
        "targets": rng.normal(size=(support_size, 1)),
    }
    query = {
        "features": rng.normal(size=(query_size, 14)),
        "targets": rng.normal(size=(query_size, 1)),
    }
    return support, query


def support_subset(support, k_shot):
    """adapt_and_predict 要求 support 行数恰为 k_shot（K 增大只从池内追加）。"""
    return {
        "features": support["features"][:k_shot],
        "targets": support["targets"][:k_shot],
    }


def small_family_tasks():
    config = tf.default_task_family_config(
        train_tasks=1,
        validation_tasks=1,
        test_tasks=1,
        ood_tasks=1,
        negative_control_tasks=0,
        support_pool_size=12,
        query_size=4,
        designs_per_task=16,
    )
    return [task for task in tf.build_task_family(config) if task.split in ("meta_test", "meta_test_ood")]


@unittest.skipUnless(maml.torch_available(), "torch 不可用：适应测试 NOT_RUN（不得假装通过）")
class AdaptAndPredictTests(unittest.TestCase):
    def setUp(self):
        self.artifact = make_artifact()
        self.support, self.query = make_blocks()

    def test_01_all_methods_all_ks_run(self):
        expected_steps = {
            "none": 0,
            "maml": 3,  # artifact config inner_steps
            "fine_tuning": 10,
            "from_scratch": 10,
        }
        for method in adaptation.ADAPTATION_METHODS:
            for k_shot in (0, 1, 5, 10):
                with self.subTest(method=method, k_shot=k_shot):
                    result = adaptation.adapt_and_predict(
                        self.artifact,
                        support_subset(self.support, k_shot),
                        self.query,
                        method=method,
                        k_shot=k_shot,
                    )
                    self.assertEqual(result.method, method)
                    self.assertEqual(result.k_shot, k_shot)
                    self.assertEqual(result.physical_call_count, 0)
                    self.assertEqual(result.predictions.shape, (6,))
                    self.assertEqual(result.targets.shape, (6,))
                    self.assertEqual(len(result.losses), result.inner_steps)
                    if k_shot == 0:
                        self.assertEqual(result.inner_steps, 0)
                        self.assertEqual(result.losses, ())
                    else:
                        self.assertEqual(result.inner_steps, expected_steps[method])
                    for name in ("rmse", "mae", "max_abs_err", "r2"):
                        self.assertIn(name, result.metrics)
                    self.assertEqual(result.metrics["n_total"], 6)

    def test_02_predictions_reproducible(self):
        first = adaptation.adapt_and_predict(
            self.artifact, support_subset(self.support, 5), self.query, method="maml", k_shot=5
        )
        second = adaptation.adapt_and_predict(
            self.artifact, support_subset(self.support, 5), self.query, method="maml", k_shot=5
        )
        np.testing.assert_array_equal(first.predictions, second.predictions)
        self.assertEqual(first.metrics, second.metrics)
        self.assertEqual(first.losses, second.losses)

    def test_03_support_growth_changes_fit(self):
        one = adaptation.adapt_and_predict(
            self.artifact, support_subset(self.support, 1), self.query, method="maml", k_shot=1
        )
        five = adaptation.adapt_and_predict(
            self.artifact, support_subset(self.support, 5), self.query, method="maml", k_shot=5
        )
        self.assertGreater(five.inner_steps, 0)
        self.assertFalse(np.array_equal(one.predictions, five.predictions))

    def test_04_config_override(self):
        result = adaptation.adapt_and_predict(
            self.artifact,
            support_subset(self.support, 5),
            self.query,
            method="fine_tuning",
            k_shot=5,
            config={"fine_tuning_steps": 4, "hidden_sizes": (8, 8)},
        )
        self.assertEqual(result.inner_steps, 4)
        self.assertEqual(len(result.losses), 4)

    def test_05_k_shot_study(self):
        tasks = small_family_tasks()
        self.assertEqual(len(tasks), 2)
        results = adaptation.run_k_shot_study(self.artifact, tasks, (0, 1, 5), seed=0)
        self.assertEqual(len(results), len(tasks) * 3)
        for result in results:
            self.assertEqual(result.physical_call_count, 0)
            self.assertIn(result.k_shot, (0, 1, 5))
            if result.k_shot == 0:
                self.assertEqual(result.losses, ())

    def test_06_adaptation_result_contract(self):
        result = adaptation.adapt_and_predict(
            self.artifact, support_subset(self.support, 5), self.query, method="maml", k_shot=5
        )
        with self.assertRaises(adaptation.AdaptationError):
            adaptation.AdaptationResult(
                method=result.method,
                k_shot=result.k_shot,
                inner_steps=result.inner_steps,
                predictions=result.predictions,
                targets=result.targets,
                losses=tuple(result.losses)[:-1],
                metrics=result.metrics,
                physical_call_count=0,
            )
        with self.assertRaises(adaptation.AdaptationError):
            adaptation.AdaptationResult(
                method=result.method,
                k_shot=result.k_shot,
                inner_steps=result.inner_steps,
                predictions=result.predictions,
                targets=result.targets,
                losses=result.losses,
                metrics=result.metrics,
                physical_call_count=1,
            )

    def test_07_invalid_method_rejected(self):
        with self.assertRaises(adaptation.AdaptationError):
            adaptation.adapt_and_predict(
                self.artifact, support_subset(self.support, 1), self.query, method="bogus", k_shot=1
            )
        with self.assertRaises(adaptation.AdaptationError):
            adaptation.adapt_and_predict(
                self.artifact, support_subset(self.support, 1), self.query, method="maml", k_shot=-1
            )


if __name__ == "__main__":
    unittest.main()
