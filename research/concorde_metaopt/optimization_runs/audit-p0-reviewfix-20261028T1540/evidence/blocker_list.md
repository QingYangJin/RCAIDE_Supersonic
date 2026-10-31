# P0 blocker list

## B-P1-OPENVSP-BINDING [minor, P1]
The project interpreter (Python 3.11) cannot import the OpenVSP 3.26.1 binding because the shipped _vsp.pyd is built for Python 3.9; this is a worker-ABI constraint, not a broken install. The SUAVE Python 3.9 interpreter imports openvsp successfully once the package roots (python/, python/openvsp, python/degen_geom, python/utilities) are on sys.path. P1 must drive OpenVSP through an external Python 3.9 worker (vsp.exe/.vsp3 remains a fallback); in-process import from envs/RCAIDE must not be assumed, and the OpenVSP version is reported only from the working worker probe, not from the 3.11 interpreter.

## B-P3-GMSH-BINDING [minor, P3]
gmsh Python module is absent from the project interpreter; the Gmsh CLI is present but any in-process meshing needs an external worker or wrapper.

## B-P1-CONCORDE-ADAPTER [major, P1]
Concorde.py is a tutorial script; no parameterized adapter or geometry checks exist yet, so the 15 design variables are not connected to a model in P0.

## B-P3-HF-SCOPE [major, P3]
Installed rcaide-multifidelity 0.1.0 evidence declares only a limited native RCAIDE input scope and Euler-only high fidelity; full Concorde high-fidelity fuel burn is not supported without a VSP3 or externally supplied SU2 mesh, and the claim must not be made before a paired test.

## B-P5-LEGACY-13D-APP [major, P5]
The bounded code scan completed (137 files) and returned 40 textual hits, but none is a candidate application source project (no maml-opt/single_cruise app tree with pyproject/setup was found); the historical 13-variable application remains unlocated. P5 must locate it with user help or build the response-model path from the installed maml-opt 0.1.0 API only.

## B-P5-MAML-SOURCE [major, P5]
maml-opt has no recorded direct_url; its source project is only an installed distribution, so reuse must be audited against site-packages source and no unverified upstream API may be assumed.

## B-P5-TORCH-CPU [minor, P5]
The installed torch build reports no CUDA device; MAML-A training must fit a small network on CPU, or a GPU-enabled build must be approved separately.

## B-GOV-BUDGET [blocking, P2-P6]
Formal true-evaluation budgets (P2 smoke, P4 BO, P6 comparison) are not frozen; no Mission or CFD budget may be spent before explicit user approval.

## B-P3-VLM-MACH2 [major, P3]
VLM/VSPAERO applicability near Mach 2 is unverified for this configuration; any low-fidelity aerodynamic use must be tested and reported before it feeds a Mission.
