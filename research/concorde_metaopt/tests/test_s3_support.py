"""S3 测试共享支撑（非用例模块）：在临时目录构建合成证据树 + prereg。

边界：只写 tempfile 临时目录；不写仓库、不训练、不启求解器、physical_call_count=0。
合成证据树与 M1 预览（EXT/p4-route-a/a1/s3_preview/build_preview.py）同一形状：
  research/concorde_metaopt/evidence/s3/{hash_vectors.json,family_package/,references_sealed/,
  calibration/,models/, s3_preregistration.json}
其中 episode bank 行与模型文件是占位结构（满足 prereg 结构校验），SMOKE run 时由
s3_runner 重新训练模型/重建 bank，不读取占位模型。
"""
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from research.concorde_metaopt.meta_learning import s3_prereg as sp
from research.concorde_metaopt.meta_learning import task_family as tf

REPO_ROOT = Path(__file__).resolve().parents[3]
CREATED_UTC = "2026-11-07T06:40:00+00:00"


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def write_canonical(path: Path, payload: Any) -> bytes:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = (canonical_json(payload) + "\n").encode("utf-8")
    target.write_bytes(data)
    return data


def load_hash_vectors() -> dict[str, Any]:
    path = REPO_ROOT / sp.HASH_VECTORS_RELPATH
    return json.loads(path.read_text(encoding="utf-8"))


def vector_by_id(vectors: dict[str, Any], vector_id: str) -> dict[str, Any]:
    for vector in vectors["vectors"]:
        if vector["id"] == vector_id:
            return vector
    raise KeyError(vector_id)


def synthetic_prereg_code_sha() -> str:
    """合成仓 prereg 用的 code_sha 占位（M1 预览同口径：显式 64-hex，不读仓库）。"""
    return sha256_text("p4ra-s3-test|code_sha")


def synthetic_prereg_analysis_code_sha() -> str:
    return sha256_text("p4ra-s3-test|analysis_code_sha")


def write_frozen_artifacts(repo: Path, *, bank_sha: dict[int, str], created_utc: str = CREATED_UTC) -> dict[str, Any]:
    """写 M2 冻结 FD 梯度门 + model_manifest（合成占位，满足 s3_prereg 结构断言）。

    返回 {gate_path, gate_sha256, model_manifest_path, model_manifest_sha256, model_sha256}。
    """
    repo = Path(repo)
    coordinates = [
        {
            "index": int(index),
            "param": "layer_0_weight" if index % 2 == 0 else "layer_1_bias",
            "analytic": 1.0 + index * 0.01,
            "numeric": 1.0 + index * 0.01 + 1e-9,
            "relative_error": index * 1e-9,
        }
        for index in range(int(sp.S3_FD_GATE_COORDINATES_PER_MODEL))
    ]
    models_block: dict[str, Any] = {}
    for key in sp.S3_FD_GATE_MODEL_KEYS:
        kind = key.split("_meta_")[0]
        block = {
            "arm_type": kind,
            "meta_seed": 0,
            "n_checked": len(coordinates),
            "status": "PASS",
            "max_relative_error": max(item["relative_error"] for item in coordinates),
            "coordinates": [dict(item) for item in coordinates],
        }
        models_block[key] = block
    gate = {
        "schema_version": sp.S3_FD_GATE_SCHEMA_VERSION,
        "created_utc": str(created_utc),
        "tolerance": 1e-6,
        "epsilon_rule": sp.S3_FD_EPSILON_RULE,
        "coordinates_per_model": int(sp.S3_FD_GATE_COORDINATES_PER_MODEL),
        "coordinates_total": int(sp.S3_FD_GATE_COORDINATES_PER_MODEL) * len(sp.S3_FD_GATE_MODEL_KEYS),
        "models": models_block,
        "negatives": {key: "PASS" for key in sp.S3_FD_GATE_NEGATIVE_KEYS},
        "status": "PASS",
        "max_relative_error": max(block["max_relative_error"] for block in models_block.values()),
        "override": False,
        "physical_call_count": 0,
        "solver_invocations": [],
    }
    gate_path = repo / sp.S3_GATE_RELPATH
    gate_data = write_canonical(gate_path, gate)

    model_sha: dict[tuple[str, int], str] = {}
    manifest_rows: list[dict[str, Any]] = []
    for kind in sp.S3_MODEL_KINDS:
        for seed in sp.S3_MODEL_META_SEEDS:
            relpath = sp.S3_MODEL_PATH_TEMPLATE.format(kind=kind, meta_seed=int(seed))
            path = repo / relpath
            data = path.read_bytes()
            sha = sha256_bytes(data)
            model_sha[(kind, int(seed))] = sha
            config = dict(sp.S3_MODEL_CONFIG_TEMPLATE)
            config["hidden_sizes"] = [int(item) for item in config["hidden_sizes"]]
            config["seed"] = int(seed)
            config["head_only"] = kind == "anil"
            manifest_rows.append(
                {
                    "arm_type": kind,
                    "meta_seed": int(seed),
                    "config": config,
                    "path": relpath,
                    "sha256": sha,
                    "train_wall_s": 1.0 + 0.1 * int(seed),
                    "peak_memory_mb": 100.0,
                    "episode_bank_sha256": str(bank_sha[int(seed)]),
                    "final_train_loss": 0.5,
                }
            )
    manifest = {
        "schema_version": sp.S3_MODEL_MANIFEST_SCHEMA_VERSION,
        "run_id": "m2-synthetic-freeze",
        "models": manifest_rows,
    }
    manifest_path = repo / sp.S3_MODEL_MANIFEST_RELPATH
    manifest_data = write_canonical(manifest_path, manifest)
    return {
        "gate_path": gate_path,
        "gate_sha256": sha256_bytes(gate_data),
        "model_manifest_path": manifest_path,
        "model_manifest_sha256": sha256_bytes(manifest_data),
        "model_sha256": model_sha,
    }


def build_synthetic_s3_repo(
    root: str | Path,
    *,
    delta1_base: float = 0.20,
    created_utc: str = CREATED_UTC,
    build_prereg: bool = True,
) -> dict[str, Any]:
    """在 root 下构建合成证据树，可选构建并写盘 prereg；返回路径与产物信息。"""
    repo = Path(root)
    evidence = repo / "research" / "concorde_metaopt" / "evidence" / "s3"
    evidence.mkdir(parents=True, exist_ok=True)

    hash_vectors_target = repo / sp.HASH_VECTORS_RELPATH
    hash_vectors_target.parent.mkdir(parents=True, exist_ok=True)
    hash_vectors_target.write_bytes((REPO_ROOT / sp.HASH_VECTORS_RELPATH).read_bytes())

    tasks = tf.build_s3_conflict_family(delta1_base=float(delta1_base))
    package = tf.build_s3_family_package(
        tasks,
        delta1_base=float(delta1_base),
        created_utc=str(created_utc),
        code_sha="0" * 64,
    )
    package_path = repo / sp.S3_FAMILY_PACKAGE_RELPATH
    package_info = tf.write_s3_family_package(package_path, package)

    references = tf.build_s3_references_sealed(tasks)
    references_path = repo / sp.S3_REFERENCES_SEALED_RELPATH
    tf.write_s3_json_canonical(references_path, references)

    calibration = {
        "schema_version": sp.S3_CALIBRATION_SCHEMA_VERSION,
        "family_id": sp.S3_FAMILY_ID,
        "formula_version": sp.S3_FORMULA_VERSION,
        "created_utc": str(created_utc),
        "validation_split": "meta_validation",
        "accepted": True,
        "selected_delta1_base": float(delta1_base),
        "candidates": [
            {"delta1_base": 0.20, "accepted": True},
            {"delta1_base": 0.22, "accepted": True},
            {"delta1_base": 0.25, "accepted": True},
        ],
        "construction_stats": {
            "n_validation_tasks": 20,
            "certificate_pass": 20,
            "support_feasible_median_fraction": 0.1758,
            "support_feasible_min_fraction": 0.0625,
            "support_feasible_max_fraction": 0.3906,
            "min_support_feasible_points": 8,
            "grid_feasible_median_fraction": 0.1647,
            "margin_mean": 0.1243,
            "objective_regret_median": 0.039,
        },
        "physical_call_count": 0,
    }
    calibration_path = repo / sp.S3_CALIBRATION_RELPATH
    write_canonical(calibration_path, calibration)

    meta_train_ids = [task.task_id for task in tasks if task.split == "meta_train"]
    bank_sha: dict[int, str] = {}
    for seed in sp.S3_MODEL_META_SEEDS:
        rows = []
        for step in range(200):
            for slot in range(8):
                episode = {
                    "schema_version": sp.S3_EPISODE_BANK_SCHEMA_VERSION,
                    "meta_seed": int(seed),
                    "outer_step": int(step),
                    "slot": int(slot),
                    "task_id": meta_train_ids[(step * 8 + slot) % len(meta_train_ids)],
                    "task_split": "meta_train",
                    "K_train": 5 if (step * 8 + slot) % 2 == 0 else 10,
                    "support_indices": [int(slot), int(slot + 1)],
                    "query_indices": list(range(64)),
                }
                episode["episode_digest"] = sp.episode_digest(episode)
                rows.append(canonical_json(episode))
        bank_path = repo / sp.S3_EPISODE_BANK_PATH_TEMPLATE.format(meta_seed=int(seed))
        bank_path.parent.mkdir(parents=True, exist_ok=True)
        data = ("\n".join(rows) + "\n").encode("utf-8")
        bank_path.write_bytes(data)
        bank_sha[int(seed)] = sha256_bytes(data)

    for kind in sp.S3_MODEL_KINDS:
        for seed in sp.S3_MODEL_META_SEEDS:
            config = dict(sp.S3_MODEL_CONFIG_TEMPLATE)
            config["seed"] = int(seed)
            config["head_only"] = kind == "anil"
            layer_sizes = [12, 64, 64, 3]
            parameters = []
            for layer in range(3):
                weight = [
                    [
                        round(0.001 * (((row + 1) * (col + 1)) % 7), 6)
                        for col in range(layer_sizes[layer])
                    ]
                    for row in range(layer_sizes[layer + 1])
                ]
                bias = [
                    round(0.001 * (row + 1), 6)
                    for row in range(layer_sizes[layer + 1])
                ]
                parameters.append({"name": "layer_%d_weight" % layer, "tensor": weight})
                parameters.append({"name": "layer_%d_bias" % layer, "tensor": bias})
            model = {
                "schema_version": sp.S3_MODEL_FILE_SCHEMA_VERSION,
                "arm_type": kind,
                "meta_seed": int(seed),
                "config": config,
                "parameters": parameters,
                "episode_bank_sha256": bank_sha[int(seed)],
                "final_train_loss": 0.5,
            }
            model_path = repo / sp.S3_MODEL_PATH_TEMPLATE.format(kind=kind, meta_seed=int(seed))
            write_canonical(model_path, model)

    frozen = write_frozen_artifacts(repo, bank_sha=bank_sha, created_utc=str(created_utc))

    result: dict[str, Any] = {
        "repo": repo,
        "evidence_root": evidence,
        "tasks": tasks,
        "family_package": package_info,
        "references_path": references_path,
        "calibration_path": calibration_path,
        "bank_sha256": bank_sha,
        "frozen": frozen,
        "gate_path": frozen["gate_path"],
        "model_manifest_path": frozen["model_manifest_path"],
        "prereg": None,
        "prereg_path": None,
    }
    if not build_prereg:
        return result

    code_sha = synthetic_prereg_code_sha()
    analysis_code_sha = synthetic_prereg_analysis_code_sha()
    prereg = sp.build_preregistration(
        repo_root=repo,
        created_utc=str(created_utc),
        code_sha=code_sha,
        analysis_code_sha=analysis_code_sha,
    )
    assert sp.verify_preregistration(
        prereg,
        repo_root=repo,
        verify_code_sha=False,
        verify_hash_vectors=True,
        verify_artifacts=True,
    )
    prereg_path = repo / sp.S3_PREREG_RELPATH
    write_info = sp.write_preregistration(prereg_path, prereg)
    loaded = sp.read_preregistration(prereg_path)
    if loaded["prereg_digest"] != prereg["prereg_digest"]:
        raise AssertionError("prereg 写读 digest 不一致")
    result.update(
        {
            "prereg": loaded,
            "prereg_path": prereg_path,
            "prereg_write": write_info,
            "code_sha": code_sha,
            "analysis_code_sha": analysis_code_sha,
        }
    )
    return result


class SyntheticRepoCase:
    """setUpClass 复用：每类一个临时合成仓（含已构建 prereg）。"""

    _repo_info: dict[str, Any] | None = None
    _tmp_dir: tempfile.TemporaryDirectory | None = None

    @classmethod
    def get_repo(cls) -> dict[str, Any]:
        if cls._repo_info is None:
            cls._tmp_dir = tempfile.TemporaryDirectory(prefix="s3-synthetic-")
            cls._repo_info = build_synthetic_s3_repo(cls._tmp_dir.name)
        return cls._repo_info

    @classmethod
    def cleanup_repo(cls) -> None:
        if cls._tmp_dir is not None:
            cls._tmp_dir.cleanup()
            cls._tmp_dir = None
            cls._repo_info = None
