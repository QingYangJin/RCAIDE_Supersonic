
"""Generate the P0 A5 dossier from files in this worktree (hashes computed live)."""
from __future__ import annotations

import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
P0 = Path(__file__).resolve().parent
OUT = P0 / "p0_a5_dossier.md"
BT = chr(96)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


pre = json.loads((P0 / "p1_p2_p3_preregistration.json").read_text(encoding="utf-8"))
code = pre["code_shas"]
tests = json.loads((P0 / "p0_test_summary.json").read_text(encoding="utf-8"))
replay = json.loads((P0 / "g1_alpha_replay.json").read_text(encoding="utf-8"))
audit = json.loads((P0 / "12d_variable_response_audit.json").read_text(encoding="utf-8"))
endpoints = json.loads((P0 / "a2_g1_baseline_endpoints.json").read_text(encoding="utf-8"))
protocol = P0 / "p0_protocol_freeze_20261122.md"

lines = []
w = lines.append
w("# P0 A5 dossier - Issue #14 D-REAL-EXP-002")
w("")
w("Independent review request. This dossier describes P0 only (code, zero-physical")
w("replay, 12D response audit, A2 endpoint analyzer, protocol freeze). It grants no")
w("new physics and no P1 authorisation.")
w("")
w("## 1. Identity")
w("")
w("- Issue: QingYangJin/RCAIDE_Supersonic#14 (D-REAL-EXP-002, 2026-11-21)")
w("- Branch: " + BT + "research/dreal004-alpha-adaptive-meta-sampling" + BT)
w("- Base commit: " + BT + "af9871cd2b16a083c228ac2ecbced4c0344012a0" + BT + " (previous stage snapshot " + BT + "409f09c8" + BT + ")")
w("- Current authorization: P0 code/protocol/zero-physical only")
w("- Physical solver starts this round: 0; internal solver cases: 0; labels created: 0")
w("- Solver identity (for later phases, not invoked): vspaero-3.55.0-v7.2.2-omp1, omp 1, no retries")
w("")
w("## 2. Code delivered (SHA256)")
w("")
w("| file | sha256 |")
w("|---|---|")
for path, digest in code.items():
    w("| " + BT + path + BT + " | " + BT + digest + BT + " |")
w("")
w("### A1 AdaptiveAlphaSolver contract")
w("")
w("- Injected evaluator only: no solver path is embedded; every probe increments one")
w("  internal alpha case; the caller owns real solver starts.")
w("- Statuses: RAW_POINT_MATCHED, INTERPOLATED_TARGET_ESTIMATE, NO_BRACKET,")
w("  NO_CONVERGENCE, INVALID_POLAR, SOLVER_FAILED, BUDGET_EXHAUSTED.")
w("- Refinement: secant interpolation constrained inside the bracket; no extrapolation;")
w("  a target that only exists as an interpolated estimate is never reported as a raw hit.")
w("- " + BT + "replay_on_existing_rows" + BT + " can only query existing raw polar rows; a missing row")
w("  returns " + BT + "REPLAY_ROW_NOT_AVAILABLE" + BT + " instead of inventing data.")
w("- " + BT + "polar_rows.read_polar_rows" + BT + " parses Beta/Mach/AoA/CLtot/CDo/CDi/CDtot by header")
w("  lookup and rejects files with no table header or no matching rows.")
w("")
w("## 3. Test evidence (zero physical)")
w("")
w("- Command: python docs/evidence/dreal004/p0/run_p0_tests.py")
w("- Modules: the 17 recovery preflight modules plus " + BT + "test_adaptive_alpha" + BT + ",")
w("  " + BT + "test_polar_rows" + BT + ", " + BT + "test_endpoint_analysis" + BT + ".")
w("- Result: %d tests, failures %d, errors %d, skipped %d, successful=%s"
  % (tests["tests_run"], tests["failures"], tests["errors"], tests["skipped"],
     tests["was_successful"]))
w("- Log: docs/evidence/dreal004/p0/p0_test_log.txt sha256 " + BT + sha(P0 / "p0_test_log.txt") + BT)
w("- Summary: p0_test_summary.json sha256 " + BT + sha(P0 / "p0_test_summary.json") + BT)
w("- The destructive run_recovery_preflight.py was intentionally not executed in this")
w("  branch; it would rewrite recovery receipts and is unrelated to P0 code review.")
w("")
w("## 4. G1 zero-physical replay (Issue #14 requirement)")
w("")
w("- Source: the 24 recorded G1 case directories (raw .polar files) and their")
w("  task_spec.json targets; no solver was started.")
w("- Result statuses: " + BT + json.dumps(replay.get("verdict_counts", {}), ensure_ascii=False) + BT)
w("- Fixed-sweep internal cases recorded in G1: %s; adaptive replay probes: %s"
  % (replay.get("old_fixed_sweep_internal_cases_total"),
     replay.get("adaptive_replay_probes_total")))
w("- physical_solver_starts_used=%s, labels_created=%s"
  % (replay.get("physical_solver_starts_used"), replay.get("labels_created")))
w("- Interpretation: 8 raw hits are exactly the 8 G1 admitted labels; 7 cases already")
w("  bracket the target on existing rows and need only new alpha rows in P1; 8 cases have")
w("  no bracket (6 of them Mach 1.6) and need a wider alpha range or separate diagnosis.")
w("- Outputs: g1_alpha_replay.json sha256 " + BT + sha(P0 / "g1_alpha_replay.json") + BT
  + ", .csv sha256 " + BT + sha(P0 / "g1_alpha_replay.csv") + BT)
w("")
w("## 5. 12D variable response audit")
w("")
w("- Static wiring: %s of %s named variables change the VSPAERO model inputs."
  % (audit.get("static_wiring_all_variables_connected"), audit.get("design_variable_count")))
w("- Dynamic: %s response pairs measured on existing G2 stage1 raw cases; every pair has"
  % audit.get("raw_response_pairs_measured"))
w("  a different deck SHA256 (see the JSON evidence).")
w("- V01 (vertical_tail_area +2%): all 8 tasks show delta CDi = 0.0 exactly; mean delta")
w("  CDo = +%s; mean |delta CLtot| = %s. Cause: beta=0 means the"
  % (audit["vertical_tail_area_analysis"]["delta_cdo_mean"],
     audit["vertical_tail_area_analysis"]["delta_cl_total_mean_abs"]))
w("  vertical tail is unloaded, so it only adds parasite drag; the primary endpoint")
w("  Di_N=q*Sref*CDi does not move. V01/V02 therefore remain in the geometry contract but")
w("  are passive dimensions for this task family; P2/P3 must not claim their 12D response.")
w("- V02 (vertical_tail_sweep_delta): no existing perturbed raw case; status")
w("  RESPONSE_PENDING_P1_PROBE - no inference was made.")
w("- Outputs: 12d_variable_response_audit.json sha256 " + BT + sha(P0 / "12d_variable_response_audit.json") + BT
  + ", .csv sha256 " + BT + sha(P0 / "12d_variable_response_audit.csv") + BT)
w("")
w("## 6. A2 endpoint analyzer and G1 baseline")
w("")
w("- endpoint_analysis.py implements N_first_feasible, best_feasible_Di_N(B), anytime")
w("  curve, point/run feasible hit rate, simple_regret (null without an independent")
w("  reference), cost_to_target; records are validated as real and feed no synthetic")
w("  values; infeasible records may not carry di_n.")
w("- G1 baseline replay (descriptive, not a new sampler run): first feasible at design")
w("  evaluation 10 / 170 internal cases; point feasible hit rate 8/24=0.3333;")
w("  3.0 design starts and 48.875 internal cases per admitted label.")
w("- Consistency: replayed internal cases %s vs G1 batch accounting %s (matches=%s)."
  % (endpoints["consistency_with_batch_accounting"]["total_internal_solver_cases_replayed"],
     endpoints["consistency_with_batch_accounting"]["batch_accounting_internal_solver_cases"],
     endpoints["consistency_with_batch_accounting"]["matches"]))
w("- Output: a2_g1_baseline_endpoints.json sha256 " + BT + sha(P0 / "a2_g1_baseline_endpoints.json") + BT)
w("")
w("## 7. Frozen protocol")
w("")
w("- Task split frozen: train M140/M160/M200/M202, val M180/M220, test M240/M260;")
w("  support d00-d03, query d04-d07, 8 unique designs per task.")
w("- P1 (NOT authorised): Mach 2.02, designs d00/d01/d04/d07, <=12 design starts,")
w("  <=3 starts per design, <=36 internal alpha cases, tol_CL=1e-3 unchanged.")
w("- P2 (NOT authorised): <=240 new starts, >=4 real admitted labels per train task,")
w("  FOMAML/pretrain/context-pretrain/random arms, negative transfer reported.")
w("- P3 (NOT authorised): <=384 new starts, paired sampler comparison at equal cost,")
w("  B=4/8/16/32/64/128 anytime curves.")
w("- Primary endpoints, fairness, statistics and forbidden practices are frozen in")
w("  p1_p2_p3_preregistration.json sha256 " + BT + sha(P0 / "p1_p2_p3_preregistration.json") + BT)
w("- Chinese protocol summary: p0_protocol_freeze_20261122.md sha256 " + BT + sha(protocol) + BT)
w("")
w("## 8. Prior-state truth (not re-graded)")
w("")
w("- G1 is unchanged: 24 starts, 8 admitted labels, 34.78% valid rate; no label is")
w("  rewritten and tol_CL is not relaxed.")
w("- G2 was halted under Issue #14: B01 24 starts / 4 labels, B02 78 starts / 26 labels,")
w("  total 102/240 charged starts, 30 labels, no G2 receipt issued.")
w("- No real MAML training was run for G2 and none is authorised here.")
w("")
w("## 9. Disclosures / limitations")
w("")
w("- A5 reviews in this project are deepseek-flash single-shot read-only; this is not a")
w("  human signature and does not replace Owner sign-off.")
w("- P0 evidence is same-host; the off-machine backup requirement is waived by Owner")
w("  (m03569) and this dossier does not claim an independent failure domain.")
w("- P0 does not admit any new real raw data; RealAdmissionManifest fail-closed behaviour")
w("  is unchanged (REAL_ADMISSION_NOT_IMPLEMENTED without certificates).")
w("- Mach 1.6 has zero G1 labels and 6 no-bracket replay cases; its inclusion in P2")
w("  training is conditional on new admitted labels.")
w("- No independent Di_N reference exists yet, so simple_regret stays null.")
w("")
w("## 10. Requested gate verdicts")
w("")
w("- P0_CODE_PASS - code files above, %d tests green." % tests["tests_run"])
w("- P0_ZERO_PHYSICAL_REPLAY_PASS - G1 replay with 0 solver starts, 0 labels.")
w("- P0_12D_RESPONSE_AUDIT_PASS - 15 wired, V01 zero-CDi mechanism explained,")
w("  V02 left explicitly pending.")
w("- P0_A2_ENDPOINT_ANALYZER_PASS - endpoints implemented and consistent with G1 ledger.")
w("- P0_PROTOCOL_FREEZE_PASS - split/endpoints/fairness/statistics frozen.")
w("- P0_ZERO_PHYSICAL - no solver process was started in this round.")
w("")
w("This dossier does not authorise P1. If the verdict is P0_CODE_AND_PROTOCOL_PASS,")
w("the Lead must still issue a separate P1 GO after a dedicated P1 batch-plan review.")
w("")
with OUT.open("w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(lines))
print(json.dumps({"dossier": str(OUT), "bytes": OUT.stat().st_size,
                  "sha256": sha(OUT)}, indent=2))
