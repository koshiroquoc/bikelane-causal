"""Pre-treatment-only group-time placebo leads for the Phase 3B gate."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from bikelane_causal.diagnostics import PRE_EVENT_TIMES, ROOT, _paths
from bikelane_causal.pipeline import load_config


REFERENCE_EVENT = -2
LEAD_EVENTS = tuple(event for event in PRE_EVENT_TIMES if event != REFERENCE_EVENT)
JOINT_TEST_BINS = {
    "-13:-11": (-13, -12, -11),
    "-10:-8": (-10, -9, -8),
    "-7:-5": (-7, -6, -5),
    "-4:-3": (-4, -3),
}


def _month(cohort: str, event_time: int) -> str:
    return str(pd.Period(cohort, freq="M") + event_time)


def _one_way_cluster_covariance(
    residual: np.ndarray, groups: pd.Series
) -> np.ndarray:
    unique_groups = sorted(set(groups))
    cluster_sums = np.vstack(
        [residual[groups.to_numpy() == group].sum(axis=0) for group in unique_groups]
    )
    n = len(residual)
    g = len(cluster_sums)
    correction = g / (g - 1) if g > 1 else 1.0
    return correction * (cluster_sums.T @ cluster_sums) / (n**2)


def _cluster_covariance(scores: pd.DataFrame, events: list) -> np.ndarray:
    wide = scores.pivot(
        index=["treated_station_id", "corridor_id", "control_station_id"],
        columns="event_time",
        values="score_log_points",
    ).reindex(columns=events)
    beta = wide.mean(axis=0).to_numpy()
    residual = wide.to_numpy() - beta
    corridor = pd.Series(wide.index.get_level_values("corridor_id"), dtype=str)
    control = pd.Series(wide.index.get_level_values("control_station_id"), dtype=str)
    intersection = corridor + "::" + control
    covariance = (
        _one_way_cluster_covariance(residual, corridor)
        + _one_way_cluster_covariance(residual, control)
        - _one_way_cluster_covariance(residual, intersection)
    )
    # Numerical noise in multiway subtraction can create tiny negative diagonal
    # values. Preserve the covariance structure while clipping only that noise.
    diagonal = np.maximum(np.diag(covariance), 0)
    covariance[np.diag_indices_from(covariance)] = diagonal
    return covariance


def _plot(leads: pd.DataFrame, path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.errorbar(
        leads.event_time,
        leads.effect_percent,
        yerr=[
            leads.effect_percent - leads.ci_low_percent,
            leads.ci_high_percent - leads.effect_percent,
        ],
        fmt="o-",
        color="#2563eb",
        ecolor="#93c5fd",
        capsize=3,
        linewidth=1.8,
    )
    ax.scatter([REFERENCE_EVENT], [0], color="#111827", marker="s", zorder=4)
    ax.axhline(0, color="#111827", linewidth=1)
    ax.axvline(-1, color="#f59e0b", linestyle="--", linewidth=1)
    ax.set_xticks(list(LEAD_EVENTS) + [REFERENCE_EVENT])
    ax.set_xlabel("Pre-treatment event month (−2 is the reference)")
    ax.set_ylabel("Placebo group-time difference (%)")
    ax.set_title("Phase 3B pre-treatment placebo leads")
    ax.grid(alpha=0.18)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight", metadata={"Software": "bikelane-causal"})
    plt.close(fig)


def run_pretrend_leads() -> dict:
    config = load_config()
    paths = _paths()
    panel = pd.read_parquet(config.paths["analysis_panel"])
    assignment = pd.read_parquet(config.paths["station_assignment"])
    matches = pd.read_csv(paths["phase3_matches"], dtype={"first_post_month": str})
    treated_assignment = assignment[
        assignment.analysis_role.eq("primary_treated")
    ].set_index("station_id")
    log_panel = panel.assign(log1p_trips=np.log1p(panel.total_trips)).pivot(
        index="station_id", columns="month", values="log1p_trips"
    )

    score_rows = []
    for cohort, cohort_matches in matches.groupby("first_post_month"):
        treated_ids = sorted(cohort_matches.treated_station_id.unique())
        reference_month = _month(cohort, REFERENCE_EVENT)
        for event_time in LEAD_EVENTS:
            event_month = _month(cohort, event_time)
            treated_delta = (
                log_panel.loc[treated_ids, event_month]
                - log_panel.loc[treated_ids, reference_month]
            )
            control_ids = sorted(cohort_matches.control_station_id.unique())
            control_delta = (
                log_panel.loc[control_ids, event_month]
                - log_panel.loc[control_ids, reference_month]
            )
            mapped = cohort_matches.assign(
                treated_delta=cohort_matches.treated_station_id.map(treated_delta),
                control_delta=cohort_matches.control_station_id.map(control_delta),
            )
            mapped["score_log_points"] = mapped.treated_delta - mapped.control_delta
            for row in mapped.itertuples(index=False):
                score_rows.append(
                    {
                        "first_post_month": cohort,
                        "event_time": event_time,
                        "treated_station_id": row.treated_station_id,
                        "corridor_id": treated_assignment.loc[
                            row.treated_station_id, "assigned_primary_corridor"
                        ],
                        "control_station_id": row.control_station_id,
                        "score_log_points": float(row.score_log_points),
                    }
                )
    scores = pd.DataFrame(score_rows)
    events = list(LEAD_EVENTS)
    covariance = _cluster_covariance(scores, events)
    beta = scores.groupby("event_time").score_log_points.mean().reindex(events).to_numpy()
    se = np.sqrt(np.diag(covariance))
    corridors = scores.corridor_id.nunique()
    critical = stats.t.ppf(0.975, df=corridors - 1)
    lead_rows = []
    for index, event_time in enumerate(events):
        low = beta[index] - critical * se[index]
        high = beta[index] + critical * se[index]
        lead_rows.append(
            {
                "event_time": event_time,
                "reference_event_time": REFERENCE_EVENT,
                "estimate_log_points": beta[index],
                "cluster_se_log_points": se[index],
                "effect_percent": 100 * np.expm1(beta[index]),
                "ci_low_percent": 100 * np.expm1(low),
                "ci_high_percent": 100 * np.expm1(high),
                "treated_stations": scores[
                    scores.event_time.eq(event_time)
                ].treated_station_id.nunique(),
                "corridor_clusters": corridors,
            }
        )
    leads = pd.DataFrame(lead_rows)
    event_to_bin = {
        event: label for label, members in JOINT_TEST_BINS.items() for event in members
    }
    binned_scores = scores.assign(joint_bin=scores.event_time.map(event_to_bin)).groupby(
        ["treated_station_id", "corridor_id", "control_station_id", "joint_bin"],
        as_index=False,
    ).score_log_points.mean()
    binned_scores = binned_scores.rename(columns={"joint_bin": "event_time"})
    bins = list(JOINT_TEST_BINS)
    binned_covariance = _cluster_covariance(binned_scores, bins)
    binned_beta = (
        binned_scores.groupby("event_time").score_log_points.mean().reindex(bins).to_numpy()
    )
    joint_wald = float(binned_beta.T @ np.linalg.pinv(binned_covariance) @ binned_beta)
    joint_df_num = len(bins)
    joint_df_den = corridors - 1
    joint_f = joint_wald / joint_df_num
    joint_pvalue = float(stats.f.sf(joint_f, joint_df_num, joint_df_den))
    individual_warning = (
        (leads.effect_percent.abs() >= 10)
        & ((leads.ci_low_percent > 0) | (leads.ci_high_percent < 0))
    )
    summary = {
        "diagnostic": "pre-treatment-only matched-panel group-time placebo leads",
        "post_treatment_outcomes_used": False,
        "reference_event_time": REFERENCE_EVENT,
        "lead_event_times": events,
        "treated_stations": int(scores.treated_station_id.nunique()),
        "corridor_clusters": corridors,
        "control_station_clusters": int(scores.control_station_id.nunique()),
        "joint_test_bins": {label: list(members) for label, members in JOINT_TEST_BINS.items()},
        "joint_f_statistic": joint_f,
        "joint_f_df_num": joint_df_num,
        "joint_f_df_den": joint_df_den,
        "joint_f_pvalue": joint_pvalue,
        "max_abs_lead_percent": float(leads.effect_percent.abs().max()),
        "individually_warned_leads": leads.loc[individual_warning, "event_time"].tolist(),
        "inference_note": "Two-way clustered by treated corridor and control station; t reference uses 11 corridor degrees of freedom. Four-bin joint F test used because 11 separate leads are too many for 12 corridors.",
    }
    leads.to_csv(paths["phase3_pretrend_leads"], index=False, float_format="%.6f")
    paths["phase3_pretrend_leads_summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    _plot(leads, ROOT / "reports" / "figures" / "phase3_pretrend_leads.png")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    run_pretrend_leads()
