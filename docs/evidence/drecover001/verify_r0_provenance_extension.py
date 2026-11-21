
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXT = ROOT / "r0_provenance_extension.json"
AUD = ROOT / "reachable_history_audit.json"
SCRIPT = ROOT / "audit_provenance_extension.py"
OUT = ROOT / "r0_provenance_extension_verification.json"

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def local_file_sha(rel):
    path = ROOT.parents[2] / rel
    if not path.is_file():
        return None
    return sha256_bytes(path.read_bytes())

def main():
    checks = []
    def check(name, ok, detail=""):
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    ext_bytes = EXT.read_bytes()
    ext = json.loads(ext_bytes.decode("utf-8"))
    aud = json.loads(AUD.read_text(encoding="utf-8"))
    script_sha = sha256_bytes(SCRIPT.read_bytes())
    out_sha = sha256_bytes(ext_bytes)

    check("schema", ext.get("schema") == "drecover001.r0_provenance_extension.v1", str(ext.get("schema")))
    check("scope", str(ext.get("scope", "")).startswith("Reachable remote history only"), str(ext.get("scope"))[:80])
    zero = [ext.get("physical_solver_starts_actual"), ext.get("internal_solver_cases_actual")]
    check("zero_physical_accounting", zero == [0, 0] and ext.get("physics_validated") is False
          and ext.get("cache_admission") == "NONE" and ext.get("admitted_scientific_labels") == 0
          and ext.get("independent_review") == "NOT_STARTED", json.dumps(zero))
    check("audit_provenance_verified", aud.get("raw_git_object_identity_verified") is True
          and aud.get("reachable_commit_count") == 200 and aud.get("unique_blob_count") == 2829,
          f"{aud.get('reachable_commit_count')} commits / {aud.get('unique_blob_count')} blobs")
    check("recorded_evidence_sha256", out_sha == "b553857c5ce986e9fbfd7f6fa6de37d7aca42af9ade61075db6e17e87c524c37", out_sha)
    check("recorded_script_sha256", script_sha == "63eb6e468ce40de035b15737b5f69d63d07f0acae369c2b76b4b1e41c0e7bb6e", script_sha)

    blobs = aud["blobs"]
    sources = [("budget_sources", "BUDGET_LEDGER_DATA"), ("solver_raw_outputs", "SOLVER_RAW_OUTPUT"),
               ("solver_run_logs", "SOLVER_RUN_LOG"), ("solver_input_decks", "SOLVER_INPUT_DECK")]
    versions_ok = True; version_detail = []
    raw_present = []
    for key, kind in sources:
        entries = ext[key]
        check(f"{key}_count", len(entries) > 0 and all(e["kind"] == kind for e in entries), f"{len(entries)} entries")
        for e in entries:
            for v in e["versions"]:
                blob = blobs.get(v["git_oid"])
                ok = bool(blob) and blob.get("sha256") == v["sha256"] and blob.get("bytes") == v["bytes"]
                if not ok:
                    versions_ok = False; version_detail.append(e["repository_path"])
            if e["classification"] == "RAW_PRESENT":
                raw_present.append(e["repository_path"])
                got = local_file_sha(e["repository_path"])
                check("raw_present_local_bytes:" + e["repository_path"],
                      got is not None and got == e["worktree"]["sha256"] and e["worktree"]["match"] == "EXACT_BYTES",
                      str(got))
            else:
                check("non_raw_present_not_byte_identical:" + e["repository_path"],
                      e.get("local_byte_identical") is False, e["classification"])
    check("all_versions_exist_in_reachable_audit", versions_ok, "; ".join(version_detail[:3]))

    budget = ext["budget_sources"]
    from collections import Counter
    bc = Counter(e["classification"] for e in budget)
    check("budget_classification_summary", dict(bc) == {"REMOTE_PRESENT": 22, "RAW_PRESENT": 3}, str(dict(bc)))
    for key, expected in (("solver_raw_outputs", 58), ("solver_run_logs", 62), ("solver_input_decks", 157)):
        entries = ext[key]
        check(f"{key}_all_remote_present", len(entries) == expected
              and all(e["classification"] == "REMOTE_PRESENT" for e in entries), f"{len(entries)} entries")
    check("raw_present_are_ledgers_only", all("optimization_runs" not in p for p in raw_present), str(raw_present))

    absent = ext["absent_claims"]
    check("absent_claims_raw_lost", len(absent) == 2
          and {a["token"] for a in absent} == {"F1R2", "F2R2"}
          and all(a["classification"] == "RAW_LOST" and a["history_path_matches"] == [] for a in absent),
          str([a["token"] for a in absent]))

    pairs = ext["ledger_budget_cross_check"]
    auth = [p for p in pairs if p["authoritative"]]
    heur = [p for p in pairs if not p["authoritative"]]
    check("cross_check_pairs", len(pairs) == 4 and len(auth) == 2, f"{len(pairs)} pairs")
    check("authoritative_flags_zero", all(not p["flags"] for p in auth), str([p["flags"] for p in auth]))
    flagged_heur = [p for p in heur if p["flags"]]
    check("heuristic_single_disagreement", len(flagged_heur) == 1 and len(flagged_heur[0]["flags"]) == 3
          and "d12d004" in flagged_heur[0]["ledger_path"], str([p["flags"] for p in heur]))

    groups = ext["claim_groups"]
    total_claims = sum(g["claim_count"] for g in groups.values())
    check("claim_groups_total", total_claims == 89, str(total_claims))
    check("critical_paths_absent", groups["critical_path_claims"]["status_counts"] == {"ABSENT_FROM_ALL_200_REACHABLE_TREES": 5},
          json.dumps(groups["critical_path_claims"]["status_counts"]))

    dup = ext["duplicate_analysis"]
    collisions = dup["cross_case_digest_collisions"]
    check("no_cross_case_digest_collisions", collisions == 0 or (isinstance(collisions, dict) and not collisions),
          str(collisions))
    check("mirrored_groups", len(dup["mirrored_within_case"]) == 20, str(len(dup["mirrored_within_case"])))

    ext_refs = ext["external_references"]
    missing = [r for r in ext_refs if not r["digest_in_reachable_history"]]
    check("external_refs_disclosed", len(ext_refs) == 4 and len(missing) == 3, f"{len(missing)} of {len(ext_refs)} unreachable")
    legacy = ext["legacy_nonstandard_json_tokens"]
    check("legacy_infinity_tokens_preserved", len(legacy) == 10 and all(t["token"] == "Infinity" for t in legacy),
          str(len(legacy)))

    failures = [c for c in checks if c["status"] != "PASS"]
    result = {
        "schema": "drecover001.r0_provenance_extension_verification.v1",
        "status": "R0_PROVENANCE_EXTENSION_EVIDENCE_INTERNALLY_CONSISTENT" if not failures else "R0_PROVENANCE_EXTENSION_EVIDENCE_FAILED",
        "check_count": len(checks),
        "failure_count": len(failures),
        "failures": failures,
        "extension": "docs/evidence/drecover001/r0_provenance_extension.json",
        "extension_sha256": out_sha,
        "script": "docs/evidence/drecover001/audit_provenance_extension.py",
        "script_sha256": script_sha,
        "checks": checks,
        "disclosure": ("Offline re-verification from archived bytes and historical git blobs only; no solver start, no network, "
                       "no new physical evidence, no independent A5 signature.")
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "check_count", "failure_count", "extension_sha256")}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)

main()
