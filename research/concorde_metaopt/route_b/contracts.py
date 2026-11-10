"""路线B（元采集策略）数据与泄漏防护契约。

本模块只定义**数据结构与不变量**，不含任何物理求解器调用、不含任何学习算法。
所有实验必须满足：

1. physical_call_count = 0：本原型只允许合成/解析任务或归档 replay（只读）。
2. 策略可观测历史 ObservationHistory 只接受**已实际评价**的 EvaluatedPoint；
   代理预测/假标签（proxy label）一律禁止进入 history。
3. 任务划分 split 只用于数据集与评测编排，**不得**进入策略特征；
   TaskContext.context_features() 显式排除 task_id 与 split。
4. 轨迹记录只保存候选池坐标与该步被选中的动作，**不保存未选中候选的标签**，
   避免离线价值学习出现未观测反事实泄漏。

术语：本模块产物均标记 source_kind=synthetic_analogue，即"合成类比任务"，
不代表 12D Concorde 真实气动响应，也不构成任何真实燃油/阻力结论。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

SOURCE_SYNTHETIC_ANALOGUE = "synthetic_analogue"
SOURCE_ARCHIVAL_REPLAY = "archival_replay"
SOURCE_TYPE = "synthetic"
PHYSICAL_CALL_COUNT = 0

HISTORY_SOURCE_EVALUATED = "evaluated"
ALLOWED_HISTORY_SOURCES = (HISTORY_SOURCE_EVALUATED,)

TASK_SPLITS = ("train", "val", "test")
STATUS_VALID = "VALID"
STATUS_FAILED = "FAILED"
STATUS_INVALID = "GEOMETRY_INVALID"

DesignVector = Tuple[float, ...]


class RouteBContractError(ValueError):
    """路线B契约被违反。"""


class ProxyLabelError(RouteBContractError):
    """试图把代理预测/假标签写入已评价历史。"""


class LeakageError(RouteBContractError):
    """训练/验证/测试任务或未来信息发生泄漏。"""


def _as_design(design: Sequence[float], dim: int, name: str = "design") -> DesignVector:
    if isinstance(design, np.ndarray):
        values = design.reshape(-1).tolist()
    else:
        values = list(design)
    if len(values) != dim:
        raise RouteBContractError("%s 维度应为 %d，实际 %d" % (name, dim, len(values)))
    out: List[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float, np.floating, np.integer)):
            raise RouteBContractError("%s 含非数值元素: %r" % (name, value))
        number = float(value)
        if not math.isfinite(number):
            raise RouteBContractError("%s 含非有限元素: %r" % (name, value))
        out.append(number)
    return tuple(out)


@dataclass(frozen=True)
class TaskContext:
    """任务上下文（允许进入策略输入的部分）。

    split 与 task_id 是评测编排信息，**不进入**特征向量。
    """

    task_id: str
    split: str
    dim: int
    budget: int
    seed: int
    source_kind: str = SOURCE_SYNTHETIC_ANALOGUE
    physical_call_count: int = PHYSICAL_CALL_COUNT

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise RouteBContractError("task_id 必须为非空字符串")
        if self.split not in TASK_SPLITS:
            raise RouteBContractError("split 必须属于 %r，实际 %r" % (TASK_SPLITS, self.split))
        if int(self.dim) <= 0:
            raise RouteBContractError("dim 必须为正整数")
        if int(self.budget) <= 0:
            raise RouteBContractError("budget 必须为正整数")
        if int(self.physical_call_count) != PHYSICAL_CALL_COUNT:
            raise RouteBContractError(
                "路线B原型只允许 physical_call_count=0，实际 %r" % (self.physical_call_count,)
            )
        if self.source_kind not in (SOURCE_SYNTHETIC_ANALOGUE, SOURCE_ARCHIVAL_REPLAY):
            raise RouteBContractError("未知 source_kind: %r" % (self.source_kind,))

    def context_features(self) -> Tuple[float, ...]:
        """策略可见的任务上下文特征：不含 task_id、split、任何标签。"""
        return (
            float(self.dim) / 12.0,
            float(self.budget) / 64.0,
            1.0 if self.source_kind == SOURCE_SYNTHETIC_ANALOGUE else 0.0,
        )


@dataclass(frozen=True)
class EvaluatedPoint:
    """一条**已实际评价**的记录。失败/不可行时 objective 为 None 且计入成本。"""

    design: DesignVector
    objective: Optional[float]
    constraints: Tuple[float, ...]
    status: str = STATUS_VALID
    eval_index: int = 0
    source: str = HISTORY_SOURCE_EVALUATED

    def __post_init__(self) -> None:
        if self.source not in ALLOWED_HISTORY_SOURCES:
            raise ProxyLabelError(
                "history 只接受已实际评价记录，source=%r 属于代理/假标签" % (self.source,)
            )
        if self.status not in (STATUS_VALID, STATUS_FAILED, STATUS_INVALID):
            raise RouteBContractError("未知 status: %r" % (self.status,))
        if self.objective is not None:
            number = float(self.objective)
            if not math.isfinite(number):
                raise RouteBContractError("objective 必须有限或 None")
        for value in self.constraints:
            if not math.isfinite(float(value)):
                raise RouteBContractError("约束值必须有限")
        if int(self.eval_index) < 0:
            raise RouteBContractError("eval_index 不能为负")

    @property
    def constraint_violation(self) -> float:
        if not self.constraints:
            return -math.inf
        return float(max(float(v) for v in self.constraints))

    @property
    def feasible(self) -> bool:
        if self.status != STATUS_VALID or self.objective is None:
            return False
        return self.constraint_violation <= 0.0


class ObservationHistory:
    """只追加的已评价历史；拒绝代理标签，拒绝重复设计。"""

    def __init__(self, dim: int, context: Optional[TaskContext] = None) -> None:
        if int(dim) <= 0:
            raise RouteBContractError("dim 必须为正整数")
        self._dim = int(dim)
        self._context = context
        self._points: List[EvaluatedPoint] = []
        self._keys: set = set()

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def context(self) -> Optional[TaskContext]:
        return self._context

    @property
    def n(self) -> int:
        return len(self._points)

    @property
    def points(self) -> Tuple[EvaluatedPoint, ...]:
        return tuple(self._points)

    def __len__(self) -> int:
        return len(self._points)

    def _key(self, design: DesignVector) -> Tuple[float, ...]:
        return tuple(round(float(v), 12) for v in design)

    def append(self, point: EvaluatedPoint) -> None:
        if not isinstance(point, EvaluatedPoint):
            raise ProxyLabelError(
                "history.append 只接受 EvaluatedPoint，收到 %r" % (type(point).__name__,)
            )
        if point.source != HISTORY_SOURCE_EVALUATED:
            raise ProxyLabelError("history 只接受已实际评价记录")
        design = _as_design(point.design, self._dim, "point.design")
        key = self._key(design)
        if key in self._keys:
            raise RouteBContractError("重复设计不得重复写入 history（同一次评价只计一次成本）")
        if self._context is not None and point.eval_index != self.n:
            raise RouteBContractError(
                "eval_index 必须等于已有历史长度（当前 %d，收到 %d）" % (self.n, point.eval_index)
            )
        self._points.append(point)
        self._keys.add(key)

    def add_evaluated(
        self,
        design: Sequence[float],
        objective: Optional[float],
        constraints: Sequence[float],
        status: str = STATUS_VALID,
    ) -> EvaluatedPoint:
        """写入一条**已实际评价**记录（调用方负责确保其来自真实/合成评价器）。"""
        point = EvaluatedPoint(
            design=_as_design(design, self._dim),
            objective=None if objective is None else float(objective),
            constraints=tuple(float(v) for v in constraints),
            status=status,
            eval_index=self.n,
            source=HISTORY_SOURCE_EVALUATED,
        )
        self.append(point)
        return point

    def designs_array(self) -> np.ndarray:
        if not self._points:
            return np.zeros((0, self._dim), dtype=float)
        return np.asarray([p.design for p in self._points], dtype=float)

    def objectives_array(self) -> np.ndarray:
        values = [np.nan if p.objective is None else float(p.objective) for p in self._points]
        return np.asarray(values, dtype=float)

    def feasible_mask(self) -> np.ndarray:
        return np.asarray([p.feasible for p in self._points], dtype=bool)

    @property
    def best_feasible(self) -> Optional[float]:
        feasible = [p.objective for p in self._points if p.feasible and p.objective is not None]
        return None if not feasible else float(min(feasible))

    @property
    def feasibility_ratio(self) -> float:
        return 0.0 if not self._points else float(sum(p.feasible for p in self._points)) / self.n

    def evaluated_keys(self) -> set:
        return set(self._keys)

    def prefix(self, k: int) -> "ObservationHistory":
        """前 k 条历史的独立副本（用于严格复现"当时可见"状态）。"""
        if not (0 <= k <= self.n):
            raise RouteBContractError("prefix 越界: k=%d, n=%d" % (k, self.n))
        out = ObservationHistory(self._dim, self._context)
        for point in self._points[:k]:
            out.append(point)
        return out


@dataclass(frozen=True)
class CandidatePool:
    """固定候选池；坐标对策略可见，**标签不可见**（不含 objective/constraints）。"""

    pool_id: str
    designs: Tuple[DesignVector, ...]

    def __post_init__(self) -> None:
        if not self.pool_id:
            raise RouteBContractError("pool_id 不能为空")
        if len(self.designs) == 0:
            raise RouteBContractError("候选池不能为空")
        dim = len(self.designs[0])
        for design in self.designs:
            _as_design(design, dim, "pool.design")
            for value in design:
                if not 0.0 <= float(value) <= 1.0:
                    raise RouteBContractError("候选池坐标必须位于 [0,1]")

    @property
    def dim(self) -> int:
        return len(self.designs[0])

    def __len__(self) -> int:
        return len(self.designs)

    def array(self) -> np.ndarray:
        return np.asarray(self.designs, dtype=float)


@dataclass(frozen=True)
class RewardSpec:
    """奖励定义：可行改进 + 首次可行奖励 - 评价成本。

    目标为**最小化**。归一化改进以任务尺度 improvement_scale 计：
    improvement = max(0, prev_best - new_best) / improvement_scale。
    每次评价都扣除 cost_weight / budget，保证"多评价一次"本身有代价。
    """

    cost_weight: float = 0.05
    first_feasible_bonus: float = 0.05
    improvement_scale: float = 1.0

    def __post_init__(self) -> None:
        if self.cost_weight < 0.0 or self.first_feasible_bonus < 0.0:
            raise RouteBContractError("奖励权重不能为负")
        if self.improvement_scale <= 0.0:
            raise RouteBContractError("improvement_scale 必须为正")

    def step_reward(
        self,
        previous_best: Optional[float],
        objective: Optional[float],
        feasible: bool,
        budget: int,
        already_feasible: bool,
    ) -> float:
        if int(budget) <= 0:
            raise RouteBContractError("budget 必须为正")
        reward = -float(self.cost_weight) / float(budget)
        if not feasible or objective is None:
            return float(reward)
        value = float(objective) / float(self.improvement_scale)
        if previous_best is None:
            reward += float(self.first_feasible_bonus)
        else:
            previous = float(previous_best) / float(self.improvement_scale)
            reward += max(0.0, previous - value)
        if not already_feasible:
            reward += 0.0  # first_feasible_bonus 已在 previous_best is None 分支计入
        return float(reward)


def rewards_to_go(rewards: Sequence[float], gamma: float = 1.0) -> List[float]:
    """从后向前累计折扣回报；gamma=1 即为“此后总奖励”。"""
    if not 0.0 < gamma <= 1.0:
        raise RouteBContractError("gamma 必须位于 (0,1]")
    out = [0.0] * len(rewards)
    running = 0.0
    for index in range(len(rewards) - 1, -1, -1):
        running = float(rewards[index]) + gamma * running
        out[index] = running
    return out


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
