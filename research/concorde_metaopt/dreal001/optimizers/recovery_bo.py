"""Regenerated NumPy GP-EI backend; not recovered maml_opt or admission authority.

Fixed RBF hyperparameters, exact Cholesky GP on finite VALID Di observations,
and kernel-smoothed feasibility weighting. Failed solves are feasibility events,
never finite objective penalties. Acquisition is optimized over a seeded LHS
pool, not a continuous global optimizer. No solver, raw loader or label source.
"""
from __future__ import annotations
import math
from typing import Mapping
import numpy as np

BACKEND_ID = "RECOVERY_NUMPY_RBF_GP_EI_V1"


def _bounds(lower, upper):
    lower, upper = np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)
    if (lower.ndim != 1 or not len(lower) or lower.shape != upper.shape
            or not np.all(np.isfinite([lower, upper])) or np.any(upper <= lower)):
        raise ValueError("finite strictly ordered vector bounds required")
    return lower, upper


def generate_initial_designs(lower, upper, *, count, seed, method="lhs"):
    lower, upper = _bounds(lower, upper)
    if method != "lhs" or isinstance(count, bool) or int(count) != count or count < 1:
        raise ValueError("positive integer count and lhs required")
    count = int(count)
    rng = np.random.default_rng(seed)
    unit = np.column_stack([(rng.permutation(count) + rng.random(count)) / count
                            for _ in lower])
    return lower + unit * (upper - lower)


def expected_improvement(mean, variance, incumbent):
    """Minimization EI under a Gaussian posterior, in standardized units."""
    mean, variance = np.asarray(mean, dtype=float), np.asarray(variance, dtype=float)
    if (mean.shape != variance.shape or not np.all(np.isfinite(mean))
            or not np.all(np.isfinite(variance)) or np.any(variance < 0)
            or not np.isfinite(incumbent)):
        raise ValueError("finite Gaussian moments required")
    sigma = np.sqrt(variance)
    improvement = float(incumbent) - mean
    z = np.divide(improvement, sigma, out=np.zeros_like(mean), where=sigma > 1e-12)
    cdf = np.array([0.5 * (1 + math.erf(float(v) / math.sqrt(2))) for v in z.flat]).reshape(z.shape)
    density = np.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return np.where(sigma > 1e-12, improvement * cdf + sigma * density,
                    np.maximum(improvement, 0.0))


class RecoveryGaussianProcessBO:
    backend_id = BACKEND_ID

    def __init__(self, lower, upper, *, seed=0, candidate_count=256,
                 length_scale=0.35, noise_variance=1e-6):
        self.lower, self.upper = _bounds(lower, upper)
        if (isinstance(candidate_count, bool) or int(candidate_count) != candidate_count
                or candidate_count < 2 or not np.isfinite(length_scale) or length_scale <= 0
                or not np.isfinite(noise_variance) or noise_variance <= 0):
            raise ValueError("invalid GP/acquisition configuration")
        self.rng = np.random.default_rng(seed)
        self.candidate_count = int(candidate_count)
        self.length_scale = float(length_scale)
        self.noise_variance = float(noise_variance)
        self.rows = []
        self.pending = []
        self.last_acquisition = {}

    def _unit(self, vector):
        vector = np.asarray(vector, dtype=float)
        if (vector.shape != self.lower.shape or not np.all(np.isfinite(vector))
                or np.any(vector < self.lower) or np.any(vector > self.upper)):
            raise ValueError("finite in-bounds design required")
        return (vector - self.lower) / (self.upper - self.lower)

    def tell(self, vector, result: Mapping):
        x = self._unit(vector)
        valid, feasible = result.get("valid"), result.get("feasible")
        value = result.get("objective")
        if not isinstance(valid, (bool, np.bool_)) or not isinstance(feasible, (bool, np.bool_)):
            raise ValueError("explicit boolean valid/feasible required")
        if valid:
            if value is None or not np.isfinite(value) or value < 0:
                raise ValueError("VALID objective must be finite nonnegative")
        elif value is not None or feasible:
            raise ValueError("failed objective must be null and infeasible")
        if any(np.max(np.abs(x - row[0])) <= 1e-12 for row in self.rows):
            raise ValueError("duplicate observation; cached reads must not refit GP")
        self.rows.append((x.copy(), None if value is None else float(value), bool(feasible)))
        self.pending = [p for p in self.pending if np.max(np.abs(x - p)) > 1e-12]

    def _kernel(self, left, right):
        distance = np.sum((left[:, None, :] - right[None, :, :]) ** 2, axis=2)
        return np.exp(-0.5 * distance / self.length_scale ** 2)

    def posterior(self, unit_candidates):
        candidates = np.asarray(unit_candidates, dtype=float)
        if (candidates.ndim != 2 or candidates.shape[1] != len(self.lower)
                or not np.all(np.isfinite(candidates)) or np.any(candidates < 0)
                or np.any(candidates > 1)):
            raise ValueError("finite unit candidate matrix required")
        observed = [row for row in self.rows if row[1] is not None]
        if not observed:
            return np.zeros(len(candidates)), np.ones(len(candidates)), 0.0, 1.0
        x = np.array([row[0] for row in observed])
        y = np.array([row[1] for row in observed])
        center, scale = float(y.mean()), max(float(y.std()), 1.0)
        gram = self._kernel(x, x) + self.noise_variance * np.eye(len(x))
        factor = np.linalg.cholesky(gram)
        alpha = np.linalg.solve(factor.T, np.linalg.solve(factor, (y - center) / scale))
        cross = self._kernel(x, candidates)
        mean = cross.T @ alpha
        projected = np.linalg.solve(factor, cross)
        variance = np.maximum(1.0 - np.sum(projected * projected, axis=0), 0.0)
        return mean, variance, center, scale

    def ask(self):
        seed = int(self.rng.integers(0, 2**31))
        candidates = generate_initial_designs(np.zeros_like(self.lower), np.ones_like(self.upper),
                                             count=self.candidate_count, seed=seed)
        used = [row[0] for row in self.rows] + self.pending
        if used:
            candidates = candidates[[not any(np.max(np.abs(x - old)) <= 1e-12 for old in used)
                                     for x in candidates]]
        if not len(candidates):
            raise RuntimeError("candidate pool exhausted")
        mean, variance, center, scale = self.posterior(candidates)
        if self.rows:
            weights = self._kernel(candidates, np.array([row[0] for row in self.rows]))
            feasible = np.array([row[2] for row in self.rows], dtype=float)
            # Beta(1,1) pseudocounts: explicitly a kernel feasibility heuristic,
            # not a claimed GP classifier or an implicit finite failure target.
            probability = (1.0 + weights @ feasible) / (2.0 + weights.sum(axis=1))
        else:
            probability = np.full(len(candidates), 0.5)
        incumbents = [row[1] for row in self.rows if row[2]]
        if incumbents:
            score = expected_improvement(mean, variance, (min(incumbents) - center) / scale) * probability
            strategy = "GP_EI_KERNEL_FEASIBILITY"
        else:
            score = np.sqrt(variance) * probability
            strategy = "FEASIBILITY_WEIGHTED_UNCERTAINTY"
        index = int(np.argmax(score))
        chosen = candidates[index].copy()
        self.pending.append(chosen)
        self.last_acquisition = dict(backend=self.backend_id, strategy=strategy,
                                    observations=len(self.rows),
                                    objective_observations=sum(row[1] is not None for row in self.rows),
                                    score=float(score[index]), candidate_count=len(candidates),
                                    length_scale=self.length_scale, noise_variance=self.noise_variance)
        return dict(design_vector=self.lower + chosen * (self.upper - self.lower),
                    acquisition=dict(self.last_acquisition))
