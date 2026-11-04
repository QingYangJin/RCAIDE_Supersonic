# Lead 打包说明（P4-M2 正式离线 run）

- 授权依据：Issue #5 / D-P4-001（P4-META-DEV，仅合成解析任务，物理调用硬性 0）。本 run 无任何求解器调用。
- 启动前门禁：M0 设计 v1.4a @36d5891 经 A5 task-80 APPROVE_FOR_M2、task-83 APPROVE_TO_START_M2；A3 task-84 隔离 PASS 17/17。
- 运行参数：五臂 × 5 seeds（actual_seeds=[0,1,2,3,4]）× 预算 64 次真实（合成）评估 × K∈{0,1,5,10}；determinism_reruns=3；physical_call_count=0。
- 推断限制：按 M0 v1.4 §10.1，预注册终点统计/图/回执/结论只引用可识别臂 {OPT-BO-rand, OPT-BO-MAML-init, OPT-DE}；OPT-BO-pretrain/OPT-BO-MAML 标 CLONE_OF_OPT-BO-rand，仅描述性记录。
- 大文件归档（仓库外，D:/RCAIDE/outputs/.../raw_artifacts/，sha256 见 data_manifest.json 的 external_artifacts 段）：evaluations.jsonl、archive/*/observations.jsonl、metrics/optimization_history.csv。
- 图表：figures/ 由 A2 用 make_p4_m4_figures.py 从 CSV 重画（fig1/2/3/5 GENERATED，fig4 NOT_RUN 归 Issue #4 D-12D-004）。
- data_manifest.json 由 scripts/make_m2_manifest.py 生成；文本按 canonical LF 哈希，二进制按 raw 字节哈希，外部大文件单独列示且不计入 file_count/total_bytes。
