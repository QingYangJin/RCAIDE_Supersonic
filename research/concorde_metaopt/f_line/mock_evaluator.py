"""F1 合成评价器（MockEvaluator，物理调用恒为 0）。

用途：在不启动任何真实求解器的前提下，验证
    12D 设计 -> 统一评价协议 -> BudgetLedger 记账 -> BO/DE ask/tell
这条软件闭环是否自洽。

边界（写死在记录里，防止误用）：
* source_kind = SYNTHETIC_MOCK，fidelity = "synthetic"，
  physical_validation_status = NOT_APPLICABLE，physical_call_count = 0。
* 合成目标只是"基线燃油 + 归一化线性占位响应"的占位函数，**不是物理结论**，
  不得用于任何阻力/油耗/配平主张。
* 几何不可行（越界或违反 C01/C02）返回 status=GEOMETRY_INVALID 且 objective=null，
  账本照样计一次请求，但物理调用仍为 0。

合成目标模型（确定性，可选确定性伪噪声）：
    u_i = 变量在上下界内的归一化位置 (0..1)，u0_i = 基线设计的位置
    objective = 34109.482571 * (1 + sum_i a_i * (u_i - u0_i)) - noise
其中 a_i = _SYNTHETIC_SENSITIVITY 的占位系数（量级约 0.5%~3%），
只为让 ask/tell 闭环产生可观测改进，**不对应任何真实气动趋势**。
其中 34109.482571 kg 取自冻结任务档案里 136000 kg 巡航进入状态的基线油耗
（research/concorde_metaopt/optimization_runs/... 与 task_fixed_cruise.yaml 证据），
仅作为量级锚点，不对应任何具体 VSPAERO/RCAIDE 结果。
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Callable, Dict, Mapping, Optional

from ..aircraft.design_space import DesignSpace
from .records import (
    EvaluationRecord,
    PHYSICAL_VALIDATION_NOT_APPLICABLE,
    SOURCE_KIND_SYNTHETIC_MOCK,
    STATUS_EVALUATOR_ERROR,
    STATUS_GEOMETRY_INVALID,
    STATUS_SOLVER_NONCONVERGED,
    STATUS_VALID,
    canonical_design_sha256,
    ordered_constraints,
)

#: 136000 kg 巡航进入状态下的基线油耗锚点（kg），仅用于量级参考。
BASELINE_FUEL_KG = 34109.482571

#: 合成线性响应系数（相对归一化位移），仅让 ask/tell 闭环产生可观测改进。
#: **这些系数没有物理含义**，不得据此推断真实气动趋势（禁止把合成梯度当阻力梯度）。
_SYNTHETIC_SENSITIVITY: Dict[str, float] = {
    "wing_area": -0.020,
    "aspect_ratio": -0.030,
    "sweep_1": -0.005,
    "sweep_2": 0.005,
    "sweep_3": -0.005,
    "span_location_2": 0.005,
    "span_location_3": -0.005,
    "chord_ratio_2": 0.005,
    "chord_ratio_3": -0.005,
    "tip_twist": 0.005,
    "vertical_tail_area": -0.010,
    "vertical_tail_sweep_delta": -0.005,
}

#: 合成巡航所需的保留燃油（kg），仅用于构造 fuel_remaining_deficit。
_SYNTHETIC_RESERVE_KG = 4000.0


class MockEvaluator:
    """零物理调用的合成评价器，实现 EvaluatorProtocol。"""

    evaluator_id = "mock-synthetic-v1"
    fidelity = "synthetic"
    source_kind = SOURCE_KIND_SYNTHETIC_MOCK
    solver_version = "mock-0.1.0"
    physical_validation_status = PHYSICAL_VALIDATION_NOT_APPLICABLE
    estimated_physical_cost = 0

    def __init__(
        self,
        design_space: DesignSpace,
        task: Any,
        run_id: str = "f1-mock",
        noise_kg: float = 0.0,
        failure_hook: Optional[Callable[[Mapping[str, float]], Optional[str]]] = None,
        raise_hook: Optional[Callable[[Mapping[str, float]], Optional[BaseException]]] = None,
    ) -> None:
        if design_space.design_dim != 12:
            raise ValueError(
                "MockEvaluator expects the 12D lifting-surface space, got design_dim=%d"
                % design_space.design_dim
            )
        self.design_space = design_space
        self.task = task
        self.run_id = str(run_id)
        self.noise_kg = float(noise_kg)
        if self.noise_kg < 0:
            raise ValueError("noise_kg must be non-negative")
        self.failure_hook = failure_hook
        self.raise_hook = raise_hook
        # 基线在归一化空间中的位置：合成响应以它为参照，使基线 range_error = 0。
        baseline_physical = self.design_space.expand(self.design_space.baseline_dict())
        self._baseline_fractions = dict(
            zip(
                self.design_space.names,
                self.design_space.to_unit_interval(baseline_physical),
            )
        )

    # -- 输入归一化 -------------------------------------------------------
    def _physical(self, design: Mapping[str, float]) -> Dict[str, float]:
        declared = set(self.design_space.names)
        fixed = set(self.design_space.fixed_names)
        keys = set(design)
        if keys == declared:
            return self.design_space.expand(design)
        if keys == declared | fixed:
            return {name: float(design[name]) for name in list(self.design_space.names) + list(self.design_space.fixed_names)}
        missing = sorted(declared - keys)
        unexpected = sorted(keys - declared - fixed)
        raise ValueError(
            "design must carry either the 12 declared variables or the full 15 physical "
            "variables (missing=%s unexpected=%s)" % (missing, unexpected)
        )

    # -- 合成目标 ---------------------------------------------------------
    def _synthetic_objective(self, physical: Mapping[str, float]) -> float:
        fractions = dict(
            zip(self.design_space.names, self.design_space.to_unit_interval(physical))
        )
        response = 0.0
        for name, fraction in fractions.items():
            response += _SYNTHETIC_SENSITIVITY.get(name, 0.0) * (
                float(fraction) - self._baseline_fractions[name]
            )
        objective = BASELINE_FUEL_KG * (1.0 + response)
        return objective - self._pseudo_noise(physical)

    def _pseudo_noise(self, physical: Mapping[str, float]) -> float:
        if self.noise_kg <= 0.0:
            return 0.0
        digest = hashlib.sha256(canonical_design_sha256(physical).encode("ascii")).digest()
        unit = int.from_bytes(digest[:8], "big") / float(2**64)
        return self.noise_kg * (unit - 0.5)

    def _synthetic_constraints(
        self,
        physical: Mapping[str, float],
        objective: float,
        geometry_violations: list,
    ) -> Dict[str, float]:
        task = self.task
        start_mass = float(task.start_mass_kg)
        fuel_loaded = float(task.fuel_loaded_kg)
        zero_fuel_mass = (
            float(task.operating_empty_kg) + float(task.payload_kg) + float(task.cargo_kg)
        )
        fractions = dict(zip(self.design_space.names, self.design_space.to_unit_interval(physical)))
        # 合成 L/D 代理：仅在归一化空间里给出方向性响应，不是气动结论。
        ref = self._baseline_fractions
        ld_proxy = (
            2.00
            + 0.30 * (fractions["aspect_ratio"] - ref["aspect_ratio"])
            + 0.10 * (fractions["sweep_1"] - ref["sweep_1"])
            + 0.08 * (fractions["sweep_2"] - ref["sweep_2"])
            + 0.05 * (fractions["span_location_2"] - ref["span_location_2"])
        )
        range_error = 1.0 - ld_proxy / 2.00
        throttle = 0.9455 * (objective / BASELINE_FUEL_KG)
        alpha_deg = (
            2.0
            + 3.0 * (fractions["vertical_tail_area"] - 0.5)
            - 2.0 * (fractions["span_location_2"] - 0.5)
        )
        constraints = {
            "geometry_invalid": 1.0 if geometry_violations else 0.0,
            "task_mass_balance": (start_mass - (zero_fuel_mass + fuel_loaded)) / start_mass,
            "fuel_capacity_excess": (fuel_loaded - float(task.max_fuel_kg)) / float(task.max_fuel_kg),
            "zero_fuel_excess": (zero_fuel_mass - float(task.max_zero_fuel_kg)) / float(task.max_zero_fuel_kg),
            "takeoff_excess": (start_mass - float(task.max_takeoff_kg)) / float(task.max_takeoff_kg),
            "fuel_remaining_deficit": (
                _SYNTHETIC_RESERVE_KG - (fuel_loaded - objective)
            )
            / fuel_loaded,
            "max_throttle": throttle - 1.0,
            "cruise_range_error": range_error,
            "mission_convergence": 0.0,
            "trim_attitude_limit": abs(alpha_deg) / 12.0 - 1.0,
        }
        return ordered_constraints(constraints)

    # -- 协议实现 ---------------------------------------------------------
    def evaluate(
        self,
        design: Mapping[str, float],
        task: Any = None,
        fidelity: Optional[str] = None,
    ) -> EvaluationRecord:
        if fidelity is not None and str(fidelity) != self.fidelity:
            raise ValueError(
                "MockEvaluator only serves fidelity %r, got %r" % (self.fidelity, fidelity)
            )
        if task is not None and hasattr(task, "fingerprint"):
            expected = getattr(self.task, "fingerprint", lambda: None)()
            if expected is not None and task.fingerprint() != expected:
                raise ValueError("task fingerprint mismatch: evaluator is bound to task %r" % self.task.task_id)
        physical = self._physical(design)
        sha = canonical_design_sha256(physical)
        if self.raise_hook is not None:
            error = self.raise_hook(physical)
            if error is not None:
                raise error
        violations = self.design_space.check_physical(
            {name: physical[name] for name in self.design_space.names}
        )
        provenance: Dict[str, Any] = {
            "model": "synthetic_linear_placeholder",
            "baseline_fuel_kg": BASELINE_FUEL_KG,
            "sensitivity": dict(_SYNTHETIC_SENSITIVITY),
            "design_space_task_id": getattr(self.design_space, "task_id", ""),
            "note": "合成目标仅用于软件闭环验证，不是物理证据；系数无物理含义",
        }
        if violations:
            return EvaluationRecord(
                run_id=self.run_id,
                task_id=str(getattr(self.task, "task_id", "")),
                design=physical,
                design_sha256=sha,
                evaluator_id=self.evaluator_id,
                fidelity=self.fidelity,
                source_kind=self.source_kind,
                physical_validation_status=self.physical_validation_status,
                solver_version=self.solver_version,
                objective=None,
                constraints=ordered_constraints({"geometry_invalid": 1.0}),
                status=STATUS_GEOMETRY_INVALID,
                provenance={**provenance, "geometry_violations": list(violations)},
                physical_call_count=0,
                wall_seconds=0.0,
                diagnostics=tuple(violations),
            )
        if self.failure_hook is not None:
            injected = self.failure_hook(physical)
            if injected:
                if injected not in (STATUS_SOLVER_NONCONVERGED, STATUS_EVALUATOR_ERROR):
                    raise ValueError("failure_hook returned unsupported status %r" % injected)
                return EvaluationRecord(
                    run_id=self.run_id,
                    task_id=str(getattr(self.task, "task_id", "")),
                    design=physical,
                    design_sha256=sha,
                    evaluator_id=self.evaluator_id,
                    fidelity=self.fidelity,
                    source_kind=self.source_kind,
                    physical_validation_status=self.physical_validation_status,
                    solver_version=self.solver_version,
                    objective=None,
                    constraints=ordered_constraints(),
                    status=injected,
                    provenance={**provenance, "failure_injected": injected},
                    physical_call_count=0,
                    wall_seconds=0.0,
                    diagnostics=("failure injected by test hook",),
                )
        objective = self._synthetic_objective(physical)
        if not math.isfinite(objective):
            raise RuntimeError("synthetic objective is not finite")
        return EvaluationRecord(
            run_id=self.run_id,
            task_id=str(getattr(self.task, "task_id", "")),
            design=physical,
            design_sha256=sha,
            evaluator_id=self.evaluator_id,
            fidelity=self.fidelity,
            source_kind=self.source_kind,
            physical_validation_status=self.physical_validation_status,
            solver_version=self.solver_version,
            objective=objective,
            constraints=self._synthetic_constraints(physical, objective, violations),
            status=STATUS_VALID,
            provenance=provenance,
            physical_call_count=0,
            wall_seconds=0.0,
        )
