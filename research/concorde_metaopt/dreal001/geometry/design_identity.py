"""Governance v3 section 3 identity helpers for the 12D design vector (D-REAL-001).

design_hash = sha256(canonical x12 JSON)[:16]
canonical   = the 12 dimensions in frozen order (W01..W10, V01, V02), every value a
              float serialised with "%.12g", no whitespace anywhere.

This module holds no state and imports nothing from the solver, so both the runner
(dreal001/geometry/solver_runner.py) and the reserializer
(dreal001/geometry/evaluation_reserialize.py) can hash a design without a circular
import.  The hash identity is the design vector, NOT the .vspgeom bytes: the
geometry digest stays available separately as geometry_sha256.
"""
from __future__ import annotations

import hashlib
from typing import Any, Sequence

CANONICAL_FLOAT_FORMAT = "%.12g"
DESIGN_HASH_HEX_LENGTH = 16
DESIGN_HASH_DEFINITION = (
    "sha256(canonical x12 JSON)[:16]; canonical = 12 dimensions in frozen order "
    "(W01..W10, V01, V02), floats serialised with %.12g, no whitespace "
    "(governance v3 section 3)")


def canonical_x12_payload(x12: Sequence[Any]) -> str:
    """Canonical JSON payload of the 12D design vector (governance v3 section 3)."""
    values = [float(value) for value in x12]
    return "[" + ",".join(CANONICAL_FLOAT_FORMAT % value for value in values) + "]"


def design_hash(x12: Sequence[Any]) -> str:
    """Governance v3 section 3 design identity: sha256(canonical x12 JSON)[:16]."""
    return hashlib.sha256(canonical_x12_payload(x12).encode("utf-8")).hexdigest()[
        :DESIGN_HASH_HEX_LENGTH]
