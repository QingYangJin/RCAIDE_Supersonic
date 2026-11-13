"""Unit tests for the M0-R task-capable evaluator (zero physics).

These tests exercise only pure functions and file-local fixtures.  They never
import OpenVSP, never start vspaero.exe and never touch the frozen F1R2/F2R2
run directories.  The atmosphere / task / deck / polar / accounting contracts
are the ones A2's M1 runner will consume.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import research.concorde_metaopt.dreal001.m1.task_evaluator as te


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def task(task_id: str = "T18K_M202_CL017") -> te.TaskDefinition:
    for item in te.TASK_DEFINITIONS:
        if item.task_id == task_id:
            return item
    raise AssertionError("unknown task " + task_id)


def make_spec(task_id: str = "T18K_M202_CL017") -> dict:
    return te.build_task_spec(task(task_id), te.SREF_REF_FROZEN)


POLAR_HEADER = "Beta Mach AoA Re/1e6 CLo CLi CLtot CDo CDi CDtot"


def polar_text(rows, mach: float = 2.02) -> str:
    lines = ["Surface Integration Forces and Moments", "", POLAR_HEADER]
    for alpha, cl, cdi, cdtot, row_mach in rows:
        values = [0.0, row_mach if row_mach is not None else mach, alpha,
                  89.397005876766, 0.0, 0.0, cl, 0.008, cdi, cdtot]
        lines.append(" ".join("%.12f" % value for value in values))
    return "\n".join(lines) + "\n"


def default_rows(cl0: float = 0.15, slope: float = 0.02,
                 mach: float = 2.02):
    rows = []
    for alpha in te.ALPHA_GRID:
        cl = cl0 + slope * alpha
        cdi = 0.017 + 0.0001 * alpha
        rows.append((alpha, cl, cdi, cdi + 0.008, mach))
    return rows


def deck_text(spec: dict, sref: float = te.SREF_REF_FROZEN,
              alpha=None, overrides=None) -> str:
    alphas = list(te.ALPHA_GRID) if alpha is None else list(alpha)
    fields = {
        "Sref": te.decimal17(sref),
        "Cref": "18.489893",
        "Bref": "25.604638",
        "X_cg": te.decimal17(te.XCG_M),
        "Mach": te.decimal17(spec["task_definition"]["mach"]),
        "AoA": ", ".join(te.decimal17(value) for value in alphas),
        "Beta": "0.0",
        "ReCref": te.decimal17(spec["recref"]),
        "Vinf": te.decimal17(spec["vinf_m_s"]),
        "Rho": te.decimal17(spec["rho_kg_m3"]),
        "NumWakeNodes": "8",
    }
    if overrides:
        fields.update(overrides)
    return "\n".join("%s = %s" % (name, value) for name, value in fields.items()) + "\n"


def build_fixture(tmp_path: Path, design=None, spec=None) -> dict:
    design = design or te.REFERENCE_DESIGNS[0]
    spec = spec or make_spec()
    root = tmp_path / "build"
    root.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for stem, payload in (("vspgeom", b"vspgeom-bytes"), ("vkey", b"vkey-bytes"),
                          ("csf", b"csf-bytes")):
        path = root / ("geometry." + stem)
        path.write_bytes(payload)
        artifacts[stem] = {"path": str(path), "sha256": te.sha256_file(path)}
    base = root / "base.vspaero"
    base.write_text(deck_text(spec, sref=design.sref_m2), encoding="utf-8")
    return {
        "design": design,
        "sref_m2": design.sref_m2,
        "vspgeom": artifacts["vspgeom"],
        "vkey": artifacts["vkey"],
        "csf": artifacts["csf"],
        "vspaero_base": {"path": str(base), "sha256": te.sha256_file(base)},
        "record": {
            "mesh": {"mesh_family": "546x480", "nodes": 546, "elements": 480},
            "component_metrics": {
                "main_wing": {"bbox_m": [31.49534375886453, 25.604638251691824, 2.9919174836412785]},
                "vertical_tail": {"bbox_m": [13.15761606842186, 1.3165253323726676, 5.009331292697659]},
            },
        },
    }


def solved_record(tmp_path: Path):
    spec = make_spec()
    build = build_fixture(tmp_path, spec=spec)
    deck = te.derive_task_deck(build, spec, tmp_path / "task")
    polar = tmp_path / "task" / "concorde_baseline.polar"
    polar.write_text(polar_text(default_rows()), encoding="utf-8")
    analysis = te.analyze_polar(polar, spec, build["sref_m2"])
    return spec, deck, analysis


# ---------------------------------------------------------------------------
# atmosphere and task contract
# ---------------------------------------------------------------------------
def test_atmosphere_anchor_is_atm_f1r2_and_scales_exactly():
    atm = te.ATM_F1R2
    result = atm.validate()
    assert result["anchor_vinf_rel_error"] <= 1e-15
    assert result["anchor_q_rel_error"] <= 1e-12
    assert atm.vinf(2.02) == pytest.approx(596.0373972278921, rel=0, abs=0)
    assert atm.q(2.02) == pytest.approx(20483.940233430174, rel=0, abs=0)
    assert atm.q_recomputed(2.02) == pytest.approx(20483.940233430174, rel=1e-12)
    assert atm.q(2.2) == pytest.approx(24297.194081414087, rel=1e-15)
    assert atm.q(1.8) == pytest.approx(16265.063806566455, rel=1e-15)
    assert atm.vinf(2.2) == pytest.approx(649.1496405452291, rel=1e-15)
    assert atm.vinf(1.8) == pytest.approx(531.1224331733692, rel=1e-15)
    assert atm.recref(2.2) == pytest.approx(97363075.70736848, rel=1e-15)
    assert atm.recref(1.8) == pytest.approx(79660698.30602875, rel=1e-15)


def test_atmosphere_validate_rejects_wrong_anchor_values():
    with pytest.raises(te.TaskEvaluatorError):
        replace(te.ATM_F1R2, anchor_q_pa=te.ATM_F1R2.anchor_q_pa * 1.001).validate()
    with pytest.raises(te.TaskEvaluatorError):
        replace(te.ATM_F1R2, anchor_vinf_m_s=te.ATM_F1R2.anchor_vinf_m_s * 1.001).validate()


def test_six_task_specs_match_atm_f1r2_contract_exactly():
    expected = {
        "T18K_M202_CL017": (2.02, 0.17, "meta_train", 20483.940233430174,
                            1247523.1700664815, 127.21196025824125),
        "T18K_M202_CL019": (2.02, 0.19, "meta_train", 20483.940233430174,
                            1394290.6018390087, 142.17807322979905),
        "T18K_M220_CL017": (2.2, 0.17, "meta_train", 24297.194081414087,
                            1479759.862543322, 150.89351231494157),
        "T18K_M220_CL019": (2.2, 0.19, "meta_val", 24297.194081414087,
                            1653849.2581366538, 168.6456902343465),
        "T18K_M180_CL017": (1.8, 0.17, "meta_test", 16265.063806566455,
                            990583.0484794137, 101.01135948355594),
        "T18K_M180_CL019": (1.8, 0.19, "meta_test", 16265.063806566455,
                            1107122.2306534622, 112.89504883456249),
    }
    assert [item.task_id for item in te.TASK_DEFINITIONS] == list(expected)
    for task_id, (mach, cl, split, q_pa, l_ref, mass_t) in expected.items():
        spec = make_spec(task_id)
        assert spec["task_id"] == task_id
        assert spec["task_definition"]["mach"] == mach
        assert spec["task_definition"]["cl_target"] == cl
        assert spec["task_definition"]["split"] == split
        assert spec["task_definition"]["altitude_m"] == 18288.0
        assert spec["task_definition"]["atmosphere_id"] == "ATM-F1R2"
        assert spec["active_mask"] == "12D_ALL_ACTIVE"
        assert spec["sref_ref_m2"] == te.SREF_REF_FROZEN
        assert spec["q_pa"] == pytest.approx(q_pa, rel=1e-15)
        assert spec["l_ref_n"] == pytest.approx(l_ref, rel=1e-15)
        assert spec["mass_t"] == pytest.approx(mass_t, rel=1e-15)
        assert spec["cl_required_baseline"] == pytest.approx(cl, rel=1e-15)
        assert spec["q_recompute_rel_error"] <= 1e-12
        assert 100.0 <= spec["mass_t"] <= 190.0
        assert spec["l_ref_n"] == pytest.approx(
            spec["q_pa"] * te.SREF_REF_FROZEN * cl, rel=1e-15)


def test_task_spec_rejects_sref_drift_and_mass_out_of_bounds():
    good = task()
    with pytest.raises(te.TaskSpecInvalid):
        te.build_task_spec(good, te.SREF_REF_FROZEN * 1.001)
    with pytest.raises(te.TaskSpecInvalid):
        te.build_task_spec(good, -1.0)
    heavy = te.TaskDefinition("HEAVY", 2.02, 0.30, "meta_test", "too heavy")
    light = te.TaskDefinition("LIGHT", 2.02, 0.08, "meta_test", "too light")
    with pytest.raises(te.TaskSpecInvalid, match="mass"):
        te.build_task_spec(heavy, te.SREF_REF_FROZEN)
    with pytest.raises(te.TaskSpecInvalid, match="mass"):
        te.build_task_spec(light, te.SREF_REF_FROZEN)


def test_task_fingerprint_is_deterministic_and_task_sensitive():
    first = te.task_fingerprint(task("T18K_M202_CL017"))
    second = te.task_fingerprint(task("T18K_M202_CL017"))
    other = te.task_fingerprint(task("T18K_M202_CL019"))
    assert first == second
    assert first != other
    spec = make_spec("T18K_M202_CL017")
    assert spec["task_fingerprint"] == first
    assert len(first) == 64


# ---------------------------------------------------------------------------
# deck parsing / rewriting / validation
# ---------------------------------------------------------------------------
def test_decimal17_round_trip_and_deck_field_parser():
    assert float(te.decimal17(0.1)) == 0.1
    assert float(te.decimal17(596.0373972278921)) == 596.0373972278921
    text = "Sref = 1.0\r\nMach = 2.02\r\n# comment line\r\nAoA = -2, 0, 2\r\n"
    fields = te.parse_deck_fields(text)
    assert fields["Sref"] == "1.0"
    assert fields["Mach"] == "2.02"
    assert fields["AoA"] == "-2, 0, 2"
    assert "# comment line" not in fields


def test_rewrite_deck_preserves_lines_and_requires_target_fields():
    text = "Mach = 1.0\r\nRho = 1.0\r\nNote = keep-me\r\n"
    rewritten, applied = te.rewrite_deck(text, {"Mach": "2.2", "Rho": "0.1"})
    assert applied == {"Mach": "2.2", "Rho": "0.1"}
    assert "Mach = 2.2\r\n" in rewritten
    assert "Rho = 0.1\r\n" in rewritten
    assert "Note = keep-me\r\n" in rewritten
    with pytest.raises(te.DeckContractError, match="missing fields"):
        te.rewrite_deck(text, {"Mach": "2.2", "NotThere": "1"})


def test_validate_task_deck_accepts_contract_and_rejects_tamper(tmp_path):
    spec = make_spec()
    deck = tmp_path / "valid.vspaero"
    deck.write_text(deck_text(spec), encoding="utf-8")
    record = te.validate_task_deck(deck, spec, te.SREF_REF_FROZEN)
    assert all(record["checks"].values())
    assert record["cl_required"] == pytest.approx(0.17, rel=1e-15)
    assert record["alpha_deg"] == list(te.ALPHA_GRID)

    bad_q = tmp_path / "bad_q.vspaero"
    bad_q.write_text(deck_text(spec, overrides={"Rho": "0.12"}), encoding="utf-8")
    with pytest.raises(te.DeckContractError):
        te.validate_task_deck(bad_q, spec, te.SREF_REF_FROZEN)

    bad_alpha = tmp_path / "bad_alpha.vspaero"
    shifted = list(te.ALPHA_GRID)
    shifted[2] = 3.0
    bad_alpha.write_text(deck_text(spec, alpha=shifted), encoding="utf-8")
    with pytest.raises(te.DeckContractError):
        te.validate_task_deck(bad_alpha, spec, te.SREF_REF_FROZEN)

    missing = tmp_path / "missing.vspaero"
    missing.write_text("Sref = 358.25\n", encoding="utf-8")
    with pytest.raises(te.DeckContractError, match="missing fields"):
        te.validate_task_deck(missing, spec, te.SREF_REF_FROZEN)


def test_derive_task_deck_shares_geometry_and_only_rewrites_solver_fields(tmp_path):
    spec = make_spec("T18K_M202_CL017")
    build = build_fixture(tmp_path, spec=spec)
    first = te.derive_task_deck(build, spec, tmp_path / "task-a")
    second_spec = make_spec("T18K_M202_CL019")
    second = te.derive_task_deck(build, second_spec, tmp_path / "task-b")

    assert first["schema"] == te.SCHEMA_TASK_DECK
    assert first["task_id"] == "T18K_M202_CL017"
    assert first["design_id"] == "B0-01"
    assert first["source_kind"] == te.SOURCE_KIND_REBUILD
    assert first["solver_started"] is False
    assert first["physical_solver_starts"] == 0
    assert first["status"] == "DECK_READY_NOT_RUN"
    assert set(first["deck"]["applied_overrides"]) == {"Mach", "Vinf", "Rho", "ReCref"}
    assert first["deck"]["source_base_deck_sha256"] == build["vspaero_base"]["sha256"]
    assert set(first["solver_inputs"]["files"]) == {"vspgeom", "vkey", "vspaero", "csf"}
    assert first["solver_inputs"]["input_sha256"] == te.canonical_digest(
        [[stem, first["solver_inputs"]["files"][stem]["sha256"]]
         for stem in ("vspgeom", "vkey", "vspaero", "csf")])

    # Same geometry bytes must be reused across tasks; only the deck changes.
    assert first["geometry"]["vspgeom"]["sha256"] == second["geometry"]["vspgeom"]["sha256"]
    assert first["geometry"]["vkey"]["sha256"] == second["geometry"]["vkey"]["sha256"]
    assert first["geometry"]["sref_m2"] == second["geometry"]["sref_m2"]
    # CL_target does not enter the solver deck: same Mach => same deck bytes/SHA.
    assert first["deck"]["sha256"] == second["deck"]["sha256"]
    assert first["deck"]["fields"]["Mach"] == te.decimal17(2.02)
    assert (tmp_path / "task-a" / "task_deck.json").is_file()
    assert (tmp_path / "task-a" / "concorde_baseline.vspgeom").read_bytes() == b"vspgeom-bytes"


def test_derive_task_deck_rejects_base_deck_sref_mismatch(tmp_path):
    spec = make_spec()
    build = build_fixture(tmp_path, spec=spec)
    base = Path(build["vspaero_base"]["path"])
    base.write_text(deck_text(spec, sref=300.0), encoding="utf-8")
    build["vspaero_base"]["sha256"] = te.sha256_file(base)
    with pytest.raises(te.DeckContractError, match="Sref"):
        te.derive_task_deck(build, spec, tmp_path / "task")


def test_solver_input_digest_requires_all_four_files(tmp_path):
    for stem in ("vspgeom", "vkey", "vspaero", "csf"):
        (tmp_path / ("concorde_baseline." + stem)).write_bytes(stem.encode("utf-8"))
    result = te.solver_input_sha256(tmp_path)
    assert result["input_sha256"] == te.canonical_digest(
        [[stem, result["files"][stem]["sha256"]]
         for stem in ("vspgeom", "vkey", "vspaero", "csf")])
    (tmp_path / "concorde_baseline.csf").unlink()
    with pytest.raises(te.DeckContractError, match="missing solver input"):
        te.solver_input_sha256(tmp_path)


# ---------------------------------------------------------------------------
# polar analysis and failure classification
# ---------------------------------------------------------------------------
def test_ols_requires_five_rows_and_r2():
    rows = [{"alpha_deg": float(alpha), "cl": 0.17 + 0.02 * alpha}
            for alpha in te.ALPHA_GRID]
    result = te._ols_cl_alpha(rows)
    assert result["computable"] is True
    assert result["slope_per_deg"] == pytest.approx(0.02, rel=1e-15)
    assert result["r2"] == pytest.approx(1.0, rel=1e-15)
    assert te._ols_cl_alpha(rows[:4])["computable"] is False
    noisy = [{"alpha_deg": float(alpha), "cl": 0.17 + 0.02 * alpha + (0.1 if i % 2 else -0.1)}
             for i, alpha in enumerate(te.ALPHA_GRID)]
    assert te._ols_cl_alpha(noisy)["computable"] is False


def test_analyze_polar_interpolates_lift_matched_cdi(tmp_path):
    spec = make_spec()
    polar = tmp_path / "interp.polar"
    polar.write_text(polar_text(default_rows()), encoding="utf-8")
    result = te.analyze_polar(polar, spec, te.SREF_REF_FROZEN)
    assert result["status"] == "OK"
    assert result["rows_total"] == 7
    assert result["rows_valid"] == 7
    assert result["cl_target"] == pytest.approx(0.17, rel=1e-15)
    assert result["alpha_star_deg"] == pytest.approx(1.0, rel=1e-12)
    assert result["cdi_lift_matched"] == pytest.approx(0.0171, rel=1e-12)
    assert result["d_i_n"] == pytest.approx(
        spec["q_pa"] * te.SREF_REF_FROZEN * result["cdi_lift_matched"], rel=1e-15)
    assert result["lift_residual_rel"] <= 1e-12
    assert result["interpolation"]["mode"] == "linear_between_rows"
    assert result["polar_sha256"] == te.sha256_file(polar)
    assert result["cl_alpha"]["computable"] is True


def test_analyze_polar_exact_row_path(tmp_path):
    spec = make_spec()
    rows = [(alpha, 0.17 + 0.02 * alpha, 0.017, 0.025, 2.02) for alpha in te.ALPHA_GRID]
    polar = tmp_path / "exact.polar"
    polar.write_text(polar_text(rows), encoding="utf-8")
    result = te.analyze_polar(polar, spec, te.SREF_REF_FROZEN)
    assert result["status"] == "OK"
    assert result["alpha_star_deg"] == pytest.approx(0.0, abs=0)
    assert result["interpolation"]["mode"] == "exact_row"
    assert result["lift_residual_rel"] == 0.0


def test_analyze_polar_failure_modes(tmp_path):
    spec = make_spec("T18K_M202_CL017")
    rows = default_rows()

    nan_rows = list(rows)
    nan_rows[3] = (nan_rows[3][0], nan_rows[3][1], float("nan"),
                   nan_rows[3][3], nan_rows[3][4])
    nonfinite = tmp_path / "nan.polar"
    nonfinite.write_text(polar_text(nan_rows), encoding="utf-8")
    result = te.analyze_polar(nonfinite, spec, te.SREF_REF_FROZEN)
    assert result["status"] == "NONFINITE"
    assert result["rows_valid"] == 6
    assert len(result["nonfinite_rows"]) == 1

    incomplete = tmp_path / "six.polar"
    incomplete.write_text(polar_text(rows[:6]), encoding="utf-8")
    assert te.analyze_polar(incomplete, spec, te.SREF_REF_FROZEN)["status"] == "INCOMPLETE"

    mismatch = tmp_path / "alpha.polar"
    bad_alpha = list(rows)
    bad_alpha[2] = (3.0, bad_alpha[2][1], bad_alpha[2][2], bad_alpha[2][3], bad_alpha[2][4])
    mismatch.write_text(polar_text(bad_alpha), encoding="utf-8")
    assert te.analyze_polar(mismatch, spec, te.SREF_REF_FROZEN)["status"] == "ALPHA_GRID_MISMATCH"

    mach = tmp_path / "mach.polar"
    mach_rows = [(a, c, d, t, 2.2) for a, c, d, t, _ in rows]
    mach.write_text(polar_text(mach_rows), encoding="utf-8")
    assert te.analyze_polar(mach, spec, te.SREF_REF_FROZEN)["status"] == "MACH_MISMATCH"

    no_bracket = tmp_path / "nobracket.polar"
    no_bracket.write_text(polar_text([(a, 0.5 + 0.01 * a, d, t, m)
                                      for a, _, d, t, m in rows]), encoding="utf-8")
    assert te.analyze_polar(no_bracket, spec, te.SREF_REF_FROZEN)["status"] == "NO_BRACKET"

    garbage = tmp_path / "garbage.polar"
    garbage.write_text("not a polar table at all\n", encoding="utf-8")
    assert te.analyze_polar(garbage, spec, te.SREF_REF_FROZEN)["status"] == "PARSE_ERROR"

    missing = te.analyze_polar(tmp_path / "missing.polar", spec, te.SREF_REF_FROZEN)
    assert missing["status"] == "NO_POLAR"
    assert missing["polar_exists"] is False


def test_classify_failure_five_class_fail_closed_order():
    ok_analysis = {"polar_exists": True, "status": "OK"}
    base_attempt = {"exit_code": 0, "timed_out": False}
    assert te.classify_failure(geometry_ok=True, deck_ok=True, attempt=base_attempt,
                               polar_analysis=ok_analysis) == te.SOLVED
    assert te.classify_failure(geometry_ok=False, deck_ok=True, attempt={},
                               polar_analysis=ok_analysis) == te.FAILURE_GEOMETRY_INVALID
    assert te.classify_failure(geometry_ok=True, deck_ok=False, attempt={},
                               polar_analysis=ok_analysis) == te.FAILURE_GEOMETRY_INVALID
    assert te.classify_failure(geometry_ok=True, deck_ok=True,
                               attempt={"timed_out": True}, polar_analysis={}) == te.FAILURE_INFRA_ERROR
    assert te.classify_failure(geometry_ok=True, deck_ok=True,
                               attempt={"exit_code": None}, polar_analysis={}) == te.FAILURE_INFRA_ERROR
    assert te.classify_failure(geometry_ok=True, deck_ok=True,
                               attempt={"exit_code": 0, "timed_out": False},
                               polar_analysis={"polar_exists": False}) == te.FAILURE_INFRA_ERROR
    assert te.classify_failure(geometry_ok=True, deck_ok=True,
                               attempt={"exit_code": 1, "timed_out": False},
                               polar_analysis={"polar_exists": False}) == te.FAILURE_SOLVER_FAILED
    assert te.classify_failure(geometry_ok=True, deck_ok=True,
                               attempt={"exit_code": 1, "timed_out": False},
                               polar_analysis={"polar_exists": True, "status": "OK"}) == te.FAILURE_SOLVER_FAILED
    for status in ("NONFINITE", "INCOMPLETE", "ALPHA_GRID_MISMATCH", "MACH_MISMATCH"):
        assert te.classify_failure(geometry_ok=True, deck_ok=True, attempt=base_attempt,
                                   polar_analysis={"polar_exists": True, "status": status}) == te.FAILURE_SOLVER_NONCONVERGED
    assert te.classify_failure(geometry_ok=True, deck_ok=True, attempt=base_attempt,
                               polar_analysis={"polar_exists": True, "status": "PARSE_ERROR"}) == te.FAILURE_INFRA_ERROR
    assert te.classify_failure(geometry_ok=True, deck_ok=True, attempt=base_attempt,
                               polar_analysis={"polar_exists": True, "status": "NO_BRACKET"}) == te.FAILURE_LIFT_TARGET_UNREACHABLE
    assert te.classify_failure(geometry_ok=True, deck_ok=True, attempt=base_attempt,
                               polar_analysis={"polar_exists": True, "status": "WEIRD"}) == te.FAILURE_INFRA_ERROR


# ---------------------------------------------------------------------------
# evaluation records and idempotence
# ---------------------------------------------------------------------------
def test_evaluation_key_is_deterministic_and_sensitive():
    spec = make_spec()
    args = ("8bd5a6c7c8311938", "d" * 64, "g" * 64, "s" * 64)
    first = te.evaluation_key(spec, *args)
    assert first == te.evaluation_key(spec, *args)
    assert first != te.evaluation_key(spec, "9" * 16, *args[1:])
    assert first != te.evaluation_key(spec, args[0], "e" * 64, *args[2:])
    assert first != te.evaluation_key(spec, args[0], args[1], "f" * 64, args[3])
    assert first != te.evaluation_key(spec, args[0], args[1], args[2], "t" * 64)


def test_build_evaluation_record_solved_and_failed(tmp_path):
    spec, deck, analysis = solved_record(tmp_path)
    attempt = {
        "attempt_id": "B0-01-a1", "exit_code": 0, "timed_out": False,
        "solver_sha256": te.SOLVER_SHA256, "started": True,
        "started_utc": "2026-11-13T00:00:00Z", "ended_utc": "2026-11-13T00:00:04Z",
        "stdout_path": "stdout.txt", "stderr_path": "stderr.txt",
        "stdout_sha256": "a" * 64, "stderr_sha256": "b" * 64,
        "argv": ["vspaero", "-omp", "1", te.BASENAME], "cwd": "case",
    }
    record = te.build_evaluation_record(task_spec=spec, deck_record=deck,
                                        attempt=attempt, polar_analysis=analysis,
                                        status=te.SOLVED)
    assert record["schema"] == te.SCHEMA_EVALUATION
    assert record["objective_Di_N"] == pytest.approx(analysis["d_i_n"], rel=1e-15)
    assert record["alpha_star_deg"] == pytest.approx(analysis["alpha_star_deg"], rel=0)
    assert record["sref_m2"] == te.SREF_REF_FROZEN
    assert record["l_ref_n"] == pytest.approx(spec["l_ref_n"], rel=1e-15)
    assert record["cl_required"] == pytest.approx(0.17, rel=1e-15)
    assert record["status"] == te.SOLVED
    assert record["failure_class"] is None
    assert record["starts"] == 1
    assert record["internal"] == 7
    assert record["physical_solver_starts"] == 1
    assert record["raw_sha"] == analysis["polar_sha256"]
    assert record["geometry_sha"] == deck["geometry"]["vspgeom"]["sha256"]
    assert record["deck_sha"] == deck["deck"]["sha256"]
    assert record["evaluation_key"] == te.evaluation_key(
        spec, deck["design_hash"], deck["deck"]["sha256"],
        deck["geometry"]["vspgeom"]["sha256"], te.SOLVER_SHA256)

    failed = te.build_evaluation_record(
        task_spec=spec, deck_record=deck, attempt=attempt,
        polar_analysis={"polar_sha256": "c" * 64, "polar_bytes": 10,
                        "status": "NO_BRACKET", "d_i_n": None,
                        "detail": "outside range"},
        status=te.FAILURE_LIFT_TARGET_UNREACHABLE)
    assert failed["objective_Di_N"] is None
    assert failed["alpha_star_deg"] is None
    assert failed["failure_class"] == te.FAILURE_LIFT_TARGET_UNREACHABLE
    assert failed["starts"] == 1
    assert failed["status"] == te.FAILURE_LIFT_TARGET_UNREACHABLE

    not_started = te.build_evaluation_record(
        task_spec=spec, deck_record=deck,
        attempt={"started": False, "exit_code": None},
        polar_analysis={"polar_exists": False, "status": "NO_POLAR"},
        status=te.FAILURE_INFRA_ERROR)
    assert not_started["starts"] == 0
    assert not_started["internal"] == 0
    assert not_started["physical_solver_starts"] == 0

    with pytest.raises(te.TaskEvaluatorError, match="unknown evaluation status"):
        te.build_evaluation_record(task_spec=spec, deck_record=deck,
                                   attempt=attempt, polar_analysis=analysis,
                                   status="NOT_A_STATUS")


def test_write_evaluation_record_is_idempotent_and_rejects_conflict(tmp_path):
    spec, deck, analysis = solved_record(tmp_path)
    record = te.build_evaluation_record(
        task_spec=spec, deck_record=deck,
        attempt={"exit_code": 0, "timed_out": False, "started": True},
        polar_analysis=analysis, status=te.SOLVED)
    first = te.write_evaluation_record(tmp_path / "out", record)
    assert first["reused"] is False
    assert Path(first["path"]).is_file()
    second = te.write_evaluation_record(tmp_path / "out", record)
    assert second["reused"] is True
    assert second["path"] == first["path"]
    changed = dict(record)
    changed["objective_Di_N"] = -1.0
    with pytest.raises(te.TaskEvaluatorError, match="conflicting"):
        te.write_evaluation_record(tmp_path / "out", changed)


def test_write_attempt_summary_requires_id_and_is_exclusive(tmp_path):
    path = te.write_attempt_summary(tmp_path, {"attempt_id": "a1", "exit_code": 0})
    assert Path(path["path"]).is_file()
    with pytest.raises(FileExistsError):
        te.write_attempt_summary(tmp_path, {"attempt_id": "a1", "exit_code": 0})
    with pytest.raises(te.TaskEvaluatorError, match="attempt_id"):
        te.write_attempt_summary(tmp_path, {"exit_code": 0})


def test_write_json_exclusive_and_strict_json(tmp_path):
    target = tmp_path / "x.json"
    te.write_json(target, {"b": 2, "a": 1})
    te.write_json(target, {"b": 3, "a": 1})
    assert json.loads(target.read_text(encoding="utf-8"))["b"] == 3
    exclusive = tmp_path / "y.json"
    te.write_json(exclusive, {"a": 1}, exclusive=True)
    with pytest.raises(FileExistsError):
        te.write_json(exclusive, {"a": 1}, exclusive=True)
    with pytest.raises(ValueError):
        te.strict_dumps({"x": float("nan")})
    assert te.canonical_digest({"a": 1, "b": 2}) == te.canonical_digest({"b": 2, "a": 1})


# ---------------------------------------------------------------------------
# spawn guard and A2 ledger hooks
# ---------------------------------------------------------------------------
def test_spawn_guard_blocks_children_and_restores_handlers():
    original_popen = subprocess.Popen
    original_system = os.system
    guard = te.SpawnGuard().install()
    try:
        with pytest.raises(te.TaskEvaluatorError, match="spawn blocked"):
            subprocess.Popen(["cmd.exe", "/c", "exit 0"])
        with pytest.raises(te.TaskEvaluatorError, match="spawn blocked"):
            os.system("echo should-not-run")
        assert any("subprocess.Popen" in item for item in guard.attempts)
        assert any("os.system" in item for item in guard.attempts)
    finally:
        guard.uninstall()
    assert subprocess.Popen is original_popen
    assert os.system is original_system


class FakeLedger:
    def __init__(self):
        self.calls = []

    def reserve(self, phase, **kwargs):
        self.calls.append(("reserve", phase, kwargs))
        return "tx-1"

    def start(self, tx_id, **kwargs):
        self.calls.append(("start", tx_id, kwargs))
        return True

    def end(self, tx_id, status, **kwargs):
        self.calls.append(("end", tx_id, status, kwargs))
        return True

    def fail_before_start(self, tx_id, **kwargs):
        self.calls.append(("fail_before_start", tx_id, kwargs))
        return True

    def record_evaluation(self, phase, **kwargs):
        self.calls.append(("record_evaluation", phase, kwargs))

    def record_cached_read(self, phase, **kwargs):
        self.calls.append(("record_cached_read", phase, kwargs))


def test_a2_ledger_hooks_translate_reserve_start_end_and_metadata():
    ledger = FakeLedger()
    hooks = te.A2LedgerHooks(ledger, phase="main", arm_id="M1_TASK")
    tx = hooks.reserve(design_index=3, design_hash="h", meta={"task_id": "T"})
    assert tx == "tx-1"
    assert hooks.start(tx, case_id="case-1", meta={"x": 1}) is True
    assert hooks.end(tx, status="SOLVED_VALID", internal_solver_cases=7) is True
    assert hooks.fail_before_start(tx, reason="cap") is True
    hooks.record_evaluation(design_index=3, design_hash="h", meta={"a": 1})
    hooks.record_cached_read(design_hash="h", source="M0_REPLAY", meta={"b": 2})
    assert ledger.calls[0] == ("reserve", "main", {
        "arm_id": "M1_TASK", "design_index": 3, "design_hash": "h",
        "planned_starts": 1, "planned_internal_cases": 7,
        "meta": {"task_id": "T"}})
    assert ledger.calls[1][0] == "start"
    assert ledger.calls[2][0] == "end"
    assert ledger.calls[2][2] == "SOLVED_VALID"
    assert ledger.calls[3][0] == "fail_before_start"
    assert ledger.calls[4][0] == "record_evaluation"
    assert ledger.calls[5][0] == "record_cached_read"

    class Broken:
        pass

    with pytest.raises(te.TaskEvaluatorError, match="missing methods"):
        te.A2LedgerHooks(Broken())


# ---------------------------------------------------------------------------
# U1 rebind and structural orientation gate
# ---------------------------------------------------------------------------
def test_u1_reference_files_and_design_hashes_are_bound():
    checks = te.verify_u1_reference_files()
    assert len(checks) == 8
    assert all(item["ok"] for item in checks)
    old = [item for item in checks if item["check_id"] == "U1-OLD-GEOMETRY-NOT-USED"]
    assert len(old) == 1 and old[0]["used"] is False


def test_orientation_gate_is_structural_for_low_tail_designs():
    baseline = {
        "record": {"component_metrics": {
            "main_wing": {"bbox_m": [31.49534375886453, 25.604638251691824, 2.9919174836412785]},
            "vertical_tail": {"bbox_m": [13.15761606842186, 1.3165253323726676, 5.009331292697659]},
        }}}
    result = te._component_orientation_checks(baseline)
    assert result["wing_horizontal"] is True
    assert result["tail_vertical_structural"] is True
    assert result["ok"] is True

    low_tail = {
        "record": {"component_metrics": {
            "main_wing": {"bbox_m": [31.495, 25.60, 2.99]},
            "vertical_tail": {"bbox_m": [12.081048, 1.208806, 4.599463]},
        }}}
    low = te._component_orientation_checks(low_tail)
    assert low["tail_vertical_structural"] is True
    assert low["ok"] is True

    coplanar = {
        "record": {"component_metrics": {
            "main_wing": {"bbox_m": [31.495, 25.60, 2.99]},
            "vertical_tail": {"bbox_m": [13.157616068421863, 5.009331292697659, 1.3165253323726676]},
        }}}
    broken = te._component_orientation_checks(coplanar)
    assert broken["tail_vertical_structural"] is False
    assert broken["ok"] is False

    bad_wing = {
        "record": {"component_metrics": {
            "main_wing": {"bbox_m": [31.495, 10.0, 8.0]},
            "vertical_tail": {"bbox_m": [13.0, 1.0, 5.0]},
        }}}
    assert te._component_orientation_checks(bad_wing)["ok"] is False

def test_alpha_refine_policy_is_frozen_no_refine():
    assert te.MAX_ALPHA_REFINE == 0
    assert te.ALPHA_REFINE_MODE == "FIXED_7_POINT_NO_REFINE"
    assert tuple(te.ALPHA_GRID) == (-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0)
    assert len(te.ALPHA_GRID) == 7


def test_deck_q_is_recomputed_from_injected_vinf_and_rho(tmp_path):
    spec = make_spec()
    deck = tmp_path / "q_contract.vspaero"
    deck.write_text(deck_text(spec), encoding="utf-8")
    record = te.validate_task_deck(deck, spec, te.SREF_REF_FROZEN)
    assert record["q_recompute_rel_error"] <= 1e-12
    assert record["q_recomputed_pa"] == pytest.approx(spec["q_pa"], rel=1e-12)
    assert record["checks"]["q_recompute_rel_le_1e_12"] is True

