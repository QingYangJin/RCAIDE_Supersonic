"""路线B的标准约束 BO 采集基线：EI / UCB / PI（自建，未复用路线A采样器）。

说明：
- 本模块用**纯 numpy 高斯过程**（各向同性 RBF 核，单位超立方体）实现目标代理；
  约束用第二个 GP 拟合违反量 h(x)=max(0, max_j g_j(x))，以可行概率
  p_feas = Phi(-mu_h / sigma_h) 加权采集值（Gardner 等 2014 的约束 EI 思路）。
- EI/UCB/PI 分别对应 Jones 等 1998、Srinivas 等 2010、Kushner 1964 的标准定义。
- 本模块**不**导入路线A的 WarmStartSampler / MAML 采样器；路线B只做序贯候选选择。
- 所有函数只接受已评价历史（ObservationHistory）；不读取候选池标签（候选池本无标签）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from scipy.linalg import cho_factor, cho_solve, solve_triangular
from scipy.stats import norm

from .contracts import CandidatePool, ObservationHistory, RouteBContractError

ACQUISITION_NAMES = ("ei", "ucb", "pi")
DEFAULT_LENGTH_SCALE = 0.35
DEFAULT_NOISE = 1e-6
DEFAULT_UCB_BETA = 2.0


def design_key(design: Sequence[float]) -> Tuple[float, ...]:
    return tuple(round(float(v), 12) for v in design)


def _rbf(a: np.ndarray, b: np.ndarray, length_scale: float) -> np.ndarray:
    diff = a[:, None, :] - b[None, :, :]
    sq = np.sum(diff * diff, axis=2)
    return np.exp(-0.5 * sq / (length_scale * length_scale))


class GaussianProcess:
    """最小可用 GP 回归（RBF 核，输出标准化，Cholesky 求解）。"""

    def __init__(
        self,
        length_scale: float = DEFAULT_LENGTH_SCALE,
        noise: float = DEFAULT_NOISE,
        jitter: float = 1e-8,
    ) -> None:
        if length_scale <= 0.0:
            raise RouteBContractError("length_scale 必须为正")
        self.length_scale = float(length_scale)
        self.noise = float(noise)
        self.jitter = float(jitter)
        self._x: Optional[np.ndarray] = None
        self._y_mean = 0.0
        self._y_std = 1.0
        self._chol: Optional[np.ndarray] = None
        self._alpha: Optional[np.ndarray] = None

    @property
    def n(self) -> int:
        return 0 if self._x is None else int(self._x.shape[0])

    def fit(self, x: np.ndarray, y: np.ndarray) -> "GaussianProcess":
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float).reshape(-1)
        if x.ndim != 2 or x.shape[0] != y.shape[0]:
            raise RouteBContractError("GP.fit 输入形状不一致")
        if x.shape[0] == 0:
            self._x = None
            return self
        finite = np.isfinite(y)
        if not finite.any():
            self._x = None
            return self
        x = x[finite]
        y = y[finite]
        self._y_mean = float(np.mean(y))
        std = float(np.std(y))
        self._y_std = std if std > 1e-12 else 1.0
        z = (y - self._y_mean) / self._y_std
        k = _rbf(x, x, self.length_scale)
        k = k + (self.noise + self.jitter) * np.eye(x.shape[0])
        chol = cho_factor(k, lower=True, check_finite=True)
        self._x = x
        self._chol = (np.tril(chol[0]), True)
        self._alpha = cho_solve(chol, z)
        return self

    def predict(self, xs: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        xs = np.asarray(xs, dtype=float)
        if xs.ndim != 2:
            raise RouteBContractError("GP.predict 输入必须为二维")
        if self._x is None or self._alpha is None:
            return np.zeros(xs.shape[0]), np.ones(xs.shape[0])
        ks = _rbf(xs, self._x, self.length_scale)
        mean_z = ks @ self._alpha
        v = solve_triangular(self._chol[0], ks.T, lower=True, check_finite=True)
        var = 1.0 - np.sum(v * v, axis=0)
        var = np.clip(var, 1e-12, None)
        mean = mean_z * self._y_std + self._y_mean
        std = np.sqrt(var) * self._y_std
        return mean, std


def expected_improvement(mean: np.ndarray, std: np.ndarray, best: float, xi: float = 0.01) -> np.ndarray:
    """最小化 EI：EI = (best - mu - xi) Phi(z) + sigma phi(z)。"""
    std = np.clip(np.asarray(std, dtype=float), 1e-12, None)
    improvement = float(best) - np.asarray(mean, dtype=float) - float(xi)
    z = improvement / std
    return improvement * norm.cdf(z) + std * norm.pdf(z)


def probability_of_improvement(mean: np.ndarray, std: np.ndarray, best: float, xi: float = 0.01) -> np.ndarray:
    std = np.clip(np.asarray(std, dtype=float), 1e-12, None)
    z = (float(best) - np.asarray(mean, dtype=float) - float(xi)) / std
    return norm.cdf(z)


def lower_confidence_bound_score(
    mean: np.ndarray, std: np.ndarray, beta: float = DEFAULT_UCB_BETA
) -> np.ndarray:
    """最小化场景的 UCB 采集值（越大越好）：-mu + beta * sigma。"""
    return -np.asarray(mean, dtype=float) + float(beta) * np.asarray(std, dtype=float)


@dataclass
class StandardAcquisition:
    """标准约束采集：采集值 * 可行概率。"""

    name: str
    length_scale: float = DEFAULT_LENGTH_SCALE
    beta: float = DEFAULT_UCB_BETA
    xi: float = 0.01

    def __post_init__(self) -> None:
        if self.name not in ACQUISITION_NAMES:
            raise RouteBContractError("未知采集函数: %r" % (self.name,))

    def score_candidates(self, history: ObservationHistory, pool: CandidatePool) -> np.ndarray:
        if pool.dim != history.dim:
            raise RouteBContractError("候选池维度与历史维度不一致")
        candidates = pool.array()
        if history.n == 0:
            return np.zeros(len(pool), dtype=float)
        objectives = history.objectives_array()
        designs = history.designs_array()
        valid = ~np.isnan(objectives)
        if not valid.any():
            return np.zeros(len(pool), dtype=float)
        objective_model = GaussianProcess(length_scale=self.length_scale).fit(
            designs[valid], objectives[valid]
        )
        mean, std = objective_model.predict(candidates)
        best = float(np.min(objectives[valid]))
        if self.name == "ei":
            score = expected_improvement(mean, std, best, self.xi)
        elif self.name == "ucb":
            score = lower_confidence_bound_score(mean, std, self.beta)
        else:
            score = probability_of_improvement(mean, std, best, self.xi)
        violation = np.asarray(
            [max(0.0, float(max(point.constraints))) for point in history.points], dtype=float
        )
        if np.any(violation > 0.0) or np.any(violation == 0.0):
            violation_model = GaussianProcess(length_scale=self.length_scale).fit(designs, violation)
            mu_h, sd_h = violation_model.predict(candidates)
            sd_h = np.clip(sd_h, 1e-12, None)
            p_feasible = norm.cdf(-mu_h / sd_h)
            # 数值安全：避免全部为 0 导致无法区分
            score = score * np.clip(p_feasible, 1e-9, 1.0)
        return np.asarray(score, dtype=float)

    def select(
        self,
        history: ObservationHistory,
        pool: CandidatePool,
        exclude_keys: Optional[set] = None,
    ) -> Tuple[int, np.ndarray]:
        scores = self.score_candidates(history, pool)
        return _argmax_available(scores, pool, exclude_keys)


def _argmax_available(
    scores: np.ndarray, pool: CandidatePool, exclude_keys: Optional[set]
) -> Tuple[int, np.ndarray]:
    values = np.array(scores, dtype=float, copy=True)
    values[~np.isfinite(values)] = -np.inf
    if exclude_keys:
        for index, design in enumerate(pool.designs):
            if design_key(design) in exclude_keys:
                values[index] = -np.inf
    if not np.isfinite(values).any():
        # 候选池已全部评价：返回 0 号并保持 score 数组原样，由调用方判定预算
        return 0, np.asarray(scores, dtype=float)
    index = int(np.argmax(values))
    return index, np.asarray(scores, dtype=float)
