"""Phase 3A diagnostics using treatment-blind control selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import linear_sum_assignment

from bikelane_causal.pipeline import ROOT, load_config


EVENT_TIMES = tuple(list(range(-13, -1)) + list(range(0, 12)))
PRE_EVENT_TIMES = tuple(range(-13, -1))
POST_EVENT_TIMES = tuple(range(0, 12))
POOL_ORDER = ("treated", "broad", "cohort_local", "pre_period_matched")
POOL_LABELS = {
    "treated": "Treated",
    "broad": "Broad controls",
    "cohort_local": "Cohort-local controls",
    "pre_period_matched": "Pre-period matched controls",
}
COLORS = {
    "treated": "#111827",
    "broad": "#9ca3af",
    "cohort_local": "#2563eb",
    "pre_period_matched": "#e11d48",
}


def _raw_config() -> dict[str, Any]:
    return json.loads((ROOT / "config" / "analysis.json").read_text(encoding="utf-8"))


def _paths() -> dict[str, Path]:
    return {key: ROOT / value for key, value in _raw_config()["paths"].items()}


def _event_months(first_post_month: str) -> dict[int, str]:
    first_post = pd.Period(first_post_month, freq="M")
    return {event: str(first_post + event) for event in EVENT_TIMES}


def _station_features(
    panel: pd.DataFrame, station_ids: list[str], first_post_month: str
) -> pd.DataFrame:
    months = _event_months(first_post_month)
    pre_months = [months[event] for event in PRE_EVENT_TIMES]
    subset = panel[
        panel.station_id.isin(station_ids) & panel.month.astype(str).isin(pre_months)
    ].copy()
    subset["log1p_trips"] = np.log1p(subset.total_trips)
    pivot = subset.pivot(index="station_id", columns="month", values="log1p_trips")
    pivot = pivot.reindex(index=station_ids, columns=pre_months)
    if pivot.isna().any().any():
        missing = pivot.index[pivot.isna().any(axis=1)].tolist()
        raise ValueError(f"Incomplete pre-period feature rows: {missing[:5]}")

    x = np.arange(len(pre_months), dtype=float)
    slopes = np.polyfit(x, pivot.to_numpy().T, 1)[0]
    totals = subset.groupby("station_id")[["member_trips", "total_trips"]].sum()
    member_share = totals.member_trips.div(totals.total_trips.replace(0, np.nan)).fillna(0)
    return pd.DataFrame(
        {
            "station_id": pivot.index,
            "pre_mean_log1p": pivot.mean(axis=1).to_numpy(),
            "pre_slope_log1p": slopes,
            "pre_sd_log1p": pivot.std(axis=1, ddof=0).to_numpy(),
            "pre_member_share": member_share.reindex(pivot.index).to_numpy(),
        }
    )


def _cohort_local_controls(
    assignment: pd.DataFrame,
    eligible: pd.DataFrame,
    cohort: str,
    project_crs: str,
    local_outer_m: float,
) -> pd.DataFrame:
    treated_corridors = assignment.loc[
        assignment.analysis_role.eq("primary_treated")
        & assignment.first_post_month.eq(cohort),
        "assigned_primary_corridor",
    ].unique()
    geometry = gpd.read_file(ROOT / "data" / "reference" / "corridor_candidates.geojson")
    geometry = geometry[geometry.corridor_id.isin(treated_corridors)].to_crs(project_crs)
    if len(geometry) != len(treated_corridors):
        raise ValueError(f"Missing cohort corridor geometry for {cohort}")

    eligible_ids = set(
        eligible.loc[
            eligible.first_post_month.eq(cohort) & eligible.eligible_12_pre_12_post,
            "station_id",
        ]
    )
    controls = assignment[
        assignment.analysis_role.eq("control_candidate")
        & assignment.station_id.isin(eligible_ids)
    ].copy()
    points = gpd.GeoDataFrame(
        controls,
        geometry=gpd.points_from_xy(controls.lng, controls.lat),
        crs="EPSG:4326",
    ).to_crs(project_crs)
    distances = np.min(
        np.vstack([points.geometry.distance(line).to_numpy() for line in geometry.geometry]),
        axis=0,
    )
    controls["cohort_local_distance_m"] = distances
    return controls[controls.cohort_local_distance_m.le(local_outer_m)].copy()


def _match_controls(
    treated_features: pd.DataFrame,
    control_features: pd.DataFrame,
    feature_names: list[str],
    ratio: int,
) -> pd.DataFrame:
    if len(control_features) < ratio * len(treated_features):
        raise ValueError("Not enough cohort-local controls for requested matching ratio")
    combined = pd.concat(
        [treated_features[feature_names], control_features[feature_names]],
        ignore_index=True,
    )
    scale = combined.std(ddof=0).replace(0, 1.0)
    center = combined.mean()
    treated_z = (treated_features[feature_names] - center) / scale
    controls_z = (control_features[feature_names] - center) / scale
    cost = np.sqrt(
        ((treated_z.to_numpy()[:, None, :] - controls_z.to_numpy()[None, :, :]) ** 2).sum(axis=2)
    )
    expanded_cost = np.repeat(cost, ratio, axis=0)
    rows, cols = linear_sum_assignment(expanded_cost)
    matches = pd.DataFrame(
        {
            "treated_station_id": treated_features.station_id.to_numpy()[rows // ratio],
            "control_station_id": control_features.station_id.to_numpy()[cols],
            "feature_distance": expanded_cost[rows, cols],
        }
    ).sort_values(["treated_station_id", "feature_distance", "control_station_id"])
    matches["match_rank"] = matches.groupby("treated_station_id").cumcount() + 1
    return matches.reset_index(drop=True)


def _monthly_series(
    panel: pd.DataFrame, station_ids: set[str], cohort: str
) -> pd.DataFrame:
    month_map = _event_months(cohort)
    reverse = {month: event for event, month in month_map.items()}
    subset = panel[
        panel.station_id.isin(station_ids) & panel.month.astype(str).isin(reverse)
    ].copy()
    subset["event_time"] = subset.month.astype(str).map(reverse)
    subset["log1p_trips"] = np.log1p(subset.total_trips)
    result = (
        subset.groupby(["month", "event_time"], as_index=False)
        .agg(mean_log1p_trips=("log1p_trips", "mean"), stations=("station_id", "nunique"))
        .sort_values("event_time")
    )
    return result[result.event_time.ne(-1)]


def _smd(left: pd.Series, right: pd.Series) -> float:
    # A conventional two-sample pooled variance is undefined for singleton
    # treated cohorts. The combined-population SD remains defined and prevents
    # those sparse cohorts from being misleadingly reported as perfect balance.
    scale = pd.concat([left, right], ignore_index=True).std(ddof=0)
    return float((left.mean() - right.mean()) / scale) if scale > 0 else 0.0


def _comparison_metrics(
    panel: pd.DataFrame,
    treated_ids: set[str],
    control_ids: set[str],
    cohort: str,
    treated_features: pd.DataFrame,
    control_features: pd.DataFrame,
    pool: str,
) -> dict[str, Any]:
    treated_series = _monthly_series(panel, treated_ids, cohort)
    control_series = _monthly_series(panel, control_ids, cohort)
    pre_t = treated_series[treated_series.event_time.isin(PRE_EVENT_TIMES)].set_index("event_time")
    pre_c = control_series[control_series.event_time.isin(PRE_EVENT_TIMES)].set_index("event_time")
    difference = pre_t.mean_log1p_trips - pre_c.mean_log1p_trips
    slope = stats.linregress(np.arange(len(difference)), difference.to_numpy())
    centered_t = pre_t.mean_log1p_trips - pre_t.mean_log1p_trips.mean()
    centered_c = pre_c.mean_log1p_trips - pre_c.mean_log1p_trips.mean()
    smds = {
        name: _smd(treated_features[name], control_features[name])
        for name in ("pre_mean_log1p", "pre_slope_log1p", "pre_sd_log1p", "pre_member_share")
    }
    return {
        "first_post_month": cohort,
        "control_pool": pool,
        "treated_stations": len(treated_ids),
        "control_stations": len(control_ids),
        "pre_months": len(difference),
        "pre_level_gap_log_points": float(difference.mean()),
        "pretrend_gap_pct_points_per_month": float(100 * slope.slope),
        "pretrend_slope_pvalue_descriptive": float(slope.pvalue),
        "centered_trajectory_rmse_log_points": float(
            np.sqrt(np.mean((centered_t - centered_c) ** 2))
        ),
        "trajectory_correlation": float(
            np.corrcoef(pre_t.mean_log1p_trips, pre_c.mean_log1p_trips)[0, 1]
        ),
        "smd_pre_mean_log1p": smds["pre_mean_log1p"],
        "smd_pre_slope_log1p": smds["pre_slope_log1p"],
        "smd_pre_sd_log1p": smds["pre_sd_log1p"],
        "smd_pre_member_share": smds["pre_member_share"],
        "max_abs_smd": max(abs(value) for value in smds.values()),
    }


def _plot_calendar(calendar: pd.DataFrame, path: Path) -> None:
    cohorts = sorted(calendar.first_post_month.unique())
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), sharey=True)
    for ax, cohort in zip(axes.flat, cohorts, strict=True):
        data = calendar[calendar.first_post_month.eq(cohort)]
        for pool in POOL_ORDER:
            line = data[data.control_pool.eq(pool)].sort_values("event_time")
            ax.plot(
                pd.to_datetime(line.month + "-01"),
                line.mean_log1p_trips,
                label=POOL_LABELS[pool],
                color=COLORS[pool],
                linewidth=2.2 if pool in {"treated", "pre_period_matched"} else 1.5,
            )
        transition = pd.Period(cohort, freq="M") - 1
        ax.axvline(transition.to_timestamp(), color="#f59e0b", linestyle="--", linewidth=1)
        ax.set_title(f"First full post month: {cohort}")
        ax.set_xlabel("Calendar month")
        ax.grid(alpha=0.18)
    axes[0, 0].set_ylabel("Mean log(1 + station trips)")
    axes[1, 0].set_ylabel("Mean log(1 + station trips)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False)
    fig.suptitle("Phase 3A raw calendar-time trends by treatment cohort", fontsize=15)
    fig.tight_layout(rect=(0, 0.06, 1, 0.96))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight", metadata={"Software": "bikelane-causal"})
    plt.close(fig)


def _plot_event(event: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
    for pool in POOL_ORDER:
        line = event[event.control_pool.eq(pool)].sort_values("event_time")
        style = dict(
            color=COLORS[pool],
            linewidth=2.4 if pool in {"treated", "pre_period_matched"} else 1.6,
            marker="o",
            markersize=3,
            label=POOL_LABELS[pool],
        )
        axes[0].plot(line.event_time, line.mean_log1p_trips, **style)
        axes[1].plot(line.event_time, line.pre_normalized_percent, **style)
    for ax in axes:
        ax.axvline(-1, color="#f59e0b", linestyle="--", linewidth=1)
        ax.axhline(0, color="#d1d5db", linewidth=0.8)
        ax.set_xlabel("Event month (−1 transition excluded)")
        ax.grid(alpha=0.18)
    axes[0].set_ylabel("Treated-station-weighted mean log(1 + trips)")
    axes[0].set_title("Raw level")
    axes[1].set_ylabel("Change from own pre-period mean (%)")
    axes[1].set_title("Pre-normalized descriptive index")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False)
    fig.suptitle("Phase 3A raw event-time view", fontsize=15)
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight", metadata={"Software": "bikelane-causal"})
    plt.close(fig)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_report(summary: dict[str, Any], comparison: pd.DataFrame, path: Path) -> None:
    rows = []
    for row in comparison.itertuples(index=False):
        rows.append(
            f"| {row.first_post_month} | {row.control_pool} | {row.treated_stations} | "
            f"{row.control_stations} | {row.pretrend_gap_pct_points_per_month:.2f} | "
            f"{row.centered_trajectory_rmse_log_points:.3f} | {row.max_abs_smd:.2f} |"
        )
    overall = summary["overall_pretrend_gap_pct_points_per_month"]
    text = f"""# Phase 3A Diagnostic Report

**Checkpoint:** `COMPLETE`  
**Causal treatment effect estimated:** no  
**Outcome used for diagnostics:** `log(1 + total station trips)`

## What is frozen before Phase 3B

- Broad controls are never-treated stations with a complete cohort-specific 12-month pre and 12-month post window.
- Cohort-local controls are broad controls within 3 km of a corridor treated in that cohort. All were already outside the 800 m exclusion donut around every 2024–2025 candidate corridor.
- Pre-period matched controls are selected only from the cohort-local pool using four 12-month pre-treatment features: mean, linear slope, variability of `log(1 + trips)`, and member-trip share.
- Matching is {summary['matching_controls_per_treated']}:1 without replacement within cohort. No post-treatment outcome enters control selection.

## Cohort comparison

The descriptive slope is the monthly linear trend in the treated-minus-control raw mean-log series over event months −13 through −2. Its p-value in the CSV is descriptive only; the Phase 3 gate does not treat it as a causal test.

| First post | Pool | Treated | Controls | Slope gap (pp/month) | Centered RMSE | Max abs SMD |
|---|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Treated-station-weighted aggregate pre-trends

- Broad controls: {overall['broad']:.2f} percentage points per month.
- Cohort-local controls: {overall['cohort_local']:.2f} percentage points per month.
- Pre-period matched controls: {overall['pre_period_matched']:.2f} percentage points per month.

## Composition

- Treated stations: {summary['treated_stations']} across {summary['treated_corridors']} corridors and {summary['cohorts']} cohorts.
- Every selected treated and control station has all 12 pre and 12 post outcome months for its cohort.
- Matched control rows: {summary['match_rows']}; unique within each cohort by construction.
- The transition month (`event_time = -1`) is excluded from every diagnostic series and from the later estimation sample.

## Figures

![Raw calendar-time trends](figures/phase3_calendar_trends.png)

![Raw event-time trends](figures/phase3_event_time_trends.png)

## Interpretation boundary

These figures reveal raw post-treatment outcomes but do not estimate an ATT, adjust for sampling uncertainty, or authorize a causal headline. Phase 3B must read the full cohort and corridor diagnostics, lock the control specification, and record the identification decision before Phase 4 begins.
"""
    path.write_text(text, encoding="utf-8")


def run_diagnostics() -> dict[str, Any]:
    config = load_config()
    raw = _raw_config()
    paths = _paths()
    phase3 = raw["phase3"]
    ratio = int(phase3["matching_controls_per_treated"])
    feature_names = list(phase3["matching_features"])
    panel = pd.read_parquet(config.paths["analysis_panel"])
    assignment = pd.read_parquet(config.paths["station_assignment"])
    eligible = pd.read_parquet(config.paths["control_cohort_eligibility"])
    treated = assignment[assignment.analysis_role.eq("primary_treated")].copy()

    match_frames: list[pd.DataFrame] = []
    metric_rows: list[dict[str, Any]] = []
    calendar_frames: list[pd.DataFrame] = []
    feature_cache: dict[tuple[str, str], pd.DataFrame] = {}
    pool_ids: dict[tuple[str, str], set[str]] = {}
    cohorts = sorted(treated.first_post_month.unique())

    for cohort in cohorts:
        cohort_treated = treated[treated.first_post_month.eq(cohort)].copy()
        treated_ids = set(cohort_treated.station_id)
        broad_ids = set(
            eligible.loc[
                eligible.first_post_month.eq(cohort) & eligible.eligible_12_pre_12_post,
                "station_id",
            ]
        )
        local = _cohort_local_controls(
            assignment, eligible, cohort, config.project_crs, config.local_control_outer_m
        )
        local_ids = set(local.station_id)
        treated_features = _station_features(panel, sorted(treated_ids), cohort)
        broad_features = _station_features(panel, sorted(broad_ids), cohort)
        local_features = _station_features(panel, sorted(local_ids), cohort)
        matches = _match_controls(treated_features, local_features, feature_names, ratio)
        matches.insert(0, "first_post_month", cohort)
        matches = matches.merge(
            local[["station_id", "cohort_local_distance_m"]],
            left_on="control_station_id",
            right_on="station_id",
            how="left",
            validate="many_to_one",
        ).drop(columns="station_id")
        matched_ids = set(matches.control_station_id)
        matched_features = local_features[local_features.station_id.isin(matched_ids)].copy()
        match_frames.append(matches)

        feature_cache[(cohort, "treated")] = treated_features
        feature_cache[(cohort, "broad")] = broad_features
        feature_cache[(cohort, "cohort_local")] = local_features
        feature_cache[(cohort, "pre_period_matched")] = matched_features
        pool_ids[(cohort, "treated")] = treated_ids
        pool_ids[(cohort, "broad")] = broad_ids
        pool_ids[(cohort, "cohort_local")] = local_ids
        pool_ids[(cohort, "pre_period_matched")] = matched_ids

        for pool in POOL_ORDER:
            series = _monthly_series(panel, pool_ids[(cohort, pool)], cohort)
            series.insert(0, "control_pool", pool)
            series.insert(0, "first_post_month", cohort)
            calendar_frames.append(series)
        for pool in POOL_ORDER[1:]:
            metric_rows.append(
                _comparison_metrics(
                    panel,
                    treated_ids,
                    pool_ids[(cohort, pool)],
                    cohort,
                    treated_features,
                    feature_cache[(cohort, pool)],
                    pool,
                )
            )

    matches = pd.concat(match_frames, ignore_index=True)
    comparison = pd.DataFrame(metric_rows)
    calendar = pd.concat(calendar_frames, ignore_index=True)
    treated_weights = (
        treated.groupby("first_post_month").station_id.nunique() / treated.station_id.nunique()
    ).to_dict()
    event_rows = []
    for pool in POOL_ORDER:
        for event_time in EVENT_TIMES:
            rows = calendar[
                calendar.control_pool.eq(pool) & calendar.event_time.eq(event_time)
            ]
            mean = sum(
                row.mean_log1p_trips * treated_weights[row.first_post_month]
                for row in rows.itertuples(index=False)
            )
            event_rows.append(
                {"control_pool": pool, "event_time": event_time, "mean_log1p_trips": mean}
            )
    event = pd.DataFrame(event_rows)
    event["pre_mean_log1p"] = event.groupby("control_pool").mean_log1p_trips.transform(
        lambda values: values[event.loc[values.index, "event_time"].isin(PRE_EVENT_TIMES)].mean()
    )
    event["pre_normalized_percent"] = 100 * np.expm1(
        event.mean_log1p_trips - event.pre_mean_log1p
    )

    overall_gaps = {}
    treated_pre = event[
        event.control_pool.eq("treated") & event.event_time.isin(PRE_EVENT_TIMES)
    ].sort_values("event_time")
    for pool in POOL_ORDER[1:]:
        control_pre = event[
            event.control_pool.eq(pool) & event.event_time.isin(PRE_EVENT_TIMES)
        ].sort_values("event_time")
        gap = treated_pre.mean_log1p_trips.to_numpy() - control_pre.mean_log1p_trips.to_numpy()
        overall_gaps[pool] = float(100 * stats.linregress(np.arange(len(gap)), gap).slope)

    corridor_rows = []
    for corridor, corridor_treated in treated.groupby("assigned_primary_corridor"):
        cohort = str(corridor_treated.first_post_month.iloc[0])
        treated_ids = set(corridor_treated.station_id)
        control_ids = pool_ids[(cohort, "pre_period_matched")]
        treated_series = _monthly_series(panel, treated_ids, cohort).set_index("event_time")
        control_series = _monthly_series(panel, control_ids, cohort).set_index("event_time")
        difference = (
            treated_series.loc[list(PRE_EVENT_TIMES), "mean_log1p_trips"]
            - control_series.loc[list(PRE_EVENT_TIMES), "mean_log1p_trips"]
        )
        slope = 100 * stats.linregress(np.arange(len(difference)), difference).slope
        corridor_rows.append(
            {
                "corridor_id": corridor,
                "first_post_month": cohort,
                "treated_stations": len(treated_ids),
                "date_confidence": ";".join(sorted(corridor_treated.date_confidence.unique())),
                "multiple_exposure_stations": int(corridor_treated.nearby_primary_corridor_count.gt(1).sum()),
                "pre_level_gap_log_points_vs_matched": float(difference.mean()),
                "pretrend_gap_pct_points_per_month_vs_matched": float(slope),
                "singleton_corridor": len(treated_ids) == 1,
                "corridor_pretrend_warning": abs(slope)
                >= float(phase3["corridor_warning_pct_points_per_month"]),
            }
        )
    corridor = pd.DataFrame(corridor_rows).sort_values("corridor_id")

    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    matches.to_csv(paths["phase3_matches"], index=False, float_format="%.6f")
    comparison.to_csv(paths["phase3_control_comparison"], index=False, float_format="%.6f")
    corridor.to_csv(paths["phase3_corridor_diagnostics"], index=False, float_format="%.6f")
    calendar.to_csv(paths["phase3_calendar_series"], index=False, float_format="%.6f")
    event.to_csv(paths["phase3_event_series"], index=False, float_format="%.6f")
    _plot_calendar(calendar, ROOT / "reports" / "figures" / "phase3_calendar_trends.png")
    _plot_event(event, ROOT / "reports" / "figures" / "phase3_event_time_trends.png")

    summary = {
        "checkpoint": "Phase 3A complete",
        "treatment_effect_estimated": False,
        "treated_stations": int(treated.station_id.nunique()),
        "treated_corridors": int(treated.assigned_primary_corridor.nunique()),
        "cohorts": len(cohorts),
        "matching_controls_per_treated": ratio,
        "matching_features": feature_names,
        "matching_uses_post_treatment_outcomes": False,
        "match_rows": len(matches),
        "unique_matches_within_cohort": not matches.duplicated(
            ["first_post_month", "control_station_id"]
        ).any(),
        "event_times": list(EVENT_TIMES),
        "transition_month_excluded": True,
        "all_selected_windows_complete": bool(
            (comparison.pre_months.eq(12)).all()
            and calendar.groupby(["first_post_month", "control_pool"]).event_time.nunique().eq(24).all()
        ),
        "overall_pretrend_gap_pct_points_per_month": overall_gaps,
        "cohort_pretrend_warning_threshold": float(
            phase3["pretrend_warning_pct_points_per_month"]
        ),
        "corridor_pretrend_warning_threshold": float(
            phase3["corridor_warning_pct_points_per_month"]
        ),
    }
    summary["matches_sha256"] = _sha256(paths["phase3_matches"])
    paths["phase3a_summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    _write_report(summary, comparison, paths["phase3a_report"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    run_diagnostics()
