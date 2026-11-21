# M1-A 12-deck freeze payload 回执（G08，零物理复制）

- freeze_id: M1A-DECK-FREEZE-20261113-A1
- 生成者: a1-geometry
- 权威对象: A3 M0-R r3 commit 7128b911f7d8cb064ecd0b619b89f3af7abd27e3
- A3 M0R_DECK_FREEZE.json SHA256: cb933119a88136b3f10c177fb34487b5d7e01055009e65d0a21af2c43141f2d6 / 40496 B
- A3 SHA256SUMS.txt SHA256: 0bf7ce2d141f051e1aff6f607a495f28bf33c0b548ebd06ec8273538c8316800 / 38 entries
- A1 U1 dry-run SHA256: 8688d25770911af7fadd42587f66a4914091c829fd8cdc89c1f349a53731b4c6 / 43587 B（18 decks 中选 12 个 M1-A 槽位）
- A1 interface clarification: 7731e9c8b6269e50b343f7e2fbb9ade9c123e14bb33db7e0a884a922cc83e948 / 7673 B（A5_ACCEPTED_AUTHORITATIVE）

## G08 声明

本次交付为 copy-only 冻结载荷：12 个 M1-A 槽位 × 5 文件 = 60 个文件，全部逐字节复制并复算 SHA256；未启动 OpenVSP，未启动 VSPAERO，未重建几何，未运行任何 solver；physical_call_count = 0；未修改 A3 M0-R 包任何字节，未创建 run dir。

## 12/12 槽位与双表比对

| slot | design | task | deck SHA256 (前12) | deck B | vspgeom SHA256 (前12) | vspgeom B | 来源 |
|---|---|---|---:|---:|---|---:|---|
| M1A-B0-01-M202_CL017 | B0-01 | T18K_M202_CL017 | 1614a964fc72 | 943 | 16da482a1f8e | 225414 | M0R_R3_FROZEN_BASELINE_DECK + A1_U1_DRY_RUN_GEOMETRY |
| M1A-B1-01-M202_CL017 | B1-01 | T18K_M202_CL017 | 1614a964fc72 | 943 | 6a296aee6e6f | 225414 | A1_U1_DRY_RUN_20261112 |
| M1A-C5-M202_CL017 | C5 | T18K_M202_CL017 | 1253fa5f2c0f | 931 | e1ad74cc3820 | 225414 | A1_U1_DRY_RUN_20261112 |
| M1A-B0-01-M202_CL019 | B0-01 | T18K_M202_CL019 | 1614a964fc72 | 943 | 16da482a1f8e | 225414 | M0R_R3_FROZEN_BASELINE_DECK + A1_U1_DRY_RUN_GEOMETRY |
| M1A-B1-01-M202_CL019 | B1-01 | T18K_M202_CL019 | 1614a964fc72 | 943 | 6a296aee6e6f | 225414 | A1_U1_DRY_RUN_20261112 |
| M1A-C5-M202_CL019 | C5 | T18K_M202_CL019 | 1253fa5f2c0f | 931 | e1ad74cc3820 | 225414 | A1_U1_DRY_RUN_20261112 |
| M1A-B0-01-M220_CL017 | B0-01 | T18K_M220_CL017 | 6a022882fa5b | 957 | 16da482a1f8e | 225414 | M0R_R3_FROZEN_BASELINE_DECK + A1_U1_DRY_RUN_GEOMETRY |
| M1A-B1-01-M220_CL017 | B1-01 | T18K_M220_CL017 | 6a022882fa5b | 957 | 6a296aee6e6f | 225414 | A1_U1_DRY_RUN_20261112 |
| M1A-C5-M220_CL017 | C5 | T18K_M220_CL017 | d5d9104e1930 | 945 | e1ad74cc3820 | 225414 | A1_U1_DRY_RUN_20261112 |
| M1A-B0-01-M220_CL019 | B0-01 | T18K_M220_CL019 | 6a022882fa5b | 957 | 16da482a1f8e | 225414 | M0R_R3_FROZEN_BASELINE_DECK + A1_U1_DRY_RUN_GEOMETRY |
| M1A-B1-01-M220_CL019 | B1-01 | T18K_M220_CL019 | 6a022882fa5b | 957 | 6a296aee6e6f | 225414 | A1_U1_DRY_RUN_20261112 |
| M1A-C5-M220_CL019 | C5 | T18K_M220_CL019 | d5d9104e1930 | 945 | e1ad74cc3820 | 225414 | A1_U1_DRY_RUN_20261112 |

双表结果：A1 U1 dry-run 12/12 与 A3 r3 m1a_required_deck_set 12/12 的 deck SHA、vspgeom SHA、design_hash 全部一致；12/12 槽位文件复制后 SHA 与源字节一致。

## 槽位文件清单

每个槽位目录含 5 个文件：concorde_baseline.vspgeom、concorde_baseline.vkey、concorde_baseline.vspaero、concorde_baseline.csf、task_deck.json。B0-01 的 .vspaero 与 task_deck.json 取自 M0-R r3 冻结 baseline 槽位；B0-01 的几何/vkey/csf 及 B1-01/C5 的全部文件取自 A1 U1 dry-run 构建产物。

## vkey 与几何身份口径

vkey 含路径相关字段，本 manifest 保存其 SHA256 仅作记录，不作为跨进程几何身份；跨进程身份使用 deck_sha256 + vspgeom_sha256。

## 未做事项

- 未启动 OpenVSP / VSPAERO；
- 未重建任何几何；
- 未修改 A3 M0-R 包、A1 frozen 包、F1R2/F2R2 run dir 字节；
- 未创建真实 run dir，未签发任何 authorization。

## 文件

- manifest.json：逐槽位字段、双表、checks、attestations；
- RECEIPT_ZH.md：本回执；
- SHA256SUMS.txt：60 个槽位文件 + manifest.json + RECEIPT_ZH.md 的 SHA256 清单。

结论：G08 的 12 槽位复制冻结载荷已就绪；等待 A5 重出 gate 与 M1-A authorization 绑定本 commit。
