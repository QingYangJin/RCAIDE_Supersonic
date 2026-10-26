"""Batch DE for isolated RCAIDE processes; never share a mutable Nexus.

SciPy's workers map does not parallelize nonlinear constraints. Here vectorized
constraint calls dispatch complete candidate evaluations to a process pool.
Only the coordinator writes the combined history; workers keep separate logs.
"""
import importlib
import json
import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import NonlinearConstraint, differential_evolution


def _signature(problem):
    tables = problem.optimization_problem
    signature = {key: np.asarray(getattr(tables, key), dtype=object).tolist()
                 for key in ('inputs', 'objective', 'constraints')}
    signature['aliases'] = tables.aliases
    return json.dumps(signature,
                      sort_keys=True, default=lambda x: x.item())


def _start_worker(factory_module, factory_name, signature, directory, blas_threads):
    global _problem, _thread_limiter, _worker_log
    # Keep log/history files out of other workers' and the coordinator's paths.
    worker_dir = Path(directory) / ('worker_%d' % os.getpid())
    worker_dir.mkdir(parents=True, exist_ok=False)
    _worker_log = (worker_dir / 'console.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = _worker_log
    from threadpoolctl import threadpool_limits
    _thread_limiter = threadpool_limits(limits=blas_threads)
    _problem = getattr(importlib.import_module(factory_module), factory_name)()
    # A factory must reproduce the coordinator's configured optimization task.
    if _signature(_problem) != signature:
        raise ValueError('Worker problem tables differ from the coordinator.')
    _problem.results_directory = str(worker_dir)


def _evaluate_candidate(x):
    import Save_Results
    before = int(_problem.evaluation_count)
    objective = np.asarray(_problem.objective(x), dtype=float).ravel()
    constraints = np.asarray(_problem.all_constraints(x), dtype=float).ravel()
    if objective.size != 1 or not np.all(np.isfinite(objective)) or not np.all(np.isfinite(constraints)):
        raise ValueError('Worker returned a non-finite or non-scalar response.')
    record = dict(record_type='performance_evaluation',
                  observed_at_utc=datetime.now(timezone.utc).isoformat(),
                  worker_pid=os.getpid(), worker_evaluation_index=int(_problem.evaluation_count),
                  design_inputs_in_declared_units={str(r[0]): float(r[1])
                                                  for r in _problem.optimization_problem.inputs})
    record.update(Save_Results._summary_scalars(_problem))
    return float(objective[0]), constraints, record, int(_problem.evaluation_count) - before


class BatchEvaluator:
    """Cache and dispatch a whole population, including expensive constraints."""
    def __init__(self, executor, constraint_count, directory, display):
        self.executor = executor
        self.constraint_count = constraint_count
        self.directory = Path(directory)
        self.display = display
        self.cache = {}
        self.records = []
        self.mission_evaluations = 0

    def _save_history(self):
        target = self.directory / 'optimization_history.json'
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.records, indent=1, allow_nan=False), encoding='utf-8')
        os.replace(temporary, target)

    def batch(self, x):
        x = np.asarray(x, dtype=float)
        scalar = x.ndim == 1
        columns = x[:, None] if scalar else x
        if columns.ndim != 2:
            raise ValueError('Expected design vector (N,) or population (N,S).')
        missing = {}
        keys = []
        for column in columns.T:
            key = np.ascontiguousarray(column).tobytes()
            keys.append(key)
            if key not in self.cache and key not in missing:
                missing[key] = column.copy()
        pending = {self.executor.submit(_evaluate_candidate, column): (key, column)
                   for key, column in missing.items()}
        for future in as_completed(pending):
            key, column = pending[future]
            objective, constraints, record, calls = future.result()
            if constraints.size != self.constraint_count:
                raise ValueError('Worker constraint count differs from the problem table.')
            self.cache[key] = (objective, constraints)
            self.mission_evaluations += calls
            record.update(iteration=len(self.records) + 1,
                          solver_coordinates=column.tolist())
            self.records.append(record)
            self._save_history()
            if self.display:
                print('[DE parallel] completed=%d worker=%d fuel=%s' % (
                    len(self.records), record['worker_pid'], record.get('fuel_burn')), flush=True)
        objectives = np.asarray([self.cache[key][0] for key in keys], dtype=float)
        constraints = np.asarray([self.cache[key][1] for key in keys], dtype=float)
        constraints = constraints.reshape(len(keys), self.constraint_count).T
        return (objectives[0], constraints[:, 0]) if scalar else (objectives, constraints)

    def objective(self, x):
        return self.batch(x)[0]

    def constraints(self, x):
        return self.batch(x)[1]


def solve(problem, *, factory_module='Optimize', factory_name='define_optimization_problem',
          parallel_workers=4, blas_threads=2, max_generations=20,
          population_multiplier=5, tolerance=0.01, seed=42, display=True):
    """Run deferred DE with process-isolated evaluations and no polishing.

    This is a NEW run, not a way to change an already running serial solve.
    The factory is an importable module-level function (Windows spawn).
    """
    integers = ((parallel_workers, 1), (blas_threads, 1),
                (max_generations, 0), (population_multiplier, 1))
    if any(isinstance(v, bool) or int(v) != v or v < minimum for v, minimum in integers):
        raise ValueError('Invalid worker/thread count or DE budget.')
    if not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError('Tolerance must be finite and nonnegative.')
    inputs = problem.optimization_problem.inputs
    scales, units = np.asarray(inputs[:, 4], float), np.asarray(inputs[:, 5], float)
    initial = np.asarray(inputs[:, 1], float).copy()
    lower, upper = np.asarray(inputs[:, 2], float), np.asarray(inputs[:, 3], float)
    if (not np.all(np.isfinite(np.concatenate((scales, units, initial, lower, upper))))
            or np.any(scales <= 0) or np.any(units <= 0) or np.any(lower >= upper)
            or np.any(initial < lower) or np.any(initial > upper)):
        raise ValueError('Invalid input scales, units, initial design or bounds.')
    lb, ub = [], []
    for row in problem.optimization_problem.constraints:
        scale, unit = float(row[3]), float(row[4])
        if not np.isfinite(scale) or scale <= 0 or not np.isfinite(unit) or unit <= 0:
            raise ValueError('Invalid constraint units or scale.')
        edge = float(row[2]) * unit / scale
        if not np.isfinite(edge):
            raise ValueError('Invalid constraint edge.')
        sense = str(row[1])
        if sense not in ('>', '<', '='):
            raise ValueError('Unsupported constraint sense: ' + sense)
        lb.append(edge if sense in ('>', '=') else -np.inf)
        ub.append(edge if sense in ('<', '=') else np.inf)
    lb, ub = np.asarray(lb), np.asarray(ub)
    directory = Path(problem.results_directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / 'optimization_history.json').exists() or (directory / 'workers').exists():
        raise ValueError('Parallel solve requires a fresh output directory.')
    generations = []
    parent_start = int(problem.evaluation_count)
    with ProcessPoolExecutor(max_workers=int(parallel_workers),
                             mp_context=mp.get_context('spawn'),
                             initializer=_start_worker,
                             initargs=(factory_module, factory_name, _signature(problem),
                                       str(directory / 'workers'), int(blas_threads))) as pool:
        evaluator = BatchEvaluator(pool, len(lb), directory, display)
        constraints = (NonlinearConstraint(evaluator.constraints, lb, ub),) if len(lb) else ()

        def progress(intermediate_result):
            _, values = evaluator.batch(intermediate_result.x)
            violation = float(np.max(np.maximum(lb - values, values - ub), initial=0.0))
            generations.append(dict(generation=len(generations) + 1,
                                    best_scaled_objective=float(intermediate_result.fun),
                                    max_constraint_violation_scaled=violation,
                                    unique_candidates=len(evaluator.cache)))
            if display:
                print('[DE parallel] generation=%d/%d candidates=%d best=%g maxcv=%g' % (
                    len(generations), max_generations, len(evaluator.cache),
                    intermediate_result.fun, violation), flush=True)
            return False

        result = differential_evolution(
            evaluator.objective, bounds=list(zip(lower / scales, upper / scales)),
            constraints=constraints, strategy='best1bin', maxiter=int(max_generations),
            popsize=int(population_multiplier), tol=float(tolerance), atol=0.,
            mutation=(0.5, 1.), recombination=0.7, rng=seed,
            x0=initial / scales, init='latinhypercube', callback=progress,
            polish=False, workers=1, vectorized=True, updating='deferred', disp=False)
        parallel_calls = evaluator.mission_evaluations
        candidate_count = len(evaluator.cache)
        parent_history = len(evaluator.records)
        returned_objective, returned_constraints = evaluator.batch(result.x)
    # Restore the actual returned design in the coordinator for full segment
    # reporting. Worker caches contain metrics, not the coordinator's Mission.
    problem.total_number_of_iterations = parent_history
    problem.evaluate(np.asarray(result.x, float))
    actual = np.asarray(inputs[:, 1], float)
    if not np.allclose(actual, result.x * scales, rtol=1e-12, atol=1e-12):
        raise RuntimeError('Final coordinator state does not match returned design.')
    # Reusing independent mutable aircraft models must not silently change the
    # returned candidate's metrics. This uses the already required final sync.
    synced_objective = np.asarray(problem.objective(result.x), float).ravel()
    synced_constraints = np.asarray(problem.all_constraints(result.x), float).ravel()
    if (not np.allclose(synced_objective, returned_objective, rtol=1e-6, atol=1e-8)
            or not np.allclose(synced_constraints, returned_constraints, rtol=1e-6, atol=1e-8)):
        raise RuntimeError('Coordinator and worker metrics disagree at returned design; inspect worker logs.')
    result.solver_name = 'differential_evolution_parallel'
    result.final_state_matches_solver_x = True
    result.mission_evaluations = parallel_calls + int(problem.evaluation_count) - parent_start
    result.unique_candidate_evaluations = candidate_count
    result.generation_history = generations
    result.run_configuration = dict(
        max_generations=int(max_generations), population_multiplier=int(population_multiplier),
        population_members=len(result.population), tolerance=float(tolerance), seed=seed,
        parallel_workers=int(parallel_workers), blas_threads=int(blas_threads),
        scipy_workers=1, vectorized=True, updating='deferred', polish=False,
        factory_module=factory_module, factory_name=factory_name)
    return result
