"""New zero-physics verification receipt. Missing torch is NOT_RUN, never PASS."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import platform
import time
import numpy as np
import sys
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.concorde_metaopt.tests import test_recovery_meta_contracts as tests
from research.concorde_metaopt.tests import test_openvsp_geometry as geometry_tests
from research.concorde_metaopt.tests import test_recovery_feedback as feedback_tests
from research.concorde_metaopt.tests import test_recovery_bo as bo_tests
from research.concorde_metaopt.tests import test_recovery_population as population_tests
from research.concorde_metaopt.tests import test_recovery_raw_verification as raw_tests
from research.concorde_metaopt.tests import test_recovery_adaptation_guards as adaptation_tests
from research.concorde_metaopt.tests import test_recovery_geometry_effects as effect_tests
from research.concorde_metaopt.tests import test_recovery_task_deck as deck_tests
from research.concorde_metaopt.tests import test_recovery_checkpoint as checkpoint_tests
from research.concorde_metaopt.tests import test_recovery_ledger as ledger_tests
from research.concorde_metaopt.tests import test_recovery_m2_rehearsal as rehearsal_tests
from research.concorde_metaopt.tests import test_recovery_path_injection as path_tests
from research.concorde_metaopt.tests import test_recovery_m1_batch as batch_tests
from research.concorde_metaopt.tests import test_recovery_readiness as readiness_tests
from research.concorde_metaopt.dreal001.meta.checkpoint import pack_fixture_checkpoint, restore_fixture_checkpoint
from research.concorde_metaopt.meta_learning import maml
from research.concorde_metaopt.dreal001.meta.production import MetaTrainer


def main():
    out = Path(__file__).resolve().parent
    stream = io.StringIO()
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(module)
                                for module in (tests, geometry_tests, feedback_tests, bo_tests, population_tests, raw_tests, adaptation_tests, effect_tests, deck_tests, checkpoint_tests, ledger_tests, rehearsal_tests, path_tests, batch_tests, readiness_tests)])
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (out / "recovery_meta_contract_tests.txt").write_text(stream.getvalue(), encoding="utf-8")
    receipt = {
        "schema": "drecover001.recovery_preflight.v1",
        "run_id": "DRECOVER001-SOFTWARE-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "origin": "REGENERATED_FROM_SPEC",
        "python": sys.executable, "version": platform.python_version(),
        "tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped),
        "torch_available": maml.torch_available(), "torch_error": maml.torch_import_error(),
        "training_status": "NOT_RUN", "physical_solver_starts_actual_this_recovery": 0,
        "internal_solver_cases_actual_this_recovery": 0,
        "real_meta_training_executed": False, "admitted_real_labels": 0,
        "a5_independent_review": "NOT_PERFORMED", "physical_go": "NOT_ISSUED",
        "backup_restore": "NOT_ESTABLISHED",
    }
    if result.wasSuccessful() and maml.torch_available():
        config = maml.MAMLConfig(input_dim=12, output_dim=1, hidden_sizes=(8,8),
                                 inner_steps=2, tasks_per_batch=2, seed=17)
        import torch
        started = time.perf_counter()
        trained = MetaTrainer().fit(tests.fixture(), config=config, max_steps=20, mode="software_fixture")
        elapsed = time.perf_counter() - started
        models = {name: maml.ParameterSet.from_dict(trained[name]["final_parameters"])
                  for name in ("fomaml", "pretrain")}
        blob = pack_fixture_checkpoint(dataset=tests.fixture(), config=config,
                                       normalizer=trained["normalizer"], models=models)
        path = out / "synthetic_software_checkpoint.json"
        path.write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()
        restored = restore_fixture_checkpoint(path.read_bytes(), expected_sha256=digest,
                                              dataset=tests.fixture())
        for name in models:
            if restored.models[name].to_dict() != models[name].to_dict():
                raise RuntimeError("fixture checkpoint roundtrip changed parameters")
        initial = maml.init_parameters(config)
        deltas = {name: float(np.sqrt(sum(float(np.sum((a - b) ** 2))
                                           for a, b in zip(model.tensors, initial.tensors))))
                  for name, model in models.items()}
        if not all(np.isfinite(v) and v > 0 for v in deltas.values()):
            raise RuntimeError("fixture training must change both initial parameter sets")
        trace = {"scope": "SOFTWARE_FIXTURE_TRAINING_ONLY",
                 "real_meta_training_executed": False, "config": config.to_arm_dict(),
                 "torch_version": torch.__version__, "device": "cpu", "dtype": "float64",
                 "elapsed_seconds": elapsed, "train_task_ids": list(trained["train_task_ids"]),
                 "parameter_l2_change_from_initial": deltas,
                 "fomaml_steps": trained["fomaml"]["steps"],
                 "fomaml_history": trained["fomaml"]["history"],
                 "pretrain_history": trained["pretrain"]["history"]}
        trace_path = out / "synthetic_software_training_trace.json"
        trace_path.write_text(json.dumps(trace, indent=2, allow_nan=False), encoding="utf-8")
        receipt["synthetic_training_trace_sha256"] = hashlib.sha256(trace_path.read_bytes()).hexdigest()
        receipt["training_steps_per_model"] = 20
        receipt["parameter_l2_change_from_initial"] = deltas
        receipt["training_status"] = "SOFTWARE_FIXTURE_TRAINING_ONLY"
        receipt["synthetic_checkpoint_sha256"] = digest
        receipt["local_fixture_checkpoint_roundtrip"] = "PASS_NOT_REMOTE_BACKUP"
    receipt["source_sha256"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [
            ROOT / "research/concorde_metaopt/dreal001/meta/task_spec.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/meta_dataset.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/production.py",
            ROOT / "research/concorde_metaopt/meta_learning/maml.py",
            ROOT / "research/concorde_metaopt/meta_learning/adaptation.py",
            ROOT / "research/concorde_metaopt/aircraft/design_space.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_meta_contracts.py",
            ROOT / "research/concorde_metaopt/aircraft/openvsp_geometry.py",
            ROOT / "research/concorde_metaopt/aircraft/openvsp_check.py",
            ROOT / "research/concorde_metaopt/tests/test_openvsp_geometry.py",
            ROOT / "research/concorde_metaopt/dreal001/optimizers/arms.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_feedback.py",
            ROOT / "research/concorde_metaopt/dreal001/optimizers/recovery_bo.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_bo.py",
            ROOT / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
            ROOT / "research/concorde_metaopt/dreal001/optimizers/recovery_population.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_population.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/raw_verification.py",
            ROOT / "research/concorde_metaopt/dreal001/geometry/polar_parser.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_raw_verification.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_adaptation_guards.py",
            ROOT / "research/concorde_metaopt/aircraft/geometry_model.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_geometry_effects.py",
            ROOT / "docs/evidence/drecover001/diagnose_geometry_effects.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/task_deck.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_task_deck.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/checkpoint.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_checkpoint.py",
            ROOT / "research/concorde_metaopt/dreal001/optimizers/ledger.py",
            ROOT / "research/concorde_metaopt/dreal001/optimizers/evaluators.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_ledger.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/validation_training.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/m2_rehearsal.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_m2_rehearsal.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_path_injection.py",
            ROOT / "research/concorde_metaopt/dreal001/optimizers/p2a_v2.py",
            ROOT / "research/concorde_metaopt/dreal001/optimizers/p2a_v2_common.py",
            ROOT / "research/concorde_metaopt/reviews/a5_audit/a5_audit.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/m1_batch.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_m1_batch.py",
            ROOT / "docs/evidence/drecover001/run_m1_batch_software.py",
            ROOT / "docs/evidence/drecover001/assess_recovery_readiness.py",
            ROOT / "docs/evidence/drecover001/build_change_manifest.py",
            ROOT / "research/concorde_metaopt/tests/test_recovery_readiness.py",
            Path(__file__).resolve(),
        ]
    }
    receipt["software_tests_status"] = ("PASS_WITH_EXPLICIT_SKIPS" if result.skipped else "PASS") if result.wasSuccessful() else "FAIL"
    (out / "recovery_preflight_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())