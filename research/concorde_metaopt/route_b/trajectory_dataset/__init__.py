"""离线轨迹数据集：只允许合成 train 任务上的**真实评价**轨迹。

数据生成方式（行为策略回放，direct-method 数据）：

1. 在 train 划分任务上以固定初始点 n_init 起步（同 task+seed 各臂共享）；
2. 每一步由行为策略（EI/UCB/PI/随机）从候选池选一个设计，调用合成任务
   evaluate 得到标签并写入 ObservationHistory（这是"真实"评价，但来源是
   synthetic_analogue，physical_call_count=0）；
3. 记录"决策时刻特征快照 -> 此后到预算结束的累计奖励（reward-to-go）"。

泄漏防护：

- 只接受 split == "train" 的任务；val/test 任务进入数据集直接抛 LeakageError。
- 记录中不含候选池标签、不含未选候选的真实值、不含最终目标值；
  特征快照由已评价历史 + 候选坐标计算，是闭环中策略可见信息的全部。
- 数据集 manifest 记录 train/val/test 任务 id 隔离断言与 SHA256。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..baselines import ACQUISITION_NAMES, StandardAcquisition, design_key
from ..contracts import (
    CandidatePool,
    LeakageError,
    ObservationHistory,
    RewardSpec,
    RouteBContractError,
    TaskContext,
    canonical_json,
)
from ..policy import RandomScorePolicy, build_features, select_candidate
from ..synthetic_tasks import DEFAULT_BUDGET, DEFAULT_N_INIT, SyntheticTask, initial_design

BEHAVIORS: Tuple[str, ...] = ACQUISITION_NAMES + ("random",)
DATASET_VERSION = "route-b-trajectory-v1"


@dataclass(frozen=True)
class DecisionRecord:
    """一次决策的离线记录（特征快照 + reward-to-go）。"""

    task_id: str
    behavior: str
    seed: int
    step: int
    n_observed: int
    features: Tuple[float, ...]
    reward_to_go: float
    step_reward: float
    chosen_design_key: str
    split: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "behavior": self.behavior,
            "seed": int(self.seed),
            "step": int(self.step),
            "n_observed": int(self.n_observed),
            "features": list(self.features),
            "reward_to_go": float(self.reward_to_go),
            "step_reward": float(self.step_reward),
            "chosen_design_key": self.chosen_design_key,
            "split": self.split,
        }


class _RandomBehavior:
    name = "random"

    def __init__(self, seed: int) -> None:
        self.rng = np.random.default_rng(int(seed))

    def select(
        self,
        history: ObservationHistory,
        pool: CandidatePool,
        context: Optional[TaskContext] = None,
        exclude_keys: Optional[set] = None,
    ) -> Tuple[int, np.ndarray]:
        values = self.rng.random(len(pool))
        if exclude_keys:
            for index, design in enumerate(pool.designs):
                if design_key(design) in exclude_keys:
                    values[index] = -np.inf
        if not np.isfinite(values).any():
            return 0, values
        return int(np.argmax(values)), values


def make_behavior(name: str, seed: int = 0):
    """构造行为策略：标准采集（ei/ucb/pi）或随机。"""
    if name == "random":
        return _RandomBehavior(seed)
    if name in ACQUISITION_NAMES:
        return StandardAcquisition(name)
    raise RouteBContractError("未知行为策略 %r，允许 %r" % (name, BEHAVIORS))


def _evaluate(task: SyntheticTask, history: ObservationHistory, design: np.ndarray) -> Dict[str, Any]:
    outcome = task.evaluate(design)
    history.add_evaluated(design, outcome["objective"], outcome["constraints"])
    return outcome


def collect_trajectory(
    task: SyntheticTask,
    behavior: str,
    budget: int = DEFAULT_BUDGET,
    n_init: int = DEFAULT_N_INIT,
    seed: int = 0,
    reward_spec: Optional[RewardSpec] = None,
) -> Dict[str, Any]:
    """在单个合成任务上回放一个行为策略，返回决策记录与指标。"""
    if task.context.split != "train":
        raise LeakageError("数据集生成只允许 train 任务，收到 split=%r" % (task.context.split,))
    reward_spec = reward_spec or RewardSpec()
    policy = make_behavior(behavior, seed)
    history = ObservationHistory(task.dim, task.context)
    init = initial_design(task, n_init=n_init, seed=seed)
    rewards: List[float] = []
    features: List[np.ndarray] = []
    chosen_keys: List[str] = []
    null_count = 0

    for design in init:
        already_feasible = history.feasibility_ratio > 0.0
        prev_best = history.best_feasible
        outcome = _evaluate(task, history, np.asarray(design, dtype=float))
        feasible = history.feasible_mask()[-1]
        if not bool(feasible):
            null_count += 1
        rewards.append(
            reward_spec.step_reward(prev_best, outcome["objective"], bool(feasible), budget, already_feasible)
        )

    while history.n < budget:
        exclude = history.evaluated_keys()
        features_now = build_features(history, task.pool, task.context)
        index, _scores = select_candidate(policy, history, task.pool, task.context, exclude)
        if np.isfinite(_scores).sum() == 0:
            break
        design = task.pool.designs[index]
        key = design_key(design)
        if key in exclude:
            break
        features.append(features_now[index])
        chosen_keys.append(key)
        already_feasible = history.feasibility_ratio > 0.0
        prev_best = history.best_feasible
        outcome = _evaluate(task, history, design)
        feasible = history.feasible_mask()[-1]
        if not bool(feasible):
            null_count += 1
        rewards.append(
            reward_spec.step_reward(prev_best, outcome["objective"], bool(feasible), budget, already_feasible)
        )

    gamma = 1.0
    rewards_array = np.asarray(rewards, dtype=float)
    decisions: List[DecisionRecord] = []
    for step, vec in enumerate(features):
        tail = rewards_array[step:]
        rtg = float(np.sum(tail * (gamma ** np.arange(tail.size))))
        decisions.append(
            DecisionRecord(
                task_id=task.context.task_id,
                behavior=behavior,
                seed=int(seed),
                step=int(step),
                n_observed=int(n_init + step),
                features=tuple(float(v) for v in vec),
                reward_to_go=rtg,
                step_reward=float(rewards_array[step]),
                chosen_design_key=chosen_keys[step],
                split=task.context.split,
            )
        )

    feasible_mask = history.feasible_mask()
    feasible_indices = np.nonzero(feasible_mask)[0]
    objectives = history.objectives_array()
    valid_objectives = objectives[~np.isnan(objectives)]
    best = history.best_feasible
    return {
        "task_id": task.context.task_id,
        "behavior": behavior,
        "seed": int(seed),
        "split": task.context.split,
        "budget": int(budget),
        "n_init": int(n_init),
        "n_evaluated": int(history.n),
        "decisions": [record.to_dict() for record in decisions],
        "metrics": {
            "first_feasible_eval": int(feasible_indices[0]) if feasible_indices.size else None,
            "feasible_hit_rate": float(feasible_mask.mean()) if history.n else 0.0,
            "feasible_hits": int(feasible_mask.sum()),
            "null_fraction": float(null_count / max(history.n, 1)),
            "best_feasible_value": float(best) if best is not None else None,
            "gap_to_reference": None if best is None else float(max(0.0, best - task.f_star)),
            "mean_objective": float(np.mean(valid_objectives)) if valid_objectives.size else None,
            "total_reward": float(rewards_array.sum()),
        },
        "source_kind": task.context.source_kind,
        "physical_call_count": 0,
        "dataset_version": DATASET_VERSION,
    }


def build_dataset(
    tasks: Sequence[SyntheticTask],
    behaviors: Sequence[str] = BEHAVIORS,
    budget: int = DEFAULT_BUDGET,
    n_init: int = DEFAULT_N_INIT,
    seeds: Sequence[int] = (0, 1),
) -> Dict[str, Any]:
    """在 train 任务集合上生成离线轨迹数据集（含防泄漏断言）。"""
    split_ids = {task.context.task_id: task.context.split for task in tasks}
    non_train = sorted(task_id for task_id, split in split_ids.items() if split != "train")
    if non_train:
        raise LeakageError("数据集只允许 train 任务，混入: %r" % (non_train,))
    if len(set(split_ids)) != len(tasks):
        raise RouteBContractError("任务 id 重复")
    records: List[Dict[str, Any]] = []
    episodes: List[Dict[str, Any]] = []
    for task in tasks:
        for behavior in behaviors:
            for seed in seeds:
                episode = collect_trajectory(task, behavior, budget=budget, n_init=n_init, seed=int(seed))
                episodes.append(
                    {
                        "task_id": episode["task_id"],
                        "behavior": episode["behavior"],
                        "seed": episode["seed"],
                        "metrics": episode["metrics"],
                    }
                )
                records.extend(episode["decisions"])
    payload = {
        "dataset_version": DATASET_VERSION,
        "records": records,
        "episodes": episodes,
        "task_ids": [task.context.task_id for task in tasks],
        "behaviors": list(behaviors),
        "seeds": [int(seed) for seed in seeds],
        "budget": int(budget),
        "n_init": int(n_init),
        "source_kind": "synthetic_analogue",
        "physical_call_count": 0,
    }
    return payload


def write_dataset(payload: Dict[str, Any], directory: Path) -> Dict[str, Any]:
    """写 dataset.jsonl + manifest.json，返回 manifest（含 SHA256）。"""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    dataset_path = directory / "dataset.jsonl"
    lines = [canonical_json(record) for record in payload["records"]]
    dataset_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sha = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    manifest = {
        "dataset_version": payload["dataset_version"],
        "file": dataset_path.name,
        "sha256": sha,
        "n_records": len(payload["records"]),
        "n_episodes": len(payload["episodes"]),
        "task_ids": payload["task_ids"],
        "behaviors": payload["behaviors"],
        "seeds": payload["seeds"],
        "budget": payload["budget"],
        "n_init": payload["n_init"],
        "source_kind": "synthetic_analogue",
        "physical_call_count": 0,
    }
    (directory / "manifest.json").write_text(canonical_json(manifest), encoding="utf-8")
    (directory / "episodes.json").write_text(canonical_json(payload["episodes"]), encoding="utf-8")
    return manifest


def load_dataset(directory: Path) -> Dict[str, Any]:
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    lines = (directory / "dataset.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    actual = hashlib.sha256((directory / manifest["file"]).read_bytes()).hexdigest()
    if actual != manifest["sha256"]:
        raise RouteBContractError("数据集 SHA256 不匹配，疑似被改写")
    if len(records) != manifest["n_records"]:
        raise RouteBContractError("记录数与 manifest 不一致")
    return {"manifest": manifest, "records": records}


def split_by_task(
    records: Sequence[Dict[str, Any]],
    train_task_ids: Sequence[str],
    held_out_task_ids: Sequence[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """按任务 id 切分记录（禁止同一任务的记录跨集合）。"""
    train_ids = set(train_task_ids)
    held_ids = set(held_out_task_ids)
    if train_ids & held_ids:
        raise LeakageError("训练与留出任务重叠: %r" % sorted(train_ids & held_ids))
    train_records = [record for record in records if record["task_id"] in train_ids]
    held_records = [record for record in records if record["task_id"] in held_ids]
    seen = {record["task_id"] for record in train_records} | {record["task_id"] for record in held_records}
    unknown = seen - train_ids - held_ids
    if unknown:
        raise LeakageError("存在未声明任务记录: %r" % sorted(unknown))
    return train_records, held_records
