"""Lead R0 byte/provenance reconciliation only; never calls a solver or admits labels."""
import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from audit_reachable_history import git_bytes

PINNED_COMMIT = 'aef2cb71e07aa28abfc28e34b14bf9dc1579c2e3'
PREFIX = 'research/concorde_metaopt/optimization_runs/d12d005-20261104T0430Z/evidence/batch2/'


def repository_path(value):
    normalized = str(value).replace('\\', '/')
    marker = 'research/concorde_metaopt/'
    if normalized.startswith(marker):
        return normalized
    offset = normalized.find('/' + marker)
    return normalized[offset + 1:] if offset >= 0 else None


def match_artifact(artifact, history):
    path = repository_path(artifact.get('path', ''))
    digest = artifact.get('sha256')
    size = artifact.get('bytes')
    ids = history['path_versions'].get(path, [])
    versions = [{'git_oid': oid, **history['blobs'][oid]} for oid in ids]
    matches = [v['git_oid'] for v in versions if isinstance(digest, str) and v['sha256'].lower() == digest.lower() and (size is None or (type(size) is int and v['bytes'] == size))]
    if path is None or not re.fullmatch(r'[a-fA-F0-9]{64}', str(digest)) or (size is not None and (type(size) is not int or size < 0)):
        status = 'INVALID_PROVENANCE_CLAIM'
    elif matches:
        status = 'EXACT_PATH_AND_DIGEST_FOUND' if size is None else 'EXACT_PATH_SIZE_AND_DIGEST_FOUND'
    elif ids:
        status = 'PATH_PRESENT_BUT_BYTES_DIFFER'
    else:
        status = 'PATH_ABSENT_FROM_REACHABLE_TREES'
    return {'original_path': artifact.get('path'), 'repository_path': path, 'expected_sha256': digest, 'expected_bytes': size, 'status': status, 'matching_git_oids': matches, 'historical_versions': versions}


def diagnose_newlines(checks, read_blob):
    """Explain differences without changing status, hashes, or writing reconstructed raw."""
    cache = {}
    for check in checks:
        diagnostics = []
        if check['status'] == 'PATH_PRESENT_BUT_BYTES_DIFFER':
            for version in check['historical_versions']:
                oid = version['git_oid']
                if oid not in cache:
                    cache[oid] = read_blob(oid)
                raw = cache[oid]
                if hashlib.sha256(raw).hexdigest() != version['sha256'] or len(raw) != version['bytes']:
                    raise ValueError('Diagnostic blob identity mismatch: ' + oid)
                lf = raw.replace(b'\r\n', b'\n')
                for name, candidate in [('LF', lf), ('CRLF', lf.replace(b'\n', b'\r\n'))]:
                    if hashlib.sha256(candidate).hexdigest() == check['expected_sha256'].lower() and (check['expected_bytes'] is None or len(candidate) == check['expected_bytes']):
                        diagnostics.append({'git_oid': oid, 'diagnostic_transform': name, 'matches_claim_only_after_transform': True})
        check['newline_diagnostics'] = diagnostics
    return sum(bool(c['newline_diagnostics']) for c in checks)


def analyze_records(records, history, budget):
    events = defaultdict(list)
    checks = []
    issues = []
    for row in records:
        events[row['event_id']].append(row)
        if row.get('record_type') != 'COMPLETED':
            continue
        for kind, artifact in row.get('artifacts', {}).items():
            checks.append({'event_id': row['event_id'], 'case_id': row['case_id'], 'artifact_kind': kind, **match_artifact(artifact, history)})
        cwd = row.get('cwd', '').replace('\\', '/')
        mesh = row.get('vspgeom_basename', '')
        stem = mesh.rsplit('.', 1)[0]
        for kind, name, digest_key, size_key in [
            ('input_mesh', mesh, 'vspgeom_sha256', 'vspgeom_bytes'),
            ('input_setup', stem + '.vspaero', 'setup_sha256', None),
            ('input_vkey', stem + '.vkey', 'vkey_sha256', None),
        ]:
            artifact = {'path': cwd + '/' + name, 'sha256': row.get(digest_key), 'bytes': row.get(size_key) if size_key else None}
            checks.append({'event_id': row['event_id'], 'case_id': row['case_id'], 'artifact_kind': kind, **match_artifact(artifact, history)})
    for event_id, rows in events.items():
        counts = Counter(r.get('record_type') for r in rows)
        if counts != Counter({'PENDING': 1, 'COMPLETED': 1}):
            issues.append({'event_id': event_id, 'record_counts': dict(counts)})
        elif rows[0].get('record_type') != 'PENDING':
            issues.append({'event_id': event_id, 'error': 'COMPLETION_PRECEDES_PENDING'})
    completed = [r for r in records if r.get('record_type') == 'COMPLETED']
    completed_ids = {r['event_id'] for r in completed}
    counters = budget.get('counters', {})
    return {
        'schema': 'drecover001.historical_raw_reconciliation.v1',
        'scope': 'Historical batch2 provenance only, not corrected F1R2/F2R2 or current authorization',
        'record_count': len(records), 'distinct_event_count': len(events),
        'completed_record_count': len(completed), 'distinct_completed_event_count': len(completed_ids),
        'pending_completed_pair_issues': issues,
        'billable_completed_records': sum(r.get('billable') is True for r in completed),
        'reported_batch_starts': counters.get('starts_used_this_batch'),
        'reported_retries': counters.get('retries_used'),
        'completed_count_matches_reported_starts': len(completed_ids) == counters.get('starts_used_this_batch'),
        'recorded_returncodes': dict(Counter(str(r.get('returncode')) for r in completed)),
        'recorded_physical_validation': dict(Counter(r.get('physical_validation') for r in completed)),
        'recorded_labels': dict(Counter(r.get('label') for r in completed)),
        'artifact_claim_counts': dict(Counter(c['status'] for c in checks)),
        'artifact_checks': checks,
        'physical_solver_starts_actual_this_recovery': 0,
        'cache_admission': 'NONE', 'physics_validated': False,
        'independent_review': 'NOT_STARTED',
        'limitations': ['Ledger event counts are historical record reconciliation, not newly witnessed process starts.', 'Inputs without size claims match path+SHA only.', 'Exact bytes do not establish physical applicability, executable provenance, complete replay or independent-failure-domain backup.', 'Legacy Infinity tokens are reported separately and never converted into labels.'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--history', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    history = json.loads(Path(args.history).read_text(encoding='utf-8'))
    documents = {}
    identities = {}
    nonstandard = []
    for name in ('ledger.jsonl', 'budget_ledger.json'):
        path = PREFIX + name
        raw = git_bytes(['show', PINNED_COMMIT + ':' + path])
        oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        identity = {'git_oid': oid, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if oid not in history['path_versions'].get(path, []) or history['blobs'][oid]['sha256'] != identity['sha256']:
            raise ValueError('Source not verified in reachable history: ' + path)
        identities[path] = identity
        if name.endswith('.jsonl'):
            rows = []
            for line_number, line in enumerate(raw.decode('utf-8').splitlines(), 1):
                def legacy_constant(value):
                    nonstandard.append({'path': path, 'line': line_number, 'token': value})
                    return {'legacy_nonfinite_token': value}
                rows.append(json.loads(line, parse_constant=legacy_constant))
            documents[name] = rows
        else:
            documents[name] = json.loads(raw)
    result = analyze_records(documents['ledger.jsonl'], history, documents['budget_ledger.json'])
    result['newline_explained_mismatch_claims'] = diagnose_newlines(result['artifact_checks'], lambda oid: git_bytes(['cat-file', 'blob', oid]))
    result['normalization_used_for_exact_match'] = False
    result.update({'source_commit': PINNED_COMMIT, 'source_identities': identities, 'legacy_nonstandard_json_tokens': nonstandard})
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('record_count', 'distinct_event_count', 'distinct_completed_event_count', 'pending_completed_pair_issues', 'completed_count_matches_reported_starts', 'artifact_claim_counts')}))


if __name__ == '__main__':
    main()
