"""Real-data FOMAML entry, enabled only by minted admission certificates.

This module is separate from the software-fixture production preflight so that
fixture-only guards remain intact. It never reads test partitions for model
selection and never claims generalization from the small R2 batch.
"""
from __future__ import annotations

import math

import numpy as np

from .meta_dataset import MetaDataset, Observation, TrainNormalizer
from .task_spec import ContractError


def _require_real_dataset(dataset: MetaDataset) -> None:
    if not isinstance(dataset, MetaDataset):
        raise ContractError("real training requires MetaDataset")
    dataset.require_real_admission()
    if any(row.source_kind != "vspaero_raw" for row in dataset.rows):
        raise ContractError("real training rejects synthetic rows")
    if not dataset.admissions:
        raise ContractError("REAL_ADMISSION_NOT_IMPLEMENTED: no minted certificates")


class RealFOMALMTrainer:
    """Bounded 12D/Di_N first-order MAML on admitted real support/query rows."""

    def fit(self, dataset: MetaDataset, *, config, max_steps: int,
            support_per_task: int = 1) -> dict:
        _require_real_dataset(dataset)
        if type(max_steps) is not int or not 1 <= max_steps <= 100:
            raise ContractError("real FOMAML requires 1..100 outer steps")
        if type(support_per_task) is not int or support_per_task < 1:
            raise ContractError("support_per_task must be a positive integer")
        if (config.input_dim != 12 or config.output_dim != 1
                or not config.first_order or config.head_only):
            raise ContractError("real FOMAML requires 12D/Di_N first-order, not ANIL/full-MAML")
        from ...meta_learning import maml
        if not maml.torch_available():
            raise ContractError("TORCH_NOT_AVAILABLE: no real training executed")
        normalizer = TrainNormalizer.fit(dataset)
        train_tasks = [task for task in dataset.tasks if task.split == "train"]
        if len(train_tasks) < 2:
            raise ContractError("real FOMAML requires at least two train tasks")
        episodes = []
        support_counts = {}
        for task in train_tasks:
            support = tuple(sorted(dataset.usable(task.task_id, "support"),
                                   key=lambda row: row.observation_id))[:support_per_task]
            query = dataset.usable(task.task_id, "query")
            if len(support) < support_per_task:
                raise ContractError("not enough admitted support rows for " + task.task_id)
            if not query:
                raise ContractError("missing admitted query rows for " + task.task_id)
            sx, sy = normalizer.arrays(support)
            qx, qy = normalizer.arrays(query)
            episodes.append(maml.TaskEpisode(sx, sy, qx, qy, task.task_id))
            support_counts[task.task_id] = len(support)
        result = maml.meta_train(episodes, config, max_steps)
        if result["status"] != "VALID" or result["steps"] != max_steps:
            raise ContractError("real FOMAML failed: " + str(result.get("failure")))
        return {
            "status": "REAL_META_TRAINING_EXECUTED",
            "real_meta_training_executed": True,
            "physical_solver_starts_actual": 0,
            "admitted_real_labels": len(dataset.rows),
            "support_per_task": support_per_task,
            "support_counts": support_counts,
            "train_task_ids": tuple(task.task_id for task in train_tasks),
            "validation_task_ids": tuple(task.task_id for task in dataset.tasks if task.split == "val"),
            "test_task_ids": tuple(task.task_id for task in dataset.tasks if task.split == "test"),
            "test_used_for_selection": False,
            "normalizer": normalizer,
            "config": config,
            "fomaml": result,
        }


class RealAdaptationRunner:
    """Support-only adaptation on admitted real observations; query labels are not used."""

    def predict(self, parameters, *, config, normalizer: TrainNormalizer,
                support_rows: tuple[Observation, ...], query_designs: np.ndarray,
                task_id: str) -> np.ndarray:
        query = np.asarray(query_designs, dtype=np.float64)
        if query.ndim != 2 or query.shape[1] != 12 or not len(query):
            raise ContractError("query designs must be nonempty (N,12)")
        if not np.isfinite(query).all():
            raise ContractError("query designs must be finite")
        if config.input_dim != 12 or config.output_dim != 1:
            raise ContractError("real adaptation requires 12D/Di_N model")
        if not support_rows:
            raise ContractError("real adaptation requires admitted support rows")
        if any(row.source_kind != "vspaero_raw" for row in support_rows):
            raise ContractError("real adaptation rejects synthetic rows")
        if any(row.status != "ok" or row.partition != "support" for row in support_rows):
            raise ContractError("real adaptation accepts only successful support rows")
        if any(row.task_id != task_id for row in support_rows):
            raise ContractError("real adaptation support must match the supplied task")
        if len({row.observation_id for row in support_rows}) != len(support_rows):
            raise ContractError("duplicate real adaptation observation identity")
        designs = np.asarray([row.design for row in support_rows], dtype=np.float64)
        for index, design in enumerate(designs):
            if any(np.max(np.abs(design - prior)) <= 1e-12 for prior in designs[:index]):
                raise ContractError("duplicate real adaptation support design")
            if np.any(np.max(np.abs(query - design), axis=1) <= 1e-12):
                raise ContractError("real adaptation support/query design leakage")
        from ...meta_learning import maml
        sx, sy = normalizer.arrays(support_rows)
        episode = maml.TaskEpisode(sx, sy, sx[:1], np.zeros((1, 1)), "support_only")
        adapted, _ = maml.inner_adapt(parameters, episode, config)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            features = (query - normalizer.x_mean) / normalizer.x_scale
            prediction = features
            for index in range(0, len(adapted.tensors), 2):
                prediction = prediction @ adapted.tensors[index] + adapted.tensors[index + 1]
                if index + 2 < len(adapted.tensors):
                    prediction = np.tanh(prediction)
            output = prediction[:, 0] * normalizer.y_scale + normalizer.y_mean
        if not np.isfinite(output).all():
            raise ContractError("nonfinite real adaptation prediction")
        return output
