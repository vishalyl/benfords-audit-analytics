"""Stage 8 (export half), dashboard data packs for Power BI and the web app.

Builds every file under ``data/dashboard/`` (committed, capped at 25 MB) plus
``data/processed/dashboard_export.parquet`` (git-ignored, full schema
including the ground-truth columns, legitimate here because this is an
*evaluation* artefact, never a model input; see plan sec 8.3).

Business/Benford aggregates (monthly_trend, segment_heatmap, benford_aggregate,
benford_by_segment_digit) and model/composite figures (dashboard_export,
top_risk lists, kpi_summary's AP/recall) both describe the full 1,030,804-row
cleaned population by default (Stage 6 no longer requires --sample; see
DECISIONS.md D-0007). If Stage 6 is ever re-run with --sample for quick
iteration, the two populations diverge and that is logged, not hidden.

Usage::

    python -m src.export
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.config import cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed

logger = logging.getLogger("audit.export")

FLAGGED_PATH = cfg.paths.processed_dir / "transactions_flagged.parquet"
DASHBOARD_DIR = cfg.paths.dashboard_dir
PROCESSED_DIR = cfg.paths.processed_dir

EXPECTED_DIGIT_PROP = {d: np.log10(1 + 1 / d) for d in range(1, 10)}


def leading_digit(amount: pd.Series) -> pd.Series:
    """First significant digit of |amount| (1-9); NaN where amount == 0."""
    a = amount.abs()
    out = pd.Series(np.nan, index=amount.index)
    valid = a > 0
    exponent = np.floor(np.log10(a[valid]))
    scaled = a[valid] / (10.0 ** exponent)
    out[valid] = np.floor(scaled).clip(1, 9)
    return out


def second_digit(amount: pd.Series) -> pd.Series:
    """Second significant digit of |amount| (0-9); NaN where fewer than 2 sig figs."""
    a = amount.abs()
    out = pd.Series(np.nan, index=amount.index)
    valid = a >= 10 ** np.floor(np.log10(a.replace(0, np.nan)))
    valid = a > 0
    exponent = np.floor(np.log10(a[valid]))
    scaled = a[valid] / (10.0 ** (exponent - 1))
    out[valid] = np.floor(scaled) % 10
    return out


# ===================================================================
# Benford aggregate (9-row digit table), data/dashboard/benford_aggregate.csv
# ===================================================================

def build_benford_aggregate(benford_metrics_path: Path) -> pd.DataFrame:
    """9-row digit, observed_count, observed_prop, expected_prop, abs_diff, z_stat.

    Reads the pre-computed observed/expected arrays for the ``amount_first``
    row of reports/metrics/benford_aggregate.csv (Stage 4 output) rather
    than recomputing from raw data, so this file can never drift from the
    number Stage 4 actually reported.
    """
    agg = pd.read_csv(benford_metrics_path)
    row = agg[agg["metric"] == "amount_first"].iloc[0]
    observed = json.loads(row["observed"].replace("'", '"')) if isinstance(row["observed"], str) else row["observed"]
    expected = json.loads(row["expected"].replace("'", '"')) if isinstance(row["expected"], str) else row["expected"]
    n = int(row["n"])

    records = []
    for digit, obs_p, exp_p in zip(range(1, 10), observed, expected):
        obs_count = round(obs_p * n)
        abs_diff = abs(obs_p - exp_p)
        se = np.sqrt(exp_p * (1 - exp_p) / n)
        z = (abs_diff - 1 / (2 * n)) / se if se > 0 else 0.0
        records.append({
            "digit": digit, "observed_count": int(obs_count),
            "observed_prop": round(obs_p, 6), "expected_prop": round(exp_p, 6),
            "abs_diff": round(abs_diff, 6), "z_stat": round(float(z), 4),
        })
    return pd.DataFrame(records)


# ===================================================================
# Benford segments (dashboard shape) + by-segment-digit expansion
# ===================================================================

def build_benford_segments(segments_csv: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reshape Stage 4's per-(country, year_month) table to the dashboard schema.

    Returns:
        (segments_df, by_segment_digit_df), segments_df has one row per
        segment with segment_dim/segment_value/n/mad/verdict/chi2/chi2_p/
        max_dev_digit/is_flagged; by_segment_digit_df expands each segment
        into 9 rows (one per leading digit) for redrawing the chart per
        segment without loading the full dataset.
    """
    bdf = pd.read_csv(segments_csv)
    bdf = bdf[bdf["metric"] == "amount_first"].copy()

    seg_rows, digit_rows = [], []
    for _, r in bdf.iterrows():
        observed = json.loads(r["observed"].replace("'", '"')) if isinstance(r["observed"], str) else r["observed"]
        expected = json.loads(r["expected"].replace("'", '"')) if isinstance(r["expected"], str) else r["expected"]
        seg_value = f"{r['country']}|{r['year_month']}"
        diffs = [abs(o - e) for o, e in zip(observed, expected)]
        max_dev_digit = int(np.argmax(diffs)) + 1

        seg_rows.append({
            "segment_dim": "country_month", "segment_value": seg_value,
            "n": int(r["n"]), "mad": round(float(r["mad"]), 6),
            "verdict": r["classification"],
            "chi2": round(float(r["chi_square"]), 2), "chi2_p": float(r["chi2_pvalue"]),
            "max_dev_digit": max_dev_digit,
            "is_flagged": r["classification"] == "NONCONFORMING",
        })
        for digit, obs_p, exp_p in zip(range(1, 10), observed, expected):
            digit_rows.append({
                "segment_dim": "country_month", "segment_value": seg_value,
                "digit": digit, "observed_prop": round(obs_p, 6), "expected_prop": round(exp_p, 6),
            })
    return pd.DataFrame(seg_rows), pd.DataFrame(digit_rows)


# ===================================================================
# Monthly trend & segment heatmap, full population, no model score needed
# ===================================================================

def build_monthly_trend(flagged: pd.DataFrame) -> pd.DataFrame:
    """One row per year_month: volume, value, flagged rate, leading-digit MAD."""
    rows = []
    for ym, g in flagged.groupby("year_month"):
        txn_count = len(g)
        total_value = float(g["amount"].sum())
        flagged_count = int(g["rule_flags"].apply(len).gt(0).sum())
        benford_pop = g[(g["amount"] >= 1) & (~g["is_adjustment"])]
        mad = np.nan
        if len(benford_pop) >= cfg.benford.min_segment_n:
            ld = leading_digit(benford_pop["amount"]).dropna()
            obs = ld.value_counts(normalize=True).reindex(range(1, 10), fill_value=0)
            exp = pd.Series(EXPECTED_DIGIT_PROP)
            mad = float((obs - exp).abs().mean())
        last_2_days = g["days_to_month_end"] <= cfg.rules.period_end_days if "days_to_month_end" in g else pd.Series(False, index=g.index)
        rows.append({
            "year_month": ym, "txn_count": txn_count, "total_value": round(total_value, 2),
            "flagged_count": flagged_count,
            "pct_flagged": round(100 * flagged_count / txn_count, 2) if txn_count else 0.0,
            "mad": round(mad, 6) if not np.isnan(mad) else None,
            "pct_last_2_days": round(100 * float(last_2_days.mean()), 2),
        })
    return pd.DataFrame(rows).sort_values("year_month").reset_index(drop=True)


def build_segment_heatmap(flagged: pd.DataFrame, segments_df: pd.DataFrame) -> pd.DataFrame:
    """country x year_month grid: volume, flagged rate, Benford MAD/verdict."""
    mad_lookup = {}
    verdict_lookup = {}
    for _, r in segments_df.iterrows():
        country, ym = r["segment_value"].split("|", 1)
        mad_lookup[(country, ym)] = r["mad"]
        verdict_lookup[(country, ym)] = r["verdict"]

    rows = []
    for (country, ym), g in flagged.groupby(["country", "year_month"]):
        txn_count = len(g)
        flagged_count = int(g["rule_flags"].apply(len).gt(0).sum())
        rows.append({
            "country": country, "year_month": ym, "txn_count": txn_count,
            "flagged_count": flagged_count,
            "pct_flagged": round(100 * flagged_count / txn_count, 2) if txn_count else 0.0,
            "mad": mad_lookup.get((country, ym)),
            "verdict": verdict_lookup.get((country, ym), "INSUFFICIENT_DATA"),
        })
    return pd.DataFrame(rows).sort_values(["country", "year_month"]).reset_index(drop=True)


# ===================================================================
# dashboard_export, the scored-sample transaction-level export
# ===================================================================

EXPORT_COLUMNS = [
    "txn_id", "invoice", "stock_code", "description", "customer_id", "country",
    "quantity", "price", "amount",
    "invoice_date", "year", "month", "year_month", "quarter", "day_of_week", "day_name",
    "hour", "days_to_month_end", "is_month_end",
    "leading_digit", "second_digit",
    "is_adjustment", "is_nonpositive_amount", "has_customer_stats",
    "rule_flag_count", "rule_flag_names",
    "benford_flag_any",
    "if_score", "lof_score", "lof_in_subsample", "if_pct",
    "composite_risk", "risk_band", "risk_rank",
    "is_synthetic_anomaly", "anomaly_type",
]


def build_dashboard_export(scored_df: pd.DataFrame) -> pd.DataFrame:
    """Full-schema export for the scored population, see EXPORT_COLUMNS."""
    df = scored_df.copy()
    df["leading_digit"] = leading_digit(df["amount"])
    df["second_digit"] = second_digit(df["amount"])
    df = df.rename(columns={"benford_flag": "benford_flag_any"})
    return df[[c for c in EXPORT_COLUMNS if c in df.columns]]


# ===================================================================
# Main run function
# ===================================================================

def run() -> dict[str, Any]:
    """Stage 8 entry point (export half). Assumes src.composite.run() already ran."""
    logger = setup_logging("export")

    with timed(logger, "stage8_export"):
        from src.composite import run as composite_run, top_risk_list

        result = composite_run()
        scored_df, comp_summary = result["df"], result["summary"]

        dashboard_export = build_dashboard_export(scored_df)
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        dashboard_export.to_parquet(PROCESSED_DIR / "dashboard_export.parquet", index=False)
        dashboard_export.to_csv(PROCESSED_DIR / "dashboard_export_sample.csv", index=False)
        logger.info("Wrote dashboard_export.parquet/.csv (%d rows, %d cols)",
                    len(dashboard_export), len(dashboard_export.columns))

        top50 = top_risk_list(scored_df, n=int(cfg.composite.top_n_export))
        top50.to_csv(DASHBOARD_DIR / "top_risk_transactions.csv", index=False)

        top5000 = top_risk_list(scored_df, n=min(5000, len(scored_df)))
        top5000.to_csv(DASHBOARD_DIR / "top_risk_5000.csv", index=False)
        logger.info("Wrote top_risk_transactions.csv (%d rows) and top_risk_5000.csv (%d rows)",
                    len(top50), len(top5000))

        # --- rank_labels.json : the live in-browser re-scoring simulator's only input.
        # Position i = whether the i-th highest composite_risk row is a real injected
        # anomaly (1) or not (0). No other column is needed: precision/recall/lift at
        # any review budget k is a prefix-sum lookup over this array in JS, and because
        # it is the exact ranking Stage 7 validated, the numbers it produces at k=500
        # match model_metrics.json's published Precision@500 exactly. ---
        ranked = scored_df.sort_values("composite_risk", ascending=False)
        rank_labels = ranked["is_synthetic_anomaly"].astype(int).tolist()
        (DASHBOARD_DIR / "rank_labels.json").write_text(json.dumps(rank_labels, separators=(",", ":")))
        logger.info("Wrote rank_labels.json (%d entries, %d positive)", len(rank_labels), sum(rank_labels))

        # --- Full-population business/Benford aggregates ---
        flagged = pd.read_parquet(FLAGGED_PATH)

        benford_agg = build_benford_aggregate(cfg.paths.metrics_dir / "benford_aggregate.csv")
        benford_agg.to_csv(DASHBOARD_DIR / "benford_aggregate.csv", index=False)

        segments_df, by_digit_df = build_benford_segments(cfg.paths.metrics_dir / "benford_segments.csv")
        segments_df.to_csv(DASHBOARD_DIR / "benford_segments.csv", index=False)
        by_digit_df.to_csv(DASHBOARD_DIR / "benford_by_segment_digit.csv", index=False)

        monthly_trend = build_monthly_trend(flagged)
        monthly_trend.to_csv(DASHBOARD_DIR / "monthly_trend.csv", index=False)

        segment_heatmap = build_segment_heatmap(flagged, segments_df)
        segment_heatmap.to_csv(DASHBOARD_DIR / "segment_heatmap.csv", index=False)

        # method_comparison.csv / model_metrics.json / pr_curve_points.csv /
        # precision_at_k.csv were already written to data/dashboard/ by
        # src.validate.run() (Stage 7), copy model_metrics.json alongside them
        # for a self-contained dashboard folder.
        mm_src = cfg.paths.metrics_dir / "model_metrics.json"
        if mm_src.exists():
            (DASHBOARD_DIR / "model_metrics.json").write_text(mm_src.read_text())

        # --- kpi_summary.json : cross-file consistency, no retyped numbers ---
        cleaning = json.loads((cfg.paths.metrics_dir / "cleaning_ledger.json").read_text())
        benford_summary = json.loads((cfg.paths.metrics_dir / "benford_summary.json").read_text())
        model_metrics = json.loads((cfg.paths.metrics_dir / "model_metrics.json").read_text())

        kpi = {
            "total_txns": cleaning["rows_out"],
            "total_value": round(float(flagged["amount"].sum()), 2),
            "date_range": [str(flagged["invoice_date"].min()), str(flagged["invoice_date"].max())],
            "aggregate_mad": benford_summary["aggregate"]["amount_first"]["mad"],
            "aggregate_verdict": benford_summary["aggregate"]["amount_first"]["classification"],
            "n_segments_assessed": benford_summary["segments"]["total"],
            "n_segments_flagged": benford_summary["segments"]["nonconforming"],
            "n_injected": benford_summary["n_injected"],
            "anomaly_rate": round(benford_summary["n_injected"] / benford_summary["n_total"], 6),
            "scored_population": comp_summary["n_rows"],
            "pct_high_critical": round(
                100 * (comp_summary["band_counts"]["HIGH"] + comp_summary["band_counts"]["CRITICAL"])
                / comp_summary["n_rows"], 2,
            ),
            "headline_average_precision": model_metrics["models"]["composite"]["average_precision"],
            "headline_ap_ci95": model_metrics["models"]["composite"]["ap_ci95"],
            "headline_recall_at_500": model_metrics["models"]["composite"]["recall_at_k"]["500"],
            "headline_precision_at_500": model_metrics["models"]["composite"]["precision_at_k"]["500"],
        }
        write_json(DASHBOARD_DIR / "kpi_summary.json", kpi)

        manifest = {p.name: p.stat().st_size for p in sorted(DASHBOARD_DIR.glob("*")) if p.is_file()}
        total_size = sum(manifest.values())
        logger.info("data/dashboard/ : %d files, %.2f MB total", len(manifest), total_size / 1e6)

    return {"kpi": kpi, "manifest": manifest, "total_size_bytes": total_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 8: dashboard data exports")
    parser.parse_args()
    run()
