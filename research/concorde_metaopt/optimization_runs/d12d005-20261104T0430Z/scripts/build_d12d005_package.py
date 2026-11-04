#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Build D-12D-005 run deliverables from archived evidence.

Zero solver starts. Read-only on evidence; writes only run-dir deliverables,
docs report/figures and evidence provenance copies.
"""

import csv
import hashlib
import json
import math
import os
import shutil
import sys

RUN_ID = 'd12d005-20261104T0430Z'
REPO = 'D:/RCAIDE-d12d005'
RUN_REL = 'research/concorde_metaopt/optimization_runs/' + RUN_ID
RUN_DIR = REPO + '/' + RUN_REL
EXT = 'C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state'
EXT_D12 = EXT + '/d12d005'
EXT_FIG = EXT_D12 + '/a2/batch2_figures'
DOCS = REPO + '/docs/reviews'
FIG_DEST_REL = 'docs/reviews/figures/d12d005_batch2'
FIG_DEST = REPO + '/' + FIG_DEST_REL
REPORT_REL = 'docs/reviews/d12d005_batch2_report_20261104.md'
REPORT_DEST = REPO + '/' + REPORT_REL
A2_REL = RUN_REL + '/evidence/a2_batch2_figures'
A2_DEST = RUN_DIR + '/evidence/a2_batch2_figures'
BT = chr(96)


def now_utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def bt(s):
    return s.replace('@BT@', BT)


def die(msg):
    sys.stderr.write('BUILD_ERROR: ' + msg + chr(10))
    sys.exit(2)


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(read_bytes(path))


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def rows_jsonl(path):
    out = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def is_finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def clean(v):
    if isinstance(v, float):
        if math.isnan(v):
            return 'NaN'
        if math.isinf(v):
            return 'Infinity' if v > 0 else '-Infinity'
        return v
    if isinstance(v, dict):
        return dict((k, clean(x)) for k, x in v.items())
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    return v


def write_text(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def write_json(name, obj):
    write_text(RUN_DIR + '/' + name, json.dumps(clean(obj), ensure_ascii=False, indent=2, sort_keys=False) + chr(10))


def write_json_abs(path, obj):
    write_text(path, json.dumps(clean(obj), ensure_ascii=False, indent=2, sort_keys=False) + chr(10))


def eol_of(data):
    if bytes([13, 10]) in data:
        return 'crlf'
    if bytes([10]) in data:
        return 'lf'
    return 'none'


def is_text_bytes(data):
    if bytes([0]) in data:
        return False
    try:
        data.decode('utf-8')
        return True
    except UnicodeDecodeError:
        return False


def canonical_lf(data):
    return data.replace(bytes([13, 10]), bytes([10]))


def file_record(path, rel=None, outside_git=False, kind=None):
    data = read_bytes(path)
    text = is_text_bytes(data)
    rec = {
        'path': rel if rel is not None else path,
        'bytes': len(data),
        'sha256_raw': sha_bytes(data),
        'is_text': text,
        'eol': eol_of(data),
        'outside_git': bool(outside_git),
    }
    if text:
        rec['sha256_canonical_lf'] = sha_bytes(canonical_lf(data))
    if kind:
        rec['kind'] = kind
    return rec


def repo_rel(path):
    if path.startswith(RUN_DIR + '/'):
        return path[len(RUN_DIR) + 1:]
    if path.startswith(REPO + '/'):
        return path[len(REPO) + 1:]
    return path


def ensure(path):
    if not os.path.exists(path):
        die('missing required path: ' + path)
    return path


def coeff_subset(coeffs):
    keys = ['CLo', 'CLi', 'CLtot', 'CDo', 'CDi', 'CDtot', 'CLwtot', 'CDwtot', 'CLiw', 'CDiw', 'E', 'Ew', 'CMxtot', 'CMytot', 'CMztot']
    out = {}
    for k in keys:
        if k in (coeffs or {}):
            out[k] = coeffs[k]
    return out


def primary3(coeffs):
    return {
        'CLtot': (coeffs or {}).get('CLtot'),
        'CDi': (coeffs or {}).get('CDi'),
        'CDtot': (coeffs or {}).get('CDtot'),
    }


def verify_status(case, key):
    v = case.get(key)
    if isinstance(v, dict):
        return v.get('status')
    if isinstance(v, str):
        return v
    return None


def list_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != '__pycache__')
        for name in sorted(filenames):
            if name.endswith('.pyc'):
                continue
            out.append(os.path.join(dirpath, name))
    return out


print('stage: load evidence')
V1 = load_json(ensure(RUN_DIR + '/evidence/v1/batch1_results.json'))
V1_LED = rows_jsonl(ensure(RUN_DIR + '/evidence/v1/ledger.jsonl'))
V1_RUN = load_json(ensure(RUN_DIR + '/evidence/v1/run_start.json'))
V1B = load_json(ensure(RUN_DIR + '/evidence/v1b/results_summary.json'))
V1B_LED = rows_jsonl(ensure(RUN_DIR + '/evidence/v1b/ledger.jsonl'))
B2 = load_json(ensure(RUN_DIR + '/evidence/batch2/batch2_results.json'))
V1_STOP = (V1.get('stop') or {})
V1_STOP_TRIGGER = (V1_STOP.get('trigger') or {})


def _sect_tess_scalar(a0v2_case):
    mr = a0v2_case.get('model_readback') or {}
    vals = mr.get('sect_tess_u_readback') or (mr.get('readback') or {}).get('sect_tess_u') or mr.get('SectTess_U')
    if isinstance(vals, (list, tuple)) and vals:
        return max(vals)
    return vals

B2_LED = rows_jsonl(ensure(RUN_DIR + '/evidence/batch2/ledger.jsonl'))
B2_STATE = load_json(ensure(RUN_DIR + '/evidence/batch2/batch_state.json'))
B2_BUDGET = load_json(ensure(RUN_DIR + '/evidence/batch2/budget_ledger.json'))
B2_CHECKS = load_json(ensure(RUN_DIR + '/evidence/batch2/final_checks.json'))
B2_RUN = load_json(ensure(RUN_DIR + '/evidence/batch2/run_start.json'))
A0 = load_json(ensure(RUN_DIR + '/evidence/a0/setup_generation.json'))
A0V2 = load_json(ensure(RUN_DIR + '/evidence/a0v2/setup_generation_v2.json'))
GATE2 = load_json(ensure(RUN_DIR + '/evidence/a0v2/gate2_repair_registration.json'))
A0_CASES = dict((c['case_id'], c) for c in A0['cases'])
A0V2_CASES = dict((c['case_id'], c) for c in A0V2['cases'])
V1_CONTRACTS = {}
for cid in ['S0_STD_M0p1_base', 'S1_STD_M0p1_wn128', 'S2_STD_M0p1_wi0', 'S3_STD_M2p02_base', 'S4_STD_M2p02_wn128', 'S5_D12_M2p02_base']:
    p = RUN_DIR + '/evidence/a0/setup_gen/' + cid + '/expected.json'
    V1_CONTRACTS[cid] = load_json(ensure(p))['contract']

def led_by_event(rows):
    out = {}
    for r in rows:
        if r.get('record_type') == 'COMPLETED':
            out[r['event_id']] = r
    return out


V1_LED_C = led_by_event(V1_LED)
V1B_LED_C = led_by_event(V1B_LED)
B2_LED_C = led_by_event(B2_LED)
if len(V1_LED_C) != 4:
    die('expected 4 completed v1 events, got ' + str(len(V1_LED_C)))
if len(V1B_LED_C) != 2:
    die('expected 2 completed v1b events, got ' + str(len(V1B_LED_C)))
if len(B2_LED_C) != 8:
    die('expected 8 completed batch2 events, got ' + str(len(B2_LED_C)))

VSPAERO_EXE = B2['run']['exe']
VSPAERO_SHA = B2['run']['exe_sha256']
RUNNER_VERSION = B2['run']['runner_version']
RUNNER_SHA = B2['run']['runner_sha256']
HEAD = B2['run']['git_head']

def ext_vspgeom_for_a0(cid):
    eb = A0_CASES[cid]['execution_bundle']
    return eb['vspgeom_external_path'], eb['vspgeom_sha256'], eb['vspgeom_bytes']


def ext_vspgeom_for_a0v2(cid):
    eb = A0V2_CASES[cid]['execution_bundle']
    return eb['vspgeom_external_path'], eb['vspgeom_sha256'], eb['vspgeom_bytes']


def basename_from_command(cmd):
    parts = str(cmd).replace(chr(92), '/').split('/')
    last = parts[-1]
    return last + '.vspgeom'


def build_evaluations():
    ev = []
    # batch 1
    for case in V1['cases']:
        if not case.get('billable'):
            continue
        cid = case['case_id']
        contract = V1_CONTRACTS[cid]
        row = V1_LED_C[case['event_id']]
        derived = []
        if case.get('verify_polar_returncode') == 2 or not is_finite((case.get('coefficients') or {}).get('Ew')):
            derived.append({'column': 'Ew', 'value': 'Infinity', 'classification': 'DERIVED_RATIO_NONFINITE_ALLOWED'})
        ext_path, ext_sha, ext_bytes = ext_vspgeom_for_a0(cid)
        assert ext_sha == row['vspgeom_sha256'], cid
        rec = {
            'event_id': case['event_id'],
            'case_id': cid,
            'short_id': case.get('short_id'),
            'batch': 'D-12D-005-A-batch-1',
            'batch_label': 'batch1',
            'class': 'A',
            'kind': 'std',
            'mach': case['mach'],
            'aoa_deg': contract['AoA'],
            'sref_m2': contract['Sref'],
            'cref_m': contract['Cref'],
            'bref_m': contract['Bref'],
            'x_cg_m': contract['X_cg'],
            'num_wake_nodes': contract['NumWakeNodes'],
            'wake_iters': contract['WakeIters'],
            'vspaero_version': '7.2.2',
            'solver_exe_sha256': VSPAERO_SHA,
            'setup_sha256': row['setup_sha256'],
            'vspgeom_sha256': row['vspgeom_sha256'],
            'vspgeom_bytes': ext_bytes,
            'vspgeom_basename': basename_from_command(row['command']),
            'vspgeom_external_path': ext_path,
            'command': row['command'],
            'cwd': row['cwd'],
            'wall_seconds': case['wall_seconds'],
            'peak_rss_gb': case.get('peak_rss_gb'),
            'returncode': case['returncode'],
            'timed_out': bool(case.get('timed_out')),
            'outcome_class': case['outcome_class'],
            'billable': True,
            'stop_rule_hit': (V1_STOP_TRIGGER.get('rule') if V1_STOP_TRIGGER.get('case_id') == case['case_id'] else None),
            'coefficients': coeff_subset(case.get('coefficients')),
            'primary_values': primary3(case.get('coefficients')),
            'derived_column_warnings': derived,
            'verify': {
                'polar_status': ('FAIL_NONFINITE_DERIVED_COLUMN' if case.get('verify_polar_returncode') == 2 else 'PASS'),
                'polar_returncode': case.get('verify_polar_returncode'),
                'history_status': 'PASS' if case.get('verify_history_returncode') == 0 else 'UNKNOWN',
                'history_returncode': case.get('verify_history_returncode'),
            },
            'labels': ['VSPAERO_INTERNAL_ONLY', 'NOT_VALIDATED', 'physical_validation=NOT_VALIDATED'],
            'notes': (case.get('conclusion') or '')[:600],
        }
        ev.append(rec)
    # batch 1b
    for case in V1B['cases']:
        cid = case['case_id']
        contract = case['contract']
        row = V1B_LED_C[case['event_id']]
        kind = 'd12' if cid.startswith('S5') else 'std'
        ext_path, ext_sha, ext_bytes = ext_vspgeom_for_a0(cid)
        assert ext_sha == row['vspgeom_sha256'], cid
        ev.append({
            'event_id': case['event_id'],
            'case_id': cid,
            'short_id': case.get('short_id'),
            'batch': 'D-12D-005-A-batch-1b',
            'batch_label': 'batch1b',
            'class': 'A',
            'kind': kind,
            'mach': contract['Mach'],
            'aoa_deg': contract['AoA'],
            'sref_m2': contract['Sref'],
            'cref_m': contract['Cref'],
            'bref_m': contract['Bref'],
            'x_cg_m': contract['X_cg'],
            'num_wake_nodes': contract['NumWakeNodes'],
            'wake_iters': contract['WakeIters'],
            'vspaero_version': '7.2.2',
            'solver_exe_sha256': VSPAERO_SHA,
            'setup_sha256': row['setup_sha256'],
            'vspgeom_sha256': row['vspgeom_sha256'],
            'vspgeom_bytes': ext_bytes,
            'vspgeom_basename': basename_from_command(case['command']),
            'vspgeom_external_path': ext_path,
            'command': case['command'],
            'cwd': case['cwd'],
            'wall_seconds': case['wall_seconds'],
            'peak_rss_gb': case.get('peak_rss_gb'),
            'returncode': case['returncode'],
            'timed_out': bool(case.get('timed_out')),
            'outcome_class': case['outcome_class'],
            'billable': True,
            'stop_rule_hit': case.get('stop_rule_hit'),
            'coefficients': coeff_subset(case.get('coefficients')),
            'primary_values': primary3(case.get('coefficients')),
            'derived_column_warnings': case.get('derived_column_warnings') or [],
            'verify': {
                'polar_status': verify_status(case, 'verify_polar'),
                'history_status': verify_status(case, 'verify_history'),
            },
            'labels': ['VSPAERO_INTERNAL_ONLY', 'NOT_VALIDATED', 'physical_validation=NOT_VALIDATED'],
            'notes': (case.get('notes') or '')[:600],
        })
    # batch 2
    for case in B2['cases']:
        cid = case['case_id']
        contract = case['contract']
        row = B2_LED_C[case['event_id']]
        pc09 = case.get('pc09') or {}
        ev.append({
            'event_id': case['event_id'],
            'case_id': cid,
            'short_id': cid,
            'batch': 'D-12D-005-A-batch-2',
            'batch_label': 'batch2',
            'class': 'A',
            'kind': case['kind'],
            'order': case.get('order'),
            'mach': contract['Mach'],
            'aoa_deg': contract['AoA'],
            'sref_m2': contract['Sref'],
            'cref_m': contract['Cref'],
            'bref_m': contract['Bref'],
            'x_cg_m': contract['X_cg'],
            'num_wake_nodes': contract['NumWakeNodes'],
            'wake_iters': contract['WakeIters'],
            'vspaero_version': '7.2.2',
            'solver_exe_sha256': VSPAERO_SHA,
            'setup_sha256': row.get('setup_sha256') or (A0V2_CASES[cid]['contract_setup']['sha256']),
            'vspgeom_sha256': row['vspgeom_sha256'],
            'vspgeom_bytes': row.get('vspgeom_bytes') or pc09.get('local_vspgeom_bytes'),
            'vspgeom_basename': pc09.get('local_vspgeom_basename') or row.get('vspgeom_basename'),
            'vspgeom_external_path': pc09.get('external_vspgeom_path'),
            'command': row['command'],
            'cwd': row['cwd'],
            'wall_seconds': case['wall_seconds'],
            'peak_rss_gb': case.get('peak_rss_gb'),
            'returncode': case['returncode'],
            'timed_out': bool(case.get('timed_out')),
            'outcome_class': case['outcome_class'],
            'billable': True,
            'stop_rule_hit': case.get('stop_rule_hit'),
            'coefficients': coeff_subset(case.get('all_coefficients') or row.get('coefficients')),
            'primary_values': case.get('primary_values') or primary3(row.get('coefficients')),
            'derived_column_warnings': case.get('derived_column_warnings') or [],
            'gate_result': case.get('gate_result'),
            'gate_failures': case.get('gate_failures') or [],
            'prestart_checks_all_pass': (case.get('prestart_checks') or {}).get('all_pass'),
            'verify': {
                'polar_status': case.get('verify_polar_status'),
                'polar_returncode': case.get('verify_polar_returncode'),
                'history_status': case.get('verify_history_status'),
                'history_returncode': case.get('verify_history_returncode'),
            },
            'labels': ['VSPAERO_INTERNAL_ONLY', 'NOT_VALIDATED', 'physical_validation=NOT_VALIDATED'],
            'notes': (case.get('outcome_class_reason') or '')[:600],
        })
    return ev


print('stage: evaluations')
EVAL = build_evaluations()
if len(EVAL) != 14:
    die('expected 14 billable evaluations, got ' + str(len(EVAL)))

REVIEW_REFS = {
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

print('stage: run_config')
RUN_CONFIG = {
    'schema': 'd12d005-run-config-1',
    'run_id': RUN_ID,
    'issue': 'https://github.com/QingYangJin/RCAIDE_Supersonic/issues/4',
    'authority_comment_id': 6622447995,
    'authority': 'D-12D-005',
    'status': 'A_LINE_CLOSED_VSPAERO_NOT_VALIDATED',
    'generated_utc': now_utc(),
    'repo': {'path': REPO, 'branch': 'research/d12d005-aero-fallback', 'head': HEAD, 'main_head': 'ec65e5a'},
    'run_dir': RUN_REL,
    'labels': B2['labels'],
    'solver': {
        'name': 'VSPAERO 7.2.2 (OpenVSP 3.55.0 thin lifting surface)',
        'exe': VSPAERO_EXE,
        'exe_sha256': VSPAERO_SHA,
        'runner_version': RUNNER_VERSION,
        'runner_sha256': RUNNER_SHA,
        'serial_only': True,
        'omp_threads': 4,
        'timeout_s_per_case': 900,
        'max_ram_gb': 16,
    },
    'frozen_contract': {
        'mach': 2.02,
        'altitude_m': 18288,
        'dynamic_pressure_pa': 20483.94,
        'temperature_k': 216.65,
        'pressure_pa': 7171.544888,
        'density_kg_m3': 0.1153178340089936,
        'velocity_m_s': 596.0373972278921,
        'reynolds': 89397005.8767656,
        'sref_m2': 358.25,
        'cref_m': 18.489893,
        'bref_m': 25.604638,
        'x_cg_m': 16.821978259514246,
        'num_wake_nodes': 8,
        'wake_iters': 5,
        'wake_relax': 1.0,
        'far_dist': -1.0,
        'symmetry': 0,
        'aoa_deg': 2.0,
    },
    'design_set': '12d_lifting_surfaces',
    'design_vector_12d': {'W01': 358.25, 'W02': 1.83, 'W03': 67.0, 'W04': 48.0, 'W05': 71.0, 'W06': 0.480469, 'W07': 0.945313, 'W08': 0.408284, 'W09': 0.130178, 'W10': 0.0, 'V01': 33.91, 'V02': 0.0},
    'fixed_fuselage': {'F01': 61.66, 'F02': 4.3, 'F03': 1.152778},
    'geometry_provenance': {
        'archived_model': A0V2.get('archived_model'),
        'archived_thin_vspgeom': A0V2.get('archived_thin_vspgeom'),
        'a0v2_readback_status': 'A0V2_SETUP_READY_NO_SOLVER',
        'a0v2_generated_cases': sorted(A0V2_CASES.keys()),
        'a0v2_status': A0V2.get('status'),
        'a0v2_solver_starts': A0V2.get('solver_starts'),
    },
    'batch_authorizations': {
        'batch1': {'source': 'evidence/v1/run_start.json', 'batch': 'A-batch-1 (S0..S5)', 'authorized_utc': '2026-11-04T07:05:00Z', 'authorized_by': 'lead', 'cap_starts': 6},
        'batch1b': {'source': 'evidence/lead/batch1b_reauthorization.md', 'authorized_by': 'lead', 'cap_starts': 2, 'starts': 2},
        'batch2': {'source': 'EXT/d12d005/lead/D12D005_BATCH2_AUTHORIZATION_20261104T130635Z.json', 'authorization_id': 'D12D005-BATCH2-20261104T130635Z', 'authorized_utc': (B2['authorization'].get('issued') or B2['authorization'].get('issued_utc')), 'authorized_by': 'lead', 'cap_starts': 8, 'retries': 0},
    },
    'review_refs': REVIEW_REFS,
    'environment': {
        'platform': 'Windows (host)',
        'python_version': sys.version.split()[0],
        'worktree': REPO,
        'run_dir': RUN_REL,
        'openvsp_root': 'D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64',
        'vspaero_exe': VSPAERO_EXE,
        'vspaero_version': '7.2.2',
        'vspaero_exe_sha256': VSPAERO_SHA,
    },
    'deliverables_expected': ['run_config.json', 'approval_and_budget_ledger.json', 'evaluations.jsonl', 'solver_case_matrix.csv', 'vspaero_diagnostics.json', 'rcaide_fallback_results.json', 'su2_crosscheck.json', 'drag_component_ledger.json', 'summary.json', 'data_manifest.json', 'evidence/batch2_corrections.json'],
    'data_manifest_convention': {
        'hash_modes': ['sha256_raw', 'sha256_canonical_lf'],
        'canonical_lf': 'sha256 over bytes after replacing every CRLF with LF',
        'note': 'repo .gitattributes normalizes text to LF on commit; worktree may hold raw CRLF; both hashes are recorded; filters are not used.',
    },
    'physical_call_accounting': {'solver_starts_this_round': 14, 'class_A_used': 14, 'class_A_cap': 20, 'class_A_remaining_not_authorized': 6, 'class_B_used': 0, 'class_C_used': 0, 'class_D_E_P4_used': 0},
}
write_json('run_config.json', RUN_CONFIG)

print('stage: budget ledger')
v1_budget = V1['budget']
v1b_budget = V1B.get('budget') or {}
batch2_budget = B2_BUDGET
BUDGET = {
    'schema': 'd12d005-budget-ledger-1',
    'run_id': RUN_ID,
    'generated_utc': now_utc(),
    'classes': {
        'A': {'category': 'VSPAERO 7.2.2 thin-LF', 'cap_starts': 20, 'used_total': 14, 'remaining': 6, 'remaining_status': 'NOT_AUTHORIZED', 'carry_over': False},
        'B': {'category': 'RCAIDE VLM empirical low-fidelity fallback', 'cap_starts': 12, 'used_total': 0, 'remaining': 12, 'status': 'LOCKED_NOT_AUTHORIZED', 'trigger_required': 'FALLBACK_TRIGGERED (not triggered)'},
        'C': {'category': 'SU2 Euler cross-check', 'cap_starts': 4, 'used_total': 0, 'remaining': 4, 'status': 'LOCKED_NOT_AUTHORIZED'},
        'D': {'category': 'batch real DOE/BO/DE (Concorde)', 'cap_starts': 0, 'used_total': 0, 'status': 'NOT_AUTHORIZED'},
        'E': {'category': 'real aviation MAML training', 'cap_starts': 0, 'used_total': 0, 'status': 'NOT_AUTHORIZED'},
        'P4': {'category': 'high-fidelity batch (SU2/Mission)', 'cap_starts': 0, 'used_total': 0, 'status': 'NOT_AUTHORIZED'},
    },
    'batches': [
        {'batch': 'batch1', 'batch_id': V1.get('batch_id'), 'authorized_starts': 6, 'starts_used': 4, 'retries': 0, 'remaining_disposition': 'CLOSED_NOT_CARRIED_OVER_NOT_REALLOCATED', 'billable_events': 4, 'non_billable_events': ['NA-D12D005-004-AMEND'], 'ledger_rows': len(V1_LED), 'ledger_sha256_raw': sha_file(RUN_DIR + '/evidence/v1/ledger.jsonl'), 'events': ['NA-D12D005-001', 'NA-D12D005-002', 'NA-D12D005-003', 'NA-D12D005-004'], 'notes': 'S3 计费但判 FAILED_INVALID_POLAR（Ew 派生列）；S4/S5 未运行（NOT_RUN_AFTER_ABORT），由 batch1b 授权补跑而非重试。'},
        {'batch': 'batch1b', 'batch_id': V1B.get('batch_id'), 'authorized_starts': 2, 'starts_used': 2, 'retries': 0, 'billable_events': 2, 'ledger_rows': len(V1B_LED), 'ledger_sha256_raw': sha_file(RUN_DIR + '/evidence/v1b/ledger.jsonl'), 'events': ['NA-D12D005B-001', 'NA-D12D005B-002']},
        {'batch': 'batch2', 'batch_id': B2.get('batch_id'), 'authorization_id': 'D12D005-BATCH2-20261104T130635Z', 'authorized_starts': 8, 'starts_used': 8, 'retries': 0, 'billable_events': 8, 'ledger_rows': len(B2_LED), 'ledger_sha256_raw': sha_file(RUN_DIR + '/evidence/batch2/ledger.jsonl'), 'events': sorted(B2_LED_C.keys()), 'stopped': B2_STATE.get('stopped')},
    ],
    'totals': {
        'starts': 14,
        'retries': 0,
        'billable_events': 14,
        'solver_invocations': 14,
        'wall_seconds_sum': round(sum(e['wall_seconds'] for e in EVAL), 3),
        'peaks': {'max_wall_seconds_single': max(e['wall_seconds'] for e in EVAL), 'max_rss_gb': max([e.get('peak_rss_gb') or 0 for e in EVAL] + [0])},
    },
    'class_A_remaining_6': {'status': 'NOT_AUTHORIZED', 'carry_over': False, 'release_condition': 'new Lead written authorization after A5+Lead review of new hypothesis and evidence (not requested this round).'},
    'sources': [{'path': 'evidence/batch2/budget_ledger.json', 'sha256_raw': sha_file(RUN_DIR + '/evidence/batch2/budget_ledger.json')}],
}
write_json('approval_and_budget_ledger.json', BUDGET)



print('stage: evaluations.jsonl')
write_text(RUN_DIR + '/evaluations.jsonl', chr(10).join(json.dumps(clean(r), ensure_ascii=False, sort_keys=True) for r in EVAL) + chr(10))

print('stage: solver_case_matrix.csv')
cols = ['case_id', 'event_id', 'order', 'batch', 'class', 'kind', 'mach', 'aoa_deg', 'sref_m2', 'cref_m', 'bref_m', 'num_wake_nodes', 'wake_iters', 'CLtot', 'CDi', 'CDtot', 'wall_seconds', 'returncode', 'outcome_class', 'gate_result', 'stop_rule_hit', 'setup_sha256', 'vspgeom_sha256', 'vspgeom_bytes', 'vspgeom_basename', 'verify_polar_status', 'verify_history_status', 'label', 'physical_validation']
with open(RUN_DIR + '/solver_case_matrix.csv', 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f, lineterminator=chr(10))
    w.writerow(cols)
    for i, e in enumerate(EVAL):
        pv = e.get('primary_values') or {}
        v = e.get('verify') or {}
        w.writerow([e['case_id'], e['event_id'], e.get('order', ''), e['batch'], e['class'], e['kind'], e['mach'], e['aoa_deg'], e['sref_m2'], e['cref_m'], e['bref_m'], e['num_wake_nodes'], e['wake_iters'], pv.get('CLtot'), pv.get('CDi'), pv.get('CDtot'), e['wall_seconds'], e['returncode'], e['outcome_class'], e.get('gate_result') or '', e.get('stop_rule_hit') or '', e['setup_sha256'], e['vspgeom_sha256'], e['vspgeom_bytes'], e['vspgeom_basename'], v.get('polar_status') or '', v.get('history_status') or '', 'VSPAERO_INTERNAL_ONLY', 'NOT_VALIDATED'])

print('stage: vspaero_diagnostics')
b1b_cases = dict((c['case_id'], c) for c in V1B['cases'])
b2_cases = dict((c['case_id'], c) for c in B2['cases'])
b2_contracts = dict((c['case_id'], c['contract']) for c in B2['cases'])
VSP = {
    'schema': 'd12d005-vspaero-diagnostics-1',
    'run_id': RUN_ID,
    'generated_utc': now_utc(),
    'labels': {'result_label': 'VSPAERO_INTERNAL_ONLY', 'physical_validation': 'NOT_VALIDATED', 'physical_validation_claim': False},
    'solver': {'version': '7.2.2', 'openvsp': '3.55.0', 'exe': VSPAERO_EXE, 'exe_sha256': VSPAERO_SHA},
    'zero_solver_setup_generation': {
        'a0_cases': sorted(A0_CASES.keys()),
        'a0_status': A0.get('status'),
        'a0_solver_processes_started': A0.get('solver_processes_started'),
        'a0_readback_fields_per_case': 17,
        'a0v2_cases': sorted(A0V2_CASES.keys()),
        'a0v2_status': A0V2.get('status'),
        'a0v2_solver_processes_started': A0V2.get('solver_processes_started'),
        'a0v2_readback_fields_per_case': 17,
        'a0v2_sect_tess_u': dict((cid, _sect_tess_scalar(A0V2_CASES[cid])) for cid in sorted(A0V2_CASES)),
        'a0v2_sect_tess_u_note': 'read back from OpenVSP model per section (max of sections); B2-01/02/03 = 3/6/12, B2-04..B2-07 = 12, S6 = 20',
    },
    'contract_readback': {
        'fields_expected': 17,
        'batch1b_contract_asserts_all_ok': [b1b_cases['S4_STD_M2p02_wn128'].get('contract_asserts_all_ok'), b1b_cases['S5_D12_M2p02_base'].get('contract_asserts_all_ok')],
        'batch2_readback_17_ok_all': all(bool((c.get('prestart_checks') or {}).get('readback_17_ok')) for c in B2['cases']),
        'batch2_prestart_all_pass': all(bool((c.get('prestart_checks') or {}).get('all_pass')) for c in B2['cases']),
        'contract_12d': {'Sref': 358.25, 'Cref': 18.489893, 'Bref': 25.604638, 'X_cg': 16.821978259514246, 'Mach': 2.02, 'AoA': 2.0, 'ReCref': 89397005.8767656, 'Vinf': 596.0373972278921, 'Rho': 0.1153178340089936, 'NumWakeNodes': 8, 'WakeIters': 5, 'WakeRelax': 1.0, 'FarDist': -1.0, 'Symmetry': 0},
        'contract_std_S6': b2_contracts['S6_STD_M2p02_aoa1'],
        'note': 'S6 使用独立标准矩形翼与 AoA=1；其 ReCref 按 Sref=4/Cref=1 计算，与 12D 案不同。',
    },
    'polar_parser': {
        'ld_002': 'VSPAERO 7.2.2 48-column polar header parsed (header row index 2); parser v2 in scripts/verify_polar_policy_v2.py.',
        'ld_001': 'contract setup format requires "key = value"; bare-key writes broke VSPAERO parsing in d12d004 and were fixed.',
        'derived_column_allowlist': ['Ew'],
        'derived_column_policy': 'Only Ew may be non-finite; PASS_WITH_WARNINGS. Any other column non-finite is a failure.',
        'primary_columns_checked': ['CLo', 'CLi', 'CLtot', 'CDo', 'CDi', 'CDtot', 'CMxtot', 'CMytot', 'CMztot'],
    },
    'batch1_stop_decision': V1_STOP,
    'batch1b_wake_sensitivity': {
        'comparison': 'S4 (NumWakeNodes=128) vs S3 (NumWakeNodes=8), same std wing, Mach 2.02, AoA 2',
        'delta_s4_vs_s3': V1B.get('deltas_s4_vs_s3_single_factor_wake_nodes'),
        's5_vs_s4_cross_geometry': V1B.get('s5_vs_s4_cross_geometry'),
        'conclusion': 'wake-node change is below 1e-7 in primary coefficients at Mach 2.02; not a physical validation.',
    },
    'batch2_sensitivity': {
        'density': {'sect_tess_u': {'B2-01': 3, 'B2-02': 6, 'B2-03': 12}, 'deltas': B2.get('deltas', {})},
        'perturbations': {'B2-04': 'W01 wing area 358.25 -> 376.1625 (fixed Sref=358.25 normalization)', 'B2-05': 'W03 quarter-chord sweep 67 -> 69 deg', 'B2-06': 'W10 tip twist 0 -> 2 deg'},
        'repeat': {'B2-07_vs_B2-03': B2.get('deltas', {}).get('B2-07_vs_B2-03') if isinstance(B2.get('deltas'), dict) else None},
    },
    'derived_column_artifact': {
        'column': 'Ew',
        'observed': 'Infinity in 8/8 batch2 and 2/2 batch1b cases',
        'mechanism': 'CDiw = 0 and CLiw = 0 in thin isolated-wing polar; Ew = CLtot^2 / (pi * AR * CDiw) divides by zero. Derived 0/0 artifact, not solver divergence.',
        'correction_source': 'A5 task-138 finding A5B2R-01 (report corrected); original evidence not rewritten.',
    },
    'corrections_latest': [
        {'id': 'A5B2R-01', 'status': 'CORRECTED_IN_DOCS_AND_DIAGNOSTICS', 'summary': 'Ew mechanism rewritten as CDiw=0 derived-ratio artifact.'},
        {'id': 'A5B2R-02', 'status': 'DISCLOSED', 'summary': 'cases[*].history_iterations null in results JSON; raw history has 5 rows per case, verified by verify-history.'},
        {'id': 'A5B2R-03', 'status': 'DISCLOSED', 'summary': 'last_solver_finish_utc and per-case stdout_sha256 null in snapshot; solver stdout archived at cases/<case>/results/solver_stdout.log.'},
        {'id': 'A5B2R-04', 'status': 'CORRECTED_IN_DOCS', 'summary': 'B2-04 delta labeled as fixed-Sref normalization, not pure aerodynamic sensitivity.'},
        {'id': 'B1B-m03', 'status': 'INFORMATIONAL_WITHDRAWN', 'summary': 'S4 budget snapshot 1/5 in immutable raw evidence is as-of-completion; corrections JSON defines final 2/6; not a new defect.'},
    ],
    'gate_notes': {
        'gate1': 'PASS_INTERNAL_ONLY',
        'gate2': {'a5_label': 'DIAGNOSTIC_REPAIR_CONFIRMED_BY_S6', 'registration': 'REGISTERED_POST_HOC_DIAGNOSTIC', 's3_s4_band': [0.06, 0.09], 's6_band': [0.03, 0.045], 's6_observed_CLtot': 0.037164223, 's6_band_pass': True},
        'gate3': 'CANNOT_REACH_PHYSICAL_VALIDATION (thin-surface VLM has no thickness, viscosity or shock capturing)',
        'lf_m2_02': 'NOT_VALIDATED',
        'fallback': 'NOT_TRIGGERED',
    },
}
write_json('vspaero_diagnostics.json', VSP)

print('stage: rcaide_fallback_results')
MISSION_E2E_CANDIDATES = [
    'D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z/mission_e2e.json',
    RUN_DIR + '/../../p1p3-fullchain-20261031T0407Z/mission_e2e.json',
]
context_ref = None
for cand in MISSION_E2E_CANDIDATES:
    cand = os.path.normpath(cand)
    if os.path.exists(cand):
        m = load_json(cand)
        context_ref = {'path': repo_rel(os.path.abspath(cand)), 'sha256_raw': sha_file(cand), 'bytes': os.path.getsize(cand), 'objective_fuel_burn_kg': m.get('objective_fuel_burn_kg'), 'note': 'archived previous-round run (p1p3 fullchain); not part of this d12d005 round; context only.'}
        break
RCAIDE = {
    'schema': 'd12d005-rcaide-fallback-results-1',
    'run_id': RUN_ID,
    'generated_utc': now_utc(),
    'status': 'NOT_EXECUTED',
    'fallback_triggered': False,
    'fallback_status': 'NOT_TRIGGERED',
    'evaluator': {'evaluator_id': 'RCAIDE_VLM_EMPIRICAL_LF_M202', 'implemented_in_repo': False, 'physics_validation_status': 'NOT_APPLICABLE'},
    'reason': 'A-line (VSPAERO thin-LF) closed at 14/20 with internal-only evidence; A5 task-125/138 verdicts: FALLBACK_NOT_TRIGGERED; B class stays LOCKED 0/12; the mandatory RCAIDE_VLM_EMPIRICAL_LF_M202 evaluator is not implemented in the repo, so no fallback run can be produced without a new authorization and evaluator work.',
    'budget': {'cap_starts': 12, 'used': 0, 'remaining': 12, 'status': 'LOCKED_NOT_AUTHORIZED'},
    'baseline_reference_context_only': context_ref,
    'unimplemented_requirements': [
        'evaluator RCAIDE_VLM_EMPIRICAL_LF_M202 (single-cruise VLM + empirical parasite/compressible drag) is not implemented.',
        'RCAIDE-LEADS 1.5.0 SingleCruiseBackend integration for this evaluator not wired.',
        'FALLBACK_TRIGGERED condition never reached (A line stopped on evidence review, not on two failed repair hypotheses).',
    ],
    'prohibitions': ['Not used for real Concorde meta-learning training', 'Not used for formal BO/DE', 'No fuel-burn claim for this round', 'No body correction injection'],
}
write_json('rcaide_fallback_results.json', RCAIDE)

print('stage: su2_crosscheck')
SU2 = {
    'schema': 'd12d005-su2-crosscheck-1',
    'run_id': RUN_ID,
    'generated_utc': now_utc(),
    'status': 'NOT_EXECUTED',
    'class_C_budget': {'cap_starts': 4, 'used': 0, 'remaining': 4, 'status': 'LOCKED_NOT_AUTHORIZED'},
    'reason': 'D-12D-005 C class remains locked; no Lead authorization issued; A-line closed without fallback, so no Euler cross-check was requested.',
    'prior_round_reference': {'source': 'D-12D-002 SU2 wedge HFS-00..HFS-04 (archived run p1p3-fullchain-20261031T0407Z)', 'note': 'Different geometry and round; not comparable; recorded only as historical capability context, not as this round result.'},
    'prohibitions': ['No SU2 result is claimed in this round', 'No Euler drag/heat-flux validation claim'],
}
write_json('su2_crosscheck.json', SU2)

print('stage: drag_component_ledger')
b2_cltot = dict((c['case_id'], c) for c in B2['cases'])
bol = V1B['cases'][0]['coefficients'] if V1B['cases'][0].get('coefficients') else {}
DRAG = {
    'schema': 'd12d005-drag-component-ledger-1',
    'run_id': RUN_ID,
    'generated_utc': now_utc(),
    'drag_component_source': 'VSPAERO 7.2.2 internal thin-surface coefficients (CDo, CDi, CDtot)',
    'derived_efficiency_column': {'Ew_available': False, 'mechanism': 'CDiw = 0 -> Ew = inf (derived 0/0 artifact)'},
    'physical_status': {'label': 'VSPAERO_INTERNAL_ONLY', 'physical_validation': 'NOT_VALIDATED', 'CDtot_is_physical_drag': False, 'usable_as_objective': False, 'usable_for_body_correction': False},
    'components': {
        'parasite_internal_CDo': {'available': True, 'note': 'VSPAERO internal parasite term, scales with Re; not a skin-friction model.'},
        'induced_CDi': {'available': True, 'note': 'thin-surface induced drag; not validated against physics.'},
        'total_CDtot': {'available': True, 'note': 'sum of internal terms; must not be used as real drag.'},
        'wave_drag': {'available': False, 'value': None, 'note': 'OpenVSP WaveDrag / area rule is NOT_VALIDATED and not injected.'},
        'compressibility_correction': {'available': False, 'value': None, 'note': 'not applied (not authorized; body correction BLOCKED).'},
        'body_correction': {'available': False, 'value': None, 'note': 'BODY-CORR stays BLOCKED; no delta-Donq was added.'},
    },
    'per_case_internal_coefficients': dict((e['case_id'], {'CLtot': (e.get('primary_values') or {}).get('CLtot'), 'CDi': (e.get('primary_values') or {}).get('CDi'), 'CDtot': (e.get('primary_values') or {}).get('CDtot'), 'class': e['batch_label'], 'label': 'VSPAERO_INTERNAL_ONLY'}) for e in EVAL),
    'deduplication_note': 'Only the single knock-down internal CDtot per case is recorded here; no cross-method addition is performed; wave-drag and body-correction deltas are null.',
    'archived_baseline_context': {'rcaide_lf_archived_fuel_burn_kg': 34109.48257123768, 'source': 'p1p3-fullchain-20261031T0407Z (previous round)', 'role': 'context only, not this round result'},
}
write_json('drag_component_ledger.json', DRAG)

print('stage: corrections')
CORR = {
    'schema': 'd12d005-batch2-corrections-1',
    'run_id': RUN_ID,
    'generated_utc': now_utc(),
    'applies_to': 'evidence/batch2 (immutable raw evidence, not rewritten)',
    'corrections': [
        {'id': 'A5B2R-01', 'field': 'Ew mechanism wording', 'old_statement': 'CLwtot near zero and CDwtot nonzero cause overflow', 'corrected_statement': 'CDiw = 0 (and CLiw = 0) makes Ew = CLtot^2/(pi*AR*CDiw) a 0/0-derived infinity; derived-column artifact, not divergence.', 'evidence': 'batch2 polar columns CLiw=0.0, CDiw=0.0 for 8/8 cases'},
        {'id': 'A5B2R-02', 'field': 'history_iterations', 'old_value': None, 'corrected_value': 5, 'note': 'Raw results JSON snapshot field not backfilled; each case history has 5 wake iterations and verify-history PASS. Raw evidence not rewritten.'},
        {'id': 'A5B2R-03', 'field': 'last_solver_finish_utc / stdout_sha256', 'old_value': None, 'note': 'Snapshot fields not backfilled; solver stdout archived at cases/<case>/results/solver_stdout.log; first/last finish derivable from ledger.'},
        {'id': 'A5B2R-04', 'field': 'B2-04 delta interpretation', 'old_statement': 'pure aerodynamic efficiency sensitivity', 'corrected_statement': 'fixed-Sref=358.25 normalization while design wing area = 376.1625 m2; delta includes reference-area effect.', 'evidence': 'batch2 plan B2-04 contract Sref=358.25'},
    ],
    'corrections_policy': 'Raw evidence is immutable; corrections are recorded here and in the final report, never by editing evidence files.',
}
write_json('evidence/batch2_corrections.json', CORR)
print('stage: figures copy')
FIG_FILES = ['fig1_budget_and_scope.png', 'fig2_case_coefficients.png', 'fig3_density_sensitivity.png', 'fig4_perturbation_delta.png', 'fig5_repeatability.png']
FIG_EXPECTED_BYTES = {'fig1_budget_and_scope.png': 209695, 'fig2_case_coefficients.png': 372259, 'fig3_density_sensitivity.png': 208607, 'fig4_perturbation_delta.png': 169150, 'fig5_repeatability.png': 215350}
if not os.path.isdir(FIG_DEST):
    os.makedirs(FIG_DEST)
fig_records = []
for name in FIG_FILES:
    src = EXT_FIG + '/figures/' + name
    ensure(src)
    dst = FIG_DEST + '/' + name
    shutil.copyfile(src, dst)
    b = os.path.getsize(dst)
    if b != FIG_EXPECTED_BYTES[name]:
        die('figure size mismatch for ' + name)
    fig_records.append({'name': name, 'repo_path': FIG_DEST_REL + '/' + name, 'source_path': 'EXT/d12d005/a2/batch2_figures/figures/' + name, 'bytes': b, 'sha256_raw': sha_file(dst), 'dpi': 300, 'font': 'Microsoft YaHei', 'language': 'zh-CN'})
if not os.path.isdir(A2_DEST):
    os.makedirs(A2_DEST)
a2_count = 0
for src in list_files(EXT_FIG):
    relp = os.path.relpath(src, EXT_FIG).replace(chr(92), '/')
    if relp.startswith('figures/'):
        continue
    dst = A2_DEST + '/' + relp
    d = os.path.dirname(dst)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    shutil.copyfile(src, dst)
    a2_count += 1
print('a2 provenance files copied:', a2_count)

print('stage: report')
draft = read_bytes(EXT_FIG + '/d12d005_batch2_report_20261104.md').decode('utf-8')
report_lines = draft.split(chr(10))


def find_line(prefix, start=0):
    for i in range(start, len(report_lines)):
        if report_lines[i].startswith(prefix):
            return i
    die('report anchor missing: ' + prefix)


i = find_line('> 状态：')
report_lines[i] = bt('> 状态：**FINAL（Lead 合并稿）**；A5 task-138 结论 APPROVE_BATCH2_RESULTS_AND_CLOSE_A_LINE（0 blocker / 0 major / 4 minor，已按 A5B2R-01..04 修正）；A3 task-139 审计 PASS（critical 40/40）；入库路径 @BT@docs/reviews/d12d005_batch2_report_20261104.md@BT@。')
i = find_line('> 生成：')
report_lines[i] = bt('> 生成：2026-11-04T14:13:12Z（A2）；Lead 合并：2026-11-04；证据根（仓库相对）：@BT@research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/batch2@BT@。外部审计状态根在本报告简记为 @BT@EXT@BT@（仓库外，不随仓库发布）。')
i = find_line('- 授权文件：')
report_lines[i] = bt('- 授权文件（仓库外）：@BT@EXT/d12d005/lead/D12D005_BATCH2_AUTHORIZATION_20261104T130635Z.json@BT@')
i = find_line('- A5 冻结计划：')
report_lines[i] = bt('- A5 冻结计划（仓库外）：@BT@EXT/d12d005/a5/batch2_prestart_gate/batch2_plan_frozen_candidate.json@BT@')
i = find_line('- 唯一警告：派生效率列')
report_lines[i] = bt('- 唯一警告：派生效率列 @BT@Ew=inf@BT@（8/8）。原因（A5 task-138 A5B2R-01 更正）：thin 孤立翼 polar 中 @BT@CDiw=0@BT@（且 @BT@CLiw=0@BT@），派生比值 Ew=CLtot²/(π·AR·CDiw) 的分母为 0 → inf；这是**派生列 0/0 伪影**，不是求解发散（主系数全部有限）。按授权派生列非有限仅记 WARNING，不触发停止。')
i = find_line('- history 由 verify-history 判定 PASS')
report_lines.insert(i + 1, bt('- 取证快照字段说明（A5B2R-02/03）：@BT@batch2_results.json@BT@ 的 @BT@cases[*].history_iterations@BT@ 与 @BT@run.run_start.last_solver_finish_utc@BT@、ledger @BT@stdout_sha256@BT@ 为 null 属快照字段未回填；原始 history 每案 5 行（verify-history PASS），每案 solver stdout 已归档于 @BT@cases/<case>/results/solver_stdout.log@BT@。原始证据不改写；详见 @BT@evidence/batch2_corrections.json@BT@。'))
i = find_line('观察：W01 面积 +5%')
report_lines[i] = report_lines[i] + bt('（A5B2R-04：W01 案设计翼面积=376.1625 m²，但合同参考面积固定 Sref=358.25 m² 未随动，故 Δ 含固定 Sref 归一化效应，不能读作纯气动效率敏感性。）')
i = find_line('| Gate2（诊断 / 可观测性门）')
report_lines[i] = bt('| Gate2（诊断 / 可观测性门） | **DIAGNOSTIC_REPAIR_CONFIRMED_BY_S6**（A5 task-138；登记属性仍为 POST_HOC_DIAGNOSTIC） | 事后诊断重注册：S3/S4 诊断带 [0.06,0.09]（观测 0.074251 在带内）；独立确认案 S6 预注册带 [0.03,0.045] PASS；密度三件套、单变量扰动、重复性差异均为内部可观测性记录；**不是事先注册的物理假设检验**，不产生物理通过/不通过结论。 |')
i = find_line('- B 类（')
if not report_lines[i + 1].startswith('- C 类（') or not report_lines[i + 2].startswith('- D（SU2）'):
    die('report B/C/D block layout unexpected')
report_lines[i:i + 3] = [
    bt('- B 类（RCAIDE VLM 经验低保真回退，evaluator @BT@RCAIDE_VLM_EMPIRICAL_LF_M202@BT@）：cap 12，**0 starts，LOCKED / NOT_AUTHORIZED**；仅在 A 线 FALLBACK_TRIGGERED、evaluator 实现并获新授权后才可启动（本轮未触发）。'),
    bt('- C 类（SU2 Euler 交叉检查）：cap 4，**0 starts，LOCKED / NOT_AUTHORIZED**。'),
    bt('- 其他（OpenVSP WaveDrag、批量真实 DOE/BO/DE、真实航空 MAML、P5/P6）：均 0 starts，未授权。'),
]
i = find_line('下一步：')
j = i + 1
k = j
while k < len(report_lines) and report_lines[k].startswith(('1.', '2.', '3.', '4.')):
    k += 1
if k - j != 4:
    die('report next-steps block unexpected')
report_lines[j:k] = [
    bt('1. A5 结果复核：task-138 = APPROVE_BATCH2_RESULTS_AND_CLOSE_A_LINE（0 blocker / 0 major / 4 minor，已按 A5B2R-01..04 修正）。'),
    bt('2. A3 隔离审计：task-139 = PASS（critical 40/40；证据 241 文件 / 7,788,381 B；审计时未提交、未推送）。'),
    bt('3. 入库：Lead 已将 @BT@evidence/batch2/@BT@、5 张中文图、本报告与 10 个交付 JSON 一并提交并推送（提交 sha 见 Issue #4 事实回执）。'),
    bt('4. 若后续需要 LF-M2.02 的物理结论，必须走不同的物理验证方法（如 SU2 Euler / 实验）并申请新授权；不得复用本批内部系数作为物理证据。'),
]
i = find_line('### 9.4 图表文件位置说明')
report_lines[i] = '### 9.4 图表与复算产物位置（入库后）'
j = i + 1
if report_lines[j].strip() != '':
    die('report 9.4 layout unexpected')
report_lines[j + 1:j + 2] = [
    bt('- 5 张中文图（300 dpi、Microsoft YaHei）：@BT@docs/reviews/figures/d12d005_batch2/@BT@（fig1..fig5，文件名不变）。'),
    bt('- 图与复算产物清单、字节与 sha256 见 §9.3 及 @BT@figures_manifest.json@BT@ / @BT@SHA256SUMS.txt@BT@。'),
    bt('- 复算与出图溯源副本（草稿报告、脚本、JSON、manifest）：@BT@research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/a2_batch2_figures/@BT@。'),
    bt('- 入库后 @BT@data_manifest.json@BT@ 对 run 目录内全部文件逐文件记录 raw + canonical-LF 双哈希；本报告与 5 张图作为 @BT@external_artifacts@BT@ 条目记录 raw sha256（文本报告另记 canonical-LF 与 verified），a2 溯源副本目录逐文件记录 sha256/bytes。'),
]
i = find_line('_本报告为草稿')
report_lines[i] = '_本报告为 D-12D-005 Batch2 最终报告（Lead 合并稿）；全部数值可由 §9 证据文件与复算脚本复现；内部系数不得作为物理证据或验收依据。_'
text = chr(10).join(report_lines)
text = text.replace('](figures/', '](figures/d12d005_batch2/')
APPENDIX = [
    '',
    '## §10 复核与入库记录',
    '',
    '| 角色 | 任务 | 结论 |',
    '| --- | --- | --- |',
    '| A5 | task-120（A0 rev6/6a @0e62db3） | APPROVE_FOR_BATCH1B（0 blocker / 0 major / 3 minor） |',
    '| A5 | task-125（BATCH1B 复核 + Gate 判定） | CHANGES_REQUESTED（0 / 3 / 6）→ 后续由 A0v2 与 Batch2 处置 |',
    '| A5 | task-131（Batch2 零求解预启动 gate） | APPROVE_BATCH2_8（0 / 0 / 4 minor；erratum 澄清 S4/S5 已在 batch1b 执行） |',
    '| A5 | task-138（Batch2 结果复核） | APPROVE_BATCH2_RESULTS_AND_CLOSE_A_LINE（0 / 0 / 4 minor） |',
    '| A3 | task-121（A0 rev6/6a 隔离） | PASS（critical 72/72） |',
    '| A3 | task-134（Batch2 预启动隔离） | PASS（critical 31/31） |',
    '| A3 | task-139（Batch2 证据完整性） | PASS（critical 40/40，warning 2/10） |',
    '| Lead | Batch2 书面授权 | authorization_id D12D005-BATCH2-20261104T130635Z；sha256 @BT@fd02dd898c816ad702a49e408ca4f31ea193a806275b9ffe95aa9d28e8507ecc@BT@ |',
    '',
    '入库交付物（写在 run 目录 @BT@research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/@BT@）：@BT@run_config.json@BT@、@BT@approval_and_budget_ledger.json@BT@、@BT@evaluations.jsonl@BT@、@BT@solver_case_matrix.csv@BT@、@BT@vspaero_diagnostics.json@BT@、@BT@rcaide_fallback_results.json@BT@、@BT@su2_crosscheck.json@BT@、@BT@drag_component_ledger.json@BT@、@BT@summary.json@BT@、@BT@data_manifest.json@BT@；证据 @BT@evidence/batch2/@BT@（241 文件 / 7,788,381 B）、@BT@evidence/batch2_corrections.json@BT@、@BT@evidence/a2_batch2_figures/@BT@。',
    '',
    '> 物理口径：本轮 14 次 A 类启动全部为 VSPAERO thin-LF 内部计算；@BT@CDtot@BT@ 不是真实阻力，机身修正、面积律与 LF-M2.02 均未签核；六门禁状态不变（GEO-12D PARTIAL / LF-M2.02 NOT_VALIDATED / HF-M2.02 PARTIAL / BODY-CORR BLOCKED / MISSION-DATA PARTIAL / BUDGET 门控中）。',
]
text = text.rstrip() + chr(10) + chr(10).join(bt(x) for x in APPENDIX) + chr(10)
write_text(REPORT_DEST, text)
print('report written: bytes=', os.path.getsize(REPORT_DEST))
print('stage: results summary')
summary_files = ['run_config.json', 'approval_and_budget_ledger.json', 'evaluations.jsonl', 'solver_case_matrix.csv', 'vspaero_diagnostics.json', 'rcaide_fallback_results.json', 'su2_crosscheck.json', 'drag_component_ledger.json', 'evidence/batch2_corrections.json']
deliverables = []
for relp in summary_files:
    p = RUN_DIR + '/' + relp
    data = read_bytes(p)
    rec = {'path': relp, 'bytes': len(data), 'sha256_raw': sha_bytes(data)}
    if is_text_bytes(data):
        rec['sha256_canonical_lf'] = sha_bytes(canonical_lf(data))
    deliverables.append(rec)
for fr in fig_records:
    deliverables.append({'path': fr['repo_path'], 'bytes': fr['bytes'], 'sha256_raw': fr['sha256_raw'], 'kind': 'figure', 'language': 'zh-CN'})
deliverables.append(file_record(REPORT_DEST, rel=REPORT_REL, kind='report'))
SUMMARY = {
    'schema': 'd12d005-summary-1',
    'run_id': RUN_ID,
    'generated_utc': now_utc(),
    'status': 'A_LINE_CLOSED_VSPAERO_NOT_VALIDATED_BATCH2_EXECUTED_AND_REVIEWED',
    'round': 'D-12D-005',
    'authority': {'issue': '#4', 'approval_comment_id': 6622447995, 'issue_comment_url': 'https://github.com/QingYangJin/RCAIDE_Supersonic/issues/4#issuecomment-6622447995'},
    'repo': {'path': REPO, 'branch': 'research/d12d005-aero-fallback', 'head': HEAD, 'head_short': HEAD[:7], 'main_head': 'ec65e5a', 'merged_to_main': False, 'pushed': True, 'pushed_note': 'package commits up to cb45917 pushed to origin/research/d12d005-aero-fallback; the commit for this revision is recorded in the Issue #4 receipt', 'as_of_git_snapshot': HEAD + ' (execution HEAD snapshot at build time)'},
    'physical_accounting': {'solver_starts': 14, 'retries': 0, 'class_A_used': 14, 'class_A_cap': 20, 'class_A_remaining_not_authorized': 6, 'class_B_used': 0, 'class_C_used': 0, 'class_D_E_P4_used': 0, 'zero_solver_actions': ['A0 setup generation 6 cases', 'A0v2 setup generation 8 cases', 'Batch2 prestart gate', 'all evidence parsing and figure generation'], 'physical_validation_claim': False},
    'labels': {'result_label': 'VSPAERO_INTERNAL_ONLY', 'physical_validation': 'NOT_VALIDATED', 'cdtot_is_physical_drag': False, 'gate3_note': 'thin-surface VSPAERO at Mach 2.02 cannot reach physical validation'},
    'gate_status': {
        'GEO-12D': {'status': 'PARTIAL', 'note': 'geometry/reference quantities/thin-surface ready; not signed off' },
        'LF-M2.02': {'status': 'NOT_VALIDATED', 'note': 'A line closed at 14/20 internal-only; no physical validation'},
        'HF-M2.02': {'status': 'PARTIAL', 'note': 'SU2 capability from prior round only; C class 0/4 locked this round'},
        'BODY-CORR': {'status': 'BLOCKED', 'note': 'area rule NOT_VALIDATED; no body correction injected'},
        'MISSION-DATA': {'status': 'PARTIAL', 'note': 'mission data contract unchanged; no new mission runs'},
        'BUDGET': {'status': 'GATED', 'note': 'A 14/20 used, remaining 6 NOT_AUTHORIZED, no carry-over; B/C locked'},
    },
    'approved_for_next_stage': False,
    'key_results': {
        'batch1': {'starts': 4, 'outcomes': {'S0': 'SOLVED_VALID', 'S1': 'SOLVED_VALID', 'S2': 'SOLVED_VALID', 'S3': 'FAILED_INVALID_POLAR'}, 'wall_s': 11.572},
        'batch1b': {'starts': 2, 'S4_CLtot': 0.074250958215, 'S4_CDi': 0.002606535876, 'S5_CLtot': 0.070832611794, 'S5_CDi': 0.002488240979, 'wall_s': 28.828},
        'batch2': {'starts': 8, 'wall_s': 9.846, 'S6_CLtot': 0.037164223, 'S6_diagnostic_band_pass': True, 'density_max_abs_delta_pct': 2.7033, 'repeat_delta_CLtot': -8.338e-08, 'repeat_delta_CDtot': -8.868e-07},
        'gate2': {'registration': 'REGISTERED_POST_HOC_DIAGNOSTIC', 's3_s4_diagnostic_band': [0.06, 0.09], 's6_independent_band': [0.03, 0.045], 's6_band_pass': True},
    },
    'fallback': {'status': 'NOT_TRIGGERED', 'class_B_used': 0, 'evaluator': 'RCAIDE_VLM_EMPIRICAL_LF_M202', 'evaluator_implemented': False},
    'su2_crosscheck': {'status': 'NOT_EXECUTED', 'class_C_used': 0, 'status_label': 'LOCKED'},
    'evidence': {
        'run_dir': RUN_REL,
        'batch2_files': 241,
        'batch2_bytes': 7788381,
        'batch2_bytes_scope': 'pre-commit worktree raw bytes of evidence/batch2 (241 files); clean checkout bytes are slightly smaller because git normalizes tracked text files to LF (see data_manifest.checkout_verification).',
        'batch2_results_sha256': sha_file(RUN_DIR + '/evidence/batch2/batch2_results.json'),
        'batch2_ledger_rows': len(B2_LED),
        'batch2_final_checks': '36/36 PASS',
        'batch2_corrections': 'evidence/batch2_corrections.json',
        'v1_evidence': 'evidence/v1 (4 billable + 1 non-billable AMEND row)',
        'v1b_evidence': 'evidence/v1b (2 billable)',
        'figures': [{'name': fr['name'], 'repo_path': fr['repo_path'], 'sha256_raw': fr['sha256_raw'], 'bytes': fr['bytes']} for fr in fig_records],
        'report': {'path': REPORT_REL, 'sha256_raw': sha_file(REPORT_DEST), 'bytes': os.path.getsize(REPORT_DEST)},
    },
    'review_refs': REVIEW_REFS,
    'deliverables': deliverables,
    'limitations': [
        'All coordinates/forces are VSPAERO internal thin-surface coefficients; no physical validation and no real-drag claim.',
        'Single AoA per case; lifting-surfaces-only for 12D cases; no mesh-convergence study.',
        'Ew is unavailable due to 0/0 derived ratio; E and L/D are internal quantities only.',
        'No wave-drag, compressibility correction or body correction injected; BODY-CORR stays BLOCKED.',
        'A-class remaining 6 starts were not authorized and are not carried over.',
        'Package JSONs contain machine-specific absolute paths (external artifact locators, worktree/install paths) as provenance only; hashes are authoritative.',
    ],
    'next_steps': ['A5 packaging review (task-140 series) and A3 delta audit of the committed package', 'Issue #4 corrected factual receipt (Chinese, auditable) after commit/push', 'No main merge; P5/P6 remain frozen'],
}
write_json('summary.json', SUMMARY)

print('stage: data_manifest')
MANIFEST_FILES = []
for p in list_files(RUN_DIR):
    relp = os.path.relpath(p, RUN_DIR).replace(chr(92), '/')
    if relp == 'data_manifest.json':
        continue
    MANIFEST_FILES.append(file_record(p, rel=relp))
external = []
for cid in sorted(A0_CASES):
    path, sha, b = ext_vspgeom_for_a0(cid)
    actual = sha_file(ensure(path))
    if actual != sha:
        die('external a0 vspgeom sha mismatch: ' + cid)
    external.append({'kind': 'vspgeom_thin_a0', 'case_id': cid, 'path': path, 'sha256_raw': sha, 'bytes': b, 'outside_git': True, 'verified': True})
for cid in sorted(A0V2_CASES):
    path, sha, b = ext_vspgeom_for_a0v2(cid)
    actual = sha_file(ensure(path))
    if actual != sha:
        die('external a0v2 vspgeom sha mismatch: ' + cid)
    external.append({'kind': 'vspgeom_thin_a0v2', 'case_id': cid, 'path': path, 'sha256_raw': sha, 'bytes': b, 'outside_git': True, 'verified': True})
for src in [
    ('batch2_authorization', EXT_D12 + '/lead/D12D005_BATCH2_AUTHORIZATION_20261104T130635Z.json'),
    ('batch2_plan_frozen_candidate', EXT_D12 + '/a5/batch2_prestart_gate/batch2_plan_frozen_candidate.json'),
    ('a5_a0_rev6_verdict', EXT_D12 + '/a5/a0_rev6_delta/verdict.txt'),
    ('a5_batch1b_review_verdict', EXT_D12 + '/a5/batch1b_review/verdict.txt'),
    ('a5_batch1b_review_report', EXT_D12 + '/a5/batch1b_review/batch1b_review.md'),
    ('a5_prestart_gate_review', EXT_D12 + '/a5/batch2_prestart_gate/batch2_prestart_gate_review.md'),
    ('a5_prestart_gate_erratum', EXT_D12 + '/a5/batch2_prestart_gate/erratum_20261104.md'),
    ('a5_results_review', EXT_D12 + '/a5/batch2_results_review/batch2_results_review.md'),
    ('a5_results_review_findings', EXT_D12 + '/a5/batch2_results_review/findings.csv'),
    ('a5_results_review_verdict', EXT_D12 + '/a5/batch2_results_review/verdict.txt'),
    ('a3_prestart_facts', EXT_D12 + '/a3/prestart_audit/facts_prestart.json'),
    ('a3_batch1b_isolation_report', EXT_D12 + '/a3/batch1b_isolation.md'),
    ('a3_batch2_evidence_audit_report', EXT_D12 + '/a3/batch2_evidence_audit/batch2_evidence_audit.md'),
    ('a3_batch2_evidence_audit_facts', EXT_D12 + '/a3/batch2_evidence_audit/facts_batch2_evidence_audit.json'),
    ('a3_a0_rev6_isolation_report', EXT_D12 + '/a3/a0_rev6_isolation_0e62db3.md'),
    ('a3_a0_rev6_facts', EXT_D12 + '/a3/facts_a0_rev6.json'),
]:
    kind, path = src
    data = read_bytes(ensure(path))
    rec = {'kind': kind, 'path': path, 'bytes': len(data), 'sha256_raw': sha_bytes(data), 'outside_git': True, 'verified': True}
    if is_text_bytes(data):
        rec['sha256_canonical_lf'] = sha_bytes(canonical_lf(data))
    external.append(rec)
for fr in fig_records:
    external.append({'kind': 'figure_zh', 'path': fr['repo_path'], 'source_path': fr['source_path'], 'sha256_raw': fr['sha256_raw'], 'bytes': fr['bytes'], 'outside_git': False, 'verified': True, 'language': 'zh-CN'})
rep_data = read_bytes(REPORT_DEST)
external.append({'kind': 'report', 'path': REPORT_REL, 'sha256_raw': sha_bytes(rep_data), 'sha256_canonical_lf': sha_bytes(canonical_lf(rep_data)) if is_text_bytes(rep_data) else None, 'bytes': len(rep_data), 'outside_git': False, 'verified': True})
a2_file_records = []
for a2_root, a2_dirs, a2_names in os.walk(A2_DEST):
    a2_dirs.sort()
    for a2_name in sorted(a2_names):
        a2_p = os.path.join(a2_root, a2_name)
        a2_data = read_bytes(a2_p)
        a2_file_records.append({'path': os.path.relpath(a2_p, A2_DEST).replace(chr(92), '/'), 'bytes': len(a2_data), 'sha256_raw': sha_bytes(a2_data), 'sha256_canonical_lf': sha_bytes(canonical_lf(a2_data)) if is_text_bytes(a2_data) else None})
external.append({'kind': 'a2_provenance_bundle', 'path': A2_REL, 'outside_git': False, 'file_count': len(a2_file_records), 'files': a2_file_records})
MANIFEST = {
    'schema': 'd12d005-data-manifest-1',
    'schema_version': '1.0.0',
    'run_id': RUN_ID,
    'generated_utc': now_utc(),
    'run_dir': RUN_REL,
    'repo': {'path': REPO, 'branch': 'research/d12d005-aero-fallback', 'head': HEAD},
    'hash_modes': ['sha256_raw', 'sha256_canonical_lf'],
    'canonical_lf_definition': 'sha256 over bytes after replacing every CRLF (0x0D 0x0A) with LF (0x0A); applied only to UTF-8 text files; equal to raw when the file is already LF.',
    'verification_scope': 'run_dir files + docs-report + 5 figures + external audit artifacts',
    'checkout_verification': {
        'worktree_eol': 'mixed: 186 run-dir files are CRLF in the original worktree',
        'committed_blob_eol': 'LF for text files (.gitattributes: * text=auto eol=lf)',
        'worktree_raw_sha': 'sha256_raw records the original pre-commit worktree bytes',
        'clean_checkout_rule': 'for is_text files compare sha256_canonical_lf against the checkout bytes; for binary files compare sha256_raw',
        'verifier_source_git': 'python -E -s -B verify_d12d005_package.py --source-git HEAD',
    },
    'path_conventions': {
        'run_dir_paths': 'relative to run_dir',
        'repo_referenced_paths': 'repo-relative (docs/... are repo-relative; deliverables are run-dir-relative)',
        'external_artifact_paths': 'absolute machine-specific locators (EXT state dir, OpenVSP install, worktrees); sha256/bytes are authoritative; in-repo evidence is fully reproducible from repo + external sha manifest',
    },
    'totals': {
        'run_dir_files': len(MANIFEST_FILES),
        'run_dir_bytes': sum(r['bytes'] for r in MANIFEST_FILES),
        'run_dir_text_files': sum(1 for r in MANIFEST_FILES if r['is_text']),
        'run_dir_raw_crlf_files': sum(1 for r in MANIFEST_FILES if r['eol'] == 'crlf'),
        'external_entries': len(external),
    },
    'external_artifacts': external,
    'files': MANIFEST_FILES,
    'self': {'path': 'data_manifest.json', 'note': 'self hash is omitted by design' },
}
write_json('data_manifest.json', MANIFEST)
total_bytes = sum(r['bytes'] for r in MANIFEST_FILES) + len(json.dumps(clean(MANIFEST), ensure_ascii=False, indent=2, sort_keys=False).encode('utf-8'))
print(json.dumps({
    'status': 'PACKAGE_BUILT',
    'generated_utc': SUMMARY['generated_utc'],
    'run_dir_files': len(MANIFEST_FILES),
    'run_dir_bytes': sum(r['bytes'] for r in MANIFEST_FILES),
    'run_dir_text_files': MANIFEST['totals']['run_dir_text_files'],
    'run_dir_crlf_files': MANIFEST['totals']['run_dir_raw_crlf_files'],
    'external_entries': len(external),
    'report_bytes': os.path.getsize(REPORT_DEST),
    'report_sha256_raw': sha_file(REPORT_DEST),
    'report_sha256_canonical_lf': sha_bytes(canonical_lf(read_bytes(REPORT_DEST))),
    'figures': [{'name': fr['name'], 'bytes': fr['bytes'], 'sha256_raw': fr['sha256_raw']} for fr in fig_records],
    'deliverables': [{'path': d['path'], 'bytes': d['bytes'], 'sha256_raw': d['sha256_raw']} for d in deliverables],
    'manifest_self_sha256': sha_file(RUN_DIR + '/data_manifest.json'),
    'physical_call_count': 0,
    'solver_processes_started': 0,
}, ensure_ascii=False, indent=2))