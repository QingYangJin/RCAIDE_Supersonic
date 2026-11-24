"""Build the D-REAL-EXP-003 H0 gate evidence (zero physical).

Issue #15 requires the H0 gate to be closed before any new VSPAERO start:
frozen real 12D geometry contract, recorded design-space conflict, real
optimizer executor wiring, and the exact code SHAs that later batches cite.

Everything here is offline. physical_solver_starts_actual stays 0 and the
sample run only exercises CPU/memory recording, not the solver.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from research.concorde_metaopt.dreal001.geometry import h0_contract  # noqa: E402
from research.concorde_metaopt.dreal001.ops.resource_monitor import (  # noqa: E402
    ResourceMonitor,
)

OUT = Path(__file__).resolve().parent
RUN_ID = "DRECOVER001-H0-20261124"
SCHEMA = "dreal005.h0_gate.v1"

TRACKED_FILES = (
    "research/concorde_metaopt/dreal001/geometry/h0_contract.py",
    "research/concorde_metaopt/dreal001/ops/resource_monitor.py",
    "research/concorde_metaopt/dreal001/meta/real_a0_ablation.py",
    "research/concorde_metaopt/dreal001/optimizers/recovery_bo.py",
    "research/concorde_metaopt/dreal001/geometry/solver_runner.py",
    "research/concorde_metaopt/dreal001/geometry/openvsp_model.py",
    "research/concorde_metaopt/dreal001/geometry/adaptive_alpha.py",
    "research/concorde_metaopt/dreal001/geometry/design_identity.py",
    "research/concorde_metaopt/dreal001/meta/real_admission.py",
    "research/concorde_metaopt/dreal001/meta/meta_dataset.py",
    "research/concorde_metaopt/dreal001/meta/task_spec.py",
    "research/concorde_metaopt/dreal001/meta/production.py",
    "research/concorde_metaopt/dreal001/geometry/task_spec.py",
    "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(payload) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write(name: str, payload) -> Path:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def git_head() -> dict:
    def run(args):
        try:
            done = subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                                  timeout=60)
        except Exception as exc:  # noqa: BLE001
            return {"error": "%s: %s" % (type(exc).__name__, exc)}
        return {"returncode": done.returncode, "stdout": done.stdout.strip(),
                "stderr": done.stderr.strip()[:400]}
    return {"head": run(["git", "rev-parse", "HEAD"]),
            "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
            "status_porcelain_short": run(["git", "status", "--porcelain=v1"])}


def code_shas() -> dict:
    rows = {}
    for rel in TRACKED_FILES:
        path = ROOT / rel
        if not path.is_file():
            raise SystemExit("tracked H0 file is missing: %s" % rel)
        rows[rel] = {"sha256": sha_file(path), "bytes": path.stat().st_size}
    return rows


def resource_baseline(duration_s: float = 6.0) -> dict:
    """Record the sampler working on a short offline probe.

    The probe runs for a fixed wall time so the sampler collects several
    intervals; the first sample only establishes the CPU baseline.
    """
    import time

    monitor = ResourceMonitor(OUT / "h0_resource_probe.jsonl", interval_s=1.0,
                              label="H0_OFFLINE_PROBE")
    started = time.time()
    iterations = 0
    total = 0
    with monitor:
        while time.time() - started < duration_s:
            for index in range(200000):
                total += index % 7
            iterations += 200000
    summary = monitor.summary()
    summary["work_done"] = {"loop_iterations": iterations, "accumulator": total,
                            "target_duration_s": duration_s,
                            "measured_duration_s": time.time() - started}
    summary["scope"] = "OFFLINE_PROBE_NOT_A_SOLVER_RUN"
    return summary


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    contract = h0_contract.build_contract()
    contract_path = write("geometry_contract.json", contract)
    verification = h0_contract.verify_contract(contract)
    verification["contract_path"] = "docs/evidence/dreal005/h0/geometry_contract.json"
    verification["contract_file_sha256"] = sha_file(contract_path)
    verification["generated_utc"] = None  # keep the record reproducible
    write("geometry_contract_verification.json",
          {key: value for key, value in verification.items() if key != "generated_utc"})

    resource = resource_baseline()
    write("h0_resource_probe_summary.json", resource)

    shas = code_shas()
    payload = {
        "schema": SCHEMA,
        "run_id": RUN_ID,
        "issue": 15,
        "stage": "H0",
        "created_utc": now,
        "branch": git_head(),
        "geometry_contract_sha256": contract["contract_sha256"],
        "geometry_contract_file_sha256": sha_file(contract_path),
        "geometry_contract_verification_file_sha256": sha_file(
            OUT / "geometry_contract_verification.json"),
        "freeze_conflict": contract["freeze_conflict"],
        "optimization_subspace": list(contract["optimization_subspace"]),
        "aerodynamic_active_mask_status": contract["aerodynamic_active_mask_status"],
        "code_sha256": shas,
        "code_bundle_sha256": canonical_sha(shas),
        "resource_probe": {
            "summary_file": "docs/evidence/dreal005/h0/h0_resource_probe_summary.json",
            "summary_file_sha256": sha_file(OUT / "h0_resource_probe_summary.json"),
            "sample_count": resource["sample_count"],
            "cpu_busy_fraction_mean": resource["cpu_busy_fraction_mean"],
            "memory_load_percent_mean": resource["memory_load_percent_mean"],
            "tracked_working_set_bytes_max": resource["tracked_working_set_bytes_max"],
        },
        "gates": {
            "H0_GEOMETRY_CONTRACT_FROZEN": "PENDING_A5_REVIEW",
            "H0_FREEZE_CONFLICT_DISCLOSED": "PENDING_A5_REVIEW",
            "H0_RESOURCE_ACCOUNTING_INSTRUMENTED": "PENDING_A5_REVIEW",
            "H0_CODE_SHA_FROZEN": "PENDING_A5_REVIEW",
            "H0_ZERO_PHYSICAL": "PASS",
        },
        "physical_solver_starts_actual": 0,
        "internal_solver_cases_actual": 0,
        "physics_validated": False,
        "not_authorized": [
            "any VSPAERO start",
            "A0 real training on admitted labels before A5 review of the exact code SHA",
            "O0 real BO before a fresh Lead GO",
        ],
        "next_gate": "A5 independent review of this H0 packet, then the A0/O0 GO records",
    }
    payload["h0_gate_sha256"] = canonical_sha(
        {key: value for key, value in payload.items() if key != "h0_gate_sha256"})
    write("h0_gate.json", payload)
    print(json.dumps({"contract_sha256": contract["contract_sha256"],
                      "code_bundle_sha256": payload["code_bundle_sha256"],
                      "h0_gate_sha256": payload["h0_gate_sha256"],
                      "resource_samples": resource["sample_count"],
                      "cpu_busy_fraction_mean": resource["cpu_busy_fraction_mean"],
                      "tracks": len(shas)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())