"""路线A 热启动采样器与优化后端契约测试（纯合成，physical_call_count=0）。

覆盖：
- WarmStartConfig 参数校验与来源契约；
- ProposedDesigns 形状/边界/唯一性/预算守恒/来源标注；
- 采样模块不含 BO 采集函数、DE 差分、PSO 速度更新；
- 采样器不读取真实标签、不写回共享观测；
- BO/DE/PSO 三后端预算守恒；
- DE 外部初始种群、集中度诊断与 LHS 补充；
- PSO 只以真实评价更新 pbest/gbest；
- 合成任务标签来源标注。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from research.concorde_metaopt.optimization.baseline_bo import BaselineError
from research.concorde_metaopt.optimization.baseline_de import (
    DifferentialEvolutionBaseline,
    _population_diversity,
)
from research.concorde_metaopt.optimization.baseline_pso import (
    ParticleSwarmBaseline,
    PSOError,
)
from research.concorde_metaopt.warm_start import experiment as exp
from research.concorde_metaopt.warm_start import sampler as sampler_module
from research.concorde_metaopt.warm_start import synthetic as syn
from research.concorde_metaopt.warm_start.sampler import (
    SOURCE_FOMAML_KSHOT,
    SOURCE_PRETRAIN,
    SOURCE_RANDOM,
    SOURCE_ZERO_SHOT,
    ProposedDesigns,
    WarmStartConfig,
    WarmStartSampler,
)
from research.concorde_metaopt.warm_start.surrogate import zero_shot_snapshot


@pytest.fixture(scope="module")
def task():
    return syn.evaluation_tasks()[0]


@pytest.fixture(scope="module")
def context(task):
    return list(task.context)


@pytest.fixture(scope="module")
def snapshot():
    return zero_shot_snapshot(seed=42)


def _support(task, k, seed=0):
    records = exp._support_records(task, k, seed)
    return {
        "designs": [record["unit_vector"] for record in records],
        "records": [dict(record) for record in records],
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "not_a_source"},
        {"support_size": -1},
        {"diversity_weight": 1.5},
        {"feasibility_weight": -0.1},
        {"candidate_pool_size": 0},
        {"seed": -1},
    ],
)
def test_warm_start_config_validation(kwargs):
    with pytest.raises(ValueError):
        WarmStartConfig(**kwargs)


def test_non_random_source_requires_matching_snapshot():
    with pytest.raises(ValueError):
        WarmStartSampler(WarmStartConfig(source=SOURCE_ZERO_SHOT, support_size=0))
    other = zero_shot_snapshot(seed=1)
    with pytest.raises(ValueError):
        WarmStartSampler(
            WarmStartConfig(source=SOURCE_FOMAML_KSHOT, support_size=0), snapshot=other
        )


def test_random_proposal_contract(context):
    sampler = WarmStartSampler(WarmStartConfig(source=SOURCE_RANDOM, support_size=0, seed=3))
    proposal = sampler.propose(
        task_context=context, design_space=syn.DIMENSION, n_new=6, seed=11
    )
    assert isinstance(proposal, ProposedDesigns)
    designs = np.asarray(proposal.X_init, dtype=float)
    assert designs.shape == (6, syn.DIMENSION)
    assert np.all(designs >= 0.0) and np.all(designs <= 1.0)
    assert np.unique(np.round(designs, 12), axis=0).shape[0] == 6
    assert proposal.predicted_objective is None
    assert proposal.predicted_constraint_margin is None
    assert proposal.predicted_feasibility is None
    assert proposal.uncertainty is None
    assert proposal.model_sha is not None and len(proposal.model_sha) == 64
    assert proposal.provenance["physical_call_count"] == 0
    assert proposal.provenance["source_kind"] == syn.SOURCE_KIND
    assert proposal.source == SOURCE_RANDOM
    assert proposal.sample_budget["support_observations"] == 0
    assert proposal.sample_budget["planned_true_evaluations"] == 6
    assert proposal.sample_budget["physical_call_count"] == 0
    assert proposal.uniformity_distance is not None and proposal.uniformity_distance > 0.0


def test_random_proposal_uses_supplied_candidate_pool(context):
    pool = np.random.default_rng(5).random((24, syn.DIMENSION))
    sampler = WarmStartSampler(WarmStartConfig(source=SOURCE_RANDOM, support_size=0, seed=1))
    proposal = sampler.propose(
        task_context=context,
        design_space=syn.DIMENSION,
        candidate_pool=pool,
        n_new=4,
        seed=2,
    )
    designs = np.asarray(proposal.X_init, dtype=float)
    assert designs.shape == (4, syn.DIMENSION)
    distances = np.min(
        np.linalg.norm(designs[:, None, :] - pool[None, :, :], axis=2), axis=1
    )
    assert np.all(distances < 1e-12)


def test_zero_shot_proposal_contract_and_determinism(task, context, snapshot):
    sampler = WarmStartSampler(
        WarmStartConfig(
            source=SOURCE_ZERO_SHOT,
            support_size=2,
            diversity_weight=0.5,
            candidate_pool_size=128,
            seed=4,
        ),
        snapshot=snapshot,
    )
    support = _support(task, 2)
    first = sampler.propose(
        task_context=context,
        design_space=syn.DIMENSION,
        observed_support=support,
        n_new=5,
        seed=7,
    )
    second = sampler.propose(
        task_context=context,
        design_space=syn.DIMENSION,
        observed_support=support,
        n_new=5,
        seed=7,
    )
    assert np.allclose(first.X_init, second.X_init, atol=0.0, rtol=0.0)
    assert np.asarray(first.predicted_objective).shape == (5,)
    assert np.asarray(first.predicted_constraint_margin).shape == (5,)
    feasibility = np.asarray(first.predicted_feasibility, dtype=float)
    assert feasibility.shape == (5,)
    assert np.all(feasibility >= 0.0) and np.all(feasibility <= 1.0)
    assert first.model_sha is not None and len(first.model_sha) == 64
    assert first.sample_budget["support_observations"] == 2
    assert first.sample_budget["planned_true_evaluations"] == 7  # 2 个共享观测 + 5 个提案
    assert first.provenance["physical_call_count"] == 0


def test_support_size_mismatch_raises(task, context, snapshot):
    sampler = WarmStartSampler(
        WarmStartConfig(source=SOURCE_ZERO_SHOT, support_size=2), snapshot=snapshot
    )
    with pytest.raises(ValueError):
        sampler.propose(
            task_context=context,
            design_space=syn.DIMENSION,
            observed_support=_support(task, 1),
            n_new=2,
        )


def test_sampler_module_has_no_optimizer_internals():
    import ast

    source = Path(sampler_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = set()
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            names.add(node.attr.lower())
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name.lower())
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    forbidden = ("acquisition", "differential", "velocity", "gbest", "pbest", "crossover")
    for token in forbidden:
        assert token not in names, "sampler.py 不应包含后端优化内部实现: %s" % token
    for module in imported:
        assert "baseline_" not in module and "optimization" not in module, module
    assert not hasattr(sampler_module, "DifferentialEvolutionBaseline")
    assert not hasattr(sampler_module, "ParticleSwarmBaseline")
    assert not hasattr(sampler_module, "ConstrainedBayesianOptimizer")


def test_sampler_never_reads_truth_or_mutates_support(monkeypatch, task, context, snapshot):
    support = _support(task, 2)
    frozen = json.dumps(support, sort_keys=True, default=list)
    calls = {"count": 0}
    original = type(task).truth

    def counting_truth(self, designs):
        calls["count"] += 1
        return original(self, designs)

    monkeypatch.setattr(type(task), "truth", counting_truth)
    sampler = WarmStartSampler(
        WarmStartConfig(source=SOURCE_ZERO_SHOT, support_size=2), snapshot=snapshot
    )
    proposal = sampler.propose(
        task_context=context,
        design_space=syn.DIMENSION,
        observed_support=support,
        n_new=3,
        seed=1,
    )
    assert calls["count"] == 0, "采样阶段不得读取真实标签"
    assert json.dumps(support, sort_keys=True, default=list) == frozen, "采样阶段不得写回真实观测"
    assert np.asarray(proposal.X_init).shape == (3, syn.DIMENSION)


def test_three_backends_conserve_budget(task, snapshot):
    snapshots = {SOURCE_ZERO_SHOT: snapshot}
    reference = {"status": "NOT_USED", "objective_star": None}
    for backend in ("bo", "de", "pso"):
        record, _ = exp.run_single(
            task=task,
            backend=backend,
            source=SOURCE_ZERO_SHOT,
            budget=16,
            k=2,
            rho=0.25,
            seed=0,
            snapshots=snapshots,
            reference=reference,
            matrix_tag="pytest",
        )
        assert len(record["trace"]) == 16, backend
        assert record["metrics"]["evaluations"] == 16, backend
        assert record["metrics"]["budget_conserved"] is True, backend
        assert record["physical_call_count"] == 0, backend
        assert record["support_size"] == 2, backend
        assert record["proposal"]["n_new"] >= 1, backend


def test_de_external_initial_population_and_concentration(task):
    rng = np.random.default_rng(0)
    population = 0.5 + 1e-4 * rng.random((8, syn.DIMENSION))
    de = DifferentialEvolutionBaseline(
        dimension=syn.DIMENSION,
        budget=12,
        seed=0,
        population_size=8,
        initial_population=population,
    )
    result = de.run(task.evaluate_unit)
    assert result["evaluations"] <= 12
    assert result["initial_population_source"] == "external"
    assert result["initial_population_size"] == 8
    assert result["initial_population_concentrated"] is True
    assert result["lhs_supplement_count"] > 0
    assert abs(result["initial_population_diversity"] - _population_diversity(population)) < 1e-9
    initial = result["trace"][:8]
    assert all(record["phase"] == "initialisation" for record in initial)
    kept = np.asarray([record["unit_vector"] for record in initial[:4]], dtype=float)
    assert np.allclose(kept, population[:4], atol=1e-12)
    vector = np.asarray([record["unit_vector"] for record in result["trace"]], dtype=float)
    assert vector.shape == (len(result["trace"]), syn.DIMENSION)


@pytest.mark.parametrize(
    "population",
    [
        np.full((3, syn.DIMENSION), 0.5),  # Np < MIN_POPULATION_SIZE
        np.full((8, syn.DIMENSION - 1), 0.5),  # 维度不符
        np.full((8, syn.DIMENSION), 1.5),  # 越界
    ],
)
def test_de_rejects_invalid_initial_population(task, population):
    with pytest.raises((ValueError, BaselineError)):
        DifferentialEvolutionBaseline(
            dimension=syn.DIMENSION,
            budget=12,
            seed=0,
            initial_population=population,
        ).run(task.evaluate_unit)


def _find_feasible(task, seed=0, limit=4000):
    rng = np.random.default_rng(seed)
    for _ in range(limit):
        design = rng.random(syn.DIMENSION)
        if task.evaluate_unit(design)["feasible"]:
            return design
    raise AssertionError("合成任务中未找到可行点")


def test_pso_uses_true_evaluations_for_pbest_and_gbest(task):
    rng = np.random.default_rng(3)
    feasible = _find_feasible(task, seed=3)
    positions = np.vstack([feasible, rng.random((4, syn.DIMENSION))])
    swarm = ParticleSwarmBaseline(
        dimension=syn.DIMENSION,
        budget=12,
        seed=0,
        swarm_size=5,
        initial_positions=positions,
    )
    result = swarm.run(task.evaluate_unit)
    initial = result["trace"][:5]
    assert all(record["phase"] == "initialisation" for record in initial)
    feasible_initial = [
        record
        for record in initial
        if record["feasible"] and record["objective"] is not None
    ]
    assert feasible_initial, "初始群体应含真实可行点"
    expected = min(feasible_initial, key=lambda record: record["objective"])
    assert result["initial_gbest"]["feasible"] is True
    assert abs(result["initial_gbest"]["objective"] - expected["objective"]) < 1e-12
    assert np.allclose(result["initial_gbest"]["position"], expected["position"])
    for index in range(5):
        history = [
            record
            for record in result["trace"]
            if record["particle_index"] == index
            and record["feasible"]
            and record["objective"] is not None
        ]
        assert history, "粒子 %d 应至少有一次真实可行评价" % index
        best_objective = min(record["objective"] for record in history)
        assert abs(result["final_swarm"][index]["pbest_objective"] - best_objective) < 1e-12
    dumped = json.dumps(result, default=float)
    assert "predicted" not in dumped
    assert result["physical_calls"] == 0


def test_pso_frozen_interface_validation():
    with pytest.raises(PSOError):
        ParticleSwarmBaseline(dimension=syn.DIMENSION, budget=12, seed=0, inertia=-0.5)
    with pytest.raises(PSOError):
        ParticleSwarmBaseline(
            dimension=syn.DIMENSION, budget=12, seed=0, cognitive=-1.0
        )
    with pytest.raises(PSOError):
        ParticleSwarmBaseline(
            dimension=syn.DIMENSION,
            budget=12,
            seed=0,
            swarm_size=5,
            initial_positions=np.full((4, syn.DIMENSION), 0.5),
        )
    with pytest.raises(PSOError):
        ParticleSwarmBaseline(
            dimension=syn.DIMENSION,
            budget=12,
            seed=0,
            swarm_size=5,
            initial_velocities=np.full((5, syn.DIMENSION), 0.5),
            max_velocity_fraction=0.2,
        )


def test_synthetic_task_labels_are_declared(task):
    result = task.evaluate_unit([0.5] * syn.DIMENSION)
    assert result["status"] == "VALID"
    assert result["physical_call_count"] == 0
    assert result["analysis_calls"] == 0
    truth = task.truth([[0.5] * syn.DIMENSION])
    assert truth["source_kind"] == syn.SOURCE_KIND
    assert truth["physical_call_count"] == 0
    assert np.asarray(truth["objective"]).shape == (1,)
