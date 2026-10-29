"""Frozen task contracts for the Concorde Phase I meta-optimisation."""

from .task_spec import (
    DEFAULT_TASK_CONFIG_PATH,
    FixedCruiseTask,
    TASK_SPEC_VERSION,
    TaskSpecError,
    load_task_spec,
)

__all__ = [
    "DEFAULT_TASK_CONFIG_PATH",
    "FixedCruiseTask",
    "TASK_SPEC_VERSION",
    "TaskSpecError",
    "load_task_spec",
]
