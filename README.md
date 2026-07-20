# Protected Bike Lanes and Divvy Ridership

This project studies whether newly completed protected bike-lane corridors in Chicago change monthly Divvy trip starts at nearby stations.

## Current status

**Feasibility stage.** No causal model will be estimated until the treatment provenance, independent-corridor count, observation-window, station-integrity, and control-credibility gates pass.

The research design is defined in [`docs/research_brief.md`](docs/research_brief.md).

## Project A inputs

The project reuses two read-only data products created by the completed `bikeshare-forecast` project:

- `data/input/station_master.parquet`
- `data/input/station_month_panel.parquet`

The files are copied inputs. Project B does not modify Project A.

## Immediate task

Build and audit `data/reference/treatment_inventory.csv` for protected bike-lane corridors completed in the candidate study window. The feasibility decision comes before modeling.

