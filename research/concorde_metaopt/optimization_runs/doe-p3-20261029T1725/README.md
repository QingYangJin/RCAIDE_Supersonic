# DOE screening run doe-p3-20261029T1725

Stage: P3 | method: doe_screening | git: 047621f3ab04c781d127e751265c90ff461ceb9b | seed: 42

This run only samples and screens geometry. It performs **zero** Mission,
VLM, VSPAERO or SU2 calls; no candidate has an objective value.

## Counts

- requested candidates: 160
- written candidates: 160
- duplicates removed: 0
- geometry valid: 160
- geometry invalid: 0
- geometry errors: 0
- physical evaluations: 0 (this is not an optimisation run)

## Files

- candidates.jsonl / candidates.csv: one row per candidate
- data_manifest.json: provenance, config hashes and file hashes
- validation.json: independent re-validation report (if enabled)
- run_config.json / environment.json / summary.json

## Method

Batches: batch-000 (32 samples, lhs), batch-001 (128 samples, lhs)

Sampling is scipy qmc (lhs) over the frozen unit box, mapped through the
design_space_15d config. Geometry legality is screened with the same
dependency-free model used by geometry-check; failed checks are recorded,
never converted into a fake objective.

## Limitations

- bounds are still provisional_until_geometry_perturbation (frozen: false)
- no aerodynamic or mission validity is claimed for any candidate
- P3 physical evaluation of candidates requires an approved budget
