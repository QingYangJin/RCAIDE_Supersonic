"""D-12D-004 pre-gate runner library (zero solver start).

Scope: LOCUST -- D-12D-004 A 类 VSPAERO 7.2.2 薄翼验证的前置门禁工具。
This module only writes, normalizes and validates VSPAERO *setup* files and
post-processes already-existing polar/history text.  It contains NO code path
that forks vspaero.exe / vspaero / SU2 / RCAIDE Mission; start_solver() always
raises SolverStartRefused so an accidental future call cannot start physics.

LD-001 fixes implemented here:
  1. legacy .vspaero lines without "=" are detected and rejected in strict
     mode, or normalized in place before contract-field injection;
  2. a non-zero "-setup" process return code is a hard gate (existing setup
     template does NOT authorize continuing);
  3. polar rows containing NaN / IND / INF or a Re/1e6 column inconsistent
     with the declared ReCref are invalid data, never "SOLVED";
  4. history header Sref_/Cref_/Bref_/Mach_/Rho_/Vinf_ are checked against the
     declared case values; mismatch => invalid data;
  5. every contract field is written explicitly and read back with the A2
     13-assertion set in config/run_config.json.

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

SCHEMA_VERSION = "d12d004-runner-1"
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
    "*.adb",
    "*.fem",
)
POLAR_REQUIRED_COLUMNS = ("Beta", "Mach", "AoA", "Re/1e6", "CL", "CDo", "CDi", "CDtot", "E")
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


def _polar_header_and_rows(text):
    lines = str(text).splitlines()
    header_index = None
    for index, raw in enumerate(lines):
        tokens = raw.split()
        if len(tokens) >= 8 and "CL" in tokens and "AoA" in tokens and "Mach" in tokens:
            header_index = index
            break
    if header_index is None:
        raise DataQualityError("POLAR_HEADER_MISSING: no header with AoA/CL/Mach")
    header = lines[header_index].split()
    rows = []
    nonfinite = []
    for lineno, raw in enumerate(lines[header_index + 1 :], header_index + 2):
        stripped = raw.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        if len(tokens) != len(header):
            raise DataQualityError(
                "POLAR_ROW_WIDTH line=%d expected=%d got=%d" % (lineno, len(header), len(tokens))
            )
        row = {}
        for name, token in zip(header, tokens):
            if NONFINITE_RE.search(token):
                nonfinite.append({"line": lineno, "column": name, "token": token})
                continue
            try:
                row[name] = float(token.replace("D", "E").replace("d", "e"))
            except ValueError:
                raise DataQualityError(
                    "POLAR_NON_NUMERIC line=%d column=%s token=%r" % (lineno, name, token)
                )
        rows.append({"line": lineno, "values": row})
    return {"header": header, "rows": rows, "nonfinite": nonfinite}


def validate_polar_file(path, expected):
    """Reject NaN/IND/INF rows and a Re/1e6 column inconsistent with ReCref."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    parsed = _polar_header_and_rows(text)
    missing = [column for column in POLAR_REQUIRED_COLUMNS if column not in parsed["header"]]
    if missing:
        raise DataQualityError("POLAR_REQUIRED_COLUMNS_MISSING: %r" % (missing,))
    if parsed["nonfinite"]:
        raise DataQualityError(
            "POLAR_NONFINITE: %r" % (parsed["nonfinite"][:6],)
        )
    if not parsed["rows"]:
        raise DataQualityError("POLAR_NO_DATA_ROWS")
    re_expected = float(expected["ReCref"]) / 1e6
    re_reports = []
    for row in parsed["rows"]:
        values = row["values"]
        for name in POLAR_REQUIRED_COLUMNS:
            if name not in values or not math.isfinite(values[name]):
                raise DataQualityError("POLAR_NONFINITE_FIELD line=%d column=%s" % (row["line"], name))
        actual_re = values["Re/1e6"]
        ok, detail = _compare("Re/1e6", actual_re, re_expected, "rel", 1e-6)
        if not ok:
            raise DataQualityError(
                "POLAR_RE_MISMATCH line=%d expected=%.9g actual=%.9g %s"
                % (row["line"], re_expected, actual_re, detail)
            )
        re_reports.append(actual_re)
    return {
        "status": "PASS",
        "path": str(Path(path).resolve()),
        "sha256": sha256_file(path),
        "header": parsed["header"],
        "rows": len(parsed["rows"]),
        "re_ue6": re_reports,
        "expected_re_ue6": re_expected,
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


def build_parser():
    parser = argparse.ArgumentParser(description="D-12D-004 pre-gate runner (zero solver start)")
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

    history = sub.add_parser("verify-history", help="reject NaN and wrong Sref/Re in history")
    history.add_argument("--history", required=True)
    history.add_argument("--expect", default=None)
    history.set_defaults(func=_cmd_verify_history)

    check = sub.add_parser("check-dir", help="format isolation + no solver artifacts")
    check.add_argument("--dir", required=True)
    check.set_defaults(func=_cmd_check_dir)

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
