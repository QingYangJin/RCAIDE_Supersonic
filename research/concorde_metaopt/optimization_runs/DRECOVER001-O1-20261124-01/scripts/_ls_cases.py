from pathlib import Path
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
C=R/'cases'/'O1-M190'
for d in sorted(C.rglob('*')):
    if d.is_dir():
        rel=d.relative_to(C)
        files=[f.name for f in d.iterdir() if f.is_file()]
        print('%-40s dirs=%d files=%d polar=%s' % (str(rel), sum(1 for x in d.iterdir() if x.is_dir()), len(files), any(f.endswith('.polar') for f in files)))
