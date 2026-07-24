from __future__ import annotations

import json

import numpy as np
import pandas as pd

from bikelane_causal.estimation import _percent_from_pair_values
from bikelane_causal.pipeline import ROOT


def test_phase4_stacked_sample_matches_frozen_contract():
    panel = pd.read_parquet(ROOT / "data" / "derived" / "phase4_stacked_panel.parquet")
    assert len(panel) == 3840
    assert panel.stack_station_id.nunique() == 160
    assert panel.loc[panel.treated_in_stack.eq(1), "station_id"].nunique() == 40
    assert panel.loc[panel.treated_in_stack.eq(0), "stack_station_id"].nunique() == 120
    assert panel.stack_event_time.nunique() == 24
    assert -1 not in set(panel.stack_event_time)
    assert panel.groupby("stack_station_id").stack_event_time.nunique().eq(24).all()


def test_group_time_percent_translation_on_known_pair_effect():
    pairs = pd.DataFrame(
        {
            "effect_count": [20.0, 20.0, 20.0, 20.0],
            "treated_observed": [120.0, 120.0, 120.0, 120.0],
            "corridor_cluster": ["a", "a", "b", "b"],
            "control_station_id": ["c1", "c2", "c3", "c4"],
        }
    )
    result = _percent_from_pair_values(pairs)
    assert result["effect_count"] == 20.0
    assert result["counterfactual_mean"] == 100.0
    assert result["effect_percent"] == 20.0
    assert result["se_percent"] < 1e-10


def test_event_study_and_registry_are_complete():
    event = pd.read_csv(ROOT / "reports" / "phase4_event_study.csv")
    expected = set(range(-13, -1)) | set(range(0, 12))
    assert set(event.event_time) == expected
    assert event.loc[event.event_time.eq(-2), "effect_percent"].iloc[0] == 0
    registry = pd.read_csv(ROOT / "reports" / "phase4_results_registry.csv")
    assert set(registry.estimator) == {
        "twfe_ols_log1p_baseline",
        "pooled_ppml_twfe_baseline",
        "group_time_att",
        "cohort_stacked_ppml",
        "group_time_att_specific_timing",
    }
    assert np.isfinite(registry.effect_percent).all()
    assert (registry.ci_low_percent <= registry.effect_percent).all()
    assert (registry.effect_percent <= registry.ci_high_percent).all()


def test_phase4_gate_and_estimator_assignment():
    summary = json.loads((ROOT / "reports" / "phase4_summary.json").read_text())
    assert summary["p4_decision"] == "PASS"
    assert summary["sample_reconciled"] is True
    assert summary["all_models_converged"] is True
    assert summary["headline"]["estimator"] == "group_time_att"
    assert summary["ppml_headline_eligible"] is False
    assert summary["cs_heterogeneity"]["severe"] is True
    assert summary["ppml_heterogeneity"]["severe"] is True
    assert summary["divergence"]["material_unresolved"] is False
    assert summary["specific_timing_sensitivity"]["treated_corridors"] == 5
