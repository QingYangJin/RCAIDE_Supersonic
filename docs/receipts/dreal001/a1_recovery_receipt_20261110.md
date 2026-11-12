# A1 恢复回执（D-REAL-001，零物理）

## 1. 身份与范围

- 角色：A1（几何冻结 / 真实 VSPAERO 接口 / F 线评价）
- 工作树：D:\RCAIDE\dnext001\wt-real-a1-geometry-solver
- 分支：research/dreal001-a1-geometry-solver，基线 683a868（未 push）
- 恢复来源会话：e145285d-5350-4ff1-9097-78386768cbec（A1 主会话）、3670a051（r1-geometry，A1 P0/P1 代码）
- 恢复方式：DSH 会话转录重放（tools.write/edit、fs.writeFile(Sync)、heredoc）+ 数据类文件确定性重生成

## 2. 恢复清单

- 清单文件：D:\RCAIDE\_recovery\a1\recovered_manifest.json
- A1 范围：141 个文件、8,380,034 字节；逐文件 bytes + SHA256 + 来源会话 + 置信度
- 关键 SHA256：
  - configs/dreal001_task_fixed_cruise_REAL.json（6,144 B）028086a56f466c1639432218f6928deb6d479160a13db597fef1aa7284e1f0f7
  - configs/design_space_12d_lifting_surfaces.yaml（10,846 B）8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e
  - design_space_freeze.json（41,775 B）fe7e48eba6a70eb76b0b139b1004f775830da68bd5d003604d686e59656e8373
  - P1R_PREREGISTRATION_v1.md（26,748 B）b521186aa36b219b23f2b550abf09869b9d64eb5c7bb3aeb8e2f3035ce35d0ec
  - runs/DREAL001-P1R-20261110-01/plan.json（86,710 B）d5562574bbc103e51be09ad09596da00303184178c29615b5cdf55f1b0940476
  - runs/DREAL001-P1R-20261110-01/preflight/index.json（19,960 B）36da4db0d404bc6f47520e60812a655cad1dcaacc169388fa79dc91563376564
  - runs/DREAL001-P0R-20261110-01/plan.json（6,303 B）b26be3cae4f33289f2c6ee85b054f41cbae0fc1ef1b57047eedc42ba9b734588

## 3. P0 冻结件与三口径

- 12D yaml：frozen true、bounds_status frozen_for_dreal001_20261110、freeze_note 存在、provisional 计数 0；W01–W10 + V01–V02 保留，F01–F03 固定未删。
- freeze json：wing_ac_x_m 16.821978259514246 与 geometry_cg_x_m 28.287395109126685 分列，wing_ac_is_aircraft_cg=false；无歧义 Xcg 字段。
- TaskSpec hash_scope（run_closeout.task_spec_hash_scope）：canonical dca981e2… / raw 028086a5…（6,144 B）/ git blob 3f831d4b…。
- correction_001 生成器已补 created_by、created_at_utc、issue、correction_type、run_id；旧 16,075 B 记录 NOT_RETAINED，21,537 B 记录 RETAINED_IN_GIT_HISTORY（b5dcbbc）。

## 4. 新批次准备（未执行）

- DREAL001-P0R-20261110-01：1 次 TOOLING_SMOKE；CFG-01 预检 all_ok、7 internal、网格族 543x472；plan PENDING_APPROVAL，approval 未批准。
- DREAL001-P1R-20261110-01：25 starts / 189 internal（caps 26/196）；8 个唯一配置预检 all_ok、physical_solver_starts=0；plan PENDING_APPROVAL，approval NOT_APPROVED。
- 网格族规则：每设计 ≤12 次零物理 round-trip 重建，目标族 543x472，达不到 FAIL_CLOSED；逐 start 记录 mesh_attempts/nodes/elements/vspgeom SHA/canonical topology hash；缓存 key 含 mesh。
- 旧 P0/P1 run 目录已写 RECOVERED_HISTORICAL.md 标记，字节不改。

## 5. 测试（零物理）

命令：python -m pytest research/concorde_metaopt/tests -q -k 'dreal001 or geometry or design_space' -p no:cacheprovider

结果：194 passed, 19 skipped, 1680 deselected in 14.45s。skip 中 4 项为依赖 P0 真实证据的 identity 用例，理由 NOT_RECOVERABLE。

## 6. 不可恢复项

- P0/P1 真实 solve 数据：solver_attempts.jsonl、evaluations.jsonl、case 目录、polar/history/vspgeom/vkey、data_manifest、SHA256SUMS、corrections（P1 全部、P0 全部）。
- E6-SENSITIVITY-20261110 的 determinism 探针与 e6_sensitivity.json。
- 冻结件旧字节 SHA（freeze 40,432 B/79b36591…、yaml config 56503a55…）不可复核，仅作历史记录。

## 7. 声明

- physical_solver_starts = 0；本回执涉及的全过程未启动 vspaero.exe。
- 预检仅用 OpenVSP 的 VSPAEROComputeGeometry（StopBeforeRun=1）做零物理网格与输入回读。
- 未 push；P0_PASS/P1R 首启必须等 A5 在新 HEAD 复签 + Lead 书面 approval.json 与 window token。