
import glob, os, json, collections
roots = ['DRECOVER001-G1-20261121-01','DRECOVER001-G2-20261121-01','DRECOVER001-P1-20261122-02','DRECOVER001-P2-20261123-01','DRECOVER001-R2-20261120-01']
seen = collections.OrderedDict()
for root in roots:
    for s in glob.glob('D:/RCAIDE/.real_runs/' + root + '/**/task_spec.json', recursive=True):
        try:
            d = json.load(open(s, encoding='utf-8'))
        except Exception:
            continue
        if abs(float(d.get('mach') or 0) - 2.02) > 1e-9:
            continue
        if not glob.glob(os.path.dirname(s) + '/*.polar'):
            continue
        x = d.get('x12')
        if x is None:
            des = d.get('design')
            x = des.get('x12') if isinstance(des, dict) else None
        key = tuple(round(float(v), 6) for v in x) if x else None
        seen.setdefault(key, []).append(root + '/' + os.path.basename(os.path.dirname(s)))
print('total cases', sum(len(v) for v in seen.values()))
print('unique designs', len([k for k in seen if k]))
for k, v in seen.items():
    if k:
        print('  area=%s ar=%s sweep1=%s sweep2=%s' % (k[0], k[1], k[2], k[3]), 'n=%d' % len(v), v[:2])
    else:
        print('  no x12 n=%d' % len(v), v[:3])
