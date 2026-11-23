# P2 数据清点与短缺矩阵（零物理重放）

生成脚本：p2_data.py；所有行均通过 admit_real_manifest 对本地原始字节重新准入。
物理求解器启动：0。

| 任务 | 切分 | Mach | 独立 support | 独立 query | K=3 support |
|---|---|---|---|---|---|
| P2-CANON-M160 | train | 1.60 | 3 | 2 | 是 |
| P2-CANON-M180 | val | 1.80 | 2 | 3 | 否 |
| P2-CANON-M200 | train | 2.00 | 3 | 3 | 是 |
| P2-CANON-M202 | train | 2.02 | 2 | 3 | 否 |
| P2-CANON-M240 | test | 2.40 | 1 | 3 | 否 |

任务别名（历史批次 -> 规范任务）：

- P2-CANON-M202: DREAL003-G1-M202, DREAL003-G2-M202, concorde-fixed-cruise-dreal001-real-v1
- P2-CANON-M160: DREAL003-G2-M160, concorde-real-M160
- P2-CANON-M180: DREAL003-G1-M180, DREAL003-G2-M180, concorde-real-M180
- P2-CANON-M240: DREAL003-G1-M240, concorde-real-M240
- P2-CANON-M200: DREAL003-G2-M200

被排除的记录（去重/冲突，均未计为独立样本）：

- g2b02-adm-g2-m160-d07-query-s2: design appears in both support and query at the same priority
- g2-adm-g2-m160-d00-support-s2: design appears in both support and query at the same priority
- g2b02-adm-g2-m180-d07-query-s2: design appears in both support and query at the same priority
- g2b02-adm-g2-m180-d00-support-s2: design appears in both support and query at the same priority
- g2b02-adm-g2-m200-d07-query-s2: design appears in both support and query at the same priority
- g2b02-adm-g2-m200-d00-support-s2: design appears in both support and query at the same priority
- g1-adm-g1-m180-d03-query: design appears in both support and query at the same priority
- g2b02-adm-g2-m180-d03-support-s2: design appears in both support and query at the same priority
- g1-adm-g1-m180-d05-query: duplicate design within canonical task
- g1-adm-g1-m202-d00-support: duplicate design within canonical task
- g1-adm-g1-m202-d01-support: duplicate design within canonical task
- g1-adm-g1-m202-d03-query: design appears in both support and query at the same priority
- g2b02-adm-g2-m202-d03-support-s2: design appears in both support and query at the same priority
- ADM-R2-B01R-M160_D02_QUERY_R1: design appears in both support and query at the same priority
- g2-adm-g2-m160-d02-support-s2: design appears in both support and query at the same priority
- ADM-R2-B01R-M180_D02_QUERY_R1: design appears in both support and query at the same priority
- g2b02-adm-g2-m180-d02-support-s2: design appears in both support and query at the same priority
- ADM-R2-B01-BASELINE-ADMIT-01: duplicate design within canonical task
- ADM-R2-B01-BASELINE-REFINE-01: duplicate design within canonical task
- ADM-R2-B01R-M202_D02_QUERY_R1: design appears in both support and query at the same priority
- g2b02-adm-g2-m202-d02-support-s2: design appears in both support and query at the same priority
- ADM-R2-MATRIX-M202-D01-SUPPORT: duplicate design within canonical task
- ADM-R2-B01R-M240_D00_SUPPORT_R1: duplicate design within canonical task
