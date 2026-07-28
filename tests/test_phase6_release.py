from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bikelane_causal.pipeline import ROOT


def test_release_summary_and_claim_contract_are_complete():
    summary = json.loads((ROOT / "reports" / "release_summary.json").read_text())
    assert summary["p6_decision"] == "PASS"
    assert summary["release_version"] == "1.0.0"
    assert summary["readme_required_sections_complete"] is True
    assert summary["machine_specific_paths"] == []
    assert summary["claims_contract"]["phase3_decision"] == "PASS WITH LIMITATIONS"
    assert summary["claims_contract"]["phase5_decision"] == "PASS WITH LIMITATIONS"
    assert summary["claims_contract"]["geography_tail_clear"] is False


def test_final_study_map_reconciles_to_frozen_sample():
    summary = json.loads((ROOT / "reports" / "release_summary.json").read_text())
    assert summary["study_design"] == {
        "treated_stations": 40,
        "matched_control_stations": 83,
        "primary_corridors": 12,
    }
    figure = ROOT / "reports" / "figures" / "study_design_map.png"
    assert figure.exists() and figure.stat().st_size > 100_000


def test_release_figure_inventory_has_readable_resolution():
    summary = json.loads((ROOT / "reports" / "release_summary.json").read_text())
    assert len(summary["figures"]) == 7
    for figure in summary["figures"]:
        assert figure["width_px"] >= 1200 or figure["height_px"] >= 1200


def test_public_docs_have_no_machine_specific_paths_and_required_artifacts_exist():
    required = [
        ROOT / "README.md",
        ROOT / "docs" / "research_memo.md",
        ROOT / "docs" / "claims_audit.md",
        ROOT / "docs" / "visual_qa.md",
        ROOT / "docs" / "portfolio_notes.md",
    ]
    for path in required:
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert ("/" + "Users/") not in text
        assert ("file:" + "//") not in text


def test_phase6_plan_and_version_are_release_ready():
    plan = (ROOT / "docs" / "project_plan.md").read_text(encoding="utf-8")
    assert "**Plan version:** 1.0" in plan
    for milestone in range(1, 7):
        assert f"- [x] **M6.{milestone}" in plan
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.0.0"' in pyproject
    registry = pd.read_csv(ROOT / "reports" / "phase5_robustness.csv")
    assert len(registry) == 16
