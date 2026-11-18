"""Bounded fixture-only validation selection. No real admission or test scoring."""
from dataclasses import dataclass
import math
import numpy as np
from .meta_dataset import TrainNormalizer
from .production import AdaptationRunner
from .task_spec import ContractError


@dataclass(frozen=True)
class ValidationPolicy:
    max_steps: int = 40
    interval: int = 5
    patience: int = 3
    min_delta: float = 0.

    def __post_init__(self):
        for name in ("max_steps", "interval", "patience"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ContractError("validation policy requires positive integer counts")
        if self.max_steps > 100 or self.interval > self.max_steps:
            raise ContractError("fixture validation requires interval <= max_steps <= 100")
        if isinstance(self.min_delta, bool) or not math.isfinite(self.min_delta) or self.min_delta < 0:
            raise ContractError("min_delta must be finite and nonnegative")


class ValidationSelector:
    """Separate best and stale counter for one model; strict improvement, ties keep first."""
    def __init__(self, policy):
        self.policy = policy
        self.best_score = math.inf
        self.best_step = None
        self.best = None
        self.stale = 0
        self.history = []

    def observe(self, step, score, parameters):
        if type(step) is not int or step < 0 or (self.history and step <= self.history[-1]["step"]):
            raise ContractError("validation steps must increase")
        if not math.isfinite(score) or score < 0:
            raise ContractError("validation score must be finite and nonnegative")
        improved = score < self.best_score - self.policy.min_delta
        if improved:
            self.best_score, self.best_step, self.best = float(score), step, parameters.copy()
            self.stale = 0
        else:
            self.stale += 1
        self.history.append({"step": step, "query_mse_di_n2": float(score), "improved": improved})
        return self.stale >= self.policy.patience


def validation_score(dataset, parameters, *, config, normalizer):
    """Macro task MSE, validation support only for adaptation; never touch test labels."""
    tasks = [t for t in dataset.tasks if t.split == "val"]
    if not tasks:
        raise ContractError("validation tasks required")
    scores = []
    runner = AdaptationRunner()
    for task in tasks:
        support = dataset.usable(task.task_id, "support")
        query = dataset.usable(task.task_id, "query")
        if not support or not query:
            raise ContractError("validation task requires successful support/query")
        prediction = runner.predict(parameters, config=config, normalizer=normalizer,
                                    support_rows=support, query_designs=np.asarray([r.design for r in query]))
        score = float(np.mean((prediction - np.asarray([r.di_n for r in query])) ** 2))
        if not math.isfinite(score):
            raise ContractError("nonfinite validation score")
        scores.append(score)
    return float(np.mean(scores))


def _pooled_step(parameters, x, y, config):
    import torch
    from ...meta_learning import maml
    tensors = [torch.tensor(t, dtype=torch.float64, requires_grad=True) for t in parameters.tensors]
    value = torch.tensor(x, dtype=torch.float64)
    for index in range(0, len(tensors), 2):
        value = value @ tensors[index] + tensors[index + 1]
        if index + 2 < len(tensors):
            value = torch.tanh(value)
    loss = torch.mean((value - torch.tensor(y, dtype=torch.float64)) ** 2)
    gradients = torch.autograd.grad(loss, tensors)
    if not torch.isfinite(loss) or not all(torch.isfinite(g).all() for g in gradients):
        raise ContractError("nonfinite pooled training")
    return maml.ParameterSet([(v - config.outer_lr * g).detach().numpy().copy()
                              for v, g in zip(tensors, gradients)]), float(loss.detach())


def fit_with_validation(dataset, *, config, policy=ValidationPolicy(), mode="real"):
    if mode == "real":
        dataset.require_real_admission()
    if mode != "software_fixture":
        raise ContractError("unsupported execution mode")
    dataset.require_software_fixture()
    if not isinstance(policy, ValidationPolicy):
        raise ContractError("ValidationPolicy required")
    if config.input_dim != 12 or config.output_dim != 1 or not config.first_order or config.head_only:
        raise ContractError("fixture validation requires 12D FOMAML")
    from ...meta_learning import maml
    if not maml.torch_available():
        raise ContractError("TORCH_NOT_AVAILABLE")
    normalizer = TrainNormalizer.fit(dataset)
    tasks = [t for t in dataset.tasks if t.split == "train"]
    episodes = []
    for task in tasks:
        sx, sy = normalizer.arrays(dataset.usable(task.task_id, "support"))
        qx, qy = normalizer.arrays(dataset.usable(task.task_id, "query"))
        episodes.append(maml.TaskEpisode(sx, sy, qx, qy, task.task_id))
    train_ids = {t.task_id for t in tasks}
    train_rows = tuple(r for r in dataset.rows if r.task_id in train_ids and r.status == "ok")
    x, y = normalizer.arrays(train_rows)
    models, reports = {}, {}
    for name in ("fomaml", "pretrain"):
        rng = np.random.default_rng(config.seed)
        params = maml.init_parameters(config)
        selector = ValidationSelector(policy)
        selector.observe(0, validation_score(dataset, params, config=config, normalizer=normalizer), params)
        training_history = []
        reason = "MAX_STEPS"
        for step in range(1, policy.max_steps + 1):
            if name == "fomaml":
                indices = rng.integers(0, len(episodes), size=config.tasks_per_batch)
                params, stats = maml.meta_train_step(params, [episodes[int(i)] for i in indices], config)
                training_history.append({"step": step, "loss": stats["outer_loss"]})
            else:
                params, loss = _pooled_step(params, x, y, config)
                training_history.append({"step": step, "loss": loss})
            if step % policy.interval == 0 or step == policy.max_steps:
                stop = selector.observe(step, validation_score(dataset, params, config=config, normalizer=normalizer), params)
                if stop:
                    reason = "VALIDATION_PATIENCE"
                    break
        models[name] = selector.best.copy()
        reports[name] = {"steps_executed": step, "best_step": selector.best_step,
                         "best_validation_mse_di_n2": selector.best_score, "stop_reason": reason,
                         "validation_history": selector.history, "training_history": training_history}
    return {"scope": "SOFTWARE_FIXTURE_VALIDATION_ONLY", "real_meta_training_executed": False,
            "physical_solver_starts_actual": 0, "test_used_for_selection": False,
            "normalizer": normalizer, "models": models, "reports": reports,
            "train_task_ids": sorted(train_ids), "validation_task_ids": [t.task_id for t in dataset.tasks if t.split == "val"],
            "pretraining_kind": "POOLED_UNCONDITIONED_FIXTURE_NOT_FORMAL_CONDITIONAL_BASELINE"}
