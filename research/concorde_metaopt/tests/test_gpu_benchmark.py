"""A4 GPU/FOMAML 实现与项目 MAML 的等价性、确定性与隔离检查自身测试。

设计原则
--------
* 不触发任何真实物理求解（physical_call_count=0），只用合成任务族。
* GPU 相关断言在无 CUDA 环境下跳过，不伪造 FP64/FP32 GPU 数字。
* 与 project maml 的等价性按"一次外循环更新后的参数"逐元素比较，阈值 1e-9 相对误差。
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from research.concorde_metaopt.meta_learning import maml

tf = pytest.importorskip("research.concorde_metaopt.gpu.torch_fomaml")


def _make_case(hidden=(16, 16), seed=7):
    config = maml.MAMLConfig(
        input_dim=tf.N_INPUT,
        output_dim=tf.N_OUTPUT,
        hidden_sizes=hidden,
        inner_lr=0.03,
        inner_steps=3,
        outer_lr=0.1,
        tasks_per_batch=4,
        first_order=True,
        seed=seed,
    )
    project_params = maml.init_parameters(config, seed=seed)
    family = tf.make_task_family(n_tasks=6, seed=seed + 1)
    episodes = tf.make_episodes(family, [0, 1, 2, 3], k_shot=8, q_query=8, seed=seed + 2)
    project_episodes = [
        maml.TaskEpisode(
            support_features=episode.support_x,
            support_targets=episode.support_y,
            query_features=episode.query_x,
            query_targets=episode.query_y,
            task_id=str(index),
        )
        for index, episode in enumerate(episodes)
    ]
    return config, project_params, episodes, project_episodes


def _torch_params(project_params, dtype):
    torch = tf.require_torch()
    return [torch.tensor(np.array(array, dtype=np.float64), dtype=dtype) for array in project_params.tensors]


def test_fomaml_step_matches_project_maml():
    torch = tf.require_torch()
    config, project_params, episodes, project_episodes = _make_case()
    expected_params, stats = maml.meta_train_step(project_params, project_episodes, config, second_order=False)
    torch_params = _torch_params(project_params, torch.float64)
    new_params, step_stats, grads = tf.fomaml_step(
        torch_params,
        episodes,
        inner_lr=config.inner_lr,
        inner_steps=config.inner_steps,
        outer_lr=config.outer_lr,
        device="cpu",
        dtype=torch.float64,
    )
    for index, (actual, expected) in enumerate(zip(new_params, expected_params.tensors)):
        actual = np.asarray(actual.detach().cpu() if hasattr(actual, "detach") else actual, dtype=np.float64)
        scale = max(1e-12, float(np.max(np.abs(expected))))
        relative = float(np.max(np.abs(actual - expected))) / scale
        assert relative < 1e-9, f"参数 {index} 相对误差 {relative:.3e} 超阈值"
    assert len(grads) == len(expected_params.tensors)
    assert math.isfinite(step_stats["outer_loss"])


def test_fomaml_step_is_deterministic():
    torch = tf.require_torch()
    config, project_params, episodes, _ = _make_case()
    base = _torch_params(project_params, torch.float64)
    kwargs = dict(inner_lr=config.inner_lr, inner_steps=config.inner_steps, outer_lr=config.outer_lr, device="cpu", dtype=torch.float64)
    first, _, _ = tf.fomaml_step(base, episodes, **kwargs)
    second, _, _ = tf.fomaml_step(base, episodes, **kwargs)
    for left, right in zip(first, second):
        assert np.array_equal(np.asarray(left.detach().cpu()), np.asarray(right.detach().cpu()))


def test_fp32_deviation_is_bounded():
    torch = tf.require_torch()
    config, project_params, episodes, _ = _make_case()
    kwargs = dict(inner_lr=config.inner_lr, inner_steps=config.inner_steps, outer_lr=config.outer_lr, device="cpu")
    fp64, _, _ = tf.fomaml_step(_torch_params(project_params, torch.float64), episodes, dtype=torch.float64, **kwargs)
    fp32, _, _ = tf.fomaml_step(_torch_params(project_params, torch.float32), episodes, dtype=torch.float32, **kwargs)
    for left, right in zip(fp64, fp32):
        left_np = np.asarray(left.detach().cpu(), dtype=np.float64)
        right_np = np.asarray(right.detach().cpu(), dtype=np.float64)
        scale = max(1e-12, float(np.max(np.abs(left_np))))
        relative = float(np.max(np.abs(left_np - right_np))) / scale
        assert relative < 5e-3, f"FP32 相对偏差 {relative:.3e} 超阈值"


def test_batch_score_shapes_and_finiteness():
    torch = tf.require_torch()
    config, project_params, episodes, _ = _make_case(hidden=(8, 8))
    base = _torch_params(project_params, torch.float64)
    features = episodes[0].support_x
    scores = tf.batch_score(base, features, "cpu", torch.float64)
    scores_np = np.asarray(scores.detach().cpu() if hasattr(scores, "detach") else scores)
    assert scores_np.shape == (features.shape[0],)
    assert np.all(np.isfinite(scores_np))
    assert tf.count_nonfinite(scores_np) == 0


def test_episode_generation_is_seeded():
    family_a = tf.make_task_family(n_tasks=4, seed=1)
    family_b = tf.make_task_family(n_tasks=4, seed=1)
    episodes_a = tf.make_episodes(family_a, [0, 1], k_shot=5, q_query=6, seed=9)
    episodes_b = tf.make_episodes(family_b, [0, 1], k_shot=5, q_query=6, seed=9)
    for left, right in zip(episodes_a, episodes_b):
        assert np.array_equal(left.support_x, right.support_x)
        assert np.array_equal(left.query_y, right.query_y)


def test_worktree_porcelain_parsing():
    from research.concorde_metaopt.gpu import repo_isolation_check as ric

    text = (
        "worktree D:/RCAIDE/dnext001/repo\n"
        "HEAD ea8ad97833eb5ceab291faae643c141a2b219749\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree D:/RCAIDE/dnext001/wt-a4\n"
        "HEAD 1234567890abcdef\n"
        "branch refs/heads/research/dnext001-gpu-benchmark\n"
        "\n"
    )
    entries = ric.parse_worktrees(text)
    assert len(entries) == 2
    assert entries[1]["branch"] == "refs/heads/research/dnext001-gpu-benchmark"


def test_markdown_rendering_reports_failures():
    from research.concorde_metaopt.gpu import repo_isolation_check as ric

    payload = {
        "generated_at_utc": "2026-11-10T00:00:00+00:00",
        "common_repo": "X",
        "current_worktree": "Y",
        "current_branch": "b",
        "head": "h",
        "base": "base",
        "all_passed": False,
        "scope_note": "n",
        "checks": [{"check_id": "c1", "ok": False, "detail": "坏了", "evidence": {}}],
    }
    markdown = ric.render_markdown(payload)
    assert "FAIL" in markdown
    assert "存在失败项" in markdown


def test_repo_isolation_check_runs_on_current_tree():
    """只读集成：在当前 worktree 上跑完整检查，确认字段齐全（不强制 all_passed）。"""
    from pathlib import Path

    from research.concorde_metaopt.gpu import repo_isolation_check as ric

    root = Path(__file__).resolve().parents[4]
    payload = ric.evaluate(
        current=root,
        base=ric.DEFAULT_BASE,
        allowed_prefixes=(
            "research/concorde_metaopt/gpu/",
            "research/concorde_metaopt/tests/test_gpu_benchmark.py",
            "docs/planning/dnext001_gpu_",
            "docs/receipts/dnext001/a4_",
        ),
        expect_branch=None,
    )
    ids = {check["check_id"] for check in payload["checks"]}
    for required in (
        "worktree_paths_unique",
        "worktree_branches_unique",
        "worktree_gitdir_wiring",
        "no_cross_tree_links",
        "base_is_ancestor_of_head",
        "no_merge_commits_current_branch",
        "no_main_merge_into_current",
        "current_branch_no_upstream",
        "other_branch_merges_observed",
        "write_scope_uncommitted",
        "frozen_artifacts_untouched",
    ):
        assert required in ids, f"缺少检查项 {required}"
    json.dumps(payload, ensure_ascii=False)
