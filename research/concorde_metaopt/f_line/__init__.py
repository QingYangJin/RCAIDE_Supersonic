"""D-NEXT-001 F 线：真实评价抽象与航空约束（零真实求解切片）。

本包提供统一的评价协议、预算账本与两个零物理评价器（合成 mock / 归档 replay），
用于在**不启动任何 VSPAERO / SU2 / RCAIDE Mission / WaveDrag** 的前提下跑通
"12D 设计 → evaluator → BO/DE ask-tell" 的最小垂直闭环。

关键事实（不得改写）：
* 本包任何路径都不导入或不触发真实求解；run 记录的 physical_call_count 恒为 0。
* 合成目标只用于验证软件闭环，不是物理证据；其 physical_validation_status 为
  NOT_APPLICABLE（synthetic）或 NOT_VALIDATED（archive replay）。
* V01/V02 属于 12 维声明变量，不得删除；机身 F01-F03 固定但不删除。
* 机翼气动中心 X=16.821978259514246 m 不是全机 CG；几何全机 CG 为
  28.287395109126685 m。详见 docs/planning/dnext001_m0_baseline_and_gate_audit.md。

F1 交付对应关系：
    protocol.py / records.py  EvaluationRecord + EvaluatorProtocol
    budget.py                 BudgetLedger（计费、失败值 null、重试）
    mock_evaluator.py         MockEvaluator（合成目标，0 物理调用）
    replay_evaluator.py       ArchiveReplayEvaluator（归档只读 replay，0 物理调用）
    search.py                 BO/DE ask-tell 最小 E2E 与 run 产物
"""

from .records import (
    ALL_STATUSES,
    CONSTRAINT_NAMES,
    EvalConstraints,
    EvaluationRecord,
    FIDELITY_RANKS,
    PHYSICAL_VALIDATION_LEVELS,
    RETRYABLE_STATUSES,
    STATUS_EVALUATOR_ERROR,
    STATUS_GEOMETRY_INVALID,
    STATUS_PHYSICS_NOT_VALIDATED,
    STATUS_SOLVER_NONCONVERGED,
    STATUS_VALID,
    SOURCE_KINDS,
    SOURCE_KIND_ARCHIVE_REPLAY,
    SOURCE_KIND_ENGINEERING_SOLVER,
    SOURCE_KIND_SYNTHETIC_MOCK,
    SOURCE_KIND_VSPAERO_INTERNAL,
    SOLVER_SOURCE_KINDS,
    canonical_design_sha256,
    is_feasible,
    ordered_constraints,
)
from .budget import (
    BudgetExceeded,
    BudgetLedger,
    BudgetLedgerError,
    CostModel,
)
from .protocol import EvaluatorProtocol
from .mock_evaluator import MockEvaluator
from .replay_evaluator import ArchiveReplayEvaluator
from .search import (
    MiniDE,
    code_sha256,
    run_bo_search,
    run_de_search,
    write_run_artifacts,
)

__all__ = [
    "ALL_STATUSES",
    "CONSTRAINT_NAMES",
    "EvalConstraints",
    "EvaluationRecord",
    "FIDELITY_RANKS",
    "PHYSICAL_VALIDATION_LEVELS",
    "RETRYABLE_STATUSES",
    "STATUS_EVALUATOR_ERROR",
    "STATUS_GEOMETRY_INVALID",
    "STATUS_PHYSICS_NOT_VALIDATED",
    "STATUS_SOLVER_NONCONVERGED",
    "STATUS_VALID",
    "SOURCE_KINDS",
    "SOURCE_KIND_ARCHIVE_REPLAY",
    "SOURCE_KIND_ENGINEERING_SOLVER",
    "SOURCE_KIND_SYNTHETIC_MOCK",
    "SOURCE_KIND_VSPAERO_INTERNAL",
    "SOLVER_SOURCE_KINDS",
    "BudgetExceeded",
    "BudgetLedger",
    "BudgetLedgerError",
    "CostModel",
    "EvaluatorProtocol",
    "MockEvaluator",
    "ArchiveReplayEvaluator",
    "MiniDE",
    "code_sha256",
    "run_bo_search",
    "run_de_search",
    "write_run_artifacts",
    "canonical_design_sha256",
    "is_feasible",
    "ordered_constraints",
]
