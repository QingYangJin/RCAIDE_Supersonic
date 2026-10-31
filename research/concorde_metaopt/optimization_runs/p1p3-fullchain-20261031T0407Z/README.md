# P1-P3 full-chain supersonic validation run (D-12D-002)

- **Run id:** p1p3-fullchain-20261031T0407Z
- **Approval:** Issue #4 / D-12D-002 (comment 6538481816) - one-off authorisation for this validation only
- **Status:** EXECUTED. No phase gate is approved. P4-P6 remain frozen.
- **Base commit:** 048ef2e55f389b0ae52e8872131dcfcf0c91a1eb (branch research/concorde-metaopt, PR #3 open against main ec65e5a)
- **Started (UTC):** 2026-10-31T04:07:14Z; **wall-clock limit:** 30 h
- **Numerical-analysis starts:** 23 of 23 (exhausted); **remaining:** 0

This run is the execution of decision D-12D-002: a single, budget-capped, low/high
multi-fidelity look at the 12D lifting-surface design set (main wing W01-W10 + vertical
tail V01-V02, fixed fuselage) at the frozen Mach 2.02 cruise point, plus a Mach-sliced
supersonic area-rule estimate of the fixed-fuselage zero-lift volume wave drag increment.

It does **not** approve any gate, does **not** produce a validated aircraft fuel-burn label,
and does **not** authorise P4 BO/DE, P5 MAML, P6 or any further solver call.

## 1. Frozen conditions

| Quantity | Value |
| --- | --- |
| Mach | 2.02 |
| Altitude | 18288 m |
| Static temperature | 216.65 K |
| Static pressure | 7171.544888256813 Pa |
| Density | 0.1153178340089936 kg/m3 |
| Speed of sound | 295.0680184 m/s |
| Freestream velocity | 596.0373972278921 m/s |
| Dynamic pressure | 20483.94023343017 Pa |
| Re (cref) | 89397005.8767656 |
| Sref | 358.25 m2 |
| cref | 18.489893 m |
| bref | 25.604638 m |
| Moment reference x | 16.821978259514246 m (wing aerodynamic centre; y = z = 0, PROVISIONAL CG) |
| Cruise range | 3028020 m |
| Start mass | 136000 kg (frozen mass contract, task p2-2026-10-29b) |
| Wing area / span / root chord | 358.25 m2 / 25.604638251691824 m / 29.901818514349216 m |
| Wing wetted area | 717.57475 m2 (analytic); 358.25 is reference/exposed area, not wetted |
| AoA used by SU2 | 2.8398297488947493 deg (taken from the archived RCAIDE LF solution; not independently frozen) |

Design space: research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml
(sha256 463bb4a0a0fc06eb7dd6a6d9790f4d5b2b3a8c3d8681d16055036dae0c57fc7b);
fuselage F01-F03 fixed at 61.66 m / 4.30 / 1.152778 per owner decision 2 (computed geometry).

## 2. Budget and accounting

Counting contract (approved): only solver **process starts** are billable
(vspaero.exe, SU2_CFD.exe). Mesh generation, geometry export, offline recomputation,
parsing and figure generation are not billable. A failed start is billable.

| Category | Cap | Used | Result |
| --- | --- | --- | --- |
| VSPAERO thin/LF | 6 | 6 | LFV-00, LFV-01, LFV-02, LFV-03 (invalid, LD-001), SENS-A, SENS-B |
| RCAIDE single-cruise/LF | 4 | 4 | LFV-04, LFV-05, E2E-00, E2E-01 |
| OpenVSP WaveDrag / area rule | 7 | 7 | WAVE-00 (data lost, LD-002), WAVE-00R, WAVE-01..05 |
| SU2 Euler/HF | 6 | 6 | HFS-SETUP-01 (config error), HFS-SETUP-02 (void run), HFS-00 wedge, HFS-01 (mesh-format failure), HFS-02 medium, HFS-03 fine |
| **Total** | **23** | **23** | HFS-00R and HFS-04 are NOT_RUN; the cap may not be raised |

Every start has an NA-xxx event in approval_and_budget_ledger.json with category, command,
start time, wall seconds, return code and status. Failures and harness defects are kept
in the ledger and in docs/reviews/p1p3_fullchain_validation_report_20261031.md.

## 3. Results

### 3.1 PRE-0 / PRE-1 (zero solver starts)

- Clean worktree of 048ef2e: unittest discover ran 294 tests, OK, 1 skipped
  (external OpenVSP real-worker test); log archived in the external state directory
  and summarised in the report.
- 12D offline DOE: 4/4 candidates valid, 0 invalid, 0 physical calls, design_dim 12.
- 12D to 15-name expansion, fixed-fuselage G23 check and DOE 12D wiring verified by the
  committed test suite (tests/test_12d_pipeline.py, tests/test_drag_ledger.py).
- W10 tip twist reaches the OpenVSP surface: 1082 wing vertices, max |dz| = 0.033961960 m
  = sin(2 deg) * 0.973136 m (1e-6), vertical tail and fuselage STL byte-identical.
- Isolated-wing STL and VSPAERO DegenGeom were cross-checked against the geometry model
  (area, span, root chord, station chords, twist) in geometry_validation.json.

### 3.2 Low fidelity, VSPAERO 6.2.0 thin surface: **NOT VALIDATED**

VSPAERO density sensitivity, isolated wing, alpha = 2 deg:

| density | Tess_U x Tess_W | CL | CDi | CDtot | CMy |
| --- | --- | --- | --- | --- | --- |
| coarse | 8 x 17 | 0.08387934 | +0.0003435104 | 0.005420316 | -0.02281313 |
| medium | 16 x 33 | 0.08781966 | -0.0008942229 | 0.004188608 | -0.02582589 |
| fine | 32 x 65 | 0.1082826 | -0.02260794 | -0.01743937 | -0.03696871 |

CDi changes sign and grows about 65x between medium and fine; CDtot is negative at fine;
CDo at alpha = 0 is exactly 0.005028233 for all three densities, which equals the solver's
own flat-plate skin-friction estimate, not an independent drag result. The three early
perturbation cases (W01 +1%, W03 +1 deg, W10 +2 deg) were run with a corrupted -setup
template (LD-001: missing " = " separator) and are non-physical; their polars are isolated
in the external archive and are not used as evidence. Conclusion: VSPAERO 6.2.0 thin-surface
analysis at Mach 2.02 on this wing does not produce convergent, physical drag, so
B-P3-VLM-MACH2 is confirmed by measurement and the LF drag is NOT_VALIDATED. Only the
geometry export and the W10 twist fix are usable evidence from this block.

### 3.3 RCAIDE single-cruise chain (12D): chain reproducible, physics provisional

Four RCAIDE single-cruise Mission evaluations on the 12D set (frozen 136000 kg contract),
each exactly one logged Mission evaluation:

| case | change | fuel burn kg | delta kg | delta % |
| --- | --- | --- | --- | --- |
| E2E-00 | 12D baseline | 34109.48257123768 | 0 | 0 |
| E2E-01 | W10 tip twist +2 deg | 34117.55529648991 | +8.072725252 | +0.02367 |
| LFV-04 | V01 tail area +1% | 34117.751745703776 | +8.269174466 | +0.02424 |
| LFV-05 | V02 tail sweep +2 deg | 34109.70744320392 | +0.224871966 | +0.00066 |

E2E-00 reproduces the archived P2 smoke baseline exactly (match = true), so the 12D to
mission chain and the physical-call accounting are reproducible. All cases are VALID and
feasible, max throttle 0.9455, alpha_end 2.8398 deg. V01/V02 are physically effective but
small under zero sideslip (parasite drag / wetted area / sweep). The RCAIDE drag ledger
in each record is ACCOUNTING_ONLY_UNVALIDATED / PARTIAL_DATA_NOT_VALIDATED (the
drag_coefficient_increment slot is missing); components are parasite 0.003456, induced
(VLM Trefftz) 0.003533, compressible 0.009508, misc 1.67e-5, total 0.0168441, with
diagnostic wave_lift 0.004204 and wave_volume 0.005304 flagged NOT additive.

### 3.4 OpenVSP WaveDrag and Mach-sliced area rule: benchmark PASS, real geometry NOT VALIDATED

- The OpenVSP Eminton-Lord analysis reproduces the closed-form Sears-Haack drag area
  D/q = 128 V^2 / (pi L^4) to a relative error of -1.55e-6 (OpenVSP itself -1.61e-6),
  using the same 81-point area distribution, and an independent plain-Python port of
  emlord matches all five WaveDrag cases to <= 1.8e-6.
- Source inspection confirmed the reference area: WaveDragMgr.cpp default Sref = 100 m2
  and CDWave = D / Sref. The implied Sref of every case is 100.0000 +/- 0.0002 m2.
- Real geometry (coarse: 36 rotation sectors x 200 slices): wing alone D/q = 12.579 m2,
  wing + fixed fuselage 15.502 m2 (CD on 358.25 m2: 0.03511 / 0.04327). The paired
  fuselage increment is D/q = +2.9236 m2 (D = +59887 N, Delta CD = +0.008161).
- The real-geometry result does not converge: refining to 72 sectors x 800 slices raises
  wing+body D/q from 15.50 to 44.44 m2 (2.87x), slice-only effect 1.90x, theta-sampling
  effect 1.51x; per-theta values scatter from 9.3 to 742 m2; the Eminton-Lord matrix
  condition number grows like n^3.1 and the sliced area distributions carry mesh
  stair-stepping noise. This is a numerical artifact, not a physical convergence.
- Absolute level contradicts the independent RCAIDE chain: area-rule wing+body CD 0.0433
  (coarse) to 0.124 (fine) versus RCAIDE total CD 0.016844 (2.6x / 7.4x). The paired
  increment alone would be 48% of the RCAIDE total drag, and injecting it into the
  mission would require 50635 kg of fuel versus 46800 kg loaded (infeasible).
- Verdict: WAVE / area rule NOT_VALIDATED for the real geometry; BODY-CORR stays BLOCKED;
  no increment is promoted to a validated correction.

### 3.5 High fidelity, SU2 8.5.0 Euler: **PARTIAL**

Wedge verification (HFS-00): Mach 2.0, 10 deg half-angle, Euler. Wall pressure ratio
1.699422 versus theory 1.706579 (-0.42%), wall Cp 0.244872 versus 0.252350 (-2.96%),
post-shock p/p_inf 1.67271 (-1.98%). Shock angle: far-field stations x = 5/6/7 give
40.902 / 41.303 / 41.364 deg versus the theoretical 39.3139 deg, i.e. +1.59 / +1.99 / +2.05
deg, and the through-origin fit is 41.927 deg (+2.61 deg). The pre-declared tolerance was
1 deg, so the wedge benchmark is PARTIAL, not PASS. Density-based crossings (valid only for
x >= 3) average 41.979 deg (+2.67 deg). rms[Rho] plateaued at -1.905 and the planned
second wedge mesh (HFS-00R) was never run because the SU2 cap was consumed by setup
failures.

Isolated 12D main wing (inviscid Euler, no fuselage/tail, AoA 2.8398 deg):

| case | mesh tets | CL | CD | CMy | wall s |
| --- | --- | --- | --- | --- | --- |
| HFS-01 coarse | 61436 | FAILED (harness mesh-format defect; still billed) | - | - | - |
| HFS-02 medium | 125876 | 0.0927765996 | 0.006819724029 | -0.03807613433 | 394 |
| HFS-03 fine | 256455 | 0.09547677964 | 0.007117048361 | -0.0394070004 | 871 |

Both completed runs have stationary integrated forces over the last 200 iterations
(relative peak-to-peak <= 6.3e-9), and an independent wall-pressure integration reproduces
the solver CD/CL to machine precision (CD_integrated 0.0068197240294 vs 0.006819724029,
CL_integrated 0.09277659960 vs 0.0927765996; medium mesh drag 50045.7 N, lift 680829.2 N).
However medium to fine changes CD by +4.36%, CL by +2.91% and CMy by -3.50%: two levels are
not enough to demonstrate grid convergence, no order of accuracy is established, and the
residual criterion was never met (force stationarity only). Mesh volumes by divergence are
128.483 / 128.828 / 129.014 m3 versus the analytic 129.4516 m3 (-0.75% / -0.48% / -0.34%,
monotone), and wall areas are 722.28 / 722.57 / 722.76 m2 versus 717.57475 m2
(+0.66% / +0.70% / +0.72%, faceting bias).

HFS-01 failed because the first msh2-to-SU2 converter wrote boundary elements with SU2
type 3 (line) instead of VTK 5 (triangle); the converter, a full mesh preflight and the
three meshes were corrected afterwards, but the failing start is billed. HFS-00R and
HFS-04 (W10 +2 deg) are NOT_RUN because the SU2 category cap (6) is exhausted.

Verdict: HF_M2_02 = PARTIAL. Euler is inviscid (no friction drag), only the isolated wing
is modelled, no CL-matched LF/HF comparison exists (Euler CL 0.093 vs mission CL 0.133),
and nothing here may be described as full-aircraft high-fidelity or used as a validated
fuel-burn label.

### 3.6 End-to-end mission and drag bookkeeping

E2E-00/E2E-01 instrument the 12D design through the versioned RCAIDE single-cruise
interface and record the drag ledger, the fuel burn, thrust, throttle and constraints, the
signed wind-axis to body-axis notes and the real call accounting. No external correction is
injected: the only candidate (area-rule fuselage zero-lift volume increment) is
NOT_VALIDATED, so the external_body_correction block keeps injected = false and stores the
candidate only as an order-of-magnitude warning.

drag_component_ledger.json compares RCAIDE LF, SU2 Euler wing and the area-rule level
side by side and explicitly marks them as NOT additive (different physics, different CL,
different reference areas and q; VSPAERO LF unusable). Deduplication rules are proposed and
the increment slot stays null. Missing terms are listed: calibrated wing-body interference,
fuselage/tail pressure drag, viscous drag at Re 8.94e7, nacelles/pylons, lift-dependent
wave drag, trim drag, component-level parasite breakdown, and a CL-matched LF/HF
comparison. Verdict: drag ledger NOT_VALIDATED, BODY-CORR BLOCKED.

## 4. Gate status after this run

| Gate | Status | Basis |
| --- | --- | --- |
| GEO-12D | PARTIAL | 12D config, fixed fuselage, DOE wiring and W10 OpenVSP twist fix verified; no validated aerodynamic geometry-to-force evidence |
| LF-M2.02 | NOT_VALIDATED (LF_PROVISIONAL) | VSPAERO drag non-convergent and non-physical; RCAIDE chain reproducible but empirical/provisional |
| HF-M2.02 | PARTIAL | SU2 Euler wedge PARTIAL, isolated-wing 2-level grid sensitivity, inviscid only, HFS-00R/04 NOT_RUN |
| BODY-CORR | BLOCKED | area rule benchmark PASS but real geometry NOT_VALIDATED; no calibrated wing-body interference model |
| MISSION-DATA | PARTIAL | instrumented E2E chain and call accounting verified; no validated aircraft fuel label, q mismatch +0.83% recorded |
| BUDGET | EXHAUSTED 23/23 | one-off D-12D-002 authorisation consumed; further physics needs a new owner approval |

No APPROVED_FOR_NEXT_STAGE. P4-P6 frozen. PR #3 stays open and is not merged into main.

## 5. Deviations and incidents (all kept, none silently repaired)

- LD-001: VSPAERO -setup template separator defect made three early polars non-physical;
  the cases stay billed and invalid, data isolated in the external archive.
- LD-002: OpenVSP analysis results must be captured with WriteResultsCSVFile / slice text
  files; the first Eminton-Lord run lost its data and was re-run as WAVE-00R.
- LD-003: SU2 3D ASCII meshes need boundary triangles with VTK type 5, not 3; the first
  wing start failed on this and is billed.
- Post-processing corrections (documented, not budget-affecting): Cp is reconstructed from
  the preserved-variable SURFACE_CSV; density-crossing statistics exclude invalid upstream
  stations (x < 3); mesh body volumes use the divergence-theorem wall flux instead of the
  domain volume.
- Mission atmosphere dynamic pressure is 20654.01 Pa, 0.83% above the frozen 20483.94 Pa.
  This is recorded as a caveat and not "corrected" silently.
- The lagged queue: budget was fully consumed; no retries were possible after the last
  failure.

## 6. Files and reproducibility

Evidence files (committed to PR #3):

- summary and configuration: README.md, run_config.json, environment.json,
  approval_and_budget_ledger.json, toolchain_capability_probe.json
- LF: lf_vspaero_results.json, lf_vspaero_density_sensitivity.csv
- RCAIDE / E2E: mission_e2e.json
- area rule: wave_drag_area_rule.json, wave_per_theta_donq.csv
- HF: hf_su2_results.json, mesh_convergence.csv
- drag bookkeeping: drag_component_ledger.json
- figures: figures/*.png (7 figures)
- manifests: data_manifest.json (all committed files), raw_artifacts_manifest.json
  (pointer to the 195 raw files, 108.8 MB, archived outside git with sha256)
- scripts: scripts/*.py and scripts/*.sh (the exact analysis/orchestration scripts used;
  they contain machine-specific absolute paths to the external state directory and the
  installed OpenVSP/SU2/Gmsh binaries, which are listed in environment.json)

Raw artefacts (meshes, restart/field CSV, histories, logs, DegenGeom, VSPAERO polars,
WaveDrag slice files) live in the git-ignored
outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/ tree with sha256 manifests, per
the D-12D-002 archiving rule.

Reproduction: with the same machine toolchain (environment.json), rerunning requires a new
owner-approved budget because every solver start is billable and this authorisation is
exhausted. The analysis scripts can be re-run offline against the archived raw data without
any solver start.

## 7. What this run does not prove

- it does not validate VSPAERO or any low-fidelity aerodynamic drag at Mach 2.02;
- it does not validate a wing-body interference or fuselage correction, and no number in
  drag_component_ledger.json may be read as a validated correction;
- it does not provide grid-converged or order-verified high-fidelity wing forces, and Euler
  has no viscosity;
- it does not produce a validated aircraft fuel-burn label or a 12D/15D performance map;
- it does not establish MAML/BO benefit and does not authorise P4-P6;
- it does not replace the owner's decision on 12D bounds, fuselage source freezing, mass/CG
  freeze, the 11-case written budget or the high-fidelity path.
