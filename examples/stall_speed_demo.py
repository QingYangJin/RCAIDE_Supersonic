"""Small aircraft performance demo with assumed inputs, not flight-test data."""

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installation"))
from environment_guard import check_environment

check_environment()

import numpy as np
import RCAIDE
from RCAIDE.Library.Methods.Performance import estimate_stall_speed


vehicle = RCAIDE.Vehicle()
vehicle.tag = "assumed_light_aircraft"
vehicle.mass_properties.takeoff = 1180.0
vehicle.reference_area = 16.2
maximum_lift_coefficient = 1.5
atmosphere = RCAIDE.Framework.Analyses.Atmospheric.US_Standard_1976()
cases = []
for altitude in (0.0, 1000.0, 3000.0):
    speed = float(
        estimate_stall_speed(
            vehicle.mass_properties.takeoff,
            vehicle.reference_area,
            altitude,
            maximum_lift_coefficient,
        )
    )
    rho = float(atmosphere.compute_values(altitude).density[0, 0])
    expected = np.sqrt(
        2 * vehicle.mass_properties.takeoff * 9.81
        / (rho * vehicle.reference_area * maximum_lift_coefficient)
    )
    if not np.isfinite(speed) or not np.isclose(speed, expected, rtol=1e-12):
        raise AssertionError(f"Unexpected stall speed at altitude {altitude}")
    cases.append({"altitude_m": altitude, "stall_speed_m_s": speed})

result = {
    "status": "PASS",
    "scope": "Local API demonstration; assumed aircraft inputs, not validated performance.",
    "mass_kg": vehicle.mass_properties.takeoff,
    "wing_area_m2": vehicle.reference_area,
    "maximum_lift_coefficient": maximum_lift_coefficient,
    "cases": cases,
}
output = ROOT / "outputs" / "stall_speed_demo.json"
output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
