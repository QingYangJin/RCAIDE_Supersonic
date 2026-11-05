"""S1（P4 路线 A / Issue #7）五臂等预算 runner：零物理调用，仅解析合成评估。

本模块是 task-215 的实现骨架 + 主流程；A1 独占，不得修改 s1_analysis.py/s1_figures.py。
合同：docs/planning/p4_route_a_s1_execution_plan_20261105.md（§4 run_records 字段、§5 端点、
§6 预算、§7 确定性/负控、§9 验收）。

关键不变量（逐 run fail-closed）：
- 每 run 恰好 B 次 billable 评价：K 次支持（缓存、计入预算）+ (8-K) 新初始点 + (B-8) 主搜索；
- K=0 时 FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 同构：登记 CLONE_OF_FOMAML-ZERO-BO 并排除推断；
- 冻结包身份（family_fingerprint/split_hash/prereg_digest/analysis_plan_digest/radius_base）逐 run 回显；
- physical_call_count=0、physical_call_sources=[]、physics_guard=PASS。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from . import family_v3 as fv3
from . import m5_arms as m5
from .baseline_arms import make_synthetic_task_evaluator
from .data_contract import CONTEXT_NAMES
from .task_family import SyntheticTask

S1_RUNNER_SCHEMA_VERSION = "p4ra-s1-runner-1"
S1_RECORD_SCHEMA_VERSION = "p4ra-s1-run-record-1"
S1_RUN_CONFIG_SCHEMA_VERSION = "p4ra-s1-run-config-1"
S1_SUMMARY_SCHEMA_VERSION = "p4ra-s1-run-summary-1"
S1_MANIFEST_SCHEMA_VERSION = "p4ra-s1-manifest-1"
DEFAULT_FROZEN_RUN_ID = "p4ra-s0-2-freeze-20261105T072500Z"
DEFAULT_RADIUS_BASE = 0.64
FROZEN_REQUIRED_FILES = (
    "tasks.json",
    "meta_task_split.json",
    "frozen_family.json",
    "preregistration.json",
)
DETERMINISM_EXCLUDED_FIELDS = ("cost", "record_digest")
PRIMARY_SPLIT = "meta_test"
SINGLE_LAYER_SPLITS = ("meta_test_ood", "negative_control")
ENDPOINT_KEYS = tuple(fv3.ENDPOINT_ROW_KEYS)
PRIMARY_ENDPOINTS = tuple(fv3.PRIMARY_ENDPOINTS)

# 正式分层网格（S1 合同）：21,000 runs，显式排除 B=128 x K=0 的 3,000 个计划外组合。
FORMAL_GRID_MODE = "formal"
CARTESIAN_GRID_MODE = "cartesian"
GRID_MODES = (CARTESIAN_GRID_MODE, FORMAL_GRID_MODE)
FORMAL_GRID_STRATA: tuple[dict[str, Any], ...] = (
    {"name": "main", "budgets": (64,), "k_values": (0, 3, 5), "expected_runs": 9000},
    {"name": "secondary", "budgets": (128,), "k_values": (3, 5), "expected_runs": 6000},
    {"name": "exploratory", "budgets": (64, 128), "k_values": (1,), "expected_runs": 6000},
)
FORMAL_GRID_TOTAL_RUNS = 21000
FORMAL_GRID_DEFAULT_META_SEEDS = (0, 1, 2)
FORMAL_GRID_DEFAULT_OPT_SEEDS = tuple(range(10))
FORMAL_GRID_STRATUM_NAMES: tuple[str, ...] = tuple(
    str(stratum["name"]) for stratum in FORMAL_GRID_STRATA
)

# 臂语义可辨识性（task-227 / S1-B03）：模型打分臂初始设计组内重叠率审计。
IDENTIFIABILITY_SCHEMA_VERSION = "p4ra-s1-identifiability-1"
IDENTIFIABILITY_OVERLAP_THRESHOLD = 0.90
IDENTIFIABILITY_REQUIRED_PAIRS: tuple[tuple[str, str], ...] = (
    (m5.S1_FOMAML_ZERO_BO, m5.S1_FOMAML_KSHOT_BO),
    (m5.S1_PRETRAIN_KSHOT_BO, m5.S1_FOMAML_ZERO_BO),
    (m5.S1_PRETRAIN_KSHOT_BO, m5.S1_FOMAML_KSHOT_BO),
)


class S1RunnerError(RuntimeError):
    """S1 runner 的 fail-closed 错误。"""


# ---------------------------------------------------------------------------
# 规范化序列化（与冻结包一致：sort_keys、紧凑分隔符、ensure_ascii=False）
# ---------------------------------------------------------------------------
def canonical_json(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise S1RunnerError(f"payload 不可 JSON 序列化: {exc}") from exc


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json_file(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise S1RunnerError(f"文件不存在: {target}")
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_file(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    target.write_text(text, encoding="utf-8")


def write_jsonl_file(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(row))
            handle.write("\n")


# ---------------------------------------------------------------------------
# 冻结包加载与身份校验
# ---------------------------------------------------------------------------
def _task_from_record(record: Mapping[str, Any]) -> SyntheticTask:
    return SyntheticTask(
        task_id=str(record["task_id"]),
        split=str(record["split"]),
        family=str(record["family"]),
        context=dict(record["context"]),
        params=dict(record["params"]),
        seed=int(record["seed"]),
    )


def load_frozen_package(root: str | Path) -> dict[str, Any]:
    """加载并严格校验 S0-2 冻结包；返回 tasks/split/frozen/prereg 与身份摘要。"""
    package = Path(root)
    if not package.is_dir():
        raise S1RunnerError(f"冻结包目录不存在: {package}")
    paths = {name: package / name for name in FROZEN_REQUIRED_FILES}
    for name, path in paths.items():
        if not path.is_file():
            raise S1RunnerError(f"冻结包缺少文件 {name}: {path}")
    raw_sha256 = {name: sha256_file(path) for name, path in paths.items()}
    tasks_payload = load_json_file(paths["tasks.json"])
    split = load_json_file(paths["meta_task_split.json"])
    frozen = load_json_file(paths["frozen_family.json"])
    prereg = load_json_file(paths["preregistration.json"])
    if not isinstance(tasks_payload, list):
        raise S1RunnerError("tasks.json 必须是任务记录列表")
    fv3.verify_split_manifest_v3(split)
    fv3.verify_frozen_family_v3(frozen)
    fv3.verify_preregistration_v3(prereg, frozen)
    counts = dict(split.get("counts", {}))
    if counts != dict(fv3.SPLIT_COUNTS):
        raise S1RunnerError(f"冻结 split counts 不符: {counts!r}")
    tasks = tuple(_task_from_record(record) for record in tasks_payload)
    if len(tasks) != sum(fv3.SPLIT_COUNTS.values()):
        raise S1RunnerError(f"tasks.json 任务数 {len(tasks)} 与冻结计数不符")
    expected_ids = [task_id for split_name in fv3.SPLIT_ORDER for task_id in split["task_ids"][split_name]]
    if [task.task_id for task in tasks] != list(tasks_payload and [record["task_id"] for record in tasks_payload]) or sorted(expected_ids) != sorted(task.task_id for task in tasks):
        raise S1RunnerError("tasks.json 与 meta_task_split.json 的 task_id 集合不一致")
    identity = {
        "frozen_package": str(package),
        "frozen_run_id": str(frozen.get("run_id", "")),
        "family_id": str(frozen.get("family_id", "")),
        "family_version": str(frozen.get("family_version", "")),
        "family_fingerprint": str(frozen["family_fingerprint"]),
        "split_hash": str(split["split_hash"]),
        "prereg_id": str(prereg.get("prereg_id", "")),
        "prereg_digest": str(prereg["prereg_digest"]),
        "analysis_plan_digest": str(frozen["analysis_plan_digest"]),
        "radius_base": float(frozen["radius_base"]),
        "reference_solution": str(frozen["reference_solution"]),
        "task_counts": counts,
        "physical_call_count": 0,
        "raw_sha256": raw_sha256,
    }
    if abs(identity["radius_base"] - DEFAULT_RADIUS_BASE) > 1e-12:
        raise S1RunnerError(f"冻结 radius_base={identity['radius_base']} != {DEFAULT_RADIUS_BASE}")
    if tuple(frozen.get("arms", ())) != m5.S1_ARM_IDS:
        raise S1RunnerError(f"冻结 arms 与 S1 五臂不符: {frozen.get('arms')!r}")
    if tuple(frozen.get("k_values", ())) != m5.S1_K_VALUES:
        raise S1RunnerError(f"冻结 k_values 与 S1 K 集合不符: {frozen.get('k_values')!r}")
    if tuple(frozen.get("budgets", ())) != m5.S1_BUDGETS:
        raise S1RunnerError(f"冻结 budgets 与 S1 预算集合不符: {frozen.get('budgets')!r}")
    by_id = {task.task_id: task for task in tasks}
    if len(by_id) != len(tasks):
        raise S1RunnerError("tasks.json 存在重复 task_id")
    return {
        "package": package,
        "tasks": tasks,
        "tasks_by_id": by_id,
        "split": split,
        "frozen": frozen,
        "prereg": prereg,
        "identity": identity,
        "raw_sha256": raw_sha256,
    }


def frozen_identity_for_run(package: Mapping[str, Any]) -> dict[str, str]:
    identity = package["identity"]
    return {
        "family_version": str(identity["family_version"]),
        "family_fingerprint": str(identity["family_fingerprint"]),
        "split_hash": str(identity["split_hash"]),
        "prereg_digest": str(identity["prereg_digest"]),
        "analysis_plan_digest": str(identity["analysis_plan_digest"]),
    }


# ---------------------------------------------------------------------------
# 支持集种子 / run_id
# ---------------------------------------------------------------------------
def support_seed(task_id: str, meta_seed: int) -> int:
    text = f"{task_id}|s1-support|{int(meta_seed)}"
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) % (2**31 - 1)


def select_support_designs(task: SyntheticTask, *, k_shot: int, meta_seed: int) -> np.ndarray:
    support = task.support_subset(k_shot, support_seed(task.task_id, meta_seed))
    return np.asarray(support, dtype=np.float64)


def make_run_id(
    run_id: str,
    *,
    arm: str,
    budget: int,
    k_shot: int,
    task_id: str,
    meta_seed: int,
    opt_seed: int,
) -> str:
    return f"{run_id}--{arm}--B{int(budget)}--K{int(k_shot)}--T{task_id}--MS{int(meta_seed)}--OS{int(opt_seed)}"


# ---------------------------------------------------------------------------
# 端点计算（合同 §5；null 不插补、不转 0）
# ---------------------------------------------------------------------------
def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _reference_objective(task: SyntheticTask) -> float | None:
    if task.is_negative_control:
        return None
    try:
        reference = task.reference()
    except Exception:  # noqa: BLE001 - 参考解不可用时如实返回 None
        return None
    return _finite_or_none(reference.get("objective_star"))


def _min_violation_sum(records: Sequence[Any]) -> float | None:
    best: float | None = None
    for record in records:
        constraints = getattr(record, "constraints", None)
        if constraints is None:
            continue
        total = 0.0
        for value in constraints.values():
            number = float(value)
            if not math.isfinite(number):
                total = math.inf
                break
            total += max(0.0, number)
        if not math.isfinite(total):
            continue
        if best is None or total < best:
            best = total
    return best


def compute_endpoint_values(
    result: Any,
    task: SyntheticTask,
    *,
    budget: int,
    k_shot: int,
) -> dict[str, Any]:
    """把 ArmResult 转换为合同 §5 的 9 键端点（主端点无可行解时为 None）。"""
    records = list(getattr(result, "observations", ()) or ())
    feasible_count = sum(1 for record in records if getattr(record, "feasible", False))
    first_index = getattr(result, "first_feasible_eval_index", None)
    best = _finite_or_none(getattr(result, "best_feasible_value", None))
    if best is None:
        first_index = None if first_index is None else int(first_index)
    f_star = _reference_objective(task)
    if best is None or f_star is None:
        gap = None
    else:
        gap = (best - f_star) / max(abs(f_star), 1e-12)
    if first_index is None:
        first_in_support: bool | None = None
        first_after: int | None = None
    else:
        first_in_support = bool(int(first_index) <= int(k_shot))
        first_after = int(first_index) - int(k_shot) if int(first_index) > int(k_shot) else None
    non_support = max(0, int(budget) - int(k_shot))
    if non_support == 0:
        hit_non_support = None
    else:
        feasible_non_support = sum(
            1
            for index, record in enumerate(records, start=1)
            if index > int(k_shot) and getattr(record, "feasible", False)
        )
        hit_non_support = feasible_non_support / non_support
    values = {
        "best_feasible_value": best,
        "gap_to_reference": gap,
        "first_feasible_eval_index": None if first_index is None else int(first_index),
        "feasible_hit_rate": feasible_count / int(budget),
        "first_feasible_in_support": first_in_support,
        "first_feasible_after_support_index": first_after,
        "feasible_hit_rate_non_support": hit_non_support,
        "n_nonnull": 0,
        "null_rate": 0.0,
    }
    main_values = [values[name] for name in PRIMARY_ENDPOINTS]
    non_null = sum(1 for value in main_values if value is not None)
    values["n_nonnull"] = int(non_null)
    values["null_rate"] = (len(main_values) - non_null) / len(main_values)
    if set(values) != set(ENDPOINT_KEYS):
        raise S1RunnerError(f"端点键与冻结 ENDPOINT_ROW_KEYS 不一致: {sorted(values)}")
    return values


def compute_fallback_values(result: Any) -> dict[str, Any]:
    records = list(getattr(result, "observations", ()) or ())
    objectives = [
        _finite_or_none(getattr(record, "objective", None))
        for record in records
    ]
    objectives = [value for value in objectives if value is not None]
    return {
        "best_objective_raw": min(objectives) if objectives else None,
        "min_constraint_violation_sum": _min_violation_sum(records),
    }


# ---------------------------------------------------------------------------
# 历史 digest 与 run record
# ---------------------------------------------------------------------------
def _history_rows(result: Any, *, task: SyntheticTask, seed: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    best_feasible_so_far: float | None = None
    best_value_so_far: float | None = None
    for record in getattr(result, "observations", ()):
        objective = _finite_or_none(getattr(record, "objective", None))
        feasible = bool(getattr(record, "feasible", False))
        if feasible and objective is not None:
            if best_feasible_so_far is None or objective < best_feasible_so_far:
                best_feasible_so_far = objective
        if objective is not None and (best_value_so_far is None or objective < best_value_so_far):
            best_value_so_far = objective
        constraints = getattr(record, "constraints", None) or {}
        rows.append(
            {
                "task_id": task.task_id,
                "split": task.split,
                "family": task.family,
                "seed": int(seed),
                "eval_index": int(record.eval_index),
                "objective": objective,
                "feasible": feasible,
                "constraints_json": json.dumps(dict(constraints), sort_keys=True, ensure_ascii=False),
                "cache_hit": bool(getattr(record, "cache_hit", False)),
                "billable": bool(getattr(record, "billable", True)),
                "status": str(getattr(record, "status", "")),
                "design_u": [float(value) for value in np.asarray(record.design_u, dtype=np.float64)],
                "best_feasible_so_far": best_feasible_so_far,
                "best_value_so_far": best_value_so_far,
            }
        )
    return rows


def history_digest(result: Any, *, task: SyntheticTask, seed: int) -> str:
    """评价历史 canonical sha256（不含 run_id/arm，保证 K=0 CLONE 对可逐字节比较）。"""
    rows = _history_rows(result, task=task, seed=seed)
    payload = {"header": list(rows[0]) if rows else [], "rows": rows}
    return digest(payload)


def _adaptation_wall_s(proxy_scoring_cost: Any) -> float | None:
    """适配墙钟：兼容代理成本块的两种布局（顶层 wall_s 或 model_scoring.wall_s）。"""
    if not isinstance(proxy_scoring_cost, Mapping):
        return None
    direct = _finite_or_none(proxy_scoring_cost.get("wall_s"))
    if direct is not None:
        return direct
    nested = proxy_scoring_cost.get("model_scoring")
    if isinstance(nested, Mapping):
        return _finite_or_none(nested.get("wall_s"))
    return None


# ---------------------------------------------------------------------------
# 单 run 执行
# ---------------------------------------------------------------------------
class RunContext:
    """一次 S1 run 的输入上下文（任务、设计空间、模型工件、身份）。"""

    def __init__(
        self,
        *,
        task: SyntheticTask,
        design_space: Any,
        model_artifact: Mapping[str, Any] | None,
        identity: Mapping[str, str],
        run_id: str,
    ) -> None:
        self.task = task
        self.design_space = design_space
        self.model_artifact = model_artifact
        self.identity = dict(identity)
        self.run_id = run_id


def run_single(
    context: RunContext,
    *,
    arm: str,
    budget: int,
    k_shot: int,
    meta_seed: int,
    opt_seed: int,
    split: str | None = None,
    grid_stratum: str | None = None,
    support_label_permutation: Sequence[int] | None = None,
) -> dict[str, Any]:
    """执行单个 S1 run 并返回合同 §4 的 run record（异常时返回 FAILED_* 记录）。"""
    task = context.task
    if arm not in m5.S1_ARM_IDS:
        raise S1RunnerError(f"arm 必须是 {m5.S1_ARM_IDS} 之一，实际 {arm!r}")
    settled_grid_stratum = validate_grid_stratum(
        grid_stratum, budget=int(budget), k_shot=int(k_shot)
    )
    plan = m5.s1_expected_budget(k_shot, budget)
    identifiability = m5.s1_identifiability(arm, k_shot)
    run_id = make_run_id(
        context.run_id,
        arm=arm,
        budget=budget,
        k_shot=k_shot,
        task_id=task.task_id,
        meta_seed=meta_seed,
        opt_seed=opt_seed,
    )
    record: dict[str, Any] = {
        "schema_version": S1_RECORD_SCHEMA_VERSION,
        "run_id": run_id,
        "run_group_id": context.run_id,
        **{name: str(value) for name, value in context.identity.items()},
        "split": str(split or task.split),
        "task_id": task.task_id,
        "arm": arm,
        "budget_B": int(budget),
        "K": int(k_shot),
        "initial_designs": int(plan["initial_designs"]),
        "bo_calls": int(plan["bo_evals"]),
        "meta_seed": int(meta_seed),
        "opt_seed": int(opt_seed),
        "grid_stratum": settled_grid_stratum,
        "initial_designs_sha256": None,
        "initial_design_row_digests": None,
        "identifiability": str(identifiability["identifiability"]),
        "clone_of": identifiability["clone_of"],
        "inference_eligible": bool(identifiability["inference_eligible"]),
        "billable_evals": 0,
        "support_evals": 0,
        "initial_evals": 0,
        "bo_evals": 0,
        "endpoint_values": {name: None for name in ENDPOINT_KEYS},
        "fallback_values": {"best_objective_raw": None, "min_constraint_violation_sum": None},
        "cost": {
            "adaptation_wall_s": None,
            "proxy_scoring_cost": None,
            "peak_memory_mb": None,
            "total_wall_s": None,
        },
        "physics": {
            "physical_call_count": 0,
            "physical_call_sources": [],
            "physics_guard": "PASS",
        },
        "status": "FAILED_OTHER",
        "failure_reason": None,
        "history_digest": None,
    }
    started = time.perf_counter()
    try:
        evaluator = make_synthetic_task_evaluator(task, context.design_space)
        support = select_support_designs(task, k_shot=k_shot, meta_seed=meta_seed)
        result = m5.run_s1_arm(
            arm,
            evaluator,
            task=task,
            seed=int(opt_seed),
            budget=int(budget),
            k_shot=int(k_shot),
            support_designs=support,
            design_space=context.design_space,
            model_artifact=artifact_for_arm(context.model_artifact, arm),
            reference_objective=_reference_objective(task),
            run_id=run_id,
            support_label_permutation=support_label_permutation,
        )
        if result.requested_evaluations != budget:
            raise m5.S1ArmError(
                f"requested_evaluations={result.requested_evaluations} != budget={budget}"
            )
        if result.true_evals_used != budget - k_shot:
            raise m5.S1ArmError(
                f"true_evals_used={result.true_evals_used} != budget-k_shot={budget - k_shot}"
            )
        if result.cache_hits != k_shot:
            raise m5.S1ArmError(f"cache_hits={result.cache_hits} != k_shot={k_shot}")
        if result.billable if hasattr(result, "billable") else False:
            raise m5.S1ArmError("ArmResult 不应携带 billable 字段")
        record["billable_evals"] = int(result.requested_evaluations)
        record["support_evals"] = int(result.cache_hits)
        record["initial_evals"] = int(plan["initial_evals"])
        record["bo_evals"] = int(plan["bo_evals"])
        scoring = result.proxy_scoring_cost
        if isinstance(scoring, Mapping):
            model_scoring = scoring.get("model_scoring")
            if isinstance(model_scoring, Mapping):
                record["initial_designs_sha256"] = model_scoring.get("initial_designs_sha256")
                row_digests = model_scoring.get("initial_design_row_digests")
                if row_digests is not None:
                    record["initial_design_row_digests"] = [str(value) for value in row_digests]
        record["endpoint_values"] = compute_endpoint_values(
            result, task, budget=budget, k_shot=k_shot
        )
        record["fallback_values"] = compute_fallback_values(result)
        record["cost"] = {
            "adaptation_wall_s": _adaptation_wall_s(result.proxy_scoring_cost),
            "proxy_scoring_cost": result.proxy_scoring_cost,
            "peak_memory_mb": None,
            "total_wall_s": float(result.wall_s),
        }
        record["history_digest"] = history_digest(result, task=task, seed=opt_seed)
        record["status"] = "OK"
    except Exception as exc:  # noqa: BLE001 - 逐 run fail-closed，记录失败原因而不伪造数据
        message = f"{type(exc).__name__}: {exc}"
        record["failure_reason"] = message
        if isinstance(exc, m5.S1ArmError):
            record["status"] = "FAILED_BUDGET_MISMATCH"
        elif "泄漏" in message or "重叠" in message:
            record["status"] = "FAILED_LEAKAGE"
        elif "NONFINITE" in message or "nan" in message.lower():
            record["status"] = "FAILED_NONFINITE"
        else:
            record["status"] = "FAILED_OTHER"
        record["cost"]["total_wall_s"] = float(time.perf_counter() - started)
    record["record_digest"] = digest({key: value for key, value in record.items() if key != "record_digest"})
    return record


# ---------------------------------------------------------------------------
# 网格定义（不真正跑 21,000 runs；由 A2 在授权后执行）
# ---------------------------------------------------------------------------
def iter_run_plan(
    package: Mapping[str, Any],
    *,
    splits: Sequence[str] = (PRIMARY_SPLIT,),
    arms: Sequence[str] = m5.S1_ARM_IDS,
    budgets: Sequence[int] = m5.S1_BUDGETS,
    k_values: Sequence[int] = m5.S1_K_VALUES,
    meta_seeds: Sequence[int] = (0, 1, 2),
    opt_seeds: Sequence[int] = tuple(range(10)),
    task_limit: int | None = None,
) -> Iterable[dict[str, Any]]:
    split_payload = package["split"]
    for split_name in splits:
        if split_name not in split_payload["task_ids"]:
            raise S1RunnerError(f"冻结包无 split={split_name!r}")
        task_ids = list(split_payload["task_ids"][split_name])
        if task_limit is not None:
            task_ids = task_ids[: int(task_limit)]
        for arm in arms:
            for budget in budgets:
                for k_shot in k_values:
                    for meta_seed in meta_seeds:
                        for opt_seed in opt_seeds:
                            for task_id in task_ids:
                                yield {
                                    "split": split_name,
                                    "task_id": task_id,
                                    "arm": arm,
                                    "budget_B": int(budget),
                                    "K": int(k_shot),
                                    "meta_seed": int(meta_seed),
                                    "opt_seed": int(opt_seed),
                                }


def formal_grid_pairs() -> tuple[tuple[int, int], ...]:
    """正式网格允许出现的全部 (budget, K) 组合（有序；B=128/K=0 刻意不在内）。"""
    pairs: list[tuple[int, int]] = []
    for stratum in FORMAL_GRID_STRATA:
        for budget in stratum["budgets"]:
            for k_shot in stratum["k_values"]:
                pair = (int(budget), int(k_shot))
                if pair not in pairs:
                    pairs.append(pair)
    return tuple(pairs)


def formal_grid_stratum(budget: int, k_shot: int) -> str:
    """返回 (B,K) 所属正式分层名；不属于任何分层 -> S1RunnerError（fail-closed）。"""
    for stratum in FORMAL_GRID_STRATA:
        if int(budget) in stratum["budgets"] and int(k_shot) in stratum["k_values"]:
            return str(stratum["name"])
    raise S1RunnerError(
        f"(budget={budget}, K={k_shot}) 不属于正式分层网格（例如 B=128 x K=0 被显式排除）"
    )


def validate_grid_stratum(value: Any, *, budget: int, k_shot: int) -> str | None:
    """校验 record 的 grid_stratum：None 允许；否则必须是正式分层名且与 (B,K) 一致。

    fail-closed：未知分层、非字符串、或与 (budget, K) 所属分层不符 -> S1RunnerError。
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise S1RunnerError(f"grid_stratum 必须是字符串或 None，实际 {type(value).__name__}")
    if value not in FORMAL_GRID_STRATUM_NAMES:
        raise S1RunnerError(
            f"grid_stratum 非法: {value!r}（可选 {list(FORMAL_GRID_STRATUM_NAMES)} 或 None）"
        )
    expected = formal_grid_stratum(int(budget), int(k_shot))
    if value != expected:
        raise S1RunnerError(
            f"grid_stratum={value!r} 与 (budget={budget}, K={k_shot}) 所属分层 {expected!r} 不一致"
        )
    return value


def _formal_strata_expected_runs() -> dict[str, int]:
    return {str(stratum["name"]): int(stratum["expected_runs"]) for stratum in FORMAL_GRID_STRATA}


def _positive_int_list(values: Sequence[Any], label: str, *, allow_zero: bool = False) -> list[int]:
    parsed = [int(value) for value in values]
    if not parsed:
        raise S1RunnerError(f"{label} 不能为空")
    for value in parsed:
        if value < 0 or (value == 0 and not allow_zero):
            raise S1RunnerError(f"{label} 必须为正整数: {value}")
    return parsed


def iter_formal_run_plan(
    package: Mapping[str, Any],
    *,
    splits: Sequence[str] = (PRIMARY_SPLIT,),
    arms: Sequence[str] = m5.S1_ARM_IDS,
    budgets: Sequence[int] | None = None,
    k_values: Sequence[int] | None = None,
    meta_seeds: Sequence[int] = FORMAL_GRID_DEFAULT_META_SEEDS,
    opt_seeds: Sequence[int] = FORMAL_GRID_DEFAULT_OPT_SEEDS,
    task_limit: int | None = None,
) -> list[dict[str, Any]]:
    """S1 正式分层网格：main=B64xK{0,3,5}、secondary=B128xK{3,5}、exploratory=K1xB{64,128}。

    默认参数（meta_test / 全臂 / meta_seeds 0,1,2 / opt_seeds 0..9 / 20 任务）下恰为 21,000 条；
    非默认参数按同一分层规则缩放并在返回前做一致性校验（0/负数/未知分层/过滤后空层 -> fail-closed）。
    """
    split_payload = package["split"]
    split_names = [str(name) for name in splits]
    if not split_names:
        raise S1RunnerError("splits 不能为空")
    task_ids_by_split: dict[str, list[str]] = {}
    for split_name in split_names:
        if split_name not in split_payload["task_ids"]:
            raise S1RunnerError(f"冻结包无 split={split_name!r}")
        ids = list(split_payload["task_ids"][split_name])
        if task_limit is not None:
            limit = int(task_limit)
            if limit <= 0:
                raise S1RunnerError(f"task_limit 必须为正整数: {task_limit}")
            ids = ids[:limit]
        if not ids:
            raise S1RunnerError(f"split={split_name!r} 无任务")
        task_ids_by_split[split_name] = ids
    arm_list = [str(arm) for arm in arms]
    if not arm_list:
        raise S1RunnerError("arms 不能为空")
    unknown_arms = [arm for arm in arm_list if arm not in m5.S1_ARM_IDS]
    if unknown_arms:
        raise S1RunnerError(f"未知臂: {unknown_arms}")
    requested_budgets = None if budgets is None else _positive_int_list(budgets, "budget")
    requested_k = None if k_values is None else _positive_int_list(k_values, "K", allow_zero=True)
    meta_list = _positive_int_list(meta_seeds, "meta_seed", allow_zero=True)
    opt_list = _positive_int_list(opt_seeds, "opt_seed", allow_zero=True)
    allowed_pairs = [
        pair
        for pair in formal_grid_pairs()
        if (requested_budgets is None or pair[0] in requested_budgets)
        and (requested_k is None or pair[1] in requested_k)
    ]
    if not allowed_pairs:
        raise S1RunnerError(
            f"正式网格过滤后无 (budget,K) 组合: budgets={requested_budgets} k_values={requested_k}"
        )
    if any(int(budget) == 128 and int(k_shot) == 0 for budget, k_shot in allowed_pairs):
        raise S1RunnerError("正式网格不得包含 B=128 x K=0 组合")
    allowed_set = set(allowed_pairs)
    items: list[dict[str, Any]] = []
    for budget, k_shot in allowed_pairs:
        stratum = formal_grid_stratum(budget, k_shot)
        for split_name in split_names:
            for arm in arm_list:
                for meta_seed in meta_list:
                    for opt_seed in opt_list:
                        for task_id in task_ids_by_split[split_name]:
                            items.append(
                                {
                                    "split": split_name,
                                    "task_id": task_id,
                                    "arm": arm,
                                    "budget_B": int(budget),
                                    "K": int(k_shot),
                                    "meta_seed": int(meta_seed),
                                    "opt_seed": int(opt_seed),
                                    "grid_stratum": stratum,
                                }
                            )
    if not items:
        raise S1RunnerError("正式网格为空，拒绝继续")
    factor = len(arm_list) * len(meta_list) * len(opt_list) * sum(
        len(ids) for ids in task_ids_by_split.values()
    )
    stratum_counts = {name: 0 for name in _formal_strata_expected_runs()}
    for item in items:
        stratum_name = str(item["grid_stratum"])
        if stratum_name not in stratum_counts:
            raise S1RunnerError(f"未知分层: {stratum_name!r}")
        stratum_counts[stratum_name] += 1
    for stratum in FORMAL_GRID_STRATA:
        name = str(stratum["name"])
        stratum_pair_count = sum(
            1
            for budget in stratum["budgets"]
            for k_shot in stratum["k_values"]
            if (int(budget), int(k_shot)) in allowed_set
        )
        expected = stratum_pair_count * factor
        if stratum_counts[name] != expected:
            raise S1RunnerError(
                f"分层 {name!r} 计数不一致: actual={stratum_counts[name]} expected={expected}"
            )
        if stratum_counts[name] <= 0:
            raise S1RunnerError(f"分层 {name!r} 过滤后为 0 runs（fail-closed）")
    default_shape = (
        split_names == [PRIMARY_SPLIT]
        and tuple(arm_list) == tuple(m5.S1_ARM_IDS)
        and tuple(meta_list) == tuple(FORMAL_GRID_DEFAULT_META_SEEDS)
        and tuple(opt_list) == tuple(FORMAL_GRID_DEFAULT_OPT_SEEDS)
        and task_limit is None
        and requested_budgets is None
        and requested_k is None
    )
    if default_shape:
        if len(items) != FORMAL_GRID_TOTAL_RUNS:
            raise S1RunnerError(
                f"正式网格总数不一致: {len(items)} != {FORMAL_GRID_TOTAL_RUNS}"
            )
        for name, expected_runs in _formal_strata_expected_runs().items():
            if stratum_counts[name] != expected_runs:
                raise S1RunnerError(
                    f"正式网格分层 {name!r} 计数不一致: {stratum_counts[name]} != {expected_runs}"
                )
    return items


def summarize_formal_grid(plan: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """正式网格摘要（strata 计数、B=128xK0 计数；供 grid 命令与 run_config 复用）。"""
    items = list(plan)
    strata: list[dict[str, Any]] = []
    for stratum in FORMAL_GRID_STRATA:
        name = str(stratum["name"])
        subset = [item for item in items if item.get("grid_stratum") == name]
        pairs = sorted({(int(item["budget_B"]), int(item["K"])) for item in subset})
        strata.append(
            {
                "name": name,
                "budgets": [int(value) for value in stratum["budgets"]],
                "k_values": [int(value) for value in stratum["k_values"]],
                "expected_runs": int(stratum["expected_runs"]),
                "actual_runs": len(subset),
                "pairs": [[budget, k_shot] for budget, k_shot in pairs],
            }
        )
    forbidden = sum(
        1 for item in items if int(item["budget_B"]) == 128 and int(item["K"]) == 0
    )
    return {
        "grid_mode": FORMAL_GRID_MODE,
        "run_count": len(items),
        "strata": strata,
        "b128_k0_count": forbidden,
    }


def _record_core(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in DETERMINISM_EXCLUDED_FIELDS
    }


def compare_run_records(left: Sequence[Mapping[str, Any]], right: Sequence[Mapping[str, Any]]) -> list[str]:
    """确定性重跑比对：忽略 cost/record_digest（含墙钟时间），其余逐字段严格一致。"""
    if len(left) != len(right):
        return [f"记录数不一致: {len(left)} != {len(right)}"]
    problems: list[str] = []
    for index, (a, b) in enumerate(zip(left, right)):
        if a.get("run_id") != b.get("run_id"):
            problems.append(f"[{index}] run_id 不一致: {a.get('run_id')} != {b.get('run_id')}")
            continue
        core_a = canonical_json(_record_core(a))
        core_b = canonical_json(_record_core(b))
        if core_a != core_b:
            problems.append(f"[{index}] {a.get('run_id')} 确定性核心字段不一致")
    return problems


def initial_design_overlap(rows_a: Sequence[str], rows_b: Sequence[str]) -> dict[str, Any]:
    """两个臂的初始设计行指纹重叠率（分母取较大集合，与 M5 可辨识性审计口径一致）。"""
    set_a = {str(value) for value in rows_a}
    set_b = {str(value) for value in rows_b}
    denominator = max(len(set_a), len(set_b))
    shared = len(set_a & set_b)
    return {
        "shared_rows": shared,
        "row_count": denominator,
        "overlap_rate": (shared / denominator) if denominator else 0.0,
    }


def ranking_identifiability_report(
    records: Sequence[Mapping[str, Any]],
    *,
    threshold: float = IDENTIFIABILITY_OVERLAP_THRESHOLD,
) -> dict[str, Any]:
    """按 (task,B,K,meta_seed) 组统计模型打分臂初始设计重叠率并登记可辨识性。

    判定（预注册）：组内两两重叠率的最大值与平均值同时 >=90% 时登记
    RANKING_INDISTINGUISHABLE（该组不用于推断），否则 IDENTIFIABLE。
    """
    if not 0.0 < float(threshold) <= 1.0:
        raise S1RunnerError(f"threshold 必须在 (0,1]，实际 {threshold!r}")
    grouped: dict[tuple[str, int, int, int], dict[str, list[str]]] = {}
    for record in records:
        arm = str(record.get("arm"))
        if arm not in m5.S1_MODEL_SCORED_ARMS:
            continue
        rows = record.get("initial_design_row_digests")
        if not isinstance(rows, (list, tuple)) or not rows:
            continue
        key = (
            str(record.get("task_id")),
            int(record.get("budget_B")),
            int(record.get("K")),
            int(record.get("meta_seed")),
        )
        grouped.setdefault(key, {})[arm] = [str(value) for value in rows]
    groups: list[dict[str, Any]] = []
    pair_coverage: dict[str, int] = {
        f"{left}|{right}": 0 for left, right in IDENTIFIABILITY_REQUIRED_PAIRS
    }
    status_counts: dict[str, int] = {}
    for key in sorted(grouped):
        arms = grouped[key]
        names = sorted(arms)
        if len(names) < 2:
            continue
        pairwise: list[dict[str, Any]] = []
        rates: list[float] = []
        for index, arm_a in enumerate(names):
            for arm_b in names[index + 1:]:
                overlap = initial_design_overlap(arms[arm_a], arms[arm_b])
                rates.append(float(overlap["overlap_rate"]))
                pairwise.append({"arm_a": arm_a, "arm_b": arm_b, **overlap})
                for left, right in IDENTIFIABILITY_REQUIRED_PAIRS:
                    if {arm_a, arm_b} == {left, right}:
                        pair_coverage[f"{left}|{right}"] += 1
        max_rate = max(rates)
        mean_rate = sum(rates) / len(rates)
        status = (
            "RANKING_INDISTINGUISHABLE"
            if max_rate >= float(threshold) and mean_rate >= float(threshold)
            else "IDENTIFIABLE"
        )
        status_counts[status] = status_counts.get(status, 0) + 1
        groups.append(
            {
                "task_id": key[0],
                "budget_B": key[1],
                "K": key[2],
                "meta_seed": key[3],
                "arms": names,
                "pairwise": pairwise,
                "max_overlap_rate": max_rate,
                "mean_overlap_rate": mean_rate,
                "ranking_status": status,
                "inference_allowed": status == "IDENTIFIABLE",
            }
        )
    return {
        "schema_version": IDENTIFIABILITY_SCHEMA_VERSION,
        "threshold": float(threshold),
        "group_count": len(groups),
        "status_counts": status_counts,
        "pair_coverage": pair_coverage,
        "groups": groups,
    }


def write_run_bundle(
    outdir: str | Path,
    *,
    run_id: str,
    package: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    run_config: Mapping[str, Any],
) -> dict[str, Any]:
    directory = Path(outdir)
    if directory.exists() and any(directory.iterdir()):
        raise S1RunnerError(f"输出目录非空，拒绝覆盖: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    write_jsonl_file(directory / "run_records.jsonl", records)
    write_json_file(directory / "run_config.json", run_config)
    identifiability = ranking_identifiability_report(records)
    write_json_file(directory / "identifiability_report.json", identifiability)
    summary = {
        "schema_version": S1_SUMMARY_SCHEMA_VERSION,
        "run_id": run_id,
        "record_count": len(records),
        "status_counts": _count_by(records, "status"),
        "split_counts": _count_by(records, "split"),
        "arm_counts": _count_by(records, "arm"),
        "identifiability_counts": _count_by(records, "identifiability"),
        "physical_call_count_total": sum(
            int(record.get("physics", {}).get("physical_call_count", 0)) for record in records
        ),
        "identity": frozen_identity_for_run(package),
        "ranking_identifiability": identifiability,
        "run_records_sha256": sha256_file(directory / "run_records.jsonl"),
    }
    write_json_file(directory / "run_summary.json", summary)
    artifacts = []
    for name in (
        "run_records.jsonl",
        "run_config.json",
        "run_summary.json",
        "identifiability_report.json",
    ):
        path = directory / name
        payload = load_json_file(path) if name.endswith(".json") else None
        artifacts.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "raw_sha256": sha256_file(path),
                "canonical_sha256": digest(payload) if payload is not None else None,
            }
        )
    manifest = {
        "schema_version": S1_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "identity": frozen_identity_for_run(package),
        "artifacts": artifacts,
    }
    write_json_file(directory / "manifest.json", manifest)
    return summary


def _count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key))
        counts[value] = counts.get(value, 0) + 1
    return counts


def build_run_config(
    package: Mapping[str, Any],
    *,
    run_id: str,
    splits: Sequence[str],
    task_limit: int | None,
    arm: str,
    budget: int,
    k_shot: int,
    meta_seed: int,
    opt_seed: int,
) -> dict[str, Any]:
    return {
        "schema_version": S1_RUN_CONFIG_SCHEMA_VERSION,
        "run_id": run_id,
        "runner": "s1_runner",
        "identity": frozen_identity_for_run(package),
        "frozen_run_id": package["identity"]["frozen_run_id"],
        "split": list(splits),
        "task_limit": task_limit,
        "arm": arm,
        "budget_B": int(budget),
        "K": int(k_shot),
        "meta_seed": int(meta_seed),
        "opt_seed": int(opt_seed),
        "initial_designs": m5.S1_INITIAL_DESIGN_COUNT,
        "k_values": list(m5.S1_K_VALUES),
        "budgets": list(m5.S1_BUDGETS),
        "arms": list(m5.S1_ARM_IDS),
        "physical_call_count": 0,
        "evaluator": "synthetic-analytic",
        "created_utc": package["frozen"]["created_utc"],
    }


def artifact_for_arm(bundle: Mapping[str, Any] | None, arm: str) -> Mapping[str, Any] | None:
    """按臂选择代理工件：PRETRAIN 用预训练代理，FOMAML 用 MAML 代理，RAND/DE 无需模型。"""
    if bundle is None:
        return None
    if arm == m5.S1_PRETRAIN_KSHOT_BO:
        return bundle.get("pretrain")
    if arm in (m5.S1_FOMAML_ZERO_BO, m5.S1_FOMAML_KSHOT_BO):
        return bundle.get("maml")
    return None


def serialize_model_artifact(payload: Mapping[str, Any]) -> dict[str, Any]:
    """把内存代理工件转为可 JSON 化载荷（parameters/config 用 to_dict 展开）。"""
    from .maml import MAMLConfig, ParameterSet

    artifact = dict(payload.get("artifact") or {})
    parameters = artifact.get("parameters")
    if isinstance(parameters, ParameterSet):
        artifact["parameters"] = parameters.to_dict()
    elif not isinstance(parameters, Mapping):
        raise S1RunnerError("代理 artifact 缺少可序列化 parameters")
    config = artifact.get("config")
    if isinstance(config, MAMLConfig):
        artifact["config"] = config.to_dict()
    elif not isinstance(config, Mapping):
        raise S1RunnerError("代理 artifact 缺少可序列化 config")
    serialized = {
        "artifact": artifact,
        "target_names": list(payload.get("target_names") or ()),
        "meta_seed": int(payload.get("meta_seed")),
        "kind": str(payload.get("kind")),
        "training": dict(payload.get("training") or {}),
        "training_rows": [dict(row) for row in payload.get("training_rows") or ()],
        "artifact_sha256": str(payload.get("artifact_sha256")),
        "physical_call_count": 0,
        "wall_s": payload.get("wall_s"),
    }
    actual_sha = m5.artifact_sha256(serialized["artifact"])
    if actual_sha != serialized["artifact_sha256"]:
        raise S1RunnerError(f"代理 artifact 指纹不一致: {actual_sha} != {serialized['artifact_sha256']}")
    return serialized


def build_model_artifact_bundle(
    package: Mapping[str, Any],
    *,
    meta_seed: int,
    maml_steps: int | None = None,
    pretrain_steps: int | None = None,
) -> dict[str, Any]:
    """只用 meta_train 任务训练单个 meta_seed 的 pretrain/MAML 代理（零物理）。"""
    from .m5_arms import build_m5_model_artifacts
    from .offline_runner import build_task_blocks

    train_tasks = [task for task in package["tasks"] if task.split == "meta_train"]
    if not train_tasks:
        raise S1RunnerError("冻结包无 meta_train 任务，无法训练代理工件")
    blocks = build_task_blocks(train_tasks)
    kwargs: dict[str, Any] = {"meta_seed": int(meta_seed)}
    if maml_steps is not None:
        kwargs["maml_steps"] = int(maml_steps)
    if pretrain_steps is not None:
        kwargs["pretrain_steps"] = int(pretrain_steps)
    bundle = build_m5_model_artifacts(blocks, train_tasks, **kwargs)
    return {
        "meta_seed": int(meta_seed),
        "target_names": list(bundle["target_names"]),
        "pretrain": serialize_model_artifact(bundle["pretrain"]),
        "maml": serialize_model_artifact(bundle["maml"]),
        "artifacts_sha256": dict(bundle["artifacts_sha256"]),
        "physical_call_count": 0,
    }


def write_model_artifact_bundle(path: str | Path, bundle: Mapping[str, Any]) -> dict[str, Any]:
    target = Path(path)
    payload = dict(bundle)
    payload["schema_version"] = "p4ra-s1-model-artifacts-1"
    write_json_file(target, payload)
    return payload


def load_model_artifacts(root: str | Path, meta_seed: int) -> dict[str, Any]:
    """从目录加载某 meta_seed 的代理工件包（A2 训练产物）；缺失/篡改 fail-closed。"""
    directory = Path(root)
    candidate = directory / f"meta_seed_{int(meta_seed)}.json"
    if not candidate.is_file():
        raise S1RunnerError(f"缺少 meta_seed={meta_seed} 的代理工件: {candidate}")
    payload = load_json_file(candidate)
    if int(payload.get("meta_seed", -1)) != int(meta_seed):
        raise S1RunnerError(f"代理工件 meta_seed 不符: {candidate}")
    for kind in ("pretrain", "maml"):
        record = payload.get(kind)
        if not isinstance(record, Mapping) or not isinstance(record.get("artifact"), Mapping):
            raise S1RunnerError(f"代理工件缺少 {kind}.artifact 字段: {candidate}")
        actual_sha = m5.artifact_sha256(record["artifact"])
        if str(record.get("artifact_sha256")) != actual_sha:
            raise S1RunnerError(f"代理工件 {kind}.artifact_sha256 不符（被篡改）: {candidate}")
        record["artifact_sha256"] = actual_sha
    return payload


# ---------------------------------------------------------------------------
# CLI（实现自测入口；全量 21,000 runs 由 A2 在 Lead 授权后执行）
# ---------------------------------------------------------------------------
def _parse_int_list(text: Any, *, allowed: Sequence[int] | None = None, label: str = "值") -> list[int]:
    parts = [part.strip() for part in str(text).split(",") if part.strip()]
    if not parts:
        raise S1RunnerError(f"{label} 不能为空")
    try:
        values = [int(part) for part in parts]
    except ValueError as exc:
        raise S1RunnerError(f"{label} 必须是逗号分隔整数: {text!r}") from exc
    if allowed is not None:
        invalid = [value for value in values if value not in allowed]
        if invalid:
            raise S1RunnerError(f"{label} 非法: {invalid}，允许 {list(allowed)}")
    return values


def _parse_str_list(
    text: Any,
    *,
    allowed: Sequence[str] | None = None,
    default: Sequence[str] | None = None,
    label: str = "值",
) -> list[str]:
    raw = str(text).strip()
    if raw in ("", "all"):
        values = list(default or ())
    else:
        values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise S1RunnerError(f"{label} 不能为空")
    if allowed is not None:
        invalid = [value for value in values if value not in allowed]
        if invalid:
            raise S1RunnerError(f"{label} 非法: {invalid}")
    return values


def load_artifact_bundles(root: str | Path, meta_seeds: Sequence[int]) -> dict[int, dict[str, Any]]:
    bundles: dict[int, dict[str, Any]] = {}
    for seed in meta_seeds:
        bundles[int(seed)] = load_model_artifacts(root, int(seed))
    return bundles


def plan_from_args(package: Mapping[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    splits = _parse_str_list(
        args.splits,
        allowed=tuple(package["split"]["task_ids"]),
        default=[PRIMARY_SPLIT],
        label="split",
    )
    arms = _parse_str_list(args.arms, allowed=m5.S1_ARM_IDS, default=m5.S1_ARM_IDS, label="arm")
    budgets = _parse_int_list(args.budgets, allowed=m5.S1_BUDGETS, label="budget")
    k_values = _parse_int_list(args.k_values, allowed=m5.S1_K_VALUES, label="K")
    meta_seeds = _parse_int_list(args.meta_seeds, label="meta_seed")
    opt_seeds = _parse_int_list(args.opt_seeds, label="opt_seed")
    grid_mode = str(getattr(args, "grid", CARTESIAN_GRID_MODE))
    if grid_mode not in GRID_MODES:
        raise S1RunnerError(f"未知 grid 模式: {grid_mode!r}（可选 {list(GRID_MODES)}）")
    if grid_mode == FORMAL_GRID_MODE:
        return list(
            iter_formal_run_plan(
                package,
                splits=splits,
                arms=arms,
                budgets=budgets,
                k_values=k_values,
                meta_seeds=meta_seeds,
                opt_seeds=opt_seeds,
                task_limit=args.task_limit,
            )
        )
    return list(
        iter_run_plan(
            package,
            splits=splits,
            arms=arms,
            budgets=budgets,
            k_values=k_values,
            meta_seeds=meta_seeds,
            opt_seeds=opt_seeds,
            task_limit=args.task_limit,
        )
    )


def execute_runs(
    package: Mapping[str, Any],
    *,
    run_id: str,
    plan: Sequence[Mapping[str, Any]],
    bundles: Mapping[int, Mapping[str, Any]] | None = None,
    design_space: Any = None,
) -> list[dict[str, Any]]:
    """按计划顺序执行 runs（确定性：同一 plan/工件/run_id 逐位同结果）。"""
    bundle_map = dict(bundles or {})
    space = design_space if design_space is not None else _design_space()
    identity = frozen_identity_for_run(package)
    records: list[dict[str, Any]] = []
    for item in plan:
        arm = str(item["arm"])
        meta_seed = int(item["meta_seed"])
        bundle = bundle_map.get(meta_seed) if arm in m5.S1_MODEL_SCORED_ARMS else None
        if arm in m5.S1_MODEL_SCORED_ARMS and bundle is None:
            raise S1RunnerError(f"{arm} 需要 meta_seed={meta_seed} 的代理工件（--artifacts-root）")
        context = RunContext(
            task=package["tasks_by_id"][item["task_id"]],
            design_space=space,
            model_artifact=bundle,
            identity=identity,
            run_id=run_id,
        )
        records.append(
            run_single(
                context,
                arm=arm,
                budget=int(item["budget_B"]),
                k_shot=int(item["K"]),
                meta_seed=meta_seed,
                opt_seed=int(item["opt_seed"]),
                split=str(item["split"]),
                grid_stratum=item.get("grid_stratum"),
            )
        )
    return records


def build_grid_run_config(
    package: Mapping[str, Any],
    *,
    run_id: str,
    plan: Sequence[Mapping[str, Any]],
    grid_mode: str = CARTESIAN_GRID_MODE,
) -> dict[str, Any]:
    mode = str(grid_mode)
    if mode not in GRID_MODES:
        raise S1RunnerError(f"未知 grid 模式: {mode!r}（可选 {list(GRID_MODES)}）")
    items = list(plan)
    if not items:
        raise S1RunnerError("grid run_config 的 plan 不能为空")
    if mode == FORMAL_GRID_MODE:
        summary = summarize_formal_grid(items)
        grid_strata = summary["strata"]
    else:
        grid_strata = []
    return {
        "schema_version": S1_RUN_CONFIG_SCHEMA_VERSION,
        "run_id": run_id,
        "runner": "s1_runner",
        "grid_mode": mode,
        "grid_strata": grid_strata,
        "identity": frozen_identity_for_run(package),
        "frozen_run_id": package["identity"]["frozen_run_id"],
        "record_count": len(items),
        "run_count": len(items),
        "splits": sorted({str(item["split"]) for item in items}),
        "arms": sorted({str(item["arm"]) for item in items}),
        "budgets": sorted({int(item["budget_B"]) for item in items}),
        "k_values": sorted({int(item["K"]) for item in items}),
        "meta_seeds": sorted({int(item["meta_seed"]) for item in items}),
        "opt_seeds": sorted({int(item["opt_seed"]) for item in items}),
        "task_ids": sorted({str(item["task_id"]) for item in items}),
        "physical_call_count": 0,
        "evaluator": "synthetic-analytic",
        "created_utc": package["frozen"]["created_utc"],
    }


_CLONE_IGNORED_FIELDS = (
    "run_id",
    "arm",
    "identifiability",
    "clone_of",
    "inference_eligible",
    "record_digest",
    "cost",
)


def clone_pairs_check(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """K=0 FOMAML-KSHOT 与 FOMAML-ZERO 必须逐字段等价（忽略臂标识/墙钟）。"""
    index = {
        (record["arm"], record["task_id"], int(record["budget_B"]), int(record["K"]), int(record["meta_seed"]), int(record["opt_seed"])): record
        for record in records
    }
    pairs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    problems: list[str] = []
    for record in records:
        if record["arm"] != m5.S1_FOMAML_KSHOT_BO or int(record["K"]) != 0:
            continue
        key = (
            m5.S1_FOMAML_ZERO_BO,
            record["task_id"],
            int(record["budget_B"]),
            0,
            int(record["meta_seed"]),
            int(record["opt_seed"]),
        )
        counterpart = index.get(key)
        entry = {
            "task_id": record["task_id"],
            "budget_B": int(record["budget_B"]),
            "meta_seed": int(record["meta_seed"]),
            "opt_seed": int(record["opt_seed"]),
        }
        if counterpart is None:
            # 计划未包含 K=0 的 FOMAML-ZERO 对照时不构成违约，只登记为跳过（fail-closed 仍由正式网格保证）。
            entry.update({"status": "SKIPPED_MISSING_COUNTERPART"})
            skipped.append(entry)
            continue
        left = {name: value for name, value in counterpart.items() if name not in _CLONE_IGNORED_FIELDS}
        right = {name: value for name, value in record.items() if name not in _CLONE_IGNORED_FIELDS}
        equal = canonical_json(left) == canonical_json(right)
        history_equal = counterpart["history_digest"] == record["history_digest"]
        entry.update(
            {
                "status": "PASS" if equal and history_equal else "MISMATCH",
                "history_digest_equal": bool(history_equal),
                "core_equal_ignoring_arm": bool(equal),
                "zero_run_id": counterpart["run_id"],
                "kshot_run_id": record["run_id"],
            }
        )
        pairs.append(entry)
        if not (equal and history_equal):
            problems.append(f"K=0 CLONE 不等价: {record['task_id']} B={record['budget_B']} ms={record['meta_seed']} os={record['opt_seed']}")
    status = "PASS" if pairs and not problems else ("NOT_APPLICABLE" if not pairs else "FAIL")
    return {"status": status, "pairs": pairs, "skipped": skipped, "problems": problems}


def run_determinism(
    package: Mapping[str, Any],
    *,
    outdir: str | Path,
    run_id: str,
    plan: Sequence[Mapping[str, Any]],
    bundles: Mapping[int, Mapping[str, Any]],
    repeats: int = 3,
) -> dict[str, Any]:
    """确定性重跑：完全相同的 plan 重复 N 次，逐 run 核心字段必须逐位一致。"""
    if type(repeats) is not int or repeats < 2:
        raise S1RunnerError(f"repeats 必须是 >=2 的整数，实际 {repeats!r}")
    directory = Path(outdir)
    if directory.exists() and any(directory.iterdir()):
        raise S1RunnerError(f"输出目录非空，拒绝覆盖: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    run_config = build_grid_run_config(package, run_id=run_id, plan=plan)
    repeat_reports: list[dict[str, Any]] = []
    problems: list[str] = []
    baseline: list[dict[str, Any]] | None = None
    for repeat in range(1, int(repeats) + 1):
        records = execute_runs(package, run_id=run_id, plan=plan, bundles=bundles)
        repeat_dir = directory / f"repeat{repeat}"
        write_run_bundle(repeat_dir, run_id=run_id, package=package, records=records, run_config=run_config)
        core_sha = digest([_record_core(record) for record in records])
        history_sha = digest([record["history_digest"] for record in records])
        if baseline is None:
            baseline = records
        else:
            problems.extend(f"repeat{repeat}: {problem}" for problem in compare_run_records(baseline, records))
        repeat_reports.append(
            {
                "repeat": repeat,
                "record_count": len(records),
                "records_core_sha256": core_sha,
                "history_sha256": history_sha,
                "run_records_sha256": sha256_file(repeat_dir / "run_records.jsonl"),
                "status_counts": _count_by(records, "status"),
            }
        )
    clones = clone_pairs_check(baseline or [])
    if clones["status"] == "FAIL":
        problems.extend(f"clone: {problem}" for problem in clones["problems"])
    status = "PASS" if not problems else "FAIL"
    report = {
        "schema_version": "p4ra-s1-determinism-report-1",
        "status": status,
        "run_id": run_id,
        "repeats": int(repeats),
        "record_count": len(plan),
        "identity": frozen_identity_for_run(package),
        "independence": "same-process-repeated",
        "excluded_fields": list(DETERMINISM_EXCLUDED_FIELDS),
        "repeat_reports": repeat_reports,
        "clone_pairs": clones,
        "problems": problems,
        "physical_call_count": 0,
    }
    write_json_file(directory / "determinism_report.json", report)
    return report


def _label_permutation(task_id: str, arm: str, k_shot: int, opt_seed: int) -> list[int]:
    seed_text = digest({"task_id": task_id, "arm": arm, "K": int(k_shot), "opt_seed": int(opt_seed)})
    rng = np.random.default_rng(int(seed_text[:12], 16) % (2**31 - 1))
    return [int(value) for value in rng.permutation(int(k_shot))]


def run_label_shuffle_diagnostic(
    package: Mapping[str, Any],
    *,
    outdir: str | Path,
    run_id: str,
    plan: Sequence[Mapping[str, Any]],
    bundles: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    """§7 标签打乱负控：同支持集只置换支持标签，诊断模型优势是否消失/缩小。"""
    directory = Path(outdir)
    if directory.exists() and any(directory.iterdir()):
        raise S1RunnerError(f"输出目录非空，拒绝覆盖: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    space = _design_space()
    identity = frozen_identity_for_run(package)
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    for item in plan:
        arm = str(item["arm"])
        k_shot = int(item["K"])
        if k_shot < 2:
            raise S1RunnerError("label-shuffle 诊断要求 K>=2")
        if arm not in m5.S1_MODEL_SCORED_ARMS:
            raise S1RunnerError("label-shuffle 诊断只接受模型打分臂")
        meta_seed = int(item["meta_seed"])
        bundle = bundles.get(meta_seed)
        if bundle is None:
            raise S1RunnerError(f"{arm} 需要 meta_seed={meta_seed} 的代理工件")
        context = RunContext(
            task=package["tasks_by_id"][item["task_id"]],
            design_space=space,
            model_artifact=bundle,
            identity=identity,
            run_id=run_id,
        )
        kwargs = dict(
            arm=arm,
            budget=int(item["budget_B"]),
            k_shot=k_shot,
            meta_seed=meta_seed,
            opt_seed=int(item["opt_seed"]),
            split=str(item["split"]),
        )
        truth = run_single(context, **kwargs)
        permutation = _label_permutation(str(item["task_id"]), arm, k_shot, int(item["opt_seed"]))
        shuffled = run_single(context, support_label_permutation=permutation, **kwargs)
        if truth["status"] != "OK" or shuffled["status"] != "OK":
            problems.append(f"{truth['run_id']} 状态异常: {truth['status']}/{shuffled['status']}")
        before = truth["endpoint_values"].get("best_feasible_value")
        after = shuffled["endpoint_values"].get("best_feasible_value")
        delta = None
        if before is not None and after is not None:
            delta = (float(after) - float(before)) / max(abs(float(before)), 1e-12)
        rows.append(
            {
                "task_id": item["task_id"],
                "arm": arm,
                "budget_B": int(item["budget_B"]),
                "K": k_shot,
                "meta_seed": meta_seed,
                "opt_seed": int(item["opt_seed"]),
                "best_feasible_true": before,
                "best_feasible_shuffled": after,
                "relative_delta": delta,
                "history_equal": truth["history_digest"] == shuffled["history_digest"],
                "status": "OK" if truth["status"] == "OK" and shuffled["status"] == "OK" else "FAILED",
            }
        )
    aggregates: dict[str, Any] = {}
    for row in rows:
        if row["relative_delta"] is None:
            continue
        key = f"{row['arm']}|K{row['K']}"
        bucket = aggregates.setdefault(key, {"deltas": [], "arms": row["arm"], "K": row["K"]})
        bucket["deltas"].append(float(row["relative_delta"]))
    for bucket in aggregates.values():
        values = bucket.pop("deltas")
        bucket["n"] = len(values)
        bucket["mean_relative_delta"] = sum(values) / len(values)
        bucket["shuffled_worse_or_equal"] = bool(bucket["mean_relative_delta"] >= 0.0)
        if bucket["arms"] == m5.S1_FOMAML_ZERO_BO:
            bucket["expected"] = "NO_EFFECT"
            bucket["status"] = "PASS" if abs(bucket["mean_relative_delta"]) == 0.0 else "UNEXPECTED_EFFECT"
        else:
            bucket["expected"] = "ADVANTAGE_SHRINKS"
            bucket["status"] = "SHRUNK_OR_DISAPPEARED" if bucket["mean_relative_delta"] >= 0.0 else "NO_SHRINK_DISCLOSE"
    status = "PASS" if not problems else "FAIL"
    report = {
        "schema_version": "p4ra-s1-label-shuffle-report-1",
        "status": status,
        "run_id": run_id,
        "identity": frozen_identity_for_run(package),
        "diagnostic_only": True,
        "note": "只置换用于适配的支持标签；支持点本身与逐 run 真实评价不变",
        "rows": rows,
        "aggregates": aggregates,
        "problems": problems,
        "physical_call_count": 0,
    }
    write_json_file(directory / "label_shuffle_report.json", report)
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="S1 五臂等预算 runner（零物理调用）")
    sub = parser.add_subparsers(dest="command", required=True)
    selftest = sub.add_parser("selftest", help="小规模自测：指定任务/臂/K/B/种子")
    selftest.add_argument("--frozen", required=True)
    selftest.add_argument("--outdir", required=True)
    selftest.add_argument("--artifacts-root", default=None)
    selftest.add_argument("--run-id", default="p4ra-s1-selftest")
    selftest.add_argument("--arm", default="RAND-BO", choices=list(m5.S1_ARM_IDS))
    selftest.add_argument("--budget", type=int, default=64, choices=list(m5.S1_BUDGETS))
    selftest.add_argument("--k-shot", type=int, default=0, choices=list(m5.S1_K_VALUES))
    selftest.add_argument("--meta-seed", type=int, default=0)
    selftest.add_argument("--opt-seed", type=int, default=0)
    selftest.add_argument("--task-limit", type=int, default=2)
    selftest.add_argument("--split", default=PRIMARY_SPLIT)
    prepare = sub.add_parser("prepare-artifacts", help="训练并落盘 meta_seed 代理工件（仅 meta_train）")
    prepare.add_argument("--frozen", required=True)
    prepare.add_argument("--outdir", required=True)
    prepare.add_argument("--meta-seeds", default="0,1,2")
    prepare.add_argument("--maml-steps", type=int, default=None)
    prepare.add_argument("--pretrain-steps", type=int, default=None)
    run = sub.add_parser("run", help="按网格计划执行并写 run bundle（A2 授权后使用）")
    run.add_argument("--frozen", required=True)
    run.add_argument("--outdir", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--artifacts-root", default=None)
    run.add_argument("--splits", default=PRIMARY_SPLIT)
    run.add_argument("--arms", default="all")
    run.add_argument("--budgets", default="64,128")
    run.add_argument("--k-values", default="0,1,3,5")
    run.add_argument("--meta-seeds", default="0,1,2")
    run.add_argument("--opt-seeds", default="0,1,2,3,4,5,6,7,8,9")
    run.add_argument("--task-limit", type=int, default=None)
    run.add_argument("--grid", choices=list(GRID_MODES), default=CARTESIAN_GRID_MODE)
    det = sub.add_parser("determinism", help="确定性重跑子集（200 runs x N）")
    det.add_argument("--frozen", required=True)
    det.add_argument("--outdir", required=True)
    det.add_argument("--run-id", required=True)
    det.add_argument("--artifacts-root", default=None)
    det.add_argument("--splits", default=PRIMARY_SPLIT)
    det.add_argument("--arms", default="all")
    det.add_argument("--budgets", default="64")
    det.add_argument("--k-values", default="0,3")
    det.add_argument("--meta-seeds", default="0")
    det.add_argument("--opt-seeds", default="0")
    det.add_argument("--task-limit", type=int, default=None)
    det.add_argument("--repeats", type=int, default=3)
    shuffle = sub.add_parser("label-shuffle", help="标签打乱负控诊断（只置换支持标签）")
    shuffle.add_argument("--frozen", required=True)
    shuffle.add_argument("--outdir", required=True)
    shuffle.add_argument("--run-id", required=True)
    shuffle.add_argument("--artifacts-root", required=True)
    shuffle.add_argument("--splits", default=PRIMARY_SPLIT)
    shuffle.add_argument("--arms", default="PRETRAIN-KSHOT-BO,FOMAML-ZERO-BO,FOMAML-KSHOT-BO")
    shuffle.add_argument("--budgets", default="64")
    shuffle.add_argument("--k-values", default="3,5")
    shuffle.add_argument("--meta-seeds", default="0")
    shuffle.add_argument("--opt-seeds", default="0")
    shuffle.add_argument("--task-limit", type=int, default=2)
    grid = sub.add_parser("grid", help="打印全量网格计数（不执行）")
    grid.add_argument("--frozen", required=True)
    grid.add_argument("--tasks", type=int, default=None)
    grid.add_argument("--grid", choices=list(GRID_MODES), default=CARTESIAN_GRID_MODE)
    return parser


def _main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    package = load_frozen_package(args.frozen)
    if args.command == "grid":
        grid_mode = str(args.grid)
        if grid_mode == FORMAL_GRID_MODE:
            payload: dict[str, Any] = summarize_formal_grid(
                iter_formal_run_plan(package, task_limit=args.tasks)
            )
        elif grid_mode == CARTESIAN_GRID_MODE:
            count = sum(1 for _ in iter_run_plan(package, task_limit=args.tasks))
            payload = {
                "grid_mode": CARTESIAN_GRID_MODE,
                "run_count": count,
                "strata": [],
                "b128_k0_count": None,
            }
        else:
            raise S1RunnerError(f"未知 grid 模式: {grid_mode!r}")
        payload["identity"] = frozen_identity_for_run(package)
        print(canonical_json(payload))
        return 0
    if args.command == "prepare-artifacts":
        meta_seeds = _parse_int_list(args.meta_seeds, label="meta_seed")
        directory = Path(args.outdir)
        if directory.exists() and any(directory.iterdir()):
            raise S1RunnerError(f"输出目录非空，拒绝覆盖: {directory}")
        directory.mkdir(parents=True, exist_ok=True)
        written: dict[str, Any] = {}
        for meta_seed in meta_seeds:
            bundle = build_model_artifact_bundle(
                package,
                meta_seed=int(meta_seed),
                maml_steps=args.maml_steps,
                pretrain_steps=args.pretrain_steps,
            )
            payload = write_model_artifact_bundle(directory / f"meta_seed_{meta_seed}.json", bundle)
            written[str(meta_seed)] = {
                "path": f"meta_seed_{meta_seed}.json",
                "pretrain_sha256": payload["pretrain"]["artifact_sha256"],
                "maml_sha256": payload["maml"]["artifact_sha256"],
            }
        print(canonical_json({"status": "OK", "artifacts": written, "physical_call_count": 0}))
        return 0
    if args.command == "selftest":
        artifacts_root = Path(args.artifacts_root) if args.artifacts_root else None
        bundle = None
        if args.arm in m5.S1_MODEL_SCORED_ARMS:
            if artifacts_root is None:
                raise S1RunnerError(f"{args.arm} 需要 --artifacts-root 提供代理工件")
            bundle = load_model_artifacts(artifacts_root, args.meta_seed)
        split_payload = package["split"]
        plan = [
            {
                "split": args.split,
                "task_id": task_id,
                "arm": args.arm,
                "budget_B": int(args.budget),
                "K": int(args.k_shot),
                "meta_seed": int(args.meta_seed),
                "opt_seed": int(args.opt_seed),
            }
            for task_id in list(split_payload["task_ids"][args.split])[: int(args.task_limit)]
        ]
        bundles = {int(args.meta_seed): bundle} if bundle is not None else {}
        records = execute_runs(package, run_id=args.run_id, plan=plan, bundles=bundles)
        run_config = build_run_config(
            package,
            run_id=args.run_id,
            splits=[args.split],
            task_limit=args.task_limit,
            arm=args.arm,
            budget=args.budget,
            k_shot=args.k_shot,
            meta_seed=args.meta_seed,
            opt_seed=args.opt_seed,
        )
        summary = write_run_bundle(args.outdir, run_id=args.run_id, package=package, records=records, run_config=run_config)
        print(canonical_json({"status_counts": summary["status_counts"], "record_count": summary["record_count"]}))
        return 0
    plan = plan_from_args(package, args)
    model_arms = [item for item in plan if item["arm"] in m5.S1_MODEL_SCORED_ARMS]
    bundles: dict[int, dict[str, Any]] = {}
    if model_arms:
        if not getattr(args, "artifacts_root", None):
            raise S1RunnerError("计划含模型打分臂，必须提供 --artifacts-root")
        meta_seeds = sorted({int(item["meta_seed"]) for item in model_arms})
        bundles = load_artifact_bundles(args.artifacts_root, meta_seeds)
    if args.command == "run":
        records = execute_runs(package, run_id=args.run_id, plan=plan, bundles=bundles)
        run_config = build_grid_run_config(
            package, run_id=args.run_id, plan=plan, grid_mode=getattr(args, "grid", CARTESIAN_GRID_MODE)
        )
        summary = write_run_bundle(args.outdir, run_id=args.run_id, package=package, records=records, run_config=run_config)
        failed = summary["record_count"] - int(summary["status_counts"].get("OK", 0))
        print(
            canonical_json(
                {
                    "record_count": summary["record_count"],
                    "status_counts": summary["status_counts"],
                    "physical_call_count_total": summary["physical_call_count_total"],
                    "failed": failed,
                }
            )
        )
        return 0 if failed == 0 else 1
    if args.command == "determinism":
        report = run_determinism(package, outdir=args.outdir, run_id=args.run_id, plan=plan, bundles=bundles, repeats=args.repeats)
        print(canonical_json({"status": report["status"], "record_count": report["record_count"], "problems": report["problems"]}))
        return 0 if report["status"] == "PASS" else 1
    if args.command == "label-shuffle":
        report = run_label_shuffle_diagnostic(package, outdir=args.outdir, run_id=args.run_id, plan=plan, bundles=bundles)
        print(canonical_json({"status": report["status"], "rows": len(report["rows"]), "problems": report["problems"]}))
        return 0 if report["status"] == "PASS" else 1
    raise S1RunnerError(f"未知命令: {args.command!r}")


def _design_space() -> Any:
    """加载 12D 提升面设计空间（与 P4-CODE/M5 相同的单位门禁）。"""
    from .offline_runner import load_design_space_12d

    return load_design_space_12d()


if __name__ == "__main__":
    sys.exit(_main())
