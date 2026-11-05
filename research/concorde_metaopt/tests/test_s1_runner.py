# -*- coding: utf-8 -*-
"""S1 五臂等预算 runner 的合同测试（零物理调用、零真实求解器）。"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from research.concorde_metaopt.meta_learning import family_v3 as fv3
from research.concorde_metaopt.meta_learning import m5_arms as m5
from research.concorde_metaopt.meta_learning import s1_runner as s1
from research.concorde_metaopt.meta_learning.offline_runner import (
    build_task_blocks,
    load_design_space_12d,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN = (
    REPO_ROOT
    / "research"
    / "concorde_metaopt"
    / "optimization_runs"
    / "p4ra-s0-2-freeze-20261105T072500Z"
)
FROZEN_V4 = (
    REPO_ROOT
    / "research"
    / "concorde_metaopt"
    / "optimization_runs"
    / "p4ra-s0-3-freeze-20261105T155925Z"
)

EXPECTED_FAMILY_FINGERPRINT = (
    "e56e6921be6b94e6611a24618a6e331cd7e4417597926d089d71b00da8c1c0c3"
)
EXPECTED_SPLIT_HASH = (
    "cd597d01bd4024d13c765a0a723449c3d67172bc260040012bea9d67d2af76ae"
)
EXPECTED_PREREG_DIGEST = (
    "6981f503fd6ea5a9fbe5de2d1825ae8993eb17e9fda5d2ff158e9248d88fd3df"
)
EXPECTED_ANALYSIS_PLAN_DIGEST = (
    "37eee53c9018fce34e414fa553ad3986a2d1be87d10409bc28e4f697b63588df"
)


def _identity(package):
    return s1.frozen_identity_for_run(package)


class FrozenPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = s1.load_frozen_package(FROZEN)
        cls.identity = _identity(cls.package)

    def test_identity_matches_contract(self):
        self.assertEqual(self.identity["family_version"], "p4ra-family-v3")
        self.assertEqual(self.identity["family_fingerprint"], EXPECTED_FAMILY_FINGERPRINT)
        self.assertEqual(self.identity["split_hash"], EXPECTED_SPLIT_HASH)
        self.assertEqual(self.identity["prereg_digest"], EXPECTED_PREREG_DIGEST)
        self.assertEqual(self.identity["analysis_plan_digest"], EXPECTED_ANALYSIS_PLAN_DIGEST)

    def test_legacy_v3_package_is_flagged_non_confirmatory(self):
        identity = self.package["identity"]
        self.assertTrue(self.package["legacy_frozen_package"])
        self.assertFalse(self.package["confirmatory_eligible"])
        self.assertTrue(identity["legacy_frozen_package"])
        self.assertFalse(identity["confirmatory_eligible"])
        self.assertEqual(identity["family_version"], "p4ra-family-v3")
        self.assertEqual(identity["task_family_version"], "p4ra-family-v3")
        self.assertIsNone(identity["holdout_seed"])
        self.assertEqual(identity["holdout_splits"], [])

    def test_split_counts_and_task_id_pattern(self):
        split = self.package["split"]
        self.assertEqual(dict(split["counts"]), dict(fv3.SPLIT_COUNTS))
        total = 0
        for split_name in fv3.SPLIT_ORDER:
            ids = list(split["task_ids"][split_name])
            self.assertEqual(len(ids), fv3.SPLIT_COUNTS[split_name])
            for task_id in ids:
                self.assertRegex(task_id, fv3.TASK_ID_PATTERN)
            total += len(ids)
        self.assertEqual(total, 120)
        self.assertEqual(len(self.package["tasks"]), 120)

    def test_radius_base_is_frozen_value(self):
        self.assertAlmostEqual(self.package["identity"]["radius_base"], 0.64, places=12)

    def _tampered_copy(self, tmp: Path, filename: str, mutate) -> Path:
        dest = tmp / "frozen"
        shutil.copytree(FROZEN, dest)
        target = dest / filename
        payload = json.loads(target.read_text(encoding="utf-8"))
        mutate(payload)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return dest

    def test_tampered_family_fingerprint_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            dest = self._tampered_copy(
                Path(raw),
                "frozen_family.json",
                lambda payload: payload.__setitem__("family_fingerprint", "0" * 64),
            )
            with self.assertRaises((s1.S1RunnerError, ValueError)):
                s1.load_frozen_package(dest)

    def test_tampered_endpoint_row_keys_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            dest = self._tampered_copy(
                Path(raw),
                "frozen_family.json",
                lambda payload: payload["endpoint_row_keys"].__setitem__(0, "bogus_key"),
            )
            with self.assertRaises((s1.S1RunnerError, ValueError)):
                s1.load_frozen_package(dest)

    def test_tampered_split_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            dest = self._tampered_copy(
                Path(raw),
                "meta_task_split.json",
                lambda payload: payload.__setitem__("split_hash", "0" * 64),
            )
            with self.assertRaises((s1.S1RunnerError, ValueError)):
                s1.load_frozen_package(dest)

    def test_tampered_prereg_digest_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            dest = self._tampered_copy(
                Path(raw),
                "preregistration.json",
                lambda payload: payload.__setitem__("prereg_digest", "0" * 64),
            )
            with self.assertRaises((s1.S1RunnerError, ValueError)):
                s1.load_frozen_package(dest)

    def test_tampered_primary_endpoint_alias_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            dest = self._tampered_copy(
                Path(raw),
                "preregistration.json",
                lambda payload: payload["primary_endpoints"].__setitem__(
                    0, "first_feasible_evaluation_index"
                ),
            )
            with self.assertRaises((s1.S1RunnerError, ValueError)):
                s1.load_frozen_package(dest)


class FrozenPackageV4Tests(unittest.TestCase):
    """R-V4-01/02：v4 冻结包（holdout 重播种）加载、身份字段与 run record 身份。"""

    @classmethod
    def setUpClass(cls):
        v3_records = json.loads((FROZEN / "tasks.json").read_text(encoding="utf-8"))
        cls.v3_fingerprints = tuple(record["task_fingerprint"] for record in v3_records)
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / "p4ra-s0-3-freeze-20261105T000000Z"
        root.mkdir(parents=True)
        legacy = {
            "task_ids": ["m2-deadbeef0001", "m5-deadbeef0002"],
            "task_fingerprints": [],
            "sources": [{"path": "<fixture>", "bytes": 0, "sha256": "f" * 64}],
        }
        bundle = fv3.build_freeze_bundle(
            run_id="p4ra-s0-3-freeze-20261105T000000Z",
            git_sha="3ebd777595bf747edc855be5fb583f51cc17352f",
            created_utc="2026-11-05T00:00:00+00:00",
            code_sha="unit-test-code-sha",
            legacy=legacy,
            radius_base=0.64,
            calibration_status="CALIBRATED",
            v3_reference_task_fingerprints=cls.v3_fingerprints,
        )
        fv3.write_json(root / "tasks.json", bundle["task_records"])
        fv3.write_json(root / "meta_task_split.json", bundle["split_manifest"])
        fv3.write_json(root / "frozen_family.json", bundle["frozen_family"])
        fv3.write_json(root / "preregistration.json", bundle["preregistration"])
        cls.bundle = bundle
        cls.root = root
        cls.package = s1.load_frozen_package(root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_v4_package_identity(self):
        identity = self.package["identity"]
        self.assertEqual(identity["family_version"], "p4ra-family-v4")
        self.assertEqual(identity["task_family_version"], "p4ra-family-v3")
        self.assertFalse(self.package["legacy_frozen_package"])
        self.assertTrue(self.package["confirmatory_eligible"])
        self.assertFalse(identity["legacy_frozen_package"])
        self.assertTrue(identity["confirmatory_eligible"])
        self.assertEqual(identity["holdout_seed"], 20261106)
        self.assertEqual(identity["holdout_splits"], {"meta_test": 20, "meta_test_ood": 10})
        self.assertEqual(identity["holdout_task_count"], 30)
        self.assertEqual(identity["evaluation_mode"], "confirmatory")
        self.assertEqual(identity["prereg_v4c_blocks_status"], "PRESENT")
        self.assertEqual(self.package["evaluation_mode"], "confirmatory")
        self.assertEqual(self.package["prereg_v4c_blocks_status"], "PRESENT")
        self.assertEqual(dict(identity["task_counts"]), dict(fv3.SPLIT_COUNTS))
        self.assertNotEqual(identity["family_fingerprint"], EXPECTED_FAMILY_FINGERPRINT)
        self.assertEqual(identity["split_hash"], EXPECTED_SPLIT_HASH)

    def test_v4c_require_confirmatory_accepts_package(self):
        package = s1.load_frozen_package(self.root, require_confirmatory=True)
        self.assertEqual(package["identity"]["evaluation_mode"], "confirmatory")

    def test_run_config_records_evaluation_mode(self):
        plan = s1.iter_run_plan(self.package, task_limit=1, meta_seeds=(0,), opt_seeds=(0,), arms=(m5.S1_RANDOM_BO,))
        config = s1.build_grid_run_config(self.package, run_id="p4ra-s0-3-freeze-20261105T000000Z", plan=plan)
        self.assertEqual(config["evaluation_mode"], "confirmatory")
        self.assertTrue(config["confirmatory_eligible"])

    def test_v4_run_record_carries_family_version_without_paths(self):
        task = next(task for task in self.package["tasks"] if task.split == "meta_train")
        record = s1.run_single(
            s1.RunContext(
                task=task,
                design_space=load_design_space_12d(),
                model_artifact=None,
                identity=s1.frozen_identity_for_run(self.package),
                run_id="p4ra-s0-3-unittest-run",
            ),
            arm=m5.S1_RANDOM_BO,
            budget=64,
            k_shot=0,
            meta_seed=0,
            opt_seed=0,
        )
        self.assertEqual(record["status"], "OK")
        self.assertEqual(record["family_version"], "p4ra-family-v4")
        self.assertEqual(record["family_fingerprint"], self.package["identity"]["family_fingerprint"])
        for forbidden in ("frozen_package", "raw_sha256", "frozen_run_id"):
            self.assertNotIn(forbidden, record)
        self.assertEqual(record["billable_evals"], 64)
        self.assertEqual(record["physics"]["physical_call_count"], 0)


class EndpointSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = s1.load_frozen_package(FROZEN)
        cls.task = cls.package["tasks_by_id"][cls.package["split"]["task_ids"]["meta_test"][0]]

    def test_endpoint_keys_match_frozen_contract(self):
        self.assertEqual(tuple(s1.ENDPOINT_KEYS), tuple(fv3.ENDPOINT_ROW_KEYS))
        self.assertEqual(tuple(s1.PRIMARY_ENDPOINTS), tuple(fv3.PRIMARY_ENDPOINTS))

    def test_alias_rejected_by_frozen_endpoint_normalizer(self):
        with self.assertRaises(ValueError):
            fv3.normalize_endpoints(("first_feasible_evaluation_index",))

    def test_null_semantics_without_any_feasible_point(self):
        result = SimpleNamespace(
            observations=[], best_feasible_value=None, first_feasible_eval_index=None
        )
        values = s1.compute_endpoint_values(result, self.task, budget=64, k_shot=0)
        self.assertIsNone(values["best_feasible_value"])
        self.assertIsNone(values["gap_to_reference"])
        self.assertIsNone(values["first_feasible_eval_index"])
        self.assertEqual(values["feasible_hit_rate"], 0.0)
        self.assertIsNone(values["first_feasible_in_support"])
        self.assertIsNone(values["first_feasible_after_support_index"])
        self.assertEqual(values["feasible_hit_rate_non_support"], 0.0)
        self.assertEqual(values["n_nonnull"], 1)
        self.assertAlmostEqual(values["null_rate"], 0.75, places=12)

    def test_first_feasible_support_and_after_semantics(self):
        feasible = SimpleNamespace(feasible=True)
        infeasible = SimpleNamespace(feasible=False)
        result = SimpleNamespace(
            observations=[infeasible, infeasible, feasible],
            best_feasible_value=0.5,
            first_feasible_eval_index=3,
        )
        in_support = s1.compute_endpoint_values(result, self.task, budget=64, k_shot=3)
        self.assertTrue(in_support["first_feasible_in_support"])
        self.assertIsNone(in_support["first_feasible_after_support_index"])
        after = s1.compute_endpoint_values(result, self.task, budget=64, k_shot=1)
        self.assertFalse(after["first_feasible_in_support"])
        self.assertEqual(after["first_feasible_after_support_index"], 2)
        self.assertAlmostEqual(after["feasible_hit_rate_non_support"], 1.0 / 63.0, places=12)
        reference = self.task.reference()["objective_star"]
        expected_gap = (0.5 - reference) / max(abs(reference), 1e-12)
        self.assertAlmostEqual(after["gap_to_reference"], expected_gap, places=12)


class BudgetFairnessTests(unittest.TestCase):
    def test_all_40_combinations_are_balanced(self):
        for arm in m5.S1_ARM_IDS:
            for k_shot in m5.S1_K_VALUES:
                for budget in m5.S1_BUDGETS:
                    plan = m5.s1_expected_budget(k_shot, budget)
                    self.assertEqual(plan["billable_evals"], budget)
                    self.assertEqual(plan["support_evals"], k_shot)
                    self.assertEqual(plan["initial_evals"], 8 - k_shot)
                    self.assertEqual(plan["bo_evals"], budget - 8)
                    self.assertEqual(
                        plan["support_evals"] + plan["initial_evals"] + plan["bo_evals"],
                        budget,
                    )
                    self.assertEqual(plan["initial_designs"], 8)

    def test_clone_check_skips_when_counterpart_absent(self):
        record = {
            "arm": "FOMAML-KSHOT-BO",
            "task_id": "p4ra-FQE3-v3-TE-000",
            "budget_B": 64,
            "K": 0,
            "meta_seed": 0,
            "opt_seed": 0,
        }
        check = s1.clone_pairs_check([record])
        self.assertEqual(check["status"], "NOT_APPLICABLE")
        self.assertEqual(len(check["skipped"]), 1)
        self.assertEqual(check["problems"], [])

    def test_invalid_k_or_budget_fails_closed(self):
        for bad_k in (-1, 2, 4):
            with self.assertRaises(m5.S1ArmError):
                m5.s1_expected_budget(bad_k, 64)
        for bad_budget in (32, 256):
            with self.assertRaises(m5.S1ArmError):
                m5.s1_expected_budget(0, bad_budget)

    def test_k0_fomaml_kshot_is_clone_and_excluded(self):
        cloned = m5.s1_identifiability("FOMAML-KSHOT-BO", 0)
        self.assertEqual(cloned["identifiability"], m5.S1_CLONE_IDENTIFIABILITY)
        self.assertEqual(cloned["clone_of"], "FOMAML-ZERO-BO")
        self.assertFalse(cloned["inference_eligible"])
        zero = m5.s1_identifiability("FOMAML-ZERO-BO", 0)
        self.assertEqual(zero["identifiability"], m5.S1_IDENTIFIABLE)
        self.assertTrue(zero["inference_eligible"])
        for k_shot in (1, 3, 5):
            entry = m5.s1_identifiability("FOMAML-KSHOT-BO", k_shot)
            self.assertEqual(entry["identifiability"], m5.S1_IDENTIFIABLE)
            self.assertTrue(entry["inference_eligible"])
            self.assertIsNone(entry["clone_of"])


class RunnerExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = s1.load_frozen_package(FROZEN)
        cls.design_space = load_design_space_12d()
        train_tasks = [task for task in cls.package["tasks"] if task.split == "meta_train"][:2]
        blocks = build_task_blocks(train_tasks)
        raw = m5.build_m5_model_artifacts(
            blocks, train_tasks, meta_seed=0, maml_steps=1, pretrain_steps=1
        )
        cls.bundle = {
            "schema_version": "p4ra-s1-model-artifacts-1",
            "meta_seed": 0,
            "target_names": list(raw["target_names"]),
            "pretrain": s1.serialize_model_artifact(raw["pretrain"]),
            "maml": s1.serialize_model_artifact(raw["maml"]),
            "artifacts_sha256": raw["artifacts_sha256"],
            "physical_call_count": 0,
        }
        cls.meta_task_id = cls.package["split"]["task_ids"]["meta_test"][0]
        cls.task = cls.package["tasks_by_id"][cls.meta_task_id]

    def _context(self, task=None):
        return s1.RunContext(
            task=task or self.task,
            design_space=self.design_space,
            model_artifact=self.bundle,
            identity=_identity(self.package),
            run_id="p4ra-s1-test",
        )

    def _run(self, arm, *, budget=64, k_shot=0, meta_seed=0, opt_seed=0):
        return s1.run_single(
            self._context(),
            arm=arm,
            budget=budget,
            k_shot=k_shot,
            meta_seed=meta_seed,
            opt_seed=opt_seed,
        )

    def test_random_bo_run_has_exact_budget_and_endpoints(self):
        record = self._run("RAND-BO")
        self.assertEqual(record["status"], "OK")
        self.assertEqual(record["billable_evals"], 64)
        self.assertEqual(record["support_evals"], 0)
        self.assertEqual(record["initial_evals"], 8)
        self.assertEqual(record["bo_evals"], 56)
        self.assertEqual(set(record["endpoint_values"]), set(s1.ENDPOINT_KEYS))
        self.assertEqual(record["identifiability"], "IDENTIFIABLE")
        self.assertTrue(record["inference_eligible"])
        self.assertEqual(record["physics"]["physical_call_count"], 0)
        self.assertEqual(record["physics"]["physics_guard"], "PASS")
        self.assertRegex(record["history_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(record["record_digest"], r"^[0-9a-f]{64}$")

    def test_model_k_shot_run_uses_support_cache(self):
        record = self._run("FOMAML-KSHOT-BO", k_shot=3)
        self.assertEqual(record["status"], "OK")
        self.assertEqual(record["support_evals"], 3)
        self.assertEqual(record["initial_evals"], 5)
        self.assertEqual(record["bo_evals"], 56)
        self.assertEqual(record["billable_evals"], 64)
        cost = record["cost"]
        self.assertIsNotNone(cost["proxy_scoring_cost"])
        self.assertEqual(cost["proxy_scoring_cost"]["model_scoring"]["adaptation_k_shot"], 3)
        self.assertIsNotNone(cost["adaptation_wall_s"])
        self.assertEqual(
            cost["proxy_scoring_cost"]["model_scoring"]["true_evaluation_budget_used"], 0
        )

    def test_k0_clone_records_are_equivalent(self):
        zero = self._run("FOMAML-ZERO-BO", k_shot=0)
        kshot = self._run("FOMAML-KSHOT-BO", k_shot=0)
        self.assertEqual(zero["status"], "OK")
        self.assertEqual(kshot["status"], "OK")
        self.assertFalse(kshot["inference_eligible"])
        self.assertEqual(kshot["clone_of"], "FOMAML-ZERO-BO")
        self.assertEqual(zero["history_digest"], kshot["history_digest"])
        check = s1.clone_pairs_check([zero, kshot])
        self.assertEqual(check["status"], "PASS", check["problems"])
        self.assertEqual(len(check["pairs"]), 1)
        self.assertTrue(check["pairs"][0]["core_equal_ignoring_arm"])

    def test_same_plan_is_deterministic(self):
        plan = [
            {
                "split": "meta_test",
                "task_id": self.meta_task_id,
                "arm": "RAND-BO",
                "budget_B": 64,
                "K": 0,
                "meta_seed": 0,
                "opt_seed": 0,
            },
            {
                "split": "meta_test",
                "task_id": self.meta_task_id,
                "arm": "FOMAML-KSHOT-BO",
                "budget_B": 64,
                "K": 3,
                "meta_seed": 0,
                "opt_seed": 0,
            },
        ]
        first = s1.execute_runs(
            self.package,
            run_id="p4ra-s1-det",
            plan=plan,
            bundles={0: self.bundle},
            design_space=self.design_space,
        )
        second = s1.execute_runs(
            self.package,
            run_id="p4ra-s1-det",
            plan=plan,
            bundles={0: self.bundle},
            design_space=self.design_space,
        )
        self.assertEqual(s1.compare_run_records(first, second), [])
        self.assertEqual(
            s1.digest([s1._record_core(record) for record in first]),
            s1.digest([s1._record_core(record) for record in second]),
        )

    def test_determinism_runner_writes_report(self):
        plan = [
            {
                "split": "meta_test",
                "task_id": self.meta_task_id,
                "arm": "RAND-BO",
                "budget_B": 64,
                "K": 0,
                "meta_seed": 0,
                "opt_seed": 0,
            }
        ]
        with tempfile.TemporaryDirectory() as raw:
            outdir = Path(raw) / "det"
            report = s1.run_determinism(
                self.package,
                outdir=outdir,
                run_id="p4ra-s1-det",
                plan=plan,
                bundles={0: self.bundle},
                repeats=2,
            )
            self.assertEqual(report["status"], "PASS", report["problems"])
            self.assertEqual(len(report["repeat_reports"]), 2)
            self.assertEqual(
                report["repeat_reports"][0]["records_core_sha256"],
                report["repeat_reports"][1]["records_core_sha256"],
            )
            self.assertTrue((outdir / "determinism_report.json").is_file())
            self.assertTrue((outdir / "repeat1" / "run_records.jsonl").is_file())

    def test_label_shuffle_diagnostic_runs(self):
        plan = [
            {
                "split": "meta_test",
                "task_id": self.meta_task_id,
                "arm": "FOMAML-KSHOT-BO",
                "budget_B": 64,
                "K": 3,
                "meta_seed": 0,
                "opt_seed": 0,
            }
        ]
        with tempfile.TemporaryDirectory() as raw:
            outdir = Path(raw) / "shuffle"
            report = s1.run_label_shuffle_diagnostic(
                self.package,
                outdir=outdir,
                run_id="p4ra-s1-shuffle",
                plan=plan,
                bundles={0: self.bundle},
            )
            self.assertEqual(report["status"], "PASS", report["problems"])
            self.assertTrue(report["diagnostic_only"])
            self.assertEqual(len(report["rows"]), 1)
            key = "FOMAML-KSHOT-BO|K3"
            self.assertIn(key, report["aggregates"])
            self.assertEqual(report["aggregates"][key]["expected"], "ADVANTAGE_SHRINKS")

    def test_label_shuffle_rejects_k_below_two(self):
        plan = [
            {
                "split": "meta_test",
                "task_id": self.meta_task_id,
                "arm": "FOMAML-KSHOT-BO",
                "budget_B": 64,
                "K": 1,
                "meta_seed": 0,
                "opt_seed": 0,
            }
        ]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(s1.S1RunnerError):
                s1.run_label_shuffle_diagnostic(
                    self.package,
                    outdir=Path(raw) / "shuffle",
                    run_id="p4ra-s1-shuffle",
                    plan=plan,
                    bundles={0: self.bundle},
                )

    def test_negative_control_has_no_reference_objective(self):
        negatives = [task for task in self.package["tasks"] if task.split == "negative_control"]
        self.assertEqual(len(negatives), 10)
        self.assertIsNone(s1._reference_objective(negatives[0]))


class PlanParsingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = s1.load_frozen_package(FROZEN)
        cls.parser = s1._build_parser()

    def test_plan_from_args_expands_grid(self):
        args = self.parser.parse_args(
            [
                "determinism",
                "--frozen",
                str(FROZEN),
                "--outdir",
                "unused",
                "--run-id",
                "p4ra-s1-plan",
                "--splits",
                "meta_test",
                "--arms",
                "RAND-BO",
                "--budgets",
                "64",
                "--k-values",
                "0,3",
                "--meta-seeds",
                "0",
                "--opt-seeds",
                "0",
                "--task-limit",
                "1",
            ]
        )
        plan = s1.plan_from_args(self.package, args)
        self.assertEqual(len(plan), 2)
        self.assertEqual([item["K"] for item in plan], [0, 3])
        self.assertTrue(all(item["arm"] == "RAND-BO" for item in plan))

    def test_plan_from_args_rejects_unknown_arm(self):
        args = self.parser.parse_args(
            [
                "run",
                "--frozen",
                str(FROZEN),
                "--outdir",
                "unused",
                "--run-id",
                "p4ra-s1-plan",
                "--arms",
                "NO-SUCH-ARM",
                "--task-limit",
                "1",
            ]
        )
        with self.assertRaises(s1.S1RunnerError):
            s1.plan_from_args(self.package, args)


class FormalGridTests(unittest.TestCase):
    """S1 正式分层网格 21,000：main 9,000 / secondary 6,000 / exploratory 6,000，排除 B=128xK=0。"""

    @classmethod
    def setUpClass(cls):
        cls.package = s1.load_frozen_package(FROZEN)

    def test_formal_grid_constants_and_pairs(self):
        self.assertEqual(s1.FORMAL_GRID_TOTAL_RUNS, 21000)
        self.assertEqual([stratum["name"] for stratum in s1.FORMAL_GRID_STRATA],
                         ["main", "secondary", "exploratory"])
        expected_runs = {stratum["name"]: int(stratum["expected_runs"])
                         for stratum in s1.FORMAL_GRID_STRATA}
        self.assertEqual(expected_runs, {"main": 9000, "secondary": 6000, "exploratory": 6000})
        self.assertEqual(sum(expected_runs.values()), 21000)
        pairs = s1.formal_grid_pairs()
        self.assertEqual(len(pairs), 7)
        self.assertIn((64, 0), pairs)
        self.assertIn((64, 3), pairs)
        self.assertIn((64, 5), pairs)
        self.assertIn((128, 3), pairs)
        self.assertIn((128, 5), pairs)
        self.assertIn((64, 1), pairs)
        self.assertIn((128, 1), pairs)
        self.assertNotIn((128, 0), pairs)
        expected_strata = {
            (64, 0): "main",
            (64, 3): "main",
            (64, 5): "main",
            (128, 3): "secondary",
            (128, 5): "secondary",
            (64, 1): "exploratory",
            (128, 1): "exploratory",
        }
        for pair, stratum in expected_strata.items():
            self.assertEqual(s1.formal_grid_stratum(*pair), stratum)
        with self.assertRaises(s1.S1RunnerError):
            s1.formal_grid_stratum(128, 0)

    def test_formal_default_plan_is_21000(self):
        plan = s1.iter_formal_run_plan(self.package)
        self.assertEqual(len(plan), 21000)
        counts = {stratum["name"]: 0 for stratum in s1.FORMAL_GRID_STRATA}
        for item in plan:
            self.assertEqual(item["grid_stratum"], s1.formal_grid_stratum(item["budget_B"], item["K"]))
            counts[item["grid_stratum"]] += 1
        self.assertEqual(counts, {"main": 9000, "secondary": 6000, "exploratory": 6000})
        self.assertFalse(any(int(item["budget_B"]) == 128 and int(item["K"]) == 0 for item in plan))

    def test_formal_default_plan_is_unique(self):
        plan = s1.iter_formal_run_plan(self.package)
        keys = {
            (item["split"], item["task_id"], item["arm"], int(item["budget_B"]),
             int(item["K"]), int(item["meta_seed"]), int(item["opt_seed"]))
            for item in plan
        }
        self.assertEqual(len(keys), len(plan))

    def test_formal_scaled_plan_consistency(self):
        plan = s1.iter_formal_run_plan(
            self.package, meta_seeds=(0,), opt_seeds=(0,), task_limit=1
        )
        self.assertEqual(len(plan), 35)  # 7 (B,K) x 5 arms x 1 x 1 x 1
        counts = {stratum["name"]: 0 for stratum in s1.FORMAL_GRID_STRATA}
        for item in plan:
            counts[item["grid_stratum"]] += 1
        self.assertEqual(counts, {"main": 15, "secondary": 10, "exploratory": 10})
        summary = s1.summarize_formal_grid(plan)
        self.assertEqual(summary["run_count"], 35)
        self.assertEqual(summary["b128_k0_count"], 0)
        self.assertEqual([row["actual_runs"] for row in summary["strata"]], [15, 10, 10])

    def test_formal_plan_negative_controls_fail_closed(self):
        with self.assertRaises(s1.S1RunnerError):
            s1.iter_formal_run_plan(self.package, task_limit=0)
        with self.assertRaises(s1.S1RunnerError):
            s1.iter_formal_run_plan(self.package, task_limit=-1)
        with self.assertRaises(s1.S1RunnerError):
            s1.iter_formal_run_plan(self.package, arms=())
        with self.assertRaises(s1.S1RunnerError):
            s1.iter_formal_run_plan(self.package, meta_seeds=())
        with self.assertRaises(s1.S1RunnerError):
            s1.iter_formal_run_plan(self.package, budgets=(128,), k_values=(0,))
        with self.assertRaises(s1.S1RunnerError):
            s1.iter_formal_run_plan(self.package, budgets=(64,), k_values=(3,))  # secondary 为空层
        with self.assertRaises(s1.S1RunnerError):
            s1.iter_formal_run_plan(self.package, budgets=(-64,))

    def test_cartesian_plan_still_24000(self):
        count = sum(1 for _ in s1.iter_run_plan(self.package))
        self.assertEqual(count, 24000)

    def test_plan_from_args_formal_mode(self):
        parser = s1._build_parser()
        args = parser.parse_args(
            [
                "run",
                "--frozen",
                str(FROZEN),
                "--outdir",
                "unused",
                "--run-id",
                "p4ra-s1-plan-formal",
                "--grid",
                "formal",
                "--splits",
                "meta_test",
                "--arms",
                "RAND-BO",
                "--budgets",
                "64",
                "--k-values",
                "0",
                "--meta-seeds",
                "0",
                "--opt-seeds",
                "0",
                "--task-limit",
                "1",
            ]
        )
        # budgets/K 过滤会令 secondary/exploratory 为空层 -> fail-closed
        with self.assertRaises(s1.S1RunnerError):
            s1.plan_from_args(self.package, args)
        args.grid = "cartesian"
        plan = s1.plan_from_args(self.package, args)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["arm"], "RAND-BO")
        args.grid = "bogus"
        with self.assertRaises(s1.S1RunnerError):
            s1.plan_from_args(self.package, args)

    def test_build_grid_run_config_formal(self):
        plan = s1.iter_formal_run_plan(self.package, meta_seeds=(0,), opt_seeds=(0,), task_limit=1)
        config = s1.build_grid_run_config(
            self.package, run_id="p4ra-s1-formal-config", plan=plan, grid_mode="formal"
        )
        self.assertEqual(config["grid_mode"], "formal")
        self.assertEqual(config["run_count"], 35)
        self.assertEqual(config["record_count"], 35)
        self.assertEqual(len(config["grid_strata"]), 3)
        self.assertEqual(
            [row["name"] for row in config["grid_strata"]],
            ["main", "secondary", "exploratory"],
        )
        self.assertEqual(
            [row["expected_runs"] for row in config["grid_strata"]], [9000, 6000, 6000]
        )
        self.assertEqual(
            [row["actual_runs"] for row in config["grid_strata"]], [15, 10, 10]
        )
        for row in config["grid_strata"]:
            for key in ("name", "budgets", "k_values", "expected_runs", "actual_runs"):
                self.assertIn(key, row)
        cartesian = s1.build_grid_run_config(
            self.package, run_id="p4ra-s1-cartesian-config", plan=plan[:5]
        )
        self.assertEqual(cartesian["grid_mode"], "cartesian")
        self.assertEqual(cartesian["grid_strata"], [])
        with self.assertRaises(s1.S1RunnerError):
            s1.build_grid_run_config(
                self.package, run_id="p4ra-s1-bad-config", plan=plan[:5], grid_mode="bogus"
            )

    def test_grid_cli_formal_output(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = s1._main(
                ["grid", "--frozen", str(FROZEN), "--grid", "formal", "--allow-legacy"]
            )
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["grid_mode"], "formal")
        self.assertEqual(payload["run_count"], 21000)
        self.assertEqual(payload["b128_k0_count"], 0)
        self.assertEqual(
            [(row["name"], row["actual_runs"]) for row in payload["strata"]],
            [("main", 9000), ("secondary", 6000), ("exploratory", 6000)],
        )
        self.assertEqual(payload["identity"]["family_fingerprint"], EXPECTED_FAMILY_FINGERPRINT)

    def test_grid_cli_cartesian_output(self):
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = s1._main(["grid", "--frozen", str(FROZEN), "--allow-legacy"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["grid_mode"], "cartesian")
        self.assertEqual(payload["run_count"], 24000)
        self.assertEqual(payload["strata"], [])

class GridStratumRecordTests(unittest.TestCase):
    """run_records.jsonl 的 grid_stratum 字段（task-223：执行计划 §4 一致性补丁）。"""

    @classmethod
    def setUpClass(cls):
        cls.package = s1.load_frozen_package(FROZEN)
        cls.design_space = load_design_space_12d()
        cls.meta_task_id = cls.package["split"]["task_ids"]["meta_test"][0]

    def _formal_plan_all(self, task_limit=1):
        # 允许全部 7 个 (B,K) 分层组合，避免过滤后任一分层为空触发 fail-closed。
        return s1.iter_formal_run_plan(
            self.package,
            splits=("meta_test",),
            arms=("RAND-BO",),
            meta_seeds=(0,),
            opt_seeds=(0,),
            task_limit=task_limit,
        )

    def _execute(self, plan, run_id="p4ra-s1-stratum"):
        return s1.execute_runs(
            self.package, run_id=run_id, plan=plan, design_space=self.design_space
        )

    def _context(self):
        return s1.RunContext(
            task=self.package["tasks_by_id"][self.meta_task_id],
            design_space=self.design_space,
            model_artifact=None,
            identity=_identity(self.package),
            run_id="p4ra-s1-stratum",
        )

    def test_formal_records_carry_matching_stratum(self):
        plan = self._formal_plan_all()
        self.assertEqual(len(plan), 7)
        by_stratum = {}
        for item in plan:
            by_stratum.setdefault(item["grid_stratum"], []).append(item)
        self.assertEqual(sorted(by_stratum), ["exploratory", "main", "secondary"])
        self.assertEqual(len(by_stratum["main"]), 3)
        self.assertEqual(len(by_stratum["secondary"]), 2)
        self.assertEqual(len(by_stratum["exploratory"]), 2)
        for stratum, items in by_stratum.items():
            item = items[0]
            self.assertEqual(
                s1.formal_grid_stratum(int(item["budget_B"]), int(item["K"])), stratum
            )
            records = self._execute([item])
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertEqual(record["status"], "OK")
            self.assertEqual(record["grid_stratum"], stratum)
            self.assertEqual(record["billable_evals"], int(item["budget_B"]))

    def test_cartesian_records_have_null_stratum(self):
        plan = list(
            s1.iter_run_plan(
                self.package,
                splits=("meta_test",),
                arms=("RAND-BO",),
                budgets=(64,),
                k_values=(0,),
                meta_seeds=(0,),
                opt_seeds=(0,),
                task_limit=1,
            )
        )
        self.assertEqual(len(plan), 1)
        self.assertNotIn("grid_stratum", plan[0])
        records = self._execute(plan)
        self.assertIsNone(records[0]["grid_stratum"])

    def test_explicit_none_stratum_allowed(self):
        plan = [
            {
                "split": "meta_test",
                "task_id": self.meta_task_id,
                "arm": "RAND-BO",
                "budget_B": 64,
                "K": 0,
                "meta_seed": 0,
                "opt_seed": 0,
                "grid_stratum": None,
            }
        ]
        records = self._execute(plan)
        self.assertIsNone(records[0]["grid_stratum"])

    def test_invalid_grid_stratum_fails_closed(self):
        with self.assertRaises(s1.S1RunnerError):
            s1.validate_grid_stratum("bogus", budget=64, k_shot=0)
        with self.assertRaises(s1.S1RunnerError):
            s1.validate_grid_stratum("secondary", budget=64, k_shot=0)
        with self.assertRaises(s1.S1RunnerError):
            s1.validate_grid_stratum("main", budget=128, k_shot=0)
        with self.assertRaises(s1.S1RunnerError):
            s1.validate_grid_stratum(64, budget=64, k_shot=0)

    def test_run_single_rejects_mismatched_stratum(self):
        with self.assertRaises(s1.S1RunnerError):
            s1.run_single(
                self._context(),
                arm="RAND-BO",
                budget=64,
                k_shot=0,
                meta_seed=0,
                opt_seed=0,
                grid_stratum="secondary",
            )

    def test_execute_runs_rejects_bad_plan_stratum(self):
        plan = [
            {
                "split": "meta_test",
                "task_id": self.meta_task_id,
                "arm": "RAND-BO",
                "budget_B": 64,
                "K": 0,
                "meta_seed": 0,
                "opt_seed": 0,
                "grid_stratum": "bogus",
            }
        ]
        with self.assertRaises(s1.S1RunnerError):
            self._execute(plan)

    def test_formal_forbids_b128_k0(self):
        with self.assertRaises(s1.S1RunnerError):
            s1.iter_formal_run_plan(
                self.package,
                splits=("meta_test",),
                arms=("RAND-BO",),
                budgets=(128,),
                k_values=(0,),
                meta_seeds=(0,),
                opt_seeds=(0,),
                task_limit=1,
            )

    def test_core_and_record_digest_include_stratum(self):
        context = self._context()
        formal = s1.run_single(
            context,
            arm="RAND-BO",
            budget=64,
            k_shot=0,
            meta_seed=0,
            opt_seed=0,
            grid_stratum="main",
        )
        cartesian = s1.run_single(
            context,
            arm="RAND-BO",
            budget=64,
            k_shot=0,
            meta_seed=0,
            opt_seed=0,
        )
        self.assertEqual(formal["status"], "OK")
        self.assertEqual(cartesian["status"], "OK")
        self.assertEqual(s1._record_core(formal)["grid_stratum"], "main")
        self.assertIsNone(s1._record_core(cartesian)["grid_stratum"])
        self.assertNotEqual(
            s1.digest(s1._record_core(formal)), s1.digest(s1._record_core(cartesian))
        )
        self.assertNotEqual(formal["record_digest"], cartesian["record_digest"])

    def test_formal_plan_runs_are_deterministic_with_stratum(self):
        plan = [item for item in self._formal_plan_all() if item["grid_stratum"] == "main"]
        self.assertEqual(len(plan), 3)
        first = self._execute(plan, run_id="p4ra-s1-stratum-det")
        second = self._execute(plan, run_id="p4ra-s1-stratum-det")
        self.assertEqual(s1.compare_run_records(first, second), [])
        self.assertEqual(first[0]["grid_stratum"], "main")
        self.assertEqual(
            s1.digest([s1._record_core(record) for record in first]),
            s1.digest([s1._record_core(record) for record in second]),
        )


class ArmSemanticsB03Tests(unittest.TestCase):
    """S1-B03 修复：FOMAML-ZERO-BO 任意 K 均不适配；K-shots 臂语义与可辨识性证据。"""

    @classmethod
    def setUpClass(cls):
        cls.package = s1.load_frozen_package(FROZEN)
        cls.design_space = load_design_space_12d()
        train_tasks = [task for task in cls.package["tasks"] if task.split == "meta_train"][:2]
        blocks = build_task_blocks(train_tasks)
        raw = m5.build_m5_model_artifacts(
            blocks, train_tasks, meta_seed=0, maml_steps=1, pretrain_steps=1
        )
        cls.bundle = {
            "schema_version": "p4ra-s1-model-artifacts-1",
            "meta_seed": 0,
            "target_names": list(raw["target_names"]),
            "pretrain": s1.serialize_model_artifact(raw["pretrain"]),
            "maml": s1.serialize_model_artifact(raw["maml"]),
            "artifacts_sha256": raw["artifacts_sha256"],
            "physical_call_count": 0,
        }
        meta_test_ids = list(cls.package["split"]["task_ids"]["meta_test"])
        cls.task = cls.package["tasks_by_id"][meta_test_ids[0]]
        cls.te003 = cls.package["tasks_by_id"][meta_test_ids[3]]

    def _support(self, task, k_shot=5, meta_seed=0):
        support = s1.select_support_designs(task, k_shot=k_shot, meta_seed=meta_seed)
        if k_shot == 0:
            return support, None, None
        features, targets = m5._s1_support_xy(task, support)
        return support, features, targets

    def _initial(self, task, arm, k_shot=5, targets=None, features=None):
        support, sf, st = self._support(task, k_shot=k_shot)
        if features is not None:
            sf = features
        if targets is not None:
            st = targets
        return m5.s1_new_initial_designs(
            arm,
            task,
            seed=0,
            k_shot=k_shot,
            design_space=self.design_space,
            model_artifact=s1.artifact_for_arm(self.bundle, arm),
            support_features=sf,
            support_targets=st,
        )

    def _context(self, task):
        return s1.RunContext(
            task=task,
            design_space=self.design_space,
            model_artifact=self.bundle,
            identity=_identity(self.package),
            run_id="p4ra-s1-b03-test",
        )

    def test_zero_shot_never_adapts_for_any_k(self):
        artifact = s1.artifact_for_arm(self.bundle, m5.S1_FOMAML_ZERO_BO)
        for k_shot in (1, 3, 5):
            initial = self._initial(self.te003, m5.S1_FOMAML_ZERO_BO, k_shot=k_shot)
            cost = initial["proxy_scoring_cost"]
            self.assertEqual(initial["method"], "none")
            self.assertEqual(cost["adaptation_k_shot"], 0)
            self.assertEqual(cost["method"], "none")
            plan = m5.s1_expected_budget(k_shot, 64)
            baseline = m5.score_m5_init_designs(
                artifact,
                self.design_space,
                self.te003,
                seed=0,
                method="none",
                k_shot=0,
                initial_design_count=int(plan["initial_evals"]),
            )
            self.assertEqual(
                m5.designs_digest(initial["designs"]),
                m5.designs_digest(baseline["designs"]),
            )

    def test_k_shot_arms_adapt_with_expected_method(self):
        kshot = self._initial(self.te003, m5.S1_FOMAML_KSHOT_BO)
        self.assertEqual(kshot["method"], "maml")
        self.assertEqual(kshot["proxy_scoring_cost"]["adaptation_k_shot"], 5)
        pretrain = self._initial(self.te003, m5.S1_PRETRAIN_KSHOT_BO)
        self.assertEqual(pretrain["method"], "fine_tuning")
        self.assertEqual(pretrain["proxy_scoring_cost"]["adaptation_k_shot"], 5)
        zero_k0 = self._initial(self.te003, m5.S1_FOMAML_ZERO_BO, k_shot=0)
        kshot_k0 = self._initial(self.te003, m5.S1_FOMAML_KSHOT_BO, k_shot=0)
        self.assertEqual(zero_k0["method"], "none")
        self.assertEqual(kshot_k0["method"], "none")
        self.assertEqual(
            m5.designs_digest(zero_k0["designs"]), m5.designs_digest(kshot_k0["designs"])
        )

    def test_zero_and_k_shot_differ_on_distinguishable_task(self):
        zero = self._initial(self.te003, m5.S1_FOMAML_ZERO_BO)
        kshot = self._initial(self.te003, m5.S1_FOMAML_KSHOT_BO)
        pretrain = self._initial(self.te003, m5.S1_PRETRAIN_KSHOT_BO)
        self.assertNotEqual(
            m5.designs_digest(zero["designs"]), m5.designs_digest(kshot["designs"])
        )
        self.assertNotEqual(
            m5.designs_digest(kshot["designs"]), m5.designs_digest(pretrain["designs"])
        )

    def test_label_permutation_changes_k_shot_predictions_only(self):
        support, sf, st = self._support(self.te003)
        permutation = np.array([1, 0, 2, 3, 4])
        from research.concorde_metaopt.meta_learning.baseline_arms import (
            derive_arm_seed,
            generate_initial_designs,
            predict_proxy_targets,
        )
        from research.concorde_metaopt.meta_learning.data_contract import CONTEXT_NAMES
        from research.concorde_metaopt.meta_learning.surrogate import encode_features

        candidates = generate_initial_designs(
            np.zeros(12), np.ones(12), 128,
            seed=derive_arm_seed(str(self.te003.task_id), 0, "label_probe"),
            method="lhs",
        )
        features = encode_features(candidates, dict(self.te003.context), tuple(CONTEXT_NAMES))
        artifact = self.bundle["maml"]["artifact"]
        plain = predict_proxy_targets(
            artifact, features, method="maml", support_features=sf,
            support_targets=st, k_shot=5,
        )
        permuted = predict_proxy_targets(
            artifact, features, method="maml", support_features=sf,
            support_targets=st[permutation], k_shot=5,
        )
        self.assertGreater(float(np.max(np.abs(plain - permuted))), 0.0)

    def test_zero_shot_initial_designs_ignore_permuted_labels(self):
        support, sf, st = self._support(self.te003)
        permutation = np.array([1, 0, 2, 3, 4])
        plain = self._initial(self.te003, m5.S1_FOMAML_ZERO_BO, features=sf, targets=st)
        permuted = self._initial(
            self.te003, m5.S1_FOMAML_ZERO_BO, features=sf, targets=st[permutation]
        )
        self.assertEqual(
            m5.designs_digest(plain["designs"]), m5.designs_digest(permuted["designs"])
        )

    def _run(self, task, arm, *, budget=64, k_shot=5, permutation=None):
        return s1.run_single(
            self._context(task),
            arm=arm,
            budget=budget,
            k_shot=k_shot,
            meta_seed=0,
            opt_seed=0,
            support_label_permutation=permutation,
        )

    def test_record_carries_initial_design_evidence_and_budget(self):
        record = self._run(self.te003, m5.S1_FOMAML_ZERO_BO)
        self.assertEqual(record["status"], "OK")
        self.assertEqual(record["billable_evals"], 64)
        self.assertEqual(record["support_evals"], 5)
        self.assertEqual(record["initial_evals"], 3)
        self.assertEqual(record["bo_evals"], 56)
        self.assertRegex(record["initial_designs_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(record["initial_design_row_digests"]), 3)
        self.assertEqual(record["physics"]["physical_call_count"], 0)

    def test_zero_shot_label_shuffle_has_no_effect(self):
        plain = self._run(self.te003, m5.S1_FOMAML_ZERO_BO)
        shuffled = self._run(
            self.te003, m5.S1_FOMAML_ZERO_BO, permutation=[1, 0, 2, 3, 4]
        )
        self.assertEqual(plain["history_digest"], shuffled["history_digest"])
        self.assertEqual(plain["initial_designs_sha256"], shuffled["initial_designs_sha256"])
        self.assertEqual(plain["billable_evals"], shuffled["billable_evals"])

    def test_identifiability_report_marks_identifiable_group(self):
        records = [
            self._run(self.te003, arm)
            for arm in (
                m5.S1_PRETRAIN_KSHOT_BO,
                m5.S1_FOMAML_ZERO_BO,
                m5.S1_FOMAML_KSHOT_BO,
            )
        ]
        report = s1.ranking_identifiability_report(records)
        self.assertEqual(report["schema_version"], s1.IDENTIFIABILITY_SCHEMA_VERSION)
        self.assertEqual(report["threshold"], 0.90)
        self.assertEqual(report["group_count"], 1)
        group = report["groups"][0]
        self.assertEqual(group["task_id"], self.te003.task_id)
        self.assertEqual(group["ranking_status"], "IDENTIFIABLE")
        self.assertTrue(group["inference_allowed"])
        for pair in s1.IDENTIFIABILITY_REQUIRED_PAIRS:
            key = f"{pair[0]}|{pair[1]}"
            self.assertIn(key, report["pair_coverage"])
            self.assertEqual(report["pair_coverage"][key], 1)
        self.assertEqual(
            set(report["pair_status_counts"]),
            {f"{left}|{right}" for left, right in s1.IDENTIFIABILITY_REQUIRED_PAIRS},
        )
        for pair in group["pairwise"]:
            self.assertEqual(pair["threshold"], 0.90)
            self.assertIsInstance(pair["pair_identifiable"], bool)
            self.assertIn(
                pair["structural_status"], ("IDENTIFIABLE", "STRUCTURALLY_IDENTICAL")
            )
            self.assertEqual(
                pair["pair_identifiable"], pair["structural_status"] == "IDENTIFIABLE"
            )
        c5 = next(
            item
            for item in group["pairwise"]
            if {item["arm_a"], item["arm_b"]}
            == {m5.S1_FOMAML_ZERO_BO, m5.S1_FOMAML_KSHOT_BO}
        )
        self.assertTrue(c5["pair_identifiable"])
        self.assertEqual(c5["structural_status"], "IDENTIFIABLE")

    def test_identifiability_report_flags_indistinguishable_rows(self):
        rows = ["a" * 64, "a" * 64, "a" * 64]
        base = {
            "task_id": "p4ra-FQE3-v3-TE-000",
            "budget_B": 64,
            "K": 5,
            "meta_seed": 0,
            "initial_designs_sha256": "d" * 64,
        }
        records = []
        for arm, row in zip(m5.S1_MODEL_SCORED_ARMS, rows):
            records.append(dict(base, arm=arm, initial_design_row_digests=[row, row, row]))
        report = s1.ranking_identifiability_report(records)
        group = report["groups"][0]
        self.assertEqual(group["ranking_status"], "RANKING_INDISTINGUISHABLE")
        self.assertFalse(group["inference_allowed"])
        self.assertEqual(group["max_overlap_rate"], 1.0)
        self.assertEqual(report["status_counts"], {"RANKING_INDISTINGUISHABLE": 1})
        for pair in group["pairwise"]:
            self.assertFalse(pair["pair_identifiable"])
            self.assertEqual(pair["structural_status"], "STRUCTURALLY_IDENTICAL")
        for counts in report["pair_status_counts"].values():
            self.assertEqual(counts["IDENTIFIABLE"], 0)
            self.assertEqual(counts["STRUCTURALLY_IDENTICAL"], 1)

    def test_pair_level_c5_structural_identity_not_masked_by_group_mean(self):
        rows_zero = ["a" * 64, "a" * 64, "a" * 64]
        base = {
            "task_id": "p4ra-FQE3-v3-TE-001",
            "budget_B": 64,
            "K": 5,
            "meta_seed": 0,
        }
        records = [
            dict(base, arm=m5.S1_FOMAML_ZERO_BO, initial_design_row_digests=rows_zero),
            dict(base, arm=m5.S1_FOMAML_KSHOT_BO, initial_design_row_digests=list(rows_zero)),
            dict(
                base,
                arm=m5.S1_PRETRAIN_KSHOT_BO,
                initial_design_row_digests=["b" * 64, "c" * 64, "d" * 64],
            ),
        ]
        report = s1.ranking_identifiability_report(records)
        group = report["groups"][0]
        self.assertEqual(group["ranking_status"], "IDENTIFIABLE")
        self.assertLess(group["mean_overlap_rate"], 0.90)
        c5 = next(
            item
            for item in group["pairwise"]
            if {item["arm_a"], item["arm_b"]}
            == {m5.S1_FOMAML_ZERO_BO, m5.S1_FOMAML_KSHOT_BO}
        )
        self.assertFalse(c5["pair_identifiable"])
        self.assertEqual(c5["structural_status"], "STRUCTURALLY_IDENTICAL")
        key = f"{m5.S1_FOMAML_ZERO_BO}|{m5.S1_FOMAML_KSHOT_BO}"
        self.assertIn(key, report["pair_status_counts"])
        self.assertEqual(report["pair_status_counts"][key]["STRUCTURALLY_IDENTICAL"], 1)
        self.assertEqual(report["pair_status_counts"][key]["IDENTIFIABLE"], 0)

    def test_identifiability_report_rejects_bad_threshold(self):
        for bad in (0.0, -0.1, 1.5):
            with self.assertRaises(s1.S1RunnerError):
                s1.ranking_identifiability_report([], threshold=bad)

    def test_write_run_bundle_includes_identifiability_artifact(self):
        records = [
            self._run(self.te003, arm)
            for arm in (m5.S1_FOMAML_ZERO_BO, m5.S1_FOMAML_KSHOT_BO)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            outdir = Path(tmp) / "bundle"
            summary = s1.write_run_bundle(
                outdir,
                run_id="p4ra-s1-b03-bundle",
                package=self.package,
                records=records,
                run_config=s1.build_run_config(
                    self.package,
                    run_id="p4ra-s1-b03-bundle",
                    splits=("meta_test",),
                    task_limit=1,
                    arm="ALL",
                    budget=64,
                    k_shot=5,
                    meta_seed=0,
                    opt_seed=0,
                ),
            )
            self.assertTrue((outdir / "identifiability_report.json").is_file())
            self.assertEqual(summary["ranking_identifiability"]["group_count"], 1)
            manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
            artifact_paths = {item["path"] for item in manifest["artifacts"]}
            self.assertIn("identifiability_report.json", artifact_paths)




class MergeSubcommandTests(unittest.TestCase):
    """R-V4-07：并行分片 + merge 子命令（缩放网格，不启动 21,000）。"""

    RUN_ID = "p4ra-s1-merge-test"
    SCALED_ARGS = {
        "splits": "meta_test",
        "arms": "RAND-BO,DE",
        "budgets": "64,128",
        "k_values": "0,1,3,5",
        "meta_seeds": "0",
        "opt_seeds": "0,1",
        "task_limit": 1,
    }

    @classmethod
    def setUpClass(cls):
        cls.package = s1.load_frozen_package(FROZEN_V4)
        cls.args = SimpleNamespace(**cls.SCALED_ARGS)
        cls.plan = s1.merge_plan_from_args(cls.package, cls.args)
        design_space = load_design_space_12d()
        cls.records = s1.execute_runs(
            cls.package, run_id=cls.RUN_ID, plan=cls.plan, design_space=design_space
        )
        cls.serial_dir = Path(tempfile.mkdtemp(prefix="s1-merge-serial-"))
        cls.addClassCleanup(shutil.rmtree, cls.serial_dir, True)
        s1.write_run_bundle(
            cls.serial_dir,
            run_id=cls.RUN_ID,
            package=cls.package,
            records=cls.records,
            run_config=s1.build_grid_run_config(
                cls.package, run_id=cls.RUN_ID, plan=cls.plan, grid_mode=s1.FORMAL_GRID_MODE
            ),
        )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="s1-merge-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.shards_root = self.root / "shards"
        self._write_shards(self.shards_root, self._shard_records())

    @classmethod
    def _shard_records(cls):
        return {
            seed: [dict(record) for record in cls.records if int(record["opt_seed"]) == seed]
            for seed in (0, 1)
        }

    def _subplan(self, opt_seed):
        return [item for item in self.plan if int(item["opt_seed"]) == opt_seed]

    def _write_shard(self, root, name, records, plan):
        directory = root / name
        s1.write_jsonl_file(directory / "run_records.jsonl", records)
        s1.write_json_file(
            directory / "run_config.json",
            s1.build_grid_run_config(
                self.package, run_id=self.RUN_ID, plan=plan, grid_mode=s1.FORMAL_GRID_MODE
            ),
        )

    def _write_shards(self, root, records_by_opt):
        root.mkdir(parents=True, exist_ok=True)
        for seed, records in records_by_opt.items():
            self._write_shard(root, f"ms0_os{seed}", records, self._subplan(seed))

    @staticmethod
    def _retamper(record, **changes):
        payload = dict(record)
        payload.update(changes)
        payload.pop("record_digest", None)
        payload["record_digest"] = s1.digest(payload)
        return payload

    def _merge(self, outdir=None, shards_root=None):
        target = Path(outdir) if outdir is not None else (self.root / "merged")
        manifest = s1.merge_run_shards(
            self.package,
            shards_root=shards_root or self.shards_root,
            outdir=target,
            run_id=self.RUN_ID,
            plan=self.plan,
            allow_legacy=True,
        )
        return manifest, target

    def _failed_manifest(self, outdir):
        path = Path(outdir) / "merge_manifest.json"
        self.assertTrue(path.is_file())
        return json.loads(path.read_text(encoding="utf-8"))

    def test_default_merge_plan_is_21000(self):
        args = SimpleNamespace(
            splits="meta_test",
            arms="all",
            budgets="64,128",
            k_values="0,1,3,5",
            meta_seeds=None,
            opt_seeds=None,
            task_limit=None,
        )
        plan = s1.merge_plan_from_args(self.package, args)
        self.assertEqual(len(plan), s1.FORMAL_GRID_TOTAL_RUNS)
        self.assertEqual(
            s1._plan_stratum_counts(plan), {"main": 9000, "secondary": 6000, "exploratory": 6000}
        )
        self.assertFalse(any(int(item["budget_B"]) == 128 and int(item["K"]) == 0 for item in plan))

    def test_shard_definitions_cover_fifteen_shards(self):
        shards = s1.shard_definitions()
        self.assertEqual(len(shards), 15)
        self.assertEqual(len({shard["name"] for shard in shards}), 15)
        self.assertTrue(all(shard["expected_runs"] == 1400 for shard in shards))
        self.assertEqual(
            sorted(seed for shard in shards for seed in shard["meta_seeds"]),
            sorted([0, 1, 2] * 5),
        )
        self.assertEqual(
            sorted(seed for shard in shards for seed in shard["opt_seeds"]),
            sorted(list(range(10)) * 3),
        )

    def test_merge_two_shards_matches_serial_bundle(self):
        manifest, outdir = self._merge()
        self.assertEqual(manifest["status"], "PASS")
        self.assertEqual(manifest["expected_run_count"], len(self.plan))
        self.assertEqual(manifest["actual_record_count"], len(self.plan))
        self.assertEqual(manifest["shard_count"], 2)
        self.assertEqual(manifest["missing_run_count"], 0)
        self.assertEqual(manifest["extra_run_count"], 0)
        self.assertEqual(manifest["duplicate_run_id_count"], 0)
        self.assertEqual(manifest["duplicate_key_count"], 0)
        self.assertEqual(manifest["physical_call_count_total"], 0)
        self.assertEqual(manifest["b128_k0_count"], 0)
        self.assertEqual([row["actual_runs"] for row in manifest["strata"]], [12, 8, 8])
        self.assertEqual([row["expected_runs"] for row in manifest["strata"]], [12, 8, 8])
        self.assertEqual([row["global_expected_runs"] for row in manifest["strata"]], [9000, 6000, 6000])
        for name in (
            "run_records.jsonl",
            "run_config.json",
            "run_summary.json",
            "identifiability_report.json",
            "manifest.json",
        ):
            self.assertEqual(
                (self.serial_dir / name).read_bytes(), (outdir / name).read_bytes(), name
            )
        self.assertEqual(
            manifest["merged"]["run_records_sha256"], s1.sha256_file(outdir / "run_records.jsonl")
        )
        self.assertEqual(manifest["merged"]["manifest_sha256"], s1.sha256_file(outdir / "manifest.json"))
        stored = json.loads((outdir / "merge_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["schema_version"], s1.MERGE_MANIFEST_SCHEMA_VERSION)
        self.assertEqual(stored["status"], "PASS")
        self.assertEqual(stored["identity"], s1.frozen_identity_for_run(self.package))
        self.assertEqual(stored["frozen_run_id"], self.package["identity"]["frozen_run_id"])
        self.assertEqual(len(stored["shards"]), 2)
        for shard in stored["shards"]:
            for key in (
                "path",
                "run_records_sha256",
                "run_records_bytes",
                "record_count",
                "run_config_sha256",
                "meta_seeds",
                "opt_seeds",
                "arms",
                "budgets",
                "k_values",
                "splits",
            ):
                self.assertIn(key, shard)
            self.assertEqual(shard["record_count"], len(self.plan) // 2)
        self.assertIn(stored["clone_pairs"]["status"], ("NOT_APPLICABLE", "PASS"))

    def test_merge_executed_shards_core_matches_serial(self):
        design_space = load_design_space_12d()
        exec_root = self.root / "exec_shards"
        for seed in (0, 1):
            subplan = self._subplan(seed)
            subrecords = s1.execute_runs(
                self.package, run_id=self.RUN_ID, plan=subplan, design_space=design_space
            )
            self._write_shard(exec_root, f"ms0_os{seed}", subrecords, subplan)
        manifest = s1.merge_run_shards(
            self.package,
            shards_root=exec_root,
            outdir=self.root / "merged_exec",
            run_id=self.RUN_ID,
            plan=self.plan,
            allow_legacy=True,
        )
        self.assertEqual(manifest["status"], "PASS")
        merged = s1.load_jsonl_file(self.root / "merged_exec" / "run_records.jsonl")
        self.assertEqual(
            [record["run_id"] for record in merged], [record["run_id"] for record in self.records]
        )
        serial_by_id = {record["run_id"]: record for record in self.records}
        for record in merged:
            self.assertEqual(s1._record_core(record), s1._record_core(serial_by_id[record["run_id"]]))

    def test_merge_missing_shard_fails_closed(self):
        records = self._shard_records()
        shards = self.root / "missing_shards"
        self._write_shards(shards, {0: records[0]})
        with self.assertRaises(s1.S1RunnerError):
            s1.merge_run_shards(
                self.package,
                shards_root=shards,
                outdir=self.root / "merged_missing",
                run_id=self.RUN_ID,
                plan=self.plan,
                allow_legacy=True,
            )
        stored = self._failed_manifest(self.root / "merged_missing")
        self.assertEqual(stored["status"], "FAIL")
        self.assertEqual(stored["missing_run_count"], len(self.plan) // 2)
        self.assertEqual(stored["shard_count"], 1)
        self.assertFalse((self.root / "merged_missing" / "run_records.jsonl").exists())

    def test_merge_extra_record_fails_closed(self):
        records = self._shard_records()
        base = records[0][0]
        extra = self._retamper(
            base,
            opt_seed=2,
            run_id=s1.make_run_id(
                self.RUN_ID,
                arm=base["arm"],
                budget=int(base["budget_B"]),
                k_shot=int(base["K"]),
                task_id=base["task_id"],
                meta_seed=int(base["meta_seed"]),
                opt_seed=2,
            ),
        )
        records[0].append(extra)
        self._write_shards(self.shards_root, records)
        with self.assertRaises(s1.S1RunnerError):
            self._merge()
        stored = self._failed_manifest(self.root / "merged")
        self.assertEqual(stored["status"], "FAIL")
        self.assertEqual(stored["extra_run_count"], 1)
        self.assertEqual(stored["actual_record_count"], len(self.plan) + 1)

    def test_merge_duplicate_run_id_fails_closed(self):
        records = self._shard_records()
        records[0].append(dict(records[0][0]))
        self._write_shards(self.shards_root, records)
        with self.assertRaises(s1.S1RunnerError):
            self._merge()
        stored = self._failed_manifest(self.root / "merged")
        self.assertEqual(stored["status"], "FAIL")
        self.assertEqual(stored["duplicate_run_id_count"], 1)
        self.assertEqual(stored["actual_record_count"], len(self.plan) + 1)

    def test_merge_overlap_duplicate_key_fails_closed(self):
        records = self._shard_records()
        base = records[1][0]
        overlap = self._retamper(base, run_id=base["run_id"] + "-overlap")
        records[0].append(overlap)
        self._write_shards(self.shards_root, records)
        with self.assertRaises(s1.S1RunnerError):
            self._merge()
        stored = self._failed_manifest(self.root / "merged")
        self.assertEqual(stored["status"], "FAIL")
        self.assertEqual(stored["duplicate_key_count"], 1)
        self.assertEqual(stored["duplicate_run_id_count"], 0)

    def test_merge_identity_drift_fails_closed(self):
        records = self._shard_records()
        records[0][0] = self._retamper(records[0][0], family_fingerprint="0" * 64)
        self._write_shards(self.shards_root, records)
        with self.assertRaises(s1.S1RunnerError):
            self._merge()
        stored = self._failed_manifest(self.root / "merged")
        self.assertEqual(stored["status"], "FAIL")
        self.assertGreater(stored["problem_count"], 0)

    def test_merge_budget_mismatch_fails_closed(self):
        records = self._shard_records()
        records[0][0] = self._retamper(records[0][0], billable_evals=1)
        self._write_shards(self.shards_root, records)
        with self.assertRaises(s1.S1RunnerError):
            self._merge()
        stored = self._failed_manifest(self.root / "merged")
        self.assertEqual(stored["status"], "FAIL")
        self.assertGreater(stored["problem_count"], 0)

    def test_merge_physical_call_fails_closed(self):
        records = self._shard_records()
        record = records[0][0]
        physics = dict(record["physics"])
        physics["physical_call_count"] = 1
        records[0][0] = self._retamper(record, physics=physics)
        self._write_shards(self.shards_root, records)
        with self.assertRaises(s1.S1RunnerError):
            self._merge()
        stored = self._failed_manifest(self.root / "merged")
        self.assertEqual(stored["status"], "FAIL")
        self.assertEqual(stored["physical_call_count_total"], 1)

    def test_merge_stratum_mismatch_fails_closed(self):
        records = self._shard_records()
        record = records[0][0]
        wrong = "secondary" if record["grid_stratum"] == "main" else "main"
        records[0][0] = self._retamper(record, grid_stratum=wrong)
        self._write_shards(self.shards_root, records)
        with self.assertRaises(s1.S1RunnerError):
            self._merge()
        stored = self._failed_manifest(self.root / "merged")
        self.assertEqual(stored["status"], "FAIL")
        self.assertGreater(stored["problem_count"], 0)

    def test_merge_b128_k0_record_fails_closed(self):
        records = self._shard_records()
        candidates = [record for record in records[1] if int(record["budget_B"]) == 128]
        record = dict(candidates[0])
        wrong = self._retamper(
            record,
            K=0,
            support_evals=0,
            initial_evals=8,
            bo_evals=120,
            bo_calls=120,
            billable_evals=128,
            grid_stratum="secondary",
            run_id=s1.make_run_id(
                self.RUN_ID,
                arm=record["arm"],
                budget=128,
                k_shot=0,
                task_id=record["task_id"],
                meta_seed=int(record["meta_seed"]),
                opt_seed=int(record["opt_seed"]),
            ),
        )
        records[1] = [item for item in records[1] if item["run_id"] != record["run_id"]]
        records[1].append(wrong)
        self._write_shards(self.shards_root, records)
        with self.assertRaises(s1.S1RunnerError):
            self._merge()
        stored = self._failed_manifest(self.root / "merged")
        self.assertEqual(stored["status"], "FAIL")
        self.assertEqual(stored["b128_k0_count"], 1)
        self.assertEqual(stored["expected_b128_k0_count"], 0)

    def test_merge_is_idempotent_byte_for_byte(self):
        first, first_dir = self._merge(outdir=self.root / "merged_a")
        second, second_dir = self._merge(outdir=self.root / "merged_b")
        self.assertEqual(first["status"], "PASS")
        self.assertEqual(second["status"], "PASS")
        for name in (
            "run_records.jsonl",
            "run_config.json",
            "run_summary.json",
            "identifiability_report.json",
            "manifest.json",
            "merge_manifest.json",
        ):
            self.assertEqual((first_dir / name).read_bytes(), (second_dir / name).read_bytes(), name)

    def test_merge_cli_pass_and_fail_exit_codes(self):
        import contextlib
        import io

        buffer = io.StringIO()
        argv = [
            "merge",
            "--frozen",
            str(FROZEN_V4),
            "--shards-root",
            str(self.shards_root),
            "--outdir",
            str(self.root / "cli_merged"),
            "--run-id",
            self.RUN_ID,
            "--splits",
            "meta_test",
            "--arms",
            "RAND-BO,DE",
            "--budgets",
            "64,128",
            "--k-values",
            "0,1,3,5",
            "--meta-seeds",
            "0",
            "--opt-seeds",
            "0,1",
            "--task-limit",
            "1",
            "--allow-legacy",
        ]
        with contextlib.redirect_stdout(buffer):
            code = s1._main(argv)
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["record_count"], len(self.plan))
        self.assertEqual(payload["shard_count"], 2)
        missing_root = self.root / "missing_cli"
        self._write_shards(missing_root, {0: self._shard_records()[0]})
        argv[argv.index(str(self.shards_root))] = str(missing_root)
        argv[argv.index(str(self.root / "cli_merged"))] = str(self.root / "cli_missing")
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = s1._main(argv)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(buffer.getvalue())["status"], "FAIL")


class V4cFormalGateTests(unittest.TestCase):
    """R-V4-08：formal（确证）路径必须拒绝非确证冻结包；旧包只能只读（--allow-legacy）。"""

    def test_require_confirmatory_rejects_legacy_packages(self):
        for root in (FROZEN, FROZEN_V4):
            with self.assertRaises(s1.S1RunnerError):
                s1.load_frozen_package(root, require_confirmatory=True)

    def test_default_load_flags_legacy_package_as_exploratory(self):
        package = s1.load_frozen_package(FROZEN_V4)
        identity = package["identity"]
        self.assertFalse(identity["confirmatory_eligible"])
        self.assertEqual(identity["evaluation_mode"], "exploratory")
        self.assertEqual(identity["prereg_v4c_blocks_status"], "ABSENT")
        self.assertEqual(package["evaluation_mode"], "exploratory")
        self.assertFalse(package["confirmatory_eligible"])

    def test_cli_grid_requires_allow_legacy(self):
        with self.assertRaises(s1.S1RunnerError):
            s1._main(["grid", "--frozen", str(FROZEN_V4), "--grid", "formal"])
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = s1._main(
                ["grid", "--frozen", str(FROZEN_V4), "--grid", "formal", "--allow-legacy"]
            )
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["evaluation_mode"], "exploratory")
        self.assertFalse(payload["confirmatory_eligible"])

    def test_merge_without_allow_legacy_rejects_legacy_package(self):
        package = s1.load_frozen_package(FROZEN_V4)
        plan = [
            {
                "split": "meta_test",
                "task_id": package["split"]["task_ids"]["meta_test"][0],
                "arm": m5.S1_RANDOM_BO,
                "budget_B": 64,
                "K": 0,
                "grid_stratum": "main",
                "meta_seed": 0,
                "opt_seed": 0,
            }
        ]
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(s1.S1RunnerError):
                s1.merge_run_shards(
                    package,
                    shards_root=Path(raw) / "shards",
                    outdir=Path(raw) / "out",
                    run_id="p4ra-s1-gate-test",
                    plan=plan,
                )


if __name__ == "__main__":
    unittest.main()

