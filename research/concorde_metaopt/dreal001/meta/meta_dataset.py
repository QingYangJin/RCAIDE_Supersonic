"""Di_N-only recovery dataset checks; synthetic fixtures never become real labels."""
from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np

from .task_spec import ContractError, TaskSpec, canonical_sha, validate_task_family


@dataclass(frozen=True)
class Observation:
    observation_id: str
    task_id: str
    design: tuple[float, ...]
    partition: str
    source_kind: str
    status: str
    di_n: float | None
    q_pa: float | None = None
    sref_m2: float | None = None
    cdi: float | None = None
    cl: float | None = None
    raw_sha256: str | None = None
    fuel_burn_kg: None = None

    def __post_init__(self) -> None:
        if not self.observation_id or not self.task_id:
            raise ContractError("observation identity missing")
        object.__setattr__(self, "design", tuple(float(v) for v in self.design))
        if len(self.design) != 12 or not all(math.isfinite(v) for v in self.design):
            raise ContractError("design must have 12 finite coordinates")
        if self.partition not in {"support", "query"}:
            raise ContractError("invalid support/query partition")
        if self.source_kind not in {"synthetic_fixture", "vspaero_raw"}:
            raise ContractError("unrecognized data source")
        if self.status not in {"ok", "failed"}:
            raise ContractError("unrecognized observation status")
        if self.fuel_burn_kg is not None:
            raise ContractError("fuel_burn_kg must remain null")
        if self.status == "failed":
            if self.di_n is not None:
                raise ContractError("failed objective must be null")
            if self.cl is not None or self.cdi is not None:
                raise ContractError("failed observation must not carry coefficient labels")
        elif self.di_n is None or not math.isfinite(self.di_n) or self.di_n < 0:
            raise ContractError("successful Di_N must be finite and nonnegative")

    @property
    def design_sha256(self) -> str:
        # Canonicalise signed zero; equality cannot be evaded by -0.0.
        return canonical_sha([0.0 if v == 0 else v for v in self.design])


class MetaDataset:
    def __init__(self, tasks: tuple[TaskSpec, ...], rows: tuple[Observation, ...]):
        self.tasks = tuple(tasks)
        self.rows = tuple(rows)
        validate_task_family(self.tasks)
        by_id = {t.task_id: t for t in self.tasks}
        if not self.rows or len({r.observation_id for r in self.rows}) != len(self.rows):
            raise ContractError("empty dataset or duplicate observation_id")
        seen: set[tuple[str, str]] = set()
        for row in self.rows:
            if row.task_id not in by_id:
                raise ContractError("unknown task_id")
            key = (row.task_id, row.design_sha256)
            if key in seen:
                raise ContractError("duplicate design or support/query leakage within task")
            seen.add(key)
        if len({r.source_kind for r in self.rows}) != 1:
            raise ContractError("real and synthetic sources must never mix")

    def usable(self, task_id: str, partition: str) -> tuple[Observation, ...]:
        return tuple(r for r in self.rows if r.task_id == task_id
                     and r.partition == partition and r.status == "ok")

    def require_software_fixture(self) -> None:
        if any(r.source_kind != "synthetic_fixture" for r in self.rows):
            raise ContractError("software fixture entry rejects real/declared-real data")

    def require_real_admission(self) -> None:
        # Intentionally fail closed even for plausible VSPAERO numbers or PASS strings.
        # R0/R1/backup/A5, raw parsing, signed manifests and task-deck binding are not
        # restored yet. This module MUST NOT mint a production admission certificate.
        raise ContractError("REAL_ADMISSION_NOT_IMPLEMENTED: independent gates and raw verification required")


@dataclass(frozen=True)
class TrainNormalizer:
    x_mean: np.ndarray
    x_scale: np.ndarray
    y_mean: float
    y_scale: float
    fit_observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        # Frozen dataclasses alone do not freeze NumPy buffers. Own read-only copies
        # prevent callers from mutating train statistics during held-out adaptation.
        for name in ("x_mean", "x_scale"):
            value = np.array(getattr(self, name), dtype=np.float64, copy=True)
            if value.shape != (12,) or not np.isfinite(value).all():
                raise ContractError("normalizer requires finite 12D statistics")
            if name == "x_scale" and np.any(value <= 0):
                raise ContractError("normalizer scales must be positive")
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        if (not math.isfinite(self.y_mean) or not math.isfinite(self.y_scale)
                or self.y_scale <= 0):
            raise ContractError("normalizer target statistics must be finite with positive scale")
        ids = tuple(self.fit_observation_ids)
        if not ids or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ContractError("normalizer fit observation identities must be nonempty and unique")
        object.__setattr__(self, "fit_observation_ids", ids)

    @classmethod
    def fit(cls, dataset: MetaDataset) -> "TrainNormalizer":
        train_ids = {t.task_id for t in dataset.tasks if t.split == "train"}
        rows = tuple(r for r in dataset.rows if r.task_id in train_ids and r.status == "ok")
        if not rows:
            raise ContractError("no usable train rows")
        x = np.asarray([r.design for r in rows], dtype=np.float64)
        y = np.asarray([r.di_n for r in rows], dtype=np.float64)
        scale = np.std(x, axis=0)
        return cls(np.mean(x, axis=0), np.where(scale > 1e-12, scale, 1.0),
                   float(np.mean(y)), max(float(np.std(y)), 1e-12),
                   tuple(r.observation_id for r in rows))

    def arrays(self, rows: tuple[Observation, ...]) -> tuple[np.ndarray, np.ndarray]:
        if not rows:
            raise ContractError("empty support/query partition")
        if any(r.status != "ok" for r in rows):
            raise ContractError("normalization accepts only successful observations")
        x = np.asarray([r.design for r in rows], dtype=np.float64)
        y = np.asarray([r.di_n for r in rows], dtype=np.float64).reshape(-1, 1)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            nx, ny = (x - self.x_mean) / self.x_scale, (y - self.y_mean) / self.y_scale
        if not np.isfinite(nx).all() or not np.isfinite(ny).all():
            raise ContractError("nonfinite normalized observations")
        return nx, ny
