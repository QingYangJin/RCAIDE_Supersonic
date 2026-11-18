"""NumPy/spy isolation tests; no executed torch gradient or physical evidence."""
from dataclasses import replace
import unittest
from unittest.mock import patch
import numpy as np

from research.concorde_metaopt.meta_learning import maml
from research.concorde_metaopt.dreal001.meta.meta_dataset import TrainNormalizer
from research.concorde_metaopt.dreal001.meta.production import AdaptationRunner, WarmStartSampler
from research.concorde_metaopt.dreal001.meta.task_spec import ContractError
from research.concorde_metaopt.tests.test_recovery_meta_contracts import fixture


class AdaptationIsolationTests(unittest.TestCase):
    def setUp(self):
        self.data = fixture()
        self.norm = TrainNormalizer.fit(self.data)
        self.config = maml.MAMLConfig(input_dim=12, output_dim=1, hidden_sizes=(8,), seed=17)
        self.params = maml.init_parameters(self.config)
        self.support = self.data.usable("fixture-3", "support")
        self.query = np.asarray([r.design for r in self.data.usable("fixture-3", "query")])

    def predict(self, support=None, query=None, params=None, config=None):
        return AdaptationRunner().predict(
            self.params if params is None else params, config=self.config if config is None else config,
            normalizer=self.norm, support_rows=self.support if support is None else support,
            query_designs=self.query if query is None else query)

    def rejected_before_gradient(self, message, **kwargs):
        with patch.object(maml, "inner_adapt") as inner:
            with self.assertRaisesRegex(ContractError, message):
                self.predict(**kwargs)
            inner.assert_not_called()

    def test_query_support_overlap_rejected_before_gradient(self):
        self.rejected_before_gradient("leakage", query=np.asarray([self.support[0].design]))

    def test_near_duplicate_query_rejected(self):
        query = np.asarray([self.support[0].design]) + 5e-13
        self.rejected_before_gradient("leakage", query=query)

    def test_duplicate_support_design_rejected(self):
        extra = replace(self.support[0], observation_id="new-id")
        self.rejected_before_gradient("duplicate adaptation support design", support=self.support + (extra,))

    def test_duplicate_support_identity_rejected(self):
        extra = replace(self.support[1], observation_id=self.support[0].observation_id)
        self.rejected_before_gradient("observation identity", support=(self.support[0], extra))

    def test_failed_support_rejected(self):
        self.rejected_before_gradient("successful support", support=(replace(self.support[0], status="failed", di_n=None),))

    def test_query_partition_not_allowed_as_support(self):
        self.rejected_before_gradient("successful support", support=self.data.usable("fixture-3", "query"))

    def test_multiple_tasks_rejected(self):
        self.rejected_before_gradient("one task", support=(self.support[0], self.data.usable("fixture-2", "support")[1]))

    def test_declared_real_support_is_not_admitted(self):
        self.rejected_before_gradient("rejects real", support=tuple(replace(r, source_kind="vspaero_raw") for r in self.support))

    def test_malformed_query_rejected_before_gradient(self):
        for query in (np.empty((0, 12)), np.ones((1, 11)), np.full((1, 12), np.nan)):
            with self.subTest(shape=query.shape):
                self.rejected_before_gradient("nonempty finite", query=query)

    def test_model_dimension_rejected(self):
        self.rejected_before_gradient("12D/Di_N", config=maml.MAMLConfig(input_dim=13, output_dim=1))

    def test_k_zero_uses_numpy_forward_without_inner_adaptation(self):
        x = (self.query - self.norm.x_mean) / self.norm.x_scale
        p = self.params.tensors
        expected = (np.tanh(x @ p[0] + p[1]) @ p[2] + p[3])[:, 0]
        expected = expected * self.norm.y_scale + self.norm.y_mean
        before = [v.copy() for v in p]
        with patch.object(maml, "inner_adapt") as inner:
            actual = self.predict(support=())
            inner.assert_not_called()
        np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0)
        for a, b in zip(before, p):
            np.testing.assert_array_equal(a, b)

    def test_support_only_arguments_reach_gradient_spy(self):
        # This is an argument-isolation spy, NOT backend gradient verification.
        with patch.object(maml, "inner_adapt", return_value=(self.params, [])) as inner:
            prediction = self.predict()
        episode = inner.call_args.args[1]
        sx, sy = self.norm.arrays(self.support)
        np.testing.assert_array_equal(episode.support_features, sx)
        np.testing.assert_array_equal(episode.support_targets, sy)
        np.testing.assert_array_equal(episode.query_targets, np.zeros((1, 1)))
        self.assertEqual(prediction.shape, (4,))

    def test_nonfinite_output_rejected(self):
        tensors = [v.copy() for v in self.params.tensors]
        tensors[-1][:] = 1e308
        self.norm = replace(self.norm, y_scale=1e308)
        with self.assertRaisesRegex(ContractError, "nonfinite adaptation"):
            self.predict(support=(), params=maml.ParameterSet(tensors))

    def test_normalizer_owns_read_only_arrays(self):
        mean = np.zeros(12)
        scale = np.ones(12)
        norm = TrainNormalizer(mean, scale, 0., 1., ("train-observation",))
        mean[:] = 90
        scale[:] = 0
        np.testing.assert_array_equal(norm.x_mean, np.zeros(12))
        np.testing.assert_array_equal(norm.x_scale, np.ones(12))
        with self.assertRaises(ValueError):
            norm.x_mean[0] = 9

    def test_malformed_normalizer_rejected(self):
        for changes in ({"x_scale": np.zeros(12)}, {"x_mean": np.ones(11)},
                        {"y_scale": 0.}, {"y_mean": float("nan")},
                        {"fit_observation_ids": ()}, {"fit_observation_ids": ("x", "x")}):
            with self.subTest(changes=changes):
                with self.assertRaises(ContractError):
                    replace(self.norm, **changes)

    def test_failed_observation_cannot_be_normalized(self):
        with self.assertRaisesRegex(ContractError, "successful observations"):
            self.norm.arrays((replace(self.support[0], status="failed", di_n=None),))

    def test_warm_start_excludes_all_previously_evaluated_designs(self):
        candidates = np.asarray([[0.] * 12, [1.] * 12, [2.] * 12, [3.] * 12])
        selected = WarmStartSampler().select(candidates, np.arange(4.), 2,
                                             evaluated_designs=candidates[:2])
        np.testing.assert_array_equal(selected, candidates[2:])

    def test_evaluated_near_duplicate_also_excluded(self):
        candidates = np.asarray([[0.] * 12, [1.] * 12])
        with self.assertRaisesRegex(ContractError, "not enough unique"):
            WarmStartSampler().select(candidates, np.arange(2.), 2,
                                      evaluated_designs=candidates[:1] + 5e-13)

    def test_invalid_evaluated_designs_rejected(self):
        for evaluated in (np.ones((2, 11)), np.full((1, 12), np.nan)):
            with self.assertRaisesRegex(ContractError, "evaluated designs"):
                WarmStartSampler().select(self.query, np.arange(4.), 1, evaluated_designs=evaluated)


if __name__ == "__main__":
    unittest.main()
