"""P4-CODE 离线元学习实验运行器（§5.6/§9/§10/§11）。

职责：
1. 构造合成任务族（F-QE 默认 60/20/20/10/10）并做参考解/泄漏/负控制断言；
2. M1 快速适应矩阵：R/P/M 三臂 × K∈{0,1,5,10}，只用解析合成标签；
3. M2 同预算优化矩阵：五臂 × seeds={0..4} × 预算 64 次真实（合成）评估；
4. 写出 §11.2 固定产物集（JSON/CSV/README），并做 data_manifest 哈希；
5. 物理守卫：启动/结束断言 physical_call_count=0，任何评估器报告非零立即中止并写
   status=PHYSICS_GUARD_VIOLATION（不写正常 0 计数 summary）；
6. 确定性：seed=0 独立重跑 3 次，比较 metrics.csv / optimization_summary.csv
   （wall_s 为非确定列，比较时剔除并记录）。

边界：不 import 任何 RCAIDE Mission / SU2 / VSPAERO / OpenVSP / Gmsh 调用面；
真实 evaluator 必须 fail-closed；本运行器只允许解析合成 evaluator。
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from ..aircraft.design_space import DesignSpace, load_design_space
from .baseline_arms import (
    ARMS,
    DE_ARM,
    DE_GENERATIONS,
    DE_POPULATION_SIZE,
    BO_INITIAL_DESIGN_COUNT,
    MAML_INIT_ARM,
    MAML_INIT_CANDIDATE_COUNT,
    MAML_INIT_DIVERSITY_CANDIDATE_COUNT,
    MAML_INIT_INITIAL_DESIGN_COUNT,
    PHYSICAL_CALL_COUNT,
    PHYSICS_GUARD_EXPECTED,
    TRUE_EVALUATION_BUDGET,
    BaselineArmError,
    PhysicsGuardViolation,
    compare_initializers,
    make_synthetic_task_evaluator,
    paired_statistics,
    run_bo_arm,
    run_de_arm,
    run_maml_init_arm,
    shared_initial_designs,
)
from .data_contract import (
    CONSTRAINT_NAMES,
    CONTEXT_NAMES,
    OOD_FLAG_NAME,
    DESIGN_LOWER,
    DESIGN_NAMES,
    DESIGN_UPPER,
    DESIGN_SET,
    PHYSICS_GUARD_EXPECTED as CONTRACT_PHYSICS_GUARD_EXPECTED,
    SPLITS,
    MetaSample,
    archive_split_for,
    design_to_normalized,
    require_valid,
    to_archive_records,
    to_archive_splits,
)
from .maml import (
    FD_DEFAULT_EPSILON,
    FD_DEFAULT_TOLERANCE,
    MAMLError,
    MAMLConfig,
    ParameterSet,
    TaskEpisode,
    build_small_model,
    finite_difference_gradient_check,
    init_parameters,
    inner_adapt,
    meta_train,
    torch_available,
    torch_import_error,
    write_finite_difference_check,
)
from .surrogate import encode_features, regression_metrics
from .task_family import (
    SyntheticTask,
    TaskFamilyConfig,
    assert_reference_solutions,
    build_task_family,
    default_task_family_config,
    family_fingerprint,
    load_task_family_config,
    serialize_task,
)

STAGE = "P4-CODE"
DATA_ORIGIN = "SYNTHETIC_TEST"
RUN_PREFIX = "p4-synthetic"
EVALUATOR_ID = "synthetic__analytic__12d_lifting_surfaces__v1"
DESIGN_SET_NAME = DESIGN_SET

#: M1 三臂（R=随机初始化、P=监督预训练、M=MAML 一阶）。
M1_ARMS = ("R", "P", "M")
#: M1 K-shot 网格（§9）。
DEFAULT_KS = (0, 1, 5, 10)
#: M2 正式 seeds（§10；可用 OfflineRunnerConfig.optimization_seeds 覆盖，正式 run 必须 5 个）。
M2_SEEDS = (0, 1, 2, 3, 4)
#: 全臂共享的 support 适应步数预算（§9 S_adapt=50）。
S_ADAPT = 50
#: M1 代理网络结构（CPU 可跑；等价性声明恒 false）。
HIDDEN_SIZES = (16, 16)
#: M2 代理网络结构（MAML-init 打分需要 objective+约束多输出）。
M2_HIDDEN_SIZES = (16, 16)

#: 主终点（预注册，§9/§10）。
PRIMARY_ENDPOINT = "meta_test K=5 query RMSE (MAML vs P, MAML vs R)"
SECONDARY_ENDPOINTS = (
    "meta_test K=0/1/10 query RMSE/MAE",
    "meta_test_ood K=0/1/5/10 query RMSE/MAE（单列）",
    "negative_control label-shuffle K-shot 诊断（不进主终点）",
    "M2 best_feasible_value/gap_to_reference/first_feasible_eval_index @ B=64",
    "M2 fallback: best_objective_raw / min_constraint_violation_sum / feasible_hit_rate",
)
STATISTICS_PLAN = {
    "paired_unit": "per (task, seed)",
    "bootstrap_samples": 10000,
    "confidence": 0.95,
    "effect_size": "paired_cohen_d",
    "test": "wilcoxon_signed_rank（n>=5 且非全零时计算）",
}

FORBIDDEN_MODULE_PREFIXES = (
    "RCAIDE",
    "SU2",
    "VSPAERO",
    "OpenVSP",
    "openvsp",
    "Gmsh",
    "gmsh",
    "su2",
)

REQUIRED_CSV_COLUMNS: dict[str, tuple[str, ...]] = {
    "training_history": (
        "run_id", "arm", "split", "task_id", "family", "iteration", "epoch",
        "loss_support", "loss_query", "grad_norm", "lr", "seed", "wall_s", "status",
    ),
    "adaptation_results": (
        "run_id", "task_id", "split", "family", "arm", "K", "seed", "n_support",
        "n_query", "adapt_steps", "mae_raw", "rmse_raw", "mae_norm", "rmse_norm",
        "r2", "max_abs_err", "wall_s", "status",
    ),
    "metrics": (
        "experiment_id", "phase", "split", "family", "arm", "K", "task_id", "seed",
        "metric", "value", "unit", "aggregation", "n", "status",
    ),
    "optimization_history": (
        "run_id", "task_id", "split", "family", "arm", "seed", "eval_index",
        *("design_u_%d" % index for index in range(12)),
        "objective", "feasible", "constraints_json", "cache_hit", "billable",
        "status", "wall_s", "best_feasible_so_far", "best_value_so_far",
    ),
    "optimization_summary": (
        "run_id", "task_id", "split", "family", "arm", "seed", "budget",
        "true_evals_used", "cache_hits", "failed_evals", "best_feasible_value",
        "gap_to_reference", "first_feasible_eval_index", "feasible_count",
        "violation_rate", "wall_s", "status", "best_objective_raw",
        "min_constraint_violation_sum", "feasible_hit_rate", "feasibility_expected_zero",
    ),
}


class OfflineRunnerError(RuntimeError):
    """离线运行器输入/状态错误（fail-closed）。"""


class FiniteDifferenceFailure(OfflineRunnerError):
    """§7.2 梯度门禁失败：M2 不得启动，summary.status=FINITE_DIFFERENCE_FAILED。"""

    def __init__(self, message: str, result: Mapping[str, Any]) -> None:
        super().__init__(message)
        #: 保留 FD 原始结果（含解析/数值梯度数组），落盘 finite_difference_check.json。
        self.result = dict(result)


@dataclass(frozen=True)
class OfflineRunnerConfig:
    """离线运行配置（§5.6 字段 + Lead A8 批准的 optimization_seeds）。"""

    run_id: str
    output_root: Path
    family_config_path: Path | None = None
    ks: tuple[int, ...] = DEFAULT_KS
    seed: int = 42
    max_meta_steps: int = 2000
    budget_true_evaluations: int = TRUE_EVALUATION_BUDGET
    bo_initial_designs: int = BO_INITIAL_DESIGN_COUNT
    de_population: int = DE_POPULATION_SIZE
    de_generations: int = DE_GENERATIONS
    maml_init_candidate_count: int = MAML_INIT_CANDIDATE_COUNT
    maml_init_initial_designs: int = MAML_INIT_INITIAL_DESIGN_COUNT
    maml_init_diversity_candidate_count: int = MAML_INIT_DIVERSITY_CANDIDATE_COUNT
    determinism_reruns: int = 3
    physical_guard_expected: int = PHYSICS_GUARD_EXPECTED
    #: Lead A8 批准：M2 seeds（正式 run 必须 (0,1,2,3,4)；单测可缩小）。
    optimization_seeds: tuple[int, ...] = M2_SEEDS

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise OfflineRunnerError("run_id 必须是非空字符串")
        if any(sep in self.run_id for sep in ("/", "\\", "..")):
            raise OfflineRunnerError(f"run_id 不能包含路径分隔符: {self.run_id!r}")
        object.__setattr__(self, "output_root", Path(self.output_root))
        if self.family_config_path is not None:
            object.__setattr__(self, "family_config_path", Path(self.family_config_path))
        if not isinstance(self.ks, (tuple, list)) or not self.ks:
            raise OfflineRunnerError("ks 必须是非空序列")
        for value in self.ks:
            if type(value) is not int or value < 0:
                raise OfflineRunnerError(f"ks 必须是非负整数，实际 {value!r}")
        object.__setattr__(self, "ks", tuple(int(value) for value in self.ks))
        for name in (
            "seed", "max_meta_steps", "budget_true_evaluations", "bo_initial_designs",
            "de_population", "de_generations", "maml_init_candidate_count",
            "maml_init_initial_designs", "maml_init_diversity_candidate_count",
            "determinism_reruns", "physical_guard_expected",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise OfflineRunnerError(f"{name} 必须是非负整数，实际 {value!r}")
        if self.max_meta_steps < 1:
            raise OfflineRunnerError("max_meta_steps 必须 >= 1")
        if self.budget_true_evaluations < 1:
            raise OfflineRunnerError("budget_true_evaluations 必须 >= 1")
        if self.determinism_reruns < 1:
            raise OfflineRunnerError("determinism_reruns 必须 >= 1")
        if self.physical_guard_expected != PHYSICS_GUARD_EXPECTED:
            raise OfflineRunnerError(
                f"P4-CODE 物理守卫期望值必须是 {PHYSICS_GUARD_EXPECTED}，"
                f"实际 {self.physical_guard_expected}"
            )
        if not isinstance(self.optimization_seeds, (tuple, list)) or not self.optimization_seeds:
            raise OfflineRunnerError("optimization_seeds 必须是非空序列")
        for value in self.optimization_seeds:
            if type(value) is not int or value < 0:
                raise OfflineRunnerError(f"optimization_seeds 必须是非负整数，实际 {value!r}")
        object.__setattr__(self, "optimization_seeds", tuple(int(v) for v in self.optimization_seeds))
        if len(set(self.optimization_seeds)) != len(self.optimization_seeds):
            raise OfflineRunnerError("optimization_seeds 不能重复")


# ---------------------------------------------------------------------------
# 通用工具：时间、JSON/CSV、哈希、manifest
# ---------------------------------------------------------------------------
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime | None = None) -> str:
    value = (moment or utc_now()).astimezone(timezone.utc)
    return value.isoformat(timespec="seconds")


def make_run_id(prefix: str = RUN_PREFIX) -> str:
    """生成 p4-synthetic-<UTC>Z 形式的运行 ID。"""
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"


def write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
    target.write_text(text + "\n", encoding="utf-8", newline="\n")
    return target


def write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=_json_default))
            handle.write("\n")
    return target


def write_csv(
    path: str | Path,
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str] | None = None,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    column_names = tuple(columns) if columns is not None else tuple(rows[0].keys()) if rows else ()
    if not column_names:
        raise OfflineRunnerError(f"CSV {target} 没有列定义")
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(column_names), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _csv_value(row.get(name)) for name in column_names})
    return target


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return "true" if bool(value) else "false"
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            return ""
        return repr(number)
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, Path):
        return str(value)
    return str(value)


def sha256_file_normalized(path: str | Path) -> tuple[str, int]:
    """按 hash_mode=CRLF->LF 计算文件 sha256 与规范化字节数。"""
    data = Path(path).read_bytes()
    normalized = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest(), len(normalized)


def build_data_manifest(run_dir: str | Path, exclude: Sequence[str] = ()) -> dict[str, Any]:
    """生成 data_manifest.json 内容（不含自身；记录每个文件的 sha256/bytes）。"""
    root = Path(run_dir).resolve()
    manifest_path = root / "data_manifest.json"
    excluded = {str(Path(item).resolve()) for item in exclude}
    excluded.add(str(manifest_path))
    files: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if str(path.resolve()) in excluded:
            continue
        relative = path.relative_to(root).as_posix()
        digest, size = sha256_file_normalized(path)
        files.append({"path": relative, "sha256": digest, "bytes": size})
        total_bytes += size
    return {
        "hash_mode": "CRLF->LF",
        "excluded": ["data_manifest.json", *sorted(str(item) for item in exclude)],
        "file_count": len(files),
        "total_bytes": total_bytes,
        "files": files,
    }


def _module_version(name: str) -> str:
    try:
        from importlib import metadata

        return metadata.version(name)
    except Exception:  # pragma: no cover - 依赖缺失时如实标 UNKNOWN
        return "UNKNOWN"


def environment_payload(run_id: str, physical_call_count: int = 0) -> dict[str, Any]:
    """environment.json：依赖版本/平台/物理调用声明。"""
    return {
        "run_id": run_id,
        "stage": STAGE,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "numpy": _module_version("numpy"),
        "scipy": _module_version("scipy"),
        "scikit-learn": _module_version("scikit-learn"),
        "torch": _module_version("torch"),
        "matplotlib": _module_version("matplotlib"),
        "maml_opt": _module_version("maml-opt"),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count() or 1,
        "gpu_available": False,
        "device": "cpu",
        "physical_call_count": int(physical_call_count),
        "physical_guard_expected": PHYSICS_GUARD_EXPECTED,
        "data_origin": DATA_ORIGIN,
    }


def repo_git_state(repo_root: str | Path) -> dict[str, Any]:
    """读取 git sha/dirty（不修改仓库；未知写 UNKNOWN）。"""
    import subprocess

    root = str(repo_root)
    try:
        sha = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=20,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", root, "status", "--porcelain"],
            capture_output=True, text=True, check=True, timeout=20,
        ).stdout
        dirty = bool(status.strip())
        return {
            "git_sha": sha,
            "worktree_dirty": dirty,
            "git_sha_label": f"{sha}-dirty" if dirty else sha,
        }
    except Exception as exc:  # pragma: no cover - git 不可用时如实标 UNKNOWN
        return {
            "git_sha": "UNKNOWN",
            "worktree_dirty": None,
            "git_sha_label": "UNKNOWN",
            "git_error": f"{type(exc).__name__}: {exc}",
        }


def _forbidden_modules_present() -> list[str]:
    """当前进程 sys.modules 中已加载的禁止模块名（排序后返回）。"""
    loaded: list[str] = []
    for name in list(sys.modules):
        for prefix in FORBIDDEN_MODULE_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                loaded.append(name)
                break
    return sorted(loaded)


_IMPORT_STATEMENT_RE = re.compile(r"(?m)^[ \t]*(?:from|import)[ \t]+[^\n]*")


def scan_forbidden_import_statements(source_text: str) -> list[str]:
    """静态扫描任意源码文本中的禁止 import 语句（§1.3 硬隔离）。

    逐行匹配 from/import 语句（允许缩进与行内多模块），再检查模块名是否落在
    FORBIDDEN_MODULE_PREFIXES 内；供内部包扫描与单元测试共用（M1-F02）。
    """
    violations: list[str] = []
    for match in _IMPORT_STATEMENT_RE.finditer(source_text):
        statement = match.group(0).strip()
        is_from = statement.startswith("from")
        body = statement[len("from") :] if is_from else statement[len("import") :]
        if is_from:
            head = body.split()
            names = [head[0]] if head else []
        else:
            names = [part.split()[0] for part in body.split(",") if part.split()]
        for name in names:
            module = name.strip("()[]{}")
            if not module:
                continue
            for prefix in FORBIDDEN_MODULE_PREFIXES:
                if module == prefix or module.startswith(prefix + "."):
                    violations.append(statement)
                    break
            else:
                continue
            break
    return violations


def _forbidden_import_statements() -> list[str]:
    """静态扫描 meta_learning 包源码，找禁止的 import 语句（§1.3 硬隔离）。"""
    violations: list[str] = []
    package_dir = Path(__file__).resolve().parent
    for path in sorted(package_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for statement in scan_forbidden_import_statements(text):
            violations.append(f"{path.name}: {statement}")
    return violations


def assert_no_forbidden_modules(baseline: Sequence[str] | None = None) -> dict[str, Any]:
    """隔离断言：本 run 不得新增真实物理/求解器模块，且本包源码不得 import 它们。

    说明：P1–P3 既有测试可能在同一进程中合法 import RCAIDE 等包（它们测试的是历史
    P1–P3 行为，不属于本 run）；因此这里以上一层快照为基线，只拦截「本 run 新增」
    的真实模块，并静态扫描 meta_learning 源码，确保运行器自身零耦合（§1.3）。
    """
    snapshot = set(baseline or ())
    current = _forbidden_modules_present()
    newly_loaded = sorted(set(current) - snapshot)
    source_violations = _forbidden_import_statements()
    if newly_loaded or source_violations:
        raise OfflineRunnerError(
            "P4-CODE 运行器检测到真实物理/求解器模块已加载（§1.3 硬隔离）："
            + "; ".join(newly_loaded + source_violations)
        )
    return {
        "forbidden_modules_loaded": newly_loaded,
        "baseline_forbidden_modules": sorted(snapshot),
        "source_scan_violations": source_violations,
        "checked_prefixes": list(FORBIDDEN_MODULE_PREFIXES),
    }


class GuardedEvaluator:
    """包一层物理守卫：每次评估/计数非零即抛 PhysicsGuardViolation（fail-closed）。"""

    def __init__(self, evaluator: Any, *, label: str = "synthetic") -> None:
        self.evaluator = evaluator
        self.label = label
        self.call_count = 0

    def __call__(self, design_u: np.ndarray) -> dict[str, Any]:
        result = self.evaluator(design_u)
        self.call_count += 1
        self._check(result)
        return result

    def _check(self, result: Any) -> None:
        reported = None
        if isinstance(result, Mapping):
            reported = result.get("physical_call_count")
        counter = int(getattr(self.evaluator, "physical_call_count", 0))
        if reported not in (None, 0, 0.0) or counter != 0:
            raise PhysicsGuardViolation(
                f"{self.label} evaluator 报告 physical_call_count={reported!r}"
                f"（内部计数 {counter}），立即中止整次 run",
                physical_call_count=int(reported if reported is not None else counter),
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.evaluator, name)


def support_subset_indices(task_id: str, seed: int, pool_size: int, k_shot: int) -> np.ndarray:
    """与 adaptation._subset_support 同构的确定性置换（任务×seed 固定，K 嵌套）。"""
    if type(pool_size) is not int or pool_size < 1:
        raise OfflineRunnerError("pool_size 必须是正整数")
    if type(k_shot) is not int or k_shot < 0 or k_shot > pool_size:
        raise OfflineRunnerError(f"k_shot 必须在 [0,{pool_size}]，实际 {k_shot!r}")
    digest = hashlib.sha1(
        "|".join(str(part) for part in (task_id, seed, "support_subset")).encode("utf-8")
    ).digest()
    stable_seed = int.from_bytes(digest[:8], "big") % (2**63 - 1)
    order = np.random.default_rng(stable_seed).permutation(pool_size)
    return order[:k_shot]
# ---------------------------------------------------------------------------
# 步骤 B：任务族/设计空间/特征与标签块（M1 与 M2 共用）
# ---------------------------------------------------------------------------
DESIGN_SPACE_12D_PATH = Path(__file__).resolve().parents[1] / "configs" / "design_space_12d_lifting_surfaces.yaml"
DESIGN_LOWER_ARRAY = np.asarray(DESIGN_LOWER, dtype=np.float64)
DESIGN_UPPER_ARRAY = np.asarray(DESIGN_UPPER, dtype=np.float64)


def load_design_space_12d() -> DesignSpace:
    """显式加载 12D 设计空间（禁止无参默认 15D；§2.3 M-08 回归）。"""
    if not DESIGN_SPACE_12D_PATH.is_file():
        raise OfflineRunnerError(f"12D 设计空间配置缺失: {DESIGN_SPACE_12D_PATH}")
    space = load_design_space(DESIGN_SPACE_12D_PATH)
    if space.design_dim != 12 or space.design_set != DESIGN_SET:
        raise OfflineRunnerError(
            f"设计空间不符合合同：dim={space.design_dim}, design_set={space.design_set!r}"
        )
    return space


def resolve_family_config(config: OfflineRunnerConfig) -> TaskFamilyConfig:
    """加载任务族配置（None=默认 F-QE 60/20/20/10/10，§4.3）。"""
    family_config = load_task_family_config(config.family_config_path)
    if config.ks and max(config.ks) > family_config.support_pool_size:
        raise OfflineRunnerError(
            f"ks 最大值 {max(config.ks)} 超过 support_pool_size={family_config.support_pool_size}"
        )
    return family_config


def compute_config_hash(
    family_config: TaskFamilyConfig,
    design_space: DesignSpace,
    runner_config: OfflineRunnerConfig,
) -> str:
    """config_hash = sha256(设计空间 + 任务族 + 运行配置)（§2.3）。"""
    payload = {
        "stage": STAGE,
        "family_fingerprint": family_fingerprint(family_config),
        "design_space": {
            "design_set": design_space.design_set,
            "names": list(design_space.names),
            "fixed_names": list(design_space.fixed_names),
            "bounds": {
                variable.name: list(variable.bounds)
                for variable in design_space.variables
            },
        },
        "ks": list(runner_config.ks),
        "budget_true_evaluations": runner_config.budget_true_evaluations,
        "bo_initial_designs": runner_config.bo_initial_designs,
        "de_population": runner_config.de_population,
        "de_generations": runner_config.de_generations,
        "maml_init": {
            "candidate_count": runner_config.maml_init_candidate_count,
            "initial_design_count": runner_config.maml_init_initial_designs,
            "diversity_candidate_count": runner_config.maml_init_diversity_candidate_count,
        },
        "optimization_seeds": list(runner_config.optimization_seeds),
        "max_meta_steps": runner_config.max_meta_steps,
        "seed": runner_config.seed,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def task_target_names(task: SyntheticTask) -> tuple[str, ...]:
    """任务目标列：objective + 启用的约束槽位（槽位名即物理约束名）。"""
    return ("objective",) + tuple(task.enabled_constraint_names)


def encode_task_block(task: SyntheticTask, designs_u: np.ndarray, *, label: str = "") -> dict[str, Any]:
    """把单位设计块编码为特征/标签（真值解析求值，无物理调用）。"""
    from .surrogate import encode_features

    designs = np.asarray(designs_u, dtype=np.float64)
    if designs.ndim != 2 or designs.shape[1] != 12:
        raise OfflineRunnerError(f"{task.task_id}{label} 设计块必须为 (n,12)，实际 {designs.shape}")
    if not np.all(np.isfinite(designs)) or np.any(designs < 0.0) or np.any(designs > 1.0):
        raise OfflineRunnerError(f"{task.task_id}{label} 设计必须位于 [0,1]^12")
    truth = task.truth(designs)
    names = task_target_names(task)
    targets = np.column_stack([np.asarray(truth[name], dtype=np.float64) for name in names])
    if not np.all(np.isfinite(targets)):
        raise OfflineRunnerError(f"{task.task_id}{label} 真值出现非有限值")
    return {
        "designs": designs,
        "features": encode_features(designs, task.context, CONTEXT_NAMES),
        "targets": targets,
        "target_names": names,
        "objective": np.asarray(truth["objective"], dtype=np.float64),
        "feasibility": np.asarray(truth["feasibility"], dtype=bool),
    }


def build_task_blocks(tasks: Sequence[SyntheticTask]) -> dict[str, dict[str, Any]]:
    """为每个任务构造 support/query 特征标签块（含负控制伪任务）。"""
    blocks: dict[str, dict[str, Any]] = {}
    for task in tasks:
        blocks[task.task_id] = {
            "task": task,
            "support": encode_task_block(task, task.support_designs(), label=".support"),
            "query": encode_task_block(task, task.query_designs(), label=".query"),
        }
    return blocks


def _meta_episodes(blocks: Mapping[str, Any], task_ids: Sequence[str]) -> list[TaskEpisode]:
    """meta_train/meta_validation 任务 -> TaskEpisode（support=池、query=query 集）。"""
    episodes: list[TaskEpisode] = []
    for task_id in task_ids:
        block = blocks[task_id]
        episodes.append(
            TaskEpisode(
                support_features=block["support"]["features"],
                support_targets=block["support"]["targets"][:, :1],
                query_features=block["query"]["features"],
                query_targets=block["query"]["targets"][:, :1],
                task_id=task_id,
            )
        )
    return episodes


def _make_artifact(
    parameters: ParameterSet,
    config: MAMLConfig,
    *,
    adaptation_method: str,
    training: Mapping[str, Any],
) -> dict[str, Any]:
    """统一 artifact 形态（adaptation._artifact_view 兼容；不含任何 query 信息）。"""
    return {
        "parameters": parameters,
        "config": config,
        "context_names": CONTEXT_NAMES,
        "adaptation_method": adaptation_method,
        "fine_tuning_steps": S_ADAPT,
        "backend": "torch" if torch_available() else "unavailable",
        "equivalence_claimed": False,
        "training": dict(training),
    }


def build_m1_artifacts(
    blocks: Mapping[str, Any],
    tasks: Sequence[SyntheticTask],
    runner_config: OfflineRunnerConfig,
) -> dict[str, Any]:
    """训练 M1 三臂参数：M=MAML 一阶、P=监督预训练、R=随机初始化（同结构同预算约束）。"""
    if not torch_available():
        raise OfflineRunnerError(
            "torch 不可用，M1 训练臂无法运行（P4-CODE 要求 torch）："
            f"{torch_import_error()}"
        )
    input_dim = 12 + len(CONTEXT_NAMES)
    output_dim = 1  # M1 只拟合 objective；约束由 M2 代理单独输出
    base = MAMLConfig(
        input_dim=input_dim,
        output_dim=output_dim,
        hidden_sizes=HIDDEN_SIZES,
        inner_lr=0.01,
        inner_steps=5,
        outer_lr=1e-3,
        tasks_per_batch=min(8, max(1, len([task for task in tasks if task.split == "meta_train"]))),
        first_order=True,
        seed=runner_config.seed,
        backend="torch",
    )
    train_ids = [task.task_id for task in tasks if task.split == "meta_train"]
    if not train_ids:
        raise OfflineRunnerError("meta_train 任务为空，无法训练 M1 臂")
    episodes = _meta_episodes(blocks, train_ids)
    eval_config = MAMLConfig(
        input_dim=input_dim,
        output_dim=output_dim,
        hidden_sizes=HIDDEN_SIZES,
        inner_lr=0.01,
        inner_steps=S_ADAPT,
        outer_lr=1e-3,
        tasks_per_batch=base.tasks_per_batch,
        first_order=True,
        seed=runner_config.seed,
        backend="torch",
    )
    training_rows: list[dict[str, Any]] = []
    meta_info: dict[str, Any] = {}

    # --- M 臂：一阶 MAML 元训练（预算 max_meta_steps）---
    wall_start = time.perf_counter()
    trained = meta_train(episodes, base, max_steps=runner_config.max_meta_steps)
    meta_wall = time.perf_counter() - wall_start
    meta_info = {
        "status": trained.get("status"),
        "steps": int(trained.get("steps", 0)),
        "failure": trained.get("failure"),
        "history_length": len(trained.get("history", ())),
        "wall_s": float(meta_wall),
        "outer_loss_first": (trained["history"][0]["outer_loss"] if trained.get("history") else None),
        "outer_loss_last": (trained["history"][-1]["outer_loss"] if trained.get("history") else None),
    }
    if trained.get("status") != "VALID":
        raise OfflineRunnerError(
            "M1 MAML 元训练失败（fail-closed，不伪造参数）："
            f"status={trained.get('status')!r} failure={trained.get('failure')!r}"
        )
    for entry in trained.get("history", ()):
        training_rows.append(
            {
                "run_id": runner_config.run_id,
                "arm": "M",
                "split": "meta_train",
                "task_id": "",
                "family": blocks[train_ids[0]]["task"].family,
                "iteration": int(entry.get("step", entry.get("iteration", len(training_rows)))),
                "epoch": 0,
                "loss_support": float(entry["inner_loss_last"]),
                "loss_query": float(entry["outer_loss"]),
                "grad_norm": float(entry["grad_norm"]),
                "lr": float(base.outer_lr),
                "seed": runner_config.seed,
                "wall_s": float(meta_wall / max(1, len(trained.get("history", ())))),
                "status": "VALID",
            }
        )
    m_parameters = trained["final_parameters"]
    if isinstance(m_parameters, Mapping):
        m_parameters = ParameterSet.from_dict(m_parameters)
    m_artifact = _make_artifact(m_parameters, eval_config, adaptation_method="maml", training=meta_info)

    # --- P 臂：在 meta-train 全部样本上做与 S_adapt 同步数的监督预训练 ---
    pretrain_steps = int(min(S_ADAPT, runner_config.max_meta_steps))
    pretrain_features = np.concatenate(
        [blocks[task_id]["support"]["features"] for task_id in train_ids]
        + [blocks[task_id]["query"]["features"] for task_id in train_ids],
        axis=0,
    )
    pretrain_targets = np.concatenate(
        [blocks[task_id]["support"]["targets"][:, :1] for task_id in train_ids]
        + [blocks[task_id]["query"]["targets"][:, :1] for task_id in train_ids],
        axis=0,
    )
    pretrain_episode = TaskEpisode(
        pretrain_features, pretrain_targets, pretrain_features, pretrain_targets
    )
    pretrain_config = MAMLConfig(
        input_dim=input_dim,
        output_dim=output_dim,
        hidden_sizes=HIDDEN_SIZES,
        inner_lr=0.01,
        inner_steps=pretrain_steps,
        outer_lr=1e-3,
        tasks_per_batch=1,
        first_order=True,
        seed=runner_config.seed,
        backend="torch",
    )
    wall_start = time.perf_counter()
    init_params = init_parameters(eval_config, seed=runner_config.seed)
    pretrained_params, pretrain_losses = inner_adapt(init_params, pretrain_episode, pretrain_config)
    pretrain_wall = time.perf_counter() - wall_start
    for step, loss in enumerate(pretrain_losses):
        training_rows.append(
            {
                "run_id": runner_config.run_id,
                "arm": "P",
                "split": "meta_train",
                "task_id": "",
                "family": blocks[train_ids[0]]["task"].family,
                "iteration": step,
                "epoch": 0,
                "loss_support": float(loss),
                "loss_query": float(loss),
                "grad_norm": float("nan"),
                "lr": float(pretrain_config.inner_lr),
                "seed": runner_config.seed,
                "wall_s": float(pretrain_wall / max(1, len(pretrain_losses))),
                "status": "VALID" if math.isfinite(float(loss)) else "NONFINITE",
            }
        )
    if not all(math.isfinite(float(loss)) for loss in pretrain_losses):
        raise OfflineRunnerError("P 臂监督预训练损失出现非有限值（fail-closed）")
    p_artifact = _make_artifact(
        pretrained_params,
        eval_config,
        adaptation_method="fine_tuning",
        training={
            "status": "VALID",
            "pretrain_steps": pretrain_steps,
            "pretrain_rows": int(pretrain_features.shape[0]),
            "wall_s": float(pretrain_wall),
            "final_loss": float(pretrain_losses[-1]) if pretrain_losses else None,
        },
    )

    # --- R 臂：同结构随机初始化（无任何训练；零样本基线）---
    r_params = init_parameters(eval_config, seed=runner_config.seed + 1)
    r_artifact = _make_artifact(
        r_params,
        eval_config,
        adaptation_method="from_scratch",
        training={"status": "RANDOM_INIT", "seed": runner_config.seed + 1},
    )
    return {
        "artifacts": {"M": m_artifact, "P": p_artifact, "R": r_artifact},
        "training_rows": training_rows,
        "meta_training": meta_info,
        "pretraining": p_artifact["training"],
        "eval_config": eval_config.to_dict(),
    }


# ---------------------------------------------------------------------------
# 步骤 B（续）：M1 快速适应矩阵
# ---------------------------------------------------------------------------
M1_EVAL_SPLITS = ("meta_test", "meta_test_ood", "negative_control")
_METRIC_UNITS = {
    "rmse_raw": "synthetic_objective",
    "mae_raw": "synthetic_objective",
    "rmse_norm": "1",
    "mae_norm": "1",
    "r2": "1",
    "max_abs_err": "synthetic_objective",
    "final_adapt_loss": "synthetic_objective",
}


def _subset_support_block(
    block: Mapping[str, Any], task_id: str, seed: int, k_shot: int
) -> tuple[np.ndarray, np.ndarray]:
    """按 (task_id, seed) 确定性置换取前 K 点（K 嵌套；只读 support 池）。"""
    features = block["features"]
    targets = block["targets"][:, :1]
    order = support_subset_indices(task_id, seed, features.shape[0], k_shot)
    return features[order], targets[order]


def run_m1_study(
    blocks: Mapping[str, Any],
    tasks: Sequence[SyntheticTask],
    artifacts: Mapping[str, Any],
    runner_config: OfflineRunnerConfig,
) -> dict[str, Any]:
    """M1：R/P/M × K∈ks × {meta_test, meta_test_ood, negative_control}。"""
    from .adaptation import adapt_and_predict

    method_by_arm = {"M": "maml", "P": "fine_tuning", "R": "from_scratch"}
    split_tasks = [task for task in tasks if task.split in M1_EVAL_SPLITS]
    if not split_tasks:
        raise OfflineRunnerError("M1 评估任务为空（meta_test/meta_test_ood 至少各 1 个）")
    rows: list[dict[str, Any]] = []
    per_task: list[dict[str, Any]] = []
    for task in split_tasks:
        block = blocks[task.task_id]
        for arm in M1_ARMS:
            artifact = artifacts[arm]
            method = method_by_arm[arm]
            for k_shot in runner_config.ks:
                support_x, support_y = _subset_support_block(block["support"], task.task_id, runner_config.seed, k_shot)
                wall_start = time.perf_counter()
                result = adapt_and_predict(
                    artifact,
                    {"features": support_x, "targets": support_y},
                    {"features": block["query"]["features"], "targets": block["query"]["targets"][:, :1]},
                    method=method,
                    k_shot=k_shot,
                    config={"fine_tuning_steps": S_ADAPT, "hidden_sizes": HIDDEN_SIZES},
                )
                wall_s = time.perf_counter() - wall_start
                if result.physical_call_count != PHYSICAL_CALL_COUNT:
                    raise PhysicsGuardViolation(
                        f"M1 适应出现物理调用 physical_call_count={result.physical_call_count}",
                        physical_call_count=result.physical_call_count,
                    )
                metrics = dict(result.metrics)
                record = {
                    "run_id": runner_config.run_id,
                    "task_id": task.task_id,
                    "split": task.split,
                    "family": task.family,
                    "arm": arm,
                    "K": k_shot,
                    "seed": runner_config.seed,
                    "n_support": int(k_shot),
                    "n_query": int(result.predictions.shape[0]),
                    "adapt_steps": int(result.inner_steps),
                    "mae_raw": float(metrics.get("mae", float("nan"))),
                    "rmse_raw": float(metrics.get("rmse", float("nan"))),
                    "mae_norm": float(metrics.get("mae_norm", float("nan"))),
                    "rmse_norm": float(metrics.get("rmse_norm", float("nan"))),
                    "r2": float(metrics.get("r2", float("nan"))),
                    "max_abs_err": float(metrics.get("max_abs_err", float("nan"))),
                    "wall_s": float(wall_s),
                    "status": "VALID" if metrics.get("n_nonfinite", 0.0) == 0.0 else "NONFINITE",
                }
                rows.append(record)
                per_task.append(
                    {
                        **record,
                        "final_adapt_loss": (
                            float(result.losses[-1]) if result.losses else None
                        ),
                        "n_nonfinite": int(metrics.get("n_nonfinite", 0) or 0),
                    }
                )
    return {
        "adaptation_rows": rows,
        "per_task_rows": per_task,
        "task_splits": {
            split: [task.task_id for task in split_tasks if task.split == split] for split in M1_EVAL_SPLITS
        },
    }


def _group_metric_rows(
    per_task_rows: Sequence[Mapping[str, Any]],
    *,
    phase: str,
    group_fields: Sequence[str],
) -> list[dict[str, Any]]:
    """按分组字段生成 group_mean/group_std/ci95_low/ci95_high 长表行。"""
    metrics = ("rmse_raw", "mae_raw", "rmse_norm", "mae_norm", "r2", "max_abs_err", "final_adapt_loss")
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in per_task_rows:
        key = tuple(row.get(field) for field in group_fields)
        groups.setdefault(key, []).append(row)
    out: list[dict[str, Any]] = []
    for key, members in sorted(groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
        base = {field: key[index] for index, field in enumerate(group_fields)}
        for metric in metrics:
            values = [float(row[metric]) for row in members if row.get(metric) is not None and math.isfinite(float(row[metric]))]
            if not values:
                continue
            array = np.asarray(values, dtype=float)
            stats = paired_statistics(array, seed=0, bootstrap_samples=1000)
            for aggregation, value in (
                ("group_mean", float(np.mean(array))),
                ("group_std", float(np.std(array, ddof=1)) if array.size > 1 else 0.0),
                ("ci95_low", stats["ci_low"]),
                ("ci95_high", stats["ci_high"]),
            ):
                out.append(
                    {
                        "experiment_id": f"M1::{base.get('split', '')}::{base.get('arm', '')}::K{base.get('K', '')}",
                        "phase": phase,
                        "split": base.get("split", ""),
                        "family": base.get("family", ""),
                        "arm": base.get("arm", ""),
                        "K": base.get("K", ""),
                        "task_id": "",
                        "seed": base.get("seed", ""),
                        "metric": metric,
                        "value": value,
                        "unit": _METRIC_UNITS.get(metric, "1"),
                        "aggregation": aggregation,
                        "n": int(array.size),
                        "status": "VALID",
                    }
                )
    for row in per_task_rows:
        for metric in metrics:
            value = row.get(metric)
            if value is None or not math.isfinite(float(value)):
                continue
            out.append(
                {
                    "experiment_id": "M1::per_task",
                    "phase": phase,
                    "split": row.get("split", ""),
                    "family": row.get("family", ""),
                    "arm": row.get("arm", ""),
                    "K": row.get("K", ""),
                    "task_id": row.get("task_id", ""),
                    "seed": row.get("seed", ""),
                    "metric": metric,
                    "value": float(value),
                    "unit": _METRIC_UNITS.get(metric, "1"),
                    "aggregation": "per_task",
                    "n": 1,
                    "status": row.get("status", "VALID"),
                }
            )
    return out


def _primary_pairs(
    per_task_rows: Sequence[Mapping[str, Any]],
    *,
    split: str,
    k_shot: int,
    metric: str = "rmse_raw",
) -> dict[str, Any]:
    """按 task_id 对齐的配对统计：M-P 与 M-R（M 为处理臂）。"""
    table: dict[str, dict[str, float]] = {}
    for row in per_task_rows:
        if row.get("split") != split or int(row.get("K", -1)) != k_shot:
            continue
        value = row.get(metric)
        if value is None or not math.isfinite(float(value)):
            continue
        table.setdefault(str(row["task_id"]), {})[str(row["arm"])] = float(value)
    out: dict[str, Any] = {}
    for baseline in ("P", "R"):
        diffs = [
            values["M"] - values[baseline]
            for values in table.values()
            if "M" in values and baseline in values
        ]
        out[f"M_vs_{baseline}"] = (
            paired_statistics(diffs, seed=42) if diffs else {"n": 0, "note": "没有可配对任务"}
        )
    return {"split": split, "K": k_shot, "metric": metric, "pairs": out, "n_tasks": len(table)}


def m1_endpoint_statistics(
    per_task_rows: Sequence[Mapping[str, Any]],
    *,
    primary_k: int = 5,
) -> dict[str, Any]:
    """M1 预注册终点：主终点 meta_test K=5；次终点 K=0/1/10 + OOD + 负控制（单列）。"""
    primary = _primary_pairs(per_task_rows, split="meta_test", k_shot=primary_k)
    secondary = {
        f"meta_test_K{k}": _primary_pairs(per_task_rows, split="meta_test", k_shot=k)
        for k in (0, 1, 10)
        if k != primary_k
    }
    secondary["meta_test_ood_K5"] = _primary_pairs(per_task_rows, split="meta_test_ood", k_shot=5)
    secondary["negative_control_K5"] = _primary_pairs(per_task_rows, split="negative_control", k_shot=5)
    return {
        "primary_endpoint": PRIMARY_ENDPOINT,
        "primary": primary,
        "secondary": secondary,
        "note": "MAML 优势=P/M 臂之差交替对照；负控制单列、不进主终点。",
    }


def m1_negative_control_checks(
    per_task_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """§10/§12-11 负控制与健全性检查（诊断用，不阻断；异常需查泄漏后重跑）。"""
    def group_mean(split: str, arm: str, k_shot: int) -> float | None:
        values = [
            float(row["rmse_raw"])
            for row in per_task_rows
            if row.get("split") == split
            and row.get("arm") == arm
            and int(row.get("K", -1)) == k_shot
            and math.isfinite(float(row.get("rmse_raw", float("nan"))))
        ]
        return float(np.mean(values)) if values else None

    mt_m, mt_p = group_mean("meta_test", "M", 5), group_mean("meta_test", "P", 5)
    nc_m, nc_p = group_mean("negative_control", "M", 5), group_mean("negative_control", "P", 5)
    ood_m = group_mean("meta_test_ood", "M", 5)
    k0 = {arm: group_mean("meta_test", arm, 0) for arm in M1_ARMS}
    advantage_meta = None if (mt_m is None or mt_p is None) else float(mt_p - mt_m)
    advantage_nc = None if (nc_m is None or nc_p is None) else float(nc_p - nc_m)
    k0_values = {arm: value for arm, value in k0.items() if value is not None}
    k0_worst_arm = max(k0_values, key=k0_values.get) if k0_values else None
    return {
        "maml_advantage_meta_test_K5": advantage_meta,
        "maml_advantage_negative_control_K5": advantage_nc,
        "label_shuffle_advantage_collapsed": (
            None if (advantage_meta is None or advantage_nc is None) else bool(advantage_nc <= advantage_meta)
        ),
        "k0_group_rmse": k0,
        "k0_worst_arm": k0_worst_arm,
        "k0_random_arm_worst": None if k0_worst_arm is None else bool(k0_worst_arm == "R"),
        "ood_K5_M_rmse": ood_m,
        "ood_degraded_vs_meta_test": (
            None if (ood_m is None or mt_m is None) else bool(ood_m >= mt_m)
        ),
        "interpretation": (
            "负控制 label-shuffle 后 MAML 相对预训练优势应回落到接近 0；"
            "K=0 随机初始化臂应最差；OOD RMSE 预期上升。任一异常需查泄漏后重跑（§12-11）。"
        ),
    }
# ---------------------------------------------------------------------------
# 步骤 B（续）：M2 同预算优化矩阵（五臂 × optimization_seeds）
# ---------------------------------------------------------------------------
M2_EVAL_SPLITS = ("meta_test", "meta_test_ood")
M2_PROXY_ARM = "M2-proxy"
M2_REFERENCE_ARM = "OPT-BO-rand"
M2_SUMMARY_EXTRA_FIELDS = (
    "implementation",
    "termination_reason",
    "initial_feasible_count",
    "proxy_scoring_cost_json",
    "reference_objective",
    "best_objective_raw",
    "min_constraint_violation_sum",
    "feasible_hit_rate",
    "feasibility_expected_zero",
)


def m2_feasibility_expected(family_id: str) -> str:
    """M2 可行域预期注记（A7：F-QE 可行域体积 ~1e-6，B=64 预期 0 可行）。"""
    if family_id == "F-QE":
        return "true"
    return "unknown"


def build_m2_proxy_artifact(
    blocks: Mapping[str, Any],
    tasks: Sequence[SyntheticTask],
    runner_config: OfflineRunnerConfig,
) -> dict[str, Any]:
    """训练 M2 代理（objective+约束双输出），供 MAML-init 初始点打分与臂元数据。"""
    if not torch_available():
        raise OfflineRunnerError(f"torch 不可用，M2 代理无法训练：{torch_import_error()}")
    train_tasks = [task for task in tasks if task.split == "meta_train"]
    if not train_tasks:
        raise OfflineRunnerError("meta_train 任务为空，无法训练 M2 代理")
    target_names = task_target_names(train_tasks[0])
    if len(target_names) < 2:
        raise OfflineRunnerError("M2 代理至少需要 objective 与一个启用的约束目标列")
    for task in train_tasks:
        if task_target_names(task) != target_names:
            raise OfflineRunnerError(
                f"M2 代理目标列不一致：{task.task_id} 为 {task_target_names(task)}，"
                f"首任务为 {target_names}；P4-CODE 要求同族启用槽位一致"
            )
    episodes: list[TaskEpisode] = []
    for task in train_tasks:
        block = blocks[task.task_id]
        indices = [0] + [list(block["support"]["target_names"]).index(name) for name in target_names[1:]]
        support = np.asarray(block["support"]["targets"], dtype=np.float64)[:, indices]
        query = np.asarray(block["query"]["targets"], dtype=np.float64)[:, indices]
        episodes.append(
            TaskEpisode(
                support_features=block["support"]["features"],
                support_targets=support,
                query_features=block["query"]["features"],
                query_targets=query,
                task_id=task.task_id,
            )
        )
    config = MAMLConfig(
        input_dim=12 + len(CONTEXT_NAMES),
        output_dim=len(target_names),
        hidden_sizes=M2_HIDDEN_SIZES,
        inner_lr=0.01,
        inner_steps=5,
        outer_lr=1e-3,
        tasks_per_batch=min(8, len(episodes)),
        first_order=True,
        seed=runner_config.seed,
        backend="torch",
    )
    wall_start = time.perf_counter()
    trained = meta_train(episodes, config, max_steps=runner_config.max_meta_steps)
    wall_s = time.perf_counter() - wall_start
    if trained.get("status") != "VALID":
        raise OfflineRunnerError(
            "M2 代理元训练失败（fail-closed）："
            f"status={trained.get('status')!r} failure={trained.get('failure')!r}"
        )
    parameters = trained["final_parameters"]
    if isinstance(parameters, Mapping):
        parameters = ParameterSet.from_dict(parameters)
    training_rows: list[dict[str, Any]] = []
    history = list(trained.get("history", ()))
    for entry in history:
        training_rows.append(
            {
                "run_id": runner_config.run_id,
                "arm": M2_PROXY_ARM,
                "split": "meta_train",
                "task_id": "",
                "family": train_tasks[0].family,
                "iteration": int(entry.get("step", len(training_rows))),
                "epoch": 0,
                "loss_support": float(entry["inner_loss_last"]),
                "loss_query": float(entry["outer_loss"]),
                "grad_norm": float(entry["grad_norm"]),
                "lr": float(config.outer_lr),
                "seed": runner_config.seed,
                "wall_s": float(wall_s / max(1, len(history))),
                "status": "VALID",
            }
        )
    artifact = _make_artifact(
        parameters,
        config,
        adaptation_method="maml",
        training={
            "status": "VALID",
            "target_names": list(target_names),
            "steps": int(trained.get("steps", 0)),
            "wall_s": float(wall_s),
            "role": "M2 proxy（objective+约束双输出；仅用于初始点排序/元数据）",
        },
    )
    return {
        "artifact": artifact,
        "training_rows": training_rows,
        "training": artifact["training"],
        "target_names": target_names,
    }


def _bo_proxy_metadata(arm: str, m2_artifact: Any, blocks: Mapping[str, Any], task: SyntheticTask) -> dict[str, Any]:
    """BO 臂的代理元数据（A6：maml_opt 无外生先验注入点，代理不参与采集排序）。"""
    if arm in ("OPT-BO-pretrain", "OPT-BO-MAML"):
        return {
            "proxy_method": "none" if arm == "OPT-BO-pretrain" else "maml",
            "candidates_scored": 0,
            "model_forward_predictions": 0,
            "true_evaluation_budget_used": 0,
            "used_for_acquisition": False,
            "note": (
                "CONTRACT_AMBIGUITY A6：maml_opt ConstrainedBayesianOptimizer 无外生先验均"
                "值注入点，P4-CODE 阶段该臂与 OPT-BO-rand 共用 BO 机制与共享 8 初始点；"
                "代理预测只记录元数据，绝不写入 BO observations（§8.2 隔离）。"
            ),
        }
    if arm == MAML_INIT_ARM:
        return {"used_for_acquisition": False, "note": "初始点由 MAML 代理打分选出（§8.2）"}
    return {"proxy_method": "none", "used_for_acquisition": False}


def _fallback_metrics(result: Any) -> dict[str, Any]:
    """A7 fallback 指标：无可行解时用以公平比较五臂（null 不写成 0）。"""
    observations = list(result.observations)
    valid = [record for record in observations if record.objective is not None]
    best_record = None
    if valid:
        best_record = min(valid, key=lambda record: (float(record.objective), record.eval_index))
    if best_record is not None:
        constraints = dict(best_record.constraints or {})
        violation = sum(max(0.0, float(value)) for value in constraints.values() if math.isfinite(float(value)))
    else:
        violation = None
    return {
        "best_objective_raw": float(best_record.objective) if best_record is not None else None,
        "min_constraint_violation_sum": violation,
        "feasible_hit_rate": (
            float(result.feasible_count) / float(len(observations)) if observations else None
        ),
    }


def _history_rows(result: Any, runner_config: OfflineRunnerConfig) -> list[dict[str, Any]]:
    """optimization_history.csv 行（含 best_so_far 列）。"""
    rows: list[dict[str, Any]] = []
    best_feasible: float | None = None
    best_value: float | None = None
    for record in result.observations:
        if record.objective is not None:
            value = float(record.objective)
            best_value = value if best_value is None else min(best_value, value)
            if record.feasible:
                best_feasible = value if best_feasible is None else min(best_feasible, value)
        rows.append(
            record.to_history_row(
                run_id=runner_config.run_id,
                task_id=result.task_id,
                split=result.split,
                family=result.family,
                arm=result.arm,
                seed=result.seed,
                wall_s=0.0,
                best_feasible_so_far=best_feasible,
                best_value_so_far=best_value,
            )
        )
    return rows


def _evaluation_rows(result: Any, runner_config: OfflineRunnerConfig) -> list[dict[str, Any]]:
    """evaluations.jsonl 行：每条真实（合成）评估的完整记录。"""
    rows: list[dict[str, Any]] = []
    for record in result.observations:
        rows.append(
            {
                "run_id": runner_config.run_id,
                "arm": result.arm,
                "task_id": result.task_id,
                "split": result.split,
                "family": result.family,
                "seed": result.seed,
                "eval_index": record.eval_index,
                "design_u": [float(value) for value in record.design_u],
                "design_physical": (
                    [float(value) for value in record.design_physical]
                    if record.design_physical is not None
                    else None
                ),
                "objective": record.objective,
                "feasible": record.feasible,
                "constraints": dict(record.constraints or {}),
                "status": record.status,
                "cache_hit": record.cache_hit,
                "billable": record.billable,
                "physical_call_count": PHYSICAL_CALL_COUNT,
            }
        )
    return rows


def _m2_summary_row(result: Any, runner_config: OfflineRunnerConfig) -> dict[str, Any]:
    row = result.to_summary_row(run_id=runner_config.run_id)
    row.update(_fallback_metrics(result))
    row.update(
        {
            "implementation": result.implementation,
            "termination_reason": result.termination_reason,
            "initial_feasible_count": int(result.initial_feasible_count),
            "proxy_scoring_cost_json": json.dumps(
                dict(result.proxy_scoring_cost or {}), sort_keys=True, ensure_ascii=False
            ),
            "reference_objective": result.reference_objective,
            "feasibility_expected_zero": m2_feasibility_expected(result.family),
        }
    )
    return row


def run_m2_study(
    blocks: Mapping[str, Any],
    tasks: Sequence[SyntheticTask],
    m2_artifact: Any,
    design_space: DesignSpace,
    runner_config: OfflineRunnerConfig,
) -> dict[str, Any]:
    """M2：五臂 × seeds × {meta_test, meta_test_ood}，恰好 budget 次真实（合成）评估。"""
    eval_tasks = [task for task in tasks if task.split in M2_EVAL_SPLITS]
    if not eval_tasks:
        raise OfflineRunnerError("M2 评估任务为空（meta_test 至少 1 个）")
    results: list[Any] = []
    history_rows: list[dict[str, Any]] = []
    evaluation_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    arms = tuple(ARMS)
    for task in eval_tasks:
        reference = task.reference()
        reference_objective = (
            None if reference.get("objective_star") is None else float(reference["objective_star"])
        )
        target_names = task_target_names(task)
        if target_names != tuple(m2_artifact["training"].get("target_names", ())):
            raise OfflineRunnerError(
                f"M2 代理目标列与任务不一致：任务 {task.task_id} 为 {target_names}，"
                f"代理为 {m2_artifact['training'].get('target_names')}"
            )
        for seed in runner_config.optimization_seeds:
            shared = shared_initial_designs(
                task.task_id, seed, count=runner_config.bo_initial_designs
            )
            for arm in arms:
                evaluator = make_synthetic_task_evaluator(task, design_space)
                guarded = GuardedEvaluator(evaluator, label=f"M2:{arm}:{task.task_id}:seed{seed}")
                if arm == DE_ARM:
                    result = run_de_arm(
                        guarded,
                        task_id=task.task_id,
                        split=task.split,
                        family=task.family,
                        seed=seed,
                        budget=runner_config.budget_true_evaluations,
                        population_size=runner_config.de_population,
                        reference_objective=reference_objective,
                        run_id=runner_config.run_id,
                    )
                elif arm == MAML_INIT_ARM:
                    result = run_maml_init_arm(
                        m2_artifact,
                        design_space,
                        task,
                        guarded,
                        seed=seed,
                        budget=runner_config.budget_true_evaluations,
                        candidate_count=runner_config.maml_init_candidate_count,
                        initial_design_count=runner_config.maml_init_initial_designs,
                        diversity_candidate_count=runner_config.maml_init_diversity_candidate_count,
                        method="maml",
                        k_shot=0,
                        target_names=target_names,
                        reference_objective=reference_objective,
                        run_id=runner_config.run_id,
                    )
                else:
                    result = run_bo_arm(
                        arm,
                        guarded,
                        task_id=task.task_id,
                        split=task.split,
                        family=task.family,
                        seed=seed,
                        budget=runner_config.budget_true_evaluations,
                        initial_designs=shared,
                        strategy="bayesian",
                        reference_objective=reference_objective,
                        run_id=runner_config.run_id,
                        proxy_scoring_cost=_bo_proxy_metadata(arm, m2_artifact, blocks, task),
                    )
                if int(getattr(evaluator, "physical_call_count", 0)) != PHYSICAL_CALL_COUNT:
                    raise PhysicsGuardViolation(
                        f"M2 评估器报告 physical_call_count={evaluator.physical_call_count}"
                        f"（arm={arm}, task={task.task_id}, seed={seed}），立即中止整次 run",
                        physical_call_count=int(evaluator.physical_call_count),
                    )
                if result.true_evals_used != runner_config.budget_true_evaluations:
                    raise OfflineRunnerError(
                        f"等预算约束被破坏：arm={arm} task={task.task_id} seed={seed} "
                        f"true_evals_used={result.true_evals_used} != "
                        f"budget={runner_config.budget_true_evaluations}"
                    )
                results.append(result)
                history_rows.extend(_history_rows(result, runner_config))
                evaluation_rows.extend(_evaluation_rows(result, runner_config))
                summary_rows.append(_m2_summary_row(result, runner_config))
    return {
        "results": results,
        "history_rows": history_rows,
        "evaluation_rows": evaluation_rows,
        "summary_rows": summary_rows,
        "n_tasks": len(eval_tasks),
        "n_runs": len(results),
    }


# ---------------------------------------------------------------------------
# 步骤 B（续）：M2 终点统计与 fallback 比较（A7）
# ---------------------------------------------------------------------------
_PRIMARY_M2_METRICS = ("best_feasible_value", "gap_to_reference", "first_feasible_eval_index")
_FALLBACK_M2_METRICS = ("best_objective_raw", "min_constraint_violation_sum", "feasible_hit_rate")


def _finite_metric_values(rows: Sequence[Mapping[str, Any]], metric: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(metric)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            values.append(number)
    return values


def _m2_arm_aggregate(
    summary_rows: Sequence[Mapping[str, Any]], arm: str, split: str
) -> dict[str, Any]:
    rows = [row for row in summary_rows if row.get("arm") == arm and row.get("split") == split]
    aggregate: dict[str, Any] = {"arm": arm, "split": split, "n_runs": len(rows)}
    for metric in _PRIMARY_M2_METRICS + _FALLBACK_M2_METRICS:
        values = _finite_metric_values(rows, metric)
        nulls = sum(1 for row in rows if row.get(metric) is None)
        aggregate[metric] = {
            "n_total": len(rows),
            "n_null": nulls,
            "n_finite": len(values),
            "mean": float(np.mean(values)) if values else None,
            "median": float(np.median(values)) if values else None,
            "min": float(np.min(values)) if values else None,
            "max": float(np.max(values)) if values else None,
        }
    return aggregate


def _paired_arm_differences(
    summary_rows: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    treatment: str,
    control: str,
    split: str,
) -> list[float]:
    table: dict[tuple[str, int], dict[str, float]] = {}
    for row in summary_rows:
        if row.get("split") != split:
            continue
        arm = row.get("arm")
        if arm not in (treatment, control):
            continue
        value = row.get(metric)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        key = (str(row.get("task_id")), int(row.get("seed")))
        table.setdefault(key, {})[str(arm)] = number
    return [
        values[treatment] - values[control]
        for values in table.values()
        if treatment in values and control in values
    ]


def m2_endpoint_statistics(
    summary_rows: Sequence[Mapping[str, Any]],
    *,
    reference_arm: str = M2_REFERENCE_ARM,
) -> dict[str, Any]:
    """M2 预注册终点统计：主终点 @ B=64 + A7 fallback 配对比较（null 如实保留）。"""
    out: dict[str, Any] = {
        "budget_note": "每次 run 恰好 64 次真实（合成）评估；可行域稀疏，主终点可为 null。",
        "primary_metrics": list(_PRIMARY_M2_METRICS),
        "fallback_metrics": list(_FALLBACK_M2_METRICS),
        "reference_arm": reference_arm,
    }
    for split in M2_EVAL_SPLITS:
        split_block: dict[str, Any] = {
            "arms": [arm for arm in ARMS],
            "aggregate": {arm: _m2_arm_aggregate(summary_rows, arm, split) for arm in ARMS},
        }
        paired: dict[str, Any] = {}
        for metric in ("best_objective_raw", "min_constraint_violation_sum"):
            paired[metric] = {}
            for arm in ARMS:
                if arm == reference_arm:
                    continue
                differences = _paired_arm_differences(
                    summary_rows,
                    metric=metric,
                    treatment=arm,
                    control=reference_arm,
                    split=split,
                )
                if differences:
                    stats = paired_statistics(differences, seed=42)
                    stats["direction"] = f"{arm} - {reference_arm}"
                else:
                    stats = {"n": 0, "note": "没有配对 run（或主指标全为 null）"}
                paired[metric][arm] = stats
        split_block["paired_vs_reference"] = paired
        out[split] = split_block
    out["null_reporting_rule"] = (
        "best_feasible_value/gap_to_reference/first_feasible_eval_index 在无可行解时"
        "如实为 null，不得写成 0；fallback 指标用于五臂可比较（A7）。"
    )
    out["feasibility_expected_zero"] = {
        "F-QE": "true（可行域体积 ~1e-6，B=64 预期 0 可行，结论表需披露）",
        "others": "unknown",
    }
    return out


def m2_negative_control_note(summary_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """M2 负控制说明（§10：负控制在 M1 K-shot 诊断；M2 不单独跑负控制）。"""
    splits = sorted({str(row.get("split")) for row in summary_rows})
    return {
        "negative_control_in_m2": False,
        "evaluated_splits": splits,
        "note": "负控制仅用于 M1 label-shuffle 诊断（§10/§12-11），不进入 M2 主矩阵。",
    }


# ---------------------------------------------------------------------------
# 步骤 B（续）：MetaSample 构造与 schema-2 归档（§3.2/§3.3）
# ---------------------------------------------------------------------------
ARCHIVE_SOURCE_RUN = "p4-synthetic-meta-learning"


def build_meta_samples(
    blocks: Mapping[str, Any],
    tasks: Sequence[SyntheticTask],
    *,
    config_hash: str,
    git_sha: str,
    created_utc: str,
    design_space: DesignSpace | None = None,
) -> list[MetaSample]:
    """把 support+query 设计块转为 §3.2 MetaSample（只含非负控制、objective 非 null）。"""
    from .data_contract import FEASIBILITY_TOLERANCE, design_from_normalized

    samples: list[MetaSample] = []
    for task in tasks:
        if task.split == "negative_control":
            continue
        block = blocks[task.task_id]
        target_index = {name: index for index, name in enumerate(block["support"]["target_names"])}
        enabled = tuple(task.enabled_constraint_names)
        for kind in ("support", "query"):
            part = block[kind]
            designs = part["designs"]
            objectives = part["objective"]
            for row in range(designs.shape[0]):
                design_u = tuple(float(value) for value in designs[row])
                design = design_from_normalized(design_u)
                constraints: dict[str, float | None] = {name: None for name in CONSTRAINT_NAMES}
                for name in enabled:
                    constraints[name] = float(part["targets"][row, target_index[name]])
                values = [constraints[name] for name in enabled]
                feasible = all(
                    value is not None and math.isfinite(float(value)) and float(value) <= FEASIBILITY_TOLERANCE
                    for value in values
                )
                objective = float(objectives[row])
                if not math.isfinite(objective):
                    raise OfflineRunnerError(
                        f"任务 {task.task_id} 的合成目标非有限，禁止写入归档"
                    )
                sample = MetaSample(
                    task_id=task.task_id,
                    fidelity="synthetic",
                    evaluator_id=EVALUATOR_ID,
                    design_set=DESIGN_SET,
                    design=design,
                    design_normalized=design_u,
                    config_hash=config_hash,
                    objective=objective,
                    constraints=constraints,
                    status="VALID" if feasible else "INFEASIBLE",
                    source_kind="synthetic",
                    physics_validation_status="NOT_APPLICABLE",
                    git_sha=git_sha,
                    seed=task.seed,
                    physical_call_count=PHYSICAL_CALL_COUNT,
                    split=task.split,
                    task_context=meta_sample_task_context(task),
                    created_utc=created_utc,
                )
                samples.append(sample)
    if not samples:
        raise OfflineRunnerError("没有可归档的 MetaSample（检查任务族配置与 split）")
    return samples


NEGATIVE_CONTROL_MANIFEST_PATH = "tasks/negative_control_manifest.json"


def meta_sample_task_context(task: SyntheticTask) -> dict[str, float]:
    """§3.2:162 / §4.4：OOD 样本的 task_context 带数值 ood_flag=1.0（M1-F06）。

    ood_flag 仅作 OOD 元数据，不进入 task_context_names 或 14 维特征
    （特征仍为 2 维 context_1/context_2，见 §3.1 与 data_contract.CONTEXT_NAMES）。
    """
    context: dict[str, float] = {name: float(value) for name, value in dict(task.context).items()}
    if task.split == "meta_test_ood":
        context[OOD_FLAG_NAME] = 1.0
    return context


def build_negative_control_manifest(tasks: Sequence[SyntheticTask], *, run_id: str) -> dict[str, Any]:
    """§11.2 固定产物：负控制伪任务清单（不训练、不进主终点、不归档，M1-F04）。"""
    entries: list[dict[str, Any]] = []
    for task in tasks:
        if task.split != "negative_control":
            continue
        params = dict(task.params or {})
        entries.append(
            {
                "pseudo_task_id": task.task_id,
                "source_task_id": params.get("source_task_id"),
                "source_family": params.get("source_family", task.family),
                "source_split": "meta_train",
                "shuffle_seed": params.get("shuffle_seed"),
                "split": "negative_control",
            }
        )
    return {
        "run_id": run_id,
        "protocol": (
            "pseudo_task_id = 'NC-' + sha1('negative_control|' + source_task_id + '|' + shuffle_seed)[:10]；"
            "只打乱 objective/constraints 与 design 的配对，不改 context/params（§4.3）"
        ),
        "count": len(entries),
        "entries": entries,
        "isolation": {
            "derived_from": "meta_train",
            "not_in_training": True,
            "not_in_primary_endpoint": True,
            "not_archived": True,
            "split_assignments_exclusive": True,
        },
    }


def build_archive_payload(
    samples: Sequence[MetaSample],
    *,
    run_id: str,
    source_run_id: str = ARCHIVE_SOURCE_RUN,
) -> dict[str, Any]:
    """构造 write_archive 参数与 manifest 附加信息（target_map/units/task_splits）。"""
    from .data_contract import (
        archive_target_names,
        to_archive_records,
        to_archive_splits,
    )

    target_names = archive_target_names(samples)
    records = to_archive_records(samples, source_run_id=source_run_id)
    units = ["1"] * (12 + len(CONTEXT_NAMES))
    target_units = ["1"] * len(target_names)
    target_map: dict[str, dict[str, Any]] = {"objective": {"source": "objective"}}
    for name in target_names[1:]:
        target_map[name] = {"source": "constraints_g_le_zero", "key": name}
    return {
        "dataset_id": re.sub(r"[^A-Za-z0-9._-]", "-", run_id)[:48] + "-m1",
        "task_split_id": "p4-synthetic-m1-split-v1",
        "task_splits": to_archive_splits(samples),
        "design_feature_names": list(DESIGN_NAMES),
        "task_context_names": list(CONTEXT_NAMES),
        "feature_units": units,
        "target_names": list(target_names),
        "target_units": target_units,
        "target_map": target_map,
        "records": records,
        "source_runs": [{"run_id": run_id, "run_type": "p4-synthetic-meta-learning"}],
        "n_samples": len(samples),
    }


def write_archive_dataset(archive_root: str | Path, payload: Mapping[str, Any]) -> Path:
    """调用 maml_opt 公开 write_archive 写 schema-2 归档（不复制 P5 代码）。"""
    from maml_opt.data.archive import write_archive

    manifest_path = write_archive(
        Path(archive_root),
        dataset_id=payload["dataset_id"],
        task_split_id=payload["task_split_id"],
        task_splits=payload["task_splits"],
        design_feature_names=payload["design_feature_names"],
        task_context_names=payload["task_context_names"],
        feature_units=payload["feature_units"],
        target_names=payload["target_names"],
        target_units=payload["target_units"],
        records=payload["records"],
        source_runs=payload["source_runs"],
        frozen=False,
        target_map=payload["target_map"],
    )
    return Path(manifest_path)
# ---------------------------------------------------------------------------
# 步骤 B（续）：运行编排、确定性检查与 §11.2 产物写出
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_CONFIG_VERSION = "p4-meta-learning-run-v1"
NOT_APPROVED = (
    {"id": "P4-REAL-LF", "note": "真实低保证度评估未获授权，本 run 禁止调用任何真实求解器"},
    {"id": "P4-MULTIFIDELITY-REAL", "note": "真实多保真训练/评估未获授权"},
    {"id": "REAL-CROSS-TASK-META-TRAINING", "note": "真实跨任务元训练未获授权，本 run 仅合成解析任务族"},
)
DETERMINISM_COMPARE_FILES = ("metrics/metrics.csv", "metrics/optimization_summary.csv")
DETERMINISM_EXCLUDED_COLUMNS = ("wall_s", "proxy_scoring_cost_json")


def run_finite_difference_gate(seed: int) -> dict[str, Any]:
    """§7.2 梯度门禁：小模型中心差分检查（M2 启动前的强制门禁）。

    模型固定为 input_dim=12 / output_dim=2 / hidden=(8,8) / 1 步内循环的
    双精度小模型（build_small_model），episode 由显式 seed 生成（不依赖任务族
    采样，保证独立重跑逐位一致）；比较点为适配后参数点（FOMAML 一阶定义）。
    """
    model = build_small_model(seed=seed)
    rng = np.random.default_rng(seed)
    input_dim = int(model.config.input_dim)
    output_dim = int(model.config.output_dim)
    episode = TaskEpisode(
        support_features=rng.uniform(0.0, 1.0, size=(8, input_dim)),
        support_targets=rng.normal(size=(8, output_dim)),
        query_features=rng.uniform(0.0, 1.0, size=(8, input_dim)),
        query_targets=rng.normal(size=(8, output_dim)),
        task_id=f"fd-gate-{seed}",
    )
    return finite_difference_gradient_check(
        model,
        [episode],
        epsilon=FD_DEFAULT_EPSILON,
        tolerance=FD_DEFAULT_TOLERANCE,
    )


def _run_core(config: OfflineRunnerConfig) -> dict[str, Any]:
    """一次完整的内存内研究运行（不写盘；供正式运行与确定性重跑共用）。"""
    family_config = resolve_family_config(config)
    design_space = load_design_space_12d()
    git_state = repo_git_state(REPO_ROOT)
    config_hash = compute_config_hash(family_config, design_space, config)
    timestamp = iso_utc()
    tasks = build_task_family(family_config)
    residuals = assert_reference_solutions(tasks)
    tolerance = float(family_config.reference_tolerance)
    bad = {task_id: value for task_id, value in residuals.items() if not math.isfinite(value) or value > tolerance}
    if bad:
        raise OfflineRunnerError(f"参考解断言失败（容差 {tolerance}）：{bad}")
    blocks = build_task_blocks(tasks)
    family_id = family_config.family_id

    m1_training = build_m1_artifacts(blocks, tasks, config)
    m1_study = run_m1_study(blocks, tasks, m1_training["artifacts"], config)
    m1_metrics_rows = _group_metric_rows(m1_study["per_task_rows"], phase="adaptation", group_fields=("split", "arm", "K", "seed"))
    m1_endpoints = m1_endpoint_statistics(m1_study["per_task_rows"], primary_k=5)
    m1_negative_control = m1_negative_control_checks(m1_study["per_task_rows"])

    # §7.2 梯度门禁：M1 完成后、M2 启动前必须 PASS，FAIL 则 fail-closed 中止。
    finite_difference = run_finite_difference_gate(config.seed)
    if finite_difference.get("status") != "PASS":
        raise FiniteDifferenceFailure(
            "FD 梯度门禁未通过（§7.2：M2 不得启动）："
            f"max_relative_error={finite_difference.get('max_relative_error')!r} "
            f"n_checked={finite_difference.get('n_checked')!r}",
            finite_difference,
        )

    m2_proxy = build_m2_proxy_artifact(blocks, tasks, config)
    m2_study = run_m2_study(blocks, tasks, m2_proxy["artifact"], design_space, config)
    m2_endpoints = m2_endpoint_statistics(m2_study["summary_rows"])
    m2_note = m2_negative_control_note(m2_study["summary_rows"])
    m2_metrics_rows = _m2_metric_rows(m2_study["summary_rows"], family_id=family_id)

    training_rows = list(m1_training["training_rows"]) + list(m2_proxy["training_rows"])
    return {
        "run_id": config.run_id,
        "timestamp": timestamp,
        "git_state": git_state,
        "config_hash": config_hash,
        "family_config": family_config,
        "family_id": family_id,
        "design_space": design_space,
        "tasks": tasks,
        "blocks": blocks,
        "reference_residuals": {task_id: float(value) for task_id, value in residuals.items()},
        "finite_difference": finite_difference,
        "m1": {
            "training": m1_training,
            "study": m1_study,
            "metrics_rows": m1_metrics_rows,
            "endpoints": m1_endpoints,
            "negative_control": m1_negative_control,
        },
        "m2": {
            "proxy": m2_proxy,
            "study": m2_study,
            "metrics_rows": m2_metrics_rows,
            "endpoints": m2_endpoints,
            "negative_control_note": m2_note,
        },
        "training_rows": training_rows,
        "metrics_rows": list(m1_metrics_rows) + list(m2_metrics_rows),
    }


def _m2_metric_rows(
    summary_rows: Sequence[Mapping[str, Any]], *, family_id: str
) -> list[dict[str, Any]]:
    """M2 指标长表行（group_mean/std/ci95；null 行显式标 NO_FEASIBLE_SOLUTION）。"""
    metrics = (
        "best_feasible_value",
        "gap_to_reference",
        "best_objective_raw",
        "min_constraint_violation_sum",
        "feasible_hit_rate",
    )
    units = {
        "best_feasible_value": "synthetic_objective",
        "gap_to_reference": "synthetic_objective",
        "best_objective_raw": "synthetic_objective",
        "min_constraint_violation_sum": "1",
        "feasible_hit_rate": "1",
    }
    rows: list[dict[str, Any]] = []
    for split in M2_EVAL_SPLITS:
        for arm in ARMS:
            subset = [
                row for row in summary_rows if row.get("split") == split and row.get("arm") == arm
            ]
            if not subset:
                continue
            for metric in metrics:
                values = _finite_metric_values(subset, metric)
                base = {
                    "experiment_id": f"M2::{split}::{arm}",
                    "phase": "optimization",
                    "split": split,
                    "family": family_id,
                    "arm": arm,
                    "K": "",
                    "task_id": "",
                    "seed": "",
                    "metric": metric,
                    "unit": units[metric],
                    "n": len(values),
                    "status": "VALID" if values else "NO_FEASIBLE_SOLUTION",
                }
                if not values:
                    rows.append({**base, "value": None, "aggregation": "group_mean"})
                    continue
                array = np.asarray(values, dtype=float)
                stats = paired_statistics(array, seed=0, bootstrap_samples=1000)
                for aggregation, value in (
                    ("group_mean", float(np.mean(array))),
                    ("group_std", float(np.std(array, ddof=1)) if array.size > 1 else 0.0),
                    ("ci95_low", stats["ci_low"]),
                    ("ci95_high", stats["ci_high"]),
                ):
                    rows.append({**base, "value": value, "aggregation": aggregation})
    return rows


def _serialize_products(metrics_rows: Sequence[Mapping[str, Any]], summary_rows: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """序列化确定性比较对象：metrics.csv 与 optimization_summary.csv（剔除非确定列）。"""
    import io

    target_columns = {
        "metrics/metrics.csv": list(REQUIRED_CSV_COLUMNS["metrics"]),
        "metrics/optimization_summary.csv": list(REQUIRED_CSV_COLUMNS["optimization_summary"]),
    }
    payloads: dict[str, str] = {}
    for name, columns in target_columns.items():
        rows = metrics_rows if name.endswith("metrics.csv") else summary_rows
        compare_columns = [column for column in columns if column not in DETERMINISM_EXCLUDED_COLUMNS]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=compare_columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column)) for column in compare_columns})
        payloads[name] = buffer.getvalue()
    return payloads


def _determinism_check(cores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """§12-15：独立重跑 N 次，metrics.csv 与 optimization_summary.csv 逐位一致。"""
    if len(cores) < 2:
        return {
            "status": "NOT_RUN",
            "reruns": len(cores),
            "note": "determinism_reruns<2，无法做逐位一致性比较（正式 run 必须 3）",
            "compared_files": list(DETERMINISM_COMPARE_FILES),
            "non_deterministic_columns_excluded": list(DETERMINISM_EXCLUDED_COLUMNS),
        }
    hashes: dict[str, list[str]] = {name: [] for name in DETERMINISM_COMPARE_FILES}
    for core in cores:
        payloads = _serialize_products(core["metrics_rows"], core["m2"]["study"]["summary_rows"])
        for name in DETERMINISM_COMPARE_FILES:
            hashes[name].append(hashlib.sha256(payloads[name].encode("utf-8")).hexdigest())
    mismatched = [
        name for name in DETERMINISM_COMPARE_FILES if len(set(hashes[name])) != 1
    ]
    status = "PASS" if not mismatched else "FAIL"
    return {
        "status": status,
        "reruns": len(cores),
        "metric": "sha256(normalized CSV text, float repr, wall_s/proxy wall 剔除)",
        "compared_files": list(DETERMINISM_COMPARE_FILES),
        "hashes": {name: hashes[name][0] for name in DETERMINISM_COMPARE_FILES},
        "mismatched_files": mismatched,
        "non_deterministic_columns_excluded": list(DETERMINISM_EXCLUDED_COLUMNS),
        "note": (
            "PASS=逐位一致；FAIL=框架非确定，必须记录并降级该臂结论，不得静默通过"
            "（§11.2/§12-15）。"
        ),
    }


def _write_failure_summary(run_dir: Path, config: OfflineRunnerConfig, status: str, error: BaseException) -> dict[str, Any]:
    """失败/物理守卫中止：只写 summary.json（如实落盘，不伪造正常 0 计数结论）。"""
    import traceback

    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": config.run_id,
        "status": status,
        "stage": STAGE,
        "data_origin": DATA_ORIGIN,
        "physical_call_count": (
            int(getattr(error, "physical_call_count", 0))
            if status == "PHYSICS_GUARD_VIOLATION"
            else None
        ),
        "physics_guard": {
            "expected": PHYSICS_GUARD_EXPECTED,
            "status": "VIOLATED" if status == "PHYSICS_GUARD_VIOLATION" else "UNKNOWN",
            "message": str(error),
        },
        "error": {"type": type(error).__name__, "message": str(error)},
        "traceback_summary": traceback.format_exc(limit=8).splitlines()[-12:],
        "products_written": ["summary.json"],
    }
    write_json(run_dir / "summary.json", summary)
    return summary


# ---------------------------------------------------------------------------
# §11.2 固定产物写出
# ---------------------------------------------------------------------------
def _write_products(core: Mapping[str, Any], config: OfflineRunnerConfig, run_dir: Path, determinism: Mapping[str, Any], archive_info: Mapping[str, Any] | None) -> dict[str, Any]:
    """按 §11.2 写出固定产物集并生成 data_manifest.json。"""
    import dataclasses

    family_config = core["family_config"]
    family_id = core["family_id"]
    design_space = core["design_space"]
    tasks = core["tasks"]
    git_state = core["git_state"]
    timestamp = core["timestamp"]
    m1 = core["m1"]
    m2 = core["m2"]
    m2_summary_rows = m2["study"]["summary_rows"]
    m1_summary = core["m1"]["endpoints"]

    metrics_dir = run_dir / "metrics"
    figures_dir = run_dir / "figures"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    # --- run_config.json（§11）---
    run_config = {
        "run_config_version": RUN_CONFIG_VERSION,
        "run_id": config.run_id,
        "stage": STAGE,
        "data_origin": DATA_ORIGIN,
        "synthetic_only": True,
        "git_sha": git_state["git_sha"],
        "worktree_dirty": git_state["worktree_dirty"],
        "git_sha_label": git_state["git_sha_label"],
        "seed": config.seed,
        "optimization_seeds": list(config.optimization_seeds),
        "actual_seeds": list(config.optimization_seeds),
        "family_id": family_id,
        "family_config_path": str(config.family_config_path) if config.family_config_path else None,
        "family_fingerprint": family_fingerprint(family_config),
        "split_counts": {
            split: len([task for task in tasks if task.split == split]) for split in SPLITS
        },
        "design_set": DESIGN_SET,
        "config_hash": core["config_hash"],
        "budget": {
            "true_evaluation_budget": config.budget_true_evaluations,
            "bo_initial_designs": config.bo_initial_designs,
            "de_population": config.de_population,
            "de_generations": config.de_generations,
            "s_adapt": S_ADAPT,
            "max_meta_steps": config.max_meta_steps,
        },
        "ks": list(config.ks),
        "tolerance": {
            "feasibility_g_le_zero": 1e-12,
            "reference_solution": family_config.reference_tolerance,
            "support_query_design_disjoint": 1e-12,
        },
        "physical_call_declaration": {
            "physical_call_count": PHYSICAL_CALL_COUNT,
            "expected": PHYSICS_GUARD_EXPECTED,
            "real_evaluator_policy": "fail-closed（构造即抛 NotImplementedError）",
        },
        "primary_endpoint": PRIMARY_ENDPOINT,
        "secondary_endpoints": list(SECONDARY_ENDPOINTS),
        "negative_control_protocol": {
            "split": "negative_control",
            "shuffle": "打乱伪任务内部 objective/constraints 与 design 的配对，不改 context/params",
            "seed_formula": "shuffle_seed = 20261102 + index",
            "pseudo_task_id": "NC-<sha1('negative_control|source_task_id|shuffle_seed')[:10]>",
            "isolation": "负控制单列，禁进主终点/调参",
        },
        "statistics": dict(STATISTICS_PLAN),
        "determinism_reruns": config.determinism_reruns,
        "maml_init": {
            "candidate_count": config.maml_init_candidate_count,
            "initial_design_count": config.maml_init_initial_designs,
            "diversity_candidate_count": config.maml_init_diversity_candidate_count,
            "dedup_tolerance": 1e-12,
            "seed_policy": "derive_arm_seed(task_id, seed, 'maml_init_pool')（禁默认 42）",
        },
        "evaluator_id": EVALUATOR_ID,
        "implementation": {
            "OPT-BO-rand": "reuse:maml_opt.bayesian:run_search",
            "OPT-BO-pretrain": "reuse:maml_opt.bayesian:run_search",
            "OPT-BO-MAML": "reuse:maml_opt.bayesian:run_search",
            "OPT-BO-MAML-init": "reuse:maml_opt.initialization:select_model_scored_initial_designs",
            "OPT-DE": (
                "reuse_semantics:research.concorde_metaopt.optimization.baseline_de:"
                "DifferentialEvolutionBaseline"
            ),
        },
        "archive": None if archive_info is None else dict(archive_info),
        "not_approved": list(NOT_APPROVED),
    }
    write_json(run_dir / "run_config.json", run_config)
    write_json(run_dir / "environment.json", environment_payload(config.run_id, PHYSICAL_CALL_COUNT))

    # --- tasks.json / reference_solutions.json ---
    write_json(
        run_dir / "tasks.json",
        {
            "family_config": dataclasses.asdict(family_config),
            "family_fingerprint": family_fingerprint(family_config),
            "split_assignments": {
                split: [task.task_id for task in tasks if task.split == split] for split in SPLITS
            },
            "tasks": [serialize_task(task) for task in tasks],
        },
    )
    tasks_dir = run_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        tasks_dir / "negative_control_manifest.json",
        build_negative_control_manifest(tasks, run_id=config.run_id),
    )

    references: dict[str, Any] = {}
    for task in tasks:
        if task.split == "negative_control":
            continue
        reference = task.reference()
        references[task.task_id] = {
            "u_star": [float(value) for value in np.asarray(reference["u_star"], dtype=float)],
            "objective_star": float(reference["objective_star"]),
            "reference_kind": reference["reference_kind"],
            "assertion_residual": float(reference["assertion_residual"]),
            "constraints": {name: float(value) for name, value in dict(reference["constraints"]).items()},
            "feasible": bool(reference["feasible"]),
        }
    write_json(
        run_dir / "reference_solutions.json",
        {
            "family_id": family_id,
            "tolerance": float(family_config.reference_tolerance),
            "max_residual": max(core["reference_residuals"].values()) if core["reference_residuals"] else 0.0,
            "solutions": references,
        },
    )

    # --- metrics/*.csv ---
    training_rows = core["training_rows"]
    write_csv(metrics_dir / "training_history.csv", training_rows, REQUIRED_CSV_COLUMNS["training_history"])
    adaptation_rows = core["m1"]["study"]["adaptation_rows"]
    write_csv(metrics_dir / "adaptation_results.csv", adaptation_rows, REQUIRED_CSV_COLUMNS["adaptation_results"])
    write_csv(metrics_dir / "metrics.csv", core["metrics_rows"], REQUIRED_CSV_COLUMNS["metrics"])
    write_csv(
        metrics_dir / "optimization_history.csv",
        m2["study"]["history_rows"],
        REQUIRED_CSV_COLUMNS["optimization_history"],
    )
    summary_rows: list[dict[str, Any]] = []
    for row in m2_summary_rows:
        summary_rows.append({column: row.get(column) for column in REQUIRED_CSV_COLUMNS["optimization_summary"]})
    write_csv(metrics_dir / "optimization_summary.csv", summary_rows, REQUIRED_CSV_COLUMNS["optimization_summary"])

    # --- evaluations.jsonl ---
    write_jsonl(run_dir / "evaluations.jsonl", m2["study"]["evaluation_rows"])

    # --- solver_validation.csv（§12-18：P4-CODE 阶段全部 NOT_RUN/NOT_APPLICABLE）---
    solver_rows = [
        {
            "run_id": config.run_id,
            "case_id": "D-12D-001",
            "evaluator_id": EVALUATOR_ID,
            "solver_family": "VSPAERO",
            "status": "NOT_APPLICABLE_THIS_STAGE",
            "note": "VSPAERO 验证归口 Issue #4 D-12D-004；P4-CODE 仅合成解析，未调用任何真实求解器",
        },
        {
            "run_id": config.run_id,
            "case_id": "D-12D-002",
            "evaluator_id": EVALUATOR_ID,
            "solver_family": "SU2",
            "status": "NOT_RUN",
            "note": "真实 CFD/任务求解未获授权（P4-REAL-LF 未批准）；本 run 物理调用 0",
        },
        {
            "run_id": config.run_id,
            "case_id": "D-12D-003",
            "evaluator_id": EVALUATOR_ID,
            "solver_family": "RCAIDE_MISSION",
            "status": "NOT_RUN",
            "note": "RCAIDE 任务求解器禁止 import/调用（§1.3 硬隔离）；真实 evaluator fail-closed",
        },
    ]
    write_csv(
        run_dir / "solver_validation.csv",
        solver_rows,
        ("run_id", "case_id", "evaluator_id", "solver_family", "status", "note"),
    )

    # --- finite_difference_check.json（§7.2：保留原始数组，非有限值写 null）---
    write_finite_difference_check(core["finite_difference"], run_dir / "finite_difference_check.json")

    # --- figures：本阶段不生成（由 A2 从 CSV 生成，缺失记 NOT_RUN；禁假图）---
    write_json(
        figures_dir / "figure_status.json",
        {
            "status": "NOT_RUN",
            "note": "fig1_meta_training_loss/fig2_k_shot_adaptation/fig3_equal_budget_convergence/fig5_budget_gate_progress 由 A2 从本 run CSV 生成；fig4_vspaero_version_panel_density 归 Issue #4 D-12D-004，本阶段 NOT_RUN",
            "figures": {
                "fig1_meta_training_loss": "NOT_RUN",
                "fig2_k_shot_adaptation": "NOT_RUN",
                "fig3_equal_budget_convergence": "NOT_RUN",
                "fig4_vspaero_version_panel_density": "NOT_RUN（归 Issue #4 D-12D-004）",
                "fig5_budget_gate_progress": "NOT_RUN",
            },
        },
    )

    # --- summary.json ---
    determinism_status = str(determinism.get("status"))
    status = "VALID" if determinism_status in ("PASS", "NOT_RUN") else "DETERMINISM_FAILED"
    if determinism_status == "FAIL":
        status = "DETERMINISM_FAILED"
    summary = {
        "run_id": config.run_id,
        "status": status,
        "stage": STAGE,
        "data_origin": DATA_ORIGIN,
        "synthetic_only": True,
        "family_id": family_id,
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "physics_guard": {
            "expected": PHYSICS_GUARD_EXPECTED,
            "status": "PASS",
            "end_assertion": "PASS",
            "forbidden_modules_loaded": [],
        },
        "determinism": dict(determinism),
        "reference_solutions": {
            "n_tasks": len(core["reference_residuals"]),
            "max_residual": max(core["reference_residuals"].values()) if core["reference_residuals"] else 0.0,
            "tolerance": float(family_config.reference_tolerance),
            "status": "PASS",
        },
        "finite_difference_check": {
            "status": core["finite_difference"].get("status"),
            "n_checked": core["finite_difference"].get("n_checked"),
            "max_relative_error": core["finite_difference"].get("max_relative_error"),
            "epsilon": core["finite_difference"].get("epsilon"),
            "tolerance": core["finite_difference"].get("tolerance"),
        },
        "m1": {
            "arms": list(M1_ARMS),
            "ks": list(config.ks),
            "n_adaptation_rows": len(adaptation_rows),
            "endpoints": m1["endpoints"],
            "negative_control_checks": m1["negative_control"],
            "meta_training": m1["training"]["meta_training"],
            "pretraining": m1["training"]["pretraining"],
        },
        "m2": {
            "arms": list(ARMS),
            "seeds": list(config.optimization_seeds),
            "budget": config.budget_true_evaluations,
            "n_runs": len(m2["study"]["results"]),
            "n_evaluations": len(m2["study"]["history_rows"]),
            "endpoints": m2["endpoints"],
            "negative_control_note": m2["negative_control_note"],
            "proxy": {
                "role": m2["proxy"]["training"].get("role"),
                "target_names": list(m2["proxy"]["target_names"]),
                "steps": m2["proxy"]["training"].get("steps"),
            },
            "feasibility_expected_zero_note": (
                "F-QE 可行域体积 ~1e-6：B=64 预期 0 可行；无可行解时 best_feasible_value/"
                "gap_to_reference/first_feasible_eval_index 如实为 null（禁写 0），"
                "五臂比较使用 A7 fallback 指标并披露。"
            ),
        },
        "failures": {
            "n_failed_evaluations": int(sum(row.get("failed_evals") or 0 for row in m2_summary_rows)),
            "n_nonfinite_m1": int(
                sum(1 for row in core["m1"]["study"]["per_task_rows"] if row.get("status") == "NONFINITE")
            ),
        },
        "not_approved": list(NOT_APPROVED),
        "figures": {
            "fig1_meta_training_loss": "NOT_RUN",
            "fig2_k_shot_adaptation": "NOT_RUN",
            "fig3_equal_budget_convergence": "NOT_RUN",
            "fig4_vspaero_version_panel_density": "NOT_RUN（归 Issue #4 D-12D-004）",
            "fig5_budget_gate_progress": "NOT_RUN",
        },
        "archive": None if archive_info is None else dict(archive_info),
        "products": [
            "run_config.json",
            "environment.json",
            "summary.json",
            "data_manifest.json",
            "tasks.json",
            "tasks/negative_control_manifest.json",
            "reference_solutions.json",
            "evaluations.jsonl",
            "README.md",
            "solver_validation.csv",
            "finite_difference_check.json",
            "metrics/training_history.csv",
            "metrics/adaptation_results.csv",
            "metrics/metrics.csv",
            "metrics/optimization_history.csv",
            "metrics/optimization_summary.csv",
            "figures/figure_status.json",
        ],
        "message": (
            "合成解析任务族上的离线元学习/优化对照（SYNTHETIC_ONLY）；不含任何真实物理结论。"
        ),
    }
    write_json(run_dir / "summary.json", summary)

    # --- README.md ---
    readme = _render_readme(core, config, determinism, archive_info, status)
    (run_dir / "README.md").write_text(readme, encoding="utf-8", newline="\n")

    # --- data_manifest.json（最后写，不含自身）---
    manifest = build_data_manifest(run_dir)
    write_json(run_dir / "data_manifest.json", manifest)
    return summary


def _render_readme(
    core: Mapping[str, Any],
    config: OfflineRunnerConfig,
    determinism: Mapping[str, Any],
    archive_info: Mapping[str, Any] | None,
    status: str,
) -> str:
    """生成中文 README（含 SYNTHETIC_ONLY、null 规则与文件清单）。"""
    m2 = core["m2"]
    lines = [
        f"# P4 元学习离线实验 run：{config.run_id}",
        "",
        "> 阶段：P4-CODE（SYNTHETIC_ONLY）。本 run 只使用解析合成任务族与合成评估器，",
        "> 未调用任何真实 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器，physical_call_count=0。",
        "> 本 run 的任何数值都不得外推为真实飞机性能结论。",
        "",
        f"- status: {status}",
        f"- family: {core['family_id']}；config_hash: {core['config_hash']}",
        f"- git_sha: {core['git_state']['git_sha_label']}；worktree_dirty={core['git_state']['worktree_dirty']}",
        f"- seed: {config.seed}；M2 seeds: {list(config.optimization_seeds)}",
        f"- 主终点（预注册）：{PRIMARY_ENDPOINT}",
        f"- 确定性重跑：{determinism.get('reruns')} 次，状态 {determinism.get('status')}",
        "",
        "## 可行域稀疏与 null 规则（A7）",
        "",
        "F-QE 的可行域是 12 维加权球（r~U(0.15,0.45)），体积约 1e-6；",
        "在 64 次真实（合成）评估预算下五臂预期均无可行解。此时",
        "best_feasible_value / gap_to_reference / first_feasible_eval_index 如实写 null，",
        "严禁写成 0。五臂比较使用 fallback 指标：best_objective_raw（最小原始目标）、",
        "min_constraint_violation_sum（最好目标设计的约束正违反之和）、",
        "feasible_hit_rate（feasible_count/evaluations）。",
        "",
        "## 产物文件",
        "",
        "run_config.json / environment.json / summary.json / data_manifest.json / tasks.json /",
        "tasks/negative_control_manifest.json / reference_solutions.json / evaluations.jsonl / solver_validation.csv /",
        "finite_difference_check.json / README.md；",
        "metrics/{training_history,adaptation_results,metrics,optimization_history,optimization_summary}.csv；",
        "figures/figure_status.json（本阶段不生成图；fig1/fig2/fig3/fig5 由 A2 从 CSV 生成，fig4 归 Issue #4 D-12D-004）。",
        "",
        "## 隔离与边界",
        "",
        "- 物理调用守卫：启动断言 sys.modules 无真实求解器模块；评估器每次调用检查",
        "  physical_call_count，非零立即中止并写 status=PHYSICS_GUARD_VIOLATION。",
        "- FD 梯度门禁（§7.2）：M2 启动前在适配后参数点做中心差分检查，非 PASS 时",
        "  整 run 中止并写 status=FINITE_DIFFERENCE_FAILED（保留 FD 原始数组）。",
        "- 数据合同：所有样本 data_origin=SYNTHETIC_TEST、physics_validation_status=NOT_APPLICABLE。",
        "- 负控制（label-shuffle）只用于 M1 诊断，单列、不进主终点/调参。",
        f"- archive：{archive_info if archive_info else 'NOT_WRITTEN'}",
        "",
        f"评估器：{EVALUATOR_ID}；实现标签：maml_opt 公开 API 复用 + 合成任务族解析真值。",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def run_offline_study(config: OfflineRunnerConfig) -> dict[str, Any]:
    """运行完整 P4-CODE 离线研究并写出 §11.2 产物（fail-closed）。

    运行目录 = config.output_root（若其 basename 不是 run_id，则取其子目录 run_id）。
    """
    output_root = Path(config.output_root)
    run_dir = output_root if output_root.name == config.run_id else output_root / config.run_id
    try:
        guard_baseline = _forbidden_modules_present()
        entry_guard = assert_no_forbidden_modules(guard_baseline)
        entry_physical = 0
        cores: list[dict[str, Any]] = []
        reruns = max(1, int(config.determinism_reruns))
        for _ in range(reruns):
            cores.append(_run_core(config))
            if entry_guard is None:  # pragma: no cover - 恒不成立
                raise OfflineRunnerError("启动守卫返回值异常")
        assert_no_forbidden_modules(guard_baseline)
        determinism = _determinism_check(cores)
        core = cores[0]
        # 归档（仅非负控制样本；schema-2；data_origin=SYNTHETIC_TEST）
        samples = build_meta_samples(
            core["blocks"],
            core["tasks"],
            config_hash=core["config_hash"],
            git_sha=core["git_state"]["git_sha"],
            created_utc=core["timestamp"],
        )
        archive_payload = build_archive_payload(samples, run_id=config.run_id)
        archive_manifest = write_archive_dataset(run_dir / "archive", archive_payload)
        archive_info = {
            "dataset_id": archive_payload["dataset_id"],
            "manifest_path": archive_manifest.relative_to(run_dir).as_posix(),
            "n_samples": archive_payload["n_samples"],
            "target_names": archive_payload["target_names"],
            "task_splits": {key: len(value) for key, value in archive_payload["task_splits"].items()},
            "data_origin": DATA_ORIGIN,
            "schema_version": 2,
        }
        summary = _write_products(core, config, run_dir, determinism, archive_info)
        if entry_physical != PHYSICAL_CALL_COUNT:  # pragma: no cover - 恒不成立
            raise OfflineRunnerError("起始物理调用计数异常")
        return summary
    except PhysicsGuardViolation as error:
        return _write_failure_summary(run_dir, config, "PHYSICS_GUARD_VIOLATION", error)
    except FiniteDifferenceFailure as error:
        # §7.2：FD 失败必须落盘原始检查结果，再写失败 summary（M2 不得启动）。
        run_dir.mkdir(parents=True, exist_ok=True)
        write_finite_difference_check(error.result, run_dir / "finite_difference_check.json")
        summary = _write_failure_summary(run_dir, config, "FINITE_DIFFERENCE_FAILED", error)
        summary["products_written"] = ["summary.json", "finite_difference_check.json"]
        summary["finite_difference_check"] = {
            "status": error.result.get("status"),
            "max_relative_error": error.result.get("max_relative_error"),
            "n_checked": error.result.get("n_checked"),
        }
        write_json(run_dir / "summary.json", summary)
        return summary
    except OfflineRunnerError as error:
        return _write_failure_summary(run_dir, config, "FAILED", error)
    except Exception as error:  # noqa: BLE001 - 失败必须如实落盘为 summary，不得静默崩溃（M1-F09）
        return _write_failure_summary(run_dir, config, "FAILED", error)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口：python -m research.concorde_metaopt.meta_learning.offline_runner ..."""
    import argparse

    parser = argparse.ArgumentParser(description="P4-CODE 元学习离线实验运行器（合成解析，物理调用 0）")
    parser.add_argument("--run-id", default=None, help="运行 ID（默认 p4-synthetic-<UTC>Z）")
    parser.add_argument(
        "--output-root",
        default=str(REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs"),
        help="输出根目录（运行目录为 <output-root>/<run-id>）",
    )
    parser.add_argument("--family-config", default=None, help="任务族配置 JSON 路径（默认 F-QE 正式规模）")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-meta-steps", type=int, default=2000)
    parser.add_argument("--budget", type=int, default=TRUE_EVALUATION_BUDGET)
    parser.add_argument("--ks", type=int, nargs="+", default=list(DEFAULT_KS))
    parser.add_argument("--optimization-seeds", type=int, nargs="+", default=list(M2_SEEDS))
    parser.add_argument("--determinism-reruns", type=int, default=3)
    arguments = parser.parse_args(list(argv) if argv is not None else None)
    config = OfflineRunnerConfig(
        run_id=arguments.run_id or make_run_id(),
        output_root=Path(arguments.output_root),
        family_config_path=Path(arguments.family_config) if arguments.family_config else None,
        ks=tuple(arguments.ks),
        seed=arguments.seed,
        max_meta_steps=arguments.max_meta_steps,
        budget_true_evaluations=arguments.budget,
        determinism_reruns=arguments.determinism_reruns,
        optimization_seeds=tuple(arguments.optimization_seeds),
    )
    summary = run_offline_study(config)
    print(json.dumps({"run_id": summary.get("run_id"), "status": summary.get("status")}, ensure_ascii=False))
    return 0 if summary.get("status") in ("VALID", "NOT_RUN") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
