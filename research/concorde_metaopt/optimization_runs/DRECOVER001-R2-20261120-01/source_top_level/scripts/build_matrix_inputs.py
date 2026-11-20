import json, subprocess, sys
from pathlib import Path

ROOT = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
PY = r"D:/Anaconda/envs/RCAIDE/python.exe"
BUILD = ROOT / "scripts" / "build_task_case.py"
MATRIX = [
    ("m202-d01-support", "m202_d01_support", 2.02, "train", "support", "concorde-fixed-cruise-dreal001-real-v1", "d01"),
    ("m202-d02-query",   "m202_d02_query",   2.02, "train", "query",   "concorde-fixed-cruise-dreal001-real-v1", "d02"),
    ("m160-d00-support", "m160_d00_support", 1.60, "train", "support", "concorde-real-M160", "d00"),
    ("m160-d01-support", "m160_d01_support", 1.60, "train", "support", "concorde-real-M160", "d01"),
    ("m160-d02-query",   "m160_d02_query",   1.60, "train", "query",   "concorde-real-M160", "d02"),
    ("m180-d00-support", "m180_d00_support", 1.80, "train", "support", "concorde-real-M180", "d00"),
    ("m180-d01-support", "m180_d01_support", 1.80, "train", "support", "concorde-real-M180", "d01"),
    ("m180-d02-query",   "m180_d02_query",   1.80, "train", "query",   "concorde-real-M180", "d02"),
    ("m220-d00-support", "m220_d00_support", 2.20, "val",   "support", "concorde-real-M220", "d00"),
    ("m220-d01-support", "m220_d01_support", 2.20, "val",   "support", "concorde-real-M220", "d01"),
    ("m220-d02-query",   "m220_d02_query",   2.20, "val",   "query",   "concorde-real-M220", "d02"),
    ("m240-d00-support", "m240_d00_support", 2.40, "test",  "support", "concorde-real-M240", "d00"),
    ("m240-d01-support", "m240_d01_support", 2.40, "test",  "support", "concorde-real-M240", "d01"),
    ("m240-d02-query",   "m240_d02_query",   2.40, "test",  "query",   "concorde-real-M240", "d02"),
]
summary = []
for case_id, basename, mach, split, partition, task_id, design in MATRIX:
    case_dir = ROOT / "cases" / case_id
    if (case_dir / "task_spec.json").is_file() and (case_dir / "plan.json").is_file():
        spec = json.loads((case_dir / "task_spec.json").read_text(encoding="utf-8"))
        summary.append({"case_id": case_id, "reused": True, "mach": spec["mach"],
                        "design": spec["design"], "alpha_center": spec["alpha_center_deg"],
                        "cl_target": spec["cl_target"], "plan_sha256": None})
        continue
    cmd = [PY, str(BUILD), "--case-id", case_id, "--basename", basename,
           "--mach", str(mach), "--split", split, "--partition", partition,
           "--task-id", task_id, "--design", design,
           "--purpose", "R2 %s %s %s design %s" % (task_id, split, partition, design)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    (ROOT / "cases" / (case_id + ".build.log")).write_text(
        "STDOUT\n" + proc.stdout + "\nSTDERR\n" + proc.stderr, encoding="utf-8")
    if proc.returncode != 0:
        print("FAILED", case_id, proc.returncode, proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit(1)
    spec = json.loads((case_dir / "task_spec.json").read_text(encoding="utf-8"))
    summary.append({"case_id": case_id, "reused": False, "mach": spec["mach"],
                    "design": spec["design"], "alpha_center": spec["alpha_center_deg"],
                    "cl_target": spec["cl_target"],
                    "plan_sha256": json.loads((case_dir / "approval.json").read_text(encoding="utf-8"))["plan_sha256"]})
print(json.dumps(summary, indent=2))
