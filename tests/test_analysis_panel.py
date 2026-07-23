from __future__ import annotations

import pandas as pd


def load_outputs(config):
    assignment = pd.read_parquet(config.paths["station_assignment"])
    controls = pd.read_parquet(config.paths["control_cohort_eligibility"])
    panel = pd.read_parquet(config.paths["analysis_panel"])
    source_panel = pd.read_parquet(config.paths["station_month_panel"])
    return assignment, controls, panel, source_panel


def test_assignment_has_one_row_per_source_station(config):
    assignment, _, _, _ = load_outputs(config)
    station_master = pd.read_parquet(config.paths["station_master"])
    assert len(assignment) == len(station_master)
    assert assignment.station_id.is_unique
    assert set(assignment.station_id) == set(station_master.station_id)


def test_analysis_panel_has_unique_keys_and_reconciles(config):
    assignment, _, panel, source_panel = load_outputs(config)
    selected_ids = set(
        assignment.loc[
            assignment.analysis_role.isin(["primary_treated", "control_candidate"]),
            "station_id",
        ]
    )
    expected = source_panel[source_panel.station_id.isin(selected_ids)]
    assert not panel.duplicated(["station_id", "month"]).any()
    assert len(panel) == len(expected)
    assert set(map(tuple, panel[["station_id", "month"]].to_numpy())) == set(
        map(tuple, expected[["station_id", "month"]].to_numpy())
    )


def test_outcomes_are_unchanged_and_never_imputed(config):
    _, _, panel, source_panel = load_outputs(config)
    outcome_columns = ["member_trips", "casual_trips", "total_trips"]
    comparison = panel[["station_id", "month", *outcome_columns]].merge(
        source_panel,
        on=["station_id", "month"],
        how="left",
        suffixes=("_phase2", "_source"),
        validate="one_to_one",
    )
    for column in outcome_columns:
        assert comparison[f"{column}_phase2"].equals(
            comparison[f"{column}_source"]
        )
    assert panel.outcome_observed.all()
    assert not panel.missing_month_imputed.any()
    assert not (panel[outcome_columns] < 0).any(axis=None)


def test_spatial_groups_respect_locked_radii(config):
    assignment, _, panel, _ = load_outputs(config)
    primary = assignment[assignment.analysis_role.eq("primary_treated")]
    controls = assignment[assignment.analysis_role.eq("control_candidate")]
    assert primary.distance_to_assigned_corridor_m.le(config.treated_radius_m).all()
    assert controls.distance_to_any_candidate_m.gt(config.donut_outer_m).all()
    panel_ids = set(panel.station_id)
    excluded_ids = set(
        assignment.loc[
            assignment.assignment_class.isin(
                ["donut", "candidate_corridor_exclusion"]
            ),
            "station_id",
        ]
    )
    assert panel_ids.isdisjoint(excluded_ids)


def test_treatment_is_monotonic_and_event_boundaries_are_correct(config):
    _, _, panel, _ = load_outputs(config)
    treated = panel[panel.ever_treated].copy()
    assert treated.groupby("station_id").post.apply(
        lambda values: values.is_monotonic_increasing
    ).all()
    first_post = treated[treated.month.astype(str).eq(treated.first_post_month.astype(str))]
    assert len(first_post) == treated.station_id.nunique()
    assert first_post.event_time.eq(0).all()
    assert first_post.post.eq(1).all()
    transition = treated[
        treated.month.astype(str).eq(treated.completion_month.astype(str))
    ]
    assert transition.event_time.eq(-1).all()
    assert transition.is_transition_month.all()
    assert not transition.analysis_row.any()


def test_controls_have_no_treatment_state(config):
    _, _, panel, _ = load_outputs(config)
    controls = panel[panel.analysis_role.eq("control_candidate")]
    assert not controls.ever_treated.any()
    assert controls.post.eq(0).all()
    assert controls.event_time.isna().all()
    assert not controls.is_transition_month.any()
    assert controls.assigned_primary_corridor.isna().all()
    assert controls.distance_to_assigned_corridor_m.isna().all()


def test_required_treated_windows_are_complete(config):
    assignment, _, _, _ = load_outputs(config)
    treated = assignment[assignment.analysis_role.eq("primary_treated")]
    assert treated.pre_months_observed.eq(config.required_pre_months).all()
    assert treated.post_months_observed.eq(config.required_post_months).all()
    assert treated.stable_12_pre_12_post.all()
    assert treated.assigned_primary_corridor.nunique() == 12


def test_control_cohort_table_is_unique_and_consistent(config):
    assignment, controls, _, _ = load_outputs(config)
    control_ids = set(
        assignment.loc[
            assignment.analysis_role.eq("control_candidate"), "station_id"
        ]
    )
    assert not controls.duplicated(["station_id", "first_post_month"]).any()
    assert set(controls.station_id) == control_ids
    expected = (
        controls.pre_months_observed.eq(config.required_pre_months)
        & controls.post_months_observed.eq(config.required_post_months)
    )
    assert controls.eligible_12_pre_12_post.equals(expected)


def test_configuration_preserves_pre_specified_policies(config):
    assert config.project_crs == "EPSG:26916"
    assert config.treated_radius_m == 300
    assert config.donut_outer_m == 800
    assert config.transition_policy == "exclude_completion_month"
    assert config.missing_month_policy == "preserve_missing"
    assert config.multiple_exposure_policy == "earliest_completion_then_nearest"
