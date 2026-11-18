"""A4 recovery tests: repository locations are injected, never machine-bound.

Zero physics.  These tests only exercise path resolution and fail-closed
argument handling; they never build geometry, never spawn a solver, and never
touch the network.
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.dreal001.optimizers import p2a_v2_common
from research.concorde_metaopt.dreal001.optimizers import p2a_v2
from research.concorde_metaopt.reviews.a5_audit import a5_audit
from research.concorde_metaopt.dreal001.meta import m0r_predraft


class ResolveA1RootTests(unittest.TestCase):
    def test_default_is_none_and_env_name_is_declared(self) -> None:
        self.assertIsNone(p2a_v2.DEFAULT_A1_ROOT)
        self.assertEqual(p2a_v2.A1_ROOT_ENV, "RCAIDE_A1_ROOT")

    def test_missing_injection_fails_closed(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "RCAIDE_A1_ROOT"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValueError) as ctx:
                p2a_v2.resolve_a1_root()
        self.assertIn("RCAIDE_A1_ROOT", str(ctx.exception))

    def test_environment_injection_is_honoured(self) -> None:
        with mock.patch.dict(os.environ, {"RCAIDE_A1_ROOT": "C:/injected/a1"}, clear=False):
            self.assertEqual(p2a_v2.resolve_a1_root(), Path("C:/injected/a1"))

    def test_explicit_argument_wins_over_environment(self) -> None:
        with mock.patch.dict(os.environ, {"RCAIDE_A1_ROOT": "C:/env/a1"}, clear=False):
            value = p2a_v2.resolve_a1_root(Path("D:/explicit/a1"))
        self.assertEqual(value, Path("D:/explicit/a1"))


class FrozenArtifactPathTests(unittest.TestCase):
    def test_artifact_path_composes_from_injected_root(self) -> None:
        value = p2a_v2_common.a1_artifact_path(
            "research/concorde_metaopt/x.json", a1_root="C:/a1-root"
        )
        self.assertEqual(value, str(Path("C:/a1-root").joinpath("research", "concorde_metaopt", "x.json")))

    def test_module_constants_follow_environment(self) -> None:
        with mock.patch.dict(os.environ, {"RCAIDE_A1_ROOT": "C:/a1-elsewhere"}, clear=False):
            module = importlib.reload(p2a_v2_common)
            try:
                prefix = str(Path("C:/a1-elsewhere"))
                self.assertTrue(module.A1_PAIR_MANIFEST_PATH.startswith(prefix))
                self.assertTrue(module.A1_PREFLIGHT_BUNDLE_PATH.startswith(prefix))
            finally:
                os.environ.pop("RCAIDE_A1_ROOT", None)
                importlib.reload(p2a_v2_common)

    def test_defaults_fall_back_to_documented_historical_binding(self) -> None:
        historical = p2a_v2_common._A1_ROOT_HISTORICAL
        self.assertTrue(historical.startswith("D:"))
        self.assertTrue(historical.endswith("wt-real-a1-geometry-solver"))


class A5AuditInjectionTests(unittest.TestCase):
    def test_missing_roots_exit_code_2_without_writing(self) -> None:
        env = {k: v for k, v in os.environ.items()
               if k not in ("RCAIDE_S3_ROOT", "RCAIDE_DNEXT_ROOT")}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(a5_audit.main([]), 2)
            self.assertEqual(a5_audit.main(["--s3-root", "C:/s3"]), 2)
            self.assertEqual(a5_audit.main(["--dnext-root", "C:/dnext"]), 2)


class DraftRootInjectionTests(unittest.TestCase):
    def test_m0r_draft_root_follows_environment(self) -> None:
        with mock.patch.dict(os.environ, {"RCAIDE_DNEXT_PARENT": str(Path("C:/dnext-parent"))}, clear=False):
            module = importlib.reload(m0r_predraft)
            try:
                self.assertEqual(module.ROOT, Path("C:/dnext-parent"))
                self.assertEqual(module.A1, Path("C:/dnext-parent/dnext001/wt-real-a1-geometry-solver"))
            finally:
                os.environ.pop("RCAIDE_DNEXT_PARENT", None)
                importlib.reload(m0r_predraft)


class NoMachinePathsInRecoveryCodeTests(unittest.TestCase):
    """Recovery code must stay relocatable; historical evidence strings stay frozen."""

    MARKERS = ("D:" + "\\" + "RCAIDE", "D:" + "/" + "RCAIDE")

    def test_recovery_modules_are_relocatable(self) -> None:
        files = [
            ROOT / "research/concorde_metaopt/dreal001/meta/task_spec.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/meta_dataset.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/production.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/validation_training.py",
            ROOT / "research/concorde_metaopt/dreal001/meta/m2_rehearsal.py",
            ROOT / "research/concorde_metaopt/dreal001/m1/task_evaluator.py",
            ROOT / "research/concorde_metaopt/dreal001/optimizers/p2a_v2.py",
            ROOT / "research/concorde_metaopt/meta_learning/m5_runner.py",
            ROOT / "research/concorde_metaopt/meta_learning/m6_study.py",
            ROOT / "docs/evidence/drecover001/run_recovery_preflight.py",
            Path(__file__).resolve(),
        ]
        offenders = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            for marker in self.MARKERS:
                if marker in text:
                    offenders.append(str(path.relative_to(ROOT)) + " :: " + marker)
        self.assertEqual(offenders, [], "recovery code must not embed machine-specific repository paths")


if __name__ == "__main__":
    unittest.main()
