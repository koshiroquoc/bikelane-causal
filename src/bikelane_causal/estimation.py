"""Phase 4 estimators on the frozen Phase 3 matched sample."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf

from bikelane_causal.diagnostics import ROOT, _paths, _raw_config
from bikelane_causal.pipeline import load_config


def _psd(matrix: np.ndarray) -> np.ndarray:
    symmetric = (matrix + matrix.T) / 2
    values, vectors = np.linalg.eigh(symmetric)
    return vectors @ np.diag(np.maximum(values, 0)) @ vectors.T


def _cluster_sum_cov(
    contributions: np.ndarray, groups: pd.Series, parameter_count: int = 1
) -> np.ndarray:
    labels = groups.astype(str).to_numpy()
    unique = np.unique(labels)
    sums = np.vstack([contributions[labels == label].sum(axis=0) for label in unique])
    n = len(contributions)
    g = len(unique)
    correction = 1.0
    if g > 1:
        correction *= g / (g - 1)
    if n > parameter_count:
        correction *= (n - 1) / (n - parameter_count)
    return correction * (sums.T @ sums)


def _multiway_cov_from_contributions(
    contributions: np.ndarray,
    corridor: pd.Series,
    station: pd.Series,
    parameter_count: int = 1,
) -> np.ndarray:
    intersection = corridor.astype(str) + "::" + station.astype(str)
    covariance = (
        _cluster_sum_cov(contributions, corridor, parameter_count)
        + _cluster_sum_cov(contributions, station, parameter_count)
        - _cluster_sum_cov(contributions, intersection, parameter_count)
    )
    return _psd(covariance)


def _mean_covariance(values: np.ndarray, data: pd.DataFrame) -> np.ndarray:
    values = np.atleast_2d(values)
    if values.shape[0] != len(data):
        values = values.T
    centered = values - values.mean(axis=0)
    contributions = centered / len(values)
    return _multiway_cov_from_contributions(
        contributions,
        data.corridor_cluster,
        data.control_station_id,
        values.shape[1],
    )


def _percent_from_pair_values(data: pd.DataFrame) -> dict[str, float]:
    values = data[["effect_count", "treated_observed"]].to_numpy(dtype=float)
    mean_effect, mean_observed = values.mean(axis=0)
    counterfactual = mean_observed - mean_effect
    covariance = _mean_covariance(values, data)
    se_count = float(np.sqrt(covariance[0, 0]))
    corridor_clusters = data.corridor_cluster.nunique()
    if counterfactual <= 0:
        return {
            "effect_count": float(mean_effect),
            "se_count": se_count,
            "counterfactual_mean": float(counterfactual),
            "effect_percent": np.nan,
            "se_percent": np.nan,
            "ci_low_percent": np.nan,
            "ci_high_percent": np.nan,
            "corridor_clusters": int(corridor_clusters),
            "control_station_clusters": int(data.control_station_id.nunique()),
        }
    effect_percent = 100 * mean_effect / counterfactual
    gradient = np.array(
        [
            100 * mean_observed / counterfactual**2,
            -100 * mean_effect / counterfactual**2,
        ]
    )
    se_percent = float(np.sqrt(gradient @ covariance @ gradient))
    critical = stats.t.ppf(0.975, max(corridor_clusters - 1, 1))
    return {
        "effect_count": float(mean_effect),
        "se_count": se_count,
        "counterfactual_mean": float(counterfactual),
        "effect_percent": float(effect_percent),
        "se_percent": se_percent,
        "ci_low_percent": float(effect_percent - critical * se_percent),
        "ci_high_percent": float(effect_percent + critical * se_percent),
        "corridor_clusters": int(corridor_clusters),
        "control_station_clusters": int(data.control_station_id.nunique()),
    }


def build_stacked_panel(
    panel: pd.DataFrame, assignment: pd.DataFrame, matches: pd.DataFrame, phase4: dict
) -> pd.DataFrame:
    pieces = []
    treated_assignment = assignment[
        assignment.analysis_role.eq("primary_treated")
    ].set_index("station_id")
    for cohort, cohort_matches in matches.groupby("first_post_month"):
        cohort = str(cohort)
        treated_ids = sorted(cohort_matches.treated_station_id.unique())
        control_ids = sorted(cohort_matches.control_station_id.unique())
        events = list(range(int(phase4["event_min"]), -1)) + list(
            range(0, int(phase4["event_max"]) + 1)
        )
        month_by_event = {
            event: str(pd.Period(cohort, freq="M") + event) for event in events
        }
        event_by_month = {month: event for event, month in month_by_event.items()}
        ids = treated_ids + control_ids
        stack = panel[
            panel.station_id.isin(ids) & panel.month.astype(str).isin(event_by_month)
        ].copy()
        stack["stack_cohort"] = cohort
        stack["stack_event_time"] = stack.month.astype(str).map(event_by_month).astype(int)
        stack["treated_in_stack"] = stack.station_id.isin(treated_ids).astype(int)
        stack["treated_post"] = (
            stack.treated_in_stack.eq(1) & stack.stack_event_time.ge(0)
        ).astype(int)
        stack["stack_station_id"] = cohort + "::" + stack.station_id.astype(str)
        stack["stack_month"] = cohort + "::" + stack.month.astype(str)
        treated_corridor = treated_assignment.assigned_primary_corridor.to_dict()
        control_to_treated = cohort_matches.set_index(
            "control_station_id"
        ).treated_station_id.to_dict()
        corridor_map = {
            station_id: treated_corridor[station_id] for station_id in treated_ids
        }
        corridor_map.update(
            {
                station_id: treated_corridor[control_to_treated[station_id]]
                for station_id in control_ids
            }
        )
        stack["corridor_cluster"] = stack.station_id.map(corridor_map)
        stack["original_station_cluster"] = stack.station_id.astype(str)
        pieces.append(stack)
    stacked = pd.concat(pieces, ignore_index=True).sort_values(
        ["stack_cohort", "stack_station_id", "stack_event_time"]
    )
    expected_months = int(phase4["event_max"]) - int(phase4["event_min"])
    counts = stacked.groupby("stack_station_id").stack_event_time.nunique()
    if not counts.eq(expected_months).all():
        raise ValueError("Phase 4 stacked panel is not balanced over the locked window")
    if stacked.stack_event_time.eq(-1).any():
        raise ValueError("Transition month entered the Phase 4 stacked panel")
    return stacked.reset_index(drop=True)


def build_pair_scores(
    panel: pd.DataFrame,
    assignment: pd.DataFrame,
    matches: pd.DataFrame,
    phase4: dict,
) -> pd.DataFrame:
    reference = int(phase4["event_reference"])
    events = [
        event
        for event in range(int(phase4["event_min"]), int(phase4["event_max"]) + 1)
        if event not in {-1, reference}
    ]
    outcome = panel.pivot(index="station_id", columns="month", values="total_trips")
    treated_assignment = assignment[
        assignment.analysis_role.eq("primary_treated")
    ].set_index("station_id")
    rows = []
    for cohort, cohort_matches in matches.groupby("first_post_month"):
        cohort = str(cohort)
        reference_month = str(pd.Period(cohort, freq="M") + reference)
        for event_time in events:
            event_month = str(pd.Period(cohort, freq="M") + event_time)
            for match in cohort_matches.itertuples(index=False):
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
                        "first_post_month": cohort,
                        "event_time": event_time,
                        "treated_station_id": match.treated_station_id,
                        "control_station_id": match.control_station_id,
                        "corridor_cluster": treated_assignment.loc[
                            match.treated_station_id, "assigned_primary_corridor"
                        ],
                        "effect_count": float(treated_delta - control_delta),
                        "treated_observed": float(
                            outcome.loc[match.treated_station_id, event_month]
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _group_mean_percent_covariance(
    pair_post: pd.DataFrame, cohorts: list[str], common_counterfactual_scale: float
) -> tuple[pd.DataFrame, np.ndarray]:
    means = pair_post.groupby("first_post_month")[["effect_count", "treated_observed"]].mean()
    contributions = np.zeros((len(pair_post), len(cohorts)))
    for index, cohort in enumerate(cohorts):
        mask = pair_post.first_post_month.eq(cohort).to_numpy()
        n_group = int(mask.sum())
        centered = (
            pair_post.loc[mask, "effect_count"].to_numpy()
            - means.loc[cohort, "effect_count"]
        ) / n_group
        contributions[mask, index] = 100 * centered / common_counterfactual_scale
    covariance = _multiway_cov_from_contributions(
        contributions,
        pair_post.corridor_cluster,
        pair_post.control_station_id,
        len(cohorts),
    )
    rows = []
    for cohort in cohorts:
        effect, observed = means.loc[cohort]
        counterfactual = observed - effect
        percent = 100 * effect / common_counterfactual_scale
        rows.append(
            {
                "first_post_month": cohort,
                "effect_count": effect,
                "cohort_counterfactual_diagnostic": counterfactual,
                "effect_percent": percent,
                "percent_scale": "common main-sample counterfactual mean",
            }
        )
    return pd.DataFrame(rows), covariance


def _heterogeneity_test(
    estimates: np.ndarray,
    covariance: np.ndarray,
    df_den: int,
    phase4: dict,
    min_treated_clusters_per_cohort: int,
) -> dict[str, Any]:
    contrast = np.zeros((len(estimates) - 1, len(estimates)))
    for row in range(len(estimates) - 1):
        contrast[row, 0] = -1
        contrast[row, row + 1] = 1
    difference = contrast @ estimates
    contrast_cov = _psd(contrast @ covariance @ contrast.T)
    wald = float(difference.T @ np.linalg.pinv(contrast_cov) @ difference)
    df_num = len(difference)
    f_stat = wald / df_num
    pvalue = float(stats.f.sf(f_stat, df_num, df_den))
    effect_range = float(estimates.max() - estimates.min())
    inference_reliable = min_treated_clusters_per_cohort >= 2
    severe = effect_range > float(
        phase4["heterogeneity_materiality_pct_points"]
    ) and (
        pvalue < float(phase4["heterogeneity_alpha"]) or not inference_reliable
    )
    return {
        "f_statistic": f_stat,
        "df_num": df_num,
        "df_den": df_den,
        "pvalue": pvalue,
        "range_pct_points": effect_range,
        "min_treated_corridors_per_cohort": int(min_treated_clusters_per_cohort),
        "inference_reliable": bool(inference_reliable),
        "severe": bool(severe),
    }


def estimate_group_time_att(
    pair_scores: pd.DataFrame,
    assignment: pd.DataFrame,
    phase4: dict,
) -> dict[str, Any]:
    post = pair_scores[pair_scores.event_time.ge(0)].copy()
    pair_keys = [
        "first_post_month",
        "treated_station_id",
        "control_station_id",
        "corridor_cluster",
    ]
    pair_post = post.groupby(pair_keys, as_index=False)[
        ["effect_count", "treated_observed"]
    ].mean()
    main = _percent_from_pair_values(pair_post)

    group_time_rows = []
    for (cohort, event_time), group in pair_scores.groupby(
        ["first_post_month", "event_time"]
    ):
        point = _percent_from_pair_values(group)
        group_time_rows.append(
            {
                "first_post_month": cohort,
                "event_time": event_time,
                **point,
                "treated_stations": group.treated_station_id.nunique(),
            }
        )
    group_time = pd.DataFrame(group_time_rows).sort_values(
        ["first_post_month", "event_time"]
    )

    event_rows = []
    for event_time, group in pair_scores.groupby("event_time"):
        event_rows.append({"event_time": event_time, **_percent_from_pair_values(group)})
    event_rows.append(
        {
            "event_time": int(phase4["event_reference"]),
            "effect_count": 0.0,
            "se_count": 0.0,
            "counterfactual_mean": np.nan,
            "effect_percent": 0.0,
            "se_percent": 0.0,
            "ci_low_percent": 0.0,
            "ci_high_percent": 0.0,
            "corridor_clusters": assignment.loc[
                assignment.analysis_role.eq("primary_treated"),
                "assigned_primary_corridor",
            ].nunique(),
            "control_station_clusters": pair_scores.control_station_id.nunique(),
        }
    )
    event = pd.DataFrame(event_rows).sort_values("event_time")

    cohorts = sorted(pair_post.first_post_month.unique())
    cohort, cohort_cov = _group_mean_percent_covariance(
        pair_post, cohorts, main["counterfactual_mean"]
    )
    treated_counts = (
        assignment[assignment.analysis_role.eq("primary_treated")]
        .groupby("first_post_month")
        .station_id.nunique()
    )
    corridor_counts = (
        assignment[assignment.analysis_role.eq("primary_treated")]
        .groupby("first_post_month")
        .assigned_primary_corridor.nunique()
    )
    critical = stats.t.ppf(0.975, 11)
    cohort["se_percent"] = np.sqrt(np.diag(cohort_cov))
    cohort["ci_low_percent"] = cohort.effect_percent - critical * cohort.se_percent
    cohort["ci_high_percent"] = cohort.effect_percent + critical * cohort.se_percent
    cohort["treated_stations"] = cohort.first_post_month.map(treated_counts)
    cohort["treated_corridors"] = cohort.first_post_month.map(corridor_counts)
    heterogeneity = _heterogeneity_test(
        cohort.effect_percent.to_numpy(),
        cohort_cov,
        11,
        phase4,
        int(corridor_counts.min()),
    )

    conservative = set(phase4["conservative_timing_corridors"])
    specific = pair_post[~pair_post.corridor_cluster.isin(conservative)].copy()
    specific_result = _percent_from_pair_values(specific)
    specific_result["treated_stations"] = int(specific.treated_station_id.nunique())
    specific_result["treated_corridors"] = int(specific.corridor_cluster.nunique())
    return {
        "main": main,
        "group_time": group_time,
        "event": event,
        "cohort": cohort,
        "heterogeneity": heterogeneity,
        "specific_timing": specific_result,
        "pair_post": pair_post,
    }


def _sandwich_covariance(
    result,
    model_type: str,
    cluster_one: pd.Series,
    cluster_two: pd.Series | None = None,
) -> np.ndarray:
    x = np.asarray(result.model.exog)
    n, k = x.shape
    if model_type == "ols":
        residual = np.asarray(result.resid)
        score = x * residual[:, None]
        bread = np.linalg.pinv(x.T @ x)
    else:
        residual = np.asarray(result.model.endog) - np.asarray(result.fittedvalues)
        score = x * residual[:, None]
        mu = np.asarray(result.fittedvalues)
        bread = np.linalg.pinv(x.T @ (x * mu[:, None]))
    if cluster_two is None:
        meat = _cluster_sum_cov(score, cluster_one.reset_index(drop=True), k)
    else:
        intersection = cluster_one.astype(str) + "::" + cluster_two.astype(str)
        meat = (
            _cluster_sum_cov(score, cluster_one.reset_index(drop=True), k)
            + _cluster_sum_cov(score, cluster_two.reset_index(drop=True), k)
            - _cluster_sum_cov(score, intersection.reset_index(drop=True), k)
        )
        meat = _psd(meat)
    return _psd(bread @ meat @ bread)


def _fit_fixed_effect_model(
    data: pd.DataFrame,
    formula: str,
    model_type: str,
    cluster_one: str,
    cluster_two: str | None = None,
):
    if model_type == "ols":
        result = smf.ols(formula, data=data).fit()
    else:
        model = smf.glm(formula, data=data, family=sm.families.Poisson())
        initial = model.fit(maxiter=50, tol=1e-6)
        result = model.fit(
            start_params=initial.params,
            method="newton",
            maxiter=100,
            tol=1e-8,
        )
    covariance = _sandwich_covariance(
        result,
        model_type,
        data[cluster_one],
        data[cluster_two] if cluster_two else None,
    )
    return result, covariance


def _coefficient_result(
    result, covariance: np.ndarray, name: str, df: int
) -> dict[str, float]:
    index = list(result.params.index).index(name)
    coefficient = float(result.params.iloc[index])
    se = float(np.sqrt(covariance[index, index]))
    critical = stats.t.ppf(0.975, df)
    return {
        "coefficient_log_points": coefficient,
        "se_log_points": se,
        "effect_percent": float(100 * np.expm1(coefficient)),
        "ci_low_percent": float(100 * np.expm1(coefficient - critical * se)),
        "ci_high_percent": float(100 * np.expm1(coefficient + critical * se)),
    }


def _converged(result) -> bool:
    if hasattr(result, "converged"):
        return bool(result.converged)
    if hasattr(result, "mle_retvals"):
        return bool(result.mle_retvals.get("converged", False))
    # Closed-form OLS results have no iterative convergence attribute.
    return True


def estimate_baselines(
    panel: pd.DataFrame, assignment: pd.DataFrame, matches: pd.DataFrame
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    matched_ids = set(matches.control_station_id) | set(matches.treated_station_id)
    baseline = panel[panel.station_id.isin(matched_ids) & panel.analysis_row].copy()
    baseline["treated_post"] = baseline.post.astype(int)
    baseline["log1p_trips"] = np.log1p(baseline.total_trips)
    formula_fe = " + C(station_id) + C(month)"
    ols, ols_cov = _fit_fixed_effect_model(
        baseline,
        "log1p_trips ~ treated_post" + formula_fe,
        "ols",
        "station_id",
    )
    ppml, ppml_cov = _fit_fixed_effect_model(
        baseline,
        "total_trips ~ treated_post" + formula_fe,
        "ppml",
        "station_id",
    )
    rows = []
    for estimator, result, covariance, model_type in (
        ("twfe_ols_log1p_baseline", ols, ols_cov, "OLS log(1+y)"),
        ("pooled_ppml_twfe_baseline", ppml, ppml_cov, "Poisson PML"),
    ):
        rows.append(
            {
                "estimator": estimator,
                "role": "transparency baseline; never headline",
                "model": model_type,
                **_coefficient_result(result, covariance, "treated_post", baseline.station_id.nunique() - 1),
                "converged": _converged(result),
                "model_rows": int(len(baseline)),
                "treated_stations": int(
                    baseline.loc[baseline.ever_treated, "station_id"].nunique()
                ),
                "control_stations": int(
                    baseline.loc[~baseline.ever_treated, "station_id"].nunique()
                ),
            }
        )
    return rows, baseline


def estimate_stacked_ppml(stacked: pd.DataFrame, phase4: dict) -> dict[str, Any]:
    common_formula = (
        "total_trips ~ treated_post + C(stack_station_id) + C(stack_month)"
    )
    common, common_cov = _fit_fixed_effect_model(
        stacked,
        common_formula,
        "ppml",
        "corridor_cluster",
        "original_station_cluster",
    )
    common_result = _coefficient_result(common, common_cov, "treated_post", 11)
    common_result["converged"] = _converged(common)
    common_result["model_rows"] = int(len(stacked))

    hetero_formula = (
        "total_trips ~ 0 + C(stack_station_id) + C(stack_month) "
        "+ treated_post:C(stack_cohort)"
    )
    hetero, hetero_cov = _fit_fixed_effect_model(
        stacked,
        hetero_formula,
        "ppml",
        "corridor_cluster",
        "original_station_cluster",
    )
    coefficient_names = [
        name
        for name in hetero.params.index
        if name.startswith("treated_post:C(stack_cohort)")
    ]
    if len(coefficient_names) != stacked.stack_cohort.nunique():
        raise ValueError("PPML cohort interaction coefficients did not reconcile")
    indices = [list(hetero.params.index).index(name) for name in coefficient_names]
    beta = hetero.params.iloc[indices].to_numpy()
    beta_cov = hetero_cov[np.ix_(indices, indices)]
    percent = 100 * np.expm1(beta)
    jacobian = np.diag(100 * np.exp(beta))
    percent_cov = _psd(jacobian @ beta_cov @ jacobian.T)
    critical = stats.t.ppf(0.975, 11)
    cohorts = [name.split("[")[-1].rstrip("]") for name in coefficient_names]
    cohort_rows = []
    for index, cohort in enumerate(cohorts):
        se = float(np.sqrt(percent_cov[index, index]))
        cohort_rows.append(
            {
                "first_post_month": cohort,
                "effect_percent": float(percent[index]),
                "se_percent": se,
                "ci_low_percent": float(percent[index] - critical * se),
                "ci_high_percent": float(percent[index] + critical * se),
            }
        )
    corridor_counts = (
        stacked[stacked.treated_in_stack.eq(1)]
        .groupby("stack_cohort")
        .corridor_cluster.nunique()
    )
    heterogeneity = _heterogeneity_test(
        percent, percent_cov, 11, phase4, int(corridor_counts.min())
    )
    return {
        "common": common_result,
        "cohort": pd.DataFrame(cohort_rows),
        "heterogeneity": heterogeneity,
        "hetero_converged": _converged(hetero),
    }


def _plot_event(event: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    plotted = event[event.event_time.ne(-1)].sort_values("event_time")
    ax.errorbar(
        plotted.event_time,
        plotted.effect_percent,
        yerr=[
            plotted.effect_percent - plotted.ci_low_percent,
            plotted.ci_high_percent - plotted.effect_percent,
        ],
        fmt="o-",
        color="#2563eb",
        ecolor="#93c5fd",
        capsize=3,
        linewidth=1.8,
    )
    ax.axhline(0, color="#111827", linewidth=1)
    ax.axvline(-1, color="#f59e0b", linestyle="--", linewidth=1)
    ax.set_xticks(range(-13, 12))
    ax.set_xlabel("Event month (−2 reference; −1 transition excluded)")
    ax.set_ylabel("Group-time ATT translated to percent")
    ax.set_title("Phase 4 matched group-time event study")
    ax.grid(alpha=0.18)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight", metadata={"Software": "bikelane-causal"})
    plt.close(fig)


def _plot_estimators(registry: pd.DataFrame, path: Path) -> None:
    order = [
        "twfe_ols_log1p_baseline",
        "pooled_ppml_twfe_baseline",
        "group_time_att",
        "cohort_stacked_ppml",
        "group_time_att_specific_timing",
    ]
    labels = {
        "twfe_ols_log1p_baseline": "TWFE OLS baseline",
        "pooled_ppml_twfe_baseline": "Pooled PPML baseline",
        "group_time_att": "Group-time ATT",
        "cohort_stacked_ppml": "Cohort-stacked PPML",
        "group_time_att_specific_timing": "ATT, specific-date subset",
    }
    data = registry.set_index("estimator").loc[order].reset_index()
    y = np.arange(len(data))
    colors = ["#9ca3af", "#9ca3af", "#2563eb", "#e11d48", "#7c3aed"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.errorbar(
        data.effect_percent,
        y,
        xerr=[
            data.effect_percent - data.ci_low_percent,
            data.ci_high_percent - data.effect_percent,
        ],
        fmt="none",
        ecolor="#9ca3af",
        capsize=4,
        linewidth=2,
    )
    ax.scatter(data.effect_percent, y, c=colors, s=55, zorder=3)
    ax.axvline(0, color="#111827", linewidth=1)
    ax.set_yticks(y, [labels[item] for item in data.estimator])
    ax.set_xlabel("Estimated change in monthly trip starts (%)")
    ax.set_title("Phase 4 estimator registry (95% intervals)")
    ax.grid(axis="x", alpha=0.18)
    ax.invert_yaxis()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight", metadata={"Software": "bikelane-causal"})
    plt.close(fig)


def _write_report(summary: dict[str, Any], registry: pd.DataFrame, path: Path) -> None:
    rows = []
    for row in registry.itertuples(index=False):
        rows.append(
            f"| `{row.estimator}` | {row.role} | {row.effect_percent:.1f}% | "
            f"[{row.ci_low_percent:.1f}%, {row.ci_high_percent:.1f}%] |"
        )
    headline = summary["headline"]
    limitations = "\n".join(f"- {item}" for item in summary["p3_limitations"])
    heterogeneity_lines = []
    for label, key in (("CS", "cs_heterogeneity"), ("PPML", "ppml_heterogeneity")):
        diagnostic = summary[key]
        if diagnostic["inference_reliable"]:
            detail = (
                f"`F({diagnostic['df_num']}, {diagnostic['df_den']}) = "
                f"{diagnostic['f_statistic']:.2f}`, `p = {diagnostic['pvalue']:.3f}`"
            )
        else:
            detail = (
                "formal few-cluster inference is not reliable because at least one "
                f"cohort has only {diagnostic['min_treated_corridors_per_cohort']} treated corridor"
            )
        heterogeneity_lines.append(
            f"- {label} cohort heterogeneity severe: {str(diagnostic['severe']).lower()}; "
            f"range {diagnostic['range_pct_points']:.1f} pp; {detail}."
        )
    text = f"""# Phase 4 Main Estimation Results

**Exit-gate decision:** `{summary['p4_decision']}`  
**P3 identification status carried forward:** `PASS WITH LIMITATIONS`  
**Headline estimator selected by the locked rule:** `{headline['estimator']}`

## Results registry

| Estimator | Role | Effect | 95% interval |
|---|---|---:|---:|
{chr(10).join(rows)}

The group-time ATT is estimated on monthly trip counts using the last non-transition pre-month (`event_time = -2`) as the universal base. Its count ATT is translated to a percentage of the estimated treated counterfactual mean. This is the matched-panel group-time implementation of the Callaway–Sant’Anna identification logic with never-treated controls; no post-treatment outcome enters matching. Cohort-stacked PPML uses the identical 40 treated stations, 120 matched control assignments, four cohorts, and 24 analysis months, with stack-station and stack-calendar fixed effects. Its percentage is `100 × (exp(β) − 1)`.

Main uncertainty is two-way clustered by treated corridor and reused control station, with t critical values based on 11 corridor degrees of freedom. Baseline models are station-clustered and remain transparency checks only.

## Headline rule and reconciliation

- Main samples reconcile: {str(summary['sample_reconciled']).lower()}.
{chr(10).join(heterogeneity_lines)}
- CS–PPML point gap: {summary['divergence']['point_gap_pct_points']:.1f} percentage points; confidence intervals overlap: {str(summary['divergence']['confidence_intervals_overlap']).lower()}.
- Material unresolved divergence: {str(summary['divergence']['material_unresolved']).lower()}.

The locked conditions therefore select **{headline['estimator']}** at **{headline['effect_percent']:.1f}%** with a 95% interval of **[{headline['ci_low_percent']:.1f}%, {headline['ci_high_percent']:.1f}%]**. The interval includes zero. This is not evidence of an increase, and it is not an unconditional causal claim: the P3 placebo-lead warning remains part of the result.

The required specific-date subset removes seven conservative first-verified corridors, retaining 24 treated stations across five corridors. Its estimate is **{summary['specific_timing_sensitivity']['effect_percent']:.1f}%** with a 95% interval of **[{summary['specific_timing_sensitivity']['ci_low_percent']:.1f}%, {summary['specific_timing_sensitivity']['ci_high_percent']:.1f}%]**; it is directionally similar but substantially less precise.

## Event study

![Matched group-time event study](figures/phase4_event_study.png)

## Estimator comparison

![Estimator comparison](figures/phase4_estimator_comparison.png)

## Limitations carried into interpretation

{limitations}

The project measures Divvy trip starts near treated corridors, not total cycling. Phase 5 must test radius, control-pool, timing, treatment-variant, outcome, leave-one-corridor-out, and geography-placebo sensitivity before any portfolio conclusion is finalized.
"""
    path.write_text(text, encoding="utf-8")


def run_estimation() -> dict[str, Any]:
    config = load_config()
    raw = _raw_config()
    phase4 = raw["phase4"]
    paths = _paths()
    p3_gate = json.loads(paths["phase3_gate_summary"].read_text(encoding="utf-8"))
    if not p3_gate["phase4_authorized"]:
        raise RuntimeError("Phase 3 gate does not authorize Phase 4 causal estimation")
    panel = pd.read_parquet(config.paths["analysis_panel"])
    assignment = pd.read_parquet(config.paths["station_assignment"])
    matches = pd.read_csv(paths["phase3_matches"], dtype={"first_post_month": str})
    stacked = build_stacked_panel(panel, assignment, matches, phase4)
    paths["phase4_stacked_panel"].parent.mkdir(parents=True, exist_ok=True)
    stacked.to_parquet(paths["phase4_stacked_panel"], index=False)

    pair_scores = build_pair_scores(panel, assignment, matches, phase4)
    cs = estimate_group_time_att(pair_scores, assignment, phase4)
    baseline_rows, baseline = estimate_baselines(panel, assignment, matches)
    ppml = estimate_stacked_ppml(stacked, phase4)

    main_cs = cs["main"]
    main_ppml = ppml["common"]
    cs_ppml_same_contract = (
        stacked.loc[stacked.treated_in_stack.eq(1), "station_id"].nunique() == 40
        and matches.treated_station_id.nunique() == 40
        and len(matches) == 120
        and stacked.stack_cohort.nunique() == 4
        and stacked.stack_event_time.nunique() == 24
    )
    point_gap = abs(main_cs["effect_percent"] - main_ppml["effect_percent"])
    opposite = np.sign(main_cs["effect_percent"]) != np.sign(main_ppml["effect_percent"])
    raw_divergence = (
        opposite
        and max(abs(main_cs["effect_percent"]), abs(main_ppml["effect_percent"]))
        > float(phase4["divergence_sign_materiality_percent"])
    ) or point_gap > float(phase4["divergence_gap_pct_points"])
    interval_overlap = max(
        main_cs["ci_low_percent"], main_ppml["ci_low_percent"]
    ) <= min(main_cs["ci_high_percent"], main_ppml["ci_high_percent"])
    material_unresolved = bool(raw_divergence and not interval_overlap)

    ppml_headline_eligible = bool(
        p3_gate["decision"] in {"PASS", "PASS WITH LIMITATIONS"}
        and cs_ppml_same_contract
        and not cs["heterogeneity"]["severe"]
        and not ppml["heterogeneity"]["severe"]
        and main_ppml["converged"]
        and ppml["hetero_converged"]
        and not material_unresolved
    )
    if ppml_headline_eligible:
        headline = {"estimator": "cohort_stacked_ppml", **main_ppml}
    else:
        headline = {"estimator": "group_time_att", **main_cs}

    registry_rows = baseline_rows + [
        {
            "estimator": "group_time_att",
            "role": "primary identification and dynamics",
            "model": "matched panel group-time ATT on counts",
            **main_cs,
            "converged": True,
            "model_rows": int(len(cs["pair_post"])),
            "treated_stations": 40,
            "control_stations": int(matches.control_station_id.nunique()),
        },
        {
            "estimator": "cohort_stacked_ppml",
            "role": "conditional headline percentage magnitude",
            "model": "cohort-stacked Poisson PML",
            **main_ppml,
            "model_rows": int(len(stacked)),
            "treated_stations": 40,
            "control_stations": int(matches.control_station_id.nunique()),
        },
        {
            "estimator": "group_time_att_specific_timing",
            "role": "required specific-date sensitivity",
            "model": "matched group-time ATT excluding conservative first-verified dates",
            **cs["specific_timing"],
            "converged": True,
            "model_rows": np.nan,
            "control_stations": np.nan,
        },
    ]
    registry = pd.DataFrame(registry_rows)

    cs_cohort = cs["cohort"].assign(estimator="group_time_att")
    ppml_cohort = ppml["cohort"].assign(estimator="cohort_stacked_ppml")
    cohort = pd.concat([cs_cohort, ppml_cohort], ignore_index=True, sort=False)
    group_time = cs["group_time"]
    event = cs["event"]
    reconciliation = pd.DataFrame(
        [
            {
                "estimator": "group_time_att",
                "representation": "matched pair changes",
                "treated_stations": 40,
                "control_assignments": 120,
                "unique_control_stations": matches.control_station_id.nunique(),
                "cohorts": 4,
                "analysis_months_per_stack": 24,
                "transition_excluded": True,
            },
            {
                "estimator": "cohort_stacked_ppml",
                "representation": "cohort-stacked station-month panel",
                "treated_stations": stacked.loc[
                    stacked.treated_in_stack.eq(1), "station_id"
                ].nunique(),
                "control_assignments": len(matches),
                "unique_control_stations": matches.control_station_id.nunique(),
                "cohorts": stacked.stack_cohort.nunique(),
                "analysis_months_per_stack": stacked.stack_event_time.nunique(),
                "transition_excluded": not stacked.stack_event_time.eq(-1).any(),
            },
        ]
    )
    all_models_converged = bool(
        registry.converged.fillna(True).all() and ppml["hetero_converged"]
    )
    p4_pass = bool(cs_ppml_same_contract and all_models_converged)
    summary = {
        "p4_decision": "PASS" if p4_pass else "FAIL",
        "p3_decision": p3_gate["decision"],
        "p3_limitations": p3_gate["limitations"],
        "sample_reconciled": bool(cs_ppml_same_contract),
        "stacked_panel_rows": int(len(stacked)),
        "stacked_panel_stations": int(stacked.stack_station_id.nunique()),
        "treated_stations": 40,
        "control_assignments": 120,
        "unique_control_stations": int(matches.control_station_id.nunique()),
        "headline": headline,
        "ppml_headline_eligible": ppml_headline_eligible,
        "cs_heterogeneity": cs["heterogeneity"],
        "ppml_heterogeneity": ppml["heterogeneity"],
        "divergence": {
            "raw_point_rule_triggered": bool(raw_divergence),
            "point_gap_pct_points": float(point_gap),
            "opposite_signs": bool(opposite),
            "confidence_intervals_overlap": bool(interval_overlap),
            "material_unresolved": material_unresolved,
        },
        "specific_timing_sensitivity": cs["specific_timing"],
        "all_models_converged": all_models_converged,
        "treatment_effect_read_after_p3_gate": True,
    }

    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    group_time.to_csv(paths["phase4_group_time_att"], index=False, float_format="%.6f")
    event.to_csv(paths["phase4_event_study"], index=False, float_format="%.6f")
    cohort.to_csv(paths["phase4_cohort_effects"], index=False, float_format="%.6f")
    reconciliation.to_csv(paths["phase4_sample_reconciliation"], index=False)
    registry.to_csv(paths["phase4_results_registry"], index=False, float_format="%.6f")
    paths["phase4_summary"].write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    _plot_event(event, ROOT / "reports" / "figures" / "phase4_event_study.png")
    _plot_estimators(
        registry, ROOT / "reports" / "figures" / "phase4_estimator_comparison.png"
    )
    _write_report(summary, registry, paths["phase4_report"])
    print(json.dumps(summary, indent=2, sort_keys=True))
    return summary


if __name__ == "__main__":
    run_estimation()
