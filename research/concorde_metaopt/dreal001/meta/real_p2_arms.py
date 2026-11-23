"""Four real-data arms for the P2 K-shot comparison (Issue #14).

Scope discipline:
- every "real" call requires admitted certificates (MetaDataset.require_real_admission);
- test partitions are read ONLY for the final evaluation, never for selection;
- normalization statistics come from train rows only (TrainNormalizer.fit);
- K=5 is refused here because the frozen support slots are d00-d03 only;
- no physical solver is invoked by this module.

Arms:
  RANDOM_INIT        : freshly initialised 12D model, K-shot adaptation
  POOLED_PRETRAIN    : ordinary joint supervised pretraining on pooled train labels
  TASK_COND_PRETRAIN : 16D model, 12D design + 4 frozen affine task-context features
  FOMAML             : 12D first-order MAML on train tasks
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .meta_dataset import MetaDataset, TrainNormalizer
from .production import ConditionalFeatureSpec, TaskContext, _append_context, context_features
from .task_spec import ContractError

ARM_NAMES = ("RANDOM_INIT", "POOLED_PRETRAIN", "TASK_COND_PRETRAIN", "FOMAML")
FROZEN_SUPPORT_SLOTS = 4          # d00..d03; K=5 has no frozen independent slot
ELIGIBLE_K = (1, 3)


def _maml():
    from ...meta_learning import maml
    return maml


@dataclass(frozen=True)
class ArmConfig:
    """Frozen per-arm training configuration (identical budgets where possible)."""

    hidden_sizes: tuple[int, ...] = (32, 32)
    inner_lr: float = 0.05
    inner_steps: int = 5
    outer_lr: float = 0.01
    tasks_per_batch: int = 2
    max_steps: int = 60
    seed: int = 7

    def __post_init__(self) -> None:
        if not self.hidden_sizes or any(type(v) is not int or v <= 0 for v in self.hidden_sizes):
            raise ContractError("hidden_sizes must be positive ints")
        for name in ("inner_lr", "outer_lr"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ContractError(name + " must be finite and positive")
        if type(self.inner_steps) is not int or self.inner_steps < 0:
            raise ContractError("inner_steps must be a nonnegative int")
        if type(self.tasks_per_batch) is not int or self.tasks_per_batch <= 0:
            raise ContractError("tasks_per_batch must be a positive int")
        if type(self.max_steps) is not int or not 1 <= self.max_steps <= 500:
            raise ContractError("max_steps must be 1..500")
        if type(self.seed) is not int:
            raise ContractError("seed must be an int")


def require_k(k: int) -> None:
    if type(k) is not int:
        raise ContractError("K must be an int")
    if k == 5:
        raise ContractError(
            "K=5 NOT_ELIGIBLE: the frozen protocol only has four independent support "
            "slots (d00-d03); query rows may not be borrowed as support")
    if k not in ELIGIBLE_K:
        raise ContractError("P2 evaluates K=1 and K=3 only")


def _config(input_dim: int, cfg: ArmConfig):
    maml = _maml()
    return maml.MAMLConfig(
        input_dim=input_dim, output_dim=1, hidden_sizes=tuple(cfg.hidden_sizes),
        inner_lr=cfg.inner_lr, inner_steps=cfg.inner_steps, outer_lr=cfg.outer_lr,
        tasks_per_batch=cfg.tasks_per_batch, first_order=True, seed=cfg.seed,
        backend="torch", head_only=False)


def _support_slice(dataset: MetaDataset, task_id: str, k: int) -> tuple:
    rows = sorted(dataset.usable(task_id, "support"), key=lambda r: r.observation_id)
    if len(rows) < k:
        raise ContractError("task %s has %d support rows but K=%d"
                            % (task_id, len(rows), k))
    return tuple(rows[:k])


def _predict(parameters, normalizer: TrainNormalizer, query_rows: tuple) -> np.ndarray:
    maml = _maml()
    x, _ = normalizer.arrays(query_rows)
    value = x
    for index in range(0, len(parameters.tensors), 2):
        value = value @ parameters.tensors[index] + parameters.tensors[index + 1]
        if index + 2 < len(parameters.tensors):
            value = np.tanh(value)
    output = value[:, 0] * normalizer.y_scale + normalizer.y_mean
    if not np.isfinite(output).all():
        raise ContractError("nonfinite arm prediction")
    return output


def _adapt(parameters, normalizer, support_rows, config):
    maml = _maml()
    sx, sy = normalizer.arrays(support_rows)
    episode = maml.TaskEpisode(sx, sy, sx[:1], np.zeros((1, 1)), "support_only")
    adapted, _ = maml.inner_adapt(parameters, episode, config)
    return adapted


def task_errors(dataset: MetaDataset, parameters, config, normalizer, *,
                task_ids, k: int, contexts=None) -> list[dict]:
    """Adapt on K support rows and score the independent query rows (in N)."""
    require_k(k)
    results = []
    for task_id in task_ids:
        support = _support_slice(dataset, task_id, k)
        query = sorted(dataset.usable(task_id, "query"), key=lambda r: r.observation_id)
        if not query:
            raise ContractError("task %s has no independent query rows" % task_id)
        if contexts is None:
            adapted = _adapt(parameters, normalizer, support, config)
            prediction = _predict(adapted, normalizer, query)
        else:
            vector = contexts[task_id]
            maml = _maml()
            sx, sy = normalizer.arrays(support)
            qx, _ = normalizer.arrays(query)
            episode = maml.TaskEpisode(_append_context(sx, vector), sy,
                                       _append_context(sx[:1], vector),
                                       np.zeros((1, 1)), "support_only")
            adapted, _ = maml.inner_adapt(parameters, episode, config)
            value = _append_context(qx, vector)
            for index in range(0, len(adapted.tensors), 2):
                value = value @ adapted.tensors[index] + adapted.tensors[index + 1]
                if index + 2 < len(adapted.tensors):
                    value = np.tanh(value)
            prediction = value[:, 0] * normalizer.y_scale + normalizer.y_mean
        target = np.asarray([row.di_n for row in query], dtype=np.float64)
        error = prediction - target
        results.append({
            "task_id": task_id, "k": k, "n_query": int(len(query)),
            "mae_n": float(np.mean(np.abs(error))),
            "rmse_n": float(np.sqrt(np.mean(error ** 2))),
            "predictions": [float(v) for v in prediction],
            "targets": [float(v) for v in target],
            "query_observation_ids": [row.observation_id for row in query],
            "support_observation_ids": [row.observation_id for row in support],
        })
    return results


def validation_score(dataset: MetaDataset, parameters, config, normalizer, *,
                     k: int, contexts=None) -> float:
    tasks = [t.task_id for t in dataset.tasks if t.split == "val"]
    if not tasks:
        raise ContractError("validation tasks required for arm selection")
    rows = task_errors(dataset, parameters, config, normalizer,
                       task_ids=tasks, k=k, contexts=contexts)
    return float(np.mean([r["mae_n"] for r in rows]))


def _train_pooled(dataset, config, max_steps, normalizer):
    """Ordinary joint pretraining on pooled train labels (no task conditioning)."""
    import torch
    maml = _maml()
    params = maml.init_parameters(config)
    tensors = [torch.tensor(v, dtype=torch.float64, requires_grad=True)
               for v in params.tensors]
    train_ids = {t.task_id for t in dataset.tasks if t.split == "train"}
    rows = tuple(r for r in dataset.rows if r.task_id in train_ids and r.status == "ok")
    x, y = normalizer.arrays(rows)
    tx, ty = torch.tensor(x, dtype=torch.float64), torch.tensor(y, dtype=torch.float64)
    history, best, best_params, best_step = [], None, None, None
    for step in range(max_steps):
        value = tx
        for index in range(0, len(tensors), 2):
            value = value @ tensors[index] + tensors[index + 1]
            if index + 2 < len(tensors):
                value = torch.tanh(value)
        loss = torch.mean((value - ty) ** 2)
        grads = torch.autograd.grad(loss, tensors)
        if not torch.isfinite(loss) or not all(torch.isfinite(g).all() for g in grads):
            raise ContractError("nonfinite pooled pretraining")
        tensors = [(v - config.outer_lr * g).detach().requires_grad_(True)
                   for v, g in zip(tensors, grads)]
        params_now = maml.ParameterSet([v.detach().numpy().copy() for v in tensors])
        score = validation_score(dataset, params_now, config, normalizer, k=1)
        history.append({"step": step + 1, "train_loss": float(loss.detach()),
                        "val_k1_mae_n": score})
        if best is None or score < best:
            best, best_params, best_step = score, params_now, step + 1
    return {"parameters": best_params, "best_step": best_step,
            "best_val_k1_mae_n": best, "history": history}


def _train_fomaml(dataset, config, max_steps, normalizer, k):
    maml = _maml()
    train_tasks = [t.task_id for t in dataset.tasks if t.split == "train"]
    episodes = []
    for task_id in train_tasks:
        support = _support_slice(dataset, task_id, k)
        query = sorted(dataset.usable(task_id, "query"), key=lambda r: r.observation_id)
        if not query:
            raise ContractError("train task needs query rows for meta-training: " + task_id)
        sx, sy = normalizer.arrays(support)
        qx, qy = normalizer.arrays(query)
        episodes.append(maml.TaskEpisode(sx, sy, qx, qy, task_id))
    rng = np.random.default_rng(config.seed)
    params = maml.init_parameters(config)
    history = []
    for step in range(max_steps):
        indices = rng.integers(0, len(episodes), size=config.tasks_per_batch)
        params, stats = maml.meta_train_step(
            params, [episodes[int(i)] for i in indices], config)
        history.append({"step": step + 1, "outer_loss": float(stats["outer_loss"])})
    return {"parameters": params, "history": history}


def _train_conditional(dataset, config, max_steps, normalizer, contexts, k):
    maml = _maml()
    train_tasks = [t.task_id for t in dataset.tasks if t.split == "train"]
    episodes = []
    for task_id in train_tasks:
        support = _support_slice(dataset, task_id, k)
        query = sorted(dataset.usable(task_id, "query"), key=lambda r: r.observation_id)
        if not query:
            raise ContractError("train task needs query rows for conditional pretraining")
        sx, sy = normalizer.arrays(support)
        qx, qy = normalizer.arrays(query)
        vector = contexts[task_id]
        episodes.append(maml.TaskEpisode(_append_context(sx, vector), sy,
                                         _append_context(qx, vector), qy, task_id))
    rng = np.random.default_rng(config.seed)
    params = maml.init_parameters(config)
    history = []
    for step in range(max_steps):
        indices = rng.integers(0, len(episodes), size=config.tasks_per_batch)
        params, stats = maml.meta_train_step(
            params, [episodes[int(i)] for i in indices], config)
        history.append({"step": step + 1, "outer_loss": float(stats["outer_loss"])})
    return {"parameters": params, "history": history}


def build_contexts(dataset: MetaDataset) -> tuple[dict, dict]:
    """Frozen task-context definition: 4 affine features from TaskSpec only.

    cl_target uses the reference Sref 358.25 m^2 for every task; it is a task
    covariate, not a per-design lift target, and never reads labels.
    """
    spec = ConditionalFeatureSpec(mach_reference=2.0, mach_scale=0.4,
                                  q_reference=20000.0, cl_reference=0.2,
                                  cl_scale=0.2, altitude_reference=18288.0)
    contexts, features = {}, {}
    for task in dataset.tasks:
        cl_target = task.lift_target_n / (task.dynamic_pressure_pa * 358.25)
        context = TaskContext(cl_target=cl_target)
        contexts[task.task_id] = context
        features[task.task_id] = context_features(task, context, spec)
    return contexts, features


def run_arms(dataset: MetaDataset, *, config: ArmConfig, k: int,
             mode: str = "real", eval_splits=("val", "test"),
             feature_spec: ConditionalFeatureSpec | None = None) -> dict:
    """Train all four arms for one (seed, K) and score the eval splits once."""
    require_k(k)
    if mode == "real":
        dataset.require_real_admission()
    elif mode != "software_fixture":
        raise ContractError("unsupported execution mode")
    else:
        dataset.require_software_fixture()
    normalizer = TrainNormalizer.fit(dataset)
    eval_tasks = [t.task_id for t in dataset.tasks if t.split in eval_splits]
    if not eval_tasks:
        raise ContractError("no evaluation tasks in requested splits")
    contexts, feature_vectors = build_contexts(dataset)
    if feature_spec is None:
        feature_spec = ConditionalFeatureSpec(
            mach_reference=2.0, mach_scale=0.4, q_reference=20000.0,
            cl_reference=0.2, cl_scale=0.2, altitude_reference=18288.0)
    config12 = _config(12, config)
    config16 = _config(16, config)

    random_params = _maml().init_parameters(config12, seed=config.seed)
    pooled = _train_pooled(dataset, config12, config.max_steps, normalizer)
    conditional = _train_conditional(dataset, config16, config.max_steps,
                                     normalizer, feature_vectors, k)
    fomaml = _train_fomaml(dataset, config12, config.max_steps, normalizer, k)

    arms = {
        "RANDOM_INIT": {"parameters": random_params, "history": []},
        "POOLED_PRETRAIN": pooled,
        "TASK_COND_PRETRAIN": conditional,
        "FOMAML": fomaml,
    }
    scores = {}
    for name, payload in arms.items():
        if name == "TASK_COND_PRETRAIN":
            rows = task_errors(dataset, payload["parameters"], config16, normalizer,
                               task_ids=eval_tasks, k=k, contexts=feature_vectors)
        else:
            rows = task_errors(dataset, payload["parameters"], config12, normalizer,
                               task_ids=eval_tasks, k=k)
        scores[name] = rows
    return {
        "scope": ("REAL_META_TRAINING_EXECUTED" if mode == "real"
                  else "SOFTWARE_FIXTURE_TRAINING_ONLY"),
        "arms": list(ARM_NAMES), "k": k, "seed": config.seed,
        "normalizer": normalizer, "config": config,
        "contexts": {task_id: {"cl_target": ctx.cl_target}
                     for task_id, ctx in contexts.items()},
        "feature_spec": feature_spec, "scores": scores,
        "histories": {name: payload["history"] for name, payload in arms.items()},
        "attention": {
            "train_observation_ids": normalizer.fit_observation_ids,
            "test_used_for_selection": False,
            "selection_documents": "fixed frozen hyperparameters; no test-time selection",
        },
    }
