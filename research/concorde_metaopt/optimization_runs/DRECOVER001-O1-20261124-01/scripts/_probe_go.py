import json
from pathlib import Path
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
go=json.loads((R/'o1_go_record.json').read_text(encoding='utf-8'))
for k,v in go.items():
    print(k,'=', json.dumps(v,ensure_ascii=False)[:300])
