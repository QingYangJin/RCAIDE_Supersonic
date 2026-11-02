import json, math, subprocess, sys
from pathlib import Path

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
OUT = EXT / "hf" / "wedge"
OUT.mkdir(parents=True, exist_ok=True)
GMSH = r"D:/Program Files/GMesh/gmsh-4.15.2-Windows64/gmsh-4.15.2-Windows64/gmsh.exe"

M = 2.0
GAMMA = 1.4
THETA = math.radians(10.0)

def shock_angle(M, theta, gamma=1.4):
    lo, hi = theta + 1e-9, math.radians(89.0)
    def f(b):
        t = 2.0 / math.tan(b) * (M**2 * math.sin(b)**2 - 1.0) / (M**2 * (gamma + math.cos(2.0*b)) + 2.0)
        return math.tan(theta) - t
    for _ in range(200):
        mid = 0.5*(lo+hi)
        if f(lo)*f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return 0.5*(lo+hi)

beta = shock_angle(M, THETA)
Mn1 = M * math.sin(beta)
p_ratio = 1.0 + 2.0*GAMMA/(GAMMA+1.0)*(Mn1**2 - 1.0)
rho_ratio = (GAMMA+1.0)*Mn1**2/((GAMMA-1.0)*Mn1**2 + 2.0)
T_ratio = p_ratio/rho_ratio
M2 = math.sqrt((1.0 + (GAMMA-1.0)/2.0*M**2*math.sin(beta)**2)/(GAMMA*M**2*math.sin(beta)**2 - (GAMMA-1.0)/2.0)/math.sin(beta-0*math.pi/180)**2) if False else None
# post-shock Mach normal component formula
Mn2_sq = (1.0 + (GAMMA-1.0)/2.0*Mn1**2) / (GAMMA*Mn1**2 - (GAMMA-1.0)/2.0)
Mn2 = math.sqrt(Mn2_sq)
M2 = Mn2 / math.sin(beta - THETA)
Cp_max = 2.0/(GAMMA*M**2)*(p_ratio - 1.0)
p1 = 7171.544888256813
T1 = 216.65
theory = dict(Mach=M, theta_deg=10.0, gamma=GAMMA, solution="weak",
              beta_deg=math.degrees(beta), Mn1=Mn1, p2_over_p1=p_ratio,
              rho2_over_rho1=rho_ratio, T2_over_T1=T_ratio, M2=M2,
              Cp_surface=Cp_max, p2_pa=p1*p_ratio, T2_K=T1*T_ratio,
              beta_minus_theta_deg=math.degrees(beta)-10.0)
(OUT/"theory.json").write_text(json.dumps(theory, indent=2), encoding="utf-8")
print(json.dumps(theory, indent=2))

L = 8.0
h = L * math.tan(THETA)
def write_geo(path, hwall):
    txt = f"""// 2D supersonic wedge, Mach {M}, half angle 10 deg, Euler benchmark
SetFactory("OpenCASCADE");
Mesh.CharacteristicLengthMax = 4.0;
Point(1) = {{-10, -20, 0, 1.0}};
Point(2) = {{ 40, -20, 0, 1.0}};
Point(3) = {{ 40,  20, 0, 1.0}};
Point(4) = {{-10,  20, 0, 1.0}};
Line(11) = {{1,2}};
Line(12) = {{2,3}};
Line(13) = {{3,4}};
Line(14) = {{4,1}};
Curve Loop(21) = {{11,12,13,14}};

Point(101) = {{0.0, 0.0, 0, {hwall:.4f}}};
Point(102) = {{{L:.4f}, {h:.6f}, 0, {hwall:.4f}}};
Point(103) = {{{L:.4f}, {-h:.6f}, 0, {hwall:.4f}}};
Line(111) = {{101,102}};
Line(112) = {{102,103}};
Line(113) = {{103,101}};
Curve Loop(22) = {{111,112,113}};

Plane Surface(31) = {{21, 22}};

Physical Curve("wall") = {{111,112,113}};
Physical Curve("farfield") = {{11,12,13,14}};
Physical Surface("fluid") = {{31}};

Field[1] = Distance;
Field[1].CurvesList = {{111,112,113}};
Field[2] = Threshold;
Field[2].InField = 1;
Field[2].SizeMin = {hwall:.4f};
Field[2].SizeMax = 2.5;
Field[2].DistMin = 0.5;
Field[2].DistMax = 12.0;
Field[3] = Min;
Field[3].FieldsList = {{2}};
Background Field = 3;
Mesh.Algorithm = 6;
"""
    Path(path).write_text(txt, encoding="utf-8")

for name, hw in (("wedge_coarse", 0.12), ("wedge_fine", 0.06)):
    geo = OUT / (name + ".geo")
    write_geo(geo, hw)
    su2 = OUT / (name + ".su2")
    r = subprocess.run([GMSH, "-2", str(geo), "-format", "su2", "-o", str(su2)],
                       capture_output=True, text=True, timeout=600)
    print(name, "rc=", r.returncode)
    print((r.stdout or "")[-1500:])
    if r.returncode != 0:
        print((r.stderr or "")[-1500:])
        break
    head = su2.read_text(encoding="utf-8", errors="replace").splitlines()
    print(name, "su2 lines=", len(head))
    print("\n".join(head[:6]))
    print("...tail:")
    print("\n".join(head[-25:]))
