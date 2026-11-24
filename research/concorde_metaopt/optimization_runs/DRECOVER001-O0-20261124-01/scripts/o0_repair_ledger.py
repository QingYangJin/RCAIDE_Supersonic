
"""Rebuild the O0-FINAL verification ledger so that the bill matches the disk.

What went wrong is recorded in full in section 4c of the A5 dossier: the first O0-FINAL run
crashed on its third start, and the ledger it left behind described two starts that had been spent
on cases whose wake count was 2 -- below the admission mesh of 8 -- so neither could ever be
admitted. The third start, a 16-wake-node probe that is a pre-registered item in its own right,
had actually completed and its paid solver output is still on the disk, but it never reached the
ledger at all because the charge came after the run.

This script does not run a solver and does not spend a start. It reads the three case directories,
checks that each one really holds the paid output it claims to hold, and rewrites the ledger with
three rows whose kinds tell the truth:

  final-baseline-r1   void   wake=2, spent, never admissible, never re-run
  final-baseline-r2   void   wake=2, spent, never admissible, never re-run
  final-baseline-wake16 wake  16 wake nodes, completed, a pre-registered probe, never admitted

A row that is written here without its evidence on the disk is a lie, so every row carries the
sha256 of the polar file and of the case_result.json that back it, plus the file count and the byte
count of the case directory. If any of that does not check out the script exits without writing.
"""
from __future__ import annotations

import json
from pathlib import Path

RUN = Path(__file__).resolve().parent.parent
LEDGER = RUN / "o0_final" / "verification_ledger.json"
CASES = RUN / "cases" / "O0F"

CAPS = {"max_verification_starts": 8, "max_verification_internal_cases": 104,
        "max_repeat_runs_per_design": 2, "max_wake_probe_starts": 2, "max_void_rows": 2,
        "n_wake_nodes_reference": 8, "n_wake_nodes_probe": 16, "refinement_points": 13}

ROWS = [
    {"label": "final-baseline-r1", "kind": "void", "case": "o0-final-baseline-r1-final",
     "n_wake_nodes": 2,
     "note": ("spent before the crash on a case whose wake count was 2, below the admission mesh "
              "of 8; the polar it produced is real but the mesh is not the admitted mesh, so it "
              "can never be admitted and must never be re-run under this label")},
    {"label": "final-baseline-r2", "kind": "void", "case": "o0-final-baseline-r2-final",
     "n_wake_nodes": 2,
     "note": ("spent before the crash on a case whose wake count was 2, below the admission mesh "
              "of 8; same disposition as final-baseline-r1")},
    {"label": "final-baseline-wake16", "kind": "wake", "case": "o0-final-baseline-wake16-final",
     "n_wake_nodes": 16,
     "note": ("the pre-registered 16-wake-node probe for the baseline; it completed before the "
              "crash and its paid output is on the disk, but the charge never ran because the "
              "charge used to happen after the run. It is charged here, it is a probe and is "
              "never admitted, and it is not re-run because it already happened")},
]


def sha(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def case_evidence(row):
    case_dir = CASES / row["case"]
    if not case_dir.is_dir():
        raise SystemExit("MISSING_CASE_DIR: %s does not exist; a ledger row without a paid case "
                         "on the disk is a claim, not a bill" % case_dir)
    files = [p for p in case_dir.rglob("*") if p.is_file()]
    polars = sorted(case_dir.glob("*.polar"))
    results = sorted(case_dir.glob("case_result.json"))
    if not polars:
        raise SystemExit("NO_POLAR: %s holds no .polar file, so no start was ever spent there"
                         % case_dir)
    if not results:
        raise SystemExit("NO_CASE_RESULT: %s holds no case_result.json, so the run did not "
                         "complete and this row must not be charged as spent" % case_dir)
    evaluation = {}
    raw = results[0].read_text(encoding="utf-8", errors="replace")
    # case_result.json carries Infinity literals, which json.loads accepts but json.dump does not.
    parsed = json.loads(raw.replace("Infinity", "1e999").replace("NaN", "null"))
    evaluation = parsed.get("evaluation") or {}
    rows = evaluation.get("rows") or []
    accounting = evaluation.get("accounting") or parsed.get("accounting") or {}
    starts = int(accounting.get("physical_solver_starts")
                 or parsed.get("physical_solver_starts") or 0)
    internal = int(accounting.get("internal_solver_cases") or len(rows) or 0)
    if starts != 1:
        raise SystemExit("BAD_START_COUNT: %s reports %r physical solver starts, expected 1"
                         % (case_dir, starts))
    if internal != int(CAPS["refinement_points"]):
        raise SystemExit("BAD_INTERNAL_COUNT: %s reports %r internal cases, expected %d"
                         % (case_dir, internal, CAPS["refinement_points"]))
    return {
        "case_id": row["case"], "case_dir": str(case_dir),
        "file_count": len(files), "bytes": sum(p.stat().st_size for p in files),
        "polar_sha256": sha(polars[0]), "polar_bytes": polars[0].stat().st_size,
        "case_result_sha256": sha(results[0]),
        "status": evaluation.get("status"), "rows": len(rows),
        "physical_solver_starts": starts, "internal_solver_cases": internal,
        "n_wake_nodes": row["n_wake_nodes"],
        "solver_config_sha256": evaluation.get("solver_config_sha256"),
    }


def main() -> int:
    old_sha = None
    old_state = {}
    if LEDGER.is_file():
        old_sha = sha(LEDGER)
        old_state = json.loads(LEDGER.read_text(encoding="utf-8"))
        done = [r for r in (old_state.get("rows") or []) if r.get("kind") in ("void", "repeat")]
        if done and old_state.get("repair"):
            print(json.dumps({"already_repaired": True, "ledger_sha256": old_sha,
                              "rows": old_state["rows"]}, ensure_ascii=False, indent=2))
            return 0
    rows = []
    for row in ROWS:
        evidence = case_evidence(row)
        rows.append({"label": row["label"], "kind": row["kind"], "starts": 1,
                     "internal": int(CAPS["refinement_points"]),
                     "utc": "2026-11-24T09:13:00Z",
                     "note": row["note"],
                     "admissible_as_evidence": False,
                     "charged_post_hoc_because_the_run_crashed_before_the_charge": True,
                     "evidence": evidence})
    starts = sum(r["starts"] for r in rows)
    internal = sum(r["internal"] for r in rows)
    payload = {
        "schema": "dreal005.o0_final_verification_ledger.v1",
        "created_utc": "2026-11-24T09:13:00Z",
        "repaired_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "caps": CAPS,
        "rows": rows,
        "verification_starts_actual": starts,
        "verification_internal_cases_actual": internal,
        "wake_probe_starts_actual": len([r for r in rows if r["kind"] == "wake"]),
        "repeat_runs_actual": len([r for r in rows if r["kind"] == "repeat"]),
        "void_rows_actual": len([r for r in rows if r["kind"] == "void"]),
        "admissible_rows_actual": 0,
        "prior_ledger_sha256": old_sha,
        "repair": {
            "reason": ("the crashed O0-FINAL run charged its starts after the run, so the third "
                       "paid start never reached the ledger, and the two starts that did reach it "
                       "were labelled kind=wake although they were repeats configured with 2 wake "
                       "nodes. Both facts are corrected here from the paid case directories."),
            "old_ledger_sha256": old_sha,
            "old_rows": old_state.get("rows") or [],
            "old_caps": old_state.get("caps"),
            "kind_corrections": [
                {"label": "final-baseline-r1", "old_kind": "wake", "new_kind": "void"},
                {"label": "final-baseline-r2", "old_kind": "wake", "new_kind": "void"},
                {"label": "final-baseline-wake16", "old_kind": None, "new_kind": "wake",
                 "why": "the run completed and the paid output is on the disk but the charge "
                        "never happened"},
            ],
            "total_charged_is_unchanged_in_kind_but_not_in_count": (
                "the old ledger claimed 2 starts and 26 internal cases; the true bill is 3 starts "
                "and 39 internal cases, all of them already spent, none of them re-runnable"),
            "not_a_new_budget": ("this repair adds no permission to spend. It only makes the "
                                 "already-spent bill visible, and the caps are the repaired "
                                 "verification caps that include the five starts still to be "
                                 "spent."),
        },
        "note": ("separately itemized verification budget; never folded into the O0 optimizer "
                 "caps. Void rows are starts already spent on mis-configured cases: charged so "
                 "the bill matches the disk, never admitted, never re-run. The wake probe row is "
                 "a pre-registered probe that is never admitted because the admitted wake count "
                 "is fixed at 8."),
    }
    if starts != 3 or internal != 39:
        raise SystemExit("SELF_CHECK: the repaired ledger must record exactly the 3 spent starts "
                         "and 39 internal cases, got %d and %d" % (starts, internal))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"ledger": str(LEDGER), "ledger_sha256": sha(LEDGER),
                      "rows": len(rows), "starts": starts, "internal": internal,
                      "kinds": [r["kind"] for r in rows],
                      "case_bytes": [r["evidence"]["bytes"] for r in rows]},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
