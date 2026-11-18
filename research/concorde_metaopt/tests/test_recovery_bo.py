"""Executable GP mathematics and feedback tests, synthetic software only."""
import math
import unittest
import numpy as np
from research.concorde_metaopt.dreal001.optimizers.recovery_bo import (
    RecoveryGaussianProcessBO, expected_improvement, generate_initial_designs, BACKEND_ID)
from research.concorde_metaopt.dreal001.optimizers import arms
from research.concorde_metaopt.tests.test_recovery_feedback import FixtureHarness


class RecoveryBOTests(unittest.TestCase):
    def bo(self, seed=17):
        return RecoveryGaussianProcessBO(np.zeros(2), np.ones(2), seed=seed)

    def test_lhs_stratifies_each_dimension_and_is_reproducible(self):
        a = generate_initial_designs(np.zeros(12), np.ones(12), count=8, seed=17)
        b = generate_initial_designs(np.zeros(12), np.ones(12), count=8, seed=17)
        np.testing.assert_array_equal(a, b)
        for column in a.T:
            np.testing.assert_array_equal(np.sort((column * 8).astype(int)), np.arange(8))

    def test_ei_matches_closed_form_at_incumbent(self):
        ei = expected_improvement(np.array([0., 2., -2.]), np.array([1., 0., 0.]), 0.)
        np.testing.assert_allclose(ei, [1 / math.sqrt(2 * math.pi), 0, 2])

    def test_posterior_matches_direct_linear_algebra(self):
        bo = self.bo()
        for x, y in [([.2, .2], 10.), ([.8, .8], 30.)]:
            bo.tell(x, dict(objective=y, valid=True, feasible=True))
        x = np.array([[.2, .2], [.8, .8]])
        q = np.array([[.4, .5], [.6, .6]])
        kernel = lambda a,b: np.exp(-.5 * np.sum((a[:,None] - b[None,:])**2, axis=2) / .35**2)
        gram = kernel(x,x) + 1e-6 * np.eye(2)
        cross = kernel(x,q)
        mean, variance, center, scale = bo.posterior(q)
        np.testing.assert_allclose(mean, cross.T @ np.linalg.solve(gram, [-1., 1.]))
        np.testing.assert_allclose(variance, 1 - np.sum(cross * np.linalg.solve(gram, cross),axis=0))
        self.assertEqual((center, scale), (20.,10.))

    def test_failed_null_not_an_objective_observation(self):
        bo = self.bo()
        bo.tell([.2,.2], dict(objective=None, valid=False, feasible=False))
        proposal = bo.ask()
        self.assertEqual(proposal['acquisition']['objective_observations'], 0)
        self.assertEqual(proposal['acquisition']['strategy'], 'FEASIBILITY_WEIGHTED_UNCERTAINTY')
        self.assertIsNone(bo.rows[0][1])

    def test_rejects_penalty_nan_missing_flags_and_duplicates(self):
        for result in [dict(objective=1e9,valid=False,feasible=False),
                       dict(objective=float('nan'),valid=True,feasible=True),
                       dict(objective=1.,valid=True)]:
            with self.subTest(result=result), self.assertRaises(ValueError):
                self.bo().tell([.2,.2], result)
        bo = self.bo()
        result = dict(objective=1.,valid=True,feasible=True)
        bo.tell([.2,.2],result)
        with self.assertRaisesRegex(ValueError,'duplicate'):
            bo.tell([.2,.2],result)

    def test_observed_and_pending_proposals_are_not_repeated(self):
        bo = self.bo()
        vectors = []
        for _ in range(8):
            x = bo.ask()['design_vector']
            self.assertTrue(np.all((x >= 0) & (x <= 1)))
            self.assertFalse(any(np.allclose(x, old, rtol=0,atol=1e-12) for old in vectors))
            vectors.append(x)
        self.assertEqual(len(bo.pending), 8)
        bo.tell(vectors[0],dict(objective=1.,valid=True,feasible=True))
        self.assertEqual(len(bo.pending),7)

    def test_swapping_labels_changes_gp_acquisition(self):
        left,right = self.bo(), self.bo()
        for bo,values in [(left,[1.,10.]),(right,[10.,1.])]:
            for x,y in zip([[.2,.2],[.8,.8]],values):
                bo.tell(x,dict(objective=y,valid=True,feasible=True))
        self.assertFalse(np.array_equal(left.ask()['design_vector'],right.ask()['design_vector']))

    def test_executable_arm_uses_returned_feedback_without_mock_backend(self):
        spec = arms.ArmSpec('BO',budget_starts=6,initial_designs=2,seed=17)
        left,right = FixtureHarness([1.,10.],cap=6),FixtureHarness([10.,1.],cap=6)
        a,b = arms._run_bo(spec,left,None),arms._run_bo(spec,right,None)
        self.assertEqual(a['backend'],BACKEND_ID)
        self.assertEqual(a['acquisitions'],4)
        self.assertEqual(a['last_acquisition']['observations'],5)
        self.assertEqual(len(left.events),6)
        np.testing.assert_array_equal(left.events[0][0],right.events[0][0])
        self.assertFalse(np.array_equal(left.events[2][0],right.events[2][0]))
        self.assertEqual(b['backend'],BACKEND_ID)

    def test_invalid_configuration_and_design_rejected(self):
        for kwargs in [dict(length_scale=0),dict(candidate_count=1),dict(noise_variance=float('nan'))]:
            with self.assertRaises(ValueError):
                RecoveryGaussianProcessBO(np.zeros(2),np.ones(2),**kwargs)
        with self.assertRaises(ValueError):
            self.bo().tell([2.,.2],dict(objective=1.,valid=True,feasible=True))


if __name__ == '__main__':
    unittest.main()
