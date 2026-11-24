from pathlib import Path
import json
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
C=R/'cases'/'O1-M190'
first=json.loads(sorted(C.rglob('case_result.json'))[0].read_text(encoding='utf-8'))
lm=first['evaluation']['lift_match']
print(json.dumps(lm,ensure_ascii=False)[:1500])
print('--- constraints')
print(json.dumps(first['evaluation'].get('constraints'),ensure_ascii=False)[:800])
