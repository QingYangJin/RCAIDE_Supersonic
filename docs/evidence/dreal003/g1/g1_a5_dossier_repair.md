# A5 预审 · Issue #13 G1 修复批次 B02（精简 dossier）

## 授权与既有事实
Owner m07992：“继续执行，把G1阶段也完成，批准实际物理计算”。G1 总上限 24 starts。
B01 已实际执行 8 starts，全部 SOLVED，但 8/8 为 CL_TARGET_OUTSIDE_POLAR，0 条准入标签；原因是单一全局 alpha 斜率外推偏大，M160 偏 0.61°、M180 偏 0.12°。
B01 原始文件、账本、失败表与 A5 预审判定已保存；不重跑 B01 的 8 个 case。

## 修订（amendment）
 amendment_id G1-REPAIR-B02-20261121，SHA256 9dc47742648e04a385400c511eef0ae300616fc1e225ecb3faec8dbe78261b5f
- 仅重建 16 个未启动 case（M180 d02-d05、M202 全部 6、M240 全部 6），不触碰 8 个已启动 case。
- 修正 alpha_center：M180 base 6.1846/slope 0.03579；M202 base 5.18125/slope 0.03439427；M240 base 4.44/slope 0.034；M160 base 7.4658/slope 0.03655（仅用于记录，B02 不再跑 M160）。
- 每 case 仍 17 个 alpha 点围绕 alpha_center、步长 0.03°（局部极曲线，跨度 0.48°）；全局 alpha_center 允许窗口为 (-2,10)，两者不是同一范围；升力容差 1e-3；每 case max_starts=1。
- B02 最多 16 starts、parallel 1、0 retry、单 case 1200s；不得重跑 B01。
- 上传/回读：本批完成后上传 raw/CSV/PNG/账本并回读 SHA256SUMS。
- 只放行 B02 16 starts；不授权 G2/G3/R2，不是人类签字。

## 会计披露
- 已消耗 8/24，剩余 16。
- 若 B02 全部成功：16 条标签；累计 16/24 = 0.667，低于 G1 的 0.70 目标。B01 的 8 个 null 不可消除，因此本轮不宣称 G1 标签率达标。
- physical_solver_starts_actual 当前 8；B02 前不会再启动。

## B02 16 个 case 精确清单
```
g1-m180-d02-support | val/support | d02 | M1.8 | center 6.1846 | plan 9c3dfeb8350c9aa3d8cbd8b8c0cf16c05ff42abd49e3050e28f3bc38430f75d4 | geom 6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05
g1-m180-d03-query | val/query | d03 | M1.8 | center 6.2492 | plan 072190d7bc7150cf2df875beef64a3050b2cb1342043bc681a86ffae9ba70f23 | geom 78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12
g1-m180-d04-query | val/query | d04 | M1.8 | center 6.1846 | plan 2efc8971ecae2805f51eb52a9bdcc55072ad2a3bc3730057bb22f26a27d87d38 | geom 2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2
g1-m180-d05-query | val/query | d05 | M1.8 | center 6.1846 | plan f689b6dda54ae2a617aeb5d0553224061c06ae2e0aa1b6274515849c80eef2c7 | geom 0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55
g1-m202-d00-support | train/support | d00 | M2.02 | center 5.1813 | plan 67ba5812be5a1a08bf4f40b51b71a20c410db966948e9b12a6c861601665abcb | geom f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34
g1-m202-d01-support | train/support | d01 | M2.02 | center 5.1290 | plan bb64a4331ddcf3645e5a94b5b28be081ba284851e0850f3eb298b617f1ff1156 | geom 31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9
g1-m202-d02-support | train/support | d02 | M2.02 | center 5.1813 | plan e0ee1a0368a5b9fd8ff78aa5c629f027d9dc107644580270aca1d880aea5bd2a | geom 6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05
g1-m202-d03-query | train/query | d03 | M2.02 | center 5.2347 | plan 1fe41792939e7d2d2433a70ad5a271b1696e185e26340383aee7fd7c9791939e | geom 78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12
g1-m202-d04-query | train/query | d04 | M2.02 | center 5.1813 | plan 566f4e50d98d37b2d0ad20fa367cdcb20bd50f783e9ecb690a569420c636f4d2 | geom 2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2
g1-m202-d05-query | train/query | d05 | M2.02 | center 5.1813 | plan ea30d7dfdfff9824591b844f1beddc9381bb8b378bee71956276367ff373039b | geom 0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55
g1-m240-d00-support | test/support | d00 | M2.4 | center 4.4382 | plan 0f73f530810853fea940acc8b80c24fc8f2dca63d80b0af978675a896a6fc474 | geom f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34
g1-m240-d01-support | test/support | d01 | M2.4 | center 4.4007 | plan e5563ae3d374c5bb0418075a44e0c1abd50df5fce5407c9c7edcb2cd61a7dd1c | geom 31d503b665b4bbaab69e5fcf63dcd5cfc6bc215642dff2d12408f24a53931ad9
g1-m240-d02-support | test/support | d02 | M2.4 | center 4.4382 | plan ed438793a7eb73cd177c8ecf8ed98639c370cd7e55dfa9c75bd3a35e9513a6d5 | geom 6d387f85caefb002b24ee72a7a26dff5ba768ef865e42e185522fdd50cb87e05
g1-m240-d03-query | test/query | d03 | M2.4 | center 4.4764 | plan b9b777080dbb1e1f3dc3e2ff3876d59c66e13c00040b5d9fdc653a8ab67d047d | geom 78f40ba8a562cebd71b014e1b2c159d5bbad9f34f62da49e4a725f8adef5de12
g1-m240-d04-query | test/query | d04 | M2.4 | center 4.4382 | plan f4e582474ddec6356ce77eda7c0e9f43ad9ac1e5b2d7aa1c5819c678e5ab7769 | geom 2180ba467800018bf351c9410b96230b4807353fc78ce4258f21027cf4deafb2
g1-m240-d05-query | test/query | d05 | M2.4 | center 4.4382 | plan c7374c28e2f3f7e6ea004871114f3be65e6165ecf91f063ca82a8488bb51e7be | geom 0b586274ef7e032d331542c1073649cbd5b1c5a3498093d00e30910706cf7f55
```

## 零物理核对
16 个 case 目录已重建 plan/approval/task_spec/case_inputs/vspgeom/vspaero；这 16 个目录无 solver_attempts.jsonl、无 case_result、无 polar；B02 尚未启动。

## 请判断
1. 修订后的 alpha 模型、16 case 计划 SHA、剩余预算与停止/上传控制，是否足以放行 B02 的 16 次真实 starts？
2. 是否接受“累计 16/24、G1 不宣称标签率达标”的披露？
3. 明确“只放行 B02 16 starts，不授权 G2/G3/R2，且不是人类签字”。

只返回 JSON：
{"reviewer":"deepseek-flash","review_type":"independent_single_shot_dossier_review","reviewed_utc":"2026-11-21T09:35:00Z","dossier_sha256":"<dossier sha>","verdict":"G1_REPAIR_APPROVE"|"G1_REPAIR_CHANGES_REQUIRED"|"G1_REJECT","gate_verdicts":{"G1_REPAIR_ROOT_CAUSE":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G1_REPAIR_CASE_PLAN":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G1_REPAIR_BUDGET":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","G1_REPAIR_CONTROLS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL"},"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"...","signature":"deepseek-flash independent A5 review; not a human signature"}
Hard limits: at most 6 findings, each <=240 characters; at most 6 limitations; scope <=400 characters. JSON must be complete.
