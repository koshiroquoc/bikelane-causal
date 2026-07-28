"""Phase 6 portfolio assets and release-readiness checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

from bikelane_causal.pipeline import ROOT, load_config


REQUIRED_FIGURES = (
    "study_design_map.png",
    "phase3_pretrend_leads.png",
    "phase4_event_study.png",
    "phase4_estimator_comparison.png",
    "phase5_radius_sensitivity.png",
    "phase5_leave_one_corridor_out.png",
    "phase5_geography_placebo.png",
)


def plot_study_design_map(path: Path) -> dict[str, int]:
    config = load_config()
    assignment = pd.read_parquet(config.paths["station_assignment"])
    matches = pd.read_csv(ROOT / "reports" / "phase3_control_matches.csv")
    inventory = pd.read_csv(config.paths["treatment_inventory"])
    corridor_geo = gpd.read_file(config.paths["corridor_geometry"])

    primary_ids = set(
        inventory.loc[
            inventory.primary_eligible.astype(str).str.lower().eq("true")
            & inventory.treatment_variant.isin(config.primary_treatment_variants),
            "corridor_id",
        ]
    )
    primary = corridor_geo[corridor_geo.corridor_id.isin(primary_ids)].to_crs(
        config.project_crs
    )
    points = gpd.GeoDataFrame(
        assignment.copy(),
        geometry=gpd.points_from_xy(assignment.lng, assignment.lat),
        crs="EPSG:4326",
    ).to_crs(config.project_crs)
    controls = points[points.analysis_role.eq("control_candidate")]
    matched_ids = set(matches.control_station_id.astype(str))
    matched = controls[controls.station_id.astype(str).isin(matched_ids)]
    treated = points[points.analysis_role.eq("primary_treated")]

    fig, ax = plt.subplots(figsize=(9.5, 10.5))
    controls.plot(ax=ax, color="#cbd5e1", markersize=7, alpha=0.65, zorder=1)
    matched.plot(
        ax=ax,
        color="#2563eb",
        edgecolor="white",
        linewidth=0.35,
        markersize=25,
        alpha=0.9,
        zorder=3,
    )
    primary.plot(ax=ax, color="#7c3aed", linewidth=3.2, alpha=0.9, zorder=4)
    treated.plot(
        ax=ax,
        color="#f97316",
        edgecolor="#7c2d12",
        linewidth=0.45,
        markersize=42,
        zorder=5,
    )
    ax.set_title("Study design: treated corridors and matched Divvy stations", fontsize=16)
    ax.text(
        0.5,
        1.005,
        "40 treated stations · 83 unique matched controls · 12 corridors",
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        color="#475569",
        fontsize=10.5,
    )
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#f97316", markeredgecolor="#7c2d12", markersize=8, label="Treated station (≤300 m)"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#2563eb", markeredgecolor="white", markersize=7, label="Matched control station"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor="#cbd5e1", markersize=5, label="Eligible control candidate"),
        Line2D([0], [0], color="#7c3aed", linewidth=3, label="Primary protected corridor"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=True, framealpha=0.95)
    ax.set_axis_off()
    ax.set_aspect("equal")
    fig.text(
        0.5,
        0.018,
        "Controls remain outside the 800 m candidate-corridor exclusion zone; matching uses pre-treatment outcomes only.",
        ha="center",
        fontsize=9.5,
        color="#475569",
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.97))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return {
        "treated_stations": int(treated.station_id.nunique()),
        "matched_control_stations": int(matched.station_id.nunique()),
        "primary_corridors": int(primary.corridor_id.nunique()),
    }


def _scan_machine_paths() -> list[str]:
    findings: list[str] = []
    text_suffixes = {".md", ".py", ".json", ".toml", ".txt", ".csv", ".yml", ".yaml"}
    ignored_parts = {".git", ".venv", ".pytest_cache", ".scratch", "data"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        if any(part in ignored_parts for part in path.relative_to(ROOT).parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if ("/" + "Users/") in text or ("file:" + "//") in text:
            findings.append(str(path.relative_to(ROOT)))
    return sorted(findings)


def _figure_inventory() -> list[dict[str, Any]]:
    rows = []
    figure_dir = ROOT / "reports" / "figures"
    for name in REQUIRED_FIGURES:
        path = figure_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Required release figure missing: {name}")
        image = mpimg.imread(path)
        rows.append(
            {
                "file": f"reports/figures/{name}",
                "width_px": int(image.shape[1]),
                "height_px": int(image.shape[0]),
            }
        )
    return rows


def run_release() -> dict[str, Any]:
    map_counts = plot_study_design_map(
        ROOT / "reports" / "figures" / "study_design_map.png"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required_readme_sections = (
        "## Bottom line",
        "## Study design",
        "## Main result",
        "## Robustness and falsification",
        "## Reproduce the analysis",
        "## Limitations",
    )
    missing_sections = [section for section in required_readme_sections if section not in readme]
    if missing_sections:
        raise ValueError(f"README missing release sections: {missing_sections}")
    machine_paths = _scan_machine_paths()
    if machine_paths:
        raise ValueError(f"Machine-specific paths remain in tracked text: {machine_paths}")
    phase3 = json.loads((ROOT / "reports" / "phase3_gate_summary.json").read_text())
    phase4 = json.loads((ROOT / "reports" / "phase4_summary.json").read_text())
    phase5 = json.loads((ROOT / "reports" / "phase5_summary.json").read_text())
    summary = {
        "p6_decision": "PASS",
        "release_version": "1.0.0",
        "readme_words": len(readme.split()),
        "readme_required_sections_complete": True,
        "machine_specific_paths": machine_paths,
        "figures": _figure_inventory(),
        "study_design": map_counts,
        "claims_contract": {
            "phase3_decision": phase3["decision"],
            "phase4_effect_percent": phase4["headline"]["effect_percent"],
            "phase4_ci_low_percent": phase4["headline"]["ci_low_percent"],
            "phase4_ci_high_percent": phase4["headline"]["ci_high_percent"],
            "phase5_decision": phase5["p5_decision"],
            "geography_tail_clear": phase5["geography_tail_clear"],
            "allowed_final_claim": (
                "The analysis does not establish an increase in nearby monthly Divvy trip "
                "starts; identification and geography-placebo limitations preclude a clean "
                "causal claim."
            ),
        },
    }
    output = ROOT / "reports" / "release_summary.json"
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run_release(), indent=2, sort_keys=True))
