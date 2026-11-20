import json, hashlib
from pathlib import Path
RUN=Path(r"D:/RCAIDE/.real_runs/DRECOVER001-R2-20261120-01")
WT=Path(r"D:/RCAIDE/.worktrees/drecover001-20261117")
def load(p): return json.loads(Path(p).read_text(encoding="utf-8"))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
freeze=load(RUN/"r2_code_freeze.json"); gate=load(RUN/"r2_gate_record.json")
pilot=load(RUN/"pilot_ledger.json"); labels=load(RUN/"pilot_label_status.json")
matrix=load(RUN/"matrix_input_verification.json"); flow=load(RUN/"flow_default_equivalence/verification.json")
pre=load(RUN/"preflight_r2/recovery_preflight_receipt.json")
verdict=load(r"D:/RCAIDE/.recovery-local-restore/a5_reviewer/run_r2_20261120/verdict.json")
rows=[]
for d in sorted((RUN/"cases").iterdir()):
    if not (d/"task_spec.json").exists() or not (d/"plan.json").exists(): continue
    if not d.name.startswith(("m160-","m180-","m220-","m240-","m202-")): continue
    s=load(d/"task_spec.json"); p=load(d/"plan.json")
    q=0.5*float(s["flow_conditions"]["rho_kg_m3"])*float(s["flow_conditions"]["vinf_m_s"])**2
    cl=float(s["lift_target_n"])/(q*float(s["sref_m2"]))
    rows.append({"case":s["case_id"],"task":s["task_id"],"split":s["split"],"part":s["partition"],
                 "mach":s["mach"],"vinf":s["flow_conditions"]["vinf_m_s"],"q":q,"cl":cl,
                 "cl_target":s["cl_target"],"rel_q":abs(q-s["dynamic_pressure_pa"])/q,
                 "rel_cl":abs(cl-s["cl_target"])/cl,"alpha":s["alpha_center_deg"],
                 "plan":p["plan_sha256"] if "plan_sha256" in p else sha(d/"plan.json"),
                 "vspgeom":p["geometry"]["files"]["vspgeom"]["sha256"],"design":s["design"]})
rows.sort(key=lambda r:(r["mach"],r["task"],r["design"],r["part"]))
def table():
    out=["| case | task | split/part | Mach | Vinf m/s | q Pa | CL target | alpha c | plan sha (12) |","|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append("| %s | %s | %s/%s | %.2f | %.6f | %.6f | %.12f | %.9f | %s |"%(r["case"],r["task"],r["split"],r["part"],r["mach"],r["vinf"],r["q"],r["cl_target"],r["alpha"],r["plan"][:12]))
    return "\n".join(out)
max_rel_q=max(r["rel_q"] for r in rows); max_rel_cl=max(r["rel_cl"] for r in rows)
text="# R2 A5 closure review dossier (2026-11-20)\n\n"
text+="Reviewer role: A5 independent read-only reviewer. No tools. This dossier is the only input. Do not treat any local audit as human authentication. Return only the requested JSON verdict.\n\n"
text+="## 1. Identity, authorization and boundary\n\n"
text+="- Owner authorization: message ref §m05968§; authorization §%s§; run §%s§; batch §%s§.\n"%(pilot["authorization_id"],pilot["run_id"],pilot["batch_id"])
text+="- Budget: 24 physical solver starts, 128 internal cases per start, timeout 1200 s, retries 0, parallel 1, MAML training runs max 8. Charged before this review: **3 starts / 23 internal cases / 0 retries; 21 starts remain**. No solver start has occurred since the A5 verdict below.\n"
text+="- Physical scope: real VSPAERO 3.55 / VSPAERO v.7.2.2 at fixed altitude 18,288 m, fixed geometry contract §5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15§, fixed lift target 1,333,704.4 N. Labels remain §LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED§; local audit is a separate script, not human or A5.\n"
text+="- Same-machine backup is the only backup; Owner waiver §WAIVER-OFFMACHINE-BACKUP-20261118§ waives the off-machine failure domain. It is not an independent backup.\n\n"
text+="## 2. Original A5 verdict and conditions\n\n"
text+="- Verdict §%s§; pilot disposition §%s§; reviewed §%s§; model §%s§; human signature false.\n"%(verdict["verdict"],verdict["pilot_disposition"],verdict["reviewed_utc"],verdict["model"])
text+="- Original findings: pilot before A5; uncommitted code / no full preflight; Ew=inf scope; flow_conditions default equivalence; NOT_AUTHENTICATED labels / same-machine backup; limited MAML power.\n\n"
text+="## 3. Condition closure evidence\n\n"
for c in gate["conditions"]:
    text+="- **%s — %s**. %s\n"%(c["id"],c["status"],c["detail"])
text+="\n## 4. Code freeze and full preflight\n\n"
text+="- Freeze §%s§ binds %d files (source, scripts, authorization, pilot and A5 evidence).\n"%(freeze["freeze_id"],freeze["file_count"])
text+="- Remote commit §%s§, tree §%s§, parent §%s§, branch §recovery/drecover001-20261117§; worktree clean at that commit. The three changed source files and the first A5 dossier are in that commit.\n"%(freeze["remote_commit"],freeze["remote_tree"],freeze["remote_parent"])
text+="- Full zero-physical preflight §%s§: **%d tests, %d failures, %d errors, %d skipped, status %s**; physical_solver_starts_actual=0, real_meta_training_executed=false, admitted_scientific_labels=0. Checkpoint §0211bc97e73418722d60e45c3eb2dd812686cc17cc412f99168b227f0dc7b155§.\n"%(pre["run_id"],pre["tests_run"],pre["failures"],pre["errors"],pre["skipped"],pre["software_tests_status"])
text+="- Targeted pytest earlier hit §PermissionError: [WinError 5]§ in the sandbox temp directory, not assertion failures. The full preflight uses the project unittest path and passed; §--basetemp§ is the documented workaround.\n\n"
text+="## 5. Pilot starts and admission status\n\n"
text+="- 3 charged starts: §baseline-coarse§ (7 alpha, exit 0, §POLAR_HAS_INVALID_ROWS§ because alpha=0 has E=-nan(ind)/Ew=-nan(ind)); §baseline-refine-01§ (13 alpha, SOLVED); §baseline-admit-01§ (3 alpha, SOLVED).\n"
text+="- Admitted certificates: baseline-admit-01 §di_n=121434.35218570218§, alpha 5.18125; baseline-refine-01 §di_n=121492.55215765651§, alpha 5.1825, lift relative error 0.00022375442687054152. baseline-coarse is **NULL_LABEL**, not admitted.\n"
text+="- All certificates are §LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED§; the audit role is §SEPARATE_LOCAL_REIMPLEMENTATION_NOT_HUMAN_NOT_A5§.\n\n"
text+="## 6. Ew=inf scope proof\n\n"
text+="§research/concorde_metaopt/dreal001/meta/raw_verification.py:144-160§ removes a nonfinite value only when §key == \"Ew\" and math.isinf(value)§. §Ew§ is a diagnostic drag column; it is not used in §D_i_N=q*Sref*CDi§. §Ew=NaN§ is not removed, and every other nonfinite column (including CLtot/CDtot/CDi) still raises §ContractError(\"nonfinite polar row\")§. Regression test §test_infinite_ew_diagnostic_tolerated_but_nan_or_core_inf_fatal§ is at §research/concorde_metaopt/tests/test_recovery_real_admission.py:214§; the admission test file reports 18 passed. The pilot certificates were produced from rows whose CL/CDi are finite.\n\n"
text+="## 7. flow_conditions default equivalence and per-case q/CL\n\n"
text+="- Default vs explicit baseline flow: same §.vspgeom§ SHA §f7e5a5dae37cfc0c72419028978125993dbcbdf4776b83ea8eb34d74452d1b34§; deck Sref/Mach/AoA/ReCref/Vinf/Rho rows identical; q=20483.940233430174; CL=0.18174391741992046; verdict §%s§.\n"%flow["verdict"]
text+="- 14 matrix input decks were verified independently: **%d checks, %d failures**, including Sref/Mach/Vinf/Rho/ReCref/q/CL/plan SHA/alpha count.\n"%(matrix["check_count"],matrix["failure_count"])
text+="- Below, q and CL are recomputed as §q=0.5*rho*Vinf^2§ and §CL=L_ref/(q*Sref)§ from each task_spec. Maximum relative q deviation from the stored dynamic pressure: %.3e; maximum relative CL deviation from stored cl_target: %.3e. Every case has 15 alpha points.\n"%(max_rel_q,max_rel_cl)
text+=table()+"\n\n"
text+="Task family: M1.60 §concorde-real-M160§ train; M1.80 §concorde-real-M180§ train; M2.02 §concorde-fixed-cruise-dreal001-real-v1§ train (d00 already admitted in pilot; matrix adds d01/d02); M2.20 §concorde-real-M220§ val; M2.40 §concorde-real-M240§ test. d00/d01 are support, d02 is query. Designs: d00 baseline X12; d01 W01=361.8325; d02 sweep_1=67.5.\n\n"
text+="## 8. MAML plan and limitations\n\n"
text+="- MAML starts only after every successful matrix case has an admission certificate; failed cases stay null labels. No label will be synthesized or interpolated.\n"
text+="- Design: 3 train tasks, K=2 support designs per task, 1 query design, FOMAML and pooled-pretrain comparison; exploratory only, no generalization claim. Same-machine backup limitation is recorded. A5 is not a human signature.\n\n"
text+="## 9. Requested decision\n\n"
text+="Decide whether conditions C1–C5 are satisfied and whether it is admissible to (a) run the 14 matrix cases (14 more starts, total 17/24; 15 internal cases each) and (b) run the exploratory real-label FOMAML/K-shot experiment after case-by-case admission. Return §PASS§ only if both are admissible under the stated limits; otherwise §CHANGES_REQUIRED§ with exact remaining actions.\n\n"
text+="## 10. Integrity anchors\n\n"
for label,p in [("r2_code_freeze.json",RUN/"r2_code_freeze.json"),("r2_gate_record.json",RUN/"r2_gate_record.json"),("pilot_ledger.json",RUN/"pilot_ledger.json"),("pilot_label_status.json",RUN/"pilot_label_status.json"),("matrix_input_verification.json",RUN/"matrix_input_verification.json"),("flow verification.json",RUN/"flow_default_equivalence/verification.json"),("preflight receipt",RUN/"preflight_r2/recovery_preflight_receipt.json"),("original A5 verdict",Path(r"D:/RCAIDE/.recovery-local-restore/a5_reviewer/run_r2_20261120/verdict.json"))]:
    text+="- §%s§: %d bytes, sha256 §%s§\n"%(label,Path(p).stat().st_size,sha(p))
text=text.replace("§",chr(96))
out=WT/"docs/evidence/drecover001/r2_a5_closure_dossier_20261120.md"
out.write_text(text,encoding="utf-8")
print("wrote",out,"bytes",out.stat().st_size,"sha256",sha(out),"rows",len(rows),"max_rel_q",max_rel_q,"max_rel_cl",max_rel_cl)
print(text[:3500])
