from pathlib import Path
import json
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
d=R/'cases'/'O1-M190'/'ARM_SOBOL_BO'/'o1-d06-refine'
print(sorted(f.name for f in d.iterdir() if f.is_file()))
print('--- arm json keys')
a=json.loads((R/'o1_arm_SOBOL_BO.json').read_text(encoding='utf-8'))
print(list(a.keys()))
print('totals', json.dumps(a.get('totals'),ensure_ascii=False)[:500])
print('ranking[:2]', json.dumps(a.get('ranking')[:2],ensure_ascii=False)[:800])
print('records[0]', json.dumps(a.get('records')[0],ensure_ascii=False)[:900])
