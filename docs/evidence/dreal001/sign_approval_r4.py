#!/usr/bin/env python3
"""Lead signer for D-REAL-001 P2a-v2 R3 approval (lead-only).

approval.DRAFT.json -> approval.json after A5 G-P2AV2R3-PRE recommendations.
Fail-closed: verifies the A5 gate, the A2 package commit blobs, executor blob,
replay bundle manifest, window/token, caps, cumulative accounting, R3 addendum,
supersedes-R2 binding and pre-execution emptiness BEFORE writing approval.json.
"""
import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone

EXPECTED = {
    "batch_id": "DREAL001-P2-20261111-09",
    "run_id": "DREAL001-P2A2R4-20261111-01",
    "window_start": "2026-11-11T09:00:00Z",
    "window_end": "2026-11-11T12:00:00Z",
    "token": "WINDOW_OK-P2AV2R4-20261111T0900Z-1200Z",
    "planned_starts": 386,
    "max_starts": 451,
    "planned_internal": 2702,
    "max_internal": 3157,
    "reserve_starts": 64,
    "cumulative_starts": 431,
    "cumulative_internal": 3029,
    "prior_starts": 39,
    "prior_internal": 285,
    "r1_starts": 2,
    "r1_internal": 14,
    "r2_starts": 2,
    "r2_internal": 14,
    "r3_starts": 2,
    "r3_internal": 14,
    "supersedes_sha": "18865f8f4e8206135f1673e5f8706bd201465bc617473c604b262ba440dd7f60",
    "supersedes_bytes": 52695,
    "supersedes_physical": 6,
    "bundle_sha": "995bb12fff738d3ebb0bde08c0d5c5bfeb9532aebe536847ef307a2332013aa5",
    "bundle_commit_full": "2a57632b3f7d5d567556d9774913ec40a5d72272",
    "bare_sha256": "db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad",
}
ALLOWED_TOP = {"approved", "approved_by", "approved_at_utc", "status", "authorization",
               "window", "conditions", "approval_refs", "b2_waiver"}
ALLOWED_WINDOW = {"status"}
ALLOWED_B2 = {"status", "approved_at_utc", "a5_pre_review_commit"}
EXPECTED_FILES = {}
EXPECTED_FILE_NAMES = ("plan.json", "identity_binding.json",
                       "initial_designs_manifest.json", "P2A_V2_PREREGISTRATION.md")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_blob(a2_repo, commit, relpath):
    try:
        return subprocess.run(["git", "-C", a2_repo, "show", "%s:%s" % (commit, relpath)],
                              check=True, capture_output=True).stdout
    except subprocess.CalledProcessError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--gate-json", required=True)
    ap.add_argument("--gate-commit", required=True)
    ap.add_argument("--a2-repo", default=r"D:\RCAIDE\dnext001\wt-real-a2-optimizers")
    ap.add_argument("--evidence-out", default=None)
    args = ap.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    a2_repo = os.path.abspath(args.a2_repo)
    draft = json.load(open(args.draft, encoding="utf-8"))
    gate = json.load(open(args.gate_json, encoding="utf-8-sig"))
    pkg_files_gate = gate.get("package_files") or {}
    for _name in EXPECTED_FILE_NAMES:
        _v = pkg_files_gate.get(_name)
        if isinstance(_v, dict) and _v.get("sha256"):
            EXPECTED_FILES[_name] = str(_v["sha256"])
        elif isinstance(_v, str) and len(_v) == 64:
            EXPECTED_FILES[_name] = _v
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
    if not conds:
        conds = [c.get("text") for c in (gate.get("conditions") or []) if isinstance(c, dict)]
    ok &= check("gate_conditions_full", isinstance(conds, list) and len(conds) == 52
                and all(isinstance(c, str) and c.strip() for c in conds), len(conds))
    srefs = dict((sr.get("approval_refs_final") or gate.get("approval_refs_final") or {}))
    srefs["a5_review"] = args.gate_commit
    ok &= check("gate_refs_complete",
                all(isinstance(v, str) and v and "TO_BE_FILLED" not in v for v in srefs.values()), srefs)
    for need in ("a1_bundle_commit", "a1_bundle_commit_full", "a1_bundle_manifest_sha256",
                 "a2_package_commit", "a2_execution_code"):
        ok &= check("gate_refs_has_" + need, need in srefs, list(srefs))
    ok &= check("gate_refs_bundle_commit",
                str(srefs.get("a1_bundle_commit")) == EXPECTED["bundle_commit_full"]
                and str(srefs.get("a1_bundle_commit_full")) == EXPECTED["bundle_commit_full"],
                [srefs.get("a1_bundle_commit"), srefs.get("a1_bundle_commit_full")])
    ok &= check("gate_refs_bundle_sha",
                str(srefs.get("a1_bundle_manifest_sha256")) == EXPECTED["bundle_sha"],
                srefs.get("a1_bundle_manifest_sha256"))
    for field, val in (("batch_id", EXPECTED["batch_id"]), ("run_id", EXPECTED["run_id"])):
        if field in gate:
            ok &= check("gate_" + field, gate.get(field) == val, [gate.get(field), val])
    anch = gate.get("anchors") or {}
    for field, val in (("batch_id", EXPECTED["batch_id"]), ("run_id", EXPECTED["run_id"]),
                       ("window_start_utc", EXPECTED["window_start"]),
                       ("window_end_utc", EXPECTED["window_end"]),
                       ("window_token", EXPECTED["token"]),
                       ("a1_bundle_manifest_sha256", EXPECTED["bundle_sha"]),
                       ("a1_executable_commit", "6753eb39b710035187db13ceb3328301c645c1ba")):
        ok &= check("gate_anchor_" + field, anch.get(field) == val, [anch.get(field), val])
    ok &= check("gate_anchor_a2_executor", anch.get("a2_executor_sha256") == srefs.get("a2_execution_code"),
                [anch.get("a2_executor_sha256"), srefs.get("a2_execution_code")])
    ok &= check("gate_anchor_pkg", anch.get("a2_package_commit") == srefs.get("a2_package_commit"),
                [anch.get("a2_package_commit"), srefs.get("a2_package_commit")])
    pkg_commit = str(srefs.get("a2_package_commit") or "")
    if not (len(pkg_commit) == 40 and all(c in "0123456789abcdef" for c in pkg_commit)):
        ok &= check("gate_pkg_commit_format", False, pkg_commit)

    # ---- draft identity / window / caps / cumulative ----
    ok &= check("draft_batch", draft.get("batch_id") == EXPECTED["batch_id"], draft.get("batch_id"))
    ok &= check("draft_run", draft.get("run_id") == EXPECTED["run_id"], draft.get("run_id"))
    win = draft.get("window") or {}
    ok &= check("draft_window_start", win.get("start_utc") == EXPECTED["window_start"], win.get("start_utc"))
    ok &= check("draft_window_end", win.get("end_utc") == EXPECTED["window_end"], win.get("end_utc"))
    ok &= check("draft_window_token", win.get("token") == EXPECTED["token"] and draft.get("token") == EXPECTED["token"],
                [draft.get("token"), win.get("token")])
    ok &= check("draft_planned_starts", draft.get("planned_starts") == EXPECTED["planned_starts"], draft.get("planned_starts"))
    ok &= check("draft_max_starts", draft.get("max_starts") == EXPECTED["max_starts"], draft.get("max_starts"))
    ok &= check("draft_planned_internal", draft.get("planned_internal_cases") == EXPECTED["planned_internal"],
                draft.get("planned_internal_cases"))
    ok &= check("draft_max_internal", draft.get("max_internal_cases") == EXPECTED["max_internal"],
                draft.get("max_internal_cases"))
    ok &= check("draft_reserve", draft.get("reserve_starts") == EXPECTED["reserve_starts"], draft.get("reserve_starts"))
    add = draft.get("r4_addendum") or {}
    cu = add.get("cumulative_accounting") or {}
    ok &= check("cum_starts", cu.get("cumulative_starts") == EXPECTED["cumulative_starts"], cu.get("cumulative_starts"))
    ok &= check("cum_internal", cu.get("cumulative_internal_cases") == EXPECTED["cumulative_internal"],
                cu.get("cumulative_internal_cases"))
    ok &= check("cum_prior", (cu.get("prior_charged_starts"), cu.get("prior_internal_cases"))
                == (EXPECTED["prior_starts"], EXPECTED["prior_internal"]),
                [cu.get("prior_charged_starts"), cu.get("prior_internal_cases")])
    ok &= check("cum_r1", (cu.get("r1_charged_starts"), cu.get("r1_internal_cases"))
                == (EXPECTED["r1_starts"], EXPECTED["r1_internal"]),
                [cu.get("r1_charged_starts"), cu.get("r1_internal_cases")])
    ok &= check("cum_r2", (cu.get("r2_charged_starts"), cu.get("r2_internal_cases"))
                == (EXPECTED["r2_starts"], EXPECTED["r2_internal"]),
                [cu.get("r2_charged_starts"), cu.get("r2_internal_cases")])
    ok &= check("cum_r3", (cu.get("r3_charged_starts"), cu.get("r3_internal_cases"))
                == (EXPECTED["r3_starts"], EXPECTED["r3_internal"]),
                [cu.get("r3_charged_starts"), cu.get("r3_internal_cases")])
    ok &= check("cum_r4_planned", (cu.get("r4_planned_starts"), cu.get("r4_planned_internal_cases"))
                == (EXPECTED["planned_starts"], EXPECTED["planned_internal"]),
                [cu.get("r4_planned_starts"), cu.get("r4_planned_internal_cases")])
    ok &= check("add_status", add.get("status") == "R4_TEMP_ROOT_FIX", add.get("status"))
    r3ref = add.get("r3_reference") or {}
    ok &= check("r3ref_sha", r3ref.get("superseded_approval_sha256") == EXPECTED["supersedes_sha"],
                r3ref.get("superseded_approval_sha256"))
    ok &= check("r3ref_polar", r3ref.get("polar_byte_match") is True, r3ref.get("polar_byte_match"))
    ok &= check("r3ref_preflight_bytes", r3ref.get("preflight_byte_match") is True,
                r3ref.get("preflight_byte_match"))
    sup = draft.get("supersedes") or {}
    ok &= check("supersedes_sha", sup.get("approval_sha256") == EXPECTED["supersedes_sha"], sup.get("approval_sha256"))
    ok &= check("supersedes_bytes", sup.get("approval_bytes") == EXPECTED["supersedes_bytes"], sup.get("approval_bytes"))
    ok &= check("supersedes_physical", sup.get("physical_call_count_at_supersede") == EXPECTED["supersedes_physical"],
                sup.get("physical_call_count_at_supersede"))
    ok &= check("supersedes_run", sup.get("run_id") == "DREAL001-P2A2R3-20261111-01", sup.get("run_id"))
    seq4 = [e for e in (draft.get("amendment_log") or []) if str(e.get("seq")) == "4"]
    ok &= check("amendment_seq4", len(seq4) == 1, draft.get("amendment_log"))
    if seq4:
        ok &= check("amendment_seq4_action", seq4[0].get("action") == "R4_TEMP_ROOT_ISOLATION_FIX",
                    seq4[0].get("action"))
        ok &= check("amendment_seq4_physical_6", seq4[0].get("physical_call_count_at_amendment") == 6,
                    seq4[0].get("physical_call_count_at_amendment"))
    prior_approval_path = str((draft.get("supersedes") or {}).get("approval_path") or "")
    ok &= check("prior_approval_exists", os.path.isfile(prior_approval_path), prior_approval_path)
    if os.path.isfile(prior_approval_path):
        ok &= check("prior_approval_sha", sha256_file(prior_approval_path) == EXPECTED["supersedes_sha"],
                    sha256_file(prior_approval_path))
        ok &= check("prior_approval_bytes", os.path.getsize(prior_approval_path) == EXPECTED["supersedes_bytes"],
                    os.path.getsize(prior_approval_path))
        prior = json.load(open(prior_approval_path, encoding="utf-8"))
        prior_log = prior.get("amendment_log") or []
        draft_log = draft.get("amendment_log") or []
        ok &= check("amendment_history_prefix", draft_log[:len(prior_log)] == prior_log,
                    "draft seq1-2 must equal signed R2 history")
    sums = os.path.join(run_dir, "SHA256SUMS.txt")
    ok &= check("sums_exists", os.path.isfile(sums), sums)
    if os.path.isfile(sums):
        n_sum = 0
        for line in open(sums, encoding="utf-8"):
            parts = line.split()
            if len(parts) < 2:
                continue
            n_sum += 1
            fn = parts[-1].lstrip("*")
            fp = os.path.join(run_dir, fn)
            ok &= check("sums:" + fn, os.path.isfile(fp) and sha256_file(fp) == parts[0],
                        "listed=" + parts[0] + " actual=" + (sha256_file(fp) if os.path.isfile(fp) else "MISSING"))
        ok &= check("sums_lines_7", n_sum == 7, n_sum)

    ok &= check("draft_not_approved", draft.get("approved") is False
                and draft.get("status") == "DRAFT_AWAITING_LEAD_SIGNATURE",
                [draft.get("approved"), draft.get("status")])
    ok &= check("draft_zero_physical", (draft.get("physical_call_count"), draft.get("physical_solver_starts"),
                                        draft.get("solver_started")) == (0, 0, False),
                [draft.get("physical_call_count"), draft.get("physical_solver_starts"), draft.get("solver_started")])
    ok &= check("draft_conditions_15", len(draft.get("conditions") or []) == 15, len(draft.get("conditions") or []))
    for bad in ("solver_attempts.jsonl", "cases", "evaluations", "batch_summary.json",
                "stop_report.json", "approval.json"):
        ok &= check("pre_exec_absent:" + bad, not os.path.exists(os.path.join(run_dir, bad)),
                    os.path.join(run_dir, bad))
    ok &= check("approval_absent_until_sign", not os.path.exists(os.path.join(run_dir, "approval.json")),
                os.path.join(run_dir, "approval.json"))

    # ---- package files vs draft SHA + committed blobs ----
    rel_dir = os.path.relpath(run_dir, a2_repo).replace("\\", "/")
    pkg_files = {
        "plan.json": draft.get("plan_sha256"),
        "P2A_V2_PREREGISTRATION.md": draft.get("prereg_sha256"),
        "identity_binding.json": draft.get("identity_binding_file_sha256"),
        "initial_designs_manifest.json": draft.get("initial_designs_manifest_sha256"),
    }
    for fname, expect in pkg_files.items():
        p = os.path.join(run_dir, fname)
        ok &= check("file_exists:" + fname, os.path.isfile(p), p)
        if os.path.isfile(p):
            actual = sha256_file(p)
            ok &= check("file_sha:" + fname, actual == expect, "expected=" + str(expect) + " actual=" + actual)
            if pkg_commit:
                blob = git_blob(a2_repo, pkg_commit, rel_dir + "/" + fname)
                ok &= check("pkg_commit_blob:" + fname, blob is not None and blob == open(p, "rb").read(),
                            "commit=" + pkg_commit)
    ok &= check("dry_run_present", os.path.isfile(os.path.join(run_dir, "dry_run.json")))
    ok &= check("executor_dry_run_present", os.path.isfile(os.path.join(run_dir, "executor_dry_run.json")))
    ok &= check("SHA256SUMS_present", os.path.isfile(os.path.join(run_dir, "SHA256SUMS.txt")))

    # ---- A2 executor blob ----
    executor_sha = None
    for ent in draft.get("executor_blob", {}).get("a2", []):
        p = ent["path"]; name = os.path.basename(p)
        ok &= check("executor_exists:" + name, os.path.isfile(p), p)
        if os.path.isfile(p):
            actual = sha256_file(p)
            ok &= check("executor_sha:" + name, actual == ent["sha256"],
                        "expected=" + str(ent["sha256"]) + " actual=" + actual)
            if name == "p2a_v2_executor.py":
                executor_sha = actual
    ok &= check("a2_executor_sha_matches", executor_sha == draft.get("a2_executor_sha256"),
                [executor_sha, draft.get("a2_executor_sha256")])
    ok &= check("a2_executor_sha_gate", executor_sha == srefs.get("a2_execution_code"),
                [executor_sha, srefs.get("a2_execution_code")])

    # ---- A1 replay bundle manifest ----
    rb = draft.get("replay_bundles") or {}
    rbp = rb.get("bundle_manifest_path", "")
    ok &= check("replay_bundle_exists", os.path.isfile(rbp), rbp)
    if os.path.isfile(rbp):
        actual = sha256_file(rbp)
        ok &= check("replay_bundle_sha", actual == rb.get("bundle_manifest_sha256"),
                    [rb.get("bundle_manifest_sha256"), actual])
        ok &= check("replay_bundle_expected", rb.get("bundle_manifest_sha256") == EXPECTED["bundle_sha"],
                    rb.get("bundle_manifest_sha256"))
    ok &= check("replay_bundle_cases_2", sorted((rb.get("cases") or {}).keys()) == ["PRE-01", "PRE-02"],
                sorted((rb.get("cases") or {}).keys()))

    # ---- solver exe binding ----
    solver = draft.get("solver") or {}
    ok &= check("solver_exe_sha", str(solver.get("exe_sha256", "")).lower() == EXPECTED["bare_sha256"],
                solver.get("exe_sha256"))
    ok &= check("solver_fuel_null", solver.get("fuel_burn_kg") is None, solver.get("fuel_burn_kg"))
    ok &= check("solver_phys_not_validated", solver.get("physical_validation_status") == "NOT_VALIDATED",
                solver.get("physical_validation_status"))

    if not ok:
        print("SIGN_ABORTED: preconditions failed; approval.json NOT written")
        return 1

    # ---- build signed approval ----
    now = utcnow()
    appr = json.loads(json.dumps(draft))
    sd = sr.get("scalar_deltas") or sr.get("allowed_scalar_deltas") or {}
    appr["approved"] = True
    appr["approved_by"] = "lead"
    appr["approved_at_utc"] = now
    appr["status"] = "APPROVED_FOR_EXECUTION_PENDING_POST_APPROVAL_DRY_RUN"
    auth = (sd.get("authorization") if isinstance(sd, dict) else None) or {}
    auth = auth if isinstance(auth, dict) else {}
    scope = auth.get("scope") if isinstance(auth.get("scope"), str) else ""
    if not scope or "PENDING" in scope:
        scope = ("batch_id %s / run_id %s only; requires post-approval dry-run "
                 "and Lead GO before first solver start") % (EXPECTED["batch_id"], EXPECTED["run_id"])
    ok &= check("authorization_scope_r4",
                EXPECTED["batch_id"] in scope and EXPECTED["run_id"] in scope, scope)
    appr["authorization"] = {
        "mode": "LEAD_SINGLE_BATCH_APPROVAL",
        "scope": scope,
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

    def diff(a, b):
        return {k for k in set(a) | set(b) if a.get(k) != b.get(k)}

    dtop = diff(draft, appr)
    ok &= check("delta_top_allowed", dtop <= ALLOWED_TOP, sorted(dtop - ALLOWED_TOP))
    dwin = diff(draft.get("window") or {}, appr.get("window") or {})
    ok &= check("delta_window_allowed", dwin <= ALLOWED_WINDOW, sorted(dwin - ALLOWED_WINDOW))
    db2 = diff(draft.get("b2_waiver") or {}, appr.get("b2_waiver") or {})
    ok &= check("delta_b2_allowed", db2 <= ALLOWED_B2, sorted(db2 - ALLOWED_B2))
    inv_names = sr.get("signed_approval_invariants_unchanged")
    if inv_names is not None:
        bad_inv = [n for n in inv_names if draft.get(n) != appr.get(n)]
        ok &= check("a5_invariants_unchanged", not bad_inv, bad_inv)
    else:
        inv_stmt = sr.get("invariants_unchanged") or []
        ok &= check("a5_invariants_statements_present",
                    len(inv_stmt) >= 8 and all(isinstance(s, str) and s.strip() for s in inv_stmt),
                    len(inv_stmt))
    for fname, exp in EXPECTED_FILES.items():
        p = os.path.join(run_dir, fname)
        ok &= check("inv_file:" + fname, os.path.isfile(p) and sha256_file(p) == exp,
                    "expected=" + exp + " actual=" + (sha256_file(p) if os.path.isfile(p) else "MISSING"))
    if not ok:
        print("SIGN_ABORTED: delta/invariant checks failed; approval.json NOT written")
        return 1

    out = os.path.join(run_dir, "approval.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(appr, ensure_ascii=False, indent=2) + "\n")
    appr_sha = sha256_file(out)
    appr_bytes = os.path.getsize(out)

    rt = json.load(open(out, encoding="utf-8"))
    valid = True
    valid &= check("post_approved", rt.get("approved") is True)
    valid &= check("post_status", rt.get("status") == "APPROVED_FOR_EXECUTION_PENDING_POST_APPROVAL_DRY_RUN",
                   rt.get("status"))
    valid &= check("post_window_status", (rt.get("window") or {}).get("status") == "APPROVED",
                   (rt.get("window") or {}).get("status"))
    valid &= check("post_token", rt.get("token") == (rt.get("window") or {}).get("token") == EXPECTED["token"],
                   rt.get("token"))
    valid &= check("post_batch_run", (rt.get("batch_id"), rt.get("run_id"))
                   == (EXPECTED["batch_id"], EXPECTED["run_id"]), [rt.get("batch_id"), rt.get("run_id")])
    valid &= check("post_conditions_count", len(rt.get("conditions") or []) == len(conds), len(rt.get("conditions") or []))
    valid &= check("post_refs_a5", (rt.get("approval_refs") or {}).get("a5_review") == args.gate_commit,
                   (rt.get("approval_refs") or {}).get("a5_review"))
    valid &= check("post_refs_bundle",
                   (rt.get("approval_refs") or {}).get("a1_bundle_manifest_sha256") == EXPECTED["bundle_sha"],
                   (rt.get("approval_refs") or {}).get("a1_bundle_manifest_sha256"))
    valid &= check("post_refs_bundle_commit",
                   (rt.get("approval_refs") or {}).get("a1_bundle_commit") == EXPECTED["bundle_commit_full"]
                   and (rt.get("approval_refs") or {}).get("a1_bundle_commit_full") == EXPECTED["bundle_commit_full"],
                   [(rt.get("approval_refs") or {}).get("a1_bundle_commit"),
                    (rt.get("approval_refs") or {}).get("a1_bundle_commit_full")])
    valid &= check("post_refs_pkg", (rt.get("approval_refs") or {}).get("a2_package_commit") == pkg_commit,
                   (rt.get("approval_refs") or {}).get("a2_package_commit"))
    valid &= check("post_b2_waiver", (rt.get("b2_waiver") or {}).get("a5_pre_review_commit") == args.gate_commit,
                   (rt.get("b2_waiver") or {}).get("a5_pre_review_commit"))
    print("POST_WRITE_VALIDATION:", "PASS" if valid else "FAIL")
    print("APPROVAL_PATH:", out)
    print("APPROVAL_SHA256:", appr_sha)
    print("APPROVAL_BYTES:", appr_bytes)
    print("CONDITIONS:", len(rt.get("conditions") or []))

    ev = {
        "schema": "dreal001.lead_signature_receipt.v1",
        "batch_id": draft.get("batch_id"), "run_id": draft.get("run_id"),
        "signed_by": "lead", "signed_at_utc": now,
        "approval_path": out, "approval_sha256": appr_sha, "approval_bytes": appr_bytes,
        "draft_path": os.path.abspath(args.draft), "draft_sha256": sha256_file(args.draft),
        "a5_gate_id": gate.get("gate_id"), "a5_gate_path": os.path.abspath(args.gate_json),
        "a5_gate_sha256": sha256_file(args.gate_json), "a5_gate_commit": args.gate_commit,
        "a2_package_commit": pkg_commit,
        "conditions_count": len(rt.get("conditions") or []),
        "approval_refs": rt.get("approval_refs"),
        "physical_call_count_at_sign": 0,
        "checks": checks,
    }
    ev_path = args.evidence_out or os.path.join(
        r"D:\RCAIDE\dnext001\wt-real-lead\docs\evidence\dreal001",
        "lead_signature_r3_" + now.replace(":", "").replace("-", "") + ".json")
    os.makedirs(os.path.dirname(os.path.abspath(ev_path)), exist_ok=True)
    with open(ev_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(ev, ensure_ascii=False, indent=2) + "\n")
    print("EVIDENCE_PATH:", os.path.abspath(ev_path))
    print("EVIDENCE_SHA256:", sha256_file(ev_path))
    print("SIGN_OK" if valid else "SIGN_POST_VALIDATION_FAILED")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
