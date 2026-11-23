# P2 A5 审查卷宗（协议与代码）

性质：Issue #14 P2 指令（Owner comment 7103901506）下的真实补采批次 + 四臂元学习协议预注册。
本文件只请求对“协议与代码”的审查；GO 记录在审查 PASS 后单独签发。

## 0. 文件身份与绑定（可核验哈希）

- 预注册文件：p2_preregistration.json，sha256 = ba2eeb884bd994837181aadd115582d4d87bf51ae45927b5eb07a9984d4dc7f3。
- 补采计划：p2_supplement_plan.json，sha256 = 208edee0dbc95e27f140ca4211138ee465120b7082c0b4720d893db477179411。
- 数据清单：p2_dataset/p2_dataset.json，sha256 = 848652cf08c715416bad4f378d8f05b4ef51ce711848ffdfcca2de1e7509b5fe。
- 本卷宗无法在正文中包含自身哈希（自引用矛盾）。评审脚本在发送前计算本卷宗字节的 sha256，并以 DOSSIER_BYTE_IDENTITY 行放在送审内容头部，评审结束后写入 a5_review/verdict.json 的 dossier_sha256，GO 记录再复述该值；因此送审字节在评审时即可被绑定。
## 1. 预算与边界

- 补采硬上限：16 次真实 solver 启动（计划正好 16 次），内部迎角工况上限 48（16 starts × 3 点），每 start 3 点，并行 1，每 start 600 s，0 重试，墙钟 9600 s（16×600 s 最坏情况），每 8 starts 上传并回读。
- 复用已有 25 条已准入真实标签，仅对缺口补采；不寻找/恢复历史丢失数据；不启动任何其他物理。
- 训练不消耗 solver 启动；P3 在线优化未授权。

## 2. 八任务数据矩阵（补采前 → 补采后；zeros 明示）

补采理由：只有缺少 K=3 支持槽或完全没有数据的任务才补。M160、M200 已有 3 个独立 support，本批 0 次启动；M140/M220/M260 完全没有标签，必须同时补 3 个 support 和 1 个独立 query，否则这些任务没有任何独立 query 可评分。所有 query 使用 d03 这一独立几何，绝不充当 support。

| 任务 | split | 补采前 support/query | 本批 starts | 补采后 support/query |
| --- | --- | --- | --- | --- |
| P2-CANON-M140 | train | 0 / 0 | 4 | 3 / 1 |
| P2-CANON-M160 | train | 3 / 2 | 0 | 3 / 2 |
| P2-CANON-M180 | val | 2 / 3 | 1 | 3 / 3 |
| P2-CANON-M200 | train | 3 / 3 | 0 | 3 / 3 |
| P2-CANON-M202 | train | 2 / 3 | 1 | 3 / 3 |
| P2-CANON-M220 | val | 0 / 0 | 4 | 3 / 1 |
| P2-CANON-M240 | test | 1 / 3 | 2 | 3 / 3 |
| P2-CANON-M260 | test | 0 / 0 | 4 | 3 / 1 |

合计复用 25 条已准入标签 + 本批最多 16 次启动（13 support、3 query）。
K=5 = NOT_ELIGIBLE（冻结协议只有 d00–d03 四个独立支持槽，禁止用 query 充数）。

## 3. 补采矩阵（16 starts，零物理 bracket 全部来自 G2 stage-1 polar）

| 任务 | design | partition | cl_target | alpha 三点 | bracket |
| --- | --- | --- | --- | --- | --- |
| P2-CANON-M140 | d00 | support | 0.378361 | 9.541121, 9.545121, 9.549121 | [9.52, 9.76] |
| P2-CANON-M140 | d01 | support | 0.374615 | 9.440008, 9.444008, 9.448008 | [9.28, 9.52] |
| P2-CANON-M140 | d02 | support | 0.378361 | 9.488677, 9.492677, 9.496677 | [9.28, 9.52] |
| P2-CANON-M140 | d03 | query | 0.382183 | 9.644687, 9.648687, 9.652687 | [9.52, 9.76] |
| P2-CANON-M220 | d00 | support | 0.153221 | 4.580209, 4.584209, 4.588209 | [4.48, 4.72] |
| P2-CANON-M220 | d01 | support | 0.151704 | 4.534082, 4.538082, 4.542082 | [4.48, 4.72] |
| P2-CANON-M220 | d02 | support | 0.153221 | 4.748850, 4.752850, 4.756850 | [4.72, 4.96] |
| P2-CANON-M220 | d03 | query | 0.154768 | 4.627268, 4.631268, 4.635268 | [4.48, 4.72] |
| P2-CANON-M260 | d00 | support | 0.109702 | 4.174299, 4.178299, 4.182299 | [4.00, 4.24] |
| P2-CANON-M260 | d01 | support | 0.108616 | 4.132390, 4.136390, 4.140390 | [4.00, 4.24] |
| P2-CANON-M260 | d02 | support | 0.109702 | 4.198574, 4.202574, 4.206574 | [4.00, 4.24] |
| P2-CANON-M260 | d03 | query | 0.110810 | 4.217055, 4.221055, 4.225055 | [4.00, 4.24] |
| P2-CANON-M240 | d01 | support | 0.127473 | 4.389310, 4.393310, 4.397310 | [4.24, 4.48] |
| P2-CANON-M240 | d03 | support | 0.130048 | 4.480000, 4.484000, 4.488000 | [4.48, 4.72] |
| P2-CANON-M202 | d02 | support | 0.181744 | 5.342636, 5.346636, 5.350636 | [5.20, 5.44] |
| P2-CANON-M180 | d02 | support | 0.228885 | 6.201040, 6.205040, 6.209040 | [6.16, 6.40] |

## 3b. 复用标签的来源、别名与去重规则（P2_DATASET_MATRIX 证据）

别名表（canonical ← 历史 task_id，显式、写死在脚本，不做字符串推断）：

- P2-CANON-M160 ← DREAL003-G2-M160、concorde-real-M160
- P2-CANON-M180 ← DREAL003-G1-M180、DREAL003-G2-M180、concorde-real-M180
- P2-CANON-M200 ← DREAL003-G2-M200
- P2-CANON-M202 ← DREAL003-G1-M202、DREAL003-G2-M202、concorde-fixed-cruise-dreal001-real-v1
- P2-CANON-M240 ← DREAL003-G1-M240、concorde-real-M240

去重与冲突规则：

- 以 (canonical task, design_sha256) 为键去重，同一设计只保留一条。
- 同一键出现于不同批次时，批次优先级 P2(4) > G2(3) > G1(2) > R2(1)，高优先级整条保留。
- 同优先级在同一设计上出现 support/query 冲突时，两条都排除并在 excluded 中记录原因，绝不自动挑选。
- 每条复用证书都在原 case 目录就地重放 admit_real_manifest，只读历史文件、不启动求解器，证书 q_pa 必须与 canonical TaskSpec 动压一致（相对 1e-9）。

逐任务/逐设计来源（复用标签，补采前）：

| canonical 任务 | design_id | partition | 历史 task_id | 来源批次 | 来源 case | polar sha256 |
| --- | --- | --- | --- | --- | --- | --- |
| P2-CANON-M160 | 937aa7c9c789 | support | concorde-real-M160 | DRECOVER001-R2-20261120-01 | m160-d00-support-r1 | 0f32d5f12ed2d87a |
| P2-CANON-M180 | 937aa7c9c789 | support | concorde-real-M180 | DRECOVER001-R2-20261120-01 | m180-d00-support-r1 | 59f61032299dc927 |
| P2-CANON-M240 | 408cafa19c7e | query | concorde-real-M240 | DRECOVER001-R2-20261120-01 | m240-d02-query-r1 | e02f4f3a4e5db5ea |
| P2-CANON-M240 | 937aa7c9c789 | support | DREAL003-G1-M240 | DRECOVER001-G1-20261121-01 | g1-m240-d00-support | 6235d417f16f003c |
| P2-CANON-M240 | f8626bb58503 | query | DREAL003-G1-M240 | DRECOVER001-G1-20261121-01 | g1-m240-d04-query | e47bded04037b9b9 |
| P2-CANON-M240 | a6baa19d0129 | query | DREAL003-G1-M240 | DRECOVER001-G1-20261121-01 | g1-m240-d05-query | 3c31851c73bcfc10 |
| P2-CANON-M160 | 3de72a4bb698 | support | DREAL003-G2-M160 | DRECOVER001-G2-20261121-01 | g2-m160-d01-support-s2 | 4b3537299d966fcd |
| P2-CANON-M160 | cab5c852e3db | support | DREAL003-G2-M160 | DRECOVER001-G2-20261121-01 | g2-m160-d03-support-s2 | c9b48ed7430b880f |
| P2-CANON-M160 | a6baa19d0129 | query | DREAL003-G2-M160 | DRECOVER001-G2-20261121-01 | g2-m160-d05-query-s2 | 86d8407549ae23d6 |
| P2-CANON-M160 | 3e904d57780d | query | DREAL003-G2-M160 | DRECOVER001-G2-20261121-01 | g2-m160-d06-query-s2 | f31cdf74872405c8 |
| P2-CANON-M180 | 3de72a4bb698 | support | DREAL003-G2-M180 | DRECOVER001-G2-20261121-01 | g2-m180-d01-support-s2 | 2bd393784296b43c |
| P2-CANON-M180 | f8626bb58503 | query | DREAL003-G2-M180 | DRECOVER001-G2-20261121-01 | g2-m180-d04-query-s2 | 38c41b7c31d6b39a |
| P2-CANON-M180 | a6baa19d0129 | query | DREAL003-G2-M180 | DRECOVER001-G2-20261121-01 | g2-m180-d05-query-s2 | 996331ad8e05693e |
| P2-CANON-M180 | 3e904d57780d | query | DREAL003-G2-M180 | DRECOVER001-G2-20261121-01 | g2-m180-d06-query-s2 | 03bd406dedb239b8 |
| P2-CANON-M200 | 3de72a4bb698 | support | DREAL003-G2-M200 | DRECOVER001-G2-20261121-01 | g2-m200-d01-support-s2 | 59660419a5df9dc2 |
| P2-CANON-M200 | 408cafa19c7e | support | DREAL003-G2-M200 | DRECOVER001-G2-20261121-01 | g2-m200-d02-support-s2 | 77e4ec59450294f1 |
| P2-CANON-M200 | cab5c852e3db | support | DREAL003-G2-M200 | DRECOVER001-G2-20261121-01 | g2-m200-d03-support-s2 | 83760df1e6f2c1be |
| P2-CANON-M200 | f8626bb58503 | query | DREAL003-G2-M200 | DRECOVER001-G2-20261121-01 | g2-m200-d04-query-s2 | 58b979e2e4929ce9 |
| P2-CANON-M200 | a6baa19d0129 | query | DREAL003-G2-M200 | DRECOVER001-G2-20261121-01 | g2-m200-d05-query-s2 | 8dbd0815ea469b95 |
| P2-CANON-M200 | 3e904d57780d | query | DREAL003-G2-M200 | DRECOVER001-G2-20261121-01 | g2-m200-d06-query-s2 | 9d53feb5e95de7b7 |
| P2-CANON-M202 | 937aa7c9c789 | support | DREAL003-G2-M202 | DRECOVER001-G2-20261121-01 | g2-m202-d00-support-s2 | 326f6bc621d0c75c |
| P2-CANON-M202 | 3de72a4bb698 | support | DREAL003-G2-M202 | DRECOVER001-G2-20261121-01 | g2-m202-d01-support-s2 | d5aa72ddf8138c27 |
| P2-CANON-M202 | f8626bb58503 | query | DREAL003-G2-M202 | DRECOVER001-G2-20261121-01 | g2-m202-d04-query-s2 | a1b0eb317848c6d1 |
| P2-CANON-M202 | a6baa19d0129 | query | DREAL003-G2-M202 | DRECOVER001-G2-20261121-01 | g2-m202-d05-query-s2 | e7a6c312d0c238e1 |
| P2-CANON-M202 | 3e904d57780d | query | DREAL003-G2-M202 | DRECOVER001-G2-20261121-01 | g2-m202-d06-query-s2 | 844eea422b2249a0 |

排除记录共 23 条，原因分布：
- design appears in both support and query at the same priority：16
- duplicate design within canonical task：7

## 3c. 代码常量与证据绑定（P2_CAPS / P2_BRACKET_PROVENANCE 证据）

补采驱动 scripts/p2_supplement.py 的硬常量（该文件 sha256 已写入预注册 source_code_sha256，运行前 gate_check 会比对，任何漂移都拒绝启动）：

MAX_STARTS = 16；MAX_INTERNAL = 48；WALL_MAX = 9600.0；UPLOAD_EVERY = 8（每 8 starts 上传并回读）；
retries: 0（代码中不存在重试路径）；parallelism: 1（单进程顺序循环）；timeout_s_per_start: 600。

冲突规则在 scripts/p2_data.py（优先级 P2(4)>G2(3)>G1(2)>R2(1)，同优先级冲突两条都排除）。

16 个 bracket 的零物理来源（原始 G2 stage-1 polar 文件、SHA256、夹住 cl_target 的两行）：

| 任务 | design | polar sha256 | 原始极曲线两行 (alpha, CL) |
| --- | --- | --- | --- |
| P2-CANON-M140 | d00 | 6bebbae3682a296d... | (9.52, 0.377434) / (9.76, 0.386295) |
| P2-CANON-M140 | d01 | 3f771f637ced430c... | (9.28, 0.368527) / (9.52, 0.377436) |
| P2-CANON-M140 | d02 | f8ac2ff378fc7270... | (9.28, 0.370426) / (9.52, 0.379381) |
| P2-CANON-M140 | d03 | c635407b8627b60c... | (9.52, 0.377431) / (9.76, 0.386293) |
| P2-CANON-M220 | d00 | 4f754ae751684e61... | (4.48, 0.149791) / (4.72, 0.157690) |
| P2-CANON-M220 | d01 | 6f263df0955c669c... | (4.48, 0.149792) / (4.72, 0.157691) |
| P2-CANON-M220 | d02 | 0255508da46b3705... | (4.72, 0.152180) / (4.96, 0.159783) |
| P2-CANON-M220 | d03 | 957ae25bfdc28c29... | (4.48, 0.149790) / (4.72, 0.157688) |
| P2-CANON-M260 | d00 | c2bfdbd02e383d20... | (4.00, 0.105078) / (4.24, 0.111303) |
| P2-CANON-M260 | d01 | ffb0db92568af6b3... | (4.00, 0.105078) / (4.24, 0.111304) |
| P2-CANON-M260 | d02 | af1350f6300d3648... | (4.00, 0.104478) / (4.24, 0.110668) |
| P2-CANON-M260 | d03 | 38c3116308d17032... | (4.00, 0.105077) / (4.24, 0.111302) |
| P2-CANON-M240 | d01 | 1de4e396ec1c429f... | (4.24, 0.123085) / (4.48, 0.129954) |
| P2-CANON-M240 | d03 | d36470474a30b291... | (4.48, 0.129952) / (4.72, 0.136805) |
| P2-CANON-M202 | d02 | cd59696806af0f46... | (5.20, 0.176861) / (5.44, 0.184853) |
| P2-CANON-M180 | d02 | 0223628bbdd9de4f... | (6.16, 0.227272) / (6.40, 0.235868) |

完整 polar 路径与 SHA256 见 p2_supplement_plan.json 的 stage1_case_dir / stage1_polar / stage1_polar_sha256 字段；生成脚本 scripts/p2_plan.py 的 sha256 也在预注册中。

## 4. 准入容差

- 维持 1e-3 相对升力容差，不放宽；插值值不得写成原始极曲线行；只用原始 polar 行计算 D_i_N=q·Sref·C_Di。
- 每条新标签须有独立本地重实现审计（非人类、非 A5）与 RealAdmissionManifest 逐文件哈希绑定。

## 5. 四臂训练协议

- 臂：RANDOM_INIT、POOLED_PRETRAIN、TASK_COND_PRETRAIN、FOMAML；K=1 与 K=3；种子 7/19/43。
- 归一化只用训练任务；验证任务选超参/早停；测试任务只在选参后打分一次。
- FOMAML：一阶，inner_lr 0.05，inner_steps 5，outer_lr 0.01，tasks_per_batch 2，max_steps 60，CPU float64。
- 主要对照是 POOLED_PRETRAIN（同输入预训练+微调），条件模型单列报告。
- 交付：逐任务 MAE/RMSE(N)、配对差、训练曲线 CSV、候选排序离线诊断、checkpoint 与归一化参数。

## 6. 零物理声明

- 本卷宗与预注册不启动任何 solver。只有 A5 给出 P2_PROTOCOL_AND_CODE_REVIEW_PASS 且 GO 记录绑定本卷宗与预注册哈希后，才可执行补采。
- 补采之外的真实训练仍为 0 次物理；训练只读已准入标签。

## 7. A5 检查点（必须逐项给出）

— P2_CAPS：16 starts / 48 internal / 600 s / 0 retry / 每 8 starts 回读，是否写入代码常量与预注册。
- P2_DATASET_MATRIX：25 条复用标签的来源、别名合并与去重规则是否可复核。
- P2_BRACKET_PROVENANCE：16 个 bracket 是否全部来自 G2 stage-1 raw polar 且未启动求解器。
- P2_ALPHA_PROTOCOL：每 start 3 点、探测点间距 0.004°（总跨度 0.008°）、中心按 bracket 夹紧、端点绝不超出原始 bracket 与 alpha 允许窗口。
- P2_ACCOUNTING_CONTROLS：逐项列出——①只在真实 run_case 返回 physical_solver_starts=1 时计数；②internal 数从原始 polar 行数回填，缺失记 UNKNOWN 而非 0；③每 8 starts 必须完成上传并远端回读，失败即 STOP；④0 重试、并行 1；⑤2 连败/REFUSED/EXCEPTION/会计不守恒即 STOP；⑥所有 null 行保留 failure_kind，不重复计样。
- P2_ADMISSION：1e-3 未放宽、原始行判据、证书逐文件哈希。
- P2_TRAINING_PROTOCOL：四臂、K=1/3、种子、只用 train 归一化、只用 val 选参、query 独立。
- P2_ZERO_PHYSICAL_UNTIL_GO。

## 8. 已知披露

- 标签同机保存、未经异机认证、无风洞/物理验证；fuel_burn_kg=null；LF-M2.02 NOT_VALIDATED。
- 旧批次 task_id 通过显式别名表合并，历史文件不修改。
- 数据不足时报告短缺矩阵，不合成、不插值、不复用 query 充当 support。
