"""Offline M2 rehearsal: real task identities, synthetic labels, zero physics.

This module exercises the recovery-side meta-learning plumbing end to end without
touching OpenVSP, VSPAERO or any child process:

* task identities come from the M0-R task family (dreal001/m1/task_evaluator.py),
  so Mach / altitude / q / lift-target are the frozen F1R2 numbers;
* geometry is only a REGENERATED_FROM_SPEC contract digest, not a rebuilt mesh;
* labels are a deterministic synthetic response surface over the 12D design and
  the task context, explicitly marked synthetic_fixture and REHEARSAL_ONLY;
* every number here is a software rehearsal, never real evidence.

Nothing in this module may set real_meta_training_executed or mint a real
admission certificate.  The receipt is fail-closed: it records
scope=OFFLINE_REHEARSAL_ONLY and zero physical counters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ...meta_learning import maml
from ...meta_learning.adaptation import predict_parameters
from ..m1.task_evaluator import (
    ACTIVE_MASK,
    ATM_F1R2,
    BASELINE_X12,
    SREF_REF_FROZEN,
    TASK_DEFINITIONS,
    TaskDefinition,
    build_task_spec,
    task_fingerprint,
)
from .meta_dataset import MetaDataset, Observation, TrainNormalizer
from .task_spec import ContractError, TaskSpec, canonical_sha
from .validation_training import (
    ValidationPolicy,
    ValidationSelector,
    fit_with_validation,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DESIGN_SPACE_PATH = (
    REPO_ROOT / "research" / "concorde_metaopt" / "configs"
    / "design_space_12d_lifting_surfaces.yaml"
)
SCHEMA = "drecover001.m2_offline_rehearsal.v1"
CHECKPOINT_SCHEMA = "drecover001.m2_offline_rehearsal_checkpoint.v1"
SCOPE = "OFFLINE_REHEARSAL_ONLY"
SPLIT_MAP = {"meta_train": "train", "meta_val": "val", "meta_test": "test"}
OBSERVATIONS_PER_TASK = 16
SUPPORT_ROWS = 10
DESIGN_OFFSET_MODULUS = 23
MACH_REFERENCE = 2.02
MACH_SCALE = 0.2
CL_REFERENCE = 0.18
CL_SCALE = 0.01
SYNTHETIC_LABEL_SPEC = {
    "kind": "synthetic_fixture",
    "formula": (
        "cdi = 1e-3 * (1 + shape(u) + 0.10*(mach-2.02)/0.2 + 0.05*(cl-0.18)/0.01); "
        "di_n = q(mach) * Sref_design * cdi"
    ),
    "shape": (
        "shape(u) = 0.020*u0 + 0.015*u1 + 0.020*u2 + 0.010*u3 + 0.006*u4 "
        "+ 0.004*u5 + 0.002*u6 + 0.001*u7"
    ),
    "u": "(design - BASELINE_X12) / max(0.02*abs(BASELINE_X12), 1e-3)",
    "note": (
        "Deterministic response surface; it is NOT a physical model and cannot be "
        "used as real Di_N evidence or as a VSPAERO surrogate."
    ),
}
CODE_FILES = (
    "research/concorde_metaopt/dreal001/meta/m2_rehearsal.py",
    "research/concorde_metaopt/dreal001/meta/meta_dataset.py",
    "research/concorde_metaopt/dreal001/meta/task_spec.py",
    "research/concorde_metaopt/dreal001/meta/validation_training.py",
    "research/concorde_metaopt/dreal001/meta/production.py",
    "research/concorde_metaopt/meta_learning/maml.py",
    "research/concorde_metaopt/meta_learning/adaptation.py",
    "research/concorde_metaopt/dreal001/m1/task_evaluator.py",
    "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
)


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ContractError("required rehearsal source missing: " + str(path))
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_shas() -> dict[str, str]:
    """SHA256 of every source that can change a rehearsal number."""
    return {relative: _sha256_file(REPO_ROOT / relative) for relative in CODE_FILES}


def geometry_contract() -> dict[str, Any]:
    """REGENERATED_FROM_SPEC geometry digest; no mesh was rebuilt for this run."""
    return {
        "schema": "drecover001.geometry_contract.v1",
        "origin": "REGENERATED_FROM_SPEC",
        "source": "research/concorde_metaopt/dreal001/m1/task_evaluator.py",
        "sref_ref_m2": SREF_REF_FROZEN,
        "active_mask": ACTIVE_MASK,
        "atmosphere": asdict(ATM_F1R2),
        "baseline_x12": list(BASELINE_X12),
        "design_space_sha256": _sha256_file(DESIGN_SPACE_PATH),
        "native_probe_status": {
            "surface_diagnostic": "SURFACE_DIAGNOSTIC_PASS_NOT_FREEZE",
            "native_12d_response": "NATIVE_RESPONSE_PASS_NOT_FREEZE",
            "stl_placement": "STL_PLACEMENT_PASS_NOT_SOLVER_MESH",
        },
        "note": (
            "Digest only. A rebuilt mesh, deck and solver input chain is still "
            "required before any R2 physical batch."
        ),
    }


def build_rehearsal_tasks() -> tuple[tuple[TaskSpec, ...], dict[str, TaskDefinition]]:
    """Six real physical task identities; geometry contract is the rehearsal digest."""
    contract_sha = canonical_sha(geometry_contract())
    tasks = []
    definitions: dict[str, TaskDefinition] = {}
    for definition in TASK_DEFINITIONS:
        spec = build_task_spec(definition, SREF_REF_FROZEN)
        task = TaskSpec(
            task_id=definition.task_id,
            split=SPLIT_MAP[definition.split],
            mach=float(definition.mach),
            altitude_m=float(spec["atmosphere"]["altitude_m"]),
            dynamic_pressure_pa=float(spec["q_pa"]),
            lift_target_n=float(spec["l_ref_n"]),
            geometry_contract_sha256=contract_sha,
        )
        if abs(task.dynamic_pressure_pa - ATM_F1R2.q(definition.mach)) > 1e-9:
            raise ContractError("task q differs from the frozen atmosphere")
        tasks.append(task)
        definitions[task.task_id] = definition
    return tuple(tasks), definitions


def _design_scale() -> np.ndarray:
    base = np.asarray(BASELINE_X12, dtype=np.float64)
    return np.maximum(np.abs(base) * 0.02, 1e-3)


def designs_for_task(task_id: str, count: int = OBSERVATIONS_PER_TASK) -> tuple[tuple[float, ...], ...]:
    """Deterministic, per-task distinct 12D designs around the frozen baseline."""
    if not task_id:
        raise ContractError("design generation requires a task_id")
    base = np.asarray(BASELINE_X12, dtype=np.float64)
    scale = _design_scale()
    designs = []
    for index in range(count):
        offsets = np.array(
            [
                ((index * (coordinate + 3) + coordinate * 7) % DESIGN_OFFSET_MODULUS)
                / DESIGN_OFFSET_MODULUS - 0.5
                for coordinate in range(12)
            ],
            dtype=np.float64,
        )
        designs.append(tuple(float(value) for value in base + offsets * scale))
    return tuple(designs)


def synthetic_response(mach: float, cl_target: float, design: Sequence[float]) -> dict[str, float]:
    """Deterministic synthetic Di_N surface; see SYNTHETIC_LABEL_SPEC (NOT physics)."""
    base = np.asarray(BASELINE_X12, dtype=np.float64)
    scale = _design_scale()
    u = (np.asarray(design, dtype=np.float64) - base) / scale
    shape = (
        0.020 * u[0] + 0.015 * u[1] + 0.020 * u[2] + 0.010 * u[3]
        + 0.006 * u[4] + 0.004 * u[5] + 0.002 * u[6] + 0.001 * u[7]
    )
    mach_term = (float(mach) - MACH_REFERENCE) / MACH_SCALE
    lift_term = (float(cl_target) - CL_REFERENCE) / CL_SCALE
    cdi = 1e-3 * (1.0 + shape + 0.10 * mach_term + 0.05 * lift_term)
    q_pa = ATM_F1R2.q(mach)
    sref_m2 = float(design[0])
    di_n = q_pa * sref_m2 * cdi
    if not (math.isfinite(cdi) and cdi > 0.0 and math.isfinite(di_n)):
        raise ContractError("synthetic response produced an invalid Di_N")
    return {"di_n": di_n, "q_pa": q_pa, "sref_m2": sref_m2, "cdi": float(cdi),
            "cl": float(cl_target)}


def build_rehearsal_dataset(
    tasks: tuple[TaskSpec, ...] | None = None,
) -> tuple[MetaDataset, dict[str, TaskDefinition], dict[str, Any]]:
    """Six tasks x 16 designs; first 10 support, last 6 query; synthetic labels only."""
    if tasks is None:
        tasks, definitions = build_rehearsal_tasks()
    else:
        definitions = {definition.task_id: definition for definition in TASK_DEFINITIONS
                       if definition.task_id in {task.task_id for task in tasks}}
    rows = []
    task_manifest = []
    for task in tasks:
        definition = definitions[task.task_id]
        for index, design in enumerate(designs_for_task(task.task_id)):
            response = synthetic_response(definition.mach, definition.cl_target, design)
            rows.append(
                Observation(
                    observation_id="%s-%02d" % (task.task_id, index),
                    task_id=task.task_id,
                    design=design,
                    partition="support" if index < SUPPORT_ROWS else "query",
                    source_kind="synthetic_fixture",
                    status="ok",
                    di_n=response["di_n"],
                    q_pa=response["q_pa"],
                    sref_m2=response["sref_m2"],
                    cdi=response["cdi"],
                    cl=response["cl"],
                )
            )
        task_manifest.append(
            {
                "task_id": task.task_id,
                "split": task.split,
                "mach": task.mach,
                "cl_target": definition.cl_target,
                "q_pa": task.dynamic_pressure_pa,
                "lift_target_n": task.lift_target_n,
                "physics_sha256": task.physics_sha256,
                "task_fingerprint": task_fingerprint(definition),
                "support_observation_ids": ["%s-%02d" % (task.task_id, i) for i in range(SUPPORT_ROWS)],
                "query_observation_ids": [
                    "%s-%02d" % (task.task_id, i) for i in range(SUPPORT_ROWS, OBSERVATIONS_PER_TASK)
                ],
            }
        )
    dataset = MetaDataset(tuple(tasks), tuple(rows))
    manifest = {
        "observations_per_task": OBSERVATIONS_PER_TASK,
        "support_rows": SUPPORT_ROWS,
        "query_rows": OBSERVATIONS_PER_TASK - SUPPORT_ROWS,
        "task_count": len(tasks),
        "tasks": task_manifest,
        "rows_sha256": canonical_sha([asdict(row) for row in dataset.rows]),
        "treatment": "SYNTHETIC_REHEARSAL_LABELS_ONLY",
    }
    return dataset, definitions, manifest


def context_features(task: TaskSpec, definition: TaskDefinition) -> tuple[float, float, float, float]:
    """Four dimensionless task-context features (never design-derived)."""
    return (
        (task.mach - MACH_REFERENCE) / MACH_SCALE,
        (task.dynamic_pressure_pa - ATM_F1R2.anchor_q_pa) / ATM_F1R2.anchor_q_pa,
        (definition.cl_target - CL_REFERENCE) / CL_SCALE,
        task.altitude_m / ATM_F1R2.altitude_m - 1.0,
    )


def conditional_features(
    designs: np.ndarray,
    task: TaskSpec,
    definition: TaskDefinition,
    normalizer: TrainNormalizer,
) -> np.ndarray:
    """16D = train-only normalized 12D design + 4 task-context features."""
    matrix = np.asarray(designs, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != 12:
        raise ContractError("conditional features need an N x 12 design matrix")
    normalized = (matrix - normalizer.x_mean) / normalizer.x_scale
    context = np.tile(
        np.asarray(context_features(task, definition), dtype=np.float64), (normalized.shape[0], 1)
    )
    result = np.concatenate([normalized, context], axis=1)
    if not np.isfinite(result).all():
        raise ContractError("nonfinite conditional features")
    return result


def _pooled_step(
    parameters: maml.ParameterSet,
    features: np.ndarray,
    targets: np.ndarray,
    config: maml.MAMLConfig,
) -> tuple[maml.ParameterSet, float]:
    """One pooled supervised step, dimension-agnostic (12D or 16D)."""
    import torch

    tensors = [torch.tensor(tensor, dtype=torch.float64, requires_grad=True)
               for tensor in parameters.tensors]
    value = torch.tensor(np.asarray(features, dtype=np.float64), dtype=torch.float64)
    for index in range(0, len(tensors), 2):
        value = value @ tensors[index] + tensors[index + 1]
        if index + 2 < len(tensors):
            value = torch.tanh(value)
    loss = torch.mean((value - torch.tensor(np.asarray(targets, dtype=np.float64))) ** 2)
    gradients = torch.autograd.grad(loss, tensors)
    if not torch.isfinite(loss) or not all(torch.isfinite(gradient).all() for gradient in gradients):
        raise ContractError("nonfinite conditional pooled training")
    updated = maml.ParameterSet(
        [(tensor - config.outer_lr * gradient).detach().numpy().copy()
         for tensor, gradient in zip(tensors, gradients)]
    )
    return updated, float(loss.detach())


def _conditional_validation_score(
    dataset: MetaDataset,
    definitions: Mapping[str, TaskDefinition],
    parameters: maml.ParameterSet,
    *,
    config: maml.MAMLConfig,
    normalizer: TrainNormalizer,
) -> float:
    scores = []
    for task in dataset.tasks:
        if task.split != "val":
            continue
        query = dataset.usable(task.task_id, "query")
        features = conditional_features(
            np.asarray([row.design for row in query]), task, definitions[task.task_id], normalizer
        )
        _, targets = normalizer.arrays(query)
        prediction = predict_parameters(parameters, features)
        scores.append(float(np.mean((prediction - targets[:, 0]) ** 2)))
    if not scores:
        raise ContractError("conditional rehearsal requires validation tasks")
    if not all(math.isfinite(score) and score >= 0.0 for score in scores):
        raise ContractError("nonfinite conditional validation score")
    return float(np.mean(scores))


def train_conditional_pretrain(
    dataset: MetaDataset,
    definitions: Mapping[str, TaskDefinition],
    *,
    config: maml.MAMLConfig,
    normalizer: TrainNormalizer,
    policy: ValidationPolicy,
) -> tuple[maml.ParameterSet, dict[str, Any]]:
    """Pooled 16D conditional pre-training with validation early stopping (rehearsal)."""
    feature_blocks: list[np.ndarray] = []
    target_blocks: list[np.ndarray] = []
    for task in dataset.tasks:
        if task.split != "train":
            continue
        rows = tuple(row for row in dataset.rows if row.task_id == task.task_id and row.status == "ok")
        feature_blocks.append(
            conditional_features(
                np.asarray([row.design for row in rows]), task, definitions[task.task_id], normalizer
            )
        )
        target_blocks.append(normalizer.arrays(rows)[1])
    if not feature_blocks:
        raise ContractError("conditional rehearsal requires train tasks")
    features = np.concatenate(feature_blocks, axis=0)
    targets = np.concatenate(target_blocks, axis=0)
    parameters = maml.init_parameters(config)
    selector = ValidationSelector(policy)
    selector.observe(
        0,
        _conditional_validation_score(dataset, definitions, parameters, config=config,
                                      normalizer=normalizer),
        parameters,
    )
    training_history = []
    reason = "MAX_STEPS"
    step = 0
    for step in range(1, policy.max_steps + 1):
        parameters, loss = _pooled_step(parameters, features, targets, config)
        training_history.append({"step": step, "loss": loss})
        if step % policy.interval == 0 or step == policy.max_steps:
            score = _conditional_validation_score(
                dataset, definitions, parameters, config=config, normalizer=normalizer
            )
            if selector.observe(step, score, parameters):
                reason = "VALIDATION_PATIENCE"
                break
    report = {
        "steps_executed": step,
        "best_step": selector.best_step,
        "best_validation_mse_normalized": selector.best_score,
        "best_validation_mse_di_n2": selector.best_score * normalizer.y_scale ** 2,
        "stop_reason": reason,
        "validation_history": selector.history,
        "training_history": training_history,
        "feature_layout": "12D normalized design + 4 task-context features",
    }
    return selector.best.copy(), report


def _prediction_after_adaptation(
    parameters: maml.ParameterSet,
    config: maml.MAMLConfig,
    features_support: np.ndarray,
    targets_support: np.ndarray,
    features_query: np.ndarray,
    targets_query: np.ndarray,
    task_id: str,
) -> np.ndarray:
    episode = maml.TaskEpisode(features_support, targets_support, features_query, targets_query, task_id)
    adapted, _ = maml.inner_adapt(parameters, episode, config)
    return predict_parameters(adapted, features_query)


def evaluate_models(
    dataset: MetaDataset,
    definitions: Mapping[str, TaskDefinition],
    *,
    normalizer: TrainNormalizer,
    config: maml.MAMLConfig,
    conditional_config: maml.MAMLConfig,
    models: Mapping[str, maml.ParameterSet],
) -> dict[str, Any]:
    """Post-hoc K=0/K=4/K=10 scores on meta-test tasks; labels are synthetic rehearsal targets."""
    results: dict[str, Any] = {
        "metric": "MSE against synthetic Di_N (normalized and N^2 units)",
        "test_task_ids": [task.task_id for task in dataset.tasks if task.split == "test"],
        "test_labels_used_only_for_post_hoc_scoring": True,
        "note": (
            "The frozen M0-R meta-test conditions (Mach 1.80) sit outside the meta-train "
            "Mach 2.02-2.20 band, so zero-shot error is dominated by a deliberate "
            "distribution shift; the K-shot block exercises adaptation machinery, not "
            "physical accuracy. FOMAML K=0 is the unadapted meta-initialization, not a "
            "deployed predictor; only K>=4 scores describe adaptation."
        ),
    }
    test_tasks = [task for task in dataset.tasks if task.split == "test"]
    if not test_tasks:
        raise ContractError("rehearsal requires blind test tasks")
    diagnostics: dict[str, Any] = {}
    for task in test_tasks:
        query = dataset.usable(task.task_id, "query")
        _, query_y = normalizer.arrays(query)
        diagnostics[task.task_id] = {
            "query_mean_shift_normalized_from_train_mean": float(np.mean(query_y)),
            "query_mean_di_n": float(np.mean(query_y) * normalizer.y_scale + normalizer.y_mean),
        }
    results["test_task_diagnostics"] = diagnostics
    for k_shot in (0, 4, 10):
        block: dict[str, Any] = {}
        for name, parameters in models.items():
            conditional = name == "conditional_pretrain"
            active_config = conditional_config if conditional else config
            per_task: dict[str, Any] = {}
            for task in test_tasks:
                support = dataset.usable(task.task_id, "support")
                query = dataset.usable(task.task_id, "query")
                if not support or not query:
                    raise ContractError("test task requires support/query rows")
                support_x, support_y = normalizer.arrays(support)
                query_x, query_y = normalizer.arrays(query)
                if conditional:
                    support_x = conditional_features(
                        np.asarray([row.design for row in support]), task,
                        definitions[task.task_id], normalizer,
                    )
                    query_x = conditional_features(
                        np.asarray([row.design for row in query]), task,
                        definitions[task.task_id], normalizer,
                    )
                if k_shot > 0:
                    if k_shot > support_x.shape[0]:
                        raise ContractError("K exceeds support rows")
                    prediction = _prediction_after_adaptation(
                        parameters, active_config,
                        support_x[:k_shot], support_y[:k_shot],
                        query_x, query_y, task.task_id,
                    )
                else:
                    prediction = predict_parameters(parameters, query_x)
                mse_normalized = float(np.mean((prediction - query_y[:, 0]) ** 2))
                per_task[task.task_id] = {
                    "mse_normalized": mse_normalized,
                    "mse_di_n2": mse_normalized * normalizer.y_scale ** 2,
                    "query_rows": len(query),
                }
            block[name] = {
                "macro": {
                    "mse_normalized": float(np.mean([v["mse_normalized"] for v in per_task.values()])),
                    "mse_di_n2": float(np.mean([v["mse_di_n2"] for v in per_task.values()])),
                },
                "per_task": per_task,
            }
        constant_per_task: dict[str, Any] = {}
        for task in test_tasks:
            query = dataset.usable(task.task_id, "query")
            _, query_y = normalizer.arrays(query)
            mse_normalized = float(np.mean(query_y ** 2))
            constant_per_task[task.task_id] = {
                "mse_normalized": mse_normalized,
                "mse_di_n2": mse_normalized * normalizer.y_scale ** 2,
                "query_rows": len(query),
            }
        block["constant_train_mean"] = {
            "macro": {
                "mse_normalized": float(np.mean(
                    [value["mse_normalized"] for value in constant_per_task.values()]
                )),
                "mse_di_n2": float(np.mean(
                    [value["mse_di_n2"] for value in constant_per_task.values()]
                )),
            },
            "per_task": constant_per_task,
        }
        results["k%d" % k_shot] = block
    return results


def _parameters_sha(parameters: maml.ParameterSet) -> str:
    return canonical_sha(parameters.to_dict())


def _normalizer_payload(normalizer: TrainNormalizer) -> dict[str, Any]:
    return {
        "x_mean": normalizer.x_mean.tolist(),
        "x_scale": normalizer.x_scale.tolist(),
        "y_mean": normalizer.y_mean,
        "y_scale": normalizer.y_scale,
        "fit_observation_ids": list(normalizer.fit_observation_ids),
    }


def _utc_run_id() -> str:
    return "DRECOVER001-M2-REHEARSAL-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_rehearsal(
    *,
    policy: ValidationPolicy | None = None,
    seed: int = 42,
    run_id: str | None = None,
    dataset: MetaDataset | None = None,
    definitions: Mapping[str, TaskDefinition] | None = None,
    manifest: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the whole offline rehearsal; returns (receipt, checkpoint payload)."""
    if policy is None:
        policy = ValidationPolicy(max_steps=30, interval=5, patience=3)
    if type(seed) is not int:
        raise ContractError("rehearsal seed must be an int")
    if dataset is None:
        if definitions is not None or manifest is not None:
            raise ContractError("definitions/manifest require a matching dataset")
        dataset, definitions, manifest = build_rehearsal_dataset()
    if definitions is None or manifest is None:
        raise ContractError("dataset requires matching definitions and manifest")
    dataset.require_software_fixture()
    if not maml.torch_available():
        raise ContractError("TORCH_NOT_AVAILABLE")
    config = maml.MAMLConfig(
        input_dim=12, output_dim=1, hidden_sizes=(32, 32), inner_steps=5,
        inner_lr=0.01, outer_lr=1e-3, tasks_per_batch=3, first_order=True, seed=seed,
    )
    conditional_config = maml.MAMLConfig(
        input_dim=16, output_dim=1, hidden_sizes=(32, 32), inner_steps=5,
        inner_lr=0.01, outer_lr=1e-3, tasks_per_batch=3, first_order=True, seed=seed,
    )
    fixture = fit_with_validation(dataset, config=config, policy=policy, mode="software_fixture")
    normalizer = fixture["normalizer"]
    conditional_parameters, conditional_report = train_conditional_pretrain(
        dataset, definitions, config=conditional_config, normalizer=normalizer, policy=policy
    )
    random_init = maml.init_parameters(config, seed=seed + 1)
    models = {
        "random_init": random_init,
        "pretrain": fixture["models"]["pretrain"],
        "fomaml": fixture["models"]["fomaml"],
        "conditional_pretrain": conditional_parameters,
    }
    evaluation = evaluate_models(
        dataset, definitions, normalizer=normalizer, config=config,
        conditional_config=conditional_config, models=models,
    )
    checkpoints = {
        "%s_parameters_sha256" % name: _parameters_sha(parameters)
        for name, parameters in models.items()
    }
    k0 = evaluation["k0"]
    k4 = evaluation["k4"]
    k10 = evaluation["k10"]
    contract = geometry_contract()
    receipt = {
        "schema": SCHEMA,
        "run_id": run_id or _utc_run_id(),
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": SCOPE,
        "evidence_grade": "OFFLINE_REHEARSAL_NO_PHYSICAL_EVIDENCE",
        "real_admission": False,
        "real_meta_training_executed": False,
        "admitted_real_labels": 0,
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
        "labels": dict(SYNTHETIC_LABEL_SPEC),
        "task_identity": {
            "source": "research/concorde_metaopt/dreal001/m1/task_evaluator.py:TASK_DEFINITIONS",
            "character": "FROZEN_F1R2_CONDITIONS_REUSED",
            "tasks": list(manifest["tasks"]),
        },
        "geometry_contract": contract,
        "sha256": {
            "geometry_contract": canonical_sha(contract),
            "task_split": canonical_sha([
                {"task_id": task.task_id, "split": task.split, "physics_sha256": task.physics_sha256}
                for task in dataset.tasks
            ]),
            "dataset_manifest": canonical_sha(dict(manifest)),
            "config": canonical_sha(config.to_arm_dict()),
            "conditional_config": canonical_sha(conditional_config.to_arm_dict()),
            "code": canonical_sha(source_shas()),
            "checkpoint": "",
        },
        "code_files": source_shas(),
        "config": config.to_arm_dict(),
        "conditional_config": conditional_config.to_arm_dict(),
        "validation_policy": asdict(policy),
        "dataset": {key: value for key, value in manifest.items() if key != "tasks"},
        "training": {
            "fomaml": fixture["reports"]["fomaml"],
            "pretrain": fixture["reports"]["pretrain"],
            "conditional_pretrain": conditional_report,
            "fixture_scope": fixture["scope"],
            "pretraining_kind": fixture["pretraining_kind"],
            "test_used_for_selection": False,
            "validation_task_ids": fixture["validation_task_ids"],
        },
        "evaluation": evaluation,
        "checkpoint_parameters_sha256": checkpoints,
        "verdict": {
            "status": "REHEARSAL_COMPLETE_NOT_REAL_EVIDENCE",
            "interpretation": (
                "The FOMAML / pooled / conditional pipeline, split isolation, validation "
                "early stopping and K-shot adaptation all execute on synthetic labels; the "
                "measured gains have no physical meaning."
            ),
            "fomaml_k4_vs_random_init_k4_mse_reduction": (
                k4["random_init"]["macro"]["mse_normalized"]
                - k4["fomaml"]["macro"]["mse_normalized"]
            ),
            "fomaml_k4_vs_pretrain_k4_mse_delta": (
                k4["fomaml"]["macro"]["mse_normalized"]
                - k4["pretrain"]["macro"]["mse_normalized"]
            ),
            "fomaml_k0_vs_pretrain_k0_mse_delta": (
                k0["fomaml"]["macro"]["mse_normalized"]
                - k0["pretrain"]["macro"]["mse_normalized"]
            ),
            "fomaml_k10_vs_pretrain_k10_mse_delta": (
                k10["fomaml"]["macro"]["mse_normalized"]
                - k10["pretrain"]["macro"]["mse_normalized"]
            ),
            "mse_normalized_by_k_shot": {
                name: {
                    "k0": k0[name]["macro"]["mse_normalized"],
                    "k4": k4[name]["macro"]["mse_normalized"],
                    "k10": k10[name]["macro"]["mse_normalized"],
                }
                for name in ("fomaml", "pretrain", "conditional_pretrain", "random_init")
            },
            "ood_blind_test_gap_expected": True,
            "meta_learning_gain_claim": "NO_META_LEARNING_GAIN_CLAIM",
            "blocking_gates_before_real_maml": [
                "R0_A5_INDEPENDENT_REVIEW",
                "RESTORED_CODE_BASELINE_PASS",
                "BACKUP_RESTORE_PASS_INDEPENDENT_FAILURE_DOMAIN",
                "REAL_ADMISSION_IMPLEMENTED_AND_RAW_VERIFIED",
                "NEW_R2_GATE_AND_LEAD_BATCH_GO",
            ],
        },
    }
    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "run_id": receipt["run_id"],
        "scope": SCOPE,
        "real_admission": False,
        "real_meta_training_executed": False,
        "labels": dict(SYNTHETIC_LABEL_SPEC),
        "normalizer": _normalizer_payload(normalizer),
        "config": config.to_arm_dict(),
        "conditional_config": conditional_config.to_arm_dict(),
        "models": {name: parameters.to_dict() for name, parameters in models.items()},
        "dataset_manifest_sha256": receipt["sha256"]["dataset_manifest"],
        "code_sha256": receipt["sha256"]["code"],
    }
    blob = json.dumps(checkpoint, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    receipt["sha256"]["checkpoint"] = hashlib.sha256(blob).hexdigest()
    return receipt, checkpoint


def write_artifacts(
    receipt: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    *,
    receipt_path: str | Path,
    checkpoint_path: str | Path,
) -> tuple[Path, Path]:
    receipt_target = Path(receipt_path)
    checkpoint_target = Path(checkpoint_path)
    checkpoint_target.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_blob = json.dumps(checkpoint, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if hashlib.sha256(checkpoint_blob.encode("utf-8")).hexdigest() != receipt["sha256"]["checkpoint"]:
        raise ContractError("checkpoint bytes differ from their recorded SHA256")
    receipt_target.parent.mkdir(parents=True, exist_ok=True)
    receipt_target.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    checkpoint_target.write_text(checkpoint_blob + "\n", encoding="utf-8")
    return receipt_target, checkpoint_target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline M2 rehearsal (zero physical).")
    parser.add_argument("--out", default=str(REPO_ROOT / "docs" / "evidence" / "drecover001"
                                             / "m2_offline_rehearsal_receipt.json"))
    parser.add_argument("--checkpoint", default=str(REPO_ROOT / "docs" / "evidence" / "drecover001"
                                                   / "m2_offline_rehearsal_checkpoint.json"))
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    policy = ValidationPolicy(max_steps=args.max_steps, interval=args.interval,
                              patience=args.patience)
    receipt, checkpoint = run_rehearsal(policy=policy, seed=args.seed)
    receipt_path, checkpoint_path = write_artifacts(
        receipt, checkpoint, receipt_path=args.out, checkpoint_path=args.checkpoint
    )
    print(json.dumps({
        "run_id": receipt["run_id"],
        "scope": receipt["scope"],
        "receipt": str(receipt_path),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": receipt["sha256"]["checkpoint"],
        "k0": {name: block["macro"] for name, block in receipt["evaluation"]["k0"].items()},
        "k4": {name: block["macro"] for name, block in receipt["evaluation"]["k4"].items()},
        "k10": {name: block["macro"] for name, block in receipt["evaluation"]["k10"].items()},
        "verdict": receipt["verdict"]["status"],
        "physical_solver_starts_actual": receipt["physical_solver_starts_actual"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
