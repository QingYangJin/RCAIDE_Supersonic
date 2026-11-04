"""P4-M6 快速适应 harness：R/P/M 三臂 × K-shot × {同分布, OOD 参数外推, 新函数族}。

职责与边界（Issue #5 D-P4-002，P4-CODE）：
- 只用解析合成任务族与 12D 设计空间的解析真值；physical_call_count 恒为 0，
  禁止任何真实 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器调用与网络访问（§1.3）。
- 三臂：M=MAML 一阶元训练、P=监督预训练后微调、R=随机初始化；同结构、同评估预算。
- K in {0,1,5,10,20}（K=0 为零样本三臂同报）；support 只从 support 池按确定性置换取，
  query 标签只在评估函数内部一次性使用（adaptation 路径不读 query 标签，§6）。
- 三层结论严格分离、禁止跨层自动推断：
  L1 训练族上的代理误差优势（M vs P / M vs R）；
  L2 BO 样本效率（M5 产物归口，本模块只引用不推断）；
  L3 OOD/新函数族泛化（必须通过 H1-H5 混杂诊断才允许称"泛化稳健"）。
- 跨族尺度不同：同时保留原始值(rmse_raw/mae_raw)与任务内标准化值(rmse_norm/mae_norm)，
  不把不同族的原始目标值直接混合比较。
- 不伪造：torch 不可用、任务族失败、确定性失败、物理守卫违规均如实落盘并给出状态。
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from . import m6_frozen

# A5M6-02：冻结门禁失败用独立异常类型；此处显式绑定便于 except 使用
M6FrozenGateError = m6_frozen.M6FrozenGateError
from . import task_family as tf
from .baseline_arms import PhysicsGuardViolation, paired_statistics
from .maml import torch_available, torch_import_error
from .offline_runner import (
    HIDDEN_SIZES,
    S_ADAPT,
    _forbidden_modules_present,
    assert_no_forbidden_modules,
    build_data_manifest,
    build_m1_artifacts,
    build_task_blocks,
    environment_payload,
    iso_utc,
    make_run_id,
    repo_git_state,
    support_subset_indices,
    utc_now,
    write_csv,
    write_json,
)

STAGE = "P4-CODE"
RUN_PREFIX = "p4-m6"
DATA_ORIGIN = "SYNTHETIC_TEST"
EVALUATOR_ID = "synthetic__analytic__12d_lifting_surfaces__v1"
PHYSICAL_CALL_COUNT = 0
DESIGN_SET = "12d_lifting_surfaces"

M6_ARMS = ("M", "P", "R")
M6_METHODS = {"M": "maml", "P": "fine_tuning", "R": "from_scratch"}
M6_KS = (0, 1, 5, 10, 20)
M6_STUDIES = ("in_dist", "ood", "new_family")
DEFAULT_NEW_FAMILIES = ("F-LIN", "F-MF")
#: A5M6-01：元训练族必须是 M5 冻结的 v2 家族；v1 F-QE 只能作历史对照，禁止默认
TRAIN_FAMILY = m6_frozen.TRAIN_FAMILY
#: A5M6-03：旧 M2 run（48,000 次合成评价）不可变门禁文件
OLD_RUN_GATE_FILE = m6_frozen.OLD_M2_RUN_GATE_FILE
#: A5M6-10：六个规范图键（缺键只能标 NOT_RUN，不得补假数据）
M6_CANONICAL_FIGURES = (
    "fig1_meta_training_loss",
    "fig2_k_shot_adaptation",
    "fig3_feasible_rate",
    "fig4_equal_budget_gap",
    "fig5_fairness_audit",
    "fig6_airframe_gate_progress",
)
EVAL_SPLITS = ("meta_test", "meta_test_ood", "negative_control")
VALID_SCALES = ("FORMAL", "SMOKE")

L1_LAYER = "surrogate_error_advantage"
L2_LAYER = "bo_sample_efficiency"
L3_LAYER = "ood_generalization"

DEGRADATION_RATIO = 1.10          # OOD/in-dist 原始 RMSE 比值超过该阈值视为退化
CONFOUND_TOLERANCE = 0.20         # H1 难度代理量相对差异超过 20% 视为疑似混杂
OOD_STRONG_SHIFT = 0.10           # H2 context 平移范数阈值（相对单位区间）
MIN_TASKS_FOR_STATS = 5           # 少于此任务数不报 p 值（如实标 INCONCLUSIVE）
BOOTSTRAP_SAMPLES = 10000
CONFIDENCE = 0.95

TRAINING_HISTORY_COLUMNS = (
    "run_id", "arm", "split", "meta_seed", "task_id", "family", "iteration", "epoch",
    "loss_support", "loss_query", "grad_norm", "lr", "seed", "wall_s", "status",
)
ADAPTATION_RESULT_COLUMNS = (
    "run_id", "study", "task_id", "split", "source_family", "train_family", "arm", "K",
    "meta_seed", "seed", "n_support", "n_query", "adapt_steps", "n_inner_losses",
    "loss_final", "loss_std", "loss_monotonic_fraction", "mae_raw", "rmse_raw",
    "mae_norm", "rmse_norm", "r2", "max_abs_err", "wall_s", "status",
)
ADAPTATION_SUMMARY_COLUMNS = (
    "run_id", "study", "source_family", "train_family", "arm", "K", "metric",
    "n_tasks", "n_runs", "n_nonnull", "null_rate", "mean", "median", "std",
    "ci_low", "ci_high", "aggregation", "status",
)
STATISTICS_COLUMNS = (
    "run_id", "study", "source_family", "arm", "reference", "K", "metric",
    "n_pairs", "median_diff", "mean_diff", "cohens_d", "rank_biserial", "ci_low", "ci_high",
    "wilcoxon_statistic", "wilcoxon_pvalue", "p_holm", "reject_holm", "status",
)
METRICS_COLUMNS = (
    "run_id", "phase", "study", "source_family", "split", "arm", "K", "task_id",
    "meta_seed", "metric", "value", "unit", "aggregation", "n", "status",
)
SOLVER_VALIDATION_COLUMNS = ("run_id", "case_id", "evaluator_id", "solver_family", "status", "note")
SOLVER_VALIDATION_ROWS = (
    {
        "case_id": "D-12D-001",
        "solver_family": "VSPAERO",
        "status": "NOT_APPLICABLE_THIS_STAGE",
        "note": "VSPAERO 验证归口 Issue #4 D-12D-004；P4-CODE 阶段不使用真实气动求解器",
    },
    {
        "case_id": "D-12D-002",
        "solver_family": "SU2",
        "status": "NOT_RUN",
        "note": "SU2 真实高频评估归口 Issue #4 D-12D-004；本阶段仅解析合成真值",
    },
    {
        "case_id": "D-12D-003",
        "solver_family": "RCAIDE_MISSION",
        "status": "NOT_RUN",
        "note": "RCAIDE Mission 真实评估归口 Issue #4 D-12D-004；P4-CODE 物理调用恒 0",
    },
)
NOT_APPROVED = (
    "真实跨任务元训练与真实低/高保真标签（需 P4-REAL-LF / P4-MULTIFIDELITY-REAL 授权）",
    "MAML 参数级等价性声明（backend=torch 自写一阶实现，equivalence_claimed=false）",
    "由 M6 代理误差直接推断 BO 样本效率（必须引用 M5 的 holdout 统计）",
)


class M6Error(ValueError):
    """M6 harness 配置/执行错误（fail-closed，不静默降级）。"""


@dataclass(frozen=True)
class M6RunnerConfig:
    """M6 运行配置：三臂 K-shot 快速适应矩阵（默认正式规模）。"""

    run_id: str
    output_root: Path
    family_seed: int = 20261102
    train_family: str = TRAIN_FAMILY
    new_families: tuple[str, ...] = DEFAULT_NEW_FAMILIES
    ks: tuple[int, ...] = M6_KS
    meta_seeds: tuple[int, ...] = (0, 1, 2)
    max_meta_steps: int = 200
    inner_steps: int = S_ADAPT
    train_tasks: int = 60
    validation_tasks: int = 20
    test_tasks: int = 20
    ood_tasks: int = 10
    negative_control_tasks: int = 10
    support_pool_size: int = 128
    query_size: int = 64
    determinism_reruns: int = 3
    physical_guard_expected: int = 0
    #: A5M6-01/02：M5 冻结 run 目录（frozen_family / preregistration / meta_task_split）
    frozen_run_dir: Path | None = None
    frozen_family_path: Path | None = None
    preregistration_path: Path | None = None
    split_manifest_path: Path | None = None
    #: A5M6-03：旧 M2 run 所在 output_root（只读快照；缺省与 output_root 相同）
    old_run_output_root: Path | None = None
    #: A5M6-09：显式预注册的 K 省略（缺 K=20 时必须给出并写入 run_config）
    k_omissions: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise M6Error("run_id 必须是非空字符串")
        if any(token in self.run_id for token in ("/", "\\")):
            raise M6Error("run_id 不得包含路径分隔符")
        object.__setattr__(self, "output_root", Path(self.output_root))
        for _path_name in (
            "frozen_run_dir",
            "frozen_family_path",
            "preregistration_path",
            "split_manifest_path",
            "old_run_output_root",
        ):
            _value = getattr(self, _path_name)
            if _value is not None:
                object.__setattr__(self, _path_name, Path(_value))
        if self.frozen_run_dir is None and self.frozen_family_path is None:
            raise M6Error(
                "M6 必须显式提供 M5 冻结输入（frozen_run_dir 或 frozen_family_path/preregistration_path/"
                "split_manifest_path）；A5M6-02：未冻结不得开 run（禁止回落到 v1 F-QE）"
            )
        if self.train_family not in tf.FAMILIES:
            raise M6Error(f"train_family 必须是 {tf.FAMILIES} 之一，实际 {self.train_family!r}")
        new_families = tuple(str(name) for name in self.new_families)
        for name in new_families:
            if name not in tf.FAMILIES:
                raise M6Error(f"new_families 含未知族 {name!r}")
        if self.train_family in new_families:
            raise M6Error("new_families 不得包含 train_family（新函数族需与训练族不同）")
        if len(set(new_families)) != len(new_families):
            raise M6Error("new_families 不得重复")
        object.__setattr__(self, "new_families", new_families)
        ks = tuple(int(value) for value in self.ks)
        if not ks or any(value < 0 for value in ks):
            raise M6Error("ks 必须非空且全部 >= 0")
        if len(set(ks)) != len(ks) or tuple(sorted(ks)) != ks:
            raise M6Error("ks 必须互异且升序（保证 K 嵌套的确定性置换）")
        if 0 not in ks:
            raise M6Error("ks 必须包含 K=0（零样本三臂同报）")
        object.__setattr__(self, "ks", ks)
        meta_seeds = tuple(int(value) for value in self.meta_seeds)
        if not meta_seeds or len(set(meta_seeds)) != len(meta_seeds):
            raise M6Error("meta_seeds 必须互异且非空")
        object.__setattr__(self, "meta_seeds", meta_seeds)
        for name in ("max_meta_steps", "inner_steps", "train_tasks", "validation_tasks", "test_tasks",
                     "ood_tasks", "negative_control_tasks", "support_pool_size", "query_size"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise M6Error(f"{name} 必须是非负整数，实际 {value!r}")
        if self.train_tasks < 1:
            raise M6Error("train_tasks 必须 >= 1（MAML 元训练需要任务）")
        if self.test_tasks < 1:
            raise M6Error("test_tasks 必须 >= 1（M6 至少评估 1 个 meta_test 任务）")
        if self.query_size < 1:
            raise M6Error("query_size 必须 >= 1")
        if self.support_pool_size < max(ks):
            raise M6Error(
                f"support_pool_size={self.support_pool_size} 不足以支持最大 K={max(ks)}（K 只能从 support 池取）"
            )
        if self.determinism_reruns < 1:
            raise M6Error("determinism_reruns 必须 >= 1")
        if int(self.physical_guard_expected) != PHYSICAL_CALL_COUNT:
            raise M6Error("P4-CODE 物理调用期望必须为 0（fail-closed）")
        omissions = tuple(int(value) for value in self.k_omissions)
        if len(set(omissions)) != len(omissions) or any(value < 0 for value in omissions):
            raise M6Error("k_omissions 必须是互异的非负 K 列表")
        for value in omissions:
            if value in ks:
                raise M6Error(f"k_omissions 不得包含实际已评估的 K={value}")
        object.__setattr__(self, "k_omissions", omissions)

    @property
    def run_dir(self) -> Path:
        return self.output_root / self.run_id

    @property
    def designs_per_task(self) -> int:
        return self.support_pool_size + self.query_size

    @property
    def study_scale(self) -> str:
        """只有满足正式规模（§4）的运行才允许用于结论。"""
        formal = (
            len(self.meta_seeds) >= 3
            and self.test_tasks >= 20
            and self.ood_tasks >= 10
            and self.negative_control_tasks >= 10
            and self.train_tasks >= 60
            and self.validation_tasks >= 20
            and self.max_meta_steps >= 200
            and all(k in self.ks for k in (0, 1, 5, 10))
            and (20 in self.ks or 20 in self.k_omissions)
            and len(self.new_families) >= 2
        )
        return "FORMAL" if formal else "SMOKE"

    @property
    def conclusions_allowed(self) -> bool:
        return self.study_scale == "FORMAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "output_root": str(self.output_root),
            "family_seed": int(self.family_seed),
            "train_family": self.train_family,
            "new_families": list(self.new_families),
            "ks": list(self.ks),
            "meta_seeds": list(self.meta_seeds),
            "max_meta_steps": int(self.max_meta_steps),
            "inner_steps": int(self.inner_steps),
            "split_counts": {
                "meta_train": int(self.train_tasks),
                "meta_validation": int(self.validation_tasks),
                "meta_test": int(self.test_tasks),
                "meta_test_ood": int(self.ood_tasks),
                "negative_control": int(self.negative_control_tasks),
            },
            "support_pool_size": int(self.support_pool_size),
            "query_size": int(self.query_size),
            "designs_per_task": int(self.designs_per_task),
            "determinism_reruns": int(self.determinism_reruns),
            "physical_guard_expected": int(self.physical_guard_expected),
            "k_omissions": list(self.k_omissions),
            "frozen_run_dir": str(self.frozen_run_dir) if self.frozen_run_dir is not None else None,
            "old_run_output_root": (
                str(self.old_run_output_root) if self.old_run_output_root is not None else None
            ),
            "study_scale": self.study_scale,
            "conclusions_allowed": self.conclusions_allowed,
        }
# ---------------------------------------------------------------------------
# 任务族构建：训练族（默认 F-QE）+ 新函数族（默认 F-LIN / F-MF）
# ---------------------------------------------------------------------------
STUDY_ORDER = ("in_dist", "ood", "new_family", "negative_control")
SUMMARY_METRICS = (
    "rmse_raw", "rmse_norm", "mae_raw", "mae_norm", "r2", "max_abs_err",
    "loss_final", "loss_std", "loss_monotonic_fraction", "wall_s",
)
PRIMARY_METRICS = ("rmse_raw", "rmse_norm")
STATISTICS_METRICS = ("rmse_raw", "rmse_norm", "mae_raw", "mae_norm")
MIN_NONNULL_FRACTION = 0.70


def _family_config(
    config: M6RunnerConfig,
    family_id: str,
    *,
    train_tasks: int,
    validation_tasks: int,
    test_tasks: int,
    ood_tasks: int,
    negative_control_tasks: int,
) -> tf.TaskFamilyConfig:
    """按 M6 配置构造任务族配置（designs_per_task 恒等于 support 池 + query）。"""
    return tf.TaskFamilyConfig(
        family_id=family_id,
        design_dim=tf.DESIGN_DIM,
        context_names=tf.CONTEXT_NAMES,
        seed=int(config.family_seed),
        train_tasks=int(train_tasks),
        validation_tasks=int(validation_tasks),
        test_tasks=int(test_tasks),
        ood_tasks=int(ood_tasks),
        negative_control_tasks=int(negative_control_tasks),
        designs_per_task=int(config.designs_per_task),
        support_pool_size=int(config.support_pool_size),
        query_size=int(config.query_size),
    )


def build_m6_family_configs(
    config: M6RunnerConfig,
    gate: m6_frozen.FrozenGate,
) -> dict[str, tf.TaskFamilyConfig]:
    """训练族用 M5 冻结的 v2 家族（A5M6-01）；新函数族只生成 meta_test（外部任务，不回训）。"""
    if config.train_family != TRAIN_FAMILY:
        raise M6Error(
            "M6 元训练族必须是冻结的 %s（A5M6-01），实际 %r；v1 F-QE 只能作历史对照"
            % (TRAIN_FAMILY, config.train_family)
        )
    if str(gate.family_id) != config.train_family:
        raise M6FrozenGateError(
            "冻结门禁 family_id=%r 与 config.train_family=%r 不一致" % (gate.family_id, config.train_family)
        )
    configs: dict[str, tf.TaskFamilyConfig] = {
        config.train_family: m6_frozen.family_config_for_m6(
            gate,
            train_tasks=config.train_tasks,
            validation_tasks=config.validation_tasks,
            test_tasks=config.test_tasks,
            ood_tasks=config.ood_tasks,
            negative_control_tasks=config.negative_control_tasks,
            support_pool_size=config.support_pool_size,
            query_size=config.query_size,
            family_seed=config.family_seed,
            full_scale=config.study_scale == "FORMAL",
        )
    }
    for family_id in config.new_families:
        configs[family_id] = _family_config(
            config,
            family_id,
            train_tasks=0,
            validation_tasks=0,
            test_tasks=config.test_tasks,
            ood_tasks=0,
            negative_control_tasks=0,
        )
    return configs


SPLIT_NAMES = ("meta_train", "meta_validation", "meta_test", "meta_test_ood", "negative_control")


def _tasks_by_split(tasks: Sequence[tf.SyntheticTask]) -> dict[str, list[tf.SyntheticTask]]:
    grouped: dict[str, list[tf.SyntheticTask]] = {split: [] for split in SPLIT_NAMES}
    for task in tasks:
        grouped.setdefault(task.split, []).append(task)
    for split in grouped:
        grouped[split] = sorted(grouped[split], key=lambda item: item.task_id)
    return grouped


def build_m6_datasets(
    config: M6RunnerConfig,
    *,
    gate: m6_frozen.FrozenGate,
    progress: Any = None,
) -> dict[str, dict[str, Any]]:
    """构造训练族与新函数族的任务集合，并断言 task_id 全局互斥（防泄漏）。"""
    configs = build_m6_family_configs(config, gate)
    datasets: dict[str, dict[str, Any]] = {}
    seen: dict[str, str] = {}
    for family_id, family_config in configs.items():
        tasks = list(tf.build_task_family(family_config))
        if not tasks:
            raise M6Error(f"任务族 {family_id} 未生成任何任务（fail-closed）")
        for task in tasks:
            if task.task_id in seen:
                raise M6Error(
                    f"task_id 跨族重复：{task.task_id}（{seen[task.task_id]} 与 {family_id}），存在泄漏风险"
                )
            seen[task.task_id] = family_id
        datasets[family_id] = {
            "family_id": family_id,
            "config": family_config,
            "fingerprint": tf.family_fingerprint(family_config),
            "tasks": tasks,
            "splits": _tasks_by_split(tasks),
        }
        if progress is not None:
            progress(
                "m6_family",
                {
                    "family_id": family_id,
                    "tasks": len(tasks),
                    "splits": {split: len(items) for split, items in datasets[family_id]["splits"].items()},
                    "fingerprint": datasets[family_id]["fingerprint"],
                },
            )
    return datasets


def training_tasks(datasets: Mapping[str, Any], config: M6RunnerConfig) -> list[tf.SyntheticTask]:
    """三臂共用的元训练任务（训练族 meta_train；不使用 validation 选模，需在报告中披露）。"""
    tasks = list(datasets[config.train_family]["splits"].get("meta_train", ()))
    if not tasks:
        raise M6Error("训练族 meta_train 为空，无法训练 M6 三臂")
    return tasks


def study_units(
    config: M6RunnerConfig,
    datasets: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """M6 评估单元：同分布 / OOD 参数外推 / 新函数族 / 负控制（单列）。"""
    units: list[dict[str, Any]] = []
    train_family = datasets[config.train_family]
    for task in train_family["splits"].get("meta_test", ()):
        units.append(
            {"study": "in_dist", "source_family": config.train_family, "split": "meta_test", "task": task}
        )
    for task in train_family["splits"].get("meta_test_ood", ()):
        units.append(
            {"study": "ood", "source_family": config.train_family, "split": "meta_test_ood", "task": task}
        )
    for family_id in config.new_families:
        for task in datasets[family_id]["splits"].get("meta_test", ()):
            units.append(
                {"study": "new_family", "source_family": family_id, "split": "meta_test", "task": task}
            )
    for task in train_family["splits"].get("negative_control", ()):
        units.append(
            {
                "study": "negative_control",
                "source_family": config.train_family,
                "split": "negative_control",
                "task": task,
            }
        )
    order = {name: index for index, name in enumerate(STUDY_ORDER)}
    units.sort(key=lambda unit: (order[unit["study"]], unit["source_family"], unit["task"].task_id))
    if not units:
        raise M6Error("M6 评估单元为空（至少需要 meta_test / OOD / 新族任务）")
    return units


# ---------------------------------------------------------------------------
# 三臂元训练（每个元训练 seed 一套 M/P/R 参数）
# ---------------------------------------------------------------------------

def _artifact_sha256(artifact: Mapping[str, Any]) -> str:
    """artifact 指纹：参数数组 + 配置（用于确定性重跑比对）。"""
    digest = hashlib.sha256()
    parameters = artifact.get("parameters")
    tensors = getattr(parameters, "tensors", None)
    if tensors is None and isinstance(parameters, Mapping):
        tensors = parameters.get("tensors")
    if tensors is None:
        raise M6Error("artifact 缺少 parameters.tensors，无法计算指纹")
    for tensor in tensors:
        array = np.ascontiguousarray(np.asarray(tensor, dtype=np.float64))
        digest.update(np.asarray(array.shape, dtype="<i8").tobytes())
        digest.update(array.tobytes())
    config = artifact.get("config")
    if isinstance(config, Mapping):
        payload = config
    else:
        to_dict = getattr(config, "to_dict", None)
        payload = to_dict() if callable(to_dict) else {}
    digest.update(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    )
    return digest.hexdigest()


def build_m6_artifacts(
    config: M6RunnerConfig,
    datasets: Mapping[str, Any],
    *,
    progress: Any = None,
) -> dict[int, dict[str, Any]]:
    """逐元训练 seed 构造 M/P/R 三臂参数（复用 M1 的 build_m1_artifacts）。"""
    if not torch_available():
        raise M6Error(f"torch 不可用，M6 三臂无法训练（P4-CODE 要求 torch）：{torch_import_error()}")
    from .offline_runner import OfflineRunnerConfig

    tasks = training_tasks(datasets, config)
    blocks = build_task_blocks(tasks)
    artifacts: dict[int, dict[str, Any]] = {}
    for meta_seed in config.meta_seeds:
        runner_config = OfflineRunnerConfig(
            run_id=f"{config.run_id}-meta{int(meta_seed)}",
            output_root=Path("."),
            seed=int(meta_seed),
            max_meta_steps=int(config.max_meta_steps),
        )
        wall_start = time.perf_counter()
        built = build_m1_artifacts(blocks, tasks, runner_config)
        wall_s = time.perf_counter() - wall_start
        training_rows = [
            dict(row, meta_seed=int(meta_seed), run_id=config.run_id) for row in built["training_rows"]
        ]
        arms = built["artifacts"]
        artifacts[int(meta_seed)] = {
            "meta_seed": int(meta_seed),
            "artifacts": arms,
            "artifacts_sha256": {
                arm: _artifact_sha256(arms[arm]) for arm in M6_ARMS
            },
            "training_rows": training_rows,
            "meta_training": dict(built["meta_training"]),
            "pretraining": dict(built["pretraining"]),
            "eval_config": dict(built["eval_config"]),
            "wall_s": float(wall_s),
            "n_train_tasks": len(tasks),
        }
        if progress is not None:
            progress(
                "m6_artifacts",
                {
                    "meta_seed": int(meta_seed),
                    "train_tasks": len(tasks),
                    "wall_s": float(wall_s),
                    "artifact_sha256": artifacts[int(meta_seed)]["artifacts_sha256"],
                },
            )
    return artifacts


# ---------------------------------------------------------------------------
# K-shot 适应矩阵（三臂 × K × 四类评估单元 × 元训练 seed）
# ---------------------------------------------------------------------------

def _evaluation_blocks(datasets: Mapping[str, Any], units: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """只为评估任务构造 support/query 特征块（解析真值，无物理调用）。"""
    blocks: dict[str, dict[str, Any]] = {}
    for family_id, dataset in datasets.items():
        tasks = list(dataset["tasks"])
        if not tasks:
            continue
        blocks.update(build_task_blocks(tasks))
    missing = [unit["task"].task_id for unit in units if unit["task"].task_id not in blocks]
    if missing:
        raise M6Error(f"评估单元缺少特征块：{missing[:3]}")
    return blocks


def _support_block(block: Mapping[str, Any], indices: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "features": np.asarray(block["support"]["features"], dtype=np.float64)[indices],
        "targets": np.asarray(block["support"]["targets"], dtype=np.float64)[indices, :1],
    }


def _query_block(block: Mapping[str, Any]) -> dict[str, np.ndarray]:
    return {
        "features": np.asarray(block["query"]["features"], dtype=np.float64),
        "targets": np.asarray(block["query"]["targets"], dtype=np.float64)[:, :1],
    }


def _loss_stability(losses: Sequence[float]) -> dict[str, float | None]:
    """内循环损失稳定性指标（梯度稳定性的可复核代理，不宣称物理意义）。"""
    values = np.asarray([float(value) for value in losses], dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {"loss_final": None, "loss_std": None, "loss_monotonic_fraction": None}
    diffs = np.diff(values)
    monotonic = float(np.mean(diffs <= 0.0)) if diffs.size else 1.0
    return {
        "loss_final": float(values[-1]),
        "loss_std": float(np.std(values)),
        "loss_monotonic_fraction": monotonic,
    }


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _adaptation_row(
    config: M6RunnerConfig,
    *,
    unit: Mapping[str, Any],
    arm: str,
    k_shot: int,
    meta_seed: int,
    result: Any,
    wall_s: float,
) -> dict[str, Any]:
    metrics = dict(result.metrics)
    stability = _loss_stability(result.losses)
    rmse = _finite_or_none(metrics.get("rmse"))
    status = "VALID" if rmse is not None else "NONFINITE"
    return {
        "run_id": config.run_id,
        "study": unit["study"],
        "task_id": unit["task"].task_id,
        "split": unit["split"],
        "source_family": unit["source_family"],
        "train_family": config.train_family,
        "arm": arm,
        "K": int(k_shot),
        "meta_seed": int(meta_seed),
        "seed": int(meta_seed),
        "n_support": int(k_shot),
        "n_query": int(np.asarray(result.targets).size),
        "adapt_steps": int(result.inner_steps),
        "n_inner_losses": int(len(result.losses)),
        "loss_final": stability["loss_final"],
        "loss_std": stability["loss_std"],
        "loss_monotonic_fraction": stability["loss_monotonic_fraction"],
        "mae_raw": _finite_or_none(metrics.get("mae")),
        "rmse_raw": rmse,
        "mae_norm": _finite_or_none(metrics.get("mae_norm")),
        "rmse_norm": _finite_or_none(metrics.get("rmse_norm")),
        "r2": _finite_or_none(metrics.get("r2")),
        "max_abs_err": _finite_or_none(metrics.get("max_abs_err")),
        "wall_s": float(wall_s),
        "status": status,
    }


def run_m6_adaptation_matrix(
    config: M6RunnerConfig,
    datasets: Mapping[str, Any],
    artifacts_by_meta: Mapping[int, Mapping[str, Any]],
    *,
    progress: Any = None,
) -> dict[str, Any]:
    """执行三臂 × K × 评估单元矩阵；范式目标只用于评估（§6 泄漏断言）。"""
    from .adaptation import adapt_and_predict

    units = study_units(config, datasets)
    blocks = _evaluation_blocks(datasets, units)
    rows: list[dict[str, Any]] = []
    training_rows: list[dict[str, Any]] = []
    ordered_meta = [int(seed) for seed in config.meta_seeds]
    for meta_seed in ordered_meta:
        if meta_seed not in artifacts_by_meta:
            raise M6Error(f"缺少元训练 seed={meta_seed} 的三臂参数（fail-closed）")
        training_rows.extend(artifacts_by_meta[meta_seed].get("training_rows", ()))
    wall_start = time.perf_counter()
    total = len(units) * len(config.ks) * len(ordered_meta) * len(M6_ARMS)
    for unit in units:
        task = unit["task"]
        block = blocks[task.task_id]
        query = _query_block(block)
        for k_shot in config.ks:
            for meta_seed in ordered_meta:
                indices = support_subset_indices(
                    task.task_id, int(meta_seed), int(config.support_pool_size), int(k_shot)
                )
                support = _support_block(block, indices)
                artifacts = artifacts_by_meta[meta_seed]["artifacts"]
                for arm in M6_ARMS:
                    arm_wall = time.perf_counter()
                    result = adapt_and_predict(
                        artifacts[arm],
                        support,
                        query,
                        M6_METHODS[arm],
                        int(k_shot),
                        {"fine_tuning_steps": int(config.inner_steps)},
                    )
                    arm_wall = time.perf_counter() - arm_wall
                    physical = int(getattr(result, "physical_call_count", 0) or 0)
                    if physical != PHYSICAL_CALL_COUNT:
                        raise PhysicsGuardViolation(
                            f"适应过程报告 physical_call_count={physical} != 0（立即中止 M6）",
                            physical_call_count=physical,
                        )
                    rows.append(
                        _adaptation_row(
                            config,
                            unit=unit,
                            arm=arm,
                            k_shot=int(k_shot),
                            meta_seed=meta_seed,
                            result=result,
                            wall_s=arm_wall,
                        )
                    )
                    if progress is not None and len(rows) % 200 == 0:
                        progress(
                            "m6_adaptation",
                            {
                                "rows": len(rows),
                                "total": total,
                                "elapsed_s": round(time.perf_counter() - wall_start, 2),
                                "study": unit["study"],
                                "arm": arm,
                                "K": int(k_shot),
                            },
                        )
    if not rows:
        raise M6Error("M6 适应矩阵为空（fail-closed）")
    statuses = {row["status"] for row in rows}
    if "NONFINITE" in statuses:
        status = "VALID_WITH_NONFINITE"
    else:
        status = "VALID"
    return {
        "rows": rows,
        "training_rows": training_rows,
        "units": units,
        "n_runs": len(rows),
        "total_planned_runs": int(total),
        "wall_s": float(time.perf_counter() - wall_start),
        "status": status,
        "physical_call_count": 0,
        "artifact_sha256": {
            int(seed): dict(artifacts_by_meta[seed]["artifacts_sha256"]) for seed in ordered_meta
        },
    }


# ---------------------------------------------------------------------------
# 聚合与配对统计（任务层级，避免同一任务上的伪重复）
# ---------------------------------------------------------------------------

def _bootstrap_ci(
    values: np.ndarray,
    *,
    seed: int,
    samples: int = BOOTSTRAP_SAMPLES,
    confidence: float = CONFIDENCE,
) -> tuple[float | None, float | None]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return None, None
    rng = np.random.default_rng(int(seed))
    indices = rng.integers(0, values.size, size=(int(samples), values.size))
    means = values[indices].mean(axis=1)
    alpha = (1.0 - float(confidence)) / 2.0
    low = float(np.quantile(means, alpha))
    high = float(np.quantile(means, 1.0 - alpha))
    return low, high


def _stable_int(*parts: Any) -> int:
    token = "|".join(str(part) for part in parts)
    return int(hashlib.sha1(token.encode("utf-8")).hexdigest()[:8], 16)


def _task_mean_values(
    rows: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    arm: str,
    study: str,
    source_family: str,
    k_shot: int,
) -> dict[str, float]:
    """先按优化 seed 在任务内取均值，再返回 {task_id: 任务层级均值}。"""
    grouped: dict[str, list[float]] = {}
    for row in rows:
        if row["arm"] != arm or row["study"] != study or row["source_family"] != source_family:
            continue
        if int(row["K"]) != int(k_shot):
            continue
        value = row.get(metric)
        if value is None:
            continue
        number = _finite_or_none(value)
        if number is None:
            continue
        grouped.setdefault(row["task_id"], []).append(number)
    result: dict[str, float] = {}
    for task_id, values in grouped.items():
        array = np.asarray(values, dtype=np.float64)
        if array.size == 0:
            continue
        result[task_id] = float(array.mean())
    return result


def adaptation_summary_rows(
    config: M6RunnerConfig,
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """按 (study, 来源族, 臂, K) 聚合；非 null 比例不足标 INCONCLUSIVE（不补假值）。"""
    groups: dict[tuple[str, str, str, int], list[Mapping[str, Any]]] = {}
    for row in rows:
        key = (row["study"], row["source_family"], row["arm"], int(row["K"]))
        groups.setdefault(key, []).append(row)
    summary_rows: list[dict[str, Any]] = []
    for key in sorted(groups, key=lambda item: (STUDY_ORDER.index(item[0]), item[1], M6_ARMS.index(item[2]), item[3])):
        study, source_family, arm, k_shot = key
        group_rows = groups[key]
        n_runs = len(group_rows)
        for metric in SUMMARY_METRICS:
            values = [
                number
                for number in (_finite_or_none(row.get(metric)) for row in group_rows)
                if number is not None
            ]
            n_null = n_runs - len(values)
            null_rate = float(n_null) / float(n_runs) if n_runs else 1.0
            if not values:
                summary_rows.append(
                    {
                        "run_id": config.run_id,
                        "study": study,
                        "source_family": source_family,
                        "train_family": config.train_family,
                        "arm": arm,
                        "K": k_shot,
                        "metric": metric,
                        "n_tasks": len({row["task_id"] for row in group_rows}),
                        "n_runs": n_runs,
                        "n_nonnull": 0,
                        "null_rate": null_rate,
                        "mean": None,
                        "median": None,
                        "std": None,
                        "ci_low": None,
                        "ci_high": None,
                        "aggregation": "group_mean",
                        "status": "MISSING",
                    }
                )
                continue
            array = np.asarray(values, dtype=np.float64)
            low, high = _bootstrap_ci(
                array, seed=_stable_int(config.run_id, study, source_family, arm, k_shot, metric)
            )
            summary_rows.append(
                {
                    "run_id": config.run_id,
                    "study": study,
                    "source_family": source_family,
                    "train_family": config.train_family,
                    "arm": arm,
                    "K": k_shot,
                    "metric": metric,
                    "n_tasks": len({row["task_id"] for row in group_rows}),
                    "n_runs": n_runs,
                    "n_nonnull": len(values),
                    "null_rate": null_rate,
                    "mean": float(array.mean()),
                    "median": float(np.median(array)),
                    "std": float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
                    "ci_low": low,
                    "ci_high": high,
                    "aggregation": "group_mean",
                    "status": "VALID" if null_rate <= (1.0 - MIN_NONNULL_FRACTION) else "INCONCLUSIVE",
                }
            )
    return summary_rows


def holm_bonferroni(p_values: Sequence[float | None], *, alpha: float = 0.05) -> list[tuple[float | None, bool | None]]:
    """Holm-Bonferroni 校正（返回 (校正 p, 是否拒绝)）；None 视为不可检验。"""
    indexed = [(index, float(value)) for index, value in enumerate(p_values) if value is not None]
    if not indexed:
        return [(None, None) for _ in p_values]
    indexed.sort(key=lambda item: item[1])
    m = len(indexed)
    adjusted: dict[int, float] = {}
    running = 0.0
    for rank, (index, value) in enumerate(indexed, start=1):
        candidate = min(1.0, (m - rank + 1) * value)
        running = max(running, candidate)
        adjusted[index] = running
    result: list[tuple[float | None, bool | None]] = []
    for index in range(len(p_values)):
        if index in adjusted:
            result.append((adjusted[index], adjusted[index] <= alpha))
        else:
            result.append((None, None))
    return result


def paired_comparison_rows(
    config: M6RunnerConfig,
    rows: Sequence[Mapping[str, Any]],
    *,
    metrics: Sequence[str] = STATISTICS_METRICS,
    comparisons: Sequence[tuple[str, str]] = (("M", "P"), ("M", "R"), ("P", "R")),
) -> list[dict[str, Any]]:
    """任务层级配对差：先 (task, meta_seed) 配对，再按任务取均值，最后跨任务统计。"""
    studies = [study for study in STUDY_ORDER if any(row["study"] == study for row in rows)]
    families = sorted({row["source_family"] for row in rows})
    ks = sorted({int(row["K"]) for row in rows})
    stats_rows: list[dict[str, Any]] = []
    for study in studies:
        study_families = [family for family in families if any(row["study"] == study and row["source_family"] == family for row in rows)]
        for source_family in study_families:
            for k_shot in ks:
                for metric in metrics:
                    block_rows: dict[tuple[str, str], dict[str, float]] = {}
                    for row in rows:
                        if row["study"] != study or row["source_family"] != source_family:
                            continue
                        if int(row["K"]) != k_shot:
                            continue
                        value = _finite_or_none(row.get(metric))
                        if value is None:
                            continue
                        block_rows.setdefault((row["task_id"], str(row["meta_seed"])), {})[row["arm"]] = value
                    for arm, reference in comparisons:
                        per_task: dict[str, list[float]] = {}
                        for (task_id, _meta), values in block_rows.items():
                            if arm in values and reference in values:
                                per_task.setdefault(task_id, []).append(values[arm] - values[reference])
                        diffs = np.asarray(
                            [float(np.mean(values)) for values in per_task.values()], dtype=np.float64
                        )
                        stats_row: dict[str, Any] = {
                            "run_id": config.run_id,
                            "study": study,
                            "source_family": source_family,
                            "arm": arm,
                            "reference": reference,
                            "K": k_shot,
                            "metric": metric,
                            "n_pairs": int(diffs.size),
                            "median_diff": float(np.median(diffs)) if diffs.size else None,
                            "mean_diff": float(diffs.mean()) if diffs.size else None,
                            "cohens_d": None,
                            "rank_biserial": None,
                            "ci_low": None,
                            "ci_high": None,
                            "wilcoxon_statistic": None,
                            "wilcoxon_pvalue": None,
                            "p_holm": None,
                            "reject_holm": None,
                            "status": "INCONCLUSIVE",
                        }
                        if diffs.size >= MIN_TASKS_FOR_STATS:
                            statistics = paired_statistics(
                                diffs,
                                seed=_stable_int(config.run_id, study, source_family, k_shot, metric, arm),
                            )
                            stats_row.update(
                                {
                                    "median_diff": statistics.get("median_diff"),
                                    "mean_diff": statistics.get("mean_diff"),
                                    "ci_low": statistics.get("ci_low"),
                                    "ci_high": statistics.get("ci_high"),
                                    "wilcoxon_statistic": statistics.get("wilcoxon_statistic"),
                                    "wilcoxon_pvalue": statistics.get("wilcoxon_pvalue"),
                                }
                            )
                            stats_row.update(_effect_sizes(diffs))
                            if statistics.get("wilcoxon_pvalue") is not None:
                                stats_row["status"] = "VALID"
                            else:
                                stats_row["status"] = "NO_VARIATION"
                        elif diffs.size > 0:
                            stats_row["median_diff"] = float(np.median(diffs))
                            stats_row["mean_diff"] = float(diffs.mean())
                            stats_row["status"] = "INSUFFICIENT_TASKS"
                        stats_rows.append(stats_row)
    # Holm-Bonferroni：范围 = 每个 (study, 来源族, K, 指标) 内的 3 个预注册比较（M-P / M-R / P-R）
    family_key = lambda row: (row["study"], row["source_family"], row["K"], row["metric"])
    grouped: dict[tuple, list[int]] = {}
    for index, row in enumerate(stats_rows):
        grouped.setdefault(family_key(row), []).append(index)
    for indices in grouped.values():
        adjusted = holm_bonferroni([stats_rows[index].get("wilcoxon_pvalue") for index in indices])
        for index, (p_holm, reject) in zip(indices, adjusted):
            stats_rows[index]["p_holm"] = p_holm
            stats_rows[index]["reject_holm"] = reject
    return stats_rows


def metrics_rows_from_adaptation(
    config: M6RunnerConfig,
    rows: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """metrics.csv 行：每任务原始值 + 每组聚合量（长表，单位显式）。"""
    metric_units = {
        "rmse_raw": "synthetic_objective",
        "mae_raw": "synthetic_objective",
        "rmse_norm": "1",
        "mae_norm": "1",
        "r2": "1",
        "max_abs_err": "synthetic_objective",
        "loss_final": "synthetic_objective",
        "loss_std": "synthetic_objective",
        "loss_monotonic_fraction": "1",
        "wall_s": "s",
    }
    metrics_rows: list[dict[str, Any]] = []
    for row in rows:
        for metric in PRIMARY_METRICS:
            metrics_rows.append(
                {
                    "run_id": config.run_id,
                    "phase": "adaptation",
                    "study": row["study"],
                    "source_family": row["source_family"],
                    "split": row["split"],
                    "arm": row["arm"],
                    "K": row["K"],
                    "task_id": row["task_id"],
                    "meta_seed": row["meta_seed"],
                    "metric": metric,
                    "value": row.get(metric),
                    "unit": metric_units[metric],
                    "aggregation": "per_task",
                    "n": 1,
                    "status": row["status"],
                }
            )
    for row in summary_rows:
        if row["metric"] not in metric_units:
            continue
        metrics_rows.append(
            {
                "run_id": config.run_id,
                "phase": "adaptation",
                "study": row["study"],
                "source_family": row["source_family"],
                "split": "",
                "arm": row["arm"],
                "K": row["K"],
                "task_id": "",
                "meta_seed": "",
                "metric": row["metric"],
                "value": row["mean"],
                "unit": metric_units[row["metric"]],
                "aggregation": "group_mean",
                "n": row["n_nonnull"],
                "status": row["status"],
            }
        )
    return metrics_rows
# ---------------------------------------------------------------------------
# 负控制：label-shuffle 伪任务上 M 相对 R 的优势必须回落
# ---------------------------------------------------------------------------
def _advantage_rows(
    stats_rows: Sequence[Mapping[str, Any]],
    *,
    study: str,
    source_family: str,
    k_shot: int,
    metric: str = "rmse_norm",
    arm: str = "M",
    reference: str = "R",
) -> dict[str, Any] | None:
    for row in stats_rows:
        if (
            row["study"] == study
            and row["source_family"] == source_family
            and int(row["K"]) == int(k_shot)
            and row["metric"] == metric
            and row["arm"] == arm
            and row["reference"] == reference
        ):
            return dict(row)
    return None


def negative_control_check(
    config: M6RunnerConfig,
    stats_rows: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """负控制协议：label-shuffle 后 MAML 优势应回落（否则查泄漏并重跑，§4.3/§12-13）。"""
    checks: list[dict[str, Any]] = []
    indist = _advantage_rows(stats_rows, study="in_dist", source_family=config.train_family, k_shot=5)
    control = _advantage_rows(
        stats_rows, study="negative_control", source_family=config.train_family, k_shot=5
    )
    indist_advantage = None
    control_advantage = None
    if indist is not None and indist.get("median_diff") is not None:
        indist_advantage = -float(indist["median_diff"])  # diff = M - R，取反后正值表示 M 更好
    if control is not None and control.get("median_diff") is not None:
        control_advantage = -float(control["median_diff"])
    # 小样本保护：配对任务数不足或配对行本身 INSUFFICIENT_TASKS/NO_VARIATION 时
    # 不得把抽样噪声判成泄漏（正式规模 meta_test=20、negative_control=10 不受影响）。
    paired_n = min(
        int(indist.get("n_pairs") or 0) if indist is not None else 0,
        int(control.get("n_pairs") or 0) if control is not None else 0,
    )
    rows_judgeable = (
        indist is not None
        and control is not None
        and indist.get("status") == "VALID"
        and control.get("status") == "VALID"
        and paired_n >= MIN_TASKS_FOR_STATS
    )
    shrink_fraction = None
    if rows_judgeable and indist_advantage is not None and indist_advantage > 0.0 and control_advantage is not None:
        shrink_fraction = 1.0 - (control_advantage / indist_advantage)
        passed = control_advantage <= 0.5 * indist_advantage
        status = "PASS" if passed else "FAIL"
    else:
        status = "INCONCLUSIVE"
    checks.append(
        {
            "id": "NC1",
            "name": "label-shuffle 后 MAML 优势回落",
            "status": status,
            "evidence": {
                "in_dist_advantage_rmse_norm": indist_advantage,
                "negative_control_advantage_rmse_norm": control_advantage,
                "shrink_fraction": shrink_fraction,
                "paired_tasks": paired_n,
                "min_paired_tasks": MIN_TASKS_FOR_STATS,
                "in_dist_status": None if indist is None else indist.get("status"),
                "negative_control_status": None if control is None else control.get("status"),
                "rule": "negative_control 优势 <= 0.5 * in_dist 优势 视为回落",
                "small_sample_rule": "配对任务数 < MIN_TASKS_FOR_STATS 或配对行非 VALID 时标 INCONCLUSIVE，不判泄漏",
            },
            "action": "FAIL 时必须排查泄漏（support/query 污染、query 标签进入适应路径）并重跑",
        }
    )
    # K=0：随机臂应最差（零样本时 M/P 应优于 R）
    k0_values: dict[str, float | None] = {}
    for arm in M6_ARMS:
        for row in summary_rows:
            if (
                row["study"] == "in_dist"
                and row["source_family"] == config.train_family
                and row["arm"] == arm
                and int(row["K"]) == 0
                and row["metric"] == "rmse_norm"
            ):
                k0_values[arm] = row["mean"]
    if all(k0_values.get(arm) is not None for arm in M6_ARMS):
        random_worst = k0_values["R"] >= max(k0_values["M"], k0_values["P"])
        checks.append(
            {
                "id": "NC2",
                "name": "K=0 随机臂最差",
                "status": "PASS" if random_worst else "FAIL",
                "evidence": {f"k0_rmse_norm_{arm}": k0_values[arm] for arm in M6_ARMS},
                "action": "FAIL 说明初始化/训练路径异常或存在信息泄漏，需排查后重跑",
            }
        )
    else:
        checks.append(
            {
                "id": "NC2",
                "name": "K=0 随机臂最差",
                "status": "INCONCLUSIVE",
                "evidence": {"k0_rmse_norm": k0_values},
                "action": "缺少 K=0 或非有限均值时如实标 INCONCLUSIVE",
            }
        )
    statuses = [check["status"] for check in checks]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif any(value == "INCONCLUSIVE" for value in statuses):
        overall = "INCONCLUSIVE"
    else:
        overall = "PASS"
    return {
        "status": overall,
        "checks": checks,
        "physical_call_count": 0,
        "note": "负控制单列，禁止进入主终点或用于调参；FAIL 时不得据 M6 结果下结论",
    }


# ---------------------------------------------------------------------------
# OOD 诊断 H1-H5：只有排除难度混杂/泄漏/尺度差异后才允许讨论泛化
# ---------------------------------------------------------------------------
def _task_difficulty(task: tf.SyntheticTask, block: Mapping[str, Any]) -> dict[str, float]:
    params = task.params
    context = np.asarray([float(task.context[name]) for name in tf.CONTEXT_NAMES], dtype=np.float64)
    reference = task.reference()
    return {
        "query_objective_std": float(np.std(np.asarray(block["query"]["objective"], dtype=np.float64))),
        "support_objective_std": float(np.std(np.asarray(block["support"]["objective"], dtype=np.float64))),
        "mean_curvature": float(np.mean(np.asarray(params["a"], dtype=np.float64))),
        "radius": float(params["r"]),
        "context_shift_norm": float(np.linalg.norm(context - 1.0)),
        "query_feasible_fraction": float(np.mean(np.asarray(block["query"]["feasibility"], dtype=bool))),
        "reference_objective": float(reference["objective_star"]),
    }


def _relative_difference(left: float, right: float) -> float:
    scale = max(abs(left), abs(right), 1e-12)
    return abs(left - right) / scale


def _mean_by_task(values: Mapping[str, dict[str, float]], key: str) -> float | None:
    numbers = [float(item[key]) for item in values.values() if key in item]
    if not numbers:
        return None
    return float(np.mean(np.asarray(numbers, dtype=np.float64)))


def ood_diagnostics(
    config: M6RunnerConfig,
    datasets: Mapping[str, Any],
    *,
    adapt_rows: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """H1-H5 混杂诊断：每一项给出证据、状态与对 L3 结论的影响。"""
    train_family = datasets[config.train_family]
    units = study_units(config, datasets)
    blocks = _evaluation_blocks(datasets, units)
    in_dist_tasks = list(train_family["splits"].get("meta_test", ()))
    ood_tasks = list(train_family["splits"].get("meta_test_ood", ()))
    if not in_dist_tasks or not ood_tasks:
        return {
            "status": "INSUFFICIENT_SPLITS",
            "checks": [],
            "conclusion_allowed": False,
            "note": "缺少 meta_test 或 meta_test_ood，无法进行 H1-H5 诊断",
        }
    in_dist = {task.task_id: _task_difficulty(task, blocks[task.task_id]) for task in in_dist_tasks}
    ood = {task.task_id: _task_difficulty(task, blocks[task.task_id]) for task in ood_tasks}
    checks: list[dict[str, Any]] = []

    # H1 难度混杂：OOD 与同分布的难度代理量显著不同则无法归因于泛化
    difficulty_keys = ("query_objective_std", "support_objective_std", "mean_curvature", "radius")
    difficulty_evidence: dict[str, Any] = {}
    confounded = False
    for key in difficulty_keys:
        left = _mean_by_task(in_dist, key)
        right = _mean_by_task(ood, key)
        if left is None or right is None:
            continue
        relative = _relative_difference(left, right)
        difficulty_evidence[key] = {
            "in_dist_mean": left,
            "ood_mean": right,
            "relative_difference": relative,
        }
        if relative > CONFOUND_TOLERANCE:
            confounded = True
    checks.append(
        {
            "id": "H1",
            "name": "难度混杂（OOD 是否显著更难/更易）",
            "status": "CONFOUND_SUSPECTED" if confounded else "NO_CONFOUND_DETECTED",
            "evidence": difficulty_evidence,
            "tolerance": CONFOUND_TOLERANCE,
            "implication": "CONFOUND_SUSPECTED 时不得把 OOD 变化归因于泛化能力",
        }
    )

    # H2 context 泄漏/错位：OOD context 必须真的平移，且特征列与任务 context 一致
    ood_contexts = {
        tuple(round(float(task.context[name]), 12) for name in tf.CONTEXT_NAMES) for task in ood_tasks
    }
    indist_contexts = {
        tuple(round(float(task.context[name]), 12) for name in tf.CONTEXT_NAMES) for task in in_dist_tasks
    }
    encoding_errors: list[str] = []
    for task in list(in_dist_tasks) + list(ood_tasks):
        block = blocks[task.task_id]
        expected = np.asarray([float(task.context[name]) for name in tf.CONTEXT_NAMES], dtype=np.float64)
        for split in ("support", "query"):
            features = np.asarray(block[split]["features"], dtype=np.float64)
            if features.shape[1] != tf.DESIGN_DIM + len(tf.CONTEXT_NAMES):
                encoding_errors.append(f"{task.task_id}.{split} 特征维度异常")
                continue
            context_columns = features[:, tf.DESIGN_DIM :]
            if not np.allclose(context_columns, expected[None, :], rtol=0.0, atol=1e-12):
                encoding_errors.append(f"{task.task_id}.{split} context 列与任务 context 不一致")
    shift_by_task = [_task_difficulty(task, blocks[task.task_id])["context_shift_norm"] for task in ood_tasks]
    mean_shift = float(np.mean(np.asarray(shift_by_task, dtype=np.float64)))
    overlap = ood_contexts.intersection(indist_contexts)
    h2_ok = not encoding_errors and mean_shift >= OOD_STRONG_SHIFT and not overlap
    checks.append(
        {
            "id": "H2",
            "name": "context 泄漏/错位",
            "status": "PASS" if h2_ok else "FAIL",
            "evidence": {
                "ood_mean_context_shift_norm": mean_shift,
                "threshold": OOD_STRONG_SHIFT,
                "context_sets_overlap": len(overlap),
                "encoding_errors": encoding_errors[:5],
                "n_encoding_errors": len(encoding_errors),
            },
            "implication": "FAIL 时 OOD 结果作废并排查特征编码",
        }
    )

    # H3 任务生成完整性：task_id 可复算、参考解证书有效、设计块合法
    generation_errors: list[str] = []
    for task in list(in_dist_tasks) + list(ood_tasks):
        expected_id = hashlib.sha1(
            f"{task.family}|{tf._canonical_json(task.params)}|{task.seed}".encode("utf-8")
        ).hexdigest()[:12]
        if expected_id != task.task_id:
            generation_errors.append(f"{task.task_id} task_id 与 params/seed 不一致")
        residual = float(task.reference().get("assertion_residual", float("nan")))
        if not math.isfinite(residual) or residual > tf.REFERENCE_ABS_TOL:
            generation_errors.append(f"{task.task_id} 参考解断言残差 {residual} 超限")
        block = blocks[task.task_id]
        for split in ("support", "query"):
            designs = np.asarray(block[split]["designs"], dtype=np.float64)
            if not np.all(np.isfinite(designs)) or np.any(designs < 0.0) or np.any(designs > 1.0):
                generation_errors.append(f"{task.task_id}.{split} 设计越界或非有限")
    checks.append(
        {
            "id": "H3",
            "name": "任务生成完整性",
            "status": "PASS" if not generation_errors else "FAIL",
            "evidence": {"n_checked": len(in_dist_tasks) + len(ood_tasks), "errors": generation_errors[:5]},
            "implication": "FAIL 时任务不可信，OOD 结论作废",
        }
    )

    # H4 抽样：support 池取点合法、K 嵌套、support 与 query 不相交
    sampling_errors: list[str] = []
    for task in list(in_dist_tasks) + list(ood_tasks):
        block = blocks[task.task_id]
        support_designs = np.asarray(block["support"]["designs"], dtype=np.float64)
        query_designs = np.asarray(block["query"]["designs"], dtype=np.float64)
        if support_designs.shape[0] != config.support_pool_size:
            sampling_errors.append(f"{task.task_id} support 池大小异常")
        if query_designs.shape[0] != config.query_size:
            sampling_errors.append(f"{task.task_id} query 大小异常")
        if support_designs.shape[0] and query_designs.shape[0]:
            distances = np.abs(
                support_designs[:, None, :] - query_designs[None, :, :]
            ).max(axis=2)
            if float(np.min(distances)) <= 1e-12:
                sampling_errors.append(f"{task.task_id} support 与 query 设计重叠（泄漏）")
        previous: np.ndarray | None = None
        for k_shot in config.ks:
            indices = support_subset_indices(task.task_id, 0, config.support_pool_size, int(k_shot))
            if int(indices.size) != int(k_shot):
                sampling_errors.append(f"{task.task_id} K={k_shot} 取点数异常")
            if len(set(int(value) for value in indices)) != int(k_shot):
                sampling_errors.append(f"{task.task_id} K={k_shot} 取点重复")
            if previous is not None and int(k_shot) > 0 and not set(previous).issubset(set(int(v) for v in indices)):
                sampling_errors.append(f"{task.task_id} K={k_shot} 未嵌套前一个 K")
            previous = np.asarray([int(value) for value in indices], dtype=np.int64)
    checks.append(
        {
            "id": "H4",
            "name": "抽样与泄漏",
            "status": "PASS" if not sampling_errors else "FAIL",
            "evidence": {"errors": sampling_errors[:5], "n_errors": len(sampling_errors)},
            "implication": "FAIL 时适应矩阵作废（support/query 泄漏或 K 嵌套破坏）",
        }
    )

    # H5 评估尺度：原始值与标准化值并列，判断 OOD 变化是否只是尺度差异
    raw_summary = _summary_value(summary_rows, study="in_dist", family=config.train_family, arm="M", k_shot=5, metric="rmse_raw")
    raw_ood = _summary_value(summary_rows, study="ood", family=config.train_family, arm="M", k_shot=5, metric="rmse_raw")
    norm_summary = _summary_value(summary_rows, study="in_dist", family=config.train_family, arm="M", k_shot=5, metric="rmse_norm")
    norm_ood = _summary_value(summary_rows, study="ood", family=config.train_family, arm="M", k_shot=5, metric="rmse_norm")
    raw_ratio = raw_ood / raw_summary if raw_summary and raw_summary > 0 and raw_ood is not None else None
    norm_ratio = norm_ood / norm_summary if norm_summary and norm_summary > 0 and norm_ood is not None else None
    scale_gap = None
    if raw_ratio is not None and norm_ratio is not None:
        scale_gap = _relative_difference(raw_ratio, norm_ratio)
    checks.append(
        {
            "id": "H5",
            "name": "评估尺度差异",
            "status": "PASS" if raw_ratio is not None and norm_ratio is not None else "INCONCLUSIVE",
            "evidence": {
                "rmse_raw_ratio_ood_over_in_dist": raw_ratio,
                "rmse_norm_ratio_ood_over_in_dist": norm_ratio,
                "raw_vs_norm_ratio_gap": scale_gap,
                "note": "原始值与任务内标准化值同时保留；不同族原始目标值不可直接混合比较",
            },
            "implication": "尺度差异大时只能报告标准化值或分族报告",
        }
    )

    statuses = [check["status"] for check in checks]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "CONFOUND_SUSPECTED" in statuses or "INCONCLUSIVE" in statuses:
        overall = "CONFOUNDED"
    else:
        overall = "PASS"
    return {
        "status": overall,
        "checks": checks,
        "conclusion_allowed": overall == "PASS",
        "tolerances": {"confound_relative_difference": CONFOUND_TOLERANCE, "ood_context_shift": OOD_STRONG_SHIFT},
        "note": "只有 H1-H5 全部通过（无难度混杂）时才允许讨论「泛化稳健」；OOD 不退化本身不构成泛化成功",
        "difficulty_matching": {"status": "NOT_COMPUTED", "note": "由 attach_ood_difficulty_matching 注入"},
    }


def _summary_value(
    summary_rows: Sequence[Mapping[str, Any]],
    *,
    study: str,
    family: str,
    arm: str,
    k_shot: int,
    metric: str,
) -> float | None:
    for row in summary_rows:
        if (
            row["study"] == study
            and row["source_family"] == family
            and row["arm"] == arm
            and int(row["K"]) == int(k_shot)
            and row["metric"] == metric
        ):
            return _finite_or_none(row.get("mean"))
    return None


# ---------------------------------------------------------------------------
# 三层结论：代理误差优势 / BO 样本效率 / OOD 泛化，禁止跨层推断
# ---------------------------------------------------------------------------
def three_layer_conclusions(
    config: M6RunnerConfig,
    *,
    stats_rows: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
    ood_diagnostic: Mapping[str, Any],
    negative_control: Mapping[str, Any],
    m5_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """三层独立结论：L1 训练族误差优势、L2 BO 样本效率（引用 M5）、L3 OOD 泛化。"""
    l1_checks: list[dict[str, Any]] = []
    for arm, reference in (("M", "P"), ("M", "R")):
        row = None
        for candidate in stats_rows:
            if (
                candidate["study"] == "in_dist"
                and candidate["source_family"] == config.train_family
                and int(candidate["K"]) == 5
                and candidate["metric"] == "rmse_norm"
                and candidate["arm"] == arm
                and candidate["reference"] == reference
            ):
                row = dict(candidate)
                break
        if row is None or row.get("status") == "INSUFFICIENT_TASKS":
            l1_checks.append(
                {"comparison": f"{arm} vs {reference}", "status": "INCONCLUSIVE", "reason": "任务数不足或缺少比较行"}
            )
            continue
        significant = bool(row.get("reject_holm")) and row.get("median_diff") is not None and float(row["median_diff"]) < 0.0
        l1_checks.append(
            {
                "comparison": f"{arm} vs {reference}",
                "status": "SIGNIFICANT_ADVANTAGE" if significant else "NO_SIGNIFICANT_ADVANTAGE",
                "K": 5,
                "metric": "rmse_norm",
                "n_pairs": row.get("n_pairs"),
                "median_diff": row.get("median_diff"),
                "ci_low": row.get("ci_low"),
                "ci_high": row.get("ci_high"),
                "p_holm": row.get("p_holm"),
            }
        )
    significant_any = any(check["status"] == "SIGNIFICANT_ADVANTAGE" for check in l1_checks)
    l1 = {
        "layer": L1_LAYER,
        "definition": "训练族 meta_test 上 K=5 的 query RMSE（任务内标准化）优势",
        "checks": l1_checks,
        "status": "ADVANTAGE_OBSERVED" if significant_any else "NO_SIGNIFICANT_ADVANTAGE",
        "scope": "仅说明代理快速适应误差，不外推到 BO 样本效率或 OOD 泛化",
    }

    l2 = {
        "layer": L2_LAYER,
        "status": "NOT_EVALUATED_IN_M6",
        "statement": "M6 只评估代理快速适应误差；BO 样本效率必须引用 M5 holdout 统计，禁止由 K-shot RMSE 推断",
        "m5_reference": dict(m5_reference) if m5_reference is not None else {"status": "PENDING_M5_HOLDOUT"},
    }

    ood_row = None
    for candidate in stats_rows:
        if (
            candidate["study"] == "ood"
            and candidate["source_family"] == config.train_family
            and int(candidate["K"]) == 5
            and candidate["metric"] == "rmse_norm"
            and candidate["arm"] == "M"
            and candidate["reference"] == "R"
        ):
            ood_row = dict(candidate)
            break
    ood_significant = bool(ood_row and ood_row.get("reject_holm") and ood_row.get("median_diff") is not None and float(ood_row["median_diff"]) < 0.0)
    diagnostics_ok = bool(ood_diagnostic.get("conclusion_allowed"))
    if ood_row is None or ood_row.get("status") == "INSUFFICIENT_TASKS":
        l3_status = "INCONCLUSIVE"
    elif ood_significant and diagnostics_ok:
        l3_status = "OOD_ADVANTAGE_OBSERVED_CONDITIONAL"
    elif ood_significant and not diagnostics_ok:
        l3_status = "OOD_ADVANTAGE_NOT_ATTRIBUTABLE"
    else:
        l3_status = "OOD_NO_SIGNIFICANT_ADVANTAGE"
    difficulty_matching = dict(ood_diagnostic.get("difficulty_matching") or {})
    matching_status = str(difficulty_matching.get("status") or "NOT_COMPUTED")
    if l3_status == "OOD_ADVANTAGE_OBSERVED_CONDITIONAL" and matching_status not in ("MATCHED",):
        l3_status = "OOD_ADVANTAGE_NOT_ATTRIBUTABLE"
    l3 = {
        "layer": L3_LAYER,
        "definition": "OOD 参数外推与新函数族上的误差优势，必须先通过 H1-H5 混杂诊断与逐任务难度匹配",
        "ood_comparison": {"arm": "M", "reference": "R", "K": 5, "metric": "rmse_norm", "row": ood_row},
        "difficulty_matching_status": matching_status,
        "attribution_gate": "H1 通过 且 difficulty_matching.status=MATCHED 才允许条件性表述泛化",
        "diagnostics_status": ood_diagnostic.get("status"),
        "diagnostics_conclusion_allowed": diagnostics_ok,
        "negative_control_status": negative_control.get("status"),
        "status": l3_status,
        "scope": "即使 OOD 不退化也不能宣布泛化成功；只有 H1-H5 通过且优势显著才可条件性表述",
    }
    return {
        "layers": {L1_LAYER: l1, L2_LAYER: l2, L3_LAYER: l3},
        "separation": "三层结论各自独立报告；禁止由 L1 推断 L2/L3，禁止把 K=5 RMSE 较低自动宣布 BO 更优",
        "cross_layer_inference_forbidden": True,
        "status": "OK",
    }


# ---------------------------------------------------------------------------
# 图数据（fig1/fig2 归本模块；fig3-5 归 M5；fig6 归 Issue #4）
# ---------------------------------------------------------------------------
def build_figure_data(
    config: M6RunnerConfig,
    *,
    training_rows: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
    adapt_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """生成 fig1（元训练损失曲线）与 fig2（K-shot MAE/RMSE）的绘图数据，不生成假图。"""
    fig1_series: dict[str, dict[str, Any]] = {}
    for meta_seed in config.meta_seeds:
        for arm in ("M", "P"):
            rows = [
                row
                for row in training_rows
                if int(row.get("meta_seed", -1)) == int(meta_seed) and row.get("arm") == arm
            ]
            if not rows:
                continue
            rows = sorted(rows, key=lambda row: int(row["iteration"]))
            fig1_series[f"meta{int(meta_seed)}-{arm}"] = {
                "meta_seed": int(meta_seed),
                "arm": arm,
                "x": [int(row["iteration"]) for row in rows],
                "loss": [_finite_or_none(row.get("loss_query")) for row in rows],
                "loss_support": [_finite_or_none(row.get("loss_support")) for row in rows],
                "status": "READY" if any(row.get("status") == "VALID" for row in rows) else "NOT_AVAILABLE",
            }
    fig2_rows: list[dict[str, Any]] = []
    for row in summary_rows:
        if row["metric"] not in ("rmse_raw", "rmse_norm", "mae_raw", "mae_norm"):
            continue
        if row.get("status") == "MISSING":
            continue
        fig2_rows.append(
            {
                "study": row["study"],
                "source_family": row["source_family"],
                "arm": row["arm"],
                "K": int(row["K"]),
                "metric": row["metric"],
                "mean": row.get("mean"),
                "ci_low": row.get("ci_low"),
                "ci_high": row.get("ci_high"),
                "n_nonnull": row.get("n_nonnull"),
                "status": row.get("status"),
            }
        )
    # OOD 退化比例（原始 vs 标准化），仅作诊断证据，不构成结论
    degradation: dict[str, Any] = {}
    for metric in ("rmse_raw", "rmse_norm"):
        indist = _summary_value(summary_rows, study="in_dist", family=config.train_family, arm="M", k_shot=5, metric=metric)
        ood = _summary_value(summary_rows, study="ood", family=config.train_family, arm="M", k_shot=5, metric=metric)
        ratio = None
        if indist is not None and ood is not None and indist > 0:
            ratio = ood / indist
        degradation[metric] = {
            "in_dist_mean": indist,
            "ood_mean": ood,
            "ood_over_in_dist_ratio": ratio,
            "degraded": bool(ratio is not None and ratio > DEGRADATION_RATIO),
        }
    figures = {
        "fig1_meta_training_loss": {
            "status": "READY" if fig1_series else "NOT_AVAILABLE",
            "title": "图1 元训练/预训练损失曲线（多 seed）",
            "series": fig1_series,
            "note": "MAML 元验证损失未记录时标 NOT_AVAILABLE，不补假曲线",
        },
        "fig2_k_shot_adaptation": {
            "status": "READY" if fig2_rows else "NOT_AVAILABLE",
            "title": "图2 K-shot MAE/RMSE（按族与 OOD 分列，原始值与标准化值并列）",
            "rows": fig2_rows,
            "n_rows": len(fig2_rows),
            "degradation_diagnostic": degradation,
            "note": "不同函数族原始目标值不可混合比较；标准化值同图分面展示",
        },
        "fig3_feasible_rate": {
            "status": "NOT_RUN",
            "note": "可行率/first_feasible 图归 M5 holdout 产物（m5_runner figures/），本模块不重复绘图",
        },
        "fig4_equal_budget_gap": {
            "status": "NOT_RUN",
            "note": "等预算 best_feasible/gap 曲线归 M5 holdout 产物，本模块不重复绘图",
        },
        "fig5_fairness_audit": {
            "status": "NOT_RUN",
            "note": "识别臂/代理成本审计图归 M5 holdout 产物（arm_audit/clone_audit），本模块引用不重绘",
        },
        "fig6_airframe_gate_progress": {
            "status": "NOT_RUN",
            "note": "fig6 归 Issue #4 D-12D-004（VSPAERO/RCAIDE 回退气动油耗+A/B/C 预算门禁联合进度）；P4-CODE 阶段 not_approved，禁止用非物理数值充图",
        },
    }
    return {
        "figures": figures,
        "status_note": "只有 READY 的图数据可交给 A2/A3 生成 PNG；NOT_RUN 不得用假数据替代",
        "physical_call_count": 0,
    }
# ---------------------------------------------------------------------------
# 确定性检查（排除 wall_s；参数指纹 + 适应矩阵逐位比较）
# ---------------------------------------------------------------------------
DETERMINISM_EXCLUDED_COLUMNS = ("wall_s",)
M6_PRODUCT_FILES = (
    "run_config.json",
    "environment.json",
    "tasks.json",
    "reference_solutions.json",
    "meta_task_split.json",
    "solver_validation.csv",
    "determinism_check.json",
    "metrics/training_history.csv",
    "metrics/adaptation_results.csv",
    "metrics/adaptation_summary.csv",
    "metrics/statistics.csv",
    "metrics/metrics.csv",
    "figures/figure_data.json",
    "figures/figure_status.json",
    "gate/frozen_family.json",
    "gate/preregistration.json",
    "gate/meta_task_split.json",
    "gate/frozen_gate.json",
    "old_m2_run_immutability.json",
    "README.md",
    "summary.json",
    "data_manifest.json",
)


def _adaptation_digest(rows: Sequence[Mapping[str, Any]], artifact_sha256: Mapping[str, Any]) -> str:
    """适应矩阵指纹：排除 wall_s 后逐行规范化 JSON 的 sha256。"""
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            {str(key): dict(value) for key, value in sorted(artifact_sha256.items())},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    )
    for row in rows:
        payload = {
            key: value
            for key, value in row.items()
            if key not in DETERMINISM_EXCLUDED_COLUMNS
        }
        digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def determinism_check(
    config: M6RunnerConfig,
    passes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """多次独立重跑核心后比较指纹；不足 2 次如实标 NOT_RUN，不冒充通过。"""
    digests = [str(item["digest"]) for item in passes]
    artifacts = [dict(item.get("artifact_sha256", {})) for item in passes]
    distinct = sorted(set(digests))
    if len(passes) < 2:
        status = "NOT_RUN"
        note = (
            f"determinism_reruns={len(passes)} < 2，未做独立重跑；"
            "不得声称确定性通过（m6 核心不具可比性时降级结论）"
        )
    elif len(distinct) == 1:
        status = "PASS"
        note = f"{len(passes)} 次独立重跑适应矩阵与参数指纹逐位一致"
    else:
        status = "FAIL"
        note = "多次重跑结果不一致；M6 结论降级为不可用，需排查非确定性来源后重跑"
    return {
        "status": status,
        "reruns": len(passes),
        "excluded_columns": list(DETERMINISM_EXCLUDED_COLUMNS),
        "digests": digests,
        "distinct_digests": len(distinct),
        "artifact_sha256": artifacts,
        "note": note,
        "physical_call_count": 0,
    }


# ---------------------------------------------------------------------------
# 产物写出
# ---------------------------------------------------------------------------
def _base_run_config(config: M6RunnerConfig, datasets: Mapping[str, Any], git_state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "p4-m6-run-config-1",
        "stage": STAGE,
        "run_id": config.run_id,
        "created_utc": iso_utc(),
        "data_origin": DATA_ORIGIN,
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "physical_guard_expected": int(config.physical_guard_expected),
        "evaluator_id": EVALUATOR_ID,
        "git_sha": git_state.get("git_sha"),
        "git_sha_label": git_state.get("git_sha_label", git_state.get("git_sha")),
        "worktree_dirty": git_state.get("worktree_dirty"),
        "config": config.to_dict(),
        "study_scale": config.study_scale,
        "conclusions_allowed": config.conclusions_allowed,
        "arms": {arm: {"method": M6_METHODS[arm]} for arm in M6_ARMS},
        "ks": list(config.ks),
        "meta_seeds": list(config.meta_seeds),
        "families": {
            family_id: {
                "fingerprint": dataset["fingerprint"],
                "counts": {split: len(items) for split, items in dataset["splits"].items()},
                "config": dataset["config"].__dict__ if hasattr(dataset["config"], "__dict__") else {},
            }
            for family_id, dataset in datasets.items()
        },
        "primary_endpoint": "meta_test / in_dist 上 K=5 query RMSE（任务内标准化）MAML(M) vs 预训练(P) / 随机(R)",
        "secondary_endpoints": [
            "K=0/1/10/20 query RMSE/MAE（原始值与标准化值）",
            "OOD 参数外推与新函数族上 K=5 query RMSE",
            "内循环损失稳定性（loss_final/loss_std/loss_monotonic_fraction）",
            "每臂适应墙钟时间（wall_s，仅作成本披露，不作统计推断）",
        ],
        "statistics": {
            "unit": "task",
            "pairing": "(task, meta_seed) 配对后按任务取均值，再跨任务统计",
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "confidence": CONFIDENCE,
            "test": "wilcoxon_signed_rank",
            "multiple_comparison": "Holm-Bonferroni（每个 (study, 族, K, 指标) 内 3 个预注册比较 M-P / M-R / P-R）",
            "min_tasks_for_stats": MIN_TASKS_FOR_STATS,
            "nonnull_threshold": MIN_NONNULL_FRACTION,
        },
        "meta_test_tuning_policy": "M6 不使用 meta_test/OOD 结果做任何模型选择或超参调整；选择只看 meta_train/meta_validation",
        "not_approved": list(NOT_APPROVED),
        "notes": [
            "SYNTHETIC_ONLY：全部标签来自解析合成任务族，physical_call_count=0（fail-closed）",
            "跨族原始目标尺度不同，原始值与标准化值同时保留，不混合比较",
            "三层结论（L1 代理误差 / L2 BO 样本效率 / L3 OOD 泛化）分别报告，禁止跨层推断",
        ],
    }


def _render_readme(
    config: M6RunnerConfig,
    *,
    summary: Mapping[str, Any],
    headline: Sequence[Mapping[str, Any]],
    ood_diagnostic: Mapping[str, Any],
    negative_control: Mapping[str, Any],
    conclusions: Mapping[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# P4-M6 快速适应 harness（合成任务族，SYNTHETIC_ONLY）")
    lines.append("")
    lines.append("## 1. 范围与边界")
    lines.append("")
    lines.append(f"- run_id：{config.run_id}；stage：{STAGE}；数据来源：{DATA_ORIGIN}。")
    lines.append("- 三臂：M=MAML 一阶元训练，P=监督预训练后微调，R=随机初始化；同结构、同评估预算、同 support/query。")
    lines.append(
        f"- K ∈ {list(config.ks)}；评估研究：同分布（meta_test）、OOD 参数外推（meta_test_ood）、"
        f"新函数族 {list(config.new_families)}；负控制单列。"
    )
    lines.append("- 全部标签为解析合成真值；physical_call_count=0，未调用任何真实 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器，无网络。")
    lines.append("- 研究规模判定：study_scale=%s，conclusions_allowed=%s。" % (config.study_scale, config.conclusions_allowed))
    lines.append("")
    lines.append("## 2. 配置")
    lines.append("")
    lines.append("- 元训练 seed：" + str(list(config.meta_seeds)) + "；元训练任务数：" + str(config.train_tasks))
    lines.append("- support 池：" + str(config.support_pool_size) + "；query：" + str(config.query_size) + "；元训练步数：" + str(config.max_meta_steps))
    lines.append("- 微调步数：" + str(config.inner_steps) + "；确定性重跑次数：" + str(config.determinism_reruns))
    lines.append("")
    lines.append("## 3. 结果（任务层级均值，K=5，任务内标准化 RMSE）")
    lines.append("")
    if headline:
        lines.append("| study | source_family | arm | K | n_tasks | mean rmse_norm | ci_low | ci_high | null_rate | status |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in headline:
            lines.append(
                "| {study} | {source_family} | {arm} | {K} | {n_tasks} | {mean} | {ci_low} | {ci_high} | {null_rate} | {status} |".format(
                    study=row.get("study"),
                    source_family=row.get("source_family"),
                    arm=row.get("arm"),
                    K=row.get("K"),
                    n_tasks=row.get("n_tasks"),
                    mean=_fmt(row.get("mean")),
                    ci_low=_fmt(row.get("ci_low")),
                    ci_high=_fmt(row.get("ci_high")),
                    null_rate=_fmt(row.get("null_rate")),
                    status=row.get("status"),
                )
            )
    else:
        lines.append("NOT_AVAILABLE：无 K=5 汇总行。")
    lines.append("")
    lines.append("## 4. OOD 诊断与负控制（不构成泛化结论）")
    lines.append("")
    lines.append("- H1–H5 诊断总体状态：" + str(ood_diagnostic.get("status")) + "（conclusion_allowed=" + str(ood_diagnostic.get("conclusion_allowed")) + "）")
    for check in ood_diagnostic.get("checks", ()):
        lines.append("  - " + str(check.get("id")) + " " + str(check.get("name")) + "：" + str(check.get("status")))
    lines.append("- 负控制状态：" + str(negative_control.get("status")))
    for check in negative_control.get("checks", ()):
        lines.append("  - " + str(check.get("id")) + " " + str(check.get("name")) + "：" + str(check.get("status")))
    lines.append("")
    lines.append("## 5. 三层结论（严格分离）")
    lines.append("")
    layers = conclusions.get("layers", {})
    for name in (L1_LAYER, L2_LAYER, L3_LAYER):
        layer = layers.get(name, {})
        lines.append("- " + name + "：" + str(layer.get("status")) + " —— " + str(layer.get("scope", "")))
    lines.append("- " + str(conclusions.get("separation")))
    lines.append("")
    lines.append("## 6. non-claims")
    lines.append("")
    for item in NOT_APPROVED:
        lines.append("- " + str(item))
    lines.append("- 不宣称真实飞机油耗/Mach 2.02 物理改进/真实 P4 优化；VSPAERO 结果为 NOT_RUN（归 Issue #4 D-12D-004）。")
    lines.append("")
    lines.append("## 7. 产物与复现")
    lines.append("")
    lines.append("- 产物文件：" + "、".join(M6_PRODUCT_FILES))
    lines.append("- 确定性：determinism_reruns=" + str(config.determinism_reruns) + "，比较时排除列：" + "、".join(DETERMINISM_EXCLUDED_COLUMNS))
    lines.append(
        "- 复现命令：cd D:/RCAIDE-p4-meta-learning && D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m research.concorde_metaopt.meta_learning.m6_study "
        + f"--run-id {config.run_id} --output-root <OUT> --ks {','.join(str(k) for k in config.ks)} "
        + f"--meta-seeds {','.join(str(seed) for seed in config.meta_seeds)}"
    )
    lines.append("")
    lines.append("## 8. 状态")
    lines.append("")
    lines.append("- summary.status = " + str(summary.get("status")) + "；physical_call_count = " + str(summary.get("physical_call_count")))
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    number = _finite_or_none(value)
    if number is None:
        return "NA"
    return f"{number:.6g}"


def _tasks_payload(datasets: Mapping[str, Any]) -> dict[str, Any]:
    families: dict[str, Any] = {}
    for family_id, dataset in datasets.items():
        family_config = dataset["config"]
        families[family_id] = {
            "family_id": family_id,
            "family_fingerprint": dataset["fingerprint"],
            "config": {
                "family_id": family_config.family_id,
                "design_dim": int(family_config.design_dim),
                "context_names": list(family_config.context_names),
                "seed": int(family_config.seed),
                "train_tasks": int(family_config.train_tasks),
                "validation_tasks": int(family_config.validation_tasks),
                "test_tasks": int(family_config.test_tasks),
                "ood_tasks": int(family_config.ood_tasks),
                "negative_control_tasks": int(family_config.negative_control_tasks),
                "designs_per_task": int(family_config.designs_per_task),
                "support_pool_size": int(family_config.support_pool_size),
                "query_size": int(family_config.query_size),
            },
            "counts": {split: len(items) for split, items in dataset["splits"].items()},
            "tasks": [tf.serialize_task(task) for task in dataset["tasks"]],
        }
    return {"schema_version": "p4-m6-tasks-1", "families": families}


def _reference_solutions_payload(datasets: Mapping[str, Any]) -> dict[str, Any]:
    solutions: dict[str, Any] = {}
    for dataset in datasets.values():
        for task in dataset["tasks"]:
            if task.is_negative_control:
                continue
            reference = task.reference()
            solutions[task.task_id] = {
                "family": task.family,
                "split": task.split,
                "objective_star": float(reference["objective_star"]),
                "u_star": [float(value) for value in np.asarray(reference["u_star"], dtype=np.float64)],
                "reference_kind": str(reference["reference_kind"]),
                "assertion_residual": float(reference["assertion_residual"]),
                "feasible": bool(reference["feasible"]),
            }
    return {"schema_version": "p4-m6-reference-solutions-1", "reference_solution": "c/analytic", "solutions": solutions}


def _split_manifest_payload(datasets: Mapping[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {"schema_version": "p4-m6-split-1", "families": {}}
    for family_id, dataset in datasets.items():
        split_payload = {
            "counts": {split: len(items) for split, items in dataset["splits"].items()},
            "task_ids": {
                split: [task.task_id for task in items] for split, items in dataset["splits"].items()
            },
            "fingerprint": dataset["fingerprint"],
        }
        body["families"][family_id] = split_payload
    body["split_hash"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return body


def _write_m6_products(
    config: M6RunnerConfig,
    *,
    datasets: Mapping[str, Any],
    matrix: Mapping[str, Any],
    summary_rows: Sequence[Mapping[str, Any]],
    stats_rows: Sequence[Mapping[str, Any]],
    metrics_rows: Sequence[Mapping[str, Any]],
    determinism: Mapping[str, Any],
    negative_control: Mapping[str, Any],
    ood_diagnostic: Mapping[str, Any],
    conclusions: Mapping[str, Any],
    figure_data: Mapping[str, Any],
    git_state: Mapping[str, Any],
    runtime_s: float,
    m5_reference: Mapping[str, Any] | None,
    gate: m6_frozen.FrozenGate,
    old_run_gate: Mapping[str, Any],
    frozen_split_verification: Mapping[str, Any],
) -> dict[str, Any]:
    run_dir = config.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("metrics", "figures"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    headline: list[dict[str, Any]] = []
    for row in summary_rows:
        if (
            int(row["K"]) == 5
            and row["metric"] == "rmse_norm"
            and row["study"] != "negative_control"
        ):
            headline.append(dict(row))
    headline.sort(key=lambda row: (STUDY_ORDER.index(row["study"]), row["source_family"], M6_ARMS.index(row["arm"])))
    summary: dict[str, Any] = {
        "schema_version": "p4-m6-summary-1",
        "stage": STAGE,
        "run_id": config.run_id,
        "created_utc": iso_utc(),
        "status": _summary_status(matrix, determinism),
        "study_scale": config.study_scale,
        "conclusions_allowed": config.conclusions_allowed,
        "data_origin": DATA_ORIGIN,
        "evaluator_id": EVALUATOR_ID,
        "arms": list(M6_ARMS),
        "ks": list(config.ks),
        "meta_seeds": list(config.meta_seeds),
        "split_counts": {
            family_id: {split: len(items) for split, items in dataset["splits"].items()}
            for family_id, dataset in datasets.items()
        },
        "counts": {
            "families": len(datasets),
            "evaluation_units": len(matrix.get("units", ())),
            "adaptation_runs": int(matrix.get("n_runs", 0)),
            "adaptation_rows": len(matrix.get("rows", ())),
            "training_rows": len(matrix.get("training_rows", ())),
            "statistics_rows": len(stats_rows),
            # A5M6-11：adaptation_runs 只是 pass0 行数；实际执行次数 = 行数 x 确定性重跑次数
            "determinism_passes": int(determinism.get("reruns", 0) or 0),
            "total_adaptation_executions": len(matrix.get("rows", ()))
            * int(determinism.get("reruns", 0) or 0),
            "nonfinite_rows": _count_rows(matrix.get("rows", ())),
        },
        "frozen_gate": gate.to_dict(),
        "old_run_gate": dict(old_run_gate),
        "frozen_split_verification": dict(frozen_split_verification),
        "k_omissions": list(config.k_omissions),
        "primary_endpoint": "K=5 任务内标准化 query RMSE（M vs P / M vs R）",
        "headline_rows": headline,
        "negative_control": dict(negative_control),
        "ood_diagnostics": dict(ood_diagnostic),
        "three_layer_conclusions": dict(conclusions),
        "determinism": dict(determinism),
        "artifact_sha256": {str(key): dict(value) for key, value in matrix.get("artifact_sha256", {}).items()},
        "m5_reference": dict(m5_reference) if m5_reference is not None else {"status": "PENDING_M5_HOLDOUT"},
        "figures": {
            name: (value.get("status") if isinstance(value, Mapping) else None)
            for name, value in figure_data.get("figures", {}).items()
        },
        "runtime_s": float(runtime_s),
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "physics_guard": {"expected": 0, "status": "PASS"},
        "not_approved": list(NOT_APPROVED),
        "products": list(M6_PRODUCT_FILES),
        "message": "SYNTHETIC_ONLY：全部标签来自解析合成任务族；禁止外推到真实飞机/油耗/BO 样本效率",
        "notes": [
            "M6 不使用 meta_test/OOD 做模型选择；元训练只用 meta_train（未做 validation 早停，需在报告中披露）",
            "L2 BO 样本效率必须引用 M5 holdout 统计，M6 不推断",
            "负控制单列，不进入主终点或调参",
            "确定性重跑不足 2 次时状态 NOT_RUN，不允许声称通过",
        ],
    }
    if determinism.get("status") == "FAIL":
        summary["status"] = "DETERMINISM_FAILED"
        summary["conclusions_allowed"] = False
    run_config = _base_run_config(config, datasets, git_state)
    run_config["m5_reference"] = summary["m5_reference"]
    write_json(run_dir / "run_config.json", run_config)
    write_json(run_dir / "environment.json", environment_payload(config.run_id, physical_call_count=PHYSICAL_CALL_COUNT))
    write_json(run_dir / "tasks.json", _tasks_payload(datasets))
    write_json(run_dir / "reference_solutions.json", _reference_solutions_payload(datasets))
    write_json(run_dir / "meta_task_split.json", _split_manifest_payload(datasets))
    gate_copies = gate.write_gate_directory(run_dir)
    frozen_gate_payload = gate.to_dict()
    frozen_gate_payload["gate_directory"] = gate_copies
    frozen_gate_payload["frozen_split_verification"] = dict(frozen_split_verification)
    write_json(run_dir / "gate" / "frozen_gate.json", frozen_gate_payload)
    write_json(run_dir / "determinism_check.json", dict(determinism))
    write_csv(run_dir / "metrics" / "training_history.csv", matrix.get("training_rows", ()), TRAINING_HISTORY_COLUMNS)
    write_csv(run_dir / "metrics" / "adaptation_results.csv", matrix.get("rows", ()), ADAPTATION_RESULT_COLUMNS)
    write_csv(run_dir / "metrics" / "adaptation_summary.csv", summary_rows, ADAPTATION_SUMMARY_COLUMNS)
    write_csv(run_dir / "metrics" / "statistics.csv", stats_rows, STATISTICS_COLUMNS)
    write_csv(run_dir / "metrics" / "metrics.csv", metrics_rows, METRICS_COLUMNS)
    solver_rows = [
        dict(row, run_id=config.run_id, evaluator_id=EVALUATOR_ID) for row in SOLVER_VALIDATION_ROWS
    ]
    write_csv(run_dir / "solver_validation.csv", solver_rows, SOLVER_VALIDATION_COLUMNS)
    figures_dir = run_dir / "figures"
    write_json(figures_dir / "figure_data.json", dict(figure_data))
    missing_figures = [name for name in M6_CANONICAL_FIGURES if name not in summary["figures"]]
    figure_status = {
        "run_id": config.run_id,
        "status": "PARTIAL" if not missing_figures else "PACKAGE_INCOMPLETE",
        "figures": summary["figures"],
        "canonical_figures": list(M6_CANONICAL_FIGURES),
        "missing_canonical_figures": missing_figures,
        "preflight": {
            "status": "PASS" if not missing_figures else "MISSING_CANONICAL_KEYS",
            "rule": "六个规范图键必须显式存在；缺失只能标 NOT_RUN，禁止补假数据",
        },
        "note": "只有 READY 的图数据可生成 PNG；NOT_RUN 不得补假数据（fig3-5 归 M5，fig6 归 Issue #4 D-12D-004）",
    }
    write_json(figures_dir / "figure_status.json", figure_status)
    readme = _render_readme(
        config,
        summary=summary,
        headline=headline,
        ood_diagnostic=ood_diagnostic,
        negative_control=negative_control,
        conclusions=conclusions,
    )
    (run_dir / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    write_json(run_dir / "summary.json", summary)
    manifest = build_data_manifest(run_dir)
    write_json(run_dir / "data_manifest.json", manifest)
    return {"run_dir": str(run_dir), "products": list(M6_PRODUCT_FILES), "data_manifest": manifest, "summary": summary}


def _write_failure_summary(config: M6RunnerConfig, error: BaseException, *, status: str, physical_call_count: int | None = None) -> dict[str, Any]:
    run_dir = config.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "p4-m6-summary-1",
        "stage": STAGE,
        "run_id": config.run_id,
        "created_utc": iso_utc(),
        "status": status,
        "study_scale": config.study_scale,
        "conclusions_allowed": False,
        "data_origin": DATA_ORIGIN,
        "error": {"type": type(error).__name__, "message": str(error)},
        "physical_call_count": physical_call_count,
        "physics_guard": {
            "expected": 0,
            "status": "VIOLATED" if status == "PHYSICS_GUARD_VIOLATION" else "UNKNOWN",
            "message": str(error),
        },
        "products_written": ["summary.json"],
        "not_approved": list(NOT_APPROVED),
        "notes": ["失败如实落盘；未写任何指标/图，不伪造结果"],
    }
    write_json(run_dir / "summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# 主执行入口
# ---------------------------------------------------------------------------
def run_m6_study(
    config: M6RunnerConfig,
    *,
    progress: Any = None,
    m5_reference: Mapping[str, Any] | None = None,
    reruns: int | None = None,
) -> dict[str, Any]:
    """运行 M6：数据集→三臂元训练→K-shot 矩阵→统计→诊断→产物。fail-closed。"""
    if config.study_scale != "FORMAL" and config.conclusions_allowed:
        raise M6Error("SMOKE 规模不得允许下结论（fail-closed）")
    guard_baseline = _forbidden_modules_present()
    total_reruns = int(config.determinism_reruns if reruns is None else reruns)
    if total_reruns < 1:
        raise M6Error("确定性重跑次数必须 >= 1")
    wall_start = time.perf_counter()
    try:
        # A5M6-02：未冻结不得开 run；缺失/篡改 fail-closed（PREREGISTRATION_NOT_FROZEN）
        gate = m6_frozen.load_frozen_gate(
            frozen_run_dir=config.frozen_run_dir,
            frozen_family_path=config.frozen_family_path,
            preregistration_path=config.preregistration_path,
            split_manifest_path=config.split_manifest_path,
        )
        old_run_root = Path(config.old_run_output_root or config.output_root)
        old_run_gate = m6_frozen.begin_old_run_gate(old_run_root, config.run_dir)
        git_state = repo_git_state(Path(__file__).resolve().parents[3])
        datasets = build_m6_datasets(config, gate=gate, progress=progress)
        frozen_split_verification = (
            m6_frozen.verify_datasets(gate, datasets)
            if config.study_scale == "FORMAL"
            else {
                "status": "NOT_APPLICABLE_SMOKE",
                "note": "SMOKE 规模任务数缩小；冻结 split 逐位校验只在 FORMAL 执行",
            }
        )
        units = study_units(config, datasets)
        passes: list[dict[str, Any]] = []
        main_payload: dict[str, Any] | None = None
        for pass_index in range(total_reruns):
            if progress is not None:
                progress("m6_pass", {"pass": pass_index + 1, "total": total_reruns})
            artifacts = build_m6_artifacts(config, datasets, progress=progress if pass_index == 0 else None)
            matrix = run_m6_adaptation_matrix(
                config, datasets, artifacts, progress=progress if pass_index == 0 else None
            )
            assert_no_forbidden_modules(guard_baseline)
            digest = _adaptation_digest(matrix["rows"], matrix["artifact_sha256"])
            passes.append({"pass": pass_index, "digest": digest, "artifact_sha256": matrix["artifact_sha256"]})
            if pass_index == 0:
                main_payload = {
                    "matrix": matrix,
                    "artifacts": artifacts,
                }
        assert main_payload is not None
        matrix = main_payload["matrix"]
        summary_rows = adaptation_summary_rows(config, matrix["rows"])
        stats_rows = paired_comparison_rows(config, matrix["rows"])
        metrics_rows = metrics_rows_from_adaptation(config, matrix["rows"], summary_rows)
        negative_control = negative_control_check(config, stats_rows, summary_rows)
        ood_diagnostic = ood_diagnostics(config, datasets, adapt_rows=matrix["rows"], summary_rows=summary_rows)
        ood_diagnostic = attach_ood_difficulty_matching(
            config, datasets, ood_diagnostic, adapt_rows=matrix["rows"]
        )
        conclusions = three_layer_conclusions(
            config,
            stats_rows=stats_rows,
            summary_rows=summary_rows,
            ood_diagnostic=ood_diagnostic,
            negative_control=negative_control,
            m5_reference=m5_reference,
        )
        figure_data = build_figure_data(
            config,
            training_rows=matrix.get("training_rows", ()),
            summary_rows=summary_rows,
            adapt_rows=matrix["rows"],
        )
        conclusions = attach_new_family_layer(
            config, stats_rows=stats_rows, conclusions=conclusions, ood_diagnostic=ood_diagnostic
        )
        determinism = determinism_check(config, passes)
        runtime_s = time.perf_counter() - wall_start
        old_run_gate = m6_frozen.finish_old_run_gate(
            old_run_root, config.run_dir, old_run_gate, stage="m6_before_products"
        )
        written = _write_m6_products(
            config,
            datasets=datasets,
            matrix=matrix,
            summary_rows=summary_rows,
            stats_rows=stats_rows,
            metrics_rows=metrics_rows,
            determinism=determinism,
            negative_control=negative_control,
            ood_diagnostic=ood_diagnostic,
            conclusions=conclusions,
            figure_data=figure_data,
            git_state=git_state,
            runtime_s=runtime_s,
            m5_reference=m5_reference,
            gate=gate,
            old_run_gate=old_run_gate,
            frozen_split_verification=frozen_split_verification,
        )
        summary = written["summary"]
        m6_frozen.assert_old_run_unchanged(old_run_root, old_run_gate, stage="m6_after_products")
        if progress is not None:
            progress(
                "m6_done",
                {
                    "run_id": config.run_id,
                    "status": summary["status"],
                    "runs": matrix["n_runs"],
                    "determinism": determinism["status"],
                    "study_scale": config.study_scale,
                    "wall_s": round(runtime_s, 2),
                },
            )
        return {
            "status": summary["status"],
            "stage": STAGE,
            "run_id": config.run_id,
            "run_dir": str(config.run_dir),
            "study_scale": config.study_scale,
            "conclusions_allowed": bool(summary["conclusions_allowed"]),
            "adaptation_runs": int(matrix["n_runs"]),
            "evaluation_units": len(units),
            "determinism": determinism["status"],
            "negative_control": negative_control["status"],
            "ood_diagnostics": ood_diagnostic["status"],
            "three_layer_status": {name: layer.get("status") for name, layer in conclusions["layers"].items()},
            "physical_call_count": PHYSICAL_CALL_COUNT,
            "frozen_gate": {
                "status": "PASS",
                "family_id": gate.family_id,
                "radius_base": gate.radius_base,
                "split_hash": gate.split_hash,
                "frozen_family_sha256": gate.frozen_sha256,
            },
            "old_run_gate": {
                "status": old_run_gate.get("status"),
                "enforced": old_run_gate.get("enforced"),
            },
            "total_adaptation_executions": int(summary["counts"]["total_adaptation_executions"]),
            "products_written": written["products"],
            "runtime_s": float(runtime_s),
            "summary": summary,
        }
    except PhysicsGuardViolation as error:
        _write_failure_summary(
            config,
            error,
            status="PHYSICS_GUARD_VIOLATION",
            physical_call_count=int(getattr(error, "physical_call_count", 1) or 1),
        )
        raise
    except M6FrozenGateError as error:
        # A5M6-02：冻结门禁失败必须单独状态，禁止混成普通 FAILED
        _write_failure_summary(config, error, status="PREREGISTRATION_NOT_FROZEN")
        raise
    except Exception as error:  # noqa: BLE001 - fail-closed 落盘后重抛
        _write_failure_summary(config, error, status="FAILED")
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_argument_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="P4-M6 快速适应 harness（合成任务族，SYNTHETIC_ONLY）")
    parser.add_argument("--run-id", default=None, help="默认 p4-m6-<UTC>")
    parser.add_argument("--output-root", default=str(Path("research/concorde_metaopt/optimization_runs")))
    parser.add_argument("--family-seed", type=int, default=20261102)
    parser.add_argument("--train-family", default=TRAIN_FAMILY)
    parser.add_argument("--new-families", default="F-LIN,F-MF")
    parser.add_argument("--ks", default="0,1,5,10,20")
    parser.add_argument("--meta-seeds", default="0,1,2")
    parser.add_argument("--max-meta-steps", type=int, default=200)
    parser.add_argument("--inner-steps", type=int, default=S_ADAPT)
    parser.add_argument("--train-tasks", type=int, default=60)
    parser.add_argument("--validation-tasks", type=int, default=20)
    parser.add_argument("--test-tasks", type=int, default=20)
    parser.add_argument("--ood-tasks", type=int, default=10)
    parser.add_argument("--negative-control-tasks", type=int, default=10)
    parser.add_argument("--support-pool-size", type=int, default=128)
    parser.add_argument("--query-size", type=int, default=64)
    parser.add_argument("--determinism-reruns", type=int, default=3)
    # A5M6-01/02：M5 冻结输入（必须提供；缺省不得开 run）
    parser.add_argument("--frozen-run-dir", default=None, help="M5 冻结 run 目录")
    parser.add_argument("--frozen-family", default=None)
    parser.add_argument("--preregistration", default=None)
    parser.add_argument("--split-manifest", default=None)
    parser.add_argument("--old-run-output-root", default=None, help="旧 M2 run 所在 output_root（缺省同 output_root）")
    parser.add_argument("--k-omissions", default="", help="显式预注册的 K 省略，例如 20")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    run_id = args.run_id or make_run_id(RUN_PREFIX)
    config = M6RunnerConfig(
        run_id=run_id,
        output_root=Path(args.output_root),
        family_seed=int(args.family_seed),
        train_family=str(args.train_family),
        new_families=tuple(item.strip() for item in str(args.new_families).split(",") if item.strip()),
        ks=tuple(int(item) for item in str(args.ks).split(",") if item.strip()),
        meta_seeds=tuple(int(item) for item in str(args.meta_seeds).split(",") if item.strip()),
        max_meta_steps=int(args.max_meta_steps),
        inner_steps=int(args.inner_steps),
        train_tasks=int(args.train_tasks),
        validation_tasks=int(args.validation_tasks),
        test_tasks=int(args.test_tasks),
        ood_tasks=int(args.ood_tasks),
        negative_control_tasks=int(args.negative_control_tasks),
        support_pool_size=int(args.support_pool_size),
        query_size=int(args.query_size),
        determinism_reruns=int(args.determinism_reruns),
        frozen_run_dir=Path(args.frozen_run_dir) if args.frozen_run_dir else None,
        frozen_family_path=Path(args.frozen_family) if args.frozen_family else None,
        preregistration_path=Path(args.preregistration) if args.preregistration else None,
        split_manifest_path=Path(args.split_manifest) if args.split_manifest else None,
        old_run_output_root=Path(args.old_run_output_root) if args.old_run_output_root else None,
        k_omissions=tuple(int(item) for item in str(args.k_omissions).split(",") if item.strip()),
    )
    result = {
        "run_id": config.run_id,
        "run_dir": str(config.run_dir),
        "study_scale": config.study_scale,
        "conclusions_allowed": config.conclusions_allowed,
    }
    try:
        outcome = run_m6_study(config, progress=lambda event, payload: print(json.dumps({"event": event, **payload}, ensure_ascii=False), flush=True))
        result.update(
            {
                "status": outcome["status"],
                "adaptation_runs": outcome["adaptation_runs"],
                "determinism": outcome["determinism"],
                "physical_call_count": outcome["physical_call_count"],
            }
        )
    except Exception as error:  # noqa: BLE001 - CLI 打印失败信息并返回非零
        result.update({"status": "FAILED", "error": f"{type(error).__name__}: {error}"})
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("status") == "VALID" else 1


_DIFFICULTY_MATCH_KEYS = (
    "query_objective_std",
    "mean_curvature",
    "radius",
    "context_shift_norm",
)
MATCH_TOLERANCE = 1.0


def _count_rows(rows: Sequence[Mapping[str, Any]]) -> int:
    """统计状态非 VALID 的行数（A5M6-08：NONFINITE 等异常必须传播到 summary）。"""
    return sum(1 for row in rows if str(row.get("status") or "") != "VALID")


def _summary_status(matrix: Mapping[str, Any], determinism: Mapping[str, Any]) -> str:
    """summary.status 推导：确定性失败优先，其次把非有限行传播为 VALID_WITH_NONFINITE。"""
    if str(determinism.get("status") or "") == "FAIL":
        return "DETERMINISM_FAILED"
    nonfinite = _count_rows(matrix.get("rows", ()))
    if str(matrix.get("status") or "") == "VALID_WITH_NONFINITE" or nonfinite > 0:
        return "VALID_WITH_NONFINITE"
    return "VALID"


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """平均秩（并列取平均），供 rank-biserial 相关使用。"""
    order = np.argsort(values, kind="stable")
    ranks = np.empty(values.size, dtype=float)
    sorted_values = values[order]
    index = 0
    while index < values.size:
        end = index + 1
        while end < values.size and sorted_values[end] == sorted_values[index]:
            end += 1
        ranks[order[index:end]] = 0.5 * (index + end - 1) + 1.0
        index = end
    return ranks


def _effect_sizes(differences: Any) -> dict[str, float | None]:
    """配对效应量：Cohen d（配对差均值/标准差）与 rank-biserial（基于差值绝对秩）。"""
    values = np.asarray(list(differences), dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return {"cohens_d": None, "rank_biserial": None}
    std = float(values.std(ddof=1))
    mean = float(values.mean())
    cohens_d = None if std <= 0.0 else mean / std
    nonzero = values[values != 0.0]
    if nonzero.size == 0:
        return {"cohens_d": cohens_d, "rank_biserial": 0.0}
    ranks = _average_ranks(np.abs(nonzero))
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    total = positive + negative
    rank_biserial = None if total <= 0.0 else (positive - negative) / total
    return {"cohens_d": cohens_d, "rank_biserial": rank_biserial}


def _difficulty_table(config: M6RunnerConfig, datasets: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """构造 meta_test / meta_test_ood 的逐任务难度协变量表（A5M6-04）。"""
    family = datasets[config.train_family]
    blocks = _evaluation_blocks(datasets, study_units(config, datasets))
    table: list[dict[str, Any]] = []
    for split in ("meta_test", "meta_test_ood"):
        for task in family["splits"].get(split, ()):  # type: ignore[union-attr]
            difficulty = _task_difficulty(task, blocks[task.task_id])
            row: dict[str, Any] = {"task_id": task.task_id, "split": split, "family": task.family}
            for key, value in difficulty.items():
                row[key] = _finite_or_none(value)
            table.append(row)
    table.sort(key=lambda row: (str(row["split"]), str(row["task_id"])))
    return table


def _difficulty_vectors(table: Sequence[Mapping[str, Any]], split: str) -> list[tuple[str, np.ndarray]]:
    """按固定键顺序抽取某 split 的难度向量；任一维缺失则跳过该任务。"""
    vectors: list[tuple[str, np.ndarray]] = []
    for row in table:
        if str(row.get("split")) != split:
            continue
        values = [row.get(key) for key in _DIFFICULTY_MATCH_KEYS]
        if any(value is None for value in values):
            continue
        vectors.append((str(row["task_id"]), np.asarray(values, dtype=float)))
    vectors.sort(key=lambda item: item[0])
    return vectors


def _match_ood_to_indist(table: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """在难度协变量空间做确定性一一最近邻匹配，并报告匹配集的不平衡度。"""
    in_dist = _difficulty_vectors(table, "meta_test")
    ood = _difficulty_vectors(table, "meta_test_ood")
    if not in_dist or not ood:
        return {
            "status": "INSUFFICIENT_TASKS",
            "matching_keys": list(_DIFFICULTY_MATCH_KEYS),
            "pairs": [],
            "note": "某一 split 无可用难度协变量，无法做逐任务匹配",
        }
    base = np.stack([vector for _, vector in in_dist])
    center = base.mean(axis=0)
    scale = base.std(axis=0)
    scale = np.where(scale > 0.0, scale, 1.0)

    def standardize(vector: np.ndarray) -> np.ndarray:
        return (vector - center) / scale

    available = list(range(len(in_dist)))
    pairs: list[dict[str, Any]] = []
    for ood_task, ood_vector in ood:
        ood_z = standardize(ood_vector)
        best_index = min(available, key=lambda idx: (float(np.linalg.norm(ood_z - standardize(in_dist[idx][1]))), idx))
        in_task, in_vector = in_dist[best_index]
        available.remove(best_index)
        in_z = standardize(in_vector)
        pairs.append(
            {
                "ood_task_id": ood_task,
                "in_dist_task_id": in_task,
                "distance": float(np.linalg.norm(ood_z - in_z)),
                "ood_z": [float(value) for value in ood_z],
                "in_dist_z": [float(value) for value in in_z],
            }
        )
        if not available:
            break
    ood_z_mean = np.mean([pair["ood_z"] for pair in pairs], axis=0)
    in_z_mean = np.mean([pair["in_dist_z"] for pair in pairs], axis=0)
    imbalance_vector = ood_z_mean - in_z_mean
    max_abs_imbalance = float(np.max(np.abs(imbalance_vector))) if pairs else 0.0
    status = "MATCHED" if max_abs_imbalance <= MATCH_TOLERANCE else "POOR_MATCH"
    return {
        "status": status,
        "matching_keys": list(_DIFFICULTY_MATCH_KEYS),
        "n_pairs": len(pairs),
        "pairs": pairs,
        "imbalance": {key: float(value) for key, value in zip(_DIFFICULTY_MATCH_KEYS, imbalance_vector)},
        "max_abs_imbalance": max_abs_imbalance,
        "tolerance": MATCH_TOLERANCE,
        "rule": "只有在 in-dist 标准化后各匹配键 |imbalance|<=tolerance 才允许称难度匹配",
        "note": "贪心最近邻一一匹配（固定排序，确定性）；匹配集与不匹配集分开报告",
    }


def _matched_metric_deltas(
    adapt_rows: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
    *,
    k_shot: int = 5,
) -> dict[str, Any]:
    """在匹配对上计算 OOD - in-dist 的配对误差差（A5M6-04 条件对比）。"""
    metrics = ("rmse_raw", "rmse_norm")
    arms = ("M", "R")
    values: dict[tuple[str, str, str], list[float]] = {}
    for row in adapt_rows:
        if int(row.get("K", -1)) != k_shot:
            continue
        task_id = str(row.get("task_id"))
        arm = str(row.get("arm"))
        if arm not in arms:
            continue
        for metric in metrics:
            value = _finite_or_none(row.get(metric))
            if value is None:
                continue
            values.setdefault((task_id, arm, metric), []).append(float(value))
    means = {key: float(np.mean(items)) for key, items in values.items()}
    payload: dict[str, Any] = {"k_shot": k_shot, "metrics": {}, "n_pairs": len(pairs)}
    any_delta = False
    for metric in metrics:
        metric_payload: dict[str, Any] = {}
        for arm in arms:
            deltas: list[float] = []
            for pair in pairs:
                ood_mean = means.get((str(pair["ood_task_id"]), arm, metric))
                in_mean = means.get((str(pair["in_dist_task_id"]), arm, metric))
                if ood_mean is None or in_mean is None:
                    continue
                deltas.append(ood_mean - in_mean)
            if deltas:
                any_delta = True
            metric_payload[arm] = {
                "mean_delta": float(np.mean(deltas)) if deltas else None,
                "n_pairs": len(deltas),
            }
        payload["metrics"][metric] = metric_payload
    payload["status"] = "COMPUTED" if any_delta else "NO_DATA"
    return payload


def attach_ood_difficulty_matching(
    config: M6RunnerConfig,
    datasets: Mapping[str, Mapping[str, Any]],
    diagnostic: Mapping[str, Any],
    *,
    adapt_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """把难度协变量表与逐任务匹配结果并入 OOD 诊断（A5M6-04）。"""
    payload = dict(diagnostic)
    family = datasets[config.train_family]
    splits = family.get("splits", {})  # type: ignore[union-attr]
    if not splits.get("meta_test") or not splits.get("meta_test_ood"):
        payload["difficulty_matching"] = {
            "status": "NOT_AVAILABLE",
            "note": "meta_test 或 meta_test_ood 为空，无法做逐任务难度匹配",
        }
        payload["attribution_rule"] = "OOD 归因必须先完成逐任务难度匹配；无匹配时只允许描述性报告"
        return payload
    table = _difficulty_table(config, datasets)
    matching = _match_ood_to_indist(table)
    matching["metric_deltas"] = _matched_metric_deltas(adapt_rows, matching.get("pairs", ()))
    payload["difficulty_table"] = table
    payload["difficulty_matching"] = matching
    payload["attribution_rule"] = "只有 H1（难度）无混杂且 difficulty_matching.status=MATCHED 才允许 OOD 归因；否则标 INCONCLUSIVE/NOT_ATTRIBUTABLE"
    return payload


def _new_family_rows(
    stats_rows: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, list[Mapping[str, Any]]]:
    """提取 new_family 层 K=5 rmse_norm 的 M-R / P-R 预注册比较行。"""
    selected: list[Mapping[str, Any]] = []
    baseline = None
    for row in stats_rows:
        if str(row.get("study")) != "new_family":
            continue
        if int(row.get("K", -1)) != 5 or str(row.get("metric")) != "rmse_norm":
            continue
        arm = str(row.get("arm"))
        reference = str(row.get("reference"))
        if arm == "M" and reference == "R":
            baseline = row
        if (arm, reference) in (("M", "R"), ("P", "R")):
            selected.append(row)
    return baseline, selected


def attach_new_family_layer(
    config: M6RunnerConfig,
    *,
    stats_rows: Sequence[Mapping[str, Any]],
    conclusions: Mapping[str, Any],
    ood_diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    """把新函数族分层并入三层结论的 L3（A5M6-06）。"""
    payload = dict(conclusions)
    layers = dict(payload.get("layers") or {})
    l3 = dict(layers.get(L3_LAYER) or {})
    baseline, rows = _new_family_rows(stats_rows)
    if not rows or baseline is None:
        new_family_status = "INCONCLUSIVE"
    elif str(baseline.get("status")) == "INSUFFICIENT_TASKS":
        new_family_status = "INCONCLUSIVE"
    elif bool(baseline.get("reject_holm")) and float(baseline.get("median_diff") or 0.0) < 0.0:
        new_family_status = "NEW_FAMILY_ADVANTAGE_OBSERVED"
    else:
        new_family_status = "NO_SIGNIFICANT_ADVANTAGE"
    ood_status = str(l3.get("status") or "INCONCLUSIVE")
    if ood_status == "INCONCLUSIVE" and new_family_status == "INCONCLUSIVE":
        combined = "INCONCLUSIVE"
    elif ood_status != "OOD_NO_SIGNIFICANT_ADVANTAGE" and ood_status != "INCONCLUSIVE":
        combined = ood_status
    elif new_family_status == "NEW_FAMILY_ADVANTAGE_OBSERVED":
        combined = "NEW_FAMILY_ADVANTAGE_OBSERVED"
    else:
        combined = "OOD_NO_SIGNIFICANT_ADVANTAGE"
    l3["new_family_comparisons"] = [dict(row) for row in rows]
    l3["new_family_status"] = new_family_status
    l3["combined_status"] = combined
    l3["reports_both_ood_and_new_family"] = True
    l3["difficulty_matching_status"] = str(
        (ood_diagnostic.get("difficulty_matching") or {}).get("status") or "NOT_COMPUTED"
    )
    layers[L3_LAYER] = l3
    payload["layers"] = layers
    payload["l3_reports_both_layers"] = True
    return payload



__all__ = [
    "M6_ARMS",
    "M6Error",
    "M6RunnerConfig",
    "M6_STUDIES",
    "M6_METHODS",
    "M6_KS",
    "STUDY_ORDER",
    "adaptation_summary_rows",
    "build_figure_data",
    "build_m6_artifacts",
    "build_m6_datasets",
    "build_m6_family_configs",
    "determinism_check",
    "holm_bonferroni",
    "main",
    "metrics_rows_from_adaptation",
    "negative_control_check",
    "ood_diagnostics",
    "paired_comparison_rows",
    "run_m6_adaptation_matrix",
    "run_m6_study",
    "study_units",
    "three_layer_conclusions",
    "training_tasks",
    "M6_CANONICAL_FIGURES",
    "TRAIN_FAMILY",
    "attach_new_family_layer",
    "attach_ood_difficulty_matching",
]


if __name__ == "__main__":
    raise SystemExit(main())
