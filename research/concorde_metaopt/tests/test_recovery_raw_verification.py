"""Synthetic bytes exercise consistency checks, NEVER real label provenance."""
from dataclasses import replace
import hashlib
import unittest

from research.concorde_metaopt.dreal001.meta.raw_verification import (
    ArtifactBinding, verify_artifact_bundle)
from research.concorde_metaopt.dreal001.meta.task_spec import (
    ContractError, TaskSpec, canonical_sha)
from research.concorde_metaopt.tests.test_recovery_meta_contracts import fixture


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bundle():
    task = TaskSpec("fixture-raw", "train", 2.02, 18000., 50., 100., "a" * 64)
    design = (0.,) * 12
    mesh = b"SYNTHETIC BYTES - NOT A REAL MESH"
    deck = b"Sref = 10\nMach = 2.02\nBeta = 0\nRho = 1\nVinf = 10\nReCref = 1000000\nAoA = 0, 2, 4\n"
    polar = (b"Beta Mach AoA Re/1e6 CLtot CDo CDi CDtot\n"
             b"0 2.02 0 1 .1 .01 .01 .02\n"
             b"0 2.02 2 1 .2 .01 .02 .03\n"
             b"0 2.02 4 1 .3 .01 .04 .05\n")
    binding = ArtifactBinding(task.physics_sha256, canonical_sha(list(design)),
                              task.geometry_contract_sha256, sha(mesh), sha(deck), sha(polar),
                              10., 1., 10., 1000000., (0., 2., 4.))
    return dict(task=task, design=design, binding=binding, mesh=mesh, deck=deck, polar=polar)


def rebind(data, name, raw):
    data[name] = raw
    data["binding"] = replace(data["binding"], **{name + "_sha256": sha(raw)})
    return data


class RawVerificationTests(unittest.TestCase):
    def test_dimensionally_correct_observed_row_not_real_admission(self):
        r = verify_artifact_bundle(**bundle())
        self.assertEqual((r.alpha_deg, r.cl, r.cdi, r.di_n), (2., .2, .02, 10.))
        self.assertEqual((r.raw_row_count, r.unique_case_count), (3, 3))
        self.assertFalse(r.real_admission)
        self.assertEqual(r.evidence_scope, "OFFLINE_ARTIFACT_CONSISTENCY_ONLY")
        with self.assertRaisesRegex(ContractError, "REAL_ADMISSION_NOT_IMPLEMENTED"):
            fixture().require_real_admission()

    def test_hash_mismatch_each_artifact(self):
        for name in ("mesh", "deck", "polar"):
            d = bundle()
            d[name] += b"changed"
            with self.subTest(name=name), self.assertRaisesRegex(ContractError, "SHA256 mismatch"):
                verify_artifact_bundle(**d)

    def test_task_design_geometry_binding(self):
        for key in ("design_sha256", "task_physics_sha256", "geometry_contract_sha256"):
            d = bundle()
            d["binding"] = replace(d["binding"], **{key: "f" * 64})
            with self.subTest(key=key), self.assertRaisesRegex(ContractError, "binding mismatch"):
                verify_artifact_bundle(**d)

    def test_signed_zero_design_identity(self):
        d = bundle()
        d["design"] = (-0.,) * 12
        self.assertEqual(verify_artifact_bundle(**d).di_n, 10.)

    def test_deck_mach_sref_and_flow_changed_even_with_matching_hash(self):
        for old, new in ((b"Mach = 2.02", b"Mach = 2.2"), (b"Sref = 10", b"Sref = 11"),
                         (b"Vinf = 10", b"Vinf = 20"), (b"Rho = 1", b"Rho = 2"),
                         (b"ReCref = 1000000", b"ReCref = 2000000")):
            d = bundle()
            rebind(d, "deck", d["deck"].replace(old, new))
            with self.subTest(old=old), self.assertRaisesRegex(ContractError, "deck condition mismatch"):
                verify_artifact_bundle(**d)

    def test_task_q_must_equal_deck_rho_vinf(self):
        d = bundle()
        d["task"] = replace(d["task"], dynamic_pressure_pa=51.)
        d["binding"] = replace(d["binding"], task_physics_sha256=d["task"].physics_sha256)
        with self.assertRaisesRegex(ContractError, "dynamic pressure"):
            verify_artifact_bundle(**d)

    def test_duplicate_or_missing_deck_fields(self):
        for raw in (bundle()["deck"] + b"Mach = 2.02\n",
                    bundle()["deck"].replace(b"Mach = 2.02\n", b"")):
            with self.assertRaises(ContractError):
                verify_artifact_bundle(**rebind(bundle(), "deck", raw))

    def test_alpha_grid_mismatch(self):
        d = bundle()
        rebind(d, "deck", d["deck"].replace(b"0, 2, 4", b"0, 3, 4"))
        with self.assertRaisesRegex(ContractError, "alpha grid mismatch"):
            verify_artifact_bundle(**d)

    def test_polar_wrong_conditions_and_nonfinite_or_negative(self):
        for old, new in ((b"0 2.02 2", b"1 2.02 2"), (b"0 2.02 2", b"0 2.2 2"),
                         (b".2 .01 .02 .03", b".2 .01 NAN(IND) .03"),
                         (b".2 .01 .02 .03", b".2 .01 -.02 .03"),
                         (b".2 .01 .02 .03", b".2 .01 .04 .03")):
            d = bundle()
            rebind(d, "polar", d["polar"].replace(old, new))
            with self.subTest(new=new), self.assertRaises(ContractError):
                verify_artifact_bundle(**d)

    def test_missing_grid_row(self):
        d = bundle()
        rebind(d, "polar", d["polar"].replace(b"0 2.02 4 1 .3 .01 .04 .05\n", b""))
        with self.assertRaisesRegex(ContractError, "incomplete polar"):
            verify_artifact_bundle(**d)

    def test_identical_duplicate_rows_counted_not_hidden(self):
        d = bundle()
        rebind(d, "polar", d["polar"] + b"0 2.02 2 1 .2 .01 .02 .03\n")
        r = verify_artifact_bundle(**d)
        self.assertEqual((r.raw_row_count, r.unique_case_count), (4, 3))

    def test_conflicting_duplicate_rejected(self):
        d = bundle()
        rebind(d, "polar", d["polar"] + b"0 2.02 2 1 .2 .01 .03 .04\n")
        with self.assertRaisesRegex(ContractError, "conflicting duplicate"):
            verify_artifact_bundle(**d)

    def test_multiple_tables_rejected(self):
        d = bundle()
        rebind(d, "polar", d["polar"] + b"\n" + d["polar"])
        with self.assertRaisesRegex(ContractError, "ambiguous polar"):
            verify_artifact_bundle(**d)

    def test_no_interpolated_label_when_raw_rows_miss_lift(self):
        d = bundle()
        rebind(d, "polar", d["polar"].replace(b".2 .01 .02", b".21 .01 .02"))
        with self.assertRaisesRegex(ContractError, "no actual raw row"):
            verify_artifact_bundle(**d)

    def test_v6_cl_alias(self):
        d = bundle()
        rebind(d, "polar", d["polar"].replace(b"CLtot", b"CL"))
        self.assertEqual(verify_artifact_bundle(**d).di_n, 10.)

    def test_truncated_extra_and_unparsed_lines_rejected(self):
        for old, new in ((b".2 .01 .02 .03", b".2 .01 .02"),
                         (b".2 .01 .02 .03", b".2 .01 .02 .03 .99"),
                         (b".2 .01 .02 .03", b".2 garbage .02 .03")):
            d = bundle()
            rebind(d, "polar", d["polar"].replace(old, new))
            with self.subTest(new=new), self.assertRaisesRegex(ContractError, "malformed"):
                verify_artifact_bundle(**d)
        d = bundle()
        rebind(d, "polar", d["polar"] + b"unexpected trailing payload\n")
        with self.assertRaisesRegex(ContractError, "unparsed"):
            verify_artifact_bundle(**d)

    def test_v6_extra_column_finite_only(self):
        d = bundle()
        raw = d["polar"].replace(b"CLtot", b"CL")
        lines = raw.splitlines()
        raw = lines[0] + b"\n" + b"\n".join(line + b" 1" for line in lines[1:]) + b"\n"
        rebind(d, "polar", raw)
        self.assertEqual(verify_artifact_bundle(**d).di_n, 10.)
        rebind(d, "polar", raw.replace(b".03 1", b".03 nan"))
        with self.assertRaisesRegex(ContractError, "nonfinite"):
            verify_artifact_bundle(**d)

    def test_strict_utf8_and_invalid_hash(self):
        d = bundle()
        rebind(d, "deck", d["deck"] + b"\xff")
        with self.assertRaisesRegex(ContractError, "decode"):
            verify_artifact_bundle(**d)
        with self.assertRaisesRegex(ContractError, "SHA256"):
            replace(bundle()["binding"], mesh_sha256="claimed-pass")


if __name__ == "__main__":
    unittest.main()
