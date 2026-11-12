"""P2A-R1 frozen historical warm-start support loader (read-only, fail-closed).

Reads A1's committed `p2a_warmstart_support.json`: the ONLY external labels an
A-arm may see in P2a (the 15 P1C/P1R SOLVED_VALID designs).  The loader is
strict:

* exactly one file is read; nothing else is discovered or globbed at runtime;
* the raw byte SHA256 must match the SHA bound in plan/approval;
* every record must carry only the pre-registered keys, so a test/target/future
  label file cannot be mistaken for support;
* design_hash is re-derived from x12 (governance v3: sha256(canonical x12)[:16]);
* the object is frozen — no append/backfill during the P2a run;
* no cache, no cross-run reuse, physical_call_count=0.

The loader never writes and never imports the solver.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

SUPPORT_SCHEMA = "dreal001.p2a_warmstart_support.v1"
EXPECTED_DESIGNS = 15
CANONICAL_FLOAT_FORMAT = "%.12g"
DESIGN_HASH_HEX_LENGTH = 16
PHYSICAL_CALL_COUNT = 0

_TOP_LEVEL_ALLOWED = {
    "schema", "schema_version", "batch_id", "generated_utc", "n_designs",
    "task_spec_sha256", "solver_config_sha256", "target_mesh_family",
    "source_batch_ids", "source_run_ids", "records", "notes", "provenance",
}
_RECORD_REQUIRED = {"design", "design_hash", "native_family", "D_i_N", "source_record_sha"}
#: Only these keys may appear in a support record.  Anything else (a test label,
#: a future evaluation, a target objective, a prediction column) is refused.
_RECORD_ALLOWED = _RECORD_REQUIRED | {
    "x12", "source_run_id", "source_batch_id", "solver_status", "mesh_family",
    "solver_config_sha256", "same_family", "sref_m2", "cltot", "cdi",
    "alpha_deg", "mach", "notes",
}
_FORBIDDEN_KEY_TOKENS = ("label", "target", "test", "query", "future", "holdout", "prediction")


class WarmStartSupportError(ValueError):
    """A1 support artifact is missing, malformed, or not the bound bytes."""


def _canonical_x12_payload(x12: Sequence[float]) -> str:
    values = [float(value) for value in x12]
    return "[" + ",".join(CANONICAL_FLOAT_FORMAT % value for value in values) + "]"


def design_hash(x12: Sequence[float]) -> str:
    return hashlib.sha256(_canonical_x12_payload(x12).encode("utf-8")).hexdigest()[:DESIGN_HASH_HEX_LENGTH]


def _is_hex(value: Any, length: int) -> bool:
    text = str(value or "")
    return len(text) == length and all(ch in "0123456789abcdefABCDEF" for ch in text)


@dataclass(frozen=True)
class SupportRecord:
    design: Tuple[float, ...]
    design_hash: str
    native_family: Tuple[int, ...]
    D_i_N: float
    source_record_sha: str
    source_run_id: str = ""
    source_batch_id: str = ""
    solver_status: str = "SOLVED_VALID"
    mesh_family: Tuple[int, ...] = ()
    solver_config_sha256: str = ""
    same_family: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "design": [float(value) for value in self.design],
            "design_hash": self.design_hash,
            "native_family": list(self.native_family),
            "D_i_N": float(self.D_i_N),
            "source_record_sha": self.source_record_sha,
            "source_run_id": self.source_run_id,
            "source_batch_id": self.source_batch_id,
            "solver_status": self.solver_status,
            "mesh_family": list(self.mesh_family),
            "solver_config_sha256": self.solver_config_sha256,
            "same_family": self.same_family,
        }


@dataclass(frozen=True)
class WarmStartSupport:
    path: str
    sha256: str
    bytes: int
    schema: str
    records: Tuple[SupportRecord, ...]
    task_spec_sha256: str
    solver_config_sha256: str
    target_mesh_family: Tuple[int, ...]
    source_batch_ids: Tuple[str, ...]
    physical_call_count: int = PHYSICAL_CALL_COUNT

    @property
    def n_designs(self) -> int:
        return len(self.records)

    @property
    def design_hashes(self) -> Tuple[str, ...]:
        return tuple(record.design_hash for record in self.records)

    def designs(self) -> List[List[float]]:
        return [[float(value) for value in record.design] for record in self.records]

    def to_observed_support(self) -> Dict[str, Any]:
        """Payload consumed by `warm_start.sampler.WarmStartSampler.propose`."""
        return {"designs": self.designs(), "records": [record.to_dict() for record in self.records]}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "path": self.path,
            "sha256": self.sha256,
            "bytes": int(self.bytes),
            "n_designs": int(self.n_designs),
            "task_spec_sha256": self.task_spec_sha256,
            "solver_config_sha256": self.solver_config_sha256,
            "target_mesh_family": list(self.target_mesh_family),
            "source_batch_ids": list(self.source_batch_ids),
            "design_hashes": list(self.design_hashes),
            "records": [record.to_dict() for record in self.records],
            "physical_call_count": int(self.physical_call_count),
            "zero_new_labels": True,
            "read_only": True,
            "append_during_run": False,
            "cache_used": False,
        }


def _allowed_record_keys(record: Mapping[str, Any]) -> None:
    unknown = sorted(set(record) - _RECORD_ALLOWED)
    if unknown:
        raise WarmStartSupportError(
            "support record has keys outside the P2A-R1 schema: %r; refusing (no test/target/future labels allowed)" % (unknown,)
        )
    for key in record:
        lowered = str(key).lower()
        if any(token in lowered for token in _FORBIDDEN_KEY_TOKENS) and key not in _RECORD_ALLOWED:
            raise WarmStartSupportError("forbidden support key %r" % (key,))


def _parse_family(value: Any, field: str) -> Tuple[int, ...]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return tuple(int(item) for item in value)
    text = str(value or "")
    parts = [part for part in text.replace("x", "/").replace(" ", "/").split("/") if part]
    if len(parts) != 2:
        raise WarmStartSupportError("%s must be a mesh family like [543, 472] or '543/472', got %r" % (field, value))
    try:
        return (int(parts[0]), int(parts[1]))
    except ValueError as exc:
        raise WarmStartSupportError("%s must be integers, got %r" % (field, value)) from exc


def _parse_record(raw: Mapping[str, Any], index: int) -> SupportRecord:
    if not isinstance(raw, Mapping):
        raise WarmStartSupportError("support record %d is not an object" % index)
    _allowed_record_keys(raw)
    missing = sorted(_RECORD_REQUIRED - set(raw))
    if missing:
        raise WarmStartSupportError("support record %d missing required keys %r" % (index, missing))
    design_raw = raw.get("x12", raw.get("design"))
    try:
        design = tuple(float(value) for value in design_raw)
    except Exception as exc:  # noqa: BLE001
        raise WarmStartSupportError("support record %d design is not 12 numeric values" % index) from exc
    if len(design) != 12:
        raise WarmStartSupportError("support record %d design has %d values, expected 12" % (index, len(design)))
    if not all(math.isfinite(value) for value in design):
        raise WarmStartSupportError("support record %d design has a non-finite value" % index)
    declared_hash = str(raw.get("design_hash", ""))
    if not _is_hex(declared_hash, DESIGN_HASH_HEX_LENGTH):
        raise WarmStartSupportError("support record %d design_hash is not 16 hex chars: %r" % (index, declared_hash))
    recomputed = design_hash(design)
    if recomputed.lower() != declared_hash.lower():
        raise WarmStartSupportError(
            "support record %d design_hash mismatch: declared %r recomputed %r" % (index, declared_hash, recomputed)
        )
    d_i = float(raw.get("D_i_N"))
    if not math.isfinite(d_i) or d_i <= 0.0:
        raise WarmStartSupportError("support record %d D_i_N must be finite and positive, got %r" % (index, d_i))
    source_sha = str(raw.get("source_record_sha", ""))
    if not _is_hex(source_sha, 64):
        raise WarmStartSupportError("support record %d source_record_sha is not 64 hex chars" % index)
    native = _parse_family(raw.get("native_family"), "native_family")
    mesh = _parse_family(raw.get("mesh_family", raw.get("native_family")), "mesh_family")
    same_family = raw.get("same_family")
    return SupportRecord(
        design=design,
        design_hash=declared_hash.lower(),
        native_family=native,
        D_i_N=d_i,
        source_record_sha=source_sha.lower(),
        source_run_id=str(raw.get("source_run_id", "")),
        source_batch_id=str(raw.get("source_batch_id", "")),
        solver_status=str(raw.get("solver_status", "SOLVED_VALID")),
        mesh_family=mesh,
        solver_config_sha256=str(raw.get("solver_config_sha256", "")),
        same_family=None if same_family is None else bool(same_family),
    )


def load_warmstart_support(
    path: Any,
    *,
    expected_sha256: Optional[str] = None,
    expected_designs: int = EXPECTED_DESIGNS,
    expected_task_spec_sha256: Optional[str] = None,
    expected_solver_config_sha256: Optional[str] = None,
) -> WarmStartSupport:
    """Load and validate A1's frozen P2a warm-start support artifact."""
    target = Path(path)
    if not target.is_file():
        raise WarmStartSupportError("A1 warm-start support artifact not found: %s" % (target,))
    raw = target.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and actual_sha.lower() != str(expected_sha256).lower():
        raise WarmStartSupportError(
            "support SHA256 mismatch for %s: bound %s actual %s" % (target, expected_sha256, actual_sha)
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise WarmStartSupportError("support artifact is not valid UTF-8 JSON: %s" % (exc,)) from exc
    if not isinstance(payload, Mapping):
        raise WarmStartSupportError("support artifact must be a JSON object")
    unknown = sorted(set(payload) - _TOP_LEVEL_ALLOWED)
    if unknown:
        raise WarmStartSupportError("support artifact has unknown top-level keys %r" % (unknown,))
    schema = str(payload.get("schema") or payload.get("schema_version") or "")
    if schema != SUPPORT_SCHEMA:
        raise WarmStartSupportError("support schema must be %r, got %r" % (SUPPORT_SCHEMA, schema))
    records_raw = payload.get("records")
    if not isinstance(records_raw, list) or not records_raw:
        raise WarmStartSupportError("support artifact must carry a non-empty records list")
    if len(records_raw) != int(expected_designs):
        raise WarmStartSupportError("support artifact must carry %d designs, got %d" % (expected_designs, len(records_raw)))
    records = tuple(_parse_record(item, index) for index, item in enumerate(records_raw))
    hashes = [record.design_hash for record in records]
    if len(set(hashes)) != len(hashes):
        raise WarmStartSupportError("support artifact has duplicate design_hash values")
    task_spec_sha = str(payload.get("task_spec_sha256", ""))
    solver_sha = str(payload.get("solver_config_sha256", ""))
    if expected_task_spec_sha256 and task_spec_sha and task_spec_sha.lower() != str(expected_task_spec_sha256).lower():
        raise WarmStartSupportError("support task_spec_sha256 does not match the frozen A1 TaskSpec")
    if expected_solver_config_sha256 and solver_sha and solver_sha.lower() != str(expected_solver_config_sha256).lower():
        raise WarmStartSupportError("support solver_config_sha256 does not match the P2a solver config")
    target_mesh_raw = payload.get("target_mesh_family")
    target_mesh = _parse_family(target_mesh_raw, "target_mesh_family") if target_mesh_raw not in (None, "", []) else ()
    source_batch_ids = payload.get("source_batch_ids") or []
    if not isinstance(source_batch_ids, (list, tuple)):
        raise WarmStartSupportError("source_batch_ids must be a list")
    return WarmStartSupport(
        path=str(target),
        sha256=actual_sha,
        bytes=len(raw),
        schema=schema,
        records=records,
        task_spec_sha256=task_spec_sha,
        solver_config_sha256=solver_sha,
        target_mesh_family=target_mesh,
        source_batch_ids=tuple(str(item) for item in source_batch_ids),
    )


def support_candidates(a1_root: Any) -> List[Path]:
    """Deterministic list of pre-registered locations for A1's support artifact."""
    root = Path(a1_root)
    geometry = root / "research" / "concorde_metaopt" / "dreal001" / "geometry"
    return [
        geometry / "p2a_warmstart_support.json",
        geometry / "runs" / "DREAL001-P1C-20261110-01" / "p2a_warmstart_support.json",
        geometry / "runs" / "DREAL001-P1R-20261110-01" / "p2a_warmstart_support.json",
        root / "docs" / "dreal001" / "p2a" / "p2a_warmstart_support.json",
    ]


__all__ = [
    "EXPECTED_DESIGNS",
    "PHYSICAL_CALL_COUNT",
    "SUPPORT_SCHEMA",
    "SupportRecord",
    "WarmStartSupport",
    "WarmStartSupportError",
    "design_hash",
    "load_warmstart_support",
    "support_candidates",
]
