# -*- coding: utf-8 -*-
"""Add git-source verification to the package verifier and checkout notes to the builder."""
import io

B = 'build_d12d005_package.py'
V = 'verify_d12d005_package.py'

s = io.open(B, encoding='utf-8').read()
a = "    'path_conventions': {"
block = """    'checkout_verification': {
        'worktree_eol': 'mixed: 186 run-dir files are CRLF in the original worktree',
        'committed_blob_eol': 'LF for text files (.gitattributes: * text=auto eol=lf)',
        'worktree_raw_sha': 'sha256_raw records the original pre-commit worktree bytes',
        'clean_checkout_rule': 'for is_text files compare sha256_canonical_lf against the checkout bytes; for binary files compare sha256_raw',
        'verifier_source_git': 'python -E -s -B verify_d12d005_package.py --source-git HEAD',
    },""".replace(chr(10) + '    ' + chr(10), '')
assert a in s, 'path_conventions anchor missing'
s = s.replace(a, block + chr(10) + a, 1)
io.open(B, 'w', encoding='utf-8', newline=chr(10)).write(s)
print('builder checkout block added')

v = io.open(V, encoding='utf-8').read()
marker = "result = {'checks': len(checks)"
insert = '''
def verify_from_git(rev):
    import subprocess
    items = []
    for rel, rec in sorted(listed.items()):
        items.append((RUN_REL + '/' + rel, rec))
    for e in M['external_artifacts']:
        if e.get('outside_git') is False and e['kind'] in ('report', 'figure_zh'):
            items.append((e['path'], e))
    reqs = b''.join((rev + ':' + p + chr(10)).encode('utf-8') for p, _ in items)
    proc = subprocess.Popen(['git', '-C', REPO, 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out, _ = proc.communicate(reqs)
    bad = []
    i = 0
    for p, rec in items:
        nl = out.index(bytes([10]), i)
        header = out[i:nl]
        i = nl + 1
        parts = header.split(b' ')
        if len(parts) < 3 or parts[1] != b'blob':
            bad.append((p, 'not_blob', header[:80].decode('utf-8', 'replace')))
            continue
        size = int(parts[2])
        blob = out[i:i + size]
        i += size + 1
        if rec.get('is_text'):
            live = sha(blob.replace(bytes([13, 10]), bytes([10])))
            ok = live == rec.get('sha256_canonical_lf')
        else:
            live = sha(blob)
            ok = live == rec['sha256_raw']
        if not ok:
            bad.append((p, rec.get('sha256_raw'), rec.get('sha256_canonical_lf'), live))
    chk('git_blob_verification', not bad, {'items': len(items), 'bad': bad[:5]})

if '--source-git' in sys.argv:
    idx = sys.argv.index('--source-git')
    rev = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else 'HEAD'
    verify_from_git(rev)

'''
assert marker in v, 'result marker missing'
v = v.replace(marker, insert + marker, 1)
io.open(V, 'w', encoding='utf-8', newline=chr(10)).write(v)
print('verifier git mode added')