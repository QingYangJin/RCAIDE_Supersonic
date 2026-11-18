"""Zero-physics recovery gates; fixture success is never real training evidence."""
import unittest
from dataclasses import replace
import numpy as np

from research.concorde_metaopt.meta_learning import maml
from research.concorde_metaopt.dreal001.meta.task_spec import (
    ContractError, TaskSpec, validate_task_family,
)
from research.concorde_metaopt.dreal001.meta.meta_dataset import (
    MetaDataset, Observation, TrainNormalizer,
)
from research.concorde_metaopt.dreal001.meta.production import (
    AdaptationRunner, ConditionalAdaptationRunner, ConditionalFeatureSpec,
    ConditionalPretrainer, MetaTrainer, TaskContext, WarmStartSampler,
    conditional_features, context_features,
)
from research.concorde_metaopt.dreal001.meta.validation_training import ValidationPolicy


def fixture():
    tasks = tuple(TaskSpec(f"fixture-{i}", split, mach, 18288., 20483., lift, "a" * 64)
                  for i, (split, mach, lift) in enumerate([
                      ("train", 1.8, 1.2e6), ("train", 2.02, 1.3e6),
                      ("val", 2.2, 1.2e6), ("test", 2.2, 1.3e6)]))
    rows = []
    for tindex, task in enumerate(tasks):
        for index in range(8):
            x = tuple(float(index + j / 12) for j in range(12))
            rows.append(Observation(f"{task.task_id}-{index}", task.task_id, x,
                                    "support" if index < 4 else "query",
                                    "synthetic_fixture", "ok", 100 + index + tindex * 3.))
    return MetaDataset(tasks, tuple(rows))


CONDITIONAL_SPEC = ConditionalFeatureSpec(
    mach_reference=2.02, mach_scale=0.2, q_reference=20483.0,
    cl_reference=0.18, cl_scale=0.01, altitude_reference=18288.0)


def conditional_contexts(data):
    return {task.task_id: TaskContext(0.17 + 0.01 * index)
            for index, task in enumerate(data.tasks)}


class RecoveryContracts(unittest.TestCase):
    def test_physical_identity_ignores_names_and_split(self):
        task = fixture().tasks[0]
        self.assertEqual(task.physics_sha256, replace(task, task_id="renamed", split="test").physics_sha256)

    def test_context_changes_deck_and_constraint(self):
        task = fixture().tasks[0]
        self.assertNotEqual(task.solver_conditions(300)["Mach"], replace(task, mach=2.2).solver_conditions(300)["Mach"])
        self.assertAlmostEqual(task.solver_conditions(300)["CL_target"] / task.solver_conditions(400)["CL_target"], 4/3)

    def test_duplicate_physics_rejected(self):
        data = fixture()
        with self.assertRaisesRegex(ContractError, "duplicate physical"):
            validate_task_family(data.tasks + (replace(data.tasks[0], task_id="clone", split="test"),))

    def test_numeric_representation_cannot_change_physical_identity(self):
        left = TaskSpec("left", "train", 1, 0.0, 1.0, 1.0, "a" * 64)
        compact = TaskSpec("right", "test", 1.0, -0.0, 1.0, 1.0, "a" * 64)
        self.assertEqual(left.physics_sha256, compact.physics_sha256)
        self.assertEqual(left.mach, 1.0)
        self.assertEqual(left.altitude_m, 0.0)

    def test_numeric_clone_rejected_as_duplicate_physics(self):
        tasks = tuple(TaskSpec(f"numeric-{i}", split, mach, 0.0, 1.0, 1.0, "a" * 64)
                      for i, (split, mach) in enumerate([
                          ("train", 1), ("train", 2.0), ("val", 3.0), ("test", 4.0)]))
        clone = replace(tasks[0], task_id="numeric-clone", split="test",
                        mach=float(tasks[0].mach))
        with self.assertRaisesRegex(ContractError, "duplicate physical"):
            validate_task_family(tasks + (clone,))

    def test_need_multiple_train_tasks(self):
        data = fixture()
        with self.assertRaisesRegex(ContractError, "multiple physical"):
            validate_task_family(tuple(t for t in data.tasks if t.task_id != "fixture-1"))

    def test_support_query_design_leakage(self):
        data = fixture()
        row = replace(data.rows[0], observation_id="leak", partition="query")
        with self.assertRaisesRegex(ContractError, "leakage"):
            MetaDataset(data.tasks, data.rows + (row,))

    def test_duplicate_observation_id(self):
        data = fixture()
        with self.assertRaisesRegex(ContractError, "duplicate observation"):
            MetaDataset(data.tasks, data.rows + (data.rows[0],))

    def test_failed_objective_must_be_null(self):
        with self.assertRaisesRegex(ContractError, "must be null"):
            replace(fixture().rows[0], status="failed")

    def test_failed_observation_rejects_coefficient_labels(self):
        with self.assertRaisesRegex(ContractError, "coefficient"):
            replace(fixture().rows[0], status="failed", di_n=None, cl=0.17)

    def test_nonfinite_objective_rejected(self):
        with self.assertRaises(ContractError):
            replace(fixture().rows[0], di_n=float("nan"))

    def test_fuel_remains_null(self):
        with self.assertRaisesRegex(ContractError, "fuel_burn"):
            replace(fixture().rows[0], fuel_burn_kg=10.)

    def test_unknown_task_rejected(self):
        data = fixture()
        with self.assertRaisesRegex(ContractError, "unknown task"):
            MetaDataset(data.tasks, (replace(data.rows[0], task_id="missing"),))

    def test_source_mixing_rejected(self):
        data = fixture()
        rows = (replace(data.rows[0], source_kind="vspaero_raw"),) + data.rows[1:]
        with self.assertRaisesRegex(ContractError, "never mix"):
            MetaDataset(data.tasks, rows)

    def test_declared_raw_cannot_self_admit(self):
        data = fixture()
        raw = MetaDataset(data.tasks, tuple(replace(r, source_kind="vspaero_raw", raw_sha256="b"*64) for r in data.rows))
        with self.assertRaisesRegex(ContractError, "REAL_ADMISSION_NOT_IMPLEMENTED"):
            MetaTrainer().fit(raw, config=None, max_steps=10)
        with self.assertRaisesRegex(ContractError, "rejects real"):
            MetaTrainer().fit(raw, config=None, max_steps=10, mode="software_fixture")

    def test_default_real_gate_precedes_backend(self):
        with self.assertRaisesRegex(ContractError, "REAL_ADMISSION_NOT_IMPLEMENTED"):
            MetaTrainer().fit(fixture(), config=None, max_steps=10)

    def test_normalization_train_only(self):
        data = fixture()
        norm = TrainNormalizer.fit(data)
        altered = MetaDataset(data.tasks, tuple(replace(r, di_n=1e30) if r.task_id == "fixture-3" else r for r in data.rows))
        other = TrainNormalizer.fit(altered)
        self.assertEqual(norm.y_mean, other.y_mean)
        self.assertTrue(all(name.startswith(("fixture-0-", "fixture-1-")) for name in norm.fit_observation_ids))
        self.assertEqual(norm.x_mean.dtype, np.float64)

    def test_warm_start_selects_unique_not_fake_labels(self):
        x = np.array([[0.]*12, [0.]*12, [1.]*12, [2.]*12])
        selected = WarmStartSampler().select(x, np.array([2., 1., 0., 3.]), 2)
        np.testing.assert_array_equal(selected, np.array([[1.]*12, [0.]*12]))

    def test_insufficient_unique_candidates_fail(self):
        with self.assertRaisesRegex(ContractError, "not enough unique"):
            WarmStartSampler().select(np.zeros((3,12)), np.ones(3), 2)

    def test_nonfinite_candidates_fail(self):
        with self.assertRaises(ContractError):
            WarmStartSampler().select(np.full((2,12), np.nan), np.ones(2), 1)

    @unittest.skipUnless(maml.torch_available(), "TORCH_NOT_AVAILABLE: training NOT_RUN")
    def test_fixture_training_and_support_only_adaptation(self):
        data = fixture()
        config = maml.MAMLConfig(input_dim=12, output_dim=1, hidden_sizes=(8,8),
                                 inner_steps=2, tasks_per_batch=2, seed=17)
        result = MetaTrainer().fit(data, config=config, max_steps=3, mode="software_fixture")
        self.assertFalse(result["real_meta_training_executed"])
        self.assertEqual(result["fomaml"]["steps"], 3)
        params = maml.ParameterSet.from_dict(result["fomaml"]["final_parameters"])
        query = np.asarray([r.design for r in data.usable("fixture-3", "query")])
        pred = AdaptationRunner().predict(params, config=config, normalizer=result["normalizer"],
                                          support_rows=data.usable("fixture-3", "support"),
                                          query_designs=query)
        self.assertEqual(pred.shape, (4,))
        self.assertTrue(np.isfinite(pred).all())
        self.assertEqual(len(result["pretrain"]["history"]), 3)

    def test_bad_geometry_sha_rejected(self):
        with self.assertRaisesRegex(ContractError, "SHA256"):
            replace(fixture().tasks[0], geometry_contract_sha256="report says pass")


    def test_conditional_features_append_four_context_dims(self):
        data = fixture()
        normalizer = TrainNormalizer.fit(data)
        task = data.tasks[0]
        context = TaskContext(0.19)
        vector = context_features(task, context, CONDITIONAL_SPEC)
        designs = np.asarray([r.design for r in data.usable(task.task_id, "support")])
        features = conditional_features(designs, normalizer, vector)
        self.assertEqual(features.shape, (4, 16))
        np.testing.assert_allclose(features[:, 12:], np.broadcast_to(vector, (4, 4)))
        np.testing.assert_allclose(features[:, :12], (designs - normalizer.x_mean) / normalizer.x_scale)

    def test_conditional_real_gate_precedes_backend(self):
        data = fixture()
        with self.assertRaisesRegex(ContractError, "REAL_ADMISSION"):
            ConditionalPretrainer().fit(
                data, config=None, contexts=conditional_contexts(data),
                feature_spec=CONDITIONAL_SPEC)

    def test_conditional_requires_16d_and_complete_contexts(self):
        data = fixture()
        config12 = maml.MAMLConfig(input_dim=12, output_dim=1, hidden_sizes=(8, 8),
                                   inner_steps=2, tasks_per_batch=2, seed=17)
        with self.assertRaisesRegex(ContractError, "16D"):
            ConditionalPretrainer().fit(
                data, config=config12, contexts=conditional_contexts(data),
                feature_spec=CONDITIONAL_SPEC, mode="software_fixture")
        config16 = maml.MAMLConfig(input_dim=16, output_dim=1, hidden_sizes=(8, 8),
                                   inner_steps=2, tasks_per_batch=2, seed=17)
        contexts = conditional_contexts(data)
        del contexts[data.tasks[0].task_id]
        with self.assertRaisesRegex(ContractError, "missing task context"):
            ConditionalPretrainer().fit(
                data, config=config16, contexts=contexts,
                feature_spec=CONDITIONAL_SPEC, mode="software_fixture")

    @unittest.skipUnless(maml.torch_available(), "TORCH_NOT_AVAILABLE: training NOT_RUN")
    def test_conditional_pretraining_and_adaptation(self):
        data = fixture()
        config = maml.MAMLConfig(input_dim=16, output_dim=1, hidden_sizes=(8, 8),
                                 inner_steps=2, tasks_per_batch=2, seed=17)
        contexts = conditional_contexts(data)
        result = ConditionalPretrainer().fit(
            data, config=config, contexts=contexts, feature_spec=CONDITIONAL_SPEC,
            policy=ValidationPolicy(max_steps=4, interval=2, patience=2),
            mode="software_fixture")
        self.assertEqual(result["scope"], "SOFTWARE_FIXTURE_CONDITIONAL_ONLY")
        self.assertFalse(result["real_meta_training_executed"])
        self.assertEqual(result["physical_solver_starts_actual"], 0)
        self.assertEqual(result["admitted_real_labels"], 0)
        self.assertFalse(result["test_used_for_selection"])
        self.assertGreaterEqual(result["report"]["steps_executed"], 1)
        self.assertEqual(len(result["feature_spec"]), len(CONDITIONAL_SPEC.__dataclass_fields__))
        task = data.tasks[3]
        query = np.asarray([r.design for r in data.usable(task.task_id, "query")])
        prediction = ConditionalAdaptationRunner().predict(
            result["parameters"], config=config, normalizer=result["normalizer"],
            support_rows=data.usable(task.task_id, "support"), query_designs=query,
            task=task, context=contexts[task.task_id], feature_spec=CONDITIONAL_SPEC)
        self.assertEqual(prediction.shape, (4,))
        self.assertTrue(np.isfinite(prediction).all())

    def test_conditional_adaptation_rejects_support_query_leakage(self):
        data = fixture()
        task = data.tasks[3]
        support = data.usable(task.task_id, "support")
        config = maml.MAMLConfig(input_dim=16, output_dim=1)
        with self.assertRaisesRegex(ContractError, "leakage"):
            ConditionalAdaptationRunner().predict(
                None, config=config, normalizer=TrainNormalizer.fit(data),
                support_rows=support,
                query_designs=np.asarray([support[0].design]), task=task,
                context=conditional_contexts(data)[task.task_id],
                feature_spec=CONDITIONAL_SPEC)

if __name__ == "__main__":
    unittest.main()
