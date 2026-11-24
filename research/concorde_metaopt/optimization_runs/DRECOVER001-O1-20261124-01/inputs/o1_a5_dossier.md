# O1 three-arm warm-start comparison -- A5 pre-registration dossier

Run `DRECOVER001-O1-20261124-01` | protocol `O1-THREE-ARM-20261124` | authorization `AUTH-DREAL005-O1-20261124-01` | written 2026-11-24T12:08:44Z

This dossier authorises **nothing**. It documents a protocol that is already frozen in `o1_preregistration.json` (d810c83a6371089dd306fe4ec8948595817d036022e47e9a83a32b5e8890791b, 13909 bytes) so that an independent reviewer can reject it before a single solver start is spent.

## 0. What this stage is, and what it is not

Issue #15 section 6 asks a narrow question: at *equal* real evaluation cost, does a meta-learned warm start reach a lower best-feasible induced drag than a plain Sobol warm start on a new task? O1 is the experiment that answers that question. It is not

* a claim that the meta objective is superior -- the A0 ablation did **not** establish that (paired test delta -893.145 N, 95% CI [-7111.5, 5289.6], sign test p=0.8145; validation was worse, p=0.0309);
* a claim of aerodynamic validation: `physics_validated` stays false and the evidence scope stays `VSPAERO_INTERNAL_ONLY`;
* a global optimum or a regret statement: the search is one frozen two-variable slice;
* a second seed or a second task: Mach 2.10 and seeds 19/43 are explicitly not authorised by this pairing.

## 1. Frozen code

The preregistration binds the exact bytes that will spend the budget:

| file | bytes | sha256 |
| --- | --- | --- |
| `o1_admit_case.py` | 7463 | `d79be02ec4494a3937126f88cf9040b9c77067b6c1b26780715ecde605f316b8` |
| `o1_arms.py` | 27338 | `2fbcb271ff00b4c472b7d6737856a707bb982601a42f462476ee7d332bdb9870` |
| `o1_build_dossier.py` | 14592 | `e27899e44575f877297e8da136c9966c0bbf510e355c7116c8eab03bba6ad6fd` |
| `o1_eval.py` | 12558 | `cd5d4b0d7c2ee80e61cc1b855d31ec724169bf200421881213ebab52406898b8` |
| `o1_make_go.py` | 18303 | `a8ee594f3094aab7b95225ba0e676513e15b2434c21a0887e95f60a791926ee3` |
| `o1_prereg.py` | 17547 | `ac1493e5e35c3c4911077cda6049f7f1d88d5e064bc9d09ccdd171fc7d78acee` |
| `o1_retire_stale.py` | 7024 | `3eaabda4c4d64829c4faf9ed0eeace8a091cf3a9437e1036f5b9276c281e706d` |
| `o1_run.py` | 23873 | `86f0187a029e5e9284fe9d59a48151176b32c693552a2500569f598cd77a4248` |
| `o1_selftest.py` | 7571 | `2baee2859132dae3ab2c63ed61a2de158300d384513b3b0bf0ba25e9c67c2331` |
| `o1_verify_binding.py` | 8347 | `50ba4a31d7d8311de1d98d6e0e27d0ff2eb5c8f28f4b414f8797639d12155742` |

## 2. The new task, and why it is new

| task | Mach | q (Pa) | physics sha256 | in any historical label? |
| --- | --- | --- | --- | --- |
| O1-M190 | 1.90 | 18122.493933 | `e1caa676b2237cbb9f09590ed41a9a36726f738e29d60c16c29758ba3b5f5acb` | no |
| O1-M210 | 2.10 | 22138.559070 | `c298ffb75d600daa79f81d35947fbbe1f46ea02d13e2ad0748cb688d347151cf` | no |

The collision check compared 8 historical physics hashes from the A0 dataset and found no collision. The physics hash excludes the task id and the split by construction, so renaming a task cannot manufacture a new physical task.

First pairing: task `O1-M190`, pairing seed 7, GP seed 7.

## 3. What is held equal, and what is allowed to differ

* the same three real shared support designs
* the same 256-design candidate pool of coordinates (no truth pre-computed)
* the same GP backend RECOVERY_NUMPY_RBF_GP_EI_V1 with the same seed and hyperparameters (candidate_count 256, length_scale 0.35, noise 1e-6)
* the same coarse/refine alpha recipe, lift tolerance, audit and admission gate
* the same geometry contract and the same frozen two-dimensional subspace
* each arm's adaptive proposals use only that arm's own real feedback

The *only* difference between arms is the rule that chooses the three extra initialisation designs:

**SOBOL_BO** -- three LHS designs from seeds 20261125, shared by every Sobol arm and independent of any model

**COND_SUPERVISED_KSHOT_BO** -- rank the common candidate pool with the frozen A0 COND_SUPERVISED_16D checkpoint after K=3 support adaptation, then take the top three

**COND_FOMAML_KSHOT_BO** -- rank the common candidate pool with the frozen A0 COND_FOMAML_16D checkpoint after K=3 support adaptation, then take the top three

Neither K-shot model reads a test label or any optimiser feedback: the context vector is a function of the task specification only (Mach, q, CL target, altitude), and the ranking is computed from the common candidate pool before any of the arm's own adaptive designs exist.

## 4. Cost model, and why every arm stops at eight designs

One design costs **20 internal alpha cases** (7 coarse + 13 refine) and **2 charged solver starts**.

| cap | value |
| --- | --- |
| `affordable_designs_per_arm` | 8 |
| `max_designs_all_arms` | 36 |
| `max_designs_per_arm` | 12 |
| `max_internal_all_arms` | 480 |
| `max_internal_per_arm` | 160 |
| `max_internal_per_design` | 20 |
| `max_starts_all_arms` | 72 |
| `max_starts_per_arm` | 24 |
| `max_starts_per_design` | 3 |
| `parallelism` | 1 |
| `retries` | 0 |
| `solver_timeout_s` | 600 |

The internal cap binds first: 160 internal / 20 per design = **8 designs per arm**, before the 12-design and 24-start caps can bind.

* per arm: 8 designs = 16 starts = 160 internal (equivalent)
* all three arms: 48 starts = 480 internal (equivalent)
* physical bill if everything admits: 48 equivalent minus 2 x 3 shared support starts = 36

The eight designs decompose as three pre-designated shared support designs, three warm-start designs and two adaptive designs. **The support designs are solved once and charged in full to all three arms**, so the equivalent bill is three times the physical bill for that block. The two numbers are reported separately and are never added together or conflated.

The truncation rule is honest by construction: every arm is cut at the same design count, so the report states that the arms were truncated at a common budget rather than claiming they independently converged.

## 5. Preregistered target

Target: best feasible Di at most **0.100000%** below the pre-designated baseline design inside the shared support.

fixed before any O1 result exists; a 0.1% Di reduction is an order of magnitude above the 1e-3 relative lift tolerance that bounds the reported drag, and O0 already demonstrated a reachable 0.2394% effect

Provenance of the cited prior effect, stated plainly: the 0.2394% figure comes from the O0 run, not from O1. It is used only to size a threshold that a reader can judge as plausible or implausible before seeing any O1 number; it is not a fit to O1 data, and no O1 label exists at the time this target was frozen.

The target is fixed before any O1 result exists; it cannot be moved to fit an outcome.

## 6. Shared support and candidate pool

Shared support: 3 designs, seed 20261124, the first of which is the baseline. Design ids:

* `s00` -> `8bd5a6c7c8311938`
* `s01` -> `8591230592ee7d88`
* `s02` -> `284b83c5f16226aa`

Candidate pool: 256 coordinate vectors, seed 20261126, containing **no objective values**.

Pool and Sobol overlap, disclosed rather than left implicit: the pool and the Sobol warm-start triple come from the same LHS generator with different seeds (20261126 vs 20261125), and no point is excluded in advance. This is harmless for the comparison because (a) the SOBOL arm never reads the pool, (b) the two K-shot arms rank the pool but are given no objective value for any point in it, and (c) every design, wherever its coordinates came from, is scored by the same real evaluation and admission gate. Any arm that would propose a design already in its own ledger -- shared support included -- skips it and takes the next, so no arm is charged twice for one design.

Measured overlap between the pool and the Sobol triple: 0 shared coordinate vector(s).

## 7. The carried-forward bill

O0 optimizer, from `o0_batch_close_B02.json`: 12 designs, 23 starts, 227 internal cases.
O0-FINAL verification, from `verification_ledger.json`: 8 starts, 104 internal cases.

O1 authorises **zero** further optimizer designs. Its whole budget is this one pairing, three arms, fixed at the cost model above.

## 8. Stop conditions

* any shared support design fails to admit a raw row -> abort before any arm starts
* an arm reaches eight designs -> stop that arm
* a solver start returns a non-SOLVED status -> record it as a paid failure, keep charging, do not retry (retries are zero)
* a wall-clock or internal cap would be exceeded -> abort rather than overspend

## 9. Primary endpoints

* best_feasible_Di_N at equal equivalent starts/internal
* equivalent starts needed to reach the preregistered target Di
* the anytime curve (best feasible Di against cumulative equivalent starts)
* point-level and run-level feasible rate

## 10. Explicitly not authorised

* Mach 2.10 or any second pairing task
* a second seed for the same task
* more than eight designs per arm in this pairing
* any change to the GP, the alpha recipe, the geometry contract or the tolerance
* reusing an old GO
* touching main or merging any pull request

## 10b. Live authorization artifacts are retired, never silently overwritten

An earlier release of this dossier was reviewed, and that review PASSed. Those bytes no longer exist as the live document: the dossier was re-signed after changes, so the old verdict and the old binding round now name a dossier hash that is not on disk.

Leaving them on the live path would make a GO issued today indistinguishable from a GO issued against the superseded bytes, which is exactly the failure this stage has to avoid. The handling rule, implemented in `scripts/o1_retire_stale.py` and frozen in section 1, is:

* an artifact is retired **only** when it names a dossier or preregistration sha256 that is not the sha256 on disk;
* an artifact that names the bytes on disk is never touched;
* a retired artifact is first copied into a dated history directory, verified byte for byte, and only then removed from the live path -- it is never deleted outright, so the record of what was ever reviewed survives;
* every retirement is written into `o1_retire_record.json` with the old and new hashes, so the substitution is auditable rather than implied.

After retirement the live path holds exactly one verdict and at most one binding round, and both name the dossier bytes on disk. The GO is then gated on that binding round and on that verdict by sha256, so a GO cannot exist for bytes that are not the bytes on disk.

## 11. What the reviewer is asked to judge

1. Is the three-arm comparison fair -- does any arm get information or effort the others do not?
2. Is the cost model arithmetically consistent, and does it prevent silent overspend?
3. Is the preregistered target fixed before the result rather than fitted to it?
4. Does the K-shot warm start use only the frozen checkpoint, the shared support and the task specification -- never a test label, never the other arm's feedback?
5. Does anything in this document claim more than the evidence will support?

