# S3-M4 6 模型 sha256 对照表

run: `p4ra-s3-formal-20261109T1310Z`
repo: `<REPO_ROOT>` HEAD `691f554`
evidence root: `<REPO_ROOT>/research/concorde_metaopt/evidence/s3`（`sp.S3_EVIDENCE_ROOT_RELPATH`，s3_prereg.py:641）

| model file (manifest path) | bytes | actual sha256 (evidence root) | run model_manifest sha256 | M2 frozen manifest sha256 | prereg sha256 | match |
|---|---:|---|---|---|---|---|
| `models/fomaml_meta_0.json` | 107426 | `520d6ba465f80c910df6add0707a600b8e948cc2c01b9bd58a994b2a3945c6c6` | `520d6ba465f80c910df6add0707a600b8e948cc2c01b9bd58a994b2a3945c6c6` | `520d6ba465f80c910df6add0707a600b8e948cc2c01b9bd58a994b2a3945c6c6` | `520d6ba465f80c910df6add0707a600b8e948cc2c01b9bd58a994b2a3945c6c6` | YES |
| `models/fomaml_meta_1.json` | 107429 | `346ad98742e9a9eab06b9f999a93612055317f471cd8c562dd4cb0f190722478` | `346ad98742e9a9eab06b9f999a93612055317f471cd8c562dd4cb0f190722478` | `346ad98742e9a9eab06b9f999a93612055317f471cd8c562dd4cb0f190722478` | `346ad98742e9a9eab06b9f999a93612055317f471cd8c562dd4cb0f190722478` | YES |
| `models/fomaml_meta_2.json` | 107363 | `8ecd4623043dd20dc15ae7ecc1510157cbfbbfde777a1c70c33d68fd1a7da183` | `8ecd4623043dd20dc15ae7ecc1510157cbfbbfde777a1c70c33d68fd1a7da183` | `8ecd4623043dd20dc15ae7ecc1510157cbfbbfde777a1c70c33d68fd1a7da183` | `8ecd4623043dd20dc15ae7ecc1510157cbfbbfde777a1c70c33d68fd1a7da183` | YES |
| `models/anil_meta_0.json` | 107370 | `37201fcf2462d317906721f2716a741ada3a19e1e79f9991bf1ef309031eba29` | `37201fcf2462d317906721f2716a741ada3a19e1e79f9991bf1ef309031eba29` | `37201fcf2462d317906721f2716a741ada3a19e1e79f9991bf1ef309031eba29` | `37201fcf2462d317906721f2716a741ada3a19e1e79f9991bf1ef309031eba29` | YES |
| `models/anil_meta_1.json` | 107387 | `604b0e54b00805819805306e79dce24b20806ec0a6843af371e30f59c773aae1` | `604b0e54b00805819805306e79dce24b20806ec0a6843af371e30f59c773aae1` | `604b0e54b00805819805306e79dce24b20806ec0a6843af371e30f59c773aae1` | `604b0e54b00805819805306e79dce24b20806ec0a6843af371e30f59c773aae1` | YES |
| `models/anil_meta_2.json` | 107378 | `8a2bb85e92ff2b1eea66331cebe17a2140e8db418e32f66eb6cba2ac0c278055` | `8a2bb85e92ff2b1eea66331cebe17a2140e8db418e32f66eb6cba2ac0c278055` | `8a2bb85e92ff2b1eea66331cebe17a2140e8db418e32f66eb6cba2ac0c278055` | `8a2bb85e92ff2b1eea66331cebe17a2140e8db418e32f66eb6cba2ac0c278055` | YES |

解析基址实测：`run_dir/<path>` 与 `repo_root/<path>` 均不存在；仅 `repo_root/research/concorde_metaopt/evidence/s3/<path>` 命中（权重按设计不进 run 目录）。
`S3_MODEL_ENTRY_FIELDS` 无 `bytes` 字段（s3_prereg.py），故 bytes 取 prereg 冻结值并实测文件大小一致。
合计：6/6 actual sha256 == run manifest == M2 frozen manifest == prereg；bytes 6/6 == prereg。
