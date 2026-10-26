"""Run the unmodified official atmosphere example and check absolute errors."""

import json
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installation"))
from environment_guard import check_environment

check_environment()

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import RCAIDE
from RCAIDE.Framework.Core import Units


official = ROOT / "examples" / "official" / "atmosphere.py"
namespace = runpy.run_path(str(official), run_name="official_atmosphere")
namespace["main"]()

# The official assertions use signed maxima; also check maximum absolute errors.
altitude = np.linspace(-3, 90, 100) * Units.km
conditions = RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976().compute_values(
    altitude
)
truth = namespace["get_truth"]()
errors = {}
for name, reference, tolerance in zip(
    ("pressure", "temperature", "density", "speed_of_sound"),
    truth,
    (1e-1, 1e-5, 1e-5, 1e-5),
):
    calculated = np.asarray(getattr(conditions, name))
    error = float(np.max(np.abs(calculated - reference)))
    if not np.all(np.isfinite(calculated)) or error >= tolerance:
        raise AssertionError(f"{name}: absolute error {error} exceeds {tolerance}")
    errors[name] = {"maximum_absolute_error": error, "tolerance": tolerance}

output = ROOT / "outputs"
output.mkdir(exist_ok=True)
figure = plt.gcf()
figure.set_size_inches(13, 5)
figure.tight_layout()
figure.savefig(output / "official_atmosphere.png", dpi=150)
plt.close("all")
report = {
    "status": "PASS",
    "official_source_commit": "2d2ad0e8b5dc00b75d84879ea02cf8c098b04008",
    "sample_count": 100,
    "altitude_range_km": [-3, 90],
    "checks": errors,
    "scope": "Official standard atmosphere example; not a full aircraft mission.",
}
(output / "official_atmosphere.json").write_text(
    json.dumps(report, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(report, indent=2))
