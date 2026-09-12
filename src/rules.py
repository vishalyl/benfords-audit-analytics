"""Stage 5 — Rule-based red flag detection for the fraud detection pipeline.

Loads ``data/processed/transactions_labeled.parquet`` and applies 10
heuristic rules to each row.  The result is written out with a new
``rule_flags`` column (``list[str]``) so every transaction carries the
names of every rule it triggered.

Usage::

    python -m src.rules [--sample] [--force]

All rules operate on raw data features only — ``is_synthetic_anomaly``
and ``anomaly_type`` are never consulted during flagging.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.config import cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed
from src.viz import PALETTE, FIGSIZE, DPI, save_fig, setup_style

logger = logging.getLogger("audit.rules")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INPUT_PATH = cfg.paths.processed_dir / "transactions_labeled.parquet"
OUTPUT_PATH = cfg.paths.processed_dir / "transactions_flagged.parquet"

# Colours used in figures
COLOR_REAL = "#4A90D9"
COLOR_FLAGGED = "#D94A4A"


# ---------------------------------------------------------------------------
# Individual rule functions
# ---------------------------------------------------------------------------

def _rule_round_number(df: pd.DataFrame) -> pd.Series:
    """ROUND_NUMBER: amount is an exact integer (no cents)."""
    mask = df["amount"].notna() & (df["amount"].round(2) == df["amount"].astype(int))
    return mask


def _rule_negative_adjustment(df: pd.DataFrame) -> pd.Series:
    """NEGATIVE_ADJUSTMENT: amount < 0 (return / credit note)."""
    return df["amount"].notna() & (df["amount"] < 0)


def _rule_large_amount(df: pd.DataFrame) -> pd.Series:
    """LARGE_AMOUNT: amount exceeds the 99th percentile of all amounts.

    NOTE: The plan says "99th percentile of real data amounts" but the rules
    must NOT use is_synthetic_anomaly for flagging.  We therefore compute
    the p99 over the entire dataset (all rows) to stay within the constraint.
    """
    p99 = df["amount"].quantile(0.99)
    return df["amount"].notna() & (df["amount"] > p99)


def _rule_zero_quantity(df: pd.DataFrame) -> pd.Series:
    """ZERO_QUANTITY: quantity == 0 with non-zero unit_price."""
    return (df["quantity"] == 0) & (df["price"] != 0)


def _rule_odd_quantity(df: pd.DataFrame) -> pd.Series:
    """ODD_QUANTITY: fractional quantity (e.g. 1.5 items)."""
    return (df["quantity"].notna()) & (df["quantity"] % 1 != 0)


def _rule_duplicate_invoice(df: pd.DataFrame) -> pd.Series:
    """DUPLICATE_INVOICE: same (invoice, customer_id, invoice_date, stock_code)
    appearing more than once."""
    dup_key = df.groupby(
        ["invoice", "customer_id", "invoice_date", "stock_code"],
    ).transform("size")
    return dup_key > 1


def _rule_round_dollars(df: pd.DataFrame) -> pd.Series:
    """ROUND_DOLLARS: amount is a multiple of 10, 50, or 100."""
    amt = df["amount"]
    mask = amt.notna()
    is_10 = (amt % 10 == 0)
    is_50 = (amt % 50 == 0)
    is_100 = (amt % 100 == 0)
    return mask & (is_10 | is_50 | is_100)


def _rule_high_quantity(df: pd.DataFrame) -> pd.Series:
    """HIGH_QUANTITY: quantity > 3 * cust_amount_std + cust_amount_mean.

    Only rows where cust_amount_std is present and > 0 participate.
    """
    valid = (df["cust_amount_std"].notna()) & (df["cust_amount_std"] > 0)
    result = pd.Series(False, index=df.index)
    subset = df.loc[valid]
    result.loc[subset.index] = (
        subset["quantity"] > 3 * subset["cust_amount_std"] + subset["cust_amount_mean"]
    )
    return result


def _rule_off_hour(df: pd.DataFrame) -> pd.Series:
    """OFF_HOUR: transactions in hours 0-5 AM (midnight to dawn)."""
    return (df["hour"].notna()) & (df["hour"] >= 0) & (df["hour"] <= 5)


def _rule_split_amount(df: pd.DataFrame) -> pd.Series:
    """SPLIT_AMOUNT: amount just below round thresholds
    (e.g. 49.99, 99.99, 199.99).

    We flag amounts where the value modulo 100 is >= 40 and > 0,
    meaning it sits in the upper band below a round hundred.
    """
    amt = df["amount"]
    mask = amt.notna() & (amt > 0)
    remainder = amt % 100
    return mask & (remainder >= 40)


# Map rule name -> function
RULES: list[tuple[str, Any]] = [
    ("ROUND_NUMBER", _rule_round_number),
    ("NEGATIVE_ADJUSTMENT", _rule_negative_adjustment),
    ("LARGE_AMOUNT", _rule_large_amount),
    ("ZERO_QUANTITY", _rule_zero_quantity),
    ("ODD_QUANTITY", _rule_odd_quantity),
    ("DUPLICATE_INVOICE", _rule_duplicate_invoice),
    ("ROUND_DOLLARS", _rule_round_dollars),
    ("HIGH_QUANTITY", _rule_high_quantity),
    ("OFF_HOUR", _rule_off_hour),
    ("SPLIT_AMOUNT", _rule_split_amount),
]


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def apply_rules(df: pd.DataFrame) -> pd.DataFrame:
    """Apply every rule and attach ``rule_flags`` (list[str]) to ``df``.

    Returns a *copy* of the input DataFrame so the original is untouched.
    """
    out = df.copy()
    out["rule_flags"] = [[] for _ in range(len(out))]

    for rule_name, rule_fn in RULES:
        mask = rule_fn(out)
        n = int(mask.sum())
        if n > 0:
            # Set flags only for rows that match; use .loc for safety.
            # We need a column we can mutate that holds list objects.
            existing = out.loc[mask, "rule_flags"]
            out.loc[mask, "rule_flags"] = existing.apply(
                lambda fl: fl + [rule_name]
            )
        logger.info(
            "%-20s flagged %6d / %d rows",
            rule_name, n, len(out),
        )

    return out


def build_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Build a JSON-serialisable summary dict from the flagged DataFrame."""
    flag_series = df["rule_flags"]
    total = len(df)
    flagged_mask = flag_series.apply(len) > 0
    n_flagged = int(flagged_mask.sum())
    n_clean = total - n_flagged

    rule_counts: dict[str, int] = {}
    for rule_name, rule_fn in RULES:
        mask = rule_fn(df)
        rule_counts[rule_name] = int(mask.sum())

    # Overlap: how many rows trigger more than one rule
    multi = flag_series.apply(len)
    overlap_stats = {
        "exactly_1": int((multi == 1).sum()),
        "exactly_2": int((multi == 2).sum()),
        "exactly_3": int((multi == 3).sum()),
        "4_or_more": int((multi >= 4).sum()),
    }

    return {
        "total_rows": total,
        "n_flagged": n_flagged,
        "n_clean": n_clean,
        "flagged_pct": round(100 * n_flagged / max(total, 1), 2),
        "rule_counts": rule_counts,
        "overlap_stats": overlap_stats,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _rule_distribution_plot(df: pd.DataFrame) -> plt.Figure:
    """Horizontal bar chart of per-rule flag counts."""
    fig, ax = plt.subplots(figsize=(10, 6))
    counts = []
    for rule_name, rule_fn in RULES:
        counts.append(rule_fn(df).sum())

    # Sort ascending for a nice left-to-right bar chart
    labels = [r[0] for r in RULES]
    counts_arr = np.array(counts)
    order = np.argsort(counts_arr)

    ax.barh(
        [labels[i] for i in order],
        counts_arr[order],
        color=COLOR_FLAGGED,
    )
    ax.set_xlabel("Number of flagged rows")
    ax.set_title("Rule-based red flag distribution")
    ax.tick_params(axis="y", labelsize=10)
    return fig


def _rule_time_series_plot(df: pd.DataFrame) -> plt.Figure:
    """Monthly stacked bar chart of flag counts split by real vs flagged."""
    # Work on a subset for speed in large datasets
    sample = cfg.ingest.sample_size
    if len(df) > sample:
        df_plot = df.sample(n=sample, random_state=cfg.project.seed)
    else:
        df_plot = df.copy()

    df_plot["flagged"] = df_plot["rule_flags"].apply(len) > 0

    fig, ax = plt.subplots(figsize=(12, 5))

    # Group by year_month and count totals and flagged counts
    total_counts = df_plot.groupby("year_month", observed=True).size()
    flagged_counts = df_plot[df_plot["flagged"]].groupby(
        "year_month", observed=True
    ).size()
    clean_counts = total_counts - flagged_counts.reindex(
        total_counts.index, fill_value=0
    )

    ax.bar(
        total_counts.index,
        clean_counts.values,
        width=0.7,
        color=COLOR_REAL,
        label="Clean",
    )
    ax.bar(
        total_counts.index,
        flagged_counts.reindex(total_counts.index, fill_value=0).values,
        width=0.7,
        color=COLOR_FLAGGED,
        bottom=clean_counts.values,
        label="Flagged",
    )
    ax.set_xlabel("Year-Month")
    ax.set_ylabel("Transaction count")
    ax.set_title("Flagged transactions over time")
    ax.legend(loc="upper left")
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    return fig


def save_figures(df: pd.DataFrame) -> None:
    """Generate and persist the two rule figures."""
    setup_style()
    fig1 = _rule_distribution_plot(df)
    save_fig(fig1, "rule_distribution.png", category="rules")
    logger.info("Saved rule_distribution.png")

    fig2 = _rule_time_series_plot(df)
    save_fig(fig2, "rule_time_series.png", category="rules")
    logger.info("Saved rule_time_series.png")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(force: bool = False, sample: bool = False) -> None:
    """Stage 5 entry point — rule-based flagging pipeline."""
    logger = setup_logging("rules")

    with timed(logger, "stage5_rules"):
        # --- Load data ---
        if INPUT_PATH.exists() and not force:
            logger.info("Loading existing %s", INPUT_PATH)
            df = pd.read_parquet(INPUT_PATH)
        else:
            logger.error("Input file %s not found. Run stages 0-4 first.", INPUT_PATH)
            raise FileNotFoundError(INPUT_PATH)

        if sample:
            n = cfg.ingest.sample_size
            logger.info("Using %d-row sample", n)
            df = df.sample(n=min(n, len(df)), random_state=cfg.project.seed)

        # --- Apply rules ---
        df_flagged = apply_rules(df)

        # --- Build summary ---
        summary = build_summary(df_flagged)

        # --- Persist outputs ---
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        df_flagged.to_parquet(OUTPUT_PATH, index=False)
        logger.info("Wrote %s (%d rows, %d with flags)",
                     OUTPUT_PATH, len(df_flagged), summary["n_flagged"])

        metrics_dir = cfg.paths.metrics_dir
        metrics_dir.mkdir(parents=True, exist_ok=True)
        write_json(metrics_dir / "rule_summary.json", summary)
        logger.info("Wrote reports/metrics/rule_summary.json")

        # --- Figures ---
        save_figures(df_flagged)

        # --- Final log ---
        logger.info(
            "Summary: total=%d flagged=%d (%.1f%%) rules=%s",
            summary["total_rows"],
            summary["n_flagged"],
            summary["flagged_pct"],
            summary["rule_counts"],
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stage 5: Rule-based red flag detection",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if output already exists",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Run on a sample for quick iteration",
    )
    args = parser.parse_args()
    run(force=args.force, sample=args.sample)
