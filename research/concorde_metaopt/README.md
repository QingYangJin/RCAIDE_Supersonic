# research/concorde_metaopt — P0 audit, P1 geometry, P2 evaluator, P3 DOE and P4 baseline BO

Phase I workspace for RCAIDE_Supersonic Issue #1 ("[METAOPT-00] ..."). P0 is
complete: the mandatory directory skeleton, the read-only `audit` subcommand and
the committed evidence runs. P1 contains the provisional 15-variable
design-space contract (`configs/design_space_15d.yaml`), a dependency-free
geometry model, an RCAIDE vehicle adapter, 23 model checks (G01–G23), 22 RCAIDE
check rows per case (19 identifiers, R16 expands to four), a 31-case (baseline + 15 variables × 2 directions) effect matrix, an OpenVSP geometry export check that builds the same baseline geometry from the model and compares twenty-one quantities (geometry plus placement/orientation) against the exported STL/STEP/VSP3 files, and a seven-case OpenVSP perturbation check that exports the baseline plus representative wing, vertical-tail and fuselage perturbations and proves that each change reaches the exported geometry. P2 now freezes the
single fixed-cruise task contract and implements the evaluation loop: a real
RCAIDE Mission backend, ten frozen `g <= 0` constraints, a budget/cache ledger,
an `evaluations.jsonl` record and the five-evaluation smoke workflow. P3 adds the
zero-physics DOE screening path (`data/schema.py`, `data/generate_doe.py`,
`data/validate_dataset.py`): LHS/Sobol candidate batches, geometry screening and a
12-check dataset validator. P4 adds the ordinary constrained BO baseline
(`optimization/baseline_bo.py`) on top of the installed maml-opt optimizer and the
same evaluation ledger. No fidelity-identity probe, MAML or CFD case is executed
by this code yet, and no real BO campaign has been committed; the rest of P3/P4
and P5–P6 remain unimplemented.

## CLI status

| subcommand | status |
| --- | --- |
| `audit` | implemented (read-only environment audit) |
| `geometry-check` | implemented (15D geometry + 31-case effect matrix + 4 negative controls + RCAIDE cross-check) |
| `openvsp-check` | implemented (baseline 15D geometry exported through an external OpenVSP 3.26.1 Python 3.9 worker; 21 model-vs-mesh checks including placement/orientation) |
| `openvsp-cases` | implemented (baseline + six representative 15D perturbations exported through OpenVSP; per-case model-vs-OpenVSP checks, perturbation-reach checks, delta CSV/JSON and figure) |
| `smoke` | implemented (three baseline RCAIDE cruise repeats + two single-variable perturbations; five true evaluations) |
| `doe` | implemented (LHS/Sobol candidate batches in the 15D box, geometry screening, dataset validator; zero physical evaluations) |
| `baseline` | implemented (ordinary constrained BO over the 15D box using maml-opt's constrained GP/EI optimizer, plus a deterministic single-process DE/rand/1/bin baseline; both share the evaluation ledger; toy and analytic-function tests only, real budget awaits approval) |
| `report` | implemented (rebuilds `report.md`/`report.json` from stored artefacts, recomputes headline numbers, checks artefact paths and redraws figures; no Mission/CFD/OpenVSP call) |
| `route-a` | declared in `cli.py`, exit code 2 with "not implemented ...; no result was produced." |

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
- `reports/summarize.py` — artefact-only run reporter. It reads
  `summary.json`, `evaluations.jsonl`, `best_design.json` and the recorded
  artefact list, recomputes the true-evaluation count, best feasible objective,
  first feasible evaluation, best design id and status histogram from the raw
  rows, compares them with the stored summary (R01–R04), flags missing or
  absolute artefact paths, redraws the figures that the run's artefacts support,
  and writes `report.md`/`report.json` (plus an optional cross-run
  `comparison.csv`/`comparison.json` when `--compare-run` is given). It never
  re-runs a Mission, CFD or OpenVSP call.
- `aircraft/openvsp_geometry.py` — worker that runs under the **external Python
  3.9** OpenVSP distribution (the project interpreter 3.11 cannot import the
  `_vsp` extension, which is ABI cp39). It reads a JSON request (OpenVSP root,
  export directory, components) and builds the main wing (four sections,
  symmetric), vertical tail (three sections) and fuselage (eight elliptical-cone
  stations), then writes `.vsp3`, `.stl`, `.step`. Components are exported in
  their **local frame**: this OpenVSP build does not bake `XForm` translation or
  rotation into exported meshes (measured: readback >0 before `Update`, reset to
  0 after `Update`, STL bounds unchanged), and an `XSecSurf` global transform is
  likewise not baked. Placement/orientation is therefore applied by the
  orchestrator when composing the assembly mesh, and checked explicitly.
  Component STL files are written by isolated one-component models because the
  OpenVSP binding has no working subset export (`ExportFile` only accepts
  `(filename, set, type)` and user sets are ignored by the STL writer).
- `aircraft/openvsp_check.py` — the RCAIDE-environment orchestrator: resolves the
  external Python/OpenVSP paths (`--openvsp-python`/`--openvsp-root` or
  `CONCORDE_OPENVSP_PYTHON`/`CONCORDE_OPENVSP_ROOT`), builds the request from the
  15D geometry model, runs the worker as a subprocess, and measures the STL files
  with `trimesh`. It composes a placed/oriented assembly mesh (main wing at
  `[14, 0, −0.8]`, vertical tail rotated 90° about X then placed at
  `[42, 0, 1]`) and writes the run artefacts. Twenty-one checks OV01–OV21 compare
  model area/span/lengths against the OpenVSP metrics and mesh extents (OV01–OV11)
  and verify placement/orientation on the composed assembly: wing X origin and Z
  centre, tail X/Z origin and vertical Z extent, assembly X origin/extent, wing
  span as Y extent, and assembly Z min/max (OV12–OV21). Missing or unreadable
  component/assembly STL measurements are check failures (`openvsp_check_failed`,
  exit 1), never silently dropped. OV08/OV09 (fuselage width/height) are capped at
  warning because OpenVSP's fuselage spline overshoots the eight-station profile
  (baseline: width +15.0% warns, height +1.17% passes). The `.vsp3`/`.step` files
  keep component local frames; the composed STL is the placed assembly artefact.
  No aerodynamic result is produced; VSPAERO is not run by this check.
- `aircraft/openvsp_perturbations.py` — the OpenVSP perturbation evidence path.
  It rebuilds the model for the baseline plus six representative 15D moves
  (W01 wing area +2%, W02 aspect ratio +2%, V01 vertical-tail area +2%, F01
  fuselage length +1%, F02 nose fineness +2%, F03 height/width ratio +2%), exports
  each case through the same external Python 3.9 worker, measures the component
  and composed-assembly STL files with `trimesh`, and runs nine checks per case
  (OVP01–OVP09: wing/tail area and span, fuselage length readback, composed
  assembly X/Y/Z extents, and a perturbation-reach check that the changed variable
  actually moved the OpenVSP geometry by at least 1e-4 relative). A case whose
  variable does not reach the exported geometry fails. The run keeps the
  per-case request/metrics/checks, delta CSVs, a heat-map figure and a
  README that lists the limitations (twist is not applied to OpenVSP surfaces,
  fuselage spline overshoot, geometry only — no CFD/Mission value).

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
# OpenVSP perturbation evidence (baseline + six 15D perturbations, ~10 s)
./run_rcaide.cmd -m research.concorde_metaopt.cli openvsp-cases \
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

Committed P1 OpenVSP evidence run: `openvsp-check-p1-20261029T1557` — baseline
15D geometry exported to `.vsp3`/`.stl`/`.step`, 21 comparisons (20 pass, one
OV08 fuselage-width warning), zero failures, zero measurement failures, zero
true evaluations. The placement/orientation checks OV12–OV21 pass on the
composed assembly: wing X origin 14.0 m and Z centre −0.8 m, tail X origin 42 m
and Z origin 1.0 m with vertical Z extent 5.009 m, assembly X extent 61.66 m,
wing span as Y extent 25.605 m, assembly Z max 6.009 m (1.0 + tail span) and
Z min −2.294 m. The exported binaries are large and live under
`outputs/concorde_metaopt/<run>/openvsp/` (gitignored); the run directory records
their relative paths, sizes and SHA-256, including the composed assembly STL.
OpenVSP is available on this host only through the external Python 3.9
distribution shipped with the install; the project environment 3.11 dependency
list is unchanged. The fuselage spline overshoot is a tool limitation, not a
model bug: the eight-station profile is exact in the model/RCAIDE path, but
OpenVSP interpolates it with a spline and exceeds the nominal width by 15.0% at
the baseline; P1 records the limitation and keeps the model as the authority.
The run records `git_dirty: true` because three pre-existing uncommitted tutorial
edits were present in the worktree; the research code and run artefacts are
otherwise clean and the `git_sha` is `35903cf`.

Committed P1 OpenVSP perturbation evidence run: `openvsp-cases-p1-20261029T1700` —
seven cases (baseline plus six perturbations) exported through OpenVSP, 63 checks
(62 pass, one baseline perturbation-reach skip, zero fail), zero true evaluations,
wall time about 10 s. The perturbation-reach measurements are the answer to the
"only a mathematical model, zero OpenVSP calls" review point: W01 wing area
+2.000% model / +2.000% OpenVSP, W02 aspect ratio (span) +0.995% / +0.995%, V01
tail area +2.000% / +2.000%, F01 fuselage length +1.000% / +1.000%, F02 nose
fineness (surface change) −0.464% model / +0.034% OpenVSP (the check requires only
a change ≥ 1e-4 because OpenVSP's fuselage spline responds differently from the
model cone formula, and the run marks that as a limitation), F03 fuselage height
+2.000% / +1.148% (within the 2% tolerance band). The full-run 15D → OpenVSP
mapping is recorded here so no dimension is silently dropped:

| model dimension | OpenVSP destination |
| --- | --- |
| W01 wing_area, W02 aspect_ratio | wing area / span and the four section chords (both perturbed here) |
| W03/W04/W05 section sweeps | section LE positions and sweeps of the four wing sections |
| W06/W07 span locations | wing section Y positions (section spans) |
| W08/W09 chord ratios | section chord ratios / root-chord percentages |
| W10 tip twist | **not applied to the OpenVSP surface**: the model and RCAIDE VLM consume tip twist, but the OpenVSP worker does not twist the section; this is the one blocked surface mapping and is stated in the run limitations |
| V01 tail area, V02 tail sweep delta | vertical-tail area / span / three section sweeps (V01 perturbed here) |
| F01 fuselage length, F02 fineness, F03 height/width ratio | fuselage length, nose/tail lengths, station width/height (all three perturbed here) |

Two conventions are explicitly recorded rather than silently aligned: the geometry
model uses `AC = LE(MAC) + 0.25·MAC` while RCAIDE uses the area centroid −0.25·MAC
(equal only for a single trapezoid, so R07 has a 0.25 m tolerance and WARN status),
and RCAIDE forces the last wing/tail segment sweep to the previous segment value
(RCAIDE check R16 records this as INFO).

## P2 status

P2 freezes the single fixed-cruise evaluation contract and implements the
evaluation loop that P3–P6 will reuse.

- `configs/task_fixed_cruise.yaml` + `tasks/task_spec.py` — frozen Phase I task:
  18,288 m (60,000 ft), Mach 2.02, 3,028,020 m (1,635 nmi) cruise; OEW 78,700 kg,
  payload 9,500 kg, cargo 1,000 kg, loaded fuel **46,800 kg**, start mass
  **136,000 kg** (zero-fuel mass 89,200 kg); limits max fuel 95,680 / max zero fuel
  92,000 / max take-off 185,000 kg; four turbojets; objective `fuel_burn_kg` in kg.
  The mass contract is `frozen` because it was measured, not guessed: with the P1
  geometry the same single-cruise mission needs **max throttle 1.2708** at the
  upstream MTOW 185,000 kg (infeasible, the historical failure the old application
  reported), 1.0374 at 155,000 kg, 1.0008 at 150,000 kg and **1.0163 at 145,000 kg**
  (also infeasible; the earlier 0.9642 estimate was extrapolated from the tutorial
  geometry, whose declared root chord is 33.8 m instead of the P1 closure 29.90 m).
  The measured feasible point is 136,000 kg with 46,800 kg fuel: max throttle
  **0.9455** (5.5% margin) and 34,109.5 kg fuel burn. The task validates its own
  mass balance, limits and objective identity on load, attaches its config path for
  run provenance, and can be adapted to `maml_opt.contracts.TaskSpec` for P4/P5. It
  is a cruise-entry contract, not an MTOW mission.
- `aircraft/concorde_adapter.py` — loads the upstream tutorial
  (`tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py`,
  SHA-256 pinned), applies the 15D geometry to the RCAIDE main wing, vertical
  tail and fuselage **before** `configs_setup` (RCAIDE `Config` deep-copies the
  vehicle, so later edits must go to `analyses.<tag>.vehicle`), rebuilds the
  eight fuselage segments (the upstream file appends a duplicate `segment_6` tag
  and silently loses one station), applies the frozen mass contract to the
  analysis vehicle, and re-derives the geometry through RCAIDE
  `wing_planform`/`fuselage_planform` to fail closed on a mismatch.
- `evaluation/contract.py` — ten constraints, all `g <= 0`, with names and
  denominators frozen: `geometry_invalid`, `task_mass_balance`,
  `fuel_capacity_excess`, `zero_fuel_excess`, `takeoff_excess`,
  `fuel_remaining_deficit`, `max_throttle`, `cruise_range_error`,
  `mission_convergence` (both convergence flags and residual norm <= 1e-4) and
  `trim_attitude_limit` (|alpha| <= 12 deg as a force-balance guard; this
  single-segment mission has no moment trim). `empty_constraints()` writes nulls,
  never fabricated numbers; invalid evaluations never get a fake large objective.
- `evaluation/mission.py` — builds the one-segment
  `Constant_Mach_Constant_Altitude` mission and extracts a validated observation
  history (mass/range/time, throttle, fuel mass flow and thrust for the four
  turbojets, alpha/CL/CD, convergence flags, residual norm); non-finite,
  decreasing-range or increasing-mass histories raise `ObservationError`.
- `evaluation/low_fidelity.py` — `SingleCruiseBackend`: one fresh vehicle,
  mission and solver state per evaluation (no warm start), status vocabulary
  VALID / GEOMETRY_INVALID / GEOMETRY_MISMATCH / MISSION_BUILD_FAILED /
  MISSION_FAILED / MISSION_NOT_CONVERGED / INVALID_OR_MISSING_RESPONSE. It is
  task-aware: `evaluate(design, task)` rejects a task whose fingerprint differs
  from the frozen one, and a run only counts as converged when both RCAIDE flags
  hold and the maximum residual is <= 1e-4 (`mission_converged`). Failed or
  invalid evaluations carry `objective: null`. `preflight()` validates the
  template and task with zero physical calls.
- `evaluation/high_fidelity.py` — fail-closed stub: SU2/RANS is not wired in P2,
  so any call raises instead of returning a placeholder number.
- `evaluation/ledger.py` — `EvaluationLedger` enforces the true-evaluation
  budget, passes the frozen task to the backend on every call, and is
  fail-closed: a record keeps its objective and feasibility only when its status
  is VALID, the objective is finite, **exactly the complete frozen constraint
  schema** (all ten names, finite values) is present and no unknown constraint
  names are supplied; otherwise the row is demoted to
  `INVALID_OR_MISSING_RESPONSE` with `objective: null` and `feasible: false`
  (and is never cached), so a misbehaving backend cannot inject a
  feasible-looking objective through a partial or all-null mapping. It also
  rejects impossible physical-call accounting: a non-integer or negative count,
  a non-cached evaluation reporting zero calls, or a count larger than the
  remaining budget marks the row `BACKEND_ERROR`, increments
  `budget_overruns`, sets `budget_exceeded` in the summary and is never cached.
  A task object without a fingerprint cannot key the cache, so that request is
  always physical. It caches only VALID results keyed by task
  fingerprint + fidelity + canonical design (a cache hit consumes no budget and
  reports `physical_call_count: 0`), records backend exceptions as
  `BACKEND_ERROR`, and writes the Issue-mandated `evaluations.jsonl` fields. It also writes
  `evaluations_detail.jsonl`: one row per true evaluation with the full backend
  record (mission responses, geometry cross-check, mass contract, design), with
  non-finite values serialised as null; cache hits are not repeated there.
- `evaluation/smoke.py` — three baseline repeats with caching disabled
  (repeatability tolerance 1e-6) and two perturbations, W01 `wing_area` +1% and
  W10 `tip_twist` 0 -> +2 deg. Repeatability passes only when exactly three rows
  were recorded and all three are VALID with a finite objective
  (`rows_recorded`/`valid_rows`/`required_rows` plus a reason are written). The
  summary carries an explicit constraint gate over every recorded row: a strict
  `all_g_le_zero` flag (any positive value, however small, makes it false), a
  tolerance-aware `all_g_le_zero_within_tolerance` (1e-12) flag, the maximum
  positive excess and the offending entries. Writes `summary.json`, `run_config.json`,
  `environment.json`, `best_design.json`, `evaluations.jsonl`,
  `evaluations_detail.jsonl`, `smoke_cases.csv`, `task_spec.json`, two figures
  and a run `README.md`, records the baseline mass contract and geometry
  cross-check counts, and updates `optimization_runs/index.json`.
- `reports/figures.py plot_smoke_artifacts` — redraws the repeatability and
  perturbation figures from `evaluations.jsonl`/`smoke_cases.csv` alone.

Run the P2 smoke (three repeats + two perturbations = five true evaluations,
roughly 80 s each on this host):

```bash
./run_rcaide.cmd -m research.concorde_metaopt.cli smoke \
  --run-id <run_id> --output-root research/concorde_metaopt/optimization_runs
```

P2 evidence so far: `smoke-p2-20261029T1520` ran five true evaluations against the
145,000 kg contract, which the run itself proved infeasible (baseline max throttle
1.0163). Its status is `smoke_completed_with_failures`: repeatability passed exactly
(three identical 36,469.33 kg burns, relative spread 0.0), the only violated
constraint was `max_throttle` (+0.0163 normalised), and `best_feasible_fuel_kg` is
therefore null. The run is kept as the diagnostic evidence that invalidated the
145 t contract. It predates the `evaluations_detail.jsonl` writer, so its
`README.md` says so explicitly instead of listing a file that does not exist.

The acceptance smoke `smoke-p2-20261029T1612` then ran against the frozen
136,000 kg contract: status `smoke_completed`, five true evaluations, five
feasible results, repeatability spread 0.0 (`34,109.48` kg three times),
`best_feasible_fuel_kg` `34,035.33` kg, W01 `wing_area` +1% -> `-74.15` kg and
W10 `tip_twist` +2 deg -> `+8.07` kg. Both runs are listed in
`optimization_runs/index.json`.

After the A5 review the constraint flags in both committed summaries were
recomputed from the unchanged `evaluations.jsonl` (no Mission was re-run; each
`summary.json` records a `regeneration` block). The strict flag is false in both
runs because the range residual is a tiny positive number: in the 136 t
acceptance run the largest excess is `+2.0e-15` (only `cruise_range_error`), so
`all_g_le_zero` is false while `all_g_le_zero_within_tolerance` (1e-12) is true
and every result is feasible. In the 145 t diagnostic run the largest excess is
`+0.01675` from `max_throttle`, which exceeds the tolerance, so both flags are
false, matching its `smoke_completed_with_failures` status.

True-evaluation accounting for P2: four calibration missions froze the mass
contract (185 t, 155 t, 150 t and the 4,500 nmi MTOW probe that showed the fuel
cannot close), the first smoke spent five, the 136 t diagnostic contract probe
spent one, and the acceptance smoke spent five, so **fifteen** in total. That
exceeds the provisional 8–12 envelope; it is disclosed in the P2 gate checklist
and in the Issue #1 receipt draft and awaits the repository owner's confirmation.
`run_smoke` still refuses a budget below five.

## P3 status

P3 starts with the dataset pipeline that everything else consumes. It is
**zero-physics** by construction: candidate rows carry `physical_call_count: 0`
and `evaluation_status: "not_evaluated"`, no objective field may exist, and the
run manifest records `objective_fields_present: false`.

- `data/schema.py` — frozen candidate-row schema (`p3-doe-1`): 17 required
  fields, 14 geometry metrics, content-addressed `cand-<sha256[:16]>` ids, and a
  hard ban on `objective`/`feasible`/`constraints`/`fuel_burn_kg`. Every row is
  re-checked by `check_candidate_row`: bounds and C01–C04 cross-constraints in
  the frozen order, finite metrics, `physical_call_count == 0`,
  `evaluation_status == "not_evaluated"`, and the id must match the design.
- `data/generate_doe.py` — `run_doe` draws unit-cube samples with
  `scipy.stats.qmc.LatinHypercube` or scrambled `Sobol`, decodes them through
  the design space, screens each candidate through `build_geometry` + the 23
  model checks (geometry-invalid vs geometry-error kept apart), de-duplicates by
  canonical design, and writes `candidates.jsonl`, `candidates.csv`,
  `data_manifest.json` (sampler, seed, git sha, config hash, counts, file
  hashes, limitations), `environment.json`, `run_config.json`, `summary.json`,
  a run `README.md` and the `optimization_runs/index.json` entry. The summary
  uses the Issue schema with `total_true_evaluations`/`low_fidelity_calls`/
  `su2_calls` all 0 and null objective fields.
- `data/validate_dataset.py` — 12 fail-closed checks DS01–DS12: manifest parse,
  JSONL/CSV presence, row-count agreement, per-row schema/bounds/id checks,
  unique ids, geometry-count agreement, manifest file hashes, current
  design-space config hash, batch totals, zero physical calls / no objective
  fields, and (with `--recompute-geometry`) an independent re-screening of every
  row. Results go to `validation.json`.
- Batch policy: `--n` accepts `32`, `32,128` or a list, so the frozen
  progression 32 -> 128 -> 512 -> 1,500–2,000 can be grown incrementally; total
  candidates per run are capped at 5,000. Geometry screening is cheap (about
  0.2 ms per candidate), so the candidate dataset can be generated ahead of any
  evaluation budget; a candidate is never an evaluation.

Run the P3 DOE screening (zero physical evaluations):

```bash
./run_rcaide.cmd -m research.concorde_metaopt.cli doe \
  --run-id <run_id> --n 32,128 --method lhs --seed 42 \
  --output-root research/concorde_metaopt/optimization_runs --recompute-geometry
```

Committed evidence run `doe-p3-20261029T1725` (git sha in its `summary.json`):
batches `32 + 128` LHS samples (seeds 42 and 43), 160 candidates, 160
geometry-valid, 0 invalid, 0 geometry errors, 0 duplicates, all twelve DS checks
pass including recomputation, zero true evaluations, about 2 s wall time. The
candidate files are the only sizeable artefacts (about 0.3 MB JSONL + 0.1 MB
CSV); they contain no objective values and no physical-call records.

## P4 status

P4 starts with the ordinary constrained baseline that every MAML-A comparison
must beat. `optimization/baseline_bo.py` reuses the installed `maml-opt` package
instead of re-implementing it: `generate_initial_designs` supplies the LHS start
set and `ConstrainedBayesianOptimizer`/`run_search` supply the constrained GP +
expected-improvement loop. The optimizer explores the unit cube `[0, 1]^15`, the
design space decodes each candidate back to physical units, and the frozen
baseline is injected as the first initial design.

Every request goes through the same `EvaluationLedger` as smoke, so budget,
cache and the `evaluations.jsonl` schema are shared and no evaluation can be
hidden from the summary. The run directory adds `opt_trace.jsonl` (one line per
request with acquisition score, predicted feasibility, expected improvement and
selection method), `observations.csv`, `best_design.json`, `data_manifest.json`
(file hashes) and two figures: `convergence.png` (best-so-far versus cumulative
physical calls) and `feasibility_rate.png`.

`optimization/baseline_de.py` implements the second mandatory P4 baseline: a
deterministic single-process DE/rand/1/bin over the same unit cube, sharing the
same ledger, design space and ten constraints so BO and DE are compared at equal
true-evaluation budgets. maml-opt ships no DE implementation and the tutorial DE
driver is tied to a different Nexus/process pool, so this is an explicit
re-implementation (LHS start population seeded with the frozen baseline,
standard feasibility-rule selection, physical-call budget cap, invalid designs
keep `objective: null`). It writes the same artefact set and is selected with
`--algorithm de`.

Both baselines map ledger rows into maml-opt's result dict defensively: a row is
`valid` only when the ledger status is VALID **and** the complete frozen
constraint schema is present; an invalid row is passed with an empty constraint
mapping and is therefore never treated as feasible by the optimizer. Constraint
values are shifted by the contract feasibility tolerance (`g - 1e-12`) because
maml-opt tests `g <= 0` exactly while the contract accepts `|g| <= 1e-12`.
A cached duplicate proposal is counted in `duplicate_proposals_ignored` and
skipped instead of aborting the search, and the experiment status is derived from
the ledger (`completed` / `completed_with_failures` /
`no_feasible_solution` / `failed`, with `status_basis: "ledger"`) rather than
echoing the optimizer's raw status. `run_paths.py` validates every run id to a
single relative segment and refuses to reuse a non-empty run directory, so
evidence from two experiments can never be mixed.

The mathematical gate the Issue requires (Analytic test functions before the
Concorde mission) is `tests/test_math_functions.py`: constrained Branin and
Ackley are optimised by the same DE class and by maml-opt's
`ConstrainedBayesianOptimizer`/`run_search`, and the tests check known minima,
feasibility, budget stopping, determinism and the no-feasible-solution path.

Run the baselines (the toy/math tests below prove the loops; a real campaign
needs an approved true-evaluation budget and is not launched by any test):

```bash
./run_rcaide.cmd -m research.concorde_metaopt.cli baseline \
  --run-id <run_id> --algorithm bo --budget 30 --seed 42 --initial-designs 5 \
  --output-root research/concorde_metaopt/optimization_runs
./run_rcaide.cmd -m research.concorde_metaopt.cli baseline \
  --run-id <run_id> --algorithm de --budget 30 --seed 42 --population-size 15 \
  --output-root research/concorde_metaopt/optimization_runs
```

`tests/test_bo_toy.py` (15 tests) drives the BO path with a synthetic quadratic
objective and a throttle-like constraint: it checks that the budget is exactly
spent (12 of 12 calls), that the search improves on the starting point, that an
infeasible case returns `baseline_bo_no_feasible_solution` with
`best_feasible_fuel_kg: null`, the random strategy, validation errors,
existing-directory protection and figure redraw. Adapter tests cover the
ledger-to-maml-opt mapping (partial mapping is not valid, an infeasible row stays
valid but not feasible, the tolerance shift makes `g = +1e-12/2` non-positive,
a non-VALID row with an objective is demoted) and the duplicate-tolerant
optimizer (a repeated `tell()` is counted and ignored, an out-of-bounds value
still raises). `tests/test_de_toy.py` (11 tests) does the same for DE
(baseline-design first evaluation, same-seed determinism, population/budget
validation, run-id validation and non-empty-directory refusal). No real RCAIDE
evaluation is executed there. A real P4 campaign (proposal: 35–50 true evaluations, about 80 s each) is
blocked on the repository owner's budget approval.

## Review fixes (P2/P4 independent review 2, 2026-10-29)

A second independent code review of the P2 evaluation loop and both P4 baselines
returned CHANGES_REQUESTED (2 BLOCKING / 5 MAJOR / 4 MINOR; the report is kept
outside the repository at `outputs/agent-worklog/reviews/p2p4_review_2.md`).
Every finding was fixed and covered by a regression test:

- B-1 a partial or all-null constraint mapping could keep its objective and then
  count as "feasible" inside the BO optimizer. The ledger now requires exactly
  the frozen ten-name constraint schema with finite values and rejects unknown
  names; the optimizer adapter re-checks completeness and never forwards a
  partial mapping, so an invalid row stays invalid.
- B-2 the contract's 1e-12 feasibility tolerance contradicted maml-opt's exact
  `g <= 0` test (`+2e-15` was feasible to P2 but infeasible to BO). Constraint
  values are shifted by `-FEASIBILITY_TOLERANCE` before `tell()`, and the run
  status is derived from the ledger instead of the optimizer's raw status. The
  committed P2 summaries keep the strict `all_g_le_zero` flag as a raw record
  (false at a `+2e-15` range residual); only the optimizer input is shifted.
- M-1 the smoke summary copied raw backend records, so a failed repeat could
  still carry an objective and `feasible: true`; the summary now stores only
  sanitized ledger rows.
- M-2 physical-call accounting could exceed the budget or report zero calls for a
  non-cached evaluation; both are now rejected as `BACKEND_ERROR`, counted in
  `budget_overruns` and never cached.
- M-3/M-4 `--allow-existing` could mix old evaluations with new traces, and a
  run id could escape the output root. `run_paths.py` validates every run id to a
  single relative segment and only reuses an existing empty directory.
- M-5 a cached duplicate proposal aborted the BO search with
  `ValueError("Design has already been recorded")`;
  `_DuplicateTolerantOptimizer` (a real `ConstrainedBayesianOptimizer`
  subclass, as `run_search` requires) counts and ignores duplicate `tell()`
  calls.
- m-1 status derivation, m-2 the 1520 run README's missing detail file, m-3
  non-finite values in the generic JSON writer and n-1 the cache task fallback
  are fixed or explicitly documented.

The full suite after these fixes is 248 tests, 1 skipped.

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

`tests/test_design_space.py` (40 tests) covers the real 15D config (order,
identifiers, units, provisional status, baseline SHA), normalization roundtrips,
bound/cross-constraint violations, rejection of missing/duplicate/reordered
variables, wrong units, out-of-range baselines, a frozen flag before the measured
bounds exist, `baseline_geometry` consistency (root chord, span, tail span,
section count, exposed area, status), the C03 expression text, and the YAML-subset
loader (nested data, inline lists, comments, quotes, tabs, duplicate keys, bad
indentation).

`tests/test_openvsp_check.py` (28 tests) drives the orchestrator with fake
workers (no real OpenVSP required): version parsing from the install directory
name, path resolution failures, request construction (components, sections,
symmetric flags, rotation, spans/chords), path sanitisation, comparison
pass/warn/fail/skip semantics including the absolute placement checks, status
aggregation, the 21-row comparison set and its reduced form when STL metrics are
missing, and the unavailable / worker-failed / measurement-failed / successful
run artefacts (summary, README, environment, external artefact hashes,
relative-path policy, writer backups, `--delete-exports`, existing export
directory protection). The perturbation tests additionally cover the seven
cases (bounds-respecting, baseline reach skipped, reach pass/fail when a change
is ignored, the F02 changed-mode rule and case-status aggregation). One
real-worker test is skipped unless
`CONCORDE_OPENVSP_PYTHON`/`CONCORDE_OPENVSP_ROOT` are set.

`tests/test_geometry_15d.py` (23 tests) covers the baseline model values and
derived dependencies, all 31 effect cases (each variable changes at least one
non-echo derived metric; area/span closure; expected directions), rejection of
invalid geometry, the volume-requirement FAIL path, the four negative controls,
RCAIDE cross-checks R00–R18, the derived `failed_count` path, and the run
artefacts (required files, summary fields, per-case JSONL fields, duplicate-run
rejection). Tests use a temporary directory outside the repository.

`tests/test_task_and_evaluation.py` (31 tests) covers the frozen task contract
(exact values, derived margins, fingerprint stability, rejection of unbalanced
masses, unfrozen status, changed objective identity, empty freeze evidence and
out-of-range Mach), the ten constraints (names, normalized range error,
throttle/non-convergence/trim violations, fuel and mass deficits, missing
observation keys), mission assembly from the task (segment altitude/Mach/
distance, control variables, missing analysis tag) and observation extraction
(happy path, increasing mass, decreasing range, non-finite or short histories,
missing propulsor, `thrust_force` fallback). The convergence gate is unit-tested
separately: a 1e-3 residual fails even when both flags are true, and non-finite
or missing residuals fail. No Mission is launched.

`tests/test_budget_and_cache.py` (38 tests) covers ledger budget enforcement
(no row on a rejected call), cache hits that consume no budget, cache-disabled
runs, invalid results not cached, backend exceptions recorded as
`BACKEND_ERROR`, the JSONL row fields and deterministic design ids, best/
first-feasible tracking, the smoke run README mass-contract rendering (nested,
flat fallback, readback disclosure, explicit "not recorded"), the
`--delete-exports` CLI wiring, and the offline smoke workflow (happy path
artefacts including the detailed ledger, repeatability failure, case failure,
minimum-budget rejection, existing run directory protection, figure redraw from
artefacts). Fail-closed tests show that a backend returning an objective with a
non-VALID status, a non-finite objective, no constraints or a partial constraint
schema cannot produce a feasible or cached row. Accounting tests cover
partial/all-null schema demotion, unknown constraint names, a physical-call
overrun and a non-cached zero-call report (both `BACKEND_ERROR` with
`budget_overruns`/`budget_exceeded`), non-integer counts and a task without a
fingerprint that can never hit the cache. A sanitization test proves the smoke
summary stores cleaned ledger rows, and a task-awareness test shows the
single-cruise backend rejects a swapped task fingerprint. The backend is a fake;
no Mission or CFD runs here.

`tests/test_doe_dataset.py` (23 tests) covers batch-size parsing, deterministic
LHS and Sobol sampling, screening outcomes (baseline valid, cross-constraint and
bad-geometry rejection), the candidate schema round-trip and forbidden fields,
content-addressed ids, a 32-candidate run (eight artefacts, manifest counts and
hashes, zero physical calls, full validation with recomputed geometry, seed
reproducibility, multi-batch seed accounting, existing-directory protection) and
tamper detection (out-of-bounds design, deleted row, changed config hash,
injected objective).

`tests/test_bo_toy.py` (15 tests) covers the P4 baseline end to end with a toy
backend: budget accounting, improvement over the starting point, rejected
budgets/initial counts/strategies, the no-feasible-solution path, random
strategy, committed artefacts and manifest hashes, existing-directory
protection, redrawing both figures from the trace alone, the defensive
ledger-to-optimizer mapping (partial mapping, feasibility tolerance, invalid
rows) and the duplicate-tolerant optimizer (a repeated duplicate `tell()` is
counted and ignored).

`tests/test_report.py` (11 tests) covers the read-only report CLI: recomputing
summary counts from `evaluations.jsonl` (including failed physical rows and
cache hits), the R01–R04 summary-versus-recomputed consistency checks, artifact
completeness and absolute-path checks, the cross-run comparison output and figure
regeneration from stored rows. No Mission, CFD or OpenVSP call is made.

All 248 tests pass, 1 skipped (17 audit + 40 design space + 23 geometry + 28
OpenVSP + 31 task/evaluation + 38 budget/cache + 23 DOE + 15 BO toy + 11 DE toy +
11 analytic functions + 11 report; the skipped test is the real OpenVSP worker
integration test, which needs the external Python 3.9 install).

## Out of scope so far

No SU2 case, no fidelity-identity study, no evaluated DOE dataset, no real BO or
DE campaign and no MAML. Those require P3–P6 code gates and explicit user
approval for true-evaluation budgets; the P3 dataset above is geometry screening
only and contains no aerodynamic or mission result, and the P4 baselines are
implemented but have only been exercised on toy backends and analytic functions
so far. The P1 config and geometry
model are provisional and must not be cited as a frozen design space or a
validated aerodynamic model; the effect matrix is a geometry-sensitivity sanity
check only, not a physical performance study. The OpenVSP check and the
perturbation cases verify geometry export only (no VSPAERO/CFD aerodynamic
analysis is claimed; the F02/F03 spline differences are recorded as limitations,
not as physics). The P2 task
contract is frozen and physically measured, but the single-cruise evaluation is
low-fidelity (RCAIDE VLM + turbojet deck) and must not be presented as a
high-fidelity fuel-burn result.