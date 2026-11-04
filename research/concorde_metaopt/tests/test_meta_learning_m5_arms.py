"""P4-M5 四个可识别优化臂（m5_arms）单元测试。

覆盖：
* 冻结常量与臂顺序（4 臂、两预算档、10 个优化 seed、3 个元训练 seed）；
* 指纹工具 designs_digest / artifact_sha256 的确定性与 1e-12 容差语义；
* 代理 artifact 构造（pretrain 与 MAML 指纹必须不同）；
* 代理打分选初始点（64 候选 -> 8 唯一、界内、候选池指纹稳定、篡改被拒）；
* 四臂等预算运行（恰 budget 次真实评价、physical_call_count=0、臂名/实现标签正确）；
* M5-DE 与 M5-BO-random 共享同一 8 点初始种群（公平性设计）；
* 可识别性审计（模型臂初始点与 random 重合时判 CLONE、pretrain 与 MAML 重合时判
  RANKING_INDISTINGUISHABLE、DE 固定 SAME_INIT_DIFFERENT_ENGINE）；
* 公平性/等预算 fail-closed 审计（预算不符、重复组、物理调用非 0、初始点不唯一、
  候选池/artifact 指纹不一致）；
* 参数校验错误路径。

全部使用解析合成任务与合成 evaluator，无任何物理调用。
"""
import unittest
from dataclasses import replace

import numpy as np

from research.concorde_metaopt.meta_learning import m5_arms as m5
from research.concorde_metaopt.meta_learning.baseline_arms import (
    make_synthetic_task_evaluator,
    shared_initial_designs,
)
from research.concorde_metaopt.meta_learning.offline_runner import (
    build_task_blocks,
    load_design_space_12d,
)
from research.concorde_metaopt.meta_learning.task_family import (
    build_task_family,
    default_task_family_config,
)


def _tiny_family_config():
    """tiny v2 任务族：只用于单元测试，不参与正式结论。"""
    return default_task_family_config(
        family_id="F-QE-feasible-v2",
        family_version="v2",
        radius_base=0.85,
        seed=20261102,
        train_tasks=2,
        validation_tasks=1,
        test_tasks=1,
        ood_tasks=0,
        negative_control_tasks=0,
        designs_per_task=12,
        support_pool_size=8,
        query_size=4,
    )


def _records_with_initial(record, initial):
    """把一条记录的初始设计替换为给定矩阵（用于构造审计用例）。"""
    matrix = np.asarray(initial, dtype=np.float64)
    return replace(
        record,
        initial_designs=tuple(tuple(float(value) for value in row) for row in matrix),
        initial_designs_sha256=m5.designs_digest(matrix),
    )


class M5ConstantsTests(unittest.TestCase):
    """冻结参数必须与 Issue #5 D-P4-002 / 预注册一致。"""

    def test_arm_order_and_names(self):
        self.assertEqual(
            m5.M5_ARM_ORDER,
            ("M5-BO-random", "M5-BO-pretrain-init", "M5-BO-MAML-init", "M5-DE"),
        )
        self.assertEqual(set(m5.M5_BO_ARMS) | {m5.M5_DE}, set(m5.M5_ARM_ORDER))
        self.assertEqual(m5.M5_ARM_ORDER, tuple(m5.M5_ARMS))

    def test_frozen_init_values(self):
        self.assertEqual(m5.M5_CANDIDATE_POOL_SIZE, 64)
        self.assertEqual(m5.M5_INITIAL_DESIGN_COUNT, 8)
        self.assertEqual(m5.M5_DIVERSITY_CANDIDATE_COUNT, 64)
        self.assertEqual(m5.M5_DEDUP_TOLERANCE, 1e-12)
        self.assertEqual(m5.M5_DE_POPULATION_SIZE, 8)
        self.assertEqual(m5.M5_DE_MUTATION_FACTOR, 0.5)
        self.assertEqual(m5.M5_DE_CROSSOVER_RATE, 0.7)
        self.assertEqual(tuple(m5.M5_BUDGETS), (64, 128))
        self.assertEqual(len(list(m5.M5_OPTIMIZATION_SEEDS)), 10)
        self.assertEqual(tuple(m5.M5_META_SEEDS), (0, 1, 2))
        self.assertEqual(m5.M5_FROZEN_INIT["dedup_tolerance"], 1e-12)
        self.assertEqual(m5.M5_FROZEN_INIT["maml_init_candidate_count"], 64)
        self.assertEqual(m5.M5_FROZEN_INIT["physical_call_count"], 0)

    def test_arm_metadata_and_invalid_arm(self):
        for arm in m5.M5_ARM_ORDER:
            meta = m5.arm_metadata(arm)
            self.assertEqual(meta["arm"], arm)
            self.assertEqual(meta["physical_call_count"], 0)
            self.assertTrue(meta["code_path"])
            self.assertTrue(meta["implementation"])
        self.assertTrue(m5.arm_metadata(m5.M5_BO_PRETRAIN_INIT)["uses_proxy"])
        self.assertFalse(m5.arm_metadata(m5.M5_DE)["uses_proxy"])
        with self.assertRaises(m5.M5ArmError):
            m5.arm_metadata("M5-NOT-AN-ARM")


class M5DigestTests(unittest.TestCase):
    """指纹工具：确定性 + 1e-12 去重容差。"""

    def test_designs_digest_deterministic_and_rounded(self):
        rng = np.random.default_rng(0)
        matrix = rng.uniform(0.0, 1.0, size=(8, 12))
        first = m5.designs_digest(matrix)
        second = m5.designs_digest(matrix.copy())
        self.assertEqual(first, second)
        perturbed = matrix.copy()
        perturbed[0, 0] += 1e-15
        self.assertEqual(first, m5.designs_digest(perturbed))
        perturbed[0, 0] += 1e-10
        self.assertNotEqual(first, m5.designs_digest(perturbed))

    def test_designs_digest_shape_validation(self):
        with self.assertRaises(m5.M5ArmError):
            m5.designs_digest(np.zeros((8, 11)))
        with self.assertRaises(m5.M5ArmError):
            m5.designs_digest(np.zeros(12))

    def test_artifact_sha256_changes_with_parameters(self):
        artifact = {
            "parameters": {"tensors": [np.array([1.0, 2.0]), np.array([0.5])]},
            "config": {"input_dim": 2},
        }
        first = m5.artifact_sha256(artifact)
        self.assertEqual(first, m5.artifact_sha256(artifact))
        changed = {
            "parameters": {"tensors": [np.array([1.0, 2.0001]), np.array([0.5])]},
            "config": {"input_dim": 2},
        }
        self.assertNotEqual(first, m5.artifact_sha256(changed))
        with self.assertRaises(m5.M5ArmError):
            m5.artifact_sha256({"config": {"input_dim": 2}})


class _M5Fixture(unittest.TestCase):
    """共享一次 tiny v2 任务族 + 代理 artifact + 四臂运行的测试夹具。"""

    @classmethod
    def setUpClass(cls):
        cls.config = _tiny_family_config()
        cls.tasks = build_task_family(cls.config)
        cls.design_space = load_design_space_12d()
        cls.blocks = build_task_blocks(cls.tasks)
        cls.artifacts = m5.build_m5_model_artifacts(
            cls.blocks, cls.tasks, meta_seed=0, maml_steps=2, pretrain_steps=3
        )
        cls.task = [task for task in cls.tasks if task.split == "meta_train"][0]
        cls.reference = cls.task.reference()
        cls.evaluator = make_synthetic_task_evaluator(cls.task, cls.design_space)
        cls.budget = 8
        cls.results = {}
        cls.records = []
        for arm in m5.M5_ARM_ORDER:
            artifact = None
            if arm == m5.M5_BO_PRETRAIN_INIT:
                artifact = cls.artifacts["pretrain"]
            elif arm == m5.M5_BO_MAML_INIT:
                artifact = cls.artifacts["maml"]
            result = m5.run_m5_arm(
                arm,
                cls.evaluator,
                task=cls.task,
                seed=0,
                budget=cls.budget,
                design_space=cls.design_space,
                model_artifact=artifact,
                reference_objective=cls.reference["objective_star"],
                run_id="unit-test-m5",
            )
            cls.results[arm] = result
            cost = dict(result.proxy_scoring_cost)
            cls.records.append(
                m5.arm_init_record(
                    result,
                    meta_seed=cost.get("meta_seed"),
                    candidate_pool_sha256=cost.get("candidate_pool_sha256"),
                    artifact_sha256=cost.get("artifact_sha256"),
                )
            )


class M5ModelArtifactTests(_M5Fixture):
    """代理 artifact 构造与打分。"""

    def test_artifacts_distinct_and_targets(self):
        self.assertNotEqual(
            self.artifacts["artifacts_sha256"]["pretrain"],
            self.artifacts["artifacts_sha256"]["maml"],
        )
        self.assertEqual(self.artifacts["meta_seed"], 0)
        self.assertEqual(self.artifacts["physical_call_count"], 0)
        target_names = tuple(self.artifacts["target_names"])
        self.assertEqual(target_names[0], "objective")
        self.assertGreaterEqual(len(target_names), 2)
        self.assertEqual(self.artifacts["pretrain"]["target_names"], target_names)

    def test_score_init_designs_unique_in_bounds(self):
        scored = m5.score_m5_init_designs(
            self.artifacts["maml"],
            self.design_space,
            self.task,
            seed=0,
            method="maml",
        )
        designs = np.asarray(scored["designs"], dtype=np.float64)
        self.assertEqual(designs.shape, (m5.M5_INITIAL_DESIGN_COUNT, 12))
        self.assertTrue(np.all(np.isfinite(designs)))
        self.assertTrue(np.all(designs >= 0.0) and np.all(designs <= 1.0))
        self.assertEqual(len(m5._rounded_design_set(designs)), m5.M5_INITIAL_DESIGN_COUNT)
        cost = scored["proxy_scoring_cost"]
        self.assertEqual(cost["candidates_scored"], m5.M5_CANDIDATE_POOL_SIZE)
        self.assertEqual(cost["true_evaluation_budget_used"], 0)
        self.assertEqual(cost["proxy_method"], "maml")
        # 候选池与调用方无关，必须可跨臂/跨调用复现。
        repeat = m5.score_m5_init_designs(
            self.artifacts["maml"],
            self.design_space,
            self.task,
            seed=0,
            method="maml",
        )
        self.assertEqual(scored["candidate_pool_sha256"], repeat["candidate_pool_sha256"])
        self.assertEqual(scored["initial_designs_sha256"], repeat["initial_designs_sha256"])
        pretrain = m5.score_m5_init_designs(
            self.artifacts["pretrain"],
            self.design_space,
            self.task,
            seed=0,
            method="none",
        )
        self.assertEqual(pretrain["candidate_pool_sha256"], scored["candidate_pool_sha256"])

    def test_score_init_designs_validation(self):
        with self.assertRaises(m5.M5ArmError):
            m5.score_m5_init_designs(
                {"artifact": self.artifacts["maml"]["artifact"], "artifact_sha256": "0" * 64},
                self.design_space,
                self.task,
                seed=0,
                method="maml",
            )
        with self.assertRaises(m5.M5ArmError):
            m5.score_m5_init_designs(
                self.artifacts["maml"], self.design_space, self.task, seed=0, method="from_scratch"
            )
        with self.assertRaises(m5.M5ArmError):
            m5.score_m5_init_designs({"no-artifact": 1}, self.design_space, self.task, seed=0, method="maml")

    def test_artifact_tampering_rejected(self):
        tampered = dict(self.artifacts["maml"])
        tampered["artifact_sha256"] = "f" * 64
        with self.assertRaises(m5.M5ArmError):
            m5.score_m5_init_designs(
                tampered, self.design_space, self.task, seed=0, method="maml"
            )


class M5ArmRunTests(_M5Fixture):
    """四臂等预算运行与可识别性/公平性审计。"""

    def test_four_arms_equal_budget_and_physical_zero(self):
        for arm in m5.M5_ARM_ORDER:
            result = self.results[arm]
            self.assertEqual(result.arm, arm)
            self.assertEqual(result.true_evals_used, self.budget)
            self.assertEqual(result.requested_evaluations, self.budget)
            self.assertEqual(result.to_dict()["physical_call_count"], 0)
            self.assertEqual(result.implementation, m5.ARM_IMPLEMENTATIONS[arm])
            self.assertEqual(len(result.observations), self.budget)

    def test_bo_random_uses_shared_initial_designs(self):
        initial = shared_initial_designs(self.task.task_id, 0, count=m5.M5_INITIAL_DESIGN_COUNT)
        random_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_RANDOM)]
        self.assertEqual(random_record.initial_designs_sha256, m5.designs_digest(initial))
        self.assertEqual(random_record.initializer, "shared_lhs_8")
        cost = dict(self.results[m5.M5_BO_RANDOM].proxy_scoring_cost)
        self.assertEqual(cost["kind"], "shared_lhs_init")
        self.assertEqual(cost["true_evaluation_budget_used"], 0)

    def test_model_arms_use_scored_initial_designs(self):
        overlap = m5._initial_overlap(
            self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_MAML_INIT)].initial_designs,
            self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_RANDOM)].initial_designs,
        )
        self.assertLess(overlap, 1.0)
        for index, arm in ((1, m5.M5_BO_PRETRAIN_INIT), (2, m5.M5_BO_MAML_INIT)):
            record = self.records[index]
            self.assertEqual(record.arm, arm)
            self.assertEqual(record.initializer, m5.ARM_INITIALIZERS[arm])
            self.assertIsNotNone(record.candidate_pool_sha256)
            self.assertIsNotNone(record.artifact_sha256)
            cost = dict(self.results[arm].proxy_scoring_cost)
            self.assertEqual(cost["kind"], "model_scored_init")
            self.assertEqual(cost["true_evaluation_budget_used"], 0)
            self.assertEqual(cost["candidates_scored"], m5.M5_CANDIDATE_POOL_SIZE)

    def test_de_shares_initial_population_with_bo_random(self):
        de_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_DE)]
        random_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_RANDOM)]
        self.assertEqual(de_record.initial_designs_sha256, random_record.initial_designs_sha256)
        self.assertEqual(de_record.initializer, "shared_lhs_8")

    def test_fairness_audit_passes(self):
        fairness = m5.assert_m5_fairness(self.records)
        self.assertEqual(fairness["status"], "PASS")
        self.assertEqual(fairness["records"], 4)
        self.assertEqual(fairness["physical_call_count"], 0)

    def test_fairness_audit_accepts_meta_seed_dimension(self):
        """模型打分臂按 meta seed 各一条记录属预注册设计，不是重复组。"""
        random_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_RANDOM)]
        de_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_DE)]
        pretrain = self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_PRETRAIN_INIT)]
        maml = self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_MAML_INIT)]
        multi = [replace(random_record), replace(de_record)]
        for meta_seed in (0, 1, 2):
            multi.append(replace(pretrain, meta_seed=meta_seed))
            multi.append(replace(maml, meta_seed=meta_seed))
        fairness = m5.assert_m5_fairness(multi)
        self.assertEqual(fairness["status"], "PASS")
        self.assertEqual(fairness["records"], 8)
        self.assertEqual(fairness["groups"], 4)
        self.assertEqual(
            fairness["group_key_fields"], ["task_id", "seed", "budget", "meta_seed"]
        )
        # 同一 (task, seed, budget, arm, meta_seed) 出现两次仍然是重复组 → fail-closed
        with self.assertRaises(m5.M5ArmError):
            m5.assert_m5_fairness(multi + [replace(pretrain, meta_seed=0)])

    def test_identifiability_audit_labels(self):
        audit = m5.identifiability_audit(self.records)
        self.assertEqual(audit["groups_checked"], 1)
        self.assertEqual(audit["physical_call_count"], 0)
        # pretrain-init 与 MAML-init 复用同一套 select_model_scored_initial_designs 实现，
        # 但代理/打分路径不同（code_path 4 条）；如实记录实现标签数=3。
        self.assertEqual(audit["distinct_implementations"], 3)
        self.assertEqual(audit["distinct_code_paths"], 4)
        labels = {(pair["arm"], pair["reference"]): pair["label"] for pair in audit["pairs"]}
        self.assertEqual(
            labels[(m5.M5_DE, m5.M5_BO_RANDOM)], "SAME_INIT_DIFFERENT_ENGINE"
        )
        self.assertIn(
            labels[(m5.M5_BO_PRETRAIN_INIT, m5.M5_BO_RANDOM)], ("IDENTIFIABLE", f"CLONE_OF_{m5.M5_BO_RANDOM}")
        )
        self.assertIn(
            labels[(m5.M5_BO_MAML_INIT, m5.M5_BO_RANDOM)], ("IDENTIFIABLE", f"CLONE_OF_{m5.M5_BO_RANDOM}")
        )
        self.assertIn(
            labels[(m5.M5_BO_MAML_INIT, m5.M5_BO_PRETRAIN_INIT)],
            ("IDENTIFIABLE", "RANKING_INDISTINGUISHABLE"),
        )
        rows = m5.identifiability_rows(audit)
        self.assertEqual(len(rows), len(audit["pairs"]))
        self.assertTrue(all(row["physical_call_count"] == 0 for row in rows))

    def test_clone_detection_when_initials_match(self):
        random_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_RANDOM)]
        pretrain_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_PRETRAIN_INIT)]
        maml_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_BO_MAML_INIT)]
        de_record = self.records[m5.M5_ARM_ORDER.index(m5.M5_DE)]
        clones = [
            _records_with_initial(pretrain_record, random_record.initial_designs),
            _records_with_initial(maml_record, random_record.initial_designs),
            replace(random_record),
            replace(de_record),
        ]
        audit = m5.identifiability_audit(clones)
        self.assertEqual(audit["status"], "CLONE_ARMS_PRESENT")
        self.assertEqual(
            audit["clone_arms"], [m5.M5_BO_MAML_INIT, m5.M5_BO_PRETRAIN_INIT]
        )
        labels = {(pair["arm"], pair["reference"]): pair["label"] for pair in audit["pairs"]}
        self.assertEqual(
            labels[(m5.M5_BO_PRETRAIN_INIT, m5.M5_BO_RANDOM)],
            f"CLONE_OF_{m5.M5_BO_RANDOM}",
        )
        self.assertEqual(
            labels[(m5.M5_BO_MAML_INIT, m5.M5_BO_RANDOM)],
            f"CLONE_OF_{m5.M5_BO_RANDOM}",
        )
        self.assertEqual(
            labels[(m5.M5_BO_MAML_INIT, m5.M5_BO_PRETRAIN_INIT)],
            "RANKING_INDISTINGUISHABLE",
        )
        self.assertEqual(audit["indistinguishable_arms"], [m5.M5_BO_MAML_INIT, m5.M5_BO_PRETRAIN_INIT])

    def test_audit_requires_records_and_rejects_duplicates(self):
        with self.assertRaises(m5.M5ArmError):
            m5.identifiability_audit([])
        with self.assertRaises(m5.M5ArmError):
            m5.identifiability_audit([self.records[0], replace(self.records[0])])

    def test_fairness_audit_fail_closed(self):
        with self.assertRaises(m5.M5ArmError):
            m5.assert_m5_fairness([])
        bad_budget = [replace(record) for record in self.records]
        bad_budget[0] = replace(bad_budget[0], true_evals_used=self.budget - 1)
        with self.assertRaises(m5.M5ArmError):
            m5.assert_m5_fairness(bad_budget)
        bad_physical = [replace(record) for record in self.records]
        bad_physical[0] = replace(bad_physical[0], physical_call_count=1)
        with self.assertRaises(m5.M5ArmError):
            m5.assert_m5_fairness(bad_physical)
        bad_unique = [replace(record) for record in self.records]
        duplicated = list(bad_unique[0].initial_designs)
        duplicated[1] = duplicated[0]
        bad_unique[0] = _records_with_initial(bad_unique[0], duplicated)
        with self.assertRaises(m5.M5ArmError):
            m5.assert_m5_fairness(bad_unique)
        mismatched_pool = [replace(record) for record in self.records]
        pretrain_index = m5.M5_ARM_ORDER.index(m5.M5_BO_PRETRAIN_INIT)
        mismatched_pool[pretrain_index] = replace(
            mismatched_pool[pretrain_index], candidate_pool_sha256="0" * 64
        )
        with self.assertRaises(m5.M5ArmError):
            m5.assert_m5_fairness(mismatched_pool)
        with self.assertRaises(m5.M5ArmError):
            m5.assert_m5_fairness([self.records[0], replace(self.records[0])])

    def test_run_arm_validation_errors(self):
        with self.assertRaises(m5.M5ArmError):
            m5.run_m5_bo_arm("M5-BAD", self.evaluator, task=self.task, seed=0, budget=self.budget)
        with self.assertRaises(m5.M5ArmError):
            m5.run_m5_bo_arm(
                m5.M5_BO_RANDOM, self.evaluator, task=self.task, seed=0, budget=4
            )
        with self.assertRaises(m5.M5ArmError):
            m5.run_m5_bo_arm(
                m5.M5_BO_MAML_INIT, self.evaluator, task=self.task, seed=0, budget=self.budget
            )
        with self.assertRaises(m5.M5ArmError):
            m5.run_m5_arm(
                "M5-BAD", self.evaluator, task=self.task, seed=0, budget=self.budget
            )
        with self.assertRaises(m5.M5ArmError):
            m5.arm_init_record(replace(self.results[m5.M5_BO_RANDOM], arm="M5-BAD"))


if __name__ == "__main__":
    unittest.main()
