# A5 independent review — D-12D-003 Round-1 package (dbc325d)

- Reviewer: A5 (a5-code-reviewer), independent session; read-only review, zero solver starts, zero new numerical analysis
- Review target: commit dbc325dd9d7412b48e0399061a86d61eb0de6941 (parent 5dcb0bf), worktree D:/RCAIDE-verify-a5-dbc325d
- Package: research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/ (35 run-directory files, of which 34 manifest entries + data_manifest.json) and docs/reviews/p1p3_d12d003_round1_remediation_report_20261102.md
- Verdict: **APPROVE_FOR_DELIVERY** (0 blocker, 0 major, 8 minor, 1 info). No gate is approved and none is claimed.

## 1. Independent verification performed

Worktree was clean before and after review (tracked/untracked empty; HEAD dbc325d). No repository write, no git index change, no GitHub write, OpenVSP was not imported, no solver or numerical analysis was started. All scripts/logs are under the external directory C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/openvsp355-round1/a5/.

1. **Commit shape / isolation** — exactly 36 changed files = 35 run-directory files + 1 docs report; single parent 5dcb0bf; no P5/MAML/learning path in the commit; largest blob is the PNG (95,305 B); no secrets found in package text.
2. **Manifest reproducibility** — all 43 manifest entries (34 run files + 8 input_source_files + 1 report_file) rehashed over canonical-LF bytes in the checked-out worktree: **43/43 match, 0 mismatch, 0 missing, 0 extra**; file_count 34 and total_bytes 407,111 are self-consistent; data_manifest.json's own canonical-LF sha256 recomputes to `35afc8fb269915bdc86936a83bb9b1981f3cd2d1a0cec3b6408ac5a42a235e7d`, exactly the value requested. Details: manifest_verification.json.
3. **JSON validity** — all **14** JSON files in the package parse: summary, data_manifest, budget_request_round2, install_provenance, evidence/{api_compat_355, geometry_parity_355_vs_326, source_evidence_355, tooling_events, vspaero7_setup_artifacts, vspaero7_setup_generation}, role_reviews/a1/{geometry_diff, vspaero_old_evidence}, role_reviews/a2/area_rule_candidates, role_reviews/a3/facts.
4. **Cross-document numeric consistency** — verified against evidence JSON/CSV: archive 49,664,844 B / f1fde65f...; new install 491 files / 149,488,735 B and vspaero.exe 811,520 B / db71c441...; old 3.26.1 vspaero 561,664 B / e1affca0... untouched (240 files, none newer than 2026-11-01); API 2186 names / 22 analyses / VSPAEROSweep 80 inputs / WaveDrag 8 / EmintonLord 2 (2176-vs-2186 count difference disclosed); wing 1082/1082 unique vertices, only_old=only_new=0 for baseline and W10; W10 max|dz| 0.03396196 m vs expected 0.03396196030486226 m, max|dy|=0; fuselage 559 vs 552, only_old 129 / only_new 122, NN median 4.382 mm / max 30.0722 mm; thick vspgeom 503,013 B / 494feef5... 1082 nodes / 1088 elements, thin 224,357 B / 9fcda6d5... 527/480; both setup files 42 lines, committed canonical 888 B / 360618f4... (raw OpenVSP CRLF form 930 B / c862aa220bc6f3a9..., see F-02); injected Sref 358.25, Cref 18.489893, Bref 25.604638, Xcg 16.821978259514246, MachStart/End 2.02, Alpha 2, Beta 0, RefFlag 0, Symmetry 0, NCPU 4, StopBeforeRun 1; generated .vspgeom header v3 with matching node/element counts; archived VSPAERO diagnosis CL 31.77605/31.32113/31.48770 normalized by case Sref to 0.08782/0.08743/0.08789 vs baseline 0.08781966, CDi +3.435104e-4 / -8.942229e-4 / -2.260794e-2, CL coarse->fine +29.09%; area-rule statistics (SH theory 0.10185916357881301, cond numbers, sigma amplification table, break bias, resolution 2.87, WAVE-05 outliers, paired SNR 0.89/1.69) match the role JSON/CSV; budget caps A10/B2/C6/D6/E2, max_starts_sum 26, recommended_cap 23, tier1 22 / tier2 4, PROPOSED_NOT_APPROVED, no carryover; gate table unchanged.
5. **Zero-solver evidence** — tooling_events.json: 8 events TG-001..TG-008, every solver_starts=0, policy totals 0; setup_generation.json solver_start_count=0, proof flags true, StopBeforeRun=1; the package contains no .polar/.history/.lod/.adb/.groups/.csf/.vkey/.stl/.vspgeom and no solver output; round-1 scripts contain no subprocess/os.system/Popen/solver invocation; no budget was executed. Verified independently (not just read from the claim).
6. **Honesty / gates** — no gate is passed or approved; BUDGET is AWAITING_OWNER_APPROVAL with the Round-2 request PROPOSED_NOT_APPROVED; APPROVED_FOR_NEXT_STAGE NOT ISSUED; P4 is DRAFT / PLAN-ONLY / NOT APPROVED; scope is stated lifting-surfaces-only and BODY-CORR remains BLOCKED; non-claims sections present in README and report. The only wording issues are the minor findings below.

Total: 109 independent checks (28 in part 1, 81 in part 2) — all pass except the deliberately recorded inconsistency findings; command and result log: commands.log.

## 2. Findings

full table with claim/evidence/fix: findings.csv.

| id | severity | location | finding |
|---|---|---|---|
| F-01 | minor | research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/data_manifest.json:9,74 | canonical-LF hashing applied to the binary PNG (raw 95,305 -> canonical 95,303 B), so manifest bytes/sha describe a normalized binary |
| F-02 | minor | research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/README.md:91-92; report:41 | "930 B / c862aa" is the raw CRLF setup file; committed canonical-LF file is 888 B / 360618f4 (not disclosed) |
| F-03 | minor | research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/role_reviews/a3/install_audit.md:25,27,97-98; report:80 | A3 audited CRLF originals (provenance 5,147/3da3dc7a, usage 1,546/3bc9b1d1) vs archived LF (5,033/6305eb12, 1,513/34b30863); A3 checks.log missing from archive while report says "archived verbatim" |
| F-04 | minor | research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/role_reviews/a1/api_compat_matrix.md:7 | matrix says 28 rows C01-C28, CSV has 29 data rows C01-C29, role README says 29-item (C29 is a PASS note; no missing authorization evidence) |
| F-05 | minor | research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/README.md:39 | "no User/Machine/Process PATH entry" is too broad: old 3.26.1 PATH entries exist, only 3.55 is absent (A3 C12 itself is precise) |
| F-06 | minor | research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/README.md:142; report:51; role README:15; A2 md:64 | "58x to 18,380x" noise amplification understates the sigma=0.002 case (own table: 8.724x; 58.175x is sigma=0.005) |
| F-07 | minor | report:57; research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/p4_plan_only_draft.md:10,40; summary.json:357 | "unchanged in substance" does not disclose BUDGET label change EXHAUSTED -> AWAITING_OWNER_APPROVAL; P4 draft still says EXHAUSTED |
| F-08 | minor | research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/README.md:62-63 | fuselage bbox values and "1627 unique wing+body vertices" are not in geometry_parity_355_vs_326.json (only external EXT STLs support them) |
| F-09 | info | research/concorde_metaopt/optimization_runs/openvsp355-remediation-20261102T014411Z/README.md:135 | "about 1e-6" CDWave reproduction; exact max is 1.79e-6 (WAVE-05) |

None of these findings changes the zero-solver, no-gate-approved, or no-physics-claim status of Round-1. F-02/F-03/F-04 are reproducibility/wording issues between raw and canonical forms or between role documents; F-07 is a gate-label disclosure issue. They are recommended to be fixed before the package is quoted in an owner-facing receipt, but do not block delivery.

## 3. Limitations

- Static review only: no OpenVSP import, no solver start, no numerical re-run, no re-execution of A1/A2/A3 probes (per zero-physics constraint).
- External artifacts outside git (big .vspgeom files, EXT STLs) were checked for declared hashes where referenced; the fuselage bbox / 1627-vertex totals could not be traced inside the package (F-08).
- Runtime claims about VSPAERO 7.2.2 behavior at Mach 2.02 remain unverified by design; Round-1 only claims setup-file generation and geometry parity.
- Toolchain: D:/RCAIDE/envs/RCAIDE/python.exe 3.11.17; git worktree D:/RCAIDE-verify-a5-dbc325d at dbc325d.

## 4. Verdict

**APPROVE_FOR_DELIVERY** — Round-1 package is internally reproducible (manifest 43/43, self-hash exact), zero-solver evidence is independently verified, no gate is approved or overstated, and no P5/MAML or secret material is mixed in. 0 blocking, 0 major, 8 minor, 1 info; see findings.csv for per-item evidence and fixes.

Signed: A5, 2026-11-02 (Asia/Shanghai)
