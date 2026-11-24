
import json
p=r"D:/RCAIDE/.real_runs/DRECOVER001-O1-20261124-01/o1_a4_geometry_identity.json"
d=json.load(open(p,encoding="utf-8"))
print("schema",d["schema"],"pairs",d["pair_count"],"proved",d["identity_proved_count"],"all",d["all_identity_proved"])
print("generated",d["generated_utc"])
for row in d["pairs"]:
    r=row["regeneration"]; c=row["canonical_xml"]
    print("==",row["run"],row["role"],"case",row["case_id"])
    print("   x12_matches",row["x12_matches_case_plan"],"design",r["design_id_from_delivered_x12"],r["design_hash_recorded_by_case_plan"],r["design_id_matches_case_plan"])
    print("   regen_sha",r["regenerated_vspgeom_sha256"],"plan_sha",r["case_plan_geometry_sha256"],"match",r["regenerated_vspgeom_matches_case_plan"])
    print("   starts",r["physical_solver_starts"],"solver_started",r["solver_started"],"sref",r["sref_m2_regenerated"])
    print("   canon diffs",c["difference_count"],"nongeom",c["non_geometric_differences"],"geom",c["geometric_differences"],"tags",c["difference_tag_counts"])
