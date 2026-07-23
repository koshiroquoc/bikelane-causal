from __future__ import annotations

import json

import pandas as pd

from bikelane_causal.pipeline import ROOT


def test_matching_is_complete_unique_and_local(config):
    raw = json.loads((ROOT / "config" / "analysis.json").read_text())
    ratio = raw["phase3"]["matching_controls_per_treated"]
    matches = pd.read_csv(ROOT / raw["paths"]["phase3_matches"], dtype={"first_post_month": str})
    assignment = pd.read_parquet(config.paths["station_assignment"])
    treated = assignment[assignment.analysis_role.eq("primary_treated")]
    expected = treated.groupby("first_post_month").station_id.nunique().mul(ratio)
    observed = matches.groupby("first_post_month").control_station_id.size()
    assert observed.to_dict() == expected.to_dict()
    assert not matches.duplicated(["first_post_month", "control_station_id"]).any()
    assert matches.cohort_local_distance_m.gt(config.donut_outer_m).all()
    assert matches.cohort_local_distance_m.le(config.local_control_outer_m).all()


def test_diagnostic_event_window_excludes_transition():
    event = pd.read_csv(ROOT / "reports" / "phase3_event_time_series.csv")
    expected = set(range(-13, -1)) | set(range(0, 12))
    for _, group in event.groupby("control_pool"):
        assert set(group.event_time) == expected
    assert -1 not in set(event.event_time)


def test_matching_is_pre_period_only_and_checkpoint_is_not_an_estimate():
    summary = json.loads((ROOT / "reports" / "phase3a_summary.json").read_text())
    assert summary["matching_features"] == [
        "pre_mean_log1p",
        "pre_slope_log1p",
        "pre_sd_log1p",
        "pre_member_share",
    ]
    assert summary["matching_uses_post_treatment_outcomes"] is False
    assert summary["treatment_effect_estimated"] is False
    assert summary["all_selected_windows_complete"] is True
