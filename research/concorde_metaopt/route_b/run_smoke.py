"""run_smoke：路线B最小可运行垂直切片（纯合成，physical_call_count=0）。

流程：合成 train 任务 -> 离线轨迹数据集 -> direct-method 策略训练 ->
val/test 闭环评测（含负控） -> 中文图与结果落盘。

用法：
  python -m research.concorde_metaopt.route_b.run_smoke [--out runs/dnext001_route_b/run_001]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from .baselines import ACQUISITION_NAMES
from .contracts import canonical_json
from .policy import MetaAcquisitionPolicy, feature_names
from .policy_eval import default_arms, evaluate_arms, write_results
from .policy_train import train_policy
from .synthetic_tasks import (
    DEFAULT_BUDGET,
    DEFAULT_DIM,
    DEFAULT_N_INIT,
    DEFAULT_POOL_SIZE,
    DEFAULT_SPLIT_SIZES,
    make_task_split,
)
from .trajectory_dataset import BEHAVIORS, build_dataset, write_dataset


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_figure(summary: Dict[str, Any], path: Path) -> Dict[str, Any]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    candidate_fonts = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
    ]
    chinese_ok = False
    for font_path in candidate_fonts:
        if Path(font_path).exists():
            try:
                font_manager.fontManager.addfont(font_path)
                prop = font_manager.FontProperties(fname=font_path)
                plt.rcParams["font.family"] = prop.get_name()
                plt.rcParams["axes.unicode_minus"] = False
                chinese_ok = True
                break
            except Exception:  # noqa: BLE001 - 字体注册失败时回退英文标签
                continue
    arms = list(summary.keys())
    rewards = [summary[arm]["total_reward_mean"] for arm in arms]
    hit = [summary[arm]["feasible_hit_rate_mean"] for arm in arms]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    colors = ["#2b6cb0" if arm == "learned" else "#a0aec0" for arm in arms]
    axes[0].bar(arms, rewards, color=colors)
    axes[0].set_title("各臂平均总奖励（合成任务，B=%d）" % DEFAULT_BUDGET)
    axes[0].set_ylabel("total_reward 均值")
    axes[0].tick_params(axis="x", rotation=35)
    axes[1].bar(arms, hit, color=colors)
    axes[1].set_title("各臂可行命中率均值")
    axes[1].set_ylabel("feasible_hit_rate")
    axes[1].set_ylim(0, 1)
    axes[1].tick_params(axis="x", rotation=35)
    fig.suptitle("D-NEXT-001 路线B元采集策略原型评测（纯合成，physical_call_count=0）")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return {"path": str(path), "chinese_font_registered": chinese_ok, "arms": arms}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="路线B合成垂直切片")
    parser.add_argument("--out", default="runs/dnext001_route_b/run_001")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    parser.add_argument("--n-init", type=int, default=DEFAULT_N_INIT)
    parser.add_argument("--epochs", type=int, default=240)
    parser.add_argument("--seeds", type=int, default=2)
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    splits = make_task_split(DEFAULT_SPLIT_SIZES, dim=DEFAULT_DIM, budget=args.budget, pool_size=DEFAULT_POOL_SIZE)
    train_tasks, val_tasks, test_tasks = splits["train"], splits["val"], splits["test"]
    seeds = list(range(max(1, int(args.seeds))))

    dataset_payload = build_dataset(train_tasks, behaviors=BEHAVIORS, budget=args.budget, n_init=args.n_init, seeds=seeds)
    manifest = write_dataset(dataset_payload, out / "trajectory_dataset")
    report = train_policy(
        out / "trajectory_dataset", out / "policy_train", epochs=args.epochs, seed=0
    )
    trained = json.loads((out / "policy_train" / "policy.json").read_text(encoding="utf-8"))

    val_eval = evaluate_arms(val_tasks, trained, budget=args.budget, n_init=args.n_init, seed=0)
    write_results(val_eval, out / "policy_eval_val")
    test_eval = evaluate_arms(test_tasks, trained, budget=args.budget, n_init=args.n_init, seed=0)
    write_results(test_eval, out / "policy_eval_test")
    figure = make_figure(test_eval["summary"], out / "figures" / "route_b_arms_test.png")

    summary = {
        "run": "dnext001_route_b_run_001",
        "source_kind": "synthetic_analogue",
        "physical_call_count": 0,
        "real_physics_solver_calls": 0,
        "budget": args.budget,
        "n_init": args.n_init,
        "dim": DEFAULT_DIM,
        "pool_size": DEFAULT_POOL_SIZE,
        "split_sizes": DEFAULT_SPLIT_SIZES,
        "train_task_ids": [task.context.task_id for task in train_tasks],
        "val_task_ids": [task.context.task_id for task in val_tasks],
        "test_task_ids": [task.context.task_id for task in test_tasks],
        "dataset_manifest": manifest,
        "train_report": {
            key: report[key]
            for key in (
                "n_train_records", "n_val_records", "best_epoch", "best_val_loss",
                "final_train_loss", "final_val_loss", "feature_dim", "policy_sha256",
                "fit_task_ids", "val_task_ids",
            )
        },
        "val_primary_comparison": val_eval["primary_comparison"],
        "test_primary_comparison": test_eval["primary_comparison"],
        "val_negative_control": val_eval["negative_control_check"],
        "test_negative_control": test_eval["negative_control_check"],
        "val_summary": val_eval["summary"],
        "test_summary": test_eval["summary"],
        "figure": figure,
        "caveats": [
            "纯合成二次型任务，非 Concorde 真实评价，不可外推到真实气动设计",
            "direct-method 离线回归未做反事实校正，存在已知偏差",
            "测试任务数 4，统计功效不足，主比较一律 INCONCLUSIVE",
            "未与路线A采样器耦合，也未做 2x2 因子消融（需两条路线各自审查通过）",
        ],
    }
    (out / "run_summary.json").write_text(canonical_json(summary), encoding="utf-8")
    print(canonical_json({
        "out": str(out),
        "dataset_records": manifest["n_records"],
        "best_val_loss": report["best_val_loss"],
        "test_primary_comparison": test_eval["primary_comparison"],
        "test_negative_control": test_eval["negative_control_check"],
        "figure": figure["path"],
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
