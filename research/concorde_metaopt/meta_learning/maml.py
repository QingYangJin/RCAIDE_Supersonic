"""MAML 核心（FOMAML 一阶 + FULL_MAML 二阶）与有限差分梯度门禁（§5.4 / §7 / §7.2 / S2 §4）。

实现说明：
- 主后端为 torch（float64 CPU，确定性 seed）；一阶近似采用"适配后参数上的
  查询梯度"作为初始参数的梯度，不回传内循环二阶图（§7 一阶 MAML）。
- 本模块是 §7.1 允许的"自写 numpy/torch 核心"，字段与 §5.4 兼容，
  但 equivalence_claimed=false（不与 maml-opt 实现声称数值等价）。
- 不做任何物理调用。
"""
from __future__ import annotations

import copy
import hashlib
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

# FULL_MAML 二阶元梯度 FD 门禁（S2 计划 §4.3）
FD_MODES = ("fomaml", "full")
FD_FULL_MAX_COORDINATES = 32
FD_FULL_MIN_COORDINATES = 32
FD_FULL_EPSILON_SCALE = 1e-6
FD_FULL_RELATIVE_TOLERANCE = 1e-6
FD_FULL_DENOMINATOR_FLOOR = 1e-12
S2_META_GRAD_FD_FAIL = "S2_META_GRAD_FD_FAIL"

# S3 ANIL 与梯度门禁（S3 计划 §4.4；A5-S3M0 处置）
S3_GATE_SCHEMA_VERSION = "p4ra-s3-gate-1"
S3_GATE_MODES = ("fomaml", "anil")
S3_GATE_EPSILON_SCALE = 1e-6
S3_GATE_RELATIVE_TOLERANCE = 1e-6
S3_GATE_COORDINATES = 32
S3_GATE_DENOMINATOR_FLOOR = 1e-12
S3_GATE_FD_FAIL = "S3_GATE_FD_FAIL"
S3_GATE_ANIL_BODY_FROZEN = "S3_GATE_ANIL_BODY_FROZEN"
S3_GATE_K0_EQUIVALENCE = "S3_GATE_K0_EQUIVALENCE"
S3_GATE_TAMPER_DETECTED = "S3_GATE_TAMPER_DETECTED"


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
    head_only: bool = False

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
        if type(self.head_only) is not bool:
            raise MAMLError("head_only 必须是 bool")
        if self.head_only and not self.first_order:
            raise MAMLError("head_only=True 要求 first_order=True：ANIL 不支持二阶元梯度")

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

    def to_arm_dict(self) -> dict[str, Any]:
        """模型/臂清单配置：to_dict（旧 10 键冻结）基础上显式记录 head_only。

        to_dict 是旧冻结合同，不得加入 head_only（会改变旧指纹/固定向量）；
        S3 model_manifest 等新产物用本方法，保证 ANIL 配置可无损重建。
        """
        payload = self.to_dict()
        payload["head_only"] = self.head_only
        return payload


def config_from_dict(payload: Mapping[str, Any]) -> MAMLConfig:
    """从配置字典重建 MAMLConfig；旧 10 键字典（无 head_only）行为不变。"""
    if not isinstance(payload, Mapping):
        raise MAMLError("config_from_dict 需要 Mapping")
    data = dict(payload)
    head_only = data.pop("head_only", None)
    if head_only is None:
        return MAMLConfig(**data)
    if type(head_only) is not bool:
        raise MAMLError("head_only 必须是 bool")
    return MAMLConfig(head_only=head_only, **data)


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


def _inner_adapt_full_torch(
    tensors: list[Any],
    support_features: Any,
    support_targets: Any,
    config: MAMLConfig,
    create_graph: bool = True,
) -> tuple[list[Any], list[float]]:
    """FULL_MAML 函数式内循环：不原地修改 .data，保留二阶计算图。

    每步 loss=MSE(forward(tensors), y)；grads=torch.autograd.grad(loss, tensors,
    create_graph=True)（FD/值评估时可关掉 create_graph 降内存），随后
    tensors=[t - inner_lr*g] 生成新的叶子外张量，旧张量不被原地改写。
    """
    losses: list[float] = []
    current = list(tensors)
    if config.inner_steps == 0:
        return current, losses
    for _ in range(config.inner_steps):
        prediction = _forward_torch(current, support_features)
        loss = _mse_torch(prediction, support_targets)
        grads = torch.autograd.grad(loss, current, create_graph=create_graph)
        losses.append(float(loss.detach().item()))
        current = [tensor - config.inner_lr * grad for tensor, grad in zip(current, grads)]
    return current, losses


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


def _head_tensor_indices(parameters_or_tensors: Any) -> tuple[int, int]:
    """ANIL 头参数索引：输出层 weight/bias = 最后两个张量（2L-2, 2L-1）。"""
    tensors = (
        parameters_or_tensors.tensors
        if isinstance(parameters_or_tensors, ParameterSet)
        else list(parameters_or_tensors)
    )
    if len(tensors) < 2 or len(tensors) % 2 != 0:
        raise MAMLError("ANIL 需要按 weight/bias 成对排列的参数，且至少一层")
    return len(tensors) - 2, len(tensors) - 1


def _inner_adapt_anil_torch(
    tensors: list[Any], support_features: Any, support_targets: Any, config: MAMLConfig
) -> tuple[list[Any], list[float]]:
    """ANIL 内循环：仅更新输出层 weight/bias，body 参数逐位不变。"""
    losses: list[float] = []
    if config.inner_steps == 0:
        return tensors, losses
    head = list(_head_tensor_indices(tensors))
    for _ in range(config.inner_steps):
        prediction = _forward_torch(tensors, support_features)
        loss = _mse_torch(prediction, support_targets)
        grads = torch.autograd.grad(loss, [tensors[index] for index in head], create_graph=False)
        losses.append(float(loss.detach().item()))
        for index, grad in zip(head, grads):
            tensors[index].data = tensors[index].data - config.inner_lr * grad.detach()
    return tensors, losses


def _inner_adapt_anil_episodes(
    parameters: ParameterSet, episodes: Sequence[TaskEpisode], config: MAMLConfig
) -> tuple[list[ParameterSet], list[float], list[float]]:
    """对每个任务做 ANIL 头-only 内循环；返回与 _inner_adapt_episodes 同构三元组。"""
    _require_torch()
    adapted_sets: list[ParameterSet] = []
    firsts: list[float] = []
    lasts: list[float] = []
    for episode in episodes:
        support_x = torch.tensor(episode.support_features, dtype=torch.float64)
        support_y = torch.tensor(episode.support_targets, dtype=torch.float64)
        tensors = _to_torch(parameters.tensors, requires_grad=True)
        _, inner_losses = _inner_adapt_anil_torch(tensors, support_x, support_y, config)
        if inner_losses:
            firsts.append(inner_losses[0])
            lasts.append(inner_losses[-1])
        adapted_sets.append(ParameterSet([tensor.detach().numpy().copy() for tensor in tensors]))
    return adapted_sets, firsts, lasts


def inner_adapt_anil(
    params: ParameterSet, support: Any, config: MAMLConfig
) -> tuple[ParameterSet, list[float]]:
    """ANIL 单任务适配：只更新输出层（最后两个张量），返回 (适配后参数, support loss)。"""
    if not isinstance(params, ParameterSet):
        raise MAMLError("inner_adapt_anil 需要 ParameterSet")
    if not isinstance(config, MAMLConfig):
        raise MAMLError("inner_adapt_anil 需要 MAMLConfig")
    if not config.head_only:
        raise MAMLError("inner_adapt_anil 需要 head_only=True 的 MAMLConfig")
    episode = _as_episode(support)
    if episode.support_features.shape[1] != config.input_dim:
        raise MAMLError("support 特征维度与 config.input_dim 不一致")
    _require_torch()
    tensors = _to_torch(params.tensors, requires_grad=True)
    support_x = torch.tensor(episode.support_features, dtype=torch.float64)
    support_y = torch.tensor(episode.support_targets, dtype=torch.float64)
    _, losses = _inner_adapt_anil_torch(tensors, support_x, support_y, config)
    adapted = ParameterSet([tensor.detach().numpy().copy() for tensor in tensors])
    return adapted, losses


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


def _full_maml_outer_gradient(
    parameters: ParameterSet, episodes: Sequence[TaskEpisode], config: MAMLConfig
) -> tuple[float, list[np.ndarray]]:
    """真二阶元梯度：J(theta)=mean_t L_query(theta_t'(theta)) 对初始 theta 求导。

    每个任务从同一 theta 做完整函数式内循环（create_graph=True），再把各任务 query
    loss 平均后的标量 J 对初始叶子张量做一次 autograd.grad(create_graph=False)，
    得到包含内循环二阶项的 FULL_MAML 元梯度。返回 (J, 梯度列表)。
    """
    outer_loss, grads, _, _ = _full_maml_loss_and_grads(parameters, episodes, config)
    return outer_loss, grads


def _full_maml_loss_and_grads(
    parameters: ParameterSet, episodes: Sequence[TaskEpisode], config: MAMLConfig
) -> tuple[float, list[np.ndarray], list[float], list[float]]:
    """返回 (J, 二阶元梯度, 首步 support loss 均值, 末步 support loss 均值)。"""
    _require_torch()
    episodes = _episode_batch(episodes)
    base = _to_torch(parameters.tensors, requires_grad=True)
    total = torch.zeros((), dtype=torch.float64)
    firsts: list[float] = []
    lasts: list[float] = []
    for episode in episodes:
        support_x = torch.tensor(episode.support_features, dtype=torch.float64)
        support_y = torch.tensor(episode.support_targets, dtype=torch.float64)
        query_x = torch.tensor(episode.query_features, dtype=torch.float64)
        query_y = torch.tensor(episode.query_targets, dtype=torch.float64)
        adapted, inner_losses = _inner_adapt_full_torch(
            base, support_x, support_y, config, create_graph=True
        )
        query_loss = _mse_torch(_forward_torch(adapted, query_x), query_y)
        total = total + query_loss / float(len(episodes))
        if inner_losses:
            firsts.append(inner_losses[0])
            lasts.append(inner_losses[-1])
    grad_tensors = torch.autograd.grad(total, base, create_graph=False)
    grads = [np.asarray(grad.detach().numpy(), dtype=np.float64) for grad in grad_tensors]
    return float(total.detach().item()), grads, firsts, lasts


def _full_maml_loss_value(
    parameters: ParameterSet, episodes: Sequence[TaskEpisode], config: MAMLConfig
) -> float:
    """在给定初始 theta 上重跑完整内循环后的元目标 J(theta)（仅取值，供 FD 用）。"""
    _require_torch()
    base = _to_torch(parameters.tensors, requires_grad=True)
    total = torch.zeros((), dtype=torch.float64)
    for episode in episodes:
        support_x = torch.tensor(episode.support_features, dtype=torch.float64)
        support_y = torch.tensor(episode.support_targets, dtype=torch.float64)
        query_x = torch.tensor(episode.query_features, dtype=torch.float64)
        query_y = torch.tensor(episode.query_targets, dtype=torch.float64)
        adapted, _ = _inner_adapt_full_torch(
            base, support_x, support_y, config, create_graph=False
        )
        total = total + _mse_torch(_forward_torch(adapted, query_x), query_y) / float(len(episodes))
    return float(total.detach().item())


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
    params: ParameterSet,
    batch: Sequence[Any],
    config: MAMLConfig,
    second_order: bool = False,
) -> tuple[ParameterSet, dict[str, float]]:
    """一次外循环更新；second_order=True 或 config.first_order=False 时走 FULL_MAML。

    FOMAML 路径保持既有行为（先一阶适配、再在适配点取 query 梯度）；FULL_MAML 路径用
    函数式内循环 + autograd 二阶图，对真实元目标 J(theta) 求导。两路径返回相同统计量键。
    """
    if not isinstance(params, ParameterSet):
        raise MAMLError("meta_train_step 需要 ParameterSet")
    episodes = _episode_batch(batch)
    if config.head_only:
        if second_order or not config.first_order:
            raise MAMLError(
                "head_only=True 时禁止 second_order/FULL_MAML：ANIL 只支持一阶外循环"
            )
        adapted_sets, firsts, lasts = _inner_adapt_anil_episodes(params, episodes, config)
        outer_loss, grads = _fomaml_outer_gradient(adapted_sets, episodes)
    else:
        full_mode = bool(second_order) or (not config.first_order)
        if full_mode:
            outer_loss, grads, firsts, lasts = _full_maml_loss_and_grads(params, episodes, config)
            if not firsts:
                # inner_steps=0：无内循环 loss 可记录，用初始点 support loss 作为首/末值（有限可记录）
                base_tensors = _to_torch(params.tensors, requires_grad=False)
                support_losses: list[float] = []
                for episode in episodes:
                    support_x = torch.tensor(episode.support_features, dtype=torch.float64)
                    support_y = torch.tensor(episode.support_targets, dtype=torch.float64)
                    with torch.no_grad():
                        support_losses.append(
                            float(_mse_torch(_forward_torch(base_tensors, support_x), support_y).item())
                        )
                firsts = support_losses
                lasts = list(support_losses)
        else:
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
        tensors = model.tensors
        if len(tensors) % 2 != 0:
            raise MAMLError("ParameterSet 参数必须按 weight/bias 成对排列")
        hidden: list[int] = []
        input_dim: int | None = None
        previous_out: int | None = None
        n_layers = len(tensors) // 2
        for layer in range(n_layers):
            weight = tensors[2 * layer]
            bias = tensors[2 * layer + 1]
            if weight.ndim != 2 or bias.ndim != 1:
                raise MAMLError("ParameterSet 参数必须按 2D weight / 1D bias 交替排列")
            if int(weight.shape[1]) != int(bias.shape[0]):
                raise MAMLError("ParameterSet 相邻 weight/bias 维度不一致")
            if input_dim is None:
                input_dim = int(weight.shape[0])
            elif int(weight.shape[0]) != int(previous_out):
                raise MAMLError("ParameterSet 相邻层维度不一致")
            previous_out = int(weight.shape[1])
            if layer < n_layers - 1:
                hidden.append(previous_out)
        config = MAMLConfig(
            input_dim=int(input_dim),
            output_dim=int(previous_out),
            hidden_sizes=tuple(hidden),
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


def _finite_difference_gradient_check_fomaml(
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


def _finite_difference_gradient_check_full(
    model: Any,
    batch: Sequence[Any],
    *,
    max_coordinates: int = FD_FULL_MAX_COORDINATES,
    min_coordinates: int | None = None,
    tolerance: float = FD_FULL_RELATIVE_TOLERANCE,
    epsilon_scale: float = FD_FULL_EPSILON_SCALE,
) -> dict[str, Any]:
    """中心差分校验 FULL_MAML 二阶元梯度（S2 计划 §4.3，fail-closed）。

    - 解析梯度 = _full_maml_outer_gradient；
    - 数值差分在原始 theta 上做：eps_j = 1e-6 * max(1, |theta_j|)，重跑完整内循环；
    - 按 |analytic| 从大到小选 max_coordinates 个坐标（跨全部张量）；
    - 相对误差分母 max(|numeric|, |analytic|, 1e-12)，阈值默认 1e-6；
    - 任何失败抛出 MAMLError（错误码前缀 S2_META_GRAD_FD_FAIL），不得静默返回 PASS。
    """
    if type(max_coordinates) is not int or max_coordinates <= 0:
        raise MAMLError("max_coordinates 必须是正整数")
    required = max_coordinates if min_coordinates is None else int(min_coordinates)
    if required < 1:
        raise MAMLError("min_coordinates 必须 >= 1")
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise MAMLError("tolerance 必须为正有限数")
    if not math.isfinite(epsilon_scale) or epsilon_scale <= 0.0:
        raise MAMLError("epsilon_scale 必须为正有限数")
    config, parameters = _model_config(model)
    if config.first_order:
        raise MAMLError(
            f"{S2_META_GRAD_FD_FAIL}: mode='full' 需要 first_order=False 的 MAMLConfig"
        )
    episodes = _episode_batch(batch)
    for episode in episodes:
        if episode.support_features.shape[1] != config.input_dim:
            raise MAMLError("batch 特征维度与 config.input_dim 不一致")
        if episode.query_targets.shape[1] != config.output_dim:
            raise MAMLError("batch 标签维度与 config.output_dim 不一致")
    _require_torch()
    outer_loss, analytic_grads = _full_maml_outer_gradient(parameters, episodes, config)
    candidates: list[tuple[int, int, float]] = []
    for tensor_index, grad in enumerate(analytic_grads):
        flat = grad.reshape(-1)
        for flat_index in range(flat.shape[0]):
            candidates.append((tensor_index, int(flat_index), float(flat[flat_index])))
    if len(candidates) < required:
        raise MAMLError(
            f"{S2_META_GRAD_FD_FAIL}: 可抽查坐标仅 {len(candidates)} 个，少于 {required}；"
            "FD 门禁不得在证据不足时判定通过（fail-closed）"
        )
    candidates.sort(key=lambda item: (-abs(item[2]), item[0], item[1]))
    selected = candidates[:max_coordinates]
    names = parameters.names
    checks: list[dict[str, Any]] = []
    max_relative_error = 0.0
    failures: list[dict[str, Any]] = []
    for tensor_index, flat_index, analytic in selected:
        theta_j = float(parameters.tensors[tensor_index].reshape(-1)[flat_index])
        eps = float(epsilon_scale * max(1.0, abs(theta_j)))
        plus = _perturb(parameters, tensor_index, flat_index, eps)
        minus = _perturb(parameters, tensor_index, flat_index, -eps)
        j_plus = _full_maml_loss_value(plus, episodes, config)
        j_minus = _full_maml_loss_value(minus, episodes, config)
        numeric = (j_plus - j_minus) / (2.0 * eps)
        denominator = max(abs(numeric), abs(analytic), FD_FULL_DENOMINATOR_FLOOR)
        relative_error = abs(numeric - analytic) / denominator
        max_relative_error = max(max_relative_error, relative_error)
        passed = relative_error <= tolerance
        check = {
            "parameter_name": names[tensor_index],
            "tensor_index": int(tensor_index),
            "flat_index": int(flat_index),
            "analytic": float(analytic),
            "numeric": float(numeric),
            "abs_error": float(abs(numeric - analytic)),
            "relative_error": float(relative_error),
            "epsilon": float(eps),
            "tolerance": float(tolerance),
            "status": "PASS" if passed else "FAIL",
        }
        checks.append(check)
        if not passed:
            failures.append(check)
    result = {
        "status": "FAIL" if failures else "PASS",
        "mode": "full",
        "backend": config.backend,
        "equivalence_claimed": False,
        "fd_point": "meta_parameters",
        "outer_loss": float(outer_loss),
        "tolerance": float(tolerance),
        "epsilon_policy": "1e-6 * max(1, |theta_j|)",
        "denominator_policy": "max(|numeric|, |analytic|, 1e-12)",
        "coordinates_requested": int(max_coordinates),
        "coordinates_available": len(candidates),
        "n_checked": len(checks),
        "max_relative_error": float(max_relative_error),
        "checks": checks,
    }
    if failures:
        raise MAMLError(
            f"{S2_META_GRAD_FD_FAIL}: max_relative_error={max_relative_error:.6e} > "
            f"tolerance={tolerance:.1e}（n_checked={len(checks)}，fail-closed）"
        )
    return result


def finite_difference_gradient_check(
    model: Any,
    batch: Sequence[Any],
    epsilon: float | None = None,
    tolerance: float | None = None,
    *,
    mode: str = "fomaml",
    max_coordinates: int = FD_FULL_MAX_COORDINATES,
    min_coordinates: int | None = None,
) -> dict[str, Any]:
    """FD 门禁统一入口；mode="fomaml" 保持 §7.2 既有口径，mode="full" 校验二阶元梯度。"""
    if mode not in FD_MODES:
        raise MAMLError(f"FD mode 只支持 {FD_MODES}，实际 {mode!r}")
    if mode == "full":
        if epsilon is not None:
            raise MAMLError("mode='full' 的 epsilon 由 eps_j=1e-6*max(1,|theta_j|) 决定，不接受 epsilon")
        full_tolerance = FD_FULL_RELATIVE_TOLERANCE if tolerance is None else float(tolerance)
        return _finite_difference_gradient_check_full(
            model,
            batch,
            max_coordinates=max_coordinates,
            min_coordinates=min_coordinates,
            tolerance=full_tolerance,
        )
    actual_epsilon = FD_DEFAULT_EPSILON if epsilon is None else float(epsilon)
    actual_tolerance = FD_DEFAULT_TOLERANCE if tolerance is None else float(tolerance)
    return _finite_difference_gradient_check_fomaml(
        model, batch, actual_epsilon, actual_tolerance
    )


# -- S3 梯度门禁（计划 §4.4） -------------------------------------------------


def _s3_gate_canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def s3_gate_coordinate_plan(
    parameters: ParameterSet,
    *,
    max_coordinates: int = S3_GATE_COORDINATES,
    head_only: bool = False,
) -> dict[str, Any]:
    """按 sha256("s3-gate|param|index") 排序选前 max_coordinates 个坐标。

    param 用 ParameterSet.names（layer_{i}_weight/bias）；index 用该张量展平后的下标。
    返回 {requested, available, selected}；available 不足 requested 时 fail-closed。
    """
    if type(max_coordinates) is not int or max_coordinates <= 0:
        raise MAMLError("max_coordinates 必须是正整数")
    if not isinstance(parameters, ParameterSet):
        raise MAMLError("s3_gate_coordinate_plan 需要 ParameterSet")
    tensors = parameters.tensors
    if len(tensors) < 2 or len(tensors) % 2 != 0:
        raise MAMLError("梯度门参数必须按 weight/bias 成对排列")
    names = parameters.names
    if head_only:
        indices = list(_head_tensor_indices(parameters))
    else:
        indices = list(range(len(tensors)))
    entries: list[dict[str, Any]] = []
    for tensor_index in indices:
        flat = np.asarray(tensors[tensor_index], dtype=np.float64).reshape(-1)
        for flat_index in range(int(flat.shape[0])):
            sort_key = hashlib.sha256(
                f"s3-gate|{names[tensor_index]}|{flat_index}".encode("utf-8")
            ).hexdigest()
            entries.append(
                {
                    "parameter_name": names[tensor_index],
                    "tensor_index": int(tensor_index),
                    "flat_index": int(flat_index),
                    "sort_key": sort_key,
                }
            )
    entries.sort(key=lambda item: (item["sort_key"], item["tensor_index"], item["flat_index"]))
    if len(entries) < max_coordinates:
        raise MAMLError(
            f"{S3_GATE_FD_FAIL}: 可抽查坐标仅 {len(entries)} 个，少于 {max_coordinates}；"
            "梯度门禁不得在证据不足时判定通过（fail-closed）"
        )
    return {
        "requested": int(max_coordinates),
        "available": len(entries),
        "selected": entries[:max_coordinates],
    }


def s3_gradient_gate(
    parameters: ParameterSet,
    episodes: Sequence[Any],
    config: MAMLConfig,
    *,
    mode: str = "fomaml",
    max_coordinates: int = S3_GATE_COORDINATES,
    tolerance: float = S3_GATE_RELATIVE_TOLERANCE,
    epsilon_scale: float = S3_GATE_EPSILON_SCALE,
) -> dict[str, Any]:
    """S3 计划 §4.4 梯度门禁（FOMAML 全参数 / ANIL 仅 head，适配点中心差分，fail-closed）。

    解析梯度：FOMAML 路径 = mean_t ∂L_q(θ'_t)/∂θ'_t（_fomaml_outer_gradient）；
    ANIL 路径同上，但内循环只更新输出层，门禁坐标只取 head（body 冻结断言）。
    数值梯度在适配后参数点 θ' 上做中心差分（FOMAML 一阶梯度定义即 adapted 点，
    不能在原始 θ 上重跑内循环后比较，否则 O(inner_lr) 截断误差远大于 1e-6）。
    相对误差分母 max(|numeric|, |analytic|, 1e-12)，阈值 1e-6；任何失败抛 MAMLError。
    """
    if not isinstance(parameters, ParameterSet):
        raise MAMLError("s3_gradient_gate 需要 ParameterSet")
    if not isinstance(config, MAMLConfig):
        raise MAMLError("s3_gradient_gate 需要 MAMLConfig")
    if mode not in S3_GATE_MODES:
        raise MAMLError(f"梯度门 mode 只支持 {S3_GATE_MODES}，实际 {mode!r}")
    if type(max_coordinates) is not int or max_coordinates <= 0:
        raise MAMLError("max_coordinates 必须是正整数")
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise MAMLError("tolerance 必须为正有限数")
    if not math.isfinite(epsilon_scale) or epsilon_scale <= 0.0:
        raise MAMLError("epsilon_scale 必须为正有限数")
    if not config.first_order:
        raise MAMLError(f"{S3_GATE_FD_FAIL}: 梯度门只支持 first_order=True（FOMAML/ANIL）")
    if mode == "anil" and not config.head_only:
        raise MAMLError(f"{S3_GATE_FD_FAIL}: mode='anil' 需要 head_only=True 的 MAMLConfig")
    if mode == "fomaml" and config.head_only:
        raise MAMLError(f"{S3_GATE_FD_FAIL}: mode='fomaml' 需要 head_only=False 的 MAMLConfig")
    episodes = _episode_batch(episodes)
    for episode in episodes:
        if episode.support_features.shape[1] != config.input_dim:
            raise MAMLError("batch 特征维度与 config.input_dim 不一致")
        if episode.support_targets.shape[1] != config.output_dim:
            raise MAMLError("batch 标签维度与 config.output_dim 不一致")
    _require_torch()
    body_frozen: bool | None = None
    if mode == "anil":
        head_start, _ = _head_tensor_indices(parameters)
        before_body = [
            np.array(tensor, dtype=np.float64, copy=True) for tensor in parameters.tensors[:head_start]
        ]
        adapted_sets, _, _ = _inner_adapt_anil_episodes(parameters, episodes, config)
        body_frozen = True
        for adapted in adapted_sets:
            for index, before in enumerate(before_body):
                if not np.array_equal(before, np.asarray(adapted.tensors[index], dtype=np.float64)):
                    raise MAMLError(
                        f"{S3_GATE_ANIL_BODY_FROZEN}: episode {episode.task_id!r} body 参数 "
                        f"{parameters.names[index]} 在内循环中被修改"
                    )
    else:
        adapted_sets, _, _ = _inner_adapt_episodes(parameters, episodes, config)
    outer_loss, analytic_grads = _fomaml_outer_gradient(adapted_sets, episodes)
    plan = s3_gate_coordinate_plan(
        adapted_sets[0], max_coordinates=max_coordinates, head_only=(mode == "anil")
    )
    base = adapted_sets[0]
    names = parameters.names
    checks: list[dict[str, Any]] = []
    max_relative_error = 0.0
    failures: list[dict[str, Any]] = []
    for entry in plan["selected"]:
        tensor_index = int(entry["tensor_index"])
        flat_index = int(entry["flat_index"])
        analytic = float(
            np.asarray(analytic_grads[tensor_index], dtype=np.float64).reshape(-1)[flat_index]
        )
        theta_j = float(
            np.asarray(base.tensors[tensor_index], dtype=np.float64).reshape(-1)[flat_index]
        )
        epsilon = float(epsilon_scale * max(1.0, abs(theta_j)))
        plus = [_perturb(adapted, tensor_index, flat_index, epsilon) for adapted in adapted_sets]
        minus = [_perturb(adapted, tensor_index, flat_index, -epsilon) for adapted in adapted_sets]
        numeric = (
            _outer_loss_at_adapted(plus, episodes) - _outer_loss_at_adapted(minus, episodes)
        ) / (2.0 * epsilon)
        denominator = max(abs(numeric), abs(analytic), S3_GATE_DENOMINATOR_FLOOR)
        relative_error = abs(numeric - analytic) / denominator
        max_relative_error = max(max_relative_error, relative_error)
        check = {
            "parameter_name": names[tensor_index],
            "tensor_index": tensor_index,
            "flat_index": flat_index,
            "analytic": analytic,
            "numeric": float(numeric),
            "abs_error": float(abs(numeric - analytic)),
            "relative_error": float(relative_error),
            "epsilon": epsilon,
            "tolerance": float(tolerance),
            "status": "PASS" if relative_error <= tolerance else "FAIL",
        }
        checks.append(check)
        if check["status"] != "PASS":
            failures.append(check)
    k0_equivalence: bool | None = None
    if config.inner_steps == 0:
        k0_equivalence = all(
            np.array_equal(np.asarray(parameters.tensors[index], dtype=np.float64),
                           np.asarray(adapted_sets[0].tensors[index], dtype=np.float64))
            for index in range(len(parameters.tensors))
        )
        if not k0_equivalence:
            raise MAMLError(
                f"{S3_GATE_K0_EQUIVALENCE}: inner_steps=0 时适配后参数必须与初始参数逐位相同"
            )
    result = {
        "schema_version": S3_GATE_SCHEMA_VERSION,
        "mode": mode,
        "backend": config.backend,
        "equivalence_claimed": False,
        "fd_point": "adapted_parameters",
        "epsilon_policy": "1e-6 * max(1, |theta_adapted_j|)",
        "tolerance": float(tolerance),
        "denominator_policy": "max(|numeric|, |analytic|, 1e-12)",
        "coordinates_requested": int(max_coordinates),
        "coordinates_available": int(plan["available"]),
        "n_checked": len(checks),
        "max_relative_error": float(max_relative_error),
        "status": "FAIL" if failures else "PASS",
        "outer_loss": float(outer_loss),
        "anil_body_frozen": body_frozen,
        "k0_equivalence": k0_equivalence,
        "inner_steps": int(config.inner_steps),
        "config": config.to_arm_dict(),
        "checks": checks,
    }
    if failures:
        raise MAMLError(
            f"{S3_GATE_FD_FAIL}: max_relative_error={max_relative_error:.6e} > "
            f"tolerance={tolerance:.1e}（n_checked={len(checks)}，fail-closed）"
        )
    return result


def s3_gate_sha256(payload: Mapping[str, Any]) -> str:
    """梯度门载荷的 canonical JSON sha256（文件原始字节 sha 由落盘函数返回）。"""
    return hashlib.sha256(_s3_gate_canonical_json(payload).encode("utf-8")).hexdigest()


def write_s3_gate_result(result: Mapping[str, Any], path: str | Any) -> str:
    """写 s3 梯度门 JSON（canonical + LF），返回文件原始字节 sha256。"""
    from pathlib import Path

    data = (_s3_gate_canonical_json(result) + "\n").encode("utf-8")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def assert_s3_gate_consistent(payload: Mapping[str, Any]) -> bool:
    """负控：校验门禁载荷内部自洽；任一篡改抛 S3_GATE_TAMPER_DETECTED。"""
    if not isinstance(payload, Mapping):
        raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: 载荷必须是 mapping")
    if payload.get("schema_version") != S3_GATE_SCHEMA_VERSION:
        raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: schema_version 不符")
    checks = payload.get("checks")
    if not isinstance(checks, list) or not checks:
        raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: checks 缺失或为空")
    if payload.get("n_checked") != len(checks):
        raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: n_checked 与 checks 数量不符")
    if payload.get("mode") not in S3_GATE_MODES:
        raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: mode 非法")
    tolerance = payload.get("tolerance")
    if not isinstance(tolerance, (int, float)) or not math.isfinite(float(tolerance)):
        raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: tolerance 非有限")
    seen: set[tuple[int, int]] = set()
    max_relative_error = 0.0
    all_pass = True
    for check in checks:
        try:
            tensor_index = int(check["tensor_index"])
            flat_index = int(check["flat_index"])
            analytic = float(check["analytic"])
            numeric = float(check["numeric"])
            relative_error = float(check["relative_error"])
            status = check["status"]
        except Exception as exc:
            raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: check 字段缺失/类型错: {exc}") from exc
        key = (tensor_index, flat_index)
        if key in seen:
            raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: 坐标重复 {key}")
        seen.add(key)
        recomputed = abs(numeric - analytic) / max(
            abs(numeric), abs(analytic), S3_GATE_DENOMINATOR_FLOOR
        )
        if abs(recomputed - relative_error) > 1e-12:
            raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: relative_error 与 num/ana 不符")
        expected_status = "PASS" if relative_error <= float(tolerance) else "FAIL"
        if status != expected_status:
            raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: check status 与阈值不符")
        if expected_status != "PASS":
            all_pass = False
        max_relative_error = max(max_relative_error, relative_error)
    if abs(max_relative_error - float(payload.get("max_relative_error", float("nan")))) > 1e-12:
        raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: max_relative_error 不一致")
    expected = "PASS" if all_pass else "FAIL"
    if payload.get("status") != expected:
        raise MAMLError(f"{S3_GATE_TAMPER_DETECTED}: status 与 checks 不一致")
    if expected != "PASS":
        raise MAMLError(f"{S3_GATE_FD_FAIL}: 门禁载荷本身为 FAIL")
    return True


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
    "FD_FULL_DENOMINATOR_FLOOR",
    "FD_FULL_EPSILON_SCALE",
    "FD_FULL_MAX_COORDINATES",
    "FD_FULL_MIN_COORDINATES",
    "FD_FULL_RELATIVE_TOLERANCE",
    "FD_MAX_COMPONENTS",
    "FD_MIN_COMPONENTS",
    "FD_MODES",
    "MAMLConfig",
    "MAMLError",
    "MAMLModel",
    "ParameterSet",
    "SUPPORTED_BACKENDS",
    "TaskEpisode",
    "S2_META_GRAD_FD_FAIL",
    "S3_GATE_ANIL_BODY_FROZEN",
    "S3_GATE_COORDINATES",
    "S3_GATE_DENOMINATOR_FLOOR",
    "S3_GATE_EPSILON_SCALE",
    "S3_GATE_FD_FAIL",
    "S3_GATE_K0_EQUIVALENCE",
    "S3_GATE_MODES",
    "S3_GATE_RELATIVE_TOLERANCE",
    "S3_GATE_SCHEMA_VERSION",
    "S3_GATE_TAMPER_DETECTED",
    "assert_s3_gate_consistent",
    "build_small_model",
    "config_from_dict",
    "finite_difference_gradient_check",
    "init_parameters",
    "inner_adapt",
    "inner_adapt_anil",
    "meta_train",
    "meta_train_step",
    "torch_available",
    "s3_gate_coordinate_plan",
    "s3_gate_sha256",
    "s3_gradient_gate",
    "torch_import_error",
    "write_finite_difference_check",
    "write_s3_gate_result",
]
