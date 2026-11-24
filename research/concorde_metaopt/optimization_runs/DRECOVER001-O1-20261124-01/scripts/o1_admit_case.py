"""Admit one O0 case: strict raw-row admission bound to the H0 geometry contract.

Copied from the G1 admittance tool, retargeted at the dreal005 worktree and the
D-REAL-EXP-003 H0 contract. It never relaxes the lift tolerance and never promotes
an interpolated row: admit_real_manifest re-reads the raw bytes and requires an
actual polar row inside 1e-3 relative lift error.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.dreal001.meta.real_admission import (  # noqa: E402
    RawFile, RealAdmissionManifest, admit_real_manifest,
)
from research.concorde_metaopt.dreal001.meta.raw_verification import (  # noqa: E402
    ArtifactBinding,
)
from research.concorde_metaopt.dreal001.meta.task_spec import (  # noqa: E402
    TaskSpec, canonical_sha,
)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-dir", required=True)
    ap.add_argument("--admission-id", required=True)
    ap.add_argument("--audit-ref", required=True)
    ap.add_argument("--evaluator-id", required=True)
    ap.add_argument("--solver-started-utc", required=True)
    ap.add_argument("--partition", default="query", choices=["support", "query"])
    ap.add_argument("--split", default="train", choices=["train", "val", "test"])
    ap.add_argument("--task-spec", default=None)
    ap.add_argument("--performance-tag", default=None)
    a = ap.parse_args()
    case = Path(a.case_dir)
    plan = json.loads((case / "plan.json").read_text(encoding="utf-8"))
    result = json.loads((case / "case_result.json").read_text(encoding="utf-8"))
    case_inputs = json.loads((case / "case_inputs.json").read_text(encoding="utf-8"))
    spec_path = Path(a.task_spec) if a.task_spec else (case / "task_spec.json")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    flow = spec["flow_conditions"]
    base = result["attempt"]["basename"]
    x12 = [float(x) for x in plan["design"]["x12"]]
    design_id = canonical_sha(x12)

    def raw(kind, filename):
        p = case / filename
        return RawFile(kind=kind, path=filename, sha256=sha(p), bytes=p.stat().st_size)

    files = (
        raw("audit", "audit.json"),
        raw("deck", base + ".vspaero"),
        raw("history", base + ".history"),
        raw("mesh", base + ".vspgeom"),
        raw("polar", base + ".polar"),
    )
    by_kind = {f.kind: f for f in files}
    task = TaskSpec(
        task_id=spec["task_id"], split=a.split, mach=float(spec["mach"]),
        altitude_m=float(spec["altitude_m"]),
        dynamic_pressure_pa=float(spec["dynamic_pressure_pa"]),
        lift_target_n=float(spec["lift_target_n"]),
        geometry_contract_sha256=spec["geometry_contract_sha256"],
        lift_tolerance_rel=float(spec.get("lift_tolerance_rel", 1e-3)),
    )
    binding = ArtifactBinding(
        task_physics_sha256=task.physics_sha256, design_sha256=design_id,
        geometry_contract_sha256=spec["geometry_contract_sha256"],
        mesh_sha256=by_kind["mesh"].sha256, deck_sha256=by_kind["deck"].sha256,
        polar_sha256=by_kind["polar"].sha256, sref_m2=float(case_inputs["sref_m2"]),
        rho_kg_m3=float(flow["rho_kg_m3"]), vinf_m_s=float(flow["vinf_m_s"]),
        recref=float(flow["recref"]),
        alpha_grid_deg=tuple(float(x) for x in case_inputs["alpha_list_deg"]),
    )
    manifest = RealAdmissionManifest(
        admission_id=a.admission_id, run_id=plan["run_id"],
        task_id=spec["task_id"], design_id=design_id, design=tuple(x12),
        geometry_sha256=spec["geometry_contract_sha256"], evaluator_id=a.evaluator_id,
        solver_returncode=int(result["process"]["exit_code"]),
        solver_started_utc=a.solver_started_utc,
        outcome="success", partition=a.partition, files=files,
        binding=binding, independent_audit_ref=a.audit_ref,
    )
    cert = admit_real_manifest(
        manifest=manifest, raw_root=case, task=task, design=x12,
        expected_evaluator_id=a.evaluator_id, expected_audit_ref=a.audit_ref,
    )
    out_manifest = case / "admission_manifest.json"
    out_manifest.write_text(json.dumps({
        "schema": manifest.schema,
        "admission_id": manifest.admission_id,
        "run_id": manifest.run_id,
        "task_id": manifest.task_id,
        "design_id": manifest.design_id,
        "design": list(manifest.design),
        "geometry_sha256": manifest.geometry_sha256,
        "evaluator_id": manifest.evaluator_id,
        "solver_returncode": manifest.solver_returncode,
        "solver_started_utc": manifest.solver_started_utc,
        "outcome": manifest.outcome,
        "partition": manifest.partition,
        "performance_tag": a.performance_tag,
        "files": [f.__dict__ for f in manifest.files],
        "artifact_sha256": manifest.artifact_sha256,
        "independent_audit_ref": manifest.independent_audit_ref,
        "binding": {
            "task_physics_sha256": binding.task_physics_sha256,
            "design_sha256": binding.design_sha256,
            "geometry_contract_sha256": binding.geometry_contract_sha256,
            "mesh_sha256": binding.mesh_sha256,
            "deck_sha256": binding.deck_sha256,
            "polar_sha256": binding.polar_sha256,
            "sref_m2": binding.sref_m2,
            "rho_kg_m3": binding.rho_kg_m3,
            "vinf_m_s": binding.vinf_m_s,
            "recref": binding.recref,
            "alpha_grid_deg": list(binding.alpha_grid_deg),
        },
        "task": {
            "task_id": task.task_id, "split": task.split,
            "physics_sha256": task.physics_sha256,
            "mach": task.mach, "altitude_m": task.altitude_m,
            "dynamic_pressure_pa": task.dynamic_pressure_pa,
            "lift_target_n": task.lift_target_n,
            "lift_tolerance_rel": task.lift_tolerance_rel,
            "geometry_contract_sha256": task.geometry_contract_sha256,
        },
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out_cert = case / "admission_certificate.json"
    out_cert.write_text(json.dumps({
        "admission_id": cert.admission_id,
        "task_id": cert.task_id,
        "design": list(cert.design),
        "design_sha256": cert.design_sha256,
        "partition": cert.partition,
        "status": cert.status,
        "di_n": cert.di_n,
        "q_pa": cert.q_pa,
        "sref_m2": cert.sref_m2,
        "cdi": cert.cdi,
        "cl": cert.cl,
        "alpha_deg": cert.alpha_deg,
        "raw_sha256": cert.raw_sha256,
        "artifact_sha256": cert.artifact_sha256,
        "geometry_sha256": cert.geometry_sha256,
        "evaluator_id": cert.evaluator_id,
        "independent_audit_ref": cert.independent_audit_ref,
        "evidence_scope": cert.evidence_scope,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": cert.status, "di_n": cert.di_n, "cdi": cert.cdi,
        "cl": cert.cl, "alpha_deg": cert.alpha_deg, "q_pa": cert.q_pa,
        "sref_m2": cert.sref_m2, "raw_sha256": cert.raw_sha256,
        "evidence_scope": cert.evidence_scope,
        "manifest": str(out_manifest), "certificate": str(out_cert),
    }, indent=2))


if __name__ == "__main__":
    main()
