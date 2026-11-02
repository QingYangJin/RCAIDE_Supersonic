# P1-P3 D-12D-003 Round-1 remediation report: OpenVSP 3.55.0 (zero solver starts)

- Date: 2026-11-02
- Approval: Issue #4 / D-12D-003 (comment 6566994749)
- Run package: `research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/`
- Round: Round-1 of at most two; **zero solver starts, zero numerical-analysis starts**
- Verdict: Round-1 evidence complete; **no P1-P3 gate improved or approved**; Round-2 budget awaits the owner

## 1. Executive summary

D-12D-003 asked for a side-install of OpenVSP 3.55.0 (Python 3.11), no new physical solve without a
per-item owner-approved budget, and at most two evidence-driven remediation rounds. Round-1 delivered the
zero-solve half: the new toolchain is installed, authenticated and isolated; the 12D wing geometry is
byte-level equivalent across versions (up to vertex ordering) while the fuselage tessellation changed by
up to 3.0 cm; VSPAERO 7.2.2 inputs can be generated without forking the solver; the archived VSPAERO 6.2.0
results are now independently diagnosed (three cases invalid by a template defect, the rest mesh
non-converged and partly negative-drag); the area-rule arithmetic is ported and validated while the
geometry inversion itself is shown to be ill-conditioned and unresolved; a Round-2 budget proposal
(23 starts, AWAITING_OWNER_APPROVAL) and a P4 plan-only draft are submitted. No solver was started, so no
gate can move on physical grounds.

## 2. What was actually done (all zero-solver)

1. **Toolchain**: archived official `OpenVSP-3.55.0-win64-Python3.11.zip` (49,664,844 B, sha256
   `f1fde65f...`) expanded to `D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64` (491/491 files, 149,488,735 B);
   API reports OpenVSP 3.55.0 (2186 names), `vspaero.exe` is v7.2.2 (811,520 B, sha256 `db71c441...`);
   old 3.26.1 + SUAVE Python 3.9 untouched (old `vspaero.exe` v6.2.0, 561,664 B, sha256
   `e1affca0...`). No PATH/registry/site-packages change (A3 PASS).
2. **Geometry parity**: main wing baseline and W10+2 deg have identical unique vertex sets (1082/1082,
   `only_old=0`, `only_new=0`; twist max|dz| = 0.03396196 m vs analytic 0.03396196030486226 m).
   Fuselage: 559 old vs 552 new unique vertices, 122 unmatched new vertices, nearest-neighbour median
   4.382 mm, max 30.0722 mm (0.049% of 61.66 m), identical bbox. STL file hashes differ across versions
   even where geometry matches, so identity is tested on vertex sets, not hashes.
3. **API compatibility**: 22 analyses; `VSPAEROSweep` has 80 inputs, `WaveDrag` 8, `EmintonLord` 2;
   result capture now requires the `ExecAnalysis` result id (analysis name raises Error Code 15);
   DegenGeom CSV camber row changed from 11 to 14 fields; the repository OpenVSP worker is still
   3.26-era and needs a reviewed fix card.
4. **Solver-input generation**: `VSPAEROComputeGeometry` + `VSPAEROSweep(StopBeforeRun=1)` produces the
   exact solver inputs without a solver fork (source guard returns before `ForkCmd`):
   thick `.vspgeom` 503,013 B (1082 nodes / 1088 elements), thin 224,357 B (527/480), both setup files
   930 B / 42 lines, with Sref 358.25, Cref 18.489893, Bref 25.604638, Xcg 16.821978259514246 (provisional),
   Mach 2.02, AoA 2.0. Eight tooling events, all `solver_starts = 0`.
5. **Archived VSPAERO 6.2.0 diagnosis (A1)**: W01/W03/W10 are INVALID because 12 template lines lacked
   `=`, so VSPAERO used Sref = 1.0 and inflated coefficients by ~358x (printed CL 31.77605/31.32113/31.48770
   -> 0.08782/0.08743/0.08789 after dividing by the case Sref, matching baseline CL(2 deg) = 0.08781966);
   those three cases consumed 3 of the 23 D-12D-002 starts. For the correctly formatted cases, Trefftz CDi
   flips sign with mesh density (+3.435104e-4 / -8.942229e-4 / -2.260794e-2), CL is not mesh-converged
   (coarse -> fine +29.09%), and CDtot becomes negative. Five harness guard defects are documented.
6. **Area rule offline (A2)**: the Eminton-Lord port reproduces the archived CDWave to ~1e-6 and
   Sears-Haack to -1.55e-9 at n=800, but the real-geometry inversion is ill-conditioned (condition number
   1.9e6 at n=200, 1.2e8 at n=800; raw noise amplification 58x-18,380x), the two slice resolutions differ
   by 2.87x, and the paired fuselage increment has SNR < 2. Verdict: NOT_VALIDATED; no correction may be
   injected. BODY-CORR stays BLOCKED.
7. **Governance**: A4 mapped 35 D-12D-003 requirements (14 Round-1 zero-solver, 9 Round-2 budget-gated,
   12 standing) and confirmed PR #3 head 5dcb0bf, open, not merged; main untouched.

## 3. Gate status after Round-1 (unchanged in substance)

| gate | status | reason |
|---|---|---|
| GEO-12D | PARTIAL | 12D software path verified; physical geometry effect at Mach 2.02 unresolved |
| LF-M2.02 | NOT_VALIDATED / LF_PROVISIONAL | archived VSPAERO 6.2.0 data invalid or non-converged; no new LF solve |
| HF-M2.02 | PARTIAL | D-12D-002 SU2 wing 2-level Euler only; wedge shock angle outside 1 deg |
| BODY-CORR | BLOCKED | no validated body/wing interference model; area rule NOT_VALIDATED |
| MISSION-DATA | PARTIAL | E2E chain reproducible (E2E-00 34,109.48257123768 kg) but no validated full-aircraft fuel label |
| BUDGET | AWAITING_OWNER_APPROVAL | D-12D-002 23/23 closed; Round-2 proposal (cap 23) pending |
| APPROVED_FOR_NEXT_STAGE | NOT ISSUED | owner-only, not requested by this run |

## 4. Round-2 proposal (proposal only)

`budget_request_round2.json`: required tier 22 starts (VSPAERO7 thin-VLM LF 10 + OpenVSP 3.55 WaveDrag 6 +
SU2 8.5 HF 6), optional 4 (thick 2 + RCAIDE LF E2E 2), total cap 23, per-category wall/CPU/RAM limits,
stop conditions, one-retry-per-case billing rule, and explicit NOT_COVERED items (validated full-aircraft
fuel label, body/wing interference correction, transonic drag rise, variable sweep optimisation).
D-12D-002's 23/23 is closed and not carried over. **No category is approved; the owner must approve each
category in writing on Issue #4 before any solver start.**

## 5. Independent review and replicability

- Role deliverables (A1-A4) are archived verbatim under `role_reviews/`; A5's package review is recorded
  under `independent_reviews/` when delivered.
- `summary.json` and `data_manifest.json` are generated by committed scripts from package JSON; the
  manifest hashes canonical LF bytes so a clean checkout reproduces every hash.
- Original large artifacts (`.vspgeom`) stay outside git under
  `outputs/concorde_metaopt/openvsp355-remediation-20261102T014411Z/` with hashes in the manifest.
- `figures/geometry_parity_355_vs_326.png` is rendered only from
  `evidence/geometry_parity_355_vs_326.json`.

## 6. Explicit non-claims

No physical result, no validated aerodynamic coefficient, no validated body correction, no validated
full-aircraft fuel label, no gate pass, no P4 activation, and no claim that OpenVSP 3.55.0 / VSPAERO 7.2.2
fixes thin-surface supersonic behaviour. That last question can only be answered by an owner-approved
Round-2 solve.

## 7. Decisions requested from the owner

1. Approve or reject the Round-2 budget proposal per category (and the 23-start cap).
2. Authorize the LD-001 guard fixes (template `=` check, setup return-code gating, polar sanity checks)
   as a repository change card before any Round-2 VSPAERO start.
3. Authorize a single-version 3.55 area-rule re-run, and decide whether the current wing+body geometry is
   to be refined before it (otherwise that analysis may remain INCONCLUSIVE).
4. Decide whether the P4 plan-only draft is acceptable as a planning artifact (it does not un-freeze
   P4-P6 by itself).
5. Confirm that APPROVED_FOR_NEXT_STAGE remains withheld.

---

Full evidence index, file hashes and caveats: `README.md`, `summary.json`, `data_manifest.json` in the
run package.
