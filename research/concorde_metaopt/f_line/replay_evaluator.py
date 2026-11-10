"""F1 归档 replay 评价器（ArchiveReplayEvaluator，只读、零物理调用）。

用途：把 F1 抽象接到**已经冻结的历史几何归档**上，验证"同一设计向量可以按
归档精确取回历史诊断量"这条链路；同时明确标注这些历史记录**不是本次求解**，
也没有通过物理门禁。

数据来源（只读，不写入）：
    research/concorde_metaopt/optimization_runs/geometry-check-p1-20261028T1835/geometry_cases.jsonl
    31 条记录，x 字段为 15 名物理设计向量，metrics 含 cg_x_m / wing_ac_x_m 等几何诊断。

契约：
* source_kind = ARCHIVE_REPLAY，fidelity = "archive_replay"，physical_call_count = 0。
* **objective 恒为 null**：归档只有几何检查，没有可用的巡航油耗；
  状态固定为 PHYSICS_NOT_VALIDATED，禁止把几何诊断当物理评价。
* 未命中归档 -> status=EVALUATOR_ERROR, objective=null, 并记录请求的设计 SHA。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..aircraft.design_space import DesignSpace
from .records import (
    EvaluationRecord,
    PHYSICAL_VALIDATION_NOT_VALIDATED,
    SOURCE_KIND_ARCHIVE_REPLAY,
    STATUS_EVALUATOR_ERROR,
    STATUS_PHYSICS_NOT_VALIDATED,
    canonical_design_sha256,
    ordered_constraints,
)

#: 默认归档目录（相对 research/concorde_metaopt/）。
DEFAULT_ARCHIVE_RUN = "geometry-check-p1-20261028T1835"
DEFAULT_ARCHIVE_FILENAME = "geometry_cases.jsonl"

#: 归档中可安全引用的几何诊断量（这些是几何量，不是气动量）。
ARCHIVED_METRIC_KEYS: Tuple[str, ...] = (
    "cg_x_m",
    "wing_ac_x_m",
    "tail_ac_x_m",
    "static_margin",
    "mass_operating_empty_kg",
    "mass_total_takeoff_kg",
    "usable_volume_m3",
    "wing_area_m2",
    "wing_mac_m",
    "wing_span_m",
    "tail_area_m2",
    "tail_mac_m",
    "tail_span_m",
    "fuselage_wetted_area_m2",
)


class ArchiveReplayEvaluator:
    """只读 replay 评价器：按设计向量精确匹配归档记录。"""

    evaluator_id = "archive-replay-geometry-p1-1835-v1"
    fidelity = "archive_replay"
    source_kind = SOURCE_KIND_ARCHIVE_REPLAY
    solver_version = "archive:geometry-check-p1-20261028T1835"
    physical_validation_status = PHYSICAL_VALIDATION_NOT_VALIDATED
    estimated_physical_cost = 0

    def __init__(
        self,
        design_space: DesignSpace,
        task: Any,
        run_id: str = "f1-replay",
        archive_path: Optional[Path] = None,
        verify_sha256: bool = True,
    ) -> None:
        self.design_space = design_space
        self.task = task
        self.run_id = str(run_id)
        if archive_path is None:
            archive_path = (
                Path(__file__).resolve().parents[1]
                / "optimization_runs"
                / DEFAULT_ARCHIVE_RUN
                / DEFAULT_ARCHIVE_FILENAME
            )
        self.archive_path = Path(archive_path)
        if not self.archive_path.is_file():
            raise FileNotFoundError("archive not found: %s" % self.archive_path)
        raw = self.archive_path.read_bytes()
        self.archive_sha256 = hashlib.sha256(raw).hexdigest()
        if not verify_sha256:
            self.archive_sha256 = hashlib.sha256(raw).hexdigest()
        self.records: List[Dict[str, Any]] = []
        self._by_design: Dict[Tuple[float, ...], Dict[str, Any]] = {}
        self._by_id: Dict[str, Dict[str, Any]] = {}
        for line in raw.decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            self.records.append(record)
            vector = record.get("x")
            if isinstance(vector, Mapping) and vector:
                key = self._key(vector)
                self._by_design[key] = record
            design_id = record.get("design_id")
            if isinstance(design_id, str) and design_id:
                self._by_id[design_id] = record

    # -- 索引工具 ---------------------------------------------------------
    @property
    def _key_names(self) -> Tuple[str, ...]:
        return tuple(self.design_space.names) + tuple(self.design_space.fixed_names)

    def _key(self, design: Mapping[str, float]) -> Tuple[float, ...]:
        return tuple(round(float(design[name]), 9) for name in self._key_names)

    def _physical(self, design: Mapping[str, float]) -> Dict[str, float]:
        declared = set(self.design_space.names)
        fixed = set(self.design_space.fixed_names)
        keys = set(design)
        if keys == declared:
            return self.design_space.expand(design)
        if keys == declared | fixed:
            return {name: float(design[name]) for name in list(self.design_space.names) + list(self.design_space.fixed_names)}
        missing = sorted(declared - keys)
        unexpected = sorted(keys - declared - fixed)
        raise ValueError(
            "design must carry either the 12 declared variables or the full 15 physical "
            "variables (missing=%s unexpected=%s)" % (missing, unexpected)
        )

    @property
    def available_design_count(self) -> int:
        return len(self._by_design)

    def lookup(self, design: Mapping[str, float]) -> Optional[Dict[str, Any]]:
        return self._by_design.get(self._key(self._physical(design)))

    def lookup_by_id(self, design_id: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(str(design_id))

    # -- 协议实现 ---------------------------------------------------------
    def evaluate(
        self,
        design: Mapping[str, float],
        task: Any = None,
        fidelity: Optional[str] = None,
    ) -> EvaluationRecord:
        if fidelity is not None and str(fidelity) != self.fidelity:
            raise ValueError(
                "ArchiveReplayEvaluator only serves fidelity %r, got %r" % (self.fidelity, fidelity)
            )
        physical = self._physical(design)
        sha = canonical_design_sha256(physical)
        matched = self._by_design.get(self._key(physical))
        if matched is None:
            return EvaluationRecord(
                run_id=self.run_id,
                task_id=str(getattr(self.task, "task_id", "")),
                design=physical,
                design_sha256=sha,
                evaluator_id=self.evaluator_id,
                fidelity=self.fidelity,
                source_kind=self.source_kind,
                physical_validation_status=self.physical_validation_status,
                solver_version=self.solver_version,
                objective=None,
                constraints=ordered_constraints(),
                status=STATUS_EVALUATOR_ERROR,
                provenance={
                    "archive_path": self._display_path(),
                    "archive_sha256": self.archive_sha256,
                    "requested_design_sha256": sha,
                    "matched_design_id": None,
                    "note": "设计不在归档中；replay 只读，不发起任何求解",
                },
                physical_call_count=0,
                wall_seconds=0.0,
                diagnostics=("design not found in archive: %s" % sha,),
            )
        metrics = matched.get("metrics") or {}
        archived = {
            key: metrics[key]
            for key in ARCHIVED_METRIC_KEYS
            if key in metrics and isinstance(metrics[key], (int, float))
        }
        feasible = bool(matched.get("feasible"))
        constraints = ordered_constraints({"geometry_invalid": 0.0 if feasible else 1.0})
        return EvaluationRecord(
            run_id=self.run_id,
            task_id=str(getattr(self.task, "task_id", "")),
            design=physical,
            design_sha256=sha,
            evaluator_id=self.evaluator_id,
            fidelity=self.fidelity,
            source_kind=self.source_kind,
            physical_validation_status=self.physical_validation_status,
            solver_version=self.solver_version,
            objective=None,
            constraints=constraints,
            status=STATUS_PHYSICS_NOT_VALIDATED,
            provenance={
                "archive_path": self._display_path(),
                "archive_sha256": self.archive_sha256,
                "matched_design_id": matched.get("design_id"),
                "archived_status": matched.get("status"),
                "archived_feasible": feasible,
                "archived_metrics": archived,
                "note": (
                    "只读归档 replay：几何检查记录，非本次求解、无物理调用；"
                    "归档不含可用的巡航油耗，故 objective=null 且物理状态 NOT_VALIDATED"
                ),
            },
            physical_call_count=0,
            wall_seconds=0.0,
        )

    def _display_path(self) -> str:
        try:
            return str(self.archive_path.resolve().relative_to(Path(__file__).resolve().parents[3]))
        except ValueError:
            return str(self.archive_path)
