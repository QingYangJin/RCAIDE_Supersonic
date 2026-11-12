"""P2A-CAL 执行后独立对账工具测试（A2，零物理，全部 fake 产物）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from research.concorde_metaopt.dreal001.reconcile import cal_reconcile as cr

ALPHAS = (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)
APPROVAL_SHA = "a" * 64


def _dump(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rebuild_manifest_and_sums(root: Path) -> None:
    summary = json.loads((root / "batch_summary.json").read_text(encoding="utf-8"))
    starts = [json.loads(line) for line in
              (root / "solver_attempts.jsonl").read_text(encoding="utf-8").splitlines()
              if line.strip()]
    start_rows = [row for row in starts if row.get("event") == "start"]
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in ("SHA256SUMS.txt", "data_manifest.json"):
            files[str(path.relative_to(root)).replace("\\", "/")] = {
                "bytes": path.stat().st_size, "sha256": _sha(path)}
    manifest = {"schema": "dreal001.data_manifest.v1", "run_id": summary["run_id"],
                "created_utc": "2026-11-11T21:05:00Z", "files": files,
                "file_count": len(files),
                "physical_solver_starts": summary["physical_solver_starts"],
                "ledger_start_lines": len(start_rows),
                "batch_summary_status": summary["status"], "source": "fixture"}
    _dump(root / "data_manifest.json", manifest)
    lines = ["%s  %s" % (entry["sha256"], name) for name, entry in sorted(files.items())]
    lines.append("%s  data_manifest.json" % _sha(root / "data_manifest.json"))
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8",
                                         newline="\n")


def _make_fixture(tmp_path: Path, *, n_starts: int = 12, early_stop: bool = False) -> dict:
    root = tmp_path / "run"
    root.mkdir(parents=True, exist_ok=True)
    executor = tmp_path / "executor_p2a_cal.py"
    executor.write_text("# frozen CAL executor fixture\n", encoding="utf-8")
    exec_sha = _sha(executor)
    designs = [("W05-plus", "6653517b11d6f891"), ("W10-plus", "6e4644578e14aaaa")]
    cases = []
    for tag, dh in designs:
        for family in ("f483x418", "f543x472"):
            for repeat in (1, 2, 3):
                cases.append({"case_id": "CAL-%s-%s-r%d" % (tag, family, repeat),
                              "design_tag": tag, "design_hash": dh,
                              "target_family": family, "repeat": repeat,
                              "starts": 1, "expected_internal_cases": 7,
                              "timeout_seconds": 60, "max_mesh_attempts": 40})
    plan = {"schema": "dreal001.p2a_cal_plan.v1", "plan_version": "v1.2",
            "run_id": "DREAL001-P2CAL-20261111-02",
            "batch_id": "DREAL001-P2-20261111-04",
            "status": "PENDING_APPROVAL",
            "designs": [{"design_tag": tag, "design_hash": dh} for tag, dh in designs],
            "case_matrix": cases,
            "budget": {"expected_starts": 12, "max_starts": 12,
                       "expected_internal_cases": 84, "max_internal_cases": 84,
                       "max_refine_starts": 0},
            "executor": {"path": str(executor), "blob_sha256": exec_sha}}
    _dump(root / "plan.json", plan)
    plan_sha = _sha(root / "plan.json")
    approval = {"schema": "dreal001.approval.v3", "status": "APPROVED",
                "approved": True, "approved_by": "lead",
                "approved_at_utc": "2026-11-11T20:55:00Z",
                "run_id": plan["run_id"], "plan_sha256": plan_sha,
                "max_starts": 12, "max_internal_cases": 84,
                "max_refine_starts": 0, "physical_solver_starts": 0}
    _dump(root / "approval.json", approval)
    approval_sha = _sha(root / "approval.json")

    start_cases = cases[:n_starts]
    ledger = []
    evaluations = []
    solved = []
    for index, case in enumerate(start_cases):
        attempt = case["case_id"] + "-a01"
        ledger.append({"schema": "dreal001.solver_attempt.v1", "event": "start",
                       "attempt_id": attempt, "case_id": case["case_id"],
                       "physical_solver_starts": 1, "starts_after": index + 1,
                       "batch_id": plan["batch_id"], "plan_sha256": plan_sha,
                       "approval_sha256": approval_sha})
        ledger.append({"schema": "dreal001.solver_attempt.v1", "event": "end",
                       "attempt_id": attempt, "case_id": case["case_id"],
                       "physical_solver_starts": 0, "status": "SOLVED",
                       "exit_code": 0, "internal_solver_cases": 7})
        for alpha in ALPHAS:
            evaluations.append({
                "schema": "dreal001.evaluation_condition.v1", "run_id": plan["run_id"],
                "case_id": case["case_id"], "attempt_id": attempt,
                "source_kind": "REAL_VSPAERO", "evidence_tier": "SOLVER_LOOP_VERIFIED",
                "physical_call_count": 0, "physical_solver_starts": 0,
                "attempt_physical_solver_starts": 1, "mach": 2.02,
                "alpha_deg": alpha, "beta_deg": 0.0, "CLtot": 0.1,
                "CDi": 0.01, "CDtot": 0.02, "CDo": 0.01, "L_N": 1.0,
                "D_i_N": 900.0, "sref_m2": 358.25, "q_pa": 20483.940233430174,
                "reference_frame": "WING_AC", "lift_rel_error_vs_Lref": 0.0,
                "design": case["design_hash"], "design_hash": case["design_hash"],
                "mesh_family": case["target_family"], "fuel_burn_kg": None,
                "external_physics_supported": False, "ts_utc": "2026-11-11T21:05:00Z",
            })
        solved.append(case["case_id"])
        case_dir = root / "cases" / case["case_id"]
        _dump(case_dir / "plan.json", {"case_id": case["case_id"]})
        _dump(case_dir / "approval.json", {"approved": True})
        _dump(case_dir / "case_result.json",
              {"case_id": case["case_id"], "status": "SOLVED",
               "physical_solver_starts": 1})
    unreachable = []
    if early_stop:
        case = cases[n_starts]
        case_dir = root / "cases" / case["case_id"]
        _dump(case_dir / "plan.json", {"case_id": case["case_id"]})
        _dump(case_dir / "case_result.json",
              {"case_id": case["case_id"], "status": "CAL_FAMILY_UNREACHABLE",
               "physical_solver_starts": 0})
        unreachable.append(case["case_id"])

    (root / "solver_attempts.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in ledger) + "\n",
        encoding="utf-8", newline="\n")
    (root / "evaluations.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in evaluations) + "\n",
        encoding="utf-8", newline="\n")
    stop_hits = ([{"condition": "S1", "detail": "TIMEOUT: fake"}] if early_stop else [])
    summary = {
        "schema": "dreal001.p2a_cal_summary.v1", "run_id": plan["run_id"],
        "batch_id": plan["batch_id"], "plan_sha256": plan_sha,
        "approval_sha256": approval_sha,
        "status": "STOPPED_FAIL_CLOSED" if early_stop else "COMPLETED",
        "physical_solver_starts": len(start_cases),
        "internal_solver_cases": 7 * len(start_cases),
        "completed_cases": len(solved), "unreachable_cases": unreachable,
        "stop_hits": stop_hits, "accounting_flags": [],
        "caps": {"max_starts": 12, "max_internal_cases": 84},
        "executor_blob_sha256": exec_sha,
        "physical_validation_status": "NOT_VALIDATED", "fuel_burn_kg": None,
        "evidence_tier": "SOLVER_LOOP_VERIFIED",
        "created_utc": "2026-11-11T21:30:00Z",
    }
    _dump(root / "batch_summary.json", summary)
    if stop_hits:
        _dump(root / "stop_report.json",
              {"schema": "dreal001.p2a_cal_stop.v1", "run_id": plan["run_id"],
               "status": "STOPPED_FAIL_CLOSED", "conditions": stop_hits,
               "physical_solver_starts": len(start_cases),
               "completed_cases": len(solved)})
    verdict = "CAL_COMPLETE" if not early_stop else "CAL_INCOMPLETE"
    decision = "ROOT_CAUSE_REQUIRED" if not early_stop else "NOT_VALIDATED"
    _dump(root / "calibration_results.json",
          {"run_id": plan["run_id"], "verdict": verdict, "per_design": {}})
    metrics = ["design_tag,design_hash,family_A,family_B,mean_relative_difference,range,n_pairs,decision"]
    for tag, dh in designs:
        metrics.append("%s,%s,f483x418,f543x472,1.0e-3,2.0e-3,3,%s" % (tag, dh, decision))
    metrics.append("# fuel_burn_physical,NOT_RUN,requires validated external physics")
    metrics.append("# 12D_ACTIVE,NOT_VALIDATED,mesh non-determinism unresolved")
    (root / "metrics.csv").write_text("\n".join(metrics) + "\n", encoding="utf-8",
                                      newline="\n")
    _rebuild_manifest_and_sums(root)
    return {"root": root, "executor": executor, "plan_sha": plan_sha,
            "approval_sha": approval_sha, "exec_sha": exec_sha}


def _make_pre_execution(tmp_path: Path) -> dict:
    root = tmp_path / "pre"
    root.mkdir()
    executor = tmp_path / "executor_pre.py"
    executor.write_text("# executor\n", encoding="utf-8")
    plan = {"schema": "dreal001.p2a_cal_plan.v1", "run_id": "DREAL001-P2CAL-20261111-02",
            "batch_id": "DREAL001-P2-20261111-04",
            "designs": [{"design_tag": "W05-plus", "design_hash": "6653517b11d6f891"}],
            "case_matrix": [{"case_id": "C%02d" % i, "starts": 1,
                             "expected_internal_cases": 7} for i in range(12)],
            "budget": {"expected_starts": 12, "max_starts": 12,
                       "expected_internal_cases": 84, "max_internal_cases": 84,
                       "max_refine_starts": 0},
            "executor": {"path": str(executor), "blob_sha256": _sha(executor)}}
    _dump(root / "plan.json", plan)
    return {"root": root, "exec_sha": _sha(executor)}


def _run(fixture: dict, **kwargs):
    params = dict(expected_approval_sha=fixture.get("approval_sha", APPROVAL_SHA),
                  expected_executor_sha=fixture["exec_sha"])
    params.update(kwargs)
    return cr.reconcile(fixture["root"], **params)


def _check(report: dict, check_id: str) -> dict:
    for item in report["checks"]:
        if item["id"] == check_id:
            return item
    raise AssertionError("missing check %s" % check_id)


def test_pre_execution_state_is_zero_physical(tmp_path: Path) -> None:
    fixture = _make_pre_execution(tmp_path)
    report = _run(fixture)
    assert report["status"] == cr.STATUS_PRE
    assert report["pre_execution"] is True
    assert report["physical_call_count"] == 0
    assert _check(report, "C01")["status"] == "PASS"
    assert _check(report, "C05")["status"] == "PASS"
    assert _check(report, "C06")["status"] == "PASS"
    assert _check(report, "C02")["status"] == "NV"
    assert report["summary"]["fail"] == 0


def test_signed_approval_without_execution_is_pre(tmp_path: Path) -> None:
    fixture = _make_pre_execution(tmp_path)
    plan_sha = _sha(fixture["root"] / "plan.json")
    _dump(fixture["root"] / "approval.json",
          {"schema": "dreal001.approval.v3", "approved": True, "approved_by": "lead",
           "approved_at_utc": "2026-11-10T19:10:48Z", "plan_sha256": plan_sha,
           "max_starts": 12, "max_internal_cases": 84})
    fixture["approval_sha"] = _sha(fixture["root"] / "approval.json")
    report = _run(fixture)
    assert report["status"] == cr.STATUS_PRE
    assert report["pre_execution"] is True
    assert _check(report, "C02")["status"] == "PASS"
    assert _check(report, "C03")["status"] == "PASS"
    assert _check(report, "C04")["status"] == "PASS"
    assert _check(report, "C07")["status"] == "NV"
    assert report["findings"] == []


def test_full_batch_reconciles_ok(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    report = _run(fixture)
    assert report["status"] == cr.STATUS_OK, report["findings"]
    assert report["summary"]["fail"] == 0
    assert report["observed"]["physical_solver_starts"] == 12
    assert report["observed"]["internal_solver_cases"] == 84
    assert report["observed"]["evaluation_rows"] == 84
    assert report["observed"]["approval_sha256"] == fixture["approval_sha"]
    for check_id in ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08",
                     "C09", "C10", "C11", "C12", "C13", "C14", "C15", "C16",
                     "C17", "C18", "C19", "C20", "C21", "C22"):
        assert _check(report, check_id)["status"] == "PASS", (check_id, _check(report, check_id))
    assert cr.status_exit_code(report["status"]) == 0


def test_missing_end_line_is_a_finding(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    ledger = fixture["root"] / "solver_attempts.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    removed = [row for row in rows if row.get("event") == "end"][-1]
    rows = [row for row in rows
            if not (row.get("event") == "end" and row.get("attempt_id") == removed["attempt_id"])]
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    _rebuild_manifest_and_sums(fixture["root"])
    report = _run(fixture)
    assert report["status"] == cr.STATUS_FINDINGS
    assert _check(report, "C08")["status"] == "FAIL"
    assert _check(report, "C11")["status"] == "FAIL"
    assert cr.status_exit_code(report["status"]) == 3


def test_retry_attempt_a02_is_a_finding(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    ledger = fixture["root"] / "solver_attempts.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    first = rows[0]
    retry_start = dict(first, attempt_id=first["case_id"] + "-a02",
                       starts_after=13, physical_solver_starts=1)
    rows.append(retry_start)
    ledger.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    _rebuild_manifest_and_sums(fixture["root"])
    report = _run(fixture)
    assert _check(report, "C09")["status"] == "FAIL"
    assert report["status"] == cr.STATUS_FINDINGS


def test_approval_sha_mismatch_is_a_finding(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    report = _run(fixture, expected_approval_sha="0" * 64)
    assert _check(report, "C03")["status"] == "FAIL"
    assert _check(report, "C02")["status"] == "PASS"
    assert report["status"] == cr.STATUS_FINDINGS


def test_early_stop_with_unreachable_case_is_not_counted(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path, n_starts=2, early_stop=True)
    report = _run(fixture)
    assert _check(report, "C10")["status"] == "NV"
    assert _check(report, "C16")["status"] == "NV"
    assert _check(report, "C17")["status"] == "PASS"
    assert _check(report, "C20")["status"] == "PASS"
    assert report["observed"]["physical_solver_starts"] == 2
    assert report["observed"]["unreachable_cases"] == 1
    assert report["findings"] == []


def test_summary_count_mismatch_is_a_finding(tmp_path: Path) -> None:
    fixture = _make_fixture(tmp_path)
    summary_path = fixture["root"] / "batch_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["physical_solver_starts"] = 11
    _dump(summary_path, summary)
    _rebuild_manifest_and_sums(fixture["root"])
    report = _run(fixture)
    assert _check(report, "C13")["status"] == "FAIL"
    assert cr.status_exit_code(report["status"]) == 3


def test_cli_writes_outputs_outside_run_dir(tmp_path: Path, capsys) -> None:
    fixture = _make_fixture(tmp_path)
    out = tmp_path / "out"
    rc = cr.main(["--run-dir", str(fixture["root"]),
                  "--expected-approval-sha", fixture["approval_sha"],
                  "--expected-executor-sha", fixture["exec_sha"],
                  "--out-dir", str(out)])
    assert rc == 0
    json_path = out / "DREAL001-P2CAL-20261111-02_reconcile.json"
    md_path = out / "DREAL001-P2CAL-20261111-02_reconcile.md"
    assert json_path.is_file() and md_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["status"] == cr.STATUS_OK
    assert "独立对账报告" in md_path.read_text(encoding="utf-8")
    assert "physical_call_count=0" in md_path.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        cr.write_outputs(payload, fixture["root"] / "x.json",
                         fixture["root"] / "x.md", None, fixture["root"])
