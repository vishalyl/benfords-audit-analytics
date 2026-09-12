# STAGES 7–9 — Validation, Composite Risk Score, Power BI Dashboard

**Document ID:** `03_STAGES_7-9`
**Prerequisite:** Stage 6 gate PASSED.
**Covers:** Stage 7 Validation against ground truth · Stage 8 Composite risk score & export · Stage 9 Power BI dashboard

> Stage 7 produces the project's single most important artefact: the
> **anomaly-type × detection-method matrix**. Every other output supports it.

---
---

# STAGE 7 — VALIDATION AGAINST GROUND TRUTH

**Goal:** measure how well each detection layer performs, per anomaly type, and prove empirically that the layers are complementary.
**Estimated time:** 3–4 hours
**Inputs:** `scored.parquet`, `flags.parquet`, `benford_segments.csv`, `transactions_labeled.parquet`, `injected_anomalies.csv`
**Outputs:** `reports/metrics/model_metrics.json`, `data/dashboard/method_comparison.csv`, `reports/figures/pr_curve.png` + others

---

## 7.1 Framing — what these metrics do and do not mean

Before any number is produced, the agent must internalise (and later write into the README):

1. **Positives are only the injected rows.** The real ledger may well contain genuine
   anomalies; when a method flags one of those, this evaluation scores it as a false
   positive. **Therefore every precision figure reported here is a lower bound.**
   State this explicitly. It is the most important caveat in the whole project.
2. **Recall is trustworthy; precision is pessimistic.** Recall is measured against a
   complete, known positive set, so it is honest. Precision is not.
3. **Ranking beats classification.** The audit-relevant question is "what should I look
   at first", so `average_precision` and `precision@k` lead; the binary F1 at a fixed
   contamination follows.
4. **Never say the model "detected fraud".** It ranked transactions for review. This
   wording discipline runs through Stages 11, 12 and 13.

## 7.2 `src/validate.py` — specification

```python
def load_evaluation_frame() -> pd.DataFrame:
    """Join on txn_id:
        transactions_labeled  (ground truth: is_synthetic_anomaly, anomaly_type)
      + flags                 (5 rule flags, rule_flag_count)
      + scored                (if_score_fsa, if_score_fsb, contamination variants, lof)
      + benford segment flag  (attached via segment_flag_map for each segmentation
                               scheme: benford_flag_country, benford_flag_month,
                               benford_flag_country_month, benford_flag_customer,
                               and benford_flag_any = OR of the four)
    Asserts a 1:1 join with no row loss and no nulls in the score columns."""

def binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """precision, recall, f1, tp, fp, tn, fn, specificity,
       false_positive_rate, alerts (=tp+fp), alert_rate."""

def ranking_metrics(y_true: np.ndarray, score: np.ndarray,
                    k_list: list[int]) -> dict:
    """average_precision (sklearn.metrics.average_precision_score),
       roc_auc,
       baseline_precision (= y_true.mean(), the random-guess line),
       lift_at_k for each k (= precision@k / baseline_precision),
       precision_at_k, recall_at_k for each k,
       and the full precision_recall_curve arrays for plotting."""

def per_type_detection(eval_df: pd.DataFrame, method_cols: dict[str, str],
                       threshold_map: dict[str, float]) -> pd.DataFrame:
    """THE MATRIX. Rows = anomaly types (+ 'ALL_INJECTED' and 'REAL_ROWS').
       Cols = detection methods. Cell = % of that type flagged by that method.
       The REAL_ROWS row gives each method's false-positive rate, so the reader
       can see the cost alongside the catch rate. Returns a tidy DataFrame plus
       a pivoted display version."""

def threshold_sweep(y_true, score, n_points: int = 200) -> pd.DataFrame:
    """precision/recall/F1/alert_count at each of n_points score thresholds.
       Used for the threshold-selection figure and for picking the operating point."""

def optimal_threshold(sweep: pd.DataFrame, criterion: str = "f1") -> float:
    """criterion in {'f1', 'precision_at_recall_50', 'alert_budget_500'}.
       Report all three; use 'f1' as the headline operating point but show the
       'alert_budget' one as the audit-realistic alternative."""

def bootstrap_ci(y_true, score, metric_fn, n_boot: int = 200,
                 seed: int = 42) -> tuple[float, float, float]:
    """Returns (point_estimate, ci_lower_95, ci_upper_95). Apply to
       average_precision and to recall at the chosen threshold. Confidence
       intervals on a portfolio project's headline metric is a genuine
       differentiator — few candidates do it."""

def run(force=False) -> None: ...
```

## 7.3 The methods evaluated (columns of the matrix)

| Column key | Definition | Type |
|---|---|---|
| `benford_country` | row's country segment is flagged | binary |
| `benford_month` | row's year_month segment is flagged | binary |
| `benford_country_month` | row's (country, month) segment is flagged | binary |
| `benford_customer` | row's customer segment is flagged | binary |
| `benford_any` | OR of the four | binary |
| `rule_duplicate` | `flag_duplicate` | binary |
| `rule_round` | `flag_round_number` | binary |
| `rule_threshold` | `flag_threshold_avoidance` | binary |
| `rule_period_end` | `flag_period_end` | binary |
| `rule_off_hours` | `flag_off_hours` | binary |
| `rules_any` | `rule_flag_count >= 1` | binary |
| `if_fsa_top` | `if_score_fsa` above the 98.5th percentile | binary from score |
| `if_fsb_top` | `if_score_fsb` above the 98.5th percentile | binary from score |
| `lof_top` | LOF above threshold (subsample rows only; blank elsewhere) | binary from score |
| `composite_top` | composite score above the 98.5th percentile (Stage 8 back-fills this) | binary from score |

> `composite_top` cannot be computed until Stage 8. Two options, either acceptable:
> (a) run Stage 8 first and then Stage 7 for the composite row only, or
> (b) compute the composite inline in Stage 7 and have Stage 8 re-use it.
> **Choose (b)** — put `compute_composite()` in `src/composite.py` and import it in
> both stages, so there is one implementation. Log the choice.

## 7.4 The matrix — required output format

`data/dashboard/method_comparison.csv`, long format for Power BI:

| anomaly_type | method | n_rows | n_caught | pct_caught |
|---|---|---|---|---|
| duplicate | rules_any | 2612 | 2455 | 93.99 |
| duplicate | if_fsb_top | 2612 | 118 | 4.52 |
| … | … | … | … | … |
| REAL_ROWS | rules_any | 1040112 | 92104 | 8.85 |

And a wide display version in the gate report and README:

```
                        Benford   Rules   IF(FS-A)  IF(FS-B)  Composite
duplicate                  x.x%    xx.x%      x.x%      x.x%       xx.x%
threshold_avoidance        x.x%    xx.x%      x.x%      x.x%       xx.x%
round_number               x.x%    xx.x%      x.x%      x.x%       xx.x%
digit_fabrication         xx.x%     x.x%      x.x%      x.x%       xx.x%
timing_period_end          x.x%    xx.x%      x.x%      x.x%       xx.x%
timing_off_hours           x.x%    xx.x%      x.x%      x.x%       xx.x%
extreme_outlier            x.x%     x.x%     xx.x%     xx.x%       xx.x%
--------------------------------------------------------------------------
ALL INJECTED              xx.x%    xx.x%     xx.x%     xx.x%       xx.x%
REAL ROWS (false pos.)     x.x%     x.x%      1.5%      1.5%        1.5%
```

**The interpretation paragraph that must accompany it** (agent writes the real
version from actual numbers, following this shape):

> No single method dominates. Rule-based checks catch duplicates, round numbers,
> threshold structuring and timing anomalies at high rates but are nearly blind to
> fabricated digit distributions and extreme outliers. Segmented Benford testing is
> the only method that surfaces digit fabrication, and it does so only at segment
> level — the aggregate test does not move. Isolation Forest is the only method that
> reliably catches extreme statistical outliers. The composite score outperforms every
> individual layer on overall recall at a comparable alert budget, which is the
> empirical case for layered detection in an audit programme.

If the measured numbers contradict that narrative, **write what is true**, and discuss
why. A surprising result honestly explained is worth more than a tidy result.

## 7.5 Required metrics in `model_metrics.json`

```jsonc
{
  "population": {"n_total": ..., "n_injected": ..., "anomaly_rate": ...},
  "baseline_precision": ...,                       // = anomaly_rate
  "models": {
    "if_fsb_c015": {
      "average_precision": ..., "ap_ci95": [..., ...],
      "roc_auc": ...,
      "threshold_used": ..., "threshold_criterion": "f1",
      "precision": ..., "recall": ..., "f1": ...,
      "confusion": {"tp":..., "fp":..., "tn":..., "fn":...},
      "precision_at_k": {"50":..., "100":..., "250":..., "500":..., "1000":..., "5000":...},
      "recall_at_k":   {"50":..., ...},
      "lift_at_k":     {"50":..., ...}
    },
    "if_fsa_c015": { ... },
    "if_fsb_c005": { ... }, "if_fsb_c010": { ... }, "if_fsb_c030": { ... },
    "lof_subsample": { ..., "note": "computed on a 150k stratified subsample" },
    "rules_any":  { "precision":..., "recall":..., "f1":..., "alerts":... },
    "benford_any":{ "precision":..., "recall":..., "f1":..., "alerts":... },
    "composite":  { ... same shape as if_fsb_c015 ... }
  },
  "per_type": { "duplicate": {...}, ... },
  "caveats": [
    "Positives are injected rows only; genuine anomalies in the real ledger are scored as false positives, so precision is a lower bound.",
    "Contamination was set to the known injection rate; in a real engagement this rate is unknown.",
    "LOF metrics are computed on a stratified subsample and are not directly comparable to full-population figures."
  ]
}
```

Every number quoted anywhere later in the project (README, PDF workpaper, resume
bullets, Power BI cards) must be read from this file, never retyped from memory.

## 7.6 Required figures

| Figure | File | Notes |
|---|---|---|
| Precision-Recall curve, all models on one axis | `pr_curve.png` | Include the horizontal baseline at `anomaly_rate`; annotate the chosen operating point with a marker; legend shows AP per model |
| ROC curve (secondary) | `roc_curve.png` | Include with a caveat that ROC is optimistic under heavy imbalance — say so in the caption |
| Precision@k curve | `precision_at_k.png` | x = k (log scale), y = precision; the most audit-relevant chart |
| Confusion matrix heatmap | `confusion_matrix.png` | Counts and row-normalised percentages in the cells |
| Method × anomaly-type heatmap | `method_comparison_heatmap.png` | **The hero chart of the project.** Rows = anomaly types, cols = methods, cell colour + printed % |
| Threshold sweep | `threshold_sweep.png` | Precision, recall, F1 and alert count vs threshold, twin y-axes |
| Score distribution by anomaly type | `score_by_type.png` | Box/violin per type plus real rows |
| Cumulative recall vs review effort | `recall_vs_effort.png` | x = number of transactions reviewed, y = % of injected anomalies found; overlay a random-review diagonal. **This is the chart that makes the business case.** |

## 7.7 Stage 7 Gate — `checks/gate_07.py`

1. `model_metrics.json` and `method_comparison.csv` exist and parse.
2. The evaluation frame joins 1:1 with no row loss and no nulls in score columns.
3. `average_precision` for `if_fsb_c015` is **strictly greater than** `baseline_precision`. If not, the sign convention is inverted or the labels are misaligned — stop and fix.
4. `average_precision` is in a plausible band **0.05 – 0.85**. Below 0.05: labels likely misaligned. Above 0.85: injection likely too easy (see Stage 3 T10) — investigate and log; do not celebrate.
5. `method_comparison.csv` has a row for every (anomaly_type × method) pair with no nulls; includes the `ALL_INJECTED` and `REAL_ROWS` rows.
6. **Complementarity assertion:** for at least one anomaly type, `rules_any` catch rate exceeds `if_fsb_top` by ≥20 percentage points, **and** for at least one other type the reverse holds by ≥20 points. This is the empirical proof that the layers differ. If it fails, the project's central claim is unsupported — investigate Stage 3 and Stage 5 before proceeding.
7. `benford_any` catch rate on `digit_fabrication` exceeds its catch rate on `REAL_ROWS` by a clear margin.
8. Every `precision_at_k` value is in [0,1]; `recall_at_k` is non-decreasing in k.
9. Bootstrap CI computed for AP; lower bound > baseline.
10. All eight figures exist and are >20 KB.
11. `caveats` array in the JSON is non-empty and contains the lower-bound-precision caveat.

**Gate report must record:** the full wide matrix, the headline metrics table for all models, the per-k precision/recall/lift table, the chosen operating point and why, the bootstrap CI, and the honest interpretation paragraph from §7.4.

**Commit:** `stage(07): validation — PR curves, precision@k, bootstrap CIs, method×type matrix`
`git tag stage-07-validation`

---
---

# STAGE 8 — COMPOSITE RISK SCORE & DASHBOARD EXPORT

**Goal:** one interpretable risk score per transaction, a ranked review list, and the data packs that feed Power BI and the public dashboard.
**Estimated time:** 2–3 hours
**Inputs:** everything from Stages 4–7
**Outputs:** `data/processed/dashboard_export.csv`, `data/dashboard/*` (8 files), `reports/metrics/composite_summary.json`

---

## 8.1 Composite score definition

```
if_component      = percentile_rank(if_score_fsb)                 # [0,1]
rules_component   = rule_flag_count / 5                           # [0,1]
benford_component = 1.0 if the row belongs to ANY flagged segment else 0.0

composite_risk = 0.50 * if_component
               + 0.30 * rules_component
               + 0.20 * benford_component
```

Weights come from `cfg.composite.*`. `composite_risk` is in [0,1] by construction —
assert it.

### 8.1.1 Risk banding (for the dashboard)

| Band | Range | Intended meaning |
|---|---|---|
| `CRITICAL` | ≥ 0.80 | Review immediately |
| `HIGH` | 0.60 – 0.80 | Review in this cycle |
| `MEDIUM` | 0.40 – 0.60 | Consider for sample selection |
| `LOW` | < 0.40 | No action |

Report the count and value in each band. Bands are a presentation device — the
underlying continuous score is what ranks.

### 8.1.2 Weight sensitivity (required)

Weights chosen by judgement must be shown to be robust. Compute AP for the composite
under at least five weight vectors:

| Variant | IF | Rules | Benford |
|---|---|---|---|
| Primary | 0.50 | 0.30 | 0.20 |
| IF-heavy | 0.70 | 0.20 | 0.10 |
| Rules-heavy | 0.20 | 0.60 | 0.20 |
| Equal | 0.34 | 0.33 | 0.33 |
| No-Benford | 0.60 | 0.40 | 0.00 |

Report AP and recall@1000 for each in `composite_summary.json` and plot them. State in
the README whether the conclusion is weight-sensitive. If a different weighting is
materially better, **say so and keep the primary anyway** (or switch and log it) — but
do not quietly tune weights against the ground truth and then present the result as if
the weights were chosen a priori. That is fitting to the test set, and an interviewer
may ask.

> **Honesty note the agent must include:** any weighting informed by the labels is,
> strictly, supervised. The primary weights are set a priori by audit judgement; the
> sensitivity analysis is reported as a robustness check, not as a tuning exercise.

## 8.2 `src/composite.py` — specification

```python
def percentile_rank(s: pd.Series) -> pd.Series:
    """Ties averaged, result strictly in [0,1]."""

def compute_composite(df: pd.DataFrame, weights: dict, cfg) -> pd.Series:
    """Implements 8.1. Asserts output range [0,1] and no nulls."""

def assign_band(score: pd.Series, cfg) -> pd.Series:
    """Returns a categorical with the four bands, ordered."""

def weight_sensitivity(df: pd.DataFrame, y_true: np.ndarray,
                       variants: dict[str, dict]) -> pd.DataFrame:
    """AP, recall@1000, precision@100 per variant."""

def top_risk_list(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Top-n by composite_risk, with the reviewer-facing columns of §8.4.
       Sorted descending; ties broken by amount descending (review the bigger
       exposure first — an audit-sensible tie-break, worth one line in the README)."""
```

## 8.3 `dashboard_export.csv` — full schema

| Group | Columns |
|---|---|
| Identity | `txn_id`, `invoice`, `stock_code`, `description`, `customer_id`, `country` |
| Values | `quantity`, `price`, `amount` |
| Time | `invoice_date`, `year`, `month`, `year_month`, `quarter`, `day_of_week`, `day_name`, `hour`, `days_to_month_end`, `is_month_end` |
| Digit | `leading_digit`, `second_digit`, `first_two_digits` |
| Classification | `is_adjustment`, `is_nonpositive_amount`, `has_customer_stats` |
| Rule flags | `flag_duplicate`, `flag_round_number`, `flag_threshold_avoidance`, `flag_period_end`, `flag_off_hours`, `rule_flag_count`, `rule_flag_names`, `flag_reasons` |
| Benford | `benford_flag_country`, `benford_flag_month`, `benford_flag_country_month`, `benford_flag_customer`, `benford_flag_any`, `segment_mad_country_month`, `segment_verdict_country_month` |
| Model | `if_score_fsa`, `if_score_fsb`, `if_pct_fsb`, `if_pred_fsb`, `lof_score`, `lof_in_subsample` |
| Composite | `composite_risk`, `risk_band`, `risk_rank` |
| Ground truth | `is_synthetic_anomaly`, `anomaly_type` — **last two columns, clearly marked** |

> **Why ground truth is in the export:** the Power BI "Model Performance" page needs it.
> It is legitimate *because the export is an evaluation artefact, not a model input*.
> Add a header comment in the data dictionary making that distinction explicit, and
> never join these columns into anything upstream of scoring.

### 8.3.1 Size management

At ~1.08M rows × ~50 columns the CSV will be roughly 350–500 MB. That is fine locally
and git-ignored, but Power BI import will be slow and GitHub cannot hold it. Therefore
also write:

| File | Content | Target size |
|---|---|---|
| `dashboard_export.parquet` | the full frame, compressed | ~60–90 MB |
| `dashboard_export_sample.csv` | a 100k-row stratified sample **containing all injected rows** plus a random real-row sample | <40 MB |

**Power BI sources the Parquet if the connector is available, otherwise the full CSV
locally.** The GitHub repo ships only the aggregates in `data/dashboard/` plus the
sample. Log this decision.

## 8.4 The "for audit review" list — `top_risk_transactions.csv`

Top `cfg.composite.top_n_export` (default 50) rows, with reviewer-facing columns only:

`risk_rank, txn_id, invoice, invoice_date, customer_id, country, stock_code,
description, quantity, price, amount, composite_risk, risk_band, rule_flag_names,
flag_reasons, benford_segment, segment_verdict, if_pct_fsb, suggested_procedure`

**`suggested_procedure`** is generated from the flags fired — a small rules-to-text map,
e.g.:

| Dominant signal | Suggested procedure |
|---|---|
| `flag_duplicate` | "Agree to supporting sales order and despatch note; confirm not a duplicate of invoice {x}." |
| `flag_threshold_avoidance` | "Obtain the approval matrix; confirm authorisation limit and whether the item was split." |
| `flag_round_number` | "Inspect for evidence of manual entry; agree to third-party documentation." |
| `flag_period_end` | "Cut-off testing: agree despatch date to the period in which revenue was recognised." |
| `flag_off_hours` | "Review system access logs for the posting user and time." |
| High IF score only | "Analytical review: compare to customer's historic transaction profile; obtain explanation for the variance." |
| Benford segment only | "Extend testing across the segment; the item is flagged by population-level analytics rather than item-level attributes." |

This column is what converts a data-science output into an **audit deliverable**, and it
is the thing an audit interviewer will react to most. Do not skip it.

## 8.5 The eight dashboard data files (`data/dashboard/`, all committed)

| File | Grain | Key columns |
|---|---|---|
| `kpi_summary.json` | 1 object | total_txns, total_value, aggregate_mad, aggregate_verdict, pct_flagged_high_risk, n_injected, anomaly_rate, headline AP, headline recall, n_segments_flagged, date range |
| `benford_aggregate.csv` | 9 rows | digit, observed_count, observed_prop, expected_prop, abs_diff, z_stat |
| `benford_segments.csv` | 1 per segment | segment_dim, segment_value, n, mad, verdict, chi2, chi2_p, max_dev_digit, is_flagged |
| `benford_by_segment_digit.csv` | segment × digit | segment_dim, segment_value, digit, observed_prop, expected_prop — **needed so the web dashboard can redraw the digit chart per segment without the full dataset** |
| `monthly_trend.csv` | 1 per month | year_month, txn_count, total_value, flagged_count, pct_flagged, mad, pct_last_2_days |
| `segment_heatmap.csv` | country × month | country, year_month, txn_count, flagged_count, pct_flagged, mad, verdict |
| `method_comparison.csv` | type × method | from Stage 7 |
| `model_metrics.json` | 1 object | from Stage 7 |
| `top_risk_transactions.csv` | 50 rows | from §8.4 |

Plus `top_risk_5000.csv` (the top 5,000 rows, reviewer columns only) so the public
dashboard's explorer table has something to page through without shipping 1M rows.
**Hard cap: the whole `data/dashboard/` directory must stay under 25 MB** — asserted in
the gate.

## 8.6 Stage 8 Gate — `checks/gate_08.py`

1. `composite_risk` ∈ [0,1], no nulls, >100,000 distinct values (i.e. genuinely continuous).
2. `risk_band` has all four levels present; counts reported.
3. `risk_rank` is a dense 1..N ranking with no gaps and no ties at rank level.
4. `dashboard_export.parquet` row count == population; column set matches §8.3 exactly (assert the list, order included).
5. `top_risk_transactions.csv` has exactly `top_n_export` rows, is sorted descending by `composite_risk`, and every row has a non-empty `suggested_procedure`.
6. The composite's AP (from Stage 7) is **≥ the best single method's AP**. If it is not, the weighting is actively harmful — report it honestly, try the sensitivity variants, and if none beats the best single method, say so in the README rather than hiding it.
7. Weight sensitivity table has ≥5 variants with AP computed for each.
8. All nine `data/dashboard/` files exist; total directory size < 25 MB.
9. `dashboard_export_sample.csv` contains 100% of injected rows.
10. `kpi_summary.json` values agree with `model_metrics.json` and `benford_summary.json` (cross-file consistency assertion — this catches copy-paste drift, which is the #1 source of wrong numbers in a portfolio README).
11. Determinism: re-running Stage 8 produces an identical `top_risk_transactions.csv` hash.

**Gate report must record:** band counts and values, the weight sensitivity table, the top 10 rows of the review list (this table goes straight into the README and the PDF workpaper), and the `data/dashboard/` file sizes.

**Commit:** `stage(08): composite risk score, banding, weight sensitivity, review list, dashboard data packs`
`git tag stage-08-export`

---
---

# STAGE 9 — POWER BI DASHBOARD

**Goal:** a five-page `.pbix` that a non-technical audit manager could navigate unaided.
**Estimated time:** 5–8 hours (the longest single stage; most of it is manual UI work)
**Inputs:** `data/dashboard/*` and `dashboard_export.parquet` (or the sample CSV)
**Outputs:** `dashboard/audit_analytics.pbix`, `dashboard/theme.json`, `dashboard/POWERBI_BUILD_NOTES.md`, `docs/screenshots/*.png`

---

## 9.0 Executor note

Power BI Desktop is a GUI application; an autonomous agent cannot click through it.
Therefore this stage splits:

- **Agent's job:** prepare every input the dashboard needs — the data files, the
  `theme.json`, the exact DAX for every measure (written into
  `POWERBI_BUILD_NOTES.md` ready to paste), the page-by-page visual specification, and
  the star-schema model diagram. Then **stop and hand over**, with a checklist.
- **Human's job:** install Power BI Desktop, load the model, paste the measures, lay out
  the five pages following the spec, export screenshots to `docs/screenshots/`.

The agent must write `POWERBI_BUILD_NOTES.md` so completely that building the dashboard
is mechanical: no design decisions left open, every field well specified.

## 9.1 Install

Power BI Desktop, free, Windows only: Microsoft Store ("Power BI Desktop") or
`https://powerbi.microsoft.com/desktop/`. **No account is required to use Desktop and
save a `.pbix` locally.** Signing in to the *Service* requires a work/school account,
which a gmail address cannot create — hence Stage 10.

## 9.2 Data model (star schema — do not load one flat table)

**Fact table**
- `fact_transactions` ← `dashboard_export.parquet` (or `dashboard_export_sample.csv`)

**Dimension tables**
- `dim_date` — generated in Power Query or DAX (`CALENDAR(MIN, MAX)`), with
  Year, Quarter, Month, MonthName, MonthYear (sorted by a numeric key), Day,
  DayOfWeek, DayName, IsMonthEnd. **Mark as a date table.**
- `dim_country` — distinct countries from the fact table
- `dim_customer` — distinct customers with their segment stats
- `dim_digit` — 9 rows: `digit`, `expected_prop` (the Benford constants).
  **This table is the key to dynamic DAX Benford** — it is a static lookup, not related
  to the fact table by a physical relationship; digit matching is done in the measure.
- `benford_segments` — from `benford_segments.csv` (precomputed MAD and verdicts)
- `method_comparison` — from `method_comparison.csv`
- `model_metrics` — a small unpivoted table of metric name/value pairs

**Relationships**
```
dim_date[Date]        1 --- * fact_transactions[invoice_date_only]
dim_country[Country]  1 --- * fact_transactions[country]
dim_customer[CustID]  1 --- * fact_transactions[customer_id]
benford_segments      -- no physical relationship; filtered via measures / or
                         relate on a composite segment key if simpler
```

Hide from report view: every raw key column, `line_no`, and the two ground-truth columns
on all pages except Model Performance.

## 9.3 DAX measures — paste-ready

```dax
-- ===== Core =====
Total Transactions = COUNTROWS ( fact_transactions )

Total Value = SUM ( fact_transactions[amount] )

Total Value (Positive) =
CALCULATE ( [Total Value], fact_transactions[amount] > 0 )

Avg Transaction Value = DIVIDE ( [Total Value], [Total Transactions] )

-- ===== Flagging =====
Flagged Transactions =
CALCULATE ( [Total Transactions], fact_transactions[rule_flag_count] >= 1 )

High Risk Transactions =
CALCULATE ( [Total Transactions],
            fact_transactions[risk_band] IN { "HIGH", "CRITICAL" } )

% Flagged = DIVIDE ( [Flagged Transactions], [Total Transactions] )

% High Risk = DIVIDE ( [High Risk Transactions], [Total Transactions] )

Flagged Value =
CALCULATE ( [Total Value], fact_transactions[risk_band] IN { "HIGH", "CRITICAL" } )

-- ===== Benford: dynamic, responds to every slicer =====
Benford Observed Count =
CALCULATE (
    COUNTROWS ( fact_transactions ),
    FILTER ( fact_transactions,
             fact_transactions[leading_digit] = SELECTEDVALUE ( dim_digit[digit] )
             && fact_transactions[amount] >= 1
             && fact_transactions[is_adjustment] = FALSE )
)

Benford Population =
CALCULATE (
    COUNTROWS ( fact_transactions ),
    FILTER ( fact_transactions,
             fact_transactions[amount] >= 1
             && fact_transactions[is_adjustment] = FALSE )
)

Benford Observed % =
DIVIDE ( [Benford Observed Count], [Benford Population] )

Benford Expected % = SELECTEDVALUE ( dim_digit[expected_prop] )

Benford Expected Count = [Benford Expected %] * [Benford Population]

Benford Deviation = [Benford Observed %] - [Benford Expected %]

-- MAD across the 9 digits, recomputed inside the current filter context
Benford MAD =
VAR Pop = [Benford Population]
RETURN
IF (
    Pop < 1000,
    BLANK (),
    AVERAGEX (
        dim_digit,
        VAR d        = dim_digit[digit]
        VAR expected = dim_digit[expected_prop]
        VAR obs =
            DIVIDE (
                CALCULATE ( COUNTROWS ( fact_transactions ),
                            FILTER ( fact_transactions,
                                     fact_transactions[leading_digit] = d
                                     && fact_transactions[amount] >= 1
                                     && fact_transactions[is_adjustment] = FALSE ) ),
                Pop
            )
        RETURN ABS ( obs - expected )
    )
)

Benford Verdict =
VAR m = [Benford MAD]
RETURN
SWITCH (
    TRUE (),
    ISBLANK ( m ),  "Insufficient data (n < 1,000)",
    m < 0.006,      "Close conformity",
    m < 0.012,      "Acceptable conformity",
    m < 0.015,      "Marginal conformity",
                    "NONCONFORMITY — review"
)

Benford Verdict Colour =
VAR m = [Benford MAD]
RETURN
SWITCH ( TRUE (),
    ISBLANK ( m ), "#9AA0A6",
    m < 0.006,     "#1E8E3E",
    m < 0.012,     "#8AB825",
    m < 0.015,     "#F9AB00",
                   "#D93025" )

Benford Chi Square =
VAR Pop = [Benford Population]
RETURN
IF ( Pop < 1000, BLANK (),
    SUMX (
        dim_digit,
        VAR d = dim_digit[digit]
        VAR e = dim_digit[expected_prop] * Pop
        VAR o = CALCULATE ( COUNTROWS ( fact_transactions ),
                    FILTER ( fact_transactions,
                             fact_transactions[leading_digit] = d
                             && fact_transactions[amount] >= 1
                             && fact_transactions[is_adjustment] = FALSE ) )
        RETURN DIVIDE ( ( o - e ) ^ 2, e )
    )
)

Chi Square Caveat =
"At n = " & FORMAT ( [Benford Population], "#,##0" ) &
" the chi-square test rejects conformity for deviations of no practical " &
"significance (excess power). MAD is the primary criterion."

-- ===== Model performance (from the unpivoted metrics table) =====
Precision = CALCULATE ( MAX ( model_metrics[value] ),
                        model_metrics[metric] = "precision" )
Recall    = CALCULATE ( MAX ( model_metrics[value] ),
                        model_metrics[metric] = "recall" )
F1        = CALCULATE ( MAX ( model_metrics[value] ),
                        model_metrics[metric] = "f1" )
Average Precision = CALCULATE ( MAX ( model_metrics[value] ),
                        model_metrics[metric] = "average_precision" )

True Positives  = CALCULATE ( [Total Transactions],
                    fact_transactions[is_synthetic_anomaly] = 1,
                    fact_transactions[risk_band] IN { "HIGH", "CRITICAL" } )
False Positives = CALCULATE ( [Total Transactions],
                    fact_transactions[is_synthetic_anomaly] = 0,
                    fact_transactions[risk_band] IN { "HIGH", "CRITICAL" } )
False Negatives = CALCULATE ( [Total Transactions],
                    fact_transactions[is_synthetic_anomaly] = 1,
                    NOT fact_transactions[risk_band] IN { "HIGH", "CRITICAL" } )
True Negatives  = CALCULATE ( [Total Transactions],
                    fact_transactions[is_synthetic_anomaly] = 0,
                    NOT fact_transactions[risk_band] IN { "HIGH", "CRITICAL" } )
```

> **Performance warning.** `Benford MAD` iterates 9 digits × a filtered COUNTROWS over
> a million-row fact table for every filter context. On the full dataset this can be
> slow in a matrix visual with many rows. Mitigations, in order:
> 1. Use `dashboard_export_sample.csv` (100k rows) as the fact table for the `.pbix`,
>    and state on the page that the Benford visual uses a sample while the precomputed
>    `benford_segments` table carries full-population verdicts.
> 2. Add a precomputed `benford_by_segment_digit.csv` table and drive the chart from it
>    for segment views, reserving the dynamic measure for the aggregate page.
> 3. Reduce the fact table's column count before import (Power Query → Remove Columns).
>
> **Pre-registered choice (PD-14): do both 1 and 2** — dynamic DAX on the aggregate page
> so slicers feel live, precomputed tables for the segment matrix. Document it on the
> page itself with a small text box, and in `POWERBI_BUILD_NOTES.md`.

## 9.4 Page specifications

### Page 1 — Overview

| Element | Visual | Fields |
|---|---|---|
| KPI row (5 cards) | Card | `Total Transactions`, `Total Value`, `Benford MAD` (+ `Benford Verdict` as the subtitle), `% High Risk`, `Flagged Value` |
| Volume over time | Line chart | Axis `dim_date[MonthYear]`, Values `Total Transactions`, secondary line `% Flagged` |
| Value by country | Bar (top 10) | Axis `country`, Values `Total Value` |
| Risk band split | Donut | Legend `risk_band`, Values `Total Transactions` |
| Narrative | Text box | 3 sentences: population, method, headline finding. Written from the real numbers. |
| Slicers | Date range, Country | applies to all page visuals |

### Page 2 — Benford's Law View

| Element | Visual | Fields |
|---|---|---|
| Observed vs expected | Clustered column | Axis `dim_digit[digit]`, Values `Benford Observed %` and `Benford Expected %`; y-axis formatted % |
| Deviation | Column | Axis `dim_digit[digit]`, Values `Benford Deviation`, conditional colour red/green on sign |
| Conformity card | Card | `Benford Verdict`, background colour driven by `Benford Verdict Colour` |
| MAD card | Card | `Benford MAD`, 4 decimal places |
| Population card | Card | `Benford Population` |
| Chi-square + caveat | Card + text box | `Benford Chi Square`, `Chi Square Caveat` |
| Segment table | Table | `benford_segments`: segment_dim, segment_value, n, mad, verdict; conditional formatting on mad using the four Nigrini bands |
| Slicers | Country, Year-Month, Customer (top 200) | **the chart recalculates live** |

### Page 3 — Anomaly Explorer

| Element | Visual | Fields |
|---|---|---|
| Ranked table | Table | risk_rank, txn_id, invoice_date, customer_id, country, amount, composite_risk, risk_band, rule_flag_names; sorted by composite_risk desc; data bars on composite_risk |
| Filters | Slicers | risk_band, country, year_month, each rule flag (as a toggle), amount range |
| Alert-budget control | Numeric range slicer or What-if parameter `Review Budget` (50–5,000) | plus a card showing how many injected anomalies fall inside the budget — **a genuinely impressive interactive touch** |
| Drill-through page | "Transaction Detail" | All fields for one txn_id: full attributes, every flag with its `flag_reasons` text, the customer's amount distribution with this transaction marked, the segment's Benford chart, and the `suggested_procedure` text |

### Page 4 — Model Performance

| Element | Visual | Fields |
|---|---|---|
| Metric cards | Card ×4 | Precision, Recall, F1, Average Precision |
| PR curve | Line chart | from a small `pr_curve_points.csv` the agent must export in Stage 7 (thin it to ~200 points) |
| Confusion matrix | Matrix | rows Actual, cols Predicted, values counts; conditional formatting |
| Method × type matrix | Matrix | rows anomaly_type, cols method, values pct_caught, colour scale — **the hero visual** |
| Precision@k | Line chart | from `precision_at_k` unpivoted into a small table |
| Caveat box | Text | the lower-bound-precision caveat, verbatim from `model_metrics.json` |

### Page 5 — Segment Risk Heatmap

| Element | Visual | Fields |
|---|---|---|
| Heatmap | Matrix | Rows `country` (top 20), Cols `dim_date[MonthYear]`, Values `% Flagged` or `Flagged Transactions`, conditional background colour scale |
| Second matrix | Matrix | same grid, Values `Benford MAD` from `segment_heatmap.csv`, coloured by the Nigrini bands |
| Detail table | Table | the flagged segments, sorted by MAD desc |
| Slicers | Minimum segment size, risk band | |

## 9.5 `dashboard/theme.json`

A single custom theme so every visual is consistent. Minimum content:

```json
{
  "name": "Audit Analytics",
  "dataColors": ["#1F4E79", "#2E75B6", "#9DC3E6", "#D93025", "#F9AB00",
                 "#1E8E3E", "#7F7F7F", "#404040"],
  "background": "#FFFFFF",
  "foreground": "#1F1F1F",
  "tableAccent": "#1F4E79",
  "visualStyles": {
    "*": {
      "*": {
        "title": [{ "fontSize": 12, "fontFamily": "Segoe UI Semibold" }],
        "background": [{ "show": true, "color": { "solid": { "color": "#FFFFFF" } } }],
        "border": [{ "show": true, "color": { "solid": { "color": "#E0E0E0" } } }]
      }
    }
  }
}
```

Red is reserved for risk/nonconformity only — never for a neutral series.

## 9.6 `POWERBI_BUILD_NOTES.md` — the handover document the agent writes

Must contain, in this order:
1. Exactly which file to load and how (Get Data → Parquet/Text-CSV; the folder path).
2. Power Query steps applied, listed (type changes, the `invoice_date_only` column, removed columns).
3. The full list of tables and relationships with cardinality and cross-filter direction.
4. Every DAX measure from §9.3, in a copy-paste block, in creation order (measures that reference others come later).
5. Per page: a wireframe sketch (ASCII is fine), each visual's type, its exact field wells, its formatting deviations from the theme, and its title text.
6. The drill-through configuration steps.
7. The What-if parameter setup for the review budget.
8. Screenshot checklist: which 5 screenshots to take, at what window size (1920×1080), saved to `docs/screenshots/page1_overview.png` etc.
9. Known performance caveats and what was done about them.

## 9.7 Stage 9 Gate — `checks/gate_09.py` (partly manual)

Automated:
1. `dashboard/audit_analytics.pbix` exists and is >100 KB.
2. `dashboard/theme.json` exists and is valid JSON.
3. `dashboard/POWERBI_BUILD_NOTES.md` exists and contains every measure name from §9.3 (string search).
4. `docs/screenshots/` contains ≥5 PNGs, each >50 KB and ≥1280 px wide.
5. `pr_curve_points.csv` and the unpivoted `precision_at_k` table exist in `data/dashboard/`.

Manual checklist (recorded in the gate report, ticked by the human):
- [ ] All 5 pages render with no error visuals
- [ ] Changing the Country slicer changes the Benford chart and the MAD card
- [ ] The MAD card shows "Insufficient data" for a segment with n<1,000
- [ ] Drill-through from the Anomaly Explorer opens Transaction Detail for the right row
- [ ] The What-if review-budget parameter updates the caught-anomalies card
- [ ] The method × type matrix matches `method_comparison.csv` for three spot-checked cells
- [ ] No ground-truth column is visible on pages 1, 2, 3 or 5
- [ ] File saves and reopens cleanly

**Commit:** `stage(09): Power BI five-page dashboard, DAX measures, theme, screenshots`
`git tag stage-09-powerbi`

---

**END OF STAGES 7–9 — proceed to `04_STAGES_10-13.md`**
