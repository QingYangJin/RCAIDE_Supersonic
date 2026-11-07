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
    EvaluationRecord,
    _constraints_or_none,
    _finite_or_none,
    _record_from_result,
    _summarize_arm,
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


def design_row_digests(designs: Any) -> list[str]:
    """逐行设计指纹（与 designs_digest 相同的 1e-12 舍入），用于臂间初始设计重叠率。"""
    matrix = np.asarray(designs, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != DESIGN_DIM:
        raise M5ArmError(f"设计矩阵必须为 (n,{DESIGN_DIM})，实际 {matrix.shape}")
    rounded = np.round(matrix, 12)
    return [
        hashlib.sha256(np.ascontiguousarray(row, dtype="<f8").tobytes()).hexdigest()
        for row in rounded
    ]


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
    support_features: np.ndarray | None = None,
    support_targets: np.ndarray | None = None,
) -> dict[str, Any]:
    """用代理对候选池打分并选出初始设计（预测标签只用于排序，不进 observations）。

    pretrain 臂用 method='none'（监督预训练模型的零样本预测）；
    MAML 臂用 method='maml'（元学习初始化处的零样本预测）；两者候选池完全相同。
    """
    if not isinstance(model_artifact, Mapping) or "artifact" not in model_artifact:
        raise M5ArmError("model_artifact 必须包含 'artifact'（build_m5_model_artifacts 的输出）")
    if method not in ("none", "maml", "fine_tuning"):
        raise M5ArmError(f"method 必须为 'none' / 'maml' / 'fine_tuning'，实际 {method!r}")
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
        support_features=support_features,
        support_targets=support_targets,
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
    "design_row_digests",
    "designs_digest",
    "identifiability_audit",
    "identifiability_rows",
    "run_m5_arm",
    "run_m5_bo_arm",
    "run_m5_de_arm",
    "score_m5_init_designs",
    "S1ArmError",
    "S1_ARM_IDS",
    "S1_BUDGETS",
    "S1_CLONE_ARM",
    "S1_CLONE_IDENTIFIABILITY",
    "S1_CLONE_TARGET",
    "S1_DE",
    "S1_FOMAML_KSHOT_BO",
    "S1_FOMAML_ZERO_BO",
    "S1_IDENTIFIABLE",
    "S1_INITIAL_DESIGN_COUNT",
    "S1_INITIAL_PHASE",
    "S1_K_VALUES",
    "S1_MODEL_SCORED_ARMS",
    "S1_PRETRAIN_KSHOT_BO",
    "S1_RANDOM_BO",
    "S1_STAGE",
    "S1_SUPPORT_PHASE",
    "make_s1_support_cache_evaluator",
    "run_s1_arm",
    "run_s1_bo_arm",
    "run_s1_de_arm",
    "s1_expected_budget",
    "s1_identifiability",
    "s1_new_initial_designs",
]


# ===========================================================================
# S1（task-215）：K-shot 支持评价计入预算的五臂闭环
# ===========================================================================
S1_ARM_IDS: tuple[str, ...] = (
    "RAND-BO",
    "PRETRAIN-KSHOT-BO",
    "FOMAML-ZERO-BO",
    "FOMAML-KSHOT-BO",
    "DE",
)
S1_RANDOM_BO = "RAND-BO"
S1_PRETRAIN_KSHOT_BO = "PRETRAIN-KSHOT-BO"
S1_FOMAML_ZERO_BO = "FOMAML-ZERO-BO"
S1_FOMAML_KSHOT_BO = "FOMAML-KSHOT-BO"
S1_DE = "DE"
S1_MODEL_SCORED_ARMS: tuple[str, ...] = (
    S1_PRETRAIN_KSHOT_BO,
    S1_FOMAML_ZERO_BO,
    S1_FOMAML_KSHOT_BO,
)
S1_K_VALUES: tuple[int, ...] = (0, 1, 3, 5)
S1_BUDGETS: tuple[int, ...] = (64, 128)
S1_INITIAL_DESIGN_COUNT = 8
S1_SUPPORT_PHASE = "support"
S1_INITIAL_PHASE = "initial"
S1_STAGE = "P4-S1"
S1_CLONE_ARM = S1_FOMAML_KSHOT_BO
S1_CLONE_TARGET = S1_FOMAML_ZERO_BO
S1_IDENTIFIABLE = "IDENTIFIABLE"
S1_CLONE_IDENTIFIABILITY = "CLONE_OF_FOMAML-ZERO-BO"


class S1ArmError(M5ArmError):
    """S1 K-shot 闭环错误（fail-closed：预算/支持集/克隆标记不一致）。"""


def s1_expected_budget(k_shot: int, budget: int) -> dict[str, int]:
    """合同 §4/§6 的逐 run 预算分解：K + (8-K) + (B-8) = B。"""
    if type(k_shot) is not int or k_shot not in S1_K_VALUES:
        raise S1ArmError(f"k_shot 必须是 {S1_K_VALUES} 之一，实际 {k_shot!r}")
    if type(budget) is not int or budget not in S1_BUDGETS:
        raise S1ArmError(f"budget 必须是 {S1_BUDGETS} 之一，实际 {budget!r}")
    if budget < S1_INITIAL_DESIGN_COUNT:
        raise S1ArmError(f"budget 必须 >= {S1_INITIAL_DESIGN_COUNT}，实际 {budget!r}")
    return {
        "budget_B": int(budget),
        "K": int(k_shot),
        "initial_designs": int(S1_INITIAL_DESIGN_COUNT),
        "support_evals": int(k_shot),
        "initial_evals": int(S1_INITIAL_DESIGN_COUNT - k_shot),
        "bo_evals": int(budget - S1_INITIAL_DESIGN_COUNT),
        "billable_evals": int(budget),
    }


def s1_identifiability(arm: str, k_shot: int) -> dict[str, Any]:
    """K=0 时 FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 同构：登记 CLONE 并排除推断。"""
    if arm not in S1_ARM_IDS:
        raise S1ArmError(f"arm 必须是 {S1_ARM_IDS} 之一，实际 {arm!r}")
    if type(k_shot) is not int or k_shot not in S1_K_VALUES:
        raise S1ArmError(f"k_shot 必须是 {S1_K_VALUES} 之一，实际 {k_shot!r}")
    if arm == S1_CLONE_ARM and k_shot == 0:
        return {
            "identifiability": S1_CLONE_IDENTIFIABILITY,
            "clone_of": S1_CLONE_TARGET,
            "inference_eligible": False,
        }
    return {
        "identifiability": S1_IDENTIFIABLE,
        "clone_of": None,
        "inference_eligible": True,
    }


def _s1_design_key(design: Any) -> tuple[float, ...]:
    vector = np.asarray(design, dtype=np.float64).reshape(-1)
    if vector.shape != (DESIGN_DIM,):
        raise S1ArmError(f"设计向量必须为 {DESIGN_DIM} 维，实际 {vector.shape}")
    if not np.all(np.isfinite(vector)):
        raise S1ArmError("设计向量必须有限")
    return tuple(float(value) for value in np.round(vector, 12))


def _s1_as_unit_designs(
    values: Any,
    *,
    label: str,
    expected_rows: int | None = None,
) -> np.ndarray:
    designs = np.asarray(values, dtype=np.float64)
    if designs.ndim != 2 or designs.shape[1] != DESIGN_DIM:
        raise S1ArmError(f"{label} 必须为 (n, {DESIGN_DIM})，实际 {designs.shape}")
    if expected_rows is not None and designs.shape[0] != expected_rows:
        raise S1ArmError(f"{label} 行数必须为 {expected_rows}，实际 {designs.shape[0]}")
    if not np.all(np.isfinite(designs)):
        raise S1ArmError(f"{label} 必须有限")
    if np.any(designs < 0.0) or np.any(designs > 1.0):
        raise S1ArmError(f"{label} 必须位于 [0,1]^{DESIGN_DIM}")
    return designs


def _s1_as_support_designs(k_shot: int, support_designs: Any) -> np.ndarray:
    if k_shot == 0:
        if support_designs is None:
            return np.zeros((0, DESIGN_DIM), dtype=np.float64)
        designs = np.asarray(support_designs, dtype=np.float64)
        if designs.size == 0:
            return np.zeros((0, DESIGN_DIM), dtype=np.float64)
        if designs.ndim != 2 or designs.shape != (0, DESIGN_DIM):
            raise S1ArmError(f"K=0 时 support_designs 必须为空，实际 {designs.shape}")
        return designs
    return _s1_as_unit_designs(support_designs, label="support_designs", expected_rows=k_shot)


def _s1_assert_support_prefix(initial_designs: np.ndarray, support_designs: np.ndarray) -> None:
    rows = support_designs.shape[0]
    for index in range(rows):
        if _s1_design_key(initial_designs[index]) != _s1_design_key(support_designs[index]):
            raise S1ArmError(f"initial_designs 前 {rows} 行必须逐位等于 support_designs（第 {index} 行不符）")


def make_s1_support_cache_evaluator(
    base_evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    support_designs: Any,
    support_results: Sequence[Mapping[str, Any]],
):
    """把 K 个支持评价包装为缓存命中（billable=False），不重复消耗真实预算。"""
    if not callable(base_evaluate):
        raise S1ArmError("base_evaluate 必须可调用")
    support = _s1_as_unit_designs(support_designs, label="support_designs")
    results = list(support_results)
    if len(results) != support.shape[0]:
        raise S1ArmError(
            f"support_results 长度 {len(results)} 与 support_designs 行数 {support.shape[0]} 不一致"
        )
    table: dict[tuple[float, ...], tuple[int, dict[str, Any]]] = {}
    for index, (design, result) in enumerate(zip(support, results), start=1):
        if not isinstance(result, Mapping):
            raise S1ArmError(f"support_results[{index - 1}] 必须是映射")
        key = _s1_design_key(design)
        if key in table:
            raise S1ArmError("support_designs 存在重复点，缓存键冲突")
        table[key] = (index, dict(result))

    def evaluate(design: Any) -> Mapping[str, Any]:
        vector = np.asarray(design, dtype=np.float64).reshape(-1)
        entry = table.get(_s1_design_key(vector))
        if entry is None:
            return base_evaluate(vector)
        support_index, payload = entry
        result = dict(payload)
        result["cache_hit"] = True
        result["billable"] = False
        result["support_eval_index"] = int(support_index)
        return result

    return evaluate


def _s1_support_xy(task: Any, support_designs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """K 个支持点的代理特征/标签（供 K-shot 适配打分；标签只用于排序）。"""
    from .data_contract import CONTEXT_NAMES as S1_CONTEXT_NAMES
    from .surrogate import encode_features

    designs = _s1_as_unit_designs(support_designs, label="support_designs")
    features = np.asarray(
        encode_features(designs, dict(getattr(task, "context", {})), S1_CONTEXT_NAMES),
        dtype=np.float64,
    )
    labels = task.truth(designs)
    target_names = ("objective",) + tuple(getattr(task, "enabled_constraint_names", ()))
    columns = []
    for name in target_names:
        if name not in labels:
            raise S1ArmError(f"task.truth 缺少目标列 {name!r}")
        columns.append(np.asarray(labels[name], dtype=np.float64))
    targets = np.column_stack(columns)
    if features.shape[0] != designs.shape[0] or targets.shape[0] != designs.shape[0]:
        raise S1ArmError("支持集特征/标签行数与设计点数不一致")
    return features, targets


def s1_new_initial_designs(
    arm: str,
    task: Any,
    *,
    seed: int,
    k_shot: int,
    design_space: Any = None,
    model_artifact: Mapping[str, Any] | None = None,
    support_features: np.ndarray | None = None,
    support_targets: np.ndarray | None = None,
    candidate_count: int = M5_CANDIDATE_POOL_SIZE,
    diversity_candidate_count: int = M5_DIVERSITY_CANDIDATE_COUNT,
) -> dict[str, Any]:
    """构造 8-K 个新初始点（支持集之外），返回设计与代理打分成本。"""
    if arm not in S1_ARM_IDS:
        raise S1ArmError(f"arm 必须是 {S1_ARM_IDS} 之一，实际 {arm!r}")
    if type(seed) is not int or seed < 0:
        raise S1ArmError(f"seed 必须是非负整数，实际 {seed!r}")
    plan = s1_expected_budget(k_shot, M5_BUDGETS[0])
    count = int(plan["initial_evals"])
    task_id = str(getattr(task, "task_id", ""))
    if not task_id:
        raise S1ArmError("task 缺少 task_id")
    if count == 0:
        return {
            "designs": np.zeros((0, DESIGN_DIM), dtype=np.float64),
            "method": "none",
            "k_shot": int(k_shot),
            "artifact_sha256": None,
            "proxy_scoring_cost": {
                "kind": "no_initial_design",
                "model_forward_predictions": 0,
                "adaptation_k_shot": int(k_shot),
                "true_evaluation_budget_used": 0,
            },
        }
    if arm in (S1_RANDOM_BO, S1_DE):
        from .baseline_arms import shared_initial_designs

        shared = shared_initial_designs(task_id, seed, count=S1_INITIAL_DESIGN_COUNT)
        designs = np.asarray(shared[:count], dtype=np.float64)
        return {
            "designs": designs,
            "method": "none",
            "k_shot": int(k_shot),
            "artifact_sha256": None,
            "proxy_scoring_cost": {
                "kind": "shared_lhs_init",
                "initial_design_count": int(S1_INITIAL_DESIGN_COUNT),
                "candidates_scored": 0,
                "model_forward_predictions": 0,
                "adaptation_k_shot": int(k_shot),
                "true_evaluation_budget_used": 0,
                "wall_s": 0.0,
                "initial_designs_sha256": designs_digest(designs),
                "initial_design_row_digests": design_row_digests(designs),
            },
        }
    if design_space is None:
        raise S1ArmError(f"{arm} 需要 12D 合成设计空间做单位门禁")
    if model_artifact is None:
        raise S1ArmError(f"{arm} 需要 model_artifact（代理打分选初始点）")
    if arm == S1_PRETRAIN_KSHOT_BO:
        method = "fine_tuning" if k_shot > 0 else "none"
    elif arm == S1_FOMAML_KSHOT_BO:
        method = "maml" if k_shot > 0 else "none"
    else:
        # 合同：FOMAML-ZERO-BO 在任何 K 下都不做支持集适应（支持点仍真实评价并计入预算）。
        method = "none"
    adapt_k = int(k_shot) if method in ("maml", "fine_tuning") else 0
    if adapt_k > 0:
        if support_features is None or support_targets is None:
            raise S1ArmError(f"{arm} 在 k_shot={k_shot} 时必须提供支持集特征/标签做适配")
    scored = score_m5_init_designs(
        model_artifact,
        design_space,
        task,
        seed=seed,
        method=method,
        candidate_count=candidate_count,
        initial_design_count=count,
        diversity_candidate_count=diversity_candidate_count,
        k_shot=adapt_k,
        support_features=support_features,
        support_targets=support_targets,
    )
    designs = np.asarray(scored["designs"], dtype=np.float64)
    if designs.shape != (count, DESIGN_DIM):
        raise S1ArmError(f"{arm} 代理打分设计形状不符：{designs.shape} != {(count, DESIGN_DIM)}")
    cost = dict(scored["proxy_scoring_cost"])
    cost["kind"] = "s1_model_scored_init"
    cost["method"] = method
    cost["support_evals"] = int(k_shot)
    cost["initial_designs_sha256"] = designs_digest(designs)
    cost["initial_design_row_digests"] = design_row_digests(designs)
    return {
        "designs": designs,
        "method": method,
        "k_shot": int(k_shot),
        "artifact_sha256": scored["artifact_sha256"],
        "proxy_scoring_cost": cost,
    }


def _s1_initial_metadata(k_shot: int, initial_count: int) -> list[dict[str, Any]]:
    metadata: list[dict[str, Any]] = []
    for index in range(initial_count):
        if index < k_shot:
            metadata.append(
                {
                    "initializer": "s1_support_k_shot",
                    "index": index,
                    "phase": S1_SUPPORT_PHASE,
                    "support_eval_index": index + 1,
                    "k_shot": int(k_shot),
                }
            )
        else:
            metadata.append(
                {
                    "initializer": "s1_initial_design",
                    "index": index,
                    "phase": S1_INITIAL_PHASE,
                    "k_shot": int(k_shot),
                }
            )
    return metadata


def run_s1_bo_arm(
    arm: str,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    seed: int,
    budget: int,
    k_shot: int,
    initial_designs: Any,
    model_scoring_cost: Mapping[str, Any] | None = None,
    reference_objective: float | None = None,
    run_id: str = "",
) -> ArmResult:
    """S1 BO 臂：前 K 次为支持评价（缓存命中），随后 8-K 新初始点，再 BO B-8 次。"""
    if arm not in (S1_RANDOM_BO, S1_PRETRAIN_KSHOT_BO, S1_FOMAML_ZERO_BO, S1_FOMAML_KSHOT_BO):
        raise S1ArmError(f"run_s1_bo_arm 不接受 arm={arm!r}")
    plan = s1_expected_budget(k_shot, budget)
    designs = _s1_as_unit_designs(
        initial_designs, label="initial_designs", expected_rows=S1_INITIAL_DESIGN_COUNT
    )
    task_id = str(getattr(task, "task_id", ""))
    split = str(getattr(task, "split", ""))
    family = str(getattr(task, "family", ""))
    metadata = _s1_initial_metadata(k_shot, designs.shape[0])
    result = run_bo_arm(
        LEGACY_BO_ARM,
        evaluate,
        task_id=task_id,
        split=split,
        family=family,
        seed=seed,
        budget=budget,
        initial_designs=designs,
        initial_design_metadata=metadata,
        reference_objective=reference_objective,
        candidate_count=512,
        run_id=run_id,
    )
    if result.requested_evaluations != budget:
        raise S1ArmError(
            f"{arm} requested_evaluations={result.requested_evaluations} != budget={budget}"
        )
    if result.cache_hits != k_shot:
        raise S1ArmError(f"{arm} cache_hits={result.cache_hits} != k_shot={k_shot}")
    if result.true_evals_used != budget - k_shot:
        raise S1ArmError(
            f"{arm} true_evals_used={result.true_evals_used} != budget-k_shot={budget - k_shot}"
        )
    proxy = {
        "kind": "s1_k_shot_bo",
        "support_evals": int(k_shot),
        "initial_evals": int(plan["initial_evals"]),
        "bo_evals": int(plan["bo_evals"]),
        "billable_evals": int(budget),
        "model_scoring": dict(model_scoring_cost) if model_scoring_cost is not None else None,
    }
    return dataclasses.replace(result, arm=arm, implementation=f"{S1_STAGE}:{arm}", proxy_scoring_cost=proxy)


def run_s1_de_arm(
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    seed: int,
    budget: int,
    k_shot: int,
    initial_designs: Any,
    model_scoring_cost: Mapping[str, Any] | None = None,
    reference_objective: float | None = None,
    run_id: str = "",
) -> ArmResult:
    """S1 DE 臂：初始种群 = K 支持点（缓存）+ 8-K 新点；恰好 B 次评价。"""
    from .baseline_arms import (
        DE_CROSSOVER_RATE,
        DE_MUTATION_FACTOR,
        DE_POPULATION_SIZE,
        _de_better,
        _record_from_result,
        _summarize_arm,
        derive_arm_seed,
    )

    plan = s1_expected_budget(k_shot, budget)
    designs = _s1_as_unit_designs(
        initial_designs, label="initial_designs", expected_rows=S1_INITIAL_DESIGN_COUNT
    )
    if designs.shape[0] != DE_POPULATION_SIZE:
        raise S1ArmError(f"DE 初始种群必须为 {DE_POPULATION_SIZE}，实际 {designs.shape[0]}")
    task_id = str(getattr(task, "task_id", ""))
    split = str(getattr(task, "split", ""))
    family = str(getattr(task, "family", ""))
    rng = np.random.default_rng(derive_arm_seed(task_id, seed, "s1-de"))
    records: list[Any] = []
    wall_start = time.perf_counter()

    def _evaluate(vector: np.ndarray, phase: str, generation: int, target_index: int) -> dict[str, Any]:
        clipped = np.clip(np.asarray(vector, dtype=np.float64), 0.0, 1.0)
        result = evaluate(clipped.copy())
        if not isinstance(result, Mapping):
            raise S1ArmError(f"评估器必须返回映射，实际 {type(result).__name__}")
        record = _record_from_result(
            eval_index=len(records) + 1,
            design_u=clipped,
            result=result,
            fallback_status="EVALUATION_FAILED",
        )
        records.append(record)
        return {
            "vector": clipped,
            "result": dict(result),
            "record": record,
            "phase": phase,
            "generation": generation,
            "target_index": target_index,
        }

    population: list[dict[str, Any]] = []
    for index, vector in enumerate(designs):
        phase = S1_SUPPORT_PHASE if index < k_shot else S1_INITIAL_PHASE
        population.append(_evaluate(np.asarray(vector, dtype=np.float64), phase, 0, index))
    if len(records) != S1_INITIAL_DESIGN_COUNT:
        raise S1ArmError(f"DE 初始评价数 {len(records)} != {S1_INITIAL_DESIGN_COUNT}")
    support_hits = sum(1 for record in records if record.cache_hit)
    if support_hits != k_shot:
        raise S1ArmError(f"DE 支持集缓存命中 {support_hits} != k_shot={k_shot}")
    generation = 1
    accepted_trials = 0
    rejected_trials = 0
    generations_completed = 0
    stagnation_generations = 0
    termination_reason = "search_finished"
    while True:
        if len(records) >= budget:
            termination_reason = "budget_exhausted"
            break
        generation_accepted = 0
        for target_index in range(len(population)):
            if len(records) >= budget:
                termination_reason = "budget_exhausted"
                break
            picks = [index for index in range(len(population)) if index != target_index]
            r1, r2, r3 = (int(value) for value in rng.choice(picks, size=3, replace=False))
            mutant = np.clip(
                population[r1]["vector"]
                + DE_MUTATION_FACTOR * (population[r2]["vector"] - population[r3]["vector"]),
                0.0,
                1.0,
            )
            forced_index = int(rng.integers(0, DESIGN_DIM))
            trial = np.array(
                [
                    mutant[index]
                    if rng.random() < DE_CROSSOVER_RATE or index == forced_index
                    else population[target_index]["vector"][index]
                    for index in range(DESIGN_DIM)
                ],
                dtype=np.float64,
            )
            candidate = _evaluate(trial, "generation", generation, target_index)
            accepted = _de_better(candidate["result"], population[target_index]["result"])
            candidate["accepted"] = bool(accepted)
            if accepted:
                accepted_trials += 1
                generation_accepted += 1
                population[target_index] = candidate
            else:
                rejected_trials += 1
        if termination_reason == "budget_exhausted":
            break
        generations_completed = generation
        if generation_accepted == 0:
            stagnation_generations += 1
        generation += 1
    if len(records) != budget:
        raise S1ArmError(f"DE 评价数 {len(records)} != budget={budget}")
    cache_hits = sum(1 for record in records if record.cache_hit)
    if cache_hits != k_shot:
        raise S1ArmError(f"DE 总缓存命中 {cache_hits} != k_shot={k_shot}")
    wall_s = time.perf_counter() - wall_start
    proxy = {
        "kind": "s1_k_shot_de",
        "population_size": int(len(population)),
        "generations_requested": int(max(1, (budget - S1_INITIAL_DESIGN_COUNT) // len(population) + 1)),
        "generations_completed": int(generations_completed),
        "accepted_trials": int(accepted_trials),
        "rejected_trials": int(rejected_trials),
        "stagnation_generations": int(stagnation_generations),
        "support_evals": int(k_shot),
        "initial_evals": int(plan["initial_evals"]),
        "bo_evals": int(plan["bo_evals"]),
        "billable_evals": int(budget),
        "model_scoring": dict(model_scoring_cost) if model_scoring_cost is not None else None,
    }
    return _summarize_arm(
        arm=S1_DE,
        task_id=task_id,
        split=split,
        family=family,
        seed=seed,
        budget=budget,
        observations=records,
        wall_s=wall_s,
        termination_reason=termination_reason,
        implementation=f"{S1_STAGE}:{S1_DE}",
        initial_count=S1_INITIAL_DESIGN_COUNT,
        proxy_scoring_cost=proxy,
        reference_objective=reference_objective,
    )


def run_s1_arm(
    arm: str,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    seed: int,
    budget: int,
    k_shot: int,
    support_designs: Any,
    design_space: Any = None,
    model_artifact: Mapping[str, Any] | None = None,
    reference_objective: float | None = None,
    run_id: str = "",
    support_label_permutation: Sequence[int] | None = None,
) -> ArmResult:
    """S1 五臂入口：支持集评价（缓存、计入预算）+ 新初始点 + 主搜索，共恰好 B 次。

    support_label_permutation 仅用于标签打乱负控诊断：支持集特征/评价保持真实，
    只把用于适配的 K 个支持标签按给定置换重排（K>=2 时有效）。
    """
    if arm not in S1_ARM_IDS:
        raise S1ArmError(f"arm 必须是 {S1_ARM_IDS} 之一，实际 {arm!r}")
    plan = s1_expected_budget(k_shot, budget)
    support = _s1_as_support_designs(k_shot, support_designs)
    support_features: np.ndarray | None = None
    support_targets: np.ndarray | None = None
    support_results: list[dict[str, Any]] = []
    for index, vector in enumerate(support):
        result = evaluate(np.array(vector, dtype=np.float64).copy())
        if not isinstance(result, Mapping):
            raise S1ArmError(f"支持集第 {index + 1} 个评价必须返回映射")
        support_results.append(dict(result))
    cached_evaluate = make_s1_support_cache_evaluator(evaluate, support, support_results)
    if k_shot > 0 and arm in S1_MODEL_SCORED_ARMS:
        support_features, support_targets = _s1_support_xy(task, support)
        if support_label_permutation is not None:
            permutation = [int(value) for value in support_label_permutation]
            if k_shot < 2:
                raise S1ArmError("标签打乱负控要求 k_shot >= 2")
            if len(permutation) != k_shot or sorted(permutation) != list(range(k_shot)):
                raise S1ArmError(f"support_label_permutation 必须是 0..{k_shot - 1} 的置换")
            support_targets = support_targets[permutation]
    initial = s1_new_initial_designs(
        arm,
        task,
        seed=seed,
        k_shot=k_shot,
        design_space=design_space,
        model_artifact=model_artifact,
        support_features=support_features,
        support_targets=support_targets,
    )
    new_designs = np.asarray(initial["designs"], dtype=np.float64)
    if new_designs.shape != (plan["initial_evals"], DESIGN_DIM):
        raise S1ArmError(f"新初始点形状不符：{new_designs.shape}")
    for row in new_designs:
        if _s1_design_key(row) in {_s1_design_key(item) for item in support}:
            raise S1ArmError("新初始点与支持集重叠（泄漏）")
    combined = (
        np.vstack([support, new_designs]) if support.shape[0] else new_designs
    )
    if combined.shape != (S1_INITIAL_DESIGN_COUNT, DESIGN_DIM):
        raise S1ArmError(f"初始设计总数 {combined.shape[0]} != {S1_INITIAL_DESIGN_COUNT}")
    _s1_assert_support_prefix(combined, support)
    if arm == S1_DE:
        return run_s1_de_arm(
            cached_evaluate,
            task=task,
            seed=seed,
            budget=budget,
            k_shot=k_shot,
            initial_designs=combined,
            model_scoring_cost=initial["proxy_scoring_cost"],
            reference_objective=reference_objective,
            run_id=run_id,
        )
    return run_s1_bo_arm(
        arm,
        cached_evaluate,
        task=task,
        seed=seed,
        budget=budget,
        k_shot=k_shot,
        initial_designs=combined,
        model_scoring_cost=initial["proxy_scoring_cost"],
        reference_objective=reference_objective,
        run_id=run_id,
    )






# ===========================================================================
# S3（task-261 rev36）：F-QE-conflict-v1 五臂闭环、联合评分与 RNG 合同
# 计划 docs/planning/p4_route_a_s3_execution_plan_20261107.md v1.2a §3/§4.1/§5.1
# 全部纯 CPU 合成评估；physical_call_count=0；不 import 任何真实求解器入口。
#
# CONTRACT_AMBIGUITY（已上报 Lead，不自行改合同）：
# 1) §3.1 要求每臂内部走 baseline_arms.run_bo_arm 的 LEGACY_BO_ARM 合同路径，但
#    run_bo_arm 的引擎 seed=derive_arm_seed(task_id, seed, "bo", arm) 含 arm 名，
#    与 §3.1-1 冻结公式（不含 arm/budget）冲突。本段按更具体的 RNG 合同直接使用
#    maml_opt.bayesian.ConstrainedBayesianOptimizer + run_search，并复用
#    baseline_arms._record_from_result / _summarize_arm 生成逐字段兼容的结果。
# 2) 克隆检测会命中 S3-BO-RANDOM / S3-DE：两者初始 8 点按 §3.1-5 与 §3.3 同为
#    support(5)+shared(3)，故对这对由合同强制的相同初始点做豁免并披露。
# ===========================================================================

S3_ARM_IDS: tuple[str, ...] = (
    "S3-BO-RANDOM",
    "S3-BO-FOMAML-OBJ",
    "S3-BO-FOMAML-CON",
    "S3-BO-ANIL-CON",
    "S3-DE",
)
S3_BO_RANDOM = "S3-BO-RANDOM"
S3_BO_FOMAML_OBJ = "S3-BO-FOMAML-OBJ"
S3_BO_FOMAML_CON = "S3-BO-FOMAML-CON"
S3_BO_ANIL_CON = "S3-BO-ANIL-CON"
S3_DE = "S3-DE"
S3_BO_ARM_IDS: tuple[str, ...] = S3_ARM_IDS[:4]
S3_STAGE = "P4-S3"
S3_K_SHOT = 5
S3_BUDGETS: tuple[int, ...] = (64, 128)
S3_INITIAL_DESIGN_COUNT = 8
S3_NEW_INITIAL_COUNT = 3
S3_CANDIDATE_POOL_SIZE = 123
S3_CANDIDATE_COUNT = 512
S3_DIVERSITY_MIN_NORM = 0.10
S3_JOINT_PENALTY = 10.0
S3_OUTPUT_DIM = 3
S3_EVAL_SOURCES: tuple[str, ...] = ("support", "initial", "bo", "de")
S3_CLONE_IDENTIFIABILITY = "CLONE"
S3_LIMITED_IDENTIFIABILITY = "IDENTIFIABILITY_LIMITED"
S3_IDENTIFIABLE = "IDENTIFIABLE"
S3_CLONE_RATE_THRESHOLD = 0.20
S3_DE_POPULATION_SIZE = 8
S3_DE_MUTATION_FACTOR = 0.5
S3_DE_CROSSOVER_RATE = 0.7
S3_DE_MAX_RETRY = 100
S3_SCORE_OBJ = "S_obj"
S3_SCORE_JOINT = "S_joint"
S3_SCORE_NONE = "none"
S3_CALIBRATION = "NOT_PERFORMED"
S3_BO_CONFIG: dict[str, Any] = {
    "engine": "maml_opt.bayesian.ConstrainedBayesianOptimizer",
    "strategy": "bayesian",
    "candidate_count": S3_CANDIDATE_COUNT,
    "minimum_model_observations": 5,
    "alpha": 1e-6,
    "exploration": 0.01,
}
S3_CLONE_EXEMPT_PAIRS: tuple[tuple[str, str], ...] = ((S3_BO_RANDOM, S3_DE),)


class S3ArmError(M5ArmError):
    """S3 五臂闭环错误（fail-closed：预算/公平/RNG/泄漏合同不一致）。"""


def _s3_require_int(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise S3ArmError(f"{label} 必须是 >= {minimum} 的整数，实际 {value!r}")
    return int(value)


def _s3_require_task(task: Any) -> Any:
    for name in ("task_id", "split", "family"):
        if not hasattr(task, name):
            raise S3ArmError(f"task 缺少属性 {name}")
    for name in ("support_designs", "support_subset", "truth"):
        if not callable(getattr(task, name, None)):
            raise S3ArmError(f"task 缺少方法 {name}()")
    return task


def _s3_require_evaluate(evaluate: Any) -> Callable[[np.ndarray], Mapping[str, Any]]:
    if not callable(evaluate):
        raise S3ArmError("evaluate 必须可调用")
    return evaluate


def _s3_round_designs(designs: Any, label: str) -> np.ndarray:
    matrix = np.asarray(designs, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[1] != DESIGN_DIM:
        raise S3ArmError(f"{label} 必须为 (n, {DESIGN_DIM})，实际 {matrix.shape}")
    if not np.all(np.isfinite(matrix)):
        raise S3ArmError(f"{label} 必须有限")
    return matrix


def _s3_pairs_distance_stats(designs: np.ndarray) -> tuple[float, float]:
    matrix = _s3_round_designs(designs, "designs")
    count = matrix.shape[0]
    if count < 2:
        return 0.0, 0.0
    pairwise = matrix[:, np.newaxis, :] - matrix[np.newaxis, :, :]
    distances = np.sqrt(np.sum(pairwise**2, axis=2)) / math.sqrt(float(DESIGN_DIM))
    mask = np.triu(np.ones((count, count), dtype=bool), k=1)
    values = distances[mask]
    return float(np.min(values)), float(np.max(values))


def _s3_min_norm(design: np.ndarray, references: np.ndarray) -> float:
    if references.shape[0] == 0:
        return float("inf")
    deltas = references - np.asarray(design, dtype=np.float64)[np.newaxis, :]
    return float(np.min(np.sqrt(np.sum(deltas**2, axis=1)) / math.sqrt(float(DESIGN_DIM))))


def s3_bo_engine_seed(task_id: str, opt_seed: int, meta_seed: int) -> int:
    """计划 §3.1-1：BO 引擎 seed，不含 arm/budget，四臂两预算共享。"""
    if not isinstance(task_id, str) or not task_id:
        raise S3ArmError("task_id 必须是非空字符串")
    opt = _s3_require_int(opt_seed, "opt_seed")
    meta = _s3_require_int(meta_seed, "meta_seed")
    text = f"{task_id}|{opt}|{meta}|s3-bo-engine"
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**31)


def s3_de_engine_seed(task_id: str, opt_seed: int, meta_seed: int) -> int:
    """计划 §3.1-4：DE seed 与 BO 不共享随机流。"""
    if not isinstance(task_id, str) or not task_id:
        raise S3ArmError("task_id 必须是非空字符串")
    opt = _s3_require_int(opt_seed, "opt_seed")
    meta = _s3_require_int(meta_seed, "meta_seed")
    text = f"{task_id}|{opt}|{meta}|s3-de"
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**31)


def s3_support_seed(task_id: str, meta_seed: int) -> int:
    """支持集 seed：与 s1_runner.support_seed 逐位一致（{task}|s1-support|{meta}）。"""
    if not isinstance(task_id, str) or not task_id:
        raise S3ArmError("task_id 必须是非空字符串")
    meta = _s3_require_int(meta_seed, "meta_seed")
    text = f"{task_id}|s1-support|{meta}"
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) % (2**31 - 1)


def s3_select_support_designs(task: Any, *, k_shot: int = S3_K_SHOT, meta_seed: int = 0) -> np.ndarray:
    """计划 §3.1：同一 task/meta_seed 下五臂支持集逐位相同（K=5）。"""
    task = _s3_require_task(task)
    if type(k_shot) is not int or k_shot != S3_K_SHOT:
        raise S3ArmError(f"k_shot 固定为 {S3_K_SHOT}，实际 {k_shot!r}")
    seed = s3_support_seed(str(task.task_id), meta_seed)
    support = np.asarray(task.support_subset(k_shot, seed), dtype=np.float64)
    return _s3_round_designs(support, "support_designs")


def s3_shared_initial_designs(task_id: str, opt_seed: int, *, count: int = S3_INITIAL_DESIGN_COUNT) -> np.ndarray:
    """计划 §3.1-5：由 (task_id, opt_seed, "shared-init") 派生的五臂共享初始点。

    两步派生：先对 "task_id|opt_seed|shared-init" 取 8 字节整数作为
    baseline_arms.shared_initial_designs 的 seed，再调用其 LHS 生成器；结果对
    (task_id, opt_seed, count) 完全确定。
    """
    if not isinstance(task_id, str) or not task_id:
        raise S3ArmError("task_id 必须是非空字符串")
    opt = _s3_require_int(opt_seed, "opt_seed")
    if type(count) is not int or count <= 0:
        raise S3ArmError(f"count 必须是正整数，实际 {count!r}")
    text = f"{task_id}|{opt}|shared-init"
    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) % (2**31)
    designs = shared_initial_designs(task_id, seed, count=count)
    return _s3_round_designs(designs, "shared_initial_designs")


def s3_candidate_pool(task: Any, *, meta_seed: int = 0) -> np.ndarray:
    """计划 §3.2：support LHS 128 点去掉 5 个 support 点后的 123 点共享候选池。"""
    task = _s3_require_task(task)
    pool = _s3_round_designs(np.asarray(task.support_designs(), dtype=np.float64), "support_designs")
    support = s3_select_support_designs(task, k_shot=S3_K_SHOT, meta_seed=meta_seed)
    support_keys = {_s1_design_key(row) for row in support}
    keep = [index for index, row in enumerate(pool) if _s1_design_key(row) not in support_keys]
    candidates = np.asarray(pool[keep], dtype=np.float64)
    if candidates.shape[0] != S3_CANDIDATE_POOL_SIZE:
        raise S3ArmError(
            f"候选池大小必须为 {S3_CANDIDATE_POOL_SIZE}，实际 {candidates.shape[0]}"
        )
    return candidates


def s3_candidate_pool_sha256(task: Any, *, meta_seed: int = 0) -> str:
    return designs_digest(s3_candidate_pool(task, meta_seed=meta_seed))


def s3_bo_engine_draws(engine_seed: int, *, candidate_count: int = S3_CANDIDATE_COUNT) -> np.ndarray:
    """引擎在首个观测前的候选抽样序列（与 maml_opt 的 _candidate_pool 逐位一致）。

    maml_opt 的候选池 = qmc.LatinHypercube(d, seed=engine_seed + _ask_count).random(n)
    再缩放到 [lower, upper]；本函数复算 _ask_count=0 时的结果（不调用私有属性），
    单测断言与 ConstrainedBayesianOptimizer._candidate_pool() 逐位相等。
    """
    seed = _s3_require_int(engine_seed, "engine_seed")
    if type(candidate_count) is not int or candidate_count <= 0:
        raise S3ArmError(f"candidate_count 必须是正整数，实际 {candidate_count!r}")
    from scipy.stats import qmc

    sampler = qmc.LatinHypercube(d=DESIGN_DIM, seed=seed)
    unit = sampler.random(candidate_count)
    lower = np.zeros(DESIGN_DIM, dtype=np.float64)
    upper = np.ones(DESIGN_DIM, dtype=np.float64)
    return np.asarray(qmc.scale(unit, lower, upper), dtype=np.float64)


def s3_bo_engine_draws_sha256(engine_seed: int, *, candidate_count: int = S3_CANDIDATE_COUNT) -> str:
    return designs_digest(s3_bo_engine_draws(engine_seed, candidate_count=candidate_count))


def s3_bo_config_sha256() -> str:
    return canonical_digest(S3_BO_CONFIG)


def s3_expected_budget(budget: int) -> dict[str, int]:
    """计划 §3.3：B = 5 support + 3 new initial + (B-8) 主搜索 = B 次计费评估。"""
    if type(budget) is not int or budget not in S3_BUDGETS:
        raise S3ArmError(f"budget 必须是 {S3_BUDGETS} 之一，实际 {budget!r}")
    if budget < S3_INITIAL_DESIGN_COUNT:
        raise S3ArmError(f"budget 必须 >= {S3_INITIAL_DESIGN_COUNT}，实际 {budget!r}")
    return {
        "budget_B": int(budget),
        "K": int(S3_K_SHOT),
        "initial_designs": int(S3_INITIAL_DESIGN_COUNT),
        "support_evals": int(S3_K_SHOT),
        "initial_evals": int(S3_NEW_INITIAL_COUNT),
        "bo_or_de_evals": int(budget - S3_INITIAL_DESIGN_COUNT),
        "billable_evals": int(budget),
    }


def s3_normalization(f_support: Any, g_support: Any) -> dict[str, Any]:
    """计划 §3.2：仅用 support 标签的逐任务归一化参数（ddof=0，尺度下限 1e-6）。"""
    f_values = np.asarray(f_support, dtype=np.float64).reshape(-1)
    if f_values.size == 0 or not np.all(np.isfinite(f_values)):
        raise S3ArmError("f_support 必须是非空有限向量")
    g_values = np.asarray(g_support, dtype=np.float64)
    if g_values.ndim != 2 or g_values.shape[0] != f_values.size or g_values.shape[1] != 2:
        raise S3ArmError(f"g_support 必须为 ({f_values.size}, 2)，实际 {g_values.shape}")
    if not np.all(np.isfinite(g_values)):
        raise S3ArmError("g_support 必须有限")
    f_mean = float(np.mean(f_values))
    f_scale = max(float(np.std(f_values)), 1e-6)
    g_scale = [
        max(float(math.sqrt(float(np.mean(g_values[:, k] ** 2)))), 1e-6) for k in range(2)
    ]
    return {"f_mean": f_mean, "f_scale": f_scale, "g_scale": g_scale}


def s3_standardize_labels(f: Any, g1: Any, g2: Any, normalization: Mapping[str, Any]) -> np.ndarray:
    f_values = np.asarray(f, dtype=np.float64).reshape(-1)
    g1_values = np.asarray(g1, dtype=np.float64).reshape(-1)
    g2_values = np.asarray(g2, dtype=np.float64).reshape(-1)
    if not (f_values.size == g1_values.size == g2_values.size):
        raise S3ArmError("f/g1/g2 长度必须一致")
    f_mean = float(normalization["f_mean"])
    f_scale = float(normalization["f_scale"])
    g_scale = list(normalization["g_scale"])
    if f_scale <= 0.0 or len(g_scale) != 2 or min(g_scale) <= 0.0:
        raise S3ArmError("归一化尺度必须为正")
    return np.stack(
        [
            (f_values - f_mean) / f_scale,
            g1_values / float(g_scale[0]),
            g2_values / float(g_scale[1]),
        ],
        axis=1,
    )


def s3_joint_score(f_tilde_hat: Any, g1_tilde_hat: Any, g2_tilde_hat: Any) -> np.ndarray:
    """计划 §3.2 冻结公式 S_joint = f_tilde_hat + 10*(max(0,g1)+max(0,g2))^2。"""
    f_hat = np.asarray(f_tilde_hat, dtype=np.float64).reshape(-1)
    g1_hat = np.asarray(g1_tilde_hat, dtype=np.float64).reshape(-1)
    g2_hat = np.asarray(g2_tilde_hat, dtype=np.float64).reshape(-1)
    if not (f_hat.size == g1_hat.size == g2_hat.size):
        raise S3ArmError("f/g1/g2 预测长度必须一致")
    violation = np.maximum(0.0, g1_hat) + np.maximum(0.0, g2_hat)
    return f_hat + S3_JOINT_PENALTY * np.square(violation)


def _s3_extract_support_labels(results: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    f_values: list[float] = []
    g_values: list[list[float]] = []
    for position, result in enumerate(results):
        if not isinstance(result, Mapping):
            raise S3ArmError(f"支持评估结果必须是映射，第 {position} 条为 {type(result).__name__}")
        objective = result.get("objective")
        constraints = result.get("constraints_g_le_zero")
        if not isinstance(constraints, Mapping):
            raise S3ArmError(f"支持评估结果缺少 constraints_g_le_zero（第 {position} 条）")
        if not {"g1", "g2"} <= set(constraints):
            raise S3ArmError(f"约束名必须包含 g1/g2，实际 {sorted(constraints)}")
        try:
            f_values.append(float(objective))
        except (TypeError, ValueError) as exc:
            raise S3ArmError(f"objective 非法（第 {position} 条）: {exc}") from exc
        g_values.append([float(constraints["g1"]), float(constraints["g2"])])
    f_array = np.asarray(f_values, dtype=np.float64)
    g_array = np.asarray(g_values, dtype=np.float64)
    if not np.all(np.isfinite(f_array)) or not np.all(np.isfinite(g_array)):
        raise S3ArmError("支持集标签出现非有限值")
    return f_array, g_array


def _s3_scorer_spec(scorer: Any) -> dict[str, Any]:
    if scorer is None:
        return {"meta_seed": None, "head_only": None, "config": None}
    predict = getattr(scorer, "predict", None)
    adapt = getattr(scorer, "adapt", None)
    if not callable(predict) or not callable(adapt):
        raise S3ArmError("scorer 必须提供 adapt(...) 与 predict(...)")
    config = getattr(scorer, "config", None)
    config_payload = None
    if config is not None and hasattr(config, "to_dict"):
        config_payload = config.to_dict()
    return {
        "meta_seed": getattr(scorer, "meta_seed", None),
        "head_only": getattr(scorer, "head_only", None),
        "config": config_payload,
    }


def _s3_adapt_and_predict(
    scorer: Any,
    support_designs: np.ndarray,
    support_labels_standardized: np.ndarray,
    designs: np.ndarray,
) -> tuple[np.ndarray, float, int]:
    if scorer is None:
        raise S3ArmError("该臂需要代理 scorer（OBJ/CON/ANIL）")
    started = time.perf_counter()
    adapted = scorer.adapt(support_designs, support_labels_standardized)
    predictions = adapted.predict(designs)
    elapsed = time.perf_counter() - started
    array = np.asarray(predictions, dtype=np.float64)
    if array.shape != (designs.shape[0], S3_OUTPUT_DIM):
        raise S3ArmError(f"scorer.predict 形状必须为 ({designs.shape[0]}, 3)，实际 {array.shape}")
    if not np.all(np.isfinite(array)):
        raise S3ArmError("scorer.predict 出现非有限值")
    return array, elapsed, int(designs.shape[0])


def s3_select_diverse_designs(
    candidates: Any,
    *,
    reference_designs: Any,
    count: int = S3_NEW_INITIAL_COUNT,
    scores: Any = None,
    min_distance: float = S3_DIVERSITY_MIN_NORM,
) -> dict[str, Any]:
    """计划 §3.2 多样性规则：d_norm>=0.10；不足时按已选点最小距离降序补足并标记 relaxed。"""
    matrix = _s3_round_designs(candidates, "candidates")
    references = _s3_round_designs(reference_designs, "reference_designs")
    if type(count) is not int or count <= 0:
        raise S3ArmError(f"count 必须是正整数，实际 {count!r}")
    if count > matrix.shape[0]:
        raise S3ArmError(f"候选数不足：需要 {count}，实际 {matrix.shape[0]}")
    if not math.isfinite(float(min_distance)) or min_distance < 0.0:
        raise S3ArmError(f"min_distance 必须是非负有限值，实际 {min_distance!r}")
    if scores is None:
        order = list(range(matrix.shape[0]))
        score_values = None
    else:
        score_values = np.asarray(scores, dtype=np.float64).reshape(-1)
        if score_values.size != matrix.shape[0] or not np.all(np.isfinite(score_values)):
            raise S3ArmError("scores 必须是与候选数一致的有限向量")
        order = sorted(range(matrix.shape[0]), key=lambda index: (float(score_values[index]), index))
    selected: list[int] = []
    relaxed = False
    for index in order:
        if len(selected) >= count:
            break
        chosen = matrix[np.asarray(selected, dtype=np.int64)] if selected else references
        pool = np.vstack([references, chosen]) if selected else references
        if _s3_min_norm(matrix[index], pool) >= min_distance:
            selected.append(index)
    if len(selected) < count:
        relaxed = True
        remaining = [index for index in order if index not in selected]
        while len(selected) < count and remaining:
            best_index = None
            best_distance = -1.0
            for index in remaining:
                chosen = matrix[np.asarray(selected, dtype=np.int64)] if selected else references
                pool = np.vstack([references, chosen]) if selected else references
                distance = _s3_min_norm(matrix[index], pool)
                if distance > best_distance:
                    best_distance = distance
                    best_index = index
            if best_index is None:
                break
            selected.append(int(best_index))
            remaining.remove(int(best_index))
    chosen_designs = matrix[np.asarray(selected, dtype=np.int64)]
    return {
        "designs": chosen_designs,
        "indices": [int(index) for index in selected],
        "scores": [float(score_values[index]) for index in selected] if score_values is not None else None,
        "diversity_relaxed": bool(relaxed),
        "min_distance": float(min_distance),
    }


def _s3_new_initial_designs(
    arm: str,
    *,
    task: Any,
    meta_seed: int,
    opt_seed: int,
    scorer: Any,
    support_designs: np.ndarray,
    support_labels: np.ndarray,
    normalization: Mapping[str, Any],
) -> dict[str, Any]:
    shared = s3_shared_initial_designs(str(task.task_id), opt_seed, count=S3_INITIAL_DESIGN_COUNT)
    shared_keys = {_s1_design_key(row) for row in shared}
    support_keys = {_s1_design_key(row) for row in support_designs}
    if shared_keys & support_keys:
        raise S3ArmError("FAILED_LEAKAGE: shared_initial_designs 与 support 集重叠")
    if arm in (S3_BO_RANDOM, S3_DE):
        picked = s3_select_diverse_designs(
            shared,
            reference_designs=support_designs,
            count=S3_NEW_INITIAL_COUNT,
        )
        return {
            "designs": picked["designs"],
            "indices": picked["indices"],
            "source": "shared_initial_designs",
            "score_kind": S3_SCORE_NONE,
            "scores": None,
            "diversity_relaxed": picked["diversity_relaxed"],
            "scoring_wall_s": 0.0,
            "forward_predictions": 0,
            "candidates_scored": 0,
        }
    if arm not in S3_BO_ARM_IDS:
        raise S3ArmError(f"未知 S3 臂: {arm!r}；允许 {S3_ARM_IDS}")
    pool = s3_candidate_pool(task, meta_seed=meta_seed)
    score_kind = S3_SCORE_OBJ if arm == S3_BO_FOMAML_OBJ else S3_SCORE_JOINT
    predictions, elapsed, forward_count = _s3_adapt_and_predict(
        scorer,
        support_designs,
        support_labels,
        pool,
    )
    f_hat = predictions[:, 0]
    g1_hat = predictions[:, 1]
    g2_hat = predictions[:, 2]
    scores = f_hat if score_kind == S3_SCORE_OBJ else s3_joint_score(f_hat, g1_hat, g2_hat)
    picked = s3_select_diverse_designs(
        pool,
        reference_designs=support_designs,
        count=S3_NEW_INITIAL_COUNT,
        scores=scores,
    )
    return {
        "designs": picked["designs"],
        "indices": picked["indices"],
        "source": "candidate_pool",
        "score_kind": score_kind,
        "scores": picked["scores"],
        "diversity_relaxed": picked["diversity_relaxed"],
        "scoring_wall_s": float(elapsed),
        "forward_predictions": int(forward_count),
        "candidates_scored": int(pool.shape[0]),
    }


def _s3_record_from_result(
    *,
    eval_index: int,
    design_u: np.ndarray,
    result: Mapping[str, Any] | None,
) -> EvaluationRecord:
    return _record_from_result(
        eval_index=eval_index,
        design_u=design_u,
        result=result,
        fallback_status="EVALUATION_FAILED",
    )


def _s3_provenance(
    *,
    arm: str,
    task: Any,
    budget: int,
    opt_seed: int,
    meta_seed: int,
    budget_plan: Mapping[str, int],
    support_designs: np.ndarray,
    initial_designs: np.ndarray,
    new_initial: Mapping[str, Any],
    normalization: Mapping[str, Any] | None,
    scorer: Any,
    records: Sequence[EvaluationRecord],
    rng: Mapping[str, Any],
    trace: np.ndarray | None,
    adaptation_wall_s: float,
) -> dict[str, Any]:
    initial_rows = np.asarray(initial_designs, dtype=np.float64)
    diversity_min, diversity_max = _s3_pairs_distance_stats(initial_rows)
    source_counts = {source: 0 for source in S3_EVAL_SOURCES}
    for record in records:
        index = record.eval_index
        if index <= S3_K_SHOT:
            source_counts["support"] += 1
        elif index <= S3_INITIAL_DESIGN_COUNT:
            source_counts["initial"] += 1
        else:
            source_counts["bo" if arm in S3_BO_ARM_IDS else "de"] += 1
        if not record.billable:
            raise S3ArmError(f"第 {index} 条评估记录 billable=False，违反预算记账合同")
    billable_evals = sum(1 for record in records if record.billable)
    payload = {
        "arm": arm,
        "task_id": str(task.task_id),
        "split": str(task.split),
        "family": str(task.family),
        "budget": int(budget),
        "opt_seed": int(opt_seed),
        "meta_seed": int(meta_seed),
        "budget_plan": dict(budget_plan),
        "budget_sources": source_counts,
        "billable_evals": int(billable_evals),
        "records": int(len(records)),
        "rng": dict(rng),
        "initial": {
            "support_designs_sha256": designs_digest(support_designs),
            "initial_designs_sha256": designs_digest(initial_rows),
            "initial_design_row_digests": design_row_digests(initial_rows),
            "new_initial_indices": list(new_initial["indices"]),
            "new_initial_source": str(new_initial["source"]),
            "initial_diversity_min": float(diversity_min),
            "initial_diversity_max": float(diversity_max),
            "diversity_relaxed": bool(new_initial["diversity_relaxed"]),
        },
        "scoring": {
            "score_kind": str(new_initial["score_kind"]),
            "scores": list(new_initial["scores"]) if new_initial.get("scores") is not None else None,
            "scorer": _s3_scorer_spec(scorer),
            "normalization": dict(normalization) if normalization is not None else None,
            "scoring_wall_s": float(new_initial["scoring_wall_s"]),
            "forward_predictions": int(new_initial["forward_predictions"]),
            "candidates_scored": int(new_initial["candidates_scored"]),
        },
        "adaptation_wall_s": float(adaptation_wall_s),
        "trace": {
            "trace_sha256": designs_digest(trace) if trace is not None and len(trace) else None,
            "trace_row_digests": design_row_digests(trace) if trace is not None and len(trace) else [],
            "trace_length": int(len(trace)) if trace is not None else 0,
        },
        "uncertainty": None,
        "calibration": S3_CALIBRATION,
        "s3_provenance_schema": "p4ra-s3-arm-provenance-v1",
    }
    expected = dict(budget_plan)
    if payload["records"] != expected["billable_evals"]:
        raise S3ArmError(
            f"FAILED_BUDGET_MISMATCH: 记录数 {payload['records']} != B {expected['billable_evals']}"
        )
    if payload["billable_evals"] != expected["billable_evals"]:
        raise S3ArmError(
            f"FAILED_BUDGET_MISMATCH: billable {payload['billable_evals']} != B {expected['billable_evals']}"
        )
    if source_counts["support"] != expected["support_evals"]:
        raise S3ArmError("FAILED_BUDGET_MISMATCH: support 评价数不符")
    if source_counts["initial"] != expected["initial_evals"]:
        raise S3ArmError("FAILED_BUDGET_MISMATCH: initial 评价数不符")
    search_key = "bo" if arm in S3_BO_ARM_IDS else "de"
    if source_counts[search_key] != expected["bo_or_de_evals"]:
        raise S3ArmError("FAILED_BUDGET_MISMATCH: 主搜索评价数不符")
    return payload


def _s3_run_bo_search(
    *,
    arm: str,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    task: Any,
    budget: int,
    opt_seed: int,
    meta_seed: int,
    support_designs: np.ndarray,
    support_results: Sequence[Mapping[str, Any]],
    initial_designs: np.ndarray,
) -> tuple[list[EvaluationRecord], np.ndarray, str]:
    from maml_opt.bayesian import ConstrainedBayesianOptimizer, run_search

    engine_seed = s3_bo_engine_seed(str(task.task_id), opt_seed, meta_seed)
    optimizer = ConstrainedBayesianOptimizer(
        np.zeros(DESIGN_DIM, dtype=np.float64),
        np.ones(DESIGN_DIM, dtype=np.float64),
        seed=engine_seed,
        candidate_count=S3_CANDIDATE_COUNT,
        minimum_model_observations=S3_BO_CONFIG["minimum_model_observations"],
        alpha=float(S3_BO_CONFIG["alpha"]),
        exploration=float(S3_BO_CONFIG["exploration"]),
    )
    support_cache = {
        _s1_design_key(design): result for design, result in zip(support_designs, support_results)
    }
    records: list[EvaluationRecord] = []

    def cached_evaluate(design: np.ndarray) -> Mapping[str, Any]:
        key = _s1_design_key(design)
        if key in support_cache:
            base = dict(support_cache[key])
            base["cache_hit"] = True
            base["billable"] = False
            base["analysis_calls"] = 0
            return base
        return evaluate(np.asarray(design, dtype=np.float64).copy())

    def on_observation(observation: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        index = len(records) + 1
        design = np.asarray(observation["design_vector"], dtype=np.float64)
        payload = result
        if index <= S3_K_SHOT:
            payload = dict(result)
            payload["cache_hit"] = False
            payload["billable"] = True
        records.append(_s3_record_from_result(eval_index=index, design_u=design, result=payload))

    search = run_search(
        optimizer,
        cached_evaluate,
        initial_designs,
        budget,
        strategy="bayesian",
        on_observation=on_observation,
    )
    trace = np.asarray(
        [np.asarray(item["design_vector"], dtype=np.float64) for item in search["history"]],
        dtype=np.float64,
    )
    if trace.shape[0] != budget:
        raise S3ArmError(f"BO 评估次数必须为 {budget}，实际 {trace.shape[0]}")
    return records, trace, str(search.get("termination_reason") or "UNKNOWN")


def _s3_de_better(
    trial_objective: float | None,
    trial_constraints: Mapping[str, float] | None,
    incumbent_objective: float | None,
    incumbent_constraints: Mapping[str, float] | None,
) -> bool:
    from ..evaluation.contract import FEASIBILITY_TOLERANCE

    def feasible(objective: float | None, constraints: Mapping[str, float] | None) -> bool:
        return (
            objective is not None
            and constraints is not None
            and bool(constraints)
            and all(value <= FEASIBILITY_TOLERANCE for value in constraints.values())
        )

    trial_ok = feasible(trial_objective, trial_constraints)
    incumbent_ok = feasible(incumbent_objective, incumbent_constraints)
    if trial_ok != incumbent_ok:
        return trial_ok
    if trial_ok and trial_objective is not None and incumbent_objective is not None:
        return trial_objective < incumbent_objective
    trial_violation = sum(max(0.0, value) for value in (trial_constraints or {}).values())
    incumbent_violation = sum(max(0.0, value) for value in (incumbent_constraints or {}).values())
    return trial_violation < incumbent_violation


def _s3_run_de_search(
    *,
    task: Any,
    budget: int,
    opt_seed: int,
    meta_seed: int,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    support_designs: np.ndarray,
    support_results: Sequence[Mapping[str, Any]],
    initial_designs: np.ndarray,
) -> tuple[list[EvaluationRecord], np.ndarray, str]:
    engine_seed = s3_de_engine_seed(str(task.task_id), opt_seed, meta_seed)
    rng = np.random.default_rng(engine_seed)
    records: list[EvaluationRecord] = []
    for design, result in zip(support_designs, support_results):
        records.append(_s3_record_from_result(eval_index=len(records) + 1, design_u=design, result=result))
    population_designs = [np.asarray(design, dtype=np.float64) for design in initial_designs]
    population_results: list[Mapping[str, Any]] = []
    for index in range(S3_NEW_INITIAL_COUNT):
        design = np.asarray(initial_designs[S3_K_SHOT + index], dtype=np.float64).copy()
        result = evaluate(design)
        population_results.append(result)
        records.append(_s3_record_from_result(eval_index=len(records) + 1, design_u=design, result=result))
    population = list(zip(population_designs[:S3_K_SHOT], list(support_results)))
    population.extend(zip(population_designs[S3_K_SHOT:], population_results))
    if len(population) != S3_INITIAL_DESIGN_COUNT:
        raise S3ArmError("DE 初始种群必须为 8 个点")
    seen_keys = {_s1_design_key(item[0]) for item in population}
    attempts = 0
    while len(records) < budget:
        if len(population) < S3_DE_POPULATION_SIZE:
            raise S3ArmError("DE 种群不足 8 个初始点")
        indices = rng.choice(len(population), size=3, replace=False)
        a = np.asarray(population[int(indices[0])][0], dtype=np.float64)
        b = np.asarray(population[int(indices[1])][0], dtype=np.float64)
        c = np.asarray(population[int(indices[2])][0], dtype=np.float64)
        target_index = int(rng.integers(0, len(population)))
        target = np.asarray(population[target_index][0], dtype=np.float64)
        mutant = np.clip(a + S3_DE_MUTATION_FACTOR * (b - c), 0.0, 1.0)
        crossover = rng.random(DESIGN_DIM) < S3_DE_CROSSOVER_RATE
        if not np.any(crossover):
            crossover[int(rng.integers(0, DESIGN_DIM))] = True
        trial = np.where(crossover, mutant, target)
        if _s1_design_key(trial) in seen_keys:
            attempts += 1
            if attempts > S3_DE_MAX_RETRY * budget:
                raise S3ArmError("DE 无法生成未评估的新设计（候选耗尽）")
            continue
        attempts = 0
        trial_result = evaluate(np.asarray(trial, dtype=np.float64).copy())
        records.append(
            _s3_record_from_result(eval_index=len(records) + 1, design_u=trial, result=trial_result)
        )
        seen_keys.add(_s1_design_key(trial))
        incumbent_design, incumbent_result = population[target_index]
        if _s3_de_better(
            _finite_or_none(trial_result.get("objective")) if isinstance(trial_result, Mapping) else None,
            _constraints_or_none(trial_result.get("constraints_g_le_zero")) if isinstance(trial_result, Mapping) else None,
            _finite_or_none(incumbent_result.get("objective")) if isinstance(incumbent_result, Mapping) else None,
            _constraints_or_none(incumbent_result.get("constraints_g_le_zero")) if isinstance(incumbent_result, Mapping) else None,
        ):
            population[target_index] = (trial, trial_result)
    trace = np.asarray(
        [np.asarray(record.design_u, dtype=np.float64) for record in records],
        dtype=np.float64,
    )
    if trace.shape[0] != budget:
        raise S3ArmError(f"DE 评估次数必须为 {budget}，实际 {trace.shape[0]}")
    return records, trace, "MAX_DESIGN_EVALUATIONS"


def run_s3_bo_arm(
    arm: str,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    budget: int,
    opt_seed: int,
    meta_seed: int,
    scorer: Any = None,
    run_id: str = "",
    reference_objective: float | None = None,
) -> ArmResult:
    """S3 BO 臂（RANDOM/OBJ/CON/ANIL）：返回与 S1/M5 BO 路径逐字段兼容的 ArmResult。

    审计元数据（RNG 四元组、初始点指纹、多样性、轨迹摘要、预算记账）放在
    ArmResult.proxy_scoring_cost["s3_provenance"]。
    """
    if arm not in S3_BO_ARM_IDS:
        raise S3ArmError(f"arm 必须是 {S3_BO_ARM_IDS} 之一，实际 {arm!r}")
    task = _s3_require_task(task)
    evaluate = _s3_require_evaluate(evaluate)
    if type(budget) is not int or budget not in S3_BUDGETS:
        raise S3ArmError(f"budget 必须是 {S3_BUDGETS} 之一，实际 {budget!r}")
    _s3_require_int(opt_seed, "opt_seed")
    _s3_require_int(meta_seed, "meta_seed")
    budget_plan = s3_expected_budget(budget)
    wall_start = time.perf_counter()
    support_designs = s3_select_support_designs(task, k_shot=S3_K_SHOT, meta_seed=meta_seed)
    support_results = [evaluate(np.asarray(row, dtype=np.float64).copy()) for row in support_designs]
    f_support, g_support = _s3_extract_support_labels(support_results)
    normalization = s3_normalization(f_support, g_support)
    support_labels = s3_standardize_labels(f_support, g_support[:, 0], g_support[:, 1], normalization)
    new_initial = _s3_new_initial_designs(
        arm,
        task=task,
        meta_seed=meta_seed,
        opt_seed=opt_seed,
        scorer=scorer,
        support_designs=support_designs,
        support_labels=support_labels,
        normalization=normalization,
    )
    initial_designs = np.vstack([support_designs, np.asarray(new_initial["designs"], dtype=np.float64)])
    if initial_designs.shape[0] != S3_INITIAL_DESIGN_COUNT:
        raise S3ArmError("初始设计总数必须为 8")
    initial_keys = {_s1_design_key(row) for row in initial_designs}
    if len(initial_keys) != S3_INITIAL_DESIGN_COUNT:
        raise S3ArmError("FAILED_LEAKAGE: 初始设计出现重复点")
    records, trace, termination_reason = _s3_run_bo_search(
        arm=arm,
        evaluate=evaluate,
        task=task,
        budget=budget,
        opt_seed=opt_seed,
        meta_seed=meta_seed,
        support_designs=support_designs,
        support_results=support_results,
        initial_designs=initial_designs,
    )
    wall_s = time.perf_counter() - wall_start
    engine_seed = s3_bo_engine_seed(str(task.task_id), opt_seed, meta_seed)
    rng = {
        "bo_engine_seed": int(engine_seed),
        "bo_engine_draws_sha256": s3_bo_engine_draws_sha256(engine_seed),
        "candidate_pool_sha256": s3_candidate_pool_sha256(task, meta_seed=meta_seed),
        "candidate_count": int(S3_CANDIDATE_COUNT),
        "bo_config_sha256": s3_bo_config_sha256(),
        "de_engine_seed": None,
    }
    provenance = _s3_provenance(
        arm=arm,
        task=task,
        budget=budget,
        opt_seed=opt_seed,
        meta_seed=meta_seed,
        budget_plan=budget_plan,
        support_designs=support_designs,
        initial_designs=initial_designs,
        new_initial=new_initial,
        normalization=normalization,
        scorer=scorer,
        records=records,
        rng=rng,
        trace=trace,
        adaptation_wall_s=float(new_initial["scoring_wall_s"]),
    )
    return _summarize_arm(
        arm=arm,
        task_id=str(task.task_id),
        split=str(task.split),
        family=str(task.family),
        seed=int(opt_seed),
        budget=int(budget),
        observations=records,
        wall_s=float(wall_s),
        termination_reason=termination_reason,
        implementation="S3-BO-diagnostic-v1",
        initial_count=S3_INITIAL_DESIGN_COUNT,
        proxy_scoring_cost={
            "s3_provenance": provenance,
            "scoring_wall_s": float(new_initial["scoring_wall_s"]),
            "forward_predictions": int(new_initial["forward_predictions"]),
            "candidates_scored": int(new_initial["candidates_scored"]),
        },
        reference_objective=reference_objective,
    )


def run_s3_de_arm(
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    budget: int,
    opt_seed: int,
    meta_seed: int,
    run_id: str = "",
    reference_objective: float | None = None,
) -> ArmResult:
    """S3-DE：support(5)+shared(3) 初始种群，DE/rand/1/bin，总评估 B 次。"""
    task = _s3_require_task(task)
    evaluate = _s3_require_evaluate(evaluate)
    if type(budget) is not int or budget not in S3_BUDGETS:
        raise S3ArmError(f"budget 必须是 {S3_BUDGETS} 之一，实际 {budget!r}")
    _s3_require_int(opt_seed, "opt_seed")
    _s3_require_int(meta_seed, "meta_seed")
    budget_plan = s3_expected_budget(budget)
    wall_start = time.perf_counter()
    support_designs = s3_select_support_designs(task, k_shot=S3_K_SHOT, meta_seed=meta_seed)
    support_results = [evaluate(np.asarray(row, dtype=np.float64).copy()) for row in support_designs]
    f_support, g_support = _s3_extract_support_labels(support_results)
    normalization = s3_normalization(f_support, g_support)
    new_initial = _s3_new_initial_designs(
        S3_DE,
        task=task,
        meta_seed=meta_seed,
        opt_seed=opt_seed,
        scorer=None,
        support_designs=support_designs,
        support_labels=np.zeros((S3_K_SHOT, S3_OUTPUT_DIM), dtype=np.float64),
        normalization=normalization,
    )
    initial_designs = np.vstack([support_designs, np.asarray(new_initial["designs"], dtype=np.float64)])
    if initial_designs.shape[0] != S3_INITIAL_DESIGN_COUNT:
        raise S3ArmError("初始设计总数必须为 8")
    records, trace, termination_reason = _s3_run_de_search(
        task=task,
        budget=budget,
        opt_seed=opt_seed,
        meta_seed=meta_seed,
        evaluate=evaluate,
        support_designs=support_designs,
        support_results=support_results,
        initial_designs=initial_designs,
    )
    wall_s = time.perf_counter() - wall_start
    engine_seed = s3_de_engine_seed(str(task.task_id), opt_seed, meta_seed)
    rng = {
        "bo_engine_seed": None,
        "bo_engine_draws_sha256": None,
        "candidate_pool_sha256": s3_candidate_pool_sha256(task, meta_seed=meta_seed),
        "candidate_count": int(S3_CANDIDATE_COUNT),
        "bo_config_sha256": s3_bo_config_sha256(),
        "de_engine_seed": int(engine_seed),
    }
    provenance = _s3_provenance(
        arm=S3_DE,
        task=task,
        budget=budget,
        opt_seed=opt_seed,
        meta_seed=meta_seed,
        budget_plan=budget_plan,
        support_designs=support_designs,
        initial_designs=initial_designs,
        new_initial=new_initial,
        normalization=normalization,
        scorer=None,
        records=records,
        rng=rng,
        trace=trace,
        adaptation_wall_s=0.0,
    )
    return _summarize_arm(
        arm=S3_DE,
        task_id=str(task.task_id),
        split=str(task.split),
        family=str(task.family),
        seed=int(opt_seed),
        budget=int(budget),
        observations=records,
        wall_s=float(wall_s),
        termination_reason=termination_reason,
        implementation="S3-DE-diagnostic-v1",
        initial_count=S3_INITIAL_DESIGN_COUNT,
        proxy_scoring_cost={"s3_provenance": provenance},
        reference_objective=reference_objective,
    )


def run_s3_arm(
    arm: str,
    evaluate: Callable[[np.ndarray], Mapping[str, Any]],
    *,
    task: Any,
    budget: int,
    opt_seed: int,
    meta_seed: int,
    scorer: Any = None,
    run_id: str = "",
    reference_objective: float | None = None,
) -> ArmResult:
    """S3 五臂统一调度入口（返回 ArmResult，provenance 见 proxy_scoring_cost）。"""
    if arm in S3_BO_ARM_IDS:
        return run_s3_bo_arm(
            arm,
            evaluate,
            task=task,
            budget=budget,
            opt_seed=opt_seed,
            meta_seed=meta_seed,
            scorer=scorer,
            run_id=run_id,
            reference_objective=reference_objective,
        )
    if arm == S3_DE:
        return run_s3_de_arm(
            evaluate,
            task=task,
            budget=budget,
            opt_seed=opt_seed,
            meta_seed=meta_seed,
            run_id=run_id,
            reference_objective=reference_objective,
        )
    raise S3ArmError(f"未知 S3 臂: {arm!r}；允许 {S3_ARM_IDS}")


def s3_arm_provenance(result: ArmResult) -> dict[str, Any]:
    """提取 run_s3_arm/run_s3_bo_arm/run_s3_de_arm 写入的 S3 审计元数据。"""
    if not isinstance(result, ArmResult):
        raise S3ArmError(f"result 必须是 ArmResult，实际 {type(result).__name__}")
    payload = result.proxy_scoring_cost.get("s3_provenance")
    if not isinstance(payload, Mapping):
        raise S3ArmError("ArmResult 缺少 s3_provenance（不是 S3 臂结果？）")
    return dict(payload)


def s3_trace_first_divergence(trace_a: Sequence[str], trace_b: Sequence[str]) -> int | None:
    """两条逐行设计指纹序列的首个分叉索引；完全相同返回 None。"""
    for index, (digest_a, digest_b) in enumerate(zip(trace_a, trace_b)):
        if digest_a != digest_b:
            return int(index)
    if len(trace_a) != len(trace_b):
        return int(min(len(trace_a), len(trace_b)))
    return None


def s3_fairness_report(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """计划 §3.3 公平性断言 + 克隆检测（fail-closed 汇总，不修改 run 数据）。

    runs 每条需含 arm/task_id/budget/opt_seed/meta_seed 与 s3_provenance。
    """
    groups: dict[tuple[str, int, int, int], dict[str, dict[str, Any]]] = {}
    problems: list[str] = []
    for position, run in enumerate(runs):
        if not isinstance(run, Mapping):
            raise S3ArmError(f"runs[{position}] 必须是映射")
        required = ("arm", "task_id", "budget", "opt_seed", "meta_seed", "s3_provenance")
        for name in required:
            if name not in run:
                raise S3ArmError(f"runs[{position}] 缺少 {name}")
        arm = str(run["arm"])
        if arm not in S3_ARM_IDS:
            raise S3ArmError(f"runs[{position}].arm 非法: {arm!r}")
        key = (
            str(run["task_id"]),
            int(run["budget"]),
            int(run["opt_seed"]),
            int(run["meta_seed"]),
        )
        provenance = run["s3_provenance"]
        if not isinstance(provenance, Mapping):
            raise S3ArmError(f"runs[{position}].s3_provenance 必须是映射")
        if arm in groups.setdefault(key, {}):
            raise S3ArmError(f"重复 run：group={key} arm={arm}")
        groups[key][arm] = dict(provenance)
    group_reports: list[dict[str, Any]] = []
    clone_pairs: list[dict[str, Any]] = []
    for key in sorted(groups):
        task_id, budget, opt_seed, meta_seed = key
        arms = groups[key]
        group_problems: list[str] = []
        if set(arms) != set(S3_ARM_IDS):
            group_problems.append(
                f"臂集合不完整：缺少 {sorted(set(S3_ARM_IDS) - set(arms))}"
            )
        base = arms.get(S3_BO_RANDOM) or next(iter(arms.values()))
        reference_fields = {
            "budget": int(budget),
            "budget_plan.budget_B": int(budget),
            "budget_plan.K": int(S3_K_SHOT),
            "budget_plan.initial_designs": int(S3_INITIAL_DESIGN_COUNT),
            "initial.support_designs_sha256": base["initial"]["support_designs_sha256"],
            "rng.candidate_pool_sha256": base["rng"]["candidate_pool_sha256"],
            "rng.candidate_count": int(base["rng"]["candidate_count"]),
            "rng.bo_config_sha256": base["rng"]["bo_config_sha256"],
        }
        for arm, provenance in arms.items():
            checks = {
                "budget": int(provenance["budget"]),
                "budget_plan.budget_B": int(provenance["budget_plan"]["budget_B"]),
                "budget_plan.K": int(provenance["budget_plan"]["K"]),
                "budget_plan.initial_designs": int(provenance["budget_plan"]["initial_designs"]),
                "initial.support_designs_sha256": provenance["initial"]["support_designs_sha256"],
                "rng.candidate_pool_sha256": provenance["rng"]["candidate_pool_sha256"],
                "rng.candidate_count": int(provenance["rng"]["candidate_count"]),
                "rng.bo_config_sha256": provenance["rng"]["bo_config_sha256"],
            }
            for name, expected in reference_fields.items():
                if checks[name] != expected:
                    group_problems.append(f"{arm}: {name} 不一致（{checks[name]!r} != {expected!r}）")
        bo_engines = {
            arm: provenance["rng"]["bo_engine_seed"]
            for arm, provenance in arms.items()
            if arm in S3_BO_ARM_IDS
        }
        if bo_engines and len(set(bo_engines.values())) != 1:
            group_problems.append(f"BO 引擎 seed 不一致: {bo_engines}")
        bo_draws = {
            arm: provenance["rng"]["bo_engine_draws_sha256"]
            for arm, provenance in arms.items()
            if arm in S3_BO_ARM_IDS
        }
        if bo_draws and len(set(bo_draws.values())) != 1:
            group_problems.append("bo_engine_draws_sha256 不一致")
        for arm, provenance in arms.items():
            plan = provenance["budget_plan"]
            sources = provenance["budget_sources"]
            if int(provenance["billable_evals"]) != int(plan["billable_evals"]):
                group_problems.append(f"{arm}: billable_evals != B")
            if int(sources.get("support", -1)) != int(plan["support_evals"]):
                group_problems.append(f"{arm}: support_evals 不符")
            if int(sources.get("initial", -1)) != int(plan["initial_evals"]):
                group_problems.append(f"{arm}: initial_evals 不符")
            if arm in S3_BO_ARM_IDS and "bo" in sources:
                if int(sources["bo"]) != int(plan["bo_or_de_evals"]):
                    group_problems.append(f"{arm}: bo_evals 不符")
            if arm == S3_DE and "de" in sources:
                if int(sources["de"]) != int(plan["bo_or_de_evals"]):
                    group_problems.append(f"{arm}: de_evals 不符")
        initial_hashes: dict[str, str] = {
            arm: str(provenance["initial"]["initial_designs_sha256"])
            for arm, provenance in arms.items()
        }
        arm_pairs = [
            (left, right)
            for index, left in enumerate(S3_ARM_IDS)
            for right in S3_ARM_IDS[index + 1 :]
            if left in arms and right in arms
        ]
        pair_clones: list[tuple[str, str]] = []
        for left, right in arm_pairs:
            if initial_hashes[left] != initial_hashes[right]:
                continue
            if (left, right) in S3_CLONE_EXEMPT_PAIRS or (right, left) in S3_CLONE_EXEMPT_PAIRS:
                continue
            pair_clones.append((left, right))
            clone_pairs.append(
                {
                    "task_id": task_id,
                    "budget": budget,
                    "opt_seed": opt_seed,
                    "meta_seed": meta_seed,
                    "arms": [left, right],
                    "initial_designs_sha256": initial_hashes[left],
                }
            )
        group_reports.append(
            {
                "task_id": task_id,
                "budget": budget,
                "opt_seed": opt_seed,
                "meta_seed": meta_seed,
                "arms": sorted(arms),
                "consistent": not group_problems,
                "problems": group_problems,
                "clone_pairs": [list(pair) for pair in pair_clones],
                "initial_designs_sha256": initial_hashes,
            }
        )
    clone_rate_by_budget: dict[str, float] = {}
    identifiability_by_budget: dict[str, str] = {}
    pair_totals: dict[int, int] = {}
    pair_clones_count: dict[int, int] = {}
    for group in group_reports:
        budget = int(group["budget"])
        pair_totals[budget] = pair_totals.get(budget, 0) + len(S3_ARM_IDS) * (len(S3_ARM_IDS) - 1) // 2
        pair_clones_count[budget] = pair_clones_count.get(budget, 0) + len(group["clone_pairs"])
    for budget in sorted(pair_totals):
        rate = pair_clones_count.get(budget, 0) / float(pair_totals[budget])
        clone_rate_by_budget[str(budget)] = float(rate)
        identifiability_by_budget[str(budget)] = (
            S3_LIMITED_IDENTIFIABILITY if rate > S3_CLONE_RATE_THRESHOLD else S3_IDENTIFIABLE
        )
        if rate > S3_CLONE_RATE_THRESHOLD:
            problems.append(
                f"budget {budget} 克隆率 {rate:.4f} > {S3_CLONE_RATE_THRESHOLD}（IDENTIFIABILITY_LIMITED）"
            )
    for group in group_reports:
        problems.extend(group["problems"])
    return {
        "schema_version": "p4ra-s3-fairness-v1",
        "groups": group_reports,
        "problems": problems,
        "clone_pairs": clone_pairs,
        "clone_rate_by_budget": clone_rate_by_budget,
        "identifiability_by_budget": identifiability_by_budget,
        "exempt_pairs": [list(pair) for pair in S3_CLONE_EXEMPT_PAIRS],
        "ok": not problems,
    }


class S3ModelScorer:
    """把已训练 maml ParameterSet 包成 S3 五臂所需的适配-预测接口。

    - adapt(support_x, support_y) -> S3ModelScorer：FOMAML 用 inner_adapt、
      ANIL（config.head_only=True）用 inner_adapt_anil；内循环步数/学习率来自 config；
    - predict(designs) -> (n,3)：纯 numpy 前向（Linear + 中间 tanh + 末层线性），
      与 maml._forward_torch 逐位同构，不依赖 torch。
    """

    def __init__(self, parameters: Any, config: Any, *, meta_seed: int, model_sha256: str | None = None):
        from .maml import MAMLConfig, ParameterSet

        if not isinstance(parameters, ParameterSet):
            raise S3ArmError("S3ModelScorer 需要 maml.ParameterSet")
        if not isinstance(config, MAMLConfig):
            raise S3ArmError("S3ModelScorer 需要 maml.MAMLConfig")
        if config.output_dim != S3_OUTPUT_DIM:
            raise S3ArmError(f"S3 代理输出维度必须为 {S3_OUTPUT_DIM}，实际 {config.output_dim}")
        if config.input_dim != DESIGN_DIM:
            raise S3ArmError(f"S3 代理输入维度必须为 {DESIGN_DIM}，实际 {config.input_dim}")
        self.parameters = parameters
        self.config = config
        self.meta_seed = _s3_require_int(meta_seed, "meta_seed")
        self.model_sha256 = model_sha256
        self.head_only = bool(config.head_only)

    def adapt(self, support_x: Any, support_y: Any) -> "S3ModelScorer":
        from .maml import TaskEpisode, inner_adapt, inner_adapt_anil

        features = np.asarray(support_x, dtype=np.float64)
        targets = np.asarray(support_y, dtype=np.float64)
        if features.ndim != 2 or features.shape[1] != self.config.input_dim:
            raise S3ArmError(f"support_x 必须为 (n,{self.config.input_dim})，实际 {features.shape}")
        if targets.ndim != 2 or targets.shape[1] != self.config.output_dim:
            raise S3ArmError(f"support_y 必须为 (n,{self.config.output_dim})，实际 {targets.shape}")
        if features.shape[0] != targets.shape[0]:
            raise S3ArmError("support_x/support_y 行数不一致")
        episode = TaskEpisode(
            support_features=features,
            support_targets=targets,
            query_features=features,
            query_targets=targets,
        )
        if self.head_only:
            adapted, _losses = inner_adapt_anil(self.parameters, episode, self.config)
        else:
            adapted, _losses = inner_adapt(self.parameters, episode, self.config)
        return S3ModelScorer(adapted, self.config, meta_seed=self.meta_seed, model_sha256=self.model_sha256)

    def predict(self, designs: Any) -> np.ndarray:
        matrix = _s3_round_designs(designs, "designs")
        tensors = self.parameters.tensors
        if len(tensors) % 2 != 0:
            raise S3ArmError("参数张量必须成对（weight/bias）")
        n_layers = len(tensors) // 2
        current = matrix
        for layer in range(n_layers):
            weight = np.asarray(tensors[2 * layer], dtype=np.float64)
            bias = np.asarray(tensors[2 * layer + 1], dtype=np.float64)
            current = current @ weight + bias
            if layer < n_layers - 1:
                current = np.tanh(current)
        return np.asarray(current, dtype=np.float64)


__all__ = [
    *__all__,
    "S3ArmError",
    "S3_ARM_IDS",
    "S3_BO_ARM_IDS",
    "S3_BO_RANDOM",
    "S3_BO_FOMAML_OBJ",
    "S3_BO_FOMAML_CON",
    "S3_BO_ANIL_CON",
    "S3_DE",
    "S3_BUDGETS",
    "S3_K_SHOT",
    "S3_INITIAL_DESIGN_COUNT",
    "S3_NEW_INITIAL_COUNT",
    "S3_CANDIDATE_COUNT",
    "S3_CANDIDATE_POOL_SIZE",
    "S3_DIVERSITY_MIN_NORM",
    "S3_JOINT_PENALTY",
    "S3_BO_CONFIG",
    "S3_CLONE_EXEMPT_PAIRS",
    "S3ModelScorer",
    "run_s3_arm",
    "run_s3_bo_arm",
    "run_s3_de_arm",
    "s3_arm_provenance",
    "s3_bo_config_sha256",
    "s3_bo_engine_draws",
    "s3_bo_engine_draws_sha256",
    "s3_bo_engine_seed",
    "s3_candidate_pool",
    "s3_candidate_pool_sha256",
    "s3_de_engine_seed",
    "s3_expected_budget",
    "s3_fairness_report",
    "s3_joint_score",
    "s3_normalization",
    "s3_select_diverse_designs",
    "s3_select_support_designs",
    "s3_shared_initial_designs",
    "s3_standardize_labels",
    "s3_support_seed",
    "s3_trace_first_divergence",
]
