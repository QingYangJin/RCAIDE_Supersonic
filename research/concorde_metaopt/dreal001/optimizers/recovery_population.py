"""Regenerated callback-only DE/rand/1/bin and synchronous bounded PSO.

No physics imports or pseudo-labels. Each run has an evaluation-request cap;
physical starts are separately enforced by ArmHarness/ledger (not equated to
requests). Every initial member is evaluated before selection/best updates.
These are explicit new backends, not historical baseline algorithm recovery.
"""
from __future__ import annotations
from collections.abc import Mapping
import numpy as np
from .recovery_bo import _bounds, generate_initial_designs

DE_BACKEND_ID = "RECOVERY_NUMPY_DE_RAND1_BIN_V1"
PSO_BACKEND_ID = "RECOVERY_NUMPY_SYNCHRONOUS_PSO_V1"


def feedback_key(result):
    """Feasible dominates valid-infeasible dominates failure; never penalty labels."""
    if not isinstance(result, Mapping):
        raise ValueError("feedback mapping required")
    valid, feasible, value = result.get("valid"), result.get("feasible"), result.get("objective")
    if not isinstance(valid, (bool, np.bool_)) or not isinstance(feasible, (bool, np.bool_)):
        raise ValueError("explicit boolean valid/feasible required")
    if not valid:
        if feasible or value is not None:
            raise ValueError("failed feedback must be infeasible with null objective")
        return (2, 0.0)
    if value is None or not np.isfinite(value) or value < 0:
        raise ValueError("VALID objective must be finite nonnegative")
    constraints = result.get("constraints_g_le_zero")
    if not isinstance(constraints, Mapping) or not constraints:
        raise ValueError("explicit finite constraints required for VALID feedback")
    values = np.asarray(list(constraints.values()), dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("finite constraints required")
    actual_feasible = bool(np.all(values <= 0))
    if bool(feasible) != actual_feasible:
        raise ValueError("feasibility contradicts constraints")
    return (0, float(value)) if feasible else (1, float(np.maximum(values, 0).sum()))


def better(candidate, incumbent):
    candidate_key = feedback_key(candidate)
    if candidate_key[0] == 2:
        return False
    return incumbent is None or candidate_key < feedback_key(incumbent)


class _Population:
    def __init__(self, *, dimension, budget, seed, size, lower_bounds, upper_bounds, initial):
        if (type(dimension) is not int or dimension < 1 or type(budget) is not int or budget < 1
                or type(size) is not int or size < 4 or type(seed) is not int or seed < 0):
            raise ValueError("positive dimension/budget, population >=4 and nonnegative seed required")
        self.lower, self.upper = _bounds(lower_bounds, upper_bounds)
        if self.lower.shape != (dimension,):
            raise ValueError("bounds dimension mismatch")
        self.dimension, self.budget, self.size = dimension, budget, size
        self.rng = np.random.default_rng(seed)
        self.initial_source = "lhs" if initial is None else "external"
        self.initial = (generate_initial_designs(self.lower, self.upper, count=size, seed=seed)
                        if initial is None else np.array(initial, dtype=float, copy=True))
        if (self.initial.shape != (size, dimension) or not np.all(np.isfinite(self.initial))
                or np.any(self.initial < self.lower) or np.any(self.initial > self.upper)):
            raise ValueError("initial population must be finite and within bounds")
        if len({tuple(x) for x in self.initial}) != size:
            raise ValueError("duplicate initial population")
        self.has_run = False
        self.trace = []
        self.first_feasible = None
        self.best_result = None
        self.best_vector = None

    def _evaluate(self, evaluate, vector, phase, generation, member):
        # Check the request cap before invoking any callback; exceptions propagate.
        if len(self.trace) >= self.budget:
            raise RuntimeError("optimizer request cap reached")
        result = dict(evaluate(vector.copy()))
        feedback_key(result)
        self.trace.append(dict(design_vector=vector.tolist(), result=result, phase=phase,
                               generation=generation, member=member))
        if result["feasible"] and self.first_feasible is None:
            self.first_feasible = len(self.trace)
        if better(result, self.best_result):
            self.best_result, self.best_vector = result, vector.copy()
        return result

    def _begin(self):
        if self.has_run:
            raise RuntimeError("optimizer instances are single-use")
        self.has_run = True

    def _report(self, backend, generations, config):
        return dict(status="REQUEST_CAP_REACHED", backend=backend,
                    evaluations_requested=len(self.trace), request_cap=self.budget,
                    generations_completed=generations,
                    first_feasible_evaluation=self.first_feasible,
                    best_feasible_objective=(self.best_result["objective"]
                                             if self.best_result and self.best_result["feasible"] else None),
                    initial_population_source=self.initial_source,
                    initial_positions_source=self.initial_source, config=config,
                    trace=list(self.trace))


class RecoveryDifferentialEvolution(_Population):
    backend_id = DE_BACKEND_ID

    def __init__(self, *, dimension, budget, seed=0, population_size=8,
                 lower_bounds, upper_bounds, initial_population=None,
                 mutation_factor=0.5, crossover_rate=0.7):
        super().__init__(dimension=dimension, budget=budget, seed=seed, size=population_size,
                         lower_bounds=lower_bounds, upper_bounds=upper_bounds, initial=initial_population)
        if not np.isfinite(mutation_factor) or not 0 < mutation_factor <= 2:
            raise ValueError("mutation factor must be in (0,2]")
        if not np.isfinite(crossover_rate) or not 0 <= crossover_rate <= 1:
            raise ValueError("crossover rate must be in [0,1]")
        self.factor, self.crossover = float(mutation_factor), float(crossover_rate)

    def run(self, evaluate):
        self._begin()
        population, results = self.initial.copy(), []
        for index, vector in enumerate(population):
            if len(self.trace) >= self.budget:
                return self._report(self.backend_id, 0, self.config())
            results.append(self._evaluate(evaluate, vector, "initial", 0, index))
        generation = 0
        while len(self.trace) < self.budget:
            # Generational DE: donors and incumbents frozen within generation.
            base, next_population, next_results = population.copy(), population.copy(), list(results)
            complete = True
            for index in range(self.size):
                if len(self.trace) >= self.budget:
                    complete = False
                    break
                choices = np.delete(np.arange(self.size), index)
                a,b,c = self.rng.choice(choices, 3, replace=False)
                mutant = np.clip(base[a] + self.factor * (base[b] - base[c]), self.lower, self.upper)
                mask = self.rng.random(self.dimension) < self.crossover
                mask[int(self.rng.integers(self.dimension))] = True
                trial = np.where(mask, mutant, base[index])
                response = self._evaluate(evaluate, trial, "de", generation+1, index)
                if better(response, results[index]):
                    next_population[index], next_results[index] = trial, response
            population, results = next_population, next_results
            if complete:
                generation += 1
        return self._report(self.backend_id, generation, self.config())

    def config(self):
        return dict(mutation_factor=self.factor, crossover_rate=self.crossover,
                    update="generational", boundary="clip")


class RecoveryParticleSwarm(_Population):
    backend_id = PSO_BACKEND_ID

    def __init__(self, *, dimension, budget, seed=0, swarm_size=8,
                 lower_bounds, upper_bounds, initial_positions=None,
                 inertia=0.7298, cognitive=1.49618, social=1.49618,
                 max_velocity_fraction=0.20):
        super().__init__(dimension=dimension, budget=budget, seed=seed, size=swarm_size,
                         lower_bounds=lower_bounds, upper_bounds=upper_bounds, initial=initial_positions)
        coefficients = np.array([inertia,cognitive,social,max_velocity_fraction],dtype=float)
        if (not np.all(np.isfinite(coefficients)) or not 0 < inertia <= 1
                or cognitive < 0 or social < 0 or not 0 < max_velocity_fraction <= 1):
            raise ValueError("invalid PSO coefficients")
        self.inertia, self.cognitive, self.social = float(inertia),float(cognitive),float(social)
        self.fraction = float(max_velocity_fraction)

    def run(self, evaluate):
        self._begin()
        positions = self.initial.copy()
        velocity_cap = self.fraction * (self.upper-self.lower)
        velocities = self.rng.uniform(-velocity_cap, velocity_cap, size=positions.shape)
        pbest, pbest_results = positions.copy(), [None] * self.size
        for index, vector in enumerate(positions):
            if len(self.trace) >= self.budget:
                return self._report(self.backend_id, 0, self.config())
            response = self._evaluate(evaluate, vector, "initial", 0, index)
            if better(response, None):
                pbest_results[index] = response
        generation = 0
        while len(self.trace) < self.budget:
            # Social best is frozen for this entire synchronous generation.
            global_best = None if self.best_vector is None else self.best_vector.copy()
            complete = True
            for index in range(self.size):
                if len(self.trace) >= self.budget:
                    complete = False
                    break
                r1,r2 = self.rng.random((2,self.dimension))
                cognitive = (self.cognitive*r1*(pbest[index]-positions[index])
                             if pbest_results[index] is not None else 0.0)
                social = self.social*r2*(global_best-positions[index]) if global_best is not None else 0.0
                velocities[index] = np.clip(self.inertia*velocities[index]+cognitive+social,
                                            -velocity_cap,velocity_cap)
                positions[index] = np.clip(positions[index]+velocities[index],self.lower,self.upper)
                response = self._evaluate(evaluate, positions[index], "pso", generation+1,index)
                if better(response,pbest_results[index]):
                    pbest[index],pbest_results[index] = positions[index].copy(),response
            if complete:
                generation += 1
        return self._report(self.backend_id,generation,self.config())

    def config(self):
        return dict(inertia=self.inertia,cognitive=self.cognitive,social=self.social,
                    max_velocity_fraction=self.fraction,update="synchronous",boundary="clip")
