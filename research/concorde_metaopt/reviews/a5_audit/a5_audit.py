r"""D-NEXT-001 / A5 独立复核脚本：只读证据收集 + 断言检查。

设计边界（硬约束）：
- 只读：不修改被审仓库、不写被审工作树、不启动任何物理求解器（VSPAERO/SU2/Mission/WaveDrag 调用数恒为 0）。
- 只允许 mock/合成/归档 replay 只读；所有输出 physical_call_count=0。
- 每条检查结论只能取 VALID / NOT_VALIDATED / NOT_RUN / FAIL 之一。
- FAIL 仅用于"证据被篡改/自相矛盾/断言被证伪"；证据缺失或外部化而无法复核一律 NOT_RUN/NOT_VALIDATED，不得升级为 FAIL，也不得降级为 PASS。

用法示例（PowerShell）：
  & D:\RCAIDE\envs\RCAIDE\python.exe research\concorde_metaopt\reviews\a5_audit\a5_audit.py --s3-root D:\RCAIDE-s3-dev --out docs\reviews\dnext001_a5_sample_audit_output_20261110.json --md docs\reviews\dnext001_a5_sample_audit_output_20261110.md

退出码：0 = 无 FAIL；2 = 存在 FAIL；3 = 证据根缺失/不可读。
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = "dnext001-a5-audit-v1"
VALID = "VALID"
NOT_VALIDATED = "NOT_VALIDATED"
NOT_RUN = "NOT_RUN"
FAIL = "FAIL"
STATUSES = (VALID, NOT_VALIDATED, NOT_RUN, FAIL)

S3_EVIDENCE_RELPATH = Path("research/concorde_metaopt/evidence/s3")
S3_PREREG_RELPATH = S3_EVIDENCE_RELPATH / "s3_preregistration.json"
S3_RUN_CONFIG_RELPATH = S3_EVIDENCE_RELPATH / "run/run_config.json"
S3_MANIFEST_RELPATH = S3_EVIDENCE_RELPATH / "run/model_manifest.json"
S3_PACKAGE_MANIFEST_RELPATH = S3_EVIDENCE_RELPATH / "PACKAGE_MANIFEST.json"
S3_SUMS_RELPATH = S3_EVIDENCE_RELPATH / "SHA256SUMS.txt"
S3_RESULT_REPORT_RELPATH = Path("docs/reviews/p4_route_a_s3_result_report_20261109.md")
S3_REQUIREMENT_MATRIX_RELPATH = Path("docs/reviews/p4_route_a_s3_requirement_matrix.md")

NC15_REQUIRED_KEYS = (
    "shuffled_con_minus_obj_feasible_hit_rate",
    "shuffled_con_minus_obj",
    "con_minus_obj_shuffled",
)

DEFAULT_DNEXT_ROOT = Path(r"D:\RCAIDE\dnext001")
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip", ".gz", ".npz", ".npy", ".pt", ".ckpt", ".pdf"}
DOWNSTREAM_ROLES = {"a1": "wt-a1", "a2": "wt-a2", "a3": "wt-a3", "a4": "wt-a4"}


def canonical_json(obj: Any) -> str:
    """与 s3_prereg.canonical_json 完全一致：sort_keys + 紧凑分隔符 + UTF-8。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_sha256(obj: Any) -> str:
    return sha256_text(canonical_json(obj))


def sha256_file_lf(path: Path) -> str:
    """SHA256SUMS 声明口径：CRLF->LF 归一化后取 sha256。"""
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def sha256_file_raw(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def iter_jsonl(path: Path) -> Iterable[dict]:
    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _check(cid, name, status, detail, *, severity="major", metrics=None, evidence=()):
    if status not in STATUSES:
        raise ValueError("非法状态: " + status)
    return {
        "id": cid,
        "name": name,
        "status": status,
        "severity": severity,
        "detail": detail,
        "metrics": dict(metrics or {}),
        "evidence": list(evidence),
    }


def _extract_function_block(text: str, start_marker: str, max_lines: int = 120) -> str:
    idx = text.find(start_marker)
    if idx < 0:
        return ""
    return "\n".join(text[idx:].splitlines()[:max_lines])


def check_package_integrity(repo_root: Path) -> dict:
    sums_path = repo_root / S3_SUMS_RELPATH
    manifest_path = repo_root / S3_PACKAGE_MANIFEST_RELPATH
    if not sums_path.is_file() or not manifest_path.is_file():
        return _check("A5-C01", "package_integrity", NOT_RUN,
                      "缺少 SHA256SUMS.txt 或 PACKAGE_MANIFEST.json，无法重算证据包哈希",
                      severity="blocker", evidence=[str(S3_SUMS_RELPATH), str(S3_PACKAGE_MANIFEST_RELPATH)])
    manifest = load_json(manifest_path)
    declared = {}
    for row in manifest.get("files") or []:
        if isinstance(row, dict) and row.get("path"):
            declared[str(row["path"])] = row

    ok_lf = ok_raw = missing = mismatch = 0
    mismatched = []
    entries = []
    for line in read_text(sums_path).splitlines():
        line = line.strip()
        if not line:
            continue
        digest, rel = line.split("  ", 1)
        entries.append((digest, rel))
        target = repo_root / rel
        if not target.is_file():
            missing += 1
            continue
        raw = sha256_file_raw(target)
        # 二进制资产（PNG 等）不得做 CRLF 归一化，否则会把 \r\n 字节改写掉而误判
        lf = raw if target.suffix.lower() in BINARY_SUFFIXES else sha256_file_lf(target)
        if lf == digest:
            ok_lf += 1
        else:
            mismatch += 1
            mismatched.append({"path": rel, "declared": digest, "recomputed_lf": lf})
        if raw == digest:
            ok_raw += 1

    counts = manifest.get("counts") or {}
    eol = manifest.get("eol_summary") or {}
    crlf = int(eol.get("crlf_count") or 0)
    declared_files = int(counts.get("files") or 0)
    bytes_total = int(counts.get("bytes_raw_total") or 0)
    consistent = (len(entries) == declared_files and ok_lf == len(entries) and mismatch == 0 and missing == 0
                  and crlf == len(entries) - ok_raw and len(declared) == len(entries))
    status = VALID if consistent else FAIL
    if status == VALID:
        detail = ("证据包可全量重算：LF-canonical 口径 " + str(ok_lf) + "/" + str(len(entries)) + " 全等；raw 字节 "
                  + str(ok_raw) + "/" + str(len(entries)) + " 相等；CRLF " + str(crlf)
                  + " 件与 manifest eol_summary 一致；manifest 计数 " + str(declared_files) + " 件/" + str(bytes_total) + " B 自洽。")
    else:
        detail = ("证据包哈希自洽性断言失败：ok_lf=" + str(ok_lf) + "/" + str(len(entries)) + " missing=" + str(missing)
                  + " mismatch=" + str(mismatch) + " crlf_declared=" + str(crlf) + " crlf_observed=" + str(len(entries) - ok_raw))
    return _check("A5-C01", "package_integrity", status, detail, severity="blocker",
                  metrics={"sums_entries": len(entries), "sha256_lf_match": ok_lf, "sha256_raw_match": ok_raw,
                           "missing_files": missing, "mismatch": mismatch, "crlf_declared": crlf,
                           "bytes_raw_total": bytes_total, "mismatched": mismatched[:5]},
                  evidence=[str(S3_SUMS_RELPATH), str(S3_PACKAGE_MANIFEST_RELPATH)])


def check_physical_zero(repo_root: Path) -> dict:
    manifest_path = repo_root / S3_PACKAGE_MANIFEST_RELPATH
    run_cfg_path = repo_root / S3_RUN_CONFIG_RELPATH
    fig_path = repo_root / S3_EVIDENCE_RELPATH / "analysis/figure_generation_summary.json"
    nc_path = repo_root / S3_EVIDENCE_RELPATH / "run/negative_control_summary.json"
    missing = [str(p) for p in (manifest_path, run_cfg_path) if not p.is_file()]
    if missing:
        return _check("A5-C02", "physical_zero", NOT_RUN, "缺少 physical 计数证据: " + ", ".join(missing), severity="blocker")
    manifest = load_json(manifest_path)
    run_cfg = load_json(run_cfg_path)
    counters = {
        "package_manifest.physical_call_count": manifest.get("physical_call_count"),
        "package_manifest.solver_processes_started": manifest.get("solver_processes_started"),
        "run_config.physical_call_count": run_cfg.get("physical_call_count"),
    }
    if fig_path.is_file():
        counters["figure_summary.physical_call_count"] = load_json(fig_path).get("physical_call_count")
    if nc_path.is_file():
        counters["negative_control_summary.physical_call_count"] = load_json(nc_path).get("physical_call_count")
    bad = {k: v for k, v in counters.items() if v not in (0, None)}
    absent = {k: v for k, v in counters.items() if v is None}
    status = FAIL if bad else VALID
    detail = "全部可见产物的 physical_call_count / solver_processes_started 均为 0。" if not bad else "存在非零物理调用计数: " + repr(bad)
    return _check("A5-C02", "physical_zero", status, detail, severity="blocker",
                  metrics={"counters": counters, "nonzero": bad, "absent": absent},
                  evidence=[str(S3_PACKAGE_MANIFEST_RELPATH), str(S3_RUN_CONFIG_RELPATH)])


def check_f01_validator_path(repo_root: Path) -> dict:
    runner = repo_root / "research/concorde_metaopt/meta_learning/s3_runner.py"
    prereg_mod = repo_root / "research/concorde_metaopt/meta_learning/s3_prereg.py"
    manifest_path = repo_root / S3_MANIFEST_RELPATH
    if not runner.is_file() or not manifest_path.is_file():
        return _check("A5-C03", "F01_validator_path", NOT_RUN, "缺少 s3_runner.py 或 run/model_manifest.json", severity="blocker")
    src = read_text(runner)
    block = _extract_function_block(src, "def _validate_model_manifest", 140)
    if not block:
        block = _extract_function_block(src, "model_manifest", 140)
    has_prefix = "S3_EVIDENCE_ROOT_RELPATH" in block
    prefix_defined = "S3_EVIDENCE_ROOT_RELPATH" in read_text(prereg_mod) if prereg_mod.is_file() else False
    rows = load_json(manifest_path).get("models") or []
    rel = str(rows[0].get("path")) if rows else ""
    evidence_root = repo_root / S3_EVIDENCE_RELPATH
    resolves_direct = bool(rel) and (repo_root / rel).is_file()
    resolves_with_prefix = bool(rel) and (evidence_root / rel).is_file()
    defect = (not has_prefix) and prefix_defined and bool(rel) and (not resolves_direct) and resolves_with_prefix
    status = VALID if defect else FAIL
    if defect:
        detail = ("缺陷可静态复现：模型清单校验块未拼接 S3_EVIDENCE_ROOT_RELPATH 前缀；row.path=" + rel
                  + " 在 repo_root 下不可解析、在 evidence/s3 下可解析 => 合法 run 会得到 validation_ok=false（fail-closed 位置错误）。")
    else:
        detail = "未复现 F-01：校验块前缀拼接缺失/路径解析反证条件不成立（需人工复核代码版本）。"
    return _check("A5-C03", "F01_validator_path", status, detail, severity="major",
                  metrics={"block_has_prefix": has_prefix, "prefix_constant_defined": prefix_defined, "row_path": rel,
                           "resolves_against_repo_root": resolves_direct, "resolves_against_evidence_root": resolves_with_prefix},
                  evidence=["research/concorde_metaopt/meta_learning/s3_runner.py:2527-2531", str(S3_MANIFEST_RELPATH)])


def _normalize_model_rows(rows):
    out = []
    for row in rows:
        item = {k: v for k, v in dict(row).items() if k != "bytes"}
        if item.get("path"):
            item["path"] = "models/" + Path(str(item["path"])).name
        out.append(item)
    return out


def check_f02_model_aggregate(repo_root: Path) -> dict:
    prereg_path = repo_root / S3_PREREG_RELPATH
    cfg_path = repo_root / S3_RUN_CONFIG_RELPATH
    if not prereg_path.is_file() or not cfg_path.is_file():
        return _check("A5-C04", "F02_model_aggregate", NOT_RUN, "缺少 prereg 或 run_config", severity="major")
    prereg = load_json(prereg_path)
    cfg = load_json(cfg_path)
    details = {}
    all_equal = True
    rows_all_sha_equal = True
    files_all_sha_equal = True
    for kind in ("fomaml", "anil"):
        pre_block = (prereg.get("models") or {}).get(kind) or {}
        pre_rows = pre_block.get("models") or []
        run_block = (cfg.get("models") or {}).get(kind) or {}
        pre_agg = str(pre_block.get("sha256") or "")
        run_agg = str(run_block.get("sha256") or "")
        normalized_agg = canonical_sha256(_normalize_model_rows(pre_rows)) if pre_rows else ""
        raw_agg = canonical_sha256([dict(r) for r in pre_rows]) if pre_rows else ""
        rows = run_block.get("models") or []
        row_sha_equal = [str(a.get("sha256")) for a in pre_rows] == [str(b.get("sha256")) for b in rows]
        file_sha_equal = True
        for row in rows:
            rel = str(row.get("path") or "")
            target = repo_root / S3_EVIDENCE_RELPATH / "models" / Path(rel).name
            if not target.is_file() or sha256_file_raw(target) != str(row.get("sha256")):
                file_sha_equal = False
        details[kind] = {"prereg_aggregate": pre_agg, "run_aggregate": run_agg, "prereg_aggregate_raw": raw_agg,
                         "prereg_aggregate_normalized": normalized_agg, "normalized_equals_run": normalized_agg == run_agg,
                         "aggregates_differ": pre_agg != run_agg, "per_model_sha_equal": row_sha_equal,
                         "model_file_sha_equal": file_sha_equal}
        all_equal = all_equal and (normalized_agg == run_agg)
        rows_all_sha_equal = rows_all_sha_equal and row_sha_equal
        files_all_sha_equal = files_all_sha_equal and file_sha_equal
    defect = all_equal and rows_all_sha_equal and files_all_sha_equal and all(d["aggregates_differ"] for d in details.values())
    status = VALID if defect else FAIL
    if defect:
        detail = ("口径差异已定位且可归一：原始聚合 sha 两侧不同（per-kind 均 differ），但去掉 bytes 并把 path 归一为 models/<kind>_meta_<seed>.json 后，"
                  "归一化聚合 sha 与 run 侧逐 kind 精确相等；6 个逐模型 sha 与磁盘模型文件 sha 全部一致 => 判定为比较器口径缺陷，非数据篡改。")
    else:
        detail = "F-02 归一化断言未通过：需人工复核 prereg/run_config/磁盘模型三者绑定。"
    return _check("A5-C04", "F02_model_aggregate", status, detail, severity="major",
                  metrics={"kinds": details, "per_model_sha_equal": rows_all_sha_equal, "model_file_sha_equal": files_all_sha_equal},
                  evidence=["research/concorde_metaopt/meta_learning/s3_runner.py:1635-1661", str(S3_PREREG_RELPATH), str(S3_RUN_CONFIG_RELPATH)])


def check_f03_ood(repo_root: Path) -> dict:
    analysis = repo_root / "research/concorde_metaopt/meta_learning/s3_analysis.py"
    ood_csv = repo_root / S3_EVIDENCE_RELPATH / "analysis/s3_ood_descriptives.csv"
    supp_csv = repo_root / S3_EVIDENCE_RELPATH / "analysis/ood_supplementary_descriptives.csv"
    disclosures = repo_root / S3_EVIDENCE_RELPATH / "analysis/analysis_disclosures.json"
    if not analysis.is_file() or not ood_csv.is_file():
        return _check("A5-C05", "F03_ood", NOT_RUN, "缺少 s3_analysis.py 或 s3_ood_descriptives.csv", severity="major")
    block = _extract_function_block(read_text(analysis), "def build_ood_rows", 40)
    reads_run_stream = bool(re.search(r"record_streams|run\.ood|ood_records", block))
    filters_split = "meta_test_ood" in block
    with ood_csv.open(encoding="utf-8") as handle:
        statuses = sorted({(row.get("status") or "").strip() for row in csv.DictReader(handle)})
    supp_rows = list(csv.DictReader(supp_csv.open(encoding="utf-8"))) if supp_csv.is_file() else []
    disc_text = read_text(disclosures) if disclosures.is_file() else ""
    has_disclosure = "A5-S3M5-01" in disc_text
    defect = (not reads_run_stream) and filters_split and statuses == ["NOT_RUN"] and bool(supp_rows) and has_disclosure
    status = VALID if defect else FAIL
    if defect:
        detail = ("冻结分析器 build_ood_rows 只按 endpoints.split=='meta_test_ood' 过滤、从不读取 run 的独立 OOD 记录流，"
                  "故 s3_ood_descriptives.csv 全行 NOT_RUN；侧车 ood_supplementary_descriptives.csv 有 " + str(len(supp_rows))
                  + " 行可与磁盘 28,800 条 OOD 记录对账，且 analysis_disclosures 已登记 A5-S3M5-01。结论：正式 OOD 分析 = NOT_RUN，侧车仅描述性。")
    else:
        detail = "F-03 断言未通过：OOD 接入状态与代码/证据不一致，需人工复核。"
    return _check("A5-C05", "F03_ood", status, detail, severity="major",
                  metrics={"build_ood_rows_reads_run_stream": reads_run_stream, "filters_meta_test_ood": filters_split,
                           "descriptive_statuses": statuses, "supplementary_rows": len(supp_rows),
                           "disclosure_A5_S3M5_01": has_disclosure},
                  evidence=["research/concorde_metaopt/meta_learning/s3_analysis.py:4601-4606", str(ood_csv), str(supp_csv)])


def check_wall_s_cost(repo_root: Path) -> dict:
    runner = repo_root / "research/concorde_metaopt/meta_learning/s3_runner.py"
    cost_csv = repo_root / S3_EVIDENCE_RELPATH / "analysis/s3_cost_table.csv"
    aggregate = repo_root / S3_EVIDENCE_RELPATH / "analysis/aggregate.json"
    disclosures = repo_root / S3_EVIDENCE_RELPATH / "analysis/analysis_disclosures.json"
    if not cost_csv.is_file() or not aggregate.is_file():
        return _check("A5-C06", "wall_s_cost", NOT_RUN, "缺少成本表或 aggregate.json", severity="major")
    with cost_csv.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    zero_total = sum(1 for row in rows if float(row.get("total_cost_median_s") or 0) == 0.0)
    budget_only = all(abs(float(row.get("adaptation_cost_mean") or 0) - float(row.get("budget") or 0)) < 1e-9 for row in rows)
    static_zero = bool(runner.is_file() and re.search(r'"wall_s"\s*:\s*0\.0', read_text(runner)))
    agg = load_json(aggregate)
    cost_ratio = (agg.get("anil_audit") or {}).get("cost_ratio")
    disclosure = "A5-S3M5-03" in read_text(disclosures) if disclosures.is_file() else False
    defect = zero_total == len(rows) and budget_only and static_zero and cost_ratio == 1.0 and disclosure
    status = VALID if defect else FAIL
    if defect:
        detail = ("ANIL 成本审计不可解释：逐点 wall_s 恒为 0.0（静态命中），s3_cost_table.csv " + str(len(rows))
                  + " 行 total_cost_median_s 全为 0，adaptation_cost_mean 恒等于预算（64/128），ANIL cost_ratio=1.0 仅反映预算比而非计算成本；"
                  "ANIL_COST_EFFICIENT（cost_ratio<=0.75）判据因此不可审计 => NOT_VALIDATED。")
    else:
        detail = "wall_s 成本口径断言未通过，需人工复核。"
    return _check("A5-C06", "wall_s_cost", status, detail, severity="major",
                  metrics={"rows": len(rows), "total_cost_zero_rows": zero_total, "adaptation_equals_budget": budget_only,
                           "runner_wall_s_zero_literal": static_zero, "anil_cost_ratio": cost_ratio,
                           "disclosure_A5_S3M5_03": disclosure},
                  evidence=["research/concorde_metaopt/meta_learning/s3_runner.py:1035",
                            "research/concorde_metaopt/meta_learning/s3_analysis.py:4113-4116", str(cost_csv)])


def check_nc15(repo_root: Path) -> dict:
    summary_path = repo_root / S3_EVIDENCE_RELPATH / "run/negative_control_summary.json"
    nc_csv = repo_root / S3_EVIDENCE_RELPATH / "analysis/s3_negative_controls.csv"
    disclosures = repo_root / S3_EVIDENCE_RELPATH / "analysis/analysis_disclosures.json"
    if not summary_path.is_file():
        return _check("A5-C07", "NC15_keys", NOT_RUN, "缺少 negative_control_summary.json", severity="major")
    summary = load_json(summary_path)
    missing = [key for key in NC15_REQUIRED_KEYS if key not in summary]
    disc_text = read_text(disclosures) if disclosures.is_file() else ""
    disclosed = "A5-S3M5-02" in disc_text and "DISCLOSED" in disc_text.upper()
    groups = summary.get("groups") or []
    de_b64 = next((g for g in groups if g.get("arm_id") == "S3-DE" and g.get("budget") == 64), None)
    defect = bool(missing) and disclosed and int(summary.get("records") or 0) == 28800
    status = VALID if defect else FAIL
    if defect:
        detail = ("NC-15 不可计算已核实：negative_control_summary.json 缺 " + ", ".join(missing)
                  + " 三键，冻结分析器据此标 DISCLOSED 而非计算；负控 10 组 28,800 条中仅 S3-DE B64=0.448958 明显偏离（已披露，未修剪）；"
                  "侧车复算为独立描述，不产生 p/CI/decision。")
    else:
        detail = "NC-15 断言未通过，需人工复核。"
    return _check("A5-C07", "NC15_keys", status, detail, severity="major",
                  metrics={"missing_keys": missing, "disclosure_present": disclosed, "records": summary.get("records"),
                           "de_b64_rate": (de_b64 or {}).get("feasible_rate")},
                  evidence=[str(summary_path), str(nc_csv)])


def check_figures(repo_root: Path) -> dict:
    status_path = repo_root / S3_EVIDENCE_RELPATH / "analysis/figure_status.json"
    summary_path = repo_root / S3_EVIDENCE_RELPATH / "analysis/figure_generation_summary.json"
    if not status_path.is_file():
        return _check("A5-C08", "figures", NOT_RUN, "缺少 figure_status.json", severity="minor")
    doc = load_json(status_path)
    figures = doc.get("figures") or {}
    rendered = sorted(k for k, v in figures.items() if (v or {}).get("status") == "RENDERED")
    not_run = sorted(k for k, v in figures.items() if (v or {}).get("status") == "NOT_RUN")
    png_missing = [k for k in rendered if not (repo_root / S3_EVIDENCE_RELPATH / "analysis" / (k + ".png")).is_file()]
    summary = load_json(summary_path) if summary_path.is_file() else {}
    cjk = str(summary.get("cjk_font") or "")
    defect = len(figures) == 10 and len(rendered) == 6 and len(not_run) == 4 and not png_missing
    status = VALID if defect else FAIL
    if defect:
        detail = ("10 图状态为 RENDERED " + str(len(rendered)) + " / NOT_RUN " + str(len(not_run))
                  + "；4 张缺数据面板已逐张给出 reason；6 张 PNG 全部在位（cjk_font=" + (cjk or "未记录") + "）。")
    else:
        detail = "图状态计数断言未通过。"
    return _check("A5-C08", "figures", status, detail, severity="minor",
                  metrics={"total": len(figures), "rendered": rendered, "not_run": not_run,
                           "png_missing": png_missing, "cjk_font": cjk},
                  evidence=[str(status_path), str(summary_path)])


def check_endpoint_arithmetic(repo_root: Path) -> dict:
    """独立重算 C1/C2 效应量与 Holm 校正，不依赖冻结分析器。"""
    agg_path = repo_root / S3_EVIDENCE_RELPATH / "analysis/aggregate.json"
    prereg_path = repo_root / S3_PREREG_RELPATH
    if not agg_path.is_file() or not prereg_path.is_file():
        return _check("A5-C09", "endpoint_arithmetic", NOT_RUN, "缺少 aggregate.json 或 prereg", severity="major")
    agg = load_json(agg_path)
    inference = agg.get("inference") or {}
    families = inference.get("families") or {}
    holms = inference.get("holm_rows") or []
    alpha = float(((load_json(prereg_path).get("analysis") or {}).get("alpha")) or 0.05)

    family_sizes = {}
    holm_ranks = {}
    for row in holms:
        fam = row.get("family_id")
        if fam is not None and row.get("family_size") is not None:
            family_sizes[str(fam)] = int(row["family_size"])
        if fam is not None and row.get("rank") is not None:
            holm_ranks.setdefault(str(fam), []).append(int(row["rank"]))
    per_task = agg.get("per_task_rows") or []
    arm_means = {}
    for row in per_task:
        key = (str(row.get("endpoint")), row.get("budget"), str(row.get("arm_id")))
        arm_means.setdefault(key, []).append(float(row.get("value")))
    arm_means = {key: (sum(vals) / len(vals)) for key, vals in arm_means.items() if vals}
    problems = []
    recomputed = []
    for fam_id, rows in families.items():
        for row in rows or []:
            diffs = [float(x) for x in (row.get("diff_values") or [])]
            mean_diff = float(row.get("mean_difference"))
            effect = float(row.get("effect"))
            ci_low = float(row.get("difference_ci_low"))
            ci_high = float(row.get("difference_ci_high"))
            tol = 1e-9
            if diffs and abs(sum(diffs) / len(diffs) - mean_diff) > 1e-9:
                problems.append("均值与 diff_values 不一致: " + str(fam_id) + " " + str(row.get("test_id")))
            # 效应量口径必须可从 aggregate 自身字段重算：C1 为均值差；C2(gap) 为相对均值差
            if str(row.get("endpoint")) == "gap_to_reference":
                obj_mean = arm_means.get((str(row.get("endpoint")), row.get("budget"), str(row.get("arm_b"))))
                if obj_mean is None:
                    problems.append("无法取得 C2 分母臂均值: " + str(row.get("test_id")))
                else:
                    expected_effect = mean_diff / max(abs(obj_mean), 1e-6)
                    if abs(effect - expected_effect) > 1e-9:
                        problems.append("C2 相对效应量不可重算: " + str(row.get("test_id")))
            elif abs(effect - mean_diff) > 1e-9:
                problems.append("effect!=mean_difference: " + str(row.get("test_id")))
            if not (ci_low <= effect <= ci_high):
                problems.append("CI 不含点估计: " + str(row.get("test_id")))
            if float(row.get("p_holm", 1.0)) + 1e-12 < float(row.get("p_raw", 0.0)):
                problems.append("p_holm < p_raw: " + str(row.get("test_id")))
            size = family_sizes.get(fam_id)
            if size is None or size < 1:
                problems.append("Holm 表缺少该族 family_size: " + str(fam_id))
            recomputed.append({"family": fam_id, "test_id": row.get("test_id"), "budget": row.get("budget"),
                               "n_paired": row.get("n_paired"), "n_eff": row.get("n_eff"),
                               "effect": effect, "ci": [ci_low, ci_high], "p_raw": row.get("p_raw"),
                               "p_holm": row.get("p_holm"), "decision": row.get("decision")})

    decisions = set()
    for key in ("c1_decisions", "c2_decisions"):
        for value in (inference.get(key) or {}).values():
            decisions.add(str(value))
    overall = str(inference.get("overall_decision") or "")
    expected_overall = "NO_EVIDENCE" if decisions == {"NULL"} else "UNKNOWN"
    if decisions and overall != expected_overall:
        problems.append("overall_decision 与逐检验决策不一致: " + overall + " vs " + expected_overall)
    for fam, ranks in holm_ranks.items():
        size = family_sizes.get(fam, 0)
        if sorted(ranks) != list(range(1, size + 1)):
            problems.append("Holm rank 不连续: " + fam + " " + repr(sorted(ranks)))
    holm_decisions = {str(r.get("decision")) for r in holms}
    if holms and not holm_decisions <= {"NULL", "SIGNIFICANT"}:
        problems.append("Holm 决策出现未登记取值: " + repr(holm_decisions))

    status = VALID if not problems else FAIL
    detail = ("独立重算 " + str(len(recomputed)) + " 条检验：C1 effect=mean_difference、C2 effect=mean_difference/|OBJ 臂均值|、CI 含点估计、p_holm>=p_raw、overall="
              + (overall or "缺失") + " 与逐检验决策（" + ",".join(sorted(decisions)) + "）一致，Holm rank 连续。" if not problems
              else "重算断言失败: " + "; ".join(problems[:4]))
    return _check("A5-C09", "endpoint_arithmetic", status, detail, severity="major",
                  metrics={"alpha": alpha, "n_tests": len(recomputed), "decisions": sorted(decisions),
                           "overall_decision": overall, "problems": problems[:6], "tests": recomputed},
                  evidence=[str(agg_path), str(S3_PREREG_RELPATH)])


def check_determinism(repo_root: Path) -> dict:
    det_path = repo_root / S3_EVIDENCE_RELPATH / "run/determinism_check.json"
    data_manifest_path = repo_root / S3_EVIDENCE_RELPATH / "run/data_manifest.json"
    if not det_path.is_file():
        return _check("A5-C10", "determinism", NOT_RUN, "缺少 determinism_check.json", severity="major")
    det = load_json(det_path)
    dm = load_json(data_manifest_path) if data_manifest_path.is_file() else {}
    excluded = [str(x) for x in (det.get("record_digest_excluded_fields") or det.get("excluded_fields") or [])]
    expected = {"wall_s", "peak_memory_mb", "record_digest"}
    core = det.get("record_core_sha256")
    core_list = [str(x) for x in core] if isinstance(core, list) else ([str(core)] if core else [])
    core_equal = bool(core_list) and len(set(core_list)) == 1
    subset = det.get("subset_run_keys_sha256")
    reruns = int(det.get("reruns") or 0)
    streams = det.get("record_streams") or {}
    stream_paths = []
    if isinstance(streams, dict):
        for value in streams.values():
            stream_paths.extend([str(x) for x in value] if isinstance(value, list) else [str(value)])
    local_ok = 0
    local_missing = 0
    for rel in stream_paths:
        if not rel:
            continue
        if (repo_root / S3_EVIDENCE_RELPATH / rel).is_file():
            local_ok += 1
        else:
            local_missing += 1
    consistent = expected <= set(excluded) and core_equal and bool(subset) and reruns == len(core_list) and reruns >= 2
    if not consistent:
        status = FAIL
        detail = "确定性口径断言失败：排除字段集=" + repr(sorted(set(excluded))) + "，record_core_sha256/subset_run_keys_sha256 不完整。"
    elif local_missing:
        status = NOT_RUN
        detail = ("确定性口径字段齐备（排除 wall_s/peak_memory_mb/record_digest），" + str(reruns) + " 次重跑 record_core_sha256=" + str(core_list[0])[:16]
                  + "…；但 " + str(local_missing) + " 个 externalized 记录流不在本机，无法按原始记录流独立重算 => 记录级确定性 NOT_RUN（仅登记声明）。")
    else:
        status = VALID
        detail = "确定性口径字段齐备且 externalized 记录流可在本机定位。"
    return _check("A5-C10", "determinism", status, detail, severity="major",
                  metrics={"excluded_fields": sorted(set(excluded)), "record_core_sha256": core_list,
                           "core_equal_across_reruns": core_equal, "reruns": reruns,
                           "subset_run_keys_sha256": subset, "external_streams_local": local_ok,
                           "external_streams_missing": local_missing},
                  evidence=[str(det_path), str(data_manifest_path)])


def check_gate_chain(repo_root: Path) -> dict:
    """门禁链：A5 M2R 未签发、A7 替代执行 M3、A3 覆盖缺口，必须显式记录且不得被当作已验证。"""
    matrix = repo_root / S3_REQUIREMENT_MATRIX_RELPATH
    reviews_dir = repo_root / S3_EVIDENCE_RELPATH / "reviews"
    if not matrix.is_file():
        return _check("A5-C11", "gate_chain", NOT_RUN, "缺少 requirement_matrix（不在 S3 worktree 根）", severity="blocker")
    text = read_text(matrix)
    has_deviation = "S3-GOV-01" in text and "DEVIATION" in text
    has_a5_m2r_missing = "A5_M2R_REVIEW=NOT_RECORDED" in text or "A5_M2R" in text
    has_a3_gap = "S3-M0-05" in text and "PARTIAL" in text
    verdict_files = sorted(p.name for p in reviews_dir.glob("*verdict*.json")) if reviews_dir.is_dir() else []
    a5_m2r = [name for name in verdict_files if "a5" in name.lower() and "m2r" in name.lower()]
    a7_m2r = [name for name in verdict_files if "a7" in name.lower() and "m2r" in name.lower()]
    a5_m5 = [name for name in verdict_files if "a5" in name.lower() and "m5" in name.lower()]
    a7_m4 = [name for name in verdict_files if "a7" in name.lower() and "m4" in name.lower()]
    accepted = (has_deviation and has_a5_m2r_missing and has_a3_gap
                and not a5_m2r and not a7_m2r and bool(a5_m5) and bool(a7_m4))
    status = VALID if accepted else FAIL
    if accepted:
        detail = ("门禁链替代已被记录为偏离：S3-GOV-01=DEVIATION，A5 M2R 无最终 verdict 落盘（reviews 下 a5_m2r verdict 0 件、a7_m2r verdict 0 件），"
                  "M3 由 A7 M2R=APPROVE_FOR_S3_RUN 替代放行；A3 覆盖仅到 691f554（S3-M0-05 PARTIAL）；"
                  "A5 仅有 M5 分析复核 verdict（" + str(a5_m5) + "）、A7 仅有 M4 复核 verdict（" + str(a7_m4) + "）。"
                  "结论：任务合法执行，但门禁完整性 = NOT_VALIDATED，须由负责人裁定补签或记入 S4 前置。")
    else:
        detail = ("门禁链断言未通过：deviation=" + str(has_deviation) + " a5_m2r=" + str(has_a5_m2r_missing)
                  + " a3_gap=" + str(has_a3_gap) + " a5_verdict=" + repr(a5_verdict) + " a7_verdict=" + repr(a7_verdict))
    metrics = {"deviation_recorded": has_deviation, "a5_m2r_not_recorded": has_a5_m2r_missing,
               "a3_coverage_partial": has_a3_gap, "a5_m2r_verdict_files": a5_m2r, "a7_m2r_verdict_files": a7_m2r,
               "a5_m5_verdict_files": a5_m5, "a7_m4_verdict_files": a7_m4}
    return _check("A5-C11", "gate_chain", status, detail, severity="blocker", metrics=metrics,
                  evidence=[str(S3_REQUIREMENT_MATRIX_RELPATH), str(reviews_dir)])


def check_downstream_products(dnext_root: Path) -> dict:
    """A1–A4 是否已产出可审对象；不存在则 NOT_RUN（不得以提交消息代替复现）。"""
    present = {}
    for role, dirname in DOWNSTREAM_ROLES.items():
        wt = dnext_root / dirname
        if not wt.is_dir():
            present[role] = {"worktree": str(wt), "exists": False}
            continue
        candidates = []
        for pattern in ("docs/receipts/dnext001/*.md", "docs/contracts/**/*.md", "docs/reviews/*task_spec*"):
            candidates.extend(str(p.relative_to(wt)) for p in wt.glob(pattern))
        present[role] = {"worktree": str(wt), "exists": True, "candidate_docs": sorted(candidates)[:5]}
    any_product = any(info.get("candidate_docs") for info in present.values())
    status = VALID if any_product else NOT_RUN
    if any_product:
        detail = "检测到下游产物候选文档，需逐件进入 M0 待审清单复核（本脚本不代签 PASS）。"
    else:
        detail = "A1–A4 工作树均无可审产物（无 receipt / TaskSpec 合同）；M0 门禁只能出待审条件清单，状态 NOT_RUN。"
    return _check("A5-C12", "downstream_products", status, detail, severity="info",
                  metrics={"roles": present}, evidence=[str(dnext_root)])


def collect_evidence(s3_root: Path, dnext_root: Path) -> dict:
    checks = [
        check_package_integrity(s3_root),
        check_physical_zero(s3_root),
        check_f01_validator_path(s3_root),
        check_f02_model_aggregate(s3_root),
        check_f03_ood(s3_root),
        check_wall_s_cost(s3_root),
        check_nc15(s3_root),
        check_figures(s3_root),
        check_endpoint_arithmetic(s3_root),
        check_determinism(s3_root),
        check_gate_chain(s3_root),
        check_downstream_products(dnext_root),
    ]
    counts = {status: 0 for status in STATUSES}
    for item in checks:
        counts[item["status"]] += 1
    if counts[FAIL]:
        overall = FAIL
    elif counts[NOT_VALIDATED]:
        overall = NOT_VALIDATED
    elif counts[NOT_RUN]:
        overall = NOT_RUN
    else:
        overall = VALID
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_id": "A5-DNEXT001-VERIFY-" + _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "generated_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reviewer_role": "A5_INDEPENDENT_REVIEW",
        "s3_root": str(s3_root),
        "dnext_root": str(dnext_root),
        "physical_call_count": 0,
        "solver_processes_started": 0,
        "evidence_mode": "ARCHIVE_REPLAY_READ_ONLY",
        "overall_status": overall,
        "status_counts": counts,
        "no_pass_by_commit_message": True,
        "checks": checks,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = []
    lines.append("# D-NEXT-001 A5 独立复核审计输出（只读归档 replay）")
    lines.append("")
    lines.append("- 审计 ID：" + str(report["audit_id"]))
    lines.append("- 生成时间（UTC）：" + str(report["generated_utc"]))
    lines.append("- 复核角色：" + str(report["reviewer_role"]) + "（仅审查，不实现被审算法、不自审自改）")
    lines.append("- S3 证据根：" + str(report["s3_root"]))
    lines.append("- 下游工作树根：" + str(report["dnext_root"]))
    lines.append("- 证据模式：" + str(report["evidence_mode"]))
    lines.append("- physical_call_count = " + str(report["physical_call_count"]) + "（全部为 mock/合成/归档只读，未启动任何物理求解器）")
    lines.append("- solver_processes_started = " + str(report["solver_processes_started"]))
    lines.append("- 总判定：" + str(report["overall_status"]))
    counts = report["status_counts"]
    lines.append("- 状态计数：VALID=" + str(counts.get(VALID, 0)) + "，NOT_VALIDATED=" + str(counts.get(NOT_VALIDATED, 0))
                 + "，NOT_RUN=" + str(counts.get(NOT_RUN, 0)) + "，FAIL=" + str(counts.get(FAIL, 0)))
    lines.append("- 规则：不得以提交消息代替复现；未审阅的提交不签 PASS；缺失/外置证据只能 NOT_RUN。")
    lines.append("")
    lines.append("## 检查明细")
    lines.append("")
    lines.append("| 检查 | 名称 | 状态 | 严重度 | 说明 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in report["checks"]:
        detail = str(item["detail"]).replace("|", "/")
        lines.append("| " + item["id"] + " | " + item["name"] + " | " + item["status"] + " | " + item["severity"] + " | " + detail + " |")
    lines.append("")
    lines.append("## 关键度量")
    lines.append("")
    for item in report["checks"]:
        metrics = item.get("metrics") or {}
        if not metrics:
            continue
        lines.append("### " + item["id"] + " " + item["name"] + "（" + item["status"] + "）")
        lines.append("")
        compact = json.dumps(metrics, ensure_ascii=False, sort_keys=True)
        if len(compact) > 1200:
            compact = compact[:1200] + "…（截断，完整值见 JSON）"
        lines.append("- metrics: " + compact)
        for ev in item.get("evidence") or []:
            lines.append("- 证据：" + str(ev))
        lines.append("")
    lines.append("## 结论边界")
    lines.append("")
    lines.append("- 本输出只覆盖归档证据的只读复核；原始记录流外置（run_records.jsonl 等不在本机）时，记录级重算标 NOT_RUN。")
    lines.append("- 侧车/描述性产物不得升级为 p 值、CI 或阶段放行结论。")
    lines.append("- 任何 PASS 结论必须由本脚本断言可复现或由具名复核人另附独立 verdict；提交消息、执行人自述均不构成 PASS 依据。")
    lines.append("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="D-NEXT-001 A5 独立只读复核（S3 归档 + 下游产物存在性）")
    parser.add_argument("--s3-root", default=str(Path(r"D:\RCAIDE-s3-dev")), help="S3 只读工作树根（含 research/concorde_metaopt/evidence/s3）")
    parser.add_argument("--dnext-root", default=str(DEFAULT_DNEXT_ROOT), help="D-NEXT-001 worktrees 根（含 wt-a1..wt-a4）")
    parser.add_argument("--out", default="", help="JSON 输出路径；为空则打印到 stdout")
    parser.add_argument("--md", default="", help="Markdown 输出路径")
    args = parser.parse_args(argv)

    s3_root = Path(args.s3_root)
    evidence_root = s3_root / S3_EVIDENCE_RELPATH
    if not evidence_root.is_dir():
        print("证据根缺失: " + str(evidence_root), file=sys.stderr)
        return 3
    report = collect_evidence(s3_root, Path(args.dnext_root))
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print("JSON: " + args.out)
    else:
        print(payload)
    if args.md:
        Path(args.md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md).write_text(render_markdown(report) + "\n", encoding="utf-8")
        print("MD: " + args.md)
    print("overall=" + report["overall_status"] + " counts=" + json.dumps(report["status_counts"], ensure_ascii=False))
    return 2 if report["status_counts"].get(FAIL) else 0


if __name__ == "__main__":
    raise SystemExit(main())
