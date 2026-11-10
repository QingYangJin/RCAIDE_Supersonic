"""路线B单元测试（2/2）：数据集哈希、训练/验证任务隔离、评测负控与泄漏拦截。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.route_b.contracts import LeakageError, RouteBContractError
from research.concorde_metaopt.route_b.policy import MetaAcquisitionPolicy
from research.concorde_metaopt.route_b.policy_eval import (
    ArmSpec,
    evaluate_arms,
    run_closed_loop,
)
from research.concorde_metaopt.route_b.policy_train import train_policy
from research.concorde_metaopt.route_b.synthetic_tasks import make_task
from research.concorde_metaopt.route_b.trajectory_dataset import build_dataset, load_dataset, write_dataset

POOL = 64


def _train_tasks(n: int = 4):
    return [
        make_task("synth-train-%02d" % index, "train", index, budget=8, pool_size=POOL)
        for index in range(n)
    ]


class DatasetAndTrainingTest(unittest.TestCase):
    def test_manifest_detects_tampering(self) -> None:
        tasks = _train_tasks(4)
        payload = build_dataset(tasks, behaviors=("random",), budget=8, n_init=4, seeds=(0,))
        directory = Path(tempfile.mkdtemp(prefix="route-b-dataset-"))
        manifest = write_dataset(payload, directory)
        self.assertEqual(manifest["n_records"], len(payload["records"]))
        dataset_file = directory / manifest["file"]
        dataset_file.write_text(dataset_file.read_text(encoding="utf-8") + "{}\n", encoding="utf-8")
        with self.assertRaises(RouteBContractError):
            load_dataset(directory)

    def test_training_task_isolation_and_policy_roundtrip(self) -> None:
        tasks = _train_tasks(4)
        payload = build_dataset(tasks, behaviors=("random",), budget=8, n_init=4, seeds=(0, 1))
        directory = Path(tempfile.mkdtemp(prefix="route-b-train-"))
        write_dataset(payload, directory / "trajectory_dataset")
        report = train_policy(directory / "trajectory_dataset", directory / "policy_train", epochs=25, seed=0)
        train_ids = {task.context.task_id for task in tasks}
        fit_ids, val_ids = set(report["fit_task_ids"]), set(report["val_task_ids"])
        self.assertFalse(fit_ids & val_ids, "训练/验证任务不得重叠")
        self.assertTrue(fit_ids | val_ids <= train_ids, "只允许 train 划分任务参与训练")
        self.assertNotIn("synth-val-00", fit_ids | val_ids)
        self.assertNotIn("synth-test-00", fit_ids | val_ids)
        self.assertEqual(report["physical_call_count"], 0)

        params = json.loads((directory / "policy_train" / "policy.json").read_text(encoding="utf-8"))
        self.assertTrue(params["trained"])
        policy = MetaAcquisitionPolicy.from_params(params)
        history_task = tasks[0]
        from research.concorde_metaopt.route_b.contracts import ObservationHistory
        from research.concorde_metaopt.route_b.synthetic_tasks import initial_design

        history = ObservationHistory(history_task.dim, history_task.context)
        for design in initial_design(history_task, n_init=4, seed=0):
            outcome = history_task.evaluate(design)
            history.add_evaluated(design, outcome["objective"], outcome["constraints"])
        first = policy.score(history, history_task.pool, history_task.context)
        reloaded = MetaAcquisitionPolicy.from_params(json.loads(json.dumps(params)))
        second = reloaded.score(history, history_task.pool, history_task.context)
        import numpy as np

        np.testing.assert_allclose(first, second, rtol=0, atol=0)


class EvalNegativeControlTest(unittest.TestCase):
    def test_eval_rejects_train_tasks(self) -> None:
        train_task = _train_tasks(1)[0]
        policy = MetaAcquisitionPolicy(22, seed=0)
        with self.assertRaises(LeakageError):
            run_closed_loop(train_task, policy, budget=8, n_init=4, seed=0)

    def test_negative_controls_and_inconclusive_verdict(self) -> None:
        tasks = [make_task("synth-test-00", "test", 0, budget=8, pool_size=POOL)]
        arms = [
            ArmSpec("learned", "meta_policy", "未训练参数占位（仅测比较逻辑）"),
            ArmSpec("ei", "standard_bo", "约束 EI"),
            ArmSpec("random", "negative_control", "随机候选"),
            ArmSpec("random_score", "negative_control", "同路径随机评分"),
            ArmSpec("untrained", "negative_control", "未训练同结构网络"),
        ]
        placeholder = MetaAcquisitionPolicy(22, seed=0).to_params()
        payload = evaluate_arms(tasks, trained_params=placeholder, arms=arms, budget=8, n_init=4, seed=0)
        rows = {(row["arm"], row["task_id"]): row for row in payload["rows"]}
        random_row = rows[("random", "synth-test-00")]
        score_row = rows[("random_score", "synth-test-00")]
        self.assertEqual(random_row["total_reward"], score_row["total_reward"])
        check = payload["negative_control_check"]
        self.assertIn(check["status"], ("PASS", "WARN"))
        self.assertLessEqual(check["delta_untrained_minus_random_total_reward"], 0.05 + 1e-9)
        self.assertEqual(payload["primary_comparison"]["verdict"], "INCONCLUSIVE")
        self.assertEqual(payload["physical_call_count"], 0)


if __name__ == "__main__":
    unittest.main()
