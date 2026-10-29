# P3 fidelity identity and applicability probe plan

Status: **proposed** (2026-10-29). This document defines the P3 fidelity work that
follows the committed DOE screening dataset. It is a technical protocol for human
review, not a result. Nothing in this plan has been executed: the probes listed
below require the budget approval described in "Budget request".

Context: Issue #1 Phase I, P3 ("分批 LHS/Sobol ... 冻结低/高保真分析身份，先
小规模基准 CFD 收敛、3 档网格趋势、少量配对"). The DOE half of P3 is complete and
committed (run `doe-p3-20261029T1725`: 160 candidates, 160 geometry-valid, zero
physical calls, all 12 validator checks pass). This plan covers the remaining
half: fidelity identity, applicability and cost evidence.

## 1. Fidelity identities (frozen labels)

| id | label | implementation | status in this repository |
| --- | --- | --- | --- |
| FI-0 | `rcade_vlm_turbojet` | RCAIDE VLM + turbojet deck single fixed cruise (P2) | implemented and measured (P2 smoke, 5 true evaluations) |
| FI-1 | `vspaero_panel` | VSPAERO 6.2.0 linear panel analysis on OpenVSP degen geometry | not yet run for Concorde at Mach 2; probe P3-F0 below |
| FI-2 | `su2_euler` | SU2 8.5.0 Euler, Gmsh volume mesh from the committed OpenVSP surface | not yet run; probe P3-S0 below |
| FI-3 | `su2_rans` | SU2 RANS with a turbulence model | **out of Phase I scope**; deferred to Phase III (needs validated mesh/turbulence setup) |

Fidelity identity strings, solver version strings, reference quantities and
convergence thresholds are recorded in each run's `summary.json` and
`run_config.json`. LF and HF results are never merged into one table without the
fidelity label.

## 2. What is already known (evidence, not assumption)

- RCAIDE-LEADS 1.5.0 VLM + turbojet deck runs the frozen single-cruise task and is
  repeatable (relative spread 0.0 over three repeats, P2 run `smoke-p2-20261029T1612`).
- OpenVSP 3.26.1 exports the baseline 15D geometry and seven perturbation cases
  (P1 run `openvsp-cases-p1-20261029T1700`), with the assembly composed in
  trimesh because the Python 3.9 binding does not bake XForm placement.
- VSPAERO 6.2.0 executes on OpenVSP degen geometry for a simple wing at Mach 0.3
  (development probe only, not repository evidence). Supersonic applicability is
  **unverified**.
- SU2 8.5.0 is installed and its binaries respond, but **no SU2 case has ever been
  run on this host**. `rcaide_cfd` (rcaide-multifidelity 0.1.0) only accepts a
  straight tapered wing + NACA4 native input, so Concorde must go through an
  explicit whole-aircraft `.vsp3` or a user-provided SU2 mesh; its committed
  evidence covers one wing chain only.
- Gmsh 4.15.2 is installed externally; no Gmsh Python binding exists for the
  RCAIDE Python 3.11 environment.

## 3. Probe batch P3-F0 — VSPAERO applicability (low cost)

Purpose: establish whether a linear panel method is usable at the frozen cruise
Mach and how far its lift/drag is from FI-0. This is an applicability probe, not a
high-fidelity result.

- Geometry: baseline main wing + vertical tail from the committed OpenVSP evidence
  (component STL / degen CSV path recorded in the run manifest).
- Conditions: Mach 0.85 and Mach 2.02; alpha 2 deg and 4 deg at Mach 2.02; sea-level
  standard atmosphere per the VSPAERO setup file (density/temperature recorded).
- Reference quantities: Sref 358.25 m2, bref 25.604638 m, cref 18.489893 m (the
  computed-consistent baseline; D-P1-01).
- Paired FI-0 points: at most 6 RCAIDE evaluations at the same Mach/alpha, single
  cruise, frozen mass contract, to compare CL/CD/Cm with identical units and
  reference quantities.
- Acceptance: each case writes a solver history, a converged-case flag and a
  paired delta table; a non-converged case is reported as such and is never turned
  into a fake objective. Expected outcome is a documented applicability limit
  (panel methods degrade at supersonic leading-edge conditions), not a claim of
  validity.
- Budget: 4 VSPAERO solver calls (fast, seconds each) + 6 FI-0 Mission evaluations.

## 4. Probe batch P3-S0 — SU2 Euler single point + three-grid trend

Purpose: establish a reproducible Euler chain and a grid-convergence trend for one
representative cruise point, plus a small FI-0/FI-2 pairing table.

- Geometry: whole-aircraft surface from the committed composed assembly STL
  (OpenVSP run), with the fuselage spline overshoot recorded as a known geometry
  limitation.
- Meshing: Gmsh 4.15.2, three levels (coarse/medium/fine), same topology and
  boundary-layer policy off (Euler). Mesh statistics (nodes, elements, min quality)
  are recorded per level.
- Solver: SU2 8.5.0 Euler, farfield conditions altitude 18,288 m, Mach 2.02, alpha
  2 deg; reference area 358.25 m2, reference length 18.489893 m; CFL ramp and
  residual targets recorded; one case per grid, one repeat on the medium grid.
- Acceptance: (a) residual drop of at least three orders or a documented
  stagnation with evidence; (b) CL/CD/Cm trend across the three grids; (c) a
  medium-grid repeat within a recorded tolerance; (d) an FI-0/FI-2 pair at the
  identical condition with reference quantities matched. Any case that does not
  converge, or whose mesh build fails, is reported as blocked/failed and stops
  expansion instead of being averaged into a "result".
- Time box: 30 min per SU2 solve and 20 min per mesh build; exceeding a box stops
  that probe with a recorded reason.
- Budget: 8 SU2 calls (3 grids + 1 repeat + 2 condition/robustness checks + 1
  spare = 7, with 8 as the cap) + no additional FI-0 calls beyond the P3-F0 batch.

## 5. Artifacts and record-keeping

- Every probe run writes `research/concorde_metaopt/optimization_runs/<run_id>/`
  with `summary.json`, `run_config.json`, `environment.json`,
  `data_manifest.json`, pairing tables (CSV/JSON) and figures, using the Issue #1
  summary fields with `su2_calls` / `low_fidelity_calls` filled from real counts and
  null objective fields where no optimization is involved.
- Raw grids, SU2 meshes, flow fields and long logs go to the git-ignored
  `outputs/concorde_metaopt/<run_id>/`; `data_manifest.json` records relative
  paths, bytes, SHA-256, physical-review conclusion and access method. Nothing large
  is committed; committed tables are small CSV/JSON/PNG.
- Fidelity identity, solver versions, reference quantities and convergence
  thresholds are mandatory fields, so a later reviewer can see exactly which
  analysis produced each number.

## 6. Budget request (T6 staged approval)

| item | requested | note |
| --- | --- | --- |
| FI-0 Mission evaluations | 6 | pairing only, ~80 s each on this host |
| VSPAERO solver calls | 4 | seconds each |
| SU2 Euler calls | 8 | 3 grids + repeat + checks, time-boxed |
| FI-1/FI-2 claims | none | geometry + applicability evidence only |

No DOE expansion, no baseline/BO/route-A campaign and no MAML run is included in
this request. If a probe exceeds its time box or fails convergence, the run stops
and the negative evidence is reported; budget is not silently re-spent.

## 7. Gate checklist for P3 (proposed)

1. DOE dataset committed, validated (12/12), zero physical calls. **done**
2. Fidelity identity table frozen with explicit version/reference quantities.
   **proposed in this document**
3. VSPAERO applicability probe run, with paired LF table and documented limits.
4. SU2 Euler chain reproducible, three-grid trend and repeat recorded.
5. Dataset manifest and fidelity report committed; raw data referenced by hash.
6. Independent review of the P3 evidence before any P4 optimization campaign.
7. Receipt comment prepared for Issue #1 and published only after explicit user
   approval.

## 8. Open decisions for the repository owner

- Approve or reduce the budget in section 6 (the P2 acceptance smoke already
  exceeded the earlier 8-12 provisional envelope with 15 true evaluations).
- Confirm that FI-3 (RANS) is out of Phase I scope and belongs to Phase III.
- Confirm D-P1-01 (computed-consistent baseline geometry) as the physical reference
  model, or state which upstream declared values must be restored.
- Approve the Issue #1 P2/P3 receipt and the PR #3 title/body update before they
  are published.
