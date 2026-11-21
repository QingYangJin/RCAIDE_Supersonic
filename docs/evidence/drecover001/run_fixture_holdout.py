"""Restored fixture models -> held-out support adaptation. Not real-task evidence."""
from pathlib import Path
import hashlib
import json
import sys
from dataclasses import replace
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.concorde_metaopt.tests.test_recovery_meta_contracts import fixture
from research.concorde_metaopt.dreal001.meta.checkpoint import restore_fixture_checkpoint
from research.concorde_metaopt.dreal001.meta.production import AdaptationRunner, WarmStartSampler
from research.concorde_metaopt.meta_learning import maml


def main():
    out = Path(__file__).resolve().parent
    receipt = json.loads((out / "recovery_preflight_receipt.json").read_text())
    if receipt["training_status"] != "SOFTWARE_FIXTURE_TRAINING_ONLY":
        raise RuntimeError("requires executed fixture training receipt")
    blob = (out / "synthetic_software_checkpoint.json").read_bytes()
    dataset = fixture()
    restored = restore_fixture_checkpoint(blob, expected_sha256=receipt["synthetic_checkpoint_sha256"], dataset=dataset)
    runner = AdaptationRunner()
    rows = []
    for task in dataset.tasks:
        if task.split == "train":
            continue
        support, query = dataset.usable(task.task_id, "support"), dataset.usable(task.task_id, "query")
        query_x = np.asarray([r.design for r in query])
        # Query labels are used below only for scoring, never given to predict.
        target = np.asarray([r.di_n for r in query])
        for name, params in restored.models.items():
            before = params.to_dict()
            predictions = {}
            for k in (0, 4):
                predicted = runner.predict(params, config=restored.config, normalizer=restored.normalizer,
                                           support_rows=support[:k], query_designs=query_x)
                repeated = runner.predict(params, config=restored.config, normalizer=restored.normalizer,
                                          support_rows=support[:k], query_designs=query_x)
                np.testing.assert_array_equal(predicted, repeated)
                predictions[k] = predicted
                rows.append({"task_id": task.task_id, "split": task.split, "model": name, "k": k,
                             "support_ids": [r.observation_id for r in support[:k]],
                             "query_ids": [r.observation_id for r in query],
                             "prediction": predicted.tolist(), "target_for_scoring_only": target.tolist(),
                             "query_mse": float(np.mean((predicted - target) ** 2)),
                             "repeat_exact": True})
            changed = tuple(replace(r, di_n=r.di_n + 10.) for r in support)
            changed_pred = runner.predict(params, config=restored.config, normalizer=restored.normalizer,
                                          support_rows=changed, query_designs=query_x)
            if np.array_equal(changed_pred, predictions[4]):
                raise RuntimeError("support response did not affect adapted prediction")
            if params.to_dict() != before:
                raise RuntimeError("adaptation mutated base checkpoint")
            # Numeric reference through a separate direct support-only inner_adapt call.
            sx, sy = restored.normalizer.arrays(support)
            episode = maml.TaskEpisode(sx, sy, sx[:1], np.zeros((1, 1)), "direct_support_reference")
            adapted, history = maml.inner_adapt(params, episode, restored.config)
            direct = runner.predict(adapted, config=restored.config, normalizer=restored.normalizer,
                                    support_rows=(), query_designs=query_x)
            np.testing.assert_array_equal(direct, predictions[4])
            selected = WarmStartSampler().select(query_x, predictions[4], 2,
                                                evaluated_designs=np.asarray([r.design for r in support]))
            if selected.shape != (2, 12) or len(history) != restored.config.inner_steps:
                raise RuntimeError("invalid adaptation or sampler shape")
    result = {"scope": "SOFTWARE_FIXTURE_HOLDOUT_ONLY", "real_meta_training_executed": False,
              "physical_solver_starts_actual": 0, "checkpoint_sha256": hashlib.sha256(blob).hexdigest(),
              "train_task_ids": [t.task_id for t in dataset.tasks if t.split == "train"],
              "query_labels_used_for_adaptation": False, "base_parameters_unchanged": True,
              "support_response_perturbation_changes_predictions": True,
              "direct_inner_adapt_equivalence": "EXACT", "software_candidate_selection": "PASS_NO_PHYSICS",
              "model_selection_on_heldout": False, "fixture_limit": "one seed; four deterministic query rows per heldout task; not a real MAML efficacy comparison",
              "results": rows}
    result["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (out / "synthetic_fixture_holdout.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "results"}, indent=2))
    print(json.dumps([{k: r[k] for k in ("task_id", "model", "k", "query_mse")} for r in rows], indent=2))


if __name__ == "__main__":
    main()
