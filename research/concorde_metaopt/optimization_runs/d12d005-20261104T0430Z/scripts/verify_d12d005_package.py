#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent verifier for the d12d005 package manifest. Read-only."""
import csv
import hashlib
import json
import math
import os
import sys

REPO = 'D:/RCAIDE-d12d005'
RUN_ID = 'd12d005-20261104T0430Z'
RUN_REL = 'research/concorde_metaopt/optimization_runs/' + RUN_ID
RUN_DIR = REPO + '/' + RUN_REL

checks = []


def chk(name, ok, detail=None):
    checks.append({'name': name, 'ok': bool(ok), 'detail': detail})


def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def sha(b):
    return hashlib.sha256(b).hexdigest()


def eol(b):
    if bytes([13, 10]) in b:
        return 'crlf'
    if bytes([10]) in b:
        return 'lf'
    return 'none'


def canon(b):
    return sha(b.replace(bytes([13, 10]), bytes([10])))


def is_text(b):
    if bytes([0]) in b:
        return False
    try:
        b.decode('utf-8')
        return True
    except UnicodeDecodeError:
        return False


def record(p):
    b = read_bytes(p)
    t = is_text(b)
    r = {'bytes': len(b), 'sha256_raw': sha(b), 'is_text': t, 'eol': eol(b)}
    if t:
        r['sha256_canonical_lf'] = canon(b)
    return r


M = json.load(open(RUN_DIR + '/data_manifest.json', encoding='utf-8'))
chk('manifest_schema', M.get('schema') == 'd12d005-data-manifest-1')
chk('manifest_run_id', M.get('run_id') == RUN_ID)
files = M['files']
listed = dict((r['path'], r) for r in files)
walked = []
for dp, dn, fn in os.walk(RUN_DIR):
    dn[:] = sorted(d for d in dn if d != '__pycache__')
    for n in sorted(fn):
        if n.endswith('.pyc'):
            continue
        p = os.path.join(dp, n)
        rel = os.path.relpath(p, RUN_DIR).replace(chr(92), '/')
        if rel == 'data_manifest.json':
            continue
        walked.append(rel)
chk('manifest_covers_all_run_files', sorted(walked) == sorted(listed.keys()), {'walked': len(walked), 'listed': len(listed)})
bad = []
canon_mismatch = []
for rel, rec in sorted(listed.items()):
    p = RUN_DIR + '/' + rel
    if not os.path.exists(p):
        bad.append((rel, 'missing'))
        continue
    live = record(p)
    for k in ('bytes', 'sha256_raw', 'is_text', 'eol'):
        if live[k] != rec[k]:
            bad.append((rel, k, rec[k], live[k]))
    if 'sha256_canonical_lf' in rec and live.get('sha256_canonical_lf') != rec['sha256_canonical_lf']:
        canon_mismatch.append(rel)
chk('manifest_hash_verification', not bad and not canon_mismatch, {'bad': bad[:5], 'canon_mismatch': canon_mismatch[:5], 'files': len(listed)})
chk('manifest_totals', M['totals']['run_dir_files'] == len(listed) and M['totals']['run_dir_bytes'] == sum(r['bytes'] for r in listed.values()), M['totals'])
chk('manifest_self_omitted', 'data_manifest.json' not in listed)

deliverables = ['run_config.json', 'approval_and_budget_ledger.json', 'evaluations.jsonl', 'solver_case_matrix.csv', 'vspaero_diagnostics.json', 'rcaide_fallback_results.json', 'su2_crosscheck.json', 'drag_component_ledger.json', 'summary.json', 'data_manifest.json']
present = [d for d in deliverables if os.path.exists(RUN_DIR + '/' + d)]
chk('ten_deliverables_present', len(present) == 10, present)

for d in deliverables:
    p = RUN_DIR + '/' + d
    try:
        if d.endswith('.json'):
            json.load(open(p, encoding='utf-8'))
        elif d.endswith('.csv'):
            rows = list(csv.reader(open(p, encoding='utf-8', newline='')))
            chk('csv_shape', len(rows) == 15 and len(rows[0]) == 29, {'rows': len(rows), 'cols': len(rows[0]) if rows else 0})
        elif d.endswith('.jsonl'):
            lines = [x for x in open(p, encoding='utf-8').read().splitlines() if x.strip()]
            chk('jsonl_lines', len(lines) == 14, len(lines))
            for x in lines:
                json.loads(x)
    except Exception as exc:
        chk('parse_' + d, False, repr(exc))
        continue
    chk('parse_' + d, True)

evals = [json.loads(x) for x in open(RUN_DIR + '/evaluations.jsonl', encoding='utf-8').read().splitlines() if x.strip()]
from collections import Counter
batches = Counter(e['batch'] for e in evals)
chk('eval_batch_counts', batches.get('D-12D-005-A-batch-1') == 4 and batches.get('D-12D-005-A-batch-1b') == 2 and batches.get('D-12D-005-A-batch-2') == 8, dict(batches))
chk('eval_labels', all(e['labels'][0] == 'VSPAERO_INTERNAL_ONLY' and 'NOT_VALIDATED' in e['labels'] for e in evals))
chk('eval_all_billable', all(e['billable'] is True for e in evals))
wall = sum(e['wall_seconds'] for e in evals)
chk('eval_wall_sum', abs(wall - 50.246) < 0.002, wall)
chk('eval_cases_unique', len(set(e['case_id'] for e in evals)) == 14)
chk('eval_vspgeom_sha_present', all(len(e.get('vspgeom_sha256') or '') == 64 for e in evals))
chk('eval_setup_sha_present', all(len(e.get('setup_sha256') or '') == 64 for e in evals))

S = json.load(open(RUN_DIR + '/summary.json', encoding='utf-8'))
chk('summary_status', S['status'] == 'A_LINE_CLOSED_VSPAERO_NOT_VALIDATED_BATCH2_EXECUTED_AND_REVIEWED', S['status'])
chk('summary_physical', S['physical_accounting']['solver_starts'] == 14 and S['physical_accounting']['class_A_remaining_not_authorized'] == 6)
chk('summary_claim_false', S['physical_accounting']['physical_validation_claim'] is False and S['approved_for_next_stage'] is False)
chk('summary_fallback', S['fallback']['status'] == 'NOT_TRIGGERED' and S['fallback']['class_B_used'] == 0)
chk('summary_su2', S['su2_crosscheck']['class_C_used'] == 0)
chk('summary_gate_lf', S['gate_status']['LF-M2.02']['status'] == 'NOT_VALIDATED')
chk('summary_gate_body', S['gate_status']['BODY-CORR']['status'] == 'BLOCKED')
missing_deliv = [d['path'] for d in S['deliverables'] if not os.path.exists((REPO + '/' + d['path']) if d['path'].startswith('docs/') else (RUN_DIR + '/' + d['path']))]
chk('summary_deliverables_exist', not missing_deliv, missing_deliv)
for d in S['deliverables']:
    p = (REPO + '/' + d['path']) if d['path'].startswith('docs/') else (RUN_DIR + '/' + d['path'])
    live = record(p)
    if live['bytes'] != d['bytes'] or live['sha256_raw'] != d['sha256_raw']:
        chk('summary_deliv_hash_' + d['path'], False, {'rec': d, 'live': live})
        break
else:
    chk('summary_deliverables_hashes', True)

report = open(REPO + '/docs/reviews/d12d005_batch2_report_20261104.md', encoding='utf-8').read()
chk('report_has_final', 'FINAL（Lead 合并稿）' in report)
chk('report_no_draft_marker', 'DRAFT_FOR_LEAD_MERGE' not in report)
chk('report_no_abs_windows_paths', 'C:/Users' not in report and 'C:' + chr(92) + 'Users' not in report and 'D:' + chr(92) + 'RCAIDE' not in report)
chk('report_ew_correction', 'CDiw=0' in report and '派生列 0/0 伪影' in report)
chk('report_b2_04_note', 'Sref=358.25' in report and 'A5B2R-04' in report)
chk('report_snapshot_fields', 'A5B2R-02/03' in report and 'solver_stdout.log' in report)
chk('report_gate2_label', 'DIAGNOSTIC_REPAIR_CONFIRMED_BY_S6' in report)
chk('report_bc_classes', 'RCAIDE VLM 经验低保真回退' in report and 'SU2 Euler 交叉检查' in report)
chk('report_appendix', '## §10 复核与入库记录' in report)
chk('report_figures_section', '### 9.4 图表与复算产物位置（入库后）' in report)
for n in range(1, 6):
    chk('report_fig_link_' + str(n), ('figures/d12d005_batch2/fig' + str(n)) in report)

figdir = REPO + '/docs/reviews/figures/d12d005_batch2'
figs = sorted(os.listdir(figdir)) if os.path.isdir(figdir) else []
chk('five_figures_present', len(figs) == 5 and all(f.endswith('.png') for f in figs), figs)
ext = dict((e['path'], e) for e in M['external_artifacts'] if e.get('path', '').startswith('docs/'))
chk('manifest_links_report', 'docs/reviews/d12d005_batch2_report_20261104.md' in ext)
chk('manifest_links_figures', all(('docs/reviews/figures/d12d005_batch2/' + f) in ext for f in figs), figs)

recc = json.load(open(RUN_DIR + '/run_config.json', encoding='utf-8'))
chk('run_config_head', recc['repo']['head'] == 'c1168ec656160a3e35e5e157050e98ac1fde8cdf')
chk('run_config_contract', recc['frozen_contract']['sref_m2'] == 358.25 and recc['frozen_contract']['mach'] == 2.02)
bud = json.load(open(RUN_DIR + '/approval_and_budget_ledger.json', encoding='utf-8'))
chk('budget_class_a', bud['classes']['A']['used_total'] == 14 and bud['classes']['A']['remaining'] == 6 and bud['classes']['A']['remaining_status'] == 'NOT_AUTHORIZED')
chk('budget_class_bc', bud['classes']['B']['used_total'] == 0 and bud['classes']['C']['used_total'] == 0)
chk('budget_totals', bud['totals']['starts'] == 14 and abs(bud['totals']['wall_seconds_sum'] - 50.246) < 0.002, bud['totals'])
cors = json.load(open(RUN_DIR + '/evidence/batch2_corrections.json', encoding='utf-8'))
chk('corrections_ids', [c['id'] for c in cors['corrections']][:4] == ['A5B2R-01', 'A5B2R-02', 'A5B2R-03', 'A5B2R-04'])
vsp = json.load(open(RUN_DIR + '/vspaero_diagnostics.json', encoding='utf-8'))
chk('vsp_zero_solver', vsp['zero_solver_setup_generation']['a0v2_solver_processes_started'] == 0)
chk('vsp_gate3', 'CANNOT_REACH_PHYSICAL_VALIDATION' in vsp['gate_notes']['gate3'])
drg = json.load(open(RUN_DIR + '/drag_component_ledger.json', encoding='utf-8'))
chk('drag_no_wave', drg['components']['wave_drag']['available'] is False and drg['components']['body_correction']['available'] is False)

result = {'checks': len(checks), 'failed': [c for c in checks if not c['ok']], 'passed': sum(1 for c in checks if c['ok'])}
print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if not result['failed'] else 1)