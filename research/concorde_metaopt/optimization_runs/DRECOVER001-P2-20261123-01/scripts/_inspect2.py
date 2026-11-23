import json
p=r"D:/RCAIDE/.real_runs/DRECOVER001-P2-20261123-01/p2_dataset/p2_dataset.json"
d=json.load(open(p,encoding="utf-8"))
print(list(d["rows"][0].keys()))
print(json.dumps(d["rows"][0],ensure_ascii=False)[:600])
print("CERT KEYS", list(d["certificates"][0].keys()) if d["certificates"] else None)
print(json.dumps(d["certificates"][0],ensure_ascii=False)[:600] if d["certificates"] else "")
