"""Guard + mechanics tests for the four P2 arms (synthetic bytes only)."""
import unittest

from research.concorde_metaopt.dreal001.meta.meta_dataset import (
    MetaDataset, Observation, TrainNormalizer)
from research.concorde_metaopt.dreal001.meta.real_p2_arms import (
    ARM_NAMES, ArmConfig, require_k, run_arms)
from research.concorde_metaopt.dreal001.meta.task_spec import ContractError, TaskSpec

GEOM = "c" * 64


def _task(task_id, split, q, lift):
    return TaskSpec(task_id, split, 2.0, 18288.0, q, lift, GEOM)


def _rows(task_id, source_kind="synthetic_fixture", base=100.0):
    rows = []
    for index in range(4):
        design = [0.0] * 12
        design[index] = float(index + 1)
        rows.append(Observation("obs-%s-s%d" % (task_id, index), task_id,
                                tuple(design), "support", source_kind, "ok",
                                base + 10.0 * index))
    design = [0.0] * 12
    design[0] = 0.5
    rows.append(Observation("obs-%s-q0" % task_id, task_id, tuple(design),
                            "query", source_kind, "ok", base + 4.0))
    return rows


def fixture():
    tasks = (_task("TRAIN-A", "train", 20000.0, 1000000.0),
             _task("TRAIN-B", "train", 21000.0, 1000000.0),
             _task("VAL-A", "val", 22000.0, 1000000.0),
             _task("TEST-A", "test", 23000.0, 1000000.0))
    rows = []
    for index, task in enumerate(tasks):
        rows.extend(_rows(task.task_id, base=100.0 + 300.0 * index))
    return MetaDataset(tasks, tuple(rows))


class RealP2ArmsTests(unittest.TestCase):
    def test_k_policy_is_fail_closed(self):
        require_k(1)
        require_k(3)
        with self.assertRaisesRegex(ContractError, "K=5 NOT_ELIGIBLE"):
            require_k(5)
        with self.assertRaisesRegex(ContractError, "K=1 and K=3"):
            require_k(2)

    def test_four_arms_run_on_fixture_and_score_heldout_only(self):
        dataset = fixture()
        config = ArmConfig(hidden_sizes=(8,), max_steps=3, seed=19)
        result = run_arms(dataset, config=config, k=1, mode="software_fixture")
        self.assertEqual(result["scope"], "SOFTWARE_FIXTURE_TRAINING_ONLY")
        self.assertEqual(result["arms"], list(ARM_NAMES))
        for name in ARM_NAMES:
            tasks = {row["task_id"] for row in result["scores"][name]}
            self.assertEqual(tasks, {"VAL-A", "TEST-A"})
            for row in result["scores"][name]:
                self.assertEqual(row["n_query"], 1)
                self.assertGreaterEqual(row["mae_n"], 0.0)
        # Train-only normalization: no validation/test observation may leak in.
        fitted = set(result["normalizer"].fit_observation_ids)
        train_ids = {r.observation_id for r in dataset.rows
                     if r.task_id in {"TRAIN-A", "TRAIN-B"}}
        self.assertEqual(fitted, train_ids)
        self.assertFalse(any("VAL" in i or "TEST" in i for i in fitted))
        self.assertFalse(result["attention"]["test_used_for_selection"])

    def test_real_mode_without_admissions_still_fails_closed(self):
        tasks = fixture().tasks
        rows = []
        for index, task in enumerate(tasks):
            rows.extend(_rows(task.task_id, source_kind="vspaero_raw",
                              base=100.0 + 300.0 * index))
        dataset = MetaDataset(tasks, tuple(rows))
        with self.assertRaisesRegex(ContractError, "REAL_ADMISSION_NOT_IMPLEMENTED"):
            run_arms(dataset, config=ArmConfig(hidden_sizes=(8,), max_steps=1, seed=7),
                     k=1, mode="real")

    def test_targets_are_never_reused_as_support(self):
        dataset = fixture()
        config = ArmConfig(hidden_sizes=(8,), max_steps=2, seed=43)
        result = run_arms(dataset, config=config, k=3, mode="software_fixture")
        for name in ARM_NAMES:
            for row in result["scores"][name]:
                self.assertEqual(len(row["support_observation_ids"]), 3)
                self.assertFalse(set(row["support_observation_ids"])
                                 & set(row["query_observation_ids"]))


if __name__ == "__main__":
    unittest.main()
