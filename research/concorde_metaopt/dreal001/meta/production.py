"""Recovery-only software preflight. Real production remains explicitly disabled.

Reuses the existing float64 FOMAML core; never imports a physical evaluator.
No fixture result from this module is REAL_META_TRAINING_EXECUTED.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np

from .meta_dataset import MetaDataset, TrainNormalizer
from .task_spec import ContractError, TaskSpec, canonical_sha


def _forward(params, features):
    value = np.asarray(features, dtype=np.float64)
    for index in range(0, len(params.tensors), 2):
        value = value @ params.tensors[index] + params.tensors[index + 1]
        if index + 2 < len(params.tensors):
            value = np.tanh(value)
    return value


class MetaTrainer:
    """Bounded software-only comparison; no real-data admission escape hatch."""

    def fit(self, dataset: MetaDataset, *, config, max_steps: int,
            mode: str = "real") -> dict:
        # Gate before any backend or normalization work, including torch imports.
        if mode == "real":
            dataset.require_real_admission()
        if mode != "software_fixture":
            raise ContractError("unsupported execution mode")
        dataset.require_software_fixture()
        if type(max_steps) is not int or not 1 <= max_steps <= 100:
            raise ContractError("software preflight requires 1..100 outer steps")
        from ...meta_learning import maml
        if not maml.torch_available():
            raise ContractError("TORCH_NOT_AVAILABLE: no training executed")
        if config.input_dim != 12 or config.output_dim != 1 or not config.first_order or config.head_only:
            raise ContractError("recovery preflight requires 12D/Di_N FOMAML, not ANIL/full-MAML")
        normalizer = TrainNormalizer.fit(dataset)
        train_tasks = [t for t in dataset.tasks if t.split == "train"]
        episodes = []
        for task in train_tasks:
            sx, sy = normalizer.arrays(dataset.usable(task.task_id, "support"))
            qx, qy = normalizer.arrays(dataset.usable(task.task_id, "query"))
            episodes.append(maml.TaskEpisode(sx, sy, qx, qy, task.task_id))
        result = maml.meta_train(episodes, config, max_steps)
        if result["status"] != "VALID" or result["steps"] != max_steps:
            raise ContractError("FOMAML preflight failed: " + str(result.get("failure")))

        # Ordinary pooled supervised pretraining, NOT a metadata-only BO clone.
        import torch
        params = maml.init_parameters(config)
        tensors = [torch.tensor(v, dtype=torch.float64, requires_grad=True) for v in params.tensors]
        train_ids = {t.task_id for t in train_tasks}
        rows = tuple(r for r in dataset.rows if r.task_id in train_ids and r.status == "ok")
        x, y = normalizer.arrays(rows)
        tx, ty = torch.tensor(x, dtype=torch.float64), torch.tensor(y, dtype=torch.float64)
        history = []
        for step in range(max_steps):
            value = tx
            for index in range(0, len(tensors), 2):
                value = value @ tensors[index] + tensors[index + 1]
                if index + 2 < len(tensors):
                    value = torch.tanh(value)
            loss = torch.mean((value - ty) ** 2)
            grads = torch.autograd.grad(loss, tensors)
            if not torch.isfinite(loss) or not all(torch.isfinite(g).all() for g in grads):
                raise ContractError("nonfinite ordinary pretraining")
            history.append({"step": step, "loss": float(loss.detach())})
            tensors = [(v - config.outer_lr * g).detach().requires_grad_(True)
                       for v, g in zip(tensors, grads)]
        pretrain = maml.ParameterSet([v.detach().numpy().copy() for v in tensors])
        return {"status": "SOFTWARE_FIXTURE_TRAINING_ONLY", "physical_solver_starts_actual": 0,
                "real_meta_training_executed": False, "fomaml": result,
                "pretrain": {"final_parameters": pretrain.to_dict(), "history": history},
                "normalizer": normalizer, "config": config,
                "train_task_ids": tuple(t.task_id for t in train_tasks)}


class AdaptationRunner:
    def predict(self, parameters, *, config, normalizer: TrainNormalizer,
                support_rows: tuple, query_designs: np.ndarray):
        """Software-only support adaptation; validate isolation BEFORE any gradient."""
        query = np.asarray(query_designs, dtype=np.float64)
        if (query.ndim != 2 or query.shape[1] != 12 or not len(query)
                or not np.isfinite(query).all()):
            raise ContractError("query designs must be nonempty finite (N,12)")
        if config.input_dim != 12 or config.output_dim != 1:
            raise ContractError("adaptation requires 12D/Di_N model")
        if support_rows:
            if any(r.source_kind != "synthetic_fixture" for r in support_rows):
                raise ContractError("software adaptation rejects real/declared-real data")
            if any(r.status != "ok" or r.partition != "support" for r in support_rows):
                raise ContractError("adaptation accepts only successful support rows")
            if len({r.task_id for r in support_rows}) != 1:
                raise ContractError("adaptation support must come from one task")
            if len({r.observation_id for r in support_rows}) != len(support_rows):
                raise ContractError("duplicate adaptation observation identity")
            support = np.asarray([r.design for r in support_rows], dtype=np.float64)
            for i, design in enumerate(support):
                if any(np.max(np.abs(design - prior)) <= 1e-12 for prior in support[:i]):
                    raise ContractError("duplicate adaptation support design")
                if np.any(np.max(np.abs(query - design), axis=1) <= 1e-12):
                    raise ContractError("adaptation support/query design leakage")
            sx, sy = normalizer.arrays(support_rows)
            from ...meta_learning import maml
            # Dummy query has no experimental label and is unused by inner_adapt.
            episode = maml.TaskEpisode(sx, sy, sx[:1], np.zeros((1, 1)), "support_only")
            parameters, _ = maml.inner_adapt(parameters, episode, config)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            features = (query - normalizer.x_mean) / normalizer.x_scale
            prediction = _forward(parameters, features)
            output = prediction[:, 0] * normalizer.y_scale + normalizer.y_mean
        if not np.isfinite(features).all() or not np.isfinite(output).all():
            raise ContractError("nonfinite adaptation prediction")
        return output


@dataclass(frozen=True)
class ConditionalFeatureSpec:
    """Frozen affine encoding for the four task-context features.

    The references/scales are caller-supplied contract values, not inferred physics.
    """

    mach_reference: float
    mach_scale: float
    q_reference: float
    cl_reference: float
    cl_scale: float
    altitude_reference: float

    def __post_init__(self) -> None:
        for name in ("mach_reference", "q_reference", "cl_reference", "altitude_reference"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
                raise ContractError(f"{name} must be finite and positive")
        for name in ("mach_scale", "cl_scale"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0.0:
                raise ContractError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class TaskContext:
    """Observed task condition feature; never a substitute for an admitted label."""

    cl_target: float

    def __post_init__(self) -> None:
        if (isinstance(self.cl_target, bool) or not math.isfinite(self.cl_target)
                or self.cl_target <= 0.0):
            raise ContractError("cl_target must be finite and positive")


def context_features(task: TaskSpec, context: TaskContext,
                     feature_spec: ConditionalFeatureSpec) -> np.ndarray:
    if not isinstance(task, TaskSpec):
        raise ContractError("context_features requires TaskSpec")
    if not isinstance(context, TaskContext):
        raise ContractError("context_features requires TaskContext")
    if not isinstance(feature_spec, ConditionalFeatureSpec):
        raise ContractError("context_features requires ConditionalFeatureSpec")
    values = (
        (task.mach - feature_spec.mach_reference) / feature_spec.mach_scale,
        (task.dynamic_pressure_pa - feature_spec.q_reference) / feature_spec.q_reference,
        (context.cl_target - feature_spec.cl_reference) / feature_spec.cl_scale,
        task.altitude_m / feature_spec.altitude_reference - 1.0,
    )
    features = np.asarray(values, dtype=np.float64)
    if features.shape != (4,) or not np.isfinite(features).all():
        raise ContractError("nonfinite task-context features")
    return features


def _append_context(normalized_design: np.ndarray, context: np.ndarray) -> np.ndarray:
    design = np.asarray(normalized_design, dtype=np.float64)
    vector = np.asarray(context, dtype=np.float64)
    if (design.ndim != 2 or design.shape[1] != 12 or not len(design)
            or not np.isfinite(design).all()):
        raise ContractError("normalized design must be nonempty finite (N,12)")
    if vector.shape != (4,) or not np.isfinite(vector).all():
        raise ContractError("task context must be finite (4,)")
    features = np.concatenate([design, np.broadcast_to(vector, (len(design), 4))], axis=1)
    if features.shape[1] != 16 or not np.isfinite(features).all():
        raise ContractError("nonfinite conditional features")
    return features


def conditional_features(designs: np.ndarray, normalizer: TrainNormalizer,
                         context: np.ndarray) -> np.ndarray:
    """Normalize 12D designs with train-only statistics and append four context dims."""
    if not isinstance(normalizer, TrainNormalizer):
        raise ContractError("conditional_features requires TrainNormalizer")
    raw = np.asarray(designs, dtype=np.float64)
    if (raw.ndim != 2 or raw.shape[1] != 12 or not len(raw) or not np.isfinite(raw).all()):
        raise ContractError("designs must be nonempty finite (N,12)")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        normalized = (raw - normalizer.x_mean) / normalizer.x_scale
    return _append_context(normalized, context)


class ConditionalPretrainer:
    """Fixture-only conditional-feature pretraining; real admission stays fail-closed.

    The 16D model is a training-time software baseline, not a physics model. It never
    reads test partitions and never writes a REAL_META_TRAINING_EXECUTED flag.
    """

    def fit(self, dataset: MetaDataset, *, config, contexts: dict,
            feature_spec: ConditionalFeatureSpec, policy=None,
            mode: str = "real") -> dict:
        if mode == "real":
            dataset.require_real_admission()
        if mode != "software_fixture":
            raise ContractError("unsupported execution mode")
        dataset.require_software_fixture()
        from .validation_training import ValidationPolicy, ValidationSelector
        if policy is None:
            policy = ValidationPolicy()
        if not isinstance(policy, ValidationPolicy):
            raise ContractError("ValidationPolicy required")
        if not isinstance(feature_spec, ConditionalFeatureSpec):
            raise ContractError("ConditionalFeatureSpec required")
        if not isinstance(contexts, dict):
            raise ContractError("contexts must be a task_id -> TaskContext mapping")
        if (config.input_dim != 16 or config.output_dim != 1
                or not config.first_order or config.head_only):
            raise ContractError("conditional pretraining requires 16D/Di_N FOMAML")
        from ...meta_learning import maml
        if not maml.torch_available():
            raise ContractError("TORCH_NOT_AVAILABLE: no conditional training executed")
        normalizer = TrainNormalizer.fit(dataset)
        context_vectors = {}
        for task in dataset.tasks:
            if task.task_id not in contexts:
                raise ContractError("missing task context for " + task.task_id)
            context_vectors[task.task_id] = context_features(
                task, contexts[task.task_id], feature_spec)
        train_tasks = [t for t in dataset.tasks if t.split == "train"]
        validation_tasks = [t for t in dataset.tasks if t.split == "val"]
        if not validation_tasks:
            raise ContractError("conditional validation tasks required")
        episodes = []
        for task in train_tasks:
            support = dataset.usable(task.task_id, "support")
            query = dataset.usable(task.task_id, "query")
            if not support or not query:
                raise ContractError("conditional train task requires support/query")
            sx, sy = normalizer.arrays(support)
            qx, qy = normalizer.arrays(query)
            vector = context_vectors[task.task_id]
            episodes.append(maml.TaskEpisode(
                _append_context(sx, vector), sy, _append_context(qx, vector), qy,
                task.task_id))
        if not episodes:
            raise ContractError("conditional pretraining needs train tasks")
        rng = np.random.default_rng(config.seed)
        parameters = maml.init_parameters(config)
        selector = ValidationSelector(policy)
        selector.observe(0, self._validation_score(
            dataset, parameters, config=config, normalizer=normalizer,
            context_vectors=context_vectors), parameters)
        history = []
        stop_reason = "MAX_STEPS"
        step = 0
        for step in range(1, policy.max_steps + 1):
            indices = rng.integers(0, len(episodes), size=config.tasks_per_batch)
            parameters, stats = maml.meta_train_step(
                parameters, [episodes[int(i)] for i in indices], config)
            history.append({"step": step, "loss": float(stats["outer_loss"])})
            if step % policy.interval == 0 or step == policy.max_steps:
                stop = selector.observe(step, self._validation_score(
                    dataset, parameters, config=config, normalizer=normalizer,
                    context_vectors=context_vectors), parameters)
                if stop:
                    stop_reason = "VALIDATION_PATIENCE"
                    break
        return {
            "scope": "SOFTWARE_FIXTURE_CONDITIONAL_ONLY",
            "pretraining_kind": "CONDITIONAL_FEATURE_FIXTURE_NOT_PHYSICS",
            "feature_layout": "12D normalized design + 4 affine task-context features",
            "feature_spec": asdict(feature_spec),
            "real_meta_training_executed": False,
            "physical_solver_starts_actual": 0,
            "admitted_real_labels": 0,
            "test_used_for_selection": False,
            "normalizer": normalizer,
            "config": config,
            "parameters": selector.best.copy(),
            "context_features": {task_id: vector.tolist()
                                 for task_id, vector in context_vectors.items()},
            "context_sha256": canonical_sha(
                {task_id: vector.tolist() for task_id, vector in context_vectors.items()}),
            "train_task_ids": tuple(t.task_id for t in train_tasks),
            "validation_task_ids": tuple(t.task_id for t in validation_tasks),
            "report": {
                "steps_executed": step,
                "best_step": selector.best_step,
                "best_validation_mse_di_n2": selector.best_score,
                "stop_reason": stop_reason,
                "validation_history": selector.history,
                "training_history": history,
                "validation_policy": {
                    "max_steps": policy.max_steps,
                    "interval": policy.interval,
                    "patience": policy.patience,
                    "min_delta": policy.min_delta,
                },
            },
        }

    def _validation_score(self, dataset, parameters, *, config, normalizer,
                          context_vectors) -> float:
        from ...meta_learning import maml
        tasks = [t for t in dataset.tasks if t.split == "val"]
        if not tasks:
            raise ContractError("conditional validation tasks required")
        scores = []
        for task in tasks:
            support = dataset.usable(task.task_id, "support")
            query = dataset.usable(task.task_id, "query")
            if not support or not query:
                raise ContractError("conditional validation task requires support/query")
            sx, sy = normalizer.arrays(support)
            qx, _ = normalizer.arrays(query)
            vector = context_vectors[task.task_id]
            episode = maml.TaskEpisode(_append_context(sx, vector), sy,
                                       _append_context(sx[:1], vector),
                                       np.zeros((1, 1)), "support_only")
            adapted, _ = maml.inner_adapt(parameters, episode, config)
            prediction = _forward(adapted, _append_context(qx, vector))[:, 0]
            target = np.asarray([r.di_n for r in query], dtype=np.float64)
            score = float(np.mean((prediction - target) ** 2))
            if not math.isfinite(score) or score < 0:
                raise ContractError("nonfinite conditional validation score")
            scores.append(score)
        return float(np.mean(scores))


class ConditionalAdaptationRunner:
    """Support-only K-shot adaptation for the 16D conditional fixture model."""

    def predict(self, parameters, *, config, normalizer: TrainNormalizer,
                support_rows: tuple, query_designs: np.ndarray,
                task: TaskSpec, context: TaskContext,
                feature_spec: ConditionalFeatureSpec) -> np.ndarray:
        query = np.asarray(query_designs, dtype=np.float64)
        if (query.ndim != 2 or query.shape[1] != 12 or not len(query)
                or not np.isfinite(query).all()):
            raise ContractError("query designs must be nonempty finite (N,12)")
        if config.input_dim != 16 or config.output_dim != 1:
            raise ContractError("conditional adaptation requires 16D/Di_N model")
        if not isinstance(task, TaskSpec):
            raise ContractError("conditional adaptation requires TaskSpec")
        vector = context_features(task, context, feature_spec)
        support_designs = None
        if support_rows:
            if any(r.source_kind != "synthetic_fixture" for r in support_rows):
                raise ContractError("software adaptation rejects real/declared-real data")
            if any(r.status != "ok" or r.partition != "support" for r in support_rows):
                raise ContractError("adaptation accepts only successful support rows")
            if any(r.task_id != task.task_id for r in support_rows):
                raise ContractError("adaptation support must match the supplied task")
            if len({r.observation_id for r in support_rows}) != len(support_rows):
                raise ContractError("duplicate adaptation observation identity")
            support_designs = np.asarray([r.design for r in support_rows], dtype=np.float64)
            for index, design in enumerate(support_designs):
                if any(np.max(np.abs(design - prior)) <= 1e-12
                       for prior in support_designs[:index]):
                    raise ContractError("duplicate adaptation support design")
                if np.any(np.max(np.abs(query - design), axis=1) <= 1e-12):
                    raise ContractError("adaptation support/query design leakage")
            from ...meta_learning import maml
            support_x, support_y = normalizer.arrays(support_rows)
            episode = maml.TaskEpisode(_append_context(support_x, vector), support_y,
                                       _append_context(support_x[:1], vector),
                                       np.zeros((1, 1)), "support_only")
            parameters, _ = maml.inner_adapt(parameters, episode, config)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            normalized_query = (query - normalizer.x_mean) / normalizer.x_scale
            prediction = _forward(parameters, _append_context(normalized_query, vector))[:, 0]
            output = prediction * normalizer.y_scale + normalizer.y_mean
        if not np.isfinite(output).all():
            raise ContractError("nonfinite conditional adaptation prediction")
        return output


class WarmStartSampler:
    def select(self, candidates: np.ndarray, predictions: np.ndarray, count: int,
               *, evaluated_designs: np.ndarray | None = None) -> np.ndarray:
        """Rank unique designs excluding supplied evaluations (including failures).

        The caller must supply ALL previously evaluated designs for the current task;
        this software helper cannot infer the physical ledger or certify a budget.
        """
        candidates = np.asarray(candidates, dtype=np.float64)
        predictions = np.asarray(predictions, dtype=np.float64)
        if (candidates.ndim != 2 or candidates.shape[1] != 12
                or predictions.shape != (len(candidates),)
                or not np.isfinite(candidates).all() or not np.isfinite(predictions).all()):
            raise ContractError("invalid candidates or predictions")
        if type(count) is not int or count <= 0:
            raise ContractError("count must be a positive integer")
        evaluated = (np.empty((0, 12), dtype=np.float64) if evaluated_designs is None
                     else np.asarray(evaluated_designs, dtype=np.float64))
        if evaluated.ndim != 2 or evaluated.shape[1] != 12 or not np.isfinite(evaluated).all():
            raise ContractError("evaluated designs must be finite (N,12)")
        selected = []
        for index in np.argsort(predictions, kind="stable"):
            design = candidates[index]
            if np.any(np.max(np.abs(evaluated - design), axis=1) <= 1e-12):
                continue
            if not any(np.max(np.abs(design - prior)) <= 1e-12 for prior in selected):
                selected.append(design.copy())
                if len(selected) == count:
                    return np.asarray(selected)
        raise ContractError("not enough unique warm-start candidates")
