"""D-NEXT-001 A4｜设备常驻 FOMAML 参考实现（G1 基准核心）。

本模块提供与项目 research.concorde_metaopt.meta_learning.maml 的 FOMAML 路径
（先一阶适配、再在适配点取 query 梯度）数学等价的实现，但参数全程常驻
torch 张量（CPU 或 CUDA），不经过 .numpy() 往返，便于在 GPU 上做真实
forward/backward 基准。

约束与来源标注：
- physical_call_count = 0，全部为合成响应（synthetic_analogue），不接触任何
  真实气动/任务求解器，不改变 S1–S3 冻结结果。
- 任务族为 12 维设计变量 x∈[0,1]^12 上的合成非线性响应，仅用于计算性能与
  数值精度基准，不代表任何真实物理响应。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

try:  # torch 为可选依赖：CPU 环境缺失时应给出明确错误而不是静默降级
    import torch
except Exception as exc:  # pragma: no cover - 环境缺失路径
    torch = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: Exception | None = exc
else:
    _TORCH_IMPORT_ERROR = None


N_INPUT = 12
N_OUTPUT = 1


class GPUError(RuntimeError):
    """GPU/基准模块错误。"""


def require_torch() -> Any:
    if torch is None:  # pragma: no cover - 环境缺失路径
        raise GPUError(f"当前 Python 环境缺少 torch：{_TORCH_IMPORT_ERROR}")
    return torch


def dtype_from_name(name: str) -> Any:
    module = require_torch()
    mapping = {"float64": module.float64, "float32": module.float32}
    if name not in mapping:
        raise GPUError(f"不支持的 dtype: {name!r}（只允许 float64/float32）")
    return mapping[name]


# ---------------------------------------------------------------------------
# 合成任务族（与真实物理无关，仅作计算/精度基准）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskFamily:
    """任务族：weights (T,12) 单位方向、amplitude (T,1)、bias (T,1)。"""

    weights: np.ndarray
    amplitude: np.ndarray
    bias: np.ndarray

    def __len__(self) -> int:
        return int(self.weights.shape[0])


def make_task_family(n_tasks: int, seed: int) -> TaskFamily:
    """确定性生成 n_tasks 个任务；同 seed 逐位复现，供三路计算配置共用。"""
    if type(n_tasks) is not int or n_tasks <= 0:
        raise GPUError("n_tasks 必须是正整数")
    rng = np.random.default_rng(int(seed))
    weights = rng.normal(size=(n_tasks, N_INPUT))
    weights /= np.linalg.norm(weights, axis=1, keepdims=True)
    amplitude = rng.uniform(0.5, 2.0, size=(n_tasks, 1))
    bias = rng.normal(0.0, 0.3, size=(n_tasks, 1))
    return TaskFamily(weights=weights, amplitude=amplitude, bias=bias)


def task_response(family: TaskFamily, task_index: int, x: np.ndarray) -> np.ndarray:
    """任务响应 y = amp * tanh(2 * x·w) + bias（12 维输入 → 1 维输出）。"""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != N_INPUT:
        raise GPUError(f"x 必须是 (n,{N_INPUT}) 矩阵，实际 {x.shape}")
    raw = 2.0 * (x @ family.weights[task_index])
    return family.amplitude[task_index] * np.tanh(raw)[:, None] + family.bias[task_index]


@dataclass(frozen=True)
class Episode:
    """单个任务的 support/query 数据（numpy float64，构造后广播到任意设备/精度）。"""

    support_x: np.ndarray
    support_y: np.ndarray
    query_x: np.ndarray
    query_y: np.ndarray


def make_episodes(
    family: TaskFamily,
    task_indices: Sequence[int],
    k_shot: int,
    q_query: int,
    seed: int,
) -> list[Episode]:
    """确定性采样 support/query；同 seed 下三路配置获得完全相同的数值。"""
    if k_shot <= 0 or q_query <= 0:
        raise GPUError("k_shot/q_query 必须为正")
    rng = np.random.default_rng(int(seed))
    episodes: list[Episode] = []
    for task_index in task_indices:
        support_x = rng.random((int(k_shot), N_INPUT))
        query_x = rng.random((int(q_query), N_INPUT))
        episodes.append(
            Episode(
                support_x=support_x,
                support_y=task_response(family, int(task_index), support_x),
                query_x=query_x,
                query_y=task_response(family, int(task_index), query_x),
            )
        )
    return episodes


# ---------------------------------------------------------------------------
# 模型与 FOMAML（设备常驻）
# ---------------------------------------------------------------------------


def init_parameters(
    hidden_sizes: Sequence[int],
    seed: int,
    device: Any,
    dtype: Any,
) -> list[Any]:
    """Xavier-uniform MLP 初始化；先在 float64 CPU 生成再 cast，保证三路可比。"""
    module = require_torch()
    generator = module.Generator(device="cpu").manual_seed(int(seed))
    sizes = [N_INPUT, *[int(h) for h in hidden_sizes], N_OUTPUT]
    params: list[Any] = []
    for fan_in, fan_out in zip(sizes[:-1], sizes[1:]):
        limit = math.sqrt(6.0 / (fan_in + fan_out))
        weight = (module.rand(fan_in, fan_out, generator=generator, dtype=module.float64) * 2.0 - 1.0) * limit
        bias = module.zeros(fan_out, dtype=module.float64)
        params.append(weight.to(device=device, dtype=dtype))
        params.append(bias.to(device=device, dtype=dtype))
    return params


def forward(params: Sequence[Any], features: Any) -> Any:
    module = require_torch()
    current = features
    n_layers = len(params) // 2
    for layer in range(n_layers):
        current = current @ params[2 * layer] + params[2 * layer + 1]
        if layer < n_layers - 1:
            current = module.tanh(current)
    return current


def mse(prediction: Any, target: Any) -> Any:
    module = require_torch()
    return module.mean((prediction - target) ** 2)


def _as_tensor(array: np.ndarray, device: Any, dtype: Any) -> Any:
    module = require_torch()
    return module.as_tensor(array, dtype=dtype, device=device)


def inner_adapt(
    params: Sequence[Any],
    support_x: Any,
    support_y: Any,
    inner_lr: float,
    inner_steps: int,
) -> list[Any]:
    """函数式内循环（FOMAML 一阶适配）；返回适配后的叶子张量列表。"""
    module = require_torch()
    current = [tensor.detach().clone().requires_grad_(True) for tensor in params]
    for _ in range(int(inner_steps)):
        loss = mse(forward(current, support_x), support_y)
        grads = module.autograd.grad(loss, current, create_graph=False)
        current = [
            (tensor - float(inner_lr) * grad).detach().requires_grad_(True)
            for tensor, grad in zip(current, grads)
        ]
    return current


def fomaml_step(
    params: Sequence[Any],
    episodes: Sequence[Episode],
    inner_lr: float,
    inner_steps: int,
    outer_lr: float,
    device: Any,
    dtype: Any,
) -> tuple[list[Any], dict[str, float], list[np.ndarray]]:
    """一次 FOMAML 外循环：任务平均 query 梯度（一阶近似）更新初始参数。

    返回 (新参数, 统计量, 元梯度 numpy 列表)。梯度定义与项目 maml.py
    _fomaml_outer_gradient 一致：g = mean_t dL_q(theta'_t)/dtheta'_t。
    """
    module = require_torch()
    total_grads: list[Any] | None = None
    total_loss = 0.0
    for episode in episodes:
        support_x = _as_tensor(episode.support_x, device, dtype)
        support_y = _as_tensor(episode.support_y, device, dtype)
        query_x = _as_tensor(episode.query_x, device, dtype)
        query_y = _as_tensor(episode.query_y, device, dtype)
        adapted = inner_adapt(params, support_x, support_y, inner_lr, inner_steps)
        query_loss = mse(forward(adapted, query_x), query_y)
        total_loss += float(query_loss.detach().item())
        grads = module.autograd.grad(query_loss, adapted, create_graph=False)
        if total_grads is None:
            total_grads = [grad.detach() for grad in grads]
        else:
            total_grads = [acc + grad.detach() for acc, grad in zip(total_grads, grads)]
    divisor = float(len(episodes))
    assert total_grads is not None
    grads_np = [grad.detach().to("cpu").numpy().astype(np.float64) for grad in total_grads]
    new_params = [
        (tensor.detach() - float(outer_lr) * (grad / divisor)).detach()
        for tensor, grad in zip(params, total_grads)
    ]
    grad_norm = math.sqrt(sum(float(np.sum(grad**2)) for grad in grads_np))
    stats = {
        "outer_loss": total_loss / divisor,
        "grad_norm": grad_norm,
        "n_tasks": float(len(episodes)),
    }
    return new_params, stats, [grad / divisor for grad in grads_np]


def adapt_and_score(
    params: Sequence[Any],
    episodes: Sequence[Episode],
    inner_lr: float,
    inner_steps: int,
    device: Any,
    dtype: Any,
) -> tuple[float, list[float]]:
    """K-shot 适应后 query RMSE（不回传梯度，用于评估）。"""
    module = require_torch()
    losses: list[float] = []
    for episode in episodes:
        support_x = _as_tensor(episode.support_x, device, dtype)
        support_y = _as_tensor(episode.support_y, device, dtype)
        query_x = _as_tensor(episode.query_x, device, dtype)
        query_y = _as_tensor(episode.query_y, device, dtype)
        adapted = inner_adapt(params, support_x, support_y, inner_lr, inner_steps)
        with module.no_grad():
            prediction = forward(adapted, query_x)
            losses.append(float(module.sqrt(mse(prediction, query_y)).item()))
    return float(np.mean(losses)) if losses else float("nan"), losses


def batch_score(
    params: Sequence[Any],
    candidates: np.ndarray,
    device: Any,
    dtype: Any,
) -> np.ndarray:
    """代理批量打分：n×12 候选点一次前向（无梯度）。"""
    module = require_torch()
    with module.no_grad():
        features = _as_tensor(np.ascontiguousarray(candidates, dtype=np.float64), device, dtype)
        prediction = forward(params, features)
        return prediction.detach().to("cpu").numpy().astype(np.float64).reshape(-1)


def count_nonfinite(value: Any) -> int:
    module = require_torch()
    if isinstance(value, np.ndarray):
        return int(np.size(value) - np.count_nonzero(np.isfinite(value)))
    total = 0
    for tensor in value:
        total += int((~(module.isfinite(tensor))).sum().item())
    return total
