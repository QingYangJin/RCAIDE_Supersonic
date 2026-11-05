"""S1 只读分析/出图合同测试（unittest）。

覆盖执行计划 §9 验收与统计计划 v1.1：
- 冻结包 fail-closed（三方/五方回显、端点 9 键、禁用别名、缺列、校验和篡改）；
- run_records 强校验负控（缺必填/未知字段/别名/record_digest/run_id/预算/物理隔离/CLONE）；
- 聚合（opt seed -> (task, meta_seed) 均值、meta seed 等权 -> task）、null 不插补；
- 统计函数（Wilcoxon 精确/并列近似、Holm、bootstrap、效应量）与判定规则，不产生假数据；
- 端到端 21,000 条记录 -> 6 数据产物 + 7 张规范图、无绝对路径、physical=0；
- CLI 成功/失败返回码。

全部测试纯离线：不 import 也不启动任何真实 Mission/SU2/VSPAERO/OpenVSP/RCAIDE 求解器。
"""

import contextlib
import copy
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

    def test_frozen_constants_match_a5_release_values(self):
        self.assertEqual(
            A.ANALYSIS_PLAN_DIGEST,
            "37eee53c9018fce34e414fa553ad3986a2d1be87d10409bc28e4f697b63588df",
        )
        self.assertEqual(
            A.FAMILY_FINGERPRINT,
            "e56e6921be6b94e6611a24618a6e331cd7e4417597926d089d71b00da8c1c0c3",
        )
        self.assertEqual(
            A.SPLIT_HASH,
            "cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae",
        )
        self.assertEqual(
            A.PREREG_DIGEST,
            "6981f503fd6ea5a9fbe5de2d1825ae8993eb17e9fda5d2ff158e9248d88fd3df",
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
        )
        self.assertEqual(decision["decision"], A.DECISION_BENEFIT)

    def test_decide_endpoint_harm(self):
        decision = A.decide_endpoint(
            self._paired(), test={"n_effective": 20}, p_adjusted=0.001, improvement=-0.2
        )
        self.assertEqual(decision["decision"], A.DECISION_HARM)

    def test_decide_endpoint_no_evidence_below_threshold(self):
        decision = A.decide_endpoint(
            self._paired(), test={"n_effective": 20}, p_adjusted=0.001, improvement=0.0
        )
        self.assertEqual(decision["decision"], A.DECISION_NONE)

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
        bundle = frozen_bundle()
        directory = Path(tempfile.mkdtemp(prefix="s1-e2e-"))
        records = full_meta_test_records(bundle)
        records_path = write_record_files(directory, records)
        meta_log = directory / "meta_training_log.json"
        meta_log.write_text(
            json.dumps({"history": [{"epoch": index + 1, "loss": 1.0 / (index + 1)} for index in range(8)]}),
            encoding="utf-8",
        )
        out_dir = directory / "out"
        aggregate = A.run_s1_analysis(
            FROZEN_DIR, records_path, out_dir, make_figures=True, meta_training_log=meta_log
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
        bundle = frozen_bundle()
        directory = self.make_temp_dir()
        path = write_record_files(directory, sparse_records(bundle))
        out_dir = directory / "out"
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
                    str(out_dir),
                    "--allow-incomplete-grid",
                    "--no-figures",
                ]
            )
        self.assertEqual(code, 0, msg=stderr.getvalue())
        self.assertNotIn("S1_ANALYSIS_FAILED", stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["n_records"], len(sparse_records(bundle)))
        self.assertTrue((out_dir / "aggregate.json").is_file())

    def test_cli_record_failure_returns_two(self):
        bundle = frozen_bundle()
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


if __name__ == "__main__":
    unittest.main()
