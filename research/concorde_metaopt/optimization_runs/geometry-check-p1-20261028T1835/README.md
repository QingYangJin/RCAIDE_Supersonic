# P1 geometry-check run geometry-check-p1-20261028T1835

This run checks the provisional 15-variable geometry model and the RCAIDE
vehicle adapter. It is **not** a Mission or CFD evaluation and reports no
objective value.

- stage: P1
- status: geometry_check_completed
- git_sha: 5e48037b40fbd58ff0df030754ab7a9e465fff27
- design_dim: 15
- cases: 31 valid (baseline + 15 variables x 2 directions)
- negative controls: 4/4 rejected or failed as expected (NC01_fuselage_volume_binding, NC02_span_order_inverted, NC03_chord_order_inverted, NC04_negative_fuselage_length)
- invalid perturbation cases: 0; derived failed_count: 0
- delta: 0.1 of each variable bound span
- invalid cases: none
- RCAIDE cross-checks: True
- true evaluations: 0
- wall_seconds: 2.227

Artefacts: summary.json, run_config.json, environment.json,
baseline_geometry.json, checks.csv, geometry_cases.jsonl,
geometry_effect_matrix.csv, geometry_effect_delta.csv,
geometry_negative_controls.csv, geometry_planforms.json and figures/.

Known unresolved upstream-declaration deviations are reported as WARN rows in
checks.csv (source_* checks); they are not repaired or hidden. Mass and CG are
PROVISIONAL_NOT_FROZEN and must not be used as frozen constraints before P2.
