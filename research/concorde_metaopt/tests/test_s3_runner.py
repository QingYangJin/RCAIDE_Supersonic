"""S3 runner 测试：run_key/shard、campaign 并行等价、冻结产物、run_config/data_manifest、预算与确定性子集。

边界：campaign 用 fake worker（不训练/不求解）；冻结产物/配置测试用合成证据仓；
不写仓库、不启动真实 solver（VLM/CFD/SU2/Gmsh 零调用）；physical_call_count=0。
"""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research.concorde_metaopt.meta_learning import s3_prereg as sp
from research.concorde_metaopt.meta_learning import s3_runner as runner
from research.concorde_metaopt.meta_learning import task_family as tf
from research.concorde_metaopt.tests import test_s3_support as support


# ---------------------------------------------------------------------------
# 合成证据仓（模块级复用；含已构建 prereg）
# ---------------------------------------------------------------------------
_REPO_INFO = None
_REPO_TMP = None


def repo_info():
    global _REPO_INFO, _REPO_TMP
    if _REPO_INFO is None:
        _REPO_TMP = tempfile.TemporaryDirectory(prefix="s3-runner-synth-")
        _REPO_INFO = support.build_synthetic_s3_repo(_REPO_TMP.name)
    return _REPO_INFO


def tearDownModule():
    global _REPO_INFO, _REPO_TMP
    _REPO_INFO = None
    if _REPO_TMP is not None:
        _REPO_TMP.cleanup()
        _REPO_TMP = None


def _assert_error_code(testcase, code, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except runner.S3RunnerError as exc:
        testcase.assertEqual(exc.code, code, str(exc))
        return exc
    raise AssertionError("期望 S3RunnerError(" + code + ") 未抛出")


# ---------------------------------------------------------------------------
# fake campaign worker：结果完全由 spec 决定（确定性、无训练）
# ---------------------------------------------------------------------------
def _fake_result(spec, *, wall=None, status="OK", peak=None):
    spec = dict(spec)
    campaign = str(spec.get("campaign_id") or "S3")
    run_id = runner._run_id_for(spec, campaign)
    budget = int(spec["budget"])
    opt = int(spec["opt_seed"])
    meta = int(spec["meta_seed"])
    if wall is None:
        wall = 0.25 + budget / 1024.0 + 0.01 * opt + 0.001 * meta
    rows = []
    for index in (1, 2, 3):
        record = {
            "schema_version": sp.S3_RECORD_SCHEMA_VERSION,
            "run_id": run_id,
            "task_id": str(spec["task_id"]),
            "split": str(spec["split"]),
            "arm_id": str(spec["arm"]),
            "budget": budget,
            "opt_seed": opt,
            "meta_seed": meta,
            "evaluation_index": int(index),
            "design": [round(0.01 * index, 6)] * 12,
            "f": float(index),
            "g1": 0.0,
            "g2": 0.0,
            "feasible": True,
            "source": "support",
            "phase": str(spec["phase"]),
            "holdout_truth_read": False,
            "wall_s": 0.0,
        }
        record["record_digest"] = runner.eval_record_digest(record)
        rows.append(record)
    run = {
        "run_id": run_id,
        "arm": str(spec["arm"]),
        "task_id": str(spec["task_id"]),
        "split": str(spec["split"]),
        "phase": str(spec["phase"]),
        "budget": budget,
        "opt_seed": opt,
        "meta_seed": meta,
        "wall_s": float(wall),
        "peak_memory_mb": (100.0 + opt) if peak is None else float(peak),
        "status": str(status),
        "n_records": len(rows),
        "source_counts": {"support": len(rows)},
    }
    return {"spec": spec, "records": rows, "run": run, "status": str(status), "error": None}


class _FakePool:
    def __init__(self, *, processes, initializer=None, initargs=()):
        self.processes = int(processes)
        self.initializer = initializer
        self.initargs = tuple(initargs)
        self.mapped = 0
        self.started = 0
        self.yielded = 0
        self.terminated = False
        self.closed = False
        self.joined = False

    def __enter__(self):
        if self.initializer is not None:
            self.initializer(*self.initargs)
        return self

    def __exit__(self, exc_type, exc, tb):
        # 与 multiprocessing.Pool.__exit__ 一致：退出即 terminate（并发停止路径的兜底）
        self.terminate()
        return False

    def map(self, func, iterable, chunksize=1):
        items = list(iterable)
        self.mapped = len(items)
        return [func(item) for item in items]

    def imap_unordered(self, func, iterable, chunksize=1):
        items = list(iterable)
        self.started = len(items)
        for item in items:
            if self.terminated:
                break
            self.yielded += 1
            yield func(item)

    def terminate(self):
        self.terminated = True

    def close(self):
        self.closed = True

    def join(self):
        self.joined = True


class _FakeContext:
    def __init__(self):
        self.pools = []

    def Pool(self, *, processes, initializer=None, initargs=()):
        pool = _FakePool(processes=processes, initializer=initializer, initargs=initargs)
        self.pools.append(pool)
        return pool


def _campaign_specs(count=10):
    specs = []
    for arm_index, arm in enumerate(sp.S3_ARMS):
        for budget in sp.S3_BUDGETS:
            specs.append(
                {
                    "arm": arm,
                    "task_id": "MT-0000",
                    "split": "meta_test",
                    "budget": int(budget),
                    "opt_seed": 0,
                    "meta_seed": 0,
                    "phase": "EVAL",
                }
            )
    return specs[: int(count)]


class _CampaignCase(unittest.TestCase):
    def setUp(self):
        self._worker_state = getattr(runner, "_WORKER_STATE", None)

    def tearDown(self):
        runner._WORKER_STATE = self._worker_state

    def _run(
        self,
        specs,
        workers,
        campaign_id="S3-TEST",
        entry=None,
        wall=None,
        status="OK",
        peak=None,
        prior_sum_run_wall_s=0.0,
        clock=None,
    ):
        def fake(spec):
            return _fake_result(spec, wall=wall, status=status, peak=peak)

        context = _FakeContext()
        with mock.patch.object(runner, "_worker_entry", side_effect=entry or fake), mock.patch.object(
            runner.multiprocessing, "get_context", lambda *args, **kwargs: context
        ):
            result = runner.execute_campaign(
                specs,
                workers=int(workers),
                state={"fake": True},
                campaign_id=str(campaign_id),
                run_mode="SMOKE",
                prior_sum_run_wall_s=float(prior_sum_run_wall_s),
                clock=clock,
            )
        return result, context


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------
class UtilityTests(unittest.TestCase):
    def test_round6(self):
        self.assertEqual(runner._round6(1.23456789), 1.234568)
        self.assertEqual(runner._round6(0), 0.0)
        self.assertEqual(runner._round6(-2.0000004), -2.0)

    def test_write_read_json_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "a.json"
            info = runner.write_json_canonical(path, {"b": 1, "a": [1, 2]})
            data = path.read_bytes()
            self.assertTrue(data.endswith(b"\n"))
            self.assertNotIn(b"\r", data)
            self.assertEqual(info["bytes"], len(data))
            self.assertEqual(info["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(runner.read_json_file(path), {"a": [1, 2], "b": 1})

    def test_write_read_jsonl_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.jsonl"
            info = runner.write_jsonl(path, [{"b": 2, "a": 1}, {"a": 3}])
            data = path.read_bytes()
            self.assertEqual(info["rows"], 2)
            self.assertEqual(info["sha256"], hashlib.sha256(data).hexdigest())
            self.assertNotIn(b"\r", data)
            rows = runner.read_jsonl(path)
            self.assertEqual([row["a"] for row in rows], [1, 3])
            self.assertIn('{"a":1,"b":2}', data.decode("utf-8"))

    def test_read_jsonl_rejects_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.jsonl"
            path.write_bytes(b'{"a":1}\n\n{"a":2}\n')
            _assert_error_code(self, runner.S3_RUNNER_RECORD_ERROR, runner.read_jsonl, path)

    def test_eval_record_digest_excludes_runtime_fields(self):
        records = _fake_result({
            "arm": "S3-BO-RANDOM",
            "task_id": "T",
            "split": "meta_test",
            "budget": 64,
            "opt_seed": 0,
            "meta_seed": 0,
            "phase": "EVAL",
        })["records"]
        base = dict(records[0])
        changed = dict(base, wall_s=99.0, peak_memory_mb=123.0)
        self.assertEqual(runner.eval_record_digest(base), runner.eval_record_digest(changed))
        changed["f"] = 7.5
        self.assertNotEqual(runner.eval_record_digest(base), runner.eval_record_digest(changed))

    def test_train_record_digest_excludes_runtime_fields(self):
        record = {
            "schema_version": sp.S3_RECORD_SCHEMA_VERSION,
            "run_id": "r",
            "meta_seed": 0,
            "outer_step": 1,
            "loss": 0.5,
            "wall_s": 0.0,
            "train_episode_digest": "a" * 64,
        }
        same = dict(record, wall_s=9.0, peak_memory_mb=1.0)
        self.assertEqual(runner.train_record_digest(record), runner.train_record_digest(same))
        same["loss"] = 0.25
        self.assertNotEqual(runner.train_record_digest(record), runner.train_record_digest(same))

    def test_peak_memory_positive(self):
        value = runner.peak_memory_mb()
        self.assertIsInstance(value, float)
        self.assertGreater(value, 0.0)

    def test_task_ids_sha256_for_sorted(self):
        ids = ["MT-0002", "MT-0000", "MT-0001"]
        self.assertEqual(runner.task_ids_sha256_for(ids), sp.task_ids_sha256(sorted(ids)))
        self.assertEqual(runner.task_ids_sha256_for(list(reversed(ids))), runner.task_ids_sha256_for(ids))

    def test_designs_sha256_stable(self):
        designs = [[0.0, 1.0], [2.0, 3.0]]
        self.assertEqual(runner.designs_sha256(designs), runner.designs_sha256([list(row) for row in designs]))
        self.assertEqual(len(runner.designs_sha256(designs)), 64)
        self.assertNotEqual(runner.designs_sha256(designs), runner.designs_sha256([[0.0, 1.0], [2.0, 4.0]]))


# ---------------------------------------------------------------------------
# run_key / shard
# ---------------------------------------------------------------------------
class RunKeyTests(unittest.TestCase):
    def setUp(self):
        self.spec = _campaign_specs(1)[0]

    def test_canonical_run_key_fields(self):
        key = runner.canonical_run_key(self.spec)
        self.assertEqual(
            list(key),
            ["arm", "budget", "meta_seed", "opt_seed", "phase", "split", "task_id"],
        )
        self.assertEqual(key["arm"], "S3-BO-RANDOM")
        self.assertEqual(key["budget"], 64)

    def test_run_id_format(self):
        run_id = runner._run_id_for(self.spec, "S3-TEST")
        self.assertEqual(run_id, "S3-TEST--S3-BO-RANDOM--B64--TMT-0000--MS0--OS0")
        self.assertNotIn("worker", run_id)

    def test_run_shard_fixed_vector(self):
        key = runner.canonical_run_key(self.spec)
        expected = int.from_bytes(
            hashlib.sha256(sp.canonical_json(key).encode("utf-8")).digest()[:8], "big"
        )
        for workers in (1, 2, 3, 8):
            self.assertEqual(runner.run_shard(self.spec, workers), expected % workers)
        _assert_error_code(self, runner.S3_RUNNER_ERROR, runner.run_shard, self.spec, 0)

    def test_run_sort_key_order(self):
        specs = _campaign_specs(4)
        ordered = sorted(specs, key=runner.run_sort_key)
        keys = [runner.run_sort_key(spec) for spec in ordered]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(ordered), 4)

    def test_shard_map_partition_and_determinism(self):
        specs = _campaign_specs(10)
        for workers in (1, 2, 3, 8):
            first = runner.shard_map(specs, workers)
            second = runner.shard_map(specs, workers)
            self.assertEqual(first["workers"], workers)
            self.assertEqual(first["run_count"], 10)
            self.assertEqual(len(first["per_shard_counts"]), workers)
            self.assertEqual(sum(first["per_shard_counts"]), 10)
            self.assertEqual(first["runs_sha256"], second["runs_sha256"])
            self.assertEqual([row["shard"] for row in first["runs"]], sorted(row["shard"] for row in first["runs"]))
            for row in first["runs"]:
                self.assertGreaterEqual(row["shard"], 0)
                self.assertLess(row["shard"], workers)
                self.assertEqual(sorted(row["spec"]), sorted(runner.canonical_run_key(specs[0])))
            if workers == 1:
                self.assertEqual(first["per_shard_counts"], [10])


# ---------------------------------------------------------------------------
# campaign：W=1 串行 vs W>1 并行（fake worker）
# ---------------------------------------------------------------------------
class CampaignTests(_CampaignCase):
    def test_w1_serial_results(self):
        specs = _campaign_specs(10)
        result, _context = self._run(specs, 1)
        self.assertEqual(len(result["results"]), 10)
        expected = [runner._run_id_for(spec, "S3-TEST") for spec in sorted(specs, key=runner.run_sort_key)]
        self.assertEqual([item["run"]["run_id"] for item in result["results"]], expected)

    def test_w8_openmp_equivalent_to_w1(self):
        specs = _campaign_specs(10)
        serial, _ = self._run(specs, 1)
        parallel, context = self._run(specs, 8)
        self.assertEqual(len(parallel["results"]), 10)
        self.assertEqual(len(context.pools), 1)
        self.assertEqual(context.pools[0].processes, 8)

        def signature(result):
            return [
                (
                    item["run"]["run_id"],
                    [record["record_digest"] for record in item["records"]],
                    item["run"]["wall_s"],
                    item["run"]["peak_memory_mb"],
                    item["status"],
                )
                for item in result["results"]
            ]

        self.assertEqual(signature(serial), signature(parallel))
        self.assertEqual(
            serial["execution_report"]["sum_run_wall_seconds"],
            parallel["execution_report"]["sum_run_wall_seconds"],
        )
        repeat, _ = self._run(specs, 8)
        self.assertEqual(signature(parallel), signature(repeat))

    def test_execution_report_schema(self):
        specs = _campaign_specs(10)
        result, _ = self._run(specs, 2)
        report = result["execution_report"]
        self.assertEqual(tuple(report), runner.S3_EXECUTION_REPORT_FIELDS)
        self.assertEqual(report["schema_version"], "p4ra-s3-execution-report-v2")
        self.assertEqual(report["campaign_id"], "S3-TEST")
        self.assertEqual(report["run_mode"], "SMOKE")
        self.assertEqual(report["parallel_workers"], 2)
        self.assertEqual(report["run_count_requested"], 10)
        self.assertEqual(report["run_count_completed"], 10)
        self.assertEqual(len(report["per_shard_counts"]), 2)
        self.assertEqual(sum(report["per_shard_counts"]), 10)
        self.assertEqual(report["physical_call_count"], 0)
        self.assertIsNone(report["stop_reason"])
        self.assertEqual(report["sum_run_wall_limit_s"], 28000)
        self.assertEqual(len(report["shard_runs_sha256"]), 64)
        expected_sum = round(sum(item["run"]["wall_s"] for item in result["results"]), 6)
        self.assertEqual(report["sum_run_wall_seconds"], expected_sum)
        self.assertGreater(report["campaign_wall_s"], 0.0)

    def test_sum_run_wall_limit_stops(self):
        specs = [_campaign_specs(1)[0] for _ in range(500)]
        result, _ = self._run(specs, 1, wall=60.0)
        report = result["execution_report"]
        self.assertEqual(report["run_count_requested"], 500)
        self.assertEqual(report["run_count_completed"], 467)
        self.assertEqual(report["stop_reason"], runner.S3_RUNNER_SUM_RUN_WALL_LIMIT)
        self.assertEqual(report["sum_run_wall_seconds"], 28020.0)

    def test_per_run_resource_limit_stops(self):
        specs = _campaign_specs(3)
        result, _ = self._run(specs, 1, status="RESOURCE_LIMIT")
        report = result["execution_report"]
        self.assertEqual(report["run_count_completed"], 1)
        self.assertEqual(report["stop_reason"], runner.S3_RUNNER_RESOURCE_LIMIT)
        self.assertEqual(result["results"][0]["status"], "RESOURCE_LIMIT")

    def test_per_run_wall_limit_stops_immediately(self):
        # A5-S3M1-M01：per-run wall 超限后立即停止，后续 run 不再执行。
        specs = _campaign_specs(3)
        calls = []

        def fake(spec):
            calls.append(runner.canonical_run_key(spec))
            return _fake_result(spec, wall=61.0)

        result, _ = self._run(specs, 1, entry=fake)
        report = result["execution_report"]
        self.assertEqual(report["run_count_requested"], 3)
        self.assertEqual(report["run_count_completed"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report["stop_reason"], runner.S3_RUNNER_RESOURCE_LIMIT)
        self.assertEqual(report["max_run_wall_s"], 61.0)
        item = result["results"][0]
        self.assertEqual(item["status"], "RESOURCE_LIMIT")
        self.assertEqual(item["run"]["status"], "RESOURCE_LIMIT")
        self.assertEqual(item["run"]["resource_violation"], "per_run_wall_s")

    def test_peak_memory_limit_stops_immediately(self):
        # A5-S3M1-M02：单 run 峰值内存超过 8192MB 立即停止。
        specs = _campaign_specs(3)
        result, _ = self._run(specs, 1, peak=9000.0)
        report = result["execution_report"]
        self.assertEqual(report["run_count_completed"], 1)
        self.assertEqual(report["stop_reason"], runner.S3_RUNNER_RESOURCE_LIMIT)
        self.assertEqual(result["results"][0]["run"]["resource_violation"], "peak_memory_mb")

    def test_campaign_wall_limit_stops(self):
        # campaign 墙钟 > 7200s（注入 clock，不真 sleep）。
        ticks = iter([0.0, 7201.0, 7201.0])
        specs = _campaign_specs(3)
        result, _ = self._run(specs, 1, clock=lambda: next(ticks))
        report = result["execution_report"]
        self.assertEqual(report["run_count_completed"], 1)
        self.assertEqual(report["stop_reason"], runner.S3_RUNNER_DEADLINE_EXCEEDED)

    def test_prior_sum_run_wall_stops_across_campaigns(self):
        # 跨 campaign 累计 Σrun wall：前序 campaign 已用 27999.9s，本 campaign 首个 run 即超 28000。
        specs = _campaign_specs(3)
        result, _ = self._run(specs, 1, prior_sum_run_wall_s=27999.9)
        report = result["execution_report"]
        self.assertEqual(report["run_count_completed"], 1)
        self.assertEqual(report["stop_reason"], runner.S3_RUNNER_SUM_RUN_WALL_LIMIT)
        # campaign 报告仍为单 campaign 口径（sum 不含 prior）。
        self.assertLess(report["sum_run_wall_seconds"], 1.0)

    def test_w8_resource_stop_immediate(self):
        # W>1：超限立即停止，未完成的 run 不再执行（记录数 < 请求数）。
        specs = _campaign_specs(10)
        result, context = self._run(specs, 8, wall=61.0)
        report = result["execution_report"]
        self.assertEqual(report["run_count_requested"], 10)
        self.assertEqual(report["run_count_completed"], 1)
        self.assertEqual(report["stop_reason"], runner.S3_RUNNER_RESOURCE_LIMIT)
        self.assertEqual(len(context.pools), 1)
        pool = context.pools[0]
        self.assertTrue(pool.terminated)
        self.assertLess(pool.yielded, 10)

    def test_campaign_rejects_bad_workers(self):
        specs = _campaign_specs(2)
        for workers in (0, -1, 33, True):
            _assert_error_code(
                self, runner.S3_RUNNER_ERROR, runner.execute_campaign, specs,
                workers=workers, state={}, campaign_id="S3-TEST",
            )


# ---------------------------------------------------------------------------
# 预算与记录计数
# ---------------------------------------------------------------------------
class BudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = repo_info()
        cls.prereg = cls.info["prereg"]

    def test_formal_budget_from_prereg(self):
        budget = runner.resolve_budget(run_mode="FORMAL", prereg=self.prereg, smoke_overrides=None)
        self.assertEqual(budget["run_mode"], "FORMAL")
        self.assertEqual(budget["outer_steps"], 200)
        self.assertEqual(budget["meta_seeds"], [0, 1, 2])
        self.assertEqual(budget["budgets"], [64, 128])
        self.assertEqual(budget["opt_seeds"], [0, 1, 2, 3, 4])
        self.assertEqual(budget["eval_tasks"], 20)
        self.assertEqual(budget["k_sweep"], [5])
        self.assertEqual(budget["fd_coordinates"], 32)
        self.assertEqual(budget["eval_split"], "meta_test")
        self.assertIsNone(budget["smoke_overrides"])

    def test_formal_rejects_overrides(self):
        _assert_error_code(
            self, runner.S3_RUNNER_ERROR, runner.resolve_budget,
            run_mode="FORMAL", prereg=self.prereg, smoke_overrides={"outer_steps": 1},
        )

    def test_smoke_override_validation(self):
        overrides = {
            "outer_steps": 2,
            "meta_seeds": [0],
            "budgets": [64],
            "opt_seeds": [0],
            "eval_tasks": 4,
            "k_sweep": [5],
            "fd_coordinates": 2,
        }
        budget = runner.resolve_budget(run_mode="SMOKE", prereg=self.prereg, smoke_overrides=overrides)
        self.assertEqual(budget["run_mode"], "SMOKE")
        self.assertEqual(budget["eval_split"], "meta_validation")
        self.assertEqual(budget["smoke_overrides"], overrides)
        missing = {key: value for key, value in overrides.items() if key != "fd_coordinates"}
        _assert_error_code(
            self, runner.S3_RUNNER_ERROR, runner.resolve_budget,
            run_mode="SMOKE", prereg=self.prereg, smoke_overrides=missing,
        )
        bad_outer = dict(overrides, outer_steps=0)
        _assert_error_code(
            self, runner.S3_RUNNER_ERROR, runner.resolve_budget,
            run_mode="SMOKE", prereg=self.prereg, smoke_overrides=bad_outer,
        )
        bad_budget = dict(overrides, budgets=[96])
        _assert_error_code(
            self, runner.S3_RUNNER_ERROR, runner.resolve_budget,
            run_mode="SMOKE", prereg=self.prereg, smoke_overrides=bad_budget,
        )
        _assert_error_code(
            self, runner.S3_RUNNER_ERROR, runner.resolve_budget,
            run_mode="SMOKE", prereg=self.prereg, smoke_overrides=None,
        )

    def test_expected_record_counts(self):
        specs = _campaign_specs(10)
        counts = runner._expected_record_counts(
            run_mode="SMOKE", train_models_count=2, outer_steps=2, main_specs=specs
        )
        self.assertEqual(counts["train"], 4)
        self.assertEqual(counts["eval"], 5 * (64 + 128))
        self.assertEqual(counts["total"], 4 + 960)


# ---------------------------------------------------------------------------
# M2 冻结产物（FORMAL 只加载、不重训）
# ---------------------------------------------------------------------------
class FrozenArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = repo_info()
        cls.repo = Path(cls.info["repo"])
        cls.prereg = cls.info["prereg"]
        cls.meta_seeds = [0, 1, 2]
        cls.tmp = tempfile.TemporaryDirectory(prefix="s3-runner-frozen-")
        cls.out = Path(cls.tmp.name) / "run"
        cls.budget = runner.resolve_budget(run_mode="FORMAL", prereg=cls.prereg, smoke_overrides=None)
        cls.package = runner.load_family_package(cls.repo / sp.S3_FAMILY_PACKAGE_RELPATH)
        cls.banks = runner.load_frozen_episode_banks(
            repo_root=cls.repo, prereg=cls.prereg, meta_seeds=cls.meta_seeds
        )
        cls.models = runner.load_frozen_models(
            repo_root=cls.repo, prereg=cls.prereg, meta_seeds=cls.meta_seeds
        )
        cls.manifest = runner.load_frozen_model_manifest(
            repo_root=cls.repo,
            prereg=cls.prereg,
            models=cls.models,
            episode_banks=cls.banks,
            run_id="formal-frozen",
            created_utc=support.CREATED_UTC,
            out=cls.out,
        )
        cls.gate = runner.load_frozen_gate(repo_root=cls.repo, prereg=cls.prereg, run_mode="FORMAL")
        cls.artifacts = runner._prepare_artifacts(
            out=cls.out / "full",
            run_id="formal-frozen",
            run_mode="FORMAL",
            prereg=cls.prereg,
            budget=cls.budget,
            package=cls.package,
            repo_root=cls.repo,
            created_utc=support.CREATED_UTC,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_load_frozen_gate(self):
        self.assertEqual(self.gate["sha256"], self.prereg["fd_gate_sha256"])
        self.assertEqual(self.gate["path"], sp.S3_GATE_RELPATH)
        self.assertTrue(self.gate["frozen"])
        payload = self.gate["payload"]
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(payload["coordinates_per_model"], sp.S3_FD_GATE_COORDINATES_PER_MODEL)
        self.assertEqual(
            payload["coordinates_total"],
            sp.S3_FD_GATE_COORDINATES_PER_MODEL * len(sp.S3_FD_GATE_MODEL_KEYS),
        )
        self.assertFalse(payload["override"])

    def test_load_frozen_models(self):
        self.assertEqual(len(self.models), 6)
        for kind in sp.S3_MODEL_KINDS:
            for seed in self.meta_seeds:
                entry = self.models[(kind, seed)]
                self.assertEqual(entry["sha256"], self.info["frozen"]["model_sha256"][(kind, seed)])
                self.assertEqual(entry["bytes"], len((self.repo / entry["path"]).read_bytes()))
                self.assertEqual(entry["config"], runner.model_config_dict(kind, seed))
                parameters = entry["parameters"].to_dict()
                self.assertEqual(parameters["names"][0], "layer_0_weight")
                first_tensor = parameters["tensors"][0]
                self.assertIsInstance(first_tensor, list)
                self.assertEqual(len(first_tensor), 64)
                self.assertEqual(len(first_tensor[0]), 12)

    def test_load_frozen_episode_banks(self):
        self.assertEqual(sorted(self.banks), [0, 1, 2])
        for seed, bank in self.banks.items():
            self.assertEqual(bank["episodes"], 1600)
            self.assertEqual(bank["sha256"], self.info["bank_sha256"][seed])
            self.assertEqual(bank["path"], "models/episode_bank_meta_" + str(seed) + ".jsonl")
            self.assertIsNone(bank["episodes_list"])

    def test_load_frozen_model_manifest(self):
        copied = runner.read_json_file(self.out / runner.S3_RUNNER_MODEL_MANIFEST_FILE)
        self.assertEqual(set(copied["verification"]), {"loaded_from_prereg", "prereg_models_sha256", "verified_utc", "source"})
        self.assertTrue(copied["verification"]["loaded_from_prereg"])
        self.assertEqual(copied["run_id"], "formal-frozen")
        self.assertEqual(len(copied["models"]), 6)
        for row in copied["models"]:
            self.assertEqual(set(row), set(sp.S3_MODEL_ENTRY_FIELDS))
        self.assertEqual(len(self.manifest["entries"]), 6)

    def test_prepare_formal_artifacts(self):
        artifacts = self.artifacts
        self.assertEqual(artifacts["train_tasks"], [])
        self.assertEqual(artifacts["train"]["train_records"], [])
        self.assertEqual(len(artifacts["train"]["models"]), 6)
        self.assertEqual(artifacts["gate"]["path"], runner.S3_RUNNER_GATE_FILE)
        out = self.out / "full"
        for seed in self.meta_seeds:
            self.assertTrue((out / "models" / ("episode_bank_meta_" + str(seed) + ".jsonl")).is_file())
        for name in (runner.S3_RUNNER_GATE_FILE, runner.S3_RUNNER_MODEL_MANIFEST_FILE):
            self.assertTrue((out / name).is_file())
        self.assertEqual(
            sp.sha256_file(out / runner.S3_RUNNER_GATE_FILE), self.prereg["fd_gate_sha256"]
        )
        for seed, bank in artifacts["episode_banks"].items():
            self.assertEqual(sp.sha256_file(out / "models" / ("episode_bank_meta_" + str(seed) + ".jsonl")), bank["sha256"])

    def _copy_repo(self, prefix):
        target = Path(tempfile.mkdtemp(prefix=prefix))
        shutil.copytree(self.repo, target, dirs_exist_ok=True)
        return target

    def test_prepare_formal_missing_manifest_fails(self):
        copied = self._copy_repo("s3-runner-nomanifest-")
        (copied / sp.S3_MODEL_MANIFEST_RELPATH).unlink()
        with tempfile.TemporaryDirectory() as tmp:
            _assert_error_code(
                self, runner.S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, runner._prepare_artifacts,
                out=Path(tmp) / "run",
                run_id="formal-missing",
                run_mode="FORMAL",
                prereg=self.prereg,
                budget=self.budget,
                package=self.package,
                repo_root=copied,
                created_utc=support.CREATED_UTC,
            )

    def test_tampered_model_detected(self):
        copied = self._copy_repo("s3-runner-tamper-model-")
        model_path = copied / self.models[("fomaml", 0)]["path"]
        data = model_path.read_bytes()
        model_path.write_bytes(data.replace(b'"meta_seed":0', b'"meta_seed":1', 1))
        _assert_error_code(
            self, runner.S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, runner.load_frozen_models,
            repo_root=copied, prereg=self.prereg, meta_seeds=self.meta_seeds,
        )

    def test_tampered_gate_detected(self):
        copied = self._copy_repo("s3-runner-tamper-gate-")
        gate_path = copied / sp.S3_GATE_RELPATH
        payload = runner.read_json_file(gate_path)
        payload["status"] = "FAIL"
        runner.write_json_canonical(gate_path, payload)
        _assert_error_code(
            self, runner.S3_RUNNER_FROZEN_ARTIFACT_MISMATCH, runner.load_frozen_gate,
            repo_root=copied, prereg=self.prereg, run_mode="FORMAL",
        )

    def test_verify_fd_gate_payload_rejects_tamper(self):
        payload = runner.read_json_file(self.repo / sp.S3_GATE_RELPATH)
        tampered = json.loads(json.dumps(payload))
        tampered["status"] = "FAIL"
        _assert_error_code(
            self, runner.S3_RUNNER_GATE_ERROR, runner.verify_fd_gate_payload,
            tampered, run_mode="FORMAL",
        )
        wrong_coordinates = json.loads(json.dumps(payload))
        wrong_coordinates["coordinates_per_model"] = 16
        _assert_error_code(
            self, runner.S3_RUNNER_GATE_ERROR, runner.verify_fd_gate_payload,
            wrong_coordinates, run_mode="FORMAL",
        )


# ---------------------------------------------------------------------------
# run_config / data_manifest / 确定性子集
# ---------------------------------------------------------------------------
class ConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = repo_info()
        cls.repo = Path(cls.info["repo"])
        cls.prereg = cls.info["prereg"]
        cls.package = runner.load_family_package(cls.repo / sp.S3_FAMILY_PACKAGE_RELPATH)
        cls.budget = runner.resolve_budget(run_mode="FORMAL", prereg=cls.prereg, smoke_overrides=None)
        cls.tmp = tempfile.TemporaryDirectory(prefix="s3-runner-config-")
        cls.artifacts = runner._prepare_artifacts(
            out=Path(cls.tmp.name) / "run",
            run_id="formal-config",
            run_mode="FORMAL",
            prereg=cls.prereg,
            budget=cls.budget,
            package=cls.package,
            repo_root=cls.repo,
            created_utc=support.CREATED_UTC,
        )
        cls.main_specs = runner.build_main_run_specs(
            tasks=cls.artifacts["by_split"]["meta_test"],
            meta_seeds=[0, 1, 2],
            opt_seeds=[0, 1, 2, 3, 4],
            budgets=[64, 128],
            eval_task_count=20,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_build_main_run_specs_grid(self):
        self.assertEqual(len(self.main_specs), 3000)
        self.assertEqual(sum(int(spec["budget"]) for spec in self.main_specs), 288000)
        first = self.main_specs[0]
        self.assertEqual(first["arm"], sp.S3_ARMS[0])
        self.assertEqual(first["split"], "meta_test")
        self.assertEqual(first["phase"], runner.eval_phase_for_split("meta_test"))

    def test_build_run_config_formal(self):
        record_counts = runner._expected_record_counts(
            run_mode="FORMAL", train_models_count=0, outer_steps=200, main_specs=self.main_specs
        )
        notes = runner._scope_notes(
            run_mode="FORMAL", workers=1, smoke_overrides=None,
            record_streams={"main": len(self.main_specs), "nc": 0, "ood": 0, "det": 0},
        )
        config = runner.build_run_config(
            run_id="formal-config",
            run_mode="FORMAL",
            budget=self.budget,
            prereg=self.prereg,
            family_package=self.package,
            episode_banks=self.artifacts["episode_banks"],
            model_block=self.artifacts["train"],
            gate=self.artifacts["gate"],
            main_specs=self.main_specs,
            record_counts=record_counts,
            scope_notes=notes,
        )
        self.assertEqual(tuple(config), sp.S3_RUN_CONFIG_REQUIRED_FIELDS)
        self.assertEqual(config["k_sweep"], [5])
        self.assertEqual(config["fd_or_gradient_gate"]["sha256"], self.prereg["fd_gate_sha256"])
        self.assertEqual(config["fd_or_gradient_gate"]["mode"], "FORMAL")
        self.assertFalse(config["fd_or_gradient_gate"]["override"])
        self.assertEqual(config["evaluation_grid"]["main_runs"], 3000)
        self.assertEqual(config["evaluation_grid"]["main_evals"], 288000)
        self.assertEqual(config["evaluation_grid"]["eval_split"], "meta_test")
        self.assertEqual(config["record_counts"], {"train": 0, "eval": 288000, "total": 288000})
        self.assertEqual(config["record_schemas"]["train"], list(sp.S3_TRAIN_RECORD_FIELDS))
        self.assertEqual(config["record_schemas"]["eval"], list(sp.S3_EVAL_RECORD_FIELDS))
        self.assertEqual(config["episode_bank"]["banks"]["meta_seed_0"], self.info["bank_sha256"][0])
        self.assertEqual(len(config["episode_bank"]["files"]), 3)
        self.assertEqual(config["physical_call_count"], 0)
        self.assertEqual(config["evidence_scope"], sp.S3_EVIDENCE_SCOPE)
        self.assertNotIn("smoke_overrides", config)
        self.assertEqual(set(config["models"]), {"fomaml", "anil"})
        self.assertEqual(len(config["models"]["fomaml"]["models"]), 3)

    def test_build_run_config_rejects_k_sweep(self):
        bad_budget = dict(self.budget, k_sweep=[3])
        notes = runner._scope_notes(run_mode="FORMAL", workers=1, smoke_overrides=None, record_streams={})
        record_counts = runner._expected_record_counts(
            run_mode="FORMAL", train_models_count=0, outer_steps=200, main_specs=self.main_specs
        )
        _assert_error_code(
            self, runner.S3_RUNNER_PREREG_ERROR, runner.build_run_config,
            run_id="bad",
            run_mode="FORMAL",
            budget=bad_budget,
            prereg=self.prereg,
            family_package=self.package,
            episode_banks=self.artifacts["episode_banks"],
            model_block=self.artifacts["train"],
            gate=self.artifacts["gate"],
            main_specs=self.main_specs,
            record_counts=record_counts,
            scope_notes=notes,
        )

    def test_build_data_manifest(self):
        manifest = runner.build_data_manifest(
            run_id="formal-config",
            prereg=self.prereg,
            by_split=self.artifacts["by_split"],
            synthetic_call_count=0,
            artifact_sha256={"b": "2", "a": "1"},
        )
        self.assertEqual(tuple(manifest), sp.S3_DATA_MANIFEST_FIELDS)
        self.assertEqual(set(manifest["split_task_ids"]), set(sp.S3_ALLOWED_SPLITS))
        counts = {split: len(ids) for split, ids in manifest["split_task_ids"].items()}
        self.assertEqual(counts["meta_train"], 60)
        self.assertEqual(counts["meta_validation"], 20)
        self.assertEqual(counts["meta_test"], 20)
        self.assertEqual(counts["meta_test_ood"], 10)
        self.assertEqual(counts["meta_test_negative_control"], 10)
        self.assertEqual(counts["dev"], 0)
        self.assertEqual(list(manifest["artifact_sha256"]), ["a", "b"])
        self.assertEqual(manifest["holdout_truth_read_phase"], "EVAL")
        self.assertEqual(manifest["physical_call_count"], 0)
        self.assertEqual(manifest["solver_processes_started"], 0)
        self.assertEqual(
            manifest["split_task_ids_sha256"]["meta_test"],
            sp.canonical_sha256(manifest["split_task_ids"]["meta_test"]),
        )

    def test_select_determinism_specs_matches_prereg(self):
        specs = runner.select_determinism_specs(self.main_specs, prereg=self.prereg)
        self.assertEqual(len(specs), 60)
        keys = [runner.canonical_run_key(spec) for spec in specs]
        self.assertEqual(
            sp.determinism_run_keys_sha256(keys),
            self.prereg["determinism"]["subset_run_keys_sha256"],
        )
        budgets = [int(spec["budget"]) for spec in specs]
        self.assertEqual(budgets.count(64), 30)
        self.assertEqual(budgets.count(128), 30)

    def test_select_determinism_detects_tamper(self):
        tampered = json.loads(json.dumps(self.prereg))
        tampered["determinism"]["subset_run_keys_sha256"] = "0" * 64
        _assert_error_code(
            self, runner.S3_RUNNER_VALIDATION_ERROR, runner.select_determinism_specs,
            self.main_specs, prereg=tampered,
        )


# ---------------------------------------------------------------------------
# W=8 试点门 family 块：真实族包 payload 字段（R2 字段错位回归）
# ---------------------------------------------------------------------------
class W8PilotGateFamilyBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="s3-runner-w8-family-")
        cls.tasks = tf.build_s3_conflict_family(delta1_base=0.20)
        payload = tf.build_s3_family_package(
            cls.tasks,
            delta1_base=0.20,
            created_utc=support.CREATED_UTC,
            code_sha="a" * 64,
        )
        cls.package_path = Path(cls.tmp.name) / "family_package_s3.json"
        cls.written = tf.write_s3_family_package(cls.package_path, payload)
        cls.package = runner.load_family_package(cls.package_path)
        cls.selection = sorted(
            (task for task in cls.tasks if task.split == "meta_validation"),
            key=lambda task: task.task_id,
        )[: int(sp.S3_W8_PILOT_TASKS)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _block(self):
        return runner._w8_family_block(
            self.package,
            package_relpath=sp.S3_FAMILY_PACKAGE_RELPATH,
            tasks=self.selection,
        )

    def test_family_block_reads_payload_fields(self):
        # 根因回归：family_id/formula_version 在 package["payload"] 内，不在顶层。
        self.assertNotIn("family_id", self.package)
        self.assertNotIn("formula_version", self.package)
        self.assertEqual(self.package["payload"]["family_id"], tf.S3_FAMILY_ID)
        self.assertEqual(self.package["payload"]["formula_version"], tf.S3_FORMULA_VERSION)
        block = self._block()
        self.assertEqual(
            list(block),
            [
                "family_id",
                "formula_version",
                "family_package_path",
                "family_package_sha256",
                "task_ids",
                "task_ids_sha256",
            ],
        )
        self.assertEqual(block["family_id"], tf.S3_FAMILY_ID)
        self.assertEqual(block["formula_version"], tf.S3_FORMULA_VERSION)
        self.assertEqual(block["family_package_path"], sp.S3_FAMILY_PACKAGE_RELPATH)
        self.assertEqual(block["family_package_sha256"], self.written["family_package_sha256"])
        self.assertEqual(block["family_package_sha256"], self.package["sha256"])
        self.assertEqual(block["task_ids"], [task.task_id for task in self.selection])
        self.assertEqual(len(block["task_ids"]), int(sp.S3_W8_PILOT_TASKS))
        self.assertEqual(block["task_ids_sha256"], sp.task_ids_sha256(block["task_ids"]))
        self.assertNotEqual(block["task_ids_sha256"], self.package["task_ids_sha256"])

    def test_family_block_rejects_missing_payload(self):
        exc = _assert_error_code(
            self, runner.S3_RUNNER_FAMILY_ERROR, runner._w8_family_block,
            {"sha256": "0" * 64, "bytes": 0},
            package_relpath="x.json",
            tasks=self.selection,
        )
        self.assertIn("payload", str(exc))

    def test_family_block_rejects_payload_mismatch(self):
        tampered = {"sha256": self.package["sha256"], "payload": json.loads(json.dumps(self.package["payload"]))}
        tampered["payload"]["family_id"] = "F-OTHER"
        _assert_error_code(
            self, runner.S3_RUNNER_FAMILY_ERROR, runner._w8_family_block,
            tampered,
            package_relpath="x.json",
            tasks=self.selection,
        )
        tampered2 = {"sha256": self.package["sha256"], "payload": json.loads(json.dumps(self.package["payload"]))}
        tampered2["payload"]["split_counts"] = {"meta_train": 1}
        _assert_error_code(
            self, runner.S3_RUNNER_FAMILY_ERROR, runner._w8_family_block,
            tampered2,
            package_relpath="x.json",
            tasks=self.selection,
        )

if __name__ == "__main__":
    unittest.main()
