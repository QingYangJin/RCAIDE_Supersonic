"""Zero-physics R0 audit of canonical git-archive bytes; no project imports."""
import argparse, collections, hashlib, json, posixpath, re, tarfile
from pathlib import Path

def audit(archive):
    files = {}
    text = {}
    archive_args = {'fileobj': archive} if hasattr(archive, 'read') else {'name': archive}
    with tarfile.open(mode='r:', **archive_args) as tf:
        for member in tf:
            if not member.isfile():
                continue
            data = tf.extractfile(member).read()
            files[member.name] = {'path': member.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'lf_bytes': len(data.replace(b'\r\n', b'\n')), 'lf_sha256': hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest(), 'crlf_bytes': len(data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')), 'crlf_sha256': hashlib.sha256(data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')).hexdigest()}
            if member.name.endswith(('.json', '.txt', '.md', '.py', '.yaml', '.yml')) and len(data) < 3000000:
                text[member.name] = data.decode('utf-8-sig', errors='replace')
    sums = []
    for name, content in text.items():
        if not posixpath.basename(name).startswith('SHA256SUMS') or not name.startswith('docs/'):
            continue
        for line_no, line in enumerate(content.splitlines(), 1):
            match = re.fullmatch(r'([a-fA-F0-9]{64})[ \t]+[*]?(.+?)[ \t]*', line)
            if not match:
                if line.strip():
                    sums.append({'manifest': name, 'line': line_no, 'status': 'UNPARSED'})
                continue
            expected, declared = match.groups()
            declared = declared.replace('\\', '/')
            # Repository-prefixed paths are root-relative; other paths are manifest-relative.
            repo_relative = declared.startswith(('docs/', 'research/', 'scripts/', 'tests/'))
            candidates = [posixpath.normpath(declared if repo_relative else posixpath.join(posixpath.dirname(name), declared))]
            matches = [p for p in candidates if p in files]
            row = {'manifest': name, 'line': line_no, 'declared_path': declared, 'expected_sha256': expected.lower(), 'candidate_paths': candidates}
            if len(matches) != 1:
                row['status'] = 'MISSING' if not matches else 'AMBIGUOUS'
                row['candidate_hash_matches'] = [p for p in matches if files[p]['sha256'] == expected.lower()]
            else:
                asset = files[matches[0]]
                row.update(resolved_path=matches[0], actual_sha256=asset['sha256'], bytes=asset['bytes'])
                row['status'] = 'MATCH' if asset['sha256'] == expected.lower() else 'HASH_MISMATCH'
                row['newline_only_match'] = asset['sha256'] != expected.lower() and expected.lower() in (asset['lf_sha256'], asset['crlf_sha256'])
            sums.append(row)
    payloads = []
    for name, content in text.items():
        if name != 'docs/evidence/dreal001/m1a_deck_freeze_20261113/manifest.json':
            continue
        manifest = json.loads(content)
        for slot in manifest['slots']:
            for role, record in slot['files'].items():
                path = record['payload_path']
                asset = files.get(path)
                payloads.append({'slot_id': slot['slot_id'], 'role': role, 'path': path, 'expected_sha256': record['sha256'], 'expected_bytes': record['bytes'], 'status': 'MISSING' if asset is None else ('MATCH' if asset['sha256'] == record['sha256'] and asset['bytes'] == record['bytes'] else 'BYTE_MISMATCH'), 'actual': asset, 'newline_only_match': bool(asset and any(asset[v + '_sha256'] == record['sha256'] and asset[v + '_bytes'] == record['bytes'] for v in ('lf', 'crlf')))})
    categories = collections.defaultdict(list)
    for path in files:
        if path.startswith('research/concorde_metaopt/dreal001/'):
            categories['dreal001_sources_and_evidence'].append(path)
        if path.endswith(('.polar', '.history', '.adb', '.vspgeom', '.vspaero')):
            categories['solver_file_candidates_not_physics_validated'].append(path)
        if path.endswith(('.pt', '.pth', '.ckpt', '.npz', '.pkl')):
            categories['checkpoint_or_array_candidates_not_real_label_validated'].append(path)
        if 'ledger' in path.lower():
            categories['ledger_named_assets'].append(path)
    return {'schema': 'drecover001.canonical_blob_audit.v1', 'baseline': '4c51c7df34c9626999ef2e66e5a6c76a2b9c92e2', 'scope': 'PINNED_LOCAL_GIT_TREE_EXPORT_NOT_ALL_REFS', 'byte_export_requirement': 'git -c core.autocrlf=false -c core.eol=lf archive; no digest normalization used for MATCH', 'physical_solver_starts_actual_this_audit': 0, 'physics_validated': False, 'independent_review': 'NOT_STARTED', 'tracked_file_count': len(files), 'tracked_bytes': sum(a['bytes'] for a in files.values()), 'checksums_summary': dict(collections.Counter(r['status'] for r in sums)), 'checksums': sums, 'm1a_payload_summary': dict(collections.Counter(r['status'] for r in payloads)), 'm1a_payloads': payloads, 'categories': dict(categories), 'files': list(files.values())}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.archive)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('schema', 'tracked_file_count', 'tracked_bytes', 'checksums_summary', 'm1a_payload_summary', 'physical_solver_starts_actual_this_audit')}, indent=2))

if __name__ == '__main__':
    main()
