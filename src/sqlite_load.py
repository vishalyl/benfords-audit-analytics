"""Stage 1 — mirror the raw combined frame into SQLite and run the showcase queries."""
from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

import pandas as pd

from src.config import cfg
from src.logging_setup import setup_logging, timed

logger = logging.getLogger("audit.sqlite_load")


def create_schema(conn: sqlite3.Connection) -> None:
    schema_sql = (Path(__file__).resolve().parents[1] / "sql/schema.sql").read_text()
    conn.executescript(schema_sql)


def load_transactions(df: pd.DataFrame, conn: sqlite3.Connection,
                       table: str = "transactions_raw", chunksize: int = 50_000) -> int:
    out = df.copy()
    out["invoice_date"] = out["invoice_date"].astype(str)
    out["customer_id"] = out["customer_id"].astype(str)
    cols = ["line_no", "invoice", "stock_code", "description", "quantity",
            "invoice_date", "price", "customer_id", "country", "source_sheet", "amount"]
    out[cols].to_sql(table, conn, if_exists="append", index=False, method="multi", chunksize=2000)
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert n == len(df), f"SQLite write mismatch: wrote table has {n} rows, expected {len(df)}"
    return n


def create_indexes(conn: sqlite3.Connection) -> None:
    # Indexes are created by schema.sql already; this is a no-op kept for API symmetry
    # in case create_schema is skipped on a pre-existing DB.
    idx_sql = [
        "CREATE INDEX IF NOT EXISTS idx_tr_customer ON transactions_raw(customer_id)",
        "CREATE INDEX IF NOT EXISTS idx_tr_country  ON transactions_raw(country)",
        "CREATE INDEX IF NOT EXISTS idx_tr_date     ON transactions_raw(invoice_date)",
        "CREATE INDEX IF NOT EXISTS idx_tr_invoice  ON transactions_raw(invoice)",
        "CREATE INDEX IF NOT EXISTS idx_tr_amount   ON transactions_raw(amount)",
    ]
    for stmt in idx_sql:
        conn.execute(stmt)
    conn.commit()


def verify(conn: sqlite3.Connection, expected_rows: int) -> dict:
    count = conn.execute("SELECT COUNT(*) FROM transactions_raw").fetchone()[0]
    distinct_invoices = conn.execute("SELECT COUNT(DISTINCT invoice) FROM transactions_raw").fetchone()[0]
    date_min, date_max = conn.execute("SELECT MIN(invoice_date), MAX(invoice_date) FROM transactions_raw").fetchone()
    assert count == expected_rows, f"SQLite row count {count} != expected {expected_rows}"
    return {"count": count, "distinct_invoices": distinct_invoices, "date_min": date_min, "date_max": date_max}


def run_queries(conn: sqlite3.Connection, metrics_dir: Path) -> dict[str, pd.DataFrame]:
    sql_text = (Path(__file__).resolve().parents[1] / "sql/queries.sql").read_text()
    # Build statements by accumulating non-comment lines, splitting on ;-terminated lines.
    statements = []
    current_lines: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue  # skip comment-only lines entirely
        current_lines.append(line)
        if stripped.endswith(";"):
            statements.append("\n".join(current_lines).strip())
            current_lines = []
    results = {}
    metrics_dir.mkdir(parents=True, exist_ok=True)
    for i, stmt in enumerate(statements, start=1):
        df = pd.read_sql_query(stmt, conn)
        results[f"q{i}"] = df
        df.head(200).to_csv(metrics_dir / f"sql_q{i}.csv", index=False)
        logger.info("Query q%d returned %d rows", i, len(df))
    return results


def run(force: bool = False, sample: bool = False) -> None:
    logger = setup_logging("sqlite_load")
    interim_dir = cfg.paths.interim_dir
    src_path = interim_dir / ("sample_50k.parquet" if sample else "raw_combined.parquet")
    db_path = cfg.paths.db_path

    with timed(logger, "stage1_sqlite"):
        df = pd.read_parquet(src_path)
        if db_path.exists() and force:
            db_path.unlink()
        conn = sqlite3.connect(db_path)
        try:
            create_schema(conn)
            load_transactions(df, conn)
            create_indexes(conn)
            info = verify(conn, len(df))
            logger.info("SQLite verify: %s", info)
            run_queries(conn, cfg.paths.metrics_dir)
        finally:
            conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    run(force=args.force, sample=args.sample)
