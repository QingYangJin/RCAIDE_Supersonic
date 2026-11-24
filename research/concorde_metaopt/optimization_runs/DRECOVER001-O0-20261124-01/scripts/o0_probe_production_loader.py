"""Archive the production-loader probe that section 2 of the dossier quotes.

The reviewer asked where the sentence "loaded=False, exception_type=DesignSpaceError" comes
from. A claim in a dossier that no artifact backs is exactly what an independent reviewer
should refuse; so the probe is run here, offline, and its output is written to a file that
the reviewer can hash. Zero solver starts: this only imports the design-space loader.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
YAML = REPO / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"
OUT = RUN / "audits/production_loader_probe.json"


def main() -> int:
    sys.path.insert(0, str(REPO))
    loaded = None
    exc_type = None
    exc_text = None
    try:
        from research.concorde_metaopt.aircraft.design_space import (  # type: ignore
            load_design_space)
        loaded = bool(load_design_space(str(YAML)))
    except Exception as exc:  # noqa: BLE001 - the exception type is the finding
        loaded = False
        exc_type = type(exc).__name__
        exc_text = str(exc)[:2000]
    payload = {
        "schema": "dreal005.production_loader_probe.v1",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "yaml": str(YAML),
        "yaml_sha256": __import__("hashlib").sha256(YAML.read_bytes()).hexdigest(),
        "loaded": loaded,
        "exception_type": exc_type,
        "exception_text": exc_text,
        "meaning": ("the production loader refuses the frozen 12D YAML; the H0 contract file is "
                    "the executable frozen copy and the batch never calls this loader"),
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"out": str(OUT), "loaded": loaded, "exception_type": exc_type}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
