"""A3 task-57 M0-R formal package tests (zero physical).

These tests read the frozen package produced by m0r_package.py.  They do not
start a solver and do not create a run dir.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
META = ROOT / "research" / "concorde_metaopt" / "dreal001" / "meta"
PKG = ROOT / "docs" / "evidence" / "dreal001" / "m0r_20261113"
FINAL_IDS = [
    "M0R-M202-CL017",
    "M0R-M202-CL019",
    "M0R-M220-CL017",
    "M0R-M220-CL019",
    "M0R-M180-CL017",
    "M0R-M180-CL019",
]


def read_json(name: str):
    return json.loads((PKG / name).read_text(encoding="utf-8"))


def sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


class M0RFormalPackageTests(unittest.TestCase):
    def test_validation_all_pass(self):
        doc = read_json("M0R_VALIDATION.json")
        self.assertEqual(doc["n_fail"], 0)
        self.assertEqual(doc["verdict"], "M0R_PACKAGE_FROZEN_PENDING_A5_GATE")
        self.assertTrue(all(c["status"] == "PASS" for c in doc["checks"]))
        self.assertEqual(doc["physical_call_count"], 0)

    def test_family_sha_new_and_recomputable(self):
        doc = read_json("M0R_TASK_SPECS.json")
        payload = doc["family_payload_sha256_input"]
        self.assertEqual(sha_text(canonical(payload)), doc["family_sha256"])
        self.assertEqual(len(doc["family_sha256"]), 64)
        self.assertFalse(doc["family_sha256"].startswith("ada424cc"))
        self.assertFalse(doc["family_sha256"].startswith("40fdd436"))

    def test_six_tasks_and_split(self):
        doc = read_json("M0R_TASK_SPECS.json")
        self.assertEqual([t["task_id"] for t in doc["tasks"]], FINAL_IDS)
        self.assertEqual(doc["splits"]["meta_train"], FINAL_IDS[:3])
        self.assertEqual(doc["splits"]["meta_val"], [FINAL_IDS[3]])
        self.assertEqual(doc["splits"]["meta_test_blind"], FINAL_IDS[4:])
        self.assertEqual(doc["n_fail"], 0)

    def test_task_contract_values(self):
        tasks = read_json("M0R_TASK_SPECS.json")["tasks"]
        expected_q = {
            "M0R-M202-CL017": 20483.940233430174,
            "M0R-M202-CL019": 20483.940233430174,
            "M0R-M220-CL017": 24297.194081414087,
            "M0R-M220-CL019": 24297.194081414087,
            "M0R-M180-CL017": 16265.063806566453,
            "M0R-M180-CL019": 16265.063806566453,
        }
        for task in tasks:
            self.assertAlmostEqual(task["q_pa"], expected_q[task["task_id"]], places=9)
            self.assertLessEqual(task["q_recompute_rel_error"], 1e-12)
            self.assertAlmostEqual(
                task["l_ref_n"], task["q_pa"] * task["sref_ref_m2"] * task["cl_target"],
                places=6)
            self.assertGreaterEqual(task["mass_t"], 100.0)
            self.assertLessEqual(task["mass_t"], 190.0)
            self.assertEqual(task["alpha_grid_deg"], [-2, 0, 2, 4, 6, 8, 10])
            self.assertEqual(task["max_refine_sweeps"], 0)
            self.assertEqual(task["active_mask"], "12D_ALL_ACTIVE")
            self.assertTrue(task["a1_task_id"])
            self.assertTrue(task["a1_interface_task_fingerprint"])

    def test_deck_freeze_uses_deck_and_vspgeom_identity(self):
        doc = read_json("M0R_DECK_FREEZE.json")
        self.assertEqual(doc["n_package_baseline_decks"], 6)
        self.assertEqual(doc["n_fail"], 0)
        for deck in doc["baseline_task_decks"]:
            path = PKG / deck["package_deck_path"]
            self.assertTrue(path.exists())
            data = path.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), deck["package_deck_sha256"])
            self.assertEqual(deck["package_deck_sha256"], deck["a1_deck_sha256"])
            self.assertEqual(deck["solver_input_sha256_role"],
                             "PATH_DEPENDENT_NOT_A_CROSS_PROCESS_EXPECTED")
            identity = deck["cross_process_deck_identity"]
            self.assertEqual(identity["deck_sha256"], deck["package_deck_sha256"])
            self.assertTrue(identity["vspgeom_sha256"].startswith("16da482a"))

    def test_deck_freeze_r3_semantics(self):
        doc = read_json("M0R_DECK_FREEZE.json")
        full = doc["full_family_deck_space"]
        self.assertEqual(len(full), 18)
        b0 = [e for e in full if e["design_id"] == "B0-01"]
        ref = doc["reference_design_decks_unfrozen_reference"]
        self.assertEqual(len(b0), 6)
        self.assertTrue(all(e["frozen_status"] == "FROZEN_IN_M0R_PACKAGE_BASELINE" for e in b0))
        self.assertEqual(len(ref), 12)
        self.assertEqual({e["design_id"] for e in ref}, {"B1-01", "C5"})
        self.assertTrue(all(e["frozen_status"] == "UNFROZEN_REFERENCE" for e in ref))
        m1a = doc["m1a_required_deck_set"]
        self.assertEqual(len(m1a), 12)
        self.assertEqual(sum(1 for e in m1a
                             if e["frozen_status"] == "FROZEN_IN_M0R_PACKAGE"), 4)
        self.assertEqual(sum(1 for e in m1a
                             if e["frozen_status"] == "TO_BE_FROZEN_BEFORE_M1A_AUTHORIZATION"), 8)
        self.assertEqual(len(doc["m3a_reference_deck_set"]), 4)
        boundary = doc["freeze_boundary"]
        self.assertEqual(boundary["full_family_deck_space_entries"], 18)
        self.assertEqual(boundary["baseline_decks_frozen"], 6)
        self.assertEqual(boundary["reference_design_deck_entries_unfrozen"], 12)
        self.assertEqual(boundary["m1a_required_deck_slots"], 12)
        self.assertEqual(boundary["m1a_baseline_slots_already_frozen"], 4)
        self.assertEqual(boundary["m1a_reference_slots_to_freeze_before_authorization"], 8)
        self.assertEqual(boundary["m3a_reference_slots_to_freeze_before_m3a"], 4)

    def test_deck_boundary_documented_in_readme_and_prereg(self):
        readme = (PKG / "README_ZH.md").read_text(encoding="utf-8")
        prereg = (PKG / "M0R_PREREGISTRATION_ZH.md").read_text(encoding="utf-8")
        self.assertIn("18", readme)
        self.assertIn("6 B0-01 baseline decks", readme)
        self.assertIn("8 B1-01/C5 slots", readme)
        self.assertIn("18 个条目", prereg)
        self.assertIn("12 个 B1-01/C5 reference 条目未冻结", prereg)
        self.assertIn("8 个 B1-01/C5 槽位", prereg)

    def test_a5_coverage_and_statuses(self):
        doc = read_json("M0R_A5_REQUIREMENTS_MAP.json")
        self.assertEqual(doc["coverage"]["requirements_mapped"], 30)
        self.assertEqual(doc["coverage"]["checklist_mapped"], 60)
        self.assertEqual(doc["coverage"]["gate_conditions_mapped"], 42)
        self.assertEqual(doc["n_fail"], 0)
        statuses = [r["pre_draft_status"] for r in doc["requirements_30"]]
        self.assertNotIn("PENDING_FINAL_PACKAGE", statuses)
        self.assertNotIn("EVIDENCED_IN_PREDRAFT", statuses)
        corrections = doc["a5_wording_corrections"]
        self.assertTrue(corrections["sref_runtime_is_only_source"])
        self.assertEqual(corrections["cross_process_deck_identity"],
                         "deck_sha256 + vspgeom_sha256")

    def test_zero_physical_and_no_authorization(self):
        zero = read_json("M0R_ZERO_PHYSICAL_EVIDENCE.json")
        self.assertEqual(zero["physical_call_count"], 0)
        self.assertFalse(zero["solver_started"])
        self.assertFalse(zero["run_dir_created"])
        pkg = read_json("M0R_PACKAGE.json")
        self.assertEqual(pkg["authorization_status"], "NOT_CREATED_M0R_ZERO_PHYSICAL")
        self.assertIsNone(pkg["run_dir"])
        self.assertIsNone(pkg["ledger"])
        self.assertIsNone(pkg["token"])
        self.assertIsNone(pkg["approval"])

    def test_sref_anchor_is_not_hardcoded_runtime_input(self):
        sref = read_json("M0R_SREF_PROVENANCE.json")
        self.assertEqual(sref["anchor_role"],
                         "VALIDATION_ANCHOR_ONLY_NOT_A_RUNTIME_HARDCODE")
        self.assertTrue(sref["runtime_recompute_required"])
        self.assertTrue(sref["runtime_binding"]["hardcode_forbidden"])
        binding = sref["runtime_binding"]
        recomputed = sha_text(canonical({
            "vspgeom_sha256": sref["independent_recompute"]["vspgeom_sha256"],
            "sref_m2": sref["independent_recompute"]["wing_area_m2"],
            "source": "post-fix baseline geometry.wing.area_m2 recomputed at runtime",
        }))
        self.assertEqual(binding["binding_sha256"], recomputed)
        tasks = read_json("M0R_TASK_SPECS.json")["tasks"]
        for task in tasks:
            self.assertEqual(task["sref_ref_role"],
                             "VALIDATION_ANCHOR_ONLY_NOT_A_RUNTIME_HARDCODE")
            self.assertTrue(task["runtime_sref_policy"]["runtime_recompute_required"])
            self.assertTrue(task["runtime_sref_policy"]["hardcode_forbidden"])

    def test_continuity_disclosure_is_not_byte_continuity(self):
        pkg = read_json("M0R_PACKAGE.json")
        self.assertFalse(pkg["continuity_disclosure"]["deck_byte_continuity"])
        self.assertFalse(pkg["continuity_disclosure"]["inherits_f1r2_expected_polar"])
        self.assertTrue(pkg["continuity_disclosure"]["m1a_rebuilds_admission_baseline"])
        self.assertIn("overstatement", pkg["continuity_disclosure"]["note"])

    def test_required_wording_present(self):
        text = (PKG / "M0R_PREREGISTRATION_ZH.md").read_text(encoding="utf-8")
        self.assertIn("SREF_REF 以 post-fix baseline 几何运行时重算值为唯一来源", text)
        self.assertIn("冻结常量仅作 1e-12 校验锚", text)
        self.assertIn("solver_input_sha256 含 path-dependent/random 的 .vkey", text)
        self.assertIn("确定性绑定只用 deck_sha256 + vspgeom_sha256", text)
        self.assertIn("M2.02 仅物理条件与 F1R2 逐位连续", text)
        self.assertIn("不继承 F1R2 expected polar", text)

    def test_a1_frozen_binding(self):
        doc = read_json("M0R_A1_INTERFACE_BINDING.json")
        self.assertEqual(doc["n_fail"], 0)
        self.assertEqual(doc["a1_sha256sums_entries"].__len__(), 7)
        self.assertEqual(doc["a1_sha256sums"]["sha256"],
                         "3ca22ec983f4c7f60360075564cf93d255fbcce2156181f0cdbdff07d4f5d302")
        self.assertEqual(doc["a1_code_commit"],
                         "0c514151d989de716dbb855973b900a34615b5aa")
        self.assertEqual(doc["a1_freeze_commit"],
                         "c5698a218fad974e8e96b604573c5cc79b3abb32")
        self.assertEqual(doc["a1_clarification"]["a5_status"],
                         "A5_ACCEPTED_AUTHORITATIVE")
        self.assertEqual(doc["a1_clarification"]["json"]["sha256"],
                         "7731e9c8b6269e50b343f7e2fbb9ade9c123e14bb33db7e0a884a922cc83e948")

    def test_generator_finalize_matches_frozen_package(self):
        sys.path.insert(0, str(META))
        module = importlib.import_module("m0r_package")
        pred = json.loads((PKG / "pre_draft" / "M0R_TASK_SPECS_PREDRAFT.json")
                          .read_text(encoding="utf-8"))
        regenerated = module.finalize_tasks(pred)
        frozen = read_json("M0R_TASK_SPECS.json")
        self.assertEqual(regenerated["family_sha256"], frozen["family_sha256"])
        self.assertEqual([t["task_fingerprint"] for t in regenerated["tasks"]],
                         [t["task_fingerprint"] for t in frozen["tasks"]])

    def test_validate_only_equivalent_in_process(self):
        sys.path.insert(0, str(META))
        module = importlib.import_module("m0r_package")
        docs = {
            "tasks": read_json("M0R_TASK_SPECS.json"),
            "decks": read_json("M0R_DECK_FREEZE.json"),
            "sref": read_json("M0R_SREF_PROVENANCE.json"),
            "design_space": read_json("M0R_DESIGN_SPACE_BINDING.json"),
            "split": read_json("M0R_SPLIT_LEAKAGE_AUDIT.json"),
            "budget": read_json("M0R_BUDGET_LEDGER.json"),
            "ctx": read_json("M0R_CTX_PLAN.json"),
            "stat": read_json("M0R_STAT_ENDPOINTS.json"),
            "a1": read_json("M0R_A1_INTERFACE_BINDING.json"),
            "a5": read_json("M0R_A5_REQUIREMENTS_MAP.json"),
            "zero": read_json("M0R_ZERO_PHYSICAL_EVIDENCE.json"),
            "package": read_json("M0R_PACKAGE.json"),
        }
        result = module.validate(docs)
        self.assertEqual(result["n_fail"], 0)
        self.assertEqual(result["verdict"], "M0R_PACKAGE_FROZEN_PENDING_A5_GATE")


if __name__ == "__main__":
    unittest.main()
