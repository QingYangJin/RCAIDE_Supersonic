# Analysis scripts used by this run

These scripts are the exact orchestration and post-processing code that produced the
committed JSON/CSV/PNG artefacts of run p1p3-fullchain-20261031T0407Z. They were executed
from the external AI state directory
(Windows: LOCALAPPDATA\RCAIDE_Supersonic_agent_state\fullchain\lead and \wave) and are
copied here for audit and reproducibility.

Caveats:

- they contain absolute Windows paths to the project, to the external state directory and
  to the installed OpenVSP 3.26.1 / SU2 8.5.0 / Gmsh 4.15.2 binaries (see environment.json);
- they are not part of the importable package and are not covered by the unit-test suite;
- rerunning any solver step requires a new owner-approved budget
  (D-12D-002 is exhausted at 23/23 starts);
- the offline post-processing scripts can be rerun against the archived raw data in
  outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/ without any solver start.

File map:

- ledger.py - approval/budget ledger CLI (start/finish/note/status)
- geometry_validation.py - STL/DegenGeom vs geometry-model cross-check (W10 twist)
- build_lf_request.py, build_lf_case.py, run_lf_case.py, lf_worker.py - LF geometry export,
  VSPAERO setup/patch, run orchestration, polar parsing
- build_wave00.py, build_wave_cases.py, build_wave_case.py, wave_worker.py, run_wave.py,
  run_wave_02_04.sh - OpenVSP WaveDrag / EmintonLord cases
- area_rule_recompute.py, area_rule_diag.py, make_wave_deliverables.py - independent
  Eminton-Lord port, condition-number/stair-stepping diagnostics, deliverable JSON/CSV/PNG
- wedge_prep.py, make_hfs_cfg.py, run_hfs00.sh, analyze_hfs00c.py - SU2 wedge verification
- gen_wing_hf.py, msh2_to_su2.py, mesh_preflight.py, run_hfs_wing.sh, analyze_hfs_wing.py -
  Gmsh wing meshes, SU2 mesh conversion and preflight, wing Euler runs, force integration
- run_rcaide_lf.py, make_mission_e2e.py - RCAIDE LF 12D mission cases and E2E assembly
- make_hf_su2_results.py, make_drag_component_ledger.py, make_fullchain_figures.py -
  derived evidence JSONs and figures
- extract_su2_options.py, fetch_wavedrag_src.py - toolchain capability probes
- stage_raw_artifacts.py, make_data_manifest.py - raw archive and hash manifests
