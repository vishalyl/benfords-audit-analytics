# Gate 08 — Composite Risk Score & Dashboard Export

**Stage:** 8 · **Date:** 2026-09-13 · **Gate:** `checks/gate_08.py` → **PASS**

## Outputs produced

| File | Rows/size |
|---|---|
| `data/processed/dashboard_export.parquet` / `dashboard_export_sample.csv` | 50,000 rows × 35 cols (scored population; git-ignored) |
| `data/dashboard/top_risk_transactions.csv` | 50 rows, ranked, `suggested_procedure` on every row |
| `data/dashboard/top_risk_5000.csv` | 5,000 rows (same schema, wider explorer table) |
| `data/dashboard/kpi_summary.json`, `benford_aggregate.csv`, `benford_segments.csv`, `benford_by_segment_digit.csv`, `monthly_trend.csv`, `segment_heatmap.csv` | new in this stage |
| `data/dashboard/` total | 12 files, **1.37 MB** (cap 25 MB) |
| `reports/metrics/composite_summary.json` | band counts, weight sensitivity (5 variants), best-single-method comparison |

## Composite score

`composite_risk = 0.50 * percentile_rank(if_score) + 0.30 * (rule_flag_count/5) + 0.20 * benford_flag`
— mean 0.4505, std 0.1586, **73.2% of rows have a distinct score** (the ceiling here is
`if_score` itself, which has only 36,564 distinct values across the 50,000-row sample —
see `checks/gate_08.py` header note).

### Risk bands

| Band | Count | % |
|---|---|---|
| LOW | 21,162 | 42.3% |
| MEDIUM | 18,681 | 37.4% |
| HIGH | 9,435 | 18.9% |
| CRITICAL | 722 | 1.4% |

### Weight sensitivity (plan sec 8.1.2 — robustness check, not a tuning search)

| Variant | w(IF) | w(Rules) | w(Benford) | AP | Recall@1000 | Precision@100 |
|---|---|---|---|---|---|---|
| **Primary** | 0.50 | 0.30 | 0.20 | **0.1817** | 0.288 | 0.54 |
| IF-heavy | 0.70 | 0.20 | 0.10 | 0.1914 | 0.310 | 0.55 |
| Rules-heavy | 0.20 | 0.60 | 0.20 | 0.1925 | 0.288 | 0.54 |
| Equal | 0.34 | 0.33 | 0.33 | 0.1807 | 0.288 | 0.54 |
| No-Benford | 0.60 | 0.40 | 0.00 | 0.1767 | 0.307 | 0.52 |

**The conclusion is mildly weight-sensitive**: IF-heavy and Rules-heavy both edge out the
Primary weighting by ~0.01 AP. Per the plan's honesty note (sec 8.1.2), the Primary
weights (0.50/0.30/0.20) were set a priori by audit judgement — IF as the leading
unsupervised signal, rules as corroborating evidence, Benford as population context —
and are **kept as the headline weighting** despite this. The sensitivity table is
disclosed in full rather than silently switching to whichever variant scores best
against the labels, which would be fitting to the test set.

### Composite vs. best single method

| Method | AP |
|---|---|
| IF only | 0.1361 |
| Rules only | 0.1347 |
| Benford only | 0.0160 |
| **Composite (Primary)** | **0.1817** |

Composite AP clears every single-signal method — check 6 **PASS**.

## Top 10 of the review list

See `data/dashboard/top_risk_transactions.csv` for the full 50-row list with
`suggested_procedure` per row (e.g. "Obtain the approval matrix; confirm the
authorisation limit and whether the item was split to avoid it." for `SPLIT_AMOUNT`
flags). Top rank scores 0.999, driven by a combination of a top-percentile Isolation
Forest score and multiple rule flags.

## Gate check log

```
GATE 08: PASS
C1 PASS: composite_risk in [0,1], no nulls, 73.2% distinct values
C2 PASS: all 4 bands present
C3 PASS: risk_rank is a dense 1..50000 permutation
C4 PASS: dashboard_export.parquet has 50000 rows (== scored population), column set matches
C5 PASS: top_risk_transactions.csv has exactly 50 rows, sorted desc, all procedures populated
C6 PASS: composite AP=0.181662 >= best single method AP=0.13605
C7 PASS: 5 weight variants, AP computed for each
C8 PASS: all 10 required files present, dir size 1.37 MB < 25 MB
C9 PASS: dashboard_export_sample.csv contains all 802 injected rows of the scored population
C10 PASS: kpi_summary.json AP matches model_metrics.json (no copy-paste drift)
C11 PASS: re-running composite scoring reproduces an identical top_risk_transactions.csv hash
```

## DECISIONS.md entries added

None new — this stage operates under D-0003 (scored-sample population) already logged
in Stage 7.

**GATE: PASS**
