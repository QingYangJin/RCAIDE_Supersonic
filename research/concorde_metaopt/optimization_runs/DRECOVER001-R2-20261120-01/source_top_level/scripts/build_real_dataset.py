import json, pathlib, sys
REPO=pathlib.Path(r"D:/RCAIDE/.worktrees/drecover001-20261117"); sys.path.insert(0,str(REPO))
from research.concorde_metaopt.dreal001.meta.real_admission import RealAdmissionManifest, RawFile, admit_real_manifest
from research.concorde_metaopt.dreal001.meta.raw_verification import ArtifactBinding
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec, canonical_sha
from research.concorde_metaopt.dreal001.meta.meta_dataset import MetaDataset
root=pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
spec_sources={"concorde-real-M160":"m160-d00-support-r1","concorde-fixed-cruise-dreal001-real-v1":"m202-d02-query-r1",
 "concorde-real-M180":"m180-d00-support-r1","concorde-real-M240":"m240-d00-support-r1"}
tasks={}
for tid,cid in spec_sources.items():
    spec=json.loads((root/"cases"/cid/"task_spec.json").read_text())
    tasks[tid]=TaskSpec(task_id=spec["task_id"],split=spec["split"],mach=float(spec["mach"]),
        altitude_m=float(spec["altitude_m"]),dynamic_pressure_pa=float(spec["dynamic_pressure_pa"]),
        lift_target_n=float(spec["lift_target_n"]),geometry_contract_sha256=spec["geometry_contract_sha256"],
        lift_tolerance_rel=float(spec.get("lift_tolerance_rel",1e-3)))
case_ids={
 "m160-d00-support-r1":"concorde-real-M160","m160-d02-query-r1":"concorde-real-M160",
 "m202-baseline-admit":"concorde-fixed-cruise-dreal001-real-v1","m202-d01-support":"concorde-fixed-cruise-dreal001-real-v1",
 "m202-d02-query-r1":"concorde-fixed-cruise-dreal001-real-v1","m180-d00-support-r1":"concorde-real-M180",
 "m180-d02-query-r1":"concorde-real-M180","m240-d00-support-r1":"concorde-real-M240","m240-d02-query-r1":"concorde-real-M240"}
paths={cid:root/"cases"/cid for cid in case_ids}
paths["m202-baseline-admit"]=root/"cases/baseline-admit-01"
certs=[]; rows=[]
for cid,cd in paths.items():
    m=json.loads((cd/"admission_manifest.json").read_text())
    b=m["binding"]
    binding=ArtifactBinding(task_physics_sha256=b["task_physics_sha256"],design_sha256=b["design_sha256"],
        geometry_contract_sha256=b["geometry_contract_sha256"],mesh_sha256=b["mesh_sha256"],
        deck_sha256=b["deck_sha256"],polar_sha256=b["polar_sha256"],sref_m2=float(b["sref_m2"]),
        rho_kg_m3=float(b["rho_kg_m3"]),vinf_m_s=float(b["vinf_m_s"]),recref=float(b["recref"]),
        alpha_grid_deg=tuple(float(x) for x in b["alpha_grid_deg"]))
    files=tuple(RawFile(kind=f["kind"],path=f["path"],sha256=f["sha256"],bytes=int(f["bytes"])) for f in m["files"])
    manifest=RealAdmissionManifest(admission_id=m["admission_id"],run_id=m["run_id"],task_id=m["task_id"],
        design_id=m["design_id"],design=tuple(m["design"]),geometry_sha256=m["geometry_sha256"],
        evaluator_id=m["evaluator_id"],solver_returncode=int(m["solver_returncode"]),
        solver_started_utc=m["solver_started_utc"],outcome=m["outcome"],partition=m["partition"],
        files=files,binding=binding,independent_audit_ref=m["independent_audit_ref"])
    task=tasks[manifest.task_id]
    cert=admit_real_manifest(manifest=manifest,raw_root=cd,task=task,design=manifest.design,
        expected_evaluator_id=manifest.evaluator_id,expected_audit_ref=manifest.independent_audit_ref)
    certs.append(cert)
    rows.append({"case_id":cid,"admission_id":cert.admission_id,"task_id":cert.task_id,"split":task.split,
                 "partition":cert.partition,"di_n":cert.di_n,"q_pa":cert.q_pa,"sref_m2":cert.sref_m2,
                 "cdi":cert.cdi,"cl":cert.cl,"alpha_deg":cert.alpha_deg,"raw_sha256":cert.raw_sha256,
                 "design_sha256":cert.design_sha256,"artifact_sha256":cert.artifact_sha256})
ds=MetaDataset.from_admitted_certificates(tuple(tasks.values()),tuple(certs))
ds.require_real_admission()
print("tasks",[(t.task_id,t.split,t.mach,round(t.dynamic_pressure_pa,3)) for t in ds.tasks])
print("rows",len(ds.rows))
for r in rows: print(r["task_id"],r["partition"],r["alpha_deg"],r["di_n"])
out={"schema":"drecover001.real_dataset_manifest.v1","run_id":"DRECOVER001-R2-20261120-01",
     "batch_id":"DRECOVER001-R2-20261120-01-B01R","physical_solver_starts":24,
     "tasks":[{"task_id":t.task_id,"split":t.split,"mach":t.mach,"altitude_m":t.altitude_m,
               "dynamic_pressure_pa":t.dynamic_pressure_pa,"lift_target_n":t.lift_target_n,
               "geometry_contract_sha256":t.geometry_contract_sha256,"physics_sha256":t.physics_sha256} for t in ds.tasks],
     "rows":rows,"admission_count":len(certs),
     "evidence_scope":"LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED",
     "physical_solver_starts_actual":0,"same_host_backup":True,
     "disclosure":"Nine raw cases; labels are NOT_AUTHENTICATED; only 2 train tasks, 1 support/query design per task; K=1 exploratory."}
out["dataset_sha256"]=canonical_sha(out)
(root/"real_dataset_manifest.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
print("dataset_sha256",out["dataset_sha256"])
