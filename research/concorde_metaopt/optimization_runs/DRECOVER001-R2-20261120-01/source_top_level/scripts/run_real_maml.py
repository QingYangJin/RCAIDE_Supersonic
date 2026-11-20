"""Run one exploratory K=1 real FOMAML experiment on the nine admitted R2 labels.

No solver is started here. Test partition is evaluated once and is not used for
model selection. Results are exploratory, not a generalization claim.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

ROOT = Path("D:/RCAIDE/.worktrees/drecover001-20261117")
sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.dreal001.meta.meta_dataset import MetaDataset, TrainNormalizer
from research.concorde_metaopt.dreal001.meta.real_admission import (
    ArtifactBinding, RawFile, RealAdmissionManifest, admit_real_manifest)
from research.concorde_metaopt.dreal001.meta.real_training import RealAdaptationRunner, RealFOMALMTrainer
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec, canonical_sha
from research.concorde_metaopt.meta_learning.maml import MAMLConfig, ParameterSet

RUN_DIR = Path("D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
OUT = RUN_DIR / "real_maml_result.json"
RUN_ID = "DRECOVER001-MAML-20261120T074500Z"

manifest_dataset = json.loads((RUN_DIR / "real_dataset_manifest.json").read_text(encoding="utf-8"))
case_dirs = {}
for row in manifest_dataset["rows"]:
    cid = row["case_id"]
    if cid == "m202-baseline-admit":
        case_dirs[cid] = RUN_DIR / "cases" / "baseline-admit-01"
    else:
        case_dirs[cid] = RUN_DIR / "cases" / cid

tasks_by_id = {}
certificates = []
for row in manifest_dataset["rows"]:
    case_dir = case_dirs[row["case_id"]]
    payload = json.loads((case_dir / "admission_manifest.json").read_text(encoding="utf-8"))
    files = tuple(RawFile(kind=f["kind"], path=f["path"], sha256=f["sha256"], bytes=f["bytes"])
                  for f in payload["files"])
    binding = ArtifactBinding(**payload["binding"])
    manifest = RealAdmissionManifest(
        admission_id=payload["admission_id"], run_id=payload["run_id"],
        task_id=payload["task_id"], design_id=payload["design_id"],
        design=tuple(payload["design"]), geometry_sha256=payload["geometry_sha256"],
        evaluator_id=payload["evaluator_id"], solver_returncode=payload["solver_returncode"],
        solver_started_utc=payload["solver_started_utc"], outcome=payload["outcome"],
        partition=payload["partition"], files=files, binding=binding,
        independent_audit_ref=payload["independent_audit_ref"])
    task_payload = manifest_dataset["tasks"]
    task = next(t for t in task_payload if t["task_id"] == manifest.task_id)
    spec = TaskSpec(task_id=task["task_id"], split=task["split"], mach=task["mach"],
                    altitude_m=task["altitude_m"],
                    dynamic_pressure_pa=task["dynamic_pressure_pa"],
                    lift_target_n=task["lift_target_n"],
                    geometry_contract_sha256=task["geometry_contract_sha256"])
    certificate = admit_real_manifest(manifest=manifest, raw_root=case_dir, task=spec,
                                      design=manifest.design,
                                      expected_evaluator_id=manifest.evaluator_id,
                                      expected_audit_ref=manifest.independent_audit_ref)
    if certificate.raw_sha256 != row["raw_sha256"]:
        raise SystemExit("raw hash mismatch for " + row["case_id"])
    if not math.isclose(certificate.di_n, row["di_n"], rel_tol=1e-12, abs_tol=1e-9):
        raise SystemExit("label mismatch for " + row["case_id"])
    certificates.append(certificate)
    tasks_by_id[spec.task_id] = spec
tasks = tuple(tasks_by_id[key] for key in sorted(tasks_by_id))
dataset = MetaDataset.from_admitted_certificates(tasks, tuple(certificates))
dataset.require_real_admission()
if len(dataset.rows) != 9:
    raise SystemExit("expected nine admitted rows")

config = MAMLConfig(input_dim=12, output_dim=1, hidden_sizes=(32, 32), inner_lr=0.05,
                    inner_steps=5, outer_lr=0.01, tasks_per_batch=2,
                    first_order=True, seed=7)
trainer = RealFOMALMTrainer()
fit = trainer.fit(dataset, config=config, max_steps=20, support_per_task=1)
parameters = ParameterSet.from_dict(fit["fomaml"]["final_parameters"])
normalizer = fit["normalizer"]
runner = RealAdaptationRunner()

def predict(task, partition, cfg):
    rows = tuple(sorted(dataset.usable(task.task_id, "support"),
                       key=lambda item: item.observation_id))[:1]
    query = dataset.usable(task.task_id, partition)
    designs = __import__("numpy").asarray([item.design for item in query], dtype=float)
    out = runner.predict(parameters, config=cfg, normalizer=normalizer,
                         support_rows=rows, query_designs=designs,
                         task_id=task.task_id)
    return rows, query, out

def metrics(task, partition, cfg):
    rows, query, out = predict(task, partition, cfg)
    truth = __import__("numpy").asarray([item.di_n for item in query], dtype=float)
    err = out - truth
    denom = __import__("numpy").maximum(__import__("numpy").abs(truth), 1e-12)
    return {
        "task_id": task.task_id,
        "split": task.split,
        "partition": partition,
        "support_observation_ids": [item.observation_id for item in rows],
        "query_observation_ids": [item.observation_id for item in query],
        "predictions_di_n": [float(v) for v in out],
        "targets_di_n": [float(v) for v in truth],
        "absolute_errors_di_n": [float(v) for v in err],
        "mse": float(__import__("numpy").mean(err ** 2)),
        "mae": float(__import__("numpy").mean(__import__("numpy").abs(err))),
        "mre": float(__import__("numpy").mean(__import__("numpy").abs(err) / denom)),
    }

val_cfg = config
zero_cfg = MAMLConfig(input_dim=12, output_dim=1, hidden_sizes=(32, 32), inner_lr=0.05,
                      inner_steps=0, outer_lr=0.01, tasks_per_batch=2,
                      first_order=True, seed=7)
eval_tasks = [t for t in dataset.tasks if t.split in {"val", "test"}]
adapted = [metrics(t, "query", val_cfg) for t in eval_tasks]
zero_shot = [metrics(t, "query", zero_cfg) for t in eval_tasks]
train_adapted = [metrics(t, "query", val_cfg) for t in dataset.tasks if t.split == "train"]

payload = {
    "schema": "drecover001.real_maml_result.v1",
    "run_id": RUN_ID,
    "batch_id": "DRECOVER001-R2-20261120-01-MAML01",
    "scope": "EXPLORATORY_REAL_K1_NINE_LABELS",
    "generalization_claimed": False,
    "test_used_for_selection": False,
    "physical_solver_starts_actual": 0,
    "admitted_real_labels": len(dataset.rows),
    "labels_evidence_scope": "LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED",
    "same_host_backup": True,
    "dataset_sha256": canonical_sha([{
        "observation_id": r.observation_id, "task_id": r.task_id,
        "design": list(r.design), "partition": r.partition, "di_n": r.di_n,
        "raw_sha256": r.raw_sha256} for r in dataset.rows]),
    "train_task_ids": list(fit["train_task_ids"]),
    "support_counts": fit["support_counts"],
    "config": config.to_dict(),
    "status": fit["status"],
    "real_meta_training_executed": fit["real_meta_training_executed"],
    "training": {
        "steps": fit["fomaml"]["steps"],
        "status": fit["fomaml"]["status"],
        "history": fit["fomaml"]["history"],
    },
    "final_parameters_sha256": canonical_sha([t.tolist() for t in parameters.tensors]),
    "val_adapted": next(item for item in adapted if item["split"] == "val"),
    "test_adapted_once": next(item for item in adapted if item["split"] == "test"),
    "val_zero_shot": next(item for item in zero_shot if item["split"] == "val"),
    "test_zero_shot_once": next(item for item in zero_shot if item["split"] == "test"),
    "train_adapted": train_adapted,
    "caveats": [
        "K=1 support per train task; two train tasks; one query per evaluation task",
        "labels are locally verified and audit-bound but NOT_AUTHENTICATED",
        "same-host backup only; off-machine backup waived by the Owner",
        "new real-training entry was added after the A5 repair freeze and is disclosed, not A5-reviewed",
    ],
}
OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
print(json.dumps({
    "out": str(OUT),
    "status": payload["status"],
    "steps": payload["training"]["steps"],
    "dataset_sha256": payload["dataset_sha256"],
    "params_sha256": payload["final_parameters_sha256"],
    "val_adapted_mse": payload["val_adapted"]["mse"],
    "val_zero_mse": payload["val_zero_shot"]["mse"],
    "test_adapted_mse": payload["test_adapted_once"]["mse"],
    "test_zero_mse": payload["test_zero_shot_once"]["mse"],
}, indent=2))
