# P0 blocker list

## B-P1-OPENVSP-BINDING [major, P1]
OpenVSP 3.26.1 Python API is not importable in the available interpreters: the shipped _vsp.pyd (x64) fails with ImportError 'DLL load failed while importing _vsp'. The pyd names libxml2.dll, which the OpenVSP install does not contain; a PATH-supplemented retry with D:/Anaconda/Library/bin also failed. P1 must drive vsp.exe/.vsp3 in a separate process or repair the binding; no in-process OpenVSP geometry call may be assumed available, and no OpenVSP version is claimed in solver_versions.

## B-P3-GMSH-BINDING [minor, P3]
gmsh Python module is absent from the project interpreter; the Gmsh CLI is present but any in-process meshing needs an external worker or wrapper.

## B-P1-CONCORDE-ADAPTER [major, P1]
Concorde.py is a tutorial script; no parameterized adapter or geometry checks exist yet, so the 15 design variables are not connected to a model in P0.

## B-P3-HF-SCOPE [major, P3]
Installed rcaide-multifidelity 0.1.0 evidence declares only a limited native RCAIDE input scope and Euler-only high fidelity; full Concorde high-fidelity fuel burn is not supported without a VSP3 or externally supplied SU2 mesh, and the claim must not be made before a paired test.

## B-P5-LEGACY-13D-APP [major, P5]
The historical 13-variable single_cruise application was not located in bounded scans; P5 must either locate it with user help or build the response-model path from the installed maml-opt 0.1.0 API only.

## B-P5-TORCH-CPU [minor, P5]
The installed torch build reports no CUDA device; MAML-A training must fit a small network on CPU, or a GPU-enabled build must be approved separately.

## B-P0-DIRTY-WORKTREE [minor, P0]
The worktree is dirty at audit time; a clean commit baseline is required before any run can be attributed to a commit.

## B-GOV-BUDGET [blocking, P2-P6]
Formal true-evaluation budgets (P2 smoke, P4 BO, P6 comparison) are not frozen; no Mission or CFD budget may be spent before explicit user approval.

## B-P3-VLM-MACH2 [major, P3]
VLM/VSPAERO applicability near Mach 2 is unverified for this configuration; any low-fidelity aerodynamic use must be tested and reported before it feeds a Mission.
