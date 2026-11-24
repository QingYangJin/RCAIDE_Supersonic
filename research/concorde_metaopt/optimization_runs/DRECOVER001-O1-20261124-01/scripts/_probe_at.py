import json
from pathlib import Path
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
a=json.loads((R/'o1_arm_SOBOL_BO.json').read_text(encoding='utf-8'))
print(json.dumps(a['anytime'][0],ensure_ascii=False))
print('n anytime', len(a['anytime']))
print('totals', json.dumps(a['totals'],ensure_ascii=False))
