
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
pre=RUN/"g1_preregistration.json"; man=RUN/"g1_case_manifest.json"
ver=RUN/"a5_review/verdict.json"; v=json.loads(ver.read_text(encoding="utf-8"))
if v.get("verdict")!="G1_APPROVE": raise SystemExit("not approved")
go={"schema":"dreal003.g1_go_record.v1","go_id":"GO-DREAL003-G1-20261121-01-B01",
 "run_id":"DRECOVER001-G1-20261121-01","batch_id":"DRECOVER001-G1-20261121-01-B01",
 "authorization_id":"AUTH-DREAL003-G1-20261121-01","owner_message_ref":"m07992",
 "owner_text":"继续执行，把G1阶段也完成，批准实际物理计算",
 "issued_utc":now(),"issued_by":"lead","status":"GO_ISSUED_FOR_MINI_BATCH_01",
 "scope":{"max_starts_this_batch":8,"max_starts_total_g1":24,"parallel":1,"retries":0,
          "case_timeout_s":1200,"not_authorized":["G2","G3","R2","additional retries","parallel > 1"]},
 "references":{"preregistration_sha256":sha(pre),"case_manifest_sha256":sha(man),
               "a5_verdict_sha256":sha(ver),"a5_dossier_sha256":v.get("dossier_sha256"),
               "a5_reviewed_utc":v.get("reviewed_utc")},
 "conditions":["Run at most 8 starts, one case at a time.","No retry; failed case objective=null.",
   "Stop on refused/exception/two consecutive non-SOLVED/ledger or upload mismatch.",
   "After this batch, compute valid label rate; if <0.70, do not start another mini-batch without new A5 review and Lead GO.",
   "Upload raw files/CSV/PNG/ledger and read back SHA256SUMS before any further mini-batch.",
   "No G2/G3/R2 and no human-signature claim."],
 "a5_minor_findings_disposition":{
   "dossier_sha":"Harness records compact dossier sha256 0ed4a2410357a34c6ff7620d42eca269034f496be1e89cc03e9f47e8b4b0fa79 and verdict field is bound to it.",
   "prereg_status":"Preregistration remains immutable at PRE_REGISTERED_PENDING_A5_AND_GO; this GO record is the separate GO.",
   "code_asserted":"Full dossier docs/evidence/dreal003/g1/g1_a5_dossier.md contains A1 diff and test log reference; compact dossier discloses it as asserted.",
   "label_rate":"Added as post-batch gate in conditions; no further batch below 0.70 without new review."},
 "physical_solver_starts_before_go":0}
(RUN/"g1_go_record.json").write_text(json.dumps(go,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print(json.dumps({"go":str(RUN/"g1_go_record.json"),"sha256":sha(RUN/"g1_go_record.json"),"status":go["status"]},indent=2))
