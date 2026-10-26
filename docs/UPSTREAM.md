# Upstream provenance and local modifications

Publication record: **2026-10-26**. Maintainer of this workspace: **QingYangJin**.

## Origin and licensing

The included tutorials and digital hangar originate from [leadsgroup/RCAIDE_LEADS](https://github.com/leadsgroup/RCAIDE_LEADS), commit [`5d80bd5006828c967cc8d3425e29a9b3a3385608`](https://github.com/leadsgroup/RCAIDE_LEADS/tree/5d80bd5006828c967cc8d3425e29a9b3a3385608). The upstream repository identifies RCAIDE-LEADS as developed at the University of Illinois Urbana-Champaign LEADS laboratory, building on RCAIDE and its contributors.

Upstream `Tutorials/` is stored as `tutorials/`; `Digital_Hangar/` is stored as `digital_hangar/`. Their original repository README, PyPI README, package metadata and AGPL v3 LICENSE are retained under each `_repository/` directory. The root LICENSE is an unmodified copy of the imported upstream license; [NOTICE.md](../NOTICE.md) describes copyright and the scope of the local license grant.

This is an application/tutorial repository, not a fork carrying the complete RCAIDE library or upstream Git history. The separately installed core distribution is `RCAIDE-LEADS==1.5.0`.

The official standard-atmosphere example is from commit `2d2ad0e8b5dc00b75d84879ea02cf8c098b04008`, upstream path `VnV/Verification/atmosphere/atmosphere.py`. It retains its own provenance and license in `examples/official/`. Its SHA-256 is `fd25d50fba0774fe3a9fc6a1449e6a468994d508962676076d23317f7bf3860b`.

## Modified upstream files

Each file below contains a prominent local-modification notice dated 2026-10-26. That date records this published modified version; earlier local changes were already present. Original authorship notices are preserved, including M Clarke's Concorde header.

| Local path, under tutorials/ | Local modifications |
| --- | --- |
| `Optimization_Wing_Planform_Fuel_Burn/Missions.py` | Correct descent_2 end altitude and explicit start/end airspeed settings. |
| `Optimization_Wing_Planform_Fuel_Burn/Optimize.py` | Use the local constrained differential-evolution adapter; resource settings, separate run directories, result export and initial-design handling. |
| `Optimization_Wing_Planform_Fuel_Burn/Procedure.py` | Append performance-evaluation history through the local Save_Results helper. |
| `Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py` | Add mission-result JSON extraction/export and error recording. |

Other local additions include `Differential_Evolution.py`, `Parallel_Differential_Evolution.py`, `Run_Optimize_Quick.py`, `Save_Results.py`, local guides, environment guards, launchers and publication/maintenance files. Root LICENSE applies to local additions under the terms described in NOTICE. Existing third-party notices are not removed or superseded.

## Verification and scope

Against the fixed tree above, all **65** tutorial baseline files are present: **61 unchanged**, **4 modified**. All **180** digital-hangar baseline files are byte-identical to their Git blobs. The [machine-readable manifest](upstream-manifest.json) records upstream blob IDs and current SHA-256 values for every baseline file. The four original modified blobs were fetched again from the upstream GitHub API during publication preparation.

Unmodified upstream content is preserved as source material, not claimed as local work. Root license placement and modification notices do not transfer copyright or imply endorsement. Local runtime environments, generated run histories, logs, caches, backup files and temporary metadata downloads are excluded from Git. Binary model/data assets remain accompanied by the preserved upstream license.

When distributing this modified version, preserve the applicable license text, upstream notices, source and modification records. If a modified covered program is offered for remote interaction as a network service, review and meet AGPL section 13's corresponding-source requirements. This repository's availability supplies source for the material included here; it does not assert compliance for separately deployed applications or undistributed external packages.

For research citation, follow [the preserved upstream instructions](../tutorials/_repository/README.md#citing-rcaide). No new bibliographic claim is made here.
