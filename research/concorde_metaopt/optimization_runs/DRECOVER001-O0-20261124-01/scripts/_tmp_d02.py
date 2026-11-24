
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
base = Path('D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/cases/m202-d02-query')
pol = sorted(base.glob('*.polar'))[0]
rows = read_polar(pol)
t = json.loads((base/'task_spec.json').read_text(encoding='utf-8'))
print('cl_target', t.get('cl_target'), 'sref', t.get('sref_m2'))
print('n rows', len(rows), 'alpha', rows[0][0], rows[-1][0])
print('max alpha CL', rows[-1][1])
slope = (rows[-1][1]-rows[0][1])/(rows[-1][0]-rows[0][0])
print('slope', slope)
print('alpha needed (linear ext.)', rows[0][0] + (t['cl_target']-rows[0][1])/slope)
# quadratic fit
xs=[r[0] for r in rows]; ys=[r[1] for r in rows]
import statistics
n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
sxx=sum((x-mx)**2 for x in xs); sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys))
sxx2=sum((x-mx)**3 for x in xs); sxx4=sum((x-mx)**4 for x in xs); sxy2=sum((x-mx)**2*(y-my) for x,y in zip(xs,ys))
det=sxx*sxx4-sxx2*sxx2
b=(sxy*sxx4-sxy2*sxx2)/det; a2=(sxx*sxy2-sxx2*sxy)/det
import math
A=a2; B=b; C=my - b*mx - a2*mx
disc=B*B-4*A*(C-t['cl_target'])
print('quad roots', [(-B+s*math.sqrt(disc))/(2*A) for s in (1,-1)])
