
import hashlib, json, os, time
from pathlib import Path

RUN = Path(r"D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z")
OUT = Path(r"D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z")

for d in ("large_artifacts", "meshes", "raw", "solver_logs"):
    p = OUT / d
    if p.is_dir() and not any(p.iterdir()):
        p.rmdir()
        print("removed empty", d)

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def walk_manifest(root):
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files.append({"file": str(p.relative_to(OUT)).replace("\\", "/"), "bytes": p.stat().st_size, "sha256": sha256(p)})
    return files

raw = json.loads((OUT / "raw_manifest.json").read_text(encoding="utf-8"))
wave_files = walk_manifest(OUT / "wave_raw")
wave_summary = {
    "dir": "outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/wave_raw",
    "manifest": "outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/wave_raw/wave_raw_manifest.json",
    "manifest_sha256": sha256(OUT / "wave_raw" / "wave_raw_manifest.json"),
    "file_count": len(wave_files),
    "total_bytes": sum(f["bytes"] for f in wave_files),
    "manifest_json_sha256": sha256(OUT / "wave_raw" / "wave_raw_manifest.json"),
}

summary = {
    "schema_version": 1,
    "run_id": RUN.name,
    "archive_root": str(OUT).replace("\\", "/"),
    "note": raw["note"],
    "policy": raw["policy"],
    "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "lf_hf": {
        "manifest": "outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/raw_manifest.json",
        "manifest_sha256": sha256(OUT / "raw_manifest.json"),
        "file_count": raw["file_count"],
        "total_bytes": raw["total_bytes"],
        "groups": {g: sum(1 for e in raw["files"] if e["group"] == g) for g in sorted({e["group"] for e in raw["files"]})},
    },
    "wave": wave_summary,
    "combined_file_count": raw["file_count"] + len(wave_files),
    "combined_total_bytes": raw["total_bytes"] + sum(f["bytes"] for f in wave_files),
}
(RUN / "raw_artifacts_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

inputs = [
    "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
    "research/concorde_metaopt/configs/task_fixed_cruise.yaml",
    "tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py",
    "research/concorde_metaopt/aircraft/concorde_adapter.py",
    "research/concorde_metaopt/evaluation/low_fidelity.py",
    "research/concorde_metaopt/evaluation/drag_ledger.py",
]
repo = Path(r"D:/RCAIDE")
input_entries = []
for rel in inputs:
    p = repo / rel
    input_entries.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha256(p)})

run_files = []
for p in sorted(RUN.rglob("*")):
    if not p.is_file():
        continue
    rel = str(p.relative_to(RUN)).replace("\\", "/")
    if rel == "data_manifest.json":
        continue
    run_files.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha256(p)})

manifest = {
    "schema_version": 1,
    "run_id": RUN.name,
    "stage": "P1-P3 full-chain multi-fidelity validation (D-12D-002)",
    "approval": "Issue #4 / D-12D-002 (comment 6538481816)",
    "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "git_sha_at_run_start": "048ef2e55f389b0ae52e8872131dcfcf0c91a1eb",
    "file_count": len(run_files),
    "total_bytes": sum(f["bytes"] for f in run_files),
    "files": run_files,
    "input_source_files": input_entries,
    "raw_artifacts": {
        "manifest": "raw_artifacts_manifest.json",
        "sha256": sha256(RUN / "raw_artifacts_manifest.json"),
        "archive_root": str(OUT).replace("\\", "/"),
        "file_count": summary["combined_file_count"],
        "total_bytes": summary["combined_total_bytes"],
        "outside_git": True,
    },
    "figure_count": sum(1 for f in run_files if f["path"].startswith("figures/")),
}
(RUN / "data_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps({k: manifest[k] for k in ("file_count", "total_bytes", "figure_count")}, indent=2))
print("raw combined:", summary["combined_file_count"], "files", round(summary["combined_total_bytes"] / 1e6, 1), "MB")
print("manifest sha256:", sha256(RUN / "data_manifest.json"))
