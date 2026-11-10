"""路线A 的优化器无关热启动采样接口。

本模块只负责「在真实评价之前，从候选池里选出一组初始设计」：
给定任务上下文、设计空间、K 个已观测共享支撑点与候选池，输出
ProposedDesigns。BO 采集函数、DE 差分变异、PSO 速度更新都**不在**本模块，
分别由 optimization/baseline_bo.py、baseline_de.py、baseline_pso.py 承担。

4 种来源：
* random：均匀随机 / LHS 候选池 + 贪心多样性挑选（无模型）。
* zero_shot_surrogate：随机初始化代理直接排序（零样本）。
* pretrain_supervised：普通有监督预训练代理排序；K>0 时只做输出偏置校准。
* fomaml_kshot：FOMAML 元训练代理 + K∈{0,1,3,5} 个共享观测做 inner_adapt。

所有 predicted_* 均为代理预测，绝不允许写回真实观测；physical_call_count=0。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .synthetic import DIMENSION, FEATURE_DIM, PHYSICAL_CALL_COUNT, SOURCE_KIND
from .surrogate import (
    SOURCE_FOMAML,
    SOURCE_PRETRAIN,
    SOURCE_ZERO_SHOT,
    SurrogateSnapshot,
    adapt_fomaml,
    calibrate_offset,
)

SOURCE_RANDOM = "random"
SOURCE_ZERO_SHOT = SOURCE_ZERO_SHOT
SOURCE_PRETRAIN = SOURCE_PRETRAIN
SOURCE_FOMAML_KSHOT = SOURCE_FOMAML
SOURCES: Tuple[str, ...] = (SOURCE_RANDOM, SOURCE_ZERO_SHOT, SOURCE_PRETRAIN, SOURCE_FOMAML_KSHOT)

DEFAULT_CANDIDATE_POOL = 256
_DESIGN_TOLERANCE = 1e-12


def sigmoid(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return 1.0 / (1.0 + np.exp(-np.clip(array, -30.0, 30.0)))


@dataclass(frozen=True)
class WarmStartConfig:
    """采样器配置（冻结；种子、支持集大小、多样性权重）。"""

    source: str = SOURCE_RANDOM
    support_size: int = 0
    diversity_weight: float = 0.0
    feasibility_weight: float = 1.0
    candidate_pool_size: int = DEFAULT_CANDIDATE_POOL
    seed: int = 42

    def __post_init__(self) -> None:
        if self.source not in SOURCES:
            raise ValueError("source 必须是 %r 之一" % (SOURCES,))
        if not isinstance(self.support_size, (int, np.integer)) or self.support_size < 0:
            raise ValueError("support_size 必须是非负整数")
        if not (0.0 <= float(self.diversity_weight) <= 1.0):
            raise ValueError("diversity_weight 必须在 [0,1]")
        if not (0.0 <= float(self.feasibility_weight) <= 10.0):
            raise ValueError("feasibility_weight 必须在 [0,10]")
        if int(self.candidate_pool_size) < 1:
            raise ValueError("candidate_pool_size 必须为正整数")
        if not isinstance(self.seed, (int, np.integer)) or int(self.seed) < 0:
            raise ValueError("seed 必须是非负整数")


@dataclass(frozen=True)
class ProposedDesigns:
    """一次热启动建议的完整结果（可归档 JSON）。"""

    X_init: np.ndarray
    rank_score: np.ndarray
    predicted_objective: Optional[np.ndarray]
    predicted_constraint_margin: Optional[np.ndarray]
    predicted_feasibility: Optional[np.ndarray]
    uncertainty: Optional[np.ndarray]
    uniformity_distance: float
    min_support_distance: float
    model_sha: str
    provenance: Dict[str, Any]
    sample_budget: Dict[str, Any]
    source: str
    seed: int
    n_new: int

    def to_dict(self) -> Dict[str, Any]:
        def _list(value: Optional[np.ndarray]) -> Optional[List[float]]:
            if value is None:
                return None
            return [float(item) for item in np.asarray(value, dtype=float)]

        return {
            "X_init": np.asarray(self.X_init, dtype=float).tolist(),
            "rank_score": _list(self.rank_score),
            "predicted_objective": _list(self.predicted_objective),
            "predicted_constraint_margin": _list(self.predicted_constraint_margin),
            "predicted_feasibility": _list(self.predicted_feasibility),
            "uncertainty": _list(self.uncertainty),
            "uniformity_distance": float(self.uniformity_distance),
            "min_support_distance": float(self.min_support_distance),
            "model_sha": self.model_sha,
            "provenance": dict(self.provenance),
            "sample_budget": dict(self.sample_budget),
            "source": self.source,
            "seed": int(self.seed),
            "n_new": int(self.n_new),
        }


@dataclass(frozen=True)
class _Support:
    designs: np.ndarray
    objective: np.ndarray
    margin: np.ndarray
    raw: Tuple[Mapping[str, Any], ...]


def _design_dimension(design_space: Any) -> int:
    if design_space is None:
        return DIMENSION
    if isinstance(design_space, (int, np.integer)):
        return int(design_space)
    for attribute in ("dimension", "design_dim"):
        value = getattr(design_space, attribute, None)
        if isinstance(value, (int, np.integer)):
            return int(value)
    variables = getattr(design_space, "variables", None)
    if variables is not None:
        try:
            return len(variables)
        except TypeError:  # pragma: no cover - 防御
            pass
    raise ValueError("无法从 design_space 推断设计维度")


def _as_unit_matrix(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 2 or array.shape[1] != DIMENSION:
        raise ValueError("%s 必须是 (n, %d) 数组" % (name, DIMENSION))
    if not np.all(np.isfinite(array)):
        raise ValueError("%s 含非有限值" % name)
    if np.any(array < -1e-9) or np.any(array > 1.0 + 1e-9):
        raise ValueError("%s 必须落在 [0,1] 单位超立方体内" % name)
    return np.clip(array, 0.0, 1.0)


def _min_constraint_margin(record: Mapping[str, Any]) -> float:
    margin = record.get("constraint_margin")
    if margin is not None:
        return float(margin)
    constraints = record.get("constraints_g_le_zero")
    if isinstance(constraints, Mapping) and constraints:
        return float(-max(float(value) for value in constraints.values()))
    result = record.get("result")
    if isinstance(result, Mapping):
        return _min_constraint_margin(result)
    return float("-inf")


def _support_from(observed_support: Any) -> _Support:
    if observed_support is None:
        empty = np.zeros((0, DIMENSION), dtype=float)
        return _Support(empty, np.zeros(0), np.zeros(0), tuple())
    if isinstance(observed_support, Mapping):
        payload = observed_support
        designs = payload.get("designs")
        if designs is None:
            designs = payload.get("unit_vectors")
        if designs is None:
            designs = payload.get("X")
        if designs is None:
            raise ValueError("observed_support 映射缺少 designs 键")
        matrix = _as_unit_matrix(designs, "observed_support.designs")
        records = payload.get("records") or payload.get("observations") or ()
        if records:
            margins = [_min_constraint_margin(item) for item in records]
            objectives = [float(item.get("objective", float("nan"))) for item in records]
            return _Support(matrix, np.asarray(objectives, dtype=float), np.asarray(margins, dtype=float), tuple(records))
        objectives = payload.get("objective")
        if objectives is None:
            objectives = payload.get("objectives")
        if objectives is None:
            raise ValueError("observed_support 缺少 objective")
        margins = payload.get("constraint_margin")
        if margins is None:
            margins = payload.get("constraint_margins")
        if margins is None:
            margins = [float("nan")] * matrix.shape[0]
        return _Support(
            matrix,
            np.asarray(objectives, dtype=float),
            np.asarray(margins, dtype=float),
            tuple(),
        )
    items = list(observed_support)
    if not items:
        empty = np.zeros((0, DIMENSION), dtype=float)
        return _Support(empty, np.zeros(0), np.zeros(0), tuple())
    designs: List[np.ndarray] = []
    objectives: List[float] = []
    margins: List[float] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("observed_support 序列元素必须是映射")
        vector = item.get("unit_vector")
        if vector is None:
            vector = item.get("design")
        if vector is None:
            vector = item.get("design_vector")
        if vector is None:
            raise ValueError("observed_support 记录缺少 unit_vector/design")
        designs.append(np.asarray(vector, dtype=float).reshape(DIMENSION))
        objectives.append(float(item.get("objective", float("nan"))))
        margins.append(_min_constraint_margin(item))
    matrix = _as_unit_matrix(np.vstack(designs), "observed_support")
    return _Support(matrix, np.asarray(objectives, dtype=float), np.asarray(margins, dtype=float), tuple(items))


def _task_features(task_context: Sequence[float], designs: np.ndarray, source: str) -> np.ndarray:
    """代理特征 = 12 维设计 + 2 维任务上下文（与 synthetic.SyntheticTask.features 一致）。"""
    matrix = np.asarray(designs, dtype=float)
    context = np.asarray(task_context, dtype=float).reshape(-1)
    if context.size == 0:
        raise ValueError("非随机来源需要任务上下文")
    tiled = np.tile(context, (matrix.shape[0], 1))
    return np.hstack([matrix, tiled])


def _lhs_pool(n_rows: int, rng: np.random.Generator) -> np.ndarray:
    """Latin Hypercube 候选池（每维分层随机）。"""
    rows = int(n_rows)
    pool = np.empty((rows, DIMENSION), dtype=float)
    for dim in range(DIMENSION):
        strata = (np.arange(rows, dtype=float) + rng.random(rows)) / rows
        pool[:, dim] = strata[rng.permutation(rows)]
    return pool


def _pairwise_distances(matrix: np.ndarray) -> np.ndarray:
    diff = matrix[:, None, :] - matrix[None, :, :]
    return np.sqrt(np.sum(diff * diff, axis=2))


def _dedupe(pool: np.ndarray, support: np.ndarray) -> np.ndarray:
    """去掉与支撑点（或池内已保留点）重合的候选。"""
    kept: List[int] = []
    keys = set()
    for index in range(pool.shape[0]):
        key = tuple(np.round(pool[index], 12))
        if key in keys:
            continue
        if support.shape[0] > 0:
            distance = np.sqrt(np.sum((support - pool[index]) ** 2, axis=1))
            if float(np.min(distance)) <= _DESIGN_TOLERANCE:
                continue
        keys.add(key)
        kept.append(index)
    return pool[np.asarray(kept, dtype=int)] if kept else np.zeros((0, DIMENSION))


def _greedy_select(
    pool: np.ndarray,
    score: np.ndarray,
    support: np.ndarray,
    n_new: int,
    diversity_weight: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """贪心选择：score + rho * 归一化最小距离（距离只由设计坐标决定）。"""
    count = pool.shape[0]
    if count < n_new:
        raise ValueError("候选池去重后仅 %d 个，少于 n_new=%d" % (count, n_new))
    distances = _pairwise_distances(pool)
    if support.shape[0] > 0:
        support_diff = pool[:, None, :] - support[None, :, :]
        min_distance = np.sqrt(np.sum(support_diff * support_diff, axis=2)).min(axis=1)
    else:
        min_distance = np.full(count, np.sqrt(DIMENSION), dtype=float)
    available = np.ones(count, dtype=bool)
    chosen: List[int] = []
    chosen_scores: List[float] = []
    chosen_distance: List[float] = []
    for _ in range(int(n_new)):
        scale = float(np.max(min_distance)) if float(np.max(min_distance)) > 1e-12 else 1.0
        combined = score + float(diversity_weight) * (min_distance / scale)
        combined = np.where(available, combined, -np.inf)
        index = int(np.argmax(combined))
        if not np.isfinite(combined[index]):
            raise ValueError("候选池已耗尽，无法选出第 %d 个设计" % (len(chosen) + 1))
        chosen.append(index)
        chosen_scores.append(float(score[index]))
        chosen_distance.append(float(min_distance[index]))
        available[index] = False
        min_distance = np.minimum(min_distance, distances[index])
    return (
        pool[np.asarray(chosen, dtype=int)],
        np.asarray(chosen_scores, dtype=float),
        np.asarray(chosen_distance, dtype=float),
    )


class WarmStartSampler:
    """优化器无关的热启动采样器（不包含 BO/DE/PSO 的搜索算子）。"""

    def __init__(self, config: WarmStartConfig, snapshot: Optional[SurrogateSnapshot] = None) -> None:
        if not isinstance(config, WarmStartConfig):
            raise TypeError("config 必须是 WarmStartConfig")
        if config.source != SOURCE_RANDOM:
            if snapshot is None:
                raise ValueError("source=%r 需要代理快照" % (config.source,))
            if snapshot.kind != config.source:
                raise ValueError("快照来源 %r 与配置来源 %r 不一致" % (snapshot.kind, config.source))
            if snapshot.config.input_dim != FEATURE_DIM:
                raise ValueError("代理快照特征维度必须是 %d" % FEATURE_DIM)
        self.config = config
        self.snapshot = snapshot

    # -- 主接口 --------------------------------------------------------
    def propose(
        self,
        task_context: Sequence[float],
        design_space: Any,
        observed_support: Any = None,
        candidate_pool: Any = None,
        n_new: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> ProposedDesigns:
        if n_new is None:
            raise ValueError("n_new 必须显式给出")
        n_new = int(n_new)
        if n_new < 1:
            raise ValueError("n_new 必须为正整数")
        dimension = _design_dimension(design_space)
        if dimension != DIMENSION:
            raise ValueError("本路线只支持 %d 维设计空间，收到 %d" % (DIMENSION, dimension))
        context = np.asarray(task_context, dtype=float).reshape(-1)
        if context.size not in (0, 2):
            raise ValueError("task_context 必须是 2 维（context_1, context_2）")
        if not np.all(np.isfinite(context)):
            raise ValueError("task_context 含非有限值")

        support = _support_from(observed_support)
        if support.designs.shape[0] != int(self.config.support_size):
            raise ValueError(
                "共享观测数 %d 与 support_size=%d 不一致"
                % (support.designs.shape[0], int(self.config.support_size))
            )
        if self.config.source != SOURCE_RANDOM and self.config.support_size > 0:
            if not np.all(np.isfinite(support.objective)):
                raise ValueError("共享观测 objective 必须有限")
            if not np.all(np.isfinite(support.margin)):
                raise ValueError("共享观测 constraint_margin 必须有限")

        pool_seed = int(self.config.seed if seed is None else seed)
        rng = np.random.default_rng(pool_seed)
        if candidate_pool is None:
            pool = _lhs_pool(int(self.config.candidate_pool_size), rng)
        else:
            pool = _as_unit_matrix(candidate_pool, "candidate_pool")
        pool = _dedupe(pool, support.designs)

        feats_pool = _task_features(task_context, pool, self.config.source)
        predicted = None
        uncertainty = None
        adapted = None
        if self.config.source == SOURCE_RANDOM:
            score = rng.random(pool.shape[0])
            model_sha = hashlib.sha256(
                json.dumps({"source": SOURCE_RANDOM, "seed": pool_seed, "dimension": DIMENSION}).encode("utf-8")
            ).hexdigest()
        else:
            assert self.snapshot is not None
            adapted = self.snapshot
            prior = self.snapshot.predict(feats_pool)
            if support.designs.shape[0] > 0:
                feats_support = _task_features(task_context, support.designs, self.config.source)
                scaled_support = self.snapshot.scaled_targets(np.column_stack([support.objective, support.margin]))
                if self.config.source == SOURCE_FOMAML_KSHOT:
                    adapted = adapt_fomaml(self.snapshot, feats_support, scaled_support)
                else:
                    adapted = calibrate_offset(self.snapshot, feats_support, scaled_support)
                if self.config.source == SOURCE_FOMAML_KSHOT:
                    posterior = adapted.predict(feats_pool)
                    uncertainty = np.sqrt(np.mean((posterior - prior) ** 2, axis=1))
            predicted_raw = adapted.predict(feats_pool)
            score = -predicted_raw[:, 0] + float(self.config.feasibility_weight) * sigmoid(predicted_raw[:, 1])
            model_sha = adapted.model_sha

        selection, chosen_scores, chosen_distance = _greedy_select(
            pool, score, support.designs, n_new, float(self.config.diversity_weight)
        )

        predicted_objective: Optional[np.ndarray] = None
        predicted_margin: Optional[np.ndarray] = None
        predicted_feasibility: Optional[np.ndarray] = None
        if self.config.source != SOURCE_RANDOM:
            selected_index = []
            for vector in selection:
                matched = np.flatnonzero(np.all(np.isclose(pool, vector, atol=0.0, rtol=0.0), axis=1))
                selected_index.append(int(matched[0]))
            selected_index_array = np.asarray(selected_index, dtype=int)
            selected_prediction = adapted.predict(feats_pool[selected_index_array])
            predicted_objective = selected_prediction[:, 0] * adapted.target_std[0] + adapted.target_mean[0]
            predicted_margin = selected_prediction[:, 1] * adapted.target_std[1] + adapted.target_mean[1]
            predicted_feasibility = sigmoid(selected_prediction[:, 1])
            if uncertainty is not None:
                uncertainty = uncertainty[selected_index_array]
            selected_feats = feats_pool[selected_index_array]
        else:
            selected_feats = None

        pairwise = _pairwise_distances(selection) if selection.shape[0] > 1 else np.zeros((1, 1))
        if selection.shape[0] > 1:
            upper = pairwise[np.triu_indices(selection.shape[0], k=1)]
            uniformity = float(np.mean(upper))
        else:
            uniformity = 0.0
        min_support_distance = float(np.mean(chosen_distance)) if chosen_distance.size else 0.0

        provenance: Dict[str, Any] = {
            "source": self.config.source,
            "source_kind": SOURCE_KIND,
            "physical_call_count": PHYSICAL_CALL_COUNT,
            "version": "warm-start-sampler-v1",
            "supported_sources": list(SOURCES),
            "task_context": [float(item) for item in context],
            "support_size": int(self.config.support_size),
            "candidate_pool_size": int(pool.shape[0]) + int(support.designs.shape[0]),
            "candidate_pool_after_dedupe": int(pool.shape[0]),
            "diversity_weight": float(self.config.diversity_weight),
            "feasibility_weight": float(self.config.feasibility_weight),
            "seed": pool_seed,
            "note": "采样模块不含 BO 采集函数 / DE 差分 / PSO 速度更新；预测不写回真实观测",
        }
        if self.snapshot is not None:
            provenance["model_kind"] = adapted.kind if adapted is not None else self.snapshot.kind
            provenance["model_version"] = self.snapshot.provenance.get("version")
            provenance["model_provenance"] = dict(adapted.provenance if adapted is not None else self.snapshot.provenance)
        elif self.config.source != SOURCE_RANDOM:
            raise RuntimeError("非随机来源必须提供代理快照")

        sample_budget = {
            "support_observations": int(self.config.support_size),
            "proposed": int(n_new),
            "planned_true_evaluations": int(self.config.support_size) + int(n_new),
            "physical_call_count": PHYSICAL_CALL_COUNT,
            "source_kind": SOURCE_KIND,
        }

        return ProposedDesigns(
            X_init=np.asarray(selection, dtype=float),
            rank_score=np.asarray(chosen_scores, dtype=float),
            predicted_objective=predicted_objective,
            predicted_constraint_margin=predicted_margin,
            predicted_feasibility=predicted_feasibility,
            uncertainty=uncertainty,
            uniformity_distance=uniformity,
            min_support_distance=min_support_distance,
            model_sha=str(model_sha),
            provenance=provenance,
            sample_budget=sample_budget,
            source=self.config.source,
            seed=pool_seed,
            n_new=n_new,
        )
