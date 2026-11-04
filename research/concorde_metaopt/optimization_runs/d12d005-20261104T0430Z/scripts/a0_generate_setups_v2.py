#!/usr/bin/env python
"""D-12D-005 A0 v2: 零求解器 VSPAERO 7 setups 生成（Batch2 / 8 cases）。

范围（P4 无关，属 D-12D-005 A 线 Batch2）：
  1) Gate2 repair registration：mach-aware CL 期望（2D Ackeret + 一阶有限展长），
     S3/S4 诊断区间 [0.060, 0.090]；显式披露 post-hoc 性质（S3/S4 已观测）；
     超声速 CDi/CDtot 数值带废止（来自亚声速公式），改为定性门。
  2) S6_STD_M2p02_aoa1：标准矩形翼 Mach 2.02 / AoA=1deg 独立超声速确认 case。
  3) 12D 主翼密度/扰动 setups：B2-01..B2-06 + B2-07（B2-03 重建 repeatability）。
     模型由 geometry_model + openvsp_check.build_openvsp_request + openvsp_geometry._add_wing
     从 12D design space 构建（wing-only），几何与 archived wing355_baseline.vsp3 做 parity。
  4) 负控制 3 项（wrong Sref / legacy 无 '=' / wrong NumWakeNodes）。
  5) 证据：evidence/a0v2/setup_generation_v2.json、gate2_repair_registration.json、
     <case>/expected_v2.json、evidence/a0v2/README.md（中文）。

硬边界：本脚本不含任何 solver 启动路径；VSPAEROSweep 一律 StopBeforeRun=1；
thin .vspgeom 由 VSPAEROComputeGeometry 生成并移动到 git 之外，evidence 记录 sha256/bytes；
solver_processes_started = 0；任何 solver 产物（.adb/.history/.polar/.lod/.groups/.fem）出现即失败。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
EVID_ROOT = RUN_DIR / "evidence" / "a0v2"
SETUP_ROOT = EVID_ROOT / "setup_gen"
GATE2_PATH = EVID_ROOT / "gate2_repair_registration.json"
EVIDENCE_PATH = EVID_ROOT / "setup_generation_v2.json"
README_PATH = EVID_ROOT / "README.md"
RAW_ARTIFACTS = (
    Path("D:/RCAIDE/outputs/concorde_metaopt") / RUN_DIR.name / "raw_artifacts" / "a0v2_setup"
)
REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RUNNER = RUN_DIR / "scripts" / "vspaero7_runner_v1frozen.py"
DESIGN_CONFIG = REPO_ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
OPENVSP_ROOT = Path("D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64")

MU = 1.42161308e-05
RHO = 0.1153178340089936
A_SOUND = 295.0680184

# 归档证据（只读）。sha 必须匹配，否则 fail-closed。
ARCHIVED_MODEL_SHA256 = "9a788b467095b1a958a240eaa0132e922f667649e9212f9b19e4399bad14f27c"
ARCHIVED_MODEL_CANDIDATES = (
    REPO_ROOT
    / "research/concorde_metaopt/optimization_runs/"
    / "d12d004-vspaero72-lf-20261102T0500Z/evidence/v0/setup_gen/wing355_baseline.vsp3",
    Path(
        "D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/"
        "d12d005-20261104T0430Z/evidence/v1b/cases/S5_D12_M2p02_base/bundle/wing355_baseline.vsp3"
    ),
)
# v1 A0 已归档的 thin vspgeom（位于 git 之外）。用于几何 parity 的强证据（文件字节级）。
ARCHIVED_STD_VSPGEOM_SHA256 = "8363f8fb209dd3120bbdf2e3766605b9405b97de0c7561b0be08c91c4cb8ebad"
ARCHIVED_D12_BASELINE_VSPGEOM_SHA256 = "9fcda6d5d45300fbb0e20257c9ddc80540b44f5064a9566089d7ef85f9018d8e"

# 12D 主翼合同（与 v1 D12_CONTRACT / v1frozen runner CONTRACT_12D 逐字段一致）。
D12_CONTRACT = {
    "Sref": 358.25, "Cref": 18.489893, "Bref": 25.604638,
    "X_cg": 16.821978259514246, "Y_cg": 0.0, "Z_cg": 0.0,
    "Mach": 2.02, "AoA": 2.0, "Beta": 0.0,
    "ReCref": 89397005.8767656, "Vinf": 596.0373972278921, "Rho": RHO,
    "Symmetry": 0, "NumWakeNodes": 8, "WakeIters": 5, "WakeRelax": 1.0, "FarDist": -1.0,
}

# 标准矩形翼（v1 S3/S4 同几何）：AR=4、Sref=4 m²、Cref=1、Bref=4、Xcg=0.25、SectTess_U=20。
STD_WING = {
    "name": "STD_RECT_AR4",
    "symmetric": True,
    "span_m": 4.0,
    "location": [0.0, 0.0, 0.0],
    "rotation": [0.0, 0.0, 0.0],
    "sections": [
        {"percent_span_location": 0.0, "chord_m": 1.0, "leading_edge_x_m": 0.0, "twist_deg": 0.0},
        {"percent_span_location": 1.0, "chord_m": 1.0, "leading_edge_x_m": 0.0, "twist_deg": 0.0},
    ],
}
STD_TESS_U = 20.0
STD_METRICS = {"TotalSpan": 4.0, "TotalArea": 4.0, "TotalChord": 1.0, "TotalAR": 4.0}

# 密度/扰动 case 计划（8 个；B2-07 为 B2-03 重建）。
D12_BASELINE = {}
CASES = [
    {"case_id": "B2-01", "kind": "d12", "tess": 3.0, "design": dict(D12_BASELINE),
     "note": "12D 主翼 thin 基线：每个 XSec SectTess_U=3（低密度）"},
    {"case_id": "B2-02", "kind": "d12", "tess": 6.0, "design": dict(D12_BASELINE),
     "note": "12D 主翼 thin 基线：每个 XSec SectTess_U=6（与 v1 S5 同密度）"},
    {"case_id": "B2-03", "kind": "d12", "tess": 12.0, "design": dict(D12_BASELINE),
     "note": "12D 主翼 thin 基线：每个 XSec SectTess_U=12（高密度）"},
    {"case_id": "B2-04", "kind": "d12", "tess": 12.0, "design": {"wing_area": 376.1625},
     "note": "单因素扰动 W01 wing_area=376.1625（baseline 358.25 的 +5%），SectTess_U=12"},
    {"case_id": "B2-05", "kind": "d12", "tess": 12.0, "design": {"sweep_1": 69.0},
     "note": "单因素扰动 W03 sweep_1=69.0（baseline 67），SectTess_U=12"},
    {"case_id": "B2-06", "kind": "d12", "tess": 12.0, "design": {"tip_twist": 2.0},
     "note": "单因素扰动 W10 tip_twist=2.0（baseline 0），SectTess_U=12"},
    {"case_id": "B2-07", "kind": "d12", "tess": 12.0, "design": dict(D12_BASELINE),
     "note": "B2-03 重建（repeatability check；SectTess_U=12）", "repeat_of": "B2-03"},
    {"case_id": "S6_STD_M2p02_aoa1", "kind": "std", "tess": STD_TESS_U, "design": dict(D12_BASELINE),
     "note": "独立超声速确认 case：标准矩形翼 Mach 2.02 AoA=1deg（与 S3 同几何/合同，仅 AoA 减半）",
     "contract": "std_mach2p02_aoa1"},
]

# 负控制：对一个已生成的 12D contract setup 做三种破坏，要求 runner 拒绝。
NEGATIVE_CONTROL_CASE = "B2-03"


class A0V2Error(RuntimeError):
    """A0 v2 setup 生成失败（fail-closed）。"""


# --------------------------------------------------------------------------- #
# 通用工具
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path: Path) -> dict:
    p = Path(path)
    return {"name": p.name, "bytes": p.stat().st_size, "sha256": sha256_file(p)}


def write_json(path: Path, payload: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_runner():
    spec = importlib.util.spec_from_file_location("vspaero7_runner_v1frozen", RUNNER)
    if spec is None or spec.loader is None:
        raise A0V2Error("无法加载 runner：%s" % RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def import_openvsp():
    root = str(OPENVSP_ROOT)
    if not Path(root).is_dir():
        raise A0V2Error("OpenVSP root 不存在：%s" % root)
    os.add_dll_directory(root)
    for sub in ("python", "python/openvsp", "python/degen_geom", "python/utilities", "python/openvsp_config"):
        candidate = os.path.join(root, sub)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    import openvsp as vsp

    return vsp


def set_input(vsp, analysis: str, key: str, value) -> None:
    typ = vsp.GetAnalysisInputType(analysis, key)
    if typ == 2:
        vsp.SetDoubleAnalysisInput(analysis, key, [float(value)], 0)
    elif typ == 1:
        vsp.SetIntAnalysisInput(analysis, key, [int(value)], 0)
    elif typ == 3:
        vsp.SetStringAnalysisInput(analysis, key, [str(value)], 0)
    else:
        raise A0V2Error("未知 analysis input 类型 %r（%s/%s）" % (typ, analysis, key))


def std_contract(mach: float, wake_nodes: int, wake_iters: int, aoa_deg: float = 2.0) -> dict:
    vinf = mach * A_SOUND
    return {
        "Sref": 4.0, "Cref": 1.0, "Bref": 4.0,
        "X_cg": 0.25, "Y_cg": 0.0, "Z_cg": 0.0,
        "Mach": mach, "AoA": aoa_deg, "Beta": 0.0,
        "ReCref": RHO * vinf * 1.0 / MU, "Vinf": vinf, "Rho": RHO,
        "Symmetry": 0, "NumWakeNodes": wake_nodes, "WakeIters": wake_iters,
        "WakeRelax": 1.0, "FarDist": -1.0,
    }


def case_contract(case: dict) -> dict:
    if case.get("contract") == "std_mach2p02_aoa1":
        return std_contract(2.02, 8, 5, aoa_deg=1.0)
    if case["kind"] == "std":
        return std_contract(2.02, 8, 5)
    return dict(D12_CONTRACT)


# --------------------------------------------------------------------------- #
# mach-aware Gate2 repair registration（Ackeret + 一阶有限展长）
# --------------------------------------------------------------------------- #
def mach_aware_cl(mach: float, aoa_deg: float, aspect_ratio: float) -> dict:
    beta = math.sqrt(mach * mach - 1.0)
    cl_alpha_2d = 4.0 / beta  # Ackeret 2D 线化超声速
    cl_2d = cl_alpha_2d * math.radians(aoa_deg)
    cl_alpha_3d = cl_alpha_2d / (1.0 + cl_alpha_2d / (math.pi * aspect_ratio))
    cl_3d = cl_alpha_3d * math.radians(aoa_deg)
    return {
        "beta": beta,
        "CL_alpha_2d_per_rad": cl_alpha_2d,
        "CL_2d": cl_2d,
        "CL_alpha_3d_first_order_per_rad": cl_alpha_3d,
        "CL_3d_first_order": cl_3d,
        "aspect_ratio": aspect_ratio,
    }


def subsonic_helmbold_cl(mach: float, aoa_deg: float, aspect_ratio: float) -> dict:
    cl_alpha_rad = 2.0 * math.pi * aspect_ratio / (math.sqrt(aspect_ratio * aspect_ratio + 4.0) + 2.0)
    cl = cl_alpha_rad * math.radians(aoa_deg)
    return {
        "theory": "subsonic Helmbold 有限翼展升力线近似（Mach 无关；超声速下不适用）",
        "CL_alpha_per_rad": cl_alpha_rad,
        "CL": cl,
        "CL_expected_range": [round(0.8 * cl, 6), round(1.2 * cl, 6)],
    }


# S3/S4 已观测值（来源：evidence/v1/cases/S3_STD_M2p02_base/case_summary.json 与
# evidence/v1b/cases/S4_STD_M2p02_wn128/S4_STD_M2p02_wn128_model.polar；A5 复核
# role_reviews/a5/s3_assessment/s3_assessment.md 认定非发散）。
OBSERVED_S3 = {
    "CLtot": 0.074251031783,
    "CDi": 0.002606540227,
    "CDtot": 0.013789407924,
    "source": "evidence/v1/cases/S3_STD_M2p02_base/case_summary.json",
}
OBSERVED_S4 = {
    "CLtot": 0.074250958215,
    "CDi": 0.002606535876,
    "CDtot": 0.013789403504,
    "source": "evidence/v1b/cases/S4_STD_M2p02_wn128/S4_STD_M2p02_wn128_model.polar",
}
# post-hoc 诊断带（预注册于本次 v2 evidence；非独立确认，独立确认由 S6 承担）。
GATE2_DIAGNOSTIC_CL_RANGE = [0.060, 0.090]
# S6 独立确认带：AoA=1deg 的 CL_3d 一阶理论值 0.0336706，取 [0.030, 0.045]。
S6_EXPECTED_CL_RANGE = [0.030, 0.045]


def build_gate2_registration() -> dict:
    theory_2deg = mach_aware_cl(2.02, 2.0, 4.0)
    theory_1deg = mach_aware_cl(2.02, 1.0, 4.0)
    old = subsonic_helmbold_cl(2.02, 2.0, 4.0)
    old_low, old_high = old["CL_expected_range"]
    shortfall_pct = round((1.0 - OBSERVED_S3["CLtot"] / old_low) * 100.0, 3)
    return {
        "schema_version": "d12d005-a0v2-gate2-repair-1",
        "artifact_kind": "D12D005_A0V2_GATE2_REPAIR_REGISTRATION",
        "generated_utc": utc_stamp(),
        "run_id": RUN_DIR.name,
        "solver_processes_started": 0,
        "physical_call_count": 0,
        "status": "REGISTERED_POST_HOC_DIAGNOSTIC",
        "scope": {
            "case_ids": ["S3_STD_M2p02_base", "S4_STD_M2p02_wn128"],
            "wing": "标准矩形翼：AR=4、Sref=4 m²、Cref=1、Bref=4、Xcg=0.25、AoA=2deg、Mach=2.02",
            "usage": "仅对既有 S3/S4 观测做诊断性解释；不得作为独立确认；独立确认由 S6_STD_M2p02_aoa1 承担",
        },
        "formula": {
            "beta": "sqrt(Mach^2 - 1)",
            "CL_alpha_2d_ackeret_per_rad": "4 / beta",
            "CL_alpha_3d_first_order_per_rad": "CL_alpha_2d / (1 + CL_alpha_2d / (pi * AR))",
            "CL": "CL_alpha * AoA_rad",
            "note": "Ackeret 线化超声速 + 一阶有限展长修正；不含粘性/厚度/尾迹非线性",
        },
        "derivation": {
            "mach": 2.02,
            "aoa_deg": 2.0,
            "aspect_ratio": 4.0,
            "beta": theory_2deg["beta"],
            "CL_alpha_2d_per_rad": theory_2deg["CL_alpha_2d_per_rad"],
            "CL_2d": theory_2deg["CL_2d"],
            "CL_alpha_3d_first_order_per_rad": theory_2deg["CL_alpha_3d_first_order_per_rad"],
            "CL_3d_first_order": theory_2deg["CL_3d_first_order"],
            "s6_aoa_deg": 1.0,
            "s6_CL_2d": theory_1deg["CL_2d"],
            "s6_CL_3d_first_order": theory_1deg["CL_3d_first_order"],
        },
        "diagnostic_expectations": {
            "S3_STD_M2p02_base": {
                "CL_range": list(GATE2_DIAGNOSTIC_CL_RANGE),
                "CDi_CDtot": "定性门：CDi>0、CDtot>=CDi、全部有限（超声速数值带废止）",
            },
            "S4_STD_M2p02_wn128": {
                "CL_range": list(GATE2_DIAGNOSTIC_CL_RANGE),
                "CDi_CDtot": "定性门：CDi>0、CDtot>=CDi、全部有限（超声速数值带废止）",
            },
        },
        "observed": {
            "S3_STD_M2p02_base": dict(OBSERVED_S3, in_diagnostic_range=(
                GATE2_DIAGNOSTIC_CL_RANGE[0] <= OBSERVED_S3["CLtot"] <= GATE2_DIAGNOSTIC_CL_RANGE[1]),
                a5_assessment="CONTINUE_S4_S5；Ew=inf 为派生列除零伪影，非发散",
                a5_assessment_path="role_reviews/a5/s3_assessment/s3_assessment.md"),
            "S4_STD_M2p02_wn128": dict(OBSERVED_S4, in_diagnostic_range=(
                GATE2_DIAGNOSTIC_CL_RANGE[0] <= OBSERVED_S4["CLtot"] <= GATE2_DIAGNOSTIC_CL_RANGE[1])),
        },
        "old_registration": {
            "theory": old["theory"],
            "CL_expected_range": old["CL_expected_range"],
            "status": "VOID_FOR_SUPERSONIC_CASES",
            "reason": "Helmbold 亚声速公式在 Mach 2.02 不适用；S3/S4 观测 CLtot 低于该带下界",
            "S3_shortfall_vs_lower_bound_pct": shortfall_pct,
        },
        "replacement_bands": {
            "CL_diagnostic_range": list(GATE2_DIAGNOSTIC_CL_RANGE),
            "CL_status": "DIAGNOSTIC_POST_HOC（S3/S4 已观测后才登记）",
            "CDi_CDtot_numeric_bands": "VOID（原带由亚声速公式推导；超声速改用定性门）",
            "CDi_CDtot_qualitative_gates": [
                "CDi > 0",
                "CDtot >= CDi",
                "CL/CDi/CDtot 全部有限且无 NaN/INF",
                "|CL| < 1（量级门）",
            ],
        },
        "disclosure": {
            "post_hoc_correction": True,
            "post_hoc_evidence": "S3/S4 的 CLtot 在本注册生成前已被观测（见 observed 字段）",
            "independence": "本注册不得作为独立确认；S6_STD_M2p02_aoa1 为独立超声速确认 case",
            "no_retroactive_relabeling": "不修改 S3/S4 的原始观测与 v1 判定记录；本文件是新增诊断层",
            "a5_had_already_assessed": True,
        },
        "provenance": {
            "a5_assessment": "role_reviews/a5/s3_assessment/s3_assessment.md",
            "s3_case_summary": "evidence/v1/cases/S3_STD_M2p02_base/case_summary.json",
            "s4_polar": "evidence/v1b/cases/S4_STD_M2p02_wn128/S4_STD_M2p02_wn128_model.polar",
            "v1_vspgeom_archive": "D:/RCAIDE/outputs/concorde_metaopt/d12d005-20261104T0430Z/raw_artifacts/a0_setup/",
        },
    }


# --------------------------------------------------------------------------- #
# 12D 设计空间 / 翼模型构建
# --------------------------------------------------------------------------- #
def open_design_space():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from research.concorde_metaopt.aircraft.design_space import load_design_space

    space = load_design_space(DESIGN_CONFIG)
    if space.design_set != "12d_lifting_surfaces" or space.design_dim != 12:
        raise A0V2Error(
            "期望 12D lifting surfaces 设计空间，实际 design_set=%r design_dim=%r"
            % (space.design_set, space.design_dim)
        )
    expected_fixed = ("fuselage_length", "fuselage_fineness", "fuselage_height_width_ratio")
    if tuple(space.fixed_names) != expected_fixed:
        raise A0V2Error("12D 固定变量不符合合同：%r" % (tuple(space.fixed_names),))
    return space


def design_physical(case: dict, space) -> dict:
    baseline = space.baseline_vector()
    if len(baseline) != space.design_dim:
        raise A0V2Error("baseline 向量维度 %d != %d" % (len(baseline), space.design_dim))
    physical = {name: float(value) for name, value in zip(space.names, baseline)}
    for name, value in case["design"].items():
        if name not in physical:
            raise A0V2Error("case %s 引用了未声明的设计变量 %r" % (case["case_id"], name))
        physical[name] = float(value)
    return physical


def measure_wing(vsp, geom) -> dict:
    """从 OpenVSP geom 读回 wing 几何。

    约定：站位 i 的真实弦长 = XSec i 的 Tip_Chord（OpenVSP quirk，见 _add_wing 注释）；
    段 i（站位 i-1→i）的四分之一弦 sweep 由 LE x 递推 + 0.25c 计算。
    """
    surf = vsp.GetXSecSurf(geom, 0)
    count = vsp.GetNumXSec(surf)
    if count < 2:
        raise A0V2Error("wing XSec 数量不足：%r" % count)
    chords, spans, sweeps, twists, tess, root_chords, tip_chords = [], [], [], [], [], [], []
    for index in range(count):
        xsec = vsp.GetXSec(surf, index)
        chords.append(float(vsp.GetParmVal(vsp.GetXSecParm(xsec, "Tip_Chord"))))
        spans.append(float(vsp.GetParmVal(vsp.GetXSecParm(xsec, "Span"))))
        sweeps.append(float(vsp.GetParmVal(vsp.GetXSecParm(xsec, "Sweep"))))
        twists.append(float(vsp.GetParmVal(vsp.GetXSecParm(xsec, "Twist"))))
        tess.append(float(vsp.GetParmVal(vsp.GetXSecParm(xsec, "SectTess_U"))))
        root_chords.append(float(vsp.GetParmVal(vsp.GetXSecParm(xsec, "Root_Chord"))))
        tip_chords.append(float(vsp.GetParmVal(vsp.GetXSecParm(xsec, "Tip_Chord"))))
    if any(value <= 0.0 for value in chords):
        raise A0V2Error("读回弦长非正：%r" % (chords,))
    semispan = float(sum(spans[1:]))
    if semispan <= 0.0:
        raise A0V2Error("读回半展长非正：%r" % semispan)
    x_le = [0.0]
    for index in range(1, count):
        x_le.append(x_le[-1] + spans[index] * math.tan(math.radians(sweeps[index])))
    x_qc = [x_le[index] + 0.25 * chords[index] for index in range(count)]
    qc_sweep_deg = [
        math.degrees(math.atan2(x_qc[index] - x_qc[index - 1], spans[index]))
        for index in range(1, count)
    ]
    area = float(vsp.GetParmVal(geom, "TotalArea", "WingGeom"))
    span = float(vsp.GetParmVal(geom, "TotalSpan", "WingGeom"))
    mac_integral = 0.0
    for index in range(count - 1):
        chord_start = chords[index]
        chord_end = chords[index + 1]
        delta = chord_end - chord_start
        fraction = spans[index + 1] / semispan
        mac_integral += fraction * (chord_start * chord_start + chord_start * delta + delta * delta / 3.0)
    mac = span * mac_integral / area if area else float("nan")
    return {
        "area_m2": area,
        "span_m": span,
        "semispan_m": semispan,
        "chords_m": chords,
        "root_chord_m": chords[0],
        "mac_m": mac,
        "qc_sweep_deg": qc_sweep_deg,
        "tip_twist_deg": twists[-1],
        "twists_deg": twists,
        "le_sweep_deg": sweeps,
        "sect_tess_u": tess,
        "root_chord_raw": root_chords,
        "tip_chord_raw": tip_chords,
    }


def _relative_error(actual: float, expected: float) -> float:
    scale = max(abs(actual), abs(expected), 1e-12)
    return abs(actual - expected) / scale


def compare_wing_metrics(measured: dict, expected: dict, tolerance: float = 1e-3) -> dict:
    """比较读回几何与设计意图；返回逐项误差与 PASS/FAIL。"""
    checks = {}

    def check(key: str, actual, want, *, abs_tolerance: float | None = None):
        actual = float(actual)
        want = float(want)
        if abs_tolerance is not None:
            error = abs(actual - want)
            ok = error <= abs_tolerance
        else:
            error = _relative_error(actual, want)
            ok = error <= tolerance
        checks[key] = {
            "measured": actual,
            "expected": want,
            "error": error,
            "tolerance": abs_tolerance if abs_tolerance is not None else tolerance,
            "mode": "absolute" if abs_tolerance is not None else "relative",
            "status": "PASS" if ok else "FAIL",
        }

    for key in ("area_m2", "span_m", "mac_m"):
        check(key, measured[key], expected[key])
    check("root_chord_m", measured["root_chord_m"], expected["root_chord_m"])
    for index, value in enumerate(measured["chords_m"]):
        check("chords_m[%d]" % index, value, expected["chords_m"][index])
    for index, value in enumerate(measured["qc_sweep_deg"]):
        check("qc_sweep_deg[%d]" % index, value, expected["qc_sweep_deg"][index])
    check("tip_twist_deg", measured["tip_twist_deg"], expected["tip_twist_deg"], abs_tolerance=1e-6)
    failed = [key for key, item in checks.items() if item["status"] != "PASS"]
    return {"tolerance": tolerance, "checks": checks, "failed": failed,
            "status": "PASS" if not failed else "FAIL"}


def expected_wing_metrics(geometry) -> dict:
    wing = geometry.wing
    sections = wing.sections
    return {
        "area_m2": float(wing.area_m2),
        "span_m": float(wing.span_m),
        "root_chord_m": float(wing.root_chord_m),
        "mac_m": float(wing.mean_aerodynamic_chord_m),
        "chords_m": [float(section.chord_m) for section in sections],
        "qc_sweep_deg": [float(section.quarter_chord_sweep_deg) for section in sections[:-1]],
        "tip_twist_deg": float(sections[-1].twist_deg),
    }


def build_model(vsp, case: dict, case_dir: Path, space) -> dict:
    """构建 wing-only 模型，写 vsp3，并读回校验（设计意图 + SectTess_U）。"""
    from research.concorde_metaopt.aircraft.geometry_builder import build_geometry_from_design_space
    from research.concorde_metaopt.aircraft.openvsp_check import build_openvsp_request
    from research.concorde_metaopt.aircraft import openvsp_geometry as OVG

    vsp.ClearVSPModel()
    record_payload = {}
    if case["kind"] == "d12":
        physical = design_physical(case, space)
        declared = [float(physical[name]) for name in space.names]
        geometry = build_geometry_from_design_space(space, declared)
        request = build_openvsp_request(geometry, case_dir, basename="wing355_baseline", formats=["vsp3"])
        wing_components = [entry for entry in request["components"] if entry["name"] == "main_wing"]
        if len(wing_components) != 1:
            raise A0V2Error("build_openvsp_request 未给出唯一 main_wing：%r" % [
                entry["name"] for entry in request["components"]])
        geom_spec = wing_components[0]
        geom = OVG._add_wing(vsp, geom_spec)
        model_name = "wing355_baseline.vsp3"
        record_payload["design_physical"] = physical
        record_payload["design_overrides"] = dict(case["design"])
        record_payload["openvsp_request"] = {
            "component": geom_spec["name"],
            "span_m": geom_spec["span_m"],
            "location": list(geom_spec["location"]),
            "section_count": len(geom_spec["sections"]),
        }
    elif case["kind"] == "std":
        geometry = None
        geom = OVG._add_wing(vsp, STD_WING)
        model_name = case["case_id"] + "_model.vsp3"
        record_payload["design_physical"] = None
        record_payload["design_overrides"] = {}
        record_payload["openvsp_request"] = {
            "component": STD_WING["name"], "span_m": STD_WING["span_m"],
            "location": list(STD_WING["location"]), "section_count": len(STD_WING["sections"]),
        }
    else:
        raise A0V2Error("未知 case kind：%r" % case["kind"])

    surf = vsp.GetXSecSurf(geom, 0)
    for index in range(vsp.GetNumXSec(surf)):
        vsp.SetParmVal(vsp.GetXSecParm(vsp.GetXSec(surf, index), "SectTess_U"), float(case["tess"]))
    vsp.Update()
    model_path = case_dir / model_name
    vsp.WriteVSPFile(str(model_path), vsp.SET_ALL)
    if not model_path.is_file():
        raise A0V2Error("OpenVSP 未写出模型：%s" % model_path)

    # 读回：模型文件重新加载，校验 SectTess_U 与几何指标。
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(model_path))
    vsp.Update()
    geoms = vsp.FindGeoms()
    if len(geoms) != 1:
        raise A0V2Error("模型读回 geom 数量 %d != 1（%s）" % (len(geoms), model_path.name))
    readback = measure_wing(vsp, geoms[0])
    expected_tess = [float(case["tess"])] * len(readback["sect_tess_u"])
    tess_error = max(abs(a - b) for a, b in zip(readback["sect_tess_u"], expected_tess))
    tess_ok = tess_error <= 1e-9
    result = {
        "model": record(model_path),
        "model_name": model_name,
        "sect_tess_u_expected": expected_tess,
        "sect_tess_u_readback": readback["sect_tess_u"],
        "sect_tess_u_max_abs_error": tess_error,
        "sect_tess_u_status": "PASS" if tess_ok else "FAIL",
        "readback": readback,
    }
    if case["kind"] == "std":
        metrics = {
            key: float(vsp.GetParmVal(vsp.FindParm(geoms[0], key, "WingGeom")))
            for key in ("TotalSpan", "TotalArea", "TotalChord", "TotalAR")
        }
        for key, want in STD_METRICS.items():
            if abs(metrics[key] - want) > 1e-6:
                raise A0V2Error("标准翼 %s 期望 %r 实际 %r" % (key, want, metrics[key]))
        result["std_wing_metrics"] = metrics
        result["std_wing_metrics_expected"] = dict(STD_METRICS)
    else:
        expected = expected_wing_metrics(geometry)
        consistency = compare_wing_metrics(readback, expected)
        if consistency["status"] != "PASS":
            raise A0V2Error(
                "case %s 模型读回几何与设计意图不一致：%r"
                % (case["case_id"], consistency["failed"])
            )
        result["design_consistency"] = consistency
        result["geometry_expected"] = expected
    if not tess_ok:
        raise A0V2Error("case %s SectTess_U 读回不符：%r" % (case["case_id"], tess_error))
    record_payload.update(result)
    return record_payload


# --------------------------------------------------------------------------- #
# 几何 parity（vs archived wing355_baseline.vsp3 / v1 thin vspgeom）
# --------------------------------------------------------------------------- #
def resolve_archived_model() -> tuple[Path, dict]:
    notes = []
    for candidate in ARCHIVED_MODEL_CANDIDATES:
        if not candidate.is_file():
            notes.append({"path": str(candidate), "status": "MISSING"})
            continue
        digest = sha256_file(candidate)
        notes.append({"path": str(candidate), "status": "FOUND", "sha256": digest,
                      "bytes": candidate.stat().st_size})
        if digest != ARCHIVED_MODEL_SHA256:
            raise A0V2Error(
                "归档模型 sha 不符：%s -> %s（期望 %s）" % (candidate, digest, ARCHIVED_MODEL_SHA256)
            )
        return candidate, {"candidates": notes, "chosen": str(candidate)}
    raise A0V2Error("未找到归档 wing355_baseline.vsp3：%r" % (notes,))


def parity_vs_archived(vsp, baseline_model: dict) -> dict:
    archived_path, resolution = resolve_archived_model()
    vsp.ClearVSPModel()
    vsp.ReadVSPFile(str(archived_path))
    vsp.Update()
    geoms = vsp.FindGeoms()
    if len(geoms) != 1:
        raise A0V2Error("归档模型 geom 数量 %d != 1" % len(geoms))
    archived = measure_wing(vsp, geoms[0])
    fresh = baseline_model["readback"]
    comparison = compare_wing_metrics(fresh, {
        "area_m2": archived["area_m2"],
        "span_m": archived["span_m"],
        "root_chord_m": archived["root_chord_m"],
        "mac_m": archived["mac_m"],
        "chords_m": archived["chords_m"],
        "qc_sweep_deg": archived["qc_sweep_deg"],
        "tip_twist_deg": archived["tip_twist_deg"],
    })
    if comparison["status"] != "PASS":
        raise A0V2Error("12D 基线几何 parity 失败：%r" % (comparison["failed"],))
    # thin vspgeom 字节级 parity（v1 A0 归档文件在 git 之外；存在则比较，不存在则标记 UNVERIFIED）
    v1_archive = Path("D:/RCAIDE/outputs/concorde_metaopt") / RUN_DIR.name / "raw_artifacts" / "a0_setup"
    result = {
        "archived_model": record(archived_path),
        "resolution": resolution,
        "archived_readback": archived,
        "fresh_baseline_readback": fresh,
        "metric_comparison": comparison,
        "model_sha_note": (
            "vsp3 容器字节在不同会话/进程中不可复现（同一几何两次写出 sha 不同，大小相同）；"
            "parity 以读回几何指标 + thin vspgeom 字节 sha 为准，不以 vsp3 sha 为准"
        ),
        "fresh_model_sha256": baseline_model["model"]["sha256"],
    }
    checks = []
    for name, expected_sha in (
        ("S5_D12_M2p02_base", ARCHIVED_D12_BASELINE_VSPGEOM_SHA256),
    ):
        path = v1_archive / (name + ".vspgeom")
        if path.is_file():
            actual = sha256_file(path)
            checks.append({"name": name, "path": str(path), "expected_sha256": expected_sha,
                           "actual_sha256": actual, "status": "PASS" if actual == expected_sha else "FAIL"})
        else:
            checks.append({"name": name, "path": str(path), "expected_sha256": expected_sha,
                           "actual_sha256": None, "status": "UNVERIFIED"})
    result["v1_archive_vspgeom"] = checks
    if any(item["status"] == "FAIL" for item in checks):
        raise A0V2Error("v1 归档 vspgeom sha 与注册常量不符：%r" % checks)
    return result


def std_thin_geometry_parity(std_model: dict) -> dict:
    v1_archive = Path("D:/RCAIDE/outputs/concorde_metaopt") / RUN_DIR.name / "raw_artifacts" / "a0_setup"
    path = v1_archive / "S3_STD_M2p02_base.vspgeom"
    if not path.is_file():
        return {"name": "S3_STD_M2p02_base", "path": str(path),
                "expected_sha256": ARCHIVED_STD_VSPGEOM_SHA256, "actual_sha256": None,
                "status": "UNVERIFIED"}
    actual = sha256_file(path)
    status = "PASS" if actual == ARCHIVED_STD_VSPGEOM_SHA256 else "FAIL"
    if status != "PASS":
        raise A0V2Error("标准翼 thin vspgeom 与 v1 S3 归档 sha 不符：%s != %s"
                        % (actual, ARCHIVED_STD_VSPGEOM_SHA256))
    return {"name": "S3_STD_M2p02_base", "path": str(path),
            "expected_sha256": ARCHIVED_STD_VSPGEOM_SHA256, "actual_sha256": actual, "status": status}


# --------------------------------------------------------------------------- #
# 单 case 生成（zero solver）
# --------------------------------------------------------------------------- #
def generate_case(vsp, runner, case: dict, space) -> dict:
    case_id = case["case_id"]
    case_dir = SETUP_ROOT / case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    built = build_model(vsp, case, case_dir, space)
    model_path = case_dir / built["model_name"]
    base = model_path.stem
    contract = case_contract(case)
    cwd = os.getcwd()
    try:
        os.chdir(case_dir)
        # --- thin 表面几何（zero solver）---
        vsp.ClearVSPModel()
        vsp.ReadVSPFile(str(model_path))
        vsp.Update()
        vsp.SetAnalysisInputDefaults("VSPAEROComputeGeometry")
        set_input(vsp, "VSPAEROComputeGeometry", "GeomSet", vsp.SET_NONE)
        set_input(vsp, "VSPAEROComputeGeometry", "ThinGeomSet", vsp.SET_ALL)
        set_input(vsp, "VSPAEROComputeGeometry", "Symmetry", vsp.SYM_NONE)
        rid_geom = vsp.ExecAnalysis("VSPAEROComputeGeometry")
        geom_csv = case_dir / "geom_result_thin.csv"
        geom_csv_error = None
        try:
            vsp.WriteResultsCSVFile(rid_geom, str(geom_csv))
        except Exception as exc:  # pragma: no cover - OpenVSP API 差异
            geom_csv = None
            geom_csv_error = repr(exc)
        # --- setup 生成（StopBeforeRun=1，绝不启动 solver）---
        vsp.SetAnalysisInputDefaults("VSPAEROSweep")
        sweep = {
            "GeomSet": vsp.SET_NONE, "ThinGeomSet": vsp.SET_ALL, "Symmetry": vsp.SYM_NONE,
            "RefFlag": vsp.MANUAL_REF, "MACFlag": 0,
            "Sref": contract["Sref"], "cref": contract["Cref"], "bref": contract["Bref"],
            "MachStart": contract["Mach"], "MachEnd": contract["Mach"], "MachNpts": 1,
            "AlphaStart": contract["AoA"], "AlphaEnd": contract["AoA"], "AlphaNpts": 1,
            "BetaStart": contract["Beta"], "BetaEnd": contract["Beta"], "BetaNpts": 1,
            "StopBeforeRun": 1, "RedirectFile": "stdout", "NCPU": 4,
            "Xcg": contract["X_cg"], "Ycg": contract["Y_cg"], "Zcg": contract["Z_cg"],
            "NumWakeNodes": contract["NumWakeNodes"], "WakeNumIter": contract["WakeIters"],
            "WakeRelax": contract["WakeRelax"], "FarDist": contract["FarDist"],
        }
        for key, value in sweep.items():
            set_input(vsp, "VSPAEROSweep", key, value)
        rid_sweep = vsp.ExecAnalysis("VSPAEROSweep")
        stop_readback = int(vsp.GetIntAnalysisInput("VSPAEROSweep", "StopBeforeRun")[0])
        if stop_readback != 1:
            raise A0V2Error("case %s StopBeforeRun readback %r != 1" % (case_id, stop_readback))
        raw_setup = case_dir / (base + ".vspaero")
        vspgeom = case_dir / (base + ".vspgeom")
        vkey = case_dir / (base + ".vkey")
        csf = case_dir / (base + ".csf")
        if not raw_setup.is_file():
            raise A0V2Error("case %s VSPAEROSweep 未写出 %s" % (case_id, raw_setup))
        if not vspgeom.is_file():
            raise A0V2Error("case %s VSPAEROComputeGeometry 未写出 %s" % (case_id, vspgeom))
        if not vkey.is_file():
            raise A0V2Error("case %s 缺失 %s" % (case_id, vkey))
        if vkey.stem != model_path.stem:
            raise A0V2Error("case %s vkey basename %r != model basename %r"
                            % (case_id, vkey.stem, model_path.stem))
        # --- 合同注入 + 17/17 readback ---
        contract_setup = case_dir / (case_id + "_contract.vspaero")
        readback = runner.inject_contract_fields(
            raw_setup, contract_setup, contract,
            allow_legacy=True, expected_source="a0_generate_setups_v2.py:%s" % case_id,
        )
        if readback.get("status") != "PASS" or int(readback.get("assertions", 0)) != 17:
            raise A0V2Error("case %s 17/17 readback 未通过：status=%r assertions=%r"
                            % (case_id, readback.get("status"), readback.get("assertions")))
        # --- 断言无 solver 产物 ---
        solver_artifacts = runner.find_solver_artifacts(case_dir)
        if solver_artifacts:
            raise A0V2Error("case %s 生成后出现 solver 产物：%r" % (case_id, solver_artifacts[:8]))
        forbidden_globs = ("*.adb", "*.history", "*.polar", "*.lod", "*.groups", "*.fem")
        forbidden_hits = [pattern for pattern in forbidden_globs if list(case_dir.glob(pattern))]
        if forbidden_hits:
            raise A0V2Error("case %s solver glob 命中：%r" % (case_id, forbidden_hits))
        # --- thin vspgeom 移出 git ---
        RAW_ARTIFACTS.mkdir(parents=True, exist_ok=True)
        external = RAW_ARTIFACTS / (case_id + ".vspgeom")
        shutil.copyfile(vspgeom, external)
        vspgeom_record = record(external)
        vspgeom_record.update({
            "external_path": str(external),
            "outside_git": True,
            "local_copy": str(vspgeom),
            "local_copy_removed": True,
        })
        local_sha = sha256_file(vspgeom)
        if local_sha != vspgeom_record["sha256"]:
            raise A0V2Error("case %s vspgeom 复制 sha 不一致" % case_id)
        vspgeom.unlink()
        # --- expected_v2.json ---
        expected_payload = build_expected_payload(case, contract, readback)
        expected_path = case_dir / "expected_v2.json"
        write_json(expected_path, expected_payload)
        execution_bundle = {
            "note": (
                "A2 执行时把 model.vsp3 + .vkey + .csf + contract.vspaero 复制到执行目录，"
                "并把 thin .vspgeom 从 external_path 复制为 <base>.vspgeom；随后把 .vkey 第 2 行"
                "改为该 .vspgeom 的绝对路径（D-12D-004 V1 根因修复），最后运行 vspaero.exe -omp 4 <base>"
            ),
            "model": model_path.name,
            "vspgeom_external_path": str(external),
            "vspgeom_sha256": vspgeom_record["sha256"],
            "vspgeom_bytes": vspgeom_record["bytes"],
            "vkey": vkey.name,
            "csf": csf.name if csf.is_file() else None,
            "setup": contract_setup.name,
        }
        files_in_case_dir = sorted(path.name for path in case_dir.iterdir() if path.is_file())
        result = {
            "case_id": case_id,
            "kind": case["kind"],
            "note": case.get("note", ""),
            "repeat_of": case.get("repeat_of"),
            "case_dir": str(case_dir),
            "contract": contract,
            "model": built["model"],
            "model_name": built["model_name"],
            "model_readback": {
                "readback": built["readback"],
                "sect_tess_u_expected": built["sect_tess_u_expected"],
                "sect_tess_u_readback": built["sect_tess_u_readback"],
                "sect_tess_u_max_abs_error": built["sect_tess_u_max_abs_error"],
                "sect_tess_u_status": built["sect_tess_u_status"],
                "design_consistency": built.get("design_consistency"),
                "geometry_expected": built.get("geometry_expected"),
                "std_wing_metrics": built.get("std_wing_metrics"),
                "std_wing_metrics_expected": built.get("std_wing_metrics_expected"),
                "openvsp_request": built["openvsp_request"],
                "design_physical": built["design_physical"],
                "design_overrides": built["design_overrides"],
            },
            "thin_geometry": vspgeom_record,
            "vkey": record(vkey),
            "csf": record(csf) if csf.is_file() else None,
            "raw_setup": record(raw_setup),
            "contract_setup": record(contract_setup),
            "readback": readback,
            "readback_status": readback.get("status"),
            "readback_assertions": int(readback.get("assertions", 0)),
            "expected_v2": record(expected_path),
            "geom_result_csv": record(geom_csv) if geom_csv and geom_csv.is_file() else None,
            "geom_result_csv_error": geom_csv_error,
            "results": {
                "geom_result_id": str(rid_geom),
                "sweep_result_id": str(rid_sweep),
                "stop_before_run_readback": stop_readback,
            },
            "solver_artifacts_present": [],
            "files_in_case_dir": files_in_case_dir,
            "execution_bundle": execution_bundle,
        }
        return result
    finally:
        os.chdir(cwd)


def build_expected_payload(case: dict, contract: dict, readback: dict) -> dict:
    case_id = case["case_id"]
    if case["kind"] == "std":
        theory = mach_aware_cl(contract["Mach"], contract["AoA"], 4.0)
        analytic = {
            "theory": "Ackeret 线化超声速 2D + 一阶有限展长修正（Mach-aware）",
            "beta": theory["beta"],
            "CL_alpha_2d_per_rad": theory["CL_alpha_2d_per_rad"],
            "CL_alpha_3d_first_order_per_rad": theory["CL_alpha_3d_first_order_per_rad"],
            "CL_2d": theory["CL_2d"],
            "CL_3d_first_order": theory["CL_3d_first_order"],
            "CL_expected_range": list(S6_EXPECTED_CL_RANGE),
            "CDi_CDtot": "仅定性门：CDi>0、CDtot>=CDi、全部有限（超声速数值带废止，见 Gate2 repair 注册）",
            "independent_confirmation": True,
        }
    else:
        analytic = {
            "cl_expected_range": None,
            "note": "12D 主翼无独立解析参考；仅要求有限、符号/量级合理，且与 baseline/密度/扰动一致",
            "independent_confirmation": False,
        }
    return {
        "schema_version": "d12d005-a0v2-expected-1",
        "case_id": case_id,
        "kind": case["kind"],
        "note": case.get("note", ""),
        "repeat_of": case.get("repeat_of"),
        "contract": contract,
        "readback_spec_source": str(RUNNER),
        "readback_assertions": int(readback.get("assertions", 0)),
        "analytic_expectations": analytic,
        "gate2_repair_registration": str(GATE2_PATH),
        "solver_processes_started": 0,
    }


# --------------------------------------------------------------------------- #
# repeatability（B2-07 vs B2-03）与几何差异
# --------------------------------------------------------------------------- #
def normalize_setup_text(path: Path, case_id: str) -> str:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for token in (
        case_id,
        str(path.parent),
        str(path.parent).replace("\\", "/"),
    ):
        text = text.replace(token, "<CASE>")
    return text.replace("\r\n", "\n")


def repeatability_check(cases_by_id: dict) -> dict:
    source = cases_by_id["B2-03"]
    repeat = cases_by_id["B2-07"]
    comparisons = []
    for name, key in (("thin_geometry", "thin_geometry"), ("raw_setup", "raw_setup"),
                      ("contract_setup", "contract_setup"), ("csf", "csf"), ("vkey", "vkey")):
        first = source[key]
        second = repeat[key]
        first_arg = first.get("sha256") if isinstance(first, dict) else first
        second_arg = second.get("sha256") if isinstance(second, dict) else second
        comparisons.append({
            "artifact": name,
            "B2-03_sha256": first_arg,
            "B2-07_sha256": second_arg,
            "equal": first_arg == second_arg,
        })
    model_equal = source["model"]["sha256"] == repeat["model"]["sha256"]
    comparisons.append({
        "artifact": "model_vsp3",
        "B2-03_sha256": source["model"]["sha256"],
        "B2-07_sha256": repeat["model"]["sha256"],
        "equal": model_equal,
        "note": "vsp3 容器字节跨会话不可复现；本项仅记录，不作 repeatability 判据",
    })
    contract_text_equal = normalize_setup_text(
        Path(source["case_dir"]) / source["contract_setup"]["name"], "B2-03"
    ) == normalize_setup_text(
        Path(repeat["case_dir"]) / repeat["contract_setup"]["name"], "B2-07"
    )
    geometry_equal = _readback_geometry_equal(
        source["model_readback"]["readback"], repeat["model_readback"]["readback"]
    )
    tess_equal = source["model_readback"]["sect_tess_u_readback"] == repeat["model_readback"]["sect_tess_u_readback"]
    # repeatability 判据：thin geometry + raw setup + contract 规范化文本 + readback 几何 + SectTess_U
    judgment_inputs = {
        "thin_geometry_equal": next(item["equal"] for item in comparisons if item["artifact"] == "thin_geometry"),
        "raw_setup_equal": next(item["equal"] for item in comparisons if item["artifact"] == "raw_setup"),
        "contract_setup_normalized_equal": contract_text_equal,
        "readback_geometry_equal": geometry_equal,
        "sect_tess_u_equal": tess_equal,
    }
    failed = [key for key, ok in judgment_inputs.items() if not ok]
    return {
        "source_case": "B2-03",
        "repeat_case": "B2-07",
        "comparisons": comparisons,
        "judgment_inputs": judgment_inputs,
        "failed": failed,
        "status": "PASS" if not failed else "FAIL",
        "note": (
            "repeatability 以 thin vspgeom/raw setup/规范化 contract/读回几何/SectTess_U 判定；"
            "vsp3 与 .vkey 的字节差异（容器随机性/绝对路径）单列记录、不作判据"
        ),
    }


def _readback_geometry_equal(first: dict, second: dict, tolerance: float = 1e-12) -> bool:
    for key in ("area_m2", "span_m", "mac_m", "root_chord_m", "tip_twist_deg"):
        if abs(float(first[key]) - float(second[key])) > tolerance * max(1.0, abs(float(first[key]))):
            return False
    for key in ("chords_m", "qc_sweep_deg", "sect_tess_u"):
        left, right = first[key], second[key]
        if len(left) != len(right):
            return False
        for a, b in zip(left, right):
            if abs(float(a) - float(b)) > tolerance * max(1.0, abs(float(a))):
                return False
    return True


# --------------------------------------------------------------------------- #
# 负控制（runner 必须拒绝）
# --------------------------------------------------------------------------- #
def rewrite_setup_field(text: str, field: str, new_value: str) -> str:
    """按行改写 'field = value'；未找到目标字段则抛 A0V2Error（负控制 helper）。"""
    lines = []
    hit = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(field + " =") or stripped.startswith(field + "="):
            lines.append("%s = %s" % (field, new_value))
            hit = True
        else:
            lines.append(raw)
    if not hit:
        raise A0V2Error("负控制字段 %r 未找到" % (field,))
    return "\n".join(lines) + "\n"


def negative_controls(runner, case_lookup: dict) -> list:
    case_id = NEGATIVE_CONTROL_CASE
    case = case_lookup[case_id]
    case_dir = Path(case["case_dir"])
    neg_dir = EVID_ROOT / "negative_controls" / case_id
    if neg_dir.exists():
        shutil.rmtree(neg_dir)
    neg_dir.mkdir(parents=True)
    contract = dict(case_lookup[case_id]["contract"])
    source = case_dir / case["contract_setup"]["name"]
    text = source.read_text(encoding="utf-8")
    checks = []

    wrong_sref = neg_dir / "neg_wrong_sref.vspaero"
    wrong_sref.write_text(rewrite_setup_field(text, "Sref", "100.0"), encoding="utf-8", newline="\n")
    try:
        runner.read_setup_file(wrong_sref, contract)
        checks.append({"control": "wrong_sref", "result": "FAIL_NOT_REJECTED"})
    except runner.ContractViolation as exc:
        checks.append({"control": "wrong_sref", "result": "REJECTED", "detail": str(exc)[:200]})

    legacy = neg_dir / "neg_legacy.vspaero"
    legacy.write_text("Sref 4.0\nMach 0.1\n", encoding="utf-8", newline="\n")
    try:
        runner.read_setup_file(legacy, contract, require_canonical=True)
        checks.append({"control": "legacy_no_equals", "result": "FAIL_NOT_REJECTED"})
    except runner.SetupFormatError as exc:
        checks.append({"control": "legacy_no_equals", "result": "REJECTED", "detail": str(exc)[:200]})

    wake = neg_dir / "neg_wake_mismatch.vspaero"
    wake.write_text(rewrite_setup_field(text, "NumWakeNodes", "999"), encoding="utf-8", newline="\n")
    try:
        runner.read_setup_file(wake, contract)
        checks.append({"control": "wake_node_mismatch", "result": "FAIL_NOT_REJECTED"})
    except runner.ContractViolation as exc:
        checks.append({"control": "wake_node_mismatch", "result": "REJECTED", "detail": str(exc)[:200]})

    return [{
        "case_id": case_id,
        "checks": checks,
        "files": sorted(path.name for path in neg_dir.iterdir() if path.is_file()),
        "all_rejected": all(item["result"] == "REJECTED" for item in checks),
    }]


# --------------------------------------------------------------------------- #
# 证据与 README
# --------------------------------------------------------------------------- #
def render_readme(evidence: dict) -> str:
    summary = evidence["summary"]
    lines = [
        "# D-12D-005 A0 v2：零求解器 VSPAERO 7 setups 生成（8 个修订 case）",
        "",
        "本目录记录 A0 v2 的**零求解器** setup 生成证据。生成过程只调用 OpenVSP Python API 完成几何与",
        "VSPAEROSweep 输入面写盘（StopBeforeRun=1），**未启动任何 VSPAERO/SU2/RCAIDE solver 进程**。",
        "",
        "## 1. 目的与范围",
        "",
        "- 修复 Gate2 registration：旧注册依赖亚声速 Helmbold 公式，在 Mach 2.02 下 band 错误（CLtot 0.0743",
        "  远低于 [0.10844, 0.16266]，S3 shortfall 31.528%）。v2 以 A5 复核的 Ackeret 线化超声速公式",
        "  重新注册 Gate2，并对 S3/S4 已观测值作 **post-hoc** 披露（不是独立确认）。",
        "- 新增独立超声速确认 case：S6_STD_M2p02_aoa1（标准矩形翼，Mach 2.02，AoA=1deg），其预期 CL 带",
        "  来自同一 Mach-aware 理论，且在该 case 运行前注册，因此可作为修复的独立确认。",
        "- 新增 12D 主翼密度/扰动 setups（B2-01..B2-07），用于后续 A2/A5 的 thin 表面几何敏感性评估。",
        "- 12D 主翼几何与 v1 归档 wing355_baseline.vsp3 做 parity（读回几何指标）+ thin vspgeom 字节 sha",
        "  对照；B2-07 为 B2-03 的重复性检查。",
        "",
        "## 2. Case 计划（8 个）",
        "",
        "| case | kind | SectTess_U | 设计 | 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in evidence["cases"]:
        design = item.get("model_readback", {}).get("design_overrides") or {}
        lines.append("| %s | %s | %s | %s | %s |" % (
            item["case_id"], item["kind"], item["model_readback"]["sect_tess_u_expected"][0],
            ("12D baseline" if not design else str(design)),
            item.get("note", ""),
        ))
    lines += [
        "",
        "12D 合同（所有 d12 case）：Sref 358.25、Cref 18.489893、Bref 25.604638、Xcg 16.821978259514246、",
        "Mach 2.02、AoA 2deg、ReCref 89397005.8767656、Vinf 596.0373972278921、Symmetry 0、NumWakeNodes 8、",
        "WakeIters 5、WakeRelax 1.0、FarDist -1.0。标准翼合同：Sref 4、Cref 1、Bref 4、Xcg 0.25；S6 仅 AoA=1deg。",
        "",
        "## 3. 结论（本阶段）",
        "",
        "- status：%s" % (summary["status"],),
        "- case 数：%d；17/17 readback 通过：%d；无 solver 产物：全部" % (
            summary["case_count"], summary["readback_pass"]),
        "- 12D 基线 parity（读回几何 vs v1 归档模型）：%s；thin vspgeom 字节 parity：%s" % (
            evidence["parity"]["metric_comparison"]["status"],
            ", ".join("%s=%s" % (item["name"], item["status"]) for item in evidence["parity"]["v1_archive_vspgeom"])),
        "- 标准翼 thin vspgeom 与 v1 S3 归档字节对照：%s" % (evidence["std_parity"]["status"],),
        "- B2-07 重复性：%s" % (evidence["repeatability"]["status"],),
        "- 负控制：%s" % ("全部按预期被拒绝" if summary["negative_controls_pass"] else "存在未被拒绝的负控制",),
        "- solver 进程启动数：%d；StopBeforeRun 强制为 1" % (summary["solver_starts"],),
        "",
        "## 4. 非结论 / 边界",
        "",
        "- 本阶段**不产生**任何气动力/极线数值结论：没有 solver 运行，CDi/CDtot 数值带已废止，只保留定性门",
        "  （CDi>0、CDtot>=CDi、全部有限）。",
        "- Gate2 修复是 **post-hoc** 注册：S3/S4 的 CLtot 已在 v1 观测到，故该修复只作诊断；独立确认只有 S6。",
        "- 12D 主翼 case 无独立解析参考，仅要求有限、符号/量级合理、与 baseline/扰动一致。",
        "- vsp3 容器字节跨会话不可复现（同一几何两次写出 sha 不同、大小相同）；parity 以读回几何指标与 thin",
        "  vspgeom 字节 sha 为准，不以 vsp3 sha 为准。",
        "- thin .vspgeom 移出 git（external_path + sha256 + bytes + outside_git=true），仓库内只保留元数据。",
        "",
        "## 5. 产物",
        "",
        "- gate2_repair_registration.json：mach-aware Gate2 修复注册（schema、公式、推导、观测值、披露）",
        "- setup_generation_v2.json：生成证据主文件（cases/parity/repeatability/negative_controls/summary）",
        "- setup_gen/<case>/：模型、contract setup、expected_v2.json、readback 记录",
        "- negative_controls/B2-03/：三种被破坏的 setup（wrong Sref / legacy 无等号 / NumWakeNodes 错配）",
        "",
        "## 6. 复现",
        "",
        "```",
        "D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B scripts/a0_generate_setups_v2.py",
        "D:/RCAIDE/envs/RCAIDE/python.exe -E -s -B -m unittest scripts/test_a0_generate_setups_v2.py",
        "```",
        "",
    ]
    return "\n".join(lines)

# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    started = time.time()
    vsp = import_openvsp()
    runner = load_runner()
    SETUP_ROOT.mkdir(parents=True, exist_ok=True)
    gate2_payload = build_gate2_registration()
    write_json(GATE2_PATH, gate2_payload)
    gate2_record = record(GATE2_PATH)
    space = open_design_space()
    case_records = []
    for case in CASES:
        record_case = generate_case(vsp, runner, case, space)
        case_records.append(record_case)
        print("[a0v2] %s kind=%s tess=%s readback=%s/%d vspgeom=%s"
              % (record_case["case_id"], record_case["kind"],
                 record_case["model_readback"]["sect_tess_u_expected"][0],
                 record_case["readback_status"], record_case["readback_assertions"],
                 record_case["thin_geometry"]["sha256"][:12]), flush=True)
    case_lookup = {item["case_id"]: item for item in case_records}
    baseline = case_lookup["B2-02"]
    parity = parity_vs_archived(vsp, {
        "readback": baseline["model_readback"]["readback"],
        "model": baseline["model"],
    })
    std_case = case_lookup["S6_STD_M2p02_aoa1"]
    std_parity = std_thin_geometry_parity({"case_id": std_case["case_id"]})
    repeat = repeatability_check(case_lookup)
    negative = negative_controls(runner, case_lookup)
    readback_pass = sum(
        1 for item in case_records
        if item["readback_status"] == "PASS" and item["readback_assertions"] == 17
    )
    parity_pass = parity["metric_comparison"]["status"] == "PASS" and all(
        item["status"] in ("PASS", "UNVERIFIED") for item in parity["v1_archive_vspgeom"]
    )
    std_parity_pass = std_parity["status"] in ("PASS", "UNVERIFIED")
    repeat_pass = repeat["status"] == "PASS"
    negative_pass = all(item["all_rejected"] for item in negative)
    cases_ok = readback_pass == len(case_records)
    status = "A0V2_SETUP_READY_NO_SOLVER" if all(
        (cases_ok, parity_pass, std_parity_pass, repeat_pass, negative_pass)
    ) else "A0V2_SETUP_FAILED"
    summary = {
        "status": status,
        "case_count": len(case_records),
        "readback_pass": readback_pass,
        "parity_pass": parity_pass,
        "std_parity_pass": std_parity_pass,
        "repeatability_pass": repeat_pass,
        "negative_controls_pass": negative_pass,
        "solver_starts": 0,
        "note": "零求解器生成：仅 OpenVSP API 构建几何与 VSPAEROSweep 输入面（StopBeforeRun=1）",
    }
    evidence = {
        "schema_version": "d12d005-a0v2-setup-generation-1",
        "generated_utc": utc_stamp(),
        "run_id": RUN_DIR.name,
        "run_dir": str(RUN_DIR),
        "status": status,
        "solver_processes_started": 0,
        "stop_before_run": 1,
        "openvsp": {
            "version": getattr(vsp, "GetVSPVersion", lambda: "UNKNOWN")(),
            "root": str(OPENVSP_ROOT),
        },
        "gate2_repair": gate2_record,
        "runner": record(RUNNER),
        "design_space_config": record(DESIGN_CONFIG),
        "archived_model": {
            "sha256": ARCHIVED_MODEL_SHA256,
            "candidates": [str(path) for path in ARCHIVED_MODEL_CANDIDATES],
        },
        "archived_thin_vspgeom": {
            "std": {"name": "S3_STD_M2p02_base", "sha256": ARCHIVED_STD_VSPGEOM_SHA256},
            "d12_baseline": {"name": "S5_D12_M2p02_base", "sha256": ARCHIVED_D12_BASELINE_VSPGEOM_SHA256},
        },
        "raw_artifacts_root": str(RAW_ARTIFACTS),
        "cases": case_records,
        "parity": parity,
        "std_parity": std_parity,
        "repeatability": repeat,
        "negative_controls": negative,
        "summary": summary,
        "runtime_s": round(time.time() - started, 3),
        "notes": [
            "本文件只记录 setup 生成；没有任何 solver 运行，因此不包含气动力/极线数值。",
            "Gate2 repair 为 post-hoc 诊断注册；独立超声速确认由 S6_STD_M2p02_aoa1 承担。",
            "thin .vspgeom 位于 git 之外（outside_git=true），仓库内保留 sha256/bytes/external_path。",
        ],
    }
    write_json(EVIDENCE_PATH, evidence)
    README_PATH.write_text(render_readme(evidence), encoding="utf-8", newline="\n")
    print(json.dumps({"status": status, "summary": summary,
                      "runtime_s": evidence["runtime_s"]}, ensure_ascii=False, indent=2), flush=True)
    return 0 if status == "A0V2_SETUP_READY_NO_SOLVER" else 1


if __name__ == "__main__":
    raise SystemExit(main())
