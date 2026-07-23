# Derived data

Files in this directory are reproducible local outputs and are not committed:

- `station_corridor_assignment.parquet`: one row per Project A station with spatial class, treatment assignment, distance, overlap, and station-integrity fields.
- `control_cohort_eligibility.parquet`: control-station eligibility for each treatment cohort's 12-month pre/post window.
- `station_month_analysis.parquet`: the audited observed-row analysis panel used by later diagnostics and estimators.

Build all three and run the critical tests from the project root:

```bash
make phase2
```

Missing station-months are preserved as missing. The build never creates zero-trip rows.

Phase 3 is split into two reproducible checkpoints:

```bash
make phase3a
make phase3b
```

Phase 3 outputs are tracked under `reports/`; no additional derived Parquet data are committed.
