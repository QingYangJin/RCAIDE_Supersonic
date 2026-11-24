"""Build the O1 result dossier: what was spent, what was produced, and what the numbers do and do not support."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01")
OUT = RUN / "o1_a5_result_dossier.md"
ARMS = ("SOBOL_BO", "COND_SUPERVISED_KSHOT_BO", "COND_FOMAML_KSHOT_BO")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def j(p):
    return json.loads((RUN / p).read_text(encoding="utf-8"))


res = j("o1_result.json")
pre = j("o1_preregistration.json")
go = j("o1_go_record.json")
bc = j("o1_batch_close.json")
sup = j("o1_shared_support.json")
rec = j("o1_a4_recompute.json")
gid = j("o1_a4_geometry_identity.json")
cost = j("o1_cost_reconciliation.json")
up = j("upload_receipt.json")
rs = j("o1_resource.summary.json")
proto = j("a5_review/verdict.json")
arms = {a: j("o1_arm_%s.json" % a) for a in ARMS}

L = []
A = L.append

A("# O1 三臂结果卷宗（Issue #15 §6：真实 support 上的三种热启动，等真实成本对照）")
A("")
A("本卷用于 A5 对本批次**结果**做独立只读复核：花费是否与 GO 一致、每个数是否可从磁盘与远端 raw 重算、"
  "三臂是否真的只差热启动规则、结论是否只说了数据支持的话。本卷不授权任何后续阶段，也不是人类签署。")
A("")

A("## 0. 文件身份（本卷引用的每一个字节）")
for name in ("o1_result.json", "o1_preregistration.json", "o1_go_record.json", "o1_batch_close.json",
             "o1_shared_support.json", "o1_a4_recompute.json", "o1_a4_geometry_identity.json",
             "o1_cost_reconciliation.json", "o1_resource.summary.json",
             "a5_review/verdict.json", "o1_binding_verification.json",
             "tables/o1_three_arm_endpoint.csv", "tables/o1_anytime_trace.csv",
             "tables/o1_solver_case_ledger.csv", "tables/o1_best_design_vs_baseline.csv",
             "tables/o1_all_designs_all_arms.csv",
             "figures/figure_manifest.json", "figures/o1_three_arm_endpoint.png",
             "figures/o1_anytime_comparison.png", "figures/o1_resource_usage.png",
             "final_aircraft/figures/figure_manifest.json",
             "final_aircraft/figures/cl_alpha_and_cdi_alpha_all_arms.png",
             "final_aircraft/figures/geometry_overlay_all_arms.png",
             "o1_not_claimed_addendum.json"):
    p = RUN / name
    A("- %s: %s (%d B)" % (name, sha(p) if p.exists() else "ABSENT", p.stat().st_size if p.exists() else 0))
for a in ARMS:
    p = RUN / ("o1_arm_%s.json" % a)
    A("- o1_arm_%s.json: %s (%d B)" % (a, sha(p), p.stat().st_size))
A("")

A("## 0b. 本卷在此前轮次里被指出的问题，以及现在磁盘上是什么样")
A("本卷不叙述自己的修订史，只陈述两件可核对的事：**这一轮之前被指出过哪些实质问题**，以及**这些问题现在在磁盘上的状态**。"
  "轮次账本（哪一轮、绑哪个字节、有没有留下文件）单独放在 o1_result_review_rounds.json，由 scripts/o1_result_rounds.py 从 "
  "a5_result_review/rounds/ 与 a5_result_review/history/ 的实际文件生成——卷宗里讲版本故事，就等于让卷宗断言一件读者查不到的事，不做。")
A("- 注意：o1_result_review_rounds.json 是**每次审查后重新生成的活索引**，因此它不在 §0 的固定身份清单里；"
  "卷宗钉哈希的对象是冻结产物，活索引不是。它的可信度由生成脚本 scripts/o1_result_rounds.py 与它引用的 rounds/ 文件本身提供。")
A("")
A("| # | 此前被指出的问题 | 现在磁盘上的状态 |")
A("|---|---|---|")
A("| 1 | critical：本卷哈希与协议 verdict 里绑的哈希不同，疑为字节漂移 | **不是漂移，是设计使然**：协议卷宗 `o1_a5_dossier.md` 与结果卷宗 `o1_a5_result_dossier.md` 是两个不同文件，哈希必然不同。§1 有区分说明。 |")
A("| 2 | major：§7 称每个 case 目录都带 admission_certificate.json，实测 18 个 coarse 目录没有 | 已按目录类别分别陈述：36 个付费目录 = 18 coarse + 18 refine；证书每**设计**一张、只落在 refine；另有 4 个预检/干跑目录 0 物理、无 .polar。判据改为机械的「有 .polar 与 case_result.json 才是付费工况」。 |")
A("| 3 | major：o1_result.json 的 cost.note 写「3 倍 support 账单」，而 108 = 3×36 是整张账单乘 3 | §2 已明确写出该 note 的措辞本身是错的，并给出正确合同读数 3×6+30=48；结果文件不改（其 sha 已被 batch_close 与上传回执引用），差异由 `o1_cost_reconciliation.json` 独立对账。 |")
A("| 4 | minor：o1_result.json 的 not_claimed 只有四项，没有「热启动未胜过 Sobol」这一条 | 结果文件不改（理由同上），补充条款落到 `o1_not_claimed_addendum.json`：三条 additional_not_claimed 各带原因与真值所在文件。结果文件里的遗漏如实保留、不隐藏。 |")
A("")
A("**一处必须自己承认的治理缺陷**：结果级审查的 harness 第一版把 verdict 直接写进 `a5_result_review/verdict.json`，"
  "于是每一轮都静默删掉上一轮的 verdict 文件；其中一轮（CHANGES_REQUIRED，绑 ad65e57f…）的原始文件因此**已经不在磁盘上**。"
  "该轮已列在 o1_result_review_rounds.json 的 rounds_with_no_surviving_file 里，标 NONE_ON_DISK，并且**不作为任何证据使用**。"
  "harness 已改为每轮先写 `rounds/verdict_<stamp>_<dossier16>.json` 与 `raw_lines_<stamp>.txt` 再替换活路径；"
  "绑旧字节的 verdict 仍由 `scripts/o1_result_retire_stale.py` 复制进 history 后从活路径移除，从不删除。")
A("")

A("## 1. 授权链（这批次凭什么可以花真钱）")
A("- run_id: %s；batch_id: %s；authorization_id: %s" % (pre["run_id"], pre.get("batch_id"), pre.get("authorization_id")))
A("- 协议 A5 verdict: %s（reviewer %s，human_signature=%s，dossier %s）" % (
    proto.get("verdict"), proto.get("reviewer"), proto.get("human_signature"),
    str(proto.get("dossier_sha256"))[:16]))
A("- GO: %s，go_sha256 %s，签发 %s，签发者 %r" % (
    go.get("go_issued"), str(go.get("go_sha256"))[:16], go.get("go_issued_utc"), go.get("issued_by")))
A("- GO 授权额度: %s" % json.dumps(go.get("authorized_remaining"), ensure_ascii=False))
A("- GO 预注册绑定: preregistration_sha256=%s，caps=%s" % (
    str(go.get("preregistration_sha256"))[:16],
    json.dumps(go.get("caps"), ensure_ascii=False)[:300]))
A("- 字节绑定说明: %r" % go.get("byte_binding"))
A("- **本仓库有两种卷宗，哈希必然不同，不要当成字节漂移**：①协议卷宗 o1_a5_dossier.md（协议级 verdict 绑的是它，"
  "%s）；②本文件 o1_a5_result_dossier.md（结果级审查对象，本卷就是它）。结果级 harness 会自己 sha256 本卷并覆写 "
  "verdict.dossier_sha256，同时保留审查者声称值（dossier_sha256_claimed_by_reviewer）。" % str(proto.get("dossier_sha256"))[:16])
cf = pre.get("carried_forward", {})
A("- O1 之前已花（结转，见 o1_preregistration.json carried_forward）: 优化器批次 %s（designs/starts/internal，authorization 口径），"
  "O0-FINAL 复验 %s starts / %s internal；两项均已花尽，O1 不新增任何优化器设计" % (
    json.dumps(cf.get("optimizer", {}).get("authorization_spend"), ensure_ascii=False),
    cf.get("final_verification", {}).get("starts"), cf.get("final_verification", {}).get("internal")))
A("")

A("## 2. 真实花费（物理 / 等价 / 内部，三种口径分开）")
C = res["cost"]
A("- 物理 solver starts: **%d**（每设计 2 笔：coarse 7 点 + refine 13 点，各 1 start）" % C["physical_solver_starts_actual"])
A("- o1_result.json 自报 equivalent_solver_starts: **%d**，其 note 原文为 %r" % (
    C["equivalent_solver_starts"], C["note"]))
A("- **该 note 的措辞本身是错的，此处如实指出**：108 = 3 x 36（整张物理账单乘 3），不是 3 x 6（support 只占 6 笔）。"
  "预注册的成本模型只把 shared support 三设计乘 3，正确合同读数是 3x6 + 30 = 48。结果文件不改（其 sha 已被 "
  "o1_batch_close.json 与上传回执引用，改它会让已发布的证据链失效），差异由 o1_cost_reconciliation.json 独立对账并披露。")
crn = cost.get("recomputed_numbers", {})
A("- 独立对账（o1_cost_reconciliation.json）：合同读数等价 starts **%s**，物理 **%s**，三臂合计计费 internal **%s**，"
  "cap_checks %d 条全部 PASS=%s，且明写不改 o1_result.json（其 sha 已被 batch_close 与上传回执引用）" % (
    crn.get("equivalent_total_contract_reading"), crn.get("physical_total"),
    crn.get("internal_equivalent_total_charged_to_the_three_arms"),
    len(cost.get("cap_checks") or []), cost.get("all_cap_checks_pass")))
A("- 差异方向: 结果文件按 3x 整张账单算（%d），而预注册的成本模型只把 **shared support 三设计**乘 3；"
  "合同读数 = 3x6 + 30 = 48。高估成本不美化任何一臂，主终点是 Di 与 starts，不是钱。" % C["equivalent_solver_starts"])
A("- 每臂内部工况: 160 = 8 设计 x（7 coarse + 13 refine），即 shared support 3 设计（60）按全价计入每臂 + 5 个本臂设计（100）")
A("- 共享 support: starts %s / internal %s，三设计一次求解、三臂各计一次等价账单" % (
    sup.get("starts"), sup.get("internal")))
A("- 资源: sample_count %s，cpu_busy_mean %s，cpu_busy_max %s，memory_load_mean %s，"
  "phys_used_mean_bytes %s，wall_clock_s %s（整机口径，非本进程独占）" % (
    rs.get("sample_count"), rs.get("cpu_busy_mean"), rs.get("cpu_busy_max"),
    rs.get("memory_load_mean"), rs.get("phys_used_mean_bytes"), rs.get("wall_clock_s")))
A("")

A("## 3. 三臂端点（主终点，全部来自真实 VSPAERO 准入证书）")
pe = res["primary_endpoint"]
A("- baseline（shared support 内预指定）: Di_N = %.6f" % pe["baseline_di_n"])
A("- 目标: Di_N <= %.6f（baseline x (1 - %.4f)，比 1e-3 升力容差高一个量级）" % (
    pe["target_di_n"], pre["budgets"].get("target_improvement_fraction", 0.001)))
A("")
A("| 臂 | 设计 | 等价 starts | 内部工况 | 准入 | 最佳 Di_N | 最佳 tag | delta vs baseline | delta% | 达标 | 达标用 starts |")
A("|---|---|---|---|---|---|---|---|---|---|---|")
for a in ARMS:
    v = res["arms"][a]
    A("| %s | %d | %d | %d | %d | %.4f | %s | %.4f | %.4f%% | %s | %s |" % (
        a, v["designs"], v["starts"], v["internal"], v["admitted"], v["best_feasible_di_n"],
        v["best_feasible_tag"], v["improvement_n"], v["improvement_fraction"] * 100.0,
        v["reached_target"], v["equivalent_starts_to_target"]))
A("")
A("三臂预算完全相同（每臂 8 设计 / 16 等价 starts / 160 内部工况，三臂合计 24 / 48 / 480），"
  "内部工况上限先于 12 设计与 24 starts 生效，这一点在预注册里就写明，不是事后解释。")
A("")

A("## 4. 逐设计 anytime（每臂 8 步，全部 FEASIBLE_ADMITTED）")
for a in ARMS:
    A("")
    A("### %s（warm_start_kind = %s）" % (a, arms[a]["warm_start_meta"].get("warm_start_kind")))
    A("| step | role | tag | design_id | cum starts | cum internal | Di_N | best_so_far |")
    A("|---|---|---|---|---|---|---|---|")
    for r in arms[a]["anytime"]:
        A("| %s | %s | %s | %s | %s | %s | %.4f | %.4f |" % (
            r.get("step"), r.get("role"), r.get("tag"), r.get("design_id"),
            r.get("cumulative_starts"), r.get("cumulative_internal"),
            r["di_n"], r.get("best_so_far", r["di_n"])))
A("")

A("## 5. 热启动到底给了什么（模型排序的预测 vs 真实）")
for a in ARMS:
    ws = [r for r in arms[a]["records"] if r.get("role") == "warm_start"]
    A("")
    A("- %s：" % a)
    for r in ws:
        A("  - %s design=%s predicted_di_n=%s actual_di_n=%.4f" % (
            r.get("tag"), r.get("design_id"), r.get("predicted_di_n"), r["di_n"]))
A("")
A("读法（诚实）：两个 K-shot 臂的模型排序在预测绝对水平上系统性偏乐观（预测比实测低约 6 到 23 kN），"
  "而在 3 选 1 的排序上也没有把最好的那个排第一 —— supervised 臂预测序 d03<d04<d05，实测最好的是 d05；"
  "FOMAML 臂预测序 d03<d04<d05，实测 d03<d05<d04。两臂的 adaptive 阶段随后收敛到同一对设计"
  "（d06 9a82dc1947bf43f0、d07 93cfb7db5e6fcd95），因此最终端点逐位相同。这不是元学习没用的证明，"
  "也不是模型排序有用的证明：它说明在 3 条真实 support 的预算下，模型排序没有提供可测的排序优势。")
A("")

A("## 6. A4 独立复算（不读结果文件，从远端 raw 重算）")
A("- o1_a4_recompute.json：method = %r" % rec.get("method"))
A("- 检查 case 数 %s，不一致 %s，commit %s" % (rec.get("case_count"), rec.get("mismatch_count"), rec.get("commit")))
A("- 几何身份 o1_a4_geometry_identity.json：pair_count %s，identity_proved %s，all %s" % (
    gid.get("pair_count"), gid.get("identity_proved_count"), gid.get("all_identity_proved")))
A("- 几何身份两条腿：leg_1 用交付 x12 在冻结代码路径重建 .vspgeom，其 sha256 必须等于付费 case plan 记录的 geometry_sha256"
  "（VSPAERO 只吃 .vspgeom，故相等即证明求解器飞的就是交付构型，StopBeforeRun=1，0 物理 starts）；"
  "leg_2 比对交付 .vsp3 与 case .vsp3 的规范化 XML（屏蔽 OpenVSP 元素 ID），判据 identical_modulo_element_ids_and_tessellation。")
A("- 已披露残余差异：交付几何用 OpenVSP 默认剖分，付费 case 用 tess_u=12/tess_w=25，"
  "故 Tess_U/Tess_W/MaxGrowth/SmallPanelW 不同，记为 non-geometric differences，不隐藏。")
A("")

A("## 7. 远端可回读（上传与回读）")
A("- 本批推送 commit %s，file_count %s，total_bytes %s，push_ok %s，"
  "readback checked %s / missing %s / bad %s，readback manifest %s" % (
    up.get("local_commit"), up.get("file_count"), up.get("total_bytes"), up.get("push_ok"),
    (up.get("readback") or {}).get("checked"), (up.get("readback") or {}).get("missing_count"),
    (up.get("readback") or {}).get("bad_count"),
    str((up.get("readback") or {}).get("manifest_sha256"))[:16]))
A("- 说明（为什么本卷不钉 upload_receipt.json 的哈希）：回执是每次推送后重写的，"
  "而本卷要在推送前定稿才能随包一起上远端，钉死回执哈希会让本卷在推送那一刻自行失效。"
  "所以本卷只引用 commit 与计数；包内**逐字节身份**由上传器生成的 data_manifest.json 与 SHA256SUMS.txt 承担"
  "（两者与包同 commit，可独立回读核对），回执只承担「推送是否成功、回读是否 0 缺失 0 坏」这一个陈述。")
A("- **三类目录必须分开，别把「目录数」当「start 数」**（本批实测，逐目录核对过）：")
A("  - 真实付费 case 目录 **36 个** = 18 个 coarse + 18 个 refine。coarse 目录 28 文件：.polar、.vspgeom、"
  "case_result.json、plan.json、task_spec.json、solver 产物与日志，**没有 admission_certificate.json**——"
  "准入证书是每个**设计**一张，落在它的 refine 目录里。refine 目录 37 文件：上述全部 + admission_certificate.json。")
A("  - 预检/干跑目录 **4 个**（PREFLIGHT/o1-s00-coarse 与 DRY_SOBOL_BO、DRY_COND_SUPERVISED_KSHOT_BO、"
  "DRY_COND_FOMAML_KSHOT_BO 各 1 个 o1-dry-coarse）：每个 11 文件、**有 .vspgeom 但没有 .polar、没有 case_result.json**，"
  "即 0 物理求解、0 花费，仅用于在花真钱前验证几何与流程能起得来。它们不是 start，也不该被计费。")
A("- 因此从 GitHub 单独重取任一工况的判据是：该目录里有 .polar 与 case_result.json。满足这一点的是 36 个付费目录；"
  "4 个预检/干跑目录不满足，这正是它们不构成花费的机械证据。Di = q*Sref*CDi 只能从 refine 目录的 "
  "admission_certificate.json 取到的 alpha 对应 polar 行重算（coarse 的 7 点只用于定位 alpha 窗口，不产生证书）。")
A("")

A("## 8. 这一批**不能**声称什么")
A("- 不能声称 MAML 优于 supervised 元学习：两臂端点逐位相同，FOMAML 只在 anytime（达标用 8 与 12 starts）上不同，n=1 任务、1 个配对。")
A("- 不能声称热启动优于 Sobol：本任务上 Sobol+BO 的 2.687% 高于两个 K-shot 臂的 0.813%。")
A("- 不能声称全局最优、regret 或有界性（o1_result.json 的 not_claimed 已列这四项）。")
A("- 不能声称气动验证：physics_validated=false，VSPAERO_INTERNAL_ONLY，燃料/任务级结论为零。")
A("- 三臂都在同一共同预算处被截断，不是各自独立收敛；adaptive_designs 每臂 2，第 3 个自适应设计就没有预算（160 内部工况上限）。")
A("- **文件级的残余缺口（已知、未修、写在这里而不是藏起来）**：o1_result.json 的 not_claimed 只有四项，"
  "没有「热启动未胜过 Sobol」这一条；该条在 o1_not_claimed_addendum.json 里，也在本卷本段里。"
  "也就是说，**只读 o1_result.json 的人拿不到这条限制**。为什么不在结果文件里补：它的 sha256 已被 "
  "o1_batch_close.json、A4 复算与上传回执引用，改一个字节会让已经发布并被引用的证据链全部失效，"
  "代价大于收益。为什么不声称这是「已修好」：因为确实没修好，只是被披露。这个缺口的风险是有限的——"
  "结果文件并没有任何一处声称热启动更好，缺的是**否证**那一句，而不是**错证**。")
A("- 结论只覆盖 1 个任务（O1-M190，Mach 1.9 / 18288 m / CL 0.205426）；预注册里另一个任务 O1-M210 未跑，"
  "batch_close 的 pairings_executed 只写 [O1-M190]，如实披露。")
A("")

A("## 9. 要审查者判的八问")
A("1. 真实花费是否与 GO 授权一致，且没有任何一笔未入账的 start？（对账文件给了 108/48/36 三个数；同时判两件事："
  "差异是否被如实披露，以及 o1_result.json 里那句 cost.note 的**措辞本身是否错误**——本卷 §2 已认定它错了，"
  "请独立判这个认定成不成立，而不是只看「有没有披露」。）")
A("2. 每臂 8 设计 / 16 等价 starts / 160 内部工况是否真的相同，是否存在某臂被偷偷多给预算或候选？")
A("3. 主终点算术是否正确：baseline 135505.77916651228，target = baseline x (1-0.001) = 135370.27338734578，"
  "各臂 best 是否真的是该臂 anytime 序列的最小值？")
A("4. 三臂是否真的只差热启动规则：同一 3 条 support、同一 256 候选池（无目标值）、同一 GP 后端与超参、"
  "同一 alpha 配方、同一准入门、同一几何合同？")
A("5. A4 复算与几何身份是否独立于结果文件（不读 o1_result.json 也能得到同样的 Di 与同一构型）？")
A("6. 结论是否被限制在数据支持的范围：是否把两臂打平说成 MAML 更好，或把截断说成收敛？")
A("7. 本卷描述的每一个文件是否真的存在于磁盘、hash 是否与卷内所写一致，且可从 GitHub 回读？")
A("8. o1_result.json 的 not_claimed 只列四项、缺「热启动未胜过 Sobol」一条（结果文件不改，见 §0b 第 4 行）；"
  "补充条款在 o1_not_claimed_addendum.json。请判：这份补充是否真的把缺口补上了，还是只是把一个遗漏挪到了另一个文件？"
  "（即：只读 o1_result.json 的人仍然拿不到这条限制——这个残余风险是否被本卷明确写出。）")

A("")
A("## 10. 本卷自身的哈希约定")
A("本卷由 scripts/o1_build_result_dossier.py 生成；审查 harness 会在读到本卷后自己 sha256 一次并覆写 verdict 里的 dossier_sha256，"
  "同时保留审查者自己声称的值以便审计。verdict 落在 a5_result_review/verdict.json。")
A("")

text = "\n".join(L)
OUT.write_text(text, encoding="utf-8", newline="\n")
print(json.dumps({"path": str(OUT), "bytes": OUT.stat().st_size,
                  "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest()}, ensure_ascii=False))
