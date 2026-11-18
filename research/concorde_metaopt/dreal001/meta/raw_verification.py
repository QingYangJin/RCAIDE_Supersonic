"""Offline artifact consistency only; never authenticates a run or admits real labels.

REGENERATED_FROM_SPEC. Caller-supplied hashes bind bytes, not provenance. A
consistent synthetic bundle still passes these checks and MUST remain unadmitted.
Only an actual polar row already meeting the lift tolerance is selected; no
interpolated value is silently promoted to an observed solver label.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re

from ..geometry.polar_parser import PolarParseError, parse_polar_text
from .task_spec import ContractError, TaskSpec, canonical_sha


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-12)


@dataclass(frozen=True)
class ArtifactBinding:
    task_physics_sha256: str
    design_sha256: str
    geometry_contract_sha256: str
    mesh_sha256: str
    deck_sha256: str
    polar_sha256: str
    sref_m2: float
    rho_kg_m3: float
    vinf_m_s: float
    recref: float
    alpha_grid_deg: tuple[float, ...]

    def __post_init__(self):
        for name in ("task_physics_sha256", "design_sha256", "geometry_contract_sha256",
                     "mesh_sha256", "deck_sha256", "polar_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ContractError("invalid artifact SHA256: " + name)
        for name in ("sref_m2", "rho_kg_m3", "vinf_m_s", "recref"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ContractError("invalid positive artifact condition: " + name)
        grid = tuple(float(x) for x in self.alpha_grid_deg)
        if not grid or not all(math.isfinite(x) for x in grid) or len(set(grid)) != len(grid):
            raise ContractError("alpha grid must be finite, unique and nonempty")
        object.__setattr__(self, "alpha_grid_deg", grid)


@dataclass(frozen=True)
class ConsistentRawCandidate:
    """NOT an Observation or an admission certificate; provenance remains unverified."""
    binding: ArtifactBinding
    alpha_deg: float
    cl: float
    cdi: float
    di_n: float
    lift_rel_error: float
    raw_row_count: int
    unique_case_count: int
    evidence_scope: str = "OFFLINE_ARTIFACT_CONSISTENCY_ONLY"
    real_admission: bool = False


def verify_artifact_bundle(*, task: TaskSpec, design, binding: ArtifactBinding,
                           mesh: bytes, deck: bytes, polar: bytes) -> ConsistentRawCandidate:
    """Check bound bytes, task/deck/flow/grid, finite rows and actual matched lift.

    No solver invocation, ledger reset, geometry freeze, backup test or A5 approval.
    The design-to-mesh relation, atmospheric model, software version and provenance
    are intentionally NOT certified by a self-declared ArtifactBinding.
    """
    vector = tuple(float(x) for x in design)
    if len(vector) != 12 or not all(math.isfinite(x) for x in vector):
        raise ContractError("design must have 12 finite coordinates")
    identity = canonical_sha([0.0 if x == 0 else x for x in vector])
    if (identity != binding.design_sha256 or task.physics_sha256 != binding.task_physics_sha256
            or task.geometry_contract_sha256 != binding.geometry_contract_sha256):
        raise ContractError("task/design/geometry binding mismatch")
    for name, raw in (("mesh", mesh), ("deck", deck), ("polar", polar)):
        if not isinstance(raw, bytes) or not raw or _sha(raw) != getattr(binding, name + "_sha256"):
            raise ContractError(name + " bytes missing or SHA256 mismatch")
    try:
        deck_text, polar_text = deck.decode("utf-8"), polar.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("raw text must decode without replacement") from exc
    fields = {}
    for line in deck_text.splitlines():
        match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*", line)
        if match:
            key, value = match.groups()
            if key in fields:
                raise ContractError("duplicate deck field: " + key)
            fields[key] = value
    expected = {"Sref": binding.sref_m2, "Mach": task.mach, "Beta": 0.0,
                "Rho": binding.rho_kg_m3, "Vinf": binding.vinf_m_s, "ReCref": binding.recref}
    try:
        for key, value in expected.items():
            if not _close(float(fields[key]), value):
                raise ContractError("deck condition mismatch: " + key)
        grid = tuple(float(x.strip()) for x in fields["AoA"].split(","))
    except (KeyError, ValueError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError("missing or invalid deck condition") from exc
    if len(grid) != len(binding.alpha_grid_deg) or not all(
            _close(a, b) for a, b in zip(grid, binding.alpha_grid_deg)):
        raise ContractError("deck alpha grid mismatch")
    q = 0.5 * binding.rho_kg_m3 * binding.vinf_m_s ** 2
    if not _close(q, task.dynamic_pressure_pa):
        raise ContractError("deck dynamic pressure mismatches task")
    try:
        parsed = parse_polar_text(polar_text)
    except PolarParseError as exc:
        raise ContractError("invalid polar table") from exc
    # Existing parser uses only its primary table. Fail rather than hide another
    # potentially conflicting numeric section. Repeated rows in one table allowed
    # only when all named numeric payloads agree exactly.
    if len(parsed["sections"]) != 1 or len(set(parsed["header"])) != len(parsed["header"]):
        raise ContractError("ambiguous polar tables or duplicate columns")
    header = parsed["header"]
    row_lines = {row["_line"] for row in parsed["rows"]}
    header_line = parsed["sections"][0]["line"]
    for number, line in enumerate(polar_text.splitlines(), start=1):
        if number <= header_line or not line.strip():
            continue
        width = len(line.split())
        allowed_widths = {len(header)}
        if parsed["format_version"] == "v6":
            allowed_widths.add(len(header) + 1)  # documented unlabeled StallFactor
        if number not in row_lines or width not in allowed_widths:
            raise ContractError("unparsed or malformed polar payload line")
    rows = {}
    for row in parsed["rows"]:
        values = {key: value for key, value in row.items() if not key.startswith("_")}
        extras = row.get("_extra_unlabeled", [])
        if (set(values) != set(header) or not all(math.isfinite(v) for v in extras)
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values.values())):
            raise ContractError("nonfinite polar row")
        try:
            alpha, mach, beta = values["AoA"], values["Mach"], values["Beta"]
            cl = values["CLtot"] if "CLtot" in values else values["CL"]
            cdi, cdtot = values["CDi"], values["CDtot"]
        except KeyError as exc:
            raise ContractError("required polar column missing") from exc
        if (not _close(mach, task.mach) or not _close(beta, 0.0)
                or not any(_close(alpha, a) for a in grid)):
            raise ContractError("polar condition mismatches deck/task")
        if cdi < 0 or cdtot < cdi:
            raise ContractError("invalid induced/total drag coefficients")
        if alpha in rows and rows[alpha] != values:
            raise ContractError("conflicting duplicate polar case")
        rows[alpha] = values
    if len(rows) != len(grid) or not all(any(_close(a, g) for a in rows) for g in grid):
        raise ContractError("incomplete polar alpha grid")
    matched = []
    for alpha, row in rows.items():
        cl = row["CLtot"] if "CLtot" in row else row["CL"]
        error = abs(q * binding.sref_m2 * cl - task.lift_target_n) / task.lift_target_n
        if error <= task.lift_tolerance_rel:
            matched.append((error, alpha, cl, row["CDi"]))
    if not matched:
        raise ContractError("no actual raw row at matched lift; refinement required")
    error, alpha, cl, cdi = min(matched)
    di = q * binding.sref_m2 * cdi
    if not math.isfinite(di):
        raise ContractError("nonfinite dimensional drag")
    return ConsistentRawCandidate(binding, alpha, cl, cdi, di, error,
                                  len(parsed["rows"]), len(rows))
