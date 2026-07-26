from __future__ import annotations

import json

import numpy as np
import pandas as pd

from bikelane_causal.pipeline import ROOT


def test_phase5_registry_covers_every_locked_milestone():
    registry = pd.read_csv(ROOT / "reports" / "phase5_robustness.csv")
    assert {
        "M5.1 radius",
        "M5.2 controls",
        "M5.4 construction window",
        "M5.4 timing sensitivity",
        "M5.5 treatment variant",
        "M5.6 outcome",
        "M5.7 timing placebo",
    } <= set(registry.milestone)
    assert len(registry[registry.milestone.eq("M5.1 radius")]) == 3
    assert len(registry[registry.milestone.eq("M5.2 controls")]) == 3
    assert set(
        registry.loc[registry.milestone.eq("M5.6 outcome"), "specification"]
    ) == {"member trips", "casual trips"}


def test_primary_specification_reconciles_to_phase4():
    registry = pd.read_csv(ROOT / "reports" / "phase5_robustness.csv")
    primary = registry[
        registry.specification.eq("300m treated / 800m donut")
    ].iloc[0]
    phase4 = json.loads((ROOT / "reports" / "phase4_summary.json").read_text())
    assert np.isclose(primary.effect_percent, phase4["headline"]["effect_percent"])
    assert primary.treated_stations == 40
    assert primary.treated_corridors == 12
    assert primary.control_stations == 83


def test_leave_one_out_is_complete_and_uses_locked_influence_rule():
    loco = pd.read_csv(ROOT / "reports" / "phase5_leave_one_corridor_out.csv")
    assert len(loco) == 12
    assert loco.omitted_corridor.nunique() == 12
    expected = loco.change_from_main_pct_points.abs().ge(5) | loco.sign_reversal
    assert (loco.influential == expected).all()


def test_geography_placebo_is_reproducible_pipeline_level_distribution():
    placebo = pd.read_csv(ROOT / "reports" / "phase5_geography_placebo.csv")
    candidates = pd.read_csv(ROOT / "reports" / "phase5_geography_candidates.csv")
    summary = json.loads((ROOT / "reports" / "phase5_summary.json").read_text())
    assert len(placebo) == 50
    assert placebo.replication.tolist() == list(range(1, 51))
    assert placebo.treated_corridors.eq(12).all()
    assert placebo.treated_stations.gt(0).all()
    assert placebo.control_stations.gt(0).all()
    assert np.isfinite(placebo.effect_percent).all()
    assert candidates.distance_to_candidate_inventory_m.ge(1200).all()
    assert not candidates.displayrou.eq("Protected Bike Lane").any()
    assert summary["geography_seed"] == 20260725
    assert summary["geography_replications"] == 50


def test_phase5_gate_reports_falsification_outcomes_honestly():
    summary = json.loads((ROOT / "reports" / "phase5_summary.json").read_text())
    assert summary["p5_decision"] in {"PASS", "PASS WITH LIMITATIONS"}
    assert summary["timing_placebo_clear"] is True
    assert summary["geography_tail_clear"] is False
    assert summary["p5_decision"] == "PASS WITH LIMITATIONS"
