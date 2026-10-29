"""Command line entry point for the Phase I research workspace.

Only subcommands that are genuinely implemented are available. Implemented so
far: the P0 read-only audit, the P1 geometry check, the P1 OpenVSP geometry
export check, the P1 OpenVSP perturbation check (representative wing/tail/
fuselage perturbations), the P2 single-cruise smoke run, the P3 DOE dataset
screening (geometry only, zero physics) and the P4 ordinary constrained BO
baseline on the frozen evaluator. Later-stage subcommands return exit code 2
with an explicit message so that no placeholder result can be mistaken for
evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _cmd_audit(args: argparse.Namespace) -> int:
    from research.concorde_metaopt.audit import run_audit

    result = run_audit(
        repo_root=REPO_ROOT,
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        shell_probes=args.shell_probes,
        allow_existing=args.allow_existing,
    )
    summary = result["summary"]
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "output_dir": result["output_dir"],
        "blockers": len(result["environment"]["blockers"]),
        "true_evaluations": summary["total_true_evaluations"],
    }, indent=2, ensure_ascii=False))
    return 0


def _cmd_geometry_check(args: argparse.Namespace) -> int:
    from research.concorde_metaopt.aircraft.geometry_checks import run_geometry_check

    summary = run_geometry_check(
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        use_rcaide=not args.no_rcaide,
        delta_fraction=args.delta_fraction,
        allow_existing=args.allow_existing,
    )
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "cases": summary["geometry"]["cases"],
        "invalid_cases": summary["geometry"]["failed_cases"],
        "rcaide_cross_checks": summary["geometry"]["rcaide_cross_checks"],
        "true_evaluations": summary["total_true_evaluations"],
    }, indent=2, ensure_ascii=False))
    return 0


def _cmd_openvsp_check(args: argparse.Namespace) -> int:
    from research.concorde_metaopt.aircraft.openvsp_check import run_openvsp_check

    summary = run_openvsp_check(
        output_root=Path(args.output_root) if args.output_root else None,
        export_root=Path(args.export_root) if args.export_root else None,
        run_id=args.run_id,
        openvsp_python=args.openvsp_python,
        openvsp_root=args.openvsp_root,
        timeout_s=args.timeout,
        allow_existing=args.allow_existing,
        delete_exports=args.delete_exports,
    )
    openvsp = summary.get("openvsp") or {}
    comparisons = openvsp.get("comparisons") or []
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "design_dim": summary["design_dim"],
        "openvsp_version": openvsp.get("version"),
        "openvsp_python": openvsp.get("python_version"),
        "comparisons": len(comparisons),
        "warnings": openvsp.get("warnings"),
        "failures": openvsp.get("failures"),
        "true_evaluations": summary["total_true_evaluations"],
    }, indent=2, ensure_ascii=False))
    return 0 if summary["status"].startswith("openvsp_check_completed") else 1


def _cmd_openvsp_cases(args: argparse.Namespace) -> int:
    from research.concorde_metaopt.aircraft.openvsp_perturbations import (
        run_openvsp_perturbation_check,
    )

    summary = run_openvsp_perturbation_check(
        output_root=Path(args.output_root) if args.output_root else None,
        export_root=Path(args.export_root) if args.export_root else None,
        run_id=args.run_id,
        openvsp_python=args.openvsp_python,
        openvsp_root=args.openvsp_root,
        timeout_s=args.timeout,
        allow_existing=args.allow_existing,
        delete_exports=args.delete_exports,
    )
    block = summary.get("perturbation") or {}
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "cases": block.get("case_count"),
        "exported_cases": block.get("exported_cases"),
        "checks_pass": block.get("checks_pass"),
        "checks_fail": block.get("checks_fail"),
        "failures": block.get("failures"),
        "true_evaluations": summary["total_true_evaluations"],
    }, indent=2, ensure_ascii=False))
    return 0 if summary["status"].startswith("openvsp_perturbation_check_completed") else 1


def _cmd_smoke(args: argparse.Namespace) -> int:
    from research.concorde_metaopt.evaluation.smoke import run_smoke

    summary = run_smoke(
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        seed=args.seed,
        budget=args.budget,
        allow_existing=args.allow_existing,
    )
    smoke = summary.get("smoke") or {}
    repeatability = smoke.get("repeatability") or {}
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "task_id": summary["task_id"],
        "true_evaluations": summary["total_true_evaluations"],
        "budget": smoke.get("budget"),
        "repeatability_passed": repeatability.get("passed"),
        "repeatability_spread": repeatability.get("relative_spread"),
        "baseline_objective": (smoke.get("baseline") or {}).get("objective"),
        "best_feasible_fuel_kg": summary["best_feasible_fuel_kg"],
        "perturbations": [
            {
                "label": case.get("label"),
                "status": case.get("status"),
                "objective": case.get("objective"),
                "objective_delta": case.get("objective_delta"),
            }
            for case in smoke.get("perturbations", [])
        ],
    }, indent=2, ensure_ascii=False))
    return 0 if summary["status"].startswith("smoke_completed") else 1


def _cmd_doe(args: argparse.Namespace) -> int:
    from research.concorde_metaopt.data.generate_doe import run_doe

    summary = run_doe(
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        batch_sizes=args.n,
        method=args.method,
        seed=args.seed,
        allow_existing=args.allow_existing,
        validate=not args.no_validate,
        recompute_geometry=args.recompute_geometry,
    )
    doe = summary.get("doe") or {}
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "method": summary["method"],
        "seed": summary["seed"],
        "requested_candidates": doe.get("requested_candidates"),
        "written_candidates": doe.get("written_candidates"),
        "geometry_valid": doe.get("geometry_valid"),
        "geometry_invalid": doe.get("geometry_invalid"),
        "geometry_errors": doe.get("geometry_errors"),
        "duplicates_removed": doe.get("duplicates_removed"),
        "validation_status": doe.get("validation_status"),
        "true_evaluations": summary["total_true_evaluations"],
    }, indent=2, ensure_ascii=False))
    if summary["total_true_evaluations"] != 0:
        return 1
    return 0 if summary["status"].startswith("doe_completed") else 1


def _cmd_baseline(args: argparse.Namespace) -> int:
    from research.concorde_metaopt.optimization.baseline_bo import run_baseline_bo

    summary = run_baseline_bo(
        output_root=Path(args.output_root) if args.output_root else None,
        run_id=args.run_id,
        budget=args.budget,
        seed=args.seed,
        initial_design_count=args.initial_designs,
        strategy=args.strategy,
        allow_existing=args.allow_existing,
    )
    bo = summary.get("baseline_bo") or {}
    print(json.dumps({
        "run_id": summary["run_id"],
        "status": summary["status"],
        "method": summary["method"],
        "algorithm": summary["algorithm"],
        "seed": summary["seed"],
        "budget": summary["budget"],
        "true_evaluations": summary["total_true_evaluations"],
        "valid_evaluations": bo.get("valid_evaluations"),
        "feasible_evaluations": bo.get("feasible_evaluations"),
        "search_status": bo.get("search_status"),
        "termination_reason": bo.get("termination_reason"),
        "baseline_objective": bo.get("baseline_objective"),
        "best_feasible_fuel_kg": summary["best_feasible_fuel_kg"],
        "improvement_kg": bo.get("improvement_kg"),
        "first_feasible_evaluation": summary["first_feasible_evaluation"],
        "cache_hits": (bo.get("ledger") or {}).get("cache_hits"),
    }, indent=2, ensure_ascii=False))
    return 0 if summary["status"].startswith("baseline_bo_completed") else 1


def _unimplemented(name: str):
    def _call(args: argparse.Namespace) -> int:
        print(
            name + " is not implemented in the P0 milestone; no result was produced.",
            file=sys.stderr,
        )
        return 2
    return _call


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research.concorde_metaopt.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="read-only P0 environment and source audit")
    audit.add_argument("--run-id", default=None, help="audit run id (default: timestamped)")
    audit.add_argument("--output-root", default=None, help="default: research/concorde_metaopt/optimization_runs")
    audit.add_argument("--shell-probes", default=None, help="JSON from scripts/probe_external_tools.sh for git/tool facts")
    audit.add_argument("--allow-existing", action="store_true", help="write into a run directory that already contains probes/")
    audit.set_defaults(func=_cmd_audit)

    geometry = sub.add_parser("geometry-check", help="P1: 15D geometry checks, effect matrix and RCAIDE cross-checks")
    geometry.add_argument("--run-id", default=None, help="run id (default: timestamped)")
    geometry.add_argument("--output-root", default=None, help="default: research/concorde_metaopt/optimization_runs")
    geometry.add_argument("--no-rcaide", action="store_true", help="skip the RCAIDE rebuild cross-checks")
    geometry.add_argument("--delta-fraction", type=float, default=0.10, help="perturbation as a fraction of each bound span (default 0.10)")
    geometry.add_argument("--allow-existing", action="store_true", help="write into an existing run directory")
    geometry.set_defaults(func=_cmd_geometry_check)

    openvsp = sub.add_parser("openvsp-check", help="P1: export baseline geometry through OpenVSP and verify STL metrics")
    openvsp.add_argument("--run-id", default=None, help="run id (default: timestamped)")
    openvsp.add_argument("--output-root", default=None, help="default: research/concorde_metaopt/optimization_runs")
    openvsp.add_argument("--export-root", default=None, help="default: outputs/concorde_metaopt (git-ignored)")
    openvsp.add_argument("--openvsp-python", default=None, help="external Python 3.9 interpreter that imports openvsp")
    openvsp.add_argument("--openvsp-root", default=None, help="OpenVSP installation root")
    openvsp.add_argument("--timeout", type=float, default=900.0, help="worker timeout seconds (default: 900)")
    openvsp.add_argument("--allow-existing", action="store_true", help="write into an existing run directory")
    openvsp.add_argument(
        "--delete-exports",
        action="store_true",
        help="delete the git-ignored export directory after recording its manifest",
    )
    openvsp.set_defaults(func=_cmd_openvsp_check)

    openvsp_cases = sub.add_parser(
        "openvsp-cases",
        help="P1: OpenVSP geometry-export evidence for representative 15D perturbations",
    )
    openvsp_cases.add_argument("--run-id", default=None, help="run id (default: timestamped)")
    openvsp_cases.add_argument("--output-root", default=None, help="default: research/concorde_metaopt/optimization_runs")
    openvsp_cases.add_argument("--export-root", default=None, help="default: outputs/concorde_metaopt (git-ignored)")
    openvsp_cases.add_argument("--openvsp-python", default=None, help="external Python 3.9 interpreter that imports openvsp")
    openvsp_cases.add_argument("--openvsp-root", default=None, help="OpenVSP installation root")
    openvsp_cases.add_argument("--timeout", type=float, default=900.0, help="per-case worker timeout seconds (default: 900)")
    openvsp_cases.add_argument("--allow-existing", action="store_true", help="write into an existing run directory")
    openvsp_cases.add_argument(
        "--delete-exports",
        action="store_true",
        help="delete the git-ignored export directory after recording its manifest",
    )
    openvsp_cases.set_defaults(func=_cmd_openvsp_cases)

    smoke = sub.add_parser("smoke", help="P2: baseline repeatability and two real single-cruise perturbations")
    smoke.add_argument("--run-id", default=None, help="run id (default: timestamped)")
    smoke.add_argument("--output-root", default=None, help="default: research/concorde_metaopt/optimization_runs")
    smoke.add_argument("--budget", type=int, default=5, help="true-evaluation budget (minimum 5, default 5)")
    smoke.add_argument("--seed", type=int, default=42, help="recorded seed (default 42)")
    smoke.add_argument("--allow-existing", action="store_true", help="write into an existing run directory")
    smoke.set_defaults(func=_cmd_smoke)

    doe = sub.add_parser("doe", help="P3: LHS/Sobol candidate generation with geometry screening (zero physics)")
    doe.add_argument("--run-id", default=None, help="run id (default: timestamped)")
    doe.add_argument("--output-root", default=None, help="default: research/concorde_metaopt/optimization_runs")
    doe.add_argument("--n", default="32", help="batch sizes, e.g. 32 or 32,128,512 (default: 32)")
    doe.add_argument("--method", default="lhs", choices=["lhs", "sobol"], help="space-filling sampler (default: lhs)")
    doe.add_argument("--seed", type=int, default=42, help="base seed (default 42; batch i uses seed+i)")
    doe.add_argument("--allow-existing", action="store_true", help="write into an existing run directory")
    doe.add_argument("--no-validate", action="store_true", help="skip the independent dataset validation")
    doe.add_argument("--recompute-geometry", action="store_true", help="re-build every candidate geometry during validation")
    doe.set_defaults(func=_cmd_doe)

    baseline = sub.add_parser("baseline", help="P4: ordinary constrained BO baseline on the frozen evaluator")
    baseline.add_argument("--run-id", default=None, help="run id (default: timestamped)")
    baseline.add_argument("--output-root", default=None, help="default: research/concorde_metaopt/optimization_runs")
    baseline.add_argument("--algorithm", default="bo", choices=["bo"], help="baseline algorithm (default: bo)")
    baseline.add_argument("--budget", type=int, default=30, help="true-evaluation budget (default 30)")
    baseline.add_argument("--seed", type=int, default=42, help="optimizer seed (default 42)")
    baseline.add_argument("--initial-designs", type=int, default=5, help="initial design count (default 5)")
    baseline.add_argument("--strategy", default="bayesian", choices=["bayesian", "random"], help="selection strategy (default: bayesian)")
    baseline.add_argument("--allow-existing", action="store_true", help="write into an existing run directory")
    baseline.set_defaults(func=_cmd_baseline)

    for name in ("route-a", "report"):
        p = sub.add_parser(name, help="declared by Issue #1; implemented in a later milestone")
        p.set_defaults(func=_unimplemented(name))
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
