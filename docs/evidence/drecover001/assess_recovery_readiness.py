"""Aggregate recovery evidence receipts into one auditable readiness matrix.

Zero physics: this script only reads archived evidence bytes and source files.
It never starts a solver, never imports the training stack, and never mints an
approval. A CLOSED gate means the required independent sign-off is absent; a
CONFLICT means two pieces of evidence disagree. Only an actual A5 reviewer can
lift the closed gates.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_REL = Path("docs/evidence/drecover001")
RUN_ID_RE = re.compile(r"DRECOVER001-SOFTWARE-\d{8}T\d{6}Z")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER_TOKEN = "STRUCTURAL_SOFTWARE_FIXTURE_NOT_A_REAL_GO"
READINESS_FILES = {"recovery_readiness.json", "recovery_readiness.md"}


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def load_json(root, relative):
    path = Path(root) / relative
    if not path.is_file():
        return None, "missing file: %s" % relative
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, "unreadable JSON %s: %s" % (relative, exc)


def new_gate(gate_id, title):
    return {"id": gate_id, "title": title, "state": "UNKNOWN", "checks": [],
            "violations": [], "missing": [], "blockers": [], "evidence": []}


def record(node, name, ok, detail, failure="violations"):
    node["checks"].append({"name": name, "status": "PASS" if ok else "FAIL",
                           "detail": detail})
    if not ok:
        node[failure].append("%s: %s" % (name, detail))


def info(node, name, detail):
    node["checks"].append({"name": name, "status": "INFO", "detail": detail})


def finalize(node, clean=False, waived=False):
    if node["violations"]:
        node["state"] = "CONFLICT"
    elif node["missing"]:
        node["state"] = "UNKNOWN"
    elif clean and not node["blockers"]:
        node["state"] = "CLEAN"
    elif waived:
        node["state"] = "WAIVED"
    else:
        node["state"] = "CLOSED"
    return node


def _finite_positive(value):
    try:
        return float(value) > 0 and float(value) < float("inf")
    except (TypeError, ValueError):
        return False


def _git_raw(root, args):
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                             text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if out.returncode != 0:
        return None, (out.stderr or out.stdout).strip()[:400]
    return out.stdout, None


def _git(root, args):
    text, err = _git_raw(root, args)
    if text is None:
        return None, err
    return text.strip(), None


def _status_paths(status_text):
    """Parse git status --porcelain=v1 -z without stripping the first entry.

    The first record may start with a leading space (for example " M path"),
    so callers must pass the untouched stdout.
    """
    excluded = {
        "docs/evidence/drecover001/recovery_change_manifest.json",
        "docs/evidence/drecover001/recovery_readiness.json",
        "docs/evidence/drecover001/recovery_readiness.md",
        "docs/evidence/drecover001/a5_review_packet.json",
        "docs/evidence/drecover001/a5_review_packet.md",
        # Written after the bundle exists; excluded from the bundle manifest to
        # avoid a self-referential hash. The backup gate still checks the receipt.
        "docs/evidence/drecover001/local_restore_receipt.json",
    }
    dirty = set()
    for raw in status_text.split("\0"):
        if not raw:
            continue
        name = raw[3:]
        if " -> " in name:
            name = name.split(" -> ", 1)[1]
        if not name or "__pycache__/" in name or name.endswith(".pyc"):
            continue
        if name in excluded:
            continue
        dirty.add(name)
    return dirty


def assess_r0(root, report):
    node = new_gate("R0_INVENTORY", "R0 loss ledger and provenance inventory")
    inventory, err = load_json(root, EVIDENCE_REL / "recovery_inventory.json")
    if inventory is None:
        node["missing"].append("recovery_inventory.json: %s" % err)
        return report["gates"].append(finalize(node))
    node["evidence"].append("docs/evidence/drecover001/recovery_inventory.json")
    record(node, "inventory_status_expected",
           inventory.get("status") == "R0_PARTIAL_NOT_AUDITED",
           "status=%r" % inventory.get("status"))
    record(node, "inventory_gate_unsigned",
           inventory.get("gate_verdict") == "NOT_SIGNED_R0_INCOMPLETE",
           "gate_verdict=%r" % inventory.get("gate_verdict"))
    review = inventory.get("independent_review") or {}
    record(node, "independent_review_not_started",
           review.get("status") == "NOT_STARTED",
           "independent_review.status=%r" % review.get("status"))
    record(node, "zero_physical_counters",
           inventory.get("physical_solver_starts_actual_this_recovery") == 0
           and inventory.get("internal_solver_cases_actual_this_recovery") == 0,
           "physical=%r internal=%r" % (
               inventory.get("physical_solver_starts_actual_this_recovery"),
               inventory.get("internal_solver_cases_actual_this_recovery")))
    record(node, "zero_admitted_labels",
           inventory.get("admitted_scientific_labels_this_recovery") == 0,
           "admitted=%r" % inventory.get("admitted_scientific_labels_this_recovery"))
    byte_audit = inventory.get("byte_audit") or {}
    record(node, "byte_audit_present",
           bool(byte_audit.get("evidence"))
           and (Path(root) / str(byte_audit.get("evidence"))).is_file(),
           "evidence=%r" % byte_audit.get("evidence"))
    record(node, "raw_git_object_identity_verified",
           byte_audit.get("raw_git_object_identity_verified") is True,
           "raw_git_object_identity_verified=%r" % byte_audit.get("raw_git_object_identity_verified"))
    history = inventory.get("reachable_history") or {}
    record(node, "reachable_history_documented",
           history.get("reachable_commits", 0) > 0
           and bool(history.get("evidence")),
           "commits=%r evidence=%r" % (history.get("reachable_commits"), history.get("evidence")))
    ext = inventory.get("r0_provenance_extension") or {}
    ext_path = Path(root) / "docs/evidence/drecover001/r0_provenance_extension.json"
    record(node, "provenance_extension_present", ext_path.is_file(),
           "path=%s" % ext_path.relative_to(Path(root)))
    if ext_path.is_file():
        actual = sha256_file(ext_path)
        record(node, "provenance_extension_sha_matches_inventory",
               ext.get("sha256") == actual,
               "inventory=%r actual=%r" % (ext.get("sha256"), actual))
    ver_rel = EVIDENCE_REL / "r0_provenance_extension_verification.json"
    verification, verr = load_json(root, ver_rel)
    if verification is None:
        node["missing"].append("r0_provenance_extension_verification.json: %s" % verr)
    else:
        node["evidence"].append(str(ver_rel))
        record(node, "provenance_verification_status",
               verification.get("status") == "R0_PROVENANCE_EXTENSION_EVIDENCE_INTERNALLY_CONSISTENT",
               "status=%r" % verification.get("status"))
        record(node, "provenance_verification_no_failures",
               verification.get("failure_count") == 0 and not verification.get("failures"),
               "failure_count=%r" % verification.get("failure_count"))
        record(node, "provenance_verification_checks_positive",
               isinstance(verification.get("check_count"), int)
               and verification.get("check_count") > 0,
               "check_count=%r" % verification.get("check_count"))
        ext_name = verification.get("extension") or "docs/evidence/drecover001/r0_provenance_extension.json"
        script_name = verification.get("script") or "docs/evidence/drecover001/audit_provenance_extension.py"
        for label, name, field in (("extension", ext_name, "extension_sha256"),
                                   ("script", script_name, "script_sha256")):
            candidate = Path(root) / str(name)
            if not candidate.is_file():
                node["violations"].append("%s_sha_matches_archived_bytes: missing %s" % (label, name))
                continue
            record(node, "%s_sha_matches_archived_bytes" % label,
                   verification.get(field) == sha256_file(candidate),
                   "recorded=%r actual=%r" % (verification.get(field), sha256_file(candidate)))
    baseline, berr = load_json(root, EVIDENCE_REL / "new_baseline_manifest.json")
    if baseline is None:
        node["missing"].append("new_baseline_manifest.json: %s" % berr)
    else:
        node["evidence"].append("docs/evidence/drecover001/new_baseline_manifest.json")
        record(node, "new_baseline_schema",
               baseline.get("schema") == "drecover001.new_baseline_manifest.v1",
               "schema=%r" % baseline.get("schema"))
        record(node, "new_baseline_base_commit",
               bool(re.fullmatch(r"[0-9a-f]{40}", str(baseline.get("base_commit")))),
               "base_commit=%r" % baseline.get("base_commit"))
        history_policy = baseline.get("historical_data_policy") or {}
        record(node, "historical_data_archived_raw_lost",
               history_policy.get("status") == "RAW_LOST_ARCHIVED"
               and history_policy.get("search_policy") == "STOPPED_NO_FURTHER_HISTORY_RECOVERY_SEARCH",
               "status=%r search=%r" % (history_policy.get("status"),
                                        history_policy.get("search_policy")))
        required = (baseline.get("identity_policy") or {}).get("new_physical_runs_require") or []
        record(node, "new_identity_policy_requires_geometry_and_admission",
               "new_geometry_sha256" in required and "RealAdmissionManifest" in required
               and "fresh Lead batch GO" in required,
               "required=%r" % required)
        record(node, "new_baseline_zero_physical",
               baseline.get("physical_solver_starts_actual") == 0
               and baseline.get("internal_solver_cases_actual") == 0
               and baseline.get("admitted_scientific_labels") == 0,
               "physical=%r internal=%r admitted=%r" % (
                   baseline.get("physical_solver_starts_actual"),
                   baseline.get("internal_solver_cases_actual"),
                   baseline.get("admitted_scientific_labels")))
    node["blockers"].append("Independent A5 review of the new baseline identity is not a human signature; the recorded deepseek-flash verdict is review input only")
    report["gates"].append(finalize(node))


def assess_geometry_freeze(root, report):
    node = new_gate("A1_GEOMETRY_FREEZE_V2", "A1 geometry freeze v2 (zero physical)")
    freeze, ferr = load_json(root, EVIDENCE_REL / "geometry_freeze_v2.json")
    verification, verr = load_json(root, EVIDENCE_REL / "geometry_freeze_v2_verification.json")
    baseline, berr = load_json(root, EVIDENCE_REL / "new_baseline_manifest.json")
    if freeze is None or verification is None or baseline is None:
        node["missing"].append("geometry freeze evidence: %s / %s / %s" % (ferr, verr, berr))
        return report["gates"].append(finalize(node))
    node["evidence"] += ["docs/evidence/drecover001/geometry_freeze_v2.json",
                         "docs/evidence/drecover001/geometry_freeze_v2_verification.json",
                         "docs/evidence/drecover001/new_baseline_manifest.json"]
    record(node, "freeze_status_issued", freeze.get("status") == "GEOMETRY_FREEZE_V2_ISSUED_ZERO_PHYSICAL",
           "status=%r" % freeze.get("status"))
    record(node, "freeze_scope_geometry_only",
           freeze.get("scope") == "GEOMETRY_AND_REFERENCE_CONTRACT_ONLY_NO_AERODYNAMIC_VALIDATION",
           "scope=%r" % freeze.get("scope"))
    record(node, "freeze_zero_physical",
           freeze.get("physical_solver_starts_actual") == 0
           and freeze.get("internal_solver_cases_actual") == 0,
           "physical=%r internal=%r" % (freeze.get("physical_solver_starts_actual"),
                                        freeze.get("internal_solver_cases_actual")))
    record(node, "freeze_contract_sha_format",
           bool(SHA_RE.fullmatch(str(freeze.get("geometry_contract_sha256")))),
           "sha=%r" % freeze.get("geometry_contract_sha256"))
    record(node, "freeze_consistency_all_pass",
           all(item.get("ok") is True for item in freeze.get("consistency_checks", []))
           and len(freeze.get("consistency_checks", [])) > 0,
           "checks=%d" % len(freeze.get("consistency_checks", [])))
    boundary = freeze.get("boundary_perturbation") or {}
    record(node, "freeze_boundary_perturbation_all_pass",
           boundary.get("all_ok") is True
           and boundary.get("model_cases_ok") == 24
           and boundary.get("native_cases_ok") == boundary.get("native_cases_total") == 24,
           "model=%r native=%r/%r" % (boundary.get("model_cases_ok"),
                                      boundary.get("native_cases_ok"),
                                      boundary.get("native_cases_total")))
    export = freeze.get("real_openvsp_export") or {}
    bad_exports = []
    for fmt, row in (export.get("exports") or {}).items():
        path = Path(root) / str(row.get("path"))
        if not path.is_file() or path.stat().st_size != row.get("bytes") or sha256_file(path) != row.get("sha256"):
            bad_exports.append(fmt)
    record(node, "freeze_exports_match_disk", not bad_exports and bool(export.get("exports")),
           "bad=%r count=%d" % (bad_exports, len(export.get("exports") or {})))
    record(node, "freeze_verification_status",
           verification.get("status") == "GEOMETRY_FREEZE_V2_VERIFIED",
           "status=%r" % verification.get("status"))
    record(node, "freeze_verification_zero_failures",
           verification.get("failure_count") == 0 and not verification.get("failures")
           and isinstance(verification.get("check_count"), int)
           and verification.get("check_count") >= 100,
           "checks=%r failures=%r" % (verification.get("check_count"),
                                      verification.get("failure_count")))
    freeze_sha = sha256_file(Path(root) / "docs/evidence/drecover001/geometry_freeze_v2.json")
    verification_sha = sha256_file(Path(root) / "docs/evidence/drecover001/geometry_freeze_v2_verification.json")
    baseline_status = (baseline.get("geometry_freeze_status") or {})
    record(node, "baseline_records_freeze_identity",
           baseline_status.get("current_geometry_contract_sha256") == freeze.get("geometry_contract_sha256")
           and baseline_status.get("freeze_id") == freeze.get("freeze_id")
           and baseline_status.get("status") == freeze.get("status"),
           "freeze_id=%r" % baseline_status.get("freeze_id"))
    record(node, "baseline_records_freeze_hash",
           baseline_status.get("freeze_json_sha256") == freeze_sha
           and baseline_status.get("verification_sha256") == verification_sha,
           "json_recorded=%r actual=%r" % (baseline_status.get("freeze_json_sha256"), freeze_sha))
    node["blockers"].append("A1 geometry freeze is geometry/reference only; force-axis signs, WING_AC moment origin and mass/CG remain unvalidated until R2 VSPAERO readback")
    report["gates"].append(finalize(node))


def assess_r1(root, report, preflight):
    node = new_gate("R1_SOFTWARE", "R1 source recovery and software regression")
    if not preflight:
        node["missing"].append("recovery_preflight_receipt.json is missing or unreadable")
        return report["gates"].append(finalize(node))
    node["evidence"].append("docs/evidence/drecover001/recovery_preflight_receipt.json")
    run_id = preflight.get("run_id")
    record(node, "software_run_id_format", bool(RUN_ID_RE.fullmatch(str(run_id))),
           "run_id=%r" % run_id)
    record(node, "software_tests_pass",
           preflight.get("software_tests_status") == "PASS"
           and isinstance(preflight.get("tests_run"), int)
           and preflight.get("tests_run") > 0
           and preflight.get("failures") == 0
           and preflight.get("errors") == 0
           and preflight.get("skipped") == 0,
           "tests=%r status=%r failures=%r errors=%r skipped=%r" % (
               preflight.get("tests_run"), preflight.get("software_tests_status"),
               preflight.get("failures"), preflight.get("errors"),
               preflight.get("skipped")))
    record(node, "zero_physical_counters",
           preflight.get("physical_solver_starts_actual_this_recovery") == 0
           and preflight.get("internal_solver_cases_actual_this_recovery") == 0,
           "physical=%r internal=%r" % (
               preflight.get("physical_solver_starts_actual_this_recovery"),
               preflight.get("internal_solver_cases_actual_this_recovery")))
    record(node, "fixture_only_training",
           preflight.get("real_meta_training_executed") is False
           and preflight.get("admitted_real_labels") == 0
           and preflight.get("training_status") == "SOFTWARE_FIXTURE_TRAINING_ONLY",
           "training_status=%r real=%r admitted=%r" % (
               preflight.get("training_status"),
               preflight.get("real_meta_training_executed"),
               preflight.get("admitted_real_labels")))
    record(node, "fixture_training_changed_parameters",
           preflight.get("training_steps_per_model") == 20
           and all(_finite_positive(v) for v in
                   (preflight.get("parameter_l2_change_from_initial") or {}).values()),
           "steps=%r l2=%r" % (preflight.get("training_steps_per_model"),
                               preflight.get("parameter_l2_change_from_initial")))
    record(node, "fixture_checkpoint_hash_format",
           bool(SHA_RE.fullmatch(str(preflight.get("synthetic_checkpoint_sha256")))),
           "sha=%r" % preflight.get("synthetic_checkpoint_sha256"))
    trace_sha = preflight.get("synthetic_training_trace_sha256")
    trace_path = Path(root) / "docs/evidence/drecover001/synthetic_software_training_trace.json"
    record(node, "fixture_trace_archived_matches_receipt",
           trace_path.is_file() and trace_sha == sha256_file(trace_path),
           "recorded=%r actual=%r" % (trace_sha, sha256_file(trace_path) if trace_path.is_file() else None))
    drift = []
    sources = preflight.get("source_sha256") or {}
    record(node, "source_hash_manifest_non_empty", len(sources) > 0,
           "entries=%d" % len(sources))
    for relative, expected in sources.items():
        candidate = Path(root) / relative
        if not candidate.is_file():
            drift.append("%s missing" % relative)
        elif sha256_file(candidate) != expected:
            drift.append("%s changed" % relative)
    record(node, "recorded_sources_still_current", not drift,
           "drift=%d %s" % (len(drift), drift[:5]))
    a2, a2_err = load_json(root, EVIDENCE_REL / "a2_feedback_rehearsal.json")
    if a2 is None:
        node["missing"].append("a2_feedback_rehearsal.json: %s" % a2_err)
    else:
        node["evidence"].append("docs/evidence/drecover001/a2_feedback_rehearsal.json")
        baseline = a2.get("baseline") or {}
        counterfactual = a2.get("counterfactual") or {}
        failed = a2.get("failed_objective_branch") or {}
        record(node, "a2_rehearsal_schema_and_scope",
               a2.get("schema") == "drecover001.a2_feedback_rehearsal.v1"
               and a2.get("scope") == "SOFTWARE_FEEDBACK_REHEARSAL_ONLY_NOT_PHYSICAL_EVIDENCE",
               "schema=%r scope=%r" % (a2.get("schema"), a2.get("scope")))
        record(node, "a2_rehearsal_zero_physical",
               a2.get("physical_solver_starts_actual") == 0
               and baseline.get("physical_solver_starts") == 0,
               "receipt=%r baseline=%r" % (a2.get("physical_solver_starts_actual"),
                                           baseline.get("physical_solver_starts")))
        record(node, "a2_rehearsal_real_arm_feedback",
               baseline.get("status") == "COMPLETED"
               and baseline.get("evaluations_requested") == 6
               and baseline.get("valid_evals") == 6
               and baseline.get("simulated_solver_starts") == 6,
               "status=%r requested=%r valid=%r simulated=%r" % (
                   baseline.get("status"), baseline.get("evaluations_requested"),
                   baseline.get("valid_evals"), baseline.get("simulated_solver_starts")))
        record(node, "a2_rehearsal_feedback_is_causal",
               counterfactual.get("first_two_proposals_identical") is True
               and counterfactual.get("third_proposal_differs") is True,
               "first_two_identical=%r third_differs=%r" % (
                   counterfactual.get("first_two_proposals_identical"),
                   counterfactual.get("third_proposal_differs")))
        record(node, "a2_rehearsal_failed_objective_is_null",
               failed.get("first_row_status") == "FAIL"
               and failed.get("first_row_valid") is False
               and failed.get("first_row_objective_D_i_N") is None,
               "status=%r valid=%r objective=%r" % (
                   failed.get("first_row_status"), failed.get("first_row_valid"),
                   failed.get("first_row_objective_D_i_N")))
    current_docs = {"recovery_inventory.md", "needed_for_next_run.json",
                    "issue12_consolidated_receipt_draft_20261117.md",
                    "maml_readiness_20261117.md"}
    stale_current, historical = [], []
    for folder, pattern in ((Path(root) / "docs/evidence/drecover001", "*.md"),
                            (Path(root) / "docs/evidence/drecover001", "*.json"),
                            (Path(root) / "docs/planning", "*.md")):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob(pattern)):
            if path.name in READINESS_FILES:
                continue
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            wrong = sorted(set(RUN_ID_RE.findall(text)) - {run_id})
            if not wrong:
                continue
            if path.name in current_docs:
                stale_current.append("%s -> %s" % (path.relative_to(Path(root)), ",".join(wrong)))
            else:
                historical.append(path.name)
    record(node, "current_state_docs_cite_latest_software_run_id", not stale_current,
           "stale_current=%d %s" % (len(stale_current), stale_current[:5]))
    info(node, "historical_docs_keep_their_original_run_ids",
         "historical=%d %s" % (len(historical), historical[:8]))
    node["blockers"].append("Independent A5 review is a recorded deepseek-flash subagent verdict (not a human signature); no human/Owner sign-off exists")
    node["blockers"].append("Independent failure-domain backup is waived by the Owner (m03569); the same-host restore is not an off-machine backup")
    report["gates"].append(finalize(node))


def assess_m1(root, report):
    node = new_gate("M1_BATCH_CONTROL_PATH", "M1 batch control path (software fixture only)")
    base = EVIDENCE_REL
    receipt, err = load_json(root, base / "m1_batch_software_rehearsal_receipt.json")
    result, rerr = load_json(root, base / "m1_batch_software_result.json")
    verification, verr = load_json(root, base / "m1_batch_software_verification.json")
    if receipt is None or result is None:
        node["missing"].append("M1 receipt/result: %s / %s" % (err, rerr))
        return report["gates"].append(finalize(node))
    node["evidence"] += [str(base / "m1_batch_software_rehearsal_receipt.json"),
                         str(base / "m1_batch_software_result.json")]
    record(node, "scope_offline", receipt.get("scope") == "OFFLINE_BATCH_SKELETON_ONLY",
           "scope=%r" % receipt.get("scope"))
    record(node, "authorization_is_placeholder",
           receipt.get("authorization_kind") == PLACEHOLDER_TOKEN,
           "authorization_kind=%r" % receipt.get("authorization_kind"))
    record(node, "no_a5_signature", receipt.get("a5_independent_review") == "NOT_PERFORMED",
           "a5=%r" % receipt.get("a5_independent_review"))
    record(node, "result_complete",
           result.get("status") == "COMPLETE"
           and receipt.get("result_status") == "COMPLETE",
           "result.status=%r receipt.result_status=%r" % (
               result.get("status"), receipt.get("result_status")))
    record(node, "evidence_grade_control_only",
           result.get("evidence_grade") == "SOFTWARE_CONTROL_PATH_ONLY",
           "evidence_grade=%r" % result.get("evidence_grade"))
    record(node, "result_sha_consistent",
           receipt.get("result_sha256") == result.get("result_sha256"),
           "receipt=%r result=%r" % (receipt.get("result_sha256"), result.get("result_sha256")))
    record(node, "plan_sha_consistent",
           receipt.get("plan_sha256") == result.get("plan_sha256"),
           "receipt=%r result=%r" % (receipt.get("plan_sha256"), result.get("plan_sha256")))
    accounting = result.get("accounting") or {}
    record(node, "fixture_physical_zero",
           accounting.get("physical_solver_starts_actual") == 0
           and receipt.get("admitted_real_labels") == 0,
           "physical=%r admitted=%r" % (
               accounting.get("physical_solver_starts_actual"),
               receipt.get("admitted_real_labels")))
    record(node, "fixture_budget_consistent",
           accounting.get("starts_issued") == accounting.get("simulated_solver_starts_actual")
           and accounting.get("charged_planned_reserved") == accounting.get("planned_reserved")
           and (accounting.get("internal_solver_cases_actual") or 0) >= 0,
           "accounting=%r" % accounting)
    controls = result.get("controls") or {}
    placeholder_claims = (controls.get("physical_go") is True
                          or controls.get("a5_verdict") not in (None, "NOT_PERFORMED"))
    record(node, "placeholder_gate_claims_disclosed",
           (not placeholder_claims)
           or (receipt.get("authorization_kind") == PLACEHOLDER_TOKEN
               and receipt.get("a5_independent_review") == "NOT_PERFORMED"
               and receipt.get("admitted_real_labels") == 0
               and result.get("evidence_grade") == "SOFTWARE_CONTROL_PATH_ONLY"),
           "controls=%r" % controls)
    if verification is None:
        node["missing"].append("m1_batch_software_verification.json: %s" % verr)
    else:
        node["evidence"].append(str(base / "m1_batch_software_verification.json"))
        record(node, "m1_verifier_consistent",
               verification.get("status") == "M1_BATCH_EVIDENCE_INTERNALLY_CONSISTENT"
               and not verification.get("failures"),
               "status=%r failures=%r" % (verification.get("status"),
                                          verification.get("failures")))
    node["blockers"].append("Real M1 label batch requires a new A5 gate and a Lead batch GO; none issued")
    report["gates"].append(finalize(node))


def assess_m2(root, report):
    node = new_gate("M2_OFFLINE_REHEARSAL", "M2 offline FOMAML/pretrain rehearsal")
    base = EVIDENCE_REL
    receipt, err = load_json(root, base / "m2_offline_rehearsal_receipt.json")
    repeat, rerr = load_json(root, base / "m2_rehearsal_repeat_check.json")
    if receipt is None:
        node["missing"].append("m2_offline_rehearsal_receipt.json: %s" % err)
        return report["gates"].append(finalize(node))
    node["evidence"].append(str(base / "m2_offline_rehearsal_receipt.json"))
    record(node, "scope_offline", receipt.get("scope") == "OFFLINE_REHEARSAL_ONLY",
           "scope=%r" % receipt.get("scope"))
    record(node, "zero_physical_counters",
           receipt.get("physical_solver_starts_actual") == 0
           and receipt.get("internal_solver_cases_actual") == 0,
           "physical=%r internal=%r" % (
               receipt.get("physical_solver_starts_actual"),
               receipt.get("internal_solver_cases_actual")))
    record(node, "no_real_meta_training",
           receipt.get("real_meta_training_executed") is False
           and receipt.get("admitted_real_labels") == 0,
           "real_meta=%r admitted=%r" % (
               receipt.get("real_meta_training_executed"),
               receipt.get("admitted_real_labels")))
    record(node, "evidence_grade_rehearsal",
           receipt.get("evidence_grade") == "OFFLINE_REHEARSAL_NO_PHYSICAL_EVIDENCE",
           "evidence_grade=%r" % receipt.get("evidence_grade"))
    if repeat is None:
        node["missing"].append("m2_rehearsal_repeat_check.json: %s" % rerr)
    else:
        node["evidence"].append(str(base / "m2_rehearsal_repeat_check.json"))
        fields = ("parameters_sha256_identical", "train_task_ids_identical",
                  "evaluation_identical", "training_reports_identical")
        record(node, "repeat_check_deterministic",
               all(repeat.get(f) is True for f in fields),
               "fields=%r" % {f: repeat.get(f) for f in fields})
        record(node, "repeat_check_zero_physical",
               repeat.get("physical_solver_starts_actual") == 0,
               "physical=%r" % repeat.get("physical_solver_starts_actual"))
    node["blockers"].append("Rehearsal is offline-only; M2 real training awaits real admitted labels")
    report["gates"].append(finalize(node))


def assess_backup(root, report):
    node = new_gate("BACKUP_INDEPENDENT_FAILURE_DOMAIN", "Independent failure-domain backup and restore")
    receipt, err = load_json(root, EVIDENCE_REL / "local_restore_receipt.json")
    waiver, waiver_err = load_json(root, EVIDENCE_REL / "owner_waiver_offmachine_backup_20261118.json")
    waived = bool(isinstance(waiver, dict)
                  and waiver.get("waived") is True
                  and waiver.get("scope") == "OFF_MACHINE_INDEPENDENT_FAILURE_DOMAIN_BACKUP")
    if receipt is None:
        node["missing"].append("local_restore_receipt.json: %s" % err)
        return report["gates"].append(finalize(node))
    node["evidence"].append("docs/evidence/drecover001/local_restore_receipt.json")
    record(node, "local_restore_status",
           receipt.get("status") == "PASS_NOT_REMOTE_BACKUP",
           "status=%r" % receipt.get("status"))
    record(node, "scope_local_only",
           receipt.get("scope") == "LOCAL_SOFTWARE_RESTORE_ONLY",
           "scope=%r" % receipt.get("scope"))
    record(node, "same_host_restore_explicitly_labelled",
           receipt.get("off_machine_backup") is False
           and receipt.get("backup_label") == "SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP",
           "off_machine_backup=%r label=%r" % (
               receipt.get("off_machine_backup"), receipt.get("backup_label")))
    if waived:
        info(node, "owner_waiver_offmachine_backup",
             "waiver_id=%r owner_ref=%r scope=%r" % (
                 waiver.get("waiver_id"), waiver.get("owner_message_ref"), waiver.get("scope")))
        record(node, "independent_failure_domain_absent_but_waived",
               receipt.get("independent_failure_domain") is False,
               "independent_failure_domain=%r" % receipt.get("independent_failure_domain"))
        record(node, "backup_restore_pass_false_under_waiver",
               receipt.get("backup_restore_pass") is False,
               "backup_restore_pass=%r" % receipt.get("backup_restore_pass"))
        node["blockers"].append(
            "Owner waived the off-machine failure-domain backup (%s); same-host restore is "
            "still not an off-machine backup and backup_restore_pass remains false"
            % waiver.get("waiver_id"))
    else:
        record(node, "independent_failure_domain_expected_false",
               receipt.get("independent_failure_domain") is False,
               "independent_failure_domain=%r" % receipt.get("independent_failure_domain"),
               failure="blockers")
        record(node, "backup_restore_pass_expected_false",
               receipt.get("backup_restore_pass") is False,
               "backup_restore_pass=%r" % receipt.get("backup_restore_pass"),
               failure="blockers")
        node["blockers"].append("No off-machine/independent backup receipt exists; same-host copy is not a backup")
        if waiver is not None and not waived:
            info(node, "owner_waiver_rejected", "waiver did not satisfy scope/waived checks: %r"
                 % (waiver.get("scope"),))
    record(node, "no_pass_without_independent_domain",
           not (receipt.get("backup_restore_pass") is True
                and receipt.get("independent_failure_domain") is not True),
           "backup_restore_pass=%r independent=%r" % (
               receipt.get("backup_restore_pass"),
               receipt.get("independent_failure_domain")))
    record(node, "zero_physical_counters",
           receipt.get("physical_solver_starts_actual") == 0,
           "physical=%r" % receipt.get("physical_solver_starts_actual"))
    bundle_path = receipt.get("bundle_path")
    bundle_sha = receipt.get("bundle_sha256")
    if bundle_path:
        candidate = Path(str(bundle_path))
        if candidate.is_file():
            record(node, "bundle_sha_matches_archived_bundle",
                   sha256_file(candidate) == bundle_sha,
                   "recorded=%r actual=%r" % (bundle_sha, sha256_file(candidate)))
        else:
            node["blockers"].append("Restore bundle is not present on this machine at %s" % bundle_path)
    report["gates"].append(finalize(node, waived=waived))


def assess_a5(root, report, preflight, m1_receipt):
    node = new_gate("A5_INDEPENDENT_REVIEW", "Independent 6-terra A5 review")
    verdicts = []
    if preflight and preflight.get("a5_independent_review") not in (None, "NOT_PERFORMED"):
        verdicts.append("preflight=%r" % preflight.get("a5_independent_review"))
    if m1_receipt and m1_receipt.get("a5_independent_review") not in (None, "NOT_PERFORMED"):
        verdicts.append("m1_receipt=%r" % m1_receipt.get("a5_independent_review"))
    record(node, "no_unbacked_a5_approval", not verdicts,
           "unbacked approvals=%r" % verdicts)
    allowed_a5_inputs = {"a5_review_packet.json", "a5_review_packet.md",
                         "build_a5_review_packet.py", "a5_review_verdict.json",
                         "a5_review_transcript.json"}
    found = sorted(p.name for p in (Path(root) / EVIDENCE_REL).glob("*a5*")
                   if p.name not in allowed_a5_inputs)
    record(node, "no_unreviewed_a5_artifact", not found, "a5 artifacts=%r" % found)
    verdict_doc, verdict_err = load_json(root, EVIDENCE_REL / "a5_review_verdict.json")
    if verdict_doc is None:
        node["blockers"].append("No A5 review verdict artifact: independent review NOT_PERFORMED")
    else:
        node["evidence"].append("docs/evidence/drecover001/a5_review_verdict.json")
        record(node, "a5_review_performed", bool(verdict_doc.get("verdict")),
               "verdict=%r reviewer=%r" % (verdict_doc.get("verdict"), verdict_doc.get("reviewer")))
        record(node, "a5_reviewer_is_authorized_subagent",
               verdict_doc.get("reviewer") == "deepseek-flash"
               and "not a human signature" in str(verdict_doc.get("signature", "")),
               "reviewer=%r signature=%r" % (verdict_doc.get("reviewer"), verdict_doc.get("signature")))
        record(node, "a5_verdict_not_an_approval_unless_approve",
               verdict_doc.get("verdict") in ("APPROVE_FOR_R2", "CHANGES_REQUIRED", "REJECT"),
               "verdict=%r" % verdict_doc.get("verdict"))
        node["blockers"].append(
            "A5 review performed by deepseek-flash subagent (not a human signature): verdict=%r; "
            "R2/M1 physics is not authorized by this review" % verdict_doc.get("verdict"))
    report["gates"].append(finalize(node))


def assess_real_admission(root, report, inventory):
    node = new_gate("REAL_ADMISSION", "Real-label admission gate")
    source = Path(root) / "research/concorde_metaopt/dreal001/meta/meta_dataset.py"
    if not source.is_file():
        node["missing"].append("meta_dataset.py is missing")
        return report["gates"].append(finalize(node))
    node["evidence"].append("research/concorde_metaopt/dreal001/meta/meta_dataset.py")
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        node["violations"].append("meta_dataset.py unparseable: %s" % exc)
        return report["gates"].append(finalize(node))
    fail_closed = False
    for item in ast.walk(tree):
        if isinstance(item, ast.FunctionDef) and item.name == "require_real_admission":
            for inner in ast.walk(item):
                if isinstance(inner, ast.Raise) and inner.exc is not None:
                    text = ast.dump(inner.exc)
                    if "REAL_ADMISSION_NOT_IMPLEMENTED" in text:
                        fail_closed = True
    record(node, "require_real_admission_fails_closed", fail_closed,
           "raise ContractError(REAL_ADMISSION_NOT_IMPLEMENTED) found=%r" % fail_closed)
    protocol = Path(root) / "research/concorde_metaopt/dreal001/meta/real_admission.py"
    tests = (Path(root) / "research/concorde_metaopt/tests/"
             "test_recovery_real_admission.py")
    if protocol.is_file():
        node["evidence"].append(
            "research/concorde_metaopt/dreal001/meta/real_admission.py")
        try:
            protocol_text = protocol.read_text(encoding="utf-8")
            protocol_tree = ast.parse(protocol_text)
        except (OSError, SyntaxError) as exc:
            node["violations"].append("real_admission.py unparseable: %s" % exc)
        else:
            names = {item.name for item in ast.walk(protocol_tree)
                     if isinstance(item, (ast.ClassDef, ast.FunctionDef))}
            required = {"RealAdmissionManifest", "AdmissionCertificate",
                        "admit_real_manifest", "artifact_sha256"}
            record(node, "admission_protocol_defines_required_api",
                   required <= names,
                   "missing=%s" % sorted(required - names))
            record(node, "admission_certificate_is_issuer_minted",
                   "_ISSUER" in protocol_text
                   and "_issuer is not _ISSUER" in protocol_text
                   and "EVIDENCE_SCOPE" in protocol_text,
                   "issuer guard and evidence scope present")
            record(node, "admission_success_path_verifies_real_raw",
                   "verify_artifact_bundle" in protocol_text
                   and "candidate.real_admission" in protocol_text,
                   "delegates to raw verification and rejects self-admitted candidates")
            if tests.is_file():
                node["evidence"].append(
                    "research/concorde_metaopt/tests/test_recovery_real_admission.py")
                test_text = tests.read_text(encoding="utf-8")
                try:
                    test_tree = ast.parse(test_text)
                except SyntaxError as exc:
                    node["violations"].append(
                        "test_recovery_real_admission.py unparseable: %s" % exc)
                else:
                    test_names = {item.name for item in ast.walk(test_tree)
                                  if isinstance(item, ast.FunctionDef)
                                  and item.name.startswith("test_")}
                    record(node, "admission_success_and_refusal_paths_tested",
                           any("success" in name for name in test_names)
                           and any("missing" in name for name in test_names)
                           and any("failed" in name for name in test_names)
                           and len(test_names) >= 10,
                           "tests=%d" % len(test_names))
            else:
                info(node, "admission_tests_not_present_in_this_tree",
                     "test_recovery_real_admission.py absent")
    else:
        info(node, "admission_protocol_not_present_in_this_tree",
             "real_admission.py absent")
    raw_verification = (Path(root) / "research/concorde_metaopt/dreal001/meta/"
                        "raw_verification.py")
    raw_text = (raw_verification.read_text(encoding="utf-8")
                if raw_verification.is_file() else "")
    safe_flag = ("real_admission=False" in raw_text
                 or "real_admission: bool = False" in raw_text)
    unsafe_flag = ("real_admission=True" in raw_text
                   or "real_admission = True" in raw_text)
    record(node, "raw_candidate_is_not_self_admitted", safe_flag and not unsafe_flag,
           "raw_verification keeps real_admission=False")
    admitted = (inventory or {}).get("admitted_scientific_labels_this_recovery")
    record(node, "no_admitted_scientific_labels", admitted == 0,
           "admitted=%r" % admitted)
    node["blockers"].append("No real raw artifact has been admitted or independently audited; "
                            "the protocol is fixture-tested only")
    report["gates"].append(finalize(node))


def assess_manifest(root, report):
    node = new_gate("EVIDENCE_MANIFEST", "Recovery change manifest freshness")
    relative = EVIDENCE_REL / "recovery_change_manifest.json"
    manifest, err = load_json(root, relative)
    if manifest is None:
        node["missing"].append("recovery_change_manifest.json: %s" % err)
        return report["gates"].append(finalize(node))
    node["evidence"].append(str(relative))
    parse_bad = []
    for current_json in (EVIDENCE_REL / "needed_for_next_run.json",
                         EVIDENCE_REL / "recovery_inventory.json"):
        parsed, parse_err = load_json(root, current_json)
        if parsed is None:
            parse_bad.append("%s: %s" % (current_json.as_posix(), parse_err))
    record(node, "current_state_json_parses", not parse_bad,
           "invalid=%d %s" % (len(parse_bad), parse_bad[:3]))
    files = manifest.get("files")
    record(node, "manifest_is_non_empty", isinstance(files, list) and len(files) > 0,
           "entries=%r" % (len(files) if isinstance(files, list) else None))
    if not isinstance(files, list):
        return report["gates"].append(finalize(node))
    record(node, "manifest_file_count_consistent",
           manifest.get("file_count") == len(files),
           "file_count=%r entries=%d" % (manifest.get("file_count"), len(files)))
    stale, missing = [], []
    total = 0
    for entry in files:
        name = entry.get("path")
        if not name:
            continue
        candidate = Path(root) / name
        if not candidate.is_file():
            missing.append(name)
            continue
        data = candidate.read_bytes()
        total += len(data)
        if sha256_bytes(data) != entry.get("sha256"):
            stale.append(name)
        elif entry.get("bytes") not in (None, len(data)):
            stale.append(name)
    record(node, "manifest_paths_exist", not missing,
           "missing=%d %s" % (len(missing), missing[:5]))
    record(node, "manifest_hashes_current", not stale,
           "stale=%d %s" % (len(stale), stale[:5]))
    record(node, "manifest_total_bytes_consistent",
           manifest.get("total_bytes") == total,
           "recorded=%r actual=%d" % (manifest.get("total_bytes"), total))
    toplevel, top_err = _git(root, ["rev-parse", "--show-toplevel"])
    if toplevel is None or Path(toplevel).resolve() != root:
        info(node, "manifest_completeness_not_checked",
             "root is not a git worktree top level: %r" % top_err)
    else:
        status_text, status_err = _git_raw(root, ["status", "--porcelain=v1", "-z",
                                                  "--untracked-files=all"])
    if toplevel is None or Path(toplevel).resolve() != root:
        info(node, "manifest_completeness_not_checked",
             "root is not a git worktree top level: %r" % top_err)
    elif status_text is None:
        info(node, "manifest_completeness_not_checked",
             "git status unavailable: %r" % status_err)
    else:
        dirty = _status_paths(status_text)
        listed = {entry.get("path") for entry in files}
        unlisted = sorted(dirty - listed)
        ghosts = sorted(listed - dirty)
        record(node, "manifest_covers_worktree", not unlisted,
               "unlisted=%d %s" % (len(unlisted), unlisted[:5]))
        record(node, "manifest_has_no_ghost_entries", not ghosts,
               "ghosts=%d %s" % (len(ghosts), ghosts[:5]))
    return report["gates"].append(finalize(node, clean=True))


def assess(root):
    root = Path(root).resolve()
    report = {"schema": "drecover001.recovery_readiness.v1",
              "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "root": str(root), "gates": []}
    head, head_err = _git(root, ["rev-parse", "HEAD"])
    branch, _ = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    status_text, _ = _git(root, ["status", "--porcelain=v1"])
    report["git"] = {"head": head, "branch": branch,
                     "dirty_paths": len([l for l in (status_text or "").splitlines() if l.strip()]),
                     "head_error": head_err}
    email, email_err = _git(root, ["config", "user.email"])
    report["git"]["author_email_configured"] = bool(email)
    report["git"]["author_email_error"] = email_err
    preflight, perr = load_json(root, EVIDENCE_REL / "recovery_preflight_receipt.json")
    if preflight is None:
        report["preflight_error"] = perr
    inventory, _ = load_json(root, EVIDENCE_REL / "recovery_inventory.json")
    m1_receipt, _ = load_json(root, EVIDENCE_REL / "m1_batch_software_rehearsal_receipt.json")
    assess_r0(root, report)
    assess_geometry_freeze(root, report)
    assess_r1(root, report, preflight)
    assess_m1(root, report)
    assess_m2(root, report)
    assess_backup(root, report)
    assess_a5(root, report, preflight, m1_receipt)
    assess_real_admission(root, report, inventory)
    assess_manifest(root, report)
    violations = ["%s: %s" % (g["id"], v) for g in report["gates"] for v in g["violations"]]
    missing = ["%s: %s" % (g["id"], v) for g in report["gates"] for v in g["missing"]]
    blockers = sorted({b for g in report["gates"] for b in g["blockers"]})
    report["counts"] = {"gates": len(report["gates"]),
                        "clean": sum(1 for g in report["gates"] if g["state"] == "CLEAN"),
                        "closed": sum(1 for g in report["gates"] if g["state"] == "CLOSED"),
                        "waived": sum(1 for g in report["gates"] if g["state"] == "WAIVED"),
                        "unknown": sum(1 for g in report["gates"] if g["state"] == "UNKNOWN"),
                        "conflict": sum(1 for g in report["gates"] if g["state"] == "CONFLICT"),
                        "violations": len(violations), "missing": len(missing),
                        "blockers": len(blockers)}
    report["violations"] = violations
    report["missing_evidence"] = missing
    report["blockers"] = blockers
    report["software_run_id"] = (preflight or {}).get("run_id")
    report["physical_solver_starts_actual"] = 0
    report["internal_solver_cases_actual"] = 0
    report["real_meta_training_executed"] = False
    report["admitted_real_labels"] = 0
    report["ready_for_physical"] = False
    report["ready_for_real_meta_training"] = False
    report["status"] = ("RECOVERY_READINESS_GATES_CLOSED_EXPECTED"
                        if not violations and not missing else "ATTENTION_REQUIRED")
    report["disclosure"] = ("Offline evidence aggregation only. No solver start, no network, no "
                            "new physical evidence, no A5 signature. A CLOSED gate is expected and "
                            "is not a PASS.")
    return report


def render_markdown(report):
    lines = ["# 恢复门禁就绪矩阵（离线聚合）", "",
             "- status: %s" % report["status"],
             "- generated_utc: %s" % report["generated_utc"],
             "- HEAD: %s (%s)" % (report["git"].get("head"), report["git"].get("branch")),
             "- software_run_id: %s" % report["software_run_id"],
             "- physical_solver_starts_actual: 0 / internal_solver_cases_actual: 0",
             "- real_meta_training_executed: false / admitted_real_labels: 0", "",
             "| gate | state | blockers | violations |", "| --- | --- | --- | --- |"]
    for gate in report["gates"]:
        lines.append("| %s | %s | %d | %d |" % (gate["id"], gate["state"],
                                                len(gate["blockers"]), len(gate["violations"])))
    lines += ["", "## 阻断项"]
    lines += ["- %s" % b for b in report["blockers"]] or ["- （无）"]
    if report["violations"]:
        lines += ["", "## 证据矛盾（必须修复）"]
        lines += ["- %s" % v for v in report["violations"]]
    if report["missing_evidence"]:
        lines += ["", "## 缺失证据"]
        lines += ["- %s" % v for v in report["missing_evidence"]]
    lines += ["", "## 说明", report["disclosure"], ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--out", default=None)
    parser.add_argument("--md", default=None)
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else Path(args.root) / EVIDENCE_REL / "recovery_readiness.json"
    md = Path(args.md) if args.md else Path(args.root) / EVIDENCE_REL / "recovery_readiness.md"
    report = assess(args.root)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "software_run_id": report["software_run_id"]}, indent=2))
    return 0 if report["status"] == "RECOVERY_READINESS_GATES_CLOSED_EXPECTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())