# D-REAL-001 P0 整改与 P1 v1.3 预检/plan 回执（A1 / a1-aviation-f）

- 生成时间：2026-11-10T10:50Z（CST 18:50）
- 工作树：D:\RCAIDE\dnext001\wt-real-a1-geometry-solver
- 分支：research/dreal001-a1-geometry-solver（未 push）
- 本轮提交：`315ba11`（P0 整改 A1–A3 + P1 v1.3 预检/plan）、`14d45ff`（证据目录字节原样保存）
- 真实物理求解启动数：**0**（physical_solver_starts=0；仅 StopBeforeRun=1 零物理预检）
- 依据：Lead 决策 L-01..L-07（D:\RCAIDE\dnext001\wt-real-lead\docs\planning\dreal001_lead_decisions_20261110.md，commit 3624db7）与 m00825 整改清单

## 1. 交付内容

| 类别 | 文件 | 说明 |
| --- | --- | --- |
| 设计身份 | research/concorde_metaopt/dreal001/geometry/design_identity.py | 治理 v3 §3：canonical x12 用 %.12g，design_hash=sha256(...)[:16]；纯函数、无循环依赖 |
| 评估重序列化 | .../evaluation_reserialize.py | design_hash 16 hex；geometry_sha256 64 hex 保留；cm_trimming 改正向 cm_trimming_enabled + cm_trimming_policy |
| 求解记录 | .../solver_runner.py | 从 case_inputs.json 取 x12 计算 design_hash；同步 cm 正向命名 |
| 收尾 | .../run_closeout.py | task_spec_hash_scope（canonical / raw bytes / git blob 三口径 + 复现命令）；correction_001 补 created_by/created_at_utc/issue/correction_type/run_id |
| 预检 | .../p1_preflight.py | 8 唯一配置 StopBeforeRun=1；contract_digest；mesh_observed；禁 CLI 列表扫描 |
| plan | .../p1_plan.py | schema dreal001.solver_plan.v1，status=PENDING_APPROVAL |
| 冻结 | research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml、aircraft/design_space.py、.../design_space_freeze.json | L-01/L-02/L-03 冻结，provisional 命中 0 |
| 预注册 | .../P1_PREREGISTRATION_v1.md | v1.3 + v1.3.1 预检身份可复现性披露 |
| 闭合文档 | docs/planning/dreal001_p0_closure_20261110.md | 修正 25/26、189/196；新增 §10 resolved-by-decision、§11 预检身份可复现性 |
| 测试 | tests/test_dreal001_r1_preflight.py、test_dreal001_r1_p1_plan.py、test_dreal001_r1_identity.py、test_design_space_12d.py | 新增 25 个用例 |
| 预检证据 | .../runs/DREAL001-P1-20261110-01/preflight/CFG-01..CFG-08/ | 8 配置 preflight.json + 四件套 + 网格 csv；index.json |

## 2. 关键哈希（原始字节口径）

- plan.json：65409 B，sha256 = `0cbd8d93ba8e826790b2d5cf91d80570ab6daedb9ae0d9a1bf02f257c9e39475`（磁盘字节 == git blob 字节，commit 315ba11）
- preflight/index.json：sha256 = `585cd463ae6e89046fc34bec47a5ac86524f431695d31271ca7274e8316f81c6`，8 配置 all_ok=true
- 预注册 v1.3：sha256 = `f28c24c6917a815858e7a1b57717f420416a602e57870b4ccdd6a1de7d076ed0`
- 冻结设计空间 config：sha256 = `56503a5512bb9d75656d1a0913936fc7505903ae5b46f1e0fa477ef3165feef7`；design_space_freeze.json `6cb7647f90545d1e93060155c92d5a1f485d5b56345211dee533f43115f857a5`
- baseline design_hash = `8bd5a6c7c8311938`
- 8 配置 contract_digest（前 16 位）：CFG-01 eb0384eba34b9476、CFG-02 2e0c934a598c7227、CFG-03 68b631c62e65d07a、CFG-04 579e794b1c1c3631、CFG-05 e7aae821523d01d2、CFG-06 195e6749570f0bc0、CFG-07 b46f52e35d2bec4c、CFG-08 1a0cc956aadeafc5
- plan 预算：starts 25 / max 26、internal 189 / max 196、case_count 25；approval{approved_by:null, window_token:null, status:"NOT_APPROVED"}；窗口请求 2026-11-10T18:45–21:30+08:00

## 3. P0 整改对照

- **P0-B1（设计空间冻结）**：L-01 Sref=358.25 m2（326.5 不采用，仅留追溯）；L-02 垂尾半展按 AR=0.74 派生 5.009331 m（上游 6.0 不用于 VLM）；L-03 yaml frozen:true、bounds_status=frozen_for_dreal001_20261110、freeze_note；design_space.py 要求冻结空间必须写 frozen_for_ 前缀与 freeze_note，provisional 空间仍拒绝以 frozen 加载。evidence：design_space_freeze.json frozen_flag_in_config=true、provisional 0 命中、sampling_violations=0。**冻结的是几何合同，不是气动**：VSPAERO 内部系数仍 VSPAERO_INTERNAL_ONLY，LF-M2.02 NOT_VALIDATED、BODY-CORR BLOCKED、HF-M2.02 PARTIAL；X_cg=16.821978259514246 m 仍是机翼 AC，几何全机 CG=28.287395109126685 m（差 11.4654 m）；136000 kg 是巡航进入质量、184880 kg 是几何 MTOW 推算值，禁止归一化互证。
- **P0-F-02（correction_001 字段）**：补 created_by/created_at_utc/issue/correction_type/run_id；superseded 两条 retention_status 分别为 NOT_RETAINED（16075 B，从未提交、盘上无副本，SHA 仅追溯）与 RETAINED_IN_GIT_HISTORY（21537 B，可从 b5dcbbc 精确恢复）。
- **TaskSpec hash_scope**：canonical_json_sha256=dca981e2… / raw_config_sha256=028086a5…（6144 B）/ git blob 3f831d4b…，三者口径与复现命令写入 run_config.json 的 reference_quantities.task_spec_hash_scope，并声明 raw 与 blob 不可直接比较（CRLF/LF 同一文本的不同字节流）。
- **design_hash**：治理 §3 口径（12 维按冻结顺序、%.12g、无空白）sha256 前 16 位；geometry_sha256 仍为 .vspgeom 的 64 hex，两者并存不混用。
- **cm_trimming 正向命名**：全部改为 cm_trimming_enabled=false + cm_trimming_policy=CM_NOT_TRIMMED_DIAGNOSTIC_ONLY。

## 4. P1 v1.3 预注册与预检

- 25 starts / max 26；189 internal / max 196；25×7+14 与逐 case 交叉核对一致；refine 每设计最多 2 次尝试、全批最多 1 次启动（7 internal），仍 >1e-3 记 LIFT_MATCH_FAILED 继续，S5 只在 actual > max 时停批。
- thick 仅负控（P1-04 12x25、P1-04b 24x49、P1-04c 48x97），thin 为生产面；E1/E2 措辞已按 L-04 统一。
- X4：L-05 豁免 1.8/2.0/2.2（仅趋势，E4 标源 case，禁 CLI -mach）。
- 8 个唯一配置全部 StopBeforeRun=1 零物理预检通过，all_ok=true，physical_solver_starts=0；argv 仅 `-omp 1 concorde_baseline`，无 -fs/-mach/-alpha/-beta。

## 5. 预检身份可复现性披露（v1.3.1，零物理）

四件套 input SHA **不可复现**，只作 as-prepared 证据：OpenVSP 每次保存写入随机 10 字符对象 ID；thin-geometry 网格器非字节确定（同一 CFG-01 合同两次预检得到 543/472 与 483/418 节点/单元）。可复现身份改为 contract_digest（仅语义合同：参考量、alpha/Mach 列表、GeomSet、Tess_U/Tess_W、NumWakeNodes、RefFlag/NCPU/StopBeforeRun、求解器 SHA256、冻结 config SHA256、12 基线值 %.12g），两次实测一致 eb0384eb…。每个 start 在自身 case 记录中钉住实际网格；S3 重复性失败先比对网格再归因求解器数值。

## 6. 测试

```
Set-Location D:\RCAIDE\dnext001\wt-real-a1-geometry-solver
& D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/tests -q -k 'dreal001 or geometry or design_space' -p no:cacheprovider
```

结果：**183 passed, 1680 deselected, 1 warning in 7.45s**（warning 为 reports/figures.py:92 的 xlim 提示，与本次无关）。其中本轮新增 25 个用例（预检 18、plan 7、身份/哈希口径 7 中的新增部分按文件计）。

## 7. 未完成项与风险

1. **P1 窗口未批准**：plan.json status=PENDING_APPROVAL、approval.json 不存在；真实启动数 0，需 Lead 写 approval.json 并提供窗口 token。
2. **网格非字节确定**：即便合同相同，面板拓扑可能变化；S3 若触发须先比对网格，结论表述需保留该不确定性。
3. **预检四件套 SHA 不可复现**：批准依据必须是 contract_digest + case matrix，不得以 input_set_sha256 作复现身份。
4. **A5 复核未完成**：P0_FAIL / P1 CHANGES_REQUESTED 的整改已按清单落地，但 PASS 需 A5 独立签署，本轮不自行宣称。
5. **.gitattributes 覆盖修正**：新增 research/concorde_metaopt/dreal001/** -text，避免 core.autocrlf=true 的 checkout 破坏 SHA 链。
6. layer_claim：fuel_burn_kg 恒为 null，本轮最多 SOLVER_LOOP_VERIFIED，不得宣称 INTERNAL_AERO_OPTIMIZATION_GAIN 或 EXTERNAL_PHYSICS_SUPPORTED。
