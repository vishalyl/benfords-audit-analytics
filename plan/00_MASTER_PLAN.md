# MASTER PLAN — Audit Analytics: Transaction Anomaly Detection
### Benford's Law + Rule-Based Red Flags + Isolation Forest + Power BI + Public Dashboard

**Document ID:** `00_MASTER_PLAN`
**Version:** 1.0
**Owner:** Y.L. Vishal
**Repository name:** `benfords-audit-analytics`
**Local root:** `C:\Users\visha\Premier Pro\EDITING\OneDrive\Desktop\fraud-detection\benfords-audit-analytics`
**Intended executor:** an autonomous AI coding agent (Claude Code / Cursor) running on the Windows machine
**Target completion:** ~7 working days at 1–2 hrs/day for Stages 0–9; Stages 10–13 add ~2 days
**Target roles:** (1) Audit / forensic analytics, (2) Data analyst / BI analyst

---

## 0. HOW TO USE THIS PLAN

### 0.1 Reading order (mandatory)

| Order | File | Contents |
|---|---|---|
| 1 | `00_MASTER_PLAN.md` (this file) | Global rules, conventions, data contracts, decision defaults, stage-gate protocol. **Read fully before writing any code.** |
| 2 | `01_STAGES_0-3.md` | Stage 0 Environment Bootstrap · Stage 1 Ingestion & SQL · Stage 2 Cleaning · Stage 3 Synthetic Anomaly Injection |
| 3 | `02_STAGES_4-6.md` | Stage 4 Benford's Law · Stage 5 Rule-Based Checks · Stage 6 Isolation Forest |
| 4 | `03_STAGES_7-9.md` | Stage 7 Validation vs Ground Truth · Stage 8 Composite Risk & Export · Stage 9 Power BI Dashboard |
| 5 | `04_STAGES_10-13.md` | Stage 10 Public Web Dashboard · Stage 11 README & Portfolio Assets · Stage 12 Audit Findings PDF · Stage 13 Resume Bullets & Interview Prep · Git publish |
| 6 | `05_FUTURE_ROADMAP.md` | Phase 2 — the advanced build, only after Phase 1 is green |

### 0.2 The executor's contract

The agent executing this plan **MUST**:

1. Work strictly in stage order. Stage N may not begin until Stage N−1's **Stage Gate** has passed.
2. Run the stage's verification script and paste its full output into the stage-gate report before declaring the stage complete.
3. When it encounters a decision this plan does not cover: **choose the most defensible option, proceed, and append an entry to `DECISIONS.md`** (format in §7). Do not stop and wait.
4. Never modify a previous stage's output file in place. If a fix is required upstream, re-run that stage end-to-end so outputs stay reproducible.
5. Never hand-edit a generated CSV/Parquet. Every artefact must be reproducible by running code.
6. Never let ground-truth labels reach a model. See the Leakage Firewall, §6.
7. Commit at the end of every stage with the commit convention in §8.

The agent **MUST NOT**:

- Invent dataset columns, row counts, or metric values. If a number is unknown, compute it.
- Report a metric it has not actually computed in code.
- Silently drop rows. Every row removed must be counted and logged in the cleaning ledger (Stage 2).
- Change a random seed to make results look better.
- Skip a verification assertion because it fails. A failing assertion is a bug to fix, not a check to delete.

### 0.3 Definition of Done for the whole project

The project is done when all of the following are true:

- [ ] `python -m src.pipeline --stage all` runs from a clean clone (raw data present) and reproduces every artefact bit-for-bit given the same seed.
- [ ] All 14 stage gates pass.
- [ ] `dashboard/audit_analytics.pbix` opens and all 5 pages render.
- [ ] A public dashboard URL is live and linked in the README.
- [ ] `README.md` contains real numbers, 3+ embedded images, and a Limitations section.
- [ ] `reports/audit_findings_workpaper.pdf` exists and is 4–6 pages.
- [ ] `docs/resume_and_interview.md` contains bullets populated with actual computed figures.
- [ ] The repo is public on GitHub with a clean commit history (one or more commits per stage).
- [ ] `DECISIONS.md` has an entry for every judgement call made.

---

## 1. PROJECT FRAMING (the story this project tells)

> A client's transaction-level sales ledger (1.07M lines, UK online retailer, Dec 2009 – Dec 2011) is analysed to identify entries warranting further audit scrutiny. Three independent detection layers are applied — digit-distribution analysis (Benford's Law, aggregate and segmented), deterministic rule-based red flags, and unsupervised machine learning (Isolation Forest) — and combined into a single composite risk score that ranks every transaction for review.
>
> Because live audit engagement data is confidential and unlabelled, a controlled set of synthetic anomalies (~1.5% of rows, six fraud archetypes) is injected into the real ledger. This yields a ground truth that permits precision/recall scoring of each detection method — something no live engagement can offer. This mirrors how forensic analytics functions validate new detection models before deploying them against client data.

**The single most important output of the project** is the *anomaly-type × detection-method* matrix in Stage 7: it demonstrates empirically that each method catches a *different* class of manipulation, which is the whole argument for layered detection in a real audit.

**Academic anchor:** Mark J. Nigrini, *Benford's Law: Applications for Forensic Accounting, Auditing, and Fraud Detection* (Wiley, 2012) — source of the MAD conformity thresholds and the segmented-testing methodology.

---

## 2. DATASET CONTRACT

### 2.1 Source

| Field | Value |
|---|---|
| Name | Online Retail II |
| Publisher | UCI Machine Learning Repository, Dataset ID 502 |
| Primary URL | `https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip` |
| Landing page | `https://archive.ics.uci.edu/dataset/502/online+retail+ii` |
| Kaggle mirror (fallback) | search "Online Retail II UCI" |
| Archive contents | `online_retail_II.xlsx` (single workbook, two sheets) |
| Sheet names | `Year 2009-2010`, `Year 2010-2011` |
| Approx. download size | ~44 MB zipped, ~45 MB xlsx |
| Licence | CC BY 4.0 — attribution required in README |

### 2.2 Expected raw shape (assert these in Stage 1)

| Sheet | Expected rows |
|---|---|
| `Year 2009-2010` | 525,461 |
| `Year 2010-2011` | 541,910 |
| **Combined** | **1,067,371** |

> **Executor note:** these figures are the published values. If your actual load differs, DO NOT adjust code to force a match — record the actual counts in the stage-gate report, log a `DECISIONS.md` entry, and carry the actual figures forward into the README. The assertion in Stage 1 is a *tolerance* check (±1%), not an equality check.

### 2.3 Raw schema

| Column (raw) | Type | Notes |
|---|---|---|
| `Invoice` | string | 6-digit; a leading `C` denotes a **cancellation/credit note** |
| `StockCode` | string | product code; some non-product codes exist (see §2.5) |
| `Description` | string | nullable; missing on a meaningful minority of rows |
| `Quantity` | int | may be negative (returns/adjustments) |
| `InvoiceDate` | datetime | **includes a real time component**, minute granularity |
| `Price` | float | unit price in GBP; may be 0 or negative |
| `Customer ID` | float | nullable; roughly 20–25% of rows are missing it |
| `Country` | string | ~40 distinct values, heavily dominated by United Kingdom |

### 2.4 Canonical column names used from Stage 1 onward

All code after ingestion uses snake_case. The rename map is **fixed** and lives in `src/config.py`:

```
"Invoice"      -> "invoice"
"StockCode"    -> "stock_code"
"Description"  -> "description"
"Quantity"     -> "quantity"
"InvoiceDate"  -> "invoice_date"
"Price"        -> "price"
"Customer ID"  -> "customer_id"
"Country"      -> "country"
```

### 2.5 Known non-product `stock_code` values (treated as ledger adjustments, not sales)

`POST`, `DOT`, `D`, `M`, `C2`, `BANK CHARGES`, `BANK CHARGES`, `CRUK`, `PADS`, `S`, `AMAZONFEE`, `TEST001`, `TEST002`, `ADJUST`, `ADJUST2`, `gift_0001_*`, `B`, and any code matching `^[A-Za-z]+$` (all-letters, no digits).

**Rule:** these are excluded from the Benford population and flagged with `is_adjustment = True`, but retained in the dataset and in the dashboard. An auditor cares about them — they are exactly where manual journal entries hide. This is an audit-credibility detail; do not silently delete them.

### 2.6 Derived core field

```
amount = quantity * price        # GBP, signed
```

`amount` is the analogue of a sales ledger line value and is the field on which Benford's Law and outlier detection operate.

### 2.7 Time granularity finding (affects Stage 5 `flag_off_hours`)

`invoice_date` in this dataset **does** carry a usable time-of-day. Observed activity concentrates roughly 07:00–20:00 UK time, with almost nothing overnight. Therefore:

- `flag_off_hours` is **implementable on real data** (unlike many retail datasets).
- Business-hours window default: **07:00–19:59 inclusive**, Monday–Saturday.
- Sunday is a live trading day in this dataset — do **not** flag Sunday as off-hours by itself. Log this.
- Stage 2 must empirically compute the hour histogram and write it to `reports/figures/hour_distribution.png`, and Stage 5 must state whether the 07:00–20:00 default is supported by that histogram. If it isn't, adjust and log.

---

## 3. TECHNOLOGY STACK (frozen)

| Layer | Choice | Version pin |
|---|---|---|
| Language | Python | 3.11.x (3.10 minimum, 3.12 acceptable; avoid 3.13 for scikit-learn wheel stability) |
| Env | `venv` at `.venv/` in repo root | stdlib |
| Data | pandas | `>=2.1,<3` |
| Numerics | numpy | `>=1.26,<3` |
| Stats | scipy | `>=1.11` |
| ML | scikit-learn | `>=1.4,<2` |
| Plots | matplotlib, seaborn | `>=3.8`, `>=0.13` |
| Columnar cache | pyarrow | `>=15` |
| Excel read | openpyxl | `>=3.1` |
| DB | sqlite3 | stdlib |
| Config | PyYAML | `>=6` |
| Notebooks | jupyterlab, ipykernel | latest |
| Progress | tqdm | latest |
| PDF workpaper | reportlab **or** the `pdf` skill route | `>=4.0` |
| Public dashboard | streamlit | `>=1.33` (Stage 10) |
| BI | Power BI Desktop (free, Windows) | latest from Microsoft Store |

**Not used in Phase 1:** pytest, Docker, CI, dbt, XGBoost, SHAP, autoencoders. All deferred to `05_FUTURE_ROADMAP.md`. Do not pull them in early.

---

## 4. REPOSITORY LAYOUT (create exactly this in Stage 0)

```
benfords-audit-analytics/
├── .gitignore
├── .gitattributes
├── README.md                         # written in Stage 11
├── requirements.txt
├── config.yaml                       # single source of truth for all tunables
├── CLAUDE.md                         # standing instructions for the coding agent
├── DECISIONS.md                      # append-only judgement log
├── CHANGELOG.md                      # one entry per stage gate
│
├── data/
│   ├── raw/                          # git-ignored
│   │   ├── online_retail_II.xlsx
│   │   └── online_retail_II.zip
│   ├── interim/                      # git-ignored
│   │   ├── raw_combined.parquet
│   │   ├── cleaned.parquet
│   │   └── sample_50k.parquet
│   ├── processed/                    # git-ignored EXCEPT the small files noted
│   │   ├── transactions_labeled.parquet
│   │   ├── transactions_labeled.csv
│   │   ├── injected_anomalies.csv        # COMMITTED (small)
│   │   ├── features.parquet
│   │   ├── scored.parquet
│   │   └── dashboard_export.csv
│   └── dashboard/                    # COMMITTED — small aggregates for the web app
│       ├── kpi_summary.json
│       ├── benford_aggregate.csv
│       ├── benford_segments.csv
│       ├── monthly_trend.csv
│       ├── segment_heatmap.csv
│       ├── method_comparison.csv
│       ├── model_metrics.json
│       └── top_risk_transactions.csv
│
├── db/
│   └── audit_data.db                 # git-ignored
│
├── sql/
│   ├── queries.sql                   # the showcase queries
│   └── schema.sql
│
├── src/
│   ├── __init__.py
│   ├── config.py                     # loads config.yaml, exposes typed settings
│   ├── logging_setup.py
│   ├── io_utils.py
│   ├── ingest.py                     # Stage 1
│   ├── sqlite_load.py                # Stage 1
│   ├── clean.py                      # Stage 2
│   ├── inject.py                     # Stage 3
│   ├── benford.py                    # Stage 4
│   ├── rules.py                      # Stage 5
│   ├── features.py                   # Stage 6
│   ├── models.py                     # Stage 6
│   ├── validate.py                   # Stage 7
│   ├── composite.py                  # Stage 8
│   ├── export.py                     # Stage 8
│   ├── viz.py                        # shared plotting
│   └── pipeline.py                   # CLI orchestrator
│
├── checks/
│   ├── gate_00.py ... gate_13.py     # one verification script per stage
│   └── common.py                     # shared assertion helpers
│
├── notebooks/
│   ├── 01_data_prep_and_sql.ipynb
│   ├── 02_synthetic_anomaly_injection.ipynb
│   ├── 03_benfords_law_analysis.ipynb
│   ├── 04_rule_based_checks.ipynb
│   ├── 05_isolation_forest_and_validation.ipynb
│   └── 06_export_for_dashboard.ipynb
│
├── dashboard/
│   ├── audit_analytics.pbix
│   ├── theme.json
│   └── POWERBI_BUILD_NOTES.md
│
├── app/                              # Stage 10 public dashboard
│   ├── streamlit_app.py
│   ├── requirements.txt
│   └── .streamlit/config.toml
│
├── reports/
│   ├── figures/                      # all PNGs — COMMITTED
│   ├── gate_reports/                 # gate_00.md ... gate_13.md — COMMITTED
│   ├── audit_findings_workpaper.pdf  # Stage 12
│   └── metrics/                      # JSON metric dumps — COMMITTED
│
├── docs/
│   ├── methodology.md
│   ├── data_dictionary.md
│   ├── resume_and_interview.md       # Stage 13
│   └── screenshots/
│
└── plan/                             # THIS PLAN — committed for transparency
    ├── 00_MASTER_PLAN.md
    ├── 01_STAGES_0-3.md
    ├── 02_STAGES_4-6.md
    ├── 03_STAGES_7-9.md
    ├── 04_STAGES_10-13.md
    └── 05_FUTURE_ROADMAP.md
```

### 4.1 `.gitignore` (exact content, Stage 0)

```
.venv/
__pycache__/
*.pyc
.ipynb_checkpoints/
data/raw/
data/interim/
data/processed/
!data/processed/injected_anomalies.csv
db/*.db
*.log
.DS_Store
Thumbs.db
```

> Note the negation line: the ground-truth injection log is small and is *deliberately* committed, because a reviewer should be able to see it.

---

## 5. NOTEBOOKS vs MODULES — THE RULE

**All logic lives in `src/`. Notebooks call `src/` and display results. Nothing else.**

A notebook cell may contain: imports, a call to a `src` function, a display/plot, and markdown narration. A notebook cell may **not** contain: a loop that transforms data, a model fit, a metric calculation, or a file write that isn't a figure. If the agent finds itself writing >10 lines of logic in a notebook, that logic belongs in `src/` and the notebook should import it.

Rationale: this is the single most common criticism of portfolio projects, the code becomes testable, and `python -m src.pipeline --stage all` reproduces everything headlessly.

Notebooks are authored in **Stage 11**, after the pipeline works, not before. During Stages 1–10 the agent works exclusively through `src/` and the CLI.

### 5.1 CLI contract (`src/pipeline.py`)

```
python -m src.pipeline --stage <name> [--sample] [--force] [--seed N]

stages: ingest | sqlite | clean | inject | benford | rules | features |
        model | validate | composite | export | dashboard-data | all
```

- `--sample` runs against `data/interim/sample_50k.parquet` and writes to `*_sample` filenames. **Use `--sample` for all iteration; only run full at stage gates.**
- `--force` re-runs a stage even if its output exists (default behaviour is skip-if-exists).
- `--seed` overrides `config.yaml`; default 42.
- Every stage logs to `logs/pipeline_<stage>_<timestamp>.log` and prints a one-line summary: `[STAGE ingest] OK rows_in=... rows_out=... elapsed=...s`.

---

## 6. THE LEAKAGE FIREWALL (non-negotiable)

Ground-truth columns are `is_synthetic_anomaly` and `anomaly_type`. They exist to score models, never to train or flag with.

**Mechanism:**

1. `src/features.py` exposes exactly one function that models may consume:
   `build_feature_matrix(df) -> tuple[pd.DataFrame, list[str]]`
2. That function begins with a hard guard:
   ```
   FORBIDDEN = {"is_synthetic_anomaly", "anomaly_type", "source_txn_id",
                "injection_params", "is_injected"}
   assert not (FORBIDDEN & set(feature_cols)), f"LEAKAGE: {FORBIDDEN & set(feature_cols)}"
   ```
3. `txn_id` must carry **no signal**. Injected rows must NOT get a distinguishable prefix. IDs are assigned *after* the original and injected frames are concatenated and deterministically sorted (see Stage 3, §3.6).
4. Row order must carry no signal: after injection the frame is sorted by `(invoice_date, invoice, stock_code, line_no)` — injected rows interleave naturally.
5. `checks/gate_03.py` includes a **leakage detector**: fit a `DecisionTreeClassifier(max_depth=3)` on the model feature set predicting `is_synthetic_anomaly` using only `txn_id`-derived and index-derived columns; ROC-AUC must be < 0.55. If it exceeds that, the ID scheme leaks and must be fixed.

---

## 7. `DECISIONS.md` PROTOCOL

Append-only. Newest at the bottom. One entry per judgement call. Format:

```markdown
### D-0007 — Missing customer_id handling
- **Stage:** 2
- **Date:** 2026-09-14
- **Question:** Drop the ~22% of rows with no customer_id, or retain them?
- **Options considered:**
  1. Drop — cleanest customer-level statistics
  2. Retain in an `UNASSIGNED` bucket — preserves population completeness
- **Decision:** Option 2.
- **Rationale:** An auditor may not exclude ~22% of the ledger population from
  digit-distribution testing; completeness is an assertion being tested. Rows are
  retained, assigned `customer_id = "UNASSIGNED"`, included in Benford and rule
  checks, and excluded only from the customer-level z-score feature (which is set
  to 0.0 for them, with a companion `has_customer_stats` binary flag).
- **Impact:** Benford population +N rows; IF feature `cust_amount_z` is 0 for N rows.
- **Reversible:** yes — toggle `cleaning.drop_missing_customer` in config.yaml
```

**Pre-registered defaults.** The following decisions are already made by this plan; the agent implements them and does *not* need a DECISIONS entry unless it deviates:

| ID | Decision |
|---|---|
| PD-01 | Missing `customer_id` → retained as `"UNASSIGNED"`, excluded from customer-level statistics only. |
| PD-02 | Cancellations (`invoice` starts with `C`) → moved to a separate `cancellations` frame, excluded from Benford and from the model population, but **counted and reported**. |
| PD-03 | Benford population = non-cancelled, non-adjustment rows with `amount >= 1.00`. |
| PD-04 | Zero and negative `amount` rows → retained, flagged `is_nonpositive_amount`, excluded from Benford only. |
| PD-05 | Duplicate detection window = same `customer_id` + same rounded `amount` (2dp) + `invoice_date` within ±1 day + different `invoice`. |
| PD-06 | Injection rate = **1.5%** of the cleaned population, split evenly across 6 anomaly types. |
| PD-07 | Global seed = **42**, set via `numpy.random.default_rng(42)` and `random_state=42` everywhere. |
| PD-08 | Minimum segment size for a Benford conformity verdict = **1,000 rows**. Smaller segments get verdict `INSUFFICIENT_DATA`. |
| PD-09 | Primary Isolation Forest contamination = **0.015**; sensitivity runs at 0.005, 0.010, 0.030. |
| PD-10 | Two feature sets are modelled: **FS-A** (no rule flags) and **FS-B** (with rule flags). FS-B is the headline; FS-A proves the ML adds signal independent of the rules. |
| PD-11 | Composite weights: `0.50 × IF_percentile + 0.30 × (rule_flag_count / 5) + 0.20 × benford_segment_flag`. |
| PD-12 | Business hours = 07:00–19:59 inclusive, all days; Sunday is NOT off-hours. |
| PD-13 | Currency is GBP throughout; no FX conversion. |
| PD-14 | Power BI Benford visuals use **precomputed segment statistics from Python** for MAD/verdict, and **DAX** for the observed-vs-expected digit bars so slicers respond live. (Hybrid — best of both.) |

---

## 8. GIT CONVENTIONS

- `main` is the only long-lived branch. Work directly on `main` (solo project; a fake branching story fools nobody).
- One commit minimum per stage; more is fine.
- Commit message format:
  ```
  stage(NN): short imperative summary

  - what changed
  - key numbers produced (rows, metrics)
  - gate: PASS
  ```
- Tag each passed gate: `git tag stage-04-benford`
- Large files never enter git — see `.gitignore`. If a file >50 MB is ever staged, abort and reconsider.

---

## 9. STAGE GATE PROTOCOL

Every stage ends with the same three artefacts:

1. **`checks/gate_NN.py`** — an executable script that exits non-zero on any failure.
2. **`reports/gate_reports/gate_NN.md`** — a written report containing:
   - Stage name and date
   - Every output file produced, with size and row count
   - The full stdout of `python checks/gate_NN.py`
   - A table of the key numbers this stage produced
   - Any `DECISIONS.md` entries added
   - `GATE: PASS` or `GATE: FAIL`
3. A git commit + tag.

**`checks/common.py`** provides:

```python
def assert_cols(df, required: set[str]) -> None
def assert_rowcount(df, expected: int, tol_pct: float = 1.0) -> None
def assert_no_nulls(df, cols: list[str]) -> None
def assert_range(df, col: str, lo, hi) -> None
def assert_unique(df, col: str) -> None
def assert_file_exists(path) -> None
def assert_deterministic(fn, *args, runs: int = 2) -> None   # hashes output twice
def report(title: str, rows: list[tuple]) -> str             # markdown table helper
```

A gate that fails is **not** a reason to proceed with a caveat. Fix it.

---

## 10. STAGE INDEX & DEPENDENCY GRAPH

| Stage | Name | Depends on | Primary output | Doc |
|---|---|---|---|---|
| 0 | Environment bootstrap | — | working `.venv`, repo skeleton | 01 |
| 1 | Ingestion & SQL layer | 0 | `raw_combined.parquet`, `audit_data.db`, `sql/queries.sql` | 01 |
| 2 | Cleaning | 1 | `cleaned.parquet`, cleaning ledger | 01 |
| 3 | Synthetic anomaly injection | 2 | `transactions_labeled.parquet`, `injected_anomalies.csv` | 01 |
| 4 | Benford's Law (aggregate + segmented) | 3 | `benford_aggregate.csv`, `benford_segments.csv`, figures | 02 |
| 5 | Rule-based checks | 3 | 5 boolean flag columns + `rule_flag_count` | 02 |
| 6 | Isolation Forest | 3,4,5 | `scored.parquet` with `if_score_fsa`, `if_score_fsb` | 02 |
| 7 | Validation vs ground truth | 6 | `model_metrics.json`, `method_comparison.csv`, PR curve | 03 |
| 8 | Composite risk & export | 7 | `dashboard_export.csv`, `top_risk_transactions.csv` | 03 |
| 9 | Power BI dashboard | 8 | `audit_analytics.pbix` (5 pages) | 03 |
| 10 | Public web dashboard | 8 | live Streamlit URL | 04 |
| 11 | Notebooks, README, figures | 9,10 | `README.md`, 6 notebooks | 04 |
| 12 | Audit findings PDF workpaper | 8,9 | `audit_findings_workpaper.pdf` | 04 |
| 13 | Resume bullets & interview prep | 11,12 | `docs/resume_and_interview.md` | 04 |

```
0 → 1 → 2 → 3 → ┬→ 4 ─┐
                ├→ 5 ─┼→ 6 → 7 → 8 → ┬→ 9 ──┐
                └─────┘               └→ 10 ─┴→ 11 → 12 → 13
```

Stages 4 and 5 are independent of each other and may be built in either order; both must complete before 6.

---

## 11. `config.yaml` — MASTER CONFIGURATION (create in Stage 0)

```yaml
project:
  name: benfords-audit-analytics
  seed: 42
  currency: GBP

paths:
  raw_dir: data/raw
  interim_dir: data/interim
  processed_dir: data/processed
  dashboard_dir: data/dashboard
  db_path: db/audit_data.db
  figures_dir: reports/figures
  metrics_dir: reports/metrics

ingest:
  source_url: "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
  excel_filename: online_retail_II.xlsx
  sheets: ["Year 2009-2010", "Year 2010-2011"]
  expected_rows_total: 1067371
  rowcount_tolerance_pct: 1.0
  sample_size: 50000

cleaning:
  drop_missing_customer: false
  unassigned_customer_label: "UNASSIGNED"
  cancellation_prefix: "C"
  nonproduct_stock_codes: ["POST","DOT","D","M","C2","BANK CHARGES","CRUK",
                           "PADS","S","AMAZONFEE","TEST001","TEST002",
                           "ADJUST","ADJUST2","B"]
  nonproduct_regex: "^[A-Za-z]+$"
  min_benford_amount: 1.00

injection:
  rate: 0.015
  types: [duplicate, threshold_avoidance, round_number,
          digit_fabrication, timing, extreme_outlier]
  duplicate:
    date_jitter_days: 1
  threshold_avoidance:
    thresholds: [1000, 5000, 10000, 500, 250]
    band_fraction: 0.02          # amount lands within 2% below the threshold
  round_number:
    values: [1000, 5000, 10000, 2000, 500]
  digit_fabrication:
    leading_digit_weights: {1: 0.05, 2: 0.05, 3: 0.05, 4: 0.05, 5: 0.05,
                            6: 0.05, 7: 0.10, 8: 0.20, 9: 0.40}
  timing:
    period_end_days: 2
    off_hours_range: [0, 5]      # inject some at 00:00-05:59
    period_end_share: 0.6
  extreme_outlier:
    multiplier_range: [10, 50]

benford:
  digits: [1,2,3,4,5,6,7,8,9]
  min_segment_n: 1000
  mad_thresholds:
    close: 0.006
    acceptable: 0.012
    marginal: 0.015
  chi2_alpha: 0.05
  segment_dimensions: [country, year_month]
  run_second_digit: true
  run_first_two_digits: true

rules:
  duplicate_window_days: 1
  round_multiples: [100, 1000]
  threshold_bands: [[950, 999.99], [4750, 4999.99], [9500, 9999.99],
                    [475, 499.99], [237.5, 249.99]]
  period_end_days: 2
  business_hours: [7, 19]

model:
  contamination_primary: 0.015
  contamination_sensitivity: [0.005, 0.010, 0.030]
  n_estimators: 200
  max_samples: 256
  n_jobs: -1
  run_lof: true
  lof_n_neighbors: 20

composite:
  weight_if: 0.50
  weight_rules: 0.30
  weight_benford: 0.20
  top_n_export: 50

validation:
  precision_at_k: [50, 100, 250, 500, 1000, 5000]
  primary_metric: average_precision
```

---

## 12. `CLAUDE.md` — STANDING INSTRUCTIONS FOR THE CODING AGENT (create in Stage 0)

```markdown
# Agent operating instructions — benfords-audit-analytics

## Before anything
Read `plan/00_MASTER_PLAN.md` in full. Then read only the stage document you
are currently working in.

## Hard rules
1. All logic in `src/`. Notebooks call `src/`. No exceptions.
2. Never let `is_synthetic_anomaly` or `anomaly_type` into a feature matrix.
3. Seed is 42 everywhere. Never change it to improve a result.
4. Use `--sample` while iterating. Full runs only at stage gates.
5. Every stage ends with `python checks/gate_NN.py` passing, a written
   `reports/gate_reports/gate_NN.md`, and a git commit.
6. Ambiguity → decide, proceed, append to `DECISIONS.md`. Do not stall.
7. Never report a number you did not compute. Never fabricate a row count.
8. Never edit a generated data file by hand.

## Style
- Type hints on every public function.
- Google-style docstrings stating what the function returns and its assumptions.
- `logging` not `print` inside `src/`.
- No bare `except:`.
- pandas: prefer vectorised ops; `.copy()` on any slice you mutate;
  never chained assignment.
- Functions under ~50 lines. If longer, split.

## Performance guardrails
- The Excel read is the slow step (~60-120s). Cache to Parquet and never
  re-read the xlsx unless `--force`.
- Full-population Isolation Forest on 1.08M rows with n_estimators=200
  should take under 2 minutes. If it takes more than 10, something is wrong.
- If memory pressure appears, downcast: float64→float32, int64→int32,
  and make `country` / `stock_code` categorical.
```

---

## 13. RISK REGISTER

| # | Risk | Likelihood | Impact | Mitigation (owner: executing agent) |
|---|---|---|---|---|
| R1 | UCI download blocked / URL moved | Med | High | Stage 0 tries the direct URL, then the UCI landing page, then instructs manual download to `data/raw/`; checksum + row-count assertion either way. Never proceed on a partial file. |
| R2 | `.xlsx` read is slow or OOM | Med | Med | Read once, cache to Parquet. Read sheet-by-sheet. Downcast dtypes immediately. |
| R3 | **Chi-square rejects everything at n≈1M** | **High** | **High** | This is expected — the "excess power problem". MAD is the primary verdict; chi-square is reported alongside with an explicit caveat. Stage 4 must discuss this. Getting this wrong is the classic amateur error. |
| R4 | Ground-truth leakage via row ID or ordering | Med | Critical | Leakage Firewall §6 + `gate_03` AUC detector. |
| R5 | Injected anomalies are trivially detectable (e.g. all amounts identical) | Med | High | Injection adds realistic jitter; `gate_03` requires that a naive single-feature threshold on `amount` alone achieves AP < 0.30. If it's higher, the injection is too easy — add noise. |
| R6 | Power BI Service rejects the gmail account | **Certain** | Med | Already handled: `.pbix` stays local, Stage 10 builds a separately hosted public dashboard. |
| R7 | Dashboard data too large for GitHub | Med | Med | `data/dashboard/` ships **aggregates plus the top ~5,000 risk rows only**, hard-capped at 25 MB total; gate_10 asserts it. |
| R8 | Streamlit Community Cloud app sleeps | High | Low | Acceptable; README notes "may take ~30s to wake". Optionally add a static HTML fallback page on GitHub Pages. |
| R9 | Results not reproducible run-to-run | Med | High | Seeds fixed; `assert_deterministic()` in gates 3, 6, 8. |
| R10 | Agent writes plausible-but-wrong metrics into README | Med | High | Stage 11 forbids hand-typed numbers: README figures are injected from `reports/metrics/*.json` by a script, or copied verbatim from a gate report. |
| R11 | Scope creep into Phase 2 | High | Med | `05_FUTURE_ROADMAP.md` exists precisely to absorb every "wouldn't it be cool if". Nothing from it enters Phase 1. |
| R12 | Over-fitting the narrative: claiming the model "found fraud" | Med | High | Language discipline: the model *ranks transactions for review*. It does not detect fraud. Stage 11 and 12 enforce this wording. |

---

## 14. GLOSSARY (for README and interview use)

| Term | Meaning |
|---|---|
| **Benford's Law** | The leading digit `d` of many naturally occurring numeric populations occurs with probability `log10(1 + 1/d)` — 1 appears ~30.1% of the time, 9 only ~4.6%. Deviations can indicate fabricated figures. |
| **MAD** | Mean Absolute Deviation between observed and expected digit proportions: `mean(|observed_i − expected_i|)`. Nigrini's conformity thresholds are applied to it. Sample-size independent, unlike chi-square. |
| **Excess power problem** | With very large n, chi-square rejects conformity for economically trivial deviations. Hence MAD is preferred for large ledgers. |
| **Z-statistic (per digit)** | Tests whether one digit's observed proportion differs significantly from expected, with a continuity correction. Pinpoints *which* digit is anomalous. |
| **Isolation Forest** | Unsupervised ensemble that isolates points by random splits; anomalies require fewer splits, so they get shorter average path lengths and lower `score_samples` values. |
| **Contamination** | The assumed proportion of anomalies, used to set the decision threshold. Unknown in a real engagement. |
| **Average Precision (AP)** | Area under the precision-recall curve; the threshold-free headline metric for heavily imbalanced detection problems. |
| **Precision@k** | Of the top *k* ranked transactions, what fraction are true anomalies. The audit-realistic metric: an audit team can review *k* items, not all of them. |
| **Composite risk score** | Weighted blend of ML score, rule-flag count and Benford segment nonconformity, used to rank the review queue. |
| **Cut-off manipulation** | Recording transactions in the wrong period (typically just before period end) to shift revenue. |
| **Threshold avoidance / structuring** | Splitting or pricing transactions just below an approval limit to escape authorisation controls. |
| **Workpaper** | The documented evidence file an auditor produces to support a conclusion. |

---

## 15. WHAT "DONE" LOOKS LIKE PER STAGE — QUICK REFERENCE

| Stage | One-line acceptance test |
|---|---|
| 0 | `python -c "import pandas, sklearn, scipy, pyarrow; print('ok')"` prints ok inside `.venv` |
| 1 | `audit_data.db` has ≥1.06M rows in `transactions_raw`; all 4 showcase queries return rows |
| 2 | Cleaning ledger accounts for every removed row; `rows_in == rows_out + sum(removed)` |
| 3 | `injected_anomalies.csv` has ~16,000 rows across 6 types; leakage AUC < 0.55 |
| 4 | Aggregate MAD computed; ≥1 segment classified NONCONFORMITY; digit chart rendered |
| 5 | 5 flag columns exist; each flags >0 and <20% of rows; `rule_flag_count` ∈ [0,5] |
| 6 | `if_score_fsa` and `if_score_fsb` present, continuous, no NaN; 4 contamination runs recorded |
| 7 | `method_comparison.csv` is a 7×7+ matrix with no empty cells; PR curve PNG exists |
| 8 | `dashboard_export.csv` opens in Excel; `composite_risk` ∈ [0,1]; top-50 list exported |
| 9 | `.pbix` opens; 5 pages; slicers change the Benford chart |
| 10 | A public URL loads the dashboard from a fresh browser with no login |
| 11 | README renders on GitHub with 3+ images and zero placeholder text |
| 12 | PDF is 4–6 pages, opens, contains the top-25 table |
| 13 | Resume bullets contain real numbers matching `reports/metrics/` |

---

**END OF MASTER PLAN — proceed to `01_STAGES_0-3.md`**
