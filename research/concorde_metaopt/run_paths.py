"""Safe run-directory resolution shared by the CLI run commands.

Every run writes a self-contained evidence directory under
research/concorde_metaopt/optimization_runs/<run_id>. The run id therefore has
to be a single relative path segment: an absolute id, a parent reference or a
nested path could otherwise escape the approved output root and mix evidence
files from different runs.

A populated run directory is never reused: appending to an existing
evaluations.jsonl while rewriting summary.json/opt_trace.jsonl would make the
evidence bundle internally inconsistent. Callers that want to resume work must
choose a new run id; --allow-existing only permits an already created but empty
directory (for example one prepared by a job scheduler).
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

PathLike = Union[str, Path]


class RunPathError(ValueError):
    """Raised when a run id or run directory is not safe to use."""


def validate_run_id(run_id: str) -> str:
    """Return the run id after checking it is one safe relative path segment."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise RunPathError("run id must be a non-empty string")
    if run_id != run_id.strip():
        raise RunPathError("run id must not have leading or trailing whitespace")
    path = Path(run_id)
    if path.is_absolute() or path.drive or run_id[0] in ("/", "\\"):
        raise RunPathError("run id must be relative to the output root: %r" % (run_id,))
    if run_id in (".", "..") or "/" in run_id or "\\" in run_id:
        raise RunPathError("run id must be a single path segment: %r" % (run_id,))
    if path.name != run_id or len(path.parts) != 1:
        raise RunPathError("run id must be a single path segment: %r" % (run_id,))
    return run_id


def resolve_run_directory(
    output_root: PathLike,
    run_id: str,
    *,
    allow_existing: bool = False,
) -> Path:
    """Resolve and create an empty run directory inside the output root.

    Raises RunPathError for unsafe ids and FileExistsError when the target
    directory exists and is not an empty directory explicitly allowed by
    allow_existing.
    """
    name = validate_run_id(run_id)
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = (root / name).resolve()
    if run_dir.parent != root:
        raise RunPathError("run directory escapes the output root: %r" % (run_dir,))
    if run_dir.exists():
        if not run_dir.is_dir():
            raise FileExistsError("run path exists and is not a directory: %s" % run_dir)
        populated = any(run_dir.iterdir())
        if populated:
            raise FileExistsError(
                "run directory is not empty; refusing to mix evidence from multiple runs: %s"
                % run_dir
            )
        if not allow_existing:
            raise FileExistsError("run directory already exists: %s" % run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
