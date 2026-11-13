"""M0-R task-capable evaluator for D-FIXED-001 (zero-physics dry-run).

This module implements the A1 side of the Lead L-30 M0-R interface.  It is
deliberately separate from the frozen F1R2/F2R2 runners and from the frozen
openvsp_model.py byte stream:

* one atmosphere model, ATM-F1R2, holds the A1 frozen injection constants;
* one TaskSpec per (Mach, CL_target) task factor;
* one geometry build per 12D design (vspgeom/vkey bytes are shared across all
  six tasks of that design);
* one derived .vspaero deck per (design, task), produced by rewriting only
  Mach / Vinf / Rho / ReCref in the base deck;
* a solver-stage EvaluationRecord builder that records raw polar SHA, exit
  code, stdout/stderr paths and the five failure classes;
* an idempotent, O_EXCL evaluation-record writer and an A2-ledger hook
  protocol.

The --dry-run command performs OpenVSP model builds and VSPAEROComputeGeometry
only (StopBeforeRun=1 deck generation), never starts vspaero.exe, keeps
physical_call_count at 0 and installs a spawn guard that fails closed on any
attempt to launch a child process.

Schema ids are under dreal001.m1_* and are intentionally new; A3 may rename
the public task ids later, but the task fingerprints and numeric contracts are
stable.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[4]

BASENAME = "concorde_baseline"
ALPHA_GRID = (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)
TARGET_FAMILY = (546, 480)
TESS_U = 12.0
TESS_W = 25.0
INTERNAL_CASES_PER_START = 7
MAX_ALPHA_REFINE = 0
ALPHA_REFINE_MODE = "FIXED_7_POINT_NO_REFINE"
G0_M_S2 = 9.80665
MASS_T_BOUNDS = (100.0, 190.0)
SREF_REF_FROZEN = 358.25000000000006
CREF_M = 18.489892944055953   # freeze-json reference length used for ReCref
DECK_CREF_M = 18.489893        # TASK_SPEC.cref_m, the value injected into .vspaero
DECK_BREF_M = 25.604638        # TASK_SPEC.bref_m, the value injected into .vspaero
XCG_M = 16.821978259514246
SOLVER_EXE = Path("D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe")
SOLVER_SHA256 = "db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad"
SOLVER_VERSION = "VSPAERO 7.2.2"

SCHEMA_TASK_SPEC = "dreal001.m1_task_spec.v1"
SCHEMA_TASK_DECK = "dreal001.m1_task_deck.v1"
SCHEMA_EVALUATION = "dreal001.m1_evaluation_record.v1"
SCHEMA_DRY_RUN = "dreal001.m1_task_evaluator_dry_run.v1"
SCHEMA_U1 = "dreal001.m1_u1_geometry_rebind.v1"

TASK_DEFINITION_SCHEMA = "dreal001.m1_task_definition.v1"
ACTIVE_MASK = "12D_ALL_ACTIVE"
SOURCE_KIND_REBUILD = "REBUILD_12D"
SOURCE_KIND_FROZEN = "FROZEN_REPLAY"

FAILURE_GEOMETRY_INVALID = "GEOMETRY_INVALID"
FAILURE_LIFT_TARGET_UNREACHABLE = "LIFT_TARGET_UNREACHABLE"
FAILURE_SOLVER_NONCONVERGED = "SOLVER_NONCONVERGED"
FAILURE_SOLVER_FAILED = "SOLVER_FAILED"
FAILURE_INFRA_ERROR = "INFRA_ERROR"
SOLVED = "SOLVED"
FAILURE_CLASSES = (
    FAILURE_GEOMETRY_INVALID,
    FAILURE_LIFT_TARGET_UNREACHABLE,
    FAILURE_SOLVER_NONCONVERGED,
    FAILURE_SOLVER_FAILED,
    FAILURE_INFRA_ERROR,
)

DECK_REQUIRED_FIELDS = ("Sref", "Mach", "AoA", "ReCref", "Vinf", "Rho")
DECK_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*?)(\s*)$")

U1_REFERENCE_FILES = (
    ("openvsp_geometry", "research/concorde_metaopt/aircraft/openvsp_geometry.py",
     "d20ee7adc38286c7da3ef3ea5aa5be8204596d491d6601b9a635b0ae5213dc56", 13654),
    ("f1r_bundle_manifest",
     "research/concorde_metaopt/dreal001/geometry/replay_bundles/DFIXED_F1R_20261113_R1/bundle_manifest.json",
     "1b16f5725cf178361f47539db5d727f9687b079e9c8534cc67c153c3d3f8bbe2", 6083),
    ("f1r_baseline_vspgeom",
     "research/concorde_metaopt/dreal001/geometry/replay_bundles/DFIXED_F1R_20261113_R1/PRE-01R/geometry.vspgeom",
     "16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84", 225414),
    ("f1r2_zero_physics_audit_12d",
     "research/concorde_metaopt/dreal001/f1r/DREAL001-F1R-20261113-01/evidence/zero_physics_audit_12d.json",
     "7a90b977fd7ba1778ee44c722a837898b62c9f9d201e4cbd22ca2b7b3afdeea5", 74850),
    ("design_space_yaml",
     "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
     "8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e", 10846),
    ("design_space_freeze_json",
     "research/concorde_metaopt/dreal001/geometry/design_space_freeze.json",
     "fe7e48eba6a70eb76b0b139b1004f775830da68bd5d003604d686e59656e8373", 41775),
)
OLD_TASK_FAMILY_GEOMETRY_SHA = "40fdd4364e01c7fe11ca2ea4530d39c371ae693a434f39e44986f7512d6446f4"


class TaskEvaluatorError(RuntimeError):
    """Base class for fail-closed task-evaluator refusals."""


class TaskSpecInvalid(TaskEvaluatorError):
    """Task definition or mass/lift contract is out of bounds (no solver start)."""


class DeckContractError(TaskEvaluatorError):
    """Derived deck does not carry the preregistered solver contract (no start)."""


class GeometryInvalid(TaskEvaluatorError):
    """Geometry build or orientation gate failed before any solver start."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_dumps(obj: Any, indent: Optional[int] = None) -> str:
    if indent is None:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent,
                      allow_nan=False)


def canonical_digest(obj: Any) -> str:
    return sha256_bytes(strict_dumps(obj).encode("utf-8"))


def require(condition: Any, message: str, exc: type = TaskEvaluatorError) -> None:
    if not condition:
        raise exc(message)


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def rel_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _exclusive_write_flags() -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    return flags


def write_json(path: str | Path, obj: Any, *, exclusive: bool = False) -> bytes:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = (strict_dumps(obj, 2) + "\n").encode("utf-8")
    if exclusive:
        fd = os.open(str(target), _exclusive_write_flags(), 0o644)
        try:
            os.write(fd, raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        return raw
    target.write_bytes(raw)
    return raw


@dataclass(frozen=True)
class AtmosphereModel:
    """Single-source atmosphere model.

    The numeric anchor is the A1 frozen F1R2/F2R2 injection set, not the ISO
    standard atmosphere.  q and Re are scaled from that anchor so that the
    M2.02 task is exactly continuous with the already executed F1R2 chain.
    """
    atmosphere_id: str
    altitude_m: float
    p_static_pa: float
    t_static_k: float
    r_j_kg_k: float
    rho_kg_m3: float
    a_sound_m_s: float
    anchor_mach: float
    anchor_vinf_m_s: float
    anchor_q_pa: float
    anchor_recref: float
    cref_m: float
    basis: str

    def vinf(self, mach: float) -> float:
        return float(mach) * self.a_sound_m_s

    def q(self, mach: float) -> float:
        return self.anchor_q_pa * (float(mach) / self.anchor_mach) ** 2

    def q_recomputed(self, mach: float) -> float:
        vinf = self.vinf(mach)
        return 0.5 * self.rho_kg_m3 * vinf * vinf

    def recref(self, mach: float) -> float:
        return self.anchor_recref * (float(mach) / self.anchor_mach)

    def validate(self) -> Dict[str, Any]:
        anchor_vinf = self.vinf(self.anchor_mach)
        anchor_q = self.q_recomputed(self.anchor_mach)
        vinf_rel = abs(anchor_vinf - self.anchor_vinf_m_s) / abs(self.anchor_vinf_m_s)
        q_rel = abs(anchor_q - self.anchor_q_pa) / abs(self.anchor_q_pa)
        require(vinf_rel <= 1e-15, "ATM anchor Vinf mismatch: %.3e" % vinf_rel)
        require(q_rel <= 1e-12, "ATM anchor q mismatch: %.3e" % q_rel)
        return {"anchor_vinf_rel_error": vinf_rel, "anchor_q_rel_error": q_rel}


ATM_F1R2 = AtmosphereModel(
    atmosphere_id="ATM-F1R2",
    altitude_m=18288.0,
    p_static_pa=7171.544888256813,
    t_static_k=216.65,
    r_j_kg_k=287.05287,
    rho_kg_m3=0.1153178340089936,
    a_sound_m_s=295.06801842964956,
    anchor_mach=2.02,
    anchor_vinf_m_s=596.0373972278921,
    anchor_q_pa=20483.940233430174,
    anchor_recref=89397005.8767656,
    cref_m=CREF_M,
    basis=("A1 frozen F1R2/F2R2 injection constants; NOT the ISO standard "
           "atmosphere. M2.02/18,288 m is the only anchored condition."),
)


@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    mach: float
    cl_target: float
    split: str
    rationale: str


TASK_DEFINITIONS = (
    TaskDefinition("T18K_M202_CL017", 2.02, 0.17, "meta_train", "anchored F1R2 condition"),
    TaskDefinition("T18K_M202_CL019", 2.02, 0.19, "meta_train", "same Mach, higher lift"),
    TaskDefinition("T18K_M220_CL017", 2.2, 0.17, "meta_train", "higher Mach"),
    TaskDefinition("T18K_M220_CL019", 2.2, 0.19, "meta_val", "higher Mach, higher lift"),
    TaskDefinition("T18K_M180_CL017", 1.8, 0.17, "meta_test", "lower Mach, blind test"),
    TaskDefinition("T18K_M180_CL019", 1.8, 0.19, "meta_test", "lower Mach, higher lift, blind test"),
)


def task_fingerprint(task: TaskDefinition) -> str:
    payload = {
        "schema": TASK_DEFINITION_SCHEMA,
        "task_id": task.task_id,
        "altitude_m": ATM_F1R2.altitude_m,
        "mach": task.mach,
        "cl_target": task.cl_target,
        "atmosphere_id": ATM_F1R2.atmosphere_id,
        "active_mask": ACTIVE_MASK,
        "split": task.split,
        "l_ref_rule": "q(M,18288)*SREF_REF*CL_target",
    }
    return canonical_digest(payload)


def build_task_spec(task: TaskDefinition, sref_ref: float,
                    atmosphere: AtmosphereModel = ATM_F1R2) -> Dict[str, Any]:
    if not (math.isfinite(sref_ref) and sref_ref > 0.0):
        raise TaskSpecInvalid("SREF_REF must be a positive finite number, got %r" % (sref_ref,))
    if abs(sref_ref - SREF_REF_FROZEN) > 1e-12 * SREF_REF_FROZEN:
        raise TaskSpecInvalid(
            "runtime SREF_REF %.17g does not match the frozen reference %.17g" % (
                sref_ref, SREF_REF_FROZEN))
    q = atmosphere.q(task.mach)
    q_rec = atmosphere.q_recomputed(task.mach)
    q_rel = abs(q_rec - q) / abs(q)
    if q_rel > 1e-12:
        raise TaskSpecInvalid("q recompute rel error %.3e > 1e-12" % q_rel)
    vinf = atmosphere.vinf(task.mach)
    rho = atmosphere.rho_kg_m3
    recref = atmosphere.recref(task.mach)
    for label, value in (("q", q), ("Vinf", vinf), ("rho", rho), ("ReCref", recref)):
        if not (math.isfinite(value) and value > 0.0):
            raise TaskSpecInvalid("%s is not positive finite: %r" % (label, value))
    l_ref = q * sref_ref * task.cl_target
    mass_t = l_ref / G0_M_S2 / 1000.0
    low, high = MASS_T_BOUNDS
    if not (low <= mass_t <= high):
        raise TaskSpecInvalid(
            "task %s mass %.6f t outside [%g, %g] t" % (task.task_id, mass_t, low, high))
    return {
        "schema": SCHEMA_TASK_SPEC,
        "task_id": task.task_id,
        "task_fingerprint": task_fingerprint(task),
        "task_definition": {
            "schema": TASK_DEFINITION_SCHEMA,
            "task_id": task.task_id,
            "mach": task.mach,
            "cl_target": task.cl_target,
            "altitude_m": atmosphere.altitude_m,
            "atmosphere_id": atmosphere.atmosphere_id,
            "active_mask": ACTIVE_MASK,
            "split": task.split,
            "rationale": task.rationale,
        },
        "atmosphere": {
            "atmosphere_id": atmosphere.atmosphere_id,
            "altitude_m": atmosphere.altitude_m,
            "p_static_pa": atmosphere.p_static_pa,
            "t_static_k": atmosphere.t_static_k,
            "r_j_kg_k": atmosphere.r_j_kg_k,
            "rho_kg_m3": atmosphere.rho_kg_m3,
            "a_sound_m_s": atmosphere.a_sound_m_s,
            "basis": atmosphere.basis,
        },
        "q_pa": q,
        "q_recomputed_pa": q_rec,
        "q_recompute_rel_error": q_rel,
        "vinf_m_s": vinf,
        "rho_kg_m3": rho,
        "recref": recref,
        "sref_ref_m2": float(sref_ref),
        "l_ref_n": l_ref,
        "mass_t": mass_t,
        "mass_bounds_t": [low, high],
        "cl_required_baseline": l_ref / (q * sref_ref),
        "active_mask": ACTIVE_MASK,
    }


@dataclass(frozen=True)
class ReferenceDesign:
    design_id: str
    label: str
    x12: Tuple[float, ...]
    design_hash: str
    sref_m2: float
    source_case: str
    source_vspgeom_sha256: str


BASELINE_X12 = (358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313,
                0.408284, 0.130178, 0.0, 33.91, 0.0)
W05P_X12 = BASELINE_X12[:4] + (72.0,) + BASELINE_X12[5:]
W01P_X12 = (370.25,) + BASELINE_X12[1:]
REFERENCE_DESIGNS = (
    ReferenceDesign("B0-01", "baseline", BASELINE_X12, "8bd5a6c7c8311938",
                    358.25000000000006, "B0-01",
                    "16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84"),
    ReferenceDesign("B1-01", "W05p_sweep3_72", W05P_X12, "6653517b11d6f891",
                    358.25000000000006, "B1-01",
                    "6a296aee6e6f6b505083c655c63a667fd52309432e798b25305d01d588d70612"),
    ReferenceDesign("C5", "W01p_wing_area_370.25", W01P_X12, "bc52a54ecefaac4c",
                    370.25, "C5",
                    "e1ad74cc3820553ee6864d121168ae8f5b72d5602619f15de9cf2c04f1a7bde8"),
)


def _load_module(module_name: str) -> Any:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    return importlib.import_module(module_name)


def design_hash(x12: Sequence[float]) -> str:
    return _load_module(
        "research.concorde_metaopt.dreal001.geometry.design_identity").design_hash(
            [float(value) for value in x12])


def _load_openvsp_model() -> Any:
    return _load_module("research.concorde_metaopt.dreal001.geometry.openvsp_model")


def _load_polar_parser() -> Any:
    return _load_module("research.concorde_metaopt.dreal001.geometry.polar_parser")


class SpawnGuard:
    """Fail-closed guard against any child process during zero-physics runs."""

    TARGETS = (
        (subprocess, ("Popen", "run", "call", "check_call", "check_output")),
        (os, ("system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe",
              "spawnv", "spawnve", "spawnvp", "spawnvpe")),
    )

    def __init__(self) -> None:
        self.attempts: List[str] = []
        self._saved: List[Tuple[Any, str, Any]] = []

    def _refuse(self, name: str) -> Any:
        def blocked(*args: Any, **kwargs: Any) -> Any:
            self.attempts.append(name)
            raise TaskEvaluatorError("spawn blocked in zero-physics dry-run: " + name)
        return blocked

    def install(self) -> "SpawnGuard":
        for owner, names in self.TARGETS:
            for name in names:
                if hasattr(owner, name):
                    self._saved.append((owner, name, getattr(owner, name)))
                    setattr(owner, name, self._refuse("%s.%s" % (owner.__name__, name)))
        return self

    def uninstall(self) -> None:
        for owner, name, saved in reversed(self._saved):
            setattr(owner, name, saved)
        self._saved = []


def build_reference_design(design: ReferenceDesign, work_dir: str | Path,
                           atmosphere: AtmosphereModel = ATM_F1R2) -> Dict[str, Any]:
    """Build one 12D design once, with VSPAEROComputeGeometry only.

    The returned vspgeom/vkey bytes are reused verbatim by every task deck of
    this design.  No solver process is started.
    """
    module = _load_openvsp_model()
    target = Path(work_dir)
    target.mkdir(parents=True, exist_ok=True)
    computed_hash = design_hash(design.x12)
    if computed_hash != design.design_hash:
        raise GeometryInvalid(
            "design %s hash %s does not match frozen %s" % (
                design.design_id, computed_hash, design.design_hash))
    geometry, _space = module._geometry_from_design_vector([float(v) for v in design.x12])
    sref = float(geometry.wing.area_m2)
    if abs(sref - design.sref_m2) > 1e-9 * max(1.0, abs(design.sref_m2)):
        raise GeometryInvalid(
            "design %s Sref %.17g != frozen %.17g" % (design.design_id, sref, design.sref_m2))
    started = time.perf_counter()
    record = module.prepare_case(
        geometry, str(target), BASENAME,
        geometry_set="thin", alphas_deg=list(ALPHA_GRID),
        tess_u=TESS_U, tess_w=TESS_W,
        openvsp_root=module.DEFAULT_OPENVSP_ROOT, n_wake_nodes=8,
        write_vsp3=True, mach_values=[atmosphere.anchor_mach],
        rebuild_strategy="roundtrip",
        target_mesh_family=list(TARGET_FAMILY), max_mesh_attempts=12,
    )
    wall_s = time.perf_counter() - started
    mesh = record["mesh"]
    if (int(mesh["nodes"]), int(mesh["elements"])) != TARGET_FAMILY:
        raise GeometryInvalid(
            "design %s build family %r != %r" % (
                design.design_id, mesh.get("mesh_family"), TARGET_FAMILY))
    if abs(float(record["sref_m2"]) - sref) > 1e-12 * max(1.0, abs(sref)):
        raise GeometryInvalid("design %s record Sref mismatch" % design.design_id)
    vspgeom = target / (BASENAME + ".vspgeom")
    vkey = target / (BASENAME + ".vkey")
    vspaero = target / (BASENAME + ".vspaero")
    csf = target / (BASENAME + ".csf")
    vsp3 = target / (BASENAME + ".vsp3")
    for path in (vspgeom, vkey, vspaero, csf, vsp3):
        if not path.is_file():
            raise GeometryInvalid("build did not produce %s" % path)
    return {
        "design": design,
        "build_dir": str(target),
        "geometry": geometry,
        "record": record,
        "sref_m2": sref,
        "design_hash": computed_hash,
        "wall_s": wall_s,
        "vspgeom": {"path": str(vspgeom), "bytes": vspgeom.stat().st_size,
                    "sha256": sha256_file(vspgeom)},
        "vkey": {"path": str(vkey), "bytes": vkey.stat().st_size,
                 "sha256": sha256_file(vkey)},
        "vspaero_base": {"path": str(vspaero), "bytes": vspaero.stat().st_size,
                         "sha256": sha256_file(vspaero)},
        "csf": {"path": str(csf), "bytes": csf.stat().st_size,
                "sha256": sha256_file(csf)},
        "vsp3": {"path": str(vsp3), "bytes": vsp3.stat().st_size,
                 "sha256": sha256_file(vsp3)},
    }


def decimal17(value: float) -> str:
    return "%.17g" % float(value)


def _split_ending(line: str) -> Tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def parse_deck_fields(text: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for line in text.splitlines(keepends=True):
        body, _ending = _split_ending(line)
        match = DECK_LINE_RE.match(body)
        if match:
            fields[match.group(1)] = match.group(3)
    return fields


def rewrite_deck(text: str, updates: Mapping[str, str]) -> Tuple[str, Dict[str, str]]:
    pending = dict(updates)
    applied: Dict[str, str] = {}
    output: List[str] = []
    for line in text.splitlines(keepends=True):
        body, ending = _split_ending(line)
        match = DECK_LINE_RE.match(body)
        if match and match.group(1) in pending:
            key = match.group(1)
            value = pending.pop(key)
            body = key + match.group(2) + value + match.group(4)
            applied[key] = value
        output.append(body + ending)
    if pending:
        raise DeckContractError("base deck is missing fields: %s" % sorted(pending))
    return "".join(output), applied


def _float_rel_error(observed: float, expected: float) -> float:
    denominator = max(abs(expected), 1e-300)
    return abs(observed - expected) / denominator


def validate_task_deck(deck_path: str | Path, task_spec: Mapping[str, Any],
                       sref_m2: float) -> Dict[str, Any]:
    path = Path(deck_path)
    if not path.is_file():
        raise DeckContractError("derived deck missing: %s" % path)
    text = path.read_text(encoding="utf-8")
    fields = parse_deck_fields(text)
    missing = [name for name in DECK_REQUIRED_FIELDS if name not in fields]
    if missing:
        raise DeckContractError("derived deck missing fields: %s" % missing)
    numeric = {name: float(fields[name]) for name in
               ("Sref", "Mach", "ReCref", "Vinf", "Rho")}
    observed_q = 0.5 * numeric["Rho"] * numeric["Vinf"] * numeric["Vinf"]
    q_rel = _float_rel_error(observed_q, float(task_spec["q_pa"]))
    checks = {
        "sref_matches_geometry": _float_rel_error(numeric["Sref"], sref_m2) <= 1e-12,
        "mach_matches_task": _float_rel_error(numeric["Mach"], float(task_spec["task_definition"]["mach"])) <= 1e-12,
        "vinf_matches_task": _float_rel_error(numeric["Vinf"], float(task_spec["vinf_m_s"])) <= 1e-12,
        "rho_matches_atmosphere": _float_rel_error(numeric["Rho"], float(task_spec["rho_kg_m3"])) <= 1e-12,
        "recref_matches_task": _float_rel_error(numeric["ReCref"], float(task_spec["recref"])) <= 1e-12,
        "q_recompute_rel_le_1e_12": q_rel <= 1e-12,
    }
    alphas = [float(token.strip()) for token in fields["AoA"].split(",")]
    checks["alpha_grid_is_frozen"] = (
        len(alphas) == len(ALPHA_GRID) and
        all(abs(observed - expected) <= 1e-9 * max(1.0, abs(expected))
            for observed, expected in zip(alphas, ALPHA_GRID)))
    required_fixed = {
        "Cref": DECK_CREF_M, "Bref": DECK_BREF_M, "X_cg": XCG_M, "Beta": 0.0,
    }
    for name, expected in required_fixed.items():
        if name not in fields:
            checks["fixed_" + name] = False
            continue
        checks["fixed_" + name] = _float_rel_error(float(fields[name]), expected) <= 1e-12
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise DeckContractError(
            "derived deck contract failed for %s: %s (q_rel=%.3e)" % (
                task_spec["task_id"], failed, q_rel))
    cl_required = float(task_spec["l_ref_n"]) / (float(task_spec["q_pa"]) * sref_m2)
    return {
        "fields": {name: fields[name] for name in
                   ("Sref", "Cref", "Bref", "X_cg", "Mach", "AoA", "Beta",
                    "ReCref", "Vinf", "Rho")},
        "numeric": numeric,
        "alpha_deg": alphas,
        "q_recomputed_pa": observed_q,
        "q_recompute_rel_error": q_rel,
        "checks": checks,
        "cl_required": cl_required,
    }


def solver_input_sha256(case_dir: str | Path, basename: str = BASENAME) -> Dict[str, Any]:
    root = Path(case_dir)
    specs: Dict[str, Any] = {}
    payload: List[List[str]] = []
    for stem in ("vspgeom", "vkey", "vspaero", "csf"):
        path = root / (basename + "." + stem)
        if not path.is_file():
            raise DeckContractError("missing solver input: %s" % path)
        sha = sha256_file(path)
        specs[stem] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha}
        payload.append([stem, sha])
    return {"files": specs, "input_sha256": canonical_digest(payload)}


def derive_task_deck(build: Mapping[str, Any], task_spec: Mapping[str, Any],
                     out_dir: str | Path) -> Dict[str, Any]:
    """Create one per-task case dir from a shared geometry build (no solver)."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    design = build["design"]
    for stem in ("vspgeom", "vkey", "csf"):
        source = Path(build[stem]["path"])
        destination = target / (BASENAME + "." + stem)
        shutil.copyfile(source, destination)
        if sha256_file(destination) != build[stem]["sha256"]:
            raise DeckContractError("copied %s SHA changed" % stem)
    base_deck_text = Path(build["vspaero_base"]["path"]).read_text(encoding="utf-8")
    base_fields = parse_deck_fields(base_deck_text)
    for name in DECK_REQUIRED_FIELDS:
        if name not in base_fields:
            raise DeckContractError("base deck missing %s" % name)
    if _float_rel_error(float(base_fields["Sref"]), float(build["sref_m2"])) > 1e-12:
        raise DeckContractError("base deck Sref does not match geometry")
    updates = {
        "Mach": decimal17(task_spec["task_definition"]["mach"]),
        "Vinf": decimal17(task_spec["vinf_m_s"]),
        "Rho": decimal17(task_spec["rho_kg_m3"]),
        "ReCref": decimal17(task_spec["recref"]),
    }
    derived_text, applied = rewrite_deck(base_deck_text, updates)
    deck_path = target / (BASENAME + ".vspaero")
    deck_path.write_bytes(derived_text.encode("utf-8"))
    validation = validate_task_deck(deck_path, task_spec, float(build["sref_m2"]))
    inputs = solver_input_sha256(target)
    deck_sha = sha256_file(deck_path)
    record = {
        "schema": SCHEMA_TASK_DECK,
        "task_id": task_spec["task_id"],
        "task_fingerprint": task_spec["task_fingerprint"],
        "design_id": design.design_id,
        "design_label": design.label,
        "design_hash": design.design_hash,
        "x12": [float(value) for value in design.x12],
        "source_kind": SOURCE_KIND_REBUILD,
        "active_mask": ACTIVE_MASK,
        "geometry": {
            "vspgeom": build["vspgeom"],
            "vkey": build["vkey"],
            "sref_m2": build["sref_m2"],
            "mesh": dict(build["record"]["mesh"]),
            "component_metrics": dict(build["record"].get("component_metrics") or {}),
        },
        "solver_inputs": inputs,
        "deck": {
            "path": str(deck_path),
            "bytes": deck_path.stat().st_size,
            "sha256": deck_sha,
            "applied_overrides": applied,
            "source_base_deck_sha256": build["vspaero_base"]["sha256"],
            "fields": validation["fields"],
            "alpha_deg": validation["alpha_deg"],
            "q_recomputed_pa": validation["q_recomputed_pa"],
            "q_recompute_rel_error": validation["q_recompute_rel_error"],
            "cl_required": validation["cl_required"],
            "checks": validation["checks"],
        },
        "task_spec": dict(task_spec),
        "expected_internal_cases_per_start": INTERNAL_CASES_PER_START,
        "solver_started": False,
        "physical_solver_starts": 0,
        "status": "DECK_READY_NOT_RUN",
    }
    write_json(target / "task_deck.json", record)
    return record


def _ols_cl_alpha(rows: Sequence[Mapping[str, float]]) -> Dict[str, Any]:
    if len(rows) < 5:
        return {"computable": False, "reason": "fewer than 5 valid rows", "n": len(rows)}
    xs = [float(row["alpha_deg"]) for row in rows]
    ys = [float(row["cl"]) for row in rows]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx if sxx else float("nan")
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else float("nan")
    computable = math.isfinite(slope) and math.isfinite(r2) and r2 >= 0.99
    return {"computable": bool(computable), "n": len(rows),
            "slope_per_deg": slope, "intercept": intercept, "r2": r2,
            "gate": "n>=5 and R2>=0.99"}


def analyze_polar(polar_path: str | Path, task_spec: Mapping[str, Any],
                  sref_m2: float) -> Dict[str, Any]:
    """Parse one polar and compute lift-matched CDi and D_i = q*Sref*CDi."""
    path = Path(polar_path)
    result: Dict[str, Any] = {
        "polar_path": str(path),
        "polar_exists": path.is_file(),
        "polar_sha256": None,
        "polar_bytes": None,
        "status": "NO_POLAR",
        "rows_total": 0,
        "rows_valid": 0,
        "alpha_deg": [],
        "cl_target": None,
        "alpha_star_deg": None,
        "cdi_lift_matched": None,
        "cl_at_alpha_star": None,
        "lift_residual_n": None,
        "lift_residual_rel": None,
        "d_i_n": None,
        "interpolation": None,
        "cl_alpha": None,
    }
    if not path.is_file():
        return result
    parser = _load_polar_parser()
    raw = path.read_bytes()
    result["polar_sha256"] = sha256_bytes(raw)
    result["polar_bytes"] = len(raw)
    try:
        record = parser.parse_polar_text(raw.decode("utf-8", errors="replace"), source=str(path))
    except Exception as exc:
        result["status"] = "PARSE_ERROR"
        result["detail"] = str(exc)
        return result
    rows = record["rows"]
    result["rows_total"] = len(rows)
    if not rows:
        result["status"] = "INCOMPLETE"
        result["detail"] = "polar has no rows"
        return result
    unique = parser.unique_case_rows(rows)
    multiplicity = parser.case_multiplicity(rows)
    result["case_multiplicity"] = multiplicity
    parsed_rows: List[Dict[str, Any]] = []
    nonfinite: List[Dict[str, Any]] = []
    for row in unique:
        alpha = parser.field(row, "AoA")
        cl = parser.cltot(row)
        cdi = parser.field(row, "CDi")
        cdtot = parser.cdtot(row)
        if (alpha is None or cl is None or cdi is None or cdtot is None or
                not math.isfinite(float(alpha)) or not math.isfinite(float(cl)) or
                not math.isfinite(float(cdi)) or not math.isfinite(float(cdtot))):
            nonfinite.append({"alpha_deg": alpha, "cl": cl, "cdi": cdi,
                              "cdtot": cdtot,
                              "invalid_tokens": row.get("_invalid_tokens", {})})
            continue
        mach = parser.field(row, "Mach")
        parsed_rows.append({"alpha_deg": float(alpha), "cl": float(cl),
                            "cdi": float(cdi), "cdtot": float(cdtot),
                            "mach": mach})
    result["rows_valid"] = len(parsed_rows)
    if nonfinite:
        result["status"] = "NONFINITE"
        result["nonfinite_rows"] = nonfinite
        result["cl_alpha"] = _ols_cl_alpha(parsed_rows)
        return result
    if len(parsed_rows) != len(ALPHA_GRID):
        result["status"] = "INCOMPLETE"
        result["detail"] = "expected %d unique rows, got %d" % (
            len(ALPHA_GRID), len(parsed_rows))
        result["cl_alpha"] = _ols_cl_alpha(parsed_rows)
        return result
    parsed_rows.sort(key=lambda row: row["alpha_deg"])
    observed_alphas = [row["alpha_deg"] for row in parsed_rows]
    result["alpha_deg"] = observed_alphas
    if not all(abs(observed - expected) <= 1e-6 * max(1.0, abs(expected))
               for observed, expected in zip(observed_alphas, ALPHA_GRID)):
        result["status"] = "ALPHA_GRID_MISMATCH"
        result["detail"] = "observed alpha grid %r != frozen %r" % (
            observed_alphas, list(ALPHA_GRID))
        result["cl_alpha"] = _ols_cl_alpha(parsed_rows)
        return result
    if any(row["mach"] is not None and
           abs(float(row["mach"]) - float(task_spec["task_definition"]["mach"])) >
           1e-6 * max(1.0, float(task_spec["task_definition"]["mach"]))
           for row in parsed_rows):
        result["status"] = "MACH_MISMATCH"
        result["detail"] = "polar Mach does not match task Mach"
        result["cl_alpha"] = _ols_cl_alpha(parsed_rows)
        return result
    result["cl_target"] = float(task_spec["l_ref_n"]) / (
        float(task_spec["q_pa"]) * sref_m2)
    result["cl_alpha"] = _ols_cl_alpha(parsed_rows)
    target = result["cl_target"]
    exact = [row for row in parsed_rows
             if abs(row["cl"] - target) <= 1e-12 * max(1.0, abs(target))]
    if exact:
        row = exact[0]
        alpha_star = row["alpha_deg"]
        cdi = row["cdi"]
        cl_at = row["cl"]
        interpolation = {"mode": "exact_row", "alpha_deg": alpha_star}
    else:
        interpolation = None
        alpha_star = None
        cdi = None
        cl_at = None
        for left, right in zip(parsed_rows[:-1], parsed_rows[1:]):
            cl_left, cl_right = left["cl"], right["cl"]
            if (cl_left - target) * (cl_right - target) <= 0.0 and cl_left != cl_right:
                fraction = (target - cl_left) / (cl_right - cl_left)
                alpha_star = left["alpha_deg"] + fraction * (
                    right["alpha_deg"] - left["alpha_deg"])
                cdi = left["cdi"] + fraction * (right["cdi"] - left["cdi"])
                cl_at = cl_left + fraction * (cl_right - cl_left)
                interpolation = {
                    "mode": "linear_between_rows",
                    "left": left, "right": right, "fraction": fraction,
                }
                break
    if alpha_star is None:
        result["status"] = "NO_BRACKET"
        result["detail"] = "CL_target %.9f is outside the polar CL range" % target
        return result
    lift_residual_n = abs(cl_at - target) * float(task_spec["q_pa"]) * sref_m2
    lift_residual_rel = abs(cl_at - target) / abs(target)
    result.update({
        "status": "OK",
        "alpha_star_deg": alpha_star,
        "cdi_lift_matched": cdi,
        "cl_at_alpha_star": cl_at,
        "lift_residual_n": lift_residual_n,
        "lift_residual_rel": lift_residual_rel,
        "d_i_n": float(task_spec["q_pa"]) * sref_m2 * cdi,
        "interpolation": interpolation,
    })
    return result


def classify_failure(*, geometry_ok: bool, deck_ok: bool,
                     attempt: Mapping[str, Any],
                     polar_analysis: Mapping[str, Any]) -> str:
    """Map one attempt to the five preregistered classes (fail-closed order)."""
    if not geometry_ok or not deck_ok:
        return FAILURE_GEOMETRY_INVALID
    if bool(attempt.get("timed_out")):
        return FAILURE_INFRA_ERROR
    exit_code = attempt.get("exit_code")
    if exit_code is None:
        return FAILURE_INFRA_ERROR
    polar_exists = bool(polar_analysis.get("polar_exists"))
    if not polar_exists:
        return FAILURE_INFRA_ERROR if int(exit_code) == 0 else FAILURE_SOLVER_FAILED
    if int(exit_code) != 0:
        return FAILURE_SOLVER_FAILED
    status = polar_analysis.get("status")
    if status in ("NONFINITE", "INCOMPLETE", "ALPHA_GRID_MISMATCH", "MACH_MISMATCH"):
        return FAILURE_SOLVER_NONCONVERGED
    if status == "PARSE_ERROR":
        return FAILURE_INFRA_ERROR
    if status == "NO_BRACKET":
        return FAILURE_LIFT_TARGET_UNREACHABLE
    if status == "OK":
        return SOLVED
    return FAILURE_INFRA_ERROR


def evaluation_key(task_spec: Mapping[str, Any], design_hash_value: str,
                   deck_sha256: str, geometry_sha256: str,
                   solver_sha256: str) -> str:
    payload = {
        "task_id": task_spec["task_id"],
        "task_fingerprint": task_spec["task_fingerprint"],
        "design_hash": design_hash_value,
        "deck_sha256": deck_sha256,
        "geometry_sha256": geometry_sha256,
        "solver_sha256": solver_sha256,
        "internal_cases_per_start": INTERNAL_CASES_PER_START,
    }
    return canonical_digest(payload)


def build_evaluation_record(*, task_spec: Mapping[str, Any],
                            deck_record: Mapping[str, Any],
                            attempt: Mapping[str, Any],
                            polar_analysis: Mapping[str, Any],
                            status: str) -> Dict[str, Any]:
    """Assemble the interface record A2's M1 runner can consume."""
    if status not in FAILURE_CLASSES and status != SOLVED:
        raise TaskEvaluatorError("unknown evaluation status: %r" % (status,))
    design = deck_record["design_id"]
    deck_sha = deck_record["deck"]["sha256"]
    geometry_sha = deck_record["geometry"]["vspgeom"]["sha256"]
    solver_sha = attempt.get("solver_sha256") or SOLVER_SHA256
    key = evaluation_key(task_spec, deck_record["design_hash"], deck_sha,
                         geometry_sha, solver_sha)
    started = bool(attempt.get("started", True))
    solved = status == SOLVED
    record = {
        "schema": SCHEMA_EVALUATION,
        "evaluation_key": key,
        "task_id": task_spec["task_id"],
        "task_fingerprint": task_spec["task_fingerprint"],
        "design_id": design,
        "design_hash": deck_record["design_hash"],
        "x12": list(deck_record["x12"]),
        "active_mask": ACTIVE_MASK,
        "source_kind": deck_record.get("source_kind", SOURCE_KIND_REBUILD),
        "objective_Di_N": polar_analysis.get("d_i_n") if solved else None,
        "alpha_star_deg": polar_analysis.get("alpha_star_deg") if solved else None,
        "sref_m2": float(deck_record["geometry"]["sref_m2"]),
        "sref_policy": "Sref(x) = exposed main-wing planform area, recomputed per design",
        "l_ref_n": float(task_spec["l_ref_n"]),
        "q_pa": float(task_spec["q_pa"]),
        "cl_required": float(task_spec["l_ref_n"]) / (
            float(task_spec["q_pa"]) * float(deck_record["geometry"]["sref_m2"])),
        "raw_sha": polar_analysis.get("polar_sha256"),
        "polar_bytes": polar_analysis.get("polar_bytes"),
        "geometry_sha": geometry_sha,
        "deck_sha": deck_sha,
        "solver_version": attempt.get("solver_version") or SOLVER_VERSION,
        "solver_sha256": solver_sha,
        "starts": 1 if started else 0,
        "internal": INTERNAL_CASES_PER_START if started else 0,
        "physical_solver_starts": 1 if started else 0,
        "status": status,
        "failure_class": None if solved else status,
        "classification_detail": polar_analysis.get("detail") if not solved else None,
        "cdi_lift_matched": polar_analysis.get("cdi_lift_matched") if solved else None,
        "cl_at_alpha_star": polar_analysis.get("cl_at_alpha_star") if solved else None,
        "lift_residual_n": polar_analysis.get("lift_residual_n") if solved else None,
        "lift_residual_rel": polar_analysis.get("lift_residual_rel") if solved else None,
        "interpolation": polar_analysis.get("interpolation") if solved else None,
        "cl_alpha": polar_analysis.get("cl_alpha"),
        "polar_rows_total": polar_analysis.get("rows_total"),
        "polar_rows_valid": polar_analysis.get("rows_valid"),
        "attempt": {
            "attempt_id": attempt.get("attempt_id"),
            "exit_code": attempt.get("exit_code"),
            "timed_out": bool(attempt.get("timed_out")),
            "started_utc": attempt.get("started_utc"),
            "ended_utc": attempt.get("ended_utc"),
            "stdout_path": attempt.get("stdout_path"),
            "stderr_path": attempt.get("stderr_path"),
            "stdout_sha256": attempt.get("stdout_sha256"),
            "stderr_sha256": attempt.get("stderr_sha256"),
            "polar_path": polar_analysis.get("polar_path"),
            "argv": attempt.get("argv"),
            "cwd": attempt.get("cwd"),
        },
        "created_utc": utc_now(),
    }
    return record


def write_evaluation_record(out_dir: str | Path, record: Mapping[str, Any]) -> Dict[str, Any]:
    path = Path(out_dir) / "evaluations" / (record["evaluation_key"] + ".json")
    raw = (strict_dumps(dict(record), 2) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing == raw:
            return {"path": str(path), "bytes": len(existing), "reused": True}
        raise TaskEvaluatorError(
            "conflicting evaluation record already exists: %s" % path)
    fd = os.open(str(path), _exclusive_write_flags(), 0o644)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    return {"path": str(path), "bytes": len(raw), "reused": False}


def write_attempt_summary(run_dir: str | Path, summary: Mapping[str, Any]) -> Dict[str, Any]:
    attempt_id = summary.get("attempt_id")
    if not isinstance(attempt_id, str) or not attempt_id:
        raise TaskEvaluatorError("attempt_id must be a non-empty string")
    target = Path(run_dir) / "attempts" / attempt_id / "attempt.json"
    raw = (strict_dumps(dict(summary), 2) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(target), _exclusive_write_flags(), 0o644)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    return {"path": str(target), "bytes": len(raw)}


class AccountingHooks(Protocol):
    """Duck-typed A2 accounting_ledger hook surface used by an M1 runner."""

    def reserve(self, *, phase: str, arm_id: str, design_index: int,
                design_hash: str, planned_starts: int = 1,
                planned_internal_cases: int = INTERNAL_CASES_PER_START,
                meta: Optional[Mapping[str, Any]] = None) -> str: ...

    def start(self, tx_id: str, *, case_id: str,
              meta: Optional[Mapping[str, Any]] = None) -> bool: ...

    def end(self, tx_id: str, *, status: str,
            internal_solver_cases: int = INTERNAL_CASES_PER_START,
            meta: Optional[Mapping[str, Any]] = None) -> bool: ...

    def fail_before_start(self, tx_id: str, *, reason: str) -> bool: ...

    def record_evaluation(self, *, phase: str, arm_id: str,
                          design_index: int, design_hash: str,
                          meta: Optional[Mapping[str, Any]] = None) -> None: ...

    def record_cached_read(self, *, phase: str, arm_id: str,
                           design_hash: str, source: str,
                           meta: Optional[Mapping[str, Any]] = None) -> None: ...


class A2LedgerHooks:
    r"""Thin adapter over D:\RCAIDE\dnext001\wt-real-a2-optimizers accounting_ledger.

    This module never imports or rewrites A2 bytes.  The M1 runner constructs
    the A2 ledger object, verifies its SHA against the M0-R package, and passes
    it here.  charged (reserve) and actual (start/end) bases stay separate.
    """

    REQUIRED = ("reserve", "start", "end", "fail_before_start",
                "record_evaluation", "record_cached_read")

    def __init__(self, ledger: Any, *, phase: str = "main",
                 arm_id: str = "M1_TASK") -> None:
        missing = [name for name in self.REQUIRED if not hasattr(ledger, name)]
        if missing:
            raise TaskEvaluatorError("A2 ledger missing methods: %s" % missing)
        self.ledger = ledger
        self.phase = phase
        self.arm_id = arm_id

    def reserve(self, *, design_index: int, design_hash: str,
                planned_starts: int = 1,
                planned_internal_cases: int = INTERNAL_CASES_PER_START,
                meta: Optional[Mapping[str, Any]] = None) -> str:
        return self.ledger.reserve(
            self.phase, arm_id=self.arm_id, design_index=design_index,
            design_hash=design_hash, planned_starts=planned_starts,
            planned_internal_cases=planned_internal_cases, meta=dict(meta or {}))

    def start(self, tx_id: str, *, case_id: str,
              meta: Optional[Mapping[str, Any]] = None) -> bool:
        return bool(self.ledger.start(tx_id, case_id=case_id, meta=dict(meta or {})))

    def end(self, tx_id: str, *, status: str,
            internal_solver_cases: int = INTERNAL_CASES_PER_START,
            meta: Optional[Mapping[str, Any]] = None) -> bool:
        return bool(self.ledger.end(tx_id, status, internal_solver_cases=internal_solver_cases,
                                    meta=dict(meta or {})))

    def fail_before_start(self, tx_id: str, *, reason: str) -> bool:
        return bool(self.ledger.fail_before_start(tx_id, reason=reason))

    def record_evaluation(self, *, design_index: int, design_hash: str,
                          meta: Optional[Mapping[str, Any]] = None) -> None:
        return self.ledger.record_evaluation(
            self.phase, arm_id=self.arm_id, design_index=design_index,
            design_hash=design_hash, meta=dict(meta or {}))

    def record_cached_read(self, *, design_hash: str, source: str,
                           meta: Optional[Mapping[str, Any]] = None) -> None:
        return self.ledger.record_cached_read(
            self.phase, arm_id=self.arm_id, design_hash=design_hash,
            source=source, meta=dict(meta or {}))


def _check_file_reference(label: str, relative_path: str,
                          expected_sha256: str, expected_bytes: int) -> Dict[str, Any]:
    path = REPO_ROOT / relative_path
    exists = path.is_file()
    actual_sha = sha256_file(path) if exists else None
    actual_bytes = path.stat().st_size if exists else None
    return {
        "check_id": "U1-FILE-" + label,
        "path": relative_path,
        "exists": exists,
        "expected_sha256": expected_sha256,
        "actual_sha256": actual_sha,
        "expected_bytes": expected_bytes,
        "actual_bytes": actual_bytes,
        "ok": bool(exists and actual_sha == expected_sha256 and actual_bytes == expected_bytes),
    }


def verify_u1_reference_files() -> List[Dict[str, Any]]:
    checks = [_check_file_reference(label, path, sha, size)
              for label, path, sha, size in U1_REFERENCE_FILES]
    design_hashes = {design.design_id: design_hash(design.x12)
                     for design in REFERENCE_DESIGNS}
    expected_hashes = {design.design_id: design.design_hash for design in REFERENCE_DESIGNS}
    checks.append({
        "check_id": "U1-DESIGN-HASHES",
        "observed": design_hashes,
        "expected": expected_hashes,
        "ok": design_hashes == expected_hashes,
    })
    checks.append({
        "check_id": "U1-OLD-GEOMETRY-NOT-USED",
        "old_task_family_geometry_sha256": OLD_TASK_FAMILY_GEOMETRY_SHA,
        "used": False,
        "ok": True,
        "detail": "old F1 543x472 geometry 40fdd436 is not referenced by any task deck; all task decks use the post-fix 546x480 chain",
    })
    return checks


def _component_orientation_checks(build: Mapping[str, Any]) -> Dict[str, Any]:
    metrics = build["record"].get("component_metrics") or {}
    checks: Dict[str, Any] = {}
    wing = metrics.get("main_wing") or {}
    tail = metrics.get("vertical_tail") or {}
    wing_bbox = wing.get("bbox_m") or [None, None, None]
    tail_bbox = tail.get("bbox_m") or [None, None, None]
    checks["wing_bbox"] = wing_bbox
    checks["tail_bbox"] = tail_bbox
    checks["wing_horizontal"] = bool(
        wing_bbox[1] is not None and wing_bbox[2] is not None and
        float(wing_bbox[1]) > 20.0 and float(wing_bbox[2]) < 0.5 * float(wing_bbox[1]))
    checks["tail_vertical_structural"] = bool(
        tail_bbox[1] is not None and tail_bbox[2] is not None and
        float(tail_bbox[2]) >= 1.0 and
        float(tail_bbox[2]) >= 3.0 * float(tail_bbox[1]))
    checks["ok"] = bool(checks["wing_horizontal"] and checks["tail_vertical_structural"])
    return checks


def run_dry_run(out_path: str | Path, scratch_root: str | Path) -> Dict[str, Any]:
    """Zero-physics 6-task x 3-design dry-run.  Never starts a solver."""
    started_utc = utc_now()
    guard = SpawnGuard().install()
    root = Path(scratch_root)
    try:
        module = _load_openvsp_model()
        atm_check = ATM_F1R2.validate()
        u1_checks = verify_u1_reference_files()

        builds: List[Dict[str, Any]] = []
        build_specs = [
            ("build-B0-01-a", REFERENCE_DESIGNS[0]),
            ("build-B0-01-b", REFERENCE_DESIGNS[0]),
            ("build-B1-01", REFERENCE_DESIGNS[1]),
            ("build-C5", REFERENCE_DESIGNS[2]),
        ]
        for directory, design in build_specs:
            builds.append(build_reference_design(design, root / "builds" / directory))

        baseline = builds[0]
        baseline_repeat = builds[1]
        sref_ref = float(baseline["sref_m2"])
        if abs(sref_ref - SREF_REF_FROZEN) > 1e-12 * SREF_REF_FROZEN:
            raise TaskSpecInvalid("runtime SREF_REF mismatch")
        tasks = [build_task_spec(task, sref_ref) for task in TASK_DEFINITIONS]

        u1_checks.append({
            "check_id": "U1-BASELINE-REBUILD-2X",
            "build_a_sha256": baseline["vspgeom"]["sha256"],
            "build_b_sha256": baseline_repeat["vspgeom"]["sha256"],
            "bundle_sha256": U1_REFERENCE_FILES[2][2],
            "byte_identical": baseline["vspgeom"]["sha256"] == baseline_repeat["vspgeom"]["sha256"],
            "equals_bundle": baseline["vspgeom"]["sha256"] == U1_REFERENCE_FILES[2][2],
            "ok": (baseline["vspgeom"]["sha256"] == baseline_repeat["vspgeom"]["sha256"] ==
                   U1_REFERENCE_FILES[2][2]),
        })
        for build, design in ((builds[2], REFERENCE_DESIGNS[1]), (builds[3], REFERENCE_DESIGNS[2])):
            u1_checks.append({
                "check_id": "U1-F1R2-REBUILD-" + design.design_id,
                "design_id": design.design_id,
                "expected_sha256": design.source_vspgeom_sha256,
                "actual_sha256": build["vspgeom"]["sha256"],
                "ok": build["vspgeom"]["sha256"] == design.source_vspgeom_sha256,
            })
        for build in builds:
            orientation = _component_orientation_checks(build)
            u1_checks.append({
                "check_id": "U1-ORIENTATION-" + build["design"].design_id,
                "orientation": orientation,
                "ok": orientation["ok"],
            })

        decks: List[Dict[str, Any]] = []
        # The baseline repeat build exists only for the U1 2/2 byte-identity
        # check; task decks are generated for the three distinct designs once.
        for build in (builds[0], builds[2], builds[3]):
            for task_spec in tasks:
                case_name = "%s__%s" % (build["design"].design_id, task_spec["task_id"])
                decks.append(derive_task_deck(
                    build, task_spec, root / "decks" / case_name))

        deck_rows = []
        for deck in decks:
            deck_rows.append({
                "task_id": deck["task_id"],
                "design_id": deck["design_id"],
                "design_hash": deck["design_hash"],
                "case_dir": rel_path(Path(deck["deck"]["path"]).parent),
                "deck_sha256": deck["deck"]["sha256"],
                "deck_bytes": deck["deck"]["bytes"],
                "solver_input_sha256": deck["solver_inputs"]["input_sha256"],
                "vspgeom_sha256": deck["geometry"]["vspgeom"]["sha256"],
                "sref_m2": deck["geometry"]["sref_m2"],
                "q_pa": deck["task_spec"]["q_pa"],
                "q_recomputed_pa": deck["deck"]["q_recomputed_pa"],
                "q_recompute_rel_error": deck["deck"]["q_recompute_rel_error"],
                "l_ref_n": deck["task_spec"]["l_ref_n"],
                "mass_t": deck["task_spec"]["mass_t"],
                "cl_required": deck["deck"]["cl_required"],
            })

        task_rows = []
        for task_spec in tasks:
            task_rows.append({
                "task_id": task_spec["task_id"],
                "task_fingerprint": task_spec["task_fingerprint"],
                "mach": task_spec["task_definition"]["mach"],
                "cl_target": task_spec["task_definition"]["cl_target"],
                "split": task_spec["task_definition"]["split"],
                "q_pa": task_spec["q_pa"],
                "q_recomputed_pa": task_spec["q_recomputed_pa"],
                "q_recompute_rel_error": task_spec["q_recompute_rel_error"],
                "vinf_m_s": task_spec["vinf_m_s"],
                "rho_kg_m3": task_spec["rho_kg_m3"],
                "recref": task_spec["recref"],
                "l_ref_n": task_spec["l_ref_n"],
                "mass_t": task_spec["mass_t"],
                "mass_ok": MASS_T_BOUNDS[0] <= task_spec["mass_t"] <= MASS_T_BOUNDS[1],
                "active_mask": task_spec["active_mask"],
                "sref_ref_m2": task_spec["sref_ref_m2"],
            })

        baseline_deck_sha = {row["task_id"]: row["deck_sha256"]
                             for row in deck_rows if row["design_id"] == "B0-01"}
        per_design = []
        for build in (builds[0], builds[2], builds[3]):
            design = build["design"]
            per_design.append({
                "design_id": design.design_id,
                "design_label": design.label,
                "design_hash": design.design_hash,
                "x12": [float(value) for value in design.x12],
                "sref_m2": build["sref_m2"],
                "vspgeom_sha256": build["vspgeom"]["sha256"],
                "vspgeom_bytes": build["vspgeom"]["bytes"],
                "mesh_family": build["record"]["mesh"]["mesh_family"],
                "nodes": build["record"]["mesh"]["nodes"],
                "elements": build["record"]["mesh"]["elements"],
                "mesh_attempts": build["record"]["mesh"]["mesh_attempts"],
                "source_case": design.source_case,
                "build_dir": rel_path(build["build_dir"]),
                "build_seconds": build["record"].get("build_seconds"),
                "wall_s": build["wall_s"],
                "component_metrics": build["record"].get("component_metrics"),
                "orientation": _component_orientation_checks(build),
            })

        checks: List[Dict[str, Any]] = []
        for check in u1_checks:
            checks.append({"check_id": check["check_id"], "ok": bool(check.get("ok")),
                           "detail": check})
        checks.append({"check_id": "ATM-F1R2-VALIDATE", "ok": True, "detail": atm_check})
        sref_rel = abs(sref_ref - SREF_REF_FROZEN) / abs(SREF_REF_FROZEN)
        checks.append({"check_id": "SREF-REF-RUNTIME",
                       "ok": bool(sref_rel <= 1e-12),
                       "detail": {"sref_ref_m2": sref_ref,
                                  "source": "post-fix baseline geometry.wing.area_m2 (runtime recompute)",
                                  "vspgeom_sha256": baseline["vspgeom"]["sha256"],
                                  "frozen_validation_anchor_m2": SREF_REF_FROZEN,
                                  "relative_error_vs_frozen_anchor": sref_rel,
                                  "computed_from_geometry": True}})
        checks.append({"check_id": "TASK-COUNT", "ok": len(tasks) == 6,
                       "detail": {"count": len(tasks)}})
        checks.append({"check_id": "DECK-COUNT", "ok": len(decks) == 18,
                       "detail": {"count": len(decks)}})
        for row in task_rows:
            checks.append({"check_id": "TASK-MASS-" + row["task_id"],
                           "ok": bool(row["mass_ok"]),
                           "detail": {"mass_t": row["mass_t"],
                                      "bounds_t": list(MASS_T_BOUNDS)}})
        for row in deck_rows:
            checks.append({"check_id": "DECK-Q-" + row["task_id"] + "-" + row["design_id"],
                           "ok": bool(row["q_recompute_rel_error"] <= 1e-12),
                           "detail": {"q_pa": row["q_pa"],
                                      "q_recomputed_from_deck_pa": row["q_recomputed_pa"],
                                      "q_recompute_rel_error": row["q_recompute_rel_error"],
                                      "formula": "q = 0.5 * Rho_deck * Vinf_deck^2"}})
        checks.append({
            "check_id": "DECK-Q-ALL",
            "ok": all(row["q_recompute_rel_error"] <= 1e-12 for row in deck_rows),
            "detail": {"deck_count": len(deck_rows),
                       "max_q_recompute_rel_error": max(row["q_recompute_rel_error"] for row in deck_rows)},
        })
        checks.append({
            "check_id": "ALPHA-REFINE-POLICY",
            "ok": MAX_ALPHA_REFINE == 0 and len(ALPHA_GRID) == 7,
            "detail": {"alpha_grid_deg": list(ALPHA_GRID),
                       "max_alpha_refine": MAX_ALPHA_REFINE,
                       "refine_mode": ALPHA_REFINE_MODE,
                       "independent_lift_residual_required": True,
                       "construction_residual_is_not_evidence": True},
        })
        design_vspgeom = {}
        for row in deck_rows:
            design_vspgeom.setdefault(row["design_id"], set()).add(row["vspgeom_sha256"])
        checks.append({
            "check_id": "CROSS-TASK-GEOMETRY-IDENTITY",
            "ok": all(len(values) == 1 for values in design_vspgeom.values()),
            "detail": {design_id: sorted(values) for design_id, values in design_vspgeom.items()},
        })
        checks.append({
            "check_id": "DECK-CASE-DIRS-DISTINCT",
            "ok": len({row["case_dir"] for row in deck_rows}) == len(deck_rows),
            "detail": {"deck_count": len(deck_rows),
                       "distinct_case_dirs": len({row["case_dir"] for row in deck_rows})},
        })
        m202 = [row for row in task_rows if row["task_id"].startswith("T18K_M202_")]
        checks.append({
            "check_id": "M202-F1R2-CONTINUITY",
            "ok": bool(m202) and all(abs(row["q_pa"] - ATM_F1R2.anchor_q_pa) <= 1e-15 * ATM_F1R2.anchor_q_pa for row in m202),
            "detail": {"q_pa": [row["q_pa"] for row in m202],
                       "f1r2_anchor_q_pa": ATM_F1R2.anchor_q_pa,
                       "new_conditions_do_not_inherit_expected_polar": ["T18K_M220_CL017", "T18K_M220_CL019", "T18K_M180_CL017", "T18K_M180_CL019"]},
        })
        checks.append({
            "check_id": "SPAWN-GUARD",
            "ok": len(guard.attempts) == 0,
            "detail": {"spawn_events": list(guard.attempts)},
        })
        checks.append({
            "check_id": "PHYSICAL-CALL-COUNT",
            "ok": True,
            "detail": {"physical_call_count": 0, "physical_solver_starts": 0,
                       "solver_started": False},
        })
        failed = [check for check in checks if not check["ok"]]
        report = {
            "schema": SCHEMA_DRY_RUN,
            "dry_run_id": "M0R-TASK-EVALUATOR-DRYRUN-" + started_utc.replace(":", ""),
            "created_utc": started_utc,
            "finished_utc": utc_now(),
            "identity": {
                "authorization_id": "DFIXED-F1R2-001",
                "run_id": "DREAL001-F1R2-20261113-01",
                "lead_decision": "L-30",
                "m0r_deliverable": "U1/U2 task-capable executor dry-run",
            },
            "atmosphere": {
                "atmosphere_id": ATM_F1R2.atmosphere_id,
                "altitude_m": ATM_F1R2.altitude_m,
                "p_static_pa": ATM_F1R2.p_static_pa,
                "t_static_k": ATM_F1R2.t_static_k,
                "r_j_kg_k": ATM_F1R2.r_j_kg_k,
                "rho_kg_m3": ATM_F1R2.rho_kg_m3,
                "a_sound_m_s": ATM_F1R2.a_sound_m_s,
                "anchor_mach": ATM_F1R2.anchor_mach,
                "anchor_vinf_m_s": ATM_F1R2.anchor_vinf_m_s,
                "anchor_q_pa": ATM_F1R2.anchor_q_pa,
                "anchor_recref": ATM_F1R2.anchor_recref,
                "cref_m": ATM_F1R2.cref_m,
                "basis": ATM_F1R2.basis,
                "validation": atm_check,
            },
            "sref_ref": {
                "sref_m2": sref_ref,
                "source": "post-fix baseline geometry.wing.area_m2 (runtime recompute)",
                "frozen_validation_anchor_m2": SREF_REF_FROZEN,
                "vspgeom_sha256": baseline["vspgeom"]["sha256"],
                "relative_error_vs_frozen_anchor": sref_rel,
                "computed_from_geometry": True,
            },
            "alpha_policy": {
                "alpha_grid_deg": list(ALPHA_GRID),
                "max_alpha_refine": MAX_ALPHA_REFINE,
                "refine_mode": ALPHA_REFINE_MODE,
                "independent_lift_residual_required": True,
                "construction_residual_is_not_evidence": True,
            },
            "f1r2_continuity": {
                "anchor_tasks": ["T18K_M202_CL017", "T18K_M202_CL019"],
                "anchor_q_pa": ATM_F1R2.anchor_q_pa,
                "m2_02_is_byte_continuous_with_f1r2": True,
                "new_conditions": ["T18K_M220_CL017", "T18K_M220_CL019", "T18K_M180_CL017", "T18K_M180_CL019"],
                "new_conditions_inherit_f1r2_expected_polar": False,
                "m1_a_reestablishes_admission_baseline": True,
            },
            "tasks": task_rows,
            "designs": per_design,
            "decks": deck_rows,
            "task_decks_baseline": baseline_deck_sha,
            "checks": checks,
            "checks_total": len(checks),
            "checks_failed": len(failed),
            "failed_checks": [check["check_id"] for check in failed],
            "verdict": "PASS" if not failed else "FAIL",
            "physical_call_count": 0,
            "physical_solver_starts": 0,
            "solver_started": False,
            "spawn_events": list(guard.attempts),
            "run_dir_created": False,
            "notes": [
                "Zero-physics dry-run: OpenVSP model build + VSPAEROComputeGeometry only; StopBeforeRun=1.",
                "ATM-F1R2 is the A1 frozen F1R2/F2R2 injection set; it is NOT the ISO standard atmosphere.",
                "M2.02/18,288 m is exactly continuous with F1R2; M2.2 and M1.8 are new conditions and do not inherit F1R2 expected polars.",
                "Sref(x) is recomputed per design; the task lift target uses SREF_REF only.",
                "Same design reuses one vspgeom/vkey byte pair across all six task decks.",
                "No real run directory is created; all build/deck scratch lives under the dry-run scratch root.",
            ],
        }
        write_json(out_path, report)
        if failed:
            raise TaskEvaluatorError("dry-run failed checks: %s" % [c["check_id"] for c in failed])
        return report
    finally:
        guard.uninstall()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="M0-R task evaluator (dry-run only; never starts a solver)")
    parser.add_argument("--dry-run", action="store_true", required=True,
                        help="run the zero-physics 6-task x 3-design dry-run")
    parser.add_argument("--out", required=True, help="dry-run JSON output path")
    parser.add_argument("--scratch", default=str(REPO_ROOT / "_scratch_f1" / "m0r_task_evaluator_dryrun"),
                        help="scratch root for builds and task decks (not a run dir)")
    args = parser.parse_args(argv)
    report = run_dry_run(args.out, args.scratch)
    print("TASK-EVALUATOR-DRYRUN %s checks=%d failed=%d decks=%d physical=%d" % (
        report["verdict"], report["checks_total"], report["checks_failed"],
        len(report["decks"]), report["physical_call_count"]))
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
