import argparse, hashlib, json, math, re
from pathlib import Path

SCHEMA = "dreal001.independent_audit_record.v1"
ARTIFACT_KINDS = ("deck", "history", "mesh", "polar")
GEOMETRY_CONTRACT = "5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15"
TASK_LIFT_N = 1333704.4
TASK_LIFT_TOL = 1e-3
RHO = 0.1153178340089936
VINF = 596.0373972278921

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def canon(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def deck_fields(text):
    fields = {}
    for line in text.splitlines():
        m = re.fullmatch(r"\s*([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*", line)
        if m:
            if m.group(1) in fields:
                raise SystemExit("duplicate deck field " + m.group(1))
            fields[m.group(1)] = m.group(2)
    return fields

def polar_rows(text):
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        parts = line.split()
        if parts[:4] == ["Beta", "Mach", "AoA", "Re/1e6"]:
            header_idx = i
            header = parts
            break
    if header_idx is None:
        raise SystemExit("polar header not found")
    rows = []
    for line in lines[header_idx + 1:]:
        parts = line.split()
        if len(parts) != len(header):
            continue
        try:
            vals = [float(x) for x in parts]
        except ValueError:
            continue
        rows.append(dict(zip(header, vals)))
    return header, rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-dir", required=True)
    ap.add_argument("--audit-id", required=True)
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--reviewer-role", required=True)
    ap.add_argument("--created-utc", required=True)
    ap.add_argument("--verdict", default="ADMIT_REAL_LABEL")
    ap.add_argument("--geometry-contract", default=GEOMETRY_CONTRACT)
    ap.add_argument("--lift-target", type=float, default=TASK_LIFT_N)
    ap.add_argument("--lift-tolerance", type=float, default=TASK_LIFT_TOL)
    args = ap.parse_args()
    case = Path(args.case_dir)
    plan = json.loads((case / "plan.json").read_text(encoding="utf-8"))
    result = json.loads((case / "case_result.json").read_text(encoding="utf-8"))
    base = result["attempt"]["basename"]
    paths = {
        "mesh": case / (base + ".vspgeom"),
        "deck": case / (base + ".vspaero"),
        "polar": case / (base + ".polar"),
        "history": case / (base + ".history"),
    }
    artifacts = []
    for kind in ARTIFACT_KINDS:
        p = paths[kind]
        artifacts.append({"kind": kind, "sha256": sha(p), "bytes": p.stat().st_size})
    artifact_sha = canon(artifacts)
    deck = deck_fields(paths["deck"].read_text(encoding="utf-8"))
    grid = [float(x.strip()) for x in deck["AoA"].split(",")]
    header, rows = polar_rows(paths["polar"].read_text(encoding="utf-8"))
    q = 0.5 * float(deck["Rho"]) * float(deck["Vinf"]) ** 2
    sref = float(deck["Sref"])
    cl_target = args.lift_target / (q * sref)
    matched = []
    for row in rows:
        err = abs(q * sref * row["CLtot"] - args.lift_target) / args.lift_target
        matched.append((err, row["AoA"], row["CLtot"], row["CDi"]))
    matched.sort()
    best = matched[0]
    if best[0] > args.lift_tolerance:
        raise SystemExit("no row meets lift tolerance: %r" % (best,))
    x12 = [float(x) for x in plan["design"]["x12"]]
    design_id = canon(x12)
    record = {
        "schema": SCHEMA,
        "audit_id": args.audit_id,
        "run_id": plan["run_id"],
        "task_id": plan["task_id"],
        "design_id": design_id,
        "geometry_sha256": args.geometry_contract,
        "artifact_sha256": artifact_sha,
        "reviewer": args.reviewer,
        "reviewer_role": args.reviewer_role,
        "verdict": args.verdict,
        "created_utc": args.created_utc,
        "notes": {
            "audit_scope": "SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5",
            "method": "independent hash/size scan, deck field parse, polar row scan, lift residual recomputation",
            "deck_sref": sref,
            "deck_mach": float(deck["Mach"]),
            "deck_rho": float(deck["Rho"]),
            "deck_vinf": float(deck["Vinf"]),
            "alpha_grid_deg": grid,
            "polar_rows": len(rows),
            "lift_target_n": args.lift_target,
            "q_pa": q,
            "cl_target": cl_target,
            "matched_lift_row": {"alpha_deg": best[1], "cl": best[2], "cdi": best[3], "rel_error": best[0]},
            "artifact_sha256_definition": "canonical_sha of sorted deck/history/mesh/polar kinds with sha256+bytes",
            "not_authenticated": "hashes bind bytes only; reviewer identity and provenance are not authenticated",
        },
    }
    out = case / "audit.json"
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"audit": str(out), "artifact_sha256": artifact_sha,
                      "matched_lift_row": record["notes"]["matched_lift_row"],
                      "audit_sha256": sha(out)}, indent=2))

if __name__ == "__main__":
    main()
