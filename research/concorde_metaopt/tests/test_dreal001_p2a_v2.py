"""A2 P2a v2 (C+B2) zero-physical unit tests.

No geometry build and no vspaero start: A1 is always injected as fake
callables; physical_call_count stays 0.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from research.concorde_metaopt.dreal001.optimizers.p2a_v2_common import (
    MAX_STARTS, PLANNED_INTERNAL_CASES, PLANNED_STARTS, PREFLIGHT_ACCEPT_NUMERIC_RTOL,
    RESERVE_STARTS, WINDOW_TOKEN,
)
from research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor import (
    summarize_evaluations,
)
from research.concorde_metaopt.dreal001.optimizers.p2a_v2_runtime import (
    A1FreezeApiAdapter, A1LedgerReader, DesignEvaluation, FreezeRecordError,
    FreezeRecordStore, FrozenPairService, PreflightVerifier, P2AV2Batch,
    P2AV2Runner, ReservePool, SolverResult, canonical_json, design_hash,
    sha256_text,
)


def x12(seed: float = 0.1) -> list[float]:
    return [seed + 0.01 * i for i in range(12)]


PAIR = {"483x418": (483, 418), "543x472": (543, 472)}
A1_ROOT = Path(__file__).resolve().parents[3].parent / "wt-real-a1-geometry-solver"


def _family_entry(nodes: int, elements: int, tag: str) -> dict:
    geom = sha256_text("geom-%s" % tag)
    canonical = sha256_text("canon-%s" % tag)
    return {
        "attempts": 3,
        "hit": True,
        "frozen": {
            "frozen_vspgeom_sha256": geom,
            "frozen_vspgeom_bytes": 1000 + nodes,
            "frozen_vkey_sha256": sha256_text("vkey-%s" % tag),
            "frozen_vsp3_sha256": sha256_text("vsp3-%s" % tag),
            "canonical_mesh_sha256": canonical,
            "sref_m2": 350.0 + nodes,
            "frozen_vspgeom_path": "/frozen/%s.vspgeom" % tag,
            "frozen_vkey_path": "/frozen/%s.vkey" % tag,
        },
    }


def pair_record(x: list[float]) -> dict:
    return {
        "status": "PAIR_READY", "discovery_attempts": 5,
        "families": {
            label: _family_entry(n, e, label) for label, (n, e) in PAIR.items()
        },
    }


def void_record(x: list[float]) -> dict:
    return {"status": "DESIGN_VOID", "discovery_attempts": 12,
            "detail": "FAMILY_UNREACHABLE", "discovered_families": ["483x418"]}


class FakeSolver:
    def __init__(self, store: FreezeRecordStore, *, cdi: tuple[float, float] = (0.02, 0.03),
                 status: str = "SOLVED_VALID", tamper_after: bool = False) -> None:
        self.store = store
        self.cdi = cdi
        self.status = status
        self.tamper_after = tamper_after
        self.calls: list[tuple[str, str]] = []

    def evaluate(self, family, dh, slot):
        assert self.store.get(dh) is not None, "append-only record must exist before start"
        self.calls.append((dh, family.label))
        value = self.cdi[0] if slot == "f1" else self.cdi[1]
        return SolverResult(
            status=self.status, cdi=value, cl=0.2,
            physical_solver_starts=1, internal_solver_cases=7,
            vspgeom_sha_before=family.vspgeom_sha256,
            vspgeom_sha_after=("deadbeef" if self.tamper_after else family.vspgeom_sha256),
            canonical_sha_after=family.canonical_sha256,
            feasible=True,
        )


def make_runner(tmp_path: Path, freeze_fn, solver_cls=FakeSolver, ledger=None):
    store = FreezeRecordStore(tmp_path / "freeze.jsonl")
    adapter = A1FreezeApiAdapter(freeze_fn, builder_code_sha256="b" * 64,
                                 freeze_api_sha256="f" * 64)
    service = FrozenPairService(adapter, store, tmp_path / "builds")
    solver = solver_cls(store)
    runner = P2AV2Runner(service, solver, store,
                         ledger_reader=ledger, max_starts=MAX_STARTS)
    return store, service, solver, runner


def _preflight_manifest() -> dict:
    return {"cases": [
        {"case_id": "PRE-%02d" % (i + 1), "design_hash": "d%d" % i,
         "family_label": "543x472", "expected_polar_sha256": "polar-%d" % i,
         "mesh_family": [543, 472], "files": {}}
        for i in range(2)
    ]}


def test_preflight_requires_two_cases():
    with pytest.raises(ValueError):
        PreflightVerifier({"cases": [{"case_id": "PRE-01"}]})


def test_preflight_fail_blocks_main_batch_with_zero_starts(tmp_path):
    calls = {"n": 0}

    def replay(case):
        calls["n"] += 1
        ok = case["case_id"] != "PRE-02"
        return {"status": "SOLVED_VALID" if ok else "SOLVER_FAILED",
                "polar_sha256": case["expected_polar_sha256"], "mesh_family": [543, 472],
                "physical_solver_starts": 1 if ok else 0}

    def freeze_fn(**kw):
        raise AssertionError("preflight must run before any freeze")

    store, service, solver, runner = make_runner(tmp_path, freeze_fn)
    batch = P2AV2Batch(runner, preflight=PreflightVerifier(_preflight_manifest(), replay_fn=replay))
    out = batch.run_batch({arm: (lambda a, i, r: x12(0.3)) for arm in ("BO", "DE", "PSO", "ABO", "ADE", "APSO")},
                          budget_designs=1)
    assert out["status"].startswith("STOP_PREFLIGHT_")
    assert out["total_starts"] == 0
    assert solver.calls == []
    assert store.records() == []
    assert out["preflight"]["physical_call_count"] == 1  # only the one case that actually started
    assert out["preflight"]["counted_in_e1_e6"] is False


def test_preflight_pass_byte_allows_and_marks_replay(tmp_path):
    def replay(case):
        return {"status": "SOLVED_VALID", "polar_sha256": case["expected_polar_sha256"],
                "mesh_family": [543, 472], "physical_solver_starts": 1}
    result = PreflightVerifier(_preflight_manifest(), replay_fn=replay).run()
    assert result["overall"] == "PREFLIGHT_PASS_BYTE"
    assert result["main_batch_may_start"] is True
    assert result["counted_in_e1_e6"] is False
    assert result["backend"] == "REPLAY_B2"
    assert result["physical_call_count"] == 2
    assert all(row["status"] == "PASS_BYTE" for row in result["cases"])




def test_preflight_failure_reports_zero_physical_not_planned():
    """A case that failed before spawn must report 0 starts; planned is separate."""

    def replay(case):
        return {"status": "GEOMETRY_INVALID", "physical_solver_starts": 0}

    result = PreflightVerifier(_preflight_manifest(), replay_fn=replay).run()
    assert result["overall"] == "PREFLIGHT_FAIL"
    assert result["physical_call_count"] == 0
    assert result["planned_starts"] == 2
    assert result["physical_call_count_source"].startswith("sum of per-case")
    assert all(row["starts"] == 0 and row["planned_starts"] == 1 for row in result["cases"])


def test_preflight_bundle_manifest_sha256_is_file_sha(tmp_path: Path):
    """bundle_manifest_sha256 must be the file SHA bound by approval, not a canonical-JSON digest."""
    manifest = _preflight_manifest()
    raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    (tmp_path / "bundle_manifest.json").write_bytes(raw)
    result = PreflightVerifier(manifest, bundle_root=tmp_path).run()
    assert result["bundle_manifest_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["bundle_manifest_sha256_source"] == "FILE_BYTES"
    assert result["bundle_manifest_canonical_sha256"] != result["bundle_manifest_sha256"]


def test_preflight_numeric_requires_acceptance():
    def replay(case):
        return {"status": "SOLVED_VALID", "polar_sha256": "different",
                "mesh_family": [543, 472], "numeric_max_rel": 1e-10,
                "physical_solver_starts": 1}
    pending = PreflightVerifier(_preflight_manifest(), replay_fn=replay).run()
    assert pending["overall"] == "PREFLIGHT_PASS_NUMERIC_PENDING_ACCEPTANCE"
    assert pending["main_batch_may_start"] is False
    accepted = PreflightVerifier(_preflight_manifest(), replay_fn=replay,
                                 accept_numeric=True).run()
    assert accepted["overall"] == "PREFLIGHT_PASS_NUMERIC_ACCEPTED"
    assert accepted["main_batch_may_start"] is True


def test_append_only_record_before_first_start_has_arm_and_slot(tmp_path):
    freeze_calls = []

    def freeze_fn(**kw):
        freeze_calls.append(kw)
        return pair_record(kw["x12"])

    store, service, solver, runner = make_runner(tmp_path, freeze_fn)
    ev = runner.run_one(x12(0.2), 1)
    assert ev.status == "SOLVED_VALID"
    assert ev.starts == 2
    assert len(freeze_calls) == 1
    rec = store.get(design_hash(x12(0.2)))
    assert rec is not None
    assert rec["status"] == "PAIR_READY"
    assert rec["physical_call_count"] == 0
    assert rec["arm_id"] == "ALL_SIX_SHARED"
    assert rec["slot_id"] == "SHARED-" + design_hash(x12(0.2))
    assert rec["shared_by_arms"] == ["BO", "DE", "PSO", "ABO", "ADE", "APSO"]
    assert set(rec["families"]) == {"483x418", "543x472"}
    assert ev.freeze_record_sha256 == rec["record_hash"]


def test_freeze_once_reused_across_arms(tmp_path):
    calls = []
    fns = {"n": 0}

    def freeze_fn(**kw):
        fns["n"] += 1
        return pair_record(kw["x12"])

    store, service, solver, runner = make_runner(tmp_path, freeze_fn)
    batch = P2AV2Batch(runner)
    design = x12(0.4)
    r1 = batch.run_arm("BO", lambda a, i, r: design, budget_designs=1, initial_designs=[design])
    r2 = batch.run_arm("DE", lambda a, i, r: design, budget_designs=1, initial_designs=[design])
    assert r1.status == r2.status == "COMPLETED"
    assert fns["n"] == 1
    assert len(store.records()) == 1
    assert r2.evaluations[0].reused_frozen_pair is True
    assert r1.evaluations[0].reused_frozen_pair is False
    assert len(solver.calls) == 4


def test_void_design_is_global_and_consumes_one_reserve_group(tmp_path):
    void_x = x12(0.5)
    good_x = x12(0.6)
    vh = design_hash(void_x)

    def freeze_fn(**kw):
        return void_record(kw["x12"]) if kw["x12"] == void_x else pair_record(kw["x12"])

    store, service, solver, runner = make_runner(tmp_path, freeze_fn)
    batch = P2AV2Batch(runner)

    def proposal(arm, index, replacement):
        return good_x

    r1 = batch.run_arm("BO", proposal, budget_designs=1, initial_designs=[void_x])
    assert r1.status == "COMPLETED"
    assert r1.void_designs == 1
    assert r1.reserve_groups_used == 1
    assert batch.reserve.groups_used == 1

    r2 = batch.run_arm("DE", proposal, budget_designs=1, initial_designs=[void_x])
    assert r2.status == "COMPLETED"
    assert batch.reserve.groups_used == 1, "the same VOID design must not consume reserve twice"
    assert batch.voided_designs == {vh}
    assert store.get(vh)["status"] == "DESIGN_VOID"
    assert store.get(vh)["physical_call_count"] == 0


def test_ledger_budget_exhausted_is_read_only_and_zero_start(tmp_path):
    ledger_path = tmp_path / "solver_attempts.jsonl"
    ledger_path.write_text(json.dumps({"event": "start", "attempt_id": "a01",
                                       "physical_solver_starts": 1}) + "\n", encoding="utf-8")
    before = ledger_path.read_bytes()
    reader = A1LedgerReader(ledger_path)
    calls = []

    def freeze_fn(**kw):
        calls.append(kw)
        return pair_record(kw["x12"])

    store, service, solver, runner = make_runner(tmp_path, freeze_fn, ledger=reader)
    runner.max_starts = 1
    ev = runner.run_one(x12(0.7), 1)
    assert ev.status == "NOT_VALIDATED"
    assert ev.validation_error == "LEDGER_BUDGET_EXHAUSTED"
    assert ev.starts == 0
    assert solver.calls == []
    assert ledger_path.read_bytes() == before, "A2 must never write the A1 ledger"


def test_frozen_bytes_pre_post_sha_mismatch_fails_closed(tmp_path):
    class TamperingSolver(FakeSolver):
        def evaluate(self, family, dh, slot):
            result = super().evaluate(family, dh, slot)
            return SolverResult(**{**result.__dict__, "vspgeom_sha_after": "0" * 64})

    def freeze_fn(**kw):
        return pair_record(kw["x12"])

    store, service, solver, runner = make_runner(tmp_path, freeze_fn, solver_cls=TamperingSolver)
    ev = runner.run_one(x12(0.8), 1)
    assert ev.status == "NOT_VALIDATED"
    assert ev.validation_error == "FROZEN_BYTES_SHA_MISMATCH"


def test_primary_is_equal_weight_mean_cdi_and_secondary_is_descriptive(tmp_path):
    def freeze_fn(**kw):
        return pair_record(kw["x12"])

    store, service, solver, runner = make_runner(tmp_path, freeze_fn,
                                                 solver_cls=lambda s: FakeSolver(s, cdi=(0.02, 0.04)))
    ev = runner.run_one(x12(0.9), 1)
    assert ev.primary == pytest.approx(0.03)
    assert ev.secondary is not None and ev.secondary > 0
    assert set(ev.family_cdi) == {"f1", "f2"}


def test_build_package_end_to_end_zero_physical(tmp_path):
    from research.concorde_metaopt.dreal001.optimizers.p2a_v2 import (
        build_package, verify_package,
    )
    out = tmp_path / "DREAL001-P2A2R-20261111-01"
    built = build_package(out_dir=out)
    assert built["planned_starts"] == PLANNED_STARTS == 386
    assert built["max_starts"] == MAX_STARTS == 451
    assert built["physical_call_count"] == 0
    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    assert plan["window"]["token"] == WINDOW_TOKEN
    assert plan["budget_and_caps"]["planned_internal_cases"] == PLANNED_INTERNAL_CASES == 2702
    assert plan["matrix"]["reserve_starts"] == RESERVE_STARTS == 64
    assert plan["family_policy"]["arm_blind"] is True
    assert plan["evidence_gate"]["row_backend_required"] == "REAL_VSPAERO"
    assert plan["preflight"]["replay_physical"] is True
    assert plan["preflight"]["launch_kind"] == "REAL_REPLAY_B2"
    assert plan["preflight"]["replay_physical_starts_per_case"] == 1
    assert plan["preflight"]["replay_internal_cases_per_case"] == 7
    assert plan["preflight"]["replay_bundles"]["bundle_manifest_sha256"] == plan["preflight"]["sha256"]
    assert plan["preflight"]["replay_bundles"]["cases"]["PRE-01"]["family_role"] == "f2"
    assert plan["preflight"]["replay_bundles"]["cases"]["PRE-02"]["family_role"] == "f1"
    assert plan["preflight"]["cases"][0]["launch_kind"] == "REAL_REPLAY_B2"
    assert plan["preflight"]["replay_pass_authority"] == "A2_BATCH_ONLY"
    assert plan["evidence_gate"]["row_level_inheritance_allowed"] is False
    assert plan["caps_reconciliation"]["preflight_slots_count_as_starts"] is True
    assert plan["initial_designs"]["family_pairs"]["15"] == ["462x401", "546x472"]
    approval = json.loads((out / "approval.DRAFT.json").read_text(encoding="utf-8"))
    assert approval["approved"] is False
    assert approval["status"] == "DRAFT_AWAITING_LEAD_SIGNATURE"
    assert approval["reserve_starts"] == 64
    assert approval["replay_bundles"]["bundle_manifest_sha256"] == plan["preflight"]["sha256"]
    assert "PRE-03" not in approval["replay_bundles"]["cases"]
    assert set(approval["replay_bundles"]["cases"]) == {"PRE-01", "PRE-02"}
    assert approval["replay_bundles"]["cases"]["PRE-01"]["polar_sha256"] == "455082e2ac8029216a811c89aaa20b34fd9d73faa319eed23da5348e3de4bc87"
    coverage = approval["family_coverage"]["designs"]
    assert len(coverage) == 5  # 3 initial LHS + 2 archival preflight designs
    pre = {d["design_hash"]: d for d in coverage if d["source"] == "PREFLIGHT_BUNDLE_REPLAY"}
    assert set(pre) == {"8bd5a6c7c8311938", "bc52a54ecefaac4c"}
    assert pre["8bd5a6c7c8311938"]["family_labels"] == {"f1": "483x418", "f2": "543x472"}
    assert pre["bc52a54ecefaac4c"]["family_labels"] == {"f1": "483x418", "f2": "543x472"}
    for entry in coverage:
        assert isinstance(entry["family_labels"], dict)
        assert set(entry["family_labels"]) == {"f1", "f2"}
        assert entry["family_labels"] == entry["roles"]
    assert approval["freeze_api_sha256"] and approval["evaluator_code_sha256"]
    assert len(approval["a1_v1_2_code_sha"]) == 40 and approval["a1_v1_2_code_sha"] != approval["evaluator_code_sha256"]
    dry = json.loads((out / "dry_run.json").read_text(encoding="utf-8"))
    assert dry["status"] == "DRY_RUN_BLOCKED_NOT_APPROVED"
    assert dry["planned_starts"] == 386
    assert dry["cases_planned"] == 0
    assert dry["physical_call_count"] == 0
    assert dry["cases_emitted"] == 0 and dry["ledger_created"] is False
    ver = verify_package(out)
    assert ver["status"] == "PASS"
    assert ver["physical_call_count"] == 0


# ---------------------------------------------------------------------------
# A5 P2AV2-21/23/24/25 regression tests (2026-11-11)
# ---------------------------------------------------------------------------
def _row(**kwargs: object) -> dict:
    base = {"ts_utc": "2026-11-11T02:30:00Z", "batch_id": "DREAL001-P2-20261111-05"}
    base.update(kwargs)
    return base


def test_ledger_reader_pairs_by_case_id_and_counts_starts(tmp_path: Path) -> None:
    ledger = tmp_path / "solver_attempts.jsonl"
    ledger.write_text(
        "\n".join(json.dumps(r) for r in [
            _row(mode="RUNTIME", event="start", case_id="BO-aaa-f1", design_hash="aaa", family_role="f1"),
            _row(mode="RUNTIME", event="end", case_id="BO-aaa-f1", status="SOLVED_VALID",
                 physical_call_count=1, internal_solver_cases=7),
            _row(mode="RUNTIME", event="start", case_id="BO-aaa-f2", design_hash="aaa", family_role="f2"),
        ]) + "\n", encoding="utf-8")
    reader = A1LedgerReader(ledger)
    assert reader.count_starts() == 2          # event=="start", not physical_solver_starts
    audit = reader.audit()
    assert audit["pairing_key"] == "case_id"
    assert audit["paired"] is False  # one start has no end
    assert audit["unpaired_start_case_ids"] == ["BO-aaa-f2"]
    assert audit["unpaired_start_case_ids"] == ["BO-aaa-f2"]
    assert audit["physical_solver_starts"] == 2
    assert audit["internal_solver_cases"] is None
    assert audit["ledger_internal_cases_recorded"] == 7
    assert audit["attempt_id"].startswith("informational_only")
    assert audit["read_only"] is True


def test_ledger_reader_rejects_duplicate_case_id_starts(tmp_path: Path) -> None:
    ledger = tmp_path / "solver_attempts.jsonl"
    ledger.write_text(
        "\n".join(json.dumps(_row(event="start", case_id="BO-dup-f1")) for _ in range(2)) + "\n",
        encoding="utf-8")
    from research.concorde_metaopt.dreal001.optimizers.p2a_v2_runtime import LedgerReadError
    with pytest.raises(LedgerReadError):
        A1LedgerReader(ledger).audit()


def test_stop_report_repairs_only_genuinely_unpaired_starts(tmp_path: Path) -> None:
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = run_dir / "solver_attempts.jsonl"
    ledger.write_text("\n".join(json.dumps(r) for r in [
        _row(event="start", case_id="DE-aaa-f1", design_hash="aaa", family_role="f1"),
        _row(event="end", case_id="DE-aaa-f1", status="SOLVED_VALID", physical_call_count=1,
             internal_solver_cases=7),
        _row(event="start", case_id="DE-bbb-f2", design_hash="bbb", family_role="f2"),
    ]) + "\n", encoding="utf-8")
    report = ex._write_stop_report(run_dir, "arm", RuntimeError("boom"), arm_id="DE", ledger_path=ledger)
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    ends = [r for r in rows if r.get("event") == "end" and r.get("case_id") == "DE-bbb-f2"]
    assert len(ends) == 1
    assert ends[0]["status"] == "EXECUTOR_EXCEPTION"
    assert ends[0]["repair"] is True
    assert ends[0]["physical_call_count"] == 0      # no refund, no fabricated start
    assert len([r for r in rows if r.get("event") == "end" and r.get("case_id") == "DE-aaa-f1"]) == 1
    assert report["physical_solver_starts"] == 2    # actual ledger starts, never hard-coded 0
    assert report["internal_solver_cases"] is None
    assert report["ledger_internal_cases_recorded"] == 7
    assert report["pending_case_ids"] == ["DE-bbb-f2"]
    assert report["ledger_starts"] == 2 and report["ledger_ends"] == 2
    assert (run_dir / "stop_report.json").is_file()


def test_stop_report_without_start_never_fabricates_end(tmp_path: Path) -> None:
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = run_dir / "solver_attempts.jsonl"
    ledger.write_text("", encoding="utf-8")
    report = ex._write_stop_report(run_dir, "preflight", RuntimeError("x"), ledger_path=ledger)
    assert ledger.read_text(encoding="utf-8") == ""
    assert report["physical_solver_starts"] == 0
    assert report["pending_case_ids"] == []


def test_sref_resolver_resolves_new_design_before_solver(tmp_path: Path) -> None:
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex
    base = [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]
    seed = ex.build_sref_map(A1_ROOT, {"dh-base": base})
    resolver = ex.SrefResolver(A1_ROOT, seed)
    assert resolver.get("dh-base") == pytest.approx(seed["dh-base"])
    new = list(base)
    new[0] = float(new[0]) + 12.5                    # unseen design outside P2AFAM manifest
    value = resolver.note("dh-new", new)
    assert value is not None and value > 0
    assert resolver.get("dh-new") == pytest.approx(value)
    snap = resolver.snapshot()
    assert "dh-new" in snap and "dh-base" in snap
    assert snap["dh-new"] > 0


def test_final_run_manifest_issued_after_freezes(tmp_path: Path) -> None:
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    log = run_dir / "runtime" / "family_pair_manifest.append_only.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("", encoding="utf-8")
    approval = {"append_only_log_path": str(log), "batch_id": "DREAL001-P2-20261111-05",
                "policy_doc_sha256": "p" * 64, "builder_code_sha256": "b" * 64}
    manifest = ex._build_final_manifest(run_dir, approval, A1_ROOT)
    assert manifest["issued"] is True
    assert manifest["chain"]["valid"] is True
    assert manifest["append_only_log_sha256"]
    assert Path(manifest["path"]).is_file()
    assert manifest["designs_total"] == 0
    assert (run_dir / "final_run_manifest.json").is_file()


def test_sequential_evaluators_share_one_ledger_without_truncation(tmp_path: Path) -> None:
    """A1 evaluator holds an exclusive .lock; closing arm N lets arm N+1 write."""
    import sys
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex
    sys.dont_write_bytecode = True
    _, ev12, _ = ex._load_a1(A1_ROOT)
    manifest_path = A1_ROOT / "research" / "concorde_metaopt" / "dreal001" / "geometry" / "runs" / \
        "P2A_FAM_FEASIBILITY_20261111" / "family_pair_manifest.json"
    manifest = ev12.load_family_pair_manifest(manifest_path)
    sha = ev12.sha256_file(manifest_path)
    approval = {"approved": True, "batch_id": "DREAL001-P2-20261111-05", "max_starts": 64,
                "pair_manifest_sha256": sha,
                "family_coverage": {"pair_manifest_sha256": sha,
                                    "designs": [{"design_hash": "absent-design"}]}}
    ledger = tmp_path / "solver_attempts.jsonl"
    for arm in ("BO", "DE", "PSO"):
        ev = ev12.TwoFamilyEvaluator(manifest, approval, batch_id="DREAL001-P2-20261111-05",
                                     max_starts=64, run_dir=tmp_path / arm,
                                     manifest_source=manifest_path, mock=True,
                                     ledger_path=ledger)
        ev.close()
    assert list(tmp_path.rglob("*.lock")) == []
    assert not (tmp_path / "solver_attempts.jsonl.lock").exists()   # lock released, never leaked
    assert ledger.exists() or not ledger.exists()                   # no truncation/rebuild by close



# ---------------------------------------------------------------------------
# P2AV2-21 follow-up: global reserve scope, internal accounting, S1 stop.
# ---------------------------------------------------------------------------

def _freeze_void_for(void_x):
    target = design_hash(void_x)

    def freeze_fn(**kwargs):
        if kwargs.get("design_hash") == target:
            return void_record(kwargs["x12"])
        return pair_record(kwargs["x12"])

    return freeze_fn


def test_reserve_pool_shared_across_arms_same_void_design(tmp_path):
    void_x = x12(0.2)
    pair_x = x12(0.3)
    store, service, solver, runner = make_runner(tmp_path, _freeze_void_for(void_x))
    pool = ReservePool()
    seen: set[str] = set()
    batch_bo = P2AV2Batch(runner, reserve_pool=pool, voided_designs=seen)
    batch_de = P2AV2Batch(runner, reserve_pool=pool, voided_designs=seen)

    def proposal(arm, index, replacement):
        return void_x if replacement == 0 else pair_x

    bo = batch_bo.run_arm("BO", proposal, budget_designs=1)
    de = batch_de.run_arm("DE", proposal, budget_designs=1)
    assert bo.status == "COMPLETED" and de.status == "COMPLETED"
    # one globally voided design costs exactly one group, not one per arm
    assert pool.groups_used == 1
    assert pool.starts_used == 2
    assert bo.reserve_groups_used == 1
    assert de.reserve_groups_used == 0


def test_reserve_global_cap_32_across_arms(tmp_path):
    counter = {"n": 0}

    def proposal(arm, index, replacement):
        counter["n"] += 1
        return x12(0.4 + 0.001 * counter["n"])

    def freeze_fn(**kwargs):
        return void_record(kwargs["x12"])

    store, service, solver, runner = make_runner(tmp_path, freeze_fn)
    pool = ReservePool()
    batch = P2AV2Batch(runner, reserve_pool=pool, voided_designs=set())
    result = batch.run_arm("BO", proposal, budget_designs=1)
    assert result.status == "NOT_VALIDATED_RESERVE_EXHAUSTED"
    assert pool.groups_used == 32
    assert pool.groups_left == 0


class SlotStatusSolver:
    def __init__(self, store, statuses):
        self.store = store
        self.statuses = dict(statuses)

    def evaluate(self, family, dh, slot):
        assert self.store.get(dh) is not None
        status = self.statuses[slot]
        return SolverResult(
            status=status,
            cdi=0.02 if status == "SOLVED_VALID" else None,
            cl=0.2 if status == "SOLVED_VALID" else None,
            physical_solver_starts=1, internal_solver_cases=7,
            vspgeom_sha_before=family.vspgeom_sha256,
            vspgeom_sha_after=family.vspgeom_sha256,
            canonical_sha_after=family.canonical_sha256, feasible=True)


def test_failed_second_family_starts_and_internal_are_preserved(tmp_path):
    store, service, solver, runner = make_runner(
        tmp_path, lambda **kw: pair_record(kw["x12"]),
        solver_cls=lambda st: SlotStatusSolver(
            st, {"f1": "SOLVED_VALID", "f2": "SOLVER_FAILED"}))
    evaluation = runner.run_one(x12(0.5), 1)
    assert evaluation.status == "SOLVER_NON_SOLVED"
    assert evaluation.starts == 2                     # both starts billed
    assert evaluation.internal_solver_cases == 14     # 7 + 7
    assert evaluation.failed_family["family_slot"] == "f2"
    assert evaluation.failed_family["internal_solver_cases"] == 7
    counts = summarize_evaluations({"BO": {"evaluations": [asdict(evaluation)]}})
    assert counts["main_starts"] == 2
    assert counts["record_internal_cases"] == 14
    assert counts["record_internal_cases_status"] == "COMPUTED_FROM_EVALUATIONS"


def test_failed_first_family_internal_is_seven(tmp_path):
    store, service, solver, runner = make_runner(
        tmp_path, lambda **kw: pair_record(kw["x12"]),
        solver_cls=lambda st: SlotStatusSolver(
            st, {"f1": "SOLVER_FAILED", "f2": "SOLVED_VALID"}))
    evaluation = runner.run_one(x12(0.6), 1)
    assert evaluation.status == "SOLVER_NON_SOLVED"
    assert evaluation.starts == 1
    assert evaluation.internal_solver_cases == 7
    assert evaluation.failed_family["family_slot"] == "f1"


def test_summary_internal_not_computable_never_written_as_zero():
    unknown = DesignEvaluation(
        design_index=1, design_hash="d" * 16, primary=None, secondary=None,
        feasible=False, status="NOT_VALIDATED", starts=1,
        family_cdi={}, family_labels={}, family_sref_m2={},
        internal_solver_cases=None)
    counts = summarize_evaluations({"BO": {"evaluations": [asdict(unknown)]}})
    assert counts["record_internal_cases"] is None
    assert counts["record_internal_cases_status"] == "NOT_COMPUTABLE"


def test_s1_stops_after_first_non_completed_arm():
    """The executor must break, write stop_report(phase=s1) and not start arm 2."""
    import inspect
    from research.concorde_metaopt.dreal001.optimizers import p2a_v2_executor as ex

    source = inspect.getsource(ex)
    assert '_write_stop_report(run_dir, "s1"' in source
    idx = source.index('_write_stop_report(run_dir, "s1"')
    assert "break" in source[idx:idx + 500]


def test_start_accounting_matches_ledger_after_failed_start():
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex
    # preflight 3 starts pass, then one main start fails and is still charged.
    acct = ex.summarize_start_accounting(4, 3)
    assert acct["preflight_starts"] == 3
    assert acct["main_starts"] == 1
    assert acct["total_starts"] == 4
    assert acct["total_ledger_starts"] == 4
    assert acct["preflight_starts"] + acct["main_starts"] == acct["total_starts"]


def test_start_accounting_never_reports_zero_when_ledger_has_starts():
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex
    acct = ex.summarize_start_accounting(6, 3)
    assert acct["total_starts"] == 6
    assert acct["main_starts"] == 3


def test_batch_summary_start_counts_are_ledger_derived():
    import inspect
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex
    src = inspect.getsource(ex)
    assert "summarize_start_accounting(ledger.count_starts(), preflight_ledger_starts)" in src
    assert "preflight_ledger_starts = ledger.count_starts()" in src
    assert 'int(pre.get("physical_call_count")' not in src

def test_approval_family_labels_parse_in_a1_evaluator(tmp_path):
    """Regression: A1 evaluator_v12._family_role_map requires family_labels as a mapping."""
    import sys

    from research.concorde_metaopt.dreal001.optimizers.p2a_v2 import build_package
    from research.concorde_metaopt.dreal001.optimizers.p2a_v2_common import A1_PAIR_MANIFEST_PATH

    out = tmp_path / "DREAL001-P2A2R-20261111-01"
    build_package(out_dir=out)
    approval = json.loads((out / "approval.DRAFT.json").read_text(encoding="utf-8"))
    for entry in approval["family_coverage"]["designs"]:
        assert isinstance(entry["family_labels"], dict)
        assert set(entry["family_labels"]) == {"f1", "f2"}

    if not (A1_ROOT / "research/concorde_metaopt/dreal001/geometry/evaluator_v12.py").is_file():
        pytest.skip("A1 worktree not available")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(A1_ROOT))
    import research.concorde_metaopt.dreal001 as dreal001

    candidate = str(A1_ROOT / "research/concorde_metaopt/dreal001")
    if candidate not in dreal001.__path__:
        dreal001.__path__.append(candidate)
    from research.concorde_metaopt.dreal001.geometry.evaluator_v12 import _family_role_map

    manifest = json.loads(Path(A1_PAIR_MANIFEST_PATH).read_text(encoding="utf-8"))
    records = manifest["records"]
    assert len(records) == 119
    checked = 0
    for record in records:
        families = record.get("families") or {}
        if len(families) != 2:
            continue
        labels = sorted(families, key=lambda lab: (int(lab.split("x")[0]), int(lab.split("x")[1])))
        roles = _family_role_map({"family_labels": {"f1": labels[0], "f2": labels[1]}}, families)
        assert roles == {"f1": labels[0], "f2": labels[1]}
        assert set(roles.values()) == set(families)
        checked += 1
    assert checked == 119


# ---------------------------------------------------------------------------
# R2 minimal execution-layer fixes: solver geometry alias, preflight internal
# cases, per-case physical_call_count, R2 window constants.
# ---------------------------------------------------------------------------
def _r2_scratch():
    """Return one fresh single-level scratch case dir.

    The DSH/Windows sandbox denies mkdir below a directory created earlier in the
    same process, so tests use unique leaves under the existing scratch root.
    """
    import shutil
    import uuid
    root = Path(__file__).resolve().parents[3] / "research" / "concorde_metaopt" / ".pytest_scratch"
    root.mkdir(parents=True, exist_ok=True)
    return root / ("r2-" + uuid.uuid4().hex[:12]), shutil


def test_r2_solver_geometry_alias_copies_model_bytes():
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex

    case_dir, shutil = _r2_scratch()
    try:
        case_dir.mkdir()
        geom, vkey = b"VSPGEOM-MODEL-BYTES", b"VKEY-MODEL-BYTES"
        (case_dir / "model.vspgeom").write_bytes(geom)
        (case_dir / "model.vkey").write_bytes(vkey)

        info = ex._ensure_solver_geometry_alias(case_dir, "concorde_baseline")
        assert (case_dir / "concorde_baseline.vspgeom").read_bytes() == geom
        assert (case_dir / "concorde_baseline.vkey").read_bytes() == vkey
        assert info["vspgeom"]["copied"] is True and info["vkey"]["copied"] is True
        assert info["vspgeom"]["sha256"] == hashlib.sha256(geom).hexdigest()
        # model.* source bytes are never modified by the alias copy
        assert (case_dir / "model.vspgeom").read_bytes() == geom
        assert (case_dir / "model.vkey").read_bytes() == vkey
        # Idempotent when the existing alias matches the source bytes.
        again = ex._ensure_solver_geometry_alias(case_dir, "concorde_baseline")
        assert again["vspgeom"]["copied"] is False and again["vkey"]["copied"] is False
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


def test_r2_solver_geometry_alias_mismatch_fails_closed():
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex

    case_dir, shutil = _r2_scratch()
    try:
        case_dir.mkdir()
        (case_dir / "model.vspgeom").write_bytes(b"good-geom")
        (case_dir / "model.vkey").write_bytes(b"good-vkey")
        (case_dir / "concorde_baseline.vspgeom").write_bytes(b"stale-geom")
        with pytest.raises(ex.ExecutorRefused):
            ex._ensure_solver_geometry_alias(case_dir, "concorde_baseline")
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


def test_r2_solver_geometry_alias_missing_source_fails_closed():
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex

    case_dir, shutil = _r2_scratch()
    case_dir2, _ = _r2_scratch()
    try:
        case_dir.mkdir()
        # Alias exists but model.* is absent: bytes cannot be verified -> refuse.
        (case_dir / "concorde_baseline.vspgeom").write_bytes(b"orphan-geom")
        with pytest.raises(ex.ExecutorRefused):
            ex._ensure_solver_geometry_alias(case_dir, "concorde_baseline")
        case_dir2.mkdir()
        (case_dir2 / "model.vkey").write_bytes(b"vkey")
        with pytest.raises(ex.ExecutorRefused):
            ex._ensure_solver_geometry_alias(case_dir2, "concorde_baseline")
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)
        shutil.rmtree(case_dir2, ignore_errors=True)


def test_r2_preflight_record_internal_counts_records_not_zero():
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex

    pre = {"cases": [
        {"case_id": "PRE-01", "starts": 1, "internal_cases": 7},
        {"case_id": "PRE-02", "starts": 1, "internal_cases": 7},
    ]}
    assert ex._preflight_record_internal(pre) == 14
    assert ex._preflight_record_internal_status(pre) == "COMPUTED_FROM_PREFLIGHT_RECORDS"
    # A charged start with unknown internal count is NOT_COMPUTABLE, not 0.
    unknown = {"cases": [{"case_id": "PRE-01", "starts": 1, "internal_cases": None}]}
    assert ex._preflight_record_internal(unknown) is None
    assert ex._preflight_record_internal_status(unknown) == "NOT_COMPUTABLE"
    # Cases that never started are not charged at all.
    assert ex._preflight_record_internal({"cases": [{"case_id": "PRE-01", "starts": 0}]}) == 0


def test_r2_preflight_per_case_physical_call_count():
    def replay(case):
        # R1-style record: physical_solver_starts present, physical_call_count absent.
        return {"status": "SOLVED_VALID", "polar_sha256": case["expected_polar_sha256"],
                "mesh_family": [543, 472], "physical_solver_starts": 1,
                "internal_solver_cases": 7}

    result = PreflightVerifier(_preflight_manifest(), replay_fn=replay).run()
    assert result["overall"] == "PREFLIGHT_PASS_BYTE"
    assert [row["physical_call_count"] for row in result["cases"]] == [1, 1]
    assert result["physical_call_count"] == 2
    assert result["physical_call_count_source"].startswith("sum of per-case")


def test_r6_window_constants_cover_the_authorized_window():
    from research.concorde_metaopt.dreal001.optimizers import p2a_v2_common as common

    assert common.WINDOW_START_UTC == "2026-11-11T11:00:00Z"
    assert common.WINDOW_END_UTC == "2026-11-11T15:00:00Z"
    assert common.WINDOW_TOKEN == "WINDOW_OK-P2AV2R6-20261111T1100Z-1500Z"
    assert common.RUN_ID == "DREAL001-P2A2R6-20261111-01"
    assert common.BATCH_ID == "DREAL001-P2-20261111-11"
    assert common.R1_APPROVAL_SHA256 == "9e5c29b0ac482f36dc0d9bbe694a94afb7a3cf4a8557b549919dbe180cfe9b9b"
    assert common.R2_APPROVAL_SHA256 == "eee7868a4ea3892a5df1a8d51595e1b8dee78c34996d5fd9ccf2293363e2808f"
    assert common.R3_APPROVAL_SHA256 == "18865f8f4e8206135f1673e5f8706bd201465bc617473c604b262ba440dd7f60"
    assert common.R4_APPROVAL_SHA256 == "6e2aebcf7b5cbced471d0dfc6d7200d761e990660ac6f384517940600a2063ab"
    assert common.R4_APPROVAL_BYTES == 59125
    assert common.R5_APPROVAL_SHA256 == "ca0bdc7b34bc29dc0a9e8a2157da28069be5279ca4a59d3ad5194e9646b528bf"
    assert common.R5_APPROVAL_BYTES == 63264
    assert common.R6_AMENDMENT_SEQ == 6
    assert common.R6_AMENDMENT_ACTION == "R6_DESIGN_SPACE_BINDING_FIX"
    assert common.R6_CUMULATIVE_STARTS == 433
    assert common.R6_CUMULATIVE_INTERNAL_CASES == 3043



class _FakeDesignSpace:
    """Unit<->physical mapping mirroring the A1 DesignSpace API shape."""

    _BOUNDS = {
        "wing_area": (100.0, 500.0), "aspect_ratio": (1.2, 4.0),
        "sweep_1": (10.0, 70.0), "sweep_2": (5.0, 60.0), "sweep_3": (0.0, 55.0),
        "span_location_2": (0.1, 0.9), "span_location_3": (0.1, 0.9),
        "chord_ratio_2": (0.2, 0.8), "chord_ratio_3": (0.2, 0.8),
        "tip_twist": (-6.0, 6.0), "vertical_tail_area": (20.0, 90.0),
        "vertical_tail_sweep_delta": (0.0, 30.0),
    }

    def to_unit_interval(self, physical):
        return [float((physical[name] - lo) / (hi - lo))
                for name, (lo, hi) in self._BOUNDS.items()]

    def from_unit_interval(self, fractions):
        return {name: float(lo + float(u) * (hi - lo))
                for (name, (lo, hi)), u in zip(self._BOUNDS.items(), fractions)}


def test_r5_x12_unit_roundtrip_is_exact_and_physical():
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex

    space = _FakeDesignSpace()
    x12 = [362.2679593707106, 2.5, 40.0, 30.0, 20.0, 0.4, 0.5, 0.45, 0.55, -1.5, 55.0, 12.0]
    unit = ex.x12_to_unit(space, x12)
    assert len(unit) == 12 and all(0.0 <= u <= 1.0 for u in unit)
    assert unit[0] == pytest.approx((362.2679593707106 - 100.0) / 400.0)
    back = ex.unit_to_x12(space, unit)
    for a, b in zip(x12, back):
        assert abs(a - b) <= 1e-12
    # A physical x12 is not a unit vector: the R4 bug must be impossible.
    assert not all(0.0 <= v <= 1.0 for v in back)


def test_r5_boundary_fails_closed_on_bad_domains():
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex

    space = _FakeDesignSpace()
    with pytest.raises(ex.ExecutorRefused):
        ex.x12_to_unit(space, [1.0] * 12)  # unit-box vector is not a physical x12 here
    with pytest.raises(ex.ExecutorRefused):
        ex.unit_to_x12(space, [1.5] + [0.5] * 11)
    with pytest.raises(ex.ExecutorRefused):
        ex.unit_to_x12(space, [float("nan")] + [0.5] * 11)
    with pytest.raises(ex.ExecutorRefused):
        ex.x12_to_unit(space, [float("inf")] + [1.0] * 11)


def test_r5_executor_source_has_no_physical_clip_seed():
    import inspect

    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex

    src = inspect.getsource(ex)
    assert "np.clip(np.asarray(x12" not in src
    assert "initial_unit = [x12_to_unit(design_space, x12) for x12 in initial_x12]" in src
    assert "return unit_to_x12(design_space, current_units[arm_id])" in src

def test_r3_real_spawn_success_status_is_solved_valid(monkeypatch):
    """R3 fix: a successful real spawn must report the A1 vocabulary SOLVED_VALID."""
    import research.concorde_metaopt.dreal001.optimizers.p2a_v2_executor as ex

    case_dir, shutil = _r2_scratch()
    try:
        case_dir.mkdir()
        exe = case_dir / "vspaero.exe"
        exe.write_bytes(b"fake-vspaero")
        expected_sha = "a" * 64
        polar = case_dir / "concorde_baseline.polar"
        polar.write_text("fake polar", encoding="ascii")

        monkeypatch.setattr(ex, "_load_a1", lambda root: (None, None, None))
        monkeypatch.setattr(ex, "_write_runtime_solver_inputs", lambda *a, **k: None)
        monkeypatch.setattr(ex, "_ensure_solver_geometry_alias", lambda *a, **k: {})
        monkeypatch.setattr(ex, "sha256_file", lambda path: expected_sha)
        monkeypatch.setattr(ex, "_polar_objective", lambda *a, **k: {
            "objective": 1.0, "results": {}, "lift": {"matched": True, "rel_error": 0.0}})

        class Proc:
            returncode = 0

            def communicate(self, timeout=None):
                return "solver ok", None

        monkeypatch.setattr(ex.subprocess, "Popen", lambda *a, **k: Proc())
        spawn = ex._real_spawn_factory(case_dir, case_dir, {"dh": 1.0}, solver_binding={
            "exe_path": str(exe), "exe_sha256": expected_sha})
        out = spawn({"case_dir": str(case_dir), "design_hash": "dh", "basename": "concorde_baseline"})
        assert out["status"] == "SOLVED_VALID"
        assert out["objective"] == 1.0

        class BadProc:
            returncode = 1

            def communicate(self, timeout=None):
                return "boom", None

        monkeypatch.setattr(ex.subprocess, "Popen", lambda *a, **k: BadProc())
        polar.unlink()
        bad = spawn({"case_dir": str(case_dir), "design_hash": "dh", "basename": "concorde_baseline"})
        assert bad["status"] == "SOLVER_FAILED"
    finally:
        shutil.rmtree(case_dir, ignore_errors=True)


def _r3_replay_with_status(status):
    def replay(case):
        return {"status": status, "polar_sha256": case["expected_polar_sha256"],
                "mesh_family": [543, 472], "physical_solver_starts": 1,
                "internal_solver_cases": 7}
    return replay


def test_r3_preflight_verifier_accepts_solved_valid_but_rejects_plain_solved():
    ok = PreflightVerifier(_preflight_manifest(),
                           replay_fn=_r3_replay_with_status("SOLVED_VALID")).run()
    assert ok["overall"] == "PREFLIGHT_PASS_BYTE"
    assert [row["status"] for row in ok["cases"]] == ["PASS_BYTE", "PASS_BYTE"]
    bad = PreflightVerifier(_preflight_manifest(),
                            replay_fn=_r3_replay_with_status("SOLVED")).run()
    assert bad["overall"] != "PREFLIGHT_PASS_BYTE"
    assert all(row["status"] == "FAIL" and row["is_hard_fail"] is True
               for row in bad["cases"])



# ---------------------------------------------------------------------------
# R7 stage D: observe() design_hash string-misuse regression (zero physical)
# ---------------------------------------------------------------------------

R7_ARMS = ("BO", "DE", "PSO")
R7_R6_RUN_DIR = (Path(__file__).resolve().parents[3]
                 / "research" / "concorde_metaopt" / "dreal001" / "runs"
                 / "DREAL001-P2A2R6-20261111-01")
R7_DESIGN_SPACE_MODULE = "research.concorde_metaopt.aircraft.design_space"


class _R7FakeEvaluation:
    """Minimal evaluation stand-in: no solver process is ever started."""

    def __init__(self, status: str, primary=None, feasible: bool = False) -> None:
        self.status = status
        self.primary = primary
        self.feasible = feasible


def _r7_load_a1_space():
    """Load the frozen A1 design_space module under its canonical name.

    The A2 tree ships its own (older) design_space.py; the executor must bind
    the A1 frozen module.  This mirrors the R6 launcher preload (zero physical)
    and restores sys.modules afterwards so other tests are unaffected.
    """
    import importlib
    import importlib.util
    import sys

    a1_root = A1_ROOT
    ds_path = a1_root / "research" / "concorde_metaopt" / "aircraft" / "design_space.py"
    if not ds_path.is_file():
        pytest.skip("A1 design_space.py not found: %s" % ds_path)
    parent = importlib.import_module("research.concorde_metaopt.aircraft")
    saved_module = sys.modules.get(R7_DESIGN_SPACE_MODULE)
    had_attr = hasattr(parent, "design_space")
    saved_attr = getattr(parent, "design_space", None)
    spec = importlib.util.spec_from_file_location(R7_DESIGN_SPACE_MODULE, ds_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[R7_DESIGN_SPACE_MODULE] = module
    try:
        spec.loader.exec_module(module)
        setattr(parent, "design_space", module)
        from research.concorde_metaopt.dreal001.optimizers import p2a_v2_executor as ex
        space, binding = ex._load_a1_design_space(a1_root)
    finally:
        if saved_module is not None:
            sys.modules[R7_DESIGN_SPACE_MODULE] = saved_module
        else:
            sys.modules.pop(R7_DESIGN_SPACE_MODULE, None)
        if had_attr and saved_attr is not None:
            setattr(parent, "design_space", saved_attr)
        elif not had_attr:
            try:
                delattr(parent, "design_space")
            except AttributeError:
                pass
    return space, binding


def _r7_initial_x12s():
    manifest = R7_R6_RUN_DIR / "initial_designs_manifest.json"
    if not manifest.is_file():
        pytest.skip("R6 initial designs manifest missing: %s" % manifest)
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    designs = doc.get("designs") or doc.get("initial_designs") or []
    x12s = [list(map(float, rec["x12"])) for rec in designs if isinstance(rec.get("x12"), list)]
    if len(x12s) != 3 or any(len(v) != 12 for v in x12s):
        pytest.skip("R6 initial manifest does not expose three 12D physical x12 vectors")
    return x12s


@pytest.mark.parametrize("arm", R7_ARMS)
def test_r7_observe_chain_does_not_raise_design_hash_valueerror(arm: str) -> None:
    from research.concorde_metaopt.dreal001.optimizers import p2a_v2_executor as ex
    from research.concorde_metaopt.dreal001.optimizers.p2a_v2_runtime import canonical_x12

    space, binding = _r7_load_a1_space()
    assert binding["physical_call_count"] == 0
    units = [ex.x12_to_unit(space, v) for v in _r7_initial_x12s()]
    assert all(len(u) == 12 for u in units)

    engine = ex.ProposalEngine(arm, seed=ex.SEED, adaptive=False)
    engine.seed_initial(units)
    for index in (1, 2, 3):
        u = list(map(float, engine.propose(arm, index, 1)))
        assert len(u) == 12
        engine.observe(u, _R7FakeEvaluation("LIFT_MATCH_FAILED"))

    if arm == "DE":
        # observe() pre-populates the population with the three seed designs
        # only, while DE needs >=4 candidates; pad the population directly so
        # the DE propose/observe key paths are exercised (latent limitation
        # reported separately in the stage-D memo, not changed here).
        while len(engine.population) < 5:
            engine.population.append({"u": engine.rng.random(12),
                                      "primary": None, "feasible": False})

    u4 = list(map(float, engine.propose(arm, 4, 1)))
    assert len(u4) == 12
    # The pre-R7 code called design_hash(canonical_x12(u)) here; canonical_x12
    # returns a string and design_hash asserts len(x12) == 12, so it always
    # raised.  This keeps a regression witness for that exact signature.
    with pytest.raises(ValueError, match="x12 must have exactly 12 values"):
        design_hash(canonical_x12(u4))
    engine.observe(u4, _R7FakeEvaluation("SOLVED_VALID", primary=130.0))

    u5 = list(map(float, engine.propose(arm, 5, 1)))
    assert len(u5) == 12
    engine.observe(u5, _R7FakeEvaluation("SOLVED_VALID", primary=123.456))


def test_r7_executor_has_no_design_hash_string_misuse() -> None:
    from research.concorde_metaopt.dreal001.optimizers import p2a_v2_executor as ex
    from research.concorde_metaopt.dreal001.optimizers.p2a_v2_runtime import canonical_x12

    src = Path(ex.__file__).read_text(encoding="utf-8")
    assert "design_hash(canonical_x12" not in src
    assert "design_hash(u)" in src
    assert not hasattr(ex, "canonical_x12")
    assert len(design_hash([0.5] * 12)) == 16
    with pytest.raises(ValueError, match="x12 must have exactly 12 values"):
        design_hash(canonical_x12([0.5] * 12))


# ---------------------------------------------------------------------------
# R9: prefrozen manifest family rows may be flat (A2 initial manifest) or nested
# (A1 pair manifest).  Both must parse; missing sibling files and tampered
# bytes must fail closed with zero physical calls.
# ---------------------------------------------------------------------------
R9_RUN_DIR = Path(__file__).resolve().parents[3] / "research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R9-20261111-01"
R9_A1_PAIR_MANIFEST = A1_ROOT / "research/concorde_metaopt/dreal001/geometry/runs/P2A_FAM_FEASIBILITY_20261111/family_pair_manifest.json"
R9_FROZEN_KEYS = ("frozen_vspgeom_path", "frozen_vspgeom_sha256", "frozen_vspgeom_bytes",
                  "frozen_vkey_sha256", "frozen_vsp3_sha256", "canonical_mesh_sha256")


def test_r9_family_frozen_payload_flat_and_nested():
    from research.concorde_metaopt.dreal001.optimizers import p2a_v2_runtime as rt
    flat = {"frozen_vspgeom_sha256": "a", "canonical_mesh_sha256": "b"}
    assert rt.family_frozen_payload(flat) == flat
    nested = {"frozen": {"frozen_vspgeom_sha256": "a"}, "attempts": 2}
    assert rt.family_frozen_payload(nested) == {"frozen_vspgeom_sha256": "a"}
    assert rt.family_frozen_payload(None) == {}


def _r9_mesh_identity():
    import importlib.util
    src = A1_ROOT / "research/concorde_metaopt/dreal001/geometry/mesh_identity.py"
    spec = importlib.util.spec_from_file_location("r9_a1_mesh_identity", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _r9_gate(manifest, root, hashes):
    import sys
    from research.concorde_metaopt.dreal001.optimizers import p2a_v2_executor as ex
    from research.concorde_metaopt.dreal001.optimizers import p2a_v2_runtime as rt

    class _DummyAdapter:
        builder_code_sha256 = "0" * 64

        def build(self, *a, **k):
            raise RuntimeError("BUILD_MUST_NOT_BE_CALLED")

    root.mkdir(parents=True, exist_ok=True)
    (root / "runtime").mkdir(exist_ok=True)
    store = rt.FreezeRecordStore(path=None, in_memory=True)
    service = rt.FrozenPairService(_DummyAdapter(), store, root / "runtime" / "designs",
                                   prefrozen_manifest=manifest, static_index_hashes=hashes,
                                   describe_mesh=_r9_mesh_identity().describe_mesh)
    return ex._prefrozen_reuse_gate(root, service, manifest, hashes)


def test_r9_prefrozen_gate_flat_nested_and_fail_closed_matrix():
    import json
    import shutil

    initial = json.loads((R9_RUN_DIR / "initial_designs_manifest.json").read_text(encoding="utf-8"))
    pm = json.loads(R9_A1_PAIR_MANIFEST.read_text(encoding="utf-8"))
    hashes = sorted({str(r.get("design_hash")) for r in pm["records"] if r.get("design_hash")})
    assert len(hashes) == 119
    base, _shutil = _r2_scratch()

    gate = _r9_gate(initial, base / "flat", hashes)
    assert gate["status"] == "PREFROZEN_REUSE_GATE_PASS"
    assert gate["all_consistent"] is True
    assert gate["static_index_count"] == 119
    assert gate["freeze_builder_invocations"] == 0
    assert [d["ok"] for d in gate["designs"]] == [True, True, True]

    nested = json.loads(json.dumps(initial))
    for design in nested["designs"]:
        for label, row in list(design["families"].items()):
            design["families"][label] = {"frozen": {k: row.get(k) for k in R9_FROZEN_KEYS}, "attempts": 0}
    gate2 = _r9_gate(nested, base / "nested", hashes)
    assert gate2["status"] == "PREFROZEN_REUSE_GATE_PASS"

    d15 = [d for d in nested["designs"] if d["design_index"] == 15][0]
    label = sorted(d15["families"])[0]
    row = d15["families"][label]["frozen"]
    srcdir = Path(row["frozen_vspgeom_path"]).parent

    only_geom = base / "missing_vkey"
    only_geom.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(row["frozen_vspgeom_path"], only_geom / "model.vspgeom")
    bad = json.loads(json.dumps(nested))
    [d for d in bad["designs"] if d["design_index"] == 15][0]["families"][label]["frozen"]["frozen_vspgeom_path"] = str(only_geom / "model.vspgeom")
    with pytest.raises(Exception):
        _r9_gate(bad, base / "case_missing", hashes)

    tampered = base / "tampered"
    tampered.mkdir(parents=True, exist_ok=True)
    for name in ("model.vspgeom", "model.vkey", "model.vsp3"):
        shutil.copyfile(srcdir / name, tampered / name)
    raw = bytearray((tampered / "model.vsp3").read_bytes())
    raw[0] ^= 0xFF
    (tampered / "model.vsp3").write_bytes(bytes(raw))
    bad2 = json.loads(json.dumps(nested))
    [d for d in bad2["designs"] if d["design_index"] == 15][0]["families"][label]["frozen"]["frozen_vspgeom_path"] = str(tampered / "model.vspgeom")
    with pytest.raises(Exception):
        _r9_gate(bad2, base / "case_tamper", hashes)
