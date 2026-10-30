# P1-P3 12D Supersonic Feasibility Review (GATE-LF / GATE-HF / GATE-CORRECTION)

**Status: STATIC REVIEW — no new physical computation. All five gates remain NOT APPROVED.**
Branch `research/concorde-metaopt`, reviewed HEAD `1f79924e296c511bd6d700bb579b11a685958f6c`.
Run: `research/concorde_metaopt/optimization_runs/review-12d-supersonic-feasibility-20261030T1555/`.
Authority: Issue #4 (current body) + decision D-12D-001. This document is a technical assessment, not an approval and not a substitute for the Issue record.

## 1. Scope and method

The acceptance unit is the 12D set: main-wing W01-W10 plus vertical-tail V01-V02, with the fuselage fixed at the model-computed baseline selected by the owner on 2026-10-30 (item 2). The 15D contract, its 160 DOE candidates and all P1-P3 results are preserved untouched; no 15D result is re-labelled as 12D.

Method: read the real code path that generated the archived P2 numbers, inventory every archived evidence artefact (14 run directories, summary hashes recomputed), audit candidate LF/HF tool capability, and map each variable to its actual geometry -> solver -> Mission consequence. No solver, Mission, mesher or OpenVSP export was executed.

## 2. What the archived low-fidelity path actually is

The tutorial `Concorde.py` attaches RCAIDE `Aerodynamics.Vortex_Lattice_Method()` (`Concorde.py:886`), and RCAIDE's base class defaults `use_surrogate=True` (`Aerodynamics.py:67`, never overridden). Every evaluation therefore rebuilds a surrogate from an 11-Mach-node grid `[0.1,...,2.0,2.5,3.5]` and 7 AoA nodes, then blends subsonic/transonic/supersonic surrogates. Mach 2.02 is **interpolated** between 2.0 and 2.5 (not extrapolated), but the surrogate itself only returns AoA-induced drag; parasite, wave, cooling, form, trim terms are appended by an empirical build-up, and the total is multiplied by a fixed 1.02 trim factor (`total_drag.py:86-102`). The VLM kernel does contain supersonic terms (`VLM.py:248` beta^2 = M^2-1; sonic vortices disabled above M=1), yet the class docstring still calls it "subsonic", and RCAIDE's own induced-drag docstring restricts Trefftz-plane validity to incompressible flow. `B-P3-VLM-MACH2` is therefore still open: the archived numbers are a usable algorithmic objective, not validated Mach-2.02 aerodynamics.

Two further structural facts matter. W10 tip twist **does** reach the RCAIDE VLM panels (adapter sets `wing.twists.tip`; `generate_wing_vortex_distribution.py:151-159,229-243` rotates airfoil points about the leading edge) — and the archived smoke runs prove a real fuel-burn signal (W10 +2 deg: +8.07 kg, +0.0237%). But the OpenVSP exporter documents that twist is **not applied** to wing sections (`openvsp_perturbations.py:590`), so any surface/VSPAERO-based W10 evidence is invalid until fixed.

## 3. Evidence inventory (read-only, verified)

| evidence | count | meaning |
| --- | --- | --- |
| RCAIDE single-cruise Mission evaluations | 10 | two P2 smoke runs, 5 each; logs + evaluations.jsonl exist |
| VSPAERO solves | 0 | none, anywhere |
| SU2 solves | 0 | none; `high_fidelity.py` is a fail-closed stub |
| P1 geometry cases | 31 | 4/4 negative controls, 0 failed checks, 0 true evaluations |
| OpenVSP export cases | 7 | geometry/placement checks only, 0 aerodynamic evidence |
| P3 DOE candidates | 160 | 15D LHS geometry candidates, **0 fuel-burn labels** |

P2 smoke 1612 (136 t frozen contract) is internally consistent: 5/5 VALID, 3 baseline repeats with spread exactly 0.0 kg, baseline 34109.4826 kg, feasible best 34035.3326 kg at W01+1% (-74.1500 kg). P2 smoke 1520 used a 145 t contract and violated max_throttle; it is contract-sensitivity evidence, not a feasible point. A5's independent rerun of the non-physical suite: 327 tests OK, 1 skipped, EXIT_CODE=0 on this HEAD.

## 4. Findings

1. **No 12D design space exists.** `configs/design_space_12d_lifting_surfaces.yaml` is absent; `aircraft/design_space.py` requires exactly the 15 frozen variables. The 12D proposal plus loader/regression tests must be approved and implemented before any 12D run.
2. **W10 exporter defect (major).** VLM applies tip twist; OpenVSP does not. Fix with a regression test, or exclude W10 from surface validation with a written limitation.
3. **V01/V02 sensitivity unverified (major).** No archived perturbation isolates either variable; at zero sideslip the vertical tail is a symmetric surface whose realistic contribution is parasite/wetted drag. The contract forbids keeping physically inert variables to reach 12 dimensions: a small LF zero-sideslip probe (LFV-04/05) is required before the 12D set is certified.
4. **Fixed-fuselage source not frozen (major).** Owner selected computed values, but `docs/planning/baseline_reference_decision.md` is still a proposal and mass/CG/SM remain PROVISIONAL_NOT_FROZEN. Computed body wetted area is +10.62% and frontal area -36.89% versus upstream declared values; both feed body drag and volume wave drag.
5. **DOE is a 15D library (major).** F01-F03 take 160 distinct values each; the 160 candidates cannot be presented as 12D native candidates. They must be projected/labelled as a historical 15D library, never as 160 fuel-burn labels.
6. **Drag ledger has unresolved overlap (blocking for GATE-CORRECTION).** RCAIDE adds Trefftz induced drag and a JAXA supersonic lift wave drag term, both CL^2-scaled; its "additive, no overlap" docstring is an implementation claim, not validation for this configuration. The required separable body/interference correction D_BODY-4 does not exist. D_total is therefore NOT_VALIDATED.
7. **HF is blocked (blocking).** No SU2 case, no wing-only closed external mesh generator, no convergence script; rcaide-multifidelity 0.1.0 is Euler-only with a limited input scope. Euler additionally carries no viscous drag, so it cannot be converted into full-aircraft fuel burn without an audited viscous correction.
8. **Data contract incomplete (major).** Runs store total fuel burn and total CL/CD but no component-level signed N-force ledger.
9. **Budget governance conflict (blocking).** Issue #4 section 2 requires itemized written approval for any diagnostic case; the owner's wing-only approval is verbal only. Until recorded, no case may run. (A5 also reports 15 P2 true evaluations versus the 10 counted here; this discrepancy must be resolved in the receipt.)

## 5. Gate status

| gate | status | what would change it |
| --- | --- | --- |
| GEO-12D | PARTIAL | 12D config + tests; W10 exporter fix; V01/V02 probe; frozen fuselage source |
| LF-M2.02 | PARTIAL (LF_PROVISIONAL) | approved wing-only VSPAERO Mach 2.02 matrix + N-force ledger + double-counting assessment |
| HF-M2.02 | BLOCKED | wing-only SU2 Euler wedge -> 3-level mesh convergence, with viscous-correction statement |
| BODY-CORR | BLOCKED | defined, calibrated body/interference correction with no-overlap proof |
| MISSION-DATA | PARTIAL | section 3 run structure, N-force ledger, DOE projection labelling, clean reproducibility |
| BUDGET | BLOCKED | itemized owner approval recorded in Issue #4 |

No gate can pass on LF-only evidence; each requires the owner's written APPROVED_FOR_NEXT_STAGE.

## 6. Proposed minimum validation (NOT approved, NOT executed)

11 solves: LF VSPAERO thin-surface baseline + W01/W03/W10 perturbations, LF zero-sideslip V01/V02 probes (RCAIDE Mission, 6 solves total); HF SU2 Mach-2 wedge verification plus wing-only Euler mesh M1-M3 and one perturbation re-run (5 solves). Verification baselines, acceptance criteria, stop conditions and reproducibility requirements are itemized in `validation_matrix_and_budget_proposal.json`. All cases run wing-only per the owner's decision; HF carries the inviscid disclaimer. Estimated wall time is order-of-magnitude only (LF 0.5-3 h, HF 3-15 h).

## 7. Top three risks

1. **Method substitution risk.** Treating the surrogated empirical build-up as physical Mach-2.02 aerodynamics. Mitigation: retain LF_PROVISIONAL and require independent VSPAERO evidence.
2. **Unprovable drag accounting.** Without a separable body/interference correction and a resolved induced-vs-lift-wave overlap, no D_total can be validated for the 12D set.
3. **No independent high-fidelity evidence.** The HF path (surface -> mesh -> Euler -> viscous correction) does not exist; until funded, GATE-HF cannot open and the 12D acceptance cannot close.

## 8. Decisions requested

1. Approve the 12D proposal and authorize creating the 12D config + loader tests without touching the 15D contract.
2. Authorize the W10 exporter fix card with its regression test (P1-P3 fix package).
3. Freeze the fixed-fuselage source in `baseline_reference_decision.md` (owner already selected computed values; sign-off still missing).
4. Record itemized written approval of the wing-only minimal validation matrix in Issue #4.
5. Decide whether HF is implemented as a separate approved package or formally marked NOT_IMPLEMENTED_FOR_CONCORDE for this acceptance.

## 9. Reproduction index

`summary.json`, `design_space_12d_proposal.json`, `variable_to_solver_matrix.csv`, `existing_evidence_inventory.json`, `supersonic_aero_method_audit.json`, `drag_ledger_and_double_counting.json`, `validation_matrix_and_budget_proposal.json`, `blocker_register.json`, `data_manifest.json`, `figures/*.png`, `make_figures.py`, `README.md` — all in the run directory above. Code references use `D:/RCAIDE/envs/RCAIDE/Lib/site-packages/RCAIDE/...` for RCAIDE 1.5.0.
