"""Stage 2 gate — Cleaning with full reconciliation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from checks.common import (
    assert_cols,
    assert_file_exists,
    assert_no_nulls,
    report,
)
from src.config import cfg
from src.io_utils import read_json

import logging
logger = logging.getLogger("audit.gate_02")
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")


def main() -> int:
    failures: list[str] = []
    lines: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        lines.append(f"[{status}] {label} {detail}".rstrip())
        if not cond:
            failures.append(label)

    # 1. cleaned.parquet exists
    cleaned_path = cfg.paths.interim_dir / "cleaned.parquet"
    assert_file_exists(str(cleaned_path))
    df = pd.read_parquet(cleaned_path)

    # 2. Cancellations parquet exists
    cancel_path = cfg.paths.interim_dir / "cancellations.parquet"
    assert_file_exists(str(cancel_path))
    cancels = pd.read_parquet(cancel_path)

    # 3. Check columns
    required_clean = {
        "invoice", "stock_code", "description", "quantity",
        "invoice_date", "price", "customer_id", "country",
        "amount", "is_adjustment", "is_nonpositive_amount",
        "year", "month", "year_month", "quarter", "day",
        "day_of_week", "day_name", "hour", "minute",
        "days_to_month_end", "is_month_end", "is_quarter_end", "date",
    }
    assert_cols(df, required_clean)
    check("all cleaning columns present", required_clean.issubset(set(df.columns)))

    # 4. Ledger reconciles
    ledger = read_json(cfg.paths.metrics_dir / "cleaning_ledger.json")
    rows_in = ledger["rows_in"]
    rows_out = ledger["rows_out"]
    cancellations = ledger["cancellations"]
    exact_dup = ledger["exact_duplicates"]
    reconciles = rows_in == rows_out + cancellations + exact_dup
    check(
        f"ledger reconciles: {rows_in} = {rows_out} + {cancellations} + {exact_dup}",
        reconciles,
        f"rows_in={rows_in}, rows_out={rows_out}, cancels={cancellations}, dups={exact_dup}",
    )
    # Also check actual parquet row counts match ledger
    check(f"cleaned.parquet row count matches ledger ({len(df):,} == {rows_out:,})",
          len(df) == rows_out, f"parquet={len(df)}, ledger={rows_out}")
    check(f"cancellations.parquet row count ({len(cancels):,} == {cancellations:,})",
          len(cancels) == cancellations)

    # 5. No nulls in critical columns
    assert_no_nulls(df, ["invoice", "stock_code", "invoice_date", "amount"])
    check("no nulls in invoice/stock_code/invoice_date/amount", True)

    # 6. Amount column checks
    pos_amounts = df.loc[df["amount"] > 0, "amount"]
    check("amount has positive values", len(pos_amounts) > 0, f"pos={len(pos_amounts):,}")
    check("amount has negative values (returns)",
          int((df["amount"] < 0).any()), f"neg count={(df['amount'] < 0).sum()}")

    # 7. Time features
    check("year_month column populated", df["year_month"].notna().all(),
          f"nulls={df['year_month'].isna().sum()}")
    check("hour column populated", df["hour"].notna().all(),
          f"nulls={df['hour'].isna().sum()}")

    # 8. Figures exist
    figs = ["hour_distribution.png", "amount_distribution.png",
            "monthly_volume.png", "dow_distribution.png", "cleaning_waterfall.png"]
    for fig in figs:
        p = cfg.paths.figures_dir / fig
        assert_file_exists(str(p))
        check(f"figure exists: {fig}", True, f"size={p.stat().st_size:,} bytes")

    # 9. Customer stats
    has_stats = df["cust_txn_count"].notna().sum()
    check("customer stats computed for some customers", has_stats > 0,
          f"rows with stats={has_stats:,}")

    # 10. Cancellation prefix check
    canc_invoice_prefix = cancels["invoice"].astype(str).str.startswith("C")
    check("all cancellations have C-prefix invoices", canc_invoice_prefix.all(),
          f"non-C cancellations={(~cancels['invoice'].astype(str).str.startswith('C')).sum()}")

    # Build report
    report_path = REPO_ROOT / "reports/gate_reports/gate_02.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    md = []
    md.append("# Stage 2 Gate Report — Cleaning\n\n")
    md.append(f"Rows in: {rows_in:,}\n")
    md.append(f"Rows out (cleaned): {rows_out:,}\n")
    md.append(f"Cancellations removed: {cancellations:,}\n")
    md.append(f"Exact duplicates removed: {exact_dup:,}\n")
    md.append(f"Adjustments flagged: {ledger['adjustments']:,}\n")
    md.append(f"Non-positive amounts: {ledger['nonpositive_amount']:,}\n")
    md.append(f"Missing customer IDs (UNASSIGNED): {ledger['missing_customer']:,}\n")
    md.append(f"Date range: {ledger['date_min']} to {ledger['date_max']}\n")
    md.append(f"N countries: {ledger['n_countries']}\n")
    md.append(f"Sunday share: {ledger['sunday_pct_share']:.2f}%\n")
    md.append(f"% rows outside 07:00-20:00: {ledger['pct_outside_business_hours_07_20']:.2f}%\n")
    md.append(f"\n## Checks\n\n```\n" + "\n".join(lines) + "\n```\n\n")
    md.append(f"## GATE: {'PASS' if not failures else 'FAIL'}\n")
    report_path.write_text("".join(md), encoding="utf-8")

    print("\n".join(lines))
    print(f"\nGATE: {'PASS' if not failures else 'FAIL'}")
    if failures:
        print(f"\nFailed checks: {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
