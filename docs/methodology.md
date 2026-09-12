# Methodology

Technical reference for `benfords-audit-analytics`. This is the long-form account —
every formula, every threshold with its source, every pre-registered decision, and the
judgement-call log — for a reviewer who wants to verify the work rather than take the
README's word for it.

## 1. Dataset

**Online Retail II** (UCI Machine Learning Repository, dataset 502), CC BY 4.0. Two
workbook sheets ("Year 2009-2010", "Year 2010-2011") combined to 1,067,371 raw rows.
Column rename map, non-product stock-code list, and the derived `amount = quantity *
price` field are fixed in `src/config.py` / `config.yaml`.

## 2. Cleaning (Stage 2)

Every row removed is counted in `reports/metrics/cleaning_ledger.json`; the pipeline
asserts `rows_in == rows_out + sum(removed)`. Pre-registered decisions (`DECISIONS.md`
"Pre-registered defaults"):

- **PD-01** — missing `customer_id` retained as `"UNASSIGNED"`, excluded only from
  customer-level z-score features (which get `has_customer_stats = False`, not dropped).
- **PD-02** — cancellations (`invoice` starts with `C`) moved to a separate frame,
  excluded from Benford and the model population, but counted and reported.
- **PD-03** — the Benford population is non-cancelled, non-adjustment rows with
  `amount >= 1.00`.
- **PD-04** — zero/negative-amount rows retained, flagged `is_nonpositive_amount`,
  excluded from Benford only.
- **PD-05** — duplicate-candidate window: same `customer_id`, same rounded `amount`
  (2dp), `invoice_date` within ±1 day, different `invoice`.

## 3. Synthetic anomaly injection (Stage 3)

Real audit engagement data is confidential and unlabelled — there is no way to measure
precision/recall against it. A controlled set of anomalies is injected instead, at
**1.5% of the cleaned population (PD-06)**, split across six archetypes:

| Archetype | Mechanism | Audit meaning |
|---|---|---|
| `duplicate` | Near-identical transaction re-posted within ±1 day (`injection.duplicate.date_jitter_days`) | Duplicate billing |
| `threshold_avoidance` | Amount placed just below an authorisation threshold (`injection.threshold_avoidance.thresholds`, 2% band) | Structuring |
| `round_number` | Amount set to a round figure (1000, 5000, 10000, 2000, 500) | Manual journal entries |
| `digit_fabrication` | Leading digit resampled from a skewed weight table favouring 7/8/9 | Fabricated figures |
| `timing` | Posted in the last `injection.timing.period_end_days` days of the month, or 00:00-05:59 | Cut-off manipulation / off-hours posting |
| `extreme_outlier` | Amount multiplied by 10-50x | Gross misstatement |

**Leakage Firewall** (`plan/00_MASTER_PLAN.md` sec 6): `txn_id` is assigned only after
injected and real rows are concatenated and sorted by `(invoice_date, invoice,
stock_code, line_no)`, so injected rows interleave naturally and carry no ID- or
order-based signal. `checks/gate_03.py` fits a depth-3 decision tree on ID/index-derived
features alone predicting `is_synthetic_anomaly`; ROC-AUC must stay below 0.55.

Global seed = **42** everywhere (**PD-07**), via `numpy.random.default_rng(42)` and
`random_state=42`.

## 4. Benford's Law (Stage 4)

For a population of amounts, the leading digit *d* should occur with probability
`log10(1 + 1/d)` (Newcomb-Benford distribution). Two conformity statistics are computed:

- **Mean Absolute Deviation (MAD)** = `mean(|observed_i - expected_i|)` across the 9
  digits. Nigrini's thresholds (`config.yaml benford.mad_thresholds`): Close <0.006,
  Acceptable <0.012, Marginal <0.015, Nonconformity >=0.015. **MAD is sample-size
  independent and is the primary conformity criterion.**
- **Chi-square** is reported alongside, with an explicit caveat: at the population
  sizes here (n ~ 10^5-10^6), chi-square rejects conformity for deviations of no
  practical significance (the "excess power" problem — `plan/00_MASTER_PLAN.md` Risk
  R3). It is informative, not decisive.

Segments smaller than **1,000 rows (PD-08)** get verdict `INSUFFICIENT_DATA`, never a
false conformity/nonconformity call on too little data. Segmentation dimension actually
implemented: combined `(country, year_month)` — see `DECISIONS.md` D-0003/D-0004 for the
finding that all 66 segments large enough to test were classified NONCONFORMING in this
run, and what that does and does not mean.

## 5. Rule-based exception testing (Stage 5)

Ten deterministic tests (`src/rules.py`): `DUPLICATE_INVOICE`, `SPLIT_AMOUNT`,
`LARGE_AMOUNT`, `ROUND_NUMBER`, `ROUND_DOLLARS`, `HIGH_QUANTITY`, `ODD_QUANTITY`,
`OFF_HOUR`, `NEGATIVE_ADJUSTMENT`, `ZERO_QUANTITY`. Business hours default
07:00-19:59 all days (**PD-12** — Sunday is a live trading day in this dataset and is
*not* treated as off-hours), empirically checked against the hour-of-day histogram
(`reports/figures/hour_distribution.png`) per `plan/00_MASTER_PLAN.md` sec 2.7.

## 6. Isolation Forest / LOF (Stage 6)

Leakage-safe feature set: `amount, quantity, price, hour, day_of_week, cust_txn_count,
cust_amount_mean, cust_amount_std, rule_flag_count` — explicitly excludes
`is_synthetic_anomaly`, `anomaly_type`, `txn_id`. IsolationForest
(`n_estimators=200, max_samples=256`) and LOF (`n_neighbors=20`) scores are min-max
normalised to `[0,1]`, higher = more anomalous.

**Known constraint (`DECISIONS.md` D-0003):** this run scored a 50,000-row sample of
the 1,030,804-row cleaned population, one feature set, one contamination level — not
the full-population FS-A/FS-B x 4-contamination grid the master plan specifies. Every
population figure from Stage 7 onward is computed on n=50,000 and this is disclosed
everywhere the population size is quoted.

## 7. Validation (Stage 7)

**Framing that must not be lost:** positives are *only* the injected rows. A method
that correctly flags a genuine, unlabelled anomaly already in the real ledger is scored
here as a false positive — so **every precision figure is a lower bound**. Recall is
trustworthy (it is measured against a complete, known positive set); precision is not.

Ranking metrics lead: **Average Precision** (`sklearn.metrics.average_precision_score`)
and **precision/recall/lift@k** for k in {50,100,250,500,1000,5000}, with a 200-resample
bootstrap 95% CI on AP. Binary confusion-matrix metrics at a contamination-consistent
threshold (98.5th percentile, matching the 1.5% injection rate) are secondary.

**The anomaly-type x detection-method matrix** (`data/dashboard/method_comparison.csv`)
is the project's central artefact — it empirically tests whether the three layers catch
*different* classes of manipulation. In this run they do not cleanly split along the
plan's template lines: rule-based checks dominate raw catch-rate on every injected type
at the matched alert budget, and the segmented Benford flag over-triggers (fires on
~93% of every population, real or injected, because all 66 assessed segments were
NONCONFORMING). This is reported as found — see `DECISIONS.md` D-0004 — rather than
tuned until it matches the expected narrative, which the master plan itself calls a
worse failure mode (sec 8.1.2's honesty note, applied here by extension).

## 8. Composite risk score (Stage 8)

```
if_component      = percentile_rank(if_score)            # [0,1], average-tie rank
rules_component    = min(rule_flag_count, 5) / 5          # [0,1]
benford_component  = 1.0 if segment is NONCONFORMING else 0.0

composite_risk = 0.50 * if_component + 0.30 * rules_component + 0.20 * benford_component
```

Weights (**PD-11**) are set a priori by audit judgement — not tuned against the ground
truth. A 5-variant weight-sensitivity table (IF-heavy, Rules-heavy, Equal, No-Benford)
is reported as a robustness check in `reports/metrics/composite_summary.json`; the
Primary weighting is kept as the headline even where another variant scores marginally
higher, and this is disclosed rather than hidden (plan sec 8.1.2).

Risk bands: CRITICAL >=0.80, HIGH 0.60-0.80, MEDIUM 0.40-0.60, LOW <0.40 — a
presentation device over the continuous score, which is what actually ranks the review
queue.

## 9. Composite weights (config.yaml, cfg.composite)

| Component | Weight |
|---|---|
| Isolation Forest percentile rank | 0.50 |
| Rule flag count / 5 | 0.30 |
| Benford segment flag | 0.20 |

## 10. Pre-registered decisions not otherwise covered above

| ID | Decision |
|---|---|
| PD-09 | Primary Isolation Forest contamination = 0.015. |
| PD-10 | Two feature sets (FS-A/FS-B) were specified; this run used one feature set (see D-0003). |
| PD-13 | Currency is GBP throughout; no FX conversion. |
| PD-14 | Power BI Benford visuals (not built this run, see D-0001) would use precomputed segment stats for MAD/verdict and DAX for the observed-vs-expected bars. |

## 11. Full judgement-call log

See `DECISIONS.md` for the complete, append-only log with dates, options considered,
rationale and reversibility for every non-pre-registered decision (D-0001 through
D-0004 as of this run): Power BI scope (D-0001), the public-dashboard delivery split
(D-0002), the scored-sample population (D-0003), and the complementarity/Benford-flag
honest finding (D-0004).

## 12. Language discipline

Throughout the README, the PDF workpaper and this document: the pipeline *ranks
transactions for review*. It does not "detect fraud", and a Benford exception or a high
composite score is a screening result that directs further audit procedures, not
evidence of misstatement on its own.
