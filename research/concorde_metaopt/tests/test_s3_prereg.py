"""S3 预注册（s3_prereg）测试：哈希固定向量、build/verify/write/read、证据绑定与负控。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research.concorde_metaopt.meta_learning import s3_prereg as sp
from research.concorde_metaopt.tests import test_s3_support as support

REPO_ROOT = support.REPO_ROOT
CREATED_UTC = support.CREATED_UTC
VECTORS = support.load_hash_vectors()


def vector(vector_id):
    return support.vector_by_id(VECTORS, vector_id)


def resign(prereg):
    payload = json.loads(json.dumps(prereg))
    payload.pop("prereg_id", None)
    payload.pop("prereg_digest", None)
    digest = sp.prereg_digest(payload)
    payload["prereg_digest"] = digest
    payload["prereg_id"] = sp.S3_PREREG_ID_PREFIX + digest[:16]
    return payload


class HashVectorTests(unittest.TestCase):
    def assert_raises_code(self, code, func, *args, **kwargs):
        with self.assertRaises(sp.S3PreregError) as ctx:
            func(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)

    def test_01_vector_canonical_payloads_self_consistent(self):
        for item in VECTORS["vectors"]:
            payload = item.get("canonical_payload")
            if payload is None:
                continue
            digest = sp.sha256_text(payload)
            if item["id"] == "V04":
                self.assertEqual(digest[: int(item["fingerprint_length"])], item["expected_sha256"])
            else:
                self.assertEqual(digest, item["expected_sha256"], item["id"])

    def test_02_v01_canonical_json(self):
        item = vector("V01")
        self.assertEqual(sp.canonical_json(item["input"]), item["canonical_payload"])
        self.assertEqual(sp.sha256_text(sp.canonical_json(item["input"])), item["expected_sha256"])

    def test_03_v02_v03_code_sha(self):
        for vector_id in ("V02", "V03"):
            item = vector(vector_id)
            self.assertEqual(sp.code_sha_from_files(item["files"]), item["expected_sha256"], vector_id)

    def test_04_v04_task_fingerprint(self):
        item = vector("V04")
        fingerprint = sp.task_fingerprint(**item["input"])
        self.assertEqual(fingerprint, item["expected_sha256"])
        self.assertEqual(len(fingerprint), int(item["fingerprint_length"]))

    def test_05_v05_task_ids_sha256(self):
        item = vector("V05")
        self.assertEqual(sp.task_ids_sha256(item["input"]["task_ids"]), item["expected_sha256"])

    def test_06_v06_analysis_plan_digest(self):
        item = vector("V06")
        self.assertEqual(sp.analysis_plan_digest(**item["input"]), item["expected_sha256"])

    def test_07_v07_package_sha256_algorithm(self):
        item = vector("V07")
        expected_payload = "\n".join(
            rel + "\t" + digest for rel, digest in sorted(item["files"].items())
        )
        self.assertEqual(expected_payload, item["canonical_payload"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "research" / "concorde_metaopt" / "evidence" / "s3"
            for rel in item["files"]:
                target = evidence / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"payload-" + rel.encode("utf-8"))
            (evidence / "SHA256SUMS.txt").write_text("ignored\n", encoding="utf-8")
            (evidence / "PACKAGE_MANIFEST.json").write_text("{}\n", encoding="utf-8")
            lines = []
            for path in sorted(evidence.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(evidence).as_posix()
                if rel in ("SHA256SUMS.txt", "PACKAGE_MANIFEST.json"):
                    continue
                lines.append(rel + "\t" + sp.sha256_bytes(path.read_bytes()))
            expected = sp.sha256_text("\n".join(lines))
            self.assertEqual(sp.package_sha256(root), expected)

    def test_08_v08_prereg_digest(self):
        item = vector("V08")
        self.assertEqual(sp.prereg_digest(item["input"]), item["expected_sha256"])

    def test_09_v09_v10_record_episode_digest(self):
        record = vector("V09")
        episode = vector("V10")
        self.assertEqual(sp.record_digest(record["input"]), record["expected_sha256"])
        self.assertEqual(sp.episode_digest(episode["input"]), episode["expected_sha256"])

    def test_10_v11_family_package_raw_bytes(self):
        item = vector("V11")
        data = item["input"]["file_bytes_utf8"].encode("utf-8")
        self.assertEqual(sp.sha256_bytes(data), item["expected_sha256"])

    def test_11_code_sha_rejects_bad_hex(self):
        self.assert_raises_code(
            sp.S3_PREREG_SCHEMA_INVALID,
            sp.code_sha_from_files,
            {"a.py": "xyz"},
        )


class RealCodeShaTests(unittest.TestCase):
    def test_01_real_seven_files_recompute(self):
        real = sp.compute_code_sha(REPO_ROOT)
        self.assertEqual(len(real), 64)
        self.assertEqual(real, sp.code_sha_for_files(REPO_ROOT, sp.S3_CODE_SHA_FILES))
        self.assertEqual(len(sp.S3_CODE_SHA_FILES), 7)

    def test_02_real_analysis_code_sha(self):
        real = sp.compute_analysis_code_sha(REPO_ROOT)
        self.assertEqual(real, sp.code_sha_for_files(REPO_ROOT, sp.S3_ANALYSIS_CODE_SHA_FILES))

    def test_03_synthetic_vector_differs_from_real(self):
        self.assertNotEqual(sp.compute_code_sha(REPO_ROOT), vector("V02")["expected_sha256"])

    def test_04_missing_file_fails_closed(self):
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.code_sha_for_files(REPO_ROOT, ["research/concorde_metaopt/meta_learning/__missing__.py"])
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_FILE_ERROR)


class PreregBuildTests(support.SyntheticRepoCase, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = support.SyntheticRepoCase.get_repo()
        cls.prereg = cls.info["prereg"]

    def test_01_top_level_keys(self):
        expected = set(sp.S3_PREREG_REQUIRED_FIELDS) | {"prereg_id", "prereg_digest"}
        self.assertEqual(set(self.prereg), expected)
        self.assertEqual(len(self.prereg), 25)

    def test_02_identity_and_digest(self):
        self.assertEqual(self.prereg["schema_version"], sp.S3_PREREG_SCHEMA_VERSION)
        digest = sp.prereg_digest(self.prereg)
        self.assertEqual(self.prereg["prereg_digest"], digest)
        self.assertEqual(self.prereg["prereg_id"], sp.S3_PREREG_ID_PREFIX + digest[:16])
        self.assertEqual(self.prereg["physical_call_count"], 0)

    def test_03_fd_gate_sha256_binding(self):
        gate_path = Path(self.info["repo"]) / sp.S3_GATE_RELPATH
        self.assertTrue(gate_path.is_file())
        self.assertEqual(self.prereg["fd_gate_sha256"], sp.sha256_file(gate_path))
        self.assertEqual(len(self.prereg["fd_gate_sha256"]), 64)

    def test_04_family_block(self):
        family = self.prereg["family"]
        self.assertEqual(family["family_id"], "F-QE-conflict-v1")
        self.assertEqual(family["formula_version"], "polyhedral-v1")
        self.assertEqual(family["FAMILY_SEED"], 20261107)
        self.assertEqual(family["HOLDOUT_SEED"], 20261108)
        self.assertEqual(family["split_counts"], sp.S3_SPLIT_COUNTS)
        self.assertEqual(len(family["task_fingerprints"]), 20)
        for entry in family["task_fingerprints"]:
            self.assertEqual(set(entry), {"task_id", "fingerprint"})
            self.assertRegex(entry["fingerprint"], r"^[0-9a-f]{16}$")
        hv = REPO_ROOT / sp.HASH_VECTORS_RELPATH
        self.assertEqual(family["hash_vectors_sha256"], sp.sha256_file(hv))

    def test_05_fixed_sections(self):
        self.assertEqual(self.prereg["resource_limits"], sp.S3_RESOURCE_LIMITS)
        for value in self.prereg["resource_limits"].values():
            self.assertIs(type(value), int)
        self.assertEqual(self.prereg["budgets"], sp.S3_PREREG_BUDGETS)
        self.assertEqual([str(arm["id"]) for arm in self.prereg["arms"]], list(sp.S3_ARMS))
        self.assertEqual(self.prereg["determinism"]["subset_runs"], 60)
        self.assertEqual(self.prereg["data_boundary"], sp.S3_DATA_BOUNDARY)
        self.assertEqual(self.prereg["physical_call_count"], 0)

    def test_06_verify_ok(self):
        self.assertTrue(
            sp.verify_preregistration(
                self.prereg,
                repo_root=self.info["repo"],
                expected_code_sha=self.prereg["code_sha"],
                verify_code_sha=False,
            )
        )

    def test_07_verify_expected_code_sha_mismatch(self):
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.verify_preregistration(
                self.prereg,
                repo_root=self.info["repo"],
                expected_code_sha="0" * 64,
                verify_code_sha=False,
            )
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_CODE_SHA_MISMATCH)


class PreregNegativeTests(support.SyntheticRepoCase, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = support.SyntheticRepoCase.get_repo()
        cls.prereg = cls.info["prereg"]

    def verify(self, payload):
        return sp.verify_preregistration(
            payload,
            repo_root=self.info["repo"],
            verify_code_sha=False,
        )

    def assert_code(self, code, payload):
        with self.assertRaises(sp.S3PreregError) as ctx:
            self.verify(payload)
        self.assertEqual(ctx.exception.code, code)

    def test_01_digest_tamper(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["family"]["package_bytes"] = int(payload["family"]["package_bytes"]) + 1
        self.assert_code(sp.S3_PREREG_DIGEST_MISMATCH, payload)

    def test_02_schema_version_tamper(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["schema_version"] = "p4ra-s3-prereg-v0"
        self.assert_code(sp.S3_PREREG_SCHEMA_INVALID, payload)

    def test_03_missing_fd_gate_sha256(self):
        payload = json.loads(json.dumps(self.prereg))
        payload.pop("fd_gate_sha256")
        self.assert_code(sp.S3_PREREG_SCHEMA_INVALID, resign(payload))

    def test_04_resource_limits_changed(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["resource_limits"] = dict(payload["resource_limits"])
        payload["resource_limits"]["sum_run_wall_limit_s"] = 30000
        self.assert_code(sp.S3_PREREG_RESOURCE_LIMITS_INVALID, resign(payload))

    def test_05_resource_limits_float(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["resource_limits"] = dict(payload["resource_limits"])
        payload["resource_limits"]["peak_memory_mb"] = float(payload["resource_limits"]["peak_memory_mb"])
        self.assert_code(sp.S3_PREREG_RESOURCE_LIMITS_INVALID, resign(payload))

    def test_06_data_boundary_tamper(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["data_boundary"] = json.loads(json.dumps(payload["data_boundary"]))
        payload["data_boundary"]["flags"]["holdout_truth_used_for_training"] = True
        self.assert_code(sp.S3_PREREG_DATA_BOUNDARY_ERROR, resign(payload))

    def test_07_hash_vectors_sha_tamper(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["family"]["hash_vectors_sha256"] = "0" * 64
        # family 结构校验会先发现 hash_vectors 绑定异常（SCHEMA_INVALID）
        self.assert_code(sp.S3_PREREG_SCHEMA_INVALID, resign(payload))

    def test_08_fd_gate_sha_tamper(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["fd_gate_sha256"] = "1" * 64
        self.assert_code(sp.S3_PREREG_ARTIFACT_INVALID, resign(payload))

    def test_09_budgets_tamper(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["budgets"] = json.loads(json.dumps(payload["budgets"]))
        payload["budgets"]["main_runs"] = int(payload["budgets"]["main_runs"]) + 1
        # verify 侧结构校验对固定节统一映射为 SCHEMA_INVALID（build 侧才是 BUDGET_MISMATCH）
        self.assert_code(sp.S3_PREREG_SCHEMA_INVALID, resign(payload))

    def test_10_authorization_tamper(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["authorization_chain"] = json.loads(json.dumps(payload["authorization_chain"]))
        payload["authorization_chain"]["stage"] = "M9"
        self.assert_code(sp.S3_PREREG_AUTHORIZATION_MISMATCH, resign(payload))

    def test_11_placeholder_rejected_by_helper(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["campaign"] = json.loads(json.dumps(payload["campaign"]))
        payload["campaign"]["authorization"] = "TBD"
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.reject_placeholders(resign(payload))
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_PLACEHOLDER_REJECTED)

    def test_12_unknown_field_rejected(self):
        payload = json.loads(json.dumps(self.prereg))
        payload["unexpected_field"] = 1
        self.assert_code(sp.S3_PREREG_SCHEMA_INVALID, payload)


class ArtifactBindingTests(support.SyntheticRepoCase, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = support.SyntheticRepoCase.get_repo()
        cls.prereg = cls.info["prereg"]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="s3-artifact-")
        self.repo = Path(self._tmp.name) / "repo"
        shutil.copytree(self.info["repo"], self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def verify(self):
        return sp.verify_preregistration(self.prereg, repo_root=self.repo, verify_code_sha=False)

    def assert_code(self, code):
        with self.assertRaises(sp.S3PreregError) as ctx:
            self.verify()
        self.assertEqual(ctx.exception.code, code)

    def test_01_gate_tamper(self):
        path = self.repo / sp.S3_GATE_RELPATH
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["models"]["fomaml_meta_0"]["coordinates"][0]["relative_error"] = 0.5
        path.write_text(json.dumps(payload), encoding="utf-8")
        self.assert_code(sp.S3_PREREG_ARTIFACT_INVALID)

    def test_02_family_package_tamper(self):
        path = self.repo / self.prereg["family"]["package_path"]
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_code(sp.S3_PREREG_ARTIFACT_INVALID)

    def test_03_references_tamper(self):
        path = self.repo / self.prereg["references_sealed"]["path"]
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_code(sp.S3_PREREG_REFERENCES_MISMATCH)

    def test_04_bank_tamper(self):
        path = self.repo / self.prereg["episode_bank"]["files"][0]["path"]
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_code(sp.S3_PREREG_ARTIFACT_INVALID)

    def test_05_model_tamper(self):
        path = self.repo / self.prereg["models"]["fomaml"]["models"][0]["path"]
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_code(sp.S3_PREREG_ARTIFACT_INVALID)

    def test_06_hash_vectors_file_tamper(self):
        path = self.repo / sp.HASH_VECTORS_RELPATH
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(sp.S3PreregError) as ctx:
            self.verify()
        self.assertIn(
            ctx.exception.code,
            (sp.S3_PREREG_HASH_VECTORS_MISMATCH, sp.S3_PREREG_ARTIFACT_INVALID),
        )

    def test_07_missing_gate_build_fails(self):
        (self.repo / sp.S3_GATE_RELPATH).unlink()
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.build_preregistration(
                repo_root=self.repo,
                created_utc=CREATED_UTC,
                code_sha=support.synthetic_prereg_code_sha(),
                analysis_code_sha=support.synthetic_prereg_analysis_code_sha(),
            )
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_ARTIFACT_INVALID)


class DeterminismSubsetTests(unittest.TestCase):
    """计划 v1.3c：60-run 子集 budget 配额规则（20/20/10/10，30 B64+30 B128，5760 evals/轮）。"""

    @classmethod
    def setUpClass(cls):
        cls.keys = cls._full_grid()

    @staticmethod
    def _full_grid():
        keys = []
        for arm in sp.S3_ARMS:
            for task_index in range(20):
                for budget in sp.S3_PREREG_BUDGETS["budgets"]:
                    for opt_seed in sp.S3_PREREG_BUDGETS["opt_seeds"]:
                        for meta_seed in sp.S3_PREREG_BUDGETS["meta_seeds"]:
                            keys.append(
                                {
                                    "arm": arm,
                                    "task_id": "p4ra-FQEC-v1-%016x" % task_index,
                                    "budget": int(budget),
                                    "opt_seed": int(opt_seed),
                                    "meta_seed": int(meta_seed),
                                    "phase": "EVAL",
                                    "split": "meta_test",
                                }
                            )
        return keys

    @staticmethod
    def _shard(row):
        return sp._determinism_run_shard(
            row, shard_count=int(sp.S3_DETERMINISM_SHARD_COUNT)
        )

    @staticmethod
    def _quota_rows(rows):
        quota = sp.determinism_quota_map(sorted({row["arm"] for row in rows}))
        out = []
        seen = set()
        for row in rows:
            cell = (row["arm"], DeterminismSubsetTests._shard(row))
            if cell in seen:
                continue
            if int(row["budget"]) == int(quota[cell]):
                seen.add(cell)
                out.append(row)
        return out

    def test_01_selection_size_and_quota(self):
        rows = sp.select_determinism_run_keys(self.keys)
        self.assertEqual(len(rows), 60)
        self.assertEqual(len({sp.canonical_json(row) for row in rows}), 60)
        arms = sorted({row["arm"] for row in rows})
        self.assertEqual(arms, sorted(sp.S3_ARMS))
        self.assertEqual(sum(1 for row in rows if int(row["budget"]) == 64), 30)
        self.assertEqual(sum(1 for row in rows if int(row["budget"]) == 128), 30)
        self.assertEqual(sum(int(row["budget"]) for row in rows), 5760)
        for arm in sp.S3_ARMS:
            arm_rows = [row for row in rows if row["arm"] == arm]
            self.assertEqual(len(arm_rows), 12, arm)
            for budget in (64, 128):
                self.assertEqual(
                    len([row for row in arm_rows if int(row["budget"]) == budget]), 6
                )
        quota = sp.determinism_quota_map(arms)
        quota_a = {64: 0, 128: 0}
        for arm in arms:
            for shard in range(int(sp.S3_DETERMINISM_SHARD_COUNT)):
                budget = int(quota[(arm, shard)])
                covered = [
                    row
                    for row in rows
                    if row["arm"] == arm
                    and int(row["budget"]) == budget
                    and self._shard(row) == shard
                ]
                self.assertGreaterEqual(len(covered), 1, (arm, shard))
                quota_a[budget] += 1
        self.assertEqual(quota_a, {64: 20, 128: 20})
        self.assertRegex(
            sp.determinism_run_keys_sha256(rows),
            r"^[0-9a-f]{64}$",
        )

    def test_02_deterministic_selection(self):
        first = sp.select_determinism_run_keys(self.keys)
        second = sp.select_determinism_run_keys(list(reversed(self.keys)))
        self.assertEqual(first, second)
        self.assertEqual(
            sp.determinism_run_keys_sha256(first),
            sp.determinism_run_keys_sha256(second),
        )

    def test_03_bucket_empty_fails(self):
        arms = sorted({key["arm"] for key in self.keys})
        arm = arms[0]
        quota = sp.determinism_quota_map(arms)
        target = (arm, 0)
        budget = int(quota[target])
        grid = [
            key
            for key in self.keys
            if not (
                key["arm"] == arm
                and int(key["budget"]) == budget
                and DeterminismSubsetTests._shard(key) == target[1]
            )
        ]
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.select_determinism_run_keys(grid)
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_SCHEMA_INVALID)
        self.assertIn("桶空", str(ctx.exception))

    def test_04_insufficient_extras_fails(self):
        rows = sp.select_determinism_run_keys(self.keys)
        quota_only = self._quota_rows(rows)
        self.assertEqual(len(quota_only), 40)
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.select_determinism_run_keys(quota_only)
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_SCHEMA_INVALID)
        self.assertIn("补点不足", str(ctx.exception))

    def test_05_duplicate_rows_fail(self):
        rows = sp.select_determinism_run_keys(self.keys)
        rows[59] = dict(rows[0])
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.validate_determinism_run_keys(rows)
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_SCHEMA_INVALID)

    def test_06_budget_distribution_mutation_fails(self):
        rows = sp.select_determinism_run_keys(self.keys)
        row = next(item for item in rows if int(item["budget"]) == 64)
        row["budget"] = 128
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.validate_determinism_run_keys(rows)
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_SCHEMA_INVALID)
        self.assertIn("budget", str(ctx.exception))

    def test_07_arm_budget_quota_mutation_fails(self):
        rows = sp.select_determinism_run_keys(self.keys)
        arms = sorted({row["arm"] for row in rows})
        source = next(item for item in rows if item["arm"] == arms[0] and int(item["budget"]) == 64)
        source_arm = source["arm"]
        source["arm"] = next(arm for arm in arms if arm != source_arm)
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.validate_determinism_run_keys(rows)
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_SCHEMA_INVALID)

    def test_08_insufficient_grid_fails(self):
        with self.assertRaises(sp.S3PreregError) as ctx:
            sp.select_determinism_run_keys(self.keys[:30])
        self.assertEqual(ctx.exception.code, sp.S3_PREREG_SCHEMA_INVALID)

    def test_09_quota_constants_consistency(self):
        self.assertEqual(
            sum(sp.S3_DETERMINISM_BUDGET_COUNTS.values()),
            int(sp.S3_DETERMINISM_SUBSET_RUNS),
        )
        self.assertEqual(
            sum(sp.S3_DETERMINISM_QUOTA_A_BUDGET_COUNTS.values())
            + sum(sp.S3_DETERMINISM_QUOTA_B_BUDGET_COUNTS.values()),
            int(sp.S3_DETERMINISM_SUBSET_RUNS),
        )
        self.assertEqual(
            sum(
                int(budget) * int(count)
                for budget, count in sp.S3_DETERMINISM_BUDGET_COUNTS.items()
            ),
            int(sp.S3_DETERMINISM_EVALS_PER_ROUND),
        )


class WriteReadTests(support.SyntheticRepoCase, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = support.SyntheticRepoCase.get_repo()
        cls.prereg = cls.info["prereg"]

    def test_01_write_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prereg.json"
            info = sp.write_preregistration(path, self.prereg)
            expected = (sp.canonical_json(self.prereg) + "\n").encode("utf-8")
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(info["bytes"], len(expected))
            self.assertEqual(info["sha256"], sp.sha256_bytes(expected))
            self.assertEqual(sp.read_preregistration(path), self.prereg)

    def test_02_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prereg.json"
            sp.write_preregistration(path, self.prereg)
            with self.assertRaises(sp.S3PreregError) as ctx:
                sp.write_preregistration(path, self.prereg)
            self.assertEqual(ctx.exception.code, sp.S3_PREREG_FILE_ERROR)

    def test_03_read_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sp.S3PreregError) as ctx:
                sp.read_preregistration(Path(tmp) / "missing.json")
            self.assertEqual(ctx.exception.code, sp.S3_PREREG_FILE_ERROR)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# B01（M2R）：campaign 授权字段与数据清单字段顺序
# ---------------------------------------------------------------------------
class CampaignAuthorizationPreregTests(unittest.TestCase):
    def test_run_config_fields_order(self):
        fields = list(sp.S3_RUN_CONFIG_REQUIRED_FIELDS)
        self.assertEqual(fields[fields.index("code_sha") + 1], "campaign_authorization_id")
        self.assertEqual(fields[fields.index("code_sha") + 2], "campaign_authorization_utc")
        self.assertIn("campaign_authorization_id", sp.S3_DATA_MANIFEST_FIELDS)
        self.assertIn("campaign_authorization_utc", sp.S3_DATA_MANIFEST_FIELDS)

    def test_campaign_contract_fields(self):
        expected = ["campaign_authorization_id", "campaign_authorization_utc"]
        self.assertEqual(sp.S3_CAMPAIGN["required_record_fields"], expected)
        self.assertEqual(sp.S3_CAMPAIGN["rules"]["required_record_fields"], expected)
        self.assertNotIn("campaign_authorized_utc", json.dumps(sp.S3_CAMPAIGN, ensure_ascii=False))

    def test_analysis_plan_digest_stored_and_hex(self):
        prereg = support.SyntheticRepoCase().get_repo()["prereg"]
        self.assertEqual(len(prereg["analysis_plan_digest"]), 64)
        int(prereg["analysis_plan_digest"], 16)
