
"""Write P2 run_config.json / task_family_split.json / geometry_freeze.json / README.md."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"D:/RCAIDE/.worktrees/dreal004-p0-20261122")
RUN = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01")
GEOM = "5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15"
LIFT_N = 1333704.4


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def dump(name: str, obj) -> None:
    (RUN / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")


prereg = json.loads((RUN / "p2_preregistration.json").read_text(encoding="utf-8"))
plan = json.loads((RUN / "p2_supplement_plan.json").read_text(encoding="utf-8"))
acc = json.loads((RUN / "p2_supplement_accounting.json").read_text(encoding="utf-8"))
ds = json.loads((RUN / "p2_dataset" / "p2_dataset.json").read_text(encoding="utf-8"))
res = json.loads((RUN / "training" / "p2_training_result.json").read_text(encoding="utf-8"))
summ = json.loads((RUN / "training" / "p2_arm_summary.json").read_text(encoding="utf-8"))

run_config = {
    "schema": "dreal004.p2_run_config.v1",
    "run_id": "DRECOVER001-P2-20261123-01",
    "issue": "QingYangJin/RCAIDE_Supersonic#14 (P2 directive; owner comment 7103901506)",
    "authorization_id": prereg["authorization_id"],
    "batch_ids": [prereg["batch_id"], "DRECOVER001-P2-20261123-01-B02"],
    "solver": {"executable": "D:/OpenVSP-3.55.0/OpenVSP-3.55.0-win64/vspaero.exe",
               "executable_id": "vspaero-3.55.0-v7.2.2-omp1", "openmp": 1,
               "dtype": "float64", "device": "cpu"},
    "caps": {"max_physical_starts": plan["max_starts"],
             "max_internal_solver_cases": plan["max_internal_solver_cases"],
             "alpha_probes_per_start": plan["max_alpha_probes_per_start"],
             "parallelism": plan["parallelism"], "retries": plan["retries"],
             "per_start_timeout_s": plan["timeout_s_per_start"],
             "wall_clock_max_s": plan["wall_clock_max_s"]},
    "actual": {"physical_solver_starts_actual": acc["physical_solver_starts_actual"],
               "physical_solver_starts_completed": acc["physical_solver_starts_completed"],
               "internal_solver_cases_actual": acc["internal_solver_cases_actual"],
               "retries_actual": acc["retries_actual"], "parallelism": acc["parallelism"],
               "wall_clock_s": acc["wall_clock_s"],
               "admitted_labels": acc["admitted_labels"], "null_labels": acc["null_labels"],
               "valid_label_rate_over_completed": acc["valid_label_rate_over_completed"]},
    "task_family": {"train": ["P2-CANON-M140", "P2-CANON-M160", "P2-CANON-M200", "P2-CANON-M202"],
                    "val": ["P2-CANON-M180", "P2-CANON-M220"],
                    "test": ["P2-CANON-M240", "P2-CANON-M260"]},
    "training": {"arms": res["arms"], "k_values": res["k_values"], "seeds": res["seeds"],
                 "k5": res["k5"], "normalizer_sha256": res["normalizer"]["sha256"],
                 "checkpoints": len(res["checkpoints"]), "max_steps": 60,
                 "hidden_sizes": [32, 32], "inner_lr": 0.05, "inner_steps": 5,
                 "outer_lr": 0.01, "tasks_per_batch": 2,
                 "device": "cpu", "dtype": "float64"},
    "summary_rows": summ["rows"],
    "environment": res["environment"],
    "code_shas": res["code_shas"],
    "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "physical_solver_starts_during_training": 0,
}
dump("run_config.json", run_config)

family = {
    "schema": "dreal004.p2_task_family_split.v1",
    "dataset_sha256": sha(RUN / "p2_dataset" / "p2_dataset.json"),
    "rows": ds["rows"], "certificates": ds["certificates"], "excluded": len(ds["excluded"]),
    "splits": run_config["task_family"],
    "tasks": [{"task_id": t["task_id"], "split": t["split"], "mach": t["mach"],
               "dynamic_pressure_pa": t["dynamic_pressure_pa"], "lift_target_n": LIFT_N,
               "geometry_contract_sha256": GEOM,
               "support_rows": t["support"], "query_rows": t["query"],
               "k3_support_ok": t["k3_support_ok"], "k3_query_ok": t["k3_query_ok"],
               "support_designs": t["support_designs"], "query_designs": t["query_designs"]}
              for t in ds["tasks"]],
    "task_aliases": ds.get("task_aliases", {}),
    "leakage_controls": ["support/query partitions disjoint per task",
                         "one admitted design appears in exactly one partition",
                         "normalization statistics fitted on train rows only",
                         "validation used only for early stopping/selection",
                         "test scored once"],
}
dump("task_family_split.json", family)

freeze = {
    "schema": "dreal004.p2_geometry_freeze_ref.v1",
    "geometry_freeze_id": "GBFREEZE2-5f2bb12fe8b1dc68",
    "geometry_contract_sha256": GEOM,
    "reference_area_m2": 358.25, "reference_chord_m": 18.489893,
    "reference_span_m": 25.604638, "altitude_m": 18288.0, "lift_target_n": LIFT_N,
    "design_space": {
        "names": ["wing_area", "wing_sweep1", "fuselage_length", "wing_sweep2",
                  "wing_span", "wing_root_thick", "wing_tip_thick", "vertical_tail_area",
                  "vertical_tail_sweep", "vertical_tail_thick", "fuselage_diameter",
                  "wing_dihedral", "wing_vertical_position", "fuselage_width", "fuselage_height"],
        "baseline": [358.25, 1.83, 67.0, 48.0, 71.0, 0.480469, 0.945313, 0.408284,
                     0.130178, 0.0, 33.91, 0.0, 61.66, 4.30, 1.152778],
        "network_input_dim": 12,
        "network_input_note": "first 12 variables only; fuselage length/width/height stay at baseline and are not effective 12D dimensions"},
    "design_geometries": {"d00": {"wing_area_m2": 358.25},
                          "d01": {"wing_area_m2": 361.8325},
                          "d02": {"wing_sweep1_deg": 67.5},
                          "d03": {"wing_area_m2": 354.6675},
                          "d04": {"wing_sweep1_deg": 66.5}},
    "mach_flow": {"M140": {"mach": 1.4, "q_pa": 9839.359586688344},
                  "M160": {"mach": 1.6, "q_pa": 12851.40843975621},
                  "M180": {"mach": 1.8, "q_pa": 16265.063806566453},
                  "M200": {"mach": 2.0, "q_pa": 20080.325687061594},
                  "M202": {"mach": 2.02, "q_pa": 20483.940233430174},
                  "M220": {"mach": 2.2, "q_pa": 24297.194081414087},
                  "M240": {"mach": 2.4, "q_pa": 28915.66898945147},
                  "M260": {"mach": 2.6, "q_pa": 33935.75041123124}},
    "alpha_algorithm": {
        "method": "zero-physical bracket from G2 stage-1 coarse polar, then 3 local alpha probes per start",
        "bracket_source": "DRECOVER001-G2-20261121-01 stage1 polars (read-only; no physics in bracketing)",
        "probes_per_start": 3},
    "lift_tolerance_rel": 0.001,
    "note": "frozen geometry contract; no geometry was modified in P2",
}
dump("geometry_freeze.json", freeze)

readme = """# DRECOVER001-P2-20261123-01（Issue #14 P2：真实 VSPAERO 标签 + MAML 四臂公平对照）

本目录是 Issue #14「P2 执行指令」的运行产物，不是 P3，也不构成任何新的物理授权。

## 1. 物理开销（真实 VSPAERO）
- 补采 16 次真实 solver 启动，16/16 完成，0 失败、0 重试，并行 1，墙钟 29.394 s。
- 内部迎角工况 48 个（每 start 3 个局部 alpha 探针），上限 48。
- 16 条准入标签（valid label rate 1.0），0 个 NULL。
- 原始 deck/polar/history/日志、准入证书、账本、上传回执全部在本仓库，可从 GitHub 实际回读。

## 2. 数据切分
- train：M140、M160、M200、M202；val：M180、M220；test：M240、M260。
- 可用独立 support/query 行见 task_family_split.json 与 p2_dataset/p2_dataset.json（44 行、44 张证书）。
- 仅训练集行用于归一化；验证集只用于早停/选择；留出测试集只评一次。
- K=1 与 K=3 实际运行；K=5 为 NOT_ELIGIBLE（冻结协议只有 d00-d03 四个独立 support 槽位，禁止用 query 充数）。

## 3. 四臂与结果（CPU float64，种子 7/19/43）
- 随机初始化、普通联合预训练、任务条件预训练、FOMAML；逐任务逐种子指标见 tables/p2_arm_metrics.csv、tables/p2_predictions.csv、tables/p2_training_curves.csv。
- 每个模型 checkpoint（npz）与归一化参数在 training/checkpoints/、training/p2_normalizer.json，SHA256 见 training/p2_training_result.json。
- 结论以实测为准，包含负结果：本轮任务条件预训练最好，FOMAML 在 K=3 明显退化（外循环损失在部分种子后期上升），未按测试集调参。
- 离线候选排序诊断见 training/p2_offline_selection.json（不是在线优化，也不是 P3 的 BO/DE 对比）。

## 4. 边界与披露
- A5 审查为 deepseek-flash 只读上下文，非人类签名；审查范围仅为协议、代码与产物，不等同 R1 全部代码 PASS。
- 标签同机保存（Owner 已豁免异机独立故障域备份要求）；无风洞/物理验证，physics_validated=false。
- 目标定义：同升力（相对容差 1e-3）下的翼面诱导阻力 Di_N = q * Sref * CDi；不含整机阻力或油耗，fuel_burn_kg=null。
- P1 的 196 对 18 内部工况差异不得记作 MAML 收益。
- P3 需另行预注册、A5 审查与新的 Lead GO。
"""
(RUN / "README.md").write_text(readme, encoding="utf-8", newline="\n")
print("wrote run_config/task_family_split/geometry_freeze/README; dataset sha", family["dataset_sha256"])
