"""One place that answers \"what has this authorization already spent?\".

Two record shapes exist and they do not mean the same thing:

  * an ABORT record (o0_batch_abort_B01.json) is written by hand from the raw case directory and
    states that one batch's own spend (basis BATCH_LOCAL);
  * a CRASH record (o0_batch_crash_B02.json) is written by the runner from the ledger summary,
    whose counters are AUTHORIZATION-CUMULATIVE: they already include everything carried forward
    from earlier batches, and the record lists which earlier records it absorbed.

Summing both shapes would count the carried-forward spend twice (1 + 23 = 24 starts when only 23
were spent), and reading only one shape would understate the bill. So every record is read with
its basis, the latest cumulative record is taken as the floor, and only batch-local records that
the cumulative record did not absorb are added on top. A record that cannot be read, or that
claims a basis this code does not know, is an error: a record that cannot be read is not a zero
bill and not a duplicate either.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

AUTHORIZATION_CUMULATIVE = "AUTHORIZATION_CUMULATIVE"
BATCH_LOCAL = "BATCH_LOCAL"


def sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_record(path: Path) -> Dict[str, Any]:
    """Return one record's own view: designs, starts, internal, basis, absorbed records."""
    row = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = str(row.get("schema") or "")
    if "abort_record" in schema or ("charged_starts_actual" in row
                                    and "ledger" not in row):
        return {"name": Path(path).name, "sha256": sha_file(path),
                "basis": BATCH_LOCAL,
                "designs": int(row.get("design_evaluations_actual") or 0),
                "starts": int(row.get("charged_starts_actual") or 0),
                "internal": int(row.get("internal_solver_cases_actual") or 0),
                "absorbed": [], "outcome": row.get("outcome"),
                "path": str(path)}
    if "crash" in schema or isinstance(row.get("ledger"), dict):
        ledger = row.get("ledger") or {}
        carried = ledger.get("carried_forward") or {}
        absorbed = [str(r.get("record")) for r in (carried.get("records") or [])
                    if r.get("record")]
        basis = str(ledger.get("spend_basis") or AUTHORIZATION_CUMULATIVE)
        if basis != AUTHORIZATION_CUMULATIVE:
            raise SystemExit("UNKNOWN_SPEND_BASIS: %s says %r; this code cannot tell whether its "
                             "counters already include earlier batches" % (path.name, basis))
        # design_attempts in an older crash record counted only this batch, while starts and
        # internal cases counted the whole authorization. Reconstruct the cumulative design
        # count from the two honest numbers instead of trusting the mixed one.
        designs = int(ledger.get("design_attempts") or 0)
        batch_designs = ledger.get("batch_design_attempts")
        carried_designs = int(ledger.get("carried_forward", {}).get("design_attempts") or 0)
        has_cumulative_designs = bool(ledger.get("design_attempts_is_cumulative"))
        if not has_cumulative_designs:
            designs = int(designs) + carried_designs
        if batch_designs is not None and int(batch_designs) != int(designs) - carried_designs:
            raise SystemExit("INCONSISTENT_CRASH_LEDGER: %s batch designs %r and cumulative "
                             "designs %r with %r carried forward" %
                             (path.name, batch_designs, designs, carried_designs))
        return {"name": Path(path).name, "sha256": sha_file(path),
                "basis": AUTHORIZATION_CUMULATIVE,
                "designs": designs,
                "starts": int(ledger.get("solver_starts_actual") or 0),
                "internal": int(ledger.get("internal_solver_cases_actual") or 0),
                "absorbed": absorbed,
                "outcome": row.get("exception_text") or row.get("outcome"),
                "path": str(path)}
    raise SystemExit("UNREADABLE_SPEND_RECORD: %s carries no spend this code can read" % path.name)


def records(run_root: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for pattern in ("o0_batch_abort_*.json", "o0_batch_crash_*.json"):
        for path in sorted(Path(run_root).glob(pattern)):
            out.append(read_record(path))
    return out


def authorization_spend(run_root: Path) -> Dict[str, Any]:
    """The bill for the authorization, counted once."""
    rows = records(run_root)
    cumulative = [r for r in rows if r["basis"] == AUTHORIZATION_CUMULATIVE]
    local = [r for r in rows if r["basis"] == BATCH_LOCAL]
    if cumulative:
        floor = cumulative[-1]
        absorbed = set()
        for row in cumulative:
            absorbed.update(row["absorbed"])
        # A cumulative record may not list the records it absorbed (the runner's ledger keeps a
        # summary, not a roster). Anything batch-local that existed on disk before the cumulative
        # record was written is already inside its counters, so it must not be added again.
        floor_mtime = Path(floor["path"]).stat().st_mtime
        for row in local:
            if Path(row["path"]).stat().st_mtime < floor_mtime:
                absorbed.add(row["name"])
        designs = floor["designs"]
        starts = floor["starts"]
        internal = floor["internal"]
        added: List[str] = []
        for row in local:
            if row["name"] in absorbed:
                continue
            designs += row["designs"]
            starts += row["starts"]
            internal += row["internal"]
            added.append(row["name"])
        base = {"record": floor["name"], "sha256": floor["sha256"],
                "basis": floor["basis"]}
    else:
        designs = starts = internal = 0
        for row in local:
            designs += row["designs"]
            starts += row["starts"]
            internal += row["internal"]
        added = [r["name"] for r in local]
        base = None
    return {"design_attempts": designs, "solver_starts": starts,
            "internal_solver_cases": internal,
            "basis_record": base, "added_batch_local": added,
            "records": rows,
            "rule": ("the latest AUTHORIZATION_CUMULATIVE record is the floor because its counters "
                     "already include what it carried forward; only batch-local records it did "
                     "not absorb are added, so nothing is counted twice")}