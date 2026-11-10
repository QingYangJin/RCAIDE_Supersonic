"""CPU 并发吞吐基准：BO/DE/PSO 多进程并发上限与资源隔离证据。

设计要点
--------
* 每个工作进程只做代理模型批量打分（BO/DE/PSO 内层最热的操作），单进程内强制
  单线程（torch.set_num_threads(1) 且 OMP/MKL_NUM_THREADS=1），因此"进程数"近似
  "物理核心占用数"，可用来判断超线程/超订的风险。
* 所有进程通过 multiprocessing.Barrier 同时起跑，父进程记录同步后的墙钟，
  避免串行启动造成的低估。
* 记录每个进程的峰值 RSS（psapi）用于 RAM 上限估算（32 GB 机器）。
* 结论只用于资源隔离建议；不是算法收益，也不是 GPU 相关结论。
"""

from __future__ import annotations

import argparse
import ctypes
import json
import multiprocessing as mp
import os
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_OUT_ROOT = Path(__file__).resolve().parent / "runs"
N_CANDIDATES = 4000
HIDDEN = 128
ITERATIONS = 20
SEED = 20261110
N_INPUT = 12


@dataclass
class WorkerResult:
    proc_index: int
    pid: int
    wall_s: float
    peak_rss_mb: float
    throughput_candidates_per_s: float
    checksum: float


def _peak_rss_mb() -> float:
    try:
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
            ctypes.wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = ctypes.wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        ok = psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.PeakWorkingSetSize / (1024.0 * 1024.0)
    except Exception:  # pragma: no cover - 非 Windows 或 psapi 不可用
        try:
            import resource

            return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0
        except Exception:
            return float("nan")


def _load_torch():
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    import torch

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    return torch


def _make_inputs(torch):
    generator = torch.Generator(device="cpu").manual_seed(SEED)
    x = torch.randn((N_CANDIDATES, N_INPUT), generator=generator, dtype=torch.float64)
    w1 = torch.randn((N_INPUT, HIDDEN), generator=generator, dtype=torch.float64) * 0.1
    b1 = torch.zeros(HIDDEN, dtype=torch.float64)
    w2 = torch.randn((HIDDEN, HIDDEN), generator=generator, dtype=torch.float64) * 0.05
    b2 = torch.zeros(HIDDEN, dtype=torch.float64)
    w3 = torch.randn((HIDDEN, 1), generator=generator, dtype=torch.float64) * 0.05
    return x, w1, b1, w2, b2, w3


def _score(torch, x, w1, b1, w2, b2, w3):
    h1 = torch.tanh(x @ w1 + b1)
    h2 = torch.tanh(h1 @ w2 + b2)
    return (h2 @ w3).squeeze(-1)


def _workload(torch, x, w1, b1, w2, b2, w3) -> float:
    total = 0.0
    for _ in range(ITERATIONS):
        out = _score(torch, x, w1, b1, w2, b2, w3)
        total += float(out.sum().item())
    return total


def _worker(index: int, barrier, result_queue) -> None:
    torch = _load_torch()
    inputs = _make_inputs(torch)
    barrier.wait()
    start = time.perf_counter()
    checksum = _workload(torch, *inputs)
    wall = time.perf_counter() - start
    result_queue.put(
        asdict(
            WorkerResult(
                proc_index=index,
                pid=os.getpid(),
                wall_s=wall,
                peak_rss_mb=_peak_rss_mb(),
                throughput_candidates_per_s=N_CANDIDATES * ITERATIONS / wall,
                checksum=checksum,
            )
        )
    )


def _cpu_model() -> str:
    try:
        import subprocess

        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        text = completed.stdout.strip().splitlines()
        if text:
            return text[0].strip()
    except Exception:
        pass
    return platform.processor() or "UNKNOWN"


def run_sweep(procs_list: list[int], out_dir: Path) -> dict[str, Any]:
    ctx = mp.get_context("spawn")
    rows: list[dict[str, Any]] = []
    baseline_throughput: float | None = None
    for procs in procs_list:
        barrier = ctx.Barrier(procs + 1)
        queue = ctx.Queue()
        processes = [
            ctx.Process(target=_worker, args=(index, barrier, queue))
            for index in range(procs)
        ]
        for process in processes:
            process.start()
        barrier.wait()  # 所有 worker 就绪后同时放行
        start = time.perf_counter()
        for process in processes:
            process.join(timeout=600)
        wall = time.perf_counter() - start
        results = [WorkerResult(**queue.get(timeout=30)) for _ in range(procs)]
        for process in processes:
            if process.is_alive():  # pragma: no cover - 防御
                process.terminate()
        aggregate = procs * N_CANDIDATES * ITERATIONS
        throughput = aggregate / wall
        if procs == 1:
            baseline_throughput = throughput
        efficiency = (
            throughput / (baseline_throughput * procs) if baseline_throughput else float("nan")
        )
        rows.append(
            {
                "processes": procs,
                "wall_s": wall,
                "aggregate_candidates": aggregate,
                "throughput_candidates_per_s": throughput,
                "per_process_throughput_candidates_per_s": statistics.mean(
                    r.throughput_candidates_per_s for r in results
                ),
                "parallel_efficiency": efficiency,
                "mean_worker_wall_s": statistics.mean(r.wall_s for r in results),
                "max_worker_peak_rss_mb": max(r.peak_rss_mb for r in results),
                "sum_worker_peak_rss_mb": sum(r.peak_rss_mb for r in results),
                "checksum_spread": max(r.checksum for r in results)
                - min(r.checksum for r in results),
                "pids": [r.pid for r in results],
            }
        )
        print(
            f"[cpu-concurrency] procs={procs} wall={wall:.3f}s "
            f"throughput={throughput:.1f} cand/s efficiency={efficiency:.3f}"
        )
    summary = {
        "kind": "cpu_concurrency_sweep",
        "physical_call_count": 0,
        "data_source": "synthetic",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workload": {
            "description": "单线程 torch FP64 三层 MLP 批量代理打分",
            "n_candidates": N_CANDIDATES,
            "hidden": HIDDEN,
            "iterations": ITERATIONS,
            "n_input": N_INPUT,
            "threads_per_process": 1,
        },
        "machine": {
            "cpu": _cpu_model(),
            "logical_cpus": os.cpu_count(),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "rows": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "cpu_concurrency.csv").open("w", encoding="utf-8", newline="") as handle:
        import csv

        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (json.dumps(value) if isinstance(value, list) else value)
                    for key, value in row.items()
                }
            )
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def _plot(summary: dict[str, Any], out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for font in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"):
        if any(font == item.name for item in matplotlib.font_manager.fontManager.ttflist):
            matplotlib.rcParams["font.sans-serif"] = [font]
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
    rows = summary["rows"]
    procs = [row["processes"] for row in rows]
    throughput = [row["throughput_candidates_per_s"] for row in rows]
    efficiency = [row["parallel_efficiency"] * 100.0 for row in rows]
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    axes[0].plot(procs, throughput, marker="o", color="#1f77b4")
    axes[0].plot(procs, [procs[0] and throughput[0] * p for p in procs], "--", color="#999999", label="线性理想")
    axes[0].set_xlabel("并发进程数（每进程 1 线程）")
    axes[0].set_ylabel("聚合吞吐（候选/秒）")
    axes[0].set_title("代理批量打分聚合吞吐")
    axes[0].set_xticks(procs)
    axes[0].legend()
    axes[0].grid(alpha=0.3)
    axes[1].bar([str(p) for p in procs], efficiency, color="#2ca02c")
    axes[1].axhline(100.0, color="#999999", linestyle="--")
    axes[1].set_xlabel("并发进程数")
    axes[1].set_ylabel("并行效率（%）")
    axes[1].set_title("相对单进程的并行效率")
    axes[1].grid(axis="y", alpha=0.3)
    figure.suptitle("CPU 并发基准（合成负载，physical_call_count=0）")
    figure.tight_layout()
    figure.savefig(out_dir / "fig_cpu_concurrency.png", dpi=140)
    plt.close(figure)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--procs",
        type=int,
        nargs="+",
        default=[1, 2, 4, 8, 16],
        help="要测试的并发进程数列表",
    )
    parser.add_argument("--out", type=Path, default=None, help="输出目录")
    parser.add_argument("--tag", default=None, help="输出目录标签")
    parser.add_argument("--skip-figures", action="store_true")
    arguments = parser.parse_args(argv)
    tag = arguments.tag or datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = arguments.out or (DEFAULT_OUT_ROOT / f"cpu_concurrency_{tag}")
    summary = run_sweep(sorted(set(arguments.procs)), out_dir)
    if not arguments.skip_figures:
        try:
            _plot(summary, out_dir)
        except Exception as error:  # pragma: no cover - 绘图失败不应掩盖数据
            print(f"[cpu-concurrency] 绘图失败：{error}", file=sys.stderr)
    print(json.dumps({"status": "COMPLETED", "out_dir": str(out_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
