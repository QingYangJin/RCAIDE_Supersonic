# D-12D-003 Round-1: OpenVSP 3.55.0 remediation package (zero solver cases; one unbillable banner probe)

Run id: `openvsp355-remediation-20261102T014411Z`
Round: **Round-1 of the two-round cap in D-12D-003** (zero physical solver starts)
Approval reference: Issue #4 comment 6566994749 / D-12D-003
Status: **ROUND-1 EVIDENCE COMPLETE - NO GATE APPROVED - ROUND-2 BUDGET AWAITING OWNER APPROVAL**

This run contains only tooling, geometry, API, source and offline-analysis evidence. It did **not** run a
VSPAERO, WaveDrag, SU2 or RCAIDE Mission numerical case. The only process launch was one no-model
`vspaero.exe` usage-banner probe (TG-008, section 4): unbillable, no input, no iteration, no artifact.
D-12D-002's 23/23 budget is closed and is **not** carried over. Any Round-2 physical start requires a
per-category written approval by the owner on Issue #4.

## 1. Scope and authority

D-12D-003 instructs the local team to (a) side-install OpenVSP 3.55.0 (Windows x64, Python 3.11) next to
the existing 3.26.1 install without changing PATH, site-packages, or archived evidence; (b) spend at most
two evidence-driven remediation rounds; (c) not start any new physical solve without a per-item budget
approved by the owner. Round-1 is the zero-solve evidence round: audit the new toolchain, re-diagnose the
archived VSPAERO 6.2.0 data, redo the area-rule analysis offline, and submit a Round-2 budget proposal plus
a P4 plan-only sketch.

Explicitly **not** authorized by D-12D-003 and not performed here: any billable solver run, new
Mission/VSPAERO/SU2/WaveDrag numerical case, BO/DE/MAML run, P4 activation, main-branch merge, new Issue,
and any statement that a P1-P3 gate passed. Process-level proof of "zero solver processes of any kind" is
not claimed: this session had no 4688/USN/ETW audit trail and Prefetch reads were EPERM (A1 F6). The
verifiable claim is **zero solver cases / zero billable numerical analyses** plus one disclosed
banner-only version probe.

## 2. Toolchain installation and isolation (no solver)

- Archive: `OpenVSP-3.55.0-win64-Python3.11.zip`, 49,664,844 B, sha256
  `f1fde65f9d48ae482dcad2c0b7711b81a22810871a5bebc236c4618c0131ebb9` (length and Last-Modified
  2026-10-12 04:47:13 GMT match the official download page).
- Expanded install: `D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64`, 491/491 files, 149,488,735 B (archive
  count; the first python import adds 13 `.pyc` files, so a live tree can show 504 files /
  150,078,455 B - a runtime side effect, not part of the archive; A1 F5).
- API: reports `OpenVSP 3.55.0` (major 3, minor 55, change 0). The exact API-name count depends on the
  enumeration method (Lead `dir()` probe 2186, A3 check 2176); both agree on the version tuple.
- Solver binary: `vspaero.exe` v7.2.2 (compiled 2026-10-12 04:08:14 PST), 811,520 B, sha256 prefix
  `db71c4412489af82...`; the copy inside the Python package is byte-identical. `-setup` no longer
  exists in the 7.2.2 usage text (see section 4).
- Old toolchain untouched: OpenVSP 3.26.1 install (240 files) and its `vspaero.exe` v6.2.0
  (561,664 B, sha256 prefix `e1affca0...`) have no post-2026-11-01 modifications; the SUAVE Python 3.9
  worker is unchanged.
- Isolation verified by A3: the 3.55 install added no User/Machine/Process PATH entry in any scope
  (`any_355_path_entry=false`); OpenVSP 3.26.1's pre-existing User/Process PATH entries remain as they
  were (`path_env_has_openvsp=true` refers to 3.26.1). No openvsp/vsp in the RCAIDE env, global Python
  3.9, or SUAVE site-packages, and no OpenVSP registry keys for 3.55. Rollback plan is static only
  (NOT_RUN); it is a directory removal plus removing the launcher env vars.
- Import recipe for the project Python 3.11.17: `os.add_dll_directory(root)` then append
  `root/python/openvsp`, `root/python/degen_geom`, `root/python/utilities`,
  `root/python/openvsp_config` to `sys.path` (a namespace package at `root/python` alone raises
  `AttributeError: module 'openvsp_config' has no attribute 'LOAD_GRAPHICS'`). The repository worker
  `aircraft/openvsp_geometry.py` is still 3.26-era (no `add_dll_directory`, no
  `openvsp_config` entry); the 3.55 probe used an external patched copy. A repository-side change
  belongs to a reviewed fix card, not to this evidence run.

## 3. Geometry parity 3.55.0 vs 3.26.1 (offline-geometry only, no solver)

Comparison is by unique vertex set, because the two STL writers emit different vertex ordering and
formatting; equal file hashes are neither necessary nor sufficient for geometric identity.

- Main wing, baseline: 1082 unique vertices in both versions, `only_old=0`, `only_new=0`
  (identical). W10 = +2 deg tip twist: same 1082/1082 identity; the new-vs-new twist displacement is
  `max|dz| = 0.03396196 m` against the expected `sin(2 deg) x 0.9731361054965724 =`,
  0.03396196030486226 m (within 1e-6), with `max|dy| = 0`.
- Fuselage (same request built by both versions): 559 old vs 552 new unique vertices,
  `only_old=129`, `only_new=122`; nearest-neighbour distance median 4.382 mm, maximum
  **30.0722 mm** over a 61.66 m body (0.049%); bounding boxes identical
  (`x -0.0..61.66`, `y +-1.65614419`, `z +-1.679472375`). The assembled wing+body STL pair has identical
  bbox (`x -0.0..61.66`, `y +-12.802319126`, `z +-1.679472375`), 1627/1627 unique vertices,
  `bbox_max_diff = 0` and hausdorff distance 0.03007221337110905 m, measured on the external Round-1
  export `geometry_wingbody_355_vs_326.json` (sha256
  `9f25a2ef235b9dd18eaaf6db1cdb2ee5e4d38790bcefe6a08b5765fb4147d1b5`), copied here as
  `evidence/geometry_parity_assembled_355_vs_326.json`. Those assembled-model facts are not fields of
  `evidence/geometry_parity_355_vs_326.json`, which carries the per-component comparison (its fuselage
  leaf counts 559/552 are not comparable with the assembled export's 546/546; see the provenance caveat
  in the copied file; A5 F-08).
- Consequence: the wing is cross-version equivalent, so future wing-only comparisons may be made
  across versions **only for geometry**; any paired area-rule comparison (wing-alone vs wing+body)
  must be built and solved **within one version**, because the fuselage subdivision differs by up to
  3.0 cm and a mixed-version subtraction would silently fold that difference into the "body increment".
  This constrains the Round-2 plan: WAVE wing-alone and wing+body must both use 3.55.

Files: `evidence/geometry_parity_355_vs_326.json`, `role_reviews/a1/geometry_diff.json`.

## 4. New solver input generation without starting the solver

VSPAERO 7.2.2 removed the old `vspaero -setup` flow. The 3.55 AnalysisManager supports a two-step
sequence that writes the exact solver inputs and then stops:

1. `VSPAEROComputeGeometry` analysis -> writes `.vspgeom` (geometry processing, no solver fork).
2. `VSPAEROSweep` analysis with `StopBeforeRun = 1` -> writes `.vspaero` and returns before the solver
   process is forked.

Source evidence (tag `OpenVSP_3.55.0`, commit `5240ef210f41c5d6aeed0ba7687f6fab0ca0cafb`):
`AnalysisMgr.cpp:2255` registers `StopBeforeRun` ("Flag to stop after writing files, but before running
VSPAERO."), `:2875-2878` reads it, `:2044-2156` runs `VSPAEROComputeGeometry`, and
`VSPAEROMgr.cpp:2142-2146` returns before `:2149 m_SolverProcess.ForkCmd(...)`. There is no solver
process start in this path.

Generated inputs (zero solver cases; no `.adb/.history/.polar/.lod/.groups` produced):

| variant | .vspgeom | header | setup file |
|---|---|---|---|
| thick | 503,013 B, sha256 prefix `494feef5bb8b070d...` | `# vspgeom v3`, 1082 nodes / 1088 elements | raw CRLF 930 B / 42 lines, sha256 `c862aa220bc6f3a9...`; committed canonical-LF copy 888 B, sha256 `360618f4b406fa72...` |
| thin  | 224,357 B, sha256 prefix `9fcda6d5d45300fb...` | `# vspgeom v3`, 527 nodes / 480 elements | raw CRLF 930 B / 42 lines, sha256 `c862aa220bc6f3a9...`; committed canonical-LF copy 888 B, sha256 `360618f4b406fa72...` |

Injected reference values: `Sref = 358.25`, `Cref = 18.489893`, `Bref = 25.604638` and
`Xcg = 16.821978259514246` (wing aerodynamic centre, Y=Z=0, **provisional CG**) are the frozen contract
values; `Mach = 2.02`, `AoA = 2.0`, `Beta = 0`, `Symmetry = 0`, `NCPU = 4`,
`RefFlag = MANUAL_REF (0)` are the intended case settings. **Do not read the remaining entries as
frozen conditions**: `ReCref = 1e7`, `Vinf = 100`, `Rho = 0.002377` are VSPAERO defaults copied
by the generator, not the contract atmosphere. The frozen contract values are Vinf 596.0373972278921 m/s,
Rho 0.1153178340089936 kg/m3 and ReCref 89397005.8767656 (`run_lf_case.py:21`); a Round-2 LF generator must
overwrite and assert these three before billing a solver start. See `defaults_not_frozen_contract` in
`evidence/vspaero7_setup_generation.json` (A1 F2). The setup content is identical for both variants
because the settings are identical; the geometry-level difference lives in the `.vspgeom`.
The big `.vspgeom` files are archived under the git-ignored
`outputs/concorde_metaopt/openvsp355-remediation-20261102T014411Z/vspaero7_setup_artifacts/` with
hashes in `evidence/vspaero7_setup_generation.json` and `evidence/vspaero7_setup_artifacts.json`.

`evidence/tooling_events.json` records TG-001..TG-008 (geometry exports, API probes, three setup
generation attempts, source retrieval, version banner). No numerical-analysis start is claimed or
consumed in Round-1. TG-008 is disclosed separately: `vspaero.exe` was launched with no arguments only to
print the v7.2.2 usage banner. That is **one unbillable, no-model process launch**
(`actual_solver_processes = 1`, `billable = false`, `numerical_analysis = false`), not a solver case; it
produced no model, input, iteration or result artifact (A1 F1).

## 5. Archived VSPAERO 6.2.0 results: confirmed invalid / non-converged

A1 independently re-analysed the D-12D-002 archive and corroborates the harness defect LD-001 from the
other direction: in `W01/W03/W10` the `_DegenGeom.vspaero` template had 12 lines written without
`=` (e.g. `Sref 358.25` instead of `Sref = 358.250000`). VSPAERO 6.2.0 silently ignored them and used
its default `Sref = 1.0`, so every printed coefficient was inflated by the case reference area
(about 358x): printed `CL = 31.77605 / 31.32113 / 31.48770`, divided by the case `Sref`, gives
0.08782 / 0.08743 / 0.08789, consistent with the correctly formatted baseline `CL(2 deg) = 0.08781966`.
The same cases show `CDo = NaN(IND)` and a subnormal Reynolds number (~1e-318). Those three cases are
**INVALID** and useful only as a harness-defect proof; they consumed 3 of the 23 D-12D-002 starts.

For the three correctly formatted cases the defect is physical/numerical rather than textual:
Trefftz `CDi` flips sign with mesh density (coarse `+3.435104e-4`, medium `-8.942229e-4`,
fine `-2.260794e-2`; `.history` `CDtrefftz` matches the polar CDi digit for digit), `CL` is not
mesh-converged (`coarse -> fine +29.09%`), and `CDtot` becomes negative at medium AoA 6 deg and for all
fine AoA points. Additional harness defects D1-D5 are listed in
`role_reviews/a1/vspaero_old_diagnostic.md`: a non-zero `vspaero -setup` return code does not stop the
solve, the template mismatch list stays empty, the polar has no finite/Re/negative-drag validation, and
invalid data is still billed.

Consequence for the gates: **LF-M2.02 stays NOT_VALIDATED / LF_PROVISIONAL**, and any earlier statement
that leaned on VSPAERO 6.2.0 CL/CDi magnitudes must be traced and marked not usable. No historical file
is rewritten; this run supersedes those statements in the record.

## 6. Area rule, offline only: arithmetic is right, the geometry inversion is not usable

A2 re-implemented Eminton-Lord offline (zero solver) and checked it three ways:

- It reproduces the archived OpenVSP CDWave values to a relative difference < 2e-6 (max 1.79e-6, WAVE-05)
  (WAVE-01 12.578880 m2, WAVE-02 15.502478, WAVE-03 11.682002, WAVE-04 14.338322, WAVE-05 44.438679),
  so the port itself is correct.
- On the Sears-Haack analytic body it converges to the closed-form value: n=81 `-1.55e-6`,
  n=800 `-1.55e-9`, n=1600 `-1.93e-10` (theory `D/q = 0.10185916357881301`).
- The real-geometry slice areas, however, make the inversion ill-conditioned: matrix condition number
  2.8e4 (n=50), 2.3e5 (n=100), 1.9e6 (n=200), 1.5e7 (n=400), 1.2e8 (n=800); synthetic white noise of
  `sigma = 0.002 .. 0.1 m2` amplifies the raw solution error by 8.7x (sigma = 0.002) and 58x
  (sigma = 0.005) up to 18,380x (sigma = 0.1). A calibrated smoothing
  spline (`lambda = 27.84 sigma^1.606`) keeps the sharp-geometry break bias to -0.29% and is the only
  one of the tested smoothers (fixed Savitzky-Golay gives -27%) that is even usable as a diagnostic.
- The two resolution levels are not converged: 36 rotations / 200 slices vs 72/800 gives a mean
  `Donq` ratio of 2.87. WAVE-05 contains 11 near-tangent outlier thetas (e.g. 73.52 deg with
  `Donq = 742.48 m2`, paired with 180-theta), which are geometric slicing artifacts rather than
  sampling noise. The paired wing+body minus wing-alone fuselage increment has SNR 0.89 and 1.69
  (raw), still below 2 after regularisation, so its value is **INCONCLUSIVE**.

Verdict: WAVE_AREA_RULE remains **NOT_VALIDATED**; **no number from this analysis may be injected as a
body correction**. BODY-CORR stays BLOCKED. This is consistent with, and now quantitatively explains,
the D-12D-002 observation that the area-rule CD was 2.6x-7.4x the independent RCAIDE total drag.

## 7. Round-2 budget proposal (proposal only, not approved)

`budget_request_round2.json` is A2's static proposal: `status = PROPOSED_NOT_APPROVED`, approval target
`Issue #4 / D-12D-003`, **AWAITING_OWNER_APPROVAL**, and no solver was started while preparing it.
It proposes a required tier of 22 starts (VSPAERO7 thin-VLM LF 10 + OpenVSP 3.55 WaveDrag 6 + SU2 8.5
HF 6) plus 4 optional starts (VSPAERO7 thick 2 + RCAIDE LF E2E 2), a total cap of 23, per-category
wall-clock/CPU/RAM limits, stop conditions, a failure-billing rule with at most one retry per case
counted inside the cap, and an explicit NOT_COVERED list (validated full-aircraft fuel label,
body/wing interference correction, transonic drag rise, variable sweep optimisation). D-12D-002's
23/23 is closed and is not carried over.

## 8. P4 plan-only draft (not approved)

`p4_plan_only_draft.md` is a DRAFT submitted for A5 review. It is plan-only: it defines the evaluation
interface contract, the frozen inputs, entry gates, an offline dry-run scope (P4.0), a small LF campaign
(P4.1, budget-gated), and the prerequisites for a HF campaign (P4.2). It does not approve P4 and does not
authorize any optimization run, solver start, or real fuel label. P4-P6 stay frozen until the owner signs
APPROVED_FOR_NEXT_STAGE.

## 9. Role reviews (archived under role_reviews/)

| role | task | result | key finding |
|---|---|---|---|
| A1 code-dev | task-36, task-37, task-43 | completed; zero-solver audit CONFIRMED | 3 archived cases invalid by missing `=`; CDi sign flip and CL non-convergence; 3.55 API/geometry compatibility confirmed; zero solver cases CONFIRMED with the TG-008 banner probe disclosed; Round-2 contract-value injection gap (F2) |
| A2 run-opt | task-38, task-39 | completed | area-rule port valid but inversion ill-conditioned; paired body increment INCONCLUSIVE; Round-2 proposal submitted |
| A3 repo-guard | task-35, task-42 | PASS | install authentic and isolated; commit-isolation delta for dbc325d PASS 7/7 (36 added files, no P5/secret, main untouched) |
| A4 issue-liaison | task-34, task-44 | completed | 35 requirements mapped; Issue #4 receipt DRAFT_NOT_POSTED pending the final commit; PR #3 head must be refreshed |
| A5 code-reviewer | task-41 | APPROVE_FOR_DELIVERY (0 blocker / 0 major / 8 minor / 1 info) | package review; findings addressed in this post-review revision |

A5's review is archived under `role_reviews/a5/`; its deliverables are copied there as canonical-LF
text (see `role_reviews/README.md`). Findings from A5 task-41 (F-01..F-09), A1 task-43 (F1..F6) and
A3's delta isolation are resolved in this revision; no numerical value or gate changed.

## 10. Gate status

| gate | status | note |
|---|---|---|
| GEO-12D | PARTIAL | 12D software path exists and was verified; physical geometry effect at Mach 2.02 still unresolved |
| LF-M2.02 | NOT_VALIDATED / LF_PROVISIONAL | VSPAERO 6.2.0 data invalid or non-converged; no new LF solve in this round |
| HF-M2.02 | PARTIAL | D-12D-002 SU2 wing 2-level only, Euler inviscid, wedge shock angle outside 1 deg |
| BODY-CORR | BLOCKED | no calibrated body/wing interference model; area rule NOT_VALIDATED, no injection |
| MISSION-DATA | PARTIAL | E2E chain reproducible (E2E-00 = 34,109.48257123768 kg) but no validated full-aircraft fuel label |
| BUDGET | AWAITING_OWNER_APPROVAL (label change, not a grant) | D-12D-002 closed with 23/23 consumed and was reported as EXHAUSTED in its close-out. The D-12D-003 label is AWAITING_OWNER_APPROVAL only because an unapproved Round-2 proposal exists; no budget is approved under either label (A5 F-07). |

No gate is approved. APPROVED_FOR_NEXT_STAGE is reserved for the owner and is not requested by this run.

## 11. What this run does not claim

It does not claim a physical result, a validated aerodynamic coefficient, a validated body correction, a
validated full-aircraft fuel label, a passing gate, P4 activation, or that OpenVSP 3.55.0 fixes the
VSPAERO 7.2.2 Mach-2 thin-surface behaviour (that can only be tested in an owner-approved Round-2).

## 12. Files and reproducibility

- `install_provenance.json` - archive/install facts and hashes.
- `evidence/` - geometry parity, API compatibility, setup generation, source evidence, tooling events,
  VSPAERO 7.2.2 usage text, setup artifacts.
- `budget_request_round2.json`, `p4_plan_only_draft.md` - proposal and plan-only draft.
- `summary.json`, `data_manifest.json` - machine summary and hashes of every package file. The manifest
  hashes text as canonical LF (`hash_mode: canonical_lf`) and binaries as raw bytes (`hash_mode: raw`);
  a Windows checkout may still show CRLF copies of committed text (e.g. the setup file is 930 B /
  `c862aa22...` as stored by OpenVSP and 888 B / `360618f4...` canonical).
- `role_reviews/` - `a1/` (API compatibility, old-VSPAERO diagnosis, zero-solver audit), `a2/` (area rule),
  `a3/` (install audit, commit-isolation delta, install checks log), `a4/` (requirements), `a5/` (package
  review); canonical-LF copies of project-external deliverables (see `role_reviews/README.md`).
- `figures/` - only if a figure is backed by real data in this package (see figure captions).

Reproduction notes: the toolchain probe scripts are in the external agent-state directory (paths in
`install_provenance.json`); the run is Windows-only and uses the project Python 3.11.17 for the 3.55 API
and the untouched SUAVE Python 3.9 for the 3.26.1 comparisons. Original large artifacts stay under the
git-ignored `outputs/concorde_metaopt/openvsp355-remediation-20261102T014411Z/` with SHA-256 manifests.
