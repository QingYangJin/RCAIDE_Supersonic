"""S3 任务族（F-QE-conflict-v1）单元测试：族构造、证书、OOD/负控、族包/封存件、校准。"""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from research.concorde_metaopt.meta_learning import s3_prereg as sp
from research.concorde_metaopt.meta_learning import task_family as tf
from research.concorde_metaopt.tests import test_s3_support as support

DELTA1_BASE = 0.20
TASK_ID_RE = r"^p4ra-FQEC-v1-[0-9a-f]{16}$"


class S3TaskFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = tf.build_s3_conflict_family(delta1_base=DELTA1_BASE)
        cls.by_split = {}
        for task in cls.tasks:
            cls.by_split.setdefault(task.split, []).append(task)

    def test_01_split_counts_and_ids(self):
        self.assertEqual(len(self.tasks), 120)
        expected = dict(sp.S3_SPLIT_COUNTS)
        for split, count in expected.items():
            self.assertEqual(len(self.by_split[split]), count, split)
        ids = [task.task_id for task in self.tasks]
        self.assertEqual(len(set(ids)), len(ids))
        for task in self.tasks:
            self.assertRegex(task.task_id, TASK_ID_RE)
            self.assertNotIn("NC-", task.task_id)
            self.assertEqual(task.family, tf.S3_FAMILY_ID)
            self.assertEqual(task.formula_version, tf.S3_FORMULA_VERSION)
            self.assertRegex(task.task_fingerprint(), r"^[0-9a-f]{16}$")

    def test_02_design_bounds_shapes_and_no_leak(self):
        for task in self.tasks[:20]:
            support_designs = task.support_designs()
            query_designs = task.query_designs()
            self.assertEqual(support_designs.shape, (128, 12))
            self.assertEqual(query_designs.shape, (64, 12))
            self.assertTrue(np.all(support_designs >= 0.02 - 1e-12))
            self.assertTrue(np.all(support_designs <= 0.98 + 1e-12))
            overlap = np.max(np.abs(query_designs[:, None, :] - support_designs[None, :, :]), axis=2) <= 1e-12
            self.assertFalse(bool(overlap.any()), task.task_id)
            subset = task.support_subset(5, 20261107)
            self.assertEqual(subset.shape, (5, 12))

    def test_03_certificates_hold(self):
        for task in self.by_split["meta_validation"]:
            reference = task.reference()
            self.assertEqual(reference["reference_kind"], "POLYHEDRAL_KKT_CERTIFIED")
            self.assertLessEqual(abs(reference["kkt_residual"]), 1e-12)
            self.assertLessEqual(abs(reference["g1_star"]), 1e-12)
            self.assertLessEqual(abs(reference["g2_star"] + reference["margin_m"]), 1e-12)
            self.assertGreater(reference["objective_regret"], 1e-6)
            self.assertLessEqual(reference["assertion_residual"], 1e-10)
            self.assertEqual(reference["task_id"], task.task_id)
            cert = tf.s3_certificate(
                a=np.asarray(task.numeric_params()["a"], dtype=np.float64),
                c=np.asarray(task.numeric_params()["c"], dtype=np.float64),
                b1=np.asarray(task.numeric_params()["b1"], dtype=np.float64),
                b2=np.asarray(task.numeric_params()["b2"], dtype=np.float64),
                delta1=float(task.numeric_params()["delta1"]),
                m2=float(task.numeric_params()["m2"]),
            )
            tf.assert_s3_certificate(cert)

    def test_04_ood_shift_and_permutation(self):
        base = self.by_split["meta_test"]
        ood = self.by_split["meta_test_ood"]
        for index, task in enumerate(ood[:5]):
            numeric = task.numeric_params()
            base_numeric = base[index].numeric_params()
            self.assertAlmostEqual(float(numeric["delta1"]), DELTA1_BASE + tf.S3_OOD_DELTA1_SHIFT, places=12)
            self.assertNotEqual(list(numeric["b1"]), list(base_numeric["b1"]))
            self.assertGreater(float(task.params.get("ood_flag", 0.0)), 0.5)
        deltas = [float(task.numeric_params()["delta1"]) for task in ood]
        self.assertTrue(all(abs(value - (DELTA1_BASE + tf.S3_OOD_DELTA1_SHIFT)) <= 1e-12 for value in deltas))

    def test_05_negative_control_labels_shuffled_only(self):
        sources = {task.task_id: task for task in self.by_split["meta_test"]}
        negatives = self.by_split["meta_test_negative_control"]
        self.assertEqual(len(negatives), 10)
        for task in negatives:
            source = sources[task.params["source_task_id"]]
            self.assertTrue(task.is_negative_control)
            self.assertEqual(task.reference_kind, "LABEL_SHUFFLED_NO_REFERENCE")
            self.assertEqual(task.split, "meta_test_negative_control")
            self.assertTrue(np.array_equal(task.support_designs(), source.support_designs()))
            self.assertTrue(np.array_equal(task.query_designs(), source.query_designs()))
            permutation = np.asarray(task.params["query_permutation"], dtype=np.int64)
            self.assertEqual(sorted(permutation.tolist()), list(range(64)))
            truth_nc = task.truth(task.query_designs())
            truth_src = source.truth(source.query_designs())
            for row in range(3):
                self.assertAlmostEqual(float(truth_nc["objective"][row]), float(truth_src["objective"][permutation[row]]), places=9)
                self.assertAlmostEqual(float(truth_nc["g1"][row]), float(truth_src["g1"][permutation[row]]), places=9)
            with self.assertRaises(tf.TaskFamilyError):
                task.reference()

    def test_06_family_package_write_and_sha(self):
        package = tf.build_s3_family_package(
            self.tasks,
            delta1_base=DELTA1_BASE,
            created_utc=support.CREATED_UTC,
            code_sha="0" * 64,
        )
        self.assertNotIn("family_package_sha256", package)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "family_package.json"
            info = tf.write_s3_family_package(path, package)
            raw = path.read_bytes()
            self.assertEqual(info["family_package_sha256"], support.sha256_bytes(raw))
            self.assertEqual(info["bytes"], len(raw))
            loaded = json.loads(raw.decode("utf-8"))
            self.assertEqual(loaded["schema_version"], tf.S3_FAMILY_PACKAGE_SCHEMA_VERSION)
            self.assertEqual(loaded["family_id"], tf.S3_FAMILY_ID)
            self.assertEqual(loaded["split_counts"], dict(sp.S3_SPLIT_COUNTS))
            self.assertEqual(loaded["task_ids_sha256"], support.sha256_text("\n".join(sorted(task.task_id for task in self.tasks))))
            by_id = {row["task_id"]: row for row in loaded["tasks"]}
            for task in self.tasks[:10]:
                self.assertEqual(by_id[task.task_id]["task_fingerprint"], task.task_fingerprint())

    def test_07_references_sealed(self):
        references = tf.build_s3_references_sealed(self.tasks)
        self.assertEqual(references["schema_version"], tf.S3_REFERENCES_SEALED_SCHEMA_VERSION)
        self.assertEqual(references["n_references"], 110)
        self.assertEqual(len(references["references"]), 110)
        self.assertEqual(references["physical_call_count"], 0)
        ids = [row["task_id"] for row in references["references"]]
        self.assertEqual(len(set(ids)), 110)
        nc_ids = {task.task_id for task in self.by_split["meta_test_negative_control"]}
        self.assertFalse(nc_ids & set(ids))
        for row in references["references"][:5]:
            self.assertRegex(row["reference_digest"], r"^[0-9a-f]{32}$")
            self.assertIn("u_star", row)
            self.assertGreater(row["objective_regret"], 0.0)

    def test_08_calibration_candidate(self):
        record = tf.evaluate_s3_delta1_candidate(DELTA1_BASE, validation_count=20, grid_points=4096)
        self.assertEqual(record["certificate_pass"], 20)
        self.assertEqual(record["grid_all_infeasible_tasks"], 0)
        self.assertGreaterEqual(record["support_feasible_min_points"], 1)
        self.assertGreater(record["margin_mean"], 0.0)
        self.assertGreater(record["regret_median"], 1e-6)
        ok, reasons = tf.check_s3_calibration_candidate(record)
        self.assertTrue(ok, reasons)
        bad = dict(record)
        bad["grid_all_infeasible_tasks"] = 1
        bad_ok, bad_reasons = tf.check_s3_calibration_candidate(bad)
        self.assertFalse(bad_ok)
        self.assertTrue(bad_reasons)

    def test_09_task_fingerprint_hash_vector_v04(self):
        vectors = support.load_hash_vectors()
        vector = support.vector_by_id(vectors, "V04")
        self.assertEqual(vector["algorithm"], "task_fingerprint")
        actual = tf.s3_task_fingerprint(**vector["input"])
        self.assertEqual(actual, vector["expected_sha256"])

    def test_10_invalid_inputs(self):
        with self.assertRaises(tf.TaskFamilyError):
            tf.build_s3_conflict_family(delta1_base=-0.1)
        task = self.by_split["meta_validation"][0]
        with self.assertRaises(tf.TaskFamilyError):
            task.support_subset(129, 1)
        with self.assertRaises(tf.TaskFamilyError):
            self.by_split["meta_test_negative_control"][0].reference()


if __name__ == "__main__":
    unittest.main()
