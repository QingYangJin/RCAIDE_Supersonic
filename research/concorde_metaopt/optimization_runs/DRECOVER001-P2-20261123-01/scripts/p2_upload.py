
"""Package the P2 run, commit and push it to GitHub, then verify remote bytes.

Usage: python p2_upload.py --label B01-01 [--no-push]
Writes upload_receipt.json inside the package and in RUN.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
RUN_REL = "research/concorde_metaopt/optimization_runs/DRECOVER001-P2-20261123-01"
PKG = REPO / RUN_REL
BRANCH = "research/dreal004-alpha-adaptive-meta-sampling"
PROXY = Path(r"D:/RCAIDE/.recovery-local-restore/git_via_proxy.py")
PY = Path(r"D:/Anaconda/envs/RCAIDE/python.exe")
OWNER_REPO = "QingYangJin/RCAIDE_Supersonic"
COPY_FILES = ("plan.json", "approval.json", "task_spec.json", "case_inputs.json",
              "case_result.json", "audit.json", "admission_manifest.json",
              "admission_certificate.json", "solver_attempts.jsonl")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def token() -> str:
    txt = Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8")
    return re.search(r"GITHUB_TOKEN:\s*([^\s]+)", txt).group(1).strip().strip('"').strip("'")


def api(path: str, tok: str) -> dict:
    """GET a GitHub API JSON document with retries and chunked reads (large trees truncate otherwise)."""
    import urllib.request
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request("https://api.github.com" + path,
                headers={"Authorization": "Bearer " + tok,
                         "Accept": "application/vnd.github+json", "User-Agent": "x"})
            with urllib.request.urlopen(req, timeout=180) as r:
                buf = bytearray()
                expected = r.length
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    buf.extend(chunk)
                if expected is not None and len(buf) != expected:
                    raise IOError("short read %d/%d bytes" % (len(buf), expected))
                return json.loads(buf.decode())
        except Exception as e:  # noqa: BLE001
            last = e
            import time as _t
            _t.sleep(2 + 2 * attempt)
    raise RuntimeError("API failed after retries: %r" % (last,))


def copy_case(case_dir: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for name in COPY_FILES:
        p = case_dir / name
        if p.exists():
            shutil.copy2(p, dst / name)
    for ext in (".vspgeom", ".vspaero", ".polar", ".history", ".lod", ".adb", ".vkey"):
        for p in case_dir.glob("*" + ext):
            shutil.copy2(p, dst / p.name)
    lg = case_dir / "logs"
    if lg.exists():
        shutil.copytree(lg, dst / "logs", dirs_exist_ok=True)


def build_package(total_starts: int) -> list[dict]:
    PKG.mkdir(parents=True, exist_ok=True)
    cases = sorted([p for p in (RUN / "cases").iterdir() if p.is_dir()]) if (RUN / "cases").exists() else []
    raw_root = PKG / "raw_cases"
    raw_root.mkdir(exist_ok=True)
    for c in cases:
        copy_case(c, raw_root / c.name)
    for dname in ("tables", "figures", "metadata", "p2_dataset"):
        src = RUN / dname
        if src.exists():
            ddir = PKG / dname
            if ddir.exists():
                shutil.rmtree(ddir)
            shutil.copytree(src, ddir)
    st = PKG / "scripts"
    st.mkdir(exist_ok=True)
    for p in (RUN / "scripts").glob("*.py"):
        shutil.copy2(p, st / p.name)
    for name in ("p2_preregistration.json", "p2_a5_dossier.md", "p2_go_record.json",
                 "p2_supplement_plan.json", "p2_supplement_state.json",
                 "p2_supplement_accounting.json", "p2_admitted_labels.csv",
                 "p2_failed_or_null.csv", "p2_attempt_ledger.csv", "p2_alpha_rows.csv",
                 "all_evaluations.json", "run_config.json",
                 "task_family_split.json", "geometry_freeze.json", "README.md"):
        p = RUN / name
        if p.exists():
            shutil.copy2(p, PKG / name)
    a5 = RUN / "a5_review"
    if a5.exists():
        dst = PKG / "a5_review"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(a5, dst)
    ev = RUN / "evidence"
    if ev.exists():
        dst = PKG / "evidence"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(ev, dst)
    files = []
    for p in sorted(PKG.rglob("*")):
        if p.is_file() and p.name not in ("data_manifest.json", "SHA256SUMS.txt", "upload_receipt.json"):
            files.append({"path": p.relative_to(PKG).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)})
    manifest = {"schema": "dreal004.p2_data_manifest.v1", "run_id": RUN.name,
                "batch_id": "DRECOVER001-P2-20261123-01-B01", "generated_utc": now(),
                "physical_starts_recorded": total_starts, "file_count": len(files),
                "total_bytes": sum(f["bytes"] for f in files), "files": files}
    (PKG / "data_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8", newline="\n")
    lines = ["%s  %s" % (f["sha256"], f["path"]) for f in sorted(files, key=lambda x: x["path"])]
    (PKG / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return files


def run(cmd, cwd=None, timeout=1800):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def git(args, timeout=1800):
    return run(["git", "-C", str(REPO), "-c", "user.name=QingYangJin",
                "-c", "user.email=118662522+QingYangJin@users.noreply.github.com"] + args,
               timeout=timeout)


def push() -> tuple[bool, str]:
    env = dict(os.environ)
    env["GIT_CWD"] = str(REPO)
    env["PYTHONIOENCODING"] = "utf-8"
    last = ""
    for ip in ("140.82.114.4", "140.82.112.3", "20.205.243.166", "4.208.26.200", "20.27.177.113"):
        env["GITHUB_IP"] = ip
        p = subprocess.run([str(PY), str(PROXY), "push", "{URL}", "HEAD:refs/heads/" + BRANCH],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, timeout=3600)
        last = (p.stdout + p.stderr)[-1500:]
        if p.returncode == 0:
            return True, last
    return False, last


def local_blobs(commit: str) -> dict:
    out = git(["ls-tree", "-r", "-z", commit, "--", RUN_REL]).stdout
    res = {}
    for ent in out.split("\x00"):
        if not ent:
            continue
        meta, path = ent.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            res[path.split(RUN_REL + "/", 1)[-1]] = parts[2]
    return res


def verify_remote(commit: str, files: list[dict]) -> dict:
    tok = token()
    tree = api("/repos/%s/git/trees/%s?recursive=1" % (OWNER_REPO, commit), tok)["tree"]
    remote = {t["path"]: t["sha"] for t in tree if t["type"] == "blob"}
    local = local_blobs(commit)
    bad, missing = [], []
    for f in files:
        local_blob = local.get(f["path"])
        r = remote.get(RUN_REL + "/" + f["path"])
        if local_blob is None:
            missing.append(f["path"] + " (absent from local commit)")
        elif r is None:
            missing.append(f["path"])
        elif r != local_blob:
            bad.append(f["path"])
    return {"commit": commit, "checked": len(files), "missing": missing, "bad": bad,
            "manifest_sha256": sha(PKG / "data_manifest.json"),
            "sha256sums_sha256": sha(PKG / "SHA256SUMS.txt")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--total-starts", type=int, required=True)
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    files = build_package(a.total_starts)
    git(["add", "-A", RUN_REL])
    git(["add", ".gitignore"])
    msg = "P2 %s: raw cases/tables/metadata (%d files, %d starts)" % (a.label, len(files), a.total_starts)
    c = git(["commit", "-m", msg])
    if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
        print(c.stdout, c.stderr)
        return 2
    head = git(["rev-parse", "HEAD"]).stdout.strip()
    receipt = {"schema": "dreal004.p2_upload_receipt.v1", "label": a.label, "run_id": RUN.name,
               "local_commit": head, "file_count": len(files),
               "total_bytes": sum(f["bytes"] for f in files), "pushed_utc": now()}
    if a.no_push:
        receipt.update(pushed=False, readback=None)
    else:
        ok, log = push()
        receipt["push_ok"] = ok
        receipt["push_log_tail"] = log[-800:]
        if not ok:
            (RUN / "upload_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=False, indent=2)[:3000])
            return 3
        remote_head = api("/repos/%s/git/ref/heads/%s" % (OWNER_REPO, BRANCH), token())["object"]["sha"]
        if remote_head != head:
            receipt["readback"] = {"remote_head": remote_head, "match_local": False}
            (RUN / "upload_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=False, indent=2)[:3000])
            return 4
        rb = verify_remote(head, files)
        receipt["remote_head"] = head
        receipt["readback"] = rb
        if rb["bad"] or rb["missing"]:
            (RUN / "upload_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                                     encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=False, indent=2)[:3000])
            return 5
    (PKG / "upload_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8", newline="\n")
    (RUN / "upload_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("label", "local_commit", "file_count",
                                             "total_bytes", "push_ok", "readback")}, ensure_ascii=False, indent=2)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
