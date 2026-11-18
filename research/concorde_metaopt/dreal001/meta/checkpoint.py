"""JSON-only fixture model round-trip. Integrity is NOT provenance or backup admission.

No pickle, torch loading, physical evaluator or file/process side effects. The external
SHA must come from a trusted channel to detect replacement; a self-supplied SHA cannot
prove training occurred. Even restored weights never authorize production use.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
import re

from .meta_dataset import MetaDataset, TrainNormalizer
from .task_spec import ContractError, canonical_sha
from ...meta_learning import maml

SCHEMA = "drecover001.fixture_checkpoint.v1"
MAX_BYTES = 16 * 1024 * 1024
SCOPE = "SOFTWARE_FIXTURE_ARTIFACT_SERIALIZATION_ONLY"


def training_identity(dataset: MetaDataset) -> str:
    dataset.require_software_fixture()
    train = {t.task_id for t in dataset.tasks if t.split == "train"}
    return canonical_sha({"tasks": [asdict(t) for t in dataset.tasks if t.task_id in train],
                          "rows": [asdict(r) for r in dataset.rows if r.task_id in train]})


def _norm_payload(norm):
    return {"x_mean": norm.x_mean.tolist(), "x_scale": norm.x_scale.tolist(),
            "y_mean": norm.y_mean, "y_scale": norm.y_scale,
            "fit_observation_ids": list(norm.fit_observation_ids)}


def _validate(payload, dataset):
    dataset.require_software_fixture()
    keys = {"schema", "scope", "real_admission", "real_meta_training_executed",
            "training_identity_sha256", "config", "normalizer", "models"}
    if not isinstance(payload, dict) or set(payload) != keys:
        raise ContractError("checkpoint fields differ from schema")
    if (payload["schema"] != SCHEMA or payload["scope"] != SCOPE
            or payload["real_admission"] is not False
            or payload["real_meta_training_executed"] is not False):
        raise ContractError("checkpoint cannot claim real admission or training")
    if payload["training_identity_sha256"] != training_identity(dataset):
        raise ContractError("checkpoint training dataset identity mismatch")
    config = maml.config_from_dict(payload["config"])
    if (config.input_dim != 12 or config.output_dim != 1 or not config.first_order
            or config.head_only):
        raise ContractError("checkpoint requires 12D FOMAML configuration")
    if payload["normalizer"] != _norm_payload(TrainNormalizer.fit(dataset)):
        raise ContractError("checkpoint normalizer differs from train-only fit")
    norm = TrainNormalizer(**payload["normalizer"])
    models = payload["models"]
    if not isinstance(models, dict) or set(models) != {"fomaml", "pretrain"}:
        raise ContractError("checkpoint requires separate fomaml/pretrain model slots")
    restored = {}
    sizes = config.layer_sizes
    for name, data in models.items():
        if not isinstance(data, dict) or set(data) != {"names", "tensors"}:
            raise ContractError("checkpoint parameter fields invalid")
        params = maml.ParameterSet.from_dict(data)
        expected = [shape for left, right in zip(sizes[:-1], sizes[1:])
                    for shape in ((left, right), (right,))]
        if [v.shape for v in params.tensors] != expected or data["names"] != list(params.names):
            raise ContractError("checkpoint parameter shape/name mismatch")
        restored[name] = params
    return RestoredFixture(config, norm, restored)


@dataclass(frozen=True)
class RestoredFixture:
    config: maml.MAMLConfig
    normalizer: TrainNormalizer
    models: dict
    evidence_scope: str = SCOPE
    real_admission: bool = False
    real_meta_training_executed: bool = False


def pack_fixture_checkpoint(*, dataset: MetaDataset, config: maml.MAMLConfig,
                            normalizer: TrainNormalizer, models: dict) -> bytes:
    payload = {"schema": SCHEMA, "scope": SCOPE, "real_admission": False,
               "real_meta_training_executed": False,
               "training_identity_sha256": training_identity(dataset),
               "config": config.to_arm_dict(), "normalizer": _norm_payload(normalizer),
               "models": {name: params.to_dict() for name, params in models.items()}}
    try:
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise ContractError("checkpoint cannot encode nonfinite or unsupported content") from exc
    restore_fixture_checkpoint(blob, expected_sha256=hashlib.sha256(blob).hexdigest(), dataset=dataset)
    return blob


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate JSON field in checkpoint")
        result[key] = value
    return result


def restore_fixture_checkpoint(blob: bytes, *, expected_sha256: str,
                               dataset: MetaDataset) -> RestoredFixture:
    dataset.require_software_fixture()
    if type(blob) is not bytes or not 0 < len(blob) <= MAX_BYTES:
        raise ContractError("checkpoint bytes missing or exceed size limit")
    if (not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or hashlib.sha256(blob).hexdigest() != expected_sha256):
        raise ContractError("checkpoint SHA256 mismatch")
    try:
        payload = json.loads(blob.decode("utf-8"), object_pairs_hook=_unique_pairs,
                             parse_constant=lambda value: (_ for _ in ()).throw(
                                 ContractError("nonfinite JSON constant")))
        return _validate(payload, dataset)
    except ContractError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, maml.MAMLError) as exc:
        raise ContractError("invalid fixture checkpoint: " + str(exc)) from exc
