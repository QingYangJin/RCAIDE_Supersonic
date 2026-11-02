# Audit run audit-p0-reviewfix-20261028T1540

Read-only P0 environment/source audit for RCAIDE_Supersonic Issue #1.
No Mission, CFD case, DOE or optimization was executed.

| field | value |
| --- | --- |
| generated_at | 2026-10-28T07:18:07.358991+00:00 |
| stage | P0 |
| status | audit_completed |
| git_sha | fdadeaa064f7c54d9d46dc763ea57740677644fa |
| wall_seconds | 12.072 |
| total_true_evaluations | 0 |
| blockers | 9 |

## Files

- environment.json: full environment snapshot and blocker list
- summary.json: Issue #1 mandatory summary fields (missing values are null)
- evidence/: tables and raw command outputs mirrored as JSON/Markdown
- probes/: raw shell-probe outputs and shell_probes.json (when present)

## Reproduction

See research/concorde_metaopt/README.md (probe -> assemble_probes -> audit).

## Notes

Repository root, user home and the external evidence root are replaced by
placeholders in generated JSON/Markdown; tool install locations are kept for
reproducibility and contain no username or secret.
- Read-only audit: no Mission, CFD case or optimization was executed.
- Missing or unobservable values are null; failed probes are recorded with their error text.
- Generated evidence placeholders the repository root, the user home and the external evidence root; standard tool install locations are kept because they contain no username, token or secret path.
- The run directory contains a README.md describing this run and its reproduction commands.
- Git and external tool facts include a shell probe conducted by research/concorde_metaopt/scripts/probe_external_tools.sh; probe_source records which path supplied them.
