"""P4 元学习初始化对照（baseline_arms）测试（设计 §8 / §8.2 / §12-8 / §12-17）。

覆盖：共享初始设计确定性；BO/DE 臂等预算与物理守卫；MAML-init 冻结参数
（候选 64 / 初始 8 / 多样性 64 / 去重 1e-12）；代理预测只用于选点、绝不写入
observations；单位门禁；配对统计键。
"""
import unittest

import numpy as np

from research.concorde_metaopt.meta_learning import baseline_arms as ba
from research.concorde_metaopt.meta_learning import maml, task_family as tf
from research.concorde_metaopt.meta_learning.offline_runner import load_design_space_12d


def small_task():
    config = tf.default_task_family_config(
        train_tasks=1,
        validation_tasks=1,
        test_tasks=1,
        ood_tasks=1,
        negative_control_tasks=0,
        support_pool_size=16,
        query_size=8,
        designs_per_task=24,
    )
    tasks = [task for task in tf.build_task_family(config) if task.split == "meta_test"]
    return tasks[0]


def proxy_artifact(task, seed=0):
    config = maml.MAMLConfig(
        input_dim=14,
        output_dim=2,
        hidden_sizes=(8, 8),
        inner_lr=0.05,
        inner_steps=3,
        outer_lr=1e-2,
        tasks_per_batch=2,
        seed=seed,
        backend="torch",
    )
    return {
        "parameters": maml.init_parameters(config, seed=seed),
        "config": config,
        "context_names": ("context_1", "context_2"),
        "adaptation_method": "maml",
        "fine_tuning_steps": 10,
        "backend": "torch",
        "equivalence_claimed": False,
    }


def target_names(task):
    return ("objective",) + tuple(task.enabled_constraint_names)


@unittest.skipUnless(maml.torch_available(), "torch 不可用：初始化对照测试 NOT_RUN（不得假装通过）")
class InitialDesignTests(unittest.TestCase):
    def setUp(self):
        self.task = small_task()
        self.design_space = load_design_space_12d()
        self.artifact = proxy_artifact(self.task)
        self.reference = float(self.task.reference()["objective_star"])

    def test_01_shared_initial_designs_deterministic(self):
        first = ba.shared_initial_designs(self.task.task_id, 0, count=8)
        second = ba.shared_initial_designs(self.task.task_id, 0, count=8)
        other = ba.shared_initial_designs(self.task.task_id, 1, count=8)
        np.testing.assert_array_equal(first, second)
        self.assertFalse(np.array_equal(first, other))
        self.assertEqual(first.shape, (8, 12))
        self.assertTrue(np.all(first >= 0.0) and np.all(first <= 1.0))

    def test_02_bo_arm_equal_budget_and_guard(self):
        evaluate = ba.make_synthetic_task_evaluator(self.task, self.design_space)
        result = ba.run_bo_arm(
            "OPT-BO-rand",
            evaluate,
            task_id=self.task.task_id,
            split="meta_test",
            family=self.task.family,
            seed=0,
            budget=8,
            initial_designs=ba.shared_initial_designs(self.task.task_id, 0, count=8),
            reference_objective=self.reference,
        )
        self.assertEqual(result.requested_evaluations, 8)
        self.assertEqual(result.true_evals_used, 8)
        self.assertEqual(len(result.observations), 8)
        self.assertEqual(evaluate.physical_call_count, 0)
        self.assertIn(result.status, (ba.VALID_STATUS, ba.NO_FEASIBLE_STATUS))
        # 前 8 次评价必须恰为传入的共享初始设计（可复现、可审计）
        expected = ba.shared_initial_designs(self.task.task_id, 0, count=8)
        for index, record in enumerate(result.observations):
            np.testing.assert_allclose(record.design_u, expected[index], atol=1e-12)

    def test_03_de_arm_equal_budget(self):
        evaluate = ba.make_synthetic_task_evaluator(self.task, self.design_space)
        result = ba.run_de_arm(
            evaluate,
            task_id=self.task.task_id,
            split="meta_test",
            family=self.task.family,
            seed=0,
            budget=8,
            population_size=8,
            reference_objective=self.reference,
        )
        self.assertEqual(result.true_evals_used, 8)
        self.assertEqual(evaluate.physical_call_count, 0)
        self.assertEqual(len(result.observations), 8)
        self.assertEqual(result.arm, ba.DE_ARM)

    def test_03b_de_arm_zero_acceptance_still_uses_full_budget(self):
        # M1-F01 回归：整代无接受也不得提前终止，必须恰好用满等预算（§10）
        task = small_task()

        def constant_evaluate(design_u):
            return {"valid": True, "objective": 1.0, "constraints_g_le_zero": {"c01": -0.1}}

        budget = 24
        result = ba.run_de_arm(
            constant_evaluate,
            task_id=task.task_id,
            split="meta_test",
            family=task.family,
            seed=0,
            budget=budget,
            population_size=8,
            reference_objective=1.0,
        )
        self.assertEqual(result.true_evals_used, budget)
        self.assertEqual(len(result.observations), budget)
        self.assertEqual(result.termination_reason, "budget_exhausted")
        self.assertEqual(result.feasible_count, budget)
        self.assertEqual(result.best_feasible_value, 1.0)
        self.assertEqual(result.initial_feasible_count, 8)

    def test_04_maml_init_frozen_parameters(self):
        self.assertEqual(ba.MAML_INIT_CANDIDATE_COUNT, 64)
        self.assertEqual(ba.MAML_INIT_INITIAL_DESIGN_COUNT, 8)
        self.assertEqual(ba.MAML_INIT_DIVERSITY_CANDIDATE_COUNT, 64)
        self.assertEqual(ba.DEDUP_TOLERANCE, 1e-12)
        scoring = ba.score_maml_init_designs(
            self.artifact,
            self.design_space,
            self.task,
            seed=0,
            candidate_count=ba.MAML_INIT_CANDIDATE_COUNT,
            initial_design_count=ba.MAML_INIT_INITIAL_DESIGN_COUNT,
            diversity_candidate_count=ba.MAML_INIT_DIVERSITY_CANDIDATE_COUNT,
            target_names=target_names(self.task),
        )
        self.assertEqual(len(scoring["designs"]), 8)
        unique = {tuple(np.round(design, 12)) for design in np.asarray(scoring["designs"])}
        self.assertEqual(len(unique), 8)
        cost = scoring["proxy_scoring_cost"]
        self.assertEqual(cost["candidates_scored"], 64)
        self.assertEqual(cost["true_evaluation_budget_used"], 0)
        self.assertEqual(scoring["method"], "maml_init")

    def test_05_maml_init_insufficient_candidates_fail(self):
        # 候选池唯一数 < 冻结的 initial_design_count=8 → 整臂失败（不得降级继续）
        with self.assertRaises((ba.BaselineArmError, ValueError)):
            ba.score_maml_init_designs(
                self.artifact,
                self.design_space,
                self.task,
                seed=0,
                candidate_count=4,
                initial_design_count=8,
                diversity_candidate_count=4,
                target_names=target_names(self.task),
            )

    def test_06_maml_init_predictions_not_in_observations(self):
        scoring = ba.score_maml_init_designs(
            self.artifact,
            self.design_space,
            self.task,
            seed=0,
            target_names=target_names(self.task),
        )
        predictions = np.asarray(scoring["predictions"], dtype=np.float64)
        selected = {tuple(np.round(design, 12)) for design in np.asarray(scoring["designs"])}
        for candidate_design, predicted in zip(np.asarray(scoring["designs"]), predictions):
            self.assertIn(tuple(np.round(candidate_design, 12)), selected)

        evaluate = ba.make_synthetic_task_evaluator(self.task, self.design_space)
        observed: list[dict] = []

        def recording_evaluator(design_u):
            result = evaluate(design_u)
            observed.append(
                {
                    "design_u": np.asarray(design_u, dtype=np.float64).copy(),
                    "objective": result["objective"],
                    "feasible": result["feasible"],
                }
            )
            return result

        result = ba.run_maml_init_arm(
            self.artifact,
            self.design_space,
            self.task,
            recording_evaluator,
            seed=0,
            budget=8,
            target_names=target_names(self.task),
            reference_objective=self.reference,
        )
        self.assertEqual(result.true_evals_used, 8)
        # observations 的标签只来自（合成）真实评估，与代理预测无关
        for index, record in enumerate(result.observations):
            np.testing.assert_allclose(record.design_u, observed[index]["design_u"], atol=1e-12)
            if record.objective is None:
                self.assertIsNone(observed[index]["objective"])
            else:
                self.assertAlmostEqual(record.objective, float(observed[index]["objective"]), places=12)
        self.assertEqual(evaluate.physical_call_count, 0)
        self.assertIn("maml_opt.initialization", result.implementation)

    def test_07_unit_gates(self):
        ba.assert_synthetic_feature_units(["1"] * 14, label="feature_units")
        with self.assertRaises(ba.BaselineArmError):
            ba.assert_synthetic_feature_units(["1"] * 13 + ["kg"], label="feature_units")
        with self.assertRaises(ba.BaselineArmError):
            ba.assert_synthetic_feature_units([], label="feature_units")
        ba.assert_synthetic_design_space(self.design_space)
        from research.concorde_metaopt.aircraft.design_space import load_design_space

        with self.assertRaises(ba.BaselineArmError):
            ba.assert_synthetic_design_space(load_design_space())

    def test_08_paired_statistics(self):
        stats = ba.paired_statistics(list(np.linspace(-1.0, 1.0, 10)), seed=0)
        for key in (
            "n",
            "median_diff",
            "mean_diff",
            "ci_low",
            "ci_high",
            "confidence",
            "bootstrap_samples",
            "seed",
            "wilcoxon_statistic",
            "wilcoxon_pvalue",
        ):
            self.assertIn(key, stats)
        self.assertEqual(stats["n"], 10)
        self.assertEqual(stats["bootstrap_samples"], 10000)
        self.assertLessEqual(stats["ci_low"], stats["ci_high"])
        few = ba.paired_statistics([0.1, 0.2, 0.3], seed=0)
        self.assertIsNone(few["wilcoxon_pvalue"])

    def test_09_compare_initializers(self):
        payload = ba.compare_initializers(
            self.design_space,
            self.artifact,
            [self.task],
            ("OPT-BO-rand", "OPT-DE"),
            budget=8,
            seed=0,
        )
        self.assertEqual(payload["status"], ba.VALID_STATUS)
        self.assertEqual(payload["physical_call_count"], 0)
        self.assertEqual(len(payload["results"]), 2)
        self.assertEqual(len(payload["summaries"]), 2)
        for summary in payload["summaries"]:
            self.assertEqual(summary["budget"], 8)
            self.assertEqual(summary["true_evals_used"], 8)


if __name__ == "__main__":
    unittest.main()
