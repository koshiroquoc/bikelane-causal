# Protected Bike Lanes and Divvy Ridership

This project studies whether newly completed protected bike-lane corridors in Chicago change monthly Divvy trip starts at nearby stations.

## Current status

**Phase 1 complete — `PASS WITH LIMITATIONS`.** The feasibility audit retains 12 independent corridors and 40 stable treated stations. The largest corridor accounts for 27.5% of the preliminary treated sample, and the planning MDE is approximately 14–20%. No treatment effect has been estimated.

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

## Immediate task

Begin Phase 2 by turning the feasibility logic into the configured, tested one-command analysis-panel build. Causal estimation remains prohibited until the Phase 3 identification gate passes.
