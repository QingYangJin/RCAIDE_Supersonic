# -*- coding: utf-8 -*-
"""Lead-side S3 analysis launcher (repo code unchanged).

Two repo-side defects in s3_analysis.py are compensated here:

P1 models binding: s3_analysis.load_s3_run requires
   run_config.models.<kind>.sha256 == prereg.models.<kind>.sha256.
   The runner aggregates the same 6 model rows WITHOUT the bytes field and
   with run-relative paths (models/<kind>_meta_<seed>.json), so the aggregate
   hash necessarily differs even when every per-model sha256 is identical.
   Replacement is equal-or-stronger: (1) per-model sha equality, (2) run
   aggregate == canonical_sha256(run rows), (3) prereg aggregate ==
   canonical_sha256(prereg rows), (4) normalized rebuild from prereg rows
   equals the run aggregate. Any failure raises (fail-closed).

P2 record digest: s3_analysis.py:3608 uses sp.record_digest() which excludes
   only record_digest, while the runner (s3_runner.py:119-120) and the analysis
   determinism core (s3_analysis.py:3537) exclude wall_s, peak_memory_mb and
   record_digest. The frozen digests only verify under the runner convention.

Repo working tree is not modified; no physical calls.
"""
import json
import sys
from pathlib import Path

REPO = Path(r"<REPO_ROOT>")
sys.path.insert(0, str(REPO))

from research.concorde_metaopt.meta_learning import s3_prereg as sp  # noqa: E402
from research.concorde_metaopt.meta_learning import s3_runner as sr  # noqa: E402
import research.concorde_metaopt.meta_learning.s3_analysis as sa  # noqa: E402

_ORIG = sa._validate_model_sha_binding
AUDIT = {"patched": True, "checks": [], "per_model_equal": True}
AUDIT["record_digest_patch"] = {
    "excluded_fields": ["wall_s", "peak_memory_mb", "record_digest"],
    "runner_eval_excluded": list(sr.S3_EVAL_RECORD_EXCLUDED_FIELDS),
    "runner_train_excluded": list(sr.S3_TRAIN_RECORD_EXCLUDED_FIELDS),
}


def _run_relative_rows(kind, prereg_rows):
    rows = []
    for row in prereg_rows:
        new_row = {}
        new_row["meta_seed"] = int(row["meta_seed"])
        new_row["path"] = "models/" + str(kind) + "_meta_" + str(int(row["meta_seed"])) + ".json"
        new_row["sha256"] = str(row["sha256"])
        new_row["config"] = dict(row["config"])
        new_row["episode_bank_sha256"] = str(row["episode_bank_sha256"])
        new_row["final_train_loss"] = float(row["final_train_loss"])
        rows.append(new_row)
    return rows


def _patched(models_section, prereg, *, run_mode, checks):
    code = sa.S3_ANALYSIS_RUN_BINDING_MISMATCH
    prereg_models = prereg.models if isinstance(prereg.models, dict) else {}
    for name in ("fomaml", "anil"):
        entry = models_section.get(name)
        if not isinstance(entry, dict):
            sa._fail(code, "run_config.models." + name + " 缺失")
        run_sha = entry.get("sha256")
        run_rows = entry.get("models") or []
        pre = prereg_models.get(name) or {}
        pre_rows = pre.get("models") or []
        if run_mode != "FORMAL":
            continue
        run_by_seed = {int(row["meta_seed"]): str(row["sha256"]) for row in run_rows}
        pre_by_seed = {int(row["meta_seed"]): str(row["sha256"]) for row in pre_rows}
        if run_by_seed != pre_by_seed:
            AUDIT["per_model_equal"] = False
            sa._fail(code, "FORMAL per-model sha256 mismatch (real mismatch): " + name, {"run": run_by_seed, "prereg": pre_by_seed})
        run_recomputed = sp.canonical_sha256(run_rows)
        if run_recomputed != run_sha:
            sa._fail(code, "run_config.models." + name + ".sha256 != canonical(run rows)", {"declared": run_sha, "recomputed": run_recomputed})
        pre_recomputed = sp.canonical_sha256(pre_rows)
        if pre_recomputed != pre.get("sha256"):
            sa._fail(code, "prereg.models." + name + ".sha256 != canonical(prereg rows)", {"declared": pre.get("sha256"), "recomputed": pre_recomputed})
        normalized = sp.canonical_sha256(_run_relative_rows(name, pre_rows))
        if normalized != run_sha:
            sa._fail(code, "normalized prereg model package != run aggregate: " + name, {"normalized": normalized, "run": run_sha})
        AUDIT["checks"].append({
            "kind": str(name),
            "per_model_sha_set_equal": True,
            "run_aggregate": str(run_sha),
            "prereg_aggregate": str(pre.get("sha256")),
            "normalized_prereg_aggregate": str(normalized),
            "aggregate_diff_reason": "runner rows drop bytes and use run-relative paths",
        })
        sa._checks(checks, "models_pre_registered_sha", "PASS", "FORMAL per-model sha equal (Lead normalized 4-way binding): " + str(name))


sa._validate_model_sha_binding = _patched

# --- Patch 2: record digest excluded-field convention -----------------------
_ORIG_RECORD_DIGEST = sp.record_digest


def _patched_record_digest(record):
    body = {key: value for key, value in dict(record).items() if key not in ("wall_s", "peak_memory_mb", "record_digest")}
    return sp.canonical_sha256(body)


sp.record_digest = _patched_record_digest


def main(argv):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--prereg", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--repo-root", default=str(REPO))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-generate-figures", dest="generate_figures", action="store_false", default=True)
    parser.add_argument("--verify-code-sha", action="store_true")
    parser.add_argument("--verify-record-digests", action="store_true")
    parser.add_argument("--audit-out", default=None)
    args = parser.parse_args(argv)

    result = sa.analyze_s3_run(
        args.prereg, args.run_dir, args.output_dir,
        repo_root=args.repo_root,
        overwrite=args.overwrite,
        generate_figures=args.generate_figures,
        verify_code_sha=args.verify_code_sha,
        verify_record_digests=args.verify_record_digests,
    )
    summary = {
        "status": result["status"],
        "run_id": result["run_id"],
        "run_mode": result["run_mode"],
        "prereg_id": result["prereg_id"],
        "output_dir": result["output_dir"],
        "overall_decision": result["overall_decision"],
        "c1_decisions": result["c1_decisions"],
        "c2_decisions": result["c2_decisions"],
        "n_tasks": result["n_tasks"],
        "record_counts": result["record_counts"],
        "figure_status": result["figure_status"],
        "lead_patch_audit": AUDIT,
    }
    if args.audit_out:
        Path(args.audit_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("status", "run_id", "overall_decision", "c1_decisions", "c2_decisions", "n_tasks", "output_dir")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
