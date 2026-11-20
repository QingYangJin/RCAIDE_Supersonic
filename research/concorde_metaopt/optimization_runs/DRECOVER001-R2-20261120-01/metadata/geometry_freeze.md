# Geometry Freeze V2 (zero physical)

- freeze_id: `GBFREEZE2-5f2bb12fe8b1dc68`
- geometry_contract_sha256: `5f2bb12fe8b1dc68c67901843c777328ae984cfdbe4ee71176b369a16a133f15`
- geometry_freeze_v2.json SHA256: `401bc6b6c605eafe416bd4b0e925d106b93673b2e4d2c21f1d21e688d7e62bf1`
- status: `GEOMETRY_FREEZE_V2_ISSUED_ZERO_PHYSICAL`
- base_commit: `01c9274801474c113a2c488e375d451bcd0297c3`
- physical_solver_starts_actual: 0; internal_solver_cases_actual: 0

## Frozen 12D design

| id | name | baseline | lower | upper | unit |
| --- | --- | ---: | ---: | ---: | --- |
| W01 | wing_area | 358.25 | 300 | 420 | m^2 |
| W02 | aspect_ratio | 1.83 | 1.5 | 2.2 | dimensionless |
| W03 | sweep_1 | 67 | 62 | 72 | deg |
| W04 | sweep_2 | 48 | 40 | 56 | deg |
| W05 | sweep_3 | 71 | 66 | 76 | deg |
| W06 | span_location_2 | 0.480469 | 0.35 | 0.58 | dimensionless |
| W07 | span_location_3 | 0.945313 | 0.85 | 0.98 | dimensionless |
| W08 | chord_ratio_2 | 0.408284 | 0.3 | 0.5 | dimensionless |
| W09 | chord_ratio_3 | 0.130178 | 0.08 | 0.2 | dimensionless |
| W10 | tip_twist | 0 | -4 | 4 | deg |
| V01 | vertical_tail_area | 33.91 | 28 | 40 | m^2 |
| V02 | vertical_tail_sweep_delta | 0 | -10 | 10 | deg |

Fixed fuselage: F01 length 61.660000 m, F02 fineness 4.300000, F03 height/width 1.152778.

## Reference contract

- Sref = 358.250000 m2 (W01), Cref = 18.489893 m, Bref = 25.604638 m.
- q = 20483.940233430 Pa, L_ref = 1333704.400 N, CL_target = 0.181743917.
- reference_frame = WING_AC; P2A xcg_m = 16.821978259514 m.
- Force axis: wind/body-aligned, +X downstream, +Y starboard, +Z up; status `DEFINED_NOT_SOLVER_VALIDATED`.
- Moment-reference origin is **ambiguous** between wing-local AC 16.821978259514 m and global AC 30.821978259514 m; see open items.

## Mass / CG / AC (provisional)

- total_takeoff = 184880.000 kg; cg_x = 28.287395109 m; wing AC global = 30.821978260 m; static margin = 0.137079385.
- status: `PROVISIONAL_NOT_FROZEN`; no weight-and-balance, trim or stability claim.

## Real OpenVSP export

| artifact | bytes | SHA256 |
| --- | ---: | --- |
| docs/evidence/drecover001/geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.vsp3 | 301252 | `e471be01fab21663d5ad4aa227a811b6fbdf719d5d459dc3bac712ea135ee8d2` |
| docs/evidence/drecover001/geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.stl | 1245302 | `bae4e17c9c7e594ab50ff2f58db60ddd50fb152fa9a18419a11e9065f734c185` |
| docs/evidence/drecover001/geometry_freeze_v2_artifacts/concorde_geometry_freeze_v2.step | 630057 | `3b0d96366ea22bdbeb982232d17aa5eb6e1595b4369f6aa89aa6c76b18751b5f` |

- Absolute XForm readback: `{"fuselage": {"Abs_Or_Relitive_flag": 0.0, "X_Location": 0.0, "X_Rotation": 0.0, "Y_Location": 0.0, "Y_Rotation": 0.0, "Z_Location": 0.0, "Z_Rotation": 0.0}, "main_wing": {"Abs_Or_Relitive_flag": 0.0, "X_Location": 14.0, "X_Rotation": 0.0, "Y_Location": 0.0, "Y_Rotation": 0.0, "Z_Location": -0.8, "Z_Rotation": 0.0}, "vertical_tail": {"Abs_Or_Relitive_flag": 0.0, "X_Location": 42.0, "X_Rotation": 90.0, "Y_Location": 0.0, "Y_Rotation": 0.0, "Z_Location": 1.0, "Z_Rotation": 0.0}}`.
- STL placement: wing span 25.604638 m, tail span 5.009331 m, fuselage length 61.660000 m (all checks PASS).

## Boundary perturbation

- 24 one-variable-at-a-time model cases: 24/24 ok.
- 24 real OpenVSP construction/readback cases: 24/24 ok.

## Open items

- Mass and CG are the geometry model's PROVISIONAL estimate; this is not a weight-and-balance validation.
- WING_AC moment-reference origin is ambiguous: P2A xcg_m equals the wing-local AC; applying WING_ORIGIN_X_M gives a different global station.
- Force-axis signs are defined here but not read back from VSPAERO; R2 must validate signs and moment reference.
- Nacelle is not exported by the current worker; it remains reference geometry only.
- Lift reference 136,000 kg differs from the provisional 184,880 kg takeoff mass; L_ref is contractual, not a performance result.

No VSPAERO solver was started. This freeze is a geometry/reference contract, not aerodynamic evidence.
