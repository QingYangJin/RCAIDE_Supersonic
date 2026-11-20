# G0 独立审查材料（A5 单发只读）

- 审查对象：Issue #13 G0 的代码修复与历史 24 次真实 VSPAERO 原件的 GitHub 上传/回读。
- 分支：research/dreal003-expanded-aero-meta-20261120
- commit：1f0bdd53af38e58f5e16394fc7e1c4cc2ee866f7
- tree：71d9fcfef564d8a51b3f54b2e2c4c39f144fe5cc
- parent：4b6bff5688b264935dc8181a40fc5b76298f20f2
- 本轮新增真实求解器启动：0。G0 上传的是历史批次原件，不是新物理。

## 1. Issue #13 对 G0 的硬要求

1. A1 修复 solver_runner.build_evaluation 使用 per-case Mach/Rho/Vinf/q/Sref，不得再用全局 M2.02/q=20483.940。
2. A3 复审 real_training / RealAdmissionManifest / split / fail-closed。
3. A4 把旧 24 次的原件实际上传到 GitHub（不是 pointer、不是本地路径、不是只给哈希）。
4. Lead/A5 从空目录下载至少 1 个成功 case 和 1 个失败 case，重算 Di_N，核对 24/645/9/null 账本。
5. A5 对确切新 SHA 给出 G0_CODE_PASS 与 G0_REMOTE_RAW_RETRIEVAL_PASS。
6. G0 首条回执必须回答：旧 24 文件是否存活/何时上传；Mach/q 修复与全量测试；G1 第一批预注册与 solver 上限；G2 split 冻结草案；GitHub 完整文件链接与新目录回读。

## 2. 代码身份（工作树逐字节 SHA256）

| 文件 | 字节 | SHA256 |
|---|---:|---|
| research/concorde_metaopt/dreal001/geometry/solver_runner.py | 42,284 | cd732583ab492885a225b06ef57d16a6930503cae87873689eaec1dde6f30ec3 |
| research/concorde_metaopt/tests/test_recovery_solver_runner.py | 6,492 | 7f29d21cc45cf7deb0469f6504145bb8065cc0d6f22eb59a4e934207a8481da1 |
| docs/evidence/dreal003/g0/verify_a1_case_flow.py | 3,561 | 4188d2f3df23215fbfdca4da7d86b30bea9ec6bf7107108f9f70aca3e1189170 |
| research/concorde_metaopt/dreal001/meta/real_admission.py | 18,286 | 4322554ea488dd583a9c06fc8bb611e0584360573287673fe46bbbcc605ee3fc |
| research/concorde_metaopt/dreal001/meta/real_training.py | 6,885 | 608f9b087f4d0293ea667c837aaa7f9855f4c1f1fd3718536cc3dadf177819ca |
| research/concorde_metaopt/dreal001/meta/meta_dataset.py | 10,611 | 48e97ddea8505791812b822ace01ec3f4cc4c48631b0fbf3a000f902690561b8 |
| research/concorde_metaopt/dreal001/meta/task_spec.py | 4,052 | 5413a1e8c1b6c71bb2af3093abfb1102eb2191e8781a5afcf5fbbe5ff5810ca5 |
| research/concorde_metaopt/tests/test_recovery_real_admission.py | 15,088 | 0b5f12b52faa20ae3b7dd5ef39512b0c0a127592174ceaedaa5c28ba5f04b136 |
| research/concorde_metaopt/tests/test_recovery_real_training.py | 1,929 | a8e70b3daf260643919034d4ed3a5d2e9cb44e3f9410bb84f2d2bc0816d3056b |
| research/concorde_metaopt/tests/test_recovery_meta_contracts.py | 13,281 | d5028d57c8b892cef93515e9d35d33c0af33043538124f8042b17f0493d783a4 |

## 3. A1 修复内容与验证

solver_runner.py 新增 _read_optional_json(path: Path) 与 _case_flow_conditions(cwd: Path, basename: str, geometry_sref_m2: Optional[float] = None)：

- 优先读取 case 的 task_spec.json；其次 case_inputs.json 的 sweep_input_readback.inputs_double；最后回退全局 TASK_SPEC。
- q 与 0.5*rho*Vinf^2 相对差 > 1e-6*max(1,q) 时抛 PreflightError("case flow conditions disagree with q from case task spec")。
- build_evaluation 使用 per-case sref/q/lift/mach/rho/vinf，preflight 写 case_flow。

真实 24 case 解析出的 per-case 条件：

| case | q (Pa) | Mach |
|---|---:|---:|
| M160 | 12851.40843975621 | 1.6 |
| M180 | 16265.063806566453 | 1.8 |
| M202 | 20483.940233430174 | 2.02 |
| M220 | 24297.194081414087 | 2.2 |
| M240 | 28915.66898945147 | 2.4 |

Sref 358.25 或 361.8325；lift 1,333,704.4 N。

G0 分支零物理 preflight：run_id=DRECOVER001-SOFTWARE-20261120T121100Z，253 tests，0 failed / 0 error / 0 skipped，physical_solver_starts_actual=0。

verify_a1_case_flow.py 结果：24 cases，23 有 evaluation；6 条由 CL_TARGET_OUTSIDE_POLAR 变为 LIFT_MATCHED_BY_INTERPOLATION（m160-d00-support-r1、m160-d02-query-r1、m180-d00-support-r1、m180-d02-query-r1、m240-d00-support-r1、m240-d02-query-r1），12 条仍 outside，新增物理 0。

## 4. 远端上传与回读证据

远端路径：research/concorde_metaopt/optimization_runs/DRECOVER001-R2-20261120-01/

- 远端文件数：1,274；总字节：209,746,158。
- 与本地工作树逐文件 size 对比：1,274/1,274 一致。
- GitHub API tree 回读：truncated=False。
- 批次原件：24 个 case 目录，1,344 个文件，209,926,588 字节。
- 提交前状态：23 完成并产出 case_result，1 中断（m240-d01-support）无 case_result。
- 准入标签：10 张证书、9 个唯一 (task_id, design_sha256)、9 条 admitted labels、14 条 null/failed。

本轮从空目录用 GitHub 精确 commit 回读 7 个文件：

成功 case m160-d00-support-r1：task_spec.json、case_inputs.json、case_result.json、admission_certificate.json、m160_d00_support_r1.polar。
失败 case m240-d01-support：task_spec.json、m240_d01_support.vspaero。

7/7 文件与本地工作树逐字节 SHA256 相同（bad=[]）。

失败 case 的 case_result.json 与 admission_certificate.json 在远端均为 404，与“中断、无标签”一致；其本地目录仍有 31 个原始文件。

## 5. Di_N 重算（两口径披露）

m160-d00-support-r1 证书记录：di_n=175533.59122875682；q=12851.40843975621；Sref=358.25；CDi=0.038126181642；CL=0.289604495511；alpha=7.47。

- 在证书记录的 alpha=7.47 网格点重算：di=175533.59122875682，与证书逐位一致。
- 用 A1 修复后的 build_evaluation 在原始 polar 内精确插值到 lift_target=1,333,704.4 N：alpha=7.472104416484619，CDi=0.038147364348580154，di=175631.11677151572，相对差 5.56e-4。

原因：旧证书用 alpha=7.47 最近网格点，没有精确命中升力目标；A1 之后改为在 polar 内精确升力插值。两值都满足 di=q*Sref*CDi。旧标签是 pre-A1 历史标签，G0 只上传原件，不回写、不重标、不声称已重新认证。

## 6. A3 内审（Lead 自审，不是 A5 结论）

- admitted_labels.csv 9 行与 10 张证书逐字段一致；9 个唯一 (task_id, design_sha256)。
- 重复身份：同一 task concorde-fixed-cruise-dreal001-real-v1、同一 design 937aa7c9… 出现两次，证书编号 ADM-R2-B01-BASELINE-ADMIT-01 与 ADM-R2-B01-BASELINE-REFINE-01；去重后 9 条标签。
- 全部证书 di_n=q*sref*cdi（相对误差 1e-9），evidence_scope=LOCAL_RAW_BYTES_VERIFIED_AUDIT_BOUND_NOT_AUTHENTICATED。
- 守卫探针：手写 AdmissionCertificate 被拒（must be issued by admit_real_manifest）；无证书的 MetaDataset 抛 REAL_ADMISSION_NOT_IMPLEMENTED: independent gates and raw verification required；support/query 同设计泄漏被拒；failed observation 携带 cl 被拒；RawFile ../escape 被拒。
- A3 内审判定：A3_INTERNAL_AUDIT_PASS。

## 7. 明确不声称的事项

- 本轮没有新增真实求解器启动，physical_solver_starts_actual=0。
- 旧 24 次标签为 pre-A1 历史标签，未重新认证；G0 不声称这些标签已被 A1 修复后重新验证。
- 同机备份，不是异机故障域；Owner 已豁免异机备份要求。
- G1 尚未预注册、未授权；NO_PHYSICAL_GO。
- 本审查是 deepseek-flash 单发只读评审，不是人类签名。

## 8. 请给出

一个 JSON 对象，键为：

{
  "reviewer": "deepseek-flash",
  "review_type": "independent_subagent_single_shot_read_only_dossier",
  "reviewed_utc": "...",
  "verdict": "G0_APPROVE" | "G0_CHANGES_REQUIRED" | "G0_REJECT",
  "gate_verdicts": {
    "G0_CODE_PASS": "PASS" | "PASS_WITH_DISCLOSURE" | "FAIL" | "UNVERIFIED",
    "G0_REMOTE_RAW_RETRIEVAL_PASS": "PASS" | "PASS_WITH_DISCLOSURE" | "FAIL" | "UNVERIFIED"
  },
  "findings": [{"severity": "major"|"minor", "claim": "...", "evidence": "...", "required_action": "..."}],
  "disclosures_required": ["..."],
  "residual_risks": ["..."],
  "human_signature": false
}

只输出 JSON。若无法独立核验的项标 UNVERIFIED，不要假设为真。
