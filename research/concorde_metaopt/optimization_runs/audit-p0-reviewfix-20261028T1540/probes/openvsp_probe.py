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
