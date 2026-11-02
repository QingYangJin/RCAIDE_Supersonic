# Concorde.py static structure (P0 audit)

relative_path: tutorials/Simulation_Turbojet_Supersonic_Aircraft_4500nmi_Mission/Concorde.py
sha256: 4c633e485a915151faaa8104e6647f9dc02bd08ae1436c22845e5917b3d735bd
lines: 1223
segment_6 references: 2

## Component segment counts

| component | append_segment calls |
|---|---|
| main_wing_segments | 4 |
| vertical_stabilizer_segments | 3 |
| fuselage_segments | 8 |
| nacelle_segments | 2 |
| mission_segments | 11 |

## Mission segment tags (in source order)

count: 28

'section_1', 'section_2', 'section_3', 'tip', 'section_1', 'section_2', 'tip', 'segment_0', 'segment_1', 'segment_2', 'segment_3', 'segment_4', 'segment_6', 'segment_6', 'segment_7', 'segment_1', 'segment_2', 'climb_1', 'climb_2', 'climb_2', 'climb_3', 'climb_4', 'climb_5', 'climbing_cruise', 'level_cruise', 'descent_2', 'descent_3', 'descent_4'

## level_cruise occurrences

| line | text |
|---|---|
| 1123 | segment.tag = "level_cruise" |

## Duplicate segment tags (same tag reused)

| tag | count |
|---|---|
| climb_2 | 2 |
| section_1 | 2 |
| section_2 | 2 |
| segment_1 | 2 |
| segment_2 | 2 |
| segment_6 | 2 |
| tip | 2 |

## Derived-quantity markers

| term | count |
|---|---|
| .areas.reference | 3 |
| .areas.wetted | 5 |
| .aspect_ratio | 2 |
| .chords.root | 5 |
| .mass_properties | 22 |
| .spans.projected | 4 |
| .usable_volume | 0 |
| .volume | 0 |
| .wet_area | 0 |
| reference_area | 1 |
| required_volume | 0 |

## Term counts

| term | count |
|---|---|
| append_airfoil | 7 |
| append_component | 5 |
| append_control_surface | 4 |
| append_segment | 28 |
| aspect_ratio | 2 |
| chord | 39 |
| design_altitude | 1 |
| design_mach | 3 |
| design_range | 2 |
| fuselages | 0 |
| mass_properties | 22 |
| max_fuel | 1 |
| segment_1 | 2 |
| segment_2 | 2 |
| segment_3 | 1 |
| segment_4 | 1 |
| segment_5 | 0 |
| segment_6 | 2 |
| span | 20 |
| sweep | 12 |
| takeoff | 5 |
| vertical_stabilizer | 1 |
| vertical_tail | 0 |
| wings | 4 |

## Top-level functions

- main (line 26)
- save_concorde_results (line 59)
- vehicle_setup (line 150)
- configs_setup (line 799)
- analyses_setup (line 856)
- base_analysis (line 867)
- plot_mission (line 918)
- mission_setup (line 945)
- missions_setup (line 1210)
