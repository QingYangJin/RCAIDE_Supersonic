"""P4 元学习离线实验包（SYNTHETIC_ONLY，physical_call_count=0）。

本包只包含结构代码、合成元训练与离线 BO-DE 对照；权威合同见
docs/planning/p4_meta_learning_design_20261102.md v1.1。
"""
from __future__ import annotations

__version__ = "0.1.0"
PACKAGE_NAME = "research.concorde_metaopt.meta_learning"
STAGE = "P4-CODE"
DATA_ORIGIN = "SYNTHETIC_TEST"
PHYSICAL_CALL_COUNT_EXPECTED = 0

__all__ = ["__version__", "PACKAGE_NAME", "STAGE", "DATA_ORIGIN", "PHYSICAL_CALL_COUNT_EXPECTED"]
