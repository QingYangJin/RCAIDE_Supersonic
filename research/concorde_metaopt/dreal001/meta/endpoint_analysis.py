
"""Primary endpoint analysis for limited-budget real sampling (Issue #14 / A2).

The module is intentionally independent of any optimizer.  It consumes a
sequence of *evaluated design records* (one dict per real design evaluation,
in the order the sampler proposed them) and computes the endpoints listed in
the P0 protocol:
  * N_first_feasible (design evaluations and internal alpha cases),
  * best feasible Di_N at budget B and the anytime curve,
  * simple regret against an independently established reference (optional),
  * point-level and run-level feasible hit rate,
  * cost to a pre-registered Di_N target.

No record may be synthesised: records must carry source="real" and a boolean
feasible flag plus the measured di_n for feasible points.  A run with no
feasible point reports None for best-so-far, never a fake number.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

REQUIRED_KEYS = ("task_id", "design_id", "feasible")


@dataclass(frozen=True)
class DesignEvaluation:
    task_id: str
    design_id: str
    feasible: bool
    di_n: Optional[float] = None
    internal_solver_cases: int = 0
    design_starts: int = 1
    source: str = "real"
    failure_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source != "real":
            raise ValueError("endpoint analysis only accepts real evaluated designs")
        if self.feasible:
            if self.di_n is None or self.di_n < 0:
                raise ValueError("feasible evaluation requires a non-negative di_n")
        elif self.di_n is not None:
            raise ValueError("infeasible evaluation must not carry di_n")


def _records(evaluations: Iterable[DesignEvaluation | dict]) -> list[DesignEvaluation]:
    out = []
    for item in evaluations:
        if isinstance(item, DesignEvaluation):
            out.append(item)
        else:
            missing = [key for key in REQUIRED_KEYS if key not in item]
            if missing:
                raise ValueError("evaluation record missing keys: %s" % missing)
            out.append(DesignEvaluation(
                task_id=str(item["task_id"]), design_id=str(item["design_id"]),
                feasible=bool(item["feasible"]), di_n=item.get("di_n"),
                internal_solver_cases=int(item.get("internal_solver_cases", 0)),
                design_starts=int(item.get("design_starts", 1)),
                source=str(item.get("source", "real")),
                failure_reason=item.get("failure_reason")))
    return out


def cumulative_costs(records: Sequence[DesignEvaluation]) -> list[tuple[int, int]]:
    """Running (design_starts, internal_solver_cases) totals after each record."""
    starts = 0
    cases = 0
    out = []
    for rec in records:
        starts += rec.design_starts
        cases += rec.internal_solver_cases
        out.append((starts, cases))
    return out


def first_feasible(evaluations) -> Optional[dict]:
    records = _records(evaluations)
    costs = cumulative_costs(records)
    for index, rec in enumerate(records):
        if rec.feasible:
            return {"design_evaluations": index + 1,
                    "design_starts": costs[index][0],
                    "internal_solver_cases": costs[index][1],
                    "di_n": rec.di_n,
                    "design_id": rec.design_id}
    return None


def best_feasible_at_budget(evaluations, budget: int,
                            cost_key: str = "design_starts") -> Optional[dict]:
    if budget <= 0:
        raise ValueError("budget must be positive")
    if cost_key not in {"design_starts", "internal_solver_cases"}:
        raise ValueError("cost_key must be design_starts or internal_solver_cases")
    records = _records(evaluations)
    best: Optional[dict] = None
    spent = 0
    for rec in records:
        spent += rec.design_starts if cost_key == "design_starts" else rec.internal_solver_cases
        if spent > budget:
            break
        if rec.feasible and (best is None or rec.di_n < best["di_n"]):
            best = {"di_n": rec.di_n, "design_id": rec.design_id, "cost": spent}
    if best is None:
        return None
    return {"budget": budget, "cost_key": cost_key, "best_feasible_di_n": best["di_n"],
            "design_id": best["design_id"], "cost_used": best["cost"]}


def anytime_curve(evaluations, budgets: Sequence[int],
                  cost_key: str = "design_starts") -> list[dict]:
    out = []
    for budget in budgets:
        best = best_feasible_at_budget(evaluations, budget, cost_key)
        out.append({"budget": budget,
                    "best_feasible_di_n": (best or {}).get("best_feasible_di_n"),
                    "design_id": (best or {}).get("design_id"),
                    "cost_used": (best or {}).get("cost_used")})
    return out


def feasible_hit_rate(evaluations) -> dict:
    records = _records(evaluations)
    if not records:
        raise ValueError("empty evaluation sequence")
    feasible = sum(1 for rec in records if rec.feasible)
    return {"design_evaluations": len(records),
            "feasible_evaluations": feasible,
            "point_feasible_hit_rate": feasible / len(records),
            "run_found_feasible": feasible > 0}


def simple_regret(evaluations, reference_di_n: Optional[float],
                  budget: Optional[int] = None,
                  cost_key: str = "design_starts") -> Optional[dict]:
    if reference_di_n is None:
        return None
    if reference_di_n < 0:
        raise ValueError("reference_di_n must be non-negative")
    if budget is not None:
        best = best_feasible_at_budget(evaluations, budget, cost_key)
        best_value = None if best is None else best["best_feasible_di_n"]
    else:
        values = [rec.di_n for rec in _records(evaluations) if rec.feasible]
        best_value = min(values) if values else None
    if best_value is None:
        return None
    return {"reference_di_n": reference_di_n, "best_feasible_di_n": best_value,
            "simple_regret": best_value - reference_di_n, "budget": budget}


def cost_to_target(evaluations, target_di_n: float,
                   cost_key: str = "design_starts") -> Optional[dict]:
    if target_di_n < 0:
        raise ValueError("target_di_n must be non-negative")
    records = _records(evaluations)
    costs = cumulative_costs(records)
    for index, rec in enumerate(records):
        if rec.feasible and rec.di_n <= target_di_n:
            starts, cases = costs[index]
            return {"target_di_n": target_di_n, "design_id": rec.design_id,
                    "design_evaluations": index + 1, "design_starts": starts,
                    "internal_solver_cases": cases, "di_n": rec.di_n}
    return None


def summarize_run(evaluations, *, budgets: Sequence[int] = (4, 8, 16, 32, 64, 128),
                  reference_di_n: Optional[float] = None,
                  target_di_n: Optional[float] = None,
                  cost_key: str = "design_starts") -> dict:
    records = _records(evaluations)
    return {
        "schema": "dreal004.endpoint_summary.v1",
        "evaluations": len(records),
        "tasks": sorted({rec.task_id for rec in records}),
        "hit_rate": feasible_hit_rate(records),
        "first_feasible": first_feasible(records),
        "anytime_curve": anytime_curve(records, budgets, cost_key),
        "simple_regret": simple_regret(records, reference_di_n, None, cost_key),
        "cost_to_target": (None if target_di_n is None
                           else cost_to_target(records, target_di_n, cost_key)),
        "total_design_starts": sum(rec.design_starts for rec in records),
        "total_internal_solver_cases": sum(rec.internal_solver_cases for rec in records),
        "cost_key": cost_key,
        "reference_available": reference_di_n is not None,
    }
