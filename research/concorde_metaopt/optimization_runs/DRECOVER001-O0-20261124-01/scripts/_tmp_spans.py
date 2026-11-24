
import json, glob
from pathlib import Path
def read_polar(path):
    rows, seen = [], False
    for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if not seen:
            if line.strip().startswith('Beta') and 'AoA' in line: seen = True
            continue
        p = line.split()
        if len(p) < 9: continue
        try: v = [float(x) for x in p]
        except ValueError: continue
        rows.append((v[2], v[6], v[8]))
    return rows
roots = ['DRECOVER001-R2-20261120-01','DRECOVER001-G1-20261121-01','DRECOVER001-G2-20261121-01','DRECOVER001-P1-20261122-02','DRECOVER001-P2-20261123-01']
for root in roots:
    for case in sorted(glob.glob('D:/RCAIDE/.real_runs/'+root+'/cases/*')):
        pols = sorted(glob.glob(case+'/*.polar'))
        spec = Path(case)/'task_spec.json'
        if not pols or not spec.is_file(): continue
        try: t = json.loads(spec.read_text(encoding='utf-8'))
        except Exception: continue
        if abs(float(t.get('mach') or 0)-2.02) > 1e-9: continue
        rows = read_polar(pols[0])
        if not rows: continue
        span = rows[-1][0]-rows[0][0]
        print('%-28s %-22s n=%2d alpha %.4f..%.4f span %.3f' % (root[12:], Path(case).name, len(rows), rows[0][0], rows[-1][0], span))
