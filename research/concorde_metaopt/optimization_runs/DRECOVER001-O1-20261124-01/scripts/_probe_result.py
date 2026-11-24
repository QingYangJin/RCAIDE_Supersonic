from pathlib import Path
import json
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
C=R/'cases'/'O1-M190'
sample=C/'SUPPORT'/'o1-s00-refine'
d=json.loads((sample/'case_result.json').read_text(encoding='utf-8'))
print(type(d), list(d.keys()) if isinstance(d,dict) else '')
print(json.dumps(d,ensure_ascii=False)[:1200])
print('--- task_spec keys')
t=json.loads((sample/'task_spec.json').read_text(encoding='utf-8'))
print(json.dumps(t,ensure_ascii=False)[:900])
