"""A4: recompute every O1 Di from the raw polar bytes that GitHub actually holds.

The Issue asks A4 to read back raw bytes and certificates at a fixed commit and recompute Di. So
this script does not read o1_result.json for any number it checks: it lists the remote tree at one
commit, downloads each case's .polar and admission_certificate.json through the blob API, parses
the polar table itself, and recomputes

    Di_N = q * Sref * CDi        (at the certified alpha, from the raw row)
    CL_target = LIFT / (q * Sref)

then compares its own numbers with the certificate and with the result file. A mismatch is
reported as a mismatch, not smoothed over.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/scripts")
import o1_upload as up  # noqa: E402

RUN = up.RUNS["O1"]
RUN_REL = up.RUN_REL_TMPL % RUN.name
COMMIT = sys.argv[1] if len(sys.argv) > 1 else None


def blob_text(sha: str, tok: str) -> str:
    d = up.api("/repos/%s/git/blobs/%s" % (up.OWNER_REPO, sha), tok)
    return base64.b64decode(d["content"]).decode("utf-8", "replace")


def parse_polar(text: str):
    """Return (columns, rows) for the VSPAERO polar table: the header row is the one that
    starts with Beta and contains AoA and CDi."""
    lines = text.splitlines()
    header_index = None
    for i, line in enumerate(lines):
        fields = line.split()
        if fields and fields[0] == "Beta" and "AoA" in fields and "CDi" in fields:
            header_index = i
            break
    if header_index is None:
        raise ValueError("no polar header found")
    cols = lines[header_index].split()
    rows = []
    for line in lines[header_index + 1:]:
        fields = line.split()
        if len(fields) != len(cols):
            continue
        try:
            rows.append({c: float(v) for c, v in zip(cols, fields)})
        except ValueError:
            continue
    return cols, rows


def main() -> int:
    tok = up.token()
    head = COMMIT or up.api("/repos/%s/git/ref/heads/%s" % (up.OWNER_REPO, up.BRANCH),
                            tok)["object"]["sha"]
    tree = up.remote_blobs(head, RUN_REL)
    print("commit %s holds %d blobs under %s" % (head, len(tree), RUN_REL), flush=True)

    result = json.loads((RUN / "o1_result.json").read_text(encoding="utf-8"))
    q = result["regression"]["dynamic_pressure_pa"]
    lift = result["regression"]["lift_target_n"]
    cases = []
    for row in result["regression"]["shared_support"]:
        cases.append(("SHARED", row["tag"], row["design_id"], row["case_ids"][-1]))
    for arm, payload in result["arms"].items():
        for record in json.loads(
                (RUN / ("o1_arm_%s.json" % arm)).read_text(encoding="utf-8"))["records"]:
            if record["case_ids"]:
                cases.append((arm, record["tag"], record["design_id"], record["case_ids"][-1]))
    # one refine case per (arm, design); the coarse case is only an alpha seed. The case id is
    # the same string in every arm, but the solver directories are per-arm and hold different
    # geometries, so the key must include the arm or three distinct runs collapse into one.
    # A shared-support design appears inside every arm's record list (it is charged to each arm),
    # but there is only one solver directory for it, under SUPPORT/. So the dedupe key is the
    # directory, not the arm: shared rows collapse to one, per-arm rows stay separate.
    seen, unique = set(), []
    for case in cases:
        group = "SUPPORT" if case[3].startswith("o1-s") else "ARM_" + case[0]
        key = (group, case[3])
        if key in seen:
            continue
        seen.add(key)
        unique.append((group,) + case)
    print("recomputing %d admitted cases" % len(unique), flush=True)

    rows_out, mismatches = [], []
    for group, arm, tag, design_id, case_id in unique:
        prefix = None
        marker = "/" + group + "/"
        for key in tree:
            if key.endswith("/" + case_id + "/admission_certificate.json") and marker in key:
                prefix = key[: -len(case_id + "/admission_certificate.json")]
                break
        if prefix is None:
            mismatches.append({"case_id": case_id, "problem": "certificate not found in remote tree"})
            continue
        cert = json.loads(blob_text(tree[prefix + case_id + "/admission_certificate.json"], tok))
        polar_key = prefix + case_id + "/" + case_id + ".polar"
        if polar_key not in tree:
            mismatches.append({"case_id": case_id, "problem": "polar not found in remote tree"})
            continue
        cols, prow = parse_polar(blob_text(tree[polar_key], tok))
        alpha = cert["alpha_deg"]
        hit = min(prow, key=lambda r: abs(r["AoA"] - alpha))
        cl_target = lift / (q * cert["sref_m2"])
        di_recomputed = q * cert["sref_m2"] * hit["CDi"]
        delta = di_recomputed - cert["di_n"]
        ok = (abs(hit["AoA"] - alpha) < 1e-6
              and abs(delta) <= 1e-6 * max(1.0, abs(cert["di_n"]))
              and abs(hit["CLtot"] - cert["cl"]) < 1e-9
              and abs(hit["CDi"] - cert["cdi"]) < 1e-9)
        rows_out.append({"arm": arm, "group": group, "tag": tag, "design_id": design_id,
                         "case_id": case_id,
                         "alpha_deg_certificate": alpha, "alpha_deg_polar_row": hit["AoA"],
                         "cl_polar": hit["CLtot"], "cl_certificate": cert["cl"],
                         "cl_target": cl_target, "cdi_polar": hit["CDi"],
                         "cdi_certificate": cert["cdi"], "di_n_recomputed": di_recomputed,
                         "di_n_certificate": cert["di_n"], "delta_n": delta, "match": ok,
                         "polar_rows_in_table": len(prow),
                         "polar_sha256_on_github": tree[polar_key]})
        if not ok:
            mismatches.append({"case_id": case_id, "delta_n": delta,
                               "alpha_gap": hit["AoA"] - alpha,
                               "cl_gap": hit["CLtot"] - cert["cl"],
                               "cdi_gap": hit["CDi"] - cert["cdi"]})
        print("  %-28s %-30s di=%.6f delta=%.3e ok=%s"
              % (arm, case_id, di_recomputed, delta, ok), flush=True)

    # independent endpoint: take the best recomputed Di inside each arm and the baseline
    by_arm = {}
    for row in rows_out:
        by_arm.setdefault(row["arm"], []).append(row)
    baseline = next(r for r in rows_out if r["tag"] == "s00")
    baseline_di = baseline["di_n_recomputed"]
    target = baseline_di * (1.0 - 0.001)
    endpoint = {}
    for arm, rows in by_arm.items():
        if arm == "SHARED":
            continue
        best = min(rows, key=lambda r: r["di_n_recomputed"])
        claimed = result["arms"][arm]["best_feasible_di_n"]
        endpoint[arm] = {"best_recomputed": best["di_n_recomputed"],
                         "best_certificate": best["di_n_certificate"],
                         "best_case": best["case_id"], "design_id": best["design_id"],
                         "claimed_best_in_result": claimed,
                         "result_matches": abs(best["di_n_recomputed"] - claimed) <= 1e-6 * max(1.0, claimed),
                         "improvement_n": baseline_di - best["di_n_recomputed"],
                         "reached_target": best["di_n_recomputed"] <= target}
    report = {
        "schema": "dreal005.a4_recompute.v1",
        "method": ("raw .polar and admission_certificate.json downloaded from the GitHub blob API "
                   "at one commit; Di recomputed as q*Sref*CDi from the polar row at the "
                   "certified alpha; nothing read from o1_result.json for the checked numbers"),
        "commit": head,
        "branch": up.BRANCH,
        "run_id": RUN.name,
        "case_count": len(rows_out),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "cases": rows_out,
        "baseline": {"tag": "s00", "case_id": baseline["case_id"],
                     "di_n_recomputed": baseline_di,
                     "di_n_claimed": result["regression"]["baseline_di_n"]},
        "target": {"rule": "baseline x (1 - 0.001)", "di_n": target,
                   "di_n_claimed": result["regression"]["target_di_n"]},
        "endpoint": endpoint,
        "checked_utc": up.now(),
        "note": ("This is a recomputation, not a re-run: no solver was invoked, and the numbers "
                 "come from bytes the remote registry serves, not from the local run directory."),
    }
    out = RUN / "o1_a4_recompute.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"commit": head, "cases": len(rows_out), "mismatches": len(mismatches),
                      "baseline_recomputed": baseline_di,
                      "baseline_claimed": result["regression"]["baseline_di_n"],
                      "target_recomputed": target, "endpoint": endpoint},
                     ensure_ascii=False, indent=2))
    print("written", out)
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
