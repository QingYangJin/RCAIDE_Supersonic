"""P4-M5 正式离线合成实验运行器：calibration → freeze → holdout。

职责与边界（Issue #5 D-P4-002，P4-CODE）：
- 只使用解析合成任务族与 12D 设计空间的解析 evaluator，physical_call_count 恒为 0；
  禁止任何真实 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器调用与网络访问（§1.3）。
- calibration 阶段只在 meta_train / meta_validation 上校准可行域半径；
  冻结 frozen_family.json + meta_task_split.json + preregistration.json 后，
  holdout 阶段才允许一次性打开 meta_test / meta_test_ood（禁止用测试集调参）。
- 等预算：每臂每 run 恰好消耗 true_evaluation_budget 次真实（合成）评价；
  BO 初始化点数、DE 种群、代理打分成本单列，不混入真值预算。
- 统计在任务层级聚合：先对 (task_id, opt_seed) 配对，再跨任务 bootstrap CI /
  Wilcoxon / Holm 多重比较；非 null 比例不足时如实给 INCONCLUSIVE。
- 不伪造数据：无可行解时保留 null；不补假曲线；失败如实落盘并披露。
"""

from __future__ import annotations

import argparse
import hashlib
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from . import feasible_v2 as fv2
from . import task_family as tf
from .baseline_arms import PhysicsGuardViolation, make_synthetic_task_evaluator
from .m5_arms import (
    M5_ARM_ORDER,
    M5_BO_MAML_INIT,
    M5_BO_PRETRAIN_INIT,
    M5_BO_RANDOM,
    M5_DE,
    ARM_INITIALIZERS,
    M5_INITIAL_DESIGN_COUNT,
    arm_init_record,
    assert_m5_fairness,
    build_m5_model_artifacts,
    identifiability_audit,
    identifiability_rows,
    run_m5_arm,
)
from .offline_runner import (
    GuardedEvaluator,
    OfflineRunnerConfig,
    _forbidden_modules_present,
    assert_no_forbidden_modules,
    build_data_manifest,
    build_task_blocks,
    environment_payload,
    iso_utc,
    load_design_space_12d,
    make_run_id,
    repo_git_state,
    task_target_names,
    utc_now,
    write_csv,
    write_json,
    write_jsonl,
)

STAGE = "P4-CODE"
STAGE_VERSION = "p4-m5-runner-v1"
RUN_PREFIX = "p4-m5"
STAGES = ("calibration", "freeze", "holdout")
STUDY_SCALES = ("FORMAL", "SMOKE")
EVAL_SPLITS = ("meta_test", "meta_test_ood")
DESIGN_SET = "12d_lifting_surfaces"
SAFE_NULL_FRACTION = 0.70
BOOTSTRAP_SAMPLES = 10000
CONFIDENCE = 0.95
BOOTSTRAP_SEED = 20261104
PHYSICAL_CALL_COUNT = 0
MAX_ALLOWED_PHYSICAL_CALLS = 0
REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_ROOT = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"
DESIGN_SPACE_CONFIG = (
    REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
)

PRIMARY_ENDPOINTS = tuple(fv2.PRIMARY_ENDPOINTS)
SECONDARY_ENDPOINTS = tuple(fv2.SECONDARY_ENDPOINTS)
FALLBACK_ENDPOINTS = (
    "best_objective_raw",
    "min_constraint_violation_sum",
    "feasible_hit_rate",
)
# 端点名 -> optimization_summary 行字段名（仅个别别名，其余同名）
ENDPOINT_ROW_KEYS = {"n_failed_evals": "failed_evals"}


def endpoint_row_key(endpoint: str) -> str:
    """端点名到 summary 行字段名的映射（避免把计数端点误读成 null）。"""
    return ENDPOINT_ROW_KEYS.get(endpoint, endpoint)


ENDPOINT_DIRECTIONS = {
    "best_feasible_value": "lower_better",
    "gap_to_reference": "lower_better",
    "first_feasible_evaluation_index": "lower_better",
    "feasible_hit_rate": "higher_better",
    "best_objective_raw": "lower_better",
    "min_constraint_violation_sum": "lower_better",
}
PREREGISTERED_COMPARISONS = (
    (M5_BO_MAML_INIT, M5_BO_RANDOM),
    (M5_BO_MAML_INIT, M5_BO_PRETRAIN_INIT),
    (M5_BO_PRETRAIN_INIT, M5_BO_RANDOM),
    (M5_DE, M5_BO_RANDOM),
    (M5_BO_PRETRAIN_INIT, M5_BO_MAML_INIT),
    (M5_DE, M5_BO_MAML_INIT),
)

OPTIMIZATION_HISTORY_COLUMNS = (
    "run_id",
    "budget",
    "meta_seed",
    "arm",
    "task_id",
    "split",
    "family",
    "seed",
    "eval_index",
    *("design_u_%d" % index for index in range(12)),
    "objective",
    "feasible",
    "constraints_json",
    "cache_hit",
    "billable",
    "status",
    "wall_s",
    "best_feasible_so_far",
    "best_value_so_far",
    "best_objective_so_far",
    "initial_design",
)
OPTIMIZATION_SUMMARY_COLUMNS = (
    "run_id",
    "budget",
    "meta_seed",
    "arm",
    "task_id",
    "split",
    "family",
    "seed",
    "initializer",
    "implementation",
    "requested_evaluations",
    "true_evals_used",
    "cache_hits",
    "failed_evals",
    "initial_feasible_count",
    "best_feasible_value",
    "gap_to_reference",
    "reference_objective",
    "first_feasible_evaluation_index",
    "feasible_count",
    "violation_rate",
    "best_objective_raw",
    "min_constraint_violation_sum",
    "feasible_hit_rate",
    "feasibility_expected_zero",
    "null_rate",
    "status",
    "termination_reason",
    "wall_s",
    "proxy_scoring_cost_json",
    "physical_call_count",
)
TRAINING_HISTORY_COLUMNS = (
    "run_id",
    "arm",
    "split",
    "task_id",
    "family",
    "iteration",
    "epoch",
    "loss_support",
    "loss_query",
    "grad_norm",
    "lr",
    "seed",
    "wall_s",
    "status",
    "meta_seed",
)
ADAPTATION_RESULTS_COLUMNS = (
    "run_id",
    "task_id",
    "split",
    "family",
    "arm",
    "K",
    "seed",
    "n_support",
    "n_query",
    "adapt_steps",
    "mae_raw",
    "rmse_raw",
    "mae_norm",
    "rmse_norm",
    "r2",
    "max_abs_err",
    "wall_s",
    "status",
)
METRICS_COLUMNS = (
    "experiment_id",
    "phase",
    "split",
    "family",
    "arm",
    "K",
    "task_id",
    "seed",
    "metric",
    "value",
    "unit",
    "aggregation",
    "n",
    "status",
)
ARM_AUDIT_COLUMNS = (
    "run_id",
    "budget",
    "arm",
    "task_id",
    "split",
    "family",
    "seed",
    "meta_seed",
    "initializer",
    "implementation",
    "code_path",
    "candidate_pool_sha256",
    "artifact_sha256",
    "initial_designs_sha256",
    "true_evals_used",
    "requested_evaluations",
    "status",
)
CLONE_AUDIT_COLUMNS = (
    "budget",
    "arm",
    "reference",
    "groups_compared",
    "mean_initial_overlap",
    "max_initial_overlap",
    "fraction_groups_at_threshold",
    "clone",
    "label",
)
STATISTICS_COLUMNS = (
    "budget",
    "split",
    "endpoint",
    "arm",
    "reference",
    "direction",
    "n_pairs",
    "n_tasks",
    "n_nonnull",
    "null_fraction",
    "median_diff",
    "mean_diff",
    "ci_low",
    "ci_high",
    "improvement_probability",
    "wilcoxon_statistic",
    "wilcoxon_pvalue",
    "cohen_d_paired",
    "holm_pvalue",
    "status",
    "note",
)
ENDPOINT_SUMMARY_COLUMNS = (
    "budget",
    "split",
    "endpoint",
    "arm",
    "n_runs",
    "n_nonnull",
    "null_rate",
    "median",
    "mean",
    "std",
    "unit",
)


class M5RunnerError(RuntimeError):
    """M5 运行器错误（fail-closed：异常即中止并写失败 summary）。"""


class PreregistrationNotFrozen(M5RunnerError):
    """在冻结/预注册校验完成前试图打开 holdout 测试集。"""


@dataclass(frozen=True)
class M5RunnerConfig:
    """M5 一次 run 的配置（含阶段、等预算/seed/任务规模声明）。"""

    run_id: str = ""
    output_root: Path = RUNS_ROOT
    stage: str = "holdout"
    family_seed: int = 20261102
    meta_train_tasks: int = 60
    meta_validation_tasks: int = 20
    meta_test_tasks: int = 20
    ood_tasks: int = 10
    negative_control_tasks: int = 10
    support_pool_size: int = 128
    query_size: int = 64
    budgets: tuple[int, ...] = (64, 128)
    optimization_seeds: tuple[int, ...] = tuple(range(10))
    meta_seeds: tuple[int, ...] = (0, 1, 2)
    calibration: fv2.CalibrationConfig = field(
        default_factory=lambda: fv2.CalibrationConfig(family_seed=20261102)
    )
    max_meta_steps: int = 200
    pretrain_steps: int = 50
    determinism_reruns: int = 3
    physical_guard_expected: int = 0
    calibration_report_path: Path | None = None
    frozen_family_path: Path | None = None
    preregistration_path: Path | None = None
    split_manifest_path: Path | None = None

    def __post_init__(self) -> None:
        if not self.run_id:
            object.__setattr__(self, "run_id", make_run_id(RUN_PREFIX))
        if not isinstance(self.run_id, str) or any(ch in self.run_id for ch in ("/", "\\")):
            raise M5RunnerError("run_id 必须是不含路径分隔符的字符串")
        object.__setattr__(self, "output_root", Path(self.output_root))
        if self.stage not in STAGES:
            raise M5RunnerError(f"stage 必须是 {STAGES} 之一，实际 {self.stage!r}")
        for name in (
            "meta_train_tasks",
            "meta_validation_tasks",
            "meta_test_tasks",
            "ood_tasks",
            "negative_control_tasks",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise M5RunnerError(f"{name} 必须是非负整数，实际 {value!r}")
        for name in ("support_pool_size", "query_size", "max_meta_steps", "pretrain_steps", "determinism_reruns"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise M5RunnerError(f"{name} 必须是正整数，实际 {value!r}")
        if self.meta_train_tasks < 2:
            raise M5RunnerError("meta_train_tasks 至少为 2（MAML 需要多任务批）")
        if self.physical_guard_expected != 0:
            raise M5RunnerError("physical_guard_expected 必须为 0（P4-CODE 硬隔离）")
        budgets = tuple(int(value) for value in self.budgets)
        if not budgets or min(budgets) < M5_INITIAL_DESIGN_COUNT:
            raise M5RunnerError(f"budgets 必须都 >= {M5_INITIAL_DESIGN_COUNT}，实际 {budgets!r}")
        if len(set(budgets)) != len(budgets):
            raise M5RunnerError("budgets 不允许重复")
        object.__setattr__(self, "budgets", tuple(sorted(budgets)))
        seeds = tuple(int(value) for value in self.optimization_seeds)
        if not seeds or len(set(seeds)) != len(seeds):
            raise M5RunnerError("optimization_seeds 必须互异且非空")
        object.__setattr__(self, "optimization_seeds", seeds)
        meta_seeds = tuple(int(value) for value in self.meta_seeds)
        if not meta_seeds or len(set(meta_seeds)) != len(meta_seeds):
            raise M5RunnerError("meta_seeds 必须互异且非空")
        object.__setattr__(self, "meta_seeds", meta_seeds)
        for name in ("calibration_report_path", "frozen_family_path", "preregistration_path", "split_manifest_path"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, Path(value))
        if not isinstance(self.calibration, fv2.CalibrationConfig):
            raise M5RunnerError("calibration 必须是 fv2.CalibrationConfig")

    @property
    def run_dir(self) -> Path:
        return self.output_root / self.run_id

    @property
    def designs_per_task(self) -> int:
        return self.support_pool_size + self.query_size

    @property
    def study_scale(self) -> str:
        """规模判定：只有正式规模才允许用于论文结论。"""
        formal = (
            set((64, 128)).issubset(set(self.budgets))
            and len(self.optimization_seeds) >= 10
            and len(self.meta_seeds) >= 3
            and self.meta_test_tasks >= 20
            and self.ood_tasks >= 10
            and self.meta_train_tasks >= 60
            and self.meta_validation_tasks >= 20
            and self.max_meta_steps >= 200
        )
        return "FORMAL" if formal else "SMOKE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "stage": self.stage,
            "output_root": str(self.output_root),
            "family_seed": self.family_seed,
            "split_counts": {
                "meta_train": self.meta_train_tasks,
                "meta_validation": self.meta_validation_tasks,
                "meta_test": self.meta_test_tasks,
                "meta_test_ood": self.ood_tasks,
                "negative_control": self.negative_control_tasks,
            },
            "support_pool_size": self.support_pool_size,
            "query_size": self.query_size,
            "designs_per_task": self.designs_per_task,
            "budgets": list(self.budgets),
            "optimization_seeds": list(self.optimization_seeds),
            "meta_seeds": list(self.meta_seeds),
            "max_meta_steps": self.max_meta_steps,
            "pretrain_steps": self.pretrain_steps,
            "determinism_reruns": self.determinism_reruns,
            "physical_guard_expected": self.physical_guard_expected,
            "calibration": self.calibration.to_dict(),
            "study_scale": self.study_scale,
            "conclusions_allowed": self.study_scale == "FORMAL",
        }

    def path_or(self, value: Path | None, default: Path) -> Path:
        return Path(value) if value is not None else default


def build_v2_family_config(config: M5RunnerConfig, radius_base: float) -> tf.TaskFamilyConfig:
    """按冻结半径构造正式 v2 任务族配置（五 split 完整规模；不用于校准）。"""
    return tf.TaskFamilyConfig(
        family_id=tf.V2_FAMILY_ID,
        design_dim=tf.DESIGN_DIM,
        context_names=tf.CONTEXT_NAMES,
        seed=int(config.family_seed),
        train_tasks=int(config.meta_train_tasks),
        validation_tasks=int(config.meta_validation_tasks),
        test_tasks=int(config.meta_test_tasks),
        ood_tasks=int(config.ood_tasks),
        negative_control_tasks=int(config.negative_control_tasks),
        designs_per_task=int(config.designs_per_task),
        support_pool_size=int(config.support_pool_size),
        query_size=int(config.query_size),
        family_version="v2",
        radius_base=float(radius_base),
    )


def _check_physical_guard(result: Any, *, label: str) -> None:
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    reported = payload.get("physical_call_count") if isinstance(payload, Mapping) else None
    if reported != PHYSICAL_CALL_COUNT:
        raise PhysicsGuardViolation(
            f"{label} 报告 physical_call_count={reported!r}，立即中止整次 run",
            physical_call_count=int(reported or 1),
        )


def feasible_expected_zero(task: Any) -> bool | None:
    """任务在解析几何下可行域体积是否接近 0（仅用于避免把 null 误读为 0）。"""
    params = getattr(task, "params", {}) or {}
    radius = params.get("r")
    weights = params.get("w")
    if radius is None or weights is None:
        return None
    try:
        fraction = fv2.analytic_ellipsoid_fraction(float(radius), weights)
    except Exception:  # 负控制/异常参数不强行推断
        return None
    return bool(fraction <= 0.01)


def fallback_metrics(result: Any) -> dict[str, Any]:
    """A7 fallback 指标：仅用于失败/无可行解场景的描述，不得冒充约束优化更优。"""
    observations = list(getattr(result, "observations", ()) or ())
    valid = [item for item in observations if item.objective is not None]
    best_raw = None
    violation = None
    if valid:
        chosen = min(valid, key=lambda item: float(item.objective))
        best_raw = float(chosen.objective)
        if chosen.constraints:
            violation = float(
                sum(max(0.0, float(value)) for value in chosen.constraints.values())
            )
    true_evals = int(getattr(result, "true_evals_used", 0))
    feasible_count = int(getattr(result, "feasible_count", 0))
    hit_rate = (feasible_count / true_evals) if true_evals else None
    nulls = sum(1 for item in observations if item.objective is None)
    return {
        "best_objective_raw": best_raw,
        "min_constraint_violation_sum": violation,
        "feasible_hit_rate": hit_rate,
        "null_rate": (nulls / len(observations)) if observations else None,
    }


def history_rows_for_result(
    result: Any,
    *,
    run_id: str,
    meta_seed: int | None,
) -> list[dict[str, Any]]:
    """把 ArmResult 的逐次评价展开为 optimization_history.csv 行（含 budget/meta_seed）。"""
    rows: list[dict[str, Any]] = []
    best_feasible: float | None = None
    best_value: float | None = None
    for observation in result.observations:
        if observation.feasible and observation.objective is not None:
            candidate = float(observation.objective)
            best_feasible = candidate if best_feasible is None else min(best_feasible, candidate)
        if observation.objective is not None:
            candidate = float(observation.objective)
            best_value = candidate if best_value is None else min(best_value, candidate)
        row = observation.to_history_row(
            run_id=run_id,
            task_id=result.task_id,
            split=result.split,
            family=result.family,
            arm=result.arm,
            seed=int(result.seed),
            wall_s=float(getattr(result, "wall_s", 0.0)),
            best_feasible_so_far=best_feasible,
            best_value_so_far=best_value,
        )
        row["budget"] = int(result.budget)
        row["meta_seed"] = None if meta_seed is None else int(meta_seed)
        row["best_objective_so_far"] = best_value
        row["initial_design"] = bool(observation.eval_index <= M5_INITIAL_DESIGN_COUNT)
        rows.append(row)
    return rows


def summary_row_for_result(
    result: Any,
    *,
    run_id: str,
    meta_seed: int | None,
    initializer: str,
    task: Any,
) -> dict[str, Any]:
    row = result.to_summary_row(run_id=run_id)
    row.update(
        {
            "budget": int(result.budget),
            "meta_seed": None if meta_seed is None else int(meta_seed),
            "initializer": initializer,
            "implementation": result.implementation,
            "requested_evaluations": int(result.requested_evaluations),
            "initial_feasible_count": int(result.initial_feasible_count),
            "reference_objective": result.reference_objective,
            "proxy_scoring_cost_json": _json_text(dict(result.proxy_scoring_cost or {})),
            "physical_call_count": PHYSICAL_CALL_COUNT,
        }
    )
    row.update(fallback_metrics(result))
    row["feasibility_expected_zero"] = feasible_expected_zero(task)
    return row


def _json_text(payload: Any) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _json_default(value: Any) -> Any:
    """规范 JSON 序列化默认值（仅用于确定性行摘要，不参与数值结论）。"""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    raise TypeError(f"无法序列化类型 {type(value).__name__}")


def _median(values: Sequence[float]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return float(np.median(finite)) if finite else None


def _mean(values: Sequence[float]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return float(np.mean(finite)) if finite else None


def _std(values: Sequence[float]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return float(np.std(finite, ddof=1)) if len(finite) >= 2 else None
# ---------------------------------------------------------------------------
# 阶段通用产物：run_config.json / environment.json / README.md / summary.json /
# data_manifest.json（每个阶段结束都重算 manifest，覆盖此前阶段产物）
# ---------------------------------------------------------------------------
SYNTHETIC_EVALUATOR_ID = "synthetic__analytic__12d_lifting_surfaces__v2"
M5_STATISTICS_PLAN = dict(fv2.STATISTICS_PLAN)


def _base_run_config(config: M5RunnerConfig, *, stage: str, git_state: Mapping[str, Any]) -> dict[str, Any]:
    """构造所有阶段共享的 run_config.json 主体（不含阶段私有字段）。"""
    return {
        "schema_version": STAGE_VERSION,
        "stage": stage,
        "stage_sequence": list(STAGES),
        "run_id": config.run_id,
        "created_utc": iso_utc(),
        "study_scale": config.study_scale,
        "conclusions_allowed": config.study_scale == "FORMAL",
        "git_sha": git_state.get("git_sha"),
        "git_sha_label": git_state.get("git_sha_label"),
        "worktree_dirty": git_state.get("worktree_dirty"),
        "data_origin": "SYNTHETIC_TEST",
        "stage_label": STAGE,
        "family": {
            "family_id": tf.V2_FAMILY_ID,
            "family_version": "v2",
            "family_seed": int(config.family_seed),
            "design_set": DESIGN_SET,
            "design_dim": tf.DESIGN_DIM,
            "design_config_path": str(DESIGN_SPACE_CONFIG),
            "support_pool_size": int(config.support_pool_size),
            "query_size": int(config.query_size),
            "designs_per_task": int(config.designs_per_task),
        },
        "split_counts": {
            "meta_train": int(config.meta_train_tasks),
            "meta_validation": int(config.meta_validation_tasks),
            "meta_test": int(config.meta_test_tasks),
            "meta_test_ood": int(config.ood_tasks),
            "negative_control": int(config.negative_control_tasks),
        },
        "budgets": {"true_evaluation_budget": list(config.budgets)},
        "optimization_seeds": list(config.optimization_seeds),
        "meta_seeds": list(config.meta_seeds),
        "max_meta_steps": int(config.max_meta_steps),
        "pretrain_steps": int(config.pretrain_steps),
        "determinism_reruns": int(config.determinism_reruns),
        "calibration_protocol": config.calibration.to_dict(),
        "calibration_selection_rule": fv2.SELECTION_RULE,
        "tolerance": {"feasibility_g_le_zero": float(tf.REFERENCE_ABS_TOL)},
        "primary_endpoints": list(PRIMARY_ENDPOINTS),
        "secondary_endpoints": list(SECONDARY_ENDPOINTS),
        "fallback_endpoints": list(FALLBACK_ENDPOINTS),
        "endpoint_directions": dict(ENDPOINT_DIRECTIONS),
        "preregistered_comparisons": [list(pair) for pair in PREREGISTERED_COMPARISONS],
        "statistics": dict(M5_STATISTICS_PLAN),
        "reference_solution": fv2.REFERENCE_SOLUTION,
        "gap_definition": fv2.GAP_DEFINITION,
        "null_policy": fv2.NULL_POLICY,
        "meta_test_tuning_policy": fv2.META_TEST_TUNING_POLICY,
        "evaluator_id": SYNTHETIC_EVALUATOR_ID,
        "implementation": {
            "runner": "research.concorde_metaopt.meta_learning.m5_runner",
            "arms": "research.concorde_metaopt.meta_learning.m5_arms",
            "bo_engine": "maml_opt.bayesian:ConstrainedBayesianOptimizer/run_search",
            "de_engine": "reuse_semantics:research.concorde_metaopt.optimization.baseline_de:DifferentialEvolutionBaseline",
            "initialization": "maml_opt.initialization:select_model_scored_initial_designs",
        },
        "physical_call_declaration": {
            "expected": int(config.physical_guard_expected),
            "stage": STAGE,
            "policy": "fail-closed：任何报告 physical_call_count!=0 立即中止整次 run",
            "data_origin": "SYNTHETIC_TEST",
        },
        "non_claims": list(fv2.NON_CLAIMS),
        "not_approved": [
            "P4-REAL-LF 真实低可信度求解器调用（未批准）",
            "P4-MULTIFIDELITY-REAL 真实多保真（未批准）",
            "真实跨任务元训练（未批准）",
        ],
    }


def _running_commands(config: M5RunnerConfig) -> list[str]:
    base = "D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m research.concorde_metaopt.meta_learning.m5_runner"
    common = f"--run-id {config.run_id} --output-root {Path(config.output_root).as_posix()}"
    return [f"{base} --stage {stage} {common}" for stage in STAGES]


def _render_readme(
    config: M5RunnerConfig,
    *,
    stage: str,
    summary: Mapping[str, Any],
    products: Sequence[str],
    run_config: Mapping[str, Any],
) -> str:
    lines = [
        f"# P4-M5 离线合成实验 run（stage={stage}）",
        "",
        f"- run_id：`{config.run_id}`",
        f"- 阶段：{stage}（完整流程 calibration → freeze → holdout）",
        f"- 数据来源：**SYNTHETIC_ONLY**（解析合成任务族 F-QE-feasible-v2 + 12D 设计空间解析 evaluator）",
        f"- 物理调用：physical_call_count={PHYSICAL_CALL_COUNT}（fail-closed 守卫，真实求解器调用 0 次）",
        f"- 规模判定：{config.study_scale}（仅 FORMAL 允许用于论文结论）",
        f"- 任务族：`{tf.V2_FAMILY_ID}`（family_version=v2）；split={dict(run_config.get('split_counts', {}))}",
        f"- 预算：true_evaluation_budget={list(config.budgets)}（每臂每 run 恰好消耗预算）",
        f"- 优化 seeds：{list(config.optimization_seeds)}；元训练 seeds：{list(config.meta_seeds)}",
        f"- 参考解：u*=c（解析认证），gap={fv2.GAP_DEFINITION}",
        "",
        "## 本阶段结果",
        "",
        f"- status：`{summary.get('status')}`",
    ]
    for key in (
        "selected_radius_base",
        "selection_status",
        "frozen_family_sha256",
        "preregistration_sha256",
        "split_hash",
        "arms_evaluated",
        "runs_completed",
        "true_evaluations",
        "determinism_status",
    ):
        if key in summary:
            lines.append(f"- {key}：`{summary.get(key)}`")
    lines += [
        "",
        "## 产物",
        "",
    ]
    lines += [f"- `{name}`" for name in products]
    lines += [
        "",
        "## 边界与非声明",
        "",
        "- 本 run 只调用解析合成 evaluator；不调用 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器，不访问网络。",
        "- 不伪造数据：无可行解保留 null 并计入预算；失败评价如实记录 status，不以惩罚常数冒充失败代价。",
        "- 图 fig1–fig5 由 A2/M5 报告阶段从本 run 的 CSV 生成；fig6 归 Issue #4 D-12D-004（VSPAERO/RCAIDE 回退气动），本阶段不生成。",
        "- 旧 F-QE 压力测试（~1e-6 可行域）结果单独成表，不与 v2 混算绝对目标。",
        "",
        "## 复现命令",
        "",
    ]
    lines += [f"- `{command}`" for command in _running_commands(config)]
    return "\n".join(lines) + "\n"


def _write_stage_products(
    run_dir: Path,
    config: M5RunnerConfig,
    *,
    stage: str,
    run_config: Mapping[str, Any],
    summary: Mapping[str, Any],
    products: Sequence[str],
) -> list[str]:
    """写 run_config/environment/README/summary/data_manifest 并返回最终产物清单。"""
    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "run_config.json", dict(run_config))
    write_json(root / "environment.json", environment_payload(config.run_id, PHYSICAL_CALL_COUNT))
    summary_payload = dict(summary)
    summary_payload.setdefault("run_id", config.run_id)
    summary_payload.setdefault("stage", stage)
    summary_payload.setdefault("study_scale", config.study_scale)
    summary_payload.setdefault("data_origin", "SYNTHETIC_TEST")
    summary_payload.setdefault("physical_call_count", PHYSICAL_CALL_COUNT)
    summary_payload.setdefault(
        "physics_guard", {"expected": 0, "status": "PASS", "message": "全程 0 次真实求解器调用"}
    )
    summary_payload["products_written"] = sorted(set(products) | {"summary.json", "README.md", "data_manifest.json"})
    write_json(root / "summary.json", summary_payload)
    readme = _render_readme(
        config,
        stage=stage,
        summary=summary_payload,
        products=summary_payload["products_written"],
        run_config=run_config,
    )
    (root / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    manifest = build_data_manifest(root)
    write_json(root / "data_manifest.json", manifest)
    return list(summary_payload["products_written"])


def _write_stage_failure(
    run_dir: Path,
    config: M5RunnerConfig,
    *,
    stage: str,
    status: str,
    error: BaseException,
) -> dict[str, Any]:
    """阶段失败时只写 summary.json（不写伪造的正常产物）。"""
    import traceback

    root = Path(run_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": config.run_id,
        "stage": stage,
        "study_scale": config.study_scale,
        "status": status,
        "data_origin": "SYNTHETIC_TEST",
        "physical_call_count": (
            None
            if status != "PHYSICS_GUARD_VIOLATION"
            else int(getattr(error, "physical_call_count", 1) or 1)
        ),
        "physics_guard": {
            "expected": 0,
            "status": "VIOLATED" if status == "PHYSICS_GUARD_VIOLATION" else "UNKNOWN",
            "message": str(error),
        },
        "error": {"type": type(error).__name__, "message": str(error)},
        "traceback_summary": traceback.format_exception(type(error), error, error.__traceback__)[-1].strip(),
        "products_written": ["summary.json"],
    }
    write_json(root / "summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# 校准报告读取（holdout/freeze 阶段需要复算 sha256 做门禁）
# ---------------------------------------------------------------------------
def _calibration_config_from_payload(payload: Mapping[str, Any]) -> fv2.CalibrationConfig:
    data = dict(payload)
    data["radius_grid"] = tuple(float(value) for value in data["radius_grid"])
    data["opt_seeds"] = tuple(int(value) for value in data["opt_seeds"])
    return fv2.CalibrationConfig(**data)


def _calibration_row_from_payload(payload: Mapping[str, Any]) -> fv2.CalibrationTaskRow:
    data = dict(payload)
    if data.get("first_feasible_eval_index") is not None:
        data["first_feasible_eval_index"] = int(data["first_feasible_eval_index"])
    for name in ("best_feasible_value", "best_objective_raw", "min_constraint_violation_sum", "wall_s"):
        if data.get(name) is not None:
            data[name] = float(data[name])
    for name in ("feasible_count", "n_null", "evaluations", "opt_seed"):
        data[name] = int(data[name])
    data["success"] = bool(data["success"])
    data["radius_base"] = float(data["radius_base"])
    return fv2.CalibrationTaskRow(**data)


def _calibration_cell_from_payload(payload: Mapping[str, Any]) -> fv2.CalibrationCell:
    data = dict(payload)
    data["success_rate_by_seed"] = tuple(float(value) for value in data["success_rate_by_seed"])
    data["feasible_hit_rate_by_seed"] = tuple(float(value) for value in data["feasible_hit_rate_by_seed"])
    for name in ("n_tasks", "budget", "evaluations", "n_null"):
        data[name] = int(data[name])
    for name in (
        "radius_base",
        "success_rate_median",
        "feasible_hit_rate_median",
        "pooled_success_train",
        "pooled_hit_rate_train",
        "validation_success_rate_median",
        "analytic_sphere_fraction",
        "analytic_ellipsoid_fraction_median",
        "feasible_volume_fraction",
        "wall_s",
    ):
        data[name] = float(data[name])
    data["all_seeds_in_acceptance"] = bool(data["all_seeds_in_acceptance"])
    return fv2.CalibrationCell(**data)


def load_calibration_report(path: str | Path) -> fv2.CalibrationReport:
    """从 calibration_report.json 还原 CalibrationReport（字段完整，缺项即 fail-closed）。"""
    import json

    target = Path(path)
    if not target.is_file():
        raise M5RunnerError(f"校准报告不存在：{target}")
    payload = json.loads(target.read_text(encoding="utf-8"))
    try:
        report = fv2.CalibrationReport(
            schema_version=str(payload["schema_version"]),
            created_utc=str(payload["created_utc"]),
            calibration=_calibration_config_from_payload(payload["calibration"]),
            cells=tuple(_calibration_cell_from_payload(item) for item in payload.get("cells", [])),
            rows=tuple(_calibration_row_from_payload(item) for item in payload.get("task_rows", [])),
            cohorts=tuple(dict(item) for item in payload.get("cohorts", [])),
            reference_certificates=tuple(dict(item) for item in payload.get("reference_certificates", [])),
            selected_radius_base=(
                None if payload.get("selected_radius_base") is None else float(payload["selected_radius_base"])
            ),
            selection_status=str(payload["selection_status"]),
            selection_rule=str(payload["selection_rule"]),
            notes=tuple(str(item) for item in payload.get("notes", [])),
            physical_call_count=int(payload.get("physical_call_count", 0)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise M5RunnerError(f"校准报告结构非法：{type(error).__name__}: {error}") from error
    if report.physical_call_count != PHYSICAL_CALL_COUNT:
        raise PhysicsGuardViolation(
            f"校准报告报告 physical_call_count={report.physical_call_count}，立即中止",
            physical_call_count=int(report.physical_call_count),
        )
    return report


def resolve_calibration_report_path(config: M5RunnerConfig) -> Path:
    """定位校准报告：显式路径优先，否则 run_dir/calibration/calibration_report.json。"""
    return config.path_or(
        config.calibration_report_path,
        config.run_dir / "calibration" / "calibration_report.json",
    )


# ---------------------------------------------------------------------------
# stage=calibration
# ---------------------------------------------------------------------------
def run_calibration_stage(
    config: M5RunnerConfig,
    *,
    design_space: Any | None = None,
    calibration_report: fv2.CalibrationReport | None = None,
    progress: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """校准阶段：只在 meta_train/meta_validation 上选半径并落盘报告。"""
    if config.stage != "calibration":
        raise M5RunnerError(f"run_calibration_stage 需要 stage='calibration'，实际 {config.stage!r}")
    started = time.perf_counter()
    guard_baseline = _forbidden_modules_present()
    try:
        assert_no_forbidden_modules(guard_baseline)
        space = design_space if design_space is not None else load_design_space_12d()
        if calibration_report is None:
            report = fv2.calibrate_radius_base(config.calibration, design_space=space, progress=progress)
        else:
            report = calibration_report
        if report.physical_call_count != PHYSICAL_CALL_COUNT:
            raise PhysicsGuardViolation(
                f"校准报告 physical_call_count={report.physical_call_count}",
                physical_call_count=int(report.physical_call_count),
            )
        runtime_s = float(time.perf_counter() - started)
        run_dir = config.run_dir
        calibration_dir = run_dir / "calibration"
        written = fv2.write_calibration_report(calibration_dir, report)
        evidence = {
            "schema_version": "p4-m5-calibration-evidence-1",
            "stage": STAGE,
            "run_id": config.run_id,
            "physical_call_count": PHYSICAL_CALL_COUNT,
            "calibration_config": config.calibration.to_dict(),
            "selected_radius_base": report.selected_radius_base,
            "selection_status": report.selection_status,
            "calibration_report_sha256": report.sha256,
            "cells": [
                {
                    "radius_base": cell.radius_base,
                    "success_rate_by_seed": list(cell.success_rate_by_seed),
                    "feasible_hit_rate_by_seed": list(cell.feasible_hit_rate_by_seed),
                    "pooled_success_train": cell.pooled_success_train,
                    "pooled_hit_rate_train": cell.pooled_hit_rate_train,
                    "validation_success_rate_median": cell.validation_success_rate_median,
                    "all_seeds_in_acceptance": cell.all_seeds_in_acceptance,
                    "analytic_sphere_fraction": cell.analytic_sphere_fraction,
                    "analytic_ellipsoid_fraction_median": cell.analytic_ellipsoid_fraction_median,
                    "feasible_volume_fraction": cell.feasible_volume_fraction,
                }
                for cell in report.cells
            ],
            "selection_rule": report.selection_rule,
            "notes": list(report.notes),
            "runtime_s": runtime_s,
        }
        evidence_path = write_json(calibration_dir / "calibration_evidence.json", evidence)
        assert_no_forbidden_modules(guard_baseline)
        git_state = repo_git_state(REPO_ROOT)
        status = "CALIBRATED" if report.selected_radius_base is not None else "NO_CELL_IN_TARGET"
        summary = {
            "status": status,
            "selected_radius_base": report.selected_radius_base,
            "selection_status": report.selection_status,
            "calibration_report_sha256": report.sha256,
            "calibration_cells": len(report.cells),
            "calibration_runs": len(report.rows),
            "runtime_s": runtime_s,
            "physics_guard": {"expected": 0, "status": "PASS", "message": "校准阶段 0 次物理调用"},
            "notes": list(report.notes),
        }
        if status == "NO_CELL_IN_TARGET":
            summary["blocking"] = (
                "校准无 pooled success∈[0.30,0.70] 的半径格；按计划 §10-R1 需 Lead 裁决"
                "（可扩半径网格/试 v2a/如实 INCONCLUSIVE），禁止用测试集调参。"
            )
        run_config = _base_run_config(config, stage=config.stage, git_state=git_state)
        run_config.update(
            {
                "calibration": {
                    "report_sha256": report.sha256,
                    "report_json": written["json"],
                    "report_csv": written["tasks_csv"],
                    "cells_csv": written["cells_csv"],
                    "evidence_json": str(evidence_path),
                    "selected_radius_base": report.selected_radius_base,
                    "selection_status": report.selection_status,
                    "selection_rule": report.selection_rule,
                    "runtime_s": runtime_s,
                }
            }
        )
        products = [
            "calibration/calibration_report.json",
            "calibration/calibration_report.csv",
            "calibration/calibration_cells.csv",
            "calibration/calibration_evidence.json",
            "run_config.json",
            "environment.json",
            "summary.json",
            "README.md",
            "data_manifest.json",
        ]
        products = _write_stage_products(
            run_dir, config, stage=config.stage, run_config=run_config, summary=summary, products=products
        )
        return {
            "status": status,
            "stage": config.stage,
            "run_dir": str(run_dir),
            "calibration_report": report,
            "summary": summary,
            "products_written": products,
        }
    except (PhysicsGuardViolation, M5RunnerError, fv2.FeasibleV2Error, tf.TaskFamilyError) as error:
        status = "PHYSICS_GUARD_VIOLATION" if isinstance(error, PhysicsGuardViolation) else "FAILED"
        summary = _write_stage_failure(config.run_dir, config, stage=config.stage, status=status, error=error)
        return {
            "status": status,
            "stage": config.stage,
            "run_dir": str(config.run_dir),
            "calibration_report": None,
            "summary": summary,
            "products_written": ["summary.json"],
            "error": summary["error"],
        }


# ---------------------------------------------------------------------------
# stage=freeze
# ---------------------------------------------------------------------------
def _tasks_payload(tasks: Sequence[tf.SyntheticTask], family_config: tf.TaskFamilyConfig) -> dict[str, Any]:
    split_assignments: dict[str, list[str]] = {
        split: [] for split in ("meta_train", "meta_validation", "meta_test", "meta_test_ood", "negative_control")
    }
    for task in tasks:
        split_assignments.setdefault(task.split, []).append(task.task_id)
    for value in split_assignments.values():
        value.sort()
    return {
        "schema_version": "p4-m5-tasks-1",
        "family_id": family_config.family_id,
        "family_version": family_config.family_version,
        "radius_base": family_config.radius_base,
        "family_fingerprint": tf.family_fingerprint(family_config),
        "split_assignments": split_assignments,
        "tasks": [tf.serialize_task(task) for task in tasks],
    }


def reference_solutions_payload(tasks: Sequence[tf.SyntheticTask]) -> dict[str, Any]:
    """参考解台账（负控制无解析参考解，显式排除并说明）。"""
    solutions: dict[str, Any] = {}
    for task in tasks:
        if task.is_negative_control:
            continue
        reference = task.reference()
        solutions[task.task_id] = {
            "split": task.split,
            "family": task.family,
            "u_star": [float(value) for value in np.asarray(reference["u_star"], dtype=float)],
            "objective_star": float(reference["objective_star"]),
            "reference_kind": str(reference.get("reference_kind", "")),
            "assertion_residual": float(reference.get("assertion_residual", 0.0)),
            "constraints": {name: float(value) for name, value in dict(reference.get("constraints", {})).items()},
            "feasible": bool(reference.get("feasible", True)),
        }
    return {
        "schema_version": "p4-m5-reference-solutions-1",
        "reference_solution": fv2.REFERENCE_SOLUTION,
        "gap_definition": fv2.GAP_DEFINITION,
        "residual_tolerance": float(tf.REFERENCE_ABS_TOL),
        "negative_control_excluded": True,
        "note": "负控制任务由打乱标签派生，无解析参考解；其参考解断言不适用。",
        "solutions": solutions,
    }


def run_freeze_stage(
    config: M5RunnerConfig,
    *,
    calibration_report: fv2.CalibrationReport | None = None,
    design_space: Any | None = None,
) -> dict[str, Any]:
    """冻结阶段：选定半径 → 构造五 split 任务族 → split manifest → frozen → preregistration。"""
    if config.stage != "freeze":
        raise M5RunnerError(f"run_freeze_stage 需要 stage='freeze'，实际 {config.stage!r}")
    started = time.perf_counter()
    guard_baseline = _forbidden_modules_present()
    try:
        assert_no_forbidden_modules(guard_baseline)
        report = calibration_report
        if report is None:
            report = load_calibration_report(resolve_calibration_report_path(config))
        if report.selected_radius_base is None:
            summary = {
                "status": "NO_CELL_IN_TARGET",
                "selection_status": report.selection_status,
                "calibration_report_sha256": report.sha256,
                "physical_call_count": PHYSICAL_CALL_COUNT,
                "physics_guard": {"expected": 0, "status": "PASS", "message": "冻结前中止：校准未选出半径"},
                "blocking": "校准未选出半径，禁止构造/冻结 holdout 任务族；按计划 §10-R1 需 Lead 裁决。",
            }
            git_state = repo_git_state(REPO_ROOT)
            run_config = _base_run_config(config, stage=config.stage, git_state=git_state)
            run_config["calibration"] = {
                "report_sha256": report.sha256,
                "selection_status": report.selection_status,
            }
            products = _write_stage_products(
                config.run_dir,
                config,
                stage=config.stage,
                run_config=run_config,
                summary=summary,
                products=["run_config.json", "environment.json", "summary.json", "README.md", "data_manifest.json"],
            )
            return {
                "status": "NO_CELL_IN_TARGET",
                "stage": config.stage,
                "run_dir": str(config.run_dir),
                "frozen_family": None,
                "preregistration": None,
                "summary": summary,
                "products_written": products,
            }
        radius = float(report.selected_radius_base)
        family_config = build_v2_family_config(config, radius)
        tasks = tf.build_task_family(family_config)
        expected_tasks = (
            config.meta_train_tasks
            + config.meta_validation_tasks
            + config.meta_test_tasks
            + config.ood_tasks
            + config.negative_control_tasks
        )
        if len(tasks) != expected_tasks:
            raise M5RunnerError(f"任务族任务数 {len(tasks)} 与配置 split 总和 {expected_tasks} 不符")
        split_manifest = fv2.build_split_manifest(tasks, family_config=family_config)
        fv2.verify_split_manifest(split_manifest, tasks=tasks, family_config=family_config)
        certificates = fv2.assert_reference_certificates([task for task in tasks if not task.is_negative_control])
        space = design_space if design_space is not None else load_design_space_12d()
        git_state = repo_git_state(REPO_ROOT)
        frozen = fv2.build_frozen_family(
            family_config,
            split_manifest=split_manifest,
            calibration_report=report,
            run_id=config.run_id,
            git_sha=str(git_state["git_sha_label"]),
            design_space=space,
        )
        preregistration = fv2.build_preregistration(
            frozen,
            run_id=config.run_id,
            budgets=config.budgets,
            optimization_seeds=config.optimization_seeds,
            meta_seeds=config.meta_seeds,
        )
        fv2.verify_preregistration(preregistration, frozen)
        run_dir = config.run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        split_path = write_json(run_dir / "meta_task_split.json", split_manifest)
        frozen_path = fv2.write_frozen_family(run_dir / "frozen_family.json", frozen)
        prereg_path = fv2.write_preregistration(run_dir / "preregistration.json", preregistration, frozen)
        tasks_path = write_json(run_dir / "tasks.json", _tasks_payload(tasks, family_config))
        solutions_path = write_json(run_dir / "reference_solutions.json", reference_solutions_payload(tasks))
        runtime_s = float(time.perf_counter() - started)
        assert_no_forbidden_modules(guard_baseline)
        summary = {
            "status": "FROZEN",
            "frozen_family_sha256": frozen["sha256"],
            "preregistration_sha256": preregistration["sha256"],
            "split_hash": split_manifest["split_hash"],
            "selected_radius_base": radius,
            "family_id": frozen["family_id"],
            "family_version": frozen["family_version"],
            "family_fingerprint": frozen["family_fingerprint"],
            "split_counts": dict(split_manifest["counts"]),
            "reference_certificates": len(certificates),
            "runtime_s": runtime_s,
            "physical_call_count": PHYSICAL_CALL_COUNT,
            "physics_guard": {"expected": 0, "status": "PASS", "message": "冻结阶段 0 次物理调用"},
            "meta_test_tuning_policy": fv2.META_TEST_TUNING_POLICY,
            "products": {
                "meta_task_split": str(split_path),
                "frozen_family": str(frozen_path),
                "preregistration": str(prereg_path),
                "tasks": str(tasks_path),
                "reference_solutions": str(solutions_path),
            },
        }
        run_config = _base_run_config(config, stage=config.stage, git_state=git_state)
        run_config.update(
            {
                "calibration": {"report_sha256": report.sha256, "selected_radius_base": radius},
                "frozen_family": {
                    "sha256": frozen["sha256"],
                    "family_id": frozen["family_id"],
                    "family_version": frozen["family_version"],
                    "family_fingerprint": frozen["family_fingerprint"],
                    "radius_base": radius,
                    "radius_mapping": dict(frozen["radius_mapping"]),
                    "reference_solution": frozen["reference_solution"],
                    "gap_definition": frozen["gap_definition"],
                },
                "split": {
                    "manifest_sha256": fv2.digest(split_manifest),
                    "split_hash": split_manifest["split_hash"],
                    "counts": dict(split_manifest["counts"]),
                },
                "preregistration": {
                    "sha256": preregistration["sha256"],
                    "arms": list(preregistration["arms"]),
                    "budgets": list(preregistration["budgets"]),
                    "optimization_seeds": list(preregistration["optimization_seeds"]),
                    "meta_seeds": list(preregistration["meta_seeds"]),
                },
            }
        )
        products = [
            "meta_task_split.json",
            "frozen_family.json",
            "preregistration.json",
            "tasks.json",
            "reference_solutions.json",
            "run_config.json",
            "environment.json",
            "summary.json",
            "README.md",
            "data_manifest.json",
        ]
        products = _write_stage_products(
            run_dir, config, stage=config.stage, run_config=run_config, summary=summary, products=products
        )
        return {
            "status": "FROZEN",
            "stage": config.stage,
            "run_dir": str(run_dir),
            "frozen_family": frozen,
            "preregistration": preregistration,
            "split_manifest": split_manifest,
            "family_config": family_config,
            "tasks": tasks,
            "summary": summary,
            "products_written": products,
        }
    except (PhysicsGuardViolation, M5RunnerError, fv2.FeasibleV2Error, tf.TaskFamilyError) as error:
        status = "PHYSICS_GUARD_VIOLATION" if isinstance(error, PhysicsGuardViolation) else "FAILED"
        summary = _write_stage_failure(config.run_dir, config, stage=config.stage, status=status, error=error)
        return {
            "status": status,
            "stage": config.stage,
            "run_dir": str(config.run_dir),
            "frozen_family": None,
            "preregistration": None,
            "summary": summary,
            "products_written": ["summary.json"],
            "error": summary["error"],
        }


# ---------------------------------------------------------------------------
# holdout 前置：加载并校验 calibration/frozen/split/preregistration 四方一致
# ---------------------------------------------------------------------------
def load_holdout_prerequisites(config: M5RunnerConfig) -> dict[str, Any]:
    """holdout 入口：任何缺失/hash 不符立即 fail-closed（禁止构造测试集）。"""
    import json

    report_path = resolve_calibration_report_path(config)
    frozen_path = config.path_or(config.frozen_family_path, config.run_dir / "frozen_family.json")
    split_path = config.path_or(config.split_manifest_path, config.run_dir / "meta_task_split.json")
    prereg_path = config.path_or(config.preregistration_path, config.run_dir / "preregistration.json")
    for path, name in (
        (report_path, "校准报告"),
        (frozen_path, "frozen_family"),
        (split_path, "meta_task_split"),
        (prereg_path, "preregistration"),
    ):
        if not Path(path).is_file():
            raise PreregistrationNotFrozen(
                f"holdout 前置缺失{name}（{path}）：必须先完成 calibration + freeze 阶段"
            )
    report = load_calibration_report(report_path)
    frozen = fv2.load_frozen_family(frozen_path)
    split_manifest = json.loads(Path(split_path).read_text(encoding="utf-8"))
    preregistration = fv2.load_preregistration(prereg_path)
    unlocked = fv2.assert_holdout_unlocked(
        frozen_family=frozen,
        preregistration=preregistration,
        split_manifest=split_manifest,
        calibration_report=report,
    )
    family_config = fv2.frozen_to_config(frozen)
    return {
        "status": unlocked["status"],
        "unlocked": unlocked,
        "calibration_report": report,
        "frozen_family": frozen,
        "split_manifest": split_manifest,
        "preregistration": preregistration,
        "family_config": family_config,
        "radius_base": float(frozen["radius_base"]),
        "paths": {
            "calibration_report": str(report_path),
            "frozen_family": str(frozen_path),
            "split_manifest": str(split_path),
            "preregistration": str(prereg_path),
        },
    }
# ---------------------------------------------------------------------------
# holdout：单组（task × 优化 seed）执行（可串行，也可经 spawn 进程池并行）
# ---------------------------------------------------------------------------
MODEL_SCORED_ARMS = (M5_BO_PRETRAIN_INIT, M5_BO_MAML_INIT)
MODEL_ARTIFACT_KEYS = {M5_BO_PRETRAIN_INIT: "pretrain", M5_BO_MAML_INIT: "maml"}
VOLATILE_ROW_KEYS = ("wall_s", "proxy_scoring_cost_json")
ENDPOINT_UNITS = {
    "best_feasible_value": "synthetic_objective_unit",
    "gap_to_reference": "synthetic_objective_unit",
    "first_feasible_evaluation_index": "evaluation_index_1based",
    "feasible_hit_rate": "ratio",
    "best_objective_raw": "synthetic_objective_unit",
    "min_constraint_violation_sum": "synthetic_constraint_unit",
    "true_evals_used": "count",
    "n_failed_evals": "count",
    "cache_hits": "count",
    "failed_evals": "count",
    "wall_s": "second",
    "null_rate": "ratio",
}
HISTORY_TMP_NAME = "holdout_history_rows.jsonl"


def _canonical_row(row: Mapping[str, Any]) -> str:
    """把一行结果规范化为可比较字符串（剔除墙钟等非确定字段）。"""
    payload = {key: value for key, value in row.items() if key not in VOLATILE_ROW_KEYS}
    proxy = payload.get("proxy_scoring_cost_json")
    if isinstance(proxy, str) and proxy:
        try:
            parsed = json.loads(proxy)
        except json.JSONDecodeError:
            parsed = proxy
        if isinstance(parsed, Mapping):
            payload["proxy_scoring_cost_json"] = json.dumps(
                {key: value for key, value in parsed.items() if key != "wall_s"},
                ensure_ascii=False,
                sort_keys=True,
                default=_json_default,
            )
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default)


def rows_digest(rows: Sequence[Mapping[str, Any]] | None) -> str:
    """行内容 sha256（用于跨重复运行逐位比较，已剔除墙钟字段）。"""
    digest = hashlib.sha256()
    for row in rows or ():
        digest.update(_canonical_row(row).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def artifact_sha_map(model_artifacts_by_meta: Mapping[int, Mapping[str, Any]]) -> dict[str, str]:
    """代理 artifact 指纹映射（确定性审计用；artifact 指纹不含墙钟/训练杂项）。"""
    mapping: dict[str, str] = {}
    for meta_seed in sorted(int(seed) for seed in model_artifacts_by_meta):
        bundle = model_artifacts_by_meta[meta_seed]
        for key in ("pretrain", "maml"):
            if not isinstance(bundle, Mapping) or not isinstance(bundle.get(key), Mapping):
                raise M5RunnerError(f"meta_seed={meta_seed} 缺少 {key} 代理 artifact")
            digest = bundle[key].get("artifact_sha256")
            if not isinstance(digest, str) or not digest:
                raise M5RunnerError(f"meta_seed={meta_seed}/{key} 缺少 artifact_sha256")
            mapping[f"meta_seed={meta_seed}/{key}"] = digest
    return mapping


def build_holdout_group_payload(
    *,
    config: M5RunnerConfig,
    task: Any,
    design_space: Any,
    model_artifacts_by_meta: Mapping[int, Mapping[str, Any]],
    reference_objective: float | None,
    seed: int,
    group_index: int = 0,
) -> dict[str, Any]:
    """构造单组 holdout 执行载荷（task × 优化 seed × 全部臂 × 全部预算）。"""
    if getattr(task, "split", None) not in EVAL_SPLITS:
        raise M5RunnerError(
            f"holdout 只允许评估 split {EVAL_SPLITS}，收到 {getattr(task, 'split', None)!r}"
        )
    if not isinstance(model_artifacts_by_meta, Mapping) or not model_artifacts_by_meta:
        raise M5RunnerError("holdout 载荷必须包含按 meta_seed 组织的代理 artifact")
    missing = sorted(set(int(seed) for seed in config.meta_seeds) - set(int(s) for s in model_artifacts_by_meta))
    if missing:
        raise M5RunnerError(f"代理 artifact 缺少 meta_seed: {missing}")
    return {
        "group_index": int(group_index),
        "group_key": f"{task.task_id}|{int(seed)}",
        "run_id": config.run_id,
        "task": task,
        "design_space": design_space,
        "seed": int(seed),
        "budgets": tuple(int(budget) for budget in config.budgets),
        "arms": tuple(M5_ARM_ORDER),
        "meta_seeds": tuple(int(value) for value in config.meta_seeds),
        "model_artifacts": dict(model_artifacts_by_meta),
        "reference_objective": None if reference_objective is None else float(reference_objective),
        "emit_rows": True,
    }


def _curve_row_for_result(
    result: Any,
    *,
    meta_seed: int | None,
    reference_objective: float | None,
) -> dict[str, Any]:
    """单个 run 的预算轴曲线数据（fig4：best_feasible/gap 随评价次数变化）。"""
    indices: list[int] = []
    best_feasible: list[float | None] = []
    gaps: list[float | None] = []
    incumbent: float | None = None
    for observation in result.observations:
        if observation.feasible and observation.objective is not None:
            value = float(observation.objective)
            incumbent = value if incumbent is None else min(incumbent, value)
        indices.append(int(observation.eval_index))
        best_feasible.append(incumbent)
        if incumbent is None or reference_objective is None:
            gaps.append(None)
        else:
            gaps.append(float(incumbent - float(reference_objective)))
    return {
        "task_id": str(result.task_id),
        "split": str(result.split),
        "family": str(result.family),
        "arm": str(result.arm),
        "budget": int(result.budget),
        "seed": int(result.seed),
        "meta_seed": None if meta_seed is None else int(meta_seed),
        "eval_index": indices,
        "best_feasible_so_far": best_feasible,
        "gap_to_reference_so_far": gaps,
    }


def run_holdout_group(payload: Mapping[str, Any]) -> dict[str, Any]:
    """执行一组 holdout：同一任务同一优化 seed 下，全部臂 × 全部预算。

    每臂独立 evaluator（缓存/计费口径独立）；每 run 恰好 budget 次真实（合成）评价；
    physical_call_count 逐 run 复核，非 0 立即抛 PhysicsGuardViolation（fail-closed）。
    """
    task = payload.get("task")
    design_space = payload.get("design_space")
    if not isinstance(task, tf.SyntheticTask):
        raise M5RunnerError("holdout payload.task 必须是 SyntheticTask")
    if getattr(task, "split", None) not in EVAL_SPLITS:
        raise M5RunnerError(f"holdout 只允许评估 split {EVAL_SPLITS}，收到 {task.split!r}")
    if design_space is None:
        raise M5RunnerError("holdout payload.design_space 不能为空")
    run_id = str(payload["run_id"])
    group_index = int(payload.get("group_index", 0))
    task_seed = int(payload["seed"])
    budgets = tuple(int(value) for value in payload["budgets"])
    arms = tuple(str(value) for value in payload["arms"])
    meta_seeds = tuple(int(value) for value in payload["meta_seeds"])
    model_artifacts = payload["model_artifacts"]
    reference_objective = payload.get("reference_objective")
    if reference_objective is not None:
        reference_objective = float(reference_objective)
    emit_rows = bool(payload.get("emit_rows", True))
    if not budgets or not arms:
        raise M5RunnerError("holdout payload 的 budgets/arms 不能为空")

    history_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    init_dicts: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    wall_total = 0.0
    started_group = time.perf_counter()
    for budget in budgets:
        for arm in arms:
            if arm in MODEL_SCORED_ARMS:
                key = MODEL_ARTIFACT_KEYS[arm]
                assignments: list[tuple[int | None, Mapping[str, Any] | None]] = []
                for meta_seed in meta_seeds:
                    bundle = model_artifacts.get(meta_seed)
                    if not isinstance(bundle, Mapping) or key not in bundle:
                        raise M5RunnerError(f"代理 artifact 缺少 meta_seed={meta_seed}/{key}")
                    assignments.append((meta_seed, bundle[key]))
            else:
                assignments = [(None, None)]
            for meta_seed, model_payload in assignments:
                evaluator = make_synthetic_task_evaluator(task, design_space)
                guarded = GuardedEvaluator(
                    evaluator,
                    label=f"m5-holdout:{task.task_id}:{arm}:budget={budget}:seed={task_seed}",
                )
                run_started = time.perf_counter()
                result = run_m5_arm(
                    arm,
                    guarded,
                    task=task,
                    seed=task_seed,
                    budget=budget,
                    design_space=design_space,
                    model_artifact=model_payload,
                    reference_objective=reference_objective,
                    run_id=run_id,
                )
                elapsed = time.perf_counter() - run_started
                wall_total += elapsed
                label = f"{arm}/{task.task_id}/budget={budget}/seed={task_seed}/meta_seed={meta_seed}"
                _check_physical_guard(result, label=label)
                reported = getattr(guarded, "physical_call_count", 0)
                if reported not in (0, None):
                    raise PhysicsGuardViolation(
                        f"{label} evaluator 报告 physical_call_count={reported!r}，立即中止整次 run",
                        physical_call_count=int(reported),
                    )
                if int(result.true_evals_used) != int(budget):
                    raise M5RunnerError(
                        f"{label} 等预算约束被破坏：true_evals_used={result.true_evals_used} != {budget}"
                    )
                history_rows.extend(
                    history_rows_for_result(result, run_id=run_id, meta_seed=meta_seed)
                )
                summary_rows.append(
                    summary_row_for_result(
                        result,
                        run_id=run_id,
                        meta_seed=meta_seed,
                        initializer=ARM_INITIALIZERS[arm],
                        task=task,
                    )
                )
                proxy_cost = dict(result.proxy_scoring_cost or {})
                init_dicts.append(
                    arm_init_record(
                        result,
                        meta_seed=meta_seed,
                        candidate_pool_sha256=proxy_cost.get("candidate_pool_sha256"),
                        artifact_sha256=proxy_cost.get("artifact_sha256"),
                    ).to_dict()
                )
                curve_rows.append(
                    _curve_row_for_result(
                        result,
                        meta_seed=meta_seed,
                        reference_objective=reference_objective,
                    )
                )
    output = {
        "group_index": group_index,
        "group_key": f"{task.task_id}|{task_seed}",
        "task_id": str(task.task_id),
        "split": str(task.split),
        "family": str(task.family),
        "seed": task_seed,
        "n_runs": len(summary_rows),
        "budget_count": len(budgets),
        "arms": list(arms),
        "wall_s": wall_total,
        "group_wall_s": time.perf_counter() - started_group,
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "digests": {
            "history": rows_digest(history_rows),
            "summary": rows_digest(summary_rows),
            "initial_design": rows_digest(init_dicts),
            "curve": rows_digest(curve_rows),
        },
        "history_rows": history_rows if emit_rows else None,
        "summary_rows": summary_rows if emit_rows else None,
        "initial_design_records": init_dicts if emit_rows else None,
        "curve_rows": curve_rows if emit_rows else None,
    }
    return output


def execute_holdout_groups(
    groups: Sequence[Mapping[str, Any]],
    *,
    workers: int = 1,
    emit_rows: bool = True,
    on_result: Callable[[dict[str, Any]], None] | None = None,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
    progress_every: int = 20,
) -> dict[str, Any]:
    """执行全部 holdout 组；workers>1 时用 spawn 进程池（结果流式回调，避免全量驻留内存）。"""
    if type(workers) is not int or workers < 1:
        raise M5RunnerError(f"workers 必须是正整数，实际 {workers!r}")
    if progress_every < 1:
        raise M5RunnerError("progress_every 必须是正整数")
    total = len(groups)
    started = time.perf_counter()
    counters = {"done": 0, "physical_call_count": 0, "runs": 0}
    digests: dict[str, dict[str, str]] = {}

    def _handle(result: Mapping[str, Any]) -> None:
        counters["done"] += 1
        counters["physical_call_count"] += int(result.get("physical_call_count", 0))
        counters["runs"] += int(result.get("n_runs", 0))
        digests[str(result["group_key"])] = dict(result.get("digests") or {})
        if on_result is not None:
            on_result(dict(result))
        if progress is not None and (counters["done"] % progress_every == 0 or counters["done"] == total):
            progress(
                "holdout_group",
                {
                    "done": counters["done"],
                    "total": total,
                    "runs": counters["runs"],
                    "wall_s": time.perf_counter() - started,
                    "physical_call_count": counters["physical_call_count"],
                },
            )

    if total == 0:
        return {
            "status": "PASS",
            "groups": 0,
            "runs": 0,
            "wall_s": 0.0,
            "physical_call_count": PHYSICAL_CALL_COUNT,
            "digests": {},
        }
    if workers <= 1:
        for payload in groups:
            item = dict(payload)
            item["emit_rows"] = bool(emit_rows)
            _handle(run_holdout_group(item))
    else:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor, as_completed

        context = multiprocessing.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
            futures = []
            for payload in groups:
                item = dict(payload)
                item["emit_rows"] = bool(emit_rows)
                futures.append(pool.submit(run_holdout_group, item))
            for future in as_completed(futures):
                _handle(future.result())
    return {
        "status": "PASS",
        "groups": counters["done"],
        "runs": counters["runs"],
        "wall_s": time.perf_counter() - started,
        "physical_call_count": counters["physical_call_count"],
        "digests": digests,
    }


def training_rows_for_artifacts(
    model_artifacts_by_meta: Mapping[int, Mapping[str, Any]],
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    """从代理 artifact 提取 training_history.csv 行（fig1 元训练损失；无验证损失）。"""
    rows: list[dict[str, Any]] = []
    for meta_seed in sorted(int(seed) for seed in model_artifacts_by_meta):
        bundle = model_artifacts_by_meta[meta_seed]
        for key in ("pretrain", "maml"):
            payload = bundle[key]
            arm = "M5-pretrain-proxy" if key == "pretrain" else "M5-MAML-proxy"
            training_rows = payload.get("training_rows") or ()
            if not training_rows:
                raise M5RunnerError(f"meta_seed={meta_seed}/{key} 缺少 training_rows（fig1 无法如实生成）")
            for row in training_rows:
                item = {column: row.get(column) for column in TRAINING_HISTORY_COLUMNS}
                item.update(
                    {
                        "run_id": run_id,
                        "arm": arm,
                        "meta_seed": int(meta_seed),
                        "seed": int(meta_seed),
                        "status": row.get("status") or "VALID",
                    }
                )
                rows.append(item)
    return rows
# ---------------------------------------------------------------------------
# 任务层级统计（先 (task, opt_seed) 聚合，再跨任务配对；Holm 多重比较）
# ---------------------------------------------------------------------------
def _task_level_values(
    summary_rows: Sequence[Mapping[str, Any]],
    *,
    arm: str,
    budget: int,
    split: str,
    endpoint: str,
) -> tuple[dict[str, float | None], int, int]:
    """按任务层级聚合某臂某端点取值。

    规则（预注册）：(task, seed) 内跨 meta_seed 取非 null 均值（全 null 则 null）；
    任务内跨 seed 再取非 null 均值（全 null 则 null）。避免把优化 seed 当独立样本造成伪重复。
    """
    per_seed: dict[tuple[str, int], list[Any]] = {}
    n_runs = 0
    for row in summary_rows:
        if str(row.get("arm")) != arm:
            continue
        if int(row.get("budget")) != int(budget):
            continue
        if str(row.get("split")) != split:
            continue
        task_id = str(row.get("task_id"))
        seed = int(row.get("seed"))
        per_seed.setdefault((task_id, seed), []).append(row.get(endpoint_row_key(endpoint)))
        n_runs += 1
    per_task: dict[str, list[float | None]] = {}
    for (task_id, _seed), values in per_seed.items():
        finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
        per_task.setdefault(task_id, []).append((sum(finite) / len(finite)) if finite else None)
    task_values: dict[str, float | None] = {}
    for task_id, seed_values in per_task.items():
        finite = [float(value) for value in seed_values if value is not None]
        task_values[task_id] = (sum(finite) / len(finite)) if finite else None
    return task_values, len(per_task), n_runs


def _holm_adjust(pvalues: Sequence[float | None]) -> list[float | None]:
    """Holm-Bonferroni 校正（只在提供 p 值的比较之间校正，保持输入顺序）。"""
    indexed = [
        (position, float(value))
        for position, value in enumerate(pvalues)
        if value is not None and math.isfinite(float(value))
    ]
    adjusted: list[float | None] = [None] * len(pvalues)
    if not indexed:
        return adjusted
    indexed.sort(key=lambda item: (item[1], item[0]))
    total = len(indexed)
    running = 0.0
    for rank, (position, value) in enumerate(indexed):
        running = max(running, min(1.0, (total - rank) * value))
        adjusted[position] = running
    return adjusted


def _is_better(difference: float, direction: str) -> bool:
    if direction == "lower_better":
        return difference < 0.0
    if direction == "higher_better":
        return difference > 0.0
    raise M5RunnerError(f"未知端点方向: {direction!r}")


def paired_statistics_rows(
    summary_rows: Sequence[Mapping[str, Any]],
    *,
    splits: Sequence[str] = EVAL_SPLITS,
    budgets: Sequence[int] | None = None,
    comparisons: Sequence[tuple[str, str]] = PREREGISTERED_COMPARISONS,
    bootstrap_samples: int = BOOTSTRAP_SAMPLES,
    confidence: float = CONFIDENCE,
    seed: int = BOOTSTRAP_SEED,
) -> list[dict[str, Any]]:
    """预注册配对统计：任务层级配对差、bootstrap CI、Wilcoxon、Holm 多重比较。"""
    from .baseline_arms import paired_statistics

    if budgets is None:
        budgets = tuple(sorted({int(row.get("budget")) for row in summary_rows}))
    rows: list[dict[str, Any]] = []
    for split in splits:
        for budget in budgets:
            family: list[dict[str, Any]] = []
            for endpoint in PRIMARY_ENDPOINTS:
                direction = ENDPOINT_DIRECTIONS[endpoint]
                for arm, reference in comparisons:
                    arm_values, n_tasks_arm, _ = _task_level_values(
                        summary_rows, arm=arm, budget=int(budget), split=split, endpoint=endpoint
                    )
                    reference_values, n_tasks_reference, _ = _task_level_values(
                        summary_rows, arm=reference, budget=int(budget), split=split, endpoint=endpoint
                    )
                    task_ids = sorted(set(arm_values) | set(reference_values))
                    paired: list[tuple[str, float, float]] = []
                    for task_id in task_ids:
                        left = arm_values.get(task_id)
                        right = reference_values.get(task_id)
                        if left is not None and right is not None and math.isfinite(left) and math.isfinite(right):
                            paired.append((task_id, left, right))
                    differences = [left - right for _task, left, right in paired]
                    n_tasks = max(len(task_ids), n_tasks_arm, n_tasks_reference)
                    if differences:
                        stats = paired_statistics(
                            differences,
                            seed=seed,
                            bootstrap_samples=bootstrap_samples,
                            confidence=confidence,
                        )
                    else:
                        stats = {}
                    improvement = None
                    if differences:
                        improvement = sum(1 for value in differences if _is_better(value, direction)) / len(differences)
                    cohen = None
                    if len(differences) >= 2:
                        spread = float(np.std(differences, ddof=1))
                        if spread > 0:
                            cohen = float(np.mean(differences) / spread)
                    null_fraction = (1.0 - len(differences) / n_tasks) if n_tasks else None
                    if not differences:
                        status = "NO_DATA"
                    elif null_fraction is not None and null_fraction > (1.0 - SAFE_NULL_FRACTION):
                        status = "INCONCLUSIVE"
                    else:
                        status = "REPORTED"
                    note = (
                        "配对单位=task（任务内先跨 meta_seed、再跨优化 seed 聚合，避免伪重复）；"
                        "差值=臂−参照；bootstrap 百分位 CI；Wilcoxon 符号秩（n<5 或无差异时不报 p 值）。"
                    )
                    if status == "INCONCLUSIVE":
                        note += (
                            f" 非 null 配对比例 {len(differences)}/{n_tasks} 低于预注册门禁 "
                            f"{SAFE_NULL_FRACTION:.2f}，按合同标 INCONCLUSIVE，不据此外推。"
                        )
                    family.append(
                        {
                            "budget": int(budget),
                            "split": split,
                            "endpoint": endpoint,
                            "arm": arm,
                            "reference": reference,
                            "direction": direction,
                            "n_pairs": len(differences),
                            "n_tasks": n_tasks,
                            "n_nonnull": len(differences),
                            "null_fraction": null_fraction,
                            "median_diff": stats.get("median_diff"),
                            "mean_diff": stats.get("mean_diff"),
                            "ci_low": stats.get("ci_low"),
                            "ci_high": stats.get("ci_high"),
                            "improvement_probability": improvement,
                            "wilcoxon_statistic": stats.get("wilcoxon_statistic"),
                            "wilcoxon_pvalue": stats.get("wilcoxon_pvalue"),
                            "cohen_d_paired": cohen,
                            "holm_pvalue": None,
                            "status": status,
                            "note": note,
                        }
                    )
            adjusted = _holm_adjust([row["wilcoxon_pvalue"] for row in family])
            for row, value in zip(family, adjusted):
                row["holm_pvalue"] = value
                row["note"] = (
                    row["note"]
                    + f" Holm 家族=split {split} / budget {budget} 下 6 组预注册比较 × 4 个主终点"
                    f"（共 {len(family)} 个检验）。fallback 指标不参与本推断。"
                )
            rows.extend(family)
    return rows


def endpoint_summary_rows(
    summary_rows: Sequence[Mapping[str, Any]],
    *,
    splits: Sequence[str] = EVAL_SPLITS,
    budgets: Sequence[int] | None = None,
    endpoints: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """逐 (budget, split, endpoint, arm) 的描述统计（任务层级聚合；null 如实披露比例）。"""
    if budgets is None:
        budgets = tuple(sorted({int(row.get("budget")) for row in summary_rows}))
    if endpoints is None:
        ordered: list[str] = []
        for name in (*PRIMARY_ENDPOINTS, *SECONDARY_ENDPOINTS, *FALLBACK_ENDPOINTS):
            if name not in ordered:
                ordered.append(name)
        endpoints = tuple(ordered)
    rows: list[dict[str, Any]] = []
    for split in splits:
        for budget in budgets:
            for endpoint in endpoints:
                arms = sorted(
                    {
                        str(row.get("arm"))
                        for row in summary_rows
                        if int(row.get("budget")) == int(budget) and str(row.get("split")) == split
                    }
                )
                for arm in arms:
                    values, n_tasks, n_runs = _task_level_values(
                        summary_rows, arm=arm, budget=int(budget), split=split, endpoint=endpoint
                    )
                    finite = [float(value) for value in values.values() if value is not None]
                    rows.append(
                        {
                            "budget": int(budget),
                            "split": split,
                            "endpoint": endpoint,
                            "arm": arm,
                            "n_runs": n_runs,
                            "n_nonnull": len(finite),
                            "null_rate": (1.0 - len(finite) / n_tasks) if n_tasks else None,
                            "median": _median(finite),
                            "mean": _mean(finite),
                            "std": _std(finite),
                            "unit": ENDPOINT_UNITS.get(endpoint, "1"),
                        }
                    )
    return rows


def metrics_rows_from_summary(
    summary_rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    """逐 run 的 metrics.csv 行（per_run；聚合统计见 statistics.csv）。"""
    endpoints = tuple(
        dict.fromkeys((*PRIMARY_ENDPOINTS, *FALLBACK_ENDPOINTS, "null_rate"))
    )
    rows: list[dict[str, Any]] = []
    for row in summary_rows:
        for endpoint in endpoints:
            value = row.get(endpoint_row_key(endpoint))
            rows.append(
                {
                    "experiment_id": (
                        f"{run_id}::{row.get('task_id')}::{row.get('arm')}::budget={row.get('budget')}"
                        f"::seed={row.get('seed')}::meta_seed={row.get('meta_seed')}"
                    ),
                    "phase": "optimization",
                    "split": row.get("split"),
                    "family": row.get("family"),
                    "arm": row.get("arm"),
                    "K": None,
                    "task_id": row.get("task_id"),
                    "seed": row.get("seed"),
                    "metric": endpoint,
                    "value": value,
                    "unit": ENDPOINT_UNITS.get(endpoint, "1"),
                    "aggregation": "per_run",
                    "n": 1,
                    "status": "OK" if value is not None else "NULL",
                }
            )
    return rows


def initial_design_record_from_dict(payload: Mapping[str, Any]) -> Any:
    """把 worker 返回的初始设计字典还原为 InitialDesignRecord（审计/公平性校验用）。"""
    from .m5_arms import InitialDesignRecord

    data = dict(payload)
    data["initial_designs"] = tuple(
        tuple(float(value) for value in design) for design in data.get("initial_designs") or ()
    )
    return InitialDesignRecord(**data)


def initial_design_rows(records: Sequence[Mapping[str, Any]], *, run_id: str) -> list[dict[str, Any]]:
    """arm_audit.csv 行（初始 8 点指纹/候选池/artifact/等预算字段）。"""
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "run_id": run_id,
                "budget": record.get("budget"),
                "arm": record.get("arm"),
                "task_id": record.get("task_id"),
                "split": record.get("split"),
                "family": record.get("family"),
                "seed": record.get("seed"),
                "meta_seed": record.get("meta_seed"),
                "initializer": record.get("initializer"),
                "implementation": record.get("implementation"),
                "code_path": record.get("code_path"),
                "candidate_pool_sha256": record.get("candidate_pool_sha256"),
                "artifact_sha256": record.get("artifact_sha256"),
                "initial_designs_sha256": record.get("initial_designs_sha256"),
                "true_evals_used": record.get("true_evals_used"),
                "requested_evaluations": record.get("requested_evaluations"),
                "status": record.get("status"),
            }
        )
    return rows


def clone_audit_rows(audit_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """clone_audit.csv 行：只保留可识别性审计字段（臂对重叠率与 CLONE 标签）。"""
    return [{column: row.get(column) for column in CLONE_AUDIT_COLUMNS} for row in audit_rows]


def compare_determinism(
    passes: Sequence[Mapping[str, Any]],
    *,
    artifact_sha_maps: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """跨独立重复运行比较逐组行内容摘要（排除墙钟）；不一致即 FAIL，不得静默通过。"""
    if not passes:
        return {
            "status": "NOT_RUN",
            "reruns": 0,
            "excluded_columns": list(VOLATILE_ROW_KEYS),
            "note": "未提供重复运行结果",
        }
    base = passes[0]
    base_digests = dict(base.get("digests") or {})
    mismatches: list[dict[str, Any]] = []
    for candidate in passes[1:]:
        candidate_digests = dict(candidate.get("digests") or {})
        for group_key in sorted(set(base_digests) | set(candidate_digests)):
            expected = base_digests.get(group_key)
            actual = candidate_digests.get(group_key)
            if expected is None or actual is None:
                mismatches.append(
                    {
                        "rerun": int(candidate.get("pass", 0)),
                        "kind": "group_presence",
                        "group": group_key,
                        "expected": expected,
                        "actual": actual,
                    }
                )
                continue
            for kind in ("history", "summary", "initial_design", "curve"):
                if expected.get(kind) != actual.get(kind):
                    mismatches.append(
                        {
                            "rerun": int(candidate.get("pass", 0)),
                            "kind": kind,
                            "group": group_key,
                            "expected": expected.get(kind),
                            "actual": actual.get(kind),
                        }
                    )
    artifact_mismatches: list[dict[str, Any]] = []
    if artifact_sha_maps:
        base_map = dict(artifact_sha_maps[0])
        for index, mapping in enumerate(artifact_sha_maps[1:], start=1):
            current = dict(mapping)
            for key in sorted(set(base_map) | set(current)):
                if base_map.get(key) != current.get(key):
                    artifact_mismatches.append(
                        {
                            "rerun": index,
                            "artifact": key,
                            "expected": base_map.get(key),
                            "actual": current.get(key),
                        }
                    )
    status = "PASS" if not mismatches and not artifact_mismatches else "FAIL"
    return {
        "status": status,
        "reruns": len(passes),
        "groups_compared": len(base_digests),
        "excluded_columns": list(VOLATILE_ROW_KEYS),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "artifact_sha256_mismatches": artifact_mismatches[:20],
        "note": (
            "逐组比较 optimization_history / optimization_summary / 初始设计 / 预算轴曲线的行内容 sha256；"
            "排除列 wall_s 与 proxy_scoring_cost_json.wall_s（墙钟不参与确定性比较）。"
            "determinism_reruns<2 时 status=NOT_RUN，不冒充确定性通过。"
        ),
    }


def build_figure_data(
    *,
    config: M5RunnerConfig,
    run_id: str,
    training_rows: Sequence[Mapping[str, Any]],
    summary_rows: Sequence[Mapping[str, Any]],
    curve_rows: Sequence[Mapping[str, Any]],
    arm_audit_rows: Sequence[Mapping[str, Any]],
    clone_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """生成各图的数据载荷（只描述真实记录；缺数据标 NOT_AVAILABLE/NOT_RUN，不补假曲线）。"""
    figures: dict[str, Any] = {}
    series: dict[str, list[dict[str, Any]]] = {}
    for row in training_rows:
        key = f"{row.get('arm')}|meta_seed={row.get('meta_seed')}"
        series.setdefault(key, []).append(
            {
                "iteration": int(row.get("iteration") or 0),
                "loss_support": row.get("loss_support"),
                "loss_query": row.get("loss_query"),
                "grad_norm": row.get("grad_norm"),
            }
        )
    for key in series:
        series[key].sort(key=lambda item: item["iteration"])
    figures["fig1_meta_loss_curves"] = {
        "status": "DATA_READY" if series else "NOT_AVAILABLE",
        "source": "metrics/training_history.csv",
        "series": series,
        "validation_loss": "NOT_AVAILABLE（M5 未记录元验证损失；按合同不得补造）",
        "note": "MAML 代理元训练损失按 meta_seed 给出；预训练代理只有终点损失，无迭代曲线。",
    }
    figures["fig2_k_shot_rmse_mae"] = {
        "status": "NOT_APPLICABLE_THIS_STAGE",
        "source": None,
        "note": "K-shot 适应曲线归 M6（m6_study.py 生成）；M5 不产生 adaptation_results 数据。",
    }

    fig3: dict[str, Any] = {}
    for split in EVAL_SPLITS:
        for budget in config.budgets:
            arms = sorted(
                {
                    str(row.get("arm"))
                    for row in summary_rows
                    if int(row.get("budget")) == int(budget) and str(row.get("split")) == split
                }
            )
            for arm in arms:
                hit_values, n_tasks, n_runs = _task_level_values(
                    summary_rows, arm=arm, budget=int(budget), split=split, endpoint="feasible_hit_rate"
                )
                first_values, _, _ = _task_level_values(
                    summary_rows,
                    arm=arm,
                    budget=int(budget),
                    split=split,
                    endpoint="first_feasible_evaluation_index",
                )
                finite_hits = [float(value) for value in hit_values.values() if value is not None]
                finite_first = [float(value) for value in first_values.values() if value is not None]
                null_runs = sum(
                    1
                    for row in summary_rows
                    if str(row.get("arm")) == arm
                    and int(row.get("budget")) == int(budget)
                    and str(row.get("split")) == split
                    and row.get("best_feasible_value") is None
                )
                fig3[f"split={split}|budget={budget}|arm={arm}"] = {
                    "n_tasks": n_tasks,
                    "n_runs": n_runs,
                    "feasible_hit_rate_task_values": {key: hit_values[key] for key in sorted(hit_values)},
                    "first_feasible_evaluation_index_task_values": {
                        key: first_values[key] for key in sorted(first_values)
                    },
                    "median_feasible_hit_rate": _median(finite_hits),
                    "median_first_feasible_evaluation_index": _median(finite_first),
                    "null_run_fraction": (null_runs / n_runs) if n_runs else None,
                }
    figures["fig3_feasibility"] = {
        "status": "DATA_READY" if fig3 else "NOT_AVAILABLE",
        "source": "metrics/optimization_summary.csv",
        "series": fig3,
        "note": "无可行解保留 null 并披露 null_run_fraction；不得把 null 画成 0。",
    }

    fig4: dict[str, Any] = {}
    for budget in config.budgets:
        for arm in sorted({str(row.get("arm")) for row in curve_rows if int(row.get("budget")) == int(budget)}):
            runs = [
                row
                for row in curve_rows
                if int(row.get("budget")) == int(budget) and str(row.get("arm")) == arm
            ]
            if not runs:
                continue
            max_index = max(len(row.get("eval_index") or ()) for row in runs)
            curve: list[dict[str, Any]] = []
            for position in range(max_index):
                feasible_values: list[float] = []
                gap_values: list[float] = []
                missing = 0
                for row in runs:
                    best = list(row.get("best_feasible_so_far") or ())
                    gaps = list(row.get("gap_to_reference_so_far") or ())
                    if position >= len(best):
                        continue
                    if best[position] is None:
                        missing += 1
                    else:
                        feasible_values.append(float(best[position]))
                        if position < len(gaps) and gaps[position] is not None:
                            gap_values.append(float(gaps[position]))
                curve.append(
                    {
                        "eval_index": position + 1,
                        "median_best_feasible": _median(feasible_values),
                        "median_gap_to_reference": _median(gap_values),
                        "n_runs_nonnull": len(feasible_values),
                        "n_runs_missing": missing,
                    }
                )
            fig4[f"budget={budget}|arm={arm}"] = {
                "curve": curve,
                "n_runs": len(runs),
                "runs_with_any_feasible": sum(
                    1 for row in runs if any(value is not None for value in (row.get("best_feasible_so_far") or ()))
                ),
            }
    figures["fig4_equal_budget_optimization"] = {
        "status": "DATA_READY" if fig4 else "NOT_AVAILABLE",
        "source": "metrics/optimization_history.csv",
        "series": fig4,
        "note": "无可行解的评价点保持空白（不插值、不以 raw objective 代替）。",
    }

    proxy: dict[str, list[float]] = {}
    for row in summary_rows:
        try:
            cost = json.loads(row.get("proxy_scoring_cost_json") or "{}")
        except json.JSONDecodeError:
            cost = {}
        wall = cost.get("wall_s") if isinstance(cost, Mapping) else None
        if isinstance(wall, (int, float)) and math.isfinite(float(wall)) and float(wall) > 0:
            proxy.setdefault(str(row.get("arm")), []).append(float(wall))
    audit_summary: dict[str, Any] = {}
    for arm in sorted({str(row.get("arm")) for row in arm_audit_rows}):
        arm_rows = [row for row in arm_audit_rows if str(row.get("arm")) == arm]
        audit_summary[arm] = {
            "n_runs": len(arm_rows),
            "distinct_initial_designs": len(
                {str(row.get("initial_designs_sha256")) for row in arm_rows}
            ),
            "distinct_code_paths": sorted({str(row.get("code_path")) for row in arm_rows}),
            "distinct_implementations": sorted({str(row.get("implementation")) for row in arm_rows}),
            "proxy_scoring_wall_s_median": _median(proxy.get(arm, [])),
            "proxy_scoring_runs": len(proxy.get(arm, [])),
        }
    figures["fig5_arm_identifiability_and_cost"] = {
        "status": "DATA_READY" if audit_summary else "NOT_AVAILABLE",
        "source": "metrics/arm_audit.csv, metrics/clone_audit.csv",
        "arms": audit_summary,
        "clone_audit": list(clone_rows),
        "note": "代理打分墙钟与真实评价预算分开披露；不把代理成本混入真值预算。",
    }
    figures["fig6_issue4_progress"] = {
        "status": "NOT_RUN",
        "source": None,
        "note": "fig6 归 Issue #4（D-12D-004 VSPAERO/RCAIDE 回退气动油耗 + A/B/C 预算门禁），本阶段不得用非物理数值充图。",
    }
    return {
        "run_id": run_id,
        "generated_utc": iso_utc(),
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "figures": figures,
        "note": "图中数据均来自本 run 的 CSV/JSONL 记录；缺失/不适用一律显式标注。",
    }
# ---------------------------------------------------------------------------
# holdout 阶段：解锁门禁 -> 组编排 -> 逐 pass 执行 -> 统计/审计/确定性
# ---------------------------------------------------------------------------
import json
import shutil
import tempfile
import traceback

SOLVER_VALIDATION_COLUMNS = ("run_id", "case_id", "evaluator_id", "solver_family", "status", "note")
SOLVER_VALIDATION_ROWS = (
    {
        "case_id": "D-12D-001",
        "solver_family": "VSPAERO",
        "status": "NOT_APPLICABLE_THIS_STAGE",
        "note": (
            "P4-CODE 只做解析合成评估；VSPAERO/RCAIDE 回退气动油耗验证归 Issue #4 D-12D-004，"
            "本阶段不调用求解器、不生成 fig4 物理曲线。"
        ),
    },
    {
        "case_id": "D-12D-002",
        "solver_family": "SU2",
        "status": "NOT_RUN",
        "note": "P4-CODE 未批准真实高保真求解；如实记 NOT_RUN，不伪造数值。",
    },
    {
        "case_id": "D-12D-003",
        "solver_family": "RCAIDE_MISSION",
        "status": "NOT_RUN",
        "note": "P4-CODE 未批准真实 Mission 评估；physical_call_count 必须为 0。",
    },
)


def holdout_split_tasks(tasks: Sequence[Any]) -> dict[str, list[Any]]:
    """按评估 split 分组（meta_test / meta_test_ood），任务按 task_id 排序保证确定性。"""
    grouped: dict[str, list[Any]] = {split: [] for split in EVAL_SPLITS}
    for task in tasks:
        split = getattr(task, "split", None)
        if split in grouped:
            grouped[split].append(task)
    for split in grouped:
        grouped[split].sort(key=lambda item: str(item.task_id))
    return grouped


def expected_holdout_plan(config: M5RunnerConfig) -> dict[str, Any]:
    """holdout 规模计划（组数、每臂/预算 run 数、总 run 数），用于落盘前一致性校验。"""
    runs_per_budget = 2 + 2 * len(config.meta_seeds)
    runs_per_group = runs_per_budget * len(config.budgets)
    splits: dict[str, Any] = {}
    for split in EVAL_SPLITS:
        task_count = int(config.meta_test_tasks) if split == "meta_test" else int(config.ood_tasks)
        splits[split] = {
            "tasks": task_count,
            "seeds": len(config.optimization_seeds),
            "groups": task_count * len(config.optimization_seeds),
        }
    return {
        "budgets": list(config.budgets),
        "meta_seeds": list(config.meta_seeds),
        "runs_per_budget_per_group": runs_per_budget,
        "runs_per_group": runs_per_group,
        "splits": splits,
        "total_groups": sum(item["groups"] for item in splits.values()),
        "total_runs": sum(item["groups"] for item in splits.values()) * runs_per_group,
    }


def reference_objectives_by_task(split_tasks: Mapping[str, Sequence[Any]]) -> dict[str, float]:
    """解析参考解目标值（v2：u*=c、f*=b_eff），用于 gap_to_reference；非有限立即失败。"""
    values: dict[str, float] = {}
    for split in EVAL_SPLITS:
        for task in split_tasks.get(split, ()):
            reference = task.reference()
            objective_star = reference.get("objective_star")
            if objective_star is None or not math.isfinite(float(objective_star)):
                raise M5RunnerError(f"任务 {task.task_id} 参考解目标值非有限：{objective_star!r}")
            values[str(task.task_id)] = float(objective_star)
    return values


def build_holdout_groups(
    config: M5RunnerConfig,
    *,
    split_tasks: Mapping[str, Sequence[Any]],
    design_space: Any,
    model_artifacts_by_meta: Mapping[int, Mapping[str, Any]],
    reference_objectives: Mapping[str, float],
) -> list[dict[str, Any]]:
    """构造全部 holdout 组载荷：split × task × optimization seed。"""
    groups: list[dict[str, Any]] = []
    index = 0
    for split in EVAL_SPLITS:
        for task in split_tasks.get(split, ()):
            reference_objective = reference_objectives.get(str(task.task_id))
            for seed in config.optimization_seeds:
                groups.append(
                    build_holdout_group_payload(
                        config=config,
                        task=task,
                        design_space=design_space,
                        model_artifacts_by_meta=model_artifacts_by_meta,
                        reference_objective=reference_objective,
                        seed=int(seed),
                        group_index=index,
                    )
                )
                index += 1
    return groups


def build_proxy_artifacts(
    config: M5RunnerConfig,
    *,
    train_tasks: Sequence[Any],
    blocks: Mapping[str, Any],
    progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[int, dict[str, Any]]:
    """按 meta_seed 训练预训练/MAML 代理（仅 meta_train 任务，绝不接触 test/ood）。"""
    bundles: dict[int, dict[str, Any]] = {}
    for meta_seed in config.meta_seeds:
        started = time.perf_counter()
        if progress is not None:
            progress("proxy_artifact_start", {"meta_seed": int(meta_seed)})
        bundle = build_m5_model_artifacts(
            blocks,
            train_tasks,
            meta_seed=int(meta_seed),
            maml_steps=int(config.max_meta_steps),
            pretrain_steps=int(config.pretrain_steps),
        )
        bundles[int(meta_seed)] = bundle
        if progress is not None:
            progress(
                "proxy_artifact_complete",
                {"meta_seed": int(meta_seed), "wall_s": float(time.perf_counter() - started)},
            )
    return bundles


def _identifiability_summary(audit: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": audit.get("status"),
        "arms_present": list(audit.get("arms_present") or ()),
        "groups_checked": audit.get("groups_checked"),
        "clone_arms": list(audit.get("clone_arms") or ()),
        "indistinguishable_arms": list(audit.get("indistinguishable_arms") or ()),
        "distinct_code_paths": audit.get("distinct_code_paths"),
        "distinct_implementations": audit.get("distinct_implementations"),
        "physical_call_count": audit.get("physical_call_count", PHYSICAL_CALL_COUNT),
    }


def _fairness_summary(fairness: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": fairness.get("status"),
        "records": fairness.get("records"),
        "groups": fairness.get("groups"),
        "arms": list(fairness.get("arms") or ()),
        "initial_design_count": fairness.get("initial_design_count"),
        "dedup_tolerance": fairness.get("dedup_tolerance"),
        "physical_call_count": fairness.get("physical_call_count", PHYSICAL_CALL_COUNT),
    }


def _primary_endpoint_payload(endpoint_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """主终点描述统计（split -> budget -> arm -> endpoint）。"""
    payload: dict[str, Any] = {}
    for row in endpoint_rows:
        endpoint = str(row.get("endpoint"))
        if endpoint not in PRIMARY_ENDPOINTS:
            continue
        split = payload.setdefault(str(row.get("split")), {})
        budget = split.setdefault(str(row.get("budget")), {})
        arm = budget.setdefault(str(row.get("arm")), {})
        arm[endpoint] = {
            "median": row.get("median"),
            "mean": row.get("mean"),
            "n_nonnull": row.get("n_nonnull"),
            "null_rate": row.get("null_rate"),
            "unit": row.get("unit"),
        }
    return payload


def _null_disclosure(summary_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """逐端点 null 比例披露（不可行/失败保留 null，不写 0）。"""
    endpoints = tuple(dict.fromkeys((*PRIMARY_ENDPOINTS, *SECONDARY_ENDPOINTS, *FALLBACK_ENDPOINTS)))
    total = len(summary_rows)
    payload: dict[str, Any] = {}
    for endpoint in endpoints:
        key = endpoint_row_key(endpoint)
        nulls = sum(1 for row in summary_rows if row.get(key) is None)
        payload[endpoint] = {
            "n_runs": total,
            "n_null": nulls,
            "null_rate": (nulls / total) if total else None,
        }
    return payload


def _project_rows(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> list[dict[str, Any]]:
    return [{column: row.get(column) for column in columns} for row in rows]


def _write_history_csv_from_jsonl(jsonl_path: Path, target: Path, *, run_id: str) -> int:
    """把流式 JSONL 历史行投影为 optimization_history.csv（避免全量驻留内存）。"""
    count = 0

    def _rows() -> Any:
        nonlocal count
        with Path(jsonl_path).open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                row = json.loads(text)
                count += 1
                yield {column: row.get(column) for column in OPTIMIZATION_HISTORY_COLUMNS}

    write_csv(target, _rows(), columns=OPTIMIZATION_HISTORY_COLUMNS)
    if count == 0:
        raise M5RunnerError(f"holdout 历史行为空（run_id={run_id}）：拒绝写出空 optimization_history.csv")
    return count


def run_holdout_stage(
    config: M5RunnerConfig,
    *,
    workers: int = 1,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """holdout 阶段：四方门禁解锁后一次性评估测试集；确定性重复 pass 不得静默通过。"""
    if config.stage != "holdout":
        raise M5RunnerError(f"run_holdout_stage 需要 stage='holdout'，实际 {config.stage!r}")
    started = time.perf_counter()
    guard_baseline = _forbidden_modules_present()
    tmp_dir: Path | None = None
    try:
        assert_no_forbidden_modules(guard_baseline)
        prereq = load_holdout_prerequisites(config)
        design_space = load_design_space_12d()
        family_config = prereq["family_config"]
        tasks = tf.build_task_family(family_config)
        fv2.verify_split_manifest(
            prereq["split_manifest"], tasks=tasks, family_config=family_config
        )
        split_tasks = holdout_split_tasks(tasks)
        plan = expected_holdout_plan(config)
        for split in EVAL_SPLITS:
            expected = plan["splits"][split]["tasks"]
            actual = len(split_tasks[split])
            if actual != expected:
                raise M5RunnerError(
                    f"holdout split {split} 任务数 {actual} 与配置 {expected} 不符（禁止临时改动测试集规模）"
                )
        train_tasks = [task for task in tasks if task.split == "meta_train"]
        if len(train_tasks) != int(config.meta_train_tasks):
            raise M5RunnerError(
                f"meta_train 任务数 {len(train_tasks)} 与配置 {config.meta_train_tasks} 不符"
            )
        reference_objectives = reference_objectives_by_task(split_tasks)
        if progress is not None:
            progress(
                "holdout_start",
                {
                    "run_id": config.run_id,
                    "radius_base": prereq["radius_base"],
                    "plan": plan,
                    "workers": int(workers),
                },
            )
        blocks = build_task_blocks(train_tasks)
        task_payload = _tasks_payload(tasks, family_config)
        solutions_payload = reference_solutions_payload(tasks)

        tmp_dir = Path(tempfile.mkdtemp(prefix="p4-m5-holdout-"))
        history_jsonl = tmp_dir / HISTORY_TMP_NAME
        passes: list[dict[str, Any]] = []
        artifact_maps: list[dict[str, str]] = []
        training_rows: list[dict[str, Any]] = []
        summary_rows: list[dict[str, Any]] = []
        init_dicts: list[dict[str, Any]] = []
        curve_rows: list[dict[str, Any]] = []
        run_wall_s = 0.0
        with history_jsonl.open("w", encoding="utf-8", newline="\n") as history_handle:
            for pass_index in range(int(config.determinism_reruns)):
                pass_started = time.perf_counter()
                passes_emit = pass_index == 0
                bundles = build_proxy_artifacts(
                    config, train_tasks=train_tasks, blocks=blocks, progress=progress
                )
                if pass_index == 0:
                    training_rows = training_rows_for_artifacts(bundles, run_id=config.run_id)
                groups = build_holdout_groups(
                    config,
                    split_tasks=split_tasks,
                    design_space=design_space,
                    model_artifacts_by_meta=bundles,
                    reference_objectives=reference_objectives,
                )
                if len(groups) != plan["total_groups"]:
                    raise M5RunnerError(
                        f"holdout 组数 {len(groups)} 与计划 {plan['total_groups']} 不符"
                    )

                def _on_result(
                    result: Mapping[str, Any],
                    *,
                    emit: bool = passes_emit,
                    handle: Any = history_handle,
                ) -> None:
                    if not emit:
                        return
                    for row in result.get("history_rows") or ():
                        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                    summary_rows.extend(result.get("summary_rows") or ())
                    init_dicts.extend(result.get("initial_design_records") or ())
                    curve_rows.extend(result.get("curve_rows") or ())

                execution = execute_holdout_groups(
                    groups,
                    workers=int(workers),
                    emit_rows=passes_emit,
                    on_result=_on_result if passes_emit else None,
                    progress=progress,
                )
                assert_no_forbidden_modules(guard_baseline)
                run_wall_s += float(execution["wall_s"])
                passes.append(
                    {
                        "pass": pass_index,
                        "digests": dict(execution["digests"]),
                        "groups": int(execution["groups"]),
                        "runs": int(execution["runs"]),
                        "wall_s": float(execution["wall_s"]),
                    }
                )
                artifact_maps.append(artifact_sha_map(bundles))
                if progress is not None:
                    progress(
                        "holdout_pass_complete",
                        {
                            "pass": pass_index,
                            "groups": int(execution["groups"]),
                            "runs": int(execution["runs"]),
                            "pass_wall_s": float(time.perf_counter() - pass_started),
                            "physical_call_count": int(execution["physical_call_count"]),
                        },
                    )
        determinism = compare_determinism(passes, artifact_sha_maps=artifact_maps)
        records = [initial_design_record_from_dict(payload) for payload in init_dicts]
        fairness = assert_m5_fairness(records)
        audit = identifiability_audit(records)
        if int(audit.get("physical_call_count", PHYSICAL_CALL_COUNT)) != PHYSICAL_CALL_COUNT:
            raise PhysicsGuardViolation(
                "可识别性审计报告 physical_call_count!=0，立即中止整次 run",
                physical_call_count=int(audit.get("physical_call_count", 1) or 1),
            )
        audit_rows = identifiability_rows(audit)
        clone_rows = clone_audit_rows(audit_rows)
        statistics_rows = paired_statistics_rows(summary_rows)
        endpoint_rows = endpoint_summary_rows(summary_rows)
        metric_rows = metrics_rows_from_summary(summary_rows, run_id=config.run_id)
        arm_rows = initial_design_rows(init_dicts, run_id=config.run_id)
        figures = build_figure_data(
            config=config,
            run_id=config.run_id,
            training_rows=training_rows,
            summary_rows=summary_rows,
            curve_rows=curve_rows,
            arm_audit_rows=arm_rows,
            clone_rows=clone_rows,
        )
        true_evaluations = sum(int(row.get("true_evals_used") or 0) for row in summary_rows)
        for row in summary_rows:
            if int(row.get("physical_call_count") or 0) != PHYSICAL_CALL_COUNT:
                raise PhysicsGuardViolation(
                    f"holdout 行报告 physical_call_count!=0（task={row.get('task_id')} arm={row.get('arm')}）",
                    physical_call_count=int(row.get("physical_call_count") or 1),
                )
        if int(config.determinism_reruns) < 2 and determinism.get("status") == "PASS":
            determinism = {
                "status": "NOT_RUN",
                "reruns": int(config.determinism_reruns),
                "groups_compared": determinism.get("groups_compared"),
                "excluded_columns": list(determinism.get("excluded_columns") or ()),
                "mismatch_count": 0,
                "mismatches": [],
                "artifact_sha256_mismatches": [],
                "note": (
                    "determinism_reruns<2：未做独立重复运行，确定性状态如实记 NOT_RUN，"
                    "不冒充通过；conclusions_allowed 相应置 False。"
                ),
            }
        status = "VALID" if determinism["status"] in ("PASS", "NOT_RUN") else "DETERMINISM_FAILED"
        conclusions = config.study_scale == "FORMAL" and determinism["status"] == "PASS"
        runtime_s = float(time.perf_counter() - started)
        git_state = repo_git_state(REPO_ROOT)
        if progress is not None:
            progress(
                "holdout_complete",
                {
                    "status": status,
                    "groups": len(passes[0]["digests"]) if passes else 0,
                    "runs": len(summary_rows),
                    "runtime_s": runtime_s,
                },
            )
        stage_payload: dict[str, Any] = {
            "config": config,
            "prereq": prereq,
            "family_config": family_config,
            "design_space": design_space,
            "git_state": git_state,
            "tasks_payload": task_payload,
            "solutions_payload": solutions_payload,
            "training_rows": training_rows,
            "summary_rows": summary_rows,
            "metric_rows": metric_rows,
            "endpoint_rows": endpoint_rows,
            "statistics_rows": statistics_rows,
            "arm_rows": arm_rows,
            "clone_rows": clone_rows,
            "figure_payload": figures,
            "determinism": determinism,
            "audit": audit,
            "fairness": fairness,
            "history_jsonl": history_jsonl,
            "workers": int(workers),
            "plan": plan,
            "true_evaluations": true_evaluations,
            "runtime_s": runtime_s,
            "run_wall_s": run_wall_s,
            "status": status,
            "conclusions_allowed": conclusions,
            "history_rows_count": sum(1 for _ in history_jsonl.open("r", encoding="utf-8")),
        }
        summary = _holdout_summary(stage_payload)
        products = _write_holdout_products(stage_payload, summary=summary)
        return {
            "status": status,
            "stage": "holdout",
            "run_dir": str(config.run_dir),
            "study_scale": config.study_scale,
            "conclusions_allowed": conclusions,
            "groups": len(passes[0]["digests"]) if passes else 0,
            "runs_completed": len(summary_rows),
            "true_evaluations": true_evaluations,
            "determinism": determinism,
            "identifiability": _identifiability_summary(audit),
            "fairness": _fairness_summary(fairness),
            "summary": summary,
            "products_written": products,
            "physical_call_count": PHYSICAL_CALL_COUNT,
        }
    except PhysicsGuardViolation as error:
        summary = _write_stage_failure(
            config.run_dir, config, stage="holdout", status="PHYSICS_GUARD_VIOLATION", error=error
        )
        return {
            "status": "PHYSICS_GUARD_VIOLATION",
            "stage": "holdout",
            "run_dir": str(config.run_dir),
            "summary": summary,
            "products_written": ["summary.json"],
            "physical_call_count": int(getattr(error, "physical_call_count", 1) or 1),
        }
    except PreregistrationNotFrozen as error:
        summary = _write_stage_failure(
            config.run_dir, config, stage="holdout", status="PREREGISTRATION_NOT_FROZEN", error=error
        )
        return {
            "status": "PREREGISTRATION_NOT_FROZEN",
            "stage": "holdout",
            "run_dir": str(config.run_dir),
            "summary": summary,
            "products_written": ["summary.json"],
        }
    except (M5RunnerError, fv2.FeasibleV2Error, tf.TaskFamilyError, ValueError) as error:
        summary = _write_stage_failure(
            config.run_dir, config, stage="holdout", status="FAILED", error=error
        )
        return {
            "status": "FAILED",
            "stage": "holdout",
            "run_dir": str(config.run_dir),
            "summary": summary,
            "error": {"type": type(error).__name__, "message": str(error)},
            "products_written": ["summary.json"],
        }
    except Exception as error:  # 失败如实落盘，绝不伪造正常产物
        summary = _write_stage_failure(
            config.run_dir, config, stage="holdout", status="FAILED", error=error
        )
        return {
            "status": "FAILED",
            "stage": "holdout",
            "run_dir": str(config.run_dir),
            "summary": summary,
            "error": {"type": type(error).__name__, "message": str(error)},
            "products_written": ["summary.json"],
        }
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
# ---------------------------------------------------------------------------
# holdout 产物写出（§11.2 固定文件集）+ 阶段编排入口
# ---------------------------------------------------------------------------
HOLDOUT_PRODUCT_FILES = (
    "run_config.json",
    "environment.json",
    "tasks.json",
    "reference_solutions.json",
    "meta_task_split.json",
    "frozen_family.json",
    "preregistration.json",
    "solver_validation.csv",
    "metrics/training_history.csv",
    "metrics/optimization_history.csv",
    "metrics/optimization_summary.csv",
    "metrics/metrics.csv",
    "metrics/statistics.csv",
    "metrics/endpoint_summary.csv",
    "metrics/arm_audit.csv",
    "metrics/clone_audit.csv",
    "metrics/adaptation_results.csv",
    "figures/figure_data.json",
    "figures/figure_status.json",
    "README.md",
    "summary.json",
    "data_manifest.json",
)

FALLBACK_NOTE = (
    "best_objective_raw / min_constraint_violation_sum / feasible_hit_rate 仅是 fallback 描述量："
    "无可行解时主终点保留 null 并披露比例，禁止以非可行 raw objective 宣称约束优化更优。"
)

FIGURES_NOTE = (
    "本阶段只落盘图数据（figure_data.json）与状态（figure_status.json）；"
    "PNG 由 A2/M5 报告阶段从 CSV 生成。fig2 归 M6；fig6 归 Issue #4 D-12D-004，"
    "缺失图一律记 NOT_RUN/NOT_APPLICABLE，禁止假图。"
)


def _holdout_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    """holdout 阶段 summary.json 载荷（结论与披露均来自真实记录）。"""
    config: M5RunnerConfig = payload["config"]
    prereq = payload["prereq"]
    determinism = payload["determinism"]
    figures = payload.get("figure_payload") or {}
    figure_status = {
        str(name): str((item or {}).get("status"))
        for name, item in (figures.get("figures") or {}).items()
    }
    frozen = prereq["frozen_family"]
    plan = payload["plan"]
    return {
        "run_id": config.run_id,
        "stage": "holdout",
        "status": payload["status"],
        "study_scale": config.study_scale,
        "conclusions_allowed": bool(payload["conclusions_allowed"]),
        "data_origin": "SYNTHETIC_TEST",
        "evaluator_id": SYNTHETIC_EVALUATOR_ID,
        "family": {
            "family_id": frozen["family_id"],
            "family_version": frozen["family_version"],
            "family_seed": int(config.family_seed),
            "radius_base": float(prereq["radius_base"]),
            "family_fingerprint": frozen["family_fingerprint"],
            "reference_solution": fv2.REFERENCE_SOLUTION,
            "gap_definition": fv2.GAP_DEFINITION,
        },
        "gate": {
            "status": prereq["status"],
            "frozen_family_sha256": frozen["sha256"],
            "preregistration_sha256": prereq["preregistration"]["sha256"],
            "calibration_report_sha256": prereq["calibration_report"].sha256,
            "split_hash": prereq["split_manifest"]["split_hash"],
            "meta_test_tuning_policy": fv2.META_TEST_TUNING_POLICY,
        },
        "split_counts": dict(prereq["split_manifest"]["counts"]),
        "budgets": list(config.budgets),
        "optimization_seeds": list(config.optimization_seeds),
        "meta_seeds": list(config.meta_seeds),
        "plan": dict(plan),
        "counts": {
            "holdout_groups": int(plan["total_groups"]),
            "runs": len(payload["summary_rows"]),
            "history_rows": payload["history_rows_count"],
            "true_evaluations": int(payload["true_evaluations"]),
        },
        "determinism": {
            "status": determinism.get("status"),
            "reruns": determinism.get("reruns"),
            "groups_compared": determinism.get("groups_compared"),
            "mismatch_count": determinism.get("mismatch_count"),
            "excluded_columns": list(determinism.get("excluded_columns") or ()),
            "note": determinism.get("note"),
        },
        "identifiability": _identifiability_summary(payload["audit"]),
        "fairness": _fairness_summary(payload["fairness"]),
        "primary_endpoint_summary": _primary_endpoint_payload(payload["endpoint_rows"]),
        "null_disclosure": _null_disclosure(payload["summary_rows"]),
        "fallback_metrics_note": FALLBACK_NOTE,
        "statistics_rows": len(payload["statistics_rows"]),
        "figures": figure_status,
        "figures_note": FIGURES_NOTE,
        "runtime_s": payload["runtime_s"],
        "holdout_wall_s": payload["run_wall_s"],
        "workers": int(payload["workers"]),
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "physics_guard": {
            "expected": 0,
            "status": "PASS",
            "message": "holdout 全程 0 次真实求解器调用（GuardedEvaluator + 逐行 physical_call_count 复核）",
        },
        "not_approved": list(_NOT_APPROVED),
        "notes": [
            "holdout 结果只在冻结（frozen_family + meta_task_split + preregistration + calibration 报告四方门禁）"
            "一致后产生；meta_test/meta_test_ood 不参与任何调参。",
            "旧 F-QE 压力测试（~1e-6 可行域）结果单独成表，不与 v2 混算绝对目标。",
            FALLBACK_NOTE,
        ],
        "message": (
            "SYNTHETIC_ONLY：仅解析合成任务族 F-QE-feasible-v2 与 12D 设计空间解析 evaluator；"
            "physical_call_count=0；结论不得外推到真实飞机/真实求解器。"
        ),
    }


def _render_holdout_readme(summary: Mapping[str, Any], *, config: M5RunnerConfig) -> str:
    """中文 README：范围 / 配置 / 结果 / 非声明 / 产物 / 复现命令。"""
    lines: list[str] = [
        "# P4-M5 holdout 离线合成实验（P4-CODE）",
        "",
        "## 范围（scope）",
        "",
        "- 数据来源：SYNTHETIC_ONLY（解析任务族 F-QE-feasible-v2 + 12D 设计空间解析 evaluator）。",
        "- 物理调用：physical_call_count=0（fail-closed：任何非 0 立即中止整次 run）。",
        "- 未调用 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器，未访问网络。",
        "- 只在 calibration -> freeze -> holdout 四方门禁一致后才评估 meta_test/meta_test_ood；",
        "  meta_test 不参与任何超参/早停/任务选择。",
        "",
        "## 配置（config）",
        "",
        f"- run_id：{config.run_id}",
        f"- study_scale：{summary.get('study_scale')}；conclusions_allowed：{summary.get('conclusions_allowed')}",
        f"- 任务族：F-QE-feasible-v2（radius_base={summary.get('family', {}).get('radius_base')}，参考解 u*=c，gap=f(u_best)-f(u*)）",
        f"- split：{summary.get('split_counts')}",
        f"- 预算：{summary.get('budgets')}；优化 seeds：{summary.get('optimization_seeds')}；元训练 seeds：{summary.get('meta_seeds')}",
        f"- 评估 split：meta_test 与 meta_test_ood（OOD 单列，不参与调参）",
        f"- workers：{summary.get('workers')}；确定性重复 pass：{summary.get('determinism', {}).get('reruns')}",
        f"- evaluator_id：{summary.get('evaluator_id')}",
        f"- 门禁：{summary.get('gate', {}).get('status')}",
        f"- 冻结指纹：frozen_family={summary.get('gate', {}).get('frozen_family_sha256')}",
        f"- 预注册指纹：{summary.get('gate', {}).get('preregistration_sha256')}",
        "",
        "## 结果（results）",
        "",
        f"- status：{summary.get('status')}",
        f"- 组数：{summary.get('counts', {}).get('holdout_groups')}；runs：{summary.get('counts', {}).get('runs')}；"
        f"真实（合成）评价：{summary.get('counts', {}).get('true_evaluations')}；历史行：{summary.get('counts', {}).get('history_rows')}",
        f"- runtime_s：{summary.get('runtime_s')}",
        f"- 确定性：{summary.get('determinism', {}).get('status')}（mismatch={summary.get('determinism', {}).get('mismatch_count')}）",
        f"- 可识别性：{summary.get('identifiability', {}).get('status')}；clone_arms={summary.get('identifiability', {}).get('clone_arms')}",
        f"- 公平性审计：{summary.get('fairness', {}).get('status')}",
        "",
        "### 主终点描述统计（任务层级聚合中位数）",
        "",
        "| split | budget | arm | best_feasible_value | gap_to_reference | first_feasible_evaluation_index | feasible_hit_rate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    primary = summary.get("primary_endpoint_summary") or {}
    for split in EVAL_SPLITS:
        split_payload = primary.get(split) or {}
        for budget in sorted(split_payload, key=lambda item: int(item)):
            budget_payload = split_payload[budget]
            for arm in sorted(budget_payload):
                values = budget_payload[arm]

                def _cell(name: str) -> str:
                    item = values.get(name) or {}
                    median = item.get("median")
                    return "" if median is None else f"{median:.6g}"

                lines.append(
                    f"| {split} | {budget} | {arm} | {_cell('best_feasible_value')} | "
                    f"{_cell('gap_to_reference')} | {_cell('first_feasible_evaluation_index')} | "
                    f"{_cell('feasible_hit_rate')} |"
                )
    lines += [
        "",
        "### null 披露（不可行/失败保留 null，不写 0）",
        "",
        "| 端点 | n_runs | n_null | null_rate |",
        "| --- | --- | --- | --- |",
    ]
    for endpoint, item in (summary.get("null_disclosure") or {}).items():
        lines.append(
            f"| {endpoint} | {item.get('n_runs')} | {item.get('n_null')} | {item.get('null_rate')} |"
        )
    lines += [
        "",
        "### fallback 指标口径",
        "",
        f"- {FALLBACK_NOTE}",
        "",
        "## 非声明（non-claims）",
        "",
    ]
    lines += [f"- {claim}" for claim in fv2.NON_CLAIMS]
    lines += [
        "",
        "## 产物",
        "",
    ]
    lines += [f"- {name}" for name in summary.get("products_written") or ()]
    lines += [
        "",
        f"- 图状态：{summary.get('figures')}",
        f"- {FIGURES_NOTE}",
        "",
        "## 复现命令",
        "",
    ]
    lines += [f"- {command}" for command in _running_commands(config)]
    lines.append("")
    return "\n".join(lines)


def _write_holdout_products(
    payload: Mapping[str, Any],
    *,
    summary: Mapping[str, Any],
) -> list[str]:
    """写 holdout 全部产物（含 §11.2 固定文件集）并返回最终清单。"""
    config: M5RunnerConfig = payload["config"]
    prereq = payload["prereq"]
    root = config.run_dir
    root.mkdir(parents=True, exist_ok=True)
    metrics_dir = root / "metrics"
    figures_dir = root / "figures"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    run_config = _base_run_config(config, stage="holdout", git_state=payload["git_state"])
    run_config.update(
        {
            "preregistration_gate": {
                "status": prereq["status"],
                "frozen_family_sha256": prereq["frozen_family"]["sha256"],
                "preregistration_sha256": prereq["preregistration"]["sha256"],
                "calibration_report_sha256": prereq["calibration_report"].sha256,
                "split_hash": prereq["split_manifest"]["split_hash"],
                "radius_base": float(prereq["radius_base"]),
                "unlock": dict(prereq["unlocked"]),
            },
            "calibration_report_sha256": prereq["calibration_report"].sha256,
            "frozen_family_sha256": prereq["frozen_family"]["sha256"],
            "preregistration_sha256": prereq["preregistration"]["sha256"],
            "split_hash": prereq["split_manifest"]["split_hash"],
            "split_counts": dict(prereq["split_manifest"]["counts"]),
            "holdout_plan": dict(payload["plan"]),
            "evaluation_splits": list(EVAL_SPLITS),
            "workers": int(payload["workers"]),
            "null_disclosure": _null_disclosure(payload["summary_rows"]),
            "determinism": {
                "status": payload["determinism"].get("status"),
                "reruns": payload["determinism"].get("reruns"),
                "groups_compared": payload["determinism"].get("groups_compared"),
                "mismatch_count": payload["determinism"].get("mismatch_count"),
                "excluded_columns": list(payload["determinism"].get("excluded_columns") or ()),
            },
            "fairness_gate": _fairness_summary(payload["fairness"]),
            "identifiability": _identifiability_summary(payload["audit"]),
            "counts": {
                "holdout_groups": int(payload["plan"]["total_groups"]),
                "runs": len(payload["summary_rows"]),
                "history_rows": payload["history_rows_count"],
                "true_evaluations": int(payload["true_evaluations"]),
            },
            "runtime_s": payload["runtime_s"],
            "products": list(HOLDOUT_PRODUCT_FILES),
        }
    )
    write_json(root / "run_config.json", run_config)
    write_json(root / "environment.json", environment_payload(config.run_id, PHYSICAL_CALL_COUNT))
    write_json(root / "tasks.json", payload["tasks_payload"])
    write_json(root / "reference_solutions.json", payload["solutions_payload"])
    write_json(root / "meta_task_split.json", prereq["split_manifest"])
    write_json(root / "frozen_family.json", prereq["frozen_family"])
    write_json(root / "preregistration.json", prereq["preregistration"])
    write_csv(
        root / "solver_validation.csv",
        [{"run_id": config.run_id, **row} for row in SOLVER_VALIDATION_ROWS],
        columns=SOLVER_VALIDATION_COLUMNS,
    )
    write_csv(
        metrics_dir / "training_history.csv",
        _project_rows(payload["training_rows"], TRAINING_HISTORY_COLUMNS),
        columns=TRAINING_HISTORY_COLUMNS,
    )
    history_rows = _write_history_csv_from_jsonl(
        payload["history_jsonl"],
        metrics_dir / "optimization_history.csv",
        run_id=config.run_id,
    )
    write_csv(
        metrics_dir / "optimization_summary.csv",
        _project_rows(payload["summary_rows"], OPTIMIZATION_SUMMARY_COLUMNS),
        columns=OPTIMIZATION_SUMMARY_COLUMNS,
    )
    write_csv(
        metrics_dir / "metrics.csv",
        _project_rows(payload["metric_rows"], METRICS_COLUMNS),
        columns=METRICS_COLUMNS,
    )
    write_csv(
        metrics_dir / "statistics.csv",
        _project_rows(payload["statistics_rows"], STATISTICS_COLUMNS),
        columns=STATISTICS_COLUMNS,
    )
    write_csv(
        metrics_dir / "endpoint_summary.csv",
        _project_rows(payload["endpoint_rows"], ENDPOINT_SUMMARY_COLUMNS),
        columns=ENDPOINT_SUMMARY_COLUMNS,
    )
    write_csv(
        metrics_dir / "arm_audit.csv",
        _project_rows(payload["arm_rows"], ARM_AUDIT_COLUMNS),
        columns=ARM_AUDIT_COLUMNS,
    )
    write_csv(
        metrics_dir / "clone_audit.csv",
        _project_rows(payload["clone_rows"], CLONE_AUDIT_COLUMNS),
        columns=CLONE_AUDIT_COLUMNS,
    )
    write_csv(metrics_dir / "adaptation_results.csv", [], columns=ADAPTATION_RESULTS_COLUMNS)

    figures = payload["figure_payload"]
    write_json(figures_dir / "figure_data.json", figures)
    figure_status = {
        str(name): {"status": (item or {}).get("status"), "source": (item or {}).get("source")}
        for name, item in (figures.get("figures") or {}).items()
    }
    write_json(
        figures_dir / "figure_status.json",
        {
            "run_id": config.run_id,
            "figures": figure_status,
            "note": FIGURES_NOTE,
        },
    )

    summary_payload = dict(summary)
    summary_payload.setdefault("run_id", config.run_id)
    summary_payload.setdefault("stage", "holdout")
    summary_payload.setdefault("study_scale", config.study_scale)
    summary_payload.setdefault("data_origin", "SYNTHETIC_TEST")
    summary_payload.setdefault("physical_call_count", PHYSICAL_CALL_COUNT)
    summary_payload.setdefault(
        "physics_guard",
        {"expected": 0, "status": "PASS", "message": "holdout 全程 0 次真实求解器调用"},
    )
    summary_payload["history_rows"] = history_rows
    summary_payload["products_written"] = list(HOLDOUT_PRODUCT_FILES)
    write_json(root / "summary.json", summary_payload)
    (root / "README.md").write_text(
        _render_holdout_readme(summary_payload, config=config), encoding="utf-8", newline="\n"
    )
    manifest = build_data_manifest(root)
    write_json(root / "data_manifest.json", manifest)
    return sorted(HOLDOUT_PRODUCT_FILES)


def _parse_int_list(text: str) -> tuple[int, ...]:
    values = [item.strip() for item in str(text).split(",") if item.strip()]
    return tuple(int(item) for item in values)


def run_m5_study(
    config: M5RunnerConfig,
    *,
    workers: int = 1,
    progress: Callable[[str, dict[str, Any]], None] | None = None,
    calibration_report: fv2.CalibrationReport | None = None,
    design_space: Any | None = None,
) -> dict[str, Any]:
    """阶段编排入口：calibration / freeze / holdout 三阶段共用同一 run_id 目录。"""
    if not isinstance(config, M5RunnerConfig):
        raise M5RunnerError("config 必须是 M5RunnerConfig")
    if progress is not None and not callable(progress):
        raise M5RunnerError("progress 必须可调用（event, payload）")
    if config.stage == "calibration":
        return run_calibration_stage(
            config,
            design_space=design_space,
            calibration_report=calibration_report,
            progress=progress,
        )
    if config.stage == "freeze":
        return run_freeze_stage(
            config, calibration_report=calibration_report, design_space=design_space
        )
    return run_holdout_stage(config, workers=int(workers), progress=progress)


def build_argument_parser() -> argparse.ArgumentParser:
    """命令行参数（三阶段共用；holdout 必须提供已冻结前置路径）。"""
    parser = argparse.ArgumentParser(
        description="P4-M5 离线合成实验运行器（calibration -> freeze -> holdout；SYNTHETIC_ONLY）"
    )
    parser.add_argument("--stage", required=True, choices=list(STAGES))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--output-root", default=str(RUNS_ROOT))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--family-seed", type=int, default=20261102)
    parser.add_argument("--meta-train-tasks", type=int, default=60)
    parser.add_argument("--meta-validation-tasks", type=int, default=20)
    parser.add_argument("--meta-test-tasks", type=int, default=20)
    parser.add_argument("--ood-tasks", type=int, default=10)
    parser.add_argument("--negative-control-tasks", type=int, default=10)
    parser.add_argument("--support-pool-size", type=int, default=128)
    parser.add_argument("--query-size", type=int, default=64)
    parser.add_argument("--budgets", default="64,128")
    parser.add_argument("--optimization-seeds", default="0,1,2,3,4,5,6,7,8,9")
    parser.add_argument("--meta-seeds", default="0,1,2")
    parser.add_argument("--max-meta-steps", type=int, default=200)
    parser.add_argument("--pretrain-steps", type=int, default=50)
    parser.add_argument("--determinism-reruns", type=int, default=3)
    parser.add_argument("--calibration-report", default="")
    parser.add_argument("--frozen-family", default="")
    parser.add_argument("--preregistration", default="")
    parser.add_argument("--split-manifest", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：成功阶段返回 0；失败/门禁未过返回 1（不掩盖失败）。"""
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    def _optional_path(text: str) -> Path | None:
        return Path(text) if str(text).strip() else None

    config = M5RunnerConfig(
        run_id=args.run_id,
        output_root=Path(args.output_root),
        stage=args.stage,
        family_seed=int(args.family_seed),
        meta_train_tasks=int(args.meta_train_tasks),
        meta_validation_tasks=int(args.meta_validation_tasks),
        meta_test_tasks=int(args.meta_test_tasks),
        ood_tasks=int(args.ood_tasks),
        negative_control_tasks=int(args.negative_control_tasks),
        support_pool_size=int(args.support_pool_size),
        query_size=int(args.query_size),
        budgets=_parse_int_list(args.budgets),
        optimization_seeds=_parse_int_list(args.optimization_seeds),
        meta_seeds=_parse_int_list(args.meta_seeds),
        max_meta_steps=int(args.max_meta_steps),
        pretrain_steps=int(args.pretrain_steps),
        determinism_reruns=int(args.determinism_reruns),
        calibration_report_path=_optional_path(args.calibration_report),
        frozen_family_path=_optional_path(args.frozen_family),
        preregistration_path=_optional_path(args.preregistration),
        split_manifest_path=_optional_path(args.split_manifest),
    )
    result = run_m5_study(config, workers=int(args.workers))
    payload = {
        "stage": result.get("stage"),
        "status": result.get("status"),
        "run_dir": result.get("run_dir"),
        "study_scale": result.get("study_scale", config.study_scale),
        "products_written": result.get("products_written"),
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["status"] in ("CALIBRATED", "FROZEN", "VALID", "NO_CELL_IN_TARGET") else 1


_NOT_APPROVED = (
    "P4-REAL-LF 真实低可信度求解器调用（未批准）",
    "P4-MULTIFIDELITY-REAL 真实多保真（未批准）",
    "真实跨任务元训练（未批准）",
)

__all__ = [
    "FALLBACK_NOTE",
    "FIGURES_NOTE",
    "HOLDOUT_PRODUCT_FILES",
    "M5RunnerConfig",
    "M5RunnerError",
    "PreregistrationNotFrozen",
    "SOLVER_VALIDATION_COLUMNS",
    "SOLVER_VALIDATION_ROWS",
    "build_argument_parser",
    "build_holdout_groups",
    "build_proxy_artifacts",
    "expected_holdout_plan",
    "holdout_split_tasks",
    "load_holdout_prerequisites",
    "main",
    "reference_objectives_by_task",
    "run_calibration_stage",
    "run_freeze_stage",
    "run_holdout_stage",
    "run_m5_study",
]


if __name__ == "__main__":
    raise SystemExit(main())
