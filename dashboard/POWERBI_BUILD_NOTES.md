# Power BI Build Notes

**Status: Stage 9 (the `.pbix` itself) was out of scope for this run, see
`DECISIONS.md` D-0001.** Power BI Desktop is a Windows GUI application with no
headless/CLI authoring path, so an autonomous agent cannot build the five-page
dashboard the master plan specifies (`plan/03_STAGES_7-9.md` Stage 9). This file
records what is already prepared, so building the `.pbix` later is mechanical.

## What is already prepared

All data Stage 9 would consume is produced by Stages 7-8 and lives here:

| File | Purpose |
|---|---|
| `data/dashboard/kpi_summary.json` | Page 1 KPI cards |
| `data/dashboard/benford_aggregate.csv` | Page 2 observed-vs-expected digit chart |
| `data/dashboard/benford_segments.csv`, `benford_by_segment_digit.csv` | Page 2 segment table + per-segment digit redraw |
| `data/dashboard/monthly_trend.csv`, `segment_heatmap.csv` | Page 1 trend, Page 5 heatmap |
| `data/dashboard/method_comparison.csv` | Page 4 hero matrix |
| `data/dashboard/model_metrics.json`, `pr_curve_points.csv`, `precision_at_k.csv` | Page 4 metric cards and curves |
| `data/dashboard/top_risk_transactions.csv`, `top_risk_5000.csv` | Page 3 anomaly explorer |
| `data/processed/dashboard_export.parquet` (git-ignored, regenerate with `python -m src.export`) | Full fact table for the star schema |

## To build the `.pbix`

1. Install Power BI Desktop (Microsoft Store, free, no account required to save a
   `.pbix` locally).
2. Get Data -> Parquet -> `data/processed/dashboard_export.parquet` as `fact_transactions`,
   plus each `data/dashboard/*.csv` as its own table.
3. Follow the data model, DAX measures (paste-ready), and page-by-page visual
   specification in `plan/03_STAGES_7-9.md` sec 9.2-9.4 verbatim. Every field well,
   every measure, and every threshold is already written out there; no design
   decisions are left open.
4. Apply `dashboard/theme.json` once it is created (not yet built this run).
5. Export 5 screenshots at 1920x1080 to `docs/screenshots/page1_overview.png` etc.
6. Save as `dashboard/audit_analytics.pbix`.

## Known performance caveat

`plan/03_STAGES_7-9.md` sec 9.3 warns that the dynamic `Benford MAD` DAX measure is
slow over the full 1.03M-row fact table in a matrix visual with many rows. Pre-registered
choice PD-14 (dynamic DAX on the aggregate page, precomputed `benford_segments` table for
the segment matrix) is unchanged and still the right approach once this is built.
