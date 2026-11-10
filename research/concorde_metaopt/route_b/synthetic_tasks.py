"""路线B合成类比任务分布（无物理求解器调用）。

本模块只生成**解析合成函数**，用于验证元采集策略的代码闭环、泄漏防护与
负控机制。它**不是** 12D Concorde 任务，不产生任何气动/燃油数值，不得用于
宣称真实工程收益。

任务族：单位超立方体 [0,1]^d 上带约束的二次型最小化问题

    f_t(x) = sum_i w_i (x_i - c_i)^2 + kappa * w_0 w_1 (x_0 - c_0)(x_1 - c_1)

约束（全部为 g_j(x) <= 0 形式，可行域非空且包含最优点 c）：

    g_1 = x_0 - 0.75
    g_2 = 0.10 - x_1
    g_3 = x_0 + x_1 - sum_bound

另设一个确定性"评价失败"区域（x_{d-1} > 0.995 时 status=FAILED、
objective=None），用于检验 null 目标与评价成本计账，物理调用数仍为 0。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .contracts import (
    CandidatePool,
    SOURCE_SYNTHETIC_ANALOGUE,
    STATUS_FAILED,
    STATUS_VALID,
    TaskContext,
)

SYNTHETIC_TASK_VERSION = "route-b-synthetic-v1"
DEFAULT_DIM = 6
DEFAULT_BUDGET = 12
DEFAULT_N_INIT = 4
DEFAULT_POOL_SIZE = 256
CONSTRAINT_NAMES = ("x0_upper", "x1_lower", "x0x1_sum")


@dataclass(frozen=True)
class SyntheticTask:
    """一个确定性的合成类比任务（解析函数，无求解器）。"""

    context: TaskContext
    center: Tuple[float, ...]
    weights: Tuple[float, ...]
    interaction: float
    sum_bound: float
    pool: CandidatePool
    f_star: float = 0.0

    @property
    def task_id(self) -> str:
        return self.context.task_id

    @property
    def split(self) -> str:
        return self.context.split

    @property
    def dim(self) -> int:
        return self.context.dim

    @property
    def budget(self) -> int:
        return self.context.budget

    def evaluate(self, design: Sequence[float]) -> Dict[str, object]:
        """合成评价：返回 status/objective/constraints/feasible/physical_call_count。"""
        x = np.asarray([float(v) for v in design], dtype=float)
        if x.shape != (self.dim,):
            raise ValueError("设计维度不匹配: %r" % (x.shape,))
        if not np.all(np.isfinite(x)):
            raise ValueError("设计含非有限值")
        center = np.asarray(self.center, dtype=float)
        weights = np.asarray(self.weights, dtype=float)
        delta = x - center
        objective = float(np.sum(weights * delta * delta))
        objective += float(self.interaction) * float(weights[0] * weights[1]) * float(
            delta[0] * delta[1]
        )
        # 约束设计：x1 必须落在窄带 [0.38, 0.62] 内，且 x0 + x1 <= sum_bound。
        # 窄带使"可行评价"成为非平凡事件（first_feasible_eval 有区分度），
        # 同时最优点 center 被限制在窄带内，保证 f_star = 0 可达。
        constraints = (
            float(x[1] - 0.62),
            float(0.38 - x[1]),
            float(x[0] + x[1] - self.sum_bound),
        )
        if float(x[-1]) > 0.995:
            return {
                "status": STATUS_FAILED,
                "objective": None,
                "constraints": constraints,
                "feasible": False,
                "physical_call_count": 0,
            }
        feasible = max(constraints) <= 0.0
        return {
            "status": STATUS_VALID,
            "objective": objective,
            "constraints": constraints,
            "feasible": feasible,
            "physical_call_count": 0,
        }


def _task_seed(task_id: str, split: str, index: int) -> int:
    base = "%s|%s|%d|%s" % (SYNTHETIC_TASK_VERSION, task_id, index, split)
    return int(hashlib.sha256(base.encode("utf-8")).hexdigest()[:8], 16) % (2**31 - 1)


def _latin_hypercube(n: int, dim: int, rng: np.random.Generator) -> np.ndarray:
    """确定性拉丁超立方采样（每维分层一次随机置换）。"""
    samples = np.empty((n, dim), dtype=float)
    for axis in range(dim):
        strata = (np.arange(n) + rng.random(n)) / n
        samples[:, axis] = strata[rng.permutation(n)]
    return np.clip(samples, 0.0, 1.0)


def make_candidate_pool(task_id: str, dim: int, size: int, seed: int) -> CandidatePool:
    rng = np.random.default_rng(seed)
    designs = _latin_hypercube(size, dim, rng)
    return CandidatePool(
        pool_id="pool-%s-%d" % (task_id, size),
        designs=tuple(tuple(float(v) for v in row) for row in designs),
    )


def make_task(
    task_id: str,
    split: str,
    index: int = 0,
    dim: int = DEFAULT_DIM,
    budget: int = DEFAULT_BUDGET,
    pool_size: int = DEFAULT_POOL_SIZE,
) -> SyntheticTask:
    """构造确定性合成任务；同一 (task_id, split, index) 永远得到同一任务。"""
    seed = _task_seed(task_id, split, index)
    rng = np.random.default_rng(seed)
    # 最优点位于约束可行域内部，f_star = 0（因此 gap_to_reference 可精确计算）
    center = rng.uniform(0.20, 0.55, size=dim)
    center[0] = float(np.clip(center[0], 0.20, 0.55))
    center[1] = float(np.clip(center[1], 0.42, 0.58))
    center[2] = float(np.clip(center[2], 0.20, 0.80))
    while center[0] + center[1] > 0.95:
        center[1] = float(center[1] * 0.9)
    weights = rng.uniform(0.5, 2.0, size=dim)
    interaction = 0.15
    sum_bound = 1.15
    context = TaskContext(
        task_id=task_id,
        split=split,
        dim=dim,
        budget=budget,
        seed=seed,
        source_kind=SOURCE_SYNTHETIC_ANALOGUE,
        physical_call_count=0,
    )
    pool = make_candidate_pool(task_id, dim, pool_size, seed + 7919)
    return SyntheticTask(
        context=context,
        center=tuple(float(v) for v in center),
        weights=tuple(float(v) for v in weights),
        interaction=interaction,
        sum_bound=sum_bound,
        pool=pool,
        f_star=0.0,
    )


DEFAULT_SPLIT_SIZES = {"train": 6, "val": 3, "test": 4}


def make_task_split(
    split_sizes: Optional[Dict[str, int]] = None,
    dim: int = DEFAULT_DIM,
    budget: int = DEFAULT_BUDGET,
    pool_size: int = DEFAULT_POOL_SIZE,
) -> Dict[str, List[SyntheticTask]]:
    """生成互不重叠的 train/val/test 任务集合（按 task_id 前缀绝对隔离）。"""
    sizes = dict(DEFAULT_SPLIT_SIZES if split_sizes is None else split_sizes)
    out: Dict[str, List[SyntheticTask]] = {"train": [], "val": [], "test": []}
    for split in ("train", "val", "test"):
        for index in range(int(sizes.get(split, 0))):
            task_id = "synth-%s-%02d" % (split, index)
            out[split].append(
                make_task(task_id, split, index, dim=dim, budget=budget, pool_size=pool_size)
            )
    _assert_disjoint(out)
    return out


def _assert_disjoint(tasks: Dict[str, Sequence[SyntheticTask]]) -> None:
    from .contracts import LeakageError

    ids = {split: {task.task_id for task in group} for split, group in tasks.items()}
    for left in ("train", "val", "test"):
        for right in ("train", "val", "test"):
            if left >= right:
                continue
            overlap = ids[left] & ids[right]
            if overlap:
                raise LeakageError("任务划分重叠 %s/%s: %r" % (left, right, sorted(overlap)))


def initial_design(task: SyntheticTask, n_init: int, seed: int) -> np.ndarray:
    """固定初始设计：同一 task + 同一 eval seed 下所有采集臂共享同一初始点。

    种子绑定 task_id，因此不同任务拥有不同初始点（否则 first_feasible_eval
    会因跨任务复用同一点而失去区分度）。
    """
    material = "%s|init|%s|%d" % (SYNTHETIC_TASK_VERSION, task.context.task_id, int(seed))
    init_seed = int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(init_seed)
    return _latin_hypercube(int(n_init), task.dim, rng)


def candidate_pool_for(task: SyntheticTask) -> CandidatePool:
    return task.pool
