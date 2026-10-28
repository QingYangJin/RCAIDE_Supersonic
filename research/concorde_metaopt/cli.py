"""Command line entry point for the Phase I research workspace.

Only subcommands that are genuinely implemented are available. The P0 scope is
the read-only audit; later-stage subcommands are declared but raise a clear
NotImplementedError so that no placeholder result can be mistaken for evidence.
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

    for name in ("geometry-check", "smoke", "doe", "baseline", "route-a", "report"):
        p = sub.add_parser(name, help="declared by Issue #1; implemented in a later milestone")
        p.set_defaults(func=_unimplemented(name))
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
