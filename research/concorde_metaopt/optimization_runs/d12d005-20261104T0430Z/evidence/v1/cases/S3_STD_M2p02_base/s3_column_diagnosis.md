# S3（标准矩形翼 M2.02）polar 数据列诊断

零求解纯文件诊断，生成时间: 2026-11-04T07:17:16Z；源: evidence/v1/cases/S3_STD_M2p02_base/s3_column_diagnosis.json。

## 1. 非有限 token

- S3 polar：仅 1 个非有限 token —— line 4, column_index_1based 47/48, column = Ew, token = inf。
- S0/S1/S2 polar：0 个非有限 token；同列 Ew = 1.009909991712 / 1.769927638406 / 1.009778243121（有限）。
- 表头与列位置：Beta, Mach, AoA, Re/1e6, CLo, CLi, CLtot, CDo, CDi, CDtot, CSo, CSi, CStot, L/D, E, CMox, CMoy, CMoz, CMix, CMiy, CMiz, CMxtot, CMytot, CMztot, CFox, CFoy, CFoz, CFix, CFiy, CFiz, CFxtot, CFytot, CFztot, CLwtot(34), CDwtot(35), CSwtot, CLiw, CDiw, CSiw, CFwxtot, CFwytot, CFwztot, CFiwx, CFiwy, CFiwz, LoDw(46), Ew(47), StallFactor(48)。

## 2. S3 polar 关键列（AoA=2）

| 列 | 值 |
|---|---|
| CLo | -0.000390514345 |
| CLi | 0.074641546128 |
| CLtot | 0.074251031783 |
| CDo | 0.011182867698 |
| CDi | 0.002606540227 |
| CDtot | 0.013789407924 |
| CMoy | 0.000000000000 |
| CMytot | -0.014777040022 |
| CLwtot | -0.000390514345 |
| CDwtot | 0.011182867698 |
| LoDw | -0.034920769492 |
| Ew | inf（非有限） |
| E | 0.168318084604 |

## 3. history 收敛（5 次迭代）

| Iter | CLtot | CDtot | L2 | Max |
|---|---|---|---|---|
| 1 | -0.000389270298 | 0.011147242841 | 1.110441223481 | 1.318092673425 |
| 2 | 0.073663981306 | 0.013775768372 | 0.414736426516 | 1.515239780349 |
| 3 | 0.074121045070 | 0.013780702003 | -0.578277511718 | 0.349698749124 |
| 4 | 0.074269385763 | 0.013790118249 | -1.557867626967 | -0.799578946736 |
| 5 | 0.074251031783 | 0.013789407924 | -2.752858965500 | -2.050385282896 |

残差 L2 单调下降（1.11 -> -2.75）、Max 由 1.32 降至 -2.05；第 4->5 步 ΔCLtot=-1.84e-5（相对 2.47e-4）、ΔCDtot=-7.1e-7，属平滑收敛而非发散。

## 4. 判断

- 判定 (A) 派生效率列退化伪影，不是 (B) 求解发散残留。
- 依据：CDwtot=0.011182867698 非零有限；CLwtot=-0.000390514345 近零（wake 升力近零）导致 Ew (wake efficiency 派生量) 溢出为 inf；主系数与 history 均有限且收敛。
- 后果：Ew=inf 仍违反 fail-closed 规则，S3 polar 判 INVALID；停止规则 1 成立，批次停止正确。
- 物理结论：VSPAERO 7.2.2 thin 在 M2.02 仍 NOT_VALIDATED；S3 的 CLtot/CDi 仅作诊断记录，不得用于阻力/燃油/body correction。

