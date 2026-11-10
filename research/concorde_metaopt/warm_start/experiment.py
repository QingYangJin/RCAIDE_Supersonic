"""路线A：优化器无关热启动的合成实验矩阵（D-NEXT-001-A）。

本模块只做合成/代理实验：
- physical_call_count = 0，未启动任何 VSPAERO / SU2 / RCAIDE Mission / WaveDrag；
- 真值来自 warm_start.synthetic 的解析合成任务（SYNTHETIC_ANALOGUE）；
- 采样器只提供初始种群/起点，BO/DE/PSO 各自用真实（合成真值）评价推进，
  预测值绝不写回真实观测。

运行方式：

    python -m research.concorde_metaopt.warm_start.experiment

产物目录：research/concorde_metaopt/optimization_runs/dnext001-a-warmstart-<stamp>/
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from ..optimization.baseline_de import DifferentialEvolutionBaseline
from ..optimization.baseline_pso import ParticleSwarmBaseline
from . import synthetic as syn
from .bo_adapter import ADAPTER_VERSION, run_warm_bo
from .sampler import (
    SOURCE_FOMAML_KSHOT,
    SOURCE_PRETRAIN,
    SOURCE_RANDOM,
    SOURCE_ZERO_SHOT,
    SOURCES,
    ProposedDesigns,
    WarmStartConfig,
    WarmStartSampler,
)
from .surrogate import (
    SURROGATE_VERSION,
    collect_meta_data,
    fomaml_snapshot,
    pretrain_snapshot,
    zero_shot_snapshot,
)

EXPERIMENT_STAGE = "D-NEXT-001-A"
BACKENDS: Tuple[str, ...] = ("bo", "de", "pso")
EARLY_BUDGETS: Tuple[int, ...] = (8, 16, 32, 64)
MAX_INIT = 8
BO_INIT_CAP = 4
SUPPORT_SEED_OFFSET = 8100
RUN_SEED = 0


def _json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    raise TypeError("无法序列化类型 %r" % (type(value),))


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _code_sha(root: str) -> Dict[str, str]:
    relative = [
        "research/concorde_metaopt/warm_start/synthetic.py",
        "research/concorde_metaopt/warm_start/surrogate.py",
        "research/concorde_metaopt/warm_start/sampler.py",
        "research/concorde_metaopt/warm_start/bo_adapter.py",
        "research/concorde_metaopt/warm_start/experiment.py",
        "research/concorde_metaopt/optimization/baseline_de.py",
        "research/concorde_metaopt/optimization/baseline_pso.py",
    ]
    result: Dict[str, str] = {}
    for item in relative:
        path = os.path.join(root, item)
        result[item] = _sha256_file(path) if os.path.isfile(path) else "NOT_FOUND"
    return result


def _git_sha(root: str) -> Tuple[str, bool]:
    def _run(args: Sequence[str]) -> str:
        try:
            output = subprocess.run(
                ["git", "-C", root, *args], capture_output=True, text=True, check=False
            )
            return output.stdout.strip()
        except Exception:  # pragma: no cover - git 缺失时如实降级
            return "UNKNOWN"

    head = _run(["rev-parse", "HEAD"])
    status = _run(["status", "--porcelain"])
    return head or "UNKNOWN", bool(status)


def _task_record(task: syn.SyntheticTask) -> Dict[str, Any]:
    return task.to_dict()


def _support_records(task: syn.SyntheticTask, k: int, seed: int) -> List[Dict[str, Any]]:
    """共享观测：K 个点的真实（合成）评价，跨来源/后端完全一致。"""
    if k == 0:
        return []
    rng = np.random.default_rng(seed + SUPPORT_SEED_OFFSET + k)
    designs = rng.random((int(k), syn.DIMENSION))
    records: List[Dict[str, Any]] = []
    for vector in designs:
        result = task.evaluate_unit(vector)
        record = dict(result)
        record["unit_vector"] = [float(value) for value in vector]
        records.append(record)
    return records


def _make_sampler(
    source: str, k: int, rho: float, seed: int, snapshot: Any = None
) -> WarmStartSampler:
    return WarmStartSampler(
        WarmStartConfig(
            source=source,
            support_size=int(k),
            diversity_weight=float(rho),
            candidate_pool_size=256,
            seed=int(seed),
        ),
        snapshot=snapshot,
    )


def _build_snapshots(meta_data: Mapping[str, Any], seed: int = 42) -> Dict[str, Any]:
    """一次性构建三条来源的代理快照（零样本 / 监督预训练 / FOMAML）。"""
    started = time.time()
    zero = zero_shot_snapshot(seed=seed)
    pretrain = pretrain_snapshot(meta_data, seed=seed)
    fomaml = fomaml_snapshot(meta_data, seed=seed)
    return {
        "snapshots": {
            SOURCE_ZERO_SHOT: zero,
            SOURCE_PRETRAIN: pretrain,
            SOURCE_FOMAML_KSHOT: fomaml,
        },
        "build_seconds": round(time.time() - started, 3),
        "meta_tasks": int(meta_data.get("n_tasks", 0)),
        "meta_designs_per_task": int(meta_data.get("n_designs", 0)),
    }


def _proposal(
    task: syn.SyntheticTask,
    sampler: WarmStartSampler,
    support: Sequence[Mapping[str, Any]],
    n_new: int,
    seed: int,
) -> ProposedDesigns:
    payload: Any = None
    if support:
        payload = {
            "designs": [record["unit_vector"] for record in support],
            "records": [dict(record) for record in support],
        }
    return sampler.propose(
        task_context=task.context,
        design_space=syn.DIMENSION,
        observed_support=payload,
        n_new=int(n_new),
        seed=int(seed),
    )


def _proposal_record(proposal: ProposedDesigns, task: syn.SyntheticTask) -> Dict[str, Any]:
    designs = np.asarray(proposal.X_init, dtype=float)
    truth = task.truth(designs)
    record = proposal.to_dict()
    record["true_feasibility_of_proposal"] = [bool(item) for item in truth["feasibility"]]
    record["true_objective_of_proposal"] = [float(item) for item in truth["objective"]]
    record["true_feasible_count"] = int(np.count_nonzero(truth["feasibility"]))
    if proposal.predicted_feasibility is not None:
        predicted = np.asarray(proposal.predicted_feasibility, dtype=float)
        record["predicted_feasible_count_at_0.5"] = int(np.count_nonzero(predicted >= 0.5))
        record["predicted_feasibility_mean"] = float(np.mean(predicted))
    return record


def _run_bo(
    task: syn.SyntheticTask,
    sampler: WarmStartSampler,
    support: Sequence[Mapping[str, Any]],
    budget: int,
    seed: int,
) -> Dict[str, Any]:
    n_init = max(1, min(BO_INIT_CAP, int(budget) - len(support)))
    return run_warm_bo(
        task=task,
        sampler=sampler,
        support_records=list(support),
        budget=int(budget),
        seed=int(seed),
        n_init=n_init,
        candidate_count=256,
    )


def _with_support_trace(
    result: Dict[str, Any], support: Sequence[Mapping[str, Any]]
) -> Dict[str, Any]:
    """把 K 个共享观测并入 trace，使总真实评价数 = K + 后端评价数，与 BO 口径一致。"""
    merged: List[Dict[str, Any]] = []
    for index, record in enumerate(support):
        row = dict(record)
        row["phase"] = "support"
        row["support_index"] = int(index)
        merged.append(row)
    merged.extend(list(result.get("trace", ())))
    result["trace"] = merged
    result["evaluations"] = int(len(merged))
    result["support_evaluations"] = int(len(support))
    return result


def _run_de(
    task: syn.SyntheticTask,
    sampler: WarmStartSampler,
    support: Sequence[Mapping[str, Any]],
    budget: int,
    seed: int,
) -> Dict[str, Any]:
    remaining = int(budget) - len(support)
    population = max(4, min(MAX_INIT, remaining))
    proposal = _proposal(task, sampler, support, population, seed)
    algorithm = DifferentialEvolutionBaseline(
        dimension=syn.DIMENSION,
        budget=remaining,
        seed=int(seed),
        population_size=population,
        initial_population=proposal.X_init,
    )
    result = algorithm.run(task.evaluate_unit)
    result = _with_support_trace(result, support)
    result["proposal"] = _proposal_record(proposal, task)
    result["initial_population_size"] = int(population)
    return result


def _run_pso(
    task: syn.SyntheticTask,
    sampler: WarmStartSampler,
    support: Sequence[Mapping[str, Any]],
    budget: int,
    seed: int,
) -> Dict[str, Any]:
    remaining = int(budget) - len(support)
    swarm = max(4, min(MAX_INIT, remaining))
    proposal = _proposal(task, sampler, support, swarm, seed)
    algorithm = ParticleSwarmBaseline(
        dimension=syn.DIMENSION,
        budget=remaining,
        seed=int(seed),
        swarm_size=swarm,
        initial_positions=proposal.X_init,
    )
    result = algorithm.run(task.evaluate_unit)
    result = _with_support_trace(result, support)
    result["proposal"] = _proposal_record(proposal, task)
    result["swarm_size"] = int(swarm)
    return result


_RUNNERS = {"bo": _run_bo, "de": _run_de, "pso": _run_pso}


def _record_feasible(record: Mapping[str, Any]) -> bool:
    return bool(record.get("feasible"))


def _record_objective(record: Mapping[str, Any]) -> Optional[float]:
    value = record.get("objective")
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _best_feasible(trace: Sequence[Mapping[str, Any]]) -> Tuple[Optional[int], Optional[float]]:
    best_index: Optional[int] = None
    best_value: Optional[float] = None
    for index, record in enumerate(trace):
        if not _record_feasible(record):
            continue
        objective = _record_objective(record)
        if objective is None:
            continue
        if best_value is None or objective < best_value:
            best_value = objective
            best_index = index
    return best_index, best_value


def _anytime(trace: Sequence[Mapping[str, Any]], targets: Iterable[int]) -> Dict[str, Optional[float]]:
    result: Dict[str, Optional[float]] = {}
    for target in targets:
        value: Optional[float] = None
        for record in trace[: int(target)]:
            if not _record_feasible(record):
                continue
            objective = _record_objective(record)
            if objective is None:
                continue
            if value is None or objective < value:
                value = objective
        result["anytime_best_feasible_%d" % int(target)] = value
    return result


def _metrics(
    result: Mapping[str, Any],
    reference: Mapping[str, Any],
    budget: int,
) -> Dict[str, Any]:
    trace = list(result.get("trace", ()))
    feasible_flags = [_record_feasible(record) for record in trace]
    feasible_count = int(sum(feasible_flags))
    first_index = next((index for index, flag in enumerate(feasible_flags) if flag), None)
    best_index, best_value = _best_feasible(trace)
    reference_value = reference.get("objective_star")
    gap: Optional[float] = None
    if best_value is not None and reference_value is not None:
        scale = max(abs(float(reference_value)), 1e-9)
        gap = float(best_value - float(reference_value)) / scale
    metrics: Dict[str, Any] = {
        "evaluations": int(len(trace)),
        "budget": int(budget),
        "budget_conserved": bool(len(trace) == int(budget)),
        "feasible_evaluations": feasible_count,
        "feasible_hit_rate": float(feasible_count) / float(budget),
        "first_feasible_eval": (int(first_index) + 1) if first_index is not None else None,
        "best_feasible_value": best_value,
        "best_feasible_eval_index": (int(best_index) + 1) if best_index is not None else None,
        "gap_to_reference": gap,
        "reference_objective_star": (float(reference_value) if reference_value is not None else None),
        "reference_status": reference.get("status"),
        "physical_call_count": int(result.get("physical_call_count", 0)),
    }
    metrics.update(_anytime(trace, EARLY_BUDGETS))
    return metrics


def _diversity(result: Mapping[str, Any]) -> Optional[float]:
    for key in ("final_population_diversity", "final_swarm_diversity"):
        value = result.get(key)
        if value is not None:
            return float(value)
    return None


def trace_to_json(trace: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for record in trace:
        row: Dict[str, Any] = {}
        for key, value in record.items():
            if isinstance(value, np.ndarray):
                row[key] = value.tolist()
            elif isinstance(value, (np.floating, np.integer, np.bool_)):
                row[key] = value.item()
            else:
                row[key] = value
        rows.append(row)
    return rows


def run_single(
    *,
    task: syn.SyntheticTask,
    backend: str,
    source: str,
    budget: int,
    k: int,
    rho: float,
    seed: int,
    snapshots: Mapping[str, Any],
    reference: Mapping[str, Any],
    matrix_tag: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    sampler = _make_sampler(
        source, k, rho, seed, snapshot=None if source == SOURCE_RANDOM else snapshots[source]
    )
    support = _support_records(task, k, seed)
    started = time.time()
    result = _RUNNERS[backend](task, sampler, support, budget, seed)
    elapsed = time.time() - started
    metrics = _metrics(result, reference, budget)
    predictions = result.get("proposal") or {}
    run_id = "%s-%s-%s-%s-K%d-B%d-rho%s-s%d" % (
        matrix_tag,
        task.family,
        backend,
        source.replace("_", "-"),
        k,
        budget,
        ("%g" % rho).replace(".", "p"),
        seed,
    )
    config: Dict[str, Any] = {
        "run_id": run_id,
        "matrix_tag": matrix_tag,
        "stage": EXPERIMENT_STAGE,
        "route": "A",
        "backend": backend,
        "source": source,
        "task_id": task.task_id,
        "task_family": task.family,
        "task_context": [float(item) for item in task.context],
        "design_dimension": syn.DIMENSION,
        "design_set": "synthetic_12d_unit_cube",
        "evaluator_id": "synthetic_analogue_truth_%s" % task.family,
        "fidelity": "SYNTHETIC",
        "source_kind": syn.SOURCE_KIND,
        "physical_validation_status": "NOT_APPLICABLE_SYNTHETIC",
        "solver_version": "route-a-synthetic-truth-v1",
        "budget_B": int(budget),
        "K": int(k),
        "diversity_weight_rho": float(rho),
        "seed": int(seed),
        "initial_population_size": int(
            result.get("initial_population_size", result.get("swarm_size", result.get("initial_size", 0)))
        ),
        "support_size": int(len(support)),
        "physical_call_count": 0,
        "surrogate_version": SURROGATE_VERSION,
        "bo_adapter_version": ADAPTER_VERSION if backend == "bo" else None,
        "elapsed_seconds": round(elapsed, 4),
        "proposal": {
            "model_sha": predictions.get("model_sha"),
            "uniformity_distance": predictions.get("uniformity_distance"),
            "min_support_distance": predictions.get("min_support_distance"),
            "predicted_feasibility_mean": predictions.get("predicted_feasibility_mean"),
            "predicted_feasible_count_at_0.5": predictions.get("predicted_feasible_count_at_0.5"),
            "true_feasible_count": predictions.get("true_feasible_count"),
            "n_new": predictions.get("n_new"),
            "source": predictions.get("source"),
            "true_feasibility_of_proposal": predictions.get("true_feasibility_of_proposal"),
        },
    }
    record = dict(config)
    record["metrics"] = metrics
    record["status"] = result.get("status")
    record["termination_reason"] = result.get("termination_reason")
    record["diversity"] = _diversity(result)
    record["first_feasible_evaluation_backend"] = result.get("first_feasible_evaluation")
    record["best_feasible_backend"] = result.get("best_feasible")
    record["duplicates_ignored"] = result.get("duplicates_ignored")
    record["trace"] = trace_to_json(result.get("trace", ()))
    record["result_meta"] = {
        key: _jsonable(result.get(key))
        for key in (
            "evaluations",
            "physical_calls",
            "support_size",
            "initial_size",
            "bo_evaluations",
            "initial_population_source",
            "initial_population_diversity",
            "concentrated",
            "lhs_supplement_count",
            "final_population_diversity",
            "initial_positions_source",
            "initial_gbest",
            "final_swarm_diversity",
            "generations_completed",
            "accepted_trials",
            "rejected_trials",
            "population_size",
            "swarm_size",
            "inertia",
            "cognitive",
            "social",
            "max_velocity_fraction",
        )
        if result.get(key) is not None
    }
    return record, result


def build_matrix() -> List[Dict[str, Any]]:
    """最小可复跑矩阵。

    - smoke：覆盖全部 B in {16,32,64,128}，K in {0,5}，rho=0，random 与 FOMAML；
    - extension：B=64，K in {1,3}，rho in {0.25,0.5,0.75}，FOMAML；
    - source_compare：B=64，K=3，rho=0，zero-shot 与 pretrain（与 random/FOMAML 同格配对）。
    """
    cells: List[Dict[str, Any]] = []
    for budget in (16, 32, 64, 128):
        for k in (0, 5):
            for source in (SOURCE_RANDOM, SOURCE_FOMAML_KSHOT):
                cells.append(
                    {"matrix_tag": "smoke", "budget": budget, "k": k, "rho": 0.0, "source": source}
                )
    for k in (1, 3):
        for rho in (0.0, 0.25, 0.5, 0.75):
            cells.append(
                {"matrix_tag": "extension", "budget": 64, "k": k, "rho": rho, "source": SOURCE_FOMAML_KSHOT}
            )
    for source in (SOURCE_ZERO_SHOT, SOURCE_PRETRAIN):
        cells.append(
            {"matrix_tag": "source_compare", "budget": 64, "k": 3, "rho": 0.0, "source": source}
        )
    return cells


def _run_dir(output_root: str, run_id: str) -> str:
    return os.path.join(output_root, "runs", run_id)


def _write_run_artifacts(output_root: str, record: Mapping[str, Any], trace: Sequence[Mapping[str, Any]]) -> None:
    directory = _run_dir(output_root, str(record["run_id"]))
    os.makedirs(directory, exist_ok=True)
    config = {key: value for key, value in record.items() if key not in ("trace", "metrics")}
    with open(os.path.join(directory, "run_config.json"), "w", encoding="utf-8") as handle:
        json.dump(_jsonable(config), handle, ensure_ascii=False, indent=2)
    with open(os.path.join(directory, "evaluations.jsonl"), "w", encoding="utf-8") as handle:
        for row in trace:
            handle.write(json.dumps(_jsonable(row), ensure_ascii=False) + "\n")
    with open(os.path.join(directory, "metrics.json"), "w", encoding="utf-8") as handle:
        json.dump(_jsonable(record["metrics"]), handle, ensure_ascii=False, indent=2)


def _write_csv(path: str, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _paired_comparisons(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, ...], Dict[str, Mapping[str, Any]]] = {}
    for record in records:
        key = (
            record["task_id"],
            record["backend"],
            int(record["budget_B"]),
            int(record["K"]),
            float(record["diversity_weight_rho"]),
            int(record["seed"]),
        )
        grouped.setdefault(key, {})[record["source"]] = record
    rows: List[Dict[str, Any]] = []
    for key, sources in sorted(grouped.items(), key=lambda item: str(item[0])):
        task_id, backend, budget, k, rho, seed = key
        pairs: List[Tuple[str, str]] = []
        if SOURCE_RANDOM in sources:
            for source in SOURCES:
                if source != SOURCE_RANDOM and source in sources:
                    pairs.append((source, SOURCE_RANDOM))
        if SOURCE_FOMAML_KSHOT in sources and SOURCE_PRETRAIN in sources:
            pairs.append((SOURCE_FOMAML_KSHOT, SOURCE_PRETRAIN))
        for treatment, control in pairs:
            left = sources[treatment]
            right = sources[control]
            left_metrics = left["metrics"]
            right_metrics = right["metrics"]
            left_best = left_metrics.get("best_feasible_value")
            right_best = right_metrics.get("best_feasible_value")
            if left_best is None and right_best is None:
                outcome = "tie_both_infeasible"
            elif left_best is None:
                outcome = "loss"
            elif right_best is None:
                outcome = "win"
            elif float(left_best) < float(right_best) - 1e-12:
                outcome = "win"
            elif float(left_best) > float(right_best) + 1e-12:
                outcome = "loss"
            else:
                outcome = "tie"
            first_left = left_metrics.get("first_feasible_eval")
            first_right = right_metrics.get("first_feasible_eval")
            delta_first = (
                float(first_left) - float(first_right)
                if first_left is not None and first_right is not None
                else None
            )
            rows.append(
                {
                    "task_id": task_id,
                    "task_family": left["task_family"],
                    "backend": backend,
                    "budget_B": budget,
                    "K": k,
                    "rho": rho,
                    "seed": seed,
                    "treatment": treatment,
                    "control": control,
                    "treatment_first_feasible_eval": first_left,
                    "control_first_feasible_eval": first_right,
                    "delta_first_feasible_eval": delta_first,
                    "treatment_best_feasible_value": left_best,
                    "control_best_feasible_value": right_best,
                    "treatment_gap": left_metrics.get("gap_to_reference"),
                    "control_gap": right_metrics.get("gap_to_reference"),
                    "treatment_hit_rate": left_metrics.get("feasible_hit_rate"),
                    "control_hit_rate": right_metrics.get("feasible_hit_rate"),
                    "outcome": outcome,
                }
            )
    return rows


def _manifest(output_root: str) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    for directory, _, names in os.walk(output_root):
        for name in sorted(names):
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, output_root).replace("\\", "/")
            if relative in ("data_manifest.json", "SHA256SUMS.txt"):
                continue
            files.append(
                {
                    "path": relative,
                    "bytes": os.path.getsize(path),
                    "sha256": _sha256_file(path),
                }
            )
    return {
        "experiment_id": os.path.basename(output_root),
        "file_count": len(files),
        "files": files,
        "source_kind": syn.SOURCE_KIND,
        "physical_call_count": 0,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def _write_sha256sums(output_root: str) -> None:
    lines: List[str] = []
    for directory, _, names in os.walk(output_root):
        for name in sorted(names):
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, output_root).replace("\\", "/")
            if relative == "SHA256SUMS.txt":
                continue
            lines.append("%s  %s" % (_sha256_file(path), relative))
    with open(os.path.join(output_root, "SHA256SUMS.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(sorted(lines)) + "\n")


def _nanmean(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return None
    return float(np.mean(clean))


def _summary_by_cell(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    buckets: Dict[Tuple[Any, ...], List[Mapping[str, Any]]] = {}
    for record in records:
        key = (
            record["matrix_tag"],
            record["backend"],
            record["source"],
            int(record["budget_B"]),
            int(record["K"]),
            float(record["diversity_weight_rho"]),
        )
        buckets.setdefault(key, []).append(record)
    rows: List[Dict[str, Any]] = []
    for key, items in sorted(buckets.items(), key=lambda item: str(item[0])):
        tag, backend, source, budget, k, rho = key
        firsts = [item["metrics"]["first_feasible_eval"] for item in items]
        bests = [item["metrics"]["best_feasible_value"] for item in items]
        hits = [item["metrics"]["feasible_hit_rate"] for item in items]
        rows.append(
            {
                "matrix_tag": tag,
                "backend": backend,
                "source": source,
                "budget_B": budget,
                "K": k,
                "rho": rho,
                "n_runs": len(items),
                "mean_first_feasible_eval": _nanmean(firsts),
                "feasible_found_rate": float(np.mean([value is not None for value in firsts])),
                "mean_best_feasible_value": _nanmean(bests),
                "mean_feasible_hit_rate": _nanmean(hits),
                "mean_gap": _nanmean([item["metrics"]["gap_to_reference"] for item in items]),
            }
        )
    return rows


def main(argv: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="路线A 合成热启动实验矩阵（physical_call_count=0）")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--stamp", default=None)
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 个 cell（调试用）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    stamp = args.stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    output_root = args.output_root or os.path.join(
        root, "research", "concorde_metaopt", "optimization_runs", "dnext001-a-warmstart-%s" % stamp
    )
    os.makedirs(output_root, exist_ok=True)
    git_head, git_dirty = _git_sha(root)

    tasks = syn.evaluation_tasks()
    meta_tasks = syn.meta_train_tasks(syn.FAMILY_COUPLED_QUADRATIC, count=6, seed=20261110) + \
        syn.meta_train_tasks(syn.FAMILY_ROSENBROCK_BAND, count=6, seed=20261110)
    meta_data = collect_meta_data(meta_tasks, n_designs=40, seed=20261110)
    snapshot_bundle = _build_snapshots(meta_data)
    snapshots = snapshot_bundle["snapshots"]

    references: Dict[str, Dict[str, Any]] = {}
    for task in tasks:
        references[task.task_id] = syn.reference_solution(task, n_starts=32, n_prefilter=4000, seed=0)

    cells = build_matrix()
    if args.limit:
        cells = cells[: int(args.limit)]

    records: List[Dict[str, Any]] = []
    total = len(cells) * len(tasks) * len(BACKENDS)
    counter = 0
    for cell in cells:
        for task in tasks:
            for backend in BACKENDS:
                counter += 1
                record, result = run_single(
                    task=task,
                    backend=backend,
                    source=cell["source"],
                    budget=int(cell["budget"]),
                    k=int(cell["k"]),
                    rho=float(cell["rho"]),
                    seed=RUN_SEED,
                    snapshots=snapshots,
                    reference=references[task.task_id],
                    matrix_tag=cell["matrix_tag"],
                )
                trace = record.pop("trace")
                _write_run_artifacts(output_root, record, trace)
                record["trace"] = trace
                records.append({key: value for key, value in record.items() if key != "trace"})
                print(
                    "[%d/%d] %s %s B=%d K=%d rho=%.2f first=%s best=%s hit=%.2f"
                    % (
                        counter,
                        total,
                        backend,
                        cell["source"],
                        cell["budget"],
                        cell["k"],
                        cell["rho"],
                        record["metrics"]["first_feasible_eval"],
                        record["metrics"]["best_feasible_value"],
                        record["metrics"]["feasible_hit_rate"],
                    ),
                    flush=True,
                )

    metrics_fields = [
        "run_id", "matrix_tag", "backend", "source", "task_id", "task_family", "budget_B",
        "K", "diversity_weight_rho", "seed", "status", "evaluations", "budget_conserved",
        "feasible_evaluations", "feasible_hit_rate", "first_feasible_eval",
        "best_feasible_value", "best_feasible_eval_index", "gap_to_reference",
        "reference_objective_star", "anytime_best_feasible_8", "anytime_best_feasible_16",
        "anytime_best_feasible_32", "anytime_best_feasible_64", "diversity",
        "proposal_predicted_feasibility_mean", "proposal_true_feasible_count",
        "proposal_n_new", "physical_call_count",
    ]
    metric_rows = []
    for record in records:
        row = {
            key: record.get(key)
            for key in (
                "run_id", "matrix_tag", "backend", "source", "task_id", "task_family",
                "budget_B", "K", "diversity_weight_rho", "seed", "status", "diversity",
                "physical_call_count",
            )
        }
        row.update(record["metrics"])
        proposal = record.get("proposal") or {}
        row["proposal_predicted_feasibility_mean"] = proposal.get("predicted_feasibility_mean")
        row["proposal_true_feasible_count"] = proposal.get("true_feasible_count")
        row["proposal_n_new"] = proposal.get("n_new")
        metric_rows.append(row)
    _write_csv(os.path.join(output_root, "metrics.csv"), metric_rows, metrics_fields)

    paired = _paired_comparisons(records)
    if paired:
        _write_csv(
            os.path.join(output_root, "paired_comparisons.csv"),
            paired,
            list(paired[0].keys()),
        )

    cell_rows = _summary_by_cell(records)
    _write_csv(os.path.join(output_root, "cell_summary.csv"), cell_rows, list(cell_rows[0].keys()))

    with open(os.path.join(output_root, "runs.jsonl"), "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_jsonable(record), ensure_ascii=False) + "\n")

    config = {
        "experiment_id": os.path.basename(output_root),
        "stage": EXPERIMENT_STAGE,
        "route": "A",
        "baseline_commit": "ea8ad97833eb5ceab291faae643c141a2b219749",
        "git_head_at_run": git_head,
        "git_dirty_at_run": git_dirty,
        "code_sha256": _code_sha(root),
        "physical_call_count": 0,
        "source_kind": syn.SOURCE_KIND,
        "evaluator": {
            "kind": "synthetic_analytic_truth",
            "families": list(syn.FAMILIES),
            "physical_validation_status": "NOT_APPLICABLE_SYNTHETIC",
        },
        "tasks": [_task_record(task) for task in tasks],
        "references": references,
        "matrix": {
            "smoke": {"budgets": [16, 32, 64, 128], "K": [0, 5], "rho": [0.0], "sources": [SOURCE_RANDOM, SOURCE_FOMAML_KSHOT]},
            "extension": {"budgets": [64], "K": [1, 3], "rho": [0.0, 0.25, 0.5, 0.75], "sources": [SOURCE_FOMAML_KSHOT]},
            "source_compare": {"budgets": [64], "K": [3], "rho": [0.0], "sources": [SOURCE_ZERO_SHOT, SOURCE_PRETRAIN]},
            "backends": list(BACKENDS),
            "seeds": [RUN_SEED],
            "note": "最小可复跑矩阵：覆盖全部 B 与 K∈{0,1,3,5}；rho 只作局部扩展；单 seed 冒烟，非全网格。",
        },
        "snapshots": {
            "build_seconds": snapshot_bundle["build_seconds"],
            "meta_tasks": snapshot_bundle["meta_tasks"],
            "meta_designs_per_task": snapshot_bundle["meta_designs_per_task"],
            "model_sha": {source: snapshot.model_sha for source, snapshot in snapshots.items()},
            "kinds": {source: snapshot.kind for source, snapshot in snapshots.items()},
        },
        "limits": [
            "单 seed（0），不足以做显著性检验；配对比较只报告方向性。",
            "代理可行性预测校准偏差较大（预测概率高估），本轮如实记录为负结果。",
            "所有真值均为合成解析函数，不得外推为真实气动/任务性能。",
        ],
    }
    with open(os.path.join(output_root, "experiment_config.json"), "w", encoding="utf-8") as handle:
        json.dump(_jsonable(config), handle, ensure_ascii=False, indent=2)

    with open(os.path.join(output_root, "README.md"), "w", encoding="utf-8") as handle:
        handle.write(_readme(records, cell_rows, paired, config))

    manifest = _manifest(output_root)
    with open(os.path.join(output_root, "data_manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    _write_sha256sums(output_root)

    print(
        "完成：%d runs，目录 %s（physical_call_count=0）" % (len(records), output_root),
        flush=True,
    )
    return {
        "output_root": output_root,
        "runs": len(records),
        "config": config,
        "cell_summary": cell_rows,
        "paired": paired,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "NOT_RUN"
    if isinstance(value, float):
        return "%.4f" % value
    return str(value)


def _readme(
    records: Sequence[Mapping[str, Any]],
    cell_rows: Sequence[Mapping[str, Any]],
    paired: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> str:
    lines: List[str] = []
    lines.append("# D-NEXT-001 路线A：优化器无关热启动合成实验")
    lines.append("")
    lines.append("- 阶段：%s（route A）" % config["stage"])
    lines.append("- 实验 ID：%s" % config["experiment_id"])
    lines.append(
        "- 基线 commit：%s；运行 HEAD：%s（dirty=%s）"
        % (config["baseline_commit"], config["git_head_at_run"], config["git_dirty_at_run"])
    )
    lines.append(
        "- **physical_call_count = 0**：全部真值来自合成解析函数，未启动 VSPAERO / SU2 / RCAIDE Mission / WaveDrag。"
    )
    lines.append("- evaluator：%s；来源：%s" % (config["evaluator"]["kind"], config["source_kind"]))
    lines.append(
        "- runs：%d；配对比较：%d 行；代码 SHA 见 experiment_config.json。"
        % (len(records), len(paired))
    )
    lines.append("")
    lines.append("## 矩阵")
    for name, spec in config["matrix"].items():
        if isinstance(spec, dict):
            lines.append(
                "- %s：B=%s，K=%s，rho=%s，来源=%s"
                % (name, spec["budgets"], spec["K"], spec["rho"], spec["sources"])
            )
    lines.append("")
    lines.append("## 参考解（scipy SLSQP 多起点，合成问题）")
    for task_id, reference in config["references"].items():
        lines.append(
            "- %s：status=%s，objective*=%s"
            % (task_id, reference.get("status"), _fmt(reference.get("objective_star")))
        )
    lines.append("")
    lines.append("## 关键负结果与风险（如实报告）")
    lines.append(
        "- 代理模型预测的可行性概率明显高于真实可行率：FOMAML/pretrain 提议点的真实可行数常为 0-1/8，"
        "而预测可行概率均值约 0.55-0.67。"
    )
    lines.append("- 单 seed、最小矩阵；first_feasible_eval 的下限受 K（支撑观测）与初始种群规模限制。")
    lines.append(
        "- 合成任务可行域阈值经调参（S-QC 可行率约 0.38，S-RB 约 0.15），调参过程记录在 receipt。"
    )
    lines.append("")
    lines.append("## 文件")
    lines.append("- metrics.csv：每个 run 的主指标与早期 anytime 指标。")
    lines.append("- paired_comparisons.csv：同任务、同预算、同 seed 的配对比较（treatment vs control）。")
    lines.append("- cell_summary.csv：按矩阵 cell 聚合的均值。")
    lines.append("- runs.jsonl：每个 run 的配置+指标（不含逐点 trace）。")
    lines.append("- runs/<run_id>/evaluations.jsonl：逐次真实评价 trace。")
    lines.append("- figures/*.png：中文图（matplotlib）。")
    lines.append("- data_manifest.json / SHA256SUMS.txt：完整性校验。")
    lines.append("")
    lines.append("## 度量口径")
    lines.append(
        "- first_feasible_eval：第几个真实评价首次得到可行解（1 起，含 K 个支撑观测与初始种群评价）。"
    )
    lines.append("- feasible_hit_rate：可行评价数 / 总预算 B。")
    lines.append("- gap_to_reference：(best_feasible - objective*) / max(|objective*|, 1e-9)。")
    lines.append("- anytime_best_feasible_*：预算截断到 8/16/32/64 时的最优可行目标值。")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
