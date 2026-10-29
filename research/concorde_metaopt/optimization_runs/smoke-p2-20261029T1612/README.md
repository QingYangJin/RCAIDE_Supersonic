# P2 single-cruise smoke run

Run id: smoke-p2-20261029T1612
Status: smoke_completed
Git: 93c4e3525cd63ca1851d97c3ad589feb131c3086 on research/concorde-metaopt
Task: concorde-fixed-cruise-p2-v1 (frozen mass contract)
Fidelity: single_cruise (RCAIDE mission, no CFD)

True evaluations: 5 (budget 5)
Frozen mass contract: start 136000 kg, loaded fuel 46800 kg, ZFW 89200 kg
Baseline repeats: 3, relative spread 0.0 (tolerance 1e-06), passed=True

Cases:
- W01_plus_1pct: W01 361.8325 -> objective 34035.332605355274 (status VALID, feasible True)
- W10_plus_2deg: W10 2.0 -> objective 34117.55529648991 (status VALID, feasible True)

This run evaluates the RCAIDE single cruise segment only. It says nothing
about full-mission fuel burn, SU2/CFD fidelity or MAML benefit. The three
baseline repeats were executed with the cache disabled to measure true
repeatability; only valid evaluations are cached by the ledger.

Artifacts: summary.json, run_config.json, environment.json,
best_design.json, evaluations.jsonl, evaluations_detail.jsonl,
smoke_cases.csv, figures/.  The detail file repeats every true
evaluation with the full backend record (mission responses and geometry
cross-check); the compact evaluations.jsonl keeps the Issue schema.
Commit note: the frozen mass-contract line was corrected in commit 6f6f215
(the nested applied/readback record previously rendered as None). This README
was regenerated from the unchanged summary.json; no evaluation was re-run and
the five recorded true evaluations were produced at 93c4e35.
