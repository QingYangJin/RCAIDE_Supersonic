# P1-P3 12D Supersonic Feasibility Review (GATE-LF / GATE-HF / GATE-CORRECTION)

**Status: STATIC REVIEW — no new physical computation. All five gates remain NOT APPROVED.**
Branch `research/concorde-metaopt`, base HEAD `1f79924e296c511bd6d700bb579b11a685958f6c`.
Run: `research/concorde_metaopt/optimization_runs/review-12d-supersonic-feasibility-20261030T1555/`.
Authority: Issue #4 current body + D-12D-001. This is a technical assessment, not an approval.

## 1. Scope and method

Acceptance unit: 12D lifting surfaces W01-W10 + V01-V02, fuselage fixed at the model-computed baseline selected by the owner on 2026-10-30 (item 2). The 15D contract, its 160 DOE candidates and all P1-P3 results stay untouched; no 15D result is re-labelled as 12D. Method: read the code path behind the archived P2 numbers, re-hash every artefact (14 run directories), audit LF/HF tool capability, and map each variable to its geometry -> solver -> Mission consequence. No solver, Mission, mesher or OpenVSP export was executed.

## 2. What the archived low-fidelity path actually is

The tutorial `Concorde.py` attaches RCAIDE `Aerodynamics.Vortex_Lattice_Method()` (`Concorde.py:886-887`). RCAIDE defaults `use_surrogate=True` (`Aerodynamics.py:67`, never overridden), so each evaluation rebuilds a surrogate from an 11-Mach grid `[0.1,...,2.0,2.5,3.5]` and 7 AoA nodes; Mach 2.02 is **interpolated** between 2.0 and 2.5. The surrogate returns only AoA-induced drag (`evaluate_VLM.py:26`); parasite, wave, cooling, form and trim terms come from an empirical build-up, and the total is multiplied by a fixed 1.02 factor (`total_drag.py:86-102`). The VLM kernel has supersonic terms (`VLM.py:248`: beta^2 = M^2-1; sonic vortices off above M=1), but its class docstring calls the method subsonic. The archived numbers are an algorithmic objective, not validated Mach-2.02 aerodynamics; `B-P3-VLM-MACH2` stays open.

W10 tip twist **does** reach the RCAIDE VLM panels (`generate_wing_vortex_distribution.py:151-159,229-243`) and the smoke runs show a real signal (+8.07 kg for +2 deg, +0.0237%). But the OpenVSP exporter documents that twist is **not applied** to wing sections (`openvsp_perturbations.py:590`), so surface/VSPAERO W10 evidence is invalid until fixed.

## 3. Evidence inventory (read-only, verified)

| evidence | count | meaning |
| --- | --- | --- |
| RCAIDE single-cruise Mission evaluations | 10 | two P2 smoke runs, 5 each, independently recomputable |
| VSPAERO solves | 0 | none, anywhere |
| SU2 solves | 0 | none; `high_fidelity.py` is a fail-closed stub |
| P1 geometry cases | 31 | 4/4 negative controls, 0 failed checks, 0 true evaluations |
| OpenVSP export cases | 7 | geometry/placement only, 0 aerodynamic evidence |
| P3 DOE candidates | 160 | 15D LHS geometry candidates, **0 fuel-burn labels** |

P2 smoke 1612 (136 t frozen contract): 5/5 VALID, 3 baseline repeats with spread exactly 0.0 kg, baseline 34109.4826 kg, best feasible 34035.3326 kg at W01+1% (-74.1500 kg). Smoke 1520 used a 145 t contract and violated max_throttle; it is contract-sensitivity evidence, not a feasible point. A5's independent suite rerun: 327 tests OK, 1 skipped, EXIT_CODE=0. A5's delivery review of this package: APPROVE_FOR_DELIVERY, 5/5 checks. A5 also resolved the budget count: 10 archived evaluations plus 5 unarchived calls documented only in `research/concorde_metaopt/README.md:468-471` (4 calibration + 1 136 t diagnostic); the receipt must state "10 archived + 5 unarchived", never 15 archived.

## 4. Findings

1. **No 12D design space exists.** `configs/design_space_12d_lifting_surfaces.yaml` is absent and `design_space.py` requires exactly the 15 frozen variables; 12D config + loader/regression tests are a prerequisite.
2. **W10 exporter defect (major).** VLM applies twist, OpenVSP does not; fix with a regression test or exclude W10 from surface validation in writing.
3. **V01/V02 sensitivity unverified (major).** No archived perturbation isolates either; at zero sideslip their realistic effect is parasite/wetted drag, so a small LF probe is required before the 12D set is certified.
4. **Fixed-fuselage source not frozen (major).** Owner selected computed values, but `baseline_reference_decision.md` is still a proposal and mass/CG/SM remain PROVISIONAL_NOT_FROZEN. Computed body wetted area is +10.62% and frontal area -36.89% versus upstream declared values.
5. **DOE is a 15D library (major).** F01-F03 vary across all 160 candidates; they are not 12D native candidates and not fuel-burn labels.
6. **Drag ledger has unresolved overlap (blocking for GATE-CORRECTION).** RCAIDE adds Trefftz induced drag and a JAXA supersonic lift wave drag term, both CL^2-scaled; its "additive, no overlap" docstring is an implementation claim, not validation. The required separable body/interference correction does not exist; D_total is NOT_VALIDATED.
7. **HF is blocked (blocking).** No SU2 case, no wing-only closed external mesh generator, no convergence script; rcaide-multifidelity 0.1.0 is Euler-only with a limited input scope, and Euler cannot be converted into full-aircraft fuel burn without an audited viscous correction.
8. **Data contract incomplete (major).** Runs store total fuel burn and CL/CD but no component-level signed N-force ledger.
9. **Budget governance conflict (blocking).** Issue #4 section 2 requires itemized written approval for any diagnostic case; the owner's wing-only approval is verbal only.

## 5. Gate status

| gate | status | what would change it |
| --- | --- | --- |
| GEO-12D | PARTIAL | 12D config + tests; W10 exporter fix; V01/V02 probe; frozen fuselage source |
| LF-M2.02 | PARTIAL (LF_PROVISIONAL) | approved wing-only VSPAERO Mach 2.02 matrix + N-force ledger + double-counting assessment |
| HF-M2.02 | BLOCKED | wing-only SU2 Euler wedge -> 3-level mesh convergence, with viscous-correction statement |
| BODY-CORR | BLOCKED | defined, calibrated body/interference correction with no-overlap proof |
| MISSION-DATA | PARTIAL | section 3 run structure, N-force ledger, DOE projection labelling, clean reproducibility |
| BUDGET | BLOCKED | itemized owner approval recorded in Issue #4 |

No gate can pass on LF-only evidence; each needs the owner's written APPROVED_FOR_NEXT_STAGE.

## 6. Proposed minimum validation (NOT approved, NOT executed)

11 wing-only solves: LF VSPAERO thin-surface baseline + W01/W03/W10 perturbations and LF zero-sideslip V01/V02 probes (6 solves); HF SU2 Mach-2 wedge verification plus Euler mesh M1-M3 and one perturbation re-run (5 solves). Baselines, acceptance criteria, stop conditions and reproducibility requirements are itemized in `validation_matrix_and_budget_proposal.json`; HF carries the inviscid disclaimer. Wall-time figures are order-of-magnitude only.

## 7. Top three risks

1. **Method substitution** — treating the surrogated empirical build-up as physical Mach-2.02 aerodynamics. Mitigation: keep LF_PROVISIONAL and require independent VSPAERO evidence.
2. **Unprovable drag accounting** — without a separable body/interference correction and a resolved induced-vs-lift-wave overlap, no D_total can be validated.
3. **No independent high-fidelity evidence** — the HF path (surface -> mesh -> Euler -> viscous correction) does not exist, so GATE-HF cannot open.

## 8. Decisions requested

1. Approve the 12D proposal and authorize creating the 12D config + loader tests without touching the 15D contract.
2. Authorize the W10 exporter fix with its regression test (P1-P3 fix package).
3. Freeze the fixed-fuselage source in `baseline_reference_decision.md`.
4. Record itemized written approval of the wing-only minimal validation matrix in Issue #4.
5. Decide whether HF is implemented as a separate approved package or formally marked NOT_IMPLEMENTED_FOR_CONCORDE for this acceptance.

## 9. Reproduction index

All package files are in the run directory above (`summary.json`, the eight JSON/CSV deliverables, `figures/*.png`, `make_figures.py`, `README.md`, `data_manifest.json`). Code references resolved against RCAIDE 1.5.0 under `D:/RCAIDE/envs/RCAIDE/Lib/site-packages/RCAIDE/`.
