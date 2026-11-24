import json, re, urllib.request, pathlib
def token():
    txt = pathlib.Path("C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8")
    m = re.search(r"GITHUB_TOKEN:\s*(\S+)", txt)
    return m.group(1).strip().strip("'\"")
def api(path):
    req = urllib.request.Request("https://api.github.com" + path,
        headers={"Authorization": "Bearer " + token(), "Accept": "application/vnd.github+json",
                 "User-Agent": "RCAIDE-audit"})
    return json.load(urllib.request.urlopen(req, timeout=90))
out = pathlib.Path(r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/audits/issue15_contract.md")
out.parent.mkdir(parents=True, exist_ok=True)
issue = api("/repos/QingYangJin/RCAIDE_Supersonic/issues/15")
parts = ["# Issue #15: " + issue["title"], "", issue["body"] or ""]
cs = api("/repos/QingYangJin/RCAIDE_Supersonic/issues/15/comments?per_page=100")
for c in cs:
    parts += ["", "## Comment %s @ %s (%s)" % (c["id"], c["created_at"], c["user"]["login"]), "", c["body"]]
out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
print("written", out, out.stat().st_size)
