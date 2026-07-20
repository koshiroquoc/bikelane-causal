# Treatment reference data

`treatment_inventory.csv` is the manually audited treatment table.

## One row means

One independently identifiable protected bike-lane corridor or corridor phase that opened in a single completion month.

If one street was completed in distinct phases or months, each phase must have its own row and corridor ID.

## Date confidence

- `high`: an official source explicitly states the opening/completion date or month.
- `medium`: an official source gives a completion season/year, corroborated by a dated secondary source.
- `low`: inferred from reporting, imagery, construction dates, or dataset differences without an explicit opening/completion statement.

Low-confidence rows may be mapped for exploration but cannot enter the primary causal sample without a documented sensitivity analysis.

`inventory_status` distinguishes a candidate from a treatment row that is ready for analysis. A non-empty `completion_month` does not by itself make a row eligible.

## Date convention

Use the month the facility became usable, not the announcement, funding approval, groundbreaking, or planned completion month. Record ambiguity in `notes` rather than silently choosing a favorable date.

## Geometry snapshots

- `chicago_bike_routes_current.geojson`: official Chicago Data Portal snapshot downloaded 2026-07-20 from dataset `hvv9-38ut`; 1,008 features, including 174 labeled `Protected Bike Lane`.
- `chicago_bike_routes_2022.geojson`: official deprecated end-of-2022 snapshot downloaded 2026-07-20 from dataset `9saw-v2cz`; 883 features, including 101 labeled `PROTECTED BIKE LANE`.

The snapshots help identify candidate additions, but an exact row difference is not an installation-date source because street segmentation and route classifications can also change between snapshots.
