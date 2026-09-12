# STAGES 4–6 — Benford's Law, Rule-Based Checks, Isolation Forest

**Document ID:** `02_STAGES_4-6`
**Prerequisite:** Stage 3 gate PASSED.
**Covers:** Stage 4 Benford's Law (aggregate + segmented) · Stage 5 Rule-based red flags · Stage 6 Isolation Forest & LOF

> Stages 4 and 5 are independent and may be built in either order. Both must be
> complete before Stage 6, because Stage 6 consumes the rule flags and the Benford
> segment verdicts as features/context.

---
---

# STAGE 4 — BENFORD'S LAW ANALYSIS

**Goal:** test digit conformity at the aggregate level and at segment level, classify each segment using Nigrini's MAD thresholds, and identify the nonconforming segments.
**Estimated time:** 3–4 hours
**Inputs:** `data/processed/transactions_labeled.parquet`
**Outputs:** `benford_aggregate.csv`, `benford_segments.csv`, `benford_second_digit.csv`, `benford_first_two.csv`, `reports/metrics/benford_summary.json`, figures

---

## 4.1 The mathematics (implement exactly this)

### 4.1.1 Expected distributions

**First digit** `d ∈ {1..9}`:
```
P(d) = log10(1 + 1/d)
```
Reference values (assert your implementation reproduces these to 6 dp):

| d | P(d) |
|---|---|
| 1 | 0.301030 |
| 2 | 0.176091 |
| 3 | 0.124939 |
| 4 | 0.096910 |
| 5 | 0.079181 |
| 6 | 0.066947 |
| 7 | 0.057992 |
| 8 | 0.051153 |
| 9 | 0.045757 |
| **Σ** | **1.000000** |

**Second digit** `d ∈ {0..9}`:
```
P(d) = Σ_{k=1}^{9} log10(1 + 1/(10k + d))
```
Reference: P(0)=0.11968, P(1)=0.11389, P(2)=0.10882, P(3)=0.10433, P(4)=0.10031,
P(5)=0.09668, P(6)=0.09337, P(7)=0.09035, P(8)=0.08757, P(9)=0.08500.

**First two digits** `d ∈ {10..99}`:
```
P(d) = log10(1 + 1/d)
```

### 4.1.2 Leading-digit extraction

**Do not use string slicing on a float.** Floating-point repr (`9.999999999999998`) will corrupt digits. Use either:

```
d1 = floor(amount / 10 ** floor(log10(amount)))
```
with a guard for `amount <= 0`, **or** format via `Decimal` at fixed precision. Whichever is chosen, the implementation must pass this unit check:

| amount | d1 | d2 | d12 |
|---|---|---|---|
| 1.00 | 1 | 0 | 10 |
| 9.99 | 9 | 9 | 99 |
| 10.00 | 1 | 0 | 10 |
| 99.99 | 9 | 9 | 99 |
| 100.00 | 1 | 0 | 10 |
| 1000.00 | 1 | 0 | 10 |
| 1999.99 | 1 | 9 | 19 |
| 0.99 | *excluded* | — | — |
| 4567.89 | 4 | 5 | 45 |

### 4.1.3 Chi-square goodness of fit

```
chi2 = Σ_i (O_i − E_i)² / E_i          where E_i = N * P(i)
df   = k − 1                            (8 for first digit, 9 for second, 89 for first-two)
critical value @ α=0.05, df=8  : 15.507
critical value @ α=0.05, df=9  : 16.919
critical value @ α=0.05, df=89 : 112.022
```

### 4.1.4 MAD (Mean Absolute Deviation) — the primary verdict

```
MAD = (1/k) * Σ_i | AP_i − EP_i |
```
where `AP_i` = actual proportion, `EP_i` = expected proportion, `k` = number of bins.

**Nigrini conformity thresholds — first digit** (from `config.yaml`):

| MAD range | Verdict |
|---|---|
| 0.000 – 0.006 | `CLOSE_CONFORMITY` |
| 0.006 – 0.012 | `ACCEPTABLE_CONFORMITY` |
| 0.012 – 0.015 | `MARGINAL_CONFORMITY` |
| > 0.015 | `NONCONFORMITY` |

**Second digit:** 0.000–0.008 / 0.008–0.010 / 0.010–0.012 / >0.012
**First two digits:** 0.0000–0.0012 / 0.0012–0.0018 / 0.0018–0.0022 / >0.0022

These differ by test — hard-code all three sets in `config.yaml` under
`benford.mad_thresholds_first`, `_second`, `_first_two`. Using the first-digit
thresholds for a first-two-digit test is a real and common error; the plan calls it out
explicitly so the agent does not make it.

### 4.1.5 Per-digit Z-statistic (which digit is the problem?)

```
        | AP − EP | − (1 / (2N))          <- continuity correction, applied only if
Z = ---------------------------------        it is smaller than |AP − EP|
       sqrt( EP * (1 − EP) / N )
```
|Z| > 1.96 → that digit's deviation is significant at 5%.
Report the per-digit Z table for the aggregate and for every flagged segment. This is
what turns "the segment fails" into "the segment fails *because digit 9 occurs 3.2×
more often than expected*", which is the sentence that belongs in an audit workpaper.

### 4.1.6 Mantissa / KS test (optional, `run_extra_tests`)

Compute the mantissa `m = log10(amount) mod 1`. Under Benford, `m ~ Uniform(0,1)`.
Report the KS statistic and p-value, plus mantissa mean (expected 0.5) and variance
(expected 1/12 ≈ 0.0833). Cheap to add and impressive in an interview.

---

## 4.2 ⚠ THE EXCESS POWER PROBLEM — DO NOT GET THIS WRONG

With N ≈ 1,000,000, the chi-square test has enormous statistical power. It will reject
conformity for deviations far too small to matter economically. **Expect chi-square to
reject the null on the aggregate population even if the ledger is perfectly normal.**

**Therefore:**

- **MAD is the primary verdict.** It is sample-size independent.
- Chi-square is reported **alongside** MAD, always with the caveat printed next to it.
- The README and the workpaper must contain a short paragraph explaining this. It is
  one of the strongest signals of genuine understanding you can put in a portfolio
  project, and the absence of it is the clearest tell of a copied tutorial.
- `benford_summary.json` must carry a field:
  `"chi2_caveat": "At N=<actual>, chi-square rejects conformity for deviations of no practical significance (Nigrini's excess power problem). MAD is used as the primary conformity criterion."`

**Do not** "fix" a failing chi-square by sampling down the data to make the p-value
pass. If the agent wants to show the effect, it may *additionally* report chi-square at
N = 5,000 / 50,000 / full as a sensitivity exhibit — that is a genuinely good exhibit.

---

## 4.3 `src/benford.py` — specification

```python
BENFORD_FIRST:  np.ndarray        # shape (9,),  index 0 -> digit 1
BENFORD_SECOND: np.ndarray        # shape (10,), index 0 -> digit 0
BENFORD_FIRST_TWO: np.ndarray     # shape (90,), index 0 -> 10

def first_digit(amount: pd.Series) -> pd.Series:
    """Vectorised leading-digit extraction. Returns Int8 with <NA> for amount < 1."""

def second_digit(amount: pd.Series) -> pd.Series: ...
def first_two_digits(amount: pd.Series) -> pd.Series: ...

def benford_population(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Apply PD-03: not a cancellation (already excluded), is_adjustment == False,
    amount >= cfg.cleaning.min_benford_amount.
    Logs how many rows each filter removed. Returns the filtered frame."""

def digit_frequencies(digits: pd.Series, expected: np.ndarray,
                      bins: np.ndarray) -> pd.DataFrame:
    """Returns one row per bin:
        digit, observed_count, observed_prop, expected_prop, expected_count,
        abs_diff, pct_diff, z_stat, z_significant"""

def conformity_stats(freq: pd.DataFrame, n: int, test: str) -> dict:
    """Returns {n, mad, mad_verdict, chi2, chi2_df, chi2_p, chi2_critical,
                chi2_reject, ssd, max_abs_dev_digit, max_abs_dev_value,
                ks_stat, ks_p, mantissa_mean, mantissa_var}
       SSD (Nigrini's sum of squared deviations) = 10000 * Σ (AP-EP)^2 — report it too."""

def classify_mad(mad: float, test: str, cfg) -> str:
    """Returns CLOSE_CONFORMITY / ACCEPTABLE_CONFORMITY /
       MARGINAL_CONFORMITY / NONCONFORMITY using the test-specific thresholds."""

def run_aggregate(df: pd.DataFrame, cfg) -> tuple[pd.DataFrame, dict]: ...

def run_segmented(df: pd.DataFrame, by: list[str], cfg) -> pd.DataFrame:
    """For each segment defined by the `by` columns:
        - if n < cfg.benford.min_segment_n -> verdict INSUFFICIENT_DATA, stats NaN
        - else compute full conformity_stats
    Returns one row per segment with:
        segment_dim, segment_value, n, mad, mad_verdict, chi2, chi2_p,
        max_dev_digit, max_dev_pct, top_z_digit, top_z_value, is_flagged
    `is_flagged` = mad_verdict in {MARGINAL_CONFORMITY, NONCONFORMITY}"""

def segment_flag_map(seg_df: pd.DataFrame) -> dict[tuple, bool]:
    """Lookup used by Stage 8 to attach benford_segment_flag to each transaction."""

def run(force=False, sample=False) -> None: ...
```

## 4.4 Segmentation plan (run all four)

| # | Segment dimension | Key | Purpose |
|---|---|---|---|
| S1 | `country` | country | Geographic manipulation |
| S2 | `year_month` | 'YYYY-MM' | Temporal manipulation / period pressure |
| S3 | `country` × `year_month` | tuple | The interaction — where the injected fabrication is concentrated |
| S4 | `customer_id` (top 200 by row count) | customer_id | Customer-level manipulation; the closest analogue to vendor-level testing in a payables audit |

> S4 is what lets the resume bullet say "by vendor/month". Only customers with
> n ≥ `min_segment_n` are assessed; the rest are `INSUFFICIENT_DATA`. Report how
> many customers qualified.

**The headline comparison** (needed for the resume bullet in Stage 13):

```
aggregate_verdict          = MAD verdict on the whole population
n_segments_assessed        = segments with n >= min_segment_n
n_segments_flagged         = segments with verdict MARGINAL or NONCONFORMITY
pct_injected_in_flagged    = share of digit_fabrication rows living in a flagged segment
uplift_vs_aggregate        = anomalies surfaced by segment testing that aggregate
                             testing would not have surfaced at all
```

If the aggregate population passes (or only marginally fails) while specific segments
clearly fail, **that is the finding** — it is precisely the argument for segment-level
testing, and it should be stated in one bold sentence in the README.

## 4.5 Required figures

| Figure | File | Spec |
|---|---|---|
| Aggregate observed vs expected, first digit | `benford_aggregate_d1.png` | Grouped bars (observed) + line/marker overlay (expected Benford curve); annotate MAD and verdict in the title; y-axis as % |
| Each flagged segment (max 6) | `benford_segment_<slug>.png` | Same layout; subtitle = segment name, n, MAD, verdict |
| Second-digit test | `benford_second_digit.png` | |
| First-two-digits test | `benford_first_two.png` | 90 bars, expected as a smooth line; highlight bars with \|Z\|>1.96 |
| MAD by segment (sorted) | `benford_mad_by_segment.png` | Horizontal bars with the four threshold bands shaded — the single best Benford visual for a dashboard |
| Country × month MAD heatmap | `benford_heatmap.png` | Precursor to the Power BI heatmap page |
| Chi-square vs sample size | `benford_chi2_power.png` | Demonstrates the excess power problem visually |

**Chart standards for every figure in this project:**
- Figure size 10×6 in, dpi 150, `bbox_inches='tight'`.
- Title states what the reader should conclude, not just what is plotted
  (`"United Kingdom · 2011-09 shows nonconformity (MAD 0.021), driven by digit 9"`).
- Axis labels with units; y-axis as percentage where proportions are shown.
- Legend only when >1 series.
- A consistent palette defined once in `src/viz.py`; no default matplotlib colour cycling.
- Every figure saved to `reports/figures/` AND registered in
  `reports/metrics/figures_index.json` so Stage 11's README builder can find it.

## 4.6 Stage 4 Gate — `checks/gate_04.py`

1. `BENFORD_FIRST.sum()` == 1.0 ± 1e-9 and matches the reference table to 6 dp.
2. The digit-extraction unit table in §4.1.2 passes for all 9 cases.
3. `benford_aggregate.csv` has exactly 9 rows; `observed_prop` sums to 1.0 ± 1e-9.
4. Aggregate MAD is finite and in [0, 1]; verdict is one of the four strings.
5. `benford_segments.csv` contains rows for all four segmentation schemes; every row has a verdict; `INSUFFICIENT_DATA` rows have NaN stats.
6. **At least one segment has verdict `NONCONFORMITY`.** If none does, the Stage 3 `digit_fabrication` concentration is too weak — return to Stage 3, raise the concentration, re-run. Log the loop in `DECISIONS.md`.
7. The segments deliberately targeted in Stage 3 (`benford_target_segments`) appear among the flagged segments. Assert and print both lists. If a targeted segment is *not* flagged, report its MAD and explain why — a legitimate negative result, not something to hide.
8. Second-digit and first-two-digit tables have 10 and 90 rows and sum to 1.0.
9. Per-digit Z-statistics computed for the aggregate.
10. `benford_summary.json` contains the `chi2_caveat` string.
11. All required figures exist and are >20 KB.

**Gate report must record:** aggregate n, MAD, verdict, chi2 and p-value; the full per-digit table with Z-stats; the top 10 flagged segments sorted by MAD; counts of segments assessed / flagged / insufficient; the overlap between flagged segments and the Stage 3 targets; and two or three sentences on excess power.

**Commit:** `stage(04): Benford aggregate + 4-way segmented testing, MAD verdicts, Z-stats`

---
---

# STAGE 5 — RULE-BASED RED FLAGS

**Goal:** five deterministic, independently-auditable flags, each a pure function.
**Estimated time:** 2–3 hours
**Inputs:** `data/processed/transactions_labeled.parquet`
**Outputs:** `data/processed/flags.parquet` (txn_id + 5 flags + count + reasons), `reports/metrics/rules_summary.json`, figures

---

## 5.1 Design contract for every rule

```python
def flag_<name>(df: pd.DataFrame, cfg) -> pd.Series:
    """Return a boolean Series aligned to df.index. Pure: no mutation of df,
    no I/O, no randomness. Vectorised — no .apply over rows on 1M+ records."""
```

Each rule must also expose a companion that explains *why* a row was flagged, for the
Power BI drill-through page:

```python
def reason_<name>(df: pd.DataFrame, flag: pd.Series, cfg) -> pd.Series:
    """Short human-readable string for flagged rows, '' otherwise.
    e.g. 'Amount 994.50 sits 0.6% below the 1,000 approval threshold'"""
```

A flag with no explanation is useless to an auditor. These strings are concatenated into
`flag_reasons` in Stage 8 and shown on the drill-through page in Stage 9.

## 5.2 The five rules

### 5.2.1 `flag_duplicate`

**Definition:** the row shares `customer_id`, `round(amount, 2)` and a date within
`cfg.rules.duplicate_window_days` (default 1) with at least one *other* row that has a
**different** `invoice`.

**Implementation guidance (performance matters here):**
- Naive pairwise comparison on 1M rows is O(n²) — forbidden.
- Approach: build a key `(customer_id, amount_rounded)`. Group by it. Almost every
  group is size 1–3; only groups of size ≥2 need work. Within a group, sort by
  `invoice_date` and use a vectorised window comparison to find any pair within ±1 day
  with different invoices.
- Exclude `customer_id == "UNASSIGNED"` (too many spurious matches); set the flag False
  for those rows and state this in the docstring and the README.
- Expected runtime: <30 s.

**Reason string:** `"Matches invoice {other_invoice} — same customer, same amount £{amt}, {n} day(s) apart"`

**Tuning target:** roughly 0.5–4% of rows. If it flags >10%, the key or window is too loose — tighten and log.

---

### 5.2.2 `flag_round_number`

**Definition:** `amount > 0` and `amount` is an exact multiple of any value in
`cfg.rules.round_multiples` (default `[100, 1000]`).

**Implementation:**
- Work in integer pence to avoid float modulo error:
  `pence = (amount * 100).round().astype('int64')`; test `pence % (mult * 100) == 0`.
- Report separately: exact multiples of 1000; of 100 but not 1000; and — as a
  diagnostic only, not part of the flag — multiples of 10 and 5, so the analyst can see
  how much natural roundness the real data already carries.

**Reason string:** `"Amount is an exact multiple of £{mult} (£{amt})"`

**Expected baseline:** real retail data *does* contain naturally round amounts (quantity
10 at £1.00, etc). Report the pre-injection and post-injection round rates side by side —
the delta is the injected signal, and the baseline is the false-positive load a real
auditor would face. Worth a paragraph in the README.

---

### 5.2.3 `flag_threshold_avoidance`

**Definition:** `amount` falls inside any band in `cfg.rules.threshold_bands`, e.g.
`[[950, 999.99], [4750, 4999.99], [9500, 9999.99], [475, 499.99], [237.5, 249.99]]`.

**Implementation:** vectorised `np.logical_or.reduce` over band masks. Do not loop rows.

**Reason string:** `"Amount £{amt} sits {pct}% below the £{T} approval threshold"`

**Refinement (implement and report — a strong differentiator):** a band test alone is
crude. Also compute a **ratio test** per threshold:
```
ratio_T = count(amounts in [0.95T, T)) / count(amounts in [T, 1.05T])
```
Under a natural distribution this ratio sits near 1 (slightly above, since smaller
values are more common). A ratio materially above ~1.3 is evidence of structuring at
that threshold. Report `ratio_T` for every threshold, pre- and post-injection, in
`rules_summary.json`. This converts a per-row flag into a **population-level control
finding**, which is how an auditor would actually phrase it.

---

### 5.2.4 `flag_period_end`

**Definition:** `days_to_month_end < cfg.rules.period_end_days` (default 2) — the last
two calendar days of the month.

**Implementation:** derived in Stage 2 (`is_month_end`); the rule just reads it. Also
produce `flag_quarter_end` as a **diagnostic column** (not one of the five).

**Reason string:** `"Dated {date}, {n} day(s) before month end"`

**Population-level companion:** per `year_month`, compute the share of transactions in
the last two days and flag months whose share exceeds `mean + 2·sd` across all months.
Report as `period_end_outlier_months`. Again: a control finding, not just a row flag.

---

### 5.2.5 `flag_off_hours`

**Definition:** `hour < cfg.rules.business_hours[0]` or `hour > cfg.rules.business_hours[1]`
(default: outside 07:00–19:59).

**Preconditions the agent must verify before trusting this rule** (from Stage 2's hour histogram):
- If >2% of *real* rows fall outside the window, the window is wrong for this dataset —
  widen it to the empirical 1st–99th percentile of activity and log a decision.
- State explicitly in the README whether the timestamps are genuine (they are, in this
  dataset). Many published copies of the Online Retail data have had times stripped, and
  reviewers will ask.

**Reason string:** `"Timestamped {time} — outside the {start}:00–{end}:59 business-hours window"`

---

## 5.3 Aggregation

```python
def apply_all_rules(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """Returns a frame indexed by txn_id with:
        flag_duplicate, flag_round_number, flag_threshold_avoidance,
        flag_period_end, flag_off_hours          (all bool)
        rule_flag_count                          (int8, 0-5)
        rule_flag_names                          (comma-separated str)
        flag_reasons                             ('; '-joined explanations)
    Asserts rule_flag_count == the row-wise sum of the five booleans."""
```

## 5.4 Required outputs and figures

| Output | Content |
|---|---|
| `rules_summary.json` | Per rule: count flagged, % of population, % of injected rows flagged, % of real rows flagged, precision-if-used-alone; plus the threshold ratio table and period-end outlier months |
| `rule_flag_rates.png` | Bar chart: % of population flagged by each rule |
| `rule_overlap_matrix.png` | 5×5 co-occurrence heatmap — shows the rules are not redundant |
| `rule_flag_count_dist.png` | Histogram of `rule_flag_count` (0–5), split real vs injected |
| `threshold_ratio.png` | `ratio_T` bars per threshold, pre/post injection |
| `period_end_share_by_month.png` | Line chart with the ±2sd band |

## 5.5 Sanity bounds (each asserted in the gate)

| Rule | Expected flag rate on the full population |
|---|---|
| `flag_duplicate` | 0.3% – 6% |
| `flag_round_number` | 0.5% – 8% |
| `flag_threshold_avoidance` | 0.1% – 3% |
| `flag_period_end` | 4% – 12% (mechanically ≈2/30 = 6.7% plus injection) |
| `flag_off_hours` | 0.05% – 4% |
| `rule_flag_count >= 1` | 6% – 20% |

Any rule outside its band is either mis-specified or mis-configured. Investigate before
proceeding; do **not** widen the band to make the assertion pass.

## 5.6 Stage 5 Gate — `checks/gate_05.py`

1. `flags.parquet` exists; row count == labeled population; `txn_id` unique and joins 1:1.
2. All five flag columns are boolean with no nulls.
3. `rule_flag_count` ∈ [0,5] and equals the row-wise boolean sum for every row.
4. Every rule's flag rate sits in its §5.5 band.
5. Each rule flags **at least one** injected row of its designed target type (per the §3.4 matrix) — assert per rule, print the numbers.
6. `flag_duplicate` is False for all `customer_id == "UNASSIGNED"` rows.
7. `flag_round_number` unit tests: `1000.00`→True, `999.99`→False, `0.0`→False, `100.00`→True, `-100.00`→False.
8. `flag_reasons` is non-empty wherever `rule_flag_count > 0` and empty elsewhere.
9. Purity: calling `apply_all_rules` twice yields identical output and leaves the input frame unmodified (`df.equals(df_before)`).
10. All six figures exist.

**Gate report must record:** per-rule flag counts and rates; the % of each injected anomaly type caught by each rule (a 7×5 preview of the Stage 7 matrix); the rule overlap matrix; the threshold ratio table; and the period-end outlier months.

**Commit:** `stage(05): five rule-based red flags with reason strings and population-level control tests`

---
---

# STAGE 6 — ISOLATION FOREST (+ LOCAL OUTLIER FACTOR)

**Goal:** an unsupervised anomaly score per transaction, from two feature sets and four contamination settings, plus a second model for comparison.
**Estimated time:** 3–4 hours
**Inputs:** `transactions_labeled.parquet`, `flags.parquet`, Benford segment verdicts
**Outputs:** `data/processed/features.parquet`, `data/processed/scored.parquet`, `reports/metrics/model_runs.json`, figures

---

## 6.1 `src/features.py` — the feature matrix

### 6.1.1 Feature list

| # | Feature | Definition | FS-A | FS-B |
|---|---|---|---|---|
| F1 | `amount_log` | `sign(amount) * log1p(abs(amount))` | ✓ | ✓ |
| F2 | `quantity_log` | `sign(q) * log1p(abs(q))` | ✓ | ✓ |
| F3 | `price_log` | `log1p(price.clip(lower=0))` | ✓ | ✓ |
| F4 | `day_of_week` | 0–6 int | ✓ | ✓ |
| F5 | `hour` | 0–23 int | ✓ | ✓ |
| F6 | `leading_digit` | 1–9, **0 for amount < 1** | ✓ | ✓ |
| F7 | `cust_amount_z` | `(amount − cust_mean) / cust_std`, 0 where undefined | ✓ | ✓ |
| F8 | `cust_amount_robust_z` | `(amount − cust_median) / (1.4826 · cust_MAD)`, 0 where undefined | ✓ | ✓ |
| F9 | `cust_txn_count_log` | `log1p(count)` | ✓ | ✓ |
| F10 | `has_customer_stats` | bool→int | ✓ | ✓ |
| F11 | `days_to_month_end` | 0–30 int | ✓ | ✓ |
| F12 | `amount_decimal_part` | `amount − floor(amount)` | ✓ | ✓ |
| F13 | `is_integer_amount` | `amount == floor(amount)` | ✓ | ✓ |
| F14 | `stockcode_amount_z` | z-score of amount within its `stock_code` | ✓ | ✓ |
| F15 | `country_freq` | frequency-encoded country (share of rows) | ✓ | ✓ |
| F16 | `flag_duplicate` | from Stage 5 | ✗ | ✓ |
| F17 | `flag_round_number` | from Stage 5 | ✗ | ✓ |
| F18 | `flag_threshold_avoidance` | from Stage 5 | ✗ | ✓ |
| F19 | `flag_period_end` | from Stage 5 | ✗ | ✓ |
| F20 | `flag_off_hours` | from Stage 5 | ✗ | ✓ |

### 6.1.2 Why two feature sets (state this in the README)

The brief asks for the rule flags to be model features. Doing *only* that creates a
circularity problem: the ML model's "detections" would be partly the rules restated, and
the Stage 7 comparison matrix would overstate the ML layer's independent contribution. So:

- **FS-A** (F1–F15, no rule flags): what unsupervised ML finds *on its own*.
- **FS-B** (F1–F20, with rule flags): the brief's specification; the best-performing
  production configuration.

Both are scored, both appear in Stage 7, and the gap between them is itself a finding
worth one sentence in the README.

### 6.1.3 Function contract

```python
FORBIDDEN_COLS = {"is_synthetic_anomaly", "anomaly_type", "source_txn_id",
                  "sibling_group", "params_json", "target_segment"}

FEATURE_SET_A: list[str]
FEATURE_SET_B: list[str]

def build_feature_matrix(df: pd.DataFrame, feature_set: str,
                         cfg) -> tuple[pd.DataFrame, list[str]]:
    """Build features per the table above.
    Guards (all assertions, all fatal):
      - FORBIDDEN_COLS ∩ returned columns == empty      # Leakage Firewall
      - no NaN, no ±inf anywhere in the matrix
      - all columns numeric dtype
      - index is txn_id, unique
      - len(matrix) == len(df)
    Returns (matrix, feature_names)."""

def customer_statistics(df: pd.DataFrame) -> pd.DataFrame:
    """Recomputed on the POST-injection population — deliberately: in a real
    engagement the analyst only ever sees the contaminated ledger, so 'typical'
    must be estimated from contaminated data. Note this in the README; it is a
    subtle point that shows methodological care.
    Uses median/MAD alongside mean/std so a few extreme injected rows do not
    blow up the baseline."""
```

### 6.1.4 Scaling

Isolation Forest is tree-based and scale-invariant — no scaler required. LOF is
**distance-based and is not** — it requires `RobustScaler` (preferred over
`StandardScaler` here, given the heavy tails). Build one shared matrix and apply the
scaler only in the LOF path. Document this asymmetry; conflating the two is a common
mistake.

## 6.2 `src/models.py` — specification

```python
@dataclass
class ModelRun:
    model: str                # 'isolation_forest' | 'lof'
    feature_set: str          # 'FS-A' | 'FS-B'
    contamination: float
    params: dict
    n_flagged: int
    flag_rate: float
    elapsed_s: float
    score_col: str

def fit_isolation_forest(X: pd.DataFrame, contamination: float,
                         cfg) -> tuple[IsolationForest, np.ndarray, np.ndarray]:
    """IsolationForest(
        n_estimators=cfg.model.n_estimators,      # 200
        max_samples=cfg.model.max_samples,        # 256
        contamination=contamination,
        max_features=1.0,
        bootstrap=False,
        random_state=cfg.project.seed,
        n_jobs=cfg.model.n_jobs)

    Returns (model, raw_scores, predictions) where
      raw_scores  = model.score_samples(X)   # LOWER = more anomalous
      predictions = model.predict(X)         # -1 anomaly, +1 normal

    SIGN CONVENTION (critical): define
        anomaly_score = -score_samples(X)    # HIGHER = more anomalous
    and use that convention EVERYWHERE downstream. Getting this backwards
    produces a PR curve below the baseline and is the single most common bug in
    Isolation Forest write-ups. gate_06 asserts the direction empirically."""

def fit_lof(X_scaled: pd.DataFrame, contamination: float,
            cfg) -> tuple[LocalOutlierFactor, np.ndarray, np.ndarray]:
    """LocalOutlierFactor(n_neighbors=cfg.model.lof_n_neighbors,
                          contamination=contamination, novelty=False, n_jobs=-1)
    Use fit_predict; scores from -lof.negative_outlier_factor_.

    PERFORMANCE WARNING: LOF is O(n log n) at best and often far worse. On 1.08M
    rows it may take hours or exhaust memory. Therefore run LOF on a stratified
    subsample of 150,000 rows (seeded) that retains ALL injected rows plus a
    random sample of real rows, and report LOF metrics on that subsample only,
    clearly labelled. Log this as a decision. Do NOT let LOF block the pipeline:
    if it exceeds 15 minutes, abort, record the abort, and continue."""

def to_percentile(scores: np.ndarray) -> np.ndarray:
    """Rank-based normalisation to [0,1]; ties averaged. Used by Stage 8."""

def run(force=False, sample=False) -> None:
    """Fits:
        IF × FS-A × 0.015                  -> if_score_fsa
        IF × FS-B × 0.015                  -> if_score_fsb        (headline)
        IF × FS-B × {0.005, 0.010, 0.030}  -> if_score_fsb_c005 …
        LOF × FS-B × 0.015 on subsample    -> lof_score (NaN off-subsample)
    Writes scored.parquet = txn_id + all score columns + binary predictions +
    percentile versions. Records every run in reports/metrics/model_runs.json."""
```

## 6.3 Contamination discussion (required in the README)

The brief correctly notes that in a real engagement the anomaly rate is unknown. So:

1. Use 0.015 as the primary setting (matching the known injection rate) — and say
   plainly that this is an advantage the simulation grants and reality does not.
2. Report the full sensitivity table across 0.005 / 0.010 / 0.015 / 0.030 showing the
   precision–recall trade-off.
3. Emphasise that the **ranking** (`score_samples`) is contamination-invariant — only
   the binary cut-off moves. The audit-realistic framing is therefore *"give me the top
   500 transactions to review"*, not *"tell me which transactions are fraudulent"*.
   Precision@k in Stage 7 reflects exactly this, and it is the number to lead with in an
   audit interview.

## 6.4 Required figures

| Figure | File |
|---|---|
| Score distribution, real vs injected (overlaid density, FS-B) | `if_score_distribution.png` |
| FS-A vs FS-B score distributions side by side | `if_featureset_comparison.png` |
| Contamination sensitivity: precision/recall/F1 vs contamination | `if_contamination_sensitivity.png` |
| 2-D projection (PCA, or `amount_log` × `cust_amount_robust_z`) coloured by score, injected rows marked | `if_score_scatter.png` |
| IF vs LOF rank agreement (percentile scatter + Spearman ρ) | `if_vs_lof_agreement.png` |
| Top-N overlap: IF top-500 vs rules-flagged vs Benford-segment rows | `method_overlap.png` |

## 6.5 Stage 6 Gate — `checks/gate_06.py`

1. `features.parquet` and `scored.parquet` exist; row counts match the population.
2. **Leakage assertion:** `FORBIDDEN_COLS ∩ FEATURE_SET_B == ∅`; and a
   `DecisionTreeClassifier(max_depth=3)` trained on the feature matrix to predict
   `is_synthetic_anomaly` achieves **AP < 0.60** (Stage 3 check T10). Print the value.
3. No NaN or ±inf in any feature column.
4. **Score direction check:** mean `if_score_fsb` of injected rows must be **greater**
   than that of real rows (higher = more anomalous). If lower, the sign convention is
   inverted — fix it at source, do not flip the metric later.
5. `if_score_fsa` and `if_score_fsb` are continuous (>10,000 distinct values each).
6. Binary predictions flag approximately `contamination × n` rows (±15%).
7. All four contamination runs recorded in `model_runs.json` with elapsed times.
8. Determinism: re-fit with the same seed → identical scores (hash equality).
9. LOF either completed on the subsample (rows marked) or is recorded as
   `status: "aborted"` with a reason. Either passes; silently missing fails.
10. Runtime: the headline FS-B fit on the full population completed in <10 minutes.
11. All six figures exist.

**Gate report must record:** feature counts per set; the leakage AP value; mean/median score by class; the contamination sensitivity table; Spearman ρ between IF and LOF ranks; elapsed time per fit; and a one-paragraph interpretation of the score distribution plot.

**Commit:** `stage(06): Isolation Forest FS-A/FS-B, contamination sensitivity, LOF comparison`
`git tag stage-06-model`

---

**END OF STAGES 4–6 — proceed to `03_STAGES_7-9.md`**
