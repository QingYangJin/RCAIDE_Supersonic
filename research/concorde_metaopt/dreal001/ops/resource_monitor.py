"""CPU and memory sampling for the D-REAL-EXP-003 runs.

Issue #15 was accepted with an explicit requirement: the optimization work must
record the CPU and memory load it actually incurs. psutil is not installed in
this environment, so the sampler uses only ctypes against kernel32/psapi:

* CPU busy fraction comes from GetSystemTimes deltas (idle/kernel/user), which is
  the same quantity Task Manager reports for total processor utilisation.
* Physical memory comes from GlobalMemoryStatusEx (load percent, total, available).
* Per-process working set comes from EnumProcesses + OpenProcess +
  GetProcessMemoryInfo, filtered to the interpreter and the VSPAERO/OpenVSP
  children of this run so the numbers are attributable to the work being done.

The monitor is deliberately dependency free and fails closed on Windows-only
APIs: on another platform it records `platform_unsupported` and no samples.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import json
import os
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

SCHEMA = "dreal005.resource_sample.v1"

_INTERESTING_NAME_TOKENS: Sequence[str] = (
    "python", "vspaero", "vspscript", "openvsp",
)

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_PROCESS_VM_READ = 0x0010


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD),
                ("dwHighDateTime", wintypes.DWORD)]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
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


def _filetime_to_seconds(value: _FILETIME) -> float:
    ticks = (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)
    return ticks / 1e7


class _Sampler:
    """Thin ctypes wrapper; raises RuntimeError when the platform lacks the APIs."""

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("resource sampling uses Windows kernel32 APIs")
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self._kernel32.GetSystemTimes.argtypes = [
            ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME), ctypes.POINTER(_FILETIME)]
        self._kernel32.GetSystemTimes.restype = wintypes.BOOL
        self._kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
        self._kernel32.GlobalMemoryStatusEx.restype = wintypes.BOOL
        # EnumProcesses/GetProcessMemoryInfo live in psapi, not k32 in every build.
        self._psapi.EnumProcesses.argtypes = [
            ctypes.POINTER(wintypes.DWORD), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self._psapi.EnumProcesses.restype = wintypes.BOOL
        self._kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self._kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self._psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(_PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
        self._psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    # -- CPU -----------------------------------------------------------------
    def system_times(self) -> Dict[str, float]:
        idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
        if not self._kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {
            "idle": _filetime_to_seconds(idle),
            "kernel": _filetime_to_seconds(kernel),
            "user": _filetime_to_seconds(user),
        }

    # -- memory --------------------------------------------------------------
    def memory(self) -> Dict[str, Any]:
        status = _MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if not self._kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        return {
            "load_percent": float(status.dwMemoryLoad),
            "total_phys_bytes": int(status.ullTotalPhys),
            "available_phys_bytes": int(status.ullAvailPhys),
            "used_phys_bytes": int(status.ullTotalPhys - status.ullAvailPhys),
        }

    # -- processes -----------------------------------------------------------
    def processes(self) -> List[Dict[str, Any]]:
        capacity = 4096
        buffer = (wintypes.DWORD * capacity)()
        needed = wintypes.DWORD()
        if not self._psapi.EnumProcesses(
                buffer, ctypes.sizeof(buffer), ctypes.byref(needed)):
            raise ctypes.WinError(ctypes.get_last_error())
        count = needed.value // ctypes.sizeof(wintypes.DWORD)
        rows: List[Dict[str, Any]] = []
        for index in range(min(count, capacity)):
            pid = int(buffer[index])
            if pid <= 0:
                continue
            handle = self._kernel32.OpenProcess(
                _PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_VM_READ, False, pid)
            if not handle:
                continue
            try:
                name_buffer = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(len(name_buffer))
                if not self._kernel32.QueryFullProcessImageNameW(
                        handle, 0, name_buffer, ctypes.byref(size)):
                    continue
                image = name_buffer.value
            finally:
                self._kernel32.CloseHandle(handle)
            lowered = os.path.basename(image).lower()
            if not any(token in lowered for token in _INTERESTING_NAME_TOKENS):
                continue
            handle = self._kernel32.OpenProcess(
                _PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_VM_READ, False, pid)
            if not handle:
                continue
            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
            try:
                ok = self._psapi.GetProcessMemoryInfo(
                    handle, ctypes.byref(counters), counters.cb)
                working_set = int(counters.WorkingSetSize) if ok else None
            finally:
                self._kernel32.CloseHandle(handle)
            rows.append({"pid": pid, "image": os.path.basename(image),
                         "working_set_bytes": working_set})
        return rows


class ResourceMonitor:
    """Sample CPU/memory on a background thread and persist JSONL samples."""

    def __init__(self, out_path: Path, *, interval_s: float = 1.0,
                 label: str = "", include_processes: bool = True) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        self.out_path = Path(out_path)
        self.interval_s = float(interval_s)
        self.label = label
        self.include_processes = include_processes
        self._sampler: Optional[_Sampler] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._samples: List[Dict[str, Any]] = []
        self._previous: Optional[Dict[str, float]] = None
        self._failure: Optional[str] = None
        self._lock = threading.Lock()

    # -- lifecycle -----------------------------------------------------------
    def __enter__(self) -> "ResourceMonitor":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def start(self) -> None:
        try:
            self._sampler = _Sampler()
        except Exception as exc:  # noqa: BLE001 - record and continue without sampling
            self._failure = "%s: %s" % (type(exc).__name__, exc)
            return
        try:
            self.out_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - sampling must not kill the run
            self._failure = "cannot create %s: %s: %s" % (
                self.out_path.parent, type(exc).__name__, exc)
            return
        self._thread = threading.Thread(target=self._loop, name="resource-monitor",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None
        summary = self.summary()
        payload = dict(summary)
        payload["out_path"] = str(self.out_path)
        payload["failure"] = self._failure
        if self._samples:
            self.out_path.with_suffix(".summary.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8")
        return payload

    # -- sampling ------------------------------------------------------------
    def _loop(self) -> None:
        try:
            handle = self.out_path.open("a", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - sampling must not kill the run
            self._failure = "cannot open %s: %s: %s" % (
                self.out_path, type(exc).__name__, exc)
            return
        try:
            while not self._stop.is_set():
                sample = self.sample_once()
                if sample is not None:
                    handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    handle.flush()
                self._stop.wait(self.interval_s)
        finally:
            handle.close()

    def sample_once(self) -> Optional[Dict[str, Any]]:
        if self._sampler is None:
            return None
        times = self._sampler.system_times()
        memory = self._sampler.memory()
        cpu_fraction: Optional[float] = None
        if self._previous is not None:
            idle_delta = times["idle"] - self._previous["idle"]
            total_delta = (times["kernel"] + times["user"]) - (
                self._previous["kernel"] + self._previous["user"])
            if total_delta > 0:
                cpu_fraction = max(0.0, min(1.0, 1.0 - idle_delta / total_delta))
        self._previous = times
        processes = self._sampler.processes() if self.include_processes else []
        working_set = sum(
            row["working_set_bytes"] for row in processes
            if row.get("working_set_bytes") is not None)
        sample = {
            "schema": SCHEMA,
            "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "label": self.label,
            "cpu_busy_fraction": cpu_fraction,
            "memory_load_percent": memory["load_percent"],
            "phys_used_bytes": memory["used_phys_bytes"],
            "phys_total_bytes": memory["total_phys_bytes"],
            "phys_available_bytes": memory["available_phys_bytes"],
            "tracked_process_count": len(processes),
            "tracked_working_set_bytes": working_set if processes else 0,
            "processes": sorted(
                (row for row in processes if row.get("working_set_bytes") is not None),
                key=lambda row: -int(row["working_set_bytes"]))[:8],
        }
        with self._lock:
            self._samples.append(sample)
        return sample

    # -- summary -------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
        cpu = [s["cpu_busy_fraction"] for s in samples if s["cpu_busy_fraction"] is not None]
        mem_load = [s["memory_load_percent"] for s in samples]
        ws = [s["tracked_working_set_bytes"] for s in samples]
        n = len(samples)
        summary: Dict[str, Any] = {
            "schema": "dreal005.resource_summary.v1",
            "label": self.label,
            "platform": platform.system(),
            "sampler": "ctypes kernel32 GetSystemTimes/GlobalMemoryStatusEx/psapi",
            "interval_s": self.interval_s,
            "sample_count": n,
            "cpu_available": bool(cpu),
            "cpu_busy_fraction_mean": (sum(cpu) / len(cpu)) if cpu else None,
            "cpu_busy_fraction_max": max(cpu) if cpu else None,
            "cpu_busy_fraction_min": min(cpu) if cpu else None,
            "memory_load_percent_mean": (sum(mem_load) / len(mem_load)) if mem_load else None,
            "memory_load_percent_max": max(mem_load) if mem_load else None,
            "phys_used_bytes_mean": (
                sum(s["phys_used_bytes"] for s in samples) / n) if n else None,
            "phys_used_bytes_max": max((s["phys_used_bytes"] for s in samples), default=None),
            "tracked_working_set_bytes_mean": (sum(ws) / len(ws)) if ws else None,
            "tracked_working_set_bytes_max": max(ws) if ws else None,
            "tracked_process_count_max": max(
                (s["tracked_process_count"] for s in samples), default=0),
            "first_utc": samples[0]["utc"] if samples else None,
            "last_utc": samples[-1]["utc"] if samples else None,
            "note": (
                "cpu_busy_fraction is total system processor utilisation from "
                "GetSystemTimes deltas; it is a host-wide figure, not a per-run share. "
                "tracked_working_set_bytes covers only python/vspaero/openvsp processes "
                "and is therefore a lower bound on this run's memory footprint."),
        }
        return summary


def sample_blocking(duration_s: float, interval_s: float = 1.0,
                    label: str = "probe") -> List[Dict[str, Any]]:
    """Sample for a fixed wall time; used by the sampler self-test."""
    monitor = ResourceMonitor(Path(os.devnull), interval_s=interval_s, label=label)
    monitor.start()
    try:
        time.sleep(duration_s)
    finally:
        monitor.stop()
    return monitor._samples  # noqa: SLF001 - test convenience