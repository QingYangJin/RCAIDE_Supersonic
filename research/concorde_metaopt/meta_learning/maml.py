"""一阶 MAML（FOMAML）核心与有限差分梯度门禁（§5.4 / §7 / §7.2）。

实现说明：
- 主后端为 torch（float64 CPU，确定性 seed）；一阶近似采用"适配后参数上的
  查询梯度"作为初始参数的梯度，不回传内循环二阶图（§7 一阶 MAML）。
- 本模块是 §7.1 允许的"自写 numpy/torch 核心"，字段与 §5.4 兼容，
  但 equivalence_claimed=false（不与 maml-opt 实现声称数值等价）。
- 不做任何物理调用。
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np

try:  # torch 缺失时相关测试应标 NOT_RUN，不得假装通过
    import torch

    _TORCH_AVAILABLE = True
    _TORCH_IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover - 环境异常路径
    torch = None  # type: ignore[assignment]
    _TORCH_AVAILABLE = False
    _TORCH_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

import os as _os

_TORCH_NUM_THREADS = max(1, min(4, _os.cpu_count() or 1))
SUPPORTED_BACKENDS = ("torch",)
FD_DEFAULT_EPSILON = 1e-5
FD_DEFAULT_TOLERANCE = 1e-4
FD_MAX_COMPONENTS = 5
FD_MIN_COMPONENTS = 3


class MAMLError(RuntimeError):
    """MAML 配置/训练/梯度门禁错误。"""


def torch_available() -> bool:
    """torch 是否可用（不可用时相关测试标 NOT_RUN）。"""
    return _TORCH_AVAILABLE


def torch_import_error() -> str | None:
    """torch 导入错误信息；可用时为 None。"""
    return _TORCH_IMPORT_ERROR


def _require_torch() -> None:
    if not _TORCH_AVAILABLE:
        raise MAMLError(
            "torch 不可用，MAML 主后端无法运行；相关测试应标记 NOT_RUN: " + str(_TORCH_IMPORT_ERROR)
        )
    torch.set_num_threads(_TORCH_NUM_THREADS)


@dataclass(frozen=True)
class MAMLConfig:
    """MAML 超参数（§5.4 字段冻结）。"""

    input_dim: int
    output_dim: int
    hidden_sizes: tuple[int, ...] = (64, 64)
    inner_lr: float = 0.01
    inner_steps: int = 5
    outer_lr: float = 1e-3
    tasks_per_batch: int = 8
    first_order: bool = True
    seed: int = 42
    backend: str = "torch"

    def __post_init__(self) -> None:
        if type(self.input_dim) is not int or self.input_dim <= 0:
            raise MAMLError("input_dim 必须是正整数")
        if type(self.output_dim) is not int or self.output_dim <= 0:
            raise MAMLError("output_dim 必须是正整数")
        hidden = tuple(self.hidden_sizes)
        if not hidden or any(type(size) is not int or size <= 0 for size in hidden):
            raise MAMLError("hidden_sizes 必须是非空正整数元组")
        object.__setattr__(self, "hidden_sizes", hidden)
        for name in ("inner_lr", "outer_lr"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise MAMLError(f"{name} 必须为正有限数")
        if type(self.inner_steps) is not int or self.inner_steps < 0:
            raise MAMLError("inner_steps 必须是非负整数")
        if type(self.tasks_per_batch) is not int or self.tasks_per_batch <= 0:
            raise MAMLError("tasks_per_batch 必须是正整数")
        if type(self.first_order) is not bool:
            raise MAMLError("first_order 必须是 bool")
        if type(self.seed) is not int:
            raise MAMLError("seed 必须是 int")
        if self.backend not in SUPPORTED_BACKENDS:
            raise MAMLError(f"backend 只支持 {SUPPORTED_BACKENDS}，实际 {self.backend!r}")

    @property
    def layer_sizes(self) -> tuple[int, ...]:
        """网络每层宽度（含输入/输出层）。"""
        return (self.input_dim, *self.hidden_sizes, self.output_dim)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_dim": self.input_dim,
            "output_dim": self.output_dim,
            "hidden_sizes": list(self.hidden_sizes),
            "inner_lr": self.inner_lr,
            "inner_steps": self.inner_steps,
            "outer_lr": self.outer_lr,
            "tasks_per_batch": self.tasks_per_batch,
            "first_order": self.first_order,
            "seed": self.seed,
            "backend": self.backend,
        }


@dataclass(frozen=True)
class ParameterSet:
    """参数字典（numpy float64 数组列表）；列表顺序 = 层权重/偏置交替。"""

    tensors: list[np.ndarray]

    def __post_init__(self) -> None:
        tensors = [np.asarray(tensor, dtype=np.float64) for tensor in self.tensors]
        if not tensors:
            raise MAMLError("ParameterSet 不能为空")
        for index, tensor in enumerate(tensors):
            if tensor.ndim not in (1, 2):
                raise MAMLError(f"第 {index} 个参数维度必须是 1 或 2，实际 {tensor.ndim}")
            if not np.all(np.isfinite(tensor)):
                raise MAMLError(f"第 {index} 个参数包含非有限值")
        object.__setattr__(self, "tensors", tensors)

    @property
    def names(self) -> tuple[str, ...]:
        """参数名：layer_{i}_weight / layer_{i}_bias（按张量维数推断）。"""
        names: list[str] = []
        layer = 0
        for tensor in self.tensors:
            if tensor.ndim == 2:
                names.append(f"layer_{layer}_weight")
            else:
                names.append(f"layer_{layer}_bias")
                layer += 1
        return tuple(names)

    def copy(self) -> "ParameterSet":
        return ParameterSet([tensor.copy() for tensor in self.tensors])

    def to_dict(self) -> dict[str, Any]:
        return {
            "names": list(self.names),
            "tensors": [tensor.tolist() for tensor in self.tensors],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ParameterSet":
        if "tensors" not in payload:
            raise MAMLError("ParameterSet.from_dict 缺少 tensors")
        return cls([np.asarray(tensor, dtype=np.float64) for tensor in payload["tensors"]])


@dataclass(frozen=True)
class TaskEpisode:
    """单个任务的 support/query 张量（features 已是代理输入特征）。"""

    support_features: np.ndarray
    support_targets: np.ndarray
    query_features: np.ndarray
    query_targets: np.ndarray
    task_id: str = ""

    def __post_init__(self) -> None:
        support_x = _as_feature_matrix(self.support_features, "support_features")
        query_x = _as_feature_matrix(self.query_features, "query_features")
        if support_x.shape[1] != query_x.shape[1]:
            raise MAMLError("support/query 特征维度不一致")
        support_y = _as_target_matrix(self.support_targets, "support_targets")
        query_y = _as_target_matrix(self.query_targets, "query_targets")
        if support_y.shape[1] != query_y.shape[1]:
            raise MAMLError("support/query 标签维度不一致")
        if support_x.shape[0] != support_y.shape[0]:
            raise MAMLError("support 特征/标签行数不一致")
        if query_x.shape[0] != query_y.shape[0]:
            raise MAMLError("query 特征/标签行数不一致")
        object.__setattr__(self, "support_features", support_x)
        object.__setattr__(self, "support_targets", support_y)
        object.__setattr__(self, "query_features", query_x)
        object.__setattr__(self, "query_targets", query_y)
        object.__setattr__(self, "task_id", str(self.task_id))


def _as_feature_matrix(values: Any, label: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim == 1:
        matrix = matrix[None, :]
    if matrix.ndim != 2:
        raise MAMLError(f"{label} 必须为二维数组，实际 {matrix.shape}")
    if matrix.shape[0] == 0:
        raise MAMLError(f"{label} 不能为空")
    if not np.all(np.isfinite(matrix)):
        raise MAMLError(f"{label} 包含非有限值")
    return matrix


def _as_target_matrix(values: Any, label: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim == 1:
        matrix = matrix[:, None]
    if matrix.ndim != 2:
        raise MAMLError(f"{label} 必须为一维/二维数组，实际 {matrix.shape}")
    if matrix.shape[0] == 0:
        raise MAMLError(f"{label} 不能为空")
    if not np.all(np.isfinite(matrix)):
        raise MAMLError(f"{label} 包含非有限值")
    return matrix


def _as_episode(value: Any) -> TaskEpisode:
    if isinstance(value, TaskEpisode):
        return value
    if isinstance(value, Mapping):
        return TaskEpisode(
            support_features=value["support_features"],
            support_targets=value["support_targets"],
            query_features=value["query_features"],
            query_targets=value["query_targets"],
            task_id=str(value.get("task_id", "")),
        )
    if isinstance(value, (tuple, list)) and len(value) == 4:
        return TaskEpisode(*value)
    raise MAMLError(f"无法把 {type(value).__name__} 转成 TaskEpisode")


def _episode_batch(batch: Sequence[Any]) -> list[TaskEpisode]:
    if not batch:
        raise MAMLError("episode batch 不能为空")
    return [_as_episode(episode) for episode in batch]


# -- 参数初始化 -------------------------------------------------------------


def init_parameters(config: MAMLConfig, seed: int | None = None) -> ParameterSet:
    """确定性初始化 MLP 参数（Xavier uniform；同 seed 逐位复现）。"""
    if not isinstance(config, MAMLConfig):
        raise MAMLError("init_parameters 需要 MAMLConfig")
    actual_seed = config.seed if seed is None else int(seed)
    rng = np.random.default_rng(actual_seed)
    tensors: list[np.ndarray] = []
    for fan_in, fan_out in zip(config.layer_sizes[:-1], config.layer_sizes[1:]):
        limit = math.sqrt(6.0 / (fan_in + fan_out))
        tensors.append(rng.uniform(-limit, limit, size=(fan_in, fan_out)))
        tensors.append(np.zeros(fan_out, dtype=np.float64))
    return ParameterSet(tensors)


def _to_torch(tensors: list[np.ndarray], requires_grad: bool = True) -> list[Any]:
    _require_torch()
    return [
        torch.tensor(tensor, dtype=torch.float64, requires_grad=requires_grad) for tensor in tensors
    ]


def _forward_torch(tensors: list[Any], features: Any) -> Any:
    current = features
    n_layers = len(tensors) // 2
    for layer in range(n_layers):
        current = current @ tensors[2 * layer] + tensors[2 * layer + 1]
        if layer < n_layers - 1:
            current = torch.tanh(current)
    return current


def _mse_torch(prediction: Any, target: Any) -> Any:
    return torch.mean((prediction - target) ** 2)


def _inner_adapt_torch(
    tensors: list[Any], support_features: Any, support_targets: Any, config: MAMLConfig
) -> tuple[list[Any], list[float]]:
    losses: list[float] = []
    if config.inner_steps == 0:
        return tensors, losses
    for _ in range(config.inner_steps):
        prediction = _forward_torch(tensors, support_features)
        loss = _mse_torch(prediction, support_targets)
        grads = torch.autograd.grad(loss, tensors, create_graph=False)
        losses.append(float(loss.detach().item()))
        for tensor, grad in zip(tensors, grads):
            tensor.data = tensor.data - config.inner_lr * grad.detach()
    return tensors, losses


def _inner_adapt_episodes(
    parameters: ParameterSet, episodes: Sequence[TaskEpisode], config: MAMLConfig
) -> tuple[list[ParameterSet], list[float], list[float]]:
    """对每个任务独立做内循环适配；返回 (适配后参数, 首步 support loss, 末步 support loss)。"""
    _require_torch()
    adapted_sets: list[ParameterSet] = []
    firsts: list[float] = []
    lasts: list[float] = []
    for episode in episodes:
        support_x = torch.tensor(episode.support_features, dtype=torch.float64)
        support_y = torch.tensor(episode.support_targets, dtype=torch.float64)
        tensors = _to_torch(parameters.tensors, requires_grad=True)
        first_inner_loss: float | None = None
        for _ in range(config.inner_steps):
            prediction = _forward_torch(tensors, support_x)
            loss = _mse_torch(prediction, support_y)
            if first_inner_loss is None:
                first_inner_loss = float(loss.detach().item())
            grads = torch.autograd.grad(loss, tensors, create_graph=False)
            with torch.no_grad():
                for tensor, grad in zip(tensors, grads):
                    tensor.data = tensor.data - config.inner_lr * grad.detach()
        if first_inner_loss is not None:
            firsts.append(first_inner_loss)
        with torch.no_grad():
            lasts.append(float(_mse_torch(_forward_torch(tensors, support_x), support_y).item()))
        adapted_sets.append(ParameterSet([tensor.detach().numpy().copy() for tensor in tensors]))
    return adapted_sets, firsts, lasts


def _query_loss_per_task(
    adapted_sets: Sequence[ParameterSet], episodes: Sequence[TaskEpisode]
) -> list[float]:
    """在给定（适配后）参数点上计算每个任务的 query MSE（不回传内循环）。"""
    _require_torch()
    losses: list[float] = []
    for adapted, episode in zip(adapted_sets, episodes):
        tensors = _to_torch(adapted.tensors, requires_grad=False)
        query_x = torch.tensor(episode.query_features, dtype=torch.float64)
        query_y = torch.tensor(episode.query_targets, dtype=torch.float64)
        with torch.no_grad():
            losses.append(float(_mse_torch(_forward_torch(tensors, query_x), query_y).item()))
    return losses


def _fomaml_outer_gradient(
    adapted_sets: Sequence[ParameterSet], episodes: Sequence[TaskEpisode]
) -> tuple[float, list[np.ndarray]]:
    """一阶 MAML 外循环梯度：适配后参数点上 query 损失梯度的任务平均（detach）。

    FOMAML 梯度定义为 g = mean_t ∂L_q(θ'_t)/∂θ'_t；meta_train_step 把该梯度当作
    初始参数梯度的一阶近似（不回传内循环二阶项）。FD 门禁即校验该定义。
    """
    _require_torch()
    total_grads: list[Any] = []
    total_loss = 0.0
    for adapted, episode in zip(adapted_sets, episodes):
        tensors = _to_torch(adapted.tensors, requires_grad=True)
        query_x = torch.tensor(episode.query_features, dtype=torch.float64)
        query_y = torch.tensor(episode.query_targets, dtype=torch.float64)
        query_loss = _mse_torch(_forward_torch(tensors, query_x), query_y)
        total_loss += float(query_loss.detach().item())
        grads = torch.autograd.grad(query_loss, tensors, create_graph=False)
        if not total_grads:
            total_grads = [grad.detach() for grad in grads]
        else:
            total_grads = [acc + grad.detach() for acc, grad in zip(total_grads, grads)]
    divisor = float(len(episodes))
    grads_np = [np.asarray((grad / divisor).numpy(), dtype=np.float64) for grad in total_grads]
    return total_loss / divisor, grads_np


def _outer_loss_at_adapted(
    adapted_sets: Sequence[ParameterSet], episodes: Sequence[TaskEpisode]
) -> float:
    """给定（适配后）参数点上的 query 平均损失；FD 数值差分使用同一函数。"""
    return float(np.mean(_query_loss_per_task(adapted_sets, episodes)))

def inner_adapt(
    params: ParameterSet, support: Any, config: MAMLConfig
) -> tuple[ParameterSet, list[float]]:
    """在 support 上做 inner_steps 步 SGD；返回 (适配后参数, 每步 support loss)。

    losses 长度恒等于 config.inner_steps（§12-7）。
    """
    if not isinstance(params, ParameterSet):
        raise MAMLError("inner_adapt 需要 ParameterSet")
    if not isinstance(config, MAMLConfig):
        raise MAMLError("inner_adapt 需要 MAMLConfig")
    episode = _as_episode(support)
    if episode.support_features.shape[1] != config.input_dim:
        raise MAMLError("support 特征维度与 config.input_dim 不一致")
    _require_torch()
    tensors = _to_torch(params.tensors, requires_grad=True)
    support_x = torch.tensor(episode.support_features, dtype=torch.float64)
    support_y = torch.tensor(episode.support_targets, dtype=torch.float64)
    _, losses = _inner_adapt_torch(tensors, support_x, support_y, config)
    adapted = ParameterSet([tensor.detach().numpy().copy() for tensor in tensors])
    return adapted, losses


def meta_train_step(
    params: ParameterSet, batch: Sequence[Any], config: MAMLConfig
) -> tuple[ParameterSet, dict[str, float]]:
    """一次外循环更新（FOMAML）；返回新参数与统计量。"""
    if not isinstance(params, ParameterSet):
        raise MAMLError("meta_train_step 需要 ParameterSet")
    episodes = _episode_batch(batch)
    adapted_sets, firsts, lasts = _inner_adapt_episodes(params, episodes, config)
    outer_loss, grads = _fomaml_outer_gradient(adapted_sets, episodes)
    new_tensors = [
        tensor - config.outer_lr * grad for tensor, grad in zip(params.tensors, grads)
    ]
    grad_norm = math.sqrt(sum(float(np.sum(grad**2)) for grad in grads))
    stats = {
        "outer_loss": float(outer_loss),
        "grad_norm": float(grad_norm),
        "inner_loss_first": float(np.mean(firsts)) if firsts else float("nan"),
        "inner_loss_last": float(np.mean(lasts)) if lasts else float("nan"),
    }
    if not all(math.isfinite(value) for value in stats.values()):
        raise MAMLError(f"meta_train_step 统计量出现非有限值: {stats}")
    return ParameterSet(new_tensors), stats


def meta_train(
    tasks: Sequence[Any],
    config: MAMLConfig,
    max_steps: int,
) -> dict[str, Any]:
    """元训练主循环：每步从 tasks 采样 tasks_per_batch 个 episode 做一次外循环更新。

    返回 dict 含 status/参数/历史；任何非有限出现即 status=FAILED 并停止
    （不伪造成功）。
    """
    if not isinstance(config, MAMLConfig):
        raise MAMLError("meta_train 需要 MAMLConfig")
    if type(max_steps) is not int or max_steps < 0:
        raise MAMLError("max_steps 必须是非负整数")
    episodes = _episode_batch(tasks)
    rng = np.random.default_rng(config.seed)
    params = init_parameters(config)
    history: list[dict[str, float]] = []
    status = "VALID"
    failure: str | None = None
    steps_done = 0
    if max_steps > 0:
        for step in range(max_steps):
            indices = rng.integers(0, len(episodes), size=config.tasks_per_batch)
            batch = [episodes[int(index)] for index in indices]
            try:
                params, stats = meta_train_step(params, batch, config)
            except MAMLError as exc:
                status = "FAILED"
                failure = f"{type(exc).__name__}: {exc}"
                break
            step_stats = dict(stats)
            step_stats["step"] = float(step)
            history.append(step_stats)
            steps_done += 1
            if not all(math.isfinite(value) for value in stats.values()):
                status = "NONFINITE"
                break
    return {
        "status": status,
        "failure": failure,
        "steps": steps_done,
        "max_steps": max_steps,
        "final_parameters": params.to_dict(),
        "history": history,
        "backend": config.backend,
        "equivalence_claimed": False,
        "seed": config.seed,
        "config": config.to_dict(),
    }


# -- 有限差分梯度门禁（§7.2） ------------------------------------------------


@dataclass(frozen=True)
class MAMLModel:
    """FD 门禁使用的模型快照（参数 + 超参）。"""

    config: MAMLConfig
    parameters: ParameterSet


def build_small_model(seed: int = 42) -> MAMLModel:
    """§7.2 规定的小模型：input_dim=12、output_dim=2、hidden=(8,8)、1 步内循环。"""
    config = MAMLConfig(
        input_dim=12,
        output_dim=2,
        hidden_sizes=(8, 8),
        inner_lr=0.01,
        inner_steps=1,
        outer_lr=1e-3,
        tasks_per_batch=2,
        first_order=True,
        seed=int(seed),
        backend="torch",
    )
    return MAMLModel(config=config, parameters=init_parameters(config))


def _model_config(model: Any) -> tuple[MAMLConfig, ParameterSet]:
    if isinstance(model, MAMLModel):
        return model.config, model.parameters
    if isinstance(model, ParameterSet):
        sizes = []
        for tensor in model.tensors:
            sizes.append(tensor.shape)
        hidden = tuple(int(shape[1]) for shape in sizes[:-2] if len(shape) == 2)
        config = MAMLConfig(
            input_dim=int(sizes[0][0]),
            output_dim=int(sizes[-1][1]),
            hidden_sizes=hidden,
            inner_steps=1,
            tasks_per_batch=1,
        )
        return config, model
    if isinstance(model, Mapping) and "parameters" in model:
        parameters = model["parameters"]
        if isinstance(parameters, Mapping):
            parameters = ParameterSet.from_dict(parameters)
        if not isinstance(parameters, ParameterSet):
            raise MAMLError("model['parameters'] 必须是 ParameterSet")
        config = model.get("config")
        if config is None:
            return _model_config(parameters)
        if isinstance(config, Mapping):
            config = MAMLConfig(**config)
        if not isinstance(config, MAMLConfig):
            raise MAMLError("model['config'] 必须是 MAMLConfig")
        return config, parameters
    raise MAMLError(f"无法识别的 model 类型: {type(model).__name__}")


def _perturb(parameters: ParameterSet, tensor_index: int, flat_index: int, delta: float) -> ParameterSet:
    tensors = [tensor.copy() for tensor in parameters.tensors]
    flat = tensors[tensor_index].reshape(-1)
    flat[flat_index] += delta
    tensors[tensor_index] = flat.reshape(tensors[tensor_index].shape)
    return ParameterSet(tensors)


def finite_difference_gradient_check(
    model: Any,
    batch: Sequence[Any],
    epsilon: float = FD_DEFAULT_EPSILON,
    tolerance: float = FD_DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """中心差分校验 FOMAML 外循环梯度（§7.2，双精度）。

    epsilon=1e-5；相对误差=|g_num-g_ana|/max(1,|g_num|,|g_ana|)；
    tolerance=1e-4；抽查 3–5 个参数分量；FAIL 时 M2 不得启动。
    """
    if not math.isfinite(epsilon) or epsilon <= 0.0:
        raise MAMLError("epsilon 必须为正有限数")
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise MAMLError("tolerance 必须为正有限数")
    config, parameters = _model_config(model)
    if not config.first_order:
        raise MAMLError("finite_difference_gradient_check 仅支持一阶 MAML（first_order=True）")
    episodes = _episode_batch(batch)
    for episode in episodes:
        if episode.support_features.shape[1] != config.input_dim:
            raise MAMLError("batch 特征维度与 config.input_dim 不一致")
        if episode.support_targets.shape[1] != config.output_dim:
            raise MAMLError("batch 标签维度与 config.output_dim 不一致")
    _require_torch()
    adapted_sets, _, _ = _inner_adapt_episodes(parameters, episodes, config)
    outer_loss, analytic_grads = _fomaml_outer_gradient(adapted_sets, episodes)
    candidates: list[tuple[int, int, float]] = []
    for tensor_index, grad in enumerate(analytic_grads):
        flat = grad.reshape(-1)
        for flat_index in range(flat.shape[0]):
            candidates.append((tensor_index, int(flat_index), float(flat[flat_index])))
    if not candidates:
        raise MAMLError("参数梯度全为空，无法做有限差分检查")
    candidates.sort(key=lambda item: (-abs(item[2]), item[0], item[1]))
    if len(candidates) < FD_MIN_COMPONENTS:
        raise MAMLError(
            f"可抽查参数分量仅 {len(candidates)} 个，少于 FD_MIN_COMPONENTS={FD_MIN_COMPONENTS}；"
            "FD 门禁不得在证据不足时判定通过（§7.2）"
        )
    selected = candidates[:FD_MAX_COMPONENTS]
    names = parameters.names
    checks: list[dict[str, Any]] = []
    max_relative_error = 0.0
    status = "PASS"
    for tensor_index, flat_index, analytic in selected:
        # 数值差分在适配后参数点（θ'）上做：FOMAML 把 θ' 当作外循环变量的
        # 一阶替身，因此 L(θ'±εe_j) 不重新适配，与解析梯度定义严格一致。
        plus_sets = [
            _perturb(adapted, tensor_index, flat_index, epsilon) for adapted in adapted_sets
        ]
        minus_sets = [
            _perturb(adapted, tensor_index, flat_index, -epsilon) for adapted in adapted_sets
        ]
        plus = _outer_loss_at_adapted(plus_sets, episodes)
        minus = _outer_loss_at_adapted(minus_sets, episodes)
        numeric = (plus - minus) / (2.0 * epsilon)
        abs_error = abs(numeric - analytic)
        denominator = max(1.0, abs(numeric), abs(analytic))
        relative_error = abs_error / denominator
        max_relative_error = max(max_relative_error, relative_error)
        passed = relative_error <= tolerance
        if not passed:
            status = "FAIL"
        checks.append(
            {
                "parameter_name": names[tensor_index],
                "tensor_index": int(tensor_index),
                "flat_index": int(flat_index),
                "analytic": float(analytic),
                "numeric": float(numeric),
                "abs_error": float(abs_error),
                "relative_error": float(relative_error),
                "epsilon": float(epsilon),
                "tolerance": float(tolerance),
                "status": "PASS" if passed else "FAIL",
            }
        )
    return {
        "status": status,
        "backend": config.backend,
        "equivalence_claimed": False,
        "fd_point": "adapted_parameters",
        "outer_loss": float(outer_loss),
        "epsilon": float(epsilon),
        "tolerance": float(tolerance),
        "n_checked": len(checks),
        "max_relative_error": float(max_relative_error),
        "checks": checks,
    }


def write_finite_difference_check(result: Mapping[str, Any], path: str | Any) -> None:
    """把 FD 结果落盘为 finite_difference_check.json（非有限值写成 null）。"""
    from pathlib import Path

    def _sanitize(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): _sanitize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_sanitize(item) for item in value]
        if isinstance(value, (np.floating, float)):
            number = float(value)
            return number if math.isfinite(number) else None
        if isinstance(value, (np.integer, int)):
            return int(value)
        if isinstance(value, (np.bool_, bool)):
            return bool(value)
        return value

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(_sanitize(result), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "FD_DEFAULT_EPSILON",
    "FD_DEFAULT_TOLERANCE",
    "FD_MAX_COMPONENTS",
    "FD_MIN_COMPONENTS",
    "MAMLConfig",
    "MAMLError",
    "MAMLModel",
    "ParameterSet",
    "SUPPORTED_BACKENDS",
    "TaskEpisode",
    "build_small_model",
    "finite_difference_gradient_check",
    "init_parameters",
    "inner_adapt",
    "meta_train",
    "meta_train_step",
    "torch_available",
    "torch_import_error",
    "write_finite_difference_check",
]
