# -*- coding: utf-8 -*-
"""Rev2 package-builder patches for A5 task-148 findings (A5-B2PKG-01..06).

Zero solver. Patches builder text only; run build_d12d005_package.py afterwards.
"""
import io, sys

BUILD = 'D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/build_d12d005_package.py'
PATCHB = 'D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/patch_build.py'
BLOCK = 'D:/RCAIDE-d12d005/research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/scripts/report_block.txt'

src = io.open(BUILD, 'r', encoding='utf-8').read()

reps = []

# --- A5-B2PKG-01: real stop key + helper for sect tess scalar
reps.append((
"B2 = load_json(ensure(RUN_DIR + '/evidence/batch2/batch2_results.json'))",
"B2 = load_json(ensure(RUN_DIR + '/evidence/batch2/batch2_results.json'))\nV1_STOP = (V1.get('stop') or {})\nV1_STOP_TRIGGER = (V1_STOP.get('trigger') or {})\n\n\ndef _sect_tess_scalar(a0v2_case):\n    mr = a0v2_case.get('model_readback') or {}\n    vals = mr.get('sect_tess_u_readback') or (mr.get('readback') or {}).get('sect_tess_u') or mr.get('SectTess_U')\n    if isinstance(vals, (list, tuple)) and vals:\n        return max(vals)\n    return vals\n"))

reps.append((
"            'billable': True,\n            'stop_rule_hit': None,\n",
"            'billable': True,\n            'stop_rule_hit': (V1_STOP_TRIGGER.get('rule') if V1_STOP_TRIGGER.get('case_id') == case['case_id'] else None),\n"))

reps.append((
"    'batch1_stop_decision': (V1.get('stop_decision') or {}), ",
"    'batch1_stop_decision': V1_STOP,"))

# --- A5-B2PKG-06: fill sect tess from a0v2 readback
reps.append((
"        'a0v2_sect_tess_u': dict((cid, A0V2_CASES[cid].get('model_readback', {}).get('SectTess_U') or A0V2_CASES[cid].get('tess_readback')) for cid in sorted(A0V2_CASES)),",
"        'a0v2_sect_tess_u': dict((cid, _sect_tess_scalar(A0V2_CASES[cid])) for cid in sorted(A0V2_CASES)),\n        'a0v2_sect_tess_u_note': 'read back from OpenVSP model per section (max of sections); B2-01/02/03 = 3/6/12, B2-04..B2-07 = 12, S6 = 20',"))

# --- A5-B2PKG-02: report 9.4 wording (also patched in report_block.txt)
reps.append((
"    bt('- 入库后 @BT@data_manifest.json@BT@ 对 run 目录全部文件（含 5 张图、本报告）记录 raw + canonical-LF 双哈希。'),",
"    bt('- 入库后 @BT@data_manifest.json@BT@ 对 run 目录内全部文件逐文件记录 raw + canonical-LF 双哈希；本报告与 5 张图作为 @BT@external_artifacts@BT@ 条目记录 raw sha256（文本报告另记 canonical-LF 与 verified），a2 溯源副本目录逐文件记录 sha256/bytes。'),"))

# --- A5-B2PKG-03: batch2 bytes raw scope note
reps.append((
"        'batch2_bytes': 7788381,",
"        'batch2_bytes': 7788381,\n        'batch2_bytes_scope': 'pre-commit worktree raw bytes of evidence/batch2 (241 files); clean checkout bytes are slightly smaller because git normalizes tracked text files to LF (see data_manifest.checkout_verification).',"))

# --- A5-B2PKG-05: pushed flag no longer stale
reps.append((
"    'repo': {'path': REPO, 'branch': 'research/d12d005-aero-fallback', 'head': HEAD, 'head_short': HEAD[:7], 'main_head': 'ec65e5a', 'merged_to_main': False, 'pushed': False},",
"    'repo': {'path': REPO, 'branch': 'research/d12d005-aero-fallback', 'head': HEAD, 'head_short': HEAD[:7], 'main_head': 'ec65e5a', 'merged_to_main': False, 'pushed': True, 'pushed_note': 'package commits up to cb45917 pushed to origin/research/d12d005-aero-fallback; the commit for this revision is recorded in the Issue #4 receipt', 'as_of_git_snapshot': HEAD + ' (execution HEAD snapshot at build time)'},"))

# --- A5-B2PKG-04: shared REVIEW_REFS + run_config environment/review_refs
REVIEW = """REVIEW_REFS = {
    'A5': [
        {'task': 'task-120', 'verdict': 'APPROVE_FOR_BATCH1B', 'path': 'EXT/d12d005/a5/a0_rev6_delta/verdict.txt', 'sha256_raw': sha_file(ensure(EXT_D12 + '/a5/a0_rev6_delta/verdict.txt'))},
        {'task': 'task-125', 'verdict': 'CHANGES_REQUESTED', 'path': 'EXT/d12d005/a5/batch1b_review/verdict.txt', 'sha256_raw': sha_file(ensure(EXT_D12 + '/a5/batch1b_review/verdict.txt'))},
        {'task': 'task-131', 'verdict': 'APPROVE_BATCH2_8', 'path': 'EXT/d12d005/a5/batch2_prestart_gate/verdict.txt', 'sha256_raw': sha_file(ensure(EXT_D12 + '/a5/batch2_prestart_gate/verdict.txt'))},
        {'task': 'task-131-erratum', 'verdict': 'ERRATUM_S4_S5_EXECUTED_IN_BATCH1B', 'path': 'EXT/d12d005/a5/batch2_prestart_gate/verdict_v2.txt', 'sha256_raw': sha_file(ensure(EXT_D12 + '/a5/batch2_prestart_gate/verdict_v2.txt'))},
        {'task': 'task-138', 'verdict': 'APPROVE_BATCH2_RESULTS_AND_CLOSE_A_LINE', 'path': 'EXT/d12d005/a5/batch2_results_review/verdict.txt', 'sha256_raw': sha_file(ensure(EXT_D12 + '/a5/batch2_results_review/verdict.txt'))},
    ],
    'A3': [
        {'task': 'task-121', 'verdict': 'PASS', 'path': 'EXT/d12d005/a3/facts_a0_rev6.json', 'sha256_raw': sha_file(ensure(EXT_D12 + '/a3/facts_a0_rev6.json'))},
        {'task': 'task-134', 'verdict': 'PASS', 'path': 'EXT/d12d005/a3/prestart_audit/facts_prestart.json', 'sha256_raw': sha_file(ensure(EXT_D12 + '/a3/prestart_audit/facts_prestart.json'))},
        {'task': 'task-139', 'verdict': 'PASS', 'path': 'EXT/d12d005/a3/batch2_evidence_audit/facts_batch2_evidence_audit.json', 'sha256_raw': sha_file(ensure(EXT_D12 + '/a3/batch2_evidence_audit/facts_batch2_evidence_audit.json'))},
    ],
    'lead_authorizations': [
        {'id': 'A0/0e62db3 batch1 auth', 'path': 'evidence/v1/run_start.json', 'sha256_raw': sha_file(ensure(RUN_DIR + '/evidence/v1/run_start.json'))},
        {'id': 'batch1b reauthorization', 'path': 'evidence/lead/batch1b_reauthorization.md', 'sha256_raw': sha_file(ensure(RUN_DIR + '/evidence/lead/batch1b_reauthorization.md'))},
        {'id': 'D12D005-BATCH2-20261104T130635Z', 'path': 'EXT/d12d005/lead/D12D005_BATCH2_AUTHORIZATION_20261104T130635Z.json', 'sha256_raw': sha_file(ensure(EXT_D12 + '/lead/D12D005_BATCH2_AUTHORIZATION_20261104T130635Z.json'))},
    ],
}

"""
reps.append((
"write_json('approval_and_budget_ledger.json', BUDGET)\n",
"write_json('approval_and_budget_ledger.json', BUDGET)\n\n" + REVIEW))

reps.append((
"    'deliverables_expected': ['run_config.json',",
"    'review_refs': REVIEW_REFS,\n    'environment': {\n        'platform': 'Windows (host)',\n        'python_version': sys.version.split()[0],\n        'worktree': REPO,\n        'run_dir': RUN_REL,\n        'openvsp_root': 'D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64',\n        'vspaero_exe': VSPAERO_EXE,\n        'vspaero_version': '7.2.2',\n        'vspaero_exe_sha256': VSPAERO_SHA,\n    },\n    'deliverables_expected': ['run_config.json',"))

# replace SUMMARY review_refs literal block with REVIEW_REFS
import re
pat = re.compile(r"    'review_refs': \{.*?\n    \},\n    'deliverables': deliverables,", re.S)
if not pat.search(src):
    print('MISS summary review_refs block'); sys.exit(3)
src = pat.sub("    'review_refs': REVIEW_REFS,\n    'deliverables': deliverables,", src, count=1)
reps.append(("PLACEHOLDER_NEVER", "PLACEHOLDER_NEVER")) if False else None

# --- A5-B2PKG-02: manifest external report/a2 entries
reps.append((
"external.append({'kind': 'report', 'path': REPORT_REL, 'sha256_raw': sha_file(REPORT_DEST), 'bytes': os.path.getsize(REPORT_DEST), 'outside_git': False})",
"rep_data = read_bytes(REPORT_DEST)\nexternal.append({'kind': 'report', 'path': REPORT_REL, 'sha256_raw': sha_bytes(rep_data), 'sha256_canonical_lf': sha_bytes(canonical_lf(rep_data)) if is_text_bytes(rep_data) else None, 'bytes': len(rep_data), 'outside_git': False, 'verified': True})"))

reps.append((
"external.append({'kind': 'a2_provenance_bundle', 'path': A2_REL, 'outside_git': False, 'files': a2_count})",
"a2_file_records = []\nfor a2_root, a2_dirs, a2_names in os.walk(A2_DEST):\n    a2_dirs.sort()\n    for a2_name in sorted(a2_names):\n        a2_p = os.path.join(a2_root, a2_name)\n        a2_data = read_bytes(a2_p)\n        a2_file_records.append({'path': os.path.relpath(a2_p, A2_DEST).replace(chr(92), '/'), 'bytes': len(a2_data), 'sha256_raw': sha_bytes(a2_data), 'sha256_canonical_lf': sha_bytes(canonical_lf(a2_data)) if is_text_bytes(a2_data) else None})\nexternal.append({'kind': 'a2_provenance_bundle', 'path': A2_REL, 'outside_git': False, 'file_count': len(a2_file_records), 'files': a2_file_records})"))

missing = []
for old, new in reps:
    if old not in src:
        missing.append(old[:80]); continue
    src = src.replace(old, new, 1)
if missing:
    print('MISSING anchors:', len(missing))
    for m in missing: print('  -', m)
    sys.exit(4)
io.open(BUILD, 'w', encoding='utf-8', newline='').write(src)
print('builder patched: bytes=', len(src), 'replacements=', len(reps))

# report_block.txt same 9.4 line for reproducibility
block = io.open(BLOCK, 'r', encoding='utf-8').read()
old_line = "    bt('- 入库后 @BT@data_manifest.json@BT@ 对 run 目录全部文件（含 5 张图、本报告）记录 raw + canonical-LF 双哈希。'),"
new_line = "    bt('- 入库后 @BT@data_manifest.json@BT@ 对 run 目录内全部文件逐文件记录 raw + canonical-LF 双哈希；本报告与 5 张图作为 @BT@external_artifacts@BT@ 条目记录 raw sha256（文本报告另记 canonical-LF 与 verified），a2 溯源副本目录逐文件记录 sha256/bytes。'),"
if old_line in block:
    io.open(BLOCK, 'w', encoding='utf-8', newline='').write(block.replace(old_line, new_line, 1))
    print('report_block patched')
else:
    print('WARN report_block line not found')

# patch_build.py rep for stop_decision key
pb = io.open(PATCHB, 'r', encoding='utf-8').read()
old_pb = "'batch1_stop_decision': (V1.get('stop_decision') or {}), "
new_pb = "'batch1_stop_decision': V1_STOP,"
if old_pb in pb:
    io.open(PATCHB, 'w', encoding='utf-8', newline='').write(pb.replace(old_pb, new_pb, 1))
    print('patch_build patched')
else:
    print('WARN patch_build anchor not found')
