"""D-NEXT-001 A4｜G1 GPU/CPU FOMAML 与代理批量打分基准（合成、零物理调用）。

用法（工作树根目录）：
  D:\RCAIDE\envs\RCAIDE\python.exe -m research.concorde_metaopt.gpu.bench_gpu --out research/concorde_metaopt/gpu/runs/<run_id>
  D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m research.concorde_metaopt.gpu.bench_gpu --out ... --configs cpu-fp64,cuda-fp64,cuda-fp32

设计要点：
- 三路配置共用同一任务族、同一种子、同一批 support/query 数据；计时前后
  torch.cuda.synchronize()，每项重复 >=3 次（默认 3 次 + 1 次预热）；
- 记录墙钟、峰值显存、进程峰值 RAM、query RMSE、相对 CPU-FP64 的元梯度误差、
  确定性（同种子重复间最大参数差）与 NaN/Inf 计数；
- physical_call_count=0，source_kind=synthetic_analogue；GPU 更快不代表算法更好。
"""

from __future__ import annotations

import argparse
import ctypes
import csv
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from research.concorde_metaopt.gpu import torch_fomaml as tf

CONFIG_ORDER = ["cpu-fp64", "cuda-fp64", "cuda-fp32"]
CONFIG_SPEC = {
    "cpu-fp64": {"device": "cpu", "dtype": "float64"},
    "cuda-fp64": {"device": "cuda", "dtype": "float64"},
    "cuda-fp32": {"device": "cuda", "dtype": "float32"},
}

INNER_LR = 0.05
INNER_STEPS = 5
OUTER_LR = 0.02


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "UNKNOWN"


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD),
        ("PageFaultCount", ctypes.wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _process_memory() -> "_PMC | None":
    """读取当前进程 PROCESS_MEMORY_COUNTERS；非 Windows 或失败返回 None。

    注意：必须显式设置 argtypes/restype，否则 64 位进程句柄会被截断成
    c_int，GetProcessMemoryInfo 静默失败并返回 0。
    """
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(_PMC),
            ctypes.wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
        counters = _PMC()
        counters.cb = ctypes.sizeof(_PMC)
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            return None
        return counters
    except Exception:
        return None


def peak_rss_mb() -> float | None:
    """Windows 进程峰值工作集（MB）；非 Windows 或失败返回 None。"""
    counters = _process_memory()
    if counters is None:
        return None
    return float(counters.PeakWorkingSetSize) / (1024.0 * 1024.0)


def current_rss_mb() -> float | None:
    """Windows 进程当前工作集（MB）；非 Windows 或失败返回 None。"""
    counters = _process_memory()
    if counters is None:
        return None
    return float(counters.WorkingSetSize) / (1024.0 * 1024.0)


def env_info() -> dict[str, Any]:
    module = tf.require_torch()
    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "processor": platform.processor(),
        "torch": module.__version__,
        "torch_cuda_build": module.version.cuda,
        "cuda_available": bool(module.cuda.is_available()),
        "deterministic_algorithms": bool(module.are_deterministic_algorithms_enabled()),
        "threads": int(module.get_num_threads()),
        "interop_threads": int(module.get_num_interop_threads()),
    }
    if info["cuda_available"]:
        props = module.cuda.get_device_properties(0)
        info.update(
            {
                "device_name": props.name,
                "compute_capability": f"{props.major}.{props.minor}",
                "total_memory_gb": round(float(props.total_memory) / 2**30, 3),
                "device_count": int(module.cuda.device_count()),
                "cudnn_version": module.backends.cudnn.version()
                if module.backends.cudnn.is_available()
                else None,
                "cudnn_deterministic": bool(module.backends.cudnn.deterministic),
                "cudnn_benchmark": bool(module.backends.cudnn.benchmark),
            }
        )
    try:
        smi = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total,compute_cap",
                "--format=csv,noheader",
            ],
            text=True,
        ).strip()
        info["nvidia_smi"] = smi
    except Exception as exc:  # pragma: no cover - 无 nvidia-smi 环境
        info["nvidia_smi"] = f"NOT_AVAILABLE: {exc}"
    info["peak_rss_mb"] = peak_rss_mb()
    return info


class Stopwatch:
    """计时上下文：CUDA 前后同步，保证墙钟包含全部 GPU 计算。"""

    def __init__(self, device: str) -> None:
        self.device = device
        self.elapsed = 0.0
        self.peak_gpu_mb = 0.0

    def __enter__(self) -> "Stopwatch":
        module = tf.require_torch()
        if self.device == "cuda":
            module.cuda.synchronize()
            module.cuda.reset_peak_memory_stats()
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        module = tf.require_torch()
        if self.device == "cuda":
            module.cuda.synchronize()
            self.peak_gpu_mb = float(module.cuda.max_memory_allocated()) / (1024.0 * 1024.0)
        self.elapsed = time.perf_counter() - self._t0


@dataclass
class Config:
    name: str
    device: str
    dtype_name: str

    @property
    def dtype(self) -> Any:
        return tf.dtype_from_name(self.dtype_name)


def resolve_configs(names: list[str]) -> tuple[list[Config], list[dict[str, Any]]]:
    module = tf.require_torch()
    configs: list[Config] = []
    skipped: list[dict[str, Any]] = []
    for name in names:
        spec = CONFIG_SPEC.get(name)
        if spec is None:
            raise SystemExit(f"未知配置 {name!r}，允许：{CONFIG_ORDER}")
        if spec["device"] == "cuda" and not module.cuda.is_available():
            skipped.append({"name": name, "status": "NOT_RUN", "reason": "torch.cuda.is_available()=False"})
            continue
        configs.append(Config(name=name, device=spec["device"], dtype_name=spec["dtype"]))
    return configs, skipped


# ---------------------------------------------------------------------------
# 工作负载
# ---------------------------------------------------------------------------


def run_pretrain(
    config: Config,
    train_episodes: list[tf.Episode],
    val_episodes: list[tf.Episode],
    steps: int,
    batch_size: int,
    seed: int,
) -> dict[str, Any]:
    """FOMAML 元预训练 + 元验证 query RMSE；返回墙钟与统计量。"""
    module = tf.require_torch()
    params = tf.init_parameters((64, 64), seed=seed, device=config.device, dtype=config.dtype)
    rng = np.random.default_rng(int(seed))
    losses: list[float] = []
    first_grads: list[np.ndarray] | None = None
    with Stopwatch(config.device) as watch:
        for step in range(int(steps)):
            indices = rng.integers(0, len(train_episodes), size=int(batch_size))
            batch = [train_episodes[int(index)] for index in indices]
            params, stats, grads = tf.fomaml_step(
                params,
                batch,
                inner_lr=INNER_LR,
                inner_steps=INNER_STEPS,
                outer_lr=OUTER_LR,
                device=config.device,
                dtype=config.dtype,
            )
            if step == 0:
                first_grads = grads
            losses.append(float(stats["outer_loss"]))
    rmse, _ = tf.adapt_and_score(
        params, val_episodes, INNER_LR, INNER_STEPS, config.device, config.dtype
    )
    return {
        "wall_s": watch.elapsed,
        "peak_gpu_mb": watch.peak_gpu_mb,
        "loss_first": losses[0] if losses else float("nan"),
        "loss_last": losses[-1] if losses else float("nan"),
        "query_rmse": rmse,
        "params": params,
        "first_grads": first_grads,
        "nan_count": tf.count_nonfinite(params),
    }


def run_kshot(
    config: Config,
    params: list[Any],
    val_episodes: list[tf.Episode],
    k_shot: int,
    seed: int,
) -> dict[str, Any]:
    """K-shot 适应（内循环 5 步）+ query RMSE。"""
    episodes = [
        tf.Episode(
            support_x=episode.support_x[:k_shot],
            support_y=episode.support_y[:k_shot],
            query_x=episode.query_x,
            query_y=episode.query_y,
        )
        for episode in val_episodes
    ]
    with Stopwatch(config.device) as watch:
        rmse, _ = tf.adapt_and_score(
            params, episodes, INNER_LR, INNER_STEPS, config.device, config.dtype
        )
    return {"wall_s": watch.elapsed, "peak_gpu_mb": watch.peak_gpu_mb, "query_rmse": rmse, "n_tasks": len(episodes)}


def run_batch_score(
    config: Config,
    params: list[Any],
    candidates: np.ndarray,
) -> dict[str, Any]:
    """代理批量打分：一次性前向 n×12 候选点。"""
    with Stopwatch(config.device) as watch:
        prediction = tf.batch_score(params, candidates, config.device, config.dtype)
    checksum = float(np.nansum(prediction))
    return {
        "wall_s": watch.elapsed,
        "peak_gpu_mb": watch.peak_gpu_mb,
        "items": int(candidates.shape[0]),
        "checksum": checksum,
        "nan_count": int(np.size(prediction) - np.count_nonzero(np.isfinite(prediction))),
    }


def run_gemm(config: Config, size: int, iterations: int, seed: int) -> dict[str, Any]:
    """方阵 GEMM 吞吐探针：FP64/FP32 峰值量级对照（不参与算法收益声明）。"""
    module = tf.require_torch()
    generator = module.Generator(device="cpu").manual_seed(int(seed))
    a = module.rand(size, size, generator=generator, dtype=module.float64).to(config.device, config.dtype)
    b = module.rand(size, size, generator=generator, dtype=module.float64).to(config.device, config.dtype)
    def _once() -> Any:
        result = a
        for _ in range(2):
            result = result @ b
        return result
    with Stopwatch(config.device) as watch:
        for _ in range(int(iterations)):
            _once()
    flops = 2.0 * (size**3) * 2 * int(iterations)
    return {
        "wall_s": watch.elapsed,
        "peak_gpu_mb": watch.peak_gpu_mb,
        "tflops": flops / watch.elapsed / 1e12 if watch.elapsed > 0 else float("nan"),
        "size": size,
        "iterations": iterations,
    }


def grad_relative_error(reference: list[np.ndarray], other: list[np.ndarray]) -> dict[str, float]:
    """相对 L2 误差与最大绝对差（用于元梯度数值一致性）。"""
    if len(reference) != len(other):
        raise SystemExit("梯度张量数量不一致")
    diff_sq = 0.0
    ref_sq = 0.0
    max_abs = 0.0
    for ref, cur in zip(reference, other):
        delta = np.asarray(cur, dtype=np.float64) - np.asarray(ref, dtype=np.float64)
        diff_sq += float(np.sum(delta**2))
        ref_sq += float(np.sum(np.asarray(ref, dtype=np.float64) ** 2))
        max_abs = max(max_abs, float(np.max(np.abs(delta))))
    rel = math.sqrt(diff_sq / ref_sq) if ref_sq > 0 else float("inf")
    return {"rel_l2": rel, "max_abs": max_abs}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D-NEXT-001 A4 G1 FOMAML 计算设备基准（合成、零物理调用）")
    parser.add_argument("--out", required=True, help="输出 run 目录")
    parser.add_argument("--configs", default=",".join(CONFIG_ORDER))
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--pretrain-steps", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--val-tasks", type=int, default=12)
    parser.add_argument("--kshot", type=int, default=10)
    parser.add_argument("--candidates", type=int, default=200000)
    parser.add_argument("--gemm-size", type=int, default=2048)
    parser.add_argument("--gemm-iterations", type=int, default=12)
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("--tag", default="default")
    parser.add_argument("--skip-gemm", action="store_true")
    parser.add_argument("--skip-figures", action="store_true")
    args = parser.parse_args(argv)

    if args.repeat < 1:
        raise SystemExit("--repeat 必须 >= 1")
    module = tf.require_torch()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    configs, skipped = resolve_configs([name for name in args.configs.split(",") if name])

    # 固定数据：三路配置共享同一 family / episode / 候选池
    train_family = tf.make_task_family(120, seed=args.seed)
    train_episodes = tf.make_episodes(
        train_family, list(range(120)), k_shot=5, q_query=10, seed=args.seed + 1
    )
    val_family = tf.make_task_family(40, seed=args.seed + 2)
    val_episodes = tf.make_episodes(
        val_family, list(range(40)), k_shot=10, q_query=20, seed=args.seed + 3
    )
    candidates = np.random.default_rng(args.seed + 4).random((int(args.candidates), tf.N_INPUT))

    run_id = f"g1_{args.tag}_{time.strftime('%Y%m%dT%H%M%S')}"
    metrics: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "run_id": run_id,
        "task_id": "D-NEXT-001",
        "role": "A4",
        "work_package": "G1",
        "git_sha": git_sha(),
        "argv": sys.argv,
        "physical_call_count": 0,
        "source_kind": "synthetic_analogue",
        "physical_validation_status": "NOT_APPLICABLE_SYNTHETIC",
        "tag": args.tag,
        "seeds": {"family": args.seed, "episodes": args.seed + 1, "val": args.seed + 2, "candidates": args.seed + 4},
        "hyperparameters": {
            "inner_lr": INNER_LR,
            "inner_steps": INNER_STEPS,
            "outer_lr": OUTER_LR,
            "pretrain_steps": args.pretrain_steps,
            "batch_size": args.batch_size,
            "k_shot_eval": args.kshot,
            "candidates": args.candidates,
            "repeat": args.repeat,
        },
        "environment": env_info(),
        "skipped_configs": skipped,
        "configs": [config.name for config in configs],
        "results": {},
    }

    ref_grads: list[np.ndarray] | None = None
    grad_store: dict[str, list[np.ndarray]] = {}
    params_by_config: dict[str, list[Any]] = {}
    determinism: dict[str, float] = {}

    for config in configs:
        print(f"[bench] config={config.name} device={config.device} dtype={config.dtype_name}", flush=True)
        config_summary = summary["results"].setdefault(config.name, {"workloads": {}})

        # W1：FOMAML 元预训练
        pretrain_rows: list[dict[str, Any]] = []
        params: list[Any] | None = None
        for rep in range(args.repeat):
            result = run_pretrain(
                config, train_episodes, val_episodes, args.pretrain_steps, args.batch_size, args.seed
            )
            params = result["params"]
            if rep == 0:
                grad_store[config.name] = result["first_grads"] or []
            row = {
                "workload": "fomaml_pretrain",
                "config": config.name,
                "device": config.device,
                "dtype": config.dtype_name,
                "repeat": rep,
                "wall_s": result["wall_s"],
                "peak_gpu_mb": result["peak_gpu_mb"],
                "peak_rss_mb": peak_rss_mb(),
                "query_rmse": result["query_rmse"],
                "loss_first": result["loss_first"],
                "loss_last": result["loss_last"],
                "items": args.pretrain_steps * args.batch_size,
                "nan_count": result["nan_count"],
            }
            metrics.append(row)
            pretrain_rows.append(row)
            print(f"  pretrain rep{rep}: wall={result['wall_s']:.3f}s rmse={result['query_rmse']:.6f}", flush=True)
        assert params is not None
        params_by_config[config.name] = params

        # W2：K-shot 适应
        kshot_rows: list[dict[str, Any]] = []
        for rep in range(args.repeat):
            result = run_kshot(config, params, val_episodes[: args.val_tasks], args.kshot, args.seed)
            row = {
                "workload": "kshot_adapt",
                "config": config.name,
                "device": config.device,
                "dtype": config.dtype_name,
                "repeat": rep,
                "wall_s": result["wall_s"],
                "peak_gpu_mb": result["peak_gpu_mb"],
                "peak_rss_mb": peak_rss_mb(),
                "query_rmse": result["query_rmse"],
                "items": result["n_tasks"],
                "nan_count": 0,
            }
            metrics.append(row)
            kshot_rows.append(row)

        # W3：代理批量打分
        score_rows: list[dict[str, Any]] = []
        for rep in range(args.repeat):
            result = run_batch_score(config, params, candidates)
            row = {
                "workload": "surrogate_batch_score",
                "config": config.name,
                "device": config.device,
                "dtype": config.dtype_name,
                "repeat": rep,
                "wall_s": result["wall_s"],
                "peak_gpu_mb": result["peak_gpu_mb"],
                "peak_rss_mb": peak_rss_mb(),
                "query_rmse": float("nan"),
                "items": result["items"],
                "checksum": result["checksum"],
                "nan_count": result["nan_count"],
            }
            metrics.append(row)
            score_rows.append(row)

        # W0：GEMM 吞吐探针
        gemm_rows: list[dict[str, Any]] = []
        if not args.skip_gemm:
            for rep in range(args.repeat):
                result = run_gemm(config, args.gemm_size, args.gemm_iterations, args.seed)
                row = {
                    "workload": "gemm_probe",
                    "config": config.name,
                    "device": config.device,
                    "dtype": config.dtype_name,
                    "repeat": rep,
                    "wall_s": result["wall_s"],
                    "peak_gpu_mb": result["peak_gpu_mb"],
                    "peak_rss_mb": peak_rss_mb(),
                    "tflops": result["tflops"],
                    "items": args.gemm_size,
                    "nan_count": 0,
                }
                metrics.append(row)
                gemm_rows.append(row)

        def agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
            walls = [row["wall_s"] for row in rows]
            out: dict[str, Any] = {
                "wall_s_median": float(statistics.median(walls)),
                "wall_s_min": float(min(walls)),
                "wall_s_max": float(max(walls)),
                "wall_s_mean": float(statistics.fmean(walls)),
                "peak_gpu_mb": max([row["peak_gpu_mb"] for row in rows] + [0.0]),
                "peak_rss_mb": max([row["peak_rss_mb"] or 0.0 for row in rows] + [0.0]),
                "nan_count": int(sum(row["nan_count"] for row in rows)),
            }
            # gemm_probe 行没有 query_rmse 字段，聚合时按需处理
            if all("query_rmse" in row for row in rows):
                out["query_rmse_median"] = float(
                    statistics.median([row["query_rmse"] for row in rows])
                )
            return out

        pretrain_agg = agg(pretrain_rows)
        pretrain_agg["loss_first"] = float(statistics.median([row["loss_first"] for row in pretrain_rows]))
        pretrain_agg["loss_last"] = float(statistics.median([row["loss_last"] for row in pretrain_rows]))
        config_summary["workloads"]["fomaml_pretrain"] = pretrain_agg
        config_summary["workloads"]["kshot_adapt"] = agg(kshot_rows)
        config_summary["workloads"]["surrogate_batch_score"] = agg(score_rows)
        if gemm_rows:
            config_summary["workloads"]["gemm_probe"] = agg(gemm_rows)
            config_summary["workloads"]["gemm_probe"]["tflops_median"] = float(
                statistics.median([row["tflops"] for row in gemm_rows])
            )
        config_summary["score_checksum"] = float(score_rows[0]["checksum"]) if score_rows else None

        # 确定性：同种子重复之间参数最大差
        diffs = []
        for rep in range(1, args.repeat):
            rerun = run_pretrain(
                config, train_episodes, val_episodes, args.pretrain_steps, args.batch_size, args.seed
            )
            diff = max(
                float(np.max(np.abs(a.detach().to("cpu").numpy() - b.detach().to("cpu").numpy())))
                for a, b in zip(params, rerun["params"])
            )
            diffs.append(diff)
        determinism[config.name] = max(diffs) if diffs else 0.0
        config_summary["determinism_max_param_delta"] = determinism[config.name]

    # 梯度误差：以 cpu-fp64 为参考
    reference_name = "cpu-fp64" if "cpu-fp64" in grad_store else (configs[0].name if configs else None)
    grad_errors: dict[str, Any] = {}
    if reference_name is not None and grad_store.get(reference_name):
        ref_grads = grad_store[reference_name]
        for name, grads in grad_store.items():
            if name == reference_name or not grads:
                continue
            grad_errors[name] = grad_relative_error(ref_grads, grads)
            if name in summary["results"]:
                summary["results"][name]["gradient_vs_cpu_fp64"] = grad_errors[name]
        summary["results"][reference_name]["gradient_vs_cpu_fp64"] = {
            "rel_l2": 0.0,
            "max_abs": 0.0,
            "note": "reference",
        }

    # 汇总表
    summary["gradient_reference"] = reference_name
    summary["gradient_errors"] = grad_errors
    summary["determinism"] = determinism
    summary["peak_rss_mb"] = peak_rss_mb()
    summary["status"] = "COMPLETED" if configs else "NOT_RUN"

    # 写出
    with (out_dir / "metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "workload",
            "config",
            "device",
            "dtype",
            "repeat",
            "wall_s",
            "peak_gpu_mb",
            "peak_rss_mb",
            "query_rmse",
            "loss_first",
            "loss_last",
            "tflops",
            "checksum",
            "items",
            "nan_count",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in metrics:
            writer.writerow(row)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (out_dir / "run_config.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "argv": sys.argv,
                "configs": [config.name for config in configs],
                "skipped_configs": skipped,
                "physical_call_count": 0,
                "source_kind": "synthetic_analogue",
                "data_seed": args.seed,
                "git_sha": git_sha(),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # 参考梯度落盘（供 A5 独立复核 / 跨构建比对）
    grad_dir = out_dir / "gradients"
    grad_dir.mkdir(exist_ok=True)
    for name, grads in grad_store.items():
        for index, grad in enumerate(grads):
            np.save(grad_dir / f"{name}_grad_{index}.npy", grad)
    if ref_grads is not None:
        (grad_dir / "gradient_index.json").write_text(
            json.dumps(
                {
                    "reference": reference_name,
                    "configs": list(grad_store),
                    "tensors_per_config": len(ref_grads),
                    "sha256_note": "元梯度按张量顺序保存，可用 numpy.load 复算相对误差",
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # 数据清单与 SHA256
    files: list[dict[str, Any]] = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append({"path": str(path.relative_to(out_dir)), "bytes": path.stat().st_size, "sha256": digest})
    (out_dir / "data_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "physical_call_count": 0,
                "source_kind": "synthetic_analogue",
                "files": files,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with (out_dir / "SHA256SUMS.txt").open("w", encoding="utf-8") as handle:
        for entry in files:
            handle.write(f"{entry['sha256']}  {entry['path']}\n")

    if not args.skip_figures:
        try:
            from research.concorde_metaopt.gpu.make_figures import make_figures

            make_figures(out_dir)
        except Exception as exc:
            (out_dir / "figures").mkdir(exist_ok=True)
            (out_dir / "figures" / "NOT_RUN.txt").write_text(
                f"图未生成：{type(exc).__name__}: {exc}\n", encoding="utf-8"
            )
    print(json.dumps({"status": summary["status"], "run_dir": str(out_dir), "gradient_errors": grad_errors}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
