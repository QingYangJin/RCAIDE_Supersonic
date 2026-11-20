import json, hashlib
from pathlib import Path
root = Path("D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
acc_path = root / "batch_accounting.json"
acc = json.loads(acc_path.read_text(encoding="utf-8"))
ds = json.loads((root / "real_dataset_manifest.json").read_text(encoding="utf-8"))
maml = json.loads((root / "real_maml_result.json").read_text(encoding="utf-8"))
by_id = {row["admission_id"]: row for row in ds["rows"]}
acc["batch_id"] = "DRECOVER001-R2-20261120-01-B01R"
acc["prior_batch_id"] = "DRECOVER001-R2-20261120-01-B01"
acc["physical_solver_starts_actual"] = 24
acc["physical_solver_starts_completed"] = 23
acc["remaining_starts"] = 0
acc["internal_solver_cases_actual_completed"] = 23 + 13 * 15 + 7 * 61
acc["internal_solver_cases_note"] = ("pilot 23 (baseline coarse 7 + refine 13 + admit 3) + 13 completed matrix cases x 15 "
                                     "+ 7 B01R repair cases x 61; interrupted m240-d01 internal cases unknown and not counted")
existing = {item["admission_id"] for item in acc["admitted_labels"]}
for admission_id, row in by_id.items():
    if admission_id in existing:
        continue
    manifest = json.loads((root / "cases" / row["case_id"] / "admission_manifest.json").read_text(encoding="utf-8"))
    acc["admitted_labels"].append({
        "case_id": row["case_id"], "task_id": row["task_id"],
        "design": manifest["design"],
        "design_sha256": row["design_sha256"], "partition": row["partition"],
        "admission_id": admission_id, "di_n": row["di_n"], "cl": row["cl"],
        "cdi": row["cdi"], "alpha_deg": row["alpha_deg"], "raw_sha256": row["raw_sha256"],
        "evidence_scope": "LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED",
    })
acc["admitted_total_certificates"] = len(acc["admitted_labels"])
acc["admitted_dataset_usable_rows"] = len(ds["rows"])
acc["admitted_dataset_note"] = ("10 certificates; baseline-refine-01 repeats M202 d00 and is excluded from the 9-row "
                                "MetaDataset to avoid duplicate design identity")
acc["dataset_sha256"] = maml["dataset_sha256"]
for row in ds["rows"]:
    cid = row["case_id"]
    if cid == "m202-baseline-admit":
        continue
    case_dir = root / "cases" / cid
    cr = case_dir / "case_result.json"
    if not cr.is_file():
        continue
    attempt = json.loads(cr.read_text(encoding="utf-8"))["attempt"]
    if cid in {item["case_id"] for item in acc["starts"]}:
        continue
    acc["starts"].append({"case_id": cid, "start_events": 1, "end_events": 1,
                          "attempt_ids": [attempt["attempt_id"]],
                          "start_ts_utc": [attempt["start_ts_utc"]]})
acc["starts"].sort(key=lambda item: item["start_ts_utc"][0])
acc["maml"] = {
    "run_id": maml["run_id"], "batch_id": maml["batch_id"],
    "status": maml["status"], "scope": maml["scope"],
    "admitted_real_labels": maml["admitted_real_labels"],
    "physical_solver_starts_actual": maml["physical_solver_starts_actual"],
    "config": maml["config"], "training_steps": maml["training"]["steps"],
    "dataset_sha256": maml["dataset_sha256"],
    "final_parameters_sha256": maml["final_parameters_sha256"],
    "val_adapted_mse": maml["val_adapted"]["mse"],
    "val_zero_shot_mse": maml["val_zero_shot"]["mse"],
    "test_adapted_mse_once": maml["test_adapted_once"]["mse"],
    "test_zero_shot_mse_once": maml["test_zero_shot_once"]["mse"],
    "generalization_claimed": False, "test_used_for_selection": False,
    "result_file": str(root / "real_maml_result.json"),
    "result_sha256": hashlib.sha256((root / "real_maml_result.json").read_bytes()).hexdigest(),
}
acc_path.write_text(json.dumps(acc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(json.dumps({"accounting_sha": hashlib.sha256(acc_path.read_bytes()).hexdigest(),
                  "starts": acc["physical_solver_starts_actual"], "completed": acc["physical_solver_starts_completed"],
                  "internal": acc["internal_solver_cases_actual_completed"],
                  "certs": acc["admitted_total_certificates"], "usable": acc["admitted_dataset_usable_rows"],
                  "maml_result_sha": acc["maml"]["result_sha256"]}, indent=2))
