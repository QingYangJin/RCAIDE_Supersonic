"""Package a dreal005 run (A0 or O0) into the repository layout, commit, push, verify.

Why a bespoke uploader instead of copying the P2 one: this project has two roots (A0 ablation and
the O0 optimisation), and the O0 root carries deliverables the P2 run did not have
(final_aircraft/, the A5 review trail, the GO record and the O0-FINAL verification ledger). The
layout below maps every source explicitly rather than globbing, so nothing silently drops out.

Usage: python o0_upload.py --run A0|O0 --label LABEL --total-starts N [--no-push]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal005-20261124")
BRANCH = "research/dreal005-conditional-meta-real-optimization"
PROXY = Path(r"D:/RCAIDE/.recovery-local-restore/git_via_proxy.py")
PY = Path(r"D:/Anaconda/envs/RCAIDE/python.exe")
OWNER_REPO = "QingYangJin/RCAIDE_Supersonic"
RUNS = {
    "A0": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-A0-20261124-01"),
    "O0": Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01"),
}
RUN_REL_TMPL = "research/concorde_metaopt/optimization_runs/%s"
DATA_SUFFIXES = (".vspgeom", ".vspaero", ".polar", ".history", ".lod", ".adb", ".vkey",
                 ".dat", ".cases", ".quad.cases", ".csf", ".group.0", ".group.1", ".0", ".1")
CASE_JSON = ("admission_certificate.json", "admission_manifest.json", "approval.json",
             "audit.json", "case_inputs.json", "case_result.json", "evaluations.jsonl",
             "plan.json", "solver_attempts.jsonl", "task_spec.json")


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
    import time
    import urllib.request
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request("https://api.github.com" + path,
                headers={"Authorization": "Bearer " + tok,
                         "Accept": "application/vnd.github+json", "User-Agent": "x"})
            with urllib.request.urlopen(req, timeout=180) as r:
                buf = bytearray()
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    buf.extend(chunk)
                return json.loads(buf.decode())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + 2 * attempt)
    raise RuntimeError("API failed after retries: %r" % (last,))


def fresh(dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    return dst


def copy_case(src: Path, dst: Path) -> None:
    """Copy one solver case directory: structured records, raw solver bytes and logs."""
    dst.mkdir(parents=True)
    for name in CASE_JSON:
        p = src / name
        if p.exists():
            shutil.copy2(p, dst / name)
    for p in src.iterdir():
        if not p.is_file() or p.name in CASE_JSON:
            continue
        if any(p.name.endswith(s) for s in DATA_SUFFIXES) or p.suffix in (
                ".json", ".csv", ".txt", ".log"):
            shutil.copy2(p, dst / p.name)
    lg = src / "logs"
    if lg.exists():
        shutil.copytree(lg, dst / "logs", dirs_exist_ok=True)


def copy_tree(src: Path, dst: Path, patterns: tuple = ("*",)) -> int:
    """Copy a directory tree, skipping caches. Returns the number of files copied."""
    if not src.exists():
        return 0
    fresh(dst)
    n = 0
    for pat in patterns:
        for p in sorted(src.rglob(pat)):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            rel = p.relative_to(src)
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst / rel)
            n += 1
    return n


def copy_files(src: Path, dst: Path, names) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for name in names:
        p = src / name
        if p.exists() and p.is_file():
            shutil.copy2(p, dst / p.name)
            n += 1
    return n


def build_a0(pkg: Path, run: Path) -> dict:
    counts = {}
    counts["dataset"] = copy_tree(run / "dataset", pkg / "training" / "dataset")
    counts["figures"] = copy_tree(run / "figures", pkg / "figures")
    counts["tables"] = copy_tree(run / "tables", pkg / "tables")
    counts["training"] = copy_tree(run / "training", pkg / "training")
    counts["scripts"] = copy_tree(run / "scripts", pkg / "scripts", ("*.py",))
    counts["audits"] = copy_tree(run / "audits", pkg / "audits")
    counts["inputs"] = copy_files(run, pkg / "inputs",
                                  ("run_config.json", "a0_preregistration.json"))
    counts["metadata"] = copy_files(run, pkg / "metadata",
                                    ("a0_resource.summary.json", "a0_result.json",
                                     "a0_batch_accounting.json", "README.md"))
    return counts


def build_o0(pkg: Path, run: Path) -> dict:
    counts = {}
    raw = fresh(pkg / "raw_cases")
    n = 0
    for batch in sorted(p for p in (run / "cases").iterdir() if p.is_dir()):
        for case in sorted(p for p in batch.iterdir() if p.is_dir()):
            copy_case(case, raw / batch.name / case.name)
            n += 1
    counts["raw_cases"] = n
    counts["tables"] = copy_tree(run / "tables", pkg / "tables")
    counts["figures"] = copy_tree(run / "figures", pkg / "figures")
    counts["final_aircraft"] = copy_tree(run / "final_aircraft", pkg / "final_aircraft")
    counts["scripts"] = copy_tree(run / "scripts", pkg / "scripts", ("*.py",))
    counts["inputs"] = copy_files(run, pkg / "inputs", (
        "o0_preregistration.json", "o0_a5_dossier.md", "o0_dossier_receipt.json",
        "o0_final_go_record.json", "o0_binding_verification.json",
        "o0_batch_close_B02.json", "o0_batch_crash_B02.json",
        "o0_batch_abort_B01.json", "o0_batch_accounting_B02.json"))
    counts["metadata"] = copy_files(run, pkg / "metadata", (
        "o0_result_B02.json", "o0_attempts.jsonl", "o0_resource.summary.json",
        "o0_resource.jsonl", "README.md"))
    counts["audits"] = (copy_tree(run / "a5_review", pkg / "audits" / "a5_review")
                        + copy_tree(run / "a5_support", pkg / "audits" / "a5_support")
                        + copy_tree(run / "go_history", pkg / "audits" / "go_history")
                        + copy_tree(run / "o0_final", pkg / "audits" / "o0_final"))
    counts["audits_logs"] = copy_files(run, pkg / "audits", tuple(
        p.name for p in sorted(run.glob("*.log"))))
    return counts


def build_package(run_name: str, label: str, total_starts: int):
    run = RUNS[run_name]
    run_rel = RUN_REL_TMPL % run.name
    pkg = REPO / run_rel
    fresh(pkg)
    counts = (build_a0 if run_name == "A0" else build_o0)(pkg, run)
    note = {
        "A0": "A0 是五臂离线对照：真实标签为 P2 阶段真实 VSPAERO 结果的重放，本阶段未发起新的物理求解。",
        "O0": "O0 是真实闭环：全部 Di 来自真实 VSPAERO 原始极曲线行，physical starts 记录见 metadata 与 raw_cases。",
    }[run_name]
    readme = "\n".join([
        "# " + run.name + ("（A0 五臂因果消融）" if run_name == "A0" else "（O0 真实气动反馈优化）"),
        "",
        note,
        "",
        "本目录由 scripts/o0_upload.py 从运行根 " + run.as_posix() + " 打包生成，",
        "逐文件 sha256 见 data_manifest.json 与 SHA256SUMS.txt。",
        "",
        "目录约定：inputs/ 预注册与授权记录；raw_cases/ 每个 case 的原始求解器产物与准入记录；",
        "tables/ 汇总表；figures/ 由原始数据绘制的图（绘图脚本见 scripts/）；",
        "metadata/ 运行记录与资源采样；training/ 训练产物；audits/ A5 审查、绑定校验与 GO 历史。",
        "final_aircraft/ 仅 O0 有：交付给 OpenVSP 的可打开构型、STL/STEP 与前后对比图表。",
    ]) + "\n"
    (pkg / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    files = []
    for p in sorted(pkg.rglob("*")):
        if p.is_file() and p.name not in ("data_manifest.json", "SHA256SUMS.txt",
                                          "upload_receipt.json"):
            files.append({"path": p.relative_to(pkg).as_posix(), "bytes": p.stat().st_size,
                          "sha256": sha(p)})
    manifest = {"schema": "dreal005.upload_manifest.v1", "run_id": run.name,
                "label": label, "generated_utc": now(), "physical_starts_recorded": total_starts,
                "file_count": len(files), "total_bytes": sum(f["bytes"] for f in files),
                "source_root": run.as_posix(), "copied_by_section": counts, "files": files}
    (pkg / "data_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    lines = ["%s  %s" % (f["sha256"], f["path"]) for f in sorted(files, key=lambda x: x["path"])]
    (pkg / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return pkg, files, manifest


def run_git(args, timeout=3600):
    return subprocess.run(["git", "-C", str(REPO), "-c", "user.name=QingYangJin",
                           "-c", "user.email=118662522+QingYangJin@users.noreply.github.com"] + args,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


def push():
    env = dict(os.environ)
    env["GIT_CWD"] = str(REPO)
    env["PYTHONIOENCODING"] = "utf-8"
    last = ""
    for ip in ("140.82.114.4", "140.82.112.3", "20.205.243.166", "4.208.26.200", "20.27.177.113"):
        env["GITHUB_IP"] = ip
        p = subprocess.run([str(PY), str(PROXY), "push", "{URL}",
                            "HEAD:refs/heads/" + BRANCH],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=env, timeout=3600)
        last = (p.stdout + p.stderr)[-1200:]
        if p.returncode == 0:
            return True, last
    return False, last


def local_blobs(commit: str, run_rel: str) -> dict:
    out = run_git(["ls-tree", "-r", "-z", commit, "--", run_rel]).stdout
    res = {}
    for ent in out.split("\x00"):
        if not ent:
            continue
        meta, path = ent.split("\t", 1)
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            res[path.split(run_rel + "/", 1)[-1]] = parts[2]
    return res


def remote_blobs(commit: str, run_rel: str) -> dict:
    tok = token()
    tree_sha = api("/repos/%s/git/commits/%s" % (OWNER_REPO, commit), tok)["tree"]["sha"]
    for part in run_rel.split("/"):
        ents = api("/repos/%s/git/trees/%s" % (OWNER_REPO, tree_sha), tok)["tree"]
        hit = next((e for e in ents if e["path"] == part), None)
        if hit is None:
            return {}
        tree_sha = hit["sha"]
    out = {}
    stack = [(run_rel, tree_sha)]
    while stack:
        prefix, sha_ = stack.pop()
        ents = api("/repos/%s/git/trees/%s" % (OWNER_REPO, sha_), tok)["tree"]
        for e in ents:
            path = prefix + "/" + e["path"]
            if e["type"] == "blob":
                out[path] = e["sha"]
            elif e["type"] == "tree":
                stack.append((path, e["sha"]))
    return out


def verify_remote(commit: str, run_rel: str, pkg: Path, files) -> dict:
    remote = remote_blobs(commit, run_rel)
    local = local_blobs(commit, run_rel)
    bad, missing = [], []
    for f in files:
        lb = local.get(f["path"])
        r = remote.get(run_rel + "/" + f["path"])
        if lb is None:
            missing.append(f["path"] + " (absent from local commit)")
        elif r is None:
            missing.append(f["path"])
        elif r != lb:
            bad.append(f["path"])
    return {"commit": commit, "checked": len(files), "missing": missing[:50],
            "missing_count": len(missing), "bad": bad[:50], "bad_count": len(bad),
            "manifest_sha256": sha(pkg / "data_manifest.json"),
            "sha256sums_sha256": sha(pkg / "SHA256SUMS.txt")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, choices=sorted(RUNS))
    ap.add_argument("--label", required=True)
    ap.add_argument("--total-starts", type=int, required=True)
    ap.add_argument("--message", default="")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    run = RUNS[a.run]
    run_rel = RUN_REL_TMPL % run.name
    pkg, files, manifest = build_package(a.run, a.label, a.total_starts)
    total = sum(f["bytes"] for f in files)
    print("packaged %d files / %d bytes -> %s" % (len(files), total, pkg))
    run_git(["add", "-A", run_rel])
    run_git(["add", ".gitignore"])
    msg = a.message or "%s 阶段证据上传：%d 文件 / %.1f MiB（真实物理 starts %d）" % (
        a.label, len(files), total / 1048576.0, a.total_starts)
    c = run_git(["commit", "-m", msg])
    if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
        print(c.stdout[-2000:], c.stderr[-2000:])
        return 2
    head = run_git(["rev-parse", "HEAD"]).stdout.strip()
    receipt = {"schema": "dreal005.upload_receipt.v1", "label": a.label, "run_id": run.name,
               "local_commit": head, "file_count": len(files), "total_bytes": total,
               "branch": BRANCH, "packaged_utc": now()}
    if a.no_push:
        receipt.update(pushed=False, readback={"skipped": True})
    else:
        ok, log = push()
        receipt["push_ok"] = ok
        receipt["push_log_tail"] = log[-600:]
        if not ok:
            (run / "upload_receipt.json").write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=False, indent=2)[:2000])
            return 3
        remote_head = api("/repos/%s/git/ref/heads/%s" % (OWNER_REPO, BRANCH),
                          token())["object"]["sha"]
        receipt["remote_head"] = remote_head
        if remote_head != head:
            receipt["readback"] = {"remote_head": remote_head, "match_local": False}
            (run / "upload_receipt.json").write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=False, indent=2)[:2000])
            return 4
        rb = verify_remote(head, run_rel, pkg, files)
        receipt["readback"] = rb
        if rb["bad"] or rb["missing"]:
            (run / "upload_receipt.json").write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=False, indent=2)[:3000])
            return 5
    (pkg / "upload_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (run / "upload_receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("label", "run_id", "local_commit", "file_count",
                                              "total_bytes")}, ensure_ascii=False, indent=2))
    print(json.dumps(receipt.get("readback"), ensure_ascii=False)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
