"""P4-M5：四个真实可识别优化臂（BO-random / BO-pretrained-init / BO-MAML-init / DE）。

职责
----
1. 把 Issue #5 D-P4-002 的四个臂实现为**等预算、同任务、同初始条件审计**的独立调用路径：

   * M5-BO-random：共享 LHS 8 初始点 + maml_opt 约束 BO 采集（基线）。
   * M5-BO-pretrain-init：监督预训练代理对 64 候选池打分排序，选出 8 初始点，
     然后走**同一个** BO 引擎（只改初始化，不改采集策略）。
   * M5-BO-MAML-init：元学习（一阶 MAML）代理对**同一个** 64 候选池打分排序，
     选出 8 初始点，然后走同一个 BO 引擎。
   * M5-DE：等预算 DE/rand/1/bin（复用 baseline_de 语义），初始种群与
     M5-BO-random 共享同一份 8 点 LHS 设计。

2. 记录每个臂的初始化指纹（候选池 sha256、初始 8 点 sha256、代理 artifact sha256、
   代码路径、代理打分成本），供 identifiability_audit 做可识别性审计：若某臂的
   初始点与 M5-BO-random 在 >=90% 的任务上重合 >=90%，则如实标注
   CLONE_OF_M5-BO-random 并从推断中排除，**不改名凑数**。

边界（§1.3 硬隔离）
------------------
本模块只使用解析合成 evaluator（由调用方注入）；不 import 任何 RCAIDE Mission /
SU2 / VSPAERO / OpenVSP / Gmsh 入口；所有函数 physical_call_count 恒 0；
代理预测标签只用于“先评估哪些点”的排序，绝不写入 BO observations（§8.2 隔离）。
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .baseline_arms import (
    ArmResult,
    BaselineArmError,
    BO_INITIAL_DESIGN_COUNT,
    DEDUP_TOLERANCE,
    DESIGN_DIM,
    assert_synthetic_design_space,
    derive_arm_seed,
    run_bo_arm,
    run_de_arm,
    score_maml_init_designs,
    shared_initial_designs,
)
from .data_contract import CONTEXT_NAMES
from .feasible_v2 import M5_ARMS, M5_BUDGETS, M5_META_SEEDS, M5_OPTIMIZATION_SEEDS

#: 旧版 BO 引擎名：三个 BO 臂共用同一引擎与同一随机种子来源，只允许初始化不同。
LEGACY_BO_ARM = "OPT-BO-rand"

M5_BO_RANDOM = "M5-BO-random"
M5_BO_PRETRAIN_INIT = "M5-BO-pretrain-init"
M5_BO_MAML_INIT = "M5-BO-MAML-init"
M5_DE = "M5-DE"
M5_ARM_ORDER = tuple(M5_ARMS)
M5_BO_ARMS = (M5_BO_RANDOM, M5_BO_PRETRAIN_INIT, M5_BO_MAML_INIT)

#: 冻结的 MAML-init 参数（§8.2：候选池 64、初始 8、多样性候选 64、去重 1e-12）。
M5_CANDIDATE_POOL_SIZE = 64
M5_INITIAL_DESIGN_COUNT = BO_INITIAL_DESIGN_COUNT
M5_DIVERSITY_CANDIDATE_COUNT = 64
M5_DEDUP_TOLERANCE = DEDUP_TOLERANCE

#: DE 冻结参数（与旧 OPT-DE 一致，保证两轮可对照）。
M5_DE_POPULATION_SIZE = 8
M5_DE_MUTATION_FACTOR = 0.5
M5_DE_CROSSOVER_RATE = 0.7

#: 代理结构/训练预算（与 M2 代理一致；meta_seed ∈ M5_META_SEEDS）。
M5_PROXY_HIDDEN_SIZES = (16, 16)
M5_PROXY_META_STEPS = 200
M5_PRETRAIN_STEPS = 50

#: 可识别性审计阈值：初始点重合 >=90% 且覆盖 >=90% 的组 -> 判为克隆臂。
CLONE_OVERLAP_THRESHOLD = 0.90
CLONE_GROUP_THRESHOLD = 0.90

PHYSICAL_CALL_COUNT = 0
STAGE = "P4-M5"

#: 每臂的代码路径（审计用；必须真实对应实现）。
ARM_CODE_PATHS = {
    M5_BO_RANDOM: (
        "m5_arms.run_m5_bo_arm[shared_initial_designs]"
        "->baseline_arms.run_bo_arm->maml_opt.bayesian.run_search"
    ),
    M5_BO_PRETRAIN_INIT: (
        "m5_arms.run_m5_bo_arm[pretrain:score_maml_init_designs(method='none')]"
        "->baseline_arms.run_bo_arm->maml_opt.bayesian.run_search"
    ),
    M5_BO_MAML_INIT: (
        "m5_arms.run_m5_bo_arm[maml:score_maml_init_designs(method='maml')]"
        "->baseline_arms.run_bo_arm->maml_opt.bayesian.run_search"
    ),
    M5_DE: "m5_arms.run_m5_de_arm->baseline_arms.run_de_arm[DE/rand/1/bin]",
}

#: 每臂实现标签（写入 run_config/optimization_summary，可复核）。
ARM_IMPLEMENTATIONS = {
    M5_BO_RANDOM: (
        "reuse:maml_opt.initialization:generate_initial_designs+"
        "maml_opt.bayesian:ConstrainedBayesianOptimizer/run_search"
    ),
    M5_BO_PRETRAIN_INIT: (
        "reuse:maml_opt.initialization:select_model_scored_initial_designs+"
        "maml_opt.bayesian:ConstrainedBayesianOptimizer/run_search"
    ),
    M5_BO_MAML_INIT: (
        "reuse:maml_opt.initialization:select_model_scored_initial_designs+"
        "maml_opt.bayesian:ConstrainedBayesianOptimizer/run_search"
    ),
    M5_DE: (
        "research.concorde_metaopt.meta_learning:m5_arms.run_m5_de_arm"
        "->baseline_arms.run_de_arm[等预算 DE/rand/1/bin；不 import baseline_de、"
        "不触 low_fidelity 链]"
    ),
}

#: 初始化器类型（审计用）。
ARM_INITIALIZERS = {
    M5_BO_RANDOM: "shared_lhs_8",
    M5_BO_PRETRAIN_INIT: "model_scored_pretrain_8_of_64",
    M5_BO_MAML_INIT: "model_scored_maml_8_of_64",
    M5_DE: "shared_lhs_8",
}


class M5ArmError(ValueError):
    """P4-M5 臂实现/审计错误（fail-closed，不静默降级）。"""


def arm_metadata(arm: str) -> dict[str, Any]:
    """返回单臂的静态元数据（代码路径/实现标签/初始化器/是否用代理）。"""
    if arm not in M5_ARM_ORDER:
        raise M5ArmError(f"未知 M5 臂: {arm!r}；允许 {M5_ARM_ORDER}")
    return {
        "arm": arm,
        "stage": STAGE,
        "code_path": ARM_CODE_PATHS[arm],
        "implementation": ARM_IMPLEMENTATIONS[arm],
        "initializer": ARM_INITIALIZERS[arm],
        "uses_proxy": arm in (M5_BO_PRETRAIN_INIT, M5_BO_MAML_INIT),
        "acquisition": "de_rand_1_bin" if arm == M5_DE else "constrained_bayesian",
        "physical_call_count": PHYSICAL_CALL_COUNT,
    }


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_digest(payload: Any) -> str:
    """任意 JSON 可序列化负载的 sha256（稳定排序、UTF-8）。"""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def designs_digest(designs: Any) -> str:
    """设计矩阵指纹：先按 1e-12 四舍五入（与去重容差一致）再哈希 float64 字节。"""
    matrix = np.asarray(designs, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != DESIGN_DIM:
        raise M5ArmError(f"设计矩阵必须为 (n,{DESIGN_DIM})，实际 {matrix.shape}")
    rounded = np.round(matrix, 12)
    payload = np.ascontiguousarray(rounded, dtype="<f8").tobytes()
    header = f"{matrix.shape[0]}x{matrix.shape[1]}:".encode("ascii")
    return hashlib.sha256(header + payload).hexdigest()


def artifact_sha256(artifact: Any) -> str:
    """代理 artifact 指纹：参数字节 + 结构配置（跨进程确定性）。"""
    from .maml import ParameterSet

    if isinstance(artifact, Mapping):
        payload = dict(artifact)
    else:
        payload = {
            "parameters": getattr(artifact, "parameters", None),
            "config": getattr(artifact, "config", None),
        }
    parameters = payload.get("parameters")
    if parameters is None:
        raise M5ArmError("artifact 缺少 parameters，无法计算指纹")
    if isinstance(parameters, Mapping):
        parameters = ParameterSet.from_dict(parameters)
    if not isinstance(parameters, ParameterSet):
        raise M5ArmError(f"artifact.parameters 类型非法: {type(parameters).__name__}")
    config = payload.get("config")
    if hasattr(config, "to_dict"):
        config_payload = config.to_dict()
    elif isinstance(config, Mapping):
        config_payload = dict(config)
    else:
        config_payload = str(config)
    digest = hashlib.sha256()
    digest.update(_canonical_json({"config": config_payload}).encode("utf-8"))
    for index, tensor in enumerate(parameters.tensors):
        array = np.ascontiguousarray(np.asarray(tensor, dtype="<f8"))
        digest.update(f"|{index}:{array.shape}|".encode("ascii"))
        digest.update(array.tobytes())
    return digest.hexdigest()


def _train_tasks(tasks: Sequence[Any]) -> list[Any]:
    train = [task for task in tasks if getattr(task, "split", None) == "meta_train"]
    if not train:
        raise M5ArmError("meta_train 任务为空，无法训练 M5 代理")
    return train


def _target_names_for(blocks: Mapping[str, Any], tasks: Sequence[Any]) -> tuple[str, ...]:
    from .offline_runner import task_target_names

    target_names = tuple(task_target_names(tasks[0]))
    if len(target_names) < 2:
        raise M5ArmError("M5 代理至少需要 objective 与一个启用的约束目标列")
    for task in tasks:
        if tuple(task_target_names(task)) != target_names:
            raise M5ArmError(
                f"M5 代理目标列不一致：{task.task_id} 为 {tuple(task_target_names(task))}，"
                f"首任务为 {target_names}"
            )
    return target_names


def _target_columns(block: Mapping[str, Any], target_names: Sequence[str]) -> np.ndarray:
    names = list(block["target_names"])
    try:
        indices = [names.index(str(name)) for name in target_names]
    except ValueError as exc:
        raise M5ArmError(f"目标列缺失: {exc}") from exc
    return np.asarray(block["targets"], dtype=np.float64)[:, indices]


def build_m5_pretrain_artifact(
    blocks: Mapping[str, Any],
    tasks: Sequence[Any],
    *,
    meta_seed: int,
    pretrain_steps: int = M5_PRETRAIN_STEPS,
) -> dict[str, Any]:
    """监督预训练代理（objective+约束双输出）：在 meta-train 全部 support+query 样本上拟合。

    该路径**不做**任务级内循环元学习；与 MAML 代理的训练目标、数据使用方式不同，
    因此两个模型打分臂在 artifact 指纹层面必须可区分（审计强制）。
    """
    from .maml import MAMLConfig, TaskEpisode, init_parameters, inner_adapt, torch_available, torch_import_error

    if not torch_available():
        raise M5ArmError(f"torch 不可用，无法训练 M5 预训练代理：{torch_import_error()}")
    if type(meta_seed) is not int or meta_seed < 0:
        raise M5ArmError(f"meta_seed 必须是非负整数，实际 {meta_seed!r}")
    if type(pretrain_steps) is not int or pretrain_steps < 1:
        raise M5ArmError("pretrain_steps 必须是正整数")
    train_tasks = _train_tasks(tasks)
    target_names = _target_names_for(blocks, train_tasks)
    features = np.concatenate(
        [np.asarray(blocks[task.task_id]["support"]["features"], dtype=np.float64) for task in train_tasks]
        + [np.asarray(blocks[task.task_id]["query"]["features"], dtype=np.float64) for task in train_tasks],
        axis=0,
    )
    targets = np.concatenate(
        [_target_columns(blocks[task.task_id]["support"], target_names) for task in train_tasks]
        + [_target_columns(blocks[task.task_id]["query"], target_names) for task in train_tasks],
        axis=0,
    )
    if not np.all(np.isfinite(features)) or not np.all(np.isfinite(targets)):
        raise M5ArmError("预训练特征/标签出现非有限值（fail-closed）")
    config = MAMLConfig(
        input_dim=12 + len(CONTEXT_NAMES),
        output_dim=len(target_names),
        hidden_sizes=M5_PROXY_HIDDEN_SIZES,
        inner_lr=0.01,
        inner_steps=pretrain_steps,
        outer_lr=1e-3,
        tasks_per_batch=1,
        first_order=True,
        seed=meta_seed,
        backend="torch",
    )
    episode = TaskEpisode(features, targets, features, targets)
    wall_start = time.perf_counter()
    initial = init_parameters(config, seed=meta_seed)
    parameters, losses = inner_adapt(initial, episode, config)
    wall_s = time.perf_counter() - wall_start
    finite = all(math.isfinite(float(loss)) for loss in losses)
    if not finite:
        raise M5ArmError("预训练损失出现非有限值（fail-closed）")
    artifact = {
        "parameters": parameters,
        "config": config,
        "context_names": tuple(CONTEXT_NAMES),
        "adaptation_method": "fine_tuning",
        "fine_tuning_steps": int(pretrain_steps),
        "backend": "torch",
        "equivalence_claimed": False,
        "training": {
            "kind": "pretrain",
            "meta_seed": int(meta_seed),
            "steps": int(pretrain_steps),
            "rows": int(features.shape[0]),
            "target_names": list(target_names),
            "final_loss": float(losses[-1]),
            "wall_s": float(wall_s),
            "physical_call_count": PHYSICAL_CALL_COUNT,
        },
    }
    training_rows = [
        {
            "run_id": "",
            "arm": "M5-pretrain-proxy",
            "split": "meta_train",
            "task_id": "",
            "family": train_tasks[0].family,
            "iteration": int(pretrain_steps),
            "epoch": 0,
            "loss_support": None,
            "loss_query": float(losses[-1]),
            "grad_norm": None,
            "lr": float(config.inner_lr),
            "seed": int(meta_seed),
            "wall_s": float(wall_s),
            "status": "VALID",
            "meta_seed": int(meta_seed),
        }
    ]
    return {
        "artifact": artifact,
        "target_names": target_names,
        "meta_seed": int(meta_seed),
        "kind": "pretrain",
        "training": artifact["training"],
        "training_rows": training_rows,
        "artifact_sha256": artifact_sha256(artifact),
    }


def build_m5_maml_artifact(
    blocks: Mapping[str, Any],
    tasks: Sequence[Any],
    *,
    meta_seed: int,
    max_meta_steps: int = M5_PROXY_META_STEPS,
) -> dict[str, Any]:
    """一阶 MAML 元学习代理（objective+约束双输出，meta_train episode 级训练）。

    复用 offline_runner.build_m2_proxy_artifact 的同一训练实现，仅把种子显式设为
    meta_seed，保证 ≥3 个元训练 seed 可用（Issue #5 统计要求）。
    """
    from .offline_runner import OfflineRunnerConfig, build_m2_proxy_artifact

    if type(meta_seed) is not int or meta_seed < 0:
        raise M5ArmError(f"meta_seed 必须是非负整数，实际 {meta_seed!r}")
    wall_start = time.perf_counter()
    runner_config = OfflineRunnerConfig(
        run_id=f"m5-maml-proxy-{meta_seed}",
        output_root=Path("."),
        seed=int(meta_seed),
        max_meta_steps=int(max_meta_steps),
    )
    payload = build_m2_proxy_artifact(blocks, tasks, runner_config)
    wall_s = time.perf_counter() - wall_start
    artifact = dict(payload["artifact"])
    training = dict(artifact.get("training") or {})
    training.update(
        {
            "kind": "maml",
            "meta_seed": int(meta_seed),
            "role": "M5 MAML-init 代理（objective+约束双输出；仅用于初始点排序）",
            "physical_call_count": PHYSICAL_CALL_COUNT,
        }
    )
    artifact["training"] = training
    training_rows = [dict(row) for row in payload.get("training_rows", ())]
    return {
        "artifact": artifact,
        "target_names": tuple(payload["target_names"]),
        "meta_seed": int(meta_seed),
        "kind": "maml",
        "training": training,
        "training_rows": training_rows,
        "artifact_sha256": artifact_sha256(artifact),
        "wall_s": float(wall_s),
    }


def build_m5_model_artifacts(
    blocks: Mapping[str, Any],
    tasks: Sequence[Any],
    *,
    meta_seed: int,
    maml_steps: int = M5_PROXY_META_STEPS,
    pretrain_steps: int = M5_PRETRAIN_STEPS,
) -> dict[str, Any]:
    """为单个元训练 seed 构造 pretrain 与 MAML 两个代理 artifact。"""
    pretrain = build_m5_pretrain_artifact(blocks, tasks, meta_seed=meta_seed, pretrain_steps=pretrain_steps)
    maml = build_m5_maml_artifact(blocks, tasks, meta_seed=meta_seed, max_meta_steps=maml_steps)
    if pretrain["artifact_sha256"] == maml["artifact_sha256"]:
        raise M5ArmError("pretrain 与 MAML 代理 artifact 指纹相同（可识别性失败）")
    return {
        "meta_seed": int(meta_seed),
        "target_names": tuple(maml["target_names"]),
        "pretrain": pretrain,
        "maml": maml,
        "artifacts_sha256": {
            "pretrain": pretrain["artifact_sha256"],
            "maml": maml["artifact_sha256"],
        },
        "physical_call_count": PHYSICAL_CALL_COUNT,
    }


@dataclass(frozen=True)
class InitialDesignRecord:
    """单臂单任务单 seed 的初始化指纹（可识别性审计/公平性审计输入）。"""

    arm: str
    task_id: str
    split: str
    family: str
    seed: int
    budget: int
    meta_seed: int | None
    initializer: str
    code_path: str
    implementation: str
    candidate_pool_sha256: str | None
    artifact_sha256: str | None
    initial_designs: tuple[tuple[float, ...], ...]
    initial_designs_sha256: str
    true_evals_used: int
    requested_evaluations: int
    status: str
    physical_call_count: int = PHYSICAL_CALL_COUNT

    def to_dict(self) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["initial_designs"] = [list(design) for design in self.initial_designs]
        return payload


def arm_init_record(
    result: ArmResult,
    *,
    meta_seed: int | None = None,
    candidate_pool_sha256: str | None = None,
    artifact_sha256: str | None = None,
) -> InitialDesignRecord:
    """从 ArmResult 提取初始化指纹（BO/DE 的前 8 次评价即初始设计）。"""
    if not isinstance(result, ArmResult):
        raise M5ArmError(f"result 必须是 ArmResult，实际 {type(result).__name__}")
    if result.arm not in M5_ARM_ORDER:
        raise M5ArmError(f"未知 M5 臂: {result.arm!r}")
    observations = list(result.observations)
    if len(observations) < M5_INITIAL_DESIGN_COUNT:
        raise M5ArmError(
            f"{result.arm}/{result.task_id}/{result.seed} 观测数 {len(observations)} "
            f"< 初始设计数 {M5_INITIAL_DESIGN_COUNT}"
        )
    initial = np.asarray(
        [observation.design_u for observation in observations[: M5_INITIAL_DESIGN_COUNT]],
        dtype=np.float64,
    )
    return InitialDesignRecord(
        arm=result.arm,
        task_id=result.task_id,
        split=result.split,
        family=result.family,
        seed=int(result.seed),
        budget=int(result.budget),
        meta_seed=None if meta_seed is None else int(meta_seed),
        initializer=ARM_INITIALIZERS[result.arm],
        code_path=ARM_CODE_PATHS[result.arm],
        implementation=result.implementation,
        candidate_pool_sha256=candidate_pool_sha256,
        artifact_sha256=artifact_sha256,
        initial_designs=tuple(tuple(float(value) for value in row) for row in initial),
        initial_designs_sha256=designs_digest(initial),
        true_evals_used=int(result.true_evals_used),
        requested_evaluations=int(result.requested_evaluations),
        status=result.status,
    )


def _assert_equal_budget(result: ArmResult, budget: int, arm: str) -> None:
    """等预算 fail-closed 断言：每臂恰好消耗 budget 次真实（合成）评价。"""
    if result.true_evals_used != budget:
        raise M5ArmError(
            f"{arm}/{result.task_id}/{result.seed} 等预算约束被破坏："
            f"true_evals_used={result.true_evals_used} != budget={budget}"
        )
    if result.requested_evaluations != budget:
        raise M5ArmError(
            f"{arm}/{result.task_id}/{result.seed} requested_evaluations="
            f"{result.requested_evaluations} != budget={budget}"
        )


def score_m5_init_designs(
    model_artifact: Mapping[str, Any],
    design_space: Any,
    task: Any,
    *,
    seed: int,
    method: str,
    candidate_count: int = M5_CANDIDATE_POOL_SIZE,
    initial_design_count: int = M5_INITIAL_DESIGN_COUNT,
    diversity_candidate_count: int = M5_DIVERSITY_CANDIDATE_COUNT,
    k_shot: int = 0,
) -> dict[str, Any]:
    """用代理对候选池打分并选出初始设计（预测标签只用于排序，不进 observations）。

    pretrain 臂用 method='none'（监督预训练模型的零样本预测）；
    MAML 臂用 method='maml'（元学习初始化处的零样本预测）；两者候选池完全相同。
    """
    if not isinstance(model_artifact, Mapping) or "artifact" not in model_artifact:
        raise M5ArmError("model_artifact 必须包含 'artifact'（build_m5_model_artifacts 的输出）")
    if method not in ("none", "maml"):
        raise M5ArmError(f"method 必须为 'none' 或 'maml'，实际 {method!r}")
    artifact = model_artifact["artifact"]
    expected_sha = model_artifact.get("artifact_sha256")
    actual_sha = artifact_sha256(artifact)
    if expected_sha is not None and str(expected_sha) != actual_sha:
        raise M5ArmError("model_artifact.artifact_sha256 与 artifact 内容不一致（被篡改）")
    wall_start = time.perf_counter()
    scored = score_maml_init_designs(
        artifact,
        design_space,
        task,
        seed=seed,
        candidate_count=candidate_count,
        initial_design_count=initial_design_count,
        diversity_candidate_count=diversity_candidate_count,
        method=method,
        k_shot=k_shot,
        target_names=tuple(model_artifact.get("target_names") or ()),
        context_names=tuple(CONTEXT_NAMES),
    )
    wall_s = time.perf_counter() - wall_start
    candidates = np.asarray(scored["candidate_designs"], dtype=np.float64)
    designs = np.asarray(scored["designs"], dtype=np.float64)
    return {
        "designs": designs,
        "candidate_pool_sha256": designs_digest(candidates),
        "initial_designs_sha256": designs_digest(designs),
        "candidate_indices": list(scored["candidate_indices"]),
        "selections": list(scored["selections"]),
        "candidate_count": int(candidate_count),
        "initial_design_count": int(initial_design_count),
        "diversity_candidate_count": int(diversity_candidate_count),
        "method": method,
        "k_shot": int(k_shot),
        "artifact_sha256": actual_sha,
        "meta_seed": model_artifact.get("meta_seed"),
        "proxy_scoring_cost": {
            "kind": "model_scored_init",
            "meta_seed": model_artifact.get("meta_seed"),
            "proxy_method": method,
            "candidates_scored": int(candidate_count),
            "model_forward_predictions": int(scored["proxy_scoring_cost"]["model_forward_predictions"]),
            "adaptation_k_shot": int(k_shot),
            "true_evaluation_budget_used": 0,
            "wall_s": float(wall_s),
            "candidate_pool_sha256": designs_digest(candidates),
            "artifact_sha256": actual_sha,
        },
    }


def _initial_metadata(count: int, *, initializer: str, extra: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    metadata = []
    for index in range(count):
        entry = {"initializer": initializer, "index": index}
        if extra:
            entry.update(dict(extra))
        metadata.append(entry)
    return metadata


def run_m5_bo_arm(
    arm: str,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    seed: int,
    budget: int = M5_BUDGETS[0],
    design_space: Any = None,
    model_artifact: Mapping[str, Any] | None = None,
    reference_objective: float | None = None,
    run_id: str = "",
    candidate_count: int = M5_CANDIDATE_POOL_SIZE,
    initial_design_count: int = M5_INITIAL_DESIGN_COUNT,
    diversity_candidate_count: int = M5_DIVERSITY_CANDIDATE_COUNT,
    strategy: str = "bayesian",
) -> ArmResult:
    """运行一个 M5 BO 臂；三个 BO 臂共用同一 BO 引擎，只允许初始化不同。"""
    if arm not in M5_BO_ARMS:
        raise M5ArmError(f"arm 必须是 {M5_BO_ARMS} 之一，实际 {arm!r}")
    if not callable(evaluate):
        raise M5ArmError("evaluate 必须可调用")
    if type(seed) is not int or seed < 0:
        raise M5ArmError(f"seed 必须是非负整数，实际 {seed!r}")
    if type(budget) is not int or budget < initial_design_count:
        raise M5ArmError(
            f"budget 必须是 >= {initial_design_count} 的整数，实际 {budget!r}"
        )
    task_id = str(getattr(task, "task_id"))
    split = str(getattr(task, "split"))
    family = str(getattr(task, "family"))
    proxy_cost: dict[str, Any]
    if arm == M5_BO_RANDOM:
        initial = shared_initial_designs(task_id, seed, count=initial_design_count)
        proxy_cost = {
            "kind": "shared_lhs_init",
            "initial_design_count": int(initial_design_count),
            "candidates_scored": 0,
            "model_forward_predictions": 0,
            "adaptation_k_shot": 0,
            "true_evaluation_budget_used": 0,
            "wall_s": 0.0,
            "initial_designs_sha256": designs_digest(initial),
        }
        metadata = _initial_metadata(initial_design_count, initializer=ARM_INITIALIZERS[arm])
    else:
        if design_space is None:
            raise M5ArmError(f"{arm} 需要 12D 合成设计空间做单位门禁")
        assert_synthetic_design_space(design_space)
        if model_artifact is None:
            raise M5ArmError(f"{arm} 需要 model_artifact（代理模型打分选初始点）")
        method = "none" if arm == M5_BO_PRETRAIN_INIT else "maml"
        scored = score_m5_init_designs(
            model_artifact,
            design_space,
            task,
            seed=seed,
            method=method,
            candidate_count=candidate_count,
            initial_design_count=initial_design_count,
            diversity_candidate_count=diversity_candidate_count,
        )
        initial = scored["designs"]
        proxy_cost = dict(scored["proxy_scoring_cost"])
        metadata = _initial_metadata(
            initial_design_count,
            initializer=ARM_INITIALIZERS[arm],
            extra={
                "proxy_method": method,
                "meta_seed": scored.get("meta_seed"),
                "candidate_pool_sha256": scored["candidate_pool_sha256"],
                "artifact_sha256": scored["artifact_sha256"],
            },
        )
    result = run_bo_arm(
        LEGACY_BO_ARM,
        evaluate,
        task_id=task_id,
        split=split,
        family=family,
        seed=seed,
        budget=budget,
        initial_designs=initial,
        initial_design_metadata=metadata,
        strategy=strategy,
        reference_objective=reference_objective,
        candidate_count=512,
        run_id=run_id,
        proxy_scoring_cost=proxy_cost,
    )
    _assert_equal_budget(result, budget, arm)
    return dataclasses.replace(
        result,
        arm=arm,
        implementation=ARM_IMPLEMENTATIONS[arm],
        proxy_scoring_cost=proxy_cost,
    )


def run_m5_de_arm(
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    seed: int,
    budget: int = M5_BUDGETS[0],
    reference_objective: float | None = None,
    run_id: str = "",
) -> ArmResult:
    """运行 M5-DE：等预算 DE/rand/1/bin，初始种群与 M5-BO-random 共享同一 8 点。"""
    result = run_de_arm(
        evaluate,
        task_id=str(getattr(task, "task_id")),
        split=str(getattr(task, "split")),
        family=str(getattr(task, "family")),
        seed=seed,
        budget=budget,
        population_size=M5_DE_POPULATION_SIZE,
        mutation_factor=M5_DE_MUTATION_FACTOR,
        crossover_rate=M5_DE_CROSSOVER_RATE,
        reference_objective=reference_objective,
        run_id=run_id,
    )
    _assert_equal_budget(result, budget, M5_DE)
    initial = shared_initial_designs(result.task_id, result.seed, count=M5_INITIAL_DESIGN_COUNT)
    return dataclasses.replace(
        result,
        arm=M5_DE,
        implementation=ARM_IMPLEMENTATIONS[M5_DE],
        proxy_scoring_cost={
            "kind": "shared_lhs_init",
            "initial_design_count": M5_INITIAL_DESIGN_COUNT,
            "candidates_scored": 0,
            "model_forward_predictions": 0,
            "adaptation_k_shot": 0,
            "true_evaluation_budget_used": 0,
            "wall_s": 0.0,
            "initial_designs_sha256": designs_digest(initial),
        },
    )


def run_m5_arm(
    arm: str,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    seed: int,
    budget: int = M5_BUDGETS[0],
    design_space: Any = None,
    model_artifact: Mapping[str, Any] | None = None,
    reference_objective: float | None = None,
    run_id: str = "",
) -> ArmResult:
    """统一入口：按臂名分派到 BO 路径或 DE 路径。"""
    if arm == M5_DE:
        return run_m5_de_arm(
            evaluate,
            task=task,
            seed=seed,
            budget=budget,
            reference_objective=reference_objective,
            run_id=run_id,
        )
    return run_m5_bo_arm(
        arm,
        evaluate,
        task=task,
        seed=seed,
        budget=budget,
        design_space=design_space,
        model_artifact=model_artifact,
        reference_objective=reference_objective,
        run_id=run_id,
    )


#: 冻结的 M5 初始化/臂参数（写入 run_config 与预注册，复核用）。
M5_FROZEN_INIT = {
    "stage": STAGE,
    "arms": list(M5_ARM_ORDER),
    "bo_engine": LEGACY_BO_ARM,
    "bo_initial_design_count": M5_INITIAL_DESIGN_COUNT,
    "maml_init_candidate_count": M5_CANDIDATE_POOL_SIZE,
    "maml_init_initial_design_count": M5_INITIAL_DESIGN_COUNT,
    "maml_init_diversity_candidate_count": M5_DIVERSITY_CANDIDATE_COUNT,
    "dedup_tolerance": M5_DEDUP_TOLERANCE,
    "de_population_size": M5_DE_POPULATION_SIZE,
    "de_mutation_factor": M5_DE_MUTATION_FACTOR,
    "de_crossover_rate": M5_DE_CROSSOVER_RATE,
    "budgets": list(M5_BUDGETS),
    "optimization_seeds": list(M5_OPTIMIZATION_SEEDS),
    "meta_seeds": list(M5_META_SEEDS),
    "proxy_hidden_sizes": list(M5_PROXY_HIDDEN_SIZES),
    "maml_proxy_meta_steps": M5_PROXY_META_STEPS,
    "pretrain_steps": M5_PRETRAIN_STEPS,
    "clone_overlap_threshold": CLONE_OVERLAP_THRESHOLD,
    "clone_group_threshold": CLONE_GROUP_THRESHOLD,
    "physical_call_count": PHYSICAL_CALL_COUNT,
}


def _rounded_design_set(designs: Sequence[Sequence[float]]) -> set[tuple[float, ...]]:
    matrix = np.round(np.asarray(designs, dtype=np.float64), 12)
    return {tuple(float(value) for value in row) for row in matrix}


def _initial_overlap(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> float:
    left_set = _rounded_design_set(left)
    right_set = _rounded_design_set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / max(len(left_set), len(right_set))


def _bucket_key(record: InitialDesignRecord) -> tuple[str, int, int]:
    return (record.task_id, int(record.seed), int(record.budget))


def _reference_record(
    bucket: Mapping[tuple[str, int | None], InitialDesignRecord],
    candidate: InitialDesignRecord,
    reference_arm: str,
) -> InitialDesignRecord | None:
    """同一组内为候选记录匹配参照臂记录：同 meta_seed 优先，否则取 meta_seed=None 的基线记录。"""
    exact = bucket.get((reference_arm, candidate.meta_seed))
    if exact is not None:
        return exact
    return bucket.get((reference_arm, None))


def identifiability_audit(records: Sequence[InitialDesignRecord]) -> dict[str, Any]:
    """可识别性审计：初始点是否真的不同、代理 artifact 是否真的不同。

    判定规则（预注册）：
    * 模型打分臂 vs M5-BO-random：若在 >=90% 的组上初始 8 点重合 >=90%，标注
      CLONE_OF_M5-BO-random 并从推断中排除；
    * pretrain-init vs MAML-init：同样阈值下若初始点重合 >=90%，标注
      RANKING_INDISTINGUISHABLE（披露，不据此宣称两臂不同）；
    * M5-DE 与 M5-BO-random 的初始点按设计完全相同（公平性要求），但采集引擎不同，
      因此单独标注 SAME_INIT_DIFFERENT_ENGINE，不判克隆。
    """
    if not records:
        raise M5ArmError("identifiability_audit 需要至少一条 InitialDesignRecord")
    groups: dict[tuple[str, int, int], dict[tuple[str, int | None], InitialDesignRecord]] = {}
    for record in records:
        bucket = groups.setdefault(_bucket_key(record), {})
        key = (record.arm, record.meta_seed)
        if key in bucket:
            raise M5ArmError(
                f"重复记录：arm={record.arm} task={record.task_id} seed={record.seed} "
                f"budget={record.budget} meta_seed={record.meta_seed}"
            )
        bucket[key] = record
    groups_checked = len(groups)
    arms_present = sorted({record.arm for record in records})
    budgets_compared = sorted({int(record.budget) for record in records})
    pairs: list[dict[str, Any]] = []

    def _compare(candidate: str, reference: str, *, clone_possible: bool, clone_label: str) -> dict[str, Any]:
        overlaps: list[float] = []
        for bucket in groups.values():
            candidates = [entry for (arm, _), entry in bucket.items() if arm == candidate]
            for entry in candidates:
                reference_record = _reference_record(bucket, entry, reference)
                if reference_record is None:
                    continue
                overlaps.append(
                    _initial_overlap(entry.initial_designs, reference_record.initial_designs)
                )
        if not overlaps:
            return {
                "arm": candidate,
                "reference": reference,
                "groups_compared": 0,
                "mean_initial_overlap": None,
                "max_initial_overlap": None,
                "fraction_groups_at_threshold": None,
                "clone": False,
                "label": "NOT_COMPARABLE",
                "note": "没有同时包含两臂的 (task, seed, budget) 组",
            }
        array = np.asarray(overlaps, dtype=np.float64)
        mean_overlap = float(array.mean())
        fraction = float(np.mean(array >= CLONE_OVERLAP_THRESHOLD))
        clone = bool(
            clone_possible
            and mean_overlap >= CLONE_OVERLAP_THRESHOLD
            and fraction >= CLONE_GROUP_THRESHOLD
        )
        return {
            "arm": candidate,
            "reference": reference,
            "groups_compared": len(overlaps),
            "mean_initial_overlap": mean_overlap,
            "max_initial_overlap": float(array.max()),
            "fraction_groups_at_threshold": fraction,
            "clone": clone,
            "label": clone_label if clone else "IDENTIFIABLE",
            "note": "" if not clone else "初始点几乎相同，按预注册规则从推断中排除",
        }

    clone_arms: list[str] = []
    indistinguishable_arms: list[str] = []
    for arm in (M5_BO_PRETRAIN_INIT, M5_BO_MAML_INIT):
        if arm in arms_present:
            pair = _compare(arm, M5_BO_RANDOM, clone_possible=True, clone_label=f"CLONE_OF_{M5_BO_RANDOM}")
            pairs.append(pair)
            if pair["clone"]:
                clone_arms.append(arm)
    if M5_DE in arms_present:
        pair = _compare(M5_DE, M5_BO_RANDOM, clone_possible=False, clone_label="SAME_INIT_DIFFERENT_ENGINE")
        if pair["groups_compared"]:
            pair["label"] = "SAME_INIT_DIFFERENT_ENGINE"
            pair["note"] = "初始 8 点按公平性设计相同；采集算法不同（DE/rand/1/bin vs 约束 BO）"
        pairs.append(pair)
    if M5_BO_PRETRAIN_INIT in arms_present and M5_BO_MAML_INIT in arms_present:
        pair = _compare(
            M5_BO_MAML_INIT,
            M5_BO_PRETRAIN_INIT,
            clone_possible=True,
            clone_label="RANKING_INDISTINGUISHABLE",
        )
        pairs.append(pair)
        if pair["clone"]:
            indistinguishable_arms = [M5_BO_PRETRAIN_INIT, M5_BO_MAML_INIT]
    # A5-M5-02：臂对重叠率在全部 budget 上聚合，显式记录聚合口径，供 clone_audit.csv
    # 的 budget/budget_scope 列使用（原先这些字段缺失导致 CSV 两列全空）。
    budget_label = ",".join(str(budget) for budget in budgets_compared)
    for pair in pairs:
        pair.setdefault("budget", budget_label)
        pair.setdefault("budget_scope", "aggregate_all_budgets")
        pair.setdefault("budgets_compared", list(budgets_compared))
    code_paths = {ARM_CODE_PATHS[arm] for arm in arms_present}
    implementations = {ARM_IMPLEMENTATIONS[arm] for arm in arms_present}
    status = "IDENTIFIABLE" if not clone_arms and not indistinguishable_arms else "CLONE_ARMS_PRESENT"
    return {
        "stage": STAGE,
        "status": status,
        "arms_present": arms_present,
        "budgets_compared": budgets_compared,
        "groups_checked": groups_checked,
        "distinct_code_paths": len(code_paths),
        "distinct_implementations": len(implementations),
        "clone_arms": sorted(clone_arms),
        "indistinguishable_arms": sorted(indistinguishable_arms),
        "pairs": pairs,
        "physical_call_count": PHYSICAL_CALL_COUNT,
    }


def assert_m5_fairness(records: Sequence[InitialDesignRecord]) -> dict[str, Any]:
    """公平性/等预算审计（fail-closed）：发现违例即抛 M5ArmError。

    审计分组键为 (task_id, seed, budget, meta_seed)。模型打分臂
    （pretrain-init / MAML-init）按预注册设计对每个 meta seed 各产生一条记录，
    因此 meta_seed 是同臂多记录的合法维度；只有同一键内同一臂出现两条记录
    才算重复组。跨臂共享检查（pretrain/MAML 候选池与 artifact 指纹）只在同一
    meta_seed 内比较，避免把不同元训练种子的 artifact 误判为同源。
    """
    if not records:
        raise M5ArmError("assert_m5_fairness 需要至少一条 InitialDesignRecord")
    errors: list[str] = []
    groups: dict[tuple[str, int, int, int | None], dict[str, InitialDesignRecord]] = {}
    for record in records:
        key = (record.task_id, int(record.seed), int(record.budget), record.meta_seed)
        bucket = groups.setdefault(key, {})
        if record.arm in bucket:
            errors.append(f"重复组 {key} 臂 {record.arm}")
        bucket[record.arm] = record
        if record.true_evals_used != record.budget:
            errors.append(
                f"{record.arm}/{record.task_id}/{record.seed}: true_evals_used="
                f"{record.true_evals_used} != budget={record.budget}"
            )
        if record.requested_evaluations != record.budget:
            errors.append(
                f"{record.arm}/{record.task_id}/{record.seed}: requested_evaluations != budget"
            )
        if record.physical_call_count != PHYSICAL_CALL_COUNT:
            errors.append(f"{record.arm}/{record.task_id}/{record.seed}: physical_call_count != 0")
        if len(record.initial_designs) != M5_INITIAL_DESIGN_COUNT:
            errors.append(f"{record.arm}/{record.task_id}/{record.seed}: 初始设计数不是 8")
        matrix = np.asarray(record.initial_designs, dtype=np.float64)
        if matrix.size and (not np.all(np.isfinite(matrix)) or np.any(matrix < 0.0) or np.any(matrix > 1.0)):
            errors.append(f"{record.arm}/{record.task_id}/{record.seed}: 初始设计不在 [0,1]^12")
        if len(_rounded_design_set(record.initial_designs)) != len(record.initial_designs):
            errors.append(f"{record.arm}/{record.task_id}/{record.seed}: 初始设计在 1e-12 去重下不唯一")
    for key, bucket in groups.items():
        if M5_BO_PRETRAIN_INIT in bucket and M5_BO_MAML_INIT in bucket:
            left = bucket[M5_BO_PRETRAIN_INIT]
            right = bucket[M5_BO_MAML_INIT]
            if left.candidate_pool_sha256 != right.candidate_pool_sha256:
                errors.append(f"组 {key}: pretrain/MAML 候选池指纹不一致")
            if left.artifact_sha256 is not None and left.artifact_sha256 == right.artifact_sha256:
                errors.append(f"组 {key}: pretrain/MAML 代理 artifact 指纹相同")
    if errors:
        raise M5ArmError("M5 公平性审计失败：" + "；".join(errors[:10]))
    return {
        "status": "PASS",
        "records": len(records),
        "groups": len(groups),
        "group_key_fields": ["task_id", "seed", "budget", "meta_seed"],
        "arms": sorted({record.arm for record in records}),
        "initial_design_count": M5_INITIAL_DESIGN_COUNT,
        "dedup_tolerance": M5_DEDUP_TOLERANCE,
        "physical_call_count": PHYSICAL_CALL_COUNT,
    }


def identifiability_rows(audit: Mapping[str, Any]) -> list[dict[str, Any]]:
    """把审计结果展开为 CSV 行（metrics/audit 产物）。"""
    rows: list[dict[str, Any]] = []
    for pair in audit.get("pairs", ()):
        rows.append(
            {
                "arm": pair.get("arm"),
                "reference_arm": pair.get("reference"),
                "reference": pair.get("reference"),
                "budget": pair.get("budget"),
                "budget_scope": pair.get("budget_scope"),
                "budgets_compared": pair.get("budgets_compared"),
                "groups_compared": pair.get("groups_compared"),
                "mean_initial_overlap": pair.get("mean_initial_overlap"),
                "max_initial_overlap": pair.get("max_initial_overlap"),
                "fraction_groups_at_threshold": pair.get("fraction_groups_at_threshold"),
                "clone": pair.get("clone"),
                "label": pair.get("label"),
                "note": pair.get("note"),
                "physical_call_count": PHYSICAL_CALL_COUNT,
            }
        )
    return rows


__all__ = [
    "ARM_CODE_PATHS",
    "ARM_IMPLEMENTATIONS",
    "ARM_INITIALIZERS",
    "CLONE_GROUP_THRESHOLD",
    "CLONE_OVERLAP_THRESHOLD",
    "InitialDesignRecord",
    "LEGACY_BO_ARM",
    "M5ArmError",
    "M5_BO_ARMS",
    "M5_BO_MAML_INIT",
    "M5_BO_PRETRAIN_INIT",
    "M5_BO_RANDOM",
    "M5_BUDGETS",
    "M5_CANDIDATE_POOL_SIZE",
    "M5_DE",
    "M5_DE_CROSSOVER_RATE",
    "M5_DE_MUTATION_FACTOR",
    "M5_DE_POPULATION_SIZE",
    "M5_DIVERSITY_CANDIDATE_COUNT",
    "M5_FROZEN_INIT",
    "M5_INITIAL_DESIGN_COUNT",
    "M5_META_SEEDS",
    "M5_OPTIMIZATION_SEEDS",
    "M5_PRETRAIN_STEPS",
    "M5_PROXY_HIDDEN_SIZES",
    "M5_PROXY_META_STEPS",
    "M5_ARM_ORDER",
    "PHYSICAL_CALL_COUNT",
    "arm_init_record",
    "arm_metadata",
    "artifact_sha256",
    "assert_m5_fairness",
    "build_m5_maml_artifact",
    "build_m5_model_artifacts",
    "build_m5_pretrain_artifact",
    "canonical_digest",
    "designs_digest",
    "identifiability_audit",
    "identifiability_rows",
    "run_m5_arm",
    "run_m5_bo_arm",
    "run_m5_de_arm",
    "score_m5_init_designs",
]
