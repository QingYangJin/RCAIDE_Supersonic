#!/usr/bin/env python
r"""D-NEXT-001 Lead 集成门禁审计（只读）。

对五条专题分支 + 集成分支执行机械可复核的集成门禁检查：
  1) 分支起点必须是基线 commit（ea8ad97...），无 main/其他线合并提交；
  2) 冻结产物（S1/S2/S3 evidence、既有 optimization_runs、data、aircraft）不得修改/删除/改名；
  3) 新增代码不得启动真实求解器（VSPAERO / OpenVSP / SU2 / RCAIDE Mission / WaveDrag）；
  4) 新增 run 产物中的 physical_call_count 必须为 0；
  5) 各 worktree 工作区洁净（无未提交改动 = 交付完成态）。

用法:
  python scripts/dnext001_lead_gate_audit.py --repo D:\RCAIDE\dnext001\repo [--json out.json]
退出码: 0 = 全部 PASS；1 = 存在 VIOLATION；2 = 审计执行错误。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

BASE = "ea8ad97833eb5ceab291faae643c141a2b219749"
PREFIX = "research/dnext001-"
FROZEN_PREFIXES = (
    "research/concorde_metaopt/evidence/",
    "research/concorde_metaopt/optimization_runs/",
    "research/concorde_metaopt/data/",
    "research/concorde_metaopt/aircraft/",
)
# 明确允许的新 run 目录前缀（新增，不覆盖既有）
ALLOWED_NEW_PREFIXES = (
    "research/concorde_metaopt/optimization_runs/dnext001-",
)
SOLVER_RE = re.compile(
    r"(vspaero|openvsp|SU2_CFD|SU2_|su2\s|solve_script|vsp\s+-|mission\.py|WaveDrag|wave_drag)",
    re.IGNORECASE,
)
LAUNCH_RE = re.compile(r"(subprocess|os\.system|Popen|call\(|check_output|run\(|Start-Process|& )")
CODE_SUFFIXES = {".py", ".ps1", ".sh", ".bat", ".cmd"}


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


def worktrees(repo: Path) -> dict[str, Path]:
    """branch -> worktree path"""
    mapping: dict[str, Path] = {}
    cur: dict[str, str] = {}
    for line in git(repo, "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):]}
        elif line.startswith("branch "):
            ref = line[len("branch "):]
            if ref.startswith("refs/heads/"):
                mapping[ref[len("refs/heads/"):]] = Path(cur["path"])
        elif line == "":
            cur = {}
    return mapping


@dataclass
class BranchReport:
    branch: str
    worktree: str | None = None
    head: str | None = None
    ahead_of_base: int = 0
    starts_at_base: bool = False
    merge_commits: list[str] = field(default_factory=list)
    changed: list[tuple[str, str]] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dirty: list[str] = field(default_factory=list)


def audit_branch(repo: Path, branch: str, wt: Path | None) -> BranchReport:
    rep = BranchReport(branch=branch, worktree=str(wt) if wt else None)
    rep.head = git(repo, "rev-parse", branch).strip()
    rep.starts_at_base = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", BASE, branch]
    ).returncode == 0
    if not rep.starts_at_base:
        rep.violations.append(f"分支历史不包含基线 {BASE[:12]}")
    rep.merge_commits = [l for l in git(repo, "rev-list", "--merges", f"{BASE}..{branch}").splitlines() if l]
    for m in rep.merge_commits:
        subj = git(repo, "log", "-1", "--format=%s", m).strip()
        rep.violations.append(f"存在合并提交 {m[:12]}: {subj}（禁止 main/跨线合并）")

    numstat = git(repo, "diff", "--numstat", f"{BASE}...{branch}")
    stat = git(repo, "diff", "--name-status", f"{BASE}...{branch}")
    rep.changed = [tuple(l.split("\t")[:2]) for l in stat.splitlines() if l.strip()]
    rep.ahead_of_base = len(git(repo, "rev-list", f"{BASE}..{branch}").splitlines())

    # 冻结产物 / 求解器启动检查
    for status, path in rep.changed:
        st = status[0]
        if any(path.startswith(p) for p in FROZEN_PREFIXES):
            if any(path.startswith(p) for p in ALLOWED_NEW_PREFIXES) and st == "A":
                continue
            if st in {"M", "D", "R", "T"}:
                rep.violations.append(f"冻结产物被修改({st}): {path}")
            else:
                rep.warnings.append(f"冻结目录内新增文件({st}): {path}")

    # 扫描新增行（代码文件）中的真实求解器启动
    diff = git(repo, "diff", f"{BASE}...{branch}", "--", "*.py", "*.ps1", "*.sh", "*.bat", "*.cmd")
    cur_file = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            cur_file = line[len("+++ b/"):]
        elif line.startswith("+") and not line.startswith("+++"):
            added = line[1:]
            if SOLVER_RE.search(added) and LAUNCH_RE.search(added):
                rep.violations.append(f"疑似真实求解器启动: {cur_file}: {added.strip()[:120]}")

    # physical_call_count 非 0 检查（新增 json/csv）
    for status, path in rep.changed:
        if status[0] != "A" or not path.endswith((".json", ".jsonl", ".csv")):
            continue
        if not (path.startswith("research/concorde_metaopt/optimization_runs/") or path.startswith("research/concorde_metaopt/gpu/")):
            continue
        blob = git(repo, "show", f"{branch}:{path}")
        for m in re.finditer(r"physical_call_count\D{0,8}(\d+)", blob):
            if int(m.group(1)) != 0:
                rep.violations.append(f"physical_call_count={m.group(1)} 非 0: {path}")

    if wt and wt.exists():
        dirty = git(wt, "status", "--porcelain").splitlines()
        rep.dirty = [d for d in dirty if d.strip()]
        if rep.dirty:
            rep.violations.append(f"工作区不洁净（{len(rep.dirty)} 项未提交）")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"D:\RCAIDE\dnext001\repo")
    ap.add_argument("--json", default=None)
    ap.add_argument("--include-integration", action="store_true", default=True)
    args = ap.parse_args()
    repo = Path(args.repo)
    wts = worktrees(repo)
    branches = [b for b in wts if b.startswith(PREFIX)]
    order = ["f-real-evaluator", "a-warmstart", "b-meta-acquisition", "gpu-benchmark", "a5-review", "integration"]
    branches.sort(key=lambda b: next((i for i, k in enumerate(order) if b.endswith(k)), 99))

    reports = [audit_branch(repo, b, wts.get(b)) for b in branches]
    payload = {
        "base": BASE,
        "branches": [
            {
                "branch": r.branch,
                "worktree": r.worktree,
                "head": r.head,
                "commits_ahead": r.ahead_of_base,
                "starts_at_base": r.starts_at_base,
                "merge_commits": r.merge_commits,
                "files_changed": len(r.changed),
                "violations": r.violations,
                "warnings": r.warnings,
                "dirty_entries": len(r.dirty),
            }
            for r in reports
        ],
    }
    payload["verdict"] = "PASS" if all(not r.violations for r in reports) else "VIOLATION"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8")
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
