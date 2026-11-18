"""Build a read-only A5 review packet from existing recovery evidence.

This script starts no solver, performs no network I/O, signs nothing, and does
not create new scientific evidence. It only aggregates evidence that already
exists, re-hashes it, and states what an independent A5 reviewer must check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EV = "docs/evidence/drecover001"
EXPECTED_READINESS = "RECOVERY_READINESS_GATES_CLOSED_EXPECTED"
PACKET_JSON = "a5_review_packet.json"
PACKET_MD = "a5_review_packet.md"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(root: Path) -> tuple[dict, list[str]]:
    root = Path(root)
    ev = root / EV
    problems: list[str] = []
    readiness = load_json(ev / "recovery_readiness.json")
    preflight = load_json(ev / "recovery_preflight_receipt.json")
    inventory = load_json(ev / "recovery_inventory.json")
    manifest = load_json(ev / "recovery_change_manifest.json")
    waiver = load_json(ev / "owner_waiver_offmachine_backup_20261118.json")
    a5_verdict = load_json(ev / "a5_review_verdict.json")

    gates = {g["id"]: g["state"] for g in readiness.get("gates", [])}
    if readiness.get("status") != EXPECTED_READINESS:
        problems.append("readiness status is " + repr(readiness.get("status")))
    if gates.get("EVIDENCE_MANIFEST") != "CLEAN":
        problems.append("EVIDENCE_MANIFEST gate is not CLEAN")
    bad = {k: v for k, v in gates.items() if v not in ("CLEAN", "CLOSED", "WAIVED")}
    if bad:
        problems.append("unexpected gate states: " + repr(bad))
    for key in ("physical_solver_starts_actual", "internal_solver_cases_actual",
                "admitted_real_labels"):
        if readiness.get(key) != 0:
            problems.append(key + " is " + repr(readiness.get(key)) + ", expected 0")
    if readiness.get("real_meta_training_executed") is not False:
        problems.append("real_meta_training_executed is not false")
    for key, expected in (("a5_independent_review", "NOT_PERFORMED"),
                          ("physical_go", "NOT_ISSUED"),
                          ("backup_restore", "NOT_ESTABLISHED")):
        if preflight.get(key) != expected:
            problems.append("preflight " + key + " is " + repr(preflight.get(key)))
    if preflight.get("run_id") != readiness.get("software_run_id"):
        problems.append("preflight run_id differs from readiness software_run_id")
    if preflight.get("training_status") != "SOFTWARE_FIXTURE_TRAINING_ONLY":
        problems.append("training_status is not SOFTWARE_FIXTURE_TRAINING_ONLY")
    if preflight.get("real_meta_training_executed") is not False:
        problems.append("preflight real_meta_training_executed is not false")
    if preflight.get("physical_solver_starts_actual_this_recovery") != 0:
        problems.append("preflight physical starts are not 0")
    if preflight.get("internal_solver_cases_actual_this_recovery") != 0:
        problems.append("preflight internal cases are not 0")
    if inventory.get("status") != "R0_PARTIAL_NOT_AUDITED":
        problems.append("inventory status is not R0_PARTIAL_NOT_AUDITED")
    if inventory.get("independent_review", {}).get("status") != "NOT_STARTED":
        problems.append("inventory independent review is not NOT_STARTED")

    entries = [
        ("recovery_inventory.json", "R0 loss ledger and provenance inventory", "R0_INVENTORY"),
        ("recovery_inventory.md", "R0 human-readable inventory", "R0_INVENTORY"),
        ("all_ref_blob_audit.json", "R0 remote-ref byte/blob audit", "R0_INVENTORY"),
        ("reachable_history_audit.json", "R0 reachable-history audit", "R0_INVENTORY"),
        ("r0_provenance_extension.json", "R0 provenance extension records", "R0_INVENTORY"),
        ("r0_provenance_extension_20261117.md", "R0 provenance extension summary", "R0_INVENTORY"),
        ("r0_provenance_extension_verification.json", "R0 archived-byte self-verification", "R0_INVENTORY"),
        ("needed_for_next_run.json", "R0/R1/R2 handoff requirements", "R0_INVENTORY"),
        ("new_baseline_manifest.json", "R0 new-baseline identity and RAW_LOST archive policy", "R0_INVENTORY"),
        ("geometry_freeze_v2.json", "A1 geometry/reference contract freeze v2 (zero physical)", "A1_GEOMETRY_FREEZE_V2"),
        ("geometry_freeze_v2.md", "A1 human-readable geometry freeze v2", "A1_GEOMETRY_FREEZE_V2"),
        ("geometry_freeze_v2_verification.json", "A1 archived-byte geometry freeze verification", "A1_GEOMETRY_FREEZE_V2"),
        ("geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.vsp3", "A1 real OpenVSP 3.55 model export", "A1_GEOMETRY_FREEZE_V2"),
        ("geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.stl", "A1 real OpenVSP assembly STL export", "A1_GEOMETRY_FREEZE_V2"),
        ("geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.step", "A1 real OpenVSP STEP export", "A1_GEOMETRY_FREEZE_V2"),
        ("geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2_main_wing.stl", "A1 main-wing STL component placement artifact", "A1_GEOMETRY_FREEZE_V2"),
        ("geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2_vertical_tail.stl", "A1 vertical-tail STL component placement artifact", "A1_GEOMETRY_FREEZE_V2"),
        ("geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2_fuselage.stl", "A1 fuselage STL component placement artifact", "A1_GEOMETRY_FREEZE_V2"),
        ("recovery_preflight_receipt.json", "R1 software preflight receipt", "R1_SOFTWARE"),
        ("a2_feedback_rehearsal.json", "A2 executable BO feedback rehearsal (software only, zero physical)", "R1_SOFTWARE"),
        ("run_a2_feedback_rehearsal.py", "A2 rehearsal generator over the real ArmHarness/GP-BO path", "R1_SOFTWARE"),
        ("../../../research/concorde_metaopt/dreal001/meta/real_admission.py", "A3 real-admission manifest/certificate protocol", "REAL_ADMISSION"),
        ("../../../research/concorde_metaopt/tests/test_recovery_real_admission.py", "A3 real-admission fixture tests (synthetic bytes)", "REAL_ADMISSION"),
        ("synthetic_software_training_trace.json", "R1 fixture training trace", "R1_SOFTWARE"),
        ("synthetic_software_checkpoint.json", "R1 fixture checkpoint roundtrip artifact", "R1_SOFTWARE"),
        ("m1_batch_software_rehearsal_receipt.json", "M1 control-path rehearsal receipt", "M1_BATCH_CONTROL_PATH"),
        ("m1_batch_software_result.json", "M1 control-path result", "M1_BATCH_CONTROL_PATH"),
        ("m1_batch_software_verification.json", "M1 artifact verification", "M1_BATCH_CONTROL_PATH"),
        ("m2_offline_rehearsal_receipt.json", "M2 offline rehearsal receipt", "M2_OFFLINE_REHEARSAL"),
        ("m2_rehearsal_repeat_check.json", "M2 repeatability check", "M2_OFFLINE_REHEARSAL"),
        ("local_restore_receipt.json", "same-host restore test explicitly labelled not an off-machine backup", "BACKUP_INDEPENDENT_FAILURE_DOMAIN"),
        ("owner_waiver_offmachine_backup_20261118.json", "Owner waiver of the off-machine failure-domain backup", "BACKUP_INDEPENDENT_FAILURE_DOMAIN"),
        ("a5_review_verdict.json", "A5 verdict from the authorized deepseek-flash subagent (not a human signature)", "A5_INDEPENDENT_REVIEW"),
        ("a5_review_transcript.json", "Read-only A5 inspection transcript (16 tool steps before HTTP 524)", "A5_INDEPENDENT_REVIEW"),
        ("issue12_consolidated_receipt_draft_20261117.md", "Issue #12 receipt draft (not posted)", "EVIDENCE_MANIFEST"),
        ("maml_readiness_20261117.md", "MAML offline readiness summary", "M2_OFFLINE_REHEARSAL"),
    ]
    manifest_entries = {item["path"].replace("\\", "/"): item for item in manifest.get("files", [])}
    generated_after_bundle = {
        "docs/evidence/drecover001/local_restore_receipt.json":
            "generated after the bundle exists; excluded from the bundle manifest to "
            "avoid a self-referential hash",
    }
    evidence_index = []
    for name, claim, gate in entries:
        path = ev / name
        item_path = EV + "/" + name
        if name.startswith("../"):
            path = (ev / name).resolve()
            item_path = path.relative_to(root.resolve()).as_posix()
        if not path.is_file():
            problems.append("missing evidence file " + item_path)
            continue
        data = path.read_bytes()
        digest = sha256_bytes(data)
        item = {"path": item_path, "bytes": len(data), "sha256": digest,
                "claim": claim, "gate": gate}
        rel = item["path"]
        if rel in manifest_entries:
            recorded = manifest_entries[rel]
            if recorded.get("sha256") != digest or recorded.get("bytes") != len(data):
                problems.append("manifest mismatch for " + rel)
            item["in_change_manifest"] = True
        else:
            item["in_change_manifest"] = False
            if rel in generated_after_bundle:
                item["manifest_exclusion_reason"] = generated_after_bundle[rel]
        evidence_index.append(item)
    if manifest.get("file_count") != len(manifest.get("files", [])):
        problems.append("manifest file_count differs from files list length")
    if manifest.get("total_bytes") != sum(int(x.get("bytes", 0)) for x in manifest.get("files", [])):
        problems.append("manifest total_bytes differs from file sizes")

    packet = {
        "schema": "drecover001.a5_review_packet.v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "scope": "READ_ONLY_EVIDENCE_AGGREGATION_FOR_INDEPENDENT_A5_REVIEW",
        "attestation": {
            "physical_solver_starts_actual": 0,
            "internal_solver_cases_actual": 0,
            "real_meta_training_executed": False,
            "admitted_real_labels": 0,
            "a5_review_performed": True,
            "a5_reviewer": a5_verdict.get("reviewer"),
            "a5_verdict_recorded": a5_verdict.get("verdict"),
            "a5_human_signature": False,
            "physical_go_issued": False,
            "backup_restore_established": False,
            "off_machine_backup_waived_by_owner": True,
            "new_scientific_evidence_created": False,
            "network_used": False,
        },
        "software_run_id": readiness.get("software_run_id"),
        "software_tests": {"run": preflight.get("tests_run"), "failures": preflight.get("failures"),
                            "errors": preflight.get("errors"), "skipped": preflight.get("skipped")},
        "gate_states": gates,
        "owner_waiver": {
            "waiver_id": waiver.get("waiver_id"),
            "owner_message_ref": waiver.get("owner_message_ref"),
            "scope": waiver.get("scope"),
            "waived": waiver.get("waived"),
            "owner_message_quote": waiver.get("owner_message_quote"),
            "effect": waiver.get("effect"),
            "not_waived": waiver.get("not_waived"),
            "file": EV + "/owner_waiver_offmachine_backup_20261118.json",
        },
        "a5_review": {
            "performed": True,
            "reviewer": a5_verdict.get("reviewer"),
            "reviewer_role": "authorized independent subagent created by the Lead at the Owner's instruction (m03569)",
            "human_signature": False,
            "verdict": a5_verdict.get("verdict"),
            "gate_verdicts": a5_verdict.get("gate_verdicts"),
            "findings": a5_verdict.get("findings"),
            "harness": a5_verdict.get("harness"),
            "signature": a5_verdict.get("signature"),
            "is_not_an_approval": "The recorded verdict is review input, not a human signature and not a physical-run authorization.",
            "files": [EV + "/a5_review_verdict.json", EV + "/a5_review_transcript.json"],
        },
        "readiness_matrix": {"path": EV + "/recovery_readiness.json",
                             "status": readiness.get("status"),
                             "generated_utc": readiness.get("generated_utc"),
                             "note": "status is quoted, not hashed, to avoid a self-referential hash cycle; rerun the aggregator to verify"},
        "claims": [
            {"claim": "R0 inventory, provenance and loss ledger are complete as offline records, not independently audited",
             "gate": "R0_INVENTORY", "state": gates.get("R0_INVENTORY")},
            {"claim": "R0 new-baseline manifest starts from commit 01c9274, archives the historical F1R2/F2R2 raw data as RAW_LOST, stops further history-recovery search, and requires new run/batch/geometry/task-family identities plus a fresh Lead GO",
             "gate": "R0_INVENTORY", "state": gates.get("R0_INVENTORY")},
            {"claim": "A1 geometry freeze v2 issues a 15-variable geometry/reference contract (12D lifting surfaces plus fixed fuselage), 24/24 declared-boundary perturbations in both the pure model and real OpenVSP 3.55, and real VSP3/STL/STEP exports with read-back; force-axis signs, WING_AC moment origin and mass/CG remain unvalidated and provisional",
             "gate": "A1_GEOMETRY_FREEZE_V2", "state": gates.get("A1_GEOMETRY_FREEZE_V2")},
            {"claim": "A2 exercises the real ArmHarness/GP-BO feedback path with a deterministic mock evaluator: six evaluations, zero physical starts, swapping the first two returned values changes the third proposal, and a failed design carries a null objective; this is software feedback evidence, not a physical loop",
             "gate": "R1_SOFTWARE", "state": gates.get("R1_SOFTWARE")},
            {"claim": f"R1 software baseline passes {preflight.get('tests_run')} offline tests; fixture-only training changes parameters and checkpoint roundtrips",
             "gate": "R1_SOFTWARE", "state": gates.get("R1_SOFTWARE")},
            {"claim": "M1 batch control path is exercised with a structural placeholder authorization, not a real GO",
             "gate": "M1_BATCH_CONTROL_PATH", "state": gates.get("M1_BATCH_CONTROL_PATH")},
            {"claim": "M2 offline rehearsal is deterministic across repeated runs; it is not real meta-training",
             "gate": "M2_OFFLINE_REHEARSAL", "state": gates.get("M2_OFFLINE_REHEARSAL")},
            {"claim": "Only a same-host restore test exists and is explicitly labelled NOT an off-machine backup; the off-machine failure-domain requirement is waived by the Owner "
                      "(WAIVER-OFFMACHINE-BACKUP-20261118, m03569) but backup_restore_pass remains false",
             "gate": "BACKUP_INDEPENDENT_FAILURE_DOMAIN", "state": gates.get("BACKUP_INDEPENDENT_FAILURE_DOMAIN")},
            {"claim": "A5 independent review was performed by the authorized deepseek-flash subagent (read-only tools); its verdict is recorded, it is not a human signature, and it is not an approval for physical runs",
             "gate": "A5_INDEPENDENT_REVIEW", "state": gates.get("A5_INDEPENDENT_REVIEW")},
            {"claim": "A RealAdmissionManifest/AdmissionCertificate protocol now exists and is fixture-tested: it recomputes file SHA256, deck conditions, q, matched-lift row and D_i_N=q*Sref*CDi, and refuses tampered/missing/path-escaping artifacts; no real raw artifact has been admitted, and require_real_admission still raises without matching certificates",
             "gate": "REAL_ADMISSION", "state": gates.get("REAL_ADMISSION")},
        ],
        "evidence_index": evidence_index,
        "open_external_gates": [
            {"gate": "A5_INDEPENDENT_REVIEW",
             "state": gates.get("A5_INDEPENDENT_REVIEW"),
             "required": "A deepseek-flash subagent performed a read-only review and recorded a verdict (not a human signature). Owner acceptance of that verdict is still external; the Lead must not upgrade it to a human sign-off."},
            {"gate": "BACKUP_INDEPENDENT_FAILURE_DOMAIN",
             "state": gates.get("BACKUP_INDEPENDENT_FAILURE_DOMAIN"),
             "required": "WAIVED by Owner (m03569): only a same-host restore is required. The same-host restore is still not an off-machine backup; backup_restore_pass stays false and the receipt must keep the explicit label."},
            {"gate": "REAL_ADMISSION",
             "state": gates.get("REAL_ADMISSION"),
             "required": "The protocol is implemented and fixture-tested but still unexercised on real VSPAERO raw output. A real run must supply mesh/deck/polar/history bytes, a matching audit record and a successful matched-lift row; this packet admits no labels and issues no GO."},
            {"gate": "R2_BATCH_GO",
             "state": "NOT_ISSUED",
             "required": "After the above, A5 and Lead must pre-register a new batch with new ids, budget, stop conditions and approval; no physical run is authorized by this packet."},
        ],
        "known_limitations": [
            "A CLOSED gate is expected and is not a PASS.",
            "The off-machine failure-domain backup is WAIVED by the Owner (m03569); the same-host restore receipt is explicitly labelled SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP and backup_restore_pass remains false. WAIVED is not a PASS.",
            "The A5 review was performed by a deepseek-flash subagent with read-only tools; it is not a human signature and does not by itself authorize physical runs. It returned CHANGES_REQUIRED, and the Lead must close or disclose each finding.",
            "Two files named real_openvsp_geometry_probe.json exist: docs/evidence/drecover001/real_openvsp_geometry_probe.json is the pre-repair SURFACE_DIAGNOSTIC_FAIL snapshot; the authoritative post-repair record is docs/evidence/drecover001/a1_thickness_repair/real_openvsp_geometry_probe.json (SURFACE_DIAGNOSTIC_PASS_NOT_FREEZE). Neither is a solver freeze or physics validation.",
            "research/concorde_metaopt/dreal001/meta/m2_rehearsal.py hardcodes three native_probe_status PASS strings into its geometry contract; the rehearsal therefore asserts, rather than reads, those probe statuses.",
            "needed_for_next_run.json had a truncated R1 requirement tail; it is valid JSON now but the lost tail is marked UNKNOWN and is not evidence.",
            "The evidence tree has uncommitted changes on top of commit 01c9274801474c113a2c488e375d451bcd0297c3. CLI git transport has no configured credential and fails with SEC_E_NO_CREDENTIALS, so this snapshot is not itself a remote commit; earlier snapshots were pushed through the GitHub API.",
            "Some R0 report claims are REPORT_PRESENT only; raw identity is not established for all historical numbers.",
            "A1 geometry freeze v2 validates the declared geometry/reference contract and zero-physical boundary perturbations, not aerodynamics. Force-axis signs, the WING_AC moment origin and mass/CG remain unvalidated; the global-versus-wing-local XCG ambiguity is disclosed as an open item for R2 VSPAERO read-back.",
            "The VSP3/STL/STEP exports are real OpenVSP 3.55 bytes checked by SHA and STL bounds, but byte-identical re-export across machines is not asserted. Re-running verify_geometry_freeze_v2.py requires the same OpenVSP installation.",
            "The RealAdmissionManifest protocol binds a matching independent-audit record by SHA256, but the protocol does not authenticate who produced that audit record; independent review remains an external requirement, and all admission tests use synthetic non-physical bytes.",
            "The M1 run uses a structural placeholder authorization and simulated starts.",
            "The readiness matrix is regenerated evidence; this packet quotes its status but intentionally does not embed its file hash.",
            "run_recovery_preflight.py is deliberately excluded from the non-destructive reproduction list: it assigns a new run_id and overwrites the preflight receipt, trace and checkpoint hashed here. Rerun the suite only inside a restored copy of the bundle, never in this frozen evidence tree.",
        ],
        "reproduction": [
            "D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/assess_recovery_readiness.py",
            "D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/verify_r0_provenance_extension.py",
            "D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/verify_geometry_freeze_v2.py",
            "D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/verify_m1_batch_evidence.py",
            "D:/Anaconda/envs/RCAIDE/python.exe docs/evidence/drecover001/build_a5_review_packet.py --check",
        ],
        "review_checklist": [
            "Confirm every evidence_index hash against the bytes on disk.",
            "Confirm physical/internal counters are 0 and no admitted real labels exist.",
            "Confirm the R0 inventory still says R0_PARTIAL_NOT_AUDITED and keeps RAW_LOST items raw-lost; confirm new_baseline_manifest.json fixes commit 01c9274 as the new start and requires fresh identities.",
            "Confirm A1 geometry_freeze_v2.json contract SHA, 24/24 model and native boundary cases, and export bytes match the files on disk.",
            "Confirm R1 changes do not overwrite historical raw data or S1/S2/S3 negative results.",
            "Confirm REAL_ADMISSION still admits no real label, every certificate requires the issuer sentinel and q*Sref*CDi identity, and no placeholder is presented as a real GO.",
            "Confirm the destructive preflight was NOT run in this tree and every evidence_index hash still matches on disk.",
            "Record an explicit verdict: APPROVE_FOR_R2, REJECT, or CHANGES_REQUIRED, with scope and date.",
        ],
        "requested_a5_verdict": None,
        "recorded_a5_verdict": a5_verdict.get("verdict"),
        "disclosure": "This packet is input to review, not a review. It creates no evidence, no approval, no budget and no physical authorization.",
    }
    return packet, problems


def render_md(packet: dict) -> str:
    lines = ["# A5 独立审查包（只读聚合）", ""]
    lines.append("- 生成时间（UTC）：" + packet["generated_utc"])
    lines.append("- 范围：" + packet["scope"])
    lines.append("- 软件 run_id：" + str(packet["software_run_id"]))
    t = packet["software_tests"]
    lines.append("- 离线测试：" + str(t["run"]) + " 项，失败 " + str(t["failures"]) +
                 "，错误 " + str(t["errors"]) + "，跳过 " + str(t["skipped"]))
    lines.append("- 物理求解器启动：0；内部求解案例：0；真实元训练：false；真实标签：0")
    lines.append("- 异机备份：Owner 已豁免（m03569），只做同机恢复；同机恢复标注为非异机备份，backup_restore_pass 仍为 false。")
    a5 = packet.get("a5_review", {})
    lines.append("- 本包记录一次 A5 审查：" + str(a5.get("reviewer")) + "，verdict=" +
                 str(a5.get("verdict")) + "，非人类签名，不授予物理 GO。")
    lines.append("")
    lines.append("## 门禁状态")
    lines.append("")
    for gate, state in packet["gate_states"].items():
        lines.append("- " + gate + ": " + state)
    lines.append("")
    lines.append("## 可复核证据（逐文件 SHA256）")
    lines.append("")
    for item in packet["evidence_index"]:
        lines.append("- " + item["path"] + "（" + str(item["bytes"]) + " 字节）：" +
                     item["sha256"] + " — " + item["claim"])
    lines.append("")
    lines.append("## 已记录的 A5 审查")
    lines.append("")
    for f in (packet.get("a5_review", {}).get("findings") or []):
        lines.append("- [" + str(f.get("severity")) + "] " + str(f.get("id")) + " × " +
                     str(f.get("gate")) + "：" + str(f.get("finding")))
    lines.append("")
    lines.append("## 待外部签署的门禁")
    lines.append("")
    for gate in packet["open_external_gates"]:
        lines.append("- " + gate["gate"] + "（" + str(gate["state"]) + "）：" + gate["required"])
    lines.append("")
    lines.append("## 已知限制")
    lines.append("")
    for item in packet["known_limitations"]:
        lines.append("- " + item)
    lines.append("")
    lines.append("## 复核步骤（非破坏性）")
    lines.append("")
    for cmd in packet["reproduction"]:
        lines.append("    " + cmd)
    lines.append("")
    lines.append("## A5 检查清单")
    lines.append("")
    for item in packet["review_checklist"]:
        lines.append("- [ ] " + item)
    lines.append("")
    lines.append("## 请求的 A5 结论")
    lines.append("")
    lines.append("APPROVE_FOR_R2、REJECT 或 CHANGES_REQUIRED，并写明范围与日期。Lead 不自签。")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out", default=None)
    parser.add_argument("--md", default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    packet, problems = build(root)
    out = Path(args.out) if args.out else root / EV / PACKET_JSON
    md = Path(args.md) if args.md else root / EV / PACKET_MD
    if args.check:
        print(json.dumps({"problems": problems, "evidence_count": len(packet["evidence_index"]),
                          "gate_states": packet["gate_states"]}, ensure_ascii=False, indent=2))
        return 0 if not problems else 1
    out.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md.write_text(render_md(packet), encoding="utf-8")
    print(json.dumps({"out": str(out), "md": str(md), "problems": problems,
                      "evidence_count": len(packet["evidence_index"])},
                     ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
