"""Zero-physics tests for regenerated DE/PSO selection, updates and caps."""
import unittest
import numpy as np
from research.concorde_metaopt.dreal001.optimizers.recovery_population import (
    RecoveryDifferentialEvolution as DE, RecoveryParticleSwarm as PSO, better, feedback_key)
from research.concorde_metaopt.dreal001.optimizers import arms


def feedback(value=1., violation=0., valid=True):
    return dict(objective=value if valid else None, valid=valid,
                feasible=bool(valid and violation <= 0),
                constraints_g_le_zero=dict(lift=violation))


class RecoveryPopulationTests(unittest.TestCase):
    def optimizer(self, kind, budget=12, initial=None, **kwargs):
        options = dict(dimension=2,budget=budget,seed=17,
                       lower_bounds=np.zeros(2),upper_bounds=np.ones(2))
        if kind is DE:
            options.update(population_size=4,initial_population=initial)
        else:
            options.update(swarm_size=4,initial_positions=initial)
        return kind(**options, **kwargs)

    def test_repository_design_yaml_parses_but_historical_freeze_is_not_readiness(self):
        from pathlib import Path
        from research.concorde_metaopt.config_io import load_config
        from research.concorde_metaopt.aircraft.design_space import design_space_from_config, DesignSpaceError
        path=Path(__file__).resolve().parents[1]/'configs/design_space_12d_lifting_surfaces.yaml'
        config=load_config(path)
        self.assertEqual(len(config['variables']),12)
        self.assertEqual(len(config['fixed_variables']),3)
        self.assertTrue(config['frozen'])
        self.assertIn('item 2: adopt',config['fixed_variables'][0]['source'])
        with self.assertRaisesRegex(DesignSpaceError,'provisional'):
            design_space_from_config(config,source=str(path))

    def test_feasibility_selection_order(self):
        self.assertTrue(better(feedback(100.),feedback(.1,1.)))
        self.assertFalse(better(feedback(.1,1.),feedback(100.)))
        self.assertTrue(better(feedback(2.),feedback(3.)))
        self.assertTrue(better(feedback(20.,.1),feedback(1.,1.)))
        self.assertFalse(better(feedback(valid=False),feedback(1.,1.)))
        self.assertFalse(better(feedback(valid=False),None))

    def test_rejects_invalid_penalty_or_feasibility(self):
        for response in [dict(valid=False,feasible=False,objective=1e9),
                         dict(valid=True,feasible=True,objective=float('nan')),
                         dict(valid=True,feasible=True,objective=1.),
                         dict(valid=True,feasible=True,objective=1.,constraints_g_le_zero=dict(lift=1.)),
                         dict(valid=True,feasible=False,objective=1.,constraints_g_le_zero=dict(lift=float('nan')))]:
            with self.subTest(response=response),self.assertRaises(ValueError):
                feedback_key(response)

    def test_request_caps_partial_initial_and_partial_generation(self):
        for kind in (DE,PSO):
            for cap in (1,3,4,5,11,12):
                seen=[]
                optimizer=self.optimizer(kind,budget=cap)
                def evaluate(x):
                    seen.append(x.copy())
                    return feedback(float(np.sum(x*x)))
                report=optimizer.run(evaluate)
                self.assertEqual(len(seen),cap)
                self.assertEqual(report['evaluations_requested'],cap)
                self.assertEqual(report['generations_completed'],max(0,(cap-4)//4))
                self.assertEqual(report['request_cap'],cap)
                self.assertTrue(all(np.all((x>=0)&(x<=1)) for x in seen))

    def test_seeded_reproducibility_and_no_pre_evaluated_bests(self):
        for kind in (DE,PSO):
            first=self.optimizer(kind)
            second=self.optimizer(kind)
            self.assertIsNone(first.best_result)
            self.assertIsNone(first.best_vector)
            a=first.run(lambda x:feedback(float(np.sum(x*x))))
            b=second.run(lambda x:feedback(float(np.sum(x*x))))
            self.assertEqual(a,b)
            self.assertEqual(first.first_feasible,1)

    def test_failures_remain_null_and_never_become_best(self):
        for kind in (DE,PSO):
            optimizer=self.optimizer(kind)
            report=optimizer.run(lambda x:feedback(valid=False))
            self.assertIsNone(optimizer.best_result)
            self.assertIsNone(optimizer.best_vector)
            self.assertIsNone(report['best_feasible_objective'])
            self.assertIsNone(report['first_feasible_evaluation'])
            self.assertTrue(all(row['result']['objective'] is None for row in report['trace']))

    def test_external_initials_evaluated_unchanged_and_copied(self):
        original=np.array([[.1,.1],[.2,.2],[.7,.7],[.9,.9]])
        for kind in (DE,PSO):
            initial=original.copy()
            optimizer=self.optimizer(kind,initial=initial)
            initial[:]=0
            seen=[]
            def evaluate(x):
                seen.append(x.copy())
                x[:]=0 # callback mutation must not alter optimizer positions
                return feedback(1.)
            report=optimizer.run(evaluate)
            np.testing.assert_array_equal(np.array(seen[:4]),original)
            self.assertEqual(report['initial_population_source'],'external')

    def test_de_trial_is_legal_rand1_bin_from_frozen_generation(self):
        initial=np.array([[.1,.2],[.2,.3],[.5,.6],[.8,.9]])
        optimizer=self.optimizer(DE,budget=8,initial=initial,crossover_rate=1.)
        report=optimizer.run(lambda x:feedback(float(np.sum(x))))
        for row in report['trace'][4:]:
            member=row['member']
            donors=[i for i in range(4) if i!=member]
            import itertools
            allowed=[np.clip(initial[a]+.5*(initial[b]-initial[c]),0,1)
                     for a,b,c in itertools.permutations(donors)]
            self.assertTrue(any(np.allclose(row['design_vector'],x) for x in allowed))

    def test_swapping_initial_labels_changes_de_later_generation_and_pso_first(self):
        for kind in (DE,PSO):
            traces=[]
            for values in ([1.,3.,6.,9.],[9.,6.,3.,1.]):
                optimizer=self.optimizer(kind,budget=12)
                count=[0]
                def evaluate(x):
                    i=count[0]
                    count[0]+=1
                    return feedback(values[i] if i<4 else 100.)
                traces.append(np.array([r['design_vector'] for r in optimizer.run(evaluate)['trace']]))
            np.testing.assert_array_equal(traces[0][:4],traces[1][:4])
            # DE mutates frozen initial positions first; label selection affects generation 2.
            # Constant poor trial values would retain all initial points, so instead show
            # PSO's immediate feedback sensitivity separately, and DE selection below.
            if kind is PSO:
                self.assertFalse(np.array_equal(traces[0][4:],traces[1][4:]))

    def test_de_selection_changes_generation_two(self):
        traces=[]
        for initial_values in ([1.]*4,[100.]*4):
            optimizer=self.optimizer(DE,budget=12)
            index=[0]
            def evaluate(x):
                i=index[0];index[0]+=1
                return feedback(initial_values[i] if i<4 else 10.)
            traces.append(np.array([r['design_vector'] for r in optimizer.run(evaluate)['trace']]))
        np.testing.assert_array_equal(traces[0][:8],traces[1][:8])
        self.assertFalse(np.array_equal(traces[0][8:],traces[1][8:]))

    def test_pso_inertial_equation_and_velocity_cap(self):
        initial=np.array([[.3,.4],[.4,.5],[.5,.6],[.6,.7]])
        optimizer=self.optimizer(PSO,budget=8,initial=initial,
                                 inertia=.5,cognitive=0.,social=0.,max_velocity_fraction=.2)
        expected_velocity=np.random.default_rng(17).uniform(-.2,.2,size=(4,2))
        report=optimizer.run(lambda x:feedback(valid=False))
        actual=np.array([row['design_vector'] for row in report['trace'][4:]])
        np.testing.assert_allclose(actual,np.clip(initial+.5*expected_velocity,0,1),rtol=0,atol=1e-15)
        self.assertTrue(np.all(np.abs(actual-initial)<=.2))

    def test_physical_budget_exception_propagates_to_arm_receipt(self):
        for name in ('DE','PSO'):
            class Harness:
                task=None
                budget_exhausted=False
                calls=0
                def evaluate(self,x,**kwargs):
                    self.calls+=1
                    raise arms.SolverBudgetExceeded('fixture physical cap')
            harness=Harness()
            spec=arms.ArmSpec(name,budget_starts=8,population_size=4,swarm_size=4)
            info=getattr(arms,'_run_'+name.lower())(spec,harness,None)
            self.assertEqual(info['status'],'BUDGET_EXHAUSTED')
            self.assertTrue(harness.budget_exhausted)
            self.assertEqual(harness.calls,1)

    def test_exceptions_propagate_without_retry(self):
        for kind in (DE,PSO):
            count=[0]
            def fail(x):
                count[0]+=1
                raise RuntimeError('callback failure')
            with self.assertRaisesRegex(RuntimeError,'callback failure'):
                self.optimizer(kind).run(fail)
            self.assertEqual(count[0],1)

    def test_invalid_initial_configuration_and_second_run_rejected(self):
        for kind in (DE,PSO):
            for initial in (np.zeros((4,2)),np.ones((4,2))*2,np.full((4,2),float('nan'))):
                with self.assertRaises(ValueError):
                    self.optimizer(kind,initial=initial)
            optimizer=self.optimizer(kind,budget=1)
            optimizer.run(lambda x:feedback())
            with self.assertRaisesRegex(RuntimeError,'single-use'):
                optimizer.run(lambda x:feedback())

    def test_arm_runners_execute_regenerated_backends_without_mock(self):
        for name in ('DE','PSO'):
            class Harness:
                task=None
                events=[]
                def evaluate(self,x,**kwargs):
                    self.events.append(np.array(x,copy=True))
                    return feedback(float(np.sum(x*x)))
            harness=Harness();harness.events=[]
            spec=arms.ArmSpec(name,budget_starts=8,population_size=4,swarm_size=4)
            info=getattr(arms,'_run_'+name.lower())(spec,harness,None)
            self.assertEqual(info['status'],'REQUEST_CAP_REACHED')
            self.assertEqual(info['evaluations_requested'],8)
            self.assertEqual(len(harness.events),8)
            self.assertIn('RECOVERY_NUMPY',info['backend'])


if __name__=='__main__':
    unittest.main()
