# Toolchain inventory (P0 audit)

Import status is 'not_probed' when no import probe exists for that distribution; it is never reported as a failure.

| distribution | version | import | location | error | probe_note |
|---|---|---|---|---|---|
| RCAIDE-LEADS | 1.5.0 | ok | <repo_root>\envs\RCAIDE\Lib\site-packages | None | imported in project interpreter |
| rcaide-gui | 1.2.0 | failed | <repo_root>\envs\RCAIDE\Lib\site-packages | ModuleNotFoundError: No module named 'rcaide_gui' | imported in project interpreter |
| numpy | 2.4.6 | ok | <repo_root>\envs\RCAIDE\Lib\site-packages | None | imported in project interpreter |
| scipy | 1.17.1 | ok | <repo_root>\envs\RCAIDE\Lib\site-packages | None | imported in project interpreter |
| matplotlib | 3.11.2 | ok | <repo_root>\envs\RCAIDE\Lib\site-packages | None | imported in project interpreter |
| pandas | 3.0.6 | not_probed | <repo_root>\envs\RCAIDE\Lib\site-packages | None | no import probe for this distribution |
| torch | 2.8.0 | ok | <repo_root>\envs\RCAIDE\Lib\site-packages | None | imported in project interpreter |
| maml-opt | 0.1.0 | ok | <repo_root>\envs\RCAIDE\Lib\site-packages | None | imported in project interpreter |
| rcaide-cpacs | 0.1.0 | ok | <repo_root>\envs\RCAIDE\Lib\site-packages | None | imported in project interpreter |
| rcaide-multifidelity | 0.1.0 | ok | <repo_root>\envs\RCAIDE\Lib\site-packages | None | imported in project interpreter |
| scikit-learn | 1.9.1 | not_probed | <repo_root>\envs\RCAIDE\Lib\site-packages | None | no import probe for this distribution |
| vtk | 9.7.1 | not_probed | <repo_root>\envs\RCAIDE\Lib\site-packages | None | no import probe for this distribution |
| pyvista | 0.49.1 | not_probed | <repo_root>\envs\RCAIDE\Lib\site-packages | None | no import probe for this distribution |
| h5py | 3.16.0 | not_probed | <repo_root>\envs\RCAIDE\Lib\site-packages | None | no import probe for this distribution |
| PyQt6 | 6.11.0 | not_probed | <repo_root>\envs\RCAIDE\Lib\site-packages | None | no import probe for this distribution |
| pytest | None | not_probed | None | None | no import probe for this distribution |
| shapely | 2.2.0 | not_probed | <repo_root>\envs\RCAIDE\Lib\site-packages | None | no import probe for this distribution |
| trimesh | 5.1.1 | not_probed | <repo_root>\envs\RCAIDE\Lib\site-packages | None | no import probe for this distribution |
