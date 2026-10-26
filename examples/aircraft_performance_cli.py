"""Run a small RCAIDE analysis with explicit, assumed aircraft inputs."""

import argparse
import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installation"))
from environment_guard import check_environment


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Expected a finite number greater than zero.")
    return number


def finite_number(value):
    number = float(value)
    if not math.isfinite(number):
        raise argparse.ArgumentTypeError("Expected a finite number.")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mass-kg", type=positive_number, default=1180.0)
    parser.add_argument("--wing-area-m2", type=positive_number, default=16.2)
    parser.add_argument("--clmax", type=positive_number, default=1.5)
    parser.add_argument(
        "--altitudes-m", nargs="+", type=finite_number, default=[0.0, 1000.0, 3000.0]
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "performance")
    args = parser.parse_args()
    package_path = check_environment()

    import RCAIDE
    from RCAIDE.Library.Methods.Performance import estimate_stall_speed

    vehicle = RCAIDE.Vehicle()
    vehicle.tag = "assumed_aircraft"
    vehicle.mass_properties.takeoff = args.mass_kg
    vehicle.reference_area = args.wing_area_m2
    cases = []
    for altitude in args.altitudes_m:
        speed = float(
            estimate_stall_speed(
                vehicle.mass_properties.takeoff, vehicle.reference_area, altitude, args.clmax
            )
        )
        if not math.isfinite(speed) or speed <= 0:
            raise RuntimeError(f"Invalid computed stall speed at altitude {altitude}.")
        cases.append(
            {
                "altitude_requested_m": altitude,
                "true_stall_speed_m_s": speed,
                "true_stall_speed_km_h": speed * 3.6,
            }
        )

    report = {
        "scope": "Assumed inputs; steady lift estimate, not validated aircraft performance.",
        "rcaide_module_version": RCAIDE.__version__,
        "python": sys.executable,
        "package_file": str(package_path),
        "mass_kg": args.mass_kg,
        "wing_area_m2": args.wing_area_m2,
        "clmax": args.clmax,
        "cases": cases,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "stall-speed.json"
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Results: {result_path.resolve()}")


if __name__ == "__main__":
    main()
