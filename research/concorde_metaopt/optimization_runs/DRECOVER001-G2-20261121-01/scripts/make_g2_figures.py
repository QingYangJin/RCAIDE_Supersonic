import csv, json, shutil
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
OUT=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120/research/concorde_metaopt/optimization_runs/DRECOVER001-G2-20261121-01")
FIG=RUN/"figures"; FIG.mkdir(parents=True,exist_ok=True)
plt.rcParams["font.sans-serif"]=["Microsoft YaHei","SimHei"]; plt.rcParams["axes.unicode_minus"]=False
rows=list(csv.DictReader((RUN/"all_evaluations.csv").open(encoding="utf-8")))
adm={r["case_id"]:r for r in csv.DictReader((RUN/"admitted_labels.csv").open(encoding="utf-8"))}
for r in rows:
    r["admitted"]=r["case_id"] in adm
    r["di_n_kN"]=round(float(adm[r["case_id"]]["di_n"])/1000,6) if r["admitted"] else ""
fields=["case_id","stage","task_id","split","partition","design","mach","q_pa","cl_target","lift_match_status","cert_status","admitted","di_n_kN"]
with (FIG/"figure_data.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader()
    for r in rows: w.writerow(r)
colors={"train":"#1f77b4","val":"#ff7f0e","test":"#2ca02c"}
# Only labels exist for M160 (Mach 1.6) support designs d00-d03.
fig,ax=plt.subplots(figsize=(8.2,4.8),dpi=170)
for r in rows:
    if not r["admitted"]: continue
    x=int(r["design"][1:])
    y=float(r["di_n_kN"])
    ax.scatter(x,y,s=92,color=colors.get(r["split"],"#333"),edgecolor="black",linewidth=0.6,zorder=3)
    ax.annotate(r["case_id"].replace("g2-",""),(x,y),textcoords="offset points",xytext=(0,7),ha="center",fontsize=6.5)
ax.set_xticks(range(8)); ax.set_xticklabels(["d00 基准","d01 面积+1%","d02 后掠+0.5°","d03 面积-1%","d04 后掠-0.5°","d05 垂尾+2%","d06 后掠2+0.5°","d07 机身+1%"],fontsize=7)
ax.set_xlim(-0.6,7.6)
ax.set_xlabel("设计编号（B01 只有 M160 任务产生 4 条标签，其余 7 个任务仍待 B02 及后续批次）")
ax.set_ylabel("匹配升力下的诱导阻力 $D_i$ (kN)")
ax.set_title("Issue #13 G2 B01：4 条真实 VSPAERO 准入标签（24 starts；同机；未做物理验证）")
ax.grid(True,alpha=0.3); fig.tight_layout(); fig.savefig(FIG/"admitted_di_n_by_task_design_b01.png"); plt.close(fig)
actual=24; completed=23
failed=sum(1 for r in rows if r["failure_kind"]=="AUDIT_FAILED")
interrupted=sum(1 for r in rows if r["failure_kind"]=="NULL_SOLVER_NO_RESULT_INTERRUPTED")
screen=sum(1 for r in rows if r["failure_kind"]=="SCREENING_ONLY_NOT_ADMITTED")
labels=["实际启动","完成求解","准入标签","筛选未准入","审计失败","中断无结果"]
vals=[actual,completed,len(adm),screen,failed,interrupted]
fig,ax=plt.subplots(figsize=(7.4,4.2),dpi=170)
bars=ax.bar(labels,vals,color=["#4c78a8","#72b7b2","#54a24b","#e45756","#f58518"])
for b,v in zip(bars,vals): ax.text(b.get_x()+b.get_width()/2,v+0.3,str(v),ha="center",va="bottom")
ax.set_ylabel("计数"); ax.set_title("G2 B01：24 starts、23 完成求解、4 条标签（4/23=17.4%，未达 70%）")
ax.tick_params(axis="x",labelsize=8); fig.tight_layout(); fig.savefig(FIG/"batch_outcome_overview_b01.png"); plt.close(fig)
print(json.dumps({"figures":[str(FIG/"admitted_di_n_by_task_design_b01.png"),str(FIG/"batch_outcome_overview_b01.png")],"figure_data":str(FIG/"figure_data.csv"),"admitted":len(adm),"completed":completed,"failed":failed,"interrupted":interrupted,"screening":screen},indent=2))
