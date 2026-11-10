"""policy_train：离线轨迹上的 direct-method 策略训练（numpy 手写反向传播）。

目标：最小化 mean((score_phi(features) - reward_to_go)^2)，即学习"该决策时刻
应当给候选打多高的分"的标量回归。离线数据中未选候选的标签不可观测，因此这是
有偏的 direct method，不做事后反事实加权；此局限在方法文档与 NOT_READY 结论
中显式声明。

隔离约束：

- 数据集本身只含 train 任务（trajectory_dataset 强制校验）；
- 再从 train 任务中按 **任务 id** 切出 held-out 训练验证集用于 early stopping，
  绝不使用 val/test 划分任务；
- 报告记录参与任务 id、记录数、loss 曲线与策略 SHA256。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np

from ..contracts import LeakageError, RouteBContractError, canonical_json
from ..policy import MetaAcquisitionPolicy, POLICY_VERSION, feature_names
from ..trajectory_dataset import load_dataset, split_by_task

TRAIN_VERSION = "route-b-policy-train-v1"
DEFAULT_EPOCHS = 240
DEFAULT_LR = 0.02


def _matrix(records: Sequence[Dict[str, Any]]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    features = np.asarray([record["features"] for record in records], dtype=float)
    targets = np.asarray([record["reward_to_go"] for record in records], dtype=float)
    tasks = np.asarray([record["task_id"] for record in records])
    if features.ndim != 2 or features.shape[0] != targets.size:
        raise RouteBContractError("记录矩阵形状异常: %r" % (features.shape,))
    return features, targets, tasks


def _forward(policy: MetaAcquisitionPolicy, x: np.ndarray, train_mode: bool = False):
    mean = policy.feature_mean
    std = np.clip(policy.feature_std, 1e-8, None)
    z = (x - mean) / std
    h_pre = z @ policy.w1 + policy.b1
    h = np.tanh(h_pre)
    out = h @ policy.w2 + policy.b2
    if not train_mode:
        return out
    return out, (z, h, h_pre)


def _backward(policy: MetaAcquisitionPolicy, cache, grad_out: np.ndarray):
    z, h, _h_pre = cache
    grad_w2 = h.T @ grad_out
    grad_b2 = float(grad_out.sum())
    grad_h = np.outer(grad_out, policy.w2) * (1.0 - h * h)
    grad_w1 = z.T @ grad_h
    grad_b1 = grad_h.sum(axis=0)
    return {"w1": grad_w1, "b1": grad_b1, "w2": grad_w2, "b2": grad_b2}


def _adam_step(policy: MetaAcquisitionPolicy, grads: Dict[str, Any], state: Dict[str, Any], lr: float, step: int) -> None:
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    for name, grad in grads.items():
        grad_arr = np.asarray(grad, dtype=float)
        if name not in state:
            state[name] = {"m": np.zeros_like(grad_arr), "v": np.zeros_like(grad_arr)}
        slot = state[name]
        slot["m"] = beta1 * slot["m"] + (1.0 - beta1) * grad_arr
        slot["v"] = beta2 * slot["v"] + (1.0 - beta2) * (grad_arr * grad_arr)
        m_hat = slot["m"] / (1.0 - beta1 ** step)
        v_hat = slot["v"] / (1.0 - beta2 ** step)
        update = lr * m_hat / (np.sqrt(v_hat) + eps)
        if name == "b2":
            policy.b2 = float(policy.b2 - update)
        else:
            setattr(policy, name, getattr(policy, name) - update)


def train_policy(
    dataset_dir: Path,
    output_dir: Path,
    holdout_tasks: int = 2,
    epochs: int = DEFAULT_EPOCHS,
    lr: float = DEFAULT_LR,
    seed: int = 0,
) -> Dict[str, Any]:
    """在离线轨迹上训练 MetaAcquisitionPolicy，返回并落盘训练报告。"""
    data = load_dataset(dataset_dir)
    records = data["records"]
    manifest = data["manifest"]
    task_ids = sorted({record["task_id"] for record in records})
    if len(task_ids) < 4:
        raise RouteBContractError("train 任务数 %d < 4，无法切出训练/验证任务" % len(task_ids))
    if any(record["split"] != "train" for record in records):
        raise LeakageError("数据集中混入非 train 划分记录")
    holdout = max(1, min(int(holdout_tasks), len(task_ids) - 2))
    rng = np.random.default_rng(seed)
    order = list(rng.permutation(len(task_ids)))
    val_ids = sorted(task_ids[index] for index in order[:holdout])
    fit_ids = sorted(task_ids[index] for index in order[holdout:])
    train_records, val_records = split_by_task(records, fit_ids, val_ids)
    if not train_records or not val_records:
        raise RouteBContractError("训练或验证记录为空")

    x_train, y_train, _ = _matrix(train_records)
    x_val, y_val, _ = _matrix(val_records)
    if x_train.shape[1] != len(feature_names(6)):
        raise RouteBContractError("特征维度 %d 与 feature_names(6)=%d 不一致" % (x_train.shape[1], len(feature_names(6))))

    policy = MetaAcquisitionPolicy(feature_input_dim=x_train.shape[1], hidden=32, seed=seed)
    policy.feature_mean = x_train.mean(axis=0)
    policy.feature_std = x_train.std(axis=0)
    policy.feature_std = np.where(policy.feature_std < 1e-8, 1.0, policy.feature_std)
    policy.target_mean = float(y_train.mean())
    policy.target_std = float(y_train.std()) if float(y_train.std()) > 1e-8 else 1.0
    y_train_norm = (y_train - policy.target_mean) / policy.target_std
    y_val_norm = (y_val - policy.target_mean) / policy.target_std

    state: Dict[str, Any] = {}
    history: List[Dict[str, float]] = []
    best = {"epoch": -1, "val_loss": float("inf"), "params": None}
    for epoch in range(1, int(epochs) + 1):
        out, cache = _forward(policy, x_train, train_mode=True)
        residual = out - y_train_norm
        train_loss = float(np.mean(residual * residual))
        _adam_step(policy, _backward(policy, cache, 2.0 * residual / residual.size), state, lr, epoch)
        val_pred = _forward(policy, x_val)
        val_loss = float(np.mean((val_pred - y_val_norm) ** 2))
        history.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        if val_loss < best["val_loss"] - 1e-12:
            best = {"epoch": epoch, "val_loss": val_loss, "params": policy.to_params()}
    if best["params"] is not None:
        policy = MetaAcquisitionPolicy.from_params(best["params"])
        policy.trained = True
        policy.to_params()["trained"] = True

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    policy_path = output_dir / "policy.json"
    params = policy.to_params()
    params["trained"] = True
    payload = canonical_json(params)
    policy_path.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    final_train_pred = _forward(policy, x_train)
    final_val_pred = _forward(policy, x_val)
    report = {
        "train_version": TRAIN_VERSION,
        "policy_version": POLICY_VERSION,
        "method": "direct_method_reward_to_go_regression",
        "known_bias": "未选候选标签不可观测，未做反事实校正",
        "dataset_manifest_sha256": manifest["sha256"],
        "dataset_records": len(records),
        "fit_task_ids": fit_ids,
        "val_task_ids": val_ids,
        "holdout_split_rule": "仅从 train 划分任务中按任务 id 切分，val/test 划分任务未参与训练或早停",
        "n_train_records": len(train_records),
        "n_val_records": len(val_records),
        "feature_dim": int(x_train.shape[1]),
        "epochs": int(epochs),
        "learning_rate": float(lr),
        "best_epoch": int(best["epoch"]),
        "best_val_loss": float(best["val_loss"]),
        "final_train_loss": float(np.mean((final_train_pred - y_train_norm) ** 2)),
        "final_val_loss": float(np.mean((final_val_pred - y_val_norm) ** 2)),
        "target_mean": policy.target_mean,
        "target_std": policy.target_std,
        "loss_history": history,
        "policy_sha256": sha,
        "policy_path": str(policy_path),
        "physical_call_count": 0,
        "source_kind": "synthetic_analogue",
    }
    (output_dir / "train_report.json").write_text(canonical_json(report), encoding="utf-8")
    (output_dir / "loss_history.json").write_text(canonical_json(history), encoding="utf-8")
    return report
