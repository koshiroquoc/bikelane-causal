# Portfolio Packaging

## GitHub metadata

**Repository description:** Spatial staggered-DiD study of Chicago protected bike lanes and monthly Divvy trip starts, with matched controls, pre-trend gates, and pipeline-level placebos.

**Suggested topics:** `causal-inference`, `difference-in-differences`, `geospatial-analysis`, `python`, `divvy`, `chicago`, `policy-evaluation`, `robustness-checks`, `portfolio-project`

## Resume bullets

- Built a reproducible geospatial staggered difference-in-differences pipeline linking 12 audited Chicago protected-lane corridors to 40 treated Divvy stations and 83 matched controls across a 36-month panel.
- Designed pre-treatment identification gates, two-way clustered group-time/PPML estimation, leave-one-corridor-out analysis, and 50 pipeline-level matched geography placebos; reported a −10.8% estimate with a null-inclusive interval and documented why it did not support a clean causal claim.

## 30-second project story

I wanted a policy question where the hard part was design rather than prediction. I built the treatment inventory from CDOT project records, converted corridor exposure into a station-month panel, matched controls using only pre-treatment behavior, and locked the estimator rules before reading the headline effect. The estimate was negative but uncertain. Instead of shopping for a nicer specification, I kept the pre-trend warning, influential corridor, and failed geography tail test in the final conclusion. The strongest portfolio signal is the auditability of the decision process.

## Interview walkthrough

1. **Question:** Did newly protected corridors change nearby monthly Divvy trip starts?
2. **Hardest data problem:** turning segment-level project records and imperfect completion dates into auditable corridor treatments.
3. **Design choice:** 300 m treatment radius, 300–800 m exclusion donut, and three pre-period-matched local controls per treated station.
4. **Identification gate:** pre-treatment behavior was usable but imperfect, so estimation proceeded only with limitations.
5. **Estimator discipline:** group-time ATT and stacked PPML were assigned roles before results; heterogeneity disqualified PPML from the headline.
6. **Result:** −10.8%, 95% CI −24.0% to 2.3%; no increase established.
7. **Stress test:** radius and leave-one-out directions were stable, fake timing was clear, but geography placebo missed its tail criterion.
8. **Lesson:** a credible DS project can finish with an inconclusive answer if the pipeline makes the uncertainty legible.

## Likely interview questions

**Why not use ordinary TWFE?**  
Treatment is staggered and effects are heterogeneous, so a single TWFE treatment coefficient can carry problematic implicit weights. TWFE is retained only as a transparent baseline.

**Why is PPML not the headline?**  
The registry required reconciled samples, convergence, and no severe cohort heterogeneity. The sample reconciled and the model converged, but heterogeneity exceeded the locked threshold and two cohorts had one corridor.

**Does the negative estimate mean the bike lanes hurt ridership?**  
No. The interval includes zero, pre-treatment leads reject exact zero, dates are uncertain, and the geography placebo does not clear its locked criterion.

**Why only 50 geography placebos?**  
The plan explicitly allowed reducing to 50 rather than dropping or weakening the pipeline-level test when compute bound. The seed, candidate screen, 138 attempted draws, and 50 accepted replications are recorded.

**What would you do next?**  
Collect station-location histories and better exact opening dates, expand independent treated corridors as new post-period data accrue, and add corridor-level bicycle counters or safety outcomes so the estimand is not limited to Divvy starts.
