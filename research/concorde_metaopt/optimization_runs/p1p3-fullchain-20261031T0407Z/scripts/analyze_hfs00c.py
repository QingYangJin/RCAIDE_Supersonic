import csv, json, math, statistics
from pathlib import Path
W = Path(r'C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain/hf/wedge')
GAMMA=1.4; p_inf=7171.544888256813; rho_inf=0.1153178340089936; V_inf=596.0373972278921; q_inf=0.5*rho_inf*V_inf**2
theory=json.loads((W/'theory.json').read_text())
rrows=list(csv.reader(open(W/'restart_hfs00.csv',encoding='utf-8-sig')))
pts=[]
for r in rrows[1:]:
    if len(r)<7: continue
    pid,x,y,rho,mx,my,e=int(r[0]),float(r[1]),float(r[2]),float(r[3]),float(r[4]),float(r[5]),float(r[6])
    u=mx/rho; v=my/rho; p=(GAMMA-1.0)*(e-0.5*rho*(u*u+v*v))
    pts.append((x,y,p,rho))
thr=p_inf*(1.0+theory['p2_over_p1'])/2.0
def crossing(band, ref, thr):
    ys=[b[0] for b in band]; vs=[b[ref] for b in band]
    for i in range(1,len(band)):
        a,b=vs[i-1],vs[i]
        if (a-thr)*(b-thr) <= 0 and a!=b:
            t=(thr-a)/(b-a)
            return ys[i-1]+t*(ys[i]-ys[i-1])
    return None
shock=[]
for x0 in [1.5,2.0,2.5,3.0,4.0,5.0,6.0,7.0]:
    band=sorted([(y,p,rho) for (x,y,p,rho) in pts if abs(x-x0)<=0.12 and -0.5 < y < 40.0])
    yp=crossing(band,1,thr)
    rho_mid=rho_inf*(1.0+theory['rho2_over_rho1'])/2.0
    yr=crossing(band,2,rho_mid)
    if yp is None:
        print('x=%.1f no crossing (n=%d)' % (x0,len(band))); continue
    bp=math.degrees(math.atan(yp/x0)); br=math.degrees(math.atan(yr/x0)) if yr else None
    shock.append(dict(x=x0,y_shock_p=round(yp,4),beta_p_deg=round(bp,4),y_shock_rho=round(yr,4) if yr else None,beta_rho_deg=round(br,4) if br else None,n=len(band)))
    print('x=%.1f y_p=%.4f beta_p=%.4f | y_rho=%s beta_rho=%s' % (x0,yp,bp,round(yr,4) if yr else None,round(br,4) if br else None))
bp=[s['beta_p_deg'] for s in shock]
# density-based crossings are only valid once the shock is far enough downstream of the
# sharp tip; upstream stations return negative y (inside the wedge) and must not enter the mean
br=[s['beta_rho_deg'] for s in shock if s['beta_rho_deg'] and s['beta_rho_deg'] > 20.0]
print('n shock points', len(shock))
print('mean beta pressure %.4f theory %.4f diff %.4f' % (statistics.mean(bp),theory['beta_deg'],statistics.mean(bp)-theory['beta_deg']))
if br: print('mean beta density %.4f diff %.4f' % (statistics.mean(br),statistics.mean(br)-theory['beta_deg']))
print('max |beta_p - theory| =', max(abs(b-theory['beta_deg']) for b in bp))
# fit through origin y = m x
m = sum(s['x']*s['y_shock_p'] for s in shock)/sum(s['x']**2 for s in shock)
print('origin-fit beta %.4f diff %.4f' % (math.degrees(math.atan(m)), math.degrees(math.atan(m))-theory['beta_deg']))
# post-shock pressure below shock
postp=[]
for s in shock:
    x0=s['x']; y0=s['y_shock_p']
    sel=[p for (x,y,p,rho) in pts if abs(x-x0)<=0.15 and y0-0.8 < y < y0-0.2]
    if sel: postp.append(statistics.mean(sel)/p_inf)
print('post-shock p/pinf mean %.5f theory %.5f dev %.4f%%' % (statistics.mean(postp),theory['p2_over_p1'],100*(statistics.mean(postp)/theory['p2_over_p1']-1)))
out=dict(theory=theory,threshold_p_pa=thr,shock=shock,beta_pressure_mean_deg=round(statistics.mean(bp),4),beta_pressure_diff_deg=round(statistics.mean(bp)-theory['beta_deg'],4),beta_density_mean_deg=round(statistics.mean(br),4) if br else None,beta_density_diff_deg=round(statistics.mean(br)-theory['beta_deg'],4) if br else None,beta_originfit_deg=round(math.degrees(math.atan(m)),4),beta_originfit_diff_deg=round(math.degrees(math.atan(m))-theory['beta_deg'],4),postshock_ppinf=round(statistics.mean(postp),5))
(W/'hfs00_analysis.json').write_text(json.dumps(out,indent=1),encoding='utf-8')
print('written hfs00_analysis.json')