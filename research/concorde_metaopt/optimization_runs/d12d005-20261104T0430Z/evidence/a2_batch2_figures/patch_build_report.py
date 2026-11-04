import io
from pathlib import Path
p = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/a2/batch2_figures/build_report.py")
s = p.read_text(encoding="utf-8")
old = '    A("- \u6bcf\u6848 history \u8fed\u4ee3 %d \u6b21\uff1bpolar \u5355\u884c\uff08S6 AoA=1\u300112D \u6848 AoA=2\uff09\uff1bpolar 48 \u5217\u3002" % BY["B2-03"]["history_iterations"])'
new = '    A("- history \u7531 verify-history \u5224\u5b9a PASS\uff08\u6bcf\u6848 5 \u6b21\u5c3e\u8ff9\u8fed\u4ee3\uff0c\u89c1 batch2_report.md\uff09\uff1bpolar \u5355\u884c\uff08S6 AoA=1\u300112D \u6848 AoA=2\uff09\uff0cpolar 48 \u5217\u3002")'
assert s.count(old) == 1, s.count(old)
p.write_text(s.replace(old, new), encoding="utf-8", newline="\n")
print("PATCH_OK")
