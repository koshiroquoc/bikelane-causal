# Phase 2 Data-Quality Report

**Exit-gate decision:** `PASS`  
**Build policy:** observed station-months only; no missing month is converted to zero  
**Treatment effects estimated:** none

## Reconciliation

- Project A station master: 2,154 stations.
- Project A panel: 45,066 observed station-months.
- Phase 2 assignment table: 2,154 unique stations.
- Analysis panel: 33,018 observed rows across 1,639 stations and 36 calendar months.
- Expected observed rows after station-role filtering: 33,018; difference: 0.
- Duplicate station-months: 0.

## Spatial assignment

- Primary treated: 40 stations.
- Represented primary corridors: 12.
- Candidate controls: 1,599 stations.
- Treated but incomplete 12/12 window: 25 stations, excluded.
- Donut: 164 stations, excluded.
- Near another 2024–2025 candidate corridor: 326 stations, excluded.
- Treated stations near multiple primary corridors: 8; earliest completion then nearest distance determines assignment.

Distances use `EPSG:26916`. Treated stations are at most 300 m from an eligible corridor; the exclusion donut extends to 800 m. Controls are also screened against every matched 2024–2025 candidate corridor.

## Time and missingness

- Panel window: 2023-07 through 2026-06.
- Transition rows present and excluded by `analysis_row`: 40.
- Stations with at least one internal missing observed month: 883.
- Rows added through zero imputation: 0.
- Negative outcome rows: 0.

`event_time = 0` is the first full post-treatment month. The completion month is `event_time = -1`, flagged as transition, and excluded. Never-treated controls have null event time and `post = 0`.

## Cohort-specific control availability

| First post month | Controls with complete 12/12 window |
|---|---:|
| 2024-08 | 391 |
| 2024-11 | 403 |
| 2024-12 | 408 |
| 2025-01 | 406 |

The control group is not locked here. Phase 3 may compare broad and local eligible controls, but both must be drawn from these pre-screened candidates.

## Critical validations

- Unique station IDs in assignment: PASS.
- Unique station-month keys in panel: PASS.
- Treatment monotonicity: PASS.
- Event-time boundaries: PASS.
- Meter-based distance thresholds: PASS.
- Donut and candidate-corridor exclusions absent from analysis panel: PASS.
- Missing months preserved rather than filled: PASS.
- Input/output row counts reconciled: PASS.

## Output fingerprint

`station_month_analysis.parquet` SHA-256: `97a8d70b6a84fd491709400dbf000d3cd57a6ea8544c82c6b0100550c3759944`
