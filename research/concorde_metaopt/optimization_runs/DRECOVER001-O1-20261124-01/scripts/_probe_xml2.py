
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/cases/O1-M190/ARM_SOBOL_BO/o1-d06-refine/o1-d06-refine.vsp3"
t=open(p,encoding="utf-8").read()
i=t.find("SmallPanelW")
print(repr(t[max(0,i-1200):i+300]))
