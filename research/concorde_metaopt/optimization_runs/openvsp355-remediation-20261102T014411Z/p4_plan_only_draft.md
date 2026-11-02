# P4-PLAN-ONLY draft (12D lifting-surface optimization)

Status: **DRAFT / PLAN-ONLY / NOT APPROVED**. This file is a Round-1 deliverable of D-12D-003 (Issue #4 comment 6566994749). It is not an authorization, not a budget, and not a statement that any gate has passed.

## 1. Authority and framing

- D-12D-003 requires that, if two evidence-driven remediation rounds still fail, the project keeps history and moves to **P4-PLAN-ONLY**, which is explicitly not `APPROVED_FOR_NEXT_STAGE`.
- P4 (constrained BO / DE on the real vehicle) remains frozen until the owner signs `APPROVED_FOR_NEXT_STAGE` after P1-P3 physical gates and budgets are approved item by item.
- This draft exists so that planning and offline work can continue without any physical evaluation, and so that a later owner decision has a concrete contract to approve or reject.
- Round-1 context: D-12D-002 consumed 23/23 authorized numerical starts, no gate passed (GEO-12D PARTIAL, LF-M2.02 NOT_VALIDATED / LF_PROVISIONAL, HF-M2.02 PARTIAL, BODY-CORR BLOCKED, MISSION-DATA PARTIAL). D-12D-002's close-out labelled BUDGET EXHAUSTED; under D-12D-003 the BUDGET status label is AWAITING_OWNER_APPROVAL because an unapproved Round-2 proposal exists. The label change is not a grant and no new physical budget is approved (A5 F-07).

## 2. Permitted and prohibited under P4-PLAN-ONLY

Permitted (zero solver cases):
- planning documents, schemas, interface contracts, offline toy/analytic tests, dry-runs of the optimizer against synthetic or archived objectives, reproducibility scripts, figures computed from already-archived numbers.

Prohibited:
- any Concorde BO/DE campaign with real evaluations; any VSPAERO / WaveDrag / SU2 / RCAIDE Mission start without a per-item owner-approved budget; P5 MAML-A training on real vehicle data; new physical fuel-burn labels; opening new issues; merging to main; injecting an unvalidated body correction into the Mission.

## 3. Frozen inputs for any future P4 evaluation

| Item | Value / path | Status |
| --- | --- | --- |
| Design set | `configs/design_space_12d_lifting_surfaces.yaml` (W01-W10 + V01-V02; fixed fuselage 61.66 m / fineness 4.30 / height-width 1.152778) | variable set owner-approved (D-12D-001); **bounds still provisional (frozen:false)** |
| 15D history | `configs/design_space_15d.yaml`, 160 LHS geometry candidates, 14 archived runs | read-only history; must not be relabelled as 12D fuel labels |
| Mission contract | `configs/task_fixed_cruise.yaml`: Mach 2.02, 18 288 m, 3 028 020 m, start mass 136 000 kg, loaded fuel 46 800 kg, ZFW 89 200 kg | frozen; any change bumps TASK_SPEC_VERSION |
| Reference quantities | Sref 358.25 m2, cref 18.489893 m, bref 25.604638 m, moment reference x 16.821978 m (PROVISIONAL CG) | frozen for comparison; CG not frozen |
| Archived baseline | E2E-00 fuel burn 34 109.48257123768 kg (D-12D-002 instrumented chain) | reproducible; **physics provisional** |
| Constraints | 10 named constraints from `evaluation/contract.py`, feasibility tolerance 1e-12, residual limit 1e-4, max attitude 12 deg | frozen code contract |

## 4. Entry gates for a real P4 campaign

| Gate | Current status | What would have to change |
| --- | --- | --- |
| GEO-12D | PARTIAL (geometry chain software-validated; W10 OpenVSP twist fixed; physical implications not validated) | owner accepts geometry + frozen bounds and fuselage source |
| LF-M2.02 | NOT_VALIDATED (VSPAERO 6.2.0 density-divergent; RCAIDE chain only a surrogate-based build-up) | Round-2 evidence under an approved budget, or an accepted LF_PROVISIONAL label |
| HF-M2.02 | PARTIAL (2-level Euler wing only, wedge shock angle outside 1 deg) | 3-level convergence, wedge grid refinement, accepted inviscid limits |
| BODY-CORR | BLOCKED (no validated wing-body interference/volume-wave increment) | independent calibration and de-duplication rule |
| MISSION-DATA | PARTIAL (23/23 ledger, reproducible chain; q mismatch 0.83%, no validated correction injected) | accepted data contract + reviewer sign-off |
| BUDGET | AWAITING_OWNER_APPROVAL (D-12D-002 EXHAUSTED at 23/23; Round-2 proposal submitted, not approved) | new per-item owner-approved budget |

## 5. Evaluation interface contract (target shape, not yet implemented for real runs)

- One versioned evaluator id per fidelity: `evaluator_id`, `fidelity` (LF/HF), `design_set` (12d_lifting_surfaces), `task_fingerprint`, `code_commit`, `solver_versions`.
- Every requested evaluation writes one `evaluations.jsonl` row with `call_accounting` schema v1 (request / cache_hit / outcome / billable_physical_calls), never a silent count.
- Cache hits must be visible and must not consume budget; failures keep the outcome that actually happened.
- No unvalidated body correction may be injected by default; an injected correction must carry `NOT_VALIDATED` and an explicit flag in the row.
- The optimizer must fail closed: missing objective, non-converged mission, or invalid geometry yields a null objective plus a status code, never a fabricated number.

## 6. Optimization stack and offline dry-run plan

- Baseline: deterministic DE (existing `optimization/baseline_de.py`) and constrained BO with maml-opt 0.1.0 GP/EI (existing `optimization/baseline_bo.py`, currently labelled low-fidelity RCAIDE VLM + turbojet).
- Phase P4.0 (offline, allowed now): freeze evaluator schema; replay archived 10 evaluations through the optimizer interfaces; verify deterministic seeds, constraint mapping (g <= 0 with 1e-12 shift), and 3x-repeatability on the archived baseline; produce synthetic dry-run report with zero solver cases.
- Phase P4.1 (needs owner budget): small LF campaign on 12D with a pre-registered design count, convergence rules, and stop conditions; results must carry LF_PROVISIONAL until LF-M2.02 is accepted.
- Phase P4.2 (needs HF + BODY-CORR acceptance and separate budget): mixed-fidelity campaign only after the correction de-duplication rule is validated.
- P5 MAML-A remains out of scope even in P4-PLAN-ONLY.

## 7. Budget envelope

No number in this section is a request or an approval. A2 is to submit a per-item budget proposal (maximum solver starts per category, retries, wall clock, CPU, RAM, stop conditions) for owner review. Any budget must state: counted process types, whether failures are billable, retry policy, and how mesh generation is separated from solver starts (D-12D-002 counting contract).

## 8. Deliverables of a future approved P4

- run directory under `research/concorde_metaopt/optimization_runs/p4-<UTC_RUN_ID>/`: run_config, budget ledger, evaluations.jsonl, convergence trace, candidate table, constraint diagnostics, figures, summary, manifest with hashes.
- `index.json` entry, report under `docs/reviews/`, and one factual Issue receipt. No gate may be declared passed by the agent; only the owner signs `APPROVED_FOR_NEXT_STAGE`.

## 9. Risks

1. LF evaluator is surrogate-interpolated and empirically built-up; optimizing it may overfit an unvalidated model.
2. Body correction is missing: any fuel-burn improvement claim would inherit an unquantified wing-body error.
3. Bounds are provisional; optimum candidates may sit outside physically meaningful ranges.
4. Archived data (10 valid Mission evaluations, only 5 feasible) is too small for a surrogate/BO claim.
5. Cross-tool double counting (Trefftz induced vs lift wave drag vs area-rule volume wave drag) is unresolved.
6. Mass/CG/SM are provisional, so trim and stability conclusions are limited.

## 10. Explicit non-actions for this round

No BO/DE campaign, no MAML-A training, no VSPAERO/WaveDrag/SU2/RCAIDE start, no new issue, no main merge, no overwrite of 15D configs, no relabelling of the 160 DOE geometry candidates as fuel labels.
