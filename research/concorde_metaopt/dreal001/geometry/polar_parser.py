"""VSPAERO .polar parser for the D-REAL-001 real-solver loop (pure parsing, no solver).

Two textual formats are observed in this programme:

* v6 / DegenGeom-era (VSPAERO 6.2.0): one header line with 20 columns
  "Beta Mach AoA Re/1e6 CL CDo CDi CDtot CS L/D E CFx CFy CFz CMx CMy CMz
  CMl CMm CMn" followed by one numeric row per alpha.  Rows carry one extra
  unlabeled column (StallFactor in the 7.x writer).
* v7 / surface+wake format (VSPAERO 7.2.2): two banner lines
  ("Surface Integration Forces and Moments -->" / group labels), one header
  line with 50 columns starting "Beta Mach AoA Re/1e6 CLo CLi CLtot CDo CDi
  CDtot ..." and one numeric row per alpha.

Design rules
------------
* Parsing is column-name based, never positional, so both formats and future
  column additions keep working.
* Non-finite payloads are preserved as float("nan") AND recorded as invalid
  tokens ("NAN(IND)", "NAN(INF)", "NaN"); the parser never fabricates a
  penalty value.
* No physical interpretation is made here: this module only extracts numbers.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

POLAR_PARSE_SCHEMA = "dreal001.polar_parse.v1"

REQUIRED_FIELDS = ("Beta", "Mach", "AoA")
TOTAL_ALIASES = {
    "CL": ("CLtot", "CL"),
    "CDi": ("CDi",),
    "CDo": ("CDo",),
    "CDtot": ("CDtot",),
    "CM": ("CMytot", "CMy", "CMm"),
    "CS": ("CStot", "CS"),
    "L_over_D": ("L/D", "LoDw"),
}

_NAN_RE = re.compile(r"^[+-]?(?:nan|NaN|NAN)(?:\([A-Za-z]+\))?$")
# Fortran style exponents ("1.23D+02") and plain E exponents are both accepted.
_EXP_RE = re.compile(r"[dD]([+-]?\d+)$")


class PolarParseError(ValueError):
    """Raised when a text blob is not a VSPAERO polar table at all."""


def _token_to_float(token: str) -> Tuple[float, Optional[str]]:
    """Return (value, invalid_token); invalid_token is the raw non-finite token."""
    raw = token.strip()
    if not raw:
        raise PolarParseError("empty numeric token")
    if _NAN_RE.match(raw):
        return float("nan"), raw
    candidate = raw
    if _EXP_RE.search(candidate):
        candidate = _EXP_RE.sub(lambda m: "e" + m.group(1), candidate)
    try:
        return float(candidate), None
    except ValueError as exc:  # pragma: no cover - defensive
        raise PolarParseError("token %r is not numeric" % raw) from exc


def _is_header(tokens: Sequence[str]) -> bool:
    if len(tokens) < 4:
        return False
    joined = {t.strip() for t in tokens}
    return {"Beta", "Mach", "AoA"}.issubset(joined) and ("CL" in joined or "CLtot" in joined)


def parse_polar_text(text: str, source: str = "<text>") -> Dict[str, Any]:
    """Parse polar text into a serialisable record (no file IO, no solver)."""
    lines = text.splitlines()
    sections: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            current = None
            continue
        tokens = stripped.split()
        if _is_header(tokens):
            current = {"header": tokens, "rows": [], "line": line_number}
            sections.append(current)
            continue
        if current is None:
            continue
        try:
            values = [_token_to_float(token) for token in tokens]
        except PolarParseError:
            current = None
            continue
        row: Dict[str, Any] = {}
        invalid_tokens: Dict[str, str] = {}
        for index, (value, invalid) in enumerate(values):
            if index < len(current["header"]):
                name = current["header"][index]
            else:
                name = "_extra_unlabeled"
                if name not in row:
                    row[name] = []
                row[name].append(value)
                continue
            row[name] = value
            if invalid is not None:
                invalid_tokens[name] = invalid
        row["_line"] = line_number
        row["_invalid_tokens"] = invalid_tokens
        current["rows"].append(row)

    usable = [section for section in sections if section["rows"]]
    if not usable:
        raise PolarParseError("no numeric polar table found in %s" % source)

    primary = usable[0]
    header = list(primary["header"])
    version = "v7" if "CLtot" in header else "v6" if "CL" in header else "unknown"
    rows = primary["rows"]
    invalid_rows = [index for index, row in enumerate(rows) if row.get("_invalid_tokens")]
    return {
        "schema": POLAR_PARSE_SCHEMA,
        "source": str(source),
        "format_version": version,
        "header": header,
        "sections": [
            {"index": index, "line": section["line"], "header": list(section["header"]),
             "row_count": len(section["rows"])}
            for index, section in enumerate(sections)
        ],
        "rows": rows,
        "row_count": len(rows),
        "invalid_row_count": len(invalid_rows),
        "invalid_row_indices": invalid_rows,
        "alpha_deg": [row.get("AoA") for row in rows],
    }


def parse_polar_file(path: str | Path) -> Dict[str, Any]:
    path = Path(path)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    record = parse_polar_text(text, source=str(path))
    record["path"] = str(path)
    record["bytes"] = len(raw)
    record["sha256"] = hashlib.sha256(raw).hexdigest()
    return record


CASE_KEY_FIELDS = ("Mach", "AoA", "Beta")


def case_key(row: Dict[str, Any]) -> Tuple[float, float, float]:
    values = []
    for name in CASE_KEY_FIELDS:
        value = field(row, name)
        values.append(round(float(value), 9) if value is not None else float("nan"))
    return (values[0], values[1], values[2])


def unique_case_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collapse repeated solver cases (same Mach/AoA/Beta) to the last occurrence.

    VSPAERO 7.2.2 merges command-line -fs lists with the .vspaero lists instead of
    replacing them, so one process start can solve a duplicated case matrix and the
    .polar then carries several identical blocks.  Lift matching must not treat the
    duplicates as a converged polar; this helper keeps one row per unique case and
    preserves the first-appearance ordering of the case keys.
    """
    order: List[Tuple[float, float, float]] = []
    latest: Dict[Tuple[float, float, float], Dict[str, Any]] = {}
    for row in rows:
        key = case_key(row)
        if key not in latest:
            order.append(key)
        latest[key] = row
    return [latest[key] for key in order]


def case_multiplicity(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for row in rows:
        key = case_key(row)
        label = "Mach=%g,AoA=%g,Beta=%g" % key
        counts[label] = counts.get(label, 0) + 1
    duplicates = {label: count for label, count in counts.items() if count > 1}
    return {"raw_row_count": len(rows), "unique_case_count": len(counts),
            "duplicate_case_labels": duplicates}


def field(row: Dict[str, Any], *names: str, default: Optional[float] = None) -> Optional[float]:
    """Fetch the first present numeric field from a parsed row."""
    for name in names:
        if name in row:
            value = row[name]
            if isinstance(value, list):
                return value[0] if value else default
            return value
    return default


def cltot(row: Dict[str, Any]) -> Optional[float]:
    return field(row, "CLtot", "CL")


def cdtot(row: Dict[str, Any]) -> Optional[float]:
    return field(row, "CDtot")


def row_is_valid(row: Dict[str, Any], required: Sequence[str] = ("AoA", "CLtot", "CDtot")) -> bool:
    """True only when every required column is present and finite (no penalty substitution)."""
    for name in required:
        candidates = TOTAL_ALIASES.get(name, (name,))
        value = field(row, *candidates)
        if value is None or not math.isfinite(float(value)):
            return False
    return True


def valid_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row_is_valid(row)]


def find_alpha_row(rows: Sequence[Dict[str, Any]], alpha_deg: float,
                   rel_tol: float = 1e-6) -> Optional[Dict[str, Any]]:
    for row in rows:
        alpha = field(row, "AoA")
        if alpha is None or not math.isfinite(float(alpha)):
            continue
        if abs(float(alpha) - float(alpha_deg)) <= rel_tol * max(1.0, abs(float(alpha_deg))):
            return row
    return None
