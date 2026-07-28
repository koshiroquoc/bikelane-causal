# Technical Research Memo

## Question and conclusion

This study asks whether newly completed protected bike-lane corridors changed monthly Divvy trip starts at nearby Chicago stations. The primary matched group-time estimate is −10.8% with a 95% confidence interval from −24.0% to 2.3%. The interval includes zero, so the analysis does not establish an increase. The negative point estimate is not interpreted as proof that the lanes reduced ridership: pre-treatment diagnostics are imperfect, treatment timing is uncertain, cohort effects are heterogeneous, and the matched geography placebo does not clear its locked tail criterion.

The final release decision is therefore `PASS WITH LIMITATIONS`. The project demonstrates a reproducible design and an honest null/negative result, not a clean causal finding.

## Data and provenance

The outcome panel is inherited from a separate, completed bikeshare data project. It contains 45,066 observed station-month rows for 2,154 stations from July 2023 through June 2026. The panel has no duplicate station-month keys or negative outcomes. Missing station-months are preserved as missing; they are never converted to zero.

Treatment candidates were assembled from the locked 2024–2025 CDOT project universe. Adjacent segments belonging to the same installation were consolidated into corridors. Each corridor retains its treatment variant, geometry, source URLs, timing confidence, and audit notes. Corridors without a medium- or high-confidence usable month or matched geometry remain in the inventory but cannot enter the primary analysis.

All dates in the final treated sample are medium-confidence. Some dates identify a specific completion month; others use the earliest month by which physical protection was independently verified. The analysis does not describe these conservative dates as exact opening dates.

## Estimand and exposure

The target is the average change in monthly trip starts for treated station-months relative to the trips those stations would have recorded without the corridor installation. The reported scale is percent of the estimated treated counterfactual mean.

A station is treated if it is within 300 m of a primary corridor. Stations 300–800 m from a primary corridor are excluded as a spillover donut. Candidate controls must also remain more than 800 m from every corridor in the full candidate inventory. If a station lies within 300 m of multiple primary corridors, it is assigned to the earliest verified completion month and then the nearest corridor; the multiple-exposure flag is retained.

The completion month is treated as transition and excluded. `event_time = 0` is the first full post-treatment month, and `event_time = -2` is the common reference month. Every selected treated and control station has all 12 required pre-treatment and 12 post-treatment observations for its cohort.

The final sample contains 40 treated stations across 12 corridors and four first-post cohorts. Four corridors contain one treated station. Eight treated stations are exposed to more than one eligible corridor.

## Control construction

The primary design uses three controls per treated station, selected without replacement within each cohort. Candidate controls must be within 3 km of a corridor treated in that cohort while remaining outside all locked exclusion zones. Matching uses only the 12-month pre-period:

1. mean `log(1 + total trips)`;
2. linear pre-period slope;
3. pre-period variability; and
4. member-trip share.

No post-treatment outcome enters selection. The frozen design has 120 cohort-control assignments and 83 unique control stations. Broad and unmatched cohort-local pools are sensitivity comparators, not alternative headline designs.

## Identification diagnostics

The treated-station-weighted matched raw pre-trend gap is 0.21 percentage points per month. No corridor crosses the locked three-point monthly raw-slope warning. These diagnostics support proceeding but do not prove parallel trends.

The stricter pre-treatment lead diagnostic is less reassuring. A two-way-clustered four-bin joint test rejects exact zero (`F(4,11) = 4.41`, `p = 0.023`), and the largest individual lead is −16.3%. The automatic Phase 3 failure rule required both `p < 0.05` and an absolute lead of at least 20%; only the first condition is met. Matched balance also remains weak for the sparse November and December 2024 cohorts.

Phase 3 was therefore recorded as `PASS WITH LIMITATIONS`. This authorizes the registered estimators but requires every interpretation to retain the lead warning, sparse-cohort problem, and timing uncertainty.

## Estimation and inference

The primary estimator follows group-time staggered-adoption logic with never-treated matched controls. Station-level changes from the common reference month are differenced against matched control changes, aggregated over post-treatment months, and translated to percent of the estimated treated counterfactual mean.

The secondary staggered-robust specification is cohort-stacked PPML with stack-station and stack-calendar fixed effects. Transparent TWFE OLS and pooled PPML-TWFE models are reported only as baselines. Main matched-estimator uncertainty is two-way clustered by treated corridor and reused control station. Confidence intervals use t critical values based on 11 corridor degrees of freedom.

The estimator registry prevents result-based selection. PPML could become the headline only if the identification gate passed, samples reconciled, the model converged, and cohort heterogeneity was not severe.

## Main results

| Estimator | Role | Estimate | 95% confidence interval |
|---|---|---:|---:|
| Group-time ATT | Registered headline | −10.8% | −24.0%, 2.3% |
| Cohort-stacked PPML | Staggered-robust comparison | −4.8% | −18.6%, 11.2% |
| Specific-date group-time subset | Timing-quality sensitivity | −11.0% | −34.7%, 12.7% |
| TWFE OLS log baseline | Transparency only | −1.6% | −8.9%, 6.2% |
| Pooled PPML-TWFE baseline | Transparency only | −4.3% | −10.4%, 2.2% |

The group-time and stacked-PPML samples reconcile to the same 40 treated stations, 120 control assignments, four cohorts, and 24-month event window. Their intervals overlap and their 6.0-point difference does not trigger the locked divergence rule.

PPML is nevertheless ineligible for the headline. Group-time cohort effects span 61.8 percentage points and PPML cohort effects span 33.3 points, both above the locked 20-point heterogeneity threshold. Two cohorts contain one treated corridor, so cohort-specific few-cluster inference is not reliable. The group-time estimate remains the headline by rule, not because it is more negative.

## Robustness and falsification

The radius estimates are tightly grouped: −10.7% for 200/600 m, −10.8% for 300/800 m, and −12.1% for 400/1,000 m treated/donut rules. The widest design uses a pre-declared 2:1 matching fallback because its local control support cannot sustain 3:1; that feasibility constraint was identified before its effect was read.

Starting the post-period at event month +1 or +2 produces −11.2% and −12.1%. The `new_protected`-only estimate is −8.6%. Member and casual estimates are −12.7% and −6.9%. Unmatched local and broad control points are −5.0% and −17.2%; they cross the five-point influence rule but do not replace the matched design.

Leave-one-corridor-out estimates remain negative from −15.0% to −5.8%. Omitting Halsted/Roosevelt/Van Buren changes the estimate by 5.1 points and is explicitly influential. No omission reverses the sign.

A fake first-post date six months early uses only actual pre-treatment event months −6 through −2. It produces +2.4% with a 95% interval from −5.1% to 10.0%, so it does not reproduce the main point estimate.

The geography placebo repeatedly draws 12 pseudo-corridors from official non-protected bike-route segments, preserves the real cohort distribution, repeats station and donut assignment, enforces complete observation windows, rematches controls, and re-estimates the ATT. Candidates are matched on length, projected location, nearby-station count, baseline ridership, and pre-period slope. Fifty fixed-seed valid replications have a median of +3.2% and a central 90% interval from −9.0% to 15.1%. The two-sided empirical tail probability for the real −10.8% estimate is 0.235, so the locked 0.10 tail criterion is not met.

## Interpretation boundary

The most defensible statement is: **the analysis does not establish an increase in monthly Divvy trip starts near the treated corridors.** It is also acceptable to say that the registered point estimates are negative and generally directionally stable.

It is not defensible to say that protected lanes reduced cycling, reduced Divvy use, or had no effect. The confidence interval includes meaningful negative effects, zero, and a small positive effect. Divvy starts are only one part of cycling behavior, and the design cannot eliminate unobserved corridor targeting, network spillovers, station relocations, or timing error.

## Reproducibility

The complete build is `make reproduce`. It rebuilds source audits, the station-month panel, control matching, identification diagnostics, estimators, robustness checks, fixed-seed placebos, final visual asset, and release tests. The two copied Project A Parquet inputs are intentionally excluded from Git; their repository-relative contract is documented in the README. All derived Parquet products are also ignored and recreated locally.

Machine-readable gate summaries and registries are stored under `reports/`. The final language contract is in `docs/claims_audit.md`.
