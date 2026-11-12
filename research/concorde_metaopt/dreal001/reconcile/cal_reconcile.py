"""P2A-CAL 执行后独立对账（A2，只读，physical_call_count=0）.

本模块只读取 run 目录中的 plan/approval/ledger/evaluations/batch_summary/
data_manifest/metrics/case_result，做交叉核对并输出 JSON + 中文 Markdown。
它不导入 A1 执行器、不解析 polar、不启动 solver、不修改 run 目录。

使用:
  python -m research.concorde_metaopt.dreal001.reconcile.cal_reconcile \
      --run-dir <.../runs/DREAL001-P2CAL-20261111-02> [--json OUT] [--md OUT]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA = "dreal001.cal_reconcile.v1"
TOOL_VERSION = "a2-cal-reconcile-2026-11-11"
DEFAULT_EXPECTED_APPROVAL_SHA = "7498aa40ce1dc170597b83f5363b7fca3162d10feaea2e9f1d1efc02b56eb3da"
DEFAULT_EXPECTED_EXECUTOR_SHA = "6fbb03cfe86810a57de19d7f4c13ceca3dc28bec812e32c76851611b53c79dec"
DEFAULT_EXPECTED_STARTS = 12
DEFAULT_EXPECTED_INTERNAL = 84
EXPECTED_INTERNAL_PER_START = 7
EXPECTED_ALPHA_COUNT = 7
STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_NV = "NV"
STATUS_OK = "RECONCILED_OK"
STATUS_FINDINGS = "RECONCILED_WITH_FINDINGS"
STATUS_PRE = "PRE_EXECUTION_NOT_RUN"
STATUS_BLOCKED = "BLOCKED"
PHYSICAL = 0


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_bytes().decode("utf-8"))


def read_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    rows: List[Dict[str, Any]] = []
    bad: List[str] = []
    if not path.is_file():
        return rows, bad
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception as exc:  # noqa: BLE001 - report malformed line, never crash
            bad.append("line %d: %r" % (index, exc))
    return rows, bad


def repo_root_for(path: Path) -> Optional[Path]:
    for parent in [path] + list(path.parents):
        if (parent / ".git").exists():
            return parent
    return None


def resolve_executor(plan: Dict[str, Any], run_dir: Path) -> Optional[Path]:
    block = plan.get("executor") or {}
    rel = block.get("path") or plan.get("executor_path")
    if not rel:
        return None
    candidate = Path(str(rel))
    if candidate.is_absolute():
        return candidate
    root = repo_root_for(run_dir)
    if root is not None:
        hit = root / candidate
        if hit.is_file():
            return hit
    return candidate if candidate.is_file() else None


class Checks:
    def __init__(self) -> None:
        self.items: List[Dict[str, Any]] = []

    def add(self, check_id: str, title: str, status: str,
            expected: Any = None, actual: Any = None, detail: str = "") -> None:
        assert status in (STATUS_PASS, STATUS_FAIL, STATUS_NV), status
        self.items.append({"id": check_id, "title": title, "status": status,
                           "expected": expected, "actual": actual, "detail": detail})

    def fail(self, check_id: str, title: str, expected: Any = None,
             actual: Any = None, detail: str = "") -> None:
        self.add(check_id, title, STATUS_FAIL, expected, actual, detail)

    def nv(self, check_id: str, title: str, expected: Any = None,
           actual: Any = None, detail: str = "") -> None:
        self.add(check_id, title, STATUS_NV, expected, actual, detail)

    def passed(self, check_id: str, title: str, expected: Any = None,
               actual: Any = None, detail: str = "") -> None:
        self.add(check_id, title, STATUS_PASS, expected, actual, detail)

    def by_id(self, check_id: str) -> Optional[Dict[str, Any]]:
        for item in self.items:
            if item["id"] == check_id:
                return item
        return None


def _case_ids(plan: Dict[str, Any]) -> List[str]:
    return [str(case.get("case_id")) for case in (plan.get("case_matrix") or [])]


def reconcile(run_dir: Path,
              expected_approval_sha: str = DEFAULT_EXPECTED_APPROVAL_SHA,
              expected_executor_sha: str = DEFAULT_EXPECTED_EXECUTOR_SHA,
              expected_starts: int = DEFAULT_EXPECTED_STARTS,
              expected_internal: int = DEFAULT_EXPECTED_INTERNAL) -> Dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    checks = Checks()
    notes: List[str] = []
    plan_path = run_dir / "plan.json"
    if not run_dir.is_dir() or not plan_path.is_file():
        checks.fail("C01", "plan.json 可读", "plan exists", "missing",
                    "run_dir 或 plan.json 不存在，无法对账")
        return _report(run_dir, STATUS_BLOCKED, checks, notes,
                       expected_approval_sha, expected_executor_sha,
                       expected_starts, expected_internal, {}, {})

    plan = load_json(plan_path)
    plan_sha = sha256_file(plan_path)
    case_ids = _case_ids(plan)
    case_meta = {str(case.get("case_id")): case for case in (plan.get("case_matrix") or [])}
    designs = plan.get("designs") or []
    plan_starts = sum(int(case.get("starts") or 1) for case in case_meta.values())
    plan_internal = sum(int(case.get("expected_internal_cases") or 0)
                        for case in case_meta.values())

    if len(case_ids) == expected_starts and len(set(case_ids)) == len(case_ids):
        checks.passed("C01", "plan case_matrix 12 个唯一 case_id",
                      expected_starts, len(case_ids), "plan_sha256=%s" % plan_sha)
    else:
        checks.fail("C01", "plan case_matrix 12 个唯一 case_id",
                    expected_starts, {"count": len(case_ids),
                                      "unique": len(set(case_ids))},
                    "case_id 数量或唯一性不符合 CAL 合同")
    if plan_starts != expected_starts or plan_internal != expected_internal:
        checks.fail("C06", "plan budget 12 starts / 84 internal / refine 0",
                    {"starts": expected_starts, "internal": expected_internal, "refine": 0},
                    {"starts": plan_starts, "internal": plan_internal,
                     "refine": (plan.get("budget") or {}).get("max_refine_starts")},
                    "plan 预算与 CAL 合同不一致")
    else:
        checks.passed("C06", "plan budget 12 starts / 84 internal / refine 0",
                      {"starts": expected_starts, "internal": expected_internal, "refine": 0},
                      {"starts": plan_starts, "internal": plan_internal, "refine": 0}, "")

    executor = resolve_executor(plan, run_dir)
    planned_executor_sha = str((plan.get("executor") or {}).get("blob_sha256") or "")
    if executor is None or not executor.is_file():
        checks.fail("C05", "executor 文件存在且 blob 绑定一致",
                    planned_executor_sha, "missing",
                    "plan.executor.path=%r 无法解析到文件"
                    % ((plan.get("executor") or {}).get("path")))
        executor_sha = None
    else:
        executor_sha = sha256_file(executor)
        if (executor_sha == expected_executor_sha
                and (not planned_executor_sha or planned_executor_sha == executor_sha)):
            checks.passed("C05", "executor 文件存在且 blob 绑定一致",
                          expected_executor_sha, executor_sha, "path=%s" % executor)
        else:
            checks.fail("C05", "executor 文件存在且 blob 绑定一致",
                        {"expected": expected_executor_sha,
                         "plan.executor.blob_sha256": planned_executor_sha},
                        {"actual": executor_sha, "path": str(executor)},
                        "执行器字节与批准 blob 不一致（可能执行期改码）")

    approval_path = run_dir / "approval.json"
    ledger_path = run_dir / "solver_attempts.jsonl"
    summary_path = run_dir / "batch_summary.json"
    approval: Optional[Dict[str, Any]] = None
    approval_sha: Optional[str] = None
    if approval_path.is_file():
        raw_approval = approval_path.read_bytes()
        approval_sha = sha256_bytes(raw_approval)
        try:
            approval = json.loads(raw_approval.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            checks.fail("C02", "approval.json 可解析且 approved=true",
                        "approved=true", "unparsable", repr(exc))
    # 已签 approval 但尚未产生任何执行产物（台账/汇总/evaluations/case 结果）
    # 仍属执行前状态；此时只做结构与绑定预检，不把缺产物误报为 FAIL。
    pre_execution = (not ledger_path.is_file()
                     and not summary_path.is_file()
                     and not (run_dir / "evaluations.jsonl").is_file()
                     and not (run_dir / "cases").is_dir())

    if approval is None:
        if pre_execution:
            checks.nv("C02", "approval.json 存在且 approved=true", True, "missing",
                      "执行前状态：尚未签 approval（零物理）")
            checks.nv("C03", "approval.json SHA256 等于 Lead 批准值",
                      expected_approval_sha, "missing", "执行前状态")
            checks.nv("C04", "approval.plan_sha256 == plan 字节 SHA256",
                      plan_sha, "missing", "执行前状态")
        else:
            checks.fail("C02", "approval.json 存在且 approved=true", True, "missing",
                        "存在执行产物但无 approval.json：不可解释")
            checks.fail("C03", "approval.json SHA256 等于 Lead 批准值",
                        expected_approval_sha, "missing", "")
            checks.fail("C04", "approval.plan_sha256 == plan 字节 SHA256",
                        plan_sha, "missing", "")
    else:
        if approval.get("approved") is True:
            checks.passed("C02", "approval.json 存在且 approved=true", True, True,
                          "approved_by=%s at=%s"
                          % (approval.get("approved_by"), approval.get("approved_at_utc")))
        else:
            checks.fail("C02", "approval.json 存在且 approved=true",
                        True, approval.get("approved"), "approval 未签")
        if approval_sha == expected_approval_sha:
            checks.passed("C03", "approval.json SHA256 等于 Lead 批准值",
                          expected_approval_sha, approval_sha, "")
        else:
            checks.fail("C03", "approval.json SHA256 等于 Lead 批准值",
                        expected_approval_sha, approval_sha,
                        "approval 字节与 Lead 签署值不一致")
        if approval.get("plan_sha256") == plan_sha:
            checks.passed("C04", "approval.plan_sha256 == plan 字节 SHA256",
                          plan_sha, plan_sha, "")
        else:
            checks.fail("C04", "approval.plan_sha256 == plan 字节 SHA256",
                        plan_sha, approval.get("plan_sha256"), "approval 绑定了另一份 plan")

    starts: List[Dict[str, Any]] = []
    ends: List[Dict[str, Any]] = []
    ledger_bad: List[str] = []
    if ledger_path.is_file():
        rows, ledger_bad = read_jsonl(ledger_path)
        starts = [row for row in rows if str(row.get("event")) == "start"]
        ends = [row for row in rows if str(row.get("event")) == "end"]
        if ledger_bad:
            checks.fail("C07", "solver_attempts.jsonl 逐行可解析",
                        "0 malformed", len(ledger_bad), "; ".join(ledger_bad[:3]))
        else:
            checks.passed("C07", "solver_attempts.jsonl 逐行可解析",
                          "0 malformed", 0, "rows=%d starts=%d ends=%d"
                          % (len(rows), len(starts), len(ends)))
    elif pre_execution:
        checks.nv("C07", "solver_attempts.jsonl 逐行可解析", "ledger", "missing",
                  "执行前状态：无台账（零物理）")
    else:
        checks.fail("C07", "solver_attempts.jsonl 逐行可解析", "ledger", "missing",
                    "执行产物缺少 append-only 台账")

    start_ids: Dict[str, Dict[str, Any]] = {}
    end_ids: Dict[str, Dict[str, Any]] = {}
    duplicate_starts: List[str] = []
    duplicate_ends: List[str] = []
    for row in starts:
        attempt = str(row.get("attempt_id") or "")
        if not attempt:
            checks.fail("C08", "start/end 按 attempt_id 一一配对", "attempt_id",
                        "start row without attempt_id", "")
            continue
        if attempt in start_ids:
            duplicate_starts.append(attempt)
        start_ids[attempt] = row
    for row in ends:
        attempt = str(row.get("attempt_id") or "")
        if attempt in end_ids:
            duplicate_ends.append(attempt)
        end_ids[attempt] = row
    missing_end = sorted(set(start_ids) - set(end_ids))
    missing_start = sorted(set(end_ids) - set(start_ids))
    if (missing_end or missing_start or duplicate_starts or duplicate_ends) and not pre_execution:
        checks.fail("C08", "start/end 按 attempt_id 一一配对", "paired 1:1",
                    {"missing_end": missing_end, "missing_start": missing_start,
                     "duplicate_starts": duplicate_starts, "duplicate_ends": duplicate_ends},
                    "存在未配对/重复台账行，物理记账不闭合")
    elif pre_execution and not start_ids and not end_ids:
        checks.nv("C08", "start/end 按 attempt_id 一一配对", "paired 1:1",
                  "no starts", "执行前状态")
    else:
        checks.passed("C08", "start/end 按 attempt_id 一一配对", "paired 1:1",
                      {"starts": len(start_ids), "ends": len(end_ids)}, "")

    physical_starts = [row for row in starts
                       if int(row.get("physical_solver_starts") or 0) == 1]
    if len(physical_starts) != len(starts) and not pre_execution:
        checks.fail("C08b", "每条 start 行 physical_solver_starts=1",
                    len(starts), {"all": len(starts), "physical": len(physical_starts)},
                    "存在未被计费的 start 行")

    bad_attempts: List[Dict[str, Any]] = []
    case_start_counts: Dict[str, int] = {}
    for row in starts:
        attempt = str(row.get("attempt_id") or "")
        case_id = str(row.get("case_id") or "")
        case_start_counts[case_id] = case_start_counts.get(case_id, 0) + 1
        expected_attempt = case_id + "-a01"
        if attempt != expected_attempt or case_id not in case_meta:
            bad_attempts.append({"attempt_id": attempt, "case_id": case_id,
                                 "expected_attempt_id": expected_attempt})
    retried_cases = {case: count for case, count in case_start_counts.items() if count > 1}
    if (bad_attempts or retried_cases) and not pre_execution:
        checks.fail("C09", "attempt_id 规范：每 case 仅 -a01、无 a02/重试",
                    {"pattern": "<case_id>-a01", "one_start_per_case": True},
                    {"bad": bad_attempts, "retried_cases": retried_cases},
                    "attempt_id 或重试计数不符合 CAL 合同")
    elif pre_execution and not starts:
        checks.nv("C09", "attempt_id 规范：每 case 仅 -a01、无 a02/重试",
                  "<case_id>-a01", "no starts", "执行前状态")
    else:
        checks.passed("C09", "attempt_id 规范：每 case 仅 -a01、无 a02/重试",
                      "<case_id>-a01", sorted(start_ids), "")

    summary_raw: Dict[str, Any] = {}
    if summary_path.is_file():
        try:
            summary_raw = load_json(summary_path)
        except Exception as exc:  # noqa: BLE001
            checks.fail("C13", "batch_summary.json 可解析", "json", "unparsable", repr(exc))
    summary_status = str(summary_raw.get("status") or "")
    stop_hits = summary_raw.get("stop_hits") or []
    retry_text = json.dumps(stop_hits, ensure_ascii=False).lower()
    if "retry" in retry_text and not pre_execution:
        checks.fail("C18", "执行记录中无自动重试（retry/a02）",
                    "no retry", retry_text[:200], "stop_report/summary 出现 retry 字样")
    elif not pre_execution:
        checks.passed("C18", "执行记录中无自动重试（retry/a02）",
                      "no retry", "no retry text", "attempt_id 与 stop_hits 均无重试")

    actual_starts = len(physical_starts)
    approval_max = int(approval.get("max_starts") or 0) if approval else 0
    if pre_execution:
        checks.nv("C10", "物理 start 数 = 12（或 fail-closed 提前停）",
                  expected_starts, "not run", "执行前状态")
    elif actual_starts > expected_starts or (approval_max and actual_starts > approval_max):
        checks.fail("C10", "物理 start 数 = 12（或 fail-closed 提前停）",
                    {"planned": expected_starts, "approval_max": approval_max},
                    actual_starts, "start 数超过胶囊/批准上限")
    elif actual_starts == expected_starts:
        checks.passed("C10", "物理 start 数 = 12（或 fail-closed 提前停）",
                      expected_starts, actual_starts, "12/12 全跑")
    elif summary_status == "COMPLETED":
        checks.fail("C10", "物理 start 数 = 12（或 fail-closed 提前停）",
                    expected_starts, actual_starts, "batch 声称 COMPLETED 但 start 数不足")
    else:
        checks.nv("C10", "物理 start 数 = 12（或 fail-closed 提前停）",
                  expected_starts, actual_starts,
                  "fail-closed 提前停（status=%s, stop_hits=%s）"
                  % (summary_status or "UNKNOWN", [h.get("condition") for h in stop_hits]))

    internal_values: List[int] = []
    bad_internal: List[str] = []
    for row in ends:
        value = row.get("internal_solver_cases")
        if value is None:
            bad_internal.append(str(row.get("attempt_id")))
        else:
            internal_values.append(int(value))
    internal_total = sum(internal_values)
    if pre_execution:
        checks.nv("C11", "internal_solver_cases 总数与 84/实际一致",
                  expected_internal, "not run", "执行前状态")
    elif bad_internal:
        checks.fail("C11", "internal_solver_cases 总数与 84/实际一致",
                    "each end has internal", {"missing": bad_internal}, "")
    elif internal_total > expected_internal:
        checks.fail("C11", "internal_solver_cases 总数与 84/实际一致",
                    expected_internal, internal_total, "internal 超过批准上限 84")
    elif actual_starts == expected_starts and internal_total != expected_internal:
        checks.fail("C11", "internal_solver_cases 总数与 84/实际一致",
                    expected_internal, internal_total, "12 starts 时 internal 应恰为 84")
    elif summary_raw.get("internal_solver_cases") not in (None, internal_total):
        checks.fail("C11", "internal_solver_cases 总数与 84/实际一致",
                    {"ledger": internal_total},
                    {"summary": summary_raw.get("internal_solver_cases")},
                    "台账 internal 与 summary 不一致")
    else:
        checks.passed("C11", "internal_solver_cases 总数与 84/实际一致",
                      expected_internal if actual_starts == expected_starts else 7 * actual_starts,
                      internal_total, "每 start 计划 7")

    eval_path = run_dir / "evaluations.jsonl"
    eval_rows: List[Dict[str, Any]] = []
    eval_bad: List[str] = []
    if eval_path.is_file():
        eval_rows, eval_bad = read_jsonl(eval_path)
    if pre_execution:
        checks.nv("C12", "evaluations.jsonl 行数与 7×starts/实际一致",
                  "7 per solved attempt", "not run", "执行前状态")
    elif eval_bad:
        checks.fail("C12", "evaluations.jsonl 行数与 7×starts/实际一致",
                    "parseable", eval_bad[:3], "evaluation 行不可解析")
    elif not eval_rows and actual_starts:
        checks.fail("C12", "evaluations.jsonl 行数与 7×starts/实际一致",
                    ">0", 0, "已有 start 但无 evaluation 行")
    else:
        unknown_attempt = sorted({str(row.get("attempt_id")) for row in eval_rows}
                                 - set(start_ids))
        unknown_case = sorted({str(row.get("case_id")) for row in eval_rows}
                              - set(case_meta))
        bad_flags = [row for row in eval_rows
                     if int(row.get("physical_call_count") or 0) != 0
                     or int(row.get("attempt_physical_solver_starts") or 0) != 1]
        keys = [(str(row.get("attempt_id")), row.get("mach"), row.get("alpha_deg"),
                 row.get("beta_deg")) for row in eval_rows]
        duplicates = len(keys) - len(set(keys))
        expected_rows = EXPECTED_ALPHA_COUNT * actual_starts
        problems = []
        if unknown_attempt:
            problems.append("unknown attempts %s" % unknown_attempt[:3])
        if unknown_case:
            problems.append("unknown cases %s" % unknown_case[:3])
        if bad_flags:
            problems.append("bad physical flags in %d rows" % len(bad_flags))
        if duplicates:
            problems.append("duplicate (attempt,Mach,alpha,Beta) rows=%d" % duplicates)
        if problems:
            checks.fail("C12", "evaluations.jsonl 行数与 7×starts/实际一致",
                        {"rows": expected_rows}, {"rows": len(eval_rows)}, "; ".join(problems))
        elif len(eval_rows) != expected_rows:
            status = STATUS_FAIL if summary_status == "COMPLETED" else STATUS_NV
            checks.add("C12", "evaluations.jsonl 行数与 7×starts/实际一致",
                       status, expected_rows, len(eval_rows),
                       "行数不等于 7×starts（fail-closed 停批时允许 NV）")
        else:
            checks.passed("C12", "evaluations.jsonl 行数与 7×starts/实际一致",
                          expected_rows, len(eval_rows), "7 alpha/start")

    if not summary_path.is_file():
        if pre_execution:
            checks.nv("C13", "batch_summary 与台账守恒", "summary exists", "missing",
                      "执行前状态")
        else:
            checks.fail("C13", "batch_summary 与台账守恒", "summary exists", "missing",
                        "执行产物缺少 batch_summary")
    else:
        problems = []
        for key, actual in (("physical_solver_starts", actual_starts),
                            ("internal_solver_cases", internal_total)):
            expected = summary_raw.get(key)
            if expected is not None and int(expected) != actual:
                problems.append("%s summary=%s ledger=%s" % (key, expected, actual))
        if summary_raw.get("approval_sha256") and approval_sha and summary_raw.get("approval_sha256") != approval_sha:
            problems.append("approval_sha256 summary != approval")
        if summary_raw.get("plan_sha256") and summary_raw.get("plan_sha256") != plan_sha:
            problems.append("plan_sha256 summary != plan")
        planned_executor = str((plan.get("executor") or {}).get("blob_sha256") or "")
        if summary_raw.get("executor_blob_sha256") and planned_executor \
                and summary_raw["executor_blob_sha256"] != planned_executor:
            problems.append("executor_blob summary != plan")
        if problems:
            checks.fail("C13", "batch_summary 与台账守恒", "summary == ledger", problems,
                        "summary 与台账不守恒")
        else:
            checks.passed("C13", "batch_summary 与台账守恒",
                          {"starts": actual_starts, "internal": internal_total},
                          {"summary_starts": summary_raw.get("physical_solver_starts"),
                           "summary_internal": summary_raw.get("internal_solver_cases")}, "")

    manifest_path = run_dir / "data_manifest.json"
    manifest: Dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = load_json(manifest_path)
        except Exception as exc:  # noqa: BLE001
            checks.fail("C14", "data_manifest 计数与文件哈希", "json", "unparsable", repr(exc))
    if not manifest:
        if pre_execution:
            checks.nv("C14", "data_manifest 计数与文件哈希", "manifest", "missing", "执行前状态")
        elif not checks.by_id("C14"):
            checks.fail("C14", "data_manifest 计数与文件哈希", "manifest", "missing", "")
    else:
        problems = []
        if manifest.get("physical_solver_starts") is not None \
                and int(manifest["physical_solver_starts"]) != actual_starts:
            problems.append("manifest physical=%s ledger=%s"
                            % (manifest["physical_solver_starts"], actual_starts))
        if manifest.get("ledger_start_lines") is not None \
                and int(manifest["ledger_start_lines"]) != len(starts):
            problems.append("manifest ledger_start_lines=%s ledger=%s"
                            % (manifest["ledger_start_lines"], len(starts)))
        bad_files = []
        for rel, entry in (manifest.get("files") or {}).items():
            target = run_dir / rel
            if not target.is_file():
                bad_files.append("missing:" + rel)
                continue
            expected_sha = (entry or {}).get("sha256")
            if expected_sha and sha256_file(target) != expected_sha:
                bad_files.append("hash:" + rel)
        if bad_files:
            problems.append("file mismatch %s" % bad_files[:3])
        if problems:
            checks.fail("C14", "data_manifest 计数与文件哈希", "manifest == disk", problems, "")
        else:
            checks.passed("C14", "data_manifest 计数与文件哈希",
                          {"starts": actual_starts, "files": len(manifest.get("files") or {})},
                          {"starts": manifest.get("physical_solver_starts"),
                           "files": manifest.get("file_count")}, "")

    metrics_path = run_dir / "metrics.csv"
    if not metrics_path.is_file():
        if pre_execution:
            checks.nv("C15", "metrics.csv 设计行与判据", "metrics", "missing", "执行前状态")
        else:
            checks.fail("C15", "metrics.csv 设计行与判据", "metrics", "missing", "")
    else:
        lines = [line for line in metrics_path.read_text(encoding="utf-8").splitlines()
                 if line and not line.startswith("#")]
        header = lines[0] if lines else ""
        data_rows = lines[1:]
        problems = []
        if "decision" not in header:
            problems.append("header missing decision")
        if len(data_rows) != len(designs):
            problems.append("design rows %d != plan designs %d" % (len(data_rows), len(designs)))
        metrics_text = metrics_path.read_text(encoding="utf-8")
        calibration_path = run_dir / "calibration_results.json"
        if calibration_path.is_file():
            try:
                calibration = load_json(calibration_path)
                if calibration.get("verdict") != "CAL_COMPLETE" and "POOLABLE_CANDIDATE" in metrics_text:
                    problems.append("CAL_INCOMPLETE 但 metrics 出现 POOLABLE")
            except Exception:  # noqa: BLE001
                problems.append("calibration_results.json unparsable")
        if problems:
            checks.fail("C15", "metrics.csv 设计行与判据", "2 design rows", problems, "")
        else:
            checks.passed("C15", "metrics.csv 设计行与判据",
                          {"designs": len(designs)}, {"rows": len(data_rows)}, "")

    cases_dir = run_dir / "cases"
    case_results: Dict[str, Dict[str, Any]] = {}
    if cases_dir.is_dir():
        for case_id in case_ids:
            result_path = cases_dir / case_id / "case_result.json"
            if result_path.is_file():
                try:
                    case_results[case_id] = load_json(result_path)
                except Exception:  # noqa: BLE001
                    case_results[case_id] = {"status": "UNPARSABLE"}
    missing_cases = [case_id for case_id in case_ids if case_id not in case_results]
    unreachable = [case_id for case_id, result in case_results.items()
                   if result.get("status") == "CAL_FAMILY_UNREACHABLE"]
    solved = [case_id for case_id, result in case_results.items()
              if result.get("status") == "SOLVED"]
    if pre_execution and not case_results:
        checks.nv("C16", "12 case 结果齐全（SOLVED 或 CAL_FAMILY_UNREACHABLE）",
                  len(case_ids), "not run", "执行前状态")
        checks.nv("C17", "CAL_FAMILY_UNREACHABLE 记录零物理", "0 starts",
                  "not run", "执行前状态")
    else:
        summary_unreachable = set(str(item) for item in (summary_raw.get("unreachable_cases") or []))
        problems = []
        if missing_cases:
            status = STATUS_FAIL if summary_status == "COMPLETED" else STATUS_NV
            checks.add("C16", "12 case 结果齐全（SOLVED 或 CAL_FAMILY_UNREACHABLE）",
                       status, len(case_ids), {"missing": missing_cases},
                       "缺失 case 结果（fail-closed 停批时允许 NV）")
        else:
            if summary_unreachable and summary_unreachable != set(unreachable):
                problems.append("summary unreachable %s != disk %s"
                                % (sorted(summary_unreachable), sorted(unreachable)))
            completed_cases = summary_raw.get("completed_cases")
            if completed_cases is not None and int(completed_cases) != len(solved):
                problems.append("summary completed_cases=%s solved=%s"
                                % (completed_cases, len(solved)))
            if problems:
                checks.fail("C16", "12 case 结果齐全（SOLVED 或 CAL_FAMILY_UNREACHABLE）",
                            len(case_ids), problems, "")
            else:
                checks.passed("C16", "12 case 结果齐全（SOLVED 或 CAL_FAMILY_UNREACHABLE）",
                              {"cases": len(case_ids)},
                              {"solved": len(solved), "unreachable": len(unreachable)}, "")
        bad_unreachable = []
        for case_id in unreachable:
            result = case_results.get(case_id) or {}
            if int(result.get("physical_solver_starts") or 0) != 0:
                bad_unreachable.append(case_id + ":physical>0")
            if case_id in case_start_counts:
                bad_unreachable.append(case_id + ":ledger_start")
        if bad_unreachable:
            checks.fail("C17", "CAL_FAMILY_UNREACHABLE 记录零物理", "0 starts",
                        bad_unreachable, "不可达族被错误计费")
        else:
            checks.passed("C17", "CAL_FAMILY_UNREACHABLE 记录零物理", "0 starts",
                          {"unreachable": len(unreachable)}, "")

    if pre_execution:
        checks.nv("C19", "证据口径：REAL_VSPAERO/SOLVER_LOOP_VERIFIED/无 fuel",
                  "NOT_VALIDATED/null", "not run", "执行前状态")
    else:
        problems = []
        if summary_raw.get("physical_validation_status") != "NOT_VALIDATED":
            problems.append("summary physical_validation_status=%r"
                            % summary_raw.get("physical_validation_status"))
        if summary_raw.get("fuel_burn_kg") is not None:
            problems.append("summary fuel_burn_kg != null")
        bad_rows = [row for row in eval_rows
                    if row.get("source_kind") != "REAL_VSPAERO"
                    or row.get("evidence_tier") != "SOLVER_LOOP_VERIFIED"
                    or row.get("fuel_burn_kg") is not None]
        if bad_rows:
            problems.append("evaluation rows bad source/evidence/fuel: %d" % len(bad_rows))
        if problems:
            checks.fail("C19", "证据口径：REAL_VSPAERO/SOLVER_LOOP_VERIFIED/无 fuel",
                        "NOT_VALIDATED/null", problems, "")
        else:
            checks.passed("C19", "证据口径：REAL_VSPAERO/SOLVER_LOOP_VERIFIED/无 fuel",
                          "NOT_VALIDATED/null", "ok", "")

    stop_path = run_dir / "stop_report.json"
    if stop_hits:
        if not stop_path.is_file():
            checks.fail("C20", "stop_report 与 summary stop_hits 一致",
                        "stop_report exists", "missing", "")
        else:
            try:
                stop_report = load_json(stop_path)
                problems = []
                if [item.get("condition") for item in (stop_report.get("conditions") or [])] != \
                        [item.get("condition") for item in stop_hits]:
                    problems.append("conditions differ")
                if int(stop_report.get("physical_solver_starts") or 0) != actual_starts:
                    problems.append("starts differ")
                if problems:
                    checks.fail("C20", "stop_report 与 summary stop_hits 一致",
                                "same conditions/counts", problems, "")
                else:
                    checks.passed("C20", "stop_report 与 summary stop_hits 一致",
                                  "same conditions/counts", "ok", "")
            except Exception as exc:  # noqa: BLE001
                checks.fail("C20", "stop_report 与 summary stop_hits 一致",
                            "parseable", repr(exc), "")
    elif pre_execution:
        checks.nv("C20", "stop_report 与 summary stop_hits 一致", "no stop", "not run",
                  "执行前状态")
    elif stop_path.is_file():
        checks.nv("C20", "stop_report 与 summary stop_hits 一致", "no stop_report",
                  "stop_report exists", "无 stop_hits 却有 stop_report，需人工确认")
    else:
        checks.passed("C20", "stop_report 与 summary stop_hits 一致", "no stop",
                      "no stop", "")

    if pre_execution:
        checks.nv("C21", "SOLVED case 均有 case plan/approval 且 approved", "present",
                  "not run", "执行前状态")
    else:
        problems = []
        for case_id in solved:
            case_dir = cases_dir / case_id
            for name in ("plan.json", "approval.json"):
                if not (case_dir / name).is_file():
                    problems.append("%s missing %s" % (case_id, name))
            approval_file = case_dir / "approval.json"
            if approval_file.is_file():
                try:
                    case_approval = load_json(approval_file)
                    if case_approval.get("approved") is not True:
                        problems.append("%s case approval not approved" % case_id)
                except Exception:  # noqa: BLE001
                    problems.append("%s case approval unparsable" % case_id)
        if problems:
            checks.fail("C21", "SOLVED case 均有 case plan/approval 且 approved",
                        "present", problems[:5], "")
        else:
            checks.passed("C21", "SOLVED case 均有 case plan/approval 且 approved",
                          "present", {"solved": len(solved)}, "")

    sums_path = run_dir / "SHA256SUMS.txt"
    if not sums_path.is_file():
        if pre_execution:
            checks.nv("C22", "SHA256SUMS.txt 逐文件校验", "present", "missing", "执行前状态")
        else:
            checks.fail("C22", "SHA256SUMS.txt 逐文件校验", "present", "missing", "")
    else:
        problems = []
        listed = []
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                problems.append("bad line: " + line[:80])
                continue
            digest, rel = parts[0], parts[1].lstrip("*")
            listed.append(rel)
            target = run_dir / rel
            if not target.is_file():
                problems.append("missing:" + rel)
            elif sha256_file(target) != digest:
                problems.append("hash:" + rel)
        if "data_manifest.json" not in listed:
            problems.append("data_manifest.json not listed")
        if problems:
            checks.fail("C22", "SHA256SUMS.txt 逐文件校验", "all match", problems[:5], "")
        else:
            checks.passed("C22", "SHA256SUMS.txt 逐文件校验", "all match",
                          {"files": len(listed)}, "")

    if pre_execution and not any(item["status"] == STATUS_FAIL for item in checks.items):
        overall = STATUS_PRE
    elif any(item["status"] == STATUS_FAIL for item in checks.items):
        overall = STATUS_FINDINGS
    else:
        overall = STATUS_OK

    observed = {
        "plan_sha256": plan_sha,
        "approval_sha256": approval_sha,
        "executor_sha256": executor_sha,
        "ledger_start_lines": len(starts),
        "ledger_end_lines": len(ends),
        "physical_solver_starts": actual_starts,
        "internal_solver_cases": internal_total,
        "evaluation_rows": len(eval_rows),
        "summary_status": summary_status or None,
        "summary_starts": summary_raw.get("physical_solver_starts"),
        "summary_internal": summary_raw.get("internal_solver_cases"),
        "manifest_starts": manifest.get("physical_solver_starts"),
        "case_ids": len(case_ids),
        "solved_cases": len(solved),
        "unreachable_cases": len(unreachable),
        "missing_cases": missing_cases,
        "stop_conditions": [item.get("condition") for item in stop_hits],
    }
    return _report(run_dir, overall, checks, notes,
                   expected_approval_sha, expected_executor_sha,
                   expected_starts, expected_internal, observed,
                   {"pre_execution": pre_execution, "plan_sha256": plan_sha,
                    "approval_sha256": approval_sha, "run_id": plan.get("run_id"),
                    "batch_id": plan.get("batch_id")})


def _report(run_dir: Path, status: str, checks: Checks, notes: Sequence[str],
            expected_approval_sha: str, expected_executor_sha: str,
            expected_starts: int, expected_internal: int,
            observed: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    findings = [item for item in checks.items if item["status"] == STATUS_FAIL]
    return {
        "schema": SCHEMA,
        "tool_version": TOOL_VERSION,
        "generated_utc": utc_now(),
        "run_dir": str(run_dir),
        "run_id": meta.get("run_id"),
        "batch_id": meta.get("batch_id"),
        "status": status,
        "pre_execution": bool(meta.get("pre_execution", False)),
        "expected": {
            "approval_sha256": expected_approval_sha,
            "executor_blob_sha256": expected_executor_sha,
            "starts": expected_starts,
            "internal_cases": expected_internal,
            "physical_call_count": PHYSICAL,
        },
        "observed": observed,
        "checks": checks.items,
        "findings": findings,
        "summary": {
            "checks_total": len(checks.items),
            "pass": sum(1 for item in checks.items if item["status"] == STATUS_PASS),
            "fail": len(findings),
            "nv": sum(1 for item in checks.items if item["status"] == STATUS_NV),
        },
        "notes": list(notes),
        "physical_call_count": PHYSICAL,
        "physical_solver_starts": PHYSICAL,
        "disclaimer": ("A2 独立只读交叉核对，不替代 A5 正式签署；"
                       "不构成气动/燃油/优化器结论；未启动 solver。"),
    }


def status_exit_code(status: str) -> int:
    if status == STATUS_BLOCKED:
        return 2
    if status == STATUS_FINDINGS:
        return 3
    return 0


def render_markdown(report: Dict[str, Any]) -> str:
    status = report["status"]
    status_zh = {
        STATUS_OK: "对账通过（RECONCILED_OK）",
        STATUS_FINDINGS: "对账发现不一致（RECONCILED_WITH_FINDINGS）",
        STATUS_PRE: "尚未执行（PRE_EXECUTION_NOT_RUN）",
        STATUS_BLOCKED: "无法对账（BLOCKED）",
    }.get(status, status)
    lines: List[str] = []
    lines.append("# P2A-CAL 执行后独立对账报告（A2）")
    lines.append("")
    lines.append("- 工具：%s / %s" % (TOOL_VERSION, SCHEMA))
    lines.append("- 生成时间（UTC）：%s" % report.get("generated_utc"))
    lines.append("- run dir：%s" % report.get("run_dir"))
    lines.append("- run_id：%s；batch_id：%s" % (report.get("run_id"), report.get("batch_id")))
    lines.append("- 总判定：**%s**" % status_zh)
    lines.append("- 物理调用：physical_call_count=0、physical_solver_starts=0（只读对账，未启动 solver）")
    lines.append("")
    lines.append("## 1. 关键计数")
    lines.append("")
    lines.append("| 口径 | 值 |")
    lines.append("|---|---|")
    obs = report.get("observed") or {}
    for key, label in (
        ("physical_solver_starts", "物理 start（台账）"),
        ("ledger_start_lines", "台账 start 行"),
        ("ledger_end_lines", "台账 end 行"),
        ("internal_solver_cases", "internal cases（台账）"),
        ("evaluation_rows", "evaluation 行"),
        ("summary_starts", "batch_summary starts"),
        ("summary_internal", "batch_summary internal"),
        ("manifest_starts", "data_manifest starts"),
        ("solved_cases", "SOLVED case"),
        ("unreachable_cases", "CAL_FAMILY_UNREACHABLE case"),
        ("missing_cases", "缺失 case"),
    ):
        lines.append("| %s | %s |" % (label, obs.get(key)))
    expected = report.get("expected") or {}
    lines.append("| 计划 starts / internal | %s / %s |"
                 % (expected.get("starts"), expected.get("internal_cases")))
    lines.append("| approval SHA256（期望） | %s |" % expected.get("approval_sha256"))
    lines.append("| approval SHA256（实际） | %s |" % obs.get("approval_sha256"))
    lines.append("| executor blob（期望/实际） | %s / %s |"
                 % (expected.get("executor_blob_sha256"), obs.get("executor_sha256")))
    lines.append("")
    lines.append("## 2. 逐项检查")
    lines.append("")
    lines.append("| # | 检查项 | 结果 | 期望 | 实际 | 说明 |")
    lines.append("|---|---|---|---|---|---|")
    for item in report.get("checks") or []:
        detail = str(item.get("detail") or "").replace("|", "/")[:160]
        expected_text = json.dumps(item.get("expected"), ensure_ascii=False)[:80]
        actual_text = json.dumps(item.get("actual"), ensure_ascii=False)[:80]
        lines.append("| %s | %s | **%s** | %s | %s | %s |"
                     % (item.get("id"), item.get("title"), item.get("status"),
                        expected_text, actual_text, detail))
    lines.append("")
    lines.append("## 3. 不一致项（FAIL）")
    lines.append("")
    findings = report.get("findings") or []
    if not findings:
        lines.append("无 FAIL 项。")
    else:
        for item in findings:
            lines.append("- **%s %s**：期望 %s，实际 %s；%s"
                         % (item.get("id"), item.get("title"),
                            json.dumps(item.get("expected"), ensure_ascii=False),
                            json.dumps(item.get("actual"), ensure_ascii=False),
                            item.get("detail")))
    lines.append("")
    lines.append("## 4. 结论与边界")
    lines.append("")
    if report.get("pre_execution"):
        lines.append("当前运行目录尚未出现 approval/台账/batch_summary，判定为 **PRE_EXECUTION_NOT_RUN**，"
                     "仅完成计划、执行器 blob 与预算的结构性预检；执行完成后须重新运行本工具。")
    elif status == STATUS_OK:
        lines.append("台账、evaluation、batch_summary、data_manifest 与 metrics 的计数互相守恒，"
                     "start/end 一一配对，attempt_id 均为 <case_id>-a01，未发现重试/额外启动；"
                     "approval 与 executor blob 均绑定到批准值。")
    elif status == STATUS_FINDINGS:
        lines.append("发现 **%d** 项 FAIL（见第 3 节），在 A5 复核前不得把该批结果用于下游；"
                     "需由 A1/A5 定位并记录，不得静默修补。" % len(findings))
    else:
        lines.append("无法完成对账（缺 run dir 或 plan.json）。")
    lines.append("")
    lines.append("本报告为 A2 独立只读交叉核对，**不替代 A5 正式结果签署**；"
                 "不构成气动、燃油或优化器结论；全程未启动 VSPAERO/任何 solver。")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: Dict[str, Any], json_path: Optional[Path],
                  md_path: Optional[Path], out_dir: Optional[Path],
                  run_dir: Path) -> Tuple[Path, Path]:
    run_id = report.get("run_id") or "CAL"
    if json_path is None or md_path is None:
        base = out_dir or (Path.cwd() / "docs" / "reviews" / "dreal001" / "cal_reconcile")
        base = Path(base)
        json_path = json_path or (base / ("%s_reconcile.json" % run_id))
        md_path = md_path or (base / ("%s_reconcile.md" % run_id))
    json_path = Path(json_path).resolve()
    md_path = Path(md_path).resolve()
    for target in (json_path, md_path):
        if run_dir.resolve() == target.parent or run_dir.resolve() in target.parents:
            raise SystemExit("refusing to write into the A1 run directory: %s" % target)
        target.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return json_path, md_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="P2A-CAL 执行后独立对账（A2 只读，零物理）")
    parser.add_argument("--run-dir", required=True,
                        help="例如 .../runs/DREAL001-P2CAL-20261111-02")
    parser.add_argument("--expected-approval-sha", default=DEFAULT_EXPECTED_APPROVAL_SHA)
    parser.add_argument("--expected-executor-sha", default=DEFAULT_EXPECTED_EXECUTOR_SHA)
    parser.add_argument("--expected-starts", type=int, default=DEFAULT_EXPECTED_STARTS)
    parser.add_argument("--expected-internal", type=int, default=DEFAULT_EXPECTED_INTERNAL)
    parser.add_argument("--json", default=None, help="JSON 输出路径（默认 docs/reviews/...）")
    parser.add_argument("--md", default=None, help="Markdown 输出路径（默认 docs/reviews/...）")
    parser.add_argument("--out-dir", default=None, help="默认输出目录")
    parser.add_argument("--print-json", action="store_true", help="stdout 打印完整 JSON")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    report = reconcile(run_dir,
                       expected_approval_sha=args.expected_approval_sha,
                       expected_executor_sha=args.expected_executor_sha,
                       expected_starts=args.expected_starts,
                       expected_internal=args.expected_internal)
    json_path, md_path = write_outputs(report, Path(args.json) if args.json else None,
                                       Path(args.md) if args.md else None,
                                       Path(args.out_dir) if args.out_dir else None,
                                       run_dir)
    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report["summary"]
        print("[%s] checks PASS=%d FAIL=%d NV=%d"
              % (report["status"], summary["pass"], summary["fail"], summary["nv"]))
        print("json: %s" % json_path)
        print("md:   %s" % md_path)
        if report["status"] == STATUS_PRE:
            print("note: approval/ledger/batch_summary 尚未齐全（PRE_EXECUTION_NOT_RUN）")
    return status_exit_code(report["status"])


if __name__ == "__main__":
    sys.exit(main())
