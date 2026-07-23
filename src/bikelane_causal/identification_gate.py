"""Record the Phase 3B identification decision from frozen Phase 3A outputs."""

from __future__ import annotations

import json

import pandas as pd

from bikelane_causal.diagnostics import ROOT, _paths, _raw_config


def run_gate() -> dict:
    raw = _raw_config()
    paths = _paths()
    phase3 = raw["phase3"]
    summary = json.loads(paths["phase3a_summary"].read_text(encoding="utf-8"))
    leads_summary = json.loads(
        paths["phase3_pretrend_leads_summary"].read_text(encoding="utf-8")
    )
    comparison = pd.read_csv(paths["phase3_control_comparison"])
    corridor = pd.read_csv(paths["phase3_corridor_diagnostics"])
    matches = pd.read_csv(paths["phase3_matches"])
    matched = comparison[comparison.control_pool.eq("pre_period_matched")]
    overall_gap = summary["overall_pretrend_gap_pct_points_per_month"][
        "pre_period_matched"
    ]

    hard_failures = []
    if not summary["all_selected_windows_complete"]:
        hard_failures.append("at least one selected analysis window is incomplete")
    if not summary["unique_matches_within_cohort"]:
        hard_failures.append("a control is reused within a cohort")
    if abs(overall_gap) >= float(phase3["pretrend_fail_pct_points_per_month"]):
        hard_failures.append(
            "the treated-station-weighted matched pre-trend gap exceeds the locked failure threshold"
        )
    lead_joint_failure = (
        leads_summary["joint_f_pvalue"] < float(phase3["lead_joint_alpha"])
        and leads_summary["max_abs_lead_percent"]
        >= float(phase3["lead_materiality_percent"])
    )
    if lead_joint_failure:
        hard_failures.append(
            "pre-treatment placebo leads are jointly significant and materially large"
        )

    limitations = []
    warned_cohorts = matched[
        matched.pretrend_gap_pct_points_per_month.abs()
        >= float(phase3["pretrend_warning_pct_points_per_month"])
    ].first_post_month.astype(str).tolist()
    if warned_cohorts:
        limitations.append(
            "Cohort-level matched pre-trend warnings remain for: " + ", ".join(warned_cohorts)
        )
    balance_warned_cohorts = matched[
        matched.max_abs_smd >= float(phase3["balance_warning_abs_smd"])
    ].first_post_month.astype(str).tolist()
    if balance_warned_cohorts:
        limitations.append(
            "Matched pre-period covariate balance remains weak for cohort(s): "
            + ", ".join(balance_warned_cohorts)
        )
    if (
        leads_summary["joint_f_pvalue"] < 0.10
        or leads_summary["individually_warned_leads"]
    ) and not lead_joint_failure:
        limitations.append(
            "the four-bin pre-treatment placebo-lead test rejects exact zero; this is a material identification limitation"
        )
    warned_corridors = corridor.loc[
        corridor.corridor_pretrend_warning, "corridor_id"
    ].tolist()
    if warned_corridors:
        limitations.append(
            f"{len(warned_corridors)} corridor(s) exceed the corridor pre-trend warning threshold"
        )
    singleton_corridors = corridor.loc[corridor.singleton_corridor, "corridor_id"].tolist()
    if singleton_corridors:
        limitations.append(
            f"{len(singleton_corridors)} corridor(s) are represented by only one treated station"
        )
    medium_timing = corridor[~corridor.date_confidence.eq("high")].corridor_id.tolist()
    if medium_timing:
        limitations.append("all treatment dates are first-verified months with medium confidence")
    if corridor.multiple_exposure_stations.sum() > 0:
        limitations.append(
            f"{int(corridor.multiple_exposure_stations.sum())} treated stations have multiple corridor exposure"
        )

    if hard_failures:
        decision = "FAIL"
    elif limitations:
        decision = "PASS WITH LIMITATIONS"
    else:
        decision = "PASS"

    result = {
        "decision": decision,
        "primary_control_specification": "pre_period_matched",
        "matching_controls_per_treated": int(phase3["matching_controls_per_treated"]),
        "matched_control_rows": len(matches),
        "overall_matched_pretrend_gap_pct_points_per_month": overall_gap,
        "pretrend_lead_joint_pvalue": leads_summary["joint_f_pvalue"],
        "max_abs_pretrend_lead_percent": leads_summary["max_abs_lead_percent"],
        "lead_failure_materiality_percent": float(phase3["lead_materiality_percent"]),
        "lead_failure_joint_alpha": float(phase3["lead_joint_alpha"]),
        "hard_failures": hard_failures,
        "limitations": limitations,
        "warned_cohorts": warned_cohorts,
        "balance_warned_cohorts": balance_warned_cohorts,
        "warned_corridors": warned_corridors,
        "singleton_corridors": singleton_corridors,
        "phase4_authorized": decision != "FAIL",
        "claim_scope": (
            "causal, conditional on the locked diagnostics and explicitly limited timing/geographic scope"
            if decision != "FAIL"
            else "descriptive only"
        ),
    }
    limitation_lines = "\n".join(f"- {item}." for item in limitations) or "- None."
    failure_lines = "\n".join(f"- {item}." for item in hard_failures) or "- None."
    warned_lines = "\n".join(f"- `{item}`" for item in warned_corridors) or "- None."
    text = f"""# Phase 3B Identification Decision

**Exit-gate decision:** `{decision}`  
**Primary control specification:** pre-period matched cohort-local controls  
**Phase 4 causal estimation authorized:** {'yes' if result['phase4_authorized'] else 'no'}

## Locked design

For each treatment cohort, begin with never-treated controls that have all 12 pre and 12 post months. Restrict them to stations within 3 km of a corridor treated in that cohort and outside the 800 m exclusion zone around every candidate corridor. Match {phase3['matching_controls_per_treated']} unique controls to each treated station, without replacement within cohort, using only the 12 pre-treatment months: mean, slope, variability of `log(1 + total trips)`, and member-trip share.

The resulting {len(matches)} cohort-control assignments are frozen in `reports/phase3_control_matches.csv` (SHA-256 `{summary['matches_sha256']}`). Phase 4 must use this sample for the primary group-time ATT and staggered-robust PPML comparison. Broad and cohort-local pools remain sensitivity specifications only.

## Gate evidence

- Treated-station-weighted matched pre-trend gap: {overall_gap:.2f} percentage points per month.
- Locked failure threshold: {phase3['pretrend_fail_pct_points_per_month']:.2f} percentage points per month in absolute value.
- All selected cohort windows complete: {str(summary['all_selected_windows_complete']).lower()}.
- Unique matched controls within cohort: {str(summary['unique_matches_within_cohort']).lower()}.
- Matching used post-treatment outcomes: {str(summary['matching_uses_post_treatment_outcomes']).lower()}.
- Four-bin pre-treatment lead diagnostic: F({leads_summary['joint_f_df_num']}, {leads_summary['joint_f_df_den']}) = {leads_summary['joint_f_statistic']:.2f}, p = {leads_summary['joint_f_pvalue']:.3f}.
- Largest absolute placebo lead: {leads_summary['max_abs_lead_percent']:.1f}%.
- Lead inference clusters: {leads_summary['corridor_clusters']} treated corridors and {leads_summary['control_station_clusters']} control stations.
- Locked lead failure rule: joint `p < {phase3['lead_joint_alpha']:.2f}` and at least one absolute lead of {phase3['lead_materiality_percent']:.0f}% or more. The joint test triggers, but the largest lead remains below that materiality threshold; it is therefore a limitation rather than an automatic failure.

![Pre-treatment placebo leads](figures/phase3_pretrend_leads.png)

### Hard failures

{failure_lines}

### Limitations carried into Phase 4 and the final claim

{limitation_lines}

### Corridor pre-trend warnings

{warned_lines}

## Interpretation

`{decision}` means the locked matched design may proceed to Phase 4, but the evidence is not equivalent to proof of parallel trends. Timing uncertainty, sparse corridors, multiple exposure, and flagged corridor heterogeneity must remain visible in the main tables and sensitivity analysis. No corridor may be removed because its post-treatment estimate is inconvenient; any leave-one-corridor-out results belong in Phase 5.
"""
    paths["phase3_gate_report"].write_text(text, encoding="utf-8")
    paths["phase3_gate_summary"].write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return result


if __name__ == "__main__":
    run_gate()
