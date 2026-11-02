# Role review deliverables (canonical-LF copies)

This directory archives the independent role deliverables for the D-12D-003 Round-1 package. Files were
copied from the project-external agent state root into this repository package. They are **not** verbatim
byte copies when the source file had CRLF line endings: text was normalised to canonical LF to match the
package hashing convention (`data_manifest.json`: `hash_mode: canonical_lf` for text,
`hash_mode: raw` for binaries).

The two log files (`a3/install_checks.log`, `a5/commands.log`) are force-added to git because the
repository `.gitignore` ignores `*.log`; they are evidence files and are listed in `data_manifest.json`.

| Role | File(s) | Source | Bytes note |
| --- | --- | --- | --- |
| A1 code-dev | `a1/api_compat_checks.csv`, `a1/api_compat_matrix.md`, `a1/geometry_diff.json` | task-36/37 | text; C29 row of the CSV normalised to the 8-column schema in revision 2 |
| A1 code-dev | `a1/vspaero_old_diagnostic.md`, `a1/vspaero_old_evidence.json` | task-36/37 | text |
| A1 code-dev | `a1/zero_solver_audit.md`, `a1/evidence.json` | task-43 | text; the audit cites raw `install_provenance.json` 5,147 B sha `3da3dc7a...` vs canonical 5,033 B sha `6305eb12...` (CRLF) |
| A2 run-opt | `a2/area_rule_offline.md`, `a2/area_rule_cases.csv`, `a2/area_rule_candidates.json` | task-38/39 | text |
| A3 repo-guard | `a3/install_audit.md`, `a3/facts.json` | task-35 | text |
| A3 repo-guard | `a3/delta_isolation_dbc325d.md`, `a3/delta_facts.json` | task-42 | text |
| A3 repo-guard | `a3/install_checks.log` | task-35 | log copied from the external state root |
| A4 issue-liaison | `a4/requirements_matrix.md`, `a4/requirements.csv`, `a4/round_plan.md` | task-34/44 | text |
| A5 code-reviewer | `a5/round1_package_review.md`, `a5/findings.csv`, `a5/manifest_verification.json`, `a5/verdict.txt`, `a5/commands.log` | task-41 | canonical-LF copies |

Status summary: A1 zero-solver audit CONFIRMED (with the TG-008 banner-probe disclosure); A2 area rule
NOT_VALIDATED / paired increment INCONCLUSIVE; A3 install audit PASS and delta isolation PASS 7/7; A4
requirements mapped (35 items) and receipt draft DRAFT_NOT_POSTED; A5 package review APPROVE_FOR_DELIVERY
(0 blocker / 0 major / 8 minor / 1 info, resolved in post-review revision 2).

No role deliverable started a solver. The package-level zero-solver statement is in
`../evidence/tooling_events.json` and `../summary.json`.