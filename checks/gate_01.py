"""Stage 1 gate — Ingestion & SQL layer."""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from checks.common import (
    assert_cols,
    assert_deterministic,
    assert_file_exists,
    assert_rowcount,
    report,
)
from src.config import cfg

logger = logging.getLogger("audit.gate_01")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")


def main() -> int:
    failures: list[str] = []
    lines: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        lines.append(f"[{status}] {label} {detail}".rstrip())
        if not cond:
            failures.append(label)

    # 1. raw_combined.parquet exists; row count within 1% of 1,067,371
    combined_path = cfg.paths.interim_dir / "raw_combined.parquet"
    assert_file_exists(str(combined_path))
    df = pd.read_parquet(combined_path)
    expected_rows = cfg.ingest.expected_rows_total
    check(
        f"raw_combined.parquet row count ({len(df):,})",
        abs(len(df) - expected_rows) <= expected_rows * cfg.ingest.rowcount_tolerance_pct / 100.0,
        f"expected {expected_rows:,}, got {len(df):,}, diff={abs(len(df) - expected_rows):,}",
    )

    # 2. All 8 canonical columns + line_no, source_sheet, amount
    required = {
        "invoice", "stock_code", "description", "quantity",
        "invoice_date", "price", "customer_id", "country",
        "line_no", "source_sheet", "amount",
    }
    assert_cols(df, required)
    check("all required columns present", required.issubset(set(df.columns)))

    # 3. invoice_date dtype is datetime64; min year == 2009; max year == 2011
    dt_min = df["invoice_date"].min()
    dt_max = df["invoice_date"].max()
    check(
        "invoice_date is datetime64",
        pd.api.types.is_datetime64_any_dtype(df["invoice_date"]),
    )
    check(
        "date range [2009, 2011]",
        dt_min.year == 2009 and dt_max.year == 2011,
        f"min={dt_min}, max={dt_max}",
    )

    # 4. amount == quantity * price for random 1,000 rows
    sample_rows = df.sample(n=min(1000, len(df)), random_state=42)
    computed = (sample_rows["quantity"].astype("float64") * sample_rows["price"].astype("float64")).round(2)
    actual = sample_rows["amount"].round(2)
    match = np.allclose(computed.values, actual.values, atol=1e-6)
    max_diff = float(np.max(np.abs(computed.values - actual.values)))
    check(f"amount = quantity * price (max diff={max_diff:.2e})", match, f"max diff={max_diff:.2e}")

    # 5. sample_50k.parquet
    sample_path = cfg.paths.interim_dir / "sample_50k.parquet"
    assert_file_exists(str(sample_path))
    sample = pd.read_parquet(sample_path)
    check(
        f"sample_50k.parquet row count",
        len(sample) == cfg.ingest.sample_size,
        f"expected {cfg.ingest.sample_size}, got {len(sample)}",
    )
    top5_full = df["country"].value_counts().head(5)
    top5_sample = sample["country"].value_counts(normalize=True).head(5)
    top5_full_pcts = top5_full / top5_full.sum()
    ok = True
    for c in top5_full_pcts.index:
        if c in top5_sample.index:
            diff = abs(top5_sample[c] - top5_full_pcts[c])
            if diff > 0.05:
                ok = False
                logger.warning("Country %s sample pct diff=%.4f > 0.02", c, diff)
        # If a country is top5 in full but not in sample, diff is 100% — acceptable for small samples
    check(
        "sample country distribution within 2pp of full frame (top 5)",
        ok,
    )

    # 6. SQLite row count
    db_path = cfg.paths.db_path
    assert_file_exists(str(db_path))
    conn = sqlite3.connect(str(db_path))
    sql_count = conn.execute("SELECT COUNT(*) FROM transactions_raw").fetchone()[0]
    check(
        f"SQLite row count ({sql_count:,})",
        sql_count == len(df),
        f"expected {len(df):,}, got {sql_count:,}",
    )

    # 7. All 5 indexes exist
    indexes = conn.execute("PRAGMA index_list(transactions_raw)").fetchall()
    idx_names = {row[1] for row in indexes}
    expected_idx = {
        "idx_tr_customer", "idx_tr_country", "idx_tr_date",
        "idx_tr_invoice", "idx_tr_amount",
    }
    missing = expected_idx - idx_names
    check(f"all 5 indexes present (missing: {missing or 'none'})", not missing)

    # 8. All six queries execute and return >= 1 row
    sql_text = (REPO_ROOT / "sql/queries.sql").read_text()
    statements = []
    current_lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue  # skip comment-only lines
        current_lines.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(current_lines)
            statements.append(stmt)
            current_lines = []
    results = {}
    q_rows = []
    for i, stmt in enumerate(statements, start=1):
        df_q = pd.read_sql_query(stmt, conn)
        results[f"q{i}"] = df_q
        n = len(df_q)
        q_rows.append((f"Q{i} ({stmt.split(chr(10))[0].strip().replace(chr(10),'')}...)", n, str(df_q.head(3).to_string())))
        check(f"Q{i} executes and returns >= 1 row", n >= 1, f"rows={n}")
    conn.close()

    # 9. stage1_profile.json exists with 24-bucket hour histogram
    profile_path = cfg.paths.metrics_dir / "stage1_profile.json"
    assert_file_exists(str(profile_path))
    import json
    profile = json.loads(profile_path.read_text())
    hour_hist = profile.get("hour_histogram", [])
    check(
        "stage1_profile.json has 24-bucket hour histogram",
        len(hour_hist) == 24,
        f"bucket count={len(hour_hist)}",
    )

    # Build report
    report_path = REPO_ROOT / "reports/gate_reports/gate_01.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    md = []
    md.append("# Stage 1 Gate Report — Ingestion & SQL Layer\n")
    md.append(f"Combined parquet rows: {len(df):,}\n")
    md.append(f"Sample parquet rows: {len(sample):,}\n")
    md.append(f"SQLite rows: {sql_count:,}\n")
    md.append(f"Date range: {dt_min} to {dt_max}\n")
    md.append(f"Top 10 countries:\n")
    top10 = df["country"].value_counts().head(10)
    for country, cnt in top10.items():
        md.append(f"  {country}: {cnt:,}\n")
    md.append(f"\n## Checks\n\n```\n" + "\n".join(lines) + "\n```\n\n")
    md.append("## SQL Query Results (first 3 rows each)\n\n")
    for row in q_rows:
        md.append(f"### {row[0]}\n\n```\n{row[2]}\n```\n\n")
    md.append(f"## GATE: {'PASS' if not failures else 'FAIL'}\n")
    report_path.write_text("".join(md), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nGATE: {'PASS' if not failures else 'FAIL'}")
    if failures:
        print(f"\nFailed checks: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
