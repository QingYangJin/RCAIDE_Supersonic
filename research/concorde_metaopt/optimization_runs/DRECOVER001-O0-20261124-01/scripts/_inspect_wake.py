import pathlib, re
root = pathlib.Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01')
hits = {}
for p in list((root/'cases').rglob('*.vspaero'))[:400]:
    txt = p.read_text(encoding='utf-8', errors='replace')
    m = re.search(r'NumWakeNodes\s*=\s*(\d+)', txt)
    if m: hits.setdefault(m.group(1), []).append(p.parent.name)
for k, v in sorted(hits.items()):
    print('NumWakeNodes', k, '->', len(v), 'cases; e.g.', v[:3])
