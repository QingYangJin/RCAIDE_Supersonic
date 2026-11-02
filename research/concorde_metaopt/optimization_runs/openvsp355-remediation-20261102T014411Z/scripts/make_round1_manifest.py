# Build data_manifest.json for the D-12D-003 Round-1 package.
# Hashing convention: sha256 over canonical LF bytes of each file (CRLF -> LF), so a clean checkout
# of the commit containing this manifest reproduces every hash exactly. bytes = length of that blob.
import hashlib
import json
import time
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
REPO = Path("D:/RCAIDE")
OUT = REPO / "outputs" / "concorde_metaopt" / RUN.name

BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".pdf", ".vspgeom"}

def hash_file(path):
    data = path.read_bytes()
    if path.suffix.lower() in BINARY_EXT:
        return hashlib.sha256(data).hexdigest(), len(data), "raw"
    canon = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(canon).hexdigest(), len(canon), "canonical_lf"

def entries(root, just_these=None, skip=()):
    out = []
    items = [root / p for p in just_these] if just_these else sorted(p for p in root.rglob("*") if p.is_file())
    for p in items:
        if not p.is_file():
            raise SystemExit(f"missing file: {p}")
        rel = str(p.relative_to(root)).replace("\\", "/")
        if rel in skip:
            continue
        sha, n, mode = hash_file(p)
        out.append({"path": rel, "bytes": n, "sha256": sha, "hash_mode": mode})
    return out

run_files = entries(RUN, skip=("data_manifest.json",))

inputs = [
    "research/concorde_metaopt/configs/design_space_12d_lifting_surfaces.yaml",
    "research/concorde_metaopt/configs/task_fixed_cruise.yaml",
    "research/concorde_metaopt/aircraft/openvsp_geometry.py",
    "research/concorde_metaopt/aircraft/openvsp_check.py",
    "research/concorde_metaopt/aircraft/concorde_adapter.py",
    "research/concorde_metaopt/evaluation/low_fidelity.py",
    "research/concorde_metaopt/evaluation/high_fidelity.py",
    "research/concorde_metaopt/evaluation/drag_ledger.py",
]
input_entries = []
for rel in inputs:
    p = REPO / rel
    sha, n, mode = hash_file(p)
    input_entries.append({"path": rel, "bytes": n, "sha256": sha, "hash_mode": mode})

report_rel = "docs/reviews/p1p3_d12d003_round1_remediation_report_20261102.md"
report_sha, report_n, report_mode = hash_file(REPO / report_rel)

raw_files = entries(OUT) if OUT.is_dir() else []
raw_manifest = {
    "schema_version": 1,
    "run_id": RUN.name,
    "archive_root": str(OUT).replace("\\", "/"),
    "note": "large .vspgeom artifacts kept outside git; hashes are sha256 of the stored bytes (raw for binaries, canonical LF for text)",
    "files": raw_files,
    "file_count": len(raw_files),
    "total_bytes": sum(f["bytes"] for f in raw_files),
}
(OUT / "raw_artifacts_manifest.json").write_text(json.dumps(raw_manifest, indent=2) + "\n", encoding="utf-8", newline="\n")

manifest = {
    "schema_version": 1,
    "run_id": RUN.name,
    "stage": "P1-P3 D-12D-003 Round-1 remediation (zero solver cases; one unbillable banner probe)",
    "approval": "Issue #4 / D-12D-003 (comment 6566994749)",
    "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "git_sha_at_run_start": "5dcb0bf09335fd6f73363d0280a667286d6d20f9",
    "revision": "post-review revision 2 (A5 task-41 findings resolved; A3/A1 reviews archived)",
    "hashing_convention": "per-entry hash_mode: text is sha256 over canonical LF bytes (CRLF -> LF), binaries are sha256 of the raw stored bytes. For binary entries bytes = raw file length; for text entries bytes = canonical LF blob length. Reproduce from a clean checkout of the commit that contains this manifest.",
    "file_count": len(run_files),
    "total_bytes": sum(f["bytes"] for f in run_files),
    "files": run_files,
    "input_source_files": input_entries,
    "report_file": {"path": report_rel, "bytes": report_n, "sha256": report_sha, "hash_mode": report_mode},
    "raw_artifacts": {
        "manifest": "raw_artifacts_manifest.json",
        "archive_root": str(OUT).replace("\\", "/"),
        "file_count": raw_manifest["file_count"],
        "total_bytes": raw_manifest["total_bytes"],
        "outside_git": True,
        "note": "the .vspgeom files are inputs for a future owner-approved Round-2; they are not evidence of any physical result",
    },
    "figure_count": sum(1 for f in run_files if f["path"].startswith("figures/")),
    "role_reviews": {
        "dir": "role_reviews/",
        "roles": ["A1", "A2", "A3", "A4", "A5"],
        "note": "canonical-LF copies of project-external role deliverables; raw-byte hashes for CRLF-origin files are listed in role_reviews/README.md. No reviewer started a solver or wrote to the repo/GitHub in Round-1",
    },
    "solver_cases": 0,
    "billable_numerical_analyses": 0,
    "unbillable_version_probe_processes": 1,
    "note": "TG-008 was one no-model vspaero.exe usage-banner process launch: unbillable, not a solver case (A1 task-43 F1). Process-level absence of any solver process is not claimed (F6).",
    "solver_starts": 0,
    "numerical_analysis_starts": 0,
}
(RUN / "data_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({"file_count": manifest["file_count"], "total_bytes": manifest["total_bytes"], "raw_files": raw_manifest["file_count"], "figure_count": manifest["figure_count"]}, indent=1))
sha, n, mode = hash_file(RUN / "data_manifest.json")
print("manifest sha256:", sha)
