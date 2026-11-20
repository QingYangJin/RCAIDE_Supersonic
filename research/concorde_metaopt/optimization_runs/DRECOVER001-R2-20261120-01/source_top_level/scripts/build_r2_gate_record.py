import json, hashlib
from pathlib import Path
from datetime import datetime, timezone
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
def load(name): return json.loads((RUN/name).read_text(encoding="utf-8"))
def sha(name): return hashlib.sha256((RUN/name).read_bytes()).hexdigest()
freeze=load("r2_code_freeze.json"); pilot=load("pilot_ledger.json"); labels=load("pilot_label_status.json")
matrix=load("matrix_input_verification.json"); flow=load("flow_default_equivalence/verification.json")
pre=load("preflight_r2/recovery_preflight_receipt.json")
verdict=json.loads(Path(r"D:/RCAIDE/.recovery-local-restore/a5_reviewer/run_r2_20261120/verdict.json").read_text(encoding="utf-8"))
successful=[c for c in labels["cases"] if c["solver_status"]=="SOLVED"]
admitted=[c for c in labels["cases"] if c["label_status"]=="ADMITTED"]
conditions=[
 {"id":"C1_PILOT_EXCEPTION","status":"CLOSED","evidence":["pilot_ledger.json","r2_a5_review_dossier_20261120.md"],
  "detail":"3 pilot starts charged; A5 verdict CHANGES_REQUIRED with pilot RATIFIED_WITH_CONDITIONS recorded; no further starts until closure review."},
 {"id":"C2_CODE_FREEZE_AND_FULL_PREFLIGHT","status":"CLOSED","evidence":["r2_code_freeze.json","preflight_r2/recovery_preflight_receipt.json"],
  "detail":"freeze_id %s binds 19 files; pushed remote commit %s (parent %s); full preflight %s ran 248 tests, 0 failures/errors/skipped, PASS. Targeted pytest PermissionError was a sandbox temp ACL issue; preflight unittest path passed; --basetemp workaround documented." % (freeze["freeze_id"],freeze["remote_commit"],freeze["remote_parent"],pre["run_id"])},
 {"id":"C3_EW_INF_SCOPE","status":"CLOSED","evidence":["research/concorde_metaopt/dreal001/meta/raw_verification.py:144-160","research/concorde_metaopt/tests/test_recovery_real_admission.py:214"],
  "detail":"Only Ew with math.isinf is removed from nonfinite; Ew NaN and every other nonfinite payload still raise ContractError. Regression test test_infinite_ew_diagnostic_tolerated_but_nan_or_core_inf_fatal; 18 admission tests passed."},
 {"id":"C4_FLOW_CONDITIONS","status":"CLOSED","evidence":["flow_default_equivalence/verification.json","matrix_input_verification.json"],
  "detail":"Default vs explicit baseline flow: same vspgeom SHA and same deck Sref/Mach/AoA/ReCref/Vinf/Rho; verdict %s. 14 matrix decks, 168 checks, 0 failures; q/CL recomputed from deck Rho/Vinf." % flow["verdict"]},
 {"id":"C5_PILOT_ADMISSIONS","status":"CLOSED","evidence":["pilot_label_status.json","cases/baseline-admit-01/admission_certificate.json","cases/baseline-refine-01/admission_certificate.json"],
  "detail":"%d/%d successful pilot cases have admission certificates; baseline-coarse remains NULL_LABEL (POLAR_HAS_INVALID_ROWS). All certificates are LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED." % (len(admitted),len(successful))},
 {"id":"C6_MAML_AFTER_ADMISSIONS","status":"PENDING","evidence":["pilot_label_status.json"],
  "detail":"MAML has not started. Matrix labels must be admitted case-by-case; failed cases stay null; results labeled exploratory with no generalization claim; same-machine backup limitation disclosed."},
]
record={"schema":"drecover001.r2_gate_record.v1",
 "generated_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
 "authorization_id":pilot["authorization_id"],"run_id":pilot["run_id"],"batch_id":pilot["batch_id"],
 "owner_message_ref":pilot["owner_message_ref"],
 "a5":{"verdict":verdict["verdict"],"pilot_disposition":verdict["pilot_disposition"],
       "model":verdict["model"],"reviewed_utc":verdict["reviewed_utc"],
       "dossier_sha256":verdict["dossier_sha256"],"tool_access":verdict["tool_access"],
       "human_signature":False,"note":"A5 is a deepseek-flash independent-context reviewer, not a human signer."},
 "code_freeze":{"freeze_id":freeze["freeze_id"],"git_head":freeze["git_head"],"remote_commit":freeze["remote_commit"],
                "remote_tree":freeze["remote_tree"],"remote_parent":freeze["remote_parent"],
                "dirty_paths":freeze["dirty_paths"],"file_count":freeze["file_count"]},
 "preflight":{"run_id":pre["run_id"],"tests_run":pre["tests_run"],"failures":pre["failures"],
              "errors":pre["errors"],"skipped":pre["skipped"],"status":pre["software_tests_status"],
              "physical_solver_starts_actual":0,"real_meta_training_executed":False},
 "pilot":{"physical_solver_starts_actual":pilot["pilot"]["physical_solver_starts_actual"],
          "internal_solver_cases_actual":pilot["pilot"]["internal_solver_cases_actual"],
          "remaining_starts":pilot["pilot"]["remaining_starts"],
          "successful_cases":len(successful),"admitted_cases":len(admitted),
          "null_label_cases":[c["case_id"] for c in labels["cases"] if c["label_status"]!="ADMITTED"]},
 "matrix":{"case_count":matrix["case_count"],"checks":matrix["check_count"],"failures":matrix["failure_count"]},
 "conditions":conditions,
 "further_starts_blocked_until_a5_closure_review":True,
 "maml_started":False,
 "evidence_sha256":{name:sha(name) for name in ("pilot_ledger.json","pilot_label_status.json","matrix_input_verification.json","flow_default_equivalence/verification.json","r2_code_freeze.json","preflight_r2/recovery_preflight_receipt.json")}}
(RUN/"r2_gate_record.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
print(json.dumps(record,indent=2)[:4000])
