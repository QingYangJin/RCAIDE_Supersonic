"""路线A：优化器无关热启动（warm start）共享采样接口（SYNTHETIC_ANALOGUE）。

模块边界（硬约束）：
* sampler.py 只负责“从候选池挑选初始设计”，不包含 BO 采集函数、
  DE 差分变异、PSO 速度更新；这些分别属于 optimization/baseline_bo.py、
  baseline_de.py、baseline_pso.py。
* 代理模型预测值只用于排序与可行性估计，绝不写入真实观测日志。
* 所有本包产物标注 physical_call_count=0 与 source_kind=SYNTHETIC_ANALOGUE。
"""
from .sampler import (  # noqa: F401
    SOURCE_FOMAML_KSHOT,
    SOURCE_PRETRAIN,
    SOURCE_RANDOM,
    SOURCE_ZERO_SHOT,
    ProposedDesigns,
    WarmStartConfig,
    WarmStartSampler,
)

__all__ = [
    "ProposedDesigns",
    "SOURCE_FOMAML_KSHOT",
    "SOURCE_PRETRAIN",
    "SOURCE_RANDOM",
    "SOURCE_ZERO_SHOT",
    "WarmStartConfig",
    "WarmStartSampler",
]
