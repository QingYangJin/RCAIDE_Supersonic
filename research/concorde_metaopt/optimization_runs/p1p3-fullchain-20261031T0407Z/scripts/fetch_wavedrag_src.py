
import urllib.request, json
base = "https://raw.githubusercontent.com/OpenVSP/OpenVSP/master/"
cands = [
    "src/external/wavedragEL/EmintonLord.cpp",
    "src/external/wavedragEL/EmintonLord.h",
    "src/external/wavedragEL/emintonlord.cpp",
    "src/external/wavedragEL/wavedragEL.cpp",
    "src/external/wavedragEL/WaveDragEL.cpp",
    "src/external/wavedragEL/EL.cpp",
    "src/external/wavedragEL/README.md",
    "src/geom_core/WaveDrag.cpp",
    "src/geom_core/WaveDrag.h",
    "src/geom_core/AnalysisWaveDrag.cpp",
    "src/geom_core/AnalysisMgr.cpp",
]
for c in cands:
    try:
        with urllib.request.urlopen(base + c, timeout=30) as fh:
            data = fh.read().decode("utf-8", "replace")
        print("FOUND", c, len(data))
        open("src_" + c.replace("/", "_"), "w", encoding="utf-8").write(data)
    except Exception as exc:
        print("miss", c, str(exc)[:80])
