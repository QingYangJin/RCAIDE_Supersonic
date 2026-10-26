"""Constrained differential evolution for this tutorial's mutable RCAIDE Nexus.

Local adapter: the installed RCAIDE package is left untouched. All solver
coordinates are scaled; input table values remain in their declared units.
"""

from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from contextlib import contextmanager
import ctypes
import importlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import NonlinearConstraint, differential_evolution
from threadpoolctl import threadpool_limits


class _CpuRate(ctypes.Structure):
    _fields_ = [('flags', ctypes.c_uint32), ('rate', ctypes.c_uint32)]


def _kernel():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel.CreateJobObjectW.restype = ctypes.c_void_p
    kernel.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.c_void_p, ctypes.c_uint32]
    kernel.QueryInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    return kernel


def _job_cpu_rate():
    if os.name != 'nt':
        return None
    info = _CpuRate()
    kernel = _kernel()
    if kernel.QueryInformationJobObject(None, 15, ctypes.byref(info), ctypes.sizeof(info), None):
        return info.rate / 100. if info.flags & 4 else None
    return None


@contextmanager
def _cpu_budget(percent):
    """Hard cap for this solver process AND its inherited Windows job children."""
    if percent is None:
        yield {'cpu_limit_percent': None, 'cpu_limit_mechanism': None}
        return
    if os.name != 'nt':
        raise OSError('CPU group limit requires Windows; set cpu_limit_percent=None elsewhere.')
    kernel = _kernel()
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # JOBOBJECTINFOCLASS JobObjectCpuRateControlInformation = 15.
        # ENABLE | HARD_CAP; CpuRate uses 1/100 percent of aggregate CPU capacity.
        info = _CpuRate(1 | 4, int(round(percent * 100)))
        if not kernel.SetInformationJobObject(job, 15, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
            raise ctypes.WinError(ctypes.get_last_error())
        yield {'cpu_limit_percent': _job_cpu_rate(),
               'cpu_limit_mechanism': 'Windows Job Object aggregate hard cap'}
    finally:
        # No KILL_ON_JOB_CLOSE flag: releasing the limit never kills a process.
        disabled = _CpuRate(0, 0)
        kernel.SetInformationJobObject(job, 15, ctypes.byref(disabled), ctypes.sizeof(disabled))
        kernel.CloseHandle(job)


def _memory_status():
    if os.name != 'nt':
        return None

    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
            (name, ctypes.c_uint64) for name in ('total_phys', 'avail_phys', 'total_commit',
                                               'avail_commit', 'total_virtual', 'avail_virtual', 'extended')]
    status = Status()
    status.length = ctypes.sizeof(status)
    if not _kernel().GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'available_physical_bytes': status.avail_phys,
            'available_commit_bytes': status.avail_commit}


def _process_resources():
    result = {'cpu_seconds': time.process_time()}
    if os.name != 'nt':
        return result

    class Counters(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_uint32), ('faults', ctypes.c_uint32)] + [
            (name, ctypes.c_size_t) for name in ('peak_working_set', 'working_set', 'peak_paged',
                'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
    if not psapi.GetProcessMemoryInfo(_kernel().GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    result.update(peak_private_bytes=int(counters.peak_pagefile),
                  peak_working_set_bytes=int(counters.peak_working_set),
                  working_set_bytes=int(counters.working_set), private_bytes=int(counters.private))
    return result


def _memory_worker_limit(requested, resources, available, reserve_gib=2.):
    """One completed warm-up worker is already included in system memory use."""
    if available is None:
        return requested
    reserve = reserve_gib * 1024 ** 3
    private = max(resources['peak_private_bytes'], 256 * 1024 ** 2) * 1.25
    physical = max(resources['peak_working_set_bytes'], 256 * 1024 ** 2) * 1.25
    additional = min((available['available_commit_bytes'] - reserve) / private,
                     (available['available_physical_bytes'] - reserve) / physical)
    return min(requested, max(1, 1 + int(max(0, additional))))


def _atomic_json(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=1, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


def _signature(problem):
    tables = problem.optimization_problem
    value = {key: np.asarray(getattr(tables, key), dtype=object).tolist()
             for key in ('inputs', 'objective', 'constraints')}
    value['aliases'] = tables.aliases
    return json.dumps(value, sort_keys=True, default=lambda x: x.item())


def _start_worker(factory_module, factory_name, signature, directory, blas_threads):
    global _worker_problem, _thread_limiter, _worker_log
    directory = Path(directory) / ('worker_%d' % os.getpid())
    directory.mkdir(parents=True, exist_ok=False)
    _worker_log = (directory / 'console.log').open('a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = _worker_log
    _thread_limiter = threadpool_limits(limits=blas_threads)
    _worker_problem = getattr(importlib.import_module(factory_module), factory_name)()
    if _signature(_worker_problem) != signature:
        raise ValueError('Worker task tables/aliases differ from the coordinator.')
    _worker_problem.results_directory = str(directory)
    from threadpoolctl import threadpool_info
    _atomic_json(directory / 'runtime.json', {
        'pid': os.getpid(), 'blas_libraries': threadpool_info(),
        'inherited_cpu_limit_percent': _job_cpu_rate(),
        'created_at_utc': datetime.now(timezone.utc).isoformat()})


def _evaluate_candidate(x):
    import Save_Results
    before = int(_worker_problem.evaluation_count)
    objective = np.asarray(_worker_problem.objective(x), float).ravel()
    constraints = np.asarray(_worker_problem.all_constraints(x), float).ravel()
    if objective.size != 1 or not np.all(np.isfinite(objective)) or not np.all(np.isfinite(constraints)):
        raise ValueError('Worker returned a non-finite or non-scalar response.')
    record = dict(record_type='performance_evaluation',
                  observed_at_utc=datetime.now(timezone.utc).isoformat(),
                  worker_pid=os.getpid(), worker_evaluation_index=int(_worker_problem.evaluation_count),
                  design_inputs_in_declared_units={str(r[0]): float(r[1])
                                                  for r in _worker_problem.optimization_problem.inputs})
    record.update(Save_Results._summary_scalars(_worker_problem))
    return (float(objective[0]), constraints, record,
            int(_worker_problem.evaluation_count) - before, _process_resources())


class _BatchEvaluator:
    """Parallelize complete candidate evaluations, including nonlinear constraints."""
    def __init__(self, executor, constraint_count, directory, requested_workers, display, cpu_info):
        self.executor, self.constraint_count = executor, constraint_count
        self.directory, self.display = Path(directory), display
        self.requested_workers, self.effective_workers = requested_workers, 1
        self.cpu_info = cpu_info
        self.cache, self.records, self.workers = {}, [], {}
        self.mission_evaluations = 0
        self.memory_plan = None

    def _save(self):
        _atomic_json(self.directory / 'optimization_history.json', self.records)
        _atomic_json(self.directory / 'parallel_runtime.json', dict(
            self.cpu_info, requested_workers=self.requested_workers,
            effective_workers=self.effective_workers, memory_plan=self.memory_plan,
            worker_resources=self.workers, performance_evaluations=self.mission_evaluations))

    def batch(self, x):
        x = np.asarray(x, float)
        scalar = x.ndim == 1
        columns = x[:, None] if scalar else x
        if columns.ndim != 2:
            raise ValueError('Expected design vector (N,) or population (N,S).')
        missing, keys = {}, []
        for column in columns.T:
            key = np.ascontiguousarray(column).tobytes()
            keys.append(key)
            if key not in self.cache and key not in missing:
                missing[key] = column.copy()
        queue, pending = iter(missing.items()), {}

        def fill():
            while len(pending) < self.effective_workers:
                try:
                    key, column = next(queue)
                except StopIteration:
                    break
                pending[self.executor.submit(_evaluate_candidate, column)] = (key, column)

        fill()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                key, column = pending.pop(future)
                objective, constraints, record, calls, resources = future.result()
                if constraints.size != self.constraint_count:
                    raise ValueError('Worker constraint count differs from the problem table.')
                self.cache[key] = (objective, constraints.copy())
                self.mission_evaluations += calls
                self.workers[str(record['worker_pid'])] = resources
                record.update(iteration=len(self.records) + 1, solver_coordinates=column.tolist())
                self.records.append(record)
                if self.memory_plan is None:
                    available = _memory_status()
                    self.effective_workers = _memory_worker_limit(self.requested_workers, resources, available)
                    self.memory_plan = dict(available_after_warmup=available,
                                            warmup_peak=resources, reserve_gib=2., peak_safety_factor=1.25)
                    if self.display:
                        print('[DE] parallel workers=%d/%d; CPU cap=%s%%' % (
                            self.effective_workers, self.requested_workers,
                            self.cpu_info['cpu_limit_percent']), flush=True)
                # Stop admitting as many NEW candidates if external memory use rises.
                available = _memory_status()
                if available and min(available.values()) < 1024 ** 3:
                    self.effective_workers = max(1, self.effective_workers // 2)
                self._save()
                if self.display:
                    print('[DE] evaluation=%d worker=%d fuel=%s' % (
                        len(self.records), record['worker_pid'], record.get('fuel_burn')), flush=True)
            fill()
        objectives = np.asarray([self.cache[key][0] for key in keys], float)
        constraints = np.asarray([self.cache[key][1] for key in keys], float)
        constraints = constraints.reshape(len(keys), self.constraint_count).T
        return (objectives[0], constraints[:, 0]) if scalar else (objectives, constraints)

    def metrics(self, x):
        return self.batch(x)

    def objective(self, x):
        return self.batch(x)[0]

    def constraints(self, x):
        return self.batch(x)[1]


class _Evaluator:
    """Cache scalar metrics, so constraint/objective requests share a Mission."""

    def __init__(self, problem, constraint_count):
        self.problem = problem
        self.constraint_count = constraint_count
        self.cache = {}

    def metrics(self, x):
        x = np.asarray(x, dtype=float)
        key = x.tobytes()
        if key not in self.cache:
            objective = np.asarray(self.problem.objective(x), dtype=float).ravel()
            constraints = np.asarray(self.problem.all_constraints(x), dtype=float).ravel()
            if objective.size != 1:
                raise ValueError('This tutorial requires one scalar objective.')
            if constraints.size != self.constraint_count:
                raise ValueError('Constraint count does not match the problem table.')
            if not np.all(np.isfinite(objective)) or not np.all(np.isfinite(constraints)):
                raise ValueError('Mission returned a non-finite objective or constraint.')
            self.cache[key] = (float(objective[0]), constraints.copy())
        return self.cache[key]

    def objective(self, x):
        return self.metrics(x)[0]

    def constraints(self, x):
        return self.metrics(x)[1].copy()


def _solve_parallel(problem, scales, initial, lower, upper, lb, ub, *,
                    max_generations, population_multiplier, tolerance, seed, display,
                    parallel_workers, blas_threads, cpu_info, factory_module, factory_name):
    directory = Path(problem.results_directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / 'optimization_history.json').exists() or (directory / 'workers').exists():
        raise ValueError('Parallel solve requires a fresh output directory.')
    generations = []
    parent_start = int(problem.evaluation_count)
    population_members = max(5, int(population_multiplier) * len(initial))
    requested = min(int(parallel_workers), population_members, 61)
    with ProcessPoolExecutor(max_workers=requested, mp_context=mp.get_context('spawn'),
            initializer=_start_worker,
            initargs=(factory_module, factory_name, _signature(problem),
                      str(directory / 'workers'), int(blas_threads))) as pool:
        evaluator = _BatchEvaluator(pool, len(lb), directory, requested, display, cpu_info)
        # The first solver-requested candidate measures memory. Let SciPy supply
        # its own scaled coordinates: a manual x0 call can differ by one ULP and
        # cause an extra Mission evaluation despite the exact-coordinate cache.
        constraints = (NonlinearConstraint(evaluator.constraints, lb, ub),) if len(lb) else ()

        def progress(intermediate_result):
            _, values = evaluator.metrics(intermediate_result.x)
            violation = float(np.max(np.maximum(lb - values, values - ub), initial=0.0))
            generations.append(dict(generation=len(generations) + 1,
                best_scaled_objective=float(intermediate_result.fun),
                max_constraint_violation_scaled=violation, unique_candidates=len(evaluator.cache)))
            if display:
                print('[DE] generation=%d/%d candidates=%d best=%g maxcv=%g' % (
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
        returned_objective, returned_constraints = evaluator.metrics(result.x)
        parallel_calls = evaluator.mission_evaluations
        candidate_count = len(evaluator.cache)
        parent_history = len(evaluator.records)
        effective_workers = evaluator.effective_workers
        memory_plan = evaluator.memory_plan
    # Workers return scalars. Synchronize the coordinator to obtain its complete
    # final Mission state, then check that its metrics agree with the worker.
    problem.total_number_of_iterations = parent_history
    problem.evaluate(np.asarray(result.x, float))
    actual = np.asarray(problem.optimization_problem.inputs[:, 1], float)
    if not np.allclose(actual, result.x * scales, rtol=1e-12, atol=1e-12):
        raise RuntimeError('Final coordinator inputs do not match returned design.')
    synced_objective = np.asarray(problem.objective(result.x), float).ravel()
    synced_constraints = np.asarray(problem.all_constraints(result.x), float).ravel()
    if (not np.allclose(synced_objective, returned_objective, rtol=1e-6, atol=1e-8)
            or not np.allclose(synced_constraints, returned_constraints, rtol=1e-6, atol=1e-8)):
        raise RuntimeError('Coordinator and worker metrics disagree; inspect worker logs.')
    result.solver_name = 'differential_evolution'
    result.final_state_matches_solver_x = True
    result.mission_evaluations = parallel_calls + int(problem.evaluation_count) - parent_start
    result.unique_candidate_evaluations = candidate_count
    result.generation_history = generations
    result.run_configuration = dict(cpu_info,
        max_generations=int(max_generations), population_multiplier=int(population_multiplier),
        population_members=len(result.population), tolerance=float(tolerance), seed=seed,
        requested_parallel_workers=int(parallel_workers), parallel_workers=effective_workers,
        blas_threads=int(blas_threads), memory_plan=memory_plan,
        scipy_workers=1, vectorized=True, updating='deferred', polish=False)
    return result


def solve(problem, *, max_generations=20, population_multiplier=5,
          tolerance=0.01, seed=42, display=True, parallel_workers=1,
          blas_threads=2, cpu_limit_percent=None,
          factory_module='Optimize', factory_name='define_optimization_problem'):
    """Bounded DE, with isolated batch workers when parallel_workers > 1.

    population_multiplier * number_of_free_variables is the population size
    (SciPy uses at least five members). ``nit`` counts generations, whereas
    ``mission_evaluations`` counts actual Nexus procedure evaluations.
    """
    inputs = problem.optimization_problem.inputs
    rows = problem.optimization_problem.constraints
    scales = np.asarray(inputs[:, 4], dtype=float)
    units = np.asarray(inputs[:, 5], dtype=float)
    initial = np.asarray(inputs[:, 1], dtype=float).copy()
    lower = np.asarray(inputs[:, 2], dtype=float)
    upper = np.asarray(inputs[:, 3], dtype=float)
    if (not np.all(np.isfinite(np.concatenate((scales, units, initial, lower, upper))))
            or np.any(scales <= 0) or np.any(units <= 0)
            or np.any(lower >= upper) or np.any(initial < lower) or np.any(initial > upper)):
        raise ValueError('Input scales/units must be positive, and bounds must contain the initial design.')
    if (isinstance(max_generations, bool) or int(max_generations) != max_generations
            or max_generations < 0 or isinstance(population_multiplier, bool)
            or int(population_multiplier) != population_multiplier or population_multiplier < 1
            or not np.isfinite(tolerance) or tolerance < 0):
        raise ValueError('Invalid DE generation limit, population multiplier, or tolerance.')
    for value in (parallel_workers, blas_threads):
        if isinstance(value, bool) or int(value) != value or value < 1:
            raise ValueError('Worker and BLAS thread counts must be positive integers.')
    if cpu_limit_percent is not None and (isinstance(cpu_limit_percent, bool)
            or not np.isfinite(cpu_limit_percent) or not 0 < cpu_limit_percent <= 100):
        raise ValueError('CPU limit must be in (0,100], or None.')

    # Nexus.all_constraints returns SI responses divided by column 4's scale.
    # Convert each declared edge to SI, then apply that SAME response scale.
    lb, ub = [], []
    for row in rows:
        scale, unit = float(row[3]), float(row[4])
        if not np.isfinite(scale) or scale <= 0 or not np.isfinite(unit) or unit <= 0:
            raise ValueError('Constraint scales and units must be finite and positive.')
        edge = float(row[2]) * unit / scale
        if not np.isfinite(edge):
            raise ValueError('Constraint edges must be finite.')
        sense = str(row[1])
        if sense == '>':
            lb.append(edge); ub.append(np.inf)
        elif sense == '<':
            lb.append(-np.inf); ub.append(edge)
        elif sense == '=':
            lb.append(edge); ub.append(edge)
        else:
            raise ValueError('Unsupported constraint sense: ' + sense)
    lb, ub = np.asarray(lb), np.asarray(ub)
    if parallel_workers > 1:
        with _cpu_budget(cpu_limit_percent) as cpu_info, threadpool_limits(limits=int(blas_threads)):
            return _solve_parallel(problem, scales, initial, lower, upper, lb, ub,
                max_generations=max_generations, population_multiplier=population_multiplier,
                tolerance=tolerance, seed=seed, display=display, parallel_workers=parallel_workers,
                blas_threads=blas_threads, cpu_info=cpu_info,
                factory_module=factory_module, factory_name=factory_name)
    with _cpu_budget(cpu_limit_percent) as cpu_info, threadpool_limits(limits=int(blas_threads)):
        evaluator = _Evaluator(problem, len(rows))
        constraints = (NonlinearConstraint(evaluator.constraints, lb, ub),) if len(rows) else ()
        generations = []
        start_count = int(getattr(problem, 'evaluation_count', 0))

        def progress(intermediate_result):
            _, values = evaluator.metrics(intermediate_result.x)
            violation = float(np.max(np.maximum(lb - values, values - ub), initial=0.0))
            record = {'generation': len(generations) + 1,
                      'best_scaled_objective': float(intermediate_result.fun),
                      'max_constraint_violation_scaled': violation,
                      'unique_candidates': len(evaluator.cache)}
            generations.append(record)
            if display:
                print('[DE] generation=%d/%d candidates=%d best=%g maxcv=%g' % (
                    record['generation'], max_generations, record['unique_candidates'],
                    record['best_scaled_objective'], violation), flush=True)
            return False

        result = differential_evolution(
            evaluator.objective, bounds=list(zip(lower / scales, upper / scales)),
            constraints=constraints, strategy='best1bin', maxiter=int(max_generations),
            popsize=int(population_multiplier), tol=float(tolerance), atol=0.0,
            mutation=(0.5, 1.0), recombination=0.7, rng=seed,
            x0=initial / scales, init='latinhypercube', callback=progress,
            polish=False, workers=1, updating='immediate', disp=False,
        )

        # Cached metrics do not restore mutable Mission state. Synchronize explicitly
        # before printing/saving; otherwise the last candidate can masquerade as x.
        problem.evaluate(np.asarray(result.x, dtype=float))
        actual = np.asarray(inputs[:, 1], dtype=float)
        if not np.allclose(actual, np.asarray(result.x) * scales, rtol=1e-12, atol=1e-12):
            raise RuntimeError('Nexus final inputs do not match the solver returned design.')
        result.solver_name = 'differential_evolution'
        result.final_state_matches_solver_x = True
        result.mission_evaluations = int(getattr(problem, 'evaluation_count', 0)) - start_count
        result.unique_candidate_evaluations = len(evaluator.cache)
        result.generation_history = generations
        result.run_configuration = {
            'max_generations': int(max_generations),
            'population_multiplier': int(population_multiplier),
            'population_members': len(result.population),
            'tolerance': float(tolerance), 'seed': seed,
            'polish': False, 'workers': 1,
        }
        result.run_configuration.update(cpu_info, blas_threads=int(blas_threads), updating='immediate')
        return result
