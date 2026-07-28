# Phase 6 Visual QA

**Decision:** `PASS` on 2026-07-27.

The release preserves analytical figures generated in their original phases. Phase 6 adds only `study_design_map.png`, which replaces the preliminary map in the executive README. No treatment-effect figure was cosmetically regenerated with different data, scales, windows, or uncertainty after results were known.

| Figure | Role | Units / sample | Uncertainty | QA result |
|---|---|---|---|---|
| `study_design_map.png` | Final design overview | 40 treated stations, 83 unique matched controls, 12 corridors; projected Chicago coordinates | Not applicable | PASS — final rather than preliminary title, exposure radius and exclusion rule stated, legend readable. |
| `phase3_pretrend_leads.png` | Identification warning | Percent effect by pre-treatment event month | Two-way clustered 95% intervals | PASS — reference and transition conventions stated. |
| `phase4_event_study.png` | Main dynamics | Group-time ATT translated to percent; event months −13 to +11 | Two-way clustered 95% intervals | PASS — zero line, reference month, excluded transition, and percent units visible. |
| `phase4_estimator_comparison.png` | Estimator registry | Percent change on reconciled sample | 95% intervals | PASS — estimator role remains explained in adjacent report text. |
| `phase5_radius_sensitivity.png` | Spatial-rule robustness | Percent change under three treated/donut rules | Two-way clustered 95% intervals | PASS — primary and alternative thresholds readable. |
| `phase5_leave_one_corridor_out.png` | Corridor influence | Percent change after each corridor omission | Two-way clustered 95% intervals | PASS — main estimate and zero reference visible; long corridor labels remain readable. |
| `phase5_geography_placebo.png` | Pipeline falsification | Distribution of 50 placebo ATTs in percent | Empirical null distribution | PASS — real ATT and placebo median identified; replication axis labeled. |

All release figures exceed 1,200 pixels in width or height and render without clipped labels. README images include nearby prose defining the sample, estimator, and interpretation boundary.
