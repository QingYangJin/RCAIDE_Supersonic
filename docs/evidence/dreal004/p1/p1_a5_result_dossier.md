# P1 结果卷宗（D-REAL-EXP-002 P1 自适应迎角小批真实试验）

本卷宗用于 A5 对 P1 结果与账本的独立复审；不是人类签署，不授权 P2/P3/MAML。

## 1. 批次身份
- run_id: DRECOVER001-P1-20261122-02；batch_id: DRECOVER001-P1-20261122-02-B01；authorization_id: AUTH-DREAL004-P1-20261122-01
- Owner 指令: m10191 批准真实评估；P1 上限 12 starts、每设计 3、每 start 3 alpha 点、36 internal、tol 1e-3 不放宽、0 retry、parallel 1
- 预注册 sha256: dfbde72fe6e6e2064dc61b2d9efabcc792adb4414576d6c03bc907817744d477
- 最终 GO sha256: 6d8deb7dbede92c883a20b2ac6343cc99de1aaebe78a3b7cc54a8d3c6595a3d8
- 协议 A5 复审 verdict: P1_PROTOCOL_AND_CODE_REVIEW_PASS（deepseek-flash，非人类）

## 2. 真实启动与内部成本（账本口径）
- 真实 design starts: 6 / 12；完成: 6；重试: 0；并行: 1；NULL: 0
- 内部 alpha solver cases: 18 / 36；每设计: [9, 3, 3, 3]（中位数 3.0）
- 固定 49 点/设计扫描基线 196 个内部 case；本批节省 178 个内部 case；每个唯一标签成本 3.6 个内部 case
- 总求解墙钟: 12.566 秒
- 重复启动: p1-m202-d00-r1 被启动两次（两个进程重叠，均已计费）；准入标签按证书去重：6 行 -> 5 张唯一证书

## 3. 标签（真实 raw 行，relative CL error <= 1e-3，未放宽容差）
- d00 / p1-m202-d00-r1：D_i_N=121438.588686 N，CL=0.181744720773，alpha=5.181341，rel=4.420e-06
- d00 / p1-m202-d00-r2：D_i_N=121438.542132 N，CL=0.181744686378，alpha=5.18134，rel=4.231e-06
- d01 / p1-m202-d01-r1：D_i_N=120206.230260 N，CL=0.179946783992，alpha=5.129049，rel=1.284e-05
- d04 / p1-m202-d04-r1：D_i_N=121679.605862 N，CL=0.18174429066，alpha=5.191543，rel=2.054e-06
- d07 / p1-m202-d07-r1：D_i_N=121438.588686 N，CL=0.181744720773，alpha=5.181341，rel=4.420e-06

## 4. 命中率与统计主张
- 行级有效率 5/6 = 0.8333；目标 70% 仅按行达成，样本 n=6，判定 UNDERPOWERED_SMALL_SAMPLE
- 不宣称 70% 目标稳健达成；不宣称任何 MAML 收益；P1 不是训练批次（PILOT_NOT_A_TRAINING_BATCH）

## 5. 远端字节复核（A4）
- remote head: 8c1acc13d2c041c6ee966ce008ebb2b5572cf52b；manifest 文件 132，逐字节核对通过 132，bad=0，not_ok=0
- 方法：GitHub Git Data API：按 commit->tree SHA 下钻得到远端 blob SHA1，再按 blob API 读回原始字节做 SHA256 逐字节核对；未构建整仓 zip
- 独立复算成功 case：5/5 通过（从远端 .polar 原始行重算 CL/CDi 与 D_i_N=q*Sref*CDi 恒等式）
- 失败样本：research/concorde_metaopt/optimization_runs/DRECOVER001-G1-20261121-01/raw_cases/g1-m202-d05-query/g1-m202-d05-query.polar，远端 present=False，无 polar 符合预期=True，HTTP=404
- A4 判据: True
- 上传回读：commit 8c1acc13d2c041c6ee966ce008ebb2b5572cf52b，file_count 132，missing/bad 均为空: []/[]

## 6. 已披露偏差与限制
- P1 driver 共 4 版：每次修改后重新预注册、重新 A5 复审并签发新 GO；6 次 start 分布在多版 GO 下，最终 GO 绑定最终代码（协议迭代已披露）
- p1-m202-d00-r1 重复启动两次（进程重叠）：两次均计费，标签按证书去重；这是执行控制缺陷，已如实记账
- 第一批 3 个 start 已 SOLVED 但准入步骤因时间戳格式失败（ADMIT_FAILED）；修复后离线重新审计+准入，未增加物理
- 自适应 bracket 来自 G2 stage1 M202 coarse polar 原始行（零新物理），不是 P1 自己的新数据
- 同机保存，未异机认证；未做风洞/物理验证；fuel_burn_kg=null；LF-M2.02=NOT_VALIDATED
- 只有 5 条唯一标签，样本不足，任何跨任务/MAML 结论均不成立
- 远端复算中 CL 的比对基准是准入阶段记录的同一 polar 行 matched_cl，因此 CL 恒等是自洽校验；独立信息体现在按报告 alpha 从远端原始行取 CDi 并复算 D_i_N=q*Sref*CDi
- 仓库内 a5_review/review_log.txt 是 UTF-16LE 编码（PowerShell Tee 输出），已按字节 SHA256 纳入 manifest 并在远端 blob 层逐字节核对；GitHub contents API 会把它当文本转 UTF-8，因此本复核使用 blob API 原始字节

## 7. 请 A5 判断的关键点
1. 账本是否自洽：6 starts / 18 internal / 5 唯一标签 / 重复启动披露是否可接受
2. 标签是否为真实 raw 行且 tol=1e-3 未放宽（不得把插值当 raw）
3. 远端字节复核与独立复算是否足以支撑 A4（无失败 P1 case 时用 G1 NO_RESULT 作失败样本是否可接受）
4. 统计主张是否被限制在 pilot/UNDERPOWERED 范围内
5. 是否放行 P2（本卷宗不请求 P2 GO；P2 需新的预注册与 GO）
