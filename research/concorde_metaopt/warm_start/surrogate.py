"""路线A 轻量代理模型与 FOMAML K-shot 适配（复用 meta_learning/maml.py）。

代理模型输入 = 12 维设计 + 2 维任务上下文；输出 2 维：
[标准化目标值, 标准化最小约束裕度]。训练数据全部来自 synthetic.py 的解析
真值（SYNTHETIC_ANALOGUE），不涉及任何真实物理求解。

三种代理来源：
* zero_shot_surrogate：随机初始化网络直接预测（零样本，无任务数据）。
* pretrain_supervised：在有监督的元训练数据上做普通梯度训练；推理时可用
  K 个共享观测做输出偏置校准（只校准，不更新权重）。
* fomaml_kshot：用 meta_learning/maml.py 的 first_order=True 元训练；
  推理时用 K 个共享观测做 inner_adapt 的 K-shot 权重适配。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..meta_learning.maml import (
    MAMLConfig,
    ParameterSet,
    TaskEpisode,
    init_parameters,
    inner_adapt,
    meta_train,
)
from .synthetic import DIMENSION, FEATURE_DIM

SURROGATE_VERSION = "warm-start-surrogate-v1"
HIDDEN_SIZES: Tuple[int, int] = (32, 32)
OUTPUT_DIM = 2
TARGET_NAMES: Tuple[str, str] = ("objective", "constraint_margin")

SOURCE_ZERO_SHOT = "zero_shot_surrogate"
SOURCE_PRETRAIN = "pretrain_supervised"
SOURCE_FOMAML = "fomaml_kshot"
SURROGATE_SOURCES: Tuple[str, ...] = (SOURCE_ZERO_SHOT, SOURCE_PRETRAIN, SOURCE_FOMAML)
FEATURE_DIM_EXPECTED = FEATURE_DIM


def build_config(seed: int = 42, inner_steps: int = 5) -> MAMLConfig:
    """FOMAML 小网络配置（14-32-32-2，一阶外循环）。"""
    return MAMLConfig(
        input_dim=FEATURE_DIM_EXPECTED,
        output_dim=OUTPUT_DIM,
        hidden_sizes=HIDDEN_SIZES,
        inner_lr=0.02,
        inner_steps=int(inner_steps),
        outer_lr=0.01,
        tasks_per_batch=4,
        first_order=True,
        seed=int(seed),
        backend="torch",
    )


def forward_numpy(parameters: ParameterSet, features: np.ndarray) -> np.ndarray:
    """ParameterSet 的前向推理（层序：weight, bias 交替，tanh 隐层）。"""
    features = np.asarray(features, dtype=float)
    if features.ndim != 2 or features.shape[1] != FEATURE_DIM_EXPECTED:
        raise ValueError("features 必须是 (n, %d) 数组" % FEATURE_DIM_EXPECTED)
    tensors = parameters.tensors
    n_layers = len(tensors) // 2
    current = features
    for layer in range(n_layers):
        current = current @ tensors[2 * layer] + tensors[2 * layer + 1]
        if layer < n_layers - 1:
            current = np.tanh(current)
    return current


@dataclass(frozen=True)
class SurrogateSnapshot:
    """可复现的代理模型快照（含目标标准化与口径哈希）。"""

    kind: str
    config: MAMLConfig
    parameters: ParameterSet
    target_mean: np.ndarray
    target_std: np.ndarray
    model_sha: str
    provenance: Dict[str, Any]

    def predict(self, features: np.ndarray) -> np.ndarray:
        return forward_numpy(self.parameters, features)

    def scaled_targets(self, raw_targets: np.ndarray) -> np.ndarray:
        raw = np.asarray(raw_targets, dtype=float)
        return (raw - self.target_mean) / self.target_std

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "model_sha": self.model_sha,
            "config": self.config.to_dict(),
            "target_mean": [float(value) for value in self.target_mean],
            "target_std": [float(value) for value in self.target_std],
            "provenance": dict(self.provenance),
            "version": SURROGATE_VERSION,
        }


def _parameters_sha(parameters: ParameterSet) -> str:
    digest = hashlib.sha256()
    for tensor in parameters.tensors:
        digest.update(np.ascontiguousarray(tensor, dtype=np.float64).tobytes())
    return digest.hexdigest()


def snapshot_sha(
    kind: str,
    config: MAMLConfig,
    parameters: ParameterSet,
    target_mean: np.ndarray,
    target_std: np.ndarray,
) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps({"kind": kind, "config": config.to_dict()}, sort_keys=True).encode("utf-8"))
    digest.update(_parameters_sha(parameters).encode("ascii"))
    digest.update(np.asarray(target_mean, dtype=np.float64).tobytes())
    digest.update(np.asarray(target_std, dtype=np.float64).tobytes())
    return digest.hexdigest()


def make_snapshot(
    kind: str,
    config: MAMLConfig,
    parameters: ParameterSet,
    target_mean: Sequence[float],
    target_std: Sequence[float],
    provenance: Mapping[str, Any],
) -> SurrogateSnapshot:
    mean = np.asarray(target_mean, dtype=float)
    std = np.asarray(target_std, dtype=float)
    if mean.shape != (OUTPUT_DIM,) or std.shape != (OUTPUT_DIM,):
        raise ValueError("target_mean/std 必须有 %d 个分量" % OUTPUT_DIM)
    if np.any(std <= 0.0) or not np.all(np.isfinite(mean)) or not np.all(np.isfinite(std)):
        raise ValueError("target_mean/std 必须有限且 std>0")
    payload = dict(provenance)
    payload.setdefault("version", SURROGATE_VERSION)
    payload.setdefault("source_kind", "SYNTHETIC_ANALOGUE")
    payload.setdefault("physical_call_count", 0)
    return SurrogateSnapshot(
        kind=kind,
        config=config,
        parameters=parameters,
        target_mean=mean,
        target_std=std,
        model_sha=snapshot_sha(kind, config, parameters, mean, std),
        provenance=payload,
    )


# -- 数据采集 ---------------------------------------------------------------


def collect_task_data(task: Any, n_designs: int = 40, seed: int = 0) -> Dict[str, np.ndarray]:
    """单个合成任务的 (特征, 原始目标/裕度) 数据。"""
    rng = np.random.default_rng(seed)
    designs = rng.random((int(n_designs), DIMENSION))
    truth = task.truth(designs)
    raw = np.column_stack([truth["objective"], truth["constraint_margin"]])
    return {"features": task.features(designs), "targets": raw, "designs": designs, "task_id": task.task_id}


def collect_meta_data(
    tasks: Sequence[Any], n_designs: int = 40, seed: int = 0
) -> Dict[str, Any]:
    """元训练数据：逐任务采样并拼接；返回标准化统计量。"""
    features: List[np.ndarray] = []
    targets: List[np.ndarray] = []
    per_task: List[Dict[str, Any]] = []
    for index, task in enumerate(tasks):
        data = collect_task_data(task, n_designs=n_designs, seed=seed + index)
        features.append(data["features"])
        targets.append(data["targets"])
        per_task.append({"task_id": task.task_id, "features": data["features"], "targets": data["targets"]})
    all_features = np.vstack(features)
    all_targets = np.vstack(targets)
    mean = np.mean(all_targets, axis=0)
    std = np.std(all_targets, axis=0)
    std = np.where(std < 1e-9, 1.0, std)
    return {
        "features": all_features,
        "targets": all_targets,
        "target_mean": mean,
        "target_std": std,
        "per_task": per_task,
        "n_tasks": len(tasks),
        "n_designs": int(n_designs),
    }


# -- 训练 -------------------------------------------------------------------


def zero_shot_snapshot(seed: int = 42) -> SurrogateSnapshot:
    config = build_config(seed=seed)
    parameters = init_parameters(config)
    return make_snapshot(
        SOURCE_ZERO_SHOT,
        config,
        parameters,
        [0.0, 0.0],
        [1.0, 1.0],
        {"description": "随机初始化代理网络（零样本参照）", "seed": int(seed)},
    )


def _forward_torch(tensors: List[Any], features: Any) -> Any:
    current = features
    n_layers = len(tensors) // 2
    for layer in range(n_layers):
        current = current @ tensors[2 * layer] + tensors[2 * layer + 1]
        if layer < n_layers - 1:
            current = __import__("torch").tanh(current)
    return current


def pretrain_snapshot(
    meta_data: Mapping[str, Any],
    seed: int = 42,
    steps: int = 240,
    learning_rate: float = 3e-3,
) -> SurrogateSnapshot:
    """普通有监督预训练（非元学习）；训练后冻结权重。"""
    import torch

    config = build_config(seed=seed)
    parameters = init_parameters(config)
    features = torch.tensor(np.asarray(meta_data["features"], dtype=np.float64), dtype=torch.float64)
    targets_raw = np.asarray(meta_data["targets"], dtype=np.float64)
    mean = np.asarray(meta_data["target_mean"], dtype=np.float64)
    std = np.asarray(meta_data["target_std"], dtype=np.float64)
    targets = torch.tensor((targets_raw - mean) / std, dtype=torch.float64)
    tensors = [torch.tensor(tensor, dtype=torch.float64, requires_grad=True) for tensor in parameters.tensors]
    optimizer = torch.optim.Adam(tensors, lr=float(learning_rate))
    history: List[float] = []
    for _ in range(int(steps)):
        optimizer.zero_grad()
        prediction = _forward_torch(tensors, features)
        loss = torch.mean((prediction - targets) ** 2)
        loss.backward()
        optimizer.step()
        history.append(float(loss.item()))
    trained = ParameterSet([tensor.detach().numpy().copy() for tensor in tensors])
    final_loss = float(np.mean((forward_numpy(trained, np.asarray(meta_data["features"])) - (targets_raw - mean) / std) ** 2))
    return make_snapshot(
        SOURCE_PRETRAIN,
        config,
        trained,
        mean,
        std,
        {
            "description": "普通有监督预训练（非元学习）",
            "steps": int(steps),
            "learning_rate": float(learning_rate),
            "train_loss_first": history[0] if history else None,
            "train_loss_last": history[-1] if history else None,
            "final_full_batch_mse": final_loss,
            "seed": int(seed),
            "n_train_samples": int(features.shape[0]),
        },
    )


def fomaml_snapshot(
    meta_data: Mapping[str, Any],
    seed: int = 42,
    max_steps: int = 90,
    support_per_task: int = 12,
    query_per_task: int = 24,
) -> SurrogateSnapshot:
    """用 meta_learning/maml.py 的 FOMAML（first_order=True）元训练。"""
    config = build_config(seed=seed)
    mean = np.asarray(meta_data["target_mean"], dtype=np.float64)
    std = np.asarray(meta_data["target_std"], dtype=np.float64)
    episodes: List[TaskEpisode] = []
    for item in meta_data["per_task"]:
        features = np.asarray(item["features"], dtype=float)
        targets = (np.asarray(item["targets"], dtype=float) - mean) / std
        support_count = min(int(support_per_task), features.shape[0] // 2)
        query_count = min(int(query_per_task), features.shape[0] - support_count)
        if support_count <= 0 or query_count <= 0:
            raise ValueError("元训练任务数据不足以构造 support/query")
        episodes.append(
            TaskEpisode(
                support_features=features[:support_count],
                support_targets=targets[:support_count],
                query_features=features[support_count : support_count + query_count],
                query_targets=targets[support_count : support_count + query_count],
                task_id=str(item["task_id"]),
            )
        )
    result = meta_train(episodes, config, int(max_steps))
    if str(result.get("status")) != "VALID":
        raise RuntimeError("FOMAML 元训练未成功：%r" % (result.get("failure") or result.get("status"),))
    parameters = ParameterSet.from_dict(result["final_parameters"])
    history = result.get("history") or []
    return make_snapshot(
        SOURCE_FOMAML,
        config,
        parameters,
        mean,
        std,
        {
            "description": "meta_learning/maml.py first_order=True (FOMAML) 元训练",
            "steps": int(result.get("steps", 0)),
            "steps_requested": int(max_steps),
            "outer_loss_first": float(history[0]["outer_loss"]) if history else None,
            "outer_loss_last": float(history[-1]["outer_loss"]) if history else None,
            "support_per_task": int(support_per_task),
            "query_per_task": int(query_per_task),
            "n_meta_tasks": len(episodes),
            "seed": int(seed),
            "equivalence_claimed": False,
        },
    )


def adapt_fomaml(
    snapshot: SurrogateSnapshot, support_features: np.ndarray, support_targets_scaled: np.ndarray
) -> SurrogateSnapshot:
    """K-shot 权重适配：inner_adapt 只用 support 的真实观测标签。"""
    episode = TaskEpisode(
        support_features=np.asarray(support_features, dtype=float),
        support_targets=np.asarray(support_targets_scaled, dtype=float),
        query_features=np.asarray(support_features, dtype=float)[:1],
        query_targets=np.asarray(support_targets_scaled, dtype=float)[:1],
    )
    adapted, losses = inner_adapt(snapshot.parameters, episode, snapshot.config)
    provenance = dict(snapshot.provenance)
    provenance.update(
        {
            "adaptation": "fomaml_inner_adapt",
            "k_shot": int(np.asarray(support_features).shape[0]),
            "inner_steps": int(snapshot.config.inner_steps),
            "adapt_loss_last": float(losses[-1]) if losses else None,
        }
    )
    return make_snapshot(
        snapshot.kind, snapshot.config, adapted, snapshot.target_mean, snapshot.target_std, provenance
    )


def calibrate_offset(
    snapshot: SurrogateSnapshot, support_features: np.ndarray, support_targets_scaled: np.ndarray
) -> SurrogateSnapshot:
    """K-shot 输出偏置校准（仅校准预测偏置，不更新权重）。"""
    predicted = snapshot.predict(np.asarray(support_features, dtype=float))
    residual = np.asarray(support_targets_scaled, dtype=float) - predicted
    delta = np.mean(residual, axis=0)
    tensors = [tensor.copy() for tensor in snapshot.parameters.tensors]
    tensors[-1] = tensors[-1] + np.asarray(delta, dtype=float)
    provenance = dict(snapshot.provenance)
    provenance.update(
        {
            "adaptation": "output_bias_calibration",
            "k_shot": int(np.asarray(support_features).shape[0]),
            "bias_delta": [float(value) for value in delta],
            "calibration_residual_rms": float(np.sqrt(np.mean(residual ** 2))),
        }
    )
    return make_snapshot(
        snapshot.kind,
        snapshot.config,
        ParameterSet(tensors),
        snapshot.target_mean,
        snapshot.target_std,
        provenance,
    )
