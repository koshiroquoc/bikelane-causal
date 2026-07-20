# Project B — Execution Plan and Milestone Control

**Working question:** Do newly protected bike-lane corridors change monthly Divvy trip starts at nearby stations?

**Plan version:** 0.1  
**Plan date:** 2026-07-20  
**Expected remaining effort:** approximately 50–70 focused hours over 4–5 weeks.  
**Current phase:** Phase 1 — Feasibility and treatment audit.

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
**Status:** nearly complete

### Milestones

- [x] **M0.1 — Independent repository:** `bikelane-causal` exists as a separate Git repository.
- [x] **M0.2 — Project A input contract:** `station_master.parquet` and `station_month_panel.parquet` copied and checksum-verified.
- [x] **M0.3 — Research brief:** question, estimand, unit definitions, claims policy, and initial gates documented.
- [~] **M0.4 — Official candidate universe:** 2024 CDOT tracker extracted to `data/reference/cdot_candidates_2024.csv` and synced to the GitHub repository.

### Exit gate P0

Pass when M0.1–M0.4 are complete and the GitHub repository contains no ignored parquet inputs.

**Expected decision:** `PASS` after the candidate CSV is synced and verified.

---

## Phase 1 — Feasibility and treatment audit

**Purpose:** determine whether Chicago data can support a defensible causal study before building analysis infrastructure.

**Estimated effort:** 12–18 hours  
**Target duration:** 4–6 focused days

### Milestones

- [ ] **M1.1 — Consolidate segments into corridors**
  - Group adjacent CDOT segments installed as one project.
  - Keep geographically separate phases as separate corridors.
  - Produce `data/reference/corridor_candidates.csv` with one row per independent corridor.

- [ ] **M1.2 — Lock treatment definition**
  - Primary proposed treatment: the first month a corridor gains physical bike-lane protection.
  - Track `new_protected` and `protection_upgrade` separately.
  - Pre-specify a robustness result using `new_protected` corridors only.
  - Record the final definition in `docs/research_brief.md` before examining outcome effects.

- [ ] **M1.3 — Audit completion month and provenance**
  - Find an opening/usable month for every candidate corridor.
  - Store primary URL, corroborating URL, confidence grade, and ambiguity notes.
  - Exclude low-confidence timing from the primary sample.

- [ ] **M1.4 — Build preliminary corridor geometry and station assignment**
  - Match corridor limits to official geometry.
  - Compute station distance in a meter-based CRS.
  - Count treated stations, donut exclusions, controls, and stations per corridor.

- [ ] **M1.5 — Audit station integrity and observation windows**
  - Inspect station openings, closures, relocations, ID changes, and internal missing months.
  - Compute pre/post months for each corridor-station pair.
  - Do not automatically label missing station-months as zero.

- [ ] **M1.6 — Design-size and power audit**
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

If P1 fails, stop full causal development and choose one of three documented alternatives: narrow the claim, switch to a descriptive spatial study, or abandon Project B.

---

## Phase 2 — Reproducible analysis dataset

**Purpose:** create one audited station-month panel that every estimator will use.

**Estimated effort:** 10–14 hours  
**Target duration:** 4–5 focused days

### Milestones

- [ ] **M2.1 — Minimal Python environment and config**
  - Add only dependencies needed for spatial work, tables, estimation, plots, and tests.
  - Put radii, minimum pre/post periods, and input paths in config.

- [ ] **M2.2 — Spatial assignment pipeline**
  - Create treated, donut-excluded, and candidate-control groups.
  - Support multiple nearby corridors and earliest valid treatment month.

- [ ] **M2.3 — Station-month panel builder**
  - Join outcome data, station attributes, corridor assignment, treatment timing, and event time.
  - Implement the documented missing-month policy.

- [ ] **M2.4 — Data tests and audit report**
  - No duplicate station-months.
  - Treatment is monotonic after activation.
  - Event time is correct at boundaries.
  - Distance units are meters.
  - Donut observations cannot enter treatment or control.

### Exit gate P2

Pass when the full analysis panel is reproduced by one command, all critical tests pass, and row/station/corridor counts reconcile with the feasibility report.

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

- [ ] **M4.1 — Simple baseline DiD:** transparent reference estimate.
- [ ] **M4.2 — Primary group-time ATT:** estimator aligned with staggered adoption.
- [ ] **M4.3 — Event study:** dynamic effects and pre-treatment coefficients.
- [ ] **M4.4 — Count-data specification:** PPML as a complementary specification, not automatic ground truth.
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

**Estimated effort:** 8–12 hours  
**Target duration:** 3–5 focused days

### Required milestones

- [ ] **M5.1 — Radius sensitivity:** pre-specified inner/donut combinations.
- [ ] **M5.2 — Control sensitivity:** local versus broader eligible controls.
- [ ] **M5.3 — Leave-one-corridor-out:** identify influential corridors.
- [ ] **M5.4 — Construction-window sensitivity:** exclude transition months around completion.
- [ ] **M5.5 — Treatment variant:** new protected lanes only versus all newly physically protected corridors.
- [ ] **M5.6 — Outcome heterogeneity:** member versus casual trips.
- [ ] **M5.7 — Timing placebo:** verify that a fake pre-treatment date does not reproduce the main effect.

### Exit gate P5

Pass does not require every coefficient to be significant. It requires the reported conclusion to remain honest under the observed sensitivity pattern and to name any corridor/specification that materially changes it.

### P5 deliverables

- robustness table
- radius-sensitivity figure
- leave-one-corridor-out figure
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

Complete M0.4, then begin M1.1 by consolidating the 37 official 2024 CDOT segments into independent corridor candidates.
