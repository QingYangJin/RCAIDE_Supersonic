# GitHub 连接检查（2026-11-18，只读诊断）

本文件只记录连接/凭据可用性，不包含任何 token 值，也不改变门禁状态。

## 结论

- **只读 API 可用**：通过会话的 GitHub API 工具可读取 Issue #12；检查时状态 `open`、0 comments、标题与 2026-11-17 创建时一致。
- **git 传输不可用**：`git ls-remote origin HEAD` 退出码 128，错误为
  `fatal: unable to access 'https://github.com/QingYangJin/RCAIDE_Supersonic.git/': schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)`。
  因此未 fetch、未 push、未创建远端 commit。
- **SSH 不可用**：22 端口可达但 `git@github.com: Permission denied (publickey)`，本机用户目录下没有可用 SSH 密钥。
- **无提交身份**：`git config user.name/user.email` 均未设置。
- **无 gh CLI**：会话工具可读 GitHub，但 shell 内没有 `gh` 可执行文件。

## 诊断细节

- remote：`https://github.com/QingYangJin/RCAIDE_Supersonic.git`；credential.helper=manager；本机凭据管理器存在 `git:https://github` 条目，但 schannel 仍报无凭据。
- Git 2.56.0.windows.3 的 `http.sslBackend` 只支持 schannel；本机没有可切换的 openssl 后端（通过代理时 openssl 报 `unexpected eof while reading`）。
- DNS：默认解析 github.com 为 57.155.223.240；公共 DNS 8.8.8.8/1.1.1.1 返回 20.247.166.64；`api.github.com` 解析 20.205.243.168，Python HTTPS HEAD 返回 200。TLS 到 github.com:443 可建立但 git 的 schannel 凭据阶段失败。
- 代理 100.109.173.96:7897 端口开放、CONNECT 可建立，但 schannel 仍在凭据阶段失败。

## 影响

- 本轮所有变更只存在于工作树（`recovery/drecover001-20261117`，HEAD `4c51c7df34c9626999ef2e66e5a6c76a2b9c92e2`），远端无法复核；Issue #12 回执仍为草案，未发布。
- 该诊断不授予物理 GO；`physical_solver_starts_actual=0`。
