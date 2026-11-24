from pathlib import Path
import json
O0=Path(r'D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01')
r=json.loads((O0/'final_aircraft'/'verification_receipt.json').read_text(encoding='utf-8'))
for side in ('baseline','optimized'):
    w=r['wake_sensitivity_probe'][side]
    print(side, {k:w.get(k) for k in ('label','case_id','status','admitted','di_n','cl','cdi','alpha','n_wake_nodes','physical_solver_starts','internal_solver_cases')})
# baseline_verification entries summary
for k in ('baseline_verification','optimized_verification'):
    print('==',k)
    for e in r[k]:
        print(' ', {kk:e.get(kk) for kk in ('label','kind','case_id','status','admitted','di_n','cl','cdi','alpha','n_wake_nodes','physical_solver_starts','internal_solver_cases')})
