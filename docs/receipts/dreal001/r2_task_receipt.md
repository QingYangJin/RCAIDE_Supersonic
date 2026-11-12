# D-REAL-001 A2 Task Receipt — real solver-in-loop fair optimizer framework

- Role: A2 / r2-optimizers
- Shared task: task-7 (claimed, rev2, in_progress)
- Worktree: `D:\RCAIDE\dnext001\wt-real-a2-optimizers`
- Branch: `research/dreal001-a2-optimizers` (base commit `683a868`; NOT pushed — Lead owns push/merge)
- Receipt generated: 2026-11-10 ~21:25 CST
- Real VSPAERO starts issued by this role: **0** (physical_solver_starts = 0; P0/P1 gate not passed by A2; no real-solver command was ever launched by A2 code in this receipt)
- Evidence class of every result below: **SYNTHETIC_NOT_REAL_SOLVER / protocol+mock only**. No statement here is aerodynamic or fuel-burn evidence.

## 1. Commits (author QingYangJin, prefix [D-REAL-001] A2)

| Commit | Subject | Content |
|---|---|---|
| `c11f40b` | A2: lift-match evaluator protocol, solver-start ledger, cache isolation, six-arm runners, preregistered pilot | 9 files, 3424 lines: evaluators.py, arms.py, ledger.py, cache.py, design.py, lift_match.py, pilot.py, records.py, task.py |
| `ad5c6cb` | A2: fix arm harness contract (budget exception, DE/PSO feasibility mapping, BO natural completion) | 3 files +29/−9 |
| `f70c403` | A2: pytest suite for six-arm fairness, cache isolation, ledger and mock e2e pilot | tests/test_dreal001_r2_optimizers.py (293 lines, 8 tests) + pilot synthetic evidence fields |
| `8606afa` | A2: mock end-to-end pilot (SYNTHETIC, physical=0) and P2 preregistration template | runs/dreal001/ 151+ files (12 run dirs + batch + P2 template) |

HEAD at receipt time: `8606afa`; `git status --short` clean for tracked files at commit time.

## 2. Deliverable status (against task-7)

| # | Deliverable | Status | Evidence |
|---|---|---|---|
| 1 | Unified lift-match evaluator `evaluate(x12, task)` + Mock/Replay/Real backends on one protocol; alpha lift matching; evaluations.jsonl + solver_attempts.jsonl; design-hash cache, cached_reads, no ground-truth label leak to warm-start arms | DONE (Mock/Replay fully; Real adapter coded, gated on approved approval + A1 callable, never invoked against a real solver) | `optimizers/evaluators.py` (863 L), `lift_match.py` (83 L), `ledger.py` (235 L), `cache.py` (113 L); pytest coverage |
| 2 | Six arms BO / DE / PSO / A-BO / A-DE / A-PSO behind unified `(task, design_space, B, seed, warmstart=None)`; per-eval history CSV, anytime best valid D_i, first_feasible_solver_start, valid_solve_rate | DONE, mock-verified on all six arms | `optimizers/arms.py` (516 L); standalone B=8 all COMPLETED, 8 starts each, physical=0; mock pilot batch 12 runs |
| 3 | Fair budget = physical_solver_starts (not evaluation count); A-arm warm-start sampling/surrogate scores never produce real labels; preregistered B/seed, no post-hoc tuning | DONE: fail-closed pre-authorized SolverStartLedger, zero-cost synthetic support in ledger, arm artifacts record labels_visible_to_arm=false / warmstart provenance physical_call_count=0 | `ledger.py`, `cache.py`, `arms.py`; tests for over-budget, double-settle, cache isolation, label store run isolation |
| 4 | Mock/replay end-to-end validation: budget conservation, cache isolation, multi-seed reproducibility, six-arm interface consistency; pytest tests/test_dreal001_r2_*.py | DONE: `8 passed in 2.59s` | `research/concorde_metaopt/tests/test_dreal001_r2_optimizers.py`; mock pilot batch below |
| 5 | Preregistered pilot runner (B=64/128, >=3 seeds/arm, stop-batch/resume), run_config.json / approval.json templates; real batches only after Lead approval and P0/P1 pass | DONE (runner + templates); REAL path implemented but NEVER executed; approval template `approved=false` | `optimizers/pilot.py` (716 L); `runs/dreal001/P2_PREREG_TEMPLATE_20261110/` |
| 6 | This receipt | DONE | `docs/receipts/dreal001/r2_task_receipt.md` |

## 3. Test command and result (verbatim)

```
D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r2_optimizers.py -q -p no:cacheprovider
........                                                                 [100%]
8 passed in 2.59s
```

Coverage (8 tests):
1. mock D_i = q·Sref(x)·CDi and lift L = q·Sref(x)·CLtot internal consistency + lift-match residual;
2. SolverStartLedger pre-authorization fail-closed (over-budget raises), double-settle raises, starts counted per launch;
3. cache isolation across runs (same design in different run/task/solver-config not shared) and `labels_visible` false from warm-start side;
4. VisibleLabelStore isolation per run (warm-start arm cannot read another run's real labels);
5. six-arm budget conservation: starts_used == planned B, physical=0 for mock, any-time curve monotone, artifacts written;
6. same-seed reproducibility of arm histories (identical design sequence);
7. REAL backend refuses construction without callable + approved approval.json (3 refusal paths);
8. mock pilot end-to-end: run dirs, run_config/summary/evaluations/solver_attempts/optimization_history/anytime_curve/data_manifest/SHA256SUMS all present, batch conservation, evidence_statement=SYNTHETIC_NOT_REAL_SOLVER.

## 4. Mock end-to-end pilot (SYNTHETIC; not real solver evidence)

- Batch id: `dreal001_a2_mock_e2e_20261110`
- Path: `runs/dreal001/dreal001_a2_mock_e2e_20261110/`
- Matrix: 6 arms × B=8 × seeds {0,1} = 12 runs; every run COMPLETED; starts 8/run; planned 96 = simulated 96; `physical_solver_starts = 0`; `budget_conserved=true`; `errors=[]`; `fuel_burn_kg=null`; `evidence_statement=SYNTHETIC_NOT_REAL_SOLVER`.
- Per-run artifacts: run_config.json, summary.json, evaluations.jsonl, solver_attempts.jsonl, optimization_history.csv, anytime_curve.csv, data_manifest.json, SHA256SUMS.txt.
- Batch artifacts and SHA256:
  - plan.json — `1c2c9d461e0b65557f3e1b194fb1e9956c1dd0c2211d6e48bb3ec4c66eaf44e2`
  - approval.json (approved=false) — `23a109cd3ebc8a666f4d15f7308765c1286b03f6ded47b4407ac6fe4656027c3`
  - batch_summary.json — `0f45cb389c216fa3a0929d8b6f1ff83d0c483391fb7f4bcdc95fa225465e6c74`
  - batch_metrics.csv — `c0affc5cbbecfb51518cab68373a9513fbfc012cffc63c1ea4846b487ee9f85e`
  - batch_SHA256SUMS.txt — `3bfa245b44f5cfc4b037add1502043a6f386908187ac41dbbc25f6124592a7f1`
  - example `runs/dreal001_a2_mock_e2e_20261110__ade__B008__s0/summary.json` — `7500c5380c9c92acc9de011cea330c0908652dd622570ac63d72784eb570dfcb`

## 5. P2 preregistration template (not executed)

- Path: `runs/dreal001/P2_PREREG_TEMPLATE_20261110/`; `approval.json` has `approved=false`, no batch may start from it.
- plan.json — SHA256 `6f8b8a4c795a4fa75fa09034ce1bd4937731c1f81b51854be98f773e4d1761e7`
- approval.json — SHA256 `4cb42ceb41196ad0afd8a94dac7ee74b87bae588848b97b8d8033f9f21a7aaaa`
- Matrix: 6 arms × B ∈ {64,128} × seeds {0,1,2} = 36 runs; planned_starts = 3456 (576/arm); backend=REAL; budget_metric=physical_solver_starts; A-arm warm-start support_size=16; `fuel_burn_kg=null`; no B-line evaluation enters the A2 objective.

## 6. Real-evaluator interface contract expected from A1 (for wiring P2a)

Adapter: `research/concorde_metaopt/dreal001/optimizers/evaluators.py:827` (`RealVspaeroAdapter`).
Construction requires all of: callable `evaluate_fn`, approved approval.json with `approved=true`, `batch_id` equal to the run's batch id, `max_starts>0`, and A1 `solver_attempts.jsonl` path (for ledger cross-verification). Otherwise `RealSolverNotAuthorized` is raised and no process is launched.

Expected A1 callable:

```python
record = evaluate_fn(vector_12d_unit_box,
                     case_id=str,           # unique per design/case
                     meta={"arm": str, "seed": int, "phase": str,
                           "batch_id": str, "run_id": str})
```

Expected returned Mapping:

```python
{
  "status": "SOLVED_VALID" | "SOLVER_FAILED" | "GEOMETRY_INVALID" | "LIFT_MATCH_FAILED" | "NOT_RUN",
  "backend": "REAL_VSPAERO",
  "solver": {"physical_solver_starts": int, "solver_config_sha256": str, "command": [str, ...]},
  "geometry": {"geometry_sha256": str},          # rebuilt per design, never copied
  "results": {"alpha_deg": [float], "cltot": [float], "cdi": [float],
              "cdo": [float], "cdtot": [float], "cmy": [float]},   # alpha sweep in ONE record
  "attempt_ids": [str], "raw_artifacts": [dict], "errors": [dict],
}
```

When `physical_solver_starts > 0`, A2 ledger calls `verify_external_attempts(design_hash, expected_starts)` against A1's `solver_attempts.jsonl`; mismatch is an accounting violation. Multi-alpha single-process sweep is assumed by this contract and is still to be confirmed by A1 (it decides starts-per-design and the P2a 384-start budget).

P2a driver readiness: `pilot.run_pilot(backend=REAL)` already supports the preregistered matrix, per-run SolverStartLedger + cache + label store, per-case evaluations.jsonl/solver_attempts.jsonl, batch summary/metrics/SHA256SUMS, resume (skip completed runs by existing summary), STOP-file batch halt, and hard approval gating. Missing for P2a execution: A1 `evaluate_fn`, A1 attempts path, real-adapter factory injection, Lead scheduling approval and signed approval.json. ETA for wiring once A1 API lands: ~1–2 h + A5 pre-review; real batch duration is Lead-scheduled.

## 7. Known limitations / risks

1. A1 real API was not present in this worktree at receipt time (`grep -r EVALUATOR_API|dreal001.geometry` → no match); adapter may need a thin schema adjustment when A1's actual signature lands.
2. Alpha-sweep-in-one-process capability unconfirmed (affects starts accounting/fairness); must be fixed before preregistration is frozen.
3. Real backend path exercised only through refusal tests and a synthetic callable shape; it has never been run against OpenVSP/VSPAERO.
4. BO/ABO "used full budget" now reports COMPLETED instead of BUDGET_EXHAUSTED; DE/PSO feasibility uses the lift-match residual constraint (C00_lift_match_rel_error <= 0, LIFT_TOL_REL=1e-3).
5. All performance numbers in mock runs are synthetic and MUST NOT be quoted as aerodynamic or fuel evidence. `fuel_burn_kg = null` until independent validation.
6. Not self-audited: A5 independent re-run of the pytest suite and mock-pilot SHA256 verification is required.

## 8. Reproduction commands

```powershell
# tests
D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r2_optimizers.py -q -p no:cacheprovider

# mock e2e pilot is committed under runs/dreal001/; regenerate with:
D:\RCAIDE\envs\RCAIDE\python.exe -c "from research.concorde_metaopt.dreal001.optimizers.pilot import run_pilot"  # see pilot.py __main__ block
```

## 9. Explicit non-claims

- SOLVER_LOOP_VERIFIED: **not claimed by A2** (protocol only; mock/replay evidence).
- INTERNAL_AERO_OPTIMIZATION_GAIN: **not claimed**; mock objectives are synthetic.
- EXTERNAL_PHYSICS_SUPPORTED: **false**.
- `fuel_burn_kg = null`; no fuel-burn statement is made.
- A2 issued 0 real VSPAERO starts; no real batch was authorized or run.


## 10. Recovery addendum — 21:15 workspace-loss rebuild (2026-11-10 21:52 CST)

> This section supersedes the commit table in §1 and the artifact SHA256 values in §3–§5 when they disagree. Anything labelled NOT_RECOVERABLE below must not be cited as a pre-loss byte-exact artifact.

### 10.1 What was lost and what replaced it

- At ~21:15–21:16 CST the entire `D:\RCAIDE\dnext001` directory (this worktree included) was deleted externally; the deletion is outside A2's actions (A2 ran only pytest/git add+commit/edit inside its worktree during 21:10–21:17 and nothing afterwards).
- Old A2 commits `c11f40b` / `ad5c6cb` / `f70c403` / `8606afa` / `1cb0bab` were **never pushed** and no bundle/patch/copy exists: **NOT_RECOVERABLE**. Their SHAs are historical only.
- Authoritative replacement commit: `892fe84d57b7ca3f09d31fff8e39f74dacd3855f` (`recover(r2-optimizers): restore A2 optimizer framework after 21:15 workspace loss`, parent `683a868`, branch `research/dreal001-a2-optimizers`, NOT pushed). Rebuilt by replaying this session's `tools.write`/`edit` programs from compressed transcript blocks b5/b6/b7/b9 plus the b10 mesh-family edits (session id `d8e22b49-1bc8-4706-95a4-b7735b8185e2`).
- Byte-level fidelity evidence: the pre-loss receipt SHA256 `dfabb3e9658d0345c8ea9ee76346fac4a68332e82d7e4b0894c726e0d0d5114b` (committed in old `1cb0bab`) was reproduced **exactly** by the replay; the other 13 restored source/doc files matched the Lead's centralized replay draft SHA256. This receipt itself is the only file modified after that check (this addendum).
- Restored: 14 files = 12 files in `research/concorde_metaopt/dreal001/` (package `__init__`, `optimizers/{__init__,arms,cache,constants,design,evaluators,ledger,lift_match,pilot,records,task}.py`) + `research/concorde_metaopt/tests/test_dreal001_r2_optimizers.py` + this receipt; total **181,551 bytes** before this addendum.
- `__pycache__` directories are local build artefacts and are not part of the committed recovery manifest.

### 10.2 Test status after recovery

Command (verbatim):

```
D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r2_optimizers.py -q -p no:cacheprovider
.........                                                                [100%]
9 passed in 3.24s
```

- 8 pre-loss tests are restored and green unchanged.
- The 9th test (`test_mesh_family_covariate_round_trips_and_real_adapter_records_it`) was written during the b10 mesh-family increment but had never run green before the loss (its insertion broke indentation of the mock-pilot test). It is now fixed and passes; it covers AeroEvaluation mesh_family/mesh_nodes/mesh_elements round-trip and RealVspaeroAdapter recording of A1-provided mesh covariates. It does not launch any solver.
- `physical_solver_starts = 0` in every test and in every run below.

### 10.3 Regenerated (NOT byte-recoverable) mock artifacts — new SHAs are authoritative

The old `runs/dreal001/` artifacts were untracked-only and are lost; they were regenerated by a deterministic scripted call to `pilot.write_preregistration` + `pilot.run_pilot(backend=MOCK)` at the recovered source commit. New hashes:

- Mock batch `runs/dreal001/dreal001_a2_mock_e2e_20261110/`: 6 arms × B=8 × seeds {0,1} = 12 runs, all COMPLETED; simulated 96 = planned 96; `physical_solver_starts=0`; `budget_conserved=true`; `errors=[]`; `evidence_statement=SYNTHETIC_NOT_REAL_SOLVER`; `fuel_burn_kg=null`.
  - plan.json — `1e983feecbf45c9e35f505af8e3e3c54595ec24e7ea789b5fdd594b257acc38d`
  - approval.json (approved=false) — `1db4a3bfe60ea1603397bcc6cc5e446ad06a6d0289191845b5a8d9d95668775c`
  - batch_summary.json — `2b8afe43f50a0f5343ad3a6138cb3b4f57fac0a5ae76be163b842992cf0b16d8`
  - batch_metrics.csv — `ec9e79f706d7e24f756225c756a509ae3e5e68671d26498b3cfc53fd250787a9`
  - data_manifest.json — `604c4efe49daf44f92832358bd85e50acdc708d3601b77bcf6ae35a53ce33865`
  - example `runs/...__ade__B008__s0/summary.json` — `55dddb1b206ab2617630d704a579c23ceae5eef7c3c26c4a9be841dab9b2cb5f`
  - Pre-loss mock SHAs `1c2c9d46…` (plan), `23a109cd…` (approval), `0f45cb38…` (batch summary), `c0affc5c…` (metrics), `7500c538…` (ADE s0 summary) — **NOT_RECOVERABLE**, superseded.
- P2 preregistration template `runs/dreal001/P2_PREREG_TEMPLATE_20261110/` (not executed): 6 arms × B∈{64,128} × seeds {0,1,2} = 36 runs, planned_starts = 3456 (576/arm), backend=REAL, approval approved=false.
  - plan.json — `635750c8585268529869053ea4b08fef4935e76e7b7e8b3ad069a8e932e7bd58`
  - approval.json — `72c4ba02a316b89a23a4e909637937bb8c42f65312f19f24df1a9924abd83787`
  - Pre-loss P2 SHAs `6f8b8a4c…` / `4cb42ceb…` — **NOT_RECOVERABLE**, superseded.
- Regeneration script and per-file recovery manifest: `D:\RCAIDE\_recovery\r2-optimizers\{gen_runs.py,recovered_manifest.json}` (outside the git tree, written under the Lead's recovery authorization).

### 10.4 Standing constraints unchanged

- Real VSPAERO starts by A2 after recovery: **0**. No REAL pilot may start from this receipt; P2/P2A-CAL need the Lead-scheduled window and a signed approval.json plus A1's real `evaluate_fn` and attempts ledger.
- A1's real API was still absent from this worktree after recovery; `RealVspaeroAdapter` stays unwired per Lead instruction and is exercised only by refusal/shape tests.
- `fuel_burn_kg = null`; no SOLVER_LOOP_VERIFIED / INTERNAL_AERO_OPTIMIZATION_GAIN / EXTERNAL_PHYSICS_SUPPORTED claim is made by A2.

## 11. Increment — mesh-family cache isolation for REAL labels (2026-11-10 ~22:25 CST)

> Supersedes the artifact SHA256 values in §10.3 again: pilot run_config gained cache-policy and mesh-covariate blocks, so every run/batch byte changed. Evidence class is unchanged: **SYNTHETIC_NOT_REAL_SOLVER**; `physical_solver_starts = 0`.

### 11.1 Commits

| Commit | Subject | Content |
|---|---|---|
| `28fadc91db7f0417b6c160266aacbf7889f1c8a9` | `[D-REAL-001] A2: mesh-family cache isolation for REAL labels (normalized_geometry_hash/vspgeom_sha256, cross-run fail-closed)` | 6 files, +384/−29: records.py, cache.py, evaluators.py, __init__.py, pilot.py, tests/test_dreal001_r2_optimizers.py |
| `474075e745e6409ad65ffa494ac8cea0793d1cc0` | `[D-REAL-001] A2: regenerate mock/P2 artifacts with mesh-cache policy; receipt section 11 (SYNTHETIC, physical=0)` | 105 files, +1831/−1020: regenerated runs + receipt §11 |

Parent chain on `research/dreal001-a2-optimizers`: `683a868` → `892fe84` (recovery) → `928bb34` (recovery artifacts) → `28fadc9` (mesh-cache source) → `474075e` (regenerated artifacts + receipt §11) → the short follow-up commit carrying §11.5/§11.6 (fail-closed mesh covariates). None pushed. The commit carrying §11 of this receipt is the artifact-commit immediately after `28fadc9`; it cannot cite its own SHA. `git status` was clean for tracked source files at `28fadc9`.

### 11.2 What changed (A1 E6-GAP-01 / Lead m00426)

- `records.AeroEvaluation`: new fields `normalized_geometry_hash` and `vspgeom_sha256` (default empty), serialised in `as_dict` and restored by `evaluation_from_dict`.
- `cache.EvaluationCache`: two-level keys. `design_key = sha256(x12_canonical || task_fingerprint || solver_config_sha256)` is unchanged for mock/replay comparability. A REAL entry key is `sha256(design_key || mesh_family || normalized_geometry_hash)`. New `store(..., design_key=, mesh_family=, normalized_geometry_hash=, vspgeom_sha256=)`, `lookup_design_scoped(design_key, run_id)` (all in-run mesh variants), `foreign_design_entry`, `guard_run_scope`, `forbid_cross_run_reuse`, and `CrossRunCacheReuse`. Cache file schema is now `dreal001.evaluation_cache.v2`; v1 files still load. `vspgeom_sha256` is provenance only and is NOT a numeric comparison key (raw bytes differ across object-id/order even within one topology family).
- `evaluators`: `ProbeResult` carries the same two covariates; `RealVspaeroAdapter._probe_batch` parses them from A1 `record.mesh*`/`record.geometry*`; the REAL success path stores under the mesh-extended key with `design_key` as the base; REAL cache lookup returns only same-run variants, and if one design has more than one mesh family in-run the design is re-measured (`cache_hit=False`) instead of mixing families; every evaluation record carries both fields.
- `RealVspaeroAdapter.__init__` sets `cache.forbid_cross_run_reuse = True`; a REAL cache file containing entries from another run fails closed with `CrossRunCacheReuse`.
- `pilot` run_config: `cache.cross_run_reuse = forbidden` for REAL (per-run isolated files), `cache.real_entry_key = sha256(design_key||mesh_family||normalized_geometry_hash)`, `cache.mesh_family_stratified = true`, `cache.ambiguous_family_policy = re-measure; never mix mesh-family variants of one design`, `cache.foreign_run_labels_visible = false`; new `mesh_covariates` block recording `{mesh_family, mesh_nodes, mesh_elements, normalized_geometry_hash, vspgeom_sha256}` with `cross_family_numeric_comparison = forbidden`.
- 10th pytest: `test_real_cache_key_includes_mesh_family_and_forbids_cross_run_reuse` — in-run REAL store/lookup with mesh-extended key, same-run cache hit, second mesh variant makes reuse ambiguous, v2 save/load keeps both variants, and a second-run REAL adapter raises `CrossRunCacheReuse`.
- 11th pytest / fail-closed rule: a REAL `SOLVED_VALID` record whose `mesh_family` or `normalized_geometry_hash` is missing raises `AccountingViolation` in `_probe_batch` and produces no cache entry and no start (`test_real_adapter_rejects_label_without_mesh_covariates`). Lead m00426: REAL labels must never be keyed by design hash alone.
- Bugs found while wiring: (a) the REAL success branch of `evaluate` was not passing `normalized_geometry_hash`/`vspgeom_sha256` into `_evaluation`, so records stayed empty although the probe parsed them correctly (fixed); (b) the synthetic A1 CL bracket in the new test must bracket `task.cl_required(Sref(x12))` — `cltot=[0.20,0.30]` does not bracket the ~0.171 target, which produced `LIFT_MATCH_FAILED` and no cache store.

### 11.3 Test status

Command (verbatim):

```
D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests/test_dreal001_r2_optimizers.py -q -p no:cacheprovider
...........                                                              [100%]
11 passed in 2.72s
```

All eleven tests are MOCK/REAL-refusal only; no VSPAERO process is launched. The new tests call synthetic A1 callables that report `physical_solver_starts = 0`. The 11th test was added after `474075e` in the follow-up commit; the earlier `10 passed in 2.98s` text is superseded.

### 11.4 Regenerated artifacts (new SHAs authoritative; generated at source commit `28fadc9`)

- Mock batch `runs/dreal001/dreal001_a2_mock_e2e_20261110/`: 12 runs (6 arms × B=8 × seeds {0,1}), all COMPLETED; simulated 96 = planned 96; `physical_solver_starts = 0`; `budget_conserved=true`; `errors=[]`; `evidence_statement=SYNTHETIC_NOT_REAL_SOLVER`; `fuel_burn_kg=null`.
  - plan.json — `af9f8c598f967dd05996849578ed1b0ccaf37820af181e6884f3ca2f17e945c8`
  - approval.json (approved=false) — `df01dd20b7bcedd673d9e3a44330a09665c65fb4de44792ba066d72d9fb0c6d6`
  - batch_summary.json — `71ebc8d99d39e9c92ad3128e8fb21a0e638ab700fba46b71531ae25772b1f08f`
  - batch_metrics.csv — `ec9e79f706d7e24f756225c756a509ae3e5e68671d26498b3cfc53fd250787a9`
  - data_manifest.json — `8311f843b6680f28be88733526806a69ae66d162dd0d7213e6b8f804c68f295e`
  - example `...__ade__B008__s0/summary.json` — `65d44302bf4c206a425d717c022f3817de46a922f05c39b4b6c49e06fcf247e4`
- P2 preregistration template `runs/dreal001/P2_PREREG_TEMPLATE_20261110/` (not executed; `approved=false`): 36 runs (6 arms × B∈{64,128} × seeds {0,1,2}), planned_starts = 3456 (576/arm), backend=REAL.
  - plan.json — `fe9b6b5b3027f1d2e9a1dcb92f49e50d3648207912fd1b4a88f35e1b69b14e60`
  - approval.json — `6d48eec0d64990525dc83c30ad99fa1343f8c10413581c1bf02affa130e9fe63`
- Superseded: §10.3 mock plan/approval/batch_summary/data_manifest/ADE-s0 SHAs (`1e983fee…`, `1db4a3bf…`, `2b8afe43…`, `604c4efe…`, `55dddb1b…`) and P2 plan/approval (`635750c8…`, `72c4ba02…`).

### 11.5 Standing constraints unchanged

- Real VSPAERO starts by A2: **0** (before and after this increment). No real batch was authorized, scheduled, or attempted.
- `RealVspaeroAdapter` stays unwired to an A1 callable (A1 EVALUATOR_API not in this worktree); it is exercised only through refusal/shape tests and synthetic callables reporting zero starts.
- `fuel_burn_kg = null`. No SOLVER_LOOP_VERIFIED / INTERNAL_AERO_OPTIMIZATION_GAIN / EXTERNAL_PHYSICS_SUPPORTED claim is made. Cross-family mesh numbers must never be compared; P2 must be stratified or pinned to one family after A1's determinism decision.
- task-7 remains in_progress pending A1 EVALUATOR_API wiring.

