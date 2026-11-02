# D-12D-003 Round-1 A3 安装审计报告：OpenVSP 3.55.0 便携式侧装

- 任务: task-35（D12D003-INSTALL-AUDIT）；执行: A3 / a3-repo-guard；向 Lead 汇报
- 决策: D-12D-003（GitHub 评论 6566994749；本地快照 .../fullchain/lead/intake-20261102/comment_08_6566994749.md）
- 审计窗口: 2026-11-02 09:47–09:58 +0800；报告生成: 2026-11-02T09:57:47+08:00
- 主机: Windows 11 Pro 10.0.26200 x64；工作区 D:/RCAIDE；分支 research/concorde-metaopt；HEAD 5dcb0bf09335fd6f73363d0280a667286d6d20f9
- 审计方式: 只读仓库 + 只读文件系统/注册表/PATH/site-packages + 在线核验 + 非求解型二进制使用信息探测；零 solver、零物理计算、无 GitHub 写、无仓库写
- 权威事实源: 同目录 facts.json（结构化实测数据）与 checks.log（原始命令/输出节选）；本报告为其摘要

## 结论

**PASS**（附 1 项对账说明 + 3 项限制）。

OpenVSP 3.55.0 官方 zip 来源在线可核验，大小/哈希与声明及 provenance 一致，解压完整；Python API 实测报告 **OpenVSP 3.55.0**，VSPAERO 实测报告 **v7.2.2** 且其 usage 捕获与 A1 仓库证据逐字节一致；旧 3.26.1 安装、SUAVE Python 3.9 worker、PATH/注册表/site-packages 均未被改动，无任何 3.55 痕迹；回滚 4 步静态评估可行（执行 NOT_RUN）；仓库无安装产物，P5 dirty 集与基线和 Lead 授权范围一致。唯一对账差异：porcelain 实测 23 行而非 Lead 预期的 22 行，原因已定位为新增的 D-12D-003 未跟踪证据目录（2 文件），非安装产物、非 tracked 改动。

## 核对结果

| # | 核对项 | 结果 | 关键证据 |
|---|---|---|---|
| C1 | 官方来源在线核验 | PASS | openvsp.org 索引/下载页/发布说明均 HTTP 200；索引列出 OpenVSP-3.55.0-win64-Python3.11.zip（2026-10-11 21:47, 47M）；下载页 label "OpenVSP 3.55.0 64-bit Python 3.11"；发布页标题 "OpenVSP 3.55.0 Released" |
| C2 | 官方件身份与大小 | PASS | 远端 HEAD: HTTP 200, Content-Length=49,664,844, Last-Modified=Mon, 12 Oct 2026 04:47:13 GMT, ETag=\"2f5d34c-65d9d64404427\"；本地 archive 大小同值 |
| C3 | 本地归档哈希 | PASS | D:/OpenVSP-download/OpenVSP-3.55.0-win64-Python3.11.zip, 49,664,844 B, sha256=f1fde65f9d48ae482dcad2c0b7711b81a22810871a5bebc236c4618c0131ebb9（与任务声明一致） |
| C4 | 压缩包完整性 | PASS | unzip -t rc=0 "No errors detected"；zipfile.testzip=None；550 entries = 491 files + 59 dirs；顶层单目录 OpenVSP-3.55.0-win64；uncompressed 149,488,735 B |
| C5 | 解压完整性 | PASS | 491/491 文件齐全（missing=0）、149,488,735 B；另有 13 个 python/**_pycache__/*.pyc（09:43，589,720 B，A1/Lead probe import 产生，非官方归档内容）；树总 504 files / 150,078,455 B |
| C6 | 哈希重算 vs provenance | PASS | 12/12 sha256 与 install_provenance.json 完全一致、0 mismatch（archive + 8 新文件 + 3 旧文件）；provenance JSON 5,147 B sha256=3da3dc7ab82c3807156de894a1f7a8542a3b76dca2bb0212a5324596c8ef06aa，字段/文件 size 校验 0 bad |
| C7 | Python API 版本 | PASS | D:/RCAIDE/envs/RCAIDE/python.exe（3.11.17 64bit）import openvsp 成功；vsp.GetVSPVersion()="OpenVSP 3.55.0"；major/minor=[3,55]；API names=2176；未做几何/求解 |
| C8 | VSPAERO 版本 | PASS | 无参数执行 D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe（exit 1，仅 usage banner，无几何/输入）输出 "VSPAERO v.7.2.2 --- Compiled on: Oct 12 2026 at 04:08:14 PST"；捕获 /tmp/vspaero_usage_a3.txt 1,546 B sha256=3bc9b1d18729856fca513dad26343ea14eadd447f13ac0fa66a02df8157f5d67，与 repo 证据 research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/evidence/vspaero_7.2.2_usage.txt 逐字节一致 |
| C9 | 版本资源元数据 | PASS（限制） | vsp.exe/vspaero.exe VersionInfo FileVersion/ProductVersion 为空（无 PE version resource）；vsp.exe 内嵌 "OpenVSP 3.55.0" ×3、vspaero_opt.exe ×1；故 vspaero 版本以 usage banner 为准 |
| C10 | 旧 3.26.1 安装未动 | PASS | D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64：240 files，0 files newer than 2026-11-01；vspaero.exe 561,664 B sha256=e1affca0…（= 2026-10-31 environment.json 记录值，VSPAERO v6.2.0）、mtime 2022-01-06 01:06:36；vsp.exe d175fcba…/_vsp.pyd b2025e16… 同 2022-01-06 mtime；15 个非二进制 egg-info 元数据 mtime 2026-10-31 12:01（审计前既有） |
| C11 | SUAVE py3.9 worker 未动 | PASS | D:/Anaconda/envs/SUAVE/python.exe 存在、3.9.25 64bit、mtime 2025-11-04T07:01:33；site-packages 无 openvsp/vsp；env 下 2026-11-01 后文件=0 |
| C12 | PATH 隔离 | PASS | User PATH len=544 仅旧 3.26.1 条目；Machine PATH len=327 无 OpenVSP；Process 仅旧；三者均无 "3.55"；where vsp/vspaero 均解析到旧安装 |
| C13 | site-packages 隔离 | PASS | RCAIDE env（3.11）、Python39 global、SUAVE env 均无 openvsp/vsp 包；RCAIDE、Python39 site-packages 顶层 2026-11-01 后条目=0/0 |
| C14 | 注册表隔离 | PASS | HKCU/HKLM/WOW6432Node 无 OpenVSP 顶层键、无 Uninstall DisplayName~OpenVSP、无 App Paths vsp/vspaero；无含 "3.55" 的注册表值；HKCR .vsp3→vsp3_auto_file 为既有文件关联（无 3.55 path，创建时间不可考） |
| C15 | 仓库无安装产物 | PASS | 0 tracked install 文件；仓库内 size=49,664,844 文件 0；文件名含 "3.55" 0；09:35 后全仓库新建/改文件恰好 2 个，均为上述 D-12D-003 未跟踪证据文件；无 OpenVSP 二进制/zip 拷入仓库；既有 openvsp*.py 为源码非安装产物 |
| C16 | dirty 集/P5 保护 | PASS（对账） | HEAD=5dcb0bf=origin；main=ec65e5a（2026-10-27）未动；staged 0；stash 0；reflog 近 50 条 reset/force=0；7 个 tracked 修改路径与基线一致（diffstat +586/−123）；P5（排除 __pycache__）54 files / 7,976,412 B 与基线一致、tracked P5=0；porcelain 23 vs 22 见下节 |
| C17 | 回滚步骤 | PASS（静态） | 4 步静态评估 REALISTIC；执行 NOT_RUN；注意 env vars 当前未设置（见第 4 步） |
| C18 | 无 solver/物理运行 | PASS | 无 vspaero/vsp/SU2_CFD 求解进程；唯一二进制执行 = vspaero 无参数 usage banner；Python 仅 import openvsp 无几何；未生成 evaluations/solver 日志 |

## 1. 官方来源与归档身份

- 索引页 https://openvsp.org/zips/current/windows/：HTTP 200，705 B；条目 OpenVSP-3.55.0-win64-Python3.11.zip（last modified 2026-10-11 21:47，47M），另有 Python3.13 版本。
- 下载页 https://openvsp.org/download.php：HTTP 200，5,843 B；Python 3.11 链接指向 download.php?file=zips/current/windows/OpenVSP-3.55.0-win64-Python3.11.zip。
- 发布说明 https://openvsp.org/blogs/announcements/2026/10/12/openvsp-3-55-0-released：HTTP 200，标题 "OpenVSP 3.55.0 Released"。
- 远端 zip HEAD：HTTP 200；Content-Length=49,664,844；Last-Modified=Mon, 12 Oct 2026 04:47:13 GMT；ETag="2f5d34c-65d9d64404427"；Content-Type=application/zip。
- 本地 archive：49,664,844 B，mtime 2026-11-02 09:39:59.4214+0800，sha256=f1fde65f…（见 C3）。
- 官方站点未发布 sha256，故以本地 sha256 作为强身份，以远端 Content-Length/ETag/Last-Modified 与 index 条目作为来源佐证。

## 2. 解压与哈希

- zip：550 entries = 491 files + 59 dirs；testzip=None；uncompressed 149,488,735 B；单顶层目录 OpenVSP-3.55.0-win64。
- 解压：491/491 文件、149,488,735 B，missing=0；另有 13 个 probe 生成的 __pycache__/*.pyc（589,720 B，09:43）。
- 12/12 sha256 与 install_provenance.json 完全一致，0 mismatch；provenance JSON 5,147 B，sha256=3da3dc7ab82c3807156de894a1f7a8542a3b76dca2bb0212a5324596c8ef06aa。

## 3. 版本结论

- Python API（import 而非几何调用）：OpenVSP 3.55.0（vsp.GetVSPVersion()；major/minor=[3,55]；2176 API names）。
- VSPAERO 二进制：v7.2.2（usage banner，编译于 Oct 12 2026 04:08:14 PST）；usage 捕获 sha256=3bc9b1d1… 与 A1 仓库证据文件逐字节一致。
- 限制：vsp.exe/vspaero.exe 无 PE version resource（FileVersion/ProductVersion 为空），版本证据依赖用法 banner、内嵌字符串与 provenance 哈希，而非 Windows 版本资源。

## 4. 仓库脏工作区对账：23 行而非 22 行

- 实测 porcelain（默认）23 行 = 7 tracked M + 16 untracked 条目；porcelain -uall=95 行（基线 93）；staged=0。
- Lead 预期 22 行；差异 +1 定位为新增未跟踪目录 research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/：
  - install_provenance.json，5,147 B，创建 2026-11-02 09:44:56，sha256=3da3dc7a…
  - evidence/vspaero_7.2.2_usage.txt，1,546 B，创建 2026-11-02 09:45:12，sha256=3bc9b1d1…
- 该目录为 D-12D-003 项目证据（A1 产出），非安装产物；未 staged、未被跟踪；无新 tracked 改动（7 个 M 路径不变，diffstat +586/−123）。
- P5 保护：排除 __pycache__ 后 54 files / 7,976,412 B 与基线完全一致、tracked P5=0；另有 2 个既有 pycache .pyc（115,639 B，mtime 2026-10-30 13:03）；P5 今日新文件=0。
- git 安全：HEAD=5dcb0bf=origin/research/concorde-metaopt；main=ec65e5a（2026-10-27）未动；stash=0；reflog 近 50 条无 reset/force。

## 5. 回滚评估（静态 REALISTIC；执行 NOT_RUN）

1. 删除或重命名 D:/OpenVSP-3.55.0：安全 — 新装为自包含目录（仓库外），无 PATH/注册表/site-packages/service 依赖；仅 probe 进程内使用 os.add_dll_directory/sys.path；删除同时移除 13 个 probe pycache。
2. 保留或删除 D:/OpenVSP-download/OpenVSP-3.55.0-win64-Python3.11.zip：安全 — 单文件、独立于安装与仓库；保留供审计无副作用。
3. 旧 3.26.1 + SUAVE worker 已核验未动（hash/mtime、0 个 2026-11-01 后文件），且 PATH/注册表/site-packages 无 3.55 痕迹 → 删除新目录即恢复此前状态，无需其他回滚动作。
4. 重跑旧 worker：旧二进制齐全且哈希为原值；需显式设置 CONCORDE_OPENVSP_ROOT/CONCORDE_OPENVSP_PYTHON（当前 Process/User/Machine 均未设置；docs 引用 research/concorde_metaopt/aircraft/openvsp_check.py:24-25,85-90 与 research/concorde_metaopt/README.md:223,782），实操可行。

未执行任何删除/重命名/移动/回滚操作（只读授权）。

## 6. 限制

1. 二进制无 PE version resource：版本靠 usage banner + 内嵌字符串 + provenance 哈希（C9）。
2. 无安装前后注册表/PATH 对照快照：隔离由"当前无任何 3.55 痕迹" + 便携 zip + provenance no_global_install=true 共同证明；残余风险 LOW。
3. 回滚仅静态评估，未执行（只读授权）。
4. 仓库状态采样于 2026-11-02 09:47–09:58，其他 agent 活跃（run dir 由 A1 于 09:44–09:45 创建），仅有 2 个证据文件可归因今日。
5. 未查询 GitHub（无 GitHub 写；用本地 intake 快照确认 D-12D-003 批准）。

## 7. 安全边界声明

- 仓库写: 0；git 写操作: 0；solver/物理计算: 0；GitHub 写: 0；文件删除/移动: 0。
- 唯一执行：vspaero.exe 无参数（仅 usage banner）与 python import openvsp（无几何/模型）；旧安装与新安装（除 probe 生成的 __pycache__）均未修改。
- 本任务未读取 .agents/github Token.txt（未访问；历史任务仅 stat）。

## 8. 交付文件（本目录）

| 文件 | 大小 | sha256 |
|---|---|---|
| install_audit.md | 见文件系统 | 见 checks.log 末节 FINAL_ARTIFACT_SHA256 |
| checks.log | 审计原始记录（[00]–[19]） | 自身哈希随末节追加变化，故由末节登记其余两文件哈希 |
| facts.json | 23,681 B | f1566e7a8ec3b612320bed8288cd0044726f1f041346f73d271fe80fd819328f |

镜像目录：C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/EXT/fullchain/d12d003/a3/（与本文档同内容）。
