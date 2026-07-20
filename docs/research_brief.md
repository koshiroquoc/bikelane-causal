# Project B — Research Brief (v0.1)

## Working title

**Do new protected bike lanes increase Divvy trip starts at nearby stations? A staggered difference-in-differences study in Chicago.**

## Status

Planning and feasibility. No causal model will be estimated until the treatment-data and sample-size gates below pass.

## Research question

Do newly completed protected bike-lane corridors in Chicago change the monthly number of Divvy trips that start at nearby stations, relative to a credible no-installation counterfactual?

## Primary estimand

The average treatment effect on treated station-months: the change in monthly Divvy trip starts at stations near a newly completed protected bike-lane corridor, after completion, compared with the trips those stations would have recorded without that corridor.

The final scale of the estimand (trip-count difference or percentage change) will be fixed after selecting an estimator that supports that interpretation. We will not mix effect scales across estimators.

## Unit definitions

- **Treatment assignment unit:** protected bike-lane corridor.
- **Outcome observation unit:** station-month.
- **Primary outcome:** monthly trip starts (`total_trips`).
- **Secondary outcomes:** `member_trips` and `casual_trips`.
- **Candidate treated station:** within 300 m of a newly completed protected corridor.
- **Candidate exclusion donut:** 300–800 m from a newly completed protected corridor.
- **Candidate control:** outside the donut, with preference for geographically local and pre-trend-comparable stations.

The distance thresholds are provisional design parameters, not choices to be optimized after seeing the effect estimate.

## Time window supported by Project A

Project A currently supplies 36 monthly periods from **2023-07 through 2026-06**.

- Preferred treatment-completion window for at least 12 pre and 12 post months: approximately **2024-07 through 2025-07**.
- Expanded fallback window for at least 9 pre and 9 post months: approximately **2024-04 through 2025-10**, with an explicit short-window limitation.

The exact valid window will be recomputed from the final treatment-month convention and whether the installation month is included in, excluded from, or separated from the post period.

## Project A input contract

Read-only inputs:

- `/Users/nguyenvanquoc/Desktop/bikeshare-forecast/data/processed/station_master.parquet`
- `/Users/nguyenvanquoc/Desktop/bikeshare-forecast/data/processed/station_month_panel.parquet`

Observed audit on 2026-07-20:

- `station_master`: 2,154 stations, 7 columns.
- `station_month_panel`: 45,066 station-month rows, 2,154 stations, 36 calendar months.
- 608 stations appear in all 36 months.
- 1,415 stations span at least 2024-07 through 2025-07 by their first and last observed trip months.
- No duplicate station-month rows and no negative trip counts.
- The panel contains no explicit zero-trip rows.
- 1,023 stations have at least one missing month between their first and last observed trip months, totaling 10,629 internal missing station-months.

Therefore, missing station-months must not automatically be labeled zero until station activity, ID changes, temporary closure, and data-coverage behavior are audited.

## Identification strategy (provisional)

Use staggered difference-in-differences with group-time treatment effects and an event-study representation. The main comparison should use never-treated or not-yet-treated stations that are geographically and behaviorally credible controls.

PPML/TWFE may be included as a count-data baseline or robustness specification. It will not automatically be treated as the primary causal estimate when adoption is staggered and treatment effects may be heterogeneous.

## Feasibility gates

Proceed to full analysis only if all critical gates pass:

1. **Treatment provenance:** each corridor has a defensible completion/opening month and source record.
2. **Independent treatment count:** preferably at least 8–10 usable corridors after exclusions; station count alone is not sufficient.
3. **Observation window:** most usable corridors have at least 12 pre and 12 post months; a 9/9 design is accepted only with a clear limitation.
4. **Station integrity:** treated stations have stable IDs/locations or a documented mapping, and station openings, closures, and relocations are audited.
5. **Control credibility:** a plausible local or matched comparison group exists and raw pre-period trends are not grossly different.
6. **No dominant corridor:** the result is not mechanically driven by one corridor containing most treated stations.

If the gates fail, options are to narrow the research claim, change the outcome/design, or stop. Expanding radii, lane types, or cities solely to rescue statistical significance is not allowed.

## Claims policy

- A clean pre-trend is supportive evidence, not proof of the parallel-trends assumption.
- The project measures Divvy trip starts near lanes, not total cycling and not necessarily total corridor usage.
- Results will be reported with effect size and uncertainty before p-values.
- Null or negative results are valid outcomes.
- If identification diagnostics fail, the final report will use descriptive language rather than a causal claim.

## Immediate next checkpoint

Build a treatment inventory for candidate protected corridors completed in the preferred window, including:

`corridor_id`, street limits, protected-lane type, completion month, geometry source, date source, source URL, and date-confidence grade.

Only after this inventory is spatially joined to Project A stations will we decide whether Project B is feasible as designed.
