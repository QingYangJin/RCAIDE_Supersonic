"""D-NEXT-001 evaluator v1.2: two frozen families, mock-only software closure.

This module implements the A5-reviewed design in
docs/planning/dnext001_evaluator_v1_2_design.md (commit b8b30e4).

Contract summary (all fail-closed; no physical solver in this module's tested path):
  * one (design, family) cell = one solver start; mock starts are counted as
    simulated starts but physical_solver_starts / physical_call_count stay 0;
  * the frozen .vspgeom/.vkey bytes come from family_pair_manifest.json;
    PRE and POST SHA verification are mandatory (A5 Q3);
  * .vkey missing is fail-closed: PRE -> 0 starts, POST -> 1 charged start unusable;
  * evaluator emits per-family records only; the two-family equal-weight mean and
    the missing-pair policy belong to A2 and must be pre-registered (A5 Q6);
  * approval must carry family_coverage + pair_manifest_sha256 (A5 Q2);
  * physical_validation_status is always NOT_VALIDATED and fuel_burn_kg is null.

The real-solver path (mock=False) refuses to run unless spawn + allow_physical_starts
+ an approved approval are all supplied; the real launch itself is intentionally not
implemented here (it reuses the v1.1 ledger machinery in a follow-up step, and this
stage is mock-only as approved by A5).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .design_identity import canonical_x12_payload, design_hash as compute_design_hash

SCHEMA = "dreal001.aero_eval.v1_2"
MANIFEST_SCHEMA = "dreal001.p2afam.family_pair_manifest.v1"
EVALUATOR_ID = "a1-two-family-evaluator-v1.2"
PHYSICAL_VALIDATION_STATUS = "NOT_VALIDATED"
BACKEND_MOCK = "MOCK"
BACKEND_REAL = "REAL_VSPAERO"

MODE_STATIC = "STATIC_MANIFEST"
MODE_RUNTIME = "RUNTIME_APPEND_ONLY"
MODE_REPLAY = "REPLAY_B2"
MODES = (MODE_STATIC, MODE_RUNTIME, MODE_REPLAY)
FREEZE_RULE = "K10_DISCOVERY_UNION_2_TARGET_40_PER_FAMILY"

STATUS_SOLVED = "SOLVED_VALID"
STATUS_SOLVED_UNVERIFIED = "SOLVED_UNVERIFIED"
STATUS_SOLVER_FAILED = "SOLVER_FAILED"
STATUS_GEOMETRY_INVALID = "GEOMETRY_INVALID"
STATUS_LIFT_MATCH_FAILED = "LIFT_MATCH_FAILED"
STATUS_NOT_RUN = "NOT_RUN"
STATUS_DISCARDED = "DISCARDED_DESIGN"
STATUS_FAMILY_VOID = "FAMILY_UNREACHABLE_DESIGN_VOID"

ERR_MANIFEST = "MANIFEST_BINDING_MISMATCH"
ERR_MANIFEST_SCHEMA = "MANIFEST_SCHEMA_MISMATCH"
ERR_APPROVAL = "APPROVAL_MISSING_OR_NOT_APPROVED"
ERR_APPROVAL_COVERAGE = "APPROVAL_FAMILY_COVERAGE_MISSING"
ERR_BATCH = "APPROVAL_BATCH_MISMATCH"
ERR_FAMILY_SELECTOR = "FAMILY_SELECTOR_INVALID"
ERR_DESIGN_NOT_IN_MANIFEST = "DESIGN_NOT_IN_MANIFEST"
ERR_DESIGN_VOID = "FAMILY_UNREACHABLE_DESIGN_VOID"
ERR_X12_LENGTH = "X12_LENGTH"
ERR_X12_NONFINITE = "X12_NONFINITE"
ERR_X12_UNIT_BOX = "UNIT_BOX_VECTOR_NOT_ACCEPTED"
ERR_X12_MANIFEST = "X12_MANIFEST_MISMATCH"
ERR_FROZEN_PRE = "FROZEN_GEOMETRY_SHA_MISMATCH_PRE"
ERR_FROZEN_POST = "FROZEN_GEOMETRY_SHA_MISMATCH_POST"
ERR_VKEY_MISSING = "VKEY_MISSING"
ERR_BUDGET = "SOLVER_BUDGET_EXHAUSTED"
ERR_REAL_NOT_AUTHORIZED = "REAL_START_NOT_AUTHORIZED"
ERR_TIMEOUT = "SOLVER_TIMEOUT"
ERR_MOCK_SPAWN = "MOCK_REAL_SPAWN_CONFUSION"
ERR_DUPLICATE_CELL = "DUPLICATE_DESIGN_FAMILY_CELL"
ERR_CASE_ID = "CASE_ID_UNSAFE"
ERR_MODE = "EVALUATOR_MODE_INVALID"
ERR_RUNTIME_LOG = "RUNTIME_APPEND_ONLY_LOG_MISSING_OR_INVALID"
ERR_CHAIN = "RUNTIME_CHAIN_INVALID"
ERR_RUNTIME_RECORD = "RUNTIME_DESIGN_RECORD_MISSING"
ERR_RUNTIME_VOID = "RUNTIME_DESIGN_NOT_PAIR_READY"
ERR_RUNTIME_SHA = "RUNTIME_RECORD_SHA_MISMATCH"
ERR_RUNTIME_ROLE = "RUNTIME_ROLE_MAP_INVALID"
ERR_LEDGER = "LEDGER_MULTIPLE_WRITERS"
ERR_REPLAY_INPUT = "REPLAY_INPUT_INCOMPLETE"
ERR_REPLAY_POLAR = "REPLAY_POLAR_SHA_MISMATCH"
ERR_REPLAY_BUNDLE = "REPLAY_BUNDLE_MISMATCH"
ERR_CODE_SHA = "CODE_IDENTITY_SHA_MISMATCH"


class V12ConfigurationError(RuntimeError):
    """Construction-time contract violation; raised before any start."""


class RealStartNotAuthorized(V12ConfigurationError):
    """A real vspaero start was requested without approval/spawn/allow flag."""


_CASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    """Canonical JSON digest used for approval/manifest binding (and by tests)."""
    return sha256_bytes(json.dumps(
        dict(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def load_family_pair_manifest(path: Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != MANIFEST_SCHEMA:
        raise V12ConfigurationError(ERR_MANIFEST_SCHEMA + ": " + str(data.get("schema")))
    if int(data.get("physical_call_count", -1)) != 0:
        raise V12ConfigurationError(ERR_MANIFEST + ": manifest physical_call_count must be 0")
    return data


def _manifest_index(manifest: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    records = manifest.get("records")
    if not isinstance(records, list):
        raise V12ConfigurationError(ERR_MANIFEST + ": manifest.records must be a list")
    index: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        dh = str(rec.get("design_hash", ""))
        if len(dh) != 16 or dh in index:
            raise V12ConfigurationError(ERR_MANIFEST + ": bad/duplicate design_hash " + dh)
        index[dh] = rec
    return index


def _approval_design_coverage(approval: Mapping[str, Any], design_hash: str) -> Optional[Mapping[str, Any]]:
    coverage = approval.get("family_coverage") or {}
    for entry in coverage.get("designs", []) or []:
        if str(entry.get("design_hash")) == design_hash:
            return entry
    return None


def _family_role_map(approval_entry: Mapping[str, Any], families: Mapping[str, Any]) -> Dict[str, str]:
    """Map role -> family label. Prefer explicit approval mapping; else lexicographic."""
    explicit = approval_entry.get("family_labels") or {}
    labels = list(families.keys())
    roles: Dict[str, str] = {}
    for role in ("f1", "f2"):
        label = explicit.get(role)
        if label is None:
            continue
        if label not in families:
            raise V12ConfigurationError(ERR_APPROVAL_COVERAGE + ": unknown family label " + str(label))
        roles[role] = str(label)
    if len(roles) == 2:
        return roles
    # E12-04: no silent lexicographic fallback; the approval must bind both roles
    # explicitly (or carry a policy-level role_order).
    order = list((approval_entry.get("role_order") or []) if isinstance(approval_entry, Mapping) else [])
    if len(order) == 2 and set(order) == set(labels):
        return {"f1": str(order[0]), "f2": str(order[1])}
    raise V12ConfigurationError(ERR_APPROVAL_COVERAGE + ": explicit f1/f2 family_labels required")


def _validate_approval_entry(entry: Mapping[str, Any], families: Mapping[str, Any], design_hash_: str) -> None:
    """E12-04: any family/frozen binding carried by the approval must match the manifest."""
    bound = entry.get("families")
    if isinstance(bound, Mapping):
        for label in bound:
            if label not in families:
                raise V12ConfigurationError(ERR_APPROVAL_COVERAGE + ": approval family not in manifest " + str(label))
        for label, item in bound.items():
            frozen_sha = (item or {}).get("frozen_vspgeom_sha256") if isinstance(item, Mapping) else None
            manifest_sha = (families[label].get("frozen") or {}).get("frozen_vspgeom_sha256")
            if frozen_sha and frozen_sha != manifest_sha:
                raise V12ConfigurationError(ERR_APPROVAL_COVERAGE + ": approval frozen SHA mismatch " + str(label))
    direct = entry.get("frozen_vspgeom_sha256")
    if isinstance(direct, Mapping):
        for label, sha in direct.items():
            if label in families and sha != (families[label].get("frozen") or {}).get("frozen_vspgeom_sha256"):
                raise V12ConfigurationError(ERR_APPROVAL_COVERAGE + ": approval frozen SHA mismatch " + str(label))


def _label_nodes_elements(label: str) -> List[int]:
    try:
        a, b = str(label).lower().split("x")
        return [int(a), int(b)]
    except Exception as exc:  # pragma: no cover - defensive
        raise V12ConfigurationError("bad family label: " + str(label)) from exc


def _base_record(case_id: str, family: str, mock: bool) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "evaluator_id": EVALUATOR_ID,
        "backend": BACKEND_MOCK if mock else BACKEND_REAL,
        "source_kind": BACKEND_MOCK if mock else BACKEND_REAL,
        "physical_validation_status": PHYSICAL_VALIDATION_STATUS,
        "status": STATUS_NOT_RUN,
        "record_status": STATUS_NOT_RUN,
        "case_id": str(case_id),
        "family_role": family,
        "design": {"x12": [], "design_hash": ""},
        "geometry_bundle": {},
        "sha_verification": {"pre": "NOT_RUN", "post": "NOT_RUN"},
        "solver": {
            "launch_kind": "MOCK_SIMULATED" if mock else "REAL",
            "simulated_solver_starts": 0,
            "physical_solver_starts": 0,
            "attempt_ids": [],
            "command": [],
        },
        "results": {"alpha_deg": [], "cltot": [], "cdi": [], "cdo": [], "cdtot": [], "cmy": []},
        "lift": {},
        "attempt_ids": [],
        "raw_artifacts": [],
        "errors": [],
        "usable_for_objective": False,
        "physical_call_count": 0,
        "objective": {"name": "D_i_N", "value": None, "unit": "N"},
        "fuel_burn_kg": None,
        "mock": bool(mock),
    }


def _error(code: str, detail: str, no_start: bool = True) -> Dict[str, Any]:
    return {"code": code, "detail": detail, "no_solver_start": bool(no_start)}


class TwoFamilyEvaluator:
    """Mock-first v1.2 evaluator over a frozen two-family manifest."""

    def __init__(self, manifest: Mapping[str, Any], approval: Optional[Mapping[str, Any]], *,
                 batch_id: str, max_starts: int, run_dir: Path,
                 manifest_source: Optional[Path] = None,
                 spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
                 real_spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
                 allow_physical_starts: bool = False, mock: bool = True,
                 replay_physical: bool = False,
                 replay_bundle_manifest: Optional[Path] = None,
                 sha_verify_pre: bool = True, sha_verify_post: bool = True,
                 mode: str = MODE_STATIC,
                 append_only_log: Optional[Path] = None,
                 policy_doc_sha256: str = "", builder_code_sha256: str = "",
                 evaluator_code_sha256: str = "",
                 ledger_path: Optional[Path] = None,
                 clock: Callable[[], float] = time.time) -> None:
        nonphysical_replay = (mode == MODE_REPLAY and not replay_physical)
        if not mock and spawn is not None and not nonphysical_replay:
            # E12-02: the offline mock callback is never a physical launcher.
            raise V12ConfigurationError(ERR_MOCK_SPAWN + ": physical mode requires real_spawn, not spawn")
        if mode == MODE_REPLAY:
            if replay_physical:
                if real_spawn is None or not allow_physical_starts:
                    raise RealStartNotAuthorized(ERR_REAL_NOT_AUTHORIZED)
                if spawn is not None:
                    raise V12ConfigurationError(ERR_MOCK_SPAWN + ": physical replay rejects the offline spawn")
            else:
                # A5 2026-11-11: a non-physical replay must never hold a real launcher;
                # a real vspaero start that is not charged would be a billing bypass.
                if real_spawn is not None:
                    raise V12ConfigurationError(ERR_MOCK_SPAWN + ": non-physical replay rejects real_spawn")
                if mock:
                    raise V12ConfigurationError(ERR_REPLAY_INPUT + ": replay requires mock=False")
                if spawn is None:
                    raise V12ConfigurationError(ERR_REPLAY_INPUT + ": self-check replay requires an offline spawn")
        elif not mock and (real_spawn is None or not allow_physical_starts):
            raise RealStartNotAuthorized(ERR_REAL_NOT_AUTHORIZED)
        if not (sha_verify_pre and sha_verify_post):
            # E12-01: SHA verification is mandatory; the old opt-out is deleted.
            raise V12ConfigurationError("SHA_VERIFY_BYPASS_NOT_ALLOWED")
        if mock and real_spawn is not None:
            # E12-02: a mock evaluator can never be wired to a real launcher.
            raise V12ConfigurationError(ERR_MOCK_SPAWN + ": mock mode rejects real_spawn")
        if mode not in MODES:
            raise V12ConfigurationError(ERR_MODE + ": " + str(mode))
        if replay_physical and mode != MODE_REPLAY:
            raise V12ConfigurationError(ERR_MODE + ": replay_physical requires REPLAY_B2")
        if replay_physical and mock:
            raise V12ConfigurationError(ERR_REPLAY_INPUT + ": replay_physical requires mock=False")
        if replay_physical and (real_spawn is None or not allow_physical_starts):
            raise RealStartNotAuthorized(ERR_REAL_NOT_AUTHORIZED)
        self.mode = str(mode)
        self.replay_physical = bool(replay_physical)
        self.replay_bundle_manifest = Path(replay_bundle_manifest) if replay_bundle_manifest else None
        self.evaluator_file_sha256 = sha256_file(Path(__file__).resolve())
        self.replay_bundle: Dict[str, Any] = {}
        self.append_only_log = Path(append_only_log) if append_only_log else None
        if self.mode == MODE_RUNTIME and self.append_only_log is None:
            raise V12ConfigurationError(ERR_RUNTIME_LOG)
        self.policy_doc_sha256 = str(policy_doc_sha256)
        self.builder_code_sha256 = str(builder_code_sha256)
        self.evaluator_code_sha256 = str(evaluator_code_sha256)
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self._ledger_handle = None
        self._lock_path: Optional[Path] = None
        # E12-03/A5 2026-11-11: the source file is the authority.  A caller-supplied
        # dict that differs from the file must be rejected, never silently trusted.
        self.manifest = dict(manifest)
        if manifest_source is None:
            raise V12ConfigurationError(ERR_MANIFEST + ": manifest_source is required")
        self.manifest_source = Path(manifest_source)
        try:
            source_payload = json.loads(self.manifest_source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise V12ConfigurationError(ERR_MANIFEST + ": unreadable manifest_source: " + repr(exc)) from exc
        if canonical_json(source_payload) != canonical_json(self.manifest):
            raise V12ConfigurationError(ERR_MANIFEST + ": MANIFEST_SOURCE_DICT_MISMATCH")
        self.manifest = dict(source_payload)
        self._manifest_bytes = canonical_json(self.manifest).encode("utf-8")
        self.manifest_sha256 = sha256_file(self.manifest_source)
        self.approval = dict(approval or {})
        self.batch_id = str(batch_id)
        self.max_starts = int(max_starts)
        self.run_dir = Path(run_dir)
        self.spawn = spawn
        self.real_spawn = real_spawn
        self.allow_physical_starts = bool(allow_physical_starts)
        self.mock = bool(mock)
        self.sha_verify_pre = True
        self.sha_verify_post = True
        self._seen_cells: set = set()
        self.clock = clock
        self.starts_used = 0
        self.simulated_starts_used = 0
        self.calls = 0
        self.refusals: List[Dict[str, Any]] = []
        self._index = _manifest_index(self.manifest)
        self._stop_report_path: Optional[Path] = None
        try:
            self._verify_approval()
            self._verify_code_identity()
            self._verify_replay_binding()
            if self.mode == MODE_RUNTIME:
                # Fail-closed on a broken hash chain before anything else is trusted.
                self._runtime_records(raise_on_error=True)
                self._verify_runtime_approval()
        except V12ConfigurationError as exc:
            # A5/Lead m07580 item 5: a binding mismatch must leave an auditable
            # stop_report next to the run, never fail silently.
            self._write_stop_report(exc)
            raise
        self._open_ledger()

    def _write_stop_report(self, exc: BaseException) -> None:
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            code = str(exc).split(":", 1)[0].strip()
            payload = {
                "schema": "dreal001.evaluator.stop_report.v1",
                "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())),
                "stage": "CONSTRUCTOR_BINDING",
                "evaluator_mode": str(getattr(self, "mode", "")),
                "batch_id": str(getattr(self, "batch_id", "")),
                "code": code,
                "detail": str(exc)[:2000],
                "manifest_source": str(getattr(self, "manifest_source", "")),
                "approval_batch_id": str((self.approval or {}).get("batch_id", "")),
                "physical_call_count": 0,
                "solver_started": False,
            }
            path = self.run_dir / "stop_report.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
            self._stop_report_path = path
        except OSError:
            self._stop_report_path = None

    # ------------------------------------------------------------------ setup
    def _verify_approval(self) -> None:
        ap = self.approval
        if ap.get("approved") is not True:
            raise V12ConfigurationError(ERR_APPROVAL)
        if str(ap.get("batch_id")) != self.batch_id:
            raise V12ConfigurationError(ERR_BATCH)
        approved_max = ap.get("max_starts")
        if approved_max is not None and self.max_starts > int(approved_max):
            raise V12ConfigurationError(ERR_APPROVAL + ": max_starts exceeds approval")
        if int(ap.get("max_starts", 0) or 0) <= 0:
            raise V12ConfigurationError(ERR_APPROVAL)
        if not ap.get("pair_manifest_sha256"):
            raise V12ConfigurationError(ERR_APPROVAL_COVERAGE + ": pair_manifest_sha256 missing")
        if str(ap.get("pair_manifest_sha256")) != self.manifest_sha256:
            raise V12ConfigurationError(ERR_MANIFEST + ": approval pair_manifest_sha256 != manifest")
        coverage = ap.get("family_coverage")
        if not isinstance(coverage, Mapping) or not coverage.get("designs"):
            raise V12ConfigurationError(ERR_APPROVAL_COVERAGE)
        if str(coverage.get("pair_manifest_sha256")) != self.manifest_sha256:
            raise V12ConfigurationError(ERR_MANIFEST + ": family_coverage manifest mismatch")
        for entry in coverage.get("designs") or []:
            rec = self._index.get(str((entry or {}).get("design_hash")))
            if rec is None:
                continue
            families = rec.get("families") or {}
            if len(families) != 2:
                continue  # evaluate() turns this into FAMILY_UNREACHABLE_DESIGN_VOID
            roles = _family_role_map(entry, families)
            if set(roles.values()) != set(families):
                raise V12ConfigurationError(ERR_APPROVAL_COVERAGE + ": role map does not cover both families")
            _validate_approval_entry(entry, families, str(rec.get("design_hash")))


    # ------------------------------------------------------------- runtime mode
    def _verify_runtime_approval(self) -> None:
        ap = self.approval
        bound_log = ap.get("append_only_log_path")
        if not bound_log:
            raise V12ConfigurationError(ERR_RUNTIME_LOG + ": approval lacks append_only_log_path")
        if Path(str(bound_log)).resolve() != self.append_only_log.resolve():
            raise V12ConfigurationError(ERR_RUNTIME_LOG + ": approval append_only_log_path mismatch")
        if str(ap.get("freeze_rule")) != FREEZE_RULE:
            raise V12ConfigurationError(ERR_RUNTIME_LOG + ": freeze_rule mismatch")
        if ap.get("final_run_manifest_required") is not True:
            raise V12ConfigurationError(ERR_RUNTIME_LOG + ": final_run_manifest_required must be true")
        for field, value in (("policy_doc_sha256", self.policy_doc_sha256),
                             ("builder_code_sha256", self.builder_code_sha256),
                             ("evaluator_code_sha256", self.evaluator_code_sha256)):
            bound = str(ap.get(field, ""))
            if not bound:
                raise V12ConfigurationError(ERR_APPROVAL + ": approval lacks " + field)
            if value and bound != str(value):
                raise V12ConfigurationError(ERR_APPROVAL + ": " + field + " mismatch")
        # A5 2026-11-11 (8 append-only conditions): the approved initial seed set is
        # bound by digest, never by a mutable embedded list.
        seeds = str(ap.get("initial_designs_manifest_sha256", "") or "")
        if not seeds:
            raise V12ConfigurationError(ERR_RUNTIME_RECORD + ": approval lacks initial_designs_manifest_sha256")
        initial_path = ap.get("initial_designs_manifest_path")
        if not initial_path:
            raise V12ConfigurationError(ERR_RUNTIME_RECORD + ": approval lacks initial_designs_manifest_path")
        p = Path(str(initial_path))
        if not p.is_file() or sha256_file(p) != seeds:
            raise V12ConfigurationError(ERR_RUNTIME_RECORD + ": initial_designs_manifest SHA mismatch")

    def _verify_code_identity(self) -> None:
        """A5 2026-11-11 fix 4: runtime/replay must prove which code/doc actually ran.

        The authoritative hashes are recomputed from the approval-bound *paths*;
        a bare SHA string in the approval is never trusted on its own.
        """
        if self.mode not in (MODE_RUNTIME, MODE_REPLAY):
            return
        import importlib
        import inspect

        eval_src = Path(inspect.getsourcefile(type(self)) or __file__).resolve()
        self.evaluator_file_sha256 = sha256_file(eval_src)
        freeze_module = importlib.import_module(type(self).__module__.rsplit(".", 1)[0] + ".freeze_api")
        freeze_src = Path(inspect.getsourcefile(freeze_module) or getattr(freeze_module, "__file__")).resolve()
        self.freeze_api_file_sha256 = sha256_file(freeze_src)
        for sha_field, path_field, attr in (
                ("policy_doc_sha256", "policy_doc_path", "policy_doc_sha256"),
                ("builder_code_sha256", "builder_code_path", "builder_code_sha256")):
            bound_sha = str(self.approval.get(sha_field) or "")
            bound_path = str(self.approval.get(path_field) or "")
            if not bound_sha or not bound_path:
                raise V12ConfigurationError(ERR_CODE_SHA + ": approval lacks " + path_field + "/" + sha_field)
            path = Path(bound_path)
            if not path.is_file() or sha256_file(path) != bound_sha:
                raise V12ConfigurationError(ERR_CODE_SHA + ": " + sha_field + " does not match " + path_field)
            passed = str(getattr(self, attr) or "")
            if passed and passed != bound_sha:
                raise V12ConfigurationError(ERR_CODE_SHA + ": " + sha_field + " mismatch")
            setattr(self, attr, bound_sha)
        if str(self.approval.get("freeze_api_sha256") or "") != self.freeze_api_file_sha256:
            raise V12ConfigurationError(ERR_CODE_SHA + ": sha256(freeze_api) != approval")
        if str(self.approval.get("evaluator_code_sha256") or "") != self.evaluator_file_sha256:
            raise V12ConfigurationError(ERR_CODE_SHA + ": sha256(evaluator file) != approval")
        self.evaluator_code_sha256 = self.evaluator_file_sha256

    def _verify_replay_binding(self) -> None:
        """Lead m07580 / A5 fix 2: approval.replay_bundles is mandatory and path-bound.

        The bundle manifest is parsed and its case table is compared item-by-item with
        approval.replay_bundles.cases (SHAs *and* byte counts).  Case files are later
        resolved only from bundle_root/<case_id>/<bundle file name>; caller-supplied
        paths/SHAs are ignored and cannot widen the binding.
        """
        if self.mode != MODE_REPLAY:
            return
        binding = self.approval.get("replay_bundles")
        if not isinstance(binding, Mapping):
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": approval.replay_bundles missing")
        required = ("schema", "bundle_manifest_path", "bundle_manifest_sha256",
                    "bundle_root", "semantics_doc_path", "semantics_doc_sha256", "cases")
        missing = [k for k in required if not binding.get(k)]
        if missing:
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": missing " + ",".join(missing))
        self.replay_bundle = dict(binding)
        self.replay_bundle_root = Path(str(binding["bundle_root"])).resolve()
        if not self.replay_bundle_root.is_dir():
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": bundle_root is not a directory")
        manifest_path = Path(str(binding["bundle_manifest_path"])).resolve()
        semantics_path = Path(str(binding["semantics_doc_path"])).resolve()
        if not self._within_root(manifest_path, self.replay_bundle_root):
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": bundle_manifest_path escapes bundle_root")
        if not manifest_path.is_file() or sha256_file(manifest_path) != str(binding["bundle_manifest_sha256"]):
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": bundle manifest SHA mismatch")
        if not semantics_path.is_file() or sha256_file(semantics_path) != str(binding["semantics_doc_sha256"]):
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": semantics_doc SHA mismatch")
        self.replay_bundle_manifest_path = manifest_path
        if self.replay_bundle_manifest is not None and \
                Path(self.replay_bundle_manifest).resolve() != manifest_path:
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": replay_bundle_manifest != approval path")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": unreadable bundle manifest") from exc
        items = payload.get("cases") if isinstance(payload, Mapping) else None
        if not isinstance(items, list):
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": bundle manifest cases missing")
        manifest_cases: Dict[str, Mapping[str, Any]] = {}
        for item in items:
            cid = str((item or {}).get("case_id") or "")
            if not cid or cid in manifest_cases:
                raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": duplicate/empty case_id")
            manifest_cases[cid] = item
        approval_cases = binding.get("cases")
        if not isinstance(approval_cases, Mapping) or not approval_cases:
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": approval cases empty")
        if set(manifest_cases) != set(approval_cases):
            raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": case sets differ")
        filename_map = (("vspgeom_sha256", "geometry.vspgeom"), ("vkey_sha256", "geometry.vkey"),
                        ("vspaero_sha256", "concorde_baseline.vspaero"),
                        ("csf_sha256", "concorde_baseline.csf"), ("polar_sha256", "expected.polar"))
        self.replay_case_files = {}
        for cid in sorted(approval_cases):
            if cid not in ("PRE-01", "PRE-02", "PRE-03"):
                raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": preflight case_id not allowed: " + cid)
            acase = approval_cases[cid]
            mcase = manifest_cases[cid]
            if not isinstance(acase, Mapping):
                raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": case entry not a mapping: " + cid)
            if str(mcase.get("design_hash")) != str(acase.get("design_hash")):
                raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": design_hash mismatch: " + cid)
            if str(mcase.get("family_label")) != str(acase.get("family")):
                raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": family label mismatch: " + cid)
            files = mcase.get("files")
            if not isinstance(files, Mapping):
                raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": files table missing: " + cid)
            case_root = (self.replay_bundle_root / cid).resolve()
            if not self._within_root(case_root, self.replay_bundle_root):
                raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": case dir escapes bundle_root")
            resolved_case: Dict[str, Any] = {"design_hash": str(acase.get("design_hash")),
                                             "family": str(acase.get("family"))}
            for field, name in filename_map:
                record = files.get(name)
                if not isinstance(record, Mapping):
                    raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": missing file entry " + name)
                sha = str(acase.get(field) or "")
                if not sha or str(record.get("sha256")) != sha:
                    raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": " + field + " mismatch: " + cid)
                if field == "polar_sha256":
                    if str(mcase.get("expected_polar_sha256")) != sha:
                        raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": polar_sha256 mismatch: " + cid)
                path = (case_root / name).resolve()
                if not self._within_root(path, case_root) or not path.is_file():
                    raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": missing case file " + name)
                if sha256_file(path) != sha:
                    raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": on-disk " + name + " mismatch: " + cid)
                if "bytes" in record and int(record["bytes"]) != path.stat().st_size:
                    raise V12ConfigurationError(ERR_REPLAY_BUNDLE + ": " + name + " bytes mismatch: " + cid)
                resolved_case[field] = sha
                resolved_case[field.replace("_sha256", "_path")] = str(path)
            self.replay_case_files[cid] = resolved_case

    @staticmethod
    def _within_root(path: Path, root: Path) -> bool:
        try:
            Path(path).resolve().relative_to(Path(root).resolve())
            return True
        except ValueError:
            return False

    def _replay_bundle_case(self, cid: str, design_hash: str, family_label: str,
                            frozen: Mapping[str, Any]) -> Dict[str, Any]:
        entry = (self.replay_case_files or {}).get(cid)
        if not isinstance(entry, Mapping):
            raise V12ConfigurationError("case " + cid + " not present in approval.replay_bundles")
        if str(entry.get("design_hash")) != str(design_hash):
            raise V12ConfigurationError("approval case design_hash != evaluated design")
        if str(entry.get("family")) != str(family_label):
            raise V12ConfigurationError("approval case family != frozen family label")
        if str(entry.get("vspgeom_sha256")) != str(frozen.get("frozen_vspgeom_sha256") or ""):
            raise V12ConfigurationError("vspgeom SHA != frozen family byte bundle")
        if str(entry.get("vkey_sha256")) != str(frozen.get("frozen_vkey_sha256") or ""):
            raise V12ConfigurationError("vkey SHA != frozen family byte bundle")
        # Re-verify the bytes immediately before they are copied (TOCTOU guard).
        for field in ("vspgeom_sha256", "vkey_sha256", "vspaero_sha256", "csf_sha256", "polar_sha256"):
            path = Path(str(entry.get(field.replace("_sha256", "_path"))))
            if not path.is_file() or sha256_file(path) != str(entry[field]):
                raise V12ConfigurationError(field + " changed after approval")
        return dict(entry)


    def _runtime_records(self, *, raise_on_error: bool = True) -> Dict[str, Dict[str, Any]]:
        from .freeze_api import latest_design_records, verify_chain
        report = verify_chain(self.append_only_log)
        if not report["valid"]:
            if raise_on_error:
                raise V12ConfigurationError(ERR_CHAIN + ": " + ",".join(report["errors"][:5]))
            return {}
        self._chain_report = report
        return latest_design_records(self.append_only_log)

    def _runtime_resolve(self, x12: Sequence[float], family: str) -> tuple:
        from .freeze_api import role_map
        if family not in ("f1", "f2"):
            raise V12ConfigurationError(ERR_FAMILY_SELECTOR + ": " + str(family))
        dh = compute_design_hash(x12)
        records = self._runtime_records(raise_on_error=False)
        if not records:
            raise KeyError((ERR_CHAIN, "append-only log invalid or empty"))
        rec = records.get(dh)
        if rec is None:
            raise KeyError((ERR_RUNTIME_RECORD, dh))
        if rec.get("status") != "PAIR_READY" or rec.get("arm_blind") is not True:
            raise KeyError((ERR_RUNTIME_VOID, "%s/%s" % (dh, rec.get("status"))))
        families = rec.get("families") or {}
        if len(families) != 2:
            raise KeyError((ERR_RUNTIME_VOID, dh))
        try:
            roles = role_map(list(families.keys()))
        except ValueError as exc:
            raise KeyError((ERR_RUNTIME_ROLE, str(exc))) from exc
        if dict(rec.get("roles") or {}) != roles:
            raise KeyError((ERR_RUNTIME_ROLE, "record roles %r != %r" % (rec.get("roles"), roles)))
        if canonical_x12_payload(rec.get("x12", [])) != canonical_x12_payload(x12):
            raise KeyError((ERR_X12_MANIFEST, dh))
        label = roles[family]
        fam = dict(families[label])
        static = self._index.get(dh)
        if static is not None:
            static_fams = static.get("families") or {}
            for role in ("f1", "f2"):
                static_fam = static_fams.get(roles[role]) or {}
                runtime_fam = families.get(roles[role]) or {}
                if (static_fam.get("frozen") or {}).get("frozen_vspgeom_sha256") != \
                        (runtime_fam.get("frozen") or {}).get("frozen_vspgeom_sha256"):
                    raise KeyError((ERR_RUNTIME_SHA, "%s/%s" % (dh, roles[role])))
        mrec = static if static is not None else {
            "design_hash": dh, "x12": rec.get("x12"), "design_index": -1,
            "builder_code_sha256": rec.get("builder_code_sha256", ""),
        }
        return dh, mrec, label, fam

    # ------------------------------------------------------------------ ledger
    def _open_ledger(self) -> None:
        if self.ledger_path is None:
            return
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.ledger_path.with_name(self.ledger_path.name + ".lock")
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise V12ConfigurationError(ERR_LEDGER + ": " + str(lock)) from exc
        os.write(descriptor, ("pid=%d\n" % os.getpid()).encode("ascii"))
        os.close(descriptor)
        self._lock_path = lock
        self._ledger_handle = self.ledger_path.open("a", encoding="utf-8")

    def _ledger_append(self, row: Mapping[str, Any]) -> None:
        if self._ledger_handle is None:
            return
        payload = {"ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "batch_id": self.batch_id, "mode": self.mode,
                   "writer_pid": os.getpid()}
        payload.update(dict(row))
        self._ledger_handle.write(canonical_json(payload) + "\n")
        self._ledger_handle.flush()

    def close(self) -> None:
        if self._ledger_handle is not None:
            self._ledger_handle.close()
            self._ledger_handle = None
        if self._lock_path is not None:
            try:
                self._lock_path.unlink()
            except FileNotFoundError:
                pass
            self._lock_path = None

    def _resolve(self, x12: Sequence[float], family: str) -> tuple:
        if self.mode == MODE_RUNTIME:
            return self._runtime_resolve(x12, family)
        if family not in ("f1", "f2"):
            raise V12ConfigurationError(ERR_FAMILY_SELECTOR + ": " + str(family))
        dh = compute_design_hash(x12)
        rec = self._index.get(dh)
        if rec is None:
            raise KeyError((ERR_DESIGN_NOT_IN_MANIFEST, dh))
        if canonical_x12_payload(rec.get("x12", [])) != canonical_x12_payload(x12):
            raise KeyError((ERR_X12_MANIFEST, dh))
        families = rec.get("families") or {}
        if len(families) != 2:
            raise KeyError((ERR_DESIGN_VOID, dh))
        entry = _approval_design_coverage(self.approval, dh)
        if entry is None:
            raise KeyError((ERR_APPROVAL_COVERAGE, dh))
        roles = _family_role_map(entry, families)
        _validate_approval_entry(entry, families, dh)
        label = roles[family]
        fam = families[label]
        if not fam.get("hit") or not fam.get("frozen"):
            raise KeyError((ERR_DESIGN_VOID, dh + "/" + label))
        return dh, rec, label, fam

    # ------------------------------------------------------------------- call
    def evaluate(self, x12: Sequence[float], family: str, case_id: Optional[str] = None,
                 meta: Optional[Mapping[str, Any]] = None,
                 replay_input: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        self.calls += 1
        if len(x12) != 12:
            raise V12ConfigurationError(ERR_X12_LENGTH)
        if any(not math.isfinite(float(v)) for v in x12):
            raise V12ConfigurationError(ERR_X12_NONFINITE)
        if all(0.0 <= float(v) <= 1.0 for v in x12):
            raise V12ConfigurationError(ERR_X12_UNIT_BOX)
        cid = str(case_id or ("case-%04d" % self.calls))
        if not _CASE_ID_RE.match(cid) or ".." in cid:
            rec = _base_record(cid[:80], family, self.mock)
            rec["errors"] = [_error(ERR_CASE_ID, "unsafe case_id")]
            rec["status"] = rec["record_status"] = STATUS_GEOMETRY_INVALID
            self.refusals.append({"case_id": cid[:80], "code": ERR_CASE_ID, "detail": "unsafe"})
            return rec
        rec = _base_record(cid, family, self.mock)
        rec["mode"] = self.mode
        rec["evaluator_file_sha256"] = self.evaluator_file_sha256
        rec["meta"] = dict(meta or {})
        try:
            dh, mrec, label, fam = self._resolve(x12, family)
        except KeyError as exc:
            code, detail = exc.args[0]
            rec["errors"] = [_error(code, str(detail))]
            if code in (ERR_DESIGN_NOT_IN_MANIFEST, ERR_RUNTIME_RECORD):
                rec["status"] = rec["record_status"] = STATUS_DISCARDED
            elif code in (ERR_DESIGN_VOID, ERR_RUNTIME_VOID, ERR_RUNTIME_SHA, ERR_RUNTIME_ROLE, ERR_CHAIN):
                rec["status"] = rec["record_status"] = STATUS_FAMILY_VOID
            else:
                rec["status"] = rec["record_status"] = STATUS_GEOMETRY_INVALID
            self.refusals.append({"case_id": cid, "code": code, "detail": str(detail)})
            return rec
        rec["design"] = {"x12": [float(v) for v in x12], "design_hash": dh}
        if (dh, family) in self._seen_cells:
            rec["errors"] = [_error(ERR_DUPLICATE_CELL, "cell already evaluated")]
            rec["status"] = rec["record_status"] = STATUS_NOT_RUN
            self.refusals.append({"case_id": cid, "code": ERR_DUPLICATE_CELL, "detail": dh})
            return rec
        replay_physical_run = self.mode == MODE_REPLAY and self.replay_physical
        if replay_physical_run:
            if self.starts_used >= self.max_starts:
                rec["errors"] = [_error(ERR_BUDGET, "solver budget exhausted")]
                rec["status"] = rec["record_status"] = STATUS_NOT_RUN
                return rec
        elif self.mock or self.mode == MODE_REPLAY:
            if self.simulated_starts_used >= self.max_starts:
                rec["errors"] = [_error(ERR_BUDGET, "simulated budget exhausted")]
                rec["status"] = rec["record_status"] = STATUS_NOT_RUN
                return rec
        elif self.starts_used >= self.max_starts:
            rec["errors"] = [_error(ERR_BUDGET, "solver budget exhausted")]
            rec["status"] = rec["record_status"] = STATUS_NOT_RUN
            return rec

        frozen = fam["frozen"]
        case_dir = self.run_dir / cid
        replay = dict(replay_input or {})
        bundle_case: Optional[Dict[str, Any]] = None
        if self.mode == MODE_REPLAY:
            try:
                bundle_case = self._replay_bundle_case(cid, dh, label, frozen)
            except V12ConfigurationError as exc:
                rec["errors"] = [_error(ERR_REPLAY_BUNDLE, str(exc))]
                rec["status"] = rec["record_status"] = STATUS_GEOMETRY_INVALID
                self.refusals.append({"case_id": cid, "code": ERR_REPLAY_BUNDLE,
                                      "detail": str(exc)[:200]})
                return rec
            replay["expected_polar_sha256"] = bundle_case["polar_sha256"]
        case_dir.mkdir(parents=True, exist_ok=True)
        src_geom = (Path(str(bundle_case["vspgeom_path"])) if self.mode == MODE_REPLAY
                    else Path(str(frozen["frozen_vspgeom_path"])))
        dst_geom = case_dir / "model.vspgeom"
        shutil.copyfile(src_geom, dst_geom)
        # The freeze layout is <family>/{model.vspgeom,model.vkey,model.vsp3}; the
        # manifest only stores the .vspgeom path + the .vkey SHA, so the .vkey is
        # resolved as a sibling and then verified by SHA (A5 Q3 fail-closed).
        vkey_src = (bundle_case["vkey_path"] if self.mode == MODE_REPLAY
                    else frozen.get("frozen_vkey_path"))
        if self.mode == MODE_REPLAY:
            # Archival replay: the approval-bound bundle record is the authority.
            expected_vkey = str(bundle_case["vkey_sha256"])
        else:
            expected_vkey = frozen.get("frozen_vkey_sha256")
        vkey_src_path = Path(str(vkey_src)) if vkey_src else src_geom.with_suffix(".vkey")
        vkey_present = bool(expected_vkey) and vkey_src_path.is_file()
        dst_vkey = case_dir / "model.vkey"
        if vkey_present:
            shutil.copyfile(vkey_src_path, dst_vkey)
        basename = "concorde_baseline"
        if self.mode == MODE_REPLAY:
            expected_geom = str(bundle_case["vspgeom_sha256"])
        else:
            expected_geom = str(frozen["frozen_vspgeom_sha256"])
        if self.mode == MODE_REPLAY:
            shutil.copyfile(Path(str(bundle_case["vspaero_path"])), case_dir / (basename + ".vspaero"))
            shutil.copyfile(Path(str(bundle_case["csf_path"])), case_dir / (basename + ".csf"))
        copy_ts = self.clock()
        pre_geom = sha256_file(dst_geom)
        pre_vkey = sha256_file(dst_vkey) if dst_vkey.exists() else None
        rec["geometry_bundle"] = {
            "family_role": family,
            "family_label": label,
            "mesh_family": _label_nodes_elements(label),
            "vspgeom_sha256": expected_geom,
            "vspgeom_bytes": int(frozen.get("frozen_vspgeom_bytes", src_geom.stat().st_size)),
            "vkey_sha256": expected_vkey,
            "vkey_present": vkey_present,
            "canonical_mesh_sha256": str(frozen.get("canonical_mesh_sha256", "")),
            "source": MODE_REPLAY if self.mode == MODE_REPLAY else "FROZEN_MANIFEST",
            "evaluator_mode": self.mode,
            "manifest_sha256": self.manifest_sha256,
            "builder_code_sha256": str(mrec.get("builder_code_sha256", "")),
            "build_attempts": int(fam.get("attempts", 0)),
            "manifest_design_index": int(mrec.get("design_index", -1)),
            "case_frozen_copy_ts_utc": copy_ts,
            "case_frozen_copy_sha256_pre": pre_geom,
            "case_frozen_vkey_sha256_pre": pre_vkey,
        }
        # A5 Q4 / E12-08: nested case_consumption contract (flat fields kept too).
        rec["case_consumption"] = {
            "case_dir": str(case_dir),
            "frozen_copy_sha256_pre": pre_geom,
            "frozen_vkey_sha256_pre": pre_vkey,
            "frozen_copy_sha256_post": None,
            "frozen_vkey_sha256_post": None,
            "copy_ts_utc": copy_ts,
            "verify_ts_utc": None,
            "manifest_sha256": self.manifest_sha256,
            "manifest_design_index": int(mrec.get("design_index", -1)),
            "source": MODE_REPLAY if self.mode == MODE_REPLAY else "FROZEN_MANIFEST",
        }
        if not vkey_present or pre_vkey is None:
            rec["errors"] = [_error(ERR_VKEY_MISSING, "frozen .vkey missing")]
            rec["status"] = rec["record_status"] = STATUS_GEOMETRY_INVALID
            rec["sha_verification"] = {"pre": "MISMATCH", "post": "NOT_RUN"}
            self.refusals.append({"case_id": cid, "code": ERR_VKEY_MISSING, "detail": "missing"})
            return rec
        pre_ok = (pre_geom == expected_geom) and (pre_vkey == str(expected_vkey or ""))
        rec["sha_verification"]["pre"] = "MATCH" if pre_ok else "MISMATCH"
        if self.sha_verify_pre and not pre_ok:
            # Runtime mode: a frozen byte bundle that no longer matches the chained
            # record void the whole design (A5 Q2), it is not a per-eval geometry error.
            if self.mode == MODE_RUNTIME:
                rec["errors"] = [_error(ERR_RUNTIME_SHA, "runtime frozen SHA mismatch")]
                rec["status"] = rec["record_status"] = STATUS_FAMILY_VOID
            else:
                rec["errors"] = [_error(ERR_FROZEN_PRE, "pre-copy SHA mismatch")]
                rec["status"] = rec["record_status"] = STATUS_GEOMETRY_INVALID
            self.refusals.append({"case_id": cid, "code": ERR_FROZEN_PRE, "detail": dh})
            return rec

        # start (mock simulation, archival replay, or a real authorised launch)
        physical = False
        if self.mode == MODE_REPLAY and self.replay_physical:
            if not self.allow_physical_starts or self.real_spawn is None:
                raise RealStartNotAuthorized(ERR_REAL_NOT_AUTHORIZED)
            physical = True
        elif self.mode == MODE_REPLAY:
            # Non-physical replay is an offline pinned self-check: simulated only.
            if self.spawn is None:
                raise RealStartNotAuthorized(ERR_REPLAY_INPUT)
            self.simulated_starts_used += 1
            rec["solver"]["simulated_solver_starts"] = 1
        elif self.mock:
            self.simulated_starts_used += 1
            rec["solver"]["simulated_solver_starts"] = 1
        else:
            if not self.allow_physical_starts or self.real_spawn is None:
                raise RealStartNotAuthorized(ERR_REAL_NOT_AUTHORIZED)
            physical = True
        if physical:
            self.starts_used += 1
            rec["solver"]["physical_solver_starts"] = 1
            rec["physical_call_count"] = 1
            if self.mode == MODE_REPLAY:
                rec["solver"]["launch_kind"] = "REAL_REPLAY_B2"
        self._seen_cells.add((dh, family))
        if physical:
            self._ledger_append({"event": "start", "case_id": cid, "design_hash": dh,
                                 "family_role": family, "family_label": label,
                                 "vspgeom_path": str(dst_geom),
                                 "launch_kind": rec["solver"]["launch_kind"]})

        context = {
            "case_id": cid,
            "case_dir": str(case_dir),
            "family_role": family,
            "family_label": label,
            "design_hash": dh,
            "vspgeom_path": str(dst_geom),
            "vkey_path": str(dst_vkey),
            "mock": self.mock,
            "mode": self.mode,
            "basename": basename,
            "replay_input": replay,
        }
        try:
            outcome = self._invoke(context)
        except TimeoutError:
            outcome = {"status": STATUS_SOLVER_FAILED, "error": ERR_TIMEOUT, "error_code": ERR_TIMEOUT}
        except Exception as exc:  # fail-closed, start already charged
            outcome = {"status": STATUS_SOLVER_FAILED, "error": "SOLVER_EXCEPTION: " + repr(exc)}
        post_geom = sha256_file(dst_geom)
        post_vkey = sha256_file(dst_vkey) if dst_vkey.exists() else None
        post_ok = (post_geom == expected_geom) and (post_vkey == str(expected_vkey or ""))
        rec["sha_verification"]["post"] = "MATCH" if post_ok else "MISMATCH"
        rec["geometry_bundle"]["case_frozen_copy_sha256_post"] = post_geom
        rec["geometry_bundle"]["case_frozen_vkey_sha256_post"] = post_vkey
        rec["geometry_bundle"]["verify_ts_utc"] = self.clock()
        rec["case_consumption"].update({
            "frozen_copy_sha256_post": post_geom,
            "frozen_vkey_sha256_post": post_vkey,
            "verify_ts_utc": self.clock(),
        })
        if not post_ok:
            rec["status"] = rec["record_status"] = STATUS_SOLVER_FAILED
            rec["errors"] = [_error(ERR_FROZEN_POST, "post-solve SHA mismatch", no_start=False)]
            rec["usable_for_objective"] = False
            rec["physical_call_count"] = 1 if physical else 0
            self._ledger_append({"event": "end", "case_id": cid, "status": STATUS_SOLVER_FAILED,
                                 "error": ERR_FROZEN_POST})
            return rec
        status = str(outcome.get("status", STATUS_SOLVER_FAILED))
        rec["status"] = rec["record_status"] = status
        rec["objective"]["value"] = outcome.get("objective") if status == STATUS_SOLVED else None
        if outcome.get("results") is not None:
            rec["results"] = dict(outcome["results"])
        if outcome.get("lift") is not None:
            rec["lift"] = dict(outcome["lift"])
        if self.mode == MODE_REPLAY:
            expected_polar = str(replay["expected_polar_sha256"])
            polar_path = outcome.get("polar_path") or str(case_dir / (basename + ".polar"))
            actual_polar = sha256_file(Path(polar_path)) if Path(polar_path).is_file() else None
            polar_ok = actual_polar == expected_polar
            rec["replay"] = {
                "source": "REPLAY_B2",
                "expected_polar_sha256": expected_polar,
                "actual_polar_sha256": actual_polar,
                "polar_match": bool(polar_ok),
                "input_override": {"vspaero_path": str(replay.get("vspaero_path")),
                                   "csf_path": str(replay.get("csf_path")),
                                   "vspgeom_path": str(replay.get("vspgeom_path")),
                                   "vkey_path": str(replay.get("vkey_path"))},
                "internal_evals": int(outcome.get("internal_evals", 7)),
                "pass_authority": "A2_BATCH_ONLY",
            }
            rec["replay"]["physical"] = bool(physical)
            rec["replay"]["launch_kind"] = ("REAL_REPLAY_B2" if physical
                                            else "SYNTHETIC_REPLAY_SELF_CHECK")
            rec["physical_call_count"] = 1 if physical else 0
            if status == STATUS_SOLVED and not polar_ok:
                # A5/R1: ONLY a genuinely solved replay whose post-solve polar
                # bytes mismatch is downgraded to SOLVED_UNVERIFIED.  A non-SOLVED
                # outcome (spawn refusal before Popen, SOLVER_FAILED, TIMEOUT) must
                # keep its original status and error code: a missing polar is then
                # a consequence of the failure, not evidence of a solved-but-
                # unverified run.
                status = rec["status"] = rec["record_status"] = STATUS_SOLVED_UNVERIFIED
                rec["errors"] = [_error(ERR_REPLAY_POLAR, "polar SHA mismatch", no_start=False)]
        if outcome.get("error"):
            code = outcome.get("error_code") or ("MOCK_SOLVER_ERROR" if self.mock else "SOLVER_ERROR")
            rec["errors"] = [_error(str(code), str(outcome["error"]), no_start=False)]
        rec["usable_for_objective"] = bool(status == STATUS_SOLVED and rec["objective"]["value"] is not None)
        rec["attempt_ids"] = ["%s-%s-%s-a%03d" % (self.batch_id, dh, family, self.calls)]
        rec["solver"]["attempt_ids"] = list(rec["attempt_ids"])
        if physical:
            rec["physical_call_count"] = 1
            self._ledger_append({"event": "end", "case_id": cid, "design_hash": dh,
                                 "status": status, "objective": rec["objective"]["value"],
                                 "physical_call_count": 1,
                                 "launch_kind": rec["solver"].get("launch_kind")})
        return rec

    def _invoke(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.mode == MODE_REPLAY:
            if self.replay_physical:
                if self.real_spawn is None:
                    raise RealStartNotAuthorized(ERR_REAL_NOT_AUTHORIZED)
                return self.real_spawn(context)
            # Non-physical replay is a pinned self-check: offline callback only, no launcher.
            if self.spawn is None:
                raise RealStartNotAuthorized(ERR_REPLAY_INPUT)
            return self.spawn(context)
        if not self.mock:
            if self.real_spawn is None:
                raise RealStartNotAuthorized(ERR_REAL_NOT_AUTHORIZED)
            return self.real_spawn(context)
        if self.spawn is not None:  # offline mock callback only; never a solver launcher
            return self.spawn(context)
        # default mock solver: deterministic synthetic objective from the design hash
        seed = int(hashlib.sha256((context["design_hash"] + "|" + context["family_role"]).encode()).hexdigest()[:8], 16)
        return {
            "status": STATUS_SOLVED,
            "objective": 120000.0 + (seed % 10000) / 100.0,
            "results": {"alpha_deg": [-2, 0, 2, 4, 6, 8, 10], "cltot": [0.0] * 7, "cdi": [0.0] * 7,
                        "cdo": [0.0] * 7, "cdtot": [0.0] * 7, "cmy": [0.0] * 7},
            "lift": {"mock": True},
        }

    # ---------------------------------------------------------------- summary
    def summary(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA,
            "evaluator_id": EVALUATOR_ID,
            "backend": BACKEND_MOCK if self.mock else BACKEND_REAL,
            "mode": self.mode,
            "physical_validation_status": PHYSICAL_VALIDATION_STATUS,
            "chain": getattr(self, "_chain_report", None),
            "ledger_path": str(self.ledger_path) if self.ledger_path else None,
            "batch_id": self.batch_id,
            "max_starts": self.max_starts,
            "starts_used": self.starts_used,
            "simulated_starts_used": self.simulated_starts_used,
            "remaining": max(0, self.max_starts - (self.simulated_starts_used if self.mock else self.starts_used)),
            "calls": self.calls,
            "refusals": list(self.refusals),
            "mock": self.mock,
            "replay_physical": bool(getattr(self, "replay_physical", False)),
            "replay_bundle_sha256": str((getattr(self, "replay_bundle", None) or {}).get("bundle_manifest_sha256", "")),
            "evaluator_file_sha256": str(getattr(self, "evaluator_file_sha256", "")),
            "freeze_api_file_sha256": str(getattr(self, "freeze_api_file_sha256", "")),
            "code_identity": {
                "policy_doc_sha256": str(getattr(self, "policy_doc_sha256", "")),
                "builder_code_sha256": str(getattr(self, "builder_code_sha256", "")),
                "evaluator_code_sha256": str(getattr(self, "evaluator_code_sha256", "")),
            },
            "stop_report_path": str(self._stop_report_path) if getattr(self, "_stop_report_path", None) else None,
            "fuel_burn_kg": None,
        }


def make_evaluate_fn(manifest: Mapping[str, Any], approval: Optional[Mapping[str, Any]], *,
                     batch_id: str, max_starts: int, run_dir: Path,
                     manifest_source: Optional[Path] = None,
                     spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
                     real_spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
                     allow_physical_starts: bool = False, mock: bool = True,
                     replay_physical: bool = False,
                     replay_bundle_manifest: Optional[Path] = None,
                     sha_verify_pre: bool = True, sha_verify_post: bool = True,
                     mode: str = MODE_STATIC,
                     append_only_log: Optional[Path] = None,
                     policy_doc_sha256: str = "", builder_code_sha256: str = "",
                     evaluator_code_sha256: str = "", ledger_path: Optional[Path] = None) -> TwoFamilyEvaluator:
    """A2 entry point; mock defaults to True so no physical start can happen accidentally."""
    return TwoFamilyEvaluator(
        manifest, approval, batch_id=batch_id, max_starts=max_starts, run_dir=run_dir,
        manifest_source=manifest_source, spawn=spawn, real_spawn=real_spawn,
        allow_physical_starts=allow_physical_starts, mock=mock,
        replay_physical=replay_physical, replay_bundle_manifest=replay_bundle_manifest,
        sha_verify_pre=sha_verify_pre, sha_verify_post=sha_verify_post, mode=mode,
        append_only_log=append_only_log, policy_doc_sha256=policy_doc_sha256,
        builder_code_sha256=builder_code_sha256, evaluator_code_sha256=evaluator_code_sha256,
        ledger_path=ledger_path)
