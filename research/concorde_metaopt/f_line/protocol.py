"""F1 评价协议（EvaluatorProtocol）。

任何评价器只要实现 evaluate(design, task, fidelity) -> EvaluationRecord 并声明
evaluator_id / fidelity / source_kind / solver_version / estimated_physical_cost
即可接入 BudgetLedger 与 BO/DE 驱动。

结构化的 Protocol 只做类型约束，不做运行时检查；运行时校验发生在 EvaluationRecord
构造与 BudgetLedger 记账处。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from .records import EvaluationRecord


@runtime_checkable
class EvaluatorProtocol(Protocol):
    """统一评价接口（对应 Issue #8 F1 的 EvaluatorProtocol.evaluate）。"""

    evaluator_id: str
    fidelity: str
    source_kind: str
    solver_version: str
    physical_validation_status: str
    #: 单次请求预估物理调用数（真实求解器=1；mock/replay=0），用于**调用前**预授权。
    estimated_physical_cost: int

    def evaluate(
        self,
        design: Mapping[str, float],
        task: Any = None,
        fidelity: Optional[str] = None,
    ) -> EvaluationRecord:
        """评价一个物理设计向量，返回带 provenance 的记录；失败时 objective 必须为 null。"""
        ...
