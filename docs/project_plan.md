# Project B — Execution Plan and Milestone Control

**Working question:** Do newly protected bike-lane corridors change monthly Divvy trip starts at nearby stations?

**Plan version:** 0.5 (v0.4 records the completed Phase 1 audit; v0.5 records the configured, tested Phase 2 panel build and its `PASS` decision)  
**Plan date:** 2026-07-21  
**Expected remaining effort:** approximately 32–48 focused hours over 3–4 weeks.  
**Current phase:** Phase 3 — Identification diagnostics and control design.

## Status legend

- `[x]` complete and verified
- `[~]` in progress or awaiting sync/review
- `[ ]` not started
- `[!]` blocked or gate failed

No phase advances until its exit gate is explicitly recorded as `PASS`, `PASS WITH LIMITATIONS`, or `FAIL`.

---

## Phase 0 — Project lock and source inventory

**Purpose:** create an independent project, preserve Project A as read-only, and lock the research question before inspecting treatment effects.

**Estimated effort:** 2–4 hours  
**Status:** complete — `PASS` recorded 2026-07-20

### Milestones

- [x] **M0.1 — Independent repository:** `bikelane-causal` exists as a separate Git repository.
- [x] **M0.2 — Project A input contract:** `station_master.parquet` and `station_month_panel.parquet` copied and checksum-verified.
- [x] **M0.3 — Research brief:** question, estimand, unit definitions, claims policy, and initial gates documented.
- [x] **M0.4 — Official candidate universe:** 2024 CDOT tracker extracted to `data/reference/cdot_candidates_2024.csv` and synced to the GitHub repository.

### Exit gate P0

Pass when M0.1–M0.4 are complete and the GitHub repository contains no ignored parquet inputs.

**Recorded decision:** `PASS` on 2026-07-20.

---

## Phase 1 — Feasibility and treatment audit

**Purpose:** determine whether Chicago data can support a defensible causal study before building analysis infrastructure.

**Estimated effort:** 12–18 hours  
**Target duration:** 4–6 focused days

### Milestones

- [x] **M1.0 — Extend candidate universe to 2025 installations**
  - The preferred completion window (2024-07 through 2025-07) extends well into 2025, but the candidate universe from M0.4 covers only the 2024 CDOT tracker.
  - Extract 2025 protected-lane installations from the CDOT planned-projects tracker and Complete Streets updates into `data/reference/cdot_candidates_2025.csv`, same schema and snapshot conventions as the 2024 file.
  - This is the sanctioned way to grow the treated sample: expanding the candidate *universe* by a pre-stated criterion (completion window), before any outcome effects are examined. It is distinct from the prohibited rescues in the change-control rules (tuning radii or lane types after seeing results).

- [x] **M1.1 — Consolidate segments into corridors**
  - Group adjacent CDOT segments installed as one project.
  - Keep geographically separate phases as separate corridors.
  - Produce `data/reference/corridor_candidates.csv` with one row per independent corridor.

- [x] **M1.2 — Lock treatment definition**
  - Primary proposed treatment: the first month a corridor gains physical bike-lane protection.
  - Track `new_protected` and `protection_upgrade` separately.
  - Pre-specify a robustness result using `new_protected` corridors only.
  - Record the final definition in `docs/research_brief.md` before examining outcome effects.

- [x] **M1.3 — Audit completion month and provenance**
  - Audit every candidate corridor for an opening/usable month; leave the month empty and exclude the corridor when the available evidence cannot support one rather than imputing a date.
  - Store primary URL, corroborating URL, confidence grade, and ambiguity notes.
  - Exclude low-confidence timing from the primary sample.
  - Result: 17 medium-confidence dated corridors, one dated fallback corridor, and 29 provenance-pending corridors explicitly excluded from the primary sample.

- [x] **M1.4 — Build preliminary corridor geometry and station assignment**
  - Match corridor limits to official geometry.
  - Compute station distance in a meter-based CRS.
  - Count treated stations, donut exclusions, controls, and stations per corridor.

- [x] **M1.5 — Audit station integrity and observation windows**
  - Inspect station openings, closures, relocations, ID changes, and internal missing months.
  - Compute pre/post months for each corridor-station pair.
  - Do not automatically label missing station-months as zero.

- [x] **M1.6 — Design-size and power audit**
  - Count independent treated corridors, not only stations.
  - Measure corridor concentration and usable treated station-months.
  - Estimate a rough minimum detectable effect using the observed panel structure.

### Exit gate P1 — Go/no-go

The preferred design passes when:

1. At least 8 independent treated corridors have high- or medium-confidence completion months.
2. At least 20 stable treated stations remain across those corridors as a planning heuristic.
3. Most primary corridors have at least 12 pre and 12 post months; 9/9 is allowed only as `PASS WITH LIMITATIONS`.
4. No single corridor contains more than roughly 30% of treated stations.
5. Geometry and station assignment pass visual spot checks.
6. The minimum detectable effect is not so large that only implausible effects could be detected.

### P1 deliverables

- `data/reference/corridor_candidates.csv`
- updated `data/reference/treatment_inventory.csv`
- preliminary treatment/control map
- `reports/feasibility_report.md`
- recorded decision: `PASS`, `PASS WITH LIMITATIONS`, or `FAIL`

**Recorded decision (2026-07-20): `PASS WITH LIMITATIONS`.** Twelve independent corridors and 40 stable treated stations are usable under the locked 300 m assignment rule; the largest corridor holds 27.5% of stable treated stations and the planning MDE is approximately 14–20%. Limitations requiring explicit Phase 2–5 handling are conservative first-verified timing for nine corridors, three multiple-exposure stations with different completion months, lack of monthly station coordinates, and one one-station corridor with a conspicuous preliminary pre-trend gap. See `reports/feasibility_report.md`.

If P1 fails, stop full causal development and choose one of three documented alternatives: narrow the claim, switch to a descriptive spatial study, or abandon Project B.

**Fallback-city decision (recorded 2026-07-20):** a fourth option — rerunning the parameterized Project A ingestion for another city with better treatment data (e.g. NYC Citi Bike, where DOT publishes bike-lane installations with dates) — was considered and deliberately deferred. Reasons: it restarts treatment provenance and panel auditing from zero in an unfamiliar data environment, roughly doubles the remaining time budget, and invites scope creep mid-project. It is *not* on the menu of P1-failure responses. It may only be revisited as a full project pivot, decided fresh and re-planned from Phase 0, never as a mid-project rescue after seeing Chicago results.

---

## Phase 2 — Reproducible analysis dataset

**Purpose:** create one audited station-month panel that every estimator will use.

**Estimated effort:** 10–14 hours  
**Target duration:** 4–5 focused days

### Milestones

- [x] **M2.1 — Minimal Python environment and config**
  - Add only dependencies needed for spatial work, tables, estimation, plots, and tests.
  - Put radii, minimum pre/post periods, and input paths in config.

- [x] **M2.2 — Spatial assignment pipeline**
  - Create treated, donut-excluded, and candidate-control groups.
  - Support multiple nearby corridors and earliest valid treatment month.

- [x] **M2.3 — Station-month panel builder**
  - Join outcome data, station attributes, corridor assignment, treatment timing, and event time.
  - Implement the documented missing-month policy.

- [x] **M2.4 — Data tests and audit report**
  - No duplicate station-months.
  - Treatment is monotonic after activation.
  - Event time is correct at boundaries.
  - Distance units are meters.
  - Donut observations cannot enter treatment or control.

### Exit gate P2

Pass when the full analysis panel is reproduced by one command, all critical tests pass, and row/station/corridor counts reconcile with the feasibility report.

**Recorded decision (2026-07-21): `PASS`.** `make phase2` rebuilds the source audit, spatial assignment, cohort-specific control eligibility, and 33,018-row station-month panel before running nine critical tests. The build contains 40 primary treated and 1,599 candidate-control stations across all 36 source months; no duplicate keys, negative outcomes, or imputed missing months were found. See `reports/data_quality_report.md`.

### P2 deliverables

- `data/derived/station_month_analysis.parquet`
- station assignment table
- data-quality report
- test suite and reproducible build command

---

## Phase 3 — Identification diagnostics and control design

**Purpose:** decide whether a causal interpretation is defensible before reading a headline ATT.

**Estimated effort:** 8–12 hours  
**Target duration:** 3–5 focused days

### Milestones

- [ ] **M3.1 — Raw trends:** plot treated and candidate controls by calendar month and cohort.
- [ ] **M3.2 — Raw event-time view:** inspect outcome differences before regression.
- [ ] **M3.3 — Control strategy:** compare broad, local, and pre-trend-compatible control pools.
- [ ] **M3.4 — Pre-treatment diagnostics:** inspect leads, composition changes, station churn, and corridor-specific anomalies.
- [ ] **M3.5 — Identification decision:** lock the primary control group and state whether the final claim may be causal or must remain descriptive.

### Exit gate P3

- `PASS`: pre-period behavior and composition support the chosen design.
- `PASS WITH LIMITATIONS`: diagnostics are imperfect but interpretable with a narrower claim.
- `FAIL`: strong differential pre-trends or composition changes remain after reasonable design corrections.

### P3 deliverables

- treatment/control map
- raw calendar-time plot
- raw event-time plot
- pre-trend diagnostic note
- locked primary control specification

---

## Phase 4 — Main estimation

**Purpose:** estimate the pre-specified treatment effect with uncertainty appropriate to staggered corridor-level treatment.

**Estimated effort:** 8–12 hours  
**Target duration:** 3–5 focused days

### Milestones

- [ ] **M4.1 — Simple baselines:** TWFE-OLS and pooled PPML-TWFE with a single treatment dummy, as transparent reference estimates only — never headline candidates.
- [ ] **M4.2 — Group-time ATT:** primary estimator for causal identification, dynamics, and cohort heterogeneity under staggered adoption; its pre-treatment coefficients inform the P3 decision together with the full diagnostic set, per the division of labor locked in the research brief.
- [ ] **M4.3 — Event study:** dynamic effects and pre-treatment coefficients.
- [ ] **M4.4 — Staggered-robust PPML:** develop a cohort-stacked or event-time-saturated PPML specification as the candidate for the headline percentage magnitude (`exp(β) − 1`). It is promoted to headline only under the conditions locked in the research brief (P3 pass, reconciled sample, no severe cohort heterogeneity, staggered-robust specification); otherwise the headline comes from M4.2 translated to the percentage scale. The pre-specified divergence protocol applies whenever M4.2 and M4.4 disagree materially.
- [ ] **M4.5 — Inference:** corridor-clustered uncertainty and few-cluster correction where supported.
- [ ] **M4.6 — Results registry:** every planned specification reported on the same audited sample with effect size and confidence interval.

### Exit gate P4

Pass when all pre-specified estimators run on reconciled samples, results are expressed on clearly labeled scales, and no estimator is selected solely because it gives a favorable answer.

### P4 deliverables

- main results table
- primary event-study figure
- estimator/sample reconciliation table
- one-paragraph interpretation matched to the P3 identification decision

---

## Phase 5 — Robustness and falsification

**Purpose:** test whether the conclusion depends on one radius, corridor, control definition, or implementation artifact.

**Estimated effort:** 10–14 hours  
**Target duration:** 3–5 focused days

### Required milestones

- [ ] **M5.1 — Radius sensitivity:** pre-specified inner/donut combinations.
- [ ] **M5.2 — Control sensitivity:** local versus broader eligible controls.
- [ ] **M5.3 — Leave-one-corridor-out:** identify influential corridors.
- [ ] **M5.4 — Construction-window sensitivity:** exclude transition months around completion.
- [ ] **M5.5 — Treatment variant:** new protected lanes only versus all newly physically protected corridors.
- [ ] **M5.6 — Outcome heterogeneity:** member versus casual trips.
- [ ] **M5.7 — Timing placebo:** verify that a fake pre-treatment date does not reproduce the main effect.
- [ ] **M5.8 — Geography placebo (matched pseudo-corridors, pipeline-level null distribution):** build a pool of pseudo-corridors from streets with no protected lane, **matched to the real treatment corridors** on corridor length, geographic area, nearby-station count, and baseline ridership/pre-period trend, and screened to exclude streets with concurrent transport projects or lying near a real treatment corridor. Each replication draws the same number of pseudo-corridors as real corridors and assigns install months preserving the real cohort distribution, then reruns the full assignment-to-estimate pipeline; 100–200 replications build the null ATT distribution, and the real estimate should sit in its tail. Matching is what gives the null distribution meaning — unmatched random streets (different density, ridership, geography) would produce an artificially easy null. This tests the entire pipeline, not just the model, and presupposes the one-command build from P2. If compute or time binds, reduce replications (e.g. to 50) rather than dropping the milestone or weakening the matching.

### Exit gate P5

Pass does not require every coefficient to be significant. It requires the reported conclusion to remain honest under the observed sensitivity pattern and to name any corridor/specification that materially changes it.

### P5 deliverables

- robustness table
- radius-sensitivity figure
- leave-one-corridor-out figure
- geography-placebo null-distribution figure
- falsification summary

---

## Phase 6 — Report and portfolio release

**Purpose:** turn the analysis into a concise, reproducible DS portfolio project.

**Estimated effort:** 6–10 hours  
**Target duration:** 3–4 focused days

### Milestones

- [ ] **M6.1 — Executive README:** question, estimand, design, map, main result, uncertainty, and limitations.
- [ ] **M6.2 — Research memo:** methods and diagnostics in enough detail for technical review.
- [ ] **M6.3 — Reproducibility:** documented setup and one-command analysis path.
- [ ] **M6.4 — Visual QA:** every figure has units, sample definition, uncertainty, and readable labels.
- [ ] **M6.5 — Claims audit:** every causal sentence is consistent with the P3 decision and robustness evidence.
- [ ] **M6.6 — Portfolio packaging:** repository topics, short project description, resume bullets, and interview narrative.

### Exit gate P6 / Definition of Done

- Fresh setup reproduces the primary table and figures.
- GitHub repository contains no private/local data or machine-specific paths.
- README communicates the project in roughly 90 seconds.
- Limitations include Divvy-versus-total-cycling scope, treatment targeting, spillovers, station churn, timing uncertainty, and few-corridor inference.
- Final tag: `v1.0.0`.

---

## Suggested release checkpoints

| Release | Meaning | Required gate |
|---|---|---|
| `v0.1-feasibility` | Treatment inventory and go/no-go report | P1 |
| `v0.2-panel` | Reproducible audited analysis panel | P2 |
| `v0.3-design` | Control and identification decision locked | P3 |
| `v0.4-results` | Main estimates and event study | P4 |
| `v0.5-robustness` | Robustness/falsification complete | P5 |
| `v1.0.0` | Public portfolio release | P6 |

## Change-control rules

1. Do not add or remove corridors after seeing outcome effects without documenting the reason and rerunning the full specification set.
2. Do not tune distance radii for statistical significance.
3. Keep primary and robustness specifications labeled before estimation.
4. Record every gate decision and limitation in the repository.
5. A null result, negative result, or failed causal gate is a valid final project outcome.

## Immediate next action

Begin M2.1: convert the Phase 1 audit script into the configured one-command data build, lock dependencies, and add critical data tests before constructing the analysis panel.
