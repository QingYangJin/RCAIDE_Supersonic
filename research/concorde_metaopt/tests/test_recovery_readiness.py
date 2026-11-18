"""Offline tests for the recovery readiness aggregator. No solver, no physics."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
# The fixture tree is pre-created on disk because the host sandbox denies
# mkdir() below a directory created at runtime. Tests only write files and
# remove them again; they never create directories.
FIXTURE_ROOT = ROOT / "research/concorde_metaopt/tests/_readiness_fixture"
MODULE_PATH = ROOT / "docs/evidence/drecover001/assess_recovery_readiness.py"
_spec = importlib.util.spec_from_file_location("assess_recovery_readiness", MODULE_PATH)
readiness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(readiness)

RUN_ID = "DRECOVER001-SOFTWARE-20261117T120000Z"
OLD_RUN_ID = "DRECOVER001-SOFTWARE-20261117T101159Z"
PLACEHOLDER = "STRUCTURAL_SOFTWARE_FIXTURE_NOT_A_REAL_GO"
ZERO_SHA = "0" * 64


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Fixture:
    def __init__(self, root):
        self.root = Path(root)
        self.ev = self.root / "docs/evidence/drecover001"
        self.ev.mkdir(parents=True, exist_ok=True)

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_json(self, relative, value):
        return self.write(relative, json.dumps(value, indent=2).encode("utf-8"))

    def read_json(self, relative):
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def build(self):
        source_rel = "pkg/source.py"
        source = b"value = 1\n"
        self.write(source_rel, source)
        trace = b"{}\n"
        self.write("docs/evidence/drecover001/synthetic_software_training_trace.json", trace)
        self.write("docs/evidence/drecover001/all_ref_blob_audit.json", b"{}")
        self.write("docs/evidence/drecover001/reachable_history_audit.json", b"{}")
        ext_rel = "docs/evidence/drecover001/r0_provenance_extension.json"
        ext = {"schema": "fixture"}
        self.write(ext_rel, json.dumps(ext).encode())
        script_rel = "docs/evidence/drecover001/audit_provenance_extension.py"
        script = b"# fixture audit\n"
        self.write(script_rel, script)
        self.write_json("docs/evidence/drecover001/r0_provenance_extension_verification.json", {
            "status": "R0_PROVENANCE_EXTENSION_EVIDENCE_INTERNALLY_CONSISTENT",
            "check_count": 328, "failure_count": 0, "failures": [],
            "extension": ext_rel, "extension_sha256": sha(json.dumps(ext).encode()),
            "script": script_rel, "script_sha256": sha(script)})
        self.write_json("docs/evidence/drecover001/recovery_inventory.json", {
            "status": "R0_PARTIAL_NOT_AUDITED",
            "gate_verdict": "NOT_SIGNED_R0_INCOMPLETE",
            "independent_review": {"status": "NOT_STARTED"},
            "physical_solver_starts_actual_this_recovery": 0,
            "internal_solver_cases_actual_this_recovery": 0,
            "admitted_scientific_labels_this_recovery": 0,
            "byte_audit": {"evidence": "docs/evidence/drecover001/all_ref_blob_audit.json",
                           "raw_git_object_identity_verified": True},
            "reachable_history": {"reachable_commits": 200,
                                  "evidence": "docs/evidence/drecover001/reachable_history_audit.json"},
            "r0_provenance_extension": {"sha256": sha(json.dumps(ext).encode())}})
        self.write_json("docs/evidence/drecover001/needed_for_next_run.json",
                         {"schema": "fixture", "status": "NO_PHYSICAL_GO"})
        artifact_rel = "docs/evidence/drecover001/geometry_freeze_v2_artifacts/fixture.vsp3"
        artifact = b"fixture-vsp3-bytes"
        self.write(artifact_rel, artifact)
        freeze = {
            "status": "GEOMETRY_FREEZE_V2_ISSUED_ZERO_PHYSICAL",
            "scope": "GEOMETRY_AND_REFERENCE_CONTRACT_ONLY_NO_AERODYNAMIC_VALIDATION",
            "freeze_id": "GBFREEZE2-fixture",
            "geometry_contract_sha256": "d" * 64,
            "physical_solver_starts_actual": 0,
            "internal_solver_cases_actual": 0,
            "consistency_checks": [{"name": "fixture", "ok": True}],
            "boundary_perturbation": {"all_ok": True, "model_cases_ok": 24,
                                      "native_cases_ok": 24, "native_cases_total": 24},
            "real_openvsp_export": {"exports": {
                "vsp3": {"path": artifact_rel, "bytes": len(artifact),
                         "sha256": sha(artifact)}}}}
        freeze_bytes = json.dumps(freeze, indent=2).encode("utf-8")
        self.write("docs/evidence/drecover001/geometry_freeze_v2.json", freeze_bytes)
        verification = {"status": "GEOMETRY_FREEZE_V2_VERIFIED", "check_count": 101,
                        "failure_count": 0, "failures": []}
        verification_bytes = json.dumps(verification, indent=2).encode("utf-8")
        self.write("docs/evidence/drecover001/geometry_freeze_v2_verification.json",
                   verification_bytes)
        self.write_json("docs/evidence/drecover001/new_baseline_manifest.json", {
            "schema": "drecover001.new_baseline_manifest.v1",
            "base_commit": "e" * 40,
            "historical_data_policy": {
                "status": "RAW_LOST_ARCHIVED",
                "search_policy": "STOPPED_NO_FURTHER_HISTORY_RECOVERY_SEARCH"},
            "identity_policy": {"new_physical_runs_require": [
                "new_geometry_sha256", "RealAdmissionManifest", "fresh Lead batch GO"]},
            "physical_solver_starts_actual": 0,
            "internal_solver_cases_actual": 0,
            "admitted_scientific_labels": 0,
            "geometry_freeze_status": {
                "status": freeze["status"], "freeze_id": freeze["freeze_id"],
                "current_geometry_contract_sha256": freeze["geometry_contract_sha256"],
                "freeze_json_sha256": sha(freeze_bytes),
                "verification_sha256": sha(verification_bytes)}})
        self.write_json("docs/evidence/drecover001/recovery_preflight_receipt.json", {
            "run_id": RUN_ID, "tests_run": 205, "failures": 0, "errors": 0, "skipped": 0,
            "software_tests_status": "PASS",
            "physical_solver_starts_actual_this_recovery": 0,
            "internal_solver_cases_actual_this_recovery": 0,
            "real_meta_training_executed": False, "admitted_real_labels": 0,
            "a5_independent_review": "NOT_PERFORMED", "physical_go": "NOT_ISSUED",
            "backup_restore": "NOT_ESTABLISHED",
            "training_status": "SOFTWARE_FIXTURE_TRAINING_ONLY",
            "training_steps_per_model": 20,
            "parameter_l2_change_from_initial": {"fomaml": 0.1, "pretrain": 0.2},
            "synthetic_checkpoint_sha256": "a" * 64,
            "synthetic_training_trace_sha256": sha(trace),
            "source_sha256": {source_rel: sha(source)}})
        result_sha = "b" * 64
        plan_sha = "c" * 64
        self.write_json("docs/evidence/drecover001/m1_batch_software_rehearsal_receipt.json", {
            "scope": "OFFLINE_BATCH_SKELETON_ONLY", "authorization_kind": PLACEHOLDER,
            "a5_independent_review": "NOT_PERFORMED", "result_status": "COMPLETE",
            "result_sha256": result_sha, "plan_sha256": plan_sha,
            "admitted_real_labels": 0})
        self.write_json("docs/evidence/drecover001/m1_batch_software_result.json", {
            "status": "COMPLETE", "evidence_grade": "SOFTWARE_CONTROL_PATH_ONLY",
            "result_sha256": result_sha, "plan_sha256": plan_sha,
            "accounting": {"physical_solver_starts_actual": 0,
                           "simulated_solver_starts_actual": 18,
                           "starts_issued": 18, "charged_planned_reserved": 18,
                           "planned_reserved": 18, "internal_solver_cases_actual": 126},
            "controls": {"physical_go": True,
                         "a5_verdict": "R2_FIXED_LOOP_GATE_APPROVED_WITH_DISCLOSURE"}})
        self.write_json("docs/evidence/drecover001/m1_batch_software_verification.json", {
            "status": "M1_BATCH_EVIDENCE_INTERNALLY_CONSISTENT", "failures": []})
        self.write_json("docs/evidence/drecover001/m2_offline_rehearsal_receipt.json", {
            "scope": "OFFLINE_REHEARSAL_ONLY", "physical_solver_starts_actual": 0,
            "internal_solver_cases_actual": 0, "real_meta_training_executed": False,
            "admitted_real_labels": 0,
            "evidence_grade": "OFFLINE_REHEARSAL_NO_PHYSICAL_EVIDENCE"})
        self.write_json("docs/evidence/drecover001/m2_rehearsal_repeat_check.json", {
            "parameters_sha256_identical": True, "train_task_ids_identical": True,
            "evaluation_identical": True, "training_reports_identical": True,
            "physical_solver_starts_actual": 0})
        self.write_json("docs/evidence/drecover001/a2_feedback_rehearsal.json", {
            "schema": "drecover001.a2_feedback_rehearsal.v1",
            "scope": "SOFTWARE_FEEDBACK_REHEARSAL_ONLY_NOT_PHYSICAL_EVIDENCE",
            "physical_solver_starts_actual": 0,
            "baseline": {"status": "COMPLETED", "evaluations_requested": 6,
                         "valid_evals": 6, "simulated_solver_starts": 6,
                         "physical_solver_starts": 0},
            "counterfactual": {"first_two_proposals_identical": True,
                               "third_proposal_differs": True},
            "failed_objective_branch": {"first_row_status": "FAIL",
                                        "first_row_valid": False,
                                        "first_row_objective_D_i_N": None}})
        bundle = b"fixture-bundle"
        bundle_path = self.root / "backup" / "bundle.bin"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_bytes(bundle)
        self.write_json("docs/evidence/drecover001/local_restore_receipt.json", {
            "status": "PASS_NOT_REMOTE_BACKUP", "scope": "LOCAL_SOFTWARE_RESTORE_ONLY",
            "independent_failure_domain": False, "backup_restore_pass": False,
            "off_machine_backup": False,
            "backup_label": "SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP",
            "physical_solver_starts_actual": 0,
            "bundle_path": str(bundle_path), "bundle_sha256": sha(bundle)})
        self.write("research/concorde_metaopt/dreal001/meta/meta_dataset.py", b'''class ContractError(Exception):
    pass


def require_real_admission(dataset):
    raise ContractError("REAL_ADMISSION_NOT_IMPLEMENTED: independent gates required")
''')
        self.write("research/concorde_metaopt/dreal001/meta/real_admission.py", b'''EVIDENCE_SCOPE = "FIXTURE_ONLY"
_ISSUER = object()


class RealAdmissionManifest:
    pass


class AdmissionCertificate:
    def __post_init__(self):
        if self._issuer is not _ISSUER:
            raise ValueError("issuer")


def artifact_sha256(files):
    return ""


def admit_real_manifest(**kwargs):
    verify_artifact_bundle(**kwargs)
    return candidate.real_admission
''')
        self.write("research/concorde_metaopt/dreal001/meta/raw_verification.py",
                   b"CANDIDATE = dict(real_admission=False)\n")
        self.write("research/concorde_metaopt/tests/test_recovery_real_admission.py", b'''class T:
    def test_success_admission(self):
        pass

    def test_failed_outcome(self):
        pass

    def test_missing_file(self):
        pass

    def test_tampered_file(self):
        pass

    def test_path_escape(self):
        pass

    def test_bad_design(self):
        pass

    def test_bad_audit(self):
        pass

    def test_certificate_tamper(self):
        pass

    def test_dataset_coverage(self):
        pass

    def test_no_lift_row(self):
        pass
''')
        self.write("docs/evidence/drecover001/recovery_inventory.md", ("run_id: " + RUN_ID + "\n").encode())
        target = self.ev / "recovery_inventory.md"
        data = target.read_bytes()
        self.write_json("docs/evidence/drecover001/recovery_change_manifest.json", {
            "file_count": 1, "total_bytes": len(data),
            "files": [{"path": "docs/evidence/drecover001/recovery_inventory.md",
                       "sha256": sha(data), "bytes": len(data)}]})
        return self

    def gate(self, report, gate_id):
        return next(item for item in report["gates"] if item["id"] == gate_id)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        if not FIXTURE_ROOT.is_dir():
            raise RuntimeError("fixture skeleton is missing: %s" % FIXTURE_ROOT)
        self._purge()
        self.fx = Fixture(FIXTURE_ROOT).build()

    def tearDown(self):
        self._purge()

    @staticmethod
    def _purge():
        for path in sorted(FIXTURE_ROOT.rglob("*"), reverse=True):
            if path.is_file() and path.name != ".gitkeep":
                path.unlink()

    def test_clean_fixture_keeps_gates_closed_and_flags_zero_physical(self):
        report = readiness.assess(self.fx.root)
        self.assertEqual(report["status"], "RECOVERY_READINESS_GATES_CLOSED_EXPECTED")
        self.assertEqual(report["violations"], [])
        self.assertEqual(report["missing_evidence"], [])
        self.assertEqual(report["physical_solver_starts_actual"], 0)
        self.assertEqual(report["internal_solver_cases_actual"], 0)
        self.assertFalse(report["ready_for_physical"])
        self.assertFalse(report["ready_for_real_meta_training"])
        states = {gate["id"]: gate["state"] for gate in report["gates"]}
        self.assertEqual(states["EVIDENCE_MANIFEST"], "CLEAN")
        for gate_id in ("R0_INVENTORY", "R1_SOFTWARE", "M1_BATCH_CONTROL_PATH",
                        "M2_OFFLINE_REHEARSAL", "BACKUP_INDEPENDENT_FAILURE_DOMAIN",
                        "A5_INDEPENDENT_REVIEW", "REAL_ADMISSION"):
            self.assertEqual(states[gate_id], "CLOSED", gate_id)

    def test_physical_counter_is_a_conflict_not_a_pass(self):
        preflight = self.fx.read_json("docs/evidence/drecover001/recovery_preflight_receipt.json")
        preflight["physical_solver_starts_actual_this_recovery"] = 1
        self.fx.write_json("docs/evidence/drecover001/recovery_preflight_receipt.json", preflight)
        report = readiness.assess(self.fx.root)
        self.assertEqual(report["status"], "ATTENTION_REQUIRED")
        self.assertEqual(self.fx.gate(report, "R1_SOFTWARE")["state"], "CONFLICT")

    def test_stale_current_document_run_id_is_a_conflict(self):
        self.fx.write("docs/evidence/drecover001/recovery_inventory.md",
                      ("run_id: " + OLD_RUN_ID + "\n").encode())
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "R1_SOFTWARE")["state"], "CONFLICT")
        self.assertTrue(any("software_run_id" in item for item in report["violations"]))

    def test_invalid_current_state_json_is_a_conflict(self):
        self.fx.write("docs/evidence/drecover001/needed_for_next_run.json", b"{not json")
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "EVIDENCE_MANIFEST")["state"], "CONFLICT")
        self.assertTrue(any("current_state_json_parses" in item for item in report["violations"]))

    def test_stale_manifest_hash_is_a_conflict(self):
        self.fx.write("docs/evidence/drecover001/recovery_inventory.md", b"changed\n")
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "EVIDENCE_MANIFEST")["state"], "CONFLICT")
        self.assertTrue(any("manifest_hashes_current" in item for item in report["violations"]))

    def test_source_drift_after_preflight_is_a_conflict(self):
        self.fx.write("pkg/source.py", b"value = 2\n")
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "R1_SOFTWARE")["state"], "CONFLICT")
        self.assertTrue(any("recorded_sources_still_current" in item for item in report["violations"]))

    def test_unbacked_a5_approval_is_a_conflict(self):
        preflight = self.fx.read_json("docs/evidence/drecover001/recovery_preflight_receipt.json")
        preflight["a5_independent_review"] = "APPROVED"
        self.fx.write_json("docs/evidence/drecover001/recovery_preflight_receipt.json", preflight)
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "A5_INDEPENDENT_REVIEW")["state"], "CONFLICT")

    def test_backup_pass_without_independent_domain_is_a_conflict(self):
        receipt = self.fx.read_json("docs/evidence/drecover001/local_restore_receipt.json")
        receipt["backup_restore_pass"] = True
        self.fx.write_json("docs/evidence/drecover001/local_restore_receipt.json", receipt)
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "BACKUP_INDEPENDENT_FAILURE_DOMAIN")["state"], "CONFLICT")

    def test_owner_waiver_marks_backup_gate_waived_not_pass(self):
        self.fx.write_json("docs/evidence/drecover001/owner_waiver_offmachine_backup_20261118.json", {
            "waiver_id": "WAIVER-FIXTURE", "scope": "OFF_MACHINE_INDEPENDENT_FAILURE_DOMAIN_BACKUP",
            "waived": True})
        report = readiness.assess(self.fx.root)
        self.assertEqual(report["violations"], [])
        gate = self.fx.gate(report, "BACKUP_INDEPENDENT_FAILURE_DOMAIN")
        self.assertEqual(gate["state"], "WAIVED")
        self.assertTrue(any("waived" in item for item in gate["blockers"]))

    def test_real_admission_must_remain_fail_closed(self):
        self.fx.write("research/concorde_metaopt/dreal001/meta/meta_dataset.py",
                      b"def require_real_admission(dataset):\n    return dataset\n")
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "REAL_ADMISSION")["state"], "CONFLICT")

    def test_m1_placeholder_gate_claims_require_disclosure(self):
        receipt = self.fx.read_json("docs/evidence/drecover001/m1_batch_software_rehearsal_receipt.json")
        receipt["authorization_kind"] = "REAL_GO"
        self.fx.write_json("docs/evidence/drecover001/m1_batch_software_rehearsal_receipt.json", receipt)
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "M1_BATCH_CONTROL_PATH")["state"], "CONFLICT")

    def test_manifest_missing_entry_is_a_conflict(self):
        manifest = self.fx.read_json("docs/evidence/drecover001/recovery_change_manifest.json")
        manifest["files"].append({"path": "docs/evidence/drecover001/ghost.md",
                                  "sha256": ZERO_SHA, "bytes": 1})
        manifest["file_count"] += 1
        manifest["total_bytes"] += 1
        self.fx.write_json("docs/evidence/drecover001/recovery_change_manifest.json", manifest)
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "EVIDENCE_MANIFEST")["state"], "CONFLICT")

    def test_status_parser_keeps_leading_space_of_first_entry(self):
        paths = readiness._status_paths(" M research/x.py\0?? research/y.py\0")
        self.assertEqual(paths, {"research/x.py", "research/y.py"})

    def test_a5_review_packet_is_an_input_not_a_verdict(self):
        self.fx.write("docs/evidence/drecover001/a5_review_packet.json", b"{}")
        self.fx.write("docs/evidence/drecover001/a5_review_packet.md", b"# input\n")
        self.fx.write("docs/evidence/drecover001/build_a5_review_packet.py", b"# generator\n")
        report = readiness.assess(self.fx.root)
        self.assertEqual(self.fx.gate(report, "A5_INDEPENDENT_REVIEW")["state"], "CLOSED")
        self.assertEqual(report["violations"], [])


if __name__ == "__main__":
    unittest.main()