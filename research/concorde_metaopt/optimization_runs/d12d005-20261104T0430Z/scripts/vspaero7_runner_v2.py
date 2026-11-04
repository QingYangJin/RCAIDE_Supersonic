"""D-12D-005 A0-aero pre-gate runner library (zero solver start).

Scope: D-12D-005 A0 pre-check -- repair of the outer-120s-wrapper false kill
and of the LD-002 polar header/parser defect for VSPAERO 7.2.2 thin-wing
cases. This module only writes, normalizes and validates VSPAERO *setup*
files, post-processes already-existing polar/history text, and runs a static
pre-start gate over a case directory. It contains NO code path that forks
vspaero.exe / vspaero / SU2 / RCAIDE Mission; start_solver() always raises
SolverStartRefused so an accidental future call cannot start physics.

LD-001 fixes kept from v1frozen:
  1. legacy .vspaero lines without "=" are detected and rejected in strict
     mode, or normalized in place before contract-field injection;
  2. a non-zero "-setup" process return code is a hard gate (existing setup
     template does NOT authorize continuing);
  3. history header Sref_/Cref_/Bref_/Mach_/Rho_/Vinf_ are checked against the
     declared case values; mismatch => invalid data;
  4. every contract field is written explicitly and read back with the A2
     13-assertion set in config/run_config.json.

LD-002 fixes added here (D-12D-005):
  5. VSPAERO 7.2.2 polar files have TWO preamble group-label lines before the
     real 48-column header (Beta Mach AoA Re/1e6 CLo CLi CLtot CDo CDi CDtot
     ...). The parser locates that header by strict token identity and enforces
     the exact 48-column list; a legacy 6.2 header (CL/CS/CMl/CMm/CMn, no
     CLo/CLi/CLtot) is rejected with POLAR_LEGACY_62_HEADER_REJECTED instead of
     silently treating "CL" as "CLtot" or reading a nonexistent column.
  6. NaN / IND / INF / non-physical CLtot/CDtot, a Re/1e6 column inconsistent
     with the declared ReCref, or a Mach mismatch => INVALID data (never
     SOLVED); missing columns are reported by name.
  7. check-case-dir adds a strict pre-start gate: contract .vspaero readback
     (17 assertions), .vspgeom/.vkey/.csf existence and consistency, thin
     geometry record (GeometrySet=-1 / ThinGeometrySet=0), StopBeforeRun=1
     evidence, and no residual solver artifacts.
  8. validate_wrapper_outcome() rejects cases whose outer wrapper timeout is
     shorter than the contract max_wall_per_start_s (600 s) or that were killed
     by a wrapper (the D-12D-004 V1 120 s false-kill root cause).

No third-party imports; Python >= 3.9 compatible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "d12d005-runner-3"
CONTRACT_MU_KG_M_S = 1.42161308e-05
CONTRACT_SPEED_OF_SOUND_M_S = 295.0680184
CONTRACT_ALTITUDE_M = 18288.0

# 12D thin-wing frozen contract (A2 config/run_config.json + configs/task_fixed_cruise.yaml)
CONTRACT_12D = {
    "Sref": 358.25,
    "Cref": 18.489893,
    "Bref": 25.604638,
    "X_cg": 16.821978259514246,
    "Y_cg": 0.0,
    "Z_cg": 0.0,
    "Mach": 2.02,
    "AoA": 2.0,
    "Beta": 0.0,
    "ReCref": 89397005.8767656,
    "Vinf": 596.0373972278921,
    "Rho": 0.1153178340089936,
    "Symmetry": 0,
    "NumWakeNodes": 8,
    "WakeIters": 5,
    "WakeRelax": 1.0,
    "FarDist": -1.0,
}

# A2 run_config.json readback_assertions: 11 fields + exact Symmetry + rule => 13 assertions
READBACK_SPEC = {
    "Mach": ("rel", 1e-9),
    "Vinf": ("rel", 1e-9),
    "Rho": ("rel", 1e-9),
    "ReCref": ("rel", 1e-6),
    "Sref": ("rel", 1e-9),
    "Cref": ("rel", 1e-9),
    "Bref": ("rel", 1e-9),
    "X_cg": ("abs", 1e-6),
    "Y_cg": ("abs", 1e-9),
    "Z_cg": ("abs", 1e-6),
    "AoA": ("abs", 1e-9),
    "Symmetry": ("exact", 0.0),
}
# Extra contract fields asserted as hard gates (wake + Beta), rel 1e-9.
EXTRA_SPEC = {
    "Beta": ("abs", 1e-9),
    "NumWakeNodes": ("exact", 0.0),
    "WakeIters": ("exact", 0.0),
    "WakeRelax": ("rel", 1e-9),
    "FarDist": ("rel", 1e-9),
}
DEFAULT_LEAK_FIELDS = {
    "Vinf": 100.0,
    "Rho": 0.002377,
    "ReCref": 10000000.0,
}
SOLVER_ARTIFACT_GLOBS = (
    "*.polar",
    "*.history",
    "*.lod",
    "*.groups",
    "*.group.*",
    "*.adb",
    "*.fem",
)
POLAR_722_COLUMNS = (
    "Beta", "Mach", "AoA", "Re/1e6",
    "CLo", "CLi", "CLtot", "CDo", "CDi", "CDtot", "CSo", "CSi", "CStot",
    "L/D", "E",
    "CMox", "CMoy", "CMoz", "CMix", "CMiy", "CMiz", "CMxtot", "CMytot", "CMztot",
    "CFox", "CFoy", "CFoz", "CFix", "CFiy", "CFiz", "CFxtot", "CFytot", "CFztot",
    "CLwtot", "CDwtot", "CSwtot", "CLiw", "CDiw", "CSiw",
    "CFwxtot", "CFwytot", "CFwztot", "CFiwx", "CFiwy", "CFiwz",
    "LoDw", "Ew", "StallFactor",
)
POLAR_REQUIRED_COLUMNS = ("Beta", "Mach", "AoA", "Re/1e6", "CLo", "CLi", "CLtot", "CDo", "CDi", "CDtot", "E")
POLAR_MOMENT_COLUMNS = ("CMxtot", "CMytot", "CMztot")
LEGACY_62_POLAR_COLUMNS = (
    "Beta", "Mach", "AoA", "Re/1e6", "CL", "CDo", "CDi", "CDtot", "CS", "L/D", "E",
    "CFx", "CFy", "CFz", "CMx", "CMy", "CMz", "CMl", "CMm", "CMn",
)
POLAR_CLTOT_LIMIT = 10.0
POLAR_CDTOT_LIMIT = 10.0
MIN_WRAPPER_TIMEOUT_S = 600.0
CASE_GEOM_GLOB = "*geom_result*.csv"

HISTORY_HEADER_KEYS = (
    "Sref_",
    "Cref_",
    "Bref_",
    "Xcg_",
    "Ycg_",
    "Zcg_",
    "Mach_",
    "AoA_",
    "Beta_",
    "Rho_",
    "Vinf_",
)

ASSIGN_RE = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<val>.+?)\s*$")
LEGACY_RE = re.compile(r"^\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<val>[-+]?[0-9].*?)\s*$")
VECTOR_RE = re.compile(r"^\s*[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?(?:\s+[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?){1,}\s*$")
NONFINITE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:NAN|IND|INF(?:INITY)?)(?![A-Za-z0-9_])", re.IGNORECASE
)


class RunnerError(RuntimeError):
    """Base class for pre-gate runner errors."""


class SetupFormatError(RunnerError):
    """Setup text is not canonical 'key = value' format (LD-001)."""


class SetupCommandError(RunnerError):
    """The setup-generation command return code / artifact gate failed."""


class ContractViolation(RunnerError):
    """A declared contract field is missing, leaked a VSPAERO default, or mismatched."""

    def __init__(self, message, violations=None):
        super().__init__(message)
        self.violations = list(violations or [])


class DataQualityError(RunnerError):
    """Polar/history text contains non-finite data or wrong reference quantities."""


class FormatIsolationError(RunnerError):
    """A new-format run directory contains legacy .vspaero files."""


class SolverStartRefused(RunnerError):
    """Raised by every start path: this runner may not start physics."""


class UnknownSetupLine(RunnerError):
    """A non-blank, non-assignment, non-vector line was found in a setup file."""


class CaseGateError(RunnerError):
    """Strict pre-start case-directory gate failure (LD-002)."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


class WrapperGateError(RunnerError):
    """Outer wrapper outcome incomplete or timeout shorter than contract (LD-002)."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _number(text, *, source="<setup>"):
    token = str(text).strip()
    if NONFINITE_RE.search(token):
        raise ContractViolation("non-finite setup value %r in %s" % (token, source))
    try:
        return float(token)
    except (TypeError, ValueError):
        raise ContractViolation("not a number %r in %s" % (token, source))


def parse_setup_text(text, *, source="<text>"):
    """Parse a .vspaero setup file into fields + format findings.

    Returns dict with keys: fields, equals_lines, legacy_lines, malformed_lines,
    vector_rows, duplicate_keys.
    """
    fields = {}
    equals_lines = []
    legacy_lines = []
    malformed_lines = []
    vector_rows = []
    duplicates = []
    for lineno, raw in enumerate(str(text).splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("!"):
            continue
        match = ASSIGN_RE.match(raw)
        if match:
            key = match.group("key")
            if key in fields:
                duplicates.append((lineno, key))
            fields[key] = match.group("val").strip()
            equals_lines.append(lineno)
            continue
        match = LEGACY_RE.match(raw)
        if match:
            key = match.group("key")
            if key in fields:
                duplicates.append((lineno, key))
            fields[key] = match.group("val").strip()
            legacy_lines.append((lineno, raw))
            continue
        if VECTOR_RE.match(stripped):
            vector_rows.append((lineno, stripped))
            continue
        malformed_lines.append((lineno, raw))
    return {
        "source": str(source),
        "fields": fields,
        "equals_lines": equals_lines,
        "legacy_lines": legacy_lines,
        "malformed_lines": malformed_lines,
        "vector_rows": vector_rows,
        "duplicate_keys": duplicates,
    }


def _format_findings(parsed, *, limit=5):
    parts = []
    if parsed["legacy_lines"]:
        parts.append("legacy_lines=%r" % (parsed["legacy_lines"][:limit],))
    if parsed["malformed_lines"]:
        parts.append("malformed_lines=%r" % (parsed["malformed_lines"][:limit],))
    if parsed["duplicate_keys"]:
        parts.append("duplicate_keys=%r" % (parsed["duplicate_keys"][:limit],))
    return "; ".join(parts) if parts else "no format findings"


def assert_canonical(parsed):
    """Strict new-format gate: every assignment must use '='; no malformed lines."""
    if parsed["legacy_lines"]:
        raise SetupFormatError(
            "LD-001 legacy lines without '=' in %s: %s"
            % (parsed["source"], _format_findings(parsed))
        )
    if parsed["malformed_lines"]:
        raise SetupFormatError(
            "unknown setup lines in %s: %s"
            % (parsed["source"], _format_findings(parsed))
        )
    if parsed["duplicate_keys"]:
        raise SetupFormatError(
            "duplicate setup keys in %s: %s"
            % (parsed["source"], _format_findings(parsed))
        )
    return True


def normalize_legacy_text(text, *, source="<text>"):
    """Convert legacy 'key value' lines in place to 'key = value'.

    Line order and vector rows are preserved; malformed lines are an error.
    Returns (new_text, converted_line_count).
    """
    parsed = parse_setup_text(text, source=source)
    if parsed["malformed_lines"]:
        raise SetupFormatError(
            "cannot normalize unknown lines in %s: %s"
            % (source, _format_findings(parsed))
        )
    if parsed["duplicate_keys"]:
        raise SetupFormatError(
            "cannot normalize duplicate keys in %s: %s"
            % (source, _format_findings(parsed))
        )
    out = []
    converted = 0
    for raw in str(text).splitlines():
        stripped = raw.strip()
        match = ASSIGN_RE.match(raw)
        if match:
            out.append("%s = %s" % (match.group("key"), match.group("val").strip()))
            continue
        match = LEGACY_RE.match(raw)
        if match and match.group("key") in parsed["fields"]:
            out.append("%s = %s" % (match.group("key"), match.group("val").strip()))
            converted += 1
            continue
        out.append(stripped)
    new_text = "\n".join(out).rstrip("\n") + "\n"
    reparsed = parse_setup_text(new_text, source=source)
    assert_canonical(reparsed)
    return new_text, converted


def _format_value(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    number = float(value)
    if not math.isfinite(number):
        raise ContractViolation("refusing to write non-finite value %r" % (value,))
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return repr(number)


def rewrite_setup_values(text, updates, *, allow_legacy=True, source="<text>"):
    """Rewrite named fields in place, preserving line order/vector rows.

    Returns (new_text, report) where report records old/new values.
    """
    parsed = parse_setup_text(text, source=source)
    converted = 0
    if parsed["legacy_lines"]:
        if not allow_legacy:
            assert_canonical(parsed)
        text, converted = normalize_legacy_text(text, source=source)
        parsed = parse_setup_text(text, source=source)
    assert_canonical(parsed)
    missing = [key for key in updates if key not in parsed["fields"]]
    if missing:
        raise ContractViolation(
            "cannot rewrite missing setup fields %r in %s" % (missing, source)
        )
    report = {}
    lines = []
    for raw in str(text).splitlines():
        match = ASSIGN_RE.match(raw)
        if match:
            key = match.group("key")
            if key in updates:
                old = parsed["fields"][key]
                report[key] = {
                    "old": old,
                    "new": updates[key],
                    "rewritten": True,
                    "legacy_converted": converted > 0,
                }
                lines.append("%s = %s" % (key, _format_value(updates[key])))
                continue
            lines.append("%s = %s" % (key, match.group("val").strip()))
            continue
        lines.append(raw.strip())
    new_text = "\n".join(lines).rstrip("\n") + "\n"
    return new_text, report


def _compare(field, actual, expected, kind, tol):
    expected = float(expected)
    if kind == "exact":
        if actual != expected:
            return False, "exact mismatch expected=%r actual=%r" % (expected, actual)
        return True, "exact ok"
    if kind == "rel":
        scale = max(1.0, abs(expected))
        delta = abs(actual - expected)
        return delta <= tol * scale, "rel_delta=%.3e tol=%.3e" % (delta, tol * scale)
    delta = abs(actual - expected)
    return delta <= tol, "abs_delta=%.3e tol=%.3e" % (delta, tol)


def _spec_for(field):
    if field in READBACK_SPEC:
        return READBACK_SPEC[field]
    if field in EXTRA_SPEC:
        return EXTRA_SPEC[field]
    return ("rel", 1e-9)


def validate_setup_fields(fields, expected, *, source="<fields>"):
    """Assert the A2 13-assertion readback contract plus wake/Beta/thromo gates."""
    violations = []
    checked = []
    for field, target in expected.items():
        kind, tol = _spec_for(field)
        if field not in fields:
            violations.append({"field": field, "kind": "MISSING_FIELD", "expected": target})
            continue
        try:
            actual = _number(fields[field], source=source)
        except ContractViolation as exc:
            violations.append({"field": field, "kind": "NON_FINITE", "detail": str(exc)})
            continue
        ok, detail = _compare(field, actual, target, kind, tol)
        record = {
            "field": field,
            "expected": float(target),
            "actual": actual,
            "spec": "%s:%s" % (kind, tol),
            "detail": detail,
            "ok": bool(ok),
        }
        checked.append(record)
        if not ok:
            violations.append({"field": field, "kind": "MISMATCH", **record})
    # LD-001 rule: VSPAERO defaults may never enter a case whose declaration differs.
    for field, default in DEFAULT_LEAK_FIELDS.items():
        target = expected.get(field)
        if target is None or field not in fields:
            continue
        try:
            actual = _number(fields[field])
        except ContractViolation:
            continue
        if abs(actual - default) <= 1e-12 * max(1.0, abs(default)) and float(target) != default:
            violations.append(
                {
                    "field": field,
                    "kind": "SETUP_DEFAULT_LEAK",
                    "expected": float(target),
                    "actual": actual,
                    "detail": "VSPAERO default %r was not replaced" % (default,),
                }
            )
    # thermodynamic self-consistency (A2 frozen_flow)
    if all(key in expected for key in ("Mach", "Vinf", "ReCref", "Cref")):
        derived = {}
        try:
            mach = float(expected["Mach"])
            vinf = float(expected["Vinf"])
            rec = float(expected["ReCref"])
            cref = float(expected["Cref"])
            if mach > 0:
                derived["speed_of_sound_m_s"] = vinf / mach
            if all(key in expected for key in ("Rho",)):
                derived["mu_kg_m_s"] = float(expected["Rho"]) * vinf * cref / rec
            if "speed_of_sound_m_s" in derived:
                ok, detail = _compare(
                    "speed_of_sound_m_s",
                    derived["speed_of_sound_m_s"],
                    CONTRACT_SPEED_OF_SOUND_M_S,
                    "rel",
                    1e-3,
                )
                if not ok:
                    violations.append(
                        {"field": "speed_of_sound_m_s", "kind": "THERMO_INCONSISTENT", "detail": detail}
                    )
            if "mu_kg_m_s" in derived:
                ok, detail = _compare(
                    "mu_kg_m_s", derived["mu_kg_m_s"], CONTRACT_MU_KG_M_S, "rel", 1e-3
                )
                if not ok:
                    violations.append(
                        {"field": "mu_kg_m_s", "kind": "THERMO_INCONSISTENT", "detail": detail}
                    )
        except (TypeError, ValueError) as exc:
            violations.append({"field": "thermo", "kind": "THERMO_PARSE", "detail": str(exc)})
    if violations:
        raise ContractViolation(
            "SETUP_READBACK_FAIL in %s: %d violation(s): %r"
            % (source, len(violations), violations[:6]),
            violations=violations,
        )
    return {"status": "PASS", "source": str(source), "fields_checked": checked, "assertions": len(checked)}


def read_setup_file(path, expected=CONTRACT_12D, *, require_canonical=True):
    """Read a setup file and enforce the readback contract."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    parsed = parse_setup_text(text, source=str(path))
    if require_canonical:
        assert_canonical(parsed)
    report = validate_setup_fields(parsed["fields"], expected, source=str(path))
    report.update(
        {
            "path": str(Path(path).resolve()),
            "bytes": Path(path).stat().st_size,
            "sha256": sha256_file(path),
            "line_count": len(text.splitlines()),
            "vector_rows": len(parsed["vector_rows"]),
            "legacy_lines": len(parsed["legacy_lines"]),
            "has_equals_format": True,
        }
    )
    return report


def inject_contract_fields(
    source_path,
    target_path,
    expected=None,
    *,
    allow_legacy=True,
    expected_source="CONTRACT_12D",
):
    """Normalize (if needed), write every contract field, then read it back."""
    expected = dict(CONTRACT_12D if expected is None else expected)
    text = Path(source_path).read_text(encoding="utf-8", errors="replace")
    parsed = parse_setup_text(text, source=str(source_path))
    legacy_found = len(parsed["legacy_lines"])
    if legacy_found and not allow_legacy:
        raise SetupFormatError(
            "refusing legacy input %s (allow_legacy=False): %s"
            % (source_path, _format_findings(parsed))
        )
    new_text, rewrite = rewrite_setup_values(
        text, expected, allow_legacy=allow_legacy, source=str(source_path)
    )
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_text, encoding="utf-8", newline="\n")
    readback = read_setup_file(target, expected, require_canonical=True)
    readback["injected_from"] = str(Path(source_path).resolve())
    readback["expected_source"] = expected_source
    readback["legacy_lines_normalized"] = legacy_found
    readback["rewrite"] = rewrite
    readback["target_sha256"] = sha256_file(target)
    return readback


def require_setup_success(returncode, setup_path, *, require_nonempty=True):
    """LD-001 gate: a failed -setup command never authorizes continuing."""
    path = Path(setup_path)
    if int(returncode) != 0:
        raise SetupCommandError(
            "SETUP_RETURNCODE_FAIL rc=%r setup_path=%s exists=%s"
            % (returncode, path, path.is_file())
        )
    if not path.is_file():
        raise SetupCommandError("SETUP_ARTIFACT_MISSING rc=0 setup_path=%s" % (path,))
    if require_nonempty and path.stat().st_size == 0:
        raise SetupCommandError("SETUP_ARTIFACT_EMPTY rc=0 setup_path=%s" % (path,))
    return {
        "status": "PASS",
        "returncode": 0,
        "setup_path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def start_solver(*args, **kwargs):
    """Permanently refused: D-12D-004 pre-gate phase may not start physics."""
    raise SolverStartRefused(
        "REFUSED: runner has no solver-start path before A1/A5/A3 gates pass; "
        "starts_used must remain 0 during this task"
    )


def _polar_tokens(line):
    return [tok for tok in line.replace("\t", " ").split(" ") if tok]


def _identify_polar_header(lines, *, source="<polar>"):
    """Locate the real VSPAERO 7.2.2 header line, or reject a legacy header."""
    legacy_lines = []
    for index, line in enumerate(lines):
        tokens = _polar_tokens(line)
        if not tokens:
            continue
        token_set = set(tokens)
        if {"CLtot", "CDtot", "Mach", "AoA"} <= token_set:
            return index, tokens
        if {"CL", "CMm"} <= token_set and "CLtot" not in token_set:
            legacy_lines.append(index)
    if legacy_lines:
        raise DataQualityError(
            "POLAR_LEGACY_62_HEADER_REJECTED: legacy VSPAERO 6.2 polar header at line(s) %r in %s; "
            "7.2.2 output requires the 48-column CLo/CLi/CLtot header"
            % ([i + 1 for i in legacy_lines], source)
        )
    raise DataQualityError("POLAR_HEADER_MISSING: no 7.2.2 header with CLtot/CDtot/Mach/AoA in %s" % source)


def _parse_polar_rows(lines, header_index, *, source="<polar>"):
    rows = []
    nonfinite = []
    malformed = []
    width = len(POLAR_722_COLUMNS)
    for offset, line in enumerate(lines[header_index + 1:]):
        if not line.strip():
            continue
        line_no = header_index + offset + 2
        tokens = _polar_tokens(line)
        if len(tokens) != width:
            malformed.append({"line": line_no, "expected_tokens": width, "actual_tokens": len(tokens)})
            continue
        values = {}
        for name, token in zip(POLAR_722_COLUMNS, tokens):
            if NONFINITE_RE.search(token):
                values[name] = None
                nonfinite.append({"line": line_no, "column": name, "token": token})
                continue
            try:
                values[name] = float(token)
            except ValueError:
                values[name] = None
                malformed.append({"line": line_no, "column": name, "token": token})
        rows.append(values)
    if malformed:
        raise DataQualityError("POLAR_ROW_WIDTH_INVALID: %r in %s" % (malformed[:8], source))
    return rows, nonfinite


def _polar_header_and_rows(path):
    """VSPAERO 7.2.2 polar reader: (header, rows, nonfinite, width)."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    index, header = _identify_polar_header(lines, source=str(path))
    if index != 2:
        raise DataQualityError(
            "POLAR_HEADER_ROW_UNEXPECTED: header found on line %d of %s; VSPAERO 7.2.2 requires the 48-column header on line 3"
            % (index + 1, path),
        )
    if list(header) != list(POLAR_722_COLUMNS):
        raise DataQualityError(
            "POLAR_HEADER_TOKENS_UNEXPECTED: got %d tokens %r in %s; expected the VSPAERO 7.2.2 48-column header"
            % (len(header), header[:12], path)
        )
    rows, nonfinite = _parse_polar_rows(lines, index, source=str(path))
    return header, rows, nonfinite, len(POLAR_722_COLUMNS)


def _spec_value(expected, name):
    value = expected.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _close(actual, expected, *, rel=0.0, abs_=0.0):
    return abs(float(actual) - float(expected)) <= max(abs_, rel * abs(float(expected)))


def validate_polar_file(path, expected):
    """Strict VSPAERO 7.2.2 polar validator (LD-002).

    Rejects a legacy 6.2 header, an unexpected token list, short/long rows,
    NaN/IND/INF values, missing CLtot/CDtot, non-physical coefficients, and a
    Re/1e6 column inconsistent with the declared ReCref (rel 1e-6).
    """
    header, rows, nonfinite, width = _polar_header_and_rows(path)
    if nonfinite:
        raise DataQualityError("POLAR_NONFINITE: %r in %s" % (nonfinite[:8], path))
    if not rows:
        raise DataQualityError("POLAR_NO_DATA_ROWS: %s" % path)
    missing = [name for name in POLAR_REQUIRED_COLUMNS if name not in header]
    if missing:
        raise DataQualityError("POLAR_COLUMNS_MISSING: %r in %s" % (missing, path))
    expected_re = _spec_value(expected, "ReCref")
    expected_mach = _spec_value(expected, "Mach")
    checks = []
    for index, row in enumerate(rows):
        label = "row[%d]" % (index + 1)
        re_million = row.get("Re/1e6")
        if re_million is None or re_million <= 0.0:
            raise DataQualityError("POLAR_RE_MISMATCH: %s Re/1e6=%r in %s" % (label, re_million, path))
        actual_re = re_million * 1.0e6
        if expected_re is not None and not _close(actual_re, expected_re, rel=1.0e-6):
            raise DataQualityError(
                "POLAR_RE_MISMATCH: %s Re=%.6f vs contract ReCref=%.6f (rel 1e-6) in %s"
                % (label, actual_re, expected_re, path)
            )
        if expected_mach is not None and not _close(row["Mach"], expected_mach, rel=1.0e-6):
            raise DataQualityError(
                "POLAR_MACH_MISMATCH: %s Mach=%r vs contract %r in %s"
                % (label, row["Mach"], expected_mach, path)
            )
        cltot = row["CLtot"]
        cdtot = row["CDtot"]
        if cltot is None or cdtot is None:
            raise DataQualityError("POLAR_REQUIRED_VALUE_MISSING: %s CLtot/CDtot in %s" % (label, path))
        if abs(cltot) > POLAR_CLTOT_LIMIT:
            raise DataQualityError(
                "POLAR_NONPHYSICAL: %s |CLtot|=%.6f > %.1f in %s" % (label, abs(cltot), POLAR_CLTOT_LIMIT, path)
            )
        if abs(cdtot) > POLAR_CDTOT_LIMIT:
            raise DataQualityError(
                "POLAR_NONPHYSICAL: %s |CDtot|=%.6f > %.1f in %s" % (label, abs(cdtot), POLAR_CDTOT_LIMIT, path)
            )
        checks.append(
            {
                "row": index + 1,
                "AoA": row["AoA"],
                "CLo": row["CLo"],
                "CLi": row["CLi"],
                "CLtot": cltot,
                "CDo": row["CDo"],
                "CDi": row["CDi"],
                "CDtot": cdtot,
                "CMztot": row["CMztot"],
                "Re": actual_re,
            }
        )
    return {
        "status": "PASS",
        "path": str(Path(path).resolve()),
        "schema": "vspaero-7.2.2-48-column",
        "header_token_count": len(header),
        "rows": len(rows),
        "checks": checks,
        "sha256": sha256_file(path),
    }


def parse_polar_structure(path, expected=None):
    """Structure-only VSPAERO 7.2.2 polar parser (LD-002).

    Returns the 48-column header and parsed rows without applying numerical
    thresholds, so evidence can archive a structurally valid but physically
    non-physical polar (e.g. the D-12D-004 V7-00 file) without weakening
    validate_polar_file. Never upgrades a case to physically valid.
    """
    header, rows, nonfinite, width = _polar_header_and_rows(path)
    if not rows:
        raise DataQualityError("POLAR_NO_DATA_ROWS: %s" % path)
    return {
        "status": "PASS_STRUCTURE_ONLY",
        "path": str(Path(path).resolve()),
        "header_token_count": len(header),
        "rows": len(rows),
        "width": width,
        "nonfinite_tokens": len(nonfinite),
        "rows_preview": [
            {
                "Mach": row.get("Mach"),
                "AoA": row.get("AoA"),
                "CLtot": row.get("CLtot"),
                "CDtot": row.get("CDtot"),
            }
            for row in rows[:5]
        ],
        "sha256": sha256_file(path),
        "physical_validation": "NOT_APPLIED",
        "expected_keys_ignored": sorted(dict(expected or {})),
    }


def _history_header_fields(text):
    fields = {}
    for lineno, raw in enumerate(str(text).splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        if tokens and tokens[0] in HISTORY_HEADER_KEYS and len(tokens) >= 2:
            token = tokens[1]
            if NONFINITE_RE.search(token):
                raise DataQualityError(
                    "HISTORY_NONFINITE line=%d field=%s token=%r" % (lineno, tokens[0], token)
                )
            try:
                fields[tokens[0]] = float(token)
            except ValueError:
                raise DataQualityError(
                    "HISTORY_NON_NUMERIC line=%d field=%s token=%r" % (lineno, tokens[0], token)
                )
    missing = [key for key in HISTORY_HEADER_KEYS if key not in fields]
    if missing:
        raise DataQualityError("HISTORY_HEADER_FIELDS_MISSING: %r" % (missing,))
    return fields


def validate_history_file(path, expected):
    """Reject NaN history and history whose Sref_/Mach_/Rho_/Vinf_ imply a different Re."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if NONFINITE_RE.search(text):
        # history may legitimately contain no non-finite tokens; any occurrence is a fail
        raise DataQualityError("HISTORY_NONFINITE_TEXT")
    fields = _history_header_fields(text)
    checks = (
        ("Sref_", expected["Sref"], "rel", 1e-6),
        ("Cref_", expected["Cref"], "rel", 1e-6),
        ("Bref_", expected["Bref"], "rel", 1e-6),
        ("Xcg_", expected["X_cg"], "abs", 1e-5),
        ("Ycg_", expected["Y_cg"], "abs", 1e-9),
        ("Zcg_", expected["Z_cg"], "abs", 1e-5),
        ("Mach_", expected["Mach"], "rel", 1e-6),
        ("AoA_", expected["AoA"], "abs", 1e-6),
        ("Beta_", expected["Beta"], "abs", 1e-6),
        ("Rho_", expected["Rho"], "rel", 1e-5),
        ("Vinf_", expected["Vinf"], "rel", 1e-6),
    )
    for key, target, kind, tol in checks:
        ok, detail = _compare(key, fields[key], target, kind, tol)
        if not ok:
            raise DataQualityError("HISTORY_REFERENCE_MISMATCH field=%s %s" % (key, detail))
    if "ReCref" in expected:
        mu = CONTRACT_MU_KG_M_S
        derived_re = fields["Rho_"] * fields["Vinf_"] * fields["Cref_"] / mu
        ok, detail = _compare("ReCref_derived", derived_re, expected["ReCref"], "rel", 1e-4)
        if not ok:
            raise DataQualityError("HISTORY_RE_MISMATCH %s" % (detail,))
    return {
        "status": "PASS",
        "path": str(Path(path).resolve()),
        "sha256": sha256_file(path),
        "reference_fields": {key: fields[key] for key in HISTORY_HEADER_KEYS},
    }


def find_solver_artifacts(directory):
    root = Path(directory)
    found = []
    for pattern in SOLVER_ARTIFACT_GLOBS:
        for path in sorted(root.rglob(pattern)):
            found.append({"path": str(path.resolve()), "pattern": pattern})
    return found


def assert_no_solver_artifacts(directory):
    found = find_solver_artifacts(directory)
    if found:
        raise DataQualityError("SOLVER_ARTIFACTS_PRESENT: %r" % (found[:8],))
    return {"status": "PASS", "directory": str(Path(directory).resolve()), "solver_artifacts": []}


def assert_new_format_only(directory):
    """Format isolation: a new-format run dir may not contain legacy .vspaero files."""
    root = Path(directory)
    bad = []
    checked = []
    for path in sorted(root.rglob("*.vspaero")):
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_setup_text(text, source=str(path))
        checked.append(str(path.resolve()))
        if parsed["legacy_lines"] or parsed["malformed_lines"] or parsed["duplicate_keys"]:
            bad.append({"path": str(path.resolve()), "findings": _format_findings(parsed)})
    if bad:
        raise FormatIsolationError("LEGACY_FORMAT_IN_NEW_RUN_DIR: %r" % (bad[:8],))
    return {"status": "PASS", "directory": str(root.resolve()), "setup_files_checked": checked}


def _case_files(case_dir, *, setup=None, vkey=None, csf=None, geom_result=None):
    root = Path(case_dir)
    if not root.is_dir():
        raise CaseGateError("CASE_DIR_MISSING", str(root))

    def _pick(explicit, pattern, code):
        if explicit is not None:
            path = Path(explicit)
            if not path.is_file():
                raise CaseGateError(code, "explicit path missing: %s" % path)
            return path
        hits = sorted(root.glob(pattern))
        if not hits:
            raise CaseGateError(code, "no %s file in %s" % (pattern, root))
        if len(hits) > 1:
            raise CaseGateError(code.replace("_MISSING", "_AMBIGUOUS"), "multiple %s files: %r" % (pattern, [str(h) for h in hits]))
        return hits[0]

    return {
        "case_dir": root.resolve(),
        "setup": _pick(setup, "*_contract.vspaero", "CASE_SETUP_MISSING").resolve(),
        "vkey": _pick(vkey, "*.vkey", "CASE_VKEY_MISSING").resolve(),
        "csf": _pick(csf, "*.csf", "CASE_CSF_MISSING").resolve(),
        "geom_result": _pick(geom_result, CASE_GEOM_GLOB, "CASE_GEOM_RESULT_MISSING").resolve(),
    }


def parse_geom_result_csv(path):
    """Read the two-column VSPAERO geom-result CSV into a {name: first_value} dict."""
    fields = {}
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 2 and parts[0]:
            fields.setdefault(parts[0], parts[1])
    return fields


def validate_thin_geometry_record(fields, *, expected=True, source="<geom_result>"):
    if "GeometrySet" not in fields or "ThinGeometrySet" not in fields:
        raise DataQualityError("CASE_THIN_GEOMETRY_MISSING: GeometrySet/ThinGeometrySet absent in %s" % source)
    geometry_set = fields["GeometrySet"]
    thin_set = fields["ThinGeometrySet"]
    if expected and (geometry_set != "-1" or thin_set != "0"):
        raise DataQualityError(
            "CASE_THIN_GEOMETRY_MISMATCH: GeometrySet=%r ThinGeometrySet=%r in %s "
            "(a thin lifting surface requires -1/0; 0/1 means the thick body set was used)"
            % (geometry_set, thin_set, source)
        )
    return {"GeometrySet": geometry_set, "ThinGeometrySet": thin_set}


def validate_vkey(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise DataQualityError("CASE_VKEY_INVALID: empty %s" % path)
    if "VSPGEOM" not in lines[0] or "v3" not in lines[0]:
        raise DataQualityError("CASE_VKEY_INVALID: unknown header %r in %s" % (lines[0], path))
    if len(lines) < 2:
        raise DataQualityError("CASE_VKEY_INVALID: no vspgeom path line in %s" % path)
    return {
        "path": str(Path(path).resolve()),
        "schema": "VSPGEOM v3",
        "vspgeom_path": lines[1],
        "bytes": Path(path).stat().st_size,
        "sha256": sha256_file(path),
    }


def validate_csf(path):
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig", errors="replace").strip()
    if not text:
        raise DataQualityError("CASE_CSF_INVALID: empty %s" % path)
    if text.lower() != "0 control surfaces":
        raise DataQualityError(
            "CASE_CSF_INVALID: %r in %s; a thin lifting-surface case must be exactly one line, 0 Control Surfaces"
            % (text[:80], path),
        )
    return {"path": str(Path(path).resolve()), "bytes": len(raw), "control_surfaces": 0, "sha256": hashlib.sha256(raw).hexdigest()}


def _recorded_vspgeom(evidence_case):
    if not isinstance(evidence_case, dict):
        return None
    bundle = evidence_case.get("execution_bundle") or {}
    thin = evidence_case.get("thin_geometry") or {}
    sha = bundle.get("vspgeom_sha256") or thin.get("sha256_raw") or thin.get("sha256")
    size = bundle.get("vspgeom_bytes") or thin.get("bytes_raw") or thin.get("bytes")
    if not sha and size is None:
        return None
    return {"sha256": sha, "bytes": int(size) if size is not None else None}


def resolve_case_vspgeom(case_dir, *, evidence_case=None, explicit=None, verify_recorded=True):
    root = Path(case_dir)
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            raise CaseGateError("CASE_VSPGEOM_MISSING", "explicit vspgeom missing: %s" % path)
        return {"path": str(path.resolve()), "source": "explicit", "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    local = sorted(root.glob("*.vspgeom"))
    if len(local) == 1:
        path = local[0]
        actual_bytes = path.stat().st_size
        actual_sha = sha256_file(path)
        recorded = _recorded_vspgeom(evidence_case)
        if verify_recorded and recorded:
            if recorded.get("sha256") and actual_sha != recorded["sha256"]:
                raise CaseGateError(
                    "CASE_VSPGEOM_SHA_MISMATCH",
                    "%s sha256 %s != evidence-recorded %s" % (path, actual_sha, recorded["sha256"]),
                )
            if recorded.get("bytes") is not None and int(recorded["bytes"]) != actual_bytes:
                raise CaseGateError(
                    "CASE_VSPGEOM_BYTES_MISMATCH",
                    "%s bytes %d != evidence-recorded %d" % (path, actual_bytes, int(recorded["bytes"])),
                )
        return {
            "path": str(path.resolve()),
            "source": "case_dir",
            "bytes": actual_bytes,
            "sha256": actual_sha,
            "evidence_record_verified": bool(recorded),
        }
    if len(local) > 1:
        raise CaseGateError("CASE_VSPGEOM_AMBIGUOUS", "multiple *.vspgeom in %s" % root)
    if evidence_case is not None:
        bundle = evidence_case.get("execution_bundle") or {}
        thin = evidence_case.get("thin_geometry") or {}
        external = bundle.get("vspgeom_external_path") or thin.get("external_path")
        recorded_sha = bundle.get("vspgeom_sha256") or thin.get("sha256")
        recorded_bytes = bundle.get("vspgeom_bytes") or thin.get("bytes")
        if external:
            path = Path(external)
            if not path.is_file():
                raise CaseGateError("CASE_VSPGEOM_MISSING", "recorded external vspgeom missing: %s" % path)
            actual_sha = sha256_file(path)
            actual_bytes = path.stat().st_size
            if verify_recorded and recorded_sha and actual_sha != recorded_sha:
                raise CaseGateError("CASE_VSPGEOM_SHA_MISMATCH", "%s sha256 %s != recorded %s" % (path, actual_sha, recorded_sha))
            if verify_recorded and recorded_bytes and int(recorded_bytes) != actual_bytes:
                raise CaseGateError("CASE_VSPGEOM_BYTES_MISMATCH", "%s bytes %d != recorded %d" % (path, actual_bytes, int(recorded_bytes)))
            return {"path": str(path.resolve()), "source": "evidence_bundle", "bytes": actual_bytes, "sha256": actual_sha}
    raise CaseGateError("CASE_VSPGEOM_MISSING", "no local *.vspgeom and no recorded external vspgeom for %s" % root)


def _load_case_expected(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "contract" in data:
        return dict(data["contract"])
    if "expected" in data:
        return dict(data["expected"])
    return dict(data)


def check_case_dir(case_dir, *, expected=None, evidence=None, case_id=None, setup=None, vkey=None, csf=None, geom_result=None, require_thin=True, min_wrapper_timeout_s=MIN_WRAPPER_TIMEOUT_S):
    """Strict pre-start gate over one VSPAERO 7.2.2 thin-wing case directory."""
    files = _case_files(case_dir, setup=setup, vkey=vkey, csf=csf, geom_result=geom_result)
    evidence_case = None
    evidence_report = {}
    if evidence is not None:
        data = json.loads(Path(evidence).read_text(encoding="utf-8"))
        cases = data.get("cases") or []
        wanted = case_id or files["case_dir"].name
        for item in cases:
            if item.get("case_id") == wanted or Path(str(item.get("case_dir", ""))).name == wanted:
                evidence_case = item
                break
        if evidence_case is None and len(cases) == 1:
            evidence_case = cases[0]
        evidence_report = {
            "path": str(Path(evidence).resolve()),
            "artifact_kind": data.get("artifact_kind"),
            "status": data.get("status"),
            "stop_before_run": data.get("stop_before_run"),
            "solver_processes_started": data.get("solver_processes_started"),
            "solver_starts": data.get("solver_starts"),
        }
    if not evidence_report:
        embedded = files["case_dir"] / "setup_gen_report.json"
        if embedded.is_file():
            data = json.loads(embedded.read_text(encoding="utf-8"))
            evidence_case = data.get("case") if isinstance(data.get("case"), dict) else None
            evidence_report = {
                "path": str(embedded.resolve()),
                "artifact_kind": data.get("artifact_kind"),
                "status": data.get("status"),
                "stop_before_run": data.get("stop_before_run"),
                "solver_processes_started": data.get("solver_processes_started"),
            "solver_starts": data.get("solver_starts"),
            }
    if expected is None:
        expected_path = files["case_dir"] / "expected.json"
        expected = _load_case_expected(expected_path) if expected_path.is_file() else dict(CONTRACT_12D)
    expected = dict(expected)
    readback = read_setup_file(files["setup"], expected)
    if readback.get("assertions") != len(expected):
        raise CaseGateError(
            "CASE_READBACK_ASSERTION_COUNT",
            "%r assertions != %d contract fields in %s" % (readback.get("assertions"), len(expected), files["setup"]),
        )
    if not evidence_report:
        raise CaseGateError("CASE_STOP_BEFORE_RUN_EVIDENCE_MISSING", "no --evidence and no setup_gen_report.json in %s" % files["case_dir"])
    if evidence_report.get("stop_before_run") != 1:
        raise CaseGateError("CASE_STOP_BEFORE_RUN_MISSING", "evidence stop_before_run=%r from %s" % (evidence_report.get("stop_before_run"), evidence_report.get("path")))
    starts = evidence_report.get("solver_processes_started", evidence_report.get("solver_starts"))
    if starts is None:
        raise CaseGateError(
            "CASE_SOLVER_PROCESS_EVIDENCE_MISSING",
            "evidence %s has no solver_processes_started/solver_starts field; zero-solver evidence must be explicit (fail closed)"
            % (evidence_report.get("path"),),
        )
    if int(starts) != 0:
        raise CaseGateError("CASE_SOLVER_PROCESS_RECORDED", "evidence solver_processes_started=%r" % (starts,))
    vkey_report = validate_vkey(files["vkey"])
    csf_report = validate_csf(files["csf"])
    geom_report = parse_geom_result_csv(files["geom_result"])
    thin_report = validate_thin_geometry_record(geom_report, expected=require_thin, source=str(files["geom_result"]))
    vspgeom = resolve_case_vspgeom(files["case_dir"], evidence_case=evidence_case)
    vkey_target = Path(vkey_report["vspgeom_path"])
    if not vkey_target.is_absolute():
        vkey_target = files["case_dir"] / vkey_target
    try:
        vkey_resolved = vkey_target.resolve(strict=True)
    except OSError:
        raise CaseGateError(
            "CASE_VKEY_GEOM_MISMATCH",
            "vkey target %r does not exist (case dir %s); the execution bundle must rewrite the vkey path to the local .vspgeom"
            % (vkey_report["vspgeom_path"], files["case_dir"]),
        )
    geom_resolved = Path(vspgeom["path"]).resolve()
    if vkey_resolved != geom_resolved:
        raise CaseGateError(
            "CASE_VKEY_GEOM_MISMATCH",
            "vkey points at %r (resolved %s) but the resolved vspgeom is %s"
            % (vkey_report["vspgeom_path"], vkey_resolved, geom_resolved),
        )
    wrapper = None
    if evidence_case is not None:
        wrapper = evidence_case.get("wrapper") or evidence_case.get("execution") or {}
        timeout = wrapper.get("wrapper_timeout_s", wrapper.get("timeout_s"))
        if timeout is not None and float(timeout) < float(min_wrapper_timeout_s):
            raise CaseGateError(
                "CASE_WRAPPER_TIMEOUT_TOO_SHORT",
                "wrapper_timeout_s=%r < %r; the D-12D-004 V1 120 s outer wrapper false-killed the solver"
                % (timeout, min_wrapper_timeout_s),
            )
    artifacts = assert_no_solver_artifacts(files["case_dir"])
    return {
        "status": "PASS",
        "case_dir": str(files["case_dir"]),
        "case_id": (evidence_case or {}).get("case_id", files["case_dir"].name),
        "setup": {"path": str(files["setup"]), "sha256": sha256_file(files["setup"]), "readback_assertions": readback["assertions"]},
        "vspgeom": vspgeom,
        "vkey": vkey_report,
        "csf": csf_report,
        "geom_result": {"path": str(files["geom_result"]), **thin_report},
        "stop_before_run": evidence_report.get("stop_before_run"),
        "solver_processes_started": starts,
        "wrapper": wrapper,
        "solver_artifacts": artifacts,
        "evidence": evidence_report,
    }


def validate_wrapper_outcome(record, *, min_wrapper_timeout_s=MIN_WRAPPER_TIMEOUT_S):
    """Reject wrapper-level false kills from recorded fields only (no solver run)."""
    timeout = record.get("wrapper_timeout_s", record.get("timeout_s"))
    if timeout is None:
        raise WrapperGateError("CASE_WRAPPER_TIMEOUT_MISSING", "record has no wrapper_timeout_s/timeout_s")
    if float(timeout) < float(min_wrapper_timeout_s):
        raise WrapperGateError(
            "CASE_WRAPPER_TIMEOUT_TOO_SHORT",
            "wrapper_timeout_s=%r < contract max_wall_per_start_s=%r" % (timeout, min_wrapper_timeout_s),
        )
    wall = record.get("wall_seconds", record.get("elapsed_seconds"))
    if wall is not None and float(wall) >= float(timeout):
        raise WrapperGateError("CASE_WRAPPER_KILLED_AT_TIMEOUT", "wall_seconds=%r >= wrapper_timeout_s=%r" % (wall, timeout))
    return_code = record.get("returncode", record.get("solver_returncode"))
    killed = record.get("killed", record.get("timeout_killed", record.get("timed_out", False)))
    if killed or return_code is None or int(return_code) < 0:
        raise WrapperGateError("CASE_KILLED_BY_WRAPPER", "killed=%r returncode=%r" % (killed, return_code))
    if record.get("completed") is False:
        raise WrapperGateError("CASE_WRAPPER_OUTCOME_INCOMPLETE", "record marked completed=false")
    return {"status": "PASS", "wrapper_timeout_s": float(timeout), "wall_seconds": wall, "returncode": int(return_code), "killed": bool(killed)}


def build_no_solver_evidence(stage, run_dir, outputs):
    """Evidence helper: this module never starts a solver."""
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "run_dir": str(Path(run_dir).resolve()),
        "solver_starts": 0,
        "billable_numerical_analysis_starts": 0,
        "solver_processes_started": 0,
        "runner_start_path": "absent (start_solver raises SolverStartRefused)",
        "outputs": outputs,
    }


def _load_expected(path):
    if path is None:
        return dict(CONTRACT_12D)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "contract" in data:
        return dict(data["contract"])
    if "expected" in data:
        return dict(data["expected"])
    return dict(data)


def _cmd_normalize(args):
    expected = _load_expected(args.expect)
    report = inject_contract_fields(
        args.input,
        args.output,
        expected,
        allow_legacy=not args.strict,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_readback(args):
    expected = _load_expected(args.expect)
    report = read_setup_file(args.setup, expected)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_polar_structure(args):
    report = parse_polar_structure(args.polar)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_verify_polar(args):
    expected = _load_expected(args.expect)
    report = validate_polar_file(args.polar, expected)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_verify_history(args):
    expected = _load_expected(args.expect)
    report = validate_history_file(args.history, expected)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_check_dir(args):
    report = assert_new_format_only(args.dir)
    report.update(assert_no_solver_artifacts(args.dir))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_setup_gate(args):
    report = require_setup_success(args.rc, args.setup)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_start_solver(args):
    try:
        start_solver()
    except SolverStartRefused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 3
    return 0


def _cmd_check_case(args):
    expected = _load_case_expected(args.expect) if args.expect else None
    report = check_case_dir(
        args.dir,
        expected=expected,
        evidence=args.evidence,
        case_id=args.case_id,
        require_thin=not args.thick,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="D-12D-005 pre-gate runner (zero solver start)")
    parser.add_argument("--version", action="version", version=SCHEMA_VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    normalize = sub.add_parser("normalize", help="normalize legacy setup and inject contract fields")
    normalize.add_argument("--input", required=True)
    normalize.add_argument("--output", required=True)
    normalize.add_argument("--expect", default=None)
    normalize.add_argument("--strict", action="store_true", help="reject legacy input instead of normalizing")
    normalize.set_defaults(func=_cmd_normalize)

    readback = sub.add_parser("readback", help="read back and assert the contract")
    readback.add_argument("--setup", required=True)
    readback.add_argument("--expect", default=None)
    readback.set_defaults(func=_cmd_readback)

    polar = sub.add_parser("verify-polar", help="reject NaN/IND/INF and wrong Re in polar")
    polar.add_argument("--polar", required=True)
    polar.add_argument("--expect", default=None)
    polar.set_defaults(func=_cmd_verify_polar)
    polar_struct = sub.add_parser("polar-structure", help="structure-only 7.2.2 polar parse (no numerical thresholds)")
    polar_struct.add_argument("--polar", required=True)
    polar_struct.set_defaults(func=_cmd_polar_structure)

    history = sub.add_parser("verify-history", help="reject NaN and wrong Sref/Re in history")
    history.add_argument("--history", required=True)
    history.add_argument("--expect", default=None)
    history.set_defaults(func=_cmd_verify_history)

    check = sub.add_parser("check-dir", help="format isolation + no solver artifacts")
    check.add_argument("--dir", required=True)
    check.set_defaults(func=_cmd_check_dir)

    case = sub.add_parser("check-case-dir", help="strict pre-start case dir gate (LD-002)")
    case.add_argument("--dir", required=True)
    case.add_argument("--expect", default=None)
    case.add_argument("--evidence", default=None)
    case.add_argument("--case-id", default=None)
    case.add_argument("--thick", action="store_true", help="allow a thick geometry record")
    case.set_defaults(func=_cmd_check_case)

    gate = sub.add_parser("setup-gate", help="require a successful -setup return code and artifact")
    gate.add_argument("--rc", type=int, required=True)
    gate.add_argument("--setup", required=True)
    gate.set_defaults(func=_cmd_setup_gate)

    start = sub.add_parser("start-solver", help="always refused in pre-gate phase")
    start.set_defaults(func=_cmd_start_solver)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except RunnerError as exc:
        print(json.dumps({"status": "FAIL", "error_type": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
