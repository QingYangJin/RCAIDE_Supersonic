# Run report: smoke-p2-20261029T1612

Rebuilt from the stored run artefacts; no Mission, CFD or OpenVSP call was executed.

## Summary

| field | value |
| --- | --- |
| stage | P2 |
| method | single_cruise_smoke |
| task_id | concorde-fixed-cruise-p2-v1 |
| experiment status | smoke_completed |
| report status | report_completed |
| git sha | 93c4e3525cd63ca1851d97c3ad589feb131c3086 |
| branch | research/concorde-metaopt |
| seed | 42 |
| design_dim | 15 |

## Recomputed headline numbers

| quantity | recomputed | stored in summary.json |
| --- | --- | --- |
| stored rows | 5 | null |
| true evaluations (sum of physical_call_count) | 5 | 5 |
| cache hits | 0 | null |
| VALID rows | 5 | null |
| feasible rows | 5 | null |
| first feasible evaluation | 1 | 1 |
| best feasible objective (kg fuel burn) | 34035.332605355274 | 34035.332605355274 |
| best design id | d-5417b9423870 | d-5417b9423870 |

| status | rows |
| --- | --- |
| VALID | 5 |

## Consistency checks

| check | subject | summary | recomputed | relative delta | status |
| --- | --- | --- | --- | --- | --- |
| R01 | total_true_evaluations | 5 | 5 | 0.0 | pass |
| R02 | best_feasible_fuel_kg | 34035.332605355274 | 34035.332605355274 | 0.0 | pass |
| R03 | first_feasible_evaluation | 1 | 1 | 0.0 | pass |
| R04 | best_design_id | d-5417b9423870 | d-5417b9423870 | null | pass |

## Constraint gate

| field | value |
| --- | --- |
| constraint names | geometry_invalid, task_mass_balance, fuel_capacity_excess, zero_fuel_excess, takeoff_excess, fuel_remaining_deficit, max_throttle, cruise_range_error, mission_convergence, trim_attitude_limit |
| all g <= 0 (strict) | False |
| all g <= 0 within tolerance | True |
| max constraint excess | 1.9991931146427733e-15 |
| feasibility tolerance | 1e-12 |
| positive offenders | 5 |

## Best design

| field | value |
| --- | --- |
| best feasible objective (kg) | 34035.332605355274 |
| best design id | d-5417b9423870 |
| baseline objective (kg) | null |
| improvement (kg) | null |
| first feasible evaluation | null |
| feasible | True |

## Artefacts

| check | value |
| --- | --- |
| recorded artefacts | 12 |
| present | 12 |
| missing | 0 |
| absolute paths | 0 |

## Figures

- smoke: repeatability.png + perturbation_sensitivity.png

Redraw command: python -m research.concorde_metaopt.reports.figures <run_dir>

## Method comparison

| run_id | stage | method | status | true evals | feasible rows | best kg | wall s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| smoke-p2-20261029T1612 | P2 | single_cruise_smoke | smoke_completed | 5 | 5 | 34035.332605355274 | 459.934 |
| smoke-p2-20261029T1520 | P2 | single_cruise_smoke | smoke_completed_with_failures | 5 | 0 | null | 398.476 |

Comparison written to comparison.csv and comparison.json.

## Notes

- smoke_completed

---

Report status: report_completed. Consistency failures: none. Artefact gaps: 0.
