#!/usr/bin/env python3
"""Lead signer for D-REAL-001 P2a-v2 R2 approval (lead-only).

approval.DRAFT.json -> approval.json following A5 G-P2AV2R2-PRE
signature_requirements. Fail-closed: all package/executor/replay SHAs and the
A5 gate itself are verified first; if anything fails no approval is written.

Allowed deltas vs DRAFT (exactly A5's scalar list):
  approved, approved_by, approved_at_utc, status, authorization,
  window.status, conditions (52), approval_refs (A5 final), b2_waiver{status,
  approved_at_utc, a5_pre_review_commit}. Everything else stays identical.

Usage:
  python sign_approval_r2.py --draft <run>/approval.DRAFT.json --run-dir <run> \
      --gate-json <a5 gate json> --gate-commit <sha> --evidence-out <path>
"""
import argparse, hashlib, json, os, sys
from datetime import datetime, timezone

ALLOWED_TOP = {"approved", "approved_by", "approved_at_utc", "status", "authorization",
               "window", "conditions", "approval_refs", "b2_waiver"}
ALLOWED_WINDOW = {"status"}
ALLOWED_B2 = {"status", "approved_at_utc", "a5_pre_review_commit"}

def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--gate-json", required=True)
    ap.add_argument("--gate-commit", required=True)
    ap.add_argument("--evidence-out", default=None)
    args = ap.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    draft = json.load(open(args.draft, encoding="utf-8"))
    gate = json.load(open(args.gate_json, encoding="utf-8-sig"))
    checks = []
    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": "" if ok else str(detail)})
        print(("OK   " if ok else "FAIL ") + name + ("" if ok else " :: " + str(detail)))
        return ok
    ok = True

    # ---- A5 gate ----
    ok &= check("gate_verdict_pass", str(gate.get("verdict", "")).startswith("PASS"), gate.get("verdict"))
    ok &= check("gate_zero_physical", gate.get("physical_call_count") == 0 and gate.get("solver_started") is False,
                [gate.get("physical_call_count"), gate.get("solver_started")])
    sr = gate.get("signature_requirements") or {}
    conds = gate.get("signature_conditions_recommended") or []
    ok &= check("gate_conditions_52", isinstance(conds, list) and len(conds) == 52 and all(isinstance(c, str) and c for c in conds), len(conds))
    srefs = dict((sr.get("approval_refs_final") or {}))
    srefs["a5_review"] = args.gate_commit
    ok &= check("gate_refs_complete", all(isinstance(v, str) and v and "TO_BE_FILLED" not in v for v in srefs.values()), srefs)
    for need in ("a1_bundle_commit", "a1_bundle_manifest_sha256", "a2_package_commit", "a2_execution_code"):
        ok &= check("gate_refs_has_" + need, need in srefs, list(srefs))

    # ---- package files in run dir ----
    for fname, expect in {
        "plan.json": draft["plan_sha256"],
        "P2A_V2_PREREGISTRATION.md": draft["prereg_sha256"],
        "identity_binding.json": draft["identity_binding_file_sha256"],
        "initial_designs_manifest.json": draft["initial_designs_manifest_sha256"],
    }.items():
        p = os.path.join(run_dir, fname)
        ok &= check("file_exists:" + fname, os.path.isfile(p), p)
        if os.path.isfile(p):
            actual = sha256_file(p)
            ok &= check("file_sha:" + fname, actual == expect, "expected=" + expect + " actual=" + actual)

    # ---- A2 executor blob ----
    executor_sha = None
    for ent in draft.get("executor_blob", {}).get("a2", []):
        p = ent["path"]; name = os.path.basename(p)
        ok &= check("executor_exists:" + name, os.path.isfile(p), p)
        if os.path.isfile(p):
            actual = sha256_file(p)
            ok &= check("executor_sha:" + name, actual == ent["sha256"], "expected=" + ent["sha256"] + " actual=" + actual)
            if name == "p2a_v2_executor.py":
                executor_sha = actual
    ok &= check("a2_executor_sha_matches", executor_sha == draft.get("a2_executor_sha256"), [executor_sha, draft.get("a2_executor_sha256")])

    # ---- A1 replay bundle manifest ----
    rb = draft.get("replay_bundles") or {}
    rbp = rb.get("bundle_manifest_path", "")
    ok &= check("replay_bundle_exists", os.path.isfile(rbp), rbp)
    if os.path.isfile(rbp):
        actual = sha256_file(rbp)
        ok &= check("replay_bundle_sha", actual == rb.get("bundle_manifest_sha256"), [rb.get("bundle_manifest_sha256"), actual])
    ok &= check("replay_bundle_cases_2", sorted((rb.get("cases") or {}).keys()) == ["PRE-01", "PRE-02"], sorted((rb.get("cases") or {}).keys()))

    # ---- window / caps / pre-exec ----
    ok &= check("window_token_same", draft.get("token") == (draft.get("window") or {}).get("token"), draft.get("token"))
    ok &= check("window_end_1200", (draft.get("window") or {}).get("end_utc") == "2026-11-11T12:00:00Z", (draft.get("window") or {}).get("end_utc"))
    ok &= check("planned_starts", draft.get("planned_starts") == 386, draft.get("planned_starts"))
    ok &= check("max_starts", draft.get("max_starts") == 451, draft.get("max_starts"))
    ok &= check("planned_internal", draft.get("planned_internal_cases") == 2702, draft.get("planned_internal_cases"))
    ok &= check("max_internal", draft.get("max_internal_cases") == 3157, draft.get("max_internal_cases"))
    ok &= check("reserve_starts", draft.get("reserve_starts") == 64, draft.get("reserve_starts"))
    ok &= check("draft_not_approved", draft.get("approved") is False and draft.get("status") == "DRAFT_AWAITING_LEAD_SIGNATURE",
                [draft.get("approved"), draft.get("status")])
    ok &= check("draft_zero_physical", (draft.get("physical_call_count"), draft.get("physical_solver_starts"),
                                        draft.get("solver_started")) == (0, 0, False),
                [draft.get("physical_call_count"), draft.get("physical_solver_starts"), draft.get("solver_started")])
    for bad in ("solver_attempts.jsonl", "cases", "evaluations", "batch_summary.json", "stop_report.json", "approval.json"):
        ok &= check("pre_exec_absent:" + bad, not os.path.exists(os.path.join(run_dir, bad)), os.path.join(run_dir, bad))
    ok &= check("draft_conditions_15", len(draft.get("conditions") or []) == 15, len(draft.get("conditions") or []))

    if not ok:
        print("SIGN_ABORTED: preconditions failed; approval.json NOT written")
        return 1

    # ---- build signed approval ----
    now = utcnow()
    appr = json.loads(json.dumps(draft))
    sd = sr.get("scalar_deltas") or {}
    appr["approved"] = True
    appr["approved_by"] = "lead"
    appr["approved_at_utc"] = now
    appr["status"] = "APPROVED_FOR_EXECUTION_PENDING_POST_APPROVAL_DRY_RUN"
    auth = dict(sd.get("authorization") or {})
    appr["authorization"] = {
        "mode": "LEAD_SINGLE_BATCH_APPROVAL",
        "scope": str(auth.get("scope")),
        "signed_at_utc": now,
        "signed_by": "lead",
    }
    appr["window"]["status"] = "APPROVED"
    appr["conditions"] = list(conds)
    appr["approval_refs"] = srefs
    bw = appr.setdefault("b2_waiver", {})
    bw["status"] = "APPROVED_BY_LEAD_FOR_THIS_BATCH_ONLY"
    bw["approved_at_utc"] = now
    bw["a5_pre_review_commit"] = args.gate_commit

    # ---- assert only allowed deltas ----
    def diff(a, b):
        return {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    dtop = diff(draft, appr)
    ok &= check("delta_top_allowed", dtop <= ALLOWED_TOP, sorted(dtop - ALLOWED_TOP))
    dwin = diff(draft.get("window") or {}, appr.get("window") or {})
    ok &= check("delta_window_allowed", dwin <= ALLOWED_WINDOW, sorted(dwin - ALLOWED_WINDOW))
    db2 = diff(draft.get("b2_waiver") or {}, appr.get("b2_waiver") or {})
    ok &= check("delta_b2_allowed", db2 <= ALLOWED_B2, sorted(db2 - ALLOWED_B2))
    # A5's declared invariants must be value-identical
    bad_inv = []
    for name in sr.get("signed_approval_invariants_unchanged") or []:
        if draft.get(name) != appr.get(name):
            bad_inv.append(name)
    ok &= check("a5_invariants_unchanged", not bad_inv, bad_inv)
    if not ok:
        print("SIGN_ABORTED: delta/invariant checks failed; approval.json NOT written")
        return 1

    out = os.path.join(run_dir, "approval.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(appr, ensure_ascii=False, indent=2) + "\n")
    appr_sha = sha256_file(out)
    appr_bytes = os.path.getsize(out)

    # ---- post-write validation ----
    rt = json.load(open(out, encoding="utf-8"))
    valid = True
    valid &= check("post_approved", rt.get("approved") is True)
    valid &= check("post_status", rt.get("status") == "APPROVED_FOR_EXECUTION_PENDING_POST_APPROVAL_DRY_RUN", rt.get("status"))
    valid &= check("post_window_status", (rt.get("window") or {}).get("status") == "APPROVED", (rt.get("window") or {}).get("status"))
    valid &= check("post_token_same", rt.get("token") == (rt.get("window") or {}).get("token") == "WINDOW_OK-P2AV2R2-20261111T0600Z-1200Z", rt.get("token"))
    valid &= check("post_conditions_52", len(rt.get("conditions") or []) == 52, len(rt.get("conditions") or []))
    valid &= check("post_refs_a5", (rt.get("approval_refs") or {}).get("a5_review") == args.gate_commit, (rt.get("approval_refs") or {}).get("a5_review"))
    valid &= check("post_refs_bundle", (rt.get("approval_refs") or {}).get("a1_bundle_manifest_sha256") == "995bb12fff738d3ebb0bde08c0d5c5bfeb9532aebe536847ef307a2332013aa5",
                   (rt.get("approval_refs") or {}).get("a1_bundle_manifest_sha256"))
    valid &= check("post_b2_waiver", (rt.get("b2_waiver") or {}).get("a5_pre_review_commit") == args.gate_commit, (rt.get("b2_waiver") or {}).get("a5_pre_review_commit"))
    print("POST_WRITE_VALIDATION:", "PASS" if valid else "FAIL")
    print("APPROVAL_PATH:", out)
    print("APPROVAL_SHA256:", appr_sha)
    print("APPROVAL_BYTES:", appr_bytes)
    print("CONDITIONS:", len(rt.get("conditions") or []))

    ev = {
        "schema": "dreal001.lead_signature_receipt.v1",
        "batch_id": draft["batch_id"],
        "run_id": draft["run_id"],
        "signed_by": "lead",
        "signed_at_utc": now,
        "approval_path": out,
        "approval_sha256": appr_sha,
        "approval_bytes": appr_bytes,
        "draft_path": os.path.abspath(args.draft),
        "draft_sha256": sha256_file(args.draft),
        "a5_gate_id": gate.get("gate_id"),
        "a5_gate_path": os.path.abspath(args.gate_json),
        "a5_gate_sha256": sha256_file(args.gate_json),
        "a5_gate_commit": args.gate_commit,
        "conditions_count": len(rt.get("conditions") or []),
        "approval_refs": rt.get("approval_refs"),
        "physical_call_count_at_sign": 0,
        "checks": checks,
    }
    ev_path = args.evidence_out or os.path.join(
        "D:\\RCAIDE\\dnext001\\wt-real-lead\\docs\\evidence\\dreal001",
        "lead_signature_r2_" + now.replace(":", "").replace("-", "") + ".json")
    os.makedirs(os.path.dirname(os.path.abspath(ev_path)), exist_ok=True)
    with open(ev_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(ev, ensure_ascii=False, indent=2) + "\n")
    print("EVIDENCE_PATH:", os.path.abspath(ev_path))
    print("EVIDENCE_SHA256:", sha256_file(ev_path))
    print("SIGN_OK" if valid else "SIGN_POST_VALIDATION_FAILED")
    return 0 if valid else 1

if __name__ == "__main__":
    sys.exit(main())
