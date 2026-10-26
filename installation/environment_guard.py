"""Reject interpreters and RCAIDE installations outside this project's environment."""

from pathlib import Path
import subprocess
import sys


PREFIX = (Path(__file__).resolve().parents[1] / "envs" / "RCAIDE").resolve()


def environment_python():
    """Support the existing Conda layout and a fresh Windows/Linux venv."""
    for relative in ("python.exe", "Scripts/python.exe", "bin/python"):
        candidate = PREFIX / relative
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"No project Python interpreter found in {PREFIX}")


def check_environment():
    if Path(sys.prefix).resolve() != PREFIX:
        raise RuntimeError(f"RCAIDE requires {PREFIX}; current prefix is {sys.prefix}")
    if Path(sys.executable).resolve() != environment_python().resolve():
        raise RuntimeError(f"Unexpected interpreter: {sys.executable}")
    if not (sys.flags.ignore_environment and sys.flags.no_user_site):
        raise RuntimeError("Launch Python with -E -s to isolate Python settings.")

    import RCAIDE

    package = Path(RCAIDE.__file__).resolve()
    if PREFIX not in package.parents:
        raise RuntimeError(f"RCAIDE was imported outside the environment: {package}")
    return package


if __name__ == "__main__":
    check_environment()
    raise SystemExit(
        subprocess.call([str(environment_python()), "-E", "-s", *sys.argv[1:]])
    )
