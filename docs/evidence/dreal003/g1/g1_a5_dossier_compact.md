# A5 预审 · Issue #13 G1（精简 dossier）

## 授权
Owner m07992：“继续执行，把G1阶段也完成，批准实际物理计算”。上限 24 starts，parallel=1，0 retry，单 case 1200s，每 mini-batch ≤8 starts/≤60min。当前 G1 真实 starts=0。

## 代码状态
分支 research/dreal003-expanded-aero-meta-20261120，base 35d1f115637c3aa57521eec8458cef706944c4af。
solver_runner.py SHA256 cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3
test_recovery_solver_runner.py SHA256 7f29d21cc45cf7deb0469f6504145bb8065cc0d6f22eb59a4e934207a8481da1
定向测试 5 passed。该 solver_runner SHA 与 G0 A5 已审 SHA 相同；A1 修复内容为 per-case 读取 task_spec/case_inputs 的 Mach/Rho/Vinf/q/Sref/lift，并校验 q=0.5ρV²，build_evaluation 使用 per-case 流场。

## G1 控制
- 4 任务：M160 train、M180 val、M202 train、M240 test；每任务 6 设计（d00 baseline、d01 area+1%、d02 sweep+0.5、d03 area-1%、d04 sweep-0.5、d05 vertical-tail+2%），3 support + 3 query。
- 每 case 17 个 alpha 点，步长 0.03°，围绕升力反算中心 ±0.24°；升力容差 1e-3。
- 每 case plan/approval max_starts=1；全局 24 由 runner 强制。24 个 case 已零物理生成 plan/approval/task_spec/case_inputs/vspgeom/vspaero；无 case_result、无 solver_attempts、无 polar。
- 三个 mini-batch 各 8 starts；每批后上传原始文件/CSV/PNG/账本并从远端回读 SHA256SUMS，成功后才下一批。
- 停止：start 被会计/窗口/计划拒绝；超时或缺进程结果；连续两个非 SOLVED；账本不守恒；上传/回读不一致。失败 case objective=null，不重跑。
- 只有 polar 实际行满足 1e-3 升力容差才生成 admission certificate；不得用 G0 旧标签替代，不得 mock/replay。
- 本预审只放行 G1 ≤24 starts，不构成 G2/G3/R2 或人类签字。

## 预注册摘要
```json
{
 "authorization_id": "AUTH-DREAL003-G1-20261121-01",
 "run_id": "DRECOVER001-G1-20261121-01",
 "batch_id": "DRECOVER001-G1-20261121-01-B01",
 "planned_starts": 24,
 "mini_batch_max_starts": 8,
 "case_timeout_s": 1200,
 "retries": 0,
 "target_valid_label_rate": 0.7,
 "status": "PRE_REGISTERED_PENDING_A5_AND_GO"
}
```

## 24 case 精确清单（plan/geom SHA）
```
g1-m160-d00-support | train/support | d00 | M1.6 | plan 29eca877ed13d0d176008247024f49ea682a747f0adcca692ac4e7ed9e216f43 | geom f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34
g1-m160-d01-support | train/support | d01 | M1.6 | plan 0d7e4c78c23fe95ceae3124fe0dfc4f86670fb590b8539c963b0703b203a6df4 | geom 31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9
g1-m160-d02-support | train/support | d02 | M1.6 | plan 8c547c2d93f091a6e7c90e29fbcedc4ea84910e01aca77a380b346584291c669 | geom 6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05
g1-m160-d03-query | train/query | d03 | M1.6 | plan 80bd4b689059e6ebbdbf4b48e383f4aed7fcf8ac4031c17a161b5687943e790f | geom 78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12
g1-m160-d04-query | train/query | d04 | M1.6 | plan a6bf2a16643e3bfdfe868aefef48c345c581d2de21a5fdf81c0483ef75af2972 | geom 2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2
g1-m160-d05-query | train/query | d05 | M1.6 | plan cbd9d2830fb644655e600768da5e92eb170a498ca69831dfd26bac225e8abfeb | geom 0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55
g1-m180-d00-support | val/support | d00 | M1.8 | plan 7be03707ac0b4f82b1c3ca51e0733ed02381b715ac618cc6158b85350275004e | geom f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34
g1-m180-d01-support | val/support | d01 | M1.8 | plan b5d41fcec85b694bf13c85dd8cd597bb4fcf8ff16fa72b022c600eaf8cf469cf | geom 31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9
g1-m180-d02-support | val/support | d02 | M1.8 | plan 8d5dfb12085dd0a47e57a85b41b202f1d121c994f684303799bd1a6c0ef4f83f | geom 6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05
g1-m180-d03-query | val/query | d03 | M1.8 | plan c70df05b770ac912fb4a900f8cf1fde5ffb36e6ba1600041e204aa6f7665ed18 | geom 78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12
g1-m180-d04-query | val/query | d04 | M1.8 | plan ff67356f70b2ca0821e6c2b13195dc2249574409912553f9291d6986967de589 | geom 2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2
g1-m180-d05-query | val/query | d05 | M1.8 | plan 6057afbb3b6fc2b06675b7a797e82af079abd7e92c28eab187b3f1396e0deb38 | geom 0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55
g1-m202-d00-support | train/support | d00 | M2.02 | plan 13e24b464ea773e542bd97e6f8827a881f48879d765636a68e20b81baadcb007 | geom f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34
g1-m202-d01-support | train/support | d01 | M2.02 | plan 81f1b8a1cd6b53ff0dcacaf48acc928273d9125452c767d9eda20bc108ffac14 | geom 31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9
g1-m202-d02-support | train/support | d02 | M2.02 | plan 7f48950e99314b2f35c0cc2697889fee4b45b2b494778886906ee078c173b305 | geom 6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05
g1-m202-d03-query | train/query | d03 | M2.02 | plan dbaee0d73847b2d6881d810804fa10dcc2409e9fd4f55127ec65ccda21794c4a | geom 78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12
g1-m202-d04-query | train/query | d04 | M2.02 | plan 21e8154f7ed4e712b0c7c176d68499be1cd16a821e4f9ed4e347504fd11dffcf | geom 2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2
g1-m202-d05-query | train/query | d05 | M2.02 | plan 1663a475fe032408c0e242f52079f6a09c831972d3fc6aeccd2125d971b2f31d | geom 0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55
g1-m240-d00-support | test/support | d00 | M2.4 | plan 6cc64caeeb8be6251f36cbbcb2a8a0178c4c40fff8a27bec7ce8f8f7e200e784 | geom f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34
g1-m240-d01-support | test/support | d01 | M2.4 | plan 09f46ed178a4fcf1e52a51cb2907c7596fe2d511654f64e4479be2032735c96d | geom 31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9
g1-m240-d02-support | test/support | d02 | M2.4 | plan 255411aa0b5f475c6caa107046c23722c2810cd7dd3dfec68d10807196f4f6ca | geom 6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05
g1-m240-d03-query | test/query | d03 | M2.4 | plan cd088a90c349abac2d3b654b3057f18ff17dc246a700053ee3d47dbcec4bf8b2 | geom 78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12
g1-m240-d04-query | test/query | d04 | M2.4 | plan 86eddc06685ff57b3e5575181109b3482cf89d6a4c3c299607aeae537452f9b0 | geom 2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2
g1-m240-d05-query | test/query | d05 | M2.4 | plan f1b3a45b421c62b48e0981b56678d3350e59571500150f94b15a02363df890b5 | geom 0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55
```

## 零物理核对
24 case 目录；case_result=0；solver_attempts.jsonl=0；.polar=0；文件 240。A5 前 physical_solver_starts_actual=0。

## 请判断
1. 授权、代码 SHA、24 case 计划 SHA、预算/停机/上传控制是否足以放行第一批 ≤8 starts？
2. 有无必须先修的 critical/major？
3. 明确“只放行 G1 ≤24 starts，不构成 G2/G3/R2 或人类签字”。

只返回 JSON：
{"reviewer":"deepseek-flash","review_type":"independent_single_shot_dossier_review","reviewed_utc":"YYYY-MM-DDTHH:MM:SSZ","dossier_sha256":"<dossier sha>","verdict":"G1_APPROVE"|"G1_CHANGES_REQUIRED"|"G1_REJECT","gate_verdicts":{"G1_PREREGISTRATION":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G1_CODE_STATE":"...","G1_CASE_PLAN":"...","G1_CONTROLS":"...","G1_ZERO_PHYSICAL":"..."},"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-flash independent A5 review; not a human signature"}
最多 6 findings，每条 <=240 字符。不要 Markdown。
