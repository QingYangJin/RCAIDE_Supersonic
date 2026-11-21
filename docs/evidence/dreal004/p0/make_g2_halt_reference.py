
"""Record the G2 halt accounting referenced by Issue #14 (no re-grading)."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

G2 = Path(r"D:/RCAIDE/.real_runs/DRECOVER001-G2-20261121-01")
OUT = Path(__file__).resolve().parent / "g2_halt_reference.json"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


b01 = json.loads((G2 / "batch_accounting.json").read_text(encoding="utf-8"))
b02 = json.loads((G2 / "b02_accounting.json").read_text(encoding="utf-8"))
halt = json.loads((G2 / "audits/g2_halt_note.json").read_text(encoding="utf-8")) \
    if (G2 / "audits/g2_halt_note.json").exists() else None
out = {
    "schema": "dreal004.g2_halt_reference.v1",
    "purpose": ("truthful record of the G2 batch halted by Issue #14; not a G2 receipt "
                "and not a PASS"),
    "issue13_handover_comment": "7063823679",
    "issue14": "QingYangJin/RCAIDE_Supersonic#14",
    "b01": {"charged_starts": b01.get("physical_solver_starts_actual"),
            "completed": b01.get("physical_solver_starts_completed"),
            "internal_solver_cases": b01.get("internal_solver_cases_actual_logged"),
            "admitted_labels": b01.get("admitted_labels"),
            "null_labels": b01.get("null_labels"),
            "source": "batch_accounting.json", "sha256": sha(G2 / "batch_accounting.json")},
    "b02": {"charged_starts": b02["physical_solver_starts_actual"],
            "completed": b02["physical_solver_starts_completed"],
            "internal_solver_cases": b02["internal_solver_cases_actual_logged"],
            "admitted_labels": b02["admitted_labels"],
            "null_labels": b02["null_labels"],
            "valid_label_rate": b02["valid_label_rate_over_charged"],
            "b02_starts_max": b02["b02_starts_max"],
            "unused_b02_starts": b02["b02_starts_max"] - b02["physical_solver_starts_actual"],
            "source": "b02_accounting.json", "sha256": sha(G2 / "b02_accounting.json")},
    "cumulative_starts": b02["cumulative_starts"],
    "g2_cap": b02["g2_cap"],
    "g2_receipt_issued": False,
    "g2_maml_run": False,
    "g1_preserved": {"starts": 24, "admitted_labels": 8, "valid_rate": 0.34782608695652173,
                     "reported_in_issue13_receipt_7041128848": True},
    "disclosure": ("B02 was stopped mid-stage2 under issue #14; 34 of the 60 planned "
                   "stage2 cases were never started and 34 B02 starts remain unused. "
                   "No G2 label is re-graded or deleted."),
}
if halt is not None:
    out["halt_note"] = {"source": "audits/g2_halt_note.json",
                        "sha256": sha(G2 / "audits/g2_halt_note.json"),
                        "keys": sorted(halt)[:20]}
OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(out, indent=2, ensure_ascii=False)[:1200])
