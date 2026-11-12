"""Zero-physical runtime for the P2a v2 (C+B2) package.

The A2 layer never builds geometry and never launches vspaero.exe.  It talks to
the A1 FreezeAPI through an injected callable, records every frozen pair in an
append-only hash-chained log before any solver start, reads the single A1
SolverLedger read-only, and only orchestrates the six arms.

Key invariants:
* one design is frozen once and shared by all six arms;
* a VOID design is globally void, never re-frozen and never partially used;
* the append-only record exists before the first start of that design;
* the A1 ledger is the only writer of solver_attempts.jsonl (A2 only reads);
* preflight runs first and a non-PASS preflight stops the main batch;
* physical_call_count is always 0 in this module.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol, Sequence

GENESIS_HASH = "0" * 64

from .p2a_v2_common import (
    APPEND_LOG_SCHEMA, APPEND_ONLY_LOG_PATH, ARMS, BATCH_ID,
    DESIGN_EVALS_PER_ARM, DISCOVERY_TARGET_ATTEMPTS, FAMILY_SLOTS,
    FAMILY_SLOTS_LABELS, FORCE_ATTEMPTS_PER_FAMILY, FREEZE_API_DISCOVERY_K,
    FREEZE_API_CHAIN_SCHEMA, FREEZE_API_SCHEMA, FREEZE_RECORD_SCHEMA,
    INITIAL_MANIFEST_SCHEMA, INVALID_EVALUATION_STATUS,
    MAX_GEOMETRY_BUILDS_PER_DESIGN, MAX_STARTS, PHYSICAL_CALL_COUNT,
    PREFLIGHT_ACCEPT_NUMERIC_RTOL, PREFLIGHT_CASES, PREFLIGHT_CASES_DEFAULT,
    PREFLIGHT_PLANNED_INTERNAL_CASES, PREFLIGHT_PLANNED_STARTS, Q_PA,
    PREFROZEN_SOURCE_KIND,
    RESERVE_GROUPS, RESERVE_STARTS, RUN_ID, SEED, TIMEOUT_SECONDS,
    INTERNAL_CASES_PER_START, INTERNAL_CASES_PER_START_SOURCE,
)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def internal_cases_from_starts(physical_starts: int) -> int:
    """R10: internal AoA cases are derived from the pre-registered policy constant.

    One physical VSPAERO start always produces exactly INTERNAL_CASES_PER_START
    (7) internal alpha cases; the count is never inferred from the A1 ledger and
    never silently defaulted when the field is absent.
    """
    return int(physical_starts or 0) * int(INTERNAL_CASES_PER_START)


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_x12(x12: Sequence[float]) -> str:
    return "[" + ",".join("%.12g" % float(v) for v in x12) + "]"


def design_hash(x12: Sequence[float]) -> str:
    if len(x12) != 12:
        raise ValueError("x12 must have exactly 12 values")
    return sha256_text(canonical_x12(x12))[:16]


def family_label(pair: Sequence[int]) -> str:
    return "%dx%d" % (int(pair[0]), int(pair[1]))


def parse_family(label: str) -> tuple[int, int]:
    a, b = str(label).lower().split("x")
    return int(a), int(b)


def sort_families(families: Iterable[Sequence[int]]) -> tuple[tuple[int, int], ...]:
    unique = {(int(f[0]), int(f[1])) for f in families}
    return tuple(sorted(unique))


@dataclass(frozen=True)
class FamilyFreeze:
    nodes: int
    elements: int
    vspgeom_sha256: str
    canonical_sha256: str
    vsp3_sha256: str
    attempts: int
    sref_m2: Optional[float] = None
    frozen_vspgeom_bytes: Optional[int] = None
    frozen_vkey_sha256: Optional[str] = None
    frozen_vspgeom_path: Optional[str] = None
    frozen_vkey_path: Optional[str] = None

    @property
    def label(self) -> str:
        return family_label((self.nodes, self.elements))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FrozenDesign:
    design_hash: str
    x12: tuple[float, ...]
    builder_code_sha256: str
    families: tuple[FamilyFreeze, ...]
    discovery_attempts: int
    request_id: str
    freeze_api_version: str = FREEZE_API_SCHEMA

    def sorted_families(self) -> tuple[FamilyFreeze, ...]:
        return tuple(sorted(self.families, key=lambda f: (f.nodes, f.elements)))


@dataclass(frozen=True)
class VoidDesign:
    reason: str
    discovery_attempts: int
    discovered_families: tuple[tuple[int, int], ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class SolverResult:
    status: str
    cdi: Optional[float]
    cl: Optional[float]
    physical_solver_starts: int
    internal_solver_cases: int
    vspgeom_sha_before: str
    vspgeom_sha_after: str
    canonical_sha_after: str
    feasible: bool = True
    errors: tuple[str, ...] = ()
    sref_m2: Optional[float] = None
    polar_sha256: Optional[str] = None


@dataclass
class DesignEvaluation:
    design_index: int
    design_hash: Optional[str]
    primary: Optional[float]
    secondary: Optional[float]
    feasible: bool
    status: str
    starts: int
    family_cdi: dict[str, Optional[float]]
    family_labels: dict[str, str]
    family_sref_m2: dict[str, Optional[float]]
    per_family: list[dict[str, Any]] = field(default_factory=list)
    void_reason: Optional[str] = None
    validation_error: Optional[str] = None
    freeze_record_sha256: Optional[str] = None
    reused_frozen_pair: bool = False
    backend: str = "REAL_VSPAERO"
    internal_solver_cases: Optional[int] = None
    failed_family: Optional[dict[str, Any]] = None


@dataclass
class ArmRunResult:
    arm_id: str
    status: str
    evaluations: list[DesignEvaluation] = field(default_factory=list)
    valid_designs: int = 0
    void_designs: int = 0
    starts: int = 0
    reserve_groups_used: int = 0
    invalid_designs: int = 0

    @property
    def best_primary(self) -> Optional[float]:
        valid = [e.primary for e in self.evaluations if e.status == "SOLVED_VALID" and e.primary is not None]
        return min(valid) if valid else None


class FreezeRecordError(RuntimeError):
    pass


class A1FreezeApiUnavailable(RuntimeError):
    pass


class LedgerReadError(RuntimeError):
    pass


def family_frozen_payload(row: Any) -> dict[str, Any]:
    data = dict(row or {})
    nested = data.get("frozen")
    if isinstance(nested, Mapping) and nested:
        return dict(nested)
    return data


class FreezeRecordStore:
    """Append-only, hash-chained per-design freeze log.

    The log is written by A2 before the first solver start of a design and is
    never rewritten.  A1's FreezeAPI owns geometry bytes and its own attempt log;
    this store is the A2 audit record required by A5 Q2 condition 2.
    """

    def __init__(self, path: Optional[Path] = None, *, run_id: str = RUN_ID,
                 batch_id: str = BATCH_ID, in_memory: bool = False,
                 a1_freeze_api: Any = None) -> None:
        self.run_id = str(run_id)
        self.batch_id = str(batch_id)
        self.path = Path(path) if path is not None else None
        self.a1_freeze_api = a1_freeze_api
        self.in_memory = bool(in_memory) or self.path is None
        self._records: list[dict[str, Any]] = []
        self._by_hash: dict[str, dict[str, Any]] = {}
        self._prev_sha: str = GENESIS_HASH
        if not self.in_memory:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                self._load()
        self._lines: list[str] = [canonical_json(r) for r in self._records]

    def _load(self) -> None:
        if self.a1_freeze_api is not None:
            report = self.a1_freeze_api.verify_chain(self.path)
            if not report.get("valid"):
                raise FreezeRecordError("APPEND_ONLY_CHAIN_INVALID: " +
                                        ",".join(report.get("errors", [])[:3]))
            rows = self.a1_freeze_api.read_chain(self.path)
        else:
            rows = [json.loads(ln) for ln in
                    self.path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            previous = GENESIS_HASH
            for idx, row in enumerate(rows, 1):
                if int(row.get("seq", -1)) != idx:
                    raise FreezeRecordError("A1 seq mismatch at line %d" % idx)
                if str(row.get("parent_hash")) != previous:
                    raise FreezeRecordError("A1 parent_hash mismatch at line %d" % idx)
                if str(row.get("record_hash")) != sha256_text(canonical_json(
                        {k: v for k, v in row.items() if k != "record_hash"})):
                    raise FreezeRecordError("A1 record_hash mismatch at line %d" % idx)
                previous = str(row["record_hash"])
        for row in rows:
            if row.get("physical_call_count") != 0:
                raise FreezeRecordError("freeze record must be zero-physical")
            self._records.append(row)
            self._by_hash[str(row["design_hash"])] = row
            self._prev_sha = str(row["record_hash"])

    @property
    def prev_sha(self) -> str:
        return self._prev_sha

    def records(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._records]

    def get(self, dh: str) -> Optional[dict[str, Any]]:
        rec = self._by_hash.get(str(dh))
        return dict(rec) if rec is not None else None

    def append(self, result: FrozenDesign | VoidDesign, *, request_id: str,
               builder_code_sha256: str = "", freeze_attempts: int = 0,
               design_hash_requested: str = "",
               source_kind: Optional[str] = None,
               reused_prefrozen: bool = False) -> dict[str, Any]:
        if isinstance(result, FrozenDesign):
            dh = result.design_hash
            status = "PAIR_READY"
            x12 = [float(v) for v in result.x12]
            families = {
                f.label: {
                    "nodes": f.nodes, "elements": f.elements,
                    "vspgeom_sha256": f.vspgeom_sha256,
                    "canonical_mesh_sha256": f.canonical_sha256,
                    "vsp3_sha256": f.vsp3_sha256,
                    "frozen_vspgeom_bytes": f.frozen_vspgeom_bytes,
                    "frozen_vkey_sha256": f.frozen_vkey_sha256,
                    "frozen_vspgeom_path": f.frozen_vspgeom_path,
                    "frozen_vkey_path": f.frozen_vkey_path,
                    "attempts": f.attempts,
                    # A1 evaluator_v12._runtime_resolve reads the nested block.
                    "frozen": {
                        "frozen_vspgeom_sha256": f.vspgeom_sha256,
                        "frozen_vkey_sha256": f.frozen_vkey_sha256,
                        "frozen_vsp3_sha256": f.vsp3_sha256,
                        "vspgeom_sha256": f.vspgeom_sha256,
                        "canonical_mesh_sha256": f.canonical_sha256,
                        "frozen_vspgeom_bytes": f.frozen_vspgeom_bytes,
                        "frozen_vspgeom_path": f.frozen_vspgeom_path,
                        "frozen_vkey_path": f.frozen_vkey_path,
                    },
                }
                for f in result.sorted_families()
            }
            if len(families) != 2:
                raise FreezeRecordError("pair_ready needs exactly two families")
            role_map = {slot: lab for slot, lab in zip(FAMILY_SLOTS_LABELS, sorted(families, key=parse_family))}
            discovery_attempts = result.discovery_attempts
            detail = ""
        elif isinstance(result, VoidDesign):
            dh = ""
            status = "DESIGN_VOID"
            x12 = []
            families = {}
            role_map = {}
            discovery_attempts = result.discovery_attempts
            detail = result.reason + ((": " + result.detail) if result.detail else "")
        else:
            raise TypeError("append expects FrozenDesign or VoidDesign")

        if status == "DESIGN_VOID":
            dh = str(design_hash_requested or ("void-" + sha256_text(canonical_json({
                "reason": result.reason, "detail": result.detail,
                "discovered": [list(x) for x in result.discovered_families],
                "discovery_attempts": result.discovery_attempts,
            }))[:16]))

        existing = self._by_hash.get(dh)
        if existing is not None:
            return existing
        payload = {
            "a2_schema": FREEZE_RECORD_SCHEMA,
            "schema_version": "1",
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "design_hash": dh,
            "x12": x12,
            "status": status,
            "request_id": str(request_id),
            "builder_code_sha256": str(builder_code_sha256),
            "freeze_api_schema": FREEZE_API_SCHEMA,
            "freeze_api_discovery_k": FREEZE_API_DISCOVERY_K,
            "discovery_attempts": int(discovery_attempts),
            "freeze_attempts": int(freeze_attempts),
            "families": families,
            "family_role_map": role_map,
            "roles": dict(role_map),
            "arm_blind": True,
            "kind": "DESIGN_FREEZE",
            "arm_id": "ALL_SIX_SHARED",
            "slot_id": "SHARED-" + dh,
            "shared_by_arms": list(ARMS),
            "detail": detail,
            "created_utc": utc_now(),
            "physical_call_count": 0,
        }
        if source_kind:
            payload["source_kind"] = str(source_kind)
            payload["reused_prefrozen"] = bool(reused_prefrozen)
        # A1 freeze_api owns seq / parent_hash / record_hash semantics.  When the
        # A1 module is injected the writer and the reader are exactly A1's own
        # append_chained_record / verify_chain (single source of truth).
        if self.a1_freeze_api is not None and not self.in_memory:
            record = self.a1_freeze_api.append_chained_record(self.path, payload)
        else:
            seq = len(self._records) + 1
            record = dict(payload, schema=FREEZE_API_CHAIN_SCHEMA, seq=seq,
                          parent_hash=self._prev_sha, physical_call_count=0)
            record["record_hash"] = sha256_text(canonical_json(
                {k: v for k, v in record.items() if k != "record_hash"}))
            line = canonical_json(record)
            if not self.in_memory:
                with self.path.open("a", encoding="utf-8", newline="\n") as fh:
                    fh.write(line + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
        self._records.append(record)
        self._by_hash[dh] = record
        self._prev_sha = str(record["record_hash"])
        self._lines.append(canonical_json(record))
        return dict(record)

    def require(self, dh: str, families: Sequence[FamilyFreeze]) -> dict[str, Any]:
        rec = self.get(dh)
        if rec is None:
            raise FreezeRecordError("no append-only freeze record for design %s" % dh)
        if rec.get("status") != "PAIR_READY":
            raise FreezeRecordError("design %s is not PAIR_READY (%s)" % (dh, rec.get("status")))
        have = rec.get("families") or {}
        if set(have) != {f.label for f in families}:
            raise FreezeRecordError("freeze record family set mismatch for %s" % dh)
        for f in families:
            row = have[f.label]
            if row.get("vspgeom_sha256") != f.vspgeom_sha256:
                raise FreezeRecordError("frozen vspgeom SHA mismatch for %s/%s" % (dh, f.label))
            if row.get("canonical_mesh_sha256") != f.canonical_sha256:
                raise FreezeRecordError("canonical mesh SHA mismatch for %s/%s" % (dh, f.label))
        return rec

    def verify_chain(self) -> dict[str, Any]:
        if self.a1_freeze_api is not None and not self.in_memory:
            report = self.a1_freeze_api.verify_chain(self.path)
            if not report.get("valid"):
                raise FreezeRecordError("APPEND_ONLY_CHAIN_INVALID: " +
                                        ",".join(report.get("errors", [])[:3]))
            return {"ok": True, "records": len(self._records),
                    "head_sha256": str(report.get("head_hash") or self._prev_sha), "a1": report}
        previous = GENESIS_HASH
        for idx, record in enumerate(self._records):
            if int(record.get("seq", -1)) != idx + 1:
                raise FreezeRecordError("A1 seq mismatch at index %d" % idx)
            if str(record.get("parent_hash")) != previous:
                raise FreezeRecordError("A1 parent_hash mismatch at index %d" % idx)
            if str(record.get("record_hash")) != sha256_text(canonical_json(
                    {k: v for k, v in record.items() if k != "record_hash"})):
                raise FreezeRecordError("A1 record_hash mismatch at index %d" % idx)
            previous = str(record["record_hash"])
        return {"ok": True, "records": len(self._records), "head_sha256": previous}

    def sha256_of_log(self) -> Optional[str]:
        if self.in_memory:
            return sha256_text("\n".join(self._lines) + ("\n" if self._lines else ""))
        return sha256_file(self.path) if self.path.exists() else None


class A1FreezeApiAdapter:
    """Thin adapter over A1 discover_and_freeze_pair.

    A1 owns discovery/force/freeze and its attempt log.  A2 only maps the A1
    record into FrozenDesign/VoidDesign and records it.  If the A1 callable is
    missing the adapter fails closed instead of re-implementing the policy.
    """

    def __init__(self, freeze_fn: Optional[Callable[..., Mapping[str, Any]]],
                 *, builder_code_sha256: str = "", freeze_api_sha256: str = "",
                 api_version: str = FREEZE_API_SCHEMA) -> None:
        self.freeze_fn = freeze_fn
        self.builder_code_sha256 = str(builder_code_sha256)
        self.freeze_api_sha256 = str(freeze_api_sha256)
        self.api_version = str(api_version)

    @property
    def available(self) -> bool:
        return callable(self.freeze_fn)

    def build(self, x12: Sequence[float], request_id: str, out_dir: Path) -> FrozenDesign | VoidDesign:
        if not self.available:
            raise A1FreezeApiUnavailable(
                "A1 FreezeAPI discover_and_freeze_pair is not importable; "
                "A2 must not re-implement discovery/force/freeze"
            )
        rec = self.freeze_fn(
            x12=[float(v) for v in x12],
            design_hash=design_hash(x12),
            out_dir=str(out_dir),
            policy={
                "discovery_cap": 20, "single_family_extend": 40,
                "cap_per_family": 40, "union_void_at": 3,
            },
            builder_sha=self.builder_code_sha256,
        )
        if not isinstance(rec, Mapping):
            raise A1FreezeApiUnavailable("A1 FreezeAPI returned no mapping")
        status = str(rec.get("status", ""))
        if status == "PAIR_READY":
            families = rec.get("families")
            if not isinstance(families, Mapping) or len(families) != 2:
                raise A1FreezeApiUnavailable("A1 FreezeAPI PAIR_READY without two families")
            parsed: list[FamilyFreeze] = []
            for label, entry in families.items():
                frozen = family_frozen_payload(entry)
                parsed.append(FamilyFreeze(
                    nodes=int(parse_family(str(label))[0]),
                    elements=int(parse_family(str(label))[1]),
                    vspgeom_sha256=str(frozen.get("frozen_vspgeom_sha256") or frozen.get("vspgeom_sha256") or ""),
                    canonical_sha256=str(frozen.get("canonical_mesh_sha256") or ""),
                    vsp3_sha256=str(frozen.get("frozen_vsp3_sha256") or frozen.get("vsp3_sha256") or ""),
                    attempts=int(entry.get("attempts", 0) or 0),
                    sref_m2=frozen.get("sref_m2"),
                    frozen_vspgeom_bytes=frozen.get("frozen_vspgeom_bytes"),
                    frozen_vkey_sha256=frozen.get("frozen_vkey_sha256"),
                    frozen_vspgeom_path=frozen.get("frozen_vspgeom_path"),
                    frozen_vkey_path=frozen.get("frozen_vkey_path"),
                ))
            if any(not f.vspgeom_sha256 or not f.canonical_sha256 for f in parsed):
                raise A1FreezeApiUnavailable("A1 FreezeAPI family record missing frozen SHA")
            return FrozenDesign(
                design_hash=design_hash(x12), x12=tuple(float(v) for v in x12),
                builder_code_sha256=self.builder_code_sha256,
                families=tuple(parsed),
                discovery_attempts=int(rec.get("discovery_attempts", 0) or 0),
                request_id=str(request_id), freeze_api_version=self.api_version,
            )
        reason = status if status else "FREEZE_API_REFUSED"
        discovered = tuple(
            parse_family(str(x)) for x in (rec.get("discovered_families") or []) if "x" in str(x)
        )
        return VoidDesign(
            reason=reason, discovery_attempts=int(rec.get("discovery_attempts", 0) or 0),
            discovered_families=sort_families(discovered),
            detail=str(rec.get("detail") or rec.get("error") or ""),
        )


class FrozenPairService:
    """Freeze once, reuse for all six arms, append the record before any start."""

    def __init__(self, adapter: A1FreezeApiAdapter, store: FreezeRecordStore,
                 build_root: Path, *,
                 prefrozen_manifest: Optional[Mapping[str, Any]] = None,
                 static_index_hashes: Optional[Iterable[str]] = None,
                 describe_mesh: Optional[Callable[[Path], Mapping[str, Any]]] = None) -> None:
        self.adapter = adapter
        self.store = store
        self.build_root = Path(build_root)
        self.builds = 0
        self.describe_mesh = describe_mesh
        self.static_index_hashes = {str(h) for h in (static_index_hashes or ())}
        self._prefrozen: dict[str, dict[str, Any]] = {}
        for design in ((prefrozen_manifest or {}).get("designs") or []):
            if not isinstance(design, Mapping):
                continue
            dh = str(design.get("design_hash") or "")
            families = design.get("families")
            if dh and isinstance(families, Mapping) and families:
                self._prefrozen[dh] = dict(design)
        self.prefrozen_reuse_evidence: dict[str, Any] = {}

    @property
    def prefrozen_hashes(self) -> list[str]:
        return sorted(self._prefrozen)

    def get(self, x12: Sequence[float]) -> Optional[dict[str, Any]]:
        return self.store.get(design_hash(x12))

    def get_or_freeze(self, x12: Sequence[float], request_id: str) -> tuple[FrozenDesign | VoidDesign, dict[str, Any], bool]:
        dh = design_hash(x12)
        existing = self.store.get(dh)
        if existing is not None:
            if existing.get("status") == "PAIR_READY":
                return self._design_from_record(existing), existing, True
            return self._void_from_record(existing), existing, True
        if dh in self._prefrozen:
            return self._reuse_prefrozen(x12, dh, request_id)
        if dh in self.static_index_hashes:
            void = VoidDesign(
                reason="STATIC_INDEX_HIT_NOT_PREFROZEN",
                detail=("A1 static pair manifest contains %s but R8 may only use pinned "
                        "prefrozen designs 15/16/17; fail-closed, no rebuild" % dh),
            )
            record = self.store.append(
                void, request_id=request_id,
                builder_code_sha256=self.adapter.builder_code_sha256,
                design_hash_requested=dh, source_kind="STATIC_INDEX_HIT",
            )
            return void, record, False
        self.builds += 1
        result = self.adapter.build(x12, request_id, self.build_root / dh)
        record = self.store.append(
            result, request_id=request_id,
            builder_code_sha256=self.adapter.builder_code_sha256,
            freeze_attempts=int(getattr(result, "discovery_attempts", 0) or 0),
            design_hash_requested=dh,
        )
        if isinstance(result, FrozenDesign):
            return result, record, False
        return result, record, False

    def _reuse_prefrozen(self, x12: Sequence[float], dh: str,
                         request_id: str) -> tuple[FrozenDesign, dict[str, Any], bool]:
        """P1: copy the pinned pre-frozen pair from the A1 manifest, never rebuild."""
        entry = self._prefrozen[dh]
        expected_x12 = canonical_x12([float(v) for v in (entry.get("x12") or [])])
        if canonical_x12([float(v) for v in x12]) != expected_x12:
            raise FreezeRecordError("PREFROZEN_X12_MISMATCH for design %s" % dh)
        if self.describe_mesh is None:
            raise FreezeRecordError(
                "PREFROZEN_REUSE_REQUIRES_DESCRIBE_MESH: cannot verify canonical mesh")
        families: list[FamilyFreeze] = []
        evidence: dict[str, Any] = {}
        rows = sorted((entry.get("families") or {}).items(), key=lambda kv: parse_family(str(kv[0])))
        for label, row in rows:
            frozen = family_frozen_payload(row)
            geom_src = Path(str(frozen.get("frozen_vspgeom_path") or ""))
            if not geom_src.is_file():
                raise FreezeRecordError("PREFROZEN_GEOM_MISSING %s/%s" % (dh, label))
            geom_sha = sha256_file(geom_src)
            if geom_sha != str(frozen.get("frozen_vspgeom_sha256") or ""):
                raise FreezeRecordError("PREFROZEN_GEOM_SHA_MISMATCH %s/%s" % (dh, label))
            geom_bytes = geom_src.stat().st_size
            if frozen.get("frozen_vspgeom_bytes") is not None:
                if int(frozen["frozen_vspgeom_bytes"]) != geom_bytes:
                    raise FreezeRecordError("PREFROZEN_GEOM_BYTES_MISMATCH %s/%s" % (dh, label))
            vkey_src = geom_src.parent / "model.vkey"
            vsp3_src = geom_src.parent / "model.vsp3"
            for pth, key, what in (
                    (vkey_src, "frozen_vkey_sha256", "VKEY"),
                    (vsp3_src, "frozen_vsp3_sha256", "VSP3")):
                if not pth.is_file():
                    raise FreezeRecordError("PREFROZEN_%s_MISSING %s/%s" % (what, dh, label))
                if sha256_file(pth) != str(frozen.get(key) or ""):
                    raise FreezeRecordError("PREFROZEN_%s_SHA_MISMATCH %s/%s" % (what, dh, label))
            mesh = self.describe_mesh(geom_src)
            canonical = str(mesh.get("canonical_mesh_sha256") or "")
            if canonical != str(frozen.get("canonical_mesh_sha256") or ""):
                raise FreezeRecordError("PREFROZEN_CANONICAL_MISMATCH %s/%s" % (dh, label))
            if str(mesh.get("vspgeom_sha256") or "") not in ("", geom_sha):
                raise FreezeRecordError("PREFROZEN_VSPGEOM_SHA_MISMATCH %s/%s" % (dh, label))
            dest = self.build_root / dh / "freeze" / str(label)
            dest.mkdir(parents=True, exist_ok=True)
            dest_geom = dest / "model.vspgeom"
            dest_vkey = dest / "model.vkey"
            dest_vsp3 = dest / "model.vsp3"
            shutil.copyfile(geom_src, dest_geom)
            shutil.copyfile(vkey_src, dest_vkey)
            shutil.copyfile(vsp3_src, dest_vsp3)
            vkey_sha = sha256_file(vkey_src)
            vsp3_sha = sha256_file(vsp3_src)
            if (sha256_file(dest_geom) != geom_sha
                    or sha256_file(dest_vkey) != vkey_sha
                    or sha256_file(dest_vsp3) != vsp3_sha):
                raise FreezeRecordError("PREFROZEN_COPY_SHA_MISMATCH %s/%s" % (dh, label))
            nodes, elements = parse_family(str(label))
            families.append(FamilyFreeze(
                nodes=nodes, elements=elements,
                vspgeom_sha256=geom_sha,
                canonical_sha256=canonical,
                vsp3_sha256=vsp3_sha,
                attempts=0,
                frozen_vspgeom_bytes=geom_bytes,
                frozen_vkey_sha256=vkey_sha,
                frozen_vspgeom_path=str(dest_geom),
                frozen_vkey_path=str(dest_vkey),
            ))
            evidence[str(label)] = {
                "source_geom": str(geom_src), "source_geom_sha256": geom_sha,
                "source_geom_bytes": geom_bytes,
                "copied_geom": str(dest_geom), "copied_geom_sha256": geom_sha,
                "vkey_sha256": vkey_sha, "vsp3_sha256": vsp3_sha,
                "canonical_mesh_sha256": canonical, "nodes": nodes, "elements": elements,
            }
        if len(families) != 2:
            raise FreezeRecordError("PREFROZEN_FAMILY_COUNT %s != 2" % dh)
        design = FrozenDesign(
            design_hash=dh, x12=tuple(float(v) for v in x12),
            builder_code_sha256=self.adapter.builder_code_sha256,
            families=tuple(families), discovery_attempts=0,
            request_id=str(request_id), freeze_api_version=FREEZE_API_SCHEMA,
        )
        record = self.store.append(
            design, request_id=request_id,
            builder_code_sha256=self.adapter.builder_code_sha256,
            freeze_attempts=0, design_hash_requested=dh,
            source_kind=PREFROZEN_SOURCE_KIND, reused_prefrozen=True,
        )
        self.prefrozen_reuse_evidence[dh] = {
            "design_hash": dh,
            "design_index": int(entry.get("design_index") or -1),
            "families": evidence,
            "record_hash": str(record.get("record_hash") or ""),
            "record_status": str(record.get("status") or ""),
            "source_kind": PREFROZEN_SOURCE_KIND,
            "attempts": 0,
        }
        return design, record, False

    def _design_from_record(self, rec: Mapping[str, Any]) -> FrozenDesign:
        families = []
        for label, row in (rec.get("families") or {}).items():
            families.append(FamilyFreeze(
                nodes=int(row["nodes"]), elements=int(row["elements"]),
                vspgeom_sha256=str(row["vspgeom_sha256"]),
                canonical_sha256=str(row["canonical_mesh_sha256"]),
                vsp3_sha256=str(row.get("vsp3_sha256") or ""),
                attempts=int(row.get("attempts", 0) or 0),
                frozen_vspgeom_bytes=row.get("frozen_vspgeom_bytes"),
                frozen_vkey_sha256=row.get("frozen_vkey_sha256"),
                frozen_vspgeom_path=row.get("frozen_vspgeom_path"),
                frozen_vkey_path=row.get("frozen_vkey_path"),
            ))
        return FrozenDesign(
            design_hash=str(rec["design_hash"]),
            x12=tuple(float(v) for v in rec.get("x12") or []),
            builder_code_sha256=str(rec.get("builder_code_sha256") or ""),
            families=tuple(families),
            discovery_attempts=int(rec.get("discovery_attempts", 0) or 0),
            request_id=str(rec.get("request_id") or ""),
            freeze_api_version=str(rec.get("freeze_api_schema") or FREEZE_API_SCHEMA),
        )

    def _void_from_record(self, rec: Mapping[str, Any]) -> VoidDesign:
        return VoidDesign(
            reason=str(rec.get("detail") or "DESIGN_VOID").split(":")[0],
            discovery_attempts=int(rec.get("discovery_attempts", 0) or 0),
            discovered_families=tuple(), detail=str(rec.get("detail") or ""),
        )


class A1LedgerReader:
    """Read-only view of A1's append-only solver_attempts.jsonl."""

    def __init__(self, attempts_path: Optional[Path], *, run_id: str = RUN_ID) -> None:
        self.path = Path(attempts_path) if attempts_path is not None else None
        self.run_id = str(run_id)

    def rows(self) -> list[dict[str, Any]]:
        if self.path is None or not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def count_starts(self) -> int:
        # A1 ledger rows carry case_id, not physical_solver_starts/attempt_id.
        return sum(1 for row in self.rows() if row.get("event") == "start")

    def audit(self) -> dict[str, Any]:
        rows = self.rows()
        starts = [r for r in rows if r.get("event") == "start"]
        ends = [r for r in rows if r.get("event") == "end"]
        start_ids = [str(r.get("case_id")) for r in starts]
        end_ids = [str(r.get("case_id")) for r in ends]
        duplicates = sorted({x for x in start_ids if start_ids.count(x) > 1})
        if duplicates:
            raise LedgerReadError("duplicate start case_id(s): %s" % ",".join(duplicates[:5]))
        unpaired = sorted(set(start_ids) - set(end_ids))
        orphan_ends = sorted(set(end_ids) - set(start_ids))
        repaired = [r for r in ends if r.get("repair") is True]
        return {
            "schema": "dreal001.p2a_v2.ledger_audit.v1",
            "path": str(self.path) if self.path is not None else None,
            "run_id": self.run_id, "starts": len(starts), "ends": len(ends),
            "physical_solver_starts": len(starts),
            "internal_solver_cases": None,  # ledger rows carry no internal count
            "internal_solver_cases_source": "evaluations/record; A1 ledger does not record internal cases",
            "ledger_internal_cases_recorded": sum(int(r.get("internal_solver_cases", 0) or 0) for r in ends),
            "duplicate_start_case_ids": duplicates,
            "unpaired_start_case_ids": unpaired,
            "orphan_end_case_ids": orphan_ends,
            "executor_exception_repairs": len(repaired),
            "paired": len(starts) == len(ends) and not unpaired and not orphan_ends,
            "pairing_key": "case_id",
            "attempt_id": "informational_only (A1 resets per evaluator instance)",
            "read_only": True,
        }

class PreflightVerifier:
    """Verify the 3 A1 preflight replay cases before any main-batch start."""

    def __init__(self, bundle_manifest: Mapping[str, Any], *,
                 bundle_root: Optional[Path] = None,
                 replay_fn: Optional[Callable[[Mapping[str, Any]], Mapping[str, Any]]] = None,
                 replay_fn_factory: Optional[Callable[[Mapping[str, Any]], Callable[[Mapping[str, Any]], Mapping[str, Any]]]] = None,
                 accept_numeric: bool = False,
                 numeric_rtol: float = PREFLIGHT_ACCEPT_NUMERIC_RTOL) -> None:
        self.manifest = dict(bundle_manifest)
        self.bundle_root = Path(bundle_root) if bundle_root is not None else None
        self.replay_fn = replay_fn
        # P0-b: A1 evaluator dedupes (design_hash, family); PRE-01 and PRE-03 are the
        # same cell, so each preflight case MUST use a fresh evaluator instance.
        self.replay_fn_factory = replay_fn_factory
        self.accept_numeric = bool(accept_numeric)
        self.numeric_rtol = float(numeric_rtol)
        self.cases = list(self.manifest.get("cases") or [])
        if len(self.cases) != PREFLIGHT_CASES:
            raise ValueError("preflight bundle must contain exactly %d cases" % PREFLIGHT_CASES)
        self.manifest_canonical_sha256 = sha256_text(canonical_json(self.manifest))
        manifest_file = (self.bundle_root / "bundle_manifest.json") if self.bundle_root is not None else None
        if manifest_file is not None and manifest_file.is_file():
            self.manifest_sha256 = sha256_file(manifest_file)
            self.manifest_sha256_source = "FILE_BYTES"
        else:
            self.manifest_sha256 = self.manifest_canonical_sha256
            self.manifest_sha256_source = "CANONICAL_JSON_DIGEST"

    def _file_checks(self, case: Mapping[str, Any]) -> dict[str, Any]:
        out = {}
        if self.bundle_root is None:
            return out
        for name, meta in (case.get("files") or {}).items():
            p = self.bundle_root / str(case["case_id"]) / name
            if not p.is_file():
                out[name] = {"status": "MISSING", "path": str(p)}
                continue
            digest = sha256_file(p)
            ok = digest == str(meta.get("sha256") or "") and p.stat().st_size == int(meta.get("bytes", -1))
            out[name] = {"status": "MATCH" if ok else "MISMATCH", "path": str(p), "sha256": digest}
        return out

    def run(self) -> dict[str, Any]:
        results = []
        for case in self.cases:
            row = {
                "case_id": case.get("case_id"),
                "backend": "REPLAY_B2", "preflight": True,
                "counted_in_starts": True, "excluded_from_e1_e6": True, "design_hash": case.get("design_hash"),
                "family_label": case.get("family_label"),
                "expected_polar_sha256": case.get("expected_polar_sha256"),
                "file_checks": self._file_checks(case), "status": "NOT_RUN",
                "is_hard_fail": False, "starts": 0, "record_starts": 0,
                "ledger_delta": None, "starts_consistent": None,
                "internal_cases": 0, "physical_call_count": 0, "errors": [],
            }
            fn = self.replay_fn
            if self.replay_fn_factory is not None:
                fn = self.replay_fn_factory(dict(case))
            if fn is None:
                row["detail"] = "A1 replay callable not provided; preflight not run"
                results.append(row)
                continue
            try:
                outcome = dict(fn(dict(case)) or {})
            except Exception as exc:  # noqa: BLE001
                row["status"] = "FAIL"
                row["is_hard_fail"] = True
                row["detail"] = "replay exception: %s: %s" % (type(exc).__name__, exc)
                results.append(row)
                continue
            row["actual_polar_sha256"] = outcome.get("polar_sha256")
            row["actual_mesh_family"] = outcome.get("mesh_family")
            row["starts"] = int(outcome.get("starts", outcome.get("physical_solver_starts", 0)) or 0)
            row["record_starts"] = int(outcome.get("record_starts", outcome.get("physical_solver_starts", 0)) or 0)
            row["ledger_delta"] = outcome.get("ledger_delta")
            row["starts_consistent"] = outcome.get("starts_consistent")
            row["physical_call_count"] = int(row["record_starts"] or row["starts"] or 0)
            row["physical_call_count_source"] = "per-case record solver.physical_solver_starts / canonical ledger delta"
            row["planned_starts"] = 1
            row["internal_cases"] = int(outcome.get("internal_solver_cases") or 0)
            row["errors"] = list(outcome.get("errors") or [])
            if row["starts_consistent"] is False:
                row["status"] = "FAIL"
                row["is_hard_fail"] = True
                row["detail"] = "per-case starts mismatch: record=%s ledger_delta=%s" % (
                    row["record_starts"], row["ledger_delta"])
            elif str(outcome.get("status", "SOLVED_VALID")) != "SOLVED_VALID":
                row["status"] = "FAIL"
                row["is_hard_fail"] = True
                row["detail"] = "non-SOLVED replay: %s" % (outcome.get("status"),)
            elif str(outcome.get("polar_sha256")) == str(case.get("expected_polar_sha256")):
                row["status"] = "PASS_BYTE"
            else:
                mesh_ok = tuple(outcome.get("mesh_family") or ()) == tuple(case.get("mesh_family") or ())
                max_rel = outcome.get("numeric_max_rel")
                numeric_ok = mesh_ok and max_rel is not None and float(max_rel) <= self.numeric_rtol
                if numeric_ok:
                    row["status"] = "PASS_NUMERIC"
                    row["numeric_max_rel"] = float(max_rel)
                else:
                    row["status"] = "FAIL"
                    row["is_hard_fail"] = True
                    row["detail"] = "polar bytes and numeric/mesh judgement both differ"
            results.append(row)
        if self.replay_fn is None and self.replay_fn_factory is None:
            overall = "PREFLIGHT_NOT_RUN"
        elif any(r["status"] == "FAIL" for r in results):
            overall = "PREFLIGHT_FAIL"
        elif all(r["status"] == "PASS_BYTE" for r in results):
            overall = "PREFLIGHT_PASS_BYTE"
        elif all(r["status"] in ("PASS_BYTE", "PASS_NUMERIC") for r in results):
            overall = "PREFLIGHT_PASS_NUMERIC_ACCEPTED" if self.accept_numeric else "PREFLIGHT_PASS_NUMERIC_PENDING_ACCEPTANCE"
        else:
            overall = "PREFLIGHT_NOT_RUN"
        return {
            "schema": "dreal001.p2a_v2.preflight_result.v1",
            "bundle_manifest_sha256": self.manifest_sha256,
            "bundle_manifest_canonical_sha256": self.manifest_canonical_sha256,
            "bundle_manifest_sha256_source": self.manifest_sha256_source,
            "cases": results, "overall": overall,
            "main_batch_may_start": overall in ("PREFLIGHT_PASS_BYTE", "PREFLIGHT_PASS_NUMERIC_ACCEPTED"),
            "numeric_acceptance_required": True, "accepted_numeric": bool(self.accept_numeric),
            "planned_starts": PREFLIGHT_PLANNED_STARTS,
            "planned_internal_cases": PREFLIGHT_PLANNED_INTERNAL_CASES,
            "preflight": True, "backend": "REPLAY_B2",
            "physical_call_count": sum(int(r.get("physical_call_count") or r.get("starts") or 0) for r in results),
            "physical_call_count_source": "sum of per-case physical_call_count (record solver.physical_solver_starts / canonical ledger delta); executor reconciles to canonical ledger",
            "counted_in_e1_e6": False,
        }


class P2AV2Runner:
    def __init__(self, freeze_service: FrozenPairService, solver: Any,
                 store: FreezeRecordStore, *, ledger_reader: Optional[A1LedgerReader] = None,
                 max_starts: int = MAX_STARTS) -> None:
        self.freeze_service = freeze_service
        self.solver = solver
        self.store = store
        self.ledger_reader = ledger_reader
        self.max_starts = int(max_starts)

    def _ledger_allows(self) -> bool:
        if self.ledger_reader is None:
            return True
        return int(self.ledger_reader.count_starts()) < self.max_starts

    @staticmethod
    def _internal_of(per_family: Sequence[dict[str, Any]]) -> int:
        return sum(int((row or {}).get("internal_solver_cases", 0) or 0) for row in per_family)

    def run_one(self, x12: Sequence[float], design_index: int, request_id: Optional[str] = None) -> DesignEvaluation:
        dh = design_hash(x12)
        rid = request_id or "req-%s-%03d" % (dh, design_index)
        frozen, record, reused = self.freeze_service.get_or_freeze(x12, rid)
        if isinstance(frozen, VoidDesign):
            return DesignEvaluation(
                design_index=design_index, design_hash=None, primary=None, secondary=None,
                feasible=False, status="DESIGN_VOID", starts=0, family_cdi={},
                family_labels={}, family_sref_m2={}, void_reason=frozen.reason,
                freeze_record_sha256=str(record.get("record_hash") or ""),
                reused_frozen_pair=reused, internal_solver_cases=0,
            )
        families = frozen.sorted_families()
        if len(families) != 2:
            return DesignEvaluation(
                design_index=design_index, design_hash=dh, primary=None, secondary=None,
                feasible=False, status="NOT_VALIDATED", starts=0, family_cdi={},
                family_labels={}, family_sref_m2={}, validation_error="FAMILY_PAIR_NOT_TWO",
                freeze_record_sha256=str(record.get("record_hash") or ""),
                reused_frozen_pair=reused, internal_solver_cases=0,
            )
        try:
            self.store.require(dh, families)
        except FreezeRecordError as exc:
            return DesignEvaluation(
                design_index=design_index, design_hash=dh, primary=None, secondary=None,
                feasible=False, status="NOT_VALIDATED", starts=0, family_cdi={},
                family_labels={}, family_sref_m2={}, validation_error=str(exc),
                freeze_record_sha256=str(record.get("record_hash") or ""),
                reused_frozen_pair=reused, internal_solver_cases=0,
            )
        per_family: list[dict[str, Any]] = []
        starts = 0
        for slot, family in zip(FAMILY_SLOTS_LABELS, families):
            if not self._ledger_allows():
                return DesignEvaluation(
                    design_index=design_index, design_hash=dh, primary=None, secondary=None,
                    feasible=False, status="NOT_VALIDATED", starts=starts,
                    family_cdi={}, family_labels={}, family_sref_m2={}, per_family=per_family,
                    validation_error="LEDGER_BUDGET_EXHAUSTED",
                    freeze_record_sha256=str(record.get("record_hash") or ""),
                    reused_frozen_pair=reused, internal_solver_cases=self._internal_of(per_family),
                )
            try:
                result = self.solver.evaluate(family, dh, slot, x12=x12)
            except TypeError:
                result = self.solver.evaluate(family, dh, slot)
            starts += int(result.physical_solver_starts)
            if (result.vspgeom_sha_before != family.vspgeom_sha256
                    or result.vspgeom_sha_after != family.vspgeom_sha256
                    or result.canonical_sha_after != family.canonical_sha256):
                failed = {"family_slot": slot, "family": family.label,
                          "status": "FROZEN_BYTES_SHA_MISMATCH",
                          "internal_solver_cases": int(result.internal_solver_cases)}
                return DesignEvaluation(
                    design_index=design_index, design_hash=dh, primary=None, secondary=None,
                    feasible=False, status="NOT_VALIDATED", starts=starts,
                    family_cdi={}, family_labels={}, family_sref_m2={}, per_family=per_family,
                    validation_error="FROZEN_BYTES_SHA_MISMATCH",
                    freeze_record_sha256=str(record.get("record_hash") or ""),
                    reused_frozen_pair=reused,
                    internal_solver_cases=self._internal_of(per_family) + int(result.internal_solver_cases),
                    failed_family=failed,
                )
            if result.status != "SOLVED_VALID":
                failed = {"family_slot": slot, "family": family.label,
                          "status": result.status,
                          "raw_status": result.status,
                          "polar_sha256": getattr(result, "polar_sha256", None),
                          "internal_solver_cases": int(result.internal_solver_cases)}
                return DesignEvaluation(
                    design_index=design_index, design_hash=dh, primary=None, secondary=None,
                    feasible=False, status=INVALID_EVALUATION_STATUS, starts=starts,
                    family_cdi={}, family_labels={}, family_sref_m2={}, per_family=per_family,
                    validation_error=result.status,
                    freeze_record_sha256=str(record.get("record_hash") or ""),
                    reused_frozen_pair=reused,
                    internal_solver_cases=self._internal_of(per_family) + int(result.internal_solver_cases),
                    failed_family=failed,
                )
            if result.cdi is None or not math.isfinite(float(result.cdi)) or float(result.cdi) < 0.0:
                failed = {"family_slot": slot, "family": family.label,
                          "status": "INVALID_CDI",
                          "raw_status": result.status,
                          "polar_sha256": getattr(result, "polar_sha256", None),
                          "internal_solver_cases": int(result.internal_solver_cases)}
                return DesignEvaluation(
                    design_index=design_index, design_hash=dh, primary=None, secondary=None,
                    feasible=False, status=INVALID_EVALUATION_STATUS, starts=starts,
                    family_cdi={}, family_labels={}, family_sref_m2={}, per_family=per_family,
                    validation_error="INVALID_CDI",
                    freeze_record_sha256=str(record.get("record_hash") or ""),
                    reused_frozen_pair=reused,
                    internal_solver_cases=self._internal_of(per_family) + int(result.internal_solver_cases),
                    failed_family=failed,
                )
            per_family.append({
                "family_slot": slot, "family": family.label, "cdi": float(result.cdi),
                "backend": "REAL_VSPAERO",
                "cl": result.cl, "feasible": bool(result.feasible),
                "sref_m2": result.sref_m2 if result.sref_m2 is not None else family.sref_m2,
                "internal_solver_cases": int(result.internal_solver_cases),
                "vspgeom_sha256": family.vspgeom_sha256,
                "canonical_sha256": family.canonical_sha256,
                "polar_sha256": getattr(result, "polar_sha256", None),
            })
        cdi_values = [float(row["cdi"]) for row in per_family]
        primary = sum(cdi_values) / len(cdi_values)
        srefs = [row["sref_m2"] for row in per_family]
        secondary = None
        if all(s is not None and math.isfinite(float(s)) for s in srefs):
            secondary = Q_PA * (sum(float(s) for s in srefs) / len(srefs)) * primary
        return DesignEvaluation(
            design_index=design_index, design_hash=dh, primary=primary, secondary=secondary,
            feasible=all(bool(row["feasible"]) for row in per_family), status="SOLVED_VALID",
            starts=starts,
            family_cdi={row["family_slot"]: row["cdi"] for row in per_family},
            family_labels={row["family_slot"]: row["family"] for row in per_family},
            family_sref_m2={row["family_slot"]: row["sref_m2"] for row in per_family},
            per_family=per_family,
            freeze_record_sha256=str(record.get("record_hash") or ""),
            reused_frozen_pair=reused,
            internal_solver_cases=self._internal_of(per_family),
        )


@dataclass
class ReservePool:
    groups_total: int = RESERVE_GROUPS
    starts_total: int = RESERVE_STARTS
    groups_used: int = 0
    starts_used: int = 0

    @property
    def groups_left(self) -> int:
        return max(0, self.groups_total - self.groups_used)

    def consume(self) -> bool:
        if self.groups_used >= self.groups_total:
            return False
        self.groups_used += 1
        self.starts_used += 2
        return True


class P2AV2Batch:
    """Preflight -> six arms; freeze once per design; append-only before start."""

    def __init__(self, runner: P2AV2Runner, *, preflight: Optional[PreflightVerifier] = None,
                 accept_preflight_numeric: bool = False,
                 reserve_pool: Optional[ReservePool] = None,
                 voided_designs: Optional[set[str]] = None) -> None:
        self.runner = runner
        self.preflight = preflight
        self.accept_preflight_numeric = bool(accept_preflight_numeric)
        self.reserve = reserve_pool if reserve_pool is not None else ReservePool()
        self.voided_designs: set[str] = voided_designs if voided_designs is not None else set()
        self.preflight_result: Optional[dict[str, Any]] = None

    def run_preflight(self) -> dict[str, Any]:
        if self.preflight is None:
            self.preflight_result = {
                "schema": "dreal001.p2a_v2.preflight_result.v1",
                "overall": "PREFLIGHT_NOT_CONFIGURED",
                "main_batch_may_start": False,
                "physical_call_count": 0, "counted_in_e1_e6": False,
            }
            return self.preflight_result
        if self.accept_preflight_numeric and not self.preflight.accept_numeric:
            self.preflight.accept_numeric = True
        self.preflight_result = self.preflight.run()
        return self.preflight_result

    def run_arm(self, arm_id: str, proposal_fn: Callable[[str, int, int], Sequence[float]],
                budget_designs: int = DESIGN_EVALS_PER_ARM,
                initial_designs: Optional[Sequence[Sequence[float]]] = None,
                on_evaluation: Optional[Callable[[str, Any], None]] = None,
                stop_check: Optional[Callable[[str, Any], Optional[str]]] = None) -> ArmRunResult:
        result = ArmRunResult(arm_id=arm_id, status="COMPLETED")
        initial = list(initial_designs or [])
        for design_index in range(1, budget_designs + 1):
            replacement_attempt = 0
            while True:
                if replacement_attempt == 0 and design_index <= len(initial):
                    x12 = initial[design_index - 1]
                else:
                    x12 = proposal_fn(arm_id, design_index, replacement_attempt)
                evaluation = self.runner.run_one(x12, design_index)
                if on_evaluation is not None:
                    on_evaluation(arm_id, evaluation)
                if stop_check is not None:
                    stop_reason = stop_check(arm_id, evaluation)
                    if stop_reason:
                        result.evaluations.append(evaluation)
                        result.starts += evaluation.starts
                        if evaluation.status != "SOLVED_VALID":
                            result.invalid_designs += 1
                        result.status = stop_reason
                        return result
                if evaluation.status == "DESIGN_VOID":
                    result.void_designs += 1
                    dh = design_hash(x12)
                    if dh not in self.voided_designs:
                        self.voided_designs.add(dh)
                        if not self.reserve.consume():
                            result.status = "NOT_VALIDATED_RESERVE_EXHAUSTED"
                            return result
                        result.reserve_groups_used += 1
                    replacement_attempt += 1
                    if replacement_attempt > RESERVE_GROUPS:
                        result.status = "NOT_VALIDATED_REPLACEMENT_LIMIT"
                        return result
                    continue
                if evaluation.status == INVALID_EVALUATION_STATUS:
                    result.evaluations.append(evaluation)
                    result.invalid_designs += 1
                    result.starts += evaluation.starts
                    break
                if evaluation.status != "SOLVED_VALID":
                    result.status = "STOP_" + evaluation.status
                    result.starts += evaluation.starts
                    result.evaluations.append(evaluation)
                    return result
                result.evaluations.append(evaluation)
                result.valid_designs += 1
                result.starts += evaluation.starts
                break
        return result

    def run_batch(self, proposal_fns: Mapping[str, Callable[[str, int, int], Sequence[float]]],
                  *, budget_designs: int = DESIGN_EVALS_PER_ARM,
                  initial_designs: Optional[Sequence[Sequence[float]]] = None,
                  on_arm_start: Optional[Callable[[str], None]] = None,
                  on_evaluation: Optional[Callable[[str, Any], None]] = None) -> dict[str, Any]:
        pre = self.run_preflight()
        if not pre.get("main_batch_may_start"):
            return {
                "schema": "dreal001.p2a_v2_batch_summary.v1",
                "batch_id": BATCH_ID, "run_id": RUN_ID,
                "status": "STOP_PREFLIGHT_" + str(pre.get("overall")),
                "preflight": pre, "arms": {}, "total_starts": 0,
                "reserve_groups_used": 0, "physical_call_count": 0,
            }
        arms: dict[str, Any] = {}
        for arm in ARMS:
            if on_arm_start is not None:
                on_arm_start(arm)
            arm_result = self.run_arm(arm, proposal_fns[arm], budget_designs=budget_designs,
                                      initial_designs=initial_designs,
                                      on_evaluation=on_evaluation)
            arms[arm] = {
                "status": arm_result.status, "valid_designs": arm_result.valid_designs,
                "void_designs": arm_result.void_designs, "starts": arm_result.starts,
                "best_primary": arm_result.best_primary,
                "reserve_groups_used": arm_result.reserve_groups_used,
                "evaluations": [asdict(e) for e in arm_result.evaluations],
            }
            if arm_result.status != "COMPLETED":
                break
        total_starts = sum(a["starts"] for a in arms.values())
        return {
            "schema": "dreal001.p2a_v2_batch_summary.v1",
            "batch_id": BATCH_ID, "run_id": RUN_ID,
            "status": "COMPLETED" if len(arms) == len(ARMS) else "STOPPED",
            "preflight": pre, "arms": arms, "total_starts": total_starts,
            "reserve_groups_used": self.reserve.groups_used,
            "voided_designs": sorted(self.voided_designs),
            "append_log_sha256": self.runner.store.sha256_of_log(),
            "append_log_head_sha256": self.runner.store.prev_sha,
            "physical_call_count": 0,
        }
