
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
R=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
man=json.loads((R/"g1_case_manifest.json").read_text(encoding="utf-8"))
acc=json.loads((R/"batch_accounting.json").read_text(encoding="utf-8"))
am={"schema":"dreal003.g1_repair_amendment.v1","amendment_id":"G1-REPAIR-B02-20261121",
 "run_id":man["run_id"],"authorization_id":man["authorization_id"],"owner_message_ref":"m07992",
 "created_utc":datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
 "trigger":{"batch":"B01","physical_solver_starts":8,"successful_solver_runs":8,"admitted_labels":0,
            "failure":"8/8 CL_TARGET_OUTSIDE_POLAR; alpha grid overpredicted by 0.12-0.62 deg",
            "evidence":{"batch_accounting_sha256":sha(R/"batch_accounting.json"),
                        "failed_or_null_sha256":sha(R/"failed_or_null.csv"),
                        "all_evaluations_sha256":sha(R/"all_evaluations.csv")}},
 "root_cause":"single global alpha slope/base CL reused across Mach; actual slopes are Mach-dependent",
 "correction":{"base_alpha_by_mach":{"1.6":[7.4658,0.2896827658750951,0.03655],"1.8":[6.1846,0.22888514834575416,0.03579],"2.02":[5.18125,0.181741590896,0.03439427],"2.4":[4.44,0.128809590323,0.034]},
               "formula":"alpha_center=base_alpha+(cl_target-base_cl)/slope",
               "calibrated_from":"B01 measured polars for M160/M180 and pre-A1 admitted cases for M202/M240; design deltas use local slope"},
 "scope":{"batch_id":"DRECOVER001-G1-20261121-01-B02","rebuilt_unstarted_cases":16,
          "started_cases_not_rerun":8,"max_starts_this_batch":16,"max_starts_total_g1":24,
          "already_consumed":8,"remaining":16,"parallel":1,"retries":0,"case_timeout_s":1200,
          "not_authorized":["G2","G3","R2","rerun of B01 cases"]},
 "accounting_effect":{"planned_starts":24,"consumed_B01":8,"remaining_B02":16,
                      "expected_valid_if_all_succeed":16,"aggregate_valid_rate_if_all_succeed":16/24,
                      "disclosure":"16/24 = 0.667 < 0.70 G1 target; B01 nulls cannot be erased; G1 cannot claim label-rate pass"},
 "references":{"original_preregistration_sha256":man["preregistration_sha256"],
               "repaired_case_manifest_sha256":sha(R/"g1_case_manifest.json"),
               "b01_a5_verdict_sha256":sha(R/"a5_review/verdict.json")},
 "status":"AMENDMENT_PENDING_A5_AND_GO"}
p=R/"g1_repair_amendment.json"; p.write_text(json.dumps(am,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps({"amendment":str(p),"sha256":sha(p)},indent=2))
