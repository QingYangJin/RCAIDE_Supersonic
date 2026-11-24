# D-REAL-EXP-003 H0 / A0 / O0 independent review dossier

Issue: #15 (2026-11-24) plus its first comment. Its title is "[D-REAL-EXP-003][2026-11-24] 任务条件化FOMAML消融与真实BO优化：立即开启反馈闭环、等预算热启动对照". That title is where the D-REAL-EXP-003 identifier in this dossier's name comes from: it is the experiment tag the Issue carries in its own title, not a label this dossier invents.
Reviewer: A5, an independent model that this round holds read-only local tools (sha256_file, stat_file, list_dir, read_text, grep) scoped to the run root and the run root, the frozen worktree and the read-only A0 run root, so every hash quoted below is checkable rather than merely stated. Not a human signature.
Physical VSPAERO starts used so far in this issue: **23** (227 internal alpha cases): 1 starts and 7 internal cases by the aborted first attempt in section 0b, and 22 starts and 220 internal cases by the optimizer batch closed in section 4b. The optimizer cap is now fully spent, so there is no further optimizer batch; the only physics this document still asks for is the separate O0-FINAL verification budget in section 4b.

## 0. File identity

| file | sha256 | bytes |
| --- | --- | --- |
| `o0_preregistration.json` | `123145bbad45a05a4ae54df303b028e916fcba3f5b93b8352dc680830131ba68` | 23012 |
| `o0_batch_close_B02.json` | `684db6bc56cecd30421a0672063534b7ccdfbc524308ffe963c2d20e96577629` | 3667 |
| `o0_batch_crash_B02.json` | `e24b747ee2afc8ae0a778e511f4a7bf1f4c2a56a1ef142d950e2d8b7f964c484` | 5183 |
| `docs/evidence/dreal005/h0/h0_gate.json` | `d1b13b0149bda407a91d52eb5ede665d685861e211afbc027843ec27fa552a30` | 6336 |
| `docs/evidence/dreal005/h0/geometry_contract.json` | `4c7602c1d28dd235a982b54d9c74454d0727b5b1d726623453a4c59d31a130f0` | 10602 |
| `docs/evidence/dreal005/h0/geometry_contract_verification.json` | `243d1e580a14cd78c68345bd0903717c1093d10b09be4ad3080d40eca1e236b6` | 1507 |
| `D:\RCAIDE\.real_runs\DRECOVER001-A0-20261124-01\training\a0_result.json` | `215a3bdbef6ae1835ddf0d9cb7c6bd54572fb3163c4f7fbb69f6f052e7ff47f9` | 28289 |
| `D:\RCAIDE\.real_runs\DRECOVER001-A0-20261124-01\training\a0_grid_search.json` | `398487764aa4372963a2de60ad51a8a5c7154fe301eec7c88cb6820fec97078b` | 5558 |
| `D:\RCAIDE\.real_runs\DRECOVER001-A0-20261124-01\tables\a0_arm_metrics.csv` | `b29f9f8672a06883aa9cb2d71b3868b584c9477c48107903d4ce227b4201c71a` | 14922 |
| `D:\RCAIDE\.real_runs\DRECOVER001-A0-20261124-01\tables\a0_paired_differences.csv` | `d8b6065df440075649b40dd029c0c751c9829e74b11483f45d27281791c525ba` | 4656 |

**Byte-to-gate binding (verifiable, not asserted).** This dossier cannot contain its own hash, so the binding is closed from outside in three verifiable steps, and no step trusts a value this document asserts about itself:

1. Immediately after these bytes are written, `o0_dossier_receipt.json` is written with the SHA256 and byte count of this exact file, plus the SHA256 of `o0_preregistration.json`.
2. The review harness reads these exact bytes from disk, computes sha256 of them, hands those same bytes to the reviewer and records the measured value in the verdict as dossier_sha256. The reviewer measures it too when it has tools; the harness value is substituted for the model's own and both are kept, so neither is taken on trust.
3. `scripts/o0_verify_binding.py` then re-reads the bytes off disk and writes `o0_binding_verification.json` plus an immutable copy under `a5_support/binding_history/`, and `o0_make_go.py` is hard-gated on that fresh round: it refuses to issue a GO unless the round reports `O0_BYTES_BOUND_MECHANICALLY` with zero failures, was written after the dossier bytes, read exactly the current dossier hash and byte count, is archived, and agrees with both the receipt and verdict.dossier_sha256. One flipped byte anywhere in that chain blocks the GO with a named reason.

Any reader holding these bytes can check the whole chain offline with one sha256sum of this file plus two comparisons against the receipt and the verdict. No gate depends on a hash value that the document reports about itself.

**A document cannot contain its own final hash, so the anchor is the artifact that does.** This file is written first; `scripts/o0_verify_binding.py` then reads the bytes off disk, hashes them, and writes `o0_binding_verification.json` containing that hash plus the receipt hash plus the verdict hash. The GO is refused unless that verifier reports `O0_BYTES_BOUND_MECHANICALLY` with zero failures. The block below is the round already on disk, quoted so the procedure can be inspected without running it: it exists because a current-round value cannot be written into the file it measures.

| archived round | status | failures | dossier sha it read | dossier bytes |
| --- | --- | --- | --- | --- |
| `o0_binding_verification_20261124T070833Z.json` | `O0_BYTES_BOUND_MECHANICALLY` | 0 | `112cfd735eff817d0dad6f0e03e3972553508794ab05046d19aea9a12e5ffe6c` | 24412 |
| `o0_binding_verification_20261124T080415Z.json` | `O0_BINDING_INCOMPLETE_OR_BROKEN` | 3 | `9d9325b48132d45896ca2baa65f96dcda802d087ede6b75fb89541f36e1ce762` | 38558 |
| `o0_binding_verification_20261124T080703Z.json` | `O0_BINDING_INCOMPLETE_OR_BROKEN` | 3 | `77dea8cdd8bcb0f9acb3f2cc188961f5b0051c88df9a3940e99ded6155fb8be6` | 39662 |
| `o0_binding_verification_20261124T081420Z.json` | `O0_BYTES_BOUND_MECHANICALLY` | 0 | `94fef447d87caf2a20778fe8d1d3a449be05f4e13642abcc13b138399a8e0784` | 41448 |
| `o0_binding_verification_20261124T085947Z.json` | `O0_BINDING_INCOMPLETE_OR_BROKEN` | 3 | `237bb31beaf45335571529d8391930eee47ebbcc0ea43d7e4c04a4933f345437` | 49903 |
| `o0_binding_verification_20261124T090942Z.json` | `O0_BYTES_BOUND_MECHANICALLY` | 0 | `ca4145c8e971fd3041bcf10a3f495269734642e941b6eed6d98156aac05528f7` | 50169 |
| `o0_binding_verification_20261124T091159Z.json` | `O0_BYTES_BOUND_MECHANICALLY` | 0 | `90b7e9b8e44cdc01e14c9fb6481200e296179d0e96b8b0d153e972bdae5bfdd1` | 50334 |
| `o0_binding_verification_20261124T101847Z.json` | `O0_BINDING_INCOMPLETE_OR_BROKEN` | 3 | `57f59023e2cdef1b01946bdfd2b9e484f923079e35733b01121c20adb049eb37` | 54250 |
| `o0_binding_verification_20261124T102133Z.json` | `O0_BYTES_BOUND_MECHANICALLY` | 0 | `64b93d00df31bcf7b596ec6814439c66001595c600f3a1eeaa2ed36e21d806ec` | 54419 |

Archive directory: `D:\RCAIDE\.real_runs\DRECOVER001-O0-20261124-01\a5_support\binding_history`. 9 round(s) archived, 5 of them clean.

~~~
verifier file      : o0_binding_verification_20261124T102133Z.json
archived at        : D:\RCAIDE\.real_runs\DRECOVER001-O0-20261124-01\a5_support\binding_history\o0_binding_verification_20261124T102133Z.json
verifier sha256    : ff9dc0556a6dd0792bafddb900cf3608610ffccab23b5a5980553da796035ca7
status             : O0_BYTES_BOUND_MECHANICALLY
check_count        : 10
failure_count      : 0
problems           : []
dossier sha it read: 64b93d00df31bcf7b596ec6814439c66001595c600f3a1eeaa2ed36e21d806ec
~~~

**Read the quoted round for exactly what it is.** It is the most recent round that passed, and it is necessarily a round over an EARLIER dossier: a round over the bytes you are reading cannot be written into this file, and one cannot exist yet either, because the round that binds these bytes also has to agree with the verdict, and the verdict is produced from this file. So the honest order is dossier, then review, then the binding round, then the GO; the round is a hard precondition of the GO and never an input to this document. The table above shows every archived round including the failed ones, because the failures are the expected intermediate state between a dossier edit and its review, and a table showing only the clean rows would overstate the archive.

The reviewer can close the loop itself this round: read `scripts/o0_verify_binding.py` and `scripts/o0_make_go.py`, then require as a condition of the verdict that the fresh round reports `O0_BYTES_BOUND_MECHANICALLY`, with zero failures, created after this file's mtime, carrying this file's sha256 and byte count, archived, and equal to the receipt and the verdict hash. Every one of those checks is enforced in `o0_make_go.py` before a GO can exist, so the condition is mechanical rather than rhetorical.

## 0b. The aborted first attempt (O0-B01), disclosed rather than deleted

The first real batch did run, for one charged start, and then stopped on a code defect in the Lead's own orchestration. It is reported here in full because a reviewer comparing this dossier against the earlier request would otherwise be reviewing a protocol that has never touched the solver, and that would be false.

- `o0_batch_abort_B01.json` (sha256 `0445d41401ff913c30806d57de5651b56740c2eba55b450385ff80726f1bac07`, basis BATCH_LOCAL): outcome `ABORTED_BY_CODE_DEFECT_AFTER_ONE_CHARGED_START`; this batch charged 1 solver start(s), 7 internal alpha case(s) and 1 design evaluation(s); admitted labels 0; recorded exception `AttributeError: 'str' object has no attribute 'get'`.
- `o0_batch_crash_B02.json` (sha256 `e24b747ee2afc8ae0a778e511f4a7bf1f4c2a56a1ef142d950e2d8b7f964c484`, basis AUTHORIZATION_CUMULATIVE): outcome `run would exceed 12 design attempts`; its ledger counts the whole authorization, i.e. 23 solver starts, 227 internal alpha cases and 12 design attempts including everything carried forward from the record above, so it is read as a running total and never added to the batch-local record; recorded exception `run would exceed 12 design attempts`.

**What went wrong.** `solver_runner.run_case()` reports the case result as the path of `case_result.json`, not as an inline object. The evaluator consumed that path as if it were a dict, so the coarse bracket parse raised `AttributeError: 'str' object has no attribute 'get'` after the solver had already solved. Two fixes follow from that, and both change code under review:

1. `o0_eval.bracket_rows()` now loads the JSON when the field is a path and keeps the inline-dict branch for callers that pass one. The real polar that was already paid for was then replayed through the fixed path with zero new starts: the seven rows reproduce the root alpha at 5.18132 deg with a quadratic fit R^2 of 0.999988 over a slope of 0.034384 per degree, which confirms the coarse bracket was usable and that only the parse was broken.
2. `o0_short_bo.evaluate_and_settle()` wraps every evaluator call so that an exception still settles whatever the evaluator already declared it spent before the error propagates. A start that has been paid for can no longer vanish from the counters just because the surrounding code raised.

**What the aborted start cost, and exactly how much of a design it was.** The crash happened between the two stages of design 0, so only the coarse stage was ever paid for: one solver start and seven internal alpha cases (the seven-point bracket). The thirteen-point refinement stage never ran and its second start was never issued. A complete design costs two starts and twenty internal cases, which is why this carry-forward reads one of twenty rather than two of twenty: the design is a third paid for, not half.

**The budget arithmetic, written out so it cannot be read two ways.** Each design costs exactly 2 starts and exactly 20 internal cases, and the design cap is 12. Therefore the most this authorization can ever spend is 12 x 2 = 24 starts and 12 x 20 = 240 internal cases. The two stored ceilings behave differently, and both statements are checked rather than assumed: the 36-start ceiling is strictly inert because 24 < 36, so the design cap binds first and those extra starts can never be reached; the 240-internal ceiling is not inert, it coincides exactly with the design cap (240 = 240), so the two bind together and cross-check each other instead of one being slack. Quoting 36 starts as if it were usable budget was the mistake in the previous round, and it is not repeated here.

Carry-forward, closed against the design cap so no reader has to guess: 0 of 12 design attempts remain, because all 12 are spent and the last one was closed by the batch record in section 4b. 1 of 24 spendable starts and 13 of 240 spendable internal cases also remain unspent, but they are stranded rather than available: a start cannot be spent without a design to spend it on, and none may be proposed. The two caps therefore still agree with each other, and the residue is stated here instead of being offered as spare budget.

**No label was manufactured out of it.** The aborted design has no admitted raw row. Two different gaps are in play and they should not be conflated: the coarse grid moves alpha in 0.35 deg steps, which at the measured 0.0328-0.0338 CL/deg slope is about 0.012 CL between neighbouring rows, roughly an order of magnitude coarser than the 1e-3 lift tolerance in CL, and about 330 times the tolerance when the same gap is expressed in alpha. Interpolation can bridge the CL gap to any accuracy one likes, but it does not create a row, so nothing was promoted and the design carries no label. The refine stage exists to turn that bridged alpha into an actual sampled row inside tolerance, and it never ran.

**Why this is a protocol question for the reviewer, not just an incident report.** The reviewer is asked to decide whether this record is fit to stand as the account of what was spent, after (a) the parse defect is fixed, (b) exception-path settlement is enforced in code, and (c) the charged start is carried forward instead of reset. If the reviewer judges that a fixed defect plus a carried-forward charge is not enough, the correct verdict is CHANGES_REQUIRED, and neither the optimizer GO nor the O0-FINAL GO will be issued; both writers refuse to issue one without a PASS on these exact bytes.

**Review ordering, stated because it is easy to misread as a missing artifact.** At the moment this dossier is reviewed there is deliberately no GO record and no A5 verdict for this batch: `o0_make_go.py` refuses to write a GO unless a PASS verdict already exists and binds to these exact bytes, so a GO cannot precede the review that authorizes it. A missing o0_go_record.json is therefore the correct pre-review state, and its absence is checkable, not an omission. The dossier asks for fitness to be authorized; it does not assert that authorization happened.

**The binding is also mechanically checked by a tool, not only described here.** `scripts/o0_verify_binding.py` (sha256 `18dbd947a5747fc544dc79415d160309db3aaa5b5d57e1a2df4c6b8085d50664`) recomputes every hash in this chain from the files on disk and fails if any of them disagrees: dossier bytes, receipt record, preregistration bytes, all code SHAs, the verdict and the GO when they exist. It writes `o0_binding_verification.json`. A reviewer who suspects the binding is merely asserted can ask for that file, or re-run those commands directly; nothing in the chain needs the reviewer to trust a number printed in this document.

H0 gate canonical hash: `1036ee10316dd834296712e33c7b6c3219a34727d90909324aa727dc69d3043c`. Geometry contract: `08c1341bdab944dd2a6e20985553e8eafc1d35ce50105a022c0a816da018f35b`.

## 0c. Executed evidence that the two fixes are in the frozen code

The previous review said, correctly, that section 0b described two fixes but showed no execution under the listed code SHAs. This section is that execution, produced offline with zero solver starts by `scripts/o0_fix_evidence.py`.

Evidence file: `a5_support/fix_evidence/fix_evidence.json` (sha256 `24ae998b72e6a316f1d4b06cdb1a7320e3b3a6c52311fef158d4030907e9f99b`, 3502 bytes).

| artifact | sha256 | bytes |
| --- | --- | --- |
| `bracket_rows_excerpt` | `4947172cdeb779fb66a327197de24d25c627a5209ec2dd3400d08e42307e2668` | 887 |
| `evaluate_and_settle_excerpt` | `31a92b54eb4dbea26eadaf5da8ed4ed5120909c598e5eb9d24806de61fee23a0` | 1584 |

- `pytest research/concorde_metaopt/tests/test_recovery_o0_short_bo.py -q` -> exit 0, `18 passed, 1 warning in 2.45s` (log sha256 `5a76665e3ada012d81e09859d438d2a6040bc689000078bc0e5b59a519e68a5b`). That file contains the two regression tests for the exception-path settle and the over-declared-charge case.
- `pytest research/concorde_metaopt/tests/test_recovery_ledger.py -q` -> exit 0, `20 passed, 1 warning in 3.10s` (log sha256 `192e1fed3fc7e5934c7922d03cac3a4af39f3e861b4806f6f4e437c7b7205537`).
- Replay of the paid B01 polar through the fixed parse path -> exit 0, 7 rows, method `QUADRATIC_BRACKET`, root alpha 5.18132 deg, quadratic R^2 0.999988 on 7 points, refine window 5.15732 to 5.20532 deg. This is real solver output that was already charged, read back with zero new starts; it exercises exactly the code path that raised on B01.

## 1. Exact code SHAs under review

| path | sha256 | bytes |
| --- | --- | --- |
| `research/concorde_metaopt/dreal001/geometry/h0_contract.py` | `6ff0c486aeba7ca10c4d6821cba22e730a4f3988f2fdb541086c1ecd1c644396` | 16643 |
| `research/concorde_metaopt/dreal001/ops/o0_short_bo.py` | `4be7182e278e638c21c4a9cf5862b499d0f71c0f7081d5815b5e04c33b3eba68` | 35481 |
| `research/concorde_metaopt/dreal001/ops/resource_monitor.py` | `e3cfdafc2ef9f3e92c5006ee1b00e32d68b758374429b23d3a3e28d7f63739b9` | 15259 |
| `research/concorde_metaopt/dreal001/optimizers/recovery_bo.py` | `8328a90ded506564ce454804efa4c89d7ae5d8024784fd2b34cd8c02557eb929` | 8238 |
| `research/concorde_metaopt/dreal001/geometry/solver_runner.py` | `cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3` | 42284 |
| `research/concorde_metaopt/dreal001/geometry/openvsp_model.py` | `9e6797901564f48435974c5dad66faa063d4c3602e07f643bd2d540b79939dc8` | 38907 |
| `research/concorde_metaopt/dreal001/geometry/design_identity.py` | `63d3f1a96150785b2ebf21eca5a41447d3fdde7f77f99ed209f3500355a3e409` | 1565 |
| `research/concorde_metaopt/dreal001/geometry/task_spec.py` | `100d2f265880b07ba679883e744fc13634d4502cee8206604dc491ab2346ec3f` | 16361 |
| `research/concorde_metaopt/dreal001/meta/real_admission.py` | `4322554ea488dd583a9c06fc8bb611e0584360573287673fe46bbbcc605ee3fc` | 18286 |
| `research/concorde_metaopt/dreal001/meta/raw_verification.py` | `36016cb57d28a018b2b2f1e5cbc532ab686552f0204ab3bef1316cea0d87322a` | 9314 |
| `research/concorde_metaopt/dreal001/meta/task_spec.py` | `5413a1e8c1b6c71bb2af3093abfb1102eb2191e8781a5afcf5fbbe5ff5810ca5` | 4052 |
| `research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml` | `ebca2b7bb2920ce1e3729a3dedd7c361a1c78d34337918a973866bef48f76efc` | 11099 |
| `scripts/o0_eval.py` | `825e90a0e2aa8b75d95789333b5deb79f9ad5ce1ae4de7af936d6e286904746c` | 18790 |
| `scripts/o0_admit_case.py` | `d79be02ec4494a3937126f88cf9040b9c77067b6c1b26780715ecde605f316b8` | 7463 |
| `scripts/o0_prereg.py` | `7699a09dc52bb70127888380defc1ddef2f198bb762987f45ba7a6ba23d01557` | 27033 |
| `scripts/o0_run.py` | `10bfdf4a632d22b9f821a5aaa1ba91948ed2691ef2dffa53d13cc369beadb72c` | 18513 |
| `scripts/o0_final.py` | `273685dd2d6c3e944bdeed984c97ad755809a3914dd1c7e400325cbdbbc10dd0` | 34624 |
| `scripts/o0_fix_evidence.py` | `0cf149f3e2f00051be7def24edd2aa8a6893c954655c67dd5b105dc0535ee851` | 6902 |
| `scripts/o0_make_go.py` | `8bcef437dee0c6e3a05b04d6575b6c16bdc743992e662a9c57ea994dc6510df4` | 13793 |
| `scripts/o0_verify_binding.py` | `18dbd947a5747fc544dc79415d160309db3aaa5b5d57e1a2df4c6b8085d50664` | 7426 |
| `scripts/o0_build_dossier.py` | `51c10a26758b69fd2a27af250414f6840a57fdadabda74e74c41148d937bcbb4` | 84969 |
| `scripts/o0_a5_review_tools.py` | `d75661db5cdf9dcd47fa5dd93761b201cde15331ec8f810a3bfe190b2d3057d3` | 25358 |
| `scripts/o0_probe_production_loader.py` | `d716142bad3dbf6b850a3ed3c08ec499f681fd40a9f8f83a60ff4a6cd4cda80c` | 2281 |
| `scripts/o0_make_final_go.py` | `05b2673f569c3bf5efe8c9176e282a309e0bf7cdf94498298d44e2d59d5068f0` | 23058 |
| `scripts/o0_spend.py` | `e16bd95cd131daba43bd89ff078261fc220b51faaddb4b08b65838d508aa60c6` | 6730 |
| `scripts/o0_retire_stale_go.py` | `6965cbd5403af34b0731df8f6ca72037bfe3c62db95f50b97f6948c5d8cacea0` | 2633 |
| `scripts/o0_retire_stale_final_go.py` | `ac034ad94beb0855447c68807a590a5271b1d5c99c3e310cbdaabfbb7c677374` | 6309 |
| `scripts/o0_repair_ledger.py` | `7b6bb9ad23516dab54494ac20599483a1e91e69fc2a925178f04e843e908385e` | 10237 |
| `scripts/o0_final_selftest.py` | `28194aa51ee34df55c6f0235817b1c41c7631ec892c09cbfc18b423f331099ca` | 8337 |
| `D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py` | `5c07a4865f37d434961f99b9862fea7ea1e8b4a238db8b1cd79aba4c339a842c` | 5378 |

These are the only files that will execute in the O0 batch. Everything else is read-only data. If any of them changes, this review is void.

**Where each path actually lives, so a reviewer with tools can hash it.** Paths of the form `scripts/o0_*.py` resolve against the run root `D:\RCAIDE\.real_runs\DRECOVER001-O0-20261124-01`, NOT against the frozen worktree; the worktree has its own `scripts/` directory with unrelated files in it. Repository paths such as `research/concorde_metaopt/...` resolve against the frozen worktree `D:\RCAIDE\.worktrees\dreal005-20261124`. The external audit script is listed by absolute path because it lives in a third root. The table above prints the bare path only because that is the key the pre-registration stores; this paragraph is the mapping.

## 2. H0 gate: frozen geometry contract and the design-space conflict

- Frozen 12 variables in order: `wing_area`, `aspect_ratio`, `sweep_1`, `sweep_2`, `sweep_3`, `span_location_2`, `span_location_3`, `chord_ratio_2`, `chord_ratio_3`, `tip_twist`, `vertical_tail_area`, `vertical_tail_sweep_delta`.
- Fixed fuselage variables: `fuselage_length`=61.66, `fuselage_fineness`=4.3, `fuselage_height_width_ratio`=1.152778.
- Baseline 12D vector: `[358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284, 0.130178, 0.0, 33.91, 0.0]`.
- Baseline design id: `8bd5a6c7c8311938`.

**Recorded conflict, not silently fixed.** `research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml` declares stage P1 with frozen true; design_space._validate_space raises for any frozen space, so load_design_space() cannot load the 12D YAML from the production path. The lead did NOT flip frozen to false and did NOT touch main. The H0 contract file is the executable frozen copy and the optimizer builds geometry with build_geometry() directly, bypassing only that guard.

Production loader probe on the untouched YAML, archived at `audits/production_loader_probe.json` (sha256 d4c8a97cdcaf456bad142d5a39584aec6248d8c0d5bcc512dea5dd464c016307, 866 bytes): loaded=False, exception_type=DesignSpaceError, physical solver starts 0.

    D:\RCAIDE\.worktrees\dreal005-20261124\research\concorde_metaopt\configs\design_space_12d_lifting_surfaces.yaml: the P1 design space is provisional and must not be loaded as frozen before the geometry perturbation checks are complete

Active-mask evidence from the measured 12D CDi response audit on existing raw rows: max|dCDi| sweep_1 1.707e-3, sweep_2 6.977e-4, wing_area 1.45e-10, vertical_tail_area 0.0, fuselage_length 0.0. Nine of twelve variables show no measurable CDi response on those samples, so this batch optimizes only the sweep_1/sweep_2 local box. The dossier does not claim the other ten variables are physically irrelevant; it claims this batch does not spend starts to find out.

**Stated limit of that evidence: the response audit rests on N=8 historical M202 rows**, roughly one perturbed design per variable, so a small CDi effect on a variable could hide inside the row-to-row spread. That is precisely why the search space here is a local 2D box around the frozen baseline, and why an O0 result will be reported as a local improvement at fixed lift, never as a statement about the full 12D design space.

## 3. A0 ablation: what was actually trained

- scope `REAL_META_TRAINING_EXECUTED`; training scope `ACTUAL_GRADIENT_TRAINING_ON_REPLAYED_REAL_LABELS`.
- physical starts 0; internal alpha cases 0; admitted labels 44; physics_validated False; fuel_burn_kg None.
- Arms: `RANDOM_INIT`, `POOLED_PRETRAIN_12D`, `COND_SUPERVISED_16D`, `FOMAML_12D`, `COND_FOMAML_16D`.
- COND_SUPERVISED_16D is a plain supervised MSE regressor on 16 inputs (12 normalised design coordinates plus 4 known task conditions). It never calls meta_train_step and its recorded inner_gradient_updates is 0. That is the specific P2 defect Issue #15 asked to fix.
- COND_FOMAML_16D is the same network under a first-order MAML outer loop. The primary mechanism comparison is COND_FOMAML_16D minus COND_SUPERVISED_16D at equal K and equal seed.
- Checkpoint selection is unified: every trained arm reports the step with minimum validation MAE at validation K=1, so no arm is advantaged by picking last vs best.
- Mean test MAE by arm and K (n = 2 test tasks x 3 seeds), newtons:

| arm | K=0 | K=1 | K=3 |
| --- | --- | --- | --- |
| `RANDOM_INIT` | 54372.2 | 22117.6 | 34900.729 |
| `POOLED_PRETRAIN_12D` | 53450.7 | 17289.9 | 33095.624 |
| `COND_SUPERVISED_16D` | 21519.1 | 8091.2 | 12163.677 |
| `FOMAML_12D` | 61066.8 | 20493.6 | 36843.606 |
| `COND_FOMAML_16D` | 25065.0 | 7054.5 | 6975.043 |

Core pair mean test delta (COND_FOMAML_16D minus COND_SUPERVISED_16D): **-893.1 N**.

Reading rule stated up front: the large effect is the 4D condition vector, not the meta objective. The meta objective helps slightly at K=1 and K=3 and is worse at K=0. Predicting Di_N in newtons is not a claim about sampling speed.

Cost actually spent (offline training, host-wide sampling): wall 24.9 s, CPU busy mean 0.158, memory load mean 42.96%, peak tracked working set 204.9 MB.

### 3b. Paired dispersion for the core pair, and what it does NOT show

The core pair is paired cell by cell (same task, same seed, same K): 18 test cells and 18 validation cells.

| split | mean delta (N) | sd | 95% bootstrap CI of the mean | FOMAML better | supervised better | sign-test p |
| --- | --- | --- | --- | --- | --- | --- |
| test | -893.1 | 13876.8 | [-7111.5, 5289.6] | 8 | 10 | 0.815 |
| val | 9416.0 | 13719.1 | [3891.7, 16128.3] | 4 | 14 | 0.031 |

**Read this honestly: the meta objective is not established by A0.** On the test split the -893 N point estimate has a 95 percent interval that straddles zero, and FOMAML wins 8 of 18 paired cells against 10 losses. On validation the same comparison is significantly *worse* for FOMAML. The defensible conclusion is that the 4D condition vector is the large, reproducible effect and that a first-order meta objective makes no measurable difference at K<=3 on this data volume. O0 is therefore not premised on the meta learner being better; it is premised on the conditional model being usable inside a real feedback loop.

### 3c. Alpha resolution measured from the raw polars, across all real runs

The reviewer objected that the replay evidence was circular and rested on one run. These numbers are recomputed differently: every readable M202 polar in every real run root is read (5 roots searched), cases are grouped by their 12D design vector so a re-run of the same design counts once, the widest-span polar per design is used, and a quadratic CL(alpha) fit locates the fixed-lift root. 7 unique designs yielded a locatable root; 0 further design(s) were kept out because their root lies outside the measured alpha span, and they are listed rather than extrapolated.

| quantity | value |
| --- | --- |
| CL slope at the target | 0.03279 to 0.03385 per deg |
| alpha half-width of the 1e-3 lift tolerance | 0.0053 to 0.0055 deg |
| refinement step | 0.004 deg |
| raw rows guaranteed inside the tolerance window | at least 3 |
| refinement half-width (0.024 deg) in CL units | 0.000787 |
| refinement half-width vs the tolerance window | 4.37x |
| largest measured root offset from the coarse centre | 0.2445 deg |
| coarse bracket half-width | 1.05 deg |
| coarse coverage margin over the worst measured root | 0.8055 deg |
| measured sweep_1 -> fixed-lift alpha coupling | 0.1574 deg per deg |

Per-design measurements (all rows are real VSPAERO polars):

| design id | differs from baseline in | area, sweep_1, sweep_2 | source run | alpha span | root alpha | CL slope |
| --- | --- | --- | --- | --- | --- | --- |
| `518b3a2b` | `wing_area` | 361.8325 m2, 67.0, 48.0 | `DRECOVER001-G2-20261121-01` | -1.76 to 9.76 deg | 5.2035 deg | 0.03385 |
| `cc5a9896` | `sweep_1` | 358.2500 m2, 67.5, 48.0 | `DRECOVER001-G2-20261121-01` | -1.76 to 9.76 deg | 5.4245 deg | 0.03279 |
| `2c5b06aa` | nothing (this is the frozen baseline) | 358.2500 m2, 67.0, 48.0 | `DRECOVER001-G2-20261121-01` | -1.76 to 9.76 deg | 5.2567 deg | 0.03384 |
| `43ac9deb` | `wing_area` | 354.6675 m2, 67.0, 48.0 | `DRECOVER001-G2-20261121-01` | -1.76 to 9.76 deg | 5.3110 deg | 0.03383 |
| `3da7999e` | `sweep_1` | 358.2500 m2, 66.5, 48.0 | `DRECOVER001-G2-20261121-01` | -1.76 to 9.76 deg | 5.2671 deg | 0.03377 |
| `fc1791b6` | `vertical_tail_area` | 358.2500 m2, 67.0, 48.0 | `DRECOVER001-G2-20261121-01` | -1.76 to 9.76 deg | 5.2567 deg | 0.03384 |
| `844de3a1` | `sweep_2` | 358.2500 m2, 67.0, 48.5 | `DRECOVER001-G2-20261121-01` | -1.76 to 9.76 deg | 5.2646 deg | 0.03379 |

What that buys, stated as a margin rather than a hope: the 1e-3 tolerance is about 0.005 deg of alpha wide, the refinement step is 0.004 deg, so any design whose true root lies within the 0.024 deg refinement window has at least 3 raw rows inside tolerance. The refinement half-width is 4.37x the tolerance window, which is the estimator margin, and the coarse bracket covers every measured root with 0.81 deg to spare.

**The residual risk is named, not hidden, and the evidence limit is stated.** This is 7 unique designs from the historical M202 sweep family, not a sample over the O0 subspace: it supports the tolerance-window geometry (a 1e-3 lift tolerance really is about 0.005 deg of alpha, so a 0.004 deg step cannot miss the window when the coarse fit lands inside 0.024 deg), and it does not prove that a novel subspace design's root always lands inside the 2.1 deg bracket. If a design's root falls outside the 0.024 deg refinement window it records objective=None and still pays both starts, which is the failure mode the ledger charges and the tables report. 7 skipped case(s) are listed with reasons in the support file rather than quietly dropped.

Support statistics file: `a5_support/o0_a5_support_stats.json` (sha256 3c78abbd341a4d3940c594d7c619fe36db310f166354d9314462ccd1ff3f6a40, 12376 bytes), produced offline with zero solver starts, and re-runnable by anyone holding the raw runs.

**The quantitative version of the alpha argument, so it does not rest on prose.** The coarse bracket is a plus minus 1.05 deg window around the baseline alpha 5.18 deg. The search box is plus minus 1.5 deg in sweep_1 and plus minus 1.5 deg in sweep_2, both smaller than the plus minus 1.05 deg bracket that the historical polars span. The measured sweep_1 to fixed-lift alpha coupling is 0.1574 deg per deg, so moving sweep_1 across its whole +-1.5 deg box moves the fixed-lift alpha by at most about 0.24 deg, which is 4.4x smaller than the bracket half-width. That is why the 7-row coarse quadratic is expected to land inside the 0.024 deg refinement window even for a design the historical data has never seen.

## 3d. The two open majors from the previous round, answered here

**Major 1, byte binding.** The reviewer now holds read-only tools, so it measures this file's hash itself instead of accepting one, and the harness measures the same bytes and records both values in the verdict. The remaining gap is ordering, not trust: the verifier round that binds these bytes can only run after they exist, so section 8 quotes an earlier round and states plainly that it read an earlier dossier. `o0_make_go.py` now refuses a GO unless a fresh round exists that reports `O0_BYTES_BOUND_MECHANICALLY` with zero failures, was created after this file's mtime, recorded this file's sha256 and byte count, is archived under `a5_support/binding_history/`, and agrees with the receipt and the verdict. That is a code path, not a promise, so the correct action is to require the fresh round rather than to accept prose.

**Major 2, how strong is the alpha margin.** The previous round was judged on 3 readable polars. This round the statistic is rebuilt over every real run root (R2, G1, G2, P1, P2): 5 roots searched, 7 unique 12D designs with a locatable root, 0 design(s) excluded because the root lies outside the measured alpha span and listed rather than extrapolated, 7 case(s) skipped with a recorded reason. The tolerance-window geometry (a 1e-3 lift tolerance is about 0.0052 deg of alpha, so a 0.004 deg step puts at least 3 real rows inside it) and the coupling bound above are what the protocol relies on; both are recomputed from raw polars and both are reproducible offline. The honest limit stays stated: 7 designs from one M202 family is not a sample over the O0 subspace, and a design whose root misses the 0.024 deg window records objective=None while still paying its 2 starts.

## 4. O0: the real feedback optimization protocol

- Task `O0-M202` at Mach 2.02, altitude 18288 m, L_ref 1333704.4 N, tolerance 1e-03; objective Di_N = q*Sref*CDi of an admitted raw polar row.
- Free variables `sweep_1` and `sweep_2` inside `{"sweep_1": [65.5, 68.5], "sweep_2": [46.5, 49.5]}`. Every other variable is held at its frozen baseline; check_design() raises if anything else moves.
- Bootstrap: LHS on the frozen box, baseline forced first.
- Adaptive backend `RECOVERY_NUMPY_RBF_GP_EI_V1`, max 8 adaptive attempts.
- One design evaluation costs exactly 2 charged starts: 7-point coarse bracket around 5.18 deg (spans 2.1 deg), then 13-point refinement centred on the coarse quadratic CL(alpha) root, plus minus 0.024 deg at 0.004 deg resolution.
- Internal alpha cases per design: exactly 20 (7 coarse + 13 refine), equal to the 20 cap rather than merely under it.
- Caps as stored in the code: `{"bootstrap_attempts": 4, "max_adaptive_attempts": 8, "max_consecutive_unadmitted_designs": 3, "max_design_attempts": 12, "max_internal_cases": 240, "max_internal_per_design": 20, "max_solver_starts": 36, "max_starts_per_design": 2, "parallelism": 1, "retries": 0, "solver_timeout_s": 600, "wall_clock_s": 3300}`.
- How those caps interact, stated once: the design cap (12) times the exact per-design cost (2 starts, 20 internal cases) gives a spendable ceiling of 24 starts and 240 internal cases. The stored 36-start cap is strictly inert (24 < 36), so it is not budget and is never quoted as remaining budget. The stored 240-internal cap is not inert: it equals the spendable ceiling exactly (240 = 240), so the design cap and the internal cap bind together and confirm each other. No number in this list is a remainder; remainders appear only in the carry-forward paragraph below.
- After the carry-forward: 23 start and 227 internal cases already paid for, so at most 0 further designs, 1 further starts and 13 further internal cases remain. Every number in this document is a spendable total unless the sentence says "further".
- The optimizer cap is now exhausted: no further design may be proposed under this authorization, so the optimizer batch cannot run again even though a residual 1 start and 13 internal case are arithmetically unspent (a start cannot be spent without a design to spend it on). The only physics still asked for is the separate O0-FINAL verification budget in section 4b.

**Per-design cost is an exact invariant, not an upper bound.** `o0_short_bo.assert_execution_contract()` asserts that max_starts_per_design equals 2 and that the alpha plan agrees, and AttemptLedger.charge() rejects any charge that would take one design past 2 starts or 20 internal cases, so a third start on the same design is architecturally impossible rather than merely discouraged. An earlier revision carried the generic Issue-#15 wording of 3 starts per design while the evaluator spends exactly 2; that inconsistency is fixed at the cap, not by loosening the evaluator.

**What the attempt numbers count.** max_design_attempts=12, bootstrap_attempts=4 and max_adaptive_attempts=8 all count distinct designs. None of them authorizes solving one design twice: bootstrap designs are LHS with duplicates rejected, and the GP backend refuses a duplicate observation, so re-evaluating a design already in the table raises instead of consuming budget. A repeat would also cost 2 new starts, which the per-design cap forbids.

**Serial and retry-free by assertion.** parallelism=1 and retries=0 are enforced values inside that same assertion, not prose in this document: any other value raises ProtocolError before the first start, and the runner calls the assertion before it validates the GO record.

**Why the coarse bracket is 2.1 deg wide.** The fixed-lift alpha moves about 0.16 deg per degree of sweep_1 on the measured M202 polars (section 3c), so across the +-1.5 deg search box the target can move by at most about 0.24 deg; a plus minus 1.05 deg bracket around the baseline alpha keeps every measured root inside with 0.81 deg of margin. A coarse quadratic fit on 7 rows across 2.1 deg then predicts the root inside the 0.024 deg refinement window, which at 0.004 deg resolution puts at least 3 raw rows inside the 1e-3 lift tolerance.

**Tolerance is not relaxed and no interpolation is promoted.** A design whose refined polar contains no actual row inside 1e-3 is recorded as a failure with objective=None; it still pays both starts and all 20 internal cases.

**A missed refinement window cannot silently eat the whole budget.** A design that misses the refinement window still pays its 2 starts, so 12 such designs could spend 24 starts, zero of them useful, with zero admitted rows. The stop rule is code, not prose: `CAPS["max_consecutive_unadmitted_designs"]` = 3, and run_bo_loop() counts any design that ends with objective=None and breaks out with budget deliberately unspent once 3 consecutive designs have failed to admit a raw row. That is 6 charged starts -- 3 designs times the exact 2 starts per design -- plus an explicit `stopped_by_unadmitted_streak` reason in the result, not 12 misses. assert_execution_contract() refuses a value that would not bite before the design cap.

Stop conditions: the baseline design (bootstrap design 0) fails: the batch aborts at once and the remaining budget is not spent, because a baseline failure means the protocol rather than the aerodynamics is broken; 3 consecutive designs with no admitted raw row (added this round, and it is the answer to the budget-drain objection); any spendable limit reached, which after the final batch means 0 further designs, 1 further starts or 13 further internal cases (the stored 36-start ceiling is unreachable and the stored 240-internal ceiling is the same number as the design-derived one); two consecutive designs with no solver result at all; wall clock 3300 s; any accounting inconsistency (ledger charge rejected); upload and remote readback after every 8 starts or 60 minutes, before continuing.

## 4b. The O0-FINAL verification step: a separate budget, and a separate review

The optimizer batch is not the end of the work. The improvement it reports still has to survive being measured again by a procedure that cannot choose what to measure. That is the O0-FINAL step, and it is the one place where a reader could reasonably suspect that the budget is being quietly extended, so it is written out here with its arithmetic instead of being left to the summary line.

- **What is re-measured.** Exactly two designs: the frozen baseline, and the admitted non-baseline design with the lowest Di_N in the closed batch. Both are re-solved from scratch with new case ids in fresh empty directories, in the same frozen configuration, 2 times each. The improvement is then the difference between two independently measured pairs rather than one optimistic number.
- **Pre-registered budget.** These numbers are already frozen in `o0_preregistration.json` under `o0_final.separate_budget` before a single verification start is spent: 8 verification starts, 104 internal alpha cases, at most 2 repeat runs per design, 2 wake probes, wake nodes 8 for the reference mesh against 16 for the probe, and 13 refinement points per case.
- **Itemization, so the total cannot be taken on faith.** The budget is gross: it covers the three starts the crashed first attempt already spent as well as the five that remain. 2 void rows x 13 refinement points = 26 internal cases (already spent, never admissible, never re-run), plus 2 wake probes x 13 = 26 internal cases (one of which, the baseline probe, is already spent and complete on disk), plus 4 repeat runs x 13 = 52 internal cases still to spend. That is 26 + 26 + 52 = 104 internal cases and 2 + 2 + 4 = 8 starts, of which 3 starts / 39 internal cases are already spent and 5 starts / 65 internal cases remain. The runner does not trust these numbers: it reads them from the pre-registration and exits with BUDGET_NOT_PRE_REGISTERED if a key is missing or with BUDGET_MISMATCH if a value disagrees with its own code.
- **Why this is not extra optimizer budget.** Verification cannot propose a design and cannot admit one. It re-measures two designs that were already selected and already paid for, and the wake probe is never admitted at all, because the admission mesh is fixed at 8 wake nodes and the probe is deliberately solved on 16. The optimizer caps are spent and stay spent; nothing here can spend them again.
- **Why it needs its own review and its own GO.** `o0_preregistration.json` records `requires_its_own_a5_review: true` and `requires_its_own_go: true`; the GO file is `o0_final_go_record.json` with authorization kind `O0_FINAL_VERIFICATION`; and `scripts/o0_final.py` refuses to move without it. That gate checks the verdict, the dossier hash, the pre-registration hash, a fresh mechanical binding round, the eight pre-registered budget numbers one by one, the verification ledger that shows what the crashed first attempt already spent, and the two design identities it is allowed to re-measure. A verdict on the optimizer protocol is therefore not a verdict on this step, which is why section 7 asks for both.
- **What counts as a start, and what does not.** A case directory is not a start. `scripts/o0_eval.py` creates a case directory with `plan.json`, `approval.json`, `task_spec.json`, the geometry files and the case inputs before anything is solved, so a directory can exist while zero solver starts have happened. A start is counted only when there is a `.polar` file and a `case_result.json` with `physical_solver_starts = 1`, or when the ledger charges it before the spawn. The directories under `cases/O0F/` that hold preparation files and no polar are therefore preflight output, not spend; `scripts/_preflight_inventory.py` prints the file count, the byte count and the polar count of each one so the distinction is checkable rather than asserted.
- **Why the ledger is a file and not a counter in memory.** `o0_final/verification_ledger.json` is read back when the runner starts and written after every charge, so a crash between two starts cannot zero the bill, and a label that has already been charged cannot be charged a second time, so a re-run cannot be smuggled in as a fresh case.

### 4c. The first attempt at this step crashed, and what that cost

This is disclosed here because a verification budget that grew from six starts to eight without the crash being stated, and without the three starts it cost being charged, would be exactly the kind of thing this dossier exists to make impossible to hide. The growth is therefore stated with its cause, its cost and its evidence.

- **What happened.** The first attempt died on its third start with `wake probe cap exceeded: 2 rows`. The two rows it had already charged were the baseline repeats, and they had been charged as `kind=wake` because the runner derived the kind from the wake count and gave every repeat two wake nodes instead of the admission mesh of eight. With `max_wake_probe_starts = 2`, the third charge was refused while the third solver run was already running.
- **What it actually cost.** Three real solver starts and 39 internal alpha cases: two baseline repeats at two wake nodes, plus one baseline probe at sixteen wake nodes that completed with its polar and `case_result.json` still on the disk. The two wake-node-two cases are void: their polar output is real, but the mesh is not the admitted mesh, so they can never be admitted and they must never be re-run under those labels.
- **What was wrong with the ledger, and not just with the code.** The ledger recorded two starts and 26 internal cases, both mislabelled, and it was missing the third start entirely, because the charge happened after the run instead of before it. A crash therefore destroyed a paid start rather than billing it. The repair is in the ordering, not in the arithmetic: the charge is now made before the solver is spawned, a crash after a charge writes a record beside the ledger, and the kind is a plan field that is never inferred from a number.
- **How the ledger was repaired.** `scripts/o0_repair_ledger.py` re-reads the three case directories, checks the sha256 of each polar and each `case_result.json`, and rewrites the ledger with three rows carrying that evidence: two `void` rows for the mis-configured repeats and one `wake` row for the completed probe. The pre-repair ledger is preserved inside the repaired file under `repair`, including its own sha256, so the correction is auditable rather than invisible.
- **What the repair does not do.** It does not re-classify a paid start as unspent, it does not re-run any case that already produced paid output, it does not spend a start, and it does not widen an optimizer cap. The five remaining starts and 65 remaining internal cases are what a GO can authorize; the runner reads the ledger back and the cap arithmetic happens there, not in this paragraph.
- **Why this is inside the owner's limit.** The owner's acceptance note allows a first verification batch of at most twelve real solver starts. The gross verification spend here is 8 starts, and the three already spent are disclosed rather than recycled, so the replacement batch stays well inside that limit without pretending the crash was free.

### 4d. The second attempt spent nothing, and that is stated too

A disclosure section that only reports the crashes that cost money would be a selection of the convenient ones, so the run that died for free is recorded as well.
- **What happened.** after the ledger repair and a fresh A5 PASS, the repaired run died on its first planned case with 'TypeError: object of type int has no len()' inside attempt_refine, before the charge and before the solver was spawned.
- **Root cause.** o0_eval.make_case() returns alpha_points as the count of alpha points, and the new pre-charge code read it as the list; the charge therefore threw while computing its own amount, which is the one way a pre-charge can still lose a start.
- **What it cost.** nothing: the failure happened before the charge was written and before any VSPAERO process was spawned. The ledger still reads 3 starts / 39 internal cases and every new case directory holds preparation files only, with no polar and no case_result.json.
- **How it is closed.** the planned cost is now computed by planned_internal_for(), which accepts either the count or the list and is tested without a solver; two further tests pin the wiring: the kind comes from the plan and never from a wake count, and repeat cases are planned at the reference wake mesh of 8.
- **How it is prevented from recurring.** o0_final_selftest.py covers the cost helper, the explicit kind wiring and the non-admissibility of wake rows; it runs 12 checks with zero solver starts.

- **The four verdicts are pre-registered strings and none of them is PASS:** `VERIFIED_IMPROVEMENT`, `FEASIBLE_NO_VERIFIED_IMPROVEMENT`, `PROVISIONAL_CANDIDATE`, `NO_FEASIBLE_NONBASELINE`.

**The optimizer batch this step would verify, already closed and disclosed.** Batch `DRECOVER001-O0-20261124-01-B02` closed with outcome `COMPLETED_BY_EXHAUSTING_THE_AUTHORIZATION_DESIGN_CAP`, and no cap was exceeded (`was_any_cap_exceeded=false`). The batch ended with an exception that reads like a crash and is not one: the adaptive loop asked for a 13th design after the 12-design cap was already fully spent, and the ledger refused, which is the ledger doing its job. The loop bound is fixed by subtracting the carried-forward designs; the fix changes code that is listed in section 1.

The measured improvement, before any verification: baseline Di_N 121437.61 N, best admitted non-baseline Di_N 121146.86 N, difference **290.75 N**, which is 0.2394% of the baseline. That is a small effect and it is reported as small. Whether it survives re-measurement is exactly what O0-FINAL is for, and it is why the verdict it can produce is one of four strings rather than a success flag.

Closure record: `o0_batch_close_B02.json` (sha256 `684db6bc56cecd30421a0672063534b7ccdfbc524308ffe963c2d20e96577629`, 3667 bytes).

## 5. Accounting and resource instrumentation

- `AttemptLedger.settle()` is the only writer of the run counters. It adopts what the evaluator reports and routes it through `charge()`, which raises if any per-design or per-run cap would be exceeded, so an over-spending evaluator fails closed instead of overspending.
- Six quantities are reported per batch: physical starts, internal alpha cases, charged starts, planned or reserved starts, design evaluations, cached reads.
- Batch spend and authorization spend are reported separately, and only the authorization total is comparable with the caps. The batch accounting file carries `carried_forward` with the records it was read from, so a restarted batch cannot be mistaken for a fresh authorization.
- **The carry-forward is counted once, by one rule, from one file.** `scripts/o0_spend.py` is the only place that decides this. An abort record reports batch-local numbers; a crash record's ledger summary is authorization-cumulative and already includes what it carried forward. Summing the two would print 24 starts for the 23 that were actually spent, so the module takes the newest cumulative record as the floor and only adds a batch-local record that the floor cannot already contain. The counting rule it applied is quoted verbatim in the receipt.
- **The failure mode that produced the abort in section 0b is now a settled charge, not a silent loss.** `AttemptLedger.settle()` runs even when the evaluator raises, and a charge that would breach a cap keeps the original exception while restoring the declared amounts into the abort record, so a crash preserves the bill instead of erasing it.
- CPU and memory are sampled during the optimization by the resource monitor: host-wide CPU busy fraction, physical memory load, and the tracked working set of the python and vspaero processes. It is pure `ctypes` because `psutil` is not installed, and a write failure is reported rather than raised, so monitoring cannot take the batch down.

## 6. What this dossier does NOT authorize

- No solver start before a separate A5 verdict on these exact bytes and a Lead GO record whose hashes match the files above.
- O1 warm-start arms are not authorized. They need their own pre-registration, their own review and their own GO.
- The O0-FINAL verification starts in section 4b are not authorized by the optimizer GO. They need their own verdict and their own `o0_final_go_record.json`.
- Lift tolerance, target lift, reference quantities and mesh standard are frozen. Changing any of them to manufacture an improvement is out of scope, and a row that is interpolated rather than sampled is never admitted.
- Earlier approval adapters are not used, and no old authorization id and no old GO record is reused. A GO is bound to one batch id and one set of bytes.
- No new design can be proposed after the optimizer caps are spent. The remaining physical budget in this issue is the O0-FINAL verification budget in section 4b and nothing else.
- `physics_validated` stays `false` and `fuel_burn_kg` stays `null`. This is a lifting-surface VSPAERO internal-only objective, not a mission-level result.

## 7. Requested verdict

**First, the optimizer batch that already ran.** No further optimizer batch is requested: the authorization's design cap is exhausted, so this section asks whether what already happened is properly stated. The binding limits were: at most 12 design attempts, exactly 2 solver starts and exactly 20 internal alpha cases per design, which means at most 24 starts and 240 internal cases could ever be spent because the design cap binds first; tolerance 1e-3 never relaxed and no interpolated row admitted; zero retries and parallelism 1 asserted by the same check rather than promised in prose.

Measured against those limits, the closed batch itself spent **11 designs, 22 starts and 220 internal cases**, of which 11 admitted raw rows and 0 failed or null; improvement of the best non-baseline design over the re-measured baseline is 290.8 N (0.239%). Both designs are re-measured independently in section 4b before any improvement is called verified.

Two different totals appear in this dossier on purpose, and neither is a typo. The **batch-local** spend of the closed optimizer batch is 11 designs / 22 starts / 220 internal cases. The **authorization-cumulative** spend is 12 designs / 23 starts / 227 internal cases, because the earlier batch that crashed (section 0b) had already charged 1 design / 1 start / 7 internal case before it died. The difference is exactly that aborted attempt: 1 design, 1 start and 7 internal case. Whenever this document says "paid so far" it means the cumulative number, because that is the number a reader needs in order to know what the authorization has actually cost.

The carry-forward, derived from the records on disk and not from prose: 23 start and 227 internal case(s) are already paid for out of 24 spendable starts and 240 spendable internal cases, against 12 design attempts out of 12. That leaves 1 further starts and 13 further internal cases arithmetically, but 0 further design attempts -- and a start or an internal case cannot be spent without a design to spend it on. The residue is stranded, not available: no optimizer spend remains, and the only physics still requested is the separate verification budget in section 4b.

This asks for a verdict on the executed protocol, its accounting and the carry-forward, not on a reset budget.

**Second, the O0-FINAL verification budget.** Decide whether the separate, pre-registered verification step in section 4b is fit to authorize its own 8 starts and 104 internal cases: the itemization above, the rule that picks the two designs, the requirement of a fresh binding round and a separate GO, the ledger that survives a crash, and the refusal to admit a wake probe. These starts are spent after the optimizer batch is closed; they cannot be folded into an optimizer cap, and the optimizer cap cannot be reopened to pay for them.

**What this dossier does not ask for.** It does not ask for a verdict on O1, on mission-level physics, or on any number that would require trusting a value this document states about itself.

## 8. How this document's own hash becomes checkable, in two rounds

A single file cannot state its own sha256. This section therefore anchors the binding in the archived output of the mechanical verifier and states exactly what the next round must produce, so a reviewer can require it as a condition instead of trusting prose.

Round N-1, archived and hashable at `o0_binding_verification_20261124T102133Z.json`:

~~~
verifier sha256    : ff9dc0556a6dd0792bafddb900cf3608610ffccab23b5a5980553da796035ca7
status             : O0_BYTES_BOUND_MECHANICALLY
check_count        : 10
failure_count      : 0
problems           : []
dossier it read    : 64b93d00df31bcf7b596ec6814439c66001595c600f3a1eeaa2ed36e21d806ec
dossier bytes      : 54419
archived at        : `D:\RCAIDE\.real_runs\DRECOVER001-O0-20261124-01\a5_support\binding_history\o0_binding_verification_20261124T102133Z.json`
~~~

That round reads an **earlier** dossier than the one you are reading. It proves the procedure is mechanical and has completed at least once; it does not prove anything about these bytes. The round that covers these bytes does not exist yet and is a hard precondition of the GO.

Round N, which the GO depends on, happens after these bytes exist: `scripts/o0_verify_binding.py` re-reads them off disk, hashes them, recomputes every other hash in the chain, and writes `o0_binding_verification.json` plus an immutable copy under `a5_support/binding_history/`. Both GO writers refuse to issue a GO unless that fresh round reports `O0_BYTES_BOUND_MECHANICALLY` with zero failures, was created after this file's mtime, recorded exactly this file's sha256 and byte count, is archived, and agrees with the receipt and with verdict.dossier_sha256. So the verdict can be made conditional on an artifact that does not exist yet, and the condition is enforced by code rather than by trust.

**What that buys, and what it does not.** It buys a mechanically enforced binding that has passed at least once, whose output is archived where it cannot be overwritten, and which is a hard precondition of both GO records. It does not buy an independent measurement of the current bytes by the reviewer beyond what its own read-only tools can hash. Section 0 says so rather than hiding it.

