from pathlib import Path
p = Path("C:/Users/pc/AppData/Local/RCAIDE_Supersonic_agent_state/d12d005/a2/batch2_figures/build_report.py")
s = p.read_text(encoding="utf-8")
reps = [("+2.43%%", "+2.43%"), ("\u22122.69%%", "\u22122.69%"), ("15%% \u91cf\u7ea7", "15% \u91cf\u7ea7")]
for old, new in reps:
    assert s.count(old) == 1, (old, s.count(old))
    s = s.replace(old, new)
p.write_text(s, encoding="utf-8", newline="\n")
print("PATCH_OK")
