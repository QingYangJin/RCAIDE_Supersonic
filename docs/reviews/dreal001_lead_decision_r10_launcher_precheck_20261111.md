# L-13 Lead decision — R10 launcher condition-count precheck fix (post-GO, non-substantive)

- decision_id: L-13
- decision: CONTINUE_R10_AFTER_LAUNCHER_CONDITION_COUNT_PRECHECK_FIX
- physical_authorization: false (no new authorization; R10 GO record already issued)
- batch_id: DREAL001-P2-20261111-15
- run_id: DREAL001-P2A2R10-20261111-01
- date_utc: 2026-11-11
- signed GO: lead_go_r10_20261111T1856Z.json SHA256 260e284a5c9939b9be2ee08e9a2e986d43345818e682ce34ecff91926a91b83a / 9,962 B, GO_TOKEN LEAD_GO_P2AV2R10_EXEC_20261111T185534Z
- signed approval: 4e67eac52833d8dfab8b8027a0838b68de15f26d9a072edb0515ece22414068c / 84,140 B, conditions 57
- A5 gates: G-P2AV2R10-PRE 48b91bf67b6b9f0f9e27e69fb6b5aca1fec3a15f; C-P2AV2R10-02 6f1498119c3a8e5d5283386dddda73ce0773c506

## Facts
1. 2026-11-11T18:56:53Z first launcher start was refused before any solver spawn by the launcher pre-start self-check: `RuntimeError: approval conditions count unexpected`. The launcher (SHA256 476481e65674d30450b03eb85f7fc44bca06323213161d53ddc652c218690bc8 / 29,361 B) hard-coded an expected count of 52 conditions; the signed R10 approval contains 57 conditions (A5 added 5 R10-specific conditions). Refusal produced no ledger rows, no cases and no physical solver starts.
2. A2 changed exactly one line in docs/evidence/dreal001/p2av2r10_launch.py: line 413 expected count 52 -> 57. New launcher SHA256 23106df237add53c99e54642b616349fc8d7bf411fc1488df1456f9d7d65861b / 29,361 B (same byte count). No other line changed (pins executor ed0f2324 / plan ba6eaa49 / identity 7e339188, GO/approval/dry-run verification, prefrozen gate call, window/token checks, prestart and executor invocation unchanged).
3. A2 restarted at 18:58:01Z (PID 27588): GATE=PASS, prefrozen gate PASS (a87b0288.../37,480 B, static_index_count 119, A1 guard all_equal=true, triples 6), preflight started 18:58:04Z; by 19:00:46Z 17 starts/17 ends, single writer PID, no stop.
4. A5 independently diffed the launcher bytes from commit 5f1f74e against the current file: exactly the 52->57 line; verified zero solver/ledger/cases artifacts in 18:56:53Z-18:58:01Z and that the refusal is correctly attributed to the fail-closed self-check (executor_run.log is a merged two-attempt log: REFUSED line from 18:56:53Z plus env/STARTED lines appended at 18:58:03Z).

## Decision rationale
- The signed approval does not bind the launcher SHA; its execution bindings are a2_executor_sha256=ed0f2324 and executor_blob, plan/identity SHAs, and the A1 frozen bytes. The launcher is an A2-owned operator wrapper whose pre-start check must agree with the signed approval; with 57 conditions the old 52 line would refuse every start.
- The change is a fail-closed pre-start validation correction only: it cannot alter solver inputs, family reuse, accounting, endpoints, caps, windows, or any scientific policy. It was made after GO and after the A5 C gate anchored the old launcher SHA, which is a process deviation that must be ratified and disclosed, not concealed.
- Stopping the already-running batch would discard a legitimate attempt whose pre-launch state was zero-physical, without improving scientific validity. A5 concurs (no dissent) that this is non-substantive and that execution may continue.
- Any further change to execution-layer bytes (launcher/executor/gate/plan/approval/A1) after this decision is a hard stop and requires a new batch/approval.

## Required records
1. A2 must preserve the merged executor_run.log bytes, the original launcher bytes from commit 5f1f74e, the one-line diff, and the old/new launcher SHAs in the R10 evidence commit and the post-run report.
2. A5 must record this as disclosure D-11 in the R10 post-run audit and Issue #9 receipt, update the launcher anchor to 23106df2..., and preserve the C-gate old anchor (476481e6) traceability.
3. The R10 approval, package bytes, executor bytes and A1 frozen bytes remain unchanged; the launcher fix does not reopen signature, and the batch remains the final attempt under L-12 (no R11).

## Status at writing
R10 execution in progress (started 18:58:01Z; preflight 2/2 SOLVED_VALID, main BO running; diagnostics DIAGNOSTICS_NOT_IN_MATRIX 0/0 as preregistered). This record authorizes no additional execution beyond the signed R10 approval and GO record.
