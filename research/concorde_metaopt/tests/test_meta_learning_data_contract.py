"""P4 元学习数据合同单元测试（设计 §3.2 / §6 / §12-3、4、12）。

覆盖：MetaSample 全字段校验、非法 source_kind/physics 组合、objective/status
联合规则、constraints 键集合、split 枚举与归档映射、任务级 split 互斥、
support/query 不相交与泄漏用例、归档记录字段。
"""
import unittest

import numpy as np

from research.concorde_metaopt.meta_learning import data_contract as dc
from research.concorde_metaopt.meta_learning.data_contract import (
    CONSTRAINT_NAMES,
    DESIGN_LOWER,
    DESIGN_NAMES,
    DESIGN_SET,
    DESIGN_UPPER,
    SPLITS,
    DataContractError,
    MetaSample,
)


BASE_DESIGN = tuple((float(lo) + float(hi)) / 2.0 for lo, hi in zip(DESIGN_LOWER, DESIGN_UPPER))
BASE_CONTEXT = {"context_1": 1.0, "context_2": 1.0}
BASE_UTC = "2026-11-02T00:00:00+00:00"


def make_sample(task_id="task-a", **overrides):
    """构造一条合法合成样本；overrides 覆盖任意字段。"""
    design = overrides.pop("design", BASE_DESIGN)
    kwargs = dict(
        task_id=task_id,
        fidelity="synthetic",
        evaluator_id="synthetic__analytic__12d_lifting_surfaces__v1",
        design_set=DESIGN_SET,
        design=design,
        design_normalized=dc.design_to_normalized(design),
        config_hash="a" * 64,
        objective=1.0,
        constraints={name: None for name in CONSTRAINT_NAMES},
        status="VALID",
        source_kind="synthetic",
        physics_validation_status="NOT_APPLICABLE",
        git_sha="deadbeef",
        seed=0,
        physical_call_count=0,
        split="meta_train",
        task_context=dict(BASE_CONTEXT),
        created_utc=BASE_UTC,
    )
    kwargs.update(overrides)
    return MetaSample(**kwargs)


def unique_designs(count):
    """生成 count 个互异的合法物理 design（沿单位区间均匀取点再解码）。"""
    designs = []
    for index in range(count):
        fraction = (index + 1) / (count + 2)
        normalized = [fraction] * len(DESIGN_NAMES)
        designs.append(dc.design_from_normalized(normalized))
    return designs


class MetaSampleValidationTests(unittest.TestCase):
    def test_01_valid_sample(self):
        self.assertEqual(dc.validate_sample(make_sample()), [])
        dc.require_valid(make_sample())

    def test_02_missing_field_rejected(self):
        kwargs = make_sample().to_dict()
        del kwargs["task_context"]
        with self.assertRaises(TypeError):
            MetaSample(**kwargs)

    def test_03_illegal_source_kind(self):
        errors = dc.validate_sample(make_sample(source_kind="bogus", evaluator_id="bogus__x__y__v1"))
        self.assertTrue(any("source_kind" in error for error in errors))

    def test_04_physics_combination(self):
        errors = dc.validate_sample(make_sample(physics_validation_status="VALIDATED"))
        self.assertTrue(any("NOT_APPLICABLE" in error for error in errors))
        hf = make_sample(
            source_kind="validated_real_hf",
            physics_validation_status="VALIDATED",
            evaluator_id="validated_real_hf__rcaide_single_cruise__12d_lifting_surfaces__p2v1",
        )
        self.assertEqual(dc.validate_sample(hf), [])
        bad_hf = make_sample(
            source_kind="validated_real_hf",
            physics_validation_status="PARTIAL",
            evaluator_id="validated_real_hf__rcaide_single_cruise__12d_lifting_surfaces__p2v1",
        )
        self.assertTrue(dc.validate_sample(bad_hf))

    def test_05_objective_status_rule(self):
        errors = dc.validate_sample(make_sample(objective=1.0, status="INVALID"))
        self.assertTrue(any("objective 非空" in error for error in errors))
        nonfinite = make_sample(objective=float("nan"))
        self.assertTrue(any("objective" in error for error in dc.validate_sample(nonfinite)))
        failed = make_sample(objective=None, status="NONFINITE")
        self.assertEqual(dc.validate_sample(failed), [])
        leaked = make_sample(objective=None, status="VALID")
        self.assertTrue(any("objective 为 null" in error for error in dc.validate_sample(leaked)))


    def test_06_physical_call_count_non_negative(self):
        self.assertTrue(any("physical_call_count" in error for error in dc.validate_sample(make_sample(physical_call_count=-1))))
        # 离线守卫在 runner/evaluator 层，数据合同只要求非负整数
        self.assertEqual(dc.validate_sample(make_sample(physical_call_count=1)), [])

    def test_07_constraints_key_set(self):
        constraints = {name: None for name in CONSTRAINT_NAMES}
        constraints.pop(CONSTRAINT_NAMES[0])
        errors = dc.validate_sample(make_sample(constraints=constraints))
        self.assertTrue(any("constraints" in error for error in errors))
        extra = {name: None for name in CONSTRAINT_NAMES}
        extra["not_a_constraint"] = 0.0
        errors = dc.validate_sample(make_sample(constraints=extra))
        self.assertTrue(any("constraints" in error for error in errors))
        bad = {name: None for name in CONSTRAINT_NAMES}
        bad[CONSTRAINT_NAMES[0]] = float("inf")
        errors = dc.validate_sample(make_sample(constraints=bad))
        self.assertTrue(any("constraints" in error for error in errors))

    def test_08_created_utc_format(self):
        errors = dc.validate_sample(make_sample(created_utc="2026-11-02T00:00:00Z"))
        self.assertTrue(any("created_utc" in error for error in errors))

    def test_09_evaluator_id_pattern(self):
        errors = dc.validate_sample(make_sample(evaluator_id="synthetic"))
        self.assertTrue(any("evaluator_id" in error for error in errors))
        errors = dc.validate_sample(make_sample(source_kind="archived_real_lf", evaluator_id="synthetic__analytic__12d_lifting_surfaces__v1"))
        self.assertTrue(any("source_kind" in error for error in errors))

    def test_10_design_normalization_consistency(self):
        sample = make_sample()
        wrong = list(sample.design_normalized)
        wrong[0] = min(1.0, wrong[0] + 0.2)
        errors = dc.validate_sample(make_sample(design_normalized=tuple(wrong)))
        self.assertTrue(any("不一致" in error for error in errors))


    def test_11_ood_flag_contract(self):
        # §3.2:162 / §4.4：OOD 标记必须是数值键 ood_flag=1.0，且不进 14 维特征
        ood_context = dict(BASE_CONTEXT)
        ood_context[dc.OOD_FLAG_NAME] = 1.0
        self.assertEqual(
            dc.validate_sample(make_sample(split="meta_test_ood", task_context=ood_context)), []
        )
        missing = dc.validate_sample(make_sample(split="meta_test_ood"))
        self.assertTrue(any("ood_flag" in error for error in missing))
        wrong = dc.validate_sample(make_sample(split="meta_train", task_context=ood_context))
        self.assertTrue(any("ood_flag" in error for error in wrong))
        zero_context = dict(BASE_CONTEXT)
        zero_context[dc.OOD_FLAG_NAME] = 0.0
        self.assertEqual(dc.validate_sample(make_sample(split="meta_train", task_context=zero_context)), [])
        extra = dc.validate_sample(make_sample(task_context=dict(BASE_CONTEXT, other=1.0)))
        self.assertTrue(any("task_context" in error for error in extra))
        constraints = {name: None for name in CONSTRAINT_NAMES}
        constraints[CONSTRAINT_NAMES[0]] = -0.1
        sample = make_sample(split="meta_test_ood", task_context=ood_context, constraints=constraints)
        record = dc.to_archive_records([sample])[0]
        self.assertEqual(len(record["features"]), 14)
        self.assertEqual(record["task_id"], "task-a")

class SplitAndDivideTests(unittest.TestCase):
    def _samples_for_tasks(self, task_ids, per_task=2):
        samples = []
        for task_index, task_id in enumerate(task_ids):
            for design in unique_designs(per_task):
                samples.append(make_sample(task_id=task_id, design=design, seed=task_index))
        return samples

    def test_01_split_enum(self):
        for split in SPLITS:
            dc.validate_split(split)
        with self.assertRaises(DataContractError):
            dc.validate_split("bogus")
        with self.assertRaises(DataContractError):
            dc.validate_split(None)

    def test_02_archive_split_mapping(self):
        self.assertEqual(set(dc.ARCHIVE_SPLIT_MAP), set(SPLITS))
        self.assertEqual(set(dc.ARCHIVE_SPLITS), {"train", "validation", "test"})
        self.assertEqual(dc.archive_split_for("meta_train"), "train")
        self.assertEqual(dc.archive_split_for("meta_validation"), "validation")
        self.assertEqual(dc.archive_split_for("meta_test"), "test")
        self.assertEqual(dc.archive_split_for("meta_test_ood"), "test")
        self.assertIsNone(dc.archive_split_for("negative_control"))

    def test_03_archive_splits_required_keys(self):
        splits = ["meta_train", "meta_validation", "meta_test", "meta_test_ood", "negative_control"]
        samples = []
        for index, split in enumerate(splits):
            context = dict(BASE_CONTEXT)
            if split == "meta_test_ood":
                context[dc.OOD_FLAG_NAME] = 1.0
            samples.append(make_sample(task_id=f"task-{index}", split=split, task_context=context))
        grouped = dc.to_archive_splits(samples)
        self.assertEqual(set(grouped), set(dc.ARCHIVE_SPLITS))
        self.assertEqual(grouped["train"], ["task-0"])
        self.assertEqual(grouped["validation"], ["task-1"])
        self.assertEqual(grouped["test"], ["task-2", "task-3"])  # OOD 只进 test 存储桶
        all_ids = set(grouped["train"]) | set(grouped["validation"]) | set(grouped["test"])
        self.assertNotIn("task-4", all_ids)  # 负控制不归档

    def test_04_split_by_task_no_leak(self):
        task_ids = [f"task-{index}" for index in range(8)]
        samples = self._samples_for_tasks(task_ids)
        result = dc.split_by_task(samples, {"meta_train": 0.5, "meta_validation": 0.25, "meta_test": 0.25}, seed=0)
        self.assertEqual(set(result), {"meta_train", "meta_validation", "meta_test"})
        seen = set()
        for split, members in result.items():
            split_tasks = {sample.task_id for sample in members}
            self.assertFalse(seen & split_tasks, f"{split} 与已分配任务重叠")
            seen |= split_tasks
        self.assertEqual(seen, set(task_ids))
        dc.assert_task_disjoint(result)

    def test_05_task_leakage_construct_fails(self):
        sample = make_sample(task_id="task-a")
        with self.assertRaises(DataContractError):
            dc.assert_task_disjoint({"meta_train": [sample]}, {"meta_test": [sample]})
        with self.assertRaises(DataContractError):
            dc.assert_task_disjoint({"meta_train": ["task-a"]}, {"meta_test": ["task-a"]})

    def test_06_support_query_no_leak_nested(self):
        designs = unique_designs(20)
        samples = [make_sample(task_id="task-a", design=design) for design in designs]
        support_1, query = dc.support_query_split(samples, "task-a", 1, 8, seed=0)
        support_5, query_5 = dc.support_query_split(samples, "task-a", 5, 8, seed=0)
        self.assertEqual(len(support_1), 1)
        self.assertEqual(len(support_5), 5)
        self.assertEqual(len(query), 8)
        self.assertEqual({sample.design_id for sample in query}, {sample.design_id for sample in query_5})
        self.assertTrue({sample.design_id for sample in support_1} <= {sample.design_id for sample in support_5})
        for left in support_5:
            for right in query:
                self.assertGreater(max(abs(a - b) for a, b in zip(left.design, right.design)), 1e-12)
        with self.assertRaises(DataContractError):
            dc.support_query_split(samples, "task-a", 2, 19, seed=0)

    def test_07_duplicate_design_leak_is_rejected(self):
        duplicate = dc.design_from_normalized([0.5] * len(DESIGN_NAMES))
        other = dc.design_from_normalized([0.25] * len(DESIGN_NAMES))
        samples = [
            make_sample(task_id="task-a", design=duplicate),
            make_sample(task_id="task-a", design=duplicate),
            make_sample(task_id="task-a", design=duplicate),
            make_sample(task_id="task-a", design=other),
        ]
        with self.assertRaises(DataContractError):
            dc.support_query_split(samples, "task-a", 1, 2, seed=0)

    def test_08_design_normalization_roundtrip(self):
        normalized = dc.design_to_normalized(BASE_DESIGN)
        self.assertEqual(len(normalized), 12)
        restored = dc.design_from_normalized(normalized)
        np.testing.assert_allclose(np.asarray(restored), np.asarray(BASE_DESIGN), atol=1e-12)
        with self.assertRaises(DataContractError):
            dc.design_to_normalized((1.0, 2.0))
        with self.assertRaises(DataContractError):
            dc.design_from_normalized((0.5,) * 13)


class ArchiveRecordTests(unittest.TestCase):
    def test_01_target_names(self):
        constraints = {name: None for name in CONSTRAINT_NAMES}
        constraints[CONSTRAINT_NAMES[0]] = -0.1
        sample = make_sample(constraints=constraints)
        self.assertEqual(dc.archive_target_names([sample]), ("objective", CONSTRAINT_NAMES[0]))

    def test_02_archive_records(self):
        constraints = {name: None for name in CONSTRAINT_NAMES}
        constraints[CONSTRAINT_NAMES[0]] = -0.1
        sample = make_sample(constraints=constraints)
        records = dc.to_archive_records([sample])
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["status"], "VALID")
        self.assertEqual(record["data_origin"], "SYNTHETIC_TEST")
        # A10：schema-2 要求 labeled 记录 analysis_calls>=1；物理调用计数另字段为 0
        self.assertEqual(record["analysis_calls"], 1)
        self.assertNotIn("physical_call_count", record)
        backend = record["provenance"]["backend"]
        self.assertEqual(backend["platform"], "SYNTHETIC_ANALYTIC")
        self.assertEqual(backend["data_origin"], "SYNTHETIC_TEST")
        self.assertEqual(len(record["targets"]), 2)
        self.assertEqual(len(record["features"]), 14)  # 12 维设计 + 2 维 context

    def test_03_archive_requires_objective(self):
        sample = make_sample(objective=None, status="INVALID")
        self.assertEqual(dc.validate_sample(sample), [])
        with self.assertRaises(DataContractError):
            dc.to_archive_records([sample])
        with self.assertRaises(DataContractError):
            dc.to_archive_splits([])

    def test_04_constraint_names_match_evaluation_contract(self):
        from research.concorde_metaopt.evaluation import contract as evaluation_contract

        self.assertEqual(tuple(CONSTRAINT_NAMES), tuple(evaluation_contract.CONSTRAINT_NAMES))
        self.assertEqual(dc.FEASIBILITY_TOLERANCE, evaluation_contract.FEASIBILITY_TOLERANCE)
        self.assertEqual(dc.FEASIBILITY_TOLERANCE, 1e-12)


class LedgerRowTests(unittest.TestCase):
    def test_01_valid_row(self):
        row = {
            "design": list(BASE_DESIGN),
            "design_u": list(dc.design_to_normalized(BASE_DESIGN)),
            "status": "VALID",
            "objective": 3.5,
            "constraints_g_le_zero": {CONSTRAINT_NAMES[0]: -0.2},
            "task_context": dict(BASE_CONTEXT),
        }
        sample = dc.from_ledger_row(
            row,
            task_id="task-a",
            config_hash="a" * 64,
            git_sha="deadbeef",
            source_kind="synthetic",
            physics_validation_status="NOT_APPLICABLE",
        )
        self.assertEqual(dc.validate_sample(sample), [])
        self.assertAlmostEqual(sample.objective, 3.5)
        self.assertEqual(sample.status, "VALID")

    def test_02_failed_row_objective_null(self):
        row = {
            "design": list(BASE_DESIGN),
            "valid": False,
            "status": "MISSION_FAILED",
            "objective": None,
            "task_context": dict(BASE_CONTEXT),
        }
        sample = dc.from_ledger_row(
            row,
            task_id="task-a",
            config_hash="a" * 64,
            git_sha="deadbeef",
            source_kind="synthetic",
            physics_validation_status="NOT_APPLICABLE",
        )
        self.assertIsNone(sample.objective)
        self.assertEqual(sample.status, "MISSION_FAILED")
        self.assertEqual(dc.validate_sample(sample), [])
        with self.assertRaises(DataContractError):
            dc.from_ledger_row(
                {"design": list(BASE_DESIGN), "status": "BOGUS"},
                task_id="task-a",
                config_hash="a" * 64,
                git_sha="deadbeef",
                source_kind="synthetic",
                physics_validation_status="NOT_APPLICABLE",
            )


if __name__ == "__main__":
    unittest.main()
