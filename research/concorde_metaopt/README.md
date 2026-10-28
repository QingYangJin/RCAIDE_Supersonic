# research/concorde_metaopt — P0 audit and P1 design space

Phase I workspace for RCAIDE_Supersonic Issue #1 ("[METAOPT-00] ..."). P0 is
complete: the mandatory directory skeleton, the read-only `audit` subcommand and
the committed evidence runs. P1 has started with the provisional 15-variable
design-space contract (`configs/design_space_15d.yaml`) and its dependency-free
loader; geometry construction and the perturbation/effect matrix are still open.
No Mission, CFD case, DOE or optimization is executed by this code yet. P2–P6
(evaluator, DOE/fidelity, BO, MAML-A, comparison) remain unimplemented.

## CLI status

| subcommand | status |
| --- | --- |
| `audit` | implemented (read-only environment audit) |
| `geometry-check`, `smoke`, `doe`, `baseline`, `route-a`, `report` | declared in `cli.py`, exit code 2 with "not implemented ...; no result was produced." |

Reproduce the P0 audit (one run directory, small files committed on purpose so the
result can be reviewed remotely):

```bash
# 1) git and external-tool facts that child processes may be denied under a sandbox
bash research/concorde_metaopt/scripts/probe_external_tools.sh \
  research/concorde_metaopt/optimization_runs/<run_id>/probes
# 2) assemble the probe JSON
./envs/RCAIDE/python.exe -E -s -B research/concorde_metaopt/scripts/assemble_probes.py \
  research/concorde_metaopt/optimization_runs/<run_id>/probes \
  research/concorde_metaopt/optimization_runs/<run_id>/probes/shell_probes.json
# 3) run the audit (re-run with --allow-existing when the probes/ directory exists)
./run_rcaide.cmd -m research.concorde_metaopt.cli audit \
  --run-id <run_id> \
  --shell-probes research/concorde_metaopt/optimization_runs/<run_id>/probes/shell_probes.json \
  --allow-existing
```

Evidence runs kept in the repository:

- `audit-p0-20261028T1430`: first run after the sandbox was lifted; 9 blockers,
  8/8 unittest, `git_sha=d9aa5e6` (schema of record for the Issue #1 receipt).
- `audit-p0-reviewfix-20261028T1540`: run after the independent A5 review
  (CHANGES_REQUESTED) was addressed; 9 blockers, clean worktree,
  `git_sha=fdadeaa`, committed in `1295576`; see "Review fixes" below. The
  earlier `...T1515` development run was deleted and is not evidence.
- `audit-p0-20261027T2055`: historical first run made while the sandbox denied
  child processes; kept only as a comparison point, not as current evidence.

## summary.json conventions (Issue #1 mandatory fields)

- `stage` is `P0`; `method` is `read_only_environment_audit`.
- `total_true_evaluations`, `low_fidelity_calls`, `su2_calls` are `0`: the audit
  executes nothing physical.
- `design_dim` is `null` with `design_dim_note`: the 15-variable space is not
  frozen until P1.
- `invalid_count`, `failed_count`, `first_feasible_evaluation`,
  `best_feasible_fuel_kg`, `best_design_id`, `cpu_seconds_if_available` are
  `null` (not applicable to an audit; never 0, inf or a fabricated label).
- `wall_seconds` is measured for every audit run and written as a number; it is
  never documented as null.
- `solver_versions` records only observed versions. The OpenVSP 3.26.1 Python
  binding exposes no version API (no `GetVSPVersion`/`GetVersion`, `__version__`
  is `None`), so `openvsp` stays `null`; the install version is identified by the
  documented install path and the executable file, and the blocker records the
  external Python 3.9 worker constraint. A failure string is never written as a
  version.
- `git_sha` comes from the committed HEAD; when the worktree is dirty this is
  reported in the blocker list (`B-P0-DIRTY-WORKTREE`).

## Evidence files

`environment.json` contains git facts, Python/packages, external tools
(`SU2_CFD.exe --help`, `gmsh --version`, OpenVSP executable and Python-binding
probes for both the project interpreter and external Python 3.9 workers), the
Concorde.py structural scan, maml-opt and rcaide-multifidelity installation facts,
`pip check`, installed-package test logs and the blocker list. `evidence/` mirrors
the tables as Markdown/JSON (`toolchain_table.md`, `api_table.md`,
`concorde_structure.md`, `blocker_list.md`, `checks.json`, `pip_check.txt`, ...).
`probes/` keeps the raw shell-probe outputs and `shell_probes.json` so every number
is traceable. Each run directory also contains a `README.md` describing that run.

Path policy: generated evidence replaces the repository root, the user home and the
external evidence root with `<repo_root>`, `<home>`, `<external_evidence_root>`.
Standard tool install locations (Program Files, Anaconda) are retained because they
are needed to reproduce the environment and contain no username, token or secret.

## Review fixes (independent A5 review, 2026-10-28)

An independent reviewer returned CHANGES_REQUESTED on the first P0 evidence. The
following were fixed and re-run under a new run id `audit-p0-reviewfix-20261028T1540`
(the `...T1515` run was a dirty-tree development attempt and was deleted):

1. `discover_maml_opt` path-concatenation TypeError (`Path / "MAML" + "..."`);
   maml-opt API table is now populated and a test exercises the real scan roots.
   The legacy 13-variable application scan is restricted to code files and its
   blocker states that 137 files were scanned and 40 textual hits (tutorial index
   JSONs and this audit itself) are not a candidate application source, so the
   historical app `remains unlocated` rather than being hidden by index hits.
2. OpenVSP probe now puts all four package roots on `sys.path`
   (`python`, `python/openvsp`, `python/degen_geom`, `python/utilities`); the
   SUAVE Python 3.9 worker imports openvsp, so the blocker became a minor
   "external worker ABI" constraint instead of a major "binding unusable" claim.
3. `toolchain_table.md` marks distributions without an import probe as
   `not_probed` instead of a failed import with `error=None`.
4. Added `pip check`, rcaide-multifidelity source-test log and run `README.md`.
5. `concorde_structure.md` now reports per-component `append_segment` counts,
   mission segment tags, `level_cruise` line, duplicate segment tags and
   derived-quantity markers.
6. README references and `wall_seconds` documentation corrected.
7. `discover_external_tools` no longer mutates global state / relies on `break`.
8. Host absolute paths in generated evidence are placeholdered; tool install paths
   are documented as non-private.

## P1 status (in progress)

P1 freezes the 15-variable order and adds the geometry pipeline. The first step is
committed as a provisional contract, not a finished geometry model:

- `configs/design_space_15d.yaml` — frozen W01–W10 / V01–V02 / F01–F03 order and
  identifiers from Issue #1, SI units, baseline values read from
  `tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py`
  (sha256 recorded in the file), and **provisional** bounds tagged
  `bounds_status: provisional_until_geometry_perturbation` / `frozen: false`.
  The file also records the planned derived-quantity rules (span, chords, wetted
  area placeholder, tail span, fuselage height, mass/CG still `NOT_IMPLEMENTED`)
  and cross constraints C01–C04.
- `config_io.py` — dependency-free config loading. The project environment has no
  PyYAML (and no network to install it), so `.yaml` files use PyYAML when present
  and otherwise a strict indentation-based subset loader (nested mappings,
  sequences, inline scalar lists, comments, quoted scalars; rejects tabs,
  bad indentation and duplicate keys with line numbers).
- `aircraft/design_space.py` — `DesignVariable`/`DesignSpace` dataclasses,
  `load_design_space()`, order/unit/range validation, baseline and cross-constraint
  checks, and normalized views `(x - baseline)/scale` plus `(x - lower)/(upper - lower)`.

Geometry discovery `geometry-check` is still declared but not implemented; the P1
exit gate requires a real 15-variable geometry builder, derived-quantity
recomputation, ≥31 perturbation cases and the effect matrix.

Run the P1 tests:

```bash
./run_rcaide.cmd -m unittest discover -s research/concorde_metaopt/tests -t . -v
```

## Host/sandbox constraints (recorded, not hidden)

- The first audit (2026-10-27) ran under a Windows file sandbox that denied child
  processes and writes to `.git/`, `outputs/` and `docs/`; git/tool facts were
  captured by the bash probe and merged under `probe_source: "shell_probe"`.
- The current session has danger-full-access; `probe_source` still records whether
  a fact came from the direct Python path or from a shell probe.
- Writes to `tempfile.mkdtemp` directories were denied in the sandbox; tests
  therefore use `research/concorde_metaopt/tests/_tmp/` (git ignored).
- `pytest` is not installed in `envs/RCAIDE`; tests run with `unittest`:
  `./run_rcaide.cmd -m unittest discover -s research/concorde_metaopt/tests -t . -v`.

## Tests

`tests/test_audit.py` (17 tests) covers the SHA-256 helper, Markdown table
rendering, Concorde scanning (real identifiers, component counts, duplicate tags,
level_cruise), blocker construction (dirty/clean worktree, OpenVSP external-worker
severity, Gmsh absence, MAML source/direct_url), shell-probe precedence for git
facts, maml-opt scan roots (regression for the TypeError), external-tool
global-state immutability, toolchain `not_probed` handling, and an end-to-end
mocked `run_audit` that writes `environment.json`/`summary.json`/`README.md`/
evidence without any simulation.

`tests/test_design_space.py` (33 tests) covers the real 15D config (order,
identifiers, units, provisional status, baseline SHA), normalization roundtrips,
bound/cross-constraint violations, rejection of missing/duplicate/reordered
variables, wrong units, out-of-range baselines, a frozen flag before the measured
bounds exist, and the YAML-subset loader (nested data, inline lists, comments,
quotes, tabs, duplicate keys, bad indentation).

All 50 tests pass.

## Out of scope so far

No geometry construction/perturbation matrix yet, no Mission evaluation, no SU2
case, no DOE dataset, no BO, no MAML. Those require the P1–P6 code gates and
explicit user approval for true-evaluation budgets. The P1 config is provisional
and must not be cited as a frozen design space.
