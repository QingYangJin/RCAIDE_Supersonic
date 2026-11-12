"""P2a 真实评价入口（A1 提供，A2 只读调用；零物理准备阶段）。

本模块把 AeroEvaluator 包装成 A2 优化器所需的 evaluate_fn：

    from research.concorde_metaopt.dreal001.geometry.p2a_contract import make_evaluate_fn
    evaluate_fn = make_evaluate_fn(design_space, TASK_SPEC, run_dir=..., approval=approval,
                                   spawn=spawn, allow_physical_starts=True, timeout_s=60.0,
                                   target_mesh_family=(543, 472), batch_id="DREAL001-P2A-...")
    record = evaluate_fn(a1_x12, case_id="arm1-seed42-d000017", meta={...})

契约（与 EVALUATOR_API v1.1 一致）：
- 输入是**物理 12 维向量**（W01..W10,V01,V02 的 SI 值），不是单位立方分数；单位立方
  向量会被 fail-closed 拒绝（A2 的 RealVspaeroAdapter 已在 _a1_x12 里做反归一化）。
- 一次真实启动 = 1 个 vspaero.exe 进程 = 7 个 alpha 内部子案；禁止按 alpha 行计费。
- 任何授权不足（approval 未批、max_starts<=0、批号不符、预算耗尽）都在启动前返回
  NOT_RUN 记录且 physical_solver_starts=0，不会产生 solver 启动，也不会产生标签。
- 目标网格族不可达时由 AeroEvaluator 直接返回 GEOMETRY_INVALID + 错误码
  MESH_FAMILY_UNAVAILABLE（0 启动），本模块只做计数与透传。

边界：本模块只保证"过程与记账"，不构成物理验证；record 永远
physical_validation_status=NOT_VALIDATED、fuel_burn_kg=null。
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

P2A_EVALUATE_SCHEMA = "dreal001.p2a_evaluate_fn.v1"
P2A_EVALUATE_ID = "a1-p2a-evaluate-fn-v1"
DEFAULT_P2A_TIMEOUT_S = 60.0
DEFAULT_P2A_TARGET_MESH_FAMILY: Tuple[int, int] = (543, 472)
DEFAULT_P2A_MAX_MESH_ATTEMPTS = 12
AERO_EVAL_SCHEMA = "dreal001.aero_eval.v1"
BACKEND_REAL = "REAL_VSPAERO"
PHYSICAL_VALIDATION_STATUS = "NOT_VALIDATED"

ERROR_UNIT_BOX = "UNIT_BOX_VECTOR_NOT_ACCEPTED"
ERROR_APPROVAL = "APPROVAL_MISSING_OR_NOT_APPROVED"
ERROR_BATCH = "APPROVAL_BATCH_MISMATCH"
ERROR_BUDGET = "SOLVER_BUDGET_EXHAUSTED"
ERROR_LENGTH = "X12_LENGTH"
ERROR_NONFINITE = "X12_NONFINITE"


class P2AConfigurationError(RuntimeError):
    """构造或输入违反 P2a 合同；必须在任何 solver 启动前抛出。"""


def _empty_results() -> Dict[str, List[float]]:
    return {"alpha_deg": [], "cltot": [], "cdi": [], "cdo": [], "cdtot": [], "cmy": []}


def _refusal_record(case_id: str, code: str, detail: str,
                    meta: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    return {
        "schema_version": AERO_EVAL_SCHEMA,
        "evaluator_id": P2A_EVALUATE_ID,
        "backend": BACKEND_REAL,
        "source_kind": BACKEND_REAL,
        "physical_validation_status": PHYSICAL_VALIDATION_STATUS,
        "status": "NOT_RUN",
        "record_status": "NOT_RUN",
        "case_id": str(case_id),
        "meta": dict(meta or {}),
        "design": {"x12": [], "design_hash": ""},
        "geometry": {},
        "solver": {"physical_solver_starts": 0, "attempt_ids": [], "argv": [], "command": []},
        "results": _empty_results(),
        "lift": {},
        "attempt_ids": [],
        "raw_artifacts": [],
        "errors": [{"code": code, "detail": detail, "no_solver_start": True}],
        "cache_hit": False,
        "physical_solver_starts": 0,
        "physical_call_count": 0,
        "objective": {"name": "D_i_N", "value": None, "unit": "N"},
        "fuel_burn_kg": None,
    }


class P2AEvaluateFn:
    """可调用的 P2a 评价入口；同时暴露计数/预算状态供审计。"""

    def __init__(self, evaluator: Any, *, approval: Mapping[str, Any],
                 allow_physical_starts: bool, max_starts: int, batch_id: Optional[str],
                 startup_refusals: Optional[List[Dict[str, Any]]] = None) -> None:
        self.evaluator = evaluator
        self.approval = dict(approval)
        self.allow_physical_starts = bool(allow_physical_starts)
        self.max_starts = int(max_starts)
        self.batch_id = batch_id
        self.starts_used = 0
        self.calls = 0
        self.refusals: List[Dict[str, Any]] = list(startup_refusals or [])

    # ---------------------------------------------------------------- helpers
    @property
    def remaining(self) -> int:
        return max(0, self.max_starts - self.starts_used)

    def summary(self) -> Dict[str, Any]:
        return {
            "schema": P2A_EVALUATE_SCHEMA,
            "evaluate_id": P2A_EVALUATE_ID,
            "backend": BACKEND_REAL,
            "physical_validation_status": PHYSICAL_VALIDATION_STATUS,
            "approval_max_starts": self.max_starts,
            "starts_used": self.starts_used,
            "remaining": self.remaining,
            "calls": self.calls,
            "refusals": list(self.refusals),
            "allow_physical_starts": self.allow_physical_starts,
            "batch_id": self.batch_id,
            "fuel_burn_kg": None,
        }

    # ------------------------------------------------------------------- call
    def __call__(self, x12: Sequence[float], case_id: Optional[str] = None,
                 meta: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        self.calls += 1
        if case_id is None:
            case_id = "p2a-%04d" % (self.calls - 1)
        vector = self._coerce(x12)
        if self.allow_physical_starts and self.starts_used >= self.max_starts:
            refusal = _refusal_record(
                case_id, ERROR_BUDGET,
                "approval max_starts=%d already used (%d); refused before any solver start"
                % (self.max_starts, self.starts_used), meta)
            self.refusals.append(refusal["errors"][0])
            return refusal
        record = self.evaluator.evaluate(vector, case_id=str(case_id), meta=meta)
        starts = int(record.get("physical_solver_starts") or 0)
        self.starts_used += max(0, starts)
        record["p2a_evaluator"] = {
            "evaluate_id": P2A_EVALUATE_ID,
            "schema_version": P2A_EVALUATE_SCHEMA,
            "starts_before": self.starts_used - max(0, starts),
            "starts_after": self.starts_used,
            "approval_max_starts": self.max_starts,
        }
        return record

    # ---------------------------------------------------------------- guards
    @staticmethod
    def _coerce(x12: Sequence[float]) -> List[float]:
        if x12 is None:
            raise P2AConfigurationError("%s: x12 is required" % ERROR_LENGTH)
        values = [float(value) for value in x12]
        if len(values) != 12:
            raise P2AConfigurationError("%s: expected 12 physical values, got %d"
                                        % (ERROR_LENGTH, len(values)))
        if not all(math.isfinite(value) for value in values):
            raise P2AConfigurationError("%s: x12 contains a non-finite value" % ERROR_NONFINITE)
        if all(0.0 <= value <= 1.0 for value in values):
            raise P2AConfigurationError(
                "%s: all 12 values are inside [0,1]; A1 consumes PHYSICAL x12 "
                "(W01..W10,V01,V02 in SI), not unit-box fractions. Denormalize first "
                "(A2 RealVspaeroAdapter._a1_x12 already does this)." % ERROR_UNIT_BOX)
        return values


def make_evaluate_fn(design_space: Any, task: Any = None, *,
                     run_dir: Optional[Any] = None,
                     approval: Optional[Mapping[str, Any]] = None,
                     spawn: Optional[Callable[..., Mapping[str, Any]]] = None,
                     allow_physical_starts: bool = False,
                     timeout_s: float = DEFAULT_P2A_TIMEOUT_S,
                     target_mesh_family: Sequence[int] = DEFAULT_P2A_TARGET_MESH_FAMILY,
                     max_starts: Optional[int] = None,
                     batch_id: Optional[str] = None,
                     max_mesh_attempts: int = DEFAULT_P2A_MAX_MESH_ATTEMPTS,
                     mesh_strategy: str = "roundtrip",
                     geometry_set: str = "thin",
                     tess_u: float = 12.0,
                     tess_w: float = 25.0,
                     cache_enabled: bool = False,
                     openvsp_root: Optional[Any] = None) -> P2AEvaluateFn:
    """构造 A2 可直接 import/调用的 evaluate_fn（fail-closed）。

    授权不足时在**构造阶段**抛 P2AConfigurationError，绝不产生 solver 启动；
    P2a 的 approval 必须 approved=true、max_starts>0，若给出 batch_id 则须与
    approval.batch_id 一致。
    """
    approval_dict = dict(approval or {})
    if not bool(approval_dict.get("approved")):
        raise P2AConfigurationError("%s: approval.approved must be true" % ERROR_APPROVAL)
    approved_max = approval_dict.get("max_starts")
    cap = int(max_starts if max_starts is not None else (approved_max if approved_max is not None else 0))
    if cap <= 0:
        raise P2AConfigurationError("%s: max_starts must be positive (approval=%r, override=%r)"
                                    % (ERROR_APPROVAL, approved_max, max_starts))
    approval_batch = approval_dict.get("batch_id")
    if batch_id is not None and approval_batch is not None and str(approval_batch) != str(batch_id):
        raise P2AConfigurationError("%s: approval batch_id %r does not match %r"
                                    % (ERROR_BATCH, approval_batch, batch_id))
    from .evaluator import AeroEvaluator  # 延迟导入，避免 import 循环/重依赖

    evaluator = AeroEvaluator(
        design_space, task,
        run_dir=run_dir,
        approval=approval_dict,
        spawn=spawn,
        allow_physical_starts=bool(allow_physical_starts),
        timeout_s=float(timeout_s),
        geometry_set=str(geometry_set),
        tess_u=float(tess_u),
        tess_w=float(tess_w),
        openvsp_root=openvsp_root,
        cache_enabled=bool(cache_enabled),
        max_mesh_attempts=int(max_mesh_attempts),
        mesh_strategy=str(mesh_strategy),
        target_mesh_family=tuple(int(value) for value in target_mesh_family),
    )
    return P2AEvaluateFn(evaluator, approval=approval_dict,
                         allow_physical_starts=bool(allow_physical_starts),
                         max_starts=cap, batch_id=batch_id or approval_batch)
