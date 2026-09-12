"""Stage 2 — cleaning with a full reconciliation ledger. No row disappears unexplained."""
from __future__ import annotations

import argparse
import logging
import re

import numpy as np
import pandas as pd

from src.config import cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed
from src.viz import PALETTE, save_fig
import matplotlib.pyplot as plt

logger = logging.getLogger("audit.clean")

_COUNTRY_FIXES = {
    "EIRE": "Eire",
    "RSA": "RSA",
    "Unspecified": "Unspecified",
    "European Community": "European Community",
}


def normalise_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["invoice"] = df["invoice"].astype(str).str.strip().str.upper()
    df["stock_code"] = df["stock_code"].astype(str).str.strip().str.upper()

    cust = df["customer_id"]
    cust_str = pd.Series(np.where(cust.isna(), cfg.cleaning.unassigned_customer_label,
                                   cust.astype("Int64").astype(str)), index=df.index)
    df["customer_id"] = cust_str

    df["description"] = df["description"].astype(str).str.strip()
    df.loc[df["description"].isin(["nan", "None", ""]), "description"] = "(no description)"

    country = df["country"].astype(str).str.strip()
    title_cased = country.str.title()
    for raw, fixed in _COUNTRY_FIXES.items():
        title_cased = title_cased.mask(country.str.upper() == raw.upper(), fixed)
    df["country"] = title_cased

    df["invoice_date"] = pd.to_datetime(df["invoice_date"], errors="raise")
    return df


def flag_cancellations(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    is_cancel = df["invoice"].str.startswith(cfg.cleaning.cancellation_prefix)
    cancellations = df[is_cancel].copy()
    main = df[~is_cancel].copy()
    pct_neg = (cancellations["quantity"] < 0).mean() if len(cancellations) else float("nan")
    logger.info("Cancellations: %d rows (%.3f%% of input), total value %.2f, %.1f%% negative qty",
                len(cancellations), 100 * is_cancel.mean(),
                (cancellations["quantity"] * cancellations["price"]).sum() if len(cancellations) else 0,
                100 * pct_neg if pd.notna(pct_neg) else float("nan"))
    return main, cancellations


def flag_adjustments(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    codes = set(cfg.cleaning.nonproduct_stock_codes)
    regex = re.compile(cfg.cleaning.nonproduct_regex)
    is_adj = df["stock_code"].isin(codes) | df["stock_code"].str.match(regex)
    df["is_adjustment"] = is_adj
    top20 = df.loc[is_adj, "stock_code"].value_counts().head(20)
    logger.info("Adjustments: %d rows (%.3f%%). Top 20 codes:\n%s",
                int(is_adj.sum()), 100 * is_adj.mean(), top20.to_string())
    return df


def compute_amount(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["amount"] = (df["quantity"].astype("float64") * df["price"].astype("float64")).round(2)
    df["is_nonpositive_amount"] = df["amount"] <= 0
    return df


def derive_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    dt = df["invoice_date"]
    df["year"] = dt.dt.year.astype("int16")
    df["month"] = dt.dt.month.astype("int8")
    df["year_month"] = dt.dt.strftime("%Y-%m")
    df["quarter"] = dt.dt.year.astype(str) + "Q" + dt.dt.quarter.astype(str)
    df["day"] = dt.dt.day.astype("int8")
    df["day_of_week"] = dt.dt.dayofweek.astype("int8")
    df["day_name"] = dt.dt.day_name().astype("category")
    df["hour"] = dt.dt.hour.astype("int8")
    df["minute"] = dt.dt.minute.astype("int8")

    month_end_days = cfg.cleaning.month_end_days
    days_in_month = dt.dt.days_in_month
    df["days_to_month_end"] = (days_in_month - dt.dt.day).astype("int8")
    df["is_month_end"] = (df["days_to_month_end"] < month_end_days)
    quarter_month = dt.dt.month % 3 == 0
    df["is_quarter_end"] = df["is_month_end"] & quarter_month
    df["date"] = dt.dt.date
    return df


def drop_exact_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    key_cols = ["invoice", "stock_code", "quantity", "invoice_date", "price", "customer_id", "country"]
    dup_mask = df.duplicated(subset=key_cols, keep="first")
    n_dropped = int(dup_mask.sum())
    if n_dropped:
        examples = df[dup_mask].head(3)[key_cols]
        logger.info("Dropping %d exact duplicate rows. Examples:\n%s", n_dropped, examples.to_string())
    return df[~dup_mask].copy(), n_dropped


def add_customer_stats(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    unassigned = cfg.cleaning.unassigned_customer_label
    positive = df[(df["amount"] > 0) & (df["customer_id"] != unassigned)]

    def _mad(s: pd.Series) -> float:
        return float((s - s.median()).abs().median())

    grp = positive.groupby("customer_id")["amount"]
    stats = grp.agg(cust_txn_count="count", cust_amount_mean="mean",
                     cust_amount_std="std", cust_amount_median="median")
    stats["cust_amount_mad"] = positive.groupby("customer_id")["amount"].apply(_mad)
    qty_grp = positive.groupby("customer_id")["quantity"]
    stats["cust_qty_mean"] = qty_grp.mean()
    stats["cust_qty_std"] = qty_grp.std()
    stats = stats.reset_index()

    df = df.merge(stats, on="customer_id", how="left")
    df["has_customer_stats"] = (df["customer_id"] != unassigned) & (df["cust_txn_count"].fillna(0) >= 5)
    stat_cols = ["cust_txn_count", "cust_amount_mean", "cust_amount_std",
                 "cust_amount_median", "cust_amount_mad", "cust_qty_mean", "cust_qty_std"]
    for c in stat_cols:
        df.loc[~df["has_customer_stats"], c] = np.nan
    return df


def build_cleaning_ledger(counts: dict) -> dict:
    rows_in = counts["rows_in"]
    rows_out = counts["rows_out"]
    cancellations = counts["cancellations"]
    exact_duplicates = counts["exact_duplicates"]
    reconciled = rows_out + cancellations + exact_duplicates
    assert rows_in == reconciled, (
        f"Cleaning ledger does not reconcile: rows_in={rows_in} != "
        f"rows_out({rows_out}) + cancellations({cancellations}) + "
        f"exact_duplicates({exact_duplicates}) = {reconciled}"
    )
    counts["reconciles"] = True
    return counts


def make_diagnostic_figures(df_full: pd.DataFrame, figures_dir) -> dict:
    findings = {}

    fig, ax = plt.subplots()
    hour_counts = df_full["hour"].value_counts().reindex(range(24), fill_value=0)
    ax.bar(hour_counts.index, hour_counts.values, color=PALETTE["primary"])
    ax.set_xlabel("Hour of day (24h)")
    ax.set_ylabel("Transaction count")
    pct_outside_7_20 = 100 * (~df_full["hour"].between(7, 19)).mean()
    ax.set_title(f"Activity concentrates 07:00-20:00 UK time ({pct_outside_7_20:.2f}% of rows fall outside)")
    save_fig(fig, "hour_distribution.png", "cleaning")
    findings["pct_outside_business_hours_07_20"] = round(pct_outside_7_20, 4)

    fig, ax = plt.subplots()
    dow_counts = df_full["day_name"].value_counts().reindex(
        ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], fill_value=0)
    colors = [PALETTE["primary"]] * 6 + [PALETTE["warning"]]
    ax.bar(dow_counts.index, dow_counts.values, color=colors)
    ax.set_ylabel("Transaction count")
    sunday_share = 100 * dow_counts["Sunday"] / dow_counts.sum()
    ax.set_title(f"Sunday carries {sunday_share:.2f}% of volume — a live trading day in this dataset")
    plt.xticks(rotation=30)
    save_fig(fig, "dow_distribution.png", "cleaning")
    findings["sunday_pct_share"] = round(float(sunday_share), 4)

    fig, ax = plt.subplots()
    pos_amount = df_full.loc[df_full["amount"] > 0, "amount"]
    ax.hist(np.log10(pos_amount), bins=80, color=PALETTE["secondary"])
    ax.set_xlabel("log10(amount), GBP")
    ax.set_ylabel("Count")
    ax.set_title("Amount distribution is heavy-tailed — justifies log1p transform downstream")
    save_fig(fig, "amount_distribution.png", "cleaning")

    fig, ax = plt.subplots()
    monthly = df_full.groupby("year_month").size()
    ax.plot(monthly.index, monthly.values, color=PALETTE["primary"], marker="o", markersize=3)
    ax.set_ylabel("Transaction count")
    ax.set_title("Monthly transaction volume, Dec 2009 - Dec 2011")
    plt.xticks(rotation=60, fontsize=7)
    save_fig(fig, "monthly_volume.png", "cleaning")

    return findings


def run(force: bool = False, sample: bool = False) -> None:
    logger = setup_logging("clean")
    interim_dir = cfg.paths.interim_dir
    src_path = interim_dir / ("sample_50k.parquet" if sample else "raw_combined.parquet")
    out_path = interim_dir / ("cleaned_sample.parquet" if sample else "cleaned.parquet")
    cancel_path = interim_dir / ("cancellations_sample.parquet" if sample else "cancellations.parquet")

    if out_path.exists() and not force:
        logger.info("%s exists, skipping (use --force to rerun).", out_path)
        return

    with timed(logger, "stage2_clean"):
        df = pd.read_parquet(src_path)
        rows_in = len(df)

        df = normalise_types(df)
        main, cancellations = flag_cancellations(df)
        main, n_dup = drop_exact_duplicates(main)
        main = flag_adjustments(main)
        main = compute_amount(main)
        main = derive_time_features(main)
        main = add_customer_stats(main)

        rows_out = len(main)
        ledger = build_cleaning_ledger({
            "rows_in": rows_in,
            "rows_out": rows_out,
            "cancellations": len(cancellations),
            "exact_duplicates": n_dup,
            "missing_customer": int((df["customer_id"] == cfg.cleaning.unassigned_customer_label).sum()),
            "adjustments": int(main["is_adjustment"].sum()),
            "nonpositive_amount": int(main["is_nonpositive_amount"].sum()),
        })
        logger.info("Cleaning ledger: %s", ledger)

        diag = make_diagnostic_figures(main, cfg.paths.figures_dir)
        ledger.update(diag)

        n_countries = main["country"].nunique()
        small_countries = main["country"].value_counts()
        small_countries = small_countries[small_countries < 1000]
        ledger["n_countries"] = int(n_countries)
        ledger["n_countries_below_segment_min"] = int(len(small_countries))
        ledger["date_min"] = str(main["invoice_date"].min())
        ledger["date_max"] = str(main["invoice_date"].max())
        zero_price_pos_qty = int(((main["price"] == 0) & (main["quantity"] > 0)).sum())
        ledger["zero_price_positive_qty_count"] = zero_price_pos_qty

        # Cleaning waterfall figure
        fig, ax = plt.subplots()
        stages_labels = ["Raw", "-Cancellations", "-Exact dup.", "Cleaned"]
        values = [rows_in, rows_in - len(cancellations), rows_in - len(cancellations) - n_dup, rows_out]
        ax.bar(stages_labels, values, color=[PALETTE["neutral"], PALETTE["warning"], PALETTE["warning"], PALETTE["good"]])
        ax.set_ylabel("Row count")
        ax.set_title(f"Cleaning waterfall: {rows_in:,} raw rows -> {rows_out:,} in the analysis population")
        save_fig(fig, "cleaning_waterfall.png", "cleaning")

        write_json(cfg.paths.metrics_dir / "cleaning_ledger.json", ledger)

        main.to_parquet(out_path, index=False)
        cancellations.to_parquet(cancel_path, index=False)
        logger.info("Wrote %s (%d rows), %s (%d rows)", out_path, len(main), cancel_path, len(cancellations))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    run(force=args.force, sample=args.sample)
