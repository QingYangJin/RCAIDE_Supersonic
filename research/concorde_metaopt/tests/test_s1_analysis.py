"""S1 只读分析/出图合同测试（unittest）。

覆盖执行计划 §9 验收与统计计划 v1.1：
- 冻结包 fail-closed（三方/五方回显、端点 9 键、禁用别名、缺列、校验和篡改）；
- run_records 强校验负控（缺必填/未知字段/别名/record_digest/run_id/预算/物理隔离/CLONE）；
- 聚合（opt seed -> (task, meta_seed) 均值、meta seed 等权 -> task）、null 不插补；
- 统计函数（Wilcoxon 精确/并列近似、Holm、bootstrap、效应量）与判定规则，不产生假数据；
- 端到端 21,000 条记录 -> 8 数据产物 + 7 张规范图、无绝对路径、physical=0；
- task-239 冻结身份解耦：五项身份从冻结包派生（v3 legacy / 合成 v4 包），expected_identity 提供时必须逐项一致；
- CLI 成功/失败返回码；
- task-250（R-V4-08）：formal 模式 code_sha 绑定、legacy 包拒绝、prereg 三键强校验、Holm 族动态大小。

全部测试纯离线：不 import 也不启动任何真实 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器。
"""

import contextlib
import copy
import csv
import io
import hashlib
import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.concorde_metaopt.meta_learning import family_v3  # noqa: E402
from research.concorde_metaopt.meta_learning import budget_fairness  # noqa: E402
from research.concorde_metaopt.meta_learning import s1_analysis as A  # noqa: E402
from research.concorde_metaopt.meta_learning import s1_figures as F  # noqa: E402

FROZEN_DIR = (
    REPO_ROOT
    / "research"
    / "concorde_metaopt"
    / "optimization_runs"
    / "p4ra-s0-2-freeze-20261105T072500Z"
)

_BUNDLE = None


def frozen_bundle():
    """模块级缓存：真实冻结包只做一次 fail-closed 校验（只读）。"""
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = A.load_frozen_bundle(FROZEN_DIR)
    return _BUNDLE


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_endpoint_values(
    *,
    K,
    budget_B,
    best_feasible_value=1.0,
    gap_to_reference=None,
    first_feasible_eval_index=None,
    feasible_hit_rate=0.25,
    hit_non_support=0.05,
):
    """按合同推导 9 键 endpoint_values（n_nonnull/null_rate/首次可行点派生字段一致）。"""
    if best_feasible_value is not None and gap_to_reference is None:
        gap_to_reference = float(best_feasible_value) - 0.4
    values = {
        "best_feasible_value": best_feasible_value,
        "gap_to_reference": gap_to_reference,
        "first_feasible_eval_index": first_feasible_eval_index,
        "feasible_hit_rate": feasible_hit_rate,
        "first_feasible_in_support": None,
        "first_feasible_after_support_index": None,
        "feasible_hit_rate_non_support": hit_non_support,
        "n_nonnull": 0,
        "null_rate": 0.0,
    }
    if first_feasible_eval_index is not None:
        first = int(first_feasible_eval_index)
        values["first_feasible_in_support"] = bool(first <= K)
        values["first_feasible_after_support_index"] = None if first <= K else int(first - K)
    non_null = sum(1 for name in A.PRIMARY_ENDPOINTS if values[name] is not None)
    values["n_nonnull"] = int(non_null)
    values["null_rate"] = (len(A.PRIMARY_ENDPOINTS) - non_null) / len(A.PRIMARY_ENDPOINTS)
    return values


def _record_plan_fields(status, budget_B, K):
    if status == "OK":
        return {
            "initial_designs": A.INITIAL_DESIGN_COUNT,
            "bo_calls": int(budget_B) - A.INITIAL_DESIGN_COUNT,
            "support_evals": int(K),
            "initial_evals": A.INITIAL_DESIGN_COUNT - int(K),
            "bo_evals": int(budget_B) - A.INITIAL_DESIGN_COUNT,
            "billable_evals": int(budget_B),
        }
    return {
        "initial_designs": A.INITIAL_DESIGN_COUNT,
        "bo_calls": int(budget_B) - A.INITIAL_DESIGN_COUNT,
        "support_evals": 0,
        "initial_evals": 0,
        "bo_evals": 0,
        "billable_evals": 0,
    }


def make_record(
    bundle=None,
    *,
    arm="RAND-BO",
    budget_B=64,
    K=0,
    task_id=None,
    split="meta_test",
    meta_seed=0,
    opt_seed=0,
    status="OK",
    endpoint_values=None,
    history_digest=None,
    identifiability=None,
    clone_of=None,
    inference_eligible=None,
    run_group_id=None,
    **overrides,
):
    """构造一条符合合同的 run_record（record_digest 自动重算）。"""
    bundle = frozen_bundle() if bundle is None else bundle
    if task_id is None:
        task_id = bundle.task_ids_for(split)[0]
    if endpoint_values is None:
        first = min(int(budget_B), int(K) + 2)
        endpoint_values = build_endpoint_values(
            K=K,
            budget_B=budget_B,
            best_feasible_value=1.1,
            first_feasible_eval_index=first,
        )
    if history_digest is None:
        history_digest = sha256_text(f"{split}|{task_id}|{budget_B}|{K}|{meta_seed}|{opt_seed}|{arm}")
    if identifiability is None:
        is_clone = int(K) == 0 and arm == A.CLONE_ALLOWED["arm"]
        identifiability = A.CLONE_IDENTIFIABILITY if is_clone else A.IDENTIFIABLE
        if is_clone:
            clone_of = A.CLONE_ALLOWED["canonical_arm"]
            inference_eligible = False
        else:
            clone_of = None
            inference_eligible = True
    if run_group_id is None:
        run_group_id = f"rg-{split}-B{budget_B}-K{K}"
    echo = bundle.expected_echo()
    record = {
        "schema_version": A.S1_RECORD_SCHEMA_VERSION,
        "run_id": f"S1TEST--{arm}--B{int(budget_B)}--K{int(K)}--T{task_id}--MS{int(meta_seed)}--OS{int(opt_seed)}",
        "run_group_id": run_group_id,
        "family_version": echo["family_version"],
        "family_fingerprint": echo["family_fingerprint"],
        "split_hash": echo["split_hash"],
        "prereg_digest": echo["prereg_digest"],
        "analysis_plan_digest": echo["analysis_plan_digest"],
        "split": split,
        "task_id": task_id,
        "arm": arm,
        "budget_B": int(budget_B),
        "K": int(K),
        "meta_seed": int(meta_seed),
        "opt_seed": int(opt_seed),
        "identifiability": identifiability,
        "clone_of": clone_of,
        "inference_eligible": inference_eligible,
        "endpoint_values": copy.deepcopy(endpoint_values),
        "fallback_values": {"best_objective_raw": 1.5, "min_constraint_violation_sum": 0.05},
        "cost": {
            "adaptation_wall_s": 0.01,
            "proxy_scoring_cost": 1.0,
            "peak_memory_mb": 16.0,
            "total_wall_s": 0.02,
        },
        "physics": {"physical_call_count": 0, "physical_call_sources": [], "physics_guard": "PASS"},
        "status": status,
        "failure_reason": None if status == "OK" else "synthetic failure",
        "history_digest": history_digest,
        "record_digest": "",
    }
    record.update(_record_plan_fields(status, budget_B, K))
    record.update(overrides)
    record.pop("record_digest", None)
    record["record_digest"] = A._canonical_record_digest(record)
    return record


def rehash_record(record):
    """重算 record_digest（用于构造 record_digest 正确的负控记录）。"""
    target = dict(record)
    target.pop("record_digest", None)
    target["record_digest"] = A._canonical_record_digest(target)
    return target


def write_record_files(directory, records, *, name="run_records.jsonl"):
    path = Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return path


# R-V4-02 / R-V4-04（task-230）：identifiability_report.json fixture（全部解析式、无真实数据）
IDENTITY_PAIRS = (
    ("FOMAML-KSHOT-BO", "FOMAML-ZERO-BO"),
    ("FOMAML-KSHOT-BO", "PRETRAIN-KSHOT-BO"),
    ("FOMAML-ZERO-BO", "PRETRAIN-KSHOT-BO"),
)


def structural_group_keys(records):
    """从 records 推导 report 组：{ (task_id,budget_B,K,meta_seed): {model-scored arms} }。"""
    groups = {}
    for record in records:
        arm = record.get("arm")
        if arm not in A.MODEL_SCORED_ARMS:
            continue
        key = (
            str(record["task_id"]),
            int(record["budget_B"]),
            int(record["K"]),
            int(record["meta_seed"]),
        )
        groups.setdefault(key, set()).add(str(arm))
    return groups


def write_identifiability_report(
    directory,
    records,
    *,
    threshold=0.90,
    schema_version=A.IDENTIFIABILITY_SCHEMA_VERSION_V4,
    overlap_map=None,
    ranking_override=None,
    drop_groups=(),
):
    """写 v4 identifiability_report.json（schema_version 传 v1 时降级为 legacy 报告）。

    overlap_map 键：(task_id, budget_B, K, meta_seed, "arm_a|arm_b")；缺省 overlap_rate=0.0。
    ranking_override 键：(task_id, budget_B, K, meta_seed)。
    """
    overlap_map = dict(overlap_map or {})
    ranking_override = dict(ranking_override or {})
    groups_map = structural_group_keys(records)
    for key in drop_groups:
        groups_map.pop(key, None)
    pair_status_counts = {}
    groups_payload = []
    for key in sorted(groups_map):
        arms = groups_map[key]
        task_id, budget, k_shot, meta_seed = key
        pairwise = []
        group_rates = []
        for arm_a, arm_b in IDENTITY_PAIRS:
            if arm_a not in arms or arm_b not in arms:
                continue
            label = A._pair_label(arm_a, arm_b)
            rate = float(overlap_map.get(key + (label,), 0.0))
            group_rates.append(rate)
            pair = {
                "arm_a": arm_a,
                "arm_b": arm_b,
                "shared_rows": 0,
                "row_count": 64,
                "overlap_rate": rate,
            }
            if schema_version == A.IDENTIFIABILITY_SCHEMA_VERSION_V4:
                status = (
                    A.STRUCTURAL_IDENTICAL
                    if rate >= threshold
                    else A.STRUCTURAL_IDENTIFIABLE
                )
                pair.update(
                    {
                        "threshold": float(threshold),
                        "pair_identifiable": bool(status == A.STRUCTURAL_IDENTIFIABLE),
                        "structural_status": status,
                    }
                )
                bucket = pair_status_counts.setdefault(label, {})
                bucket[status] = bucket.get(status, 0) + 1
            pairwise.append(pair)
        max_rate = max(group_rates) if group_rates else 0.0
        mean_rate = sum(group_rates) / len(group_rates) if group_rates else 0.0
        groups_payload.append(
            {
                "task_id": task_id,
                "budget_B": int(budget),
                "K": int(k_shot),
                "meta_seed": int(meta_seed),
                "arms": sorted(arms),
                "pairwise": pairwise,
                "max_overlap_rate": max_rate,
                "mean_overlap_rate": mean_rate,
                "ranking_status": ranking_override.get(
                    key,
                    "RANKING_INDISTINGUISHABLE" if max_rate >= threshold else "IDENTIFIABLE",
                ),
                "inference_allowed": bool(max_rate < threshold),
            }
        )
    payload = {
        "schema_version": schema_version,
        "threshold": float(threshold),
        "group_count": len(groups_payload),
        "pair_coverage": {},
        "groups": groups_payload,
    }
    if schema_version == A.IDENTIFIABILITY_SCHEMA_VERSION_V4:
        payload["pair_status_counts"] = pair_status_counts
        payload["status_counts"] = {
            status: sum(
                1
                for group in groups_payload
                for pair in group["pairwise"]
                if pair.get("structural_status") == status
            )
            for status in (A.STRUCTURAL_IDENTIFIABLE, A.STRUCTURAL_IDENTICAL)
        }
    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / "identifiability_report.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def structural_records(
    bundle,
    *,
    tasks=20,
    budgets=(64, 128),
    ks=(3, 5),
    metas=(0, 1, 2),
    arms=None,
):
    """构造仅含需要臂的合成记录（用于结构可辨识性/C5 单测）。"""
    arms = tuple(A.ARM_IDS if arms is None else arms)
    records = []
    task_ids = bundle.task_ids_for(A.MAIN_SPLIT)[: int(tasks)]
    for task_index, task_id in enumerate(task_ids):
        for meta_seed in metas:
            for budget in budgets:
                for k_shot in ks:
                    for arm in arms:
                        records.append(
                            signal_record(
                                bundle,
                                arm=arm,
                                budget_B=int(budget),
                                K=int(k_shot),
                                task_id=task_id,
                                split=A.MAIN_SPLIT,
                                meta_seed=int(meta_seed),
                                opt_seed=0,
                                task_index=task_index,
                            )
                        )
    return records


# 信号臂参数：仅用于「有信号」端到端 fixture；数值全部解析式固定，不含真实求解。
_ARM_BASE = {
    "RAND-BO": 1.30,
    "PRETRAIN-KSHOT-BO": 1.20,
    "FOMAML-ZERO-BO": 1.15,
    "FOMAML-KSHOT-BO": 1.00,
    "DE": 1.25,
}
_ARM_HIT = {
    "RAND-BO": 0.05,
    "PRETRAIN-KSHOT-BO": 0.10,
    "FOMAML-ZERO-BO": 0.20,
    "FOMAML-KSHOT-BO": 0.30,
    "DE": 0.08,
}
_ARM_FIRST_OFFSET = {
    "RAND-BO": 20,
    "PRETRAIN-KSHOT-BO": 10,
    "FOMAML-ZERO-BO": 6,
    "FOMAML-KSHOT-BO": 2,
    "DE": 15,
}

GRID_UNITS = tuple(
    [(64, 0)]
    + [(budget, K) for K in (1, 3, 5) for budget in A.BUDGETS]
)


def signal_record(bundle, *, arm, budget_B, K, task_id, split, meta_seed, opt_seed, task_index=0):
    """生成固定信号的合成记录；K=0 的 CLONE 臂与 FOMAML-ZERO-BO 端点/历史完全一致。"""
    canonical_arm = "FOMAML-ZERO-BO" if (int(K) == 0 and arm == A.CLONE_ALLOWED["arm"]) else arm
    scale = 1e-6 * float(task_index) + 1e-5 * float(meta_seed) + 1e-4 * float(opt_seed)
    base = _ARM_BASE[canonical_arm]
    best = base + scale
    gap = best - 0.40
    first = min(int(budget_B), int(K) + _ARM_FIRST_OFFSET[canonical_arm])
    endpoint_values = build_endpoint_values(
        K=K,
        budget_B=budget_B,
        best_feasible_value=best,
        gap_to_reference=gap,
        first_feasible_eval_index=first,
        feasible_hit_rate=_ARM_HIT[canonical_arm],
        hit_non_support=0.02,
    )
    # K=0 的 CLONE 与 canonical 共享历史摘要（逐字节等价合同的 fixture 表达）。
    history = sha256_text(f"history|{split}|{task_id}|{budget_B}|{K}|{meta_seed}|{opt_seed}")
    return make_record(
        bundle,
        arm=arm,
        budget_B=budget_B,
        K=K,
        task_id=task_id,
        split=split,
        meta_seed=meta_seed,
        opt_seed=opt_seed,
        endpoint_values=endpoint_values,
        history_digest=history,
        run_group_id="rg-s1-e2e",
    )


def full_meta_test_records(bundle):
    """主 split 完整网格：20 tasks x 3 meta seeds x 10 opt seeds x 35 单元 = 21,000 条。"""
    records = []
    for task_index, task_id in enumerate(bundle.task_ids_for(A.MAIN_SPLIT)):
        for meta_seed in (0, 1, 2):
            for opt_seed in range(10):
                for budget_B, K in GRID_UNITS:
                    for arm in A.ARM_IDS:
                        records.append(
                            signal_record(
                                bundle,
                                arm=arm,
                                budget_B=budget_B,
                                K=K,
                                task_id=task_id,
                                split=A.MAIN_SPLIT,
                                meta_seed=meta_seed,
                                opt_seed=opt_seed,
                                task_index=task_index,
                            )
                        )
    return records


def make_record_for_pair(bundle, *, comparison_id, treatment_value, reference_value, budget_B=64, K=3, task_index=0):
    """构造 C1 一对记录（treatment=FOMAML-KSHOT-BO，reference=PRETRAIN-KSHOT-BO）。"""
    comparison = A.COMPARISON_BY_ID[comparison_id]
    task_id = bundle.task_ids_for(A.MAIN_SPLIT)[task_index]
    common = dict(
        bundle=bundle,
        budget_B=budget_B,
        K=K,
        task_id=task_id,
        split=A.MAIN_SPLIT,
        meta_seed=0,
        opt_seed=0,
        endpoint_values=build_endpoint_values(
            K=K, budget_B=budget_B, best_feasible_value=treatment_value, first_feasible_eval_index=K + 2
        ),
    )
    treatment = make_record(arm=comparison["arm"], **common)
    common["endpoint_values"] = build_endpoint_values(
        K=K, budget_B=budget_B, best_feasible_value=reference_value, first_feasible_eval_index=K + 10
    )
    reference = make_record(arm=comparison["reference"], **common)
    return treatment, reference


class TempDirMixin(unittest.TestCase):
    def make_temp_dir(self):
        path = Path(tempfile.mkdtemp(prefix="s1-analysis-test-"))
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path


# ---------------------------------------------------------------------------
# 冻结包 fail-closed 校验（A5 phase2 §7 前置）
# ---------------------------------------------------------------------------


def _load_frozen_payloads():
    payloads = {}
    raw = {}
    for name in A.FROZEN_PAYLOAD_FILES:
        data = (FROZEN_DIR / name).read_bytes()
        raw[name] = data
        payloads[name] = json.loads(data.decode("utf-8"))
    # freeze_summary 不属于 payload 合同文件（不含 sha256 自校验），回显链仍需要它。
    summary_name = "freeze_summary.json"
    summary_bytes = (FROZEN_DIR / summary_name).read_bytes()
    raw[summary_name] = summary_bytes
    payloads[summary_name] = json.loads(summary_bytes.decode("utf-8"))
    return payloads, raw


def _echo_check(payloads, raw):
    return A._cross_check_echo_chain(
        payloads["frozen_family.json"],
        payloads["preregistration.json"],
        payloads["meta_task_split.json"],
        payloads["freeze_summary.json"],
        raw=raw,
    )


class FrozenBundleValidationTests(TempDirMixin):
    """冻结包必须与 A5 phase2 §7 放行常量逐字一致；任一漂移 fail-closed。"""

    def test_bundle_loads_with_expected_identity(self):
        bundle = frozen_bundle()
        self.assertEqual(bundle.family_id, "F-QE-feasible-v3")
        self.assertEqual(bundle.family_version, "p4ra-family-v3")
        self.assertEqual(bundle.split_counts, dict(family_v3.SPLIT_COUNTS))
        self.assertEqual(sum(bundle.split_counts.values()), 120)
        self.assertEqual(len(bundle.task_ids_for(A.MAIN_SPLIT)), 20)
        self.assertEqual(bundle.task_ids_for(A.MAIN_SPLIT)[0], "p4ra-FQE3-v3-TE-000")
        self.assertEqual(bundle.meta_seeds, (0, 1, 2))
        self.assertEqual(bundle.opt_seeds, tuple(range(10)))
        self.assertEqual(bundle.radius_base, 0.64)
        self.assertEqual(bundle.physical_call_count if hasattr(bundle, "physical_call_count") else 0, 0)

    def test_derived_identity_matches_v3_reference_and_is_package_sourced(self):
        # task-239：不再硬编码 v3 身份常量；五项期望值从冻结包派生。
        bundle = frozen_bundle()
        self.assertEqual(
            bundle.identity_five(),
            {
                "family_fingerprint": "e56e6921be6b94e6611a24618a6e331cd7e4417597926d089d71b00da8c1c0c3",
                "split_hash": "cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae",
                "prereg_digest": "6981f503fd6ea5a9fbe5de2d1825ae8993eb17e9fda5d2ff158e9248d88fd3df",
                "analysis_plan_digest": "37eee53c9018fce34e414fa553ad3986a2d1be87d10409bc28e4f697b63588df",
                "radius_base": 0.64,
            },
        )
        self.assertEqual(bundle.identity_source, A.IDENTITY_SOURCE_PACKAGE)
        self.assertEqual(bundle.expected_identity_fields, ())

    def test_module_no_longer_hardcodes_v3_identity_as_expectation(self):
        for name in (
            "FAMILY_FINGERPRINT",
            "SPLIT_HASH",
            "PREREG_DIGEST",
            "ANALYSIS_PLAN_DIGEST",
            "RADIUS_BASE",
            "FAMILY_VERSION",
        ):
            self.assertFalse(hasattr(A, name), msg=f"模块仍保留 v3 硬编码常量 {name}")
        self.assertEqual(
            tuple(A.IDENTITY_FIELDS),
            (
                "family_fingerprint",
                "split_hash",
                "prereg_digest",
                "analysis_plan_digest",
                "radius_base",
            ),
        )

    def test_endpoint_row_keys_are_exactly_nine_canonical_keys(self):
        expected = (
            "best_feasible_value",
            "gap_to_reference",
            "first_feasible_eval_index",
            "feasible_hit_rate",
            "first_feasible_in_support",
            "first_feasible_after_support_index",
            "feasible_hit_rate_non_support",
            "n_nonnull",
            "null_rate",
        )
        self.assertEqual(tuple(A.ENDPOINT_ROW_KEYS), expected)
        self.assertEqual(len(set(A.ENDPOINT_ROW_KEYS)), 9)
        self.assertIn("first_feasible_evaluation_index", A.FORBIDDEN_ENDPOINT_ALIASES)
        for alias in A.FORBIDDEN_ENDPOINT_ALIASES:
            self.assertNotIn(alias, A.ENDPOINT_ROW_KEYS)

    def test_echo_chain_accepts_real_frozen_bundle(self):
        payloads, raw = _load_frozen_payloads()
        _echo_check(payloads, raw)  # 不抛错即通过

    def test_endpoint_alias_in_frozen_payload_rejected(self):
        payloads, raw = _load_frozen_payloads()
        frozen = copy.deepcopy(payloads["frozen_family.json"])
        keys = list(frozen["endpoint_row_keys"])
        keys[keys.index("first_feasible_eval_index")] = "first_feasible_evaluation_index"
        frozen["endpoint_row_keys"] = keys
        payloads["frozen_family.json"] = frozen
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            _echo_check(payloads, raw)
        self.assertIn("ENDPOINT_ROW_KEYS", str(ctx.exception))

    def test_missing_endpoint_column_rejected(self):
        payloads, raw = _load_frozen_payloads()
        frozen = copy.deepcopy(payloads["frozen_family.json"])
        frozen["endpoint_row_keys"] = list(frozen["endpoint_row_keys"])[:-1]
        payloads["frozen_family.json"] = frozen
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            _echo_check(payloads, raw)
        self.assertIn("ENDPOINT_ROW_KEYS", str(ctx.exception))

    def test_extra_endpoint_key_rejected(self):
        payloads, raw = _load_frozen_payloads()
        frozen = copy.deepcopy(payloads["frozen_family.json"])
        frozen["endpoint_row_keys"] = list(frozen["endpoint_row_keys"]) + ["extra_column"]
        payloads["frozen_family.json"] = frozen
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            _echo_check(payloads, raw)
        self.assertIn("ENDPOINT_ROW_KEYS", str(ctx.exception))

    def test_analysis_plan_digest_tamper_rejected(self):
        payloads, raw = _load_frozen_payloads()
        payloads["frozen_family.json"] = copy.deepcopy(payloads["frozen_family.json"])
        payloads["frozen_family.json"]["analysis_plan_digest"] = "0" * 64
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            _echo_check(payloads, raw)
        self.assertIn("analysis_plan_digest", str(ctx.exception))

    def test_family_fingerprint_tamper_rejected(self):
        payloads, raw = _load_frozen_payloads()
        payloads["preregistration.json"] = copy.deepcopy(payloads["preregistration.json"])
        payloads["preregistration.json"]["family_fingerprint"] = "f" * 64
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            _echo_check(payloads, raw)
        self.assertIn("family_fingerprint", str(ctx.exception))

    def test_split_hash_tamper_rejected(self):
        payloads, raw = _load_frozen_payloads()
        payloads["meta_task_split.json"] = copy.deepcopy(payloads["meta_task_split.json"])
        payloads["meta_task_split.json"]["split_hash"] = "0" * 64
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            _echo_check(payloads, raw)
        self.assertIn("split_hash", str(ctx.exception))

    def test_prereg_digest_tamper_rejected(self):
        payloads, raw = _load_frozen_payloads()
        payloads["preregistration.json"] = copy.deepcopy(payloads["preregistration.json"])
        payloads["preregistration.json"]["prereg_digest"] = "0" * 64
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            _echo_check(payloads, raw)
        self.assertIn("prereg_digest", str(ctx.exception))

    def test_arms_echo_tamper_rejected(self):
        # 回归负控：arms 是 str 列表，不得被 int() 误解析（曾是实现 bug）；
        # 口令链会先做 digest 自校验，因此篡改 frozen.arms（不改自 sha）命中 arms 回显分支。
        payloads, raw = _load_frozen_payloads()
        payloads["frozen_family.json"] = copy.deepcopy(payloads["frozen_family.json"])
        payloads["frozen_family.json"]["arms"] = ["RAND-BO"]
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            _echo_check(payloads, raw)
        self.assertIn("arms", str(ctx.exception))

    def test_budget_fairness_negative_controls(self):
        _, raw = _load_frozen_payloads()
        payloads, _ = _load_frozen_payloads()
        report = payloads["budget_fairness_report.json"]
        tampered = copy.deepcopy(report)
        tampered["clone_pairs"][0]["canonical_arm"] = "RAND-BO"
        with self.assertRaises(A.S1FreezeValidationError):
            A._verify_budget_fairness(tampered)
        tampered = copy.deepcopy(report)
        tampered["inference_eligible"]["0"].append(A.CLONE_ALLOWED["arm"])
        with self.assertRaises(A.S1FreezeValidationError):
            A._verify_budget_fairness(tampered)
        tampered = copy.deepcopy(report)
        tampered["assertion"] = "UNVERIFIED"
        with self.assertRaises(A.S1FreezeValidationError):
            A._verify_budget_fairness(tampered)
        tampered = copy.deepcopy(report)
        tampered["physical_call_count"] = 1
        with self.assertRaises(A.S1FreezeValidationError):
            A._verify_budget_fairness(tampered)

    def test_tasks_payload_duplicate_task_rejected(self):
        payloads, _ = _load_frozen_payloads()
        tasks = copy.deepcopy(payloads["tasks.json"])
        tasks.append(copy.deepcopy(tasks[0]))
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A._verify_tasks_payload(tasks, payloads["meta_task_split.json"])
        self.assertIn("重复", str(ctx.exception))

    def test_missing_freeze_dir_rejected(self):
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A.load_frozen_bundle(self.make_temp_dir() / "does-not-exist")
        self.assertIn("不存在", str(ctx.exception))

    def test_missing_payload_file_rejected(self):
        target = self.make_temp_dir() / "freeze"
        shutil.copytree(FROZEN_DIR, target)
        (target / "preregistration.json").unlink()
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A.load_frozen_bundle(target)
        self.assertIn("缺少", str(ctx.exception))

    def test_tampered_payload_bytes_rejected_by_checksums(self):
        target = self.make_temp_dir() / "freeze"
        shutil.copytree(FROZEN_DIR, target)
        path = target / "frozen_family.json"
        text = path.read_text(encoding="utf-8")
        self.assertIn("0.64", text)
        path.write_text(text.replace("0.64", "0.65"), encoding="utf-8")
        with self.assertRaises(A.S1FreezeValidationError):
            A.load_frozen_bundle(target)

    def test_tampered_sha256sums_rejected(self):
        target = self.make_temp_dir() / "freeze"
        shutil.copytree(FROZEN_DIR, target)
        path = target / "SHA256SUMS.txt"
        lines = path.read_text(encoding="utf-8").splitlines()
        digest, name = lines[0].split(" *", 1)
        flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
        lines[0] = f"{flipped} *{name}"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(A.S1FreezeValidationError):
            A.load_frozen_bundle(target)

    def test_tampered_freeze_summary_radius_rejected(self):
        target = self.make_temp_dir() / "freeze"
        shutil.copytree(FROZEN_DIR, target)
        path = target / "freeze_summary.json"
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["radius_base"] = 0.65
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A.load_frozen_bundle(target, verify_checksums=False, verify_sha256sums=False)
        self.assertIn("radius_base", str(ctx.exception))

    def test_tampered_frozen_payload_rejected_even_without_checksum_files(self):
        target = self.make_temp_dir() / "freeze"
        shutil.copytree(FROZEN_DIR, target)
        path = target / "frozen_family.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("0.64", "0.65"), encoding="utf-8")
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A.load_frozen_bundle(target, verify_checksums=False, verify_sha256sums=False)
        self.assertIn("raw_sha256", str(ctx.exception))


# ---------------------------------------------------------------------------
# run_records 强校验负控（fail-closed）
# ---------------------------------------------------------------------------


class RecordValidationTests(TempDirMixin):
    def setUp(self):
        self.bundle = frozen_bundle()

    def assert_rejected(self, records, fragment):
        with self.assertRaises(A.S1RecordValidationError) as ctx:
            A.validate_run_records(records, self.bundle)
        self.assertIn(fragment, str(ctx.exception))

    def test_valid_record_passes(self):
        record = make_record(self.bundle)
        validation = A.validate_run_records([record], self.bundle)
        self.assertEqual(validation.record_count, 1)
        self.assertEqual(validation.counts_by_split, {"meta_test": 1})
        self.assertEqual(validation.counts_by_status, {"OK": 1})
        self.assertEqual(validation.clone_equivalence_checked, 0)

    # B01（task-226）：runner 写 grid_stratum，分析端必须接受合法分层并与 (B,K) 交叉校验。
    def test_grid_stratum_main_accepted(self):
        record = make_record(self.bundle, grid_stratum="main")
        validation = A.validate_run_records([record], self.bundle)
        self.assertEqual(validation.record_count, 1)
        self.assertEqual(A.expected_grid_stratum(64, 0), "main")
        self.assertEqual(A.expected_grid_stratum(64, 3), "main")
        self.assertEqual(A.expected_grid_stratum(64, 5), "main")

    def test_grid_stratum_secondary_accepted(self):
        record = make_record(self.bundle, budget_B=128, K=3, grid_stratum="secondary")
        A.validate_run_records([record], self.bundle)
        self.assertEqual(A.expected_grid_stratum(128, 3), "secondary")
        self.assertEqual(A.expected_grid_stratum(128, 5), "secondary")

    def test_grid_stratum_exploratory_accepted(self):
        record = make_record(self.bundle, budget_B=64, K=1, grid_stratum="exploratory")
        A.validate_run_records([record], self.bundle)
        self.assertEqual(A.expected_grid_stratum(64, 1), "exploratory")
        self.assertEqual(A.expected_grid_stratum(128, 1), "exploratory")

    def test_grid_stratum_null_or_absent_accepted(self):
        A.validate_run_records([make_record(self.bundle, grid_stratum=None)], self.bundle)
        record = make_record(self.bundle)
        record.pop("grid_stratum", None)
        A.validate_run_records([record], self.bundle)

    def test_grid_stratum_unknown_rejected(self):
        record = make_record(self.bundle, grid_stratum="bogus")
        self.assert_rejected([record], "grid_stratum 非法")

    def test_grid_stratum_non_string_rejected(self):
        record = make_record(self.bundle, grid_stratum=3)
        self.assert_rejected([record], "grid_stratum 必须是 str 或 null")

    def test_grid_stratum_mismatch_rejected(self):
        record = make_record(self.bundle, budget_B=128, K=3, grid_stratum="main")
        self.assert_rejected([record], "grid_stratum 与 (budget_B,K) 不一致")

    def test_grid_stratum_on_non_formal_grid_rejected(self):
        # (B=128, K=0) 不属于 formal 网格（K=0 只在 B=64 main），登记分层必须拒绝。
        self.assertIsNone(A.expected_grid_stratum(128, 0))
        record = make_record(self.bundle, budget_B=128, K=0, grid_stratum="main")
        self.assert_rejected([record], "不属于 formal 网格")

    # B01 续（task-226）：runner 的可辨识性审计字段（task-227 / S1-B03）也必须被分析端接受并校验。
    def test_initial_design_fields_null_accepted(self):
        record = make_record(
            self.bundle,
            initial_designs_sha256=None,
            initial_design_row_digests=None,
        )
        validation = A.validate_run_records([record], self.bundle)
        self.assertEqual(validation.record_count, 1)

    def test_initial_design_fields_valid_accepted(self):
        row_digests = [sha256_text(f"row-{index}") for index in range(A.INITIAL_DESIGN_COUNT)]
        record = make_record(
            self.bundle,
            initial_designs_sha256=sha256_text("initial-designs"),
            initial_design_row_digests=row_digests,
        )
        validation = A.validate_run_records([record], self.bundle)
        self.assertEqual(validation.record_count, 1)

    def test_initial_design_fields_k_shot_rows_accepted(self):
        row_digests = [sha256_text(f"k3-row-{index}") for index in range(A.INITIAL_DESIGN_COUNT - 3)]
        record = make_record(
            self.bundle,
            arm="RAND-BO",
            K=3,
            initial_designs_sha256=sha256_text("initial-designs-k3"),
            initial_design_row_digests=row_digests,
        )
        validation = A.validate_run_records([record], self.bundle)
        self.assertEqual(validation.record_count, 1)

    def test_initial_design_row_count_mismatch_rejected(self):
        row_digests = [sha256_text(f"row-{index}") for index in range(A.INITIAL_DESIGN_COUNT - 1)]
        record = make_record(self.bundle, initial_design_row_digests=row_digests)
        self.assert_rejected([record], "initial_design_row_digests")

    def test_initial_design_row_bad_hex_rejected(self):
        row_digests = [sha256_text(f"row-{index}") for index in range(A.INITIAL_DESIGN_COUNT)]
        row_digests[3] = "z" * 64
        record = make_record(self.bundle, initial_design_row_digests=row_digests)
        self.assert_rejected([record], "initial_design_row_digests[3]")

    def test_initial_designs_sha256_bad_format_rejected(self):
        record = make_record(self.bundle, initial_designs_sha256="NOT-A-SHA256")
        self.assert_rejected([record], "initial_designs_sha256")

    # A2-B01b / B01 续（task-226）：runner 的 cost.proxy_scoring_cost 是 object（模型打分明细），
    # 分析器容错 object 并 fail-closed 校验子字段（数值有限、键为 str、JSON 值）。
    def test_proxy_scoring_cost_object_accepted(self):
        record = make_record(self.bundle)
        record["cost"] = dict(record["cost"])
        record["cost"]["proxy_scoring_cost"] = {
            "kind": "model_scoring",
            "billable_evals": 64,
            "bo_evals": 59,
            "model_scoring": {
                "wall_s": 0.5,
                "initial_designs_sha256": sha256_text("initial-designs"),
                "initial_design_row_digests": [
                    sha256_text(f"row-{index}") for index in range(A.INITIAL_DESIGN_COUNT)
                ],
            },
        }
        record = rehash_record(record)
        validation = A.validate_run_records([record], self.bundle)
        self.assertEqual(validation.record_count, 1)

    def test_proxy_scoring_cost_object_nonfinite_rejected(self):
        record = make_record(self.bundle)
        record["cost"] = dict(record["cost"])
        record["cost"]["proxy_scoring_cost"] = {"wall_s": float("nan")}
        record = rehash_record(record)
        self.assert_rejected([record], "有限")

    def test_proxy_scoring_cost_object_non_json_rejected(self):
        # 直接调用校验器：set 无法写入 record_digest 的规范化 JSON，故在 cost 校验层做负控。
        cost = {
            "adaptation_wall_s": 0.0,
            "proxy_scoring_cost": {"wall_s": {1, 2}},
            "peak_memory_mb": None,
            "total_wall_s": 0.0,
        }
        with self.assertRaises(A.S1RecordValidationError) as ctx:
            A._validate_cost(cost, 0)
        self.assertIn("不是合法 JSON 值", str(ctx.exception))

    def test_proxy_scoring_cost_negative_number_rejected(self):
        record = make_record(self.bundle)
        record["cost"] = dict(record["cost"])
        record["cost"]["proxy_scoring_cost"] = -1.0
        record = rehash_record(record)
        self.assert_rejected([record], "必须是非负有限数")

    def test_k0_clone_equivalence_checked(self):
        values = build_endpoint_values(K=0, budget_B=64, best_feasible_value=1.15, first_feasible_eval_index=2)
        history = sha256_text("clone-pair")
        canonical = make_record(
            self.bundle, arm="FOMAML-ZERO-BO", K=0, endpoint_values=values, history_digest=history
        )
        clone = make_record(
            self.bundle, arm="FOMAML-KSHOT-BO", K=0, endpoint_values=copy.deepcopy(values), history_digest=history
        )
        validation = A.validate_run_records([canonical, clone], self.bundle)
        self.assertEqual(validation.clone_count, 1)
        self.assertEqual(validation.clone_equivalence_checked, 1)

    def test_missing_required_field_rejected(self):
        record = make_record(self.bundle)
        record.pop("physics")
        self.assert_rejected([record], "缺少合同必填字段")

    def test_unknown_field_rejected(self):
        record = make_record(self.bundle, extra_field=1)
        self.assert_rejected([record], "未登记字段")

    def test_endpoint_alias_rejected(self):
        values = build_endpoint_values(K=3, budget_B=64, first_feasible_eval_index=5)
        values["first_feasible_evaluation_index"] = values.pop("first_feasible_eval_index")
        record = make_record(self.bundle, arm="FOMAML-KSHOT-BO", K=3, endpoint_values=values)
        self.assert_rejected([record], "禁用别名")

    def test_endpoint_missing_key_rejected(self):
        values = build_endpoint_values(K=3, budget_B=64, first_feasible_eval_index=5)
        values.pop("null_rate")
        record = make_record(self.bundle, arm="FOMAML-KSHOT-BO", K=3, endpoint_values=values)
        self.assert_rejected([record], "9 个规范键")

    def test_endpoint_extra_key_rejected(self):
        values = build_endpoint_values(K=3, budget_B=64, first_feasible_eval_index=5)
        values["extra_endpoint"] = 1.0
        record = make_record(self.bundle, arm="FOMAML-KSHOT-BO", K=3, endpoint_values=values)
        self.assert_rejected([record], "9 个规范键")

    def test_record_digest_tamper_rejected(self):
        record = make_record(self.bundle)
        record["record_digest"] = "0" * 64
        self.assert_rejected([record], "record_digest 自校验失败")

    def test_run_id_field_mismatch_rejected(self):
        record = make_record(self.bundle)
        record["run_id"] = record["run_id"].replace("RAND-BO", "DE")
        record = rehash_record(record)
        self.assert_rejected([record], "run_id 与记录字段不一致")

    def test_budget_mismatch_rejected(self):
        record = make_record(self.bundle)
        record["billable_evals"] = 63
        record = rehash_record(record)
        self.assert_rejected([record], "billable_evals")

    def test_physics_call_rejected(self):
        record = make_record(self.bundle)
        record["physics"] = {"physical_call_count": 1, "physical_call_sources": ["su2"], "physics_guard": "PASS"}
        record = rehash_record(record)
        self.assert_rejected([record], "physical_call_count")

    def test_clone_identity_violation_rejected(self):
        record = make_record(self.bundle, arm="FOMAML-KSHOT-BO", K=0)
        record["identifiability"] = A.IDENTIFIABLE
        record["clone_of"] = None
        record["inference_eligible"] = True
        record = rehash_record(record)
        self.assert_rejected([record], "CLONE")

    def test_k0_clone_equivalence_mismatch_rejected(self):
        values = build_endpoint_values(K=0, budget_B=64, best_feasible_value=1.15, first_feasible_eval_index=2)
        canonical = make_record(
            self.bundle,
            arm="FOMAML-ZERO-BO",
            K=0,
            endpoint_values=copy.deepcopy(values),
            history_digest=sha256_text("canonical"),
        )
        clone = make_record(
            self.bundle,
            arm="FOMAML-KSHOT-BO",
            K=0,
            endpoint_values=copy.deepcopy(values),
            history_digest=sha256_text("clone"),
        )
        self.assert_rejected([canonical, clone], "CLONE 逐字节等价失败")

    def test_frozen_echo_mismatch_rejected(self):
        record = make_record(self.bundle)
        record["family_version"] = "p4ra-family-v2"
        record = rehash_record(record)
        self.assert_rejected([record], "family_version")

    def test_task_not_in_split_rejected(self):
        other_task = self.bundle.task_ids_for("meta_train")[0]
        record = make_record(self.bundle, task_id=other_task, split="meta_test")
        self.assert_rejected([record], "不属于冻结 split")

    def test_meta_seed_not_frozen_rejected(self):
        record = make_record(self.bundle, meta_seed=3)
        self.assert_rejected([record], "meta_seed")

    def test_null_rate_inconsistent_rejected(self):
        values = build_endpoint_values(K=3, budget_B=64, first_feasible_eval_index=5)
        values["null_rate"] = 0.5
        record = make_record(self.bundle, arm="FOMAML-KSHOT-BO", K=3, endpoint_values=values)
        self.assert_rejected([record], "null_rate")

    def test_duplicate_run_id_across_files_rejected(self):
        directory = self.make_temp_dir()
        record = make_record(self.bundle)
        write_record_files(directory / "shard-a", [record])
        write_record_files(directory / "shard-b", [record])
        with self.assertRaises(A.S1RecordValidationError) as ctx:
            A.load_run_records(directory)
        self.assertIn("run_id 重复", str(ctx.exception))

    def test_invalid_json_line_rejected(self):
        directory = self.make_temp_dir()
        path = directory / "bad.jsonl"
        path.write_text("{not json}\n", encoding="utf-8")
        with self.assertRaises(A.S1RecordValidationError) as ctx:
            A.load_run_records(path)
        self.assertIn("不是合法 JSON", str(ctx.exception))

    def test_non_utf8_records_rejected(self):
        directory = self.make_temp_dir()
        path = directory / "bad.jsonl"
        path.write_bytes(b'{"run_id": "\xff\xfe"}\n')
        with self.assertRaises(A.S1RecordValidationError) as ctx:
            A.load_run_records(path)
        self.assertIn("非 UTF-8", str(ctx.exception))

    def test_failed_record_with_planned_budget_accepted(self):
        record = make_record(self.bundle, status="FAILED_BUDGET_MISMATCH", billable_evals=0)
        validation = A.validate_run_records([record], self.bundle)
        self.assertEqual(validation.failed_count, 1)
        self.assertEqual(validation.counts_by_status.get("FAILED_BUDGET_MISMATCH"), 1)


# ---------------------------------------------------------------------------
# 聚合层：opt seed -> (task, meta_seed) 均值；meta seed 等权 -> task
# ---------------------------------------------------------------------------


class AggregationTests(TempDirMixin):
    def setUp(self):
        self.bundle = frozen_bundle()
        self.task = self.bundle.task_ids_for(A.MAIN_SPLIT)[0]

    def _values(self, best, first):
        return build_endpoint_values(K=3, budget_B=64, best_feasible_value=best, first_feasible_eval_index=first)

    def test_opt_seed_mean_then_meta_seed_equal_weight(self):
        records = []
        for meta_seed, opt_values in ((0, (1.0, 3.0)), (1, (5.0, 5.0))):
            for opt_seed, value in enumerate(opt_values):
                records.append(
                    make_record(
                        self.bundle,
                        arm="RAND-BO",
                        budget_B=64,
                        K=3,
                        task_id=self.task,
                        meta_seed=meta_seed,
                        opt_seed=opt_seed,
                        endpoint_values=self._values(value, 5),
                    )
                )
        cells = A.aggregate_run_records(records, self.bundle)
        cell = cells[(A.MAIN_SPLIT, 64, 3, "RAND-BO")]
        self.assertAlmostEqual(cell.endpoint_per_task[self.task]["best_feasible_value"], 3.5, places=12)
        self.assertEqual(cell.n_ok_runs, 4)
        self.assertEqual(cell.n_runs[self.task], 4)
        self.assertEqual(cell.n_tasks, 20)

    def test_null_not_imputed_across_meta_seeds(self):
        null_values = build_endpoint_values(K=3, budget_B=64, best_feasible_value=None, first_feasible_eval_index=None)
        records = [
            make_record(
                self.bundle,
                arm="RAND-BO",
                budget_B=64,
                K=3,
                task_id=self.task,
                meta_seed=0,
                opt_seed=0,
                endpoint_values=self._values(2.0, 5),
            ),
            make_record(
                self.bundle,
                arm="RAND-BO",
                budget_B=64,
                K=3,
                task_id=self.task,
                meta_seed=1,
                opt_seed=0,
                endpoint_values=copy.deepcopy(null_values),
            ),
        ]
        cells = A.aggregate_run_records(records, self.bundle)
        cell = cells[(A.MAIN_SPLIT, 64, 3, "RAND-BO")]
        # 语义：null 的 meta seed 不插补为 0、也不参与均值；剩余非 null 的 meta seed 等权平均。
        self.assertIsNone(cell.endpoint_per_meta_seed[1][self.task]["best_feasible_value"])
        self.assertAlmostEqual(
            cell.endpoint_per_meta_seed[0][self.task]["best_feasible_value"], 2.0, places=12
        )
        self.assertAlmostEqual(cell.endpoint_per_task[self.task]["best_feasible_value"], 2.0, places=12)

    def test_failed_records_only_counted_not_aggregated(self):
        records = [
            make_record(
                self.bundle,
                arm="RAND-BO",
                budget_B=64,
                K=3,
                task_id=self.task,
                meta_seed=0,
                opt_seed=0,
                endpoint_values=self._values(2.0, 5),
            ),
            make_record(
                self.bundle,
                arm="RAND-BO",
                budget_B=64,
                K=3,
                task_id=self.task,
                meta_seed=1,
                opt_seed=0,
                status="FAILED_OTHER",
            ),
        ]
        cells = A.aggregate_run_records(records, self.bundle)
        cell = cells[(A.MAIN_SPLIT, 64, 3, "RAND-BO")]
        self.assertAlmostEqual(cell.endpoint_per_task[self.task]["best_feasible_value"], 2.0, places=12)
        self.assertEqual((cell.n_ok_runs, cell.n_failed_runs), (1, 1))
        self.assertIsNone(cell.endpoint_per_meta_seed[1][self.task]["best_feasible_value"])

    def test_expected_grid_has_35_units_and_21000_records(self):
        units = A.expected_grid_units(self.bundle, A.MAIN_SPLIT)
        self.assertEqual(len(units), 35)
        self.assertEqual(sum(units.values()), 21000)
        self.assertEqual(units[(64, 0, "DE")], 600)


# ---------------------------------------------------------------------------
# 统计层：Wilcoxon/Holm/bootstrap/效应量/阈值
# ---------------------------------------------------------------------------


class StatisticsTests(unittest.TestCase):
    def test_wilcoxon_exact_all_positive(self):
        result = A.wilcoxon_signed_rank([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        self.assertEqual(result["method"], "exact")
        self.assertEqual(result["n_effective"], 6)
        self.assertAlmostEqual(result["p_value"], 0.03125, places=15)
        self.assertAlmostEqual(result["statistic"], 0.0, places=15)

    def test_wilcoxon_exact_n20_all_positive(self):
        result = A.wilcoxon_signed_rank([float(index + 1) for index in range(20)])
        self.assertEqual(result["method"], "exact")
        self.assertAlmostEqual(result["p_value"], 2.0 / (2 ** 20), places=18)

    def test_wilcoxon_all_zero(self):
        result = A.wilcoxon_signed_rank([0.0, 0.0, 0.0])
        self.assertEqual(result["method"], "all_zero")
        self.assertEqual(result["p_value"], 1.0)
        self.assertEqual(result["n_effective"], 0)
        self.assertEqual(result["zero_count"], 3)

    def test_wilcoxon_ties_use_tie_corrected_approximation(self):
        result = A.wilcoxon_signed_rank([1.0, 1.0, 2.0, 2.0, 3.0, -3.0])
        self.assertTrue(result["ties_present"])
        self.assertEqual(result["method"], "normal_approx_tie_corrected")
        self.assertGreater(result["p_value"], 0.0)
        self.assertLessEqual(result["p_value"], 1.0)

    def test_paired_effect_sizes(self):
        effects = A.paired_effect_sizes([1.0, 2.0, 3.0])
        self.assertAlmostEqual(effects["mean_difference"], 2.0, places=15)
        self.assertAlmostEqual(effects["median_difference"], 2.0, places=15)
        self.assertAlmostEqual(effects["cohens_d"], 2.0, places=15)
        self.assertAlmostEqual(effects["rank_biserial"], 1.0, places=15)

    def test_paired_effect_sizes_zero_sd_returns_null(self):
        effects = A.paired_effect_sizes([2.0, 2.0, 2.0])
        self.assertIsNone(effects["cohens_d"])
        self.assertAlmostEqual(effects["mean_difference"], 2.0, places=15)

    def test_bootstrap_reproducible_with_same_seed_key(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        first = A.bootstrap_mean_ci(values, seed_key=("s1", "C1", 64, 3, "best_feasible_value"))
        second = A.bootstrap_mean_ci(values, seed_key=("s1", "C1", 64, 3, "best_feasible_value"))
        self.assertEqual(first, second)
        self.assertLess(first["low"], first["high"])
        self.assertEqual(first["samples"], A.BOOTSTRAP_SAMPLES)

    def test_bootstrap_single_value_returns_no_interval(self):
        result = A.bootstrap_mean_ci([1.0], seed_key=("s1",))
        self.assertIsNone(result["low"])
        self.assertIsNone(result["high"])

    def test_holm_adjust_known_values(self):
        adjusted = A.holm_adjust([0.01, 0.04, 0.03, None, 0.2])
        self.assertEqual(adjusted[3], None)
        self.assertAlmostEqual(adjusted[0], 0.04, places=15)
        self.assertAlmostEqual(adjusted[1], 0.09, places=15)
        self.assertAlmostEqual(adjusted[2], 0.09, places=15)
        self.assertAlmostEqual(adjusted[4], 0.2, places=15)

    def test_endpoint_thresholds(self):
        self.assertEqual(A._endpoint_threshold("feasible_hit_rate", 64), 0.05)
        self.assertEqual(A._endpoint_threshold("first_feasible_eval_index", 64), 4.0)
        self.assertEqual(A._endpoint_threshold("best_feasible_value", 64), 0.01)

    def _paired(self, **overrides):
        base = dict(
            comparison_id="C1",
            split=A.MAIN_SPLIT,
            budget_B=64,
            K=3,
            endpoint="best_feasible_value",
            treatment="FOMAML-KSHOT-BO",
            reference="PRETRAIN-KSHOT-BO",
            task_ids=[f"task-{index}" for index in range(20)],
            treatment_values=[2.0] * 20,
            reference_values=[2.2] * 20,
            paired_task_ids=[f"task-{index}" for index in range(20)],
            differences=[-0.2] * 20,
        )
        base.update(overrides)
        return A.PairedEndpoint(**base)

    def test_decide_endpoint_benefit(self):
        decision = A.decide_endpoint(
            self._paired(),
            test={"n_effective": 20},
            p_adjusted=0.001,
            improvement=0.2,
            ci_low=-0.3,
            ci_high=-0.1,
        )
        self.assertEqual(decision["decision"], A.DECISION_BENEFIT)
        self.assertTrue(decision["ci_defined"])
        self.assertAlmostEqual(decision["ci_low"], -0.3, places=15)
        self.assertAlmostEqual(decision["ci_high"], -0.1, places=15)

    def test_decide_endpoint_harm(self):
        decision = A.decide_endpoint(
            self._paired(),
            test={"n_effective": 20},
            p_adjusted=0.001,
            improvement=-0.2,
            ci_low=0.1,
            ci_high=0.3,
        )
        self.assertEqual(decision["decision"], A.DECISION_HARM)

    def test_decide_endpoint_no_evidence_below_threshold(self):
        decision = A.decide_endpoint(
            self._paired(),
            test={"n_effective": 20},
            p_adjusted=0.001,
            improvement=0.0,
            ci_low=-0.01,
            ci_high=0.01,
        )
        self.assertEqual(decision["decision"], A.DECISION_NONE)

    # B02（task-226）：bootstrap 95% CI 必须参与判定，跨 0 不得判 SUPPORTED_*。
    def test_decide_endpoint_significant_but_ci_crosses_zero(self):
        decision = A.decide_endpoint(
            self._paired(),
            test={"n_effective": 20},
            p_adjusted=0.001,
            improvement=0.2,
            ci_low=-0.05,
            ci_high=0.4,
        )
        self.assertEqual(decision["decision"], A.DECISION_NONE)
        self.assertTrue(any("CI" in reason and "跨 0" in reason for reason in decision["decision_reasons"]))

    def test_decide_endpoint_harm_ci_crosses_zero(self):
        decision = A.decide_endpoint(
            self._paired(),
            test={"n_effective": 20},
            p_adjusted=0.001,
            improvement=-0.2,
            ci_low=-0.4,
            ci_high=0.05,
        )
        self.assertEqual(decision["decision"], A.DECISION_NONE)

    # B02（task-226）方向矩阵：4 端点 x benefit / harm / 跨 0 / 方向不符，
    # 防止把「越小越好」端点（best_feasible_value/gap_to_reference/first_feasible_eval_index）
    # 的 CI 方向判反，也防止只对 feasible_hit_rate 正确。
    def test_decide_endpoint_ci_direction_matrix_for_all_primary_endpoints(self):
        cases = {
            # 每个端点的 beneficial CI（配对差值 treatment-reference 的方向）与达标改善量。
            "best_feasible_value": {"improvement": 0.2, "benefit_ci": (-0.3, -0.1)},
            "gap_to_reference": {"improvement": 0.2, "benefit_ci": (-0.3, -0.1)},
            "first_feasible_eval_index": {"improvement": 10.0, "benefit_ci": (-3.0, -1.0)},
            "feasible_hit_rate": {"improvement": 0.2, "benefit_ci": (0.1, 0.3)},
        }
        for endpoint, spec in cases.items():
            improvement = float(spec["improvement"])
            low, high = (float(value) for value in spec["benefit_ci"])
            paired = self._paired(endpoint=endpoint)
            with self.subTest(endpoint=endpoint, case="benefit"):
                decision = A.decide_endpoint(
                    paired,
                    test={"n_effective": 20},
                    p_adjusted=0.001,
                    improvement=improvement,
                    ci_low=low,
                    ci_high=high,
                )
                self.assertEqual(decision["decision"], A.DECISION_BENEFIT)
            with self.subTest(endpoint=endpoint, case="harm"):
                decision = A.decide_endpoint(
                    paired,
                    test={"n_effective": 20},
                    p_adjusted=0.001,
                    improvement=-improvement,
                    ci_low=-high,
                    ci_high=-low,
                )
                self.assertEqual(decision["decision"], A.DECISION_HARM)
            with self.subTest(endpoint=endpoint, case="cross_zero"):
                decision = A.decide_endpoint(
                    paired,
                    test={"n_effective": 20},
                    p_adjusted=0.001,
                    improvement=improvement,
                    ci_low=-abs(low),
                    ci_high=abs(high),
                )
                self.assertEqual(decision["decision"], A.DECISION_NONE)
                self.assertTrue(
                    any("跨 0" in reason for reason in decision["decision_reasons"]),
                    msg=f"{endpoint} 跨 0 的 reason 未说明：{decision['decision_reasons']}",
                )
            with self.subTest(endpoint=endpoint, case="direction_mismatch"):
                # CI 不跨 0 但方向与「改善」相反：不得判 BENEFIT。
                decision = A.decide_endpoint(
                    paired,
                    test={"n_effective": 20},
                    p_adjusted=0.001,
                    improvement=improvement,
                    ci_low=-high,
                    ci_high=-low,
                )
                self.assertEqual(decision["decision"], A.DECISION_NONE)
                self.assertTrue(
                    any("方向" in reason for reason in decision["decision_reasons"]),
                    msg=f"{endpoint} 方向不符的 reason 未说明：{decision['decision_reasons']}",
                )

    def test_decide_endpoint_missing_ci_is_inconclusive(self):
        decision = A.decide_endpoint(
            self._paired(),
            test={"n_effective": 20},
            p_adjusted=0.001,
            improvement=0.2,
        )
        self.assertEqual(decision["decision"], A.DECISION_INCONCLUSIVE)
        self.assertFalse(decision["ci_defined"])
        self.assertTrue(any("bootstrap CI" in reason for reason in decision["decision_reasons"]))

    def test_decide_endpoint_nonfinite_ci_is_inconclusive(self):
        decision = A.decide_endpoint(
            self._paired(),
            test={"n_effective": 20},
            p_adjusted=0.001,
            improvement=0.2,
            ci_low=float("nan"),
            ci_high=0.3,
        )
        self.assertEqual(decision["decision"], A.DECISION_INCONCLUSIVE)
        self.assertFalse(decision["ci_defined"])

    def test_decide_endpoint_inconclusive_small_n(self):
        decision = A.decide_endpoint(
            self._paired(paired_task_ids=[f"task-{index}" for index in range(5)]),
            test={"n_effective": 5},
            p_adjusted=0.001,
            improvement=0.2,
        )
        self.assertEqual(decision["decision"], A.DECISION_INCONCLUSIVE)

    def test_decide_endpoint_inconclusive_when_null_rate_above_70pct(self):
        paired = self._paired(
            treatment_values=[None] * 15 + [2.0] * 5,
        )
        decision = A.decide_endpoint(paired, test={"n_effective": 20}, p_adjusted=0.001, improvement=0.2)
        self.assertEqual(decision["decision"], A.DECISION_INCONCLUSIVE)
        self.assertAlmostEqual(decision["max_null_rate"], 0.75, places=12)
        self.assertTrue(any("null" in reason for reason in decision["decision_reasons"]))

    def test_analyze_pair_does_not_fabricate_data(self):
        paired = self._paired(
            budget_B=128,
            endpoint="feasible_hit_rate",
            treatment_values=[0.30] * 20,
            reference_values=[0.10] * 20,
            differences=[0.20] * 20,
        )
        row = A.analyze_pair(paired, p_adjusted=0.001)
        self.assertEqual(row["decision"], A.DECISION_BENEFIT)
        self.assertAlmostEqual(row["improvement"], 0.20, places=12)
        self.assertIsNotNone(row["ci_low"])
        self.assertIsNotNone(row["ci_high"])
        self.assertEqual(row["n_pairs"], 20)

    def test_analyze_pair_with_no_pairs_is_inconclusive(self):
        paired = self._paired(
            treatment_values=[None] * 20,
            reference_values=[None] * 20,
            paired_task_ids=[],
            differences=[],
        )
        row = A.analyze_pair(paired)
        self.assertEqual(row["decision"], A.DECISION_INCONCLUSIVE)
        self.assertIsNone(row["improvement"])
        self.assertIsNone(row["ci_low"])

    # M01（task-226）：预注册改善量用中位数，不用均值；配对子集两臂均非 null。
    def test_endpoint_improvement_uses_median_not_mean(self):
        treatment = [1.0] * 19 + [100.0]
        reference = [1.0] * 20
        paired = self._paired(
            treatment_values=treatment,
            reference_values=reference,
            differences=[left - right for left, right in zip(treatment, reference)],
        )
        improvement = A.endpoint_improvement(paired)
        # 中位数：处理臂 1.0、参考臂 1.0 -> 相对改善 0；均值法则会给出约 -4.95（严重离群）。
        self.assertAlmostEqual(improvement, 0.0, places=15)
        mean_based = (1.0 - (sum(treatment) / len(treatment))) / 1.0
        self.assertLess(mean_based, -4.0)
        row = A.analyze_pair(paired, p_adjusted=0.001)
        self.assertEqual(row["improvement_method"], "median_paired_subset")
        self.assertAlmostEqual(row["improvement"], 0.0, places=15)

    def test_endpoint_improvement_feasible_hit_rate_uses_median(self):
        treatment = [0.1] * 19 + [0.9]
        reference = [0.2] * 20
        paired = self._paired(
            endpoint="feasible_hit_rate",
            treatment_values=treatment,
            reference_values=reference,
            differences=[left - right for left, right in zip(treatment, reference)],
        )
        # 处理臂中位数 0.1，参考臂中位数 0.2 -> 绝对改善 -0.1；均值法为 -0.06。
        self.assertAlmostEqual(A.endpoint_improvement(paired), -0.1, places=15)

    def test_endpoint_improvement_first_feasible_uses_median(self):
        treatment = [2.0, 4.0, 6.0, 8.0, 100.0]
        reference = [10.0] * 5
        paired = self._paired(
            endpoint="first_feasible_eval_index",
            task_ids=[f"task-{index}" for index in range(5)],
            paired_task_ids=[f"task-{index}" for index in range(5)],
            treatment_values=treatment,
            reference_values=reference,
            differences=[left - right for left, right in zip(treatment, reference)],
        )
        # 处理臂中位数 6、参考臂中位数 10 -> 改善 4（评价次数更少更好）。
        self.assertAlmostEqual(A.endpoint_improvement(paired), 4.0, places=15)

    def test_endpoint_improvement_filters_unpaired_null_before_median(self):
        paired = self._paired(
            task_ids=["task-0", "task-1"],
            paired_task_ids=["task-1"],
            treatment_values=[None, 2.0],
            reference_values=[1.0, 2.2],
            differences=[2.0 - 2.2],
        )
        self.assertEqual(paired.n_pairs, 1)
        improvement = A.endpoint_improvement(paired)
        self.assertAlmostEqual(improvement, (2.2 - 2.0) / 2.2, places=15)


# ---------------------------------------------------------------------------
# 判定层：主结论 / 复现层 / 负控 payload
# ---------------------------------------------------------------------------


def _decision_row(comparison_id, budget_B, K, endpoint, decision):
    return {
        "comparison_id": comparison_id,
        "budget_B": int(budget_B),
        "K": int(K),
        "endpoint": endpoint,
        "decision": decision,
    }


class ConclusionTests(unittest.TestCase):
    def _rows(self, decisions):
        rows = []
        for K in (3, 5):
            for budget in (64, 128):
                for endpoint, decision in zip(A.PRIMARY_ENDPOINTS, decisions):
                    rows.append(_decision_row("C1", budget, K, endpoint, decision))
        return rows

    def test_primary_conclusion_supported_improvement(self):
        result = A.primary_conclusion(self._rows([A.DECISION_BENEFIT] * 4))
        self.assertEqual(result["overall"], A.OVERALL_ADVANTAGE)
        self.assertEqual(len(result["layers"]), 2)

    def test_primary_conclusion_all_inconclusive(self):
        result = A.primary_conclusion(self._rows([A.DECISION_INCONCLUSIVE] * 4))
        self.assertEqual(result["overall"], A.OVERALL_INCONCLUSIVE)

    def test_primary_conclusion_harm(self):
        rows = self._rows([A.DECISION_HARM] * 4)
        result = A.primary_conclusion(rows)
        self.assertEqual(result["overall"], A.OVERALL_HARM)

    def test_primary_conclusion_no_significant_improvement(self):
        result = A.primary_conclusion(self._rows([A.DECISION_NONE] * 4))
        self.assertEqual(result["overall"], A.OVERALL_NONE)

    def test_secondary_reproduction_states(self):
        supported = self._rows([A.DECISION_BENEFIT] * 4)
        self.assertEqual(A.secondary_reproduction_conclusion(supported)["status"], A.REPRODUCED)
        none_rows = [row for row in self._rows([A.DECISION_NONE] * 4) if row["budget_B"] == 128]
        self.assertEqual(A.secondary_reproduction_conclusion(none_rows)["status"], A.NOT_REPRODUCED)
        self.assertEqual(
            A.secondary_reproduction_conclusion([])["status"], A.REPRODUCTION_NOT_AVAILABLE
        )
        mixed = [row for row in self._rows([A.DECISION_BENEFIT] * 4) if row["budget_B"] == 128]
        mixed[0]["decision"] = A.DECISION_HARM
        mixed[1]["decision"] = A.DECISION_HARM
        self.assertEqual(A.secondary_reproduction_conclusion(mixed)["status"], A.REPRODUCTION_MIXED)


# ---------------------------------------------------------------------------
# 端到端：21,000 条完整网格 -> 6 数据产物 + 7 张规范图
# ---------------------------------------------------------------------------

_E2E = None


def full_e2e_run():
    """模块级缓存一次完整端到端运行（21,000 条），避免重复抽样拖慢测试。"""
    global _E2E
    if _E2E is None:
        directory, _identity = synthetic_v4c_confirmatory_freeze_package()
        bundle = A.load_frozen_bundle(directory)
        records = full_meta_test_records(bundle)
        records_path = write_record_files(directory, records)
        write_identifiability_report(directory, records)
        meta_log = directory / "meta_training_log.json"
        meta_log.write_text(
            json.dumps({"history": [{"epoch": index + 1, "loss": 1.0 / (index + 1)} for index in range(8)]}),
            encoding="utf-8",
        )
        out_dir = directory / "out"
        aggregate = A.run_s1_analysis(
            directory, records_path, out_dir, make_figures=True, meta_training_log=meta_log
        )
        _E2E = {
            "aggregate": aggregate,
            "out_dir": out_dir,
            "records_path": records_path,
            "directory": directory,
            "meta_log": meta_log,
        }
    return _E2E


class EndToEndTests(TempDirMixin):
    def test_full_grid_validates_and_aggregates(self):
        run = full_e2e_run()
        aggregate = run["aggregate"]
        validation = aggregate["validation"]
        self.assertEqual(validation["record_count"], 21000)
        self.assertEqual(validation["counts_by_split"], {"meta_test": 21000})
        self.assertEqual(validation["clone_count"], 600)
        self.assertEqual(validation["clone_equivalence_checked"], 600)
        self.assertEqual(aggregate["grid"]["status"], "PASS")
        self.assertEqual(aggregate["input"]["record_count"], 21000)
        self.assertEqual(aggregate["freeze_echo"]["radius_base"], 0.64)

    def test_primary_and_secondary_conclusions(self):
        aggregate = full_e2e_run()["aggregate"]
        self.assertEqual(aggregate["primary_conclusion"]["overall"], A.OVERALL_ADVANTAGE)
        self.assertEqual(aggregate["secondary_reproduction"]["status"], A.REPRODUCED)
        # 负控 split 无数据且未提供 determinism 报告：如实 NOT_AVAILABLE，不伪造 PASS。
        self.assertEqual(aggregate["negative_controls"]["status"], "NOT_AVAILABLE")
        self.assertEqual(aggregate["negative_controls"]["clone_k0"]["status"], "PASS")
        self.assertIn("null", aggregate["statistical_rules"]["null_policy"])
        self.assertTrue(aggregate["contract_ambiguities"])

    def test_all_contract_output_files_written(self):
        run = full_e2e_run()
        out_dir = run["out_dir"]
        for name in A.S1_OUTPUT_FILES:
            path = out_dir / name
            self.assertTrue(path.is_file(), msg=f"缺少产物 {name}")
            self.assertGreater(path.stat().st_size, 0, msg=f"产物为空 {name}")
        figure_status = json.loads((out_dir / "figure_status.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(A.FIGURE_KEYS), tuple(F.FIGURE_KEYS))
        self.assertEqual(set(figure_status["figures"]), set(F.FIGURE_KEYS))
        pngs = sorted(out_dir.glob("*.png"))
        self.assertEqual(len(pngs), 7, msg="7 张规范图必须全部生成")
        for key, filename in F.FIGURE_FILENAMES.items():
            self.assertEqual(figure_status["figures"][key], filename)
            target = out_dir / filename
            self.assertTrue(target.is_file())
            self.assertGreater(target.stat().st_size, 1000)
        self.assertEqual(figure_status["schema_version"], A.S1_FIGURE_STATUS_SCHEMA_VERSION)
        self.assertEqual(sorted(figure_status["generated"]), sorted(F.FIGURE_FILENAMES.values()))

    def test_outputs_contain_no_absolute_paths(self):
        run = full_e2e_run()
        out_dir = run["out_dir"]
        forbidden = ["D:/", "D:\\", "C:/", "C:\\", str(REPO_ROOT)]
        for path in sorted(out_dir.glob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in forbidden:
                self.assertNotIn(token, text, msg=f"{path.name} 含绝对路径 {token}")

    def test_physical_isolation_evidence(self):
        aggregate = full_e2e_run()["aggregate"]
        self.assertEqual(aggregate["limitations"][0].count("physical_call_count=0"), 1)
        for name in A.S1_OUTPUT_FILES:
            text = (full_e2e_run()["out_dir"] / name).read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("vspaero", text.lower())
            self.assertNotIn("su2", text.lower())

    def test_figure_status_is_honest_when_no_meta_log(self):
        # 无 meta 训练日志时 fig1 必须 NOT_RUN，其余图照常；不得伪造 fig1。
        run = full_e2e_run()
        status = F.render_figures(run["aggregate"], self.make_temp_dir() / "figs-no-log")
        self.assertEqual(status["figures"]["fig1_meta_training_loss"], F.STATUS_NOT_RUN)
        self.assertIn("fig1_meta_training_loss", status["notes"])
        for key in F.FIGURE_KEYS[1:]:
            self.assertEqual(status["figures"][key], F.FIGURE_FILENAMES[key])

    def test_render_figures_on_empty_aggregate_does_not_fabricate(self):
        directory = self.make_temp_dir() / "empty"
        status = F.render_figures({}, directory)
        self.assertEqual(set(status["figures"]), set(F.FIGURE_KEYS))
        self.assertEqual(list(directory.glob("*.png")), [])
        for key, value in status["figures"].items():
            self.assertIn(value, (F.STATUS_NOT_RUN, F.STATUS_NOT_APPLICABLE), msg=key)


# ---------------------------------------------------------------------------
# R-V4-08-01：唯一 Holm 族 = 同 (主端点, 预算_B, K) 内的全部可推断比较（C1-C4）
# ---------------------------------------------------------------------------


class HolmFamilyTests(unittest.TestCase):
    """R-V4-08-01：Holm 族键=(主端点, 预算_B, K)，成员 C1-C4（C5 不进族），族大小动态。"""

    @classmethod
    def setUpClass(cls):
        cls.aggregate = full_e2e_run()["aggregate"]

    def test_family_size_and_count_are_reported(self):
        population = self.aggregate["primary_population"]
        # R-V4-08-01：族键=(主端点, 预算_B, K)，成员为 C1..C4（C5 不进族），族大小动态记录。
        self.assertEqual(population["holm_family_key_fields"], ["primary_endpoint", "budget_B", "K"])
        self.assertTrue(population["holm_family_size_dynamic"])
        self.assertEqual(population["holm_family_max_size"], 4)
        self.assertEqual(population["holm_family_size_min"], 4)
        self.assertEqual(population["holm_family_size_max"], 4)
        self.assertEqual(population["holm_family_size_counts"], {"4": 24})
        self.assertEqual(population["holm_family_count"], 24)
        self.assertIn("R-V4-08-01", population["holm_family"])
        self.assertEqual(population["inference_comparison_ids"], ["C1", "C2", "C3", "C4"])
        self.assertEqual(population["excluded_comparison_ids"], ["C5"])
        sizes = self.aggregate["statistical_rules"]["holm_family_sizes"]
        self.assertEqual(len(sizes), 24)
        self.assertEqual(set(sizes.values()), {4})
        # 端点 4 个 x 预算 2 个 x 推断 K 3 个 = 24 个族。
        self.assertEqual(len({key.split("|")[0] for key in sizes}), 4)

    def test_holm_adjustment_grouped_by_endpoint_budget_and_k(self):
        rows = [row for row in self.aggregate["endpoint_rows"] if row.get("row_type") == "comparison"]
        # 4 个可推断比较 x 2 预算 x 3 个推断 K x 4 主端点 = 96 行（C5 不进推断）。
        self.assertEqual(len(rows), 96)
        self.assertEqual({row["comparison_id"] for row in rows}, {"C1", "C2", "C3", "C4"})
        families: dict[tuple[str, int, int], list[dict]] = {}
        for row in rows:
            key = (str(row["endpoint"]), int(row["budget_B"]), int(row["K"]))
            families.setdefault(key, []).append(row)
        self.assertEqual(len(families), 24)
        for key in sorted(families):
            family = families[key]
            self.assertEqual(len(family), 4, msg=str(key))
            expected = A.holm_adjust([row["p_raw"] for row in family])
            for row, adjusted in zip(family, expected):
                self.assertAlmostEqual(row["p_adjusted"], adjusted, places=15, msg=str(key))

    def test_c1_k3_best_endpoint_uses_family_of_five(self):
        rows = [
            row
            for row in self.aggregate["endpoint_rows"]
            if row.get("row_type") == "comparison"
            and row["comparison_id"] == "C1"
            and int(row["budget_B"]) == 64
            and int(row["K"]) == 3
            and row["endpoint"] == "best_feasible_value"
        ]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        # 每族 4 个检验：p_adj 至多 min(1, 4*p_raw)，绝不可能再按 40 个检验放大。
        self.assertLessEqual(row["p_adjusted"], min(1.0, 4.0 * row["p_raw"]) + 1e-15)


# ---------------------------------------------------------------------------
# B01 回归：runner 正式网格记录（含 grid_stratum）-> 分析端端到端可分析
# ---------------------------------------------------------------------------


class RunnerToAnalysisIntegrationTests(TempDirMixin):
    """用 runner 的 selftest 口径生成 1 条正式网格记录，验证 analysis 能加载/校验/出产物。"""

    @classmethod
    def setUpClass(cls):
        import importlib

        cls.runner = importlib.import_module("research.concorde_metaopt.meta_learning.s1_runner")
        cls.bundle = frozen_bundle()
        cls.task_id = cls.bundle.task_ids_for(A.MAIN_SPLIT)[0]

    def _runner_bundle_dir(self):
        directory = self.make_temp_dir() / "runner-bundle"
        package = self.runner.load_frozen_package(FROZEN_DIR)
        plan = [
            {
                "split": A.MAIN_SPLIT,
                "task_id": self.task_id,
                "arm": "RAND-BO",
                "budget_B": 64,
                "K": 3,
                "meta_seed": 0,
                "opt_seed": 0,
                "grid_stratum": "main",
            }
        ]
        run_id = "s1-selftest-analysis-integration"
        records = self.runner.execute_runs(package, run_id=run_id, plan=plan)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["grid_stratum"], "main")
        # 只读回归：runner 记录字段必须全部被 analysis 认识（防止 runner/analysis 记录 schema 静默漂移）。
        unknown = sorted(set(records[0]) - set(A.RECORD_KNOWN_FIELDS))
        self.assertEqual(unknown, [], msg=f"runner 记录出现 analysis 未登记字段：{unknown}")
        # 可辨识性审计字段：runner 必须写 8 行初始设计的 sha256（analysis 只做格式/行数校验）。
        self.assertRegex(records[0]["initial_designs_sha256"], r"^[0-9a-f]{64}$")
        # CONTRACT_AMBIGUITY：字段名似「全部初始设计」，但 runner 实际记录新初始点 = 8-K 行。
        self.assertEqual(
            len(records[0]["initial_design_row_digests"]),
            A.INITIAL_DESIGN_COUNT - int(records[0]["K"]),
        )
        for digest in records[0]["initial_design_row_digests"]:
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
        run_config = self.runner.build_grid_run_config(
            package,
            run_id=run_id,
            plan=plan,
            grid_mode=self.runner.FORMAL_GRID_MODE,
        )
        self.runner.write_run_bundle(
            directory,
            run_id=run_id,
            package=package,
            records=records,
            run_config=run_config,
        )
        return directory

    def test_runner_records_accepted_and_analyzed(self):
        bundle_dir = self._runner_bundle_dir()
        records, sources = A.load_run_records(bundle_dir)
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["grid_stratum"], "main")
        self.assertEqual(records[0]["physics"]["physical_call_count"], 0)
        validation = A.validate_run_records(records, self.bundle)
        self.assertEqual(validation.record_count, 1)
        self.assertEqual(validation.counts_by_status, {"OK": 1})
        self.assertEqual(validation.counts_by_arm, {"RAND-BO": 1})

        out_dir = self.make_temp_dir() / "analysis-out"
        aggregate = A.run_s1_analysis(
            FROZEN_DIR,
            bundle_dir,
            out_dir,
            make_figures=False,
            require_complete_grid=False,
            analysis_mode=A.ANALYSIS_MODE_EXPLORATORY,
            allow_legacy=True,
            allow_code_delta=True,
        )
        self.assertFalse(aggregate["confirmatory_eligible"])
        self.assertEqual(aggregate["validation"]["record_count"], 1)
        self.assertEqual(aggregate["grid"]["status"], "SKIPPED_BY_CALLER")
        for name in A.S1_OUTPUT_FILES:
            self.assertTrue((out_dir / name).is_file(), msg=f"缺少产物 {name}")
        self.assertEqual(
            aggregate["figure_status"]["figures"]["fig1_meta_training_loss"], "NOT_RUN"
        )
        self.assertEqual(
            aggregate["limitations"][0].count("physical_call_count=0"), 1
        )


# ---------------------------------------------------------------------------
# CLI：成功/失败返回码（只读分析）
# ---------------------------------------------------------------------------


def sparse_records(bundle, *, tasks=3, meta_seeds=(0, 1), opt_seeds=(0, 1)):
    records = []
    for task_index in range(tasks):
        task_id = bundle.task_ids_for(A.MAIN_SPLIT)[task_index]
        for meta_seed in meta_seeds:
            for opt_seed in opt_seeds:
                for budget_B, K in GRID_UNITS:
                    for arm in A.ARM_IDS:
                        records.append(
                            signal_record(
                                bundle,
                                arm=arm,
                                budget_B=budget_B,
                                K=K,
                                task_id=task_id,
                                split=A.MAIN_SPLIT,
                                meta_seed=meta_seed,
                                opt_seed=opt_seed,
                                task_index=task_index,
                            )
                        )
    return records


class CliTests(TempDirMixin):
    def test_cli_success_returns_zero_and_writes_outputs(self):
        freeze_dir, _identity = synthetic_v4c_confirmatory_freeze_package()
        bundle = A.load_frozen_bundle(freeze_dir)
        directory = self.make_temp_dir()
        records = sparse_records(bundle)
        path = write_record_files(directory, records)
        write_identifiability_report(directory, records)
        out_dir = directory / "out"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = A.main(
                [
                    "--freeze-dir",
                    str(freeze_dir),
                    "--run-records",
                    str(path),
                    "--output-dir",
                    str(out_dir),
                    "--allow-incomplete-grid",
                    "--no-figures",
                ]
            )
        self.assertEqual(code, 0, msg=stderr.getvalue())
        self.assertNotIn("S1_ANALYSIS_FAILED", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["n_records"], len(records))
        self.assertEqual(payload["analysis_mode"], A.ANALYSIS_MODE_FORMAL)
        self.assertTrue(payload["confirmatory_eligible"])
        self.assertEqual(payload["c5_structural_identifiability"], A.C5_NOT_ESTIMABLE)
        self.assertTrue((out_dir / "aggregate.json").is_file())
        self.assertTrue((out_dir / "s1_structural_identifiability.csv").is_file())

    def test_cli_record_failure_returns_two(self):
        freeze_dir, _identity = synthetic_v4c_confirmatory_freeze_package()
        bundle = A.load_frozen_bundle(freeze_dir)
        directory = self.make_temp_dir()
        records = sparse_records(bundle, tasks=1, meta_seeds=(0,), opt_seeds=(0,))
        records[0].pop("physics")
        path = write_record_files(directory, records)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = A.main(
                [
                    "--freeze-dir",
                    str(freeze_dir),
                    "--run-records",
                    str(path),
                    "--output-dir",
                    str(directory / "out"),
                    "--allow-incomplete-grid",
                    "--no-figures",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("S1_ANALYSIS_FAILED", stderr.getvalue())
        self.assertFalse((directory / "out" / "aggregate.json").exists())

    def test_cli_frozen_bundle_failure_returns_two(self):
        bundle = frozen_bundle()
        directory = self.make_temp_dir()
        path = write_record_files(directory, sparse_records(bundle, tasks=1, meta_seeds=(0,), opt_seeds=(0,)))
        bad_freeze = directory / "bad-freeze"
        shutil.copytree(FROZEN_DIR, bad_freeze)
        frozen_path = bad_freeze / "frozen_family.json"
        frozen_path.write_text(frozen_path.read_text(encoding="utf-8").replace("0.64", "0.65"), encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = A.main(
                [
                    "--freeze-dir",
                    str(bad_freeze),
                    "--run-records",
                    str(path),
                    "--output-dir",
                    str(directory / "out"),
                    "--allow-incomplete-grid",
                    "--no-figures",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("S1_ANALYSIS_FAILED", stderr.getvalue())


# ---------------------------------------------------------------------------
# task-239：冻结身份解耦（五项从包派生；expected_identity 可选强校验）
# ---------------------------------------------------------------------------

_V4_PACKAGE = None


def _v3_reference_task_fingerprints():
    """取 v3 旧冻结包 120 个任务 fingerprint（v4 构建要求的参考指纹集合）。"""
    payload = json.loads((FROZEN_DIR / "tasks.json").read_text(encoding="utf-8"))
    return [str(record["task_fingerprint"]) for record in payload]


def synthetic_v4_freeze_package():
    """模块级缓存：构造自洽的合成 v4 冻结包（不读新 meta_test/OOD，不跑任何数值）。

    返回 (directory, expected_identity)：expected_identity 为从包派生的五项。
    """
    global _V4_PACKAGE
    if _V4_PACKAGE is None:
        created = "2026-11-06T00:00:00Z"
        legacy = {
            "task_ids": ["legacy-m2-task-000"],
            "task_fingerprints": [],
            "sources": [
                {
                    "source": "legacy/tests",
                    "input_name": "tasks.json",
                    "task_id_count": 1,
                    "task_fingerprint_count": 0,
                }
            ],
        }
        bundle = family_v3.build_freeze_bundle(
            run_id="p4ra-s0-3-freeze-20261106T000000Z",
            git_sha="0" * 40,
            created_utc=created,
            legacy=legacy,
            calibration_status="CALIBRATED",
            radius_base=0.64,
            holdout_seed=family_v3.HOLDOUT_SEED,
            v3_reference_task_fingerprints=_v3_reference_task_fingerprints(),
        )
        directory = Path(tempfile.mkdtemp(prefix="s1-v4-freeze-"))
        payloads = {
            "tasks.json": bundle["task_records"],
            "meta_task_split.json": bundle["split_manifest"],
            "v3_isolation_report.json": bundle["isolation_report"],
            "frozen_family.json": bundle["frozen_family"],
            "preregistration.json": bundle["preregistration"],
            "budget_fairness_report.json": budget_fairness.build_fairness_report(created_utc=created),
        }
        raw = {}
        for name, payload in payloads.items():
            data = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
            (directory / name).write_bytes(data)
            raw[name] = data
        artifacts = []
        for name in A.FROZEN_PAYLOAD_FILES:
            payload = payloads[name]
            entry = {
                "path": name,
                "bytes": len(raw[name]),
                "canonical_sha256": A._canonical_artifact_digest(payload),
                "raw_sha256": hashlib.sha256(raw[name]).hexdigest(),
            }
            if isinstance(payload, dict) and isinstance(payload.get("sha256"), str):
                entry["stored_sha256"] = payload["sha256"]
            artifacts.append(entry)
        manifest = family_v3.build_digest_manifest(artifacts, created_utc=created)
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (directory / "digest_manifest.json").write_bytes(manifest_bytes)
        raw["digest_manifest.json"] = manifest_bytes
        canonical = {
            name: A._canonical_artifact_digest(payloads[name]) for name in A.FROZEN_PAYLOAD_FILES
        }
        frozen = bundle["frozen_family"]
        split = bundle["split_manifest"]
        prereg = bundle["preregistration"]

        def rawsha(name):
            return hashlib.sha256(raw[name]).hexdigest()

        summary = {
            "schema_version": "p4ra-freeze-summary-2",
            "created_utc": created,
            "run_id": "p4ra-s0-3-freeze-20261106T000000Z",
            "git_sha": "0" * 40,
            "code_sha": "tests",
            "family_id": family_v3.FAMILY_ID,
            "family_version": frozen["family_version"],
            "family_seed": family_v3.FAMILY_SEED,
            "formula_version": family_v3.FORMULA_VERSION,
            "radius_base": frozen["radius_base"],
            "frozen_at_utc": created,
            "calibration_status": frozen["calibration"]["status"],
            "artifacts": {
                name: {
                    "raw_sha256": rawsha(name),
                    "canonical_sha256": canonical[name],
                    "bytes": len(raw[name]),
                }
                for name in A.FROZEN_PAYLOAD_FILES
            },
            "digest_manifest": {
                "raw_sha256": rawsha("digest_manifest.json"),
                "canonical_sha256": A._canonical_artifact_digest(manifest),
                "bytes": len(manifest_bytes),
            },
            "orchestration": {
                "physical_call_count": 0,
                "family_fingerprint": frozen["family_fingerprint"],
                "split_hash": split["split_hash"],
                "prereg_digest": prereg["prereg_digest"],
                "analysis_plan_digest": frozen["analysis_plan_digest"],
                "radius_base": frozen["radius_base"],
                "frozen_family_sha256": canonical["frozen_family.json"],
                "preregistration_sha256": canonical["preregistration.json"],
                "budget_fairness_report_sha256": canonical["budget_fairness_report.json"],
                "isolation_report_sha256": canonical["v3_isolation_report.json"],
                "split_counts": dict(split["counts"]),
                "task_count": family_v3.TOTAL_TASKS,
            },
        }
        summary_bytes = (json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        (directory / "freeze_summary.json").write_bytes(summary_bytes)
        raw["freeze_summary.json"] = summary_bytes
        lines = [rawsha(name) + " *" + name for name in A.FROZEN_REQUIRED_FILES]
        (directory / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        expected = A.load_frozen_bundle(directory).identity_five()
        _V4_PACKAGE = (directory, expected)
    return _V4_PACKAGE


class IdentityDecouplingTests(TempDirMixin):
    """task-239：v3 旧包与合成 v4 包都通过；expected_identity 错误必须 fail-closed。"""

    def test_synthetic_v4_package_loads_with_package_identity(self):
        directory, expected = synthetic_v4_freeze_package()
        bundle = A.load_frozen_bundle(directory)
        v3 = frozen_bundle()
        self.assertEqual(bundle.family_version, "p4ra-family-v4")
        self.assertEqual(bundle.identity_source, A.IDENTITY_SOURCE_PACKAGE)
        self.assertEqual(bundle.expected_identity_fields, ())
        self.assertEqual(bundle.identity_five(), expected)
        # v4 重播种 meta_test/OOD 后 family fingerprint 与 prereg digest 必变；task_id 不变故 split hash 相同。
        self.assertNotEqual(bundle.identity.family_fingerprint, v3.identity.family_fingerprint)
        self.assertNotEqual(bundle.identity.prereg_digest, v3.identity.prereg_digest)
        self.assertEqual(bundle.identity.split_hash, v3.identity.split_hash)
        # R-V4-08-01 后 v4 采用新 analysis_plan（Holm 族唯一口径）；v3 legacy 包用旧 digest。
        self.assertEqual(bundle.identity.analysis_plan_digest, family_v3.ANALYSIS_PLAN_DIGEST)
        self.assertEqual(v3.identity.analysis_plan_digest, family_v3.LEGACY_ANALYSIS_PLAN_DIGEST)
        self.assertNotEqual(bundle.identity.analysis_plan_digest, v3.identity.analysis_plan_digest)
        self.assertAlmostEqual(bundle.identity.radius_base, 0.64, places=12)

    def test_synthetic_v4_expected_identity_roundtrip(self):
        directory, expected = synthetic_v4_freeze_package()
        bundle = A.load_frozen_bundle(
            directory, expected_identity=dict(expected), expected_identity_source="run_config.json"
        )
        self.assertEqual(bundle.identity_source, A.IDENTITY_SOURCE_EXPECTED)
        self.assertEqual(tuple(bundle.expected_identity_fields), tuple(A.IDENTITY_FIELDS))
        self.assertEqual(bundle.family_version, "p4ra-family-v4")

    def test_wrong_expected_identity_fails_closed(self):
        for freeze_dir in (FROZEN_DIR, synthetic_v4_freeze_package()[0]):
            bundle = A.load_frozen_bundle(freeze_dir)
            bad = bundle.identity_five()
            bad["family_fingerprint"] = "f" * 64
            with self.assertRaises(A.S1FreezeValidationError) as ctx:
                A.load_frozen_bundle(freeze_dir, expected_identity=bad)
            self.assertIn("与冻结包不一致", str(ctx.exception))
            bad_radius = bundle.identity_five()
            bad_radius["radius_base"] = 0.65
            with self.assertRaises(A.S1FreezeValidationError):
                A.load_frozen_bundle(freeze_dir, expected_identity=bad_radius)

    def test_expected_identity_missing_extra_or_bad_format_fails(self):
        expected = frozen_bundle().identity_five()
        cases = []
        for missing in A.IDENTITY_FIELDS:
            payload = dict(expected)
            payload.pop(missing)
            cases.append((f"missing {missing}", payload))
        extra = dict(expected)
        extra["unknown_field"] = "x"
        cases.append(("extra field", extra))
        bad_hex = dict(expected)
        bad_hex["split_hash"] = "zz"
        cases.append(("bad hex", bad_hex))
        bad_radius_type = dict(expected)
        bad_radius_type["radius_base"] = "0.64"
        cases.append(("bad radius type", bad_radius_type))
        for label, payload in cases:
            with self.subTest(case=label):
                with self.assertRaises(A.S1FreezeValidationError):
                    A.load_frozen_bundle(FROZEN_DIR, expected_identity=payload)
        with self.assertRaises(A.S1FreezeValidationError):
            A.load_frozen_bundle(FROZEN_DIR, expected_identity=["not", "a", "mapping"])

    def test_tampered_v4_payload_fails_closed(self):
        directory, _expected = synthetic_v4_freeze_package()
        tampered = self.make_temp_dir() / "tampered-v4"
        shutil.copytree(directory, tampered)
        frozen_path = tampered / "frozen_family.json"
        text = frozen_path.read_text(encoding="utf-8")
        self.assertIn("0.64", text)
        frozen_path.write_text(text.replace("0.64", "0.65", 1), encoding="utf-8")
        with self.assertRaises(A.S1FreezeValidationError):
            A.load_frozen_bundle(tampered)

    def _sparse_analysis_inputs(self):
        freeze_dir, _identity = synthetic_v4c_confirmatory_freeze_package()
        bundle = A.load_frozen_bundle(freeze_dir)
        directory = self.make_temp_dir()
        records = sparse_records(bundle, tasks=1, meta_seeds=(0,), opt_seeds=(0,))
        path = write_record_files(directory, records)
        write_identifiability_report(directory, records)
        return bundle, directory, path, freeze_dir

    def test_run_s1_analysis_records_identity_source(self):
        bundle, directory, path, freeze_dir = self._sparse_analysis_inputs()
        expected = bundle.identity_five()
        out_dir = directory / "out"
        aggregate = A.run_s1_analysis(
            freeze_dir,
            path,
            out_dir,
            make_figures=False,
            require_complete_grid=False,
            expected_identity=expected,
            expected_identity_source="run_config.json",
        )
        echo = aggregate["freeze_echo"]
        self.assertEqual(echo["identity_source"], A.IDENTITY_SOURCE_EXPECTED)
        self.assertEqual(echo["identity_five"], expected)
        self.assertEqual(tuple(echo["identity_expected_fields"]), tuple(A.IDENTITY_FIELDS))
        self.assertEqual(aggregate["input"]["identity_source"], A.IDENTITY_SOURCE_EXPECTED)
        self.assertEqual(aggregate["input"]["expected_identity_source"], "run_config.json")
        self.assertTrue((out_dir / "s1_freeze_identity.csv").is_file())
        with (out_dir / "s1_freeze_identity.csv").open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["identity_source"], A.IDENTITY_SOURCE_EXPECTED)
        self.assertEqual(rows[0]["family_fingerprint"], expected["family_fingerprint"])
        self.assertEqual(rows[0]["expected_identity_fields"], ";".join(A.IDENTITY_FIELDS))

    def test_run_s1_analysis_wrong_expected_identity_fails_closed(self):
        bundle, directory, path, freeze_dir = self._sparse_analysis_inputs()
        bad = bundle.identity_five()
        bad["prereg_digest"] = "0" * 64
        out_dir = directory / "out-bad"
        with self.assertRaises(A.S1FreezeValidationError):
            A.run_s1_analysis(
                freeze_dir,
                path,
                out_dir,
                make_figures=False,
                require_complete_grid=False,
                expected_identity=bad,
            )
        self.assertFalse((out_dir / "aggregate.json").exists())

    def test_cli_expected_identity_json_records_source(self):
        bundle, directory, path, freeze_dir = self._sparse_analysis_inputs()
        identity_path = directory / "expected_identity.json"
        identity_path.write_text(
            json.dumps(bundle.identity_five(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        out_dir = directory / "out-cli"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = A.main(
                [
                    "--freeze-dir",
                    str(freeze_dir),
                    "--run-records",
                    str(path),
                    "--output-dir",
                    str(out_dir),
                    "--allow-incomplete-grid",
                    "--no-figures",
                    "--expected-identity-json",
                    str(identity_path),
                ]
            )
        self.assertEqual(code, 0, msg=stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["identity_source"], A.IDENTITY_SOURCE_EXPECTED)
        self.assertTrue((out_dir / "s1_freeze_identity.csv").is_file())

    def test_cli_missing_expected_identity_json_returns_two(self):
        _bundle, directory, path, freeze_dir = self._sparse_analysis_inputs()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = A.main(
                [
                    "--freeze-dir",
                    str(freeze_dir),
                    "--run-records",
                    str(path),
                    "--output-dir",
                    str(directory / "out-missing"),
                    "--allow-incomplete-grid",
                    "--no-figures",
                    "--expected-identity-json",
                    str(directory / "does-not-exist.json"),
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("S1_ANALYSIS_FAILED", stderr.getvalue())


# ---------------------------------------------------------------------------
# task-250（R-V4-08）：v4c 确证冻结包三键、confirmatory_eligible、code_sha 绑定、
# legacy 拒绝与 Holm 族动态大小（物理解析式、随机性全部显式 seed；不读真实 meta_test/OOD）
# ---------------------------------------------------------------------------

_V4C_PACKAGE = None
V4C_RUN_ID = "p4ra-s0-4-freeze-20261106T000000Z"
V4C_CREATED_UTC = "2026-11-06T00:00:00Z"


def _build_v4c_confirmatory_package(
    src_dir,
    *,
    run_id=V4C_RUN_ID,
    created_utc=V4C_CREATED_UTC,
    code_sha=None,
    frozen_mutator=None,
    prereg_mutator=None,
):
    """由 task-239 的合成 v4 包构造 v4c 确证包（R-V4-08-02 三键 + confirmatory_eligible）。

    仅重写冻结载荷并重算 SHA256/prereg_digest 链；不触碰任务族内容、不生成真实包。
    返回新包目录（目录名即 run_id）。frozen_mutator/prereg_mutator 供负控注入漂移。
    """
    payloads = {
        name: json.loads((Path(src_dir) / name).read_text(encoding="utf-8"))
        for name in A.FROZEN_PAYLOAD_FILES
    }
    frozen = payloads["frozen_family.json"]
    prereg = payloads["preregistration.json"]
    split = payloads["meta_task_split.json"]
    frozen["run_id"] = run_id
    frozen["holdout_splits"] = dict(A.V4C_HOLDOUT_SPLIT_COUNTS)
    frozen["confirmatory_eligible"] = True
    if code_sha is not None:
        frozen["code_sha"] = code_sha
    if frozen_mutator is not None:
        frozen_mutator(frozen)
    frozen["sha256"] = family_v3.digest(
        {key: value for key, value in frozen.items() if key != "sha256"}
    )
    prereg["run_id"] = run_id
    prereg["holdout_splits"] = dict(A.V4C_HOLDOUT_SPLIT_COUNTS)
    prereg["confirmatory_eligible"] = True
    prereg["frozen_family_sha256"] = frozen["sha256"]
    prereg["holdout_package"] = {
        "run_id": run_id,
        "family_version": A.CONFIRMATORY_FAMILY_VERSION,
        "holdout_seed": prereg["holdout_seed"],
        "split_counts": dict(A.V4C_HOLDOUT_SPLIT_COUNTS),
        "task_count": A.V4C_HOLDOUT_TASK_COUNT,
        "frozen_family_sha256": frozen["sha256"],
        "package_path": "research/concorde_metaopt/optimization_runs/" + run_id,
    }
    prereg["c5_policy"] = dict(A.V4C_C5_POLICY)
    prereg["structural_identifiability"] = dict(A.V4C_STRUCTURAL_IDENTIFIABILITY)
    if prereg_mutator is not None:
        prereg_mutator(prereg)
    prereg["prereg_digest"] = family_v3.compute_prereg_digest(prereg)
    prereg["sha256"] = family_v3.digest(
        {key: value for key, value in prereg.items() if key != "sha256"}
    )
    directory = Path(tempfile.mkdtemp(prefix="s1-v4c-freeze-")) / run_id
    directory.mkdir(parents=True)
    raw = {}
    for name in A.FROZEN_PAYLOAD_FILES:
        data = (
            json.dumps(payloads[name], ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        (directory / name).write_bytes(data)
        raw[name] = data
    artifacts = []
    for name in A.FROZEN_PAYLOAD_FILES:
        payload = payloads[name]
        entry = {
            "path": name,
            "bytes": len(raw[name]),
            "canonical_sha256": A._canonical_artifact_digest(payload),
            "raw_sha256": hashlib.sha256(raw[name]).hexdigest(),
        }
        if isinstance(payload, dict) and isinstance(payload.get("sha256"), str):
            entry["stored_sha256"] = payload["sha256"]
        artifacts.append(entry)
    manifest = family_v3.build_digest_manifest(artifacts, created_utc=created_utc)
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (directory / "digest_manifest.json").write_bytes(manifest_bytes)
    raw["digest_manifest.json"] = manifest_bytes
    canonical = {
        name: A._canonical_artifact_digest(payloads[name])
        for name in A.FROZEN_PAYLOAD_FILES
    }
    summary = {
        "schema_version": "p4ra-freeze-summary-2",
        "created_utc": created_utc,
        "run_id": run_id,
        "git_sha": "0" * 40,
        "code_sha": frozen["code_sha"],
        "confirmatory_eligible": True,
        "family_id": family_v3.FAMILY_ID,
        "family_version": frozen["family_version"],
        "family_seed": family_v3.FAMILY_SEED,
        "formula_version": family_v3.FORMULA_VERSION,
        "radius_base": frozen["radius_base"],
        "frozen_at_utc": created_utc,
        "calibration_status": frozen["calibration"]["status"],
        "artifacts": {
            name: {
                "raw_sha256": hashlib.sha256(raw[name]).hexdigest(),
                "canonical_sha256": canonical[name],
                "bytes": len(raw[name]),
            }
            for name in A.FROZEN_PAYLOAD_FILES
        },
        "digest_manifest": {
            "raw_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "canonical_sha256": A._canonical_artifact_digest(manifest),
            "bytes": len(manifest_bytes),
        },
        "orchestration": {
            "physical_call_count": 0,
            "family_fingerprint": frozen["family_fingerprint"],
            "split_hash": split["split_hash"],
            "prereg_digest": prereg["prereg_digest"],
            "analysis_plan_digest": frozen["analysis_plan_digest"],
            "radius_base": frozen["radius_base"],
            "frozen_family_sha256": canonical["frozen_family.json"],
            "preregistration_sha256": canonical["preregistration.json"],
            "budget_fairness_report_sha256": canonical["budget_fairness_report.json"],
            "isolation_report_sha256": canonical["v3_isolation_report.json"],
            "split_counts": dict(split["counts"]),
            "task_count": family_v3.TOTAL_TASKS,
        },
    }
    summary_bytes = (
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    (directory / "freeze_summary.json").write_bytes(summary_bytes)
    raw["freeze_summary.json"] = summary_bytes
    sums = [
        hashlib.sha256(raw[name]).hexdigest() + " *" + name
        for name in A.FROZEN_REQUIRED_FILES
    ]
    (directory / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return directory


def synthetic_v4c_confirmatory_freeze_package():
    """模块级缓存：自洽的 v4c 确证冻结包（三键 + confirmatory_eligible=true）。"""
    global _V4C_PACKAGE
    if _V4C_PACKAGE is None:
        source_dir, _identity = synthetic_v4_freeze_package()
        directory = _build_v4c_confirmatory_package(source_dir)
        bundle = A.load_frozen_bundle(directory)
        _V4C_PACKAGE = (directory, bundle.identity_five())
    return _V4C_PACKAGE


def _sparse_records_and_paths(bundle, directory, *, tasks=2):
    records = sparse_records(bundle, tasks=tasks, meta_seeds=(0,), opt_seeds=(0,))
    path = write_record_files(directory, records)
    write_identifiability_report(directory, records)
    return records, path


class V4CConfirmatoryPackageTests(TempDirMixin):
    """R-V4-08-02/03/04：三键消费、legacy 拒绝、code_sha 绑定与非确证输出标记。"""

    @classmethod
    def setUpClass(cls):
        cls.freeze_dir, cls.expected_identity = synthetic_v4c_confirmatory_freeze_package()
        cls.bundle = A.load_frozen_bundle(cls.freeze_dir)

    def test_formal_compliance_pass_on_confirmatory_package(self):
        compliance = A.verify_analysis_freeze(self.bundle, analysis_mode=A.ANALYSIS_MODE_FORMAL)
        self.assertTrue(compliance["confirmatory_eligible"])
        self.assertFalse(compliance["legacy_package"])
        self.assertTrue(compliance["code_sha"]["match"])
        blocks = compliance["prereg_v4c_blocks"]
        self.assertEqual(blocks["status"], "PASS")
        self.assertEqual(blocks["rule"], "R-V4-08-02")
        values = blocks["values"]
        self.assertEqual(values["holdout_splits"], dict(A.V4C_HOLDOUT_SPLIT_COUNTS))
        self.assertEqual(values["holdout_package_run_id"], self.freeze_dir.name)
        self.assertTrue(values["holdout_package_package_path"].endswith(self.freeze_dir.name))
        self.assertFalse(values["c5_in_holm"])
        self.assertEqual(values["min_estimable_tasks"], 10)
        self.assertEqual(values["pair_overlap_threshold"], 0.90)

    def test_formal_analysis_marks_confirmatory_and_writes_outputs(self):
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(self.bundle, directory)
        out_dir = directory / "out"
        aggregate = A.run_s1_analysis(
            self.freeze_dir,
            path,
            out_dir,
            make_figures=False,
            require_complete_grid=False,
            expected_identity=self.expected_identity,
            expected_identity_source="run_config.json",
        )
        self.assertEqual(aggregate["analysis_mode"], A.ANALYSIS_MODE_FORMAL)
        self.assertTrue(aggregate["confirmatory_eligible"])
        self.assertEqual(aggregate["freeze_compliance"]["prereg_v4c_blocks"]["status"], "PASS")
        self.assertTrue(aggregate["freeze_echo"]["confirmatory_eligible"])
        self.assertEqual(aggregate["freeze_echo"]["identity_source"], A.IDENTITY_SOURCE_EXPECTED)
        self.assertEqual(
            aggregate["primary_population"]["holm_family_size_counts"], {"4": 24}
        )
        for name in A.S1_OUTPUT_FILES:
            self.assertTrue((out_dir / name).is_file(), msg=name)

    def test_formal_rejects_legacy_v3_package(self):
        bundle = frozen_bundle()
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(bundle, directory, tasks=1)
        out_dir = directory / "out"
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A.run_s1_analysis(
                FROZEN_DIR, path, out_dir, make_figures=False, require_complete_grid=False
            )
        self.assertIn(A.S1_ANALYSIS_LEGACY_PACKAGE, str(ctx.exception))
        self.assertFalse((out_dir / "aggregate.json").exists())

    def test_formal_rejects_old_v4_package_without_confirmatory_flag(self):
        # S0-3 是 v4 但缺三键/confirmatory_eligible 的只读历史包：formal 必须拒绝。
        old_dir = FROZEN_V4_DIR
        bundle = A.load_frozen_bundle(old_dir)
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(bundle, directory, tasks=1)
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A.run_s1_analysis(
                old_dir,
                path,
                directory / "out",
                make_figures=False,
                require_complete_grid=False,
            )
        self.assertIn(A.S1_ANALYSIS_LEGACY_PACKAGE, str(ctx.exception))

    def test_exploratory_allows_legacy_with_non_confirmatory_outputs(self):
        bundle = frozen_bundle()  # noqa: F841 - 保持旧 fixture 语义，records 由 sparse_records 生成
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(bundle, directory, tasks=2)
        aggregate = A.run_s1_analysis(
            FROZEN_DIR,
            path,
            directory / "out",
            make_figures=False,
            require_complete_grid=False,
            analysis_mode=A.ANALYSIS_MODE_EXPLORATORY,
            allow_legacy=True,
            allow_code_delta=True,
        )
        self.assertEqual(aggregate["analysis_mode"], A.ANALYSIS_MODE_EXPLORATORY)
        self.assertFalse(aggregate["confirmatory_eligible"])
        self.assertEqual(aggregate["primary_conclusion"]["overall"], A.OVERALL_INCONCLUSIVE)
        self.assertFalse(aggregate["primary_conclusion"]["confirmatory_eligible"])
        self.assertIn("non_confirmatory_reason", aggregate["primary_conclusion"])
        # ② legacy 放行必须写 warning，且输出明确 confirmatory_eligible=false。
        warnings = aggregate["freeze_compliance"]["warnings"]
        self.assertTrue(any("--allow-legacy" in str(item) for item in warnings), msg=str(warnings))
        self.assertFalse(aggregate["freeze_echo"]["confirmatory_eligible"])
        self.assertEqual(
            aggregate["secondary_reproduction"]["status"], A.REPRODUCTION_NOT_AVAILABLE
        )

    def test_formal_code_sha_drift_fails_closed(self):
        source_dir, _identity = synthetic_v4_freeze_package()
        drift_dir = _build_v4c_confirmatory_package(source_dir, code_sha="0" * 64)
        bundle = A.load_frozen_bundle(drift_dir)
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(bundle, directory, tasks=2)
        out_dir = directory / "out"
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A.run_s1_analysis(
                drift_dir, path, out_dir, make_figures=False, require_complete_grid=False
            )
        self.assertIn(A.S1_ANALYSIS_CODE_SHA_DRIFT, str(ctx.exception))
        self.assertFalse((out_dir / "aggregate.json").exists())

    def test_exploratory_allows_code_delta_but_stays_non_confirmatory(self):
        source_dir, _identity = synthetic_v4_freeze_package()
        drift_dir = _build_v4c_confirmatory_package(source_dir, code_sha="0" * 64)
        bundle = A.load_frozen_bundle(drift_dir)
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(bundle, directory, tasks=2)
        aggregate = A.run_s1_analysis(
            drift_dir,
            path,
            directory / "out",
            make_figures=False,
            require_complete_grid=False,
            analysis_mode=A.ANALYSIS_MODE_EXPLORATORY,
            allow_code_delta=True,
        )
        self.assertFalse(aggregate["confirmatory_eligible"])
        self.assertTrue(aggregate["freeze_compliance"]["code_sha"]["allow_code_delta"])
        self.assertEqual(aggregate["primary_conclusion"]["overall"], A.OVERALL_INCONCLUSIVE)

    def test_cli_formal_legacy_returns_two(self):
        bundle = frozen_bundle()
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(bundle, directory, tasks=1)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = A.main(
                [
                    "--freeze-dir",
                    str(FROZEN_DIR),
                    "--run-records",
                    str(path),
                    "--output-dir",
                    str(directory / "out"),
                    "--allow-incomplete-grid",
                    "--no-figures",
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("S1_ANALYSIS_FAILED", stderr.getvalue())
        self.assertIn(A.S1_ANALYSIS_LEGACY_PACKAGE, stderr.getvalue())

    def test_cli_exploratory_legacy_returns_zero(self):
        bundle = frozen_bundle()
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(bundle, directory, tasks=2)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = A.main(
                [
                    "--freeze-dir",
                    str(FROZEN_DIR),
                    "--run-records",
                    str(path),
                    "--output-dir",
                    str(directory / "out"),
                    "--allow-incomplete-grid",
                    "--no-figures",
                    "--analysis-mode",
                    "exploratory",
                    "--allow-legacy",
                    "--allow-code-delta",
                ]
            )
        self.assertEqual(code, 0, msg=stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["analysis_mode"], A.ANALYSIS_MODE_EXPLORATORY)
        self.assertFalse(payload["confirmatory_eligible"])


class PreregV4CBlocksTests(unittest.TestCase):
    """R-V4-08-02：prereg 三键（holdout_splits/holdout_package/c5_policy/structural）强校验。"""

    @classmethod
    def setUpClass(cls):
        cls.freeze_dir, _identity = synthetic_v4c_confirmatory_freeze_package()
        cls.bundle = A.load_frozen_bundle(cls.freeze_dir)
        cls.prereg = copy.deepcopy(cls.bundle.preregistration)
        cls.frozen = copy.deepcopy(cls.bundle.frozen_family)

    def _verify(self, prereg):
        return A.verify_prereg_v4c_blocks(
            prereg, frozen=self.frozen, freeze_dir_name=self.freeze_dir.name
        )

    def _drifted(self, mutate):
        prereg = copy.deepcopy(self.prereg)
        mutate(prereg)
        return prereg

    def test_blocks_pass_on_confirmatory_package(self):
        values = self._verify(self.prereg)
        self.assertEqual(values["holdout_package_run_id"], self.freeze_dir.name)
        self.assertEqual(values["holdout_splits"], dict(A.V4C_HOLDOUT_SPLIT_COUNTS))
        self.assertFalse(values["c5_in_holm"])
        self.assertEqual(values["min_estimable_tasks"], 10)

    def test_missing_blocks_fail_closed(self):
        for name in (
            "holdout_splits",
            "holdout_package",
            "c5_policy",
            "structural_identifiability",
        ):
            with self.subTest(block=name):
                prereg = copy.deepcopy(self.prereg)
                prereg.pop(name)
                with self.assertRaises(A.S1FreezeValidationError) as ctx:
                    self._verify(prereg)
                self.assertIn(A.S1_ANALYSIS_PREREG_BLOCK_MISSING, str(ctx.exception))
                self.assertIn(name, str(ctx.exception))

    def test_drift_negative_controls(self):
        run_id = self.freeze_dir.name

        def _set_holdout_package(**fields):
            def mutate(prereg):
                prereg["holdout_package"].update(fields)

            return mutate

        def _set_c5(**fields):
            def mutate(prereg):
                prereg["c5_policy"].update(fields)

            return mutate

        def _set_structural(**fields):
            def mutate(prereg):
                prereg["structural_identifiability"].update(fields)

            return mutate

        def _drop_structural(key):
            def mutate(prereg):
                prereg["structural_identifiability"].pop(key)

            return mutate

        cases = [
            ("holdout_splits_is_list", lambda p: p.__setitem__("holdout_splits", ["meta_test", "meta_test_ood"])),
            ("holdout_splits_missing_key", lambda p: p.__setitem__("holdout_splits", {"meta_test": 20})),
            ("holdout_splits_wrong_count", lambda p: p.__setitem__("holdout_splits", {"meta_test": 19, "meta_test_ood": 10})),
            ("run_id_mismatch", _set_holdout_package(run_id="p4ra-s0-4-freeze-20260101T000000Z")),
            ("run_id_bad_pattern", _set_holdout_package(run_id="not-a-run-id")),
            ("package_path_absolute", _set_holdout_package(package_path="D:/abs/" + run_id)),
            ("package_path_not_run_id", _set_holdout_package(package_path="research/concorde_metaopt/optimization_runs/other")),
            ("family_version_wrong", _set_holdout_package(family_version="p4ra-family-v3")),
            ("holdout_seed_wrong", _set_holdout_package(holdout_seed=20260101)),
            ("split_counts_wrong", _set_holdout_package(split_counts={"meta_test": 19, "meta_test_ood": 10})),
            ("task_count_wrong", _set_holdout_package(task_count=29)),
            ("frozen_sha_zero", _set_holdout_package(frozen_family_sha256="0" * 64)),
            ("c5_in_holm_true", _set_c5(c5_in_holm=True)),
            ("c5_threshold_shift", _set_c5(overlap_threshold=0.8)),
            ("c5_min_estimable_tasks", _set_c5(min_estimable_tasks=20)),
            ("c5_mode_wrong", _set_c5(mode="C5_PERMUTATION")),
            ("c5_benefit_harm_true", _set_c5(c5_benefit_harm_inference=True)),
            ("structural_post_hoc_true", _set_structural(post_hoc_task_exclusion=True)),
            ("structural_overlap_definition_wrong", _set_structural(overlap_definition="min / max")),
            ("structural_pair_status_wrong", _set_structural(pair_status_above_threshold="CLONE")),
            ("structural_threshold_shift", _set_structural(pair_overlap_threshold=0.8)),
        ]
        for name, mutate in cases:
            with self.subTest(case=name):
                with self.assertRaises(A.S1FreezeValidationError) as ctx:
                    self._verify(self._drifted(mutate))
                self.assertIn(A.S1_ANALYSIS_PREREG_BLOCK_DRIFT, str(ctx.exception))

    def test_structural_subkey_missing_is_block_missing(self):
        prereg = copy.deepcopy(self.prereg)
        prereg["structural_identifiability"].pop("exclude_from_holm")
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            self._verify(prereg)
        self.assertIn(A.S1_ANALYSIS_PREREG_BLOCK_MISSING, str(ctx.exception))
        self.assertIn("exclude_from_holm", str(ctx.exception))


class V4CMissingBlockIntegrationTests(TempDirMixin):
    """R-V4-08-02 集成：缺三键时 formal fail-closed，exploratory 显式降级且不确证。"""

    def test_missing_c5_policy_fails_formal_and_degrades_exploratory(self):
        source_dir, _identity = synthetic_v4_freeze_package()

        def _drop_c5_policy(prereg):
            prereg.pop("c5_policy")

        broken_dir = _build_v4c_confirmatory_package(source_dir, prereg_mutator=_drop_c5_policy)
        bundle = A.load_frozen_bundle(broken_dir)
        directory = self.make_temp_dir()
        _records, path = _sparse_records_and_paths(bundle, directory, tasks=2)
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            A.run_s1_analysis(
                broken_dir,
                path,
                directory / "out-formal",
                make_figures=False,
                require_complete_grid=False,
            )
        self.assertIn(A.S1_ANALYSIS_PREREG_BLOCK_MISSING, str(ctx.exception))
        self.assertFalse((directory / "out-formal" / "aggregate.json").exists())

        aggregate = A.run_s1_analysis(
            broken_dir,
            path,
            directory / "out-exploratory",
            make_figures=False,
            require_complete_grid=False,
            analysis_mode=A.ANALYSIS_MODE_EXPLORATORY,
        )
        self.assertFalse(aggregate["confirmatory_eligible"])
        self.assertEqual(
            aggregate["freeze_compliance"]["prereg_v4c_blocks"]["status"],
            "NOT_VERIFIED_EXPLORATORY",
        )
        self.assertEqual(aggregate["primary_conclusion"]["overall"], A.OVERALL_INCONCLUSIVE)


class DynamicHolmFamilyTests(unittest.TestCase):
    """R-V4-08-01：Holm 族大小动态（缺 C3/DE 臂时族大小为 3），C5 永不进族。"""

    @classmethod
    def setUpClass(cls):
        freeze_dir, _identity = synthetic_v4c_confirmatory_freeze_package()
        cls.bundle = A.load_frozen_bundle(freeze_dir)
        records = [
            record
            for record in sparse_records(
                cls.bundle, tasks=3, meta_seeds=(0, 1), opt_seeds=(0, 1)
            )
            if record["arm"] != "DE"
        ]
        cells = A.aggregate_run_records(records, cls.bundle)
        cls.collected = A.collect_hypotheses(
            cells, cls.bundle, split=A.MAIN_SPLIT, inference_ks=(3,)
        )

    def test_family_size_is_dynamic(self):
        collected = self.collected
        # sparse records 覆盖 B=64/128 两个预算 x 4 主端点 = 8 个族，缺 DE 臂后每族 3 个成员。
        self.assertEqual(collected["holm_family_size_counts"], {"3": 8})
        self.assertEqual(collected["holm_family_size_min"], 3)
        self.assertEqual(collected["holm_family_size_max"], 3)
        self.assertEqual(collected["holm_family_max_size"], 4)
        self.assertTrue(collected["holm_family_size_dynamic"])
        self.assertEqual(collected["holm_family_key_fields"], ["primary_endpoint", "budget_B", "K"])
        self.assertEqual(collected["holm_family_count"], 8)
        self.assertEqual(collected["n_hypotheses"], 24)

    def test_missing_de_arm_removes_only_c3(self):
        ids = {row["comparison_id"] for row in self.collected["rows"]}
        self.assertEqual(ids, {"C1", "C2", "C4"})
        self.assertNotIn("C5", ids)
        # ① C5 永不出现在任何 p_adj 行。
        self.assertFalse(
            any(row["comparison_id"] == "C5" and "p_adjusted" in row for row in self.collected["rows"])
        )
        self.assertEqual(self.collected["excluded_comparison_ids"], ["C5"])

    def test_holm_adjustment_matches_manual_family_of_three(self):
        families = {}
        for row in self.collected["rows"]:
            key = (str(row["endpoint"]), int(row["budget_B"]), int(row["K"]))
            families.setdefault(key, []).append(row)
        self.assertEqual(len(families), 8)
        for key, family in families.items():
            self.assertEqual(len(family), 3, msg=str(key))
            raw = [row["p_raw"] for row in family]
            expected = A.holm_adjust(raw)
            for row, adjusted in zip(family, expected):
                self.assertAlmostEqual(row["p_adjusted"], adjusted, places=15, msg=str(key))
            finite = [value for value in raw if isinstance(value, float) and math.isfinite(value)]
            if len(finite) == 3:
                ordered = sorted(finite)
                manual = [min(1.0, 3.0 * ordered[0]), min(1.0, 2.0 * ordered[1]), min(1.0, ordered[2])]
                self.assertEqual(len(manual), 3)
                self.assertAlmostEqual(min(manual[0], 1.0), min(expected), places=15)





# ---------------------------------------------------------------------------
# R-V4-02 / R-V4-04（task-230）：identifiability_report 加载与 fail-closed 负控
# ---------------------------------------------------------------------------


class StructuralIdentifiabilityReportTests(TempDirMixin):
    @classmethod
    def setUpClass(cls):
        cls.bundle = frozen_bundle()
        cls.records = structural_records(
            cls.bundle, tasks=2, budgets=(64,), ks=(3,), metas=(0,)
        )
        cls.first_key = sorted(structural_group_keys(cls.records))[0]

    def _write(self, **kwargs):
        directory = self.make_temp_dir()
        write_identifiability_report(directory, self.records, **kwargs)
        return directory

    def test_v4_report_loads_and_indexes_pair_status(self):
        directory = self._write()
        loaded = A.load_identifiability_report(directory / "identifiability_report.json")
        self.assertEqual(loaded["schema_version"], A.IDENTIFIABILITY_SCHEMA_VERSION_V4)
        self.assertEqual(loaded["threshold"], 0.90)
        self.assertEqual(len(loaded["groups"]), 2)
        self.assertEqual(
            loaded["pair_status_counts"]["FOMAML-KSHOT-BO|FOMAML-ZERO-BO"][
                A.STRUCTURAL_IDENTIFIABLE
            ],
            2,
        )
        index = A.load_structural_identifiability([directory], self.records, mode="formal")
        self.assertTrue(index.present)
        self.assertEqual(index.mode, "formal")
        self.assertEqual(index.pair_level_fields_source, A.PAIR_LEVEL_FIELDS_SOURCE_RUNNER)
        self.assertEqual(index.coverage["missing_group_count"], 0)
        self.assertEqual(index.coverage["arm_gap_count"], 0)
        self.assertEqual(index.coverage["pair_gap_count"], 0)
        self.assertEqual(index.structural_exclusion_counts(), {label: 0 for label in (
            "FOMAML-KSHOT-BO|FOMAML-ZERO-BO",
            "FOMAML-KSHOT-BO|PRETRAIN-KSHOT-BO",
            "FOMAML-ZERO-BO|PRETRAIN-KSHOT-BO",
        )})

    def test_v4_missing_pair_level_fields_rejected(self):
        directory = self._write()
        path = directory / "identifiability_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["groups"][0]["pairwise"][0].pop("pair_identifiable")
        payload["groups"][0]["pairwise"][0].pop("structural_status")
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(A.S1AnalysisError) as ctx:
            A.load_identifiability_report(path)
        self.assertIn("pair_identifiable", str(ctx.exception))

    def test_v4_missing_pair_status_counts_rejected(self):
        directory = self._write()
        path = directory / "identifiability_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.pop("pair_status_counts")
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(A.S1AnalysisError) as ctx:
            A.load_identifiability_report(path)
        self.assertIn("pair_status_counts", str(ctx.exception))

    def test_pair_status_counts_mismatch_rejected(self):
        directory = self._write()
        path = directory / "identifiability_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        label = "FOMAML-KSHOT-BO|FOMAML-ZERO-BO"
        payload["pair_status_counts"][label][A.STRUCTURAL_IDENTICAL] = 1
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(A.S1AnalysisError) as ctx:
            A.load_identifiability_report(path)
        self.assertIn("pair_status_counts", str(ctx.exception))

    def test_structural_status_inconsistent_with_overlap_rejected(self):
        directory = self._write()
        path = directory / "identifiability_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        pair = payload["groups"][0]["pairwise"][0]
        pair["structural_status"] = A.STRUCTURAL_IDENTICAL
        pair["pair_identifiable"] = False
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(A.S1AnalysisError) as ctx:
            A.load_identifiability_report(path)
        self.assertIn("不一致", str(ctx.exception))

    def test_v1_legacy_report_derives_pair_level_and_discloses(self):
        directory = self.make_temp_dir()
        write_identifiability_report(
            directory,
            self.records,
            schema_version=A.IDENTIFIABILITY_SCHEMA_VERSIONS[0],
            overlap_map={self.first_key + ("FOMAML-KSHOT-BO|FOMAML-ZERO-BO",): 0.95},
        )
        loaded = A.load_identifiability_report(directory / "identifiability_report.json")
        self.assertEqual(loaded["schema_version"], A.IDENTIFIABILITY_SCHEMA_VERSIONS[0])
        index = A.load_structural_identifiability([directory], self.records, mode="formal")
        self.assertEqual(
            index.pair_level_fields_source, A.PAIR_LEVEL_FIELDS_SOURCE_DERIVED
        )
        self.assertTrue(
            index.is_structurally_identical(
                self.first_key[0],
                self.first_key[1],
                self.first_key[2],
                self.first_key[3],
                "FOMAML-KSHOT-BO",
                "FOMAML-ZERO-BO",
            )
        )
        self.assertTrue(any("v1" in warning for warning in index.warnings))

    def test_missing_groups_formal_fail_closed(self):
        directory = self._write(drop_groups=[self.first_key])
        with self.assertRaises(A.S1AnalysisError) as ctx:
            A.load_structural_identifiability([directory], self.records, mode="formal")
        self.assertIn("组覆盖不全", str(ctx.exception))
        with self.assertRaises(A.S1AnalysisError):
            A.load_structural_identifiability([directory], self.records, mode="exploratory")
        index = A.load_structural_identifiability(
            [directory], self.records, mode="exploratory", allow_missing=True
        )
        self.assertEqual(index.coverage["missing_group_count"], 1)
        self.assertTrue(index.warnings)

    def test_missing_report_formal_fail_closed_exploratory_requires_allow(self):
        empty = self.make_temp_dir()
        with self.assertRaises(A.S1AnalysisError) as ctx:
            A.load_structural_identifiability([empty], self.records, mode="formal")
        self.assertIn("identifiability_report", str(ctx.exception))
        with self.assertRaises(A.S1AnalysisError):
            A.load_structural_identifiability([empty], self.records, mode="exploratory")
        index = A.load_structural_identifiability(
            [empty], self.records, mode="exploratory", allow_missing=True
        )
        self.assertFalse(index.present)
        self.assertIn(
            index.pair_level_fields_source, (A.PAIR_LEVEL_FIELDS_SOURCE_NONE,)
        )
        self.assertTrue(index.warnings)

    def test_formal_disallows_allow_missing_flag(self):
        directory = self._write()
        with self.assertRaises(A.S1AnalysisError) as ctx:
            A.load_structural_identifiability(
                [directory], self.records, mode="formal", allow_missing=True
            )
        self.assertIn("allow_missing", str(ctx.exception))

    def test_unknown_schema_rejected(self):
        directory = self._write()
        path = directory / "identifiability_report.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["schema_version"] = "p4ra-s1-identifiability-999"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(A.S1AnalysisError) as ctx:
            A.load_identifiability_report(path)
        self.assertIn("schema_version", str(ctx.exception))


# ---------------------------------------------------------------------------
# R-V4-02：pair-level STRUCTURALLY_IDENTICAL 行级排除（不剔除任务）与 C5 描述层
# ---------------------------------------------------------------------------


class StructuralExclusionTests(TempDirMixin):
    @classmethod
    def setUpClass(cls):
        cls.bundle = frozen_bundle()
        cls.task_ids = list(cls.bundle.task_ids_for(A.MAIN_SPLIT))
        cls.records = structural_records(
            cls.bundle, tasks=12, budgets=(64, 128), ks=(3,), metas=(0, 1, 2)
        )
        cls.te001 = cls.task_ids[1]
        cls.exclusion_pairs = []
        cls.overlap = {}
        for meta_seed in (1, 2):
            key = (cls.te001, 64, 3, meta_seed)
            cls.exclusion_pairs.append(key)
            cls.overlap[key + ("FOMAML-KSHOT-BO|FOMAML-ZERO-BO",)] = 1.0
        cls.directory = Path(tempfile.mkdtemp(prefix="s1-structural-"))
        write_identifiability_report(
            cls.directory,
            cls.records,
            overlap_map=cls.overlap,
            # 复现 A5 证据的 TE-001 型：组级 ranking 仍 IDENTIFIABLE（旧组级策略漏报）
            ranking_override={key: "IDENTIFIABLE" for key in cls.exclusion_pairs},
        )
        cls.index = A.load_structural_identifiability(
            [cls.directory], cls.records, mode="formal"
        )
        cls.cells = A.aggregate_run_records(cls.records, cls.bundle)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.directory, ignore_errors=True)

    def test_pair_level_identical_detected_despite_identifiable_group_ranking(self):
        for key in self.exclusion_pairs:
            self.assertTrue(
                self.index.is_structurally_identical(
                    key[0], key[1], key[2], key[3], "FOMAML-KSHOT-BO", "FOMAML-ZERO-BO"
                ),
                msg=str(key),
            )
        self.assertEqual(
            self.index.structural_exclusion_counts()["FOMAML-KSHOT-BO|FOMAML-ZERO-BO"], 2
        )

    def test_build_paired_endpoint_excludes_identical_meta_groups_only(self):
        paired = A.build_paired_endpoint(
            self.cells,
            self.bundle,
            comparison_id="C5",
            split=A.MAIN_SPLIT,
            budget_B=64,
            K=3,
            endpoint="best_feasible_value",
            structural_index=self.index,
        )
        self.assertIsNotNone(paired)
        self.assertEqual(paired.structural_exclusion_count, 2)
        self.assertEqual(paired.n_pairs, 12)
        # 本用例 records 只覆盖 12 个 task，其余 8 个任务无数据（非排除导致）。
        self.assertEqual(paired.n_tasks_unpaired, 8)
        # 任务保留（不是事后剔除）：n_tasks 仍为该 split 全部 20 个任务。
        self.assertEqual(paired.n_tasks, len(self.task_ids))
        # C1 臂对未被误排除。
        c1_paired = A.build_paired_endpoint(
            self.cells,
            self.bundle,
            comparison_id="C1",
            split=A.MAIN_SPLIT,
            budget_B=64,
            K=3,
            endpoint="best_feasible_value",
            structural_index=self.index,
        )
        self.assertEqual(c1_paired.structural_exclusion_count, 0)

    def test_c5_not_in_holm_family(self):
        collected = A.collect_hypotheses(
            self.cells,
            self.bundle,
            split=A.MAIN_SPLIT,
            inference_ks=(3,),
            structural_index=self.index,
        )
        ids = {row["comparison_id"] for row in collected["rows"]}
        self.assertEqual(ids, {"C1", "C2", "C3", "C4"})
        self.assertEqual(collected["holm_family_max_size"], 4)
        self.assertEqual(collected["holm_family_size_counts"], {"4": 8})
        self.assertEqual(collected["holm_family_size_dynamic"], True)
        self.assertEqual(collected["excluded_comparison_ids"], ["C5"])
        self.assertEqual(collected["n_hypotheses"], 4 * 2 * 4)
        for row in collected["rows"]:
            self.assertNotEqual(row["comparison_id"], "C5")

    def test_c5_descriptive_only_when_estimable_tasks_at_least_ten(self):
        summary = A.c5_structural_summary(self.cells, self.bundle, self.index)
        self.assertEqual(summary["status"], A.C5_DESCRIPTIVE_ONLY)
        self.assertEqual(summary["estimable_tasks"], 12)
        self.assertEqual(summary["total_groups"], 12 * 3 * 2)
        self.assertEqual(summary["structurally_identical_groups"], 2)
        self.assertFalse(summary["in_holm"])
        self.assertIsNone(summary["benefit_harm_decision"])
        for row in summary["descriptive_rows"]:
            self.assertNotIn("p_raw", row)
            self.assertNotIn("p_adjusted", row)
            self.assertFalse(row["inference"])

    def test_c5_not_estimable_when_estimable_tasks_below_ten(self):
        small_records = structural_records(
            self.bundle, tasks=4, budgets=(64,), ks=(3,), metas=(0, 1, 2)
        )
        directory = self.make_temp_dir()
        write_identifiability_report(directory, small_records)
        index = A.load_structural_identifiability([directory], small_records, mode="formal")
        cells = A.aggregate_run_records(small_records, self.bundle)
        summary = A.c5_structural_summary(cells, self.bundle, index)
        self.assertEqual(summary["status"], A.C5_NOT_ESTIMABLE)
        self.assertEqual(summary["estimable_tasks"], 4)
        self.assertIn("NOT_ESTIMABLE", summary["reason"])

    def test_exclusion_counts_by_comparison(self):
        counts = A.comparison_structural_exclusion_counts(self.index)
        self.assertEqual(counts["by_comparison"]["C5"], 2)
        self.assertEqual(counts["by_comparison"]["C1"], 0)
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["by_pair"]["FOMAML-KSHOT-BO|FOMAML-ZERO-BO"], 2)

    def test_structural_rows_are_exportable(self):
        summary = A.c5_structural_summary(self.cells, self.bundle, self.index)
        rows = A.structural_identifiability_rows(self.index, self.bundle, summary)
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(set(row), set(A.STRUCTURAL_IDENTIFIABILITY_COLUMNS))
        row_types = {row["row_type"] for row in rows}
        self.assertEqual(row_types, {"pair_group", "exclusion_summary", "c5_summary"})
        pair_rows = [row for row in rows if row["row_type"] == "pair_group"]
        self.assertEqual(len(pair_rows), len(self.index.groups) * 3)
        excluded = [
            row
            for row in pair_rows
            if row["structural_status"] == A.STRUCTURAL_IDENTICAL
        ]
        self.assertEqual(len(excluded), 2)
        for row in excluded:
            self.assertFalse(row["used_in_inference"])
        c5_rows = [row for row in rows if row["row_type"] == "c5_summary"]
        # labels=B*meta_seed 层：budgets(2) x inference_ks(3) = 6 行。
        self.assertEqual(
            len(c5_rows), len(A.MAIN_POPULATION_BUDGETS) * len(A.INFERENCE_KS)
        )
        self.assertEqual(c5_rows[0]["status"], A.C5_DESCRIPTIVE_ONLY)


# ---------------------------------------------------------------------------
# R-V4-02/R-V4-04：端到端 aggregate/CSV/figure_status 的 C5 与排除计数披露
# ---------------------------------------------------------------------------


class StructuralEndToEndDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aggregate = full_e2e_run()["aggregate"]

    def test_c5_reported_as_descriptive_only(self):
        c5 = self.aggregate["c5_structural_identifiability"]
        self.assertEqual(c5["status"], A.C5_DESCRIPTIVE_ONLY)
        self.assertEqual(c5["estimable_tasks"], 20)
        self.assertFalse(c5["in_holm"])
        self.assertIsNone(c5["benefit_harm_decision"])
        rows = [
            row
            for row in self.aggregate["endpoint_rows"]
            if row.get("row_type") == "comparison"
        ]
        self.assertNotIn("C5", {row["comparison_id"] for row in rows})

    def test_structural_exclusion_counts_exported(self):
        counts = self.aggregate["structural_exclusion_counts"]
        self.assertEqual(counts["total"], 0)
        self.assertEqual(set(counts["by_comparison"]), {"C1", "C2", "C3", "C4", "C5"})
        self.assertEqual(
            self.aggregate["excluded_pair_counts"],
            {
                "FOMAML-KSHOT-BO|FOMAML-ZERO-BO": 0,
                "FOMAML-KSHOT-BO|PRETRAIN-KSHOT-BO": 0,
                "FOMAML-ZERO-BO|PRETRAIN-KSHOT-BO": 0,
            },
        )
        index_payload = self.aggregate["structural_identifiability"]
        self.assertTrue(index_payload["present"])
        self.assertEqual(index_payload["pair_level_fields_source"], A.PAIR_LEVEL_FIELDS_SOURCE_RUNNER)
        self.assertEqual(index_payload["coverage"]["missing_group_count"], 0)
        self.assertEqual(index_payload["schema_version"], A.S1_STRUCTURAL_SCHEMA_VERSION)

    def test_structural_csv_written_with_contract_columns(self):
        out_dir = full_e2e_run()["out_dir"]
        path = out_dir / "s1_structural_identifiability.csv"
        self.assertTrue(path.is_file())
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(tuple(reader.fieldnames), A.STRUCTURAL_IDENTIFIABILITY_COLUMNS)
            rows = list(reader)
        self.assertTrue(rows)
        self.assertIn("c5_summary", {row["row_type"] for row in rows})

    def test_figure_status_discloses_c5_without_fabricating_figure(self):
        status = self.aggregate["figure_status"]
        self.assertEqual(
            status["c5_structural_identifiability"]["status"], A.C5_DESCRIPTIVE_ONLY
        )
        self.assertEqual(len(status["figures"]), 7)
        self.assertNotIn("c5", " ".join(status["figures"]))
        self.assertTrue(any("C5" in note for note in status["notes"]))
# ---------------------------------------------------------------------------
# task-241（A2-V4-B01）：S0-3 v4 冻结包 freeze_summary schema 3 兼容与严格校验
# ---------------------------------------------------------------------------

FROZEN_V4_DIR = (
    REPO_ROOT
    / "research"
    / "concorde_metaopt"
    / "optimization_runs"
    / "p4ra-s0-3-freeze-20261105T155925Z"
)


def _rewrite_freeze_summary_and_sums(package_dir, mutate):
    """改写 freeze_summary.json 并只重算 SHA256SUMS.txt 中该行的摘要。"""
    summary_path = package_dir / "freeze_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    mutate(summary)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    sums_path = package_dir / "SHA256SUMS.txt"
    new_sha = hashlib.sha256(summary_path.read_bytes()).hexdigest()
    rewritten = []
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition(" *")
        if separator and name.strip() == "freeze_summary.json":
            line = new_sha + " *freeze_summary.json"
        elif not separator:
            raise AssertionError("Unexpected SHA256SUMS line: " + line)
        rewritten.append(line)
    sums_path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


class FreezeSummarySchemaCompatTests(TempDirMixin):
    """task-241 / A2-V4-B01：schema 1/2/3 正向兼容，未知版本与关键字段漂移 fail-closed。"""

    def _copy_package(self, source):
        target = self.make_temp_dir() / source.name
        shutil.copytree(source, target)
        return target

    def _copy_and_load(self, source, mutate):
        package = self._copy_package(source)
        _rewrite_freeze_summary_and_sums(package, mutate)
        return A.load_frozen_bundle(package)

    def _assert_rejected(self, source, mutate, needle):
        with self.assertRaises(A.S1FreezeValidationError) as ctx:
            self._copy_and_load(source, mutate)
        self.assertIn(needle, str(ctx.exception))

    # ---- 正向：schema 3（真实 S0-3 v4 包） ----
    def test_v4_package_schema_3_loads(self):
        summary = json.loads(
            (FROZEN_V4_DIR / "freeze_summary.json").read_text(encoding="utf-8")
        )
        self.assertEqual(summary["schema_version"], "p4ra-freeze-summary-3")
        bundle = A.load_frozen_bundle(FROZEN_V4_DIR)
        self.assertEqual(bundle.family_version, "p4ra-family-v4")
        self.assertEqual(
            bundle.identity.family_fingerprint,
            "a1f9462c35ea641d0559485354c63b47eec2e6fb4696e86f94efa1f3d19daf2e",
        )
        self.assertEqual(
            bundle.identity.prereg_digest,
            "aa806767445421335874322321145af4b5ed5bc52826dc732a05c0f8f3feb948",
        )
        self.assertEqual(bundle.identity.radius_base, 0.64)
        self.assertEqual(len(bundle.task_ids_for("meta_test")), 20)

    # ---- 正向：schema 2（v3 legacy 包） ----
    def test_v3_legacy_package_schema_2_still_loads(self):
        summary = json.loads((FROZEN_DIR / "freeze_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["schema_version"], "p4ra-freeze-summary-2")
        bundle = A.load_frozen_bundle(FROZEN_DIR)
        self.assertEqual(bundle.family_version, "p4ra-family-v3")
        self.assertEqual(bundle.identity.radius_base, 0.64)

    # ---- 正向：schema 1（历史兼容） ----
    def test_schema_1_variant_accepted(self):
        package = self._copy_package(FROZEN_DIR)
        _rewrite_freeze_summary_and_sums(
            package, lambda summary: summary.__setitem__("schema_version", "p4ra-freeze-summary-1")
        )
        bundle = A.load_frozen_bundle(package)
        self.assertEqual(bundle.family_version, "p4ra-family-v3")

    # ---- 负向：未知/缺失 schema ----
    def test_schema_4_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary.__setitem__("schema_version", "p4ra-freeze-summary-4"),
            "schema 不符",
        )

    def test_missing_schema_version_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR, lambda summary: summary.pop("schema_version"), "schema 不符"
        )

    # ---- 负向：schema 3 顶层字段集合 ----
    def test_unknown_top_level_field_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary.__setitem__("unexpected_field", 1),
            "未登记字段",
        )

    def test_missing_holdout_seed_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR, lambda summary: summary.pop("holdout_seed"), "缺少字段"
        )

    # ---- 负向：holdout / 校准 / 家族身份漂移 ----
    def test_tampered_holdout_seed_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary.__setitem__("holdout_seed", 20261107),
            "holdout_seed",
        )

    def test_tampered_holdout_splits_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary.__setitem__("holdout_splits", ["meta_test"]),
            "holdout_splits",
        )

    def test_tampered_holdout_task_count_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary.__setitem__("holdout_task_count", 29),
            "holdout_task_count",
        )

    def test_tampered_calibration_status_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary.__setitem__("calibration_status", "PENDING_A2_CALIBRATION"),
            "calibration_status",
        )

    def test_tampered_family_version_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary.__setitem__("family_version", "p4ra-family-v3"),
            "family_version",
        )

    def test_tampered_code_sha_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary.__setitem__("code_sha", "0" * 64),
            "code_sha",
        )

    # ---- 负向：artifacts / digest_manifest ----
    def test_missing_artifact_entry_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary["artifacts"].pop("tasks.json"),
            "artifacts",
        )

    def test_tampered_artifact_stored_sha256_rejected(self):
        def mutate(summary):
            summary["artifacts"]["frozen_family.json"]["stored_sha256"] = "0" * 64

        self._assert_rejected(FROZEN_V4_DIR, mutate, "stored_sha256")

    def test_tampered_digest_manifest_block_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary["digest_manifest"].__setitem__("bytes", 1),
            "digest_manifest.bytes",
        )

    # ---- 负向：orchestration ----
    def test_tampered_physical_call_count_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary["orchestration"].__setitem__("physical_call_count", 1),
            "physical_call_count",
        )

    def test_missing_orchestration_field_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary["orchestration"].pop("legacy"),
            "orchestration 字段集合不符",
        )

    def test_tampered_task_id_intersection_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary["orchestration"]["task_id_intersection"].__setitem__(
                "status", "FAIL"
            ),
            "task_id_intersection.status",
        )

    def test_tampered_legacy_counts_rejected(self):
        self._assert_rejected(
            FROZEN_V4_DIR,
            lambda summary: summary["orchestration"]["legacy"].__setitem__("task_id_count", 279),
            "legacy.task_id_count",
        )


if __name__ == "__main__":
    unittest.main()
