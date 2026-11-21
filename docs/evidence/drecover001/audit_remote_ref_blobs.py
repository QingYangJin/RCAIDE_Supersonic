"""R0 only: hash Git blobs across remote-verified head tips; no project imports."""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def git_to_file(args, output, input_file=None):
    result = subprocess.run(['git', *args], stdin=input_file, stdout=output, stderr=None)
    if result.returncode:
        raise RuntimeError('git command failed: ' + ' '.join(args))


def audit_refs(manifest):
    refs = json.loads(Path(manifest).read_text(encoding='utf-8'))
    trees = []
    object_ids = set()
    for ref in refs['heads']:
        with tempfile.TemporaryFile() as output:
            git_to_file(['ls-tree', '-r', '-z', ref['sha']], output)
            output.seek(0)
            entries = []
            for record in output.read().split(b'\0'):
                if not record:
                    continue
                metadata, path = record.split(b'\t', 1)
                mode, kind, oid = metadata.decode('ascii').split()
                entries.append({'path': path.decode('utf-8'), 'mode': mode, 'kind': kind, 'git_oid': oid})
                if kind == 'blob':
                    object_ids.add(oid)
            trees.append({**ref, 'entries': entries})
    blobs = {}
    with tempfile.TemporaryFile() as inputs, tempfile.TemporaryFile() as output:
        inputs.write(('\n'.join(sorted(object_ids)) + '\n').encode('ascii'))
        inputs.seek(0)
        git_to_file(['cat-file', '--batch'], output, inputs)
        output.seek(0)
        for expected_oid in sorted(object_ids):
            oid, kind, size = output.readline().decode('ascii').strip().split()
            if oid != expected_oid or kind != 'blob':
                raise ValueError('Unexpected git batch response')
            size = int(size)
            data = output.read(size)
            if len(data) != size or output.read(1) != b'\n':
                raise ValueError('Truncated git batch response')
            object_digest = hashlib.sha1(b'blob ' + str(size).encode('ascii') + b'\0' + data).hexdigest()
            if object_digest != oid:
                raise ValueError('Git object identity mismatch: ' + oid)
            blobs[oid] = {'bytes': size, 'sha256': hashlib.sha256(data).hexdigest()}
    return {'schema': 'drecover001.all_ref_blob_audit.v1', 'scope': 'All 20 current GitHub head tips, no tags; ancestors and unreachable/unpushed commits not exhaustively covered', 'remote_refs_source': refs['source_url'], 'raw_git_object_identity_verified': True, 'physical_solver_starts_actual': 0, 'physics_validated': False, 'independent_review': 'NOT_STARTED', 'head_count': len(trees), 'unique_blob_count': len(blobs), 'unique_blob_bytes': sum(x['bytes'] for x in blobs.values()), 'trees': trees, 'blobs': blobs}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--refs', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit_refs(args.refs)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('head_count', 'unique_blob_count', 'unique_blob_bytes', 'physical_solver_starts_actual')}))
