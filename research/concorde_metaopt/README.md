# research/concorde_metaopt — P0 audit, P1 geometry and P2 single-cruise evaluator

Phase I workspace for RCAIDE_Supersonic Issue #1 ("[METAOPT-00] ..."). P0 is
complete: the mandatory directory skeleton, the read-only `audit` subcommand and
the committed evidence runs. P1 contains the provisional 15-variable
design-space contract (`configs/design_space_15d.yaml`), a dependency-free
geometry model, an RCAIDE vehicle adapter, 23 model checks (G01–G23), 22 RCAIDE
check rows per case (19 identifiers, R16 expands to four), a 31-case (baseline + 15 variables × 2 directions) effect matrix, and an OpenVSP geometry export check that builds the same baseline geometry from the model and compares eleven derived quantities against the exported STL/STEP/VSP3 files. P2 now freezes the
single fixed-cruise task contract and implements the evaluation loop: a real
RCAIDE Mission backend, ten frozen `g <= 0` constraints, a budget/cache ledger,
an `evaluations.jsonl` record and the five-evaluation smoke workflow. No DOE,
BO, MAML or CFD case is executed by this code yet; P3–P6 remain unimplemented.

## CLI status

| subcommand | status |
| --- | --- |
| `audit` | implemented (read-only environment audit) |
| `geometry-check` | implemented (15D geometry + 31-case effect matrix + 4 negative controls + RCAIDE cross-check) |
| `openvsp-check` | implemented (baseline 15D geometry exported through an external OpenVSP 3.26.1 Python 3.9 worker; 11 model-vs-STL checks) |
| `smoke` | implemented (three baseline RCAIDE cruise repeats + two single-variable perturbations; five true evaluations) |
| `doe`, `baseline`, `route-a`, `report` | declared in `cli.py`, exit code 2 with "not implemented ...; no result was produced." |

Reproduce the P0 audit (one run directory, small files committed on purpose so the
result can be reviewed remotely):

```bash
# 1) git and external-tool facts that child processes may be denied under a sandbox
bash research/concorde_metaopt/scripts/probe_external_tools.sh \
  research/concorde_metaopt/optimization_runs/<run_id>/probes
# 2) assemble the probe JSON
./envs/RCAIDE/python.exe -E -s -B research/concorde_metaopt/scripts/assemble_probes.py \
  research/concorde_metaopt/optimization_runs/<run_id>/probes \
  research/concorde_metaopt/optimization_runs/<run_id>/probes/shell_probes.json
# 3) run the audit (re-run with --allow-existing when the probes/ directory exists)
./run_rcaide.cmd -m research.concorde_metaopt.cli audit \
  --run-id <run_id> \
  --shell-probes research/concorde_metaopt/optimization_runs/<run_id>/probes/shell_probes.json \
  --allow-existing
```

Evidence runs kept in the repository:

- `audit-p0-20261028T1430`: first run after the sandbox was lifted; 9 blockers,
  8/8 unittest, `git_sha=d9aa5e6` (schema of record for the Issue #1 receipt).
- `audit-p0-reviewfix-20261028T1540`: run after the independent A5 review
  (CHANGES_REQUESTED) was addressed; 9 blockers, clean worktree,
  `git_sha=fdadeaa`, committed in `1295576`; see "Review fixes" below. The
  earlier `...T1515` development run was deleted and is not evidence.
- `audit-p0-20261027T2055`: historical first run made while the sandbox denied
  child processes; kept only as a comparison point, not as current evidence.

## summary.json conventions (Issue #1 mandatory fields)

- `stage` is `P0`; `method` is `read_only_environment_audit`.
- `total_true_evaluations`, `low_fidelity_calls`, `su2_calls` are `0`: the audit
  executes nothing physical.
- `design_dim` is `null` with `design_dim_note`: the 15-variable space is not
  frozen until P1.
- `invalid_count`, `failed_count`, `first_feasible_evaluation`,
  `best_feasible_fuel_kg`, `best_design_id`, `cpu_seconds_if_available` are
  `null` (not applicable to an audit; never 0, inf or a fabricated label).
- `wall_seconds` is measured for every audit run and written as a number; it is
  never documented as null.
- `solver_versions` records only observed versions. The OpenVSP 3.26.1 Python
  binding exposes no version API (no `GetVSPVersion`/`GetVersion`, `__version__`
  is `None`), so `openvsp` stays `null`; the install version is identified by the
  documented install path and the executable file, and the blocker records the
  external Python 3.9 worker constraint. A failure string is never written as a
  version.
- `git_sha` comes from the committed HEAD; when the worktree is dirty this is
  reported in the blocker list (`B-P0-DIRTY-WORKTREE`).

## Evidence files

`environment.json` contains git facts, Python/packages, external tools
(`SU2_CFD.exe --help`, `gmsh --version`, OpenVSP executable and Python-binding
probes for both the project interpreter and external Python 3.9 workers), the
Concorde.py structural scan, maml-opt and rcaide-multifidelity installation facts,
`pip check`, installed-package test logs and the blocker list. `evidence/` mirrors
the tables as Markdown/JSON (`toolchain_table.md`, `api_table.md`,
`concorde_structure.md`, `blocker_list.md`, `checks.json`, `pip_check.txt`, ...).
`probes/` keeps the raw shell-probe outputs and `shell_probes.json` so every number
is traceable. Each run directory also contains a `README.md` describing that run.

Path policy: generated evidence replaces the repository root, the user home and the
external evidence root with `<repo_root>`, `<home>`, `<external_evidence_root>`.
Standard tool install locations (Program Files, Anaconda) are retained because they
are needed to reproduce the environment and contain no username, token or secret.

## Review fixes (independent A5 review, 2026-10-28)

An independent reviewer returned CHANGES_REQUESTED on the first P0 evidence. The
following were fixed and re-run under a new run id `audit-p0-reviewfix-20261028T1540`
(the `...T1515` run was a dirty-tree development attempt and was deleted):

1. `discover_maml_opt` path-concatenation TypeError (`Path / "MAML" + "..."`);
   maml-opt API table is now populated and a test exercises the real scan roots.
   The legacy 13-variable application scan is restricted to code files and its
   blocker states that 137 files were scanned and 40 textual hits (tutorial index
   JSONs and this audit itself) are not a candidate application source, so the
   historical app `remains unlocated` rather than being hidden by index hits.
2. OpenVSP probe now puts all four package roots on `sys.path`
   (`python`, `python/openvsp`, `python/degen_geom`, `python/utilities`); the
   SUAVE Python 3.9 worker imports openvsp, so the blocker became a minor
   "external worker ABI" constraint instead of a major "binding unusable" claim.
3. `toolchain_table.md` marks distributions without an import probe as
   `not_probed` instead of a failed import with `error=None`.
4. Added `pip check`, rcaide-multifidelity source-test log and run `README.md`.
5. `concorde_structure.md` now reports per-component `append_segment` counts,
   mission segment tags, `level_cruise` line, duplicate segment tags and
   derived-quantity markers.
6. README references and `wall_seconds` documentation corrected.
7. `discover_external_tools` no longer mutates global state / relies on `break`.
8. Host absolute paths in generated evidence are placeholdered; tool install paths
   are documented as non-private.

## P1 status

P1 freezes the 15-variable order and implements the geometry pipeline. Bounds and
the geometry model remain **provisional** until a Mission evaluation exists (P2):

- `configs/design_space_15d.yaml` — frozen W01–W10 / V01–V02 / F01–F03 order and
  identifiers from Issue #1, SI units, baseline values read from
  `tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py`
  (sha256 recorded in the file), and **provisional** bounds tagged
  `bounds_status: provisional_until_geometry_perturbation` / `frozen: false`.
  It records the nine derived-quantity rules (three-segment trapezoid integration
  for span/chords/MAC, wetted area from exposed area, tail span from V01 and fixed
  AR 0.74, fuselage nose/tail/cabin/volume from F01–F03, mass and CG explicitly
  `PROVISIONAL_NOT_FROZEN`) and cross constraints C01–C04.
- `config_io.py` — dependency-free config loading. The project environment has no
  PyYAML (and no network to install it), so `.yaml` files use PyYAML when present
  and otherwise a strict indentation-based subset loader (nested mappings,
  sequences, inline scalar lists, comments, quoted scalars; rejects tabs,
  bad indentation and duplicate keys with line numbers).
- `aircraft/design_space.py` — `DesignVariable`/`DesignSpace` dataclasses,
  `load_design_space()`, order/unit/range validation, baseline and cross-constraint
  checks, normalized views `(x - baseline)/scale` and
  `(x - lower)/(upper - lower)`, and validation of the `baseline_geometry` block
  against the derived-quantity rules (a hand-edited inconsistent baseline is now
  rejected instead of silently accepted).
- `aircraft/geometry_model.py` — dependency-free 15D → `ConcordeGeometry` model.
  Wing: four sections, span `sqrt(area·AR)`, root chord from the three-segment
  trapezoid factor, fixed chord ratios `[1, W08, W09, 0.032544]`, quarter-chord
  sweeps `[W03, W04, W05, W05]`, tip twist W10, MAC/AC from the integrated chord
  distribution, wetted area from exposed area. Vertical tail: three sections, span
  `sqrt(V01·0.74)`, fixed chord ratios, sweeps `[63, 40, 0] + V02`. Fuselage:
  nose/tail lengths from F02, height from F03, eight elliptical-cone stations,
  wetted area and usable volume by integration. Mass/CG are provisional scalings of
  the upstream OEW and must not be used as frozen constraints.
- `aircraft/geometry_builder.py` — builds an RCAIDE `Vehicle` from the model
  (main wing with four segments and four control surfaces, vertical tail, fuselage,
  landing gear, upstream airfoil files) and runs RCAIDE `wing_planform` /
  `fuselage_planform` as an independent cross-check.
- `aircraft/geometry_checks.py` — 23 model checks (G01–G23: area/span/AR closure,
  section order, chord positivity and monotonicity, sweep/twist bounds, wetted and
  exposed area, tail closure, fuselage station order and cabin length, volume
  requirement, mass/CG finiteness) and 22 RCAIDE check rows per case from 19
  identifiers (R00–R18; R16 expands to four rows). G01/G02/G03/G11/G12 are
  identity/regression guards, G10 is an explicit WARN limitation (exposed area is
  not modelled) and G15 is a defensive guard that the fuselage constructor normally
  makes unreachable. Also the 31-case effect matrix, four deliberately invalid
  negative controls, CSV/JSON run artefacts and PNG figures.
- `reports/figures.py` — regenerates the two figures from the CSV/JSON artefacts
  alone (`python -m research.concorde_metaopt.reports.figures <run_dir>`).
- `aircraft/openvsp_geometry.py` — worker that runs under the **external Python
  3.9** OpenVSP distribution (the project interpreter 3.11 cannot import the
  `_vsp` extension, which is ABI cp39). It reads a JSON request (OpenVSP root,
  export directory, components) and builds the main wing (four sections,
  symmetric), vertical tail (three sections, rotated 90° about X) and fuselage
  (eight elliptical-cone stations), then writes `.vsp3`, `.stl`, `.step`.
  Component STL files are written by isolated one-component models because the
  OpenVSP binding has no working subset export (`ExportFile` only accepts
  `(filename, set, type)` and user sets are ignored by the STL writer).
- `aircraft/openvsp_check.py` — the RCAIDE-environment orchestrator: resolves the
  external Python/OpenVSP paths (`--openvsp-python`/`--openvsp-root` or
  `CONCORDE_OPENVSP_PYTHON`/`CONCORDE_OPENVSP_ROOT`), builds the request from the
  15D geometry model, runs the worker as a subprocess, measures the STL files with
  `trimesh`, and writes the run artefacts. Eleven checks OV01–OV11 compare model
  area/span/lengths against the OpenVSP metrics and mesh extents; OV08/OV09
  (fuselage width/height) are warnings because OpenVSP's fuselage spline
  overshoots the eight-station profile (measured width 3.312 m vs model 2.88 m
  at the baseline). No aerodynamic result is produced; VSPAERO is not run by this
  check.

Run the P1 geometry check and the tests:

```bash
./run_rcaide.cmd -m research.concorde_metaopt.cli geometry-check \
  --run-id <run_id> --output-root research/concorde_metaopt/optimization_runs
# OpenVSP export check (external Python 3.9 + OpenVSP 3.26.1 install)
./run_rcaide.cmd -m research.concorde_metaopt.cli openvsp-check \
  --run-id <run_id> \
  --openvsp-python <path-to-python3.9.exe> \
  --openvsp-root <path-to-OpenVSP-3.26.1-win64> \
  --export-root outputs/concorde_metaopt
./run_rcaide.cmd -m unittest discover -s research/concorde_metaopt/tests -t . -v
```

Committed P1 evidence run: `geometry-check-p1-20261028T1835` — 31 valid cases, zero
invalid perturbation cases, four negative controls rejected/failed as expected,
RCAIDE cross-checks enabled, `total_true_evaluations=0`, `failed_count=0`, two
figures. The run is generated from the code commit and committed separately so its
`git_sha` attests the reviewed code. Known unresolved source deviations are recorded as WARN checks (not
hidden): derived wing root chord 29.902 m vs upstream 33.8 m (−11.5%), wing wetted
area 717.6 vs 601 m² (+19.4%), wing exposed area 358.25 vs 326.5 m² (+9.7%,
fuselage shielding is not modelled in P1), tail span 5.009 vs 6.0 m (−16.5%), tail
root chord 13.158 vs 14.5 m (−9.3%), fuselage wetted area 488.9 vs 442 m² (+10.6%),
fuselage front projected area 7.510 vs 11.9 m² (−36.9%). The upstream declared
values are kept in `baseline_geometry.upstream_declared` for traceability only.
These deviations must be resolved (or frozen with a documented physical decision)
before the P2 Mission contract is frozen. Their arithmetic causes are recorded here
so the WARN rows are not mistaken for model bugs:

- Main wing: the upstream declarations are mutually inconsistent. With area
  358.25 m², span 25.6 m and the upstream section fractions/chord ratios, the
  three-segment trapezoid integral requires a root chord of 29.902 m; the upstream
  declared root chord 33.8 m would give an area of about 404.7 m². The RCAIDE
  rebuild driven by this model returns 358.25 m², so the model preserves the
  declared reference area and treats 33.8 m as an upstream inconsistency kept in
  `upstream_declared`.
- Vertical tail: area 33.91 m² with the fixed AR 0.74 implies a span of 5.009 m;
  the upstream declared span 6.0 m would imply an area of about 26.6 m². The model
  preserves the declared area and records the declared span as upstream data.
- Fuselage front projected area: `π/4 · width · height = π/4 · 2.88 · 3.32 =
  7.510 m²`; the upstream declaration 11.9 m² cannot be reproduced from its own
  width/height and is kept as upstream data.
- Fuselage wetted area: the eight-station truncated-elliptic-cone integral gives
  488.9 m² vs the upstream empirical 442 m². Which value P2 should use is an open
  TaskSpec question, not a P1 fix.
- Wing exposed area: P1 does not model fuselage shielding, so exposed equals the
  reference area (358.25 m²) instead of 326.5 m²; this is explicitly a P1
  limitation to be resolved in P2.

Committed P1 OpenVSP evidence run: `openvsp-check-p1-20261029T1425` — baseline
15D geometry exported to `.vsp3`/`.stl`/`.step`, eleven comparisons
(ten pass, OV08 fuselage width warning), zero failures, zero true evaluations.
The exported binaries are large and live under `outputs/concorde_metaopt/<run>/openvsp/`
(gitignored); the run directory records their relative paths, sizes and SHA-256.
OpenVSP is available on this host only through the external Python 3.9
distribution shipped with the install; the project environment 3.11 dependency
list is unchanged. The fuselage spline overshoot is a tool limitation, not a
model bug: the eight-station profile is exact in the model/RCAIDE path, but
OpenVSP interpolates it with a spline and exceeds the nominal width by 15.0% at
the baseline. A denser station set was tried and also overshoots; P1 records the
limitation and keeps the model as the authority.

Two conventions are explicitly recorded rather than silently aligned: the geometry
model uses `AC = LE(MAC) + 0.25·MAC` while RCAIDE uses the area centroid −0.25·MAC
(equal only for a single trapezoid, so R07 has a 0.25 m tolerance and WARN status),
and RCAIDE forces the last wing/tail segment sweep to the previous segment value
(RCAIDE check R16 records this as INFO).

## P2 status

P2 freezes the single fixed-cruise evaluation contract and implements the
evaluation loop that P3–P6 will reuse.

- \`configs/task_fixed_cruise.yaml\` + \`tasks/task_spec.py\` — frozen Phase I task:
  18,288 m (60,000 ft), Mach 2.02, 3,028,020 m (1,635 nmi) cruise; OEW 78,700 kg,
  payload 9,500 kg, cargo 1,000 kg, loaded fuel 55,800 kg, start mass 145,000 kg
  (zero-fuel mass 89,200 kg); limits max fuel 95,680 / max zero fuel 92,000 /
  max take-off 185,000 kg; four turbojets; objective \`fuel_burn_kg\` in kg. The
  mass contract is \`frozen\` because it was measured, not guessed: the same
  single-cruise mission at the upstream MTOW 185,000 kg needs **max throttle
  1.2708** (infeasible, the historical failure the old application reported),
  155,000 kg needs 1.0374, 150,000 kg needs 1.0008, so 145,000 kg was selected
  with about 3.7% throttle margin. The task validates its own mass balance,
  limits and objective identity on load and can be adapted to
  \`maml_opt.contracts.TaskSpec\` for P4/P5. It is a cruise-entry contract, not an
  MTOW mission.
- \`aircraft/concorde_adapter.py\` — loads the upstream tutorial
  (\`tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py\`,
  SHA-256 pinned), applies the 15D geometry to the RCAIDE main wing, vertical
  tail and fuselage **before** \`configs_setup\` (RCAIDE \`Config\` deep-copies the
  vehicle, so later edits must go to \`analyses.<tag>.vehicle\`), rebuilds the
  eight fuselage segments (the upstream file appends a duplicate \`segment_6\` tag
  and silently loses one station), applies the frozen mass contract to the
  analysis vehicle, and re-derives the geometry through RCAIDE
  \`wing_planform\`/\`fuselage_planform\` to fail closed on a mismatch.
- \`evaluation/contract.py\` — ten constraints, all \`g <= 0\`, with names and
  denominators frozen: \`geometry_invalid\`, \`task_mass_balance\`,
  \`fuel_capacity_excess\`, \`zero_fuel_excess\`, \`takeoff_excess\`,
  \`fuel_remaining_deficit\`, \`max_throttle\`, \`cruise_range_error\`,
  \`mission_convergence\` (both convergence flags and residual norm <= 1e-4) and
  \`trim_attitude_limit\` (|alpha| <= 12 deg as a force-balance guard; this
  single-segment mission has no moment trim). \`empty_constraints()\` writes nulls,
  never fabricated numbers; invalid evaluations never get a fake large objective.
- \`evaluation/mission.py\` — builds the one-segment
  \`Constant_Mach_Constant_Altitude\` mission and extracts a validated observation
  history (mass/range/time, throttle, fuel mass flow and thrust for the four
  turbojets, alpha/CL/CD, convergence flags, residual norm); non-finite,
  decreasing-range or increasing-mass histories raise \`ObservationError\`.
- \`evaluation/low_fidelity.py\` — \`SingleCruiseBackend\`: one fresh vehicle,
  mission and solver state per evaluation (no warm start), status vocabulary
  VALID / GEOMETRY_INVALID / GEOMETRY_MISMATCH / MISSION_BUILD_FAILED /
  MISSION_FAILED / MISSION_NOT_CONVERGED / INVALID_OR_MISSING_RESPONSE. Failed or
  invalid evaluations carry \`objective: null\`. \`preflight()\` validates the
  template and task with zero physical calls.
- \`evaluation/high_fidelity.py\` — fail-closed stub: SU2/RANS is not wired in P2,
  so any call raises instead of returning a placeholder number.
- \`evaluation/ledger.py\` — \`EvaluationLedger\` enforces the true-evaluation
  budget, caches only VALID results keyed by task fingerprint + fidelity +
  canonical design (a cache hit consumes no budget and reports
  \`physical_call_count: 0\`), records backend exceptions as \`BACKEND_ERROR\`, and
  writes the Issue-mandated \`evaluations.jsonl\` fields.
- \`evaluation/smoke.py\` — three baseline repeats with caching disabled
  (repeatability tolerance 1e-6) and two perturbations, W01 \`wing_area\` +1% and
  W10 \`tip_twist\` 0 -> +2 deg. Writes \`summary.json\`, \`run_config.json\`,
  \`environment.json\`, \`best_design.json\`, \`evaluations.jsonl\`,
  \`smoke_cases.csv\`, \`task_spec.json\`, two figures and a run \`README.md\`, and
  updates \`optimization_runs/index.json\`.
- \`reports/figures.py plot_smoke_artifacts\` — redraws the repeatability and
  perturbation figures from \`evaluations.jsonl\`/\`smoke_cases.csv\` alone.

Run the P2 smoke (three repeats + two perturbations = five true evaluations,
roughly 80 s each on this host):

\`\`\`bash
./run_rcaide.cmd -m research.concorde_metaopt.cli smoke \
  --run-id <run_id> --output-root research/concorde_metaopt/optimization_runs
\`\`\`

True-evaluation accounting for P2 (approved envelope 8–12 missions): four
calibration missions froze the mass contract (185 t, 155 t, 150 t and the
4,500 nmi MTOW probe that showed the fuel cannot close), and the smoke spends
five, so nine in total. \`run_smoke\` refuses a budget below five.

## Host/sandbox constraints (recorded, not hidden)

- The first audit (2026-10-27) ran under a Windows file sandbox that denied child
  processes and writes to `.git/`, `outputs/` and `docs/`; git/tool facts were
  captured by the bash probe and merged under `probe_source: "shell_probe"`.
- The current session has danger-full-access; `probe_source` still records whether
  a fact came from the direct Python path or from a shell probe.
- The historical sandbox denied writes to `tempfile.mkdtemp`; the current session
  has danger-full-access and the tests now use `tempfile.mkdtemp` outside the repo
  (the old `tests/_tmp/` rule remains ignored for safety).
- `pytest` is not installed in `envs/RCAIDE`; tests run with `unittest`:
  `./run_rcaide.cmd -m unittest discover -s research/concorde_metaopt/tests -t . -v`.

## Tests

`tests/test_audit.py` (17 tests) covers the SHA-256 helper, Markdown table
rendering, Concorde scanning (real identifiers, component counts, duplicate tags,
level_cruise), blocker construction (dirty/clean worktree, OpenVSP external-worker
severity, Gmsh absence, MAML source/direct_url), shell-probe precedence for git
facts, maml-opt scan roots (regression for the TypeError), external-tool
global-state immutability, toolchain `not_probed` handling, and an end-to-end
mocked `run_audit` that writes `environment.json`/`summary.json`/`README.md`/
evidence without any simulation.

`tests/test_design_space.py` (41 tests) covers the real 15D config (order,
identifiers, units, provisional status, baseline SHA), normalization roundtrips,
bound/cross-constraint violations, rejection of missing/duplicate/reordered
variables, wrong units, out-of-range baselines, a frozen flag before the measured
bounds exist, `baseline_geometry` consistency (root chord, span, tail span,
section count, exposed area, status), the C03 expression text, and the YAML-subset
loader (nested data, inline lists, comments, quotes, tabs, duplicate keys, bad
indentation).

`tests/test_openvsp_check.py` (14 tests) drives the orchestrator with fake
workers (no real OpenVSP required): version parsing from the install directory
name, path resolution failures, request construction (components, sections,
symmetric flags, rotation, spans/chords), path sanitisation, comparison
pass/warn/fail/skip semantics, status aggregation, and the unavailable /
worker-failed / successful run artefacts (summary, README, environment,
external artefact hashes, relative-path policy).

`tests/test_geometry_15d.py` (23 tests) covers the baseline model values and
derived dependencies, all 31 effect cases (each variable changes at least one
non-echo derived metric; area/span closure; expected directions), rejection of
invalid geometry, the volume-requirement FAIL path, the four negative controls,
RCAIDE cross-checks R00–R18, the derived `failed_count` path, and the run
artefacts (required files, summary fields, per-case JSONL fields, duplicate-run
rejection). Tests use a temporary directory outside the repository.

`tests/test_task_and_evaluation.py` (28 tests) covers the frozen task contract
(exact values, derived margins, fingerprint stability, rejection of unbalanced
masses, unfrozen status, changed objective identity, empty freeze evidence and
out-of-range Mach), the ten constraints (names, normalized range error,
throttle/non-convergence/trim violations, fuel and mass deficits, missing
observation keys), mission assembly from the task (segment altitude/Mach/
distance, control variables, missing analysis tag) and observation extraction
(happy path, increasing mass, decreasing range, non-finite or short histories,
missing propulsor, `thrust_force` fallback). No Mission is launched.

`tests/test_budget_and_cache.py` (17 tests) covers ledger budget enforcement
(no row on a rejected call), cache hits that consume no budget, cache-disabled
runs, invalid results not cached, backend exceptions recorded as
`BACKEND_ERROR`, the JSONL row fields and deterministic design ids, best/
first-feasible tracking, and the offline smoke workflow (happy path artefacts,
repeatability failure, case failure, minimum-budget rejection, existing run
directory protection, figure redraw from artefacts). The backend is a fake; no
Mission or CFD runs here.

All 139 tests pass (17 audit + 40 design space + 23 geometry + 14 OpenVSP +
28 task/evaluation + 17 budget/cache).

## Out of scope so far

No SU2 case, no DOE dataset, no BO, no MAML. Those require P3–P6 code gates and
explicit user approval for true-evaluation budgets. The P1 config and geometry
model are provisional and must not be cited as a frozen design space or a
validated aerodynamic model; the effect matrix is a geometry-sensitivity sanity
check only, not a physical performance study. The OpenVSP check verifies geometry
export only (no VSPAERO/CFD aerodynamic analysis is claimed). The P2 task
contract is frozen and physically measured, but the single-cruise evaluation is
low-fidelity (RCAIDE VLM + turbojet deck) and must not be presented as a
high-fidelity fuel-burn result.
