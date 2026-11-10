# D-NEXT-001 A5 独立评审：M0 门禁与物理口径（待审条件清单 v1）

- 评审人：A5（独立审查；不实现被审业务算法）
- 评审对象：M0 门禁（A1 TaskSpec / CG / 质量合同；A2/A3/A4 的 M0 前置口径）
- 当前状态：A1 产物尚不存在（wt-a1 HEAD=ea8ad97833eb5ceab291faae643c141a2b219749，无 receipt、无 TaskSpec 合同文档；脚本 A5-C12=NOT_RUN）
- 因此本文件不是对 A1 的评审结论，而是"待审条件清单 + 判定判据"：A1 交付后按其逐条对照，A5 只据此出 PASS / CHANGES_REQUESTED / FAIL
- physical_call_count=0；本评审不调用任何物理求解器，不产生新的物理结论

## 0. 不可改写的历史物理口径（M0 必须继承）

| 编号 | 事实 | 来源（只读） |
| --- | --- | --- |
| H-1 | X_cg=16.821978 m 实为机翼气动中心（AC），不得作为全机 CG 使用 | S2/S3 封账披露 |
| H-2 | 几何全机 CG=28.287395 m | 几何计算产物（只读归档） |
| H-3 | 136,000 kg 是单巡航进入质量（任务进入条件），不是几何 MTOW | 任务/几何档案 |
| H-4 | 几何 MTOW=184,880 kg | 几何产物 |
| H-5 | VSPAERO 内部系数（CL/CD 等）不等于整机油耗；阻力/油耗物理验证状态仍为 NOT_VALIDATED | 计划文档 + S3 报告 |
| H-6 | VSPAERO LF-M2.02=NOT_VALIDATED；BODY-CORR=BLOCKED | S2/S3 封账披露 |
| H-7 | 上一阶段：S1 21000 runs 主端点无显著受益；S2 Full MAML 比 FOMAML 更差；S3 四检验 NULL、阶段放行 NOT_ISSUED | S1/S2/S3 封账 |

上述任一条被新交付"重新解释"而未给出新证据与具名复核 => 直接判 FAIL（见 §4）。

## 1. A1 必须交付的最小合同（缺一项即 CHANGES_REQUESTED）

- C-M0-01 CG 来源可追溯：每个 CG 值必须带 source_kind（MEASURED/GEOMETRY/DERIVED/ASSUMED）、source_path、source_sha256、坐标原点与轴向定义；禁止把机翼 AC 当全机 CG。
- C-M0-02 质量口径显式：至少区分单巡航进入质量（136,000 kg）、几何 MTOW（184,880 kg）；每个质量字段带 label、unit、provenance；禁止无标注地混用。
- C-M0-03 参考量可追溯：S_ref、C_ref（或 MAC）、b_ref、参考面积/长度单位与来源；VSPAERO 内部系数命名空间与整机指标命名空间分开（不得把内部 CL/CD 映射为整机油耗）。
- C-M0-04 力轴与力矩参考点：定义 body/wind 轴、正方向、力矩参考点（CG 或指定 ref point）及其与 X_cg 的关系；力矩量必须带 reference_point 字段。
- C-M0-05 TaskSpec 合同完整：task_id、任务类型（巡航/机动）、目标函数、约束、设计空间（变量名/上下界/单位/是否整数）、评价器 ID 与 fidelity、预算 B、随机种子、初始设计集来源、evaluator_id、physical_validation_status。
- C-M0-06 评价器契约：对象必须区分"求解器内部成功"与"物理有效"两个状态（如 GEOMETRY_INVALID / SOLVER_NONCONVERGED / PHYSICS_NOT_VALIDATED），不得用"求解成功"冒充"物理验证通过"。
- C-M0-07 来源与证据字段：每个数值带 unit、source_kind、source_path、source_sha256；缺任一 => 该数值视为不可审计。
- C-M0-08 版本与冻结：TaskSpec 必须带 git_sha + code_sha；合同 JSON 需可规范化序列化并给出 canonical sha（与 S3 同一 canonical_json 约定）。
- C-M0-09 不得以提交消息/口头说明替代字段证据。
- C-M0-10 不得引入未授权的物理调用（VSPAERO/SU2/Mission/WaveDrag 本轮上限 = 0）。

## 2. 判定判据（A1 交付后逐条执行）

### 2.1 PASS（全部满足才可）
- §1 全部合同项在 TaskSpec 文件与测试中可验证；
- CG/质量/参考量三类数值与 §0 历史口径一致或有新证据链（新证据须具名、可复现、由 A5 独立复核）；
- 合同中的每个数值都能由"字段 + 单位 + 来源 + sha"四元组回溯；
- 单测覆盖：单位换算、CG 越界拒绝、机翼 AC 被误用为 CG 时必须报错、质量口径混用必须报错；
- 复跑命令与测试结果一致，无物理调用（physical_call_count=0）。

### 2.2 CHANGES_REQUESTED（可修复，不阻断后续设计）
- 合同字段齐备但命名/单位/来源部分缺失；
- 缺负向测试（例如未测"机翼 AC 当 CG"必须被拒）；
- 参考量或力轴定义在文档中已有但未进入机器可读合同；
- 存在 NOT_VALIDATED 字段但已显式标注（允许进入 Wave-1 设计，不得进入真实评价）。

### 2.3 FAIL（任一命中即 FAIL，且不得以"后续补"放行）
- 机翼 AC（16.821978 m）被用作全机 CG，或 X_cg 未声明来源；
- 136,000 kg 与 184,880 kg 未显式区分，或以单点质量冒充 MTOW；
- VSPAERO 内部系数被直接当作整机阻力/油耗结论；
- 缺力矩参考点却输出力矩量；
- 合同数值无法回溯（无 source_path/sha）；
- 以提交消息、执行人自述、图表外观替代可复现证据；
- 出现未授权的真实物理求解调用（>0）。

## 3. 预启动检查清单（A1 交付后、M0 签字前必跑）

| 编号 | 检查 | 方法 | 失败处理 |
| --- | --- | --- | --- |
| P0 | 工作树边界 | git -C D:\RCAIDE\dnext001\wt-a1 status --porcelain；确认只改 wt-a1 | 跨树写入 => FAIL 并停止 |
| P1 | 产物存在性 | glob docs/contracts/**/*.json、docs/receipts/dnext001/*.md | 缺失 => NOT_RUN，不签字 |
| P2 | 物理调用计数 | 逐 run_config.json / metrics 检查 physical_call_count 字段 | 非 0 => FAIL |
| P3 | CG 口径 | 合同 CG 与 16.821978 m / 28.287395 m 比对；检查 source_kind | 机翼 AC 当 CG => FAIL |
| P4 | 质量口径 | 合同质量与 136,000 / 184,880 kg 比对；检查 label | 混用/无标注 => FAIL |
| P5 | 参考量与力轴 | S_ref/C_ref/b_ref/轴/力矩参考点字段齐全 | 缺 => CHANGES_REQUESTED |
| P6 | 求解成功 vs 物理有效 | 评价器状态机是否区分三类失败 | 混淆 => FAIL |
| P7 | 单测可复跑 | & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest <a1 tests> -q | 失败/不可复现 => FAIL |

## 4. A5 的签字规则

- 只对"我实际运行过命令并看到输出"的对象签字；未审阅提交不签 PASS。
- 签字必须附：文件路径 + canonical sha + 运行的命令 + 结果摘要 + physical_call_count。
- 只有 PASS / CHANGES_REQUESTED / FAIL 三种结论；证据不足写 NOT_VALIDATED 而不是 PASS。
- 若 A1 只交提交消息或截图而无合同文件 => NOT_RUN，直接退回。

## 5. 当前结论

- A1 M0 合同：NOT_RUN（产物不存在），本文件为待审条件清单 v1。
- 待 A1 交付后，A5 按 §2/§3 执行并另出具名 verdict；本清单本身不构成任何 PASS。

## 6. 声明

- physical_call_count=0；未启动 VSPAERO/SU2/Mission/WaveDrag。
- 未修改 A1 工作树；未替未审阅提交签 PASS。
