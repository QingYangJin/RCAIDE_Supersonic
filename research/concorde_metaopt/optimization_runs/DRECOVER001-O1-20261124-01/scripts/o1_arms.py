"""O1: the three-arm warm-start comparison required by Issue #15 section 6.

    SOBOL_BO                -- three LHS extra initialisation designs, then the shared GP
    COND_SUPERVISED_KSHOT_BO -- three designs chosen by the frozen 16D conditional
                               supervised checkpoint after K=3 support adaptation
    COND_FOMAML_KSHOT_BO    -- the same, from the frozen 16D conditional FOMAML checkpoint

Everything else is held equal and lives in this one module so it cannot drift:

* one shared support set of three real designs (baseline plus two LHS draws), evaluated
  once for real and charged in full, as equivalent cost, to every arm;
* one pre-generated candidate pool of coordinates (no truth is ever pre-computed for it);
* one GP/acquisition backend with identical hyperparameters and seed;
* one coarse/refine alpha recipe, one lift tolerance, one audit gate, one admission gate.

The only thing an arm is allowed to influence is which three extra designs it starts from.
After that, each arm's adaptively proposed designs come from the same GP fed only with
that arm's own real feedback.

Cost model (preregistered): one design = two charged VSPAERO starts and 20 internal alpha
cases (7 coarse + 13 refine). Per arm per pairing the caps are 12 designs / 24 starts /
160 internal, and 160 internal binds, so an arm can afford exactly eight designs: the
three shared support designs plus three warm-start designs plus two adaptive designs.
Three arms therefore cost 48 equivalent starts and 480 internal cases; the three shared
support designs are solved once, so the physical bill is 36 starts.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
A0_RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01")
sys.path.insert(0, str(REPO))

from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC  # noqa: E402
from research.concorde_metaopt.dreal001.meta.meta_dataset import (  # noqa: E402
    Observation, TrainNormalizer,
)
from research.concorde_metaopt.dreal001.meta.production import (  # noqa: E402
    TaskContext, context_features,
)
from research.concorde_metaopt.dreal001.meta.real_a0_ablation import (  # noqa: E402
    DEFAULT_FEATURE_SPEC, _append_context, _forward_np, _maml, _maml_config,
)
from research.concorde_metaopt.dreal001.ops import o0_short_bo as o0  # noqa: E402
from research.concorde_metaopt.dreal001.optimizers import recovery_bo  # noqa: E402

import o1_eval as ev  # noqa: E402

SCHEMA = "dreal005.o1_three_arm.v1"
PROTOCOL_ID = "O1-THREE-ARM-20261124"

ARMS: Tuple[str, ...] = ("SOBOL_BO", "COND_SUPERVISED_KSHOT_BO", "COND_FOMAML_KSHOT_BO")
CHECKPOINT_ARM = {
    "COND_SUPERVISED_KSHOT_BO": "COND_SUPERVISED_16D",
    "COND_FOMAML_KSHOT_BO": "COND_FOMAML_16D",
}

# The frozen local subspace and the alpha recipe are inherited verbatim from O0: the
# contract requires one geometry/alpha algorithm shared by every arm.
SUBSPACE_LOWER = o0.SUBSPACE_LOWER
SUBSPACE_UPPER = o0.SUBSPACE_UPPER
ALPHA_PLAN = o0.alpha_plan()

SHARED_SUPPORT_COUNT = 3
WARM_START_COUNT = 3
SHARED_SUPPORT_SEED = 20261124
WARM_START_SEED = 20261125
CANDIDATE_POOL_COUNT = 256
CANDIDATE_POOL_SEED = 20261126
GP_SEED = 7
PAIRING_SEED = 7
K_SUPPORT = 3

INTERNAL_PER_DESIGN = ALPHA_PLAN["coarse_internal_cases"] + ALPHA_PLAN["refine_internal_cases"]
STARTS_PER_DESIGN = 2

CAPS = {
    "max_designs_per_arm": 12,
    "max_starts_per_arm": 24,
    "max_internal_per_arm": 160,
    "max_starts_per_design": 3,
    "max_internal_per_design": 20,
    "max_designs_all_arms": 36,
    "max_starts_all_arms": 72,
    "max_internal_all_arms": 480,
    # 160 internal / 20 per design binds before the 12-design and 24-start caps do.
    "affordable_designs_per_arm": 8,
    "solver_timeout_s": o0.CAPS["solver_timeout_s"],
    "parallelism": 1,
    "retries": 0,
}

# Preregistered target, fixed before any O1 result exists. The reference point is the
# pre-designated baseline design inside the shared support; a 0.1% Di reduction is used
# because it is an order of magnitude above the 1e-3 relative lift tolerance that bounds
# the reported drag, and because O0 already demonstrated a 0.2394% effect is reachable.
TARGET_IMPROVEMENT_FRACTION = 1e-3


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode("utf-8")).hexdigest()


def support_designs() -> List[Tuple[float, ...]]:
    """Three pre-designated shared support designs; the baseline is always the first."""
    points = recovery_bo.generate_initial_designs(SUBSPACE_LOWER, SUBSPACE_UPPER,
                                                  count=SHARED_SUPPORT_COUNT,
                                                  seed=SHARED_SUPPORT_SEED)
    designs = [tuple(float(v) for v in o0.subspace_to_design(p)) for p in points]
    designs[0] = tuple(float(v) for v in o0.BASELINE_X12)
    unique: List[Tuple[float, ...]] = []
    for design in designs:
        if not any(np.max(np.abs(np.array(design) - np.array(old))) <= 1e-12 for old in unique):
            unique.append(design)
    if len(unique) != SHARED_SUPPORT_COUNT:
        raise RuntimeError("shared support designs collapsed to %d" % (len(unique),))
    return unique


def candidate_pool() -> List[Tuple[float, ...]]:
    """The common candidate pool: coordinates only, never a pre-computed objective."""
    points = recovery_bo.generate_initial_designs(SUBSPACE_LOWER, SUBSPACE_UPPER,
                                                  count=CANDIDATE_POOL_COUNT,
                                                  seed=CANDIDATE_POOL_SEED)
    return [tuple(float(v) for v in o0.subspace_to_design(p)) for p in points]


def sobol_warm_start() -> List[Tuple[float, ...]]:
    points = recovery_bo.generate_initial_designs(SUBSPACE_LOWER, SUBSPACE_UPPER,
                                                  count=WARM_START_COUNT,
                                                  seed=WARM_START_SEED)
    return [tuple(float(v) for v in o0.subspace_to_design(p)) for p in points]


def load_a0_normalizer() -> TrainNormalizer:
    payload = json.loads((A0_RUN / "training" / "a0_normalizer.json").read_text(encoding="utf-8"))
    return TrainNormalizer(
        x_mean=np.array(payload["x_mean"], dtype=float),
        x_scale=np.array(payload["x_scale"], dtype=float),
        y_mean=float(payload["y_mean"]), y_scale=float(payload["y_scale"]),
        fit_observation_ids=tuple(payload["fit_observation_ids"]),
    )


def load_checkpoint(arm_name: str) -> Tuple[Any, Dict[str, Any]]:
    """Load the frozen A0 checkpoint for a K-shot arm, with the grid-selected config."""
    grid = json.loads((A0_RUN / "training" / "a0_grid_search.json").read_text(encoding="utf-8"))
    chosen = grid["chosen"][arm_name]
    config = o0cfg = None
    from research.concorde_metaopt.dreal001.meta.real_a0_ablation import AblationConfig
    base = AblationConfig()
    config = base.replace(inner_lr=float(chosen["inner_lr"]),
                          inner_steps=int(chosen["inner_steps"]),
                          seed=PAIRING_SEED, validation_k=1)
    maml_cfg = _maml_config(16, config)
    path = A0_RUN / "training" / "checkpoints" / ("%s_k3_seed7.npz" % (arm_name,))
    if not path.exists():
        raise FileNotFoundError("missing A0 checkpoint %s" % (path,))
    with np.load(path) as data:
        keys = sorted(data.files)
        tensors = [np.array(data[k], dtype=float) for k in keys]
    params = _maml().ParameterSet(tensors=tensors)
    return params, {"checkpoint_path": str(path), "checkpoint_sha256": sha(path),
                    "maml_config": maml_cfg.to_dict(), "ablation_config": config.as_dict(),
                    "grid_selection": chosen, "tensor_names": keys,
                    "input_dim": maml_cfg.input_dim}


def _unit_designs(designs: Sequence[Sequence[float]],
                  normalizer: TrainNormalizer) -> np.ndarray:
    matrix = np.asarray(designs, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != 12:
        raise ValueError("design matrix must be (N, 12)")
    return (matrix - normalizer.x_mean) / normalizer.x_scale


def kshot_ranked_candidates(arm_name: str, task_key: str,
                            support_rows: Sequence[Observation],
                            pool: Sequence[Tuple[float, ...]]) -> Dict[str, Any]:
    """Rank the common candidate pool with one frozen K-shot model, no feedback used."""
    params, checkpoint_meta = load_checkpoint(arm_name)
    normalizer = load_a0_normalizer()
    maml_cfg = _maml().MAMLConfig(**checkpoint_meta["maml_config"])
    task = ev.task_spec(task_key)
    cl_target = task.lift_target_n / (task.dynamic_pressure_pa * 358.25)
    context = context_features(task, TaskContext(cl_target=cl_target), DEFAULT_FEATURE_SPEC)
    if len(support_rows) != K_SUPPORT:
        raise ValueError("K-shot arm needs %d support rows, got %d"
                         % (K_SUPPORT, len(support_rows)))
    sx, sy = normalizer.arrays(list(support_rows))
    sx16 = _append_context(sx, context)
    episode = _maml().TaskEpisode(sx16, sy, sx16[:1], np.zeros((1, 1)), "support_only")
    adapted, inner_losses = _maml().inner_adapt(params, episode, maml_cfg)
    unit = _unit_designs(pool, normalizer)
    unit16 = _append_context(unit, context)
    predicted = _forward_np(adapted, unit16)[:, 0] * normalizer.y_scale + normalizer.y_mean
    if not np.all(np.isfinite(predicted)):
        raise ValueError("nonfinite K-shot prediction")
    order = np.argsort(predicted, kind="stable")
    return {
        "arm": arm_name,
        "task_id": task.task_id,
        "support_observation_ids": [row.observation_id for row in support_rows],
        "context_vector": [float(v) for v in context],
        "inner_losses": [float(v) for v in inner_losses],
        "predicted_min": float(predicted.min()),
        "predicted_max": float(predicted.max()),
        "predicted_mean": float(predicted.mean()),
        "order": [int(i) for i in order],
        "predicted": predicted,
        "checkpoint": checkpoint_meta,
    }


@dataclass
class DesignRecord:
    arm: str
    role: str
    design_index: int
    tag: str
    x12: Tuple[float, ...]
    design_id: str = ""
    is_baseline: bool = False
    starts: int = 0
    internal: int = 0
    status: str = "PENDING"
    feasible: bool = False
    di_n: Optional[float] = None
    cl: Optional[float] = None
    cdi: Optional[float] = None
    alpha_deg: Optional[float] = None
    sref_m2: Optional[float] = None
    q_pa: Optional[float] = None
    lift_rel_error: Optional[float] = None
    failure_kind: Optional[str] = None
    detail: str = ""
    case_ids: List[str] = field(default_factory=list)
    acquisition: Dict[str, Any] = field(default_factory=dict)
    predicted_di_n: Optional[float] = None
    admission_certificate_path: Optional[str] = None
    admission_certificate_sha256: Optional[str] = None
    audit_path: Optional[str] = None

    def __post_init__(self) -> None:
        ident = o0.design_identity(list(self.x12))
        self.design_id = ident["design_id"]
        self.is_baseline = bool(ident["is_baseline"])
        if not self.tag:
            self.tag = "d%02d" % (self.design_index,)

    def as_dict(self) -> Dict[str, Any]:
        payload = dict(self.__dict__)
        payload["x12"] = list(self.x12)
        return payload


class ArmLedger:
    """Per-arm accounting, with the shared support cost carried in full."""

    def __init__(self, arm: str) -> None:
        self.arm = arm
        self.records: List[DesignRecord] = []
        self.shared_support_carried = False

    def add(self, record: DesignRecord) -> None:
        if len(self.records) >= CAPS["affordable_designs_per_arm"]:
            raise RuntimeError("%s would exceed the affordable design count of %d"
                               % (self.arm, CAPS["affordable_designs_per_arm"]))
        self.records.append(record)

    def totals(self) -> Dict[str, int]:
        return {
            "designs": len(self.records),
            "starts": sum(r.starts for r in self.records),
            "internal": sum(r.internal for r in self.records),
            "admitted": sum(1 for r in self.records if r.feasible),
            "failed": sum(1 for r in self.records if not r.feasible and r.status != "PENDING"),
        }

    def carry_shared_support(self, support_records: Sequence[DesignRecord]) -> None:
        if self.shared_support_carried:
            raise RuntimeError("shared support already carried into %s" % (self.arm,))
        for record in support_records:
            if not record.feasible:
                raise RuntimeError("shared support design %s was not admitted; O1 cannot "
                                   "pretend the support is real" % (record.tag,))
            clone = DesignRecord(arm=self.arm, role="shared_support",
                                 design_index=record.design_index, tag=record.tag,
                                 x12=record.x12, starts=record.starts,
                                 internal=record.internal, status=record.status,
                                 feasible=record.feasible, di_n=record.di_n, cl=record.cl,
                                 cdi=record.cdi, alpha_deg=record.alpha_deg,
                                 sref_m2=record.sref_m2, q_pa=record.q_pa,
                                 lift_rel_error=record.lift_rel_error,
                                 detail="equivalent cost of one shared support design",
                                 case_ids=list(record.case_ids),
                                 admission_certificate_path=record.admission_certificate_path,
                                 admission_certificate_sha256=record.admission_certificate_sha256,
                                 audit_path=record.audit_path)
            self.records.append(clone)
        self.shared_support_carried = True

    def best_feasible(self) -> Optional[DesignRecord]:
        feasible = [r for r in self.records if r.feasible and r.di_n is not None]
        if not feasible:
            return None
        return min(feasible, key=lambda r: (r.di_n, r.design_index))

    def anytime(self) -> List[Dict[str, Any]]:
        curve = []
        best = None
        cumulative_starts = 0
        cumulative_internal = 0
        for index, record in enumerate(self.records):
            cumulative_starts += record.starts
            cumulative_internal += record.internal
            if record.feasible and record.di_n is not None:
                best = record.di_n if best is None else min(best, record.di_n)
            curve.append({
                "step": index + 1, "design_index": record.design_index,
                "role": record.role, "tag": record.tag, "design_id": record.design_id,
                "starts": record.starts, "internal": record.internal,
                "cumulative_starts": cumulative_starts,
                "cumulative_internal": cumulative_internal,
                "feasible": record.feasible, "di_n": record.di_n,
                "best_so_far": best, "status": record.status,
            })
        return curve


def evaluate_design(task_key: str, group: str, record: DesignRecord,
                    attempt_log: Optional[Path] = None) -> DesignRecord:
    """One real design evaluation: coarse bracket, refine, audit, admission.

    Two charged starts and twenty internal alpha cases, charged whether or not the
    design ends up admitting a raw row. This is the same code path for every arm.
    """
    trace: List[Dict[str, Any]] = []
    tag = record.tag
    case_ids: List[str] = []
    # The shared support designs are support rows and every other design is a query row.
    # The partition is carried into the task spec and therefore into the certificate.
    partition = "support" if record.role == "shared_support" else "query"
    try:
        cl_target = ev.cl_target_for(task_key, list(record.x12))
        coarse_alphas = o0.coarse_alphas()
        coarse = ev.make_case(task_key, group, list(record.x12), tag, "coarse",
                              coarse_alphas, cl_target, o0.COARSE_ALPHA_GUESS_DEG,
                              partition=partition)
        case_ids.append(coarse["case_id"])
        result = ev.run(coarse, "%s-%s-coarse" % (group, tag))
        record.starts += int(result.get("physical_solver_starts", 0))
        record.internal += int(result.get("internal_solver_cases", 0))
        trace.append({"stage": "coarse", "case_id": coarse["case_id"],
                      "status": result.get("status"), "starts": record.starts,
                      "internal": record.internal})
        if result.get("status") != "SOLVED":
            record.status = "COARSE_%s" % (result.get("status"),)
            record.failure_kind = "SOLVER_NO_RESULT"
            record.detail = "coarse start did not solve"
            return record
        rows = ev.bracket_rows(result)
        prediction = o0.predict_alpha(rows, cl_target)
        if not prediction.get("ok"):
            record.status = "COARSE_BRACKET_NOT_USABLE"
            record.failure_kind = "ALPHA_BRACKET"
            record.detail = str(prediction.get("reason") or "coarse bracket rejected")
            return record
        center = float(prediction["predicted_alpha_deg"])
        refine_alphas = o0.refine_alphas(center)
        refine = ev.make_case(task_key, group, list(record.x12), tag, "refine",
                              refine_alphas, cl_target, center, partition=partition)
        case_ids.append(refine["case_id"])
        result2 = ev.run(refine, "%s-%s-refine" % (group, tag))
        record.starts += int(result2.get("physical_solver_starts", 0))
        record.internal += int(result2.get("internal_solver_cases", 0))
        trace.append({"stage": "refine", "case_id": refine["case_id"],
                      "status": result2.get("status"), "starts": record.starts,
                      "internal": record.internal})
        if result2.get("status") != "SOLVED":
            record.status = "REFINE_%s" % (result2.get("status"),)
            record.failure_kind = "SOLVER_NO_RESULT"
            record.detail = "refine start did not solve"
            return record
        audit_id = "O1-AUDIT-%s" % (refine["case_id"],)
        audit = ev.audit_case(refine["case_id"], group, task_key, audit_id)
        trace.append({"stage": "audit", "returncode": audit["returncode"],
                      "audit_sha256": audit["audit_sha256"]})
        if audit["returncode"] != 0:
            record.status = "AUDIT_FAILED"
            record.failure_kind = "NO_RAW_ROW_IN_LIFT_TOLERANCE"
            record.detail = (audit["stderr"] or audit["stdout"] or "")[-600:]
            return record
        record.audit_path = audit["audit_path"]
        admission_id = "O1-ADM-%s" % (refine["case_id"],)
        admitted = ev.admit_case(refine["case_id"], group, task_key, admission_id, audit_id,
                                 tag, partition=partition, split="train")
        trace.append({"stage": "admission", "returncode": admitted["returncode"],
                      "certificate_sha256": admitted["certificate_sha256"]})
        if admitted["returncode"] != 0:
            record.status = "ADMISSION_FAILED"
            record.failure_kind = "ADMISSION_CONTRACT"
            record.detail = (admitted["stderr"] or admitted["stdout"] or "")[-600:]
            return record
        cert = admitted["certificate"]
        record.status = "FEASIBLE_ADMITTED"
        record.feasible = True
        record.di_n = float(cert["di_n"])
        record.cl = float(cert["cl"])
        record.cdi = float(cert["cdi"])
        record.alpha_deg = float(cert["alpha_deg"])
        record.sref_m2 = float(cert["sref_m2"])
        record.q_pa = float(cert["q_pa"])
        record.lift_rel_error = abs(record.q_pa * record.sref_m2 * record.cl
                                    - ev.LIFT) / ev.LIFT
        record.admission_certificate_path = admitted["certificate_path"]
        record.admission_certificate_sha256 = admitted["certificate_sha256"]
        record.detail = "raw row admitted at %.6f deg" % (record.alpha_deg,)
        return record
    finally:
        record.case_ids = case_ids
        record.acquisition.setdefault("trace", []).extend(trace)
        if attempt_log is not None:
            with open(attempt_log, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"utc": ev.now(), "design": record.as_dict()},
                                        ensure_ascii=False) + "\n")


def support_rows_from_records(task_key: str,
                              records: Sequence[DesignRecord]) -> List[Observation]:
    task = ev.task_spec(task_key)
    rows = []
    for index, record in enumerate(records):
        if not record.feasible:
            raise RuntimeError("support design %s is not admitted" % (record.tag,))
        rows.append(Observation(
            observation_id="O1-SUPPORT-%s-%02d" % (task_key, index),
            task_id=task.task_id, design=tuple(float(v) for v in record.x12),
            partition="support", source_kind="vspaero_raw", status="ok",
            di_n=float(record.di_n), q_pa=float(record.q_pa),
            sref_m2=float(record.sref_m2), cdi=float(record.cdi), cl=float(record.cl),
            raw_sha256=record.admission_certificate_sha256,
        ))
    return rows


def run_arm(task_key: str, arm: str, support_records: Sequence[DesignRecord],
            attempt_log: Path, pool: Sequence[Tuple[float, ...]],
            warm_start: Sequence[Tuple[float, ...]],
            warm_start_meta: Dict[str, Any]) -> Dict[str, Any]:
    """Run one arm: three warm-start designs, then the shared GP for the rest."""
    ledger = ArmLedger(arm)
    ledger.carry_shared_support(support_records)
    support_rows = support_rows_from_records(task_key, support_records)
    group = "ARM_%s" % (arm,)

    used_ids = {record.design_id for record in ledger.records}
    warm: List[Tuple[float, ...]] = []
    for design in warm_start:
        design_id = o0.design_identity(list(design))["design_id"]
        if design_id in used_ids:
            continue
        used_ids.add(design_id)
        warm.append(design)
        if len(warm) == WARM_START_COUNT:
            break
    if len(warm) != WARM_START_COUNT:
        raise RuntimeError("%s could not produce %d distinct warm-start designs"
                           % (arm, WARM_START_COUNT))

    ranking = None
    if arm in CHECKPOINT_ARM:
        ranking = kshot_ranked_candidates(CHECKPOINT_ARM[arm], task_key, support_rows, pool)
        by_index = {index: design for index, design in enumerate(pool)}
        ordered = [by_index[i] for i in ranking["order"]]
        warm = []
        used_ids = {record.design_id for record in ledger.records}
        for design in ordered:
            design_id = o0.design_identity(list(design))["design_id"]
            if design_id in used_ids:
                continue
            used_ids.add(design_id)
            warm.append(design)
            if len(warm) == WARM_START_COUNT:
                break
        predicted_by_id = {}
        for index in ranking["order"]:
            predicted_by_id[o0.design_identity(list(pool[index]))["design_id"]] = \
                float(ranking["predicted"][index])

    bo = recovery_bo.RecoveryGaussianProcessBO(SUBSPACE_LOWER, SUBSPACE_UPPER, seed=GP_SEED)
    for record in ledger.records:
        bo.tell(o0.design_to_subspace(list(record.x12)),
                {"valid": True, "feasible": True, "objective": float(record.di_n)})

    design_index = len(ledger.records)
    for design in warm:
        record = DesignRecord(arm=arm, role="warm_start", design_index=design_index,
                              tag="d%02d" % (design_index,), x12=tuple(design))
        if ranking is not None:
            record.predicted_di_n = predicted_by_id.get(record.design_id)
        ledger.add(record)
        evaluate_design(task_key, group, record, attempt_log)
        bo.tell(o0.design_to_subspace(list(record.x12)),
                {"valid": bool(record.feasible), "feasible": bool(record.feasible),
                 "objective": float(record.di_n) if record.feasible else None})
        design_index += 1

    adaptive = 0
    while len(ledger.records) < CAPS["affordable_designs_per_arm"]:
        ask = bo.ask()
        point = [float(v) for v in ask["design_vector"]]
        x12 = [float(v) for v in o0.subspace_to_design(point)]
        o0.check_design(x12)
        record = DesignRecord(arm=arm, role="adaptive", design_index=design_index,
                              tag="d%02d" % (design_index,), x12=tuple(x12),
                              acquisition=dict(ask["acquisition"]))
        ledger.add(record)
        evaluate_design(task_key, group, record, attempt_log)
        bo.tell(o0.design_to_subspace(list(record.x12)),
                {"valid": bool(record.feasible), "feasible": bool(record.feasible),
                 "objective": float(record.di_n) if record.feasible else None})
        design_index += 1
        adaptive += 1

    totals = ledger.totals()
    if totals["internal"] > CAPS["max_internal_per_arm"]:
        raise RuntimeError("%s spent %d internal > %d"
                           % (arm, totals["internal"], CAPS["max_internal_per_arm"]))
    if totals["starts"] > CAPS["max_starts_per_arm"]:
        raise RuntimeError("%s spent %d starts > %d"
                           % (arm, totals["starts"], CAPS["max_starts_per_arm"]))
    baseline = next((r for r in ledger.records if r.is_baseline and r.feasible), None)
    best = ledger.best_feasible()
    return {
        "schema": SCHEMA, "protocol_id": PROTOCOL_ID, "arm": arm,
        "task_id": task_key,
        "group": group,
        "warm_start": [list(d) for d in warm],
        "warm_start_meta": warm_start_meta,
        "ranking": None if ranking is None else {
            key: value for key, value in ranking.items() if key != "predicted"},
        "records": [record.as_dict() for record in ledger.records],
        "totals": totals,
        "baseline_di_n": None if baseline is None else float(baseline.di_n),
        "best_feasible_di_n": None if best is None else float(best.di_n),
        "best_feasible_tag": None if best is None else best.tag,
        "best_feasible_design_id": None if best is None else best.design_id,
        "anytime": ledger.anytime(),
        "adaptive_designs": adaptive,
        "physical_solver_starts_actual": sum(
            r.starts for r in ledger.records if r.role != "shared_support"),
        "equivalent_starts_actual": totals["starts"],
        "internal_solver_cases_actual": totals["internal"],
        "physics_validated": False,
        "evidence_scope": "VSPAERO_INTERNAL_ONLY",
    }
