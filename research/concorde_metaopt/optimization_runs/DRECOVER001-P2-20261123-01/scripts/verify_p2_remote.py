
"""Independent A4-style remote retrieval + recompute for the P2 16 real cases.

Reads only GitHub blob API bytes (no local raw files) for each case's polar and
certificate, then recomputes CL/CDi and Di_N = q * Sref * CDi from the raw polar row.
"""
from __future__ import annotations
import base64, hashlib, json, re, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
OUT = RUN / "remote_retrieval"
OUT.mkdir(parents=True, exist_ok=True)
BRANCH = "research/dreal004-alpha-adaptive-meta-sampling"
OREPO = "QingYangJin/RCAIDE_Supersonic"
RUN_REL = "research/concorde_metaopt/optimization_runs/DRECOVER001-P2-20261123-01"
TOK = re.search(r"GITHUB_TOKEN:\s*([^\s]+)",
                Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8")).group(1).strip().strip('"').strip("'")
HEADERS = {"Authorization": "Bearer " + TOK, "Accept": "application/vnd.github+json", "User-Agent": "p2-a4"}


def api(path: str):
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request("https://api.github.com" + path, headers=HEADERS)
            # path already absolute (starts with /repos)
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + 2 * attempt)
    raise RuntimeError("api failed %s: %r" % (path, last))


def blob(sha: str) -> bytes:
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request("https://api.github.com/repos/" + OREPO + "/git/blobs/" + sha, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=180) as r:
                doc = json.loads(r.read().decode())
            return base64.b64decode(doc["content"])
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + 2 * attempt)
    raise RuntimeError("blob failed %s: %r" % (sha, last))


def tree(sha: str):
    return api("/repos/" + OREPO + "/git/trees/" + sha)


def find(root_sha: str, parts):
    cur = root_sha
    for i, part in enumerate(parts):
        doc = tree(cur)
        hit = next((e for e in doc["tree"] if e["path"] == part), None)
        if hit is None:
            return None
        cur = hit["sha"]
    return cur


def parse_polar(text: str):
    lines = text.splitlines()
    hi = next(i for i, l in enumerate(lines) if "AoA" in l and "CLtot" in l and "CDi" in l)
    header = lines[hi].split()
    ri = header.index("AoA")
    ci = header.index("CDi")
    li = header.index("CLtot")
    rows = []
    for l in lines[hi + 1:]:
        parts = l.split()
        if len(parts) != len(header):
            continue
        try:
            rows.append([float(x) for x in parts])
        except ValueError:
            continue
    return header, rows, ri, ci, li


ref = api("/repos/" + OREPO + "/git/ref/heads/" + BRANCH)
head = ref["object"]["sha"]
commit = api("/repos/" + OREPO + "/git/commits/" + head)
run_tree = find(commit["tree"]["sha"], RUN_REL.split("/") + ["raw_cases"])
if run_tree is None:
    raise SystemExit("raw_cases tree not found")
listing = tree(run_tree)
cases = sorted((e for e in listing["tree"] if e["type"] == "tree"), key=lambda e: e["path"])

results, bad = [], []
for entry in cases:
    name = entry["path"]
    cdir = tree(entry["sha"])
    by_name = {e["path"]: e["sha"] for e in cdir["tree"]}
    cert_b = blob(by_name["admission_certificate.json"])
    polar_b = blob(by_name[name + ".polar"])
    cert = json.loads(cert_b.decode())
    polar_sha = hashlib.sha256(polar_b).hexdigest()
    header, rows, ri, ci, li = parse_polar(polar_b.decode("utf-8", "replace"))
    match = min(rows, key=lambda r: abs(r[ri] - cert["alpha_deg"]))
    alpha_err = abs(match[ri] - cert["alpha_deg"])
    cl = match[li]
    cdi = match[ci]
    di = cert["q_pa"] * cert["sref_m2"] * cdi
    rel = abs(di - cert["di_n"]) / abs(cert["di_n"])
    checks = {
        "case": name, "remote_polar_sha256": polar_sha,
        "certificate_raw_sha256_matches_remote_polar": polar_sha == cert["raw_sha256"],
        "alpha_row_abs_error_deg": alpha_err,
        "recomputed_cl": cl, "certificate_cl": cert["cl"],
        "cl_abs_error": abs(cl - cert["cl"]),
        "recomputed_cdi": cdi, "certificate_cdi": cert["cdi"],
        "recomputed_di_n": di, "certificate_di_n": cert["di_n"],
        "di_n_rel_error": rel,
        "pass": (polar_sha == cert["raw_sha256"] and alpha_err <= 1e-6
                 and abs(cl - cert["cl"]) <= 1e-6 and abs(cdi - cert["cdi"]) <= 1e-6
                 and rel <= 1e-9),
    }
    results.append(checks)
    if not checks["pass"]:
        bad.append(checks)

labels = json.loads((RUN / "p2_dataset" / "p2_dataset.json").read_text(encoding="utf-8"))
audit = {
    "schema": "dreal004.p2_remote_retrieval_audit.v1",
    "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "method": "GitHub blob API raw bytes for remote certificates and polar files; recompute CL/CDi from the raw row at the certified alpha and Di_N = q*Sref*CDi; no local raw file is read",
    "remote_head": head,
    "remote_run_tree": run_tree,
    "remote_case_count": len(cases),
    "expected_case_count": 16,
    "cases_checked": len(results),
    "cases_ok": sum(1 for r in results if r["pass"]),
    "bad": bad,
    "dataset_rows": labels["rows"],
    "dataset_certificates": labels["certificates"],
    "a4_criteria_met": len(cases) == 16 and len(bad) == 0,
    "cases": results,
}
p = OUT / "p2_remote_retrieval_audit.json"
p.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps({k: audit[k] for k in ("remote_head", "remote_case_count", "cases_ok", "a4_criteria_met")}, ensure_ascii=False))
print("sha256", hashlib.sha256(p.read_bytes()).hexdigest())
