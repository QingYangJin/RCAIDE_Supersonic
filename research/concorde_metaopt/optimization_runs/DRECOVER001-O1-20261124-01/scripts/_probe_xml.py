
import re
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/final_aircraft/geometry/sobol_best_solver.vsp3"
t=open(p,encoding="utf-8").read()
i=t.find("Tess_U")
print(repr(t[max(0,i-900):i+400]))
