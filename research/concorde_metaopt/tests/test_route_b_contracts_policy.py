"""路线B单元测试（1/2）：契约、泄漏防护、策略输出与特征前缀一致性。

这些测试全部只跑合成任务，physical_call_count=0，不触发任何物理求解器。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from research.concorde_metaopt.route_b.baselines import design_key
from research.concorde_metaopt.route_b.contracts import (
    EvaluatedPoint,
    LeakageError,
    ObservationHistory,
    ProxyLabelError,
    RouteBContractError,
    TaskContext,
)
from research.concorde_metaopt.route_b.policy import (
    MetaAcquisitionPolicy,
    RandomScorePolicy,
    build_features,
    feature_dim,
    feature_names,
)
from research.concorde_metaopt.route_b.synthetic_tasks import (
    DEFAULT_BUDGET,
    DEFAULT_N_INIT,
    SyntheticTask,
    initial_design,
    make_task,
    make_task_split,
)
from research.concorde_metaopt.route_b.trajectory_dataset import (
    build_dataset,
    collect_trajectory,
    make_behavior,
    split_by_task,
)

POOL = 64


def _task(task_id: str = "synth-train-00", split: str = "train") -> SyntheticTask:
    return make_task(task_id, split, 0, budget=8, pool_size=POOL)


class ContractsTest(unittest.TestCase):
    def test_proxy_label_rejected(self) -> None:
        with self.assertRaises(ProxyLabelError):
            EvaluatedPoint(design=(0.5,) * 6, objective=1.0, constraints=(-0.1,), source="surrogate_proxy")
        history = ObservationHistory(6, _task().context)
        with self.assertRaises(ProxyLabelError):
            history.append(EvaluatedPoint(design=(0.5,) * 6, objective=1.0, constraints=(-0.1,), source="proxy"))
        history.add_evaluated((0.4,) * 6, 1.0, (-0.1,))
        self.assertEqual(history.n, 1)

    def test_history_rejects_duplicate_design(self) -> None:
        history = ObservationHistory(6, _task().context)
        history.add_evaluated((0.4,) * 6, 1.0, (-0.1,))
        with self.assertRaises(RouteBContractError):
            history.add_evaluated((0.4,) * 6, 0.5, (-0.2,))

    def test_physical_call_count_must_be_zero(self) -> None:
        with self.assertRaises(RouteBContractError):
            TaskContext(task_id="x", split="train", dim=6, budget=8, seed=1, physical_call_count=1)

    def test_context_features_do_not_encode_split_or_task_id(self) -> None:
        left = TaskContext(task_id="synth-train-00", split="train", dim=6, budget=8, seed=1)
        right = TaskContext(task_id="synth-test-99", split="test", dim=6, budget=8, seed=2)
        self.assertEqual(left.context_features(), right.context_features())

    def test_dataset_rejects_non_train_tasks(self) -> None:
        val_task = make_task("synth-val-00", "val", 0, budget=8, pool_size=POOL)
        with self.assertRaises(LeakageError):
            build_dataset([val_task], behaviors=("random",), budget=8, n_init=4, seeds=(0,))
        with self.assertRaises(LeakageError):
            collect_trajectory(val_task, "random", budget=8, n_init=4, seed=0)

    def test_split_by_task_rejects_overlap(self) -> None:
        records = [{"task_id": "a"}, {"task_id": "b"}]
        with self.assertRaises(LeakageError):
            split_by_task(records, ["a", "b"], ["b"])


class PolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.task = _task()
        self.history = ObservationHistory(self.task.dim, self.task.context)
        for design in initial_design(self.task, n_init=DEFAULT_N_INIT, seed=0):
            outcome = self.task.evaluate(design)
            self.history.add_evaluated(design, outcome["objective"], outcome["constraints"])

    def test_feature_dim_matches_names(self) -> None:
        features = build_features(self.history, self.task.pool, self.task.context)
        self.assertEqual(features.shape[0], len(self.task.pool))
        self.assertEqual(features.shape[1], feature_dim(self.task.dim))
        self.assertEqual(len(feature_names(self.task.dim)), feature_dim(self.task.dim))

    def test_policy_scores_are_finite_and_select_legal_index(self) -> None:
        policy = MetaAcquisitionPolicy(feature_dim(self.task.dim), seed=0)
        scores = policy.score(self.history, self.task.pool, self.task.context)
        self.assertEqual(scores.shape, (len(self.task.pool),))
        self.assertTrue(np.all(np.isfinite(scores)))
        index, _ = policy.select(self.history, self.task.pool, self.task.context, self.history.evaluated_keys())
        self.assertGreaterEqual(index, 0)
        self.assertLess(index, len(self.task.pool))
        self.assertNotIn(design_key(self.task.pool.designs[index]), self.history.evaluated_keys())

    def test_prefix_features_contain_no_future_labels(self) -> None:
        """决策时刻特征必须能由当时的前缀历史精确重算（不存在未来信息）。"""
        budget, n_init, seed = 8, DEFAULT_N_INIT, 0
        episode = collect_trajectory(self.task, "random", budget=budget, n_init=n_init, seed=seed)
        self.assertGreaterEqual(len(episode["decisions"]), 1)
        history = ObservationHistory(self.task.dim, self.task.context)
        behavior = make_behavior("random", seed)
        for design in initial_design(self.task, n_init=n_init, seed=seed):
            outcome = self.task.evaluate(design)
            history.add_evaluated(design, outcome["objective"], outcome["constraints"])
        for record in episode["decisions"]:
            features = build_features(history, self.task.pool, self.task.context)
            index, _ = behavior.select(history, self.task.pool, exclude_keys=history.evaluated_keys())
            self.assertEqual(design_key(self.task.pool.designs[index]), record["chosen_design_key"])
            expected = features[index]
            np.testing.assert_allclose(expected, np.asarray(record["features"], dtype=float), rtol=1e-9, atol=1e-9)
            design = self.task.pool.designs[index]
            outcome = self.task.evaluate(design)
            history.add_evaluated(design, outcome["objective"], outcome["constraints"])

    def test_random_score_policy_is_control_path(self) -> None:
        control = RandomScorePolicy(seed=3)
        scores = control.score(self.history, self.task.pool, self.task.context)
        self.assertEqual(scores.shape, (len(self.task.pool),))
        self.assertTrue(np.all(np.isfinite(scores)))


if __name__ == "__main__":
    unittest.main()
