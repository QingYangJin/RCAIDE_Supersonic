from pathlib import Path
import json
R=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01')
for arm in ('SOBOL_BO','COND_SUPERVISED_KSHOT_BO','COND_FOMAML_KSHOT_BO'):
    a=json.loads((R/('o1_arm_%s.json'%arm)).read_text(encoding='utf-8'))
    print('===',arm, a['warm_start_meta'])
    for rec in a['records']:
        print(' %-4s %-14s %-8s Di=%.3f pred=%s acq=%s' % (rec['tag'], rec['role'], rec['design_id'], rec['di_n'], rec.get('predicted_di_n'), json.dumps(rec.get('acquisition'),ensure_ascii=False)[:80]))
print()
print('=== arm result fields for result json')
res=json.loads((R/'o1_result.json').read_text(encoding='utf-8'))
for arm,v in res['arms'].items():
    print(arm, {k:v[k] for k in ('designs','starts','internal','admitted','failed','point_feasible_rate','run_level_feasible','best_feasible_di_n','best_feasible_tag','improvement_n','improvement_fraction','reached_target','equivalent_starts_to_target','adaptive_designs')})
