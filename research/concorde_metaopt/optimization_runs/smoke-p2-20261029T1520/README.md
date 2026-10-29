# P2 single-cruise smoke run

Run id: smoke-p2-20261029T1520
Status: smoke_completed_with_failures
Git: c8bd8790359b08aa5cca4dc54921e6ca32ba07fe on research/concorde-metaopt
Task: concorde-fixed-cruise-p2-v1 (frozen mass contract)
Fidelity: single_cruise (RCAIDE mission, no CFD)

True evaluations: 5 (budget 5)
Baseline repeats: 3, relative spread 0.0 (tolerance 1e-06), passed=True

Cases:
- W01_plus_1pct: W01 361.8325 -> objective 36384.415908260984 (status VALID, feasible False)
- W10_plus_2deg: W10 2.0 -> objective 36479.34300305339 (status VALID, feasible False)

This run evaluates the RCAIDE single cruise segment only. It says nothing
about full-mission fuel burn, SU2/CFD fidelity or MAML benefit. The three
baseline repeats were executed with the cache disabled to measure true
repeatability; only valid evaluations are cached by the ledger.

Artifacts: summary.json, run_config.json, environment.json,
best_design.json, evaluations.jsonl, smoke_cases.csv, figures/.

Path note: workspace paths are displayed relative to the repository root.
