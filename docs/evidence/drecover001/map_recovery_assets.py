"""R0 evidence classification only; no imports from research or solver invocation."""
import ast
import json
import re
from collections import Counter
from pathlib import Path


def digest_status(value, blobs, expected_bytes=None):
    if not re.fullmatch(r'[a-fA-F0-9]{64}', str(value)):
        return {'status': 'ABBREVIATED_NOT_IDENTITY_PROOF', 'digest': value, 'matches': []}
    matches = [{'git_oid': oid, **item} for oid, item in blobs.items() if item['sha256'].lower() == value.lower()]
    if expected_bytes is not None:
        matches = [x for x in matches if x['bytes'] == expected_bytes]
    return {'status': 'BYTE_IDENTITY_FOUND' if matches else 'NOT_FOUND_IN_REACHABLE_HISTORY', 'digest': value, 'expected_bytes': expected_bytes, 'matches': matches}


def collect_claims(index, blobs, prefix=''):
    claims = []
    if isinstance(index, list):
        for i, value in enumerate(index):
            if isinstance(value, (dict, list)):
                claims.extend(collect_claims(value, blobs, prefix + str(i) + '.'))
        return claims
    for key, value in index.items():
        name = prefix + key
        if isinstance(value, (dict, list)):
            claims.extend(collect_claims(value, blobs, name + '.'))
        elif isinstance(value, str) and (re.fullmatch(r'[a-fA-F0-9]{64}', value) or (prefix == 'key_code_sha256.')):
            bytes_key = key.replace('sha256', 'bytes')
            claims.append({'index_key': name, **digest_status(value, blobs, index.get(bytes_key) if 'sha256' in key else None)})
    return claims


def classify_path(path):
    lower = path.lower()
    if lower.endswith(('.polar', '.history', '.adb', '.lod', '.stab')):
        return 'SOLVER_OUTPUT_CANDIDATE_NOT_PHYSICS_VALIDATED'
    if lower.endswith(('.vspgeom', '.vspaero', '.vsp3')):
        return 'MODEL_OR_DECK_CANDIDATE_NOT_REAL_LABEL'
    if lower.endswith(('.pt', '.pth', '.ckpt', '.pkl', '.npz')):
        return 'CHECKPOINT_OR_ARRAY_CANDIDATE_NOT_ADMITTED'
    if 'ledger' in lower:
        return 'LEDGER_NAMED_SOURCE_OR_REPORT_NOT_RECONCILED'
    if path.startswith('docs/evidence/dreal001/figs/'):
        return 'HISTORICAL_FIGURE_OR_TABLE_NOT_NEW_PHYSICS'
    if path.startswith('docs/evidence/dreal001/m0r_'):
        return 'M0R_CONTRACT_NOT_REAL_LABEL'
    if path.startswith('research/concorde_metaopt/') and path.endswith('.py'):
        return 'SOURCE_CODE_PRESENT_NOT_READINESS_PROOF'
    return 'OTHER'


def build_matrix(history, index, head_summary):
    groups = {}
    for path, versions in history['path_versions'].items():
        category = classify_path(path)
        if category != 'OTHER':
            groups.setdefault(category, []).append({'path': path, 'versions': [{'git_oid': oid, 'bytes': history['blobs'][oid]['bytes'], 'sha256': history['blobs'][oid]['sha256']} for oid in versions]})
    missing_paths = [{'path': row['path'], 'historical_versions': history['path_versions'].get(row['path'], []), 'status': 'PRESENT_IN_REACHABLE_HISTORY' if row['path'] in history['path_versions'] else 'ABSENT_FROM_ALL_' + str(history['reachable_commit_count']) + '_REACHABLE_TREES'} for row in head_summary['missing_paths']]
    additional = []
    for claim in head_summary['historical_sha_matches']:
        additional.append(digest_status(claim['sha256'], history['blobs']))
    return {'schema': 'drecover001.historical_asset_matrix.v1', 'scope': history['scope'], 'physical_solver_starts_actual': 0, 'physics_validated': False, 'cache_admission': 'NONE', 'replayable': 'NOT_ESTABLISHED', 'independent_review': 'NOT_STARTED', 'reachable_commit_count': history['reachable_commit_count'], 'index_digest_claims': collect_claims(index, history['blobs']), 'additional_required_digests': additional, 'critical_path_claims': missing_paths, 'historical_commit_claims': [{'index_key': k, 'commit_prefix': v, 'reachable_matches': [c for c in history['commits'] if c.startswith(v)]} for k, v in commit_claims(index)], 'group_counts': {k: len(v) for k, v in groups.items()}, 'groups': groups, 'limits': ['Byte presence is not solver validity or a fresh independent approval', 'No off-machine backup/restore proof is created by this matrix', 'Unknown or unpushed server objects are excluded', 'Historical review/report PASS does not authorize current physics']}


def commit_claims(data, prefix=''):
    rows = []
    for key, value in data.items():
        if isinstance(value, dict):
            rows.extend(commit_claims(value, prefix + key + '.'))
        elif isinstance(value, str) and ('commit' in key or key == 'f0_parent') and re.fullmatch(r'[a-fA-F0-9]{7,40}', value):
            rows.append((prefix + key, value))
    return rows


if __name__ == '__main__':
    folder = Path(__file__).resolve().parent
    history = json.loads((folder / 'reachable_history_audit.json').read_text(encoding='utf-8'))
    index = json.loads((folder.parent / 'dfixed001_stage_evidence_index_20261113.json').read_text(encoding='utf-8'))
    heads = json.loads((folder / 'asset_audit_summary.json').read_text(encoding='utf-8'))
    result = build_matrix(history, index, heads)
    root = folder.parents[2]
    tree = ast.parse((root / 'research/concorde_metaopt/dreal001/m1/task_evaluator.py').read_text(encoding='utf-8'))
    frozen = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'U1_REFERENCE_FILES' for t in node.targets))
    result['u1_dependency_claims'] = [{'name': name, 'path': path, **digest_status(digest, history['blobs'], size)} for name, path, digest, size in frozen]
    figures = json.loads((root / 'docs/evidence/dreal001/figs/data_sources.json').read_text(encoding='utf-8'))
    result['figure_source_digest_claims'] = collect_claims(figures, history['blobs'])
    result['missing_checksum_history'] = [{'declared_path': c['declared_path'], **digest_status(c['expected_sha256'], history['blobs'])} for c in heads['missing_checksums']]
    (folder / 'historical_asset_matrix.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'digest_claim_status': dict(Counter(x['status'] for x in result['index_digest_claims'])), 'additional_digests': [x['status'] for x in result['additional_required_digests']], 'critical_paths': result['critical_path_claims'], 'group_counts': result['group_counts'], 'missing_commit_claims': [x for x in result['historical_commit_claims'] if not x['reachable_matches']]}))
