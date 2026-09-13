# Gate 08: Composite Risk Score & Dashboard Export

**Stage:** 8 · **Date:** 2026-09-13 (re-run at full population) · **Gate:** `checks/gate_08.py` -> **PASS**

## Outputs produced

| File | Rows/size |
|---|---|
| `data/processed/dashboard_export.parquet` / `dashboard_export_sample.csv` | 1,030,804 rows x 36 cols (full population; git-ignored) |
| `data/dashboard/top_risk_transactions.csv` | 50 rows, ranked, `suggested_procedure` on every row |
| `data/dashboard/top_risk_5000.csv` | 5,000 rows (same schema, wider explorer table) |
| `data/dashboard/rank_labels.json` | new: 1,030,804-entry 0/1 array (composite-risk rank order) for the live web simulator |
| `data/dashboard/` total | 13 files, **3.60 MB** (cap 25 MB) |
| `reports/metrics/composite_summary.json` | band counts, weight sensitivity (5 variants), best-single-method comparison |

## Composite score

`composite_risk = 0.50 * percentile_rank(if_score) + 0.30 * (rule_flag_count/5) + 0.20 * benford_flag`,
mean 0.4505, **337,950 distinct values** (>100,000, the master plan's literal check,
achievable now that Stage 6 scores the full population; see DECISIONS.md D-0007).

### Risk bands (full population)

| Band | Count | % |
|---|---|---|
| LOW | 436,639 | 42.4% |
| MEDIUM | 386,266 | 37.5% |
| HIGH | 192,891 | 18.7% |
| CRITICAL | 15,008 | 1.5% |

### Weight sensitivity (plan sec 8.1.2, robustness check, not a tuning search)

| Variant | w(IF) | w(Rules) | w(Benford) | AP | Recall@1000 |
|---|---|---|---|---|---|
| **Primary** | 0.50 | 0.30 | 0.20 | **0.1656** | 0.0254 |
| IF-heavy | 0.70 | 0.20 | 0.10 | 0.1770 | 0.0256 |
| Rules-heavy | 0.20 | 0.60 | 0.20 | 0.1744 | 0.0254 |
| Equal | 0.34 | 0.33 | 0.33 | 0.1632 | 0.0254 |
| No-Benford | 0.60 | 0.40 | 0.00 | 0.1599 | 0.0258 |

The conclusion remains mildly weight-sensitive (IF-heavy and Rules-heavy edge out
Primary by ~0.01-0.012 AP, the same pattern seen at 50k). Primary is kept as the
headline weighting per the a-priori judgement rationale in DECISIONS.md, not switched
to whichever variant scores best.

### Composite vs. best single method

| Method | AP |
|---|---|
| IF only | 0.1355 |
| Rules only | 0.1180 |
| Benford only | 0.0163 |
| **Composite (Primary)** | **0.1656** |

Composite AP clears every single-signal method, check 6 **PASS**.

## Gate check log

```
GATE 08: PASS
C1 PASS: composite_risk in [0,1], no nulls, 337,950 distinct values (>100,000)
C2 PASS: all 4 bands present: {'LOW': 436639, 'MEDIUM': 386266, 'HIGH': 192891, 'CRITICAL': 15008}
C3 PASS: risk_rank is a dense 1..1030804 permutation
C4 PASS: dashboard_export.parquet has 1030804 rows (== scored population), column set matches
C5 PASS: top_risk_transactions.csv has exactly 50 rows, sorted desc, all procedures populated
C6 PASS: composite AP=0.165573 >= best single method AP=0.135522
C7 PASS: 5 weight variants, AP computed for each
C8 PASS: all 10 required files present, dir size 3.60 MB < 25 MB
C9 PASS: dashboard_export_sample.csv contains all 16874 injected rows of the scored population
C10 PASS: kpi_summary.json AP matches model_metrics.json (no copy-paste drift)
C11 PASS: re-running composite scoring reproduces an identical top_risk_transactions.csv hash
```

## A determinism bug caught and fixed in this pass

C11 initially failed after the full-population re-run: `if_pct` (an unrounded
`rank(pct=True)` on `if_score`) differed in its 15th decimal place between two runs of
the same seeded pipeline, traced to `IsolationForest(n_jobs=-1)`'s parallel score
reduction not being bit-exact run to run. Fixed by rounding `if_pct` to 6dp, the same
convention every other score column already uses (`src/composite.py`). See DECISIONS.md
D-0007 for the full account, including a second false failure caused by the gate's own
comparison method (a `read_csv` -> `to_csv` round trip on one side only), fixed by
hashing the original file's raw bytes instead.

**GATE: PASS**
