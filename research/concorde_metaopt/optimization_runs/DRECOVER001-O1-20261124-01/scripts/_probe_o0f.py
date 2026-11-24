from pathlib import Path
import json
O0=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01')
O1=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
for f in ('o0_final/o0_final_verdict.json','o0_final/o0_final_plan.json','o0_final/verification_ledger.json'):
    p=O0/f
    print('===',f, p.exists(), p.stat().st_size if p.exists() else '')
    if p.exists():
        d=json.loads(p.read_text(encoding='utf-8'))
        print(json.dumps(d,ensure_ascii=False)[:1500])
print()
print('=== O0 final_aircraft listing')
for f in sorted((O0/'final_aircraft').rglob('*')):
    if f.is_file(): print('%-60s %9d' % (str(f.relative_to(O0)), f.stat().st_size))
print()
print('=== O0 receipt')
print(json.dumps(json.loads((O0/'upload_receipt.json').read_text(encoding='utf-8')),ensure_ascii=False)[:1200])
print()
print('=== O1 figure manifest final_aircraft')
print((O1/'final_aircraft'/'figures'/'figure_manifest.json').read_text(encoding='utf-8')[:1500])
