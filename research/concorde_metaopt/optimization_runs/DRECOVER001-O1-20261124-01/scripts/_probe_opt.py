import json
from pathlib import Path
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
res=json.loads((R/'o1_result.json').read_text(encoding='utf-8'))
print('not_claimed', res['not_claimed'])
print('evidence_scope', res['evidence_scope'], 'physics_validated', res['physics_validated'])
print('protocol', res['protocol_id'])
O=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01')
d=json.loads((O/'final_aircraft/optimized_design.json').read_text(encoding='utf-8'))
print('opt design keys', list(d.keys()))
print(json.dumps(d,ensure_ascii=False)[:2500])
