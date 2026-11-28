# S3 dev-set online trial findings (D-MAML-100K, stage S3)

Status: complete, 48/48 trials, 3072/3072 charged attempts, 0 retries.

## Protocol (frozen before the run)

- 4 dev tasks (val split): DREAL006-VAL-M170-L0090, -M190-L0108, -M210-L0090, -M230-L0108
- 3 arms: SOBOL_BO (cold start + GP-EI), COND_SUPERVISED_KSHOT_BO (5 support + 10-step adaptation + model warm start + GP-EI),
  COND_FOMAML_KSHOT_BO (same but with the FOMAML checkpoint)
- 4 paired repeats, seeds 7/19/43/71, 64 charged evals per trial = 48 x 64 = 3072
- Trial = 5 shared support designs (identical for all arms and repeats of a task) + 3 hot-start points + 56 EI steps
- GP: ConstantKernel(1.0, fixed) x RBF(0.25, fixed) + White(1e-4, fixed), normalize_y, optimizer=None, random_state=0
- Candidate pool: 8192 scrambled Sobol points over the 5D active box, seed 20261125; no pool point reused inside a trial
- 20x10 lattice, geometry reference mode, force lift target, 16 inner-solve hard guard

## Counters

evaluation_attempts_charged 3072 / fresh_evaluator_attempts 3072 / unique_task_design_labels 305 /
vlm_inner_solves_actual 16620 (5.41 per design, max 16 per eval, 2 guard hits) / cache_hits 0

Statuses: VALID 3045, NON_PHYSICAL_CDI 25, ERROR 2, LIFT_RESIDUAL_REJECTED 0, ALPHA_SOLVE_FAILED 0.

## Mean best relative CDi improvement by charged budget (mean over 16 trials per arm)

| arm | B=5 | B=8 | B=11 | B=16 | B=32 | B=48 | B=64 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SOBOL_BO | 0.425 | 0.425 | 0.425 | 0.440 | 0.484 | 0.559 | 0.584 |
| COND_SUPERVISED_KSHOT_BO | 0.425 | 0.661 | 0.661 | 0.661 | 0.667 | 0.667 | 0.697 |
| COND_FOMAML_KSHOT_BO | 0.425 | 0.651 | 0.651 | 0.651 | 0.651 | 0.651 | 0.683 |

B=5 is the shared support set, so all arms coincide there by construction.

## Paired comparisons (same task, same seed)

- B=8, learning arm minus SOBOL: supervised +0.236 (sd 0.121, 15/16 wins), FOMAML +0.225 (sd 0.115, 16/16 wins)
- B=64, learning arm minus SOBOL: supervised +0.113 (sd 0.102, 11/16 wins), FOMAML +0.100 (sd 0.126, 12/16 wins)
- B=64, supervised minus FOMAML: +0.014 (sd 0.080, 3/16 wins) - no meaningful difference

## Where the budget is spent

Earliest step at which the trial's final best design was evaluated:
SOBOL_BO mean 55.2 / median 58; COND_SUPERVISED mean 21.4 / median 6.5; COND_FOMAML mean 17.5 / median 7.0.

The learning arms reach their best design inside the 5 support + 3 warm-start evaluations in the median trial, while
the random-start arm needs almost the whole 64-evaluation budget to reach a worse design. The GP-EI loop adds only
+0.036 (supervised) and +0.032 (FOMAML) between B=8 and B=64, versus +0.159 for SOBOL_BO.

## Reading

1. Task-conditioned supervision is worth roughly +0.10 to +0.11 relative CDi improvement at equal budget, and the
   advantage is already realized at B=8 - it comes from warm-start selection, not from the BO loop.
2. FOMAML adaptation does not beat plain task-conditioned supervision in this stage (+0.014, 3/16 wins). Under the
   S1 finding that conditioning collapses the adaptation gain, S3 confirms the same ordering online.
3. Only 305 unique (task, design) labels were charged across 3072 attempts (9.9%), because the pool, GP and warm-start
   are deterministic and every repeat converges onto the same few designs. The nominal budget therefore overstates the
   information gained; S4 needs per-repeat pool/GP diversity before its 69,120 attempts are spent.

## Limitations

- 4 dev tasks, 4 repeats, 64 evaluations per trial; the plateau at B >= 8 means higher budgets are untested here.
- Warm-start designs come from models trained on the 24 train tasks only; S2 test split untouched.
- 25 non-physical (negative CDi) and 2 solver-guard failures are charged and excluded from the GP, as declared.
- The 20x10 lattice carries a documented ~9% CDi bias versus 45x25 (S0); it is used identically by all arms.
