"""Lead R0 provenance extension beyond batch2; reads git objects only, never starts a solver."""
import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

BUDGET_RE = re.compile(r'(?:^|/)[^/]*(?:ledger|budget)[^/]*\.(?:json|jsonl|csv)$', re.IGNORECASE)
RAW_OUTPUT_EXT = ('.polar', '.history', '.adb')
INPUT_EXT = ('.vspaero', '.vspgeom', '.vkey', '.vsp3')


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def normalize_newlines(raw):
    return raw.replace(b'\r\n', b'\n')


def git_blob(repo, oid):
    return subprocess.run(['git', '-C', str(repo), 'cat-file', 'blob', oid], capture_output=True, check=True).stdout


def local_state(repo, rel, expected_raw):
    path = Path(repo) / rel
    if not path.is_file():
        return {'present': False, 'match': 'ABSENT_LOCALLY'}
    raw = path.read_bytes()
    state = {'present': True, 'bytes': len(raw), 'sha256': sha256_bytes(raw), 'match': 'BYTES_DIFFER'}
    if state['sha256'] == sha256_bytes(expected_raw) and state['bytes'] == len(expected_raw):
        state['match'] = 'EXACT_BYTES'
    elif (sha256_bytes(normalize_newlines(raw)) == sha256_bytes(normalize_newlines(expected_raw))
          and len(normalize_newlines(raw)) == len(normalize_newlines(expected_raw))):
        state['match'] = 'BYTES_DIFFER_LINE_ENDINGS_ONLY'
    return state


def parse_jsonl(raw, nonstandard):
    rows = []
    for line_number, line in enumerate(raw.decode('utf-8', 'replace').splitlines(), 1):
        if not line.strip():
            continue
        def legacy(value):
            nonstandard.append({'line': line_number, 'token': value})
            return {'legacy_nonfinite_token': value}
        rows.append(json.loads(line, parse_constant=legacy))
    return rows


def ledger_summary(rows):
    if all(row.get('record_type') is None for row in rows):
        return {
            'schema': 'ALTERNATE_LEDGER_SCHEMA_NO_RECORD_TYPE',
            'row_count': len(rows),
            'distinct_event_count': len({row.get('event_id') for row in rows}),
            'field_presence': dict(sorted(Counter(key for row in rows for key in row).items())),
            'row_returncodes': dict(Counter(str(row.get('returncode')) for row in rows)),
            'retry_marked_rows': sum(row.get('is_retry') is True for row in rows),
            'outcome_classes': dict(Counter(str(row.get('outcome_class')) for row in rows)),
            'billable_rows': sum(row.get('billable') is True for row in rows),
        }
    pairs = defaultdict(list)
    amendments = []
    for row in rows:
        if row.get('record_type') == 'AMEND':
            amendments.append(row)
            continue
        pairs[row.get('event_id')].append(row)
    completed = [row for row in rows if row.get('record_type') == 'COMPLETED']
    return {
        'schema': 'PENDING_COMPLETED_LEDGER',
        'row_count': len(rows),
        'record_type_counts': dict(sorted(Counter(row.get('record_type') for row in rows).items())),
        'distinct_event_count': len(pairs),
        'completed_record_count': len(completed),
        'distinct_completed_event_count': len({row.get('event_id') for row in completed}),
        'billable_completed_records': sum(row.get('billable') is True for row in completed),
        'retry_marked_records': sum(row.get('is_retry') is True for row in rows),
        'amendment_records': len(amendments),
        'recorded_returncodes': dict(Counter(str(row.get('returncode')) for row in completed)),
        'recorded_labels': dict(Counter(str(row.get('label')) for row in completed)),
        'pair_issues': [
            {'event_id': event_id, 'counts': dict(Counter(r.get('record_type') for r in group))}
            for event_id, group in pairs.items()
            if Counter(r.get('record_type') for r in group) != Counter({'PENDING': 1, 'COMPLETED': 1})
        ],
    }


def budget_summary(payload):
    if not isinstance(payload, dict):
        return {'type': type(payload).__name__}
    keys = [k for k in payload if re.search(r'start|budget|count|limit|charge', k, re.IGNORECASE)]
    return {
        'top_level_keys': sorted(payload)[:40],
        'budget_like_fields': {k: payload[k] for k in keys if not isinstance(payload[k], (dict, list))},
        'counters_present': isinstance(payload.get('counters'), dict),
    }


ABS_PATH_RE = re.compile(r'[A-Za-z]:\\[^"\s,;}]+')


def find_external_refs(node, source, out):
    if isinstance(node, dict):
        path = node.get('path')
        digest = node.get('sha256')
        if isinstance(path, str) and (re.match(r'[A-Za-z]:\\', path) or 'AppData' in path):
            out.append({'source': source, 'path': path,
                        'sha256': str(digest).lower() if isinstance(digest, str) else None})
        for value in node.values():
            find_external_refs(value, source, out)
    elif isinstance(node, list):
        for value in node:
            find_external_refs(value, source, out)


def extract_counters(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('counters'), dict):
        return {}
    counters = payload['counters']
    return {key: counters[key] for key in
            ('starts_used', 'starts_used_this_batch', 'retries_used', 'billable_events') if key in counters}


def ledger_observed(entry):
    ledger = entry.get('ledger') or {}
    if ledger.get('schema') == 'ALTERNATE_LEDGER_SCHEMA_NO_RECORD_TYPE':
        return {'attempts': ledger.get('row_count'), 'starts': ledger.get('distinct_event_count'),
                'retries': ledger.get('retry_marked_rows'), 'billable': ledger.get('billable_rows')}
    return {'attempts': ledger.get('row_count'),
            'starts': ledger.get('distinct_completed_event_count'),
            'retries': ledger.get('retry_marked_records'),
            'billable': ledger.get('billable_completed_records')}


def run_root(path):
    match = re.search(r'/optimization_runs/([^/]+)/', path)
    return match.group(1) if match else None


def source_entry(repo, history, rel, kind, nonstandard):
    blobs, path_versions = history['blobs'], history['path_versions']
    versions = []
    last_raw = None
    for oid in path_versions.get(rel, []):
        raw = git_blob(repo, oid)
        identity = {'git_oid': oid, 'bytes': len(raw), 'sha256': sha256_bytes(raw)}
        if identity['bytes'] != blobs[oid]['bytes'] or identity['sha256'] != blobs[oid]['sha256']:
            raise ValueError('Blob identity mismatch for ' + rel + ' ' + oid)
        versions.append(identity)
        last_raw = raw
    entry = {'repository_path': rel, 'kind': kind, 'versions': versions,
             'remote_present': bool(versions),
             'physical_solver_starts_actual': 0, 'physics_validated': False}
    if versions:
        state = local_state(repo, rel, last_raw)
        entry['worktree'] = state
        entry['local_byte_identical'] = state['match'] == 'EXACT_BYTES'
        entry['classification'] = 'RAW_PRESENT' if state['match'] == 'EXACT_BYTES' else 'REMOTE_PRESENT'
    else:
        entry['classification'] = 'RAW_LOST'
    if rel.endswith('.jsonl') and versions:
        local_nonstandard = []
        summary = ledger_summary(parse_jsonl(last_raw, local_nonstandard))
        if local_nonstandard:
            summary['legacy_nonfinite_tokens'] = local_nonstandard
            nonstandard.extend({'path': rel, **item} for item in local_nonstandard)
        entry['ledger'] = summary
    elif rel.endswith('.json') and versions:
        try:
            entry['budget'] = budget_summary(json.loads(last_raw))
        except Exception as error:  # noqa: BLE001 - record parse failures, never infer values
            entry['budget'] = {'parse_error': type(error).__name__ + ': ' + str(error)[:200]}
    return entry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--history', required=True)
    parser.add_argument('--matrix', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    repo = Path(args.repo)
    history = json.loads(Path(args.history).read_text(encoding='utf-8'))
    matrix = json.loads(Path(args.matrix).read_text(encoding='utf-8'))
    if history['raw_git_object_identity_verified'] is not True:
        raise ValueError('Reachable-history audit did not verify raw git object identity')
    paths = sorted(history['path_versions'])
    nonstandard = []

    budget_paths = [p for p in paths if BUDGET_RE.search(p)]
    raw_output_paths = [p for p in paths if p.lower().endswith(RAW_OUTPUT_EXT) and '/optimization_runs/' in p]
    solver_log_paths = [p for p in paths if '/optimization_runs/' in p and '/evidence/' in p and p.lower().endswith('.log')
                        and re.search(r'solver|vspaero|run', p, re.IGNORECASE)]
    input_paths = [p for p in paths if p.lower().endswith(INPUT_EXT) and '/optimization_runs/' in p]

    budget_sources = [source_entry(repo, history, p, 'BUDGET_LEDGER_DATA', nonstandard) for p in budget_paths]
    raw_outputs = [source_entry(repo, history, p, 'SOLVER_RAW_OUTPUT', nonstandard) for p in raw_output_paths]
    solver_logs = [source_entry(repo, history, p, 'SOLVER_RUN_LOG', nonstandard) for p in solver_log_paths]
    inputs = [source_entry(repo, history, p, 'SOLVER_INPUT_DECK', nonstandard) for p in input_paths]

    claim_groups = {}
    for key in ('index_digest_claims', 'additional_required_digests', 'critical_path_claims',
                'u1_dependency_claims', 'figure_source_digest_claims'):
        claims = []
        for claim in matrix.get(key, []):
            digest = str(claim.get('digest') or claim.get('sha256') or '').lower()
            matches = claim.get('matches') or []
            claims.append({
                'label': claim.get('index_key') or claim.get('name') or claim.get('path'),
                'status': claim.get('status'),
                'digest': digest or None,
                'expected_bytes': claim.get('expected_bytes'),
                'matched_git_oids': [match.get('git_oid') for match in matches],
                'matched_representative_paths': [match.get('representative_path') for match in matches],
                'claim_path': claim.get('path'),
            })
        claim_groups[key] = {
            'claim_count': len(claims),
            'status_counts': dict(Counter(claim['status'] for claim in claims)),
            'claims': claims,
        }

    absent_claims = []
    for token in ('F1R2', 'F2R2'):
        token_paths = [p for p in paths if token.lower() in p.lower()]
        absent_claims.append({
            'claim_id': 'raw:' + token,
            'token': token,
            'classification': 'RAW_LOST' if not token_paths else 'REMOTE_PRESENT',
            'history_path_matches': token_paths,
            'note': 'Corrected original raw was not recovered from any reachable remote head tree.'
                    if not token_paths else 'Token present in reachable history paths.',
        })

    reachable_digests = {blob['sha256'] for blob in history['blobs'].values()}
    external_refs = []
    budget_payloads = {}
    for entry in budget_sources:
        if entry['repository_path'].endswith('.json') and entry['versions']:
            payload = json.loads(git_blob(repo, entry['versions'][-1]['git_oid']))
            budget_payloads[entry['repository_path']] = payload
            find_external_refs(payload, entry['repository_path'], external_refs)
    for ref in external_refs:
        ref['digest_in_reachable_history'] = bool(ref['sha256'] and ref['sha256'] in reachable_digests)

    def walk_strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from walk_strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk_strings(value)

    absolute_map = {}
    for entry in budget_sources:
        if not (entry['repository_path'].endswith('.jsonl') and entry['versions']):
            continue
        rows = parse_jsonl(git_blob(repo, entry['versions'][-1]['git_oid']), [])
        for text in walk_strings(rows):
            for path in ABS_PATH_RE.findall(text):
                kind = ('OPENVSP_EXECUTABLE_PATH' if re.search(r'openvsp|vspaero', path, re.IGNORECASE)
                        else 'AGENT_STATE_DIR' if 'AppData' in path or 'agent_state' in path.lower()
                        else 'OTHER_ABSOLUTE_PATH')
                record = absolute_map.setdefault((path, kind), {'path': path, 'kind': kind, 'sources': []})
                if entry['repository_path'] not in record['sources'] and len(record['sources']) < 3:
                    record['sources'].append(entry['repository_path'])
    absolute_paths = [absolute_map[key] for key in sorted(absolute_map)]

    ledgers = [entry for entry in budget_sources if entry.get('ledger')]
    cross_check = []
    for ledger in ledgers:
        ledger_dir = ledger['repository_path'].rsplit('/', 1)[0]
        same_dir = [path for path in budget_payloads if path.rsplit('/', 1)[0] == ledger_dir]
        same_root = [path for path in budget_payloads
                     if run_root(path) and run_root(path) == run_root(ledger['repository_path'])]
        ancestors = [path for path in same_root
                     if ledger['repository_path'].startswith(path.rsplit('/', 1)[0] + '/')]
        def prefix_tokens(path):
            return path.split('/')[:-1]

        def common_prefix(path):
            left, right = prefix_tokens(path), prefix_tokens(ledger['repository_path'])
            return sum(1 for a, b in zip(left, right) if a == b)

        def filename_priority(path):
            name = path.rsplit('/', 1)[-1]
            if 'actual_solver_budget' in name:
                return 0
            if 'approval' in name:
                return 1
            if 'budget' in name:
                return 2
            return 3

        ordered = []
        for path in same_dir + ancestors:
            if path not in ordered:
                ordered.append(path)
        if same_root and not any(extract_counters(budget_payloads[path]) for path in ordered):
            with_counters = [path for path in same_root if extract_counters(budget_payloads[path])]
            if with_counters:
                closest = max(with_counters, key=lambda path: (-filename_priority(path), common_prefix(path),
                                                               -len(path)))
                if closest not in ordered:
                    ordered.append(closest)
        observed = ledger_observed(ledger)
        for path in ordered:
            if path in same_dir:
                basis = 'SAME_DIRECTORY'
            elif path in ancestors:
                basis = 'ANCESTOR_DIRECTORY'
            else:
                basis = 'SAME_RUN_ROOT_CLOSEST_SIBLING_HEURISTIC'
            counters = extract_counters(budget_payloads[path])
            if not counters:
                continue
            starts_claimed = counters.get('starts_used', counters.get('starts_used_this_batch'))
            flags = []
            if starts_claimed == 0 and observed.get('attempts'):
                flags.append('COUNTERS_CLAIM_ZERO_STARTS_BUT_LEDGER_HAS_ATTEMPTS')
            if isinstance(starts_claimed, int) and starts_claimed and observed.get('starts') is not None \
                    and starts_claimed != observed['starts']:
                flags.append('START_COUNT_DISAGREES_WITH_LEDGER')
            if observed.get('retries') is not None and counters.get('retries_used') is not None \
                    and counters['retries_used'] != observed['retries']:
                flags.append('RETRY_COUNT_DISAGREES_WITH_LEDGER')
            if observed.get('billable') is not None and counters.get('billable_events') is not None \
                    and counters['billable_events'] != observed['billable']:
                flags.append('BILLABLE_COUNT_DISAGREES_WITH_LEDGER')
            cross_check.append({'ledger_path': ledger['repository_path'], 'budget_path': path, 'basis': basis,
                                'authoritative': basis in ('SAME_DIRECTORY', 'ANCESTOR_DIRECTORY'),
                                'budget_counters': counters, 'ledger_observed': observed, 'flags': flags})

    def case_of(path):
        match = re.search(r'/cases/([^/]+)/', path)
        return match.group(1) if match else None

    def digest_groups(entries):
        by_digest = defaultdict(list)
        for entry in entries:
            if entry['versions']:
                by_digest[entry['versions'][-1]['sha256']].append(entry['repository_path'])
        return {digest: group for digest, group in by_digest.items() if len(group) > 1}

    mirrored = []
    grouped = defaultdict(list)
    for entry in raw_outputs:
        case = case_of(entry['repository_path'])
        entry['case_id'] = case
        if case and entry['versions']:
            grouped[(case, entry['versions'][-1]['sha256'])].append(entry['repository_path'])
    for (case, digest), members in grouped.items():
        if len(members) > 1:
            mirrored.append({'case_id': case, 'sha256': digest, 'members': members,
                             'interpretation': 'MIRRORED_COPY_WITHIN_CASE_NOT_EXTRA_PHYSICS'})
    cross_case = {}
    for digest, members in digest_groups(raw_outputs).items():
        cases = {case_of(member) for member in members}
        if len(cases) > 1:
            cross_case[digest] = members

    def counts(entries):
        return dict(Counter(entry['classification'] for entry in entries))

    result = {
        'schema': 'drecover001.r0_provenance_extension.v1',
        'scope': 'Reachable remote history only (20 API-verified head tips); no solver start, no label admission, no physical validation.',
        'source_audit': {
            'path': 'docs/evidence/drecover001/reachable_history_audit.json',
            'sha256': sha256_bytes(Path(args.history).read_bytes()),
            'reachable_commit_count': history['reachable_commit_count'],
            'unique_blob_count': history['unique_blob_count'],
            'unique_blob_bytes': history['unique_blob_bytes'],
            'history_path_count': len(paths),
            'matrix_path': 'docs/evidence/drecover001/historical_asset_matrix.json',
            'matrix_sha256': sha256_bytes(Path(args.matrix).read_bytes()),
        },
        'budget_sources': budget_sources,
        'solver_raw_outputs': raw_outputs,
        'solver_run_logs': solver_logs,
        'solver_input_decks': inputs,
        'claim_groups': claim_groups,
        'external_references': external_refs,
        'absolute_path_references': absolute_paths,
        'ledger_budget_cross_check': cross_check,
        'absent_claims': absent_claims,
        'duplicate_analysis': {
            'mirrored_within_case': mirrored,
            'cross_case_digest_collisions': cross_case,
            'interpretation': 'Byte-identical copies inside one case are mirrored evidence, not additional solver runs.',
        },
        'summary': {
            'budget_source_count': len(budget_sources),
            'budget_classifications': counts(budget_sources),
            'raw_output_count': len(raw_outputs),
            'raw_output_classifications': counts(raw_outputs),
            'solver_log_count': len(solver_logs),
            'solver_log_classifications': counts(solver_logs),
            'input_deck_count': len(inputs),
            'input_deck_classifications': counts(inputs),
            'absent_claim_count': len(absent_claims),
            'external_reference_count': len(external_refs),
            'external_reference_without_reachable_digest': sum(1 for ref in external_refs
                                                               if not ref['digest_in_reachable_history']),
            'absolute_path_reference_count': len(absolute_paths),
            'cross_check_pair_count': len(cross_check),
            'cross_check_flag_count': sum(1 for pair in cross_check if pair['flags'] and pair['authoritative']),
            'cross_check_heuristic_flag_count': sum(1 for pair in cross_check
                                                    if pair['flags'] and not pair['authoritative']),
            'reconciled_ledger_jsonl': [entry['repository_path'] for entry in budget_sources if entry.get('ledger')],
            'claim_status_counts': {key: group['status_counts'] for key, group in claim_groups.items()},
            'batch2_reconciliation_reference': 'docs/evidence/drecover001/historical_raw_reconciliation.json',
        },
        'conclusions': [
            'All byte identities above were re-read from local git objects and matched the reachable-history audit; no network fetch was used.',
            'No path or digest in reachable history establishes corrected F1R2/F2R2 original raw; that loss remains unrepaired and requires a new identity if regenerated.',
            'Historical budget/ledger records are provenance records only; they do not witness new process starts, physical applicability or complete replay.',
            'Input decks and raw outputs under old runs are REMOTE_PRESENT; local presence is reported separately and never upgrades scientific validity.',
            'Byte differences that vanish after LF/CRLF normalization are reported as line-ending-only and are not byte-identical evidence.',
            'Normalization was never used for classification: RAW_PRESENT requires exact local bytes.',
            'Budget/ledger counts that disagree across historical artifacts are reported as flags; the Lead does not pick a winner and does not convert either side into evidence of physics.',
        ],
        'physical_solver_starts_actual': 0,
        'internal_solver_cases_actual': 0,
        'physics_validated': False,
        'cache_admission': 'NONE',
        'admitted_scientific_labels': 0,
        'independent_review': 'NOT_STARTED',
        'legacy_nonstandard_json_tokens': nonstandard,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                                 encoding='utf-8', newline='\n')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
