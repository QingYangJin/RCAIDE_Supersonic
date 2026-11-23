"""Write the Lead GO record for the P2 supplement batch (Issue #14 P2 directive).

Gate: A5 verdict must be P2_PROTOCOL_AND_CODE_REVIEW_PASS with dossier/prereg hashes equal to current files.
This GO authorizes only the frozen <=16-start supplement batch; it does not authorize P3.
"""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
DOSSIER = RUN / "p2_a5_dossier.md"
VERDICT = RUN / "a5_review" / "verdict.json"
PRE = RUN / "p2_preregistration.json"
PLAN = RUN / "p2_supplement_plan.json"
GO = RUN / "p2_go_record.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if v.get("verdict") != "P2_PROTOCOL_AND_CODE_REVIEW_PASS":
        raise SystemExit("A5 verdict not PASS: %r" % v.get("verdict"))
    if v.get("dossier_sha256") != sha(DOSSIER):
        raise SystemExit("A5 dossier sha mismatch; dossier changed after review")
    if v.get("preregistration_sha256") != sha(PRE):
        raise SystemExit("A5 prereg sha mismatch; prereg changed after review")
    script_map = {rel: RUN / "scripts" / Path(rel).name for rel in pre["source_code_sha256"]
                  if rel.startswith("scripts/p2_")}
    script_map.update({
                  "scripts/audit_real_case.py": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py"),
                  "scripts/admit_g1_case.py": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/scripts/admit_g1_case.py")})
    for rel, want in pre["source_code_sha256"].items():
        p = script_map.get(rel) or (REPO / rel)
        if not p.exists():
            raise SystemExit("code file missing: " + rel)
        if sha(p) != want:
            raise SystemExit("code sha drift: " + rel)
    if sha(PLAN) != pre["supplement_batch"]["plan_sha256"]:
        raise SystemExit("plan sha drift vs prereg")
    rec = {
        "schema": "dreal004.p2_go_record.v1",
        "go_issued": True,
        "go_issued_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_by": "Lead (agent), not a human approver and not the A5 reviewer",
        "owner_authorization_ref": "m10841 (新issue已发布，请执行) + Issue #14 comment 7103901506 P2 directive",
        "owner_authorization_interpretation": (
            "Owner's P2 directive says: use existing data first and supplement only the missing slots; "
            "if supplementing, freeze a small batch of <=16 real solver starts with internal-case caps, "
            "failure/timeout/stop conditions, charged to the P2 <=240 capacity, uploading/readback every <=8 starts. "
            "This GO authorizes exactly that 16-start supplement batch, nothing else."),
        "issue": "QingYangJin/RCAIDE_Supersonic#14",
        "run_id": pre["run_id"], "batch_id": pre["batch_id"],
        "authorization_id": pre["authorization_id"],
        "preregistration_sha256": sha(PRE),
        "preregistration_schema": pre["schema"],
        "plan_sha256": sha(PLAN),
        "a5_dossier_sha256": sha(DOSSIER),
        "a5_verdict_sha256": sha(VERDICT),
        "a5_verdict": v["verdict"],
        "a5_reviewer": v.get("reviewer"),
        "a5_human_signature": False,
        "caps": pre["supplement_batch"],
        "physical_starts_authorized_this_go": 16,
        "physical_starts_used_before_this_go": 0,
        "not_authorized": ["P3 online optimization", "additional starts beyond 16",
                           "retry of a failed/refused case", "reuse of query rows as support",
                           "any change to the frozen split or task family"],
    }
    GO.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("GO written:", GO, "sha256", sha(GO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
