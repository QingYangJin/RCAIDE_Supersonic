"""A1 real-solver lift-match evaluator for A2 (dreal001.aero_eval.v1).

This module is the A1 side of the A2 contract:

    AeroEvaluator.evaluate(x12, case_id=..., meta=...) -> Mapping

A2's RealVspaeroAdapter reads these keys (see
research/concorde_metaopt/dreal001/optimizers/evaluators.py):

    status / backend / solver.physical_solver_starts / solver.command /
    solver.solver_config_sha256 / geometry.geometry_sha256 /
    results.alpha_deg|cltot|cdi|cdo|cdtot|cmy / attempt_ids /
    raw_artifacts / errors

A1 guarantees, in this order:

1. GEOMETRY IS REBUILT FROM x12 ON EVERY EVALUATION through the canonical path
   openvsp_model._geometry_from_design_vector.  Copying a template four-piece
   file is refused (TemplateCopyDetected) and recorded as a fail-closed error.
2. Zero-physical preflight uses VSPAEROSweep StopBeforeRun=1 only: no
   vspaero.exe process is ever launched in this mode (status NOT_RUN, starts 0).
3. A real launch is possible ONLY when an approved approval.json is supplied
   AND allow_physical_starts=True AND a spawn callable is injected.  Every
   attempt is booked with attempt_id, timeout and argv, and the record carries
   physical_solver_starts=1.
4. Cache key = sha256(canonical x12 || task_spec_sha256 || solver_config_hash)
   (governance section 6).  A cache hit returns physical_solver_starts=0 and
   cache_hit=True; the label is only ever exposed for a billed launch.

The record never contains fuel_burn_kg and never claims physical validation:
physical_validation_status stays NOT_VALIDATED, objective is D_i only.

CLI contract test (zero physical):

    <python> -m research.concorde_metaopt.dreal001.geometry.evaluator \
        --run-dir <dir> --designs-json <file>
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from . import openvsp_model
from .design_identity import design_hash as compute_design_hash
from .mesh_identity import TARGET_MESH_FAMILY, MeshFamilyUnavailable, family_label
from .task_spec import TASK_SPEC

AERO_EVAL_SCHEMA = "dreal001.aero_eval.v1"
EVALUATOR_ID = "a1-aero-evaluator-v1"
BACKEND_REAL = "REAL_VSPAERO"
SOURCE_KIND = "REAL_VSPAERO"
PHYSICAL_VALIDATION_STATUS = "NOT_VALIDATED"

RECORD_SOLVED_VALID = "SOLVED_VALID"
RECORD_SOLVER_FAILED = "SOLVER_FAILED"
RECORD_GEOMETRY_INVALID = "GEOMETRY_INVALID"
RECORD_LIFT_MATCH_FAILED = "LIFT_MATCH_FAILED"
RECORD_NOT_RUN = "NOT_RUN"
RECORD_STATUSES = (RECORD_SOLVED_VALID, RECORD_SOLVER_FAILED,
                   RECORD_GEOMETRY_INVALID, RECORD_LIFT_MATCH_FAILED, RECORD_NOT_RUN)

DEFAULT_GEOMETRY_SET = "thin"
DEFAULT_TESS_U = 12.0
DEFAULT_TESS_W = 25.0
DEFAULT_TIMEOUT_S = 1200.0
DEFAULT_BASENAME = "concorde_baseline"
DEFAULT_MAX_MESH_ATTEMPTS = 12
MESH_STRATEGY = "roundtrip"  # rejection sampling re-build until target mesh family
RESULTS_KEYS = ("alpha_deg", "cltot", "cdi", "cdo", "cdtot", "cmy")


class EvaluatorError(RuntimeError):
    """Base error for the A1 evaluator (fail closed)."""


class TemplateCopyDetected(EvaluatorError):
    """A case directory already holds a different design: template copying."""


class RealStartNotAuthorized(EvaluatorError):
    """A real launch was requested without an approved approval object."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_x12(x12: Sequence[Any]) -> str:
    return json.dumps([float(value) for value in x12], ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))


def task_spec_sha256() -> str:
    payload = json.dumps(TASK_SPEC.to_dict(), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def solver_config_hash(geometry_set: str = DEFAULT_GEOMETRY_SET,
                       tess_u: float = DEFAULT_TESS_U, tess_w: float = DEFAULT_TESS_W,
                       timeout_s: float = DEFAULT_TIMEOUT_S,
                       omp: int = 1) -> str:
    """Hash of everything that can change solver numbers, minus geometry."""
    payload = json.dumps({
        "geometry_set": geometry_set,
        "tessellation": [float(tess_u), float(tess_w)],
        "alpha_list_deg": [float(value) for value in TASK_SPEC.alpha_fixed_list_deg],
        "mach": float(TASK_SPEC.mach),
        "vinf_m_s": float(TASK_SPEC.vinf_m_s),
        "rho_kg_m3": float(TASK_SPEC.rho_kg_m3),
        "recref": float(TASK_SPEC.recref),
        "cref_m": float(TASK_SPEC.cref_m),
        "bref_m": float(TASK_SPEC.bref_m),
        "xcg_m": float(TASK_SPEC.xcg_m),
        "ref_flag": 0,
        "omp": int(omp),
        "timeout_s": float(timeout_s),
        "basename": DEFAULT_BASENAME,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_cache_key(x12: Sequence[Any], config_hash: str,
                      task_sha256: Optional[str] = None,
                      mesh_strategy: Optional[str] = None,
                      target_mesh_family: Optional[Sequence[int]] = None,
                      max_mesh_attempts: Optional[int] = None) -> str:
    """Cache identity: canonical x12 + task spec + solver config + mesh target.

    The mesh family belongs to the identity: one design can build two different
    topologies (543x472 vs 483x418), and a record from the other family must never
    satisfy a request that demands the target family.
    """
    family = ("%dx%d" % (int(target_mesh_family[0]), int(target_mesh_family[1]))
              if target_mesh_family else "unspecified")
    payload = "%s||%s||%s||mesh:%s|target:%s|max_attempts:%s" % (
        canonical_x12(x12), task_sha256 or task_spec_sha256(), config_hash,
        mesh_strategy or "unspecified", family,
        "" if max_mesh_attempts is None else int(max_mesh_attempts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _empty_results() -> Dict[str, List[float]]:
    return {key: [] for key in RESULTS_KEYS}


class AeroEvaluator:
    """A1 evaluator: canonical geometry rebuild + lift-match-ready polar record."""

    evaluator_id = EVALUATOR_ID
    backend = BACKEND_REAL
    source_kind = SOURCE_KIND

    def __init__(self, design_space: Any, task: Any = None, run_dir: Optional[Any] = None, *,
                 approval: Optional[Mapping[str, Any]] = None,
                 spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
                 allow_physical_starts: bool = False,
                 timeout_s: float = DEFAULT_TIMEOUT_S,
                 geometry_set: str = DEFAULT_GEOMETRY_SET,
                 tess_u: float = DEFAULT_TESS_U, tess_w: float = DEFAULT_TESS_W,
                 openvsp_root: Optional[Any] = None,
                 cache_enabled: bool = True,
                 max_mesh_attempts: int = DEFAULT_MAX_MESH_ATTEMPTS,
                 mesh_strategy: str = MESH_STRATEGY,
                 target_mesh_family: Optional[Sequence[int]] = None) -> None:
        self.design_space = design_space
        self.task = task
        self.run_dir = Path(run_dir) if run_dir is not None else None
        self.approval = dict(approval) if approval else None
        self.spawn = spawn
        self.allow_physical_starts = bool(allow_physical_starts)
        self.timeout_s = float(timeout_s)
        self.geometry_set = str(geometry_set)
        self.tess_u = float(tess_u)
        self.tess_w = float(tess_w)
        self.openvsp_root = openvsp_root
        self.cache_enabled = bool(cache_enabled)
        self.max_mesh_attempts = int(max_mesh_attempts)
        self.mesh_strategy = str(mesh_strategy)
        # A5 B3: the target family is per solver configuration, never a global constant.
        # The caller passes the family frozen by that configuration's zero-physics
        # L-09 selection; the 543x472 baseline is only the default for the baseline
        # thin 12x25 configuration.
        self.target_mesh_family = (tuple(int(value) for value in target_mesh_family)
                                   if target_mesh_family else tuple(TARGET_MESH_FAMILY))
        self.config_hash = solver_config_hash(self.geometry_set, self.tess_u, self.tess_w,
                                              self.timeout_s)
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.log: List[Dict[str, Any]] = []
        self._names = [variable.name for variable in design_space.variables] + \
                      [fixed.name for fixed in design_space.fixed_variables]

    # ---------------------------------------------------------------- helpers
    def _baseline_input(self) -> List[float]:
        values = dict(self.design_space.baseline_dict())
        for fixed in self.design_space.fixed_variables:
            values[fixed.name] = float(fixed.baseline)
        return [float(values[name]) for name in self._names]

    def build_geometry(self, x12: Sequence[float]):
        """Canonical path: 12D vector -> ConcordeGeometry (no solver, no cache)."""
        values = self._baseline_input()
        if len(x12) != len(self.design_space.variables):
            raise ValueError("expected %d design values, got %d"
                             % (len(self.design_space.variables), len(x12)))
        for index, variable in enumerate(self.design_space.variables):
            values[self._names.index(variable.name)] = float(x12[index])
        from research.concorde_metaopt.aircraft.geometry_model import build_geometry
        return build_geometry(self._names, values)

    def _geometry_valid(self, x12: Sequence[float]) -> Optional[List[str]]:
        design = {variable.name: float(x12[index])
                  for index, variable in enumerate(self.design_space.variables)}
        problems: List[str] = []
        bounds = self.design_space.check_bounds(design)
        if bounds:
            problems.extend(str(item) for item in bounds)
        cross = self.design_space.check_cross_constraints(design)
        if cross:
            problems.extend(str(item) for item in cross)
        return problems or None

    def _case_dir(self, case_id: str) -> Optional[Path]:
        if self.run_dir is None:
            return None
        return self.run_dir / "cases" / str(case_id)

    def _template_guard(self, case_id: str, x12: Sequence[float]) -> None:
        case_dir = self._case_dir(case_id)
        if case_dir is None:
            return
        record_path = case_dir / "case_inputs.json"
        if not record_path.is_file():
            return
        try:
            stored = json.loads(record_path.read_text(encoding="utf-8"))
        except ValueError:
            return
        design = stored.get("design") or {}
        stored_x12 = design.get("x12")
        if not stored_x12:
            return
        if canonical_x12(stored_x12) != canonical_x12(x12):
            raise TemplateCopyDetected(
                "case %r already holds a different design (stored design_hash %r, "
                "requested %r); rebuilding from x12 is mandatory, template copying is forbidden"
                % (case_id, design.get("design_hash"), compute_design_hash(x12)))

    def _authorize_real_start(self) -> None:
        if not self.allow_physical_starts:
            raise RealStartNotAuthorized(
                "physical solver starts are disabled by default in AeroEvaluator "
                "(allow_physical_starts=False); P2 needs a separate approval")
        if self.spawn is None:
            raise RealStartNotAuthorized("AeroEvaluator needs an injected spawn callable "
                                         "for real starts (A1 owns the process)")
        approval = self.approval or {}
        if not bool(approval.get("approved")):
            raise RealStartNotAuthorized("approval.approved must be true")
        if int(approval.get("max_starts", 0) or 0) <= 0:
            raise RealStartNotAuthorized("approval.max_starts must be positive")

    def _base_record(self, x12: Sequence[float], case_id: str,
                     meta: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        return {
            "schema_version": AERO_EVAL_SCHEMA,
            "evaluator_id": EVALUATOR_ID,
            "backend": BACKEND_REAL,
            "source_kind": SOURCE_KIND,
            "physical_validation_status": PHYSICAL_VALIDATION_STATUS,
            "status": RECORD_NOT_RUN,
            "record_status": RECORD_NOT_RUN,
            "case_id": str(case_id),
            "meta": dict(meta or {}),
            "design": {"x12": [float(value) for value in x12],
                       "design_hash": compute_design_hash(x12)},
            "geometry": {},
            "solver": {},
            "results": _empty_results(),
            "lift": {},
            "attempt_ids": [],
            "raw_artifacts": [],
            "errors": [],
            "cache_hit": False,
            "physical_solver_starts": 0,
            "simulated_solver_starts": 0,
            "physical_call_count": 0,
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "objective": {"name": "D_i_N", "value": None, "unit": "N"},
            "fuel_burn_kg": None,
        }

    # -------------------------------------------------------------- evaluate
    def evaluate(self, x12: Sequence[float], case_id: Optional[str] = None,
                 meta: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        x12 = [float(value) for value in x12]
        design_hash = compute_design_hash(x12)
        if case_id is None:
            case_id = "case-" + design_hash
        record = self._base_record(x12, str(case_id), meta)
        problems = self._geometry_valid(x12)
        if problems:
            record["status"] = RECORD_GEOMETRY_INVALID
            record["record_status"] = RECORD_GEOMETRY_INVALID
            record["geometry"] = {"design_hash": design_hash, "geometry_source":
                                  "REJECTED_BEFORE_BUILD", "problems": problems}
            record["errors"].append({"code": "GEOMETRY_INVALID", "detail": "; ".join(problems)})
            self.log.append({"case_id": str(case_id), "design_hash": design_hash,
                             "status": record["status"], "starts": 0})
            return record

        self._template_guard(str(case_id), x12)
        cache_key = compute_cache_key(
            x12, self.config_hash, mesh_strategy=self.mesh_strategy,
            target_mesh_family=self.target_mesh_family,
            max_mesh_attempts=self.max_mesh_attempts)
        record["cache_key"] = cache_key
        if self.cache_enabled and cache_key in self.cache:
            cached = copy.deepcopy(self.cache[cache_key])
            cached["cache_hit"] = True
            cached["physical_solver_starts"] = 0
            cached["physical_call_count"] = 0
            cached["solver"]["physical_solver_starts"] = 0
            cached["solver"]["cache_hit"] = True
            cached["case_id"] = str(case_id)
            self.log.append({"case_id": str(case_id), "design_hash": design_hash,
                             "status": cached["status"], "starts": 0, "cache_hit": True})
            return cached

        geometry = self.build_geometry(x12)
        sref = float(geometry.wing.area_m2)
        case_dir = self._case_dir(str(case_id))
        if case_dir is not None:
            case_dir.mkdir(parents=True, exist_ok=True)
        prepare_root = case_dir if case_dir is not None else Path(".")
        try:
            prepared = openvsp_model.prepare_case(
                geometry, prepare_root, DEFAULT_BASENAME,
                geometry_set=self.geometry_set,
                alphas_deg=TASK_SPEC.alpha_fixed_list_deg,
                tess_u=self.tess_u, tess_w=self.tess_w,
                openvsp_root=(self.openvsp_root if self.openvsp_root is not None
                              else openvsp_model.DEFAULT_OPENVSP_ROOT),
                rebuild_strategy=self.mesh_strategy,
                target_mesh_family=self.target_mesh_family,
                max_mesh_attempts=self.max_mesh_attempts,
            )
        except MeshFamilyUnavailable as exc:
            # P2 fail-closed: a design whose target mesh family cannot be reached is
            # rejected BEFORE any solver authorization.  Zero physical starts, no label.
            record["status"] = RECORD_GEOMETRY_INVALID
            record["record_status"] = RECORD_GEOMETRY_INVALID
            record["geometry"] = {
                "design_hash": design_hash,
                "geometry_source": "REJECTED_MESH_FAMILY_UNAVAILABLE",
                "mesh_family_target": family_label(self.target_mesh_family),
                "mesh_strategy": self.mesh_strategy,
                "mesh_attempts": len(exc.attempts),
                "mesh_attempt_history": [dict(item) for item in exc.attempts],
                "sref_m2": sref,
            }
            record["errors"].append({
                "code": "MESH_FAMILY_UNAVAILABLE",
                "detail": str(exc),
                "no_solver_start": True,
                "target_mesh_family": family_label(self.target_mesh_family),
                "attempts": len(exc.attempts),
            })
            self.log.append({"case_id": str(case_id), "design_hash": design_hash,
                             "status": record["status"], "starts": 0,
                             "mesh_family_unavailable": True})
            return record
        header = prepared.get("vspgeom_header") or {}
        artifacts = prepared.get("artifacts") or {}
        mesh_block = prepared.get("mesh") or {}
        mesh_nodes = int(mesh_block.get("nodes") or header.get("nodes") or 0)
        mesh_elements = int(mesh_block.get("elements") or header.get("elements") or 0)
        geometry_block = {
            "design_hash": design_hash,
            "geometry_source": "REBUILT_FROM_X12_VIA_CANONICAL_PATH",
            "geometry_sha256": str(prepared.get("geometry_sha256") or ""),
            "vspgeom_sha256": str(mesh_block.get("vspgeom_sha256")
                                  or prepared.get("geometry_sha256") or ""),
            "vspaero_input_sha256": str(prepared.get("vspaero_input_sha256") or ""),
            "input_set_sha256_reproducible": False,
            "nodes": mesh_nodes,
            "elements": mesh_elements,
            "mesh_family": str(mesh_block.get("mesh_family")
                               or family_label((mesh_nodes, mesh_elements)) or ""),
            "mesh_family_target": str(mesh_block.get("target_mesh_family")
                                      or family_label(TARGET_MESH_FAMILY)),
            "mesh_attempts": int(mesh_block.get("mesh_attempts") or 1),
            "mesh_strategy": str(mesh_block.get("rebuild_strategy") or self.mesh_strategy),
            "canonical_mesh_sha256": str(mesh_block.get("canonical_mesh_sha256") or ""),
            # A2 contract name for the same quantity: canonical hash over the sorted
            # %.9f node coordinates plus element connectivity.  Kept as an explicit
            # alias so a downstream adapter never has to infer the mapping.
            "normalized_geometry_hash": str(mesh_block.get("canonical_mesh_sha256") or ""),
            "normalized_geometry_hash_definition": (
                "sha256 over sorted canonical %.9f node coordinates and element "
                "connectivity; identical to canonical_mesh_sha256"),
            "roundtrip_vsp3_sha256": mesh_block.get("roundtrip_vsp3_sha256"),
            "sref_m2": sref,
            "cref_m": float(TASK_SPEC.cref_m),
            "bref_m": float(TASK_SPEC.bref_m),
            "xcg_m": float(TASK_SPEC.xcg_m),
            "reference_frame": "WING_AC",
            "geometry_set": self.geometry_set,
            "tessellation": {"u": self.tess_u, "w": self.tess_w},
            "solver_includes_fuselage": bool(TASK_SPEC.solver_includes_fuselage),
            "component_metrics": prepared.get("component_metrics") or {},
            "input_files": {label: {"sha256": entry.get("sha256"),
                                    "bytes": entry.get("bytes"),
                                    "path": entry.get("path")}
                            for label, entry in artifacts.items()},
            "mesh_family_note": ("OpenVSP 3.55 thin mesher is not deterministic: the same x12 "
                                 "can yield 483x418 or 543x472 nodes/elements across rebuilds. "
                                 "Record mesh_family and never compare runs across families."),
        }
        command = list(((prepared.get("solver_invocation") or {}).get("argv")) or [])
        solver_block = {
            "physical_solver_starts": 0,
            "simulated_solver_starts": 0,
            "command": command,
            "argv": command,
            "timeout_s": self.timeout_s,
            "omp": 1,
            "internal_solver_cases": 0,
            "internal_solver_cases_expected": int(prepared.get("internal_solver_cases_expected") or 0),
            "solver_config_sha256": self.config_hash,
            "solver_config_sha256_source": "a1_geometry.evaluator.solver_config_hash",
            "dry_run_stop_before_run": True,
            "attempt_ids": [],
            "exit_code": None,
            "wall_s": 0.0,
            "cache_hit": False,
        }
        record["geometry"] = geometry_block
        record["solver"] = solver_block
        record["status"] = RECORD_NOT_RUN
        record["record_status"] = RECORD_NOT_RUN
        record["raw_artifacts"] = [
            {"label": label, "path": str(entry.get("path")),
             "sha256": entry.get("sha256"), "bytes": entry.get("bytes")}
            for label, entry in artifacts.items()
        ]

        # Persist the A1 design identity next to the preflight case inputs so a
        # later call can detect template copying (different x12 in same dir).
        if case_dir is not None:
            record_path = case_dir / "case_inputs.json"
            payload = {}
            if record_path.is_file():
                try:
                    payload = json.loads(record_path.read_text(encoding="utf-8"))
                except ValueError:
                    payload = {}
            payload["design"] = record["design"]
            payload["evaluator"] = {
                "evaluator_id": EVALUATOR_ID,
                "schema_version": AERO_EVAL_SCHEMA,
                "cache_key": cache_key,
                "geometry_source": geometry_block["geometry_source"],
                "mesh_family": geometry_block["mesh_family"],
            }
            record_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")

        if self.allow_physical_starts:
            self._authorize_real_start()
            attempt_id = "%s-a01" % case_id
            spawned = self.spawn(case_id=case_id, attempt_id=attempt_id,
                                 case_dir=case_dir, argv=command,
                                 timeout_s=self.timeout_s)
            record["attempt_ids"] = [str(attempt_id)]
            record["physical_solver_starts"] = 1
            record["physical_call_count"] = 1
            solver_block["physical_solver_starts"] = 1
            solver_block["attempt_ids"] = [str(attempt_id)]
            solver_block["internal_solver_cases"] = int(spawned.get("internal_solver_cases") or 0)
            solver_block["exit_code"] = spawned.get("exit_code")
            solver_block["wall_s"] = float(spawned.get("wall_s") or 0.0)
            solver_block["dry_run_stop_before_run"] = False
            status = str(spawned.get("status") or RECORD_SOLVER_FAILED)
            record["status"] = status if status in RECORD_STATUSES else RECORD_SOLVER_FAILED
            record["record_status"] = record["status"]
            for key in RESULTS_KEYS:
                values = (spawned.get("results") or {}).get(key) or []
                record["results"][key] = [float(value) for value in values]
            record["lift"] = dict(spawned.get("lift") or {})

        self.log.append({"case_id": str(case_id), "design_hash": design_hash,
                         "status": record["status"],
                         "starts": record["physical_solver_starts"]})
        if self.cache_enabled:
            self.cache[cache_key] = copy.deepcopy(record)
        return record

    def summary(self) -> Dict[str, Any]:
        return {
            "schema": "dreal001.aero_evaluator.summary.v1",
            "evaluator_id": EVALUATOR_ID,
            "backend": BACKEND_REAL,
            "physical_validation_status": PHYSICAL_VALIDATION_STATUS,
            "run_dir": str(self.run_dir) if self.run_dir is not None else None,
            "physical_call_count": sum(int(item.get("starts", 0)) for item in self.log),
            "evaluations": len(self.log),
            "cache_entries": len(self.cache),
            "solver_config_sha256": self.config_hash,
            "task_spec_sha256": task_spec_sha256(),
            "geometry_source": "REBUILT_FROM_X12_VIA_CANONICAL_PATH",
            "template_copy_policy": "FAIL_CLOSED (TemplateCopyDetected)",
            "zero_physical_default": not self.allow_physical_starts,
        }


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    from research.concorde_metaopt.aircraft.design_space import load_design_space
    from .e6_sensitivity import baseline_x12

    parser = argparse.ArgumentParser(description="A1 AeroEvaluator zero-physical contract run")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--designs-json", default=None,
                        help="JSON list of x12 vectors; default baseline only")
    args = parser.parse_args(argv)
    config = Path(__file__).resolve().parents[2] / "configs" / "design_space_12d_lifting_surfaces.yaml"
    space = load_design_space(str(config))
    designs = ([baseline_x12()] if not args.designs_json
               else json.loads(Path(args.designs_json).read_text(encoding="utf-8")))
    evaluator = AeroEvaluator(space, TASK_SPEC, args.run_dir)
    for index, x12 in enumerate(designs):
        record = evaluator.evaluate([float(value) for value in x12],
                                    case_id="contract-%02d" % index)
        print(json.dumps({"case_id": record["case_id"], "status": record["status"],
                          "design_hash": record["design"]["design_hash"],
                          "nodes": record["geometry"].get("nodes"),
                          "elements": record["geometry"].get("elements"),
                          "sref_m2": record["geometry"].get("sref_m2"),
                          "physical_solver_starts": record["physical_solver_starts"]}))
    print(json.dumps(evaluator.summary(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
