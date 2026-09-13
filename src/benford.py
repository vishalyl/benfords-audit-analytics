"""Benford's Law analysis for the fraud detection pipeline.

Computes first-digit, second-digit, and first-two-digit distributions for
``amount`` and ``quantity``.  Compares observed distributions against Benford
expected values using chi-square and Mean Absolute Deviation (MAD).  Classifies
each (country, year_month) segment with Nigrini MAD thresholds and writes
aggregated metrics, per-segment details, a JSON summary, and diagnostic figures.

Usage:
    python -m src.benford [--sample] [--force]

Outputs (reports/metrics/):
    benford_aggregate.csv      -- Benford stats for amount & quantity (pooled)
    benford_segments.csv       -- per-(country,year_month) MAD + classification
    benford_second_digit.csv   -- second-digit distribution for amount
    benford_summary.json       -- high-level summary for the pipeline gate
Outputs (reports/figures/):
    benford_first_digit.png    -- bar chart: observed vs Benford first digits
    benford_segment_mad.png    -- bar chart: segment MAD scores
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Local imports (package-aware)
# ---------------------------------------------------------------------------
from src.config import cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BENFORD_PROB: list[float] = [
    0.301030,  # d = 1
    0.176091,  # d = 2
    0.124939,  # d = 3
    0.096910,  # d = 4
    0.079181,  # d = 5
    0.066947,  # d = 6
    0.057992,  # d = 7
    0.051153,  # d = 8
    0.045757,  # d = 9
]
DIGITS: list[int] = list(range(1, 10))

# Standard Nigrini thresholds for first-digit MAD (used as defaults).
# Configurable via config.yaml keys
#   benford.mad_thresholds_first  {close, acceptable, marginal}
# Falls back to these hardcoded values.
NIGRINI_DEFAULTS: dict[str, float] = {
    "close": 0.006,
    "acceptable": 0.012,
    "marginal": 0.018,  # SUSPECT
}


# ---------------------------------------------------------------------------
# Digit extraction  (Decimal-based -- NOT float string slicing)
# ---------------------------------------------------------------------------
def _extract_digits(value: float) -> tuple[int, int, int]:
    """Return (first_digit, second_digit, first_two_digits) via Decimal.

    Values <= 0 are returned as (0, 0, 0).  Negative amounts are abs'd.
    Uses Decimal(str(...)).to_integral_value() so we get the correct
    integer part without floating-point string-slicing artefacts.
    """
    if value is None or not math.isfinite(value) or value <= 0:
        return 0, 0, 0
    # Round DOWN to integer part via Decimal (avoids float rounding artefacts).
    d = int(Decimal(str(abs(value))).to_integral_value(rounding=ROUND_DOWN))
    if d == 0:
        return 0, 0, 0
    s = str(d)
    d1 = int(s[0])
    if len(s) == 1:
        return d1, 0, d1
    d2 = int(s[1])
    d12 = int(s[:2]) if len(s) >= 2 else d1
    return d1, d2, d12


def _extract_first_digit(value: float) -> int:
    """Convenience: just the first significant digit."""
    return _extract_digits(value)[0]


def _extract_second_digit(value: float) -> int:
    """Convenience: the second significant digit."""
    return _extract_digits(value)[1]


def _extract_first_two_digits(value: float) -> int:
    """Convenience: first two significant digits (10..99)."""
    return _extract_digits(value)[2]


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------
def _observed_distribution(digits: np.ndarray) -> np.ndarray:
    """Return a normalised length-9 array of proportions for digits 1..9."""
    counts = np.bincount(digits, minlength=10)[1:]  # skip index 0
    total = counts.sum()
    if total == 0:
        return np.zeros(9)
    return counts / total


def _mad(observed: np.ndarray, expected: np.ndarray) -> float:
    """Mean Absolute Deviation between two length-9 probability arrays."""
    return float(np.mean(np.abs(observed - expected)))


def _chi_square(observed: np.ndarray, n: int,
                expected: np.ndarray | None = None) -> tuple[float, float]:
    """Chi-square statistic and p-value against Benford (or supplied) distribution."""
    if expected is None:
        expected = np.array(BENFORD_PROB)
    expected_counts = expected * n
    # Guard against zero expected counts
    mask = expected_counts > 0
    chi2 = float(
        np.sum((observed[mask] - expected_counts[mask]) ** 2 / expected_counts[mask])
    )
    # df = 8 (9 categories - 1)
    from scipy.stats import chi2 as chi2_dist
    p_value = float(1 - chi2_dist.cdf(chi2, df=8))
    return chi2, p_value


def _classify(mad: float) -> str:
    """Nigrini MAD classification (first-digit scale).

    Thresholds are read from ``cfg.benford.mad_thresholds_first`` (close,
    acceptable, marginal) -- each key maps to CLOSE_CONFORMITY,
    INDISTINGUISHABLE, SUSPECT respectively.  Falls back to hardcoded
    Nigrini defaults when the config keys are absent.
    """
    try:
        mt = cfg.benford.mad_thresholds_first
        close = float(mt.close)
        acceptable = float(mt.acceptable)
        marginal = float(mt.marginal)
    except (AttributeError, TypeError, ValueError):
        close = NIGRINI_DEFAULTS["close"]
        acceptable = NIGRINI_DEFAULTS["acceptable"]
        marginal = NIGRINI_DEFAULTS["marginal"]

    if mad <= close:
        return "CLOSE_CONFORMITY"
    elif mad <= acceptable:
        return "INDISTINGUISHABLE"
    elif mad <= marginal:
        return "SUSPECT"
    else:
        return "NONCONFORMING"


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------
def _compute_benford_stats(series: pd.Series, label: str,
                           min_value: float | None = None) -> dict[str, Any]:
    """Compute first-digit distribution, MAD, chi-square for *series*.

    Only rows with value >= min_value (default 1.0 per config) are used,
    because Benford's law applies to magnitudes >= 1.
    """
    min_val = min_value if min_value is not None else cfg.cleaning.min_benford_amount
    mask = (series > 0) & (series >= min_val)
    vals = series.loc[mask]

    digits = np.vectorize(_extract_first_digit)(vals.values)
    obs = _observed_distribution(digits)
    n = int(mask.sum())
    mad = _mad(obs, BENFORD_PROB)
    chi2, p = _chi_square(obs, n)

    return {
        "metric": label,
        "n": n,
        "observed": obs.tolist(),
        "expected": BENFORD_PROB,
        "mad": round(mad, 6),
        "chi_square": round(chi2, 4),
        "chi2_pvalue": round(p, 6),
        "classification": _classify(mad),
    }


def _compute_all_digits(series: pd.Series, label: str,
                        min_value: float | None = None) -> dict[str, Any]:
    """Compute first, second, and first-two-digit stats."""
    stats = {}
    stats["first"] = _compute_benford_stats(series, f"{label}_first", min_value)

    min_val = min_value if min_value is not None else cfg.cleaning.min_benford_amount
    mask = (series > 0) & (series >= min_val)
    vals = series.loc[mask]

    if len(vals) > 0:
        d1 = np.vectorize(_extract_first_digit)(vals.values)
        d2 = np.vectorize(_extract_second_digit)(vals.values)
        d12 = np.vectorize(_extract_first_two_digits)(vals.values)

        obs2 = _observed_distribution(d2)
        mad2 = _mad(obs2, BENFORD_PROB)
        chi2_2, p2 = _chi_square(obs2, len(vals))
        stats["second"] = {
            "metric": f"{label}_second",
            "n": len(vals),
            "observed": obs2.tolist(),
            "expected": BENFORD_PROB,
            "mad": round(mad2, 6),
            "chi_square": round(chi2_2, 4),
            "chi2_pvalue": round(p2, 6),
            "classification": _classify(mad2),
        }

        # First-two digits: 10..99 range
        valid12 = d12[d12 > 0]
        if len(valid12) > 0:
            first_two_digits = [
                np.log10(1 + 1 / d) for d in range(10, 100)
            ]
            counts12 = np.bincount(valid12, minlength=100)[10:]
            total12 = counts12.sum()
            obs12 = counts12 / total12 if total12 > 0 else np.zeros(90)
            mad12 = float(np.mean(np.abs(obs12 - np.array(first_two_digits))))
            exp_counts12 = np.array(first_two_digits) * len(valid12)
            chi2_12 = float(
                np.sum((counts12 - exp_counts12) ** 2 / exp_counts12)
                if np.all(exp_counts12 > 0) else 0.0
            )
            from scipy.stats import chi2 as chi2_dist
            p12 = float(1 - chi2_dist.cdf(chi2_12, df=89))
            stats["first_two"] = {
                "metric": f"{label}_first_two",
                "n": len(valid12),
                "mad": round(mad12, 6),
                "chi_square": round(chi2_12, 4),
                "chi2_pvalue": round(p12, 6),
                "classification": _classify(mad12),
            }
    else:
        stats["second"] = {
            "metric": f"{label}_second", "n": 0,
            "observed": [0.0] * 9, "expected": BENFORD_PROB,
            "mad": 0.0, "chi_square": 0.0, "chi2_pvalue": 1.0,
            "classification": "CLOSE_CONFORMITY",
        }
        stats["first_two"] = {
            "metric": f"{label}_first_two", "n": 0,
            "mad": 0.0, "chi_square": 0.0, "chi2_pvalue": 1.0,
            "classification": "CLOSE_CONFORMITY",
        }

    return stats


def _second_digit_distribution(df: pd.DataFrame,
                               col: str = "amount") -> pd.DataFrame:
    """Full second-digit breakdown by country + year_month."""
    min_val = cfg.cleaning.min_benford_amount
    mask = (df[col] > 0) & (df[col] >= min_val)
    sub = df.loc[mask].copy()

    sub[f"{col}_d1"] = sub[col].apply(_extract_first_digit)
    sub[f"{col}_d2"] = sub[col].apply(_extract_second_digit)
    sub[f"{col}_d12"] = sub[col].apply(_extract_first_two_digits)

    rows = []
    for (country, ym), grp in sub.groupby(["country", "year_month"]):
        n = len(grp)
        d2_vals = grp[f"{col}_d2"].values
        d12_vals = grp[f"{col}_d12"].values

        obs2 = _observed_distribution(d2_vals)
        d12_valid = d12_vals[d12_vals > 0]
        if len(d12_valid) > 0:
            d12_obs = np.bincount(d12_valid, minlength=100)[10:]
            t12 = d12_obs.sum()
            obs12 = (d12_obs / t12 if t12 > 0 else np.zeros(90)).tolist()
        else:
            obs12 = [0.0] * 90

        rows.append({
            "country": country,
            "year_month": ym,
            "n": n,
            "d1_1": round(obs2[0], 6), "d1_2": round(obs2[1], 6),
            "d1_3": round(obs2[2], 6), "d1_4": round(obs2[3], 6),
            "d1_5": round(obs2[4], 6), "d1_6": round(obs2[5], 6),
            "d1_7": round(obs2[6], 6), "d1_8": round(obs2[7], 6),
            "d1_9": round(obs2[8], 6),
            "mad": round(_mad(obs2, BENFORD_PROB), 6),
            "classification": _classify(_mad(obs2, BENFORD_PROB)),
            "obs12_10": round(obs12[0], 6), "obs12_11": round(obs12[1], 6),
            "obs12_12": round(obs12[2], 6), "obs12_13": round(obs12[3], 6),
            "obs12_14": round(obs12[4], 6), "obs12_15": round(obs12[5], 6),
            "obs12_16": round(obs12[6], 6), "obs12_17": round(obs12[7], 6),
            "obs12_18": round(obs12[8], 6), "obs12_19": round(obs12[9], 6),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Segment analysis
# ---------------------------------------------------------------------------
def _segment_benford(df: pd.DataFrame,
                     label: str = "amount") -> pd.DataFrame:
    """Compute MAD and classification for each (country, year_month) segment.

    Returns a DataFrame sorted by MAD descending so nonconforming segments
    are easy to spot.
    """
    min_val = cfg.cleaning.min_benford_amount
    seg_min_n = cfg.benford.min_segment_n
    col = label

    # Vectorised digit extraction on the subset
    mask = (df[col] > 0) & (df[col] >= min_val)
    sub = df.loc[mask].copy()
    if len(sub) == 0:
        return pd.DataFrame()

    sub[f"{col}_d1"] = sub[col].apply(_extract_first_digit)

    seg_rows = []
    for (country, ym), grp in sub.groupby(["country", "year_month"]):
        n = len(grp)
        if n < seg_min_n:
            continue
        digits = grp[f"{col}_d1"].values
        obs = _observed_distribution(digits)
        mad = _mad(obs, BENFORD_PROB)
        chi2, p = _chi_square(obs, n)
        seg_rows.append({
            "country": country,
            "year_month": ym,
            "metric": f"{label}_first",
            "n": n,
            "observed": obs.tolist(),
            "expected": BENFORD_PROB,
            "mad": round(mad, 6),
            "chi_square": round(chi2, 4),
            "chi2_pvalue": round(p, 6),
            "classification": _classify(mad),
        })

    return pd.DataFrame(seg_rows).sort_values("mad", ascending=False)


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------
def _plot_first_digit(df: pd.DataFrame, label: str = "amount",
                      force: bool = False) -> Path:
    """Save benford_first_digit.png -- observed vs Benford bars."""
    figs = Path(cfg.paths.figures_dir)
    figs.mkdir(parents=True, exist_ok=True)
    out = figs / "benford_first_digit.png"
    if out.exists() and not force:
        return out

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for ax, col, title in zip(
        axes, ["amount_first", "quantity_first"],
        ["Amount, First Digit", "Quantity, First Digit"]
    ):
        row = df[df["metric"] == col]
        if row.empty:
            ax.set_title(f"{title} -- no data")
            continue
        row = row.iloc[0]
        obs = np.array(row["observed"])
        x = np.arange(1, 10)
        w = 0.35
        ax.bar(x - w / 2, BENFORD_PROB, w, label="Benford", color="#999999")
        ax.bar(x + w / 2, obs, w, label="Observed", color="#4A90D9")
        ax.set_xticks(x)
        ax.set_ylabel("Proportion")
        ax.set_title(title)
        ax.legend()
        ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(str(out), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def _plot_segment_mad(seg_df: pd.DataFrame, force: bool = False) -> Path:
    """Save benford_segment_mad.png -- bar chart of segment MAD scores."""
    figs = Path(cfg.paths.figures_dir)
    figs.mkdir(parents=True, exist_ok=True)
    out = figs / "benford_segment_mad.png"
    if out.exists() and not force:
        return out

    # Take the first-digit amount segment data; flag nonconforming red
    plot = seg_df[seg_df["metric"] == "amount_first"].copy()
    if plot.empty:
        plot = seg_df.copy()

    # Limit to top-30 segments for readability
    n_show = min(30, len(plot))
    if n_show == 0:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No segment data", ha="center", va="center",
                transform=ax.transAxes, fontsize=14)
        fig.savefig(str(out), dpi=150, bbox_inches="tight")
        plt.close(fig)
        return out

    plot = plot.nlargest(n_show, "mad")

    labels = [f"{r['country']}\n{r['year_month']}" for _, r in plot.iterrows()]
    mads = plot["mad"].values

    # Flag colour: red if NONCONFORMING or SUSPECT
    cls = plot["classification"].values
    colors = [
        "#D94A4A" if c in ("NONCONFORMING", "SUSPECT") else "#4A90D9"
        for c in cls
    ]

    # Read thresholds from config (same source as _classify)
    try:
        mt = cfg.benford.mad_thresholds_first
        thresh_marginal = float(mt.marginal)
        thresh_acceptable = float(mt.acceptable)
    except (AttributeError, TypeError, ValueError):
        thresh_marginal = NIGRINI_DEFAULTS["marginal"]
        thresh_acceptable = NIGRINI_DEFAULTS["acceptable"]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.barh(range(n_show), mads, color=colors, edgecolor="none")
    ax.set_yticks(range(n_show))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("MAD")
    ax.set_title("Benford First-Digit Segment MAD (amount)")
    ax.axvline(x=thresh_marginal,
               color="red", linestyle="--", alpha=0.5, label=f"SUSPECT threshold ({thresh_marginal})")
    ax.axvline(x=thresh_acceptable,
               color="orange", linestyle="--", alpha=0.5, label=f"INDISTINGUISHABLE threshold ({thresh_acceptable})")
    ax.grid(axis="x", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(str(out), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run(sample: bool = False, force: bool = False) -> dict[str, Any]:
    """Run the full Benford analysis and write all outputs."""
    logger = setup_logging("benford")

    input_path = Path(cfg.paths.processed_dir) / "transactions_labeled.parquet"
    if not input_path.exists():
        logger.error("Input not found: %s", input_path)
        sys.exit(1)

    logger.info("Loading %s", input_path)
    df = pd.read_parquet(input_path)
    if sample:
        sample_n = min(500_000, len(df))
        df = df.sample(n=sample_n, random_state=int(cfg.project.seed))
        logger.info("Sampled %d rows", len(df))

    metrics_dir = Path(cfg.paths.metrics_dir)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    with timed(logger, "Benford analysis"):
        # ------------------------------------------------------------------
        # 1. Aggregate stats (amount & quantity pooled)
        # ------------------------------------------------------------------
        amt_stats = _compute_all_digits(df["amount"], "amount")
        qty_stats = _compute_all_digits(df["quantity"], "quantity")
        aggregate = pd.DataFrame([
            {**amt_stats["first"], "detail": "first"},
            {**amt_stats["second"], "detail": "second"},
            {**amt_stats.get("first_two", {}), "detail": "first_two"},
            {**qty_stats["first"], "detail": "first"},
            {**qty_stats["second"], "detail": "second"},
            {**qty_stats.get("first_two", {}), "detail": "first_two"},
        ])

        # Reorder / fix columns for clean output
        out_cols = [
            "metric", "detail", "n", "observed", "expected",
            "mad", "chi_square", "chi2_pvalue", "classification",
        ]
        for c in out_cols:
            if c not in aggregate.columns:
                aggregate[c] = None
        aggregate = aggregate[out_cols]
        aggregate.to_csv(metrics_dir / "benford_aggregate.csv", index=False)
        logger.info("Wrote benford_aggregate.csv (%d rows)", len(aggregate))

        # ------------------------------------------------------------------
        # 2. Segment-level stats  (country, year_month)
        # ------------------------------------------------------------------
        seg_amt = _segment_benford(df, "amount")
        seg_qty = _segment_benford(df, "quantity")
        segments = pd.concat([seg_amt, seg_qty], ignore_index=True)

        # Flag nonconforming
        nonconforming = segments[segments["classification"] == "NONCONFORMING"].copy()
        nonconforming["column"] = nonconforming["metric"].apply(
            lambda m: "amount" if m == "amount_first" else "quantity"
        )
        nonconforming.to_csv(metrics_dir / "benford_segments.csv", index=False)
        logger.info(
            "Wrote benford_segments.csv (%d rows, %d nonconforming)",
            len(segments), len(nonconforming),
        )

        # ------------------------------------------------------------------
        # 3. Second-digit distribution (amount, per segment)
        # ------------------------------------------------------------------
        second_digit_df = _second_digit_distribution(df, "amount")
        second_digit_df.to_csv(metrics_dir / "benford_second_digit.csv", index=False)
        logger.info(
            "Wrote benford_second_digit.csv (%d segments)",
            len(second_digit_df),
        )

        # ------------------------------------------------------------------
        # 4. Summary JSON
        # ------------------------------------------------------------------
        overall_mad_amt = float(aggregate.loc[aggregate["metric"] == "amount_first", "mad"].values[0]) if len(aggregate.loc[aggregate["metric"] == "amount_first"]) > 0 else 0.0
        overall_mad_qty = float(aggregate.loc[aggregate["metric"] == "quantity_first", "mad"].values[0]) if len(aggregate.loc[aggregate["metric"] == "quantity_first"]) > 0 else 0.0

        # Count classifications for segments
        cls_counts = segments["classification"].value_counts().to_dict()

        # Top nonconforming segments
        top_nc = nonconforming.head(10).to_dict(orient="records")

        summary = {
            "n_total": int(len(df)),
            "n_base": int((~df["is_synthetic_anomaly"].astype(bool)).sum()),
            "n_injected": int(df["is_synthetic_anomaly"].sum()),
            "n_countries": int(df["country"].nunique()),
            "n_year_months": int(df["year_month"].nunique()),
            "aggregate": {
                "amount_first": {
                    "n": int(amt_stats["first"]["n"]),
                    "mad": round(overall_mad_amt, 6),
                    "chi_square": round(amt_stats["first"]["chi_square"], 4),
                    "chi2_pvalue": round(amt_stats["first"]["chi2_pvalue"], 6),
                    "classification": amt_stats["first"]["classification"],
                },
                "quantity_first": {
                    "n": int(qty_stats["first"]["n"]),
                    "mad": round(overall_mad_qty, 6),
                    "chi_square": round(qty_stats["first"]["chi_square"], 4),
                    "chi2_pvalue": round(qty_stats["first"]["chi2_pvalue"], 6),
                    "classification": qty_stats["first"]["classification"],
                },
                "amount_second": {
                    "n": int(amt_stats["second"]["n"]),
                    "mad": round(amt_stats["second"]["mad"], 6),
                    "chi_square": round(amt_stats["second"]["chi_square"], 4),
                    "chi2_pvalue": round(amt_stats["second"]["chi2_pvalue"], 6),
                    "classification": amt_stats["second"]["classification"],
                },
            },
            "segments": {
                "total": len(segments),
                "nonconforming": int((segments["classification"] == "NONCONFORMING").sum()),
                "suspect": int((segments["classification"] == "SUSPECT").sum()),
                "indistinguishable": int((segments["classification"] == "INDISTINGUISHABLE").sum()),
                "close_conformity": int((segments["classification"] == "CLOSE_CONFORMITY").sum()),
                "classification_counts": cls_counts,
                "top_nonconforming": top_nc,
            },
            "nonconforming_count": len(nonconforming),
        }
        write_json(metrics_dir / "benford_summary.json", summary)
        logger.info("Wrote benford_summary.json")

        # ------------------------------------------------------------------
        # 5. Figures
        # ------------------------------------------------------------------
        _plot_first_digit(aggregate, force=force)
        logger.info("Wrote benford_first_digit.png")
        _plot_segment_mad(segments, force=force)
        logger.info("Wrote benford_segment_mad.png")

    # ----------------------------------------------------------------------
    # Quick console report
    # ----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("BENFORD'S LAW ANALYSIS REPORT")
    print("=" * 60)
    print(f"  Total rows analysed : {len(df):,}")
    print(f"  Countries           : {df['country'].nunique()}")
    print(f"  Year-months         : {df['year_month'].nunique()}")
    print(f"  ---")
    print(f"  Amount  MAD (1st)   : {overall_mad_amt:.6f}  [{amt_stats['first']['classification']}]")
    print(f"  Amount  MAD (2nd)   : {amt_stats['second']['mad']:.6f}")
    print(f"  Quantity MAD (1st)  : {overall_mad_qty:.6f}  [{qty_stats['first']['classification']}]")
    print(f"  ---")
    print(f"  Segment nonconform  : {len(nonconforming)} / {len(segments)}")
    if len(nonconforming) > 0:
        print("  Top offenders:")
        for _, r in nonconforming.head(5).iterrows():
            print(f"    {r['country']:>12s}  {r['year_month']:>8s}  MAD={r['mad']:.6f}")
    print("=" * 60)

    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benford's Law analysis for fraud detection",
    )
    parser.add_argument(
        "--sample", action="store_true",
        help="Analyse a random sample (up to 500 k rows) for speed",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate figures even if they already exist",
    )
    args = parser.parse_args()
    run(sample=args.sample, force=args.force)


if __name__ == "__main__":
    main()
