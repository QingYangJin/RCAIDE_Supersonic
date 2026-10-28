"""P0 read-only audit for the Concorde Phase I contract (RCAIDE_Supersonic Issue #1).

The audit records environment and source facts and produces an explicit blocker
list. It never runs a Mission, a CFD case or an optimization. Anything that is
not observed is stored as null or as an error entry, never as a pass.
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.metadata as md
import inspect
import json
import os
import platform
import pkgutil
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1"
STAGE = "P0"

KEY_PACKAGES = [
    "RCAIDE-LEADS", "rcaide-gui", "numpy", "scipy", "matplotlib", "pandas",
    "torch", "maml-opt", "rcaide-cpacs", "rcaide-multifidelity", "scikit-learn",
    "vtk", "pyvista", "h5py", "PyQt6", "pytest", "shapely", "trimesh",
]

IMPORT_MODULES = {
    "RCAIDE-LEADS": "RCAIDE",
    "rcaide-gui": "rcaide_gui",
    "maml-opt": "maml_opt",
    "rcaide-multifidelity": "rcaide_cfd",
    "rcaide-cpacs": "rcaide_cpacs",
    "numpy": "numpy",
    "scipy": "scipy",
    "torch": "torch",
    "matplotlib": "matplotlib",
}

CONCORDE_REL = Path("tutorials") / "Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission" / "Concorde.py"

EXTERNAL_TOOLS = {
    "su2_cfd": {
        "paths": [r"D:\Program Files\SU2\SU2-v8.5.0-win64-mpi\win64-mpi\bin\SU2_CFD.exe"],
        "probe": ["--help"],
        "kind": "solver",
    },
    "gmsh": {
        "paths": [r"D:\Program Files\GMesh\gmsh-4.15.2-Windows64\gmsh-4.15.2-Windows64\gmsh.exe"],
        "probe": ["--version"],
        "kind": "mesher",
    },
    "openvsp_gui": {
        "paths": [r"D:\Program Files\OpenVSP\OpenVSP-3.26.1-win64-Python3.9\OpenVSP-3.26.1-win64\vsp.exe"],
        "probe": None,
        "kind": "geometry_gui",
    },
}

OPENVSP_PYTHON_CANDIDATES = [
    r"D:\Anaconda\envs\SUAVE\python.exe",
    r"D:\Anaconda\python.exe",
]
OPENVSP_API_PARENT_CANDIDATES = [
    r"D:\Program Files\OpenVSP\OpenVSP-3.26.1-win64-Python3.9\OpenVSP-3.26.1-win64\python",
]
TOOLS_LOCAL_NAMES = ["tools.local.json"]

MAML_SOURCE_PATHS = ["maml_opt", "maml-opt", "maml_opt-0.1.0.dist-info"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd, cwd=None, timeout=60) -> dict:
    started = time.time()
    try:
        proc = subprocess.run(
            [str(part) for part in cmd],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        return {
            "cmd": [str(part) for part in cmd],
            "returncode": proc.returncode,
            "stdout": proc.stdout[-8000:],
            "stderr": proc.stderr[-8000:],
            "timed_out": False,
            "seconds": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": [str(part) for part in cmd],
            "returncode": None,
            "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "timed_out": True,
            "seconds": round(time.time() - started, 3),
        }
    except Exception as exc:  # pragma: no cover - depends on host
        return {
            "cmd": [str(part) for part in cmd],
            "returncode": None,
            "stdout": "",
            "stderr": type(exc).__name__ + ": " + str(exc),
            "timed_out": False,
            "seconds": round(time.time() - started, 3),
        }


def _safe(label: str, fn):
    try:
        return fn()
    except Exception as exc:  # pragma: no cover - defensive
        return {"error": type(exc).__name__ + ": " + str(exc), "traceback": traceback.format_exc()[-4000:], "label": label}


def _distribution_info(name: str) -> dict:
    info = {"name": name, "version": None, "location": None, "direct_url": None, "error": None}
    try:
        dist = md.distribution(name)
        info["version"] = dist.version
        try:
            info["location"] = str(dist.locate_file(""))
        except Exception:
            info["location"] = None
        files = dist.files or []
        info["py_file_count"] = sum(1 for f in files if str(f).endswith(".py"))
        try:
            raw = dist.read_text("direct_url.json")
            info["direct_url"] = json.loads(raw) if raw else None
        except Exception:
            info["direct_url"] = None
    except Exception as exc:
        info["error"] = type(exc).__name__ + ": " + str(exc)
    return info


def discover_git(repo_root: Path, shell_probes=None) -> dict:
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo_root)
    branch = _run(["git", "branch", "--show-current"], cwd=repo_root)
    status = _run(["git", "status", "--porcelain=v1"], cwd=repo_root)
    status_lines = [line for line in (status["stdout"] or "").splitlines() if line.strip()]
    result = {
        "head_sha": (head["stdout"] or "").strip() or None,
        "branch": (branch["stdout"] or "").strip() or None,
        "dirty": bool(status_lines),
        "status_lines": status_lines,
        "status_error": status["stderr"].strip() or None if status["returncode"] not in (0, None) else None,
        "commands": {"head": head, "branch": branch, "status": status},
        "probe_source": "python_subprocess",
    }
    shell_git = (shell_probes or {}).get("git") or {}
    if shell_git.get("head_sha"):
        result.update({
            "head_sha": shell_git.get("head_sha"),
            "branch": shell_git.get("branch"),
            "dirty": bool(shell_git.get("status_lines")),
            "status_lines": shell_git.get("status_lines") or [],
            "status_error": None,
            "probe_source": "shell_probe",
        })
    return result


def discover_python() -> dict:
    return {
        "executable": sys.executable,
        "version": platform.python_version(),
        "version_full": sys.version,
        "prefix": sys.prefix,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "cwd": os.getcwd(),
        "flags": {"ignore_environment": bool(sys.flags.ignore_environment), "no_user_site": bool(sys.flags.no_user_site)},
    }


def discover_packages() -> dict:
    inventory = {}
    for name in KEY_PACKAGES:
        inventory[name] = _distribution_info(name)
    imports = {}
    for dist_name, module_name in IMPORT_MODULES.items():
        entry = {"module": module_name, "ok": False, "version_attr": None, "error": None}
        try:
            module = importlib.import_module(module_name)
            entry["ok"] = True
            entry["version_attr"] = getattr(module, "__version__", None)
            if module_name == "torch":
                entry["cuda_available"] = bool(module.cuda.is_available())
                entry["cuda_device_count"] = int(module.cuda.device_count()) if hasattr(module.cuda, "device_count") else 0
            if module_name == "RCAIDE":
                entry["file"] = getattr(module, "__file__", None)
        except Exception as exc:
            entry["error"] = type(exc).__name__ + ": " + str(exc)
        imports[dist_name] = entry
    return {"distributions": inventory, "imports": imports}


def _find_tools_local(repo_root: Path):
    found = []
    for name in TOOLS_LOCAL_NAMES:
        for candidate in [repo_root / name, repo_root / "installation" / name, repo_root / "outputs" / name]:
            if candidate.exists():
                found.append(candidate)
    return found


def discover_external_tools(repo_root: Path, shell_probes=None) -> dict:
    tools = {}
    for name in ("su2_cfd", "gmsh", "vspaero"):
        which = shutil.which(name)
        if which:
            EXTERNAL_TOOLS.setdefault(name, {"paths": [], "probe": None, "kind": "solver"})["paths"].append(which)
            break
    for name, spec in EXTERNAL_TOOLS.items():
        candidates = []
        for raw in spec["paths"]:
            path = Path(raw)
            entry = {"path": str(path), "exists": path.exists(), "bytes": path.stat().st_size if path.exists() else None}
            if path.exists() and spec.get("probe"):
                entry["probe"] = _run([path] + spec["probe"], timeout=60)
            candidates.append(entry)
        tools[name] = {"kind": spec["kind"], "candidates": candidates}
    vsp_dir = Path(EXTERNAL_TOOLS["openvsp_gui"]["paths"][0]).parent
    vspaero = sorted(vsp_dir.glob("vspaero*.exe")) if vsp_dir.exists() else []
    tools["vspaero"] = {"kind": "solver", "candidates": [{"path": str(p), "exists": p.exists(), "bytes": p.stat().st_size} for p in vspaero]}
    python_probe = []
    for py in OPENVSP_PYTHON_CANDIDATES:
        entry = {"python": py, "exists": Path(py).exists(), "probe": None}
        if Path(py).exists():
            script = (
                "import sys\n"
                "paths = " + json.dumps(OPENVSP_API_PARENT_CANDIDATES) + "\n"
                "for p in paths:\n"
                "    sys.path.insert(0, p)\n"
                "try:\n"
                "    import openvsp\n"
                "    print('OPENVSP_IMPORT_OK', openvsp.__file__)\n"
                "except Exception as exc:\n"
                "    print('OPENVSP_IMPORT_FAIL', type(exc).__name__, str(exc))\n"
            )
            entry["probe"] = _run([py, "-c", script], timeout=120)
        python_probe.append(entry)
    tools["openvsp_python_binding"] = {
        "kind": "python_binding",
        "project_interpreter_import": _import_probe("openvsp"),
        "external_interpreters": python_probe,
    }
    tools["gmsh_python_binding"] = {"kind": "python_binding", "project_interpreter_import": _import_probe("gmsh")}
    tools["tools_local_json"] = [
        {"path": str(p), "bytes": p.stat().st_size, "sha256": _sha256(p)} for p in _find_tools_local(repo_root)
    ]
    shell_tools = (shell_probes or {}).get("tools") or {}
    for name, probe in shell_tools.items():
        if name == "openvsp_python_binding" and isinstance(probe, dict):
            tools["openvsp_python_binding"]["external_interpreters"] = probe.get("external_interpreters") or []
            continue
        entry = tools.get(name)
        if not isinstance(entry, dict):
            entry = {"kind": "external", "candidates": []}
            tools[name] = entry
        entry["shell_probe"] = probe
    tools["probe_source"] = "shell_probe" if shell_tools else "python_subprocess"
    return tools


def _import_probe(module_name: str) -> dict:
    try:
        module = importlib.import_module(module_name)
        return {"ok": True, "file": getattr(module, "__file__", None)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__ + ": " + str(exc)}


def scan_concorde(repo_root: Path) -> dict:
    path = repo_root / CONCORDE_REL
    if not path.exists():
        return {"path": str(path), "exists": False, "error": "Concorde.py not found"}
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    terms = [
        "segment_6", "segment_5", "segment_4", "segment_3", "segment_2", "segment_1",
        "append_segment", "append_component", "append_airfoil", "append_control_surface",
        "vertical_stabilizer", "vertical_tail", "fuselages", "wings",
        "aspect_ratio", "sweep", "span", "chord", "mass_properties",
        "takeoff", "max_fuel", "design_mach", "design_altitude", "design_range",
    ]
    counts = {term: len(re.findall(re.escape(term), text)) for term in terms}
    functions, classes, call_names = [], [], Counter()
    parse_error = None
    try:
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions.append({"name": node.name, "line": node.lineno})
            elif isinstance(node, ast.ClassDef):
                classes.append({"name": node.name, "line": node.lineno})
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    call_names[node.func.id] += 1
                elif isinstance(node.func, ast.Attribute):
                    call_names[node.func.attr] += 1
    except SyntaxError as exc:
        parse_error = "SyntaxError: " + str(exc)
    segment_6_lines = [
        {"line": index, "text": line.strip()[:240]}
        for index, line in enumerate(lines, start=1)
        if "segment_6" in line
    ]
    return {
        "path": str(path),
        "relative_path": str(CONCORDE_REL).replace("\\", "/"),
        "exists": True,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "line_count": len(lines),
        "term_counts": counts,
        "top_level_functions": functions,
        "classes": classes,
        "top_call_names": call_names.most_common(25),
        "segment_6_lines": segment_6_lines[:40],
        "segment_6_line_count": len(segment_6_lines),
        "ast_parse_error": parse_error,
    }


def _iter_source_files(roots, max_files=1500, max_bytes=2_000_000, time_budget_s=25.0):
    extensions = {".py", ".yaml", ".yml", ".json", ".md", ".txt", ".jsonl"}
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "envs", "site-packages", "Lib", "include", "Scripts"}
    seen = 0
    started = time.time()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
            for filename in filenames:
                if time.time() - started > time_budget_s or seen >= max_files:
                    return
                path = Path(dirpath) / filename
                if path.suffix.lower() not in extensions:
                    continue
                try:
                    if path.stat().st_size > max_bytes:
                        continue
                except OSError:
                    continue
                seen += 1
                yield path


def _search_terms(roots, terms, max_hits=40) -> dict:
    lowered = [(t, t.lower()) for t in terms]
    hits = []
    scanned = 0
    for path in _iter_source_files(roots):
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            low = line.lower()
            for term, low_term in lowered:
                if low_term in low:
                    hits.append({"path": str(path), "line": line_no, "term": term, "text": line.strip()[:220]})
                    break
            if len(hits) >= max_hits:
                return {"terms": terms, "scanned_files": scanned, "hits": hits, "truncated": True}
    return {"terms": terms, "scanned_files": scanned, "hits": hits, "truncated": False}


def discover_maml_opt(repo_root: Path) -> dict:
    info = _distribution_info("maml-opt")
    entry = {"distribution": info, "import_ok": False, "modules": [], "api": {}, "legacy_13d_scan": None, "error": None}
    try:
        import maml_opt
        entry["import_ok"] = True
        entry["file"] = getattr(maml_opt, "__file__", None)
        entry["modules"] = sorted(name for _, name, _ in pkgutil.iter_modules(maml_opt.__path__))
        for module_name in ["contracts", "initialization", "evaluation", "bayesian", "campaign", "cli",
                            "learning.model", "learning.training", "adapters.rcaide", "data.dataset", "data.archive"]:
            full = "maml_opt." + module_name
            mod_entry = {"ok": False, "classes": [], "functions": [], "error": None}
            try:
                module = importlib.import_module(full)
                mod_entry["ok"] = True
                for name, obj in inspect.getmembers(module):
                    if name.startswith("_"):
                        continue
                    if inspect.isclass(obj) and getattr(obj, "__module__", "").startswith("maml_opt"):
                        try:
                            signature = str(inspect.signature(obj))
                        except Exception:
                            signature = None
                        mod_entry["classes"].append({"name": name, "signature": signature})
                    elif inspect.isfunction(obj) and getattr(obj, "__module__", "").startswith("maml_opt"):
                        try:
                            signature = str(inspect.signature(obj))
                        except Exception:
                            signature = None
                        mod_entry["functions"].append({"name": name, "signature": signature})
            except Exception as exc:
                mod_entry["error"] = type(exc).__name__ + ": " + str(exc)
            entry["api"][full] = mod_entry
    except Exception as exc:
        entry["error"] = type(exc).__name__ + ": " + str(exc)
    roots = [repo_root / "tutorials", repo_root / "research"]
    for extra in [Path(r"D:\CodexMemory\RCAIDE"), Path(r"D:\CodexMemory") / "MAML" + "\u5143\u5b66\u4e60"]:
        if extra.exists():
            roots.append(extra)
    entry["legacy_13d_scan"] = _search_terms(
        roots,
        ["single_cruise", "maml_a", "route_a", "design_space_15", "design_space_13", "concorde"],
    )
    return entry


def discover_rcaide_cfd(repo_root: Path) -> dict:
    entry = {"distribution": _distribution_info("rcaide-multifidelity"), "import_ok": False, "modules": [], "evidence": {}, "error": None}
    try:
        import rcaide_cfd
        entry["import_ok"] = True
        entry["file"] = getattr(rcaide_cfd, "__file__", None)
        entry["modules"] = sorted(name for _, name, _ in pkgutil.iter_modules(rcaide_cfd.__path__))
    except Exception as exc:
        entry["error"] = type(exc).__name__ + ": " + str(exc)
    source_root = r"D:\CodexMemory\RCAIDE\multifidelity"
    for rel in ["evidence/build-result.json", "evidence/review.md", "pyproject.toml", "README.md"]:
        path = Path(source_root) / rel
        if path.exists():
            item = {"path": str(path), "bytes": path.stat().st_size, "sha256": _sha256(path)}
            if path.suffix == ".json":
                try:
                    item["content"] = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    item["content"] = None
            entry["evidence"][rel] = item
    return entry


def discover_rcaide() -> dict:
    entry = {"ok": False, "version": None, "attributes": {}, "error": None}
    try:
        import RCAIDE
        entry["ok"] = True
        entry["version"] = getattr(RCAIDE, "__version__", None)
        for attr in ["Mission", "Vehicle", "Analyses", "Aerodynamics", "Components", "Library", "Methods"]:
            entry["attributes"][attr] = hasattr(RCAIDE, attr)
    except Exception as exc:
        entry["error"] = type(exc).__name__ + ": " + str(exc)
    return entry


def build_blockers(environment: dict) -> list:
    blockers = []
    imports = environment.get("packages", {}).get("imports", {})
    tools = environment.get("external_tools", {})
    cfd = environment.get("rcaide_cfd", {})
    maml = environment.get("maml_opt", {})
    concorde = environment.get("concorde", {})
    git = environment.get("git", {})
    py = environment.get("python", {})

    openvsp = tools.get("openvsp_python_binding", {})
    if not (openvsp.get("project_interpreter_import") or {}).get("ok"):
        blockers.append({
            "id": "B-P1-OPENVSP-BINDING",
            "severity": "major",
            "stage": "P1",
            "statement": ("OpenVSP 3.26.1 Python API is not importable in the available interpreters: the shipped _vsp.pyd "
                          "(x64) fails with ImportError 'DLL load failed while importing _vsp'. The pyd names libxml2.dll, "
                          "which the OpenVSP install does not contain; a PATH-supplemented retry with D:/Anaconda/Library/bin "
                          "also failed. P1 must drive vsp.exe/.vsp3 in a separate process or repair the binding; no in-process "
                          "OpenVSP geometry call may be assumed available, and no OpenVSP version is claimed in solver_versions."),
            "evidence": {
                "project_import": openvsp.get("project_interpreter_import"),
                "external_interpreters": openvsp.get("external_interpreters"),
                "install_probe": "OpenVSP install root 3.26.1-win64 contains vsp.exe/vspaero.exe but no libxml2.dll; _vsp.pyd is PE x64 and dates 2022-01-06.",
            },
        })
    gmsh = tools.get("gmsh_python_binding", {})
    if not (gmsh.get("project_interpreter_import") or {}).get("ok"):
        blockers.append({
            "id": "B-P3-GMSH-BINDING",
            "severity": "minor",
            "stage": "P3",
            "statement": "gmsh Python module is absent from the project interpreter; the Gmsh CLI is present but any in-process meshing needs an external worker or wrapper.",
            "evidence": {"project_import": gmsh.get("project_interpreter_import"), "cli": tools.get("gmsh")},
        })
    if not concorde.get("exists"):
        blockers.append({"id": "B-P1-CONCORDE-SOURCE", "severity": "blocking", "stage": "P1",
                         "statement": "Concorde.py tutorial source was not found.", "evidence": concorde})
    else:
        blockers.append({"id": "B-P1-CONCORDE-ADAPTER", "severity": "major", "stage": "P1",
                         "statement": "Concorde.py is a tutorial script; no parameterized adapter or geometry checks exist yet, so the 15 design variables are not connected to a model in P0.",
                         "evidence": {"relative_path": concorde.get("relative_path"), "line_count": concorde.get("line_count")}})
    evidence = cfd.get("evidence", {}) if isinstance(cfd, dict) else {}
    build_result = (evidence.get("evidence/build-result.json") or {}).get("content") or {}
    blockers.append({
        "id": "B-P3-HF-SCOPE",
        "severity": "major",
        "stage": "P3",
        "statement": "Installed rcaide-multifidelity 0.1.0 evidence declares only a limited native RCAIDE input scope and Euler-only high fidelity; full Concorde high-fidelity fuel burn is not supported without a VSP3 or externally supplied SU2 mesh, and the claim must not be made before a paired test.",
        "evidence": {"build_status": build_result.get("status"), "evidence_files": sorted(evidence.keys())},
    })
    maml_dist = maml.get("distribution", {}) if isinstance(maml, dict) else {}
    legacy = maml.get("legacy_13d_scan") or {}
    if not legacy.get("hits"):
        blockers.append({
            "id": "B-P5-LEGACY-13D-APP",
            "severity": "major",
            "stage": "P5",
            "statement": "The historical 13-variable single_cruise application was not located in bounded scans; P5 must either locate it with user help or build the response-model path from the installed maml-opt 0.1.0 API only.",
            "evidence": {"scanned_files": legacy.get("scanned_files"), "roots": ["tutorials", "research", "D:/CodexMemory/RCAIDE", "D:/CodexMemory/..."]},
        })
    if not maml_dist.get("direct_url") and maml_dist.get("location"):
        blockers.append({
            "id": "B-P5-MAML-SOURCE",
            "severity": "major",
            "stage": "P5",
            "statement": "maml-opt has no recorded direct_url; its source project is only an installed distribution, so reuse must be audited against site-packages source and no unverified upstream API may be assumed.",
            "evidence": {"location": maml_dist.get("location"), "version": maml_dist.get("version")},
        })
    torch_info = imports.get("torch", {})
    if torch_info.get("ok") and not torch_info.get("cuda_available"):
        blockers.append({"id": "B-P5-TORCH-CPU", "severity": "minor", "stage": "P5",
                         "statement": "The installed torch build reports no CUDA device; MAML-A training must fit a small network on CPU, or a GPU-enabled build must be approved separately.",
                         "evidence": {"torch": torch_info}})
    if git.get("dirty"):
        blockers.append({"id": "B-P0-DIRTY-WORKTREE", "severity": "minor", "stage": "P0",
                         "statement": "The worktree is dirty at audit time; a clean commit baseline is required before any run can be attributed to a commit.",
                         "evidence": {"status_lines": git.get("status_lines")}})
    blockers.append({
        "id": "B-GOV-BUDGET",
        "severity": "blocking",
        "stage": "P2-P6",
        "statement": "Formal true-evaluation budgets (P2 smoke, P4 BO, P6 comparison) are not frozen; no Mission or CFD budget may be spent before explicit user approval.",
        "evidence": {"budget_approval": None},
    })
    blockers.append({
        "id": "B-P3-VLM-MACH2",
        "severity": "major",
        "stage": "P3",
        "statement": "VLM/VSPAERO applicability near Mach 2 is unverified for this configuration; any low-fidelity aerodynamic use must be tested and reported before it feeds a Mission.",
        "evidence": {"tested": False},
    })
    return blockers


def _md_table(headers, rows) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("|", "/") for cell in row) + " |")
    return "\n".join(out) + "\n"


def _write_evidence(output_dir: Path, environment: dict) -> dict:
    evidence = output_dir / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    written = {}

    def dump(name, payload):
        path = evidence / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        written[name] = str(path.relative_to(output_dir)).replace("\\", "/")

    dump("git.json", environment["git"])
    dump("python.json", environment["python"])
    dump("packages.json", environment["packages"])
    dump("external_tools.json", environment["external_tools"])
    dump("concorde_scan.json", environment["concorde"])
    dump("maml_opt_scan.json", environment["maml_opt"])
    dump("rcaide_cfd_scan.json", environment["rcaide_cfd"])
    dump("rcaide.json", environment["rcaide"])

    git = environment["git"]
    (evidence / "git_status.txt").write_text(
        "branch: " + str(git.get("branch")) + "\n"
        "head_sha: " + str(git.get("head_sha")) + "\n"
        "dirty: " + str(git.get("dirty")) + "\n\n"
        + "\n".join(git.get("status_lines", [])) + "\n",
        encoding="utf-8",
    )
    written["git_status.txt"] = "evidence/git_status.txt"

    packages = environment["packages"]["distributions"]
    imports = environment["packages"]["imports"]
    rows = []
    for name, info in packages.items():
        import_info = imports.get(name, {})
        rows.append([name, info.get("version"), "ok" if import_info.get("ok") else "failed", info.get("location"), import_info.get("error")])
    (evidence / "toolchain_table.md").write_text(
        "# Toolchain inventory (P0 audit)\n\n" + _md_table(
            ["distribution", "version", "import", "location", "error"], rows), encoding="utf-8")
    written["toolchain_table.md"] = "evidence/toolchain_table.md"

    api_rows = []
    for module_name, mod in environment["maml_opt"].get("api", {}).items():
        for cls in mod.get("classes", []):
            api_rows.append([module_name, "class", cls.get("name"), cls.get("signature")])
        for fn in mod.get("functions", []):
            api_rows.append([module_name, "function", fn.get("name"), fn.get("signature")])
    (evidence / "api_table.md").write_text(
        "# Observed installed-package API (P0 audit)\n\n"
        "Only members whose __module__ starts with maml_opt are listed. No API is assumed beyond this table.\n\n"
        + _md_table(["module", "kind", "name", "signature"], api_rows), encoding="utf-8")
    written["api_table.md"] = "evidence/api_table.md"

    concorde = environment["concorde"]
    term_rows = [[term, count] for term, count in sorted(concorde.get("term_counts", {}).items())]
    (evidence / "concorde_structure.md").write_text(
        "# Concorde.py static structure (P0 audit)\n\n"
        "relative_path: " + str(concorde.get("relative_path")) + "\n"
        "sha256: " + str(concorde.get("sha256")) + "\n"
        "lines: " + str(concorde.get("line_count")) + "\n"
        "segment_6 references: " + str(concorde.get("segment_6_line_count")) + "\n\n"
        "## Term counts\n\n" + _md_table(["term", "count"], term_rows)
        + "\n## Top-level functions\n\n" + "\n".join(
            "- " + fn["name"] + " (line " + str(fn["line"]) + ")" for fn in concorde.get("top_level_functions", []))
        + "\n",
        encoding="utf-8")
    written["concorde_structure.md"] = "evidence/concorde_structure.md"

    blocker_lines = ["# P0 blocker list\n"]
    for item in environment["blockers"]:
        blocker_lines.append("## " + item["id"] + " [" + item["severity"] + ", " + item["stage"] + "]")
        blocker_lines.append(item["statement"])
        blocker_lines.append("")
    (evidence / "blocker_list.md").write_text("\n".join(blocker_lines), encoding="utf-8")
    written["blocker_list.md"] = "evidence/blocker_list.md"

    return written


def run_audit(repo_root=None, output_root=None, run_id=None, shell_probes=None, allow_existing=False) -> dict:
    repo_root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[2]
    output_root = Path(output_root) if output_root else repo_root / "research" / "concorde_metaopt" / "optimization_runs"
    started = time.time()
    if run_id is None:
        run_id = "audit-p0-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = output_root / run_id
    if shell_probes is not None and not isinstance(shell_probes, dict):
        shell_probes = json.loads(Path(shell_probes).read_text(encoding="utf-8"))
    if output_dir.exists() and any(output_dir.iterdir()) and not allow_existing:
        raise FileExistsError("audit output directory already exists and is not empty: " + str(output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    environment = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "repo_root": str(repo_root),
        "notes": [
            "Read-only audit: no Mission, CFD case or optimization was executed.",
            "Missing or unobservable values are null; failed probes are recorded with their error text.",
            "Absolute local paths are recorded for traceability; no token or secret value is read.",
        ],
        "git": _safe("git", lambda: discover_git(repo_root, shell_probes)),
        "python": _safe("python", discover_python),
        "packages": _safe("packages", discover_packages),
        "external_tools": _safe("external_tools", lambda: discover_external_tools(repo_root, shell_probes)),
        "concorde": _safe("concorde", lambda: scan_concorde(repo_root)),
        "maml_opt": _safe("maml_opt", lambda: discover_maml_opt(repo_root)),
        "rcaide_cfd": _safe("rcaide_cfd", lambda: discover_rcaide_cfd(repo_root)),
        "rcaide": _safe("rcaide", discover_rcaide),
    }
    environment["blockers"] = build_blockers(environment)

    summary = {
        "run_id": run_id,
        "stage": STAGE,
        "task_id": "issue-1-p0-audit",
        "method": "read_only_environment_audit",
        "seed": None,
        "git_sha": (environment["git"] or {}).get("head_sha"),
        "solver_versions": {
            "python": environment["python"].get("version"),
            "rcaide": environment["rcaide"].get("version") or (environment["packages"]["imports"].get("RCAIDE-LEADS") or {}).get("version_attr"),
            "maml_opt": (environment["packages"]["imports"].get("maml-opt") or {}).get("version_attr"),
            "rcaide_cfd": (environment["packages"]["imports"].get("rcaide-multifidelity") or {}).get("version_attr"),
            "numpy": environment["packages"]["imports"].get("numpy", {}).get("version_attr"),
            "scipy": environment["packages"]["imports"].get("scipy", {}).get("version_attr"),
            "torch": environment["packages"]["imports"].get("torch", {}).get("version_attr"),
            "su2": None,
            "gmsh": None,
            "openvsp": None,
        },
        "design_dim": None,
        "status": "audit_completed",
        "total_true_evaluations": 0,
        "low_fidelity_calls": 0,
        "su2_calls": 0,
        "invalid_count": None,
        "failed_count": None,
        "first_feasible_evaluation": None,
        "best_feasible_fuel_kg": None,
        "best_design_id": None,
        "wall_seconds": None,
        "cpu_seconds_if_available": None,
        "artifacts": {},
        "design_dim_note": "The 15-variable space is specified by Issue #1 but is not frozen until P1; design_dim is therefore null in P0.",
    }
    external = environment.get("external_tools", {})
    for key, tool_key, probe_index in [("su2", "su2_cfd", 0), ("gmsh", "gmsh", 0), ("openvsp", "openvsp_gui", 0)]:
        entry = external.get(tool_key) or {}
        shell_probe = entry.get("shell_probe") or {}
        candidates = entry.get("candidates") or []
        if shell_probe.get("version_text"):
            summary["solver_versions"][key] = str(shell_probe["version_text"]).strip()[:200] or None
        elif candidates:
            summary["solver_versions"][key] = (candidates[0].get("probe") or {}).get("stdout", "").strip()[:200] or None

    if shell_probes:
        environment["notes"].append("Git and external tool facts include a shell probe conducted by research/concorde_metaopt/scripts/probe_external_tools.sh; probe_source records which path supplied them.")
    evidence = _write_evidence(output_dir, environment)
    summary["artifacts"] = {
        "environment": "environment.json",
        "summary": "summary.json",
        "evidence_dir": "evidence/",
        "evidence": evidence,
    }
    summary["wall_seconds"] = round(time.time() - started, 3)
    probes_dir = output_dir / "probes"
    if probes_dir.exists():
        summary["artifacts"]["probes_dir"] = "probes/"
    environment["summary_ref"] = "summary.json"
    (output_dir / "environment.json").write_text(json.dumps(environment, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"summary": summary, "environment": environment, "output_dir": str(output_dir)}
