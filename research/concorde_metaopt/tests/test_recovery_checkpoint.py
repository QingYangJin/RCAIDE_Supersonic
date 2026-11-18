"""Untrained NumPy parameter serialization; these tests NEVER execute training."""
from dataclasses import replace
import hashlib
import json
import unittest
import numpy as np

from research.concorde_metaopt.meta_learning import maml
from research.concorde_metaopt.tests.test_recovery_meta_contracts import fixture
from research.concorde_metaopt.dreal001.meta.meta_dataset import MetaDataset, TrainNormalizer
from research.concorde_metaopt.dreal001.meta.task_spec import ContractError
from research.concorde_metaopt.dreal001.meta.production import AdaptationRunner
from research.concorde_metaopt.dreal001.meta.checkpoint import (
    MAX_BYTES, pack_fixture_checkpoint, restore_fixture_checkpoint, training_identity)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.config = maml.MAMLConfig(input_dim=12, output_dim=1, hidden_sizes=(8, 4), seed=17)
        self.norm = TrainNormalizer.fit(self.data)
        self.models = {"fomaml": maml.init_parameters(self.config),
                       "pretrain": maml.init_parameters(self.config, seed=29)}
        self.blob = pack_fixture_checkpoint(dataset=self.data, config=self.config,
                                           normalizer=self.norm, models=self.models)

    def restore(self, blob=None, data=None):
        blob = self.blob if blob is None else blob
        return restore_fixture_checkpoint(blob, expected_sha256=hashlib.sha256(blob).hexdigest(),
                                          dataset=self.data if data is None else data)

    def mutate(self, fn):
        payload = json.loads(self.blob)
        fn(payload)
        return json.dumps(payload).encode()

    def test_roundtrip_exact_parameters_normalizer_and_predictions(self):
        restored = self.restore()
        self.assertFalse(restored.real_admission)
        self.assertFalse(restored.real_meta_training_executed)
        self.assertEqual(restored.config.to_arm_dict(), self.config.to_arm_dict())
        query = np.asarray([r.design for r in self.data.usable("fixture-3", "query")])
        for name in self.models:
            for a, b in zip(self.models[name].tensors, restored.models[name].tensors):
                np.testing.assert_array_equal(a, b)
                self.assertEqual(b.dtype, np.float64)
            original = AdaptationRunner().predict(self.models[name], config=self.config,
                normalizer=self.norm, support_rows=(), query_designs=query)
            reloaded = AdaptationRunner().predict(restored.models[name], config=restored.config,
                normalizer=restored.normalizer, support_rows=(), query_designs=query)
            np.testing.assert_array_equal(original, reloaded)
        self.assertFalse(restored.normalizer.x_mean.flags.writeable)

    def test_deterministic_pack_and_independent_parameter_buffers(self):
        other = pack_fixture_checkpoint(dataset=self.data, config=self.config,
                                        normalizer=self.norm, models=self.models)
        self.assertEqual(other, self.blob)
        a, b = self.restore(), self.restore()
        before = b.models["fomaml"].tensors[0].copy()
        a.models["fomaml"].tensors[0][:] = 99
        np.testing.assert_array_equal(before, b.models["fomaml"].tensors[0])

    def test_external_sha_detects_byte_replacement(self):
        with self.assertRaisesRegex(ContractError, "SHA256 mismatch"):
            restore_fixture_checkpoint(self.blob + b" ",
                expected_sha256=hashlib.sha256(self.blob).hexdigest(), dataset=self.data)

    def test_changed_train_label_or_physical_context_rejected(self):
        rows = (replace(self.data.rows[0], di_n=999.),) + self.data.rows[1:]
        tasks = (replace(self.data.tasks[0], mach=1.9),) + self.data.tasks[1:]
        for data in (MetaDataset(self.data.tasks, rows), MetaDataset(tasks, self.data.rows)):
            with self.assertRaisesRegex(ContractError, "dataset identity"):
                self.restore(data=data)

    def test_heldout_targets_not_in_checkpoint_identity_or_statistics(self):
        rows = tuple(replace(r, di_n=1e30) if r.task_id == "fixture-3" else r for r in self.data.rows)
        altered = MetaDataset(self.data.tasks, rows)
        self.assertEqual(training_identity(altered), training_identity(self.data))
        self.restore(data=altered)

    def test_normalizer_poisoning_rejected_even_with_recomputed_sha(self):
        def poison(p):
            p["normalizer"]["y_mean"] += 1
        with self.assertRaisesRegex(ContractError, "train-only fit"):
            self.restore(self.mutate(poison))

    def test_model_shape_or_names_rejected(self):
        def shape(p):
            p["models"]["fomaml"]["tensors"][0].pop()
        def name(p):
            p["models"]["pretrain"]["names"][0] = "wrong"
        for fn in (shape, name):
            with self.assertRaisesRegex(ContractError, "shape/name"):
                self.restore(self.mutate(fn))

    def test_schema_and_real_claims_rejected(self):
        for key, value in (("real_admission", True), ("real_meta_training_executed", True),
                           ("scope", "REAL_META_TRAINING_EXECUTED"), ("schema", "unknown")):
            with self.assertRaises(ContractError):
                self.restore(self.mutate(lambda p: p.update({key: value})))
        with self.assertRaises(ContractError):
            self.restore(self.mutate(lambda p: p.update({"pickle": "not_allowed"})))

    def test_json_duplicates_nonfinite_truncation_invalid_utf8_rejected(self):
        duplicate = b'{"schema": "x",' + self.blob[1:]
        for blob in (duplicate, b'{"schema":NaN}', self.blob[:-1], b"\xff", b"[]"):
            with self.assertRaises(ContractError):
                self.restore(blob)

    def test_nonfinite_parameter_or_invalid_config_becomes_contract_error(self):
        def parameter(p):
            p["models"]["fomaml"]["tensors"][0][0][0] = float("inf")
        def config(p):
            p["config"]["inner_lr"] = -1.
        for fn in (parameter, config):
            with self.assertRaises(ContractError):
                self.restore(self.mutate(fn))
        # JSON 1e999 is legal syntax but overflows a float; parse_constant alone
        # does not reject it, so parameter validation must do so too.
        payload = self.mutate(parameter).replace(b"Infinity", b"1e999")
        with self.assertRaises(ContractError):
            self.restore(payload)

    def test_missing_model_slot_and_incompatible_config_rejected(self):
        def missing(p):
            del p["models"]["pretrain"]
        def config(p):
            p["config"]["head_only"] = True
        for fn in (missing, config):
            with self.assertRaises(ContractError):
                self.restore(self.mutate(fn))

    def test_real_dataset_cannot_restore_fixture_weights(self):
        raw = MetaDataset(self.data.tasks, tuple(replace(r, source_kind="vspaero_raw") for r in self.data.rows))
        with self.assertRaisesRegex(ContractError, "rejects real"):
            self.restore(data=raw)

    def test_empty_oversize_and_nonbytes_rejected(self):
        for blob in (b"", b"x" * (MAX_BYTES + 1), "not bytes"):
            with self.assertRaises(ContractError):
                self.restore(blob if isinstance(blob, bytes) else blob.encode())
        with self.assertRaises(ContractError):
            restore_fixture_checkpoint("not bytes", expected_sha256="a" * 64, dataset=self.data)


if __name__ == "__main__":
    unittest.main()
