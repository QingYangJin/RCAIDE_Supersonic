"""Canonical records / hashing for D-REAL-001 (governance v2 sec 3/5/6)."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .constants import SCHEMA_VERSION


def fmt_float(value: Any) -> str:
    """Canonical float formatting: '%.12g' (governance sec 3)."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("canonical float must be finite, got %r" % (value,))
    text = "%.12g" % number
    if text == "-0":
        text = "0"
    return text


def canonical_json(payload: Any) -> str:
    """Sorted, whitespace-free JSON with canonical float formatting."""
    if payload is None:
        return "null"
    if isinstance(payload, bool):
        return "true" if payload else "false"
    if isinstance(payload, (int, np.integer)):
        return str(int(payload))
    if isinstance(payload, (float, np.floating)):
        return fmt_float(payload)
    if isinstance(payload, str):
        return json.dumps(payload, ensure_ascii=False)
    if isinstance(payload, Mapping):
        items = sorted(payload.items(), key=lambda item: str(item[0]))
        return "{" + ",".join(
            json.dumps(str(key), ensure_ascii=False) + ":" + canonical_json(value)
            for key, value in items
        ) + "}"
    if isinstance(payload, np.ndarray):
        return "[" + ",".join(canonical_json(item) for item in payload.ravel().tolist()) + "]"
    if isinstance(payload, (list, tuple)):
        return "[" + ",".join(canonical_json(item) for item in payload) + "]"
    raise TypeError("unsupported canonical_json type: %r" % (type(payload),))


def canonical_x12(x12: Sequence[float]) -> str:
    """Canonical 12-D design vector JSON: frozen order, '%.12g', no whitespace."""
    vector = np.asarray(x12, dtype=float).reshape(-1)
    return "[" + ",".join(fmt_float(value) for value in vector) + "]"


def design_hash(x12: Sequence[float]) -> str:
    """Governance design_hash = sha256(canonical x12 JSON)[:16]."""
    return sha256_bytes(canonical_x12(x12).encode("utf-8"))[:16]


def solver_config_hash(config: Mapping[str, Any]) -> str:
    """sha256 of the canonical solver configuration JSON (governance sec 3)."""
    return sha256_bytes(canonical_json(dict(config)).encode("utf-8"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json_atomic(path: Any, payload: Any) -> Path:
    """Write JSON via a temporary file + os.replace (append-only evidence friendly)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return target


def append_jsonl(path: Any, payload: Mapping[str, Any], *, fsync: bool = True) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line + "\n")
        stream.flush()
        if fsync:
            os.fsync(stream.fileno())


def read_jsonl(path: Any) -> List[Dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with target.open("r", encoding="utf-8") as stream:
        for line in stream:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


@dataclass(frozen=True)
class SolverAttempt:
    """One solver attempt ledger row (governance v2 sec 5).

    MOCK rows carry backend=MOCK, physical_solver_starts=0 and
    simulated_solver_starts=1; they must never enter a real evidence table.
    """

    attempt_id: str
    batch_id: str
    run_id: str
    case_id: str
    sequence: int
    task_id: str
    design_hash: str
    x12_canonical: str
    geometry_source: str
    geometry_sha256: str
    solver_version: str
    solver_config_hash: str
    argv: Tuple[str, ...]
    start_ts_utc: str
    end_ts_utc: str
    wall_s: float
    exit_code: Optional[int]
    status: str
    physical_solver_starts: int
    simulated_solver_starts: int
    backend: str
    stdout_path: str = ""
    stderr_path: str = ""
    raw_artifacts: Tuple[Mapping[str, Any], ...] = ()
    notes: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "sequence": int(self.sequence),
            "task_id": self.task_id,
            "design_hash": self.design_hash,
            "x12": self.x12_canonical,
            "x12_canonical": self.x12_canonical,
            "geometry_source": self.geometry_source,
            "geometry_sha256": self.geometry_sha256,
            "solver_version": self.solver_version,
            "solver_config_hash": self.solver_config_hash,
            "argv": list(self.argv),
            "start_ts_utc": self.start_ts_utc,
            "end_ts_utc": self.end_ts_utc,
            "wall_s": float(self.wall_s),
            "exit_code": self.exit_code,
            "status": self.status,
            "physical_solver_starts": int(self.physical_solver_starts),
            "simulated_solver_starts": int(self.simulated_solver_starts),
            "backend": self.backend,
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
            "raw_artifacts": [dict(item) for item in self.raw_artifacts],
            "notes": self.notes,
        }


@dataclass(frozen=True)
class AlphaSample:
    alpha_deg: float
    cltot: float
    cdi: float
    cdo: float = 0.0
    cdtot: float = 0.0
    cm: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    converged: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "alpha_deg": float(self.alpha_deg),
            "CLtot": float(self.cltot),
            "CDi": float(self.cdi),
            "CDo": float(self.cdo),
            "CDtot": float(self.cdtot),
            "CM": [float(item) for item in self.cm],
            "converged": bool(self.converged),
        }


@dataclass(frozen=True)
class LiftMatchResult:
    alpha_deg: Optional[float]
    cltot: Optional[float]
    cdi: Optional[float]
    cdtot: Optional[float]
    cdo: Optional[float]
    cm: Optional[Tuple[float, float, float]]
    lift_rel_error: Optional[float]
    converged: bool
    method: str
    n_samples: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "alpha_deg": None if self.alpha_deg is None else float(self.alpha_deg),
            "CLtot": None if self.cltot is None else float(self.cltot),
            "CDi": None if self.cdi is None else float(self.cdi),
            "CDtot": None if self.cdtot is None else float(self.cdtot),
            "CDo": None if self.cdo is None else float(self.cdo),
            "CM": None if self.cm is None else [float(item) for item in self.cm],
            "lift_rel_error": None if self.lift_rel_error is None else float(self.lift_rel_error),
            "converged": bool(self.converged),
            "method": self.method,
            "n_samples": int(self.n_samples),
        }


@dataclass(frozen=True)
class AeroEvaluation:
    """One design evaluation. objective D_i_N only; fuel_burn_kg is always None."""

    schema_version: str
    record_id: str
    batch_id: str
    run_id: str
    task_id: str
    arm_id: str
    design_hash: str
    x12_canonical: str
    x12_unit: Tuple[float, ...]
    backend: str
    source_kind: str
    status: str
    record_status: str
    attempt_refs: Tuple[str, ...]
    physical_solver_starts: int
    simulated_solver_starts: int
    cache_hit: bool
    cache_key: str
    labels_visible_to_arm: bool
    alpha_deg: Optional[float]
    CLtot: Optional[float]
    CDi: Optional[float]
    CDtot: Optional[float]
    CDo: Optional[float]
    CM: Optional[Tuple[float, float, float]]
    L_N: Optional[float]
    D_i_N: Optional[float]
    q_Pa: float
    Sref_m2: Optional[float]
    L_ref_N: float
    lift_rel_error: Optional[float]
    solver_config_hash: str
    reference_frame: str
    geometry_sha256: str
    created_ts_utc: str
    wall_s: float
    refines_used: int = 0
    error_code: str = ""
    error_message: str = ""
    alpha_samples: Tuple[Mapping[str, Any], ...] = ()
    geometry_source: str = ""
    notes: str = ""
    # A1 E6-GAP-01: OpenVSP thin mesher can emit different topology families for
    # the same x12; family is recorded as a covariate and must never be compared
    # across families without stratification.
    mesh_family: str = ""
    mesh_nodes: int = 0
    mesh_elements: int = 0
    # Cache isolation (Lead m00426): REAL cache entries are keyed by mesh family
    # and the normalised geometry hash; the raw .vspgeom bytes sha is provenance.
    normalized_geometry_hash: str = ""
    vspgeom_sha256: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "arm_id": self.arm_id,
            "design_hash": self.design_hash,
            "x12_canonical": self.x12_canonical,
            "x12_unit": [float(value) for value in self.x12_unit],
            "backend": self.backend,
            "source_kind": self.source_kind,
            "status": self.status,
            "record_status": self.record_status,
            "attempt_ids": list(self.attempt_refs),
            "physical_solver_starts": int(self.physical_solver_starts),
            "simulated_solver_starts": int(self.simulated_solver_starts),
            "cache_hit": bool(self.cache_hit),
            "cache_key": self.cache_key,
            "labels_visible_to_arm": bool(self.labels_visible_to_arm),
            "alpha_deg": None if self.alpha_deg is None else float(self.alpha_deg),
            "CLtot": None if self.CLtot is None else float(self.CLtot),
            "CDi": None if self.CDi is None else float(self.CDi),
            "CDtot": None if self.CDtot is None else float(self.CDtot),
            "CDo": None if self.CDo is None else float(self.CDo),
            "CM": None if self.CM is None else [float(item) for item in self.CM],
            "L_N": None if self.L_N is None else float(self.L_N),
            "D_i_N": None if self.D_i_N is None else float(self.D_i_N),
            "q_Pa": float(self.q_Pa),
            "Sref_m2": None if self.Sref_m2 is None else float(self.Sref_m2),
            "L_ref_N": float(self.L_ref_N),
            "lift_rel_error": None if self.lift_rel_error is None else float(self.lift_rel_error),
            "solver_config_hash": self.solver_config_hash,
            "reference_frame": self.reference_frame,
            "geometry_sha256": self.geometry_sha256,
            "created_ts_utc": self.created_ts_utc,
            "wall_s": float(self.wall_s),
            "refines_used": int(self.refines_used),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "alpha_samples": [dict(item) for item in self.alpha_samples],
            "geometry_source": self.geometry_source,
            "notes": self.notes,
            "mesh_family": self.mesh_family,
            "mesh_nodes": int(self.mesh_nodes),
            "mesh_elements": int(self.mesh_elements),
            "normalized_geometry_hash": self.normalized_geometry_hash,
            "vspgeom_sha256": self.vspgeom_sha256,
            "objective": {
                "name": "D_i_N",
                "value": None if self.D_i_N is None else float(self.D_i_N),
                "status": self.status,
            },
            "fuel_burn_kg": None,
        }


def evaluation_from_dict(row: Mapping[str, Any]) -> AeroEvaluation:
    """Reconstruct an AeroEvaluation from a persisted evaluations.jsonl row."""
    samples = tuple(dict(item) for item in row.get("alpha_samples") or ())
    cm = row.get("CM")
    return AeroEvaluation(
        schema_version=str(row.get("schema_version", SCHEMA_VERSION)),
        record_id=str(row.get("record_id", "")),
        batch_id=str(row.get("batch_id", "")),
        run_id=str(row.get("run_id", "")),
        task_id=str(row.get("task_id", "")),
        arm_id=str(row.get("arm_id", "")),
        design_hash=str(row.get("design_hash", "")),
        x12_canonical=str(row.get("x12_canonical", "")),
        x12_unit=tuple(float(value) for value in row.get("x12_unit") or ()),
        backend=str(row.get("backend", "")),
        source_kind=str(row.get("source_kind", "")),
        status=str(row.get("status", "")),
        record_status=str(row.get("record_status", "")),
        attempt_refs=tuple(str(item) for item in row.get("attempt_ids") or ()),
        physical_solver_starts=int(row.get("physical_solver_starts", 0)),
        simulated_solver_starts=int(row.get("simulated_solver_starts", 0)),
        cache_hit=bool(row.get("cache_hit", False)),
        cache_key=str(row.get("cache_key", "")),
        labels_visible_to_arm=bool(row.get("labels_visible_to_arm", False)),
        alpha_deg=row.get("alpha_deg"),
        CLtot=row.get("CLtot"),
        CDi=row.get("CDi"),
        CDtot=row.get("CDtot"),
        CDo=row.get("CDo"),
        CM=None if cm is None else tuple(float(item) for item in cm),
        L_N=row.get("L_N"),
        D_i_N=row.get("D_i_N"),
        q_Pa=float(row.get("q_Pa", 0.0)),
        Sref_m2=row.get("Sref_m2"),
        L_ref_N=float(row.get("L_ref_N", 0.0)),
        lift_rel_error=row.get("lift_rel_error"),
        solver_config_hash=str(row.get("solver_config_hash", "")),
        reference_frame=str(row.get("reference_frame", "")),
        geometry_sha256=str(row.get("geometry_sha256", "")),
        created_ts_utc=str(row.get("created_ts_utc", "")),
        wall_s=float(row.get("wall_s", 0.0)),
        refines_used=int(row.get("refines_used", 0)),
        error_code=str(row.get("error_code", "")),
        error_message=str(row.get("error_message", "")),
        alpha_samples=samples,
        geometry_source=str(row.get("geometry_source", "")),
        notes=str(row.get("notes", "")),
        mesh_family=str(row.get("mesh_family", "")),
        mesh_nodes=int(row.get("mesh_nodes", 0) or 0),
        mesh_elements=int(row.get("mesh_elements", 0) or 0),
        normalized_geometry_hash=str(row.get("normalized_geometry_hash", "")),
        vspgeom_sha256=str(row.get("vspgeom_sha256", "")),
    )
