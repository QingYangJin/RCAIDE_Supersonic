# DRECOVER001-R2-20261120-01 真实 VSPAERO 原始结果

本目录是 Issue #13 G0 要求的旧 24 次真实 VSPAERO 计算原件上传，不是重新计算，也不是历史 F1R2/F2R2 的找回。

- run_id: DRECOVER001-R2-20261120-01
- authorization_id: AUTH-DRECOVER001-R2-20261120-01（含 B01R repair amendment）
- 24 physical solver starts，其中 23 完成、1 次外层 120s 超时中断（m240-d01-support）
- 10 张准入证书，去重后 9 条可用标签，14 条 null/failed 记录
- 645 internal solver cases，0 retries，parallel=1
- 所有 raw 文件逐字节保留；metadata/data_manifest.json 与 SHA256SUMS.txt 记录 SHA256
- 本批使用旧 build_evaluation（全局 Mach 2.02/q=20483.940233430174）产生 case_result；A1 的 per-case Mach/q 修复只影响后续批次，不回写本批 raw
- 标签证据等级：LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED；同机保存，异机备份已由 Owner 豁免（WAIVER-OFFMACHINE-BACKUP-20261118）
- 本目录不声称物理验证、不声称泛化、不授权新的真实求解
