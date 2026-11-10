"""路线A 合成 12 维任务族（SYNTHETIC_ANALOGUE，physical_call_count=0）。

本模块为“优化器无关热启动”提供受控、可复现、可配难度的 12 维基准问题，
用于 BO / DE / PSO 三种后端的同预算、同任务配对比较。所有目标值与约束值
都由解析函数生成，不来自 VSPAERO / SU2 / RCAIDE Mission / WaveDrag，
也不得被解释为真实物理结果（source_kind = SYNTHETIC_ANALOGUE）。

两个任务族：
* S-QC「二次耦合 + 双椭球约束竞争」：目标为带非线性耦合项
  0.7 * u2 * u3 的加权二次型；两个球心不同的二次约束互相挤压，
  可行域是两球交集，最优解通常落在约束边界上。
* S-RB「Rosenbrock 型耦合 + 线性带/球约束竞争」：目标为 12 维
  Rosenbrock 链（无约束最优在 u=1 角落，通常不可行）；约束为
  “均值带 + 二阶矩球”，可行域位于积分平均意义下的中心区域；
  阈值经调参使随机可行率约 20%（附录 receipt 记录调参过程）。

任务上下文 context=(c1, c2) 会平移目标中心与约束球心，因此不同 context
构成同一分布下的不同“任务”，可用于 few-shot 元学习（meta-train / meta-test
按 context 划分）。
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np

DIMENSION = 12
CONTEXT_DIM = 2
FEATURE_DIM = DIMENSION + CONTEXT_DIM
SOURCE_KIND = "SYNTHETIC_ANALOGUE"
PHYSICAL_CALL_COUNT = 0
STAGE = "D-NEXT-001-route-a-warm-start"
FAMILY_COUPLED_QUADRATIC = "S-QC"
FAMILY_ROSENBROCK_BAND = "S-RB"
FAMILIES: Tuple[str, ...] = (FAMILY_COUPLED_QUADRATIC, FAMILY_ROSENBROCK_BAND)
REFERENCE_METHOD = "scipy.optimize.minimize(method=SLSQP, multistart, deterministic seed)"

_INDEX = np.arange(DIMENSION, dtype=float)


def _as_unit_matrix(values: Any, label: str = "unit_matrix") -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix[None, :]
    if matrix.ndim != 2 or matrix.shape[1] != DIMENSION:
        raise ValueError("%s 必须是形状 (n, %d) 的二维数组，实际 %r" % (label, DIMENSION, matrix.shape))
    if not np.all(np.isfinite(matrix)):
        raise ValueError("%s 包含非有限值" % label)
    if np.any(matrix < -1e-12) or np.any(matrix > 1.0 + 1e-12):
        raise ValueError("%s 必须位于单位超立方体 [0, 1]^%d 内" % (label, DIMENSION))
    return np.clip(matrix, 0.0, 1.0)


def _normalize_context(context: Any) -> Tuple[float, float]:
    if isinstance(context, Mapping):
        values = [float(context["context_1"]), float(context["context_2"])]
    else:
        values = [float(value) for value in context]
        if len(values) != CONTEXT_DIM:
            raise ValueError("task context 必须包含 %d 个分量" % CONTEXT_DIM)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("task context 必须是有限实数")
    return (values[0], values[1])


@dataclass(frozen=True)
class SyntheticTask:
    """一个 12 维合成任务（族 + 上下文 + 固定 seed）。"""

    family: str
    context: Tuple[float, float]
    seed: int = 20261110

    def __post_init__(self) -> None:
        if self.family not in FAMILIES:
            raise ValueError("未知任务族 %r，可选 %r" % (self.family, FAMILIES))
        object.__setattr__(self, "context", _normalize_context(self.context))

    @property
    def task_id(self) -> str:
        payload = "%s|%.6f|%.6f|%d" % (self.family, self.context[0], self.context[1], self.seed)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]

    def features(self, designs: Any) -> np.ndarray:
        """代理模型输入：12 维设计 + 2 维任务上下文。"""
        matrix = _as_unit_matrix(designs, "designs")
        context = np.tile(np.asarray(self.context, dtype=float), (matrix.shape[0], 1))
        return np.hstack([matrix, context])

    @property
    def constraint_names(self) -> Tuple[str, ...]:
        if self.family == FAMILY_COUPLED_QUADRATIC:
            return ("g_ball_obj_shift", "g_ball_context_shift")
        return ("g_mean_upper", "g_mean_lower", "g_second_moment")

    def truth(self, designs: Any) -> Dict[str, Any]:
        """解析真值：目标、各约束 g<=0、可行性与最小约束裕度。"""
        u = _as_unit_matrix(designs, "designs")
        if self.family == FAMILY_COUPLED_QUADRATIC:
            objective, constraints = self._truth_coupled_quadratic(u)
        else:
            objective, constraints = self._truth_rosenbrock_band(u)
        stacked = np.column_stack([constraints[name] for name in self.constraint_names])
        margin = np.min(stacked, axis=1)
        feasible = np.all(stacked <= 0.0, axis=1)
        return {
            "objective": objective,
            "constraints": constraints,
            "constraint_margin": margin,
            "feasibility": feasible,
            "task_id": self.task_id,
            "source_kind": SOURCE_KIND,
            "physical_call_count": PHYSICAL_CALL_COUNT,
        }

    def _truth_coupled_quadratic(self, u: np.ndarray) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        c1, c2 = self.context
        center = 0.5 + 0.10 * c1 * np.cos(0.9 * _INDEX + 0.4 * c2) + 0.05 * c2
        weights = 1.0 + 0.25 * np.sin(1.7 * _INDEX + c1)
        diff = u - center
        objective = (
            np.sum(weights * diff * diff, axis=1)
            + 0.9 * (u[:, 0] - u[:, 1]) ** 2
            + 0.7 * u[:, 2] * u[:, 3]
            + 0.35 * np.cos(2.0 * math.pi * u[:, 4] + c2)
        )
        mu1 = 0.5 + 0.08 * c1 * np.sin(0.7 * _INDEX) - 0.06 * c2
        g1 = np.mean((u - mu1) ** 2, axis=1) - 0.080
        mu2 = 0.5 + 0.10 * c2 * np.cos(1.1 * _INDEX) + 0.05 * c1
        g2 = np.mean((u - mu2) ** 2, axis=1) - 0.085
        return objective, {"g_ball_obj_shift": g1, "g_ball_context_shift": g2}

    def _truth_rosenbrock_band(self, u: np.ndarray) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        c1, c2 = self.context
        x = 2.0 * u - 1.0
        chain = np.zeros(u.shape[0], dtype=float)
        for index in range(DIMENSION - 1):
            chain += (x[:, index + 1] - x[:, index] ** 2) ** 2 + 0.1 * (1.0 - x[:, index]) ** 2
        objective = (
            chain / (DIMENSION - 1)
            + 0.40 * c1 * np.mean(x, axis=1)
            + 0.30 * c2 * x[:, 0]
            + 0.20 * np.mean(np.sin(3.0 * math.pi * x[:, 5:9]), axis=1)
        )
        mean_x = np.mean(x, axis=1)
        second_moment = np.mean(x * x, axis=1)
        return objective, {
            "g_mean_upper": mean_x - 0.10 - 0.03 * c1,
            "g_mean_lower": -mean_x - 0.10 + 0.03 * c2,
            "g_second_moment": second_moment - 0.30,
        }

    def evaluate_unit(self, vector: Any) -> Dict[str, Any]:
        """单点真值评价（供优化后端 evaluator 回调用）。"""
        result = self.truth(np.asarray(vector, dtype=float).reshape(1, -1))
        return {
            "status": "VALID",
            "valid": True,
            "feasible": bool(result["feasibility"][0]),
            "objective": float(result["objective"][0]),
            "constraints_g_le_zero": {
                name: float(values[0]) for name, values in result["constraints"].items()
            },
            "constraint_margin": float(result["constraint_margin"][0]),
            "analysis_calls": 0,
            "physical_call_count": PHYSICAL_CALL_COUNT,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "family": self.family,
            "context": list(self.context),
            "seed": int(self.seed),
            "source_kind": SOURCE_KIND,
            "physical_call_count": PHYSICAL_CALL_COUNT,
            "constraint_names": list(self.constraint_names),
        }


def make_task(family: str, context: Sequence[float], seed: int = 20261110) -> SyntheticTask:
    return SyntheticTask(family=family, context=_normalize_context(context), seed=int(seed))


def meta_train_tasks(family: str, count: int = 6, seed: int = 20261110) -> list:
    """元训练任务：同族、不同上下文（上下文是任务身份）。"""
    if family not in FAMILIES:
        raise ValueError("未知任务族 %r" % (family,))
    if count < 1:
        raise ValueError("count 必须为正整数")
    rng = np.random.default_rng(seed + (0 if family == FAMILY_COUPLED_QUADRATIC else 17))
    contexts = rng.uniform(-1.0, 1.0, size=(count, CONTEXT_DIM))
    return [SyntheticTask(family, (float(a), float(b)), seed) for a, b in contexts]


def evaluation_tasks(seed: int = 20261110) -> list:
    """评测任务：每个族一个留出的上下文（不参与元训练）。"""
    return [
        SyntheticTask(FAMILY_COUPLED_QUADRATIC, (0.55, -0.65), seed),
        SyntheticTask(FAMILY_ROSENBROCK_BAND, (-0.70, 0.45), seed),
    ]


def feasible_rate_estimate(
    task: SyntheticTask, n_samples: int = 20000, seed: int = 0
) -> Dict[str, Any]:
    rng = np.random.default_rng(seed)
    designs = rng.random((int(n_samples), DIMENSION))
    truth = task.truth(designs)
    feasible = int(np.count_nonzero(truth["feasibility"]))
    return {
        "n_samples": int(n_samples),
        "feasible_count": feasible,
        "feasible_rate": float(feasible) / float(n_samples),
        "best_objective_in_sample": float(np.min(truth["objective"])),
        "source_kind": SOURCE_KIND,
        "physical_call_count": PHYSICAL_CALL_COUNT,
    }


def reference_solution(
    task: SyntheticTask,
    n_starts: int = 32,
    n_prefilter: int = 4000,
    seed: int = 0,
) -> Dict[str, Any]:
    """用 scipy SLSQP 多起点求约束最优参考解（合成问题，物理调用=0）。

    先随机采样 n_prefilter 个设计并按“先可行性、再目标值”排序，取若干可行
    样本作为起点；其余起点为随机点。只有真正满足全部约束的候选才会被记为
    参考解；找不到可行解时如实返回 objective_star=None。
    """
    from scipy.optimize import minimize

    rng = np.random.default_rng(seed)
    prefilter = rng.random((int(n_prefilter), DIMENSION))
    pre_truth = task.truth(prefilter)
    feasible_index = np.flatnonzero(pre_truth["feasibility"])
    starts: list = []
    if feasible_index.size:
        order = feasible_index[np.argsort(pre_truth["objective"][feasible_index])]
        takes = min(int(n_starts) * 2 // 3, order.size)
        starts.extend(prefilter[order[:takes]])
    while len(starts) < int(n_starts):
        starts.append(rng.random(DIMENSION))

    names = task.constraint_names
    bounds = [(0.0, 1.0)] * DIMENSION
    constraints = [
        {
            "type": "ineq",
            "fun": (lambda vector, name=name: -float(task.truth(vector.reshape(1, -1))["constraints"][name][0])),
        }
        for name in names
    ]

    def objective(vector: np.ndarray) -> float:
        return float(task.truth(vector.reshape(1, -1))["objective"][0])

    best: Optional[Dict[str, Any]] = None
    attempts: list = []
    for start in starts:
        try:
            result = minimize(
                objective,
                np.asarray(start, dtype=float),
                method="SLSQP",
                bounds=bounds,
                constraints=constraints,
                options={"maxiter": 250, "ftol": 1e-12},
            )
        except Exception as exc:  # pragma: no cover - scipy 数值失败时如实记录
            attempts.append({"status": "EXCEPTION", "detail": "%s: %s" % (type(exc).__name__, exc)})
            continue
        vector = np.clip(np.asarray(result.x, dtype=float), 0.0, 1.0)
        check = task.evaluate_unit(vector)
        attempts.append(
            {
                "status": str(result.status),
                "success": bool(result.success),
                "objective": float(check["objective"]),
                "feasible": bool(check["feasible"]),
            }
        )
        if not check["feasible"]:
            continue
        candidate = {
            "objective_star": float(check["objective"]),
            "design_star": [float(value) for value in vector],
            "constraints": dict(check["constraints_g_le_zero"]),
            "feasible": True,
        }
        if best is None or candidate["objective_star"] < best["objective_star"]:
            best = candidate
    if best is None:
        return {
            "task_id": task.task_id,
            "status": "NO_FEASIBLE_REFERENCE",
            "objective_star": None,
            "design_star": None,
            "method": REFERENCE_METHOD,
            "n_starts": int(n_starts),
            "attempts": attempts,
            "source_kind": SOURCE_KIND,
            "physical_call_count": PHYSICAL_CALL_COUNT,
        }
    payload = {
        "task_id": task.task_id,
        "family": task.family,
        "context": list(task.context),
        "status": "VALID",
        "objective_star": best["objective_star"],
        "design_star": best["design_star"],
        "constraints": best["constraints"],
        "method": REFERENCE_METHOD,
        "n_starts": int(n_starts),
        "n_prefilter": int(n_prefilter),
        "source_kind": SOURCE_KIND,
        "physical_call_count": PHYSICAL_CALL_COUNT,
    }
    payload["reference_sha256"] = hashlib.sha256(
        ("%s|%.12f" % (task.task_id, best["objective_star"])).encode("utf-8")
    ).hexdigest()
    return payload
