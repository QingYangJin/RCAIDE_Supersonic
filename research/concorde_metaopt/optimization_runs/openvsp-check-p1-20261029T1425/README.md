# P1 OpenVSP geometry check: openvsp-check-p1-20261029T1425

This run exports the provisional 15-variable Concorde-like geometry
through OpenVSP 3 and compares the exported STL/product metrics with the
dependency-free geometry model. It performs no aerodynamic or Mission
evaluation and reports no objective value.

- stage: P1
- status: openvsp_check_completed_with_warnings
- git_sha: c0eb7accba8394b5e01e1b31a6f164fab412dc43
- design_dim: 15
- OpenVSP: 3.26.1 (external Python 3.9.25)
- components: main_wing, vertical_tail, fuselage
- comparisons: 11 checks (10 pass, 1 warn, 0 fail)
- warning: OV08_fuselage_width (+15.01%)
- failure: none
- true evaluations: 0

The exported STL/STEP/VSP3 files are under the git-ignored outputs
directory; this run records their relative paths, sizes and SHA-256.

Known limitation: OpenVSP fuselage surface uses spline interpolation
between the eight stations and overshoots the declared maximum width near
the tail; the comparison is recorded as a warning and must be resolved
before OpenVSP-derived fuselage drag or volume is treated as validated.
