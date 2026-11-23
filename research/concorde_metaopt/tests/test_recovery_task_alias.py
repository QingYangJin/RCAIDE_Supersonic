"""Explicit canonical-task aliasing for historical batches (synthetic bytes only).

These fixtures prove the alias mechanics: several historical certificate task_id
strings can be merged onto one canonical physical task only through an explicit
declared alias table, and a certificate can never be relabelled implicitly.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import unittest

from research.concorde_metaopt.dreal001.meta import real_admission as ra
from research.concorde_metaopt.dreal001.meta.meta_dataset import (
    MetaDataset, normalize_task_aliases)
from research.concorde_metaopt.dreal001.meta.raw_verification import ArtifactBinding
from research.concorde_metaopt.dreal001.meta.task_spec import (
    ContractError, TaskSpec, canonical_sha)

MESH = b"SYNTHETIC BYTES - NOT A REAL MESH"
def deck_bytes(task):
    # Minimal synthetic deck whose declared flow conditions match the binding.
    return (("Sref = 358.25\nMach = %r\nBeta = 0\nRho = %r\nVinf = 1.0\n"
             "ReCref = 1000000\nAoA = 0, 2, 4\n")
            % (task.mach, 2.0 * task.dynamic_pressure_pa)).encode("ascii")
def polar_bytes(task):
    # One raw row sits exactly at the declared lift target; the others bracket it.
    cl = task.lift_target_n / (task.dynamic_pressure_pa * 358.25)
    lines = [b"Beta Mach AoA Re/1e6 CLtot CDo CDi CDtot"]
    for alpha, scale in ((0.0, 0.999), (2.0, 1.0), (4.0, 1.001)):
        row_cl = cl * scale
        cdi = max(row_cl * 0.01, 0.001)
        lines.append(("%.6f %.6f %.6f 1 %.9f .010000 %.9f %.9f"
                      % (0.0, task.mach, alpha, row_cl, cdi, cdi + 0.01)).encode("ascii"))
    return b"\n".join(lines) + b"\n"
HISTORY = b"SYNTHETIC VSPAERO HISTORY - NOT A REAL SOLVER LOG\n"
GEOMETRY = "a" * 64
WORK_ROOT = Path(__file__).resolve().parent / "_task_alias_work"

CANONICAL = TaskSpec("P2-CANON-M140", "train", 2.02, 18288., 9839.359586688344,
                     1333704.4, GEOMETRY)
OLD_A = TaskSpec("DREAL003-G2-M140", "train", 2.02, 18288., 9839.359586688344,
                 1333704.4, GEOMETRY)
OLD_B = TaskSpec("concorde-real-M140", "train", 2.02, 18288., 9839.359586688344,
                 1333704.4, GEOMETRY)
CANONICAL_TRAIN2 = TaskSpec("P2-CANON-M160", "train", 2.02, 18288.,
                             12851.40843975621, 1333704.4, GEOMETRY)
CANONICAL_VAL = TaskSpec("P2-CANON-M180", "val", 2.02, 18288., 16265.063806566453,
                         1200000., GEOMETRY)
CANONICAL_TEST = TaskSpec("P2-CANON-M240", "test", 2.02, 18288., 28915.66898945147,
                          1100000., GEOMETRY)
FAMILY = (CANONICAL, CANONICAL_TRAIN2, CANONICAL_VAL, CANONICAL_TEST)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)


class TaskAliasTests(unittest.TestCase):
    def setUp(self):
        self._root = WORK_ROOT / (self._testMethodName + "_" + str(os.getpid()))
        shutil.rmtree(self._root, ignore_errors=True)
        self._root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(shutil.rmtree, self._root, True)
        self._index = 0

    def _mint(self, task, design):
        self._index += 1
        admission_id = "ADM-" + str(self._index)
        root = str(self._root / ("case-" + str(self._index)))
        paths = {"mesh": "case/mesh.vspgeom", "deck": "case/deck.vspaero",
                 "polar": "case/polar.polar", "history": "case/solver.history"}
        deck = deck_bytes(task)
        polar = polar_bytes(task)
        payloads = {"mesh": MESH, "deck": deck, "polar": polar, "history": HISTORY}
        for kind, payload in payloads.items():
            _write(os.path.join(root, *paths[kind].split("/")), payload)
        design = tuple(float(v) for v in design)
        binding = ArtifactBinding(
            task.physics_sha256, canonical_sha(list(design)), task.geometry_contract_sha256,
            sha(MESH), sha(deck), sha(polar), 358.25,
            2. * task.dynamic_pressure_pa, 1., 1000000., (0., 2., 4.))
        raw_files = tuple(ra.RawFile(kind, paths[kind], sha(payloads[kind]),
                                     len(payloads[kind]))
                          for kind in ("mesh", "deck", "polar", "history"))
        record = {
            "schema": ra.AUDIT_SCHEMA,
            "audit_id": "AUDIT-" + str(self._index),
            "run_id": "RUN-" + str(self._index),
            "task_id": task.task_id,
            "design_id": canonical_sha(list(design)),
            "geometry_sha256": task.geometry_contract_sha256,
            "artifact_sha256": ra.artifact_sha256(raw_files),
            "reviewer": "synthetic-independent-reviewer",
            "reviewer_role": "independent_reviewer",
            "verdict": "ADMIT_REAL_LABEL",
            "created_utc": "2026-11-18T00:00:00Z",
        }
        audit_bytes = json.dumps(record, sort_keys=True, indent=2).encode("utf-8")
        _write(os.path.join(root, "audit", "audit_record.json"), audit_bytes)
        files = raw_files + (ra.RawFile("audit", "audit/audit_record.json",
                                        sha(audit_bytes), len(audit_bytes)),)
        manifest = ra.RealAdmissionManifest(
            admission_id=admission_id, run_id=record["run_id"], task_id=task.task_id,
            design_id=canonical_sha(list(design)), design=design,
            geometry_sha256=task.geometry_contract_sha256,
            evaluator_id="vspaero-3.55", solver_returncode=0,
            solver_started_utc="2026-11-18T00:00:00Z", outcome="success",
            partition="support", files=files, binding=binding,
            independent_audit_ref=record["audit_id"])
        return ra.admit_real_manifest(manifest=manifest, raw_root=root, task=task,
                                      design=design, expected_evaluator_id="vspaero-3.55",
                                      expected_audit_ref=record["audit_id"])

    def test_alias_table_merges_historical_task_ids(self):
        certificates = (self._mint(OLD_A, (0.,) * 12),
                        self._mint(OLD_B, (1.,) + (0.,) * 11))
        aliases = {"P2-CANON-M140": ["DREAL003-G2-M140", "concorde-real-M140"]}
        data = MetaDataset.from_admitted_certificates(
            FAMILY, certificates, task_aliases=aliases)
        self.assertEqual([row.task_id for row in data.rows],
                         ["P2-CANON-M140", "P2-CANON-M140"])
        self.assertEqual([row.source_task_id for row in data.rows],
                         ["DREAL003-G2-M140", "concorde-real-M140"])
        self.assertIsNone(data.require_real_admission())
        self.assertEqual(len(data.usable("P2-CANON-M140", "support")), 2)

    def test_aliasing_is_never_implicit(self):
        certificate = self._mint(OLD_A, (0.,) * 12)
        with self.assertRaisesRegex(ContractError, "not in the task family"):
            MetaDataset.from_admitted_certificates(FAMILY, (certificate,))
        with self.assertRaisesRegex(ContractError, "not in the task family"):
            MetaDataset.from_admitted_certificates(
                FAMILY, (certificate,),
                task_aliases={"P2-CANON-M140": "concorde-real-M140"})

    def test_ambiguous_or_unknown_alias_rejected(self):
        with self.assertRaisesRegex(ContractError, "more than one canonical task"):
            normalize_task_aliases({"A": ["old"], "B": ["old"]})
        with self.assertRaisesRegex(ContractError, "unknown canonical task"):
            MetaDataset.from_admitted_certificates(
                FAMILY, (), task_aliases={"NOT-A-TASK": ["old"]})

    def test_alias_cannot_move_a_certificate_across_physics(self):
        certificate = self._mint(OLD_A, (0.,) * 12)
        other = TaskSpec("P2-CANON-M202", "train", 2.02, 18288., 20483.94,
                         1333704.4, GEOMETRY)
        other_family = (other, CANONICAL_TRAIN2, CANONICAL_VAL, CANONICAL_TEST)
        with self.assertRaisesRegex(ContractError, "q_pa disagrees"):
            MetaDataset.from_admitted_certificates(
                other_family, (certificate,),
                task_aliases={"P2-CANON-M202": ["DREAL003-G2-M140"]})
        wrong_geometry = TaskSpec("P2-CANON-M140", "train", 2.02, 18288.,
                                  9839.359586688344, 1333704.4, "b" * 64)
        wrong_family = (wrong_geometry, CANONICAL_TRAIN2, CANONICAL_VAL,
                        CANONICAL_TEST)
        with self.assertRaisesRegex(ContractError, "geometry disagrees"):
            MetaDataset.from_admitted_certificates(
                wrong_family, (certificate,),
                task_aliases={"P2-CANON-M140": ["DREAL003-G2-M140"]})


if __name__ == "__main__":
    unittest.main()
