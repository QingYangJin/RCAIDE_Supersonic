"""P4 元学习合成任务族单元测试（设计 §4 / §12-5、11、13 的非物理断言）。

覆盖：同 seed 逐位复现、五集合互斥、support/query 不相交、参考解断言、
标签确定性、拒绝采样记录、负控制协议、四族可构造。
"""
import json
import unittest

import numpy as np

from research.concorde_metaopt.meta_learning import task_family as tf
from research.concorde_metaopt.meta_learning.data_contract import CONSTRAINT_NAMES


def small_config(family_id="F-QE", **overrides):
    """极小任务族配置：2/1/2/1/1，support=16、query=8（剩余预算可控）。"""
    base = dict(
        family_id=family_id,
        train_tasks=2,
        validation_tasks=1,
        test_tasks=2,
        ood_tasks=1,
        negative_control_tasks=1,
        support_pool_size=16,
        query_size=8,
        designs_per_task=24,
    )
    base.update(overrides)
    return tf.default_task_family_config(**base)


def check_tolerance(config):
    return float(config.reference_tolerance)


class TaskFamilyBuildTests(unittest.TestCase):
    def setUp(self):
        self.config = small_config()
        self.tasks = tf.build_task_family(self.config)

    def test_01_build_reproducible(self):
        again = tf.build_task_family(small_config())
        self.assertEqual([task.task_id for task in self.tasks], [task.task_id for task in again])
        self.assertEqual(
            [tf.serialize_task(task) for task in self.tasks],
            [tf.serialize_task(task) for task in again],
        )

    def test_02_split_counts_and_disjoint(self):
        groups = {}
        for task in self.tasks:
            groups.setdefault(task.split, []).append(task)
        self.assertEqual(len(groups["meta_train"]), 2)
        self.assertEqual(len(groups["meta_validation"]), 1)
        self.assertEqual(len(groups["meta_test"]), 2)
        self.assertEqual(len(groups["meta_test_ood"]), 1)
        self.assertEqual(len(groups["negative_control"]), 1)
        ids = {split: {task.task_id for task in members} for split, members in groups.items()}
        splits = list(ids)
        for i in range(len(splits)):
            for j in range(i + 1, len(splits)):
                self.assertFalse(ids[splits[i]] & ids[splits[j]], f"{splits[i]} 与 {splits[j]} 泄漏")
        self.assertEqual(len({task.task_id for task in self.tasks}), len(self.tasks))

    def test_03_negative_control_ids(self):
        negatives = [task for task in self.tasks if task.split == "negative_control"]
        for task in negatives:
            self.assertTrue(task.is_negative_control)
            self.assertTrue(task.task_id.startswith("NC-"))
            self.assertEqual(len(task.task_id), 13)  # "NC-" + sha1[:10]
            self.assertIn("source_task_id", task.params)
            self.assertEqual(task.params["shuffle_seed"], 20261102)

    def test_04_support_query_disjoint(self):
        for task in self.tasks:
            if task.is_negative_control:
                continue
            support = task.support_designs()
            query = task.query_designs()
            self.assertEqual(support.shape, (16, 12))
            self.assertEqual(query.shape, (8, 12))
            for left in support:
                for right in query:
                    self.assertGreater(float(np.max(np.abs(left - right))), 1e-12)

    def test_05_designs_deterministic(self):
        again = tf.build_task_family(small_config())
        for task, rebuilt in zip(self.tasks, again):
            np.testing.assert_array_equal(task.support_designs(), rebuilt.support_designs())
            np.testing.assert_array_equal(task.query_designs(), rebuilt.query_designs())

    def test_06_reference_solutions_pass(self):
        residuals = tf.assert_reference_solutions(self.tasks)
        self.assertTrue(residuals)
        tolerance = check_tolerance(self.config)
        for task_id, residual in residuals.items():
            self.assertLessEqual(float(residual), tolerance, f"{task_id} 参考解残差超限")

    def test_07_truth_contract(self):
        task = [item for item in self.tasks if item.split == "meta_train"][0]
        designs = task.support_designs()
        truth = task.truth(designs)
        enabled = task.enabled_constraint_names
        self.assertEqual(len(enabled), 1)
        self.assertIn(enabled[0], CONSTRAINT_NAMES[:3])
        self.assertEqual(truth["objective"].shape, (16,))
        self.assertTrue(np.isfinite(truth["objective"]).all())
        for name in enabled:
            self.assertEqual(truth[name].shape, (16,))
            self.assertTrue(np.isfinite(truth[name]).all())
        self.assertEqual(truth["feasibility"].dtype, bool)
        again = task.truth(designs)
        np.testing.assert_array_equal(truth["objective"], again["objective"])
        np.testing.assert_array_equal(truth["feasibility"], again["feasibility"])

    def test_08_reference_detail(self):
        task = [item for item in self.tasks if item.split == "meta_train"][0]
        detail = task.reference()
        self.assertIsInstance(detail["reference_kind"], str)
        self.assertTrue(detail["reference_kind"].strip())
        self.assertEqual(len(detail["u_star"]), 12)
        self.assertTrue(np.isfinite(detail["objective_star"]))
        self.assertLessEqual(float(detail["assertion_residual"]), check_tolerance(self.config))
        self.assertIn("feasible", detail)

    def test_09_rejection_sampling_recorded(self):
        for task in self.tasks:
            if task.is_negative_control:
                continue
            self.assertIn("reference_rejections", task.params)
            self.assertIsInstance(task.params["reference_rejections"], int)
            self.assertGreaterEqual(task.params["reference_rejections"], 0)

    def test_10_negative_control_shuffle_semantics(self):
        negatives = [task for task in self.tasks if task.is_negative_control]
        self.assertEqual(len(negatives), 1)
        negative = negatives[0]
        sources = [task for task in self.tasks if task.task_id == negative.params["source_task_id"]]
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source.split, "meta_train")
        designs = negative.support_designs()
        np.testing.assert_array_equal(designs, source.support_designs())
        pool = np.vstack([source.support_designs(), source.query_designs()])
        nc_truth = negative.truth(pool)["objective"]
        source_truth = source.truth(pool)["objective"]
        # 负控制只打乱标签配对：全池目标值多重集合不变
        np.testing.assert_allclose(np.sort(nc_truth), np.sort(source_truth), rtol=0.0, atol=1e-12)
        permutation = list(negative.params["permutation"])
        self.assertEqual(sorted(permutation), list(range(len(permutation))))
        if permutation != list(range(len(permutation))):
            self.assertFalse(np.allclose(nc_truth, source_truth))

    def test_11_negative_control_id_formula(self):
        import hashlib

        negative = [task for task in self.tasks if task.is_negative_control][0]
        shuffle_seed = negative.params["shuffle_seed"]
        payload = f"negative_control|{negative.params['source_task_id']}|{shuffle_seed}"
        expected = "NC-" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
        self.assertEqual(negative.task_id, expected)

    def test_12_serialize_json(self):
        payload = [tf.serialize_task(task) for task in self.tasks]
        text = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(json.loads(text), payload)

    def test_13_family_fingerprint(self):
        fingerprint = tf.family_fingerprint(self.config)
        self.assertEqual(fingerprint, tf.family_fingerprint(small_config()))
        self.assertNotEqual(fingerprint, tf.family_fingerprint(small_config(seed=20261103)))
        self.assertIsInstance(fingerprint, str)
        self.assertEqual(len(fingerprint), 64)


class TaskFamilyVariantTests(unittest.TestCase):
    def _build(self, family_id):
        config = small_config(
            family_id,
            validation_tasks=1,
            test_tasks=1,
            ood_tasks=1,
            negative_control_tasks=0,
        )
        return config, tf.build_task_family(config)

    def test_01_linear_family_constraints(self):
        config, tasks = self._build("F-LIN")
        task = tasks[0]
        self.assertEqual(tuple(task.enabled_constraint_names), tuple(CONSTRAINT_NAMES[:2]))
        residuals = tf.assert_reference_solutions(tasks)
        self.assertLessEqual(max(residuals.values()), check_tolerance(config))

    def test_02_rastrigin_family_reference(self):
        config, tasks = self._build("F-NC")
        task = tasks[0]
        detail = task.reference()
        self.assertEqual(detail["reference_kind"], "ANALYTIC_RASTRIGIN")
        self.assertAlmostEqual(float(detail["objective_star"]), 0.0, places=9)
        center = np.asarray(task.params["c"], dtype=float)
        np.testing.assert_allclose(np.asarray(detail["u_star"], dtype=float), center, atol=1e-12)
        self.assertLessEqual(max(tf.assert_reference_solutions(tasks).values()), check_tolerance(config))

    def test_03_multifidelity_family_kkt(self):
        config, tasks = self._build("F-MF")
        task = tasks[0]
        detail = task.reference()
        self.assertEqual(detail["reference_kind"], "KKT_CERTIFIED_NUMERIC")
        self.assertLess(float(task.params["reference_kkt_residual"]), 1e-9)
        self.assertLessEqual(max(tf.assert_reference_solutions(tasks).values()), check_tolerance(config))

    def test_04_invalid_config_rejected(self):
        import tempfile
        from pathlib import Path

        config = small_config()
        with self.assertRaises(tf.TaskFamilyError):
            tf.default_task_family_config(designs_per_task=25)
        with self.assertRaises(tf.TaskFamilyError):
            tf.default_task_family_config(train_tasks=1, negative_control_tasks=2)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "family.json"
            path.write_text(json.dumps({"family_id": "F-QE", "bogus": 1}), encoding="utf-8")
            with self.assertRaises(tf.TaskFamilyError):
                tf.load_task_family_config(path)
            payload = {name: getattr(config, name) for name in tf.TaskFamilyConfig.__dataclass_fields__}
            payload["context_names"] = list(payload["context_names"])
            payload["family_id"] = "NOT-A-FAMILY"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(tf.TaskFamilyError):
                tf.load_task_family_config(path)

    def test_05_sample_designs_api(self):
        _, tasks = self._build("F-QE")
        task = tasks[0]
        designs = tf.sample_designs(task, 5, "lhs", 0)
        self.assertEqual(designs.shape, (5, 12))
        self.assertTrue(((designs >= 0.0) & (designs <= 1.0)).all())
        np.testing.assert_array_equal(designs, tf.sample_designs(task, 5, "lhs", 0))
        with self.assertRaises(tf.TaskFamilyError):
            tf.sample_designs(task, -1, "lhs", 0)
        with self.assertRaises(tf.TaskFamilyError):
            tf.sample_designs(task, 3, "bogus", 0)


if __name__ == "__main__":
    unittest.main()
