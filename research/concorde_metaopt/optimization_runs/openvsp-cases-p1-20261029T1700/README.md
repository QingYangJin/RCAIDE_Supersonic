# P1 OpenVSP perturbation geometry check

Representative wing / vertical-tail / fuselage perturbations are exported
through the external Python 3.9 OpenVSP worker, measured with trimesh and
compared with the internal geometry model. This is a geometry-export check:
no Mission, VSPAERO or CFD evaluation was run and no objective value is reported.

- run_id: openvsp-cases-p1-20261029T1700
- git_sha: 5237a1ccc7659204001f220d3e3769d0a0c7a91e
- cases: 7
- checks: 62 pass / 0 fail / 1 skip
- status: openvsp_perturbation_check_completed

Cases (relative perturbation of the frozen baseline design):

- baseline: pass
- W01_plus_2pct: pass
- W02_plus_2pct: pass
- V01_plus_2pct: pass
- F01_plus_1pct: pass
- F02_plus_2pct: pass
- F03_plus_2pct: pass

Placement is checked on the trimesh-composed assembly STL; .vsp3/.step
exports remain component-local in this OpenVSP build.
Known limitation: OpenVSP fuselage spline overshoot; surface bounds are
measured from the exported STL rather than the OpenVSP BBox parameters.

Redraw the figure:

    ./run_rcaide.cmd -m research.concorde_metaopt.aircraft.openvsp_perturbations research/concorde_metaopt/optimization_runs/openvsp-cases-p1-20261029T1700
