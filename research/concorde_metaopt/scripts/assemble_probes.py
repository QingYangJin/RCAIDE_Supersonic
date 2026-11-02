"""Assemble raw shell probe files into the JSON consumed by the P0 audit.

This script performs no file operations beyond reading the probe directory and
writing shell_probes.json. It never launches a process.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _read_rc(path: Path):
    text = _read_text(path).strip()
    try:
        return int(text)
    except ValueError:
        return None


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def assemble(probe_dir: Path) -> dict:
    status_text = _read_text(probe_dir / "git_status.txt")
    status_lines = [line for line in status_text.splitlines() if line.strip()]
    git = {
        "head_sha": _first_line(_read_text(probe_dir / "git_head.txt")) or None,
        "branch": _first_line(_read_text(probe_dir / "git_branch.txt")) or None,
        "status_lines": status_lines,
        "returncodes": {
            "head": _read_rc(probe_dir / "git_head.rc"),
            "branch": _read_rc(probe_dir / "git_branch.rc"),
            "status": _read_rc(probe_dir / "git_status.rc"),
        },
    }
    tools = {
        "su2_cfd": {
            "version_text": _first_line(_read_text(probe_dir / "su2_help.txt")),
            "returncode": _read_rc(probe_dir / "su2_help.rc"),
            "raw_file": "su2_help.txt",
        },
        "gmsh": {
            "version_text": _first_line(_read_text(probe_dir / "gmsh_version.txt")),
            "returncode": _read_rc(probe_dir / "gmsh_version.rc"),
            "raw_file": "gmsh_version.txt",
        },
    }
    interpreters = []
    for label, python in [
        ("suave", r"D:\Anaconda\envs\SUAVE\python.exe"),
        ("anaconda", r"D:\Anaconda\python.exe"),
    ]:
        raw = _read_text(probe_dir / ("openvsp_" + label + ".txt"))
        version_raw = _read_text(probe_dir / ("py_" + label + ".txt"))
        entry = {
            "python": python,
            "probe": {
                "stdout": raw.strip()[-4000:],
                "returncode": _read_rc(probe_dir / ("openvsp_" + label + ".rc")),
                "version_stdout": version_raw.strip()[-2000:],
            },
        }
        extra = _read_text(probe_dir / ("openvsp_" + label + "_with_libxml2.txt"))
        if extra:
            entry["probe_with_system_libxml2"] = {
                "stdout": extra.strip()[-4000:],
                "raw_file": "openvsp_" + label + "_with_libxml2.txt",
            }
        interpreters.append(entry)
    tools["openvsp_python_binding"] = {
        "external_interpreters": interpreters,
        "sys_path_roots": [
            r"D:\Program Files\OpenVSP\OpenVSP-3.26.1-win64-Python3.9\OpenVSP-3.26.1-win64\python",
            r"D:\Program Files\OpenVSP\OpenVSP-3.26.1-win64-Python3.9\OpenVSP-3.26.1-win64\python\openvsp",
            r"D:\Program Files\OpenVSP\OpenVSP-3.26.1-win64-Python3.9\OpenVSP-3.26.1-win64\python\degen_geom",
            r"D:\Program Files\OpenVSP\OpenVSP-3.26.1-win64-Python3.9\OpenVSP-3.26.1-win64\python\utilities",
        ],
    }
    return {
        "probe_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "probe_dir": str(probe_dir),
        "git": git,
        "tools": tools,
    }


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: assemble_probes.py <probe_dir> [output_json]", file=sys.stderr)
        return 2
    probe_dir = Path(argv[0])
    output = Path(argv[1]) if len(argv) > 1 else probe_dir / "shell_probes.json"
    payload = assemble(probe_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
