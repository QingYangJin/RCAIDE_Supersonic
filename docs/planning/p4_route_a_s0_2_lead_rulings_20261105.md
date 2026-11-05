# P4 路线A S0-2 · Lead 裁定记录（2026-11-05）

> 性质：Lead 集成裁定（S0-2 阶段一 → 正式冻结前）；依据 A5 `EXT/p4-route-a/a5/S0_2_A5_review_phase1.md`（CHANGES_REQUESTED：2 blocker/3 major/4 minor）、A2 `S0_2_calibration.md`（radius_base 校准）、A4 合同 v1.1、D-S0-2-01..07。
> 硬约束：physical_call_count=0；不打开 meta_test/meta_test_ood/negative_control；不合并 main；不构成 S1 formal 放行。

## R-01（关闭 A5-S0P1-B01）family_version 唯一口径 = `p4ra-family-v3`
- 权威来源：合同 `p4_route_a_s0_design_contract.md:47/190` 与 D-S0-2-05（`p4_route_a_s0_2_decisions_20261105.md:55`）均已固定 `p4ra-family-v3`；代码/测试/设计文档中的 `v3` 属实现漂移，**以合同为准**。
- 修改面：`family_v3.py`（`FAMILY_VERSION`、fingerprint/payload）、`task_family.py`（v3 config 校验与 params 写入）、`tests/test_meta_learning_family_v3.py` 断言、冻结包全部 payload；设计文档 §1.1/§2.1 已同步更正。
- 影响：`family_fingerprint`、`split_hash`、`frozen_family`/`preregistration` 哈希全部变化 → **必须整包重生成**；旧 M2/M5/M6 冻结件不改。

## R-02（S1 前置）radius_base = 0.64（A2 校准），并披露判据口径
- A2 证据：`EXT/p4-route-a/a2/S0_2_calibration.md/.json`；meta_train 21 格 × 48 BO = 1,008 run / 64,512 合成评价，physical=0。
- 采用 **0.64**：pooled success 16/24=0.6667，逐 seed [0.750,0.688,0.750]，Wilson 95% [0.467,0.820]；与 M5（0.75/0.6667）难度经验对齐。设计初值 0.32 实测 pooled success=0.0（24 个 (任务,seed) 全未命中）**不可冻结**。
- 敏感性（pooled success）：0.44=0.250、0.47=0.333、0.53=0.417、0.56=0.542、0.60=0.583、0.64=0.667、0.66=0.708（>0.70 上界）；备选 0.60 记录在案。
- 口径披露（须写入 prereg）：候选格 pooled hit 仅 0.0065–0.0723（远低于 0.5），第二判据实际退化为「成功率带 [0.50,0.70] 内取最大半径」；与 M5 同现象。A5/A2 可在阶段二对该口径提出异议，但不得用 meta_test/OOD 调参。

## R-03（关闭 A5-S0P1-B02）preregistration 必须完整实现合同 §7
- 17 个必填字段按合同 `p4_route_a_s0_design_contract.md:184-204` 原名落盘：`schema_version=p4ra-prereg-v1`、`prereg_id`、`family_version`、`split_digest`、`task_id_regex`、`frozen_at_utc`、`secondary_metrics`、`budget_plan`、`task_counts`、`seeds`、`failure_rules`、`analysis_plan_digest`、`prereg_digest` 及其余字段；`multiple_comparison` 必须为 object。
- 名称口径：合同字段名为**规范名**；旧名（`split_hash`/`task_id_pattern`/`created_utc`/`secondary_endpoints`/`split_counts`/`optimization_seeds`+`meta_seeds`）可作为附加别名保留，但 verify 必须校验规范名存在且类型正确，缺失即 fail-closed。
- `analysis_plan_digest`：对 S1 统计/分析计划的 canonical JSON（不含绝对路径，含端点 ID、比较族、检验方法、多重校正、bootstrap 种子）取 sha256，并写入 prereg；今后分析脚本必须校验该 digest。
- 负控测试：缺任一字段、别名缺失规范名、错误类型（如 `multiple_comparison` 为 str）、`split_digest≠split_hash` 均须 fail-closed。

## R-04（M01）legacy prereg fail-closed 语义
- `verify_preregistration(payload, *, allow_legacy=False)`：默认**拒绝** `p4-m5-prereg-v1`（抛 `FeasibleV2Error`，附 `legacy_warning` 字段），仅历史只读路径显式 `allow_legacy=True` 放行并在返回值/日志记录 `legacy_warning`。
- 旧 M2/M5/M6 文件不改写；只读复核用 `allow_legacy=True`。

## R-05（M02）v3 `ENDPOINT_ROW_KEYS` 与分析键
- 在 v3 模块登记 `ENDPOINT_ROW_KEYS`：四个规范主端点 + `first_feasible_in_support`、`first_feasible_after_support_index`、`feasible_hit_rate_non_support`、`n_nonnull`、`null_rate`；统计 CSV/图表只读该登记表，禁止另起键名。
- 负控：端点全 null、键名与登记表不一致 → fail-closed。

## R-06（M03）隔离报告表述
- `v3_isolation_report.json` 必须分列：`task_id_intersection`（实质证据：v3 120 vs legacy 280，零交集）与 `task_fingerprint_intersection`（legacy 无指纹字段 → **NOT_DETERMINABLE**，不得写 PASS/ZERO_INTERSECTION 强断言）。
- `freeze_summary` 同步分开表述，禁止把空集当零交集证明。

## R-07 冻结包再生成与提交顺序（正式冻结前）
1. A1 完成 task-206 修复 + 全量测试（≥579 + 新增）OK；
2. Lead 提交代码/文档修复（commit X，包含设计文档更正）；
3. 在**干净工作树**运行 `make_freeze.py`，参数化真实 `run_id`（`p4ra-s0-2-freeze-<UTC>Z`）、`created_utc`、`git_sha=X`、`radius_base=0.64`，生成两遍并逐字节比对；
4. 冻结包提交 commit Y（仅冻结产物 + 摘要，不含外部原始大文件）；
5. A5 阶段二复核 → `APPROVE_FOR_S1_FORMAL` 才可 S1 formal；在此之前 S0-2 = NOT_COMPLETE。

## R-08 本轮边界（不变）
- physical_call_count=0；不启动任何求解器；不打开 meta_test/OOD/负控；不合并 main；不新开 PR；仅 Lead 写 GitHub。
- A1/A2/A4/A5 的交付仍按角色隔离；A5 阶段二审阅对象为 commit X + 冻结包 commit Y。

## 附：阶段一 A5 结论摘要
- verdict=CHANGES_REQUESTED（2 blocker/3 major/4 minor）；已通过项：五 split 60/20/20/10/10 + 120 IDs、40 预算计划 billable=B、K=0 CLONE 排除、四规范端点 ID、stopping_rules v2、run1/run2 7 payload 逐位一致、579 tests OK(skipped=1)、0 物理/0 求解器。
- 阶段一报告 sha256：`1825967f…`（详细版）；A5 测试日志 7,766 B。
