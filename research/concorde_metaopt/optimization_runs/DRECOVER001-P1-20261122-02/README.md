# DRECOVER001-P1-20261122-02（P1 自适应迎角小批真实试验）

性质：Issue #14 P1 pilot，不是训练批次，不据此训练正式跨任务 MAML。

## 预算与记账

- 真实 design starts：6 / 上限 12（每设计 <=3）；完成求解 6；重试 0；并行 1。
- 内部 alpha solver cases：18（每 start 3 个局部 alpha 点），上限 36；相对固定 49 点/设计扫描节省 178 个内部 case。
- 唯一真实准入标签：5 条（另有 6 行已准入；p1-m202-d00-r1 重复启动两次，标签按证书去重）。
- 行级有效率：5/6 = 83.3%（目标 70%；样本过小 UNDERPOWERED，不宣称目标稳健达成）。
- 每设计内部 case 中位数 3.0，总墙钟 12.566 秒。

## 标签（真实 raw 行，rel CL <= 1e-3，未放宽）

- d00：p1-m202-d00-r1，D_i_N=121438.589 N，CL=0.181744720773，alpha=5.181341，rel=4.42e-06
- d00：p1-m202-d00-r2，D_i_N=121438.542 N，CL=0.181744686378，alpha=5.18134，rel=4.23e-06
- d01：p1-m202-d01-r1，D_i_N=120206.230 N，CL=0.179946783992，alpha=5.129049，rel=1.28e-05
- d04：p1-m202-d04-r1，D_i_N=121679.606 N，CL=0.18174429066，alpha=5.191543，rel=2.05e-06
- d07：p1-m202-d07-r1，D_i_N=121438.589 N，CL=0.181744720773，alpha=5.181341，rel=4.42e-06

## 边界

- 同机保存，未做异机认证；LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED。
- 未做风洞/物理验证；fuel_burn_kg=null；LF-M2.02=NOT_VALIDATED。
- 只报告翼面诱导阻力 D_i_N = q * Sref * CDi，不称整机总阻力或真实油耗。

## 文件

- raw_cases/：每个 case 的 .vspgeom/.vspaero/.polar/.history/.adb、deck、plan/approval/task_spec、审计与准入证书、stdout/stderr。
- tables/：all_evaluations.csv、admitted_labels.csv、failed_or_null.csv、alpha_refinement_history.csv、actual_solver_ledger.csv、optimization_history.csv。
- figures/：中文 PNG 4 张 + figure_data.csv。
- metadata/、run_config.json、task_family_split.json、geometry_freeze.json、p1_result.json、p1_accounting.json、p1_metrics.json。
