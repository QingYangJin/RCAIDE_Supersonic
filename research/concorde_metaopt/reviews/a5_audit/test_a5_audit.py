r"""A5 复核脚本单测：只读、纯 stdlib、构造最小合成证据包做断言回归。

运行：
  & D:\RCAIDE\envs\RCAIDE\python.exe -m pytest research/concorde_metaopt/reviews/a5_audit -q
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[0] / "a5_audit.py"
SPEC = importlib.util.spec_from_file_location("a5_audit_under_test", SCRIPT)
a5 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(a5)

REL = Path("research/concorde_metaopt/evidence/s3")


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        # 用 bytes 写入以精确控制行尾（Windows 文本模式会把 \n 翻译成 \r\n）
        path.write_bytes(data.encode("utf-8"))


def _build_package(tmp_path: Path, *, crlf: bool = False) -> Path:
    root = tmp_path / "repo"
    text_a = "alpha-证据\n"
    text_b = "beta\n"
    _write(root / REL / "a.json", text_a)
    _write(root / REL / "b.txt", text_b.replace("\n", "\r\n") if crlf else text_b)
    entries = []
    for rel, text in (("a.json", text_a), ("b.txt", text_b)):
        target = root / REL / rel
        body = target.read_bytes()
        normalized = body.replace(b"\r\n", b"\n") if target.suffix != ".png" else body
        entries.append((__import__("hashlib").sha256(normalized).hexdigest(), str(REL / rel)))
    _write(root / REL / "SHA256SUMS.txt", "".join(d + "  " + p + "\n" for d, p in entries))
    manifest = {
        "schema_version": "p4ra-s3-evidence-package-1",
        "physical_call_count": 0,
        "solver_processes_started": 0,
        "counts": {"files": len(entries), "bytes_raw_total": sum((root / p).stat().st_size for _, p in entries)},
        "eol_summary": {"crlf_count": 1 if crlf else 0},
        "files": [{"path": p} for _, p in entries],
    }
    _write(root / REL / "PACKAGE_MANIFEST.json", json.dumps(manifest, ensure_ascii=False))
    return root


def test_canonical_sha_is_key_order_independent():
    assert a5.canonical_sha256({"b": 1, "a": 2}) == a5.canonical_sha256({"a": 2, "b": 1})
    assert a5.canonical_sha256({"a": 1}) != a5.canonical_sha256({"a": 2})


def test_binary_files_are_not_crlf_normalized():
    digest = a5.sha256_text("x")
    assert a5.sha256_file_raw(Path(__file__)) != ""
    assert a5.sha256_file_lf(Path(__file__)) == a5.sha256_file_lf(Path(__file__))
    assert digest == a5.sha256_text("x")


def test_normalize_model_rows_drops_bytes_and_path_prefix():
    rows = [{"bytes": 123, "path": "D:/x/models/fomaml_meta_0.json", "sha256": "aa"}]
    normalized = a5._normalize_model_rows(rows)
    assert normalized == [{"path": "models/fomaml_meta_0.json", "sha256": "aa"}]


def test_package_integrity_valid_and_crlf_accounted(tmp_path):
    root = _build_package(tmp_path, crlf=True)
    result = a5.check_package_integrity(root)
    assert result["status"] == a5.VALID
    assert result["metrics"]["sha256_lf_match"] == result["metrics"]["sums_entries"] == 2
    assert result["metrics"]["crlf_declared"] == 1


def test_package_integrity_detects_tamper(tmp_path):
    root = _build_package(tmp_path)
    _write(root / REL / "a.json", "tampered\n")
    result = a5.check_package_integrity(root)
    assert result["status"] == a5.FAIL
    assert result["metrics"]["mismatch"] >= 1


def test_physical_zero_valid_then_fail(tmp_path):
    root = _build_package(tmp_path)
    _write(root / REL / "run/run_config.json", json.dumps({"physical_call_count": 0}))
    assert a5.check_physical_zero(root)["status"] == a5.VALID
    _write(root / REL / "run/run_config.json", json.dumps({"physical_call_count": 3}))
    assert a5.check_physical_zero(root)["status"] == a5.FAIL


def test_figures_valid_with_six_rendered(tmp_path):
    root = _build_package(tmp_path)
    figures = {}
    for index in range(1, 11):
        name = "fig" + str(index)
        rendered = index in (3, 4, 5, 6, 8, 9)
        figures[name] = {"status": "RENDERED" if rendered else "NOT_RUN"}
        if rendered:
            _write(root / REL / "analysis" / (name + ".png"), b"\x89PNG\r\n\x1a\n")
    _write(root / REL / "analysis/figure_status.json", json.dumps({"figures": figures}))
    _write(root / REL / "analysis/figure_generation_summary.json", json.dumps({"cjk_font": "Microsoft YaHei"}))
    result = a5.check_figures(root)
    assert result["status"] == a5.VALID
    assert len(result["metrics"]["rendered"]) == 6
    assert len(result["metrics"]["not_run"]) == 4


def test_downstream_products_not_run_when_empty(tmp_path):
    dnext = tmp_path / "dnext"
    for name in ("wt-a1", "wt-a2", "wt-a3", "wt-a4"):
        (dnext / name / "docs").mkdir(parents=True)
    result = a5.check_downstream_products(dnext)
    assert result["status"] == a5.NOT_RUN


def test_collect_evidence_never_passes_missing_evidence(tmp_path):
    root = _build_package(tmp_path)
    report = a5.collect_evidence(root, tmp_path / "dnext")
    assert report["physical_call_count"] == 0
    assert report["no_pass_by_commit_message"] is True
    for item in report["checks"]:
        assert item["status"] in a5.STATUSES
    statuses = {item["id"]: item["status"] for item in report["checks"]}
    assert statuses["A5-C12"] == a5.NOT_RUN


def test_main_returns_3_for_missing_evidence_root(tmp_path):
    assert a5.main(["--s3-root", str(tmp_path / "missing"), "--dnext-root", str(tmp_path)]) == 3


def test_render_markdown_marks_physical_zero():
    report = {
        "audit_id": "t", "generated_utc": "t", "reviewer_role": "A5",
        "s3_root": "x", "dnext_root": "y", "evidence_mode": "ARCHIVE_REPLAY_READ_ONLY",
        "physical_call_count": 0, "solver_processes_started": 0, "overall_status": a5.VALID,
        "status_counts": {a5.VALID: 1, a5.NOT_VALIDATED: 0, a5.NOT_RUN: 0, a5.FAIL: 0},
        "checks": [{"id": "A5-C02", "name": "physical_zero", "status": a5.VALID, "severity": "blocker",
                    "detail": "ok", "metrics": {}, "evidence": []}],
    }
    text = a5.render_markdown(report)
    assert "physical_call_count = 0" in text
    assert "不得以提交消息代替复现" in text
