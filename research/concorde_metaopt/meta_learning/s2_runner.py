"""S2（P4 路线 A / Issue #7 D-P4-003）runner：零物理、解析合成评价器上的等预算算法对照。

合同：docs/planning/p4_route_a_s2_execution_plan_20261106.md（v1.6）
- §2 数据边界（allowlist + 负控 + task_id 身份）；
- §3 episode 与确定性合同（seed 公式、bank manifest sha）；
- §4 算法/等预算/FD 门禁（FULL_MAML vs FOMAML，同一 config 仅 first_order 不同）；
- §5 训练/评估记录与资源实测；
- §7 prereg 构建/核验（s2_prereg.py）；
- §9 失败/停止规则。

关键不变量（逐 run fail-closed）：
- physical_call_count=0：不 import/调用 VSPAERO/SU2/RCAIDE Mission/CFD/WaveDrag/Gmsh；
- 只使用 S0-7 冻结包的 meta_train(60) 与 meta_validation(20)，holdout_rows_used=0；
- 两臂除 first_order 外逐字段相同；训练 episode bank 两臂共享且与 arm 无关；
- run_config / episode bank manifest / run_records_core 在两次独立进程间逐字节一致；
- FD 门禁（mode="full"，32 坐标，max_rel<=1e-6）不通过则拒绝启动并 fail-closed。

本模块 A1 所有（§10）；不写 docs/planning，不启动正式 run（A2 执行）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import random
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from . import maml
from . import s2_prereg as sp
from .task_family import SyntheticTask, TaskFamilyError, derive_seed, sample_designs

S2_RUNNER_SCHEMA_VERSION = "p4ra-s2-runner-v1"
# 共享接口 schema v2（计划 v1.6 §7）：版本/字段集单源来自 s2_prereg.py，禁止本地复制
S2_RUN_CONFIG_SCHEMA_VERSION = sp.RUN_CONFIG_SCHEMA_VERSION
S2_RUN_SUMMARY_SCHEMA_VERSION = sp.RUN_SUMMARY_SCHEMA_VERSION
S2_EPISODE_BANK_SCHEMA_VERSION = "p4ra-s2-episode-bank-v1"
S2_FD_GATE_SCHEMA_VERSION = "p4ra-s2-fd-gate-v1"
S2_RECORD_SCHEMA_VERSION = "p4ra-s2-run-record-v1"

RUN_MODES = ("FORMAL", "SMOKE")
ARM_IDS = ("FULL_MAML", "FOMAML")
ALLOWED_SPLITS = sp.ALLOWED_SPLITS
META_TRAIN_SPLIT = "meta_train"
META_VALIDATION_SPLIT = "meta_validation"

TRAIN_RECORD_FIELDS = (
    "record_type",
    "run_id",
    "arm",
    "meta_seed",
    "outer_step",
    "train_loss",
    "grad_norm",
    "inner_loss_first",
    "inner_loss_last",
    "wall_s",
    "peak_memory_mb",
    "status",
)
EVAL_RECORD_FIELDS = (
    "record_type",
    "run_id",
    "arm",
    "meta_seed",
    "task_id",
    "split",
    "K",
    "draw",
    "query_rmse_raw",
    "query_rmse_standardized",
    "query_mae_raw",
    "support_size",
    "query_size",
    "adaptation_inner_steps",
    "wall_s",
    "status",
)
RECORD_CORE_EXCLUDED_FIELDS = ("wall_s", "peak_memory_mb")
EVAL_STATUSES = sp.RECORD_STATUS_COUNTS
TRAIN_STATUSES = sp.RECORD_STATUS_COUNTS

# 错误码前缀（消息首段），供上层 fail-closed 判断
S2_RUNNER_ERROR = "S2_RUNNER_ERROR"
S2_RUNNER_BANK_ERROR = "S2_RUNNER_BANK_ERROR"
S2_RUNNER_RESOURCE_ERROR = "S2_RUNNER_RESOURCE_ERROR"
S2_RUNNER_STATE_ERROR = "S2_RUNNER_STATE_ERROR"
S2_RUNNER_PREREG_ERROR = "S2_RUNNER_PREREG_ERROR"
S2_RUNNER_VALIDATION_ERROR = "S2_RUNNER_VALIDATION_ERROR"

DEFAULT_BATCH_SIZE = 8
DEFAULT_SUPPORT_SIZE = 16
DEFAULT_QUERY_SIZE = 32
DEFAULT_EVAL_QUERY_SIZE = 64
DEFAULT_EVAL_K = (0, 1, 5, 10)
DEFAULT_EVAL_DRAWS = 10

# §5/§9 资源规则（v1.6：状态枚举/资源上限/记录状态改为共享接口 schema v2 单源）
RUN_RESOURCE_LIMITS = dict(sp.RUN_RESOURCE_LIMITS)
RUN_STATUSES = sp.RUN_STATUSES
SEED_STATUSES = sp.SEED_STATUSES
RECORD_STATUS_COUNTS = sp.RECORD_STATUS_COUNTS
SEED_WALL_CLOCK_LIMIT_S = RUN_RESOURCE_LIMITS["per_seed_train_wall_s"]
PEAK_MEMORY_LIMIT_MB = RUN_RESOURCE_LIMITS["peak_memory_mb"]
RUN_HARD_DEADLINE_S = RUN_RESOURCE_LIMITS["total_wall_s"]


class S2RunnerError(RuntimeError):
    """S2 runner 错误（fail-closed，消息含错误码前缀）。"""


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise S2RunnerError(f"{code}: {message}")


def _round_sig(value: float, digits: int = 6) -> float:
    """按有效数字舍入（用于 run_config 中跨进程稳定的 FD 摘要）。"""
    number = float(value)
    if not math.isfinite(number):
        raise S2RunnerError(f"{S2_RUNNER_STATE_ERROR}: 无法舍入非有限值 {number!r}")
    return float(format(number, f".{int(digits)}g"))


def canonical_sha256(value: Any) -> str:
    """canonical JSON + 末尾换行 的 sha256（与 s2_prereg 同口径）。"""
    return sp.canonical_sha256(value)


def array_sha256(array: Any) -> str:
    """float64 小端连续内存字节的 sha256（跨进程逐字节稳定，不受 JSON 浮点表示影响）。"""
    matrix = np.ascontiguousarray(np.asarray(array, dtype="<f8"))
    if not np.isfinite(matrix).all():
        raise S2RunnerError(f"{S2_RUNNER_BANK_ERROR}: 待哈希数组包含非有限值")
    return hashlib.sha256(matrix.tobytes()).hexdigest()


def record_core(record: Mapping[str, Any]) -> dict[str, Any]:
    """记录的核心投影：去掉墙钟/峰值内存等运行波动字段。"""
    return {str(key): value for key, value in record.items() if key not in RECORD_CORE_EXCLUDED_FIELDS}


def records_core_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(sp.canonical_json(record_core(record)).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_json_canonical(path: Path | str, payload: Any) -> str:
    """canonical JSON + 末尾换行落盘，返回文件 sha256（raw bytes）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = sp.canonical_json_line(payload)
    target.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_jsonl(path: Path | str, records: Iterable[Mapping[str, Any]]) -> str:
    """逐行 canonical JSON 落盘，返回文件 sha256（raw bytes）。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            line = sp.canonical_json(dict(record))
            handle.write(line + "\n")
            digest.update(line.encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()




# -- §2 数据边界 -------------------------------------------------------------


@dataclass(frozen=True)
class S2TaskSet:
    """冻结包 S0-7 中允许使用的任务与身份摘要（只含 meta_train / meta_validation）。"""

    meta_train: tuple[SyntheticTask, ...]
    meta_validation: tuple[SyntheticTask, ...]
    split_counts: dict[str, int]
    meta_train_task_ids_sha256: str
    meta_validation_task_ids_sha256: str
    holdout_task_ids_sha256: str
    frozen_package: dict[str, Any]


def _task_from_record(record: Mapping[str, Any]) -> SyntheticTask:
    try:
        return SyntheticTask(
            task_id=str(record["task_id"]),
            split=str(record["split"]),
            family=str(record["family"]),
            context=dict(record["context"]),
            params=dict(record["params"]),
            seed=int(record["seed"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise S2RunnerError(
            f"{S2_RUNNER_BANK_ERROR}: tasks.json 记录无法重建 SyntheticTask: {type(exc).__name__}: {exc}"
        ) from exc


def _verify_data_boundary(tasks: S2TaskSet, boundary: Mapping[str, Any]) -> None:
    """负控 3 项 + prereg data_boundary 字段逐项核对（fail-closed）。"""
    code = sp.S2_DATA_BOUNDARY_ERROR
    _require(
        list(boundary.get("allowed_splits") or []) == list(sp.ALLOWED_SPLITS),
        code,
        f"allowed_splits 应为 {list(sp.ALLOWED_SPLITS)}，实际 {boundary.get('allowed_splits')!r}",
    )
    _require(
        list(boundary.get("forbidden_splits") or []) == list(sp.FORBIDDEN_SPLITS),
        code,
        f"forbidden_splits 应为 {list(sp.FORBIDDEN_SPLITS)}",
    )
    _require(
        dict(boundary.get("split_counts") or {}) == dict(sp.EXPECTED_SPLIT_COUNTS),
        code,
        "split_counts 与冻结包不一致",
    )
    _require(
        tasks.split_counts == dict(sp.EXPECTED_SPLIT_COUNTS),
        code,
        f"冻结包 split 计数异常: {tasks.split_counts}",
    )
    _require(boundary.get("holdout_rows_used") == 0, code, "holdout_rows_used 必须为 0")
    _require(
        str(boundary.get("meta_train_task_ids_sha256")) == tasks.meta_train_task_ids_sha256,
        code,
        "meta_train task_id 集合摘要不匹配（负控 c）",
    )
    _require(
        str(boundary.get("meta_validation_task_ids_sha256")) == tasks.meta_validation_task_ids_sha256,
        code,
        "meta_validation task_id 集合摘要不匹配（负控 c）",
    )
    _require(
        str(boundary.get("holdout_task_ids_sha256")) == tasks.holdout_task_ids_sha256,
        code,
        "holdout task_id 集合摘要不匹配（负控 c）",
    )


def load_s2_tasks(
    package_dir: Path | str,
    *,
    expected_boundary: Mapping[str, Any] | None = None,
) -> S2TaskSet:
    """只读加载 S0-7 冻结包，仅返回 meta_train(60) / meta_validation(20)。

    负控：任务集若出现未知 split 立即 S2_DATA_BOUNDARY_ERROR；返回集合与预注册期望
    task_id 集合摘要不一致同样 fail-closed。
    """
    package = Path(package_dir)
    frozen = sp.inspect_frozen_package(package)
    raw_records = json.loads((package / "tasks.json").read_text(encoding="utf-8"))
    known_splits = set(sp.ALLOWED_SPLITS) | set(sp.FORBIDDEN_SPLITS)
    all_tasks: list[SyntheticTask] = []
    seen: set[str] = set()
    for record in raw_records:
        task = _task_from_record(record)  # type: ignore[arg-type]
        if task.split not in known_splits:
            raise S2RunnerError(
                f"{sp.S2_DATA_BOUNDARY_ERROR}: 未知 split {task.split!r}（task_id={task.task_id}）"
            )
        if task.task_id in seen:
            raise S2RunnerError(f"{S2_RUNNER_BANK_ERROR}: 重复 task_id {task.task_id!r}")
        seen.add(task.task_id)
        all_tasks.append(task)
    counts: dict[str, int] = {}
    for task in all_tasks:
        counts[task.split] = counts.get(task.split, 0) + 1
    _require(
        dict(sorted(counts.items())) == dict(sorted(sp.EXPECTED_SPLIT_COUNTS.items())),
        sp.S2_DATA_BOUNDARY_ERROR,
        f"冻结包 split 计数异常: {counts}",
    )
    meta_train = tuple(sorted((t for t in all_tasks if t.split == META_TRAIN_SPLIT), key=lambda t: t.task_id))
    meta_validation = tuple(
        sorted((t for t in all_tasks if t.split == META_VALIDATION_SPLIT), key=lambda t: t.task_id)
    )
    holdout_ids: list[str] = []
    for split in sp.FORBIDDEN_SPLITS:
        holdout_ids.extend(t.task_id for t in all_tasks if t.split == split)
    task_set = S2TaskSet(
        meta_train=meta_train,
        meta_validation=meta_validation,
        split_counts=dict(sorted(counts.items())),
        meta_train_task_ids_sha256=sp.ids_sha256([t.task_id for t in meta_train]),
        meta_validation_task_ids_sha256=sp.ids_sha256([t.task_id for t in meta_validation]),
        holdout_task_ids_sha256=sp.ids_sha256(holdout_ids),
        frozen_package=frozen,
    )
    if expected_boundary is not None:
        _verify_data_boundary(task_set, expected_boundary)
    return task_set


def assert_allowed_split(split: str, *, task_id: str = "") -> None:
    """episode 生成层数据边界断言（负控 b：holdout split 直接拒绝）。"""
    if split not in sp.ALLOWED_SPLITS:
        raise S2RunnerError(
            f"{sp.S2_DATA_BOUNDARY_ERROR}: split {split!r} 不允许用于 episode 生成（task_id={task_id!r}）"
        )


# -- §3 episode 与确定性 bank -------------------------------------------------


def _objective_targets(task: SyntheticTask, designs: np.ndarray) -> np.ndarray:
    """解析合成任务真值（纯解析、零物理）的标量目标。"""
    payload = task.truth(designs)
    targets = np.asarray(payload["objective"], dtype=np.float64).reshape(-1)
    _require(targets.shape[0] == designs.shape[0], S2_RUNNER_BANK_ERROR, "truth objective 行数与设计数不一致")
    if not np.isfinite(targets).all():
        raise S2RunnerError(f"{S2_RUNNER_BANK_ERROR}: truth objective 含非有限值（task_id={task.task_id}）")
    return targets


def rows_sha256(features: Any, targets: Any) -> str:
    """episode 行摘要：特征 float64 小端字节 sha + ':' + 目标同口径 sha 的 sha256。"""
    return hashlib.sha256(
        (array_sha256(features) + ":" + array_sha256(targets)).encode("ascii")
    ).hexdigest()


def _train_task_order(train_tasks: Sequence[SyntheticTask], meta_seed: int, outer_step: int) -> list[SyntheticTask]:
    """§3：60 个 meta_train 任务按 derive_seed("S2-train-order", m, s) 洗牌（两臂共享）。"""
    ordered: list[SyntheticTask] = sorted(train_tasks, key=lambda t: t.task_id)
    order = [task.task_id for task in ordered]
    rng = random.Random(derive_seed("S2-train-order", str(meta_seed), str(outer_step)))
    rng.shuffle(order)
    by_id = {task.task_id: task for task in ordered}
    return [by_id[task_id] for task_id in order]


def build_train_batch(
    train_tasks: Sequence[SyntheticTask],
    meta_seed: int,
    outer_step: int,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    support_size: int = DEFAULT_SUPPORT_SIZE,
    query_size: int = DEFAULT_QUERY_SIZE,
) -> tuple[list[maml.TaskEpisode], list[dict[str, Any]]]:
    """构建某 (meta_seed, outer_step) 的训练 batch 与 manifest 条目（确定性 seed 公式）。"""
    _require(batch_size > 0, S2_RUNNER_BANK_ERROR, "batch_size 必须为正")
    order = _train_task_order(train_tasks, meta_seed, outer_step)
    _require(len(order) >= batch_size, S2_RUNNER_BANK_ERROR, "meta_train 任务数不足以组成 batch")
    episodes: list[maml.TaskEpisode] = []
    entries: list[dict[str, Any]] = []
    for position, task in enumerate(order[:batch_size]):
        assert_allowed_split(task.split, task_id=task.task_id)
        _require(task.split == META_TRAIN_SPLIT, S2_RUNNER_BANK_ERROR, "训练 episode 只能来自 meta_train")
        support_designs = sample_designs(
            task, support_size, "support", derive_seed("S2-train-support", task.task_id, str(meta_seed), str(outer_step))
        )
        query_designs = sample_designs(
            task, query_size, "query", derive_seed("S2-train-query", task.task_id, str(meta_seed), str(outer_step))
        )
        support_targets = _objective_targets(task, support_designs)
        query_targets = _objective_targets(task, query_designs)
        episodes.append(
            maml.TaskEpisode(
                support_features=support_designs,
                support_targets=support_targets,
                query_features=query_designs,
                query_targets=query_targets,
                task_id=task.task_id,
            )
        )
        entries.append(
            {
                "meta_seed": int(meta_seed),
                "outer_step": int(outer_step),
                "position": int(position),
                "task_id": task.task_id,
                "split": task.split,
                "support_rows_sha256": rows_sha256(support_designs, support_targets),
                "query_rows_sha256": rows_sha256(query_designs, query_targets),
            }
        )
    return episodes, entries


def build_train_episode_bank(
    train_tasks: Sequence[SyntheticTask],
    *,
    meta_seeds: Sequence[int],
    outer_steps: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    support_size: int = DEFAULT_SUPPORT_SIZE,
    query_size: int = DEFAULT_QUERY_SIZE,
) -> dict[str, Any]:
    """生成训练 episode bank manifest（§3：逐 episode 记 task_id/split/行摘要）。"""
    _require(outer_steps > 0, S2_RUNNER_BANK_ERROR, "outer_steps 必须为正")
    _require(len(meta_seeds) > 0, S2_RUNNER_BANK_ERROR, "meta_seeds 不得为空")
    entries: list[dict[str, Any]] = []
    for meta_seed in meta_seeds:
        for outer_step in range(int(outer_steps)):
            _, step_entries = build_train_batch(
                train_tasks,
                int(meta_seed),
                int(outer_step),
                batch_size=batch_size,
                support_size=support_size,
                query_size=query_size,
            )
            entries.extend(step_entries)
    return {
        "schema_version": S2_EPISODE_BANK_SCHEMA_VERSION,
        "meta_seeds": [int(value) for value in meta_seeds],
        "outer_steps": int(outer_steps),
        "batch_size": int(batch_size),
        "support_size": int(support_size),
        "query_size": int(query_size),
        "episodes": entries,
    }


def episode_bank_sha256(manifest: Mapping[str, Any]) -> str:
    """bank manifest 的 canonical JSON（+末尾换行）sha256（跨进程稳定）。"""
    return canonical_sha256(manifest)


def build_eval_episode(
    task: SyntheticTask,
    meta_seed: int,
    k_shot: int,
    draw: int,
    *,
    query_size: int = DEFAULT_EVAL_QUERY_SIZE,
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray, np.ndarray]:
    """构建一个评估 episode；K=0 时 support 为空且不调用 sample_designs（§3）。"""
    assert_allowed_split(task.split, task_id=task.task_id)
    _require(task.split == META_VALIDATION_SPLIT, sp.S2_DATA_BOUNDARY_ERROR, "评估 episode 只能来自 meta_validation")
    _require(int(k_shot) >= 0 and int(draw) >= 0, S2_RUNNER_BANK_ERROR, "K/draw 必须为非负整数")
    query_designs = sample_designs(
        task, query_size, "query", derive_seed("S2-eval-query", task.task_id, str(meta_seed), str(k_shot), str(draw))
    )
    query_targets = _objective_targets(task, query_designs)
    if int(k_shot) == 0:
        return None, None, query_designs, query_targets
    support_designs = sample_designs(
        task, int(k_shot), "support", derive_seed("S2-eval-support", task.task_id, str(meta_seed), str(k_shot), str(draw))
    )
    support_targets = _objective_targets(task, support_designs)
    return support_designs, support_targets, query_designs, query_targets


# -- §4.3 FD 门禁 -------------------------------------------------------------


def run_fd_gate(
    train_tasks: Sequence[SyntheticTask],
    *,
    config: maml.MAMLConfig,
    meta_seed: int = 0,
    outer_step: int = 0,
    batch_size: int = DEFAULT_BATCH_SIZE,
    support_size: int = DEFAULT_SUPPORT_SIZE,
    query_size: int = DEFAULT_QUERY_SIZE,
    max_coordinates: int = 32,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    """在 FULL_MAML 上做 32 坐标中心差分门禁（零物理）；失败 fail-closed。"""
    _require(config.first_order is False, S2_RUNNER_VALIDATION_ERROR, "FD 门禁要求 FULL_MAML config（first_order=False）")
    batch, entries = build_train_batch(
        train_tasks,
        int(meta_seed),
        int(outer_step),
        batch_size=batch_size,
        support_size=support_size,
        query_size=query_size,
    )
    parameters = maml.init_parameters(config, seed=0)
    # 必须用 MAMLModel 携带真实 config（inner_steps=5 等）；仅传 ParameterSet 会丢失训练配置
    model = maml.MAMLModel(config=config, parameters=parameters)
    try:
        result = maml.finite_difference_gradient_check(
            model,
            batch,
            mode="full",
            max_coordinates=int(max_coordinates),
            min_coordinates=int(max_coordinates),
            tolerance=float(tolerance),
        )
    except maml.MAMLError as exc:
        raise S2RunnerError(f"{S2_RUNNER_VALIDATION_ERROR}: FD 门禁失败: {exc}") from exc
    _require(result.get("status") == "PASS", S2_RUNNER_VALIDATION_ERROR, "FD 门禁未返回 PASS")
    _require(int(result.get("n_checked") or 0) == int(max_coordinates), S2_RUNNER_VALIDATION_ERROR, "FD 检查坐标数不足")
    payload = {
        "schema_version": S2_FD_GATE_SCHEMA_VERSION,
        "mode": "full",
        "meta_seed": int(meta_seed),
        "outer_step": int(outer_step),
        "batch_size": int(batch_size),
        "support_size": int(support_size),
        "query_size": int(query_size),
        "episode_keys_sha256": canonical_sha256(
            [{key: entry[key] for key in ("task_id", "support_rows_sha256", "query_rows_sha256")} for entry in entries]
        ),
        "result": result,
        "physical_call_count": 0,
    }
    payload["fd_gate_sha256"] = canonical_sha256(payload)
    return payload


def summarize_fd_gate(fd_payload: Mapping[str, Any]) -> dict[str, Any]:
    """run_config 用的 FD 摘要（确定性：非整数数值按 6 位有效数字舍入）。"""
    result = dict(fd_payload.get("result") or {})
    return {
        "mode": "full",
        "tolerance": _round_sig(float(result.get("tolerance", 1e-6)), 6),
        "coordinates": int(result.get("n_checked") or 0),
        "coordinates_requested": int(result.get("coordinates_requested") or 0),
        "coordinates_available": int(result.get("coordinates_available") or 0),
        "n_checked": int(result.get("n_checked") or 0),
        "status": str(result.get("status")),
        "max_relative_error": _round_sig(float(result.get("max_relative_error", 0.0)), 6),
        "fd_gate_sha256": str(fd_payload.get("fd_gate_sha256")),
    }


# -- §5 资源实测 --------------------------------------------------------------


def _windows_peak_memory_bytes() -> int:
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    last_error = "psapi/kernel32 均不可用"
    for dll_name, function_name in (("psapi", "GetProcessMemoryInfo"), ("kernel32", "K32GetProcessMemoryInfo")):
        try:
            library = ctypes.WinDLL(dll_name)
            function = getattr(library, function_name)
        except (OSError, AttributeError) as exc:  # pragma: no cover - 平台差异
            last_error = f"{dll_name}.{function_name}: {exc}"
            continue
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        function.restype = wintypes.BOOL
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ok = function(process, ctypes.byref(counters), counters.cb)
        if ok:
            return int(counters.PeakWorkingSetSize)
        last_error = f"{dll_name}.{function_name} 返回 0"
    raise OSError(last_error)


def peak_memory_mb() -> float:
    """进程峰值驻留内存实测（MB）；不可测量时 fail-closed，绝不以 null 冒充 0。"""
    try:
        if sys.platform.startswith("win"):
            peak_bytes = _windows_peak_memory_bytes()
        else:  # pragma: no cover - CI 平台差异
            import resource

            usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            peak_bytes = usage if sys.platform == "darwin" else usage * 1024
    except OSError as exc:
        raise S2RunnerError(f"{S2_RUNNER_RESOURCE_ERROR}: 无法实测峰值内存: {exc}") from exc
    value = float(peak_bytes) / (1024.0 * 1024.0)
    _require(math.isfinite(value) and value > 0.0, S2_RUNNER_RESOURCE_ERROR, f"峰值内存实测值非法: {value!r}")
    return value


# -- §5 训练 ------------------------------------------------------------------


def config_from_arm(arm: Mapping[str, Any]) -> maml.MAMLConfig:
    """由 prereg arm 记录构造 MAMLConfig（两臂除 first_order 外逐字段相同）。"""
    config = dict(arm.get("config") or {})
    return maml.MAMLConfig(
        input_dim=int(config["input_dim"]),
        output_dim=int(config["output_dim"]),
        hidden_sizes=tuple(int(value) for value in config["hidden_sizes"]),
        inner_lr=float(config["inner_lr"]),
        inner_steps=int(config["inner_steps"]),
        outer_lr=float(config["outer_lr"]),
        tasks_per_batch=int(config["tasks_per_batch"]),
        first_order=bool(arm.get("first_order")),
        seed=int(config["seed"]),
        backend=str(config["backend"]),
    )


def _nonfinite(value: Any) -> bool:
    try:
        return not math.isfinite(float(value))
    except (TypeError, ValueError):
        return True


def train_arm(
    *,
    arm_id: str,
    run_id: str,
    task_set: S2TaskSet,
    config: maml.MAMLConfig,
    meta_seed: int,
    outer_steps: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    support_size: int = DEFAULT_SUPPORT_SIZE,
    query_size: int = DEFAULT_QUERY_SIZE,
    seed_wall_limit_s: float = SEED_WALL_CLOCK_LIMIT_S,
    memory_limit_mb: float = PEAK_MEMORY_LIMIT_MB,
    run_started: float | None = None,
    hard_deadline_s: float | None = None,
) -> dict[str, Any]:
    """单 (arm, meta_seed) 训练；含 §5/§9 资源停止路径（不重试、不伪造数值）。

    - 非有限 loss/grad -> 该 seed FAILED；
    - 单 seed 训练墙钟 > 20 min 或峰值内存 > 8 GB -> 该 seed RESOURCE_LIMIT；
    - 正式 run 总硬截止 2 h -> DEADLINE_EXCEEDED。
    """
    parameters = maml.init_parameters(config, seed=int(meta_seed))
    records: list[dict[str, Any]] = []
    status = "OK"
    failure: str | None = None
    wall_seconds = 0.0
    peak_mb = 0.0
    seed_started = time.perf_counter()

    def _stop(reason_status: str, reason: str) -> None:
        nonlocal status, failure
        status = reason_status
        failure = reason

    for outer_step in range(int(outer_steps)):
        if run_started is not None and hard_deadline_s is not None:
            if time.perf_counter() - run_started > float(hard_deadline_s):
                _stop(
                    "DEADLINE_EXCEEDED",
                    f"DEADLINE_EXCEEDED: run 总墙钟超过硬截止 {float(hard_deadline_s):.1f}s（outer_step={outer_step}）",
                )
                break
        if wall_seconds > float(seed_wall_limit_s):
            _stop(
                "RESOURCE_LIMIT",
                f"RESOURCE_LIMIT: (arm={arm_id}, meta_seed={meta_seed}) 训练墙钟 {wall_seconds:.3f}s > {float(seed_wall_limit_s):.1f}s",
            )
            break
        started = time.perf_counter()
        try:
            batch, _ = build_train_batch(
                task_set.meta_train,
                int(meta_seed),
                int(outer_step),
                batch_size=batch_size,
                support_size=support_size,
                query_size=query_size,
            )
            parameters, stats = maml.meta_train_step(
                parameters, batch, config, second_order=not config.first_order
            )
            elapsed = time.perf_counter() - started
            peak_mb = max(peak_mb, peak_memory_mb())
            metrics = {
                "train_loss": float(stats["outer_loss"]),
                "grad_norm": float(stats["grad_norm"]),
                "inner_loss_first": float(stats["inner_loss_first"]),
                "inner_loss_last": float(stats["inner_loss_last"]),
            }
            if any(_nonfinite(value) for value in metrics.values()):
                raise S2RunnerError(f"{S2_RUNNER_STATE_ERROR}: 训练统计含非有限值 outer_step={outer_step}")
            records.append(
                {
                    "record_type": "train",
                    "run_id": run_id,
                    "arm": arm_id,
                    "meta_seed": int(meta_seed),
                    "outer_step": int(outer_step),
                    **metrics,
                    "wall_s": elapsed,
                    "peak_memory_mb": peak_mb,
                    "status": "OK",
                }
            )
            wall_seconds += elapsed
        except Exception as exc:  # noqa: BLE001 - FAILED 行必须记录原因，不伪造数值
            elapsed = time.perf_counter() - started
            wall_seconds += elapsed
            status = "FAILED"
            failure = f"{type(exc).__name__}: {exc}"
            records.append(
                {
                    "record_type": "train",
                    "run_id": run_id,
                    "arm": arm_id,
                    "meta_seed": int(meta_seed),
                    "outer_step": int(outer_step),
                    "train_loss": None,
                    "grad_norm": None,
                    "inner_loss_first": None,
                    "inner_loss_last": None,
                    "wall_s": elapsed,
                    "peak_memory_mb": None,
                    "status": "FAILED",
                }
            )
            break
        if peak_mb > float(memory_limit_mb):
            _stop(
                "RESOURCE_LIMIT",
                f"RESOURCE_LIMIT: (arm={arm_id}, meta_seed={meta_seed}) 峰值内存 {peak_mb:.1f}MB > {float(memory_limit_mb):.1f}MB",
            )
            break
        if wall_seconds > float(seed_wall_limit_s):
            _stop(
                "RESOURCE_LIMIT",
                f"RESOURCE_LIMIT: (arm={arm_id}, meta_seed={meta_seed}) 训练墙钟 {wall_seconds:.3f}s > {float(seed_wall_limit_s):.1f}s",
            )
            break
    return {
        "arm": arm_id,
        "meta_seed": int(meta_seed),
        "status": status,
        "failure": failure,
        "records": records,
        "parameters": parameters if status == "OK" else None,
        "training_wall_s": wall_seconds,
        "peak_memory_mb": peak_mb if status == "OK" else None,
        "seed_elapsed_s": time.perf_counter() - seed_started,
    }


# -- §5 评估 ------------------------------------------------------------------


def _predict(parameters: maml.ParameterSet, features: np.ndarray) -> np.ndarray:
    maml._require_torch()
    tensors = maml._to_torch(parameters.tensors, requires_grad=False)
    feature_tensor = maml.torch.tensor(np.asarray(features, dtype=np.float64), dtype=maml.torch.float64)
    with maml.torch.no_grad():
        prediction = maml._forward_torch(tensors, feature_tensor)
    return np.asarray(prediction.detach().numpy(), dtype=np.float64).reshape(-1)


def _commitment_metrics(prediction: np.ndarray, targets: np.ndarray) -> tuple[float, float]:
    residual = np.asarray(prediction, dtype=np.float64) - np.asarray(targets, dtype=np.float64)
    rmse = float(math.sqrt(float(np.mean(residual**2))))
    mae = float(np.mean(np.abs(residual)))
    _require(math.isfinite(rmse) and math.isfinite(mae), S2_RUNNER_STATE_ERROR, "评估指标非有限")
    return rmse, mae


def evaluate_arm(
    *,
    arm_id: str,
    run_id: str,
    task_set: S2TaskSet,
    parameters: maml.ParameterSet,
    config: maml.MAMLConfig,
    meta_seed: int,
    k_values: Sequence[int],
    draws: int,
    query_size: int = DEFAULT_EVAL_QUERY_SIZE,
) -> list[dict[str, Any]]:
    """单 (arm, meta_seed) 在全部 meta_validation 任务上的 K-shot 评估记录。"""
    from dataclasses import replace

    records: list[dict[str, Any]] = []
    for task in task_set.meta_validation:
        for k_shot in k_values:
            for draw in range(int(draws)):
                started = time.perf_counter()
                support_size = int(k_shot)
                try:
                    support_features, support_targets, query_features, query_targets = build_eval_episode(
                        task, int(meta_seed), int(k_shot), int(draw), query_size=query_size
                    )
                    if int(k_shot) == 0:
                        adapted = parameters
                    else:
                        eval_config = replace(config, inner_steps=int(k_shot))
                        episode = maml.TaskEpisode(
                            support_features=support_features,
                            support_targets=support_targets,
                            query_features=query_features,
                            query_targets=query_targets,
                            task_id=task.task_id,
                        )
                        adapted, _ = maml.inner_adapt(parameters, episode, eval_config)
                    prediction = _predict(adapted, query_features)
                    rmse_raw, mae_raw = _commitment_metrics(prediction, query_targets)
                    standardized: float | None = None
                    if int(k_shot) >= 2:
                        std_support = float(np.std(np.asarray(support_targets).reshape(-1), ddof=1))
                        if math.isfinite(std_support) and std_support >= 1e-8:
                            standardized = rmse_raw / std_support
                    elapsed = time.perf_counter() - started
                    records.append(
                        {
                            "record_type": "eval",
                            "run_id": run_id,
                            "arm": arm_id,
                            "meta_seed": int(meta_seed),
                            "task_id": task.task_id,
                            "split": task.split,
                            "K": int(k_shot),
                            "draw": int(draw),
                            "query_rmse_raw": rmse_raw,
                            "query_rmse_standardized": standardized,
                            "query_mae_raw": mae_raw,
                            "support_size": support_size,
                            "query_size": int(query_features.shape[0]),
                            "adaptation_inner_steps": int(k_shot),
                            "wall_s": elapsed,
                            "status": "OK",
                        }
                    )
                except Exception as exc:  # noqa: BLE001 - FAILED 行不伪造指标
                    elapsed = time.perf_counter() - started
                    records.append(
                        {
                            "record_type": "eval",
                            "run_id": run_id,
                            "arm": arm_id,
                            "meta_seed": int(meta_seed),
                            "task_id": task.task_id,
                            "split": task.split,
                            "K": int(k_shot),
                            "draw": int(draw),
                            "query_rmse_raw": None,
                            "query_rmse_standardized": None,
                            "query_mae_raw": None,
                            "support_size": int(k_shot),
                            "query_size": int(query_size),
                            "adaptation_inner_steps": int(k_shot),
                            "wall_s": elapsed,
                            "status": "FAILED",
                        }
                    )
    return records


# -- §5 单 outer-step 计时（资源预估与报告披露用） ------------------------------

def measure_outer_step_timing(
    task_set: S2TaskSet,
    *,
    arm: Mapping[str, Any],
    meta_seed: int = 0,
    outer_step: int = 0,
    batch_size: int = DEFAULT_BATCH_SIZE,
    support_size: int = DEFAULT_SUPPORT_SIZE,
    query_size: int = DEFAULT_QUERY_SIZE,
) -> dict[str, Any]:
    """真实执行 1 个 outer step 并计时（零物理；不影响后续训练，参数随后重初始化）。"""
    config = config_from_arm(arm)
    parameters = maml.init_parameters(config, seed=int(meta_seed))
    batch, _ = build_train_batch(
        task_set.meta_train,
        int(meta_seed),
        int(outer_step),
        batch_size=batch_size,
        support_size=support_size,
        query_size=query_size,
    )
    started = time.perf_counter()
    _, stats = maml.meta_train_step(
        parameters, batch, config, second_order=not config.first_order
    )
    elapsed = time.perf_counter() - started
    return {
        "arm": str(arm.get("id")),
        "meta_seed": int(meta_seed),
        "outer_step": int(outer_step),
        "wall_s": elapsed,
        "outer_loss": float(stats["outer_loss"]),
        "grad_norm": float(stats["grad_norm"]),
        "first_order": bool(config.first_order),
    }


# -- §2/§3 预算解析与 run_config ------------------------------------------------

SMOKE_REQUIRED_OVERRIDES = ("outer_steps", "meta_seeds", "K", "draws", "eval_tasks")
SMOKE_OPTIONAL_OVERRIDES = (
    "batch_size",
    "support_size",
    "query_size",
    "eval_query_size",
    "fd_coordinates",
)


def _resource_limits_from_prereg(prereg: Mapping[str, Any]) -> dict[str, int]:
    """v1.5 §7：读取 prereg 固定资源上限（int），与 runner 常量逐项对齐（fail-closed）。"""
    raw = prereg.get("resource_limits")
    _require(isinstance(raw, Mapping), S2_RUNNER_PREREG_ERROR, "prereg 缺少 resource_limits")
    _require(
        set(raw) == set(RUN_RESOURCE_LIMITS),
        S2_RUNNER_PREREG_ERROR,
        f"resource_limits 键集合应为 {sorted(RUN_RESOURCE_LIMITS)}，实际 {sorted(raw)}",
    )
    limits: dict[str, int] = {}
    for key, expected in RUN_RESOURCE_LIMITS.items():
        value = raw[key]
        _require(type(value) is int, S2_RUNNER_PREREG_ERROR, f"resource_limits.{key} 必须是 int")
        _require(value == expected, S2_RUNNER_PREREG_ERROR, f"resource_limits.{key} 应为 {expected}，实际 {value}")
        limits[key] = int(value)
    return limits


def resolve_budget(
    prereg: Mapping[str, Any],
    *,
    run_mode: str,
    smoke_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """解析本次运行预算：FORMAL 完全取自 prereg；SMOKE 仅用于测试（显式覆盖并记录）。"""
    _require(run_mode in RUN_MODES, S2_RUNNER_VALIDATION_ERROR, f"未知 run_mode {run_mode!r}")
    training = dict(prereg.get("training_budget") or {})
    grid = dict(prereg.get("evaluation_grid") or {})
    fd_coordinates = int((prereg.get("fd_gate") or {}).get("coordinates") or 0)
    if run_mode == "FORMAL":
        return {
            "run_mode": run_mode,
            "meta_seeds": [int(value) for value in training["meta_seeds"]],
            "outer_steps": int(training["outer_steps"]),
            "batch_size": DEFAULT_BATCH_SIZE,
            "support_size": DEFAULT_SUPPORT_SIZE,
            "query_size": DEFAULT_QUERY_SIZE,
            "eval_query_size": DEFAULT_EVAL_QUERY_SIZE,
            "k_values": [int(value) for value in grid["K"]],
            "draws": int(grid["draws"]),
            "eval_task_limit": None,
            "fd_coordinates": fd_coordinates,
            "resource_limits": _resource_limits_from_prereg(prereg),
            "smoke": False,
        }
    overrides = dict(smoke_overrides or {})
    missing = [key for key in SMOKE_REQUIRED_OVERRIDES if key not in overrides]
    _require(not missing, S2_RUNNER_VALIDATION_ERROR, f"SMOKE 模式缺少覆盖字段 {missing}")
    unknown = set(overrides) - set(SMOKE_REQUIRED_OVERRIDES) - set(SMOKE_OPTIONAL_OVERRIDES)
    _require(not unknown, S2_RUNNER_VALIDATION_ERROR, f"SMOKE 覆盖含未知字段 {sorted(unknown)}")
    meta_seeds = [int(value) for value in overrides["meta_seeds"]]
    k_values = [int(value) for value in overrides["K"]]
    _require(len(meta_seeds) > 0, S2_RUNNER_VALIDATION_ERROR, "SMOKE meta_seeds 不得为空")
    _require(len(k_values) > 0 and all(value >= 0 for value in k_values), S2_RUNNER_VALIDATION_ERROR, "SMOKE K 非法")
    _require(int(overrides["outer_steps"]) >= 1, S2_RUNNER_VALIDATION_ERROR, "SMOKE outer_steps >= 1")
    _require(int(overrides["draws"]) >= 1, S2_RUNNER_VALIDATION_ERROR, "SMOKE draws >= 1")
    _require(int(overrides["eval_tasks"]) >= 1, S2_RUNNER_VALIDATION_ERROR, "SMOKE eval_tasks >= 1")
    return {
        "run_mode": run_mode,
        "meta_seeds": meta_seeds,
        "outer_steps": int(overrides["outer_steps"]),
        "batch_size": int(overrides.get("batch_size", 2)),
        "support_size": int(overrides.get("support_size", 4)),
        "query_size": int(overrides.get("query_size", 8)),
        "eval_query_size": int(overrides.get("eval_query_size", 16)),
        "k_values": k_values,
        "draws": int(overrides["draws"]),
        "eval_task_limit": int(overrides["eval_tasks"]),
        "fd_coordinates": int(overrides.get("fd_coordinates", 8)),
        "resource_limits": _resource_limits_from_prereg(prereg),
        "smoke": True,
    }


def _expected_record_counts(budget: Mapping[str, Any], eval_tasks: int) -> dict[str, Any]:
    n_seeds = len(budget["meta_seeds"])
    train = len(ARM_IDS) * n_seeds * int(budget["outer_steps"])
    evaluation = len(ARM_IDS) * n_seeds * int(eval_tasks) * len(budget["k_values"]) * int(budget["draws"])
    return {
        "train_expected": train,
        "eval_expected": evaluation,
        "total_expected": train + evaluation,
    }


def build_run_config(
    *,
    prereg: Mapping[str, Any],
    run_id: str,
    run_mode: str,
    budget: Mapping[str, Any],
    task_set: S2TaskSet,
    bank_manifest: Mapping[str, Any],
    bank_sha256: str,
    fd_payload: Mapping[str, Any],
    record_counts: Mapping[str, int],
    eval_task_count: int,
) -> dict[str, Any]:
    """构建确定性 run_config（不含墙钟/环境/created_utc；两次独立进程须逐字节一致）。"""
    expected = _expected_record_counts(budget, eval_task_count)
    boundary = dict(prereg["data_boundary"])
    boundary["holdout_metrics_read"] = False
    fd_summary = summarize_fd_gate(fd_payload)
    fd_summary["override"] = bool(budget.get("smoke"))
    fd_summary["pilot_artifacts"] = json.loads(json.dumps(prereg["fd_gate"]["pilot_artifacts"]))
    config: dict[str, Any] = {
        "schema_version": S2_RUN_CONFIG_SCHEMA_VERSION,
        "run_id": run_id,
        "run_mode": run_mode,
        "prereg_id": str(prereg["prereg_id"]),
        "prereg_digest": str(prereg["prereg_digest"]),
        "analysis_plan_digest": str(prereg["analysis_plan_digest"]),
        "code_sha": str(prereg["code_sha"]),
        "frozen_package": json.loads(json.dumps(prereg["frozen_package"])),
        "data_boundary": boundary,
        "arms": json.loads(json.dumps(prereg["arms"])),
        "training_budget": {
            "meta_seeds": [int(value) for value in budget["meta_seeds"]],
            "outer_steps": int(budget["outer_steps"]),
            "train_records_expected": int(expected["train_expected"]),
        },
        "evaluation_grid": {
            "meta_validation_tasks": int(eval_task_count),
            "K": [int(value) for value in budget["k_values"]],
            "draws": int(budget["draws"]),
            "eval_records_expected": int(expected["eval_expected"]),
        },
        "episode_bank": {
            "sha256": str(bank_sha256),
            "episodes": len(bank_manifest["episodes"]),
            "meta_seeds": [int(value) for value in bank_manifest["meta_seeds"]],
            "outer_steps": int(bank_manifest["outer_steps"]),
            "batch_size": int(bank_manifest["batch_size"]),
            "support_size": int(bank_manifest["support_size"]),
            "query_size": int(bank_manifest["query_size"]),
        },
        "fd_gate": fd_summary,
        "determinism": json.loads(json.dumps(prereg["determinism"])),
        "record_counts": {
            "train": int(record_counts.get("train", 0)),
            "eval": int(record_counts.get("eval", 0)),
            "total": int(record_counts.get("total", 0)),
            **expected,
        },
        "record_schemas": {
            "train": list(TRAIN_RECORD_FIELDS),
            "eval": list(EVAL_RECORD_FIELDS),
        },
        "resource_limits": {str(key): int(value) for key, value in budget["resource_limits"].items()},
        "physical_call_count": 0,
        "evidence_scope": str(prereg["statistical_plan"]["evidence_scope"]),
        "development_set": "meta_validation",
        "scope_notes": {
            "objective_source": "SyntheticTask.truth(designs)['objective']（解析合成评价器，零物理）",
            "lifting_surfaces_only": "NOT_APPLICABLE（S2 无 VLM/CFD 气动求解）",
            "holdout_metrics_read": False,
            "physical_call_count": 0,
        },
    }
    if budget.get("smoke"):
        config["smoke_overrides"] = {
            "outer_steps": int(budget["outer_steps"]),
            "meta_seeds": [int(value) for value in budget["meta_seeds"]],
            "K": [int(value) for value in budget["k_values"]],
            "draws": int(budget["draws"]),
            "eval_tasks": int(eval_task_count),
            "batch_size": int(budget["batch_size"]),
            "support_size": int(budget["support_size"]),
            "query_size": int(budget["query_size"]),
            "eval_query_size": int(budget["eval_query_size"]),
            "fd_coordinates": int(budget["fd_coordinates"]),
        }
    return config


# -- §7 preflight -------------------------------------------------------------

def preflight(
    *,
    prereg_path: Path | str,
    repo_root: Path | str | None = None,
    run_mode: str = "FORMAL",
    smoke_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """正式 run 启动前门禁：prereg 核验 + 数据边界 + bank sha + FD gate，全部 fail-closed。"""
    root = sp.DEFAULT_REPO_ROOT if repo_root is None else Path(repo_root)
    prereg = sp.read_preregistration(prereg_path)
    sp.verify_preregistration(prereg, repo_root=root)
    _require(run_mode in RUN_MODES, S2_RUNNER_VALIDATION_ERROR, f"未知 run_mode {run_mode!r}")
    budget = resolve_budget(prereg, run_mode=run_mode, smoke_overrides=smoke_overrides)
    _require(
        dict(budget["resource_limits"]) == dict(RUN_RESOURCE_LIMITS),
        S2_RUNNER_PREREG_ERROR,
        "run 资源上限与 runner 常量不一致",
    )
    package_path = root / str(prereg["frozen_package"]["package_path"])
    task_set = load_s2_tasks(package_path, expected_boundary=prereg["data_boundary"])
    eval_tasks = list(task_set.meta_validation)
    if budget["eval_task_limit"] is not None:
        _require(
            int(budget["eval_task_limit"]) <= len(eval_tasks),
            S2_RUNNER_VALIDATION_ERROR,
            "SMOKE eval_tasks 超过 meta_validation 任务数",
        )
        eval_tasks = eval_tasks[: int(budget["eval_task_limit"])]
    bank_manifest = build_train_episode_bank(
        task_set.meta_train,
        meta_seeds=budget["meta_seeds"],
        outer_steps=budget["outer_steps"],
        batch_size=budget["batch_size"],
        support_size=budget["support_size"],
        query_size=budget["query_size"],
    )
    bank_sha256 = episode_bank_sha256(bank_manifest)
    prereg_bank_sha = str(prereg["episode_contract"]["train_episode_bank_sha256"])
    if run_mode == "FORMAL":
        _require(
            bank_sha256 == prereg_bank_sha,
            S2_RUNNER_PREREG_ERROR,
            f"训练 episode bank sha 与 prereg 不一致: bank {bank_sha256} prereg {prereg_bank_sha}",
        )
    configs: dict[str, maml.MAMLConfig] = {}
    arms = json.loads(json.dumps(prereg["arms"]))
    for arm in arms:
        configs[str(arm["id"])] = config_from_arm(arm)
    full_config = configs["FULL_MAML"]
    fomaml_config = configs["FOMAML"]
    _require(
        full_config == replace(fomaml_config, first_order=False),
        S2_RUNNER_VALIDATION_ERROR,
        "两臂 config 除 first_order 外不一致",
    )
    fd_payload = run_fd_gate(
        task_set.meta_train,
        config=full_config,
        meta_seed=int(budget["meta_seeds"][0]),
        outer_step=0,
        batch_size=int(budget["batch_size"]),
        support_size=int(budget["support_size"]),
        query_size=int(budget["query_size"]),
        max_coordinates=int(budget["fd_coordinates"]),
        tolerance=float(prereg["fd_gate"]["max_relative_error"]),
    )
    if not budget.get("smoke"):
        _require(
            int(fd_payload["result"]["n_checked"]) == int(prereg["fd_gate"]["coordinates"]),
            S2_RUNNER_VALIDATION_ERROR,
            "FORMAL FD 坐标数必须等于 prereg 的 32",
        )
    return {
        "repo_root": root,
        "prereg": prereg,
        "prereg_path": Path(prereg_path),
        "run_mode": run_mode,
        "budget": budget,
        "task_set": task_set,
        "eval_tasks": eval_tasks,
        "bank_manifest": bank_manifest,
        "bank_sha256": bank_sha256,
        "bank_sha256_matches_prereg": bank_sha256 == prereg_bank_sha,
        "arms": arms,
        "configs": configs,
        "fd_payload": fd_payload,
    }


# -- §5/§6 run 执行 ------------------------------------------------------------

_REQUIRED_ARTIFACTS = (
    "run_config.json",
    "run_records.jsonl",
    "run_summary.json",
    "fd_gate.json",
    "data_manifest.json",
)


def _aggregate_arm_resources(per_seed_resources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """v1.5 §12 fig8 数据源：resources.per_arm 的实测聚合（train wall 秒 + 峰值内存）。"""
    per_arm: dict[str, dict[str, Any]] = {}
    for arm_id in ARM_IDS:
        entries = [item for item in per_seed_resources if str(item.get("arm")) == arm_id]
        walls = {str(int(item["meta_seed"])): float(item["training_wall_s"]) for item in entries}
        peaks = [
            float(item["peak_memory_mb"])
            for item in entries
            if _is_number(item.get("peak_memory_mb"))
        ]
        per_arm[arm_id] = {
            "meta_seeds": [int(item["meta_seed"]) for item in entries],
            "train_wall_seconds_per_meta_seed": dict(sorted(walls.items())),
            "train_wall_seconds_mean": (sum(walls.values()) / len(walls)) if walls else None,
            "peak_memory_mb_max": (max(peaks) if peaks else None),
        }
    full_mean = per_arm.get("FULL_MAML", {}).get("train_wall_seconds_mean")
    fomaml_mean = per_arm.get("FOMAML", {}).get("train_wall_seconds_mean")
    ratio = None
    if _is_number(full_mean) and _is_number(fomaml_mean) and float(fomaml_mean) > 0:
        ratio = float(full_mean) / float(fomaml_mean)
    return {"per_arm": per_arm, "train_wall_seconds_ratio": ratio}


def _status_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """v1.6 共享接口 schema v2：train/eval 两桶恒含 OK/FAILED 两键（缺失补 0）。"""
    counts: dict[str, dict[str, int]] = {
        split: {status: 0 for status in sp.RECORD_STATUS_COUNTS} for split in ("train", "eval")
    }
    for record in records:
        bucket = counts[str(record.get("record_type"))]
        status = str(record.get("status"))
        bucket[status] = bucket.get(status, 0) + 1
    return counts


def run_experiment(
    *,
    out_dir: Path | str,
    run_id: str,
    prereg_path: Path | str,
    repo_root: Path | str | None = None,
    run_mode: str = "FORMAL",
    smoke_overrides: Mapping[str, Any] | None = None,
    created_utc: str | None = None,
) -> dict[str, Any]:
    """执行一次 S2 run（零物理）；资源停止/总截止 fail-closed 并落部分产物。"""
    _require(bool(str(run_id)), S2_RUNNER_VALIDATION_ERROR, "run_id 不得为空")
    target = Path(out_dir)
    if target.exists() and any((target / name).exists() for name in _REQUIRED_ARTIFACTS):
        raise S2RunnerError(f"{S2_RUNNER_STATE_ERROR}: 输出目录已含 run 产物，拒绝覆盖: {target}")
    target.mkdir(parents=True, exist_ok=True)
    # 确定性：单线程 torch（跨进程逐字节一致）
    if maml.torch is not None:
        maml.torch.set_num_threads(1)
    maml._TORCH_NUM_THREADS = 1

    pre = preflight(
        prereg_path=prereg_path,
        repo_root=repo_root,
        run_mode=run_mode,
        smoke_overrides=smoke_overrides,
    )
    prereg = pre["prereg"]
    budget = pre["budget"]
    task_set = pre["task_set"]
    eval_tasks = pre["eval_tasks"]
    bank_manifest = pre["bank_manifest"]
    bank_sha256 = pre["bank_sha256"]

    outer_step_timing: list[dict[str, Any]] = []
    for arm in pre["arms"]:
        timing = measure_outer_step_timing(
            task_set,
            arm=arm,
            meta_seed=int(budget["meta_seeds"][0]),
            outer_step=0,
            batch_size=int(budget["batch_size"]),
            support_size=int(budget["support_size"]),
            query_size=int(budget["query_size"]),
        )
        outer_step_timing.append(timing)

    train_records: list[dict[str, Any]] = []
    eval_records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    per_seed_resources: list[dict[str, Any]] = []
    stop_run: str | None = None
    stop_detail: dict[str, Any] | None = None
    run_started = time.perf_counter()

    for arm in pre["arms"]:
        arm_id = str(arm["id"])
        config = pre["configs"][arm_id]
        for meta_seed in budget["meta_seeds"]:
            if stop_run is not None:
                break
            result = train_arm(
                arm_id=arm_id,
                run_id=str(run_id),
                task_set=task_set,
                config=config,
                meta_seed=int(meta_seed),
                outer_steps=int(budget["outer_steps"]),
                batch_size=int(budget["batch_size"]),
                support_size=int(budget["support_size"]),
                query_size=int(budget["query_size"]),
                seed_wall_limit_s=float(budget["resource_limits"]["per_seed_train_wall_s"]),
                memory_limit_mb=float(budget["resource_limits"]["peak_memory_mb"]),
                run_started=run_started,
                hard_deadline_s=float(budget["resource_limits"]["total_wall_s"]),
            )
            train_records.extend(result["records"])
            per_seed_resources.append(
                {
                    "arm": arm_id,
                    "meta_seed": int(meta_seed),
                    "status": str(result["status"]),
                    "training_wall_s": float(result["training_wall_s"]),
                    "peak_memory_mb": result["peak_memory_mb"],
                }
            )
            if result["status"] in ("RESOURCE_LIMIT", "DEADLINE_EXCEEDED"):
                stop_run = str(result["status"])
                stop_detail = {
                    "arm": arm_id,
                    "meta_seed": int(meta_seed),
                    "status": stop_run,
                    "failure": result["failure"],
                    "resource_limits": {str(key): int(value) for key, value in budget["resource_limits"].items()},
                }
                break
            if result["status"] == "FAILED":
                failures.append(
                    {"arm": arm_id, "meta_seed": int(meta_seed), "stage": "train", "failure": result["failure"]}
                )
                continue
            seed_task_set = S2TaskSet(
                meta_train=task_set.meta_train,
                meta_validation=tuple(eval_tasks),
                split_counts=task_set.split_counts,
                meta_train_task_ids_sha256=task_set.meta_train_task_ids_sha256,
                meta_validation_task_ids_sha256=task_set.meta_validation_task_ids_sha256,
                holdout_task_ids_sha256=task_set.holdout_task_ids_sha256,
                frozen_package=task_set.frozen_package,
            )
            eval_records.extend(
                evaluate_arm(
                    arm_id=arm_id,
                    run_id=str(run_id),
                    task_set=seed_task_set,
                    parameters=result["parameters"],
                    config=config,
                    meta_seed=int(meta_seed),
                    k_values=budget["k_values"],
                    draws=int(budget["draws"]),
                    query_size=int(budget["eval_query_size"]),
                )
            )
        if stop_run is not None:
            break

    all_records = list(train_records) + list(eval_records)
    if stop_run is not None:
        status = stop_run
    elif failures or any(record["status"] == "FAILED" for record in all_records):
        status = "PARTIAL"
    else:
        status = "COMPLETED"

    record_counts = {
        "train": len(train_records),
        "eval": len(eval_records),
        "total": len(all_records),
    }
    run_config = build_run_config(
        prereg=prereg,
        run_id=str(run_id),
        run_mode=run_mode,
        budget=budget,
        task_set=task_set,
        bank_manifest=bank_manifest,
        bank_sha256=bank_sha256,
        fd_payload=pre["fd_payload"],
        record_counts=record_counts,
        eval_task_count=len(eval_tasks),
    )
    run_config_sha256 = write_json_canonical(target / "run_config.json", run_config)
    run_records_sha256 = write_jsonl(target / "run_records.jsonl", all_records)
    fd_gate_sha256 = write_json_canonical(target / "fd_gate.json", pre["fd_payload"])
    holdout_ids: list[str] = []
    for split in sp.FORBIDDEN_SPLITS:
        holdout_ids.extend(task_set.frozen_package["task_ids"][split])
    data_manifest = {
        "schema_version": "p4ra-s2-data-manifest-v1",
        "frozen_package": {
            "run_id": str(prereg["frozen_package"]["run_id"]),
            "package_path": str(prereg["frozen_package"]["package_path"]),
            "sha256sums_sha256": str(prereg["frozen_package"]["sha256sums_sha256"]),
            "code_sha": str(prereg["frozen_package"]["code_sha"]),
            "git_sha": str(prereg["frozen_package"]["git_sha"]),
        },
        "split_counts": dict(task_set.split_counts),
        "meta_train_task_ids": [task.task_id for task in task_set.meta_train],
        "meta_validation_task_ids": [task.task_id for task in eval_tasks],
        "holdout_task_ids_sha256": sp.ids_sha256(holdout_ids),
        "holdout_rows_used": 0,
        "holdout_metrics_read": False,
        "episode_bank_sha256": bank_sha256,
        "physical_call_count": 0,
    }
    data_manifest_sha256 = write_json_canonical(target / "data_manifest.json", data_manifest)

    arm_resources = _aggregate_arm_resources(per_seed_resources)
    per_arm_seed: dict[str, list[int]] = {}
    for item in per_seed_resources:
        seeds = per_arm_seed.setdefault(str(item["arm"]), [])
        meta_seed_value = int(item["meta_seed"])
        if meta_seed_value not in seeds:
            seeds.append(meta_seed_value)
    for seeds in per_arm_seed.values():
        seeds.sort()
    created = (
        datetime.now(timezone.utc).isoformat(timespec="seconds") if created_utc is None else str(created_utc)
    )
    summary = {
        "schema_version": S2_RUN_SUMMARY_SCHEMA_VERSION,
        "run_id": str(run_id),
        "run_mode": run_mode,
        "status": status,
        "created_utc": created,
        "prereg_id": str(prereg["prereg_id"]),
        "prereg_digest": str(prereg["prereg_digest"]),
        "code_sha": str(prereg["code_sha"]),
        "record_counts": record_counts,
        "status_counts": _status_counts(all_records),
        "failures": failures,
        "resource_stop": stop_detail,
        "episode_bank_sha256": bank_sha256,
        "run_config_sha256": run_config_sha256,
        "run_records_sha256": run_records_sha256,
        "run_records_core_sha256": records_core_sha256(all_records),
        "fd_gate_sha256": fd_gate_sha256,
        "data_manifest_sha256": data_manifest_sha256,
        "outer_step_timing": outer_step_timing,
        "per_arm_seed": per_arm_seed,
        "fd_pilot_artifacts": json.loads(json.dumps(run_config["fd_gate"]["pilot_artifacts"])),
        "scope_notes": json.loads(json.dumps(run_config["scope_notes"])),
        "resources": {
            "per_seed": per_seed_resources,
            "per_arm": arm_resources["per_arm"],
            "train_wall_seconds_ratio": arm_resources["train_wall_seconds_ratio"],
            "run_wall_s": time.perf_counter() - run_started,
            "resource_limits": {str(key): int(value) for key, value in budget["resource_limits"].items()},
            "auxiliary_compute": {
                "outer_step_timing_measurements": len(outer_step_timing),
                "physical_call_count": 0,
                "note": "每 arm 训练前 1 outer-step 实测（measure_outer_step_timing），仅资源预估，非物理计算，不计入训练预算",
            },
        },
        "resource_limits": {str(key): int(value) for key, value in budget["resource_limits"].items()},
        "torch_threads": 1,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "torch": getattr(maml.torch, "__version__", "absent") if maml.torch is not None else "absent",
        },
        "physical_call_count": 0,
        "evidence_scope": str(prereg["statistical_plan"]["evidence_scope"]),
        "development_set": "meta_validation",
        "smoke": bool(budget.get("smoke")),
    }
    write_json_canonical(target / "run_summary.json", summary)
    return summary


# -- §12 产物校验 --------------------------------------------------------------

def _read_json(path: Path) -> Any:
    _require(path.is_file(), S2_RUNNER_VALIDATION_ERROR, f"缺少产物 {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    _require(path.is_file(), S2_RUNNER_VALIDATION_ERROR, f"缺少产物 {path.name}")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise S2RunnerError(f"{S2_RUNNER_VALIDATION_ERROR}: run_records 第 {number} 行非法 JSON: {exc}") from exc
        _require(isinstance(row, dict), S2_RUNNER_VALIDATION_ERROR, f"run_records 第 {number} 行不是对象")
        rows.append(row)
    return rows


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def per_arm_seed_from_summary(summary: Mapping[str, Any]) -> dict[str, list[int]]:
    """从 resources.per_seed 机械重建 per_arm_seed（v1.6 校验用）。"""
    per_arm_seed: dict[str, list[int]] = {}
    resources = summary.get("resources") if isinstance(summary.get("resources"), Mapping) else {}
    for item in resources.get("per_seed") or []:
        if not isinstance(item, Mapping):
            continue
        seeds = per_arm_seed.setdefault(str(item.get("arm")), [])
        seed_value = int(item.get("meta_seed"))
        if seed_value not in seeds:
            seeds.append(seed_value)
    for seeds in per_arm_seed.values():
        seeds.sort()
    return per_arm_seed


def validate_run_artifacts(
    run_dir: Path | str,
    *,
    prereg: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """只读校验一次 run 的产物完整性与合同一致性；返回逐项 checks。"""
    root = Path(run_dir)
    checks: list[dict[str, Any]] = []

    def check(name: str, condition: bool, detail: Any = None) -> None:
        checks.append({"name": name, "ok": bool(condition), "detail": detail})

    missing = [name for name in _REQUIRED_ARTIFACTS if not (root / name).is_file()]
    check("required_artifacts", not missing, {"missing": missing})
    if missing:
        return {"ok": False, "checks": checks, "run_status": None}
    config = _read_json(root / "run_config.json")
    summary = _read_json(root / "run_summary.json")
    fd_gate = _read_json(root / "fd_gate.json")
    manifest = _read_json(root / "data_manifest.json")
    records = _read_jsonl(root / "run_records.jsonl")

    check("run_config_schema", config.get("schema_version") == S2_RUN_CONFIG_SCHEMA_VERSION, config.get("schema_version"))
    check("run_summary_schema", summary.get("schema_version") == S2_RUN_SUMMARY_SCHEMA_VERSION, summary.get("schema_version"))
    config_expected_keys = set(sp.RUN_CONFIG_REQUIRED_FIELDS) | (
        set(sp.RUN_CONFIG_OPTIONAL_FIELDS) if "smoke_overrides" in config else set()
    )
    check(
        "run_config_fields",
        set(config) == config_expected_keys,
        {
            "missing": sorted(config_expected_keys - set(config)),
            "extra": sorted(set(config) - config_expected_keys),
        },
    )
    check(
        "run_summary_fields",
        set(summary) == set(sp.RUN_SUMMARY_REQUIRED_FIELDS),
        {
            "missing": sorted(set(sp.RUN_SUMMARY_REQUIRED_FIELDS) - set(summary)),
            "extra": sorted(set(summary) - set(sp.RUN_SUMMARY_REQUIRED_FIELDS)),
        },
    )
    summary_resources = summary.get("resources") if isinstance(summary.get("resources"), Mapping) else {}
    check(
        "run_summary_resources_fields",
        set(summary_resources) == set(sp.RUN_SUMMARY_RESOURCES_FIELDS),
        {"keys": sorted(summary_resources)},
    )
    status_counts = summary.get("status_counts") if isinstance(summary.get("status_counts"), Mapping) else {}
    check(
        "status_counts_ok_failed",
        set(status_counts) == {"train", "eval"}
        and all(
            isinstance(status_counts.get(split_name), Mapping)
            and set(status_counts[split_name]) == set(sp.RECORD_STATUS_COUNTS)
            for split_name in ("train", "eval")
        ),
        status_counts,
    )
    check(
        "summary_fields_v2",
        summary.get("per_arm_seed") == per_arm_seed_from_summary(summary)
        and summary.get("fd_pilot_artifacts") == config.get("fd_gate", {}).get("pilot_artifacts")
        and summary.get("scope_notes") == config.get("scope_notes"),
        {
            "per_arm_seed": summary.get("per_arm_seed"),
            "fd_pilot_artifacts": summary.get("fd_pilot_artifacts"),
        },
    )
    check("physical_call_count_zero", config.get("physical_call_count") == 0 and summary.get("physical_call_count") == 0)
    check(
        "resource_limits_fixed",
        config.get("resource_limits") == RUN_RESOURCE_LIMITS and summary.get("resource_limits") == RUN_RESOURCE_LIMITS,
        {"config": config.get("resource_limits"), "summary": summary.get("resource_limits")},
    )
    boundary = config.get("data_boundary") or {}
    check(
        "data_boundary_holdout_untouched",
        boundary.get("holdout_rows_used") == 0
        and boundary.get("holdout_metrics_read") is False
        and manifest.get("holdout_rows_used") == 0
        and manifest.get("holdout_metrics_read") is False,
    )

    if prereg is not None:
        check("prereg_id_match", config.get("prereg_id") == prereg.get("prereg_id"))
        check("prereg_digest_match", config.get("prereg_digest") == prereg.get("prereg_digest"))
        check("code_sha_match", config.get("code_sha") == prereg.get("code_sha"))
        expected_bank_sha = (prereg.get("episode_contract") or {}).get("train_episode_bank_sha256")
        if config.get("run_mode") == "FORMAL":
            check(
                "episode_bank_sha_match",
                config.get("episode_bank", {}).get("sha256") == expected_bank_sha,
            )
        else:
            check("episode_bank_sha_match", True, "SMOKE: bank sha 只做 config/summary 自洽校验")

    fd_result = fd_gate.get("result") or {}
    check("fd_gate_pass", fd_result.get("status") == "PASS", fd_result.get("status"))
    check("fd_gate_mode_full", fd_gate.get("mode") == "full")
    check(
        "fd_gate_tolerance",
        _is_number(fd_result.get("max_relative_error")) and float(fd_result["max_relative_error"]) <= 1e-6,
        fd_result.get("max_relative_error"),
    )
    is_formal = config.get("run_mode") == "FORMAL"
    fd_coordinates = int(fd_result.get("n_checked") or 0)
    check("fd_gate_coordinates", (fd_coordinates == 32) if is_formal else (fd_coordinates >= 1), fd_coordinates)

    budget = config.get("training_budget") or {}
    grid = config.get("evaluation_grid") or {}
    arms = [str(arm.get("id")) for arm in config.get("arms") or []]
    meta_seeds = [int(value) for value in budget.get("meta_seeds") or []]
    outer_steps = int(budget.get("outer_steps") or 0)
    k_values = [int(value) for value in grid.get("K") or []]
    draws = int(grid.get("draws") or 0)
    eval_task_ids = list(manifest.get("meta_validation_task_ids") or [])
    check("arms_exactly_two", sorted(arms) == sorted(ARM_IDS), arms)
    check(
        "record_counts_match",
        config.get("record_counts", {}).get("train") == len([r for r in records if r.get("record_type") == "train"])
        and config.get("record_counts", {}).get("eval") == len([r for r in records if r.get("record_type") == "eval"])
        and config.get("record_counts", {}).get("total") == len(records),
    )
    expected_train = len(arms) * len(meta_seeds) * outer_steps
    expected_eval = len(arms) * len(meta_seeds) * len(eval_task_ids) * len(k_values) * draws
    check(
        "record_counts_expected",
        config.get("record_counts", {}).get("train") == expected_train
        and config.get("record_counts", {}).get("eval") == expected_eval
        and config.get("record_counts", {}).get("total") == expected_train + expected_eval,
        {"config": config.get("record_counts"), "expected": {"train": expected_train, "eval": expected_eval}},
    )

    bad_fields: list[Any] = []
    bad_values: list[Any] = []
    seen_train: set[tuple[str, int, int]] = set()
    seen_eval: set[tuple[str, int, str, int, int]] = set()
    for index, record in enumerate(records):
        record_type = record.get("record_type")
        if record_type == "train":
            if set(record.keys()) != set(TRAIN_RECORD_FIELDS):
                bad_fields.append({"index": index, "type": "train", "keys": sorted(record.keys())})
                continue
            key = (str(record["arm"]), int(record["meta_seed"]), int(record["outer_step"]))
            if key in seen_train:
                bad_values.append({"index": index, "duplicate": key})
            seen_train.add(key)
            if record["arm"] not in arms or int(record["meta_seed"]) not in meta_seeds or not (
                0 <= int(record["outer_step"]) < outer_steps
            ):
                bad_values.append({"index": index, "domain": key})
            if record["status"] not in TRAIN_STATUSES:
                bad_values.append({"index": index, "status": record["status"]})
            if record["status"] == "OK":
                metrics = ("train_loss", "grad_norm", "inner_loss_first", "inner_loss_last")
                if not all(_is_number(record[name]) for name in metrics):
                    bad_values.append({"index": index, "nonfinite": True})
                if not (_is_number(record["wall_s"]) and float(record["wall_s"]) >= 0):
                    bad_values.append({"index": index, "wall_s": record["wall_s"]})
                if not (_is_number(record["peak_memory_mb"]) and float(record["peak_memory_mb"]) > 0):
                    bad_values.append({"index": index, "peak_memory_mb": record["peak_memory_mb"]})
            else:
                metrics = ("train_loss", "grad_norm", "inner_loss_first", "inner_loss_last")
                if any(record[name] is not None for name in metrics):
                    bad_values.append({"index": index, "failed_metrics_not_null": True})
        elif record_type == "eval":
            if set(record.keys()) != set(EVAL_RECORD_FIELDS):
                bad_fields.append({"index": index, "type": "eval", "keys": sorted(record.keys())})
                continue
            key = (
                str(record["arm"]),
                int(record["meta_seed"]),
                str(record["task_id"]),
                int(record["K"]),
                int(record["draw"]),
            )
            if key in seen_eval:
                bad_values.append({"index": index, "duplicate": key})
            seen_eval.add(key)
            if (
                record["arm"] not in arms
                or int(record["meta_seed"]) not in meta_seeds
                or record["task_id"] not in eval_task_ids
                or int(record["K"]) not in k_values
                or not (0 <= int(record["draw"]) < draws)
                or record["split"] != META_VALIDATION_SPLIT
            ):
                bad_values.append({"index": index, "domain": key})
            if int(record["support_size"]) != int(record["K"]) or int(record["adaptation_inner_steps"]) != int(record["K"]):
                bad_values.append({"index": index, "K_mismatch": key})
            if int(record["query_size"]) < 1:
                bad_values.append({"index": index, "query_size": record["query_size"]})
            if record["status"] not in EVAL_STATUSES:
                bad_values.append({"index": index, "status": record["status"]})
            metrics = ("query_rmse_raw", "query_rmse_standardized", "query_mae_raw")
            if record["status"] == "OK":
                if not (_is_number(record["query_rmse_raw"]) and float(record["query_rmse_raw"]) >= 0):
                    bad_values.append({"index": index, "rmse": record["query_rmse_raw"]})
                if not (_is_number(record["query_mae_raw"]) and float(record["query_mae_raw"]) >= 0):
                    bad_values.append({"index": index, "mae": record["query_mae_raw"]})
                standardized = record["query_rmse_standardized"]
                if standardized is not None:
                    if int(record["K"]) < 2 or not _is_number(standardized) or float(standardized) < 0:
                        bad_values.append({"index": index, "standardized": standardized})
            else:
                if any(record[name] is not None for name in metrics):
                    bad_values.append({"index": index, "failed_metrics_not_null": True})
        else:
            bad_fields.append({"index": index, "type": record_type})
    check("record_fields", not bad_fields, bad_fields[:5])
    check("record_values", not bad_values, bad_values[:5])

    completed = summary.get("status") == "COMPLETED"
    if completed:
        check("coverage_train_complete", len(seen_train) == expected_train, [len(seen_train), expected_train])
        check("coverage_eval_complete", len(seen_eval) == expected_eval, [len(seen_eval), expected_eval])
    else:
        check("coverage_train_no_duplicates", len(seen_train) == len([r for r in records if r.get("record_type") == "train"]))
        check("coverage_eval_no_duplicates", len(seen_eval) == len([r for r in records if r.get("record_type") == "eval"]))

    raw_config_sha = hashlib.sha256((root / "run_config.json").read_bytes()).hexdigest()
    raw_records_sha = hashlib.sha256((root / "run_records.jsonl").read_bytes()).hexdigest()
    fd_file_sha = hashlib.sha256((root / "fd_gate.json").read_bytes()).hexdigest()
    manifest_sha = hashlib.sha256((root / "data_manifest.json").read_bytes()).hexdigest()
    check("summary_run_config_sha", raw_config_sha == summary.get("run_config_sha256"))
    check("summary_run_records_sha", raw_records_sha == summary.get("run_records_sha256"))
    check("summary_run_records_core_sha", records_core_sha256(records) == summary.get("run_records_core_sha256"))
    check("summary_fd_gate_sha", fd_file_sha == summary.get("fd_gate_sha256"))
    check("summary_data_manifest_sha", manifest_sha == summary.get("data_manifest_sha256"))
    check("summary_episode_bank_sha", summary.get("episode_bank_sha256") == config.get("episode_bank", {}).get("sha256"))
    check("fd_gate_sha256_present", bool(config.get("fd_gate", {}).get("fd_gate_sha256")))
    return {
        "ok": all(entry["ok"] for entry in checks),
        "checks": checks,
        "record_counts": {"train": len([r for r in records if r.get("record_type") == "train"]), "eval": len([r for r in records if r.get("record_type") == "eval"])},
        "run_status": summary.get("status"),
    }


def compare_deterministic_runs(run_dir_a: Path | str, run_dir_b: Path | str) -> dict[str, Any]:
    """比较两次独立进程 run 的确定性产物（run_config 字节、bank sha、records core）。"""
    first = Path(run_dir_a)
    second = Path(run_dir_b)
    config_a = _read_json(first / "run_config.json")
    config_b = _read_json(second / "run_config.json")
    records_a = _read_jsonl(first / "run_records.jsonl")
    records_b = _read_jsonl(second / "run_records.jsonl")
    core_a = [record_core(record) for record in records_a]
    core_b = [record_core(record) for record in records_b]
    result = {
        "run_config_byte_identical": (first / "run_config.json").read_bytes() == (second / "run_config.json").read_bytes(),
        "episode_bank_sha256_equal": config_a.get("episode_bank", {}).get("sha256")
        == config_b.get("episode_bank", {}).get("sha256"),
        "fd_gate_sha256_equal": config_a.get("fd_gate", {}).get("fd_gate_sha256")
        == config_b.get("fd_gate", {}).get("fd_gate_sha256"),
        "run_records_core_equal": core_a == core_b,
        "run_records_core_sha256_equal": records_core_sha256(records_a) == records_core_sha256(records_b),
        "record_counts_equal": config_a.get("record_counts") == config_b.get("record_counts"),
    }
    result["ok"] = all(value for key, value in result.items() if key != "ok")
    return result


# -- CLI ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="s2_runner", description="S2 零物理 runner（A1）")
    sub = parser.add_subparsers(dest="command", required=True)
    bank = sub.add_parser("bank-sha", help="计算训练 episode bank sha（不跑训练）")
    bank.add_argument("--repo-root", default=None)
    bank.add_argument("--package", default=sp.DEFAULT_PACKAGE_PATH)
    bank.add_argument("--meta-seeds", required=True, help="逗号分隔，如 0,1,2")
    bank.add_argument("--outer-steps", type=int, required=True)
    bank.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)

    build = sub.add_parser("build-prereg", help="构建并落盘 prereg")
    build.add_argument("--repo-root", default=None)
    build.add_argument("--out", required=True)
    build.add_argument("--bank-sha", required=True)
    build.add_argument("--created-utc", default=None)

    pre = sub.add_parser("preflight", help="执行正式 run 前门禁")
    pre.add_argument("--repo-root", default=None)
    pre.add_argument("--prereg", required=True)
    pre.add_argument("--run-mode", default="FORMAL", choices=RUN_MODES)

    run = sub.add_parser("run", help="执行一次 run（默认 SMOKE 需显式覆盖预算）")
    run.add_argument("--repo-root", default=None)
    run.add_argument("--prereg", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--run-mode", default="FORMAL", choices=RUN_MODES)
    run.add_argument("--smoke-overrides", default=None, help="JSON 字符串")
    run.add_argument("--created-utc", default=None)

    validate = sub.add_parser("validate", help="只读校验 run 产物")
    validate.add_argument("--run-dir", required=True)

    compare = sub.add_parser("compare", help="比较两次独立 run 的确定性产物")
    compare.add_argument("--dir-a", required=True)
    compare.add_argument("--dir-b", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "bank-sha":
            root = sp.DEFAULT_REPO_ROOT if args.repo_root is None else Path(args.repo_root)
            package = root / str(args.package)
            task_set = load_s2_tasks(package)
            manifest = build_train_episode_bank(
                task_set.meta_train,
                meta_seeds=[int(value) for value in str(args.meta_seeds).split(",") if value.strip()],
                outer_steps=int(args.outer_steps),
                batch_size=int(args.batch_size),
            )
            print(json.dumps({"episode_bank_sha256": episode_bank_sha256(manifest), "episodes": len(manifest["episodes"])}, ensure_ascii=False))
            return 0
        if args.command == "build-prereg":
            prereg = sp.build_preregistration(
                repo_root=None if args.repo_root is None else Path(args.repo_root),
                created_utc=args.created_utc,
                train_episode_bank_sha256=str(args.bank_sha),
            )
            target = sp.write_preregistration(prereg, args.out)
            print(json.dumps({"path": str(target), "prereg_id": prereg["prereg_id"], "prereg_digest": prereg["prereg_digest"]}, ensure_ascii=False))
            return 0
        if args.command == "preflight":
            pre = preflight(
                prereg_path=args.prereg,
                repo_root=None if args.repo_root is None else Path(args.repo_root),
                run_mode=args.run_mode,
            )
            print(json.dumps({"ok": True, "episode_bank_sha256": pre["bank_sha256"], "run_mode": pre["run_mode"]}, ensure_ascii=False))
            return 0
        if args.command == "run":
            overrides = json.loads(args.smoke_overrides) if args.smoke_overrides else None
            summary = run_experiment(
                out_dir=args.out,
                run_id=args.run_id,
                prereg_path=args.prereg,
                repo_root=None if args.repo_root is None else Path(args.repo_root),
                run_mode=args.run_mode,
                smoke_overrides=overrides,
                created_utc=args.created_utc,
            )
            print(json.dumps({"ok": True, "status": summary["status"], "record_counts": summary["record_counts"]}, ensure_ascii=False))
            return 0
        if args.command == "validate":
            result = validate_run_artifacts(args.run_dir)
            print(json.dumps({"ok": result["ok"], "run_status": result["run_status"]}, ensure_ascii=False))
            return 0 if result["ok"] else 1
        if args.command == "compare":
            result = compare_deterministic_runs(args.dir_a, args.dir_b)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0 if result["ok"] else 1
    except (S2RunnerError, sp.S2PreregError, TaskFamilyError) as exc:
        print(f"S2_RUNNER_CLI_ERROR: {exc}", file=sys.stderr)
        return 2
    parser.error(f"未知命令 {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())