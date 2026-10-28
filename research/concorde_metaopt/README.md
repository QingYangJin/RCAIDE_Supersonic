# research/concorde_metaopt — P0 audit implementation

Read-only P0 implementation for RCAIDE_Supersonic Issue #1 ("[METAOPT-00] ...").
It implements the mandatory `research/concorde_metaopt/` skeleton and the `audit`
subcommand only. No Mission, CFD case, DOE or optimization is executed by this code.
Later phases (P1 geometry, P2 evaluator, P3 DOE/fidelity, P4 BO, P5 MAML-A, P6
comparison) are not implemented yet, as required by the Issue.

## CLI status

| subcommand | status |
| --- | --- |
| `audit` | implemented (read-only environment audit) |
| `geometry-check`, `smoke`, `doe`, `baseline`, `route-a`, `report` | declared in `cli.py`, exit code 2 with "not implemented ...; no result was produced." |

Reproduce the P0 audit (one run directory, small files committed on purpose so the
result can be reviewed remotely):

```bash
# 1) git and external-tool facts that sandboxed child processes cannot obtain
bash research/concorde_metaopt/scripts/probe_external_tools.sh \
  research/concorde_metaopt/optimization_runs/<run_id>/probes
# 2) assemble the probe JSON
./run_rcaide.cmd -m research.concorde_metaopt.scripts.assemble_probes \
  research/concorde_metaopt/optimization_runs/<run_id>/probes \
  research/concorde_metaopt/optimization_runs/<run_id>/probes/shell_probes.json
# 3) run the audit (re-run with --allow-existing when the probes/ directory exists)
./run_rcaide.cmd -m research.concorde_metaopt.cli audit \
  --run-id <run_id> \
  --shell-probes research/concorde_metaopt/optimization_runs/<run_id>/probes/shell_probes.json \
  --allow-existing
```

The current evidence run is
`research/concorde_metaopt/optimization_runs/audit-p0-20261027T2055/`
(`environment.json`, `summary.json`, `evidence/`, `probes/`).

## summary.json conventions (Issue #1 mandatory fields)

- `stage` is `P0`; `method` is `read_only_environment_audit`.
- `total_true_evaluations`, `low_fidelity_calls`, `su2_calls` are `0`: the audit
  executes nothing physical.
- `design_dim` is `null` with `design_dim_note`: the 15-variable space is not
  frozen until P1.
- `invalid_count`, `failed_count`, `first_feasible_evaluation`,
  `best_feasible_fuel_kg`, `best_design_id`, `wall_seconds`,
  `cpu_seconds_if_available` are `null` (not applicable to an audit; never 0 or inf
  as a stand-in).
- `solver_versions` records only observed versions. `openvsp` is `null` because
  the Python API could not be imported; the installer version is not claimed as a
  working solver version.
- `git_sha` comes from the committed HEAD; when the worktree is dirty this is
  reported in the blocker list (`B-P0-DIRTY-WORKTREE`).

## Evidence files

`environment.json` contains git facts, Python/packages, external tools
(`SU2_CFD.exe --help`, `gmsh --version`, OpenVSP executable/binding probes),
the Concorde.py structural scan, maml-opt and rcaide-multifidelity installation
facts, and the blocker list. `evidence/` mirrors the tables as Markdown/JSON
(`toolchain_table.md`, `api_table.md`, `concorde_structure.md`,
`blocker_list.md`, ...). `probes/` keeps the raw shell-probe outputs and
`shell_probes.json` so every number is traceable.

## Host/sandbox constraints (recorded, not hidden)

- The project interpreter is under a Windows file sandbox. Spawning child
  processes (git, SU2, gmsh, external Python) from Python raises
  `PermissionError: [WinError 5]`, so those facts are captured by the bash
  probe and merged under `probe_source: "shell_probe"`.
- Writes to the system temp directory and to `tempfile.mkdtemp` directories are
  denied. Tests therefore use `research/concorde_metaopt/tests/_tmp/` (git
  ignored).
- `pytest` is not installed in `envs/RCAIDE`; tests run with `unittest`:
  `./run_rcaide.cmd -m unittest discover -s research/concorde_metaopt/tests -t . -v`.
- Python package writes to `outputs/` and `.git/` are denied in this sandbox;
  audit evidence therefore lives under `research/`, which is writable.

## Tests

`tests/test_audit.py` covers the SHA-256 helper, Markdown table rendering,
Concorde.py scanning (real identifier names, missing file), blocker construction
(dirty/clean worktree, OpenVSP/Gmsh absence), shell-probe precedence for git
facts, and an end-to-end mocked `run_audit` that writes
`environment.json`/`summary.json`/`evidence/blocker_list.md` without any
simulation. All 8 tests pass.

## Out of scope in P0

No 15-variable parameterization, no geometry construction, no Mission evaluation,
no SU2 case, no DOE dataset, no BO, no MAML. Those require the P1–P6 code gates
and explicit user approval for true-evaluation budgets.
