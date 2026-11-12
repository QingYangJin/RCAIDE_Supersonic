#!/usr/bin/env python3
"""Lead signer for D-REAL-001 P2a-v2 R8 approval (lead-only).

approval.DRAFT.json -> approval.json after A5 G-P2AV2R8-PRE recommendations.
R8 = protocol D continuation (L-10): initial designs 15/16/17 reuse A1 P2AFAM
prefrozen pair bytes (zero rebuild) + 2 diagnostics evaluated as full pairs
(4 starts/28 internal preregistered) + 384 main; internal-count fix; no mesh-QC gate.
Fail-closed: verifies the A5 gate, the A2 package commit blobs, executor blob,
replay bundle manifest, window/token, caps, cumulative accounting, r9_addendum
(incl. prefrozen reuse / diagnostics / invalid policy), supersedes-R8 binding,
launcher binding and pre-execution emptiness BEFORE writing approval.json.
"""
import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone

EXPECTED = {
    "batch_id": "DREAL001-P2-20261111-14",
    "run_id": "DREAL001-P2A2R9-20261111-01",
    "window_start": "2026-11-11T17:30:00Z",
    "window_end": "2026-11-12T04:00:00Z",
    "token": "WINDOW_OK-P2AV2R9-20261111T1730Z-20261112T0400Z",
    "planned_starts": 390,
    "max_starts": 451,
    "planned_internal": 2730,
    "max_internal": 3157,
    "reserve_starts": 64,
    "cumulative_starts": 446,
    "cumulative_internal": 3134,
    "prior_starts": 39,
    "prior_internal": 285,
    "r1_starts": 2, "r1_internal": 14,
    "r2_starts": 2, "r2_internal": 14,
    "r3_starts": 2, "r3_internal": 14,
    "r4_starts": 2, "r4_internal": 14,
    "r5_starts": 0, "r5_internal": 0,
    "r6_starts": 3, "r6_internal": 21,
    "r7_starts": 6, "r7_internal": 42,
    "r8_starts": 0, "r8_internal": 0,
    "supersedes_sha": "fa0d94a2be7ea2dcb6828b85b0cc032885829a9c8fe904e993bb40535c981f46",
    "supersedes_bytes": 75166,
    "supersedes_physical": 56,
    "supersedes_run": "DREAL001-P2A2R8-20261111-01",
    "bundle_sha": "995bb12fff738d3ebb0bde08c0d5c5bfeb9532aebe536847ef307a2332013aa5",
    "bundle_commit_full": "2a57632b3f7d5d567556d9774913ec40a5d72272",
    "bare_sha256": "db71c4412489af82398833408ea30fb73327bdd9434de2ef530d31375b9fddad",
    "design_space_config_sha": "8b29d1e3833edc2af248d68cd6b7b4c94ebf775f25c86d80062a3850765a499e",
    "design_space_config_path": r"D:\RCAIDE\dnext001\wt-real-a1-geometry-solver\research\concorde_metaopt\configs\design_space_12d_lifting_surfaces.yaml",
    "a1_design_space_module_sha": "8f9b893c13195c80ff1ee88598134e3f44fef0495452249780d114c9e0593b89",
    "a1_executable_commit": "6753eb39b710035187db13ceb3328301c645c1ba",
    "prev_executor_sha": "ff3f5639211306276712302e561f2ff931d702396db625eeb96112e6807d3d20",
    "a2_executor_sha": None,  # resolved from A5 gate anchors; must differ from R8 sha
    "diag_design16": "eb00b7ad545243e6",
    "diag_design17": "dc96d2438a6dddc3",
    "diag_starts": 4,
    "diag_internal": 28,
}
ALLOWED_TOP = {"approved", "approved_by", "approved_at_utc", "status", "authorization",
               "window", "conditions", "approval_refs", "b2_waiver"}
ALLOWED_WINDOW = {"status"}
ALLOWED_B2 = {"status", "approved_at_utc", "a5_pre_review_commit"}
EXPECTED_FILES = {}
EXPECTED_FILE_NAMES = ("plan.json", "identity_binding.json",
                       "initial_designs_manifest.json", "P2A_V2_PREREGISTRATION.md")


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_blob(a2_repo, commit, relpath):
    try:
        return subprocess.run(["git", "-C", a2_repo, "show", "%s:%s" % (commit, relpath)],
                              check=True, capture_output=True).stdout
    except subprocess.CalledProcessError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--gate-json", required=True)
    ap.add_argument("--gate-commit", required=True)
    ap.add_argument("--conditions-file", default=None)
    ap.add_argument("--a2-repo", default=r"D:\RCAIDE\dnext001\wt-real-a2-optimizers")
    ap.add_argument("--launcher-path", default=None)
    ap.add_argument("--launcher-sha", default=None)
    ap.add_argument("--bootstrap-path", default=None)
    ap.add_argument("--bootstrap-sha", default=None)
    ap.add_argument("--evidence-out", default=None)
    args = ap.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    a2_repo = os.path.abspath(args.a2_repo)
    draft = json.load(open(args.draft, encoding="utf-8"))
    gate = json.load(open(args.gate_json, encoding="utf-8-sig"))
    gate_dump = json.dumps(gate, ensure_ascii=False)
    pkg_files_gate = gate.get("package_files") or {}
    for _name in EXPECTED_FILE_NAMES:
        _v = pkg_files_gate.get(_name)
        if isinstance(_v, dict) and _v.get("sha256"):
            EXPECTED_FILES[_name] = str(_v["sha256"])
        elif isinstance(_v, str) and len(_v) == 64:
            EXPECTED_FILES[_name] = _v
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": "" if ok else str(detail)})
        print(("OK   " if ok else "FAIL ") + name + ("" if ok else " :: " + str(detail)))
        return ok

    ok = True
    # ---- A5 gate ----
    ok &= check("gate_verdict_pass", str(gate.get("verdict", "")).startswith("PASS"), gate.get("verdict"))
    _gs = gate.get("solver_started")
    ok &= check("gate_zero_physical",
                gate.get("physical_call_count") == 0
                and (_gs is False or (_gs is None and "solver_started" not in gate)),
                [gate.get("physical_call_count"), _gs])
    sr = gate.get("signature_requirements") or {}
    srefs = dict(gate.get("refs_final") or gate.get("approval_refs_final")
                 or sr.get("approval_refs_final") or {})
    srefs["a5_review"] = args.gate_commit
    conds = gate.get("signature_conditions_recommended") or []
    if not conds:
        conds = [c.get("text") if isinstance(c, dict) else c
                 for c in (gate.get("conditions") or [])]
    if (not conds) and args.conditions_file and os.path.isfile(args.conditions_file):
        _cf = json.load(open(args.conditions_file, encoding="utf-8-sig"))
        _items = (_cf.get("conditions") if isinstance(_cf, dict) else _cf) or []
        conds = [c.get("text") if isinstance(c, dict) else c for c in _items]
    ok &= check("gate_conditions_full", isinstance(conds, list) and len(conds) >= 52
                and all(isinstance(c, str) and c.strip() for c in conds), len(conds))
    conds_text = "\n".join(c for c in conds if isinstance(c, str))
    anch_raw = gate.get("anchors") or {}
    _win = gate.get("window") or {}
    _a1 = anch_raw.get("a1") or {}

    def _sub(d, k):
        v = d.get(k)
        return v.get("sha256") if isinstance(v, dict) else v

    def _split(v):
        if isinstance(v, str) and "/" in v and len(v.split("/")[0]) == 64:
            return v.split("/")[0]
        return v

    anch = dict(anch_raw)
    anch.setdefault("batch_id", gate.get("batch_id"))
    anch.setdefault("run_id", gate.get("run_id"))
    anch.setdefault("window_start_utc", _win.get("start_utc") or _win.get("start"))
    anch.setdefault("window_end_utc", _win.get("end_utc") or _win.get("end"))
    anch.setdefault("window_token", _win.get("token"))
    anch.setdefault("a2_executor_sha256", _sub(anch_raw, "executor"))
    anch.setdefault("a2_package_commit", anch_raw.get("package_commit"))
    anch.setdefault("launcher_sha256", _sub(anch_raw, "launcher"))
    anch.setdefault("a1_bundle_manifest_sha256", _split(_a1.get("bundle")) or _a1.get("bundle_manifest_sha256"))
    anch.setdefault("a1_executable_commit", _a1.get("a1_task49_commit") or srefs.get("a1_executable_commit"))
    anch.setdefault("design_space_config_sha256", _split(_a1.get("config")))
    _exec = anch.get("a2_executor_sha256")
    if isinstance(_exec, str) and len(_exec) == 64 and all(c in "0123456789abcdef" for c in _exec.lower()):
        EXPECTED["a2_executor_sha"] = _exec.lower()
    ok &= check("gate_anchor_executor_present", EXPECTED["a2_executor_sha"] is not None, _exec)
    ok &= check("gate_anchor_executor_not_previous",
                EXPECTED["a2_executor_sha"] != EXPECTED["prev_executor_sha"],
                [EXPECTED["a2_executor_sha"], EXPECTED["prev_executor_sha"]])
    ok &= check("gate_refs_complete",
                all(isinstance(v, str) and v and "TO_BE_FILLED" not in v and "PENDING" not in v
                    or k == "a5_review" for k, v in srefs.items()), srefs)
    for need in ("a1_bundle_commit", "a1_bundle_commit_full", "a1_bundle_manifest_sha256",
                 "a2_package_commit", "a2_execution_code"):
        ok &= check("gate_refs_has_" + need, need in srefs, list(srefs))
    ok &= check("gate_refs_bundle_commit",
                str(srefs.get("a1_bundle_commit")) == EXPECTED["bundle_commit_full"]
                and str(srefs.get("a1_bundle_commit_full")) == EXPECTED["bundle_commit_full"],
                [srefs.get("a1_bundle_commit"), srefs.get("a1_bundle_commit_full")])
    ok &= check("gate_refs_bundle_sha",
                str(srefs.get("a1_bundle_manifest_sha256")) == EXPECTED["bundle_sha"],
                srefs.get("a1_bundle_manifest_sha256"))
    ok &= check("gate_refs_executor", str(srefs.get("a2_execution_code")) == EXPECTED["a2_executor_sha"],
                srefs.get("a2_execution_code"))
    for field, val in (("batch_id", EXPECTED["batch_id"]), ("run_id", EXPECTED["run_id"])):
        if field in gate:
            ok &= check("gate_" + field, gate.get(field) == val, [gate.get(field), val])
    for field, val in (("batch_id", EXPECTED["batch_id"]), ("run_id", EXPECTED["run_id"]),
                       ("window_start_utc", EXPECTED["window_start"]),
                       ("window_end_utc", EXPECTED["window_end"]),
                       ("window_token", EXPECTED["token"]),
                       ("a1_bundle_manifest_sha256", EXPECTED["bundle_sha"]),
                       ("a1_executable_commit", EXPECTED["a1_executable_commit"]),
                       ("a2_executor_sha256", EXPECTED["a2_executor_sha"])):
        ok &= check("gate_anchor_" + field, anch.get(field) == val, [anch.get(field), val])
    ok &= check("gate_anchor_pkg", anch.get("a2_package_commit") == srefs.get("a2_package_commit"),
                [anch.get("a2_package_commit"), srefs.get("a2_package_commit")])
    pkg_commit = str(srefs.get("a2_package_commit") or "")
    ok &= check("gate_pkg_commit_format", len(pkg_commit) == 40
                and all(c in "0123456789abcdef" for c in pkg_commit), pkg_commit)

    # ---- launcher / bootstrap binding ----
    def _resolve(p):
        if not p:
            return p
        if os.path.isfile(p):
            return p
        cand = os.path.join(a2_repo, p)
        return cand if os.path.isfile(cand) else p

    for kind, path, sha in (("launcher", _resolve(args.launcher_path), args.launcher_sha),
                            ("bootstrap", _resolve(args.bootstrap_path), args.bootstrap_sha)):
        if path or sha:
            ok &= check(kind + "_sha_format", bool(sha) and len(sha) == 64, sha)
            ok &= check(kind + "_exists", bool(path) and os.path.isfile(path), path)
            if path and os.path.isfile(path):
                actual = sha256_file(path)
                ok &= check(kind + "_sha_match", actual == sha, [actual, sha])
            ok &= check(kind + "_in_gate", bool(sha) and sha in gate_dump, sha)
    ok &= check("launcher_given", bool(args.launcher_sha) and bool(args.launcher_path),
                [args.launcher_sha, args.launcher_path])

    # ---- draft identity / window / caps / cumulative ----
    ok &= check("draft_batch", draft.get("batch_id") == EXPECTED["batch_id"], draft.get("batch_id"))
    ok &= check("draft_run", draft.get("run_id") == EXPECTED["run_id"], draft.get("run_id"))
    win = draft.get("window") or {}
    ok &= check("draft_window_start", win.get("start_utc") == EXPECTED["window_start"], win.get("start_utc"))
    ok &= check("draft_window_end", win.get("end_utc") == EXPECTED["window_end"], win.get("end_utc"))
    ok &= check("draft_window_token", win.get("token") == EXPECTED["token"] and draft.get("token") == EXPECTED["token"],
                [draft.get("token"), win.get("token")])
    ok &= check("draft_planned_starts", draft.get("planned_starts") == EXPECTED["planned_starts"], draft.get("planned_starts"))
    ok &= check("draft_max_starts", draft.get("max_starts") == EXPECTED["max_starts"], draft.get("max_starts"))
    ok &= check("draft_planned_internal", draft.get("planned_internal_cases") == EXPECTED["planned_internal"],
                draft.get("planned_internal_cases"))
    ok &= check("draft_max_internal", draft.get("max_internal_cases") == EXPECTED["max_internal"],
                draft.get("max_internal_cases"))
    ok &= check("draft_reserve", draft.get("reserve_starts") == EXPECTED["reserve_starts"], draft.get("reserve_starts"))
    ok &= check("draft_executor_sha", draft.get("a2_executor_sha256") == EXPECTED["a2_executor_sha"],
                draft.get("a2_executor_sha256"))
    _drefs = draft.get("approval_refs") or {}
    ok &= check("draft_refs_executor", str(_drefs.get("a2_execution_code")) == EXPECTED["a2_executor_sha"],
                _drefs.get("a2_execution_code"))

    add = draft.get("r9_addendum") or {}
    add_dump = json.dumps(add, ensure_ascii=False)
    cu = add.get("cumulative_accounting") or {}
    ok &= check("add_status", add.get("status") == "R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX", add.get("status"))
    ok &= check("cum_starts", cu.get("cumulative_starts") == EXPECTED["cumulative_starts"], cu.get("cumulative_starts"))
    ok &= check("cum_internal", cu.get("cumulative_internal_cases") == EXPECTED["cumulative_internal"],
                cu.get("cumulative_internal_cases"))
    _cap = (cu.get("cumulative_starts_cap", cu.get("max_starts")),
            cu.get("cumulative_internal_cap", cu.get("max_internal_cases")))
    ok &= check("cum_caps", _cap == (EXPECTED["max_starts"], EXPECTED["max_internal"]), list(_cap))
    _prior = cu.get("prior_charged_starts")
    ok &= check("cum_prior", _prior in (EXPECTED["prior_starts"], 47, 39), _prior)
    for i in (1, 2, 3, 4):
        _ri = cu.get("r%d_charged_internal_cases" % i, cu.get("r%d_internal_cases" % i))
        ok &= check("cum_r%d_charged" % i,
                    (cu.get("r%d_charged_starts" % i), _ri)
                    == (EXPECTED["r%d_starts" % i], EXPECTED["r%d_internal" % i]),
                    [cu.get("r%d_charged_starts" % i), _ri])
    _r5 = cu.get("r5_charged_starts", cu.get("r5_setup_charged_starts", None))
    _r5i = cu.get("r5_charged_internal_cases", cu.get("r5_setup_charged_internal_cases", None))
    ok &= check("cum_r5_charged", (_r5 in (None, 0)) and (_r5i in (None, 0)), [_r5, _r5i])
    _r6 = cu.get("r6_charged_starts", cu.get("r6_s1_charged_starts", None))
    _r6i = cu.get("r6_charged_internal_cases", cu.get("r6_s1_charged_internal_cases", None))
    ok &= check("cum_r6_charged", (_r6, _r6i) == (EXPECTED["r6_starts"], EXPECTED["r6_internal"]), [_r6, _r6i])
    _r7c = cu.get("r7_charged_starts", cu.get("r7_s1_charged_starts", None))
    _r7ci = cu.get("r7_charged_internal_cases", cu.get("r7_s1_charged_internal_cases", None))
    ok &= check("cum_r7_charged", (_r7c, _r7ci) == (EXPECTED["r7_starts"], EXPECTED["r7_internal"]), [_r7c, _r7ci])
    _r8c = cu.get("r8_charged_starts", cu.get("r8_setup_charged_starts", None))
    _r8ci = cu.get("r8_charged_internal_cases", cu.get("r8_setup_charged_internal_cases", None))
    ok &= check("cum_r8_charged", (_r8c in (None, 0)) and (_r8ci in (None, 0)), [_r8c, _r8ci])
    _r9p = cu.get("r9_planned_starts", cu.get("planned_starts"))
    _r9pi = cu.get("r9_planned_internal_cases", cu.get("planned_internal_cases"))
    ok &= check("cum_r9_planned", (_r9p, _r9pi) == (EXPECTED["planned_starts"], EXPECTED["planned_internal"]),
                [_r9p, _r9pi])
    _sum = (int(_prior or 0) + 2 + 2 + 2 + 2 + int(_r5 or 0) + int(_r6 or 0)
            + int(_r7c or 0) + int(_r8c or 0) + int(_r9p or 0))
    ok &= check("cum_components_sum", _sum == EXPECTED["cumulative_starts"], _sum)
    _isum = (int(cu.get("prior_charged_internal_cases") or 0) + 14 * 4 + int(cu.get("r5_charged_internal_cases") or 0)
             + int(_r6i or 0) + int(_r7ci or 0) + int(_r8ci or 0) + int(_r9pi or 0))
    ok &= check("cum_internal_components_sum", _isum == EXPECTED["cumulative_internal"], _isum)
    r8ref = add.get("r8_reference") or {}
    ok &= check("r8ref_sha", r8ref.get("superseded_approval_sha256") == EXPECTED["supersedes_sha"],
                r8ref.get("superseded_approval_sha256"))
    ok &= check("r8ref_excluded", r8ref.get("excluded_from_endpoints") is True, r8ref.get("excluded_from_endpoints"))
    ok &= check("r8ref_preserved", r8ref.get("artifacts_preserved") is True, r8ref.get("artifacts_preserved"))
    ok &= check("r8ref_status", "SETUP_STOP" in str(r8ref.get("status")), r8ref.get("status"))
    r5ref = add.get("r5_reference") or {}
    ok &= check("r5ref_excluded", r5ref.get("excluded_from_endpoints") is True, r5ref.get("excluded_from_endpoints"))
    # diagnostics + invalid-numerical policy + no mesh QC gate
    diag = (add.get("diagnostic_phase") or draft.get("diagnostics")
            or add.get("diagnostics") or {})
    diag_dump = json.dumps(diag, ensure_ascii=False) if diag else add_dump
    ok &= check("diag_present", bool(diag), list(add.keys()))
    ok &= check("diag_design16", EXPECTED["diag_design16"] in diag_dump or EXPECTED["diag_design16"] in add_dump,
                "design16 hash")
    ok &= check("diag_design17", EXPECTED["diag_design17"] in diag_dump or EXPECTED["diag_design17"] in add_dump,
                "design17 hash")
    _dstart = diag.get("planned_starts", diag.get("starts", diag.get("diagnostic_starts")))
    _dint = diag.get("planned_internal_cases", diag.get("diagnostic_internal_cases"))
    ok &= check("diag_counts", (_dstart, _dint) == (EXPECTED["diag_starts"], EXPECTED["diag_internal"]),
                [_dstart, _dint])
    ok &= check("diag_draft_top_counts",
                (draft.get("diagnostic_planned_starts"), draft.get("diagnostic_planned_internal_cases"))
                == (EXPECTED["diag_starts"], EXPECTED["diag_internal"]),
                [draft.get("diagnostic_planned_starts"), draft.get("diagnostic_planned_internal_cases")])
    _policy_txt = (add_dump + "\n" + json.dumps(draft, ensure_ascii=False) + "\n" + conds_text).lower()
    ok &= check("invalid_policy_present",
                ("invalid_numerical" in _policy_txt or "invalid-numerical" in _policy_txt
                 or "invalid numerical" in _policy_txt),
                "invalid-numerical tolerance policy recorded in draft/addendum/A5 conditions")
    ok &= check("no_mesh_qc_gate", add.get("mesh_qc_gate") not in (True, "ENABLED", "enabled")
                and not (isinstance(add.get("mesh_qc"), dict) and add.get("mesh_qc", {}).get("enabled") is True)
                and ("no mesh qc data gate" in _policy_txt or "mesh-qc data gate not adopted" in _policy_txt),
                "mesh_qc_gate must not be enabled; no-mesh-QC-gate policy recorded in addendum or A5 conditions")
    ok &= check("r9_change_mentions_prefrozen", "PREFROZEN" in add_dump.upper(), "prefrozen reuse mentioned")
    ok &= check("r9_change_mentions_reused_flag", "reused_prefrozen" in add_dump, "reused_prefrozen flag mentioned")
    ok &= check("r9_change_mentions_diag_pair", ("4" in add_dump and "28" in add_dump)
                or "pair" in add_dump.lower(), "diagnostic 4/28 pair prereg mentioned")
    ok &= check("r8_prefrozen_manifest_bound", "55e63f39" in add_dump or "family_pair_manifest" in add_dump,
                "static manifest binding mentioned")
    ok &= check("r9_flat_row_fix_marker", ("flat" in add_dump.lower() and "nested" in add_dump.lower()),
                "flat/nested family-row compatibility fix mentioned")
    ok &= check("r9_executor_gate_smoke_marker",
                ("executor" in add_dump.lower() and ("gate" in add_dump.lower() or "smoke" in add_dump.lower())),
                "executor-side gate smoke evidence mentioned")
    sup = draft.get("supersedes") or {}
    _ssha = sup.get("sha256", sup.get("approval_sha256"))
    _sbytes = sup.get("bytes", sup.get("approval_bytes"))
    ok &= check("supersedes_sha", _ssha == EXPECTED["supersedes_sha"], _ssha)
    ok &= check("supersedes_bytes", _sbytes == EXPECTED["supersedes_bytes"], _sbytes)
    ok &= check("supersedes_physical", sup.get("physical_call_count_at_supersede") == EXPECTED["supersedes_physical"],
                sup.get("physical_call_count_at_supersede"))
    ok &= check("supersedes_run", sup.get("run_id") == EXPECTED["supersedes_run"], sup.get("run_id"))
    seq9 = [e for e in (draft.get("amendment_log") or []) if str(e.get("seq")) == "9"]
    ok &= check("amendment_seq9", len(seq9) == 1, draft.get("amendment_log"))
    if seq9:
        ok &= check("amendment_seq9_action", seq9[0].get("action") == "R9_PREFROZEN_MANIFEST_FLAT_ROW_FIX",
                    seq9[0].get("action"))
        ok &= check("amendment_seq9_physical_56", seq9[0].get("physical_call_count_at_amendment") == 56,
                    seq9[0].get("physical_call_count_at_amendment"))
    prior_approval_path = str((draft.get("supersedes") or {}).get("approval_path") or "")
    ok &= check("prior_approval_exists", os.path.isfile(prior_approval_path), prior_approval_path)
    if os.path.isfile(prior_approval_path):
        ok &= check("prior_approval_sha", sha256_file(prior_approval_path) == EXPECTED["supersedes_sha"],
                    sha256_file(prior_approval_path))
        ok &= check("prior_approval_bytes", os.path.getsize(prior_approval_path) == EXPECTED["supersedes_bytes"],
                    os.path.getsize(prior_approval_path))
        prior = json.load(open(prior_approval_path, encoding="utf-8"))
        prior_log = prior.get("amendment_log") or []
        draft_log = draft.get("amendment_log") or []
        ok &= check("amendment_history_prefix", draft_log[:len(prior_log)] == prior_log,
                    "draft amendment history must equal signed R8 history")
    sums = os.path.join(run_dir, "SHA256SUMS.txt")
    ok &= check("sums_exists", os.path.isfile(sums), sums)
    if os.path.isfile(sums):
        n_sum = 0
        for line in open(sums, encoding="utf-8"):
            parts = line.split()
            if len(parts) < 2:
                continue
            n_sum += 1
            fn = parts[-1].lstrip("*")
            fp = os.path.join(run_dir, fn)
            ok &= check("sums:" + fn, os.path.isfile(fp) and sha256_file(fp) == parts[0],
                        "listed=" + parts[0] + " actual=" + (sha256_file(fp) if os.path.isfile(fp) else "MISSING"))
        ok &= check("sums_lines_7", n_sum == 7, n_sum)

    ok &= check("draft_not_approved", draft.get("approved") is False
                and draft.get("status") == "DRAFT_AWAITING_LEAD_SIGNATURE",
                [draft.get("approved"), draft.get("status")])
    ok &= check("draft_zero_physical", (draft.get("physical_call_count"), draft.get("physical_solver_starts"),
                                        draft.get("solver_started")) == (0, 0, False),
                [draft.get("physical_call_count"), draft.get("physical_solver_starts"), draft.get("solver_started")])
    ok &= check("draft_conditions_15", len(draft.get("conditions") or []) == 15, len(draft.get("conditions") or []))
    _allowed = {"plan.json", "approval.DRAFT.json", "identity_binding.json",
                "initial_designs_manifest.json", "P2A_V2_PREREGISTRATION.md",
                "dry_run.json", "executor_dry_run.json", "SHA256SUMS.txt"}
    _actual = set(os.listdir(run_dir))
    ok &= check("run_dir_exactly_package_files", _actual == _allowed,
                "extra=" + repr(sorted(_actual - _allowed)) + " missing=" + repr(sorted(_allowed - _actual)))
    for bad in ("solver_attempts.jsonl", "cases", "evaluations", "batch_summary.json",
                "stop_report.json", "approval.json"):
        ok &= check("pre_exec_absent:" + bad, not os.path.exists(os.path.join(run_dir, bad)),
                    os.path.join(run_dir, bad))

    # ---- package files vs draft SHA + committed blobs ----
    rel_dir = os.path.relpath(run_dir, a2_repo).replace("\\", "/")
    pkg_files = {
        "plan.json": draft.get("plan_sha256"),
        "P2A_V2_PREREGISTRATION.md": draft.get("prereg_sha256"),
        "identity_binding.json": draft.get("identity_binding_file_sha256"),
        "initial_designs_manifest.json": draft.get("initial_designs_manifest_sha256"),
    }
    for fname, expect in pkg_files.items():
        p = os.path.join(run_dir, fname)
        ok &= check("file_exists:" + fname, os.path.isfile(p), p)
        if os.path.isfile(p):
            actual = sha256_file(p)
            ok &= check("file_sha:" + fname, actual == expect, "expected=" + str(expect) + " actual=" + actual)
            if pkg_commit:
                blob = git_blob(a2_repo, pkg_commit, rel_dir + "/" + fname)
                ok &= check("pkg_commit_blob:" + fname, blob is not None and blob == open(p, "rb").read(),
                            "commit=" + pkg_commit)
    ok &= check("dry_run_present", os.path.isfile(os.path.join(run_dir, "dry_run.json")))
    ok &= check("executor_dry_run_present", os.path.isfile(os.path.join(run_dir, "executor_dry_run.json")))
    ok &= check("SHA256SUMS_present", os.path.isfile(os.path.join(run_dir, "SHA256SUMS.txt")))

    # ---- A2 executor blob ----
    executor_sha = None
    for ent in draft.get("executor_blob", {}).get("a2", []):
        p = ent["path"]; name = os.path.basename(p)
        ok &= check("executor_exists:" + name, os.path.isfile(p), p)
        if os.path.isfile(p):
            actual = sha256_file(p)
            ok &= check("executor_sha:" + name, actual == ent["sha256"],
                        "expected=" + str(ent["sha256"]) + " actual=" + actual)
            if name == "p2a_v2_executor.py":
                executor_sha = actual
    ok &= check("a2_executor_sha_matches", executor_sha == draft.get("a2_executor_sha256"),
                [executor_sha, draft.get("a2_executor_sha256")])
    ok &= check("a2_executor_sha_gate", executor_sha == srefs.get("a2_execution_code"),
                [executor_sha, srefs.get("a2_execution_code")])
    ok &= check("a2_executor_sha_expected", executor_sha == EXPECTED["a2_executor_sha"],
                [executor_sha, EXPECTED["a2_executor_sha"]])

    # ---- A1 replay bundle manifest ----
    rb = draft.get("replay_bundles") or {}
    rbp = rb.get("bundle_manifest_path", "")
    ok &= check("replay_bundle_exists", os.path.isfile(rbp), rbp)
    if os.path.isfile(rbp):
        actual = sha256_file(rbp)
        ok &= check("replay_bundle_sha", actual == rb.get("bundle_manifest_sha256"),
                    [rb.get("bundle_manifest_sha256"), actual])
        ok &= check("replay_bundle_expected", rb.get("bundle_manifest_sha256") == EXPECTED["bundle_sha"],
                    rb.get("bundle_manifest_sha256"))
    ok &= check("replay_bundle_cases_2", sorted((rb.get("cases") or {}).keys()) == ["PRE-01", "PRE-02"],
                sorted((rb.get("cases") or {}).keys()))

    # ---- solver exe binding ----
    solver = draft.get("solver") or {}
    ok &= check("solver_exe_sha", str(solver.get("exe_sha256", "")).lower() == EXPECTED["bare_sha256"],
                solver.get("exe_sha256"))
    ok &= check("solver_fuel_null", solver.get("fuel_burn_kg") is None, solver.get("fuel_burn_kg"))
    ok &= check("solver_phys_not_validated", solver.get("physical_validation_status") == "NOT_VALIDATED",
                solver.get("physical_validation_status"))

    # ---- design-space binding ----
    ds_path = EXPECTED["design_space_config_path"]
    ok &= check("design_space_config_exists", os.path.isfile(ds_path), ds_path)
    if os.path.isfile(ds_path):
        _dsha = sha256_file(ds_path)
        ok &= check("design_space_config_sha", _dsha == EXPECTED["design_space_config_sha"],
                    [_dsha, EXPECTED["design_space_config_sha"]])
    ok &= check("gate_anchor_design_space",
                (anch.get("design_space_config_sha256") in (None, EXPECTED["design_space_config_sha"])),
                anch.get("design_space_config_sha256"))

    if not ok:
        print("SIGN_ABORTED: preconditions failed; approval.json NOT written")
        return 1

    # ---- build signed approval ----
    now = utcnow()
    appr = json.loads(json.dumps(draft))
    sd = sr.get("scalar_deltas") or sr.get("allowed_scalar_deltas") or {}
    appr["approved"] = True
    appr["approved_by"] = "lead"
    appr["approved_at_utc"] = now
    appr["status"] = "APPROVED_FOR_EXECUTION_PENDING_POST_APPROVAL_DRY_RUN"
    auth = (sd.get("authorization") if isinstance(sd, dict) else None) or {}
    auth = auth if isinstance(auth, dict) else {}
    scope = auth.get("scope") if isinstance(auth.get("scope"), str) else ""
    if not scope or "PENDING" in scope:
        scope = ("batch_id %s / run_id %s only; 2 replay preflight + 4 preregistered diagnostic starts "
                 "(designs 16/17, full pair) + 384 main under protocol D (L-09/L-10, prefrozen reuse); "
                 "requires post-approval dry-run and Lead GO before first solver start"
                 % (EXPECTED["batch_id"], EXPECTED["run_id"]))
    ok &= check("authorization_scope_r7",
                EXPECTED["batch_id"] in scope and EXPECTED["run_id"] in scope, scope)
    appr["authorization"] = {
        "mode": "LEAD_SINGLE_BATCH_APPROVAL",
        "scope": scope,
        "signed_at_utc": now,
        "signed_by": "lead",
    }
    appr["window"]["status"] = "APPROVED"
    appr["conditions"] = list(conds)
    appr["approval_refs"] = srefs
    bw = appr.setdefault("b2_waiver", {})
    bw["status"] = "APPROVED_BY_LEAD_FOR_THIS_BATCH_ONLY"
    bw["approved_at_utc"] = now
    bw["a5_pre_review_commit"] = args.gate_commit

    def diff(a, b):
        return {k for k in set(a) | set(b) if a.get(k) != b.get(k)}

    dtop = diff(draft, appr)
    ok &= check("delta_top_allowed", dtop <= ALLOWED_TOP, sorted(dtop - ALLOWED_TOP))
    dwin = diff(draft.get("window") or {}, appr.get("window") or {})
    ok &= check("delta_window_allowed", dwin <= ALLOWED_WINDOW, sorted(dwin - ALLOWED_WINDOW))
    db2 = diff(draft.get("b2_waiver") or {}, appr.get("b2_waiver") or {})
    ok &= check("delta_b2_allowed", db2 <= ALLOWED_B2, sorted(db2 - ALLOWED_B2))
    inv_names = sr.get("signed_approval_invariants_unchanged")
    if isinstance(inv_names, list) and inv_names and all(isinstance(x, str) for x in inv_names):
        bad_inv = [n for n in inv_names if n in draft or n in appr]
        bad_inv = [n for n in bad_inv if draft.get(n) != appr.get(n)]
        ok &= check("a5_invariants_unchanged", not bad_inv, bad_inv)
    else:
        inv_stmt = sr.get("invariants_unchanged") or []
        ok &= check("a5_invariants_statements_present",
                    isinstance(inv_stmt, list) and len(inv_stmt) >= 8
                    and all(isinstance(s, str) and s.strip() for s in inv_stmt),
                    len(inv_stmt) if isinstance(inv_stmt, list) else inv_stmt)
    for fname, exp in EXPECTED_FILES.items():
        p = os.path.join(run_dir, fname)
        ok &= check("inv_file:" + fname, os.path.isfile(p) and sha256_file(p) == exp,
                    "expected=" + exp + " actual=" + (sha256_file(p) if os.path.isfile(p) else "MISSING"))
    if not ok:
        print("SIGN_ABORTED: delta/invariant checks failed; approval.json NOT written")
        return 1

    out = os.path.join(run_dir, "approval.json")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(appr, ensure_ascii=False, indent=2) + "\n")
    appr_sha = sha256_file(out)
    appr_bytes = os.path.getsize(out)

    rt = json.load(open(out, encoding="utf-8"))
    valid = True
    valid &= check("post_approved", rt.get("approved") is True)
    valid &= check("post_status", rt.get("status") == "APPROVED_FOR_EXECUTION_PENDING_POST_APPROVAL_DRY_RUN",
                   rt.get("status"))
    valid &= check("post_window_status", (rt.get("window") or {}).get("status") == "APPROVED",
                   (rt.get("window") or {}).get("status"))
    valid &= check("post_token", rt.get("token") == (rt.get("window") or {}).get("token") == EXPECTED["token"],
                   rt.get("token"))
    valid &= check("post_batch_run", (rt.get("batch_id"), rt.get("run_id"))
                   == (EXPECTED["batch_id"], EXPECTED["run_id"]), [rt.get("batch_id"), rt.get("run_id")])
    valid &= check("post_conditions_count", len(rt.get("conditions") or []) == len(conds), len(rt.get("conditions") or []))
    valid &= check("post_refs_a5", (rt.get("approval_refs") or {}).get("a5_review") == args.gate_commit,
                   (rt.get("approval_refs") or {}).get("a5_review"))
    valid &= check("post_refs_bundle",
                   (rt.get("approval_refs") or {}).get("a1_bundle_manifest_sha256") == EXPECTED["bundle_sha"],
                   (rt.get("approval_refs") or {}).get("a1_bundle_manifest_sha256"))
    valid &= check("post_refs_bundle_commit",
                   (rt.get("approval_refs") or {}).get("a1_bundle_commit") == EXPECTED["bundle_commit_full"]
                   and (rt.get("approval_refs") or {}).get("a1_bundle_commit_full") == EXPECTED["bundle_commit_full"],
                   [(rt.get("approval_refs") or {}).get("a1_bundle_commit"),
                    (rt.get("approval_refs") or {}).get("a1_bundle_commit_full")])
    valid &= check("post_refs_pkg", (rt.get("approval_refs") or {}).get("a2_package_commit") == pkg_commit,
                   (rt.get("approval_refs") or {}).get("a2_package_commit"))
    valid &= check("post_refs_executor", (rt.get("approval_refs") or {}).get("a2_execution_code") == EXPECTED["a2_executor_sha"],
                   (rt.get("approval_refs") or {}).get("a2_execution_code"))
    valid &= check("post_b2_waiver", (rt.get("b2_waiver") or {}).get("a5_pre_review_commit") == args.gate_commit,
                   (rt.get("b2_waiver") or {}).get("a5_pre_review_commit"))
    print("POST_WRITE_VALIDATION:", "PASS" if valid else "FAIL")
    print("APPROVAL_PATH:", out)
    print("APPROVAL_SHA256:", appr_sha)
    print("APPROVAL_BYTES:", appr_bytes)
    print("CONDITIONS:", len(rt.get("conditions") or []))

    ev = {
        "schema": "dreal001.lead_signature_receipt.v1",
        "batch_id": draft.get("batch_id"), "run_id": draft.get("run_id"),
        "signed_by": "lead", "signed_at_utc": now,
        "approval_path": out, "approval_sha256": appr_sha, "approval_bytes": appr_bytes,
        "draft_path": os.path.abspath(args.draft), "draft_sha256": sha256_file(args.draft),
        "a5_gate_id": gate.get("gate_id"), "a5_gate_path": os.path.abspath(args.gate_json),
        "a5_gate_sha256": sha256_file(args.gate_json), "a5_gate_commit": args.gate_commit,
        "a2_package_commit": pkg_commit,
        "a2_executor_sha256": EXPECTED["a2_executor_sha"],
        "launcher_path": args.launcher_path, "launcher_sha256": args.launcher_sha,
        "bootstrap_path": args.bootstrap_path, "bootstrap_sha256": args.bootstrap_sha,
        "conditions_count": len(rt.get("conditions") or []),
        "approval_refs": rt.get("approval_refs"),
        "physical_call_count_at_sign": 0,
        "checks": checks,
    }
    ev_path = args.evidence_out or os.path.join(
        r"D:\RCAIDE\dnext001\wt-real-lead\docs\evidence\dreal001",
        "lead_signature_r9_" + now.replace(":", "").replace("-", "") + ".json")
    os.makedirs(os.path.dirname(os.path.abspath(ev_path)), exist_ok=True)
    with open(ev_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(ev, ensure_ascii=False, indent=2) + "\n")
    print("EVIDENCE_PATH:", os.path.abspath(ev_path))
    print("EVIDENCE_SHA256:", sha256_file(ev_path))
    print("SIGN_OK" if valid else "SIGN_POST_VALIDATION_FAILED")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
