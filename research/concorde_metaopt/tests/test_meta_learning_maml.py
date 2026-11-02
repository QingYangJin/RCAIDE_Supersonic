"""P4 元学习 MAML 一阶实现测试（设计 §7 / §12-6）。

覆盖：FD 门禁（中心差分 vs 自动微分，epsilon=1e-5、相对误差 tolerance=1e-4）、
初始化 seed 复现、内循环 loss 长度、一阶元训练 loss 有限、FAIL 时状态正确。
torch 不可用时整类标 NOT_RUN（skip），不得假装通过。
"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research.concorde_metaopt.meta_learning import maml


def make_episode(seed=0, support_size=6, query_size=5):
    rng = np.random.default_rng(seed)
    support_features = rng.normal(size=(support_size, 12))
    support_targets = rng.normal(size=(support_size, 2))
    query_features = rng.normal(size=(query_size, 12))
    query_targets = rng.normal(size=(query_size, 2))
    return maml.TaskEpisode(support_features, support_targets, query_features, query_targets, task_id=f"ep-{seed}")


def tiny_config(seed=7):
    return maml.MAMLConfig(
        input_dim=12,
        output_dim=2,
        hidden_sizes=(8, 8),
        inner_lr=0.05,
        inner_steps=3,
        outer_lr=1e-2,
        tasks_per_batch=4,
        first_order=True,
        seed=seed,
        backend="torch",
    )


@unittest.skipUnless(maml.torch_available(), "torch 不可用：相关测试 NOT_RUN（不得假装通过）")
class FiniteDifferenceGateTests(unittest.TestCase):
    def setUp(self):
        self.model = maml.build_small_model(seed=42)
        self.episode = make_episode(seed=1)

    def test_01_fd_gate_passes(self):
        result = maml.finite_difference_gradient_check(self.model, [self.episode], epsilon=1e-5, tolerance=1e-4)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["epsilon"], 1e-5)
        self.assertEqual(result["tolerance"], 1e-4)
        self.assertLessEqual(int(result["n_checked"]), 5)
        self.assertGreaterEqual(int(result["n_checked"]), 3)
        self.assertLessEqual(float(result["max_relative_error"]), 1e-4)
        self.assertFalse(result["equivalence_claimed"])
        for check in result["checks"]:
            self.assertEqual(check["status"], "PASS")
            self.assertTrue(np.isfinite(check["analytic"]))
            self.assertTrue(np.isfinite(check["numeric"]))
            self.assertLessEqual(float(check["relative_error"]), 1e-4)

    def test_02_fd_gate_fails_with_impossible_tolerance(self):
        result = maml.finite_difference_gradient_check(self.model, [self.episode], epsilon=1e-5, tolerance=1e-30)
        self.assertEqual(result["status"], "FAIL")
        self.assertGreater(float(result["max_relative_error"]), 1e-30)

    def test_03_fd_result_written_as_json(self):
        result = maml.finite_difference_gradient_check(self.model, [self.episode])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "finite_difference_check.json"
            maml.write_finite_difference_check(result, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["fd_point"], "adapted_parameters")
        self.assertIn("checks", payload)
        for name in ("epsilon", "tolerance", "max_relative_error", "n_checked"):
            self.assertIn(name, payload)


@unittest.skipUnless(maml.torch_available(), "torch 不可用：相关测试 NOT_RUN（不得假装通过）")
class MAMLCoreTests(unittest.TestCase):
    def test_01_init_parameters_seed_reproducible(self):
        config = tiny_config(seed=11)
        first = maml.init_parameters(config, seed=11)
        again = maml.init_parameters(config, seed=11)
        other = maml.init_parameters(config, seed=12)
        self.assertEqual(len(first.tensors), len(again.tensors))
        for left, right in zip(first.tensors, again.tensors):
            np.testing.assert_array_equal(left, right)
        self.assertTrue(any(not np.array_equal(a, b) for a, b in zip(first.tensors, other.tensors)))
        self.assertGreater(len(first.names), 0)

    def test_02_inner_adapt_loss_length(self):
        config = tiny_config()
        params = maml.init_parameters(config, seed=0)
        support = make_episode(seed=2)
        adapted, losses = maml.inner_adapt(params, support, config)
        self.assertEqual(len(losses), config.inner_steps)
        self.assertTrue(all(np.isfinite(loss) for loss in losses))
        changed = any(not np.array_equal(left, right) for left, right in zip(params.tensors, adapted.tensors))
        self.assertTrue(changed, "内循环应更新参数")

    def test_03_meta_train_step_stats_finite(self):
        config = tiny_config()
        params = maml.init_parameters(config, seed=0)
        batch = [make_episode(seed=index) for index in range(4)]
        updated, stats = maml.meta_train_step(params, batch, config)
        self.assertIsInstance(updated, maml.ParameterSet)
        for name in ("outer_loss", "grad_norm"):
            self.assertIn(name, stats)
            self.assertTrue(np.isfinite(stats[name]))
        for left, right in zip(params.tensors, updated.tensors):
            self.assertTrue(np.isfinite(right).all())
            self.assertFalse(np.array_equal(left, right))

    def test_04_meta_train_runs_and_reproducible(self):
        config = tiny_config(seed=3)
        tasks = [make_episode(seed=index) for index in range(6)]
        first = maml.meta_train(tasks, config, max_steps=3)
        second = maml.meta_train(tasks, config, max_steps=3)
        self.assertEqual(first["status"], "VALID")
        self.assertEqual(first["backend"], "torch")
        self.assertFalse(first["equivalence_claimed"])
        self.assertEqual(len(first["history"]), 3)
        self.assertEqual(first["history"], second["history"])
        self.assertEqual(first["final_parameters"], second["final_parameters"])
        for step in first["history"]:
            self.assertTrue(np.isfinite(step["outer_loss"]))
        final = first["final_parameters"]
        tensors = final.tensors if isinstance(final, maml.ParameterSet) else final["tensors"]
        for tensor in tensors:
            self.assertTrue(np.isfinite(np.asarray(tensor)).all())

    def test_05_nonfinite_episode_rejected(self):
        rng = np.random.default_rng(0)
        features = rng.normal(size=(3, 12))
        targets = np.full((3, 2), np.nan)
        with self.assertRaises(maml.MAMLError):
            maml.TaskEpisode(features, targets, features, rng.normal(size=(2, 2)), task_id="bad")

    def test_06_meta_train_nonfinite_data_fails_closed(self):
        config = tiny_config()
        good = make_episode(seed=0)
        bad_targets = np.asarray(good.query_targets, dtype=float).copy()
        bad_targets[0, 0] = np.inf
        # 绕过 TaskEpisode 构造校验写入非有限标签：元训练步必须 fail-closed 抛错
        object.__setattr__(good, "query_targets", bad_targets)
        params = maml.init_parameters(config, seed=0)
        with self.assertRaises(maml.MAMLError):
            maml.meta_train_step(params, [good], config)


if __name__ == "__main__":
    unittest.main()
