import io
import sys
B = 'D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/build_d12d005_package.py'
BLOCK = 'D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/report_block.txt'
src = io.open(B, 'r', encoding='utf-8').read()
block = io.open(BLOCK, 'r', encoding='utf-8').read()
start = src.index("print('stage: report')")
end = src.index("print('stage: results summary')")
src = src[:start] + block + src[end:]
reps = [
  ("'contract_std_S6': {'Sref': 4.0, 'Cref': 1.0, 'Bref': 4.0, 'X_cg': 0.25, 'AoA': 1.0, 'Mach': 2.02, 'ReCref': 2417456.008134507, 'NumWakeNodes': 8, 'WakeIters': 5},",
   "'contract_std_S6': b2_contracts['S6_STD_M2p02_aoa1'],"),
  ("b2_cases = dict((c['case_id'], c) for c in B2['cases'])",
   "b2_cases = dict((c['case_id'], c) for c in B2['cases'])" + chr(10) + "b2_contracts = dict((c['case_id'], c['contract']) for c in B2['cases'])"),
  ("'batch1_stop_decision': {'artifact_kind': V1.get('stop_decision', {}).get('artifact_kind'), 'status': V1.get('stop_decision', {}).get('status'), 'trigger': V1.get('stop_decision', {}).get('trigger') if isinstance(V1.get('stop_decision'), dict) else None},",
   "'batch1_stop_decision': V1_STOP,"),
  ("'delta_CLtot': V1B.get('deltas_s4_vs_s3_single_factor_wake_nodes', {}).get('CLtot'),",
   "'delta_s4_vs_s3': V1B.get('deltas_s4_vs_s3_single_factor_wake_nodes'),"),
  ("'delta_CDi': V1B.get('deltas_s4_vs_s3_single_factor_wake_nodes', {}).get('CDi'),",
   "'s5_vs_s4_cross_geometry': V1B.get('s5_vs_s4_cross_geometry'),"),
  ("'archived_model_sha256': A0V2.get('archived_model', {}).get('sha256'),",
   "'archived_model': A0V2.get('archived_model'),"),
  ("'archived_thin_vspgeom_12d_sha256': (A0V2.get('archived_thin_vspgeom') or {}).get('d12'),",
   "'archived_thin_vspgeom': A0V2.get('archived_thin_vspgeom'),"),
  ("'archived_thin_vspgeom_std_sha256': (A0V2.get('archived_thin_vspgeom') or {}).get('std'),",
   "'a0v2_readback_status': 'A0V2_SETUP_READY_NO_SOLVER',"),
  ("'physics_validation_status': 'LF_PROVISIONAL' if False else 'NOT_APPLICABLE'",
   "'physics_validation_status': 'NOT_APPLICABLE'"),
  ("'wall_seconds': case['wall_seconds'],",
   "'wall_seconds': case['wall_seconds']," + chr(10) + "            'peak_rss_gb': case.get('peak_rss_gb'),"),
]
cnt = 0
for old, new in reps:
    if old not in src:
        print('MISS:', old[:70])
        sys.exit(3)
    n = src.count(old)
    src = src.replace(old, new)
    cnt += 1
    print('patched', cnt, 'occurrences', n)
io.open(B, 'w', encoding='utf-8', newline='').write(src)
print('ok spliced report block, file bytes=', len(src))
