import json
from pathlib import Path
RUN = Path("D:/RCAIDE/.real_runs/DRECOVER001-O0-20261124-01")
for name in ("baseline", "best"):
    for tag in ("r1", "r2", "wake16"):
        d = RUN / "cases/O0F" / ("o0-final-%s-%s-final" % (name, tag))
        if not d.is_dir():
            print(name, tag, "MISSING"); continue
        files = [p for p in d.rglob("*") if p.is_file()]
        polars = [p for p in files if p.suffix == ".polar"]
        print(name, tag, len(files), sum(p.stat().st_size for p in files), "polars", len(polars))
        cr = d / "case_result.json"
        if cr.is_file():
            txt = cr.read_text(encoding="utf-8")
            i = txt.find('"polar_rows"')
            print("   case_result len", len(txt), "|", txt[max(0,i-60):i+80].replace("\n", " "))
