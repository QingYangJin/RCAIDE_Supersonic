# Requires the parent directory of the openvsp package on sys.path.
import sys
sys.path.insert(0, sys.argv[1])
try:
    import openvsp
    print("OPENVSP_IMPORT_OK", getattr(openvsp, "__file__", None))
    print("OPENVSP_VERSION", openvsp.GetVSPVersion())
except Exception as exc:
    print("OPENVSP_IMPORT_FAIL", type(exc).__name__, str(exc))
