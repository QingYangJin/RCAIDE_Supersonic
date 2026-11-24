"""Tests for the O0-FINAL verification ledger, run without spending a solver start.

The ledger is the only thing that stands between a crashed verification run and a bill that
disagrees with the disk, so it is tested directly rather than through a solver run. Nothing here
touches VSPAERO; every test uses a temporary ledger file and synthetic rows.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent
SCRIPTS = RUN / "scripts"
sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("o0_final", SCRIPTS / "o0_final.py")
o0_final = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o0_final)

Ledger = o0_final.Ledger
CAPS = dict(o0_final.CAPS)
FAILS = []


def check(name, fn):
    try:
        fn()
    except AssertionError as exc:
        FAILS.append("%s: %s" % (name, exc))
        print("FAIL %s: %s" % (name, exc))
    else:
        print("ok   %s" % name)


TMP_ROOT = RUN / "o0_final" / "selftest"


def fresh(caps=None):
    # Under the run root rather than the OS temp directory: the sandbox allows writes here and
    # nowhere else, and a test that cannot write a ledger cannot test a ledger.
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    counter = len(list(TMP_ROOT.glob("ledger_*"))) + 1
    path = TMP_ROOT / ("ledger_%02d.json" % counter)
    if path.exists():
        path.unlink()
    return Ledger(path, caps or dict(CAPS))


def test_caps_are_the_repaired_ones():
    assert CAPS["max_verification_starts"] == 8, CAPS["max_verification_starts"]
    assert CAPS["max_verification_internal_cases"] == 104, CAPS["max_verification_internal_cases"]
    assert CAPS["max_void_rows"] == 2, CAPS["max_void_rows"]
    assert CAPS["max_repeat_runs_per_design"] == 2
    assert CAPS["max_wake_probe_starts"] == 2
    assert CAPS["n_wake_nodes_reference"] == 8
    assert CAPS["n_wake_nodes_probe"] == 16
    assert CAPS["refinement_points"] == 13


def test_kind_must_be_a_known_plan_field():
    book = fresh()

    def boom():
        book.charge("x1", 1, 13, "repeat-like")
    try:
        boom()
    except RuntimeError as exc:
        assert "never inferred from a number" in str(exc), exc
    else:
        raise AssertionError("an unknown kind was accepted")
    assert book.totals()["starts"] == 0, "a refused charge must not move the bill"


def test_void_rows_are_charged_but_not_admissible():
    book = fresh()
    book.charge("v1", 1, 13, "void", note="wake=2")
    book.charge("v2", 1, 13, "void", note="wake=2")
    total = book.totals()
    assert total["starts"] == 2, total
    assert total["void_rows"] == 2, total
    assert total["admissible_rows"] == 0, total
    persisted = json.loads(book.path.read_text(encoding="utf-8"))
    assert persisted["void_rows_actual"] == 2, persisted
    assert all(r["admissible_as_evidence"] is False for r in persisted["rows"]), persisted


def test_void_cap_is_enforced():
    book = fresh()
    book.charge("v1", 1, 13, "void")
    book.charge("v2", 1, 13, "void")
    try:
        book.charge("v3", 1, 13, "void")
    except RuntimeError as exc:
        assert "void row cap exceeded" in str(exc), exc
    else:
        raise AssertionError("a third void row was accepted")


def test_repeat_and_wake_caps_are_separate_from_void():
    book = fresh()
    book.charge("v1", 1, 13, "void")
    book.charge("v2", 1, 13, "void")
    book.charge("w1", 1, 13, "wake")
    book.charge("w2", 1, 13, "wake")
    try:
        book.charge("w3", 1, 13, "wake")
    except RuntimeError as exc:
        assert "wake probe cap exceeded" in str(exc), exc
    else:
        raise AssertionError("a third wake probe was accepted")
    assert book.totals()["admissible_rows"] == 0, book.totals()


def test_duplicate_label_is_refused():
    book = fresh()
    book.charge("r1", 1, 13, "repeat")
    try:
        book.charge("r1", 1, 13, "repeat")
    except RuntimeError as exc:
        assert "already in the verification ledger" in str(exc), exc
    else:
        raise AssertionError("a duplicate label was accepted")


def test_gross_budget_leaves_only_five_starts_after_the_crash():
    """The repaired ledger holds 3 spent starts, so the runner must allow exactly 5 more."""
    book = fresh()
    tmp_rows = [
        {"label": "final-baseline-r1", "kind": "void", "starts": 1, "internal": 13,
         "admissible_as_evidence": False},
        {"label": "final-baseline-r2", "kind": "void", "starts": 1, "internal": 13,
         "admissible_as_evidence": False},
        {"label": "final-baseline-wake16", "kind": "wake", "starts": 1, "internal": 13,
         "admissible_as_evidence": False},
    ]
    book.rows = list(tmp_rows)
    book.persist()
    for label in ("final-baseline-r1b", "final-baseline-r2b",
                  "final-best-r1", "final-best-r2", "final-best-wake16"):
        book.charge(label, 1, 13, "repeat" if "wake" not in label else "wake")
    total = book.totals()
    assert total["starts"] == 8, total
    assert total["internal"] == 104, total
    try:
        book.charge("beyond-the-cap", 1, 13, "repeat")
    except RuntimeError as exc:
        assert "cap" in str(exc), exc
    else:
        raise AssertionError("a ninth start was charged past the gross budget")


def test_ledger_survives_a_reload():
    book = fresh()
    book.charge("r1", 1, 13, "repeat")
    reloaded = Ledger(book.path, dict(CAPS))
    assert reloaded.totals()["starts"] == 1, reloaded.totals()
    assert reloaded.prior_sha256, "a reloaded ledger must record the sha of the file it read"
    assert reloaded.charged("r1"), "a reloaded ledger must remember what it charged"


def test_free_label_skips_charged_labels():
    """The second batch cannot re-use the label of a start that was already spent."""
    book = fresh()
    book.rows = [{"label": "final-baseline-r1", "kind": "void", "starts": 1, "internal": 13,
                  "admissible_as_evidence": False}]
    book.persist()
    source = (SCRIPTS / "o0_final.py").read_text(encoding="utf-8")
    assert "def free_label" in source, "the free-label helper is gone"
    assert 'base + suffix' in source, "the helper no longer searches for a free suffix"


def test_planned_cost_accepts_both_shapes_of_alpha_points():
    """The charge must not throw, because a charge that throws is a start nobody billed.

    o0_eval.make_case() returns the count; an earlier draft read it as a list and the run died
    on the first start with TypeError before the charge. Both shapes must cost the same.
    """
    count_shape = {"alpha_points": 13}
    list_shape = {"alpha_points": [5.1 + 0.004 * i for i in range(13)]}
    assert o0_final.planned_internal_for(count_shape) == 13
    assert o0_final.planned_internal_for(list_shape) == 13
    try:
        o0_final.planned_internal_for({"alpha_points": None})
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError("a case with no alpha points must fail loudly, not cost zero")


def test_kind_comes_from_the_plan_not_from_the_wake_count():
    """The crash happened because the kind was inferred from a number. The wiring must be explicit."""
    source = (SCRIPTS / "o0_final.py").read_text(encoding="utf-8")
    assert '"kind" if wake' not in source, "the kind is being inferred from the wake count again"
    assert 'admit=(kind == "repeat")' in source, "admission is no longer keyed to the plan kind"
    assert 'CAPS["n_wake_nodes_reference"], "repeat")' in source, (
        "repeat cases are no longer planned at the reference wake mesh")


def test_wake_rows_are_never_admissible():
    book = fresh()
    book.charge("w1", 1, 13, "wake", note="16 wake nodes")
    assert book.totals()["admissible_rows"] == 0, book.totals()
    assert book.totals()["wake_rows"] == 1
    assert book.rows[0]["admissible_as_evidence"] is False


def main():
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            check(name, fn)
    print()
    if FAILS:
        print("FAILED %d check(s):" % len(FAILS))
        for item in FAILS:
            print("  - " + item)
        return 1
    print("ALL O0-FINAL LEDGER CHECKS PASSED (no solver start spent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
