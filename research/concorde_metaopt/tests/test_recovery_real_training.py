import numpy as np
import pytest
from research.concorde_metaopt.dreal001.meta.meta_dataset import MetaDataset, Observation
from research.concorde_metaopt.dreal001.meta.real_training import RealFOMALMTrainer, RealAdaptationRunner
from research.concorde_metaopt.dreal001.meta.task_spec import ContractError, TaskSpec
from research.concorde_metaopt.meta_learning.maml import MAMLConfig, init_parameters

GEOM = "5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15"


def fixture():
    tasks = (
        TaskSpec("t1", "train", 1.6, 18288.0, 12851.4, 1333704.4, GEOM),
        TaskSpec("t2", "train", 1.8, 18288.0, 16265.1, 1333704.4, GEOM),
        TaskSpec("v1", "val", 2.0, 18288.0, 20000.0, 1333704.4, GEOM),
        TaskSpec("s1", "test", 2.2, 18288.0, 24000.0, 1333704.4, GEOM),
    )
    rows = (
        Observation("o1", "t1", tuple([1.0] * 12), "support", "synthetic_fixture", "ok", 1.0),
        Observation("o2", "t1", tuple([2.0] * 12), "query", "synthetic_fixture", "ok", 2.0),
    )
    return MetaDataset(tasks, rows)


def test_real_trainer_rejects_unadmitted_fixture():
    with pytest.raises(ContractError, match="REAL_ADMISSION_NOT_IMPLEMENTED"):
        RealFOMALMTrainer().fit(fixture(), config=MAMLConfig(12, 1, hidden_sizes=(4,)), max_steps=1)


def test_real_adaptation_rejects_synthetic_rows():
    cfg = MAMLConfig(12, 1, hidden_sizes=(4,))
    rows = fixture().rows
    normalizer = type("N", (), {"x_mean": np.zeros(12), "x_scale": np.ones(12),
                                "y_mean": 0.0, "y_scale": 1.0})()
    with pytest.raises(ContractError, match="synthetic"):
        RealAdaptationRunner().predict(init_parameters(cfg), config=cfg,
                                       normalizer=normalizer,
                                       support_rows=rows[:1], query_designs=np.ones((1, 12)),
                                       task_id="t1")
