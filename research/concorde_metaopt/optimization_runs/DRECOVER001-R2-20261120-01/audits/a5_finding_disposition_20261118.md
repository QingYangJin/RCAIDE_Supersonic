# A5 finding disposition matrix (2026-11-18)

Scope: RCAIDE Issue #12 R0/R1, zero physical. This file records, finding by finding, what the Lead
did with (a) the prior A5 verdict recorded in `a5_review_verdict.json` (review of snapshot 01c9274,
bundle bfe10ef5) and (b) the current A5 verdict recorded in `a5_review_verdict_c0723397.json`
(single-shot read-only dossier review of snapshot c0723397, bundle 3088b316).
It is a disposition record, not an approval: neither verdict is a human signature or a physical GO.

## A. Prior verdict (a5_review_verdict.json, reviewed 01c9274)

| # | Severity | Finding | Disposition | Evidence |
|---|----------|---------|-------------|----------|
| A1 | major | Same-host restore receipt lacked the owner-required "not an off-machine backup" label | FIXED | `local_restore_receipt.json` now records `off_machine_backup=false`, `backup_label=SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP` and an `owner_waiver` block; asserted by `run_local_restore.py` |
| A2 | major | Packet reported BACKUP_INDEPENDENT_FAILURE_DOMAIN CLOSED, conflicting with the Owner waiver | FIXED | `recovery_readiness.json` counts `waived=1`; gate state is `WAIVED`; packet gate state is `WAIVED`; `assess_recovery_readiness.py --check` fails if it is not |
| A3 | minor | R0 inventory is R0_PARTIAL_NOT_AUDITED, so R0 may pass only with disclosure | DISCLOSED, STILL OPEN | `recovery_inventory.json.status=R0_PARTIAL_NOT_AUDITED`; packet claims say "offline records, not independently audited"; R0 gate blocker keeps the human-signature gap |
| A4 | info | REAL_ADMISSION remains fail-closed and no R2 preregistration or Lead GO exists | DISCLOSED, STILL OPEN (by design) | `meta_dataset.py` still raises `REAL_ADMISSION_NOT_IMPLEMENTED` without certificates; no real raw admitted; R2 not preregistered; `physical_go=NOT_ISSUED` |

No prior finding is marked resolved by argument alone; A1/A2 have machine-checkable evidence, A3/A4
remain open and are carried into the blocker list.

## B. Current verdict (a5_review_verdict_c0723397.json, reviewed c0723397)

| # | Severity | Finding (abridged) | Disposition | Evidence / action |
|---|----------|--------------------|-------------|-------------------|
| B1 | major | Real admission is not proven over real raw bytes and does not prove real physics | ACCEPTED, OPEN | No real raw artifact exists yet (F1R2/F2R2 are RAW_LOST). The protocol stays fixture-only; `REAL_ADMISSION` is explicitly non-passing; R2 must admit at least one independently audited real raw artifact before any physics claim |
| B2 | major | CLOSED gates could be mistaken for PASS; prior A5 findings lack a closure record | PARTIALLY FIXED | This matrix is the finding-by-finding disposition record (A1–A4, B1–B10). Packet `a5_review` block and `known_limitations` state that CLOSED means "evidence for the gate was checked", never PASS or approval. Human/Owner sign-off remains absent and is listed as a blocker |
| B3 | major | Same-host restore is not an independent backup and must not be treated as one | DISCLOSED; OWNER-WAIVED, NOT PASS | Receipt label and `backup_restore_pass=false` retained; packet says WAIVED is not PASS |
| B4 | major | Zero-physical rehearsals could be read as real MAML/physics results | DISCLOSED | A2 carries `SOFTWARE_FEEDBACK_REHEARSAL_ONLY_NOT_PHYSICAL_EVIDENCE`; M2 receipt is labelled offline rehearsal; M1 uses a structural placeholder authorization; packet claims say so; M2 hardcoded `native_probe_status` strings are called out as non-authoritative in `known_limitations` |
| B5 | major | A1 geometry freeze v2 is not aerodynamic validation and keeps open physics items | DISCLOSED | `geometry_freeze_v2.json.open_items` records force-axis signs, WING_AC moment origin, provisional mass/CG and missing VSPAERO read-back; packet claim and limitation repeat it; R2 preregistration must include the read-back |
| B6 | major | Prior A5 CHANGES_REQUIRED findings were not shown closed finding by finding | FIXED (record), OPEN (substance) | Section A above; A3/A4 remain open and are not claimed closed |
| B7 | major | M1 batch control is not authorized by a real Lead GO | ACCEPTED, BLOCKED | No M1 label batch is run; M1 gate blocker and packet claim state that a new A5 gate + Lead batch GO is required |
| B8 | minor | Two OpenVSP probe JSONs are ambiguous about which record is authoritative | DISCLOSED | Packet limitation names the authoritative post-repair record `a1_thickness_repair/real_openvsp_geometry_probe.json` (SURFACE_DIAGNOSTIC_PASS_NOT_FREEZE) and says neither probe is a solver freeze or physics validation |
| B9 | minor | Some R0 claims are REPORT_PRESENT only and one requirement tail is UNKNOWN | DISCLOSED | `needed_for_next_run.json` integrity note and packet limitation; neither is used as raw identity evidence |
| B10 | minor | OpenVSP export reproducibility is not asserted across machines | DISCLOSED | `geometry_freeze_v2_verification.json` records the OpenVSP runtime `_vsp.pyd` SHA and installation path; packet limitation says byte-identical re-export across machines is not asserted |

## C. Review method and limits (must be quoted with the verdicts)

- Both A5 reviews were performed by a `deepseek-flash` reviewer subagent created by the Lead at the
  Owner's instruction (m03569). The reviewer is a model, not a human, and grants no authorization.
- `a5_review_verdict.json`: read-only tool loop, cut by HTTP 524 after 16 steps, verdict derived from a
  compact transcript digest.
- `a5_review_verdict_c0723397.json`: single-shot review over a harness-assembled dossier
  (`a5_review_dossier_c0723397.txt`); the reviewer had no tools and did not inspect files independently.
  Dossier assembly (hashing, verifier execution) was performed by the Lead's harness, so content
  selection is not fully independent of the Lead.
- Neither verdict is `READY_FOR_NEW_REAL_BATCH`; both are `CHANGES_REQUIRED`; `physical_go_granted=false`
  and `human_signature=false` in both records.
