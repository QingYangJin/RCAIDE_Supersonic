
"""Build the P1 preregistration JSON and the A5 dossier (Issue #14, zero physical)."""
from __future__ import annotations
import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P1-20261122-02")
G2 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
sys.path.insert(0, str(REPO))
from research.concorde_metaopt.dreal001.geometry.polar_rows import read_polar_rows  # noqa: E402

RUN_ID = "DRECOVER001-P1-20261122-02"
BATCH_ID = "DRECOVER001-P1-20261122-02-B01"
AUTH = "AUTH-DREAL004-P1-20261122-01"
DESIGNS = ["d00", "d01", "d04", "d07"]
PARTS = {"d00": "support", "d01": "support", "d04": "query", "d07": "query"}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def coarse() -> list[dict]:
    out = []
    for d in DESIGNS:
        cid = "g2-m202-%s-%s-s1" % (d, PARTS[d])
        cd = G2 / "cases" / cid
        spec = json.loads((cd / "task_spec.json").read_text(encoding="utf-8"))
        polar = cd / (cid + ".polar")
        rows = read_polar_rows(polar, mach=2.02)
        clt = float(spec["cl_target"])
        lo = hi = None
        for a, b in zip(rows, rows[1:]):
            if a.cl <= clt <= b.cl:
                lo, hi = a, b
                break
        if lo is None:
            raise SystemExit("no coarse bracket for " + d)
        slope = (hi.cl - lo.cl) / (hi.alpha_deg - lo.alpha_deg)
        a_t = lo.alpha_deg + (clt - lo.cl) / slope
        out.append({
            "design": d, "partition": PARTS[d], "coarse_case_id": cid,
            "coarse_polar_path": str(polar), "coarse_polar_sha256": sha(polar),
            "coarse_task_spec_sha256": sha(cd / "task_spec.json"),
            "cl_target": clt, "sref_m2": float(spec["sref_m2"]),
            "q_pa": float(spec["dynamic_pressure_pa"]),
            "coarse_rows": len(rows), "coarse_alpha_step_deg": rows[1].alpha_deg - rows[0].alpha_deg,
            "bracket_alpha_deg": [lo.alpha_deg, hi.alpha_deg],
            "bracket_cl": [lo.cl, hi.cl],
            "coarse_slope_cl_per_deg": slope,
            "alpha_target_estimate_deg": a_t,
        })
    return out


def code_shas() -> dict:
    rel = [
        "research/concorde_metaopt/dreal001/geometry/adaptive_alpha.py",
        "research/concorde_metaopt/dreal001/geometry/polar_rows.py",
        "research/concorde_metaopt/dreal001/geometry/solver_runner.py",
        "research/concorde_metaopt/dreal001/meta/real_admission.py",
    ]
    out = {r: sha(REPO / r) for r in rel}
    out["scripts/p1_run.py"] = sha(RUN / "scripts" / "p1_run.py") if (RUN / "scripts" / "p1_run.py").exists() else "PENDING_AT_PREREG"
    out["scripts/audit_real_case.py"] = sha(Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py"))
    out["scripts/admit_g1_case.py"] = sha(Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/scripts/admit_g1_case.py"))
    return out


def main() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    brackets = coarse()
    prereg = {
        "schema": "dreal004.p1_preregistration.v1",
        "generated_utc": now(),
        "issue": "QingYangJin/RCAIDE_Supersonic#14",
        "owner_instruction_refs": ["issue #14 body（P1 需 A5 批次审查 + Lead 新 GO）", "m10191 批准真实评估"],
        "branch": "research/dreal004-alpha-adaptive-meta-sampling",
        "base_commit": "3a8de159aa461d10ac72571db042d3feb893afe0",
        "run_id": RUN_ID,
        "batch_id": BATCH_ID,
        "authorization_id": AUTH,
        "target_task": "DREAL004-M202",
        "target_mach": 2.02,
        "designs": brackets,
        "caps": {
            "max_design_starts": 12,
            "max_starts_per_design": 3,
            "max_alpha_probes_per_start": 3,
            "max_internal_solver_cases": 36,
            "retries": 0,
            "parallelism": 1,
            "case_timeout_s": 600,
            "wall_clock_s": 3600,
            "consecutive_solver_failure_stop": 2,
        },
        "algorithm": {
            "name": "ADAPTIVE_SECANT_ALPHA_REFINEMENT",
            "coarse_source": "existing G2 stage1 M202 raw polar rows only (zero physical)",
            "round_half_widths_deg": [0.004, 0.002, 0.001],
            "probes_per_round": 3,
            "probe_rule": "predicted alpha_target and predicted +/- half_width, clipped to the current raw bracket; never extrapolate",
            "bracket_update": "refit a local secant bracket around cl_target using all observed raw rows (coarse + new rounds); if no bracket -> NO_BRACKET and stop that design",
            "stop_when": "a raw polar row from a new solver run satisfies |q*Sref*CL - lift_target|/lift_target <= 1e-3",
        },
        "admission": {
            "tol_cl_rel": 1e-3,
            "may_not_be_relaxed": True,
            "interpolated_target_never_admitted": True,
            "only_raw_polar_rows_admitted": True,
            "audit_script": "D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py",
            "admit_script": "D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/scripts/admit_g1_case.py",
            "certificate_scope": "LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED",
        },
        "success_criteria": {
            "raw_point_hit_rate": ">=0.70 over 4 designs",
            "internal_cases": "report per design; comparison baseline = 4 fixed 49-point sweeps = 196 internal",
        },
        "stop_rules": [
            "3 starts per design exhausted without a raw point -> NO_RAW_POINT",
            "12 starts total -> batch closes",
            "2 consecutive solver failures -> STOP",
            "wall clock >= 3600s -> STOP",
            "accounting not conserved -> STOP_ACCOUNTING_VIOLATION",
            "each mini-batch (<=4 starts) uploaded and remote-readback verified before the next",
        ],
        "not_authorized": ["P2", "P3", "MAML training", "G2 restart", "R2", "tol widening"],
        "code_shas": code_shas(),
        "physical_starts_before_batch": 0,
    }
    pre_path = RUN / "p1_preregistration.json"
    pre_path.write_text(json.dumps(prereg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    pre_sha = sha(pre_path)

    gates = {
        "P1_CAPS": "12 starts total, 3 per design, 3 alpha probes per start, 36 internal max, 0 retry, parallel 1, 600s per case, wall 3600s, 2 consecutive failure stop.",
        "P1_COARSE_BRACKET_PROVENANCE": "all coarse brackets come from existing G2 stage1 M202 raw polar files whose sha256 are listed per design; no new solver call before GO.",
        "P1_ALPHA_ALGORITHM": "secant prediction inside the observed raw bracket, half widths 0.004/0.002/0.001 deg, no extrapolation, non-monotone or missing bracket stops the design.",
        "P1_ADMISSION_TOLERANCE": "tol_CL=1e-3 unchanged; only raw polar rows from new solver runs may be admitted; interpolated targets are never labels.",
        "P1_ACCOUNTING_CONTROLS": "per-start ledger rows (case, round, status, wall, internal, exit code, matched row), cumulative caps enforced before each start, accounting report at the end.",
        "P1_ZERO_PHYSICAL_UNTIL_GO": "dossier creation and A5 review are zero physical; the batch starts only after an A5 PASS and a separate Lead GO record binding this prereg sha256.",
    }
    L = []
    w = L.append
    w("# Issue #14 P1 批次方案 A5 审查卷宗（自适应迎角，真实评估，≤12 starts）")
    w("")
    w("## 0. 本卷宗的性质")
    w("")
    w("- 对象：Issue #14 的 P1 小批（真实求解），Owner m10191 已批准真实评估。")
    w("- 本卷宗在 GO 之前生成：**尚未启动任何真实求解**，coarse bracket 全部来自既有 G2 stage1 原始 polar（零物理）。")
    w("- A5 需裁决：是否允许按本方案启动 ≤12 个真实 design starts。P2/P3/MAML/G2 重启/R2 均不在本授权内。")
    w("- 本卷宗不解宽任何容差，不允许把插值当原始行，不允许复用或改写 G1/G2 结果。")
    w("")
    w("## 1. 批次身份与预算")
    w("")
    w("- run_id: " + RUN_ID)
    w("- batch_id: " + BATCH_ID)
    w("- authorization_id: " + AUTH)
    w("- 目标：DREAL004-M202，Mach 2.02，设计 d00/d01/d04/d07")
    w("- 上限：12 starts，每设计 ≤3 starts，每 start ≤3 alpha probes，内部 case ≤36，0 retry，parallel 1，单 case 600s，墙钟 3600s")
    w("- 算术核对：12 starts × 3 probes = 36 internal（<=36）；固定 49 点扫描对照：4 设计 × 49 = 196 internal")
    w("- 现有既有原始行只作为 coarse bracket 来源，不计入本轮 starts/internal")
    w("")
    w("## 2. coarse bracket 来源（零物理）")
    w("")
    w("| 设计 | 粗 case | 粗 polar sha256 | cl_target | bracket alpha (deg) | bracket CL | 粗步长 | 预测 alpha |")
    w("|---|---|---|---|---|---|---|---|")
    for b in brackets:
        w("| %s | %s | %s | %.12f | [%.4f, %.4f] | [%.9f, %.9f] | %.4f | %.6f |"
          % (b["design"], b["coarse_case_id"], b["coarse_polar_sha256"][:16], b["cl_target"],
             b["bracket_alpha_deg"][0], b["bracket_alpha_deg"][1],
             b["bracket_cl"][0], b["bracket_cl"][1],
             b["coarse_alpha_step_deg"], b["alpha_target_estimate_deg"]))
    w("")
    w("说明：G2 stage1 的 M202 扫描步长 0.24 deg，目标 CL 落在 4.96–5.20 deg 之间；上表是把这些既有原始行做局部割线插值得到的预测中心，不是新求解结果。")
    w("")
    w("## 3. 自适应算法（每设计最多 3 轮、每轮 3 个 alpha probe）")
    w("")
    w("1. 用当前 bracket 做割线预测 alpha_target，取 alpha_target-Δ、alpha_target、alpha_target+Δ（Δ 依次 0.004/0.002/0.001 deg），并夹在当前原始 bracket 内；不做外推。")
    w("2. 每个 case 做 1 次真实求解（1 start，3 个 internal alpha 行）。")
    w("3. 读取新原始 polar 行；若存在某行满足 |q*Sref*CL - lift_target|/lift_target <= 1e-3，则该设计命中，转独立审计 + 准入。")
    w("4. 否则用全部已观测原始行重拟合 bracket，进入下一轮；3 轮仍未命中 -> NO_RAW_POINT（NULL_LABEL），不重跑。")
    w("5. 单调性缺失、无 bracket、求解失败按停止条件处理，不伪造行。")
    w("")
    w("## 4. 准入与记账")
    w("")
    w("- 只有新求解产生的原始 polar 行可准入；插值估计只用于选点，永不作为标签。")
    w("- 准入走既有独立审计脚本（复核 artifact sha256/deck 字段/polar 行/升力残差）与 RealAdmissionManifest 准入脚本，证书 scope 同前：LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED。")
    w("- 每次 start 前检查：starts<12、该设计 starts<3、internal+3<=36、墙钟+600<=3600、无 2 连败；否则不启动。")
    w("- 每个 ≤4 starts 迷你批完成后上传 GitHub 并逐文件 SHA256 回读，回读失败即停。")
    w("")
    w("## 5. 交付物")
    w("")
    w("- raw_cases（每个 case 的全部原始文件）、tables/alpha_refinement_history.csv、all_evaluations.csv、admitted_labels.csv、failed_or_null.csv、actual_solver_ledger.csv")
    w("- metadata（prereg/go/code_sha/data_manifest）、figures（中文 PNG + figure_data.csv）、SHA256SUMS.txt、upload_receipt.json")
    w("- P1 结论：hit rate、每设计 internal 数、与固定 49 点扫描的 internal 对比、A5 P1 关闭审查")
    w("")
    w("## 6. 披露（不隐藏）")
    w("")
    w("- d00/d01 在 G1 已有同几何、同 Mach 的已准入标签；P1 对这两个设计是重确认 + 自适应效率测量，不是新几何发现。d04/d07 在 G1/G2 尚无准入标签。")
    w("- 已发现的重复：d07 的 G2 stage1 coarse polar 与 d00 字节完全相同（同 sha256 b1374bdf…），两设计仅 fuselage_length 不同。这说明该变量在当前薄面 VSPAERO 模型下对本极曲线无影响；d07 因此只作该变量的重复性/无效性对照，即使命中也不视为独立几何发现。")
    w("- 所有准入证书为同机、非物理验证、非人类签名；A5 为 deepseek-flash 单发只读评审，不是人类签署。")
    w("- 本批次不训练 MAML、不产生跨任务泛化结论；P2/P3 仍需另行 A5 + Lead GO。")
    w("- 墙钟按各次 run_case 的 wall_s 之和计算（含求解进程时间，不含上传等待），与 G2 口径一致。")
    w("")
    w("## 7. A5 检查点")
    w("")
    for k, v in gates.items():
        w("- " + k + ": " + v)
    w("")
    w("## 8. 待绑定哈希")
    w("")
    w("- 本 preregistration sha256: " + pre_sha)
    w("- 代码/脚本 sha256:")
    for k, v in prereg["code_shas"].items():
        w("  - " + k + ": " + v)
    w("")
    dossier = RUN / "p1_a5_dossier.md"
    dossier.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"prereg": str(pre_path), "prereg_sha256": pre_sha,
                      "dossier": str(dossier), "dossier_bytes": dossier.stat().st_size,
                      "dossier_sha256": sha(dossier),
                      "designs": [b["design"] for b in brackets]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
