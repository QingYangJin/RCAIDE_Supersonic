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
    config: TaskFamilyConfig, split: str, index: int, ood: bool
) -> SyntheticTask:
    """生成单个任务：拒绝采样直到参考解落在 [0,1]^12 且参考断言通过。"""
    family = config.family_id
    last_error: Exception | None = None
    for attempt in range(_MAX_REFERENCE_RESAMPLES + 1):
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


def build_task_family(config: TaskFamilyConfig) -> list[SyntheticTask]:
    """构造任务族全部五个集合（meta_train/meta_validation/meta_test/meta_test_ood/negative_control）。

    顺序：meta_train -> meta_validation -> meta_test -> meta_test_ood -> negative_control；
    OOD 任务使用平移后的 context 中心并把 r 缩小 30%（§4.3），负控制由前
    negative_control_tasks 个不同 meta-train 任务派生，五集合 task_id 两两互斥。
    """
    if not isinstance(config, TaskFamilyConfig):
        raise TaskFamilyError("build_task_family 需要 TaskFamilyConfig")
    tasks: list[SyntheticTask] = []
    plan = (
        ("meta_train", config.train_tasks, False),
        ("meta_validation", config.validation_tasks, False),
        ("meta_test", config.test_tasks, False),
        ("meta_test_ood", config.ood_tasks, True),
    )
    splits: dict[str, list[SyntheticTask]] = {}
    for split, count, ood in plan:
        split_tasks = [_make_task(config, split, index, ood) for index in range(count)]
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
