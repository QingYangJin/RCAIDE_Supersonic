"""FULL_MAML（二阶）与 FD full 门禁测试（S2 计划 §4.1–§4.3 / §4.2）。

覆盖：
- 微型网络解析二阶元梯度 vs 中心差分（多步内循环，相对误差 <= 1e-6）；
- inner_steps=0 时 FULL 与 FOMAML 元梯度逐元素等价（<= 1e-12）；
- mode="full" fail-closed：first_order=True 传入、坐标不足、tolerance 不可能、显式 epsilon 均拒绝；
- meta_train_step(second_order=True) 统计量有限、内循环 loss 键存在、结果可复现；
- 旧 FOMAML 入口 mode="fomaml" 仍走既有口径（行为由 legacy 测试保证，这里只验证分发）。

torch 不可用时整类标 NOT_RUN（skip），不得假装通过。
"""
import unittest

import numpy as np

from research.concorde_metaopt.meta_learning import maml


def make_single_target_episode(seed=0, support_size=6, query_size=5, input_dim=3):
    rng = np.random.default_rng(seed)
    support_features = rng.normal(size=(support_size, input_dim))
    support_targets = rng.normal(size=(support_size, 1))
    query_features = rng.normal(size=(query_size, input_dim))
    query_targets = rng.normal(size=(query_size, 1))
    return maml.TaskEpisode(support_features, support_targets, query_features, query_targets, task_id=f"ep-{seed}")


def small_full_config(seed=5, inner_steps=2, first_order=False, input_dim=3):
    return maml.MAMLConfig(
        input_dim=input_dim,
        output_dim=1,
        hidden_sizes=(4, 4),
        inner_lr=0.05,
        inner_steps=inner_steps,
        outer_lr=1e-2,
        tasks_per_batch=2,
        first_order=first_order,
        seed=seed,
        backend="torch",
    )


def total_gradient_norm(grads):
    return float(sum(float(np.sum(grad**2)) for grad in grads))


@unittest.skipUnless(maml.torch_available(), "torch 不可用：相关测试 NOT_RUN（不得假装通过）")
class FullMAMLSecondOrderGradientTests(unittest.TestCase):
    def test_01_full_gradient_matches_central_difference(self):
        config = small_full_config(inner_steps=2)
        model = maml.MAMLModel(config=config, parameters=maml.init_parameters(config, seed=7))
        episodes = [make_single_target_episode(seed=index, input_dim=config.input_dim) for index in range(2)]
        loss, grads = maml._full_maml_outer_gradient(model.parameters, episodes, config)
        self.assertTrue(np.isfinite(loss))
        self.assertTrue(np.isfinite(total_gradient_norm(grads)))
        # 独立中心差分（不经过 FD 门禁内部实现）抽查 3 个坐标
        candidates = []
        for tensor_index, grad in enumerate(grads):
            flat = grad.reshape(-1)
            for flat_index in range(flat.shape[0]):
                candidates.append((tensor_index, int(flat_index), float(flat[flat_index])))
        candidates.sort(key=lambda item: (-abs(item[2]), item[0], item[1]))
        for tensor_index, flat_index, analytic in candidates[:3]:
            theta_j = float(model.parameters.tensors[tensor_index].reshape(-1)[flat_index])
            eps = 1e-6 * max(1.0, abs(theta_j))
            plus = maml._perturb(model.parameters, tensor_index, flat_index, eps)
            minus = maml._perturb(model.parameters, tensor_index, flat_index, -eps)
            numeric = (maml._full_maml_loss_value(plus, episodes, config) - maml._full_maml_loss_value(minus, episodes, config)) / (2.0 * eps)
            relative = abs(numeric - analytic) / max(abs(numeric), abs(analytic), 1e-12)
            self.assertLessEqual(relative, 1e-6, f"坐标 {(tensor_index, flat_index)} FD 相对误差 {relative}")

    def test_02_full_fd_gate_pass_and_json_shape(self):
        config = small_full_config(inner_steps=2)
        model = maml.MAMLModel(config=config, parameters=maml.init_parameters(config, seed=8))
        episodes = [make_single_target_episode(seed=index, input_dim=config.input_dim) for index in range(2)]
        result = maml.finite_difference_gradient_check(model, episodes, mode="full", max_coordinates=8)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["mode"], "full")
        self.assertEqual(result["fd_point"], "meta_parameters")
        self.assertEqual(result["n_checked"], 8)
        self.assertLessEqual(result["max_relative_error"], 1e-6)
        self.assertEqual(result["epsilon_policy"], "1e-6 * max(1, |theta_j|)")
        self.assertEqual(result["denominator_policy"], "max(|numeric|, |analytic|, 1e-12)")
        self.assertFalse(result["equivalence_claimed"])
        for check in result["checks"]:
            self.assertEqual(check["status"], "PASS")
            self.assertTrue(np.isfinite(check["analytic"]))
            self.assertTrue(np.isfinite(check["numeric"]))

    def test_03_multi_step_inner_loop_fd(self):
        config = small_full_config(inner_steps=4)
        model = maml.MAMLModel(config=config, parameters=maml.init_parameters(config, seed=9))
        episodes = [make_single_target_episode(seed=index, input_dim=config.input_dim) for index in range(2)]
        result = maml.finite_difference_gradient_check(model, episodes, mode="full", max_coordinates=10, tolerance=1e-6)
        self.assertEqual(result["status"], "PASS")
        self.assertLessEqual(result["max_relative_error"], 1e-6)

    def test_04_full_gradient_deterministic(self):
        config = small_full_config(inner_steps=2)
        parameters = maml.init_parameters(config, seed=10)
        episodes = [make_single_target_episode(seed=index, input_dim=config.input_dim) for index in range(2)]
        loss_a, grads_a = maml._full_maml_outer_gradient(parameters, episodes, config)
        loss_b, grads_b = maml._full_maml_outer_gradient(parameters, episodes, config)
        self.assertEqual(loss_a, loss_b)
        for left, right in zip(grads_a, grads_b):
            np.testing.assert_array_equal(left, right)


@unittest.skipUnless(maml.torch_available(), "torch 不可用：相关测试 NOT_RUN（不得假装通过）")
class FullMAMLZeroStepEquivalenceTests(unittest.TestCase):
    def test_01_inner_steps_zero_full_equals_fomaml_gradient(self):
        config = small_full_config(inner_steps=0, first_order=False)
        parameters = maml.init_parameters(config, seed=11)
        episodes = [make_single_target_episode(seed=index, input_dim=config.input_dim) for index in range(3)]
        adapted_sets, firsts, lasts = maml._inner_adapt_episodes(parameters, episodes, config)
        # inner_steps=0：没有内循环步 loss；lasts 记录的是最终参数点上的 support loss（非内循环步）
        self.assertEqual(len(firsts), 0)
        self.assertEqual(len(lasts), len(episodes))
        fomaml_loss, fomaml_grads = maml._fomaml_outer_gradient(adapted_sets, episodes)
        full_loss, full_grads = maml._full_maml_outer_gradient(parameters, episodes, config)
        self.assertAlmostEqual(fomaml_loss, full_loss, places=12)
        self.assertEqual(len(fomaml_grads), len(full_grads))
        for left, right in zip(fomaml_grads, full_grads):
            max_diff = float(np.max(np.abs(left - right))) if left.size else 0.0
            self.assertLessEqual(max_diff, 1e-12, f"inner_steps=0 时 FULL/FOMAML 梯度差应 <=1e-12，实际 {max_diff}")

    def test_02_zero_step_meta_train_step_full_stats_finite(self):
        config = small_full_config(inner_steps=0, first_order=False)
        parameters = maml.init_parameters(config, seed=12)
        episodes = [make_single_target_episode(seed=index, input_dim=config.input_dim) for index in range(2)]
        updated, stats = maml.meta_train_step(parameters, episodes, config, second_order=True)
        self.assertIsInstance(updated, maml.ParameterSet)
        for name in ("outer_loss", "grad_norm", "inner_loss_first", "inner_loss_last"):
            self.assertIn(name, stats)
            self.assertTrue(np.isfinite(stats[name]), f"{name} 应为有限值")


@unittest.skipUnless(maml.torch_available(), "torch 不可用：相关测试 NOT_RUN（不得假装通过）")
class FullMAMLTrainingStepTests(unittest.TestCase):
    def test_01_second_order_step_finite_and_reproducible(self):
        config = small_full_config(inner_steps=3)
        parameters = maml.init_parameters(config, seed=13)
        episodes = [make_single_target_episode(seed=index, input_dim=config.input_dim) for index in range(2)]
        updated_a, stats_a = maml.meta_train_step(parameters, episodes, config, second_order=True)
        updated_b, stats_b = maml.meta_train_step(parameters, episodes, config, second_order=True)
        self.assertEqual(stats_a, stats_b)
        for left, right in zip(updated_a.tensors, updated_b.tensors):
            np.testing.assert_array_equal(left, right)
        # FULL 与 FOMAML 一步在二阶项非零时应产生不同参数；注意 FOMAML 需要 first_order=True 的 config
        fomaml_config = small_full_config(inner_steps=3, first_order=True)
        fomaml_updated, _ = maml.meta_train_step(parameters, episodes, fomaml_config, second_order=False)
        max_diff = max(
            float(np.max(np.abs(left - right)))
            for left, right in zip(updated_a.tensors, fomaml_updated.tensors)
        )
        self.assertGreater(max_diff, 0.0, "FULL_MAML 与 FOMAML 一步更新不应完全一致")

    def test_02_first_order_false_config_routes_to_full(self):
        config = small_full_config(inner_steps=2, first_order=False)
        parameters = maml.init_parameters(config, seed=14)
        episodes = [make_single_target_episode(seed=index, input_dim=config.input_dim) for index in range(2)]
        updated, stats = maml.meta_train_step(parameters, episodes, config)
        expected, _ = maml.meta_train_step(parameters, episodes, config, second_order=True)
        for left, right in zip(updated.tensors, expected.tensors):
            np.testing.assert_array_equal(left, right)
        self.assertTrue(np.isfinite(stats["outer_loss"]))


@unittest.skipUnless(maml.torch_available(), "torch 不可用：相关测试 NOT_RUN（不得假装通过）")
class FullMAMLFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.full_config = small_full_config(inner_steps=2, first_order=False)
        self.full_model = maml.MAMLModel(
            config=self.full_config, parameters=maml.init_parameters(self.full_config, seed=15)
        )
        self.episodes = [
            make_single_target_episode(seed=index, input_dim=self.full_config.input_dim) for index in range(2)
        ]
        fomaml_config = small_full_config(inner_steps=2, first_order=True)
        self.fomaml_model = maml.MAMLModel(
            config=fomaml_config, parameters=maml.init_parameters(fomaml_config, seed=15)
        )

    def test_01_first_order_model_rejected_in_full_mode(self):
        with self.assertRaises(maml.MAMLError) as context:
            maml.finite_difference_gradient_check(self.fomaml_model, self.episodes, mode="full")
        self.assertIn(maml.S2_META_GRAD_FD_FAIL, str(context.exception))

    def test_02_insufficient_coordinates_fail_closed(self):
        with self.assertRaises(maml.MAMLError) as context:
            maml.finite_difference_gradient_check(
                self.full_model, self.episodes, mode="full", max_coordinates=1000000
            )
        self.assertIn(maml.S2_META_GRAD_FD_FAIL, str(context.exception))

    def test_03_impossible_tolerance_fails_closed(self):
        with self.assertRaises(maml.MAMLError) as context:
            maml.finite_difference_gradient_check(
                self.full_model, self.episodes, mode="full", max_coordinates=4, tolerance=1e-30
            )
        self.assertIn(maml.S2_META_GRAD_FD_FAIL, str(context.exception))

    def test_04_explicit_epsilon_rejected_in_full_mode(self):
        with self.assertRaises(maml.MAMLError):
            maml.finite_difference_gradient_check(self.full_model, self.episodes, epsilon=1e-5, mode="full")

    def test_05_invalid_mode_rejected(self):
        with self.assertRaises(maml.MAMLError):
            maml.finite_difference_gradient_check(self.full_model, self.episodes, mode="hvp")

    def test_06_fomaml_mode_still_legacy(self):
        result = maml.finite_difference_gradient_check(
            self.fomaml_model, self.episodes, epsilon=1e-5, tolerance=1e-4, mode="fomaml"
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["fd_point"], "adapted_parameters")
        self.assertLessEqual(result["max_relative_error"], 1e-4)

    def test_07_full_fd_gate_requires_first_order_false(self):
        with self.assertRaises(maml.MAMLError) as context:
            maml._finite_difference_gradient_check_full(self.fomaml_model, self.episodes)
        self.assertIn(maml.S2_META_GRAD_FD_FAIL, str(context.exception))


if __name__ == "__main__":
    unittest.main()
