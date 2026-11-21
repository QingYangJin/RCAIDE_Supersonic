
import argparse, hashlib, json, math, shutil, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
CASE_ROOT = RUN / "cases"
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.aircraft.geometry_model import build_geometry
from research.concorde_metaopt.dreal001.geometry import openvsp_model
from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec

RUN_ID = "DRECOVER001-G2-20261121-01"
AUTH_ID = "AUTH-DREAL003-G2-20261121-01"
OWNER_REF = "m08739"
WINDOW_END = "2026-11-23T00:00:00Z"
GEOM = "5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15"
LIFT = 1333704.4
ALT = 18288.0
BASE_MACH = 2.02
BASE_VINF = 596.0373972278921
BASE_RHO = 0.1153178340089936
BASE_RECREF = 89397005.8767656
EXE = Path(r"D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe")

NAMES=["wing_area","aspect_ratio","sweep_1","sweep_2","sweep_3","span_location_2",
       "span_location_3","chord_ratio_2","chord_ratio_3","tip_twist",
       "vertical_tail_area","vertical_tail_sweep_delta","fuselage_length",
       "fuselage_fineness","fuselage_height_width_ratio"]
BASELINE=[358.25,1.83,67.0,48.0,71.0,0.480469,0.945313,0.408284,0.130178,0.0,
          33.91,0.0,61.66,4.30,1.152778]
DES={k:BASELINE[:] for k in ("d00","d01","d02","d03","d04","d05","d06","d07")}
DES["d01"][0]=361.8325
DES["d02"][2]=67.5
DES["d03"][0]=354.6675
DES["d04"][2]=66.5
DES["d05"][10]=34.5882
DES["d06"][3]=48.5
DES["d07"][12]=62.2766
TASKS=[
 ("140","DREAL003-G2-M140",1.40,"train"),
 ("160","DREAL003-G2-M160",1.60,"train"),
 ("180","DREAL003-G2-M180",1.80,"val"),
 ("200","DREAL003-G2-M200",2.00,"train"),
 ("202","DREAL003-G2-M202",2.02,"train"),
 ("220","DREAL003-G2-M220",2.20,"val"),
 ("240","DREAL003-G2-M240",2.40,"test"),
 ("260","DREAL003-G2-M260",2.60,"test"),
]
SUPPORT=("d00","d01","d02","d03")
QUERY=("d04","d05","d06","d07")

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for c in iter(lambda:f.read(1<<20),b""): h.update(c)
    return h.hexdigest()
def canon(p):
    return hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def stage1_alphas():
    lo,hi=TASK_SPEC.alpha_window_deg
    n=49
    step=(hi-lo)/(n+1)
    return [round(lo+step*(i+1),10) for i in range(n)], step

def flow_for(mach):
    vinf=mach*(BASE_VINF/BASE_MACH)
    recref=BASE_RECREF*(vinf/BASE_VINF)
    q=0.5*BASE_RHO*vinf*vinf
    return vinf,recref,q

def make_case(c, stage, alphas, alpha_center, cl_target, batch_id):
    tag=c["tag"]; design=c["design"]; mach=c["mach"]; split=c["split"]; part=c["partition"]
    case_id="g2-m%s-%s-%s-s%d"%(tag,design,part,stage)
    case_dir=CASE_ROOT/case_id
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    vals=DES[design][:]; x12=vals[:12]
    geom=build_geometry(NAMES,vals); sref=float(geom.wing.area_m2)
    vinf,recref,q=flow_for(mach)
    flow={"vinf_m_s":vinf,"rho_kg_m3":BASE_RHO,"recref":recref}
    openvsp_model.prepare_case(geom,case_dir,case_id,geometry_set="thin",alphas_deg=alphas,
        tess_u=12,tess_w=25,n_wake_nodes=8,mach_values=[mach],flow_conditions=flow)
    vspgeom=case_dir/(case_id+".vspgeom"); vkey=case_dir/(case_id+".vkey"); vspaero=case_dir/(case_id+".vspaero")
    design_id=canon(x12)
    plan={"schema":"dreal001.solver_plan.v1","run_id":RUN_ID,"batch_id":batch_id,
      "task_id":c["task_id"],"case_id":case_id,
      "purpose":"D-REAL-EXP-001 G2 %s alpha scan; %s %s %s"%(stage,c["task_id"],design,part),
      "solver":{"path":str(EXE),"sha256":sha(EXE),"cwd":str(case_dir),
                "version_banner":openvsp_model.EXPECTED_VSPAERO_VERSION,"omp_threads":1,
                "timeout_s":600,"solver_config_hash":sha(vspaero)},
      "command":{"argv":[str(EXE),"-omp","1",case_id]},
      "geometry":{"files":{"vspgeom":{"path":str(vspgeom),"sha256":sha(vspgeom)},
                           "vkey":{"path":str(vkey),"sha256":sha(vkey)},
                           "vspaero":{"path":str(vspaero),"sha256":sha(vspaero)}},
                  "sref_m2":sref,"geometry_sha256":sha(vspgeom),"design_hash":design_id},
      "design":{"design_hash":design_id,"x12":x12},
      "budget":{"physical_solver_starts_max":1,"expected_internal_cases":len(alphas),
                "max_internal_cases":64}}
    pb=json.dumps(plan,indent=2,ensure_ascii=False).encode()+b"\n"
    (case_dir/"plan.json").write_bytes(pb)
    t=datetime.now(timezone.utc)
    approval={"schema":"dreal001.solver_approval.v1","approved":True,"authorization_id":AUTH_ID,
      "owner_message_ref":OWNER_REF,"run_id":RUN_ID,"batch_id":batch_id,"case_id":case_id,
      "plan_sha256":hashlib.sha256(pb).hexdigest(),"max_starts":1,
      "window":{"start_utc":(t-timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_utc":WINDOW_END,"token":AUTH_ID+"-WINDOW"},
      "window_token":AUTH_ID+"-WINDOW"}
    (case_dir/"approval.json").write_text(json.dumps(approval,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    task=TaskSpec(task_id=c["task_id"],split=split,mach=mach,altitude_m=ALT,
                  dynamic_pressure_pa=q,lift_target_n=LIFT,geometry_contract_sha256=GEOM,
                  lift_tolerance_rel=1e-3)
    spec={"schema":"dreal001.r2_task_spec.v1","task_id":c["task_id"],"split":split,
      "partition":part,"case_id":case_id,"design":design,"design_id":design_id,"x12":x12,
      "mach":mach,"altitude_m":ALT,"dynamic_pressure_pa":q,"lift_target_n":LIFT,
      "geometry_contract_sha256":GEOM,"lift_tolerance_rel":1e-3,"flow_conditions":flow,
      "alpha_center_deg":alpha_center,"alpha_grid_deg":alphas,"cl_target":cl_target,
      "sref_m2":sref,"task_physics_sha256":task.physics_sha256,"stage":stage}
    (case_dir/"task_spec.json").write_text(json.dumps(spec,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return {"case_id":case_id,"case_dir":str(case_dir),"stage":stage,
            "task_id":c["task_id"],"split":split,"partition":part,"design":design,
            "mach":mach,"sref_m2":sref,"q_pa":q,"cl_target":cl_target,
            "alpha_center_deg":alpha_center,"alpha_min_deg":min(alphas),"alpha_max_deg":max(alphas),
            "alpha_points":len(alphas),"x12":x12,
            "plan_sha256":hashlib.sha256(pb).hexdigest(),
            "approval_sha256":sha(case_dir/"approval.json"),
            "task_spec_sha256":sha(case_dir/"task_spec.json"),
            "vspgeom_sha256":sha(vspgeom),"vspaero_sha256":sha(vspaero),
            "vkey_sha256":sha(vkey),"case_inputs_sha256":sha(case_dir/"case_inputs.json")}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stage",type=int,required=True,choices=[1,2])
    ap.add_argument("--batch-id",default="DRECOVER001-G2-20261121-01-MAIN")
    ap.add_argument("--case-ids",default=None,help="comma separated stage1 case ids")
    a=ap.parse_args()
    CASE_ROOT.mkdir(parents=True,exist_ok=True)
    base=[]
    for tag,task_id,mach,split in TASKS:
        for design in SUPPORT+QUERY:
            base.append({"tag":tag,"task_id":task_id,"mach":mach,"split":split,
                         "design":design,"partition":"support" if design in SUPPORT else "query"})
    if a.stage==1:
        alphas,step=stage1_alphas()
        out=[]
        for c in base:
            vinf,recref,q=flow_for(c["mach"])
            geom=build_geometry(NAMES,DES[c["design"]])
            sref=float(geom.wing.area_m2)
            cl=LIFT/(q*sref)
            alpha_center=sum(alphas)/len(alphas)
            out.append(make_case(c,1,alphas,alpha_center,cl,a.batch_id))
            print("BUILT",out[-1]["case_id"],"cl",round(cl,6),"sref",round(sref,3),flush=True)
        mp=RUN/"g2_stage1_manifest.json"
        man={"schema":"dreal003.g2_stage1_manifest.v1","run_id":RUN_ID,"authorization_id":AUTH_ID,
             "stage1_alpha_points":len(alphas),"stage1_alpha_step_deg":step,
             "case_count":len(out),"cases":out,"created_utc":now()}
        mp.write_text(json.dumps(man,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(json.dumps({"manifest":str(mp),"case_count":len(out),"sha256":sha(mp)},indent=2))
        return 0
    # stage 2
    man=json.loads((RUN/"g2_stage1_manifest.json").read_text(encoding="utf-8"))
    s1={c["case_id"]:c for c in man["cases"]}
    ids=a.case_ids.split(",") if a.case_ids else list(s1)
    out=[]
    for cid in ids:
        c=s1[cid]
        d=CASE_ROOT/cid
        resf=d/"case_result.json"
        if not resf.exists():
            print("SKIP_NO_RESULT",cid,flush=True); continue
        res=json.loads(resf.read_text(encoding="utf-8"))
        ev=res.get("evaluation") or {}
        lm=ev.get("lift_match") or {}
        pts=lm.get("points") or []
        if len(pts)<5:
            print("SKIP_INSUFFICIENT_POINTS",cid,len(pts),flush=True); continue
        x=[float(p[0]) for p in pts]; y=[float(p[1]) for p in pts]
        n=len(x); mx=sum(x)/n; my=sum(y)/n
        den=sum((v-mx)**2 for v in x)
        if den<=0:
            print("SKIP_DEGENERATE",cid,flush=True); continue
        slope=sum((u-mx)*(v-my) for u,v in zip(x,y))/den
        ss_res=sum((v-(my+slope*(u-mx)))**2 for u,v in zip(x,y))
        ss_tot=sum((v-my)**2 for v in y)
        r2=1.0-(ss_res/ss_tot) if ss_tot>0 else 0.0
        if r2<0.99:
            print("SKIP_LOW_R2",cid,round(r2,6),flush=True); continue
        cl_target=float(lm.get("cl_target") or c["cl_target"])
        alpha_t=float((cl_target-(my-slope*mx))/slope)
        alphas=[round(alpha_t+0.001*(i-6),10) for i in range(13)]
        part={"tag":cid.split("-")[1][1:],"task_id":c["task_id"],"mach":c["mach"],
              "split":c["split"],"design":c["design"],"partition":c["partition"]}
        out.append(make_case(part,2,alphas,alpha_t,cl_target,a.batch_id))
        out[-1]["stage1_case_id"]=cid
        out[-1]["stage1_slope_cl_per_deg"]=slope
        out[-1]["stage1_regression_r2"]=r2
        out[-1]["stage1_regression_points"]=n
        out[-1]["stage1_alpha_target_deg"]=alpha_t
        print("BUILT2",out[-1]["case_id"],"alpha_t",round(alpha_t,5),"slope",round(slope,6),flush=True)
    mp=RUN/"g2_stage2_manifest.json"
    man2={"schema":"dreal003.g2_stage2_manifest.v1","run_id":RUN_ID,"authorization_id":AUTH_ID,
          "refinement":{"points":13,"step_deg":0.001,"half_width_deg":0.006,
                        "method":"local linear regression of stage1 polar CL(alpha); center=exact lift target; no extra coarse start"},
          "case_count":len(out),"cases":out,"created_utc":now()}
    mp.write_text(json.dumps(man2,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"manifest":str(mp),"case_count":len(out),"sha256":sha(mp)},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())