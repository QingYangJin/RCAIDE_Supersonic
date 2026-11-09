
import json, hashlib, os, statistics as st
RUN=r'<STATE_ROOT>/s3_runs/p4ra-s3-formal-20261109T1310Z'
OUT=r'<STATE_ROOT>/EXT/p4-route-a/lead/s3'
p=os.path.join(RUN,'ood_records.jsonl')
rows=[]
with open(p,encoding='utf-8') as f:
    for line in f:
        d=json.loads(line)
        rows.append(d)
print('records',len(rows))
# group by run_id
runs={}
for d in rows:
    runs.setdefault(d['run_id'],[]).append(d)
print('runs',len(runs))
# per run endpoints
per_run={}
for rid,recs in runs.items():
    r0=recs[0]
    B=r0['budget']
    feas=[r for r in recs if r.get('feasible')]
    hit=len(feas)/B
    best=min(r['f'] for r in feas) if feas else None
    per_run[rid]={'task_id':r0['task_id'],'budget':B,'arm':r0['arm_id'],'meta_seed':r0['meta_seed'],'opt_seed':r0['opt_seed'],
                  'n_records':len(recs),'n_feasible':len(feas),'feasible_hit_rate':hit,'best_feasible_value':best}
# per (task,budget,arm) mean over seeds
cells={}
for rid,v in per_run.items():
    cells.setdefault((v['task_id'],v['budget'],v['arm']),[]).append(v['feasible_hit_rate'])
def mean(xs): return sum(xs)/len(xs)
tasks=sorted({v['task_id'] for v in per_run.values()})
budgets=sorted({v['budget'] for v in per_run.values()})
arms=sorted({v['arm'] for v in per_run.values()})
print('tasks',len(tasks),'budgets',budgets,'arms',len(arms))
lines=[]
for b in budgets:
    for a in arms:
        for t in tasks:
            xs=cells[(t,b,a)]
            lines.append((t,b,a,len(xs),mean(xs)))
csv_path=os.path.join(OUT,'ood_supplementary_descriptives.csv')
with open(csv_path,'w',encoding='utf-8',newline='\n') as fh:
    fh.write('task_id,budget,arm,n_seed_runs,feasible_hit_rate_mean\n')
    for t,b,a,n,m in lines:
        fh.write('%s,%d,%s,%d,%.12f\n'%(t,b,a,n,m))
summary={'schema_version':'p4ra-s3-ood-supplementary-1',
 'label':'LEAD_AUXILIARY_NOT_FROM_FROZEN_ANALYZER',
 'purpose':'S3 预注册 OOD 描述性端点；冻结分析器 build_ood_rows 未接入独立 OOD 记录流（A5-S3M5-01 / A7-F-03），本文件为 Lead 辅助脚本对该流的描述性汇总，非确认性推断，不替代冻结分析器产物。',
 'source_file':os.path.join(RUN,'ood_records.jsonl'),
 'source_bytes':os.path.getsize(p),
 'source_sha256':hashlib.sha256(open(p,'rb').read()).hexdigest(),
 'record_count':len(rows),'run_count':len(runs),'task_count':len(tasks),'budgets':budgets,'arms':arms,
 'seeds_per_cell':'meta_seed 0 x opt_seed 0..2 = 3 次 run per (task,budget,arm) cell',
 'aggregation':'先对每 (task,budget,arm) 的 3 次 run 取 feasible_hit_rate 均值，再对 10 个 OOD task 取均值',
 'evidence_scope':'DEVELOPMENT_VALIDATION_ONLY',
 'inference':'NONE_DESCRIPTIVE_ONLY'}
per_budget={}
for b in budgets:
    for a in arms:
        vals=[mean(cells[(t,b,a)]) for t in tasks]
        per_budget.setdefault(str(b),{})[a]=mean(vals)
summary['arm_means_by_budget']=per_budget
summary['con_minus_obj_by_budget']={str(b): per_budget[str(b)]['S3-BO-FOMAML-CON']-per_budget[str(b)]['S3-BO-FOMAML-OBJ'] for b in budgets}
summary['csv_sha256']=hashlib.sha256(open(csv_path,'rb').read()).hexdigest()
json_path=os.path.join(OUT,'ood_supplementary_summary.json')
with open(json_path,'w',encoding='utf-8',newline='\n') as fh:
    json.dump(summary,fh,ensure_ascii=False,indent=1)
    fh.write('\n')
print(json.dumps(summary['arm_means_by_budget'],ensure_ascii=False,indent=1))
print(json.dumps(summary['con_minus_obj_by_budget'],ensure_ascii=False))
print('csv',os.path.getsize(csv_path),summary['csv_sha256'])
print('json',os.path.getsize(json_path),hashlib.sha256(open(json_path,'rb').read()).hexdigest())
