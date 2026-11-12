"""P2a pre-registration package tests (A2, zero physical).

Covers: plan matrix/budget identity, governance naming, digest canonicalisation,
approval.DRAFT fail-closed, dry-run/verify PASS, and the no-solver guarantee.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import hashlib

import numpy as np

from research.concorde_metaopt.dreal001.optimizers import p2a, p2a_support
from research.concorde_metaopt.dreal001.optimizers.p2a_support import (
    SUPPORT_SCHEMA,
    WarmStartSupportError,
    design_hash,
    load_warmstart_support,
)

A1_ROOT = Path(__file__).resolve().parents[3].parent / "wt-real-a1-geometry-solver"


def _support_fixture(tmp_path: Path, n: int = 15) -> Path:
    rng = np.random.default_rng(20261111)
    records = []
    for index in range(n):
        design = [float(value) for value in rng.random(12)]
        records.append(
            {
                "design": design,
                "design_hash": design_hash(design),
                "native_family": [543, 472],
                "D_i_N": 900.0 + 11.0 * index,
                "source_record_sha": hashlib.sha256(("record-%d" % index).encode("utf-8")).hexdigest(),
                "source_run_id": "DREAL001-P1C-20261110-01",
                "source_batch_id": "DREAL001-P1C-20261110-01",
                "solver_status": "SOLVED_VALID",
                "mesh_family": [543, 472],
                "same_family": True,
            }
        )
    payload = {
        "schema": SUPPORT_SCHEMA,
        "batch_id": "DREAL001-P1C-20261110-01",
        "n_designs": n,
        "target_mesh_family": [543, 472],
        "source_batch_ids": ["DREAL001-P1C-20261110-01"],
        "records": records,
    }
    path = tmp_path / "p2a_warmstart_support.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write(tmp_path: Path, **kwargs):
    batch = tmp_path / "batch"
    docs = tmp_path / "docs"
    kwargs.setdefault("support_path", _support_fixture(tmp_path))
    return p2a.write_p2a_batch(batch, a1_root=kwargs.pop("a1_root", A1_ROOT), docs_dir=docs, **kwargs)


def test_plan_schema_and_identity_fields(tmp_path):
    result = _write(tmp_path)
    plan = json.loads((Path(result["batch_dir"]) / "plan.json").read_text(encoding="utf-8"))
    assert plan["schema"] == p2a.P2A_PLAN_SCHEMA
    assert plan["batch_id"] == p2a.P2A_BATCH_ID
    assert p2a.BATCH_ID_RE.match(plan["batch_id"])
    assert plan["planned_starts"] == 384
    assert plan["budget"]["max_starts"] == 384
    assert plan["budget"]["max_internal_cases"] == 2688
    assert plan["budget"]["expected_internal_cases"] == 2688
    assert plan["budget"]["max_refine_starts"] == 0
    assert plan["timeouts"]["per_case_seconds"] == 60.0
    assert plan["timeouts"]["timeout_overrides"] == {}
    assert plan["warmstart"]["support_size"] == 15
    assert plan["warmstart"]["policy"]["initial_designs"] == 3
    assert len(plan["run_matrix"]) == 6
    assert len(plan["case_matrix"]) == 384
    assert plan["l_ref"]["L_ref_N"] == 1333704.4
    assert plan["identity_binding"]["l_ref"]["value_N"] == 1333704.4
    assert plan["physical_solver_starts"] == 0
    assert plan["notes"].startswith("P2a pre-registration only")


def test_run_ids_follow_governance(tmp_path):
    plan = p2a.build_plan(batch_dir=tmp_path / "batch", a1_root=A1_ROOT)
    run_ids = [row["run_id"] for row in plan["run_matrix"]]
    assert run_ids == ["DREAL001-P2-20261111-01-%s-B64-s42" % arm for arm in p2a.ARMS]
    for run_id in run_ids:
        assert p2a.RUN_ID_RE.match(run_id), run_id
    for run in plan["run_matrix"]:
        assert run["budget_starts"] == 64
        assert run["seed"] == 42
        assert run["initial_designs"] == 3
        assert run["warmstart"] == (run["arm_id"] in p2a.ADAPTIVE_ARMS)
    for case in plan["case_matrix"][:5]:
        assert p2a.RUN_ID_RE.match(case["run_id"])
        assert "c%04d" % case["budget_slot"] in case["case_slot_id"]
        assert case["case_id_template"].endswith("<design_hash8>")
        assert case["expected_internal_cases"] == 7
        assert case["timeout_seconds"] == 60.0
        assert case["refine_allowed"] is False


def test_case_matrix_digest_is_canonical(tmp_path):
    plan = p2a.build_plan(batch_dir=tmp_path / "batch", a1_root=A1_ROOT)
    projected = p2a.case_matrix_digest(plan["case_matrix"])
    assert projected == plan["case_matrix_digest"]
    assert p2a.case_matrix_digest(plan["case_matrix"]) == projected
    assert plan["case_matrix_digest_full_canonical"] != projected
    assert plan["case_matrix_digest_full_canonical"] == p2a._sha_of_json(plan["case_matrix"])


def test_approval_draft_blocks_real(tmp_path):
    result = _write(tmp_path)
    batch = Path(result["batch_dir"])
    plan = json.loads((batch / "plan.json").read_text(encoding="utf-8"))
    approval = json.loads((batch / "approval.DRAFT.json").read_text(encoding="utf-8"))
    assert approval["schema"] == p2a.P2A_APPROVAL_SCHEMA
    assert approval["approved"] is False
    assert approval["approved_by"] == ""
    assert approval["max_starts"] == 384
    assert approval["planned_starts"] == 384
    assert approval["plan_sha256"] == result["plan_sha256"]
    assert approval["case_matrix_digest"] == plan["case_matrix_digest"]
    assert approval["digest_scope"]
    assert approval["window"]["start_utc"] == p2a.WINDOW_START_UTC
    assert approval["window"]["end_utc"] == p2a.WINDOW_END_UTC
    assert approval["window"]["token"] == p2a.WINDOW_TOKEN
    assert len(approval["run_ids"]) == 6
    assert approval["solver"]["parallelism"] == "1 process x 1 omp thread"
    assert approval["physical_solver_starts"] == 0
    from research.concorde_metaopt.dreal001.optimizers.pilot import validate_approval
    with pytest.raises(Exception):
        validate_approval(dict(plan, plan_sha256=result["plan_sha256"]), approval)


def test_dry_run_and_verify_pass(tmp_path):
    result = _write(tmp_path)
    batch = Path(result["batch_dir"])
    dry = p2a.dry_run(batch)
    assert dry["status"] == "DRY_RUN_BLOCKED_FAIL_CLOSED"
    assert dry["n_failed"] == 0
    assert dry["physical_solver_starts"] == 0
    assert dry["solver_started"] is False
    assert dry["real_path"]["status"] == "BLOCKED_FAIL_CLOSED"
    assert dry["checks"]
    report = p2a.verify(batch)
    assert report["status"] == "PASS", report
    assert all(check["status"] == "PASS" for check in report["checks"])


def test_sha256sums_cover_plan_and_prereg(tmp_path):
    result = _write(tmp_path)
    batch = Path(result["batch_dir"])
    sums = (batch / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert "plan.json" in sums
    assert "approval.DRAFT.json" in sums
    assert "identity_binding.json" in sums
    assert result["plan_sha256"] in sums
    prereg = Path(result["prereg_path"]).read_text(encoding="utf-8")
    assert "P1R=INCOMPLETE_S1_STOPPED_WITH_PROTOCOL_DEVIATION" in prereg.replace("：", ":").replace("=", "=") or "P1R=INCOMPLETE" in prereg
    assert "P2A-PREREG-v1" in prereg
    assert "single seed" in prereg.lower() or "单 seed" in prereg
    assert "physical_solver_starts" in prereg


def test_preregistration_discloses_required_states(tmp_path):
    result = _write(tmp_path)
    text = Path(result["prereg_path"]).read_text(encoding="utf-8")
    flat = text.replace(" ", "")
    for token in (
        "P1R=INCOMPLETE_S1_STOPPED_WITH_PROTOCOL_DEVIATION",
        "P1C=SOLVER_INTERNAL_PASS_CONTINUATION",
        "12D_ACTIVE=NOT_VALIDATED",
        "V01/V02",
        "跨族",
        "S1",
        "physical_call_count=0",
        "NOT_RUN",
    ):
        assert token in text or token in flat, token


def test_package_never_launches_solver(tmp_path):
    result = _write(tmp_path)
    batch = Path(result["batch_dir"])
    plan = json.loads((batch / "plan.json").read_text(encoding="utf-8"))
    assert plan["retry_policy"]["infra_retries_allowed"] == 0
    assert plan["physical_solver_starts"] == 0
    text = (batch / "plan.json").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "Popen", "os.system"):
        assert forbidden not in text
    assert plan["stop_conditions_text"]
    codes = {item["code"] for item in plan["stop_conditions"]}
    assert {"S1", "S2", "S3", "S4", "S5", "S6", "S7"} <= codes


def test_support_binding_uses_only_committed_p1c(tmp_path):
    support_path = _support_fixture(tmp_path)
    plan = p2a.build_plan(batch_dir=tmp_path / "batch", a1_root=A1_ROOT, support_path=support_path)
    support = plan["identity_binding"]["support"]
    assert support["status"] == "BOUND"
    assert support["n_designs"] == 15
    assert support["sha256"] == hashlib.sha256(support_path.read_bytes()).hexdigest()
    assert support["zero_new_labels"] is True
    assert support["source_kind"] == "REAL_VSPAERO"
    assert support["support_append_during_run"] is False
    assert support["counted_separately_from_p2a_starts"] is True
    assert any("V01/V02" in item for item in support["disclosures"])
    assert any("cross-family" in item or "Cross-family" in item for item in support["disclosures"])
    assert plan["warmstart_support_status"] == "BOUND"


def test_support_binding_pending_without_a1_artifact(tmp_path):
    plan = p2a.build_plan(batch_dir=tmp_path / "batch", a1_root=A1_ROOT)
    support = plan["identity_binding"]["support"]
    assert support["status"] == "PENDING_A1_ARTIFACT"
    assert support["expected_designs"] == 15
    assert support["schema_requirement"]["required_record_fields"]
    assert plan["warmstart_support_status"] == "PENDING_A1_ARTIFACT"


def test_support_loader_roundtrip(tmp_path):
    path = _support_fixture(tmp_path)
    loaded = load_warmstart_support(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    observed = loaded.to_observed_support()
    assert loaded.n_designs == 15
    assert len(observed["designs"]) == 15 and len(observed["designs"][0]) == 12
    assert all(float(value) > 0 for row in observed["records"] for value in row["design"])
    assert loaded.to_dict()["read_only"] is True
    assert loaded.to_dict()["cache_used"] is False
    assert loaded.to_dict()["physical_call_count"] == 0
    # frozen dataclass: no append/backfill during the run
    with pytest.raises(Exception):
        loaded.records = ()  # type: ignore[misc]


def test_support_loader_rejects_tampering(tmp_path):
    path = _support_fixture(tmp_path)
    good = json.loads(path.read_text(encoding="utf-8"))
    with pytest.raises(WarmStartSupportError):
        load_warmstart_support(path, expected_sha256="0" * 64)

    duplicate = json.loads(json.dumps(good))
    duplicate["records"][1]["design"] = list(duplicate["records"][0]["design"])
    duplicate["records"][1]["design_hash"] = duplicate["records"][0]["design_hash"]
    dup_path = tmp_path / "dup.json"
    dup_path.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(WarmStartSupportError, match="duplicate"):
        load_warmstart_support(dup_path)

    short = json.loads(json.dumps(good))
    short["records"] = short["records"][:14]
    short_path = tmp_path / "short.json"
    short_path.write_text(json.dumps(short), encoding="utf-8")
    with pytest.raises(WarmStartSupportError, match="15"):
        load_warmstart_support(short_path)

    bad_hash = json.loads(json.dumps(good))
    bad_hash["records"][0]["design_hash"] = "0123456789abcdef"
    bad_path = tmp_path / "badhash.json"
    bad_path.write_text(json.dumps(bad_hash), encoding="utf-8")
    with pytest.raises(WarmStartSupportError, match="design_hash"):
        load_warmstart_support(bad_path)

    bad_objective = json.loads(json.dumps(good))
    bad_objective["records"][0]["D_i_N"] = -1.0
    obj_path = tmp_path / "badobj.json"
    obj_path.write_text(json.dumps(bad_objective), encoding="utf-8")
    with pytest.raises(WarmStartSupportError):
        load_warmstart_support(obj_path)


def test_support_loader_rejects_label_leak_keys(tmp_path):
    path = _support_fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    for injected in ("test_labels", "target_objective", "future_eval", "query_label", "prediction"):
        leaked = json.loads(json.dumps(payload))
        leaked["records"][0][injected] = [0.1, 0.2]
        leak_path = tmp_path / (injected + ".json")
        leak_path.write_text(json.dumps(leaked), encoding="utf-8")
        with pytest.raises(WarmStartSupportError, match="outside the P2A-R1 schema"):
            load_warmstart_support(leak_path)


def test_arms_warmstart_uses_frozen_support(tmp_path):
    from research.concorde_metaopt.dreal001.optimizers.arms import ArmSpec, WarmStartSpec, warmstart_designs

    class _Task:
        def task_context(self):
            return (2.02, 18.288)

    path = _support_fixture(tmp_path)
    support = load_warmstart_support(path)
    spec = ArmSpec(
        arm_id="ABO",
        budget_starts=8,
        seed=42,
        warmstart=WarmStartSpec(source="zero_shot_surrogate", support_size=15, candidate_pool_size=64, seed=42),
    )
    designs, info = warmstart_designs(spec, _Task(), None, 4, support=support)
    assert designs.shape == (4, 12)
    assert info["historical_support"] == "FROZEN_A1_ARTIFACT"
    assert info["historical_support_n_designs"] == 15
    assert info["historical_support_sha256"] == support.sha256
    assert info["support_append_during_run"] is False
    assert info["support_cache_used"] is False
    assert info["physical_call_count"] == 0


def test_arms_require_support_fails_closed(tmp_path):
    from research.concorde_metaopt.dreal001.optimizers.arms import ArmSpec, WarmStartSpec, warmstart_designs

    class _Task:
        def task_context(self):
            return (2.02, 18.288)

    spec = ArmSpec(
        arm_id="APSO",
        budget_starts=8,
        seed=42,
        warmstart=WarmStartSpec(source="zero_shot_surrogate", support_size=15, candidate_pool_size=64, seed=42),
    )
    with pytest.raises(WarmStartSupportError):
        warmstart_designs(spec, _Task(), None, 4, support=None, require_support=True)


def test_task_spec_binding_is_thin_and_a1_bound(tmp_path):
    plan = p2a.build_plan(batch_dir=tmp_path / "batch", a1_root=A1_ROOT)
    task = plan["task"]
    solver = task["solver_config"]
    assert solver["geom_set"] == "thin"
    assert solver["tess_u"] == 12.0 and solver["tess_w"] == 25.0
    assert solver["alpha_primary_deg"] == [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0]
    assert solver["refine_starts"] == 0
    assert plan["solver_config_legacy_keys"] == []
    for legacy_key in ("num_wake_nodes", "wake_iters", "alpha_refine_deg", "max_refine_sweeps"):
        assert legacy_key not in solver
    a1_task = plan["a1_task_spec"]
    if a1_task["status"] == "A1_TASK_SPEC_UNAVAILABLE":
        pytest.skip("A1 worktree not present")
    assert a1_task["status"] == "BOUND"
    assert a1_task["schema"] == "dreal001.task_spec.v1"
    assert a1_task["checks"]["geometry_set_thin"] is True
    assert a1_task["checks"]["alpha_fixed_list_deg"] is True
    assert len(a1_task["raw_sha256"]) == 64 and len(a1_task["canonical_sha256"]) == 64
    frozen = plan["frozen_design_space"]
    assert frozen["status"] == "BOUND"
    assert frozen["n_variables"] == 12
    assert len(frozen["raw_sha256"]) == 64 and len(frozen["canonical_sha256"]) == 64 and len(frozen["bounds_sha256"]) == 64


def test_approval_binds_task_spec_frozen_space_and_conservation(tmp_path):
    result = _write(tmp_path)
    batch = Path(result["batch_dir"])
    plan = json.loads((batch / "plan.json").read_text(encoding="utf-8"))
    approval = json.loads((batch / "approval.DRAFT.json").read_text(encoding="utf-8"))
    assert approval["task_spec"]["a1_raw_sha256"] == plan["a1_task_spec"]["raw_sha256"]
    assert approval["task_spec"]["a1_canonical_sha256"] == plan["a1_task_spec"]["canonical_sha256"]
    assert approval["task_spec"]["thin_12x25_7alpha"] is True
    assert approval["frozen_design_space"]["raw_sha256"] == plan["frozen_design_space"]["raw_sha256"]
    assert approval["frozen_design_space"]["canonical_sha256"] == plan["frozen_design_space"]["canonical_sha256"]
    assert approval["frozen_design_space"]["bounds_sha256"] == plan["frozen_design_space"]["bounds_sha256"]
    assert approval["conservation"]["one_start_equals"]["internal_solver_cases"] == 7
    assert approval["conservation"]["refine"]["max_refine_starts"] == 0
    assert "projected case-slot fields" in approval["digest_scope"]
    assert "384" in approval["digest_scope"]
    assert approval["case_matrix_digest"] == plan["case_matrix_digest"]
    assert approval["case_matrix_digest_full_canonical"] == plan["case_matrix_digest_full_canonical"]
    assert approval["amendment_log"][0]["superseded_plan_sha256"].startswith("c8eb7d28")
    assert approval["amendment_log"][0]["physical_solver_starts"] == 0


def test_dry_run_real_a1_path_records_code_sha(tmp_path):
    result = _write(tmp_path)
    batch = Path(result["batch_dir"])
    dry = json.loads((batch / "dry_run.json").read_text(encoding="utf-8"))
    assert dry["n_failed"] == 0, [c for c in dry["checks"] if c["status"] == "FAIL"]
    assert dry["a1_probe"]["status"] == "REFUSED_BEFORE_SOLVER"
    assert dry["a1_probe"]["physical_call_count"] == 0
    assert dry["a2_probe"]["status"] == "REFUSED_BEFORE_SPAWN"
    assert dry["a2_probe"]["physical_call_count"] == 0
    assert len(dry["code_sha"]) == 64
    assert dry["executor_blob"]["path"].endswith("p2a.py")
    assert dry["executor_blob"]["a1_code_files"]
    assert dry["window"]["start_utc"] == p2a.WINDOW_START_UTC
    assert dry["window"]["remaining_s"] is not None
    assert dry["cases_emitted"] == 0
    assert dry["ledger_created"] is False
    assert dry["solver_processes"] == 0
    by_name = {check["check"]: check for check in dry["checks"]}
    for required in (
        "a1_task_spec_bound",
        "task_spec_thin_12x25_7alpha",
        "p2a_contract_thin_bound",
        "frozen_design_space_bound",
        "conservation_three_ledgers",
        "digest_scope_two_values",
        "warmstart_support_bound",
        "mesh_policy_canonical_roundtrip",
        "endpoint_policy_declared",
        "a1_fail_closed_before_solver",
        "a2_adapter_fail_closed_before_spawn",
        "no_runtime_artifacts",
    ):
        assert by_name[required]["status"] == "PASS", (required, by_name[required])


def test_evaluator_binding_pending_or_bound(tmp_path):
    plan = p2a.build_plan(batch_dir=tmp_path / "batch", a1_root=A1_ROOT)
    evaluator = plan["identity_binding"]["evaluator"]
    assert evaluator["module"].endswith("geometry.evaluator")
    assert evaluator["class"] == "AeroEvaluator"
    assert evaluator["status"] in ("EVALUATOR_PENDING_A1_V1_1", "EVALUATOR_V1_1_TEMPLATE_BOUND")
    assert evaluator["physical_call_count_in_a2"] == 0
    if evaluator["status"] == "EVALUATOR_PENDING_A1_V1_1":
        assert "EVALUATOR_PENDING_A1_V1_1" in plan["notes"]

def test_mesh_policy_is_canonical_roundtrip(tmp_path):
    plan = p2a.build_plan(batch_dir=tmp_path / "batch", a1_root=A1_ROOT)
    mesh = plan["mesh_policy"]
    assert mesh["mesh_policy"] == "canonical_roundtrip_native_family"
    assert mesh["no_target_family"] is True
    assert mesh["target_mesh_family"] is None
    assert mesh["single_build"] is True
    assert mesh["max_build_attempts_per_design"] == 1
    assert mesh["fail_closed_0_start"] is True
    assert mesh["actual_family_recorded_per_design"] is True
    assert mesh["determinism_evidence"]["status"] == "PENDING_A1_V1_VALIDATION"
    assert mesh["max_mesh_attempts"] == 1
    assert mesh["cross_family_numeric_comparison"].startswith("FORBIDDEN")
    assert plan["mesh_target_family"] is None
    assert plan["case_matrix"][0]["mesh_target_family"] is None
    assert plan["case_matrix"][0]["actual_family_recorded_at_execution"] is True
    endpoints = plan["endpoint_policy"]
    assert endpoints["E1_anytime_best_D_i"].startswith("DESCRIPTIVE_ONLY")
    assert endpoints["E2_best_D_i_at_B"].startswith("DESCRIPTIVE_ONLY")
    assert "CROSS_FAMILY_NUMERIC_NOT_COMPARABLE" in endpoints["E2_best_D_i_at_B"]
    assert endpoints["E3_six_arm_ranking_or_winner"].startswith("NOT_COMPARABLE")
    assert endpoints["E5_significance_or_overall_winner"].startswith("NOT_COMPUTABLE")
    assert endpoints["E6_failure_classification_and_feasible_rate"].startswith("DESCRIPTIVE_ONLY")
    assert endpoints["family_label_required"] is True
    approval = p2a.build_approval_draft(plan, "0" * 64)
    assert approval["mesh_policy"]["mesh_policy"] == "canonical_roundtrip_native_family"
    assert approval["endpoint_policy"]["E3_six_arm_ranking_or_winner"].startswith("NOT_COMPARABLE")
    assert "write .vsp3 -> Clear -> Read -> ComputeGeometry" in approval["references"]["reconstruction"]


def test_support_loader_allows_absent_target_family(tmp_path):
    path = _support_fixture(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("target_mesh_family")
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_warmstart_support(path)
    assert loaded.target_mesh_family == ()
    assert loaded.n_designs == 15

