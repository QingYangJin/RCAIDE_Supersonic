"""Synthetic byte-only deck/constraint integration, never a physical run."""
from dataclasses import replace
import hashlib
import unittest
from research.concorde_metaopt.dreal001.meta.task_spec import TaskSpec, ContractError, canonical_sha
from research.concorde_metaopt.dreal001.meta.task_deck import ProposedFlow, render_task_deck
from research.concorde_metaopt.dreal001.meta.raw_verification import ArtifactBinding, verify_artifact_bundle

BASE = (b"# untouched\r\nSref = 1\r\nMach = 1\r\nCref = 1\r\nBeta = 1\r\n"
        b"Rho = 1\r\nVinf = 1\r\nReCref = 1\r\nAoA = 0\r\nBref = 9\r\nX_cg = 7")


class TaskDeckTests(unittest.TestCase):
    def setUp(self):
        self.task = TaskSpec("fixture", "train", 2., 1000., 50., 100., "a" * 64)
        self.flow = ProposedFlow(1000., 1., 10., 5., 1e-5, 2.)

    def render(self, task=None, flow=None, base=BASE, area=10., grid=(-2., 0., 2.)):
        return render_task_deck(base, task=self.task if task is None else task,
                                flow=self.flow if flow is None else flow,
                                sref_m2=area, alpha_grid_deg=grid)

    def test_flow_equations_and_serialized_fields(self):
        result = self.render()
        self.assertEqual(self.flow.q_pa, 50.)
        self.assertAlmostEqual(self.flow.recref, 2e6)
        self.assertIn(b"Mach = 2\r\n", result.deck)
        self.assertIn(b"Sref = 10\r\n", result.deck)
        self.assertIn(b"Cref = 2\r\n", result.deck)
        self.assertIn(b"Beta = 0\r\n", result.deck)
        self.assertEqual(result.constraints["cl_target"], .2)
        self.assertFalse(result.real_admission)

    def test_target_change_changes_constraints_and_cache_not_deck(self):
        a = self.render()
        b = self.render(task=replace(self.task, lift_target_n=110.))
        self.assertEqual(a.deck, b.deck)
        self.assertNotEqual(a.constraints, b.constraints)
        self.assertNotEqual(a.evaluation_contract_sha256, b.evaluation_contract_sha256)

    def test_id_or_split_only_change_does_not_create_physical_task(self):
        a = self.render()
        b = self.render(task=replace(self.task, task_id="renamed", split="test"))
        self.assertEqual(a.evaluation_contract_sha256, b.evaluation_contract_sha256)

    def test_mach_changes_actual_solver_fields(self):
        other = replace(self.flow, vinf_m_s=11.)
        a, b = self.render(), self.render(flow=other, task=replace(self.task, mach=2.2, dynamic_pressure_pa=60.5))
        self.assertNotEqual(a.deck_sha256, b.deck_sha256)
        self.assertIn(b"Vinf = 11\r\n", b.deck)
        self.assertNotEqual(a.flow.recref, b.flow.recref)

    def test_area_updates_deck_and_cl_but_not_lift_force(self):
        a, b = self.render(area=10.), self.render(area=20.)
        self.assertEqual(a.constraints["lift_target_n"], b.constraints["lift_target_n"])
        self.assertEqual(a.constraints["cl_target"], 2 * b.constraints["cl_target"])
        self.assertNotEqual(a.deck_sha256, b.deck_sha256)

    def test_untouched_lines_and_endings_preserved(self):
        result = self.render()
        self.assertTrue(result.deck.startswith(b"# untouched\r\n"))
        self.assertTrue(result.deck.endswith(b"Bref = 9\r\nX_cg = 7"))
        self.assertEqual(result.deck.count(b"\r\n"), BASE.count(b"\r\n"))
        self.assertEqual(BASE.count(b"Mach = 1"), 1)

    def test_missing_duplicate_invalid_text_rejected(self):
        for base in (BASE.replace(b"Mach = 1\r\n", b""), BASE + b"\nMach = 5", b"\xff", b""):
            with self.subTest(base=base):
                with self.assertRaises(ContractError):
                    self.render(base=base)

    def test_inconsistent_flow_rejected(self):
        for changes in ({"altitude_m": 999.}, {"sound_speed_m_s": 4.}, {"rho_kg_m3": 2.}):
            with self.assertRaisesRegex(ContractError, "task/flow"):
                self.render(flow=replace(self.flow, **changes))

    def test_nonfinite_nonpositive_flow_area_and_grid_rejected(self):
        for key in ("rho_kg_m3", "vinf_m_s", "sound_speed_m_s", "dynamic_viscosity_pa_s", "cref_m"):
            for value in (0., -1., float("nan"), True):
                with self.assertRaises(ContractError):
                    replace(self.flow, **{key: value})
        for area in (0., float("nan"), True):
            with self.assertRaises(ContractError):
                self.render(area=area)
        for grid in ((), (0., 0.), (float("nan"),), ("bad",)):
            with self.assertRaises(ContractError):
                self.render(grid=grid)

    def test_constraint_dictionary_mutation_does_not_change_binding(self):
        result = self.render()
        before = result.evaluation_contract_sha256
        external = result.constraints
        external["lift_target_n"] = 9.
        self.assertEqual(result.evaluation_contract_sha256, before)

    def test_renderer_to_raw_consistency_still_does_not_admit(self):
        result = self.render()
        mesh = b"SYNTHETIC_MESH_NOT_REAL"
        polar = b"Mach AoA Beta CL CDi CDtot\n2 -2 0 .1 .02 .03\n2 0 0 .2 .02 .03\n2 2 0 .3 .03 .04\n"
        sha = lambda data: hashlib.sha256(data).hexdigest()
        design = (0.,) * 12
        binding = ArtifactBinding(self.task.physics_sha256, canonical_sha(list(design)),
            self.task.geometry_contract_sha256, sha(mesh), result.deck_sha256, sha(polar),
            10., 1., 10., self.flow.recref, result.alpha_grid_deg)
        candidate = verify_artifact_bundle(task=self.task, design=design, binding=binding,
                                          mesh=mesh, deck=result.deck, polar=polar)
        self.assertAlmostEqual(candidate.di_n, 10.)
        self.assertFalse(candidate.real_admission)
        with self.assertRaisesRegex(ContractError, "binding mismatch"):
            verify_artifact_bundle(task=replace(self.task, lift_target_n=110.), design=design,
                                   binding=binding, mesh=mesh, deck=result.deck, polar=polar)


if __name__ == "__main__":
    unittest.main()
