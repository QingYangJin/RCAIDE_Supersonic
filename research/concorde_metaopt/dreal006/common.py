"""Shared paths and IO helpers for the D-MAML-100K campaign.

Everything the campaign writes stays under one run directory so the receipt can
name a single tree.  The module deliberately imports no numpy/torch: the
evaluation driver imports it in the parent process, and the heavy scientific
stack is imported only inside the worker after its BLAS/temp environment has
been pinned.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time
from typing import Any, Mapping

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUN_ID = "DRECOVER001-MAML100K-20261125"
RUN_DIR = REPO_ROOT / "research" / "concorde_metaopt" / "optimization_runs" / RUN_ID
META_DIR = RUN_DIR / "metadata"
DATA_DIR = RUN_DIR / "data" / "s1"
RAW_DIR = DATA_DIR / "raw"
SHARD_DIR = DATA_DIR / "shards"
MODEL_DIR = RUN_DIR / "models"
STATUS_PATH = META_DIR / "s1_run_status.json"
LEDGER_PATH = META_DIR / "s1_ledger.json"
LOCK_PATH = RUN_DIR / "s1_run.lock"

TASK_FAMILY_PATH = META_DIR / "task_family.json"
ACTIVE_SUBSPACE_PATH = META_DIR / "active_subspace.json"
MANIFEST_PATH = META_DIR / "s1_design_manifest.json"
DESIGN_SPACE_PATH = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"

LATTICE = (20, 10)
DESIGNS_PER_TASK = 256
FIT_DESIGNS = 128
SHARD_SIZE = 512
S1_BUDGET = 8192  # 24 train x 256 + 8 val x 256
MAX_INNER_SOLVES_PER_EVAL = 16
SCHEMA_PREFIX = "dreal006"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: pathlib.Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: pathlib.Path | str, payload: Mapping[str, Any]) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: pathlib.Path | str) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def load_task_family() -> dict:
    return read_json(TASK_FAMILY_PATH)


def load_active_subspace() -> dict:
    return read_json(ACTIVE_SUBSPACE_PATH)


def load_design_bounds() -> dict[str, dict[str, float]]:
    """Bounds/baseline for the 12 declared variables, read without importing RCAIDE."""
    import yaml  # PyYAML is a hard RCAIDE dependency

    data = yaml.safe_load(DESIGN_SPACE_PATH.read_text(encoding="utf-8"))
    out = {}
    for variable in data["variables"]:
        out[variable["name"]] = {
            "baseline": float(variable["baseline"]),
            "lower": float(variable["lower"]),
            "upper": float(variable["upper"]),
        }
    return out


def task_seed(task_id: str, purpose: str = "s1-designs-v1") -> int:
    digest = hashlib.sha256(("%s|%s" % (task_id, purpose)).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def repair_jsonl(path: pathlib.Path | str) -> int:
    """Drop a torn final line left by a hard kill; return the kept line count."""
    path = pathlib.Path(path)
    if not path.exists():
        return 0
    data = path.read_bytes()
    if not data:
        return 0
    if not data.endswith(b"\n"):
        cut = data.rfind(b"\n")
        data = data[: cut + 1] if cut >= 0 else b""
        path.write_bytes(data)
    return data.count(b"\n")


def read_jsonl(path: pathlib.Path | str) -> list[dict]:
    path = pathlib.Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows
