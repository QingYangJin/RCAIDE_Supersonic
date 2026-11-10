"""路线A：把热启动采样器接到现有约束 BO 路径上。

本适配器不实现任何采集函数：它直接复用
research/concorde_metaopt/optimization/baseline_bo.py 已导入的
ConstrainedBayesianOptimizer（maml-opt 的 EI×可行性 / 可行性概率 /
空间填充策略），只负责：

1. 把 K 个共享真实观测 tell 给优化器（计入预算）；
2. 由 WarmStartSampler 给出 n 个初始设计并逐个真实评价（计入预算）；
3. 之后完全走优化器自己的 ask()/tell() 循环，直到预算耗尽。

物理求解调用数 = 0；所有 objective/constraints 由调用方提供的合成任务给出。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..optimization.baseline_bo import ConstrainedBayesianOptimizer
from .sampler import ProposedDesigns, WarmStartSampler

DIMENSION = 12
ADAPTER_VERSION = "route-a-warm-bo-v1"
SOURCE_KIND = "SYNTHETIC_ANALOGUE"


class BOAdapterError(RuntimeError):
    """Raised when the warm-start BO request is invalid."""


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _record_result(record: Mapping[str, Any]) -> Dict[str, Any]:
    constraints = record.get("constraints_g_le_zero") or {}
    values: Dict[str, float] = {}
    for name, value in constraints.items():
        number = _finite(value)
        if number is None:
            return {"valid": False, "objective": None, "constraints_g_le_zero": {}}
        values[str(name)] = number
    objective = _finite(record.get("objective"))
    valid = bool(record.get("valid", False)) and objective is not None and bool(values)
    return {
        "status": "VALID" if valid else "INVALID",
        "valid": valid,
        "feasible": bool(valid and all(value <= 0.0 for value in values.values())),
        "objective": objective if valid else None,
        "constraints_g_le_zero": values if valid else {},
        "analysis_calls": 0,
        "analysis_calls_this_request": 0,
        "objective_model_eligible": True,
    }


def _is_feasible(record: Mapping[str, Any]) -> bool:
    if not bool(record.get("valid", False)):
        return False
    objective = _finite(record.get("objective"))
    if objective is None:
        return False
    constraints = record.get("constraints_g_le_zero") or {}
    if not constraints:
        return False
    for value in constraints.values():
        number = _finite(value)
        if number is None or number > 0.0:
            return False
    return True


def _best_feasible(trace: Sequence[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = [
        record for record in trace if _is_feasible(record) and record.get("objective") is not None
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda item: float(item["objective"]))
    return {
        "objective": float(best["objective"]),
        "iteration": int(best["iteration"]),
        "unit_vector": list(best["unit_vector"]),
    }


def _iteration_best(trace: Sequence[Mapping[str, Any]]) -> List[Optional[float]]:
    best: Optional[float] = None
    history: List[Optional[float]] = []
    for record in trace:
        if _is_feasible(record) and record.get("objective") is not None:
            value = float(record["objective"])
            best = value if best is None else min(best, value)
        history.append(best)
    return history


def run_warm_bo(
    task: Any,
    sampler: WarmStartSampler,
    support_records: Sequence[Mapping[str, Any]],
    budget: int,
    seed: int = 0,
    n_init: Optional[int] = None,
    candidate_count: int = 256,
    minimum_model_observations: Optional[int] = None,
) -> Dict[str, Any]:
    """K 个共享观测 + n 个采样器起点 + 现有约束 BO 直到预算耗尽。"""
    budget = int(budget)
    if budget < 2:
        raise BOAdapterError("budget must be at least 2")
    support = list(support_records)
    if len(support) >= budget:
        raise BOAdapterError("support observations must leave room for at least one more evaluation")
    if n_init is None:
        n_init = max(1, min(4, budget - len(support)))
    n_init = int(n_init)
    if len(support) + n_init > budget:
        raise BOAdapterError("support plus initial designs exceed the budget")

    proposal: ProposedDesigns = sampler.propose(
        task_context=task.context,
        design_space=DIMENSION,
        observed_support=support,
        candidate_pool=None,
        n_new=n_init,
        seed=int(seed),
    )

    optimizer = ConstrainedBayesianOptimizer(
        np.zeros(DIMENSION),
        np.ones(DIMENSION),
        seed=int(seed),
        candidate_count=int(candidate_count),
        minimum_model_observations=minimum_model_observations,
    )
    trace: List[Dict[str, Any]] = []
    seen: set = set()

    def _key(vector: Sequence[float]) -> Tuple[float, ...]:
        return tuple(np.round(np.asarray(vector, dtype=float), 12))

    for index, record in enumerate(support):
        vector = np.asarray(record["unit_vector"], dtype=float).reshape(DIMENSION)
        row = {
            "iteration": index,
            "phase": "support",
            "unit_vector": [float(value) for value in vector],
            "valid": bool(record.get("valid", False)),
            "feasible": _is_feasible(record),
            "objective": _finite(record.get("objective")),
            "constraints_g_le_zero": {
                str(name): _finite(value) for name, value in (record.get("constraints_g_le_zero") or {}).items()
            },
            "analysis_calls": 0,
            "selection_method": "SHARED_SUPPORT",
        }
        trace.append(row)
        seen.add(_key(vector))
        optimizer.tell(vector, _record_result(record), selection={"selection_method": "SHARED_SUPPORT"})

    def _evaluate(vector: np.ndarray, phase: str, selection: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        result = dict(task.evaluate_unit(vector))
        row = {
            "iteration": len(trace),
            "phase": phase,
            "unit_vector": [float(value) for value in np.clip(vector, 0.0, 1.0)],
            "valid": bool(result.get("valid", False)),
            "feasible": _is_feasible(result),
            "objective": _finite(result.get("objective")),
            "constraints_g_le_zero": {
                str(name): _finite(value) for name, value in (result.get("constraints_g_le_zero") or {}).items()
            },
            "analysis_calls": int(result.get("analysis_calls", 0) or 0),
            "selection_method": (dict(selection).get("selection_method") if selection else None),
        }
        if selection:
            for key in ("model_status", "acquisition_score", "probability_feasible", "expected_improvement"):
                if selection.get(key) is not None:
                    row[key] = selection[key]
        trace.append(row)
        optimizer.tell(vector, _record_result(result), selection=selection)
        seen.add(_key(vector))
        return row

    for vector in proposal.X_init:
        _evaluate(np.asarray(vector, dtype=float), "initial_design", {"selection_method": "WARM_START_SAMPLER"})

    duplicates = 0
    while len(trace) < budget:
        candidate = optimizer.ask()
        if candidate is None:
            break
        vector = np.asarray(candidate["design_vector"], dtype=float).reshape(DIMENSION)
        if _key(vector) in seen:
            duplicates += 1
            if duplicates > 5 * budget:
                break
            continue
        _evaluate(vector, "bo", candidate)

    best = _best_feasible(trace)
    first_feasible = next(
        (int(record["iteration"]) + 1 for record in trace if _is_feasible(record) and record.get("objective") is not None),
        None,
    )
    if not trace:
        status = "failed"
    elif best is None:
        status = "no_feasible_solution"
    else:
        status = "completed"
    return {
        "status": status,
        "termination_reason": "budget_exhausted" if len(trace) >= budget else "optimizer_exhausted",
        "evaluations": len(trace),
        "support_size": len(support),
        "initial_size": int(proposal.X_init.shape[0]),
        "bo_evaluations": max(0, len(trace) - len(support) - int(proposal.X_init.shape[0])),
        "duplicates_ignored": int(duplicates),
        "physical_call_count": 0,
        "source_kind": SOURCE_KIND,
        "first_feasible_evaluation": first_feasible,
        "best_feasible": best,
        "iteration_best_feasible_objective": _iteration_best(trace),
        "trace": trace,
        "proposal": proposal.to_dict(),
        "adapter_version": ADAPTER_VERSION,
    }
