"""K-shot 适应与评估（§5.5 / §9 M1）。

方法：none（零样本）、fine_tuning（含预训练对照 P）、maml（一阶 MAML 臂 M）、
from_scratch（随机初始化臂 R）。本模块只使用 support 标签做适应；query 标签
只在评估（计算 metrics）时一次性使用，绝不回流到适应路径。
physical_call_count 恒为 0（离线合成）。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .data_contract import PHYSICAL_CALL_COUNT as _CONTRACT_PHYSICAL_CALL_COUNT
from .maml import MAMLConfig, ParameterSet, TaskEpisode, init_parameters, inner_adapt
from .surrogate import encode_features, regression_metrics

ADAPTATION_METHODS = ("none", "fine_tuning", "maml", "from_scratch")
DEFAULT_FINE_TUNING_STEPS = 50
DEFAULT_MAML_INNER_STEPS = 5


class AdaptationError(ValueError):
    """适应/评估阶段错误。"""


@dataclass(frozen=True)
class AdaptationResult:
    """单次 K-shot 适应的结果（§5.5）。"""

    method: str
    k_shot: int
    inner_steps: int
    predictions: np.ndarray
    targets: np.ndarray
    losses: tuple[float, ...]
    metrics: Mapping[str, float]
    physical_call_count: int = 0

    def __post_init__(self) -> None:
        if self.method not in ADAPTATION_METHODS:
            raise AdaptationError(f"未知适应方法: {self.method!r}")
        if type(self.k_shot) is not int or self.k_shot < 0:
            raise AdaptationError("k_shot 必须是非负整数")
        if self.inner_steps < 0:
            raise AdaptationError("inner_steps 不能为负")
        if self.physical_call_count != _CONTRACT_PHYSICAL_CALL_COUNT:
            raise AdaptationError(
                f"离线适应 physical_call_count 必须为 0，实际 {self.physical_call_count}"
            )
        predictions = np.asarray(self.predictions, dtype=np.float64).reshape(-1)
        targets = np.asarray(self.targets, dtype=np.float64).reshape(-1)
        if predictions.shape != targets.shape:
            raise AdaptationError(f"预测/标签形状不一致: {predictions.shape} vs {targets.shape}")
        object.__setattr__(self, "predictions", predictions)
        object.__setattr__(self, "targets", targets)
        losses = tuple(float(value) for value in self.losses)
        if len(losses) != self.inner_steps:
            raise AdaptationError(
                f"losses 长度 {len(losses)} 必须等于 inner_steps {self.inner_steps}"
            )
        object.__setattr__(self, "losses", losses)
        object.__setattr__(self, "metrics", dict(self.metrics))

    def to_record(self, run_id: str, task_id: str, split: str, family: str, seed: int) -> dict[str, Any]:
        """转成 adaptation_results.csv 行（列名按 p4_schemas.json）。"""
        metrics = self.metrics
        return {
            "run_id": run_id,
            "task_id": task_id,
            "split": split,
            "family": family,
            "arm": _ARM_BY_METHOD[self.method],
            "K": self.k_shot,
            "seed": int(seed),
            "n_support": int(self.k_shot),
            "n_query": int(self.predictions.shape[0]),
            "adapt_steps": int(self.inner_steps),
            "mae_raw": float(metrics.get("mae", float("nan"))),
            "rmse_raw": float(metrics.get("rmse", float("nan"))),
            "mae_norm": float(metrics.get("mae_norm", float("nan"))),
            "rmse_norm": float(metrics.get("rmse_norm", float("nan"))),
            "r2": float(metrics.get("r2", float("nan"))),
            "max_abs_err": float(metrics.get("max_abs_err", float("nan"))),
            "wall_s": 0.0,
            "status": "VALID" if metrics.get("n_nonfinite", 0.0) == 0.0 else "NONFINITE",
        }


_ARM_BY_METHOD = {"none": "R", "fine_tuning": "P", "maml": "M", "from_scratch": "R"}


def _stable_seed(*parts: Any) -> int:
    digest = hashlib.sha1("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _forward_numpy(tensors: Sequence[np.ndarray], features: np.ndarray) -> np.ndarray:
    current = np.asarray(features, dtype=np.float64)
    n_layers = len(tensors) // 2
    for layer in range(n_layers):
        current = current @ tensors[2 * layer] + tensors[2 * layer + 1]
        if layer < n_layers - 1:
            current = np.tanh(current)
    return current


def predict_parameters(
    parameters: ParameterSet, features: np.ndarray, output_dim: int | None = None
) -> np.ndarray:
    """用给定参数做前向预测（不训练）；单输出时返回一维数组。"""
    if not isinstance(parameters, ParameterSet):
        raise AdaptationError("predict_parameters 需要 ParameterSet")
    matrix = np.asarray(features, dtype=np.float64)
    if matrix.ndim != 2:
        raise AdaptationError(f"features 必须为二维数组，实际 {matrix.shape}")
    prediction = _forward_numpy(parameters.tensors, matrix)
    if output_dim is None:
        output_dim = prediction.shape[1]
    if prediction.shape[1] == 1:
        return prediction[:, 0]
    return prediction


def _parameter_set_from(value: Any, label: str) -> ParameterSet:
    if isinstance(value, ParameterSet):
        return value
    if isinstance(value, Mapping):
        return ParameterSet.from_dict(value)
    raise AdaptationError(f"{label} 必须是 ParameterSet 或参数字典，实际 {type(value).__name__}")


def _config_from(value: Any) -> MAMLConfig:
    if isinstance(value, MAMLConfig):
        return value
    if isinstance(value, Mapping):
        return MAMLConfig(**value)
    raise AdaptationError(f"config 必须是 MAMLConfig 或字典，实际 {type(value).__name__}")


def _resolve_config(artifact: Mapping[str, Any]) -> MAMLConfig:
    if "config" in artifact:
        return _config_from(artifact["config"])
    parameters = _parameter_set_from(artifact["parameters"], "artifact['parameters']")
    return MAMLConfig(
        input_dim=int(parameters.tensors[0].shape[0]),
        output_dim=int(parameters.tensors[-1].shape[1]),
        inner_steps=DEFAULT_MAML_INNER_STEPS,
    )


def _artifact_view(artifact: Any) -> dict[str, Any]:
    """统一 artifact 形态（meta_train 输出、字典或带属性的对象）。"""
    if isinstance(artifact, Mapping):
        payload = dict(artifact)
    elif hasattr(artifact, "parameters") and hasattr(artifact, "config"):
        payload = {"parameters": artifact.parameters, "config": artifact.config}
    else:
        raise AdaptationError(f"无法识别的 artifact 类型: {type(artifact).__name__}")
    if "parameters" not in payload:
        if "final_parameters" in payload:
            payload["parameters"] = payload["final_parameters"]
        else:
            raise AdaptationError("artifact 缺少 parameters/final_parameters")
    view: dict[str, Any] = {
        "parameters": _parameter_set_from(payload["parameters"], "artifact['parameters']"),
        "config": _config_from(payload["config"]) if "config" in payload else None,
        "context_names": tuple(payload.get("context_names", ())),
        "adaptation_method": str(payload.get("adaptation_method", payload.get("method", "maml"))),
        "fine_tuning_steps": payload.get("fine_tuning_steps", DEFAULT_FINE_TUNING_STEPS),
        "backend": payload.get("backend", "torch"),
        "equivalence_claimed": bool(payload.get("equivalence_claimed", False)),
    }
    if view["config"] is None:
        view["config"] = _resolve_config(payload)
    return view


def _block_to_xy(block: Any, artifact_view: Mapping[str, Any], label: str) -> tuple[np.ndarray, np.ndarray]:
    """把 support/query 块统一成 (features, targets)。

    支持三种形态：
    1. TaskEpisode；
    2. {"features": (n,d), "targets": (n,) 或 (n,k)}；
    3. {"designs": (n,12) 归一化设计, "task_context": {...}}（用 encode_features 构造特征）。
    """
    if isinstance(block, TaskEpisode):
        if label.endswith("query"):
            return block.query_features, block.query_targets
        return block.support_features, block.support_targets
    if not isinstance(block, Mapping):
        raise AdaptationError(f"{label} 必须是 TaskEpisode 或字典，实际 {type(block).__name__}")
    if "features" in block and "targets" in block:
        features = np.asarray(block["features"], dtype=np.float64)
        targets = np.asarray(block["targets"], dtype=np.float64)
    elif "designs" in block:
        context_names = artifact_view["context_names"]
        if not context_names:
            raise AdaptationError(f"{label} 使用 designs 形态时必须提供 context_names")
        features = encode_features(block["designs"], block.get("task_context"), context_names)
        if "targets" not in block:
            raise AdaptationError(f"{label} 缺少 targets")
        targets = np.asarray(block["targets"], dtype=np.float64)
    else:
        raise AdaptationError(f"{label} 缺少 features/targets 或 designs")
    if features.ndim != 2:
        raise AdaptationError(f"{label} features 必须二维")
    if targets.ndim == 1:
        targets = targets[:, None]
    if targets.ndim != 2 or targets.shape[0] != features.shape[0]:
        raise AdaptationError(f"{label} targets 行数与 features 不一致")
    return features, targets


def _subset_support(
    features: np.ndarray, targets: np.ndarray, k_shot: int, task_id: str, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """从 support 候选池取 K 点：置换只由 (task_id, seed) 决定，K 增大时嵌套（§4.3）。"""
    if type(k_shot) is not int or k_shot < 0:
        raise AdaptationError("k_shot 必须是非负整数")
    if k_shot > features.shape[0]:
        raise AdaptationError(
            f"任务 {task_id} 的 support 池只有 {features.shape[0]} 点，无法取 K={k_shot}"
        )
    order = np.random.default_rng(_stable_seed(task_id, seed, "support_subset")).permutation(
        features.shape[0]
    )
    take = order[:k_shot]
    return features[take], targets[take]


def _support_episode(features: np.ndarray, targets: np.ndarray) -> TaskEpisode:
    """仅含 support 的 episode（inner_adapt 只使用 support，query 槽位不参与适应）。

    query 槽位填与 support 相同数组只为满足 TaskEpisode 结构校验；适应路径
    从不读取 query 标签（§6 泄漏断言）。
    """
    return TaskEpisode(features, targets, features, targets)


def adapt_and_predict(
    artifact: Any,
    support: Any,
    query: Any,
    method: str,
    k_shot: int,
    config: Mapping[str, Any] | MAMLConfig | None = None,
) -> AdaptationResult:
    """按方法在 support 上适应，并在 query 上评估（query 标签只用于算指标）。"""
    if method not in ADAPTATION_METHODS:
        raise AdaptationError(f"未知适应方法: {method!r}（允许 {ADAPTATION_METHODS}）")
    view = _artifact_view(artifact)
    base_config: MAMLConfig = view["config"]
    override = dict(config) if isinstance(config, Mapping) else {}
    if isinstance(config, MAMLConfig):
        base_config = config
    inner_lr = float(override.get("inner_lr", base_config.inner_lr))
    hidden_sizes = tuple(override.get("hidden_sizes", base_config.hidden_sizes))
    fine_tuning_steps = int(override.get("fine_tuning_steps", view["fine_tuning_steps"]))
    if fine_tuning_steps < 0:
        raise AdaptationError("fine_tuning_steps 不能为负")
    support_features, support_targets = _block_to_xy(support, view, "support")
    query_features, query_targets = _block_to_xy(query, view, "query")
    if support_features.shape[1] != base_config.input_dim:
        raise AdaptationError(
            f"support 特征维度 {support_features.shape[1]} != config.input_dim {base_config.input_dim}"
        )
    if query_features.shape[1] != base_config.input_dim:
        raise AdaptationError("query 特征维度与 config.input_dim 不一致")
    if support_features.shape[0] != k_shot and k_shot != 0:
        raise AdaptationError(
            f"support 行数 {support_features.shape[0]} 与 k_shot={k_shot} 不一致"
        )
    output_dim = base_config.output_dim
    if support_targets.shape[1] != output_dim and support_targets.shape[1] != 1:
        raise AdaptationError("support 标签维度与 config.output_dim 不一致")
    # 单输出配置允许 support 标签为 (n,1)；多输出时沿用全部列
    support_targets = support_targets[:, :output_dim]
    query_targets_full = np.asarray(query_targets, dtype=np.float64)
    if query_targets_full.shape[1] == 1:
        evaluation_targets = query_targets_full[:, 0]
    else:
        evaluation_targets = query_targets_full[:, :output_dim]

    effective_steps = 0
    losses: list[float] = []
    if method == "none":
        parameters = view["parameters"].copy()
        predictions = predict_parameters(parameters, query_features, output_dim)
    elif method == "maml":
        if k_shot == 0:
            parameters = view["parameters"].copy()
            predictions = predict_parameters(parameters, query_features, output_dim)
        else:
            episode = _support_episode(support_features, support_targets)
            parameters, losses = inner_adapt(view["parameters"], episode, base_config)
            effective_steps = len(losses)
            predictions = predict_parameters(parameters, query_features, output_dim)
    elif method == "fine_tuning":
        if k_shot == 0:
            parameters = view["parameters"].copy()
            predictions = predict_parameters(parameters, query_features, output_dim)
        else:
            steps = max(1, fine_tuning_steps)
            tune_config = MAMLConfig(
                input_dim=base_config.input_dim,
                output_dim=base_config.output_dim,
                hidden_sizes=hidden_sizes,
                inner_lr=inner_lr,
                inner_steps=steps,
                outer_lr=base_config.outer_lr,
                tasks_per_batch=1,
                first_order=True,
                seed=base_config.seed,
            )
            episode = _support_episode(support_features, support_targets)
            parameters, losses = inner_adapt(view["parameters"], episode, tune_config)
            effective_steps = len(losses)
            predictions = predict_parameters(parameters, query_features, output_dim)
    else:  # from_scratch：随机初始化后只用 support 标签训练，K=0 直接随机预测
        fresh_config = MAMLConfig(
            input_dim=base_config.input_dim,
            output_dim=base_config.output_dim,
            hidden_sizes=hidden_sizes,
            inner_lr=inner_lr,
            inner_steps=max(1, fine_tuning_steps) if k_shot > 0 else 0,
            outer_lr=base_config.outer_lr,
            tasks_per_batch=1,
            first_order=True,
            seed=_stable_seed(base_config.seed, "from_scratch") % (2**31),
        )
        parameters = init_parameters(fresh_config)
        if k_shot > 0:
            episode = _support_episode(support_features, support_targets)
            parameters, losses = inner_adapt(parameters, episode, fresh_config)
            effective_steps = len(losses)
        predictions = predict_parameters(parameters, query_features, output_dim)

    if np.asarray(evaluation_targets).ndim == 2:
        # 多输出：对每列分别算指标后取宏平均，非有限计数取总和
        metric_list = [
            regression_metrics(predictions[:, column], evaluation_targets[:, column])
            for column in range(evaluation_targets.shape[1])
        ]
        metrics = _aggregate_metrics(metric_list)
    else:
        metrics = regression_metrics(
            np.asarray(predictions).reshape(-1), np.asarray(evaluation_targets).reshape(-1)
        )
        scale = float(np.std(np.asarray(evaluation_targets, dtype=np.float64)))
        metrics["mae_norm"] = metrics["mae"] / scale if scale > 0.0 else float("nan")
        metrics["rmse_norm"] = metrics["rmse"] / scale if scale > 0.0 else float("nan")
    metrics["k_shot"] = float(k_shot)
    metrics["inner_steps"] = float(effective_steps)
    return AdaptationResult(
        method=method,
        k_shot=k_shot,
        inner_steps=effective_steps,
        predictions=np.asarray(predictions, dtype=np.float64).reshape(-1),
        targets=np.asarray(evaluation_targets, dtype=np.float64).reshape(-1),
        losses=tuple(losses),
        metrics=metrics,
        physical_call_count=_CONTRACT_PHYSICAL_CALL_COUNT,
    )


def _aggregate_metrics(metric_list: Sequence[Mapping[str, float]]) -> dict[str, float]:
    keys = set(metric_list[0])
    for item in metric_list[1:]:
        keys &= set(item)
    aggregated: dict[str, float] = {}
    for key in sorted(keys):
        values = np.asarray([item[key] for item in metric_list], dtype=np.float64)
        if key == "n_nonfinite":
            aggregated[key] = float(np.sum(values))
        else:
            finite = values[np.isfinite(values)]
            aggregated[key] = float(np.mean(finite)) if finite.size else float("nan")
    return aggregated


def run_k_shot_study(
    artifact: Any,
    tasks: Sequence[Any],
    ks: Sequence[int],
    seed: int,
) -> list[AdaptationResult]:
    """对任务 × K 运行适应研究（support 从池内嵌套取前 K，query 固定）。

    tasks 元素形态：SyntheticTask 或 dict：
      {"task_id": str, "family": str, "split": str,
       "support": {"features","targets"} 或 {"designs","task_context","targets"},
       "query": 同 support 形态}
    """
    if not tasks:
        raise AdaptationError("tasks 不能为空")
    view = _artifact_view(artifact)
    method = view["adaptation_method"]
    results: list[AdaptationResult] = []
    for task in tasks:
        payload = _task_payload(task, view)
        task_id = payload["task_id"]
        support_features, support_targets = _block_to_xy(payload["support"], view, f"{task_id}.support")
        query_features, query_targets = _block_to_xy(payload["query"], view, f"{task_id}.query")
        for k_shot in ks:
            if type(k_shot) is not int or k_shot < 0:
                raise AdaptationError(f"ks 必须是非负整数，实际 {k_shot!r}")
            subset_x, subset_y = _subset_support(
                support_features, support_targets, k_shot, task_id, seed
            )
            result = adapt_and_predict(
                artifact,
                {"features": subset_x, "targets": subset_y},
                {"features": query_features, "targets": query_targets},
                method=method,
                k_shot=k_shot,
                config=None,
            )
            results.append(result)
    return results


def _task_payload(task: Any, view: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(task, Mapping):
        payload = dict(task)
        if "task_id" not in payload:
            raise AdaptationError("任务字典缺少 task_id")
        if "support" not in payload or "query" not in payload:
            raise AdaptationError(f"任务 {payload['task_id']} 缺少 support/query")
        return payload
    # SyntheticTask：用任务族真值构造 support 池与 query 标签
    from .task_family import SyntheticTask

    if isinstance(task, SyntheticTask):
        context_names = view["context_names"] or ("context_1", "context_2")
        support_designs = task.support_designs()
        query_designs = task.query_designs()
        support_truth = task.truth(support_designs)
        query_truth = task.truth(query_designs)
        return {
            "task_id": task.task_id,
            "family": task.family,
            "split": task.split,
            "support": {
                "designs": support_designs,
                "task_context": dict(task.context),
                "targets": np.asarray(support_truth["objective"], dtype=np.float64),
            },
            "query": {
                "designs": query_designs,
                "task_context": dict(task.context),
                "targets": np.asarray(query_truth["objective"], dtype=np.float64),
            },
        }
    raise AdaptationError(f"无法识别的任务类型: {type(task).__name__}")


__all__ = [
    "ADAPTATION_METHODS",
    "DEFAULT_FINE_TUNING_STEPS",
    "DEFAULT_MAML_INNER_STEPS",
    "AdaptationError",
    "AdaptationResult",
    "adapt_and_predict",
    "predict_parameters",
    "run_k_shot_study",
]
