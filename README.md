# Protected Bike Lanes and Divvy Ridership

This project studies whether newly completed protected bike-lane corridors in Chicago change monthly Divvy trip starts at nearby stations.

## Current status

**Phase 2 complete — `PASS`.** The configured build produces an audited 33,018-row station-month panel containing 40 primary treated stations and 1,599 candidate controls across all 36 source months. Nine critical tests pass. No treatment effect has been estimated.

The limitations are conservative first-verified timing for nine corridors, multiple-corridor exposure for a small number of stations, and the absence of monthly station coordinates. See [`reports/feasibility_report.md`](reports/feasibility_report.md).

The research design is defined in [`docs/research_brief.md`](docs/research_brief.md). The phase gates, milestones, and release checkpoints are tracked in [`docs/project_plan.md`](docs/project_plan.md).

## Project A inputs

The project reuses two read-only data products created by the completed `bikeshare-forecast` project:

- `data/input/station_master.parquet`
- `data/input/station_month_panel.parquet`

The files are copied inputs. Project B does not modify Project A.

## Phase 1 outputs

- `data/reference/corridor_candidates.csv` and `.geojson`
- `data/reference/treatment_inventory.csv`
- `data/reference/preliminary_station_assignment.csv`
- `reports/geometry_audit.csv`
- `reports/pretrend_screen.csv`
- `reports/power_audit.csv`
- `reports/figures/phase1_treatment_control_map.png`

Rebuild them with:

```bash
MPLCONFIGDIR=.scratch/matplotlib .venv/bin/python scripts/build_phase1_audit.py
```

## Reproducible Phase 2 build

```bash
make setup
make phase2
```

`make phase2` rebuilds Phase 1 reference artifacts, creates the spatial assignment and station-month panel, writes the data-quality report, and runs the test suite. Derived Parquet files remain local and ignored by Git.

Key tracked inputs and outputs:

- `config/analysis.json`
- `src/bikelane_causal/pipeline.py`
- `tests/test_analysis_panel.py`
- `reports/data_quality_report.md`
- `reports/panel_build_summary.json`

## Immediate task

Begin Phase 3 identification diagnostics and lock the control strategy before reading a headline treatment estimate.
