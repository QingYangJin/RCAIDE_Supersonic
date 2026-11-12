"""One evaluation interface, three backends (D-REAL-001 A2).

    evaluate(x12, case_index=..., case_id=..., meta=...) -> AeroEvaluation

The evaluation internally performs lift matching: D_i = q*Sref(x)*CDi at
L = q*Sref(x)*CLtot equal to L_ref = 136000*g0 N, using linear interpolation on
the pre-registered alpha grid (governance v2 sec 12.5). At most one refine launch
with the pre-registered refine grid; at most max_launches_per_design launches.

Backends
--------
MOCK          MockLiftMatchEvaluator: deterministic synthetic aero model.
              physical_solver_starts=0; simulated_solver_starts counts fake
              launches; rows carry backend=MOCK and never enter real evidence.
REPLAY        ReplayEvaluator: replays historical records, 0 launches.
REAL_VSPAERO  RealVspaeroAdapter: thin adapter over A1
              dreal001.geometry.evaluator.AeroEvaluator.evaluate; refuses to run
              without an approved approval.json (fail-closed) and A1 callable.

Every launch is reserved fail-closed on SolverStartLedger before it happens.
"""
from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .cache import EvaluationCache, VisibleLabelStore
from .constants import (
    BACKEND_MOCK,
    DIMENSION,
    BACKEND_REAL,
    BACKEND_REPLAY,
    RECORD_GEOMETRY_INVALID,
    RECORD_LIFT_MATCH_FAILED,
    RECORD_MOCK,
    RECORD_NOT_RUN,
    RECORD_SOLVED_VALID,
    RECORD_SOLVER_FAILED,
    P2A_EVALUATE_SCHEMA,
    RECORD_TO_STATUS,
    REFERENCE_FRAME,
    SCHEMA_VERSION,
    STATUS_FAIL,
    STATUS_INVALID,
    STATUS_NOT_CONVERGED,
    STATUS_NOT_RUN,
    STATUS_VALID,
)
from .design import (
    clip_x12,
    constraint_violation_total,
    geometric_constraint_g,
    sref_from_physical,
    validate_x12,
)
from .ledger import AccountingViolation, SolverBudgetExceeded, SolverStartLedger
from .lift_match import interpolate_lift_match
from .records import (
    AeroEvaluation,
    AlphaSample,
    SolverAttempt,
    append_jsonl,
    canonical_x12,
    design_hash as compute_design_hash,
    read_jsonl,
    sha256_bytes,
    utc_now,
)


class RealSolverNotAuthorized(RuntimeError):
    """Raised when a REAL_VSPAERO backend is requested without approval."""


@dataclass
class ProbeResult:
    samples: List[AlphaSample]
    launches: int
    status: str
    attempt_refs: List[str] = field(default_factory=list)
    solver_config_sha256: str = ""
    geometry_sha256: str = ""
    geometry_source: str = ""
    mesh_family: str = ""
    mesh_nodes: int = 0
    mesh_elements: int = 0
    normalized_geometry_hash: str = ""
    vspgeom_sha256: str = ""
    wall_s: float = 0.0
    argv: List[str] = field(default_factory=list)
    raw_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    internal_cases: int = 0
    notes: str = ""


class EvaluationRecorder:
    """Append-only evaluations.jsonl / solver_attempts.jsonl writer."""

    def __init__(self, run_dir: Any, *, attempts_path: Optional[Any] = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.evaluations_path = self.run_dir / "evaluations.jsonl"
        self.attempts_path = Path(attempts_path) if attempts_path is not None else self.run_dir / "solver_attempts.jsonl"

    def record_evaluation(self, evaluation: AeroEvaluation) -> None:
        append_jsonl(self.evaluations_path, evaluation.as_dict())

    def record_attempt(self, attempt: SolverAttempt) -> None:
        append_jsonl(self.attempts_path, attempt.as_dict())

    def evaluations(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.evaluations_path)

    def attempts(self) -> List[Dict[str, Any]]:
        return read_jsonl(self.attempts_path)


class BaseLiftMatchEvaluator(abc.ABC):
    """Shared lift-matching / accounting workflow; backends implement _probe_*."""

    backend: str = BACKEND_MOCK
    source_kind: str = "MOCK"
    physical_validation_status: str = "NOT_VALIDATED"
    supports_alpha_sweep: bool = True
    #: A1 EVALUATOR_API v1.0 evaluates a fixed 7-alpha grid per launch; the A2
    #: refine grid needs an alpha-override entry point A1 has not published yet.
    #: REAL therefore cannot request a refine launch until A1 extends the API.
    supports_refine_sweep: bool = True
    requires_starts: bool = True

    def __init__(
        self,
        design_space: Any,
        task: Any,
        ledger: SolverStartLedger,
        *,
        batch_id: Optional[str] = None,
        run_id: Optional[str] = None,
        arm_id: str = "",
        seed: int = 0,
        cache: Optional[EvaluationCache] = None,
        label_store: Optional[VisibleLabelStore] = None,
        recorder: Optional[EvaluationRecorder] = None,
        run_dir: Optional[Any] = None,
        max_launches_per_design: Optional[int] = None,
        supports_alpha_sweep: Optional[bool] = None,
        noise_rel: float = 0.0,
        failure_callable: Optional[Callable[[np.ndarray, float], Optional[str]]] = None,
        fail_design_hashes: Sequence[str] = (),
        evaluator_id: Optional[str] = None,
    ) -> None:
        self.design_space = design_space
        self.task = task
        self.ledger = ledger
        self.batch_id = str(batch_id if batch_id is not None else ledger.batch_id)
        self.run_id = str(run_id if run_id is not None else ledger.run_id)
        self.arm_id = str(arm_id)
        self.seed = int(seed)
        self.cache = cache
        self.label_store = label_store
        if recorder is None and run_dir is not None:
            recorder = EvaluationRecorder(run_dir)
        self.recorder = recorder
        self.run_dir = Path(run_dir) if run_dir is not None else None
        self.max_launches_per_design = int(
            max_launches_per_design if max_launches_per_design is not None else task.max_launches_per_design
        )
        if supports_alpha_sweep is not None:
            self.supports_alpha_sweep = bool(supports_alpha_sweep)
        self.noise_rel = float(noise_rel)
        self.failure_callable = failure_callable
        self.fail_design_hashes = {str(item) for item in fail_design_hashes}
        self.evaluator_id = str(evaluator_id or ("%s:%s" % (self.backend.lower(), task.task_id)))
        self._case_counter = 0
        self._attempt_seq = 0
        self.history: List[AeroEvaluation] = []

    # -- helpers --------------------------------------------------------
    def cache_key(
        self,
        x12_canonical: str,
        *,
        mesh_family: str = "",
        normalized_geometry_hash: str = "",
    ) -> str:
        return EvaluationCache.key(
            x12_canonical,
            self.task.fingerprint(),
            self.task.solver_config_sha256,
            mesh_family=mesh_family,
            normalized_geometry_hash=normalized_geometry_hash,
        )

    def __call__(self, x12: Sequence[float], **kwargs: Any) -> AeroEvaluation:
        return self.evaluate(x12, **kwargs)

    def _next_attempt_id(self, case_id: str) -> Tuple[str, int]:
        self._attempt_seq += 1
        return "%s-a%02d" % (case_id, self._attempt_seq), self._attempt_seq

    def _physical(self, vector: np.ndarray) -> Dict[str, float]:
        physical = self.design_space.from_unit_interval([float(value) for value in np.clip(vector, 0.0, 1.0)])
        return {str(key): float(value) for key, value in dict(physical).items()}

    def _reservation_size(self) -> int:
        if not self.requires_starts:
            return 0
        if self.backend == BACKEND_REAL:
            return max(1, min(int(self.max_launches_per_design), 2))
        return 1

    def _collect(self, vector: np.ndarray, alphas: Sequence[float], case_id: str, *, phase: str) -> List[ProbeResult]:
        alphas = [float(value) for value in alphas]
        if not self.supports_alpha_sweep:
            results = []
            for alpha in alphas:
                reservation = self.ledger.reserve(1)
                try:
                    result = self._probe_single(vector, alpha, case_id, phase=phase)
                except BaseException:
                    self.ledger.cancel(reservation)
                    raise
                self.ledger.settle(reservation, result.launches, internal_solver_cases=result.internal_cases)
                results.append(result)
            return results
        size = self._reservation_size()
        reservation = None if size <= 0 else self.ledger.reserve(size)
        try:
            result = self._probe_batch(vector, alphas, case_id, phase=phase)
        except BaseException:
            if reservation is not None:
                self.ledger.cancel(reservation)
            raise
        if reservation is not None:
            self.ledger.settle(reservation, result.launches, internal_solver_cases=result.internal_cases)
        return [result]

    def _cache_payload(self, evaluation: AeroEvaluation) -> Dict[str, Any]:
        return {
            "status": evaluation.status,
            "record_status": evaluation.record_status,
            "alpha_deg": evaluation.alpha_deg,
            "CLtot": evaluation.CLtot,
            "CDi": evaluation.CDi,
            "CDtot": evaluation.CDtot,
            "CDo": evaluation.CDo,
            "CM": None if evaluation.CM is None else list(evaluation.CM),
            "L_N": evaluation.L_N,
            "D_i_N": evaluation.D_i_N,
            "Sref_m2": evaluation.Sref_m2,
            "lift_rel_error": evaluation.lift_rel_error,
            "alpha_samples": [dict(item) for item in evaluation.alpha_samples],
            "refines_used": evaluation.refines_used,
            "backend": evaluation.backend,
            "source_kind": evaluation.source_kind,
            "solver_config_sha256": evaluation.solver_config_hash,
            "geometry_sha256": evaluation.geometry_sha256,
            "geometry_source": evaluation.geometry_source,
            "mesh_family": evaluation.mesh_family,
            "mesh_nodes": int(evaluation.mesh_nodes),
            "mesh_elements": int(evaluation.mesh_elements),
            "normalized_geometry_hash": evaluation.normalized_geometry_hash,
            "vspgeom_sha256": evaluation.vspgeom_sha256,
        }

    def _evaluation(
        self,
        *,
        vector: np.ndarray,
        case_id: str,
        record_status: str,
        status: str,
        physical_solver_starts: int,
        simulated_solver_starts: int,
        cache_hit: bool,
        cache_key: str,
        labels_visible: bool,
        alpha_deg: Optional[float],
        CLtot: Optional[float],
        CDi: Optional[float],
        CDtot: Optional[float],
        CDo: Optional[float],
        CM: Optional[Tuple[float, float, float]],
        L_N: Optional[float],
        D_i_N: Optional[float],
        Sref_m2: Optional[float],
        lift_rel_error: Optional[float],
        alpha_samples: Sequence[AlphaSample],
        refines_used: int,
        attempt_refs: Sequence[str],
        solver_config_sha256: str,
        geometry_sha256: str,
        geometry_source: str,
        wall_s: float,
        mesh_family: str = "",
        mesh_nodes: int = 0,
        mesh_elements: int = 0,
        normalized_geometry_hash: str = "",
        vspgeom_sha256: str = "",
        error_code: str = "",
        error_message: str = "",
        notes: str = "",
    ) -> AeroEvaluation:
        q = float(self.task.q_Pa)
        return AeroEvaluation(
            schema_version=SCHEMA_VERSION,
            record_id="%s-c%04d" % (self.run_id, self._case_counter),
            batch_id=self.batch_id,
            run_id=self.run_id,
            task_id=self.task.task_id,
            arm_id=self.arm_id,
            design_hash=compute_design_hash(vector),
            x12_canonical=canonical_x12(vector),
            x12_unit=tuple(float(value) for value in vector),
            backend=self.backend,
            source_kind=self.source_kind,
            status=status,
            record_status=record_status,
            attempt_refs=tuple(str(item) for item in attempt_refs),
            physical_solver_starts=int(physical_solver_starts) if self.backend == BACKEND_REAL else 0,
            simulated_solver_starts=int(simulated_solver_starts) if self.backend != BACKEND_REAL else 0,
            cache_hit=bool(cache_hit),
            cache_key=str(cache_key),
            labels_visible_to_arm=bool(labels_visible),
            alpha_deg=None if alpha_deg is None else float(alpha_deg),
            CLtot=None if CLtot is None else float(CLtot),
            CDi=None if CDi is None else float(CDi),
            CDtot=None if CDtot is None else float(CDtot),
            CDo=None if CDo is None else float(CDo),
            CM=None if CM is None else tuple(float(item) for item in CM),
            L_N=None if L_N is None else float(L_N),
            D_i_N=None if D_i_N is None else float(D_i_N),
            q_Pa=q,
            Sref_m2=None if Sref_m2 is None else float(Sref_m2),
            L_ref_N=float(self.task.lift_reference_N),
            lift_rel_error=None if lift_rel_error is None else float(lift_rel_error),
            solver_config_hash=str(solver_config_sha256 or self.task.solver_config_sha256),
            reference_frame=REFERENCE_FRAME,
            geometry_sha256=str(geometry_sha256),
            created_ts_utc=utc_now(),
            wall_s=float(wall_s),
            refines_used=int(refines_used),
            error_code=str(error_code),
            error_message=str(error_message),
            alpha_samples=tuple(sample.as_dict() for sample in alpha_samples),
            geometry_source=str(geometry_source),
            notes=str(notes),
            mesh_family=str(mesh_family),
            mesh_nodes=int(mesh_nodes or 0),
            mesh_elements=int(mesh_elements or 0),
            normalized_geometry_hash=str(normalized_geometry_hash),
            vspgeom_sha256=str(vspgeom_sha256),
        )

    def _cache_hit_evaluation(
        self, *, vector: np.ndarray, case_id: str, cache_key: str, payload: Mapping[str, Any], cache_hit: bool, labels_visible: bool
    ) -> AeroEvaluation:
        samples = [
            AlphaSample(
                alpha_deg=float(item.get("alpha_deg", 0.0)),
                cltot=float(item.get("CLtot", 0.0)),
                cdi=float(item.get("CDi", 0.0)),
                cdo=float(item.get("CDo", 0.0)),
                cdtot=float(item.get("CDtot", 0.0)),
                cm=tuple(float(v) for v in (item.get("CM") or (0.0, 0.0, 0.0))),
                converged=bool(item.get("converged", True)),
            )
            for item in payload.get("alpha_samples") or ()
        ]
        cm = payload.get("CM")
        return self._evaluation(
            vector=vector,
            case_id=case_id,
            record_status=str(payload.get("record_status", RECORD_SOLVED_VALID)),
            status=str(payload.get("status", STATUS_VALID)),
            physical_solver_starts=0,
            simulated_solver_starts=0,
            cache_hit=bool(cache_hit),
            cache_key=cache_key,
            labels_visible=bool(labels_visible),
            alpha_deg=payload.get("alpha_deg"),
            CLtot=payload.get("CLtot"),
            CDi=payload.get("CDi"),
            CDtot=payload.get("CDtot"),
            CDo=payload.get("CDo"),
            CM=None if cm is None else tuple(float(v) for v in cm),
            L_N=payload.get("L_N"),
            D_i_N=payload.get("D_i_N"),
            Sref_m2=payload.get("Sref_m2"),
            lift_rel_error=payload.get("lift_rel_error"),
            alpha_samples=samples,
            refines_used=int(payload.get("refines_used", 0) or 0),
            attempt_refs=(),
            solver_config_sha256=str(payload.get("solver_config_sha256", self.task.solver_config_sha256)),
            geometry_sha256=str(payload.get("geometry_sha256", "")),
            geometry_source=str(payload.get("geometry_source", "")),
            wall_s=0.0,
            mesh_family=str(payload.get("mesh_family", "")),
            mesh_nodes=int(payload.get("mesh_nodes", 0) or 0),
            mesh_elements=int(payload.get("mesh_elements", 0) or 0),
            normalized_geometry_hash=str(payload.get("normalized_geometry_hash", "")),
            vspgeom_sha256=str(payload.get("vspgeom_sha256", "")),
            notes="same_run_cache_hit" if cache_hit else "",
        )

    def _record(self, evaluation: AeroEvaluation) -> AeroEvaluation:
        self.history.append(evaluation)
        if self.recorder is not None:
            self.recorder.record_evaluation(evaluation)
        return evaluation

    def _invalid_evaluation(self, vector: np.ndarray, case_id: str, issues: Sequence[str], *, cache_key: str = "") -> AeroEvaluation:
        return self._evaluation(
            vector=vector,
            case_id=case_id,
            record_status=RECORD_GEOMETRY_INVALID,
            status=STATUS_INVALID,
            physical_solver_starts=0,
            simulated_solver_starts=0,
            cache_hit=False,
            cache_key=cache_key,
            labels_visible=False,
            alpha_deg=None, CLtot=None, CDi=None, CDtot=None, CDo=None, CM=None,
            L_N=None, D_i_N=None, Sref_m2=None, lift_rel_error=None,
            alpha_samples=(), refines_used=0, attempt_refs=(),
            solver_config_sha256=self.task.solver_config_sha256,
            geometry_sha256="", geometry_source="",
            wall_s=0.0,
            error_code="DESIGN_INVALID",
            error_message="; ".join(str(item) for item in issues),
        )

    # -- main -----------------------------------------------------------
    def evaluate(
        self,
        x12: Sequence[float],
        *,
        case_index: Optional[int] = None,
        case_id: Optional[str] = None,
        meta: Optional[Mapping[str, Any]] = None,
    ) -> AeroEvaluation:
        _ = meta or {}
        self._case_counter += 1
        if case_index is None:
            case_index = self._case_counter
        try:
            vector = np.asarray(x12, dtype=float).reshape(-1)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("x12 must be numeric: %s" % (exc,))
        if vector.size != 12:
            raise ValueError("x12 must have 12 entries, got %d" % vector.size)
        d_hash = compute_design_hash(vector)
        x12_canonical = canonical_x12(vector)
        key = self.cache_key(x12_canonical)
        case_id = str(case_id or ("%s-c%04d-%s" % (self.run_id, int(case_index), d_hash[:8])))

        issues = validate_x12(self.design_space, vector)
        if issues:
            evaluation = self._invalid_evaluation(vector, case_id, issues, cache_key=key)
            self.ledger.register_evaluation(cache_hit=False, started=False, valid=False)
            self.ledger.register_invalid_design()
            return self._record(evaluation)

        if self.cache is not None:
            if self.backend == BACKEND_REAL:
                # E6-GAP-01: a REAL label is only reusable for the mesh family and
                # normalised geometry it was measured on. A unique in-run variant of
                # this design is a paid label; if the design crossed families
                # (multiple variants) it must be re-measured, never mixed.
                self.cache.guard_run_scope(self.run_id)
                variants = self.cache.lookup_design_scoped(key, self.run_id)
                if len(variants) == 1:
                    variant = variants[0]
                    evaluation = self._cache_hit_evaluation(
                        vector=vector,
                        case_id=case_id,
                        cache_key=str(variant["key"]),
                        payload=variant["payload"],
                        cache_hit=True,
                        labels_visible=True,
                    )
                    self.ledger.register_evaluation(cache_hit=True, started=False, valid=(evaluation.status == STATUS_VALID))
                    return self._record(evaluation)
            else:
                scoped = self.cache.lookup_scoped(key, self.run_id)
                if scoped is not None:
                    evaluation = self._cache_hit_evaluation(
                        vector=vector, case_id=case_id, cache_key=key, payload=scoped, cache_hit=True, labels_visible=True
                    )
                    self.ledger.register_evaluation(cache_hit=True, started=False, valid=(evaluation.status == STATUS_VALID))
                    return self._record(evaluation)
            _foreign = self.cache.foreign_design_entry(key, self.run_id) or self.cache.foreign_entry(key, self.run_id)
            if _foreign is not None:
                # A foreign (other run/arm) entry exists; its numbers must NOT be
                # returned and this run pays its own solver start below.
                pass

        try:
            physical_sref = sref_from_physical(self._physical(vector))
        except Exception:  # noqa: BLE001
            physical_sref = None

        started = utc_now()
        clock = time.perf_counter()
        probes: List[ProbeResult] = []
        match = None
        refines_used = 0
        try:
            primary = self._collect(vector, self.task.alpha_primary_deg, case_id, phase="primary")
            probes.extend(primary)
            samples = [sample for probe in probes for sample in probe.samples]
            match = self._match(samples, physical_sref)
            primary_launches = sum(probe.launches for probe in probes)
            if (
                not match.converged
                and int(self.task.max_refine_sweeps) > 0
                and self.supports_alpha_sweep
                and self.supports_refine_sweep
                and primary_launches + 1 <= self.max_launches_per_design
                and self.ledger.remaining_starts > 0
            ):
                refine = self._collect(vector, self.task.alpha_refine_deg, case_id, phase="refine")
                probes.extend(refine)
                refines_used = 1
                samples = [sample for probe in probes for sample in probe.samples]
                match = self._match(samples, physical_sref)
        except SolverBudgetExceeded:
            raise
        except AccountingViolation:
            raise
        except Exception as exc:  # noqa: BLE001 - backend failure -> FAIL record
            wall_s = time.perf_counter() - clock
            evaluation = self._evaluation(
                vector=vector, case_id=case_id,
                record_status=RECORD_SOLVER_FAILED, status=STATUS_FAIL,
                physical_solver_starts=0, simulated_solver_starts=0,
                cache_hit=False, cache_key=key, labels_visible=False,
                alpha_deg=None, CLtot=None, CDi=None, CDtot=None, CDo=None, CM=None,
                L_N=None, D_i_N=None, Sref_m2=None, lift_rel_error=None,
                alpha_samples=(), refines_used=0, attempt_refs=(),
                solver_config_sha256=self.task.solver_config_sha256,
                geometry_sha256="", geometry_source="", wall_s=wall_s,
                error_code="EVALUATOR_ERROR", error_message="%s: %s" % (type(exc).__name__, exc),
            )
            self.ledger.register_evaluation(cache_hit=False, started=False, valid=False)
            return self._record(evaluation)

        wall_s = time.perf_counter() - clock
        launches = sum(probe.launches for probe in probes)
        simulated = launches if self.backend != BACKEND_REAL else 0
        physical = launches if self.backend == BACKEND_REAL else 0
        attempt_refs = [ref for probe in probes for ref in probe.attempt_refs]
        samples = [sample for probe in probes for sample in probe.samples]
        solver_config_sha256 = next((probe.solver_config_sha256 for probe in probes if probe.solver_config_sha256), self.task.solver_config_sha256)
        geometry_sha256 = next((probe.geometry_sha256 for probe in probes if probe.geometry_sha256), "")
        geometry_source = next((probe.geometry_source for probe in probes if probe.geometry_source), "")
        mesh_family = next((probe.mesh_family for probe in probes if probe.mesh_family), "")
        mesh_nodes = next((int(probe.mesh_nodes) for probe in probes if probe.mesh_nodes), 0)
        mesh_elements = next((int(probe.mesh_elements) for probe in probes if probe.mesh_elements), 0)
        normalized_geometry_hash = next((probe.normalized_geometry_hash for probe in probes if probe.normalized_geometry_hash), "")
        vspgeom_sha256 = next((probe.vspgeom_sha256 for probe in probes if probe.vspgeom_sha256), "")
        # REAL entries are keyed by mesh family + normalised geometry; mock/replay
        # keep the design key so their artefacts stay comparable across runs.
        record_cache_key = (
            self.cache_key(
                x12_canonical,
                mesh_family=mesh_family,
                normalized_geometry_hash=normalized_geometry_hash,
            )
            if self.backend == BACKEND_REAL
            else key
        )
        probe_statuses = {probe.status for probe in probes}

        if RECORD_GEOMETRY_INVALID in probe_statuses and not samples:
            evaluation = self._evaluation(
                vector=vector, case_id=case_id,
                record_status=RECORD_GEOMETRY_INVALID, status=STATUS_INVALID,
                physical_solver_starts=physical, simulated_solver_starts=simulated,
                cache_hit=False, cache_key=record_cache_key, labels_visible=False,
                alpha_deg=None, CLtot=None, CDi=None, CDtot=None, CDo=None, CM=None,
                L_N=None, D_i_N=None, Sref_m2=physical_sref, lift_rel_error=None,
                alpha_samples=samples, refines_used=refines_used, attempt_refs=attempt_refs,
                solver_config_sha256=solver_config_sha256, geometry_sha256=geometry_sha256,
                geometry_source=geometry_source, wall_s=wall_s,
                mesh_family=mesh_family, mesh_nodes=mesh_nodes, mesh_elements=mesh_elements,
                normalized_geometry_hash=normalized_geometry_hash, vspgeom_sha256=vspgeom_sha256,
                error_code="GEOMETRY_INVALID", error_message="A1 geometry invalid",
            )
            self.ledger.register_evaluation(cache_hit=False, started=(launches > 0), valid=False)
            return self._record(evaluation)

        if not samples and probe_statuses and probe_statuses <= {RECORD_NOT_RUN}:
            # A1 P2a budget refusal / fail-closed NOT_RUN: the solver never ran.
            # This is not a design failure, must not be billed, and must not be
            # turned into a synthetic penalty value.
            probe_errors = [dict(item) for probe in probes for item in probe.errors]
            codes = sorted({str(item.get("code", "")) for item in probe_errors if item.get("code")})
            evaluation = self._evaluation(
                vector=vector, case_id=case_id,
                record_status=RECORD_NOT_RUN, status=STATUS_NOT_RUN,
                physical_solver_starts=physical, simulated_solver_starts=simulated,
                cache_hit=False, cache_key=record_cache_key, labels_visible=False,
                alpha_deg=None, CLtot=None, CDi=None, CDtot=None, CDo=None, CM=None,
                L_N=None, D_i_N=None, Sref_m2=physical_sref, lift_rel_error=None,
                alpha_samples=(), refines_used=refines_used, attempt_refs=attempt_refs,
                solver_config_sha256=solver_config_sha256, geometry_sha256=geometry_sha256,
                geometry_source=geometry_source, wall_s=wall_s,
                mesh_family=mesh_family, mesh_nodes=mesh_nodes, mesh_elements=mesh_elements,
                normalized_geometry_hash=normalized_geometry_hash, vspgeom_sha256=vspgeom_sha256,
                error_code=(codes[0] if codes else "NOT_RUN"),
                error_message="solver did not run: %s" % (", ".join(codes) or "NOT_RUN"),
            )
            self.ledger.register_evaluation(cache_hit=False, started=(launches > 0), valid=False)
            return self._record(evaluation)

        if RECORD_SOLVER_FAILED in probe_statuses or not samples:
            status = STATUS_FAIL if RECORD_SOLVER_FAILED in probe_statuses else STATUS_NOT_CONVERGED
            record_status = RECORD_SOLVER_FAILED if status == STATUS_FAIL else RECORD_LIFT_MATCH_FAILED
            evaluation = self._evaluation(
                vector=vector, case_id=case_id,
                record_status=record_status, status=status,
                physical_solver_starts=physical, simulated_solver_starts=simulated,
                cache_hit=False, cache_key=record_cache_key, labels_visible=False,
                alpha_deg=None, CLtot=None, CDi=None, CDtot=None, CDo=None, CM=None,
                L_N=None, D_i_N=None, Sref_m2=physical_sref, lift_rel_error=None,
                alpha_samples=samples, refines_used=refines_used, attempt_refs=attempt_refs,
                solver_config_sha256=solver_config_sha256, geometry_sha256=geometry_sha256,
                geometry_source=geometry_source, wall_s=wall_s,
                mesh_family=mesh_family, mesh_nodes=mesh_nodes, mesh_elements=mesh_elements,
                normalized_geometry_hash=normalized_geometry_hash, vspgeom_sha256=vspgeom_sha256,
                error_code="SOLVER_FAILED" if status == STATUS_FAIL else "LIFT_MATCH_FAILED",
                error_message="probe statuses=%s" % sorted(probe_statuses),
            )
            self.ledger.register_evaluation(cache_hit=False, started=(launches > 0), valid=False)
            return self._record(evaluation)

        match = match or self._match(samples)
        if not match.converged:
            evaluation = self._evaluation(
                vector=vector, case_id=case_id,
                record_status=RECORD_LIFT_MATCH_FAILED, status=STATUS_NOT_CONVERGED,
                physical_solver_starts=physical, simulated_solver_starts=simulated,
                cache_hit=False, cache_key=record_cache_key, labels_visible=False,
                alpha_deg=None, CLtot=None, CDi=None, CDtot=None, CDo=None, CM=None,
                L_N=None, D_i_N=None, Sref_m2=physical_sref, lift_rel_error=match.lift_rel_error,
                alpha_samples=samples, refines_used=refines_used, attempt_refs=attempt_refs,
                solver_config_sha256=solver_config_sha256, geometry_sha256=geometry_sha256,
                geometry_source=geometry_source, wall_s=wall_s,
                mesh_family=mesh_family, mesh_nodes=mesh_nodes, mesh_elements=mesh_elements,
                normalized_geometry_hash=normalized_geometry_hash, vspgeom_sha256=vspgeom_sha256,
                error_code="LIFT_MATCH_FAILED",
                error_message="lift_rel_error=%s method=%s" % (match.lift_rel_error, match.method),
            )
            self.ledger.register_evaluation(cache_hit=False, started=(launches > 0), valid=False)
            return self._record(evaluation)

        sref = float(physical_sref)
        q = float(self.task.q_Pa)
        cltot = float(match.cltot)
        L_n = q * sref * cltot
        D_i_n = q * sref * float(match.cdi)
        evaluation = self._evaluation(
            vector=vector, case_id=case_id,
            record_status=RECORD_MOCK if self.backend == BACKEND_MOCK else RECORD_SOLVED_VALID,
            status=STATUS_VALID,
            physical_solver_starts=physical, simulated_solver_starts=simulated,
            cache_hit=False, cache_key=record_cache_key, labels_visible=True,
            alpha_deg=match.alpha_deg, CLtot=cltot, CDi=match.cdi, CDtot=match.cdtot,
            CDo=match.cdo, CM=match.cm, L_N=L_n, D_i_N=D_i_n, Sref_m2=sref,
            lift_rel_error=match.lift_rel_error,
            alpha_samples=samples, refines_used=refines_used, attempt_refs=attempt_refs,
            solver_config_sha256=solver_config_sha256, geometry_sha256=geometry_sha256,
            geometry_source=geometry_source, wall_s=wall_s,
            mesh_family=mesh_family, mesh_nodes=mesh_nodes, mesh_elements=mesh_elements,
            normalized_geometry_hash=normalized_geometry_hash, vspgeom_sha256=vspgeom_sha256,
        )
        self.ledger.register_evaluation(cache_hit=False, started=(launches > 0), valid=True)
        if self.cache is not None:
            self.cache.store(
                record_cache_key,
                self.run_id,
                self._cache_payload(evaluation),
                design_key=key,
                mesh_family=mesh_family,
                normalized_geometry_hash=normalized_geometry_hash,
                vspgeom_sha256=vspgeom_sha256,
            )
        if self.label_store is not None:
            try:
                g = geometric_constraint_g(self.design_space, vector)
                margin = -constraint_violation_total(g)
            except Exception:  # noqa: BLE001
                margin = 0.0
            self.label_store.add(vector, D_i_n, constraint_margin=margin, design_hash=d_hash)
        return self._record(evaluation)

    def _match(self, samples: Sequence[AlphaSample], sref: Optional[float]) -> Any:
        reference_area = self.task.sref_baseline_m2 if sref is None else float(sref)
        return interpolate_lift_match(
            samples,
            cl_target=self.task.cl_required(reference_area),
            lift_tol_rel=float(self.task.lift_tol_rel),
        )

    # -- backend hooks --------------------------------------------------
    @abc.abstractmethod
    def _probe_batch(self, vector: np.ndarray, alphas: Sequence[float], case_id: str, *, phase: str = "primary") -> ProbeResult:
        raise NotImplementedError

    def _probe_single(self, vector: np.ndarray, alpha_deg: float, case_id: str, *, phase: str = "primary") -> ProbeResult:
        raise NotImplementedError("backend does not support per-alpha probing")


# ---------------------------------------------------------------------------
# MOCK
# ---------------------------------------------------------------------------

class MockLiftMatchEvaluator(BaseLiftMatchEvaluator):
    """Deterministic synthetic aero model. NEVER real evidence."""

    backend = BACKEND_MOCK
    source_kind = "MOCK"
    physical_validation_status = "NOT_VALIDATED"
    supports_alpha_sweep = True
    requires_starts = True

    def _rng(self, vector: np.ndarray) -> np.random.Generator:
        seed = int(compute_design_hash(vector)[:8], 16) ^ int(self.seed)
        return np.random.default_rng(seed)

    def _mock_status(self, vector: np.ndarray, alpha_deg: float) -> Optional[str]:
        d_hash = compute_design_hash(vector)
        if d_hash in self.fail_design_hashes:
            return RECORD_SOLVER_FAILED
        if self.failure_callable is not None:
            try:
                return self.failure_callable(vector, float(alpha_deg))
            except Exception:  # noqa: BLE001
                return RECORD_SOLVER_FAILED
        return None

    def _sample_at(self, vector: np.ndarray, alpha_deg: float) -> AlphaSample:
        u = np.clip(vector, 0.0, 1.0)
        physical = self._physical(vector)
        ar = float(physical.get("aspect_ratio", 1.83))
        area = float(physical.get("wing_area", 358.25))
        sweep = float(physical.get("sweep_1", 67.0))
        span2 = float(physical.get("span_location_2", 0.48))
        cl0 = 0.05 + 0.30 * (span2 - 0.480469) + 0.02 * (u[7] - 0.5)
        slope = 0.030 * (1.83 / ar) ** 0.35 * (1.0 - 0.004 * (sweep - 67.0)) + 0.002 * (u[8] - 0.5)
        cl = cl0 + slope * alpha_deg
        k = (
            0.26
            * (1.83 / ar) ** 1.10
            * (1.0 + 0.0035 * (sweep - 67.0))
            * (1.0 + 0.15 * (u[6] - 0.5))
            * (1.0 + 0.10 * (u[9] - 0.5))
        )
        cdi = k * cl * cl + 0.00025 * (alpha_deg / 10.0) ** 2 + 0.00005 * (u[10] - 0.5) ** 2
        cdo = 0.010 + 0.002 * (u[11] - 0.5)
        cm = (0.02 - 0.01 * (span2 - 0.5), 0.0, 0.0)
        rng = self._rng(vector)
        if self.noise_rel > 0.0:
            cl *= 1.0 + self.noise_rel * float(rng.normal())
            cdi *= 1.0 + self.noise_rel * float(rng.normal())
        _ = area
        return AlphaSample(alpha_deg=float(alpha_deg), cltot=float(cl), cdi=float(cdi), cdo=float(cdo), cdtot=float(cdi + cdo), cm=cm)

    def _mock_geometry_sha256(self, vector: np.ndarray) -> str:
        return sha256_bytes(("MOCK-GEOMETRY|" + canonical_x12(vector)).encode("utf-8"))

    def _write_mock_attempt(
        self, *, vector: np.ndarray, case_id: str, status: str, wall_s: float, alpha_deg: Optional[float], starts: int = 1
    ) -> str:
        attempt_id, sequence = self._next_attempt_id(case_id)
        attempt = SolverAttempt(
            attempt_id=attempt_id,
            batch_id=self.batch_id,
            run_id=self.run_id,
            case_id=case_id,
            sequence=sequence,
            task_id=self.task.task_id,
            design_hash=compute_design_hash(vector),
            x12_canonical=canonical_x12(vector),
            geometry_source="MOCK_GEOMETRY",
            geometry_sha256=self._mock_geometry_sha256(vector),
            solver_version="MOCK-0",
            solver_config_hash=self.task.solver_config_sha256,
            argv=("mock://vspaero", "--alpha", "%.6f" % (alpha_deg or 0.0)),
            start_ts_utc=utc_now(),
            end_ts_utc=utc_now(),
            wall_s=float(wall_s),
            exit_code=0,
            status=str(status),
            physical_solver_starts=0,
            simulated_solver_starts=int(starts),
            backend=BACKEND_MOCK,
            notes="MOCK simulated solver start; not real evidence; alpha=%.6f; phase-alpha launch" % (alpha_deg or 0.0),
        )
        self.ledger.record_attempt(attempt)
        return attempt_id

    def _probe_batch(self, vector: np.ndarray, alphas: Sequence[float], case_id: str, *, phase: str = "primary") -> ProbeResult:
        clock_start = time.perf_counter()
        samples: List[AlphaSample] = []
        forced = None
        for alpha in alphas:
            status = self._mock_status(vector, float(alpha))
            if status is not None:
                forced = status
                break
            samples.append(self._sample_at(vector, float(alpha)))
        wall_s = time.perf_counter() - clock_start
        alpha_ref = float(alphas[0]) if alphas else 0.0
        attempt_id = self._write_mock_attempt(
            vector=vector, case_id=case_id,
            status=("FAIL" if forced else "SIMULATED_VALID"),
            wall_s=wall_s, alpha_deg=alpha_ref, starts=1,
        )
        return ProbeResult(
            samples=samples,
            launches=1,
            status=(forced or RECORD_MOCK),
            attempt_refs=[attempt_id],
            solver_config_sha256=self.task.solver_config_sha256,
            geometry_sha256=self._mock_geometry_sha256(vector),
            geometry_source="MOCK_GEOMETRY",
            wall_s=wall_s,
            argv=["mock://vspaero", "--alphas", ",".join("%.3f" % a for a in alphas)],
            notes="MOCK sweep; phase=%s" % phase,
        )

    def _probe_single(self, vector: np.ndarray, alpha_deg: float, case_id: str, *, phase: str = "primary") -> ProbeResult:
        clock_start = time.perf_counter()
        forced = self._mock_status(vector, float(alpha_deg))
        samples = [] if forced else [self._sample_at(vector, float(alpha_deg))]
        wall_s = time.perf_counter() - clock_start
        attempt_id = self._write_mock_attempt(
            vector=vector, case_id=case_id, status=("FAIL" if forced else "SIMULATED_VALID"),
            wall_s=wall_s, alpha_deg=float(alpha_deg), starts=1,
        )
        return ProbeResult(
            samples=samples,
            launches=1,
            status=(forced or RECORD_MOCK),
            attempt_refs=[attempt_id],
            solver_config_sha256=self.task.solver_config_sha256,
            geometry_sha256=self._mock_geometry_sha256(vector),
            geometry_source="MOCK_GEOMETRY",
            wall_s=wall_s,
            argv=["mock://vspaero", "--alpha", "%.6f" % float(alpha_deg)],
            notes="MOCK single-alpha; phase=%s" % phase,
        )


# ---------------------------------------------------------------------------
# REPLAY
# ---------------------------------------------------------------------------

class ReplayEvaluator(BaseLiftMatchEvaluator):
    """Replay historical records by design_hash. Never launches a solver."""

    backend = BACKEND_REPLAY
    source_kind = "REPLAY_ARCHIVE"
    physical_validation_status = "NOT_VALIDATED"
    supports_alpha_sweep = True
    requires_starts = False

    def __init__(self, design_space: Any, task: Any, ledger: SolverStartLedger, *, records: Any = None, records_path: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(design_space, task, ledger, **kwargs)
        self._records: Dict[str, Dict[str, Any]] = {}
        if records_path is not None:
            for row in read_jsonl(records_path):
                self._records[str(row.get("design_hash", ""))] = dict(row)
        if records is not None:
            for row in records:
                self._records[str(row.get("design_hash", ""))] = dict(row)

    def _samples_from_record(self, row: Mapping[str, Any]) -> List[AlphaSample]:
        samples: List[AlphaSample] = []
        if row.get("alpha_samples"):
            for item in row["alpha_samples"]:
                samples.append(
                    AlphaSample(
                        alpha_deg=float(item.get("alpha_deg", 0.0)),
                        cltot=float(item.get("CLtot", 0.0)),
                        cdi=float(item.get("CDi", 0.0)),
                        cdo=float(item.get("CDo", 0.0)),
                        cdtot=float(item.get("CDtot", 0.0)),
                        cm=tuple(float(v) for v in (item.get("CM") or (0.0, 0.0, 0.0))),
                        converged=bool(item.get("converged", True)),
                    )
                )
            return samples
        results = row.get("results") or {}
        alphas = list(results.get("alpha_deg") or ())
        cltot = list(results.get("cltot") or ())
        cdi = list(results.get("cdi") or ())
        cdo = list(results.get("cdo") or ())
        cdtot = list(results.get("cdtot") or ())
        for index, alpha in enumerate(alphas):
            samples.append(
                AlphaSample(
                    alpha_deg=float(alpha),
                    cltot=float(cltot[index]) if index < len(cltot) else 0.0,
                    cdi=float(cdi[index]) if index < len(cdi) else 0.0,
                    cdo=float(cdo[index]) if index < len(cdo) else 0.0,
                    cdtot=float(cdtot[index]) if index < len(cdtot) else 0.0,
                )
            )
        return samples

    def _probe_batch(self, vector: np.ndarray, alphas: Sequence[float], case_id: str, *, phase: str = "primary") -> ProbeResult:
        d_hash = compute_design_hash(vector)
        row = self._records.get(d_hash)
        if row is None:
            return ProbeResult(samples=[], launches=0, status=RECORD_NOT_RUN, notes="replay record missing")
        samples = self._samples_from_record(row)
        status = str(row.get("record_status") or row.get("status") or RECORD_SOLVED_VALID)
        if status not in (RECORD_SOLVED_VALID, RECORD_MOCK):
            status = RECORD_SOLVED_VALID if samples else RECORD_NOT_RUN
        return ProbeResult(
            samples=samples,
            launches=0,
            status=status,
            solver_config_sha256=str(row.get("solver_config_hash") or self.task.solver_config_sha256),
            geometry_sha256=str(row.get("geometry_sha256") or ""),
            geometry_source="REPLAY_ARCHIVE",
            notes="replay phase=%s" % phase,
        )

    def _probe_single(self, vector: np.ndarray, alpha_deg: float, case_id: str, *, phase: str = "primary") -> ProbeResult:
        return self._probe_batch(vector, [alpha_deg], case_id, phase=phase)


# ---------------------------------------------------------------------------
# REAL (A1 adapter, fail-closed)
# ---------------------------------------------------------------------------

class RealVspaeroAdapter(BaseLiftMatchEvaluator):
    """Thin adapter over A1 dreal001.geometry.evaluator.AeroEvaluator.evaluate.

    Constructing this adapter without a callable evaluate_fn or without an
    approved approval.json raises RealSolverNotAuthorized. No vspaero process is
    ever launched from this module; A1 owns the process and its ledger rows.
    """

    backend = BACKEND_REAL
    source_kind = "REAL_VSPAERO"
    physical_validation_status = "NOT_VALIDATED"
    supports_alpha_sweep = True
    #: A1 EVALUATOR_API v1.0 runs the fixed 7-alpha grid inside one launch and
    #: exposes no alpha-override; a refine launch would repeat the same grid, so
    #: A2 does not spend a second start until A1 publishes that entry point
    #: (gap reported to Lead/A1). The pre-registered max stays 2.
    supports_refine_sweep = False
    requires_starts = True

    def __init__(
        self,
        design_space: Any,
        task: Any,
        ledger: SolverStartLedger,
        *,
        evaluate_fn: Optional[Callable[..., Mapping[str, Any]]] = None,
        approval: Optional[Mapping[str, Any]] = None,
        external_attempts_path: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        if evaluate_fn is None or not callable(evaluate_fn):
            raise RealSolverNotAuthorized(
                "REAL_VSPAERO backend needs A1 AeroEvaluator.evaluate callable; "
                "P0/P1 gate not passed, real solver starts stay at 0"
            )
        if not approval or not bool(approval.get("approved")):
            raise RealSolverNotAuthorized(
                "REAL_VSPAERO backend needs an approved approval.json (approved=true); none supplied"
            )
        if int(approval.get("max_starts", 0) or 0) <= 0:
            raise RealSolverNotAuthorized("approval.json max_starts must be positive")
        super().__init__(design_space, task, ledger, **kwargs)
        if self.cache is not None:
            # Lead m00426: REAL formal batches must never reuse another run's
            # cache; the cache fails closed on foreign entries.
            self.cache.forbid_cross_run_reuse = True
        self.evaluate_fn = evaluate_fn
        self.evaluate_fn_kind = "A1_EVALUATOR_V1_0"
        #: P2a guarded callable stamps record["p2a_evaluator"]; reconciled below.
        self.p2a_last_accounting: Optional[Dict[str, Any]] = None
        self.p2a_calls = 0
        self.p2a_starts_reported = 0
        self.p2a_budget_exhausted = False
        self.approval = dict(approval)
        if external_attempts_path is not None:
            self.ledger.attempts_path = Path(external_attempts_path)
        if self.ledger.attempts_path is None:
            raise RealSolverNotAuthorized("REAL_VSPAERO needs A1 solver_attempts.jsonl path for verification")
        if str(approval.get("batch_id", "")) and str(approval.get("batch_id")) != self.batch_id:
            raise RealSolverNotAuthorized("approval batch_id %r does not match run batch %r" % (approval.get("batch_id"), self.batch_id))

    def _a1_x12(self, vector: np.ndarray) -> List[float]:
        """Unit-box design -> A1 physical x12 in the frozen W01..W10,V01,V02 order.

        A1 EVALUATOR_API v1.0 consumes physical values only (F01-F03 are
        injected inside A1); passing the optimizer's unit fractions would build
        the wrong geometry, so this conversion is fail-closed.
        """
        physical = self._physical(vector)
        names = list(getattr(self.design_space, "names", ()) or ())
        if len(names) != DIMENSION:
            raise AccountingViolation(
                "design space must expose %d ordered names to build A1 x12, got %d"
                % (DIMENSION, len(names))
            )
        return [float(physical[str(name)]) for name in names]

    def _call_a1(self, vector: np.ndarray, case_id: str, phase: str) -> Tuple[Mapping[str, Any], List[float]]:
        a1_x12 = self._a1_x12(vector)
        meta = {"arm": self.arm_id, "seed": self.seed, "phase": phase, "batch_id": self.batch_id, "run_id": self.run_id}
        try:
            record = self.evaluate_fn(a1_x12, case_id=case_id, meta=meta)
        except TypeError:
            record = self.evaluate_fn(a1_x12)
        if not isinstance(record, Mapping):
            raise TypeError("A1 evaluate_fn must return a mapping, got %r" % (type(record),))
        return record, a1_x12

    #: A1 P2a error code for a budget refusal that never reached the solver.
    P2A_BUDGET_EXHAUSTED_CODE = "SOLVER_BUDGET_EXHAUSTED"

    def _p2a_accounting(
        self,
        record: Mapping[str, Any],
        *,
        physical_starts: int,
        status: str,
        error_codes: Sequence[str],
    ) -> Optional[Dict[str, Any]]:
        """Reconcile A1's P2a budget stamp against the record's billed starts.

        A P2a record carries record["p2a_evaluator"] =
        {evaluate_id, schema_version, starts_before, starts_after,
        approval_max_starts}. The delta must equal physical_solver_starts and the
        post-call counter must stay inside the approved cap; anything else is an
        accounting contradiction and fails closed. The stamp is optional only for
        the older v1.0 evaluator route (no P2a wrapper).
        """
        block = record.get("p2a_evaluator")
        if block is None:
            if status == RECORD_NOT_RUN and self.P2A_BUDGET_EXHAUSTED_CODE in error_codes:
                self.p2a_budget_exhausted = True
            return None
        if not isinstance(block, Mapping):
            raise AccountingViolation(
                "A1 P2a record has non-mapping p2a_evaluator %r" % (type(block),)
            )
        missing = [
            key
            for key in ("starts_before", "starts_after", "approval_max_starts")
            if key not in block
        ]
        if missing:
            raise AccountingViolation(
                "A1 P2a p2a_evaluator lacks required keys %s: %r" % (missing, dict(block))
            )
        try:
            before = int(block["starts_before"])
            after = int(block["starts_after"])
            cap = int(block["approval_max_starts"])
        except (TypeError, ValueError) as exc:
            raise AccountingViolation(
                "A1 P2a p2a_evaluator has non-integer counters: %r" % (dict(block),)
            ) from exc
        if before < 0 or after < before or cap <= 0:
            raise AccountingViolation(
                "A1 P2a p2a_evaluator counters are inconsistent: before=%d after=%d cap=%d"
                % (before, after, cap)
            )
        delta = after - before
        if delta != int(physical_starts):
            raise AccountingViolation(
                "A1 P2a p2a_evaluator delta %d does not match record physical_solver_starts %d"
                % (delta, int(physical_starts))
            )
        if after > cap:
            raise AccountingViolation(
                "A1 P2a p2a_evaluator starts_after %d exceeds approved cap %d"
                % (after, cap)
            )
        approved = int(self.approval.get("max_starts", 0) or 0)
        if approved and cap != approved:
            raise AccountingViolation(
                "A1 P2a approval_max_starts %d does not match A2 approval max_starts %d"
                % (cap, approved)
            )
        schema_version = str(block.get("schema_version", "") or "")
        if schema_version and schema_version != P2A_EVALUATE_SCHEMA:
            raise AccountingViolation(
                "A1 P2a p2a_evaluator schema_version %r is not %r"
                % (schema_version, P2A_EVALUATE_SCHEMA)
            )
        accounting = {
            "evaluate_id": str(block.get("evaluate_id", "") or ""),
            "schema_version": schema_version,
            "starts_before": before,
            "starts_after": after,
            "delta": delta,
            "approval_max_starts": cap,
            "budget_exhausted": bool(
                status == RECORD_NOT_RUN
                and self.P2A_BUDGET_EXHAUSTED_CODE in error_codes
            ),
        }
        self.p2a_last_accounting = dict(accounting)
        self.p2a_calls += 1
        self.p2a_starts_reported += max(0, delta)
        if accounting["budget_exhausted"]:
            self.p2a_budget_exhausted = True
        return accounting

    def _probe_batch(self, vector: np.ndarray, alphas: Sequence[float], case_id: str, *, phase: str = "primary") -> ProbeResult:
        started = utc_now()
        clock = time.perf_counter()
        record, a1_x12 = self._call_a1(vector, case_id, phase)
        wall_s = time.perf_counter() - clock
        schema_version = str(record.get("schema_version") or "")
        if schema_version and schema_version != SCHEMA_VERSION:
            raise AccountingViolation(
                "A1 record schema_version %r is not %r" % (schema_version, SCHEMA_VERSION)
            )
        status = str(record.get("status", ""))
        backend = str(record.get("backend", ""))
        if backend and backend != BACKEND_REAL:
            raise AccountingViolation("A1 record backend %r is not %r" % (backend, BACKEND_REAL))
        if status not in (RECORD_SOLVED_VALID, RECORD_SOLVER_FAILED, RECORD_GEOMETRY_INVALID, RECORD_LIFT_MATCH_FAILED, RECORD_NOT_RUN):
            raise AccountingViolation("A1 record has unknown status %r" % (status,))
        solver = record.get("solver") or {}
        # A1 contract: record.physical_solver_starts and
        # record.solver.physical_solver_starts carry the same value. Accept
        # either location but never a contradiction (never bill alpha rows).
        top_starts = record.get("physical_solver_starts", None)
        solver_starts = solver.get("physical_solver_starts", None)
        if top_starts is not None and solver_starts is not None and int(top_starts) != int(solver_starts):
            raise AccountingViolation(
                "A1 record contradicting physical_solver_starts: top=%r solver=%r"
                % (top_starts, solver_starts)
            )
        starts = int(solver_starts if solver_starts is not None else (top_starts or 0))
        internal_cases = int(
            solver.get("internal_solver_cases", record.get("internal_solver_cases", 0)) or 0
        )
        geometry = record.get("geometry") or {}
        # A1 E6-GAP-01: thin-mesh family is a covariate (e.g. "483/418" vs "543/472");
        # records must carry it so cross-family numbers are never silently compared.
        mesh = record.get("mesh") or geometry.get("mesh") or {}
        mesh_nodes = int(mesh.get("nodes", geometry.get("mesh_nodes", geometry.get("nodes", 0))) or 0)
        mesh_elements = int(mesh.get("elements", geometry.get("mesh_elements", geometry.get("elements", 0))) or 0)
        mesh_family = str(
            record.get("mesh_family")
            or mesh.get("family")
            or geometry.get("mesh_family")
            or ("%d/%d" % (mesh_nodes, mesh_elements) if mesh_nodes and mesh_elements else "")
        )
        # Cache isolation for REAL labels: family + normalised geometry identify
        # the mesh this reading belongs to; raw .vspgeom sha is provenance only.
        normalized_geometry_hash = str(
            record.get("normalized_geometry_hash")
            or mesh.get("normalized_geometry_hash")
            or geometry.get("normalized_geometry_hash")
            # EVALUATOR_API v1.0 defines normalized_geometry_hash as the sorted
            # node/face canonical mesh sha; accept the canonical field name too.
            or geometry.get("canonical_mesh_sha256")
            or ""
        )
        vspgeom_sha256 = str(
            record.get("vspgeom_sha256")
            or mesh.get("vspgeom_sha256")
            or geometry.get("vspgeom_sha256")
            or ""
        )
        # Lead m00426: a REAL label must never be keyed by design hash alone. A1
        # must report the thin-mesh family and a normalised-geometry hash, else
        # the reading is not attributable to one mesh and cannot be cached or
        # compared (E6-GAP-01 non-determinism). Fail closed instead of guessing.
        if status == RECORD_SOLVED_VALID and not (mesh_family and normalized_geometry_hash):
            raise AccountingViolation(
                "A1 REAL record lacks mesh covariates (mesh_family=%r normalized_geometry_hash=%r); "
                "REAL labels cannot be keyed or compared across mesh families" % (mesh_family, normalized_geometry_hash)
            )
        results = record.get("results") or {}
        samples: List[AlphaSample] = []
        alphas_record = list(results.get("alpha_deg") or ())
        cltot = list(results.get("cltot") or ())
        cdi = list(results.get("cdi") or ())
        cdo = list(results.get("cdo") or ())
        cdtot = list(results.get("cdtot") or ())
        cm_y = list(results.get("cmy") or ())
        for index, alpha in enumerate(alphas_record):
            samples.append(
                AlphaSample(
                    alpha_deg=float(alpha),
                    cltot=float(cltot[index]) if index < len(cltot) else 0.0,
                    cdi=float(cdi[index]) if index < len(cdi) else 0.0,
                    cdo=float(cdo[index]) if index < len(cdo) else 0.0,
                    cdtot=float(cdtot[index]) if index < len(cdtot) else 0.0,
                    cm=(0.0, float(cm_y[index]) if index < len(cm_y) else 0.0, 0.0),
                )
            )
        attempt_refs = [str(item) for item in (record.get("attempt_ids") or solver.get("attempt_ids") or ())]
        if not attempt_refs and starts > 0:
            attempt_refs = ["%s-a%02d" % (case_id, index + 1) for index in range(starts)]
        errors = [dict(item) for item in (record.get("errors") or ())]
        error_codes = [str(item.get("code", "")) for item in errors if item.get("code")]
        p2a = self._p2a_accounting(
            record, physical_starts=starts, status=status, error_codes=error_codes
        )
        p2a_note = ""
        if p2a is not None:
            p2a_note = " p2a_starts=%d->%d cap=%d%s" % (
                p2a["starts_before"],
                p2a["starts_after"],
                p2a["approval_max_starts"],
                " BUDGET_EXHAUSTED" if p2a["budget_exhausted"] else "",
            )
        if starts > 0:
            design_block = record.get("design") or {}
            # A1 bills physical starts keyed by its own physical-x12 design_hash
            # (16 hex); A2's unit-box design hash is a different namespace.
            a1_design_hash = str(design_block.get("design_hash") or compute_design_hash(a1_x12))
            self.ledger.verify_external_attempts(design_hash=a1_design_hash, expected_starts=starts)
        return ProbeResult(
            samples=samples,
            launches=starts,
            status=status,
            attempt_refs=attempt_refs,
            solver_config_sha256=str(solver.get("solver_config_sha256") or self.task.solver_config_sha256),
            geometry_sha256=str(geometry.get("geometry_sha256") or ""),
            geometry_source="A1_OPENVSP_GEOMETRY",
            mesh_family=mesh_family,
            mesh_nodes=mesh_nodes,
            mesh_elements=mesh_elements,
            normalized_geometry_hash=normalized_geometry_hash,
            vspgeom_sha256=vspgeom_sha256,
            wall_s=wall_s,
            argv=[str(item) for item in (solver.get("command") or ())],
            raw_artifacts=[dict(item) for item in (record.get("raw_artifacts") or ())],
            errors=errors,
            internal_cases=internal_cases,
            notes="A1 record %s phase=%s started=%s design_hash=%s internal_cases=%d%s"
            % (
                status,
                phase,
                started,
                str((record.get("design") or {}).get("design_hash", "")),
                internal_cases,
                p2a_note,
            ),
        )

    def _probe_single(self, vector: np.ndarray, alpha_deg: float, case_id: str, *, phase: str = "primary") -> ProbeResult:
        return self._probe_batch(vector, [alpha_deg], case_id, phase=phase)
