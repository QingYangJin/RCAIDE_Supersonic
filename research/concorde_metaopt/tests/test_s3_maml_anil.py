"""S3 ANIL / 梯度门单测（A1 写域；零物理调用、零求解器）。"""
from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research.concorde_metaopt.meta_learning import maml
from research.concorde_metaopt.meta_learning import s3_prereg as sp


def _config(**overrides):
    payload = dict(
        input_dim=12,
        output_dim=3,
        hidden_sizes=(8, 8),
        inner_lr=0.01,
        inner_steps=2,
        outer_lr=1e-3,
        tasks_per_batch=4,
        first_order=True,
        seed=7,
        backend="torch",
    )
    payload.update(overrides)
    return maml.MAMLConfig(**payload)


def _episode(rng, support_size=5, query_size=7, task_id="t"):
    return maml.TaskEpisode(
        support_features=rng.normal(size=(support_size, 12)),
        support_targets=rng.normal(size=(support_size, 3)),
        query_features=rng.normal(size=(query_size, 12)),
        query_targets=rng.normal(size=(query_size, 3)),
        task_id=task_id,
    )


def _episodes(count=4, seed=0):
    rng = np.random.default_rng(seed)
    return [_episode(rng, task_id="t" + str(index)) for index in range(count)]


class AnilConfigTests(unittest.TestCase):
    def test_01_head_only_default_and_serialization(self):
        config = _config()
        self.assertFalse(config.head_only)
        self.assertEqual(set(config.to_dict()), set(sp.S3_MODEL_CONFIG_FIELDS) - {"head_only"})
        self.assertEqual(set(config.to_arm_dict()), set(sp.S3_MODEL_CONFIG_FIELDS))
        self.assertTrue(config.to_arm_dict()["head_only"] is False)
        restored = maml.config_from_dict(config.to_dict())
        self.assertFalse(restored.head_only)
        payload = config.to_arm_dict()
        payload["head_only"] = True
        anil = maml.config_from_dict(payload)
        self.assertTrue(anil.head_only)
        self.assertEqual(anil.to_dict(), config.to_dict())

    def test_02_head_only_requires_first_order(self):
        with self.assertRaises(maml.MAMLError):
            _config(head_only=True, first_order=False)
        with self.assertRaises(maml.MAMLError):
            _config(head_only="yes")


class AnilInnerLoopTests(unittest.TestCase):
    def test_01_anil_inner_freezes_body(self):
        config = _config(head_only=True)
        initial = maml.init_parameters(config)
        adapted, losses = maml.inner_adapt_anil(initial, _episode(np.random.default_rng(1)), config)
        self.assertEqual(len(losses), config.inner_steps)
        self.assertTrue(all(math.isfinite(value) for value in losses))
        head = maml._head_tensor_indices(initial)
        for index, (before, after) in enumerate(zip(initial.tensors, adapted.tensors)):
            if index in head:
                self.assertFalse(np.array_equal(before, after), "head 参数未更新: " + str(index))
            else:
                self.assertTrue(np.array_equal(before, after), "body 参数被更新: " + str(index))

    def test_02_anil_inner_requires_head_only(self):
        config = _config()
        initial = maml.init_parameters(config)
        with self.assertRaises(maml.MAMLError):
            maml.inner_adapt_anil(initial, _episode(np.random.default_rng(2)), config)

    def test_03_inner_adapt_still_updates_all(self):
        config = _config()
        initial = maml.init_parameters(config)
        adapted, losses = maml.inner_adapt(initial, _episode(np.random.default_rng(3)), config)
        self.assertEqual(len(losses), config.inner_steps)
        changed = [not np.array_equal(before, after) for before, after in zip(initial.tensors, adapted.tensors)]
        self.assertTrue(any(changed))


class AnilMetaStepTests(unittest.TestCase):
    def test_01_anil_meta_step_updates_all_parameters(self):
        config = _config(head_only=True)
        initial = maml.init_parameters(config)
        updated, stats = maml.meta_train_step(initial, _episodes(4, 11), config)
        self.assertEqual(set(stats), {"outer_loss", "grad_norm", "inner_loss_first", "inner_loss_last"})
        self.assertTrue(all(math.isfinite(value) for value in stats.values()))
        changed = [not np.array_equal(before, after) for before, after in zip(initial.tensors, updated.tensors)]
        self.assertTrue(all(changed), "ANIL 外循环应更新全部参数")

    def test_02_anil_rejects_second_order(self):
        config = _config(head_only=True)
        initial = maml.init_parameters(config)
        with self.assertRaises(maml.MAMLError):
            maml.meta_train_step(initial, _episodes(2, 12), config, second_order=True)

    def test_03_fomaml_step_keys_and_finite(self):
        config = _config()
        initial = maml.init_parameters(config)
        updated, stats = maml.meta_train_step(initial, _episodes(2, 13), config)
        self.assertEqual(len(updated.tensors), len(initial.tensors))
        self.assertTrue(all(math.isfinite(value) for value in stats.values()))


class GradientGateTests(unittest.TestCase):
    def test_01_coordinate_plan(self):
        config = _config()
        initial = maml.init_parameters(config)
        plan = maml.s3_gate_coordinate_plan(initial, max_coordinates=8)
        self.assertEqual(plan["requested"], 8)
        self.assertGreaterEqual(plan["available"], 8)
        selected = [(entry["tensor_index"], entry["flat_index"]) for entry in plan["selected"]]
        self.assertEqual(len(selected), 8)
        self.assertEqual(len(set(selected)), 8)
        again = maml.s3_gate_coordinate_plan(initial, max_coordinates=8)
        again_selected = [(entry["tensor_index"], entry["flat_index"]) for entry in again["selected"]]
        self.assertEqual(selected, again_selected)
        with self.assertRaises(maml.MAMLError):
            maml.s3_gate_coordinate_plan(initial, max_coordinates=10**6)

    def test_02_fomaml_gate_pass(self):
        config = _config()
        initial = maml.init_parameters(config)
        payload = maml.s3_gradient_gate(initial, _episodes(4, 21), config, mode="fomaml", max_coordinates=8)
        self.assertEqual(payload["schema_version"], maml.S3_GATE_SCHEMA_VERSION)
        self.assertEqual(payload["mode"], "fomaml")
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["n_checked"], 8)
        self.assertEqual(len(payload["checks"]), 8)
        self.assertLessEqual(payload["max_relative_error"], sp.S3_FD_TOLERANCE)
        self.assertTrue(all(check["status"] == "PASS" for check in payload["checks"]))
        self.assertEqual(payload["fd_point"], "adapted_parameters")

    def test_03_anil_gate_pass_and_body_frozen(self):
        config = _config(head_only=True)
        initial = maml.init_parameters(config)
        payload = maml.s3_gradient_gate(initial, _episodes(4, 22), config, mode="anil", max_coordinates=8)
        self.assertEqual(payload["mode"], "anil")
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["anil_body_frozen"])
        self.assertEqual(payload["n_checked"], 8)
        self.assertLessEqual(payload["max_relative_error"], sp.S3_FD_TOLERANCE)

    def test_04_mode_pairing(self):
        normal = maml.init_parameters(_config())
        anil_config = _config(head_only=True)
        anil = maml.init_parameters(anil_config)
        with self.assertRaises(maml.MAMLError):
            maml.s3_gradient_gate(anil, _episodes(2, 23), anil_config, mode="fomaml", max_coordinates=4)
        with self.assertRaises(maml.MAMLError):
            maml.s3_gradient_gate(normal, _episodes(2, 24), _config(), mode="anil", max_coordinates=4)

    def test_05_fail_closed_tolerance(self):
        config = _config()
        initial = maml.init_parameters(config)
        with self.assertRaises(maml.MAMLError) as raised:
            maml.s3_gradient_gate(initial, _episodes(4, 25), config, mode="fomaml", max_coordinates=8, tolerance=1e-13)
        self.assertIn(maml.S3_GATE_FD_FAIL, str(raised.exception))

    def test_06_k0_equivalence(self):
        config = _config(inner_steps=0)
        initial = maml.init_parameters(config)
        payload = maml.s3_gradient_gate(initial, _episodes(4, 26), config, mode="fomaml", max_coordinates=8)
        self.assertTrue(payload["k0_equivalence"])
        self.assertEqual(payload["status"], "PASS")

    def test_07_tamper_detection(self):
        config = _config()
        initial = maml.init_parameters(config)
        payload = maml.s3_gradient_gate(initial, _episodes(4, 27), config, mode="fomaml", max_coordinates=8)
        tampered = json.loads(json.dumps(payload))
        tampered["checks"][0]["relative_error"] = 1.0
        with self.assertRaises(maml.MAMLError) as raised:
            maml.assert_s3_gate_consistent(tampered)
        self.assertIn(maml.S3_GATE_TAMPER_DETECTED, str(raised.exception))
        broken = json.loads(json.dumps(payload))
        broken["status"] = "FAIL"
        with self.assertRaises(maml.MAMLError):
            maml.assert_s3_gate_consistent(broken)

    def test_08_write_gate_result_sha(self):
        config = _config()
        initial = maml.init_parameters(config)
        payload = maml.s3_gradient_gate(initial, _episodes(4, 28), config, mode="fomaml", max_coordinates=8)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate.json"
            sha = maml.write_s3_gate_result(payload, path)
            data = path.read_bytes()
            self.assertTrue(data.endswith(b"\n"))
            self.assertEqual(sha, hashlib.sha256(data).hexdigest())
            self.assertEqual(maml.s3_gate_sha256(payload), sp.canonical_sha256(payload))
            self.assertTrue(maml.assert_s3_gate_consistent(json.loads(data.decode("utf-8"))))


if __name__ == "__main__":
    unittest.main()
