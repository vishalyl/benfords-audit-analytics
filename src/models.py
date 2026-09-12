"""Stage 6 — Unsupervised anomaly scoring (Isolation Forest + LOF).

Loads ``data/processed/transactions_flagged.parquet``, trains an
IsolationForest on a 50 % random sample and computes Local Outlier
Factor scores on the full dataset.  A composite risk score combining
IF, LOF and rule-flag counts is derived and written to parquet along
with a risk-tier bucket and summary artefacts.

Usage::

    python -m src.models [--sample] [--force]
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

from src.config import cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed
from src.viz import PALETTE, FIGSIZE, DPI, save_fig, setup_style

logger = logging.getLogger("audit.models")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INPUT_PATH = cfg.paths.processed_dir / "transactions_flagged.parquet"
OUTPUT_PATH = cfg.paths.processed_dir / "transactions_scored.parquet"

COLOR_REAL = "#4A90D9"
COLOR_FLAGGED = "#D94A4A"

# Feature columns — leakage-safe, deterministic set
FEATURE_COLS = [
    "amount",
    "quantity",
    "price",
    "hour",
    "day_of_week",
    "cust_txn_count",
    "cust_amount_mean",
    "cust_amount_std",
]

# Columns to drop / never expose to the model matrix
LEAKAGE_COLS = {"is_synthetic_anomaly", "anomaly_type", "txn_id"}


# ---------------------------------------------------------------------------
# Helper: normalise an array into [0, 1]
# ---------------------------------------------------------------------------

def _normalise(arr: np.ndarray) -> np.ndarray:
    """Min-max normalise *arr* into [0, 1].

    Returns the original array unchanged when its range is zero.
    """
    mn, mx = arr.min(), arr.max()
    if mx == mn:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def _train_iforest(X: np.ndarray) -> tuple[IsolationForest, np.ndarray]:
    """Train an IsolationForest on a 50 % random sample and score *all* rows.

    Returns the fitted model and the normalised anomaly scores (0-1).
    """
    rng = np.random.RandomState(cfg.project.seed)
    mask = rng.random(len(X)) < 0.5
    X_train = X[mask]
    logger.info("IsolationForest training on %d / %d rows", len(X_train), len(X))

    model = IsolationForest(
        n_estimators=cfg.model.n_estimators,
        max_samples=cfg.model.max_samples,
        contamination="auto",
        random_state=cfg.project.seed,
        n_jobs=cfg.model.n_jobs,
    )
    model.fit(X_train)

    # decision_function: higher = more normal (inlier), lower = more outlier
    raw_scores = model.decision_function(X)
    # Negate so higher = more anomalous
    anomaly_scores = -raw_scores
    return model, _normalise(anomaly_scores)


def _compute_lof(X: np.ndarray) -> np.ndarray:
    """Compute LOF scores on the full dataset.

    Uses subsampling to stay within memory bounds for ~1M rows.
    Returns the normalised anomaly scores (0-1).
    """
    max_subsample = cfg.model.lof_subsample_n
    if len(X) > max_subsample:
        logger.info("LOF subsampling %d -> %d rows", len(X), max_subsample)
        idx = np.arange(len(X))
        rng = np.random.RandomState(cfg.project.seed)
        sample_idx = rng.choice(idx, size=max_subsample, replace=False)
        X_fit = X[sample_idx]
    else:
        X_fit = X

    lof = LocalOutlierFactor(
        n_neighbors=cfg.model.lof_n_neighbors,
        contamination="auto",
        novelty=False,
        n_jobs=cfg.model.n_jobs,
    )
    lof.fit(X_fit)

    # negative_outlier_factor_: more negative = more anomalous
    raw_scores = -lof.negative_outlier_factor_
    normalised = _normalise(raw_scores)

    logger.info("LOF computed for %d rows", len(normalised))
    return normalised


# ---------------------------------------------------------------------------
# Risk tiers
# ---------------------------------------------------------------------------

def _assign_tier(risk: np.ndarray) -> np.ndarray:
    """Map continuous risk to discrete tiers.

    * LOW      < 0.2
    * MEDIUM   0.2 - 0.5
    * HIGH     0.5 - 0.8
    * CRITICAL >= 0.8
    """
    tiers = pd.cut(
        risk,
        bins=[-np.inf, 0.2, 0.5, 0.8, np.inf],
        labels=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
    )
    return np.asarray(tiers)


# ---------------------------------------------------------------------------
# Composite risk score
# ---------------------------------------------------------------------------

def _composite_score(
    if_score: np.ndarray,
    lof_score: np.ndarray,
    rule_flag_count: np.ndarray,
) -> np.ndarray:
    """risk = 0.4 * IF + 0.3 * LOF + 0.3 * rule_flag_norm"""
    flag_norm = _normalise(rule_flag_count)
    risk = 0.4 * if_score + 0.3 * lof_score + 0.3 * flag_norm
    return risk


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _score_distribution_plot(
    df_scored: pd.DataFrame,
) -> plt.Figure:
    """Histogram of the composite risk score, faceted by anomaly label."""
    fig, ax = plt.subplots(figsize=(10, 6))

    mask_real = df_scored["is_synthetic_anomaly"] == 0
    mask_anom = ~mask_real

    ax.hist(
        df_scored.loc[mask_real, "risk_score"],
        bins=80, alpha=0.5, color=COLOR_REAL,
        label="Real", density=True,
    )
    ax.hist(
        df_scored.loc[mask_anom, "risk_score"],
        bins=80, alpha=0.5, color=COLOR_FLAGGED,
        label="Anomaly (injected)", density=True,
    )

    ax.set_xlabel("Composite risk score")
    ax.set_ylabel("Density")
    ax.set_title("Composite risk score distribution")
    ax.legend()
    ax.tick_params(axis="x", rotation=0)
    plt.tight_layout()
    return fig


def _risk_by_anomaly_plot(
    df_scored: pd.DataFrame,
) -> plt.Figure:
    """Bar chart: risk-tier breakdown split by real vs anomaly."""
    fig, ax = plt.subplots(figsize=(10, 6))

    tier_order = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    cross = pd.crosstab(
        df_scored["is_synthetic_anomaly"],
        df_scored["risk_tier"],
        margins=False,
    )
    # Reindex to ensure correct tier order
    cross = cross.reindex(columns=tier_order, fill_value=0)

    width = 0.35
    x = np.arange(len(tier_order))
    ax.bar(
        x - width / 2,
        cross.loc[0, tier_order],
        width, color=COLOR_REAL, label="Real",
    )
    ax.bar(
        x + width / 2,
        cross.loc[1, tier_order],
        width, color=COLOR_FLAGGED, label="Anomaly",
    )

    ax.set_xticks(x)
    ax.set_xticklabels(tier_order)
    ax.set_ylabel("Count")
    ax.set_title("Risk tier by ground-truth label")
    ax.legend()
    plt.tight_layout()
    return fig


def _feature_importance_plot(
    X: pd.DataFrame,
    if_scores: np.ndarray,
) -> plt.Figure:
    """Bar chart of feature importance based on absolute correlation with IF scores."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Compute absolute correlation of each feature with IF anomaly score
    correlations = X.apply(lambda col: abs(np.corrcoef(col.values, if_scores)[0, 1]))
    correlations = correlations.sort_values(ascending=True)

    ax.barh(correlations.index, correlations.values, color=PALETTE["secondary"])
    ax.set_xlabel("Absolute correlation with IF anomaly score")
    ax.set_title("Feature importance (IF correlation)")
    ax.tick_params(axis="y", labelsize=10)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def _build_features(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, np.ndarray, dict[str, Any], np.ndarray]:
    """Return feature DataFrame, rule_flag_count, info dict, and NaN mask.

    Excludes leakage columns and non-feature identifiers.  Returns a boolean
    array indicating which rows have any NaN in the feature columns so callers
    can handle them (score = 0).
    """
    drop_cols = LEAKAGE_COLS | {"invoice", "customer_id"}
    keep = [c for c in df.columns if c not in drop_cols]
    feat_df = df[keep].copy()

    # Compute rule_flag_count from the list-of-strings column
    feat_df["rule_flag_count"] = df["rule_flags"].apply(len)

    full = feat_df[FEATURE_COLS + ["rule_flag_count"]]
    nan_mask = full.isna().any(axis=1).values

    info = {
        "feature_columns": list(FEATURE_COLS),
        "n_feature_columns": len(FEATURE_COLS),
        "total_rows": len(full),
        "rows_with_nan": int(nan_mask.sum()),
    }

    return full, full["rule_flag_count"].values, info, nan_mask


def run(force: bool = False, sample: bool = False) -> None:
    """Stage 6 entry point — unsupervised anomaly scoring pipeline."""
    logger = setup_logging("models")

    with timed(logger, "stage6_models"):
        # --- Load data ---
        if not INPUT_PATH.exists():
            logger.error(
                "Input file %s not found. Run stages 0-5 first.", INPUT_PATH,
            )
            raise FileNotFoundError(INPUT_PATH)

        logger.info("Loading %s", INPUT_PATH)
        df = pd.read_parquet(INPUT_PATH)

        # --- Sub-sample for iteration ---
        if sample:
            n = cfg.ingest.sample_size
            logger.info("Using %d-row sample", n)
            df = df.sample(n=min(n, len(df)), random_state=cfg.project.seed)

        # --- Build feature matrix ---
        feat_df, rule_flag_count, feat_info, nan_mask = _build_features(df)
        logger.info("Feature matrix: %s", feat_info)

        # Downcast floats to float32 for memory efficiency
        for col in feat_df.columns:
            if feat_df[col].dtype == "float64":
                feat_df[col] = feat_df[col].astype("float32")

        # Clean rows with NaN — models can't handle missing values
        clean_mask = ~nan_mask
        X_clean = feat_df.loc[clean_mask].values.astype(np.float64)
        X_full = feat_df.values.astype(np.float64)  # original order, with NaNs

        n_clean = len(X_clean)
        logger.info("Clean rows for training: %d / %d", n_clean, len(df))

        # --- Isolation Forest (train on clean data) ---
        if_model, if_scores = _train_iforest(X_clean)

        # --- LOF (fit on clean data, score all) ---
        lof_scores = _compute_lof(X_clean)

        # --- Pad NaN rows with zeros so arrays stay aligned ---
        if_scores_full = np.zeros(len(df))
        lof_scores_full = np.zeros(len(df))
        if_scores_full[clean_mask] = if_scores
        lof_scores_full[clean_mask] = lof_scores

        # --- Composite risk ---
        risk_scores = _composite_score(
            if_scores_full, lof_scores_full, rule_flag_count,
        )
        risk_tiers = _assign_tier(risk_scores)

        # --- Build output DataFrame ---
        out = df.copy()
        out["if_score"] = if_scores_full
        out["lof_score"] = lof_scores_full
        out["risk_score"] = risk_scores
        out["risk_tier"] = risk_tiers

        # --- Tier distribution ---
        tier_counts = pd.Series(risk_tiers).value_counts()
        logger.info("Risk tier distribution:\n%s", tier_counts.to_string())

        # --- AUC against ground truth (informational) ---
        auc = roc_auc_score(
            df["is_synthetic_anomaly"], risk_scores,
        )
        logger.info("AUC-ROC (risk_score vs is_synthetic_anomaly): %.4f", auc)

        # --- Persist scored parquet ---
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(OUTPUT_PATH, index=False)
        logger.info(
            "Wrote %s (%d rows, %d with risk_score > 0.5)",
            OUTPUT_PATH, len(out), int((risk_scores > 0.5).sum()),
        )

        # --- Summary JSON ---
        summary: dict[str, Any] = {
            **feat_info,
            "n_flagged_rows": int((rule_flag_count > 0).sum()),
            "risk_score_mean": round(float(risk_scores.mean()), 6),
            "risk_score_std": round(float(risk_scores.std()), 6),
            "risk_score_min": round(float(risk_scores.min()), 6),
            "risk_score_max": round(float(risk_scores.max()), 6),
            "if_score_mean": round(float(if_scores_full.mean()), 6),
            "lof_score_mean": round(float(lof_scores_full.mean()), 6),
            "risk_tiers": {
                str(tier): int(cnt) for tier, cnt in tier_counts.items()
            },
            "auc_roc": round(auc, 6),
            "parameters": {
                "n_estimators": cfg.model.n_estimators,
                "max_samples": cfg.model.max_samples,
                "lof_n_neighbors": cfg.model.lof_n_neighbors,
                "lof_subsample_n": cfg.model.lof_subsample_n,
                "if_weight": 0.4,
                "lof_weight": 0.3,
                "flag_weight": 0.3,
            },
        }
        metrics_dir = cfg.paths.metrics_dir
        metrics_dir.mkdir(parents=True, exist_ok=True)
        write_json(metrics_dir / "model_summary.json", summary)
        logger.info("Wrote reports/metrics/model_summary.json")

        # --- Figures ---
        setup_style()

        fig_dist = _score_distribution_plot(out)
        save_fig(fig_dist, "model_score_distribution.png", category="models")
        logger.info("Saved model_score_distribution.png")

        fig_risk = _risk_by_anomaly_plot(out)
        save_fig(fig_risk, "model_risk_by_anomaly.png", category="models")
        logger.info("Saved model_risk_by_anomaly.png")

        feat_cols_df = pd.DataFrame(
            feat_df.values, columns=list(FEATURE_COLS) + ["rule_flag_count"],
        )
        fig_fi = _feature_importance_plot(feat_cols_df, if_scores_full)
        save_fig(fig_fi, "model_feature_importance.png", category="models")
        logger.info("Saved model_feature_importance.png")

        logger.info(
            "Summary: rows=%d AUC=%.4f tiers=%s",
            len(out), auc, dict(tier_counts),
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Stage 6: Isolation Forest + LOF anomaly scoring",
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
