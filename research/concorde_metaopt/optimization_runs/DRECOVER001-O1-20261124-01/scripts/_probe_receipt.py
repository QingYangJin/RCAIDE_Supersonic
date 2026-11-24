from pathlib import Path
import json
O0=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01')
r=json.loads((O0/'final_aircraft'/'verification_receipt.json').read_text(encoding='utf-8'))
print('receipt keys', list(r.keys()))
print('verdict', r.get('verdict'))
print('wake probe', json.dumps(r.get('wake_sensitivity_probe'),ensure_ascii=False)[:1200])
print('budget', json.dumps(r.get('verification_budget'),ensure_ascii=False)[:400])
print('repeat spread', r.get('repeat_spread_di_n'), 'improvement', r.get('improvement_di_n'), r.get('improvement_fraction'))
print('disclosure', json.dumps(r.get('disclosure'),ensure_ascii=False)[:800])
v=json.loads((O0/'o0_final'/'o0_final_verdict.json').read_text(encoding='utf-8'))
print('ledger totals', json.dumps(v['ledger'].get('totals'),ensure_ascii=False)[:400])
c=json.loads((O0/'o0_batch_close_B02.json').read_text(encoding='utf-8'))
print('batch close', json.dumps({k:c[k] for k in ('outcome','was_any_cap_exceeded','batch_spend','authorization_spend','improvement_n','improvement_fraction_of_baseline','feedback_dependent','physics_validated')},ensure_ascii=False)[:900])
