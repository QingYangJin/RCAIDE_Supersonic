"""Inspect this installation without claiming complete aircraft workflow coverage."""

import argparse
from datetime import datetime, timezone, timedelta
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import shutil
import site
import sys

from environment_guard import check_environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    package_path = check_environment()

    import numpy as np
    import RCAIDE
    from RCAIDE.Framework.Core import Data

    args.report_dir.mkdir(parents=True, exist_ok=True)
    sample = Data()
    sample.tag = "local_io_check"
    sample.speed_m_s = np.array([10.0, 20.0, 30.0])
    sample.mass_kg = 1180.0
    saved_file = args.report_dir / "io-roundtrip.json"
    RCAIDE.save(sample, str(saved_file))
    restored = RCAIDE.load(str(saved_file))
    if restored.tag != sample.tag or restored.mass_kg != sample.mass_kg:
        raise AssertionError("RCAIDE JSON roundtrip changed scalar data.")
    np.testing.assert_array_equal(restored.speed_m_s, sample.speed_m_s)

    api_names = (
        "Framework.Analyses.Atmospheric.US_Standard_1976",
        "Framework.Analyses.Aerodynamics.Vortex_Lattice_Method",
        "Framework.Analyses.Weights.Conventional_Transport",
        "Framework.Mission.Sequential_Segments",
        "Framework.Networks.Fuel",
        "Framework.Networks.Electric",
        "Framework.Networks.Hybrid",
        "Framework.Optimization.Common.Nexus",
        "Library.Components.Wings.Main_Wing",
        "Library.Methods.Performance.estimate_stall_speed",
        "Library.Methods.Performance.generate_V_n_diagram",
        "Library.Methods.Performance.compute_payload_range_diagram",
    )
    apis = {}
    for dotted_name in api_names:
        obj = RCAIDE
        for part in dotted_name.split("."):
            obj = getattr(obj, part, None)
            if obj is None:
                break
        apis[dotted_name] = {
            "export_available": obj is not None,
            "workflow_executed": False,
        }

    optional_modules = {
        name: importlib.util.find_spec(name) is not None
        for name in ("vsp", "openvsp", "cantera", "pyoptsparse", "IPython", "ipykernel")
    }
    report = {
        "checked_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "status": "PASS",
        "python": sys.version,
        "executable": sys.executable,
        "prefix": sys.prefix,
        "distribution_version": importlib.metadata.version("RCAIDE-LEADS"),
        "module_version": RCAIDE.__version__,
        "package_file": str(package_path),
        "conda_prefix": __import__("os").environ.get("CONDA_PREFIX"),
        "user_site_enabled": site.ENABLE_USER_SITE,
        "ignore_python_environment": bool(sys.flags.ignore_environment),
        "io_roundtrip": "PASS",
        "api_export_probes": apis,
        "optional_module_discovery": optional_modules,
        "executables_on_path": {
            name: shutil.which(name) for name in ("vsp", "vspaero", "avl", "SU2_CFD")
        },
        "external_tool_probe_scope": "PATH and environment module discovery only.",
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "matplotlib", "pandas", "pyvista", "vtk")
        },
    }
    path = args.report_dir / "runtime.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
