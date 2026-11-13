# A1 M0-R Interface Clarification (zero physics)

- clarification_id: A1-M0R-INTERFACE-CLARIFICATION-20261113
- created_utc: 2026-11-13T06:56:44Z
- status: authoritative clarification; frozen files were not rewritten
- code commit: 0c514151d989de716dbb855973b900a34615b5aa
- freeze commit: c5698a218fad974e8e96b604573c5cc79b3abb32
- physical_call_count: 0; solver_started: false; spawn_events: []; no run dir

This addendum records the three corrections accepted by A5 pre-review and Lead. The A1 frozen code and interface bytes stay unchanged; the M0-R package and the A5 G-M0R-ADMISSION-01 gate must use the wording below.

## CL-1 SREF: runtime value is the only source, frozen constant is a validation anchor

SREF_REF is the runtime post-fix baseline geometry.wing.area_m2 recomputed by the evaluator (this run: 358.25000000000006). SREF_REF_FROZEN (task_evaluator.py:56) is a validation anchor only; build_task_spec validates the runtime value at task_evaluator.py:296-303 with 1e-12 relative tolerance, and the runtime value comes from the baseline build at task_evaluator.py:1169. No objective or target formula may hard-code 358.25.

M0-R wording: SREF_REF 以 post-fix baseline 几何运行时重算值为唯一来源（本次 358.25000000000006），冻结常量仅作 1e-12 校验锚；不得把 358.25 作为计算输入硬编码。

## CL-2 solver_input_sha256 is per-run metadata, not a cross-process expected value

The .vkey embeds an absolute path and a random OpenVSP component object ID, so solver_input_sha256 is not deterministic across processes. Deterministic bindings use deck_sha256 + vspgeom_sha256 (+ solver_sha256 and task_fingerprint); vkey and solver_input_sha256 are recorded per run only.

- A1 dry-run input_sha256: 9785548818a7ecba73b2f13c73499b630d04c61e8d6abab395a0ab6ff93b8f4d
- A5 independent rerun: ebdfb1ff...
- identical: deck_sha256 1614a964fc729d42bfa764025a2aa1d3915be8f20dbc6480b72862c15e0c59dc, vspgeom_sha256 16da482a1f8e59f6b454378769961caafde5eef87784127db6cce87381943b84
- observed vkey: 417 B, absolute path plus random component ID ZCUUDKMFCZ

M0-R wording: solver_input_sha256 含 path-dependent/random 的 .vkey，跨进程不可复现；确定性绑定只用 deck_sha256 + vspgeom_sha256（加 solver_sha256/task_fingerprint），vkey 与 input_sha 按 run 记录，不作跨进程 expected。

## CL-3 F1R2 continuity is physical-condition continuity, not deck-byte continuity

At M2.02/18,288 m the physical conditions are bitwise continuous with F1R2 (q=20483.940233430174 Pa; same Mach/Vinf/Rho/ReCref/alpha grid). Deck bytes differ:

- A1 M202 deck: 943 B, LF only, SHA 1614a964fc729d42bfa764025a2aa1d3915be8f20dbc6480b72862c15e0c59dc
- F1R2 preflight deck: 985 B, CRLF 42, SHA 3c70d11ae6af74e6fd1cf9b787c71571768bc398a07b1343df9a1340cf93b837
- after CRLF normalization: 43 lines identical; 42-byte difference equals the 42 CRLF pairs

M0-R wording: M2.02 仅物理条件与 F1R2 逐位连续（q=20483.940233430174，Mach/Vinf/Rho/ReCref/alpha 网格相同），deck 字节不相等（A1 943B/LF vs F1R2 985B/CRLF，43 行规范化后相同）；不继承 F1R2 expected polar，M1-A 重建 admission baseline。

## Frozen file references

- task_evaluator_py: e88c21775d753c555b1ba8d5076c45d5c3fc956be8c2daf8eb194e73ec777261 / 63459 B (research/concorde_metaopt/dreal001/m1/task_evaluator.py)
- interface_md: 6ef6b16e181f404ee6219db27a9125769b78d5368de653ec791c2aa21a4e790b / 16925 B (docs/receipts/dreal001/a1_m0r_task_evaluator_interface_20261113.md)
- dry_run_json: 8688d25770911af7fadd42587f66a4914091c829fd8cdc89c1f349a53731b4c6 / 43587 B (docs/receipts/dreal001/a1_m0r_task_executor_dry_run_20261113.json)
- u1_json: d90f2ed5ca3031be6500e4b7a4167253f4aa03828438af1e137b703164ab0e8e / 33508 B (docs/receipts/dreal001/a1_m0r_u1_geometry_rebind_20261113.json)
- freeze_json: a2faeda15dd56228ac832dbd1d8db37d80235790bb63c602a66f66805d3c6a02 / 25639 B (docs/receipts/dreal001/a1_m0r_interface_freeze_20261113.json)
- freeze_md: c81fe1a899044a1cf4a9344070127a8402e9707cf418dcea09d1bdde55a002ab / 5996 B (docs/receipts/dreal001/a1_m0r_interface_freeze_20261113.md)

## Physical accounting

physical_call_count=0, physical_solver_starts=0, solver_started=false, spawn_events=[], run_dir_created=false. No VSPAERO solver was started.
