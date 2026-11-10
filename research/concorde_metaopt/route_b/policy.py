"""路线B元采集策略 MetaAcquisitionPolicy（可学习采集评分）。

核心约束（泄漏防护）：

- 策略输入 = 已实际评价历史 history（只含 EvaluatedPoint） + 固定候选池坐标 +
  任务上下文（不含 split/task_id）。**没有**任何真实标签、未见候选标签、
  未来 query 或 holdout 信息进入特征。
- 候选池只提供坐标；其 objective/constraints 从未被策略或特征函数读取。
- 训练目标：离线轨迹上的"此后总奖励"回归（直接法 / direct method）。
  由于未选中候选的真实标签在离线数据中不可观测，本原型**不做**反事实估计，
  这是当前 NOT_READY 结论的主要科学原因之一。

策略结构：标准化特征 -> 2 层 tanh MLP -> 标量采集评分；评测时对候选池取 argmax
（排除已评价点），因此学习到的是"下一个候选选择"而不是初始点排序。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .contracts import (
    CandidatePool,
    ObservationHistory,
    RouteBContractError,
    TaskContext,
    canonical_json,
)
from .baselines import design_key

FEATURE_VERSION = "route-b-policy-features-v1"
POLICY_VERSION = "route-b-meta-acquisition-v1"
DEFAULT_LENGTH_SCALE = 0.35
DEFAULT_TOP_K = 3
FEATURE_CLIP = 10.0


def feature_names(dim: int) -> Tuple[str, ...]:
    """特征列名（与 build_features 的列顺序严格一致）。"""
    names: List[str] = ["x_%d" % index for index in range(dim)]
    names += [
        "nearest_eval",
        "nearest_feasible",
        "surrogate_pred_norm",
        "surrogate_uncertainty",
        "surrogate_p_feasible",
        "predicted_improvement",
        "n_over_budget",
        "n_feasible_over_budget",
        "budget_remaining_fraction",
        "has_feasible",
        "rank_nearest",
        "rank_pred",
        "rank_p_feasible",
        "ctx_dim_over_12",
        "ctx_budget_over_64",
        "ctx_synthetic_flag",
    ]
    return tuple(names)


def feature_dim(dim: int) -> int:
    return len(feature_names(dim))


def _pairwise_distances(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    diff = a[:, None, :] - b[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=2))


def _rank_percentile(values: np.ndarray) -> np.ndarray:
    if values.size <= 1:
        return np.zeros_like(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(values.size, dtype=float)
    return ranks / float(values.size - 1)


def build_features(
    history: ObservationHistory,
    pool: CandidatePool,
    context: Optional[TaskContext] = None,
    length_scale: float = DEFAULT_LENGTH_SCALE,
    top_k: int = DEFAULT_TOP_K,
) -> np.ndarray:
    """由**已评价历史** + 候选池坐标构造策略特征矩阵 (n_candidates, feature_dim)。

    显式拒绝：任何 history 中的代理标签都会在 ObservationHistory 层抛错，
    因此本函数拿到的输入天然只含真实评价记录。
    """
    if history.dim != pool.dim:
        raise RouteBContractError("history.dim=%d 与 pool.dim=%d 不一致" % (history.dim, pool.dim))
    candidates = pool.array()
    n_candidates = candidates.shape[0]
    dim = candidates.shape[1]
    columns: List[np.ndarray] = [candidates[:, axis] for axis in range(dim)]

    nearest = np.ones(n_candidates, dtype=float)
    nearest_feasible = np.ones(n_candidates, dtype=float)
    predicted = np.zeros(n_candidates, dtype=float)
    uncertainty = np.ones(n_candidates, dtype=float)
    p_feasible = np.full(n_candidates, 0.5, dtype=float)
    predicted_improvement = np.zeros(n_candidates, dtype=float)
    n_fraction = np.zeros(n_candidates, dtype=float)
    n_feasible_fraction = np.zeros(n_candidates, dtype=float)
    budget_remaining = np.ones(n_candidates, dtype=float)
    has_feasible = np.zeros(n_candidates, dtype=float)

    if history.n > 0:
        designs = history.designs_array()
        objectives = history.objectives_array()
        feasible_mask = history.feasible_mask()
        distances = _pairwise_distances(candidates, designs)
        nearest = distances.min(axis=1)
        if feasible_mask.any():
            nearest_feasible = distances[:, feasible_mask].min(axis=1)
        weights = np.exp(-0.5 * (distances / float(length_scale)) ** 2)
        weight_sum = weights.sum(axis=1, keepdims=True)
        weight_sum = np.clip(weight_sum, 1e-12, None)
        normalized = weights / weight_sum
        valid = ~np.isnan(objectives)
        if valid.any():
            values = objectives[valid]
            location = float(np.mean(values))
            spread = float(np.std(values))
            spread = spread if spread > 1e-12 else 1.0
            filled = np.where(valid, objectives, location)
            raw_prediction = normalized @ filled
            predicted = (raw_prediction - location) / spread
            if history.best_feasible is not None:
                predicted_improvement = np.maximum(
                    0.0, (history.best_feasible - raw_prediction) / spread
                )
        uncertainty = 1.0 - normalized.max(axis=1)
        p_feasible = normalized @ feasible_mask.astype(float)
        budget = float(context.budget) if context is not None else float(max(history.n + 1, 1))
        n_fraction = np.full(n_candidates, history.n / max(budget, 1.0))
        n_feasible_fraction = np.full(n_candidates, float(feasible_mask.sum()) / max(budget, 1.0))
        budget_remaining = np.full(n_candidates, max(0.0, 1.0 - history.n / max(budget, 1.0)))
        has_feasible = np.full(n_candidates, 1.0 if feasible_mask.any() else 0.0)

    top_k = max(1, int(top_k))
    if history.n > 0:
        sorted_distances = np.sort(_pairwise_distances(candidates, history.designs_array()), axis=1)
        topk = sorted_distances[:, : min(top_k, sorted_distances.shape[1])].mean(axis=1)
    else:
        topk = np.ones(n_candidates, dtype=float)

    columns += [
        nearest,
        nearest_feasible,
        predicted,
        uncertainty,
        p_feasible,
        predicted_improvement,
        np.full(n_candidates, n_fraction[0] if n_fraction.size else 0.0),
        np.full(n_candidates, n_feasible_fraction[0] if n_feasible_fraction.size else 0.0),
        np.full(n_candidates, budget_remaining[0] if budget_remaining.size else 1.0),
        np.full(n_candidates, has_feasible[0] if has_feasible.size else 0.0),
        _rank_percentile(nearest),
        _rank_percentile(predicted),
        _rank_percentile(p_feasible),
    ]
    if context is None:
        context_features = (dim / 12.0, 0.0, 0.0)
    else:
        context_features = context.context_features()
    for value in context_features:
        columns.append(np.full(n_candidates, float(value)))
    matrix = np.column_stack(columns).astype(float)
    matrix = np.clip(np.nan_to_num(matrix, nan=0.0, posinf=FEATURE_CLIP, neginf=-FEATURE_CLIP), -FEATURE_CLIP, FEATURE_CLIP)
    expected = feature_dim(dim)
    if matrix.shape[1] != expected:
        raise RouteBContractError("特征列数 %d 与 feature_dim(%d) 不一致" % (matrix.shape[1], expected))
    return matrix


class MetaAcquisitionPolicy:
    """可学习采集评分 policy：features -> scalar score。"""

    def __init__(
        self,
        feature_input_dim: int,
        hidden: int = 32,
        seed: int = 0,
        params: Optional[Dict[str, Any]] = None,
        trained: bool = False,
    ) -> None:
        if feature_input_dim <= 0 or hidden <= 0:
            raise RouteBContractError("feature_input_dim/hidden 必须为正")
        self.feature_input_dim = int(feature_input_dim)
        self.hidden = int(hidden)
        self.seed = int(seed)
        self.trained = bool(trained)
        rng = np.random.default_rng(seed)
        if params is None:
            self.w1 = rng.normal(0.0, 1.0 / np.sqrt(feature_input_dim), (feature_input_dim, hidden))
            self.b1 = np.zeros(hidden, dtype=float)
            self.w2 = rng.normal(0.0, 1.0 / np.sqrt(hidden), (hidden,))
            self.b2 = 0.0
            self.feature_mean = np.zeros(feature_input_dim, dtype=float)
            self.feature_std = np.ones(feature_input_dim, dtype=float)
            self.target_mean = 0.0
            self.target_std = 1.0
        else:
            self.w1 = np.asarray(params["w1"], dtype=float)
            self.b1 = np.asarray(params["b1"], dtype=float)
            self.w2 = np.asarray(params["w2"], dtype=float)
            self.b2 = float(params["b2"])
            self.feature_mean = np.asarray(params["feature_mean"], dtype=float)
            self.feature_std = np.asarray(params["feature_std"], dtype=float)
            self.target_mean = float(params.get("target_mean", 0.0))
            self.target_std = float(params.get("target_std", 1.0))
        self._check_shapes()

    def _check_shapes(self) -> None:
        if self.w1.shape != (self.feature_input_dim, self.hidden):
            raise RouteBContractError("w1 形状错误: %r" % (self.w1.shape,))
        if self.b1.shape != (self.hidden,):
            raise RouteBContractError("b1 形状错误")
        if self.w2.shape != (self.hidden,):
            raise RouteBContractError("w2 形状错误")
        if self.feature_mean.shape != (self.feature_input_dim,):
            raise RouteBContractError("feature_mean 形状错误")
        if self.feature_std.shape != (self.feature_input_dim,):
            raise RouteBContractError("feature_std 形状错误")

    def forward(self, features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != self.feature_input_dim:
            raise RouteBContractError(
                "策略输入形状应为 (n, %d)，实际 %r" % (self.feature_input_dim, matrix.shape)
            )
        standardized = (matrix - self.feature_mean) / np.clip(self.feature_std, 1e-8, None)
        hidden = np.tanh(standardized @ self.w1 + self.b1)
        return hidden @ self.w2 + self.b2

    def score(
        self,
        history: ObservationHistory,
        pool: CandidatePool,
        context: Optional[TaskContext] = None,
    ) -> np.ndarray:
        features = build_features(history, pool, context)
        return self.forward(features)

    def select(
        self,
        history: ObservationHistory,
        pool: CandidatePool,
        context: Optional[TaskContext] = None,
        exclude_keys: Optional[set] = None,
    ) -> Tuple[int, np.ndarray]:
        scores = self.score(history, pool, context)
        values = np.array(scores, dtype=float, copy=True)
        values[~np.isfinite(values)] = -np.inf
        if exclude_keys:
            for index, design in enumerate(pool.designs):
                if design_key(design) in exclude_keys:
                    values[index] = -np.inf
        if not np.isfinite(values).any():
            return 0, scores
        return int(np.argmax(values)), scores

    def to_params(self) -> Dict[str, Any]:
        return {
            "policy_version": POLICY_VERSION,
            "feature_version": FEATURE_VERSION,
            "feature_input_dim": self.feature_input_dim,
            "hidden": self.hidden,
            "seed": self.seed,
            "trained": self.trained,
            "w1": self.w1.tolist(),
            "b1": self.b1.tolist(),
            "w2": self.w2.tolist(),
            "b2": float(self.b2),
            "feature_mean": self.feature_mean.tolist(),
            "feature_std": self.feature_std.tolist(),
            "target_mean": self.target_mean,
            "target_std": self.target_std,
        }

    @classmethod
    def from_params(cls, params: Dict[str, Any]) -> "MetaAcquisitionPolicy":
        return cls(
            feature_input_dim=int(params["feature_input_dim"]),
            hidden=int(params["hidden"]),
            seed=int(params.get("seed", 0)),
            params=params,
            trained=bool(params.get("trained", True)),
        )

    def save(self, path: Any) -> str:
        import hashlib
        from pathlib import Path

        payload = canonical_json(self.to_params())
        target = Path(str(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def load(cls, path: Any) -> "MetaAcquisitionPolicy":
        from pathlib import Path

        raw = Path(str(path)).read_text(encoding="utf-8")
        return cls.from_params(json.loads(raw))


class RandomScorePolicy:
    """负控：随机采集评分（与学习策略相同的选择代码路径，但评分随机）。"""

    def __init__(self, seed: int = 0) -> None:
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)

    def score(
        self,
        history: ObservationHistory,
        pool: CandidatePool,
        context: Optional[TaskContext] = None,
    ) -> np.ndarray:
        return self.rng.standard_normal(len(pool))

    def select(
        self,
        history: ObservationHistory,
        pool: CandidatePool,
        context: Optional[TaskContext] = None,
        exclude_keys: Optional[set] = None,
    ) -> Tuple[int, np.ndarray]:
        scores = self.score(history, pool, context)
        values = np.array(scores, dtype=float, copy=True)
        if exclude_keys:
            for index, design in enumerate(pool.designs):
                if design_key(design) in exclude_keys:
                    values[index] = -np.inf
        if not np.isfinite(values).any():
            return 0, scores
        return int(np.argmax(values)), scores

def select_candidate(
    policy: Any,
    history: ObservationHistory,
    pool: CandidatePool,
    context: Optional[TaskContext],
    exclude_keys: Optional[set],
) -> Tuple[int, np.ndarray]:
    """统一选择入口：兼容带/不带 context 参数的策略（标准采集无 context）。"""
    import inspect

    params = inspect.signature(policy.select).parameters
    if "context" in params:
        return policy.select(history, pool, context=context, exclude_keys=exclude_keys)
    return policy.select(history, pool, exclude_keys=exclude_keys)
