"""Fail-closed real-label admission from locally hashed VSPAERO artifacts.

This module verifies that raw bytes exist at a declared root, match declared
SHA256/size, bind to the task/design/geometry, and (for successful runs) contain
an actual polar row at the requested lift with D_i_N = q * Sref * CDi. It also
binds an independent-audit record by hash and requires the audit to name the
same run/task/design/artifact identity.

It does NOT authenticate who produced the bytes or who wrote the audit record.
No signature, key or remote attestation exists yet. Callers must still obtain
the real R2 authorization and A5 review before treating a certificate as a
scientific label. Certificates are minted only by admit_real_manifest(); deleting
the MetaDataset guard or hand-writing an Observation cannot mint one.

Offline tests use synthetic bytes and must label them as such.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math
import os
import re
from pathlib import PurePosixPath

from .raw_verification import ArtifactBinding, verify_artifact_bundle
from .task_spec import ContractError, TaskSpec, canonical_sha

SCHEMA = "dreal001.real_admission_manifest.v1"
AUDIT_SCHEMA = "dreal001.independent_audit_record.v1"
EVIDENCE_SCOPE = "LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED"
FILE_KINDS = ("audit", "deck", "history", "mesh", "polar")
REQUIRED_FILE_KINDS = frozenset(FILE_KINDS)
_ARTIFACT_KINDS = frozenset(("deck", "history", "mesh", "polar"))
_SHA256 = re.compile(r"[0-9a-f]{64}")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_ISSUER = object()


def _require_text(value, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ContractError(name + MUST_BE_NONEMPTY)
    return value


MUST_BE_NONEMPTY = " must be a nonempty trimmed string"


def _require_sha256(value, name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ContractError("invalid SHA256: " + name)
    return value


def _parse_utc(value, name: str) -> None:
    _require_text(value, name)
    if not _UTC.fullmatch(value):
        raise ContractError(name + " must be UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ContractError(name + " is not a valid UTC timestamp") from exc


def _normalized_design(design) -> tuple[float, ...]:
    vector = tuple(float(value) for value in design)
    if len(vector) != 12 or not all(math.isfinite(value) for value in vector):
        raise ContractError("design must have 12 finite coordinates")
    # Canonicalise signed zero; equality cannot be evaded by -0.0.
    return tuple(0.0 if value == 0 else value for value in vector)


def _design_sha256(design) -> str:
    return canonical_sha(list(_normalized_design(design)))


@dataclass(frozen=True)
class RawFile:
    """A declared raw artifact. Paths are relative POSIX paths under raw_root."""
    kind: str
    path: str
    sha256: str
    bytes: int

    def __post_init__(self) -> None:
        if self.kind not in REQUIRED_FILE_KINDS:
            raise ContractError("unrecognized raw file kind: " + str(self.kind))
        _require_text(self.path, "raw file path")
        if "\\" in self.path or ":" in self.path or "\x00" in self.path:
            raise ContractError("raw file path must not use Windows separators, drive letters or NUL")
        parsed = PurePosixPath(self.path)
        if parsed.is_absolute() or any(part in ("", ".", "..") for part in parsed.parts):
            raise ContractError("raw file path must stay relative and normalized")
        _require_sha256(self.sha256, "raw file SHA256")
        if type(self.bytes) is not int or self.bytes <= 0:
            raise ContractError("raw file bytes must be a positive integer")


def artifact_sha256(files) -> str:
    """Location-independent identity of the four payload artifacts (audit excluded)."""
    entries = tuple(files)
    if any(not isinstance(item, RawFile) for item in entries):
        raise ContractError("artifact identity requires RawFile entries")
    artifacts = sorted((item for item in entries if item.kind != "audit"),
                       key=lambda item: (item.kind, item.path))
    if {item.kind for item in artifacts} != _ARTIFACT_KINDS:
        raise ContractError("artifact identity requires mesh, deck, polar and history exactly once")
    return canonical_sha([{"kind": item.kind, "sha256": item.sha256, "bytes": item.bytes}
                          for item in artifacts])


@dataclass(frozen=True)
class RealAdmissionManifest:
    """Declared provenance for one real solver case; not itself an admission."""
    admission_id: str
    run_id: str
    task_id: str
    design_id: str
    design: tuple[float, ...]
    geometry_sha256: str
    evaluator_id: str
    solver_returncode: int
    solver_started_utc: str
    outcome: str
    partition: str
    files: tuple[RawFile, ...]
    binding: ArtifactBinding
    independent_audit_ref: str
    schema: str = SCHEMA

    def __post_init__(self) -> None:
        if self.schema != SCHEMA:
            raise ContractError("unsupported real admission manifest schema")
        for name in ("admission_id", "run_id", "task_id", "evaluator_id",
                     "independent_audit_ref"):
            _require_text(getattr(self, name), name)
        _require_sha256(self.geometry_sha256, "geometry_sha256")
        vector = _normalized_design(self.design)
        object.__setattr__(self, "design", vector)
        if self.design_id != canonical_sha(list(vector)):
            raise ContractError("design_id does not match canonical design identity")
        _parse_utc(self.solver_started_utc, "solver_started_utc")
        if self.outcome not in {"success", "failed"}:
            raise ContractError("outcome must be success or failed")
        if self.partition not in {"support", "query"}:
            raise ContractError("invalid support/query partition")
        if type(self.solver_returncode) is not int:
            raise ContractError("solver_returncode must be an integer")
        if self.outcome == "success" and self.solver_returncode != 0:
            raise ContractError("successful outcome requires solver_returncode 0")
        if self.outcome == "failed" and self.solver_returncode == 0:
            raise ContractError("failed outcome requires a nonzero solver_returncode")
        if not isinstance(self.binding, ArtifactBinding):
            raise ContractError("real admission requires ArtifactBinding")
        files = tuple(self.files)
        if (len(files) != len(REQUIRED_FILE_KINDS) or any(not isinstance(item, RawFile) for item in files)
                or {item.kind for item in files} != REQUIRED_FILE_KINDS):
            raise ContractError("real admission requires exactly five distinct raw file kinds")
        if len({item.path for item in files}) != len(files):
            raise ContractError("raw file paths must be unique")
        by_kind = {item.kind: item for item in files}
        for kind in ("mesh", "deck", "polar"):
            if getattr(self.binding, kind + "_sha256") != by_kind[kind].sha256:
                raise ContractError("manifest binding does not match raw file: " + kind)
        if self.binding.design_sha256 != self.design_id:
            raise ContractError("manifest binding does not match design_id")
        if self.binding.geometry_contract_sha256 != self.geometry_sha256:
            raise ContractError("manifest binding does not match geometry_sha256")
        object.__setattr__(self, "files", files)

    @property
    def artifact_sha256(self) -> str:
        return artifact_sha256(self.files)

    def file(self, kind: str) -> RawFile:
        for item in self.files:
            if item.kind == kind:
                return item
        raise ContractError("raw file kind missing: " + kind)


@dataclass(frozen=True)
class AdmissionCertificate:
    """Minted only after local byte verification; provenance is still unauthenticated."""
    admission_id: str
    task_id: str
    design: tuple[float, ...]
    partition: str
    status: str
    di_n: float | None
    q_pa: float | None
    sref_m2: float | None
    cdi: float | None
    cl: float | None
    alpha_deg: float | None
    raw_sha256: str
    artifact_sha256: str
    geometry_sha256: str
    evaluator_id: str
    independent_audit_ref: str
    evidence_scope: str
    _issuer: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issuer is not _ISSUER:
            raise ContractError("admission certificate must be issued by admit_real_manifest")
        for name in ("admission_id", "task_id", "evaluator_id", "independent_audit_ref"):
            _require_text(getattr(self, name), name)
        object.__setattr__(self, "design", _normalized_design(self.design))
        if self.partition not in {"support", "query"}:
            raise ContractError("invalid support/query partition")
        if self.status not in {"ok", "failed"}:
            raise ContractError("unrecognized admission status")
        _require_sha256(self.raw_sha256, "raw_sha256")
        _require_sha256(self.artifact_sha256, "artifact_sha256")
        _require_sha256(self.geometry_sha256, "geometry_sha256")
        if self.evidence_scope != EVIDENCE_SCOPE:
            raise ContractError("unrecognized admission evidence scope")
        if self.status == "ok":
            if (self.di_n is None or not math.isfinite(self.di_n) or self.di_n < 0
                    or self.cdi is None or not math.isfinite(self.cdi) or self.cdi < 0
                    or self.cl is None or not math.isfinite(self.cl)
                    or self.alpha_deg is None or not math.isfinite(self.alpha_deg)):
                raise ContractError("successful admission requires finite coefficients")
            expected_di = self.q_pa * self.sref_m2 * self.cdi
            if not math.isclose(self.di_n, expected_di, rel_tol=1e-9, abs_tol=1e-12):
                raise ContractError("admission D_i_N does not equal q*Sref*CDi")
        else:
            if self.di_n is not None or self.cdi is not None or self.cl is not None or self.alpha_deg is not None:
                raise ContractError("failed admission must not carry coefficient labels")
        for name in ("q_pa", "sref_m2"):
            value = getattr(self, name)
            if value is None or not math.isfinite(value) or value <= 0:
                raise ContractError("admission requires a positive finite " + name)

    @property
    def observation_id(self) -> str:
        return self.admission_id

    @property
    def design_sha256(self) -> str:
        return canonical_sha(list(self.design))


def _resolve_root(raw_root) -> str:
    try:
        root = os.path.realpath(os.fspath(raw_root))
    except TypeError as exc:
        raise ContractError("raw_root must be a filesystem path") from exc
    if not os.path.isdir(root):
        raise ContractError("raw_root must be an existing directory")
    return root


def _read_bound_file(root: str, spec: RawFile) -> bytes:
    parsed = PurePosixPath(spec.path)
    candidate = os.path.join(root, *parsed.parts)
    real = os.path.realpath(candidate)
    if os.path.normcase(os.path.commonpath([os.path.normcase(root), os.path.normcase(real)])) != os.path.normcase(root):
        raise ContractError("raw file path escapes raw_root: " + spec.kind)
    if not os.path.isfile(real):
        raise ContractError("raw file missing: " + spec.kind)
    if os.path.getsize(real) != spec.bytes:
        raise ContractError("raw file size mismatch: " + spec.kind)
    with open(real, "rb") as handle:
        payload = handle.read()
    if len(payload) != spec.bytes or hashlib.sha256(payload).hexdigest() != spec.sha256:
        raise ContractError("raw file SHA256 mismatch: " + spec.kind)
    return payload


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate audit record field: " + key)
        result[key] = value
    return result


def _parse_audit_record(raw: bytes, manifest: RealAdmissionManifest,
                        expected_audit_ref: str) -> dict:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("audit record must decode as UTF-8") from exc
    try:
        record = json.loads(text, object_pairs_hook=_unique_pairs)
    except json.JSONDecodeError as exc:
        raise ContractError("audit record is not valid JSON") from exc
    if not isinstance(record, dict):
        raise ContractError("audit record must be a JSON object")
    required = {"schema", "audit_id", "run_id", "task_id", "design_id", "geometry_sha256",
                "artifact_sha256", "reviewer", "reviewer_role", "verdict", "created_utc"}
    if not required <= set(record):
        raise ContractError("audit record is missing required fields")
    if set(record) - required - {"notes"}:
        raise ContractError("audit record contains unrecognized fields")
    if record["schema"] != AUDIT_SCHEMA:
        raise ContractError("unsupported independent audit record schema")
    _require_text(record["audit_id"], "audit_id")
    _require_text(record["reviewer"], "reviewer")
    _require_text(record["reviewer_role"], "reviewer_role")
    _parse_utc(record["created_utc"], "created_utc")
    expected = {
        "audit_id": manifest.independent_audit_ref,
        "run_id": manifest.run_id,
        "task_id": manifest.task_id,
        "design_id": manifest.design_id,
        "geometry_sha256": manifest.geometry_sha256,
        "artifact_sha256": manifest.artifact_sha256,
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise ContractError("audit record does not match manifest: " + key)
    if manifest.independent_audit_ref != expected_audit_ref:
        raise ContractError("unexpected independent audit reference")
    required_verdict = "ADMIT_REAL_LABEL" if manifest.outcome == "success" else "ADMIT_FAILED_RUN"
    if record["verdict"] != required_verdict:
        raise ContractError("audit record verdict does not admit this outcome")
    return record


def admit_real_manifest(*, manifest: RealAdmissionManifest, raw_root, task: TaskSpec,
                        design, expected_evaluator_id: str,
                        expected_audit_ref: str) -> AdmissionCertificate:
    """Verify declared raw bytes and return an admission certificate or raise.

    expected_evaluator_id and expected_audit_ref come from the future R2
    authorization/review record, not from the manifest itself. Matching them only
    proves the caller expected the same strings; it does not authenticate either.
    """
    if not isinstance(manifest, RealAdmissionManifest):
        raise ContractError("RealAdmissionManifest required")
    if not isinstance(task, TaskSpec):
        raise ContractError("TaskSpec required")
    _require_text(expected_evaluator_id, "expected_evaluator_id")
    _require_text(expected_audit_ref, "expected_audit_ref")
    vector = _normalized_design(design)
    if canonical_sha(list(vector)) != manifest.design_id:
        raise ContractError("admission design does not match manifest")
    if task.task_id != manifest.task_id:
        raise ContractError("manifest task_id does not match task")
    if task.geometry_contract_sha256 != manifest.geometry_sha256:
        raise ContractError("manifest geometry does not match task contract")
    if task.physics_sha256 != manifest.binding.task_physics_sha256:
        raise ContractError("manifest binding does not match task physics")
    if manifest.evaluator_id != expected_evaluator_id:
        raise ContractError("unexpected evaluator_id")
    if manifest.independent_audit_ref != expected_audit_ref:
        raise ContractError("unexpected independent audit reference")
    root = _resolve_root(raw_root)
    payloads = {spec.kind: _read_bound_file(root, spec) for spec in manifest.files}
    _parse_audit_record(payloads["audit"], manifest, expected_audit_ref)
    q_pa = 0.5 * manifest.binding.rho_kg_m3 * manifest.binding.vinf_m_s ** 2
    if not math.isclose(q_pa, task.dynamic_pressure_pa, rel_tol=1e-9, abs_tol=1e-12):
        raise ContractError("manifest flow conditions do not match task dynamic pressure")
    if manifest.outcome == "success":
        candidate = verify_artifact_bundle(task=task, design=vector, binding=manifest.binding,
                                           mesh=payloads["mesh"], deck=payloads["deck"],
                                           polar=payloads["polar"])
        if candidate.real_admission:
            raise ContractError("raw verification unexpectedly minted a real admission")
        status, di_n, cdi, cl, alpha = ("ok", candidate.di_n, candidate.cdi,
                                        candidate.cl, candidate.alpha_deg)
    else:
        # A failed solve cannot mint a label; only its bound bytes/conditions are recorded.
        status, di_n, cdi, cl, alpha = ("failed", None, None, None, None)
    return AdmissionCertificate(
        admission_id=manifest.admission_id,
        task_id=manifest.task_id,
        design=vector,
        partition=manifest.partition,
        status=status,
        di_n=di_n,
        q_pa=q_pa,
        sref_m2=manifest.binding.sref_m2,
        cdi=cdi,
        cl=cl,
        alpha_deg=alpha,
        raw_sha256=manifest.file("polar").sha256,
        artifact_sha256=manifest.artifact_sha256,
        geometry_sha256=manifest.geometry_sha256,
        evaluator_id=manifest.evaluator_id,
        independent_audit_ref=manifest.independent_audit_ref,
        evidence_scope=EVIDENCE_SCOPE,
        _issuer=_ISSUER,
    )
