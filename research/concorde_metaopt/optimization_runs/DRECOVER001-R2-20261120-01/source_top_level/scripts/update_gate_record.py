import json, hashlib
from pathlib import Path
root = Path("D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
p = root / "r2_gate_record.json"
d = json.loads(p.read_text(encoding="utf-8"))
d["generated_utc"] = "2026-11-20T07:50:00Z"
d["batch_id"] = "DRECOVER001-R2-20261120-01-B01R"
d["physical_solver_starts_actual"] = 24
d["admitted_certificates"] = 10
d["admitted_dataset_rows"] = 9
for cond in d["conditions"]:
    if cond["id"] == "C6_MAML_AFTER_ADMISSIONS":
        cond["status"] = "CLOSED"
        cond["evidence"] = ["real_dataset_manifest.json", "real_maml_result.json",
                            "docs/evidence/drecover001/real_maml_experiment_20261120.md"]
        cond["detail"] = ("Nine unique admitted rows (ten certificates; baseline-refine-01 duplicates M202 d00) used "
                          "for one K=1 FOMAML run (2 train tasks, 20 steps); val/test evaluated once each; "
                          "exploratory, no generalization claim; test not used for selection.")
d["maml_started"] = True
d["maml"] = json.loads((root / "real_maml_result.json").read_text(encoding="utf-8"))["run_id"]
d["maml_result"] = {
    "run_id": "DRECOVER001-MAML-20261120T074500Z",
    "status": "REAL_META_TRAINING_EXECUTED",
    "scope": "EXPLORATORY_REAL_K1_NINE_LABELS",
    "physical_solver_starts_actual": 0,
    "admitted_real_labels": 9,
    "training_steps": 20,
    "val_adapted_mse": 194471711.40892053,
    "val_zero_shot_mse": 172004200.8751603,
    "test_adapted_mse_once": 2495232593.693889,
    "test_zero_shot_mse_once": 3030527242.735841,
    "generalization_claimed": False,
    "test_used_for_selection": False,
    "result_sha256": hashlib.sha256((root / "real_maml_result.json").read_bytes()).hexdigest(),
}
d["matrix"].update({"successful_cases": 13, "interrupted_cases": 1,
                    "admitted_cases": 7,
                    "null_labels": 14})
d["next_step"] = ("No further starts under this authorization (24/24). Fix build_evaluation per-case q/Mach; "
                  "obtain independent review of the new real-training entry; a new authorization is required "
                  "for more tasks/designs or feedback-driven BO.")
d["evidence_sha256"]["batch_accounting.json"] = hashlib.sha256((root / "batch_accounting.json").read_bytes()).hexdigest()
d["evidence_sha256"]["real_dataset_manifest.json"] = hashlib.sha256((root / "real_dataset_manifest.json").read_bytes()).hexdigest()
d["evidence_sha256"]["real_maml_result.json"] = hashlib.sha256((root / "real_maml_result.json").read_bytes()).hexdigest()
p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(hashlib.sha256(p.read_bytes()).hexdigest())
