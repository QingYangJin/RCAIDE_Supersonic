"""P4 元学习合成任务族（F-QE / F-LIN / F-NC / F-MF）。

本模块只做解析、可复现的合成元学习任务构造，不导入/不调用任何真实
RCAIDE Mission、SU2、VSPAERO、OpenVSP 求解器（physical_call_count = 0）。

设计依据：docs/planning/p4_meta_learning_design_20261102.md v1.1 §4/§5.1/§6。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .data_contract import CONSTRAINT_NAMES

__all__ = [
    "TaskFamilyError",
    "DESIGN_DIM",
    "DESIGN_NAMES",
    "DESIGN_LOWER",
    "DESIGN_UPPER",
    "CONTEXT_NAMES",
    "FAMILIES",
    "FORMULA_VERSION",
    "V2_FAMILY_ID",
    "V2_RADIUS_JITTER",
    "V2_RADIUS_MIN",
    "V2_RADIUS_MAX",
    "V3_FAMILY_ID",
    "V3_FORMULA_VERSION",
    "V3_FAMILY_SEED",
    "V3_RADIUS_JITTER",
    "V3_RADIUS_MIN",
    "V3_RADIUS_MAX",
    "V3_RADIUS_BASE_DEFAULT",
    "V3_TASK_ID_PREFIX",
    "V3_OOD_RADIUS_SCALE",
    "V3_OOD_CONTEXT_SHIFT",
    "V3_CONTEXT_COUPLING_SCALE",
    "V3_PARAM_DISTRIBUTIONS",
    "V4_HOLDOUT_SEED",
    "RESEEDED_SPLITS",
    "SYNTHETIC_CONSTRAINT_SLOTS",
    "TaskFamilyConfig",
    "SyntheticTask",
    "load_task_family_config",
    "build_task_family",
    "sample_designs",
    "family_fingerprint",
    "assert_reference_solutions",
    "serialize_task",
    "derive_seed",
    "S3_FAMILY_ID",
    "S3_FORMULA_VERSION",
    "S3_FAMILY_VERSION",
    "S3_FAMILY_SEED",
    "S3_HOLDOUT_SEED",
    "S3_TASK_ID_PREFIX",
    "S3_SPLITS",
    "S3_SPLIT_COUNTS",
    "S3_DESIGN_LOWER",
    "S3_DESIGN_UPPER",
    "S3_SUPPORT_POOL_SIZE",
    "S3_QUERY_SIZE",
    "S3_DELTA1_CANDIDATES",
    "S3_DELTA1_CANDIDATES_EXTENDED",
    "S3_M2_LOWER",
    "S3_M2_UPPER",
    "S3_CERT_TOL",
    "S3_REGRET_MIN",
    "S3_MIN_SUPPORT_FEASIBLE",
    "S3_MAX_SUPPORT_RETRIES",
    "S3_MAX_REFERENCE_REJECTIONS",
    "S3_OOD_DELTA1_SHIFT",
    "S3_OOD_B1_PERTURB",
    "S3_CALIBRATION_GRID_POINTS",
    "S3_CALIBRATION_MEDIAN_BAND",
    "S3_FAMILY_PACKAGE_SCHEMA_VERSION",
    "S3_REFERENCES_SEALED_SCHEMA_VERSION",
    "S3_PARAM_DISTRIBUTIONS",
    "S3ConflictTask",
    "s3_task_seed",
    "s3_ood_b1",
    "s3_certificate",
    "assert_s3_certificate",
    "s3_task_fingerprint",
    "s3_task_id",
    "build_s3_conflict_family",
    "s3_reference_record",
    "build_s3_references_sealed",
    "build_s3_family_package",
    "write_s3_json_canonical",
    "write_s3_family_package",
    "evaluate_s3_delta1_candidate",
    "check_s3_calibration_candidate",
    "summarize_s3_calibration",
]

DESIGN_DIM = 12
# 12 维设计空间顺序冻结（§2.1，与 configs/design_space_12d_lifting_surfaces.yaml 一致）
DESIGN_NAMES = (
    "wing_area", "aspect_ratio", "sweep_1", "sweep_2", "sweep_3",
    "span_location_2", "span_location_3", "chord_ratio_2", "chord_ratio_3",
    "tip_twist", "vertical_tail_area", "vertical_tail_sweep_delta",
)
DESIGN_LOWER = np.array([300.0, 1.5, 62.0, 40.0, 66.0, 0.35, 0.85, 0.30, 0.08, -4.0, 28.0, -10.0])
DESIGN_UPPER = np.array([420.0, 2.2, 72.0, 56.0, 76.0, 0.58, 0.98, 0.50, 0.20, 4.0, 40.0, 10.0])

CONTEXT_NAMES = ("context_1", "context_2")
FAMILIES = ("F-QE", "F-LIN", "F-NC", "F-MF", "F-QE-feasible-v2", "F-QE-feasible-v3")
FORMULA_VERSION = "p4-task-family-v1"
SYNTHETIC_CONSTRAINT_SLOTS = ("synth_c01", "synth_c02", "synth_c03")
# 合成槽位固定占用 10 项物理约束名的前 3 个（§4.4），其余 7 项未启用置 null
CONSTRAINT_SLOT_NAMES = CONSTRAINT_NAMES[: len(SYNTHETIC_CONSTRAINT_SLOTS)]

# 参考解断言容差（§4.2：|f(u*)-f*| <= 1e-10 * max(1, |f*|)）
REFERENCE_ABS_TOL = 1e-10
# 内层解析 λ 求根的几何容差（远小于参考断言容差）
_LAMBDA_TOL = 1e-13
_KKT_TOL = 1e-9
_MAX_REFERENCE_RESAMPLES = 200
# 负控制 shuffle seed 基数（§4.3：shuffle_seed = 20261102 + i）
NEGATIVE_CONTROL_SEED_BASE = 20261102
# context 进入目标的耦合系数（CONTRACT_AMBIGUITY A1，写入 family_fingerprint）
CONTEXT_COUPLING_SCALE = 0.5
# §4.2 F-NC：标准 Rastrigin 常数项 A*n = 10*12；在 u=c 处 f*=0
_NC_CONSTANT = 120.0
# OOD 协议（§4.3：context 中心整体平移 +0.2，r 缩小 30%）
OOD_CONTEXT_SHIFT = 0.2
OOD_RADIUS_SCALE = 0.7
# P4-M5 版本化可行域族（Issue #5 D-P4-002）：仅改约束半径分布，旧 F-QE 逐位不变。
V2_FAMILY_ID = "F-QE-feasible-v2"
V2_FORMULA_VERSION = "p4-task-family-v2"
# 任务级有界扰动：r_v2 = clip(radius_base*(1+0.15*z), r_min, r_max)，z~N(0,1) 由 task seed 派生
V2_RADIUS_JITTER = 0.15
V2_RADIUS_MIN = 0.20
V2_RADIUS_MAX = 1.20
# P4 路线A S1 任务族 v3（Issue #7 D-P4-003；task-198 / D-S0-2-05）：
# 与 v2 同解析族（F-QE 径向投影），只改参数分布/seed/task_id 命名空间，旧 v1/v2 逐位不变。
V3_FAMILY_ID = "F-QE-feasible-v3"
# 合同 §7 冻结的族版本字符串（Lead task-206 裁定 B01：不得再用简写 "v3"）
V3_FAMILY_VERSION = "p4ra-family-v3"
V3_FORMULA_VERSION = "p4-task-family-v3"
V3_FAMILY_SEED = 20261105
V3_RADIUS_JITTER = 0.20
V3_RADIUS_MIN = 0.15
V3_RADIUS_MAX = 1.10
V3_RADIUS_BASE_DEFAULT = 0.32
V3_TASK_ID_PREFIX = "p4ra-FQE3-v3-"
V3_OOD_RADIUS_SCALE = 0.75
V3_OOD_CONTEXT_SHIFT = 0.25
V3_CONTEXT_COUPLING_SCALE = 0.45
# v3 参数分布（进入 family_fingerprint 与 frozen_family，任何改动必须升 family_version）
V3_PARAM_DISTRIBUTIONS = {
    "c": "uniform(0.20, 0.80) per coordinate",
    "d": "clip(c + normal(0, 0.20), 0.10, 0.90)",
    "a": "loguniform(0.5, 4.0)",
    "w": "loguniform(0.5, 4.0)",
    "r": "clip(radius_base*(1+0.20*z), 0.15, 1.10); ood *= 0.75 then clipped",
    "b": "uniform(-0.9, 0.9)",
    "context": "uniform(0.6, 1.4)",
    "context_ood": "uniform(0.85, 1.65)",
}
# P4 路线A S1 v4（R-V4-01，H1 holdout 重播种，task-229）：
# 只对 meta_test/meta_test_ood 追加 holdout_seed 派生，meta_train/meta_validation/
# negative_control 的 seed 派生逐位不变（以此保证旧 task_fingerprint 不漂移）。
V4_HOLDOUT_SEED = 20261106
RESEEDED_SPLITS = ("meta_test", "meta_test_ood")

_PARAM_DISTRIBUTIONS = {
    "c": "uniform(0.15, 0.85) per coordinate",
    "d": "clip(c + normal(0, 0.25), 0.05, 0.95)",
    "a": "loguniform(0.5, 5.0)",
    "w": "loguniform(0.5, 5.0)",
    "r": "uniform(0.15, 0.45)",
    "b": "uniform(-1.0, 1.0)",
    "context": "uniform(0.6, 1.4)",
    "context_ood": "uniform(0.8, 1.6)",
    "F-LIN": "p,s ~ normal(0,1)/sqrt(12); slack ~ uniform(0.02,0.15)",
    "F-MF": "gamma ~ uniform(0.2,1.0); v ~ normal(0,1) normalized; delta ~ uniform(-0.5,0.5)",
}


class TaskFamilyError(ValueError):
    """任务族构造/参考解/采样失败（异常信息直接落盘，不伪造数值）。"""


def derive_seed(*parts: Any) -> int:
    """由字符串部件派生确定性非负 32 位 seed（同输入逐位复现）。"""
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:4], "big") % (2**31 - 1)


def _digest_text(*parts: Any) -> str:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _as_float_array(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (DESIGN_DIM,):
        raise TaskFamilyError(f"{name} 必须是 {DESIGN_DIM} 维向量，实际 shape={array.shape}")
    if not np.isfinite(array).all():
        raise TaskFamilyError(f"{name} 含非有限值")
    return array


def _validate_unit_designs(designs: Any) -> np.ndarray:
    array = np.asarray(designs, dtype=np.float64)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if array.ndim != 2 or array.shape[1] != DESIGN_DIM:
        raise TaskFamilyError(f"designs 必须是 (n, {DESIGN_DIM}) 数组，实际 shape={array.shape}")
    if not np.isfinite(array).all():
        raise TaskFamilyError("designs 含非有限值")
    if (array < -1e-12).any() or (array > 1.0 + 1e-12).any():
        raise TaskFamilyError("designs 必须位于单位超立方体 [0,1]^12（单位坐标，不是物理值）")
    return np.clip(array, 0.0, 1.0)


def _lhs_designs(count: int, seed: int) -> np.ndarray:
    """拉丁超立方采样，返回 [0,1)^12；同 seed 逐位复现。"""
    if type(count) is not int or count < 0:
        raise TaskFamilyError("count 必须是非负整数")
    if count == 0:
        return np.zeros((0, DESIGN_DIM), dtype=np.float64)
    try:
        from scipy.stats import qmc
    except ImportError as exc:  # pragma: no cover - scipy 在目标环境可用
        raise TaskFamilyError("缺少 scipy，无法进行拉丁超立方采样") from exc
    sampler = qmc.LatinHypercube(d=DESIGN_DIM, seed=int(seed))
    return np.asarray(sampler.random(count), dtype=np.float64)


def _sample_context(rng: np.random.Generator, ood: bool, family: str | None = None) -> dict[str, float]:
    if family == V3_FAMILY_ID:
        # v3 OOD context 偏移 0.25（D-S0-2 / 设计文档 §2.3）：U(0.85,1.65) = U(0.6,1.4)+0.25
        low, high = ((0.85, 1.65) if ood else (0.6, 1.4))
    else:
        low, high = ((0.8, 1.6) if ood else (0.6, 1.4))
    return {name: float(rng.uniform(low, high)) for name in CONTEXT_NAMES}


def _context_offset(context: Mapping[str, float], scale: float = CONTEXT_COUPLING_SCALE) -> float:
    """CONTRACT_AMBIGUITY A1：context 耦合 b_eff = b + scale*(context_1+context_2-2)。

    v3 使用 V3_CONTEXT_COUPLING_SCALE=0.45，v1/v2 保持 0.5（旧指纹逐位不变）。
    """
    return float(scale) * (float(context[CONTEXT_NAMES[0]]) + float(context[CONTEXT_NAMES[1]]) - 2.0)


@dataclass(frozen=True)
class TaskFamilyConfig:
    """合成任务族配置（§5.1，字段顺序冻结）。"""

    family_id: str
    design_dim: int
    context_names: tuple[str, ...]
    seed: int
    train_tasks: int
    validation_tasks: int
    test_tasks: int
    ood_tasks: int
    negative_control_tasks: int
    designs_per_task: int
    support_pool_size: int
    query_size: int
    reference_tolerance: float = REFERENCE_ABS_TOL
    # v2 版本化字段（尾部默认值保证旧配置/fingerprint 逐位不变，CONTRACT_AMBIGUITY A11）
    family_version: str = "v1"
    radius_base: float | None = None

    def __post_init__(self) -> None:
        if self.family_id not in FAMILIES:
            raise TaskFamilyError(f"未知 family_id: {self.family_id!r}，允许 {FAMILIES}")
        if self.design_dim != DESIGN_DIM:
            raise TaskFamilyError(f"design_dim 必须为 {DESIGN_DIM}")
        if tuple(self.context_names) != CONTEXT_NAMES:
            raise TaskFamilyError(f"context_names 必须为 {CONTEXT_NAMES}")
        for name in (
            "train_tasks", "validation_tasks", "test_tasks", "ood_tasks",
            "negative_control_tasks", "designs_per_task", "support_pool_size", "query_size",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise TaskFamilyError(f"{name} 必须是非负整数")
        if self.support_pool_size < 1 or self.query_size < 1:
            raise TaskFamilyError("support_pool_size 与 query_size 必须为正整数")
        if self.designs_per_task != self.support_pool_size + self.query_size:
            raise TaskFamilyError("designs_per_task 必须等于 support_pool_size + query_size")
        if self.negative_control_tasks > self.train_tasks:
            raise TaskFamilyError("negative_control_tasks 不能超过 meta-train 任务数（需由不同 meta-train 任务派生）")
        if not math.isfinite(self.reference_tolerance) or self.reference_tolerance <= 0:
            raise TaskFamilyError("reference_tolerance 必须是正有限数")
        if self.family_version not in ("v1", "v2", "v3", V3_FAMILY_VERSION):
            raise TaskFamilyError(
                f"family_version 必须是 v1/v2/v3/{V3_FAMILY_VERSION}，实际 {self.family_version!r}"
            )
        if self.family_id == V3_FAMILY_ID:
            if self.family_version != V3_FAMILY_VERSION:
                raise TaskFamilyError(
                    f"{V3_FAMILY_ID} 必须显式声明 family_version={V3_FAMILY_VERSION!r}"
                )
            if self.radius_base is None:
                raise TaskFamilyError(f"{V3_FAMILY_ID} 必须提供 radius_base（校准后冻结）")
            if not math.isfinite(float(self.radius_base)) or not (0.05 < float(self.radius_base) <= 2.0):
                raise TaskFamilyError(f"radius_base 必须在 (0.05, 2.0]，实际 {self.radius_base!r}")
        elif self.family_id == V2_FAMILY_ID:
            if self.family_version != "v2":
                raise TaskFamilyError(f"{V2_FAMILY_ID} 必须显式声明 family_version='v2'")
            if self.radius_base is None:
                raise TaskFamilyError(f"{V2_FAMILY_ID} 必须提供 radius_base（校准后冻结）")
            if not math.isfinite(float(self.radius_base)) or not (0.05 < float(self.radius_base) <= 2.0):
                raise TaskFamilyError(f"radius_base 必须在 (0.05, 2.0]，实际 {self.radius_base!r}")
        else:
            if self.family_version != "v1":
                raise TaskFamilyError(f"未版本化任务族 {self.family_id!r} 只能使用 family_version='v1'")
            if self.radius_base is not None:
                raise TaskFamilyError("radius_base 仅适用于 F-QE-feasible-v2/v3，旧族必须为 None")


def default_task_family_config(**overrides: Any) -> TaskFamilyConfig:
    """默认配置：F-QE，60/20/20/10/10（§4.3 规模）。"""
    base: dict[str, Any] = dict(
        family_id="F-QE", design_dim=DESIGN_DIM, context_names=CONTEXT_NAMES,
        seed=20261102, train_tasks=60, validation_tasks=20, test_tasks=20,
        ood_tasks=10, negative_control_tasks=10, support_pool_size=128,
        query_size=64, designs_per_task=192, reference_tolerance=REFERENCE_ABS_TOL,
    )
    base.update(overrides)
    return TaskFamilyConfig(**base)


_CONFIG_FIELDS = tuple(TaskFamilyConfig.__dataclass_fields__)


def load_task_family_config(path: Path | None = None) -> TaskFamilyConfig:
    """加载任务族配置；path=None 返回默认 F-QE 60/20/20/10/10 配置。"""
    if path is None:
        return default_task_family_config()
    config_path = Path(path)
    if not config_path.is_file():
        raise TaskFamilyError(f"任务族配置文件不存在: {config_path}")
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TaskFamilyError(f"任务族配置无法解析: {config_path}") from exc
    if not isinstance(payload, dict):
        raise TaskFamilyError("任务族配置必须是 JSON 对象")
    unknown = set(payload) - set(_CONFIG_FIELDS)
    if unknown:
        raise TaskFamilyError(f"任务族配置含未知字段: {sorted(unknown)}")
    if "context_names" in payload:
        payload["context_names"] = tuple(payload["context_names"])
    return TaskFamilyConfig(**payload)


def family_fingerprint(config: TaskFamilyConfig) -> str:
    """任务族指纹：配置 + 公式版本 + 参数分布 + context 耦合 + OOD/负控制协议。"""
    payload = {
        "formula_version": FORMULA_VERSION,
        "config": {
            "family_id": config.family_id,
            "design_dim": config.design_dim,
            "context_names": list(config.context_names),
            "seed": config.seed,
            "train_tasks": config.train_tasks,
            "validation_tasks": config.validation_tasks,
            "test_tasks": config.test_tasks,
            "ood_tasks": config.ood_tasks,
            "negative_control_tasks": config.negative_control_tasks,
            "designs_per_task": config.designs_per_task,
            "support_pool_size": config.support_pool_size,
            "query_size": config.query_size,
            "reference_tolerance": config.reference_tolerance,
        },
        "design_names": list(DESIGN_NAMES),
        "design_lower": [float(v) for v in DESIGN_LOWER],
        "design_upper": [float(v) for v in DESIGN_UPPER],
        "param_distributions": _PARAM_DISTRIBUTIONS,
        "context_coupling": {
            "scale": CONTEXT_COUPLING_SCALE,
            "formula": "b_eff = b + scale*(context_1 + context_2 - 2.0)",
        },
        "ood_protocol": {
            "context_shift": OOD_CONTEXT_SHIFT,
            "radius_scale": OOD_RADIUS_SCALE,
        },
        "negative_control_protocol": {
            "pseudo_task_id": 'NC-<sha1("negative_control|" + source_task_id + "|" + shuffle_seed)[:10]>',
            "shuffle_seed_base": NEGATIVE_CONTROL_SEED_BASE,
            "scope": "objective/constraints 与 design 的配对，不改 context/params",
        },
        "synthetic_constraint_slots": list(SYNTHETIC_CONSTRAINT_SLOTS),
    }
    # v2 版本化：只在 v2 配置上追加块，保证旧 F-QE 指纹逐位不变（M5 回归测试锁定）。
    if config.family_version == "v2":
        payload["formula_version"] = V2_FORMULA_VERSION
        payload["config"]["family_version"] = "v2"
        payload["config"]["radius_base"] = float(config.radius_base)
        payload["v2"] = {
            "family_id": V2_FAMILY_ID,
            "formula": {
                "objective": "b_eff + sum_i a_i*(u_i-c_i)^2",
                "constraint": "sum_i w_i*(u_i-c_i)^2 - r_v2^2 <= 0",
                "d": "c",
            },
            "radius_mapping": {
                "formula": "clip(radius_base*(1+jitter*z), min, max)",
                "jitter": V2_RADIUS_JITTER,
                "min": V2_RADIUS_MIN,
                "max": V2_RADIUS_MAX,
                "z": "normal(0,1) from task seed",
                "ood_radius_scale": OOD_RADIUS_SCALE,
            },
            "reference_kind": "ANALYTIC_RADIAL_PROJECTION",
        }
    elif config.family_version == V3_FAMILY_VERSION:
        # v3 版本化：独立 formula_version/分布/耦合/OOD/命名空间（设计文档 §4.1）
        payload["formula_version"] = V3_FORMULA_VERSION
        payload["config"]["family_version"] = V3_FAMILY_VERSION
        payload["config"]["radius_base"] = float(config.radius_base)
        payload["design_bounds"] = [[float(lo), float(hi)] for lo, hi in zip(DESIGN_LOWER, DESIGN_UPPER)]
        payload["param_distributions"] = dict(V3_PARAM_DISTRIBUTIONS)
        payload["context_coupling"] = {
            "scale": V3_CONTEXT_COUPLING_SCALE,
            "formula": "b_eff = b + scale*(context_1 + context_2 - 2.0)",
        }
        payload["ood_protocol"] = {
            "context_shift": V3_OOD_CONTEXT_SHIFT,
            "radius_scale": V3_OOD_RADIUS_SCALE,
        }
        payload["task_id_namespace"] = V3_TASK_ID_PREFIX
        payload["v3"] = {
            "family_id": V3_FAMILY_ID,
            "family_seed": int(config.seed),
            "formula": {
                "objective": "b_eff + sum_i a_i*(u_i-c_i)^2",
                "constraint": "sum_i w_i*(u_i-c_i)^2 - r_v3^2 <= 0",
                "d": "c",
            },
            "radius_mapping": {
                "formula": "clip(radius_base*(1+jitter*z), min, max)",
                "jitter": V3_RADIUS_JITTER,
                "min": V3_RADIUS_MIN,
                "max": V3_RADIUS_MAX,
                "z": "normal(0,1) from task seed",
                "ood_radius_scale": V3_OOD_RADIUS_SCALE,
            },
            "reference_kind": "ANALYTIC_RADIAL_PROJECTION",
        }
    return _digest_text(_canonical_json(payload))


# ---------------------------------------------------------------------------
# 参数采样
# ---------------------------------------------------------------------------

def _sample_common_params(
    rng: np.random.Generator, family: str, ood: bool, radius_base: float | None = None
) -> dict[str, Any]:
    if family == V3_FAMILY_ID:
        # v3 独立采样路径（D-S0-2-05 / 设计文档 §2.3）；绘制顺序固定以保证逐位复现。
        if radius_base is None:
            raise TaskFamilyError(f"{V3_FAMILY_ID} 采样必须提供 radius_base")
        c = rng.uniform(0.20, 0.80, size=DESIGN_DIM)
        d = np.clip(c + rng.normal(0.0, 0.20, size=DESIGN_DIM), 0.10, 0.90)
        a = np.exp(rng.uniform(math.log(0.5), math.log(4.0), size=DESIGN_DIM))
        w = np.exp(rng.uniform(math.log(0.5), math.log(4.0), size=DESIGN_DIM))
        z = float(rng.normal())
        r = float(np.clip(float(radius_base) * (1.0 + V3_RADIUS_JITTER * z), V3_RADIUS_MIN, V3_RADIUS_MAX))
        if ood:
            r = float(np.clip(r * V3_OOD_RADIUS_SCALE, V3_RADIUS_MIN, V3_RADIUS_MAX))
        b = float(rng.uniform(-0.9, 0.9))
        params: dict[str, Any] = {
            "c": [float(v) for v in c],
            "d": [float(v) for v in d],
            "a": [float(v) for v in a],
            "w": [float(v) for v in w],
            "r": r,
            "b": b,
            "constraint_slots": list(CONSTRAINT_SLOT_NAMES[:1]),
        }
        return params
    c = rng.uniform(0.15, 0.85, size=DESIGN_DIM)
    d = np.clip(c + rng.normal(0.0, 0.25, size=DESIGN_DIM), 0.05, 0.95)
    a = np.exp(rng.uniform(math.log(0.5), math.log(5.0), size=DESIGN_DIM))
    w = np.exp(rng.uniform(math.log(0.5), math.log(5.0), size=DESIGN_DIM))
    if family == V2_FAMILY_ID:
        if radius_base is None:
            raise TaskFamilyError(f"{V2_FAMILY_ID} 采样必须提供 radius_base")
        # 任务级有界扰动（§计划 1.1），z 由 task seed 派生 → 逐位可复现
        z = float(rng.normal())
        r = float(np.clip(float(radius_base) * (1.0 + V2_RADIUS_JITTER * z), V2_RADIUS_MIN, V2_RADIUS_MAX))
    else:
        r = float(rng.uniform(0.15, 0.45))
    if ood:
        r *= OOD_RADIUS_SCALE
    if family == V2_FAMILY_ID:
        r = float(np.clip(r, V2_RADIUS_MIN, V2_RADIUS_MAX))
    b = float(rng.uniform(-1.0, 1.0))
    params: dict[str, Any] = {
        "c": [float(v) for v in c],
        "d": [float(v) for v in d],
        "a": [float(v) for v in a],
        "w": [float(v) for v in w],
        "r": r,
        "b": b,
    }
    if family == "F-LIN":
        p = rng.normal(0.0, 1.0, size=DESIGN_DIM) / math.sqrt(DESIGN_DIM)
        s = rng.normal(0.0, 1.0, size=DESIGN_DIM) / math.sqrt(DESIGN_DIM)
        u0 = np.clip(c + rng.normal(0.0, 0.10, size=DESIGN_DIM), 0.10, 0.90)
        slack_p = float(rng.uniform(0.02, 0.15))
        slack_s = float(rng.uniform(0.02, 0.15))
        params.update(
            p=[float(v) for v in p],
            s=[float(v) for v in s],
            q=float(np.dot(p, u0) + slack_p),
            t=float(np.dot(s, u0) + slack_s),
        )
    elif family == "F-MF":
        gamma = float(rng.uniform(0.2, 1.0))
        v = rng.normal(0.0, 1.0, size=DESIGN_DIM)
        norm = float(np.linalg.norm(v))
        if norm <= 1e-12:
            v = np.ones(DESIGN_DIM)
            norm = float(np.linalg.norm(v))
        params.update(
            gamma=gamma,
            v=[float(value / norm) for value in v],
            delta=float(rng.uniform(-0.5, 0.5)),
        )
    params["constraint_slots"] = list(CONSTRAINT_SLOT_NAMES[: (1 if family != "F-LIN" else 2)])
    return params


def _make_task(
    config: TaskFamilyConfig,
    split: str,
    index: int,
    ood: bool,
    *,
    holdout_seed: int | None = None,
) -> SyntheticTask:
    """生成单个任务：拒绝采样直到参考解落在 [0,1]^12 且参考断言通过。

    R-V4-01：holdout_seed 仅对 RESEEDED_SPLITS 追加进 seed 派生；其余 split 走
    原派生路径（逐位不变），从而 meta_train/meta_validation/negative_control 的
    task_id/params/task_fingerprint 与旧 v3 包保持一致。
    """
    family = config.family_id
    last_error: Exception | None = None
    for attempt in range(_MAX_REFERENCE_RESAMPLES + 1):
        if holdout_seed is not None and split in RESEEDED_SPLITS:
            seed = derive_seed(
                family, split, index, attempt, config.seed, "holdout", holdout_seed
            )
        else:
            seed = derive_seed(family, split, index, attempt, config.seed)
        rng = np.random.default_rng(seed)
        params = _sample_common_params(rng, family, ood, getattr(config, "radius_base", None))
        if family == V2_FAMILY_ID:
            # 版本化任务参数（进入 task_id canonical json，便于审计与逐位复现）
            params["family_version"] = "v2"
            params["radius_base"] = float(config.radius_base)
            params["radius_jitter"] = V2_RADIUS_JITTER
            params["radius_bounds"] = [V2_RADIUS_MIN, V2_RADIUS_MAX]
        if family == V3_FAMILY_ID:
            # v3 版本化任务参数（进入 task_id canonical json/fingerprint，便于审计与逐位复现）
            params["family_version"] = V3_FAMILY_VERSION
            params["formula_version"] = V3_FORMULA_VERSION
            params["radius_base"] = float(config.radius_base)
            params["radius_jitter"] = V3_RADIUS_JITTER
            params["radius_bounds"] = [V3_RADIUS_MIN, V3_RADIUS_MAX]
        params["support_pool_size"] = config.support_pool_size
        params["query_size"] = config.query_size
        context = _sample_context(rng, ood, family)
        probe = SyntheticTask("REFERENCE_PROBE", split, family, context, params, seed)
        try:
            reference = probe.reference()
        except TaskFamilyError as exc:
            last_error = exc
            continue
        u_star = np.asarray(reference["u_star"], dtype=np.float64)
        if not _box_ok(u_star):
            last_error = TaskFamilyError("参考解越出单位超立方体")
            continue
        params["reference_rejections"] = attempt
        params["reference_kind"] = str(reference["reference_kind"])
        params["reference_kkt_residual"] = float(reference.get("kkt_residual", 0.0))
        task_id = hashlib.sha1(
            f"{family}|{_canonical_json(params)}|{seed}".encode("utf-8")
        ).hexdigest()[:12]
        return SyntheticTask(task_id=task_id, split=split, family=family, context=context, params=params, seed=seed)
    raise TaskFamilyError(
        f"任务族 {family} 在 {_MAX_REFERENCE_RESAMPLES} 次拒绝采样后仍无有效参考解: {last_error}"
    )


def _derive_negative_control(source: SyntheticTask, shuffle_seed: int) -> SyntheticTask:
    """由 meta-train 任务派生负控制伪任务（§4.3：仅打乱 objective/constraints 与 design 配对）。"""
    digest = hashlib.sha1(
        f"negative_control|{source.task_id}|{shuffle_seed}".encode("utf-8")
    ).hexdigest()
    pseudo_task_id = "NC-" + digest[:10]
    pool_size = source.support_pool_size + source.query_size
    rng = np.random.default_rng(derive_seed(pseudo_task_id, shuffle_seed))
    permutation = [int(value) for value in rng.permutation(pool_size)]
    params: dict[str, Any] = {
        "constraint_slots": list(source.enabled_constraint_names),
        "support_pool_size": source.support_pool_size,
        "query_size": source.query_size,
        "reference_rejections": 0,
        "source_task_id": source.task_id,
        "source_family": source.family,
        "source_context": dict(source.context),
        "source_params": dict(source.params),
        "source_seed": source.seed,
        "shuffle_seed": int(shuffle_seed),
        "permutation": permutation,
    }
    seed = derive_seed("negative_control", source.task_id, shuffle_seed)
    return SyntheticTask(
        task_id=pseudo_task_id,
        split="negative_control",
        family=source.family,
        context=dict(source.context),
        params=params,
        seed=seed,
    )


def build_task_family(
    config: TaskFamilyConfig, *, holdout_seed: int | None = None
) -> list[SyntheticTask]:
    """构造任务族全部五个集合（meta_train/meta_validation/meta_test/meta_test_ood/negative_control）。

    顺序：meta_train -> meta_validation -> meta_test -> meta_test_ood -> negative_control；
    OOD 任务使用平移后的 context 中心并把 r 缩小 30%（§4.3），负控制由前
    negative_control_tasks 个不同 meta-train 任务派生，五集合 task_id 两两互斥。

    R-V4-01（task-229）：holdout_seed 非 None 时只对 meta_test/meta_test_ood 追加
    holdout 重播种；meta_train/meta_validation/negative_control 逐位不变。
    """
    if not isinstance(config, TaskFamilyConfig):
        raise TaskFamilyError("build_task_family 需要 TaskFamilyConfig")
    if holdout_seed is not None:
        if type(holdout_seed) is not int or holdout_seed < 0:
            raise TaskFamilyError(f"holdout_seed 必须是非负整数，实际 {holdout_seed!r}")
        if holdout_seed > 2**31 - 1:
            raise TaskFamilyError("holdout_seed 超出 32 位范围")
        if config.family_id != V3_FAMILY_ID:
            raise TaskFamilyError("holdout_seed 只适用于 F-QE-feasible-v3 数学族（R-V4-01）")
    tasks: list[SyntheticTask] = []
    plan = (
        ("meta_train", config.train_tasks, False),
        ("meta_validation", config.validation_tasks, False),
        ("meta_test", config.test_tasks, False),
        ("meta_test_ood", config.ood_tasks, True),
    )
    splits: dict[str, list[SyntheticTask]] = {}
    for split, count, ood in plan:
        split_tasks = [
            _make_task(config, split, index, ood, holdout_seed=holdout_seed)
            for index in range(count)
        ]
        splits[split] = split_tasks
        tasks.extend(split_tasks)
    negative: list[SyntheticTask] = []
    for index in range(config.negative_control_tasks):
        source = splits["meta_train"][index]
        negative.append(_derive_negative_control(source, NEGATIVE_CONTROL_SEED_BASE + index))
    tasks.extend(negative)
    # 五集合 task_id 两两互斥（构造即断言，失败整族 FAILED）
    seen: dict[str, str] = {}
    for task in tasks:
        if task.task_id in seen:
            raise TaskFamilyError(f"任务 task_id 冲突: {task.task_id}（{seen[task.task_id]} 与 {task.split}）")
        seen[task.task_id] = task.split
    for task in tasks:
        if task.is_negative_control:
            continue
        support = task.support_designs()
        query = task.query_designs()
        if _rows_overlap(query, support, tol=1e-12):
            raise TaskFamilyError(f"任务 {task.task_id} 的 support/query 设计存在泄漏")
    return tasks


def sample_designs(task: SyntheticTask, count: int, kind: str, seed: int) -> np.ndarray:
    """采样设计（单位坐标 u∈[0,1]^12），全部显式 seed、同输入逐位复现。

    kind:
      - "lhs"：独立拉丁超立方（count 点）；
      - "support"：从 support 候选池按 seed 置换取 count 点（嵌套子集）；
      - "query"：从 query 设计集按 seed 置换取 count 点。
    """
    if not isinstance(task, SyntheticTask):
        raise TaskFamilyError("sample_designs 需要 SyntheticTask")
    if type(count) is not int or count < 0:
        raise TaskFamilyError("count 必须是非负整数")
    if kind == "lhs":
        return _lhs_designs(count, derive_seed(task.task_id, "lhs", seed))
    if kind == "support":
        pool = task.support_designs()
    elif kind == "query":
        pool = task.query_designs()
    else:
        raise TaskFamilyError(f"未知采样 kind: {kind!r}（允许 lhs/support/query）")
    if count > pool.shape[0]:
        raise TaskFamilyError(f"kind={kind} 的候选池只有 {pool.shape[0]} 点，无法取 {count} 点")
    import random as _random
    order = list(range(pool.shape[0]))
    _random.Random(f"{task.task_id}|{kind}|{int(seed)}").shuffle(order)
    return pool[np.array(order[:count], dtype=np.int64)]


def assert_reference_solutions(tasks: Sequence[SyntheticTask]) -> dict[str, float]:
    """断言每任务参考解满足 |f(u*)-f*|<=1e-10*max(1,|f*|)；失败抛 TaskFamilyError（整族 FAILED）。"""
    if not tasks:
        raise TaskFamilyError("assert_reference_solutions 需要至少一个任务")
    residuals: dict[str, float] = {}
    for task in tasks:
        if not isinstance(task, SyntheticTask):
            raise TaskFamilyError("assert_reference_solutions 需要 SyntheticTask 序列")
        if task.is_negative_control:
            continue
        reference = task.reference()
        residuals[task.task_id] = float(reference["assertion_residual"])
    return residuals


def serialize_task(task: SyntheticTask) -> dict[str, Any]:
    """任务 -> JSON 可序列化记录（写入 tasks.json）。"""
    payload = {
        "task_id": task.task_id,
        "split": task.split,
        "family": task.family,
        "context": dict(task.context),
        "params": task.params,
        "seed": task.seed,
        "constraint_slots": list(task.enabled_constraint_names),
    }
    return json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False))


# ---------------------------------------------------------------------------
# SyntheticTask
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SyntheticTask:
    """单个合成元学习任务（§5.1）。truth 为解析函数，reference 为可认证参考解。"""

    task_id: str
    split: str
    family: str
    context: Mapping[str, float]
    params: Mapping[str, Any]
    seed: int

    # -- 基本属性 ---------------------------------------------------------
    @property
    def enabled_constraint_names(self) -> tuple[str, ...]:
        slots = tuple(self.params.get("constraint_slots", ()))
        if not slots or any(name not in CONSTRAINT_SLOT_NAMES for name in slots):
            raise TaskFamilyError(f"任务 {self.task_id} 的约束槽位非法: {slots}")
        return slots

    @property
    def is_negative_control(self) -> bool:
        return self.split == "negative_control"

    @property
    def support_pool_size(self) -> int:
        return int(self.params["support_pool_size"])

    @property
    def query_size(self) -> int:
        return int(self.params["query_size"])

    # -- 数值辅助 ---------------------------------------------------------
    def _vector(self, key: str) -> np.ndarray:
        return _as_float_array(self.params[key], f"params.{key}")

    def _scalar(self, key: str) -> float:
        value = float(self.params[key])
        if not math.isfinite(value):
            raise TaskFamilyError(f"params.{key} 非有限")
        return value

    def _b_effective(self) -> float:
        scale = V3_CONTEXT_COUPLING_SCALE if self.family == V3_FAMILY_ID else CONTEXT_COUPLING_SCALE
        return self._scalar("b") + _context_offset(self.context, scale)

    # -- 参考解 -----------------------------------------------------------
    def reference(self) -> dict[str, Any]:
        """返回参考解 u*（单位坐标）/ f* / reference_kind / assertion_residual。"""
        if self.is_negative_control:
            raise TaskFamilyError("负控制伪任务没有参考解（label-shuffle 破坏解析结构）")
        family = self.family
        if family in (V2_FAMILY_ID, V3_FAMILY_ID):
            return self._reference_feasible_v2()
        if family == "F-QE":
            return self._reference_quadratic_ellipsoid()
        if family == "F-LIN":
            return self._reference_linear()
        if family == "F-NC":
            return self._reference_rastrigin()
        if family == "F-MF":
            return self._reference_multifidelity()
        raise TaskFamilyError(f"未知 family: {family!r}")

    def _assert_reference(self, u_star: np.ndarray, f_star: float, kind: str,
                          extra: dict[str, Any] | None = None) -> dict[str, Any]:
        labels = self.truth(np.asarray(u_star, dtype=np.float64).reshape(1, -1))
        f_truth = float(labels["objective"][0])
        residual = abs(f_truth - f_star)
        limit = REFERENCE_ABS_TOL * max(1.0, abs(f_star))
        if residual > limit:
            raise TaskFamilyError(
                f"任务 {self.task_id} 参考解断言失败: |f(u*)-f*|={residual:.3e} > {limit:.3e}"
            )
        constraints = {
            name: float(labels[name][0]) for name in self.enabled_constraint_names
        }
        result = {
            "u_star": u_star.astype(np.float64),
            "objective_star": float(f_star),
            "reference_kind": kind,
            "assertion_residual": float(residual),
            "constraints": constraints,
            "feasible": bool(labels["feasibility"][0]),
        }
        if extra:
            result.update(extra)
        return result

    # F-QE：二次目标 + 椭球约束（λ 一维求根，KKT 精确）
    def _reference_quadratic_ellipsoid(self) -> dict[str, Any]:
        c = self._vector("c")
        d = self._vector("d")
        a = self._vector("a")
        w = self._vector("w")
        r = self._scalar("r")
        b_eff = self._b_effective()
        u_star, lam, kkt = _trust_region_diag(c, a, d, w, r)
        f_star = b_eff + float(np.sum(a * (u_star - c) ** 2))
        return self._assert_reference(
            u_star, f_star, "KKT_CERTIFIED_ANALYTIC",
            {"lambda": float(lam), "kkt_residual": float(kkt)},
        )

    # F-QE-feasible-v2：d=c 的可行域版本（§M5 计划 1.1），径向投影 u*=c、f*=b_eff
    def _reference_feasible_v2(self) -> dict[str, Any]:
        c = self._vector("c")
        r = self._scalar("r")
        y_c = np.sqrt(self._vector("w")) * (c - c)
        norm = float(np.linalg.norm(y_c))
        u_star = c.copy()
        f_star = self._b_effective()
        return self._assert_reference(
            u_star, f_star, "ANALYTIC_RADIAL_PROJECTION",
            {"lambda": 0.0, "kkt_residual": 0.0, "radius": float(r), "radial_norm": norm},
        )

    # F-LIN：二次目标 + 2 线性约束（活动集枚举）
    def _reference_linear(self) -> dict[str, Any]:
        c = self._vector("c")
        a = self._vector("a")
        b_eff = self._b_effective()
        rows = [self._vector("p"), self._vector("s")]
        rhs = [self._scalar("q"), self._scalar("t")]
        best: tuple[float, np.ndarray, tuple[int, ...], float] | None = None
        for active in ((), (0,), (1,), (0, 1)):
            candidate = _solve_active_set_quadratic(c, a, rows, rhs, active)
            if candidate is None:
                continue
            u, lam, kkt = candidate
            if not _box_ok(u):
                continue
            g_values = [float(np.dot(rows[j], u) - rhs[j]) for j in range(2)]
            if any(g > 1e-9 for j, g in enumerate(g_values) if j not in active):
                continue
            if any(lam[j] < -1e-9 for j in range(len(active))):
                continue
            f_value = b_eff + float(np.sum(a * (u - c) ** 2))
            if best is None or f_value < best[0] - 1e-12:
                best = (f_value, u, active, kkt)
        if best is None:
            raise TaskFamilyError(f"任务 {self.task_id} 的 F-LIN 活动集枚举未找到可行参考解")
        f_star, u_star, active, kkt = best
        if kkt > _KKT_TOL:
            raise TaskFamilyError(f"任务 {self.task_id} 的 F-LIN KKT 残差 {kkt:.3e} 超限")
        return self._assert_reference(
            u_star, f_star, "ACTIVE_SET_ENUMERATION",
            {"active_set": list(active), "kkt_residual": float(kkt)},
        )

    # F-NC：Rastrigin + 球约束，f*=0, u*=c
    def _reference_rastrigin(self) -> dict[str, Any]:
        c = self._vector("c")
        u_star = c.copy()
        # §4.2 F-NC：f=120+Σ[(u-c)^2-10cos(2π(u-c))]，f*=0（不含 b 偏移）
        f_star = _NC_CONSTANT + float(
            np.sum((u_star - c) ** 2 - 10.0 * np.cos(2.0 * np.pi * (u_star - c)))
        )
        return self._assert_reference(
            u_star, f_star, "ANALYTIC_RASTRIGIN",
            {"kkt_residual": 0.0},
        )

    # F-MF：HF 目标 + 椭球约束（λ 一维求根，KKT 精确）
    def _reference_multifidelity(self) -> dict[str, Any]:
        c = self._vector("c")
        d = self._vector("d")
        a = self._vector("a")
        w = self._vector("w")
        r = self._scalar("r")
        gamma = self._scalar("gamma")
        v = self._vector("v")
        delta = self._scalar("delta")
        b_eff = self._b_effective()
        u_star, lam, kkt = _trust_region_linear(c, a, gamma * v, d, w, r)
        f_star = b_eff + float(
            np.sum(a * (u_star - c) ** 2) + gamma * np.dot(v, u_star - c) + delta
        )
        return self._assert_reference(
            u_star, f_star, "KKT_CERTIFIED_NUMERIC",
            {"lambda": float(lam), "kkt_residual": float(kkt)},
        )

    # -- 真值函数 ---------------------------------------------------------
    def truth(self, designs: Any, fidelity: str = "HF") -> dict[str, np.ndarray]:
        """解析真值；返回 objective / 启用约束 / feasibility（键为物理槽位名）。"""
        u = _validate_unit_designs(designs)
        if self.is_negative_control:
            return self._negative_control_truth(u)
        family = self.family
        names = self.enabled_constraint_names
        if family == "F-QE":
            objective, constraints = self._truth_quadratic_ellipsoid(u)
        elif family in (V2_FAMILY_ID, V3_FAMILY_ID):
            objective, constraints = self._truth_feasible_v2(u)
        elif family == "F-LIN":
            objective, constraints = self._truth_linear(u)
        elif family == "F-NC":
            objective, constraints = self._truth_rastrigin(u)
        elif family == "F-MF":
            if fidelity not in ("LF", "HF"):
                raise TaskFamilyError(f"未知 fidelity: {fidelity!r}")
            objective, constraints = self._truth_multifidelity(u, fidelity)
        else:
            raise TaskFamilyError(f"未知 family: {family!r}")
        result: dict[str, np.ndarray] = {"objective": objective}
        for name, values in zip(names, constraints):
            result[name] = values
        result["feasibility"] = np.all(
            np.stack([values <= 0.0 for values in constraints], axis=0), axis=0
        ) if constraints else np.ones(u.shape[0], dtype=bool)
        return result

    def _truth_quadratic_ellipsoid(self, u: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        c = self._vector("c")
        d = self._vector("d")
        a = self._vector("a")
        w = self._vector("w")
        r = self._scalar("r")
        objective = self._b_effective() + np.sum(a * (u - c) ** 2, axis=1)
        g = np.sum(w * (u - d) ** 2, axis=1) - r * r
        return objective, [g]

    def _truth_feasible_v2(self, u: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        c = self._vector("c")
        a = self._vector("a")
        w = self._vector("w")
        r = self._scalar("r")
        objective = self._b_effective() + np.sum(a * (u - c) ** 2, axis=1)
        g = np.sum(w * (u - c) ** 2, axis=1) - r * r
        return objective, [g]

    def _truth_linear(self, u: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        c = self._vector("c")
        a = self._vector("a")
        objective = self._b_effective() + np.sum(a * (u - c) ** 2, axis=1)
        g1 = u @ self._vector("p") - self._scalar("q")
        g2 = u @ self._vector("s") - self._scalar("t")
        return objective, [g1, g2]

    def _truth_rastrigin(self, u: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        c = self._vector("c")
        r = self._scalar("r")
        shift = u - c
        objective = _NC_CONSTANT + np.sum(shift**2 - 10.0 * np.cos(2.0 * np.pi * shift), axis=1)
        g = np.sum(shift**2, axis=1) - r * r
        return objective, [g]

    def _truth_multifidelity(self, u: np.ndarray, fidelity: str) -> tuple[np.ndarray, list[np.ndarray]]:
        c = self._vector("c")
        d = self._vector("d")
        a = self._vector("a")
        w = self._vector("w")
        r = self._scalar("r")
        b_eff = self._b_effective()
        delta_c = u - c
        low = b_eff + np.sum(a * delta_c**2, axis=1)
        if fidelity == "LF":
            objective = low
        else:
            gamma = self._scalar("gamma")
            v = self._vector("v")
            delta = self._scalar("delta")
            objective = low + gamma * (delta_c @ v) + delta
        g = np.sum(w * (u - d) ** 2, axis=1) - r * r
        return objective, [g]

    # -- 负控制 -----------------------------------------------------------
    def _negative_control_truth(self, u: np.ndarray) -> dict[str, np.ndarray]:
        source = self._source_task()
        pool = np.vstack([source.support_designs(), source.query_designs()])
        permutation = np.asarray(self.params["permutation"], dtype=np.int64)
        labels = source.truth(pool)
        shuffled = {name: values[permutation] for name, values in labels.items()}
        indices = _match_rows(u, pool)
        result = {name: values[indices] for name, values in shuffled.items()}
        result["feasibility"] = np.asarray(result["feasibility"], dtype=bool)
        return result

    def _source_task(self) -> "SyntheticTask":
        if not self.is_negative_control:
            raise TaskFamilyError("仅负控制伪任务包含 source 信息")
        source_params = dict(self.params["source_params"])
        source_context = dict(self.params["source_context"])
        return SyntheticTask(
            task_id=self.params["source_task_id"],
            split="meta_train",
            family=self.params["source_family"],
            context=source_context,
            params=source_params,
            seed=int(self.params["source_seed"]),
        )

    # -- 设计采样 ---------------------------------------------------------
    def _pool_designs(self, kind: str) -> np.ndarray:
        if self.is_negative_control:
            return self._source_task()._pool_designs(kind)
        if kind == "support":
            count = self.support_pool_size
        elif kind == "query":
            count = self.query_size
        else:
            raise TaskFamilyError(f"未知 design kind: {kind!r}（仅 support/query）")
        return _lhs_designs(count, derive_seed(self.task_id, kind, self.seed))

    def support_designs(self) -> np.ndarray:
        """support 候选池（默认 128 点，独立 LHS seed）。"""
        return self._pool_designs("support")

    def query_designs(self) -> np.ndarray:
        """query 设计（默认 64 点），并保证与 support 池精确不相交（容差 1e-12）。"""
        if self.is_negative_control:
            return self._source_task().query_designs()
        support = self.support_designs()
        attempt = 0
        while True:
            seed = derive_seed(self.task_id, "query", self.seed, attempt)
            candidate = _lhs_designs(self.query_size, seed)
            if not _rows_overlap(candidate, support, tol=1e-12):
                return candidate
            attempt += 1
            if attempt > 20:
                raise TaskFamilyError(f"任务 {self.task_id} 的 query 与 support 无法构造不相交设计")

    def support_subset(self, k_shot: int, seed: int) -> np.ndarray:
        """K-shot support：128 点池按 seed 置换后取前 K 点（K 增大只从池内取）。"""
        pool = self.support_designs()
        if type(k_shot) is not int or k_shot < 0 or k_shot > pool.shape[0]:
            raise TaskFamilyError(f"k_shot 必须在 [0,{pool.shape[0]}]，实际 {k_shot!r}")
        import random as _random
        order = list(range(pool.shape[0]))
        _random.Random(int(seed)).shuffle(order)
        selected = np.array(order[:k_shot], dtype=np.int64)
        return pool[selected]

    def reference_radial_projection(self) -> dict[str, Any]:
        """§4.2 文档给出的径向投影公式（仅在 A ∝ W 时等于真实最优解）。

        保留用于 CONTRACT_AMBIGUITY A5 的交叉校验；不作为训练/评估参考解。
        """
        if self.family != "F-QE":
            raise TaskFamilyError("径向投影公式仅用于 F-QE")
        c = self._vector("c")
        d = self._vector("d")
        w = self._vector("w")
        r = self._scalar("r")
        y_c = np.sqrt(w) * (c - d)
        norm = float(np.linalg.norm(y_c))
        if norm <= r:
            u_star = c.copy()
        else:
            u_star = d + (r / norm) * y_c / np.sqrt(w)
        return {"u_star": u_star, "radial_norm": norm, "r": r}


def _rows_overlap(left: np.ndarray, right: np.ndarray, tol: float) -> bool:
    for row in left:
        if np.min(np.max(np.abs(right - row), axis=1)) <= tol:
            return True
    return False


def _match_rows(designs: np.ndarray, pool: np.ndarray, tol: float = 1e-12) -> np.ndarray:
    indices = []
    for row in designs:
        distances = np.max(np.abs(pool - row), axis=1)
        index = int(np.argmin(distances))
        if distances[index] > tol:
            raise TaskFamilyError("负控制伪任务只接受其固定 design 池内的设计（label-shuffle 破坏了解析映射）")
        indices.append(index)
    return np.asarray(indices, dtype=np.int64)


def _box_ok(u: np.ndarray, tol: float = 1e-12) -> bool:
    return bool((u >= -tol).all() and (u <= 1.0 + tol).all())


def _ellipsoid_radius(u: np.ndarray, d: np.ndarray, w: np.ndarray) -> float:
    return float(np.sqrt(np.sum(w * (u - d) ** 2)))


def _solve_lambda(
    objective_center: np.ndarray,
    a: np.ndarray,
    linear: np.ndarray,
    d: np.ndarray,
    w: np.ndarray,
    r: float,
) -> tuple[np.ndarray, float]:
    """求解 min 0.5*u^T A u + A*center? 的统一闭式（见调用方）＋ 椭球约束。

    目标：f(u) = sum a_i (u_i - c_i)^2 + linear·u + const，A = diag(2a)。
    KKT：2a(u-c) + linear + 2*lambda*w*(u-d) = 0
        => u_i(lambda) = (2a_i c_i - linear_i + 2*lambda*w_i*d_i) / (2a_i + 2*lambda*w_i)
    约束：sum w_i (u_i-d_i)^2 = r^2（边界）。
    """
    def solve(lam: float) -> np.ndarray:
        return (2.0 * a * objective_center - linear + 2.0 * lam * w * d) / (2.0 * a + 2.0 * lam * w)

    u_low = solve(0.0)
    if _ellipsoid_radius(u_low, d, w) <= r:
        return u_low, 0.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        if _ellipsoid_radius(solve(hi), d, w) <= r:
            break
        hi *= 2.0
    else:  # pragma: no cover - 数值兜底
        raise TaskFamilyError("椭球约束 λ 上界搜索失败")
    for _ in range(400):
        mid = 0.5 * (lo + hi)
        if _ellipsoid_radius(solve(mid), d, w) > r:
            lo = mid
        else:
            hi = mid
        if hi - lo <= _LAMBDA_TOL * max(1.0, hi):
            break
    u_star = solve(hi)
    return u_star, hi


def _trust_region_diag(
    c: np.ndarray, a: np.ndarray, d: np.ndarray, w: np.ndarray, r: float
) -> tuple[np.ndarray, float, float]:
    """min sum a_i(u_i-c_i)^2 s.t. sum w_i(u_i-d_i)^2 <= r^2；返回 (u*, λ, KKT 残差)。"""
    u_star, lam = _solve_lambda(c, a, np.zeros(DESIGN_DIM), d, w, r)
    grad_f = 2.0 * a * (u_star - c)
    grad_g = 2.0 * w * (u_star - d)
    kkt = float(np.max(np.abs(grad_f + lam * grad_g)))
    return u_star, lam, kkt


def _trust_region_linear(
    c: np.ndarray, a: np.ndarray, linear: np.ndarray, d: np.ndarray, w: np.ndarray, r: float
) -> tuple[np.ndarray, float, float]:
    """min sum a_i(u_i-c_i)^2 + linear·u s.t. sum w_i(u_i-d_i)^2 <= r^2。"""
    u_star, lam = _solve_lambda(c, a, linear, d, w, r)
    grad_f = 2.0 * a * (u_star - c) + linear
    grad_g = 2.0 * w * (u_star - d)
    kkt = float(np.max(np.abs(grad_f + lam * grad_g)))
    return u_star, lam, kkt


def _solve_active_set_quadratic(
    c: np.ndarray,
    a: np.ndarray,
    rows: Sequence[np.ndarray],
    rhs: Sequence[float],
    active: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray, float] | None:
    """解等式约束 QP：min sum a_i(u_i-c_i)^2 s.t. P u = h（活动集活动约束）。"""
    if not active:
        lambda_values = np.zeros(0)
        return c.copy(), lambda_values, 0.0
    P = np.stack([rows[j] for j in active], axis=0)
    h = np.array([rhs[j] for j in active], dtype=np.float64)
    inv_a = 1.0 / (2.0 * a)
    gram = P @ (inv_a[:, None] * P.T)
    try:
        if abs(float(np.linalg.det(gram))) <= 1e-12:
            return None
        lambda_values = np.linalg.solve(gram, P @ c - h)
    except np.linalg.LinAlgError:
        return None
    u = c - inv_a * (P.T @ lambda_values)
    residual = float(np.max(np.abs(2.0 * a * (u - c) + P.T @ lambda_values)))
    return u, lambda_values, residual

# ===========================================================================
# S3：F-QE-conflict-v1 冲突任务族（计划 v1.2 §2.1/§2.2，M1 实现）
# ---------------------------------------------------------------------------
# 与旧 F-QE / F-QE-feasible-v2/v3 完全独立：新 family_id/formula_version/命名空间，
# 不改变任何旧族的采样、task_id、fingerprint 或 truth 路径（旧测试逐位锁定）。
# 族几何：f(u)=sum a_i (u_i-c_i)^2；g1(u)=b1.(u-c)+delta1 <= 0；
#          g2(u)=b2.(u-c)+delta2 <= 0，其中 delta2=-b2.(u*-c)-m2，u* 为 KKT 解析解。
# ===========================================================================
S3_FAMILY_ID = "F-QE-conflict-v1"
S3_FORMULA_VERSION = "polyhedral-v1"
S3_FAMILY_VERSION = "p4ra-s3-family-v1"
S3_FAMILY_SEED = 20261107
S3_HOLDOUT_SEED = 20261108
S3_TASK_ID_PREFIX = "p4ra-FQEC-v1-"
S3_SPLITS = (
    "meta_train",
    "meta_validation",
    "meta_test",
    "meta_test_ood",
    "meta_test_negative_control",
)
S3_SPLIT_COUNTS = {
    "meta_train": 60,
    "meta_validation": 20,
    "meta_test": 20,
    "meta_test_ood": 10,
    "meta_test_negative_control": 10,
}
S3_DESIGN_LOWER = 0.02
S3_DESIGN_UPPER = 0.98
S3_SUPPORT_POOL_SIZE = 128
S3_QUERY_SIZE = 64
S3_DELTA1_CANDIDATES = (0.20, 0.22, 0.25)
S3_DELTA1_CANDIDATES_EXTENDED = (0.18, 0.28, 0.30)
S3_M2_LOWER = 0.10
S3_M2_UPPER = 0.15
S3_CERT_TOL = 1e-12
S3_REGRET_MIN = 1e-6
S3_MIN_SUPPORT_FEASIBLE = 1
S3_MAX_SUPPORT_RETRIES = 10
S3_MAX_REFERENCE_REJECTIONS = 200
S3_OOD_DELTA1_SHIFT = 0.05
S3_OOD_B1_PERTURB = 0.30
S3_CALIBRATION_GRID_POINTS = 4096
S3_CALIBRATION_MEDIAN_BAND = (0.02, 0.50)
S3_NEGATIVE_CONTROL_SOURCE_SPLIT = "meta_test"
S3_NEGATIVE_CONTROL_SOURCE_COUNT = 10
S3_FAMILY_PACKAGE_SCHEMA_VERSION = "p4ra-s3-family-package-v1"
S3_REFERENCES_SEALED_SCHEMA_VERSION = "p4ra-s3-references-sealed-v1"

S3_PARAM_DISTRIBUTIONS = {
    "a": "exp(uniform(-0.5, 0.5)) per coordinate (12D)",
    "c": "uniform(0.30, 0.70) per coordinate (12D)",
    "b1": "normal(0,1)^12 normalized to unit vector",
    "b2": "normal(0,1)^12 normalized to unit vector",
    "delta1": "delta1_base (selected by calibration); meta_test_ood = delta1_base + 0.05",
    "m2": "uniform(0.10, 0.15); delta2 = -b2.(u*-c) - m2",
    "design_box": "[0.02, 0.98]^12 (unit coordinates)",
}

_S3_NUMERIC_PARAM_KEYS = ("a", "c", "b1", "b2", "delta1", "delta2", "m2")


def _s3_unit_norm(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if not math.isfinite(norm) or norm <= 1e-12:
        raise TaskFamilyError("S3 族方向向量范数为 0，无法归一化")
    return np.asarray(vector / norm, dtype=np.float64)


def _s3_lhs(count: int, seed: int) -> np.ndarray:
    """[0.02,0.98]^12 内的拉丁超立方采样（LHS 在 [0,1] 后线性缩放）。"""
    base = _lhs_designs(count, seed)
    return S3_DESIGN_LOWER + (S3_DESIGN_UPPER - S3_DESIGN_LOWER) * base


def s3_task_seed(split: str, index: int, split_seed: int, attempt: int = 0) -> int:
    """计划 §2.2 seed 公式；attempt>0 时追加 retry 域（同 attempt 逐位可复现）。"""
    if split not in S3_SPLITS:
        raise TaskFamilyError("未知 S3 split: " + repr(split))
    if type(index) is not int or index < 0:
        raise TaskFamilyError("index 必须是非负整数")
    if type(attempt) is not int or attempt < 0:
        raise TaskFamilyError("attempt 必须是非负整数")
    payload = (
        str(split) + "|" + S3_FAMILY_ID + "|" + S3_FORMULA_VERSION + "|"
        + str(index) + "|" + str(int(split_seed))
    )
    if attempt:
        payload += "|retry|" + str(attempt)
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2**31)


def s3_ood_b1(task_index: int, b1: np.ndarray, holdout_seed: int = S3_HOLDOUT_SEED) -> np.ndarray:
    """OOD：b1_ood = normalize(b1 + 0.30*e_rand)，e_rand 由 HOLDOUT_SEED|ood-direction|index 派生。"""
    rng = np.random.default_rng(derive_seed(holdout_seed, "ood-direction", int(task_index)))
    e_rand = _s3_unit_norm(np.asarray(rng.normal(0.0, 1.0, size=DESIGN_DIM), dtype=np.float64))
    return _s3_unit_norm(np.asarray(b1, dtype=np.float64) + S3_OOD_B1_PERTURB * e_rand)


def _s3_sample_numeric_params(
    rng: np.random.Generator,
    *,
    delta1_base: float,
    ood: bool,
    task_index: int,
    holdout_seed: int,
) -> dict[str, Any]:
    a = np.exp(np.asarray(rng.uniform(-0.5, 0.5, size=DESIGN_DIM), dtype=np.float64))
    c = np.asarray(rng.uniform(0.30, 0.70, size=DESIGN_DIM), dtype=np.float64)
    b1 = _s3_unit_norm(np.asarray(rng.normal(0.0, 1.0, size=DESIGN_DIM), dtype=np.float64))
    b2 = _s3_unit_norm(np.asarray(rng.normal(0.0, 1.0, size=DESIGN_DIM), dtype=np.float64))
    m2 = float(rng.uniform(S3_M2_LOWER, S3_M2_UPPER))
    delta1 = float(delta1_base) + (S3_OOD_DELTA1_SHIFT if ood else 0.0)
    if ood:
        b1 = s3_ood_b1(task_index, b1, holdout_seed)
    certificate = s3_certificate(a=a, c=c, b1=b1, b2=b2, delta1=delta1, m2=m2)
    return {
        "a": [float(v) for v in a],
        "c": [float(v) for v in c],
        "b1": [float(v) for v in b1],
        "b2": [float(v) for v in b2],
        "delta1": float(delta1),
        "delta2": float(certificate["delta2"]),
        "m2": float(m2),
    }


def s3_certificate(
    *,
    a: Any,
    c: Any,
    b1: Any,
    b2: Any,
    delta1: float,
    m2: float,
) -> dict[str, Any]:
    """解析 KKT 证书（计划 §2.1）：u*、lambda、S、f*、g1*、g2*、kkt 残差。"""
    a_arr = _as_float_array(a, "a")
    c_arr = _as_float_array(c, "c")
    b1_arr = _as_float_array(b1, "b1")
    b2_arr = _as_float_array(b2, "b2")
    if (a_arr <= 0.0).any():
        raise TaskFamilyError("a 必须逐坐标为正")
    if not (math.isfinite(float(delta1)) and float(delta1) > 0.0):
        raise TaskFamilyError("delta1 必须为正有限数")
    if not (math.isfinite(float(m2)) and float(m2) > 0.0):
        raise TaskFamilyError("m2 必须为正有限数")
    s_value = float(np.sum(b1_arr * b1_arr / a_arr))
    if not math.isfinite(s_value) or s_value <= 1e-12:
        raise TaskFamilyError("S=sum(b1^2/a) 非正，无法构造参考解")
    lam = float(delta1) / s_value
    u_star = c_arr - lam * (b1_arr / a_arr)
    f_star = float(delta1) * float(delta1) / s_value
    delta2 = float(-np.dot(b2_arr, u_star - c_arr) - float(m2))
    g1_star = float(np.dot(b1_arr, u_star - c_arr) + float(delta1))
    g2_star = float(np.dot(b2_arr, u_star - c_arr) + delta2)
    kkt = float(np.max(np.abs(2.0 * a_arr * (u_star - c_arr) + 2.0 * lam * b1_arr)))
    return {
        "u_star": u_star,
        "f_star": float(f_star),
        "g1_star": g1_star,
        "g2_star": g2_star,
        "lambda": lam,
        "S": s_value,
        "kkt_residual": kkt,
        "margin_m": float(m2),
        "conflict_ratio": float(delta1),
        "objective_regret": float(f_star),
        "delta1": float(delta1),
        "delta2": float(delta2),
    }


def assert_s3_certificate(certificate: Mapping[str, Any]) -> None:
    """证书断言（计划 §2.1）：box 严格内、|g1*|<=1e-12、kkt<=1e-12、|g2*+m2|<=1e-12、regret>1e-6。"""
    u_star = np.asarray(certificate["u_star"], dtype=np.float64)
    if u_star.shape != (DESIGN_DIM,):
        raise TaskFamilyError("S3 证书 u_star 维度错误")
    tol = S3_DESIGN_LOWER - 1e-15
    upper = S3_DESIGN_UPPER + 1e-15
    if (u_star <= tol).any() or (u_star >= upper).any():
        raise TaskFamilyError("S3 证书 u* 未严格位于 [0.02,0.98]^12 内")
    if abs(float(certificate["g1_star"])) > S3_CERT_TOL:
        raise TaskFamilyError("S3 证书 |g1(u*)| 超限")
    if float(certificate["kkt_residual"]) > S3_CERT_TOL:
        raise TaskFamilyError("S3 证书 KKT 残差超限")
    if abs(float(certificate["g2_star"]) + float(certificate["margin_m"])) > S3_CERT_TOL:
        raise TaskFamilyError("S3 证书 |g2(u*)+m2| 超限")
    m2 = float(certificate["margin_m"])
    if not (S3_M2_LOWER - 1e-12 <= m2 <= S3_M2_UPPER + 1e-12):
        raise TaskFamilyError("S3 证书 m2 越界")
    if float(certificate["objective_regret"]) <= S3_REGRET_MIN:
        raise TaskFamilyError("S3 证书 regret 必须 > 1e-6")
    if float(certificate["delta1"]) <= 0.0:
        raise TaskFamilyError("S3 证书 delta1 必须为正")


def _s3_truth_arrays(
    *,
    a: np.ndarray,
    c: np.ndarray,
    b1: np.ndarray,
    b2: np.ndarray,
    delta1: float,
    delta2: float,
    designs: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    u = _validate_unit_designs(designs)
    delta = u - c
    objective = np.sum(a * delta * delta, axis=1)
    g1 = delta @ b1 + float(delta1)
    g2 = delta @ b2 + float(delta2)
    return objective, g1, g2


@dataclass(frozen=True)
class S3ConflictTask:
    """S3 冲突族任务（与旧 SyntheticTask 独立；API 兼容 support_designs/query_designs/truth）。"""

    task_id: str
    split: str
    family: str
    formula_version: str
    params: Mapping[str, Any]
    seed: int
    context: Mapping[str, float]
    reference_kind: str
    source_task_id: str | None = None

    @property
    def is_negative_control(self) -> bool:
        return self.split == "meta_test_negative_control"

    @property
    def support_pool_size(self) -> int:
        return int(self.params["support_pool_size"])

    @property
    def query_size(self) -> int:
        return int(self.params["query_size"])

    @property
    def design_bounds(self) -> tuple[float, float]:
        return (S3_DESIGN_LOWER, S3_DESIGN_UPPER)

    def numeric_params(self) -> dict[str, Any]:
        return {key: self.params[key] for key in _S3_NUMERIC_PARAM_KEYS}

    def _vectors(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        return (
            _as_float_array(self.params["a"], "a"),
            _as_float_array(self.params["c"], "c"),
            _as_float_array(self.params["b1"], "b1"),
            _as_float_array(self.params["b2"], "b2"),
        )

    def _pool_designs(self, kind: str) -> np.ndarray:
        if kind == "support":
            count = self.support_pool_size
        elif kind == "query":
            count = self.query_size
        else:
            raise TaskFamilyError("未知 S3 design kind: " + repr(kind))
        return _s3_lhs(count, derive_seed(self.task_id, kind, self.seed))

    def support_designs(self) -> np.ndarray:
        if self.is_negative_control:
            # 计划 §2.2：负控制沿用来源 meta_test 任务的设计点，仅置换 query 标签行。
            return self._source_task().support_designs()
        return self._pool_designs("support")

    def query_designs(self) -> np.ndarray:
        if self.is_negative_control:
            return self._source_task().query_designs()
        support = self.support_designs()
        attempt = 0
        while True:
            seed = derive_seed(self.task_id, "query", self.seed, attempt)
            candidate = _s3_lhs(self.query_size, seed)
            if not _rows_overlap(candidate, support, tol=1e-12):
                return candidate
            attempt += 1
            if attempt > 20:
                raise TaskFamilyError("S3 任务 query 与 support 无法构造不相交设计")

    def support_subset(self, k_shot: int, seed: int) -> np.ndarray:
        pool = self.support_designs()
        if type(k_shot) is not int or k_shot < 0 or k_shot > pool.shape[0]:
            raise TaskFamilyError("k_shot 越界")
        import random as _random
        order = list(range(pool.shape[0]))
        _random.Random(int(seed)).shuffle(order)
        return pool[np.asarray(order[:k_shot], dtype=np.int64)]

    def truth(self, designs: Any, fidelity: str = "HF") -> dict[str, np.ndarray]:
        if fidelity != "HF":
            raise TaskFamilyError("S3 冲突族只提供 HF 解析真值")
        u = _validate_unit_designs(designs)
        if self.is_negative_control:
            source = self._source_task()
            base = source.truth(u, fidelity=fidelity)
            return self._negative_control_truth(u, base)
        a, c, b1, b2 = self._vectors()
        objective, g1, g2 = _s3_truth_arrays(
            a=a, c=c, b1=b1, b2=b2,
            delta1=float(self.params["delta1"]),
            delta2=float(self.params["delta2"]),
            designs=u,
        )
        feasible = (g1 <= 0.0) & (g2 <= 0.0)
        return {
            "objective": objective,
            "g1": g1,
            "g2": g2,
            "feasibility": feasible,
        }

    def _negative_control_truth(
        self,
        u: np.ndarray,
        base: Mapping[str, np.ndarray],
    ) -> dict[str, np.ndarray]:
        source = self._source_task()
        query_pool = source.query_designs()
        permutation = np.asarray(self.params["query_permutation"], dtype=np.int64)
        source_labels = source.truth(query_pool)
        source_objective = np.asarray(source_labels["objective"], dtype=np.float64)
        source_g1 = np.asarray(source_labels["g1"], dtype=np.float64)
        source_g2 = np.asarray(source_labels["g2"], dtype=np.float64)
        shuffled_objective = np.asarray(base["objective"], dtype=np.float64).copy()
        shuffled_g1 = np.asarray(base["g1"], dtype=np.float64).copy()
        shuffled_g2 = np.asarray(base["g2"], dtype=np.float64).copy()
        for query_index in range(query_pool.shape[0]):
            target_index = int(permutation[query_index])
            matches = np.where(np.max(np.abs(u - query_pool[query_index]), axis=1) <= 1e-12)[0]
            if matches.size:
                shuffled_objective[matches] = source_objective[target_index]
                shuffled_g1[matches] = source_g1[target_index]
                shuffled_g2[matches] = source_g2[target_index]
        feasible = (shuffled_g1 <= 0.0) & (shuffled_g2 <= 0.0)
        return {
            "objective": shuffled_objective,
            "g1": shuffled_g1,
            "g2": shuffled_g2,
            "feasibility": feasible,
        }

    def _source_task(self) -> "S3ConflictTask":
        if not self.is_negative_control:
            raise TaskFamilyError("仅负控制任务包含 source")
        source_params = dict(self.params["source_params"])
        source_params["support_pool_size"] = self.support_pool_size
        source_params["query_size"] = self.query_size
        return S3ConflictTask(
            task_id=self.params["source_task_id"],
            split=self.params["source_split"],
            family=S3_FAMILY_ID,
            formula_version=S3_FORMULA_VERSION,
            params=source_params,
            seed=int(self.params["source_seed"]),
            context=dict(self.params["source_context"]),
            reference_kind="POLYHEDRAL_KKT_CERTIFIED",
        )

    def reference(self) -> dict[str, Any]:
        if self.is_negative_control:
            raise TaskFamilyError("S3 负控制任务没有参考解（query 标签置换）")
        a, c, b1, b2 = self._vectors()
        certificate = s3_certificate(
            a=a, c=c, b1=b1, b2=b2,
            delta1=float(self.params["delta1"]),
            m2=float(self.params["m2"]),
        )
        assert_s3_certificate(certificate)
        labels = self.truth(np.asarray(certificate["u_star"], dtype=np.float64).reshape(1, -1))
        f_truth = float(labels["objective"][0])
        residual = abs(f_truth - float(certificate["f_star"]))
        if residual > REFERENCE_ABS_TOL * max(1.0, abs(float(certificate["f_star"]))):
            raise TaskFamilyError("S3 参考解断言失败（truth 与解析 f* 不一致）")
        result = dict(certificate)
        result["reference_kind"] = self.reference_kind
        result["assertion_residual"] = float(residual)
        result["task_id"] = self.task_id
        result["split"] = self.split
        return result

    def task_fingerprint(self) -> str:
        if self.is_negative_control:
            params: Mapping[str, Any] = {
                "source_task_id": self.source_task_id,
                "shuffle_seed": int(self.params["shuffle_seed"]),
                "reference_kind": self.reference_kind,
            }
        else:
            params = self.numeric_params()
        return s3_task_fingerprint(
            family_id=self.family,
            formula_version=self.formula_version,
            task_id=self.task_id,
            seed=self.seed,
            params=params,
        )


def s3_task_fingerprint(
    *,
    family_id: str,
    formula_version: str,
    task_id: str,
    seed: int,
    params: Mapping[str, Any],
) -> str:
    """计划 §6.1 task_fingerprint：canonical json 的 sha256 前 16 hex。"""
    payload = {
        "family_id": str(family_id),
        "formula_version": str(formula_version),
        "task_id": str(task_id),
        "seed": int(seed),
        "params": dict(params),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def s3_task_id(family_id: str, formula_version: str, params: Mapping[str, Any], seed: int) -> str:
    """计划 §2.2 task_id：sha1(family|formula|canonical(params)|seed) 前 16 hex。"""
    payload = (
        str(family_id) + "|" + str(formula_version) + "|"
        + _canonical_json(dict(params)) + "|" + str(int(seed))
    )
    return S3_TASK_ID_PREFIX + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _make_s3_task(
    *,
    split: str,
    index: int,
    delta1_base: float,
    split_seed: int,
    holdout_seed: int,
    support_pool_size: int,
    query_size: int,
) -> "S3ConflictTask":
    ood = split == "meta_test_ood"
    resample_support = split in ("meta_train", "meta_validation")
    support_retries = 0
    reference_rejections = 0
    last_error: Exception | None = None
    for attempt in range(S3_MAX_REFERENCE_REJECTIONS + 1):
        seed = s3_task_seed(split, index, split_seed, attempt)
        rng = np.random.default_rng(seed)
        try:
            numeric = _s3_sample_numeric_params(
                rng,
                delta1_base=delta1_base,
                ood=ood,
                task_index=index,
                holdout_seed=holdout_seed,
            )
            certificate = s3_certificate(
                a=numeric["a"],
                c=numeric["c"],
                b1=numeric["b1"],
                b2=numeric["b2"],
                delta1=numeric["delta1"],
                m2=numeric["m2"],
            )
            assert_s3_certificate(certificate)
        except TaskFamilyError as exc:
            last_error = exc
            reference_rejections += 1
            continue
        task_params: dict[str, Any] = dict(numeric)
        task_params["support_pool_size"] = int(support_pool_size)
        task_params["query_size"] = int(query_size)
        task_params["reference_kind"] = "POLYHEDRAL_KKT_CERTIFIED"
        task_params["reference_rejections"] = int(reference_rejections)
        task_params["support_retry_count"] = int(support_retries)
        task_params["degenerate_support"] = False
        task_params["ood_flag"] = 1.0 if ood else 0.0
        task_id = s3_task_id(S3_FAMILY_ID, S3_FORMULA_VERSION, numeric, seed)
        task = S3ConflictTask(
            task_id=task_id,
            split=split,
            family=S3_FAMILY_ID,
            formula_version=S3_FORMULA_VERSION,
            params=task_params,
            seed=seed,
            context={"ood_flag": 1.0 if ood else 0.0},
            reference_kind="POLYHEDRAL_KKT_CERTIFIED",
        )
        labels = task.truth(task.support_designs())
        feasible_count = int(np.asarray(labels["feasibility"], dtype=bool).sum())
        task_params["support_feasible_count"] = feasible_count
        if feasible_count < S3_MIN_SUPPORT_FEASIBLE:
            if resample_support and support_retries < S3_MAX_SUPPORT_RETRIES:
                support_retries += 1
                continue
            task_params["degenerate_support"] = True
        task_params["support_retry_count"] = int(support_retries)
        return task
    raise TaskFamilyError(
        "S3 任务构造在 " + str(S3_MAX_REFERENCE_REJECTIONS) + " 次拒绝采样后失败: " + repr(last_error)
    )


def build_s3_conflict_family(
    *,
    delta1_base: float,
    family_seed: int = S3_FAMILY_SEED,
    holdout_seed: int = S3_HOLDOUT_SEED,
    support_pool_size: int = S3_SUPPORT_POOL_SIZE,
    query_size: int = S3_QUERY_SIZE,
) -> list["S3ConflictTask"]:
    """构造 S3 五集合任务族（60/20/20/10/10），顺序与计划 §2.2 一致。"""
    if not (math.isfinite(float(delta1_base)) and float(delta1_base) > 0.0):
        raise TaskFamilyError("delta1_base 必须为正有限数")
    if type(support_pool_size) is not int or support_pool_size < 1:
        raise TaskFamilyError("support_pool_size 必须为正整数")
    if type(query_size) is not int or query_size < 1:
        raise TaskFamilyError("query_size 必须为正整数")
    split_seeds = {
        "meta_train": family_seed,
        "meta_validation": family_seed,
        "meta_test": holdout_seed,
        "meta_test_ood": holdout_seed,
    }
    tasks: list[S3ConflictTask] = []
    splits: dict[str, list[S3ConflictTask]] = {}
    for split in ("meta_train", "meta_validation", "meta_test", "meta_test_ood"):
        count = S3_SPLIT_COUNTS[split]
        split_tasks = [
            _make_s3_task(
                split=split,
                index=index,
                delta1_base=float(delta1_base),
                split_seed=split_seeds[split],
                holdout_seed=holdout_seed,
                support_pool_size=support_pool_size,
                query_size=query_size,
            )
            for index in range(count)
        ]
        splits[split] = split_tasks
        tasks.extend(split_tasks)
    negative: list[S3ConflictTask] = []
    for index in range(S3_SPLIT_COUNTS["meta_test_negative_control"]):
        source = splits[S3_NEGATIVE_CONTROL_SOURCE_SPLIT][index]
        negative.append(_derive_s3_negative_control(source, index))
    tasks.extend(negative)
    seen: dict[str, str] = {}
    for task in tasks:
        if task.task_id in seen:
            raise TaskFamilyError("S3 task_id 冲突: " + task.task_id)
        seen[task.task_id] = task.split
    for task in tasks:
        if task.is_negative_control:
            continue
        support = task.support_designs()
        query = task.query_designs()
        if _rows_overlap(query, support, tol=1e-12):
            raise TaskFamilyError("S3 任务 support/query 存在泄漏: " + task.task_id)
    return tasks


def _derive_s3_negative_control(source: S3ConflictTask, index: int) -> "S3ConflictTask":
    """负控制：沿用 meta_test 前 10 个任务几何/design points，仅置换 query 标签行。"""
    query = source.query_designs()
    query_size = int(query.shape[0])
    shuffle_seed = int.from_bytes(
        hashlib.sha256(
            (str(S3_FAMILY_SEED) + "|" + source.task_id + "|label-shuffle").encode("utf-8")
        ).digest()[:8],
        "big",
    ) % (2**31)
    rng = np.random.default_rng(shuffle_seed)
    permutation = [int(v) for v in rng.permutation(query_size)]
    source_params = dict(source.numeric_params())
    source_params["support_pool_size"] = source.support_pool_size
    source_params["query_size"] = source.query_size
    params: dict[str, Any] = {
        "support_pool_size": source.support_pool_size,
        "query_size": source.query_size,
        "shuffle_seed": shuffle_seed,
        "query_permutation": permutation,
        "source_task_id": source.task_id,
        "source_split": source.split,
        "source_seed": source.seed,
        "source_context": dict(source.context),
        "source_params": source_params,
        "reference_kind": "LABEL_SHUFFLED_NO_REFERENCE",
        "support_feasible_count": int(source.params.get("support_feasible_count", 0)),
        "support_retry_count": int(source.params.get("support_retry_count", 0)),
        "reference_rejections": 0,
        "degenerate_support": bool(source.params.get("degenerate_support", False)),
        "ood_flag": float(source.params.get("ood_flag", 0.0)),
    }
    task_id = S3_TASK_ID_PREFIX + hashlib.sha1(
        (S3_FAMILY_ID + "|" + S3_FORMULA_VERSION + "|nc|" + source.task_id + "|" + str(shuffle_seed)).encode("utf-8")
    ).hexdigest()[:16]
    return S3ConflictTask(
        task_id=task_id,
        split="meta_test_negative_control",
        family=S3_FAMILY_ID,
        formula_version=S3_FORMULA_VERSION,
        params=params,
        seed=shuffle_seed,
        context=dict(source.context),
        reference_kind="LABEL_SHUFFLED_NO_REFERENCE",
        source_task_id=source.task_id,
    )


def s3_reference_record(task: S3ConflictTask) -> dict[str, Any]:
    """参考解记录（写入 references_sealed；不含 design 行，只含证书数值）。"""
    reference = task.reference()
    record: dict[str, Any] = {
        "task_id": task.task_id,
        "split": task.split,
        "reference_kind": reference["reference_kind"],
        "u_star": [float(v) for v in np.asarray(reference["u_star"], dtype=np.float64)],
        "f_star": float(reference["f_star"]),
        "g1_star": float(reference["g1_star"]),
        "g2_star": float(reference["g2_star"]),
        "lambda": float(reference["lambda"]),
        "S": float(reference["S"]),
        "kkt_residual": float(reference["kkt_residual"]),
        "margin_m": float(reference["margin_m"]),
        "conflict_ratio": float(reference["conflict_ratio"]),
        "objective_regret": float(reference["objective_regret"]),
        "delta1": float(reference["delta1"]),
        "delta2": float(reference["delta2"]),
    }
    record["reference_digest"] = hashlib.sha256(
        _canonical_json(record).encode("utf-8")
    ).hexdigest()[:32]
    return record


def build_s3_references_sealed(tasks: Sequence[S3ConflictTask]) -> dict[str, Any]:
    """封存参考解文件载荷（runner 禁读；analysis 跑后读取计算 gap_to_reference）。"""
    records = [s3_reference_record(task) for task in tasks if not task.is_negative_control]
    payload: dict[str, Any] = {
        "schema_version": S3_REFERENCES_SEALED_SCHEMA_VERSION,
        "family_id": S3_FAMILY_ID,
        "formula_version": S3_FORMULA_VERSION,
        "family_seed": S3_FAMILY_SEED,
        "holdout_seed": S3_HOLDOUT_SEED,
        "physical_call_count": 0,
        "n_references": len(records),
        "references": records,
    }
    return payload


def build_s3_family_package(
    tasks: Sequence[S3ConflictTask],
    *,
    delta1_base: float,
    created_utc: str,
    code_sha: str,
    package_version: str = S3_FAMILY_VERSION,
) -> dict[str, Any]:
    """族冻结包载荷（计划 §2.2）；写入后由 Lead 冻结，M1 不写 evidence。"""
    split_ids: dict[str, list[str]] = {split: [] for split in S3_SPLITS}
    task_records: list[dict[str, Any]] = []
    for task in tasks:
        if task.split not in split_ids:
            raise TaskFamilyError("未知 split: " + repr(task.split))
        split_ids[task.split].append(task.task_id)
        task_records.append(
            {
                "task_id": task.task_id,
                "split": task.split,
                "family": task.family,
                "formula_version": task.formula_version,
                "seed": int(task.seed),
                "task_fingerprint": task.task_fingerprint(),
                "reference_kind": task.reference_kind,
                "params": dict(task.params),
                "context": dict(task.context),
                "support_retry_count": int(task.params.get("support_retry_count", 0)),
                "support_feasible_count": int(task.params.get("support_feasible_count", 0)),
                "degenerate_support": bool(task.params.get("degenerate_support", False)),
                "source_task_id": task.source_task_id,
            }
        )
    all_ids = [task.task_id for task in tasks]
    payload: dict[str, Any] = {
        "schema_version": S3_FAMILY_PACKAGE_SCHEMA_VERSION,
        "family_id": S3_FAMILY_ID,
        "formula_version": S3_FORMULA_VERSION,
        "package_version": str(package_version),
        "family_seed": S3_FAMILY_SEED,
        "holdout_seed": S3_HOLDOUT_SEED,
        "design_dim": DESIGN_DIM,
        "design_box": [S3_DESIGN_LOWER, S3_DESIGN_UPPER],
        "delta1_base": float(delta1_base),
        "delta1_candidates": list(S3_DELTA1_CANDIDATES),
        "param_distributions": dict(S3_PARAM_DISTRIBUTIONS),
        "support_pool_size": int(tasks[0].support_pool_size) if tasks else S3_SUPPORT_POOL_SIZE,
        "query_size": int(tasks[0].query_size) if tasks else S3_QUERY_SIZE,
        "splits": {split: split_ids[split] for split in S3_SPLITS},
        "split_counts": {split: len(split_ids[split]) for split in S3_SPLITS},
        "task_ids_sha256": hashlib.sha256(
            "\n".join(sorted(all_ids)).encode("utf-8")
        ).hexdigest(),
        "tasks": task_records,
        "created_utc": str(created_utc),
        "code_sha": str(code_sha),
        "physical_call_count": 0,
    }
    # family_package_sha256 按计划 §6.1 是族包文件的原始字节 sha（V11），
    # 不能内嵌进载荷自身（自引用）；由 write_s3_family_package 写盘后返回，
    # 记录到 prereg 的 frozen_package.family_package_sha256。
    return payload


def write_s3_json_canonical(path: str | Path, payload: Mapping[str, Any]) -> str:
    """写 canonical JSON + LF 到 path（调用方负责目录；M2 由 Lead 写入 evidence）。"""
    target = Path(path)
    data = (_canonical_json(dict(payload)) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def write_s3_family_package(
    path: str | Path,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """写族包文件并返回原始字节 sha（计划 §2.2/§6.1 V11 语义）。"""
    target = Path(path)
    raw_sha256 = write_s3_json_canonical(target, payload)
    data = target.read_bytes()
    if hashlib.sha256(data).hexdigest() != raw_sha256:
        raise TaskFamilyError("族包原始字节 sha 复算不一致")
    return {
        "path": str(target),
        "bytes": len(data),
        "family_package_sha256": raw_sha256,
    }


def evaluate_s3_delta1_candidate(
    delta1_base: float,
    *,
    validation_count: int = 20,
    grid_points: int = S3_CALIBRATION_GRID_POINTS,
) -> dict[str, Any]:
    """计划 §2.5 校准：在 meta_validation 20 任务上重算候选 delta1_base 的统计。"""
    tasks = build_s3_conflict_family(delta1_base=float(delta1_base))
    validation = [task for task in tasks if task.split == "meta_validation"][:validation_count]
    certificate_ok = 0
    support_ratios: list[float] = []
    min_feasible: list[int] = []
    grid_ratios: list[float] = []
    regrets: list[float] = []
    margins: list[float] = []
    conflict_ratios: list[float] = []
    for task in validation:
        try:
            reference = task.reference()
        except TaskFamilyError:
            continue
        certificate_ok += 1
        regrets.append(float(reference["objective_regret"]))
        margins.append(float(reference["margin_m"]))
        conflict_ratios.append(float(reference["conflict_ratio"]))
        support_labels = task.truth(task.support_designs())
        support_feasible = int(np.asarray(support_labels["feasibility"], dtype=bool).sum())
        support_ratios.append(support_feasible / float(task.support_pool_size))
        min_feasible.append(support_feasible)
        grid = _s3_lhs(int(grid_points), derive_seed("s3-calibration-grid", task.task_id))
        grid_labels = task.truth(grid)
        grid_feasible = int(np.asarray(grid_labels["feasibility"], dtype=bool).sum())
        grid_ratios.append(grid_feasible / float(grid_points))
    def _median(values: list[float]) -> float:
        if not values:
            raise TaskFamilyError("校准统计为空")
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return float(ordered[middle])
        return float(0.5 * (ordered[middle - 1] + ordered[middle]))
    return {
        "delta1_base": float(delta1_base),
        "validation_tasks": len(validation),
        "certificate_pass": int(certificate_ok),
        "support_feasible_ratio_median": _median(support_ratios),
        "support_feasible_ratio_min": float(min(support_ratios)),
        "support_feasible_ratio_max": float(max(support_ratios)),
        "support_feasible_min_points": int(min(min_feasible)),
        "grid_feasible_ratio_median": _median(grid_ratios),
        "grid_feasible_ratio_min": float(min(grid_ratios)),
        "grid_feasible_ratio_max": float(max(grid_ratios)),
        "grid_all_infeasible_tasks": int(sum(1 for value in grid_ratios if value <= 0.0)),
        "margin_mean": float(sum(margins) / len(margins)),
        "regret_median": _median(regrets),
        "conflict_ratio_median": _median(conflict_ratios),
        "grid_points": int(grid_points),
    }


def check_s3_calibration_candidate(record: Mapping[str, Any]) -> tuple[bool, list[str]]:
    """计划 §2.5 接受条件 (a)-(f)；返回 (ok, 失败原因列表)。"""
    reasons: list[str] = []
    if int(record["certificate_pass"]) != int(record["validation_tasks"]):
        reasons.append("(a) 证书未全部通过")
    if int(record["support_feasible_min_points"]) < S3_MIN_SUPPORT_FEASIBLE:
        reasons.append("(b) 存在 support 池 0 可行任务")
    support_median = float(record["support_feasible_ratio_median"])
    if not (S3_CALIBRATION_MEDIAN_BAND[0] <= support_median <= S3_CALIBRATION_MEDIAN_BAND[1]):
        reasons.append("(c) support 可行比例中位不在 [0.02,0.50]")
    grid_median = float(record["grid_feasible_ratio_median"])
    if not (S3_CALIBRATION_MEDIAN_BAND[0] <= grid_median <= S3_CALIBRATION_MEDIAN_BAND[1]):
        reasons.append("(c) 4096 网格可行比例中位不在 [0.02,0.50]")
    if int(record["grid_all_infeasible_tasks"]) != 0:
        reasons.append("(d) 存在 4096 网格全不可行任务")
    margin_mean = float(record["margin_mean"])
    if not (S3_M2_LOWER - 1e-12 <= margin_mean <= S3_M2_UPPER + 1e-12):
        reasons.append("(e) margin 均值不在 [0.10,0.15]")
    if float(record["regret_median"]) <= S3_REGRET_MIN:
        reasons.append("(f) regret 中位不大于 1e-6")
    return (not reasons, reasons)


def summarize_s3_calibration(candidate_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """按 §2.5 选择 delta1_base；返回选中值与全部候选的通过情况。"""
    if not candidate_records:
        raise TaskFamilyError("校准至少需要一个候选")
    rows = []
    selected: float | None = None
    for record in candidate_records:
        ok, reasons = check_s3_calibration_candidate(record)
        rows.append({"candidate": dict(record), "accepted": bool(ok), "reasons": reasons})
        if ok and selected is None:
            selected = float(record["delta1_base"])
    return {
        "candidates": rows,
        "selected_delta1_base": selected,
        "selection_rule": "首个通过 (a)-(f) 的候选（候选顺序固定）",
        "all_rejected": selected is None,
    }
