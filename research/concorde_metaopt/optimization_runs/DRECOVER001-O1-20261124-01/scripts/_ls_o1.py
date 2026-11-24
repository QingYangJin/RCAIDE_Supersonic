from pathlib import Path
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
def ls(label, p, rec=False):
    print('---', label)
    if not p.exists():
        print('ABSENT'); return
    it = p.rglob('*') if rec else p.iterdir()
    for f in sorted(it):
        if f.is_file(): print('%-72s %10d' % (str(f.relative_to(R)), f.stat().st_size))
ls('root', R)
for sub in ('tables','figures','final_aircraft','a5_review','a5_support'):
    ls(sub, R/sub)
