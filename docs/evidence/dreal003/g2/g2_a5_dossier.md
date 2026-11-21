# G2 独立预审 dossier（第 5 版；deepseek-flash 只读；非人类签字）

## 1. 授权与性质
- Owner 在 m08739 对 Lead 的 G2 提案回答“批准”。G2 提案：新 authorization、8 任务×8 设计、上限 240 starts；本文件请求 A5 预审 **首批 ≤24 starts**（完整计划 128 starts，分 6 个 mini-batch）。
- 当前零物理：证据文件 g2_zero_physical_snapshot.json（SHA256 edf212a58ad6c90802135c059e5281516d513908ec2970af4effa8979d186732）记录 physical_solver_starts_actual=0、internal=0、charged=0、reserved=0、admitted=0；G2 只建了 64 个输入 deck，未执行任何 case。G1 的 24 starts 属于另一已结案批次，不计入本批。
- 本文件不是人类签字；A5=deepseek-flash 单发只读，无工具，不得冒充人类。

## 2. 关键哈希与文件绑定
- run_id: DRECOVER001-G2-20261121-01
- authorization_id: AUTH-DREAL003-G2-20261121-01
- preregistration_sha256: d4aa6c235367a3093933dacb2039ceab8baa9c392fe6c61aeb00dd4e4fce83f9
- stage1_case_manifest_sha256: 87ba0f47c9069ee4b00ed9312f1ad3cd32aac020e08546a4605d0c21b1bfe5fc
- stage1_case_count: 64
- g2_build.py_sha256: 3de1c261abc1a38f5f12c4d2d4c3c83bccefd75300d5b4f3df65fc0bbedf18b8
- solver_runner.py_sha256: cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3
- zero_physical_snapshot_sha256: edf212a58ad6c90802135c059e5281516d513908ec2970af4effa8979d186732
- base_commit: 409f09c8b31ce653873727217273805a16d5b422
- geometry_contract_sha256: 5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15
- solver: D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe, omp 1, timeout 600s, parallel 1, retries 0
- 自哈希定义：dossier_payload_sha256 = SHA256(本文件中标记行 <!-- SELF_HASH --> 之前的所有字节)；第 8 节在标记行后给出该值。A5 无工具，无法自行重算任何哈希；哈希由 Lead 在调用前计算并写入 g2_a5_review_request.json，A5 的职责是审查内容与方法，不是重算哈希。

## 3. 任务族与 split（8 任务，4 train/2 val/2 test）
| task_id | Mach | split | 设计数 | q Pa | sref m2 | CL target 范围 |
|---|---|---|---|---|---|---|
| DREAL003-G2-M140 | 1.40 | train | 8 | 9839.36 | 354.6675/358.25/361.8325 | 0.374615–0.382183 |
| DREAL003-G2-M160 | 1.60 | train | 8 | 12851.408 | 354.6675/358.25/361.8325 | 0.286815–0.292609 |
| DREAL003-G2-M180 | 1.80 | val | 8 | 16265.064 | 354.6675/358.25/361.8325 | 0.226619–0.231197 |
| DREAL003-G2-M200 | 2.00 | train | 8 | 20080.326 | 354.6675/358.25/361.8325 | 0.183561–0.187270 |
| DREAL003-G2-M202 | 2.02 | train | 8 | 20483.94 | 354.6675/358.25/361.8325 | 0.179944–0.183580 |
| DREAL003-G2-M220 | 2.20 | val | 8 | 24297.194 | 354.6675/358.25/361.8325 | 0.151704–0.154768 |
| DREAL003-G2-M240 | 2.40 | test | 8 | 28915.669 | 354.6675/358.25/361.8325 | 0.127473–0.130048 |
| DREAL003-G2-M260 | 2.60 | test | 8 | 33935.75 | 354.6675/358.25/361.8325 | 0.108616–0.110810 |

设计：d00 基准、d01 机翼面积+1%、d02 sweep_1+0.5°、d03 面积-1%、d04 sweep_1-0.5°、d05 垂尾面积+2%、d06 sweep_2+0.5°、d07 机身长度+1%。support=d00–d03，query=d04–d07；每任务 8 个唯一设计，共 64。

## 4. 两段式 alpha 方法（针对 G1 15/23 null）
- G1 根因：单次 17 点网格以预测 alpha 为中心，插值残差不满足 1e-3 升力相对容差；G1 拒绝放宽容差、拒绝把插值当原始行。
- stage1：49 点、步长 0.24°，覆盖全窗口内部 (-1.76…9.76)，不依赖 Mach 专用斜率；每 case 1 start、49 internal。
- stage2：取 stage1 原始 polar 同 Mach 有效行（最多 49），在完整 stage1 alpha 范围内做 OLS CL(alpha)，要求 ≥5 点且 R²≥0.99；求命中 cl_target 的 alpha_t；在 alpha_t ±0.006° 内布 13 点、步长 0.001°；每 case 1 start、13 internal。
- OLS 披露：拟合只用于选 stage2 网格中心，是模型步骤；准入不依赖拟合，只要求 stage2 原始 polar 行满足 |L-L_target|≤1e-3·L_target；不插值、不放宽。每 case 报告拟合点数与 R²。实现中若 <5 点或 R²<0.99 直接跳过并不建 stage2。
- 准入不要求 bracket：只要有原始行命中容差即可。
- 定量容差：最低 CL_target=0.108616 → 绝对容差 1.086e-4；保守局部斜率 0.020/deg 时最近点误差 0.0005° 诱导 CL 误差 1e-5，比容差小 10 倍以上；预测斜率偏差 50% 时目标偏移约 0.0033°，仍在 ±0.006° 半宽内。
- 失败分类预定义：NULL_STAGE1_NOT_BRACKETED（stage1 原始行不 bracket 目标，如 M140 近 10° 边缘；不扩窗、不重跑）、NULL_STAGE1_REGRESSION_UNRELIABLE（<5 点或 R²<0.99）、NULL_STAGE2_NO_RAW_ROW_WITHIN_TOLERANCE、NULL_SOLVER_NO_RESULT（超时/崩溃）。
- 预期 null：0–16 个（主因 M140 八个设计可能不 bracket）；预先声明的上界，不是隐藏失败。预计 128 starts，internal=64×49+64×13=3,968；本批 24 starts。

## 5. 批次控制与账本
- mini-batch ≤24 starts、≤60 min；parallel 1；retries 0；case_timeout 600s。
- wall-clock 强制停止：每次启动前测 batch 已用时间；若 elapsed≥3300s 或 elapsed+case_timeout>3300s，则不再启动并关闭本批；运行中 case 的 timeout=min(600s, 3300s-elapsed)。预留 300s 上传/回读。规则在 g2_preregistration.json.solver.mini_batch_wall_clock_stop。
- 每个 mini-batch 后上传 raw/logs/CSV/accounting 到 GitHub，回读 SHA256SUMS 后再开下一批。
- 六口径：physical starts / internal cases / charged / planned_reserved 128 / design_evaluations（仅准入标签）/ cached_reads（0）。
- 失败 case objective=null，不重跑；任何 REFUSED、连续 2 非 SOLVED、超时、账本不守恒、哈希不符即 STOP。
- stage2 不可用率：STOP 只用同一 mini-batch 作分母（权威）；分子=该批已完成 stage1 但无法生成或运行 stage2 的 case 数；>20% 即 STOP。累计率为披露值，不触发 STOP。

## 6. 已知风险与披露
- M140 近窗口边缘：按 NULL_STAGE1_NOT_BRACKETED 记 null，不扩窗、不重跑；预期 null 上界 16 已预先声明。
- stage2 13 点仍可能无原始行命中；记 null，不放宽、不插值。
- 同机存储；异机备份 Owner 豁免（WAIVER-OFFMACHINE-BACKUP-20261118），同机恢复不是独立故障域备份。
- 旧 G1 8 条标签不并入 G2；G2 只用本批新标签做后续 MAML。
- 本批不是物理验证，VSPAERO_INTERNAL_ONLY；fuel_burn_kg=null。

## 7. 请 A5 判断
是否批准 首批 ≤24 starts（在 128 starts 计划内），以及是否认可两段式 alpha 与仅原始行准入。请给 G2_APPROVE / G2_CHANGES_REQUIRED / G2_REJECT，并列出必须修复项。

<!-- SELF_HASH -->
## 8. 自哈希
dossier_payload_sha256: 68c5655ec1bd0ed6d0ab72f6123473a016a8e33c9676588208dafa5dd604702a
计算范围：仅 <!-- SELF_HASH --> 之前的全部字节；标记行之后不参与。