"""Recompute response decisions from stored native coordinates, without OpenVSP."""
from pathlib import Path
import hashlib
import json
import numpy as np


def main():
    root = Path(__file__).resolve().parent
    result = json.loads((root / "native_response_receipt.json").read_text())
    archive = root / result["sample_archive"]["name"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != result["sample_archive"]["sha256"]:
        raise ValueError("native coordinate archive SHA mismatch")
    labels = ["baseline", "baseline_repeat"] + ["probe_%02d" % i for i in range(12)]
    names = ("main_wing", "vertical_tail", "fuselage")
    with np.load(archive, allow_pickle=False) as arrays:
        if set(arrays.files) != {label + "__" + name for label in labels for name in names}:
            raise ValueError("native archive array identity mismatch")
        for key in arrays.files:
            array = arrays[key]
            if array.dtype != np.float64 or array.ndim != 2 or array.shape[1] != 3 or not np.isfinite(array).all():
                raise ValueError("invalid saved native coordinates")
        for name in names:
            a, b = arrays["baseline__" + name], arrays["baseline_repeat__" + name]
            if not np.array_equal(a, b):
                raise ValueError("baseline repeat differs")
            if hashlib.sha256(a.astype("<f8").tobytes()).hexdigest() != result["baseline"][name]["coordinate_sha256"]:
                raise ValueError("baseline sample SHA mismatch")
        checks = []
        for index, row in enumerate(result["probes"]):
            deltas = {}
            for name in names:
                a, b = arrays["baseline__" + name], arrays["probe_%02d__" % index + name]
                delta = float(np.max(np.abs(a - b)))
                if delta != row["native_coordinate_max_abs_delta_m"][name]:
                    raise ValueError("reported delta disagrees with saved coordinates")
                if hashlib.sha256(b.astype("<f8").tobytes()).hexdigest() != row["native_metrics"][name]["coordinate_sha256"]:
                    raise ValueError("probe sample SHA mismatch")
                deltas[name] = delta
            changed = [name for name in names if deltas[name] > 1e-8]
            isolated = changed == [row["expected_component"]] and all(deltas[n] <= 1e-10 for n in names if n != row["expected_component"])
            if not isolated or not row["expected_component_only"]:
                raise ValueError("saved response fails component isolation")
            checks.append({"variable": row["name"], "expected_component_only": isolated})
    summary = {"status": "SAVED_NATIVE_RESPONSE_RECOMPUTED", "checks": checks,
               "archive_sha256": result["sample_archive"]["sha256"],
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "independent_review": False, "physical_solver_starts_actual": 0,
               "aerodynamic_active_mask": "NOT_VALIDATED", "freeze_issued": False}
    (root / "saved_sample_verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
