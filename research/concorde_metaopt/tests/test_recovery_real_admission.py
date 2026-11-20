"""Synthetic bytes exercise admission mechanics; NEVER real solver evidence.

The fixtures use visibly synthetic mesh/deck/polar/history payloads and an
unsigned synthetic audit record. They prove that the gate checks bytes and
bindings, not that any real VSPAERO run happened.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest

from research.concorde_metaopt.dreal001.meta import real_admission as ra
from research.concorde_metaopt.dreal001.meta.meta_dataset import (
    MetaDataset, Observation, TrainNormalizer)
from research.concorde_metaopt.dreal001.meta.raw_verification import ArtifactBinding
from research.concorde_metaopt.dreal001.meta.task_spec import (
    ContractError, TaskSpec, canonical_sha)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


TASKS = (
    TaskSpec("real-0", "train", 2.02, 18000., 50., 100., "a" * 64),
    TaskSpec("real-1", "train", 1.8, 18000., 50., 110., "a" * 64),
    TaskSpec("real-2", "val", 2.2, 18000., 50., 120., "a" * 64),
    TaskSpec("real-3", "test", 2.4, 18000., 50., 130., "a" * 64),
)
TASK = TASKS[0]
DESIGN = (0.,) * 12
MESH = b"SYNTHETIC BYTES - NOT A REAL MESH"
DECK = b"Sref = 10\nMach = 2.02\nBeta = 0\nRho = 1\nVinf = 10\nReCref = 1000000\nAoA = 0, 2, 4\n"
POLAR = (b"Beta Mach AoA Re/1e6 CLtot CDo CDi CDtot\n"
         b"0 2.02 0 1 .1 .01 .01 .02\n"
         b"0 2.02 2 1 .2 .01 .02 .03\n"
         b"0 2.02 4 1 .3 .01 .04 .05\n")
POLAR_AUX = (b"Beta Mach AoA Re/1e6 CLtot CDo CDi CDtot Ew\n"
             b"0 2.02 0 1 .1 .01 .01 .02 inf\n"
             b"0 2.02 2 1 .2 .01 .02 .03 inf\n"
             b"0 2.02 4 1 .3 .01 .04 .05 inf\n")
HISTORY = b"SYNTHETIC VSPAERO HISTORY - NOT A REAL SOLVER LOG\n"
WORK_ROOT = Path(__file__).resolve().parent / "_real_admission_work"


def _write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)


class RealAdmissionTests(unittest.TestCase):
    def setUp(self):
        self._root = WORK_ROOT / (self._testMethodName + "_" + str(os.getpid()))
        shutil.rmtree(self._root, ignore_errors=True)
        self._root.mkdir(parents=True, exist_ok=True)
        self._case_index = 0
        self.addCleanup(shutil.rmtree, self._root, True)

    def case(self, *, outcome="success", returncode=0, verdict=None,
             mesh=MESH, deck=DECK, polar=POLAR, history=HISTORY,
             audit_artifact_sha=None, audit_encoder=None, omit=()):
        self._case_index += 1
        root = str(self._root / ("case-" + str(self._case_index)))
        os.makedirs(root, exist_ok=True)
        paths = {"mesh": "case/mesh.vspgeom", "deck": "case/deck.vspaero",
                 "polar": "case/polar.polar", "history": "case/solver.history"}
        payloads = {"mesh": mesh, "deck": deck, "polar": polar, "history": history}
        for kind, payload in payloads.items():
            if kind not in omit:
                _write(os.path.join(root, *paths[kind].split("/")), payload)
        binding = ArtifactBinding(
            TASK.physics_sha256, canonical_sha(list(DESIGN)),
            TASK.geometry_contract_sha256, sha(mesh), sha(deck), sha(polar),
            10., 1., 10., 1000000., (0., 2., 4.))
        raw_files = tuple(ra.RawFile(kind, paths[kind], sha(payloads[kind]),
                                     len(payloads[kind]))
                          for kind in ("mesh", "deck", "polar", "history"))
        record = {
            "schema": ra.AUDIT_SCHEMA,
            "audit_id": "AUDIT-001",
            "run_id": "RUN-001",
            "task_id": TASK.task_id,
            "design_id": canonical_sha(list(DESIGN)),
            "geometry_sha256": TASK.geometry_contract_sha256,
            "artifact_sha256": audit_artifact_sha or ra.artifact_sha256(raw_files),
            "reviewer": "synthetic-independent-reviewer",
            "reviewer_role": "independent_reviewer",
            "verdict": verdict or ("ADMIT_REAL_LABEL" if outcome == "success"
                                   else "ADMIT_FAILED_RUN"),
            "created_utc": "2026-11-18T00:00:00Z",
        }
        audit_bytes = (audit_encoder(record) if audit_encoder
                       else json.dumps(record, sort_keys=True, indent=2).encode("utf-8"))
        audit_path = "audit/audit_record.json"
        if "audit" not in omit:
            _write(os.path.join(root, *audit_path.split("/")), audit_bytes)
        files = raw_files + (ra.RawFile("audit", audit_path, sha(audit_bytes),
                                        len(audit_bytes)),)
        manifest = ra.RealAdmissionManifest(
            admission_id="ADM-001", run_id="RUN-001", task_id=TASK.task_id,
            design_id=canonical_sha(list(DESIGN)), design=DESIGN,
            geometry_sha256=TASK.geometry_contract_sha256,
            evaluator_id="vspaero-3.55", solver_returncode=returncode,
            solver_started_utc="2026-11-18T00:00:00Z", outcome=outcome,
            partition="support", files=files, binding=binding,
            independent_audit_ref="AUDIT-001")
        return {"root": root, "manifest": manifest}

    def admit(self, case, **overrides):
        arguments = dict(manifest=case["manifest"], raw_root=case["root"],
                         task=TASK, design=DESIGN,
                         expected_evaluator_id="vspaero-3.55",
                         expected_audit_ref="AUDIT-001")
        arguments.update(overrides)
        return ra.admit_real_manifest(**arguments)

    def test_success_admission_mints_certificate_and_dataset_gate_passes(self):
        certificate = self.admit(self.case())
        self.assertEqual(certificate.status, "ok")
        self.assertEqual((certificate.alpha_deg, certificate.cl, certificate.cdi),
                         (2., .2, .02))
        self.assertEqual(certificate.di_n, 10.)
        self.assertEqual((certificate.q_pa, certificate.sref_m2), (50., 10.))
        self.assertEqual(certificate.evidence_scope, ra.EVIDENCE_SCOPE)
        data = MetaDataset.from_admitted_certificates(TASKS, (certificate,))
        self.assertIsNone(data.require_real_admission())
        self.assertEqual(data.rows[0].source_kind, "vspaero_raw")
        self.assertEqual(data.rows[0].raw_sha256, sha(POLAR))
        self.assertEqual(TrainNormalizer.fit(data).x_mean.shape, (12,))

    def test_failed_outcome_mints_null_label_and_gate_passes(self):
        certificate = self.admit(self.case(outcome="failed", returncode=1))
        self.assertEqual(certificate.status, "failed")
        self.assertIsNone(certificate.di_n)
        self.assertIsNone(certificate.cdi)
        data = MetaDataset.from_admitted_certificates(TASKS, (certificate,))
        self.assertIsNone(data.require_real_admission())
        self.assertEqual(data.rows[0].status, "failed")
        self.assertIsNone(data.rows[0].di_n)
        self.assertEqual(data.usable(TASK.task_id, "support"), ())

    def test_deleting_guard_alone_cannot_admit_declared_raw(self):
        declared = MetaDataset(TASKS, (Observation(
            "declared-real", TASK.task_id, DESIGN, "support", "vspaero_raw",
            "ok", 10., q_pa=50., sref_m2=10., cdi=.02, cl=.2,
            raw_sha256=sha(POLAR)),))
        with self.assertRaisesRegex(ContractError, "REAL_ADMISSION_NOT_IMPLEMENTED"):
            declared.require_real_admission()

    def test_missing_or_tampered_raw_bytes_rejected(self):
        missing = self.case(omit=("mesh",))
        with self.assertRaisesRegex(ContractError, "missing"):
            self.admit(missing)
        tampered = self.case()
        path = os.path.join(tampered["root"], "case", "mesh.vspgeom")
        _write(path, MESH[:-1] + b"X")
        with self.assertRaisesRegex(ContractError, "SHA256 mismatch"):
            self.admit(tampered)
        resized = self.case()
        path = os.path.join(resized["root"], "case", "deck.vspaero")
        with open(path, "ab") as handle:
            handle.write(b"\n")
        with self.assertRaisesRegex(ContractError, "size mismatch"):
            self.admit(resized)

    def test_manifest_paths_cannot_escape_root(self):
        for bad in ("../outside", "/absolute", "C:/windows/file", "case/../../escape"):
            with self.subTest(bad=bad), self.assertRaises(ContractError):
                ra.RawFile("mesh", bad, "f" * 64, 1)

    def test_link_escape_rejected_when_supported(self):
        import subprocess

        case = self.case()
        outside_dir = self._root / "outside_dir"
        outside_dir.mkdir(exist_ok=True)
        _write(os.path.join(outside_dir, "mesh.vspgeom"), MESH)
        link = Path(case["root"]) / "case" / "meshlink"
        created = False
        try:
            os.symlink(outside_dir, link, target_is_directory=True)
            created = True
        except (OSError, NotImplementedError):
            completed = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(outside_dir)],
                capture_output=True, text=True)
            created = completed.returncode == 0 and link.is_dir()
        if not created:
            self.skipTest("directory link creation is unavailable")
        files = tuple(
            replace(item, path="case/meshlink/mesh.vspgeom")
            if item.kind == "mesh" else item
            for item in case["manifest"].files)
        escaped = dict(case)
        escaped["manifest"] = replace(case["manifest"], files=files)
        with self.assertRaisesRegex(ContractError, "escapes raw_root"):
            self.admit(escaped)

    def test_task_design_geometry_and_trusted_expectations_checked(self):
        case = self.case()
        with self.assertRaisesRegex(ContractError, "design does not match"):
            self.admit(case, design=(1.,) + (0.,) * 11)
        with self.assertRaisesRegex(ContractError, "geometry does not match"):
            self.admit(case, task=replace(TASK, geometry_contract_sha256="b" * 64))
        with self.assertRaisesRegex(ContractError, "unexpected evaluator_id"):
            self.admit(case, expected_evaluator_id="other-evaluator")
        with self.assertRaisesRegex(ContractError, "unexpected independent audit"):
            self.admit(case, expected_audit_ref="OTHER-AUDIT")

    def test_infinite_ew_diagnostic_tolerated_but_nan_or_core_inf_fatal(self):
        certificate = self.admit(self.case(polar=POLAR_AUX))
        self.assertEqual((certificate.alpha_deg, certificate.cl, certificate.cdi),
                         (2., .2, .02))
        with self.assertRaisesRegex(ContractError, "nonfinite polar row"):
            self.admit(self.case(polar=POLAR_AUX.replace(
                b".2 .01 .02 .03 inf", b"nan .01 .02 .03 inf")))
        with self.assertRaisesRegex(ContractError, "nonfinite polar row"):
            self.admit(self.case(polar=POLAR_AUX.replace(
                b".2 .01 .02 .03 inf", b".2 .01 .02 .03 nan")))

    def test_missing_actual_lift_row_rejected_even_when_hashes_bind(self):
        polar = POLAR.replace(b".2 .01 .02", b".21 .01 .02")
        with self.assertRaisesRegex(ContractError, "no actual raw row"):
            self.admit(self.case(polar=polar))

    def test_audit_record_must_bind_same_artifact_identity(self):
        with self.assertRaisesRegex(ContractError, "does not match manifest"):
            self.admit(self.case(audit_artifact_sha="f" * 64))

    def test_audit_record_verdict_must_match_outcome(self):
        with self.assertRaisesRegex(ContractError, "verdict"):
            self.admit(self.case(verdict="ADMIT_FAILED_RUN"))

    def test_audit_record_duplicate_key_rejected(self):
        def duplicate(record):
            return b'{"schema": "duplicate", ' + json.dumps(record).encode("utf-8")[1:]
        with self.assertRaisesRegex(ContractError, "duplicate audit"):
            self.admit(self.case(audit_encoder=duplicate))

    def test_returncode_must_match_outcome(self):
        with self.assertRaisesRegex(ContractError, "successful outcome"):
            self.case(returncode=1)
        with self.assertRaisesRegex(ContractError, "failed outcome"):
            self.case(outcome="failed", returncode=0)

    def test_certificate_cannot_be_constructed_outside_issuer(self):
        certificate = self.admit(self.case())
        with self.assertRaisesRegex(ContractError, "issued by"):
            replace(certificate, _issuer=object())

    def test_dataset_rejects_certificate_label_or_coverage_mismatch(self):
        certificate = self.admit(self.case())
        with self.assertRaisesRegex(ContractError, "D_i_N"):
            replace(certificate, di_n=999.)
        data = MetaDataset.from_admitted_certificates(TASKS, (certificate,))
        with self.assertRaisesRegex(ContractError, "label mismatch"):
            MetaDataset(TASKS, (replace(data.rows[0], di_n=999.),),
                        admissions=(certificate,))
        extra = Observation("extra-real", TASK.task_id, (1.,) + (0.,) * 11,
                            "query", "vspaero_raw", "ok", 12.,
                            q_pa=50., sref_m2=10., cdi=.03, cl=.24,
                            raw_sha256=sha(POLAR))
        with self.assertRaisesRegex(ContractError, "exactly one admission certificate"):
            MetaDataset(TASKS, data.rows + (extra,), admissions=(certificate,))

    def test_gate_revalidates_after_rows_are_mutated(self):
        certificate = self.admit(self.case())
        data = MetaDataset.from_admitted_certificates(TASKS, (certificate,))
        data.rows = data.rows + (Observation(
            "injected", TASK.task_id, (1.,) + (0.,) * 11, "query",
            "vspaero_raw", "ok", 12., q_pa=50., sref_m2=10., cdi=.03,
            cl=.24, raw_sha256=sha(POLAR)),)
        with self.assertRaisesRegex(ContractError, "exactly one admission certificate"):
            data.require_real_admission()

    def test_bad_root_and_empty_trusted_strings_rejected(self):
        case = self.case()
        with self.assertRaisesRegex(ContractError, "existing directory"):
            self.admit(case, raw_root=str(self._root / "absent"))
        with self.assertRaisesRegex(ContractError, "expected_audit_ref"):
            self.admit(case, expected_audit_ref="  ")

    def test_manifest_rejects_unbound_or_duplicate_file_kinds(self):
        manifest = self.case()["manifest"]
        with self.assertRaisesRegex(ContractError, "exactly five"):
            replace(manifest, files=manifest.files[:-1])
        with self.assertRaisesRegex(ContractError, "does not match raw file"):
            replace(manifest, binding=replace(manifest.binding, mesh_sha256="f" * 64))
        with self.assertRaisesRegex(ContractError, "design_id"):
            replace(manifest, design_id="f" * 64)


if __name__ == "__main__":
    unittest.main()
