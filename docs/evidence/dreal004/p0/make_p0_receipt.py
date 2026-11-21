
"""Generate the Chinese P0 receipt draft (Issue #14) from live files.

Backtick characters in the markdown are written as the placeholder '¶' and
replaced at the end, so this file itself contains no literal backticks.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

P0 = Path(__file__).resolve().parent
OUT = P0 / "p0_receipt_draft_20261122.md"
TICK = chr(96)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tick(s: str) -> str:
    return s.replace("¶", TICK)


verdict = json.loads((P0 / "a5_review_p0_verdict.json").read_text(encoding="utf-8"))
tests = json.loads((P0 / "p0_test_summary.json").read_text(encoding="utf-8"))
halt = json.loads((P0 / "g2_halt_reference.json").read_text(encoding="utf-8"))

files = ["p0_a5_dossier.md", "p0_test_summary.json", "p0_test_log.txt",
         "g1_alpha_replay.json", "12d_variable_response_audit.json",
         "a2_g1_baseline_endpoints.json", "p1_p2_p3_preregistration.json",
         "p0_protocol_freeze_20261122.md", "a5_review_p0_verdict.json",
         "g2_halt_reference.json"]

L = []
w = L.append
w("# Issue #14 P0 阶段回执（D-REAL-EXP-002，2026-11-22）")
w("")
w("**性质声明**：本回执只覆盖 P0（代码 / 零物理 replay / 12D 审计 / A2 主终点分析器 / 协议冻结）。")
w("**不是 P1 授权**，**不是新的物理结果**，也不改写 G1/G2 历史。P1 起仍需专门的 A5 批次方案审查 + Lead 新 GO。")
w("")
w("## 1. 零物理事实")
w("")
w("- ¶physical_solver_starts_actual = 0¶，¶internal_solver_cases_actual = 0¶，¶labels_created = 0¶。")
w("- 本轮没有启动任何 VSPAERO 进程；replay 只读取 G1 已有的 ¶.polar¶ 原始行。")
w("- 测试解释器 ¶%s¶；求解器身份只登记不调用。"
  % tests["python"])
w("")
w("## 2. 已交付代码与证据")
w("")
w("| 项目 | 结果 |")
w("|---|---|")
w("| A1 ¶AdaptiveAlphaSolver¶ | 注入式真实求解回调；每次 probe 计 1 internal case；割线插值夹在 bracket 内；非单调返回 ¶INVALID_POLAR¶；预算耗尽 ¶BUDGET_EXHAUSTED¶；插值目标不计 raw |")
w("| A1 ¶polar_rows¶ 解析 | 按表头解析 Beta/Mach/AoA/CLtot/CDo/CDi/CDtot；无表头/无行报错；缺失行返回 ¶REPLAY_ROW_NOT_AVAILABLE¶ |")
w("| G1 零物理 replay | 24 case：raw 命中 8、需新 alpha 行 7、无 bracket 8、缺输入 1；旧固定扫描 391 internal vs 自适应 replay 329 probes；新标签 0 |")
w("| 12D 响应审计 | 15 个变量全部真实进入 VSPAERO 输入；56 个 response pair 的 deck SHA 均不同 |")
w("| A2 主终点分析器 | N_first_feasible / best_feasible_Di_N(B) / anytime / hit rate / simple_regret(null) / cost_to_target；G1 复算首个可行第 10 个 design（170 internal），点级可行率 8/24=0.3333，internal 391 与 batch accounting 一致 |")
w("| 测试 | %d 项，failures %d，errors %d，skipped %d，successful=%s |"
  % (tests["tests_run"], tests["failures"], tests["errors"], tests["skipped"],
     tests["was_successful"]))
w("")
w("分支 ¶research/dreal004-alpha-adaptive-meta-sampling¶，基线 ¶af9871c¶。")
w("代码提交 ¶db44071¶；证据目录 ¶docs/evidence/dreal004/p0/¶。")
w("")
for name in files:
    p = P0 / name
    w("- ¶docs/evidence/dreal004/p0/%s¶ sha256 ¶%s¶" % (name, sha(p)))
w("")
w("## 3. A5 独立审查结论")
w("")
w("- reviewer：¶deepseek-flash¶，单发只读、无工具；**非人类签署**，不替代 Owner 签字。")
w("- verdict：**¶%s¶**（reviewed %s）。" % (verdict["verdict"], verdict["reviewed_utc"]))
w("- gates：" + "；".join("¶%s¶=%s" % (k, v)
                          for k, v in verdict["gate_verdicts"].items()))
w("- findings：" + "；".join("[%s] %s" % (f["severity"], f["finding"])
                             for f in verdict["findings"]))
w("- 非阻断披露：V01/V02 在 β=0 任务族中为 passive 维度，不声称其 12D 响应；Mach 1.6 零 G1 标签、6 个无 bracket；无独立 Di_N 参考，¶simple_regret¶ 保持 null。")
w("")
w("## 4. 冻结协议（P1–P3 预注册）")
w("")
w("- 任务 split 冻结：train M140/M160/M200/M202，val M180/M220，test M240/M260；support ¶d00–d03¶、query ¶d04–d07¶。")
w("- P1（**未授权**）：Mach 2.02，设计 ¶d00/d01/d04/d07¶，≤12 design starts、≤3 starts/design、≤36 internal cases，¶tol_CL=1e-3¶ 不放宽；需 A5 批次方案审查 + Lead 新 GO。")
w("- P2（未授权）：≤240 新 starts；每 train 任务 ≥4 条真实准入标签；FOMAML/普通预训练/16D 上下文预训练/随机初始化；负迁移照实报告。")
w("- P3（未授权）：≤384 新 starts；等预算配对比较 Random/LHS/Sobol/预训练/FOMAML；输出 B=4/8/16/32/64/128 anytime 曲线。")
w("- 主终点、公平性、统计、禁止项见 ¶p1_p2_p3_preregistration.json¶ 和中文 ¶p0_protocol_freeze_20261122.md¶。")
w("")
w("## 5. 上一阶段（G2）中止真相（不改写、不签发 G2 回执）")
w("")
w("- B01：%d starts，%d completed，%d internal，%d 标签，%d null。"
  % (halt["b01"]["charged_starts"], halt["b01"]["completed"],
     halt["b01"]["internal_solver_cases"], halt["b01"]["admitted_labels"],
     halt["b01"]["null_labels"]))
w("- B02：%d starts，%d completed，%d internal，%d 标签，%d null，有效率 %.1f%%，B02 上限 %d，剩 %d 未用。"
  % (halt["b02"]["charged_starts"], halt["b02"]["completed"],
     halt["b02"]["internal_solver_cases"], halt["b02"]["admitted_labels"],
     halt["b02"]["null_labels"], 100 * halt["b02"]["valid_label_rate"],
     halt["b02"]["b02_starts_max"], halt["b02"]["unused_b02_starts"]))
w("- 累计 **%d/%d** starts；G2 MAML 未运行，G2 回执未签发。G1 24 starts / 8 labels / 34.78%% 永久保留。"
  % (halt["cumulative_starts"], halt["g2_cap"]))
w("")
w("## 6. 门禁与下一步")
w("")
w("- P0：A5 ¶P0_CODE_AND_PROTOCOL_PASS¶ 已取得（非人类）；**P0 已完成**。")
w("- P1：未授权。拟定 ¶AUTH-DREAL004-P1-20261122-01¶ / ¶DRECOVER001-P1-20261122-01¶（Mach 2.02，4 designs，≤12 starts，每 ≤8 starts 上传+远端回读，连续 2 次 solver 失败或墙钟 3600s 停止）。")
w("- P2/P3：未授权，须 P1 验收后另行 A5 + Lead 分批 GO。")
w("")
w("## 7. GitHub 复核入口")
w("")
w("- 分支：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/research/dreal004-alpha-adaptive-meta-sampling")
w("- P0 证据目录：https://github.com/QingYangJin/RCAIDE_Supersonic/tree/research/dreal004-alpha-adaptive-meta-sampling/docs/evidence/dreal004/p0")
w("- G2 中止说明：Issue #13 评论 https://github.com/QingYangJin/RCAIDE_Supersonic/issues/13#issuecomment-7063823679")
w("")
text = tick("\n".join(L) + "\n")
with OUT.open("w", encoding="utf-8", newline="\n") as fh:
    fh.write(text)
print(json.dumps({"receipt": str(OUT), "bytes": OUT.stat().st_size,
                  "sha256": sha(OUT)}, indent=2))
