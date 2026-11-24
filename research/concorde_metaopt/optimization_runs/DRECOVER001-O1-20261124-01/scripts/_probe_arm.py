from pathlib import Path
import json
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
for arm in ('SOBOL_BO','COND_SUPERVISED_KSHOT_BO','COND_FOMAML_KSHOT_BO'):
    a=json.loads((R/('o1_arm_%s.json'%arm)).read_text(encoding='utf-8'))
    print('===',arm)
    print('warm_start_meta', json.dumps(a['warm_start_meta'],ensure_ascii=False)[:700])
    print('adaptive_designs', a['adaptive_designs'], 'phys', a['physical_solver_starts_actual'], 'equiv', a['equivalent_starts_actual'], 'internal', a['internal_solver_cases_actual'])
    print('records n', len(a['records']), 'first keys', list(a['records'][0].keys()))
    print('anytime n', len(a['anytime']), 'first', json.dumps(a['anytime'][0],ensure_ascii=False)[:400])
