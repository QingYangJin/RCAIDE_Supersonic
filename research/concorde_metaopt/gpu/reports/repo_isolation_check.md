# 仓库隔离可复跑检查报告

* 生成时间（UTC）：2026-11-10T06:37:18.895657+00:00
* common repo：D:\RCAIDE\dnext001\repo
* 当前工作树：D:\RCAIDE\dnext001\wt-a4（分支 research/dnext001-gpu-benchmark，HEAD 1f492f727fad0abf4489434f675b526cc9c8e463）
* 基线 commit：ea8ad97833eb5ceab291faae643c141a2b219749
* 结论：**全部通过**

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| worktree_list_available | PASS | 发现 7 个 worktree：D:\RCAIDE\dnext001\repo, D:\RCAIDE\dnext001\wt-a1, D:\RCAIDE\dnext001\wt-a2, D:\RCAIDE\dnext001\wt-a3, D:\RCAIDE\dnext001\wt-a4, D:\RCAIDE\dnext001\wt-a5, D:\RCAIDE\dnext001\wt-lead |
| worktree_paths_unique | PASS | worktree 路径唯一 |
| worktree_branches_unique | PASS | 每个 worktree 的检出分支互不相同 |
| worktree_gitdir_wiring | PASS | linked worktree 的 gitdir 接线全部正确 |
| no_cross_tree_links | PASS | worktree 顶层无越界链接 |
| current_worktree_branch | PASS | 当前分支 research/dnext001-gpu-benchmark（期望 research/dnext001-gpu-benchmark） |
| base_is_ancestor_of_head | PASS | 基线 commit 是当前分支的祖先 |
| no_merge_commits_current_branch | PASS | 当前分支 research/dnext001-gpu-benchmark 在基线之后无 merge commit |
| no_main_merge_into_current | PASS | 当前分支未把 main 合并进来 |
| current_branch_no_upstream | PASS | 当前分支未配置 upstream（本地提交，未推送） |
| other_branch_merges_observed | PASS | 其他分支合并情况（仅记录，不判定）：{'research/dnext001-integration': 4} |
| write_scope_uncommitted | PASS | 未提交改动 4 个文件，全部在声明作用域内 |
| write_scope_committed | PASS | 基线以来提交改动 52 个文件，全部在声明作用域内 |
| frozen_artifacts_untouched | PASS | 冻结产物目录在基线之后无改动（receipts 仅允许新增回执） |

> 本检查只证明结构性与可观测事实；不能证明其他 agent 未在其自身工作树写入，也无法离线验证是否 push 过远端，因此不替代 A5 独立复核。
