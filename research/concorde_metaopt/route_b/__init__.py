"""路线B：学习 BO 迭代采集决策的元策略原型（纯合成，physical_call_count=0）。

模块结构：

- contracts：数据契约与泄漏防护不变量；
- synthetic_tasks：合成类比任务分布（不是 12D Concorde 真实任务）；
- baselines：自建标准约束 BO 采集（EI/UCB/PI），未复用路线A采样器；
- policy：MetaAcquisitionPolicy 及其特征构造；
- trajectory_dataset：离线轨迹生成、manifest 与划分校验；
- policy_train：仅在 train 任务上训练、val 任务早停；
- policy_eval：固定初始点下与标准采集/随机/负控的配对评测。

显式声明：本包**没有**复用路线A WarmStartSampler 或任何 MAML 采样器；
路线B学的是序贯候选选择，不是初始点排序。
"""

from .contracts import (
    CandidatePool,
    EvaluatedPoint,
    LeakageError,
    ObservationHistory,
    PHYSICAL_CALL_COUNT,
    ProxyLabelError,
    RouteBContractError,
    SOURCE_SYNTHETIC_ANALOGUE,
    TaskContext,
)

__all__ = [
    "CandidatePool",
    "EvaluatedPoint",
    "LeakageError",
    "ObservationHistory",
    "PHYSICAL_CALL_COUNT",
    "ProxyLabelError",
    "RouteBContractError",
    "SOURCE_SYNTHETIC_ANALOGUE",
    "TaskContext",
]

__version__ = "route-b-2026-11-10"
