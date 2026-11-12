# L-15 Lead decision — R10 accounting must be reported on two bases (charged vs actual physical)

- decision_id: L-15
- decision: CLARIFY_R10_ACCOUNTING_TWO_BASES_NO_POLICY_CHANGE
- physical_authorization: false
- related: L-09, L-12, L-13, L-14; A3 R10 stats commit 699ce2abfcbeef3a47934bfa88bb173ec00ac489

## Trigger
A3's independent R10 statistics review (commit 699ce2a, docs/evidence/dreal001/r10_stats_20261111.{json,md,csv}) established that the cumulative figure 448/3148 used in the R10 approval, the R10 batch summary field cumulative_charged_starts/cumulative_charged_internal_cases, L-14 and A2's stop note is an authorization/reservation (charged/projected) quantity, not physical consumption:
- charged/projected = prior actual 62/446 + R10 planned reservation 386/2702 = 448/3148; the signed caps 451/3157 are checked on this charged basis (headroom 3/9).
- R10 actual physical consumption = 91 starts / 637 internal cases (preflight 2/14 + diagnostics 0/0 + main 89/623).
- cumulative actual physical consumption = 62 + 91 = 153 starts / 446 + 637 = 1,083 internal cases; actual remaining capacity against the caps = 298 starts / 2,074 internal cases.

## Decision
- No policy, approval, caps, package or evidence byte changes. R10 is accepted as the final execution attempt under L-12/L-14 (no R11).
- All downstream reporting (A5 post-run audit, Issue #9 receipt, A3/A4 appendix, Lead final answer) must present the two bases explicitly and never describe 448/3148 as consumed physical budget.
- Recommended wording in the receipt:
  1. Authorization/charged basis: R10 planned reservation 386/2,702; cumulative charged 448/3,148 against caps 451/3,157 (headroom 3/9); caps are enforced on this basis.
  2. Actual physical basis: R10 actual 91/637; cumulative actual 153/1,083; remaining actual capacity vs caps 298/2,074.
- The earlier L-14 wording "Cumulative 448 starts / 3,148 internal against signed caps ... headroom 3 starts / 9 internal" remains literally correct on the charged basis but must be annotated as charged/projected; A2's stop note wording must be corrected by disclosure/addendum, not by editing committed bytes.

## Consequences for the receipt
- The pilot remains NOT COMPLETED: preflight 2/2 PASS_BYTE; diagnostics 0/0 as preregistered; main stopped by the pre-registered protocol-D scientific auto-stop at 48 evaluations / 13 invalid (27.08% > 25%); BO COMPLETED (32 evaluations, 23 valid), DE STOPPED (16 evaluations, 12 valid per evaluations.jsonl; batch summary valid_designs=11 is a known reporting discrepancy), PSO / A-BO / A-DE / A-PSO NOT_RUN.
- Endpoints E1-E6 of the six-arm pilot are NOT_COMPUTABLE (A3); only descriptive BO/DE observations exist; no winner, no significance, no cross-family pooling; fuel_burn_kg=null; physical_validation_status=NOT_VALIDATED.
