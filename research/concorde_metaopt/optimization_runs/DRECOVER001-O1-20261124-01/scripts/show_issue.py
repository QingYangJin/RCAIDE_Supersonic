import json, re, sys, urllib.request, pathlib

def token():
    txt = pathlib.Path("C:/Users/pc/.dsh/.credentials.yaml").read_text(encoding="utf-8")
    m = re.search(r"GITHUB_TOKEN:\s*(\S+)", txt)
    if not m:
        m = re.search(r"GITHUB_TOKEN['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]+)", txt)
    return m.group(1).strip().strip("'\"")

def api(path):
    t = token()
    req = urllib.request.Request("https://api.github.com" + path,
        headers={"Authorization": "Bearer " + t, "Accept": "application/vnd.github+json",
                 "User-Agent": "RCAIDE-audit"})
    return json.load(urllib.request.urlopen(req, timeout=90))

issue = api("/repos/QingYangJin/RCAIDE_Supersonic/issues/15")
print("TITLE:", issue["title"])
print("STATE:", issue["state"], "| comments:", issue["comments"], "| updated:", issue["updated_at"])
print("BODY CHARS:", len(issue["body"] or ""))
print("=====BODY=====")
print(issue["body"])
print("=====COMMENTS=====")
cs = api("/repos/QingYangJin/RCAIDE_Supersonic/issues/15/comments?per_page=100")
for c in cs:
    print("---", c["id"], c["created_at"], c["user"]["login"], len(c["body"]), "chars")
    print(c["body"][:600].replace("\n", " ")[:600])
