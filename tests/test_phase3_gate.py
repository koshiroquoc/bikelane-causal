from __future__ import annotations

import json

from bikelane_causal.pipeline import ROOT


def test_gate_locks_design_and_claim_scope():
    result = json.loads((ROOT / "reports" / "phase3_gate_summary.json").read_text())
    assert result["decision"] in {"PASS", "PASS WITH LIMITATIONS", "FAIL"}
    assert result["primary_control_specification"] == "pre_period_matched"
    assert result["matching_controls_per_treated"] == 3
    assert result["phase4_authorized"] == (result["decision"] != "FAIL")


def test_pretrend_leads_use_only_pre_periods_and_corridor_clusters():
    leads = json.loads((ROOT / "reports" / "phase3_pretrend_leads_summary.json").read_text())
    assert leads["post_treatment_outcomes_used"] is False
    assert leads["reference_event_time"] == -2
    assert all(event < -1 for event in leads["lead_event_times"])
    assert leads["treated_stations"] == 40
    assert leads["corridor_clusters"] == 12
    assert leads["control_station_clusters"] > leads["treated_stations"]
