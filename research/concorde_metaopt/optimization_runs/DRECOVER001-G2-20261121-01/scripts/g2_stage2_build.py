
import argparse, hashlib, json, sys
from pathlib import Path
REPO=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120")
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
sys.path.insert(0,str(RUN/"scripts"))
import g2_build as gb
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--case-ids",required=True)
    ap.add_argument("--batch-id",default="DRECOVER001-G2-20261121-01-MAIN")
    a=ap.parse_args()
    man=json.loads((RUN/"g2_stage1_manifest.json").read_text(encoding="utf-8"))
    s1={c["case_id"]:c for c in man["cases"]}
    out=[]
    for cid in a.case_ids.split(","):
        c=s1[cid]; d=Path(c["case_dir"]); resf=d/"case_result.json"
        if not resf.exists(): print("SKIP_NO_RESULT",cid,flush=True); continue
        res=json.loads(resf.read_text(encoding="utf-8"))
        polar=res.get("polar") or {}
        rows=polar.get("unique_case_rows") or polar.get("rows") or []
        rows=[r for r in rows if not (r.get("_invalid_tokens") or {}) and abs(float(r.get("Mach",-1))-float(c["mach"]))<1e-12]
        pts=[(float(r["AoA"]),float(r["CLtot"])) for r in rows]
        if len(pts)<5: print("SKIP_INSUFFICIENT_POINTS",cid,len(pts),flush=True); continue
        x=[p[0] for p in pts]; y=[p[1] for p in pts]; n=len(x)
        mx=sum(x)/n; my=sum(y)/n; den=sum((v-mx)**2 for v in x)
        if den<=0: print("SKIP_DEGENERATE",cid,flush=True); continue
        slope=sum((u-mx)*(v-my) for u,v in zip(x,y))/den
        ss_res=sum((v-(my+slope*(u-mx)))**2 for u,v in zip(x,y)); ss_tot=sum((v-my)**2 for v in y)
        r2=1.0-(ss_res/ss_tot) if ss_tot>0 else 0.0
        if r2<0.99: print("SKIP_LOW_R2",cid,round(r2,6),flush=True); continue
        cl_target=float(c["cl_target"]); alpha_t=float((cl_target-(my-slope*mx))/slope)
        alphas=[round(alpha_t+0.001*(i-6),10) for i in range(13)]
        part={"tag":cid.split("-")[1][1:],"task_id":c["task_id"],"mach":c["mach"],"split":c["split"],"design":c["design"],"partition":c["partition"]}
        item=gb.make_case(part,2,alphas,alpha_t,cl_target,a.batch_id)
        item["stage1_case_id"]=cid; item["stage1_slope_cl_per_deg"]=slope; item["stage1_alpha_target_deg"]=alpha_t
        item["stage1_regression_r2"]=r2; item["stage1_regression_points"]=n
        out.append(item); print("BUILT2",item["case_id"],"alpha_t",round(alpha_t,5),"slope",round(slope,6),"r2",round(r2,6),flush=True)
    mp=RUN/"g2_stage2_manifest.json"
    man2={"schema":"dreal003.g2_stage2_manifest.v1","run_id":gb.RUN_ID,"authorization_id":gb.AUTH_ID,
          "refinement":{"points":13,"step_deg":0.001,"half_width_deg":0.006,
                        "method":"OLS of stage1 raw polar CLtot(AoA) at the case Mach; center=cl_target; admission raw-row only"},
          "builder_sha256":sha(Path(__file__)),"g2_build_sha256":sha(RUN/"scripts/g2_build.py"),
          "case_count":len(out),"cases":out,"created_utc":gb.now()}
    mp.write_text(json.dumps(man2,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"manifest":str(mp),"case_count":len(out),"sha256":sha(mp)},indent=2))
if __name__=="__main__": raise SystemExit(main())
