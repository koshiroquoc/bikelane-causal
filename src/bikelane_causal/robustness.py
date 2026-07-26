"""Phase 5 robustness checks and pipeline-level falsification tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bikelane_causal.diagnostics import (
    ROOT,
    _cohort_local_controls,
    _match_controls,
    _paths,
    _raw_config,
    _station_features,
)
from bikelane_causal.estimation import _percent_from_pair_values, build_pair_scores
from bikelane_causal.pipeline import (
    AnalysisConfig,
    build_analysis_panel,
    build_station_assignment,
    load_config,
    load_sources,
    month_window,
)


def _pair_result(pair_scores: pd.DataFrame, post_start: int = 0) -> dict[str, float]:
    post = pair_scores[pair_scores.event_time.ge(post_start)].copy()
    keys = [
        "first_post_month",
        "treated_station_id",
        "control_station_id",
        "corridor_cluster",
    ]
    pair_post = post.groupby(keys, as_index=False)[
        ["effect_count", "treated_observed"]
    ].mean()
    return _percent_from_pair_values(pair_post)


def _row(
    milestone: str,
    specification: str,
    result: dict[str, Any],
    treated_stations: int,
    treated_corridors: int,
    control_stations: int,
    inference: str = "two-way clustered 95% CI",
    notes: str = "",
) -> dict[str, Any]:
    return {
        "milestone": milestone,
        "specification": specification,
        "effect_percent": result.get("effect_percent", np.nan),
        "ci_low_percent": result.get("ci_low_percent", np.nan),
        "ci_high_percent": result.get("ci_high_percent", np.nan),
        "treated_stations": int(treated_stations),
        "treated_corridors": int(treated_corridors),
        "control_stations": int(control_stations),
        "inference": inference,
        "notes": notes,
    }


def _build_real_matches(
    config: AnalysisConfig,
    raw: dict[str, Any],
    station_master: pd.DataFrame,
    station_panel: pd.DataFrame,
    inventory: pd.DataFrame,
    corridor_geo: gpd.GeoDataFrame,
    ratio_override: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    assignment, eligible = build_station_assignment(
        config, station_master, station_panel, inventory, corridor_geo
    )
    panel = build_analysis_panel(station_panel, assignment)
    treated = assignment[assignment.analysis_role.eq("primary_treated")]
    ratio = int(
        ratio_override
        if ratio_override is not None
        else raw["phase3"]["matching_controls_per_treated"]
    )
    features = list(raw["phase3"]["matching_features"])
    frames = []
    for cohort in sorted(treated.first_post_month.dropna().unique()):
        treated_ids = sorted(
            treated.loc[treated.first_post_month.eq(cohort), "station_id"].unique()
        )
        local = _cohort_local_controls(
            assignment,
            eligible,
            str(cohort),
            config.project_crs,
            config.local_control_outer_m,
        )
        treated_features = _station_features(panel, treated_ids, str(cohort))
        control_features = _station_features(
            panel, sorted(local.station_id.unique()), str(cohort)
        )
        matches = _match_controls(treated_features, control_features, features, ratio)
        matches.insert(0, "first_post_month", str(cohort))
        frames.append(matches)
    return assignment, eligible, panel, pd.concat(frames, ignore_index=True)


def _pool_point_result(
    panel: pd.DataFrame,
    assignment: pd.DataFrame,
    eligible: pd.DataFrame,
    pool: str,
    phase4: dict[str, Any],
    local_outer_m: float,
    project_crs: str,
) -> tuple[dict[str, float], int]:
    outcome = panel.pivot(index="station_id", columns="month", values="total_trips")
    treated = assignment[assignment.analysis_role.eq("primary_treated")]
    rows: list[dict[str, float]] = []
    used_controls: set[str] = set()
    reference = int(phase4["event_reference"])
    for cohort in sorted(treated.first_post_month.unique()):
        cohort = str(cohort)
        if pool == "broad":
            control_ids = sorted(
                eligible.loc[
                    eligible.first_post_month.eq(cohort)
                    & eligible.eligible_12_pre_12_post,
                    "station_id",
                ].unique()
            )
        elif pool == "cohort_local":
            local = _cohort_local_controls(
                assignment, eligible, cohort, project_crs, local_outer_m
            )
            control_ids = sorted(local.station_id.unique())
        else:
            raise ValueError(f"Unknown control pool: {pool}")
        used_controls.update(control_ids)
        treated_ids = sorted(
            treated.loc[treated.first_post_month.eq(cohort), "station_id"].unique()
        )
        reference_month = str(pd.Period(cohort, freq="M") + reference)
        for event in range(0, int(phase4["event_max"]) + 1):
            event_month = str(pd.Period(cohort, freq="M") + event)
            control_delta = float(
                (
                    outcome.loc[control_ids, event_month]
                    - outcome.loc[control_ids, reference_month]
                ).mean()
            )
            for station_id in treated_ids:
                treated_delta = float(
                    outcome.loc[station_id, event_month]
                    - outcome.loc[station_id, reference_month]
                )
                rows.append(
                    {
                        "effect_count": treated_delta - control_delta,
                        "treated_observed": float(outcome.loc[station_id, event_month]),
                    }
                )
    values = pd.DataFrame(rows).mean()
    counterfactual = values.treated_observed - values.effect_count
    return (
        {
            "effect_percent": float(100 * values.effect_count / counterfactual),
            "counterfactual_mean": float(counterfactual),
        },
        len(used_controls),
    )


def _shifted_pair_scores(
    panel: pd.DataFrame,
    assignment: pd.DataFrame,
    matches: pd.DataFrame,
    shift_months: int,
    post_end: int,
    shift_only_corridors: set[str] | None = None,
    outcome_column: str = "total_trips",
) -> pd.DataFrame:
    outcome = panel.pivot(index="station_id", columns="month", values=outcome_column)
    treated = assignment[assignment.analysis_role.eq("primary_treated")].set_index(
        "station_id"
    )
    rows = []
    for match in matches.itertuples(index=False):
        info = treated.loc[match.treated_station_id]
        corridor = str(info.assigned_primary_corridor)
        apply_shift = shift_only_corridors is None or corridor in shift_only_corridors
        shift = shift_months if apply_shift else 0
        cohort = pd.Period(str(match.first_post_month), freq="M") + shift
        reference_month = str(cohort - 2)
        for event in range(0, post_end + 1):
            event_month = str(cohort + event)
            treated_delta = (
                outcome.loc[match.treated_station_id, event_month]
                - outcome.loc[match.treated_station_id, reference_month]
            )
            control_delta = (
                outcome.loc[match.control_station_id, event_month]
                - outcome.loc[match.control_station_id, reference_month]
            )
            rows.append(
                {
                    "first_post_month": str(cohort),
                    "event_time": event,
                    "treated_station_id": match.treated_station_id,
                    "control_station_id": match.control_station_id,
                    "corridor_cluster": corridor,
                    "effect_count": float(treated_delta - control_delta),
                    "treated_observed": float(
                        outcome.loc[match.treated_station_id, event_month]
                    ),
                }
            )
    return pd.DataFrame(rows)


def _plot_radius(table: pd.DataFrame, path: Path) -> None:
    data = table[table.milestone.eq("M5.1 radius")].copy()
    fig, ax = plt.subplots(figsize=(9, 4.8))
    y = np.arange(len(data))
    ax.errorbar(
        data.effect_percent,
        y,
        xerr=[
            data.effect_percent - data.ci_low_percent,
            data.ci_high_percent - data.effect_percent,
        ],
        fmt="o",
        color="#155e75",
        ecolor="#67e8f9",
        capsize=4,
    )
    ax.axvline(0, color="#6b7280", linewidth=1)
    ax.set_yticks(y, data.specification)
    ax.set_xlabel("Estimated change in monthly trips (%)")
    ax.set_title("Phase 5 radius and donut sensitivity")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _plot_loco(table: pd.DataFrame, main_effect: float, path: Path) -> None:
    data = table.sort_values("effect_percent").copy()
    fig, ax = plt.subplots(figsize=(9, 7))
    y = np.arange(len(data))
    ax.errorbar(
        data.effect_percent,
        y,
        xerr=[
            data.effect_percent - data.ci_low_percent,
            data.ci_high_percent - data.effect_percent,
        ],
        fmt="o",
        color="#7c3aed",
        ecolor="#c4b5fd",
        capsize=3,
    )
    ax.axvline(main_effect, color="#111827", linestyle="--", label="Primary estimate")
    ax.axvline(0, color="#9ca3af", linewidth=1)
    ax.set_yticks(y, data.omitted_corridor)
    ax.set_xlabel("Estimated change in monthly trips (%)")
    ax.set_title("Leave-one-corridor-out estimates")
    ax.legend(frameon=False)
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _complete_ids(
    station_panel: pd.DataFrame, completion_month: str
) -> set[str]:
    pre, post = month_window(completion_month, 12, 12)
    required = set(pre + post)
    observed = station_panel.groupby("station_id").month.agg(
        lambda values: set(values.astype(str))
    )
    return {station_id for station_id, months in observed.items() if required <= months}


def _pseudo_candidate_pool(
    config: AnalysisConfig,
    geo_cfg: dict[str, Any],
    station_master: pd.DataFrame,
    station_panel: pd.DataFrame,
    assignment: pd.DataFrame,
    inventory: pd.DataFrame,
    corridor_geo: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, dict[str, list[str]], pd.DataFrame]:
    routes = gpd.read_file(
        ROOT / "data" / "reference" / "chicago_bike_routes_current.geojson"
    ).to_crs(config.project_crs)
    protected_streets = set(
        routes.loc[routes.displayrou.eq("Protected Bike Lane"), "st_name"].dropna()
    )
    routes = routes[
        routes.displayrou.ne("Protected Bike Lane")
        & ~routes.st_name.isin(protected_streets)
    ].copy()
    candidates = routes.dissolve(by="st_name").explode(index_parts=False).reset_index()
    candidates["length_miles"] = candidates.length / 1609.344
    candidates = candidates[
        candidates.length_miles.between(
            float(geo_cfg["candidate_min_length_miles"]),
            float(geo_cfg["candidate_max_length_miles"]),
        )
    ].copy()
    real_all = corridor_geo.to_crs(config.project_crs)
    real_union = real_all.geometry.union_all()
    candidates["distance_to_candidate_inventory_m"] = candidates.distance(real_union)
    candidates = candidates[
        candidates.distance_to_candidate_inventory_m.gt(
            float(geo_cfg["real_corridor_buffer_m"])
        )
    ].copy()
    candidates = candidates.reset_index(drop=True)
    candidates["pseudo_corridor_id"] = [f"PSEUDO_{i:03d}" for i in range(len(candidates))]
    candidates["centroid_x"] = candidates.centroid.x
    candidates["centroid_y"] = candidates.centroid.y

    stations = gpd.GeoDataFrame(
        station_master.copy(),
        geometry=gpd.points_from_xy(station_master.lng, station_master.lat),
        crs="EPSG:4326",
    ).to_crs(config.project_crs)
    candidate_station_ids: dict[str, list[str]] = {}
    for row in candidates.itertuples(index=False):
        ids = stations.loc[
            stations.geometry.distance(row.geometry).le(config.treated_radius_m),
            "station_id",
        ].astype(str).tolist()
        candidate_station_ids[row.pseudo_corridor_id] = ids
    candidates["nearby_station_count_raw"] = candidates.pseudo_corridor_id.map(
        lambda key: len(candidate_station_ids[key])
    )
    candidates = candidates[candidates.nearby_station_count_raw.gt(0)].copy()

    primary = inventory[
        inventory.primary_eligible
        & inventory.treatment_variant.isin(config.primary_treatment_variants)
    ].copy()
    primary_geo = corridor_geo.merge(
        primary[["corridor_id", "first_post_month"]], on="corridor_id", how="inner"
    ).to_crs(config.project_crs)
    treated = assignment[assignment.analysis_role.eq("primary_treated")]
    feature_rows: list[dict[str, Any]] = []
    shortlists: dict[str, list[str]] = {}
    match_features = [
        "log_length",
        "centroid_x",
        "centroid_y",
        "nearby_stations",
        "baseline_mean_log1p",
        "baseline_slope_log1p",
    ]
    for real in primary_geo.itertuples(index=False):
        cohort = str(real.first_post_month)
        completion = str(pd.Period(cohort, freq="M") - 1)
        complete = _complete_ids(station_panel, completion)
        real_ids = sorted(
            treated.loc[
                treated.assigned_primary_corridor.eq(real.corridor_id), "station_id"
            ].astype(str)
        )
        real_station_features = _station_features(station_panel, real_ids, cohort)
        real_feature = {
            "pseudo_corridor_id": "__REAL__",
            "log_length": float(np.log(max(real.geometry.length / 1609.344, 0.01))),
            "centroid_x": float(real.geometry.centroid.x),
            "centroid_y": float(real.geometry.centroid.y),
            "nearby_stations": len(real_ids),
            "baseline_mean_log1p": float(real_station_features.pre_mean_log1p.mean()),
            "baseline_slope_log1p": float(real_station_features.pre_slope_log1p.mean()),
        }
        pool_rows = []
        for candidate in candidates.itertuples(index=False):
            ids = sorted(
                set(candidate_station_ids[candidate.pseudo_corridor_id]) & complete
            )
            if not ids:
                continue
            station_features = _station_features(station_panel, ids, cohort)
            pool_rows.append(
                {
                    "pseudo_corridor_id": candidate.pseudo_corridor_id,
                    "log_length": float(np.log(candidate.length_miles)),
                    "centroid_x": float(candidate.centroid_x),
                    "centroid_y": float(candidate.centroid_y),
                    "nearby_stations": len(ids),
                    "baseline_mean_log1p": float(
                        station_features.pre_mean_log1p.mean()
                    ),
                    "baseline_slope_log1p": float(
                        station_features.pre_slope_log1p.mean()
                    ),
                }
            )
        frame = pd.DataFrame([real_feature] + pool_rows)
        scale = frame[match_features].std(ddof=0).replace(0, 1)
        z = (frame[match_features] - frame[match_features].mean()) / scale
        distance = np.sqrt(((z.iloc[1:] - z.iloc[0]) ** 2).sum(axis=1))
        frame = frame.iloc[1:].copy()
        frame["match_distance"] = distance.to_numpy()
        frame["real_corridor_id"] = real.corridor_id
        frame["first_post_month"] = cohort
        frame = frame.sort_values(["match_distance", "pseudo_corridor_id"])
        shortlist = frame.head(int(geo_cfg["shortlist_per_real_corridor"]))
        shortlists[real.corridor_id] = shortlist.pseudo_corridor_id.tolist()
        feature_rows.extend(shortlist.to_dict("records"))
    candidates = candidates[candidates.pseudo_corridor_id.isin(
        {item for values in shortlists.values() for item in values}
    )].copy()
    return candidates, shortlists, pd.DataFrame(feature_rows)


def _draw_pseudo_design(
    rng: np.random.Generator,
    shortlists: dict[str, list[str]],
    real_slots: pd.DataFrame,
) -> pd.DataFrame | None:
    selected: set[str] = set()
    rows = []
    order = real_slots.assign(
        choices=real_slots.corridor_id.map(lambda key: len(shortlists[key]))
    ).sort_values(["choices", "corridor_id"])
    for slot in order.itertuples(index=False):
        available = [item for item in shortlists[slot.corridor_id] if item not in selected]
        if not available:
            return None
        rank_cap = min(len(available), 6)
        pseudo = available[int(rng.integers(0, rank_cap))]
        selected.add(pseudo)
        rows.append(
            {
                "real_corridor_id": slot.corridor_id,
                "pseudo_corridor_id": pseudo,
                "first_post_month": str(slot.first_post_month),
            }
        )
    return pd.DataFrame(rows)


def _estimate_pseudo_design(
    draw: pd.DataFrame,
    candidates: gpd.GeoDataFrame,
    config: AnalysisConfig,
    raw: dict[str, Any],
    station_master: pd.DataFrame,
    station_panel: pd.DataFrame,
    corridor_geo: gpd.GeoDataFrame,
    stations: gpd.GeoDataFrame,
    safe_real: np.ndarray,
    complete_by_cohort: dict[str, set[str]],
) -> dict[str, Any] | None:
    selected = draw.merge(
        candidates[["pseudo_corridor_id", "geometry"]],
        on="pseudo_corridor_id",
        how="left",
        validate="one_to_one",
    )
    distance = pd.DataFrame(
        {
            row.pseudo_corridor_id: stations.geometry.distance(row.geometry).to_numpy()
            for row in selected.itertuples(index=False)
        },
        index=stations.station_id.astype(str),
    )
    slot = selected.set_index("pseudo_corridor_id")
    assignments = []
    for station_id, values in distance.iterrows():
        nearby = values[values.le(config.treated_radius_m)]
        if nearby.empty:
            continue
        pseudo_id = sorted(
            nearby.index,
            key=lambda key: (
                pd.Period(slot.loc[key, "first_post_month"], freq="M"),
                float(nearby[key]),
            ),
        )[0]
        cohort = str(slot.loc[pseudo_id, "first_post_month"])
        if station_id not in complete_by_cohort[cohort]:
            continue
        assignments.append(
            {
                "station_id": station_id,
                "analysis_role": "primary_treated",
                "assigned_primary_corridor": pseudo_id,
                "first_post_month": cohort,
            }
        )
    treated = pd.DataFrame(assignments)
    if treated.empty or treated.assigned_primary_corridor.nunique() != len(selected):
        return None

    safe_pseudo = distance.min(axis=1).gt(config.donut_outer_m).to_numpy()
    control_base = stations.loc[safe_real & safe_pseudo].copy()
    ratio = int(raw["phase3"]["matching_controls_per_treated"])
    feature_names = list(raw["phase3"]["matching_features"])
    match_frames = []
    for cohort in sorted(treated.first_post_month.unique()):
        complete = complete_by_cohort[cohort]
        cohort_geometry = selected.loc[
            selected.first_post_month.eq(cohort), "geometry"
        ]
        local_distance = np.min(
            np.vstack(
                [control_base.geometry.distance(geometry) for geometry in cohort_geometry]
            ),
            axis=0,
        )
        controls = control_base.loc[
            (local_distance <= config.local_control_outer_m)
            & control_base.station_id.astype(str).isin(complete)
        ].copy()
        treated_ids = sorted(
            treated.loc[treated.first_post_month.eq(cohort), "station_id"].unique()
        )
        if len(controls) < ratio * len(treated_ids):
            return None
        try:
            treated_features = _station_features(station_panel, treated_ids, cohort)
            control_features = _station_features(
                station_panel, sorted(controls.station_id.astype(str)), cohort
            )
            matches = _match_controls(
                treated_features, control_features, feature_names, ratio
            )
        except ValueError:
            return None
        matches.insert(0, "first_post_month", cohort)
        match_frames.append(matches)
    matches = pd.concat(match_frames, ignore_index=True)
    pair_scores = build_pair_scores(
        station_panel, treated, matches, raw["phase4"], "total_trips"
    )
    result = _pair_result(pair_scores)
    return {
        **result,
        "treated_stations": int(treated.station_id.nunique()),
        "treated_corridors": int(treated.assigned_primary_corridor.nunique()),
        "control_stations": int(matches.control_station_id.nunique()),
    }


def _geography_placebos(
    config: AnalysisConfig,
    raw: dict[str, Any],
    station_master: pd.DataFrame,
    station_panel: pd.DataFrame,
    assignment: pd.DataFrame,
    inventory: pd.DataFrame,
    corridor_geo: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    geo_cfg = raw["phase5"]["geography_placebo"]
    candidates, shortlists, match_table = _pseudo_candidate_pool(
        config,
        geo_cfg,
        station_master,
        station_panel,
        assignment,
        inventory,
        corridor_geo,
    )
    primary = inventory[
        inventory.primary_eligible
        & inventory.treatment_variant.isin(config.primary_treatment_variants)
    ][["corridor_id", "first_post_month"]].copy()
    complete_by_cohort = {
        str(cohort): _complete_ids(
            station_panel, str(pd.Period(str(cohort), freq="M") - 1)
        )
        for cohort in sorted(primary.first_post_month.unique())
    }
    stations = gpd.GeoDataFrame(
        station_master.copy(),
        geometry=gpd.points_from_xy(station_master.lng, station_master.lat),
        crs="EPSG:4326",
    ).to_crs(config.project_crs)
    real_union = corridor_geo.to_crs(config.project_crs).geometry.union_all()
    safe_real = (
        stations.geometry.distance(real_union).gt(config.donut_outer_m).to_numpy()
    )
    rng = np.random.default_rng(int(geo_cfg["seed"]))
    results = []
    attempts = 0
    target = int(geo_cfg["replications"])
    while len(results) < target and attempts < int(geo_cfg["max_attempts"]):
        attempts += 1
        draw = _draw_pseudo_design(rng, shortlists, primary)
        if draw is None:
            continue
        result = _estimate_pseudo_design(
            draw,
            candidates,
            config,
            raw,
            station_master,
            station_panel,
            corridor_geo,
            stations,
            safe_real,
            complete_by_cohort,
        )
        if result is None:
            continue
        result["replication"] = len(results) + 1
        result["attempt"] = attempts
        result["drawn_corridors"] = ";".join(sorted(draw.pseudo_corridor_id))
        results.append(result)
    placebo = pd.DataFrame(results)
    if len(placebo) < target:
        raise RuntimeError(
            f"Only {len(placebo)} valid geography placebos after {attempts} attempts"
        )
    screening = {
        "replications": len(placebo),
        "attempts": attempts,
        "candidate_components": int(candidates.pseudo_corridor_id.nunique()),
        "candidate_streets": int(candidates.st_name.nunique()),
        "screen": (
            "non-protected facility on a street name with no protected segment; "
            "outside the locked buffer around every 2024-2025 candidate corridor"
        ),
    }
    candidate_export = candidates.drop(columns="geometry").merge(
        match_table.groupby("pseudo_corridor_id", as_index=False).agg(
            matched_real_corridors=("real_corridor_id", "nunique"),
            best_match_distance=("match_distance", "min"),
        ),
        on="pseudo_corridor_id",
        how="left",
    )
    return placebo, candidate_export, screening


def _plot_placebo(
    placebo: pd.DataFrame, main_effect: float, path: Path
) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(placebo.effect_percent, bins=14, color="#93c5fd", edgecolor="#1d4ed8")
    ax.axvline(main_effect, color="#dc2626", linewidth=2.2, label="Real-corridor ATT")
    ax.axvline(placebo.effect_percent.median(), color="#1e3a8a", linestyle="--", label="Placebo median")
    ax.set_xlabel("Pipeline-level placebo ATT (%)")
    ax.set_ylabel("Replications")
    ax.set_title("Matched geography-placebo null distribution")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _write_report(
    summary: dict[str, Any], robustness: pd.DataFrame, loco: pd.DataFrame, path: Path
) -> None:
    display = robustness.copy()
    for column in ("effect_percent", "ci_low_percent", "ci_high_percent"):
        display[column] = display[column].map(
            lambda value: "—" if pd.isna(value) else f"{value:.1f}"
        )
    rows = "\n".join(
        f"| {row.milestone} | {row.specification} | {row.effect_percent} | "
        f"[{row.ci_low_percent}, {row.ci_high_percent}] | {row.treated_stations} | "
        f"{row.treated_corridors} | {row.inference} |"
        for row in display.itertuples(index=False)
    )
    influential = summary["influential_corridors"] or ["none at the locked 5-point threshold"]
    influential_specs = summary["influential_specifications"] or [
        "none at the locked point/interval rules"
    ]
    text = f"""# Phase 5 Robustness and Falsification

**Exit-gate decision:** `{summary['p5_decision']}`  
**Specification lock:** {summary['specification_locked_before_run']}  
**Primary Phase 4 estimate:** {summary['main_effect_percent']:.1f}% (95% CI {summary['main_ci_low_percent']:.1f}% to {summary['main_ci_high_percent']:.1f}%)

## Robustness registry

| Milestone | Specification | Effect (%) | 95% CI | Treated stations | Corridors | Inference |
|---|---|---:|---:|---:|---:|---|
{rows}

Point-only local and broad control-pool estimates deliberately do not report a confidence interval: those pools reuse unequal numbers of controls and are sensitivity comparators, not replacements for the locked matched design.

## What changed the estimate

- Locked influential-corridor rule: an absolute change of at least {summary['influential_threshold_pct_points']:.1f} percentage points or a sign reversal.
- Influential omissions: {', '.join(influential)}.
- Influential specifications: {', '.join(influential_specs)}.
- Leave-one-out range: {summary['loco_min_percent']:.1f}% to {summary['loco_max_percent']:.1f}%.
- Radius-specification range: {summary['radius_min_percent']:.1f}% to {summary['radius_max_percent']:.1f}%.

![Radius sensitivity](figures/phase5_radius_sensitivity.png)

![Leave one corridor out](figures/phase5_leave_one_corridor_out.png)

## Falsification

- Pre-treatment fake-date estimate: {summary['timing_placebo_effect_percent']:.1f}% (95% CI {summary['timing_placebo_ci_low_percent']:.1f}% to {summary['timing_placebo_ci_high_percent']:.1f}%). The fake post window maps only to real event months −6 through −2.
- Geography placebo: {summary['geography_replications']} valid replications from {summary['geography_attempts']} draws, fixed seed {summary['geography_seed']}. The null median is {summary['geography_median_percent']:.1f}% and its central 90% interval is [{summary['geography_p05_percent']:.1f}%, {summary['geography_p95_percent']:.1f}%]. The two-sided empirical tail probability for the real estimate is {summary['geography_empirical_pvalue']:.3f}.
- The pseudo-corridor screen uses official non-protected bike-route segments, removes any street name that also contains a protected segment, and excludes geometry within {summary['geography_real_buffer_m']:.0f} m of every corridor in the locked 2024–2025 candidate inventory. This inventory is the available concurrent-project proxy, not a complete registry of all city construction.

![Geography placebo](figures/phase5_geography_placebo.png)

## Interpretation

{summary['interpretation']}

This phase does not erase the Phase 3 pre-trend warning, sparse cohorts, medium-confidence timing, or the fact that the outcome is Divvy trip starts rather than total cycling. It tests how much the Phase 4 conclusion moves under the pre-registered alternatives and reports the failures as limitations rather than selecting a favorable specification.
"""
    path.write_text(text, encoding="utf-8")


def run_robustness() -> dict[str, Any]:
    config = load_config()
    raw = _raw_config()
    phase4 = raw["phase4"]
    phase5 = raw["phase5"]
    paths = _paths()
    station_master, station_panel, inventory, corridor_geo = load_sources(config)
    assignment = pd.read_parquet(config.paths["station_assignment"])
    eligible = pd.read_parquet(config.paths["control_cohort_eligibility"])
    panel = pd.read_parquet(config.paths["analysis_panel"])
    matches = pd.read_csv(paths["phase3_matches"], dtype={"first_post_month": str})
    pair_scores = build_pair_scores(panel, assignment, matches, phase4)
    main = _pair_result(pair_scores)
    treated = assignment[assignment.analysis_role.eq("primary_treated")]
    rows: list[dict[str, Any]] = []

    for spec in phase5["radius_specs"]:
        variant = replace(
            config,
            treated_radius_m=float(spec["treated_radius_m"]),
            donut_outer_m=float(spec["donut_outer_m"]),
        )
        ratio = int(raw["phase3"]["matching_controls_per_treated"])
        try:
            a, _, p, m = _build_real_matches(
                variant, raw, station_master, station_panel, inventory, corridor_geo
            )
        except ValueError as error:
            if "Not enough cohort-local controls" not in str(error):
                raise
            ratio = int(phase5["radius_matching_ratio_fallback"])
            a, _, p, m = _build_real_matches(
                variant,
                raw,
                station_master,
                station_panel,
                inventory,
                corridor_geo,
                ratio,
            )
        scores = build_pair_scores(p, a, m, phase4)
        result = _pair_result(scores)
        t = a[a.analysis_role.eq("primary_treated")]
        rows.append(
            _row(
                "M5.1 radius",
                f"{spec['treated_radius_m']}m treated / {spec['donut_outer_m']}m donut",
                result,
                t.station_id.nunique(),
                t.assigned_primary_corridor.nunique(),
                m.control_station_id.nunique(),
                notes=f"{ratio}:1 pre-period matching within cohort-local pool",
            )
        )

    rows.append(
        _row(
            "M5.2 controls",
            "pre-period matched (primary)",
            main,
            treated.station_id.nunique(),
            treated.assigned_primary_corridor.nunique(),
            matches.control_station_id.nunique(),
        )
    )
    for pool in ("cohort_local", "broad"):
        result, controls = _pool_point_result(
            panel,
            assignment,
            eligible,
            pool,
            phase4,
            config.local_control_outer_m,
            config.project_crs,
        )
        rows.append(
            _row(
                "M5.2 controls",
                pool.replace("_", " "),
                result,
                treated.station_id.nunique(),
                treated.assigned_primary_corridor.nunique(),
                controls,
                "point estimate only",
                "unequal reusable control pool",
            )
        )

    post_pair = pair_scores[pair_scores.event_time.ge(0)].groupby(
        [
            "first_post_month",
            "treated_station_id",
            "control_station_id",
            "corridor_cluster",
        ],
        as_index=False,
    )[["effect_count", "treated_observed"]].mean()
    loco_rows = []
    threshold = float(phase5["influential_corridor_change_pct_points"])
    for corridor in sorted(post_pair.corridor_cluster.unique()):
        subset = post_pair[post_pair.corridor_cluster.ne(corridor)]
        result = _percent_from_pair_values(subset)
        change = float(result["effect_percent"] - main["effect_percent"])
        loco_rows.append(
            {
                "omitted_corridor": corridor,
                **result,
                "change_from_main_pct_points": change,
                "sign_reversal": bool(
                    np.sign(result["effect_percent"]) != np.sign(main["effect_percent"])
                ),
                "influential": bool(
                    abs(change) >= threshold
                    or np.sign(result["effect_percent"])
                    != np.sign(main["effect_percent"])
                ),
                "treated_stations_remaining": int(subset.treated_station_id.nunique()),
            }
        )
    loco = pd.DataFrame(loco_rows)

    for post_start in phase5["construction_post_starts"]:
        result = _pair_result(pair_scores, int(post_start))
        rows.append(
            _row(
                "M5.4 construction window",
                f"post starts at event +{post_start}",
                result,
                treated.station_id.nunique(),
                treated.assigned_primary_corridor.nunique(),
                matches.control_station_id.nunique(),
            )
        )

    new_ids = set(
        treated.loc[treated.treatment_variant.eq("new_protected"), "station_id"]
    )
    new_matches = matches[matches.treated_station_id.isin(new_ids)]
    new_scores = build_pair_scores(panel, assignment, new_matches, phase4)
    new_result = _pair_result(new_scores)
    new_corridors = treated.loc[
        treated.station_id.isin(new_ids), "assigned_primary_corridor"
    ].nunique()
    rows.append(
        _row(
            "M5.5 treatment variant",
            "new protected only",
            new_result,
            len(new_ids),
            new_corridors,
            new_matches.control_station_id.nunique(),
        )
    )

    for outcome in ("member_trips", "casual_trips"):
        result = _pair_result(
            build_pair_scores(panel, assignment, matches, phase4, outcome)
        )
        rows.append(
            _row(
                "M5.6 outcome",
                outcome.replace("_", " "),
                result,
                treated.station_id.nunique(),
                treated.assigned_primary_corridor.nunique(),
                matches.control_station_id.nunique(),
            )
        )

    timing_corridors = set(phase4["conservative_timing_corridors"])
    for shift in phase5["timing_shifts_months"]:
        scores = _shifted_pair_scores(
            panel,
            assignment,
            matches,
            int(shift),
            11,
            timing_corridors,
        )
        result = _pair_result(scores)
        rows.append(
            _row(
                "M5.4 timing sensitivity",
                f"conservative dates shifted {int(shift):+d} month",
                result,
                treated.station_id.nunique(),
                treated.assigned_primary_corridor.nunique(),
                matches.control_station_id.nunique(),
            )
        )

    placebo_scores = _shifted_pair_scores(
        panel,
        assignment,
        matches,
        int(phase5["timing_placebo_shift_months"]),
        int(phase5["timing_placebo_post_end"]),
    )
    timing_placebo = _pair_result(placebo_scores)
    rows.append(
        _row(
            "M5.7 timing placebo",
            "fake first-post 6 months early; fake events 0..4",
            timing_placebo,
            treated.station_id.nunique(),
            treated.assigned_primary_corridor.nunique(),
            matches.control_station_id.nunique(),
        )
    )

    robustness = pd.DataFrame(rows)
    placebo, candidate_export, geo_screen = _geography_placebos(
        config,
        raw,
        station_master,
        station_panel,
        assignment,
        inventory,
        corridor_geo,
    )
    empirical_p = float(
        (1 + placebo.effect_percent.abs().ge(abs(main["effect_percent"])).sum())
        / (1 + len(placebo))
    )
    quantiles = placebo.effect_percent.quantile([0.05, 0.5, 0.95])
    influential = loco.loc[loco.influential, "omitted_corridor"].tolist()
    radius = robustness[robustness.milestone.eq("M5.1 radius")]
    effect_specs = robustness[
        ~robustness.milestone.eq("M5.7 timing placebo")
        & ~robustness.specification.isin(
            [
                "300m treated / 800m donut",
                "pre-period matched (primary)",
                "post starts at event +0",
                "conservative dates shifted +0 month",
            ]
        )
    ].copy()
    main_includes_zero = main["ci_low_percent"] <= 0 <= main["ci_high_percent"]
    point_influential = effect_specs.effect_percent.sub(main["effect_percent"]).abs().ge(
        threshold
    ) | np.sign(effect_specs.effect_percent).ne(np.sign(main["effect_percent"]))
    interval_influential = (
        main_includes_zero
        & effect_specs.ci_low_percent.notna()
        & (
            effect_specs.ci_low_percent.gt(0)
            | effect_specs.ci_high_percent.lt(0)
        )
    )
    effect_specs["influential"] = point_influential | interval_influential
    influential_specs = (
        effect_specs.loc[effect_specs.influential, "specification"].sort_values().tolist()
    )
    placebo_clear = bool(empirical_p <= 0.10)
    timing_clear = bool(
        timing_placebo["ci_low_percent"] <= 0 <= timing_placebo["ci_high_percent"]
    )
    p5_decision = "PASS" if placebo_clear and timing_clear else "PASS WITH LIMITATIONS"
    if placebo_clear and timing_clear:
        interpretation = (
            "The central conclusion is stable: the data do not establish an increase in "
            "nearby Divvy trip starts, and the negative point estimate is not reproduced "
            "by either locked falsification design."
        )
    else:
        failed = []
        if not timing_clear:
            failed.append("the fake-date estimate excludes zero")
        if not placebo_clear:
            failed.append("the real estimate is not in the locked 10% geography-placebo tail")
        interpretation = (
            "The main estimate still does not establish an increase, but robustness cannot "
            "upgrade that result to a clean causal claim because " + " and ".join(failed) + "."
        )
    summary = {
        "p5_decision": p5_decision,
        "specification_locked_before_run": phase5["specification_locked_before_run"],
        "main_effect_percent": main["effect_percent"],
        "main_ci_low_percent": main["ci_low_percent"],
        "main_ci_high_percent": main["ci_high_percent"],
        "robustness_rows": len(robustness),
        "radius_min_percent": float(radius.effect_percent.min()),
        "radius_max_percent": float(radius.effect_percent.max()),
        "loco_min_percent": float(loco.effect_percent.min()),
        "loco_max_percent": float(loco.effect_percent.max()),
        "influential_threshold_pct_points": threshold,
        "influential_corridors": influential,
        "influential_specifications": influential_specs,
        "timing_placebo_effect_percent": timing_placebo["effect_percent"],
        "timing_placebo_ci_low_percent": timing_placebo["ci_low_percent"],
        "timing_placebo_ci_high_percent": timing_placebo["ci_high_percent"],
        "timing_placebo_clear": timing_clear,
        "geography_replications": len(placebo),
        "geography_attempts": geo_screen["attempts"],
        "geography_seed": int(phase5["geography_placebo"]["seed"]),
        "geography_candidate_components": geo_screen["candidate_components"],
        "geography_candidate_streets": geo_screen["candidate_streets"],
        "geography_median_percent": float(quantiles.loc[0.5]),
        "geography_p05_percent": float(quantiles.loc[0.05]),
        "geography_p95_percent": float(quantiles.loc[0.95]),
        "geography_empirical_pvalue": empirical_p,
        "geography_tail_clear": placebo_clear,
        "geography_real_buffer_m": float(
            phase5["geography_placebo"]["real_corridor_buffer_m"]
        ),
        "geography_screen": geo_screen["screen"],
        "interpretation": interpretation,
    }

    for key in (
        "phase5_robustness",
        "phase5_loco",
        "phase5_geography_placebo",
        "phase5_geography_candidates",
        "phase5_summary",
        "phase5_report",
    ):
        paths[key].parent.mkdir(parents=True, exist_ok=True)
    robustness.to_csv(paths["phase5_robustness"], index=False, float_format="%.6f")
    loco.to_csv(paths["phase5_loco"], index=False, float_format="%.6f")
    placebo.to_csv(
        paths["phase5_geography_placebo"], index=False, float_format="%.6f"
    )
    candidate_export.to_csv(
        paths["phase5_geography_candidates"], index=False, float_format="%.6f"
    )
    paths["phase5_summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    _plot_radius(robustness, ROOT / "reports/figures/phase5_radius_sensitivity.png")
    _plot_loco(
        loco,
        main["effect_percent"],
        ROOT / "reports/figures/phase5_leave_one_corridor_out.png",
    )
    _plot_placebo(
        placebo,
        main["effect_percent"],
        ROOT / "reports/figures/phase5_geography_placebo.png",
    )
    _write_report(summary, robustness, loco, paths["phase5_report"])
    return summary


if __name__ == "__main__":
    print(json.dumps(run_robustness(), indent=2, sort_keys=True))
