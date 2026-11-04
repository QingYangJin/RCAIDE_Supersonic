
import json, re, hashlib, math
from pathlib import Path

RAW = Path(r"D:/RCAIDE/outputs/concorde_metaopt/d12d004-vspaero72-lf-20261102T0500Z/raw_artifacts")
OUT = Path(r"D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/a0")
OUT.mkdir(parents=True, exist_ok=True)

def sha256(p):
    h = hashlib.sha256()
    with open(p,'rb') as f:
        for chunk in iter(lambda: f.read(1<<20), b''):
            h.update(chunk)
    return h.hexdigest()

def parse_vspaero(p):
    d = {}
    for line in Path(p).read_text(errors='replace').splitlines():
        if '=' in line:
            k,v = line.split('=',1)
            d[k.strip()] = v.strip()
    return d

def parse_polar(p):
    lines = Path(p).read_text(errors='replace').splitlines()
    # VSPAERO 7.2.2 polar: line0 group labels, line1 surface/wake tags, line2 column names
    hdr = None
    for i, ln in enumerate(lines):
        toks = ln.split()
        if 'CLtot' in toks and 'CDtot' in toks and 'Mach' in toks:
            hdr = i
            names = toks
            break
    if hdr is None:
        return {'names': [], 'rows': [], 'n_rows': 0, 'error': 'header_not_found'}
    rows = []
    for line in lines[hdr+1:]:
        parts = line.split()
        if len(parts) < len(names): continue
        try:
            vals = [float(x) for x in parts[:len(names)]]
        except ValueError:
            continue
        rows.append(dict(zip(names, vals)))
    return {'names': names, 'rows': rows, 'n_rows': len(rows)}

def parse_history(p):
    lines = Path(p).read_text(errors='replace').splitlines()
    rows = []
    for line in lines:
        parts = line.split()
        if not parts: continue
        try:
            int(parts[0])
        except ValueError:
            continue
        vals = []
        ok = True
        for x in parts:
            try: vals.append(float(x))
            except ValueError: ok=False; break
        if ok: rows.append(vals)
    return rows

def log_markers(p):
    txt = Path(p).read_text(errors='replace')
    # split on CR / form feed patterns used by vspaero console rewriting
    chunks = re.split(r'[\r\n]+', txt)
    keys = ['GMRES','Convergence','WARNING','ERROR','iterations','Total','Wake Iter','residual','Mach','CLtot','Diverge','not converged','singular']
    hits = [c.strip() for c in chunks if any(k.lower() in c.lower() for k in keys)]
    return {'n_chunks': len(chunks), 'n_hits': len(hits), 'hits_head': hits[:15], 'hits_tail': hits[-15:]}

cases = {}
for cid, stem, mach in [('V7-00','v7_00_standard_wing_mach0p1','0.1'), ('V7-01','v7_01_standard_wing_mach2p02','2.02')]:
    cdir = RAW/'cases'/cid
    ap = parse_vspaero(cdir/f'{stem}.vspaero')
    po = parse_polar(cdir/f'{stem}.polar') if (cdir/f'{stem}.polar').exists() else None
    hi = parse_history(cdir/f'{stem}.history') if (cdir/f'{stem}.history').exists() else None
    lg = log_markers(cdir/'solver_stdout.log') if (cdir/'solver_stdout.log').exists() else None
    entry = {'case_id':cid,'stem':stem,'vspaero_path':str(cdir/f'{stem}.vspaero'),
             'vspaero':ap,'polar':po,'history':None,'solver_log':lg,
             'artifacts':{}}
    for fn in ['solver_stdout.log','solver_stderr.log']:
        fp = cdir/fn
        if fp.exists(): entry['artifacts'][fn]={'bytes':fp.stat().st_size,'sha256':sha256(fp)}
    if hi is not None:
        # history columns per vspaero 7.2.2: iter, Mach, AoA, Beta, then coefficient blocks
        rec = {'n_rows':len(hi)}
        if hi:
            last = hi[-1]
            rec['last_row_first_8']=last[:8]
            # CLtot is column index 6 (0-based: iter,Mach,AoA,Beta,CLo,CLi,CLtot)
            cl = [r[6] for r in hi if len(r)>6]
            cd = [r[9] for r in hi if len(r)>9]
            rec['CLtot_series']=cl
            rec['CDtot_series']=cd
            rec['CLtot_last']=cl[-1] if cl else None
            rec['CDtot_last']=cd[-1] if cd else None
            rec['CLtot_maxabs']=max((abs(x) for x in cl), default=None)
            rec['CDtot_maxabs']=max((abs(x) for x in cd), default=None)
            rec['CDtot_min']=min(cd) if cd else None
            rec['diverged']= bool(cl and abs(cl[-1])>100) or bool(cd and (cd[-1]<0 or abs(cd[-1])>100))
            # per-iteration growth factor of CLtot magnitude (skip zeros)
            gf=[abs(cl[i+1])/abs(cl[i]) for i in range(len(cl)-1) if cl[i] not in (0.0,) and abs(cl[i])>1e-30]
            rec['growth_factors_CLtot']=gf[:20]
            rec['growth_factor_max']=max(gf, default=None)
        entry['history']=rec
    cases[cid]=entry

# geometry identity
geom = {}
for label, path in [
  ('V7-00_case', RAW/'cases'/'V7-00'/'v7_00_standard_wing_mach0p1.vspgeom'),
  ('V7-01_case', RAW/'cases'/'V7-01'/'v7_01_standard_wing_mach2p02.vspgeom'),
  ('V7-05_12D_W01', RAW/'setup_v1'/'V7-05'/'v7_05_w01_area_plus1pct.vspgeom'),
  ('d12d004_V0_thin_baseline', RAW/'wing355_baseline.vspgeom'),
]:
    p = Path(path)
    if p.exists():
        geom[label]={'bytes':p.stat().st_size,'sha256':sha256(p)}
# model sources from evidence
ms = {}
for cid in ['V7-00','V7-01']:
    fp = Path(r"D:/RCAIDE-d12d004/research/concorde_metaopt/optimization_runs/d12d004-vspaero72-lf-20261102T0500Z/evidence/v1/setup_gen")/cid/'model_source.json'
    if fp.exists():
        d = json.loads(fp.read_text())
        ms[cid]={'source_path':d['model_source']['source']['path'],
                 'source_bytes':d['model_source']['source']['bytes'],
                 'source_sha256':d['model_source']['source']['sha256'],
                 'note':d['model_copy']['source']}

doc = {
 'schema_version':'1.0.0',
 'artifact_kind':'D12D005_A0_V1_ARCHIVE_DIAGNOSTICS',
 'stage':'A0_ZERO_SOLVER_DIAGNOSTICS',
 'generated_utc':'2026-11-04T04:45:00Z',
 'authority':{'issue':4,'comment_id':6622447995,'budget_used':0,'solver_starts':0},
 'source_archive':str(RAW),
 'cases':cases,
 'geometry_identity':geom,
 'model_sources':ms,
 'findings':{},
 'limitations':['只读归档数据，未启动任何求解器','history 列名按 VSPAERO 7.2.2 约定（iter,Mach,AoA,Beta,CLo,CLi,CLtot,CDo,CDi,CDtot,...）重建，未用官方列名文件'],
}
# findings
f = {}
c0 = cases['V7-00']; c1 = cases['V7-01']
f['F-A0-01_geometry_mismatch'] = {
 'statement':'V7-00/V7-01 文件的 case 名为 standard_wing，但 model_source 与 .vspgeom 显示使用的是 OpenVSP 官方 Uber_eCRM-002/uber2.vsp3 全机多旋翼模型（913,497 B, sha 87ab38dc…），不是孤立标准翼；.vspgeom 2,019,343 B sha 091ba77f… 与 12D 主翼 thin 几何 224,357 B sha 9fcda6d5… 不同。',
 'evidence':{'case_says':['V7-00: standard thin wing subsonic','V7-01: standard thin wing supersonic'],
             'model_source':ms,'vspgeom':geom},
 'impact':'V1 的“标准翼”门实际上未执行；发散无法归因于标准翼设置族。A0/A-line 必须用真正标准翼重做。'
}
f['F-A0-02_v7_00_nonphysical'] = {
 'statement':'V7-00（Mach 0.1）SPAERO 结果非物理：CLtot=%r、CDtot=%r（负阻力）、CDi=%r；polar 单点与 history 最后一轮一致；history 中出现 CLtot 量级先大后收（%r→%r→%r），非单调收敛。' % (
    c0['polar']['rows'][0]['CLtot'] if c0['polar'] and c0['polar']['rows'] else None,
    c0['polar']['rows'][0]['CDtot'] if c0['polar'] and c0['polar']['rows'] else None,
    c0['polar']['rows'][0]['CDi'] if c0['polar'] and c0['polar']['rows'] else None,
    c0['history']['CLtot_series'][0] if c0['history'] else None,
    c0['history']['CLtot_series'][-2] if c0['history'] and len(c0['history']['CLtot_series'])>1 else None,
    c0['history']['CLtot_last'] if c0['history'] else None),
}
f['F-A0-03_v7_01_divergence'] = {
 'statement':'V7-01（Mach 2.02）history 第 2–3 轮出现 1e18–1e24 级发散（CLtot %r→%r），无 polar 输出，600.331 s 超时；属数值发散而非“收敛到非物理值”。' % (
    c1['history']['CLtot_series'][1] if c1['history'] and len(c1['history']['CLtot_series'])>1 else None,
    c1['history']['CLtot_series'][-1] if c1['history'] else None),
}
# settings comparison
f['F-A0-04_settings_untested'] = {
 'statement':'归档 .vspaero 与官方示例/默认值对照：V7-00/01 NumWakeNodes=%s、WakeIters=%s、WakeRelax=%s、FreezeWakeAtIteration=%s；一次只改一个因素的尾迹设置族在 V1 中从未被执行（V7-01 超时前中止）。' % (
    c0['vspaero'].get('NumWakeNodes'), c0['vspaero'].get('WakeIters'),
    c0['vspaero'].get('WakeRelax'), c0['vspaero'].get('FreezeWakeAtIteration')),
 'pending':'A 批 1 的 S1/S2 将分别只改 NumWakeNodes=128 / WakeIters=0 验证。'
}
doc['findings']=f
doc['summary'] = {
 'n_cases_analyzed': 2,
 'v7_00_status':'NONPHYSICAL_VALUE',
 'v7_01_status':'NUMERICAL_DIVERGENCE_NO_POLAR',
 'solver_starts':0,
 'key_conclusion':'V1 两案均在 Uber_eCRM-002 全机模型上运行（非标准翼），一个得到非物理系数一个数值发散；因此“标准翼设置族是否健康”在 V1 中未获证。A-line 必须先跑真正的标准翼（S0/S1/S2），再跑 12D 主翼（S5）。',
}
(OUT/'vspaero_v1_divergence_analysis.json').write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
print('WROTE', OUT/'vspaero_v1_divergence_analysis.json')
print(json.dumps({'findings_keys':list(f), 'geom':geom, 'v7_00_cl':c0['history']['CLtot_series'] if c0['history'] else None,
                  'v7_01_cl':c1['history']['CLtot_series'] if c1['history'] else None,
                  'v7_00_polar_names': c0['polar']['names'] if c0['polar'] else None,
                  'log_v7_00': (c0['solver_log']['hits_tail'] if c0['solver_log'] else None),
                  'log_v7_01': (c1['solver_log']['hits_tail'] if c1['solver_log'] else None)}, ensure_ascii=False, indent=1)[:6000])
