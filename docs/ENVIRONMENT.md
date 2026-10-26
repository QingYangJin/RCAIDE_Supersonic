# Environment and rebuilding scope

The published workspace uses RCAIDE-LEADS 1.5.0 as its core dependency. `requirements.txt` is the core installation entry point; it does not reproduce every optional package installed on the original workstation.

## Current workstation snapshot: 2026-10-26

Python 3.11.17, RCAIDE-LEADS 1.5.0, RCAIDE-GUI 1.2.0, NumPy 2.4.6, SciPy 1.17.1, Matplotlib 3.11.2, pandas 3.0.6, torch 2.8.0, maml-opt 0.1.0, rcaide-cpacs 0.1.0 and rcaide-multifidelity 0.1.0 were installed. A full 83-distribution version inventory is recorded in `requirements/current-windows-inventory.txt`.

That inventory is an observation, not an independently resolvable or hash-locked recipe. In particular:

- `maml-opt`, `rcaide-cpacs` and `rcaide-multifidelity` require separately maintained source or versioned build artifacts. Their source projects and wheels are not included here. Do not assume identically named public packages provide the intended implementation.
- `package-name==0.1` is present in the original environment with unclear purpose; it is not added to core installation requirements.
- The older `installation/environment.yml` and `installation/requirements-lock.txt` omit 21 subsequently installed distributions; they remain historical records, not complete restoration instructions.
- Optional GUI/native libraries and external solvers need separate installation and runtime checks. A successful basic analysis does not validate those paths.

## Maintenance checks

`run_rcaide.cmd` locates the project environment relative to the checkout, preserves DLL search paths needed by the current Conda layout, disables bytecode writes, and isolates Python environment variables and user site packages with `-E -s`.

The Windows workflow creates a fresh project venv, installs core dependencies and runs dependency consistency, standard atmosphere and stall-speed checks. Its live run determines whether the current public dependency resolution works on the hosted runner. It does not execute long aircraft optimizations, the optional custom packages, or GUI interactions.

Existing analysis scripts and numerical/optimization settings are preserved during publication. The environment-guard path calculation and publication/attribution files were updated on 2026-10-26.
