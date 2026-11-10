"""F1 预算账本（BudgetLedger）：零求解阶段也必须可审计。

与 P2 的 EvaluationLedger 的区别：
* EvaluationLedger 以"真实求解调用"为唯一预算单位，并要求每次非缓存评价至少计费 1 次；
  这在 physical_call_count=0 的 F1 软件闭环里不可用。
* BudgetLedger 把"请求数"和"物理调用数"分开记账：mock/archive 评价器只消耗请求数、
  物理调用恒为 0；真实求解器每次调用前先按 estimated_physical_cost 预授权，
  预算不足时**在启动求解器之前**抛 BudgetExceeded（fail-closed，避免超发）。
* 失败值必须为 null：账本拒绝把 objective 非 null 的非 VALID 记录写入。

记账规则：
    used_physical = sum(record.physical_call_count)
    used_requests = 评价请求数（含失败与重试）
    失败是否计费由评价器自己上报：求解器已启动即 physical_call_count=1，
    几何/协议层拒绝则为 0。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .records import (
    ALL_STATUSES,
    FAILURE_STATUSES,
    RETRYABLE_STATUSES,
    STATUS_VALID,
    EvaluationRecord,
    SOLVER_SOURCE_KINDS,
    ordered_constraints,
)


class BudgetExceeded(RuntimeError):
    """物理调用预算不足（在启动求解器之前抛出）。"""

    def __init__(self, budget: int, used: int, requested: int = 1) -> None:
        self.budget = int(budget)
        self.used = int(used)
        self.requested = int(requested)
        super().__init__(
            "physical budget exhausted: budget=%d used=%d requested=%d"
            % (self.budget, self.used, self.requested)
        )


class BudgetLedgerError(RuntimeError):
    """账本契约违规：例如评价器上报的物理调用数与预授权不一致。"""


@dataclass(frozen=True)
class CostModel:
    """计费与重试策略。"""

    unit_cost: int = 1
    max_retries: int = 0
    bill_failed_calls: bool = True
    timeout_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if type(self.unit_cost) is not int or self.unit_cost < 0:
            raise ValueError("unit_cost must be a non-negative int")
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError("max_retries must be a non-negative int")
        if self.timeout_seconds is not None and float(self.timeout_seconds) <= 0:
            raise ValueError("timeout_seconds must be positive when set")


class BudgetLedger:
    """按物理调用计费的评价账本，兼容零物理调用的软件闭环。"""

    def __init__(
        self,
        physical_budget: int = 0,
        max_requests: int = 1000,
        run_id: str = "",
        cost_model: Optional[CostModel] = None,
        cache_enabled: bool = True,
    ) -> None:
        if type(physical_budget) is not int or physical_budget < 0:
            raise ValueError("physical_budget must be a non-negative int")
        if type(max_requests) is not int or max_requests < 1:
            raise ValueError("max_requests must be a positive int")
        self.physical_budget = int(physical_budget)
        self.max_requests = int(max_requests)
        self.run_id = str(run_id)
        self.cost_model = cost_model or CostModel()
        self.cache_enabled = bool(cache_enabled)
        self.records: List[EvaluationRecord] = []
        self.attempts: List[EvaluationRecord] = []
        self.physical_calls = 0
        self.requests = 0
        self.accounting_violations = 0
        self._cache: Dict[str, EvaluationRecord] = {}

    # -- 预授权 -----------------------------------------------------------
    @property
    def remaining(self) -> int:
        return max(self.physical_budget - self.physical_calls, 0)

    def authorize(self, cost: Optional[int] = None) -> None:
        """在调用评价器之前预授权；预算不足立即抛 BudgetExceeded。"""
        requested = self.cost_model.unit_cost if cost is None else int(cost)
        if requested < 0:
            raise ValueError("cost must be non-negative")
        if self.physical_calls + requested > self.physical_budget:
            raise BudgetExceeded(self.physical_budget, self.physical_calls, requested)

    # -- 记账 -------------------------------------------------------------
    def _estimate(self, evaluator: Any) -> int:
        if getattr(evaluator, "source_kind", None) not in SOLVER_SOURCE_KINDS:
            return 0
        return int(getattr(evaluator, "estimated_physical_cost", self.cost_model.unit_cost) or 0)

    def _cache_key(
        self,
        task: Any,
        fidelity: str,
        design: Mapping[str, float],
        evaluator_id: str = "",
    ) -> Optional[str]:
        fingerprint = task.fingerprint() if hasattr(task, "fingerprint") else None
        if fingerprint is None:
            return None
        from .records import canonical_design_sha256

        return "%s|%s|%s|%s" % (
            fingerprint,
            evaluator_id,
            fidelity,
            canonical_design_sha256(design),
        )

    def evaluate(
        self,
        evaluator: Any,
        design: Mapping[str, float],
        task: Any = None,
        fidelity: Optional[str] = None,
    ) -> EvaluationRecord:
        """评价一个设计并记账；返回最后一条记录。"""
        if self.requests >= self.max_requests:
            raise BudgetLedgerError(
                "request cap reached: max_requests=%d (zero-physics runs still cap requests)"
                % self.max_requests
            )
        fidelity_name = fidelity or getattr(evaluator, "fidelity", "unknown")
        cost = self._estimate(evaluator)
        self.authorize(cost)
        key = (
            self._cache_key(
                task,
                str(fidelity_name),
                design,
                str(getattr(evaluator, "evaluator_id", "")),
            )
            if self.cache_enabled
            else None
        )
        if key is not None and key in self._cache:
            cached = self._cache[key]
            # 缓存命中不计费：复制记录并把请求数 +1，保持 provenance 可追溯。
            record = EvaluationRecord(
                run_id=cached.run_id,
                task_id=cached.task_id,
                design=dict(cached.design),
                design_sha256=cached.design_sha256,
                evaluator_id=cached.evaluator_id,
                fidelity=cached.fidelity,
                source_kind=cached.source_kind,
                physical_validation_status=cached.physical_validation_status,
                solver_version=cached.solver_version,
                objective=cached.objective,
                constraints=dict(cached.constraints),
                status=cached.status,
                provenance={**dict(cached.provenance), "cache_hit": True},
                physical_call_count=0,
                wall_seconds=0.0,
                diagnostics=tuple(cached.diagnostics),
            )
            self.requests += 1
            self.records.append(record)
            self.attempts.append(record)
            return record

        try:
            record = evaluator.evaluate(design, task=task, fidelity=fidelity_name)
        except BudgetExceeded:
            raise
        except Exception as exc:  # pragma: no cover - 防御边界
            self.accounting_violations += 1
            raise BudgetLedgerError(
                "evaluator %r raised before returning a record: %s: %s"
                % (getattr(evaluator, "evaluator_id", type(evaluator).__name__), type(exc).__name__, exc)
            ) from exc

        if not isinstance(record, EvaluationRecord):
            self.accounting_violations += 1
            raise BudgetLedgerError(
                "evaluator %r returned %r, expected EvaluationRecord"
                % (getattr(evaluator, "evaluator_id", None), type(record).__name__)
            )
        self.requests += 1
        self.physical_calls += int(record.physical_call_count)
        if self.physical_calls > self.physical_budget:
            self.accounting_violations += 1
            self.records.append(record)
            self.attempts.append(record)
            raise BudgetLedgerError(
                "accounting violation: record bills %d physical call(s) but budget is %d (used %d)"
                % (record.physical_call_count, self.physical_budget, self.physical_calls)
            )
        self.records.append(record)
        self.attempts.append(record)
        # 只缓存成功记录：失败记录若进缓存，重试会命中缓存而永远拿不到第二次真实尝试。
        if key is not None and record.status == STATUS_VALID:
            self._cache[key] = record
        return record

    def evaluate_with_retry(
        self,
        evaluator: Any,
        design: Mapping[str, float],
        task: Any = None,
        fidelity: Optional[str] = None,
    ) -> EvaluationRecord:
        """按 CostModel.max_retries 重试；每次尝试独立记账（失败也计费）。"""
        attempts_allowed = 1 + int(self.cost_model.max_retries)
        last: Optional[EvaluationRecord] = None
        for attempt in range(attempts_allowed):
            last = self.evaluate(evaluator, design, task=task, fidelity=fidelity)
            retryable = last.status in RETRYABLE_STATUSES
            if not retryable:
                return last
            if attempt + 1 >= attempts_allowed:
                return last
            if not self.cost_model.bill_failed_calls and last.physical_call_count == 0:
                return last
        if last is None:  # pragma: no cover - attempts_allowed >= 1 恒成立
            raise BudgetLedgerError("no attempt was made")
        return last

    # -- 视图与产物 -------------------------------------------------------
    def status_counts(self) -> Dict[str, int]:
        counts = {status: 0 for status in ALL_STATUSES}
        for record in self.records:
            counts[record.status] = counts.get(record.status, 0) + 1
        return counts

    def summary(self) -> Dict[str, Any]:
        counts = self.status_counts()
        failures = {status: counts.get(status, 0) for status in FAILURE_STATUSES}
        return {
            "run_id": self.run_id,
            "physical_budget": self.physical_budget,
            "physical_calls": self.physical_calls,
            "remaining": self.remaining,
            "requests": self.requests,
            "max_requests": self.max_requests,
            "records": len(self.records),
            "attempts": len(self.attempts),
            "valid_records": counts.get(STATUS_VALID, 0),
            "failure_records": sum(failures.values()),
            "failures_by_status": failures,
            "accounting_violations": self.accounting_violations,
            "zero_physical_run": self.physical_calls == 0,
            "cache_enabled": self.cache_enabled,
        }

    def evaluations_jsonl(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in self.records:
                handle.write(json.dumps(record.to_dict(), sort_keys=True, allow_nan=False) + "\n")
        return path

    def write_summary_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.summary(), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return path
