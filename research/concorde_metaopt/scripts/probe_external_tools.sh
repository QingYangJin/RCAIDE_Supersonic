#!/usr/bin/env bash
# Capture git and external tool facts that a sandboxed Python child may be denied.
# Usage: bash research/concorde_metaopt/scripts/probe_external_tools.sh <out_dir>
# The out_dir is normally research/concorde_metaopt/optimization_runs/<run_id>/probes
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
OUT="${1:-$ROOT/research/concorde_metaopt/probes/latest}"
SU2="D:/Program Files/SU2/SU2-v8.5.0-win64-mpi/win64-mpi/bin/SU2_CFD.exe"
GMSH="D:/Program Files/GMesh/gmsh-4.15.2-Windows64/gmsh-4.15.2-Windows64/gmsh.exe"
OPENVSP_PY="D:/Anaconda/envs/SUAVE/python.exe"
OPENVSP_PY2="D:/Anaconda/python.exe"
OPENVSP_PY_ROOT="D:/Program Files/OpenVSP/OpenVSP-3.26.1-win64-Python3.9/OpenVSP-3.26.1-win64/python"
# The openvsp package imports utilities.transformations and degen_geom is shipped
# beside it; all four roots must be on sys.path (independent P0 review, 2026-10-28).
OPENVSP_SYS_PATHS=("$OPENVSP_PY_ROOT" "$OPENVSP_PY_ROOT/openvsp" "$OPENVSP_PY_ROOT/degen_geom" "$OPENVSP_PY_ROOT/utilities")
mkdir -p "$OUT" || exit 2
cd "$ROOT" || exit 2
run_probe() {
  name="$1"; shift
  "$@" > "$OUT/$name.txt" 2>&1
  echo $? > "$OUT/$name.rc"
}
run_probe git_head git rev-parse HEAD
run_probe git_branch git branch --show-current
run_probe git_status git status --porcelain=v1
run_probe su2_help "$SU2" --help
run_probe gmsh_version "$GMSH" --version
run_probe py_suave "$OPENVSP_PY" -c "import sys; print(sys.executable); print(sys.version)"
run_probe py_anaconda "$OPENVSP_PY2" -c "import sys; print(sys.executable); print(sys.version)"
cat > "$OUT/openvsp_probe.py" <<'PYEOF'
# Requires all package roots on sys.path: openvsp imports utilities.transformations
# and degen_geom is shipped beside openvsp.
import sys
for path in sys.argv[1:]:
    sys.path.insert(0, path)
try:
    import openvsp
    print("OPENVSP_IMPORT_OK", getattr(openvsp, "__file__", None))
    # The 3.26.1 Python binding exposes no version API; record that fact instead
    # of inventing a version. The install version is documented by its directory name.
    try:
        print("OPENVSP_VERSION", openvsp.GetVSPVersion())
    except Exception as exc:
        print("OPENVSP_VERSION_UNAVAILABLE", type(exc).__name__, str(exc))
except Exception as exc:
    print("OPENVSP_IMPORT_FAIL", type(exc).__name__, str(exc))
PYEOF
run_probe openvsp_suave "$OPENVSP_PY" "$OUT/openvsp_probe.py" "${OPENVSP_SYS_PATHS[@]}"
run_probe openvsp_anaconda "$OPENVSP_PY2" "$OUT/openvsp_probe.py" "${OPENVSP_SYS_PATHS[@]}"
# Optional diagnostic: prepend Anaconda Library bin. This is recorded as a diagnostic
# only; it does not claim that libxml2 is the cause of any failure.
PATH="D:/Anaconda/Library/bin:$PATH" "$OPENVSP_PY" "$OUT/openvsp_probe.py" "${OPENVSP_SYS_PATHS[@]}" > "$OUT/openvsp_suave_with_libxml2.txt" 2>&1
echo $? > "$OUT/openvsp_suave_with_libxml2.rc"
echo "probe_dir=$OUT"
ls "$OUT" | head -40
