"""F1 统一评价记录（EvaluationRecord）与状态词表。

设计原则（对应 Issue #8 的 F1 要求）：
1. 一个记录必须自描述：run_id / task_id / design / sha / evaluator_id / fidelity /
   source_kind / physical_validation_status / solver_version / objective /
   constraints / status / provenance 全部显式，缺一即视为契约违规。
2. **失败值必须为 null**：只有 status=VALID 才允许非空 objective。几何不可行、
   求解器未收敛、物理未验证一律 objective=None，禁止用大罚值伪造目标。
3. **零求解保护**：source_kind 为 SYNTHETIC_MOCK / ARCHIVE_REPLAY 的评价器
   绝不允许上报 physical_call_count>0，否则构造记录时直接报错。
4. constraints 复用冻结合同 evaluation.contract 的 10 项 g<=0 名称与顺序，
   不另立一套，保证与 P2 ledger / BO / DE 的口径一致。

本模块不导入 RCAIDE、OpenVSP、VSPAERO 或任何求解器。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from ..evaluation.contract import (
    CONSTRAINT_NAMES,
    CONSTRAINT_UNITS,
    FEASIBILITY_TOLERANCE,
    OBJECTIVE_NAME,
    OBJECTIVE_UNIT,
)

# -- 评价状态 -------------------------------------------------------------
STATUS_VALID = "VALID"
STATUS_GEOMETRY_INVALID = "GEOMETRY_INVALID"
STATUS_SOLVER_NONCONVERGED = "SOLVER_NONCONVERGED"
STATUS_PHYSICS_NOT_VALIDATED = "PHYSICS_NOT_VALIDATED"
STATUS_EVALUATOR_ERROR = "EVALUATOR_ERROR"

ALL_STATUSES: Tuple[str, ...] = (
    STATUS_VALID,
    STATUS_GEOMETRY_INVALID,
    STATUS_SOLVER_NONCONVERGED,
    STATUS_PHYSICS_NOT_VALIDATED,
    STATUS_EVALUATOR_ERROR,
)

FAILURE_STATUSES: Tuple[str, ...] = tuple(s for s in ALL_STATUSES if s != STATUS_VALID)

# 只有这两类失败值得再试：求解器类失败在零求解阶段由 mock 模拟。
RETRYABLE_STATUSES: Tuple[str, ...] = (
    STATUS_SOLVER_NONCONVERGED,
    STATUS_EVALUATOR_ERROR,
)

# -- 证据来源 -------------------------------------------------------------
SOURCE_KIND_SYNTHETIC_MOCK = "SYNTHETIC_MOCK"
SOURCE_KIND_ARCHIVE_REPLAY = "ARCHIVE_REPLAY"
SOURCE_KIND_ENGINEERING_SOLVER = "ENGINEERING_SOLVER_IN_LOOP"
SOURCE_KIND_VSPAERO_INTERNAL = "VSPAERO_INTERNAL_ONLY"

SOURCE_KINDS: Tuple[str, ...] = (
    SOURCE_KIND_SYNTHETIC_MOCK,
    SOURCE_KIND_ARCHIVE_REPLAY,
    SOURCE_KIND_ENGINEERING_SOLVER,
    SOURCE_KIND_VSPAERO_INTERNAL,
)

# 只有这两类可以有物理调用；真实第一层仅此两类（Issue #8 计划）。
SOLVER_SOURCE_KINDS: Tuple[str, ...] = (
    SOURCE_KIND_ENGINEERING_SOLVER,
    SOURCE_KIND_VSPAERO_INTERNAL,
)

# -- 物理验证状态 ---------------------------------------------------------
PHYSICAL_VALIDATION_VALIDATED = "VALIDATED"
PHYSICAL_VALIDATION_PARTIAL = "PARTIAL"
PHYSICAL_VALIDATION_NOT_VALIDATED = "NOT_VALIDATED"
PHYSICAL_VALIDATION_NOT_APPLICABLE = "NOT_APPLICABLE"

PHYSICAL_VALIDATION_LEVELS: Tuple[str, ...] = (
    PHYSICAL_VALIDATION_VALIDATED,
    PHYSICAL_VALIDATION_PARTIAL,
    PHYSICAL_VALIDATION_NOT_VALIDATED,
    PHYSICAL_VALIDATION_NOT_APPLICABLE,
)

# -- 保真度等级（数值只用于比较，不得用来把低保真结论包装成高保真）--------
FIDELITY_RANKS: Dict[str, int] = {
    "geometry_only": 0,
    "synthetic": 1,
    "archive_replay": 2,
    "single_cruise": 3,
    "vspaero_internal": 4,
    "coupled_mission": 5,
}


def canonical_design_sha256(design: Mapping[str, float]) -> str:
    """设计向量的稳定 SHA-256（键排序、float repr 固定）。"""
    payload = json.dumps(
        {str(name): float(value) for name, value in design.items()},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ordered_constraints(values: Optional[Mapping[str, float]] = None) -> Dict[str, float]:
    """按冻结顺序返回完整 10 项约束；缺省补 0，未知名称或非有限值报错。"""
    if values is None:
        return {name: 0.0 for name in CONSTRAINT_NAMES}
    unknown = [str(key) for key in values if str(key) not in CONSTRAINT_NAMES]
    if unknown:
        raise ValueError("unknown constraint name(s): %s" % (sorted(unknown),))
    result: Dict[str, float] = {}
    for name in CONSTRAINT_NAMES:
        if name not in values:
            result[name] = 0.0
            continue
        value = float(values[name])
        if not math.isfinite(value):
            raise ValueError("constraint %r is not finite: %r" % (name, values[name]))
        result[name] = value
    return result


def is_feasible(constraints: Mapping[str, float]) -> bool:
    """全部 10 项约束存在、有限且 g<=0 才可行。"""
    for name in CONSTRAINT_NAMES:
        if name not in constraints:
            return False
        value = float(constraints[name])
        if not math.isfinite(value) or value > FEASIBILITY_TOLERANCE:
            return False
    return True


@dataclass(frozen=True)
class EvaluationRecord:
    """一次评价的完整、可审计记录（失败值 null）。"""

    run_id: str
    task_id: str
    design: Dict[str, float]
    design_sha256: str
    evaluator_id: str
    fidelity: str
    source_kind: str
    physical_validation_status: str
    solver_version: str
    objective: Optional[float]
    constraints: Dict[str, float]
    status: str
    provenance: Dict[str, Any] = field(default_factory=dict)
    physical_call_count: int = 0
    wall_seconds: float = 0.0
    feasible: bool = False
    diagnostics: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.task_id, str) or not self.task_id:
            raise ValueError("task_id must be a non-empty string")
        if not isinstance(self.design, Mapping) or not self.design:
            raise ValueError("design must be a non-empty mapping")
        if self.status not in ALL_STATUSES:
            raise ValueError("unknown evaluation status %r (allowed: %s)" % (self.status, ALL_STATUSES))
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError("unknown source_kind %r (allowed: %s)" % (self.source_kind, SOURCE_KINDS))
        if self.physical_validation_status not in PHYSICAL_VALIDATION_LEVELS:
            raise ValueError(
                "unknown physical_validation_status %r (allowed: %s)"
                % (self.physical_validation_status, PHYSICAL_VALIDATION_LEVELS)
            )
        if type(self.physical_call_count) is not int or self.physical_call_count < 0:
            raise ValueError("physical_call_count must be a non-negative int")
        if self.physical_call_count and self.source_kind not in SOLVER_SOURCE_KINDS:
            raise ValueError(
                "software evaluator %r must not bill physical calls (got %d)"
                % (self.source_kind, self.physical_call_count)
            )
        if self.status == STATUS_VALID:
            if self.objective is None or not isinstance(self.objective, (int, float)):
                raise ValueError("status VALID requires a finite objective")
            if not math.isfinite(float(self.objective)):
                raise ValueError("status VALID requires a finite objective")
        else:
            if self.objective is not None:
                raise ValueError(
                    "status %r must carry objective=null, got %r" % (self.status, self.objective)
                )
        design = {str(name): float(value) for name, value in self.design.items()}
        object.__setattr__(self, "design", design)
        constraints = ordered_constraints(self.constraints)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "diagnostics", tuple(str(item) for item in self.diagnostics))
        object.__setattr__(
            self,
            "feasible",
            bool(self.status == STATUS_VALID and is_feasible(constraints)),
        )

    # -- 便捷视图 ---------------------------------------------------------
    @property
    def objective_is_null(self) -> bool:
        return self.objective is None

    @property
    def has_physical_evidence(self) -> bool:
        """只有真实求解器来源且物理验证非 NOT_APPLICABLE 才算物理证据。"""
        return (
            self.source_kind in SOLVER_SOURCE_KINDS
            and self.physical_call_count > 0
            and self.physical_validation_status
            in (PHYSICAL_VALIDATION_VALIDATED, PHYSICAL_VALIDATION_PARTIAL)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "design": dict(self.design),
            "sha": self.design_sha256,
            "evaluator_id": self.evaluator_id,
            "fidelity": self.fidelity,
            "source_kind": self.source_kind,
            "physical_validation_status": self.physical_validation_status,
            "solver_version": self.solver_version,
            "objective": None if self.objective is None else float(self.objective),
            "objective_name": OBJECTIVE_NAME,
            "objective_unit": OBJECTIVE_UNIT,
            "constraints": dict(self.constraints),
            "constraint_units": {name: CONSTRAINT_UNITS[name] for name in CONSTRAINT_NAMES},
            "feasible": bool(self.feasible),
            "status": self.status,
            "physical_call_count": int(self.physical_call_count),
            "wall_seconds": float(self.wall_seconds),
            "provenance": dict(self.provenance),
            "diagnostics": list(self.diagnostics),
        }


#: 约束容器的别名，便于调用方标注类型。
EvalConstraints = Dict[str, float]
