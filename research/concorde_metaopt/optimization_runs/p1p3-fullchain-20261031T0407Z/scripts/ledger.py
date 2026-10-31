"""Approval and budget ledger helper for the D-12D-002 full-chain run.

Usage:
  python ledger.py note <kind> <message> [--case ID] [--files "a:b;c:d"]
  python ledger.py start <category> <case_id> <description> <command> [--files "a:b"]
  python ledger.py finish <case_id> <status> <wall_seconds> <returncode> [--files "a:b;c:d"] [--note text]
  python ledger.py status
"""
import json
import sys
from pathlib import Path

LEDGER = Path(r"D:/RCAIDE/research/concorde_metaopt/optimization_runs/p1p3-fullchain-20261031T0407Z/approval_and_budget_ledger.json")


def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load():
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def save(data):
    data["updated_utc"] = now()
    LEDGER.write_text(json.dumps(data, indent=2), encoding="utf-8")


def files_arg(argv):
    for i, a in enumerate(argv):
        if a == "--files" and i + 1 < len(argv):
            out = {}
            for pair in argv[i + 1].split(";"):
                pair = pair.strip()
                if not pair:
                    continue
                if ":" in pair:
                    name, size = pair.rsplit(":", 1)
                    try:
                        out[name] = int(size)
                    except ValueError:
                        out[name] = size
                else:
                    out[pair] = None
            return out
    return {}


def note_flag(argv):
    for i, a in enumerate(argv):
        if a == "--note" and i + 1 < len(argv):
            return argv[i + 1]
    return None


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    data = load()
    cmd = argv[0]
    if cmd == "note":
        kind = argv[1]
        message = " ".join(argv[2:])
        data["policy_events"].append({"utc": now(), "kind": kind, "message": message})
        save(data)
        print("noted", kind)
    elif cmd == "start":
        category, case_id, description, command = argv[1], argv[2], argv[3], argv[4]
        used = data["categories"][category]["used"]
        cap = data["categories"][category]["cap"]
        if used >= cap:
            print("REFUSED: category %s exhausted (%d/%d)" % (category, used, cap))
            return 2
        if data["totals"]["used"] >= data["totals"]["cap"]:
            print("REFUSED: total budget exhausted")
            return 2
        data["categories"][category]["used"] = used + 1
        data["totals"]["used"] += 1
        data["totals"]["remaining"] = data["totals"]["cap"] - data["totals"]["used"]
        event = {
            "event_id": "NA-%03d" % data["totals"]["used"],
            "case_id": case_id,
            "category": category,
            "started_utc": now(),
            "status": "STARTED",
            "description": description,
            "command": command,
            "files_before_utc": {},
            "files_after_utc": {},
            "wall_seconds": None,
            "returncode": None,
            "budget_after_start": {"category_used": used + 1, "category_cap": cap,
                                   "total_used": data["totals"]["used"], "total_cap": data["totals"]["cap"]},
        }
        data["numerical_analysis_events"].append(event)
        save(data)
        print("started", event["event_id"], case_id, "category %d/%d total %d/%d" % (used + 1, cap, data["totals"]["used"], data["totals"]["cap"]))
    elif cmd == "finish":
        case_id, status, wall, rc = argv[1], argv[2], float(argv[3]), int(argv[4])
        files = files_arg(argv)
        event = None
        for e in reversed(data["numerical_analysis_events"]):
            if e["case_id"] == case_id and e["status"] == "STARTED":
                event = e
                break
        if event is None:
            print("no STARTED event for", case_id)
            return 3
        event["finished_utc"] = now()
        event["status"] = status
        event["wall_seconds"] = wall
        event["returncode"] = rc
        event["files_after_utc"] = files
        event["note"] = note_flag(argv)
        save(data)
        print("finished", event["event_id"], case_id, status, "wall", wall)
    elif cmd == "status":
        print(json.dumps({"totals": data["totals"],
                          "categories": {k: {"used": v["used"], "cap": v["cap"]} for k, v in data["categories"].items()},
                          "events": [{"id": e["event_id"], "case": e["case_id"], "status": e["status"],
                                      "wall": e["wall_seconds"]} for e in data["numerical_analysis_events"]]}, indent=1))
    else:
        print("unknown command")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
