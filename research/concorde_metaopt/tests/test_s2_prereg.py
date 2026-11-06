"""S2 预注册（s2_prereg）单元测试：canonical/digest、固定节、v1.5 resource_limits、fail-closed 负控。

覆盖计划 §7 / §12：
- canonical JSON、ids_sha256、code_sha 文件清单算法、parse_sha256sums 的固定向量；
- build_preregistration 固定字段（upstream/physical=0/arms 公平/fd_gate/frozen_package 双 family 版本/
  failure_rules/stopping_rules/resource_limits 三键 int）；
- prereg_id 同时剔除 id+digest、prereg_digest 仅剔除自身、analysis_plan_digest 四节复算；
- 写读往返与拒绝覆盖；
- 负控：digest 篡改、schema_version、physical_call_count、prereg_id 格式、placeholder、code_sha、
  frozen_package task_family_version、data_boundary holdout sha、fd_gate 坐标、pilot 绝对路径/缺文件/sha、
  stale analysis_plan_digest、legacy prereg 缺 resource_limits、resource_limits 缺键/多键/浮点/布尔/改值
  （改值后重新签名仍必须被 S2_PREREG_RESOURCE_LIMITS_INVALID 拒绝）。
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.meta_learning import s2_prereg as sp

REPO_ROOT = Path(__file__).resolve().parents[3]
CREATED_UTC = "2026-11-07T00:00:00+00:00"
BANK_SHA = "0" * 64


def resign(prereg):
    """篡改后重新签名：analysis_plan_digest → prereg_id → prereg_digest（保持自洽，测试更深层校验）。"""
    prereg["analysis_plan_digest"] = sp.analysis_plan_digest(
        {key: prereg[key] for key in ("endpoints", "comparison", "statistical_plan", "fd_gate")}
    )
    prereg["prereg_id"] = sp.compute_prereg_id(prereg)
    prereg["prereg_digest"] = sp.compute_prereg_digest(prereg)
    return prereg


class PreregCanonicalAndHelperTests(unittest.TestCase):
    def test_01_canonical_json_rules(self):
        payload = {"b": [3, 2, 1], "a": "中文", "c": 1.5, "d": True, "e": None}
        text = sp.canonical_json(payload)
        self.assertEqual(text, '{"a":"中文","b":[3,2,1],"c":1.5,"d":true,"e":null}')
        self.assertNotIn(" ", text)
        self.assertTrue(sp.canonical_json_line(payload).endswith("\n"))
        self.assertTrue(sp.canonical_json_line(payload).endswith(sp.canonical_json(payload) + "\n"))

    def test_02_sha256_text_and_bytes(self):
        self.assertEqual(sp.sha256_text("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(sp.sha256_bytes(b"abc"), sp.sha256_text("abc"))
        self.assertEqual(sp.canonical_sha256({"a": 1}), sp.sha256_text('{"a":1}\n'))

    def test_03_ids_sha256_sorted_with_trailing_newline(self):
        expected = sp.sha256_text("\n".join(sorted(["t-b", "t-a", "t-c"])) + "\n")
        self.assertEqual(sp.ids_sha256(["t-b", "t-a", "t-c"]), expected)
        self.assertEqual(sp.ids_sha256(["t-a", "t-b", "t-c"]), expected)
        self.assertEqual(sp.ids_sha256([]), sp.sha256_text("\n"))

    def test_04_parse_sha256sums_git_style(self):
        text = "a" * 64 + " *tasks.json\n" + "b" * 64 + "  meta_task_split.json\n"
        entries = sp.parse_sha256sums(text)
        self.assertEqual(entries, [("tasks.json", "a" * 64), ("meta_task_split.json", "b" * 64)])
        with self.assertRaises(sp.S2PreregError):
            sp.parse_sha256sums("not-a-sha *file\n")
        with self.assertRaises(sp.S2PreregError):
            sp.parse_sha256sums("0" * 64 + "\n")
        self.assertEqual(sp.parse_sha256sums("\n\n"), [])

    def test_05_code_sha_for_files_fixed_vector(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("print('a')\n", encoding="utf-8")
            (root / "b.py").write_text("print('b')\n", encoding="utf-8")
            first = sp.code_sha_for_files(["a.py", "b.py"], root)
            second = sp.code_sha_for_files(["b.py", "a.py"], root)
            self.assertEqual(first, second, "code_sha 必须按路径字典序拼接（与入参顺序无关）")
            raw_a = (root / "a.py").read_bytes()
            raw_b = (root / "b.py").read_bytes()
            concatenated = (
                b"a.py\n" + sp.sha256_bytes(raw_a).encode("ascii") + b"\n"
                + b"b.py\n" + sp.sha256_bytes(raw_b).encode("ascii") + b"\n"
            )
            self.assertEqual(first, sp.sha256_bytes(concatenated))

    def test_06_analysis_plan_digest_only_four_sections(self):
        base = {"endpoints": {"x": 1}, "comparison": {"y": 2}, "statistical_plan": {"z": 3}, "fd_gate": {"w": 4}}
        digest = sp.analysis_plan_digest(base)
        self.assertEqual(
            digest,
            sp.canonical_sha256(
                {"endpoints": {"x": 1}, "comparison": {"y": 2}, "statistical_plan": {"z": 3}, "fd_gate": {"w": 4}}
            ),
        )
        extra = dict(base, other={"ignored": True})
        self.assertEqual(sp.analysis_plan_digest(extra), digest, "四节以外的字段不得影响 analysis_plan_digest")

    def test_07_prereg_id_excludes_id_and_digest_digest_excludes_only_digest(self):
        payload = {
            "schema_version": sp.SCHEMA_VERSION,
            "prereg_id": "p4ra-s2-prereg-" + "0" * 16,
            "prereg_digest": "1" * 64,
            "x": [1, 2, 3],
        }
        without_both = {key: value for key, value in payload.items() if key not in ("prereg_id", "prereg_digest")}
        self.assertEqual(sp.compute_prereg_id(payload), sp.PREREG_ID_PREFIX + sp.canonical_sha256(without_both)[:16])
        without_digest = {key: value for key, value in payload.items() if key != "prereg_digest"}
        self.assertEqual(sp.compute_prereg_digest(payload), sp.canonical_sha256(without_digest))
        changed_id = dict(payload, prereg_id="p4ra-s2-prereg-" + "f" * 16)
        self.assertEqual(sp.compute_prereg_id(changed_id), sp.compute_prereg_id(payload), "prereg_id 不得依赖自身")
        self.assertNotEqual(sp.compute_prereg_digest(changed_id), sp.compute_prereg_digest(payload), "prereg_digest 覆盖 prereg_id")

    def test_08_placeholder_rejection(self):
        self.assertEqual(sp.find_placeholders({"a": "TBD"}), ["TBD"])
        self.assertEqual(sp.find_placeholders({"a": ["<fill me>", "ok"]}), ["<fill me>"])
        with self.assertRaises(sp.S2PreregError) as context:
            sp.reject_placeholders({"a": "TODO"})
        self.assertIn(sp.S2_PREREG_PLACEHOLDER_REJECTED, str(context.exception))


class PreregistrationBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = sp.build_preregistration(
            repo_root=REPO_ROOT,
            created_utc=CREATED_UTC,
            train_episode_bank_sha256=BANK_SHA,
        )

    def fresh(self):
        return copy.deepcopy(self.base)

    def test_01_verify_build_ok(self):
        self.assertTrue(sp.verify_preregistration(self.fresh(), repo_root=REPO_ROOT))

    def test_02_required_keys_and_fixed_sections(self):
        prereg = self.fresh()
        for key in sp.REQUIRED_TOP_KEYS:
            self.assertIn(key, prereg)
        self.assertEqual(prereg["schema_version"], sp.SCHEMA_VERSION)
        self.assertEqual(prereg["upstream"], sp.UPSTREAM)
        self.assertEqual(prereg["upstream"]["issue"], "#7")
        self.assertEqual(prereg["physical_call_count"], 0)
        self.assertEqual(prereg["training_budget"], sp.TRAINING_BUDGET)
        self.assertEqual(prereg["evaluation_grid"], sp.EVALUATION_GRID)
        self.assertEqual(prereg["endpoints"], sp.ENDPOINTS)
        self.assertEqual(prereg["comparison"], sp.COMPARISON)
        self.assertEqual(prereg["statistical_plan"], sp.STATISTICAL_PLAN)
        self.assertEqual(prereg["determinism"], sp.DETERMINISM)
        self.assertEqual(prereg["failure_rules"], sp.FAILURE_RULES)
        self.assertEqual(prereg["stopping_rules"], sp.STOPPING_RULES)
        self.assertEqual(prereg["episode_contract"]["train_episode_bank_sha256"], BANK_SHA)
        contract_body = {key: value for key, value in prereg["episode_contract"].items() if key != "train_episode_bank_sha256"}
        self.assertEqual(contract_body, sp.EPISODE_CONTRACT)

    def test_03_v15_resource_limits_fixed_ints(self):
        prereg = self.fresh()
        self.assertEqual(prereg["resource_limits"], {"per_seed_train_wall_s": 1200, "peak_memory_mb": 8192, "total_wall_s": 7200})
        self.assertEqual(set(prereg["resource_limits"]), set(sp.RESOURCE_LIMITS))
        for key, value in prereg["resource_limits"].items():
            self.assertIs(type(value), int, f"resource_limits.{key} 必须是 int")
            self.assertEqual(value, sp.RESOURCE_LIMITS[key])
        self.assertEqual(
            sp.FAILURE_RULES[1],
            "resource_limit(per_seed_train_wall_s>1200 or peak_memory_mb>8192) -> RESOURCE_LIMIT, stop entire run, no retry",
        )
        self.assertEqual(sp.STOPPING_RULES[-1], "total_wall_s>7200 -> stop, report partial products")

    def test_04_arms_fairness_and_family_versions(self):
        prereg = self.fresh()
        arms = prereg["arms"]
        self.assertEqual([arm["id"] for arm in arms], ["FULL_MAML", "FOMAML"])
        self.assertIs(arms[0]["first_order"], False)
        self.assertIs(arms[1]["first_order"], True)
        self.assertEqual(arms[0]["config"], sp.BASE_ARM_CONFIG)
        self.assertEqual(arms[1]["config"], sp.BASE_ARM_CONFIG)
        frozen = prereg["frozen_package"]
        self.assertEqual(frozen["package_family_version"], "p4ra-family-v4")
        self.assertEqual(frozen["task_family_version"], "p4ra-family-v3")
        self.assertEqual(set(frozen), set(sp.FROZEN_PACKAGE_KEYS))

    def test_05_pilot_artifacts_sha_matches_files(self):
        prereg = self.fresh()
        artifacts = prereg["fd_gate"]["pilot_artifacts"]
        self.assertEqual(set(artifacts), {"micro", "full_size"})
        for name, entry in artifacts.items():
            self.assertEqual(set(entry), {"path", "sha256"})
            path = Path(entry["path"])
            self.assertFalse(path.is_absolute())
            self.assertEqual(entry["sha256"], sp.sha256_file(REPO_ROOT / path), f"pilot {name} sha 与文件不一致")

    def test_06_data_boundary_splits(self):
        boundary = self.fresh()["data_boundary"]
        self.assertEqual(boundary["allowed_splits"], list(sp.ALLOWED_SPLITS))
        self.assertEqual(boundary["forbidden_splits"], list(sp.FORBIDDEN_SPLITS))
        self.assertEqual(boundary["split_counts"], sp.EXPECTED_SPLIT_COUNTS)
        self.assertEqual(boundary["holdout_rows_used"], 0)
        for key in ("meta_train_task_ids_sha256", "meta_validation_task_ids_sha256", "holdout_task_ids_sha256"):
            self.assertRegex(boundary[key], r"^[0-9a-f]{64}$")

    def test_07_prereg_id_and_digest_self_consistent(self):
        prereg = self.fresh()
        self.assertRegex(prereg["prereg_id"], r"^p4ra-s2-prereg-[0-9a-f]{16}$")
        self.assertRegex(prereg["prereg_digest"], r"^[0-9a-f]{64}$")
        self.assertEqual(prereg["prereg_id"], sp.compute_prereg_id(prereg))
        self.assertEqual(prereg["prereg_digest"], sp.compute_prereg_digest(prereg))
        self.assertEqual(prereg["analysis_plan_digest"], sp.analysis_plan_digest(prereg))

    def test_08_write_read_roundtrip_and_refuse_overwrite(self):
        prereg = self.fresh()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "prereg.json"
            written = sp.write_preregistration(prereg, path)
            self.assertEqual(written, path)
            raw = path.read_bytes()
            self.assertTrue(raw.endswith(b"\n"))
            self.assertNotIn(b"\r\n", raw)
            self.assertEqual(raw, (sp.canonical_json(prereg) + "\n").encode("utf-8"))
            loaded = sp.read_preregistration(path)
            self.assertEqual(loaded, prereg)
            with self.assertRaises(sp.S2PreregError):
                sp.write_preregistration(prereg, path)


class PreregistrationVerifyNegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = sp.build_preregistration(
            repo_root=REPO_ROOT,
            created_utc=CREATED_UTC,
            train_episode_bank_sha256=BANK_SHA,
        )

    def fresh(self):
        return copy.deepcopy(self.base)

    def assert_rejected(self, prereg, code, *, resign_payload=False, **kwargs):
        if resign_payload:
            resign(prereg)
        with self.assertRaises(sp.S2PreregError) as context:
            sp.verify_preregistration(prereg, repo_root=REPO_ROOT, **kwargs)
        self.assertIn(code, str(context.exception))
        return str(context.exception)

    def test_01_digest_tamper_without_resign(self):
        prereg = self.fresh()
        prereg["failure_rules"][0] = "tampered"
        self.assert_rejected(prereg, sp.S2_PREREG_DIGEST_MISMATCH)

    def test_02_schema_version(self):
        prereg = self.fresh()
        prereg["schema_version"] = "p4ra-s2-prereg-v0"
        self.assert_rejected(prereg, sp.S2_PREREG_SCHEMA_ERROR)

    def test_03_physical_call_count(self):
        prereg = self.fresh()
        prereg["physical_call_count"] = 1
        self.assert_rejected(prereg, sp.S2_PREREG_SCHEMA_ERROR, resign_payload=True)

    def test_04_prereg_id_format(self):
        prereg = self.fresh()
        prereg["prereg_id"] = "p4ra-s2-prereg-XYZ"
        self.assert_rejected(prereg, sp.S2_PREREG_SCHEMA_ERROR)

    def test_05_placeholder(self):
        prereg = self.fresh()
        prereg["created_utc"] = "TBD"
        self.assert_rejected(prereg, sp.S2_PREREG_PLACEHOLDER_REJECTED)

    def test_06_code_sha_expected_mismatch(self):
        self.assert_rejected(self.fresh(), sp.S2_CODE_SHA_MISMATCH, expected_code_sha="f" * 64)

    def test_07_code_sha_worktree_mismatch(self):
        prereg = self.fresh()
        prereg["code_sha"] = "e" * 64
        resign(prereg)
        # 复算 digest 通过后，verify_code_sha 检测与当前工作树不一致
        with self.assertRaises(sp.S2PreregError) as context:
            sp.verify_preregistration(prereg, repo_root=REPO_ROOT)
        self.assertIn(sp.S2_CODE_SHA_MISMATCH, str(context.exception))

    def test_08_frozen_task_family_version(self):
        prereg = self.fresh()
        prereg["frozen_package"]["task_family_version"] = "p4ra-family-v2"
        self.assert_rejected(prereg, sp.S2_FROZEN_PACKAGE_MISMATCH, resign_payload=True)

    def test_09_data_boundary_holdout_sha(self):
        prereg = self.fresh()
        prereg["data_boundary"]["holdout_task_ids_sha256"] = "a" * 64
        self.assert_rejected(prereg, sp.S2_DATA_BOUNDARY_ERROR, resign_payload=True)

    def test_10_fd_gate_coordinates(self):
        prereg = self.fresh()
        prereg["fd_gate"]["coordinates"] = 16
        self.assert_rejected(prereg, sp.S2_PREREG_SCHEMA_ERROR, resign_payload=True)

    def test_11_pilot_absolute_path(self):
        prereg = self.fresh()
        prereg["fd_gate"]["pilot_artifacts"]["micro"]["path"] = str(REPO_ROOT / prereg["fd_gate"]["pilot_artifacts"]["micro"]["path"])
        self.assert_rejected(prereg, sp.S2_PILOT_ARTIFACT_INVALID, resign_payload=True)

    def test_12_pilot_missing_file(self):
        prereg = self.fresh()
        entry = prereg["fd_gate"]["pilot_artifacts"]["full_size"]
        entry["path"] = "research/concorde_metaopt/evidence/s2/does_not_exist.json"
        self.assert_rejected(prereg, sp.S2_PILOT_ARTIFACT_INVALID, resign_payload=True)

    def test_13_pilot_sha_mismatch(self):
        prereg = self.fresh()
        prereg["fd_gate"]["pilot_artifacts"]["micro"]["sha256"] = "b" * 64
        self.assert_rejected(prereg, sp.S2_PILOT_ARTIFACT_INVALID, resign_payload=True)

    def test_14_stale_analysis_plan_digest(self):
        prereg = self.fresh()
        prereg["analysis_plan_digest"] = "c" * 64
        prereg["prereg_id"] = sp.compute_prereg_id(prereg)
        prereg["prereg_digest"] = sp.compute_prereg_digest(prereg)
        self.assert_rejected(prereg, sp.S2_PREREG_DIGEST_MISMATCH)

    def test_15_legacy_prereg_without_resource_limits(self):
        prereg = self.fresh()
        del prereg["resource_limits"]
        self.assert_rejected(prereg, sp.S2_PREREG_SCHEMA_ERROR, resign_payload=True)

    def test_16_resource_limits_wrong_values(self):
        for mutation in (
            {"per_seed_train_wall_s": 1201},
            {"peak_memory_mb": 4096},
            {"total_wall_s": 3600},
        ):
            prereg = self.fresh()
            prereg["resource_limits"].update(mutation)
            self.assert_rejected(prereg, sp.S2_PREREG_RESOURCE_LIMITS_INVALID, resign_payload=True)

    def test_17_resource_limits_wrong_types(self):
        for mutation in (
            {"per_seed_train_wall_s": 1200.0},
            {"peak_memory_mb": True},
            {"total_wall_s": "7200"},
        ):
            prereg = self.fresh()
            prereg["resource_limits"].update(mutation)
            self.assert_rejected(prereg, sp.S2_PREREG_RESOURCE_LIMITS_INVALID, resign_payload=True)

    def test_18_resource_limits_key_set(self):
        prereg = self.fresh()
        del prereg["resource_limits"]["total_wall_s"]
        self.assert_rejected(prereg, sp.S2_PREREG_RESOURCE_LIMITS_INVALID, resign_payload=True)

        prereg = self.fresh()
        prereg["resource_limits"]["extra_limit"] = 1
        self.assert_rejected(prereg, sp.S2_PREREG_RESOURCE_LIMITS_INVALID, resign_payload=True)

        prereg = self.fresh()
        prereg["resource_limits"] = []
        self.assert_rejected(prereg, sp.S2_PREREG_RESOURCE_LIMITS_INVALID, resign_payload=True)

    def test_19_failure_and_stopping_rules_exact(self):
        prereg = self.fresh()
        prereg["failure_rules"][1] = "resource_limit -> RESOURCE_LIMIT, no retry"
        self.assert_rejected(prereg, sp.S2_PREREG_SCHEMA_ERROR, resign_payload=True)

        prereg = self.fresh()
        prereg["stopping_rules"][-1] = "hard_deadline_2h"
        self.assert_rejected(prereg, sp.S2_PREREG_SCHEMA_ERROR, resign_payload=True)

    def test_20_unknown_schema_version(self):
        prereg = self.fresh()
        prereg["schema_version"] = "p4ra-s2-prereg-v9"
        self.assert_rejected(prereg, sp.S2_PREREG_SCHEMA_ERROR)


if __name__ == "__main__":
    unittest.main()