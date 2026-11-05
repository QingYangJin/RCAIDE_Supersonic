# -*- coding: utf-8 -*-
"""P4 路线A S1：五臂预算公平性（D-S0-2-03）——纯元数据，零求解。

规则（D-S0-2-03，全部 fail-closed）：
- 同一任务上所有臂按固定顺序评价精确 B 个真实点；
- 阶段1 支持评价 K 个（计入 B）；阶段2 初始设计 8-K 个（计入 B）；阶段3 主搜索 B-8 个；
- 合计必须精确等于 B；K 未计入或各臂不等即抛 BudgetFairnessError；
- K=0 时 FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 同构：登记 CLONE，并从推断比较中排除；
- DE 的 8-K 个初始点同时作为初始 population 的一部分，不得额外评价。

本模块不产生任何物理调用（physical_call_count=0）。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from .family_v3 import ARM_IDS, BUDGETS, INITIAL_DESIGN_COUNT, K_VALUES, FamilyV3Error

__all__ = [
    "BudgetFairnessError",
    "ARM_IDS",
    "K_VALUES",
    "BUDGETS",
    "INITIAL_DESIGN_COUNT",
    "SUPPORT_ADAPTATION_ARMS",
    "ZERO_SHOT_ARM",
    "K0_CLONE_ARM",
    "clone_map",
    "inference_eligible_arms",
    "build_budget_plan",
    "build_all_budget_plans",
    "assert_budget_fairness",
    "build_fairness_report",
    "FAIRNESS_SCHEMA_VERSION",
]

FAIRNESS_SCHEMA_VERSION = "p4ra-budget-fairness-1"
SUPPORT_ADAPTATION_ARMS = ("PRETRAIN-KSHOT-BO", "FOMAML-KSHOT-BO")
# K=0：FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 同构；以 ZERO 为规范臂，KSHOT 登记 CLONE。
ZERO_SHOT_ARM = "FOMAML-ZERO-BO"
K0_CLONE_ARM = "FOMAML-KSHOT-BO"
# 不使用支持集标签的臂（仍评价 K 个支持点并计费）
NON_ADAPTATION_ARMS = ("RAND-BO", "FOMAML-ZERO-BO", "DE")


class BudgetFairnessError(ValueError):
    """预算映射/公平性违规（K 未计入 B、各臂不等、阶段和不一致等）。"""


def _validate_key(arm: str, k_shot: int, budget: int) -> None:
    if arm not in ARM_IDS:
        raise BudgetFairnessError(f"未知臂: {arm!r}，允许 {ARM_IDS}")
    if type(k_shot) is not int or k_shot not in K_VALUES:
        raise BudgetFairnessError(f"K 必须是 {K_VALUES} 之一，实际 {k_shot!r}")
    if type(budget) is not int or budget not in BUDGETS:
        raise BudgetFairnessError(f"B 必须是 {BUDGETS} 之一，实际 {budget!r}")


def clone_map(k_shot: int) -> dict[str, str]:
    """K=0 时 KSHOT 臂 = ZERO 臂的 CLONE；其他 K 无 CLONE。"""
    if type(k_shot) is not int or k_shot not in K_VALUES:
        raise BudgetFairnessError(f"K 必须是 {K_VALUES} 之一，实际 {k_shot!r}")
    if k_shot == 0:
        return {K0_CLONE_ARM: ZERO_SHOT_ARM}
    return {}


def inference_eligible_arms(k_shot: int) -> tuple[str, ...]:
    """可进入推断比较的臂（排除 K=0 的 CLONE 臂）。"""
    clones = set(clone_map(k_shot))
    return tuple(arm for arm in ARM_IDS if arm not in clones)


def build_budget_plan(arm: str, k_shot: int, budget: int) -> dict[str, Any]:
    """构造单个 (arm, K, B) 预算计划；所有阶段评价数显式记录并计入 billable。"""
    _validate_key(arm, k_shot, budget)
    support_evaluations = k_shot
    initial_evaluations = INITIAL_DESIGN_COUNT - k_shot
    main_evaluations = budget - INITIAL_DESIGN_COUNT
    if initial_evaluations < 0:
        raise BudgetFairnessError("初始设计数 8-K 不能为负")
    if main_evaluations < 0:
        raise BudgetFairnessError("主搜索评价数 B-8 不能为负")
    total = support_evaluations + initial_evaluations + main_evaluations
    if total != budget:
        raise BudgetFairnessError(f"阶段评价合计 {total} != B={budget}（预算公平性 fail-closed）")
    clone_of = clone_map(k_shot).get(arm)
    adaptation = arm in SUPPORT_ADAPTATION_ARMS and k_shot > 0
    stages = [
        {
            "stage": "support",
            "evaluations": support_evaluations,
            "counted_in_billable": True,
            "note": "任务支持池固定前 K 点（固定 seed/顺序）；所有臂共享同一批支持点、标签与顺序。",
        },
        {
            "stage": "initial_designs",
            "evaluations": initial_evaluations,
            "counted_in_billable": True,
            "note": "代理/随机机制补 8-K 个新点；DE 臂的这 8-K 点同时作为初始 population 的一部分。",
        },
        {
            "stage": "main_search",
            "evaluations": main_evaluations,
            "counted_in_billable": True,
            "note": "BO 臂为 B-8 次 BO 迭代；DE 臂为 B-8 次 DE 世代评价；不得额外评价。",
        },
    ]
    plan: dict[str, Any] = {
        "arm": arm,
        "K": k_shot,
        "B": budget,
        "support_evaluations": support_evaluations,
        "initial_design_evaluations": initial_evaluations,
        "main_search_evaluations": main_evaluations,
        "stages": stages,
        "budget": {
            "B_total": budget,
            "K_support": k_shot,
            "initial_designs": INITIAL_DESIGN_COUNT,
            "initial_design_evaluations": initial_evaluations,
            "main_search_evaluations": main_evaluations,
            "support_evaluations_counted": True,
        },
        "evaluations": {
            "billable": budget,
            "non_billable": 0,
            "physical_call_count": 0,
        },
        "support": {
            "K": k_shot,
            "evaluated_count": support_evaluations,
            "counted_in_billable": True,
            "shared_by_all_arms": True,
            "used_for_adaptation": bool(adaptation),
            "labels_visible_to_arm": bool(adaptation),
        },
        "clone_of": clone_of,
        "inference_eligible": clone_of is None,
        "notes": (
            ["K=0 时 FOMAML-KSHOT-BO 与 FOMAML-ZERO-BO 同构：登记 CLONE 并排除推断。"]
            if clone_of is not None
            else []
        ),
    }
    return plan


def build_all_budget_plans(
    *,
    arms: Sequence[str] = ARM_IDS,
    k_values: Sequence[int] = K_VALUES,
    budgets: Sequence[int] = BUDGETS,
) -> list[dict[str, Any]]:
    """5 臂 x 4 K x 2 B = 40 个预算计划（默认全组合）。"""
    if tuple(arms) != ARM_IDS:
        raise BudgetFairnessError(f"arms 必须为 {ARM_IDS}")
    if tuple(k_values) != K_VALUES:
        raise BudgetFairnessError(f"k_values 必须为 {K_VALUES}")
    if tuple(budgets) != BUDGETS:
        raise BudgetFairnessError(f"budgets 必须为 {BUDGETS}")
    return [
        build_budget_plan(arm, k_shot, budget)
        for k_shot in K_VALUES
        for budget in BUDGETS
        for arm in ARM_IDS
    ]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise BudgetFairnessError(message)


def assert_budget_fairness(plans: Sequence[Mapping[str, Any]]) -> bool:
    """逐计划重算 + 分组校验：任一字段被篡改/各臂不等/K 未计入 即 fail-closed。"""
    if not plans:
        raise BudgetFairnessError("assert_budget_fairness 需要非空计划列表")
    seen: set[tuple[str, int, int]] = set()
    groups: dict[tuple[int, int], set[str]] = {}
    for index, plan in enumerate(plans):
        if not isinstance(plan, Mapping):
            raise BudgetFairnessError(f"计划[{index}] 必须是对象")
        for field in ("arm", "K", "B"):
            if field not in plan:
                raise BudgetFairnessError(f"计划[{index}] 缺少字段 {field!r}")
        arm, k_shot, budget = plan["arm"], plan["K"], plan["B"]
        if type(k_shot) is not int or type(budget) is not int:
            raise BudgetFairnessError(f"计划[{index}] K/B 必须是 int")
        _validate_key(arm, k_shot, budget)
        key = (arm, k_shot, budget)
        if key in seen:
            raise BudgetFairnessError(f"计划重复: {key}")
        seen.add(key)
        expected = build_budget_plan(arm, k_shot, budget)
        for field in (
            "stages",
            "budget",
            "evaluations",
            "support",
            "clone_of",
            "inference_eligible",
        ):
            if isinstance(expected[field], Mapping):
                matches = dict(plan.get(field, {})) == expected[field]
            else:
                matches = plan.get(field) == expected[field]
            if not matches:
                raise BudgetFairnessError(
                    f"计划 {key} 的 {field} 与规范预算映射不一致（fail-closed）"
                )
        evaluations = plan.get("evaluations", {})
        _require(
            int(evaluations.get("billable", -1)) == budget,
            f"计划 {key} billable={evaluations.get('billable')!r} != B={budget}",
        )
        _require(
            int(evaluations.get("non_billable", -1)) == 0,
            f"计划 {key} non_billable 必须为 0",
        )
        _require(
            int(evaluations.get("physical_call_count", -1)) == 0,
            f"计划 {key} physical_call_count 必须为 0",
        )
        budget_block = plan.get("budget", {})
        _require(
            budget_block.get("support_evaluations_counted") is True,
            f"计划 {key} 的 K 个支持评价未计入 B（fail-closed）",
        )
        _require(
            int(plan.get("support_evaluations", -1)) == k_shot,
            f"计划 {key} support_evaluations 必须等于 K={k_shot}",
        )
        stage_sum = sum(int(stage.get("evaluations", 0)) for stage in plan.get("stages", []))
        _require(stage_sum == budget, f"计划 {key} 阶段评价合计 {stage_sum} != B={budget}")
        groups.setdefault((k_shot, budget), set()).add(arm)
    expected_groups = {(k_shot, budget) for k_shot in K_VALUES for budget in BUDGETS}
    if set(groups) != expected_groups:
        raise BudgetFairnessError(f"计划缺少分组: {sorted(expected_groups - set(groups))}")
    for group_key, arms in sorted(groups.items()):
        if arms != set(ARM_IDS):
            raise BudgetFairnessError(
                f"分组 {group_key} 的臂集合不完整: {sorted(set(ARM_IDS) - arms)}"
            )
        for arm in ARM_IDS:
            plan = next(
                item
                for item in plans
                if item["arm"] == arm and item["K"] == group_key[0] and item["B"] == group_key[1]
            )
            _require(
                int(plan["evaluations"]["billable"]) == group_key[1],
                f"分组 {group_key} 的 {arm} billable != B（各臂不等该预算）",
            )
    # CLONE 一致性：K=0 时 KSHOT 臂必须标记 CLONE 且不得进入推断；其他 K 不得误标。
    for k_shot in K_VALUES:
        expected_clone = clone_map(k_shot)
        for arm in ARM_IDS:
            matching = [
                item for item in plans if item["arm"] == arm and item["K"] == k_shot
            ]
            _require(len(matching) == len(BUDGETS), f"臂 {arm} K={k_shot} 的计划数不等于预算数")
            for plan in matching:
                if arm in expected_clone:
                    _require(plan.get("clone_of") == expected_clone[arm],
                             f"K={k_shot} 的 {arm} 必须标记 clone_of={expected_clone[arm]!r}")
                    _require(plan.get("inference_eligible") is False,
                             f"K={k_shot} 的 {arm} 是 CLONE，必须排除推断")
                else:
                    _require(plan.get("clone_of") is None,
                             f"K={k_shot} 的 {arm} 不得误标 CLONE")
                    _require(plan.get("inference_eligible") is True,
                             f"K={k_shot} 的 {arm} 应可进入推断")
    return True


def build_fairness_report(
    plans: Sequence[Mapping[str, Any]] | None = None, *, created_utc: str
) -> dict[str, Any]:
    """公平性证据载荷（供 EXT 证据 JSON；不含任何求解数据）。"""
    if not isinstance(created_utc, str) or not created_utc.strip():
        raise BudgetFairnessError("created_utc 必须是非空字符串")
    plan_list = [dict(plan) for plan in (plans if plans is not None else build_all_budget_plans())]
    assert_budget_fairness(plan_list)
    payload: dict[str, Any] = {
        "schema_version": FAIRNESS_SCHEMA_VERSION,
        "created_utc": created_utc,
        "family_id": "F-QE-feasible-v3",
        "physical_call_count": 0,
        "arms": list(ARM_IDS),
        "k_values": list(K_VALUES),
        "budgets": list(BUDGETS),
        "initial_design_count": INITIAL_DESIGN_COUNT,
        "plan_count": len(plan_list),
        "clone_pairs": [
            {"K": k_shot, "clone_arm": arm, "canonical_arm": canonical}
            for k_shot in K_VALUES
            for arm, canonical in clone_map(k_shot).items()
        ],
        "inference_eligible": {
            str(k_shot): list(inference_eligible_arms(k_shot)) for k_shot in K_VALUES
        },
        "assertion": "ALL_ARMS_BILLABLE_EQUALS_B_AND_K_COUNTED",
        "status": "PASS",
        "plans": plan_list,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return payload
