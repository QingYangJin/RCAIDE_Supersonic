"""仓库隔离可复跑检查（worktree / 分支 / 写作用域 / 冻结产物 / 链接逃逸）。

用途
----
在 A4 工作树内独立复核"多 worktree 并行开发是否互不越界"，输出机器可读 JSON +
中文 Markdown 报告，可反复运行、结果可 diff。它证明的只是**结构性与可观测**事实：

* 通过则说明：各 worktree 的 .git 接线正确且唯一、分支唯一、无 pull/merge 提交、
  当前分支没有 upstream 跟踪、工作区改动都落在声明的作用域内、冻结产物未被触碰、
  worktree 根目录没有指向树外的 junction/symlink。
* 不能说明：其他 agent 是否在**它们自己的**工作树里写过东西（那属于对方作用域）、
  本地是否曾 push（离线无法验证远端状态）。因此本检查**不能替代 A5 的独立复核**。

只读脚本：只调用 git 查询命令与文件系统读取，不写仓库、不改分支。
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_BASE = "ea8ad97833eb5ceab291faae643c141a2b219749"
FROZEN_PREFIXES = (
    "research/concorde_metaopt/optimization_runs/",
    "research/concorde_metaopt/evidence/",
    "research/concorde_metaopt/reports/",
    "docs/receipts/",
)
SKIP_TOP_LEVEL = {".git"}


@dataclass
class Check:
    check_id: str
    ok: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


def git(args: list[str], cwd: Path) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def parse_worktrees(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    if current:
        entries.append(current)
    return entries


def is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _relative_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def check_worktree_layout(common_repo: Path) -> tuple[list[Check], list[dict[str, str]]]:
    checks: list[Check] = []
    code, out = git(["worktree", "list", "--porcelain"], common_repo)
    if code != 0:
        return [Check("git_worktree_list", False, "git worktree list 失败：" + out.strip())], []
    entries = parse_worktrees(out)
    paths = [Path(entry.get("worktree", "")) for entry in entries]
    branches = [entry.get("branch", "") for entry in entries]

    checks.append(
        Check(
            "worktree_list_available",
            len(entries) >= 2,
            "发现 " + str(len(entries)) + " 个 worktree：" + ", ".join(str(path) for path in paths),
            {"count": len(entries), "paths": [str(path) for path in paths]},
        )
    )
    checks.append(
        Check(
            "worktree_paths_unique",
            len(set(str(path).lower() for path in paths)) == len(paths),
            "worktree 路径唯一"
            if len(set(str(p).lower() for p in paths)) == len(paths)
            else "存在重复 worktree 路径",
            {"paths": [str(path) for path in paths]},
        )
    )
    linked_branches = [branch for branch in branches if branch.startswith("refs/heads/")]
    unique = len(set(linked_branches)) == len(linked_branches)
    checks.append(
        Check(
            "worktree_branches_unique",
            unique,
            "每个 worktree 的检出分支互不相同" if unique else "分支重复：" + str(linked_branches),
            {"branches": linked_branches},
        )
    )

    # .git 接线：linked worktree 的 .git 必须是指向 common gitdir/worktrees/<name> 的文件，
    # 且该目录下的 gitdir 回指本 worktree，防止两个 worktree 误共享同一私有目录。
    wiring_errors: list[str] = []
    wiring_evidence: dict[str, Any] = {}
    for entry in entries:
        path = Path(entry.get("worktree", ""))
        git_marker = path / ".git"
        if path.resolve() == common_repo.resolve():
            wiring_evidence[str(path)] = "main worktree (.git 目录)"
            continue
        if not git_marker.is_file():
            wiring_errors.append(str(path) + " 的 .git 不是文件")
            continue
        content = git_marker.read_text(encoding="utf-8", errors="replace").strip()
        if not content.startswith("gitdir:"):
            wiring_errors.append(str(path) + "/.git 缺少 gitdir: 前缀")
            continue
        target = Path(content.split("gitdir:", 1)[1].strip())
        if not target.is_absolute():
            target = (path / target).resolve()
        wiring_evidence[str(path)] = str(target)
        if not target.exists():
            wiring_errors.append(str(path) + " 的 gitdir 目标不存在：" + str(target))
            continue
        back = target / "gitdir"
        if not back.exists():
            wiring_errors.append(str(target) + " 缺少 gitdir 回指文件")
            continue
        back_target = (target / back.read_text(encoding="utf-8", errors="replace").strip()).resolve()
        if back_target != (path / ".git").resolve():
            wiring_errors.append(
                str(target) + " 的 gitdir 回指 " + str(back_target) + " 与本 worktree 不匹配"
            )
    checks.append(
        Check(
            "worktree_gitdir_wiring",
            not wiring_errors,
            "linked worktree 的 gitdir 接线全部正确" if not wiring_errors else "；".join(wiring_errors),
            wiring_evidence,
        )
    )

    # 链接逃逸：worktree 顶层若存在 junction/symlink，其真实目标不得在本树之外。
    escape_errors: list[str] = []
    link_evidence: dict[str, str] = {}
    for entry in entries:
        root = Path(entry.get("worktree", ""))
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if child.name in SKIP_TOP_LEVEL:
                continue
            if os.path.islink(child) or is_reparse_point(child):
                real = child.resolve()
                link_evidence[str(child)] = str(real)
                if not _relative_inside(real, root):
                    escape_errors.append(str(child) + " -> " + str(real) + " 指向本树之外")
    checks.append(
        Check(
            "no_cross_tree_links",
            not escape_errors,
            "worktree 顶层无越界链接" if not escape_errors else "；".join(escape_errors),
            link_evidence,
        )
    )
    return checks, entries


def check_branch_hygiene(
    entries: list[dict[str, str]],
    base: str,
    current_branch: str,
    current_worktree: Path,
) -> list[Check]:
    """分支卫生：只对**当前工作树分支**判定 PASS/FAIL，其他分支仅作观察记录。

    角色边界：A4 只能为自己分支的提交行为负责。wt-lead 的集成分支可能包含合并
    提交（例如合并 A5 分支），那属于 Lead 作用域；如让 A4 的隔离检查因此失败，
    等于把别人的行为算到本角色头上。因此对"其他分支"只记录、不判定。
    """
    checks: list[Check] = []
    merge_counts: dict[str, int] = {}
    upstreams: dict[str, str] = {}
    base_errors: list[str] = []
    for entry in entries:
        branch_ref = entry.get("branch", "")
        if not branch_ref.startswith("refs/heads/"):
            continue
        branch = branch_ref[len("refs/heads/"):]
        cwd = Path(entry["worktree"])
        code, out = git(["rev-list", "--merges", base + "..HEAD", "--count"], cwd)
        if code != 0:
            base_errors.append(branch + ": " + out.strip())
            continue
        merge_counts[branch] = int(out.strip() or 0)
        code, out = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd)
        if code == 0 and out.strip():
            upstreams[branch] = out.strip()

    code, out = git(["merge-base", "--is-ancestor", base, "HEAD"], current_worktree)
    ancestor_ok = code == 0
    checks.append(
        Check(
            "base_is_ancestor_of_head",
            ancestor_ok and not base_errors,
            "基线 commit 是当前分支的祖先"
            if ancestor_ok and not base_errors
            else "基线 commit 不是当前分支祖先，或查询失败：" + "；".join(base_errors or [out.strip()]),
            {"base": base, "is_ancestor": ancestor_ok, "errors": base_errors},
        )
    )

    current_merges = merge_counts.get(current_branch, 0)
    checks.append(
        Check(
            "no_merge_commits_current_branch",
            current_merges == 0 and current_branch in merge_counts,
            "当前分支 " + current_branch + " 在基线之后无 merge commit"
            if current_merges == 0
            else "当前分支存在 " + str(current_merges) + " 个 merge commit",
            {"branch": current_branch, "merge_count": current_merges},
        )
    )

    main_merged: list[dict[str, Any]] = []
    code, out = git(["rev-parse", "--verify", "main"], current_worktree)
    main_exists = code == 0
    if main_exists:
        code, merges_out = git(["rev-list", "--merges", base + "..HEAD"], current_worktree)
        for merge in merges_out.split():
            code, parents_out = git(["rev-list", "--parents", "-n", "1", merge], current_worktree)
            parents = parents_out.split()[1:]
            for parent in parents:
                code, _ = git(["merge-base", "--is-ancestor", parent, "main"], current_worktree)
                if code == 0:
                    main_merged.append({"merge": merge, "main_parent": parent})
                    break
    checks.append(
        Check(
            "no_main_merge_into_current",
            not main_merged,
            "当前分支未把 main 合并进来" if not main_merged else "当前分支包含来自 main 的合并：" + str(main_merged),
            {"main_exists": main_exists, "offenders": main_merged},
        )
    )

    code, head_upstream = git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], current_worktree
    )
    has_upstream = code == 0 and bool(head_upstream.strip())
    checks.append(
        Check(
            "current_branch_no_upstream",
            not has_upstream,
            "当前分支未配置 upstream（本地提交，未推送）" if not has_upstream else "当前分支有 upstream：" + head_upstream.strip(),
            {"upstream": head_upstream.strip() if has_upstream else None},
        )
    )

    others_with_merges = {
        branch: count for branch, count in merge_counts.items() if branch != current_branch and count
    }
    checks.append(
        Check(
            "other_branch_merges_observed",
            True,
            "其他分支合并情况（仅记录，不判定）：" + (str(others_with_merges) if others_with_merges else "无"),
            {
                "merge_counts": merge_counts,
                "upstreams": upstreams,
                "note": "其他 worktree 分支的提交行为属于对应角色作用域，本检查不代替其自证，也不代替 A5 独立复核。",
            },
        )
    )
    return checks


def check_write_scope(
    current: Path, base: str, allowed_prefixes: tuple[str, ...]
) -> list[Check]:
    checks: list[Check] = []
    outside: list[str] = []
    code, out = git(["status", "--porcelain=v1", "--untracked-files=all"], current)
    if code != 0:
        return [Check("write_scope", False, "git status 失败：" + out.strip())]
    changed = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:  # 重命名
            path = path.split(" -> ", 1)[1]
        changed.append(path.replace("\\", "/"))
    for path in changed:
        if not any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in allowed_prefixes):
            outside.append(path)
    checks.append(
        Check(
            "write_scope_uncommitted",
            not outside,
            "未提交改动 " + str(len(changed)) + " 个文件，全部在声明作用域内"
            if not outside
            else "作用域外改动：" + str(outside),
            {"changed": changed, "outside": outside, "allowed": list(allowed_prefixes)},
        )
    )

    code, out = git(["diff", "--name-only", base + "..HEAD"], current)
    committed = [line.replace("\\", "/") for line in out.splitlines() if line.strip()]
    leaked = [path for path in committed if not any(path.startswith(prefix) for prefix in allowed_prefixes)]
    checks.append(
        Check(
            "write_scope_committed",
            not leaked,
            "基线以来提交改动 " + str(len(committed)) + " 个文件，全部在声明作用域内"
            if not leaked
            else "提交中作用域外文件：" + str(leaked),
            {"committed": committed, "leaked": leaked},
        )
    )

    code, out = git(["diff", "--name-only", base + "..HEAD", "--", *FROZEN_PREFIXES], current)
    frozen_touched = [line for line in out.splitlines() if line.strip()]
    checks.append(
        Check(
            "frozen_artifacts_untouched",
            not frozen_touched,
            "冻结产物目录在基线之后无改动"
            if not frozen_touched
            else "冻结产物被改动：" + str(frozen_touched),
            {"base": base, "touched": frozen_touched, "frozen_prefixes": list(FROZEN_PREFIXES)},
        )
    )
    return checks


def evaluate(
    current: Path,
    base: str,
    allowed_prefixes: tuple[str, ...],
    expect_branch: str | None,
) -> dict[str, Any]:
    code, out = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], current)
    common_dir = Path(out.strip()) if code == 0 else None
    common_repo = common_dir.parent if common_dir else current

    checks: list[Check] = []
    if not common_repo.is_dir():
        checks.append(Check("common_repo_found", False, "未找到 common repo：" + str(common_repo)))
        entries: list[dict[str, str]] = []
    else:
        layout_checks, entries = check_worktree_layout(common_repo)
        checks.extend(layout_checks)

    code, branch_out = git(["rev-parse", "--abbrev-ref", "HEAD"], current)
    current_branch = branch_out.strip() if code == 0 else "UNKNOWN"
    if expect_branch:
        checks.append(
            Check(
                "current_worktree_branch",
                current_branch == expect_branch,
                "当前分支 " + current_branch + "（期望 " + expect_branch + "）",
                {"branch": current_branch, "expected": expect_branch},
            )
        )
    else:
        checks.append(Check("current_worktree_branch", True, "当前分支 " + current_branch))

    checks.extend(check_branch_hygiene(entries, base, current_branch, current))
    checks.extend(check_write_scope(current, base, allowed_prefixes))

    code, head_out = git(["rev-parse", "HEAD"], current)
    payload = {
        "kind": "repo_isolation_check",
        "physical_call_count": 0,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "common_repo": str(common_repo),
        "current_worktree": str(current),
        "current_branch": current_branch,
        "head": head_out.strip() if code == 0 else "UNKNOWN",
        "base": base,
        "allowed_prefixes": list(allowed_prefixes),
        "checks": [check.__dict__ for check in checks],
        "all_passed": all(check.ok for check in checks),
        "scope_note": (
            "本检查只证明结构性与可观测事实；不能证明其他 agent 未在其自身工作树写入，"
            "也无法离线验证是否 push 过远端，因此不替代 A5 独立复核。"
        ),
    }
    return payload


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 仓库隔离可复跑检查报告",
        "",
        "* 生成时间（UTC）：" + payload["generated_at_utc"],
        "* common repo：" + payload["common_repo"],
        "* 当前工作树：" + payload["current_worktree"] + "（分支 " + payload["current_branch"] + "，HEAD " + payload["head"] + "）",
        "* 基线 commit：" + payload["base"],
        "* 结论：**" + ("全部通过" if payload["all_passed"] else "存在失败项") + "**",
        "",
        "| 检查项 | 结果 | 说明 |",
        "| --- | --- | --- |",
    ]
    for check in payload["checks"]:
        status = "PASS" if check["ok"] else "FAIL"
        detail = str(check["detail"]).replace("|", "\\|")
        lines.append("| " + check["check_id"] + " | " + status + " | " + detail + " |")
    lines.extend(["", "> " + payload["scope_note"], ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="要检查的 worktree")
    parser.add_argument("--base", default=DEFAULT_BASE, help="基线 commit")
    parser.add_argument(
        "--allowed-prefix",
        action="append",
        default=None,
        help="允许的写作用域前缀（可多次指定）",
    )
    parser.add_argument("--expect-branch", default="research/dnext001-gpu-benchmark")
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--out-md", type=Path, default=None)
    arguments = parser.parse_args(argv)
    arguments.cwd = arguments.cwd.resolve()
    allowed = tuple(arguments.allowed_prefix or (
        "research/concorde_metaopt/gpu/",
        "docs/planning/dnext001_gpu_",
        "docs/receipts/dnext001/a4_",
        "research/concorde_metaopt/tests/test_gpu_benchmark.py",
        "research/concorde_metaopt/tests/test_repo_isolation_check.py",
    ))
    payload = evaluate(arguments.cwd, arguments.base, allowed, arguments.expect_branch)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if arguments.out_json:
        arguments.out_json.parent.mkdir(parents=True, exist_ok=True)
        arguments.out_json.write_text(text, encoding="utf-8")
    if arguments.out_md:
        arguments.out_md.parent.mkdir(parents=True, exist_ok=True)
        arguments.out_md.write_text(render_markdown(payload), encoding="utf-8")
    print(text)
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
