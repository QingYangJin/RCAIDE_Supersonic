# L-11 Lead decision: R8 attempt-1 setup stop (zero physical) and R9 authorization

- decision_id: L-11
- decision: CONTINUE_WITH_R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX
- decision_utc: 2026-11-11T17:20:00Z
- decision_maker: lead
- physical_authorization: false (this decision authorizes R9 packaging and gate work only; no solver start until a signed R9 approval + post-approval dry-run + A5 C-gate + Lead GO)
- policy_basis: protocol D (L-09), R8 prefrozen reuse (L-10), user instruction m01474 (continue)

## 1. R8 attempt-1 facts (all Lead-independent rechecked)
- start 2026-11-11T17:14:09Z, stop 2026-11-11T17:14:11Z, PID 8160.
- launcher GATE=PASS; zero-physical launcher prefrozen gate PASS 79 checks, static_index_count=119, a1_runtime_guard all_equal=true, triples=6, evidence prestart_prefrozen_gate.json sha256 533263b7ce6982cf79e6ed20345c68dd4f90a4e4ad945633c5fd44ff68e8321b / 37,476 B.
- executor_prestart.json sha256 72a51f0c9121af10d20cd6cd1e617fa36dbb85e11e92dab7dd37d15f83bdc160 / 12,545 B.
- executor then failed in its own _prefrozen_reuse_gate: FreezeRecordError: PREFROZEN_GEOM_MISSING d51866f7d3c49303/462x401 (p2a_v2_executor.py:1117 -> p2a_v2_runtime.py:577).
- stop_report.json sha256 729eae0f339558881139cf593bfc998f9498a5fb5a4c63139ccb5a5edc07cb6b / 2,303 B, phase=setup, physical_solver_starts=0, physical_call_count=0, ledger_starts=0, ledger_ends=0, pending 0.
- no preflight_result.json, no solver_attempts.jsonl, no cases/, no batch_summary.json; no retry; R8 charged 0 starts / 0 internal; cumulative remains 56 starts / 404 internal.
- root cause (A2 code-level, Lead confirmed location): initial_designs_manifest.json family rows are FLAT (frozen_vspgeom_path/sha/bytes, frozen_vkey_sha256, frozen_vsp3_sha256, canonical_mesh_sha256 at row level, no nested "frozen"); p2a_v2_runtime.py:574 and p2a_v2_executor.py:1131 read only nested row["frozen"], produce empty mapping, and the executor prefrozen gate raises PREFROZEN_GEOM_MISSING. The launcher-side gate module already handled flat rows, so the launcher gate PASSed.
- process gap: R8 pre-GO evidence exercised only the launcher-side prefrozen gate, never the executor-side _prefrozen_reuse_gate on the production code path; that is why the incompatibility was not caught before GO.

## 2. Decision
R8 is closed as SETUP_STOP_PREFROZEN_GEOM_MISSING with zero physical consumption; its approval is not reused and R8 is permanently excluded from E1-E6. A new R9 cycle is authorized with a minimal execution-layer fix (flat/nested family-row compatibility in A2 runtime/executor) and a mandatory zero-physical smoke that exercises the executor-side prefrozen gate end to end before signature.

## 3. R9 identity and bounds
- batch_id: DREAL001-P2-20261111-14
- run_id: DREAL001-P2A2R9-20261111-01
- run_dir: D:\RCAIDE\dnext001\wt-real-a2-optimizersesearch\concorde_metaopt\dreal001uns\DREAL001-P2A2R9-20261111-01 (new empty)
- window: 2026-11-11T17:30:00Z - 2026-11-12T04:00:00Z
- window token: WINDOW_OK-P2AV2R9-20261111T1730Z-20261112T0400Z
- execution-start deadline 2026-11-11T21:00:00Z; clean-stop 2026-11-12T02:30:00Z; hard stop 2026-11-12T04:00:00Z
- planned: 390 starts / 2,730 internal (2 preflight + 4 diagnostic starts + 384 main)
- caps: max 451 starts / 3,157 internal; reserve 64
- cumulative: 446 starts / 3,134 internal (prior 56/404 + R8 0/0 + R9 390/2,730); headroom 5 starts / 23 internal
- supersedes: R8 approval sha256 fa0d94a2be7ea2dcb6828b85b0cc032885829a9c8fe904e993bb40535c981f46 / 75,166 B / physical_call_count_at_supersede 56 / run DREAL001-P2A2R8-20261111-01
- amendment seq 9: action R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX, physical_call_count_at_amendment 56
- R9 is the FINAL execution attempt under the current caps. If main fails again the R line terminates with an incident receipt; no R10 is authorized by this decision.

## 4. Required fix boundary
- permitted: A2 p2a_v2_runtime.py / p2a_v2_executor.py flat-row compatibility, tests, smoke and reporting/evidence additions; new R9 package/launcher/dry-run tool.
- forbidden: A1 frozen bytes, plan scientific fields, protocol D policy, caps/planned numbers, R1-R8 evidence bytes, R8 run dir, any retry, any pre-GO solver start.
- required pre-GO evidence: zero-physical smoke that runs the executor-side prefrozen gate on the actual R9 run dir and initial_designs_manifest and records PASS evidence (no PREFROZEN_GEOM_MISSING).
