from pathlib import Path
import json
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
for n in ('o1_a4_recompute.json','o1_a4_geometry_identity.json','upload_receipt.json','o1_dossier_receipt.json','o1_binding_verification.json','o1_go_record.json'):
    d=json.loads((R/n).read_text(encoding='utf-8'))
    print('===',n, type(d).__name__)
    if isinstance(d,dict):
        print('keys:', list(d.keys()))
        s=json.dumps(d,ensure_ascii=False)
        print(s[:1200].replace(chr(10),' '))
    print()
