"""Command line entry point for the Phase I research workspace.

Only subcommands that are genuinely implemented are available. Implemented so
far: the P0 read-only audit, the P1 geometry check and the P1 OpenVSP geometry
export check. Later-stage subcommands return exit code 2 with an explicit
message so that no placeholder result can be mistaken for evidence.
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
    openvsp.set_defaults(func=_cmd_openvsp_check)

    for name in ("smoke", "doe", "baseline", "route-a", "report"):
        p = sub.add_parser(name, help="declared by Issue #1; implemented in a later milestone")
        p.set_defaults(func=_unimplemented(name))
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
