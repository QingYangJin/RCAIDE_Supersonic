"""Make the repository root importable when pytest is started from anywhere."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

#: 12D 提升面设计空间配置（frozen: false，边界为 provisional）。
DESIGN_SPACE_12D = (
    ROOT / "research" / "concorde_metaopt" / "configs" / "design_space_12d_lifting_surfaces.yaml"
)


@pytest.fixture(scope="session")
def design_space_12d():
    """加载 12D 提升面设计空间（W01–W10 + V01–V02）。"""
    from research.concorde_metaopt.aircraft.design_space import load_design_space

    return load_design_space(DESIGN_SPACE_12D)


@pytest.fixture(scope="session")
def fixed_cruise_task():
    """加载冻结的固定巡航任务（Mach 2.02 / 18288 m / 3028020 m / 136000 kg）。"""
    from research.concorde_metaopt.tasks.task_spec import load_task_spec

    return load_task_spec()


@pytest.fixture()
def mock_evaluator(design_space_12d, fixed_cruise_task):
    """F1 合成评价器（物理调用恒为 0）。"""
    from research.concorde_metaopt.f_line import MockEvaluator

    return MockEvaluator(design_space_12d, fixed_cruise_task)


@pytest.fixture()
def archive_replay_evaluator(design_space_12d, fixed_cruise_task):
    """F1 归档 replay 评价器（只读 geometry-check-p1-20261028T1835 归档）。"""
    from research.concorde_metaopt.f_line import ArchiveReplayEvaluator

    return ArchiveReplayEvaluator(design_space_12d, fixed_cruise_task)
