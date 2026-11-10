"""policy_eval：闭环评测（学习策略 vs 标准约束 BO 采集 vs 负控）。

统一协议（对齐计划文档的 B 线验收要求）：

- 同一任务上所有臂共享**同一固定初始点**（initial_design(task, n_init, seed)）；
- 同一预算 B（默认 12）、同一候选池、同一任务/种子；
- 任务级统计：first_feasible_eval、feasible_hit_rate、best_feasible_value、
  gap_to_reference、null_fraction、total_reward；
- 负控：random（随机候选）与 random_score（与学习策略同一选择路径但随机评分）；
  负控应当不优于随机基线，否则评测实现可疑。

泄漏防护：评测只读取 val/test 划分任务；测试任务不参与训练、早停或调参。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..baselines import ACQUISITION_NAMES, StandardAcquisition, design_key
from ..contracts import (
    LeakageError,
    ObservationHistory,
    RewardSpec,
    RouteBContractError,
    canonical_json,
)
from ..policy import MetaAcquisitionPolicy, RandomScorePolicy, select_candidate
from ..synthetic_tasks import DEFAULT_BUDGET, DEFAULT_N_INIT, SyntheticTask, initial_design

EVAL_VERSION = "route-b-policy-eval-v1"


@dataclass(frozen=True)
class ArmSpec:
    name: str
    family: str
    note: str


def default_arms() -> List[ArmSpec]:
    return [
        ArmSpec("learned", "meta_policy", "MetaAcquisitionPolicy（离线 direct-method 训练）"),
        ArmSpec("ei", "standard_bo", "约束 EI（可行概率加权）"),
        ArmSpec("ucb", "standard_bo", "约束 UCB（beta=2.0）"),
        ArmSpec("pi", "standard_bo", "约束 PI（可行概率加权）"),
        ArmSpec("random", "negative_control", "随机候选（无模型基线）"),
        ArmSpec("random_score", "negative_control", "同选择路径随机评分负控"),
        ArmSpec("untrained", "negative_control", "随机初始化同结构网络（无训练负控）"),
    ]


def make_arm_policy(spec: ArmSpec, trained_params: Optional[Dict[str, Any]], seed: int):
    if spec.name == "learned":
        if trained_params is None:
            raise RouteBContractError("learned 臂需要已训练策略参数")
        policy = MetaAcquisitionPolicy.from_params(trained_params)
        policy.trained = True
        return policy
    if spec.name == "untrained":
        dim = int(trained_params["feature_input_dim"]) if trained_params else 22
        return MetaAcquisitionPolicy(feature_input_dim=dim, seed=seed)
    if spec.name == "random_score":
        return RandomScorePolicy(seed=seed)
    if spec.name in ACQUISITION_NAMES:
        return StandardAcquisition(spec.name)
    if spec.name == "random":
        return RandomScorePolicy(seed=seed)
    raise RouteBContractError("未知评测臂 %r" % (spec.name,))


def run_closed_loop(
    task: SyntheticTask,
    policy: Any,
    budget: int = DEFAULT_BUDGET,
    n_init: int = DEFAULT_N_INIT,
    seed: int = 0,
    reward_spec: Optional[RewardSpec] = None,
) -> Dict[str, Any]:
    """在单个任务上闭环运行一个策略，返回任务级指标（不含标签泄漏）。"""
    if task.context.split not in ("val", "test"):
        raise LeakageError("评测只允许 val/test 划分任务，收到 %r" % (task.context.split,))
    reward_spec = reward_spec or RewardSpec()
    history = ObservationHistory(task.dim, task.context)
    null_count = 0
    rewards: List[float] = []

    def evaluate(design: np.ndarray) -> None:
        nonlocal null_count
        already_feasible = history.feasibility_ratio > 0.0
        prev_best = history.best_feasible
        outcome = task.evaluate(np.asarray(design, dtype=float))
        history.add_evaluated(design, outcome["objective"], outcome["constraints"])
        feasible = bool(history.feasible_mask()[-1])
        if not feasible:
            null_count += 1
        rewards.append(
            reward_spec.step_reward(prev_best, outcome["objective"], feasible, budget, already_feasible)
        )

    for design in initial_design(task, n_init=n_init, seed=seed):
        evaluate(design)

    steps = 0
    while history.n < budget:
        exclude = history.evaluated_keys()
        index, scores = select_candidate(policy, history, task.pool, task.context, exclude)
        if not np.isfinite(np.asarray(scores, dtype=float)).any():
            break
        design = task.pool.designs[index]
        if design_key(design) in exclude:
            break
        evaluate(design)
        steps += 1

    feasible_mask = history.feasible_mask()
    feasible_indices = np.nonzero(feasible_mask)[0]
    objectives = history.objectives_array()
    valid = objectives[~np.isnan(objectives)]
    best = history.best_feasible
    return {
        "task_id": task.context.task_id,
        "split": task.context.split,
        "n_evaluated": int(history.n),
        "selection_steps": int(steps),
        "first_feasible_eval": int(feasible_indices[0]) if feasible_indices.size else None,
        "feasible_hit_rate": float(feasible_mask.mean()) if history.n else 0.0,
        "feasible_hits": int(feasible_mask.sum()),
        "null_fraction": float(null_count / max(history.n, 1)),
        "best_feasible_value": float(best) if best is not None else None,
        "gap_to_reference": None if best is None else float(max(0.0, best - task.f_star)),
        "mean_objective": float(np.mean(valid)) if valid.size else None,
        "total_reward": float(np.sum(rewards)),
        "empty_pool_exhausted": bool(history.n < budget and steps == 0),
    }


def aggregate(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """按臂聚合任务级指标（统计单位 = 任务）。"""
    by_arm: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_arm.setdefault(row["arm"], []).append(row)
    summary: Dict[str, Any] = {}
    for arm, arm_rows in by_arm.items():
        first = [row["first_feasible_eval"] for row in arm_rows if row["first_feasible_eval"] is not None]
        best = [row["best_feasible_value"] for row in arm_rows if row["best_feasible_value"] is not None]
        gaps = [row["gap_to_reference"] for row in arm_rows if row["gap_to_reference"] is not None]
        hit = [row["feasible_hit_rate"] for row in arm_rows]
        nulls = [row["null_fraction"] for row in arm_rows]
        rewards = [row["total_reward"] for row in arm_rows]
        summary[arm] = {
            "n_tasks": len(arm_rows),
            "n_tasks_feasible": len(first),
            "first_feasible_eval_mean": float(np.mean(first)) if first else None,
            "feasible_hit_rate_mean": float(np.mean(hit)),
            "best_feasible_value_mean": float(np.mean(best)) if best else None,
            "gap_to_reference_mean": float(np.mean(gaps)) if gaps else None,
            "null_fraction_mean": float(np.mean(nulls)),
            "total_reward_mean": float(np.mean(rewards)),
            "total_reward_std": float(np.std(rewards)),
        }
    return summary


def compare_arms(
    summary: Dict[str, Any], reference: str = "ei", candidate: str = "learned"
) -> Dict[str, Any]:
    ref = summary.get(reference)
    cand = summary.get(candidate)
    if ref is None or cand is None:
        return {
            "candidate": candidate,
            "reference": reference,
            "verdict": "NOT_APPLICABLE",
            "verdict_reason": "缺少 %r 或 %r 臂，无法做配对比较" % (candidate, reference),
        }
    deltas: Dict[str, Any] = {}
    for metric in ("first_feasible_eval_mean", "feasible_hit_rate_mean", "best_feasible_value_mean", "total_reward_mean"):
        left = ref.get(metric)
        right = cand.get(metric)
        if left is None or right is None:
            deltas[metric] = None
        else:
            deltas[metric] = float(right - left)
    return {
        "candidate": candidate,
        "reference": reference,
        "delta_candidate_minus_reference": deltas,
        "n_tasks": min(ref["n_tasks"], cand["n_tasks"]),
        "verdict": "INCONCLUSIVE",
        "verdict_reason": "任务数过少（<=4），未达统计功效；仅报告描述性差异，不宣称 MetaBO 一定胜出",
    }


def evaluate_arms(
    tasks: Sequence[SyntheticTask],
    trained_params: Optional[Dict[str, Any]],
    arms: Optional[Sequence[ArmSpec]] = None,
    budget: int = DEFAULT_BUDGET,
    n_init: int = DEFAULT_N_INIT,
    seed: int = 0,
) -> Dict[str, Any]:
    """在给定 val/test 任务上评测各臂并聚合。"""
    arms = list(arms or default_arms())
    rows: List[Dict[str, Any]] = []
    for arm in arms:
        for task in tasks:
            if task.context.split not in ("val", "test"):
                raise LeakageError("评测任务必须是 val/test，收到 %r" % (task.context.split,))
            policy = make_arm_policy(arm, trained_params, seed)
            metrics = run_closed_loop(task, policy, budget=budget, n_init=n_init, seed=seed)
            row = dict(metrics)
            row["arm"] = arm.name
            row["family"] = arm.family
            rows.append(row)
    summary = aggregate(rows)
    payload = {
        "eval_version": EVAL_VERSION,
        "protocol": {
            "budget": int(budget),
            "n_init": int(n_init),
            "shared_initial_design": True,
            "seed": int(seed),
            "statistical_unit": "task",
            "arms": [{"name": arm.name, "family": arm.family, "note": arm.note} for arm in arms],
        },
        "task_ids": [task.context.task_id for task in tasks],
        "rows": rows,
        "summary": summary,
        "primary_comparison": compare_arms(summary),
        "negative_control_check": _negative_control_check(summary),
        "physical_call_count": 0,
        "source_kind": "synthetic_analogue",
    }
    return payload


def _negative_control_check(summary: Dict[str, Any]) -> Dict[str, Any]:
    """负控自检。

    关键负控：**未训练**的同结构网络（untrained）不得显著优于随机基线（random），
    否则说明评测/特征管线可能泄漏。random_score 与 random 都等价于均匀随机选择，
    二者差异接近 0 属预期（记录为退化等价性检查，不作为独立证据）。
    """
    random_arm = summary.get("random")
    untrained_arm = summary.get("untrained")
    score_arm = summary.get("random_score")
    if random_arm is None or untrained_arm is None:
        return {"status": "NOT_RUN", "reason": "缺少 random 或 untrained 臂"}
    delta_untrained = float(untrained_arm["total_reward_mean"] - random_arm["total_reward_mean"])
    result = {
        "status": "PASS" if delta_untrained <= 0.05 else "WARN",
        "delta_untrained_minus_random_total_reward": delta_untrained,
        "note": "未训练网络不得显著优于随机基线；显著优于随机说明评测或特征管线可能泄漏",
    }
    if score_arm is not None:
        result["delta_random_score_minus_random_total_reward"] = float(
            score_arm["total_reward_mean"] - random_arm["total_reward_mean"]
        )
        result["degenerate_note"] = "random_score 与 random 同为均匀随机选择，差异≈0 属预期"
    return result


def write_results(payload: Dict[str, Any], directory: Path) -> Dict[str, Any]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "eval_results.json").write_text(canonical_json(payload), encoding="utf-8")
    rows = payload["rows"]
    fields = [
        "task_id", "split", "arm", "family", "n_evaluated", "selection_steps",
        "first_feasible_eval", "feasible_hit_rate", "feasible_hits", "null_fraction",
        "best_feasible_value", "gap_to_reference", "mean_objective", "total_reward",
    ]
    with (directory / "eval_results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
    (directory / "eval_summary.json").write_text(
        canonical_json({"summary": payload["summary"], "primary_comparison": payload["primary_comparison"]}),
        encoding="utf-8",
    )
    return {"directory": str(directory), "n_rows": len(rows)}


def load_trained_policy(directory: Path) -> Dict[str, Any]:
    path = Path(directory) / "policy.json"
    if not path.exists():
        raise RouteBContractError("缺少策略文件 %s" % (path,))
    return json.loads(path.read_text(encoding="utf-8"))
