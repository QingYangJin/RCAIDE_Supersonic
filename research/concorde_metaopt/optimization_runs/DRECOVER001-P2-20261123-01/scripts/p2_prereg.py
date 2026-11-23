
"""Freeze the P2 preregistration (dataset matrix, supplement batch, four-arm protocol)."""
import hashlib, json
from pathlib import Path
REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
PY = Path(r"D:/Anaconda/envs/RCAIDE/python.exe")


def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


dataset = rj(RUN / "p2_dataset" / "p2_dataset.json")
plan = rj(RUN / "p2_supplement_plan.json")
code_shas = {
    "research/concorde_metaopt/dreal001/meta/real_p2_arms.py":
        sha(REPO / "research/concorde_metaopt/dreal001/meta/real_p2_arms.py"),
    "research/concorde_metaopt/dreal001/meta/real_training.py":
        sha(REPO / "research/concorde_metaopt/dreal001/meta/real_training.py"),
    "research/concorde_metaopt/dreal001/meta/meta_dataset.py":
        sha(REPO / "research/concorde_metaopt/dreal001/meta/meta_dataset.py"),
    "research/concorde_metaopt/dreal001/meta/task_spec.py":
        sha(REPO / "research/concorde_metaopt/dreal001/meta/task_spec.py"),
    "research/concorde_metaopt/meta_learning/maml.py":
        sha(REPO / "research/concorde_metaopt/meta_learning/maml.py"),
    "research/concorde_metaopt/dreal001/meta/real_admission.py":
        sha(REPO / "research/concorde_metaopt/dreal001/meta/real_admission.py"),
    "scripts/p2_data.py": sha(RUN / "scripts" / "p2_data.py"),
    "scripts/p2_plan.py": sha(RUN / "scripts" / "p2_plan.py"),
    "scripts/p2_supplement.py": sha(RUN / "scripts" / "p2_supplement.py"),
    "scripts/p2_upload.py": sha(RUN / "scripts" / "p2_upload.py"),
    "scripts/audit_real_case.py":
        sha(Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01/scripts/audit_real_case.py")),
    "scripts/admit_g1_case.py":
        sha(Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G1-20261121-01/scripts/admit_g1_case.py")),
}
tasks = []
for t in dataset["tasks"]:
    tasks.append({"task_id": t["task_id"], "split": t["split"],
                  "support_designs": t.get("support_designs") or [],
                  "query_designs": t.get("query_designs") or [],
                  "support": t["support"], "query": t["query"],
                  "k_eligible_after_supplement": [k for k in (1, 3) if t["support"] >= k]})
prereg = {
    "schema": "dreal004.p2_preregistration.v1",
    "run_id": "DRECOVER001-P2-20261123-01",
    "batch_id": "DRECOVER001-P2-20261123-01-B01",
    "authorization_id": "AUTH-DREAL004-P2-20261123-01",
    "owner_instruction_ref": "m10841 + Issue #14 comment 7103901506 (P2 directive)",
    "created_utc": "2026-11-23T15:20:00Z",
    "nature": "P2: reuse existing admitted real labels, supplement only the missing "
              "support slots with one frozen <=16-start batch, then run four-arm meta-learning "
              "with K=1 and K=3. Not a P3 optimization comparison and no online BO.",
    "dataset_before_supplement": {
        "source_runs_scanned": ["DRECOVER001-R2-20261120-01",
                                "DRECOVER001-G1-20261121-01",
                                "DRECOVER001-G2-20261121-01"],
        "rows": dataset["rows"],
        "certificates": len(dataset["certificates"]) if isinstance(dataset["certificates"], list)
        else dataset["certificates"],
        "tasks": tasks,
        "excluded_records": len(dataset.get("excluded") or []),
        "replay_method": "re-admit historical admission_manifest.json in place with the "
                         "original historical task_id mapped by an explicit alias table; no solver start, "
                         "historical files unmodified",
    },
    "supplement_batch": {
        "starts": plan["starts"], "max_starts": 16,
        "max_alpha_probes_per_start": 3, "max_internal_solver_cases": 48,
        "parallelism": 1, "timeout_s_per_start": 600, "retries": 0,
        "wall_clock_max_s": 9600, "upload_readback_every_starts": 8,
        "bracket_provenance": plan["bracket_provenance"],
        "plan_sha256": sha(RUN / "p2_supplement_plan.json"),
        "starts_plan": plan["starts_plan"],
        "stop_rules": ["max 16 charged starts", "max 48 internal cases",
                       "wall clock 9600 s (= 16 x 600 s worst case)", "two consecutive non-SOLVED starts",
                       "solver REFUSED/EXCEPTION", "accounting not conserved",
                       "upload/readback failure", "any physics anomaly"],
        "no_retry_on_failed_label": True,
    },
    "post_supplement_expectation": {
        "note": "expected availability if every supplement start admits; shortfalls are reported, "
                "not filled with synthetic or interpolated values",
        "expected": {"P2-CANON-M140": "3 support / 1 query",
                     "P2-CANON-M160": "3 support / 2 query",
                     "P2-CANON-M180": "3 support / 3 query",
                     "P2-CANON-M200": "3 support / 3 query",
                     "P2-CANON-M202": "3 support / 3 query",
                     "P2-CANON-M220": "3 support / 1 query",
                     "P2-CANON-M240": "3 support / 3 query",
                     "P2-CANON-M260": "3 support / 1 query"},
        "k5": "NOT_ELIGIBLE: frozen protocol has four independent support slots d00-d03; "
              "query rows may never be borrowed as support and repeated sampling is forbidden",
    },
    "arms": {
        "names": ["RANDOM_INIT", "POOLED_PRETRAIN", "TASK_COND_PRETRAIN", "FOMAML"],
        "module": "research/concorde_metaopt/dreal001/meta/real_p2_arms.py",
        "k_values": [1, 3],
        "seeds": [7, 19, 43],
        "network": "12D input, two hidden layers of 32, scalar output; the task-conditioned arm "
                   "adds 4 affine context features in a separate input block and is reported separately",
        "fomaml": "first-order, inner_lr 0.05, inner_steps 5, outer_lr 0.01, tasks_per_batch 2, "
                  "max_steps 60, CPU float64",
        "pretrain": "pooled supervised pretraining on all training-task support+query rows with "
                    "validation-selected early stopping; the same pretrained weights are the "
                    "primary control for the FOMAML adaptation",
        "normalization": "TrainNormalizer fitted on training-task rows only",
        "selection": "hyperparameters and early stopping use validation tasks only; "
                     "test rows are scored once after selection",
        "reporting": "per task per seed per arm: MAE and RMSE in newtons, predictions, targets, "
                     "support/query ids, training curves, checkpoint sha256, normalization params",
    },
    "splits": {"train": ["P2-CANON-M140", "P2-CANON-M160", "P2-CANON-M200", "P2-CANON-M202"],
               "val": ["P2-CANON-M180", "P2-CANON-M220"],
               "test": ["P2-CANON-M240", "P2-CANON-M260"]},
    "source_code_sha256": code_shas,
    "targets_and_claims": {
        "primary": "unseen-task K-shot MAE/RMSE in newtons and paired difference versus "
                   "POOLED_PRETRAIN, reported per task and per seed",
        "secondary": "offline candidate ranking diagnostics only; not online optimization",
        "not_claimed": ["statistical普遍显著性 from two held-out tasks",
                        "P1 internal-case reduction as MAML benefit",
                        "any physical/wind-tunnel validation"],
    },
    "disclosures": [
        "labels are LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED; same-host storage",
        "no off-machine backup (Owner waiver WAIVER-OFFMACHINE-BACKUP-20261118)",
        "CPU float64 23 repeated K=1/K=3 runs are the reproducible reference; CUDA only after numeric parity",
        "fuel_burn_kg is null; VSPAERO_INTERNAL_ONLY; LF-M2.02 NOT_VALIDATED",
        "old 24/8/4-label batches keep their own scopes; P1 is a pilot and is not a training batch",
    ],
}
(RUN / "p2_preregistration.json").write_text(
    json.dumps(prereg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

FULL = {"P2-CANON-M140": ("train", 0, 0), "P2-CANON-M160": ("train", 3, 2),
        "P2-CANON-M180": ("val", 2, 3), "P2-CANON-M200": ("train", 3, 3),
        "P2-CANON-M202": ("train", 2, 3), "P2-CANON-M220": ("val", 0, 0),
        "P2-CANON-M240": ("test", 1, 3), "P2-CANON-M260": ("test", 0, 0)}
SUPP = {}
for s in plan["starts_plan"]:
    d = SUPP.setdefault(s["task_id"], {"support": 0, "query": 0})
    d[s["partition"]] += 1
rows = ["# P2 A5 审查卷宗（协议与代码）", "",
        "性质：Issue #14 P2 指令（Owner comment 7103901506）下的真实补采批次 + 四臂元学习协议预注册。",
        "本文件只请求对“协议与代码”的审查；GO 记录在审查 PASS 后单独签发。", "",
        "## 0. 文件身份与绑定（可核验哈希）", "",
        "- 预注册文件：p2_preregistration.json，sha256 = " + sha(RUN / "p2_preregistration.json") + "。",
        "- 补采计划：p2_supplement_plan.json，sha256 = " + sha(RUN / "p2_supplement_plan.json") + "。",
        "- 数据清单：p2_dataset/p2_dataset.json，sha256 = " + sha(RUN / "p2_dataset" / "p2_dataset.json") + "。",
        "- 本卷宗无法在正文中包含自身哈希（自引用矛盾）。评审脚本在发送前计算本卷宗字节的 sha256，"
        "并以 DOSSIER_BYTE_IDENTITY 行放在送审内容头部，评审结束后写入 a5_review/verdict.json 的 dossier_sha256，"
        "GO 记录再复述该值；因此送审字节在评审时即可被绑定。", ""
        "## 1. 预算与边界", "",
        "- 补采硬上限：%d 次真实 solver 启动（计划正好 %d 次），内部迎角工况上限 48（16 starts × 3 点），每 start 3 点，并行 1，"
        "每 start 600 s，0 重试，墙钟 9600 s（16×600 s 最坏情况），每 8 starts 上传并回读。" % (16, plan["starts"]),
        "- 复用已有 25 条已准入真实标签，仅对缺口补采；不寻找/恢复历史丢失数据；不启动任何其他物理。",
        "- 训练不消耗 solver 启动；P3 在线优化未授权。", "",
        "## 2. 八任务数据矩阵（补采前 → 补采后；zeros 明示）", "",
        "补采理由：只有缺少 K=3 支持槽或完全没有数据的任务才补。M160、M200 已有 3 个独立 support，"
        "本批 0 次启动；M140/M220/M260 完全没有标签，必须同时补 3 个 support 和 1 个独立 query，"
        "否则这些任务没有任何独立 query 可评分。所有 query 使用 d03 这一独立几何，绝不充当 support。", "",
        "| 任务 | split | 补采前 support/query | 本批 starts | 补采后 support/query |",
        "| --- | --- | --- | --- | --- |"]
for tid in ("P2-CANON-M140", "P2-CANON-M160", "P2-CANON-M180", "P2-CANON-M200",
            "P2-CANON-M202", "P2-CANON-M220", "P2-CANON-M240", "P2-CANON-M260"):
    split, sb, qb = FULL[tid]
    sup = SUPP.get(tid, {"support": 0, "query": 0})
    rows.append("| %s | %s | %d / %d | %d | %d / %d |"
                % (tid, split, sb, qb, sup["support"] + sup["query"],
                   sb + sup["support"], qb + sup["query"]))
rows += ["", "合计复用 25 条已准入标签 + 本批最多 16 次启动（13 support、3 query）。",
         "K=5 = NOT_ELIGIBLE（冻结协议只有 d00–d03 四个独立支持槽，禁止用 query 充数）。", "",
         "## 3. 补采矩阵（16 starts，零物理 bracket 全部来自 G2 stage-1 polar）", "",
         "| 任务 | design | partition | cl_target | alpha 三点 | bracket |", "| --- | --- | --- | --- | --- | --- |"]
for s in plan["starts_plan"]:
    rows.append("| %s | %s | %s | %.6f | %s | [%.2f, %.2f] |"
                % (s["task_id"], s["design"], s["partition"], s["cl_target"],
                   ", ".join("%.6f" % a for a in s["alpha_grid_deg"]),
                   s["bracket_alpha_deg"][0], s["bracket_alpha_deg"][1]))
rows += ["", "## 3b. 复用标签的来源、别名与去重规则（P2_DATASET_MATRIX 证据）", "",
         "别名表（canonical ← 历史 task_id，显式、写死在脚本，不做字符串推断）：", ""]
for canon, aliases in sorted(dataset.get("task_aliases", {}).items()):
    rows.append("- " + canon + " ← " + "、".join(aliases))
rows += ["", "去重与冲突规则：", "",
         "- 以 (canonical task, design_sha256) 为键去重，同一设计只保留一条。",
         "- 同一键出现于不同批次时，批次优先级 P2(4) > G2(3) > G1(2) > R2(1)，高优先级整条保留。",
         "- 同优先级在同一设计上出现 support/query 冲突时，两条都排除并在 excluded 中记录原因，绝不自动挑选。",
         "- 每条复用证书都在原 case 目录就地重放 admit_real_manifest，只读历史文件、不启动求解器，"
         "证书 q_pa 必须与 canonical TaskSpec 动压一致（相对 1e-9）。", "",
         "逐任务/逐设计来源（复用标签，补采前）：", "",
         "| canonical 任务 | design_id | partition | 历史 task_id | 来源批次 | 来源 case | polar sha256 |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
alias_rev = {hist: canon for canon, names in dataset.get("task_aliases", {}).items() for hist in names}
for aid, src in sorted(dataset.get("sources", {}).items()):
    cdir = Path(src.get("case_dir", ""))
    man = json.loads((cdir / "admission_manifest.json").read_text(encoding="utf-8"))
    canon = alias_rev.get(man["task_id"], man["task_id"])
    polar = next((f for f in man.get("files", []) if str(f.get("path", "")).endswith(".polar")), {})
    rows.append("| %s | %s | %s | %s | %s | %s | %s |"
                % (canon, str(man.get("design_id", ""))[:12], man.get("partition"),
                   man["task_id"], src.get("run_id"), cdir.name,
                   str(polar.get("sha256", ""))[:16]))
rows += ["", "排除记录共 %d 条，原因分布：" % len(dataset.get("excluded") or [])]
from collections import Counter as _C
for reason, n in _C((e.get("reason") or "") for e in (dataset.get("excluded") or [])).most_common():
    rows.append("- %s：%d" % (reason, n))
rows += ["", "## 3c. 代码常量与证据绑定（P2_CAPS / P2_BRACKET_PROVENANCE 证据）", "",
         "补采驱动 scripts/p2_supplement.py 的硬常量（该文件 sha256 已写入预注册 source_code_sha256，"
         "运行前 gate_check 会比对，任何漂移都拒绝启动）：", "",
         "MAX_STARTS = 16；MAX_INTERNAL = 48；WALL_MAX = 9600.0；UPLOAD_EVERY = 8（每 8 starts 上传并回读）；",
         "retries: 0（代码中不存在重试路径）；parallelism: 1（单进程顺序循环）；timeout_s_per_start: 600。", "",
         "冲突规则在 scripts/p2_data.py（优先级 P2(4)>G2(3)>G1(2)>R2(1)，同优先级冲突两条都排除）。", "",
         "16 个 bracket 的零物理来源（原始 G2 stage-1 polar 文件、SHA256、夹住 cl_target 的两行）：", "",
         "| 任务 | design | polar sha256 | 原始极曲线两行 (alpha, CL) |", "| --- | --- | --- | --- |"]
for s in plan["starts_plan"]:
    rows.append("| %s | %s | %s | (%.2f, %.6f) / (%.2f, %.6f) |"
                % (s["task_id"], s["design"], s["stage1_polar_sha256"][:16] + "...",
                   s["bracket_alpha_deg"][0], s["bracket_cl"][0],
                   s["bracket_alpha_deg"][1], s["bracket_cl"][1]))
rows += ["", "完整 polar 路径与 SHA256 见 p2_supplement_plan.json 的 stage1_case_dir / stage1_polar / "
         "stage1_polar_sha256 字段；生成脚本 scripts/p2_plan.py 的 sha256 也在预注册中。", "",
         "## 4. 准入容差", "",
         "- 维持 1e-3 相对升力容差，不放宽；插值值不得写成原始极曲线行；只用原始 polar 行计算 D_i_N=q·Sref·C_Di。",
         "- 每条新标签须有独立本地重实现审计（非人类、非 A5）与 RealAdmissionManifest 逐文件哈希绑定。", "",
         "## 5. 四臂训练协议", "",
         "- 臂：RANDOM_INIT、POOLED_PRETRAIN、TASK_COND_PRETRAIN、FOMAML；K=1 与 K=3；种子 7/19/43。",
         "- 归一化只用训练任务；验证任务选超参/早停；测试任务只在选参后打分一次。",
         "- FOMAML：一阶，inner_lr 0.05，inner_steps 5，outer_lr 0.01，tasks_per_batch 2，max_steps 60，CPU float64。",
         "- 主要对照是 POOLED_PRETRAIN（同输入预训练+微调），条件模型单列报告。",
         "- 交付：逐任务 MAE/RMSE(N)、配对差、训练曲线 CSV、候选排序离线诊断、checkpoint 与归一化参数。", "",
         "## 6. 零物理声明", "",
         "- 本卷宗与预注册不启动任何 solver。只有 A5 给出 P2_PROTOCOL_AND_CODE_REVIEW_PASS 且 GO 记录绑定本卷宗与预注册哈希后，才可执行补采。",
         "- 补采之外的真实训练仍为 0 次物理；训练只读已准入标签。", "",
         "## 7. A5 检查点（必须逐项给出）", "",
         "— P2_CAPS：16 starts / 48 internal / 600 s / 0 retry / 每 8 starts 回读，是否写入代码常量与预注册。",
         "- P2_DATASET_MATRIX：25 条复用标签的来源、别名合并与去重规则是否可复核。",
         "- P2_BRACKET_PROVENANCE：16 个 bracket 是否全部来自 G2 stage-1 raw polar 且未启动求解器。",
         "- P2_ALPHA_PROTOCOL：每 start 3 点、探测点间距 0.004°（总跨度 0.008°）、"
         "中心按 bracket 夹紧、端点绝不超出原始 bracket 与 alpha 允许窗口。",
         "- P2_ACCOUNTING_CONTROLS：逐项列出——①只在真实 run_case 返回 physical_solver_starts=1 时计数；"
         "②internal 数从原始 polar 行数回填，缺失记 UNKNOWN 而非 0；③每 8 starts 必须完成上传并远端回读，"
         "失败即 STOP；④0 重试、并行 1；⑤2 连败/REFUSED/EXCEPTION/会计不守恒即 STOP；"
         "⑥所有 null 行保留 failure_kind，不重复计样。",
         "- P2_ADMISSION：1e-3 未放宽、原始行判据、证书逐文件哈希。",
         "- P2_TRAINING_PROTOCOL：四臂、K=1/3、种子、只用 train 归一化、只用 val 选参、query 独立。",
         "- P2_ZERO_PHYSICAL_UNTIL_GO。", "",
         "## 8. 已知披露", "",
         "- 标签同机保存、未经异机认证、无风洞/物理验证；fuel_burn_kg=null；LF-M2.02 NOT_VALIDATED。",
         "- 旧批次 task_id 通过显式别名表合并，历史文件不修改。",
         "- 数据不足时报告短缺矩阵，不合成、不插值、不复用 query 充当 support。", ""]
(RUN / "p2_a5_dossier.md").write_text("\n".join(rows), encoding="utf-8", newline="\n")
print("prereg", sha(RUN / "p2_preregistration.json"))
print("dossier", sha(RUN / "p2_a5_dossier.md"))
