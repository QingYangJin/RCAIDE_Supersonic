"""Regenerated task-to-deck/constraint binding; pure bytes, NEVER solver admission.

Caller-supplied flow is checked algebraically, not an atmospheric calibration.
Geometry/reference-point semantics, executable identity, raw provenance, backup and
independent approval must still be established before a production evaluator uses it.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import math
import re

from .task_spec import ContractError, TaskSpec, canonical_sha


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
        raise ContractError(name + " must be finite and positive")


def _close(a, b):
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


@dataclass(frozen=True)
class ProposedFlow:
    altitude_m: float
    rho_kg_m3: float
    vinf_m_s: float
    sound_speed_m_s: float
    dynamic_viscosity_pa_s: float
    cref_m: float

    def __post_init__(self):
        if isinstance(self.altitude_m, bool) or not math.isfinite(self.altitude_m) or self.altitude_m < 0:
            raise ContractError("flow altitude must be finite and nonnegative")
        for key in ("rho_kg_m3", "vinf_m_s", "sound_speed_m_s", "dynamic_viscosity_pa_s", "cref_m"):
            _positive(getattr(self, key), key)
        if not math.isfinite(self.q_pa) or not math.isfinite(self.recref):
            raise ContractError("nonfinite derived flow condition")

    @property
    def q_pa(self):
        return 0.5 * self.rho_kg_m3 * self.vinf_m_s ** 2

    @property
    def recref(self):
        return self.rho_kg_m3 * self.vinf_m_s * self.cref_m / self.dynamic_viscosity_pa_s


@dataclass(frozen=True)
class UnadmittedTaskDeck:
    task: TaskSpec
    flow: ProposedFlow
    deck: bytes
    sref_m2: float
    alpha_grid_deg: tuple[float, ...]

    @property
    def deck_sha256(self):
        return hashlib.sha256(self.deck).hexdigest()

    @property
    def constraints(self):
        # Fresh dictionary: a caller cannot mutate the bound constraint contract.
        return {"lift_target_n": self.task.lift_target_n,
                "lift_tolerance_rel": self.task.lift_tolerance_rel,
                "cl_target": self.task.lift_target_n / (self.task.dynamic_pressure_pa * self.sref_m2),
                "objective": "Di_N", "fuel_burn_kg": None}

    @property
    def evaluation_contract_sha256(self):
        # Equal deck SHA is possible at equal Mach/different lift targets. Cache
        # identity must include constraints, not only deck or arbitrary task_id.
        return canonical_sha({"task_physics": self.task.physics_sha256,
                              "deck": self.deck_sha256, "flow": asdict(self.flow),
                              "constraints": self.constraints})

    @property
    def evidence_scope(self):
        return "UNADMITTED_TASK_DECK_CONSTRAINT_BINDING_ONLY"

    @property
    def real_admission(self):
        return False


FIELD = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*?)(\s*)$")


def render_task_deck(base: bytes, *, task: TaskSpec, flow: ProposedFlow,
                     sref_m2: float, alpha_grid_deg) -> UnadmittedTaskDeck:
    """Return rewritten bytes plus lift contract; no filesystem/process side effects.

    Preserve all untouched lines and their endings. Refuse missing/duplicate fields
    instead of appending a misleading field which a solver might ignore.
    """
    _positive(sref_m2, "Sref")
    if (not _close(task.altitude_m, flow.altitude_m)
            or not _close(task.mach, flow.vinf_m_s / flow.sound_speed_m_s)
            or not _close(task.dynamic_pressure_pa, flow.q_pa)):
        raise ContractError("task/flow altitude, Mach or dynamic pressure mismatch")
    try:
        grid = tuple(float(v) for v in alpha_grid_deg)
    except (TypeError, ValueError) as exc:
        raise ContractError("alpha grid must be finite, unique and nonempty") from exc
    if not grid or len(set(grid)) != len(grid) or not all(math.isfinite(v) for v in grid):
        raise ContractError("alpha grid must be finite, unique and nonempty")
    if not isinstance(base, bytes) or not base:
        raise ContractError("nonempty base deck bytes required")
    try:
        text = base.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("base deck must be strict UTF8") from exc
    updates = {"Sref": format(sref_m2, ".17g"), "Mach": format(task.mach, ".17g"),
               "Cref": format(flow.cref_m, ".17g"), "Beta": "0",
               "Rho": format(flow.rho_kg_m3, ".17g"), "Vinf": format(flow.vinf_m_s, ".17g"),
               "ReCref": format(flow.recref, ".17g"),
               "AoA": ", ".join(format(v, ".17g") for v in grid)}
    seen, applied, lines = set(), set(), []
    for line in text.splitlines(keepends=True):
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        body = line[:-len(ending)] if ending else line
        match = FIELD.fullmatch(body)
        if match:
            prefix, key, equals, value, suffix = match.groups()
            if key in seen:
                raise ContractError("duplicate deck field: " + key)
            seen.add(key)
            if key in updates:
                body = prefix + key + equals + updates[key] + suffix
                applied.add(key)
        lines.append(body + ending)
    if applied != set(updates):
        raise ContractError("base deck missing fields: " + ",".join(sorted(set(updates) - applied)))
    return UnadmittedTaskDeck(task, flow, "".join(lines).encode("utf-8"), float(sref_m2), grid)
