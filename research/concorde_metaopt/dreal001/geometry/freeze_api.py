"""FreezeAPI v1.0 -- arm-blind two-family geometry freeze (zero physical solver).

Interface (frozen for A2 integration):
    discover_and_freeze_pair(x12, design_hash, out_dir, policy, builder_sha) -> record

Policy (Lead m07117):
  * discovery (arm-blind K=10): fresh-process builds until the family union has
    2 labels, at most 10 observations; if only 1 label is seen, keep going to 40;
    |F|>=3 -> DESIGN_VOID.
  * then force each of the two target families, each at most 40 fresh-process builds.
  * every build is a brand-new process with its own cwd and TMP/TEMP; prepared
    mesh (nodes,elements) must equal the parsed .vspgeom (prepared==parsed).
  * freeze .vspgeom + .vkey + .vsp3 per family; write append-only attempts.jsonl,
    a hash-chained freeze_log.jsonl (one per-design record, parent_hash links),
    freeze_record.json and SHA256SUMS. physical_call_count is always 0: only
    VSPAEROComputeGeometry is used, never vspaero.exe.

Role mapping is deterministic and must be identical everywhere:
f1 = family with the smaller (nodes, elements) tuple, f2 = the larger one.
Equal-weight aggregation is independent of role order; no arm/result may change it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

SCHEMA = "dreal001.freeze_api.v1"
API_VERSION = "1.0"
CAP_PER_FAMILY = 40
DISCOVERY_CAP = 10
DISCOVERY_EXTEND_SINGLE = 40
UNION_VOID_AT = 3
DEFAULT_POLICY = {
    "discovery_cap": DISCOVERY_CAP,
    "single_family_extend": DISCOVERY_EXTEND_SINGLE,
    "cap_per_family": CAP_PER_FAMILY,
    "union_void_at": UNION_VOID_AT,
}

STATUS_PAIR_READY = "PAIR_READY"
STATUS_DESIGN_VOID = "DESIGN_VOID"
STATUS_FAMILY_UNREACHABLE = "FAMILY_UNREACHABLE"
STATUS_NO_FAMILY = "NO_FAMILY_DISCOVERED"
STATUS_HASH_MISMATCH = "DESIGN_HASH_MISMATCH"


class FreezeApiError(RuntimeError):
    """Fail-closed FreezeAPI contract violation (A5 P2AV2 fixes 5)."""


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_family(label: Optional[str]) -> Optional[tuple]:
    if not label:
        return None
    try:
        a, b = str(label).lower().split("x")
        return int(a), int(b)
    except Exception:
        return None


def family_label(pair: Sequence[int]) -> str:
    return "%dx%d" % (int(pair[0]), int(pair[1]))


def role_map(labels: Sequence[str]) -> Dict[str, str]:
    """f1 = smaller (nodes, elements); f2 = larger. Deterministic, result-independent."""
    ordered = sorted(str(lab) for lab in labels)
    if len(ordered) != 2:
        raise ValueError("role_map needs exactly two family labels")
    ordered = sorted(ordered, key=lambda lab: parse_family(lab) or (0, 0))
    return {"f1": ordered[0], "f2": ordered[1]}


def _design_hash(x12: Sequence[float]) -> str:
    from .design_identity import design_hash
    return design_hash(x12)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_config_path() -> Path:
    return _repo_root() / "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml"



# --------------------------------------------------------------- hash chain
GENESIS_HASH = "0" * 64
FREEZE_LOG_NAME = "freeze_log.jsonl"
CHAIN_SCHEMA = "dreal001.freeze_api.chain.v1"


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def record_digest(row: Mapping[str, Any]) -> str:
    """SHA256 over the canonical record without its own record_hash field."""
    body = {k: v for k, v in dict(row).items() if k != "record_hash"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def append_chained_record(log_path: Path, payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Append one hash-chained record; parent_hash is the previous record_hash."""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    previous = GENESIS_HASH
    seq = 1
    if log_path.is_file():
        rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if rows:
            previous = str(rows[-1]["record_hash"])
            seq = int(rows[-1].get("seq", len(rows))) + 1
        # A5 2026-11-11: one design = exactly one DESIGN_FREEZE record; the chain
        # must be valid before anything is appended (no silent overwrite/repair).
        report = verify_chain(log_path)
        if not report["valid"]:
            raise FreezeApiError("APPEND_ONLY_CHAIN_INVALID: " + ",".join(report["errors"][:3]))
        if str(payload.get("kind")) == "DESIGN_FREEZE":
            dh_existing = str(payload.get("design_hash", ""))
            if dh_existing in latest_design_records(log_path):
                raise FreezeApiError("DUPLICATE_DESIGN_FREEZE: " + dh_existing)
    row = dict(payload)
    row.update({"schema": CHAIN_SCHEMA, "seq": seq, "parent_hash": previous,
                "physical_call_count": 0})
    row["record_hash"] = record_digest(row)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(row) + "\n")
    return row


def read_chain(log_path: Path) -> List[Dict[str, Any]]:
    log_path = Path(log_path)
    if not log_path.is_file():
        return []
    rows = []
    for number, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError("bad freeze log line %d: %s" % (number, exc)) from exc
    return rows


def verify_chain(log_path: Path) -> Dict[str, Any]:
    """Validate seq order, parent_hash links and each record_hash. Returns a report."""
    rows = read_chain(log_path)
    errors: List[str] = []
    previous = GENESIS_HASH
    for index, row in enumerate(rows, 1):
        if int(row.get("seq", -1)) != index:
            errors.append("seq_mismatch@%d" % index)
        if str(row.get("parent_hash")) != previous:
            errors.append("parent_hash_mismatch@%d" % index)
        if str(row.get("record_hash")) != record_digest(row):
            errors.append("record_hash_mismatch@%d" % index)
        previous = str(row.get("record_hash", ""))
    return {"schema": "dreal001.freeze_api.chain_report.v1", "path": str(Path(log_path)),
            "records": len(rows), "valid": not errors, "errors": errors,
            "head_hash": previous if rows else GENESIS_HASH,
            "physical_call_count": 0}


def latest_design_records(log_path: Path) -> Dict[str, Dict[str, Any]]:
    """design_hash -> latest chained record (append-only log: last one wins)."""
    out: Dict[str, Dict[str, Any]] = {}
    for row in read_chain(log_path):
        if row.get("kind") == "DESIGN_FREEZE":
            out[str(row.get("design_hash"))] = row
    return out


def build_final_run_manifest(log_path: Path, out_path: Path, *, batch_id: str = "",
                             manifest_source_sha256: str = "",
                             policy_doc_sha256: str = "",
                             builder_code_sha256: str = "",
                             verify_files: bool = True,
                             allow_invalid: bool = False) -> Dict[str, Any]:
    """Final run manifest over every runtime design in the append-only log.

    Verifies the chain, and (by default) that each frozen file still matches its
    recorded SHA.  Only PAIR_READY designs are listed as usable; every other
    terminal status is listed as DESIGN_VOID/UNUSABLE for uniform-void handling.
    """
    report = verify_chain(log_path)
    records = latest_design_records(log_path)
    designs: List[Dict[str, Any]] = []
    file_errors: List[str] = []
    for dh in sorted(records):
        rec = records[dh]
        families = rec.get("families") or {}
        usable = rec.get("status") == STATUS_PAIR_READY
        for label, fam in families.items():
            frozen = (fam or {}).get("frozen") or {}
            if not frozen:
                continue
            if verify_files:
                geom = Path(str(frozen.get("frozen_vspgeom_path", "")))
                if not geom.is_file():
                    file_errors.append("missing@%s/%s" % (dh, label))
                    usable = False
                elif sha256_file(geom) != frozen.get("frozen_vspgeom_sha256"):
                    file_errors.append("sha_mismatch@%s/%s" % (dh, label))
                    usable = False
                vkey_path = Path(str(frozen.get("frozen_vkey_path") or (geom.parent / "model.vkey")))
                if not vkey_path.is_file():
                    # A5 RUN-06: a missing .vkey must void the design, never pass silently.
                    file_errors.append("vkey_missing@%s/%s" % (dh, label))
                    usable = False
                elif not frozen.get("frozen_vkey_sha256"):
                    file_errors.append("vkey_sha_absent@%s/%s" % (dh, label))
                    usable = False
                elif sha256_file(vkey_path) != frozen["frozen_vkey_sha256"]:
                    file_errors.append("vkey_sha_mismatch@%s/%s" % (dh, label))
                    usable = False
        designs.append({
            "design_hash": dh, "x12": rec.get("x12"), "group": rec.get("group", ""),
            "status": rec.get("status"), "usable": bool(usable),
            "roles": rec.get("roles") or {}, "families": families,
            "attempts": rec.get("attempts"), "arm_blind": True,
            "record_hash": rec.get("record_hash"), "seq": rec.get("seq"),
        })
    chain_valid = bool(report["valid"])
    if not chain_valid:
        # A5 RUN-07: a broken chain can never yield usable designs.
        for design in designs:
            design["usable"] = False
    if verify_files and (not chain_valid or file_errors):
        detail = ",".join(([("chain_invalid:" + e) for e in report["errors"][:3]] + file_errors)[:8])
        if not allow_invalid:
            raise FreezeApiError("FINAL_RUN_MANIFEST_REFUSED: " + detail)
    manifest = {
        "schema": "dreal001.freeze_api.final_run_manifest.v1",
        "issued": bool(chain_valid and not file_errors and not allow_invalid),
        "api_version": API_VERSION, "batch_id": str(batch_id), "created_utc": utc_now(),
        "append_only_log_path": str(log_path), "append_only_log_sha256": sha256_file(log_path),
        "chain": report, "designs": designs,
        "designs_total": len(designs),
        "designs_usable": sum(1 for d in designs if d["usable"]),
        "file_errors": file_errors,
        "manifest_source_sha256": str(manifest_source_sha256),
        "policy_doc_sha256": str(policy_doc_sha256),
        "builder_code_sha256": str(builder_code_sha256),
        "physical_call_count": 0, "solver_started": False,
    }
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------- worker
def _worker(task_path: Path, out_path: Path) -> None:
    from research.concorde_metaopt.aircraft.design_space import load_design_space
    from research.concorde_metaopt.aircraft.geometry_model import build_geometry
    from research.concorde_metaopt.dreal001.geometry import openvsp_model
    from research.concorde_metaopt.dreal001.geometry.mesh_identity import describe_mesh
    from research.concorde_metaopt.dreal001.geometry.task_spec import TASK_SPEC

    task = json.loads(task_path.read_text(encoding="utf-8"))
    space = load_design_space(Path(task["config_path"]))
    names = list(space.names) + [f.name for f in space.fixed_variables]
    values = dict(space.baseline_dict())
    for fixed in space.fixed_variables:
        values[fixed.name] = float(fixed.baseline)
    for name, value in zip(space.names, [float(v) for v in task["x12"]]):
        values[name] = float(value)
    geometry = build_geometry(names, [float(values[name]) for name in names])
    case_dir = Path(tempfile.mkdtemp(prefix="freezeapi_", dir=task["tmp_root"]))
    record: Dict[str, Any] = {"design_hash": task["design_hash"], "requested_family": task.get("requested_family"),
                              "pid": os.getpid(), "process_start_utc": utc_now(), "family": None, "error": None}
    started = time.perf_counter()
    try:
        prepared = openvsp_model.prepare_case(
            geometry, case_dir, "concorde_baseline", geometry_set=task.get("geometry_set", "thin"),
            alphas_deg=list(TASK_SPEC.alpha_fixed_list_deg), tess_u=task.get("tess_u", 12.0),
            tess_w=task.get("tess_w", 25.0), openvsp_root=task.get("openvsp_root"),
            rebuild_strategy="direct", target_mesh_family=None, max_mesh_attempts=1, write_vsp3=True)
        mesh = prepared.get("mesh") or {}
        geom_path = case_dir / "concorde_baseline.vspgeom"
        parsed = describe_mesh(geom_path)
        record.update({
            "family": parsed.get("mesh_family"),
            "nodes": parsed.get("nodes"), "elements": parsed.get("elements"),
            "prepared_family": mesh.get("mesh_family"),
            "prepared_nodes": mesh.get("nodes"), "prepared_elements": mesh.get("elements"),
            "parsed_matches_prepared": (mesh.get("nodes"), mesh.get("elements"))
                == (parsed.get("nodes"), parsed.get("elements")),
            "vspgeom_sha256": parsed.get("vspgeom_sha256"),
            "canonical_mesh_sha256": parsed.get("canonical_mesh_sha256"),
        })
        requested = task.get("requested_family")
        requested_pair = parse_family(requested)
        parsed_pair = parse_family(record["family"])
        if requested_pair and parsed_pair == requested_pair:
            target = Path(task["freeze_dir"])
            target.mkdir(parents=True, exist_ok=True)
            for suffix in ("vspgeom", "vkey", "vsp3"):
                source = case_dir / ("concorde_baseline." + suffix)
                if source.is_file():
                    shutil.copyfile(source, target / ("model." + suffix))
            geom_target = target / "model.vspgeom"
            vkey_target = target / "model.vkey"
            vsp3_target = target / "model.vsp3"
            record.update({
                "frozen_vspgeom_path": str(geom_target),
                "frozen_vspgeom_sha256": sha256_file(geom_target),
                "frozen_vspgeom_bytes": geom_target.stat().st_size,
                "frozen_vkey_path": str(vkey_target) if vkey_target.is_file() else None,
                "frozen_vkey_sha256": sha256_file(vkey_target) if vkey_target.is_file() else None,
                "frozen_vsp3_sha256": sha256_file(vsp3_target) if vsp3_target.is_file() else None,
                "frozen_vsp3_path": str(vsp3_target) if vsp3_target.is_file() else None,
            })
    except Exception as exc:  # noqa: BLE001
        record["error"] = "%s: %s" % (type(exc).__name__, str(exc)[:300])
    finally:
        record["build_s"] = round(time.perf_counter() - started, 4)
        record["worker_end_utc"] = utc_now()
        shutil.rmtree(case_dir, ignore_errors=True)
    out_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")


class FreshProcessBuilder:
    """Production builder: one fresh Python process per geometry build (no solver)."""

    def __init__(self, *, config_path: Optional[Path] = None, geometry_set: str = "thin",
                 tess_u: float = 12.0, tess_w: float = 25.0, timeout_s: int = 300,
                 max_infra_retries: int = 4) -> None:
        self.config_path = str(config_path or _default_config_path())
        self.geometry_set = geometry_set
        self.tess_u = tess_u
        self.tess_w = tess_w
        self.timeout_s = int(timeout_s)
        self.max_infra_retries = int(max_infra_retries)

    def __call__(self, x12: Sequence[float], requested_family: Optional[str], freeze_dir: Optional[Path]) -> Dict[str, Any]:
        tmp_root = Path(tempfile.mkdtemp(prefix="freezeapi_root_"))
        task_path = tmp_root / "task.json"
        out_path = tmp_root / "out.json"
        task = {"design_hash": _design_hash(x12), "x12": [float(v) for v in x12],
                "requested_family": requested_family, "freeze_dir": str(freeze_dir) if freeze_dir else None,
                "tmp_root": str(tmp_root), "config_path": self.config_path,
                "geometry_set": self.geometry_set, "tess_u": self.tess_u, "tess_w": self.tess_w}
        record: Optional[Dict[str, Any]] = None
        for infra_attempt in range(1, self.max_infra_retries + 2):
            task_path.write_text(json.dumps(task, ensure_ascii=False), encoding="utf-8")
            workdir = Path(tempfile.mkdtemp(prefix="freezeapi_cwd_", dir=str(tmp_root)))
            tmpdir = workdir / "tmp"
            tmpdir.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ)
            env["TMP"] = str(tmpdir)
            env["TEMP"] = str(tmpdir)
            try:
                completed = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--worker", str(task_path), str(out_path)],
                    capture_output=True, text=True, timeout=self.timeout_s, cwd=str(workdir), env=env)
            except subprocess.TimeoutExpired:
                completed = None
            if completed is not None and completed.returncode == 0 and out_path.is_file():
                record = json.loads(out_path.read_text(encoding="utf-8"))
                record["infra_attempts"] = infra_attempt
                break
            record = {"design_hash": task["design_hash"], "requested_family": requested_family,
                      "family": None, "pid": None, "error": "worker_infra_failure",
                      "stderr_tail": (completed.stderr[-300:] if completed is not None else "timeout"),
                      "infra_attempts": infra_attempt}
        shutil.rmtree(tmp_root, ignore_errors=True)
        return record or {"design_hash": task["design_hash"], "family": None, "error": "worker_no_record"}


# --------------------------------------------------------------------------- freeze
def _finalize(out_dir: Path, record: Dict[str, Any], log_path: Optional[Path],
              design_hash: str, group: str) -> Dict[str, Any]:
    """Write freeze_record.json + SHA256SUMS, and append one chained design record."""
    record["group"] = str(group)
    record["created_utc"] = record.get("created_utc") or utc_now()
    if log_path is not None:
        payload = {
            "kind": "DESIGN_FREEZE", "design_hash": str(design_hash), "x12": record["x12"],
            "group": str(group), "status": record["status"], "roles": record["roles"],
            "families": record["families"], "attempts": record["attempts"],
            "builder_code_sha256": record["builder_sha"], "builder_kind": record["builder_kind"],
            "policy": record["policy"], "arm_blind": True,
            "discovery": record["discovery"], "created_utc": record["created_utc"],
        }
        record["freeze_log"] = append_chained_record(Path(log_path), payload)
    _write_record(out_dir, record)
    return record


def discover_and_freeze_pair(x12: Sequence[float], design_hash: str, out_dir: Path,
                             policy: Optional[Mapping[str, Any]] = None, builder_sha: str = "",
                             *, builder: Optional[Callable[..., Dict[str, Any]]] = None,
                             group: str = "", log_path: Optional[Path] = None) -> Dict[str, Any]:
    """Arm-blind discovery + forcing + freezing. Returns the freeze record (also written to disk)."""
    policy = dict(DEFAULT_POLICY, **(dict(policy or {})))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    x12 = [float(v) for v in x12]
    computed = _design_hash(x12)
    record: Dict[str, Any] = {
        "schema": SCHEMA, "api_version": API_VERSION, "created_utc": utc_now(),
        "x12": x12, "design_hash_requested": str(design_hash), "design_hash_computed": computed,
        "policy": policy, "builder_sha": str(builder_sha),
        "builder_kind": "INJECTED" if builder is not None else "FRESH_OPENVSP_PROCESS",
        "physical_call_count": 0, "solver_started": False,
        "source_kind": "OPENVSP_GEOMETRY_SYNTHETIC", "status": None,
        "roles": {}, "families": {}, "discovery": {"attempts": 0, "observed": []},
        "freeze": {}, "attempts": 0, "error": None,
    }
    attempts_path = out_dir / "attempts.jsonl"
    log_path = Path(log_path) if log_path is not None else out_dir / FREEZE_LOG_NAME
    builder = builder or FreshProcessBuilder()
    if computed != str(design_hash):
        record["status"] = STATUS_HASH_MISMATCH
        record["error"] = "computed design_hash %s != requested %s" % (computed, design_hash)
        return _finalize(out_dir, record, log_path, design_hash, group)

    observed: List[str] = []
    attempts = 0
    discovery_cap = int(policy["discovery_cap"])
    extend_single = int(policy["single_family_extend"])
    union_void_at = int(policy["union_void_at"])
    # K=10 arm-blind discovery always runs the full cap: stopping at the second
    # family would hide a third family and turn a VOID design into PAIR_READY.
    while attempts < discovery_cap:
        attempts += 1
        rec = builder(x12, None, None)
        _append_attempt(attempts_path, rec, "discovery", attempts)
        fam = rec.get("family")
        if fam:
            observed.append(str(fam))
            if len(set(observed)) >= union_void_at:
                break
    # Only a single-family union is extended (up to 40) looking for the second.
    while len(set(observed)) == 1 and attempts < extend_single:
        attempts += 1
        rec = builder(x12, None, None)
        _append_attempt(attempts_path, rec, "discovery", attempts)
        fam = rec.get("family")
        if fam:
            observed.append(str(fam))
    record["discovery"] = {"attempts": attempts, "observed": observed,
                           "family_set": sorted(set(observed))}
    family_set = sorted(set(observed), key=lambda lab: parse_family(lab) or (0, 0))
    record["attempts"] = attempts
    if len(family_set) >= union_void_at:
        record["status"] = STATUS_DESIGN_VOID
        record["error"] = "family union |F|>=%d" % union_void_at
        return _finalize(out_dir, record, log_path, design_hash, group)
    if not family_set:
        record["status"] = STATUS_NO_FAMILY
        record["error"] = "no family observed"
        return _finalize(out_dir, record, log_path, design_hash, group)
    if len(family_set) == 1:
        record["status"] = STATUS_FAMILY_UNREACHABLE
        record["error"] = "only one family observed after %d fresh builds" % attempts
        return _finalize(out_dir, record, log_path, design_hash, group)

    roles = role_map(family_set)
    record["roles"] = roles
    cap = int(policy["cap_per_family"])
    for role in ("f1", "f2"):
        label = roles[role]
        freeze_dir = out_dir / "freeze" / label
        if freeze_dir.exists():
            shutil.rmtree(freeze_dir)
        freeze_dir.mkdir(parents=True, exist_ok=True)
        fam_rec: Dict[str, Any] = {"family_label": label, "mesh_family": list(parse_family(label) or ()),
                                   "attempts": 0, "hit": False, "frozen": None, "error": None, "first_error": None}
        for attempt in range(1, cap + 1):
            fam_rec["attempts"] = attempt
            record["attempts"] += 1
            rec = builder(x12, label, freeze_dir)
            _append_attempt(attempts_path, rec, "force_" + role, attempt)
            fam_rec["last_family"] = rec.get("family")
            fam_rec["first_error"] = fam_rec["first_error"] or rec.get("error")
            if rec.get("error"):
                continue
            if rec.get("family") != label:
                continue
            if rec.get("parsed_matches_prepared") is False:
                fam_rec["error"] = "prepared_parsed_mismatch"
                continue
            if not rec.get("frozen_vspgeom_sha256"):
                fam_rec["error"] = "missing_frozen_artifact"
                continue
            fam_rec["hit"] = True
            fam_rec["frozen"] = {
                "frozen_vspgeom_path": rec["frozen_vspgeom_path"],
                "frozen_vspgeom_sha256": rec["frozen_vspgeom_sha256"],
                "frozen_vspgeom_bytes": int(rec["frozen_vspgeom_bytes"]),
                "frozen_vkey_path": rec.get("frozen_vkey_path"),
                "frozen_vkey_sha256": rec.get("frozen_vkey_sha256"),
                "frozen_vsp3_sha256": rec.get("frozen_vsp3_sha256"),
                "frozen_vsp3_path": rec.get("frozen_vsp3_path"),
                "vspgeom_sha256": rec["frozen_vspgeom_sha256"],
                "canonical_mesh_sha256": rec.get("canonical_mesh_sha256"),
            }
            break
        if not fam_rec["hit"] and fam_rec["error"] is None:
            fam_rec["error"] = "TARGET_UNREACHABLE_WITHIN_CAP"
        record["families"][label] = fam_rec

    if all(record["families"][roles[r]]["hit"] for r in ("f1", "f2")):
        record["status"] = STATUS_PAIR_READY
    else:
        record["status"] = STATUS_FAMILY_UNREACHABLE
        record["error"] = "one or both target families unreachable within cap"
    record["freeze"] = {
        "freeze_dir": str(out_dir / "freeze"),
        "vspgeom_total_bytes": sum(int(f["frozen"]["frozen_vspgeom_bytes"]) for f in record["families"].values() if f.get("hit")), 
    }
    return _finalize(out_dir, record, log_path, design_hash, group)


def _append_attempt(path: Path, rec: Mapping[str, Any], stage: str, attempt: int) -> None:
    row = {"stage": stage, "attempt": int(attempt), "utc": utc_now()}
    row.update({k: rec.get(k) for k in ("family", "requested_family", "design_hash", "pid", "error",
                                        "nodes", "elements", "prepared_family", "parsed_matches_prepared",
                                        "vspgeom_sha256", "canonical_mesh_sha256", "build_s",
                                        "infra_attempts", "frozen_vspgeom_sha256")})
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_record(out_dir: Path, record: Dict[str, Any]) -> None:
    path = out_dir / "freeze_record.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sums = []
    for item in sorted(out_dir.rglob("*")):
        if item.is_file() and item.name != "SHA256SUMS.txt":
            sums.append(sha256_file(item) + "  " + item.relative_to(out_dir).as_posix())
    (out_dir / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8")


if __name__ == "__main__" and "--worker" in sys.argv:
    idx = sys.argv.index("--worker")
    _worker(Path(sys.argv[idx + 1]), Path(sys.argv[idx + 2]))
