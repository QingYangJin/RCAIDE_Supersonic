# A4 可注入根目录与相对路径（代码修改记录）

日期：2026-11-17；分支：`recovery/drecover001-20261117`；基线：`4c51c7df34c9626999ef2e66e5a6c76a2b9c92e2`。
范围：仅 A4 要求中的"可注入根目录 / 相对路径 / fresh-clone 软件回归"前置。**本文件不构成任何物理授权；physical_solver_starts_actual 仍为 0。**

## 1. 改了什么

| 文件 | 改前 | 改后 |
|---|---|---|
| `research/concorde_metaopt/dreal001/optimizers/p2a_v2.py` | `DEFAULT_A1_ROOT = Path(r"D:\RCAIDE\dnext001\wt-real-a1-geometry-solver")` | `A1_ROOT_ENV = "RCAIDE_A1_ROOT"`；`DEFAULT_A1_ROOT = None`；新增 `resolve_a1_root(a1_root=None) -> Path`：显式参数 > 环境变量，缺失即 `ValueError("A1 root is not injected: pass a1_root/--a1-root or set RCAIDE_A1_ROOT")` |
| 同上，7 处调用点 | 隐式使用模块级硬编码常量 | `a1_binding`(:222)、`_preflight_binding`(:576)、`builder_code_path`(:718/:1615，取 `a1.get("a1_root")`)、`run_dry_run`(:1977)、`build_package`(:2101)、CLI `--a1-root`(:2236) 全部经 `resolve_a1_root` |
| `research/concorde_metaopt/dreal001/optimizers/p2a_v2_common.py` | 常量直接拼 `D:/RCAIDE/dnext001/wt-real-a1-geometry-solver` | `A1_ROOT_ENV = "RCAIDE_A1_ROOT"`；`_A1_ROOT_HISTORICAL` 保留为**已声明的历史默认**（R10 已签 plan 的 SHA 复现需要它）；`a1_artifact_path(relpath, a1_root=None)` 允许环境变量覆盖；`A1_PAIR_MANIFEST_PATH` / `A1_PREFLIGHT_BUNDLE_PATH` 改由该函数生成 |
| `research/concorde_metaopt/reviews/a5_audit/a5_audit.py` | `DEFAULT_DNEXT_ROOT = Path(r"D:\RCAIDE\dnext001")`；`--s3-root` 默认 `D:\RCAIDE-s3-dev` | 删除硬编码；新增 `RCAIDE_S3_ROOT` / `RCAIDE_DNEXT_ROOT`；argparse 默认取环境变量或空串；缺失时打印 `S3 root is not injected: pass --s3-root or set RCAIDE_S3_ROOT`（dnext 同理）并以退出码 2 结束 |
| `research/concorde_metaopt/dreal001/meta/m0r_predraft.py` | `ROOT = Path("D:/RCAIDE")` | `DEFAULT_ROOT = Path(__file__).resolve().parents[4].parent`；`ROOT = Path(os.environ.get("RCAIDE_DNEXT_PARENT", str(DEFAULT_ROOT)))` |
| `research/concorde_metaopt/meta_learning/m5_runner.py`、`m6_study.py` | 复现命令写死 `D:/Anaconda/envs/RCAIDE/python.exe` | 改用 `sys.executable` |
| `gpu/env_check.py`、`gpu/bench_gpu.py`、`dreal001/optimizers/p2a.py`、`dreal001/m1/task_evaluator.py`（A2LedgerHooks docstring）、`reviews/a5_audit/test_a5_audit.py` | 文档/帮助串含机器路径 | 改为 `<python>` 等占位符，不改行为 |

**行为差异**：以上入口在未注入根目录时**立即失败**，不再静默指向本机不存在的路径；唯一保留的历史默认是 `p2a_v2_common._A1_ROOT_HISTORICAL`，已在代码与本文声明，并可用 `RCAIDE_A1_ROOT` 迁移。

## 2. 新增回归测试

`research/concorde_metaopt/tests/test_recovery_path_injection.py`（10 项，全部通过）：

- `p2a_v2.DEFAULT_A1_ROOT is None` 且 `A1_ROOT_ENV == "RCAIDE_A1_ROOT"`；
- 无注入时 `resolve_a1_root()` 抛 `ValueError`，消息含 `RCAIDE_A1_ROOT`；
- 环境变量注入生效；显式参数优先于环境变量；
- `a1_artifact_path` 拼接与 `a1_root` 覆盖正确；
- reload 后模块常量随环境变量变化；
- 历史默认常量形状正确（`D:` 前缀、`wt-real-a1-geometry-solver` 结尾）；
- `a5_audit.main` 在缺 `--s3-root`/环境变量时返回 2；
- `m0r_predraft.ROOT` 随 `RCAIDE_DNEXT_PARENT` reload；
- 静态扫描：`meta/*`、`m1/task_evaluator.py`、`p2a_v2.py`、`m5_runner.py`、`m6_study.py`、preflight 脚本与本测试自身均不含 `D:\RCAIDE` / `D:/RCAIDE` 字面量。

已再次接入 `docs/evidence/drecover001/run_recovery_preflight.py`（suite 计入，SHA 计入 `source_sha256`）。

## 3. 复验

- `pytest research/concorde_metaopt/tests/test_recovery_path_injection.py` → 10 passed。
- 全量软件 preflight：`run_id=DRECOVER001-SOFTWARE-20261117T095835Z`，**187 tests / 0 failed / 0 error / 0 skipped**，physical=0，A5=NOT_PERFORMED，physical_go=NOT_ISSUED，backup_restore=NOT_ESTABLISHED。见 [recovery_preflight_receipt.json](<.worktrees/drecover001-20261117/docs/evidence/drecover001/recovery_preflight_receipt.json>)。
- `p2a_v2` / `p2a_v2_common` / `a5_audit` 导入冒烟通过；`p2a_v2_common.A1_PAIR_MANIFEST_PATH` 在无注入时返回历史绑定（已声明行为）。

## 4. 仍含机器路径的代码文件（披露，不冒充已注入）

恢复代码目录（排除 `optimization_runs/`）中仍出现 `D:/RCAIDE` 的代码文件共 6 个：

1. `dreal001/meta/m0r_predraft.py`：仅注释中描述历史草稿，代码路径已改为注入。
2. `dreal001/optimizers/p2a_v2_common.py`：已声明的历史默认常量，供已签 plan SHA 复现，可被环境变量覆盖。
3. `tests/test_audit.py`、`tests/test_gpu_benchmark.py`、`tests/test_repo_isolation_check.py`：旧 A4 fixture 样例串，属冻结历史测试，按原样保留。
4. `tests/test_recovery_path_injection.py`：markers 由字符串拼接产生，静态扫描已覆盖自身（不计为命中）。

这些文件均不参与"干净目录恢复"判定；R1 的 fresh-clone 软件回归仍待真正从远端 clone 的执行（当前 git 无 author identity、无法连 github.com，未 push）。

## 5. 未完成

- 未做 commit / push：git 无 author identity，且 `git fetch/push` 报 `schannel: SEC_E_NO_CREDENTIALS`，远端不可复核。所有改动只在工作树。
- 未在真正干净 clone 上跑：本轮用同一工作树 + 注入环境变量验证；fresh-clone 回归仍属 A4 未闭环项。
- 历史证据（`docs/`、`optimization_runs/`、旧 runs）一律未改。
