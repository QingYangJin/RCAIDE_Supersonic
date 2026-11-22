# Issue #14 P1 阶段回执草案（D-REAL-EXP-002 自适应迎角小批真实试验）

状态：DRAFT / NOT POSTED（由 make_p1_receipt.py 生成）；这不是 P2/P3/MAML 授权，也不构成 R1 全面 PASS。

## 一、结论摘要

- P1 已完成：真实 VSPAERO 启动 6 次（上限 12），全部 SOLVED，0 失败，0 重试，并行 1；内部 alpha 求解 case 18 个（上限 36）。
- 产出 5 条唯一真实准入标签（6 行准入，按证书去重），容差 1e-3 未放宽，全部来自可远端回读的原始 .polar 行。
- 自适应局部 bracket 把内部 solver case 从固定 49 点/设计扫描的 196 降到 18（省 178 个，约 90.8%），单设计内部中位数 3.0 个。
- 行级有效率 5/6 = 83.33%，但样本 n=6，判定 UNDERPOWERED_SMALL_SAMPLE；不宣称 70% 目标稳健达成。
- 本轮不产生任何 MAML 收益结论：P1 是 PILOT_NOT_A_TRAINING_BATCH，只有 5 条标签、单一 Mach，不足以训练或评测元学习。

## 二、授权与预算

- Owner 指令：m10191 批准真实评估；authorization_id AUTH-DREAL004-P1-20261122-01；batch_id DRECOVER001-P1-20261122-02-B01；run_id DRECOVER001-P1-20261122-02。
- 上限：12 design starts、每设计 3、每 start 3 个 alpha 读取点、36 internal、tol 1e-3、0 retry、parallel 1；实际使用：starts 6/12（剩余 6）、internal 18/36。
- 停止：d00 在 3 次启动后触发 MAX_PER_DESIGN；每个设计都要把预测点附近窗口收敛到 <= 1e-3 才准入，否则 NULL。
- 目标：DREAL004-M202（Mach 2.02，几何冻结 GBFREEZE2）；4 个设计 d00/d01/d04/d07。

## 三、真实准入标签（同升力条件）

| 设计 | case | D_i_N (N) | CL | alpha (deg) | rel err | 备注 |
|---|---|---|---|---|---|---|
| d00 | p1-m202-d00-r1 | 121438.589 | 0.181744721 | 5.181341 | 4.42e-06 | 两次启动，按证书去重 |
| d00 | p1-m202-d00-r2 | 121438.542 | 0.181744686 | 5.181340 | 4.23e-06 | 两次启动，按证书去重 |
| d01 | p1-m202-d01-r1 | 120206.230 | 0.179946784 | 5.129049 | 1.28e-05 | 面积 +1%（Sref 361.8325） |
| d04 | p1-m202-d04-r1 | 121679.606 | 0.181744291 | 5.191543 | 2.05e-06 | 后掠 +1 度 |
| d07 | p1-m202-d07-r1 | 121438.589 | 0.181744721 | 5.181341 | 4.42e-06 | 与 d00 coarse polar 字节相同 |

说明：q = 20483.94023 Pa，Sref 358.25 m2（d01 为 361.8325 m2）；D_i_N = q*Sref*CDi 只含机翼诱导阻力，不是整机阻力，也不含配平/粘性/波阻，更不是油耗。

## 四、内部成本与自适应方法

- 方法：用 G2 stage1 M202 的粗极曲线（零新物理）给出 alpha 初始 bracket 与预测点，每次真实启动只在预测点附近解 3 个 alpha；残差 >1e-3 时按斜率再细化一轮（最多 3 轮/设计），仍未收敛则 NULL。
- 每设计内部 case：[9, 3, 3, 3]；总墙钟 12.566 秒（不含排队与上传）。
- 对照：固定 49 点极曲线扫描需 4 设计 x 49 = 196 个内部 case；P1 用 18 个（每个唯一标签 3.6 个内部 case）。这是成本结论，不是精度结论。

## 五、A5 独立审查

- 协议复审：P1_PROTOCOL_AND_CODE_REVIEW_PASS（子智能体 deepseek-flash 单发只读，非人类签署）。
- 结果复审：P1_RESULT_REVIEW_PASS；gates: {"P1_ACCOUNTING_CONSISTENCY": "PASS_WITH_DISCLOSURE", "P1_RAW_BYTES_REMOTE": "PASS", "P1_ADMISSION_TOLERANCE": "PASS", "P1_BUDGET_COST": "PASS", "P1_STATISTICAL_CLAIMS": "PASS", "P1_BOUNDARIES": "PASS"}
- A5 结果复审给出的 minor 项：重复启动根因未彻底解释；CL 侧比对是自洽校验（独立信息来自 alpha→CDi→D_i_N 复算）；6 次 start 跨多版 driver/GO 增加溯源复杂度。这些项已在第七节如实披露，未用 A5 结论关闭。
- A5 结论不等于人类签署，也不等于 R1 全部代码 PASS；A5 指出的限制见其 limitations 字段与下文披露。

## 六、远端证据与回读

- 分支 research/dreal004-alpha-adaptive-meta-sampling，P1 目录 research/concorde_metaopt/optimization_runs/DRECOVER001-P1-20261122-02，commit 8c1acc13d2c041c6ee966ce008ebb2b5572cf52b。
- 上传 132 文件 / 5805712 字节；回读 checked 132，missing []，bad []。
- A4 远端复核（GitHub blob API 按原始字节读回后逐字节核对 + 独立复算）：manifest 文件 132/132 通过，bad []，not_ok []；成功 case 复算 5/5；失败样本 g1-m202-d05-query.polar 预期不存在（404=True）；A4 判据 = True。
- 复算恒等式：D_i_N = q*Sref*CDi（CDi/CL 取远端 .polar 原始行中与报告 alpha 匹配的那一行），rel_di <= 1e-6；CL 相对误差均 <= 1e-3。
- 目录：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/8c1acc13d2c041c6ee966ce008ebb2b5572cf52b/research/concorde_metaopt/optimization_runs/DRECOVER001-P1-20261122-02
- 图表（仓库内）：research/concorde_metaopt/optimization_runs/DRECOVER001-P1-20261122-02/figures/ 下 cl_alpha_adaptive_vs_fixed.png、p1_outcome_overview.png、di_n_by_design.png、internal_cost_by_design.png，配 figure_data.csv。

## 七、偏差、缺陷与披露

- 重复启动：p1-m202-d00-r1 被两个进程重叠启动两次，两次均计费（计入 6 次 starts），标签按证书去重，只算 1 条唯一标签；随后把 run lock 和每设计上限作为硬检查加入执行器。
- 首批准入失败：第一批 3 个 start 已 SOLVED，但准入步骤因时间戳格式错误失败（ADMIT_FAILED）；修复后离线重新审计并准入，未增加物理启动。
- 协议迭代：执行器在批次内修改过 4 次，每次重新预注册、重新 A5 复审并重签 Lead GO；6 次 start 分布在多版 GO 下，最终 GO 绑定最终代码，历史 GO 记录保留在 RUN 目录。
- d07 与 d00 的 coarse polar 字节相同：因此 d07 标签数值与 d00 相同，不能当作独立设计的独立证据。
- 没有失败求解样本：P1 的 6 次启动全部 SOLVED，A4 失败样本借用 G1 的 NO_RESULT case（无 .polar，404），不冒充 P1 数据。
- 边界：同机保存、未异机认证；未做风洞/物理验证；fuel_burn_kg=null；LF-M2.02=NOT_VALIDATED；标签是本地 raw 字节 + 审计绑定的标签，不是独立可信执行环境认证的标签。
- 缩水声明：P1 只证明自适应局部 bracket 能在 1e-3 容差下产出真实标签并显著降低内部成本，不证明精度提升、不证明泛化、不证明 MAML 有效。

## 八、下一门禁（未授权）

- P2/P3/MAML 均需新的预注册 + A5 独立审查 + 新的 Lead GO；本回执不授权任何新物理。
- P2 草案（Issue #14 预注册已写）：扩展到多 Mach 任务族（>= 8 任务，<= 240 starts），在真实标签上做 K=1/3/5 FOMAML 与普通预训练对照；理由：现有 5 条标签不足以支撑任何元学习结论。

## 九、关键文件（本仓库）

- docs/evidence/dreal004/p1/p1_preregistration.json：sha256 dfbde72fe6e6e2064dc61b2d9efabcc792adb4414576d6c03bc907817744d477
- docs/evidence/dreal004/p1/p1_accounting.json：sha256 880669f8e662589fdcfa6265d61657c3c90d8977f4640b05fce24b04bde85996
- docs/evidence/dreal004/p1/p1_metrics.json：sha256 ac5447566a0acddcb02ef575ecf5ad7bd714dcb2cebef3935d875e551da739c7
- docs/evidence/dreal004/p1/p1_result.json：sha256 c4615ff09d386513d75798a466d16a1cf0539c4c4aab1876011232a84cf0a687
- docs/evidence/dreal004/p1/p1_go_record.json：sha256 6d8deb7dbede92c883a20b2ac6343cc99de1aaebe78a3b7cc54a8d3c6595a3d8
- docs/evidence/dreal004/p1/p1_admitted_labels.csv：sha256 cac192ef0f53dd757910394b046a368ffc3b758e86f3f2456aeb0088134780da
- docs/evidence/dreal004/p1/a5_protocol_verdict.json：sha256 672cb6bbe36aa76adbbe3341dbb1e51435e117c44b1415de5cd96538887972ef
- docs/evidence/dreal004/p1/a5_result_verdict.json：sha256 8837d6fc75a03601fd296e0e3c63df9b2071211a0f164a4e5fd0623fd6322502
- docs/evidence/dreal004/p1/p1_a5_protocol_dossier.md：sha256 639ac4a206e58e2310367938c381dcec93dd06e9f5351e4879ca89450f17de28
- docs/evidence/dreal004/p1/p1_a5_result_dossier.md：sha256 c4adae27fca46d8d7afbf84e257d0c2bcedc20d21e29e63a9df4367d5e412089
- docs/evidence/dreal004/p1/p1_remote_retrieval_audit.json：sha256 283647c00fc1f2218ce78b57cefe01be4e14f143b307aecc83ce76f24d373445
- docs/evidence/dreal004/p1/p1_upload_receipt.json：sha256 c8c7bf91555b61b9f1b55ef6972850453a5b333c6c6821c1205398a938a9708a
- 原始数据与表格：research/concorde_metaopt/optimization_runs/DRECOVER001-P1-20261122-02/（raw_cases/、p1_admitted_labels.csv、p1_accounting.json、p1_metrics.json、p1_result.json、figures/、SHA256SUMS.txt）

