"""Clean local restoration test. NOT independent-domain backup or real admission.

The bundle is a snapshot: its embedded change manifest must describe the bundle
payload, not the evolving source worktree.  The receipt is generated only after
the bundle exists, so it is deliberately excluded from that manifest.  After the
restored tree has re-run the preflight, its evidence files are put back to the
bundle's original bytes before the readiness aggregator and A5 packet checks are
run.  This proves that the restored evidence chain, not just the tests, is
internally consistent.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
EVIDENCE = OUT
RESTORE_RECEIPT = "local_restore_receipt.json"
EXPECTED_SCOPE = "SOFTWARE_FIXTURE_TRAINING_ONLY"
EXPECTED_READINESS = "RECOVERY_READINESS_GATES_CLOSED_EXPECTED"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if not name or "\\" in name or p.is_absolute() or ".." in p.parts or ":" in name:
        raise RuntimeError("unsafe archive path: " + name)
    return p


def refresh_manifest():
    """Regenerate the source manifest immediately before snapshotting."""
    subprocess.run([sys.executable, "-B", str(EVIDENCE / "build_change_manifest.py")],
                   cwd=ROOT, check=True, timeout=120,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def worktree_overlay_paths(root):
    raw = subprocess.check_output(["git", "status", "--porcelain=v1", "-z",
                                   "--untracked-files=all"], cwd=root)
    entries = [e for e in raw.split(b"\0") if e]
    paths = []
    i = 0
    while i < len(entries):
        text = entries[i].decode("utf-8")
        if len(text) < 4:
            raise RuntimeError("malformed git status entry")
        status, rel = text[:2], text[3:]
        if status[0] in "RC":
            i += 1  # skip the rename/copy source entry
        if status.strip() != "D" and PurePosixPath(rel).name != RESTORE_RECEIPT:
            paths.append(rel)
        i += 1
    return paths


def snapshot_evidence(root):
    ev = root / "docs/evidence/drecover001"
    snap = {}
    for path in ev.rglob("*"):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            if rel.endswith("/" + RESTORE_RECEIPT):
                continue
            snap[rel] = path.read_bytes()
    return snap


def restore_evidence(root, snap):
    ev = root / "docs/evidence/drecover001"
    for path in sorted(ev.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.endswith("/" + RESTORE_RECEIPT):
            continue
        if rel not in snap:
            path.unlink()
    for rel, data in snap.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def verify_bundle_manifest(bundle, inventory, head):
    """Verify that the embedded bundle manifest describes the bundle payload.

    This is deliberately a verifier, not a re-serialization of the manifest that
    was just written: it reads the zip's own LOCAL_RESTORE_MANIFEST.json and
    compares every recorded path, SHA256 and byte count with the actual payload.
    """
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        if "LOCAL_RESTORE_MANIFEST.json" not in names:
            raise RuntimeError("bundle manifest is missing")
        raw = archive.read("LOCAL_RESTORE_MANIFEST.json")
        manifest = json.loads(raw)
        files = manifest.get("files")
        if not isinstance(files, dict) or set(files) != set(inventory):
            raise RuntimeError("bundle manifest path set does not match payload")
        for name, meta in files.items():
            data = archive.read(name)
            if sha(data) != meta.get("sha256") or len(data) != meta.get("bytes"):
                raise RuntimeError("bundle manifest mismatch: " + name)
        if manifest.get("baseline_commit") != head:
            raise RuntimeError("bundle manifest baseline mismatch")
        if manifest.get("includes_all_worktree_changes") is not True:
            raise RuntimeError("bundle manifest does not declare full worktree overlay")
        excluded = {item.get("path") for item in manifest.get("excluded_from_manifest", [])}
        receipt_path = "docs/evidence/drecover001/" + RESTORE_RECEIPT
        if receipt_path not in excluded:
            raise RuntimeError("bundle manifest does not declare the post-bundle receipt exclusion")
    return {"verified": True, "files": len(files), "manifest_sha256": sha(raw)}


def receipt_payload(*, head, bundle, restored, inventory, overlay, source_receipt,
                    checkpoint_equal, holdout_equal, evidence_files_restored,
                    evidence_chain_verified, readiness_status, readiness_violations,
                    packet_problems, verifier_results, passes, bundle_manifest):
    return {
        "scope": "LOCAL_SOFTWARE_RESTORE_ONLY",
        "status": "PASS_NOT_REMOTE_BACKUP",
        "baseline_commit": head,
        "bundle_path": str(bundle),
        "bundle_sha256": sha(bundle.read_bytes()),
        "restored_path": str(restored),
        "files_verified": len(inventory),
        "overlay_files": len(overlay),
        "tests_run": source_receipt["tests_run"],
        "tests_passed": source_receipt["tests_run"],
        "fresh_import_origin": "RESTORED_TREE",
        "training_status": source_receipt["training_status"],
        "checkpoint_retrained_exact": checkpoint_equal,
        "holdout_recomputed_exact": holdout_equal,
        "evidence_files_restored": evidence_files_restored,
        "bundle_manifest_verified": bundle_manifest["verified"],
        "bundle_manifest_files": bundle_manifest["files"],
        "bundle_manifest_sha256": bundle_manifest["manifest_sha256"],
        "evidence_chain_verified": evidence_chain_verified,
        "readiness_status": readiness_status,
        "readiness_violations": readiness_violations,
        "packet_check_problems": packet_problems,
        "evidence_verifiers": verifier_results,
        "verification_passes": passes,
        "independent_failure_domain": False,
        "backup_restore_pass": False,
        "off_machine_backup": False,
        "backup_label": "SAME_HOST_RESTORE_NOT_AN_OFF_MACHINE_BACKUP",
        "owner_waiver": {
            "waiver_id": "WAIVER-OFFMACHINE-BACKUP-20261118",
            "owner_message_ref": "m03569",
            "scope": "OFF_MACHINE_INDEPENDENT_FAILURE_DOMAIN_BACKUP",
            "waived": True,
            "note": "Owner waived the off-machine failure-domain backup; this receipt proves a same-host restore only.",
        },
        "real_meta_training_executed": False,
        "physical_solver_starts_actual": 0,
        "source_sha256": sha(Path(__file__).read_bytes()),
    }


def run_checked(command, *, cwd, env, log):
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                              stderr=subprocess.STDOUT, timeout=240)
    if proc.returncode != 0:
        raise RuntimeError("command failed with exit %d: %s" % (proc.returncode, command))
    return proc


def run_check(command, *, cwd, env, log):
    """Run a check that returns its JSON on stdout; non-zero is reported, not hidden."""
    with log.open("w", encoding="utf-8") as stream:
        proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=240)
        stream.write(proc.stdout)
        stream.write(proc.stderr)
    return proc


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build and verify a portable local restoration bundle.")
    parser.add_argument("--target-dir", default=None,
                        help="existing empty directory for the bundle and restored tree; default is a timestamped dir")
    args = parser.parse_args(argv)
    refresh_manifest()
    source_receipt = json.loads((EVIDENCE / "recovery_preflight_receipt.json").read_text())
    if source_receipt["training_status"] != EXPECTED_SCOPE:
        raise RuntimeError("requires executed software fixture training")
    source_checkpoint = (EVIDENCE / "synthetic_software_checkpoint.json").read_bytes()
    if sha(source_checkpoint) != source_receipt["synthetic_checkpoint_sha256"]:
        raise RuntimeError("source checkpoint checksum mismatch")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    session_root = ROOT.parents[1]
    if args.target_dir:
        target = Path(args.target_dir).resolve()
        if not target.is_dir() or any(target.iterdir()):
            raise RuntimeError("--target-dir must be an existing empty directory")
    else:
        token = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = session_root / ".recovery-local-restore" / token
        target.mkdir(parents=True, exist_ok=False)
    baseline = target / "baseline.zip"
    # core.autocrlf=true would make git archive rewrite LF blobs as CRLF, so a
    # restored text evidence file would no longer match its recorded SHA256.
    # Force the repository bytes for the baseline archive.
    subprocess.run(["git", "-c", "core.autocrlf=false", "archive", "--format=zip",
                    "-o", str(baseline), head], cwd=ROOT, check=True)
    overlay = {}
    for rel, digest in source_receipt["source_sha256"].items():
        name = rel.replace("\\", "/")
        safe_name(name)
        data = (ROOT / name).read_bytes()
        if sha(data) != digest:
            raise RuntimeError("source changed since preflight: " + name)
        overlay[name] = data
    extra = ["run_fixture_holdout.py", "run_local_restore.py", "recovery_preflight_receipt.json",
             "synthetic_software_checkpoint.json", "synthetic_software_training_trace.json",
             "synthetic_fixture_holdout.json"]
    for name in extra:
        overlay["docs/evidence/drecover001/" + name] = (EVIDENCE / name).read_bytes()
    # Overlay every changed/untracked worktree file so the bundle reproduces the
    # current tree.  The restore receipt is excluded: it describes this bundle
    # and is created only after the bundle exists.
    for rel in worktree_overlay_paths(ROOT):
        name = rel.replace("\\", "/")
        safe_name(name)
        path = ROOT / name
        if not path.is_file():
            continue
        data = path.read_bytes()
        if name in overlay and overlay[name] != data:
            raise RuntimeError("overlay conflict: " + name)
        overlay[name] = data
    payload = {}
    with zipfile.ZipFile(baseline) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            safe_name(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise RuntimeError("symlink forbidden in restoration bundle")
            if info.filename in payload:
                raise RuntimeError("duplicate baseline path")
            payload[info.filename] = archive.read(info)
    payload.update(overlay)
    inventory = {name: {"sha256": sha(data), "bytes": len(data)} for name, data in sorted(payload.items())}
    bundle_manifest = {
        "scope": "LOCAL_SOFTWARE_RESTORE_ONLY",
        "baseline_commit": head,
        "overlay_paths": sorted(overlay),
        "files": inventory,
        "includes_all_worktree_changes": True,
        "excluded_from_manifest": [
            {"path": "docs/evidence/drecover001/" + RESTORE_RECEIPT,
             "reason": "created after the bundle exists; would make the manifest self-referential"},
        ],
        "independent_failure_domain": False,
        "real_admission": False,
    }
    bundle = target / "recovery_bundle.zip"
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            archive.writestr(name, data)
        archive.writestr("LOCAL_RESTORE_MANIFEST.json", json.dumps(bundle_manifest, sort_keys=True, indent=2))
    bundle_manifest = verify_bundle_manifest(bundle, payload, head)
    restored = target / "restored"
    restored.mkdir()
    with zipfile.ZipFile(bundle) as archive:
        for info in archive.infolist():
            rel = safe_name(info.filename)
            dest = restored.joinpath(*rel.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("xb") as stream:
                stream.write(archive.read(info))
    for name, expected in inventory.items():
        data = (restored / name).read_bytes()
        if sha(data) != expected["sha256"] or len(data) != expected["bytes"]:
            raise RuntimeError("restored checksum mismatch: " + name)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    restored_evidence = restored / "docs/evidence/drecover001"
    evidence_snapshot = snapshot_evidence(restored)
    # Independent child process roots imports in the extracted tree, not the source worktree.
    probe = ("import pathlib,sys; root=pathlib.Path.cwd().resolve(); "
             "import research.concorde_metaopt.dreal001.meta.production as p; "
             "import research.concorde_metaopt.meta_learning.maml as m; "
             "assert pathlib.Path(p.__file__).resolve().is_relative_to(root); "
             "assert pathlib.Path(m.__file__).resolve().is_relative_to(root); print(p.__file__,m.__file__)")
    commands = [[sys.executable, "-B", "-c", probe],
                [sys.executable, "-B", "docs/evidence/drecover001/run_recovery_preflight.py"],
                [sys.executable, "-B", "docs/evidence/drecover001/run_fixture_holdout.py"]]
    logs = []
    for i, command in enumerate(commands):
        log = target / ("restore_step_%d.log" % i)
        run_checked(command, cwd=restored, env=env, log=log)
        logs.append(str(log))
    receipt = json.loads((restored_evidence / "recovery_preflight_receipt.json").read_text())
    checkpoint_equal = (restored_evidence / "synthetic_software_checkpoint.json").read_bytes() == source_checkpoint
    holdout_equal = (json.loads((restored_evidence / "synthetic_fixture_holdout.json").read_text())
                     == json.loads((EVIDENCE / "synthetic_fixture_holdout.json").read_text()))
    if receipt["tests_run"] != source_receipt["tests_run"] or receipt["failures"] or receipt["errors"] or receipt["skipped"]:
        raise RuntimeError("restored software suite mismatch")
    if receipt["training_status"] != EXPECTED_SCOPE or not checkpoint_equal or not holdout_equal:
        raise RuntimeError("restored deterministic training/holdout mismatch")
    # Put the evidence chain back to the exact bytes that the bundle manifest
    # describes.  The preflight has already been compared above; its regenerated
    # receipt/trace must not remain as a fresh-timestamped copy in the bundle.
    restore_evidence(restored, evidence_snapshot)
    provisional = receipt_payload(
        head=head, bundle=bundle, restored=restored, inventory=inventory, overlay=overlay,
        source_receipt=source_receipt, checkpoint_equal=checkpoint_equal,
        holdout_equal=holdout_equal, evidence_files_restored=len(evidence_snapshot),
        evidence_chain_verified=False, readiness_status="NOT_RUN",
        readiness_violations=[], packet_problems=[], verifier_results={}, passes=0,
        bundle_manifest=bundle_manifest)
    (restored_evidence / RESTORE_RECEIPT).write_text(json.dumps(provisional, indent=2), encoding="utf-8")
    run_logs = []
    readiness_cmd = [sys.executable, "-B", "docs/evidence/drecover001/assess_recovery_readiness.py"]
    packet_cmd = [sys.executable, "-B", "docs/evidence/drecover001/build_a5_review_packet.py", "--check"]
    r0_verify_cmd = [sys.executable, "-B", "docs/evidence/drecover001/verify_r0_provenance_extension.py"]
    m1_verify_cmd = [sys.executable, "-B", "docs/evidence/drecover001/verify_m1_batch_evidence.py"]

    def verifier_status(proc, expected):
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"status": "UNPARSABLE", "failures": ["stdout is not JSON"]}
        status = payload.get("status")
        return {
            "returncode": proc.returncode,
            "status": status,
            "failures": payload.get("failures", []),
            "ok": proc.returncode == 0 and status == expected,
        }

    for pass_index in (1, 2):
        r0_log = target / ("restore_evidence_verify_r0_%d.log" % pass_index)
        r0_proc = run_check(r0_verify_cmd, cwd=restored, env=env, log=r0_log)
        m1_log = target / ("restore_evidence_verify_m1_%d.log" % pass_index)
        m1_proc = run_check(m1_verify_cmd, cwd=restored, env=env, log=m1_log)
        verifier_results = {
            "r0_provenance": verifier_status(
                r0_proc, "R0_PROVENANCE_EXTENSION_EVIDENCE_INTERNALLY_CONSISTENT"),
            "m1_batch": verifier_status(
                m1_proc, "M1_BATCH_EVIDENCE_INTERNALLY_CONSISTENT"),
        }
        verifier_ok = all(item["ok"] for item in verifier_results.values())
        readiness_log = target / ("restore_evidence_readiness_%d.log" % pass_index)
        readiness_proc = run_check(readiness_cmd, cwd=restored, env=env, log=readiness_log)
        readiness = json.loads((restored_evidence / "recovery_readiness.json").read_text())
        packet_log = target / ("restore_evidence_packet_%d.log" % pass_index)
        packet_proc = run_check(packet_cmd, cwd=restored, env=env, log=packet_log)
        try:
            packet_result = json.loads(packet_proc.stdout)
        except json.JSONDecodeError:
            packet_result = {"problems": ["packet check stdout is not JSON"]}
        problems = packet_result.get("problems", [])
        violations = readiness.get("violations", [])
        ready_ok = (readiness_proc.returncode == 0
                    and readiness.get("status") == EXPECTED_READINESS
                    and not violations)
        packet_ok = packet_proc.returncode == 0 and not problems
        verified = ready_ok and packet_ok and verifier_ok
        result = receipt_payload(
            head=head, bundle=bundle, restored=restored, inventory=inventory, overlay=overlay,
            source_receipt=source_receipt, checkpoint_equal=checkpoint_equal,
            holdout_equal=holdout_equal, evidence_files_restored=len(evidence_snapshot),
            evidence_chain_verified=verified, readiness_status=readiness.get("status"),
            readiness_violations=violations, packet_problems=problems,
            verifier_results=verifier_results, passes=pass_index,
            bundle_manifest=bundle_manifest)
        (OUT / RESTORE_RECEIPT).write_text(json.dumps(result, indent=2), encoding="utf-8")
        (restored_evidence / RESTORE_RECEIPT).write_text(json.dumps(result, indent=2), encoding="utf-8")
        run_logs.extend([str(r0_log), str(m1_log), str(readiness_log), str(packet_log)])
        if not verified:
            raise RuntimeError("restored evidence chain failed on pass %d: readiness=%r violations=%r packet=%r verifiers=%r"
                               % (pass_index, readiness.get("status"), violations, problems,
                                  verifier_results))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
