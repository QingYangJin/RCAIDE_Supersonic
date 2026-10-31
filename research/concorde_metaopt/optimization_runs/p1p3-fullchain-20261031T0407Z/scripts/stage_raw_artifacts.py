
import hashlib, json, shutil, time
from pathlib import Path

EXT = Path(r"C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/fullchain")
OUT = Path(r"D:/RCAIDE/outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z")
RUN = Path(r"D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z")

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

entries = []

def copy_group(src_dir, dst_rel, glob_pat="**/*", skip=()):
    src_dir = Path(src_dir)
    dst_dir = OUT / dst_rel
    dst_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(src_dir.glob(glob_pat)):
        if not p.is_file():
            continue
        rel = p.relative_to(src_dir)
        if any(str(rel).endswith(s) for s in skip):
            continue
        d = dst_dir / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, d)
        entries.append({"group": dst_rel, "file": str(Path(dst_rel) / rel).replace("\\", "/"),
                        "bytes": d.stat().st_size, "sha256": sha256(d),
                        "source_abs": str(p).replace("\\", "/")})
        n += 1
    print(f"copied {n} files -> {dst_rel}")

# LF raw: per-case exported geometry, polar, setup templates, logs
for case in ["baseline", "w01_plus1pct", "w03_plus1deg", "w10_plus2", "sens_coarse", "sens_fine"]:
    copy_group(EXT / "lf" / case, f"lf_raw/{case}")
copy_group(EXT / "lf_mission", "lf_raw/mission_records", "*.json")

# HF raw: wing meshes/cfg/history/surface/restart/logs + wedge verification
copy_group(EXT / "hf" / "wing", "hf_raw/wing")
copy_group(EXT / "hf" / "wedge", "hf_raw/wedge")

manifest = {
    "schema_version": 1,
    "archive_root": str(OUT).replace("\\", "/"),
    "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "note": "Large raw solver artefacts (meshes, restart/field CSV, histories, logs, DegenGeom, VSPAERO polars, wave-drag slice files) are archived outside the git working tree with hashes; the run directory keeps only the parsed JSON/CSV/PNG evidence and a pointer to this manifest.",
    "policy": "D-12D-002 requires large meshes/field data in the ignored outputs/concorde_metaopt/ with a hash index; this manifest provides it.",
    "file_count": len(entries),
    "total_bytes": sum(e["bytes"] for e in entries),
    "files": entries,
}
(OUT / "raw_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
summary = {"schema_version": 1, "raw_manifest": "outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/raw_manifest.json",
           "raw_manifest_sha256": sha256(OUT / "raw_manifest.json"),
           "file_count": manifest["file_count"], "total_bytes": manifest["total_bytes"],
           "groups": {g: sum(1 for e in entries if e["group"] == g) for g in sorted({e["group"] for e in entries})},
           "wave_raw_dir": "outputs/concorde_metaopt/p1p3-fullchain-20261031T0407Z/wave_raw",
           "note": manifest["note"]}
(RUN / "raw_artifacts_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2)[:1500])
print("MB:", round(manifest["total_bytes"] / 1e6, 1))
