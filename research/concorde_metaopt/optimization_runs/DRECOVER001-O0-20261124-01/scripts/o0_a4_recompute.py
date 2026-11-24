"""A4 for O0: recompute every admitted Di from the raw polar bytes GitHub actually serves.

Same discipline as the O1 recompute: nothing checked here is read out of o0_result_B02.json. Each
case's .polar and admission_certificate.json are fetched from the remote blob API at one commit,
the polar table is parsed here, and Di is recomputed as q*Sref*CDi at the certified alpha.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/scripts")
import o1_upload as up  # noqa: E402

RUN = up.RUNS["O0"]
RUN_REL = up.RUN_REL_TMPL % RUN.name
COMMIT = sys.argv[1] if len(sys.argv) > 1 else None

# Which refine cases are the admitted ones, per batch. B02 holds the 11 optimiser designs; O0F
# holds the 8 verification attempts. The pairing here is a list of directory names, not values:
# every number is still recomputed from the bytes.
PLAN = {
    "B02": [("o0-d%02d-refine" % i) for i in range(11)],
    "O0F": ["o0-final-baseline-r1-final", "o0-final-baseline-r1b-final",
            "o0-final-baseline-r2-final", "o0-final-baseline-r2b-final",
            "o0-final-baseline-wake16-final", "o0-final-best-r1-final",
            "o0-final-best-r2-final", "o0-final-best-wake16-final"],
}


# These O0-FINAL directories exist on disk with a real paid polar but were never admitted, so
# they carry no admission certificate. Void rows had wake=2, below the fixed admission mesh of 8
# wake nodes; the wake16 probes are probe rows whose mesh can never match the admission mesh.
# Naming them here keeps "no certificate" from being silently read as "failed a check".
NOT_ADMITTED = {
    "o0-final-baseline-r1-final": "VOID_ROW wake=2 below the admission mesh of 8; charged but never admissible",
    "o0-final-baseline-r2-final": "VOID_ROW wake=2 below the admission mesh of 8; charged but never admissible",
    "o0-final-baseline-wake16-final": "WAKE_PROBE wake=16; the admission mesh is fixed at 8 so a probe row is never admitted",
    "o0-final-best-wake16-final": "WAKE_PROBE wake=16; the admission mesh is fixed at 8 so a probe row is never admitted",
}


def blob_text(sha: str, tok: str) -> str:
    d = up.api("/repos/%s/git/blobs/%s" % (up.OWNER_REPO, sha), tok)
    return base64.b64decode(d["content"]).decode("utf-8", "replace")


def parse_polar(text: str):
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

    result = json.loads((RUN / "o0_result_B02.json").read_text(encoding="utf-8"))
    q = result["attempts"][0]["q_pa"]
    rows_out, mismatches, not_admitted = [], [], []
    for batch, case_ids in PLAN.items():
        for case_id in case_ids:
            prefix = None
            marker = "/raw_cases/" + batch + "/"
            for key in tree:
                if key.endswith("/" + case_id + "/admission_certificate.json") and marker in key:
                    prefix = key[: -len(case_id + "/admission_certificate.json")]
                    break
            if prefix is None:
                if case_id in NOT_ADMITTED:
                    not_admitted.append({"batch": batch, "case_id": case_id,
                                         "reason": NOT_ADMITTED[case_id],
                                         "polar_present_on_github": any(
                                             k.endswith("/" + case_id + "/" + case_id + ".polar")
                                             and marker in k for k in tree)})
                else:
                    mismatches.append({"case_id": case_id, "batch": batch,
                                       "problem": "certificate not found in remote tree"})
                continue
            cert = json.loads(blob_text(tree[prefix + case_id + "/admission_certificate.json"], tok))
            polar_key = prefix + case_id + "/" + case_id + ".polar"
            if polar_key not in tree:
                mismatches.append({"case_id": case_id, "batch": batch,
                                   "problem": "polar not found in remote tree"})
                continue
            cols, prow = parse_polar(blob_text(tree[polar_key], tok))
            alpha = cert["alpha_deg"]
            hit = min(prow, key=lambda r: abs(r["AoA"] - alpha))
            di_recomputed = cert["q_pa"] * cert["sref_m2"] * hit["CDi"]
            delta = di_recomputed - cert["di_n"]
            ok = (abs(hit["AoA"] - alpha) < 1e-6
                  and abs(delta) <= 1e-6 * max(1.0, abs(cert["di_n"]))
                  and abs(hit["CLtot"] - cert["cl"]) < 1e-9
                  and abs(hit["CDi"] - cert["cdi"]) < 1e-9)
            rows_out.append({"batch": batch, "case_id": case_id,
                             "design_sha256": cert["design_sha256"],
                             "alpha_deg_certificate": alpha, "alpha_deg_polar_row": hit["AoA"],
                             "cl_polar": hit["CLtot"], "cl_certificate": cert["cl"],
                             "cdi_polar": hit["CDi"], "cdi_certificate": cert["cdi"],
                             "q_pa": cert["q_pa"], "sref_m2": cert["sref_m2"],
                             "di_n_recomputed": di_recomputed,
                             "di_n_certificate": cert["di_n"], "delta_n": delta,
                             "match": ok, "polar_rows_in_table": len(prow),
                             "polar_sha256_on_github": tree[polar_key]})
            if not ok:
                mismatches.append({"case_id": case_id, "batch": batch, "delta_n": delta,
                                   "alpha_gap": hit["AoA"] - alpha,
                                   "cl_gap": hit["CLtot"] - cert["cl"],
                                   "cdi_gap": hit["CDi"] - cert["cdi"]})
            print("  %-4s %-32s di=%.6f delta=%.3e ok=%s"
                  % (batch, case_id, di_recomputed, delta, ok), flush=True)

    b02 = [r for r in rows_out if r["batch"] == "B02"]
    o0f = [r for r in rows_out if r["batch"] == "O0F"]
    baseline = next(r for r in b02 if r["case_id"] == "o0-d00-refine")
    best = min(b02, key=lambda r: r["di_n_recomputed"])
    claimed = json.loads((RUN / "o0_batch_close_B02.json").read_text(encoding="utf-8"))
    endpoint = {
        "baseline_recomputed": baseline["di_n_recomputed"],
        "best_recomputed": best["di_n_recomputed"],
        "best_case": best["case_id"],
        "improvement_n": baseline["di_n_recomputed"] - best["di_n_recomputed"],
        "improvement_fraction": (baseline["di_n_recomputed"] - best["di_n_recomputed"])
        / baseline["di_n_recomputed"],
        "claimed_baseline_in_close_record": claimed["baseline"]["di_n"],
        "claimed_best_in_close_record": claimed["best_non_baseline"]["di_n"],
        "claimed_improvement_in_close_record": claimed["improvement_n"],
        "claimed_best_design_id": claimed["best_non_baseline"]["design_id"],
        "report_matches": (
            abs(baseline["di_n_recomputed"] - claimed["baseline"]["di_n"])
            <= 1e-9 * max(1.0, abs(claimed["baseline"]["di_n"]))
            and abs(best["di_n_recomputed"] - claimed["best_non_baseline"]["di_n"])
            <= 1e-9 * max(1.0, abs(claimed["best_non_baseline"]["di_n"]))
        ),
    }
    report = {
        "schema": "dreal005.o0_a4_recompute.v1",
        "method": ("raw .polar and admission_certificate.json downloaded from the GitHub blob API "
                   "at one commit; Di recomputed as q*Sref*CDi from the polar row at the "
                   "certified alpha; nothing read from o0_result_B02.json for the checked numbers"),
        "commit": head,
        "branch": up.BRANCH,
        "run_id": RUN.name,
        "case_count": len(rows_out),
        "not_admitted_count": len(not_admitted),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "not_admitted_no_certificate": not_admitted,
        "cases": rows_out,
        "endpoint": endpoint,
        "o0_final_repeats": {
            "baseline": sorted(r["di_n_recomputed"] for r in o0f
                               if "baseline-r" in r["case_id"] and "wake" not in r["case_id"]),
            "best": sorted(r["di_n_recomputed"] for r in o0f
                           if r["case_id"].startswith("o0-final-best-r")),
        },
        "checked_utc": up.now(),
        "note": ("Recomputation only: no solver was invoked. The q and Sref used are the ones "
                 "recorded in each certificate, so the check is that the polar row and the "
                 "certificate agree, not that the certificate chose the right q."),
    }
    out = RUN / "o0_a4_recompute.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"commit": head, "admitted_cases": len(rows_out),
                      "mismatches": len(mismatches),
                      "not_admitted_no_certificate": len(not_admitted),
                      "endpoint": endpoint, "o0_final_repeats": report["o0_final_repeats"]},
                     ensure_ascii=False, indent=2))
    print("written", out)
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())