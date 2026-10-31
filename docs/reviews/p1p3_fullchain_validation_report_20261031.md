# P1-P3 full-chain supersonic validation report (D-12D-002)

- Date: 2026-10-31
- Authorised by: owner decision D-12D-002, Issue #4 comment 6538481816
- Executed by: Team Lead (this machine), with independent review requested from the A1-A5 roles
- Run directory: research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z/
- Base commit: 048ef2e55f389b0ae52e8872131dcfcf0c91a1eb, branch research/concorde-metaopt, PR #3
- Status: execution complete; **no phase gate approved**; budget 23/23 exhausted

## 1. Scope and authorisation

D-12D-002 authorised exactly one capped validation of the 12D lifting-surface design set
(main wing W01-W10, vertical tail V01-V02, fixed fuselage) at Mach 2.02: up to 23 solver
process starts, 30 h wall clock, serial, at most 4 CPU cores, split as 6 VSPAERO thin/LF,
4 RCAIDE single-cruise/LF, 6 SU2 Euler/HF and 7 OpenVSP WaveDrag / area-rule analyses.
The same decision froze the cruise condition, the reference quantities and the 12D
design set, required independent review by A1/A2/A3/A4/A5 and required that no number be
promoted to a validated correction without evidence. This report records what was run,
what was measured, what failed and why, and the resulting gate status. It does not request
or grant APPROVED_FOR_NEXT_STAGE.

## 2. Method

1. PRE-0 software preflight on a clean worktree of 048ef2e: 294 unit tests (1 skipped,
   external OpenVSP real-worker only), 12D offline DOE, 12D-to-15-name expansion, G23
   fixed-fuselage check, W10 OpenVSP twist verification. Zero solver starts.
2. LF VSPAERO 6.2.0: isolated-wing DegenGeom export from the same 12D geometry model,
   VSPAERO -setup template patched with the frozen Sref/cref/bref/CG/Mach/Re/Vinf, polar
   runs over alpha = -2..6 deg plus two tessellation densities.
3. RCAIDE single-cruise LF: 12D baseline and W10/V01/V02 perturbations through the
   versioned single-cruise Mission interface, one logged Mission evaluation per case,
   frozen 136000 kg mass contract, 10-constraint fail-closed contract.
4. OpenVSP WaveDrag 3.26.1 plus an independent Eminton-Lord port: analytical Sears-Haack
   benchmark, real-geometry wing-alone and wing-plus-fixed-fuselage area distributions,
   slice/rotation refinement, source-level confirmation of the reference area.
5. SU2 8.5.0 Euler: oblique-shock wedge verification first, then Gmsh tetrahedral meshes of
   the isolated 12D main wing at three densities, medium and fine solved, integrated-force
   stationarity and an independent wall-pressure integration cross-check.
6. End-to-end: E2E-00/E2E-01 through the versioned 12D mission interface with the drag
   ledger and physical-call accounting; no unvalidated external correction injected.

Frozen condition: Mach 2.02, 18288 m, 216.65 K, 7171.544888 Pa, rho 0.115317834 kg/m3,
V 596.037397 m/s, q 20483.94023343017 Pa, Re 8.9397e7, range 3028020 m, start mass
136000 kg, Sref 358.25 m2, cref 18.489893 m, bref 25.604638 m, moment reference
x = 16.821978259514246 m (PROVISIONAL CG, y = z = 0). Wing wetted area is 717.57475 m2;
358.25 m2 is the reference/exposed area and is not the wetted area.

## 3. Budget accounting

| Category | Cap | Used | Cases and outcome |
| --- | --- | --- | --- |
| VSPAERO thin/LF | 6 | 6 | LFV-00, LFV-01/02/03 (invalid template, LD-001), SENS-A, SENS-B |
| RCAIDE single-cruise/LF | 4 | 4 | LFV-04, LFV-05, E2E-00, E2E-01 all VALID |
| OpenVSP WaveDrag / area rule | 7 | 7 | WAVE-00 (data loss, LD-002), WAVE-00R benchmark, WAVE-01..05 |
| SU2 Euler/HF | 6 | 6 | 2 setup failures, HFS-00 wedge, HFS-01 failure, HFS-02, HFS-03 |
| Total | 23 | 23 | HFS-00R and HFS-04 NOT_RUN |

Only solver process starts are billable; mesh generation, geometry export, offline
recomputation, parsing and figure generation are not. Every start is an NA-xxx event in
approval_and_budget_ledger.json with command, wall seconds, return code and status. Failed
starts remain bills; no category cap was raised.

## 4. Results

### 4.1 LF VSPAERO: NOT VALIDATED

At alpha = 2 deg the isolated wing gives CL 0.08388 / 0.08782 / 0.10828 and CDi
+3.435e-4 / -8.942e-4 / -2.261e-2 for coarse / medium / fine tessellation. CDi changes
sign and blows up about 65x between medium and fine and CDtot becomes negative at fine;
CDo at zero lift is identical at 0.005028233 for all densities and equals the solver's own
flat-plate friction estimate. Three early perturbation runs were invalid because the
-setup template was patched without the " = " separator (LD-001): their polars are
non-physical, kept as billed failed evidence, and excluded. Verdict: VSPAERO thin-surface
drag at Mach 2.02 is non-convergent and non-physical here; B-P3-VLM-MACH2 is confirmed by
measurement; only the geometry export and the W10 twist fix survive as usable evidence.

### 4.2 RCAIDE single-cruise LF and E2E: reproducible, physics provisional

E2E-00 reproduces the archived P2 baseline exactly: 34109.48257123768 kg, max throttle
0.9454702906042612, alpha_end 2.8398 deg, CL_end 0.1334329, CD_end 0.0168441. Perturbation
deltas are: W10 tip twist +2 deg +8.072725 kg (+0.02367%), V01 tail area +1% +8.269174 kg
(+0.02424%), V02 tail sweep +2 deg +0.224872 kg (+0.00066%). All four cases are VALID,
feasible, and account exactly one Mission evaluation each. The tail variables are
physically effective but small under zero sideslip. The embedded drag ledger is
PARTIAL_DATA_NOT_VALIDATED (missing drag increment slot); RCAIDE components on Sref are
parasite 0.0034563, induced 0.0035327, compressible 0.0095081, misc 1.675e-5, total
0.0168441, plus non-additive diagnostics wave_lift 0.0042044 and wave_volume 0.0053037.
The mission-atmosphere q is 20654.01 Pa, 0.83% above the frozen value; recorded, not
silently corrected.

### 4.3 Area rule: analytical benchmark PASS, real geometry NOT VALIDATED

The Eminton-Lord analysis reproduces the Sears-Haack closed form to -1.55e-6 relative
(OpenVSP -1.61e-6); an independent Python port matches all five real-geometry runs to
<= 1.8e-6. Source inspection shows WaveDragMgr.cpp defaults Sref to 100 m2 and reports
CDWave = D / Sref; the implied Sref of every case is 100.0000 +/- 0.0002 m2.

Real geometry, coarse discretisation (36 rotation sectors x 200 slices): wing alone
D/q = 12.5789 m2, wing + fixed fuselage 15.5025 m2, i.e. CD on 358.25 m2 of 0.035112 and
0.043272. The paired fuselage zero-lift volume increment is D/q = +2.9236 m2
(D = +59887 N, Delta CD = +0.008161) for the baseline, and +2.6563 m2 for the W03 +1 deg
case. W03 +1 deg lowers wing-alone D/q by 0.8969 m2 and wing+body by 1.1642 m2.

The real-geometry number is not converged: refining to 72 sectors x 800 slices raises
wing+body D/q to 44.4387 m2 (2.87x); holding the rotation grid fixed gives a 1.90x slice
effect and a 1.51x theta-sampling effect; at the only common angles (0 and 180 deg) the
ratio is 1.045. Individual rotation sectors scatter from 9.3 to 742 m2. The Eminton-Lord
matrix condition number scales like n^3.1 (1.9e6 at 200 slices, 1.2e8 at 800) and the
sliced area distributions carry visible stair-stepping (max jump 1.43 m2 at the worst
angle). This is numerical amplification of discretisation noise, not physical convergence.
The absolute level contradicts the independent RCAIDE chain by 2.6x (coarse) to 7.4x
(fine); the paired increment alone equals 48% of RCAIDE total drag, and injecting it would
need 50635 kg of fuel against 46800 kg loaded. Verdict: NOT_VALIDATED for the real
geometry; BODY-CORR stays BLOCKED; the increment is retained only as a candidate with a
documented magnitude warning and is not injected into any mission.

### 4.4 SU2 Euler HF: PARTIAL

Wedge verification (Mach 2.0, 10 deg half-angle): wall pressure ratio 1.699422 vs 1.706579
(-0.42%), wall Cp 0.244872 vs 0.252350 (-2.96%), post-shock pressure ratio 1.67271
(-1.98%). Shock angle from pressure crossings at x = 5/6/7 is 40.902 / 41.303 / 41.364 deg
versus the theoretical 39.3139 deg (+1.59 / +1.99 / +2.05 deg), through-origin fit
41.927 deg (+2.61 deg), density crossings (valid only for x >= 3) 41.979 deg (+2.67 deg).
The pre-declared acceptance tolerance of 1 deg is missed, so the wedge benchmark is
PARTIAL. rms[Rho] plateaued at -1.905 instead of the requested -8, consistent with a sharp
leading-edge singularity; the planned second wedge mesh (HFS-00R) is NOT_RUN because the
SU2 cap was consumed by setup failures.

Isolated wing, inviscid Euler, AoA 2.8398 deg: medium (125876 tets) CL 0.0927765996,
CD 0.006819724029, CMy -0.03807613433, wall 394 s; fine (256455 tets) CL 0.09547677964,
CD 0.007117048361, CMy -0.0394070004, wall 871 s; HFS-01 (coarse) failed on a mesh-format
defect in our own converter and is billed. CD/CL/CMy are stationary over the last 200
iterations (relative peak-to-peak <= 6.3e-9); this does not hold for every monitored
component (HFS-02 CMx 4.6e-7, HFS-03 CMx 3.6e-3 relative). An independent wall-pressure
integration reproduces the solver CD/CL to machine precision (medium drag 50045.7 N, lift 680829.2 N),
so the post-processing chain is verified. Grid sensitivity medium to fine is CD +4.36%,
CL +2.91%, CMy -3.50%: two levels do not demonstrate convergence and no order of accuracy
is established. Mesh body volumes by divergence are 128.483 / 128.828 / 129.014 m3 versus
the analytic 129.4516 m3 (-0.75% / -0.48% / -0.34%, monotone); wall areas are 722.28 /
722.57 / 722.76 m2 versus 717.57475 m2 (+0.66% / +0.70% / +0.72%, expected faceting bias).
HFS-04 (W10 +2 deg) is NOT_RUN. Euler is inviscid and only the wing is modelled: no
friction drag, no fuselage/tail/nacelle, no CL-matched LF/HF comparison
(Euler CL 0.093 vs mission CL 0.133). Verdict: HF_M2_02 = PARTIAL; nothing may be
described as full-aircraft high fidelity or as a validated fuel-burn label.

### 4.5 Drag bookkeeping end-to-end

drag_component_ledger.json lists RCAIDE LF components, the SU2 isolated-wing pressure drag
(medium 50045.7 N, fine 52228 N on Sref at frozen q), the area-rule absolute level and
paired increments, and the drag-ledger closure status. It explicitly marks these as not
additive across tools, proposes deduplication rules, leaves the increment slot null, and
lists missing terms (wing-body interference calibration, fuselage/tail pressure drag,
viscosity at Re 8.94e7, nacelles/pylons, lift-dependent wave drag, trim drag, component
parasite breakdown, CL-matched comparison). Verdict: NOT_VALIDATED, BODY-CORR BLOCKED.

## 5. Gate status

| Gate | Status | Evidence |
| --- | --- | --- |
| GEO-12D | PARTIAL | 12D config, fixed fuselage, DOE wiring, W10 OpenVSP twist fix verified; no validated geometry-to-force evidence |
| LF-M2.02 | NOT_VALIDATED (LF_PROVISIONAL) | VSPAERO drag non-convergent/non-physical; RCAIDE chain reproducible but empirical |
| HF-M2.02 | PARTIAL | wedge PARTIAL, 2-level wing sensitivity, inviscid, wing only, HFS-00R/04 NOT_RUN |
| BODY-CORR | BLOCKED | area-rule benchmark PASS but real geometry NOT_VALIDATED; no calibrated interference model |
| MISSION-DATA | PARTIAL | instrumented E2E chain and call accounting verified; no validated aircraft label; q +0.83% caveat |
| BUDGET | EXHAUSTED | 23/23 used; further physics requires new owner approval |

No APPROVED_FOR_NEXT_STAGE. P4 BO/DE, P5 MAML and P6 remain frozen. PR #3 stays open; main
is not merged.

## 6. Deviations, failures and corrections

- LD-001: VSPAERO -setup template lacked the " = " separator; three polars non-physical,
  billed, excluded, isolated in the external archive.
- LD-002: OpenVSP analysis result capture requires WriteResultsCSVFile / slice files; the
  first Eminton-Lord run lost its data (billed) and was repeated as WAVE-00R.
- LD-003: SU2 3D ASCII meshes require boundary triangles with VTK type 5, not 3; HFS-01
  failed on this and is billed; converter, preflight and meshes were corrected after.
- HFS-00R (wedge refinement) and HFS-04 (W10 recompute) NOT_RUN at the SU2 cap.
- Post-processing corrections: Cp rebuilt from preserved-variable SURFACE_CSV; density
  crossing statistics exclude invalid upstream stations; mesh body volume uses the
  divergence theorem wall flux rather than the domain volume.
- Mission-atmosphere dynamic pressure 20654.01 Pa (+0.83%) recorded as a caveat.

## 7. Review requested

A1: rerun the committed non-physical test suite in a clean worktree at the run commit and
report pass/fail, log and SHA.
A2: recompute the committed JSON/CSV from the archived raw logs (mesh_convergence,
wave per-theta Donq, mission_e2e deltas) and confirm or refute each number.
A3: confirm repository isolation and that no P5 worktree file entered this run commit.
A4: map every D-12D-002 acceptance criterion to the corresponding committed evidence file
or NOT_RUN/BLOCKED status.
A5: independently re-derive SU2 CD/CL for medium/fine from history CSV, re-derive the
Eminton-Lord numbers from the raw slice files, audit the physical-call accounting and
failure classification, and issue a verdict on whether any gate status above is overstated.

## 8. Conclusion

The authorised 23 solver starts were executed and are fully accounted. The run produced
three honest negative or partial results: VSPAERO LF drag at Mach 2.02 is not usable;
the area-rule level for the real geometry is not converged and is inconsistent with the
independent RCAIDE drag level; the SU2 Euler wing result is inviscid, wing-only and only
two-level grid sensitive, with the wedge shock-angle tolerance missed. The one positive
chain result is reproducibility: the 12D RCAIDE single-cruise chain reproduces the archived
baseline exactly and the V01/V02/W10 sensitivities are measured and small. No gate is
approved, no validated aircraft correction exists, and P4-P6 remain frozen pending the
owner's decisions and any new budget.
