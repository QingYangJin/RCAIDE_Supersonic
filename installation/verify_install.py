"""Record the installed environment and compare its version with the PyPI snapshot."""

import importlib.metadata
import json
from pathlib import Path
import platform
import site
import sys

from environment_guard import check_environment


package = check_environment()
root = Path(__file__).resolve().parent
metadata = json.loads((root / "pypi-metadata.json").read_text(encoding="utf-8-sig"))
installed = importlib.metadata.version("RCAIDE-LEADS")
latest = metadata["info"]["version"]
if installed != latest:
    raise RuntimeError(f"Installed RCAIDE {installed} differs from PyPI {latest}")
install_report = json.loads(
    (root / "pip-install-report.json").read_text(encoding="utf-8")
)
distribution = next(
    item
    for item in install_report["install"]
    if item["metadata"]["name"].lower().replace("_", "-") == "rcaide-leads"
)
archive = distribution["download_info"]
sha256 = archive["archive_info"]["hashes"]["sha256"]
if sha256 not in {item["digests"]["sha256"] for item in metadata["urls"]}:
    raise RuntimeError("Installed archive hash differs from official PyPI metadata.")
result = {
    "python": platform.python_version(),
    "executable": sys.executable,
    "prefix": sys.prefix,
    "rcaide_version": installed,
    "pypi_latest_checked": latest,
    "archive_sha256_matches_pypi": True,
    "archive_sha256": sha256,
    "archive_url": archive["url"],
    "package_file": str(package),
    "user_site_enabled": site.ENABLE_USER_SITE,
    "ignore_python_environment": bool(sys.flags.ignore_environment),
    "dependencies": {
        name: importlib.metadata.version(name)
        for name in ("numpy", "scipy", "matplotlib", "pandas", "vtk", "pyvista")
    },
}
(root / "verification.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(result, indent=2))
