"""Offline M2 rehearsal tests: synthetic labels only, zero physical solver starts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import unittest

import numpy as np

from research.concorde_metaopt.dreal001.meta import m2_rehearsal as rehearsal
from research.concorde_metaopt.dreal001.meta.meta_dataset import MetaDataset, Observation
from research.concorde_metaopt.dreal001.meta.task_spec import ContractError, canonical_sha
from research.concorde_metaopt.dreal001.meta.validation_training import ValidationPolicy
from research.concorde_metaopt.dreal001.m1.task_evaluator import (
    SREF_REF_FROZEN,
    TASK_DEFINITIONS,
    SpawnGuard,
    build_task_spec,
)

ROOT = Path(__file__).resolve().parents[3]
SMALL_POLICY = ValidationPolicy(max_steps=6, interval=3, patience=2)


class RehearsalDatasetTests(unittest.TestCase):
    def test_frozen_tasks_keep_their_declared_splits(self):
        tasks, definitions = rehearsal.build_rehearsal_tasks()
        self.assertEqual(len(tasks), 6)
        expected = {definition.task_id: definition.split for definition in TASK_DEFINITIONS}
        self.assertEqual({task.task_id: task.split for task in tasks},
                         {"T18K_M202_CL017": "train", "T18K_M202_CL019": "train",
                          "T18K_M220_CL017": "train", "T18K_M220_CL019": "val",
                          "T18K_M180_CL017": "test", "T18K_M180_CL019": "test"})
        for task in tasks:
            definition = definitions[task.task_id]
            self.assertIn(task.split, ("train", "val", "test"))
            self.assertEqual(definition.split, "meta_" + task.split)
            self.assertEqual(task.mach, definition.mach)
            self.assertEqual(task.lift_tolerance_rel, 1e-3)
            expected_split = {"meta_train": "train", "meta_val": "val", "meta_test": "test"}[definition.split]
            self.assertEqual(task.split, expected_split)
            self.assertEqual(task.task_id, definition.task_id)
            self.assertEqual(len(task.geometry_contract_sha256), 64)
            self.assertTrue(all(character in "0123456789abcdef" for character in task.geometry_contract_sha256))
            self.assertIn(task.task_id, expected)

    def test_task_physics_matches_frozen_f1r2_task_spec(self):
        tasks, definitions = rehearsal.build_rehearsal_tasks()
        for task in tasks:
            spec = build_task_spec(definitions[task.task_id], SREF_REF_FROZEN)
            self.assertEqual(task.mach, spec["task_definition"]["mach"])
            self.assertAlmostEqual(task.dynamic_pressure_pa, spec["q_pa"], places=9)
            self.assertAlmostEqual(task.lift_target_n, spec["l_ref_n"], places=6)
            self.assertAlmostEqual(task.altitude_m, spec["atmosphere"]["altitude_m"], places=6)
            self.assertEqual(spec["sref_ref_m2"], SREF_REF_FROZEN)

    def test_dataset_is_fixture_only_and_support_query_disjoint(self):
        dataset, definitions, manifest = rehearsal.build_rehearsal_dataset()
        self.assertIsInstance(dataset, MetaDataset)
        self.assertEqual(len(dataset.rows), 96)
        self.assertEqual(manifest["observations_per_task"], 16)
        self.assertEqual(manifest["support_rows"], 10)
        self.assertEqual(manifest["query_rows"], 6)
        for task in dataset.tasks:
            support = dataset.usable(task.task_id, "support")
            query = dataset.usable(task.task_id, "query")
            self.assertEqual(len(support), 10)
            self.assertEqual(len(query), 6)
            self.assertEqual({row.source_kind for row in support + query}, {"synthetic_fixture"})
            self.assertEqual({row.status for row in support + query}, {"ok"})
            support_designs = {row.design_sha256 for row in support}
            query_designs = {row.design_sha256 for row in query}
            self.assertFalse(support_designs & query_designs)
        self.assertEqual(len(dataset.rows), 6 * (10 + 6))
        with self.assertRaises(ContractError) as caught:
            dataset.require_real_admission()
        self.assertIn("REAL_ADMISSION_NOT_IMPLEMENTED", str(caught.exception))

    def test_manifest_and_rows_are_reproducible(self):
        first = rehearsal.build_rehearsal_dataset()
        second = rehearsal.build_rehearsal_dataset()
        self.assertEqual(canonical_sha(dict(first[2])), canonical_sha(dict(second[2])))
        self.assertEqual([row.observation_id for row in first[0].rows],
                         [row.observation_id for row in second[0].rows])
        np.testing.assert_array_equal(first[0].rows[0].di_n, second[0].rows[0].di_n)

    def test_rejects_task_family_without_blind_test_tasks(self):
        tasks, definitions = rehearsal.build_rehearsal_tasks()
        with self.assertRaises(ContractError):
            rehearsal.build_rehearsal_dataset(tasks=[task for task in tasks if task.split != "test"])

    def test_rejects_mixed_source_kinds(self):
        dataset, definitions, manifest = rehearsal.build_rehearsal_dataset()
        rows = list(dataset.rows)
        raw = Observation(
            observation_id="raw-fixture", task_id=rows[0].task_id, design=rows[0].design,
            partition="support", source_kind="vspaero_raw", status="ok",
            di_n=rows[0].di_n, q_pa=rows[0].q_pa, sref_m2=rows[0].sref_m2,
            cdi=rows[0].cdi, cl=rows[0].cl, raw_sha256="0" * 64,
        )
        with self.assertRaises(ContractError):
            MetaDataset(tasks=dataset.tasks, rows=rows[:1] + [raw])


class RehearsalReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks, cls.definitions = rehearsal.build_rehearsal_tasks()
        cls.dataset, cls.definitions, cls.manifest = rehearsal.build_rehearsal_dataset(cls.tasks)
        cls.receipt, cls.checkpoint = rehearsal.run_rehearsal(
            policy=SMALL_POLICY, seed=42, run_id="TEST-M2-REHEARSAL-FIXED")

    def test_receipt_declares_offline_rehearsal_and_zero_physical(self):
        receipt = self.receipt
        self.assertEqual(receipt["scope"], "OFFLINE_REHEARSAL_ONLY")
        self.assertEqual(receipt["evidence_grade"], "OFFLINE_REHEARSAL_NO_PHYSICAL_EVIDENCE")
        self.assertIs(receipt["real_admission"], False)
        self.assertIs(receipt["real_meta_training_executed"], False)
        self.assertEqual(receipt["admitted_real_labels"], 0)
        self.assertEqual(receipt["physical_solver_starts_actual"], 0)
        self.assertEqual(receipt["internal_solver_cases_actual"], 0)
        self.assertEqual(receipt["labels"]["kind"], "synthetic_fixture")
        self.assertIn("NOT A PHYSICAL MODEL", receipt["labels"]["note"].upper())

    def test_receipt_contains_k_shot_scores_and_scoring_baseline(self):
        evaluation = self.receipt["evaluation"]
        for k_shot in (0, 4, 10):
            block = evaluation["k%d" % k_shot]
            self.assertEqual(set(block),
                             {"fomaml", "pretrain", "conditional_pretrain", "random_init",
                              "constant_train_mean"})
            for name, entry in block.items():
                self.assertGreaterEqual(entry["macro"]["mse_normalized"], 0.0)
                self.assertTrue(np.isfinite(entry["macro"]["mse_di_n2"]))
                self.assertEqual(len(entry["per_task"]), 2)
        baseline = {k: evaluation[k]["constant_train_mean"]["macro"]["mse_normalized"]
                    for k in ("k0", "k4", "k10")}
        self.assertAlmostEqual(baseline["k0"], baseline["k10"], places=12)
        self.assertEqual(len(evaluation["test_task_diagnostics"]), 2)
        for task_id, diagnostic in evaluation["test_task_diagnostics"].items():
            self.assertIn(task_id, evaluation["test_task_ids"])
            self.assertLess(diagnostic["query_mean_shift_normalized_from_train_mean"], 0.0)

    def test_receipt_verdict_is_honest_about_gated_real_maml(self):
        verdict = self.receipt["verdict"]
        self.assertEqual(verdict["status"], "REHEARSAL_COMPLETE_NOT_REAL_EVIDENCE")
        self.assertIs(verdict["ood_blind_test_gap_expected"], True)
        self.assertEqual(verdict["meta_learning_gain_claim"], "NO_META_LEARNING_GAIN_CLAIM")
        self.assertEqual(verdict["blocking_gates_before_real_maml"], [
            "R0_A5_INDEPENDENT_REVIEW",
            "RESTORED_CODE_BASELINE_PASS",
            "BACKUP_RESTORE_PASS_INDEPENDENT_FAILURE_DOMAIN",
            "REAL_ADMISSION_IMPLEMENTED_AND_RAW_VERIFIED",
            "NEW_R2_GATE_AND_LEAD_BATCH_GO",
        ])
        self.assertIn("mse_normalized_by_k_shot", verdict)
        self.assertEqual(set(verdict["mse_normalized_by_k_shot"]),
                         {"fomaml", "pretrain", "conditional_pretrain", "random_init"})

    def test_validation_uses_only_val_tasks_and_never_blind_test(self):
        training = self.receipt["training"]
        self.assertEqual(training["validation_task_ids"], ["T18K_M220_CL019"])
        self.assertIs(training["test_used_for_selection"], False)
        self.assertEqual(training["fixture_scope"], "SOFTWARE_FIXTURE_VALIDATION_ONLY")
        self.assertIn("NOT_FORMAL", training["pretraining_kind"])

    def test_checkpoint_sha_matches_payload_bytes(self):
        blob = json.dumps(self.checkpoint, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
        self.assertEqual(hashlib.sha256(blob).hexdigest(), self.receipt["sha256"]["checkpoint"])
        self.assertEqual(self.checkpoint["dataset_manifest_sha256"],
                         self.receipt["sha256"]["dataset_manifest"])
        self.assertIs(self.checkpoint["real_meta_training_executed"], False)

    def test_code_and_geometry_contract_hashes_are_verifiable(self):
        shas = rehearsal.source_shas()
        self.assertEqual(len(shas), 9)
        for name, digest in shas.items():
            self.assertEqual(len(digest), 64, name)
        self.assertEqual(self.receipt["sha256"]["code"], canonical_sha(shas))
        contract = rehearsal.geometry_contract()
        self.assertEqual(contract["schema"], "drecover001.geometry_contract.v1")
        self.assertEqual(contract["origin"], "REGENERATED_FROM_SPEC")
        self.assertEqual(contract["sref_ref_m2"], SREF_REF_FROZEN)
        self.assertEqual(contract["active_mask"], "12D_ALL_ACTIVE")
        self.assertEqual(self.receipt["sha256"]["geometry_contract"], canonical_sha(contract))
        self.assertEqual(self.receipt["geometry_contract"]["design_space_sha256"],
                         shas["research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"])

    def test_rehearsal_is_deterministic_for_a_fixed_seed(self):
        policy = ValidationPolicy(max_steps=4, interval=2, patience=1)
        first, _ = rehearsal.run_rehearsal(policy=policy, seed=7, run_id="TEST-M2-DETERMINISM")
        second, _ = rehearsal.run_rehearsal(policy=policy, seed=7, run_id="TEST-M2-DETERMINISM")
        self.assertEqual(first["checkpoint_parameters_sha256"],
                         second["checkpoint_parameters_sha256"])
        self.assertEqual(first["sha256"], second["sha256"])

    def test_spawn_guard_blocks_any_child_process_during_rehearsal(self):
        guard = SpawnGuard().install()
        try:
            receipt, checkpoint = rehearsal.run_rehearsal(
                policy=ValidationPolicy(max_steps=4, interval=2, patience=1), seed=11,
                run_id="TEST-M2-SPAWN-GUARD")
        finally:
            guard.uninstall()
        self.assertEqual(guard.attempts, [])
        self.assertEqual(receipt["physical_solver_starts_actual"], 0)
        self.assertIs(checkpoint["real_admission"], False)


class RehearsalArtifactTests(unittest.TestCase):
    def test_write_artifacts_roundtrip_and_tamper_rejection(self):
        scratch = ROOT / "tmp_m2_artifacts_test"
        if scratch.exists():
            shutil.rmtree(scratch)
        scratch.mkdir()
        try:
            receipt, checkpoint = rehearsal.run_rehearsal(
                policy=SMALL_POLICY, seed=3, run_id="TEST-M2-ARTIFACTS")
            receipt_path, checkpoint_path = rehearsal.write_artifacts(
                receipt, checkpoint, receipt_path=scratch / "receipt.json",
                checkpoint_path=scratch / "checkpoint.json")
            written = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(written["sha256"]["checkpoint"], receipt["sha256"]["checkpoint"])
            checkpoint_text = checkpoint_path.read_text(encoding="utf-8").rstrip("\n")
            self.assertEqual(hashlib.sha256(checkpoint_text.encode("utf-8")).hexdigest(),
                             receipt["sha256"]["checkpoint"])
            tampered = json.loads(json.dumps(checkpoint))
            tampered["dataset_manifest_sha256"] = "0" * 64
            with self.assertRaises(ContractError):
                rehearsal.write_artifacts(receipt, tampered,
                                          receipt_path=scratch / "bad_receipt.json",
                                          checkpoint_path=scratch / "bad_checkpoint.json")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
