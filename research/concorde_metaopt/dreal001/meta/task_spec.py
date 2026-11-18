"""New recovery contracts, REGENERATED_FROM_SPEC; no solver execution or approval."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass


class ContractError(ValueError):
    """A task or dataset cannot be admitted."""


def canonical_sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    split: str
    mach: float
    altitude_m: float
    dynamic_pressure_pa: float
    lift_target_n: float
    geometry_contract_sha256: str
    # A target force, NOT a constant CL for every varying design area.
    lift_tolerance_rel: float = 1e-3

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ContractError("task_id must be nonempty")
        if self.split not in {"train", "val", "test"}:
            raise ContractError("invalid task split")
        for name in ("mach", "altitude_m", "dynamic_pressure_pa",
                     "lift_target_n", "lift_tolerance_rel"):
            raw = getattr(self, name)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ContractError(f"{name} must be a finite number")
            value = float(raw)
            if not math.isfinite(value):
                raise ContractError(f"{name} must be finite")
            # Canonicalise numeric representation and signed zero. Otherwise the
            # same physical condition could acquire a new identity via 1 vs 1.0
            # or -0.0 vs 0.0, bypassing duplicate-physics checks.
            object.__setattr__(self, name, 0.0 if value == 0.0 else value)
        if (self.mach <= 0 or self.dynamic_pressure_pa <= 0
                or self.lift_target_n <= 0 or self.lift_tolerance_rel <= 0):
            raise ContractError("mach, dynamic_pressure_pa, lift_target_n and lift_tolerance_rel must be finite and positive")
        if self.altitude_m < 0:
            raise ContractError("altitude_m must be finite and nonnegative")
        if self.lift_tolerance_rel >= 1:
            raise ContractError("lift tolerance must be less than one")
        if (not isinstance(self.geometry_contract_sha256, str)
                or len(self.geometry_contract_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.geometry_contract_sha256)):
            raise ContractError("geometry contract requires lowercase SHA256")

    @property
    def physics_sha256(self) -> str:
        # Changing an id, split or random seed cannot create a new physical task.
        payload = asdict(self)
        del payload["task_id"]
        del payload["split"]
        return canonical_sha(payload)

    def solver_conditions(self, sref_m2: float) -> dict[str, float]:
        if not math.isfinite(sref_m2) or sref_m2 <= 0:
            raise ContractError("Sref must be finite and positive")
        return {"Mach": self.mach, "altitude_m": self.altitude_m,
                "q_pa": self.dynamic_pressure_pa, "Sref_m2": sref_m2,
                "L_ref_N": self.lift_target_n,
                "CL_target": self.lift_target_n / (self.dynamic_pressure_pa * sref_m2)}


def validate_task_family(tasks: tuple[TaskSpec, ...]) -> None:
    if not tasks or len({t.task_id for t in tasks}) != len(tasks):
        raise ContractError("empty family or duplicate task_id")
    identities = [t.physics_sha256 for t in tasks]
    if len(set(identities)) != len(identities):
        raise ContractError("duplicate physical task, including cross-split leakage")
    if {t.split for t in tasks} != {"train", "val", "test"}:
        raise ContractError("train/val/test tasks are all required")
    if sum(t.split == "train" for t in tasks) < 2:
        raise ContractError("meta-training needs multiple physical train tasks")
