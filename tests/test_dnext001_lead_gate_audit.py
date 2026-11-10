"""Lead 集成门禁审计脚本的自测（合成 git 仓库，不含真实求解）。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dnext001_lead_gate_audit as audit


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if check and out.returncode != 0:
        raise RuntimeError(out.stderr)
    return out


def _make_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.com")
    (repo / "research/concorde_metaopt/evidence/s3").mkdir(parents=True)
    (repo / "research/concorde_metaopt/evidence/s3/gate.json").write_text('{"status":"NOT_ISSUED"}\n', encoding="utf-8")
    (repo / "research/concorde_metaopt/optimization").mkdir(parents=True)
    (repo / "research/concorde_metaopt/optimization/baseline_bo.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base


def test_clean_branch_and_violating_branch(tmp_path, monkeypatch):
    repo, base = _make_repo(tmp_path)
    monkeypatch.setattr(audit, "BASE", base)

    # 干净分支：仅新增文件
    _git(repo, "checkout", "-q", "-b", "research/dnext001-a-warmstart")
    (repo / "research/concorde_metaopt/warm_start.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "clean")

    # 违规分支：修改冻结文件 + 疑似真实求解器启动 + physical_call_count!=0
    _git(repo, "checkout", "-q", "main")
    _git(repo, "checkout", "-q", "-b", "research/dnext001-f-real-evaluator")
    (repo / "research/concorde_metaopt/evidence/s3/gate.json").write_text('{"status":"PASS"}\n', encoding="utf-8")
    (repo / "research/concorde_metaopt/run_solver.py").write_text(
        "import subprocess\nsubprocess.run(['vspaero', 'case.vspaero'])\n", encoding="utf-8"
    )
    run_dir = repo / "research/concorde_metaopt/optimization_runs/fake-run"
    run_dir.mkdir(parents=True)
    (run_dir / "run_config.json").write_text('{"physical_call_count": 3}\n', encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "bad")

    clean = audit.audit_branch(repo, "research/dnext001-a-warmstart", repo)
    bad = audit.audit_branch(repo, "research/dnext001-f-real-evaluator", repo)

    assert clean.violations == [], clean.violations
    assert any("冻结产物" in v for v in bad.violations), bad.violations
    assert any("求解器启动" in v for v in bad.violations), bad.violations
    assert any("physical_call_count" in v for v in bad.violations), bad.violations


def test_merge_commit_detected(tmp_path, monkeypatch):
    repo, base = _make_repo(tmp_path)
    monkeypatch.setattr(audit, "BASE", base)
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "side.txt").write_text("s\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "side")
    _git(repo, "checkout", "-q", "main")
    (repo / "main2.txt").write_text("m\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main2")
    _git(repo, "merge", "-q", "--no-ff", "side", "-m", "merge side", check=True)
    _git(repo, "checkout", "-q", "-b", "research/dnext001-integration")

    rep = audit.audit_branch(repo, "research/dnext001-integration", repo)
    assert rep.merge_commits, rep
    assert any("合并提交" in v for v in rep.violations), rep.violations
