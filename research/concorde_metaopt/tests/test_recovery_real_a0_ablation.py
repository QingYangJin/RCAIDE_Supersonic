"""Guard + mechanism tests for the A0 five-arm ablation (synthetic bytes only)."""
import unittest

from research.concorde_metaopt.dreal001.meta.meta_dataset import (
    MetaDataset, Observation)
from research.concorde_metaopt.dreal001.meta import real_a0_ablation as a0
from research.concorde_metaopt.dreal001.meta.task_spec import ContractError, TaskSpec

GEOM = "c" * 64


def _task(task_id, split, q):
    return TaskSpec(task_id, split, 2.0, 18288.0, q, 1000000.0, GEOM)


def _rows(task_id, base):
    rows = []
    for index in range(4):
        design = [0.0] * 12
        design[index] = float(index + 1)
        rows.append(Observation("obs-%s-s%d" % (task_id, index), task_id,
                                tuple(design), "support", "synthetic_fixture",
                                "ok", base + 10.0 * index))
    design = [0.0] * 12
    design[0] = 0.5
    rows.append(Observation("obs-%s-q0" % task_id, task_id, tuple(design),
                            "query", "synthetic_fixture", "ok", base + 4.0))
    return rows


def fixture():
    tasks = (_task("TRAIN-A", "train", 20000.0),
             _task("TRAIN-B", "train", 21000.0),
             _task("VAL-A", "val", 22000.0),
             _task("TEST-A", "test", 23000.0))
    rows = []
    for index, task in enumerate(tasks):
        rows.extend(_rows(task.task_id, 100.0 + 300.0 * index))
    return MetaDataset(tasks, tuple(rows))


class A0AblationTests(unittest.TestCase):
    def test_arm_set_separates_conditional_supervision_from_conditional_meta(self):
        self.assertEqual(a0.ARM_NAMES, (
            "RANDOM_INIT", "POOLED_PRETRAIN_12D", "COND_SUPERVISED_16D",
            "FOMAML_12D", "COND_FOMAML_16D"))
        self.assertNotIn("COND_SUPERVISED_16D", a0.META_ARMS)
        self.assertIn("COND_FOMAML_16D", a0.META_ARMS)

    def test_k_policy_is_fail_closed(self):
        for k in a0.ELIGIBLE_K:
            a0.require_k(k)
        with self.assertRaisesRegex(ContractError, "K=5 NOT_ELIGIBLE"):
            a0.require_k(5)
        with self.assertRaisesRegex(ContractError, "K=0, K=1 and K=3"):
            a0.require_k(2)

    def test_conditional_supervision_never_uses_meta_train_step(self):
        """The P2 defect: a conditional arm that calls meta_train_step is FOMAML."""
        dataset = fixture()
        config = a0.AblationConfig(hidden_sizes=(8,), max_steps=2, seed=19)
        normalizer = a0.TrainNormalizer.fit(dataset)
        built = a0.build_contexts(dataset)
        supervised = a0.train_arm(dataset, config, normalizer,
                                  "COND_SUPERVISED_16D", built_contexts=built)
        meta = a0.train_arm(dataset, config, normalizer, "COND_FOMAML_16D",
                            built_contexts=built)
        self.assertEqual(supervised["arm_family"], "SUPERVISED")
        self.assertEqual(meta["arm_family"], "META")
        self.assertEqual(supervised["cost"]["inner_gradient_updates"], 0)
        self.assertGreater(meta["cost"]["inner_gradient_updates"], 0)
        self.assertEqual(supervised["input_dim"], 16)
        self.assertEqual(meta["input_dim"], 16)

    def test_all_five_arms_run_and_score_heldout_only(self):
        dataset = fixture()
        config = a0.AblationConfig(hidden_sizes=(8,), max_steps=2, seed=19)
        result = a0.run_arm(dataset, config=config, k=1, mode="software_fixture")
        self.assertEqual(result["scope"], "SOFTWARE_FIXTURE_TRAINING_ONLY")
        self.assertEqual(result["arms"], list(a0.ARM_NAMES))
        for name in a0.ARM_NAMES:
            tasks = {row["task_id"] for row in result["scores"][name]}
            self.assertEqual(tasks, {"VAL-A", "TEST-A"})
            for row in result["scores"][name]:
                self.assertEqual(row["n_query"], 1)
                self.assertGreaterEqual(row["mae_n"], 0.0)
        fitted = set(result["attention"]["train_observation_ids"])
        self.assertFalse(any("VAL" in i or "TEST" in i for i in fitted))
        self.assertFalse(result["attention"]["test_used_for_selection"])

    def test_every_trained_arm_reports_a_frozen_checkpoint_rule(self):
        dataset = fixture()
        config = a0.AblationConfig(hidden_sizes=(8,), max_steps=3, seed=7)
        result = a0.run_arm(dataset, config=config, k=1, mode="software_fixture")
        for name in a0.TRAINED_ARMS:
            entry = result["checkpoint_selection"][name]
            self.assertIsNotNone(entry["best_step"])
            self.assertIn("validation MAE", entry["rule"])
        self.assertIsNone(result["checkpoint_selection"]["RANDOM_INIT"]["best_step"])

    def test_query_rows_are_never_borrowed_as_support(self):
        dataset = fixture()
        config = a0.AblationConfig(hidden_sizes=(8,), max_steps=2, seed=43)
        result = a0.run_arm(dataset, config=config, k=3, mode="software_fixture")
        for name in a0.ARM_NAMES:
            for row in result["scores"][name]:
                self.assertEqual(len(row["support_observation_ids"]), 3)
                self.assertFalse(set(row["support_observation_ids"])
                                 & set(row["query_observation_ids"]))

    def test_real_mode_without_admissions_fails_closed(self):
        base = fixture()
        rows = []
        for row in base.rows:
            rows.append(Observation(row.observation_id, row.task_id, row.design,
                                    row.partition, "vspaero_raw", row.status,
                                    row.di_n))
        dataset = MetaDataset(base.tasks, tuple(rows))
        with self.assertRaisesRegex(ContractError, "REAL_ADMISSION_NOT_IMPLEMENTED"):
            a0.run_arm(dataset, config=a0.AblationConfig(hidden_sizes=(8,),
                                                        max_steps=1, seed=7),
                       k=1, mode="real")

    def test_paired_differences_require_identical_coverage(self):
        left = [{"task_id": "T", "k": 1, "mae_n": 10.0, "rmse_n": 12.0}]
        right = [{"task_id": "T", "k": 1, "mae_n": 7.0, "rmse_n": 9.0}]
        rows = a0.paired_differences(left, right)
        self.assertEqual(rows[0]["delta_mae_n"], -3.0)
        with self.assertRaisesRegex(ContractError, "identical task coverage"):
            a0.paired_differences(left, [])


if __name__ == "__main__":
    unittest.main()
