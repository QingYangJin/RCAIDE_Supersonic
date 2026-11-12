"""P2a v2 (C+B2) preregistration package and zero-physical runner glue.

Package policy (Lead m01809/m01866/m01889, A5 Q2=A, Lead m02229):
* C+B2: per-design two frozen families from the A1 runtime FreezeAPI; the
  solver consumes frozen .vspgeom bytes; primary endpoint is the equal-weight
  mean of the two family CDi values.
* sequential runtime freeze: approval binds policy + code + three initial LHS
  seeds, never the future designs; each runtime design is frozen arm-blind and
  appended to a hash-chained log before any solver start.
* preflight (3 replay cases) runs first and gates the main batch.
* the A1 TwoFamilyEvaluator (canonical evaluator event ledger) is the only writer of
  solver_attempts.jsonl; A1 solver_ledger.SolverLedger is not invoked; A2 only
  reads/pairs rows by case_id (no writes, truncation, or rebuild).
  reads count_starts for its own budget guard.
* this module never launches a solver and always reports physical_call_count=0.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from .p2a_v2_common import (
    APPEND_ONLY_LOG_PATH, APPROVAL_SCHEMA, ARMS, A1_PAIR_MANIFEST_PATH,
    A1_PREFLIGHT_BUNDLE_PATH, A1_PROBE_V3_OVERALL, A1_PROBE_V3_REL,
    A1_PROBE_V3_SHA256, A1_READINESS_STATUS, BATCH_ID, DESIGN_EVALS_PER_ARM,
    DISCLOSURE_FAMILY_PAIRS, DRY_RUN_FILENAME, FAMILY_SLOTS_LABELS,
    FREEZE_API_CHAIN_SCHEMA, FREEZE_API_DISCOVERY_K, FREEZE_API_SCHEMA, FORCE_ATTEMPTS_PER_FAMILY, FROZEN_PAIR_MANIFEST_SHA256,
    IDENTITY_SCHEMA, INITIAL_DESIGN_HASHES, INITIAL_DESIGN_INDICES,
    INITIAL_DESIGNS_NOTE, INITIAL_MANIFEST_SCHEMA, LEDGER_SCHEMA,
    L_REF_N, LIFT_TOLERANCE_REL, MAIN_PLANNED_STARTS, MAX_GEOMETRY_BUILDS,
    MAX_GEOMETRY_BUILDS_PER_DESIGN, MAX_INTERNAL_CASES, MAX_REFINE_STARTS,
    MAX_STARTS, PHYSICAL_CALL_COUNT, PLAN_SCHEMA, PLANNED_INTERNAL_CASES,
    PLANNED_STARTS, PREFLIGHT_ACCEPT_NUMERIC_RTOL, PREFLIGHT_BUNDLE_SCHEMA,
    PREFLIGHT_CASES, PREFLIGHT_CASES_DEFAULT, PREFLIGHT_PLANNED_INTERNAL_CASES,
    PREFLIGHT_PLANNED_STARTS, Q_PA, RESERVE_GROUPS, RESERVE_STARTS, RUN_ID,
    RUNNER_VERSION, SEED, STAGE, TIMEOUT_SECONDS, WINDOW_END_UTC,
    R1_APPROVAL_BYTES, R1_APPROVAL_SHA256, R1_CHARGED_INTERNAL_CASES,
    PRIOR_CHARGED_INTERNAL_CASES, PRIOR_CHARGED_STARTS,
    R1_CHARGED_STARTS, R1_MAIN_STARTS, R1_RUN_ID,
    R2_AMENDMENT_ACTION, R2_AMENDMENT_REASON, R2_AMENDMENT_SEQ,
    R2_APPROVAL_BYTES, R2_APPROVAL_SHA256, R2_CHARGED_INTERNAL_CASES,
    R2_CHARGED_STARTS, R2_MAIN_STARTS, R2_RUN_ID,
    R3_AMENDMENT_ACTION, R3_AMENDMENT_REASON, R3_AMENDMENT_SEQ,
    R4_AMENDMENT_ACTION, R4_AMENDMENT_AT_UTC, R4_AMENDMENT_REASON,
    R4_AMENDMENT_SEQ, R4_APPROVAL_BYTES, R4_APPROVAL_SHA256,
    R4_CHARGED_INTERNAL_CASES, R4_CHARGED_STARTS, R4_DRY_RUN_BYTES,
    R4_DRY_RUN_FILENAME, R4_DRY_RUN_SHA256, R4_MAIN_STARTS, R4_RUN_ID,
    R5_AMENDMENT_ACTION, R5_AMENDMENT_REASON, R5_AMENDMENT_SEQ,
    R5_CUMULATIVE_INTERNAL_CASES, R5_CUMULATIVE_STARTS,
    R5_EXCLUDES_R1_R2_R3_R4_FROM_ENDPOINTS, R5_AMENDMENT_AT_UTC,
    R5_APPROVAL_BYTES, R5_APPROVAL_SHA256, R5_CHARGED_INTERNAL_CASES,
    R5_CHARGED_STARTS, R5_MAIN_STARTS, R5_RUN_ID,
    R6_AMENDMENT_ACTION, R6_AMENDMENT_REASON, R6_AMENDMENT_SEQ,
    R6_CUMULATIVE_INTERNAL_CASES, R6_CUMULATIVE_STARTS,
    R6_EXCLUDES_R1_R2_R3_R4_R5_FROM_ENDPOINTS,
    A1_DESIGN_SPACE_CONFIG_BYTES, A1_DESIGN_SPACE_CONFIG_REL,
    A1_DESIGN_SPACE_CONFIG_SHA256, A1_DESIGN_SPACE_PY_BYTES,
    A1_DESIGN_SPACE_PY_REL, A1_DESIGN_SPACE_PY_SHA256,
    DESIGN_SPACE_VARIABLE_IDS,
    WINDOW_START_UTC, WINDOW_TOKEN, ZERO_PHYSICAL_WALL_CAP_SECONDS,
    VSPAERO_EXE_BYTES, VSPAERO_EXE_PATH, VSPAERO_EXE_SHA256,
    R2_AMENDMENT_AT_UTC, R3_AMENDMENT_AT_UTC, R3_APPROVAL_BYTES,
    R3_APPROVAL_SHA256, R3_CHARGED_INTERNAL_CASES, R3_CHARGED_STARTS,
    R3_MAIN_STARTS, R3_RUN_ID,
    R6_APPROVAL_BYTES, R6_APPROVAL_SHA256, R6_CHARGED_INTERNAL_CASES,
    R6_CHARGED_STARTS, R6_MAIN_STARTS, R6_RUN_ID,
    R7_AMENDMENT_ACTION, R7_AMENDMENT_REASON, R7_AMENDMENT_SEQ,
    R7_CUMULATIVE_INTERNAL_CASES, R7_CUMULATIVE_STARTS,
    R7_EXCLUDES_R1_R2_R3_R4_R5_R6_FROM_ENDPOINTS, R10_MAIN_PLANNED_STARTS,
    R10_PLANNED_INTERNAL_CASES, R10_PLANNED_STARTS,
    DIAGNOSTIC_CASES, DIAGNOSTIC_PLANNED_INTERNAL_CASES, DIAGNOSTIC_PLANNED_STARTS,
    INVALID_EVALUATION_STATUS,
    R7_APPROVAL_BYTES, R7_APPROVAL_SHA256, R7_CHARGED_INTERNAL_CASES, R7_CHARGED_STARTS,
    R7_MAIN_STARTS, R7_RUN_ID, R7_AMENDMENT_AT_UTC,
    R7_CUMULATIVE_INTERNAL_CASES_RECORDED, R7_CUMULATIVE_STARTS_RECORDED,
    DIAGNOSTIC_STARTS_PER_CASE, DIAGNOSTIC_INTERNAL_CASES_PER_CASE,
    R10_MAIN_PLANNED_STARTS, R10_PLANNED_INTERNAL_CASES, R10_PLANNED_STARTS,
    R10_CUMULATIVE_INTERNAL_CASES, R10_CUMULATIVE_STARTS,
    R10_EXCLUDES_R1_R2_R3_R4_R5_R6_R7_R8_R9_FROM_ENDPOINTS,
    R10_AMENDMENT_ACTION, R10_AMENDMENT_REASON, R10_AMENDMENT_SEQ,
    STATIC_INDEX_COUNT_EXPECTED, PREFROZEN_SOURCE_KIND, ACCOUNTING_INCONSISTENT,
    R8_APPROVAL_BYTES, R8_APPROVAL_SHA256, R8_CHARGED_INTERNAL_CASES,
    R8_CHARGED_STARTS, R8_LAUNCHER_GATE_BYTES, R8_LAUNCHER_GATE_SHA256,
    R8_PRESTART_BYTES, R8_PRESTART_SHA256, R8_RUN_ID,
    R8_STOP_REPORT_BYTES, R8_STOP_REPORT_SHA256,
    R10_MAIN_PLANNED_STARTS, R10_PLANNED_INTERNAL_CASES, R10_PLANNED_STARTS,
    R10_CUMULATIVE_INTERNAL_CASES, R10_CUMULATIVE_STARTS,
    R10_EXCLUDES_R1_R2_R3_R4_R5_R6_R7_R8_R9_FROM_ENDPOINTS,
    R10_AMENDMENT_ACTION, R10_AMENDMENT_REASON, R10_AMENDMENT_SEQ,
    R9_CHARGED_STARTS, R9_CHARGED_INTERNAL_CASES, R9_MAIN_STARTS, R9_RUN_ID,
    R9_APPROVAL_SHA256, R9_APPROVAL_BYTES, R9_AMENDMENT_AT_UTC,
    R9_STOP_REPORT_SHA256, R9_STOP_REPORT_BYTES,
    R9_PREFLIGHT_RESULT_SHA256, R9_PREFLIGHT_RESULT_BYTES,
    R9_SOLVER_ATTEMPTS_SHA256, R9_SOLVER_ATTEMPTS_BYTES,
    R9_PRESTART_SHA256, R9_PRESTART_BYTES,
    R9_LAUNCHER_GATE_SHA256, R9_LAUNCHER_GATE_BYTES,
    R9_CUMULATIVE_STARTS_RECORDED, R9_CUMULATIVE_INTERNAL_CASES_RECORDED,
    R9_DIAGNOSTICS_IN_MATRIX, R10_DIAGNOSTICS_IN_MATRIX,
    R10_DIAGNOSTIC_EVIDENCE_R9,
    INTERNAL_CASES_PER_START, INTERNAL_CASES_PER_START_SOURCE,
    ACCOUNTING_CONSERVATION_TOLERANCE,
)
from .p2a_v2_runtime import (
    P2AV2Batch, P2AV2Runner, PreflightVerifier, canonical_json,
    design_hash as compute_design_hash, sha256_bytes, sha256_file, sha256_text,
    utc_now,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
RUN_DIR = REPO_ROOT / "research/concorde_metaopt/dreal001/runs/DREAL001-P2A2R10-20261111-01"
PKG_DIR = RUN_DIR
DEFAULT_A1_ROOT = Path(r"D:\RCAIDE\dnext001\wt-real-a1-geometry-solver")
APPROVAL_FILENAME = "approval.DRAFT.json"
IDENTITY_FILENAME = "identity_binding.json"
INITIAL_MANIFEST_FILENAME = "initial_designs_manifest.json"
PREREG_FILENAME = "P2A_V2_PREREGISTRATION.md"
EXECUTOR_DRY_RUN_FILENAME = "executor_dry_run.json"
PLAN_FILENAME = "plan.json"
FREEZE_RULE = "K10_DISCOVERY_UNION_2_TARGET_40_PER_FAMILY"
FREEZE_API_REL = "research/concorde_metaopt/dreal001/geometry/freeze_api.py"
EVALUATOR_REL = "research/concorde_metaopt/dreal001/geometry/evaluator_v12.py"
BUILDER_REL_FILES = (
    "research/concorde_metaopt/dreal001/geometry/openvsp_model.py",
    "research/concorde_metaopt/dreal001/geometry/mesh_identity.py",
    "research/concorde_metaopt/dreal001/geometry/design_identity.py",
    "research/concorde_metaopt/dreal001/geometry/task_spec.py",
)
A2_CODE_FILES = (
    "research/concorde_metaopt/dreal001/optimizers/p2a_v2_common.py",
    "research/concorde_metaopt/dreal001/optimizers/p2a_v2_runtime.py",
    "research/concorde_metaopt/dreal001/optimizers/p2a_v2.py",
    "research/concorde_metaopt/dreal001/optimizers/p2a_v2_executor.py",
)


def _sha256_json(payload: Any) -> str:
    return sha256_text(canonical_json(payload))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_text(text)


def _file_binding(path: Path, role: str, status: str = "BOUND") -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"path": str(path), "role": role, "status": "MISSING", "sha256": None, "bytes": None}
    data = path.read_bytes()
    return {"path": str(path), "role": role, "status": status,
            "sha256": sha256_bytes(data), "bytes": len(data)}


def a2_code_binding() -> dict[str, Any]:
    files = []
    for rel in A2_CODE_FILES:
        files.append(_file_binding(REPO_ROOT / rel, "A2_EXECUTOR"))
    payload = [{f["path"]: f["sha256"] for f in files}]
    executor_row = next(f for f in files
                        if Path(str(f["path"])).name == "p2a_v2_executor.py")
    return {
        "schema": "dreal001.p2a_v2.code_binding.v1",
        "files": files,
        "a2_executor_sha256": executor_row["sha256"],
        "a2_executor_file": "research/concorde_metaopt/dreal001/optimizers/p2a_v2_executor.py",
        "a2_executor_sha256_definition": "SHA256 of the p2a_v2_executor.py file bytes (the runner blob), not a JSON aggregate",
        "a2_code_bundle_sha256": _sha256_json(payload),
        "runner_version": RUNNER_VERSION,
        "physical_call_count": 0,
    }


def _import_a1(a1_root: Path, module_name: str) -> Any:
    root = Path(a1_root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    # The A2 package may already have imported research.concorde_metaopt.dreal001
    # from its own tree; extend that package path with the A1 tree so that the
    # geometry subpackage resolves to the frozen A1 evaluator/freeze code.
    dreal_pkg = importlib.import_module("research.concorde_metaopt.dreal001")
    a1_dreal = root / "research/concorde_metaopt/dreal001"
    a1_text = str(a1_dreal)
    if a1_text not in dreal_pkg.__path__:
        dreal_pkg.__path__.append(a1_text)
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        name = "research.concorde_metaopt.dreal001.geometry." + module_name
        return importlib.import_module(name)
    finally:
        sys.dont_write_bytecode = old


def a1_binding(a1_root: Optional[Path] = None) -> dict[str, Any]:
    root = Path(a1_root) if a1_root is not None else DEFAULT_A1_ROOT
    files = [
        _file_binding(root / FREEZE_API_REL, "A1_FREEZE_API"),
        _file_binding(root / EVALUATOR_REL, "A1_EVALUATOR_V1_2"),
    ]
    for rel in BUILDER_REL_FILES:
        files.append(_file_binding(root / rel, "A1_GEOMETRY_BUILDER"))
    task_spec_cfg = root / "configs/dreal001_task_fixed_cruise_REAL.json"
    files.append(_file_binding(task_spec_cfg, "A1_TASK_SPEC"))
    by_role = {f["role"]: f for f in files}
    builder_payload = [{f["path"]: f["sha256"] for f in files if f["role"] == "A1_GEOMETRY_BUILDER"}]
    api = "UNAVAILABLE"
    freeze_rule = "UNAVAILABLE"
    try:
        freeze_api = _import_a1(root, "freeze_api")
        if callable(getattr(freeze_api, "discover_and_freeze_pair", None)):
            api = "AVAILABLE"
            freeze_rule = str(getattr(freeze_api, "FREEZE_RULE", FREEZE_RULE))
    except Exception as exc:  # noqa: BLE001
        api = "IMPORT_ERROR: %s" % (type(exc).__name__,)
    evaluator_status = "UNKNOWN"
    if by_role["A1_EVALUATOR_V1_2"].get("status") == "BOUND":
        evaluator_status = A1_READINESS_STATUS
    probe_path = root / A1_PROBE_V3_REL
    probe_status = "BOUND" if probe_path.is_file() else "MISSING"
    probe_sha = sha256_file(probe_path) if probe_path.is_file() else None
    return {
        "schema": "dreal001.p2a_v2.a1_binding.v1",
        "a1_root": str(root),
        "a1_head": _git_head(root),
        # Executable geometry code commit (task-49); later A1 commits are bundle/docs only.
        "a1_executable_commit": "6753eb39b710035187db13ceb3328301c645c1ba",
        "files": files,
        "freeze_api_status": api,
        "freeze_api_schema": FREEZE_API_SCHEMA,
        "freeze_api_sha256": by_role["A1_FREEZE_API"].get("sha256"),
        "builder_code_path": str((root / "research/concorde_metaopt/dreal001/geometry/openvsp_model.py").resolve()),
        "builder_code_file_sha256": sha256_file((root / "research/concorde_metaopt/dreal001/geometry/openvsp_model.py")),
        "builder_code_sha256": sha256_file((root / "research/concorde_metaopt/dreal001/geometry/openvsp_model.py")),
        "builder_code_bundle_sha256": _sha256_json(builder_payload),
        "evaluator_code_sha256": by_role["A1_EVALUATOR_V1_2"].get("sha256"),
        "evaluator_status": evaluator_status,
        "evaluator_real_path_status": A1_READINESS_STATUS,
        "a1_probe_v3_path": str(probe_path.resolve()),
        "a1_probe_v3_status": probe_status,
        "a1_probe_v3_sha256": probe_sha,
        "a1_probe_v3_overall": A1_PROBE_V3_OVERALL,
        "a1_probe_v3_expected_sha256": A1_PROBE_V3_SHA256,
        "task_spec_sha256": by_role["A1_TASK_SPEC"].get("sha256"),
        "freeze_rule_in_code": freeze_rule,
        "physical_call_count": 0,
    }


def _git_head(root: Path) -> Optional[str]:
    try:
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=15, check=False)
        if proc.returncode == 0:
            sha = proc.stdout.strip()
            return sha if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha) else None
    except Exception:  # noqa: BLE001
        return None
    return None


def build_initial_designs_manifest(source_path: Optional[Path] = None) -> dict[str, Any]:
    path = Path(source_path) if source_path is not None else Path(A1_PAIR_MANIFEST_PATH)
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if digest != FROZEN_PAIR_MANIFEST_SHA256:
        raise ValueError("P2AFAM manifest SHA mismatch: %s != %s" % (digest, FROZEN_PAIR_MANIFEST_SHA256))
    manifest = json.loads(data)
    records = manifest.get("records") or []
    subset = [records[i] for i in INITIAL_DESIGN_INDICES]
    if [str(r.get("design_hash")) for r in subset] != list(INITIAL_DESIGN_HASHES):
        raise ValueError("initial design hashes do not match the frozen indices")
    designs = []
    for idx, rec in zip(INITIAL_DESIGN_INDICES, subset):
        fams = rec.get("families") or {}
        family_rows = {}
        for label, fam in fams.items():
            frozen = (fam or {}).get("frozen") or {}
            family_rows[str(label)] = {
                "nodes": int(str(label).split("x")[0]),
                "elements": int(str(label).split("x")[1]),
                "frozen_vspgeom_sha256": frozen.get("frozen_vspgeom_sha256"),
                "frozen_vspgeom_bytes": frozen.get("frozen_vspgeom_bytes"),
                "frozen_vkey_sha256": frozen.get("frozen_vkey_sha256"),
                "frozen_vsp3_sha256": frozen.get("frozen_vsp3_sha256"),
                "canonical_mesh_sha256": frozen.get("canonical_mesh_sha256"),
                "frozen_vspgeom_path": frozen.get("frozen_vspgeom_path"),
            }
        if len(family_rows) != 2:
            raise ValueError("initial design %s does not have exactly two families" % idx)
        designs.append({
            "design_index": int(idx), "design_hash": str(rec.get("design_hash")),
            "group": str(rec.get("group", "")), "source_case_id": rec.get("source_case_id"),
            "x12": [float(v) for v in rec.get("x12") or []],
            "families": family_rows,
            "status": "PREFROZEN_ZERO_PHYSICAL_FROM_P2AFAM_MANIFEST",
            "physical_call_count": 0,
        })
    doc = {
        "schema": INITIAL_MANIFEST_SCHEMA,
        "created_utc": utc_now(),
        "source_file": str(path),
        "source_file_sha256": digest,
        "source_file_bytes": len(data),
        "source_manifest_schema": manifest.get("schema"),
        "source_manifest_designs": len(records),
        "subset_rule": "group=LHS, design_index ascending; first three: 15,16,17",
        "initial_design_indices": list(INITIAL_DESIGN_INDICES),
        "initial_design_hashes": list(INITIAL_DESIGN_HASHES),
        "initial_designs_note": INITIAL_DESIGNS_NOTE,
        "records": subset,
        "records_subset_sha256": _sha256_json(subset),
        "designs": designs,
        "zero_physical": True,
        "solver_started": False,
        "physical_call_count": 0,
        "append_rule": "these three designs are pre-frozen from the P2AFAM manifest and are never rebuilt; the runtime FreezeAPI is not called for them",
    }
    doc["manifest_sha256"] = _sha256_json({k: v for k, v in doc.items() if k != "manifest_sha256"})
    return doc


def preregistration_text(plan_sha: str = "", a1: Optional[Mapping[str, Any]] = None,
                         a2: Optional[Mapping[str, Any]] = None) -> str:
    a1 = dict(a1 or {})
    a2 = dict(a2 or {})
    lines = [
        "# D-NEXT-001 P2a v2 预注册：C+B2 每设计双冻结族 + 六臂公平优化",
        "",
        "状态：DRAFT_PENDING_LEAD_APPROVAL / A5 REVIEW。physical_solver_starts=0，"
        "physical_call_count=0；本文件不是批准书，也不得作为执行授权。",
        "",
        "## 1. 目的与范围",
        "",
        "在 A1 几何族非确定性已由 P1/P2CAL 证据确认的前提下，P2a v2 用每设计双族冻结"
        "（C）加 B2 字节冻结，给六个优化臂提供同一 f(x)，只比较优化器行为，"
        "不比较单族数值、不产生气动/燃油证据。",
        "",
        "## 2. 不可比性与披露",
        "",
        "- P2a v2 的结果与 P1C/P1R/P2CAL 的单族数值不可比；跨族数值不可比。",
        "- P1R=INCOMPLETE_S1_STOPPED_WITH_PROTOCOL_DEVIATION；P1C=SOLVER_INTERNAL_PASS_CONTINUATION；"
        "P1 整体未签、P2/P2a 未授权；P2a 原六臂 384-start 判定 NOT_RUN（网格族非确定性）。",
        "- P2CAL v1.2 已完成 12 starts / CAL_COMPLETE / ROOT_CAUSE_REQUIRED（W05 mean 5.826%、"
        "W10 5.832%），仅诊断；12D_ACTIVE=NOT_VALIDATED。",
        "- 本阶段单 seed（42）仅描述性，无显著性、无 winner，不签 optimizer PASS。",
        "- fuel_burn_kg=null；physical_validation_status=NOT_VALIDATED。",
        "",
        "## 3. 几何策略：每设计双族冻结（C+B2）",
        "",
        "- 臂盲 discovery：全新进程 direct build，K=10 观测；族并集恰为 2 时成为族对；"
        "只有 1 族时继续到 40 次；并集 >=3 时整设计 DESIGN_VOID。",
        "- 对族对的两族分别强制命中（每族 <=40 次全新进程 build），命中后冻结 "
        ".vspgeom/.vkey/.vsp3 字节并记录 SHA256。",
        "- f1=较小 (nodes, elements)，f2=较大；角色映射全局一致，任何臂不得改变。",
        "- 六臂只读同一对冻结字节；solver 前 PRE、后 POST 校验字节 SHA；不一致即 0 start 或"
        "该 start 不可用，不回退重建。",
        "- 同一设计只冻结一次，append-only hash-chained 记录先于任何 solver start；"
        "任一族不可达则整设计所有臂统一 VOID，不得单臂丢弃或单族进入 primary。",
        "- 冻结总量上限 8,000 次零物理 build；每设计硬上限 100 次（20 discovery + 2x40）；"
        "零物理墙钟上限 3,600 s；任一上限触发即停批 NOT_VALIDATED。",
        "",
        "## 4. 初始设计（零物理预冻结）",
        "",
        "- 从既有 P2AFAM manifest（SHA256=%s）取 group=LHS、design_index 升序前 3 个：" % FROZEN_PAIR_MANIFEST_SHA256,
        "- design_index 15/16/17，design_hash d51866f7d3c49303 / eb00b7ad545243e6 / dc96d2438a6dddc3。",
        "- 三条记录原字节、x12、每族 frozen vspgeom/vkey/canonical SHA 精确列入 "
        "initial_designs_manifest.json，六臂完全相同；它们不在 A 臂 15 个 P1C/P1R 历史标签内，无热启动泄漏。",
        "",
        "## 5. 预检（preflight，必须先于主批）",
        "",
        "- A1 R1 replay bundle 由 A1 在 R1 重建（SHA256 见 identity_binding/approval.replay_bundles），2 个 case 排最前：",
        "  PRE-01 design 0 / 543x472；PRE-02 W01-plus / 483x418；原 PRE-03（同 PRE-01 但用历史 P1R vkey 对照）因与 B2 冻结字节合同冲突已退役。",
        "- approval.replay_bundles 绑定 bundle_manifest_sha256、semantics_doc_sha256，以及每 case 的 "
        "vspgeom/vkey/vspaero/csf/polar 五个 SHA；family_role 规则 f1=483x418、f2=543x472（与 A1 role_map 一致）。",
        "- 判定：actual polar SHA==expected -> PASS_BYTE；字节不等但 7 行数值 max rel<=1e-9 且网格一致"
        " -> PASS_NUMERIC（须 Lead/A5 书面接受）；否则 FAIL -> 停批，主批 NOT_RUN。",
        "- preflight 计入预算（2 starts / 14 internal），但不计入 E1-E6。",
        "- preflight 每个 case 必须新建独立的 A1 TwoFamilyEvaluator 实例（独立 _seen_cells，max_starts=1），调用后 finally close；"
        "PRE-01 与 PRE-02 仍绝不共享实例；per-case starts 同时取自 record.solver.physical_solver_starts 与 canonical ledger delta 交叉校验。",
        "",
        "## 6. 矩阵与预算",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        "| 臂 | BO / DE / PSO / ABO / ADE / APSO |",
        "| 每臂设计评价 | 32（每个设计 2 starts，f1+f2） |",
        "| 主批 planned starts | 384 |",
        "| preflight planned starts | 2 |",
        "| planned starts 合计 | 386 |",
        "| reserve groups | 32 组（64 starts），仅用于全局 VOID 替换 |",
        "| max_starts | 451 |",
        "| planned internal cases | 2,702（386x7） |",
        "| max_internal_cases | 3,157（451x7） |",
        "| refine starts | 0 |",
        "| per-case timeout | 60 s |",
        "| retry | 无；任何非 SOLVED 立即 S1 |",
        "| 并发 | 1 |",
        "",
        "## 7. 公平性规则",
        "",
        "1. 六臂同任务（同 f(x)、同 initial 3 designs、同 B=32 设计评价、同 seed=42）。",
        "2. 六臂共享同一冻结族对与同一 append-only 记录；不允许重算/挑族/覆盖。",
        "3. A 臂历史标签只允许来自 P1C/P1R 已提交 15 设计；本阶段 A 臂零新增历史标签。",
        "4. 冷启动基线只看本 run 的 VisibleLabelStore；历史支持不作为 BO/DE/PSO 的即时标签。",
        "5. VOID 设计全局作废并走同一 reserve，不按臂补差、不改变其他臂预算。",
        "",
        "## 8. 停机条件（S1-S9）",
        "",
        "- S1：preflight 非 PASS -> 主批 NOT_RUN。",
        "- S2：任何 solver 结果非 SOLVED_VALID -> 停批，不重试、不补跑。",
        "- S3：负 CDi 或非有限 CDi -> 停批。",
        "- S4：冻结 .vspgeom/.vkey/canonical SHA 前后不一致 -> 停批。",
        "- S5：starts/internal 超过 caps 或台账对账不一致 -> ACCOUNTING_MISMATCH 停批。",
        "- S6：VOID 设计超过 32 个 reserve 组 -> NOT_VALIDATED 停批。",
        "- S7：零物理 build >8,000 或每设计 >100 或墙钟 >3,600 s -> 停批。",
        "- S8：窗口关闭、approval 无效或 executor blob 变化 -> 0 start 停批。",
        "- S9：执行器异常 -> 写 end 行与 stop_report 后停批，不静默重试。",
        "",
        "## 9. 终点与统计",
        "",
        "- E1：每设计 primary=0.5*CDi(f1)+0.5*CDi(f2)（within-design 等权均值）。",
        "- E2：secondary/描述 only：D_i=q*Sref_family*CDi(family)；mean(D_i) 不排序、不进入跨臂比较；未定义 normalized companion。",
        "- E3：单族数值、跨族数值、跨 run 数值均不可比；不得拼成单族排行榜。",
        "- E4：32 design/臂、单 seed，仅描述性；不计算 p 值、不宣布 winner。",
        "- E5：VOID 设计与缺失 pair 不计入 E1，但必须逐条披露。",
        "- E6：fuel_burn_kg=null，不产生燃油/航程证据。",
        "",
        "## 10. 台账与审计",
        "",
        "- A1 TwoFamilyEvaluator 是本批 solver_attempts.jsonl 的唯一 writer（evaluator event=start/end 行）；A1 solver_ledger.SolverLedger 在本架构不被调用；A2 只读配对/计数，不写、不删、不截断、不重建。",
        "- 全局单一 canonical ledger（run_dir/solver_attempts.jsonl）；同一时刻只允许一个 evaluator writer："
        "preflight 每 case 在作用域内构造并 finally close，主批每臂开始时构造、臂结束 close，禁止预构造 6 个。",
        "- 传给 evaluator 的 max_starts 是该臂预算 64，不是全局 451；全局 451 由 A2 每次 start 前读 ledger 实时累计。",
        "- attempt_id 仅是信息性字段，A1 evaluator 实例内 calls 重置，跨臂可能重复；A2/A3/A5 一律以全局唯一 case_id "
        "（主批 <arm>-<design_hash>-<f1|f2>，preflight PRE-01/02）配对 start/end。",
        "- A2 append-only 冻结日志由 A1 freeze_api.append_chained_record 写、A1 verify_chain 读；逐设计记录先于 start；"
        "run 末调 A1 build_final_run_manifest（issued 必须 true）交 final pair manifest + 完整日志；拒绝则写 stop_report 且不宣告成功。",
        "- 异常边界：preflight、每臂、整批全 try/except/finally；先 close evaluator（确认无 writer），"
        "再仅对确实无 end 的 start 追加 status=EXECUTOR_EXCEPTION 的 end 行（不退款、不伪造 end），最后写 stop_report；"
        "stop_report 中 physical_solver_starts/internal 从 ledger 实算，不得硬写 0。",
        "- stale lock 不得静默删除，fail-closed 并写 stop_report。",
        "- A5 是正式结果签署人；A2 只做独立交叉核对，不签署。",
        "",
        "## 11. 批准绑定（sequential）",
        "",
        "- approval 绑定：policy_doc_sha256、builder_code_sha256、evaluator_code_sha256、"
        "pair_manifest_sha256=%s、initial_designs_manifest_sha256、append_only_log_path、"
        "freeze_rule、final_run_manifest_required=true。" % FROZEN_PAIR_MANIFEST_SHA256,
        "- approval 绑定策略+代码+初始种子，不绑定未来设计；这是运行时分阶段冻结，"
        "不是批准时已知全部设计；禁止 exact all-design approval。",
        "- 初始 design 集在 plan 中固定；运行中新增设计只能来自六臂 proposal 的臂盲冻结。",
        "",
        "## 12. 代码绑定的当前状态",
        "",
        "- A1 FreezeAPI：%s；schema=%s；builder_code_sha256=%s。" % (
            a1.get("freeze_api_status", "PENDING"),
            a1.get("freeze_api_schema", ""), a1.get("builder_code_sha256", "")),
        "- A1 evaluator v1.2：%s；evaluator_code_sha256=%s。" % (
            a1.get("evaluator_status", "PENDING"), a1.get("evaluator_code_sha256", "")),
        "- A2 executor sha256：%s；runner_version=%s。" % (
            a2.get("a2_executor_sha256", ""), RUNNER_VERSION),
        "- A1 evaluator v1.2 真实路径已实现；A1 probe v3 10/10 SECURE（physical=0，证据 %s sha256=%s）。"
        "本包只做零物理预注册/骨架，尚未发生任何真实 start；执行仍需 Lead 签名、窗口 open 与 post-approval dry-run。" % (
            A1_PROBE_V3_REL, A1_PROBE_V3_SHA256),
        "- 每行证据门禁：主批每条 evaluation/per_family 行必须自带 backend=REAL_VSPAERO；"
        "preflight 每条行必须自带 backend=REPLAY_B2 且 preflight=true、counted_in_starts=true、excluded_from_e1_e6=true；"
        "禁止 run 级 backend 继承，A3 工具按行校验。",
        "",
        "## 13. A5 Q2=A 八条硬条件的落地位置",
        "",
        "1. approval 绑定 policy/builder/evaluator/P2AFAM/initial/append-log/freeze-rule/final-manifest。",
        "2. runner：冻结点先于任何 start；append-only 记录在 start 之前。",
        "3. A1 evaluator MODE_RUNTIME 在 evaluate 前校验记录存在与两族 SHA，否则 0 start。",
        "4. 同设计冻结一次、六臂共用；VOID 全局。",
        "5. run 末 final manifest + 完整日志。",
        "6. plan/prereg/approval 披露 sequential 语义。",
        "7. initial 3 designs 零物理预冻结并精确列入 manifest。",
        "8. 若 A1 无法提供 2-3，则退 B（分周期），不得在 A2 侧静默实现。",
        "",
        "## 14. caps 对账（386/451/2,702/3,157/64/0）",
        "",
        "- planned starts=386 = 2 个 preflight slot（每个 7 internal）+ 384 个主批 slot；preflight 明确占独立 slot 区并计 starts。",
        "- reserve 64 starts（32 组）在 planned 之外；max_starts=386+64=451。",
        "- planned internal=386x7=2,702；max_internal=451x7=3,157；refine=0。",
        "- max_geometry_builds=8,000 是零物理全局 fail-closed 上限，与 start 上限独立；每设计硬上限 100。",
        "",
        "## 16. B2 冻结几何字节的使用许可（待 A5）",
        "",
        "- B2 policy：每设计只使用臂盲冻结后的 .vspgeom/.vkey 字节作为 solver 输入，不重建、不换族。",
        "- 许可范围：仅本 batch/run；禁止跨 run、跨 batch、P1/P1C/P1R 复用；批准人 lead、时间待签。",
        "- approval.b2_waiver 与 plan.b2_waiver 记录 policy_doc、A1 evaluator SHA 与 P2AFAM manifest SHA。",
        "",
        "## 15. 记录 schema 与真实证据门禁",
        "",
        "- 每个设计只写一条共享冻结记录：arm_id=ALL_SIX_SHARED、slot_id=SHARED-<design_hash>、"
        "shared_by_arms=[BO,DE,PSO,ABO,ADE,APSO]；记录含 design_hash/x12/status/families/family_role_map/"
        "arm_blind/roles/kind/schema/seq/parent_hash/record_hash/physical_call_count，按 (design, family) 去重不会误报重复；"
        "链记录由 A1 append_chained_record 追加并由 A1 verify_chain 校验，A2 不实现第二套 parent_hash 语义。",
        "- evaluations 与 ledger 的每一行必须显式 backend=REAL_VSPAERO；不接受 run 级继承，"
        "A3/A5 工具拒绝 MOCK/REPLAY/synthetic 行进入真实结果。",
        "- 2 个 preflight 行为 REPLAY_B2，逐行标 preflight=true，计入 386 starts/2,702 internal，"
        "但与主批分开统计并排除 E1-E6。",
        "",
        "## 17. 串行 evaluator 生命周期与异常恢复（A5 P2AV2-21/24）",
        "",
        "- canonical ledger：run_dir/solver_attempts.jsonl，A1 TwoFamilyEvaluator 唯一 writer（event=start/end 行）；A1 solver_ledger.SolverLedger 不被调用；全批不删除、不截断、不重建。",
        "- preflight：每个 case 新建独立 A1 TwoFamilyEvaluator（max_starts=1），调用后 finally close；"
        "PRE-01 与 PRE-02 绝不共享实例；per-case starts 取自 record.solver.physical_solver_starts 并与 ledger event=start delta 交叉校验。",
        "- 主批：每臂开始时才构造 A1 TwoFamilyEvaluator（max_starts=64），臂结束后 finally close；同一时刻仅一个 writer。",
        "- A1LedgerReader：按 event=='start' 计数；按 case_id 配对 start/end；case_id 为空或重复即 fail-closed；"
        "attempt_id 仅信息性，不作为配对键。",
        "- 异常：close 先于任何台账追加；仅对无 end 的 start 补 EXECUTOR_EXCEPTION end 行；写 stop_report.json，"
        "physical 计数从 ledger 实算；非 0 退出。",
        "- 启动前校验 initial 3 designs：initial_designs_manifest 文件 SHA 与 approval 绑定一致，"
        "x12 重算 design_hash 必须分别等于 d51866f7d3c49303 / eb00b7ad545243e6 / dc96d2438a6dddc3。",
        "- Sref(x) 在 solver 启动前由 x12 计算/校验/缓存（零物理）；缺失/非有限/<=0 即 0 starts 拒绝。",
        "",
        "## 18. internal 记账与 preflight 异常顺序（A5 P2AV2-21）",
        "",
        "- A1 evaluator event 行不含 internal_solver_cases；A2 不从 ledger 求 internal，也不静默默认 7。",
        "- internal 一律按预注册政策常量 INTERNAL_PER_START_POLICY 推导：internal = 7 x physical_solver_starts（starts==0 则 internal=0），覆盖 preflight/diagnostics/main 全部 evaluation/record 行；ledger 只审计 physical start/end；阶段边界与最终 summary 守恒校验 sum(internal)=7 x starts，不一致 fail-closed 为 ACCOUNTING_INCONSISTENT。",
        "- batch_summary 分列 preflight_starts、main_starts、total_ledger_starts（event==start 计数）、record_internal_cases（记录求和），并标 source；不得把 0 当真实 internal。",
        "- preflight 非 PASS（含 start 后异常被吞成 case FAIL）顺序固定：先 close evaluator -> _repair_pending_starts 只补 orphan end（不退款）-> 从 ledger 实算 physical -> 写 stop_report -> 再写 summary。",
        "",
        "## 19. R10 addendum（预冻结 family row flat/nested 兼容修复；零物理预注册）",
        "",
        "- R1（batch DREAL001-P2-20261111-06、run DREAL001-P2A2R-20261111-01）：2 starts/14 internal，2/2 SOLVER_FAILED（几何文件名别名缺失），主批 0；PREFLIGHT_FAIL_MAIN_BATCH_NOT_RUN。",
        "- R2（batch 07、run DREAL001-P2A2R2-20261111-01）：2 starts/14 internal，2/2 PASS_BYTE polar，status 词表假 FAIL；主批 0。",
        "- R3（batch 08、run DREAL001-P2A2R3-20261111-01）：2 starts/14 internal，2/2 PASS_BYTE polar；BO 臂主批前因本机 sandbox 拒绝 mkdtemp 0o700 目录而异常停止。",
        "- R4（batch 09、run DREAL001-P2A2R4-20261111-01）：2 starts/14 internal，2/2 PASS_BYTE polar；BO 第 1 次评估抛 A1 V12ConfigurationError UNIT_BOX_VECTOR_NOT_ACCEPTED，主批 0。",
        "- R5（batch 10、run DREAL001-P2A2R5-20261111-01）：SETUP_STOP_DESIGN_SPACE_IMPORT，0 starts/0 internal；design_space 导入解析到 A2 旧模块；证据只读保留。",
        "- R6（batch 11、run DREAL001-P2A2R6-20261111-01）：2 starts/14 internal 的 PASS_BYTE replay preflight + 1 start/7 internal 的 main 首案评估；polar 成功生成但 on_evaluation 因 executor 的 design_hash(canonical_x12(...)) 字符串误用抛 ValueError，S1 main-stage 停止；主批 1 start。R6 NaN 机制未证明（候选 H1/H2/H3）。",
        "- R7（batch 12、run DREAL001-P2A2R7-20261111-01）：2 starts/14 internal PASS_BYTE replay preflight + 2 个诊断设计各按完整 pair 评估（4 starts/28 internal）；main 首设计 design15 在 solver 启动前因 FROZEN_BYTES_SHA_MISMATCH 停止，主批 0；S1_STOP_FROZEN_BYTES_SHA_MISMATCH。",
        "- R8（batch 13、run DREAL001-P2A2R8-20261111-01）：SETUP_STOP_PREFROZEN_GEOM_MISSING，0 starts/0 internal；executor 的预冻结复用 gate 把 initial manifest 的平铺 family 行误当嵌套结构，solver/ledger 均未启动，主批 0；R8 证据只读保留、永久排除。",
        "- R9（batch 14、run DREAL001-P2A2R9-20261111-01）：PASS_BYTE replay preflight 2 starts/14 internal + 2 个诊断设计按完整 pair 评估（4 starts/28 internal），合计 charged 6 starts/42 internal；main 首设计评估前因诊断 internal 记账不一致（记录 internal=0，预注册 4/28）停止，main 0；STOP_DIAGNOSTICS_ACCOUNTING_INCONSISTENT；R9 证据只读保留、永久排除。",
        "- R10 仅做 A2 执行/报告层最小修复：(a) internal_solver_cases 一律按预注册政策常量推导 internal = 7 x physical_solver_starts（来源 INTERNAL_PER_START_POLICY；不再从 A1 ledger 推断，也不再静默默认 7），覆盖 preflight/diagnostic/main 全部 evaluation/record 行；(b) 阶段边界与最终 summary 守恒校验 sum(internal)=7 x starts，不一致 fail-closed 为 ACCOUNTING_INCONSISTENT；(c) evaluation/record 行记录 polar_sha256（可得时；不可得记 null 并披露）；(d) 零物理 smoke 走 executor 真实 main-path 记账链路（假 solver/录制结果，含 preflight 与 main 两段评估）证明 internal=7 x starts 且 phase 守恒、physical=0、solver_started=false；(e) R10 不重跑诊断：R10 矩阵不含诊断，引用 R9 诊断证据 SHA；保留 R9 全部已修项（prefrozen flat/nested reuse、observe、x12 域、invalid tolerance、launcher preload/env shim、异常路径落盘）。",
        "- R10 窗口 2026-11-11T18:30:00Z-2026-11-12T04:00:00Z / token WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z；启动死线 2026-11-11T21:00:00Z、clean stop 2026-11-12T02:30:00Z、硬停 2026-11-12T04:00:00Z。",
        "- R10 planned 386 starts/2,702 internal（2 preflight + 384 main；不重跑诊断；reserve 64）；累计 prior 62/446（含 R9 6/42）+ 386/2,702 = 448 starts/3,148 internal，均在 451/3,157 上限内（headroom 3/9）；R1-R9 全部排除出 E1-E6 端点。",
        "- 其余 policy 字节不变：451/3,157/64/0/8,000、104 族对、初始 3 设计、seed 42、no-retry/timeout 60s/串行 OMP1；bundle 995bb12f、A1 evaluator f74a4752/freeze 31d78182/openvsp_model c40b11df/design_space 8f9b893c+8b29d1e3；A2 executor 只改执行/报告层（其 SHA 由构建器回填）。R1-R9 旧目录、旧 approval 与旧证据原字节只读保留；R10 使用新 run dir DREAL001-P2A2R10-20261111-01 与新 approval（supersedes R9 approval）。"
        "",
        "",
    ]
    if plan_sha:
        lines += ["plan_sha256（由构建器回填）：%s" % plan_sha, ""]
    return "\n".join(lines) + "\n"


def _preflight_binding(bundle_path: Optional[Path] = None, a1_root: Optional[Path] = None) -> dict[str, Any]:
    root = Path(a1_root) if a1_root is not None else DEFAULT_A1_ROOT
    path = Path(bundle_path) if bundle_path is not None else Path(A1_PREFLIGHT_BUNDLE_PATH)
    if not path.is_file():
        path = root / "research/concorde_metaopt/dreal001/geometry/replay_bundles/P2A_V2_PREFLIGHT_20261111/bundle_manifest.json"
    binding = _file_binding(path, "A1_PREFLIGHT_BUNDLE")
    binding["expected_cases"] = PREFLIGHT_CASES
    binding["case_ids"] = [c["case_id"] for c in PREFLIGHT_CASES_DEFAULT]
    binding["expected_polar_sha256"] = {c["case_id"]: c["expected_polar_sha256"] for c in PREFLIGHT_CASES_DEFAULT}
    binding["expected_vspgeom_sha256"] = {c["case_id"]: c["expected_vspgeom_sha256"] for c in PREFLIGHT_CASES_DEFAULT}
    binding["judgement"] = ["PASS_BYTE", "PASS_NUMERIC", "FAIL"]
    binding["counted_in_e1_e6"] = False
    binding["replay_physical"] = True
    binding["replay_physical_starts_per_case"] = 1
    binding["replay_internal_cases_per_case"] = 7
    binding["replay_pass_authority"] = "A2_BATCH_ONLY"
    binding["a1_replay_semantics_doc"] = {
        "path": "docs/planning/dnext001_replay_b2_spawn_semantics.md",
        "sha256": "D95137D485C6A26D2CAA7CB30EA98F62DAB578B37F90AC52B4205D597BE2DB2F",
        "a1_commit": "c80beb5",
    }
    cases = {}
    for c in PREFLIGHT_CASES_DEFAULT:
        label = c["family_label"]
        role = "f1" if label == "483x418" else "f2"
        cases[c["case_id"]] = {
            "design_hash": c["design_hash"],
            "family": label,
            "family_role": role,
            "vspgeom_sha256": c["expected_vspgeom_sha256"],
            "vkey_sha256": c["expected_vkey_sha256"],
            "vspaero_sha256": c["expected_vspaero_sha256"],
            "csf_sha256": c["expected_csf_sha256"],
            "polar_sha256": c["expected_polar_sha256"],
            "replay_physical": True,
            "launch_kind": "REAL_REPLAY_B2",
            "replay_physical_starts": 1,
            "replay_internal_cases": 7,
        }
    binding["replay_bundles"] = {
        "schema": "dreal001.replay_bundle_binding.v1",
        "bundle_manifest_path": str(path.resolve()),
        "bundle_root": str(path.parent.resolve()),
        "semantics_doc_path": str((root / "docs/planning/dnext001_replay_b2_spawn_semantics.md").resolve()),
        "bundle_manifest_sha256": binding["sha256"],
        "semantics_doc_sha256": "d95137d485c6a26d2caa7cb30ea98f62dab578b37f90ac52b4205d597be2db2f",
        "cases": cases,
        "family_role_rule": "f1 = 483x418 (smaller nodes/elements), f2 = 543x472; consistent with A1 FreezeAPI role_map",
    }
    binding["launch_kind"] = "REAL_REPLAY_B2"
    binding["cases"] = [
        {"case_id": c["case_id"], "design_hash": c["design_hash"], "family_label": c["family_label"],
         "family_role": cases[c["case_id"]]["family_role"], "launch_kind": "REAL_REPLAY_B2",
         "replay_physical": True, "replay_physical_starts": 1, "replay_internal_cases": 7,
         "vspgeom_sha256": c["expected_vspgeom_sha256"], "vkey_sha256": c["expected_vkey_sha256"],
         "vspaero_sha256": c["expected_vspaero_sha256"], "csf_sha256": c["expected_csf_sha256"],
         "polar_sha256": c["expected_polar_sha256"]} for c in PREFLIGHT_CASES_DEFAULT
    ]
    return binding


def _projected_slots() -> dict[str, Any]:
    preflight = [{"slot_id": "PRE-%02d" % (i + 1), "kind": "PREFLIGHT",
                  "case_id": c["case_id"], "design_hash": c["design_hash"],
                  "family_label": c["family_label"]} for i, c in enumerate(PREFLIGHT_CASES_DEFAULT)]
    main = []
    for arm in ARMS:
        for ordinal in range(1, DESIGN_EVALS_PER_ARM + 1):
            for role in FAMILY_SLOTS_LABELS:
                main.append({"slot_id": "%s-D%02d-%s" % (arm, ordinal, role), "kind": "MAIN",
                             "arm_id": arm, "design_ordinal": ordinal, "family_role": role})
    reserve = []
    for group in range(1, RESERVE_GROUPS + 1):
        for role in FAMILY_SLOTS_LABELS:
            reserve.append({"slot_id": "RESERVE-G%02d-%s" % (group, role), "kind": "RESERVE",
                            "reserve_group": group, "family_role": role})
    projected = {"preflight": preflight, "main": main, "reserve": reserve}
    return {
        "schema": "dreal001.p2a_v2.projected_slot_matrix.v1",
        "preflight_slots": len(preflight), "main_slots": len(main), "reserve_slots": len(reserve),
        "total_projected_slots": len(preflight) + len(main) + len(reserve),
        "slot_digest": _sha256_json(projected),
        "matrix": projected,
    }


def projected_case_matrix_digest() -> tuple[str, str]:
    slots = _projected_slots()
    projected = {
        "preflight": slots["matrix"]["preflight"],
        "main": slots["matrix"]["main"],
        "reserve": slots["matrix"]["reserve"],
    }
    return _sha256_json(projected), "projected slots only: PRE-01..02 + 384 main slots (arm/design_ordinal/family_role) + 64 reserve slots; runtime design_hash is deliberately absent"


def build_plan(*, prereg_sha256: str, prereg_path: Path,
               initial_manifest: Mapping[str, Any], initial_manifest_sha256: str,
               a1: Optional[Mapping[str, Any]] = None,
               a2: Optional[Mapping[str, Any]] = None,
               created_utc: Optional[str] = None) -> dict[str, Any]:
    a1 = dict(a1 or a1_binding())
    a2 = dict(a2 or a2_code_binding())
    preflight = _preflight_binding()
    slots = _projected_slots()
    case_digest, digest_scope = projected_case_matrix_digest()
    pkg = Path(prereg_path).parent
    plan = {
        "schema": PLAN_SCHEMA,
        "plan_version": "p2a-v2.0",
        "status": "DRAFT_PENDING_LEAD_APPROVAL_NOT_EXECUTABLE",
        "executable": False,
        "stage": STAGE,
        "batch_id": BATCH_ID,
        "canonical_batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "run_dir": str(Path(pkg).resolve()),
        "run_dir_name": Path(pkg).name,
        "batch_vs_run": {
            "batch_id": BATCH_ID,
            "run_id": RUN_ID,
            "relationship": "one P2a v2 batch_id DREAL001-P2-20261111-15 maps to one run DREAL001-P2A2R10-20261111-01; the run directory name equals run_id",
            "run_dir_name_must_equal_run_id": True,
        },
        "created_utc": created_utc or utc_now(),
        "window": {
            "start_utc": WINDOW_START_UTC, "end_utc": WINDOW_END_UTC,
            "token": WINDOW_TOKEN, "status": "REQUESTED_NOT_SIGNED",
        },
        "window_start": WINDOW_START_UTC,
        "window_end": WINDOW_END_UTC,
        "window_token": WINDOW_TOKEN,
        "authority": {
            "lead_decision": "A5 Q2=A; Lead m02229",
            "approval_required": True,
            "a5_review_required": True,
            "executable": False,
        },
        "policy_doc": {"path": str(Path(prereg_path)), "sha256": prereg_sha256},
        "policy_doc_sha256": prereg_sha256,
        "pair_manifest_sha256": FROZEN_PAIR_MANIFEST_SHA256,
        "pair_manifest_path": A1_PAIR_MANIFEST_PATH,
        "policy_doc_path": str(Path(prereg_path).resolve()),
        "builder_code_path": str((Path(a1.get("a1_root", DEFAULT_A1_ROOT)) / "research/concorde_metaopt/dreal001/geometry/openvsp_model.py").resolve()),
        "builder_code_sha256": a1.get("builder_code_sha256"),
        "builder_code_bundle_sha256": a1.get("builder_code_bundle_sha256"),
        "evaluator_code_sha256": a1.get("evaluator_code_sha256"),
        "initial_designs_manifest_sha256": initial_manifest_sha256,
        "append_only_log_path": APPEND_ONLY_LOG_PATH,
        "family_pair_policy": {
            "global_family_pair": None,
            "hardcoded_pair_forbidden": True,
            "selection": "arm-blind runtime A1 FreezeAPI discovery per design",
            "distinct_observed_pairs_in_p2afam_manifest": 104,
            "global_pair_design_indices": [0, 2, 5, 8, 9, 11, 13, 14],
            "fixed_global_pair_status": "FORBIDDEN",
        },
        "family_policy": {
            "mode": "RUNTIME_APPEND_ONLY_SEQUENTIAL_FREEZE",
            "short_name": "C+B2",
            "discovery": "arm-blind K=10 fresh-process direct builds; if only one family is observed continue to 40; |F|>=3 -> DESIGN_VOID",
            "force": "after a two-family union, force each target family in fresh processes, <=40 attempts per family",
            "freeze": "freeze .vspgeom/.vkey/.vsp3 bytes per family; solver consumes frozen .vspgeom only",
            "roles": "f1=smaller (nodes,elements), f2=larger; deterministic and arm-independent",
            "arm_blind": True,
            "force_attempts_per_family": FORCE_ATTEMPTS_PER_FAMILY,
            "family_pair_manifest": A1_PAIR_MANIFEST_PATH,
            "family_pair_manifest_sha256": FROZEN_PAIR_MANIFEST_SHA256,
            "required_record_fields": ["design_hash", "x12", "status", "families", "family_role_map",
                                       "arm_id", "slot_id", "shared_by_arms", "arm_blind", "roles",
                                       "kind", "schema", "seq", "parent_hash", "record_hash",
                                       "physical_call_count"],
            "record_arm_slot_convention": "one shared pair record per design: arm_id=ALL_SIX_SHARED, slot_id=SHARED-<design_hash>, shared_by_arms=[BO,DE,PSO,ABO,ADE,APSO]; per-(design,family) dedupe is therefore unambiguous",
            "hash_chain": True,
            "hash_chain_description": "append-only hash chain written by A1 freeze_api.append_chained_record and validated by A1 freeze_api.verify_chain: each record carries seq, parent_hash and record_hash",
            "freeze_once_shared_by": list(ARMS),
            "append_only_log": APPEND_ONLY_LOG_PATH,
            "append_only_log_path": APPEND_ONLY_LOG_PATH,
            "append_only_record_schema": FREEZE_API_CHAIN_SCHEMA,
            "append_only_writer": "A1 freeze_api.append_chained_record (single source of truth)",
            "append_only_reader": "A1 freeze_api.verify_chain + read_chain",
            "append_only_repair_forbidden": True,
            "hash_chain": True,
            "parent_hash_field": "parent_hash",
            "append_record_before_any_start": True,
            "recompute_forbidden": True,
            "pick_family_forbidden": True,
            "overwrite_forbidden": True,
            "pre_sha_required": True,
            "post_sha_required": True,
            "void_is_global": True,
            "void_status": "FAMILY_UNREACHABLE_DESIGN_VOID",
            "final_run_manifest_required": True,
            "freeze_rule": FREEZE_RULE,
            "freeze_api_schema": FREEZE_API_SCHEMA,
            "discovery_k": FREEZE_API_DISCOVERY_K,
            "max_geometry_builds": MAX_GEOMETRY_BUILDS,
            "max_geometry_builds_per_design": MAX_GEOMETRY_BUILDS_PER_DESIGN,
            "zero_physical_wall_cap_seconds": ZERO_PHYSICAL_WALL_CAP_SECONDS,
        },
        "objective": {
            "primary": "TWO_FAMILY_EQUAL_WEIGHT_MEAN_CDI",
            "primary_formula": "0.5*CDi(f1)+0.5*CDi(f2)",
            "primary_short": "within-design equal-weight mean CDi over the two frozen families",
            "normalized_companion": "none: CDi is the primary endpoint",
            "secondary": "D_i=q*Sref_family*CDi(family) descriptive only; mean(D_i) is secondary and not ranked",
            "secondary_short": "mean(D_i) descriptive only",
            "q_pa": Q_PA, "l_ref_n": L_REF_N, "lift_tolerance_rel": LIFT_TOLERANCE_REL,
            "single_family_ranking_forbidden": True,
            "cross_family_numeric_comparison_forbidden": True,
            "fuel_burn_kg": None,
            "physical_validation_status": "NOT_VALIDATED",
        },
        "solver_contract": {
            "exe_path": VSPAERO_EXE_PATH,
            "exe_sha256": VSPAERO_EXE_SHA256,
            "exe_bytes": VSPAERO_EXE_BYTES,
            "exe_binding": "plan and approval bind the same absolute path + SHA256; the executor refuses any other exe",
            "argv": "vspaero.exe -omp 1 concorde_baseline",
            "forbidden_flags": ["-fs", "-mach", "-alpha", "-beta"],
            "parallelism": 1, "omp_threads": 1,
            "timeout_seconds": TIMEOUT_SECONDS,
            "internal_solver_cases_per_start": 7,
            "no_retry": True,
        },
        "execution_lifecycle": {
            "mode": "SEQUENTIAL_ONE_EVALUATOR_AT_A_TIME",
            "canonical_ledger_path": "solver_attempts.jsonl",
            "canonical_ledger_writer": "A1 TwoFamilyEvaluator only",
            "preflight_evaluator_instance_per_case": True,
            "main_evaluator_instance_per_arm": True,
            "main_evaluator_construct_scope": "inside each arm; finally close",
            "main_evaluator_max_starts": DESIGN_EVALS_PER_ARM * 2,
            "max_starts_per_evaluator_is_arm_budget_not_global": True,
            "global_max_starts_451_enforced_by": "A2 P2AV2Runner reads A1 ledger count_starts before every start",
            "one_writer_at_a_time": True,
            "ledger_delete_truncate_rebuild_forbidden": True,
            "stale_lock_policy": "fail-closed + stop_report; never silently deleted",
            "attempt_id_semantics": "attempt_id is informational only and may repeat across arm-scoped evaluators; case_id is the globally unique pairing key",
            "case_id_uniqueness": "main case_id=<arm>-<design_hash>-<f1|f2>; preflight case_id=PRE-01/02",
            "exception_policy": "close evaluator, then repair ONLY genuinely unpaired starts with status EXECUTOR_EXCEPTION, then write stop_report; no refund, no fake end",
            "final_run_manifest_builder": "A1 freeze_api.build_final_run_manifest (issued must be true)",
            "internal_count_policy": "ledger audits physical start/end only; internal_solver_cases is summed from evaluations/record rows, never inferred from ledger",
            "batch_summary_start_fields": ["preflight_starts", "main_starts", "total_ledger_starts", "record_internal_cases"],
            "batch_summary_sources": {"total_ledger_starts": "canonical evaluator event ledger, event==start", "record_internal_cases": "evaluations/record per-family rows"},
            "preflight_failure_order": "close evaluator -> repair only genuinely unpaired starts -> physical recomputed from ledger -> write stop_report -> write summary",
        },
        "stop_report_contract": {
            "path": "stop_report.json",
            "schema": "dreal001.p2a_v2.stop_report.v1",
            "required_fields": ["phase", "error_type", "message", "traceback", "pending_starts_repaired",
                                "ledger_starts", "physical_solver_starts", "internal_solver_cases", "internal_solver_cases_source", "ledger_internal_cases_recorded"],
            "physical_counts_from_ledger": True,
            "no_fake_end_without_start": True,
        },
        "design_flow": {
            "step_0": "preflight 2 replay cases (PRE-01/PRE-02); main batch is gated by PASS_BYTE or accepted PASS_NUMERIC",
            "step_1": "for each runtime design: A1 FreezeAPI arm-blind freeze (or reuse an existing PAIR_READY record)",
            "step_2": "append-only hash-chained record (parent_hash) written before any start",
            "step_3": "two solver starts: f1 then f2; frozen-byte PRE/POST SHA verification",
            "step_4": "design primary = 0.5*CDi(f1)+0.5*CDi(f2), the within-design equal-weight mean CDi; D_i is secondary descriptive only",
            "step_5": "Sref(x) is resolved from x12 BEFORE any solver start; missing/invalid Sref -> 0 starts and ExecutorRefused",
            "step_6": "run ends with the A1 final run manifest; refusal writes stop_report and never declares success",
            "initial_designs_are_shared_by_all_six_arms": True,
            "final_run_manifest_required": True,
        },
        "preflight": {
            **preflight,
            "runs_before_main_batch": True,
            "planned_starts": PREFLIGHT_PLANNED_STARTS,
            "planned_internal_cases": PREFLIGHT_PLANNED_INTERNAL_CASES,
            "numeric_acceptance_required": True,
            "numeric_rtol": PREFLIGHT_ACCEPT_NUMERIC_RTOL,
            "replay_physical": True,
            "replay_physical_starts_per_case": 1,
            "replay_internal_cases_per_case": 7,
            "evaluator_instance_per_case": True,
        "duplicate_cell_policy": "A fresh A1 TwoFamilyEvaluator instance per case; PRE-03 is retired, PRE-01 and PRE-02 are distinct cells and must never share one instance.",
        "replay_pass_authority": "A2_BATCH_ONLY",
            "a1_replay_semantics_doc_sha256": "D95137D485C6A26D2CAA7CB30EA98F62DAB578B37F90AC52B4205D597BE2DB2F",
            "main_batch_may_start_only_if": ["PASS_BYTE", "PASS_NUMERIC_ACCEPTED"],
        },
        "initial_designs": {
            "manifest_path": str((Path(pkg) / INITIAL_MANIFEST_FILENAME).resolve()),
            "manifest_sha256": initial_manifest_sha256,
            "manifest_schema": INITIAL_MANIFEST_SCHEMA,
            "design_indices": list(INITIAL_DESIGN_INDICES),
            "design_hashes": list(INITIAL_DESIGN_HASHES),
            "family_pairs": {
                "15": ["462x401", "546x472"],
                "16": ["456x395", "548x474"],
                "17": ["481x416", "539x468"],
            },
            "designs": [
                {"design_index": d["design_index"], "design_hash": d["design_hash"],
                 "x12": d["x12"], "family_labels": sorted(d["families"]),
                 "family_pair": sorted(d["families"])}
                for d in initial_manifest.get("designs", [])
            ],
            "source_file_sha256": FROZEN_PAIR_MANIFEST_SHA256,
            "records_subset_sha256": initial_manifest.get("records_subset_sha256"),
            "zero_physical_prefrozen": True,
            "shared_by_all_six_arms": True,
            "inside_a_arm_historical_labels": False,
            "note": INITIAL_DESIGNS_NOTE,
        },
        "caps_reconciliation": {
            "planned_starts": PLANNED_STARTS,
            "main_starts": MAIN_PLANNED_STARTS,
            "preflight_starts": PREFLIGHT_PLANNED_STARTS,
            "preflight_internal_cases": PREFLIGHT_PLANNED_INTERNAL_CASES,
            "reserve_starts": RESERVE_STARTS,
            "max_starts": MAX_STARTS,
            "planned_internal_cases": PLANNED_INTERNAL_CASES,
            "max_internal_cases": MAX_INTERNAL_CASES,
            "formula": "2 preflight slots (7 internal each) + 2 diagnostic slots (7 internal each) + 384 main slots = 388 planned starts; planned_internal=388*7=2716; signed caps max_starts=451, max_internal=3157; reserve 64 starts sit outside planned",
            "preflight_slots_count_as_starts": True,
            "preflight_slots_are_a_separate_slot_region": True,
            "max_geometry_builds": MAX_GEOMETRY_BUILDS,
            "max_geometry_builds_basis": "global fail-closed zero-physical cap, independent of the start cap; per-design hard cap 100",
            "max_refine_starts": MAX_REFINE_STARTS,
        },
        "b2_waiver": {
            "policy": "B2_FROZEN_GEOMETRY_BYTES",
            "status": "PENDING_A5_G-P2AV2R10-PRE",
            "batch_scoped": True,
            "scope": {"batch_id": BATCH_ID, "run_id": RUN_ID},
            "per_design_frozen_assets": ["frozen .vspgeom", "frozen .vkey"],
            "forbidden_reuse": ["cross-run", "cross-batch", "P1/P1C/P1R reuse as P2a-v2 solver input"],
            "approver": "lead",
            "approved_at_utc": None,
            "a1_v1_2_code_sha256": a1.get("evaluator_code_sha256"),
            "pair_manifest_sha256": FROZEN_PAIR_MANIFEST_SHA256,
            "physical_call_count": 0,
        },
        "evidence_gate": {
            "row_backend_required": "REAL_VSPAERO",
            "row_backend_field": "backend",
            "row_backend_required_value": "REAL_VSPAERO",
            "per_family_rows_require_backend": True,
            "row_level_inheritance_allowed": False,
            "mock_replay_synthetic_rows_accepted": False,
            "preflight": {"count": PREFLIGHT_PLANNED_STARTS, "preflight": True, "backend": "REPLAY_B2",
                          "counted_in_starts": True, "excluded_from_e1_e6": True},
            "main_rows": {"backend": "REAL_VSPAERO", "preflight": False,
                          "row_backend_field": "backend", "per_row_required": True},
            "note": "every main evaluation/per_family row carries backend=REAL_VSPAERO; every preflight row carries backend=REPLAY_B2; A3 validates each row, not the run-level field",
        },
        "matrix": {
            "arms": list(ARMS),
            "seed": SEED,
            "design_evaluations_per_arm": DESIGN_EVALS_PER_ARM,
            "starts_per_design": 2,
            "starts_per_arm": DESIGN_EVALS_PER_ARM * 2,
            "main_planned_starts": MAIN_PLANNED_STARTS,
            "planned_starts": PLANNED_STARTS,
            "reserve_groups": RESERVE_GROUPS,
            "reserve_starts": RESERVE_STARTS,
            "max_starts": MAX_STARTS,
            "planned_internal_cases": PLANNED_INTERNAL_CASES,
            "max_internal_cases": MAX_INTERNAL_CASES,
            "max_refine_starts": MAX_REFINE_STARTS,
            "single_seed_descriptive_only": True,
            "projected_slot_digest": slots["slot_digest"],
            "case_matrix_digest": case_digest,
            "case_matrix_digest_scope": digest_scope,
        },
        "budget_and_caps": {
            "planned_starts": PLANNED_STARTS,
            "max_starts": MAX_STARTS,
            "planned_internal_cases": PLANNED_INTERNAL_CASES,
            "max_internal_cases": MAX_INTERNAL_CASES,
            "max_refine_starts": MAX_REFINE_STARTS,
            "per_case_timeout_seconds": TIMEOUT_SECONDS,
            "concurrency": 1,
            "omp_threads": 1,
            "infra_retries_allowed": 0,
            "automatic_numeric_retry": False,
            "max_geometry_builds": MAX_GEOMETRY_BUILDS,
            "max_geometry_builds_per_design": MAX_GEOMETRY_BUILDS_PER_DESIGN,
            "zero_physical_wall_cap_seconds": ZERO_PHYSICAL_WALL_CAP_SECONDS,
            "reserve_rule": "only globally voided designs consume one reserve group (2 starts); no per-arm top-up; reserve exhaustion -> NOT_VALIDATED",
        },
        "stop_conditions": [
            {"code": "S1", "condition": "preflight not PASS", "action": "main batch NOT_RUN"},
            {"code": "S2", "condition": "any solver result != SOLVED_VALID", "action": "stop batch; no retry; no replacement run"},
            {"code": "S3", "condition": "negative or non-finite CDi", "action": "stop batch"},
            {"code": "S4", "condition": "frozen .vspgeom/.vkey/canonical SHA mismatch pre or post", "action": "0 start or one charged unusable start; stop batch"},
            {"code": "S5", "condition": "starts/internal above caps or ledger mismatch", "action": "ACCOUNTING_MISMATCH stop"},
            {"code": "S6", "condition": "global VOID designs exceed reserve groups", "action": "NOT_VALIDATED stop"},
            {"code": "S7", "condition": "geometry builds or zero-physical wall cap exceeded", "action": "NOT_VALIDATED stop"},
            {"code": "S8", "condition": "approval/window/executor blob invalid", "action": "0 start stop"},
            {"code": "S9", "condition": "executor exception", "action": "end line + stop_report; no silent retry"},
        ],
        "endpoint_policy": [
            {"code": "E1", "definition": "primary = within-design equal-weight mean CDi over the two frozen families (0.5*CDi(f1)+0.5*CDi(f2)); D_i is not the primary endpoint", "in_primary": True},
            {"code": "E2", "definition": "secondary descriptive only: D_i=q*Sref_family*CDi(family); mean(D_i) is not ranked; no normalized companion is defined", "in_primary": False},
            {"code": "E3", "definition": "single-family/cross-family/cross-run numeric comparison forbidden", "in_primary": False},
            {"code": "E4", "definition": "single seed, 32 designs/arm, descriptive only; no p-value, no winner", "in_primary": False},
            {"code": "E5", "definition": "VOID/missing pair excluded from E1 but disclosed", "in_primary": False},
            {"code": "E6", "definition": "fuel_burn_kg=null; no fuel/range evidence", "in_primary": False},
        ],
        "statistics_policy": {
            "single_seed": 42,
            "designs_per_arm": DESIGN_EVALS_PER_ARM,
            "descriptive_only": True,
            "significance_testing": "NOT_PERFORMED",
            "winner_declaration": "FORBIDDEN",
            "paired_scope": "within design (f1/f2) only; no cross-family pairing",
            "within_design": True,
            "equal_weight_family_average": True,
            "significance_claim_allowed": False,
            "significance_policy": "no significance claims; single seed descriptive only",
            "scope_note": "within-design paired only",
            "no_winner": True,
            "optimizer_pass": "NOT_SIGNED",
        },
        "fairness_rules": [
            "six arms share the same task, initial 3 designs, B=32 design evaluations, seed=42",
            "six arms share the same frozen family pair and append-only record",
            "A-arm historical labels are only the 15 committed P1C/P1R designs; zero new labels in P2a v2",
            "cold-start baseline sees only this run's VisibleLabelStore; historical support is not an immediate label",
            "VOID designs are global and use the same reserve; no per-arm compensation",
        ],
        "void_policy": {
            "family_unreachable": "entire design VOID for all six arms",
            "void_status": "FAMILY_UNREACHABLE_DESIGN_VOID",
            "single_family_disclosure": "recorded but never used in primary",
            "reserve_replacement": "next proposal from the same arm; one global reserve group",
            "reserve_exhausted": "NOT_VALIDATED stop",
        },
        "ledger_policy": {
            "single_writer": "A1 TwoFamilyEvaluator (canonical evaluator event ledger)",
            "a2_access": "read_only_pairing_and_count_starts",
            "solver_attempts_path": "solver_attempts.jsonl",
            "a2_append_only_log_path": APPEND_ONLY_LOG_PATH,
            "a2_may_write_solver_attempts": False,
            "ledger_schema": LEDGER_SCHEMA,
            "note": "A1 solver_ledger.SolverLedger is NOT invoked in P2a v2 because A2 real_spawn is a direct Popen; canonical rows are A1 evaluator event rows with event=start/end and no schema field.",
        },
        "approval_policy": {
            "binds_policy_and_code_and_initial_seeds": True,
            "binds_future_designs": False,
            "sequential_runtime_freeze": True,
            "exact_all_design_approval_forbidden": True,
            "approval_binds": [
                "policy_doc_sha256", "builder_code_sha256", "evaluator_code_sha256",
                "pair_manifest_sha256", "initial_designs_manifest_sha256",
                "append_only_log_path", "freeze_rule", "final_run_manifest_required",
            ],
        },
        "runtime_binding": {
            "a1": a1,
            "a2": a2,
            "freeze_api_required": True,
            "evaluator_mode_required": "RUNTIME_APPEND_ONLY",
            "a1_evaluator_real_path_status": a1.get("evaluator_status"),
        },
        "disclosures": [
            "P1R=INCOMPLETE_S1_STOPPED_WITH_PROTOCOL_DEVIATION; P1C=SOLVER_INTERNAL_PASS_CONTINUATION; P1 overall unsigned",
            "P2/P2a not authorized; original P2a six-arm 384-start run = NOT_RUN (mesh-family non-determinism)",
            "P2CAL v1.2 completed 12 starts / CAL_COMPLETE / ROOT_CAUSE_REQUIRED; diagnostic only",
            "12D_ACTIVE=NOT_VALIDATED; physical_validation_status=NOT_VALIDATED; fuel_burn_kg=null",
            DISCLOSURE_FAMILY_PAIRS,
            "A1 evaluator v1.2 real path is implemented (SHA256 f74a4752495fd6c5330edcaf7edb4bcbe93f99c2a76bac06b5670d1f765ae20d, freeze_api 31d781821516bb80fc158238e4ef485c361afea674ca3b962efbb89d5a737173); readiness=REAL_PATH_IMPLEMENTED_PROBE_VERIFIED_PENDING_FIRST_REAL_START; probe v3 SECURE physical=0.",
            "R7 addendum: R1/R2/R3/R4 each charged 2 preflight starts / 14 internal cases with mains NOT_RUN; R5 charged 0/0; R6 charged 2 PASS_BYTE preflight starts plus 1 main first-evaluation start (3 starts / 21 internal); all six are excluded from E1-E6 endpoints; planned 2 preflight + 2 diagnostic + 384 main = 388 starts / 2,716 internal, cumulative 50+388=438 starts / 362+2716=3078 internal <=451/3157; R6 NaN mechanism not proven (candidates H1/H2/H3); no mesh-QC data gate adopted",
            "R10 addendum: prior 62/446 (R1-R4 each 2/14, R5 0/0, R6 3/21, R7 6/42, R8 0/0 setup stop, R9 6/42 diagnostics accounting stop) unchanged; R10 planned 2 preflight + 384 main = 386 starts / 2,702 internal (diagnostics NOT in the R10 matrix; R9 diagnostic evidence referenced by SHA and excluded); cumulative 62+386=448 starts / 446+2702=3148 internal <=451/3157 (headroom 3/9); R1-R9 excluded from E1-E6 endpoints; internal cases derive from the pre-registered INTERNAL_PER_START_POLICY constant (7 x physical_solver_starts) with sum conservation checks, never from the A1 ledger and never a silent default; initial designs 15/16/17 reuse pre-frozen manifest family bytes with flat/nested row support (R9); mechanism of the R6 NaN remains unproven",
            "single seed=42, descriptive only; no winner; no optimizer PASS",
        ],
        "r6_addendum": {
            "status": "R6_DESIGN_SPACE_BINDING_FIX",
            "r1_reference": {
                "batch_id": "DREAL001-P2-20261111-06",
                "run_id": "DREAL001-P2A2R-20261111-01",
                "status": "PREFLIGHT_FAIL_MAIN_BATCH_NOT_RUN",
                "charged_starts": R1_CHARGED_STARTS,
                "charged_internal_cases": R1_CHARGED_INTERNAL_CASES,
                "main_starts": R1_MAIN_STARTS,
                "root_cause": "A2 spawn basename concorde_baseline but A1 materialised model.vspgeom/model.vkey; VSPAERO found no basename geometry",
                "excluded_from_endpoints": R6_EXCLUDES_R1_R2_R3_R4_R5_FROM_ENDPOINTS,
                "artifacts_preserved": True,
            },
            "r2_reference": {
                "batch_id": "DREAL001-P2-20261111-07",
                "run_id": R2_RUN_ID,
                "status": "PREFLIGHT_FAIL_MAIN_BATCH_NOT_RUN",
                "charged_starts": R2_CHARGED_STARTS,
                "charged_internal_cases": R2_CHARGED_INTERNAL_CASES,
                "main_starts": R2_MAIN_STARTS,
                "polar_byte_match": True,
                "root_cause": "A2 real spawn returned status SOLVED while the A2 preflight verifier required the literal SOLVED_VALID; both polar files matched the approval SHA exactly",
                "excluded_from_endpoints": R6_EXCLUDES_R1_R2_R3_R4_R5_FROM_ENDPOINTS,
                "artifacts_preserved": True,
                "superseded_approval_sha256": R2_APPROVAL_SHA256,
            },
            "r3_reference": {
                "batch_id": "DREAL001-P2-20261111-08",
                "run_id": R3_RUN_ID,
                "status": "EXECUTOR_ARM_ABORT_MAIN_BATCH_NOT_RUN",
                "charged_starts": R3_CHARGED_STARTS,
                "charged_internal_cases": R3_CHARGED_INTERNAL_CASES,
                "main_starts": R3_MAIN_STARTS,
                "polar_byte_match": True,
                "preflight_byte_match": True,
                "root_cause": "frozen A1 FreshProcessBuilder wrote task.json under a tempfile.mkdtemp 0o700 root that this DSH session sandbox denies; chmod is also denied (WinError 5); the child geometry worker additionally lacked the A1 repo root on PYTHONPATH and the openvsp_root task key",
                "excluded_from_endpoints": R6_EXCLUDES_R1_R2_R3_R4_R5_FROM_ENDPOINTS,
                "artifacts_preserved": True,
                "superseded_approval_sha256": R3_APPROVAL_SHA256,
            },
            "r4_reference": {
                "batch_id": "DREAL001-P2-20261111-09",
                "run_id": R4_RUN_ID,
                "status": "EXECUTOR_ARM_ABORT_MAIN_BATCH_NOT_RUN",
                "charged_starts": R4_CHARGED_STARTS,
                "charged_internal_cases": R4_CHARGED_INTERNAL_CASES,
                "main_starts": R4_MAIN_STARTS,
                "polar_byte_match": True,
                "preflight_byte_match": True,
                "root_cause": "A2 executor seeded the unit proposal engine with np.clip(physical x12) and returned unit vectors as physical x12; the A1 evaluator unit-box guard raised V12ConfigurationError UNIT_BOX_VECTOR_NOT_ACCEPTED on the first BO design before any main solver start",
                "excluded_from_endpoints": R6_EXCLUDES_R1_R2_R3_R4_R5_FROM_ENDPOINTS,
                "artifacts_preserved": True,
                "superseded_approval_sha256": R4_APPROVAL_SHA256,
            },
            "r5_reference": {
                "batch_id": "DREAL001-P2-20261111-10",
                "run_id": R5_RUN_ID,
                "status": "SETUP_STOP_DESIGN_SPACE_IMPORT",
                "charged_starts": R5_CHARGED_STARTS,
                "charged_internal_cases": R5_CHARGED_INTERNAL_CASES,
                "main_starts": R5_MAIN_STARTS,
                "physical_call_count": 0,
                "root_cause": "the executor imported design_space through the already-bound A2 research package, so the A2 copy shadowed the A1 frozen module 8f9b893c.../33660B and its P1 frozen-guard rejected the A1 frozen config; the stop occurred in executor setup before any solver start",
                "excluded_from_endpoints": R6_EXCLUDES_R1_R2_R3_R4_R5_FROM_ENDPOINTS,
                "artifacts_preserved": True,
                "superseded_approval_sha256": R5_APPROVAL_SHA256,
            },
            "r6_change": "launcher-level A1 design-space binding fix only: p2av2r6_launch.py loads the A1 frozen design_space.py by importlib from its absolute path, recomputes module SHA 8f9b893c.../33660B and config SHA 8b29d1e3.../10846B, registers it in sys.modules['research.concorde_metaopt.aircraft.design_space'] and sets the parent package attribute BEFORE importing the A2 executor; no A1 bytes, no executor bytes and no plan science fields change",
            "design_space_binding": {
                "config_rel": A1_DESIGN_SPACE_CONFIG_REL,
                "config_sha256": A1_DESIGN_SPACE_CONFIG_SHA256,
                "config_bytes": A1_DESIGN_SPACE_CONFIG_BYTES,
                "module_rel": A1_DESIGN_SPACE_PY_REL,
                "module_sha256": A1_DESIGN_SPACE_PY_SHA256,
                "module_bytes": A1_DESIGN_SPACE_PY_BYTES,
                "variable_ids": list(DESIGN_SPACE_VARIABLE_IDS),
                "unit_domain": "[0,1]^12 sealed in the proposal engine; conversion at the A2 execution boundary only",
                "a1_execution_head": "2a57632b3f7d5d567556d9774913ec40a5d72272",
            },
            "r4_change": "launcher-level env/compat shim only: launcher process sets TMP/TEMP to a workspace scratch root, prepends A1 repo root + shim dir to PYTHONPATH and replaces tempfile.mkdtemp with an ACL-safe implementation using the default os.mkdir mode; the frozen A1 geometry worker is covered by sitecustomize.py auto-imported from PYTHONPATH, which applies the same two patches plus openvsp_model.import_openvsp(None)->DEFAULT_OPENVSP_ROOT; prestart records temp_root/TMP/TEMP/PYTHONPATH/openvsp_root and shim SHAs; frozen A1 bytes, frozen executor bytes and plan scientific policy are unchanged",
            "r6_changes_retained": [
                "R5 A2 execution-layer x12 unit<->physical boundary fix retained unchanged (initial seed via A1 frozen design space to_unit_interval; ProposalEngine stays in unit space; proposal_fn returns from_unit_interval physical x12; fail-closed bounds checks)",
                "R4 launcher-level env/compat shim (TMP/TEMP=workspace scratch, ACL-safe mkdtemp using default os.mkdir mode, PYTHONPATH=A1 repo root+shim dir, sitecustomize-injected worker patches incl. openvsp_root fallback) retained unchanged",
                "A2 real spawn success status literal SOLVED -> SOLVED_VALID (R3) with the preflight verifier fail-closed",
                "R2 spawn geometry alias copy model.vspgeom/model.vkey -> <basename>.vspgeom/.vkey with SHA check",
                "R2 preflight record_internal_cases from preflight records (14) or NOT_COMPUTABLE",
                "R2 per-case physical_call_count from record_starts/ledger_delta",
            ],
            "cumulative_accounting": {
                "prior_charged_starts": PRIOR_CHARGED_STARTS,
                "prior_internal_cases": PRIOR_CHARGED_INTERNAL_CASES,
                "r1_charged_starts": R1_CHARGED_STARTS,
                "r1_internal_cases": R1_CHARGED_INTERNAL_CASES,
                "r2_charged_starts": R2_CHARGED_STARTS,
                "r2_internal_cases": R2_CHARGED_INTERNAL_CASES,
                "r3_charged_starts": R3_CHARGED_STARTS,
                "r3_internal_cases": R3_CHARGED_INTERNAL_CASES,
                "r4_charged_starts": R4_CHARGED_STARTS,
                "r4_internal_cases": R4_CHARGED_INTERNAL_CASES,
                "r5_charged_starts": R5_CHARGED_STARTS,
                "r5_internal_cases": R5_CHARGED_INTERNAL_CASES,
                "r6_planned_starts": PLANNED_STARTS,
                "r6_planned_internal_cases": PLANNED_INTERNAL_CASES,
                "cumulative_starts": R6_CUMULATIVE_STARTS,
                "cumulative_starts_cap": MAX_STARTS,
                "cumulative_internal_cases": R6_CUMULATIVE_INTERNAL_CASES,
                "cumulative_internal_cap": MAX_INTERNAL_CASES,
            },
            "unchanged": "caps/104 family pairs/initial 3 designs/seed 42/no-retry/timeout 60 s/bundle 995bb12f/A1 executable SHA/R3 SOLVED_VALID status literal/R4 launcher env shim/R5 x12 domain fix stay as the R5 package policy; only the run/window identity, the launcher-level A1 design-space preload binding and the cumulative accounting change",
        },
        "physical_call_count": 0,
        "physical_solver_starts": 0,
        "solver_started": False,
    }
    r6_addendum = dict(plan.get("r6_addendum") or {})
    r7_addendum: dict[str, Any] = {
        "status": "R7_OBSERVE_AND_INVALID_TOLERANCE_FIX",
        "r1_reference": r6_addendum.get("r1_reference"),
        "r2_reference": r6_addendum.get("r2_reference"),
        "r3_reference": r6_addendum.get("r3_reference"),
        "r4_reference": r6_addendum.get("r4_reference"),
        "r5_reference": r6_addendum.get("r5_reference"),
        "r6_reference": {
            "batch_id": "DREAL001-P2-20261111-11",
            "run_id": R6_RUN_ID,
            "superseded_approval_sha256": R6_APPROVAL_SHA256,
            "superseded_approval_bytes": R6_APPROVAL_BYTES,
            "status": "S1_STOP_MAIN_FIRST_EVALUATION",
            "charged_starts": R6_CHARGED_STARTS,
            "charged_internal_cases": R6_CHARGED_INTERNAL_CASES,
            "main_starts": R6_MAIN_STARTS,
            "preflight_result": "2/2 PASS_BYTE replay preflight (polar bytes matched approval)",
            "first_main_evaluation": {
                "design_index": 15, "design_hash": "d51866f7d3c49303",
                "status": "LIFT_MATCH_FAILED",
                "polar_sha256": "58b8438df1225b07b3ef8dc327670575d99a6866b204f2c0840de074324d489a",
            },
            "root_cause": "on_evaluation callback raised ValueError: x12 must have exactly 12 values from design_hash(canonical_x12(...)) string misuse in the frozen executor; the polar itself was produced.",
            "nan_observation": "the single main polar had 7 rows with non-finite Cl/Cd and a null objective; the mechanism is not proven (candidates H1 face/cut topology singularity, H2 frozen geometry plus numerics incompatibility, H3 family/wake initialisation).",
            "excluded_from_endpoints": True,
            "artifacts_preserved": True,
        },
        "r7_change": "A2 execution-layer and reporting remediation only: (a) observe() design_hash string misuse corrected; (b) per-evaluation invalid-numerical tolerance (INVALID_NUMERICAL recorded with raw status and polar SHA, excluded from objective statistics) with pre-registered scientific auto-stop rules, so one invalid case no longer aborts the batch; (c) DE/PSO population padding removes the latent proposal crash; (d) the arm-failure path now persists a minimal preflight_result.json and batch_summary.json; (e) a pre-registered two-case diagnostic phase (designs 16/17, 1 start / 7 internal each) runs after preflight and before the 384-start main batch. No A1 frozen bytes, no executor scientific policy and no plan scientific fields are changed. Mesh-QC data gate not adopted (Lead L-09).",
        "r7_changes_retained": [
            "R6 launcher-level A1 design_space importlib preload retained unchanged",
            "R5 x12 unit<->physical domain fix retained",
            "R4 launcher-level env/compat shim retained",
            "R3 SOLVED_VALID status vocabulary retained",
            "R2 solver geometry alias copy retained",
            "R2 preflight internal-case accounting retained",
            "R2 per-case physical_call_count retained",
        ],
        "cumulative_accounting": {
            "prior_charged_starts": PRIOR_CHARGED_STARTS,
            "prior_charged_internal_cases": PRIOR_CHARGED_INTERNAL_CASES,
            "r1_charged_starts": R1_CHARGED_STARTS,
            "r1_charged_internal_cases": R1_CHARGED_INTERNAL_CASES,
            "r2_charged_starts": R2_CHARGED_STARTS,
            "r2_charged_internal_cases": R2_CHARGED_INTERNAL_CASES,
            "r3_charged_starts": R3_CHARGED_STARTS,
            "r3_charged_internal_cases": R3_CHARGED_INTERNAL_CASES,
            "r4_charged_starts": R4_CHARGED_STARTS,
            "r4_charged_internal_cases": R4_CHARGED_INTERNAL_CASES,
            "r5_charged_starts": R5_CHARGED_STARTS,
            "r5_charged_internal_cases": R5_CHARGED_INTERNAL_CASES,
            "r6_charged_starts": R6_CHARGED_STARTS,
            "r6_charged_internal_cases": R6_CHARGED_INTERNAL_CASES,
            "r7_planned_starts": R10_PLANNED_STARTS,
            "r7_planned_internal_cases": R10_PLANNED_INTERNAL_CASES,
            "cumulative_starts": R7_CUMULATIVE_STARTS,
            "cumulative_internal_cases": R7_CUMULATIVE_INTERNAL_CASES,
            "max_starts": MAX_STARTS, "max_internal_cases": MAX_INTERNAL_CASES,
            "reserve_starts": RESERVE_STARTS,
        },
        "unchanged": r6_addendum.get("unchanged"),
        "design_space_binding": r6_addendum.get("design_space_binding"),
    }
    plan.pop("r6_addendum", None)
    plan["r7_addendum"] = r7_addendum
    plan["planned_starts"] = R10_PLANNED_STARTS
    plan["planned_internal_cases"] = R10_PLANNED_INTERNAL_CASES
    plan["diagnostic_planned_starts"] = 0
    plan["diagnostic_planned_internal_cases"] = 0
    plan["diagnostics"] = {
        "in_r10_matrix": False,
        "diagnostics_not_rerun": True,
        "r9_source": R10_DIAGNOSTIC_EVIDENCE_R9,
        "cases": [],
        "planned_starts": 0,
        "planned_internal_cases": 0,
        "pass_rule": "not applicable: R10 does not run the diagnostic phase",
        "fail_rule": "not applicable",
        "excluded_from_endpoints": True,
    }
    plan["slot_matrix_summary"] = {
        "preflight_slots": slots["preflight_slots"], "main_slots": slots["main_slots"],
        "reserve_slots": slots["reserve_slots"], "total": slots["total_projected_slots"],
    }
    r7_addendum = dict(plan.get("r7_addendum") or {})
    r10_addendum: dict[str, Any] = {
        "status": R10_AMENDMENT_ACTION,
        "r1_reference": r7_addendum.get("r1_reference"),
        "r2_reference": r7_addendum.get("r2_reference"),
        "r3_reference": r7_addendum.get("r3_reference"),
        "r4_reference": r7_addendum.get("r4_reference"),
        "r5_reference": r7_addendum.get("r5_reference"),
        "r6_reference": r7_addendum.get("r6_reference"),
        "r7_reference": {
            "batch_id": "DREAL001-P2-20261111-12",
            "run_id": R7_RUN_ID,
            "superseded_approval_sha256": R7_APPROVAL_SHA256,
            "superseded_approval_bytes": R7_APPROVAL_BYTES,
            "status": "S1_STOP_FROZEN_BYTES_SHA_MISMATCH",
            "charged_starts": R7_CHARGED_STARTS,
            "charged_internal_cases": R7_CHARGED_INTERNAL_CASES,
            "main_starts": 0,
            "preflight_result": "2/2 PASS_BYTE replay preflight (polar bytes matched approval)",
            "diagnostics_observed": "2 diagnostic designs evaluated over both families: 4 starts / 28 internal; R7 prereg had written 2 starts / 14 internal (preregistration deviation disclosed)",
            "main_failure": "design_index 15 (d51866f7d3c49303) stopped at NOT_VALIDATED / FROZEN_BYTES_SHA_MISMATCH before any solver spawn: rebuilt f2 27325306c712f1bb1a709aec52e0d6d63dfe7c6a54ef407d66940120c0e9ec14 != A1 static/manifest pre-frozen be8454bfd7db4c4637e73d9637a79391e45f4cbfd66408b956ad35d51f68a689",
            "root_cause": "A2 runtime rebuilt the initial design family pair instead of reusing the A1 pre-frozen manifest bytes; the A1 evaluator static-vs-runtime frozen_vspgeom SHA guard refused the design before spawning a solver",
            "excluded_from_endpoints": True,
            "artifacts_preserved": True,
        },
        "r8_reference": {
            "batch_id": "DREAL001-P2-20261111-13",
            "run_id": R8_RUN_ID,
            "status": "SETUP_STOP_PREFROZEN_GEOM_MISSING",
            "charged_starts": R8_CHARGED_STARTS,
            "charged_internal_cases": R8_CHARGED_INTERNAL_CASES,
            "main_starts": 0,
            "stop_report_sha256": R8_STOP_REPORT_SHA256,
            "stop_report_bytes": R8_STOP_REPORT_BYTES,
            "executor_prestart_sha256": R8_PRESTART_SHA256,
            "executor_prestart_bytes": R8_PRESTART_BYTES,
            "launcher_gate_sha256": R8_LAUNCHER_GATE_SHA256,
            "launcher_gate_bytes": R8_LAUNCHER_GATE_BYTES,
            "root_cause": "executor-side prefrozen reuse gate assumed the nested A1 family_pair_manifest row shape while the packaged initial_designs_manifest carries flat family rows (frozen_vspgeom_path and the vkey/vsp3 checks at row level); the launcher gate already accepted both shapes, so it passed and the failure surfaced only after executor start, before any solver spawn or ledger write",
            "excluded_from_endpoints": True,
            "artifacts_preserved": True,
            "superseded_approval_sha256": R8_APPROVAL_SHA256,
        },
        "r9_reference": {
            "batch_id": "DREAL001-P2-20261111-14",
            "run_id": R9_RUN_ID,
            "superseded_approval_sha256": R9_APPROVAL_SHA256,
            "superseded_approval_bytes": R9_APPROVAL_BYTES,
            "status": "STOP_DIAGNOSTICS_ACCOUNTING_INCONSISTENT",
            "charged_starts": R9_CHARGED_STARTS,
            "charged_internal_cases": R9_CHARGED_INTERNAL_CASES,
            "main_starts": R9_MAIN_STARTS,
            "preflight_result": "2/2 PASS_BYTE replay preflight (polar bytes matched approval)",
            "preflight_result_sha256": R9_PREFLIGHT_RESULT_SHA256,
            "preflight_result_bytes": 5771,
            "diagnostics_observed": "designs 16/17 evaluated over both frozen families: 4 starts, all SOLVED_VALID with finite objectives; polar bytes identical to the R7 diagnostic polars",
            "diagnostic_polar_sha256": {
                "DIAG-01": ["11ff632bb870a6c8f24454edc3251da5d9e2868646d122be561b8cc964ae9c89", "aac6e2174c934401f76ccef5c34d2e1f20e77637aaddb14c6061a4f8682ea52b"],
                "DIAG-02": ["0540341a1064bfb739efdd8b4a52e226d788efc835a483fda748d84100b848dd", "483479ad9c2f1783331b775fdd88a32da786f25311daeadb25224b2fe3fd95fe"],
            },
            "solver_attempts_sha256": R9_SOLVER_ATTEMPTS_SHA256,
            "solver_attempts_bytes": 4477,
            "stop_report_sha256": R9_STOP_REPORT_SHA256,
            "stop_report_bytes": 830,
            "executor_prestart_sha256": R9_PRESTART_SHA256,
            "executor_prestart_bytes": 12552,
            "launcher_gate_sha256": R9_LAUNCHER_GATE_SHA256,
            "launcher_gate_bytes": 37476,
            "root_cause": "the A1 evaluator records carry physical_solver_starts but no internal_solver_cases field; after the R8 removal of the silent default-7 fallback the derived internal count became 0 while the pre-registered diagnostic boundary expects 28 (=4x7), so the fail-closed boundary check stopped the batch before the main batch",
            "charged_accounting_note": "6 starts charged (2 preflight + 4 diagnostics); internal = 6 x 7 = 42 under INTERNAL_PER_START_POLICY; the recorded internal field was 0, which is the reporting defect this R10 fixes",
            "excluded_from_endpoints": True,
            "artifacts_preserved": True,
        },
        "r10_change": "A2 execution-layer and reporting fix only: (a) internal_solver_cases is now derived uniformly as INTERNAL_CASES_PER_START (7) x physical_solver_starts from the pre-registered policy constant, source tagged INTERNAL_PER_START_POLICY, for every preflight/diagnostic/main evaluation and record row; the legacy silent default of 7 and any inference from the A1 ledger are removed; (b) phase-boundary and final-summary conservation checks assert sum(internal) == 7 x starts and fail closed with ACCOUNTING_INCONSISTENT on any mismatch; (c) every evaluation/pair row records polar_sha256 when available (null otherwise, disclosed); (d) a mandatory zero-physical smoke runs the executor real main-path accounting chain (preflight and main evaluations through the P3 wiring) and proves internal=7xstarts per phase with physical=0 and solver_started=false; (e) R10 does not re-run the diagnostic phase: the plan/prereg state diagnostics-not-in-R10-matrix and cite the R9 diagnostic evidence SHAs, which remain excluded from endpoints. All R9 remediations are retained (prefrozen flat/nested reuse, observe fix, x12 domain, invalid tolerance, launcher preload/env shim, arm-failure evidence). No A1 frozen bytes, no plan scientific policy and no scientific endpoint changes.",
        "r7_changes_retained": [
            "R7 observe() design_hash string-misuse fix retained",
            "R7 invalid-numerical tolerance and pre-registered scientific auto-stop rules retained",
            "R7 DE/PSO population padding retained",
            "R7 arm-failure minimal preflight_result.json/batch_summary.json evidence retained",
            "R6 launcher-level A1 design_space importlib preload retained unchanged",
            "R5 x12 unit<->physical domain fix retained",
            "R4 launcher-level env/compat shim retained",
            "R3 SOLVED_VALID status vocabulary retained",
            "R2 solver geometry alias copy retained",
            "R2 preflight internal-case accounting retained",
            "R2 per-case physical_call_count retained",
        ],
        "r8_changes_retained": [
            "R8 prefrozen manifest reuse for initial designs 15/16/17 retained (PREFROZEN_MANIFEST_REUSE, attempts=0, fail-closed SHA/canonical checks)",
            "R8 phase-split accounting and ACCOUNTING_INCONSISTENT cap-breach guard retained; the silent default-7 removal is superseded by the R10 policy-derived 7xstarts rule",
            "R8 diagnostic 4 starts / 28 internal pre-registration retained",
            "R8 static-index hit without prefrozen reuse remains fail-closed (no silent rebuild)",
        ],
        "r9_changes_retained": [
            "R9 flat/nested family-row compatibility in runtime prefrozen reuse retained",
            "R9 executor-side prefrozen reuse gate exercised zero-physical before GO retained",
            "R9 launcher gate plus executor gate dual defence retained",
        ],
        "prefrozen_reuse": {
            "source": "A1 family_pair_manifest.json initial designs 15/16/17 (frozen_vspgeom_path plus sibling model.vkey/model.vsp3)",
            "source_kind": PREFROZEN_SOURCE_KIND,
            "reused_prefrozen": True,
            "attempts": 0,
            "static_index_count": STATIC_INDEX_COUNT_EXPECTED,
            "fail_closed": "missing/short/mutated bytes, SHA mismatch, canonical mismatch, duplicate record, or static hit without prefrozen reuse -> refused, never rebuilt silently",
            "freeze_builder_forbidden_for_initial": True,
        },
        "diagnostic_prereg_deviation": {
            "r7_prereg": "2 starts / 14 internal",
            "r7_observed": "4 starts / 28 internal (full pair evaluation per design)",
            "r8_prereg": "4 starts / 28 internal",
            "r9_prereg": "4 starts / 28 internal (observed 4 starts, internal reporting defect)",
            "r10_prereg": "diagnostics are NOT part of the R10 matrix; the R9 diagnostic evidence is cited and excluded from endpoints",
            "r10_note": "DIAG-01 design 16 eb00b7ad545243e6 and DIAG-02 design 17 dc96d2438a6dddc3 both passed feasibility under R9 within the R7 diagnostic SHAs; they are not re-run in R10",
            "reason": "full pair evaluation semantics retained; one physical start per family per design",
        },
        "cumulative_accounting": {
            "prior_charged_starts": PRIOR_CHARGED_STARTS,
            "prior_charged_internal_cases": PRIOR_CHARGED_INTERNAL_CASES,
            "r1_charged_starts": R1_CHARGED_STARTS,
            "r1_charged_internal_cases": R1_CHARGED_INTERNAL_CASES,
            "r2_charged_starts": R2_CHARGED_STARTS,
            "r2_charged_internal_cases": R2_CHARGED_INTERNAL_CASES,
            "r3_charged_starts": R3_CHARGED_STARTS,
            "r3_charged_internal_cases": R3_CHARGED_INTERNAL_CASES,
            "r4_charged_starts": R4_CHARGED_STARTS,
            "r4_charged_internal_cases": R4_CHARGED_INTERNAL_CASES,
            "r5_charged_starts": R5_CHARGED_STARTS,
            "r5_charged_internal_cases": R5_CHARGED_INTERNAL_CASES,
            "r6_charged_starts": R6_CHARGED_STARTS,
            "r6_charged_internal_cases": R6_CHARGED_INTERNAL_CASES,
            "r7_charged_starts": R7_CHARGED_STARTS,
            "r7_charged_internal_cases": R7_CHARGED_INTERNAL_CASES,
            "r8_charged_starts": R8_CHARGED_STARTS,
            "r8_charged_internal_cases": R8_CHARGED_INTERNAL_CASES,
            "r9_charged_starts": R9_CHARGED_STARTS,
            "r9_charged_internal_cases": R9_CHARGED_INTERNAL_CASES,
            "r10_planned_starts": R10_PLANNED_STARTS,
            "r10_planned_internal_cases": R10_PLANNED_INTERNAL_CASES,
            "cumulative_starts": R10_CUMULATIVE_STARTS,
            "cumulative_internal_cases": R10_CUMULATIVE_INTERNAL_CASES,
            "max_starts": MAX_STARTS, "max_internal_cases": MAX_INTERNAL_CASES,
            "reserve_starts": RESERVE_STARTS,
            "headroom_starts": MAX_STARTS - R10_CUMULATIVE_STARTS,
            "headroom_internal_cases": MAX_INTERNAL_CASES - R10_CUMULATIVE_INTERNAL_CASES,
        },
        "unchanged": r7_addendum.get("unchanged"),
        "design_space_binding": r7_addendum.get("design_space_binding"),
    }
    plan.pop("r7_addendum", None)
    plan["r10_addendum"] = r10_addendum
    plan["planned_starts"] = R10_PLANNED_STARTS
    plan["planned_internal_cases"] = R10_PLANNED_INTERNAL_CASES
    plan["diagnostic_planned_starts"] = 0
    plan["diagnostic_planned_internal_cases"] = 0
    plan["diagnostics"] = {
        "in_r10_matrix": False,
        "diagnostics_not_rerun": True,
        "r9_source": R10_DIAGNOSTIC_EVIDENCE_R9,
        "cases": [],
        "planned_starts": 0,
        "planned_internal_cases": 0,
        "pass_rule": "not applicable: R10 does not run the diagnostic phase",
        "fail_rule": "not applicable",
        "excluded_from_endpoints": True,
    }
    _formula = ("2 preflight slots (7 internal each) + 384 main slots = 386 planned starts; "
                "planned_internal_cases = 386*7 = 2702; diagnostics are NOT in the R10 matrix; "
                "signed caps max_starts=451, max_internal_cases=3157; reserve 64 starts sit outside planned")
    for _budget_key in ("budget_and_caps", "caps_reconciliation", "matrix", "slot_matrix"):
        _budget = plan.get(_budget_key)
        if isinstance(_budget, dict):
            _budget["planned_starts"] = R10_PLANNED_STARTS
            _budget["planned_internal_cases"] = R10_PLANNED_INTERNAL_CASES
            _budget["diagnostic_starts"] = 0
            _budget["diagnostic_internal_cases"] = 0
            if "main_batch_starts" in _budget or "main_planned_starts" in _budget:
                _budget["main_batch_starts"] = R10_MAIN_PLANNED_STARTS
                _budget.pop("main_planned_starts", None)
            if "formula" in _budget:
                _budget["formula"] = _formula
    plan["caps_reconciliation"]["formula"] = _formula

    return plan


def build_identity_binding(*, plan_path: Path, plan_sha256: str, prereg_path: Path,
                           initial_manifest_path: Path, preflight_bundle_path: Path,
                           a1: Mapping[str, Any], a2: Mapping[str, Any]) -> dict[str, Any]:
    files = [
        _file_binding(plan_path, "PLAN"),
        _file_binding(prereg_path, "POLICY_DOC"),
        _file_binding(initial_manifest_path, "INITIAL_DESIGNS_MANIFEST"),
        _file_binding(preflight_bundle_path, "PREFLIGHT_BUNDLE"),
    ]
    doc = {
        "schema": IDENTITY_SCHEMA,
        "created_utc": utc_now(),
        "batch_id": BATCH_ID, "run_id": RUN_ID,
        "plan": {"path": str(plan_path), "sha256": plan_sha256},
        "policy_doc": {"path": str(prereg_path), "sha256": sha256_file(prereg_path)},
        "files": files,
        "a1": dict(a1),
        "a2": dict(a2),
        "design_space_binding": {
            "config_rel": A1_DESIGN_SPACE_CONFIG_REL,
            "config_sha256": A1_DESIGN_SPACE_CONFIG_SHA256,
            "config_bytes": A1_DESIGN_SPACE_CONFIG_BYTES,
            "module_rel": A1_DESIGN_SPACE_PY_REL,
            "module_sha256": A1_DESIGN_SPACE_PY_SHA256,
            "module_bytes": A1_DESIGN_SPACE_PY_BYTES,
            "variable_ids": list(DESIGN_SPACE_VARIABLE_IDS),
        },
        "binding_chain": [
            {"item": "policy_doc", "sha256": sha256_file(prereg_path)},
            {"item": "plan", "sha256": plan_sha256},
            {"item": "initial_designs_manifest", "sha256": sha256_file(initial_manifest_path)},
            {"item": "preflight_bundle", "sha256": sha256_file(preflight_bundle_path)},
            {"item": "a1_freeze_api", "sha256": a1.get("freeze_api_sha256")},
            {"item": "a1_evaluator", "sha256": a1.get("evaluator_code_sha256")},
            {"item": "a1_builder", "sha256": a1.get("builder_code_sha256")},
            {"item": "a2_executor", "sha256": a2.get("a2_executor_sha256")},
            {"item": "a1_design_space_config", "sha256": A1_DESIGN_SPACE_CONFIG_SHA256},
            {"item": "a1_design_space_module", "sha256": A1_DESIGN_SPACE_PY_SHA256},
        ],
        "status": "ALL_BINDINGS_VERIFIED",
        "result": "ALL_BINDINGS_VERIFIED",
        "approval_state": "PENDING_LEAD_SIGNATURE",
        "a1_execution_readiness": A1_READINESS_STATUS,
        "a1_execution_readiness_note": "A1 evaluator v1.2 real path is implemented and verified by the A1 probe v3 (physical=0); no real start has occurred yet.",
        "a1_probe_v3_path": a1.get("a1_probe_v3_path"),
        "a1_probe_v3_sha256": a1.get("a1_probe_v3_sha256"),
        "a1_probe_v3_overall": a1.get("a1_probe_v3_overall"),
        "a1_probe_v3_expected_sha256": A1_PROBE_V3_SHA256,
        "a5_review_ref": "PENDING_A5_G-P2AV2R10-PRE",
        "physical_call_count": 0,
    }
    doc["identity_sha256"] = _sha256_json({k: v for k, v in doc.items() if k != "identity_sha256"})
    return doc


def _preflight_coverage_designs() -> list[dict[str, Any]]:
    """Two archival preflight designs, added to approval coverage only for REPLAY.

    A1 MODE_REPLAY resolves (design_hash, family) through
    approval.family_coverage.designs; the signed approval initially listed only
    the three initial LHS designs, so the 3-case preflight (PRE-01/PRE-02/PRE-03; PRE-03 retired in R1) failed before any
    solver start with APPROVAL_FAMILY_COVERAGE_MISSING. These two entries are
    read from the frozen P2AFAM manifest (x12 + both frozen vspgeom SHAs) and
    do not pre-list any future runtime design.
    """
    wanted = (("8bd5a6c7c8311938", 0), ("bc52a54ecefaac4c", 5))
    data = json.loads(Path(A1_PAIR_MANIFEST_PATH).read_bytes())
    by_hash = {str(r.get("design_hash")): r for r in data.get("records") or []}
    out: list[dict[str, Any]] = []
    for dh, expected_index in wanted:
        rec = by_hash.get(dh)
        if rec is None:
            raise ValueError("preflight design %s missing from P2AFAM manifest" % dh)
        fams = rec.get("families") or {}
        labels = sorted(fams, key=lambda lab: (int(lab.split("x")[0]), int(lab.split("x")[1])))
        if len(labels) != 2:
            raise ValueError("preflight design %s must have exactly two families" % dh)
        family_rows = {}
        for lab in labels:
            frozen = (fams.get(lab) or {}).get("frozen") or {}
            family_rows[lab] = {
                "frozen_vspgeom_sha256": frozen.get("frozen_vspgeom_sha256"),
                "frozen_vkey_sha256": frozen.get("frozen_vkey_sha256"),
            }
        out.append({
            "design_hash": dh,
            "design_index": int(rec.get("design_index", expected_index)),
            "group": rec.get("group"),
            "x12": rec.get("x12"),
            "roles": {"f1": labels[0], "f2": labels[1]},
            "family_labels": {"f1": labels[0], "f2": labels[1]},
            "family_label": labels,
            "families": family_rows,
            "source": "PREFLIGHT_BUNDLE_REPLAY",
            "physical_call_count": 0,
        })
    return out


def _r7_amendment_log(prior_approval_path: str) -> list[dict[str, Any]]:
    """R7: copy seq1-seq6 verbatim from the signed R6 approval, then append seq7."""
    prior = json.loads(Path(prior_approval_path).read_text(encoding="utf-8"))
    log = [dict(entry) for entry in (prior.get("amendment_log") or [])]
    cumulative_physical = (PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS + R2_CHARGED_STARTS
                           + R3_CHARGED_STARTS + R4_CHARGED_STARTS + R5_CHARGED_STARTS
                           + R6_CHARGED_STARTS)
    log.append({
        "seq": R7_AMENDMENT_SEQ,
        "action": R7_AMENDMENT_ACTION,
        "at_utc": utc_now(),
        "physical_call_count_at_amendment": cumulative_physical,
        "reason": R7_AMENDMENT_REASON,
        "supersedes_approval_path": prior_approval_path,
        "supersedes_approval_sha256": R6_APPROVAL_SHA256,
    })
    return log

def _r10_amendment_log(prior_approval_path: str) -> list[dict[str, Any]]:
    """R10: copy seq1-seq9 verbatim from the signed R9 approval, then append seq10."""
    prior = json.loads(Path(prior_approval_path).read_text(encoding="utf-8"))
    log = [dict(entry) for entry in (prior.get("amendment_log") or [])]
    cumulative_physical = (PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS + R2_CHARGED_STARTS
                           + R3_CHARGED_STARTS + R4_CHARGED_STARTS + R5_CHARGED_STARTS
                           + R6_CHARGED_STARTS + R7_CHARGED_STARTS + R8_CHARGED_STARTS
                           + R9_CHARGED_STARTS)
    log.append({
        "seq": R10_AMENDMENT_SEQ,
        "action": R10_AMENDMENT_ACTION,
        "at_utc": utc_now(),
        "physical_call_count_at_amendment": cumulative_physical,
        "reason": R10_AMENDMENT_REASON,
        "supersedes_approval_path": prior_approval_path,
        "supersedes_approval_sha256": R9_APPROVAL_SHA256,
    })
    return log


def build_approval_draft(*, plan: Mapping[str, Any], plan_sha256: str, plan_bytes: int,
                         prereg_path: Path, identity_binding: Mapping[str, Any],
                         initial_manifest: Mapping[str, Any],
                         initial_manifest_sha256: str = "",
                         identity_binding_file_sha256: str = "",
                         pkg_dir: Optional[Path] = None,
                         previous_plan_sha256: str = "") -> dict[str, Any]:
    base = Path(pkg_dir) if pkg_dir is not None else RUN_DIR
    # R10 explicitly supersedes the signed R9 approval; R1-R9 approvals are read-only history.
    prior_approval_path = str((Path(REPO_ROOT) / "research/concorde_metaopt/dreal001/runs"
                              / R9_RUN_ID / "approval.json").resolve())
    case_digest = plan["matrix"]["case_matrix_digest"]
    identity_sha = identity_binding["identity_sha256"]
    a1 = plan["runtime_binding"]["a1"]
    a2 = plan["runtime_binding"]["a2"]
    coverage_designs = []
    for design in initial_manifest["designs"]:
        labels = sorted(design["families"], key=lambda lab: (int(lab.split("x")[0]), int(lab.split("x")[1])))
        coverage_designs.append({
            "design_hash": design["design_hash"],
            "design_index": design["design_index"],
            "x12": design["x12"],
            "roles": {"f1": labels[0], "f2": labels[1]},
            "family_labels": {"f1": labels[0], "f2": labels[1]},
            "family_label": labels,
            "source": "INITIAL_LHS_PREFROZEN",
            "physical_call_count": 0,
        })
    coverage_designs.extend(_preflight_coverage_designs())
    log_path = str((base / APPEND_ONLY_LOG_PATH).resolve())
    approval = {
        "schema": APPROVAL_SCHEMA,
        "approval_version": "p2a-v2.0",
        "status": "DRAFT_AWAITING_LEAD_SIGNATURE",
        "approved": False,
        "approved_by": None,
        "approved_at_utc": None,
        "authorization": None,
        "batch_id": BATCH_ID, "canonical_batch_id": BATCH_ID, "run_id": RUN_ID,
        "run_dir": str(Path(base).resolve()), "run_dir_name": Path(base).name,
        "batch_vs_run": plan.get("batch_vs_run"),
        "created_utc": utc_now(),
        "plan_sha256": plan_sha256,
        "plan_bytes": int(plan_bytes),
        "plan_path": str(Path(plan_path_hint(plan, base))),
        "identity_binding_sha256": identity_sha,
        "identity_binding_file_sha256": identity_binding_file_sha256 or sha256_file(base / IDENTITY_FILENAME),
        "identity_binding_note": "identity_binding_sha256 is the internal canonical digest (identity_sha256 field excluded); identity_binding_file_sha256 is the SHA256 of the identity_binding.json file bytes.",
        "policy_doc_path": str(Path(prereg_path).resolve()),
        "policy_doc_sha256": sha256_file(prereg_path),
        "builder_code_path": str((Path(a1.get("a1_root", DEFAULT_A1_ROOT)) / "research/concorde_metaopt/dreal001/geometry/openvsp_model.py").resolve()),
        "pair_manifest_sha256": FROZEN_PAIR_MANIFEST_SHA256,
        "pair_manifest_path": A1_PAIR_MANIFEST_PATH,
        "pair_manifest_role": "schema and initial-design binding only; not an approval of future designs",
        "initial_designs_manifest_sha256": initial_manifest_sha256 or initial_manifest["manifest_sha256"],
        "initial_designs_manifest_path": str((Path(base) / INITIAL_MANIFEST_FILENAME).resolve()),
        "append_only_log_path": log_path,
        "append_only_log_relative": APPEND_ONLY_LOG_PATH,
        "freeze_rule": FREEZE_RULE,
        "final_run_manifest_required": True,
        "builder_code_sha256": a1.get("builder_code_sha256"),
        "builder_code_bundle_sha256": a1.get("builder_code_bundle_sha256"),
        "evaluator_code_sha256": a1.get("evaluator_code_sha256"),
        "freeze_api_sha256": a1.get("freeze_api_sha256"),
        "a2_executor_sha256": a2.get("a2_executor_sha256"),
        "executor_blob": {"a1": a1.get("files"), "a2": a2.get("files")},
        "family_coverage": {
            "mode": "RUNTIME_APPEND_ONLY",
            "policy_doc_sha256": sha256_file(prereg_path),
            "pair_manifest_sha256": FROZEN_PAIR_MANIFEST_SHA256,
            "initial_designs_manifest_sha256": initial_manifest_sha256 or initial_manifest["manifest_sha256"],
            "append_only_log_path": log_path,
            "freeze_rule": FREEZE_RULE,
            "final_run_manifest_required": True,
            "designs": coverage_designs,
            "future_designs_covered": False,
            "future_designs_note": "each runtime design is arm-blind frozen and appended at run time; approval does not pre-list them",
        },
        "execution_lifecycle": {
            "mode": "SEQUENTIAL_ONE_EVALUATOR_AT_A_TIME",
            "canonical_ledger_path": "solver_attempts.jsonl",
            "canonical_ledger_writer": "A1 TwoFamilyEvaluator only",
            "preflight_evaluator_instance_per_case": True,
            "main_evaluator_instance_per_arm": True,
            "main_evaluator_construct_scope": "inside each arm; finally close",
            "main_evaluator_max_starts": DESIGN_EVALS_PER_ARM * 2,
            "max_starts_per_evaluator_is_arm_budget_not_global": True,
            "global_max_starts_451_enforced_by": "A2 reads A1 ledger count_starts before every start",
            "one_writer_at_a_time": True,
            "ledger_delete_truncate_rebuild_forbidden": True,
            "stale_lock_policy": "fail-closed + stop_report; never silently deleted",
            "append_only_writer": "A1 freeze_api.append_chained_record",
            "append_only_reader": "A1 freeze_api.verify_chain",
            "final_run_manifest_builder": "A1 freeze_api.build_final_run_manifest",
            "final_run_manifest_required": True,
            "internal_count_policy": "ledger audits physical start/end only; internal_solver_cases is summed from evaluations/record rows, never inferred from ledger",
            "batch_summary_start_fields": ["preflight_starts", "main_starts", "total_ledger_starts", "record_internal_cases"],
            "preflight_failure_order": "close evaluator -> repair only genuinely unpaired starts -> physical recomputed from ledger -> write stop_report -> write summary",
        },
        "ledger_contract": {
            "schema": LEDGER_SCHEMA,
            "single_canonical_path": "solver_attempts.jsonl",
            "single_writer": "A1 TwoFamilyEvaluator",
            "a2_read_only": True,
            "count_starts_semantics": "count rows with event=='start'",
            "pairing_key": "case_id",
            "attempt_id": "informational only; may repeat across arm-scoped evaluators; NOT a pairing key",
            "case_id_uniqueness": "main <arm>-<design_hash>-<f1|f2>; preflight PRE-01/02",
            "internal_solver_cases_recorded_in_ledger": False,
            "internal_solver_cases_source": "evaluations/record rows only",
        },
        "stop_report_contract": {
            "path": "stop_report.json",
            "schema": "dreal001.p2a_v2.stop_report.v1",
            "physical_counts_from_ledger": True,
            "repair_only_genuinely_unpaired_starts": True,
            "repair_after_evaluator_close": True,
            "no_refund": True,
            "no_fake_end_without_start": True,
            "final_manifest_refusal_writes_stop_report": True,
            "internal_solver_cases": None,
            "internal_solver_cases_source": "evaluations/record; ledger only audits physical start/end",
            "ledger_internal_cases_recorded": "sum of end-row internal counts when present; informational only",
        },
        "preflight_bundle_sha256": plan["preflight"]["sha256"],
        "replay_bundles": plan["preflight"]["replay_bundles"],
        "preflight_bundle": {
            "path": plan["preflight"]["path"],
            "sha256": plan["preflight"]["sha256"],
            "bytes": plan["preflight"]["bytes"],
            "case_ids": plan["preflight"]["case_ids"],
            "expected_polar_sha256": plan["preflight"]["expected_polar_sha256"],
            "expected_vspgeom_sha256": plan["preflight"]["expected_vspgeom_sha256"],
            "replay_physical": True,
            "replay_physical_starts_per_case": 1,
            "replay_internal_cases_per_case": 7,
            "pass_authority": "A2_BATCH_ONLY",
            "replay_semantics_doc_sha256": "D95137D485C6A26D2CAA7CB30EA98F62DAB578B37F90AC52B4205D597BE2DB2F",
        },
        "replay_semantics_doc_sha256": "D95137D485C6A26D2CAA7CB30EA98F62DAB578B37F90AC52B4205D597BE2DB2F",
        "b2_waiver": {
            "policy": "B2_FROZEN_GEOMETRY_BYTES",
            "status": "PENDING_A5_G-P2AV2R10-PRE",
            "batch_scoped": True,
            "scope": {"batch_id": BATCH_ID, "run_id": RUN_ID},
            "per_design_frozen_assets": ["frozen .vspgeom", "frozen .vkey"],
            "forbidden_reuse": ["cross-run", "cross-batch", "P1/P1C/P1R reuse as P2a-v2 solver input"],
            "approver": "lead",
            "approved_at_utc": None,
            "a1_v1_2_code_sha256": a1.get("evaluator_code_sha256"),
            "pair_manifest_sha256": FROZEN_PAIR_MANIFEST_SHA256,
            "physical_call_count": 0,
        },
        "max_starts": MAX_STARTS,
        "planned_starts": PLANNED_STARTS,
        "planned_starts_breakdown": {
            "preflight": PREFLIGHT_PLANNED_STARTS,
            "main_batch": MAIN_PLANNED_STARTS,
            "reserve": RESERVE_STARTS,
        },
        "max_internal_cases": MAX_INTERNAL_CASES,
        "planned_internal_cases": PLANNED_INTERNAL_CASES,
        "max_refine_starts": MAX_REFINE_STARTS,
        "reserve_starts": RESERVE_STARTS,
        "reserve_groups": RESERVE_GROUPS,
        "a1_v1_2_code_sha": a1.get("a1_head"),
        "a1_executable_commit": a1.get("a1_executable_commit"),
        "a1_v1_2_evaluator_sha256": a1.get("evaluator_code_sha256"),
        "a1_v1_2_freeze_api_sha256": a1.get("freeze_api_sha256"),
        "prereg_sha256": sha256_file(prereg_path),
        "solver": {
            "backend": "REAL_VSPAERO", "parallelism": 1, "omp_threads": 1,
            "timeout_s": TIMEOUT_SECONDS, "refine_starts": 0,
            "exe_path": VSPAERO_EXE_PATH, "exe_sha256": VSPAERO_EXE_SHA256,
            "exe_bytes": VSPAERO_EXE_BYTES,
            "physical_validation_status": "NOT_VALIDATED", "fuel_burn_kg": None,
        },
        "timeouts": {"per_case_seconds": TIMEOUT_SECONDS, "batch_wall_seconds_max": 7200},
        "limits": {
            "max_geometry_builds": MAX_GEOMETRY_BUILDS,
            "max_geometry_builds_per_design": MAX_GEOMETRY_BUILDS_PER_DESIGN,
            "zero_physical_wall_cap_seconds": ZERO_PHYSICAL_WALL_CAP_SECONDS,
        },
        "case_matrix_digest": case_digest,
        "digest_scope": plan["matrix"]["case_matrix_digest_scope"],
        "full_canonical_plan_sha256": plan_sha256,
        "stop_conditions": plan["stop_conditions"],
        "endpoint_policy": plan["endpoint_policy"],
        "statistics_policy": plan["statistics_policy"],
        "window": {
            "start_utc": WINDOW_START_UTC, "end_utc": WINDOW_END_UTC,
            "token": WINDOW_TOKEN, "status": "REQUESTED_NOT_SIGNED",
        },
        "token": WINDOW_TOKEN,
        "conditions": [
            "A5 Q2=A sequential runtime freeze; approval binds policy+code+initial seeds only, not future designs.",
            "Before any solver start for a design: A1 FreezeAPI arm-blind K=10 discovery + <=40 builds per target family -> two families frozen -> PRE SHA -> append-only record -> then start.",
            "A1 evaluator MODE_RUNTIME must verify the design record exists and both family SHAs match; otherwise 0 start.",
            "One freeze per design shared by all six arms; no recompute, no family picking, no overwrite.",
            "Any unreachable family -> entire design VOID for every arm; no single-arm discard and no single-family primary.",
            "End of run: final pair manifest + complete append-only log for A5 review.",
            "Initial three LHS designs are zero-physical pre-frozen and exactly listed in the initial manifest.",
            "If A1 cannot satisfy the runtime checks, fall back to B (split windows); A2 must not re-implement freeze.",
            "The single canonical solver_attempts.jsonl writer is the A1 TwoFamilyEvaluator (event=start/end rows); A1 solver_ledger.SolverLedger is not invoked; A2 only reads/pairs by case_id and never writes a second schema.",
            "No retry: any non-SOLVED result -> S2 stop; timeout is a charged start, no retry.",
            "Single seed=42 descriptive only; no winner; no optimizer PASS; cross-family numeric comparison forbidden.",
            "A1 evaluator v1.2 real path is implemented and verified by the A1 probe v3 (10/10 SECURE, physical=0); no real start has occurred yet, first real start requires this signed approval.",
            "Physical validation remains NOT_VALIDATED; fuel_burn_kg is null.",
            "R6 addendum: R1/R2/R3/R4 each charged 2 preflight starts / 14 internal cases with mains NOT_RUN; R5 stopped in executor setup before any solver start (0 starts / 0 internal); all five are excluded from E1-E6 endpoints and from this stage evidence; cumulative caps are 433 starts / 3,043 internal cases (451/3,157 bounds).",
            "R6 change is limited to a launcher-level importlib preload that binds the A1 frozen design_space.py SHA 8f9b893c.../33660B and config SHA 8b29d1e3.../10846B before the executor import (sys.modules registration + parent package setattr); no A1/executor/plan-science bytes change; window is 2026-11-11T11:00:00Z-15:00:00Z with token WINDOW_OK-P2AV2R6-20261111T1100Z-1500Z.",
        ],
        "approval_refs": {
            "a5_review": "PENDING_A5_G-P2AV2R10-PRE",
            "a1_execution_code": "6979802",
            "a1_execution_code_note": "A1 docs/planning + receipt commit for task-49; executable geometry code is a1_v1_2_code_sha",
            "a1_head": a1.get("a1_head"),
            "a1_bundle_commit": "0598441",
            "a1_bundle_commit_full": "059844140aad0051509cd0dde3b50e373becc85b",
            "a1_bundle_manifest_sha256": "20999b3e23fdf3b50714f84844e1633faa090d7e2df40b372f2c82566df7af46",
            "a2_execution_code": a2.get("a2_executor_sha256"),
        },
        "supersedes": {
            "approval_path": prior_approval_path,
            "approval_sha256": R5_APPROVAL_SHA256,
            "approval_bytes": R5_APPROVAL_BYTES,
            "run_id": R5_RUN_ID,
            "physical_call_count_at_supersede": R1_CHARGED_STARTS + R2_CHARGED_STARTS + R3_CHARGED_STARTS + R4_CHARGED_STARTS + R5_CHARGED_STARTS,
            "superseded_at_utc": utc_now(),
            "reason": R6_AMENDMENT_REASON,
        },
        "amendment_log": [
            {
                "seq": 1,
                "action": "PREFLIGHT_CONTRACT_FIX_R1",
                "at_utc": "2026-11-11T04:39:37Z",
                "physical_call_count_at_amendment": 0,
                "reason": "P2a v2 R1 preflight contract fix (vspaero exe binding, PRE-03 retirement, per-case starts); no real solver starts occurred.",
                "supersedes_approval_path": str((Path(REPO_ROOT) / "research/concorde_metaopt/dreal001/runs" / R1_RUN_ID / "approval.json").resolve()),
                "supersedes_approval_sha256": "064076e4ed5d5974502e98a5256e267369cbc3590375193608aefd064bf96cc6",
            },
            {
                "seq": R2_AMENDMENT_SEQ,
                "action": R2_AMENDMENT_ACTION,
                "at_utc": R2_AMENDMENT_AT_UTC,
                "physical_call_count_at_amendment": R1_CHARGED_STARTS,
                "reason": R2_AMENDMENT_REASON,
                "supersedes_approval_path": str((Path(REPO_ROOT) / "research/concorde_metaopt/dreal001/runs" / R1_RUN_ID / "approval.json").resolve()),
                "supersedes_approval_sha256": R1_APPROVAL_SHA256,
            },
            {
                "seq": R3_AMENDMENT_SEQ,
                "action": R3_AMENDMENT_ACTION,
                "at_utc": R3_AMENDMENT_AT_UTC,
                "physical_call_count_at_amendment": R1_CHARGED_STARTS + R2_CHARGED_STARTS,
                "reason": R3_AMENDMENT_REASON,
                "supersedes_approval_path": str((Path(REPO_ROOT) / "research/concorde_metaopt/dreal001/runs" / R2_RUN_ID / "approval.json").resolve()),
                "supersedes_approval_sha256": R2_APPROVAL_SHA256,
            },
            {
                "seq": R4_AMENDMENT_SEQ,
                "action": R4_AMENDMENT_ACTION,
                "at_utc": R4_AMENDMENT_AT_UTC,
                "physical_call_count_at_amendment": R1_CHARGED_STARTS + R2_CHARGED_STARTS + R3_CHARGED_STARTS,
                "reason": R4_AMENDMENT_REASON,
                "supersedes_approval_path": str((Path(REPO_ROOT) / "research/concorde_metaopt/dreal001/runs" / R3_RUN_ID / "approval.json").resolve()),
                "supersedes_approval_sha256": R3_APPROVAL_SHA256,
            },
            {
                "seq": R5_AMENDMENT_SEQ,
                "action": R5_AMENDMENT_ACTION,
                "at_utc": R5_AMENDMENT_AT_UTC,
                "physical_call_count_at_amendment": R1_CHARGED_STARTS + R2_CHARGED_STARTS + R3_CHARGED_STARTS + R4_CHARGED_STARTS,
                "reason": R5_AMENDMENT_REASON,
                "supersedes_approval_path": str((Path(REPO_ROOT) / "research/concorde_metaopt/dreal001/runs" / R4_RUN_ID / "approval.json").resolve()),
                "supersedes_approval_sha256": R4_APPROVAL_SHA256,
            },
            {
                "seq": R6_AMENDMENT_SEQ,
                "action": R6_AMENDMENT_ACTION,
                "at_utc": utc_now(),
                "physical_call_count_at_amendment": R1_CHARGED_STARTS + R2_CHARGED_STARTS + R3_CHARGED_STARTS + R4_CHARGED_STARTS + R5_CHARGED_STARTS,
                "reason": R6_AMENDMENT_REASON,
                "supersedes_approval_path": prior_approval_path,
                "supersedes_approval_sha256": R5_APPROVAL_SHA256,
            },
        ],
        "r6_addendum": dict(plan.get("r6_addendum") or {}),
        "physical_call_count": 0,
        "physical_solver_starts": 0,
        "solver_started": False,
    }
    approval["planned_starts"] = R10_PLANNED_STARTS
    approval["planned_internal_cases"] = R10_PLANNED_INTERNAL_CASES
    approval["diagnostic_planned_starts"] = 0
    approval["diagnostic_planned_internal_cases"] = 0
    approval["planned_starts_breakdown"] = {
        "preflight_starts": PREFLIGHT_PLANNED_STARTS,
        "preflight_internal_cases": PREFLIGHT_PLANNED_INTERNAL_CASES,
        "diagnostic_starts": 0,
        "diagnostic_internal_cases": 0,
        "main_batch_starts": R10_MAIN_PLANNED_STARTS,
        "main_batch_internal_cases": PLANNED_INTERNAL_CASES,
        "reserve_starts": RESERVE_STARTS,
        "total_starts": R10_PLANNED_STARTS,
        "total_internal_cases": R10_PLANNED_INTERNAL_CASES,
    }
    approval["supersedes"] = {
        "approval_path": prior_approval_path,
        "sha256": R6_APPROVAL_SHA256,
        "bytes": R6_APPROVAL_BYTES,
        "run_id": R6_RUN_ID,
        "physical_call_count_at_supersede": (PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS
                                             + R2_CHARGED_STARTS + R3_CHARGED_STARTS
                                             + R4_CHARGED_STARTS + R5_CHARGED_STARTS
                                             + R6_CHARGED_STARTS),
        "superseded_at_utc": utc_now(),
        "reason": R7_AMENDMENT_REASON,
    }
    approval["amendment_log"] = _r7_amendment_log(prior_approval_path)
    approval.pop("r6_addendum", None)
    approval["r7_addendum"] = dict(plan.get("r7_addendum") or {})
    approval["diagnostics"] = dict(plan.get("diagnostics") or {})
    approval["conditions"] = [
        "R7 supersedes the signed R6 approval; R1-R6 approvals and run directories are read-only history and are excluded from E1-E6 endpoints.",
        "Window is 2026-11-11T14:00:00Z through 2026-11-12T04:00:00Z; token WINDOW_OK-P2AV2R7-20261111T1400Z-20261112T0400Z.",
        "Planned budget 388 starts / 2,716 internal cases (2 preflight + 2 diagnostic + 384 main) within caps 451 / 3,157; reserve 64; refine 0.",
        "Cumulative accounting after R7 is 438 starts / 3,078 internal cases; prior 50 / 362 include R1-R6 charged starts.",
        "No A1 frozen bytes change: bundle 995bb12f, evaluator f74a4752, freeze_api 31d78182, openvsp_model c40b11df, design_space py 8f9b893c / config 8b29d1e3.",
        "A2 executor bytes change only in the execution/reporting layer (observe design_hash, invalid tolerance, DE/PSO population padding, diagnostic phase, arm-failure evidence).",
        "Preflight remains 2 replay cases; only PASS_BYTE is accepted unless Lead and A5 accept PASS_NUMERIC in writing.",
        "After preflight, two diagnostic real starts (designs 16 and 17, 1 start / 7 internal each) must run before the main batch; if both fail the main batch is NOT_RUN.",
        "Main batch is 384 starts / 2,702 internal cases, six arms, 32 designs per arm, two families per design.",
        "Serial execution: one process at a time, OMP_NUM_THREADS=1, timeout 60 s, no retry of failed evaluations.",
        "Individual invalid-numerical evaluations are recorded and do not abort the batch; pre-registered auto-stop rules apply (>=48 evaluations and >25% invalid, >=6 consecutive, >64 total).",
        "Any non-diagnostic execution-layer error, ledger gap, accounting inconsistency, hardware fault or protocol deviation stops the batch immediately and writes a stop_report.",
        "Window hard stop is 2026-11-12T04:00:00Z; clean-stop checkpoint is 2026-11-12T02:30:00Z; the batch must not start after 2026-11-11T19:00:00Z.",
        "No winner, significance or cross-family comparison is claimed; fuel_burn_kg is null and physical validation is NOT_VALIDATED.",
        "Mesh quality metrics are observations only; no mesh-QC data gate is adopted in R7 (Lead L-09).",
    ]
    approval["approval_refs"]["a5_review"] = "PENDING_A5_G-P2AV2R10-PRE"
    approval["planned_starts"] = R10_PLANNED_STARTS
    approval["planned_internal_cases"] = R10_PLANNED_INTERNAL_CASES
    approval["diagnostic_planned_starts"] = 0
    approval["diagnostic_planned_internal_cases"] = 0
    approval["planned_starts_breakdown"] = {
        "preflight_starts": PREFLIGHT_PLANNED_STARTS,
        "preflight_internal_cases": PREFLIGHT_PLANNED_INTERNAL_CASES,
        "diagnostic_starts": 0,
        "diagnostic_internal_cases": 0,
        "main_batch_starts": R10_MAIN_PLANNED_STARTS,
        "main_batch_internal_cases": PLANNED_INTERNAL_CASES,
        "reserve_starts": RESERVE_STARTS,
        "total_starts": R10_PLANNED_STARTS,
        "total_internal_cases": R10_PLANNED_INTERNAL_CASES,
    }
    approval["supersedes"] = {
        "approval_path": prior_approval_path,
        "sha256": R9_APPROVAL_SHA256,
        "bytes": R9_APPROVAL_BYTES,
        "run_id": R9_RUN_ID,
        "physical_call_count_at_supersede": (PRIOR_CHARGED_STARTS + R1_CHARGED_STARTS
                                             + R2_CHARGED_STARTS + R3_CHARGED_STARTS
                                             + R4_CHARGED_STARTS + R5_CHARGED_STARTS
                                             + R6_CHARGED_STARTS + R7_CHARGED_STARTS
                                             + R8_CHARGED_STARTS + R9_CHARGED_STARTS),
        "superseded_at_utc": utc_now(),
        "reason": R10_AMENDMENT_REASON,
    }
    approval["amendment_log"] = _r10_amendment_log(prior_approval_path)
    approval.pop("r7_addendum", None)
    approval.pop("r6_addendum", None)
    approval["r10_addendum"] = dict(plan.get("r10_addendum") or {})
    approval["diagnostics"] = dict(plan.get("diagnostics") or {})
    approval["conditions"] = [
        "R10 supersedes the signed R9 approval; R1-R9 approvals and run directories are read-only history and are excluded from E1-E6 endpoints. R9 charged 6 real starts / 42 real internal cases (recorded 0 was a reporting defect) and its main batch stayed NOT_RUN.",
        "Window is 2026-11-11T18:30:00Z through 2026-11-12T04:00:00Z; token WINDOW_OK-P2AV2R10-20261111T1830Z-20261112T0400Z; launch deadline 2026-11-11T21:00:00Z, clean-stop checkpoint 2026-11-12T02:30:00Z, hard stop 2026-11-12T04:00:00Z.",
        "Planned budget 386 starts / 2,702 internal cases (2 preflight + 384 main; the diagnostic phase is NOT in the R10 matrix) within caps 451 / 3,157; reserve 64; refine 0.",
        "Cumulative accounting after R10 is 448 starts / 3,148 internal cases (prior 62 / 446 include R1-R9 charged counts); headroom 3 starts / 9 internal cases.",
        "No A1 frozen bytes change: bundle 995bb12f, evaluator f74a4752, freeze_api 31d78182, openvsp_model c40b11df, design_space py 8f9b893c / config 8b29d1e3.",
        "A2 executor bytes change only in the execution/reporting accounting layer (internal derivation from the pre-registered policy constant, conservation checks, polar SHA capture); no plan science fields change.",
        "internal_solver_cases is always derived from the pre-registered INTERNAL_PER_START_POLICY constant: internal = 7 x physical_solver_starts, so starts==0 implies internal=0. It is never inferred from the A1 ledger and never silently defaulted. Per-phase and final conservation checks sum(internal) == 7 x starts fail closed as ACCOUNTING_INCONSISTENT.",
        "Evaluation rows, diagnostic rows and the batch_summary record polar_sha256 when available; null is recorded with a disclosure when the record shape cannot expose it.",
        "Initial designs 15/16/17 must reuse the pre-frozen manifest family bytes (frozen_vspgeom_path plus sibling model.vkey/model.vsp3); the three file SHAs and the A1 describe_mesh canonical SHA are verified fail-closed and FreezeBuilder is forbidden for these designs. Family rows may be flat or nested (R9).",
        "Non-initial designs keep the FreezeBuilder path; a static-index hit without prefrozen reuse is recorded unusable (no silent rebuild). static_index_count=119 is recorded in the zero-physical gate.",
        "The preflight 2 replay cases remain PASS_BYTE only unless Lead and A5 accept PASS_NUMERIC in writing.",
        "Main batch is 384 starts / 2,702 internal cases, six arms, 32 designs per arm, two families per design; serial execution with one process at a time, OMP_NUM_THREADS=1, timeout 60 s, no retry of failed evaluations.",
        "Individual invalid-numerical evaluations are recorded and do not abort the batch; pre-registered auto-stop rules apply (>=48 evaluations and >25% invalid, >=6 consecutive, >64 total).",
        "Any execution-layer error, ledger gap, accounting conservation failure, hardware fault or protocol deviation stops the batch immediately and writes a stop_report.",
        "No winner, significance or cross-family comparison is claimed; fuel_burn_kg is null and physical validation is NOT_VALIDATED. R10 is the final attempt and there is no R11.",
    ]
    approval["approval_refs"]["a5_review"] = "PENDING_A5_G-P2AV2R10-PRE"

    return approval


def plan_path_hint(plan: Mapping[str, Any], base: Path) -> Path:
    return Path(base) / PLAN_FILENAME


def _check(checks: list[dict[str, Any]], check_id: str, ok: bool, expected: Any, actual: Any,
           detail: str = "", *, nv: bool = False) -> None:
    status = "NV" if (nv and ok) else ("PASS" if ok else "FAIL")
    checks.append({
        "check_id": check_id, "status": status,
        "expected": expected, "actual": actual, "detail": detail,
    })


def run_dry_run(*, plan_path: Path, approval_path: Path, prereg_path: Path,
                initial_manifest_path: Path, identity_path: Path,
                a1_root: Optional[Path] = None, out_path: Optional[Path] = None,
                now_utc: Optional[str] = None) -> dict[str, Any]:
    root = Path(a1_root) if a1_root is not None else DEFAULT_A1_ROOT
    now_utc = now_utc or utc_now()
    plan_bytes = Path(plan_path).read_bytes()
    plan = json.loads(plan_bytes)
    approval = _read_json(approval_path)
    identity = _read_json(identity_path)
    checks: list[dict[str, Any]] = []
    plan_sha = sha256_bytes(plan_bytes)
    approval_sha = sha256_file(approval_path)
    _check(checks, "C01_plan_sha", approval.get("plan_sha256") == plan_sha,
           plan_sha, approval.get("plan_sha256"), "approval binds exact plan bytes")
    _check(checks, "C02_plan_bytes", int(approval.get("plan_bytes", -1)) == len(plan_bytes),
           len(plan_bytes), approval.get("plan_bytes"))
    _check(checks, "C03_prereg_sha", sha256_file(prereg_path) == approval.get("policy_doc_sha256"),
           sha256_file(prereg_path), approval.get("policy_doc_sha256"))
    _check(checks, "C04_initial_manifest_sha",
           sha256_file(initial_manifest_path) == approval.get("initial_designs_manifest_sha256"),
           sha256_file(initial_manifest_path), approval.get("initial_designs_manifest_sha256"))
    _check(checks, "C05_identity_sha", identity.get("identity_sha256") == approval.get("identity_binding_sha256"),
           identity.get("identity_sha256"), approval.get("identity_binding_sha256"))
    _check(checks, "C06_pair_manifest_sha", sha256_file(Path(A1_PAIR_MANIFEST_PATH)) == FROZEN_PAIR_MANIFEST_SHA256,
           FROZEN_PAIR_MANIFEST_SHA256, sha256_file(Path(A1_PAIR_MANIFEST_PATH)))
    a1 = dict(plan.get("runtime_binding", {}).get("a1") or {})
    _check(checks, "C07_a1_freeze_api_sha", sha256_file(root / FREEZE_API_REL) == a1.get("freeze_api_sha256"),
           a1.get("freeze_api_sha256"), sha256_file(root / FREEZE_API_REL))
    _check(checks, "C08_a1_evaluator_sha", sha256_file(root / EVALUATOR_REL) == a1.get("evaluator_code_sha256"),
           a1.get("evaluator_code_sha256"), sha256_file(root / EVALUATOR_REL))
    a2 = dict(plan.get("runtime_binding", {}).get("a2") or {})
    for f in a2.get("files") or []:
        _check(checks, "C09_a2_file_%s" % Path(f.get("path", "file")).stem,
               sha256_file(Path(f.get("path"))) == f.get("sha256"),
               f.get("sha256"), sha256_file(Path(f.get("path"))))
    _check(checks, "C10_executor_sha", a2.get("a2_executor_sha256") == _sha256_json(
        [{f.get("path"): f.get("sha256") for f in a2.get("files") or []}]),
        a2.get("a2_executor_sha256"), "recomputed")
    pf = plan.get("preflight") or {}
    _check(checks, "C11_preflight_cases", len(pf.get("case_ids") or []) == PREFLIGHT_CASES,
           PREFLIGHT_CASES, len(pf.get("case_ids") or []))
    _check(checks, "C12_append_log_path",
           (plan.get("family_policy") or {}).get("append_only_log_path") == APPEND_ONLY_LOG_PATH,
           APPEND_ONLY_LOG_PATH, (plan.get("family_policy") or {}).get("append_only_log_path"))
    _check(checks, "C13_freeze_rule", (plan.get("family_policy") or {}).get("freeze_rule") == FREEZE_RULE,
           FREEZE_RULE, (plan.get("family_policy") or {}).get("freeze_rule"))
    _check(checks, "C14_final_manifest",
           (plan.get("family_policy") or {}).get("final_run_manifest_required") is True, True,
           (plan.get("family_policy") or {}).get("final_run_manifest_required"))
    _check(checks, "C15_budget", (
        int(approval.get("max_starts", -1)) == MAX_STARTS
        and int(approval.get("planned_starts", -1)) == R10_PLANNED_STARTS
        and int(approval.get("max_internal_cases", -1)) == MAX_INTERNAL_CASES
        and int(approval.get("max_refine_starts", -1)) == MAX_REFINE_STARTS
        and int(approval.get("reserve_starts", -1)) == RESERVE_STARTS),
        {"max_starts": MAX_STARTS, "planned_starts": R10_PLANNED_STARTS,
         "max_internal_cases": MAX_INTERNAL_CASES, "reserve_starts": RESERVE_STARTS,
         "refine": MAX_REFINE_STARTS},
        {"max_starts": approval.get("max_starts"), "planned_starts": approval.get("planned_starts"),
         "max_internal_cases": approval.get("max_internal_cases"),
         "reserve_starts": approval.get("reserve_starts"), "refine": approval.get("max_refine_starts")})
    window = approval.get("window") or {}
    window_open = str(window.get("start_utc", "")) <= now_utc <= str(window.get("end_utc", ""))
    _check(checks, "C16_window_requested", bool(window.get("token")), WINDOW_TOKEN, window.get("token"),
           "requested window; signature/authorization is separate", nv=True)
    _check(checks, "C17_approval_state", approval.get("status") in ("DRAFT_AWAITING_LEAD_SIGNATURE", "APPROVED_SIGNED"),
           "DRAFT_AWAITING_LEAD_SIGNATURE or APPROVED_SIGNED", approval.get("status"),
           "DRAFT is not an authorization; it never passes the launch gate")
    artifact_dir = Path(plan_path).parent
    bad = [name for name in ("cases", "solver_attempts.jsonl", "evaluations.jsonl", "batch_summary.json")
           if (artifact_dir / name).exists()]
    _check(checks, "C18_no_execution_artifacts", not bad, [], bad, "zero-physical package")
    _check(checks, "C19_a1_runtime_constructor", approval.get("approved") is not True, "real path deferred until approval",
           "SKIPPED_NOT_APPROVED", "no solver and no A1 evaluator construction before a signed approval", nv=True)
    doc = {
        "schema": "dreal001.p2a_v2.dry_run.v1",
        "created_utc": now_utc,
        "status": "DRY_RUN_BLOCKED_NOT_APPROVED" if approval.get("approved") is not True else "DRY_RUN_EXECUTED_NOT_AUTHORIZED_TO_LAUNCH",
        "blocked": approval.get("approved") is not True,
        "executable": False,
        "plan_path": str(plan_path),
        "plan_sha256": plan_sha,
        "approval_path": str(approval_path),
        "approval_sha256": approval_sha,
        "approval_status": approval.get("status"),
        "approved": bool(approval.get("approved")),
        "batch_id": plan.get("batch_id"), "run_id": plan.get("run_id"),
        "prereg_sha256": sha256_file(prereg_path),
        "initial_designs_manifest_sha256": sha256_file(initial_manifest_path),
        "identity_binding_sha256": identity.get("identity_sha256"),
        "a2_executor_sha256": (plan.get("runtime_binding", {}).get("a2") or {}).get("a2_executor_sha256"),
        "executor_blob": {"a1": (plan.get("runtime_binding", {}).get("a1") or {}).get("files"),
                          "a2": (plan.get("runtime_binding", {}).get("a2") or {}).get("files")},
        "window": dict(window, open_at_dry_run=window_open),
        "planned_starts": R10_PLANNED_STARTS, "max_starts": MAX_STARTS,
        "planned_internal_cases": R10_PLANNED_INTERNAL_CASES, "max_internal_cases": MAX_INTERNAL_CASES,
        "preflight_cases": PREFLIGHT_CASES, "main_planned_starts": R10_MAIN_PLANNED_STARTS,
        "diagnostic_cases": [],
        "diagnostic_planned_starts": 0,
        "diagnostic_planned_internal_cases": 0,
        "diagnostics_in_matrix": False,
        "internal_cases_per_start": INTERNAL_CASES_PER_START,
        "internal_cases_per_start_source": INTERNAL_CASES_PER_START_SOURCE,
        "reserve_starts": RESERVE_STARTS, "max_refine_starts": MAX_REFINE_STARTS,
        "cases_planned": 0, "cases_emitted": 0, "ledger_created": False,
        "solver_processes": 0, "physical_solver_starts": 0, "physical_call_count": 0,
        "a1_probe": {"attempted": False, "error": None,
                     "skipped_reason": "approval not signed; launch-gate dry-run deferred"},
        "checks": checks,
        "note": "dry-run never launches a solver; it validates artifacts and, after a real approval, constructs the A1 evaluator in mock RUNTIME mode without a spawn callable",
        "dry_run_path": str(out_path or (Path(plan_path).parent / DRY_RUN_FILENAME)),
    }
    return doc


def write_sha256sums(out_dir: Path, names: Sequence[str]) -> str:
    out = Path(out_dir)
    lines = ["%s  %s" % (sha256_file(out / name), name) for name in names if (out / name).is_file()]
    path = out / "SHA256SUMS.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sha256_file(path)


def build_package(*, out_dir: Optional[Path] = None, a1_root: Optional[Path] = None,
                  prereg_path: Optional[Path] = None,
                  preflight_bundle: Optional[Path] = None,
                  previous_plan_sha256: str = "") -> dict[str, Any]:
    root = Path(a1_root) if a1_root is not None else DEFAULT_A1_ROOT
    out = Path(out_dir) if out_dir is not None else RUN_DIR
    out.mkdir(parents=True, exist_ok=True)
    a1 = a1_binding(root)
    a2 = a2_code_binding()
    initial = build_initial_designs_manifest()
    initial_path = out / INITIAL_MANIFEST_FILENAME
    _write_json(initial_path, initial)
    prereg = Path(prereg_path) if prereg_path is not None else out / PREREG_FILENAME
    if prereg_path is None or not prereg.is_file():
        prereg.write_text(preregistration_text(a1=a1, a2=a2), encoding="utf-8")
    prereg_sha = sha256_file(prereg)
    plan = build_plan(prereg_sha256=prereg_sha, prereg_path=prereg,
                      initial_manifest=initial, initial_manifest_sha256=sha256_file(initial_path),
                      a1=a1, a2=a2)
    plan_path = out / PLAN_FILENAME
    _write_json(plan_path, plan)
    plan_bytes = plan_path.read_bytes()
    plan_sha = sha256_bytes(plan_bytes)
    bundle = Path(preflight_bundle) if preflight_bundle is not None else Path(A1_PREFLIGHT_BUNDLE_PATH)
    identity = build_identity_binding(plan_path=plan_path, plan_sha256=plan_sha,
                                      prereg_path=prereg, initial_manifest_path=initial_path,
                                      preflight_bundle_path=bundle, a1=a1, a2=a2)
    identity_path = out / IDENTITY_FILENAME
    _write_json(identity_path, identity)
    approval = build_approval_draft(plan=plan, plan_sha256=plan_sha, plan_bytes=len(plan_bytes),
                                    prereg_path=prereg, identity_binding=identity,
                                    initial_manifest=initial,
                                    initial_manifest_sha256=sha256_file(initial_path),
                                    identity_binding_file_sha256=sha256_file(identity_path),
                                    pkg_dir=out, previous_plan_sha256=previous_plan_sha256)
    approval_path = out / APPROVAL_FILENAME
    _write_json(approval_path, approval)
    dry = run_dry_run(plan_path=plan_path, approval_path=approval_path, prereg_path=prereg,
                      initial_manifest_path=initial_path, identity_path=identity_path,
                      a1_root=root, out_path=out / DRY_RUN_FILENAME)
    _write_json(out / DRY_RUN_FILENAME, dry)
    executor_dry_path = out / EXECUTOR_DRY_RUN_FILENAME
    try:
        from .p2a_v2_executor import run_dry_run as run_executor_dry_run
        executor_dry = run_executor_dry_run(out, root)
        _write_json(executor_dry_path, executor_dry)
    except Exception as exc:  # noqa: BLE001 - pre-approval evidence, never a physical path
        _write_json(executor_dry_path, {
            "schema": "dreal001.p2a_v2.executor_dry_run.v1",
            "status": "EXECUTOR_DRY_RUN_UNAVAILABLE", "blocked": True,
            "error": "%s: %s" % (type(exc).__name__, exc), "physical_call_count": 0,
        })
    sums_sha = write_sha256sums(out, (PLAN_FILENAME, APPROVAL_FILENAME, IDENTITY_FILENAME,
                                      INITIAL_MANIFEST_FILENAME, PREREG_FILENAME, DRY_RUN_FILENAME,
                                      EXECUTOR_DRY_RUN_FILENAME))
    return {
        "run_dir": str(Path(out).resolve()),
        "plan_path": str(plan_path), "plan_sha256": plan_sha, "plan_bytes": len(plan_bytes),
        "approval_path": str(approval_path), "approval_sha256": sha256_file(approval_path),
        "identity_path": str(identity_path), "identity_sha256": identity.get("identity_sha256"),
        "initial_manifest_path": str(Path(initial_path).resolve()), "initial_manifest_sha256": sha256_file(initial_path),
        "prereg_path": str(prereg), "prereg_sha256": prereg_sha,
        "dry_run_path": str(out / DRY_RUN_FILENAME), "dry_run_sha256": sha256_file(out / DRY_RUN_FILENAME),
        "sha256sums_sha256": sums_sha,
        "planned_starts": R10_PLANNED_STARTS, "max_starts": MAX_STARTS,
        "planned_internal_cases": R10_PLANNED_INTERNAL_CASES,
        "physical_call_count": 0, "physical_solver_starts": 0,
    }


def verify_package(out_dir: Optional[Path] = None) -> dict[str, Any]:
    out = Path(out_dir) if out_dir is not None else RUN_DIR
    checks: list[dict[str, Any]] = []
    plan_path = out / PLAN_FILENAME
    approval_path = out / APPROVAL_FILENAME
    identity_path = out / IDENTITY_FILENAME
    initial_path = out / INITIAL_MANIFEST_FILENAME
    dry_path = out / DRY_RUN_FILENAME
    for name, p in (("V00_plan", plan_path), ("V00_approval", approval_path),
                    ("V00_identity", identity_path), ("V00_initial", initial_path),
                    ("V00_dry_run", dry_path), ("V00_sums", out / "SHA256SUMS.txt")):
        _check(checks, name, p.is_file(), str(p), str(p))
    plan = _read_json(plan_path)
    approval = _read_json(approval_path)
    identity = _read_json(identity_path)
    dry = _read_json(dry_path)
    plan_sha = sha256_file(plan_path)
    _check(checks, "V01_plan_schema", plan.get("schema") == PLAN_SCHEMA, PLAN_SCHEMA, plan.get("schema"))
    _check(checks, "V02_ids", plan.get("batch_id") == BATCH_ID and plan.get("run_id") == RUN_ID
           and Path(out).name == plan.get("run_id") == RUN_ID,
           {"batch_id": BATCH_ID, "run_id": RUN_ID, "dir": RUN_ID},
           {"batch_id": plan.get("batch_id"), "run_id": plan.get("run_id"), "dir": Path(out).name})
    _check(checks, "V03_approval_plan_sha", approval.get("plan_sha256") == plan_sha,
           plan_sha, approval.get("plan_sha256"))
    _check(checks, "V04_approval_draft", approval.get("approved") is False
           and approval.get("status") == "DRAFT_AWAITING_LEAD_SIGNATURE",
           "approved=false status=DRAFT_AWAITING_LEAD_SIGNATURE",
           {"approved": approval.get("approved"), "status": approval.get("status")})
    _check(checks, "V05_initial_sha", approval.get("initial_designs_manifest_sha256") == sha256_file(initial_path),
           sha256_file(initial_path), approval.get("initial_designs_manifest_sha256"))
    _check(checks, "V06_identity_sha", identity.get("identity_sha256") == approval.get("identity_binding_sha256"),
           identity.get("identity_sha256"), approval.get("identity_binding_sha256"))
    _check(checks, "V06b_identity_file_sha", approval.get("identity_binding_file_sha256") == sha256_file(identity_path),
           sha256_file(identity_path), approval.get("identity_binding_file_sha256"))
    _check(checks, "V07_identity_verified", identity.get("status") == "ALL_BINDINGS_VERIFIED",
           "ALL_BINDINGS_VERIFIED", identity.get("status"))
    budget = (R10_PLANNED_STARTS, MAX_STARTS, R10_PLANNED_INTERNAL_CASES, MAX_INTERNAL_CASES, RESERVE_STARTS, MAX_REFINE_STARTS)
    got = (approval.get("planned_starts"), approval.get("max_starts"), approval.get("planned_internal_cases"),
           approval.get("max_internal_cases"), approval.get("reserve_starts"), approval.get("max_refine_starts"))
    _check(checks, "V08_budget", budget == got, budget, got)
    _check(checks, "V09_dry_run", dry.get("physical_call_count") == 0
           and dry.get("cases_emitted") == 0 and dry.get("blocked") is True,
           {"physical": 0, "cases": 0, "blocked": True},
           {"physical": dry.get("physical_call_count"), "cases": dry.get("cases_emitted"),
            "blocked": dry.get("blocked")})
    bad = []
    for line in (out / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        if not (out / name).is_file() or sha256_file(out / name) != digest:
            bad.append(name)
    _check(checks, "V10_sha256sums", not bad, [], bad)
    failed = [c for c in checks if c["status"] == "FAIL"]
    return {"status": "PASS" if not failed else "FAIL", "checks": checks,
            "failed": [c["check_id"] for c in failed],
            "run_dir": str(Path(out).resolve()), "physical_call_count": 0}


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="P2a v2 zero-physical package builder/verifier")
    parser.add_argument("command", choices=("build", "verify", "dry-run", "run"))
    parser.add_argument("--out", default=None)
    parser.add_argument("--a1-root", default=None)
    parser.add_argument("--prereg", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else RUN_DIR
    root = Path(args.a1_root) if args.a1_root else DEFAULT_A1_ROOT
    if args.command == "build":
        result = build_package(out_dir=out, a1_root=root,
                               prereg_path=Path(args.prereg) if args.prereg else None)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    if args.command == "verify":
        result = verify_package(out)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0 if result["status"] == "PASS" else 1
    if args.command == "dry-run":
        plan_path = out / PLAN_FILENAME
        plan = _read_json(plan_path)
        result = run_dry_run(plan_path=plan_path, approval_path=out / APPROVAL_FILENAME,
                             prereg_path=out / PREREG_FILENAME,
                             initial_manifest_path=out / INITIAL_MANIFEST_FILENAME,
                             identity_path=out / IDENTITY_FILENAME, a1_root=root,
                             out_path=out / DRY_RUN_FILENAME)
        _write_json(out / DRY_RUN_FILENAME, result)
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    if args.command == "run":
        if not (out / "approval.json").is_file():
            print(json.dumps({"status": "REFUSED",
                              "reason": "approval.json is absent; P2a v2 is not authorized",
                              "physical_call_count": 0}, ensure_ascii=False))
            return 2
        from .p2a_v2_executor import ExecutorRefused, run_batch_executable
        try:
            result = run_batch_executable(out, root)
        except ExecutorRefused as exc:
            print(json.dumps({"status": "REFUSED", "reason": str(exc),
                              "physical_call_count": 0}, ensure_ascii=False))
            return 2
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
        return 0
    print(json.dumps({"status": "REFUSED", "reason": "unknown command", "physical_call_count": 0},
                     ensure_ascii=False))
    return 2


if __name__ == "__main__":
    sys.exit(main())
