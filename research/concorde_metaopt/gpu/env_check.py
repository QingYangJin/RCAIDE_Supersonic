"""D-NEXT-001 A4｜G0 独立 CUDA 环境自检（零物理调用）。

用途：在 D:\RCAIDE\dnext001\gpu-env 的独立 venv 中核对
  * 版本/驱动/计算能力/设备信息；
  * FP32 与 FP64 的前向/反向是否真实在 GPU 上执行，且与 CPU float64 参考一致；
  * 同种子重复运行的确定性；
  * GEMM 吞吐探针（FP32/FP64，用于诚实报告 RTX 5060 的 FP64 能力）；
  * 峰值显存。
输出 JSON 供中文环境报告引用。

用法：
  D:\RCAIDE\dnext001\gpu-env\Scripts\python.exe -m research.concorde_metaopt.gpu.env_check \
      --out research/concorde_metaopt/gpu/reports/g0_env_check.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import numpy as np

from research.concorde_metaopt.gpu import torch_fomaml as tf

PHYSICAL_CALL_COUNT = 0


def nvidia_smi(query: str) -> str | None:
    try:
        return subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"],
            text=True,
            timeout=30,
        ).strip()
    except Exception:
        return None


def device_report(torch) -> dict[str, Any]:
    available = bool(torch.cuda.is_available())
    info: dict[str, Any] = {
        "python": sys_version(),
        "executable": os.sys.executable,
        "platform": platform.platform(),
        "torch_version": torch.__version__,
        "torch_cuda_build": torch.version.cuda,
        "torch_cudnn": torch.backends.cudnn.version(),
        "cuda_available": available,
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "nvidia_smi_name_driver": nvidia_smi("name,driver_version"),
        "nvidia_smi_memory_total_mib": nvidia_smi("memory.total"),
        "nvidia_smi_compute_cap": nvidia_smi("compute_cap"),
    }
    if available:
        info.update(
            {
                "device_count": torch.cuda.device_count(),
                "device_name": torch.cuda.get_device_name(0),
                "device_capability": list(torch.cuda.get_device_capability(0)),
                "device_total_memory_mb": round(
                    torch.cuda.get_device_properties(0).total_memory / (1024.0**2), 1
                ),
                "device_multiprocessors": torch.cuda.get_device_properties(0).multi_processor_count,
                "cudnn_enabled": bool(torch.backends.cudnn.enabled),
                "cudnn_version": torch.backends.cudnn.version(),
            }
        )
    return info


def sys_version() -> str:
    import sys

    return sys.version.split()[0]


def fp_forward_backward(torch, dtype_name: str, device: str) -> dict[str, Any]:
    """线性层前向/反向：GPU 结果与 CPU float64 参考比较。

    返回最大绝对误差、相对误差、梯度是否有限、梯度是否非零（证明反向真的执行）。
    """
    torch.manual_seed(20261110)
    dtype = tf.dtype_from_name(dtype_name)
    dev = torch.device(device)
    x_cpu = torch.randn(512, 256, dtype=torch.float64)
    w_cpu = torch.randn(256, 256, dtype=torch.float64) * 0.05

    # CPU float64 参考
    x_ref = x_cpu.clone().requires_grad_(True)
    w_ref = w_cpu.clone().requires_grad_(True)
    y_ref = x_ref @ w_ref
    loss_ref = (y_ref * y_ref).sum()
    loss_ref.backward()

    x = x_cpu.to(device=dev, dtype=dtype).clone().requires_grad_(True)
    w = w_cpu.to(device=dev, dtype=dtype).clone().requires_grad_(True)
    y = x @ w
    loss = (y * y).sum()
    loss.backward()

    y_gpu = y.detach().to("cpu", dtype=torch.float64)
    gx_gpu = x.grad.detach().to("cpu", dtype=torch.float64)
    gw_gpu = w.grad.detach().to("cpu", dtype=torch.float64)
    out_scale = float(y_ref.abs().max())
    grad_scale = float(w_ref.grad.abs().max())
    return {
        "device": device,
        "dtype": dtype_name,
        "forward_max_abs_error": float((y_gpu - y_ref.detach()).abs().max()),
        "forward_rel_error": float(
            (y_gpu - y_ref.detach()).abs().max() / max(out_scale, 1e-30)
        ),
        "grad_w_max_abs_error": float((gw_gpu - w_ref.grad).abs().max()),
        "grad_w_rel_error": float(
            (gw_gpu - w_ref.grad).abs().max() / max(grad_scale, 1e-30)
        ),
        "grad_x_max_abs_error": float((gx_gpu - x_ref.grad).abs().max()),
        "grad_x_rel_error": float(
            (gx_gpu - x_ref.grad).abs().max() / max(float(x_ref.grad.abs().max()), 1e-30)
        ),
        "grad_w_finite": bool(torch.isfinite(w.grad).all().item()),
        "grad_w_nonzero": bool((w.grad.abs().sum().item()) > 0),
        "executed_on_device": str(w.device),
        "precision_note": "FP32 在 GPU 上的误差应与 float32 舍入量级一致（~1e-5 相对）",
    }


def determinism_check(torch, dtype_name: str, device: str, repeats: int = 3) -> dict[str, Any]:
    dtype = tf.dtype_from_name(dtype_name)
    dev = torch.device(device)
    results: list[np.ndarray] = []
    for _ in range(repeats):
        torch.manual_seed(4242)
        x = torch.randn(1024, 512, device=dev, dtype=dtype)
        w = torch.randn(512, 512, device=dev, dtype=dtype) * 0.02
        w.requires_grad_(True)
        y = x @ w
        loss = (y * y).sum()
        loss.backward()
        results.append(w.grad.detach().to("cpu", dtype=torch.float64).numpy().copy())
    deltas = [
        float(np.abs(results[0] - other).max()) for other in results[1:]
    ]
    return {
        "device": device,
        "dtype": dtype_name,
        "repeats": repeats,
        "max_grad_delta_between_repeats": max(deltas) if deltas else 0.0,
        "bitwise_identical": bool(all(d == 0.0 for d in deltas)),
        "cudnn_benchmark": bool(torch.backends.cudnn.benchmark),
        "cudnn_deterministic": bool(torch.backends.cudnn.deterministic),
    }


def gemm_probe(torch, dtype_name: str, device: str, size: int, iterations: int) -> dict[str, Any]:
    """方阵 GEMM 吞吐探针（FLOPs 按 2*N^3 计）。"""
    dtype = tf.dtype_from_name(dtype_name)
    dev = torch.device(device)
    if device == "cuda":
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
    a = torch.randn(size, size, device=dev, dtype=dtype)
    b = torch.randn(size, size, device=dev, dtype=dtype)
    for _ in range(2):  # 预热
        c = a @ b
    if device == "cuda":
        torch.cuda.synchronize()
    start = time.perf_counter()
    for _ in range(iterations):
        c = a @ b
    if device == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    flops = 2.0 * size**3 * iterations
    out: dict[str, Any] = {
        "device": device,
        "dtype": dtype_name,
        "size": size,
        "iterations": iterations,
        "wall_s": elapsed,
        "gflops": flops / elapsed / 1e9,
        "checksum": float(c.double().abs().sum().item()) if device == "cpu" else None,
    }
    if device == "cuda":
        out["peak_memory_allocated_mb"] = round(
            torch.cuda.max_memory_allocated() / (1024.0**2), 1
        )
        out["peak_memory_reserved_mb"] = round(
            torch.cuda.max_memory_reserved() / (1024.0**2), 1
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G0 CUDA 环境自检（physical_call_count=0）")
    parser.add_argument(
        "--out",
        default="research/concorde_metaopt/gpu/reports/g0_env_check.json",
        help="输出 JSON 路径",
    )
    parser.add_argument("--gemm-size", type=int, default=2048)
    parser.add_argument("--gemm-iterations", type=int, default=10)
    args = parser.parse_args(argv)

    torch = tf.require_torch()
    report: dict[str, Any] = {
        "kind": "dnext001_g0_env_check",
        "physical_call_count": PHYSICAL_CALL_COUNT,
        "data_source": "synthetic",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "device": device_report(torch),
        "forward_backward": [],
        "determinism": [],
        "gemm": [],
    }

    devices = ["cpu"]
    if torch.cuda.is_available():
        devices.append("cuda")
    for device in devices:
        for dtype_name in ("float64", "float32"):
            report["forward_backward"].append(
                fp_forward_backward(torch, dtype_name, device)
            )
            report["determinism"].append(determinism_check(torch, dtype_name, device))
            report["gemm"].append(
                gemm_probe(torch, dtype_name, device, args.gemm_size, args.gemm_iterations)
            )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
