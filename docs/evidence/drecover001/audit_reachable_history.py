"""Lead R0: inspect all objects reachable from verified remote head SHAs, zero physics."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from audit_remote_ref_blobs import git_to_file


def git_bytes(args, data=None):
    with tempfile.TemporaryFile() as inputs, tempfile.TemporaryFile() as output:
        if data is not None:
            inputs.write(data)
            inputs.seek(0)
        git_to_file(args, output, inputs if data is not None else None)
        output.seek(0)
        return output.read()


def audit_history(refs_path):
    refs = json.loads(Path(refs_path).read_text(encoding='utf-8'))
    heads = ('\n'.join(r['sha'] for r in refs['heads']) + '\n').encode('ascii')
    shallow = git_bytes(['rev-parse', '--is-shallow-repository']).strip().decode()
    if shallow != 'false':
        raise ValueError('Shallow repository cannot support complete reachable-object claims')
    commits = git_bytes(['rev-list', '--stdin'], heads).decode().splitlines()
    records = git_bytes(['rev-list', '--objects', '--stdin'], heads).splitlines()
    object_paths = {}
    for record in records:
        oid, _, path = record.partition(b' ')
        object_paths[oid.decode('ascii')] = path.decode('utf-8')
    request = ('\n'.join(sorted(object_paths)) + '\n').encode('ascii')
    headers = git_bytes(['cat-file', '--batch-check'], request).decode().splitlines()
    blob_ids = []
    for header in headers:
        fields = header.split()
        if len(fields) != 3:
            raise ValueError('Missing reachable object: ' + header)
        if fields[1] == 'blob':
            blob_ids.append(fields[0])
    blobs = {}
    with tempfile.TemporaryFile() as inputs, tempfile.TemporaryFile() as output:
        inputs.write(('\n'.join(blob_ids) + '\n').encode('ascii'))
        inputs.seek(0)
        git_to_file(['cat-file', '--batch'], output, inputs)
        output.seek(0)
        for expected in blob_ids:
            oid, kind, size = output.readline().decode('ascii').strip().split()
            size = int(size)
            data = output.read(size)
            if oid != expected or kind != 'blob' or len(data) != size or output.read(1) != b'\n':
                raise ValueError('Invalid batch payload: ' + expected)
            if hashlib.sha1(b'blob ' + str(size).encode() + b'\0' + data).hexdigest() != oid:
                raise ValueError('Git identity mismatch: ' + oid)
            blobs[oid] = {'representative_path': object_paths[oid], 'bytes': size, 'sha256': hashlib.sha256(data).hexdigest()}
    path_versions = {}
    for commit in commits:
        for record in git_bytes(['ls-tree', '-r', '-z', commit]).split(b'\0'):
            if not record:
                continue
            metadata, path = record.split(b'\t', 1)
            mode, kind, oid = metadata.decode('ascii').split()
            if kind == 'blob':
                path_versions.setdefault(path.decode('utf-8'), set()).add(oid)
    path_versions = {p: sorted(ids) for p, ids in sorted(path_versions.items())}
    return {'path_versions': path_versions, 'schema': 'drecover001.reachable_history_audit.v1', 'scope': 'All objects reachable from 20 API-verified remote head SHAs; no unreachable server objects, hidden refs or unpushed commits', 'source_refs': refs['heads'], 'shallow_repository': False, 'reachable_commit_count': len(commits), 'reachable_object_count': len(object_paths), 'unique_blob_count': len(blobs), 'unique_blob_bytes': sum(x['bytes'] for x in blobs.values()), 'raw_git_object_identity_verified': True, 'physical_solver_starts_actual': 0, 'physics_validated': False, 'independent_review': 'NOT_STARTED', 'commits': commits, 'blobs': blobs, 'path_limit': 'path_versions covers every blob path at every reachable commit; representative_path is only the rev-list label'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--refs', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit_history(args.refs)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('reachable_commit_count', 'reachable_object_count', 'unique_blob_count', 'unique_blob_bytes', 'physical_solver_starts_actual')}))
