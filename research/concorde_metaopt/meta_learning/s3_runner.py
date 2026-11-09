
"""S3 正式运行器（runner）：数据边界、episode bank、模型训练、评估 campaign、门禁与产物校验。

本模块是计划 v1.2b/v1.3 §2/§4 的执行层实现，所有 schema 常量与哈希算法从
s3_prereg.py 单源导入（禁止复制字面量）。边界：physical_call_count=0，不启动
任何真实求解器/子进程/网络；不读取 references_sealed 封存参考（读了即
S3_LEAKAGE_SEALED_REFERENCE_READ）；训练只读 meta_train，SMOKE/DEV 评估只读
meta_validation，FORMAL 评估才进入 meta_test/meta_test_ood/meta_test_negative_control。

并行合同（R-S3-05）：每个 run 的随机流完全由 (arm, task, budget, opt_seed,
meta_seed) 派生，worker 编号不进入任何 RNG/记录；shard 映射固定；合并顺序按
规范 run_key 排序；W=1 与串行逐位等价。
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import hashlib
import json
import math
import multiprocessing
import os
import platform
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

# 线程固定（R-S3-05 / Lead m07082）：主进程与 worker 都在导入 numpy 前固定 BLAS/OMP 单线程
for _thread_env_name in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[_thread_env_name] = "1"
del _thread_env_name

import numpy as np

from . import m5_arms
from . import maml
from . import s3_prereg as sp
from . import task_family as tf

# ---------------------------------------------------------------------------
# 运行器常量（s3_prereg 单源；仅本模块私有的执行常量在此定义）
# ---------------------------------------------------------------------------
S3_RUNNER_SCHEMA_VERSION = "p4ra-s3-runner-v1"
S3_EXECUTION_REPORT_SCHEMA_VERSION = "p4ra-s3-execution-report-v2"
# 执行报告 18 字段（R-S3-05 + A5 M0R3 B01 单源；顺序固定，禁止改名/增删）
S3_EXECUTION_REPORT_FIELDS = (
    "schema_version",
    "campaign_id",
    "run_mode",
    "created_utc",
    "parallel_workers",
    "execution_rule",
    "shard_runs_sha256",
    "per_shard_counts",
    "run_count_requested",
    "run_count_completed",
    "campaign_wall_s",
    "sum_run_wall_seconds",
    "max_run_wall_s",
    "max_peak_memory_mb",
    "sum_run_wall_limit_s",
    "stop_reason",
    "physical_call_count",
    "parallel_note",
)
S3_THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
S3_RUNNER_RECORD_SCHEMA_VERSION = sp.S3_RECORD_SCHEMA_VERSION
S3_RUNNER_GATE_FILE = "fd_or_gradient_gate.json"
S3_RUNNER_RECORD_FILE = "run_records.jsonl"
S3_RUNNER_CONFIG_FILE = "run_config.json"
S3_RUNNER_SUMMARY_FILE = "run_summary.json"
S3_RUNNER_MODEL_MANIFEST_FILE = "model_manifest.json"
S3_RUNNER_DATA_MANIFEST_FILE = "data_manifest.json"
S3_RUNNER_EXECUTION_REPORT_FILE = "execution_report.json"
S3_RUNNER_NC_RECORDS_FILE = "negative_control_records.jsonl"
S3_RUNNER_NC_SUMMARY_FILE = "negative_control_summary.json"
S3_RUNNER_OOD_RECORDS_FILE = "ood_records.jsonl"
S3_RUNNER_DET_DIR = "determinism"
S3_RUNNER_DET_CHECK_FILE = "determinism_check.json"
S3_RUNNER_MODELS_DIR = "models"
S3_RUNNER_REQUIRED_ARTIFACTS = (
    S3_RUNNER_CONFIG_FILE,
    S3_RUNNER_SUMMARY_FILE,
    S3_RUNNER_RECORD_FILE,
    S3_RUNNER_MODEL_MANIFEST_FILE,
    S3_RUNNER_DATA_MANIFEST_FILE,
    S3_RUNNER_GATE_FILE,
    S3_RUNNER_EXECUTION_REPORT_FILE,
)
S3_RUNNER_EXECUTION_MODES = ("FORMAL", "SMOKE")
S3_W8_PILOT_GATE_SCHEMA_VERSION = sp.S3_W8_PILOT_GATE_SCHEMA_VERSION
S3_W8_PILOT_GATE_RELPATH = sp.S3_W8_PILOT_GATE_RELPATH
S3_RUNNER_DEFAULT_WORKERS = 1
S3_RUNNER_MAX_WORKERS = 32
S3_TRAIN_OUTER_STEPS = 200
S3_TRAIN_EPISODES_PER_STEP = 8
S3_TRAIN_TOTAL_EPISODES = 1600
S3_SMOKE_OUTER_STEPS = 2
S3_SMOKE_EPISODES = 16
S3_ADAM_BETA1 = 0.9
S3_ADAM_BETA2 = 0.999
S3_ADAM_EPSILON = 1e-8
S3_TRAIN_RECORD_EXCLUDED_FIELDS = ("wall_s", "peak_memory_mb", "record_digest")
S3_EVAL_RECORD_EXCLUDED_FIELDS = ("wall_s", "peak_memory_mb", "record_digest")
S3_GATE_COORDINATES_REQUESTED = sp.S3_FD_MAX_COORDINATES
S3_GATE_EPSILON_POLICY = "1e-6 * max(1, |theta_j|)"
S3_TRAIN_RULE = (
    "内循环 SGD lr=inner_lr 5 步 MSE(3 输出)；外循环 Adam lr=outer_lr；"
    "ANIL 内循环仅更新输出层 head，body 逐位冻结；元梯度由 maml.meta_train_step 计算后转换为 Adam 更新"
)

# 错误码（fail-closed）
S3_RUNNER_ERROR = "S3_RUNNER_ERROR"
S3_RUNNER_PREREG_ERROR = "S3_RUNNER_PREREG_ERROR"
S3_RUNNER_DATA_BOUNDARY_ERROR = "S3_RUNNER_DATA_BOUNDARY_ERROR"
S3_RUNNER_BANK_ERROR = "S3_RUNNER_BANK_ERROR"
S3_RUNNER_MODEL_ERROR = "S3_RUNNER_MODEL_ERROR"
S3_RUNNER_RECORD_ERROR = "S3_RUNNER_RECORD_ERROR"
S3_RUNNER_RESOURCE_ERROR = "S3_RUNNER_RESOURCE_ERROR"
S3_RUNNER_GATE_ERROR = "S3_RUNNER_GATE_ERROR"
# R-S3-07（Lead m07285 Q3）：FORMAL 只加载 M2 冻结产物；缺失/sha 不符即 fail-closed
S3_RUNNER_FROZEN_ARTIFACT_MISMATCH = "S3_RUNNER_FROZEN_ARTIFACT_MISMATCH"
S3_RUNNER_VALIDATION_ERROR = "S3_RUNNER_VALIDATION_ERROR"
S3_RUNNER_FAMILY_ERROR = "S3_RUNNER_FAMILY_ERROR"
S3_RUNNER_FILE_ERROR = "S3_RUNNER_FILE_ERROR"
S3_RUNNER_BUDGET_MISMATCH = "FAILED_BUDGET_MISMATCH"
S3_RUNNER_RESOURCE_LIMIT = "RESOURCE_LIMIT"
S3_RUNNER_DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
S3_RUNNER_SUM_RUN_WALL_LIMIT = "S3_SUM_RUN_WALL_LIMIT"
S3_LEAKAGE_SEALED_REFERENCE_READ = "S3_LEAKAGE_SEALED_REFERENCE_READ"
S3_RUNNER_TAMPER_DETECTED = "S3_GATE_TAMPER_DETECTED"
S3_RUNNER_STATUSES = (
    "COMPLETED",
    "PARTIAL",
    "FAILED",
    "RESOURCE_LIMIT",
    "DEADLINE_EXCEEDED",
)

# B01（M2R）：FORMAL campaign 一次性书面授权字段
S3_RUNNER_CAMPAIGN_AUTH_ERROR = "S3_RUNNER_CAMPAIGN_AUTH_ERROR"
CAMPAIGN_AUTHORIZATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
CAMPAIGN_AUTHORIZATION_UTC_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

# M02（M2R）：3780 runs 外推权威口径 = bench_v13a + bench_v13a_run2（R-S3-05B）
S3_W8_BENCH_RELPATHS = (
    "research/concorde_metaopt/evidence/s3/bench/bench_v13a.json",
    "research/concorde_metaopt/evidence/s3/bench/bench_v13a_run2.json",
)
S3_W8_BENCH_FILE_SHA256 = {
    "research/concorde_metaopt/evidence/s3/bench/bench_v13a.json":
        "16fbb1f587a2b4d7ae0ce1650fa57c3043cd586fc95b96cceae57901aa553d16",
    "research/concorde_metaopt/evidence/s3/bench/bench_v13a_run2.json":
        "004bbe644f6e2f7c8a1e1350d265fa78d99c29d7f787ea7deb11ccbd3382a331",
}
S3_W8_TARGET_RUNS = 3780
S3_W8_PROJECTED_3780_WALL_S = 5509.562
S3_W8_PROJECTED_3780_THROUGHPUT_S = 3712.731
S3_W8_HARD_CAP_S = 7200
S3_W8_SECOND_CAMPAIGN_WALL_DELTA_LIMIT_PCT = 20.0
S3_W8_ACCEPTANCE_RULING = "R-S3-05B"
S3_W8_ACCEPTANCE_RULING_SHA256 = "e72f1ec90c7ef9f6c0ef8c2625c75aee345871856e0b380671b9a777601dd23f"
S3_W8_ACCEPTANCE_UPPER_BOUND_S = 5509.562
S3_W8_ACCEPTANCE_WITHIN_5400 = False


class S3RunnerError(RuntimeError):
    """S3 runner 错误（fail-closed，带机器可读错误码）。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        self.message = str(message)
        super().__init__(self.code + ": " + self.message)


def _require(condition: Any, code: str, message: str) -> None:
    if not condition:
        raise S3RunnerError(code, message)


def _is_sha256_hex(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def validate_campaign_authorization(
    run_mode: str, campaign_authorization: Any
) -> dict[str, str] | None:
    """B01：校验 FORMAL campaign 一次性授权（id/utc）；SMOKE 允许 None。"""
    if campaign_authorization is None:
        _require(
            run_mode != "FORMAL",
            S3_RUNNER_CAMPAIGN_AUTH_ERROR,
            "FORMAL run 必须提供 campaign_authorization（id/utc）",
        )
        return None
    _require(
        isinstance(campaign_authorization, Mapping),
        S3_RUNNER_CAMPAIGN_AUTH_ERROR,
        "campaign_authorization 必须是 mapping",
    )
    _require(
        set(campaign_authorization) == {"campaign_authorization_id", "campaign_authorization_utc"},
        S3_RUNNER_CAMPAIGN_AUTH_ERROR,
        "campaign_authorization 键集必须恰为 id/utc",
    )
    auth_id = campaign_authorization.get("campaign_authorization_id")
    auth_utc = campaign_authorization.get("campaign_authorization_utc")
    _require(
        isinstance(auth_id, str)
        and bool(auth_id.strip())
        and bool(CAMPAIGN_AUTHORIZATION_ID_PATTERN.fullmatch(auth_id)),
        S3_RUNNER_CAMPAIGN_AUTH_ERROR,
        "campaign_authorization_id 非法",
    )
    _require(
        isinstance(auth_utc, str) and bool(CAMPAIGN_AUTHORIZATION_UTC_PATTERN.fullmatch(auth_utc)),
        S3_RUNNER_CAMPAIGN_AUTH_ERROR,
        "campaign_authorization_utc 非法",
    )
    return {"campaign_authorization_id": auth_id, "campaign_authorization_utc": auth_utc}


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
def utc_now() -> str:
    """返回秒级 ISO8601 UTC 时间戳（+00:00）。"""
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def _round6(value: float) -> float:
    if not math.isfinite(float(value)):
        raise S3RunnerError(S3_RUNNER_RECORD_ERROR, "记录值必须有限: " + repr(value))
    return float(round(float(value), 6))


# threadpoolctl 限流控制器必须保持存活，否则 GC 会恢复原 BLAS 线程数
_THREADPOOL_CONTROLLER: Any = None


def set_thread_environment() -> None:
    """固定 BLAS/OMP 单线程（主进程与 worker 均调用；R-S3-05 / Lead m07082）。

    除设置环境变量外，若 threadpoolctl 可用则强制所有已加载的 BLAS 线程池为 1
    （保证 numpy 在该进程内更早被导入时，W=1 与 worker 仍得到逐位一致的数值结果）。
    """
    global _THREADPOOL_CONTROLLER
    for name in S3_THREAD_ENV_VARS:
        os.environ[name] = "1"
    try:
        import threadpoolctl  # type: ignore

        _THREADPOOL_CONTROLLER = threadpoolctl.threadpool_limits(limits=1)
    except Exception:
        pass
    try:  # worker 不训练模型；若 torch 已可用则同时固定其线程数
        import torch  # type: ignore

        torch.set_num_threads(1)
    except Exception:
        pass


def _safe_relpath(path: str | Path, root: str | Path) -> tuple[Path, str]:
    target = Path(path).resolve()
    base = Path(root).resolve()
    try:
        rel = target.relative_to(base)
    except ValueError as exc:
        raise S3RunnerError(S3_RUNNER_ERROR, "路径越界: " + str(path)) from exc
    return target, rel.as_posix()


def write_json_canonical(path: str | Path, payload: Any) -> dict[str, Any]:
    """以 canonical JSON + LF 写盘，返回 path/bytes/sha256（原始字节 sha）。"""
    target = Path(path)
    data = sp.canonical_json(payload).encode("utf-8") + b"\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "path": str(target),
        "bytes": len(data),
        "sha256": sp.sha256_bytes(data),
    }


def read_json_file(path: str | Path) -> Any:
    target = Path(path)
    _require(target.is_file(), S3_RUNNER_ERROR, "文件不存在: " + str(target))
    try:
        return json.loads(target.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise S3RunnerError(S3_RUNNER_ERROR, "不是合法 UTF-8 JSON: " + str(target)) from exc


def write_jsonl(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    target = Path(path)
    lines = [sp.canonical_json(row) for row in rows]
    data = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "path": str(target),
        "bytes": len(data),
        "sha256": sp.sha256_bytes(data),
        "rows": len(rows),
    }


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    _require(target.is_file(), S3_RUNNER_ERROR, "文件不存在: " + str(target))
    text = target.read_bytes().decode("utf-8")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            raise S3RunnerError(
                S3_RUNNER_RECORD_ERROR,
                "jsonl 出现空行: " + str(target) + " line " + str(line_no),
            )
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise S3RunnerError(
                S3_RUNNER_RECORD_ERROR,
                "jsonl 行不是合法 JSON: " + str(target) + " line " + str(line_no),
            ) from exc
        _require(isinstance(row, dict), S3_RUNNER_RECORD_ERROR, "jsonl 行必须是对象")
        rows.append(row)
    return rows


def array_sha256(array: Any) -> str:
    """float64 小端连续字节的 sha256（设计/数组指纹）。"""
    matrix = np.ascontiguousarray(np.asarray(array, dtype="<f8"))
    return sp.sha256_bytes(matrix.tobytes())


def designs_sha256(designs: Any) -> str:
    return array_sha256(designs)


def _windows_peak_memory_bytes() -> int:
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
    for dll_name, function_name in (
        ("psapi", "GetProcessMemoryInfo"),
        ("kernel32", "K32GetProcessMemoryInfo"),
    ):
        try:
            library = ctypes.WinDLL(dll_name)
            function = getattr(library, function_name)
        except (OSError, AttributeError) as exc:  # pragma: no cover - 平台差异
            last_error = dll_name + "." + function_name + ": " + str(exc)
            continue
        function.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        function.restype = wintypes.BOOL
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        ok = function(process, ctypes.byref(counters), counters.cb)
        if ok:
            return int(counters.PeakWorkingSetSize)
        last_error = dll_name + "." + function_name + " 返回 0"
    raise OSError(last_error)


def peak_memory_mb() -> float:
    """本进程峰值常驻内存（MB）实测；失败抛错，不以 0/null 冒充。"""
    if os.name == "nt":
        try:
            peak_bytes = _windows_peak_memory_bytes()
        except OSError as exc:  # pragma: no cover - 平台相关
            raise S3RunnerError(S3_RUNNER_RESOURCE_ERROR, "无法实测峰值内存: " + str(exc)) from exc
    else:  # pragma: no cover - 非 Windows 回退
        try:
            import resource  # type: ignore

            usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            peak_bytes = usage if sys.platform == "darwin" else usage * 1024
        except Exception as exc:
            raise S3RunnerError(
                S3_RUNNER_RESOURCE_ERROR, "当前平台无法读取峰值内存: " + str(exc)
            ) from exc
    value = float(peak_bytes) / (1024.0 * 1024.0)
    _require(math.isfinite(value) and value > 0.0, S3_RUNNER_RESOURCE_ERROR, "峰值内存实测值非法: " + repr(value))
    return value


def _record_core(record: Mapping[str, Any], excluded: Sequence[str]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in set(excluded)}


def eval_record_digest(record: Mapping[str, Any]) -> str:
    return sp.canonical_sha256(_record_core(record, S3_EVAL_RECORD_EXCLUDED_FIELDS))


def train_record_digest(record: Mapping[str, Any]) -> str:
    return sp.canonical_sha256(_record_core(record, S3_TRAIN_RECORD_EXCLUDED_FIELDS))


def task_ids_sha256_for(ids: Iterable[str]) -> str:
    return sp.task_ids_sha256(sorted(str(item) for item in ids))


# ---------------------------------------------------------------------------
# 族冻结包：读取并重建 S3ConflictTask（只读；不读 holdout truth）
# ---------------------------------------------------------------------------
def load_family_package(path: str | Path) -> dict[str, Any]:
    """读取族冻结包并重建 120 个 S3ConflictTask（不评估任何 truth）。"""
    target = Path(path)
    data = target.read_bytes()
    payload = read_json_file(target)
    _require(isinstance(payload, Mapping), S3_RUNNER_FAMILY_ERROR, "族包必须是 mapping")
    _require(
        payload.get("schema_version") == sp.S3_FAMILY_PACKAGE_SCHEMA_VERSION,
        S3_RUNNER_FAMILY_ERROR,
        "族包 schema 不符",
    )
    _require(payload.get("family_id") == sp.S3_FAMILY_ID, S3_RUNNER_FAMILY_ERROR, "族包 family_id 不符")
    _require(
        payload.get("formula_version") == sp.S3_FORMULA_VERSION,
        S3_RUNNER_FAMILY_ERROR,
        "族包 formula_version 不符",
    )
    _require(payload.get("family_seed") == sp.S3_FAMILY_SEED, S3_RUNNER_FAMILY_ERROR, "族包 family_seed 不符")
    _require(payload.get("holdout_seed") == sp.S3_HOLDOUT_SEED, S3_RUNNER_FAMILY_ERROR, "族包 holdout_seed 不符")
    _require(payload.get("physical_call_count") == 0, S3_RUNNER_FAMILY_ERROR, "族包 physical_call_count 必须为 0")
    _require(
        dict(payload.get("split_counts") or {}) == dict(sp.S3_SPLIT_COUNTS),
        S3_RUNNER_FAMILY_ERROR,
        "族包 split_counts 不符",
    )
    records = payload.get("tasks")
    _require(isinstance(records, list), S3_RUNNER_FAMILY_ERROR, "族包 tasks 必须是 list")
    tasks: list[tf.S3ConflictTask] = []
    by_split: dict[str, list[tf.S3ConflictTask]] = {split: [] for split in sp.S3_SPLIT_COUNTS}
    seen: set[str] = set()
    for record in records:
        _require(isinstance(record, Mapping), S3_RUNNER_FAMILY_ERROR, "族包任务记录必须是 mapping")
        task = tf.S3ConflictTask(
            task_id=str(record["task_id"]),
            split=str(record.get("split")),
            family=str(record.get("family")),
            formula_version=str(record.get("formula_version")),
            params=dict(record.get("params") or {}),
            seed=int(record.get("seed")),
            context=dict(record.get("context") or {}),
            reference_kind=str(record.get("reference_kind")),
            source_task_id=record.get("source_task_id"),
        )
        _require(task.task_id not in seen, S3_RUNNER_FAMILY_ERROR, "族包 task_id 重复: " + task.task_id)
        seen.add(task.task_id)
        expected_fp = record.get("task_fingerprint")
        _require(
            task.task_fingerprint() == expected_fp,
            S3_RUNNER_FAMILY_ERROR,
            "族包 task_fingerprint 复算不一致: " + task.task_id,
        )
        _require(
            task.split in by_split,
            S3_RUNNER_FAMILY_ERROR,
            "族包未知 split: " + str(task.split),
        )
        by_split[task.split].append(task)
        tasks.append(task)
    for split, count in sp.S3_SPLIT_COUNTS.items():
        _require(
            len(by_split[split]) == count,
            S3_RUNNER_FAMILY_ERROR,
            "族包 split 计数不符 " + split + ": " + str(len(by_split[split])),
        )
    task_ids = sorted(task.task_id for task in tasks)
    return {
        "path": str(target),
        "sha256": sp.sha256_bytes(data),
        "bytes": len(data),
        "payload": dict(payload),
        "tasks": tasks,
        "by_split": by_split,
        "task_ids_sha256": sp.task_ids_sha256(task_ids),
    }


def family_design_cache(tasks: Sequence[tf.S3ConflictTask]) -> dict[str, dict[str, np.ndarray]]:
    """一次性计算每个任务的 support(128)/query(64) 设计池，供 bank/评估复用。"""
    cache: dict[str, dict[str, np.ndarray]] = {}
    for task in tasks:
        cache[task.task_id] = {
            "support": np.asarray(task.support_designs(), dtype=np.float64),
            "query": np.asarray(task.query_designs(), dtype=np.float64),
        }
    return cache


def task_labels(task: tf.S3ConflictTask, designs: Any) -> dict[str, np.ndarray]:
    """解析真值：返回 objective/g1/g2/feasibility（纯解析，physical=0）。"""
    truth = task.truth(np.asarray(designs, dtype=np.float64))
    return {
        "objective": np.asarray(truth["objective"], dtype=np.float64),
        "g1": np.asarray(truth["g1"], dtype=np.float64),
        "g2": np.asarray(truth["g2"], dtype=np.float64),
        "feasibility": np.asarray(truth["feasibility"], dtype=bool),
    }


def _episode_targets(labels: Mapping[str, np.ndarray]) -> np.ndarray:
    return np.column_stack(
        [
            np.asarray(labels["objective"], dtype=np.float64),
            np.asarray(labels["g1"], dtype=np.float64),
            np.asarray(labels["g2"], dtype=np.float64),
        ]
    )


# ---------------------------------------------------------------------------
# Episode bank（计划 §4.1）：3 个 meta_seed 各 1600 条（SMOKE 16 条）
# ---------------------------------------------------------------------------
def _bank_task_index(meta_seed: int, outer_step: int, slot: int, attempt: int, count: int) -> int:
    text = (
        str(sp.S3_FAMILY_SEED)
        + "|"
        + str(int(meta_seed))
        + "|task|"
        + str(int(outer_step))
        + "|"
        + str(int(slot))
        + "|"
        + str(int(attempt))
    )
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % int(count)


def _support_index_seed(meta_seed: int, outer_step: int, slot: int) -> int:
    text = (
        str(sp.S3_FAMILY_SEED)
        + "|"
        + str(int(meta_seed))
        + "|support|"
        + str(int(outer_step))
        + "|"
        + str(int(slot))
    )
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**31)


def build_episode_bank(
    meta_train_tasks: Sequence[tf.S3ConflictTask],
    meta_seed: int,
    outer_steps: int,
    *,
    design_cache: Mapping[str, Mapping[str, np.ndarray]] | None = None,
) -> list[dict[str, Any]]:
    """构建单个 meta_seed 的 episode bank（确定性；仅设计索引，不含标签）。"""
    _require(
        len(meta_train_tasks) in (int(sp.S3_SPLIT_COUNTS["meta_train"]), int(SMOKE_TRAIN_TASK_COUNT)),
        S3_RUNNER_BANK_ERROR,
        "meta_train 任务数必须为 60（FORMAL）或 4（SMOKE）",
    )
    _require(int(meta_seed) in sp.S3_MODEL_META_SEEDS, S3_RUNNER_BANK_ERROR, "meta_seed 必须是 0/1/2")
    _require(1 <= int(outer_steps) <= 200, S3_RUNNER_BANK_ERROR, "outer_steps 必须 1..200")
    cache = design_cache if design_cache is not None else family_design_cache(meta_train_tasks)
    count = len(meta_train_tasks)
    episodes: list[dict[str, Any]] = []
    for step in range(int(outer_steps)):
        used: set[int] = set()
        require_distinct = count >= S3_TRAIN_EPISODES_PER_STEP
        for slot in range(8):
            task_index = 0
            found = False
            for attempt in range(100):
                candidate = _bank_task_index(meta_seed, step, slot, attempt, count)
                if not require_distinct:
                    task_index = candidate
                    used.add(candidate)
                    found = True
                    break
                if candidate not in used:
                    task_index = candidate
                    used.add(candidate)
                    found = True
                    break
            _require(found, S3_RUNNER_BANK_ERROR, "episode bank 任务抽样 100 次仍重复")
            task = meta_train_tasks[task_index]
            k_train = 5 if ((step * 8 + slot) % 2 == 0) else 10
            rng = np.random.default_rng(_support_index_seed(meta_seed, step, slot))
            support_indices = [int(index) for index in rng.permutation(sp.S3_SUPPORT_POOL_SIZE)[:k_train]]
            query_indices = [int(index) for index in range(sp.S3_QUERY_SIZE)]
            designs = cache[task.task_id]
            support_designs = designs["support"][np.asarray(support_indices, dtype=np.int64)]
            query_designs = designs["query"][np.asarray(query_indices, dtype=np.int64)]
            episode = {
                "schema_version": sp.S3_EPISODE_BANK_SCHEMA_VERSION,
                "meta_seed": int(meta_seed),
                "outer_step": int(step),
                "slot": int(slot),
                "task_split": "meta_train",
                "task_id": task.task_id,
                "task_index": int(task_index),
                "K_train": int(k_train),
                "support_indices": support_indices,
                "query_indices": query_indices,
                "support_designs_sha256": designs_sha256(support_designs),
                "query_designs_sha256": designs_sha256(query_designs),
            }
            episode["episode_digest"] = sp.episode_digest(episode)
            episodes.append(episode)
    _require(
        len(episodes) == int(outer_steps) * 8,
        S3_RUNNER_BANK_ERROR,
        "episode bank 条数不符",
    )
    return episodes


def write_episode_bank(path: str | Path, episodes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    info = write_jsonl(path, episodes)
    return {
        "path": str(path),
        "bytes": info["bytes"],
        "sha256": info["sha256"],
        "episodes": info["rows"],
    }


def read_episode_bank(path: str | Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    seen: set[tuple[int, int]] = set()
    for row in rows:
        _require(
            row.get("schema_version") == sp.S3_EPISODE_BANK_SCHEMA_VERSION,
            S3_RUNNER_BANK_ERROR,
            "episode 行 schema 不符: " + str(path),
        )
        _require(row.get("task_split") == "meta_train", S3_RUNNER_BANK_ERROR, "episode 行 task_split 必须是 meta_train")
        key = (int(row.get("outer_step")), int(row.get("slot")))
        _require(key not in seen, S3_RUNNER_BANK_ERROR, "episode bank (outer_step, slot) 重复")
        seen.add(key)
        _require(
            row.get("episode_digest") == sp.episode_digest(row),
            S3_RUNNER_BANK_ERROR,
            "episode_digest 复算不一致: " + str(path),
        )
    return rows


def build_task_episode(
    task: tf.S3ConflictTask,
    support_indices: Sequence[int],
    query_indices: Sequence[int],
    design_cache: Mapping[str, Mapping[str, np.ndarray]],
) -> maml.TaskEpisode:
    designs = design_cache[task.task_id]
    support_x = np.asarray(designs["support"], dtype=np.float64)[np.asarray(support_indices, dtype=np.int64)]
    query_x = np.asarray(designs["query"], dtype=np.float64)[np.asarray(query_indices, dtype=np.int64)]
    support_labels = task_labels(task, support_x)
    query_labels = task_labels(task, query_x)
    return maml.TaskEpisode(
        support_features=support_x,
        support_targets=_episode_targets(support_labels),
        query_features=query_x,
        query_targets=_episode_targets(query_labels),
        task_id=task.task_id,
    )


# ---------------------------------------------------------------------------
# 模型：配置 / 训练（FOMAML + ANIL）/ 确定性序列化 / 读取
# ---------------------------------------------------------------------------
def model_config(kind: str, meta_seed: int) -> maml.MAMLConfig:
    _require(kind in sp.S3_MODEL_KINDS, S3_RUNNER_MODEL_ERROR, "模型 kind 必须是 fomaml/anil")
    template = dict(sp.S3_MODEL_CONFIG_TEMPLATE)
    return maml.MAMLConfig(
        input_dim=int(template["input_dim"]),
        output_dim=int(template["output_dim"]),
        hidden_sizes=tuple(int(item) for item in template["hidden_sizes"]),
        inner_lr=float(template["inner_lr"]),
        inner_steps=int(template["inner_steps"]),
        outer_lr=float(template["outer_lr"]),
        tasks_per_batch=int(template["tasks_per_batch"]),
        first_order=bool(template["first_order"]),
        seed=int(meta_seed),
        backend=str(template["backend"]),
        head_only=(kind == "anil"),
    )


def model_config_dict(kind: str, meta_seed: int) -> dict[str, Any]:
    config = model_config(kind, meta_seed)
    return {
        "input_dim": int(config.input_dim),
        "output_dim": int(config.output_dim),
        "hidden_sizes": [int(item) for item in config.hidden_sizes],
        "inner_lr": float(config.inner_lr),
        "inner_steps": int(config.inner_steps),
        "outer_lr": float(config.outer_lr),
        "tasks_per_batch": int(config.tasks_per_batch),
        "first_order": bool(config.first_order),
        "seed": int(config.seed),
        "backend": str(config.backend),
        "head_only": bool(config.head_only),
    }


def model_file_payload(
    kind: str,
    meta_seed: int,
    parameters: maml.ParameterSet,
    *,
    episode_bank_sha256: str,
    final_train_loss: float,
) -> dict[str, Any]:
    """确定性模型文件（无时间戳/墙钟；重训练应逐字节可复现）。"""
    _require(len(episode_bank_sha256) == 64, S3_RUNNER_MODEL_ERROR, "episode_bank_sha256 必须是 64 hex")
    parameter_set = parameters.to_dict()
    return {
        "schema_version": sp.S3_MODEL_FILE_SCHEMA_VERSION,
        "arm_type": kind,
        "meta_seed": int(meta_seed),
        "config": model_config_dict(kind, meta_seed),
        "parameters": [
            {"name": name, "tensor": tensor}
            for name, tensor in zip(parameter_set["names"], parameter_set["tensors"])
        ],
        "episode_bank_sha256": str(episode_bank_sha256),
        "final_train_loss": float(final_train_loss),
        "training_rule": S3_TRAIN_RULE,
        "physical_call_count": 0,
    }


def load_model_file(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    data = target.read_bytes()
    payload = read_json_file(target)
    _require(isinstance(payload, Mapping), S3_RUNNER_MODEL_ERROR, "模型文件必须是 mapping")
    _require(
        payload.get("schema_version") == sp.S3_MODEL_FILE_SCHEMA_VERSION,
        S3_RUNNER_MODEL_ERROR,
        "模型文件 schema 不符",
    )
    kind = str(payload.get("arm_type"))
    meta_seed = int(payload.get("meta_seed"))
    _require(kind in sp.S3_MODEL_KINDS, S3_RUNNER_MODEL_ERROR, "模型 arm_type 不符")
    _require(meta_seed in sp.S3_MODEL_META_SEEDS, S3_RUNNER_MODEL_ERROR, "模型 meta_seed 不符")
    config = maml.config_from_dict(payload.get("config") or {})
    parameters_payload = payload.get("parameters")
    _require(isinstance(parameters_payload, list), S3_RUNNER_MODEL_ERROR, "模型 parameters 必须是 list")
    tensors = [np.asarray(item["tensor"], dtype=np.float64) for item in parameters_payload]
    parameters = maml.ParameterSet(tensors)
    return {
        "path": str(target),
        "sha256": sp.sha256_bytes(data),
        "payload": dict(payload),
        "config": config,
        "parameters": parameters,
        "kind": kind,
        "meta_seed": meta_seed,
    }


def _adam_update(
    parameters: maml.ParameterSet,
    gradients: Sequence[np.ndarray],
    first_moment: list[np.ndarray],
    second_moment: list[np.ndarray],
    step: int,
) -> maml.ParameterSet:
    beta1, beta2 = S3_ADAM_BETA1, S3_ADAM_BETA2
    corrected1 = 1.0 - beta1 ** step
    corrected2 = 1.0 - beta2 ** step
    new_tensors: list[np.ndarray] = []
    for index, tensor in enumerate(parameters.tensors):
        grad = np.asarray(gradients[index], dtype=np.float64)
        first_moment[index] = beta1 * first_moment[index] + (1.0 - beta1) * grad
        second_moment[index] = beta2 * second_moment[index] + (1.0 - beta2) * (grad * grad)
        m_hat = first_moment[index] / corrected1
        v_hat = second_moment[index] / corrected2
        update = m_hat / (np.sqrt(v_hat) + S3_ADAM_EPSILON)
        new_tensors.append(np.asarray(tensor, dtype=np.float64) - S3_ADAM_LR * update)
    return maml.ParameterSet(new_tensors)


S3_ADAM_LR = 1e-3


def train_model(
    kind: str,
    meta_seed: int,
    tasks_by_id: Mapping[str, tf.S3ConflictTask],
    episodes: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    episode_bank_sha256: str,
    design_cache: Mapping[str, Mapping[str, np.ndarray]],
    train_wall_limit_s: float = 1200.0,
) -> dict[str, Any]:
    """训练单个模型（确定性 FOMAML/ANIL），返回模型载荷、训练记录与资源统计。"""
    _require(len(episodes) % 8 == 0, S3_RUNNER_BANK_ERROR, "episode bank 条数必须是 8 的倍数")
    config = model_config(kind, meta_seed)
    parameters = maml.init_parameters(config)
    first_moment = [np.zeros_like(tensor) for tensor in parameters.tensors]
    second_moment = [np.zeros_like(tensor) for tensor in parameters.tensors]
    records: list[dict[str, Any]] = []
    start = time.perf_counter()
    last_loss = float("nan")
    peak = 0.0
    for step in range(len(episodes) // 8):
        batch_rows = list(episodes[step * 8 : (step + 1) * 8])
        batch = [
            build_task_episode(
                tasks_by_id[str(row["task_id"])],
                row["support_indices"],
                row["query_indices"],
                design_cache,
            )
            for row in batch_rows
        ]
        step_start = time.perf_counter()
        new_parameters, stats = maml.meta_train_step(parameters, batch, config, second_order=False)
        gradients = [
            (np.asarray(old, dtype=np.float64) - np.asarray(new, dtype=np.float64)) / config.outer_lr
            for old, new in zip(parameters.tensors, new_parameters.tensors)
        ]
        parameters = _adam_update(parameters, gradients, first_moment, second_moment, step + 1)
        step_wall = time.perf_counter() - step_start
        last_loss = float(stats["outer_loss"])
        episode_digest_text = "\n".join(str(row["episode_digest"]) for row in batch_rows)
        record: dict[str, Any] = {
            "schema_version": S3_RUNNER_RECORD_SCHEMA_VERSION,
            "run_id": run_id,
            "meta_seed": int(meta_seed),
            "outer_step": int(step),
            "loss": _round6(last_loss),
            "wall_s": _round6(step_wall),
            "train_episode_digest": sp.sha256_text(episode_digest_text),
        }
        record["record_digest"] = train_record_digest(record)
        records.append(record)
        peak = max(peak, peak_memory_mb())
        if (time.perf_counter() - start) > float(train_wall_limit_s):
            raise S3RunnerError(
                S3_RUNNER_RESOURCE_LIMIT,
                "模型训练墙钟超过限制 " + str(train_wall_limit_s) + "s（" + kind + "/" + str(meta_seed) + "）",
            )
    train_wall_s = time.perf_counter() - start
    if not math.isfinite(last_loss):
        raise S3RunnerError(S3_RUNNER_MODEL_ERROR, "训练 loss 非有限")
    payload = model_file_payload(
        kind,
        meta_seed,
        parameters,
        episode_bank_sha256=episode_bank_sha256,
        final_train_loss=last_loss,
    )
    return {
        "kind": kind,
        "meta_seed": int(meta_seed),
        "config": config,
        "config_dict": model_config_dict(kind, meta_seed),
        "parameters": parameters,
        "payload": payload,
        "records": records,
        "train_wall_s": float(train_wall_s),
        "peak_memory_mb": float(peak),
        "final_train_loss": float(last_loss),
        "steps": len(records),
    }



# ---------------------------------------------------------------------------
# 解析评估器（纯合成真值；physical_call_count=0，不启动任何求解器）
# ---------------------------------------------------------------------------
S3_EVAL_PHASE_BY_SPLIT = {
    "meta_validation": "DEV",
    "meta_test": "EVAL",
    "meta_test_ood": "OOD",
    "meta_test_negative_control": "NEGATIVE_CONTROL",
}
S3_HOLDOUT_PHASES = ("EVAL", "OOD", "NEGATIVE_CONTROL")


def eval_phase_for_split(split: str) -> str:
    phase = S3_EVAL_PHASE_BY_SPLIT.get(str(split))
    _require(phase is not None, S3_RUNNER_DATA_BOUNDARY_ERROR, "未知评估 split: " + str(split))
    return phase


def make_evaluator(
    task: tf.S3ConflictTask,
    *,
    phase: str,
) -> Callable[[np.ndarray], Mapping[str, Any]]:
    """构造单任务解析评估器；返回 dict 满足 m5_arms.run_s3_arm evaluator 合同。"""
    _require(phase in ("DEV", "EVAL", "OOD", "NEGATIVE_CONTROL"), S3_RUNNER_DATA_BOUNDARY_ERROR, "未知 phase")
    holdout = phase in S3_HOLDOUT_PHASES

    def evaluate(design: Any) -> Mapping[str, Any]:
        vector = np.asarray(design, dtype=np.float64).reshape(-1)
        _require(vector.shape[0] == tf.DESIGN_DIM, S3_RUNNER_RECORD_ERROR, "设计向量维度必须是 12")
        truth = task.truth(vector.reshape(1, -1))
        feasible = bool(np.asarray(truth["feasibility"], dtype=bool).reshape(-1)[0])
        return {
            "analysis_calls": 1,
            "objective": float(np.asarray(truth["objective"], dtype=np.float64).reshape(-1)[0]),
            "constraints_g_le_zero": {
                "g1": float(np.asarray(truth["g1"], dtype=np.float64).reshape(-1)[0]),
                "g2": float(np.asarray(truth["g2"], dtype=np.float64).reshape(-1)[0]),
            },
            "status": "OK",
            "cache_hit": False,
            "billable": True,
            "design_physical": None,
            "feasible": feasible,
            "valid": True,
            "holdout_truth_read": holdout,
        }

    return evaluate


# ---------------------------------------------------------------------------
# 单个 run（run 级并行的工作单元；不得依赖 worker 编号）
# ---------------------------------------------------------------------------
_WORKER_STATE: dict[str, Any] | None = None


def _worker_init(payload: Mapping[str, Any]) -> None:
    global _WORKER_STATE
    _WORKER_STATE = dict(payload)
    set_thread_environment()


def _worker_entry(spec: Mapping[str, Any]) -> dict[str, Any]:
    _require(_WORKER_STATE is not None, S3_RUNNER_ERROR, "worker 未初始化")
    return execute_run_spec(dict(spec), _WORKER_STATE)


def _run_id_for(spec: Mapping[str, Any], campaign_id: str) -> str:
    return (
        str(campaign_id)
        + "--"
        + str(spec["arm"])
        + "--B"
        + str(int(spec["budget"]))
        + "--T"
        + str(spec["task_id"])
        + "--MS"
        + str(int(spec["meta_seed"]))
        + "--OS"
        + str(int(spec["opt_seed"]))
    )


def _eval_record_from_observation(
    observation: Any,
    *,
    run_id: str,
    arm: str,
    task_id: str,
    split: str,
    budget: int,
    opt_seed: int,
    meta_seed: int,
    phase: str,
) -> dict[str, Any]:
    index = int(observation.eval_index)
    if index <= sp.S3_K_SHOT:
        source = "support"
    elif index <= sp.S3_INITIAL_DESIGN_COUNT:
        source = "initial"
    else:
        source = "bo" if arm in m5_arms.S3_BO_ARM_IDS else "de"
    constraints = observation.constraints or {}
    record: dict[str, Any] = {
        "schema_version": S3_RUNNER_RECORD_SCHEMA_VERSION,
        "run_id": run_id,
        "task_id": str(task_id),
        "split": str(split),
        "arm_id": str(arm),
        "budget": int(budget),
        "opt_seed": int(opt_seed),
        "meta_seed": int(meta_seed),
        "evaluation_index": index,
        "design": [float(value) for value in observation.design_u],
        "f": None if observation.objective is None else float(observation.objective),
        "g1": None if "g1" not in constraints else float(constraints["g1"]),
        "g2": None if "g2" not in constraints else float(constraints["g2"]),
        "feasible": bool(observation.feasible) if observation.feasible is not None else False,
        "source": source,
        "phase": phase,
        "holdout_truth_read": bool(phase in S3_HOLDOUT_PHASES),
        "wall_s": 0.0,
    }
    record["record_digest"] = eval_record_digest(record)
    return record


def execute_run_spec(spec: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    """执行单个 (arm, task, budget, opt_seed, meta_seed) run。随机流完全由 spec 决定。"""
    arm = str(spec["arm"])
    task_id = str(spec["task_id"])
    budget = int(spec["budget"])
    opt_seed = int(spec["opt_seed"])
    meta_seed = int(spec["meta_seed"])
    campaign_id = str(spec.get("campaign_id") or "S3")
    phase = str(spec.get("phase") or eval_phase_for_split(spec.get("split", "")))
    tasks = state["tasks"]
    _require(task_id in tasks, S3_RUNNER_DATA_BOUNDARY_ERROR, "run spec 引用未知 task_id: " + task_id)
    task = tasks[task_id]
    _require(
        task.split == spec.get("split"),
        S3_RUNNER_DATA_BOUNDARY_ERROR,
        "run spec split 与 task.split 不一致: " + task_id,
    )
    models = state["models"]
    model_key = "anil" if arm == m5_arms.S3_BO_ANIL_CON else "fomaml"
    entry = models[(model_key, meta_seed)]
    config = maml.config_from_dict(entry["config"])
    parameters = maml.ParameterSet.from_dict(entry["parameters"])
    scorer = m5_arms.S3ModelScorer(
        parameters,
        config,
        meta_seed=meta_seed,
        model_sha256=str(entry.get("sha256") or ""),
    )
    evaluate = make_evaluator(task, phase=phase)
    run_id = _run_id_for(spec, campaign_id)
    started = time.perf_counter()
    peak_before = peak_memory_mb()
    status = "OK"
    error = None
    try:
        result = m5_arms.run_s3_arm(
            arm,
            evaluate,
            task=task,
            budget=budget,
            opt_seed=opt_seed,
            meta_seed=meta_seed,
            scorer=scorer,
            run_id=run_id,
            reference_objective=None,
        )
        records = [
            _eval_record_from_observation(
                observation,
                run_id=run_id,
                arm=arm,
                task_id=task_id,
                split=str(task.split),
                budget=budget,
                opt_seed=opt_seed,
                meta_seed=meta_seed,
                phase=phase,
            )
            for observation in result.observations
        ]
        from collections import Counter

        source_counts = dict(Counter(record["source"] for record in records))
        _require(
            len(records) == budget,
            S3_RUNNER_BUDGET_MISMATCH,
            "run 记录数 " + str(len(records)) + " != B " + str(budget),
        )
        _require(
            source_counts.get("support", 0) == sp.S3_K_SHOT
            and source_counts.get("initial", 0) == sp.S3_INITIAL_DESIGN_COUNT - sp.S3_K_SHOT,
            S3_RUNNER_BUDGET_MISMATCH,
            "run source 分布不符: " + repr(source_counts),
        )
        provenance = m5_arms.s3_arm_provenance(result)
        wall_s = time.perf_counter() - started
        peak = max(peak_before, peak_memory_mb())
        run_status = {
            "run_id": run_id,
            "arm": arm,
            "task_id": task_id,
            "split": str(task.split),
            "phase": phase,
            "budget": int(budget),
            "opt_seed": int(opt_seed),
            "meta_seed": int(meta_seed),
            "wall_s": _round6(wall_s),
            "peak_memory_mb": _round6(peak),
            "status": status,
            "feasible_count": int(result.feasible_count),
            "best_feasible_value": (
                None if result.best_feasible_value is None else float(result.best_feasible_value)
            ),
            "first_feasible_eval_index": result.first_feasible_eval_index,
            "termination_reason": str(result.termination_reason),
            "n_records": int(len(records)),
            "source_counts": {key: int(value) for key, value in sorted(source_counts.items())},
            "s3_provenance": provenance,
        }
        return {
            "spec": dict(spec),
            "records": records,
            "run": run_status,
            "status": status,
            "error": None,
        }
    except Exception as exc:  # fail-closed：记录失败，不伪造指标
        wall_s = time.perf_counter() - started
        status = "FAILED"
        error = type(exc).__name__ + ": " + str(exc)
        return {
            "spec": dict(spec),
            "records": [],
            "run": {
                "run_id": run_id,
                "arm": arm,
                "task_id": task_id,
                "split": str(spec.get("split")),
                "phase": phase,
                "budget": int(budget),
                "opt_seed": int(opt_seed),
                "meta_seed": int(meta_seed),
                "wall_s": _round6(wall_s),
                "peak_memory_mb": _round6(max(peak_before, peak_memory_mb())),
                "status": status,
                "error": error,
                "n_records": 0,
            },
            "status": status,
            "error": error,
        }


# ---------------------------------------------------------------------------
# 并行执行合同（R-S3-05）：固定 shard 映射 + 规范排序合并
# ---------------------------------------------------------------------------
def canonical_run_key(spec: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "arm": str(spec["arm"]),
        "budget": int(spec["budget"]),
        "meta_seed": int(spec["meta_seed"]),
        "opt_seed": int(spec["opt_seed"]),
        "phase": str(spec.get("phase")),
        "split": str(spec.get("split")),
        "task_id": str(spec["task_id"]),
    }


def run_sort_key(spec: Mapping[str, Any]) -> tuple[str, str, int, int, int, str]:
    return (
        str(spec["arm"]),
        str(spec["task_id"]),
        int(spec["budget"]),
        int(spec["opt_seed"]),
        int(spec["meta_seed"]),
        str(spec.get("phase")),
    )


def run_shard(spec: Mapping[str, Any], workers: int) -> int:
    _require(type(workers) is int and workers >= 1, S3_RUNNER_ERROR, "workers 必须是正整数")
    text = sp.canonical_json(canonical_run_key(spec))
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % int(workers)


def shard_map(specs: Sequence[Mapping[str, Any]], workers: int) -> dict[str, Any]:
    rows = [
        {"spec": canonical_run_key(spec), "shard": run_shard(spec, workers)}
        for spec in specs
    ]
    rows.sort(key=lambda row: (row["shard"], sp.canonical_json(row["spec"])))
    counts = [0] * int(workers)
    for row in rows:
        counts[int(row["shard"])] += 1
    return {
        "workers": int(workers),
        "rule": "shard = int(sha256(canonical(run_key))[:8],16) %% W",
        "runs": rows,
        "runs_sha256": sp.sha256_text("\n".join(sp.canonical_json(row) for row in rows)),
        "per_shard_counts": counts,
        "run_count": len(rows),
    }


def worker_payload_for_state(
    *,
    models: Mapping[tuple[str, int], Mapping[str, Any]],
    tasks: Mapping[str, tf.S3ConflictTask],
    prereg: Mapping[str, Any],
) -> dict[str, Any]:
    payload_models: dict[tuple[str, int], dict[str, Any]] = {}
    for key, entry in models.items():
        payload_models[key] = {
            "config": dict(entry["config"]),
            "parameters": entry["parameters"].to_dict(),
            "sha256": str(entry.get("sha256") or ""),
        }
    return {
        "models": payload_models,
        "tasks": dict(tasks),
        "prereg": dict(prereg),
    }


# ---------------------------------------------------------------------------
# 资源停止判定（单源；计划 L298/L303、R-S3-05A、A5-S3M1-M01/M02、Lead m08211）
# ---------------------------------------------------------------------------
def _mark_resource_limit(result: dict[str, Any], violation: str) -> None:
    """把已完成 run 标记为资源超限停止（只标状态，不改已完成的评估记录）。"""
    result["status"] = S3_RUNNER_RESOURCE_LIMIT
    run = result.get("run")
    if isinstance(run, dict):
        run["status"] = S3_RUNNER_RESOURCE_LIMIT
        run["resource_violation"] = str(violation)


def resource_stop_reason(
    result: Mapping[str, Any],
    *,
    completed_sum_wall_s: float,
    campaign_wall_s: float,
) -> str | None:
    """单一资源停止判定（唯一事实源）：每完成一个 run 立即调用。

    A5-S3M1-M01/M02：per-run wall > per_run_wall_s 或单 run 峰值内存 >
    peak_memory_mb 时先把该 run 置 RESOURCE_LIMIT 并立即停止；随后判定累计
    Σrun wall（> sum_run_wall_limit_s；跨 campaign 累计）与 campaign 墙钟
    （> total_wall_s）。返回 None 表示未超限。
    """
    limits = sp.S3_RESOURCE_LIMITS
    run_entry = result.get("run")
    run = run_entry if isinstance(run_entry, Mapping) else {}
    violation: str | None = None
    wall_s = run.get("wall_s")
    if isinstance(wall_s, (int, float)) and float(wall_s) > float(limits["per_run_wall_s"]):
        violation = "per_run_wall_s"
    else:
        peak_mb = run.get("peak_memory_mb")
        if isinstance(peak_mb, (int, float)) and float(peak_mb) > float(limits["peak_memory_mb"]):
            violation = "peak_memory_mb"
    if violation is not None:
        _mark_resource_limit(result, violation)
        return S3_RUNNER_RESOURCE_LIMIT
    if (
        str(result.get("status")) == S3_RUNNER_RESOURCE_LIMIT
        or str(run.get("status")) == S3_RUNNER_RESOURCE_LIMIT
    ):
        return S3_RUNNER_RESOURCE_LIMIT
    if float(completed_sum_wall_s) > float(limits["sum_run_wall_limit_s"]):
        return S3_RUNNER_SUM_RUN_WALL_LIMIT
    if float(campaign_wall_s) > float(limits["total_wall_s"]):
        return S3_RUNNER_DEADLINE_EXCEEDED
    return None


def execute_campaign(
    specs: Sequence[Mapping[str, Any]],
    *,
    workers: int,
    state: Mapping[str, Any],
    campaign_id: str,
    run_mode: str = "FORMAL",
    prior_sum_run_wall_s: float = 0.0,
    clock: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """按固定排序执行 run 列表；W=1 串行等价，W>1 有界并发逐结果消费。

    A5-S3M1-M01/M02：每个 run 完成即调用 resource_stop_reason（唯一事实源）；超限
    立即停止当前 campaign，不再启动新 run，停止前已完成的结果保留。W>1 使用
    spawn 子进程池 + imap_unordered(chunksize=1)：结果到达即判定，超限 terminate
    未完成任务；无超限时结果按 run_key 规范排序合并，故与 W=1 逐位一致。
    分片（shard_map）是账目口径（execution_report.per_shard_counts /
    shard_runs_sha256），实际执行不按 shard 绑定 worker；worker 编号不进入
    RNG/记录/digest。prior_sum_run_wall_s 用于跨 campaign 累计 Σrun wall 判定。
    """
    _require(type(workers) is int and 1 <= workers <= S3_RUNNER_MAX_WORKERS, S3_RUNNER_ERROR, "workers 越界")
    _require(
        type(prior_sum_run_wall_s) in (int, float) and float(prior_sum_run_wall_s) >= 0.0,
        S3_RUNNER_ERROR,
        "prior_sum_run_wall_s 必须是非负数",
    )
    ordered = sorted((dict(spec, campaign_id=campaign_id) for spec in specs), key=run_sort_key)
    plan = shard_map(ordered, workers)
    set_thread_environment()
    now = clock if clock is not None else time.perf_counter
    campaign_started = now()
    results: list[dict[str, Any]] = []
    stop_reason: str | None = None
    sum_limit_s = float(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"])
    total_limit_s = float(sp.S3_RESOURCE_LIMITS["total_wall_s"])
    completed_sum = [float(prior_sum_run_wall_s)]

    def _accept(result: dict[str, Any]) -> str | None:
        results.append(result)
        wall_s = (result.get("run") or {}).get("wall_s")
        if isinstance(wall_s, (int, float)):
            completed_sum[0] = completed_sum[0] + float(wall_s)
        return resource_stop_reason(
            result,
            completed_sum_wall_s=completed_sum[0],
            campaign_wall_s=now() - campaign_started,
        )

    if workers == 1:
        _worker_init(state)
        try:
            for spec in ordered:
                stop_reason = _accept(_worker_entry(spec))
                if stop_reason is not None:
                    break
        finally:
            global _WORKER_STATE
            _WORKER_STATE = None
    else:
        context = multiprocessing.get_context("spawn")
        with context.Pool(
            processes=int(workers),
            initializer=_worker_init,
            initargs=(dict(state),),
        ) as pool:
            for result in pool.imap_unordered(_worker_entry, ordered, chunksize=1):
                stop_reason = _accept(result)
                if stop_reason is not None:
                    # 立即停止：丢弃排队任务并终止在飞 worker（Pool.__exit__ 再 terminate 为 no-op）
                    pool.terminate()
                    break
    results.sort(key=lambda item: run_sort_key(item["spec"]))
    campaign_wall_s = now() - campaign_started
    wall_values = [
        float(result["run"]["wall_s"])
        for result in results
        if isinstance(result.get("run", {}).get("wall_s"), (int, float))
    ]
    sum_run_wall_s = sum(wall_values)
    if stop_reason is None and sum_run_wall_s > sum_limit_s:
        stop_reason = S3_RUNNER_SUM_RUN_WALL_LIMIT
    if stop_reason is None and campaign_wall_s > total_limit_s:
        stop_reason = S3_RUNNER_DEADLINE_EXCEEDED
    peak_values = [
        float(result["run"]["peak_memory_mb"])
        for result in results
        if isinstance(result.get("run", {}).get("peak_memory_mb"), (int, float))
    ]
    report = {
        "schema_version": S3_EXECUTION_REPORT_SCHEMA_VERSION,
        "campaign_id": campaign_id,
        "run_mode": str(run_mode),
        "created_utc": utc_now(),
        "parallel_workers": int(workers),
        "execution_rule": plan["rule"],
        "shard_runs_sha256": plan["runs_sha256"],
        "per_shard_counts": list(plan["per_shard_counts"]),
        "run_count_requested": len(ordered),
        "run_count_completed": len(results),
        "campaign_wall_s": _round6(campaign_wall_s),
        "sum_run_wall_seconds": _round6(sum_run_wall_s),
        "max_run_wall_s": _round6(max(wall_values) if wall_values else 0.0),
        "max_peak_memory_mb": _round6(max(peak_values) if peak_values else 0.0),
        "sum_run_wall_limit_s": int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]),
        "stop_reason": stop_reason,
        "physical_call_count": 0,
        "parallel_note": (
            "run 级并行仅执行层；分片 shard=sha256(canonical(run_key))%%W 仅用于账目口径"
            "（execution_report.per_shard_counts/shard_runs_sha256），实际执行为有界并发"
            "（W=1 串行；W>1 spawn 池 imap_unordered(chunksize=1) 逐结果消费、超限 terminate），"
            "结果按 run_key 规范排序合并；worker 编号不进入 RNG/记录/digest；"
            "sum_run_wall_seconds=sum(本 campaign 逐 run wall_s)，campaign_wall_s 为墙钟"
        ),
    }
    _require(tuple(report) == S3_EXECUTION_REPORT_FIELDS, S3_RUNNER_VALIDATION_ERROR, "execution_report 字段集/顺序不符")
    return {"results": results, "execution_report": report}


# ---------------------------------------------------------------------------
# 计划网格（run spec 列表）
# ---------------------------------------------------------------------------
def _first_tasks(tasks: Sequence[tf.S3ConflictTask], count: int) -> list[tf.S3ConflictTask]:
    _require(len(tasks) >= count, S3_RUNNER_DATA_BOUNDARY_ERROR, "任务数不足: " + str(len(tasks)))
    return list(tasks[:count])


def build_main_run_specs(
    *,
    tasks: Sequence[tf.S3ConflictTask],
    meta_seeds: Sequence[int],
    opt_seeds: Sequence[int],
    budgets: Sequence[int],
    eval_task_count: int,
) -> list[dict[str, Any]]:
    eval_tasks = _first_tasks(tasks, eval_task_count)
    specs: list[dict[str, Any]] = []
    for arm in sp.S3_ARMS:
        for task in eval_tasks:
            for budget in budgets:
                for meta_seed in meta_seeds:
                    for opt_seed in opt_seeds:
                        specs.append(
                            {
                                "arm": str(arm),
                                "task_id": task.task_id,
                                "split": str(task.split),
                                "budget": int(budget),
                                "opt_seed": int(opt_seed),
                                "meta_seed": int(meta_seed),
                                "phase": eval_phase_for_split(task.split),
                            }
                        )
    return specs


def build_aux_run_specs(
    *,
    tasks: Sequence[tf.S3ConflictTask],
    phase: str,
    budgets: Sequence[int],
    opt_seeds: Sequence[int],
    meta_seeds: Sequence[int],
) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for arm in sp.S3_ARMS:
        for task in tasks:
            for budget in budgets:
                for meta_seed in meta_seeds:
                    for opt_seed in opt_seeds:
                        specs.append(
                            {
                                "arm": str(arm),
                                "task_id": task.task_id,
                                "split": str(task.split),
                                "budget": int(budget),
                                "opt_seed": int(opt_seed),
                                "meta_seed": int(meta_seed),
                                "phase": phase,
                            }
                        )
    return specs



# ---------------------------------------------------------------------------
# 模型训练 / episode bank / 梯度门：正式运行前的准备产物
# ---------------------------------------------------------------------------
SMOKE_TRAIN_TASK_COUNT = 4


def _bank_sha_mapping(episode_banks: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "banks": {("meta_seed_" + str(seed)): info["sha256"] for seed, info in sorted(episode_banks.items())},
        "files": [
            {
                "meta_seed": int(seed),
                "path": info["path"],
                "sha256": info["sha256"],
                "bytes": info["bytes"],
                "episodes": info["episodes"],
            }
            for seed, info in sorted(episode_banks.items())
        ],
        "episodes_per_bank": int(sum(info["episodes"] for info in episode_banks.values()) // max(1, len(episode_banks))),
        "unique_episodes": int(sum(info["episodes"] for info in episode_banks.values())),
        "model_episode_pairs": int(sum(info["episodes"] for info in episode_banks.values()) * 2),
        "physical_call_count": 0,
    }


def prepare_training_tasks(
    *,
    run_mode: str,
    by_split: Mapping[str, Sequence[tf.S3ConflictTask]],
) -> list[tf.S3ConflictTask]:
    if run_mode == "SMOKE":
        tasks = list(by_split["meta_validation"])[:SMOKE_TRAIN_TASK_COUNT]
        _require(len(tasks) == SMOKE_TRAIN_TASK_COUNT, S3_RUNNER_DATA_BOUNDARY_ERROR, "SMOKE 训练任务不足 4 个")
        return tasks
    tasks = list(by_split["meta_train"])
    _require(
        len(tasks) == sp.S3_SPLIT_COUNTS["meta_train"],
        S3_RUNNER_DATA_BOUNDARY_ERROR,
        "FORMAL 训练任务必须为 60 个 meta_train",
    )
    return tasks


def train_models(
    *,
    run_mode: str,
    run_id: str,
    models_dir: Path,
    train_tasks: Sequence[tf.S3ConflictTask],
    meta_seeds: Sequence[int],
    outer_steps: int,
    episode_banks: Mapping[int, Mapping[str, Any]],
    design_cache: Mapping[str, Mapping[str, np.ndarray]],
    prereg: Mapping[str, Any],
    repo_root: Path,
    torch_threads: int = 1,
) -> dict[str, Any]:
    tasks_by_id = {task.task_id: task for task in train_tasks}
    models: dict[tuple[str, int], dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    train_records: list[dict[str, Any]] = []
    per_seed_resources: list[dict[str, Any]] = []
    for kind in sp.S3_MODEL_KINDS:
        for meta_seed in meta_seeds:
            bank = episode_banks[int(meta_seed)]
            result = train_model(
                kind,
                int(meta_seed),
                tasks_by_id,
                bank["episodes_list"],
                run_id=run_id,
                episode_bank_sha256=bank["sha256"],
                design_cache=design_cache,
            )
            model_path = models_dir / (str(kind) + "_meta_" + str(int(meta_seed)) + ".json")
            info = write_json_canonical(model_path, result["payload"])
            models[(str(kind), int(meta_seed))] = {
                "config": model_config_dict(str(kind), int(meta_seed)),
                "parameters": result["parameters"],
                "sha256": info["sha256"],
                "path": info["path"],
                "train_wall_s": result["train_wall_s"],
                "peak_memory_mb": result["peak_memory_mb"],
                "final_train_loss": result["final_train_loss"],
                "episode_bank_sha256": bank["sha256"],
            }
            entries.append(
                {
                    "arm_type": str(kind),
                    "meta_seed": int(meta_seed),
                    "config": model_config_dict(str(kind), int(meta_seed)),
                    "path": "models/" + model_path.name,
                    "sha256": info["sha256"],
                    "train_wall_s": _round6(result["train_wall_s"]),
                    "peak_memory_mb": _round6(result["peak_memory_mb"]),
                    "episode_bank_sha256": bank["sha256"],
                    "final_train_loss": float(result["final_train_loss"]),
                }
            )
            train_records.extend(result["records"])
            per_seed_resources.append(
                {
                    "arm_type": str(kind),
                    "meta_seed": int(meta_seed),
                    "train_wall_s": _round6(result["train_wall_s"]),
                    "peak_memory_mb": _round6(result["peak_memory_mb"]),
                    "steps": int(result["steps"]),
                }
            )
    # FORMAL：训练产物必须与 prereg 冻结的模型文件 / episode bank 逐字节一致
    if run_mode == "FORMAL":
        frozen = prereg.get("models") or {}
        frozen_banks = (prereg.get("episode_bank") or {}).get("banks") or {}
        for kind in sp.S3_MODEL_KINDS:
            kind_block = frozen.get(kind)
            _require(isinstance(kind_block, Mapping), S3_RUNNER_PREREG_ERROR, "prereg 缺少 models 节: " + str(kind))
            frozen_rows = {int(row["meta_seed"]): row for row in kind_block.get("models") or []}
            for meta_seed in meta_seeds:
                _require(
                    int(meta_seed) in frozen_rows,
                    S3_RUNNER_PREREG_ERROR,
                    "prereg 缺少模型 " + str(kind) + "/" + str(meta_seed),
                )
                expected = str(frozen_rows[int(meta_seed)]["sha256"])
                actual = models[(str(kind), int(meta_seed))]["sha256"]
                _require(
                    expected == actual,
                    S3_RUNNER_MODEL_ERROR,
                    "模型与 prereg 不一致 " + str(kind) + "/" + str(meta_seed) + ": " + expected + " != " + actual,
                )
        for meta_seed in meta_seeds:
            expected_bank = str(frozen_banks.get("meta_seed_" + str(int(meta_seed))))
            actual_bank = episode_banks[int(meta_seed)]["sha256"]
            _require(
                expected_bank == actual_bank,
                S3_RUNNER_BANK_ERROR,
                "episode bank 与 prereg 不一致 meta_seed=" + str(meta_seed),
            )
    train_records.sort(key=lambda row: (str(row["run_id"]), int(row["meta_seed"]), int(row["outer_step"])))
    manifest_models = {
        "schema_version": sp.S3_MODEL_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "models": entries,
    }
    return {
        "models": models,
        "entries": entries,
        "manifest": manifest_models,
        "train_records": train_records,
        "per_seed_resources": per_seed_resources,
    }


def _model_block_summary(
    kind: str,
    entries: Sequence[Mapping[str, Any]],
    episode_banks: Mapping[int, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [
        {
            "meta_seed": int(row["meta_seed"]),
            "path": str(row["path"]),
            "sha256": str(row["sha256"]),
            "config": dict(row["config"]),
            "episode_bank_sha256": str(row["episode_bank_sha256"]),
            "final_train_loss": float(row["final_train_loss"]),
        }
        for row in entries
        if str(row["arm_type"]) == str(kind)
    ]
    return {
        "config": model_config_dict(kind, 0),
        "sha256": sp.canonical_sha256(rows),
        "meta_seeds": [int(row["meta_seed"]) for row in rows],
        "models": rows,
        "episode_bank_sha256": {
            "meta_seed_" + str(int(seed)): str(episode_banks[int(seed)]["sha256"])
            for seed in sorted(episode_banks)
        },
    }


def prepare_episode_banks(
    *,
    run_mode: str,
    models_dir: Path,
    train_tasks: Sequence[tf.S3ConflictTask],
    meta_seeds: Sequence[int],
    outer_steps: int,
    design_cache: Mapping[str, Mapping[str, np.ndarray]],
) -> dict[int, dict[str, Any]]:
    banks: dict[int, dict[str, Any]] = {}
    for meta_seed in meta_seeds:
        episodes = build_episode_bank(
            train_tasks,
            int(meta_seed),
            int(outer_steps),
            design_cache=design_cache,
        )
        path = models_dir / ("episode_bank_meta_" + str(int(meta_seed)) + ".jsonl")
        info = write_episode_bank(path, episodes)
        banks[int(meta_seed)] = {
            "path": "models/" + path.name,
            "sha256": info["sha256"],
            "bytes": info["bytes"],
            "episodes": info["episodes"],
            "episodes_list": episodes,
        }
    return banks


def verify_fd_gate_payload(
    payload: Any,
    *,
    run_mode: str,
    expected_per_model: int | None = None,
) -> dict[str, Any]:
    """校验 FD/梯度门 v1（p4ra-s3-fd-gate-v1）：结构、每模型坐标数、误差、负控。"""
    code = S3_RUNNER_GATE_ERROR
    _require(isinstance(payload, Mapping), code, "FD 门必须是 JSON object")
    _require(payload.get("schema_version") == sp.S3_FD_GATE_SCHEMA_VERSION, code, "FD 门 schema_version 不符")
    _require(str(payload.get("status")) == "PASS", code, "FD 门 status 必须 PASS")
    _require(int(payload.get("physical_call_count", -1)) == 0, code, "FD 门 physical_call_count 必须 0")
    _require(abs(float(payload.get("tolerance", "nan")) - float(sp.S3_FD_TOLERANCE)) <= 0.0, code, "FD 门 tolerance 不符")
    _require(str(payload.get("epsilon_rule")) == sp.S3_FD_EPSILON_RULE, code, "FD 门 epsilon_rule 不符")
    per_model = int(payload.get("coordinates_per_model", -1))
    if expected_per_model is not None:
        _require(per_model == int(expected_per_model), code, "FD 门每模型坐标数不符")
    if run_mode == "FORMAL":
        _require(per_model == int(sp.S3_FD_GATE_COORDINATES_PER_MODEL), code, "FORMAL FD 门每模型坐标数必须 32")
    models = payload.get("models")
    raw_keys = tuple(models) if isinstance(models, Mapping) else ()
    _require(set(raw_keys) == set(sp.S3_FD_GATE_MODEL_KEYS), code, "FD 门 models 键必须恰为 " + repr(sp.S3_FD_GATE_MODEL_KEYS))
    _require(
        int(payload.get("coordinates_total", -1)) == per_model * len(sp.S3_FD_GATE_MODEL_KEYS),
        code,
        "FD 门 coordinates_total 不符",
    )
    overall = 0.0
    for key in sp.S3_FD_GATE_MODEL_KEYS:
        block = models[key]
        _require(isinstance(block, Mapping), code, "FD 门 models." + key + " 必须是 mapping")
        _require(str(block.get("status")) == "PASS", code, "FD 门 models." + key + ".status 必须 PASS")
        _require(str(block.get("arm_type")) in sp.S3_MODEL_KINDS, code, "FD 门 models." + key + ".arm_type 非法")
        n_checked = int(block.get("n_checked", -1))
        _require(n_checked == per_model, code, "FD 门 models." + key + ".n_checked 不符")
        coordinates = block.get("coordinates")
        _require(isinstance(coordinates, list) and len(coordinates) == n_checked, code, "FD 门 coordinates 长度不符")
        block_max = 0.0
        for item in coordinates:
            _require(isinstance(item, Mapping), code, "FD 门坐标必须是 mapping")
            _require(
                {"index", "param", "analytic", "numeric", "relative_error"} <= set(item),
                code,
                "FD 门坐标缺少必需键",
            )
            relative = abs(float(item["relative_error"]))
            _require(math.isfinite(relative), code, "FD 门坐标相对误差非有限")
            _require(relative <= float(sp.S3_FD_TOLERANCE), code, "FD 门坐标相对误差超限")
            block_max = max(block_max, relative)
        _require(
            abs(float(block.get("max_relative_error", "nan")) - block_max) <= 1e-15,
            code,
            "FD 门 models." + key + ".max_relative_error 与坐标实算不一致",
        )
        overall = max(overall, block_max)
    _require(
        abs(float(payload.get("max_relative_error", "nan")) - overall) <= 1e-15,
        code,
        "FD 门顶层 max_relative_error 与坐标实算不一致",
    )
    negatives = payload.get("negatives")
    _require(isinstance(negatives, Mapping), code, "FD 门 negatives 必须是 mapping")
    _require(set(negatives) == set(sp.S3_FD_GATE_NEGATIVE_KEYS), code, "FD 门 negatives 键不符")
    for key in sp.S3_FD_GATE_NEGATIVE_KEYS:
        _require(str(negatives[key]) == "PASS", code, "FD 门 negatives." + key + " 必须 PASS")
    return dict(payload)


def _fd_gate_model_block(kind: str, gate_payload: Mapping[str, Any], max_coordinates: int) -> dict[str, Any]:
    coordinates = [
        {
            "index": int(index),
            "param": str(check["parameter_name"]),
            "analytic": float(check["analytic"]),
            "numeric": float(check["numeric"]),
            "relative_error": float(check["relative_error"]),
        }
        for index, check in enumerate(gate_payload["checks"])
    ]
    _require(len(coordinates) == int(max_coordinates), S3_RUNNER_GATE_ERROR, "梯度门坐标数不符")
    for item in coordinates:
        _require(
            abs(float(item["relative_error"])) <= float(sp.S3_FD_TOLERANCE),
            S3_RUNNER_GATE_ERROR,
            "梯度门相对误差超限",
        )
    return {
        "arm_type": str(kind),
        "meta_seed": 0,
        "n_checked": int(len(coordinates)),
        "status": "PASS",
        "max_relative_error": max((abs(item["relative_error"]) for item in coordinates), default=0.0),
        "coordinates": coordinates,
    }


def _tamper_negative_passes(gate_payload: Mapping[str, Any]) -> bool:
    """负控：篡改 1 个坐标后 maml.assert_s3_gate_consistent 必须抛 S3_GATE_TAMPER_DETECTED。"""
    try:
        tampered = json.loads(json.dumps(gate_payload))
        first = tampered["checks"][0]
        first["numeric"] = float(first["numeric"]) * 1.000001 + 1e-12
        maml.assert_s3_gate_consistent(tampered)
    except maml.MAMLError as exc:
        return str(exc).startswith(maml.S3_GATE_TAMPER_DETECTED)
    return False


def build_gradient_gate(
    *,
    run_mode: str,
    gate_path: Path,
    created_utc: str,
    prereg: Mapping[str, Any],
    models: Mapping[tuple[str, int], Mapping[str, Any]],
    episode_banks: Mapping[int, Mapping[str, Any]],
    design_cache: Mapping[str, Mapping[str, np.ndarray]],
    tasks_by_id: Mapping[str, tf.S3ConflictTask],
    fd_coordinates: int,
) -> dict[str, Any]:
    """生成 FD/梯度门 v1（SMOKE 用；FORMAL 从 M2 冻结件读取，不调用本函数重算）。"""
    bank = episode_banks[0]
    gate_rows = [
        row
        for row in bank["episodes_list"]
        if int(row["outer_step"]) == 0 and int(row["slot"]) < 4
    ]
    _require(len(gate_rows) == 4, S3_RUNNER_GATE_ERROR, "梯度门需要 meta_seed=0、step=0、slot 0..3 共 4 个 episode")
    gate_episodes = [
        build_task_episode(
            tasks_by_id[str(row["task_id"])],
            row["support_indices"],
            row["query_indices"],
            design_cache,
        )
        for row in gate_rows
    ]
    gates: dict[str, Any] = {}
    for kind in sp.S3_MODEL_KINDS:
        entry = models[(str(kind), 0)]
        config = maml.config_from_dict(entry["config"])
        gates[str(kind)] = maml.s3_gradient_gate(
            entry["parameters"],
            gate_episodes,
            config,
            mode=str(kind),
            max_coordinates=int(fd_coordinates),
        )
    for payload in gates.values():
        maml.assert_s3_gate_consistent(payload)
    models_block: dict[str, Any] = {}
    for kind in sp.S3_MODEL_KINDS:
        models_block[str(kind) + "_meta_0"] = _fd_gate_model_block(str(kind), gates[str(kind)], int(fd_coordinates))
    tamper_ok = _tamper_negative_passes(gates["fomaml"])
    fomaml_entry = models[("fomaml", 0)]
    fomaml_config = maml.config_from_dict(fomaml_entry["config"])
    k0_config = dataclasses.replace(fomaml_config, inner_steps=0)
    k0_gate = maml.s3_gradient_gate(
        fomaml_entry["parameters"],
        gate_episodes,
        k0_config,
        mode="fomaml",
        max_coordinates=int(fd_coordinates),
    )
    maml.assert_s3_gate_consistent(k0_gate)
    negatives = {
        "tamper": "PASS" if tamper_ok else "FAIL",
        "anil_body_frozen": "PASS" if bool(gates["anil"].get("anil_body_frozen")) else "FAIL",
        "k0_equivalence": "PASS" if bool(k0_gate.get("k0_equivalence")) else "FAIL",
    }
    max_relative_error = max(
        (abs(float(item["relative_error"])) for block in models_block.values() for item in block["coordinates"]),
        default=0.0,
    )
    payload: dict[str, Any] = {
        "schema_version": sp.S3_FD_GATE_SCHEMA_VERSION,
        "created_utc": str(created_utc),
        "tolerance": float(sp.S3_FD_TOLERANCE),
        "epsilon_rule": str(sp.S3_FD_EPSILON_RULE),
        "coordinates_per_model": int(fd_coordinates),
        "coordinates_total": int(fd_coordinates) * len(sp.S3_FD_GATE_MODEL_KEYS),
        "models": models_block,
        "negatives": negatives,
        "status": "PASS",
        "max_relative_error": max_relative_error,
        "override": run_mode == "SMOKE",
        "physical_call_count": 0,
        "solver_invocations": [],
    }
    verify_fd_gate_payload(payload, run_mode=run_mode)
    info = write_json_canonical(gate_path, payload)
    return {"path": str(gate_path), "sha256": info["sha256"], "bytes": info["bytes"], "payload": payload}


def load_frozen_gate(*, repo_root: Path, prereg: Mapping[str, Any], run_mode: str = "FORMAL") -> dict[str, Any]:
    """读取 M2 冻结 FD 门（Q2）：sha 由调用方与 run_config/run 产物三方比对。"""
    path = Path(repo_root) / sp.S3_GATE_RELPATH
    _require(
        path.is_file(),
        S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
        "缺少 M2 冻结 FD 梯度门: " + sp.S3_GATE_RELPATH,
    )
    data = path.read_bytes()
    sha = sp.sha256_bytes(data)
    _require(
        sha == str(prereg.get("fd_gate_sha256") or ""),
        S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
        "冻结 FD 门 raw sha 与 prereg.fd_gate_sha256 不一致",
    )
    payload = read_json_file(path)
    verify_fd_gate_payload(payload, run_mode="FORMAL")
    return {
        "path": sp.S3_GATE_RELPATH,
        "sha256": sha,
        "bytes": len(data),
        "payload": payload,
        "frozen": True,
    }


def load_frozen_models(
    *,
    repo_root: Path,
    prereg: Mapping[str, Any],
    meta_seeds: Sequence[int],
) -> dict[tuple[str, int], dict[str, Any]]:
    """加载 M2 冻结模型（Q3）：逐文件 sha/bytes == prereg.models，失败 fail-closed。"""
    root = Path(repo_root)
    frozen = prereg.get("models") or {}
    models: dict[tuple[str, int], dict[str, Any]] = {}
    for kind in sp.S3_MODEL_KINDS:
        _require(isinstance(frozen.get(kind), Mapping), S3_RUNNER_PREREG_ERROR, "prereg 缺少 models." + str(kind))
        rows = {int(row["meta_seed"]): row for row in frozen[str(kind)].get("models") or []}
        for meta_seed in meta_seeds:
            seed = int(meta_seed)
            _require(seed in rows, S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "prereg 缺少冻结模型 " + str(kind) + "/" + str(seed))
            row = rows[seed]
            rel_path = str(row["path"])
            path = root / rel_path
            _require(path.is_file(), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结模型文件不存在: " + rel_path)
            data = path.read_bytes()
            sha = sp.sha256_bytes(data)
            _require(sha == str(row["sha256"]), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结模型 sha 与 prereg 不一致: " + rel_path)
            _require(int(row["bytes"]) == len(data), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结模型 bytes 与 prereg 不一致: " + rel_path)
            loaded = load_model_file(path)
            _require(loaded["kind"] == str(kind), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结模型 arm_type 不符: " + rel_path)
            _require(int(loaded["meta_seed"]) == seed, S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结模型 meta_seed 不符: " + rel_path)
            _require(loaded["sha256"] == sha, S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结模型重读 sha 不符: " + rel_path)
            models[(str(kind), seed)] = {
                "config": dict(loaded["payload"]["config"]),
                "parameters": loaded["parameters"],
                "sha256": sha,
                "path": rel_path,
                "bytes": len(data),
            }
    return models


def load_frozen_episode_banks(
    *, repo_root: Path, prereg: Mapping[str, Any], meta_seeds: Sequence[int]
) -> dict[int, dict[str, Any]]:
    """加载 M2 冻结 episode bank（逐文件 raw sha == prereg）。"""
    root = Path(repo_root)
    block = prereg.get("episode_bank") or {}
    rows = {int(row["meta_seed"]): row for row in block.get("files") or []}
    banks: dict[int, dict[str, Any]] = {}
    for meta_seed in meta_seeds:
        seed = int(meta_seed)
        _require(seed in rows, S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "prereg 缺少冻结 episode bank meta_seed=" + str(seed))
        row = rows[seed]
        rel_path = str(row["path"])
        path = root / rel_path
        _require(path.is_file(), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结 episode bank 不存在: " + rel_path)
        data = path.read_bytes()
        sha = sp.sha256_bytes(data)
        _require(sha == str(row["sha256"]), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结 episode bank sha 与 prereg 不一致: " + rel_path)
        episodes = read_jsonl(path)
        _require(len(episodes) == int(row["episodes"]), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "冻结 episode bank 行数不符: " + rel_path)
        banks[seed] = {
            "path": "models/episode_bank_meta_" + str(seed) + ".jsonl",
            "source_path": rel_path,
            "sha256": sha,
            "bytes": len(data),
            "episodes": len(episodes),
            "episodes_list": None,
            "raw": data,
        }
    return banks


def load_frozen_model_manifest(
    *,
    repo_root: Path,
    prereg: Mapping[str, Any],
    models: Mapping[tuple[str, int], Mapping[str, Any]],
    episode_banks: Mapping[int, Mapping[str, Any]],
    run_id: str,
    created_utc: str,
    out: Path,
) -> dict[str, Any]:
    """加载 M2 冻结 model_manifest，复制到 run 目录并追加 verification（Q3）。"""
    root = Path(repo_root)
    source = root / sp.S3_MODEL_MANIFEST_RELPATH
    _require(source.is_file(), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "缺少 M2 冻结 model_manifest: " + sp.S3_MODEL_MANIFEST_RELPATH)
    manifest = read_json_file(source)
    _require(isinstance(manifest, Mapping), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "model_manifest 必须是 mapping")
    _require(
        manifest.get("schema_version") == sp.S3_MODEL_MANIFEST_SCHEMA_VERSION,
        S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
        "model_manifest schema_version 不符",
    )
    rows = manifest.get("models")
    _require(isinstance(rows, list) and bool(rows), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "model_manifest 缺 models 列表")
    seen: set[tuple[str, int]] = set()
    for row in rows:
        _require(isinstance(row, Mapping), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "model_manifest 条目必须是 mapping")
        _require(
            set(row) == set(sp.S3_MODEL_ENTRY_FIELDS),
            S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
            "model_manifest 条目字段集不符",
        )
        key = (str(row["arm_type"]), int(row["meta_seed"]))
        _require(key not in seen, S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "model_manifest 条目重复")
        seen.add(key)
        _require(key in models, S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "model_manifest 条目不属本次冻结 model 集合")
        _require(
            str(row["sha256"]) == str(models[key]["sha256"]),
            S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
            "model_manifest 条目 sha 与冻结模型不一致",
        )
        _require(
            dict(row["config"]) == model_config_dict(key[0], key[1]),
            S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
            "model_manifest 条目 config 不符",
        )
        _require(
            str(row["episode_bank_sha256"]) == str(episode_banks[key[1]]["sha256"]),
            S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
            "model_manifest 条目 episode_bank_sha256 不符",
        )
    _require(len(rows) == len(models), S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, "model_manifest 条目数不符")
    copied = {
        "schema_version": str(manifest.get("schema_version")),
        "run_id": str(run_id),
        "models": [dict(row) for row in rows],
        "verification": {
            "loaded_from_prereg": True,
            "prereg_models_sha256": sp.canonical_sha256(prereg.get("models") or {}),
            "verified_utc": str(created_utc),
            "source": sp.S3_MODEL_MANIFEST_RELPATH,
        },
    }
    info = write_json_canonical(out / S3_RUNNER_MODEL_MANIFEST_FILE, copied)
    return {"manifest": copied, "entries": [dict(row) for row in rows], "info": info}



# ---------------------------------------------------------------------------
# run_config / run_summary / data_manifest
# ---------------------------------------------------------------------------
def _scope_notes(
    *,
    run_mode: str,
    workers: int,
    smoke_overrides: Mapping[str, Any] | None,
    record_streams: Mapping[str, int],
) -> list[str]:
    notes = [
        "DEVELOPMENT_VALIDATION_ONLY：S3 主统计仅用 meta_test，OOD 用 meta_test_ood，负控用 meta_test_negative_control；meta_train 只用于训练。",
        "physical_call_count=0：无 RCAIDE Mission / VSPAERO / SU2 / Gmsh / 任何真实求解器调用，全部为纯解析合成评估（synthetic_call_count 见 data_manifest）。",
        "record_digest 排除 wall_s/peak_memory_mb/record_digest 三个字段；确定性比较只比较 record_core。",
        "梯度门 FD 取 adapted point（与计划 §4.4 “原始 theta”文本存在歧义，按旧门口径实现，见 S3_M1 实现报告）。",
        "per-record wall_s 未逐点计时（统一 0.0）；run 级墙钟与峰值见 execution_report.json 与 run_summary.per_run。",
        "parallel_workers=" + str(int(workers)) + "；sum_run_wall_seconds=sum(逐 run wall_s)（单核等效），campaign_wall_s 为并行墙钟；Σ run wall 硬上限 sum_run_wall_limit_s=" + str(int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"])) + "；实测值只写入 execution_report.json 与 run_summary.resources，不写入本确定性字段；worker 编号不进入任何 RNG/记录。",
    ]
    if run_mode == "SMOKE":
        notes.append(
            "SMOKE：训练使用 meta_validation 前 4 task、评估使用 meta_validation 前 N task；smoke_overrides="
            + sp.canonical_json(dict(smoke_overrides or {}))
        )
    else:
        notes.append("FORMAL：主网格 5 臂 × 2 预算 × 5 opt_seed × 3 meta_seed × 20 task = 3000 runs / 288000 evals；五流合计 3780 runs / 362880 evals。")
    notes.append(
        "record_streams=main:"
        + str(int(record_streams.get("main", 0)))
        + ",nc:"
        + str(int(record_streams.get("nc", 0)))
        + ",ood:"
        + str(int(record_streams.get("ood", 0)))
        + ",det:"
        + str(int(record_streams.get("det", 0)))
        + "（五条记录流评估行合计；run_records.jsonl 仅主网格；aux 记录文件为 negative_control_records.jsonl / ood_records.jsonl / determinism/r1..r3/run_records.jsonl）。"
    )
    return notes


def resolve_budget(
    *,
    run_mode: str,
    prereg: Mapping[str, Any],
    smoke_overrides: Mapping[str, Any] | None,
) -> dict[str, Any]:
    _require(run_mode in S3_RUNNER_EXECUTION_MODES, S3_RUNNER_ERROR, "run_mode 必须是 FORMAL/SMOKE")
    budgets_block = prereg.get("budgets") or {}
    formal = {
        "outer_steps": int(budgets_block.get("outer_steps", S3_TRAIN_OUTER_STEPS)),
        "meta_seeds": [int(seed) for seed in (budgets_block.get("meta_seeds") or sp.S3_MODEL_META_SEEDS)],
        "budgets": [int(item) for item in (budgets_block.get("budgets") or sp.S3_BUDGETS)],
        "opt_seeds": [int(item) for item in (budgets_block.get("opt_seeds") or sp.S3_OPT_SEEDS)],
        "eval_tasks": int(budgets_block.get("eval_tasks", sp.S3_EVAL_TASKS)),
        "k_sweep": [int(budgets_block.get("k_shot", 5))],
        "fd_coordinates": int(sp.S3_FD_MAX_COORDINATES),
        "eval_split": str(budgets_block.get("eval_split", sp.S3_EVAL_SPLIT)),
    }
    if run_mode == "FORMAL":
        _require(smoke_overrides is None, S3_RUNNER_ERROR, "FORMAL 不允许 smoke_overrides")
        budget = dict(formal)
        budget["run_mode"] = "FORMAL"
        budget["smoke_overrides"] = None
        return budget
    _require(isinstance(smoke_overrides, Mapping), S3_RUNNER_ERROR, "SMOKE 必须提供 smoke_overrides")
    overrides = dict(smoke_overrides)
    _require(
        set(overrides) == set(sp.S3_SMOKE_OVERRIDE_KEYS),
        S3_RUNNER_ERROR,
        "smoke_overrides 键集必须恰为 " + repr(tuple(sp.S3_SMOKE_OVERRIDE_KEYS)),
    )
    outer_steps = int(overrides["outer_steps"])
    meta_seeds = [int(item) for item in overrides["meta_seeds"]]
    budgets = [int(item) for item in overrides["budgets"]]
    opt_seeds = [int(item) for item in overrides["opt_seeds"]]
    eval_tasks = int(overrides["eval_tasks"])
    k_sweep = [int(item) for item in overrides["k_sweep"]]
    fd_coordinates = int(overrides["fd_coordinates"])
    _require(1 <= outer_steps <= S3_TRAIN_OUTER_STEPS, S3_RUNNER_ERROR, "SMOKE outer_steps 越界")
    _require(meta_seeds and all(seed in sp.S3_MODEL_META_SEEDS for seed in meta_seeds), S3_RUNNER_ERROR, "SMOKE meta_seeds 非法")
    _require(budgets and all(item in sp.S3_BUDGETS for item in budgets), S3_RUNNER_ERROR, "SMOKE budgets 非法")
    _require(opt_seeds and all(item >= 0 for item in opt_seeds), S3_RUNNER_ERROR, "SMOKE opt_seeds 非法")
    _require(2 <= eval_tasks <= sp.S3_EVAL_TASKS, S3_RUNNER_ERROR, "SMOKE eval_tasks 越界")
    _require(k_sweep == [5], S3_RUNNER_ERROR, "SMOKE k_sweep 必须为 [5]（S3 K 固定为 5）")
    _require(1 <= fd_coordinates <= int(sp.S3_FD_MAX_COORDINATES), S3_RUNNER_ERROR, "SMOKE fd_coordinates 越界")
    return {
        "run_mode": "SMOKE",
        "outer_steps": outer_steps,
        "meta_seeds": meta_seeds,
        "budgets": budgets,
        "opt_seeds": opt_seeds,
        "eval_tasks": eval_tasks,
        "k_sweep": k_sweep,
        "fd_coordinates": fd_coordinates,
        "eval_split": "meta_validation",
        "smoke_overrides": overrides,
    }


def _expected_record_counts(
    *,
    run_mode: str,
    train_models_count: int,
    outer_steps: int,
    main_specs: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    train_expected = int(train_models_count) * int(outer_steps)
    evals_per_run = {
        int(spec["budget"]): int(spec["budget"]) for spec in main_specs
    }
    eval_expected = int(sum(evals_per_run[int(spec["budget"])] for spec in main_specs))
    return {"train": train_expected, "eval": eval_expected, "total": train_expected + eval_expected}


def _status_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    counts = {
        "train": {status: 0 for status in sp.S3_RECORD_STATUSES},
        "eval": {status: 0 for status in sp.S3_RECORD_STATUSES},
    }
    for record in records:
        bucket = "train" if "outer_step" in record else "eval"
        status = "FAILED" if record.get("f") is None and bucket == "eval" and record.get("status") == "FAILED" else "OK"
        if status not in counts[bucket]:
            status = "OK"
        counts[bucket][status] += 1
    return counts


def select_determinism_specs(
    main_specs: Sequence[Mapping[str, Any]],
    *,
    prereg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """按 prereg determinism 规则（5 臂 x 8 shard 最小者 40 + 每臂补 2 = 60）选确定性子集并做 fail-closed 断言。"""
    keys = [canonical_run_key(spec) for spec in main_specs]
    selected = sp.select_determinism_run_keys(keys, shard_count=int(sp.S3_DETERMINISM_SHARD_COUNT))
    expected_sha = str((prereg.get("determinism") or {}).get("subset_run_keys_sha256") or "")
    _require(
        bool(expected_sha) and sp.determinism_run_keys_sha256(selected) == expected_sha,
        S3_RUNNER_VALIDATION_ERROR,
        "确定性子集与 prereg determinism.subset_run_keys_sha256 不符",
    )
    by_key = {sp.canonical_json(canonical_run_key(spec)): spec for spec in main_specs}
    specs: list[dict[str, Any]] = []
    for key in selected:
        spec = by_key.get(sp.canonical_json(key))
        _require(spec is not None, S3_RUNNER_VALIDATION_ERROR, "确定性子集 run_key 不在主网格: " + str(dict(key)))
        specs.append(dict(spec))
    specs.sort(key=run_sort_key)
    _require(len(specs) == int(sp.S3_DETERMINISM_SUBSET_RUNS), S3_RUNNER_VALIDATION_ERROR, "确定性子集 run 数不符")
    return specs


def _det_record_relpath(repeat: int) -> str:
    return "/".join((S3_RUNNER_DET_DIR, "r" + str(int(repeat)), S3_RUNNER_RECORD_FILE))


def _split_task_ids(by_split: Mapping[str, Sequence[tf.S3ConflictTask]]) -> tuple[dict[str, list[str]], dict[str, str]]:
    mapping: dict[str, list[str]] = {}
    hashes: dict[str, str] = {}
    for split in sp.S3_ALLOWED_SPLITS:
        ids = sorted(task.task_id for task in by_split.get(split, ()))
        mapping[str(split)] = ids
        hashes[str(split)] = sp.task_ids_sha256(ids)
    return mapping, hashes


def build_run_config(
    *,
    run_id: str,
    run_mode: str,
    budget: Mapping[str, Any],
    prereg: Mapping[str, Any],
    family_package: Mapping[str, Any],
    episode_banks: Mapping[int, Mapping[str, Any]],
    model_block: Mapping[str, Any],
    gate: Mapping[str, Any],
    main_specs: Sequence[Mapping[str, Any]],
    record_counts: Mapping[str, int],
    scope_notes: Sequence[str],
    campaign_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    auth = validate_campaign_authorization(run_mode, campaign_authorization)
    family = prereg.get("family") or {}
    references = prereg.get("references_sealed") or {}
    models_summary = {
        "fomaml": _model_block_summary("fomaml", model_block["entries"], episode_banks),
        "anil": _model_block_summary("anil", model_block["entries"], episode_banks),
    }
    k_sweep_values = [int(item) for item in budget["k_sweep"]]
    if run_mode == "FORMAL":
        _require(
            k_sweep_values == [int(sp.S3_K_SHOT)],
            S3_RUNNER_PREREG_ERROR,
            "FORMAL k_sweep 必须为 [5]（S3 K 固定为 5）",
        )
    config: dict[str, Any] = {
        "schema_version": sp.S3_RUN_CONFIG_SCHEMA_VERSION,
        "run_id": str(run_id),
        "run_mode": str(run_mode),
        "prereg_id": str(prereg.get("prereg_id")),
        "prereg_digest": str(prereg.get("prereg_digest")),
        "analysis_plan_digest": str(prereg.get("analysis_plan_digest")),
        "code_sha": str(prereg.get("code_sha")),
        "campaign_authorization_id": (auth["campaign_authorization_id"] if auth else None),
        "campaign_authorization_utc": (auth["campaign_authorization_utc"] if auth else None),
        "family_package": {
            "path": str(sp.S3_FAMILY_PACKAGE_RELPATH),
            "sha256": str(family.get("family_package_sha256")),
            "bytes": int(family_package["bytes"]),
        },
        "task_ids_sha256": str(family["task_ids_sha256"]),
        "references_sealed_sha256": str(references.get("sha256")),
        "data_boundary": dict(prereg.get("data_boundary") or {}),
        "models": models_summary,
        "arms": list(prereg.get("arms") or []),
        "budgets": dict(prereg.get("budgets") or {}),
        "seeds": {
            "meta_seeds": [int(seed) for seed in budget["meta_seeds"]],
            "opt_seeds": [int(seed) for seed in budget["opt_seeds"]],
            "k_shot": int(sp.S3_K_SHOT),
        },
        "episode_bank": _bank_sha_mapping(episode_banks),
        "evaluation_grid": {
            "eval_split": str(budget["eval_split"]),
            "eval_tasks": int(budget["eval_tasks"]),
            "budgets": [int(item) for item in budget["budgets"]],
            "K": [int(sp.S3_K_SHOT)],
            "meta_seeds": [int(seed) for seed in budget["meta_seeds"]],
            "opt_seeds": [int(seed) for seed in budget["opt_seeds"]],
            "main_runs": int(len(main_specs)),
            "main_evals": int(sum(int(spec["budget"]) for spec in main_specs)),
        },
        "k_sweep": k_sweep_values,
        "fd_or_gradient_gate": {
            "sha256": str(gate["sha256"]),
            "coordinates_per_model": int(gate["payload"]["coordinates_per_model"]),
            "coordinates_total": int(gate["payload"]["coordinates_total"]),
            "mode": str(run_mode),
            "override": bool(gate["payload"].get("override")),
            "models": {
                key: {
                    "path": S3_RUNNER_GATE_FILE,
                    "sha256": str(gate["sha256"]),
                    "n_checked": int(block["n_checked"]),
                    "status": str(block["status"]),
                    "max_relative_error": float(block["max_relative_error"]),
                }
                for key, block in gate["payload"]["models"].items()
            },
        },
        "record_counts": {
            "train": int(record_counts["train"]),
            "eval": int(record_counts["eval"]),
            "total": int(record_counts["total"]),
        },
        "record_schemas": {
            "train": list(sp.S3_TRAIN_RECORD_FIELDS),
            "eval": list(sp.S3_EVAL_RECORD_FIELDS),
        },
        "resource_limits": dict(sp.S3_RESOURCE_LIMITS),
        "physical_call_count": 0,
        "evidence_scope": str(sp.S3_EVIDENCE_SCOPE),
        "scope_notes": list(scope_notes),
    }
    if run_mode == "SMOKE":
        config["smoke_overrides"] = dict(budget["smoke_overrides"] or {})
    return config


def build_data_manifest(
    *,
    run_id: str,
    prereg: Mapping[str, Any],
    by_split: Mapping[str, Sequence[tf.S3ConflictTask]],
    synthetic_call_count: int,
    artifact_sha256: Mapping[str, str],
    run_mode: str = "SMOKE",
    campaign_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    auth = validate_campaign_authorization(run_mode, campaign_authorization)
    split_ids, _split_hashes = _split_task_ids(by_split)
    expected_counts = {split: len(ids) for split, ids in split_ids.items()}
    for split in sp.S3_ALLOWED_SPLITS:
        if split in sp.S3_SPLIT_COUNTS:
            _require(
                expected_counts.get(str(split)) == int(sp.S3_SPLIT_COUNTS[str(split)]),
                S3_RUNNER_DATA_BOUNDARY_ERROR,
                "data_manifest split 计数不符: " + str(split),
            )
    references = prereg.get("references_sealed") or {}
    return {
        "schema_version": sp.S3_DATA_MANIFEST_SCHEMA_VERSION,
        "run_id": str(run_id),
        "campaign_authorization_id": (auth["campaign_authorization_id"] if auth else None),
        "campaign_authorization_utc": (auth["campaign_authorization_utc"] if auth else None),
        "data_boundary": dict(prereg.get("data_boundary") or {}),
        "split_task_ids": split_ids,
        "split_task_ids_sha256": {split: sp.canonical_sha256(ids) for split, ids in split_ids.items()},
        "references_sealed_sha256": str(references.get("sha256")),
        "holdout_truth_read_phase": "EVAL",
        "physical_call_count": 0,
        "solver_processes_started": 0,
        "synthetic_call_count": int(synthetic_call_count),
        "artifact_sha256": {str(key): str(value) for key, value in sorted(artifact_sha256.items())},
    }



# ---------------------------------------------------------------------------
# 产物校验：fail-closed，任何 schema/计数/哈希不符都拒绝
# ---------------------------------------------------------------------------
def _check(checks: dict[str, Any], name: str, ok: bool, detail: Any = "") -> None:
    checks[str(name)] = {"ok": bool(ok), "detail": detail}


def _raw_sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sp.sha256_file(path)


def _record_field_sets() -> tuple[set[str], set[str]]:
    return set(sp.S3_TRAIN_RECORD_FIELDS), set(sp.S3_EVAL_RECORD_FIELDS)


def _run_early_stopped(summary: Mapping[str, Any], execution_report: Mapping[str, Any]) -> bool:
    """资源限制早停判定（A5-S3M1-m03）：run_status 或最终 execution_report.stop_reason 反映停止。"""
    if isinstance(summary, Mapping) and str(summary.get("status")) in (
        S3_RUNNER_RESOURCE_LIMIT,
        S3_RUNNER_DEADLINE_EXCEEDED,
    ):
        return True
    return isinstance(execution_report, Mapping) and execution_report.get("stop_reason") is not None


def validate_run_artifacts(
    run_dir: str | Path,
    *,
    prereg: Mapping[str, Any] | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run_dir)
    checks: dict[str, Any] = {}
    required = [
        S3_RUNNER_CONFIG_FILE,
        S3_RUNNER_SUMMARY_FILE,
        S3_RUNNER_RECORD_FILE,
        S3_RUNNER_MODEL_MANIFEST_FILE,
        S3_RUNNER_DATA_MANIFEST_FILE,
        S3_RUNNER_GATE_FILE,
        S3_RUNNER_EXECUTION_REPORT_FILE,
    ]
    missing = [name for name in required if not (root / name).is_file()]
    _check(checks, "required_artifacts", not missing, {"missing": missing})
    if missing:
        return {"ok": False, "checks": checks, "record_counts": {}, "run_status": None}
    config = read_json_file(root / S3_RUNNER_CONFIG_FILE)
    summary = read_json_file(root / S3_RUNNER_SUMMARY_FILE)
    model_manifest = read_json_file(root / S3_RUNNER_MODEL_MANIFEST_FILE)
    data_manifest = read_json_file(root / S3_RUNNER_DATA_MANIFEST_FILE)
    gate = read_json_file(root / S3_RUNNER_GATE_FILE)
    records = read_jsonl(root / S3_RUNNER_RECORD_FILE)
    execution_report = read_json_file(root / S3_RUNNER_EXECUTION_REPORT_FILE)
    early_stop = _run_early_stopped(summary, execution_report)
    _check(checks, "run_early_stopped", True, early_stop)
    _check(checks, "run_config_is_mapping", isinstance(config, Mapping), type(config).__name__)
    _check(checks, "run_summary_is_mapping", isinstance(summary, Mapping), type(summary).__name__)
    if not isinstance(config, Mapping) or not isinstance(summary, Mapping):
        return {"ok": False, "checks": checks, "record_counts": {}, "run_status": None}
    run_mode = str(config.get("run_mode"))
    if run_mode == "FORMAL":
        stream_required = [
            S3_RUNNER_NC_RECORDS_FILE,
            S3_RUNNER_OOD_RECORDS_FILE,
            S3_RUNNER_DET_CHECK_FILE,
        ] + [
            _det_record_relpath(index) for index in range(1, int(sp.S3_DETERMINISM_REPEATS) + 1)
        ]
        missing_streams = [name for name in stream_required if not (root / name).is_file()]
        _check(checks, "record_stream_artifacts", early_stop or not missing_streams, {"missing": missing_streams, "early_stop": early_stop})
    _check(checks, "run_config_schema", config.get("schema_version") == sp.S3_RUN_CONFIG_SCHEMA_VERSION, config.get("schema_version"))
    expected_fields = set(sp.S3_RUN_CONFIG_REQUIRED_FIELDS)
    if run_mode == "SMOKE":
        expected_fields |= set(sp.S3_RUN_CONFIG_OPTIONAL_FIELDS)
    _check(checks, "run_config_fields", set(config) == expected_fields, sorted(set(config) ^ expected_fields))
    auth_id = config.get("campaign_authorization_id")
    auth_utc = config.get("campaign_authorization_utc")
    has_auth_fields = {"campaign_authorization_id", "campaign_authorization_utc"} <= set(config)
    if run_mode == "FORMAL":
        run_config_auth_ok = (
            has_auth_fields
            and isinstance(auth_id, str)
            and bool(CAMPAIGN_AUTHORIZATION_ID_PATTERN.fullmatch(auth_id))
            and isinstance(auth_utc, str)
            and bool(CAMPAIGN_AUTHORIZATION_UTC_PATTERN.fullmatch(auth_utc))
        )
    else:
        smoke_auth_ok = (auth_id is None and auth_utc is None) or (
            isinstance(auth_id, str)
            and bool(CAMPAIGN_AUTHORIZATION_ID_PATTERN.fullmatch(auth_id))
            and isinstance(auth_utc, str)
            and bool(CAMPAIGN_AUTHORIZATION_UTC_PATTERN.fullmatch(auth_utc))
        )
        run_config_auth_ok = has_auth_fields and smoke_auth_ok
    _check(checks, "run_config_campaign_authorization", run_config_auth_ok, {"id": auth_id, "utc": auth_utc})
    data_manifest_auth_ok = (
        isinstance(data_manifest, Mapping)
        and {"campaign_authorization_id", "campaign_authorization_utc"} <= set(data_manifest)
        and data_manifest.get("campaign_authorization_id") == auth_id
        and data_manifest.get("campaign_authorization_utc") == auth_utc
        and (run_mode != "FORMAL" or (auth_id is not None and auth_utc is not None))
    )
    _check(checks, "data_manifest_campaign_authorization", data_manifest_auth_ok, {"id": data_manifest.get("campaign_authorization_id") if isinstance(data_manifest, Mapping) else None, "utc": data_manifest.get("campaign_authorization_utc") if isinstance(data_manifest, Mapping) else None})
    k_sweep = config.get("k_sweep")
    _check(
        checks,
        "run_config_k_sweep",
        isinstance(k_sweep, list) and [int(item) for item in k_sweep] == [int(sp.S3_K_SHOT)],
        k_sweep,
    )
    _check(checks, "run_mode_consistency", run_mode in S3_RUNNER_EXECUTION_MODES and summary.get("run_mode") == run_mode, run_mode)
    _check(checks, "summary_schema", summary.get("schema_version") == sp.S3_RUN_SUMMARY_SCHEMA_VERSION, summary.get("schema_version"))
    summary_allowed = set(sp.S3_RUN_SUMMARY_REQUIRED_FIELDS) | {"failures"}
    _check(checks, "summary_fields", set(summary) == summary_allowed, sorted(set(summary) ^ summary_allowed))
    _check(checks, "summary_status", summary.get("status") in S3_RUNNER_STATUSES, summary.get("status"))
    _check(checks, "physical_zero", config.get("physical_call_count") == 0 and summary.get("physical_call_count") == 0 and data_manifest.get("physical_call_count") == 0, None)
    _check(checks, "solver_processes_started_zero", data_manifest.get("solver_processes_started") == 0, data_manifest.get("solver_processes_started"))
    _check(checks, "evidence_scope", config.get("evidence_scope") == sp.S3_EVIDENCE_SCOPE and summary.get("evidence_scope") == sp.S3_EVIDENCE_SCOPE, config.get("evidence_scope"))
    _check(checks, "scope_notes_equal", summary.get("scope_notes") == config.get("scope_notes"), None)
    boundary = config.get("data_boundary") or {}
    flags = boundary.get("flags") if isinstance(boundary, Mapping) else None
    boundary_ok = isinstance(flags, Mapping) and set(flags) == set(sp.S3_DATA_BOUNDARY["flags"])
    if boundary_ok:
        boundary_ok = (
            flags.get("holdout_truth_used_for_training") is False
            and flags.get("holdout_truth_used_for_adaptation") is False
            and flags.get("holdout_truth_used_for_bo_ranking") is False
            and flags.get("holdout_truth_read_for_evaluation") is True
        )
    _check(checks, "data_boundary_flags", boundary_ok, flags)
    if prereg is not None:
        _check(checks, "prereg_id_binding", config.get("prereg_id") == prereg.get("prereg_id"), None)
        _check(checks, "prereg_digest_binding", config.get("prereg_digest") == prereg.get("prereg_digest"), None)
        _check(checks, "family_package_binding", (config.get("family_package") or {}).get("sha256") == (prereg.get("family") or {}).get("family_package_sha256"), None)
        _check(checks, "task_ids_binding", config.get("task_ids_sha256") == (prereg.get("family") or {}).get("task_ids_sha256"), None)
        _check(checks, "references_sealed_binding", config.get("references_sealed_sha256") == (prereg.get("references_sealed") or {}).get("sha256"), None)
    else:
        _check(checks, "prereg_binding_not_checked", True, "prereg=None，仅做结构校验")
    episode_bank = config.get("episode_bank") or {}
    bank_files = episode_bank.get("files") if isinstance(episode_bank, Mapping) else None
    bank_ok = isinstance(bank_files, list) and len(bank_files) >= 1
    bank_detail: list[Any] = []
    if bank_ok:
        for row in bank_files:
            path = root / str(row.get("path"))
            raw = _raw_sha(path)
            count = len(read_jsonl(path)) if path.is_file() else -1
            ok = raw is not None and raw == str(row.get("sha256")) and count == int(row.get("episodes"))
            bank_detail.append({"path": row.get("path"), "ok": bool(ok), "count": count})
            bank_ok = bank_ok and ok
    _check(checks, "episode_bank_files", bank_ok, bank_detail)
    models = model_manifest.get("models") if isinstance(model_manifest, Mapping) else None
    model_ok = isinstance(models, list) and len(models) >= 2
    model_detail: list[Any] = []
    if model_ok:
        seen: set[tuple[str, int]] = set()
        for row in models:
            if not isinstance(row, Mapping) or set(row) != set(sp.S3_MODEL_ENTRY_FIELDS):
                model_ok = False
                model_detail.append({"row": row, "error": "字段集不符"})
                continue
            key = (str(row["arm_type"]), int(row["meta_seed"]))
            if key in seen:
                model_ok = False
                model_detail.append({"row": row, "error": "重复 (arm_type, meta_seed)"})
                continue
            seen.add(key)
            rel_path = str(row.get("path"))
            path = root / rel_path
            if not path.is_file() and repo_root is not None:
                path = Path(repo_root) / rel_path
            raw = _raw_sha(path)
            if raw != str(row.get("sha256")):
                model_ok = False
            model_detail.append({"path": row.get("path"), "ok": raw == str(row.get("sha256"))})
    _check(checks, "model_manifest_models", model_ok, model_detail)
    if run_mode == "FORMAL":
        verification = model_manifest.get("verification") if isinstance(model_manifest, Mapping) else None
        formal_model_ok = (
            isinstance(verification, Mapping)
            and verification.get("loaded_from_prereg") is True
            and isinstance(verification.get("verified_utc"), str)
            and len(str(verification.get("prereg_models_sha256", ""))) == 64
        )
        if formal_model_ok and prereg is not None:
            formal_model_ok = verification.get("prereg_models_sha256") == sp.canonical_sha256(prereg.get("models") or {})
            frozen_sha: dict[tuple[str, int], str] = {}
            for kind in sp.S3_MODEL_KINDS:
                for row in ((prereg.get("models") or {}).get(kind) or {}).get("models", []):
                    frozen_sha[(str(kind), int(row["meta_seed"]))] = str(row["sha256"])
            if isinstance(models, list):
                for row in models:
                    if isinstance(row, Mapping) and set(row) == set(sp.S3_MODEL_ENTRY_FIELDS):
                        key = (str(row["arm_type"]), int(row["meta_seed"]))
                        if frozen_sha.get(key) != str(row["sha256"]):
                            formal_model_ok = False
        _check(checks, "formal_model_manifest", formal_model_ok, {"verification": verification})
    config_gate = config.get("fd_or_gradient_gate") or {}
    expected_per_model: int | None = None
    if isinstance(config_gate, Mapping):
        raw_expected = config_gate.get("coordinates_per_model")
        if type(raw_expected) is int and raw_expected > 0:
            expected_per_model = int(raw_expected)
    if run_mode == "FORMAL":
        expected_per_model = int(sp.S3_FD_GATE_COORDINATES_PER_MODEL)
    gate_ok = isinstance(gate, Mapping)
    gate_detail: dict[str, Any] = {}
    if gate_ok:
        try:
            verify_fd_gate_payload(gate, run_mode=run_mode, expected_per_model=expected_per_model)
        except S3RunnerError as exc:
            gate_ok = False
            gate_detail["error"] = str(exc)
        if gate_ok and isinstance(config_gate, Mapping):
            gate_ok = (
                str(config_gate.get("sha256")) == str(_raw_sha(root / S3_RUNNER_GATE_FILE))
                and int(config_gate.get("coordinates_per_model", -1)) == int(gate["coordinates_per_model"])
                and int(config_gate.get("coordinates_total", -1)) == int(gate["coordinates_total"])
                and str(config_gate.get("mode")) == run_mode
                and set(config_gate.get("models") or {}) == set(sp.S3_FD_GATE_MODEL_KEYS)
            )
            gate_detail["config_consistent"] = bool(gate_ok)
    else:
        gate_detail["error"] = "gate 不是 mapping"
    _check(checks, "gate_payload", gate_ok, gate_detail)
    gate_sha = _raw_sha(root / S3_RUNNER_GATE_FILE)
    _check(checks, "gate_sha_binding", gate_sha is not None and gate_sha == config_gate.get("sha256") and gate_sha == summary.get("fd_or_gradient_gate_sha256"), None)
    if run_mode == "FORMAL" and repo_root is not None:
        frozen_gate_sha = _raw_sha(Path(repo_root) / sp.S3_GATE_RELPATH)
        _check(checks, "formal_gate_matches_repo", frozen_gate_sha is not None and frozen_gate_sha == gate_sha, {"repo": frozen_gate_sha, "run": gate_sha})
    if run_mode == "FORMAL":
        prereg_gate_sha = str((prereg or {}).get("fd_gate_sha256") or "")
        _check(
            checks,
            "formal_gate_prereg_binding",
            bool(prereg_gate_sha) and gate_sha == prereg_gate_sha,
            {"prereg": prereg_gate_sha, "run": gate_sha},
        )
    execution_fields_ok = isinstance(execution_report, Mapping) and set(execution_report) == set(S3_EXECUTION_REPORT_FIELDS)
    _check(checks, "execution_report_fields", execution_fields_ok, sorted(set(execution_report) ^ set(S3_EXECUTION_REPORT_FIELDS)) if isinstance(execution_report, Mapping) else type(execution_report).__name__)
    _check(checks, "execution_report_schema", isinstance(execution_report, Mapping) and execution_report.get("schema_version") == S3_EXECUTION_REPORT_SCHEMA_VERSION, None if not isinstance(execution_report, Mapping) else execution_report.get("schema_version"))
    execution_values_ok = False
    if execution_fields_ok:
        per_shard = execution_report["per_shard_counts"]
        execution_values_ok = (
            execution_report["physical_call_count"] == 0
            and isinstance(per_shard, list)
            and len(per_shard) == int(execution_report["parallel_workers"])
            and int(execution_report["run_count_completed"]) <= int(execution_report["run_count_requested"])
            and float(execution_report["sum_run_wall_seconds"]) >= float(execution_report["max_run_wall_s"])
            and int(execution_report["sum_run_wall_limit_s"]) == int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"])
            and execution_report["stop_reason"] in (None, "RESOURCE_LIMIT", "DEADLINE_EXCEEDED", S3_RUNNER_SUM_RUN_WALL_LIMIT)
        )
    _check(checks, "execution_report_values", execution_values_ok, None)
    artifacts_map = data_manifest.get("artifact_sha256") if isinstance(data_manifest, Mapping) else None
    _check(checks, "execution_report_sha_binding", isinstance(artifacts_map, Mapping) and artifacts_map.get(S3_RUNNER_EXECUTION_REPORT_FILE) == _raw_sha(root / S3_RUNNER_EXECUTION_REPORT_FILE), None)
    if run_mode == "FORMAL":
        stream_artifact_names = [S3_RUNNER_NC_RECORDS_FILE, S3_RUNNER_OOD_RECORDS_FILE, S3_RUNNER_DET_CHECK_FILE] + [
            _det_record_relpath(index) for index in range(1, int(sp.S3_DETERMINISM_REPEATS) + 1)
        ]
        stream_artifacts_ok = isinstance(artifacts_map, Mapping) and all(
            artifacts_map.get(name) == _raw_sha(root / name) for name in stream_artifact_names
        )
        _check(checks, "record_stream_artifact_sha", early_stop or stream_artifacts_ok, {"early_stop": early_stop})
    train_fields, eval_fields = _record_field_sets()
    record_ok = True
    record_detail: list[Any] = []
    train_count = 0
    eval_count = 0
    budget_by_run: dict[str, int] = {}
    sources_by_run: dict[str, dict[str, int]] = {}
    digests_ok = True
    for position, record in enumerate(records):
        if set(record) == train_fields:
            train_count += 1
            if record.get("record_digest") != train_record_digest(record):
                digests_ok = False
        elif set(record) == eval_fields:
            eval_count += 1
            run_id = str(record["run_id"])
            budget_by_run[run_id] = int(record["budget"])
            bucket = sources_by_run.setdefault(run_id, {})
            source = str(record["source"])
            bucket[source] = bucket.get(source, 0) + 1
            if record.get("record_digest") != eval_record_digest(record):
                digests_ok = False
        else:
            record_ok = False
            record_detail.append({"position": position, "keys": sorted(record)})
    _check(checks, "record_field_sets", record_ok, record_detail[:5])
    _check(checks, "record_digests", digests_ok, None)
    nc_rows: list[dict[str, Any]] = []
    ood_rows: list[dict[str, Any]] = []
    det_streams: list[list[dict[str, Any]]] = []
    stream_rows_ok = True
    stream_detail: dict[str, Any] = {}
    if run_mode == "FORMAL" and not early_stop:
        nc_rows = read_jsonl(root / S3_RUNNER_NC_RECORDS_FILE)
        ood_rows = read_jsonl(root / S3_RUNNER_OOD_RECORDS_FILE)
        for stream, rows, split, phase in (
            ("nc", nc_rows, "meta_test_negative_control", "NEGATIVE_CONTROL"),
            ("ood", ood_rows, "meta_test_ood", "OOD"),
        ):
            ok = all(set(row) == eval_fields and row.get("record_digest") == eval_record_digest(row) for row in rows)
            if ok:
                ok = all(
                    str(row.get("split")) == split
                    and str(row.get("phase")) == phase
                    and row.get("holdout_truth_read") is True
                    for row in rows
                )
            stream_rows_ok = stream_rows_ok and ok
            stream_detail[stream] = {"rows": len(rows), "ok": bool(ok)}
        for repeat in range(1, int(sp.S3_DETERMINISM_REPEATS) + 1):
            relpath = _det_record_relpath(repeat)
            rows = read_jsonl(root / relpath) if (root / relpath).is_file() else []
            det_streams.append(rows)
            ok = all(set(row) == eval_fields and row.get("record_digest") == eval_record_digest(row) for row in rows)
            if ok:
                ok = all(
                    str(row.get("split")) == "meta_test"
                    and str(row.get("phase")) == "EVAL"
                    and row.get("holdout_truth_read") is True
                    for row in rows
                )
            stream_rows_ok = stream_rows_ok and ok
            stream_detail["det_r" + str(repeat)] = {"rows": len(rows), "ok": bool(ok)}
        _check(checks, "record_stream_rows", stream_rows_ok, stream_detail)
        grid_meta = config.get("evaluation_grid") or {}
        main_evals_expected = int(grid_meta.get("main_evals", -1))
        main_runs_expected = int(grid_meta.get("main_runs", -1))
        per_run_evals = main_evals_expected // main_runs_expected if main_runs_expected > 0 else -1
        expected_det_evals = int(sp.S3_DETERMINISM_SUBSET_RUNS) * int(per_run_evals) if per_run_evals > 0 else -1
        counts_ok = (
            per_run_evals > 0
            and len(nc_rows) == int(sp.S3_NEGATIVE_CONTROL_EVALS)
            and len(ood_rows) == int(sp.S3_OOD_EVALS)
            and all(len(rows) == expected_det_evals for rows in det_streams)
            and sum(len(rows) for rows in det_streams) == int(sp.S3_DETERMINISM_EVALS)
        )
        _check(
            checks,
            "record_stream_counts",
            counts_ok,
            {"per_run_evals": per_run_evals, "nc": len(nc_rows), "ood": len(ood_rows), "det": [len(rows) for rows in det_streams]},
        )
        det_check = read_json_file(root / S3_RUNNER_DET_CHECK_FILE) if (root / S3_RUNNER_DET_CHECK_FILE).is_file() else {}
        det_ok = (
            isinstance(det_check, Mapping)
            and det_check.get("subset_runs") == int(sp.S3_DETERMINISM_SUBSET_RUNS)
            and det_check.get("record_core_equal") is True
        )
        if det_ok and prereg is not None:
            expected_subset_sha = str((prereg.get("determinism") or {}).get("subset_run_keys_sha256") or "")
            det_ok = bool(expected_subset_sha) and det_check.get("subset_run_keys_sha256") == expected_subset_sha
        _check(checks, "determinism_check_binding", bool(det_ok), {"subset_runs": det_check.get("subset_runs") if isinstance(det_check, Mapping) else None})
    for run_id, budget in budget_by_run.items():
        bucket = sources_by_run.get(run_id, {})
        expected_support = int(sp.S3_K_SHOT)
        expected_initial = int(sp.S3_INITIAL_DESIGN_COUNT) - int(sp.S3_K_SHOT)
        total = sum(bucket.values())
        if total != budget or bucket.get("support", 0) != expected_support or bucket.get("initial", 0) != expected_initial:
            _check(checks, "budget_distribution", False, {"run_id": run_id, "bucket": bucket, "budget": budget})
            break
    else:
        _check(checks, "budget_distribution", True, None)
    stream_eval_total = int(eval_count + sum(len(rows) for rows in det_streams) + len(nc_rows) + len(ood_rows))
    actual_counts = {"train": train_count, "eval": stream_eval_total, "total": train_count + stream_eval_total}
    config_counts = config.get("record_counts") or {}
    _check(checks, "record_counts_vs_config", actual_counts == {key: int(config_counts.get(key, -1)) for key in ("train", "eval", "total")}, {"actual": actual_counts, "config": config_counts})
    _check(checks, "record_counts_vs_summary", actual_counts == {key: int((summary.get("record_counts") or {}).get(key, -1)) for key in ("train", "eval", "total")}, summary.get("record_counts"))
    _check(
        checks,
        "record_counts_config_summary_equal",
        dict(config.get("record_counts") or {}) == dict(summary.get("record_counts") or {}),
        {"config": config.get("record_counts"), "summary": summary.get("record_counts")},
    )
    _check(checks, "synthetic_call_count_binding", int(data_manifest.get("synthetic_call_count", -1)) == actual_counts["eval"], None)
    if run_mode == "FORMAL":
        train_bucket = (summary.get("status_counts") or {}).get("train") or {}
        _check(
            checks,
            "formal_train_zero",
            actual_counts["train"] == 0
            and int(train_bucket.get("OK", -1)) == 0
            and int(train_bucket.get("FAILED", -1)) == 0,
            {"records": actual_counts["train"], "status_counts": train_bucket},
        )
    status_counts = summary.get("status_counts") or {}
    _check(
        checks,
        "status_counts_shape",
        isinstance(status_counts, Mapping)
        and set(status_counts) == {"train", "eval"}
        and all(set(status_counts[bucket]) == set(sp.S3_RECORD_STATUSES) for bucket in ("train", "eval")),
        status_counts,
    )
    expected_status = _status_counts(
        list(records)
        + list(nc_rows)
        + list(ood_rows)
        + [row for rows in det_streams for row in rows]
    )
    _check(checks, "status_counts_equal", isinstance(status_counts, Mapping) and dict(status_counts) == expected_status, {"expected": expected_status})
    grid = config.get("evaluation_grid") or {}
    eval_run_ids = set(budget_by_run)
    expected_main_runs = int(grid.get("main_runs", -1))
    eval_run_count_ok = len(eval_run_ids) == expected_main_runs or (
        early_stop and 0 <= len(eval_run_ids) <= expected_main_runs
    )
    _check(checks, "eval_run_count", eval_run_count_ok, {"actual": len(eval_run_ids), "expected": expected_main_runs, "early_stop": early_stop})
    train_expected = 2 * len(config.get("seeds", {}).get("meta_seeds") or [])
    _check(checks, "train_record_count_formula", False, None)  # 占位，下面用真实值覆盖
    del checks["train_record_count_formula"]
    resources = summary.get("resources") or {}
    _check(checks, "summary_resources", isinstance(resources, Mapping) and {"total_wall_s", "max_wall_s", "max_peak_memory_mb", "sum_run_wall_seconds", "sum_run_wall_limit_s", "auxiliary_compute", "resource_limits"} <= set(resources), sorted(resources) if isinstance(resources, Mapping) else resources)
    _check(checks, "resource_limits_fixed", isinstance(resources, Mapping) and dict(resources.get("resource_limits") or {}) == dict(sp.S3_RESOURCE_LIMITS), None)
    _check(checks, "sum_run_wall_limit_fixed", isinstance(resources, Mapping) and int(resources.get("sum_run_wall_limit_s", -1)) == int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]) and isinstance(execution_report, Mapping) and int(execution_report.get("sum_run_wall_limit_s", -1)) == int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]), None)
    consistency_ok = False
    consistency_detail: dict[str, Any] = {}
    if isinstance(execution_report, Mapping) and isinstance(resources, Mapping):
        try:
            consistency_ok = (
                execution_report.get("stop_reason") == resources.get("stop_reason")
                and float(execution_report.get("sum_run_wall_seconds")) == float(resources.get("sum_run_wall_seconds"))
                and int(execution_report.get("parallel_workers")) == int(resources.get("parallel_workers"))
            )
            consistency_detail = {
                "stop_reason": [execution_report.get("stop_reason"), resources.get("stop_reason")],
                "sum_run_wall_seconds": [execution_report.get("sum_run_wall_seconds"), resources.get("sum_run_wall_seconds")],
                "parallel_workers": [execution_report.get("parallel_workers"), resources.get("parallel_workers")],
            }
        except (TypeError, ValueError):
            consistency_ok = False
    _check(checks, "execution_report_summary_consistency", consistency_ok, consistency_detail)
    _check(checks, "data_manifest_fields", set(data_manifest) == set(sp.S3_DATA_MANIFEST_FIELDS), sorted(set(data_manifest) ^ set(sp.S3_DATA_MANIFEST_FIELDS)))
    split_ids = data_manifest.get("split_task_ids") or {}
    split_ok = isinstance(split_ids, Mapping) and set(split_ids) == set(sp.S3_ALLOWED_SPLITS)
    _check(checks, "data_manifest_splits_allowed", split_ok, sorted(split_ids) if isinstance(split_ids, Mapping) else split_ids)
    if split_ok:
        _check(checks, "data_manifest_split_counts", all(len(split_ids[split]) == int(sp.S3_SPLIT_COUNTS[split]) for split in sp.S3_SPLIT_COUNTS), {split: len(split_ids[split]) for split in sp.S3_SPLIT_COUNTS})
    _check(checks, "data_manifest_sha_binding", summary.get("data_manifest_sha256") == _raw_sha(root / S3_RUNNER_DATA_MANIFEST_FILE), None)
    per_run = summary.get("per_run")
    if isinstance(per_run, list) and per_run and all(isinstance(row, Mapping) and "s3_provenance" in row for row in per_run):
        try:
            fairness_rows = list(per_run)
            if early_stop:
                # 资源早停时记录只含实际完成 run，一个臂组可能没有跑满 5 臂；
                # 公平性断言只对完整臂组生效，不完整组在 detail 中披露（不伪造、不放宽正常路径）。
                group_counts: dict[tuple[Any, ...], int] = {}
                keys: list[tuple[Any, ...]] = []
                for row in fairness_rows:
                    key = (
                        str(row.get("task_id")),
                        int(row.get("budget", -1)),
                        int(row.get("opt_seed", -1)),
                        int(row.get("meta_seed", -1)),
                    )
                    keys.append(key)
                    group_counts[key] = group_counts.get(key, 0) + 1
                fairness_rows = [
                    row
                    for row, key in zip(fairness_rows, keys)
                    if group_counts[key] == len(m5_arms.S3_ARM_IDS)
                ]
            if fairness_rows:
                fairness = m5_arms.s3_fairness_report(fairness_rows)
                _check(checks, "fairness", bool(fairness.get("ok")), fairness.get("problems"))
            else:
                _check(
                    checks,
                    "fairness",
                    bool(early_stop),
                    {"early_stop": True, "complete_groups": 0, "rows": len(per_run), "detail": "无完整臂组可断言"},
                )
        except Exception as exc:
            _check(checks, "fairness", False, type(exc).__name__ + ": " + str(exc))
    else:
        _check(checks, "fairness", False, "per_run 缺失或缺少 s3_provenance")
    ok = all(bool(entry["ok"]) for entry in checks.values())
    return {"ok": bool(ok), "checks": checks, "record_counts": actual_counts, "run_status": summary.get("status")}


def _record_core_list(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    core: list[dict[str, Any]] = []
    for record in records:
        train_fields, _eval_fields = _record_field_sets()
        excluded = ("wall_s", "peak_memory_mb", "record_digest")
        core.append({key: value for key, value in record.items() if key not in excluded})
    return core


def compare_deterministic_runs(dir_a: str | Path, dir_b: str | Path) -> dict[str, Any]:
    root_a = Path(dir_a)
    root_b = Path(dir_b)
    config_bytes_a = (root_a / S3_RUNNER_CONFIG_FILE).read_bytes()
    config_bytes_b = (root_b / S3_RUNNER_CONFIG_FILE).read_bytes()
    config_a = read_json_file(root_a / S3_RUNNER_CONFIG_FILE)
    config_b = read_json_file(root_b / S3_RUNNER_CONFIG_FILE)
    records_a = read_jsonl(root_a / S3_RUNNER_RECORD_FILE)
    records_b = read_jsonl(root_b / S3_RUNNER_RECORD_FILE)
    manifest_a = read_json_file(root_a / S3_RUNNER_MODEL_MANIFEST_FILE)
    manifest_b = read_json_file(root_b / S3_RUNNER_MODEL_MANIFEST_FILE)
    gate_sha_a = _raw_sha(root_a / S3_RUNNER_GATE_FILE)
    gate_sha_b = _raw_sha(root_b / S3_RUNNER_GATE_FILE)
    sha_a = {
        str(row.get("path")): str(row.get("sha256"))
        for row in (manifest_a.get("models") or [])
        if isinstance(row, Mapping)
    }
    sha_b = {
        str(row.get("path")): str(row.get("sha256"))
        for row in (manifest_b.get("models") or [])
        if isinstance(row, Mapping)
    }
    core_a = _record_core_list(records_a)
    core_b = _record_core_list(records_b)
    payload = {
        "run_config_byte_identical": config_bytes_a == config_bytes_b,
        "episode_bank_sha256_equal": (config_a.get("episode_bank") or {}).get("banks") == (config_b.get("episode_bank") or {}).get("banks"),
        "model_sha256_equal": sha_a == sha_b,
        "fd_gate_sha256_equal": gate_sha_a == gate_sha_b,
        "record_core_equal": core_a == core_b,
        "record_counts_equal": (config_a.get("record_counts") or {}) == (config_b.get("record_counts") or {}),
        "record_core_sha256": sp.canonical_sha256(core_a),
    }
    payload["ok"] = all(bool(payload[key]) for key in ("run_config_byte_identical", "episode_bank_sha256_equal", "model_sha256_equal", "fd_gate_sha256_equal", "record_core_equal", "record_counts_equal"))
    return payload


# ---------------------------------------------------------------------------
# 运行编排
# ---------------------------------------------------------------------------
def _resolve_prereg_and_family(
    *,
    prereg_path: str | Path,
    repo_root: Path,
    run_mode: str,
    smoke_overrides: Mapping[str, Any] | None,
    verify_code_sha: bool | None,
) -> dict[str, Any]:
    prereg = sp.read_preregistration(Path(prereg_path))
    if verify_code_sha is None:
        verify_code_sha = run_mode == "FORMAL"
    sp.verify_preregistration(
        prereg,
        repo_root=repo_root,
        verify_code_sha=bool(verify_code_sha),
        verify_hash_vectors=True,
        verify_artifacts=True,
    )
    budget = resolve_budget(run_mode=run_mode, prereg=prereg, smoke_overrides=smoke_overrides)
    package = load_family_package(repo_root / sp.S3_FAMILY_PACKAGE_RELPATH)
    family = prereg.get("family") or {}
    _require(
        str(family.get("family_package_sha256")) == package["sha256"],
        S3_RUNNER_PREREG_ERROR,
        "族包与 prereg 不一致",
    )
    _require(
        str(family.get("task_ids_sha256")) == package["task_ids_sha256"],
        S3_RUNNER_PREREG_ERROR,
        "族 task_ids_sha256 与 prereg 不一致",
    )
    return {"prereg": prereg, "budget": budget, "package": package}


def _prepare_artifacts(
    *,
    out: Path,
    run_id: str,
    run_mode: str,
    prereg: Mapping[str, Any],
    budget: Mapping[str, Any],
    package: Mapping[str, Any],
    repo_root: Path,
    created_utc: str,
) -> dict[str, Any]:
    by_split = package["by_split"]
    design_cache = family_design_cache(package["tasks"])
    tasks_by_id = {task.task_id: task for task in package["tasks"]}
    models_dir = out / S3_RUNNER_MODELS_DIR
    models_dir.mkdir(parents=True, exist_ok=True)
    if run_mode == "FORMAL":
        # R-S3-07 Q1/Q2/Q3：FORMAL 只加载 M2 冻结产物，不训练、不重算 FD 门。
        episode_banks = load_frozen_episode_banks(
            repo_root=repo_root, prereg=prereg, meta_seeds=budget["meta_seeds"]
        )
        for seed, bank in episode_banks.items():
            target = models_dir / ("episode_bank_meta_" + str(int(seed)) + ".jsonl")
            target.write_bytes(bank["raw"])
            _require(
                sp.sha256_file(target) == str(bank["sha256"]),
                S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
                "冻结 episode bank 复制后 sha 不一致",
            )
        models = load_frozen_models(repo_root=repo_root, prereg=prereg, meta_seeds=budget["meta_seeds"])
        frozen_manifest = load_frozen_model_manifest(
            repo_root=repo_root,
            prereg=prereg,
            models=models,
            episode_banks=episode_banks,
            run_id=str(run_id),
            created_utc=str(created_utc),
            out=out,
        )
        gate = load_frozen_gate(repo_root=repo_root, prereg=prereg, run_mode="FORMAL")
        gate_data = (Path(repo_root) / sp.S3_GATE_RELPATH).read_bytes()
        (out / S3_RUNNER_GATE_FILE).write_bytes(gate_data)
        _require(
            sp.sha256_file(out / S3_RUNNER_GATE_FILE) == str(gate["sha256"]),
            S3_RUNNER_FROZEN_ARTIFACT_MISMATCH,
            "冻结 FD 门复制后 sha 不一致",
        )
        gate = dict(gate)
        gate["path"] = S3_RUNNER_GATE_FILE
        train = {
            "models": models,
            "entries": frozen_manifest["entries"],
            "manifest": frozen_manifest["manifest"],
            "train_records": [],
            "per_seed_resources": [],
        }
        return {
            "by_split": by_split,
            "design_cache": design_cache,
            "tasks_by_id": tasks_by_id,
            "train_tasks": [],
            "episode_banks": episode_banks,
            "train": train,
            "model_manifest": frozen_manifest["manifest"],
            "model_manifest_info": frozen_manifest["info"],
            "gate": gate,
        }
    train_tasks = prepare_training_tasks(run_mode=run_mode, by_split=by_split)
    episode_banks = prepare_episode_banks(
        run_mode=run_mode,
        models_dir=models_dir,
        train_tasks=train_tasks,
        meta_seeds=budget["meta_seeds"],
        outer_steps=int(budget["outer_steps"]),
        design_cache=design_cache,
    )
    train = train_models(
        run_mode=run_mode,
        run_id=run_id,
        models_dir=models_dir,
        train_tasks=train_tasks,
        meta_seeds=budget["meta_seeds"],
        outer_steps=int(budget["outer_steps"]),
        episode_banks=episode_banks,
        design_cache=design_cache,
        prereg=prereg,
        repo_root=repo_root,
    )
    model_manifest_info = write_json_canonical(out / S3_RUNNER_MODEL_MANIFEST_FILE, train["manifest"])
    gate = build_gradient_gate(
        run_mode=run_mode,
        gate_path=out / S3_RUNNER_GATE_FILE,
        created_utc=str(created_utc),
        prereg=prereg,
        models=train["models"],
        episode_banks=episode_banks,
        design_cache=design_cache,
        tasks_by_id=tasks_by_id,
        fd_coordinates=int(budget["fd_coordinates"]),
    )
    return {
        "by_split": by_split,
        "design_cache": design_cache,
        "tasks_by_id": tasks_by_id,
        "train_tasks": train_tasks,
        "episode_banks": episode_banks,
        "train": train,
        "model_manifest": train["manifest"],
        "model_manifest_info": model_manifest_info,
        "gate": gate,
    }


def _eval_tasks_for(
    *,
    run_mode: str,
    by_split: Mapping[str, Sequence[tf.S3ConflictTask]],
    eval_tasks: int,
) -> list[tf.S3ConflictTask]:
    split = "meta_validation" if run_mode == "SMOKE" else "meta_test"
    tasks = list(by_split[split])
    _require(len(tasks) >= int(eval_tasks), S3_RUNNER_DATA_BOUNDARY_ERROR, "评估任务不足: " + str(split))
    return tasks[: int(eval_tasks)]


def _environment() -> dict[str, Any]:
    torch_version = "unavailable"
    try:
        import torch  # type: ignore

        torch_version = str(torch.__version__)
    except Exception:
        torch_version = "unavailable"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "torch": torch_version,
        "thread_env": {name: os.environ.get(name) for name in S3_THREAD_ENV_VARS},
        "runner_schema_version": S3_RUNNER_SCHEMA_VERSION,
    }


def _outer_step_timing(train: Mapping[str, Any]) -> list[dict[str, Any]]:
    timings: list[dict[str, Any]] = []
    for row in train["per_seed_resources"]:
        timings.append(
            {
                "arm_type": str(row["arm_type"]),
                "meta_seed": int(row["meta_seed"]),
                "outer_step_wall_s_estimate": float(row["train_wall_s"]) / max(1, int(row["steps"])),
                "steps": int(row["steps"]),
            }
        )
    return timings


def build_final_execution_report(
    main_report: Mapping[str, Any],
    *,
    stop_reason: str | None,
    sum_run_wall_seconds: float,
    max_run_wall_s: float,
    max_peak_memory_mb: float,
    campaign_wall_s: float,
) -> dict[str, Any]:
    """把 main campaign 报告扩展为整个 run 的最终 execution_report（A5-S3M1-m03）。

    18 字段 schema/顺序不变，只把 stop_reason/Σrun wall/max run wall/max peak/
    campaign wall 覆盖为全部已执行 campaign 的最终口径；落盘只写这一次最终版，
    且与 run_summary.resources 的 stop_reason/sum_run_wall_seconds/parallel_workers
    完全一致。
    """
    report = dict(main_report)
    report["campaign_wall_s"] = _round6(float(campaign_wall_s))
    report["sum_run_wall_seconds"] = _round6(float(sum_run_wall_seconds))
    report["max_run_wall_s"] = _round6(float(max_run_wall_s))
    report["max_peak_memory_mb"] = _round6(float(max_peak_memory_mb))
    report["stop_reason"] = None if stop_reason is None else str(stop_reason)
    report["parallel_note"] = (
        "run 级并行仅执行层；分片为账目口径（shard=sha256(canonical(run_key))%W，"
        "仅用于 execution_report.per_shard_counts/shard_runs_sha256），实际执行为有界并发"
        "有序合并（W=1 串行；W>1 spawn 池 imap_unordered(chunksize=1) 逐结果消费、超限 terminate）；"
        "worker 编号不进入 RNG/记录/digest；合并顺序按 run_key 规范排序；"
        "sum_run_wall_seconds=Σ(全部已执行 campaign 的逐 run wall_s)；campaign_wall_s=Σ(各 campaign 墙钟)"
    )
    _require(tuple(report) == S3_EXECUTION_REPORT_FIELDS, S3_RUNNER_VALIDATION_ERROR, "最终 execution_report 字段集/顺序不符")
    return report


def run_experiment(
    *,
    out_dir: str | Path,
    run_id: str,
    prereg_path: str | Path,
    repo_root: str | Path | None = None,
    run_mode: str = "FORMAL",
    smoke_overrides: Mapping[str, Any] | None = None,
    parallel_workers: int = S3_RUNNER_DEFAULT_WORKERS,
    created_utc: str | None = None,
    verify_code_sha: bool | None = None,
    campaign_authorization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """完整 S3 run：准备模型/bank/梯度门 → 主 campaign（可选负控/OOD/确定性） → 产物 + 校验。"""
    _require(run_mode in S3_RUNNER_EXECUTION_MODES, S3_RUNNER_ERROR, "run_mode 非法")
    auth = validate_campaign_authorization(run_mode, campaign_authorization)
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    out = Path(out_dir)
    _require(not (out / S3_RUNNER_CONFIG_FILE).exists(), S3_RUNNER_FILE_ERROR, "run 目录已有产物: " + str(out))
    out.mkdir(parents=True, exist_ok=True)
    resolved = _resolve_prereg_and_family(
        prereg_path=prereg_path,
        repo_root=root,
        run_mode=run_mode,
        smoke_overrides=smoke_overrides,
        verify_code_sha=verify_code_sha,
    )
    prereg = resolved["prereg"]
    budget = resolved["budget"]
    package = resolved["package"]
    prepared = _prepare_artifacts(
        out=out,
        run_id=str(run_id),
        run_mode=run_mode,
        prereg=prereg,
        budget=budget,
        package=package,
        repo_root=root,
        created_utc=str(created_utc or utc_now()),
    )
    by_split = prepared["by_split"]
    design_cache = prepared["design_cache"]
    tasks_by_id = prepared["tasks_by_id"]
    train = prepared["train"]
    state = worker_payload_for_state(models=train["models"], tasks=tasks_by_id, prereg=prereg)
    eval_tasks = _eval_tasks_for(run_mode=run_mode, by_split=by_split, eval_tasks=int(budget["eval_tasks"]))
    main_specs = build_main_run_specs(
        tasks=eval_tasks,
        meta_seeds=budget["meta_seeds"],
        opt_seeds=budget["opt_seeds"],
        budgets=budget["budgets"],
        eval_task_count=len(eval_tasks),
    )
    main = execute_campaign(main_specs, workers=int(parallel_workers), state=state, campaign_id=str(run_id), run_mode=run_mode)
    main_results = main["results"]
    main_stop_reason = main["execution_report"].get("stop_reason")
    if main_stop_reason is not None:
        main_stop_reason = str(main_stop_reason)
    # A5-S3M1-m02：main campaign 未资源停止时必须全 OK，否则 fail-closed（不再保留死变量）
    enforces_ok = all(result.get("status") == "OK" for result in main_results)
    _require(
        main_stop_reason is not None or enforces_ok,
        S3_RUNNER_RESOURCE_ERROR,
        "main campaign 未资源停止但存在非 OK run: "
        + repr([
            {"run_id": result["run"].get("run_id"), "status": result.get("status"), "error": result.get("error")}
            for result in main_results
            if result.get("status") != "OK"
        ]),
    )
    eval_records = [record for result in main_results for record in result.get("records", [])]
    train_records = list(train["train_records"])
    failures = [
        {"run_id": result["run"].get("run_id"), "status": result.get("status"), "error": result.get("error")}
        for result in main_results
        if result.get("status") != "OK"
    ]
    campaign_walls: list[float] = [float(main["execution_report"]["campaign_wall_s"])]
    campaign_peaks: list[float] = [float(main["execution_report"]["max_peak_memory_mb"])]
    campaign_max_run_walls: list[float] = [float(main["execution_report"]["max_run_wall_s"])]
    campaign_sum_run_walls: list[float] = [float(main["execution_report"]["sum_run_wall_seconds"])]
    campaign_stop_reasons: list[Any] = []
    aux_records: dict[str, list[dict[str, Any]]] = {}
    det_streams: list[list[dict[str, Any]]] = []
    negative_controls: dict[str, Any] = {"executed": False, "reason": "SMOKE 不执行负控/OOD/确定性子集"}
    determinism: dict[str, Any] = {
        "mode": run_mode,
        "reruns": 0,
        "executed": False,
        "record_digest_excluded_fields": ["wall_s", "peak_memory_mb", "record_digest"],
        "byte_identical_artifacts": [
            "run_config.json",
            "episode_bank_sha256",
            "model_sha256",
            "fd_or_gradient_gate_sha256",
            "record_core",
        ],
    }
    aux_runs = 0
    run_stop_reason: str | None = main_stop_reason
    total_sum_run_wall = float(main["execution_report"]["sum_run_wall_seconds"])
    if run_mode == "FORMAL":
        nc_tasks = list(by_split["meta_test_negative_control"])
        ood_tasks = list(by_split["meta_test_ood"])
        nc_specs = build_aux_run_specs(
            tasks=nc_tasks,
            phase="NEGATIVE_CONTROL",
            budgets=budget["budgets"],
            opt_seeds=list(budget["opt_seeds"])[:3],
            meta_seeds=[0],
        )
        ood_specs = build_aux_run_specs(
            tasks=ood_tasks,
            phase="OOD",
            budgets=budget["budgets"],
            opt_seeds=list(budget["opt_seeds"])[:3],
            meta_seeds=[0],
        )
        det_specs = select_determinism_specs(main_specs, prereg=prereg)
        det_count = int(len(det_specs))
        main_by_run_id = {result["run"].get("run_id"): result for result in main_results}
        det_streams = []
        det_core: list[list[dict[str, Any]]] = []

        def _record_campaign(campaign: Mapping[str, Any]) -> str | None:
            """记录一个已执行 campaign 的资源账目并返回其 stop_reason（A5-S3M1-m03）。"""
            nonlocal total_sum_run_wall, aux_runs
            report = campaign["execution_report"]
            campaign_walls.append(float(report["campaign_wall_s"]))
            campaign_peaks.append(float(report["max_peak_memory_mb"]))
            campaign_max_run_walls.append(float(report["max_run_wall_s"]))
            campaign_sum_run_walls.append(float(report["sum_run_wall_seconds"]))
            total_sum_run_wall = total_sum_run_wall + float(report["sum_run_wall_seconds"])
            aux_runs = aux_runs + len(campaign.get("results") or [])
            reason = report.get("stop_reason")
            if reason is not None:
                campaign_stop_reasons.append(reason)
                return str(reason)
            return None

        # A5-S3M1-M01：任一 campaign 资源停止后不再启动后续 campaign。
        if run_stop_reason is None:
            nc = execute_campaign(
                nc_specs,
                workers=int(parallel_workers),
                state=state,
                campaign_id=str(run_id) + "--NC",
                run_mode=run_mode,
                prior_sum_run_wall_s=total_sum_run_wall,
            )
            aux_records["negative_control"] = [record for result in nc["results"] for record in result.get("records", [])]
            negative_controls = {
                "executed": True,
                "runs": len(nc["results"]),
                "records": len(aux_records["negative_control"]),
                "ood_runs": 0,
                "ood_records": 0,
                "failures": len([result for result in nc["results"] if result.get("status") != "OK"]),
            }
            run_stop_reason = _record_campaign(nc)
        if run_stop_reason is None:
            ood = execute_campaign(
                ood_specs,
                workers=int(parallel_workers),
                state=state,
                campaign_id=str(run_id) + "--OOD",
                run_mode=run_mode,
                prior_sum_run_wall_s=total_sum_run_wall,
            )
            aux_records["ood"] = [record for result in ood["results"] for record in result.get("records", [])]
            negative_controls["executed"] = True
            negative_controls["ood_runs"] = len(ood["results"])
            negative_controls["ood_records"] = len(aux_records["ood"])
            negative_controls["failures"] = int(negative_controls.get("failures", 0)) + len(
                [result for result in ood["results"] if result.get("status") != "OK"]
            )
            run_stop_reason = _record_campaign(ood)
        if run_stop_reason is not None and not negative_controls.get("executed"):
            negative_controls = {"executed": False, "reason": "资源停止：" + str(run_stop_reason)}
        if run_stop_reason is None:
            det_stopped: str | None = None
            for repeat in range(int(sp.S3_DETERMINISM_REPEATS)):
                if repeat == 0:
                    det_rows: list[dict[str, Any]] = []
                    for spec in det_specs:
                        run_key = _run_id_for(spec, str(run_id))
                        result = main_by_run_id.get(run_key)
                        _require(result is not None, S3_RUNNER_ERROR, "确定性子集 run 缺失于主 campaign: " + str(run_key))
                        det_rows.extend(result.get("records", []))
                else:
                    det_campaign = execute_campaign(
                        det_specs,
                        workers=int(parallel_workers),
                        state=state,
                        # R-S3-08 / Lead m07182：重复 campaign 必须与主 campaign 同 campaign_id。
                        campaign_id=str(run_id),
                        run_mode=run_mode,
                        prior_sum_run_wall_s=total_sum_run_wall,
                    )
                    det_rows = [record for result in det_campaign["results"] for record in result.get("records", [])]
                    det_stopped = _record_campaign(det_campaign)
                det_dir = out / S3_RUNNER_DET_DIR / ("r" + str(repeat + 1))
                det_dir.mkdir(parents=True, exist_ok=True)
                write_jsonl(det_dir / S3_RUNNER_RECORD_FILE, det_rows)
                det_streams.append(det_rows)
                det_core.append(_record_core_list(det_rows))
                if det_stopped is not None:
                    run_stop_reason = det_stopped
                    break
            if det_stopped is None:
                determinism = {
                    "mode": run_mode,
                    "reruns": int(sp.S3_DETERMINISM_REPEATS),
                    "subset_runs": det_count,
                    "subset_run_keys_sha256": str((prereg.get("determinism") or {}).get("subset_run_keys_sha256")),
                    "executed": True,
                    "record_digest_excluded_fields": ["wall_s", "peak_memory_mb", "record_digest"],
                    "byte_identical_artifacts": [
                        "run_config.json",
                        "episode_bank_sha256",
                        "model_sha256",
                        "fd_or_gradient_gate_sha256",
                        "record_core",
                    ],
                    "record_core_equal": all(core == det_core[0] for core in det_core),
                    "record_core_sha256": [sp.canonical_sha256(core) for core in det_core],
                    "record_streams": {
                        "main": S3_RUNNER_RECORD_FILE,
                        "nc": S3_RUNNER_NC_RECORDS_FILE,
                        "ood": S3_RUNNER_OOD_RECORDS_FILE,
                        "det": [_det_record_relpath(index) for index in range(1, int(sp.S3_DETERMINISM_REPEATS) + 1)],
                    },
                }
                write_json_canonical(out / S3_RUNNER_DET_CHECK_FILE, determinism)
            else:
                determinism = {
                    "mode": run_mode,
                    "reruns": 0,
                    "executed": False,
                    "record_digest_excluded_fields": ["wall_s", "peak_memory_mb", "record_digest"],
                    "byte_identical_artifacts": [
                        "run_config.json",
                        "episode_bank_sha256",
                        "model_sha256",
                        "fd_or_gradient_gate_sha256",
                        "record_core",
                    ],
                    "reason": "资源停止：" + str(run_stop_reason),
                }
        else:
            determinism = {
                "mode": run_mode,
                "reruns": 0,
                "executed": False,
                "record_digest_excluded_fields": ["wall_s", "peak_memory_mb", "record_digest"],
                "byte_identical_artifacts": [
                    "run_config.json",
                    "episode_bank_sha256",
                    "model_sha256",
                    "fd_or_gradient_gate_sha256",
                    "record_core",
                ],
                "reason": "资源停止：" + str(run_stop_reason),
            }
    total_sum_run_wall = float(sum(campaign_sum_run_walls))
    if run_stop_reason is None and total_sum_run_wall > float(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]):
        run_stop_reason = S3_RUNNER_SUM_RUN_WALL_LIMIT
    status = "COMPLETED"
    if run_stop_reason in (S3_RUNNER_RESOURCE_LIMIT, S3_RUNNER_SUM_RUN_WALL_LIMIT):
        status = "RESOURCE_LIMIT"
    elif run_stop_reason == S3_RUNNER_DEADLINE_EXCEEDED:
        status = "DEADLINE_EXCEEDED"
    elif failures:
        status = "PARTIAL"
    stream_evals = {
        "main": int(len(eval_records)),
        "nc": int(len(aux_records.get("negative_control", []))),
        "ood": int(len(aux_records.get("ood", []))),
        "det": int(sum(len(rows) for rows in det_streams)),
    }
    all_eval_records: list[dict[str, Any]] = list(eval_records)
    for rows in aux_records.values():
        all_eval_records.extend(rows)
    for rows in det_streams:
        all_eval_records.extend(rows)
    eval_total = int(sum(stream_evals.values()))
    record_counts = {
        "train": int(len(train_records)),
        "eval": eval_total,
        "total": int(len(train_records) + eval_total),
    }
    scope_notes = _scope_notes(
        run_mode=run_mode,
        workers=int(parallel_workers),
        smoke_overrides=budget.get("smoke_overrides"),
        record_streams=stream_evals,
    )
    model_block = {
        "entries": train["entries"],
    }
    run_config = build_run_config(
        run_id=str(run_id),
        run_mode=run_mode,
        budget=budget,
        prereg=prereg,
        family_package=package,
        episode_banks=prepared["episode_banks"],
        model_block=model_block,
        gate=prepared["gate"],
        main_specs=main_specs,
        record_counts=record_counts,
        scope_notes=scope_notes,
        campaign_authorization=auth,
    )
    config_info = write_json_canonical(out / S3_RUNNER_CONFIG_FILE, run_config)
    records_info = write_jsonl(out / S3_RUNNER_RECORD_FILE, train_records + eval_records)
    aux_sha: dict[str, str] = {}
    for name, rows in aux_records.items():
        if rows:
            info = write_jsonl(out / (str(name) + "_records.jsonl"), rows)
            aux_sha[str(name) + "_records.jsonl"] = info["sha256"]
    if negative_controls.get("executed"):
        nc_summary = _negative_control_summary(aux_records.get("negative_control", []))
        write_json_canonical(out / S3_RUNNER_NC_SUMMARY_FILE, nc_summary)
        aux_sha[S3_RUNNER_NC_SUMMARY_FILE] = _raw_sha(out / S3_RUNNER_NC_SUMMARY_FILE) or ""
    det_artifact_sha: dict[str, str] = {}
    for repeat in range(1, len(det_streams) + 1):
        relpath = _det_record_relpath(repeat)
        det_artifact_sha[relpath] = _raw_sha(out / relpath) or ""
    artifact_sha256 = {
        S3_RUNNER_RECORD_FILE: records_info["sha256"],
        S3_RUNNER_MODEL_MANIFEST_FILE: prepared["model_manifest_info"]["sha256"],
        S3_RUNNER_GATE_FILE: prepared["gate"]["sha256"],
        S3_RUNNER_EXECUTION_REPORT_FILE: "",
        **{key: value for key, value in aux_sha.items() if value},
        **det_artifact_sha,
    }
    for seed, bank in prepared["episode_banks"].items():
        artifact_sha256[str(bank["path"])] = str(bank["sha256"])
    for row in prepared["model_manifest"]["models"]:
        candidate = out / str(row["path"])
        if candidate.is_file():
            artifact_sha256[str(row["path"])] = str(row["sha256"])
    final_execution_report = build_final_execution_report(
        main["execution_report"],
        stop_reason=run_stop_reason,
        sum_run_wall_seconds=total_sum_run_wall,
        max_run_wall_s=max(campaign_max_run_walls) if campaign_max_run_walls else 0.0,
        max_peak_memory_mb=max(campaign_peaks) if campaign_peaks else 0.0,
        campaign_wall_s=sum(campaign_walls),
    )
    execution_info = write_json_canonical(out / S3_RUNNER_EXECUTION_REPORT_FILE, final_execution_report)
    artifact_sha256[S3_RUNNER_EXECUTION_REPORT_FILE] = execution_info["sha256"]
    if run_mode == "FORMAL":
        artifact_sha256[S3_RUNNER_DET_CHECK_FILE] = _raw_sha(out / S3_RUNNER_DET_CHECK_FILE) or ""
    data_manifest = build_data_manifest(
        run_id=str(run_id),
        prereg=prereg,
        by_split=by_split,
        synthetic_call_count=int(eval_total),
        artifact_sha256=artifact_sha256,
        run_mode=run_mode,
        campaign_authorization=auth,
    )
    data_info = write_json_canonical(out / S3_RUNNER_DATA_MANIFEST_FILE, data_manifest)
    timings = _outer_step_timing(train)
    train_wall_total = (
        sum(float(row["train_wall_s"]) for row in train["per_seed_resources"])
        if train["per_seed_resources"]
        else 0.0
    )
    if run_mode == "FORMAL":
        auxiliary_compute = {
            "models_source": "PREREG_FROZEN",
            "model_training_episodes": int(sp.S3_MODEL_EPISODE_PAIRS),
            "fd_gate_models": int(len(sp.S3_FD_GATE_MODEL_KEYS)),
            "fd_gate_coordinates_per_model": int(sp.S3_FD_GATE_COORDINATES_PER_MODEL),
            "fd_gate_episode_reruns": int(sp.S3_FD_GATE_COORDINATES_PER_MODEL * 2 * len(sp.S3_FD_GATE_MODEL_KEYS)),
            "outer_step_timing_measurements": 0,
            "evaluation_record_streams": dict(stream_evals),
            "physical_call_count": 0,
            "note": "FORMAL：加载 M2 冻结模型/episode bank/FD 门（不重训）；M2 的 9600 model-episode 训练与 128 次梯度门 episode 重跑不计入本次 run。",
        }
    else:
        auxiliary_compute = {
            "models_source": "RETRAINED_IN_RUN",
            "outer_step_timing_measurements": len(timings),
            "outer_step_timing": timings,
            "evaluation_record_streams": dict(stream_evals),
            "physical_call_count": 0,
            "note": "SMOKE：run 内重训微型模型并重新生成 FD 门（与 prereg 冻结件不同，analysis 按 SMOKE 专属 DISCLOSED 处理）；全部为纯解析合成。",
        }
    resources = {
        "total_wall_s": _round6(float(sum(campaign_walls)) + float(train_wall_total)),
        "max_wall_s": _round6(float(max(campaign_max_run_walls)) if campaign_max_run_walls else 0.0),
        "max_peak_memory_mb": _round6(float(max(campaign_peaks)) if campaign_peaks else 0.0),
        "sum_run_wall_seconds": _round6(total_sum_run_wall),
        "sum_run_wall_limit_s": int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]),
        "parallel_workers": int(parallel_workers),
        "stop_reason": run_stop_reason,
        "auxiliary_compute": auxiliary_compute,
        "resource_limits": dict(sp.S3_RESOURCE_LIMITS),
    }
    summary: dict[str, Any] = {
        "schema_version": sp.S3_RUN_SUMMARY_SCHEMA_VERSION,
        "run_id": str(run_id),
        "run_mode": run_mode,
        "created_utc": str(created_utc or utc_now()),
        "status": status,
        "record_counts": dict(record_counts),
        "status_counts": _status_counts(list(train_records) + all_eval_records),
        "per_run": [result["run"] for result in main_results],
        "models": run_config["models"],
        "resources": resources,
        "determinism": determinism,
        "fd_or_gradient_gate_sha256": prepared["gate"]["sha256"],
        "data_manifest_sha256": data_info["sha256"],
        "negative_controls": negative_controls,
        "physical_call_count": 0,
        "evidence_scope": str(sp.S3_EVIDENCE_SCOPE),
        "environment": _environment(),
        "scope_notes": list(scope_notes),
        "failures": failures,
    }
    _require(set(summary) == set(sp.S3_RUN_SUMMARY_REQUIRED_FIELDS) | {"failures"}, S3_RUNNER_VALIDATION_ERROR, "run_summary 字段集不符")
    write_json_canonical(out / S3_RUNNER_SUMMARY_FILE, summary)
    validation = validate_run_artifacts(out, prereg=prereg, repo_root=root)
    return {
        "summary": summary,
        "validation": validation,
        "run_dir": str(out),
        "run_config_sha256": config_info["sha256"],
        "run_records_sha256": records_info["sha256"],
        "data_manifest_sha256": data_info["sha256"],
        "model_manifest_sha256": prepared["model_manifest_info"]["sha256"],
        "gate_sha256": prepared["gate"]["sha256"],
        "execution_report": final_execution_report,
    }


def _negative_control_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, int], list[bool]] = {}
    for record in records:
        key = (str(record["arm_id"]), int(record["budget"]))
        grouped.setdefault(key, []).append(bool(record.get("feasible")))
    rows = [
        {
            "arm_id": key[0],
            "budget": int(key[1]),
            "n": len(values),
            "feasible_rate": float(sum(1 for item in values if item) / max(1, len(values))),
        }
        for key, values in sorted(grouped.items())
    ]
    suspicious = [row for row in rows if float(row["feasible_rate"]) > 0.50]
    return {
        "schema_version": "p4ra-s3-negative-control-summary-v1",
        "executed": True,
        "records": len(records),
        "groups": rows,
        "suspicious_groups": suspicious,
        "physical_call_count": 0,
    }



def _pilot_run_digests(results: Sequence[Mapping[str, Any]]) -> tuple[dict[str, list[str]], list[str], dict[str, Any]]:
    """把每次 run 的评估 record_digest 序列映射到 canonical run_key。"""
    digests: dict[str, list[str]] = {}
    order: list[str] = []
    per_run: dict[str, Any] = {}
    for result in results:
        key = sp.canonical_json(canonical_run_key(result["spec"]))
        if key in digests:
            continue
        digests[key] = [str(record["record_digest"]) for record in result.get("records") or []]
        order.append(key)
        per_run[key] = {
            "status": str(result.get("status")),
            "n_records": len(result.get("records") or []),
            "digests_sha256": sp.sha256_text("\n".join(digests[key])),
        }
    order.sort()
    return digests, order, per_run


def _w8_family_block(
    package: Mapping[str, Any],
    *,
    package_relpath: str,
    tasks: Sequence[tf.S3ConflictTask],
) -> dict[str, Any]:
    """W=8 试点门 family 块：族标识从 load_family_package 的 payload 读取。

    R2 缺陷根因：load_family_package 顶层是 {path,sha256,bytes,payload,tasks,by_split,
task_ids_sha256}，family_id/formula_version 实际在 payload 内；W=8 试点门曾按顶层
取值而 KeyError。本 helper 统一取值并 fail-closed 复核 payload 的族常量；M01/M02
（计划 v1.3e）追加 family_package_bytes 用于字节级复核（输出 7 键）。
    """
    payload = package.get("payload")
    _require(isinstance(payload, Mapping), S3_RUNNER_FAMILY_ERROR, "W=8 试点门族包缺少 payload mapping")
    family_id = str(payload.get("family_id") or "")
    formula_version = str(payload.get("formula_version") or "")
    _require(family_id == str(sp.S3_FAMILY_ID), S3_RUNNER_FAMILY_ERROR, "W=8 试点门族包 payload family_id 不符")
    _require(
        formula_version == str(sp.S3_FORMULA_VERSION),
        S3_RUNNER_FAMILY_ERROR,
        "W=8 试点门族包 payload formula_version 不符",
    )
    _require(
        payload.get("family_seed") == int(sp.S3_FAMILY_SEED),
        S3_RUNNER_FAMILY_ERROR,
        "W=8 试点门族包 payload family_seed 不符",
    )
    _require(
        payload.get("holdout_seed") == int(sp.S3_HOLDOUT_SEED),
        S3_RUNNER_FAMILY_ERROR,
        "W=8 试点门族包 payload holdout_seed 不符",
    )
    _require(
        dict(payload.get("split_counts") or {}) == dict(sp.S3_SPLIT_COUNTS),
        S3_RUNNER_FAMILY_ERROR,
        "W=8 试点门族包 payload split_counts 不符",
    )
    task_ids = [task.task_id for task in tasks]
    return {
        "family_id": family_id,
        "formula_version": formula_version,
        "family_package_path": str(package_relpath),
        "family_package_sha256": str(package["sha256"]),
        "family_package_bytes": int(package["bytes"]),
        "task_ids": task_ids,
        "task_ids_sha256": sp.task_ids_sha256(task_ids),
    }

# ---------------------------------------------------------------------------
# M2R（M01/M02）：W=8 试点门 payload 组装、bench 外推块与复算
# ---------------------------------------------------------------------------
def _canonical_lf_sha256(data: bytes) -> str:
    """按 canonical LF 字节算 sha（构建/校验 bench/gate/family 文件一致口径）。"""
    return sp.sha256_bytes(data.replace(b"\r\n", b"\n"))


def _w8_bench_block(repo_root: str | Path) -> dict[str, Any]:
    """读取 bench_v13a / bench_v13a_run2（R-S3-05B）：校验 canonical LF sha 并抽取外推数字。"""
    root = Path(repo_root)
    bench: dict[str, Any] = {}
    for rel_path in S3_W8_BENCH_RELPATHS:
        path = root / str(rel_path)
        _require(path.is_file(), S3_RUNNER_VALIDATION_ERROR, "缺少 W8 外推 bench 文件: " + str(rel_path))
        raw = path.read_bytes()
        sha = _canonical_lf_sha256(raw)
        _require(
            sha == str(S3_W8_BENCH_FILE_SHA256[str(rel_path)]),
            S3_RUNNER_VALIDATION_ERROR,
            "W8 外推 bench 文件 canonical LF sha 不符: " + str(rel_path),
        )
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - fail-closed 包装
            raise S3RunnerError(S3_RUNNER_VALIDATION_ERROR, "W8 外推 bench JSON 解析失败: " + str(rel_path)) from exc
        measurements = data.get("measurements") or {}
        w1 = measurements.get("w1") or {}
        w8 = measurements.get("w8") or {}
        projection = ((data.get("projection") or {}).get("w8") or {}).get(str(int(S3_W8_TARGET_RUNS))) or {}
        try:
            entry = {
                "path": str(rel_path),
                "sha256": str(S3_W8_BENCH_FILE_SHA256[str(rel_path)]),
                "w1_wall_s": float(w1["wall_s"]),
                "w8_wall_s": float(w8["wall_s"]),
                "runs_per_second": float(w8["runs_per_s"]),
                "projected_3780_by_measured_throughput_s": float(projection["by_measured_throughput_s"]),
                "projected_3780_by_conservative_batch_s": float(projection["by_conservative_batch_s"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise S3RunnerError(S3_RUNNER_VALIDATION_ERROR, "W8 外推 bench 字段缺失: " + str(rel_path)) from exc
        _require(
            entry["w1_wall_s"] > 0 and entry["w8_wall_s"] > 0 and entry["runs_per_second"] > 0,
            S3_RUNNER_VALIDATION_ERROR,
            "W8 外推 bench wall/runs_per_s 必须 > 0: " + str(rel_path),
        )
        bench[path.stem] = entry
    _require(
        set(bench) == {"bench_v13a", "bench_v13a_run2"},
        S3_RUNNER_VALIDATION_ERROR,
        "W8 外推 bench 文件集合不符",
    )
    return bench


def _w8_throughput_block(repo_root: str | Path) -> dict[str, Any]:
    """组装 3780 runs 外推块（权威口径 = 两次 bench 的最保守 max）。"""
    bench = _w8_bench_block(repo_root)
    first = bench["bench_v13a"]
    second = bench["bench_v13a_run2"]
    projected_throughput = round(
        max(float(entry["projected_3780_by_measured_throughput_s"]) for entry in bench.values()), 3
    )
    projected_conservative = round(
        max(float(entry["projected_3780_by_conservative_batch_s"]) for entry in bench.values()), 3
    )
    _require(
        projected_throughput == float(S3_W8_PROJECTED_3780_THROUGHPUT_S),
        S3_RUNNER_VALIDATION_ERROR,
        "W8 外推 throughput 与 R-S3-05B 权威值不符: " + repr(projected_throughput),
    )
    _require(
        projected_conservative == float(S3_W8_PROJECTED_3780_WALL_S),
        S3_RUNNER_VALIDATION_ERROR,
        "W8 外推 conservative 与 R-S3-05B 权威值不符: " + repr(projected_conservative),
    )
    delta_pct = abs(float(second["w8_wall_s"]) - float(first["w8_wall_s"])) / float(first["w8_wall_s"]) * 100.0
    delta_pct = float(round(delta_pct, 6))
    acceptance = {
        "lead_ruling": str(S3_W8_ACCEPTANCE_RULING),
        "ruling_sha256": str(S3_W8_ACCEPTANCE_RULING_SHA256),
        "accepted_upper_bound_s": float(projected_conservative),
        "within_5400": bool(float(projected_conservative) <= 5400.0),
        "accepted": bool(float(projected_conservative) <= float(S3_W8_HARD_CAP_S)),
    }
    return {
        "basis": "bench_v13a+bench_v13a_run2 (R-S3-05B)",
        "bench": bench,
        "projected_3780_throughput_s": float(projected_throughput),
        "projected_3780_conservative_s": float(projected_conservative),
        "second_campaign_wall_delta_pct": float(delta_pct),
        "second_campaign_wall_delta_pass": bool(delta_pct < float(S3_W8_SECOND_CAMPAIGN_WALL_DELTA_LIMIT_PCT)),
        "hard_cap_s": int(S3_W8_HARD_CAP_S),
        "acceptance": acceptance,
    }


def _w8_gate_payload(
    *,
    repo_root: str | Path,
    campaign_id: str,
    created_utc: str,
    family: Mapping[str, Any],
    models_sha: Mapping[str, str],
    models_files: Mapping[str, Mapping[str, Any]],
    grid: Mapping[str, Any],
    workers: Sequence[int],
    campaigns: Mapping[str, Mapping[str, Any]],
    determinism_block: Mapping[str, Any],
) -> dict[str, Any]:
    """组装 W=8 试点门 payload（§4.2.1 字段；本地 wall 只披露、不外推 3780）。"""
    root = Path(repo_root)
    throughput = _w8_throughput_block(root)
    w1 = campaigns["W1"]
    w8 = campaigns["W8"]
    w1_wall = float(w1["campaign_wall_s"])
    w8_wall = float(w8["campaign_wall_s"])
    _require(w1_wall > 0 and w8_wall > 0, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 campaign wall 必须 > 0")
    det_equal = bool(determinism_block.get("record_digest_sequences_equal"))
    all_completed = all(
        int(block.get("run_count_completed") or 0) == int(sp.S3_W8_PILOT_RUNS_PER_CAMPAIGN)
        for block in campaigns.values()
    )
    status = "PASS" if det_equal and all_completed else "FAIL"
    peak_memory = max(float(w1["max_peak_memory_mb"]), float(w8["max_peak_memory_mb"]))
    peak_upper = peak_memory * float(max(int(item) for item in workers))
    threads_env = {name: "1" for name in S3_THREAD_ENV_VARS}
    criteria = {
        "record_digest_equal": bool(det_equal),
        "extrapolation_within_hard_cap": bool(
            float(throughput["projected_3780_conservative_s"]) <= float(throughput["hard_cap_s"])
        ),
        "lead_acceptance": bool(throughput["acceptance"]["accepted"]),
        "peak_memory_within_limit": bool(peak_memory < float(sp.S3_RESOURCE_LIMITS["peak_memory_mb"])),
        "repeat_wall_delta_below_20pct": bool(throughput["second_campaign_wall_delta_pass"]),
        "thread_env_fixed": True,
    }
    verdict = "PASS" if status == "PASS" and all(bool(value) for value in criteria.values()) else "FAIL"
    return {
        "schema_version": str(sp.S3_W8_PILOT_GATE_SCHEMA_VERSION),
        "created_utc": str(created_utc),
        "campaign_id": str(campaign_id),
        "family": dict(family),
        "models": {
            "kind": "fomaml+anil",
            "meta_seed": int(sp.S3_W8_PILOT_META_SEED),
            "sha256": {str(kind): str(value) for kind, value in sorted(models_sha.items())},
            "files": {
                str(kind): {
                    "path": str(entry["path"]),
                    "sha256": str(entry["sha256"]),
                    "bytes": int(entry["bytes"]),
                }
                for kind, entry in sorted(models_files.items())
            },
        },
        "grid": dict(grid),
        "workers": [int(item) for item in workers],
        "campaigns": dict(campaigns),
        "determinism": dict(determinism_block),
        "w1_wall_s": float(w1_wall),
        "w8_wall_s": float(w8_wall),
        "runs_per_second": float(int(sp.S3_W8_PILOT_RUNS_PER_CAMPAIGN) / w8_wall),
        "projected_3780_wall_s": float(throughput["projected_3780_conservative_s"]),
        "projected_3780_throughput_s": float(throughput["projected_3780_throughput_s"]),
        "record_digest_equal": bool(det_equal),
        "peak_memory_mb": float(peak_memory),
        "peak_upper_bound_mb": float(peak_upper),
        "threads_env": threads_env,
        "threads_env_fixed": True,
        "throughput_extrapolation": dict(throughput),
        "criteria": criteria,
        "verdict": str(verdict),
        "parallel": {
            "speedup": float(w1_wall / w8_wall),
            "peak_upper_bound_mb": float(peak_upper),
            "peak_memory_limit_mb": float(sp.S3_RESOURCE_LIMITS["peak_memory_mb"]),
            "sum_run_wall_limit_s": int(sp.S3_RESOURCE_LIMITS["sum_run_wall_limit_s"]),
            "thread_env": dict(threads_env),
        },
        "status": str(status),
        "physical_call_count": 0,
        "solver_processes_started": 0,
    }


def build_w8_pilot_gate(
    *,
    repo_root: str | Path,
    prereg: Mapping[str, Any],
    out_path: str | Path | None = None,
    created_utc: str | None = None,
    workers: Sequence[int] = sp.S3_W8_PILOT_WORKERS,
    campaign_id: str = "w8-pilot",
) -> dict[str, Any]:
    """M2 W=8 并行确定性试点门：3 meta_validation task x 5 臂 x B=128，W=1 与 W=8 各 15 runs。"""
    root = Path(repo_root).resolve()
    worker_list = tuple(sorted({int(item) for item in workers}))
    _require(
        worker_list == tuple(int(item) for item in sp.S3_W8_PILOT_WORKERS),
        S3_RUNNER_ERROR,
        "W=8 试点门 workers 必须为 (1, 8)",
    )
    family = prereg.get("family") or {}
    package_relpath = str(family.get("package_path") or sp.S3_FAMILY_PACKAGE_RELPATH)
    package = load_family_package(root / package_relpath)
    validation_tasks = sorted(package["by_split"]["meta_validation"], key=lambda task: task.task_id)
    tasks = validation_tasks[: int(sp.S3_W8_PILOT_TASKS)]
    _require(
        len(tasks) == int(sp.S3_W8_PILOT_TASKS),
        S3_RUNNER_FAMILY_ERROR,
        "W=8 试点门需要 3 个 meta_validation 任务",
    )
    by_id = {task.task_id: task for task in tasks}
    models = load_frozen_models(repo_root=root, prereg=prereg, meta_seeds=[int(sp.S3_W8_PILOT_META_SEED)])
    state = worker_payload_for_state(models=models, tasks=by_id, prereg=prereg)
    specs: list[dict[str, Any]] = []
    for task in tasks:
        for arm in sp.S3_ARMS:
            specs.append(
                {
                    "arm": str(arm),
                    "task_id": task.task_id,
                    "budget": int(sp.S3_W8_PILOT_BUDGET),
                    "opt_seed": int(sp.S3_W8_PILOT_OPT_SEED),
                    "meta_seed": int(sp.S3_W8_PILOT_META_SEED),
                    "split": "meta_validation",
                    "phase": eval_phase_for_split("meta_validation"),
                    "campaign_id": str(campaign_id),
                }
            )
    runs_expected = int(sp.S3_W8_PILOT_RUNS_PER_CAMPAIGN)
    _require(len(specs) == runs_expected, S3_RUNNER_ERROR, "W=8 试点门 run 数必须为 15")
    campaigns: dict[str, Any] = {}
    digests_by_worker: dict[int, dict[str, list[str]]] = {}
    order_by_worker: dict[int, list[str]] = {}
    per_run_by_worker: dict[int, dict[str, Any]] = {}
    for count in worker_list:
        outcome = execute_campaign(
            specs,
            workers=int(count),
            state=state,
            campaign_id=str(campaign_id),
            run_mode="SMOKE",
        )
        results = list(outcome["results"])
        report = dict(outcome["execution_report"])
        digests_by_worker[int(count)] = digests = {}
        order_by_worker[int(count)] = order = []
        digests, order, per_run = _pilot_run_digests(results)
        digests_by_worker[int(count)] = digests
        order_by_worker[int(count)] = order
        per_run_by_worker[int(count)] = per_run
        campaigns["W" + str(int(count))] = {
            "parallel_workers": int(count),
            "campaign_wall_s": float(report["campaign_wall_s"]),
            "sum_run_wall_seconds": float(report["sum_run_wall_seconds"]),
            "max_run_wall_s": float(report["max_run_wall_s"]),
            "max_peak_memory_mb": float(report["max_peak_memory_mb"]),
            "run_count_requested": int(report["run_count_requested"]),
            "run_count_completed": int(report["run_count_completed"]),
            "stop_reason": report["stop_reason"],
            "execution_report_sha256": sp.canonical_sha256(report),
        }
    baseline = order_by_worker[1]
    equal = True
    first_divergence: dict[str, Any] | None = None
    for count in worker_list:
        order = order_by_worker[int(count)]
        if order != baseline:
            equal = False
            first_divergence = {"worker": int(count), "reason": "run_key_order_mismatch"}
            break
        for key in baseline:
            if digests_by_worker[int(count)][key] != digests_by_worker[1][key]:
                equal = False
                first_divergence = {"worker": int(count), "run_key": json.loads(key)}
                break
        if not equal:
            break
    completed = {int(count): int(campaigns["W" + str(int(count))]["run_count_completed"]) for count in worker_list}
    all_completed = all(value == runs_expected for value in completed.values())
    status = "PASS" if bool(equal) and all_completed else "FAIL"
    models_sha = {str(kind): str(entry["sha256"]) for (kind, _seed), entry in sorted(models.items())}
    models_files = {str(kind): entry for (kind, _seed), entry in sorted(models.items())}
    grid = {
        "tasks": int(sp.S3_W8_PILOT_TASKS),
        "arms": [str(arm) for arm in sp.S3_ARMS],
        "budget": int(sp.S3_W8_PILOT_BUDGET),
        "opt_seed": int(sp.S3_W8_PILOT_OPT_SEED),
        "meta_seed": int(sp.S3_W8_PILOT_META_SEED),
        "runs_per_campaign": runs_expected,
        "evals_per_campaign": int(sp.S3_W8_PILOT_EVALS_PER_CAMPAIGN),
        "total_runs": int(sp.S3_W8_PILOT_TOTAL_RUNS),
        "total_evals": int(sp.S3_W8_PILOT_TOTAL_EVALS),
        "run_keys_sha256": sp.sha256_text("\n".join(baseline)),
    }
    determinism_block = {
        "record_digest_sequences_equal": bool(equal),
        "first_divergence": first_divergence,
        "n_runs_compared": len(baseline),
        "per_run": per_run_by_worker[1],
        "per_run_by_worker": {
            "W1": per_run_by_worker[1],
            "W8": per_run_by_worker[8],
        },
    }
    payload = _w8_gate_payload(
        repo_root=root,
        campaign_id=str(campaign_id),
        created_utc=str(created_utc or utc_now()),
        family=_w8_family_block(package, package_relpath=str(package_relpath), tasks=tasks),
        models_sha=models_sha,
        models_files=models_files,
        grid=grid,
        workers=worker_list,
        campaigns=campaigns,
        determinism_block=determinism_block,
    )
    target = Path(out_path) if out_path is not None else root / sp.S3_W8_PILOT_GATE_RELPATH
    target.parent.mkdir(parents=True, exist_ok=True)
    info = write_json_canonical(target, payload)
    # M2R M01 生产调用点：写盘后立即用 file_sha256 + repo_root 全量复核，失败 fail-closed
    verify_w8_pilot_gate(
        payload,
        gate_path=target,
        file_sha256=str(info["sha256"]),
        repo_root=root,
    )
    try:
        rel_path = target.resolve().relative_to(root).as_posix()
    except ValueError:
        rel_path = str(target)
    return {"path": rel_path, "absolute_path": str(target), "bytes": int(info["bytes"]), "sha256": str(info["sha256"]), "payload": payload}


def verify_w8_pilot_gate(
    payload: Any,
    *,
    gate_path: str | Path | None = None,
    file_sha256: str | None = None,
    repo_root: str | Path | None = None,
) -> bool:
    """M2R M01：逐项 fail-closed 校验 M2 W=8 试点门（结构/哈希/外推/文件字节）。"""
    _require(isinstance(payload, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门必须是 mapping")
    _require(
        payload.get("schema_version") == sp.S3_W8_PILOT_GATE_SCHEMA_VERSION,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 schema 不符",
    )
    _require(payload.get("status") == "PASS", S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 status 必须为 PASS")
    _require(payload.get("verdict") == "PASS", S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 verdict 必须为 PASS")
    _require(
        tuple(payload.get("workers") or ()) == tuple(int(item) for item in sp.S3_W8_PILOT_WORKERS),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 workers 必须为 [1, 8]",
    )
    campaigns = payload.get("campaigns")
    _require(
        isinstance(campaigns, Mapping) and set(campaigns) == {"W1", "W8"},
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 campaigns 必须恰含 W1/W8",
    )
    runs_expected = int(sp.S3_W8_PILOT_RUNS_PER_CAMPAIGN)
    for count in sp.S3_W8_PILOT_WORKERS:
        block = campaigns.get("W" + str(int(count)))
        _require(isinstance(block, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门缺少 W" + str(int(count)) + " campaign")
        _require(
            int(block.get("parallel_workers") or -1) == int(count),
            S3_RUNNER_VALIDATION_ERROR,
            "W=" + str(int(count)) + " parallel_workers 不符",
        )
        _require(
            int(block.get("run_count_completed") or 0) == runs_expected
            and int(block.get("run_count_requested") or 0) == runs_expected,
            S3_RUNNER_VALIDATION_ERROR,
            "W=" + str(int(count)) + " run_count_completed/requested 不符",
        )
        _require(float(block.get("campaign_wall_s") or 0) > 0, S3_RUNNER_VALIDATION_ERROR, "W=" + str(int(count)) + " campaign_wall_s 必须 > 0")
        _require(
            float(block.get("sum_run_wall_seconds") or 0) > 0,
            S3_RUNNER_VALIDATION_ERROR,
            "W=" + str(int(count)) + " sum_run_wall_seconds 必须 > 0",
        )
        _require(
            float(block.get("max_peak_memory_mb") or 0) < float(sp.S3_RESOURCE_LIMITS["peak_memory_mb"]),
            S3_RUNNER_VALIDATION_ERROR,
            "W=" + str(int(count)) + " max_peak_memory_mb 超限",
        )
        _require(
            _is_sha256_hex(block.get("execution_report_sha256")),
            S3_RUNNER_VALIDATION_ERROR,
            "W=" + str(int(count)) + " execution_report_sha256 非法",
        )
    determinism = payload.get("determinism")
    _require(isinstance(determinism, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 determinism 必须是 mapping")
    _require(
        determinism.get("record_digest_sequences_equal") is True,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 W=1 与 W=8 record_digest 序列不一致",
    )
    _require(determinism.get("first_divergence") is None, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门存在 first_divergence")
    _require(
        int(determinism.get("n_runs_compared") or 0) == runs_expected,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门比较 run 数不符",
    )
    per_run_by_worker = determinism.get("per_run_by_worker")
    _require(
        isinstance(per_run_by_worker, Mapping) and set(per_run_by_worker) == {"W1", "W8"},
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 per_run_by_worker 必须恰含 W1/W8",
    )
    for worker in ("W1", "W8"):
        rows = per_run_by_worker.get(worker)
        _require(
            isinstance(rows, Mapping) and len(rows) == runs_expected,
            S3_RUNNER_VALIDATION_ERROR,
            "W=8 试点门 " + worker + " per_run_by_worker 必须有 15 个 run_key",
        )
        for run_key, entry in rows.items():
            _require(isinstance(run_key, str) and bool(run_key), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 run_key 必须为非空字符串")
            _require(isinstance(entry, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 per_run 条目必须是 mapping")
            _require(
                isinstance(entry.get("status"), str) and bool(entry.get("status")),
                S3_RUNNER_VALIDATION_ERROR,
                "W=8 试点门 per_run.status 非法",
            )
            _require(int(entry.get("n_records") or 0) > 0, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 per_run.n_records 必须 > 0")
            _require(
                _is_sha256_hex(entry.get("digests_sha256")),
                S3_RUNNER_VALIDATION_ERROR,
                "W=8 试点门 per_run.digests_sha256 非法",
            )
    _require(
        per_run_by_worker.get("W1") == per_run_by_worker.get("W8"),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门两 worker 每 run 的 digest 序列不一致",
    )
    _require(
        determinism.get("per_run") == per_run_by_worker.get("W1"),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 determinism.per_run 与 per_run_by_worker.W1 不一致",
    )
    grid = payload.get("grid")
    _require(isinstance(grid, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 grid 必须是 mapping")
    _require(
        [str(arm) for arm in grid.get("arms") or []] == [str(arm) for arm in sp.S3_ARMS],
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 grid.arms 不符",
    )
    _require(int(grid.get("runs_per_campaign") or 0) == runs_expected, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 grid.runs_per_campaign 不符")
    _require(int(grid.get("total_runs") or 0) == int(sp.S3_W8_PILOT_TOTAL_RUNS), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 grid.total_runs 不符")
    _require(int(grid.get("total_evals") or 0) == int(sp.S3_W8_PILOT_TOTAL_EVALS), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 grid.total_evals 不符")
    _require(_is_sha256_hex(grid.get("run_keys_sha256")), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 grid.run_keys_sha256 非法")
    family = payload.get("family")
    _require(isinstance(family, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 family 必须是 mapping")
    task_ids = family.get("task_ids")
    _require(
        isinstance(task_ids, list) and len(task_ids) == int(sp.S3_W8_PILOT_TASKS),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 family.task_ids 数量不符",
    )
    task_id_texts = [str(item) for item in task_ids]
    _require(
        task_id_texts == sorted(task_id_texts),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 family.task_ids 未按 task_id 排序",
    )
    _require(
        family.get("task_ids_sha256") == sp.task_ids_sha256(task_id_texts),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 family.task_ids_sha256 不符",
    )
    _require(_is_sha256_hex(family.get("family_package_sha256")), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 family.family_package_sha256 非法")
    _require(
        isinstance(family.get("family_package_bytes"), int) and int(family["family_package_bytes"]) > 0,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 family.family_package_bytes 非正",
    )
    models_block = payload.get("models")
    _require(isinstance(models_block, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 models 必须是 mapping")
    sha_map = models_block.get("sha256")
    files_map = models_block.get("files")
    _require(
        isinstance(sha_map, Mapping) and set(sha_map) == {"fomaml", "anil"} and all(_is_sha256_hex(value) for value in sha_map.values()),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 models.sha256 必须恰含 fomaml/anil 64hex",
    )
    _require(
        isinstance(files_map, Mapping) and set(files_map) == {"fomaml", "anil"},
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 models.files 必须恰含 fomaml/anil",
    )
    for kind in ("fomaml", "anil"):
        entry = files_map.get(kind)
        _require(isinstance(entry, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 models.files." + kind + " 非法")
        _require(
            isinstance(entry.get("path"), str) and bool(entry.get("path")),
            S3_RUNNER_VALIDATION_ERROR,
            "W=8 试点门 models.files." + kind + ".path 非法",
        )
        _require(
            str(entry.get("sha256")) == str(sha_map.get(kind)),
            S3_RUNNER_VALIDATION_ERROR,
            "W=8 试点门 models.files." + kind + ".sha256 与 models.sha256 不一致",
        )
        _require(int(entry.get("bytes") or 0) > 0, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 models.files." + kind + ".bytes 非正")
    _require(payload.get("physical_call_count") == 0, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 physical_call_count 必须为 0")
    _require(payload.get("solver_processes_started") == 0, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 solver_processes_started 必须为 0")
    expected_threads_env = {name: "1" for name in S3_THREAD_ENV_VARS}
    _require(
        isinstance(payload.get("threads_env"), Mapping) and dict(payload["threads_env"]) == expected_threads_env,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 threads_env 必须精确等于单线程展开",
    )
    _require(payload.get("threads_env_fixed") is True, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 threads_env_fixed 必须为 True")
    # ---- 3780 runs 外推块：内部自洽 + 权威值 ----
    extrapolation = payload.get("throughput_extrapolation")
    _require(isinstance(extrapolation, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门缺 throughput_extrapolation")
    bench = extrapolation.get("bench")
    _require(
        isinstance(bench, Mapping) and set(bench) == {"bench_v13a", "bench_v13a_run2"},
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 throughput_extrapolation.bench 必须恰含两次 bench",
    )
    for name, entry in bench.items():
        _require(isinstance(entry, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 bench." + str(name) + " 必须是 mapping")
        for field in (
            "path",
            "sha256",
            "w1_wall_s",
            "w8_wall_s",
            "runs_per_second",
            "projected_3780_by_measured_throughput_s",
            "projected_3780_by_conservative_batch_s",
        ):
            _require(field in entry, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 bench." + str(name) + " 缺字段 " + field)
        _require(_is_sha256_hex(entry.get("sha256")), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 bench." + str(name) + ".sha256 非法")
        _require(float(entry["w8_wall_s"]) > 0, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 bench." + str(name) + ".w8_wall_s 非正")
    expected_throughput = max(float(entry["projected_3780_by_measured_throughput_s"]) for entry in bench.values())
    expected_conservative = max(float(entry["projected_3780_by_conservative_batch_s"]) for entry in bench.values())
    _require(
        abs(float(extrapolation.get("projected_3780_throughput_s")) - expected_throughput) <= 1e-9,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门外推 throughput 与 bench 复算不一致",
    )
    _require(
        abs(float(extrapolation.get("projected_3780_conservative_s")) - expected_conservative) <= 1e-9,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门外推 conservative 与 bench 复算不一致",
    )
    _require(
        abs(expected_throughput - float(S3_W8_PROJECTED_3780_THROUGHPUT_S)) <= 1e-9,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门外推 throughput 与 R-S3-05B 权威值不符",
    )
    _require(
        abs(expected_conservative - float(S3_W8_PROJECTED_3780_WALL_S)) <= 1e-9,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门外推 conservative 与 R-S3-05B 权威值不符",
    )
    first = bench["bench_v13a"]
    second = bench["bench_v13a_run2"]
    expected_delta_pct = abs(float(second["w8_wall_s"]) - float(first["w8_wall_s"])) / float(first["w8_wall_s"]) * 100.0
    _require(
        abs(float(extrapolation.get("second_campaign_wall_delta_pct")) - expected_delta_pct) <= 1e-6,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门第二次 campaign wall 差异与复算不一致",
    )
    _require(
        extrapolation.get("second_campaign_wall_delta_pass") is True
        and expected_delta_pct < float(S3_W8_SECOND_CAMPAIGN_WALL_DELTA_LIMIT_PCT),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门第二次 campaign wall 差异超 20%",
    )
    hard_cap = float(extrapolation.get("hard_cap_s"))
    _require(hard_cap == float(S3_W8_HARD_CAP_S), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 hard_cap_s 必须为 7200")
    _require(expected_conservative <= hard_cap, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门外推 conservative 超硬顶")
    acceptance = extrapolation.get("acceptance")
    _require(isinstance(acceptance, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门缺 acceptance")
    _require(
        acceptance.get("lead_ruling") == str(S3_W8_ACCEPTANCE_RULING),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 acceptance.lead_ruling 不符",
    )
    _require(
        acceptance.get("ruling_sha256") == str(S3_W8_ACCEPTANCE_RULING_SHA256),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 acceptance.ruling_sha256 不符",
    )
    _require(
        float(acceptance.get("accepted_upper_bound_s") or 0) >= expected_conservative,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 acceptance.accepted_upper_bound_s 低于外推值",
    )
    _require(
        bool(acceptance.get("within_5400")) == bool(expected_conservative <= 5400.0),
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 acceptance.within_5400 与复算不一致",
    )
    _require(
        expected_conservative <= 5400.0 or acceptance.get("accepted") is True,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 conservative > 5400 时必须书面接受",
    )
    _require(acceptance.get("accepted") is True, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门外推口径未被接受")
    # ---- 顶层派生字段一致性 ----
    w1 = campaigns["W1"]
    w8 = campaigns["W8"]
    _require(abs(float(payload.get("w1_wall_s")) - float(w1["campaign_wall_s"])) <= 1e-9, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 w1_wall_s 与 W1 campaign 不一致")
    _require(abs(float(payload.get("w8_wall_s")) - float(w8["campaign_wall_s"])) <= 1e-9, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 w8_wall_s 与 W8 campaign 不一致")
    _require(
        abs(float(payload.get("runs_per_second")) - float(runs_expected) / float(payload.get("w8_wall_s"))) <= 1e-9,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门 runs_per_second 与本地 W8 wall 不一致",
    )
    _require(
        abs(float(payload.get("projected_3780_wall_s")) - expected_conservative) <= 1e-9
        and abs(float(payload.get("projected_3780_throughput_s")) - expected_throughput) <= 1e-9,
        S3_RUNNER_VALIDATION_ERROR,
        "W=8 试点门顶层 projected_3780 与外推块不一致",
    )
    _require(payload.get("record_digest_equal") is True, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 record_digest_equal 必须为 True")
    peak_memory = max(float(w1["max_peak_memory_mb"]), float(w8["max_peak_memory_mb"]))
    worker_max = float(max(int(item) for item in sp.S3_W8_PILOT_WORKERS))
    _require(abs(float(payload.get("peak_memory_mb")) - peak_memory) <= 1e-9, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 peak_memory_mb 与 campaign 不一致")
    _require(abs(float(payload.get("peak_upper_bound_mb")) - peak_memory * worker_max) <= 1e-9, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 peak_upper_bound_mb 与复算不一致")
    criteria = payload.get("criteria")
    _require(isinstance(criteria, Mapping), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门缺 criteria")
    expected_criteria = {
        "record_digest_equal": True,
        "extrapolation_within_hard_cap": bool(expected_conservative <= hard_cap),
        "lead_acceptance": True,
        "peak_memory_within_limit": bool(peak_memory < float(sp.S3_RESOURCE_LIMITS["peak_memory_mb"])),
        "repeat_wall_delta_below_20pct": bool(expected_delta_pct < float(S3_W8_SECOND_CAMPAIGN_WALL_DELTA_LIMIT_PCT)),
        "thread_env_fixed": True,
    }
    _require(dict(criteria) == expected_criteria, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 criteria 与复算不一致")
    _require(all(bool(value) for value in criteria.values()), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门存在未通过 criteria")
    _require(payload.get("verdict") == "PASS", S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 verdict 与 criteria 不一致")
    # ---- repo_root：族包/模型文件字节与 bench 文件复算 ----
    if repo_root is not None:
        root = Path(repo_root)
        package_relpath = str(family.get("family_package_path") or sp.S3_FAMILY_PACKAGE_RELPATH)
        package_file = root / package_relpath
        _require(package_file.is_file(), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门族包文件不存在: " + package_relpath)
        package_bytes = package_file.read_bytes()
        _require(
            _canonical_lf_sha256(package_bytes) == str(family.get("family_package_sha256")),
            S3_RUNNER_VALIDATION_ERROR,
            "W=8 试点门族包 canonical LF sha 不符",
        )
        _require(
            len(package_bytes) == int(family.get("family_package_bytes")),
            S3_RUNNER_VALIDATION_ERROR,
            "W=8 试点门族包 bytes 不符",
        )
        package = load_family_package(package_file)
        validation_tasks = sorted(package["by_split"]["meta_validation"], key=lambda task: task.task_id)
        expected_family = _w8_family_block(
            package,
            package_relpath=package_relpath,
            tasks=validation_tasks[: int(sp.S3_W8_PILOT_TASKS)],
        )
        _require(dict(family) == expected_family, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 family 块与族包复算不一致")
        for kind in ("fomaml", "anil"):
            entry = files_map[kind]
            model_file = root / str(entry["path"])
            _require(model_file.is_file(), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门模型文件不存在: " + str(entry["path"]))
            raw = model_file.read_bytes()
            _require(len(raw) == int(entry["bytes"]), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门模型 bytes 不符: " + str(entry["path"]))
            file_sha = _canonical_lf_sha256(raw)
            _require(file_sha == str(entry["sha256"]), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门模型 canonical LF sha 不符: " + str(entry["path"]))
            _require(file_sha == str(sha_map[kind]), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门模型 sha 与 models.sha256 不一致")
        expected_extrapolation = _w8_throughput_block(root)
        _require(dict(extrapolation) == expected_extrapolation, S3_RUNNER_VALIDATION_ERROR, "W=8 试点门外推块与 bench 文件复算不一致")
    # ---- 文件字节复核（M01：build 写盘后生产调用点） ----
    if file_sha256 is not None:
        _require(gate_path is not None, S3_RUNNER_VALIDATION_ERROR, "提供 file_sha256 时必须同时提供 gate_path")
        gate_file = Path(gate_path)
        _require(gate_file.is_file(), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 gate 文件不存在: " + str(gate_path))
        require_sha = str(file_sha256).lower()
        _require(_is_sha256_hex(require_sha), S3_RUNNER_VALIDATION_ERROR, "W=8 试点门 file_sha256 格式不符")
        _require(
            _canonical_lf_sha256(gate_file.read_bytes()) == require_sha,
            S3_RUNNER_VALIDATION_ERROR,
            "W=8 试点门 gate 文件 canonical LF sha 不符",
        )
    return True


# ---------------------------------------------------------------------------
# 命令行接口（M2/M3 运维入口；不改变任何方法、随机流或预算）
# ---------------------------------------------------------------------------
def _parse_int_list(text: str) -> list[int]:
    pieces = [piece.strip() for piece in str(text).split(",") if piece.strip()]
    _require(bool(pieces), S3_RUNNER_ERROR, "整数列表不能为空")
    try:
        return [int(piece) for piece in pieces]
    except ValueError as exc:
        raise S3RunnerError(S3_RUNNER_ERROR, "整数列表格式错误: " + str(text)) from exc


def _print_json(payload: Any) -> None:
    print(sp.canonical_json(payload))


def command_bank(args: argparse.Namespace) -> int:
    """构建 1-3 个 episode bank（仅设计索引与摘要，不含标签；零物理调用）。"""
    package = load_family_package(args.family_package)
    by_split = package["by_split"]
    if args.tasks == "smoke":
        tasks = list(by_split["meta_validation"])[:SMOKE_TRAIN_TASK_COUNT]
        _require(len(tasks) == int(SMOKE_TRAIN_TASK_COUNT), S3_RUNNER_BANK_ERROR, "SMOKE 训练任务不足 4 个")
    else:
        tasks = list(by_split["meta_train"])
        _require(
            len(tasks) == int(sp.S3_SPLIT_COUNTS["meta_train"]),
            S3_RUNNER_BANK_ERROR,
            "FORMAL 训练任务必须为 60 个 meta_train",
        )
    design_cache = family_design_cache(tasks)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for meta_seed in _parse_int_list(args.meta_seeds):
        episodes = build_episode_bank(tasks, int(meta_seed), int(args.outer_steps), design_cache=design_cache)
        info = write_episode_bank(out / ("episode_bank_meta_" + str(int(meta_seed)) + ".jsonl"), episodes)
        rows.append(
            {
                "meta_seed": int(meta_seed),
                "path": str(info["path"]),
                "bytes": int(info["bytes"]),
                "sha256": str(info["sha256"]),
                "episodes": len(episodes),
            }
        )
    _print_json(
        {
            "command": "bank",
            "family_package": str(args.family_package),
            "family_package_sha256": package["sha256"],
            "tasks": str(args.tasks),
            "task_count": len(tasks),
            "outer_steps": int(args.outer_steps),
            "banks": rows,
            "physical_call_count": 0,
        }
    )
    return 0


def command_verify_prereg(args: argparse.Namespace) -> int:
    """校验 prereg 文件（结构、digest、证据绑定；可选真实 code_sha 复算）。"""
    prereg = sp.read_preregistration(args.prereg)
    root = Path(args.repo_root) if args.repo_root else None
    ok = sp.verify_preregistration(
        prereg,
        repo_root=root,
        verify_code_sha=bool(args.verify_code_sha),
    )
    _print_json(
        {
            "command": "verify-prereg",
            "ok": bool(ok),
            "prereg_id": prereg.get("prereg_id"),
            "prereg_digest": prereg.get("prereg_digest"),
            "verify_code_sha": bool(args.verify_code_sha),
        }
    )
    return 0 if ok else 1


def command_run(args: argparse.Namespace) -> int:
    overrides = None
    if args.smoke_overrides:
        overrides = json.loads(args.smoke_overrides)
        _require(isinstance(overrides, Mapping), S3_RUNNER_ERROR, "--smoke-overrides 必须是 JSON object")
    verify_code_sha: bool | None = None
    if args.verify_code_sha != "auto":
        verify_code_sha = args.verify_code_sha == "true"
    campaign_authorization = None
    auth_id = getattr(args, "campaign_authorization_id", None)
    auth_utc = getattr(args, "campaign_authorization_utc", None)
    _require(
        (auth_id is None) == (auth_utc is None),
        S3_RUNNER_CAMPAIGN_AUTH_ERROR,
        "--campaign-authorization-id 与 --campaign-authorization-utc 必须同时提供",
    )
    if auth_id is not None:
        campaign_authorization = {
            "campaign_authorization_id": auth_id,
            "campaign_authorization_utc": auth_utc,
        }
    result = run_experiment(
        out_dir=args.out,
        run_id=args.run_id,
        prereg_path=args.prereg,
        repo_root=args.repo_root,
        run_mode=args.run_mode,
        smoke_overrides=overrides,
        parallel_workers=int(args.workers),
        created_utc=args.created_utc,
        verify_code_sha=verify_code_sha,
        campaign_authorization=campaign_authorization,
    )
    summary = result["summary"]
    _print_json(
        {
            "command": "run",
            "run_dir": result["run_dir"],
            "run_mode": summary["run_mode"],
            "status": summary["status"],
            "record_counts": summary["record_counts"],
            "validation_ok": bool(result["validation"]["ok"]),
            "run_config_sha256": result["run_config_sha256"],
            "run_records_sha256": result["run_records_sha256"],
            "data_manifest_sha256": result["data_manifest_sha256"],
            "model_manifest_sha256": result["model_manifest_sha256"],
            "gate_sha256": result["gate_sha256"],
            "execution_report": result["execution_report"],
        }
    )
    return 0 if result["validation"]["ok"] else 1


def command_validate(args: argparse.Namespace) -> int:
    prereg = sp.read_preregistration(args.prereg) if args.prereg else None
    result = validate_run_artifacts(args.run_dir, prereg=prereg, repo_root=args.repo_root)
    failed = sorted(name for name, item in result["checks"].items() if not item["ok"])
    _print_json(
        {
            "command": "validate",
            "ok": bool(result["ok"]),
            "run_status": result["run_status"],
            "record_counts": result["record_counts"],
            "failed_checks": failed,
        }
    )
    return 0 if result["ok"] else 1


def command_compare(args: argparse.Namespace) -> int:
    result = compare_deterministic_runs(args.dir_a, args.dir_b)
    _print_json({"command": "compare", **result})
    return 0 if result["ok"] else 1


def command_w8_pilot(args: argparse.Namespace) -> int:
    """M2 W=8 并行确定性试点门（3 task x 5 臂 x B=128；W=1 与 W=8 各 15 runs）。"""
    prereg = sp.read_preregistration(args.prereg)
    result = build_w8_pilot_gate(
        repo_root=args.repo_root,
        prereg=prereg,
        out_path=args.out,
        created_utc=args.created_utc,
    )
    payload = result["payload"]
    _print_json(
        {
            "command": "w8-pilot-gate",
            "path": result["path"],
            "sha256": result["sha256"],
            "bytes": result["bytes"],
            "status": payload["status"],
            "determinism": payload["determinism"]["record_digest_sequences_equal"],
            "campaigns": payload["campaigns"],
            "physical_call_count": 0,
        }
    )
    return 0 if payload["status"] == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s3_runner",
        description="S3 runner：零物理调用、run 级并行、fail-closed 产物校验（纯解析合成任务族）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bank = sub.add_parser("bank", help="构建 episode bank（仅设计索引，无标签）")
    bank.add_argument("--family-package", required=True, help="族包 JSON 路径")
    bank.add_argument("--out", required=True, help="输出目录（绝对路径）")
    bank.add_argument("--meta-seeds", default="0,1,2", help="逗号分隔 meta_seed 列表")
    bank.add_argument("--outer-steps", type=int, default=int(S3_TRAIN_OUTER_STEPS), help="outer steps（每 step 8 slot）")
    bank.add_argument("--tasks", choices=("formal", "smoke"), default="formal", help="formal=meta_train 60；smoke=meta_validation 前 4")
    bank.set_defaults(func=command_bank)

    verify = sub.add_parser("verify-prereg", help="校验 prereg（结构/digest/证据绑定；可选 code_sha 复算）")
    verify.add_argument("--prereg", required=True, help="prereg JSON 路径")
    verify.add_argument("--repo-root", default=None, help="仓库根（默认 runner 所在仓库）")
    verify.add_argument("--verify-code-sha", action="store_true", help="用真实 7 文件复算 code_sha（正式冻结必须开）")
    verify.set_defaults(func=command_verify_prereg)

    run = sub.add_parser("run", help="执行 run（FORMAL 或 SMOKE）")
    run.add_argument("--prereg", required=True, help="prereg JSON 路径")
    run.add_argument("--out", required=True, help="run 输出目录（不得已有产物）")
    run.add_argument("--run-id", required=True, help="run_id")
    run.add_argument("--run-mode", choices=S3_RUNNER_EXECUTION_MODES, default="SMOKE", help="运行模式")
    run.add_argument("--smoke-overrides", default=None, help="SMOKE 覆盖 JSON（7 键）")
    run.add_argument("--workers", type=int, default=int(S3_RUNNER_DEFAULT_WORKERS), help="run 级并行度 W")
    run.add_argument("--repo-root", default=None, help="仓库根")
    run.add_argument("--created-utc", default=None, help="created_utc 覆盖（仅测试/复现用）")
    run.add_argument("--verify-code-sha", choices=("auto", "true", "false"), default="auto", help="prereg code_sha 复算策略")
    run.add_argument("--campaign-authorization-id", default=None, help="FORMAL campaign 一次性授权 id（SMOKE 可省）")
    run.add_argument("--campaign-authorization-utc", default=None, help="FORMAL campaign 一次性授权 UTC（SMOKE 可省）")
    run.set_defaults(func=command_run)

    validate = sub.add_parser("validate", help="校验 run 目录产物")
    validate.add_argument("--run-dir", required=True, help="run 目录")
    validate.add_argument("--prereg", default=None, help="prereg JSON（提供则做绑定校验）")
    validate.add_argument("--repo-root", default=None, help="仓库根")
    validate.set_defaults(func=command_validate)

    pilot = sub.add_parser("w8-pilot-gate", help="M2 W=8 并行确定性试点门（W=1 与 W=8 各 15 runs）")
    pilot.add_argument("--prereg", required=True, help="prereg JSON 路径")
    pilot.add_argument("--repo-root", required=True, help="仓库根（含冻结模型/族包）")
    pilot.add_argument("--out", default=None, help="输出路径（默认 evidence/s3/gate/w8_pilot_gate.json）")
    pilot.add_argument("--created-utc", default=None, help="created_utc 覆盖（仅测试/复现用）")
    pilot.set_defaults(func=command_w8_pilot)

    compare = sub.add_parser("compare", help="比较两次 run 的确定性核心记录")
    compare.add_argument("--dir-a", required=True)
    compare.add_argument("--dir-b", required=True)
    compare.set_defaults(func=command_compare)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except S3RunnerError as exc:
        _print_json({"command": str(args.command), "ok": False, "error_code": exc.code, "error": exc.message})
        return 2
    except json.JSONDecodeError as exc:
        _print_json({"command": str(args.command), "ok": False, "error_code": S3_RUNNER_ERROR, "error": "JSON 解析失败: " + str(exc)})
        return 2


__all__ = [
    "S3_RUNNER_SCHEMA_VERSION",
    "S3_EXECUTION_REPORT_SCHEMA_VERSION",
    "S3_RUNNER_RECORD_SCHEMA_VERSION",
    "S3_RUNNER_GATE_FILE",
    "S3_RUNNER_RECORD_FILE",
    "S3_RUNNER_CONFIG_FILE",
    "S3_RUNNER_SUMMARY_FILE",
    "S3_RUNNER_MODEL_MANIFEST_FILE",
    "S3_RUNNER_DATA_MANIFEST_FILE",
    "S3_RUNNER_EXECUTION_REPORT_FILE",
    "S3_RUNNER_NC_RECORDS_FILE",
    "S3_RUNNER_NC_SUMMARY_FILE",
    "S3_RUNNER_MODELS_DIR",
    "S3_RUNNER_REQUIRED_ARTIFACTS",
    "S3_RUNNER_EXECUTION_MODES",
    "S3_RUNNER_DEFAULT_WORKERS",
    "S3_RUNNER_MAX_WORKERS",
    "S3_TRAIN_OUTER_STEPS",
    "S3_TRAIN_EPISODES_PER_STEP",
    "S3_TRAIN_TOTAL_EPISODES",
    "S3_SMOKE_OUTER_STEPS",
    "S3_SMOKE_EPISODES",
    "S3_ADAM_BETA1",
    "S3_ADAM_BETA2",
    "S3_ADAM_EPSILON",
    "S3_ADAM_LR",
    "S3_GATE_COORDINATES_REQUESTED",
    "S3_GATE_EPSILON_POLICY",
    "S3_TRAIN_RULE",
    "S3_RUNNER_ERROR",
    "S3_RUNNER_PREREG_ERROR",
    "S3_RUNNER_DATA_BOUNDARY_ERROR",
    "S3_RUNNER_BANK_ERROR",
    "S3_RUNNER_MODEL_ERROR",
    "S3_RUNNER_RECORD_ERROR",
    "S3_RUNNER_RESOURCE_ERROR",
    "S3_RUNNER_GATE_ERROR",
    "S3_RUNNER_FROZEN_ARTIFACT_MISMATCH",
    "S3_RUNNER_VALIDATION_ERROR",
    "S3_RUNNER_FAMILY_ERROR",
    "S3_RUNNER_FILE_ERROR",
    "S3_RUNNER_BUDGET_MISMATCH",
    "S3_RUNNER_RESOURCE_LIMIT",
    "S3_RUNNER_DEADLINE_EXCEEDED",
    "S3_LEAKAGE_SEALED_REFERENCE_READ",
    "S3_RUNNER_TAMPER_DETECTED",
    "S3_RUNNER_STATUSES",
    "S3_RUNNER_CAMPAIGN_AUTH_ERROR",
    "validate_campaign_authorization",
    "CAMPAIGN_AUTHORIZATION_ID_PATTERN",
    "CAMPAIGN_AUTHORIZATION_UTC_PATTERN",
    "S3_W8_PILOT_GATE_SCHEMA_VERSION",
    "S3_W8_PILOT_GATE_RELPATH",
    "S3RunnerError",
    "utc_now",
    "write_json_canonical",
    "read_json_file",
    "write_jsonl",
    "read_jsonl",
    "array_sha256",
    "designs_sha256",
    "peak_memory_mb",
    "eval_record_digest",
    "train_record_digest",
    "task_ids_sha256_for",
    "load_family_package",
    "family_design_cache",
    "task_labels",
    "build_episode_bank",
    "write_episode_bank",
    "read_episode_bank",
    "build_task_episode",
    "model_config",
    "model_config_dict",
    "model_file_payload",
    "load_model_file",
    "train_model",
    "eval_phase_for_split",
    "make_evaluator",
    "execute_run_spec",
    "canonical_run_key",
    "run_sort_key",
    "run_shard",
    "shard_map",
    "worker_payload_for_state",
    "execute_campaign",
    "build_main_run_specs",
    "build_aux_run_specs",
    "prepare_training_tasks",
    "train_models",
    "prepare_episode_banks",
    "build_gradient_gate",
    "resolve_budget",
    "build_run_config",
    "build_data_manifest",
    "validate_run_artifacts",
    "compare_deterministic_runs",
    "build_w8_pilot_gate",
    "verify_w8_pilot_gate",
    "run_experiment",
    "build_parser",
    "main",
]




