
"""Minimal reader for VSPAERO *.polar result files.

The polar file has two header lines (a banner and the column names) followed by
whitespace separated numeric rows.  Only the columns needed for strict lift
matching are exposed; nothing is interpolated or repaired here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

COL_BETA = 0
COL_MACH = 1
COL_AOA = 2
COL_CL = 6      # CLtot
COL_CDO = 7     # CDo
COL_CDI = 8     # CDi
COL_CDTOT = 9   # CDtot


@dataclass(frozen=True)
class PolarRow:
    beta: float
    mach: float
    alpha_deg: float
    cl: float
    cdi: float
    line_number: int
    cdo: float = 0.0
    cdtot: float = 0.0

    def as_dict(self) -> dict:
        return {"alpha_deg": self.alpha_deg, "cl_total": self.cl,
                "cdo": self.cdo, "cdi": self.cdi, "cdtot": self.cdtot,
                "mach": self.mach, "beta": self.beta}


class PolarFormatError(ValueError):
    pass


def read_polar_rows(path: str | Path, *, beta_tol: float = 1e-9,
                    mach: Optional[float] = None,
                    mach_tol: float = 1e-9) -> list[PolarRow]:
    """Return the real evaluated rows of one polar (no interpolation)."""
    text_lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    header_index = None
    for i, line in enumerate(text_lines[:10]):
        tokens = line.split()
        if len(tokens) >= 20 and tokens[COL_BETA] == "Beta" and tokens[COL_MACH] == "Mach":
            header_index = i
            break
    if header_index is None:
        raise PolarFormatError("polar column header not found in the first ten lines")
    rows: list[PolarRow] = []
    for offset, line in enumerate(text_lines[header_index + 1:], start=header_index + 2):
        tokens = line.split()
        if not tokens:
            continue
        if not tokens[0].replace(".", "", 1).lstrip("+-").isdigit():
            raise PolarFormatError("unexpected non-numeric polar row at line %d" % offset)
        if len(tokens) <= COL_CDI:
            raise PolarFormatError("polar row shorter than expected at line %d" % offset)
        try:
            row = PolarRow(beta=float(tokens[COL_BETA]), mach=float(tokens[COL_MACH]),
                           alpha_deg=float(tokens[COL_AOA]), cl=float(tokens[COL_CL]),
                           cdi=float(tokens[COL_CDI]), line_number=offset,
                           cdo=float(tokens[COL_CDO]), cdtot=float(tokens[COL_CDTOT]))
        except ValueError as exc:  # pragma: no cover - defensive
            raise PolarFormatError("bad numeric value at line %d: %s" % (offset, exc)) from exc
        if abs(row.beta) > beta_tol:
            continue
        if mach is not None and abs(row.mach - mach) > mach_tol:
            continue
        rows.append(row)
    rows.sort(key=lambda r: r.alpha_deg)
    if not rows:
        raise PolarFormatError("polar contains no usable rows")
    return rows
