from pathlib import Path
import json, statistics
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
C=R/'cases'/'O1-M190'
rows=[]
for cert in sorted(C.rglob('admission_certificate.json')):
    c=json.loads(cert.read_text(encoding='utf-8'))
    case=cert.parent
    rel=str(case.relative_to(C))
    rows.append((rel, c['status'], c['di_n'], c['cl'], c['cdi'], c['alpha_deg'], c['partition'], c['sref_m2'], c['q_pa']))
print('cert count', len(rows))
for r in rows: print(r)
