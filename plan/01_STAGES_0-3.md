# STAGES 0–3 — Foundation, Ingestion, Cleaning, Anomaly Injection

**Document ID:** `01_STAGES_0-3`
**Prerequisite:** `00_MASTER_PLAN.md` read in full.
**Covers:** Stage 0 Environment Bootstrap · Stage 1 Ingestion & SQL · Stage 2 Cleaning · Stage 3 Synthetic Anomaly Injection

> Stage 3 is the differentiator of this whole project. Budget more time there than
> anywhere else. A sloppy injection makes every downstream metric meaningless.

---
---

# STAGE 0 — ENVIRONMENT BOOTSTRAP

**Goal:** a reproducible Python environment, the repo skeleton, config, and the raw data on disk.
**Estimated time:** 45–90 minutes (mostly waiting on installs/download)
**Inputs:** none
**Outputs:** working `.venv`, full directory tree, `config.yaml`, `CLAUDE.md`, `requirements.txt`, `data/raw/online_retail_II.xlsx`

---

## 0.1 Detect what is already installed

The machine's Python state is unknown. Run this detection first and branch on the result.

**Windows PowerShell / cmd detection sequence:**

```powershell
py --version
py -3.11 --version
python --version
python3 --version
where python
where py
conda --version
git --version
```

**Branch table:**

| Detection result | Action |
|---|---|
| `py -3.11` works | Use `py -3.11 -m venv .venv`. Preferred path. |
| `py` works but not 3.11 (e.g. 3.10 / 3.12) | Acceptable — use it. Log a `DECISIONS.md` entry noting the version. Avoid 3.13+. |
| Only `python` works, version ≥3.10 | Use `python -m venv .venv`. |
| `conda` present and Python absent | Create `conda create -n audit python=3.11 -y`, then use pip inside it. Log the deviation; `requirements.txt` still governs versions. |
| Nothing present | Install Python 3.11 (see 0.2) |
| `git --version` fails | Install Git for Windows from `https://git-scm.com/download/win`. Required for Stage 13. |

**Write the detection output verbatim into `reports/gate_reports/gate_00.md`.**

## 0.2 If Python must be installed

1. Download Python 3.11.x (64-bit) from `https://www.python.org/downloads/windows/`.
2. During install: **tick "Add python.exe to PATH"** and choose "Install for all users" if permitted.
3. Verify in a **new** terminal: `py -3.11 --version` → `Python 3.11.x`.
4. Do not use the Microsoft Store Python build — its sandboxed filesystem causes path problems with OneDrive-hosted folders.

> **OneDrive warning (this repo lives under a OneDrive path).** OneDrive can lock or
> cloud-offload files mid-run, which produces confusing `PermissionError` and
> `FileNotFoundError` failures. Two mitigations, in order of preference:
> 1. Right-click the `benfords-audit-analytics` folder → **"Always keep on this device"**.
> 2. If errors persist, move the repo to `C:\dev\benfords-audit-analytics` and log it.
> Add `data/raw`, `data/interim`, `.venv` to OneDrive's excluded-folder list if the option exists.

## 0.3 Create the repository skeleton

```powershell
# from the fraud-detection folder
mkdir benfords-audit-analytics
cd benfords-audit-analytics
git init
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell
# or: .\.venv\Scripts\activate.bat  # cmd
python -m pip install --upgrade pip
```

Create every directory listed in `00_MASTER_PLAN.md` §4, including empty ones (add a `.gitkeep` to each otherwise-empty directory so git tracks them).

## 0.4 `requirements.txt` (exact)

```
pandas>=2.1,<3
numpy>=1.26,<3
scipy>=1.11
scikit-learn>=1.4,<2
matplotlib>=3.8
seaborn>=0.13
pyarrow>=15
openpyxl>=3.1
PyYAML>=6
tqdm>=4.66
jupyterlab>=4
ipykernel>=6
requests>=2.31
reportlab>=4.0
```

Install: `pip install -r requirements.txt`
Freeze the resolved versions for the README: `pip freeze > requirements.lock.txt`

## 0.5 Files to author in Stage 0

| File | Content source |
|---|---|
| `config.yaml` | Copy verbatim from `00_MASTER_PLAN.md` §11 |
| `CLAUDE.md` | Copy verbatim from `00_MASTER_PLAN.md` §12 |
| `.gitignore` | Copy verbatim from `00_MASTER_PLAN.md` §4.1 |
| `DECISIONS.md` | Header + `## Pre-registered defaults` table copied from §7 |
| `CHANGELOG.md` | Header only |
| `src/__init__.py` | empty |
| `src/config.py` | see 0.6 |
| `src/logging_setup.py` | see 0.7 |
| `checks/common.py` | signatures in `00_MASTER_PLAN.md` §9 |

## 0.6 `src/config.py` — specification

**Purpose:** load `config.yaml` once, expose it as an attribute-accessible object, and resolve all paths to absolute `pathlib.Path` objects relative to the repo root.

```python
# Signatures only — agent writes bodies.

REPO_ROOT: Path                 # resolved as Path(__file__).resolve().parents[1]

class Config:
    """Attribute-access wrapper around the parsed config.yaml dict.

    Nested mappings are wrapped recursively so cfg.injection.rate works.
    Any key under `paths` is returned as an absolute Path with parents created.
    """
    def __getattr__(self, name: str) -> Any: ...
    def to_dict(self) -> dict: ...

def load_config(path: Path | None = None) -> Config:
    """Load config.yaml. Caches on first call. Raises FileNotFoundError with a
    clear message naming the expected location if absent."""

cfg = load_config()             # module-level singleton, imported everywhere

COLUMN_RENAME_MAP: dict[str, str]   # exactly as in MASTER_PLAN §2.4
```

**Acceptance test:**
```python
from src.config import cfg
assert cfg.project.seed == 42
assert cfg.paths.raw_dir.is_absolute() and cfg.paths.raw_dir.exists()
assert cfg.injection.rate == 0.015
```

## 0.7 `src/logging_setup.py` — specification

```python
def setup_logging(stage: str, level: int = logging.INFO) -> logging.Logger:
    """Configure root logging to BOTH stdout and logs/pipeline_<stage>_<ts>.log.

    Format: '%(asctime)s | %(levelname)-7s | %(name)s | %(message)s'
    Idempotent: calling twice must not duplicate handlers.
    Returns a logger named f'audit.{stage}'.
    """

@contextmanager
def timed(logger, label: str):
    """Log 'START <label>' / 'DONE <label> in X.Xs'. Used to wrap every stage."""
```

## 0.8 Acquire the raw data

`src/ingest.py::download_raw()` — specification:

```python
def download_raw(force: bool = False) -> Path:
    """Ensure data/raw/online_retail_II.xlsx exists. Returns its path.

    Order of attempts:
      1. If the xlsx already exists and force is False -> return immediately.
      2. requests.get(cfg.ingest.source_url, stream=True, timeout=120) with a
         browser-like User-Agent; write to data/raw/online_retail_II.zip with a
         tqdm progress bar; verify Content-Length matches bytes written.
      3. Unzip with zipfile; locate the member whose name ends '.xlsx'
         (do NOT assume the exact member name); extract to data/raw/.
      4. On any network failure: raise RuntimeError with a message that prints
         the landing-page URL and the exact target path, instructing a manual
         download. Do NOT fall back to a synthetic dataset silently.

    Post-conditions (assert):
      - file exists, size between 35_000_000 and 60_000_000 bytes
      - openpyxl can open it and both configured sheet names are present
    """
```

> **Proxy/TLS note:** if downloads fail with certificate errors on this machine,
> do not disable verification. Download manually in a browser and place the file.

## 0.9 Stage 0 Gate — `checks/gate_00.py`

Assertions:

1. `sys.version_info >= (3, 10)` and the interpreter path contains `.venv`.
2. All of `pandas, numpy, scipy, sklearn, matplotlib, seaborn, pyarrow, openpyxl, yaml` import.
3. Every directory in MASTER_PLAN §4 exists.
4. `config.yaml`, `CLAUDE.md`, `.gitignore`, `requirements.txt` exist and are non-empty.
5. `from src.config import cfg` works and `cfg.project.seed == 42`.
6. `data/raw/online_retail_II.xlsx` exists, size in the expected band.
7. `openpyxl.load_workbook(path, read_only=True).sheetnames` contains both configured sheets.
8. `git rev-parse --is-inside-work-tree` returns true.

**Gate report must record:** Python version, pip freeze output, xlsx file size in MB, sheet names found.

**Commit:** `stage(00): bootstrap environment, repo skeleton, config, raw data`

---
---

# STAGE 1 — INGESTION & SQL LAYER

**Goal:** load both sheets into one tidy DataFrame, cache as Parquet, mirror into SQLite, and write four showcase SQL queries.
**Estimated time:** 1.5–2 hours
**Inputs:** `data/raw/online_retail_II.xlsx`
**Outputs:** `data/interim/raw_combined.parquet`, `data/interim/sample_50k.parquet`, `db/audit_data.db`, `sql/schema.sql`, `sql/queries.sql`, `reports/metrics/stage1_profile.json`

---

## 1.1 `src/ingest.py` — specification

```python
def load_sheet(xlsx_path: Path, sheet_name: str) -> pd.DataFrame:
    """Read one sheet with pd.read_excel(engine='openpyxl').
    Adds a 'source_sheet' column set to sheet_name.
    Does NOT rename columns.
    Logs rows read and elapsed seconds."""

def combine_sheets(xlsx_path: Path, sheets: list[str]) -> pd.DataFrame:
    """Read each sheet, concat with ignore_index=True, then:
      - rename via COLUMN_RENAME_MAP
      - assert the 8 canonical columns are present
      - add 'line_no' = a stable 0-based integer within the concatenated order
        (this is ONLY used for deterministic sorting, never as a feature)
    Returns the combined frame."""

def optimise_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Downcast for memory:
      quantity -> int32 (after verifying no overflow)
      price    -> float32
      country, stock_code, source_sheet -> category
      invoice, description -> string[python]
      customer_id -> keep nullable Float64 for now (cleaned in Stage 2)
    Log memory_usage(deep=True).sum() before and after."""

def profile_raw(df: pd.DataFrame) -> dict:
    """Return a JSON-serialisable profile:
      n_rows, n_cols, per-column: dtype, n_null, pct_null, n_unique,
      min/max for numeric and datetime columns,
      top 10 countries by row count,
      n_invoices, n_customers, n_stock_codes,
      pct_rows_with_C_prefix_invoice,
      pct_rows_negative_quantity, pct_rows_nonpositive_price,
      date_min, date_max,
      hour_histogram (24 buckets)
    Written to reports/metrics/stage1_profile.json."""

def build_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Stratified sample: sample proportionally within (source_sheet, country-top10
    vs 'OTHER') strata so the sample preserves the country mix. Deterministic."""

def run(force: bool = False, sample: bool = False) -> None:
    """Stage entry point called by pipeline.py."""
```

### 1.1.1 Caching rule

`raw_combined.parquet` is written once. Every subsequent stage reads the Parquet, never the xlsx. If `--force` is passed, the xlsx is re-read. Log clearly which path was taken.

### 1.1.2 Expected runtime

Excel read: 60–150 s total for both sheets. Parquet read thereafter: <3 s. If the Excel read exceeds 10 minutes, the agent should check that `read_only` memory settings and `openpyxl` are being used correctly, and log the finding.

## 1.2 `src/sqlite_load.py` — specification

```python
def create_schema(conn: sqlite3.Connection) -> None:
    """Execute sql/schema.sql."""

def load_transactions(df: pd.DataFrame, conn: sqlite3.Connection,
                      table: str = "transactions_raw",
                      chunksize: int = 50_000) -> int:
    """pandas.to_sql with if_exists='replace', index=False, method='multi'.
    Datetime columns written as ISO-8601 TEXT (SQLite has no datetime type).
    Returns rows written; asserts it equals len(df)."""

def create_indexes(conn: sqlite3.Connection) -> None:
    """CREATE INDEX on customer_id, country, invoice_date, invoice, amount."""

def verify(conn: sqlite3.Connection, expected_rows: int) -> dict:
    """SELECT COUNT(*), COUNT(DISTINCT invoice), MIN/MAX(invoice_date).
    Returns dict; asserts count matches expected_rows exactly."""
```

### 1.2.1 `sql/schema.sql`

```sql
DROP TABLE IF EXISTS transactions_raw;
CREATE TABLE transactions_raw (
    line_no       INTEGER,
    invoice       TEXT,
    stock_code    TEXT,
    description   TEXT,
    quantity      INTEGER,
    invoice_date  TEXT,          -- ISO-8601
    price         REAL,
    customer_id   TEXT,
    country       TEXT,
    source_sheet  TEXT,
    amount        REAL
);
CREATE INDEX idx_tr_customer ON transactions_raw(customer_id);
CREATE INDEX idx_tr_country  ON transactions_raw(country);
CREATE INDEX idx_tr_date     ON transactions_raw(invoice_date);
CREATE INDEX idx_tr_invoice  ON transactions_raw(invoice);
CREATE INDEX idx_tr_amount   ON transactions_raw(amount);
```

> `amount` is computed in Stage 1 (`quantity * price`) so the SQL queries below can use it.
> Full cleaning still happens in Stage 2; the SQLite table is the *raw* mirror.

## 1.3 `sql/queries.sql` — the four required queries plus two bonus

Each query must be preceded by a comment block explaining the audit purpose. This file is quoted in the README as SQL evidence, so it must be readable, formatted, and commented.

```sql
-- =============================================================
-- Q1. Transaction value and volume by country and month
-- Audit purpose: establishes the population and identifies
-- geographic/temporal concentrations that warrant segment testing.
-- =============================================================
SELECT
    country,
    strftime('%Y-%m', invoice_date)              AS year_month,
    COUNT(*)                                      AS txn_count,
    ROUND(SUM(amount), 2)                         AS total_value,
    ROUND(AVG(amount), 2)                         AS avg_value,
    ROUND(MIN(amount), 2)                         AS min_value,
    ROUND(MAX(amount), 2)                         AS max_value
FROM transactions_raw
WHERE amount > 0
GROUP BY country, year_month
ORDER BY total_value DESC;

-- =============================================================
-- Q2. Top 20 customers by total transaction value
-- Audit purpose: revenue concentration. A small number of
-- customers driving most revenue raises both a going-concern
-- consideration and a targeted-testing opportunity.
-- =============================================================
SELECT
    customer_id,
    country,
    COUNT(DISTINCT invoice)                       AS invoice_count,
    COUNT(*)                                      AS line_count,
    ROUND(SUM(amount), 2)                         AS total_value,
    ROUND(AVG(amount), 2)                         AS avg_line_value,
    MIN(invoice_date)                             AS first_txn,
    MAX(invoice_date)                             AS last_txn
FROM transactions_raw
WHERE customer_id IS NOT NULL
  AND customer_id <> 'UNASSIGNED'
  AND amount > 0
GROUP BY customer_id, country
ORDER BY total_value DESC
LIMIT 20;

-- =============================================================
-- Q3. Duplicate-candidate detection
-- Audit purpose: duplicate billing / duplicate revenue recognition.
-- Same customer, same value, same calendar day, more than one
-- distinct invoice = candidate for duplicate-payment testing.
-- =============================================================
SELECT
    customer_id,
    DATE(invoice_date)                            AS txn_date,
    ROUND(amount, 2)                              AS amount_rounded,
    COUNT(*)                                      AS occurrences,
    COUNT(DISTINCT invoice)                       AS distinct_invoices,
    GROUP_CONCAT(DISTINCT invoice)                AS invoice_list,
    ROUND(SUM(amount), 2)                         AS total_exposure
FROM transactions_raw
WHERE amount > 0
  AND customer_id IS NOT NULL
GROUP BY customer_id, txn_date, amount_rounded
HAVING COUNT(*) > 1
   AND COUNT(DISTINCT invoice) > 1
ORDER BY total_exposure DESC
LIMIT 200;

-- =============================================================
-- Q4. Monthly transaction volume trend + period-end concentration
-- Audit purpose: cut-off testing. An abnormal share of the month's
-- volume booked in the final two days suggests period-end pressure.
-- =============================================================
WITH monthly AS (
    SELECT
        strftime('%Y-%m', invoice_date)           AS year_month,
        COUNT(*)                                   AS txn_count,
        SUM(amount)                                AS total_value,
        SUM(CASE
              WHEN CAST(strftime('%d', invoice_date) AS INTEGER) >=
                   CAST(strftime('%d', DATE(invoice_date,'start of month','+1 month','-2 day')) AS INTEGER)
              THEN 1 ELSE 0 END)                   AS last2day_count
    FROM transactions_raw
    WHERE amount > 0
    GROUP BY year_month
)
SELECT
    year_month,
    txn_count,
    ROUND(total_value, 2)                          AS total_value,
    last2day_count,
    ROUND(100.0 * last2day_count / txn_count, 2)   AS pct_in_last_2_days
FROM monthly
ORDER BY year_month;

-- =============================================================
-- Q5 (bonus). Leading-digit distribution straight in SQL
-- Audit purpose: demonstrates Benford extraction without Python,
-- useful when the only access to client data is a read-only DB.
-- =============================================================
WITH positive AS (
    SELECT CAST(SUBSTR(
        REPLACE(printf('%.2f', amount), '.', ''), 1, 1) AS INTEGER) AS lead_digit
    FROM transactions_raw
    WHERE amount >= 1.0
)
SELECT
    lead_digit,
    COUNT(*)                                       AS observed_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4) AS observed_pct
FROM positive
WHERE lead_digit BETWEEN 1 AND 9
GROUP BY lead_digit
ORDER BY lead_digit;

-- =============================================================
-- Q6 (bonus). Round-amount concentration by customer
-- Audit purpose: manual journal entries and estimates cluster on
-- round numbers; system-generated sales rarely do.
-- =============================================================
SELECT
    customer_id,
    COUNT(*)                                       AS txn_count,
    SUM(CASE WHEN amount > 0 AND CAST(amount AS INTEGER) = amount
             AND CAST(amount AS INTEGER) % 100 = 0
        THEN 1 ELSE 0 END)                         AS round_100_count,
    ROUND(100.0 * SUM(CASE WHEN amount > 0 AND CAST(amount AS INTEGER) = amount
             AND CAST(amount AS INTEGER) % 100 = 0
        THEN 1 ELSE 0 END) / COUNT(*), 2)          AS pct_round_100
FROM transactions_raw
WHERE amount > 0 AND customer_id IS NOT NULL
GROUP BY customer_id
HAVING COUNT(*) >= 50
ORDER BY pct_round_100 DESC
LIMIT 25;
```

**Requirement:** the agent must actually execute all six queries, save each result to `reports/metrics/sql_q1.csv` … `sql_q6.csv` (truncated to 200 rows each), and paste the first 10 rows of each into the gate report. A query that has never been run is not evidence of SQL skill.

> **Hint for Q4:** the SQLite date arithmetic above is fiddly. An acceptable
> simplification is to compute `days_to_month_end` in Python during Stage 2 and
> expose it as a column, then keep Q4 simple. If the agent simplifies, it must
> log a `DECISIONS.md` entry and keep the query correct rather than clever.

## 1.4 Stage 1 Gate — `checks/gate_01.py`

1. `raw_combined.parquet` exists; `len(df)` within 1% of 1,067,371.
2. All 8 canonical columns + `line_no`, `source_sheet`, `amount` present.
3. `invoice_date` dtype is datetime64; `df.invoice_date.min().year == 2009`; `.max().year == 2011`.
4. `amount` equals `quantity * price` for a random 1,000-row check (tolerance 1e-6).
5. `sample_50k.parquet` exists, has exactly `cfg.ingest.sample_size` rows, and its country distribution is within 2 percentage points of the full frame for the top 5 countries.
6. SQLite: `SELECT COUNT(*) FROM transactions_raw` equals `len(df)`.
7. All 5 indexes exist (`PRAGMA index_list`).
8. All six queries execute without error and return ≥1 row.
9. `stage1_profile.json` exists and contains a 24-bucket hour histogram.

**Gate report must record:** actual row counts per sheet, memory before/after downcasting, top 10 countries, % null customer_id, % C-prefixed invoices, % negative quantity, date range, the hour histogram, and the first 10 rows of each SQL query.

**Commit:** `stage(01): ingest both sheets, parquet cache, sqlite mirror, showcase SQL`

---
---

# STAGE 2 — CLEANING

**Goal:** produce a defensible analysis population, with every excluded row accounted for in a cleaning ledger.
**Estimated time:** 2 hours
**Inputs:** `data/interim/raw_combined.parquet`
**Outputs:** `data/interim/cleaned.parquet`, `data/interim/cancellations.parquet`, `reports/metrics/cleaning_ledger.json`, `reports/figures/hour_distribution.png`

---

## 2.1 The cleaning philosophy for an audit context

In a commercial data-science project you drop bad rows. In an audit you **account for** them. Completeness is an assertion under test. Therefore this stage produces a *ledger* — a reconciliation where:

```
rows_in  ==  rows_out  +  Σ(rows moved to each bucket)
```

and that identity is asserted. No row disappears unexplained.

**Buckets (rows leave the main population into these, they are not deleted):**

| Bucket | Definition | Destination |
|---|---|---|
| `cancellations` | `invoice` starts with `C` | `cancellations.parquet`, excluded from main population |
| `adjustments` | `stock_code` in the non-product list or matching `^[A-Za-z]+$` | **retained** in main population, flagged `is_adjustment=True`, excluded from Benford |
| `nonpositive_amount` | `amount <= 0` and not a cancellation | **retained**, flagged `is_nonpositive_amount=True`, excluded from Benford |
| `missing_customer` | `customer_id` null | **retained**, set to `"UNASSIGNED"`, flagged `has_customer_stats=False` |
| `missing_description` | `description` null | **retained**, description set to `"(no description)"` |
| `exact_duplicates` | full-row duplicates across all raw columns | **removed**, counted — these are true data-quality artefacts |

Only `exact_duplicates` and `cancellations` reduce the main population. Everything else is flagged, not dropped. This is the auditable choice, and it is what the README should say.

## 2.2 `src/clean.py` — specification

```python
def normalise_types(df: pd.DataFrame) -> pd.DataFrame:
    """invoice/stock_code -> str, uppercased, stripped.
       customer_id -> string; nulls -> cfg.cleaning.unassigned_customer_label;
                      non-nulls formatted as integer strings ('17850' not '17850.0').
       description  -> str, stripped, nulls -> '(no description)'.
       country      -> str, stripped, title-cased consistently
                       (watch 'EIRE', 'RSA', 'Unspecified', 'European Community').
       invoice_date -> pd.to_datetime, errors='raise'."""

def flag_cancellations(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split on invoice.str.startswith(cfg.cleaning.cancellation_prefix).
    Returns (main, cancellations). Log counts and total value of each.
    Sanity check to log: cancellations should be predominantly negative quantity."""

def flag_adjustments(df: pd.DataFrame) -> pd.DataFrame:
    """Add is_adjustment: stock_code in configured list OR matches nonproduct_regex.
    Log the top 20 adjustment stock_codes by row count so the analyst can eyeball
    whether the regex is over-reaching."""

def compute_amount(df: pd.DataFrame) -> pd.DataFrame:
    """amount = (quantity * price).round(2).
    Add is_nonpositive_amount = amount <= 0."""

def derive_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive, all from invoice_date:
        year            int16
        month           int8            (1-12)
        year_month      str             'YYYY-MM'   <- segment key
        quarter         str             'YYYYQn'
        day             int8
        day_of_week     int8            (0=Mon .. 6=Sun)
        day_name        category
        hour            int8            (0-23)
        minute          int8
        is_month_end    bool            day within last N days of month (cfg)
        is_quarter_end  bool
        days_to_month_end int8
        date            date            (for duplicate windowing)
    """

def drop_exact_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop rows duplicated across ALL raw columns
    (invoice, stock_code, quantity, invoice_date, price, customer_id, country).
    Returns (df, n_dropped). Log examples of 3 dropped rows."""

def add_customer_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Per customer_id (excluding UNASSIGNED), compute over POSITIVE amounts only:
        cust_txn_count, cust_amount_mean, cust_amount_std, cust_amount_median,
        cust_amount_mad (median absolute deviation), cust_qty_mean, cust_qty_std
    Merge back. For UNASSIGNED rows and customers with cust_txn_count < 5,
    set has_customer_stats = False and leave the stats as NaN (filled downstream).
    NOTE: these stats are computed on the CLEAN population BEFORE injection, and
    are recomputed in Stage 6 on the POST-injection population. Stage 2's version
    exists only for profiling; Stage 6 owns the modelling version. Log this."""

def build_cleaning_ledger(counts: dict) -> dict:
    """Assemble the reconciliation dict and ASSERT the identity:
        rows_in == rows_out + cancellations + exact_duplicates_dropped
    Raise AssertionError with the arithmetic printed if it fails."""

def run(force: bool = False, sample: bool = False) -> None: ...
```

## 2.3 Required diagnostics (write to `reports/figures/`)

| Figure | File | Purpose |
|---|---|---|
| Hour-of-day histogram | `hour_distribution.png` | Validates the 07:00–20:00 business-hours assumption for Stage 5 |
| Day-of-week bar | `dow_distribution.png` | Shows whether Saturday/Sunday trade; informs off-hours rule |
| Amount distribution (log x) | `amount_distribution.png` | Shows the heavy tail justifying log1p in Stage 6 |
| Monthly volume line | `monthly_volume.png` | Baseline for period-end analysis |
| Nulls / bucket waterfall | `cleaning_waterfall.png` | Visual of the cleaning ledger — excellent README material |

## 2.4 Explicit checks the agent must perform and report

1. **Does the hour histogram support 07:00–20:00?** Report the % of rows outside that window. If >2%, reconsider the window and log a decision.
2. **Is Sunday traded?** Report Sunday's share of rows. (In this dataset it is materially traded — confirm.)
3. **How many distinct countries?** Report the full list with counts; note any that will be too small for segment-level Benford (n<1000).
4. **What is the cancellation rate?** Report count, % of rows, and total absolute value.
5. **What share of rows are adjustments?** Report and list the codes.
6. **Any dates outside Dec 2009 – Dec 2011?** Report min/max.
7. **Any `price` of exactly 0 with positive quantity?** These are often promotional/sample lines — report the count; they become `is_nonpositive_amount`.

## 2.5 Stage 2 Gate — `checks/gate_02.py`

1. `cleaned.parquet` and `cancellations.parquet` exist.
2. Ledger identity holds exactly (see 2.2 `build_cleaning_ledger`).
3. No nulls in: `invoice, stock_code, description, quantity, invoice_date, price, customer_id, country, amount`.
4. `customer_id` is string dtype; no value ends in `.0`; `"UNASSIGNED"` present.
5. `hour` ∈ [0,23]; `day_of_week` ∈ [0,6]; `month` ∈ [1,12]; `year_month` matches `^\d{4}-\d{2}$`.
6. `amount == round(quantity * price, 2)` for all rows (vectorised, tolerance 0.005).
7. No row in `cleaned` has an invoice starting with `C`.
8. All five figures exist and are >10 KB.
9. `cleaning_ledger.json` exists and every bucket count is an integer ≥0.

**Gate report must record:** the full cleaning ledger as a markdown table, the answers to all seven questions in §2.4, and the final population row count (this number is quoted in the README and resume bullets).

**Commit:** `stage(02): cleaning, ledger reconciliation, time features, diagnostics`

---
---

# STAGE 3 — SYNTHETIC ANOMALY INJECTION

> **This is the differentiator. Spend the most time here.**
> Everything in Stages 7, 12 and 13 — every precision/recall figure, the method
> comparison matrix, the resume bullet — is only as credible as this stage.

**Goal:** inject ~1.5% synthetic anomalies across six fraud archetypes, realistic enough that they are not trivially separable, with a complete ground-truth log.
**Estimated time:** 4–6 hours (the single largest block in Phase 1)
**Inputs:** `data/interim/cleaned.parquet`
**Outputs:** `data/processed/transactions_labeled.parquet` + `.csv`, `data/processed/injected_anomalies.csv`, `reports/metrics/injection_summary.json`, `reports/figures/injection_*.png`

---

## 3.1 Design principles (read before writing a line of injection code)

1. **Realism beats volume.** An injected row must be individually plausible. If a
   human auditor scanning 20 rows could pick out every synthetic one at a glance,
   the injection is broken.
2. **Each anomaly type must be catchable by at least one method — and ideally
   *not* by all of them.** The whole point of Stage 7's matrix is that methods
   differ. If every type is caught by everything, the matrix is boring and the
   project's central argument collapses.
3. **Inherit, don't invent.** Every injected row is derived from a real sampled
   row (same customer, same country, same stock code family, plausible price
   range) and only the specific manipulated attribute is changed.
4. **Jitter everything.** Never inject a hard-coded constant. Amounts, dates,
   quantities, hours all get controlled randomness.
5. **No structural tells.** Injected rows must not be distinguishable by row
   order, ID pattern, missing fields, dtype, precision, or any column the model
   sees. See §3.6.
6. **Full determinism.** One `numpy.random.default_rng(seed)` threaded through
   every generator; two runs with the same seed produce byte-identical output.
7. **Document the parameters actually used.** Every injected row's parameters go
   into the ground-truth log so the Stage 7 analysis can slice by them.

## 3.2 Volume plan

```
base_rows            = len(cleaned)                    # ~1,040,000 expected
n_inject_total       = round(base_rows * 0.015)        # ~15,600
n_per_type           = n_inject_total // 6             # ~2,600 each
remainder            -> added to `duplicate`
```

Injected rows are **appended** to the population (they do not replace real rows), so the final population is `base_rows + n_inject_total` and the true anomaly rate is `n_inject_total / (base_rows + n_inject_total)` ≈ **1.478%**. Report the exact figure; do not round it in the README.

> **Design decision, pre-registered (PD-06):** appending rather than overwriting
> keeps the real population intact and means a "false positive" is always a
> genuine real transaction — the interpretation in Stage 7 stays clean.

## 3.3 The six anomaly archetypes — full specifications

Every generator has the same contract:

```python
def inject_<type>(base: pd.DataFrame, n: int, rng: np.random.Generator,
                  cfg) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (new_rows, log_rows).

    new_rows : DataFrame with EXACTLY the same columns/dtypes as `base`
               (schema equality is asserted by the caller)
    log_rows : DataFrame with columns
               [temp_key, anomaly_type, source_line_no, params_json, note]
    """
```

---

### 3.3.1 Type 1 — `duplicate` (duplicate billing / double revenue recognition)

**Audit rationale:** the same sale recorded twice under different invoice numbers inflates revenue and, in a payables context, causes duplicate payment. It is one of the highest-frequency findings in real duplicate-payment testing.

**Generation algorithm:**

1. Eligible source pool: real rows with `amount > 0`, `customer_id != "UNASSIGNED"`, `is_adjustment == False`.
2. Sample `n` source rows **without replacement**, weighted toward higher amounts
   (weight ∝ `log1p(amount)`) — duplicating a £2 line is uninteresting; a fraudster
   duplicates material items. Log this weighting choice.
3. For each source row, copy it and change:
   - `invoice` → a new invoice number that **looks native**: 6 digits, drawn from the
     unused space adjacent to the real invoice range (e.g. real max + 1..50,000, or a
     gap in the sequence). Must not collide with an existing invoice.
   - `invoice_date` → source date ± `Uniform{-1, 0, +1}` days, with a **new plausible
     time** drawn from the empirical hour/minute distribution of the real data (not
     the source row's exact time — an exact timestamp match is a structural tell).
   - `quantity`, `price`, `amount` → unchanged (this is the signal).
   - Everything else → unchanged.
4. 20% of duplicates should be "triples" (the same source duplicated twice) to
   create a realistic long tail — real duplicate billing is not always pairwise.

**Which method should catch it:** rule-based `flag_duplicate` (high), Isolation Forest (low — a duplicate is not an outlier in feature space), Benford (none). **This is the archetype that proves rules beat ML.**

**Log params:** `{"source_invoice": ..., "new_invoice": ..., "date_shift_days": ..., "is_triple": bool}`

---

### 3.3.2 Type 2 — `threshold_avoidance` (structuring below approval limits)

**Audit rationale:** organisations set authorisation thresholds (e.g. any item over £1,000 needs a second signature). Structuring means pricing or splitting transactions to land just below the limit. The statistical signature is an unnatural spike immediately below round thresholds and a corresponding void immediately above.

**Generation algorithm:**

1. Thresholds from config: `[250, 500, 1000, 5000, 10000]`, sampled with weights
   `[0.15, 0.20, 0.35, 0.20, 0.10]` (smaller limits are more common in practice).
2. Target amount = `T * (1 - Uniform(0.0005, cfg.injection.threshold_avoidance.band_fraction))`
   → lands within 0.05%–2% below `T`, e.g. £981.40, £994.75, £999.20.
3. Round the target to 2 dp.
4. **Realise the amount through quantity × price**, do not fabricate `amount` directly:
   - Sample a source row for customer/country/stock_code context.
   - Choose `quantity` from the empirical quantity distribution for that stock_code
     (fall back to the global distribution), constrained to 1–500.
   - Set `price = round(target_amount / quantity, 2)`.
   - Recompute `amount = round(quantity * price, 2)`; accept if
     `|amount - target| <= 0.05 * T * band_fraction`, else resample quantity (max 20 tries,
     then fall back to quantity=1).
   > **Why this matters:** if you set `amount` directly and leave `quantity*price`
   > inconsistent, the model can detect injected rows via the arithmetic mismatch —
   > a catastrophic leak. `gate_03` asserts `amount == round(quantity*price, 2)` for
   > **every** injected row.
5. `invoice_date` sampled from the real date range with a plausible time; ~30% of
   these should cluster with the same customer on the same day (a split transaction
   looks like several sub-limit lines at once) — implement as: for 30% of rows,
   emit 2–4 sibling rows under the same customer and date with different invoices,
   each sub-threshold. Count siblings toward `n`.

**Which method should catch it:** rule-based `flag_threshold_avoidance` (high), Benford (moderate — inflates leading digits 9, 4, 2), Isolation Forest (low-moderate).

**Log params:** `{"threshold": T, "target_amount": ..., "realised_amount": ..., "quantity": ..., "price": ..., "sibling_group": id|null}`

---

### 3.3.3 Type 3 — `round_number` (manual journal entries / estimates)

**Audit rationale:** system-generated sales produce messy amounts. Round amounts (£1,000.00 exactly) are the fingerprint of a human typing a number — an accrual, an estimate, a top-side adjustment, or a fabricated entry.

**Generation algorithm:**

1. Values from config `[500, 1000, 2000, 5000, 10000]`, weights `[0.25,0.30,0.20,0.15,0.10]`.
2. Realise through `quantity × price` as in 3.3.2, but choose quantity from divisors
   that give clean prices: pick `quantity ∈ {1, 2, 4, 5, 10, 20, 25, 50, 100}` such
   that `value / quantity` has ≤2 dp. Accept only exact realisations
   (`amount == value` to the penny).
3. 15% of these should be round *near*-values (£999.99, £1,000.01) — a deliberate
   hard negative that tests whether the rule's equality check is brittle. Tag these
   in the log with `"near_round": true`.
4. Bias toward month-end dates (40%) — manual entries cluster at close.

**Which method should catch it:** rule-based `flag_round_number` (very high), Isolation Forest (low), Benford (moderate — pushes digits 1 and 5).

**Log params:** `{"target_value": ..., "quantity": ..., "price": ..., "near_round": bool, "at_month_end": bool}`

---

### 3.3.4 Type 4 — `digit_fabrication` (Benford violation)

**Audit rationale:** humans inventing numbers under-produce leading 1s and over-produce leading 7/8/9, because invented figures feel "more random" when they start high. This is the archetype Benford's Law exists to catch, and **it must be nearly invisible to the rule-based checks** — otherwise the Stage 7 matrix has nothing to prove.

**Generation algorithm:**

1. Draw a leading digit `d` from `cfg.injection.digit_fabrication.leading_digit_weights`
   (heavily skewed: 9→0.40, 8→0.20, 7→0.10, 1–6→0.05 each).
2. Draw a magnitude exponent `e` from the **empirical** distribution of
   `floor(log10(amount))` in the real positive population — so injected amounts occupy
   the same value range as real ones (critical: if all fabricated amounts are £900–999
   they become extreme-value outliers instead of digit anomalies).
3. Draw the remaining mantissa digits uniformly:
   `amount = (d + Uniform(0,1)) * 10**e`, rounded to 2 dp.
4. **Reject** any amount that is an exact multiple of 100 or falls in a
   `threshold_bands` window — otherwise this type contaminates types 2 and 3 and the
   comparison matrix becomes muddy. Resample (max 50 tries).
5. Realise through quantity × price as before, preserving the leading digit of
   `amount` after the 2-dp rounding (assert it).
6. Concentrate ~60% of these rows into **2–3 specific (country, year_month) segments**
   chosen from mid-sized segments (n between 3,000 and 30,000). This is what makes
   *segment-level* Benford testing outperform aggregate testing — and it is the exact
   evidence behind the resume bullet "segmented testing surfaced X% more anomalies
   than aggregate analysis alone." Record the chosen segments in
   `injection_summary.json` under `benford_target_segments`.

**Which method should catch it:** Benford segment flags (high, and *only* at segment level), rules (near zero — by construction), Isolation Forest (low).

**Log params:** `{"leading_digit": d, "exponent": e, "amount": ..., "target_segment": "Country|YYYY-MM"|null}`

---

### 3.3.5 Type 5 — `timing` (cut-off manipulation and off-hours entry)

**Audit rationale:** revenue pulled into a period is booked in its final days; unauthorised entries are often made outside working hours when oversight is lowest.

**Generation algorithm:** split `n` into two sub-types, logged separately as
`timing_period_end` and `timing_off_hours` (so Stage 7 can report them separately
while still rolling up to `timing`).

**5a. Period-end (60% of `n`)**
- Choose a month uniformly from the dataset's months, weighted 2× toward
  quarter-end months (Mar, Jun, Sep, Dec) — cut-off pressure is strongest at quarters.
- Date = one of the final `cfg.injection.timing.period_end_days` (2) days of that month.
- Time = plausible business hours.
- Amount = drawn from the customer's own amount distribution (so it is *not* an
  amount anomaly — the anomaly is purely temporal).
- Inflate volume: for a chosen (month) the injected period-end rows should raise
  that month's last-2-day share by a *detectable but not absurd* margin. Target:
  final-2-day share rises by 2–5 percentage points in the affected months. Compute
  and assert this after injection; log the before/after shares.

**5b. Off-hours (40% of `n`)**
- Date uniform over the range.
- Time drawn from `Uniform(00:00, 05:59)` (config `off_hours_range`), plus a small
  share at 22:00–23:59.
- Everything else drawn from a real source row.

**Which method should catch it:** rules `flag_period_end` / `flag_off_hours` (high), Isolation Forest (moderate for off-hours once `hour` is a feature; low for period-end), Benford (none).

**Log params:** `{"subtype": "period_end"|"off_hours", "month": "YYYY-MM", "hour": ..., "days_to_month_end": ...}`

---

### 3.3.6 Type 6 — `extreme_outlier` (unsupported material entries)

**Audit rationale:** a single line 10–50× the customer's norm with no supporting documentation is the classic material misstatement. It is also the archetype **Isolation Forest should dominate** — proving the ML layer earns its place.

**Generation algorithm:**

1. Eligible customers: those with `cust_txn_count >= 20` (so "typical" is meaningful).
2. Sample a source row from that customer.
3. Multiplier `m ~ Uniform(10, 50)`.
4. Split the inflation between quantity and price so neither alone is absurd:
   - 40% of cases: quantity × m, price unchanged (bulk order)
   - 30% of cases: price × m, quantity unchanged (mispriced line)
   - 30% of cases: quantity × sqrt(m), price × sqrt(m)
5. Round quantity to int (min 1) and price to 2 dp; recompute `amount`.
6. **Reject** results whose `amount` is an exact round number or lands in a threshold
   band (same contamination-avoidance rule as 3.3.4).
7. Date/time plausible; ~25% at month-end for flavour.

**Which method should catch it:** Isolation Forest (very high, both feature sets), rules (near zero), Benford (none — a handful of rows cannot move a digit distribution).

**Log params:** `{"source_line_no": ..., "multiplier": m, "mode": "qty"|"price"|"both", "cust_amount_mean": ..., "z_score_realised": ...}`

---

## 3.4 The contamination matrix — verify the design works

After injection, before anything else, produce this table and put it in the gate report. It is the *designed* answer that Stage 7 will later measure empirically.

| Injected type | Benford (segment) | Rules | Isolation Forest |
|---|---|---|---|
| duplicate | none | **high** | low |
| threshold_avoidance | moderate | **high** | low–moderate |
| round_number | moderate | **high** | low |
| digit_fabrication | **high (segment only)** | ~none | low |
| timing (period-end) | none | **high** | low |
| timing (off-hours) | none | **high** | moderate |
| extreme_outlier | none | ~none | **very high** |

If Stage 7's measured matrix diverges wildly from this design, that is a finding worth
writing about — not a failure to hide. Discuss it in the README.

## 3.5 Orchestration — `src/inject.py`

```python
ANOMALY_TYPES = ["duplicate", "threshold_avoidance", "round_number",
                 "digit_fabrication", "timing", "extreme_outlier"]

def plan_volumes(base_rows: int, rate: float, types: list[str]) -> dict[str, int]:
    """Even split with the remainder going to 'duplicate'. Returns {type: n}."""

def sample_plausible_time(rng, hour_hist: np.ndarray, minute_choices) -> tuple[int,int]:
    """Draw an (hour, minute) from the empirical hour histogram of the real data."""

def mint_invoice_numbers(existing: set[str], n: int, rng) -> list[str]:
    """Generate n unique 6-digit invoice strings not in `existing`, drawn from the
    numeric neighbourhood of the real range. Asserts uniqueness and no collision."""

def realise_amount(target: float, rng, qty_pool: np.ndarray,
                   tol: float) -> tuple[int, float, float]:
    """Find (quantity, price, amount) with amount ≈ target and
    amount == round(quantity*price, 2) exactly. Returns the triple."""

# ... the six inject_* functions per §3.3 ...

def assemble(base: pd.DataFrame, injected: list[pd.DataFrame],
             logs: list[pd.DataFrame], rng) -> tuple[pd.DataFrame, pd.DataFrame]:
    """1. assert every injected frame has identical columns & dtypes to base
       2. concat base + injected
       3. set is_synthetic_anomaly (0 for base, 1 for injected) and anomaly_type
          ('none' for base)
       4. SORT by (invoice_date, invoice, stock_code, quantity, price) — deterministic
       5. reset_index and assign txn_id = 'TXN-' + zero-padded 8-digit sequence
          **after** the sort, so IDs carry no injection signal
       6. join the logs to txn_id via temp_key, then DROP temp_key
       7. return (labeled_df, injection_log)"""

def run(force: bool = False, sample: bool = False) -> None: ...
```

### 3.5.1 `injected_anomalies.csv` schema (the ground truth)

| Column | Type | Notes |
|---|---|---|
| `txn_id` | str | joins to `transactions_labeled` |
| `anomaly_type` | str | one of the six |
| `anomaly_subtype` | str | e.g. `period_end`, `off_hours`, `near_round`, `triple`; else `""` |
| `source_txn_id` | str | for `duplicate`/`extreme_outlier`; else `""` |
| `sibling_group` | str | groups split-transaction siblings; else `""` |
| `params_json` | str | the per-type params dict, JSON-encoded |
| `injected_amount` | float | |
| `injected_datetime` | datetime | |
| `target_segment` | str | for `digit_fabrication`; `"Country|YYYY-MM"` |
| `seed` | int | 42 |
| `created_at` | datetime | run timestamp |

### 3.5.2 `transactions_labeled` schema additions

Everything from `cleaned.parquet`, plus:

| Column | Type |
|---|---|
| `txn_id` | str, unique, primary key |
| `is_synthetic_anomaly` | int8 (0/1) — **ground truth, never a feature** |
| `anomaly_type` | category — **ground truth, never a feature** |

Write **both** `.parquet` (canonical, used by the pipeline) and `.csv` (human-inspectable, git-ignored due to size — note the CSV will be ~250 MB; if that is unwieldy, write only a 100k-row sample CSV and log the decision).

## 3.6 Anti-tell checklist (the agent must verify each one)

| # | Tell | Verification |
|---|---|---|
| T1 | ID prefix reveals injection | IDs assigned after sort; assert `groupby(is_synthetic_anomaly).txn_id.apply(lambda s: s.str[4:6])` distributions are similar |
| T2 | Row order reveals injection | assert the index positions of injected rows are approximately uniform: KS test of injected positions vs Uniform(0,1) has p > 0.01 |
| T3 | `amount != quantity * price` | assert equality to 2 dp for **all** rows |
| T4 | Impossible decimal precision (e.g. price with 4 dp) | assert `price` and `amount` have ≤2 dp everywhere |
| T5 | Timestamps at exactly :00:00 seconds | ensure injected times carry the same second-granularity pattern as real data (this dataset's seconds are always 00 — so injected must also be 00; **verify empirically, don't assume**) |
| T6 | Invoice number collisions or out-of-range values | assert uniqueness and that injected invoice lengths match the real distribution |
| T7 | Novel `stock_code` / `country` / `description` values | assert every injected value already exists in the real population |
| T8 | Injected rows all from one date/customer | assert injected rows span ≥90% of the real date range and ≥100 distinct customers |
| T9 | A single raw feature separates classes | fit a 1-feature logistic model on each of `amount, quantity, price, hour, day_of_week` predicting the label; **no single feature may reach ROC-AUC > 0.80** (except by design for `extreme_outlier` — so run this test excluding that type) |
| T10 | Global separability too easy | fit `DecisionTreeClassifier(max_depth=3)` on the Stage-6 feature set; Average Precision must be **< 0.60**. If higher, the injection is too easy — increase jitter and log it. |

> T9/T10 are the difference between a project that looks rigorous and one that is.
> An AP of 0.98 does not mean the model is brilliant; it means the anomalies were
> planted badly. Say so in the README either way.

## 3.7 Required figures

| Figure | File |
|---|---|
| Injected count by type (bar) | `injection_by_type.png` |
| Amount distribution: real vs injected, log x, overlaid density | `injection_amount_overlay.png` |
| Hour distribution: real vs injected | `injection_hour_overlay.png` |
| Day-of-month distribution: real vs injected | `injection_dom_overlay.png` |
| Leading-digit distribution: real vs injected vs Benford expected | `injection_leading_digit.png` |
| Injected-row position within the sorted frame (uniformity check) | `injection_position_uniformity.png` |

The amount-overlay figure is the honesty check: the two densities should look broadly similar with the expected local bumps. If the injected density is a set of isolated spikes, the injection is too crude.

## 3.8 Stage 3 Gate — `checks/gate_03.py`

1. `transactions_labeled.parquet` exists; `len == base_rows + n_inject_total` exactly.
2. `txn_id` unique, non-null, matches `^TXN-\d{8}$`.
3. `is_synthetic_anomaly` sums to `n_inject_total`; rate within 0.001 of the planned rate.
4. `injected_anomalies.csv` row count == `n_inject_total`; every `txn_id` in it exists in the labeled frame; `anomaly_type` value counts match the volume plan.
5. Schema equality: the labeled frame has exactly `cleaned` columns + 3.
6. Anti-tell checks T1–T10 all pass (each asserted, each result printed).
7. Determinism: `assert_deterministic` — re-run injection with the same seed and assert the SHA-256 of the sorted output frame is identical.
8. All six figures exist.
9. Every injected row has `amount == round(quantity*price, 2)`, `price` and `amount` ≤2 dp, `quantity >= 1`.
10. Every injected `country`, `stock_code`, `description` value exists in the real population.
11. `digit_fabrication` rows: observed leading-digit distribution matches the configured weights within ±3 percentage points.
12. `benford_target_segments` recorded in `injection_summary.json` and each has n ≥ 3,000 post-injection.

**Gate report must record:** the volume plan actually realised, the contamination matrix from §3.4, the results of every anti-tell check with its numeric value, the chosen Benford target segments, and the exact final anomaly rate to 4 dp.

**Commit:** `stage(03): synthetic anomaly injection, 6 archetypes, ground truth log, anti-tell verification`
`git tag stage-03-injection`

---

## 3.9 Common failure modes in this stage (pre-mortem)

| Symptom | Likely cause | Fix |
|---|---|---|
| Stage 7 AP ≈ 0.99 | Injection too crude — probably fabricated `amount` directly or used constants | Enforce `realise_amount`, add jitter, re-check T9/T10 |
| Stage 7 AP ≈ 0.02 | Injection too subtle, or a bug means labels don't align with rows | Check the `temp_key` → `txn_id` join in `assemble`; verify by sampling 10 injected rows and eyeballing |
| Benford segment test flags nothing | `digit_fabrication` rows spread too thinly across segments | Increase `segment concentration` from 60% to 80%, or pick smaller target segments |
| Rules catch `digit_fabrication` | Contamination-avoidance rejection not implemented | Add the reject-and-resample step in 3.3.4 step 4 |
| Duplicates not caught by `flag_duplicate` | Date jitter of ±1 day exceeds the rule's window, or amounts differ by rounding | Align `injection.duplicate.date_jitter_days` with `rules.duplicate_window_days` |
| Injection takes >10 minutes | Row-by-row `df.append` / `pd.concat` in a loop | Build lists of dicts, construct the frame once |
| dtype mismatch on concat | Categorical columns with different category sets | Cast injected frames' categoricals using `pd.Categorical(values, categories=base[col].cat.categories)` |

---

**END OF STAGES 0–3 — proceed to `02_STAGES_4-6.md`**
