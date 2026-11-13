# M0-R Formal Package (A3 task-57, zero physical, not a gate)

Status: M0R_PACKAGE_FROZEN_PENDING_A5_GATE.

- New family SHA256: 98b84f5ecf6e18a7be90e21da41b243dccb664f09034366ea3b58d777f1c0311
- A1 code commit: 0c514151d989de716dbb855973b900a34615b5aa
- A1 freeze commit: c5698a218fad974e8e96b604573c5cc79b3abb32
- A5 gate: G-M0R-ADMISSION-01 PENDING (A5 owns it)
- Zero physical: physical=0, solver_started=false, no run dir/ledger/token/authorization
- fuel_burn_kg=null; physics NOT_VALIDATED; single seed descriptive;
  no winner/significance/cross-family.

A5 wording corrections applied explicitly:

1. SREF runtime value from post-fix baseline is the only source. 358.25000000000006 is
   a validation anchor constant only; it must not be used as the runtime SREF input.
2. solver_input_sha256 contains a path-dependent .vkey and is not a cross-process
   expected value. Deterministic binding is deck_sha256 + vspgeom_sha256. A2 runner must
   not gate on solver_input_sha256.
3. M2.02 continuity with F1R2 is q/physical-condition continuity only; decks are not
   byte-continuous and F1R2 expected polar is not inherited. M1-A rebuilds the admission
   baseline.
4. Deck freeze boundary: the full family deck space is 3 designs (B0-01, B1-01, C5) x 6 tasks = 18
   entries. The 6 B0-01 baseline decks are frozen here. The 12 B1-01/C5 reference entries are
   unfrozen reference. M1-A requires 12 deck slots (4 M1 tasks x 3 designs): the 4 B0-01 slots are
   already frozen, and the 8 B1-01/C5 slots must be frozen or deterministically regenerated before
   M1-A authorization. The remaining 4 B1-01/C5 meta_test slots must be frozen before M3-A. The
   M1-A_REQUIRED_DECK_SET in M0R_DECK_FREEZE.json lists all 12 slots with frozen_status.

pre_draft/ is retained as the historical task-60 appendix. It is not the formal
package and must not be used as A5 gate input. See M0R_PREREGISTRATION_ZH.md for
the Chinese preregistration.
