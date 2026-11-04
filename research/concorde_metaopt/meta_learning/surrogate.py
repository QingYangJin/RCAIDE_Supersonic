"""代理模型接口、特征编码与回归指标（§5.3）。

本模块不进行任何物理调用；所有网络输入是 12 维归一化设计 + 任务 context
（来自任务参数而非数据统计，防泄漏）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

import numpy as np

from .data_contract import CONSTRAINT_NAMES, OBJECTIVE_NAME

# 代理回归的最小/最大目标数，防止调用方误传
MAX_TARGET_DIM = 3
TOP_K_OVERLAP_K = 10
DEFAULT_HIDDEN_SIZES: tuple[int, ...] = (32, 32)


class SurrogateError(ValueError):
    """代理模型接口/训练错误。"""


@dataclass(frozen=True)
class SurrogatePrediction:
    """代理预测：mean 必填；uncertainty 仅当真标定时可填，未标定必须为 None。"""

    mean: np.ndarray
    uncertainty: np.ndarray | None = None

    def __post_init__(self) -> None:
        mean = np.asarray(self.mean, dtype=np.float64)
        if mean.ndim == 0:
            raise SurrogateError("预测均值至少为 1 维")
        if not np.all(np.isfinite(mean)):
            raise SurrogateError("预测均值包含非有限值")
        object.__setattr__(self, "mean", mean)
        if self.uncertainty is not None:
            uncertainty = np.asarray(self.uncertainty, dtype=np.float64)
            if uncertainty.shape != mean.shape:
                raise SurrogateError("uncertainty 形状必须与 mean 一致")
            if np.any(uncertainty < 0.0) or not np.all(np.isfinite(uncertainty)):
                raise SurrogateError("uncertainty 必须是非负有限值")
            object.__setattr__(self, "uncertainty", uncertainty)


@runtime_checkable
class ResponseSurrogate(Protocol):
    """代理模型协议（§5.3）：只要求最小接口，实现可替换。"""

    input_dim: int

    def fit(self, features: np.ndarray, targets: np.ndarray) -> "ResponseSurrogate":
        ...

    def predict(self, features: np.ndarray) -> SurrogatePrediction:
        ...


def encode_features(
    designs: np.ndarray,
    task_context: Mapping[str, float] | None,
    context_names: Sequence[str],
) -> np.ndarray:
    """把归一化设计 u∈[0,1]^d 与任务 context 拼成代理输入特征。

    designs: 形状 (n, d) 的归一化设计（§2.3 唯一解码路径之前的值）；
    task_context: {名称: 数值}，必须包含全部 context_names 且有限；
    context_names: 任务族的 context 名称顺序（合成族为 context_1/context_2）。
    返回形状 (n, d + len(context_names)) 的 float64 数组；不按数据统计重标定。
    """
    matrix = np.asarray(designs, dtype=np.float64)
    if matrix.ndim != 2:
        raise SurrogateError(f"designs 必须为二维数组，实际 {matrix.shape}")
    if matrix.shape[0] == 0:
        raise SurrogateError("designs 不能为空")
    if not np.all(np.isfinite(matrix)):
        raise SurrogateError("designs 包含非有限值")
    names = tuple(str(name) for name in context_names)
    if len(set(names)) != len(names):
        raise SurrogateError("context_names 不能重复")
    if task_context is None:
        raise SurrogateError("task_context 不能为 None")
    values: list[float] = []
    for name in names:
        if name not in task_context:
            raise SurrogateError(f"task_context 缺少 context 字段: {name}")
        value = task_context[name]
        if value is None or isinstance(value, bool):
            raise SurrogateError(f"task_context[{name}] 必须是数值")
        number = float(value)
        if not math.isfinite(number):
            raise SurrogateError(f"task_context[{name}] 非有限: {number!r}")
        values.append(number)
    context_block = np.repeat(np.asarray(values, dtype=np.float64)[None, :], matrix.shape[0], axis=0)
    return np.concatenate([matrix, context_block], axis=1)


def _rankdata(values: np.ndarray) -> np.ndarray:
    """平均秩（与 scipy.stats.rankdata 的 average 方法一致），不引入 scipy 依赖。"""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.shape[0], dtype=np.float64)
    sorted_values = values[order]
    position = 0
    while position < values.shape[0]:
        end = position + 1
        while end < values.shape[0] and sorted_values[end] == sorted_values[position]:
            end += 1
        average_rank = 0.5 * (position + end - 1) + 1.0
        ranks[order[position:end]] = average_rank
        position = end
    return ranks


def _top_k_overlap(predicted: np.ndarray, target: np.ndarray, k: int) -> float:
    """最小化问题 Top-k 重叠率：|topk(预测)∩topk(真值)| / k。"""
    if predicted.shape[0] == 0:
        return 0.0
    k_effective = int(min(k, predicted.shape[0]))
    if k_effective <= 0:
        return 0.0
    predicted_top = set(np.argsort(predicted, kind="mergesort")[:k_effective].tolist())
    target_top = set(np.argsort(target, kind="mergesort")[:k_effective].tolist())
    return float(len(predicted_top & target_top) / k_effective)


def regression_metrics(
    prediction: np.ndarray | SurrogatePrediction,
    target: np.ndarray,
) -> dict[str, float]:
    """回归指标（§9/§5.3）：rmse/mae/r2/max_abs_err/spearman/top_k_overlap。

    非有限预测或标签从指标计算中剔除，但计入 n_nonfinite（分母如实记录，
    不允许把失败样本静默丢掉）。
    """
    if isinstance(prediction, SurrogatePrediction):
        predicted = np.asarray(prediction.mean, dtype=np.float64)
    else:
        predicted = np.asarray(prediction, dtype=np.float64)
    truth = np.asarray(target, dtype=np.float64)
    if predicted.shape != truth.shape:
        raise SurrogateError(f"预测/标签形状不一致: {predicted.shape} vs {truth.shape}")
    if predicted.ndim == 2:
        if predicted.shape[1] != 1:
            raise SurrogateError("regression_metrics 仅接受单目标；多目标请逐列调用")
        predicted = predicted[:, 0]
        truth = truth[:, 0]
    if predicted.ndim != 1:
        raise SurrogateError(f"预测/标签必须为一维，实际 {predicted.ndim}")
    finite_mask = np.isfinite(predicted) & np.isfinite(truth)
    n_total = int(predicted.shape[0])
    n_finite = int(np.count_nonzero(finite_mask))
    metrics: dict[str, float] = {
        "n_total": float(n_total),
        "n_finite": float(n_finite),
        "n_nonfinite": float(n_total - n_finite),
    }
    if n_finite == 0:
        metrics.update({"rmse": float("nan"), "mae": float("nan"), "r2": float("nan"),
                        "max_abs_err": float("nan"), "spearman": float("nan"),
                        "top_k_overlap": float("nan")})
        return metrics
    p = predicted[finite_mask]
    t = truth[finite_mask]
    residual = p - t
    metrics["rmse"] = float(np.sqrt(np.mean(residual**2)))
    metrics["mae"] = float(np.mean(np.abs(residual)))
    metrics["max_abs_err"] = float(np.max(np.abs(residual)))
    if n_finite >= 2:
        ss_tot = float(np.sum((t - np.mean(t)) ** 2))
        ss_res = float(np.sum(residual**2))
        metrics["r2"] = float("nan") if ss_tot == 0.0 else float(1.0 - ss_res / ss_tot)
        rank_pred = _rankdata(p)
        rank_true = _rankdata(t)
        std_pred = float(np.std(rank_pred))
        std_true = float(np.std(rank_true))
        if std_pred == 0.0 or std_true == 0.0:
            metrics["spearman"] = float("nan")
        else:
            metrics["spearman"] = float(
                np.mean((rank_pred - rank_pred.mean()) * (rank_true - rank_true.mean()))
                / (std_pred * std_true)
            )
    else:
        metrics["r2"] = float("nan")
        metrics["spearman"] = float("nan")
    metrics["top_k_overlap"] = _top_k_overlap(p, t, TOP_K_OVERLAP_K)
    return metrics


def select_objective_and_constraint_targets(
    target_names: Sequence[str],
) -> tuple[int, tuple[int, ...]]:
    """从归档 target_names 中定位 objective 下标与约束下标（按冻结顺序）。

    约束下标顺序 = CONSTRAINT_NAMES 中出现在 target_names 里的顺序，
    不使用归档中的偶然顺序，保证跨 run 一致。
    """
    names = tuple(str(name) for name in target_names)
    if len(set(names)) != len(names):
        raise SurrogateError("target_names 不能重复")
    objective_candidates = [OBJECTIVE_NAME, "objective"]
    objective_index: int | None = None
    for candidate in objective_candidates:
        if candidate in names:
            objective_index = names.index(candidate)
            break
    if objective_index is None:
        raise SurrogateError(
            f"target_names 中缺少目标列（期望 {OBJECTIVE_NAME!r} 或 'objective'）: {names}"
        )
    constraint_indices = tuple(
        names.index(name) for name in CONSTRAINT_NAMES if name in names
    )
    if objective_index in constraint_indices:
        raise SurrogateError("objective 列与约束列重复")
    return objective_index, constraint_indices


class MLPRegressorSurrogate:
    """纯 numpy 的确定性 MLP 回归代理（tanh 隐层 + Adam，全批量）。

    该实现仅用于 M1 的基线臂 R/P 以及 BO 候选初筛；未标定，因此
    predict() 的 uncertainty 固定为 None（§5.3 要求未标定不得伪造）。
    """

    def __init__(
        self,
        input_dim: int,
        output_dim: int = 1,
        hidden_sizes: Sequence[int] = DEFAULT_HIDDEN_SIZES,
        *,
        learning_rate: float = 1e-2,
        epochs: int = 400,
        seed: int = 42,
        weight_decay: float = 0.0,
    ) -> None:
        if type(input_dim) is not int or input_dim <= 0:
            raise SurrogateError("input_dim 必须是正整数")
        if type(output_dim) is not int or output_dim <= 0:
            raise SurrogateError("output_dim 必须是正整数")
        hidden = tuple(int(size) for size in hidden_sizes)
        if any(size <= 0 for size in hidden):
            raise SurrogateError("hidden_sizes 必须全为正整数")
        if learning_rate <= 0.0:
            raise SurrogateError("learning_rate 必须为正")
        if type(epochs) is not int or epochs <= 0:
            raise SurrogateError("epochs 必须为正整数")
        if weight_decay < 0.0:
            raise SurrogateError("weight_decay 不能为负")
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.hidden_sizes = hidden
        self.learning_rate = float(learning_rate)
        self.epochs = epochs
        self.seed = int(seed)
        self.weight_decay = float(weight_decay)
        self._weights: list[np.ndarray] = []
        self._biases: list[np.ndarray] = []
        self._feature_mean: np.ndarray | None = None
        self._feature_std: np.ndarray | None = None
        self._target_scale: float = 1.0
        self._fitted = False
        self._initialize()

    # -- 初始化 -----------------------------------------------------------
    def _initialize(self) -> None:
        rng = np.random.default_rng(self.seed)
        sizes = (self.input_dim, *self.hidden_sizes, self.output_dim)
        self._weights = []
        self._biases = []
        for fan_in, fan_out in zip(sizes[:-1], sizes[1:]):
            limit = math.sqrt(6.0 / (fan_in + fan_out))
            self._weights.append(rng.uniform(-limit, limit, size=(fan_in, fan_out)))
            self._biases.append(np.zeros(fan_out, dtype=np.float64))

    # -- 前向/反向 ---------------------------------------------------------
    def _forward(self, features: np.ndarray) -> tuple[list[np.ndarray], np.ndarray]:
        activations = [features]
        current = features
        for index, (weight, bias) in enumerate(zip(self._weights, self._biases)):
            linear = current @ weight + bias
            current = np.tanh(linear) if index < len(self._weights) - 1 else linear
            activations.append(current)
        return activations, current

    def fit(self, features: np.ndarray, targets: np.ndarray) -> "MLPRegressorSurrogate":
        matrix = _validate_feature_matrix(features, self.input_dim)
        labels = _validate_target_matrix(targets, self.output_dim)
        if matrix.shape[0] != labels.shape[0]:
            raise SurrogateError("特征与标签行数不一致")
        if matrix.shape[0] < 2:
            raise SurrogateError("至少需要 2 个样本才能拟合代理")
        self._feature_mean = matrix.mean(axis=0)
        std = matrix.std(axis=0)
        self._feature_std = np.where(std > 1e-12, std, 1.0)
        self._target_scale = max(float(np.std(labels)), 1e-12)
        normalized = (matrix - self._feature_mean) / self._feature_std
        normalized_targets = labels / self._target_scale
        momentum_w = [np.zeros_like(w) for w in self._weights]
        momentum_b = [np.zeros_like(b) for b in self._biases]
        velocity_w = [np.zeros_like(w) for w in self._weights]
        velocity_b = [np.zeros_like(b) for b in self._biases]
        beta1, beta2, epsilon = 0.9, 0.999, 1e-8
        n = normalized.shape[0]
        for step in range(1, self.epochs + 1):
            activations, output = self._forward(normalized)
            delta = (2.0 / (n * self.output_dim)) * (output - normalized_targets)
            grad_w: list[np.ndarray] = [np.zeros_like(w) for w in self._weights]
            grad_b: list[np.ndarray] = [np.zeros_like(b) for b in self._biases]
            for index in range(len(self._weights) - 1, -1, -1):
                grad_w[index] = activations[index].T @ delta
                grad_b[index] = delta.sum(axis=0)
                if index > 0:
                    delta = (delta @ self._weights[index].T) * (1.0 - activations[index] ** 2)
            for index in range(len(self._weights)):
                if self.weight_decay:
                    grad_w[index] = grad_w[index] + self.weight_decay * self._weights[index]
                momentum_w[index] = beta1 * momentum_w[index] + (1 - beta1) * grad_w[index]
                momentum_b[index] = beta1 * momentum_b[index] + (1 - beta1) * grad_b[index]
                velocity_w[index] = beta2 * velocity_w[index] + (1 - beta2) * grad_w[index] ** 2
                velocity_b[index] = beta2 * velocity_b[index] + (1 - beta2) * grad_b[index] ** 2
                m_hat_w = momentum_w[index] / (1 - beta1**step)
                m_hat_b = momentum_b[index] / (1 - beta1**step)
                v_hat_w = velocity_w[index] / (1 - beta2**step)
                v_hat_b = velocity_b[index] / (1 - beta2**step)
                self._weights[index] = self._weights[index] - self.learning_rate * m_hat_w / (
                    np.sqrt(v_hat_w) + epsilon
                )
                self._biases[index] = self._biases[index] - self.learning_rate * m_hat_b / (
                    np.sqrt(v_hat_b) + epsilon
                )
        self._fitted = True
        return self

    def predict(self, features: np.ndarray) -> SurrogatePrediction:
        if not self._fitted:
            raise SurrogateError("代理尚未拟合")
        matrix = _validate_feature_matrix(features, self.input_dim)
        normalized = (matrix - self._feature_mean) / self._feature_std
        _, output = self._forward(normalized)
        mean = output * self._target_scale
        if self.output_dim == 1:
            mean = mean[:, 0]
        return SurrogatePrediction(mean=mean)


def _validate_feature_matrix(features: np.ndarray, input_dim: int) -> np.ndarray:
    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2:
        raise SurrogateError(f"features 必须为二维数组，实际 {matrix.shape}")
    if matrix.shape[1] != input_dim:
        raise SurrogateError(f"features 列数应为 {input_dim}，实际 {matrix.shape[1]}")
    if matrix.shape[0] == 0:
        raise SurrogateError("features 不能为空")
    if not np.all(np.isfinite(matrix)):
        raise SurrogateError("features 包含非有限值")
    return matrix


def _validate_target_matrix(targets: np.ndarray, output_dim: int) -> np.ndarray:
    matrix = np.asarray(targets, dtype=np.float64)
    if matrix.ndim == 1:
        if output_dim != 1:
            raise SurrogateError(f"标签应为一维，实际 {matrix.shape}")
        matrix = matrix[:, None]
    if matrix.ndim != 2:
        raise SurrogateError(f"targets 必须为二维数组，实际 {matrix.shape}")
    if matrix.shape[1] != output_dim:
        raise SurrogateError(f"标签列数应为 {output_dim}，实际 {matrix.shape[1]}")
    if matrix.shape[0] == 0:
        raise SurrogateError("targets 不能为空")
    if not np.all(np.isfinite(matrix)):
        raise SurrogateError("targets 包含非有限值")
    return matrix


__all__ = [
    "DEFAULT_HIDDEN_SIZES",
    "MAX_TARGET_DIM",
    "MLPRegressorSurrogate",
    "ResponseSurrogate",
    "SurrogateError",
    "SurrogatePrediction",
    "TOP_K_OVERLAP_K",
    "encode_features",
    "regression_metrics",
    "select_objective_and_constraint_targets",
]
