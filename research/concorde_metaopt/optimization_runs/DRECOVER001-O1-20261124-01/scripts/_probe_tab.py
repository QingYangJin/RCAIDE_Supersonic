from pathlib import Path
import json
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
res=json.loads((R/'o1_result.json').read_text(encoding='utf-8'))
print('COST', json.dumps(res['cost'],ensure_ascii=False,indent=1))
print('PE', json.dumps(res['primary_endpoint'],ensure_ascii=False,indent=1)[:1200])
print('REGRESSION keys', list(res['regression'].keys()))
for n in ('o1_three_arm_endpoint.csv','o1_anytime_trace.csv','o1_solver_case_ledger.csv','o1_best_design_vs_baseline.csv','o1_all_designs_all_arms.csv'):
    t=(R/'tables'/n).read_text(encoding='utf-8').splitlines()
    print('==',n,len(t),'lines'); print('\n'.join(t[:3]))
