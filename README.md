# Protected Bike Lanes and Divvy Ridership

This project studies whether newly completed protected bike-lane corridors in Chicago change monthly Divvy trip starts at nearby stations.

## Current status

**Phase 3 complete — `PASS WITH LIMITATIONS`.** Phase 3A compares broad, cohort-local, and pre-period-matched control pools; Phase 3B locks 120 matched control assignments (3 per treated station) and runs pre-treatment-only placebo-lead diagnostics. The treated-station-weighted matched raw pre-trend gap is 0.21 percentage points per month, but the two-way-clustered four-bin lead test rejects exact zero (`F(4,11) = 4.41`, `p = 0.023`) and balance remains weak in two sparse cohorts. Phase 4 may proceed, but causal claims must remain narrow and conditional. No post-treatment ATT has been estimated.

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

## Reproducible Phase 3 checkpoints

```bash
make phase3a  # raw trends, control comparison, matching, composition
make phase3b  # pre-treatment leads and identification gate
```

The next task is Phase 4 estimation on the locked matched sample. Group-time ATT remains the primary identification/dynamics estimator; staggered-robust PPML is a conditional candidate for the headline percentage magnitude.
