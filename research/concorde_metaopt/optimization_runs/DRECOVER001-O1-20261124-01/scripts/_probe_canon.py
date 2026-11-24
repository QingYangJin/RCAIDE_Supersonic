
import json
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/o1_a4_geometry_identity.json"
d=json.load(open(p,encoding="utf-8"))
for row in d["pairs"]:
    c=row["canonical_xml"]
    print("==",row["run"],row["role"],"elems",c["elements_delivered"],c["elements_case"],"diffs",c["difference_count"],"nongeom",c["non_geometric_differences"],"geom",c["geometric_differences"])
    print("   tags:",c["difference_tag_counts"])
    for r in c["residual_differences"][:4]:
        print("   RESID",r["tag"],"| delivered",r["delivered"],"| case",r["case"])
