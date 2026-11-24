"""Read back the A0 package from GitHub and compare blob-by-blob with the local commit.

The A0 upload ran with --no-push at the time (its receipt records pushed=false and readback
skipped=true). The files are in the branch (they were carried along by the O0 commit and the
rebase), but "present in a commit I made" is not "what the remote holds". This script asks the
remote tree API for every file under the A0 directory and compares the blob shas one by one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/scripts")
import o1_upload as up  # noqa: E402

RUN = up.RUNS["A0"]
RUN_REL = up.RUN_REL_TMPL % RUN.name


def main() -> int:
    head = up.run_git(["rev-parse", "HEAD"]).stdout.strip()
    remote_head = up.api("/repos/%s/git/ref/heads/%s" % (up.OWNER_REPO, up.BRANCH),
                          up.token())["object"]["sha"]
    local = up.local_blobs(head, RUN_REL)
    remote = up.remote_blobs(head, RUN_REL)
    files = sorted(p for p in (up.REPO / RUN_REL).rglob("*") if p.is_file())
    missing, bad, checked = [], [], 0
    for path in files:
        rel = path.relative_to(up.REPO / RUN_REL).as_posix()
        if rel in ("upload_receipt.json", "data_manifest.json", "SHA256SUMS.txt"):
            continue
        checked += 1
        lb = local.get(rel)
        rb = remote.get(RUN_REL + "/" + rel)
        if lb is None:
            missing.append(rel + " (not in local commit)")
        elif rb is None:
            missing.append(rel)
        elif rb != lb:
            bad.append(rel)
    report = {
        "schema": "dreal005.a0_readback.v1",
        "run_id": RUN.name,
        "local_head": head,
        "remote_branch_head": remote_head,
        "head_matches_remote": head == remote_head,
        "branch": up.BRANCH,
        "checked": checked,
        "local_blob_count": len(local),
        "remote_blob_count": len(remote),
        "missing_count": len(missing),
        "bad_count": len(bad),
        "missing": missing[:50],
        "bad": bad[:50],
        "note": ("The A0 package was committed but its own receipt records pushed=false and "
                 "readback skipped. This is the readback that receipt lacked; it compares the "
                 "remote tree at the current branch head with the local commit, so it proves "
                 "the remote holds the same bytes, not merely that a commit exists."),
        "checked_utc": up.now(),
    }
    out = RUN / "a0_remote_readback.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("local_head", "remote_branch_head",
                                             "head_matches_remote", "checked", "missing_count",
                                             "bad_count", "missing", "bad")},
                     ensure_ascii=False, indent=2))
    return 0 if not missing and not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
