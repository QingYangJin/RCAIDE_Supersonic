
"""Write the Lead GO record for the P1 mini-batch, binding A5 verdict, dossier and preregistration hashes.

Gate: A5 verdict must be P1_PROTOCOL_AND_CODE_REVIEW_PASS and its dossier_sha256 must equal the current dossier.
The GO is the Lead's own record; it is not an A5 signature and it authorizes only this <=12-start P1 batch.
"""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P1-20261122-02")
DOSSIER = RUN / "p1_a5_dossier.md"
VERDICT = RUN / "a5_review" / "verdict.json"
PRE = RUN / "p1_preregistration.json"
GO = RUN / "p1_go_record.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    pre = json.loads(PRE.read_text(encoding="utf-8"))
    v = json.loads(VERDICT.read_text(encoding="utf-8"))
    if v.get("verdict") != "P1_PROTOCOL_AND_CODE_REVIEW_PASS":
        raise SystemExit("A5 verdict not PASS: %r" % v.get("verdict"))
    if v.get("dossier_sha256") != sha(DOSSIER):
        raise SystemExit("A5 dossier sha mismatch; dossier changed after review")
    if v.get("preregistration_sha256") != sha(PRE):
        raise SystemExit("A5 prereg sha mismatch; prereg changed after review")
    script_map = {"scripts/p1_run.py": RUN / "scripts" / "p1_run.py",
                  "scripts/audit_real_case.py": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py"),
                  "scripts/admit_g1_case.py": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/scripts/admit_g1_case.py")}
    for rel, want in pre["code_shas"].items():
        p = script_map.get(rel) or (Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122") / rel)
        if not p.exists():
            raise SystemExit("code file missing: " + rel)
        if sha(p) != want:
            raise SystemExit("code sha drift: " + rel)
    rec = {
        "schema": "dreal004.p1_go_record.v1",
        "go_issued": True,
        "go_issued_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "issued_by": "Lead (agent), not a human approver and not the A5 reviewer",
        "owner_authorization_ref": "m10191 批准真实评估",
        "owner_authorization_interpretation": "Owner approved the P1 real evaluation described in the Issue #14 body, bounded by the frozen P1 preregistration: <=12 real solver starts, 3 per design, 3 alpha probes per start, <=36 internal cases, tolerance 1e-3 not relaxed, no retries, parallelism 1, upload/readback every <=4 starts.",
        "issue": "QingYangJin/RCAIDE_Supersonic#14",
        "run_id": pre["run_id"],
        "batch_id": pre["batch_id"],
        "authorization_id": pre["authorization_id"],
        "preregistration_sha256": sha(PRE),
        "a5_dossier_sha256": sha(DOSSIER),
        "a5_verdict_sha256": sha(VERDICT),
        "a5_verdict": v["verdict"],
        "a5_reviewer": v.get("reviewer"),
        "a5_human_signature": False,
        "caps": pre["caps"],
        "not_authorized": pre["not_authorized"],
        "physical_starts_authorized_this_go": 12,
        "physical_starts_used_before_this_go": 0,
    }
    GO.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("GO written:", GO, "sha256", sha(GO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
