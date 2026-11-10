"""D-NEXT-001 A4｜仓库隔离可复核脚本的单元测试。

只测纯函数与结构性判定，不写入仓库状态，不访问网络。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research.concorde_metaopt.gpu import repo_isolation_check as ric


SAMPLE_PORCELAIN = """worktree D:/RCAIDE/dnext001/repo
HEAD aaaa1111
branch refs/heads/main

worktree D:/RCAIDE/dnext001/wt-a4
HEAD bbbb2222
branch refs/heads/research/dnext001-gpu-benchmark

worktree D:/RCAIDE/dnext001/wt-detached
HEAD cccc3333
detached
"""


def test_parse_worktrees_extracts_path_head_branch() -> None:
    entries = ric.parse_worktrees(SAMPLE_PORCELAIN)
    assert [e["worktree"] for e in entries] == [
        "D:/RCAIDE/dnext001/repo",
        "D:/RCAIDE/dnext001/wt-a4",
        "D:/RCAIDE/dnext001/wt-detached",
    ]
    assert entries[1]["HEAD"] == "bbbb2222"
    assert entries[1]["branch"] == "refs/heads/research/dnext001-gpu-benchmark"
    # 分离头指针里没有 branch 行，不应被伪造成分支名
    assert "branch" not in entries[2]


def test_frozen_prefixes_cover_evidence_dirs() -> None:
    assert any("optimization_runs" in p for p in ric.FROZEN_PREFIXES)
    assert any("evidence" in p for p in ric.FROZEN_PREFIXES)
    assert any("reports" in p for p in ric.FROZEN_PREFIXES)
    assert any("docs/receipts" in p for p in ric.FROZEN_PREFIXES)


def test_relative_inside_only_matches_true_descendants(tmp_path: Path) -> None:
    parent = tmp_path / "wt-a4"
    child = parent / "research" / "concorde_metaopt" / "gpu" / "x.py"
    child.parent.mkdir(parents=True)
    child.write_text("x", encoding="utf-8")
    assert ric._relative_inside(child, parent) is True
    assert ric._relative_inside(parent, child) is False


def test_render_markdown_of_failing_payload_says_failed() -> None:
    payload = {
        "kind": "repo_isolation_check",
        "generated_at_utc": "2026-11-10T06:19:00+00:00",
        "common_repo": "D:/RCAIDE/dnext001/repo",
        "current_worktree": "D:/RCAIDE/dnext001/wt-a4",
        "current_branch": "research/dnext001-gpu-benchmark",
        "head": "b" * 40,
        "base": "a" * 40,
        "all_passed": False,
        "checks": [
            {"check_id": "demo_fail", "ok": False, "detail": "演示失败", "evidence": {}},
            {"check_id": "demo_pass", "ok": True, "detail": "演示通过", "evidence": {}},
        ],
        "scope_note": "仅结构性事实",
        "physical_call_count": 0,
    }
    md = ric.render_markdown(payload)
    assert "存在失败项" in md
    assert "| demo_fail | FAIL |" in md
    assert "| demo_pass | PASS |" in md


def test_render_markdown_of_passing_payload() -> None:
    payload = {
        "kind": "repo_isolation_check",
        "generated_at_utc": "2026-11-10T06:19:00+00:00",
        "common_repo": "r",
        "current_worktree": "w",
        "current_branch": "b",
        "head": "h" * 40,
        "base": "b" * 40,
        "all_passed": True,
        "checks": [{"check_id": "ok", "ok": True, "detail": "fine", "evidence": {}}],
        "scope_note": "n",
        "physical_call_count": 0,
    }
    json.dumps(payload, ensure_ascii=False)  # 不抛异常
    md = ric.render_markdown(payload)
    assert "全部通过" in md
    assert isinstance(md, str)


def test_evaluate_marks_this_tree_without_writing() -> None:
    """在本工作树上跑一次真实检查：不写文件、返回结构完整、当前分支名正确。"""
    payload = ric.evaluate(
        Path("D:/RCAIDE/dnext001/wt-a4").resolve(),
        ric.DEFAULT_BASE,
        (
            "research/concorde_metaopt/gpu/",
            "docs/planning/dnext001_gpu_",
            "docs/receipts/dnext001/a4_",
            "research/concorde_metaopt/tests/test_gpu_benchmark.py",
            "research/concorde_metaopt/tests/test_repo_isolation_check.py",
        ),
        "research/dnext001-gpu-benchmark",
    )
    ids = {check["check_id"] for check in payload["checks"]}
    assert "worktree_paths_unique" in ids
    assert "no_merge_commits_current_branch" in ids
    assert "frozen_artifacts_untouched" in ids
    assert payload["current_branch"] == "research/dnext001-gpu-benchmark"
    assert payload["physical_call_count"] == 0
    assert isinstance(payload["all_passed"], bool)
