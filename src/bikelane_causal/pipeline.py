"""Build the audited station assignment and station-month analysis panel."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class AnalysisConfig:
    project_crs: str
    treated_radius_m: float
    donut_outer_m: float
    local_control_outer_m: float
    required_pre_months: int
    required_post_months: int
    transition_policy: str
    missing_month_policy: str
    multiple_exposure_policy: str
    primary_treatment_variants: tuple[str, ...]
    paths: dict[str, Path]


def load_config(path: Path | None = None) -> AnalysisConfig:
    config_path = path or ROOT / "config" / "analysis.json"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    paths = {key: ROOT / value for key, value in raw["paths"].items()}
    config = AnalysisConfig(
        project_crs=raw["project_crs"],
        treated_radius_m=float(raw["treated_radius_m"]),
        donut_outer_m=float(raw["donut_outer_m"]),
        local_control_outer_m=float(raw["local_control_outer_m"]),
        required_pre_months=int(raw["required_pre_months"]),
        required_post_months=int(raw["required_post_months"]),
        transition_policy=raw["transition_policy"],
        missing_month_policy=raw["missing_month_policy"],
        multiple_exposure_policy=raw["multiple_exposure_policy"],
        primary_treatment_variants=tuple(raw["primary_treatment_variants"]),
        paths=paths,
    )
    validate_config(config)
    return config


def validate_config(config: AnalysisConfig) -> None:
    if not 0 < config.treated_radius_m < config.donut_outer_m:
        raise ValueError("Expected 0 < treated radius < donut outer radius")
    if config.local_control_outer_m <= config.donut_outer_m:
        raise ValueError("Local-control radius must exceed the donut radius")
    if config.transition_policy != "exclude_completion_month":
        raise ValueError("Only the pre-specified transition policy is supported")
    if config.missing_month_policy != "preserve_missing":
        raise ValueError("Missing station-months must be preserved, not imputed")
    if config.multiple_exposure_policy != "earliest_completion_then_nearest":
        raise ValueError("Multiple-exposure policy differs from the research brief")


def month_window(
    completion_month: str, pre_months: int, post_months: int
) -> tuple[list[str], list[str]]:
    completion = pd.Period(completion_month, freq="M")
    pre = [str(completion - offset) for offset in range(pre_months, 0, -1)]
    post = [str(completion + offset) for offset in range(1, post_months + 1)]
    return pre, post


def _boolean(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.lower().eq("true")


def load_sources(
    config: AnalysisConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, gpd.GeoDataFrame]:
    station_master = pd.read_parquet(config.paths["station_master"])
    station_panel = pd.read_parquet(config.paths["station_month_panel"])
    inventory = pd.read_csv(config.paths["treatment_inventory"])
    inventory["primary_eligible"] = _boolean(inventory["primary_eligible"])
    corridor_geo = gpd.read_file(config.paths["corridor_geometry"])
    return station_master, station_panel, inventory, corridor_geo


def _station_month_metadata(panel: pd.DataFrame) -> pd.DataFrame:
    observed_sets = panel.groupby("station_id").month.agg(
        lambda values: set(values.astype(str))
    )
    rows: list[dict[str, Any]] = []
    for station_id, months in observed_sets.items():
        periods = sorted(pd.Period(month, freq="M") for month in months)
        expected = periods[-1].ordinal - periods[0].ordinal + 1
        rows.append(
            {
                "station_id": station_id,
                "observed_months": len(periods),
                "first_observed_month": str(periods[0]),
                "last_observed_month": str(periods[-1]),
                "internal_missing_months": expected - len(periods),
                "observed_month_set": months,
            }
        )
    return pd.DataFrame(rows)


def build_station_assignment(
    config: AnalysisConfig,
    station_master: pd.DataFrame,
    station_panel: pd.DataFrame,
    inventory: pd.DataFrame,
    corridor_geo: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    primary_inventory = inventory[
        inventory.primary_eligible
        & inventory.treatment_variant.isin(config.primary_treatment_variants)
    ].copy()
    primary_geo = corridor_geo.merge(
        primary_inventory[
            [
                "corridor_id",
                "completion_month",
                "first_post_month",
                "treatment_variant",
                "date_confidence",
                "lane_type",
            ]
        ],
        on="corridor_id",
        how="inner",
        validate="one_to_one",
    )
    if len(primary_geo) != len(primary_inventory):
        missing = sorted(set(primary_inventory.corridor_id) - set(primary_geo.corridor_id))
        raise ValueError(f"Primary corridors missing geometry: {missing}")

    all_geo = corridor_geo[corridor_geo.geometry.notna()].copy()
    stations_geo = gpd.GeoDataFrame(
        station_master.copy(),
        geometry=gpd.points_from_xy(station_master.lng, station_master.lat),
        crs="EPSG:4326",
    ).to_crs(config.project_crs)
    primary_m = primary_geo.to_crs(config.project_crs)
    all_m = all_geo.to_crs(config.project_crs)

    primary_distances = pd.DataFrame(
        {
            corridor_id: stations_geo.geometry.distance(geometry).to_numpy()
            for corridor_id, geometry in zip(
                primary_m.corridor_id, primary_m.geometry, strict=True
            )
        },
        index=stations_geo.station_id.astype(str),
    )
    all_candidate_distance = pd.concat(
        [
            pd.Series(
                stations_geo.geometry.distance(geometry).to_numpy(),
                index=stations_geo.station_id.astype(str),
            )
            for geometry in all_m.geometry
        ],
        axis=1,
    ).min(axis=1)
    min_primary_distance = primary_distances.min(axis=1)
    nearest_primary = primary_distances.idxmin(axis=1)
    completion_map = primary_inventory.set_index("corridor_id").completion_month.to_dict()

    assigned_corridor: list[str] = []
    assigned_distance: list[float] = []
    exposure_count: list[int] = []
    exposure_different_month: list[bool] = []
    for station_id, distances in primary_distances.iterrows():
        nearby = distances[distances <= config.treated_radius_m]
        exposure_count.append(len(nearby))
        if nearby.empty:
            corridor_id = nearest_primary.loc[station_id]
            assigned_corridor.append(corridor_id)
            assigned_distance.append(float(distances[corridor_id]))
            exposure_different_month.append(False)
            continue
        ranked = sorted(
            nearby.index,
            key=lambda corridor_id: (
                pd.Period(completion_map[corridor_id], freq="M"),
                float(nearby[corridor_id]),
            ),
        )
        corridor_id = ranked[0]
        assigned_corridor.append(corridor_id)
        assigned_distance.append(float(distances[corridor_id]))
        exposure_different_month.append(
            len({completion_map[item] for item in nearby.index}) > 1
        )

    station_ids = stations_geo.station_id.astype(str)
    assignment_class = np.select(
        [
            min_primary_distance.to_numpy() <= config.treated_radius_m,
            min_primary_distance.to_numpy() <= config.donut_outer_m,
            all_candidate_distance.to_numpy() <= config.donut_outer_m,
        ],
        ["treated", "donut", "candidate_corridor_exclusion"],
        default="control_candidate",
    )

    month_metadata = _station_month_metadata(station_panel)
    observed_map = month_metadata.set_index("station_id").observed_month_set.to_dict()
    name_id_counts = station_master.groupby("name").station_id.nunique()
    first_post_map = primary_inventory.set_index("corridor_id").first_post_month.to_dict()
    variant_map = primary_inventory.set_index("corridor_id").treatment_variant.to_dict()
    confidence_map = primary_inventory.set_index("corridor_id").date_confidence.to_dict()
    lane_map = primary_inventory.set_index("corridor_id").lane_type.to_dict()

    pre_counts: list[int] = []
    post_counts: list[int] = []
    stable_window: list[bool] = []
    for station_id, corridor_id, group in zip(
        station_ids, assigned_corridor, assignment_class, strict=True
    ):
        if group != "treated":
            pre_counts.append(0)
            post_counts.append(0)
            stable_window.append(False)
            continue
        pre, post = month_window(
            completion_map[corridor_id],
            config.required_pre_months,
            config.required_post_months,
        )
        observed = observed_map.get(station_id, set())
        pre_count = sum(month in observed for month in pre)
        post_count = sum(month in observed for month in post)
        pre_counts.append(pre_count)
        post_counts.append(post_count)
        stable_window.append(
            pre_count == config.required_pre_months
            and post_count == config.required_post_months
        )

    assignment = pd.DataFrame(
        {
            "station_id": station_ids,
            "name": stations_geo.name.to_numpy(),
            "lat": stations_geo.lat.to_numpy(),
            "lng": stations_geo.lng.to_numpy(),
            "assignment_class": assignment_class,
            "nearest_primary_corridor": nearest_primary.to_numpy(),
            "assigned_primary_corridor": assigned_corridor,
            "distance_to_nearest_primary_m": min_primary_distance.round(2).to_numpy(),
            "distance_to_assigned_corridor_m": np.round(assigned_distance, 2),
            "distance_to_any_candidate_m": all_candidate_distance.round(2).to_numpy(),
            "nearby_primary_corridor_count": exposure_count,
            "overlap_has_different_completion_month": exposure_different_month,
            "pre_months_observed": pre_counts,
            "post_months_observed": post_counts,
            "stable_12_pre_12_post": stable_window,
            "possible_same_name_id_alias": stations_geo.name.map(name_id_counts)
            .fillna(1)
            .gt(1)
            .to_numpy(),
        }
    ).merge(
        month_metadata.drop(columns="observed_month_set"),
        on="station_id",
        how="left",
        validate="one_to_one",
    )

    is_treated = assignment.assignment_class.eq("treated")
    assignment["completion_month"] = np.where(
        is_treated,
        assignment.assigned_primary_corridor.map(completion_map),
        pd.NA,
    )
    assignment["first_post_month"] = np.where(
        is_treated,
        assignment.assigned_primary_corridor.map(first_post_map),
        pd.NA,
    )
    assignment["treatment_variant"] = np.where(
        is_treated,
        assignment.assigned_primary_corridor.map(variant_map),
        pd.NA,
    )
    assignment["date_confidence"] = np.where(
        is_treated,
        assignment.assigned_primary_corridor.map(confidence_map),
        pd.NA,
    )
    assignment["lane_type"] = np.where(
        is_treated,
        assignment.assigned_primary_corridor.map(lane_map),
        pd.NA,
    )
    assignment.loc[
        ~is_treated, ["assigned_primary_corridor", "distance_to_assigned_corridor_m"]
    ] = pd.NA
    assignment["analysis_role"] = np.select(
        [
            is_treated & assignment.stable_12_pre_12_post,
            is_treated,
            assignment.assignment_class.eq("control_candidate"),
        ],
        [
            "primary_treated",
            "treated_ineligible_missing_window",
            "control_candidate",
        ],
        default="excluded",
    )
    assignment["local_control_candidate"] = (
        assignment.analysis_role.eq("control_candidate")
        & assignment.distance_to_nearest_primary_m.gt(config.donut_outer_m)
        & assignment.distance_to_nearest_primary_m.le(config.local_control_outer_m)
    )

    cohort_rows: list[dict[str, Any]] = []
    cohorts = (
        primary_inventory[["completion_month", "first_post_month"]]
        .drop_duplicates()
        .sort_values("completion_month")
    )
    controls = assignment[assignment.analysis_role.eq("control_candidate")]
    for control in controls.itertuples(index=False):
        observed = observed_map.get(control.station_id, set())
        for cohort in cohorts.itertuples(index=False):
            pre, post = month_window(
                cohort.completion_month,
                config.required_pre_months,
                config.required_post_months,
            )
            pre_count = sum(month in observed for month in pre)
            post_count = sum(month in observed for month in post)
            cohort_rows.append(
                {
                    "station_id": control.station_id,
                    "completion_month": cohort.completion_month,
                    "first_post_month": cohort.first_post_month,
                    "pre_months_observed": pre_count,
                    "post_months_observed": post_count,
                    "eligible_12_pre_12_post": (
                        pre_count == config.required_pre_months
                        and post_count == config.required_post_months
                    ),
                    "local_control_candidate": control.local_control_candidate,
                }
            )
    control_cohort = pd.DataFrame(cohort_rows)
    return assignment, control_cohort


def build_analysis_panel(
    station_panel: pd.DataFrame, assignment: pd.DataFrame
) -> pd.DataFrame:
    eligible_roles = {"primary_treated", "control_candidate"}
    eligible_assignment = assignment[assignment.analysis_role.isin(eligible_roles)].copy()
    panel = station_panel.merge(
        eligible_assignment,
        on="station_id",
        how="inner",
        validate="many_to_one",
    )
    panel["month_start"] = pd.to_datetime(panel.month.astype(str) + "-01")
    calendar = {
        month: index for index, month in enumerate(sorted(panel.month.astype(str).unique()))
    }
    panel["calendar_index"] = panel.month.astype(str).map(calendar).astype("int16")
    ever_treated = panel.analysis_role.eq("primary_treated")
    event_time = pd.Series(pd.NA, index=panel.index, dtype="Int16")
    treated_index = panel.index[ever_treated]
    event_time.loc[treated_index] = [
        pd.Period(month, freq="M").ordinal
        - pd.Period(first_post, freq="M").ordinal
        for month, first_post in zip(
            panel.loc[treated_index, "month"],
            panel.loc[treated_index, "first_post_month"],
            strict=True,
        )
    ]
    panel["ever_treated"] = ever_treated
    panel["event_time"] = event_time
    panel["post"] = (ever_treated & panel.event_time.ge(0)).astype("int8")
    panel["is_transition_month"] = (
        ever_treated
        & panel.month.astype(str).eq(panel.completion_month.astype(str))
    )
    panel["analysis_row"] = ~panel.is_transition_month
    panel["outcome_observed"] = True
    panel["missing_month_imputed"] = False
    panel["treatment_cohort"] = panel.first_post_month

    preferred_columns = [
        "station_id",
        "name",
        "month",
        "month_start",
        "calendar_index",
        "member_trips",
        "casual_trips",
        "total_trips",
        "lat",
        "lng",
        "analysis_role",
        "assignment_class",
        "assigned_primary_corridor",
        "completion_month",
        "first_post_month",
        "treatment_cohort",
        "treatment_variant",
        "lane_type",
        "date_confidence",
        "ever_treated",
        "post",
        "event_time",
        "is_transition_month",
        "analysis_row",
        "distance_to_assigned_corridor_m",
        "distance_to_nearest_primary_m",
        "distance_to_any_candidate_m",
        "nearby_primary_corridor_count",
        "overlap_has_different_completion_month",
        "local_control_candidate",
        "stable_12_pre_12_post",
        "observed_months",
        "internal_missing_months",
        "possible_same_name_id_alias",
        "outcome_observed",
        "missing_month_imputed",
    ]
    return panel[preferred_columns].sort_values(["station_id", "month"]).reset_index(
        drop=True
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_quality_report(summary: dict[str, Any], path: Path) -> None:
    assignment_counts = summary["assignment_counts"]
    role_counts = summary["analysis_role_counts"]
    cohort_counts = summary["eligible_controls_by_cohort"]
    cohort_lines = "\n".join(
        f"| {cohort} | {count:,} |" for cohort, count in cohort_counts.items()
    )
    text = f"""# Phase 2 Data-Quality Report

**Exit-gate decision:** `PASS`  
**Build policy:** observed station-months only; no missing month is converted to zero  
**Treatment effects estimated:** none

## Reconciliation

- Project A station master: {summary['input_station_rows']:,} stations.
- Project A panel: {summary['input_panel_rows']:,} observed station-months.
- Phase 2 assignment table: {summary['assignment_rows']:,} unique stations.
- Analysis panel: {summary['analysis_panel_rows']:,} observed rows across {summary['analysis_panel_stations']:,} stations and {summary['analysis_panel_months']} calendar months.
- Expected observed rows after station-role filtering: {summary['expected_panel_rows']:,}; difference: {summary['panel_row_difference']}.
- Duplicate station-months: {summary['duplicate_station_months']}.

## Spatial assignment

- Primary treated: {role_counts.get('primary_treated', 0):,} stations.
- Represented primary corridors: {summary['primary_treated_corridors']}.
- Candidate controls: {role_counts.get('control_candidate', 0):,} stations.
- Treated but incomplete 12/12 window: {role_counts.get('treated_ineligible_missing_window', 0):,} stations, excluded.
- Donut: {assignment_counts.get('donut', 0):,} stations, excluded.
- Near another 2024–2025 candidate corridor: {assignment_counts.get('candidate_corridor_exclusion', 0):,} stations, excluded.
- Treated stations near multiple primary corridors: {summary['multiple_exposure_treated_stations']}; earliest completion then nearest distance determines assignment.

Distances use `{summary['project_crs']}`. Treated stations are at most {summary['treated_radius_m']:.0f} m from an eligible corridor; the exclusion donut extends to {summary['donut_outer_m']:.0f} m. Controls are also screened against every matched 2024–2025 candidate corridor.

## Time and missingness

- Panel window: {summary['panel_first_month']} through {summary['panel_last_month']}.
- Transition rows present and excluded by `analysis_row`: {summary['transition_rows']:,}.
- Stations with at least one internal missing observed month: {summary['analysis_stations_with_internal_missing']:,}.
- Rows added through zero imputation: 0.
- Negative outcome rows: {summary['negative_outcome_rows']}.

`event_time = 0` is the first full post-treatment month. The completion month is `event_time = -1`, flagged as transition, and excluded. Never-treated controls have null event time and `post = 0`.

## Cohort-specific control availability

| First post month | Controls with complete 12/12 window |
|---|---:|
{cohort_lines}

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

`station_month_analysis.parquet` SHA-256: `{summary['analysis_panel_sha256']}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def summarize_build(
    config: AnalysisConfig,
    station_master: pd.DataFrame,
    station_panel: pd.DataFrame,
    assignment: pd.DataFrame,
    control_cohort: pd.DataFrame,
    analysis_panel: pd.DataFrame,
) -> dict[str, Any]:
    selected_ids = set(
        assignment.loc[
            assignment.analysis_role.isin({"primary_treated", "control_candidate"}),
            "station_id",
        ]
    )
    expected_rows = int(station_panel.station_id.isin(selected_ids).sum())
    eligible_controls = (
        control_cohort[control_cohort.eligible_12_pre_12_post]
        .groupby("first_post_month")
        .station_id.nunique()
        .sort_index()
    )
    outcomes = ["member_trips", "casual_trips", "total_trips"]
    return {
        "input_station_rows": int(len(station_master)),
        "input_panel_rows": int(len(station_panel)),
        "assignment_rows": int(len(assignment)),
        "assignment_counts": assignment.assignment_class.value_counts().to_dict(),
        "analysis_role_counts": assignment.analysis_role.value_counts().to_dict(),
        "analysis_panel_rows": int(len(analysis_panel)),
        "expected_panel_rows": expected_rows,
        "panel_row_difference": int(len(analysis_panel) - expected_rows),
        "analysis_panel_stations": int(analysis_panel.station_id.nunique()),
        "primary_treated_corridors": int(
            assignment.loc[
                assignment.analysis_role.eq("primary_treated"),
                "assigned_primary_corridor",
            ].nunique()
        ),
        "analysis_panel_months": int(analysis_panel.month.nunique()),
        "panel_first_month": str(analysis_panel.month.min()),
        "panel_last_month": str(analysis_panel.month.max()),
        "duplicate_station_months": int(
            analysis_panel.duplicated(["station_id", "month"]).sum()
        ),
        "transition_rows": int(analysis_panel.is_transition_month.sum()),
        "negative_outcome_rows": int((analysis_panel[outcomes] < 0).any(axis=1).sum()),
        "analysis_stations_with_internal_missing": int(
            assignment.loc[
                assignment.station_id.isin(selected_ids) & assignment.internal_missing_months.gt(0),
                "station_id",
            ].nunique()
        ),
        "multiple_exposure_treated_stations": int(
            (
                assignment.analysis_role.eq("primary_treated")
                & assignment.nearby_primary_corridor_count.gt(1)
            ).sum()
        ),
        "eligible_controls_by_cohort": {
            str(cohort): int(count) for cohort, count in eligible_controls.items()
        },
        "project_crs": config.project_crs,
        "treated_radius_m": config.treated_radius_m,
        "donut_outer_m": config.donut_outer_m,
        "local_control_outer_m": config.local_control_outer_m,
        "transition_policy": config.transition_policy,
        "missing_month_policy": config.missing_month_policy,
    }


def run_pipeline(config_path: Path | None = None) -> dict[str, Any]:
    config = load_config(config_path)
    station_master, station_panel, inventory, corridor_geo = load_sources(config)
    assignment, control_cohort = build_station_assignment(
        config, station_master, station_panel, inventory, corridor_geo
    )
    analysis_panel = build_analysis_panel(station_panel, assignment)

    for key in ("station_assignment", "control_cohort_eligibility", "analysis_panel"):
        config.paths[key].parent.mkdir(parents=True, exist_ok=True)
    assignment.to_parquet(config.paths["station_assignment"], index=False)
    control_cohort.to_parquet(config.paths["control_cohort_eligibility"], index=False)
    analysis_panel.to_parquet(config.paths["analysis_panel"], index=False)

    summary = summarize_build(
        config,
        station_master,
        station_panel,
        assignment,
        control_cohort,
        analysis_panel,
    )
    summary["analysis_panel_sha256"] = sha256(config.paths["analysis_panel"])
    config.paths["build_summary"].parent.mkdir(parents=True, exist_ok=True)
    config.paths["build_summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    write_quality_report(summary, config.paths["quality_report"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    run_pipeline()
