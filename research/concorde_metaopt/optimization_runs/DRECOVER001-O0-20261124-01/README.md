# DRECOVER001-O0-20261124-01（O0 真实气动反馈优化）

O0 是真实闭环：全部 Di 来自真实 VSPAERO 原始极曲线行，physical starts 记录见 metadata 与 raw_cases。

本目录由 scripts/o0_upload.py 从运行根 D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01 打包生成，
逐文件 sha256 见 data_manifest.json 与 SHA256SUMS.txt。

目录约定：inputs/ 预注册与授权记录；raw_cases/ 每个 case 的原始求解器产物与准入记录；
tables/ 汇总表；figures/ 由原始数据绘制的图（绘图脚本见 scripts/）；
metadata/ 运行记录与资源采样；training/ 训练产物；audits/ A5 审查、绑定校验与 GO 历史。
final_aircraft/ 仅 O0 与 O1 有：交付给 OpenVSP 的可打开构型、STL/STEP 与前后对比图表。
