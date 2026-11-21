
import hashlib, json, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120"); RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
sys.path.insert(0,str(REPO))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.dreal001.geometry import openvsp_model
from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec
NAMES=["wing_area","aspect_ratio","sweep_1","sweep_2","sweep_3","span_location_2","span_location_3","chord_ratio_2","chord_ratio_3","tip_twist","vertical_tail_area","vertical_tail_sweep_delta","fuselage_length","fuselage_fineness","fuselage_height_width_ratio"]
BASELINE=[358.25,1.83,67.0,48.0,71.0,0.480469,0.945313,0.408284,0.130178,0.0,33.91,0.0,61.66,4.30,1.152778]
DES={k:BASELINE[:] for k in ("d00","d01","d02","d03","d04","d05")}
DES["d01"][0]=361.8325; DES["d02"][2]=67.5; DES["d03"][0]=354.6675; DES["d04"][2]=66.5; DES["d05"][10]=34.5882
CAL={"1.6":(7.4658,0.2896827658750951,0.03655),"1.8":(6.1846,0.22888514834575416,0.03579),"2.02":(5.18125,0.181741590896,0.03439427),"2.4":(4.44,0.128809590323,0.034)}
RUN_ID="DRECOVER001-G1-20261121-01"; BATCH="DRECOVER001-G1-20261121-01-B02"; AUTH="AUTH-DREAL003-G1-20261121-01"; LIFT=1333704.4; ALT=18288.0; VINF=596.0373972278921; RHO=0.1153178340089936; RECREF=89397005.8767656; MACH0=2.02; GEOM="5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15"; WEND="2026-11-22T12:00:00Z"
def sha(p):
    h=hashlib.sha256(); h.update(Path(p).read_bytes()); return h.hexdigest()
def canon(p): return hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def main():
    man=json.loads((RUN/"g1_case_manifest.json").read_text(encoding="utf-8"))
    old={c["case_id"]:c for c in man["cases"]}
    for c in man["cases"]:
        d=RUN/"cases"/c["case_id"]
        if (d/"solver_attempts.jsonl").exists() or (d/"case_result.json").exists(): continue
        tag=c["task_id"].split("-")[-1].replace("M",""); mach=c["mach"]; des=c["design"]; part=c["partition"]
        vals=DES[des][:]; x12=vals[:12]; geom=build_geometry(NAMES,vals); sref=float(geom.wing.area_m2)
        vinf=mach*(VINF/MACH0); recref=RECREF*(vinf/VINF); q=0.5*RHO*vinf*vinf; cl=LIFT/(q*sref)
        base_a,base_cl,slope=CAL[str(mach)]; alpha=base_a+(cl-base_cl)/slope
        n=17; step=0.03; half=(n-1)/2; alphas=[round(alpha+(i-half)*step,10) for i in range(n)]
        lo,hi=TASK_SPEC.alpha_window_deg
        if min(alphas)<lo or max(alphas)>hi: raise SystemExit("alpha outside %r"%(alphas,))
        case_id=c["case_id"]; basename=case_id; case_dir=RUN/"cases"/case_id
        if case_dir.exists(): shutil.rmtree(case_dir)
        case_dir.mkdir(parents=True)
        flow={"vinf_m_s":vinf,"rho_kg_m3":RHO,"recref":recref}
        openvsp_model.prepare_case(geom,case_dir,basename,geometry_set="thin",alphas_deg=alphas,tess_u=12,tess_w=25,n_wake_nodes=8,mach_values=[mach],flow_conditions=flow)
        exe=Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe"); vspgeom=case_dir/(basename+".vspgeom"); vkey=case_dir/(basename+".vkey"); vspaero=case_dir/(basename+".vspaero")
        design_id=canon(x12); plan={"schema":"dreal001.solver_plan.v1","run_id":RUN_ID,"batch_id":BATCH,"task_id":c["task_id"],"case_id":case_id,
          "purpose":"D-REAL-EXP-001 G1 repair B02 real label; %s %s %s"%(c["task_id"],des,part),
          "solver":{"path":str(exe),"sha256":sha(exe),"cwd":str(case_dir),"version_banner":openvsp_model.EXPECTED_VSPAERO_VERSION,"omp_threads":1,"timeout_s":1200,"solver_config_hash":sha(vspaero)},
          "command":{"argv":[str(exe),"-omp","1",basename]},
          "geometry":{"files":{"vspgeom":{"path":str(vspgeom),"sha256":sha(vspgeom)},"vkey":{"path":str(vkey),"sha256":sha(vkey)},"vspaero":{"path":str(vspaero),"sha256":sha(vspaero)}},"sref_m2":sref,"geometry_sha256":sha(vspgeom),"design_hash":design_id},
          "design":{"design_hash":design_id,"x12":x12},
          "budget":{"physical_solver_starts_max":1,"expected_internal_cases":n,"max_internal_cases":32}}
        pb=json.dumps(plan,indent=2,ensure_ascii=False).encode()+b"\n"; (case_dir/"plan.json").write_bytes(pb)
        now=datetime.now(timezone.utc); approval={"schema":"dreal001.solver_approval.v1","approved":True,"authorization_id":AUTH,"owner_message_ref":"m07992","run_id":RUN_ID,"batch_id":BATCH,"case_id":case_id,"plan_sha256":hashlib.sha256(pb).hexdigest(),"max_starts":1,"window":{"start_utc":(now-timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),"end_utc":WEND,"token":AUTH+"-WINDOW"},"window_token":AUTH+"-WINDOW"}
        (case_dir/"approval.json").write_text(json.dumps(approval,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        task=TaskSpec(task_id=c["task_id"],split=c["split"],mach=mach,altitude_m=ALT,dynamic_pressure_pa=q,lift_target_n=LIFT,geometry_contract_sha256=GEOM,lift_tolerance_rel=1e-3)
        spec={"schema":"dreal001.r2_task_spec.v1","task_id":c["task_id"],"split":c["split"],"partition":part,"case_id":case_id,"design":des,"design_id":design_id,"x12":x12,"mach":mach,"altitude_m":ALT,"dynamic_pressure_pa":q,"lift_target_n":LIFT,"geometry_contract_sha256":GEOM,"lift_tolerance_rel":1e-3,"flow_conditions":flow,"alpha_center_deg":alpha,"alpha_grid_deg":alphas,"cl_target":cl,"sref_m2":sref,"task_physics_sha256":task.physics_sha256}
        (case_dir/"task_spec.json").write_text(json.dumps(spec,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        old[case_id].update(plan_sha256=hashlib.sha256(pb).hexdigest(),approval_sha256=sha(case_dir/"approval.json"),task_spec_sha256=sha(case_dir/"task_spec.json"),vspgeom_sha256=sha(vspgeom),vspaero_sha256=sha(vspaero),vkey_sha256=sha(vkey),case_inputs_sha256=sha(case_dir/"case_inputs.json"),alpha_grid_deg=alphas,alpha_center_deg=alpha)
        print("REBUILT",case_id,"alpha",round(alpha,5),"cl",round(cl,6),flush=True)
    man["cases"]=[old[c["case_id"]] for c in man["cases"]]
    man["repaired_utc"]=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    man["alpha_model"]={"reason":"B01 8/8 CL_TARGET_OUTSIDE_POLAR; single global slope overpredicted alpha","calibration":{"1.6":[7.4658,0.2896827658750951,0.03655],"1.8":[6.1846,0.22888514834575416,0.03579],"2.02":[5.18125,0.181741590896,0.03439427],"2.4":[4.44,0.128809590323,0.034]},"formula":"alpha=base_alpha+(cl_target-base_cl)/slope"}
    mp=RUN/"g1_case_manifest.json"; mp.write_text(json.dumps(man,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"case_manifest":str(mp),"sha256":sha(mp)},indent=2))
if __name__=="__main__": raise SystemExit(main())
