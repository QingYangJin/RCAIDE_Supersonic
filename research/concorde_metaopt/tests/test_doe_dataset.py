"""Tests for the P3 DOE dataset: sampling, screening, manifest, validation.

These tests never run a Mission or CFD code; they exercise the geometry-only
screening path and the independent re-validation that guards the committed
dataset artifacts.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from research.concorde_metaopt.aircraft.design_space import load_design_space
from research.concorde_metaopt.data import schema
from research.concorde_metaopt.data.generate_doe import (
    DoEError,
    generate_unit_samples,
    parse_batch_sizes,
    run_doe,
    screen_design,
)
from research.concorde_metaopt.data.validate_dataset import validate_dataset


_SPACE = load_design_space()


class HelperTests(unittest.TestCase):
    def test_parse_batch_sizes_accepts_int_string_and_list(self) -> None:
        self.assertEqual(parse_batch_sizes(32), [32])
        self.assertEqual(parse_batch_sizes("32,128, 512"), [32, 128, 512])
        self.assertEqual(parse_batch_sizes([8, 16]), [8, 16])

    def test_parse_batch_sizes_rejects_invalid_values(self) -> None:
        for value in (0, -5, "", "a,b", 6000, "3000,3000"):
            with self.assertRaises(DoEError):
                parse_batch_sizes(value)

    def test_lhs_sampling_is_deterministic_and_inside_unit_box(self) -> None:
        first = generate_unit_samples("lhs", 42, 16, 15)
        second = generate_unit_samples("lhs", 42, 16, 15)
        self.assertEqual(first, second)
        other = generate_unit_samples("lhs", 43, 16, 15)
        self.assertNotEqual(first, other)
        for row in first:
            self.assertEqual(len(row), 15)
            for value in row:
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)

    def test_sobol_sampling_shape(self) -> None:
        samples = generate_unit_samples("sobol", 7, 8, 15)
        self.assertEqual(len(samples), 8)
        self.assertTrue(all(len(row) == 15 for row in samples))

    def test_unknown_method_rejected(self) -> None:
        with self.assertRaises(DoEError):
            generate_unit_samples("random", 42, 4, 15)

    def test_screen_baseline_is_valid_and_carries_no_objective(self) -> None:
        result = screen_design(_SPACE, _SPACE.baseline_dict())
        self.assertEqual(result["status"], schema.GEOMETRY_VALID)
        self.assertIsNone(result["error"])
        self.assertIn("wing_area_m2", result["metrics"])

    def test_screen_rejects_cross_constraint_violation(self) -> None:
        design = dict(_SPACE.baseline_dict())
        design["span_location_2"] = 0.96
        result = screen_design(_SPACE, design)
        self.assertEqual(result["status"], schema.GEOMETRY_INVALID)
        self.assertIn("span_location_2", result["error"])

    def test_screen_rejects_invalid_geometry(self) -> None:
        design = dict(_SPACE.baseline_dict())
        design["fuselage_length"] = -1.0
        result = screen_design(_SPACE, design)
        self.assertIn(result["status"], (schema.GEOMETRY_INVALID, schema.GEOMETRY_ERROR))
        self.assertTrue(result["error"])


class SchemaTests(unittest.TestCase):
    def _row(self) -> Dict[str, Any]:
        design = _SPACE.baseline_dict()
        return schema.make_candidate_row(
            _SPACE,
            design,
            batch_id="batch-000",
            batch_index=0,
            sample_index=0,
            method="lhs",
            seed=42,
            geometry_status=schema.GEOMETRY_VALID,
            metrics={"wing_area_m2": 358.25},
        )

    def test_row_round_trips_schema(self) -> None:
        row = self._row()
        self.assertEqual(schema.check_candidate_row(row, _SPACE), [])

    def test_row_forbids_objective_fields(self) -> None:
        row = self._row()
        row["objective"] = 1.0
        errors = schema.check_candidate_row(row, _SPACE)
        self.assertTrue(any("forbidden field" in error for error in errors))

    def test_row_requires_zero_physical_calls(self) -> None:
        row = self._row()
        row["physical_call_count"] = 3
        errors = schema.check_candidate_row(row, _SPACE)
        self.assertTrue(any("physical_call_count" in error for error in errors))

    def test_candidate_id_tracks_content(self) -> None:
        row = self._row()
        changed = dict(row)
        changed_design = dict(row["design"])
        changed_design["wing_area"] = 360.0
        changed["design"] = changed_design
        errors = schema.check_candidate_row(changed, _SPACE)
        self.assertTrue(any("candidate_id" in error for error in errors))


class RunDoETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="concorde-doe-tests-"))
        cls.summary = run_doe(
            output_root=cls.root,
            run_id="doe-test-32",
            batch_sizes=(32,),
            method="lhs",
            seed=42,
            validate=True,
            recompute_geometry=True,
        )
        cls.run_dir = cls.root / "doe-test-32"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_summary_reports_zero_physics(self) -> None:
        summary = self.summary
        self.assertEqual(summary["stage"], "P3")
        self.assertEqual(summary["status"], "doe_completed")
        self.assertEqual(summary["total_true_evaluations"], 0)
        self.assertEqual(summary["low_fidelity_calls"], 0)
        self.assertEqual(summary["su2_calls"], 0)
        self.assertEqual(summary["doe"]["written_candidates"], 32)
        self.assertEqual(summary["doe"]["geometry_valid"], 32)

    def test_artifacts_exist(self) -> None:
        for name in (
            "candidates.jsonl",
            "candidates.csv",
            "data_manifest.json",
            "run_config.json",
            "environment.json",
            "summary.json",
            "validation.json",
            "README.md",
        ):
            self.assertTrue((self.run_dir / name).is_file(), name)

    def test_manifest_counts_and_hashes_are_consistent(self) -> None:
        manifest = json.loads((self.run_dir / "data_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["candidates"]["written"], 32)
        self.assertEqual(manifest["geometry"]["valid"], 32)
        self.assertEqual(manifest["evaluations"]["physical_call_count"], 0)
        self.assertFalse(manifest["evaluations"]["objective_fields_present"])
        self.assertGreaterEqual(len(manifest["files"]), 4)
        rows = [json.loads(line) for line in (self.run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 32)
        self.assertEqual({row["candidate_id"] for row in rows}.__len__(), 32)
        self.assertTrue(all(row["evaluation_status"] == schema.EVALUATION_NOT_RUN for row in rows))
        self.assertTrue(all(row["physical_call_count"] == 0 for row in rows))

    def test_validation_recomputes_geometry(self) -> None:
        report = json.loads((self.run_dir / "validation.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "valid", report["checks"])
        self.assertEqual(report["failed_count"], 0)
        recompute = [check for check in report["checks"] if check["check_id"] == "DS12"]
        self.assertEqual(recompute[0]["status"], "pass")

    def test_same_seed_reproduces_candidate_ids(self) -> None:
        other_root = Path(tempfile.mkdtemp(prefix="concorde-doe-tests-repeat-"))
        try:
            run_doe(
                output_root=other_root,
                run_id="doe-test-repeat",
                batch_sizes=(32,),
                method="lhs",
                seed=42,
                validate=False,
            )
            first = [
                json.loads(line)["candidate_id"]
                for line in (self.run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            second = [
                json.loads(line)["candidate_id"]
                for line in (other_root / "doe-test-repeat" / "candidates.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(first, second)
        finally:
            shutil.rmtree(other_root, ignore_errors=True)

    def test_multi_batch_run_sums_counts(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="concorde-doe-tests-batches-"))
        try:
            summary = run_doe(
                output_root=root,
                run_id="doe-test-batches",
                batch_sizes=(8, 16),
                method="sobol",
                seed=5,
                validate=False,
            )
            self.assertEqual(summary["doe"]["requested_candidates"], 24)
            self.assertEqual(summary["doe"]["written_candidates"], 24)
            self.assertEqual(len(summary["doe"]["batches"]), 2)
            self.assertEqual(summary["doe"]["batches"][0]["seed"], 5)
            self.assertEqual(summary["doe"]["batches"][1]["seed"], 6)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_existing_run_directory_requires_flag(self) -> None:
        with self.assertRaises(FileExistsError):
            run_doe(output_root=self.root, run_id="doe-test-32", validate=False)


class TamperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="concorde-doe-tests-tamper-"))
        run_doe(
            output_root=self.root,
            run_id="doe-test-tamper",
            batch_sizes=(8,),
            seed=11,
            validate=False,
        )
        self.run_dir = self.root / "doe-test-tamper"

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _rewrite_rows(self, rows) -> None:
        path = self.run_dir / "candidates.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    def test_validation_detects_out_of_bounds_design(self) -> None:
        rows = [json.loads(line) for line in (self.run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
        rows[0]["design"]["wing_area"] = 1000.0
        self._rewrite_rows(rows)
        report = validate_dataset(self.run_dir, write=False)
        self.assertEqual(report["status"], "invalid")
        self.assertTrue(any("DS05" == check["check_id"] or "DS03" == check["check_id"] for check in report["checks"] if check["status"] == "fail"))

    def test_validation_detects_missing_rows(self) -> None:
        rows = [json.loads(line) for line in (self.run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
        self._rewrite_rows(rows[:-1])
        report = validate_dataset(self.run_dir, write=False)
        self.assertEqual(report["status"], "invalid")
        failed = {check["check_id"] for check in report["checks"] if check["status"] == "fail"}
        self.assertIn("DS03", failed)

    def test_validation_detects_config_hash_drift(self) -> None:
        path = self.run_dir / "data_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["design_space"]["config_sha256"] = "0" * 64
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report = validate_dataset(self.run_dir, write=False)
        failed = {check["check_id"] for check in report["checks"] if check["status"] == "fail"}
        self.assertIn("DS09", failed)

    def test_validation_detects_objective_injection(self) -> None:
        rows = [json.loads(line) for line in (self.run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
        rows[0]["objective"] = 34000.0
        self._rewrite_rows(rows)
        report = validate_dataset(self.run_dir, write=False)
        failed = {check["check_id"] for check in report["checks"] if check["status"] == "fail"}
        self.assertIn("DS05", failed)
        self.assertIn("DS11", failed)


if __name__ == "__main__":
    unittest.main()
