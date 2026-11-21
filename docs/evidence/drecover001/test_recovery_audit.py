"""Offline R0 audit tests. No solver, project imports, or physical observations."""
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from audit_historical_raw import repository_path, match_artifact, analyze_records, diagnose_newlines
from audit_canonical_inventory import audit
from map_recovery_assets import digest_status, collect_claims, classify_path, build_matrix, commit_claims


class AuditTests(unittest.TestCase):
    def run_audit(self, files):
        # Pure in-memory fixtures avoid writing outside the workspace.
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w') as tf:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        archive.seek(0)
        return audit(archive)

    def checksum(self, data, name):
        return (hashlib.sha256(data).hexdigest() + '  ' + name + '\n').encode()

    def test_manifest_relative_not_root_readme(self):
        result = self.run_audit({'README.md': b'wrong', 'docs/example/README.md': b'correct', 'docs/example/SHA256SUMS.txt': self.checksum(b'correct', 'README.md')})
        self.assertEqual(result['checksums_summary'], {'MATCH': 1})
        self.assertEqual(result['checksums'][0]['resolved_path'], 'docs/example/README.md')

    def test_repo_relative(self):
        result = self.run_audit({'docs/example/file.json': b'{}', 'docs/example/SHA256SUMS.txt': self.checksum(b'{}', 'docs/example/file.json')})
        self.assertEqual(result['checksums_summary'], {'MATCH': 1})

    def test_newline_difference_is_not_byte_match(self):
        result = self.run_audit({'docs/example/a.txt': b'abc\r\n', 'docs/example/SHA256SUMS.txt': self.checksum(b'abc\n', 'a.txt')})
        self.assertEqual(result['checksums_summary'], {'HASH_MISMATCH': 1})
        self.assertTrue(result['checksums'][0]['newline_only_match'])

    def test_missing_and_unparsed(self):
        result = self.run_audit({'docs/example/SHA256SUMS.txt': self.checksum(b'abc', 'absent') + b'invalid\n'})
        self.assertEqual(result['checksums_summary'], {'MISSING': 1, 'UNPARSED': 1})

    def test_payload_size_is_required(self):
        data = b'payload'
        manifest = {'slots': [{'slot_id': 'OFFLINE_FIXTURE', 'files': {'deck': {'payload_path': 'docs/example/deck', 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data) + 1}}}]}
        result = self.run_audit({'docs/example/deck': data, 'docs/evidence/dreal001/m1a_deck_freeze_20261113/manifest.json': json.dumps(manifest).encode()})
        self.assertEqual(result['m1a_payload_summary'], {'BYTE_MISMATCH': 1})

    def test_solver_file_presence_never_validates_physics(self):
        result = self.run_audit({'docs/example/fake.polar': b'not a real observation'})
        self.assertFalse(result['physics_validated'])
        self.assertEqual(result['physical_solver_starts_actual_this_audit'], 0)
        self.assertIn('docs/example/fake.polar', result['categories']['solver_file_candidates_not_physics_validated'])


class HistoricalRawTests(unittest.TestCase):
    def test_windows_provenance_mapping(self):
        self.assertEqual(repository_path('D:/old/research/concorde_metaopt/raw/a'), 'research/concorde_metaopt/raw/a')
        self.assertIsNone(repository_path('D:/unrelated/a'))

    def test_same_digest_elsewhere_not_original_path_proof(self):
        history = {'path_versions': {'research/concorde_metaopt/other': ['oid']}, 'blobs': {'oid': {'sha256': 'a' * 64, 'bytes': 3}}}
        result = match_artifact({'path': 'research/concorde_metaopt/raw', 'sha256': 'a' * 64, 'bytes': 3}, history)
        self.assertEqual(result['status'], 'PATH_ABSENT_FROM_REACHABLE_TREES')

    def test_uppercase_digest_is_same_byte_identity(self):
        raw = b'fixture'
        digest = hashlib.sha256(raw).hexdigest()
        history = {'path_versions': {'research/concorde_metaopt/a': ['oid']}, 'blobs': {'oid': {'sha256': digest, 'bytes': len(raw)}}}
        result = match_artifact({'path': 'research/concorde_metaopt/a', 'sha256': digest.upper(), 'bytes': len(raw)}, history)
        self.assertEqual(result['status'], 'EXACT_PATH_SIZE_AND_DIGEST_FOUND')
        self.assertEqual(result['matching_git_oids'], ['oid'])

    def test_uppercase_newline_diagnostic_does_not_upgrade_identity(self):
        raw = b'a\nb\n'
        history = {'path_versions': {'research/concorde_metaopt/a': ['oid']}, 'blobs': {'oid': {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}}}
        check = match_artifact({'path': 'research/concorde_metaopt/a', 'sha256': hashlib.sha256(b'a\r\nb\r\n').hexdigest().upper(), 'bytes': 6}, history)
        self.assertEqual(diagnose_newlines([check], lambda oid: raw), 1)
        self.assertEqual(check['status'], 'PATH_PRESENT_BUT_BYTES_DIFFER')

    def test_invalid_digest_and_size(self):
        history = {'path_versions': {}, 'blobs': {}}
        for digest, size in [('z' * 64, 3), ('a' * 64, -1), ('a' * 64, True)]:
            self.assertEqual(match_artifact({'path': 'research/concorde_metaopt/a', 'sha256': digest, 'bytes': size}, history)['status'], 'INVALID_PROVENANCE_CLAIM')

    def test_newline_diagnostic_never_upgrades_identity(self):
        raw = b'a\nb\n'
        digest = hashlib.sha256(raw).hexdigest()
        history = {'path_versions': {'research/concorde_metaopt/a': ['oid']}, 'blobs': {'oid': {'sha256': digest, 'bytes': len(raw)}}}
        claim = {'path': 'research/concorde_metaopt/a', 'sha256': hashlib.sha256(b'a\r\nb\r\n').hexdigest(), 'bytes': 6}
        check = match_artifact(claim, history)
        self.assertEqual(diagnose_newlines([check], lambda oid: raw), 1)
        self.assertEqual(check['status'], 'PATH_PRESENT_BUT_BYTES_DIFFER')
        self.assertEqual(check['matching_git_oids'], [])

    def test_pending_and_completion_count_once(self):
        event = {'event_id': 'fixture', 'case_id': 'fixture', 'billable': True}
        records = [{**event, 'record_type': 'PENDING'}, {**event, 'record_type': 'COMPLETED'}]
        result = analyze_records(records, {'path_versions': {}, 'blobs': {}}, {'counters': {'starts_used_this_batch': 1}})
        self.assertEqual(result['distinct_completed_event_count'], 1)
        self.assertEqual(result['billable_completed_records'], 1)
        self.assertEqual(result['pending_completed_pair_issues'], [])
        self.assertFalse(result['physics_validated'])
        self.assertEqual(result['cache_admission'], 'NONE')

    def test_duplicate_completion_not_silently_accepted(self):
        row = {'event_id': 'fixture', 'case_id': 'fixture', 'record_type': 'COMPLETED'}
        result = analyze_records([row, row], {'path_versions': {}, 'blobs': {}}, {'counters': {}})
        self.assertTrue(result['pending_completed_pair_issues'])


class AssetMatrixTests(unittest.TestCase):
    def test_abbreviated_digest_never_identity(self):
        self.assertEqual(digest_status('ed0f2324', {})['status'], 'ABBREVIATED_NOT_IDENTITY_PROOF')

    def test_digest_and_size_both_required(self):
        digest = 'a' * 64
        blobs = {'oid': {'sha256': digest, 'bytes': 3}}
        self.assertEqual(digest_status(digest.upper(), blobs, 3)['status'], 'BYTE_IDENTITY_FOUND')
        self.assertEqual(digest_status(digest, blobs, 4)['status'], 'NOT_FOUND_IN_REACHABLE_HISTORY')

    def test_code_key_without_byte_sibling(self):
        digest = 'a' * 64
        claims = collect_claims({'key_code_sha256': {'trainer': digest}}, {'oid': {'sha256': digest, 'bytes': 3}})
        self.assertEqual(claims[0]['status'], 'BYTE_IDENTITY_FOUND')
        self.assertIsNone(claims[0]['expected_bytes'])

    def test_report_size_sibling_enforced(self):
        digest = 'a' * 64
        claims = collect_claims({'report': {'sha256': digest, 'bytes': 4}}, {'oid': {'sha256': digest, 'bytes': 3}})
        self.assertEqual(claims[0]['status'], 'NOT_FOUND_IN_REACHABLE_HISTORY')

    def test_solver_or_model_is_never_real_label(self):
        self.assertEqual(classify_path('untrusted.polar'), 'SOLVER_OUTPUT_CANDIDATE_NOT_PHYSICS_VALIDATED')
        self.assertEqual(classify_path('untrusted.vspaero'), 'MODEL_OR_DECK_CANDIDATE_NOT_REAL_LABEL')
        self.assertEqual(classify_path('tutorial.pkl'), 'CHECKPOINT_OR_ARRAY_CANDIDATE_NOT_ADMITTED')

    def test_present_path_missing_path_and_gates(self):
        history = {'scope': 'OFFLINE_FIXTURE', 'path_versions': {'a.polar': ['oid']}, 'blobs': {'oid': {'sha256': 'a' * 64, 'bytes': 3}}, 'reachable_commit_count': 200, 'commits': []}
        result = build_matrix(history, {}, {'missing_paths': [{'path': 'a.polar'}, {'path': 'absent'}], 'historical_sha_matches': []})
        self.assertEqual(result['critical_path_claims'][0]['status'], 'PRESENT_IN_REACHABLE_HISTORY')
        self.assertEqual(result['critical_path_claims'][1]['historical_versions'], [])
        self.assertEqual(result['cache_admission'], 'NONE')
        self.assertFalse(result['physics_validated'])
        self.assertEqual(result['independent_review'], 'NOT_STARTED')

    def test_nested_list_claim_and_size(self):
        digest = 'b' * 64
        claims = collect_claims({'sources': [{'sha256': digest, 'bytes': 5}]}, {'oid': {'sha256': digest, 'bytes': 5}})
        self.assertEqual(claims[0]['index_key'], 'sources.0.sha256')
        self.assertEqual(claims[0]['status'], 'BYTE_IDENTITY_FOUND')
        self.assertEqual(claims[0]['expected_bytes'], 5)

    def test_coverage_count_is_not_hardcoded(self):
        history = {'scope': 'OFFLINE_FIXTURE', 'path_versions': {}, 'blobs': {}, 'reachable_commit_count': 2, 'commits': []}
        result = build_matrix(history, {}, {'missing_paths': [{'path': 'absent'}], 'historical_sha_matches': []})
        self.assertEqual(result['critical_path_claims'][0]['status'], 'ABSENT_FROM_ALL_2_REACHABLE_TREES')

    def test_commit_is_not_digest_claim(self):
        rows = commit_claims({'gates': {'t0': {'commit': '318c5ac', 'verdict': 'PASS'}}})
        self.assertEqual(rows, [('gates.t0.commit', '318c5ac')])


if __name__ == '__main__':
    unittest.main(verbosity=2)
