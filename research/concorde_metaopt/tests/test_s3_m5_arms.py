"""S3 五臂 + 联合评分 + RNG/公平合同单测（A1 写域；零物理调用）。"""
from __future__ import annotations

import hashlib
import math
import unittest

import numpy as np

from research.concorde_metaopt.meta_learning import m5_arms as m5
from research.concorde_metaopt.meta_learning import maml
from research.concorde_metaopt.meta_learning import task_family as tf


def _task():
    tasks = tf.build_s3_conflict_family(delta1_base=0.20)
    for task in tasks:
        if task.split == "meta_train":
            return task
    raise AssertionError("缺少 meta_train 任务")


def _evaluator(calls):
    def evaluate(design):
        design = np.asarray(design, dtype=np.float64)
        calls.append(tuple(float(value) for value in design))
        f = float(np.sum((design - 0.5) ** 2))
        g1 = float(0.20 - design[0])
        g2 = float(design[1] - 0.80)
        return {
            "objective": f,
            "constraints_g_le_zero": {"g1": g1, "g2": g2},
            "status": "OK",
            "feasible": bool(g1 <= 0.0 and g2 <= 0.0),
            "cache_hit": False,
            "billable": True,
            "design_physical": None,
            "analysis_calls": 1,
        }

    return evaluate


def _proxy_config(**overrides):
    payload = dict(
        input_dim=12,
        output_dim=3,
        hidden_sizes=(8, 8),
        inner_lr=0.01,
        inner_steps=2,
        outer_lr=1e-3,
        tasks_per_batch=4,
        first_order=True,
        seed=0,
        backend="torch",
    )
    payload.update(overrides)
    return maml.MAMLConfig(**payload)


def _scorer(head_only=False, seed=0):
    config = _proxy_config(head_only=head_only, seed=seed)
    parameters = maml.init_parameters(config, seed=seed)
    return m5.S3ModelScorer(parameters, config, meta_seed=0)


class BudgetTests(unittest.TestCase):
    def test_01_expected_budget(self):
        for budget in (64, 128):
            plan = m5.s3_expected_budget(budget)
            self.assertEqual(plan["budget_B"], budget)
            self.assertEqual(plan["K"], 5)
            self.assertEqual(plan["initial_designs"], 8)
            self.assertEqual(plan["support_evals"], 5)
            self.assertEqual(plan["initial_evals"], 3)
            self.assertEqual(plan["bo_or_de_evals"], budget - 8)
            self.assertEqual(plan["billable_evals"], budget)
        for bad in (0, 8, 96, 256, "128", None):
            with self.assertRaises(m5.S3ArmError):
                m5.s3_expected_budget(bad)

    def test_02_budget_constants(self):
        self.assertEqual(tuple(m5.S3_BUDGETS), (64, 128))
        self.assertEqual(m5.S3_K_SHOT, 5)
        self.assertEqual(m5.S3_INITIAL_DESIGN_COUNT, 8)
        self.assertEqual(m5.S3_NEW_INITIAL_COUNT, 3)
        self.assertEqual(m5.S3_CANDIDATE_POOL_SIZE, 123)
        self.assertEqual(m5.S3_CANDIDATE_COUNT, 512)


class RngContractTests(unittest.TestCase):
    def test_01_bo_engine_seed_fixed_vector(self):
        task_id, opt_seed, meta_seed = "p4ra-FQEC-v1-deadbeefdeadbeef", 3, 1
        expected = int.from_bytes(
            hashlib.sha256(f"{task_id}|{opt_seed}|{meta_seed}|s3-bo-engine".encode("utf-8")).digest()[:8],
            "big",
        ) % (2**31)
        self.assertEqual(m5.s3_bo_engine_seed(task_id, opt_seed, meta_seed), expected)
        self.assertEqual(m5.s3_bo_engine_seed(task_id, 4, 2) != expected, True)

    def test_02_de_engine_seed_fixed_vector(self):
        task_id, opt_seed, meta_seed = "p4ra-FQEC-v1-deadbeefdeadbeef", 3, 1
        expected = int.from_bytes(
            hashlib.sha256(f"{task_id}|{opt_seed}|{meta_seed}|s3-de".encode("utf-8")).digest()[:8],
            "big",
        ) % (2**31)
        self.assertEqual(m5.s3_de_engine_seed(task_id, opt_seed, meta_seed), expected)
        self.assertNotEqual(m5.s3_de_engine_seed(task_id, opt_seed, meta_seed), m5.s3_bo_engine_seed(task_id, opt_seed, meta_seed))

    def test_03_support_seed_fixed_vector(self):
        task_id, meta_seed = "p4ra-FQEC-v1-deadbeefdeadbeef", 2
        expected = int(hashlib.sha256(f"{task_id}|s1-support|{meta_seed}".encode("utf-8")).hexdigest()[:8], 16) % (2**31 - 1)
        self.assertEqual(m5.s3_support_seed(task_id, meta_seed), expected)

    def test_04_engine_draws_deterministic(self):
        first = m5.s3_bo_engine_draws(12345)
        second = m5.s3_bo_engine_draws(12345)
        self.assertEqual(first.shape, (512, 12))
        self.assertTrue(np.array_equal(first, second))
        self.assertEqual(m5.s3_bo_engine_draws_sha256(12345), m5.s3_bo_engine_draws_sha256(12345))
        self.assertNotEqual(m5.s3_bo_engine_draws_sha256(12345), m5.s3_bo_engine_draws_sha256(54321))

    def test_05_bo_config_sha_stable(self):
        self.assertEqual(m5.s3_bo_config_sha256(), m5.s3_bo_config_sha256())
        self.assertEqual(len(m5.s3_bo_config_sha256()), 64)


class DesignContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = _task()

    def test_01_shared_initial_designs(self):
        designs = m5.s3_shared_initial_designs(str(self.task.task_id), 0)
        self.assertEqual(designs.shape, (8, 12))
        self.assertTrue(np.all(designs >= 0.0) and np.all(designs <= 1.0))
        again = m5.s3_shared_initial_designs(str(self.task.task_id), 0)
        self.assertTrue(np.array_equal(designs, again))
        other = m5.s3_shared_initial_designs(str(self.task.task_id), 1)
        self.assertFalse(np.array_equal(designs, other))

    def test_02_shared_initial_independent_of_arm(self):
        first = m5.s3_shared_initial_designs(str(self.task.task_id), 0, count=3)
        second = m5.s3_shared_initial_designs(str(self.task.task_id), 0, count=3)
        self.assertTrue(np.array_equal(first, second))

    def test_03_candidate_pool_size_and_disjoint(self):
        pool = m5.s3_candidate_pool(self.task, meta_seed=0)
        support = m5.s3_select_support_designs(self.task, meta_seed=0)
        self.assertEqual(pool.shape, (123, 12))
        self.assertEqual(support.shape, (5, 12))
        pool_keys = {tuple(np.round(row, 12)) for row in pool}
        support_keys = {tuple(np.round(row, 12)) for row in support}
        self.assertEqual(pool_keys & support_keys, set())
        other = m5.s3_candidate_pool(self.task, meta_seed=1)
        self.assertNotEqual(m5.s3_candidate_pool_sha256(self.task, meta_seed=0), m5.s3_candidate_pool_sha256(self.task, meta_seed=1))
        self.assertTrue(np.array_equal(pool, other) or pool.shape == other.shape)

    def test_04_select_diverse_designs(self):
        candidates = np.array([[index * 0.05] * 12 for index in range(10)], dtype=np.float64)
        references = np.zeros((1, 12), dtype=np.float64)
        result = m5.s3_select_diverse_designs(candidates, reference_designs=references, count=3, min_distance=0.0)
        self.assertEqual(result["indices"], [0, 1, 2])
        self.assertFalse(result["diversity_relaxed"])
        forced = m5.s3_select_diverse_designs(candidates, reference_designs=references, count=3, min_distance=10.0)
        self.assertEqual(len(forced["indices"]), 3)
        self.assertEqual(len(set(forced["indices"])), 3)
        self.assertTrue(forced["diversity_relaxed"])
        scored = m5.s3_select_diverse_designs(
            candidates,
            reference_designs=references,
            count=3,
            scores=np.array([5.0, 4.0, 3.0, 2.0, 1.0, 0.0, -1.0, -2.0, -3.0, -4.0]),
            min_distance=0.0,
        )
        self.assertEqual(scored["indices"], [9, 8, 7])


class NormalizationTests(unittest.TestCase):
    def test_01_normalization_floor(self):
        result = m5.s3_normalization(np.array([1.0] * 5), np.zeros((5, 2)))
        self.assertEqual(result["f_mean"], 1.0)
        self.assertEqual(result["f_scale"], 1e-6)
        self.assertEqual(result["g_scale"], [1e-6, 1e-6])

    def test_02_standardize_labels(self):
        support_f = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        support_g = np.array([[0.1, -0.1], [0.2, -0.2], [0.3, -0.3], [0.4, -0.4], [0.5, -0.5]])
        normalization = m5.s3_normalization(support_f, support_g)
        standardized = m5.s3_standardize_labels(support_f, support_g[:, 0], support_g[:, 1], normalization)
        self.assertEqual(standardized.shape, (5, 3))
        self.assertAlmostEqual(float(np.mean(standardized[:, 0])), 0.0, places=12)

    def test_03_joint_score_formula(self):
        result = m5.s3_joint_score(np.array([0.5]), np.array([0.2]), np.array([0.3]))
        self.assertAlmostEqual(float(result[0]), 3.0, places=12)
        none_violated = m5.s3_joint_score(np.array([0.5]), np.array([-0.2]), np.array([-0.3]))
        self.assertAlmostEqual(float(none_violated[0]), 0.5, places=12)


class ArmContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = _task()

    def test_01_random_arm_budget_and_provenance(self):
        calls = []
        result = m5.run_s3_bo_arm(m5.S3_BO_RANDOM, _evaluator(calls), task=self.task, budget=64, opt_seed=0, meta_seed=0)
        self.assertEqual(result.arm, m5.S3_BO_RANDOM)
        self.assertEqual(len(result.observations), 64)
        self.assertEqual([record.eval_index for record in result.observations], list(range(1, 65)))
        self.assertEqual(len(calls), 64)
        self.assertTrue(all(record.billable for record in result.observations))
        provenance = m5.s3_arm_provenance(result)
        self.assertEqual(provenance["budget_plan"]["billable_evals"], 64)
        self.assertEqual(provenance["budget_sources"], {"support": 5, "initial": 3, "bo": 56, "de": 0})
        self.assertEqual(provenance["rng"]["candidate_pool_sha256"], m5.s3_candidate_pool_sha256(self.task, meta_seed=0))
        self.assertEqual(provenance["rng"]["bo_engine_seed"], m5.s3_bo_engine_seed(str(self.task.task_id), 0, 0))
        self.assertEqual(provenance["rng"]["de_engine_seed"], None)
        self.assertEqual(provenance["s3_provenance_schema"], "p4ra-s3-arm-provenance-v1")
        self.assertEqual(provenance["uncertainty"], None)
        self.assertEqual(provenance["calibration"], "NOT_PERFORMED")
        self.assertEqual(provenance["initial"]["support_designs_sha256"], m5.designs_digest(m5.s3_select_support_designs(self.task, meta_seed=0)))

    def test_02_scored_arms_run(self):
        for arm, scorer in (
            (m5.S3_BO_FOMAML_OBJ, _scorer(False)),
            (m5.S3_BO_FOMAML_CON, _scorer(False)),
            (m5.S3_BO_ANIL_CON, _scorer(True)),
        ):
            calls = []
            result = m5.run_s3_bo_arm(arm, _evaluator(calls), task=self.task, budget=64, opt_seed=0, meta_seed=0, scorer=scorer)
            provenance = m5.s3_arm_provenance(result)
            self.assertEqual(len(result.observations), 64)
            self.assertEqual(provenance["scoring"]["score_kind"], "S_obj" if arm == m5.S3_BO_FOMAML_OBJ else "S_joint")
            self.assertEqual(provenance["scoring"]["candidates_scored"], 123)
            self.assertEqual(provenance["scoring"]["forward_predictions"], 123)
            self.assertEqual(provenance["scoring"]["scorer"]["head_only"], arm == m5.S3_BO_ANIL_CON)

    def test_03_de_arm_budget_and_provenance(self):
        calls = []
        result = m5.run_s3_de_arm(_evaluator(calls), task=self.task, budget=64, opt_seed=0, meta_seed=0)
        self.assertEqual(result.arm, m5.S3_DE)
        self.assertEqual(len(result.observations), 64)
        provenance = m5.s3_arm_provenance(result)
        self.assertEqual(provenance["budget_sources"], {"support": 5, "initial": 3, "bo": 0, "de": 56})
        self.assertEqual(provenance["rng"]["de_engine_seed"], m5.s3_de_engine_seed(str(self.task.task_id), 0, 0))
        self.assertEqual(provenance["rng"]["bo_engine_seed"], None)

    def test_04_invalid_arm_and_budget(self):
        with self.assertRaises(m5.S3ArmError):
            m5.run_s3_arm("S3-BO-UNKNOWN", _evaluator([]), task=self.task, budget=64, opt_seed=0, meta_seed=0)
        with self.assertRaises(m5.S3ArmError):
            m5.run_s3_bo_arm(m5.S3_BO_RANDOM, _evaluator([]), task=self.task, budget=96, opt_seed=0, meta_seed=0)
        with self.assertRaises(m5.S3ArmError):
            m5.run_s3_bo_arm(m5.S3_BO_FOMAML_OBJ, _evaluator([]), task=self.task, budget=64, opt_seed=0, meta_seed=0, scorer=None)

    def test_05_de_arm_deterministic(self):
        first = m5.run_s3_de_arm(_evaluator([]), task=self.task, budget=64, opt_seed=1, meta_seed=1)
        second = m5.run_s3_de_arm(_evaluator([]), task=self.task, budget=64, opt_seed=1, meta_seed=1)
        first_trace = [record.design_u for record in first.observations]
        second_trace = [record.design_u for record in second.observations]
        self.assertEqual(first_trace, second_trace)


class FairnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.task = _task()
        cls.results = {}
        for arm in m5.S3_ARM_IDS:
            scorer = None
            if arm == m5.S3_BO_FOMAML_OBJ or arm == m5.S3_BO_FOMAML_CON:
                scorer = _scorer(False)
            elif arm == m5.S3_BO_ANIL_CON:
                scorer = _scorer(True)
            cls.results[arm] = m5.run_s3_arm(arm, _evaluator([]), task=cls.task, budget=64, opt_seed=0, meta_seed=0, scorer=scorer)
        cls.runs = [
            {
                "arm": result.arm,
                "task_id": result.task_id,
                "budget": result.budget,
                "opt_seed": 0,
                "meta_seed": 0,
                "s3_provenance": m5.s3_arm_provenance(result),
            }
            for result in cls.results.values()
        ]

    def test_01_fairness_ok(self):
        report = m5.s3_fairness_report(self.runs)
        self.assertTrue(report["ok"], report["problems"])
        self.assertEqual(len(report["groups"]), 1)
        group = report["groups"][0]
        self.assertEqual(group["arms"], sorted(m5.S3_ARM_IDS))
        self.assertEqual(group["clone_pairs"], [])
        self.assertIn(m5.S3_BO_RANDOM, group["initial_designs_sha256"])
        self.assertEqual(
            group["initial_designs_sha256"][m5.S3_BO_RANDOM],
            group["initial_designs_sha256"][m5.S3_DE],
        )
        self.assertEqual(report["exempt_pairs"], [[m5.S3_BO_RANDOM, m5.S3_DE]])
        self.assertEqual(report["clone_rate_by_budget"]["64"], 0.0)
        self.assertEqual(report["identifiability_by_budget"]["64"], m5.S3_IDENTIFIABLE)

    def test_02_support_hash_mismatch_problem(self):
        runs = [dict(run) for run in self.runs]
        runs[1] = dict(runs[1])
        provenance = dict(runs[1]["s3_provenance"])
        provenance["initial"] = dict(provenance["initial"])
        provenance["initial"]["support_designs_sha256"] = "0" * 64
        runs[1]["s3_provenance"] = provenance
        report = m5.s3_fairness_report(runs)
        self.assertFalse(report["ok"])
        self.assertTrue(any("support_designs_sha256" in problem for problem in report["problems"]))

    def test_03_missing_arm_problem(self):
        report = m5.s3_fairness_report(self.runs[:-1])
        self.assertFalse(report["ok"])
        self.assertTrue(any("臂集合不完整" in problem for problem in report["problems"]))

    def test_04_duplicate_run_rejected(self):
        with self.assertRaises(m5.S3ArmError):
            m5.s3_fairness_report([*self.runs, self.runs[0]])

    def test_05_trace_divergence(self):
        self.assertIsNone(m5.s3_trace_first_divergence(["a", "b"], ["a", "b"]))
        self.assertEqual(m5.s3_trace_first_divergence(["a", "b"], ["a", "c"]), 1)
        self.assertEqual(m5.s3_trace_first_divergence(["a"], ["a", "b"]), 1)


class ScorerTests(unittest.TestCase):
    def test_01_predict_shape_and_finite(self):
        scorer = _scorer(False)
        predictions = scorer.predict(np.full((7, 12), 0.5))
        self.assertEqual(predictions.shape, (7, 3))
        self.assertTrue(np.all(np.isfinite(predictions)))

    def test_02_adapt_returns_scorer(self):
        scorer = _scorer(False)
        rng = np.random.default_rng(0)
        features = rng.uniform(0.0, 1.0, size=(5, 12))
        targets = rng.normal(size=(5, 3))
        adapted = scorer.adapt(features, targets)
        self.assertIsInstance(adapted, m5.S3ModelScorer)
        self.assertFalse(np.array_equal(scorer.parameters.tensors[0], adapted.parameters.tensors[0]))
        self.assertEqual(adapted.meta_seed, 0)

    def test_03_anil_adapt_keeps_body(self):
        scorer = _scorer(True)
        rng = np.random.default_rng(1)
        features = rng.uniform(0.0, 1.0, size=(5, 12))
        targets = rng.normal(size=(5, 3))
        adapted = scorer.adapt(features, targets)
        head = maml._head_tensor_indices(scorer.parameters)
        for index, (before, after) in enumerate(zip(scorer.parameters.tensors, adapted.parameters.tensors)):
            if index in head:
                self.assertFalse(np.array_equal(before, after))
            else:
                self.assertTrue(np.array_equal(before, after))

    def test_04_scorer_rejects_wrong_dims(self):
        config = _proxy_config(output_dim=1)
        parameters = maml.init_parameters(config, seed=0)
        with self.assertRaises(m5.S3ArmError):
            m5.S3ModelScorer(parameters, config, meta_seed=0)


if __name__ == "__main__":
    unittest.main()
