"""Evaluation cache with run-scoped label visibility (governance v2 sec 12.6).

Two-level keys (A1 E6-GAP-01, OpenVSP 3.55 thin-mesh non-determinism):

* design_key = sha256(canonical x12 || task_spec_sha256 || solver_config_hash)
  identifies a design, not a numerical reading.
* a REAL_VSPAERO entry key additionally includes mesh_family and
  normalized_geometry_hash. The thin mesher can emit different topology
  families for the same x12, so a real label is only reusable for the exact
  family and normalised geometry it was measured on. The raw .vspgeom bytes
  sha is stored as provenance only (families differ by object ids/order).

Fairness / leak rules:
* a same-run cache hit is a re-read of a label this run already paid for:
  cache_hit=True, physical_solver_starts=0, labels_visible_to_arm=True, and the
  hit is reported separately as cached_reads (never as a new real label);
* a design evaluated in another run/arm is a *foreign* entry: it may be detected
  but its numbers are never returned, and this run must pay its own solver
  start to read it;
* hot-start arms / surrogates only see labels collected inside their own run
  (VisibleLabelStore), never global truth;
* a REAL formal batch must never reuse a cache file from another run: the
  adapter sets forbid_cross_run_reuse and the cache fails closed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .records import canonical_json, sha256_bytes

#: normalisation for surrogate-facing objectives (D_i ~ 1e4..1e5 N)
D_I_SCALE_N = 1e5

_META_FIELDS = ("design_key", "mesh_family", "normalized_geometry_hash", "vspgeom_sha256")


class CrossRunCacheReuse(RuntimeError):
    """Raised when a REAL cache would serve or accept another run's entries."""


class EvaluationCache:
    def __init__(self, path: Optional[Any] = None) -> None:
        self.path = None if path is None else Path(path)
        self._entries: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._meta: Dict[Tuple[str, str], Dict[str, str]] = {}
        #: REAL formal batches set this True: cross-run reuse is forbidden.
        self.forbid_cross_run_reuse = False

    @staticmethod
    def key(
        x12_canonical: str,
        task_fingerprint: str,
        solver_config_sha256: str,
        mesh_family: str = "",
        normalized_geometry_hash: str = "",
    ) -> str:
        base = "%s||%s||%s" % (str(x12_canonical), str(task_fingerprint), str(solver_config_sha256))
        if not mesh_family and not normalized_geometry_hash:
            return sha256_bytes(base.encode("utf-8"))
        extended = "%s||mesh_family:%s||normalized_geometry_hash:%s" % (
            base,
            str(mesh_family),
            str(normalized_geometry_hash),
        )
        return sha256_bytes(extended.encode("utf-8"))

    def guard_run_scope(self, run_id: str) -> None:
        """Fail closed when a REAL cache file contains entries from other runs."""
        if not self.forbid_cross_run_reuse:
            return
        foreign = sorted({entry_run for (_key, entry_run) in self._entries if entry_run != str(run_id)})
        if foreign:
            raise CrossRunCacheReuse(
                "REAL cache forbids cross-run reuse; found entries from runs %s while serving run %s"
                % (foreign, str(run_id))
            )

    def store(
        self,
        key: str,
        run_id: str,
        payload: Mapping[str, Any],
        *,
        design_key: Optional[str] = None,
        mesh_family: str = "",
        normalized_geometry_hash: str = "",
        vspgeom_sha256: str = "",
    ) -> None:
        ident = (str(key), str(run_id))
        if self.forbid_cross_run_reuse:
            self.guard_run_scope(run_id)
        self._entries[ident] = dict(payload)
        self._meta[ident] = {
            "design_key": str(key if design_key is None else design_key),
            "mesh_family": str(mesh_family),
            "normalized_geometry_hash": str(normalized_geometry_hash),
            "vspgeom_sha256": str(vspgeom_sha256),
        }

    def lookup_scoped(self, key: str, run_id: str) -> Optional[Dict[str, Any]]:
        entry = self._entries.get((str(key), str(run_id)))
        return None if entry is None else dict(entry)

    def lookup_design_scoped(self, design_key: str, run_id: str) -> List[Dict[str, Any]]:
        """All in-run entries for one design (one per mesh family variant)."""
        rows: List[Dict[str, Any]] = []
        for (entry_key, entry_run), payload in self._entries.items():
            if entry_run != str(run_id):
                continue
            meta = self._meta.get((entry_key, entry_run), {})
            if str(meta.get("design_key", "")) != str(design_key):
                continue
            row = {"key": entry_key, "payload": dict(payload)}
            row.update({name: str(meta.get(name, "")) for name in ("mesh_family", "normalized_geometry_hash", "vspgeom_sha256")})
            rows.append(row)
        return sorted(rows, key=lambda item: item["key"])

    def foreign_entry(self, key: str, run_id: str) -> Optional[Dict[str, Any]]:
        for (entry_key, entry_run), payload in self._entries.items():
            if entry_key == str(key) and entry_run != str(run_id):
                return dict(payload)
        return None

    def foreign_design_entry(self, design_key: str, run_id: str) -> Optional[Dict[str, Any]]:
        for (entry_key, entry_run), payload in self._entries.items():
            if entry_run == str(run_id):
                continue
            meta = self._meta.get((entry_key, entry_run), {})
            if str(meta.get("design_key", "")) == str(design_key):
                return dict(payload)
        return None

    def runs_for_key(self, key: str) -> List[str]:
        return sorted(entry_run for (entry_key, entry_run) in self._entries if entry_key == str(key))

    def __len__(self) -> int:
        return len(self._entries)

    def save(self, path: Optional[Any] = None) -> Path:
        target = Path(path) if path is not None else self.path
        if target is None:
            raise ValueError("no cache path configured")
        payload = {
            "schema_version": "dreal001.evaluation_cache.v2",
            "entries": [
                {
                    "key": key,
                    "run_id": run_id,
                    "design_key": self._meta.get((key, run_id), {}).get("design_key", key),
                    "mesh_family": self._meta.get((key, run_id), {}).get("mesh_family", ""),
                    "normalized_geometry_hash": self._meta.get((key, run_id), {}).get("normalized_geometry_hash", ""),
                    "vspgeom_sha256": self._meta.get((key, run_id), {}).get("vspgeom_sha256", ""),
                    "payload": dict(value),
                }
                for (key, run_id), value in sorted(self._entries.items())
            ],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Any) -> "EvaluationCache":
        source = Path(path)
        cache = cls(source)
        if not source.exists():
            return cache
        payload = json.loads(source.read_text(encoding="utf-8"))
        schema = str(payload.get("schema_version", "dreal001.evaluation_cache.v1"))
        if schema not in ("dreal001.evaluation_cache.v1", "dreal001.evaluation_cache.v2"):
            raise ValueError("unsupported evaluation cache schema: %s" % (schema,))
        for item in payload.get("entries", []):
            cache.store(
                item["key"],
                item["run_id"],
                item.get("payload") or {},
                design_key=item.get("design_key") or item["key"],
                mesh_family=item.get("mesh_family", ""),
                normalized_geometry_hash=item.get("normalized_geometry_hash", ""),
                vspgeom_sha256=item.get("vspgeom_sha256", ""),
            )
        return cache


class VisibleLabelStore:
    """Labels visible to one run's hot-start / surrogate (already paid in-run)."""

    def __init__(self, run_id: str, *, d_i_scale_n: float = D_I_SCALE_N) -> None:
        self.run_id = str(run_id)
        self.d_i_scale_n = float(d_i_scale_n)
        self._rows: List[Dict[str, Any]] = []

    def add(
        self,
        unit_vector: Sequence[float],
        d_i_n: float,
        *,
        constraint_margin: float = 1.0,
        design_hash: str = "",
        extra: Optional[Mapping[str, Any]] = None,
    ) -> None:
        vector = [float(value) for value in np.asarray(unit_vector, dtype=float).reshape(-1)]
        row = {
            "unit_vector": vector,
            "objective": float(d_i_n) / self.d_i_scale_n,
            "constraint_margin": float(constraint_margin),
            "design_hash": str(design_hash),
        }
        if extra:
            row.update({str(key): value for key, value in extra.items()})
        self._rows.append(row)

    def __len__(self) -> int:
        return len(self._rows)

    def rows(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def to_support(self) -> Optional[Dict[str, Any]]:
        if not self._rows:
            return None
        designs = np.asarray([row["unit_vector"] for row in self._rows], dtype=float)
        objective = np.asarray([row["objective"] for row in self._rows], dtype=float)
        return {
            "designs": designs,
            "objective": objective,
            "records": [dict(row) for row in self._rows],
        }

    def as_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "n_labels_visible": len(self._rows),
            "d_i_scale_n": self.d_i_scale_n,
            "labels": self.rows(),
        }
