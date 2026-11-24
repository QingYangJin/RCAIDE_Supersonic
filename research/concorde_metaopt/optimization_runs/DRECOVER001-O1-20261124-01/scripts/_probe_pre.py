import json
from pathlib import Path
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
pre=json.loads((R/'o1_preregistration.json').read_text(encoding='utf-8'))
print('top keys', list(pre.keys()))
print('carried', json.dumps(pre.get('carried_forward'),ensure_ascii=False)[:800])
