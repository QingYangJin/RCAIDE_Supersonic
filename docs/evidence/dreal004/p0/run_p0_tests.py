
"""Non-destructive P0 test runner: the recovery preflight module set plus the new
Issue #14 modules.  Writes only a log and a summary JSON; it does not regenerate
any recovery receipt and does not start a solver.
"""
from __future__ import annotations

import io, json, platform, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.tests import (  # noqa: E402
    test_recovery_meta_contracts as tests,
    test_openvsp_geometry as geometry_tests,
    test_recovery_feedback as feedback_tests,
    test_recovery_bo as bo_tests,
    test_recovery_population as population_tests,
    test_recovery_raw_verification as raw_tests,
    test_recovery_adaptation_guards as adaptation_tests,
    test_recovery_geometry_effects as effect_tests,
    test_recovery_task_deck as deck_tests,
    test_recovery_checkpoint as checkpoint_tests,
    test_recovery_ledger as ledger_tests,
    test_recovery_m2_rehearsal as rehearsal_tests,
    test_recovery_path_injection as path_tests,
    test_recovery_m1_batch as batch_tests,
    test_recovery_readiness as readiness_tests,
    test_recovery_real_admission as admission_tests,
    test_recovery_solver_runner as solver_runner_tests,
)
from research.concorde_metaopt.tests import test_adaptive_alpha as adaptive_tests  # noqa: E402
from research.concorde_metaopt.tests import test_polar_rows as polar_rows_tests  # noqa: E402
from research.concorde_metaopt.tests import test_endpoint_analysis as endpoint_tests  # noqa: E402

OUT = Path(__file__).resolve().parent
MODULES = (tests, geometry_tests, feedback_tests, bo_tests, population_tests, raw_tests,
           adaptation_tests, effect_tests, deck_tests, checkpoint_tests, ledger_tests,
           rehearsal_tests, path_tests, batch_tests, readiness_tests, admission_tests,
           solver_runner_tests, adaptive_tests, polar_rows_tests, endpoint_tests)


def main() -> int:
    stream = io.StringIO()
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(m)
                                for m in MODULES])
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (OUT / "p0_test_log.txt").write_text(stream.getvalue(), encoding="utf-8")
    summary = {
        "schema": "dreal004.p0_test_summary.v1",
        "python": sys.executable, "version": platform.python_version(),
        "modules": [m.__name__ for m in MODULES],
        "tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped),
        "was_successful": result.wasSuccessful(),
        "physical_solver_starts_actual": 0,
        "note": ("Non-destructive module-level run.  The destructive full "
                 "run_recovery_preflight.py is not executed in the P0 branch."),
    }
    (OUT / "p0_test_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
