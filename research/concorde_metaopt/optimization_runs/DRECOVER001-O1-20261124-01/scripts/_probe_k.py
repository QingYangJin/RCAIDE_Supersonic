import json
from pathlib import Path
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
cost=json.loads((R/'o1_cost_reconciliation.json').read_text(encoding='utf-8'))
print('COST keys', list(cost.keys()))
print(json.dumps(cost,ensure_ascii=False)[:2500])
print('=== arm record keys')
a=json.loads((R/'o1_arm_SOBOL_BO.json').read_text(encoding='utf-8'))
print(list(a.keys()))
print('record0', json.dumps(a['records'][0],ensure_ascii=False)[:1200])
print('=== upload receipt')
up=json.loads((R/'upload_receipt.json').read_text(encoding='utf-8'))
for k,v in up.items(): print(k,'=',json.dumps(v,ensure_ascii=False)[:200])
