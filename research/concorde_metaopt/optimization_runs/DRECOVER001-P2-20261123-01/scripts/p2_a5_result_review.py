
"""Build the P2 result dossier and run the A5 single-shot read-only review (deepseek-flash)."""
from __future__ import annotations
import hashlib, json, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import yaml

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
OUT = RUN / "a5_result_review"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://concept-generated-visitors-trackbacks.trycloudflare.com/v1"

prereg = json.loads((RUN / "p2_preregistration.json").read_text(encoding="utf-8"))
go = json.loads((RUN / "p2_go_record.json").read_text(encoding="utf-8"))
proto = json.loads((RUN / "a5_review" / "verdict.json").read_text(encoding="utf-8"))
acc = json.loads((RUN / "p2_supplement_accounting.json").read_text(encoding="utf-8"))
ds = json.loads((RUN / "p2_dataset" / "p2_dataset.json").read_text(encoding="utf-8"))
res = json.loads((RUN / "training" / "p2_training_result.json").read_text(encoding="utf-8"))
summ = json.loads((RUN / "training" / "p2_arm_summary.json").read_text(encoding="utf-8"))
up = json.loads((RUN / "upload_receipt.json").read_text(encoding="utf-8"))
audit_p = RUN / "remote_retrieval" / "p2_remote_retrieval_audit.json"
audit = json.loads(audit_p.read_text(encoding="utf-8")) if audit_p.exists() else None
norm = json.loads((RUN / "training" / "p2_normalizer.json").read_text(encoding="utf-8"))
metrics = (RUN / "tables" / "p2_arm_metrics.csv").read_text(encoding="utf-8").splitlines()


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


L = []
A = L.append
A("# P2 结果卷宗（Issue #14：真实 VSPAERO 标签 + 四臂 MAML 公平对照）")
A("")
A("本卷宗用于 A5 对 P2 结果、账本与产物做独立只读复审；不是人类签署，不授权 P3，也不改变任何历史结论。")
A("")
A("## 0. 文件身份")
for name in ("p2_preregistration.json", "p2_go_record.json", "a5_review/verdict.json",
             "p2_supplement_plan.json", "p2_supplement_accounting.json",
             "p2_dataset/p2_dataset.json", "tables/p2_arm_metrics.csv",
             "tables/p2_predictions.csv", "tables/p2_training_curves.csv",
             "training/p2_training_result.json", "training/p2_arm_summary.json",
             "training/p2_normalizer.json", "upload_receipt.json",
             "remote_retrieval/p2_remote_retrieval_audit.json"):
    p = RUN / name
    A("- " + name + ": " + (sha(p) if p.exists() else "ABSENT"))
A("")
A("## 1. 批次身份与授权链")
A("- run_id: " + acc["run_id"] + "；batch_id: " + acc["batch_id"] + "；authorization_id: " + acc["authorization_id"])
A("- Owner 指令：Issue #14 comment 7103901506（P2 执行指令）；m10841 要求执行；P2 物理上限 240 starts")
A("- 预注册 sha256: " + sha(RUN / "p2_preregistration.json"))
A("- GO sha256: " + sha(RUN / "p2_go_record.json") + "；GO 绑定预注册、卷宗、协议 verdict 与全部 source_code_sha256")
A("- 协议 A5 verdict: " + str(proto.get("verdict")) + "（" + str(proto.get("reviewer")) + "，非人类签署，human_signature=" + str(proto.get("human_signature")) + "）")
A("- 补采前数据：旧批次复用 25 条准入标签（R2/G1/G2），8 任务中 3 个任务为零标签；补采 16 starts 后 44 行/44 证书")
A("")
A("## 2. 真实启动与内部成本（本次补采批次）")
A("- 真实 design starts: " + str(acc["physical_solver_starts_actual"]) + " / 上限 16（P2 累计 16/240）；完成 " + str(acc["physical_solver_starts_completed"]) + "；失败 0；重试 " + str(acc["retries_actual"]) + "；并行 " + str(acc["parallelism"]))
A("- 内部 alpha solver cases: " + str(acc["internal_solver_cases_actual"]) + " / 上限 " + str(acc["max_internal_solver_cases"]) + "（每 start 3 个局部迎角探针）")
A("- 准入标签 " + str(acc["admitted_labels"]) + "；NULL " + str(acc["null_labels"]) + "；行级有效率 " + str(acc["valid_label_rate_over_completed"]) + "；总求解墙钟 " + str(acc["wall_clock_s"]) + " s；停止条件 " + str(acc["stops"]))
A("- 本批次解密：16 个 case 全部 SOLVED 且原始 polar 行升力相对误差 <= 1.4e-4（容差 1e-3 未放宽）")
A("")
A("## 3. 数据集与切分（44 行 / 44 证书）")
A("- 任务族：train M140/M160/M200/M202；val M180/M220；test M240/M260（训练/验证/留出按 Owner 指令固定，未因算法表现换任务）")
A("- 每任务 support/query 行：")
for t in ds["tasks"]:
    A("  - " + t["task_id"] + "（" + t["split"] + "，Mach " + str(t["mach"]) + "）：support " + str(t["support"]) + " / query " + str(t["query"]) + "；K=3 可行=" + str(t["k3_support_ok"] and t["k3_query_ok"]))
A("- 数据来源：R2/G1/G2 旧案例只读复用 + P2 补采 16 个案例；历史 task_id 通过显式别名表映射到 8 个 canonical 任务，历史证书/原始文件未被改写")
A("- 去重与冲突：excluded=" + str(len(ds["excluded"])) + " 条（同设计重复、低优先级冲突被高优先级批次取代、同优先级 support/query 冲突整条丢弃）")
A("- 关键披露（post-GO 数据构建器修复）：首次重建时 2 条 R2 低优先级 query 记录与 P2 补采 support 记录在“同设计不同分区”分支被误判为不可解冲突并同时剔除，导致 M180/M202 各少 1 条 support（39 行、K=3 不可行）；修复为“低优先级冲突只剔除低优先级记录”后重建为 44 行，M180/M202 恢复 3+ support。该修复只影响样本分配，不改变已发生的 16 次物理启动与 16 条标签；修复前后数据集 SHA 与行数差异在此披露。")
A("- 数据集合规：K=5 为 NOT_ELIGIBLE（冻结协议仅 d00–d03 四个独立 support 槽位；禁止 query 充数或重复采样）")
A("")
A("## 4. 四臂训练协议")
A("- 臂：" + ", ".join(res["arms"]) + "；K 值 " + str(res["k_values"]) + "；种子 " + str(res["seeds"]) + "；CPU float64")
A("- 网络容量：隐藏层 [32, 32]（条件模型输入 16D 条件特征，其余 12D 设计向量）；最大 60 步；inner_lr 0.05、inner_steps 5、outer_lr 0.01、tasks_per_batch 2")
A("- 归一化：x/y 统计只用 train split 行（fit_observation_ids 共 " + str(len(norm["fit_observation_ids"])) + " 条，全部为 train 任务）；val 只用于早停/选择；test 只评一次")
A("- checkpoint：" + str(len(res["checkpoints"])) + " 个 npz（每臂 × K × 种子），归一化参数 sha256 " + res["normalizer"]["sha256"])
A("- 训练脚本不启动任何物理求解器（physical_solver_starts=0）")
A("")
A("## 5. 结果（MAE/RMSE，N；逐任务逐种子平均）")
for r in summ["rows"]:
    A("- " + r["arm"] + " / " + r["split"] + "：MAE " + ("%.1f" % r["mean_mae_n"]) + " N，RMSE " + ("%.1f" % r["mean_rmse_n"]) + " N（n=" + str(r["n_task_k_seed"]) + " 任务×K×种子）")
A("- 逐任务逐种子明细见 tables/p2_arm_metrics.csv；逐 query 预测见 tables/p2_predictions.csv；训练曲线见 tables/p2_training_curves.csv 与 figures/p2_training_curves.png")
A("")
A("## 6. 负结果与诊断（不隐藏）")
A("- FOMAML 在 K=3 明显退化：外循环损失在部分种子的后段从约 0.22 升到 0.43，K=3 的留出 MAE 反而高于随机初始化；本轮 FOMAML 超参数未调（未用 test/val 反调），该负结果按原样保留")
A("- 任务条件预训练在所有 split 上最好；普通联合预训练次之；随机初始化居中偏弱")
A("- 离线候选排序诊断（training/p2_offline_selection.json）：按预测最小 Di_N 选设计的遗憾在 M180/M240 可计算，M220/M260 只有 1 个 query，遗憾恒为 0；该诊断不是在线优化，也不是 P3 的 BO/DE 对比")
A("- 不得把 P1 的 196 对 18 内部工况差异记作 MAML 收益；本卷宗未做该比较")
A("")
A("## 7. 产物上传与远端回读（A4）")
A("- 上传 commit: " + str(up.get("local_commit")) + "；文件 " + str(up.get("file_count")) + "，字节 " + str(up.get("total_bytes")) + "；readback checked=" + str((up.get("readback") or {}).get("checked")) + "，missing=" + str((up.get("readback") or {}).get("missing")) + "，bad=" + str((up.get("readback") or {}).get("bad")))
if audit:
    A("- 远端独立复核（GitHub blob API 原始字节）：remote head " + audit["remote_head"] + "，case 目录 " + str(audit["remote_case_count"]) + "，逐 case 通过 " + str(audit["cases_ok"]) + "，bad=" + str(len(audit["bad"])) + "，A4 判据=" + str(audit["a4_criteria_met"]))
    A("- 复核方法：" + audit["method"])
    A("- 每条标签均从远端 .polar 原始行按证书 alpha 重算 CL/CDi 并验证 Di_N = q·Sref·CDi 恒等式；同时验证证书 raw_sha256 等于远端 polar 字节 SHA256")
else:
    A("- 远端独立复核缺失（视为 FAIL）")
A("")
A("## 8. 已披露偏差与限制")
for d in [
    "A5 为 deepseek-flash 单发只读审查，非人类签署；本卷宗不请求也不构成 P3/MAML 授权",
    "标签同机保存（Owner 已豁免异机独立故障域备份）；未做风洞/物理验证；physics_validated=false；fuel_burn_kg=null",
    "目标为同升力（tol 1e-3）下翼面诱导阻力 Di_N=q·Sref·CDi；不含整机阻力/油耗；LF-M2.02 未验证",
    "样本量小（44 行、2 个留出任务）；不宣称统计显著或普遍泛化；不把种子当独立任务",
    "post-GO 代码变更已披露：p2_data.py 去重优先级修复、p2_upload.py 远端校验改为逐层 tree 下钻（修复 recursive tree 截断）、新增 p2_train/p2_figures/p2_metadata/verify_p2_remote 脚本；这些变更不新增物理、不改变已发生的 16 次启动",
    "M140 迎角接近 G2 stage-1 极曲线上界（9.52–9.76°），补采探针已夹紧在 bracket 内；该批次 1.0 标签率不构成对其它 Mach 的保证",
    "P1 仅为单任务 pilot，不作为正式训练批；P2 未使用 P1 的 6 次启动作为训练样本",
]:
    A("- " + d)
A("")
A("## 9. 请 A5 判断的关键点")
A("1. 账本是否自洽：16 starts / 16 completed / 48 internal / 16 标签 / 0 NULL / 0 retry")
A("2. 数据切分与去重是否可接受：44 行、8 任务、support/query 无泄漏、K=5 NOT_ELIGIBLE、post-GO 去重修复是否披露充分")
A("3. 四臂对照是否公平：同一标签、同一归一化（仅 train 拟合）、同一容量/预算/种子、未用 test 调参")
A("4. 远端回读与独立复算是否支撑 A4")
A("5. 结果与负结果（FOMAML 退化）是否被如实报告，统计主张是否被限制在样本范围内")
A("6. 是否放行 P2 结果（本卷宗不请求 P3 GO；P3 需另行预注册与新的 GO）")
dossier = "\n".join(L) + "\n"
p = RUN / "p2_a5_result_dossier.md"
p.write_text(dossier, encoding="utf-8", newline="\n")
dh = sha(p)
print("dossier", len(dossier), dh, flush=True)

key = yaml.safe_load(Path(r"C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8"))["refs"]["SUB2_API_KEY"]
prompt = """You are A5, an independent read-only reviewer. No tools. Review only the dossier text below; never invent data.
Return ONLY one valid compact JSON object, no markdown, ending with }:
{"reviewer":"deepseek-flash","review_type":"independent_single_shot_result_review","dossier_sha256":"__DOSSIER_SHA__","verdict":"P2_RESULT_REVIEW_PASS"|"P2_RESULT_CHANGES_REQUIRED"|"P2_RESULT_REJECT","gate_verdicts":{"P2_ACCOUNTING":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_DATASET_SPLIT":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_ARM_FAIRNESS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_REMOTE_RETRIEVAL":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_STATISTICAL_CLAIMS":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL","P2_BOUNDARIES":"PASS"|"PASS_WITH_DISCLOSURE"|"FAIL"},"evidence_checked":["..."],"findings":[{"severity":"critical|major|minor|info","finding":"...","evidence":"..."}],"limitations":["..."],"scope":"P2 result review only; not a human signature; does not authorize P3/MAML","signature":"deepseek-flash independent A5 review; not a human signature"}
Hard limits: at most 8 findings, each finding and evidence <= 240 characters; at most 6 limitations; scope <= 300 characters. JSON must be complete.
Judge strictly: (a) accounting 16 starts/16 completed/48 internal/16 labels/0 nulls/0 retries consistent; (b) dataset split has no support/query leakage, 8 tasks fixed, K=5 ineligible, and the post-GO dedupe fix disclosed honestly; (c) four arms share labels, train-only normalization, capacity, budget and seeds, with no test tuning; (d) remote blob readback plus independent Di_N recompute adequate; (e) negative FOMAML result reported and statistical claims limited to 44 rows / 2 held-out tasks; (f) boundaries: no physical validation, same host, no P3 authorization.

DOSSIER_BYTE_IDENTITY: __DOSSIER_SHA__
DOSSIER:
""" + dossier
payload = {"model": "deepseek-flash",
           "messages": [{"role": "system", "content": "You are a strict independent reviewer. Output only valid compact JSON."},
                        {"role": "user", "content": prompt}],
           "max_tokens": 20000, "temperature": 0.1, "stream": True,
           "chat_template_kwargs": {"thinking": False}}
req = urllib.request.Request(BASE + "/chat/completions", data=json.dumps(payload).encode("utf-8"), method="POST",
                             headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                      "Accept": "text/event-stream"})
chunks, raw = [], []
status = 0
try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        status = resp.status
        for line in resp:
            s = line.decode("utf-8", "replace").strip()
            if not s:
                continue
            raw.append(s)
            if not s.startswith("data:"):
                continue
            data = s[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            for ch in obj.get("choices", []):
                if ch.get("delta", {}).get("content"):
                    chunks.append(ch["delta"]["content"])
except urllib.error.HTTPError as e:
    status = e.code
    print("HTTP_ERROR", e.code, e.read().decode("utf-8", "replace")[:1500], flush=True)
except Exception as e:  # noqa: BLE001
    print("EXC", type(e).__name__, str(e)[:1500], flush=True)

text = "".join(chunks)
(OUT / "raw_lines.txt").write_text("\n".join(raw), encoding="utf-8", newline="\n")
(OUT / "verdict_raw.txt").write_text(text, encoding="utf-8", newline="\n")
print("http", status, "chars", len(text), flush=True)
if not text:
    raise SystemExit(3)
s0, s1 = text.find("{"), text.rfind("}")
v = json.loads(text[s0:s1 + 1] if s0 >= 0 and s1 > s0 else text)
_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
v.update(model="deepseek-flash", reviewer="deepseek-flash", reviewed_utc=_now, review_recorded_utc=_now,
         dossier_path=str(p), dossier_sha256=dh, run_id=acc["run_id"], batch_id=acc["batch_id"],
         authorization_id=acc["authorization_id"], tool_access="NONE_SINGLE_SHOT_DOSSIER_STREAM",
         human_signature=False,
         scope_of_this_review="P2 result review only; not a human signature; does not authorize P3/MAML")
(OUT / "verdict.json").write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(v, ensure_ascii=False, indent=2)[:6000], flush=True)
