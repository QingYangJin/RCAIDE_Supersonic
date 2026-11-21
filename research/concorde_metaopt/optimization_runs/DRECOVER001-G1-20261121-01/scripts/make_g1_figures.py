
import csv, json, shutil
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01")
OUT=Path(r"D:/RCAIDE/.worktrees/dreal003-g0-20261120/research/concorde_metaopt/optimization_runs/DRECOVER001-G1-20261121-01")
FIG=RUN/"figures"; FIG.mkdir(parents=True,exist_ok=True)
plt.rcParams["font.sans-serif"]=["Microsoft YaHei","SimHei"]; plt.rcParams["axes.unicode_minus"]=False
rows=list(csv.DictReader((RUN/"all_evaluations.csv").open(encoding="utf-8")))
adm={r["case_id"]:r for r in csv.DictReader((RUN/"admitted_labels.csv").open(encoding="utf-8"))}
for r in rows:
    r["admitted"]=r["case_id"] in adm
    r["di_n_kN"]=round(float(adm[r["case_id"]]["di_n"])/1000,6) if r["admitted"] else ""
fields=["case_id","task_id","split","partition","design","mach","q_pa","cl_target","lift_match_status","cert_status","admitted","di_n_kN"]
with (FIG/"figure_data.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader()
    for r in rows: w.writerow(r)
colors={"train":"#1f77b4","val":"#ff7f0e","test":"#2ca02c"}
offsets={1.6:-0.27,1.8:-0.09,2.02:0.09,2.4:0.27}
fig,ax=plt.subplots(figsize=(8.6,5.1),dpi=170)
for r in rows:
    if not r["admitted"]: continue
    x=int(r["design"][1:])+offsets[float(r["mach"])]
    y=float(r["di_n_kN"])
    ax.scatter(x,y,s=78,color=colors.get(r["split"],"#333"),edgecolor="black",linewidth=0.6,zorder=3)
ax.set_xticks(range(6)); ax.set_xticklabels(["d00 基准","d01 面积+1%","d02 后掠+0.5°","d03 面积-1%","d04 后掠-0.5°","d05 垂尾+2%"],fontsize=8)
ax.set_xlim(-0.6,5.6); ax.set_ylim(98,150)
ax.set_xlabel("设计编号（每个设计按马赫数轻微左右错开；只画有准入标签的 case）")
ax.set_ylabel("匹配升力下的诱导阻力 $D_i$ (kN)")
ax.set_title("Issue #13 G1：8 条真实 VSPAERO 准入标签（24 starts；同机；未做物理验证）")
handles=[Line2D([0],[0],marker="o",color="w",markerfacecolor=colors[k],markeredgecolor="black",label=k+" 标签") for k in ("train","val","test")]
ax.legend(handles=handles,fontsize=8,loc="upper right"); ax.grid(True,alpha=0.3)
ax.text(0.5,0.02,"24 starts 中 16 个 case 无标签（15 个审计升力容差失败 + 1 个启动后无结果）；本图不画这些点",transform=ax.transAxes,ha="center",va="bottom",fontsize=8,color="#555555")
fig.tight_layout(); fig.savefig(FIG/"admitted_di_n_by_mach_design.png"); plt.close(fig)
completed=sum(1 for r in rows if r["status"]=="SOLVED")
failed=sum(1 for r in rows if r["failure_kind"]=="AUDIT_FAILED")
nores=sum(1 for r in rows if r["failure_kind"]=="NO_RESULT")
labels=["实际启动","完成求解","准入标签","审计失败(null)","启动无结果"]
vals=[24,completed,len(adm),failed,nores]
fig,ax=plt.subplots(figsize=(7.4,4.2),dpi=170)
bars=ax.bar(labels,vals,color=["#4c78a8","#72b7b2","#54a24b","#e45756","#f58518"])
for b,v in zip(bars,vals): ax.text(b.get_x()+b.get_width()/2,v+0.3,str(v),ha="center",va="bottom")
ax.set_ylabel("计数"); ax.set_title("G1 批次结果：24 starts，8/23 完成求解获得标签（34.8%）")
ax.tick_params(axis="x",labelsize=8); fig.tight_layout(); fig.savefig(FIG/"batch_outcome_overview.png"); plt.close(fig)
src=Path(__file__).resolve(); dst=(OUT/"scripts/make_g1_figures.py").resolve()
if src!=dst: shutil.copy2(src,dst)
print(json.dumps({"figures":[str(FIG/"admitted_di_n_by_mach_design.png"),str(FIG/"batch_outcome_overview.png")],"figure_data":str(FIG/"figure_data.csv"),"admitted":len(adm),"completed":completed,"failed":failed,"no_result":nores},indent=2))
