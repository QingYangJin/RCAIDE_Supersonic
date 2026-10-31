# P1-P3 implementation note: 12D pipeline and drag ledger

**Scope**: approved P1-P3 software-only repairs; NO new RCAIDE Mission, VSPAERO or SU2 physics calls, no BO/DE or MAML training. Historic 15D artifacts remain unchanged.

## Code paths and gates

- GEO-12D: 12 declared lifting-surface variables expand into the same 15 physical geometry inputs, with 3 fixed fuselage values. The P2 SingleCruiseBackend and P3 DOE screening paths now accept explicit 12D configuration, while defaulting to the legacy 15D configuration. G23 checks both declared and fixed variables.
- MISSION-DATA: the data schema rejects extra 15D fuselage fields in a 12D row. The CLI exposes --design-space-config for smoke (real Mission, NOT APPROVED to run) and doe (zero-physics screening). Physical budget checks remain mandatory.
- BODY-CORR: the new read-only drag_ledger module records available RCAIDE component coefficients and their wind-axis drag magnitudes in N using end-of-segment dynamic pressure and the actual wing Sref. Absent fields and trim-factor assumptions remain NULL; nested wave-lift/volume are expressly diagnostic and must not be added again. Numeric closure is *not* evidence of physical no-overlap. There is still NO calibrated, design-dependent wing-body interference correction.
- New tests/test_12d_pipeline.py and tests/test_drag_ledger.py are offline unit tests. Their existence does NOT mean the local suite has been executed.

## Review errata from the previous static review

1. LF-R6 incorrectly described 358.25 m2 as wing wetted area. The archived geometry says: reference area = exposed area = 358.25 m2 (unexposed wing-body region NOT modelled); wetted area = 717.57475 m2. The existing hashed review run is an immutable historical snapshot; this note supersedes that *wording*, not the underlying measurements.
2. The 11 proposed validations are **4 VSPAERO main-wing cases + 2 RCAIDE Mission vertical-tail sensitivity probes + 5 SU2 Euler cases**, not 6 VSPAERO. At least one additional independent wing-body benchmark or correction-calibration source is still necessary for BODY-CORR. Completing the 11 cases alone cannot yield a full-aircraft validation.
3. The SU2 Mach-2 wedge single case cannot *by itself* establish mesh convergence. A grid refinement or previously verified reference is needed. Similarly, wing-only high-fidelity CFD does not validate the vertical-tail corrections used by the 12D objective.
4. Trefftz induced drag and supersonic lift wave drag may overlap, but both scaling with CL squared does NOT prove double counting. Independently compare consistent force components before drawing such a conclusion.
5. Previously archived P2 Mission evidence: 10 calls with complete run records; 5 earlier calls only described in README, not independently verifiable. This patch adds 0 calls.

## Mandatory local verification before any approval

Execute on the project computer and record the actual HEAD, interpreter, logs and outcomes:

python -E -s -B -m unittest research.concorde_metaopt.tests.test_12d_pipeline research.concorde_metaopt.tests.test_drag_ledger -v

python -E -s -B -m unittest discover -s research/concorde_metaopt/tests -t . -v

Code/test review status: PENDING_LOCAL_EXECUTION_AND_INDEPENDENT_A5_REVIEW. LF-M2.02, HF-M2.02, BODY-CORR and overall P1-P3 physical acceptance are NOT APPROVED. The earlier static review JSON and manifest have not been modified or silently re-hashed.
