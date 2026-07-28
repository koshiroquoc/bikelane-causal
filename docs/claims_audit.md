# Final Claims Audit

**Decision:** `PASS` for portfolio release, conditional on the language below.

## Approved core claim

> The primary matched group-time estimate is −10.8% (95% CI −24.0% to 2.3%). The analysis does not establish an increase in nearby monthly Divvy trip starts, and identification and geography-placebo limitations preclude a clean causal claim.

## Language contract

| Safe wording | Wording to avoid | Reason |
|---|---|---|
| “The point estimate is negative.” | “The lanes reduced ridership.” | A negative estimate is not an identified causal decrease. |
| “The analysis does not establish an increase.” | “The lanes had no effect.” | Failure to establish an increase is not proof of a zero effect. |
| “Results are directionally stable across radius checks.” | “Every robustness check passed.” | Geography placebo misses the locked tail criterion; timing and controls are influential. |
| “Divvy trip starts near treated corridors.” | “Cycling in Chicago.” | Divvy starts do not measure all cycling, safety, access, or welfare. |
| “First verified usable month.” | “Exact opening date.” | All final treatment dates have medium confidence. |
| “Conditional causal design” or “causal-inference study.” | “Protected lanes caused…” | Phase 3 and Phase 5 both pass only with limitations. |

## Evidence that must accompany the headline

- 40 treated stations across 12 corridors, with four single-station corridors.
- Group-time ATT −10.8%, 95% CI −24.0% to 2.3%.
- Phase 3 placebo-lead test `F(4,11) = 4.41`, `p = 0.023`; largest lead −16.3%.
- Severe cohort heterogeneity disqualifies stacked PPML from headline status.
- Halsted/Roosevelt/Van Buren is influential in leave-one-corridor-out analysis.
- The fake-date placebo is clear, but the matched geography placebo has empirical `p = 0.235` and misses the locked 0.10 tail criterion.
- The outcome is monthly Divvy trip starts, not total cycling.

## Artifact audit

| Artifact | Status | Audit finding |
|---|---|---|
| `README.md` | PASS | Leads with effect and interval, states no increase is established, and immediately rejects a clean decrease claim. |
| `docs/research_memo.md` | PASS | Separates estimand, estimator, diagnostics, robustness, and interpretation boundary. |
| `reports/phase4_results.md` | PASS | Retains P3 lead warning and null-inclusive interval. |
| `reports/phase5_robustness.md` | PASS | Reports geography-placebo failure and influential specifications without selecting a favorable alternative. |
| Portfolio notes | PASS | Resume and interview language describe the workflow and uncertainty rather than claiming policy impact. |

## Interview answer in one sentence

“I built a spatial staggered-DiD pipeline around 12 Chicago protected-lane corridors; the headline estimate was −10.8% with a wide null-inclusive interval, and because pre-trends and geography placebos were imperfect, I presented it as no established increase rather than a causal decrease.”
