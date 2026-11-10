"""F1 最小 E2E：12D 设计 -> 合成/归档评价 -> BO/DE ask-tell -> run 产物（零物理调用）。"""

import csv
import hashlib
import json

from research.concorde_metaopt.f_line import (
    ArchiveReplayEvaluator,
    BudgetLedger,
    MockEvaluator,
    run_bo_search,
    run_de_search,
    write_run_artifacts,
)
from research.concorde_metaopt.f_line.mock_evaluator import BASELINE_FUEL_KG

RUN_FILES = (
    "run_config.json",
    "evaluations.jsonl",
    "optimization_history.csv",
    "metrics.csv",
    "data_manifest.json",
    "SHA256SUMS.txt",
)


def test_bo_run_is_zero_physics(design_space_12d, fixed_cruise_task, mock_evaluator):
    ledger = BudgetLedger(physical_budget=0, run_id="f1-bo-test")
    summary = run_bo_search(
        mock_evaluator,
        ledger,
        design_space_12d,
        fixed_cruise_task,
        run_id="f1-bo-test",
        requests=8,
        initial_designs=4,
        seed=42,
    )
    assert summary["requests"] == 8
    assert summary["iterations"] == 8
    assert ledger.requests == 8
    assert summary["physical_call_count"] == 0
    assert ledger.physical_calls == 0
    assert all(record.physical_call_count == 0 for record in ledger.records)
    assert all(row["physical_call_count"] == 0 for row in summary["history"])
    best = summary["best_feasible"]
    assert best is not None
    assert best["physical_call_count"] == 0
    assert best["objective"] <= BASELINE_FUEL_KG
    assert best["objective"] < BASELINE_FUEL_KG  # 合成线性响应应产生可观测改进


def test_de_run_is_zero_physics(design_space_12d, fixed_cruise_task, mock_evaluator):
    ledger = BudgetLedger(physical_budget=0, run_id="f1-de-test")
    summary = run_de_search(
        mock_evaluator,
        ledger,
        design_space_12d,
        fixed_cruise_task,
        run_id="f1-de-test",
        requests=12,
        population_size=6,
        seed=42,
    )
    assert summary["requests"] == 12
    assert ledger.requests == 12
    assert summary["generations"] >= 1
    assert summary["physical_call_count"] == 0
    assert ledger.physical_calls == 0
    assert all(row["physical_call_count"] == 0 for row in summary["history"])
    best = summary["best_feasible"]
    assert best is not None
    assert best["objective"] < BASELINE_FUEL_KG


def test_run_artifacts_are_complete_and_self_consistent(
    tmp_path, design_space_12d, fixed_cruise_task, mock_evaluator
):
    ledger = BudgetLedger(physical_budget=0, run_id="f1-artifacts")
    summary = run_bo_search(
        mock_evaluator,
        ledger,
        design_space_12d,
        fixed_cruise_task,
        run_id="f1-artifacts",
        requests=6,
        initial_designs=3,
        seed=42,
    )
    output = tmp_path / "run"
    write_run_artifacts(output, summary, ledger, design_space_12d, fixed_cruise_task, mock_evaluator)

    for name in RUN_FILES:
        assert (output / name).is_file(), name
    assert (output / "figures" / "README.md").is_file()

    run_config = json.loads((output / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["physical_call_count"] == 0
    assert run_config["zero_physical_run"] is True
    assert run_config["budget_B"] == 0
    assert run_config["design_set"] == "12d_lifting_surfaces"
    assert run_config["design_dim"] == 12
    assert run_config["source_kind"] == "SYNTHETIC_MOCK"
    assert run_config["fidelity"] == "synthetic"
    assert run_config["K"] == 6
    assert run_config["initial_population_size"] == 3
    assert run_config["seed"] == 42
    assert run_config["task_id"] == fixed_cruise_task.task_id

    rows = [
        json.loads(line)
        for line in (output / "evaluations.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == len(ledger.records) == ledger.requests
    assert all(row["physical_call_count"] == 0 for row in rows)
    assert all(len(row["constraints"]) == 10 for row in rows)
    assert all(row["source_kind"] == "SYNTHETIC_MOCK" for row in rows)

    manifest = json.loads((output / "data_manifest.json").read_text(encoding="utf-8"))
    assert manifest["physical_call_count"] == 0
    manifest_paths = {item["path"] for item in manifest["files"]}
    # data_manifest.json 在扫描之后写入，因此不自包含；SHA256SUMS.txt 单独覆盖它。
    for name in RUN_FILES:
        if name not in ("SHA256SUMS.txt", "data_manifest.json"):
            assert name in manifest_paths
    assert "figures/README.md" in manifest_paths
    assert "data_manifest.json" not in manifest_paths

    # SHA256SUMS 必须覆盖除自身之外的全部产物，且哈希与文件一致。
    sums = {}
    for line in (output / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split("  ", 1)
        sums[relative] = digest
    actual = {
        path.relative_to(output).as_posix()
        for path in output.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    assert set(sums) == actual
    for relative, digest in sums.items():
        payload = (output / relative).read_bytes()
        assert digest == hashlib.sha256(payload).hexdigest()

    metrics_text = (output / "metrics.csv").read_text(encoding="utf-8")
    assert "NOT_RUN" in metrics_text
    figure_note = (output / "figures" / "README.md").read_text(encoding="utf-8")
    assert "NOT_RUN" in figure_note
    assert "造假图" in figure_note or "伪造" in figure_note


def test_metrics_csv_marks_physical_metrics_not_run(
    tmp_path, design_space_12d, fixed_cruise_task, mock_evaluator
):
    ledger = BudgetLedger(physical_budget=0, run_id="f1-metrics")
    summary = run_bo_search(
        mock_evaluator,
        ledger,
        design_space_12d,
        fixed_cruise_task,
        run_id="f1-metrics",
        requests=4,
        initial_designs=2,
        seed=7,
    )
    output = tmp_path / "metrics-run"
    write_run_artifacts(output, summary, ledger, design_space_12d, fixed_cruise_task, mock_evaluator)
    with (output / "metrics.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    row = rows[0]
    for column in ("drag_polar", "trim_curve", "fuel_burn_physical"):
        assert row[column] == "NOT_RUN"
    assert row["physical_call_count"] == "0"
    assert row["physical_validation_status"] == "NOT_VALIDATED"


def test_replay_run_keeps_physics_not_validated(
    tmp_path, design_space_12d, fixed_cruise_task
):
    evaluator = ArchiveReplayEvaluator(design_space_12d, fixed_cruise_task, run_id="f1-replay-run")
    ledger = BudgetLedger(physical_budget=0, run_id="f1-replay-run")
    summary = run_bo_search(
        evaluator,
        ledger,
        design_space_12d,
        fixed_cruise_task,
        run_id="f1-replay-run",
        requests=4,
        initial_designs=2,
        seed=42,
    )
    assert summary["physical_call_count"] == 0
    assert summary["best_feasible"] is None  # 归档 replay 不产生可行目标值
    assert all(record.objective is None for record in ledger.records)
    assert all(record.status != "VALID" for record in ledger.records)
    output = tmp_path / "replay-run"
    write_run_artifacts(output, summary, ledger, design_space_12d, fixed_cruise_task, evaluator)
    run_config = json.loads((output / "run_config.json").read_text(encoding="utf-8"))
    assert run_config["source_kind"] == "ARCHIVE_REPLAY"
    assert run_config["physical_validation_status"] == "NOT_VALIDATED"
    assert run_config["physical_call_count"] == 0
