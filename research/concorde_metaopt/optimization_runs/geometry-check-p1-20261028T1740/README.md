# P1 geometry-check run geometry-check-p1-20261028T1740

This run checks the provisional 15-variable geometry model and the RCAIDE
vehicle adapter. It is **not** a Mission or CFD evaluation and reports no
objective value.

- stage: P1
- status: geometry_check_completed
- git_sha: 0fd5e0fcf179f620b5b4685ee2031332c8247f47
- design_dim: 15
- cases: 31 (baseline + 15 variables x 2 directions)
- delta: 0.1 of each variable bound span
- invalid cases: none
- RCAIDE cross-checks: True
- true evaluations: 0
- wall_seconds: 2.291

Artefacts: summary.json, run_config.json, environment.json,
baseline_geometry.json, checks.csv, geometry_cases.jsonl,
geometry_effect_matrix.csv, geometry_effect_delta.csv,
geometry_planforms.json and figures/.

Known unresolved upstream-declaration deviations are reported as WARN rows in
checks.csv (source_* checks); they are not repaired or hidden. Mass and CG are
PROVISIONAL_NOT_FROZEN and must not be used as frozen constraints before P2.
