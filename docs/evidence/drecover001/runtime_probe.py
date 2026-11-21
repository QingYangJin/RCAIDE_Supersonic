"""Zero-physics runtime dependency probe; no solver imports."""
import importlib.util
import json
import sys
print(json.dumps({"python": sys.executable, "version": sys.version, "packages": {name: bool(importlib.util.find_spec(name)) for name in ("torch", "numpy", "pytest")}}))
