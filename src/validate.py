"""Stage 7, Validation against ground truth.

Joins ground-truth labels with rule flags, Benford segment flags and model
scores, then computes binary and ranking metrics, the anomaly-type x
detection-method matrix, a threshold sweep and bootstrap confidence
intervals.

Framing (see plan/03_STAGES_7-9.md sec 7.1), must be respected everywhere
this module's output is later quoted:
  1. Positives are ONLY the injected rows. A method that flags a genuine
     (unlabelled) anomaly in the real ledger is scored here as a false
     positive, so every precision figure is a LOWER BOUND.
  2. Recall is trustworthy; precision is pessimistic.
  3. Ranking metrics (average precision, precision@k) lead; binary
     confusion-matrix metrics at a fixed operating point are secondary.
  4. The model ranks transactions for review. It does not "detect fraud".

Usage::

    python -m src.validate [--sample]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Callable

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

matplotlib.use("Agg")

from src.config import cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed
from src.viz import PALETTE, FIGSIZE, DPI, save_fig, setup_style

logger = logging.getLogger("audit.validate")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

LABELED_PATH = cfg.paths.processed_dir / "transactions_labeled.parquet"
FLAGGED_PATH = cfg.paths.processed_dir / "transactions_flagged.parquet"
SCORED_PATH = cfg.paths.processed_dir / "transactions_scored.parquet"
BENFORD_SEGMENTS_CSV = cfg.paths.metrics_dir / "benford_segments.csv"

K_LIST = [50, 100, 250, 500, 1000, 5000]

# Identity / value / time columns pulled through from the labeled frame so
# that Stage 8's dashboard export does not need a second load of the raw data.
PASSTHROUGH_COLS = [
    "invoice", "stock_code", "description", "quantity", "price", "amount",
    "customer_id", "country", "invoice_date", "year", "month", "year_month",
    "quarter", "day_of_week", "day_name", "hour", "days_to_month_end",
    "is_month_end", "is_adjustment", "is_nonpositive_amount",
    "has_customer_stats",
]

CAVEATS = [
    "Positives are injected rows only; genuine anomalies already present in "
    "the real ledger are scored as false positives when flagged, so every "
    "precision figure reported here is a lower bound, not an exact rate.",
    "The Isolation Forest decision threshold was calibrated to the known "
    "injection rate (contamination=0.015); in a real engagement the true "
    "anomaly rate is unknown and this threshold would have to be set by "
    "judgement or a fixed review-alert budget instead.",
    "Local Outlier Factor does not scale to the full population, so it is fit "
    "and scored on a bounded random subsample only (see lof_in_subsample); its "
    "ranking metrics (average precision, ROC-AUC) are computed on that subsample, "
    "while its precision/recall/confusion figures span the full population, so "
    "its recall is capped by coverage as well as by model quality.",
]


# ===================================================================
# 1. load_evaluation_frame
# ===================================================================

def load_evaluation_frame(
    labeled_path: Path | None = None,
    flagged_path: Path | None = None,
    scored_path: Path | None = None,
) -> pd.DataFrame:
    """Join ground truth + rule flags + model scores on ``txn_id``.

    The join is inner on the three sources' ``txn_id`` sets. If Stage 6 was
    run with ``--sample``, the evaluation population is that sample rather
    than the full cleaned ledger; this is logged either way, not hidden.

    Returns:
        DataFrame with one row per scored transaction carrying ground truth,
        rule-flag info, a Benford segment flag, model scores, and the
        passthrough identity/value/time columns needed by Stage 8.

    Raises:
        ValueError: if any source has duplicate txn_ids (would break the
            1:1 join guarantee the Leakage Firewall depends on).
    """
    labeled_path = Path(labeled_path) if labeled_path else LABELED_PATH
    flagged_path = Path(flagged_path) if flagged_path else FLAGGED_PATH
    scored_path = Path(scored_path) if scored_path else SCORED_PATH

    df_label = pd.read_parquet(labeled_path)
    df_flag = pd.read_parquet(flagged_path)
    df_score = pd.read_parquet(scored_path)

    for frame, tag in [(df_label, "label"), (df_flag, "flag"), (df_score, "score")]:
        dup = frame["txn_id"].duplicated().sum()
        if dup:
            raise ValueError(f"{dup} duplicate txn_ids in {tag} source, join would not be 1:1")

    id_label = df_label.set_index("txn_id")
    id_flag = df_flag.set_index("txn_id")
    id_score = df_score.set_index("txn_id")

    common_ids = id_label.index.intersection(id_score.index).intersection(id_flag.index)
    n_total, n_after = len(id_label), len(common_ids)
    logger.info(
        "Evaluation population: %d / %d labeled rows (%.1f%% coverage)",
        n_after, n_total, 100 * n_after / n_total,
    )

    ground_truth = id_label.loc[common_ids, ["is_synthetic_anomaly", "anomaly_type"]]
    passthrough = id_label.loc[common_ids, [c for c in PASSTHROUGH_COLS if c in id_label.columns]]
    rule_flags = id_flag.loc[common_ids, ["rule_flags"]]
    score_cols = ["if_score", "lof_score"] + (["lof_in_subsample"] if "lof_in_subsample" in id_score.columns else [])
    scores = id_score.loc[common_ids, score_cols]
    if "lof_in_subsample" not in scores.columns:
        scores = scores.assign(lof_in_subsample=True)  # older scored files: LOF ran on every row

    merged = pd.concat([ground_truth, passthrough, rule_flags, scores], axis=1).reset_index()

    merged["is_synthetic_anomaly"] = merged["is_synthetic_anomaly"].astype(int)
    merged["rule_flag_count"] = merged["rule_flags"].apply(
        lambda x: len(x) if isinstance(x, (list, np.ndarray)) else 0
    )
    merged["rule_flag_names"] = merged["rule_flags"].apply(
        lambda x: ", ".join(x) if isinstance(x, (list, np.ndarray)) and len(x) else ""
    )

    # --- Benford segment flag: row's (country, year_month) segment was
    #     classified NONCONFORMING on the amount leading-digit test ---
    merged["benford_flag"] = 0
    if BENFORD_SEGMENTS_CSV.exists():
        bdf = pd.read_csv(BENFORD_SEGMENTS_CSV)
        bdf = bdf[(bdf["metric"] == "amount_first") & (bdf["classification"] == "NONCONFORMING")]
        bad_segments = set(zip(bdf["country"], bdf["year_month"]))
        if bad_segments:
            # Vectorised membership test (was a per-row .apply, too slow at
            # full-population scale of ~1M rows).
            seg_keys = pd.Series(list(zip(merged["country"], merged["year_month"])), index=merged.index)
            merged["benford_flag"] = seg_keys.isin(bad_segments).astype(int)

    # Assert no nulls in the score columns used by every downstream metric.
    assert merged[["if_score", "lof_score"]].isna().sum().sum() == 0, "nulls in score columns"

    logger.info("Evaluation frame: %d rows, %d cols", len(merged), len(merged.columns))
    return merged.reset_index(drop=True)


# ===================================================================
# 2. binary_metrics
# ===================================================================

def binary_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Confusion-matrix metrics for a fixed binary decision.

    Returns:
        precision, recall, f1, tp, fp, tn, fn, specificity, fpr,
        alerts (=tp+fp), alert_rate.
    """
    yt = np.asarray(y_true, dtype=int)
    yp = np.asarray(y_pred, dtype=int)
    tn, fp, fn, tp = confusion_matrix(yt, yp, labels=[0, 1]).ravel()

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    alerts = int(tp + fp)

    return {
        "precision": round(float(precision), 6),
        "recall": round(float(recall), 6),
        "f1": round(float(f1), 6),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
        "specificity": round(float(specificity), 6),
        "fpr": round(float(fpr), 6),
        "alerts": alerts,
        "alert_rate": round(alerts / len(yt), 6) if len(yt) else 0.0,
    }


# ===================================================================
# 3. ranking_metrics
# ===================================================================

def ranking_metrics(
    y_true: np.ndarray, score: np.ndarray, k_list: list[int] | None = None,
) -> dict[str, Any]:
    """Threshold-free ranking metrics: AP, ROC-AUC, precision/recall/lift@k.

    Returns:
        average_precision, roc_auc, baseline_precision (= y_true.mean()),
        precision_at_k / recall_at_k / lift_at_k dicts keyed by k, and a
        thinned precision_recall_curve for plotting.
    """
    k_list = k_list or K_LIST
    yt = np.asarray(y_true)
    sc = np.asarray(score)
    n_total = len(yt)
    n_pos = int(yt.sum())
    baseline = n_pos / n_total if n_total else 0.0

    result: dict[str, Any] = {
        "average_precision": round(float(average_precision_score(yt, sc)), 6),
        "roc_auc": round(float(roc_auc_score(yt, sc)), 6),
        "baseline_precision": round(baseline, 6),
        "n_positive": n_pos,
        "n_total": n_total,
        "precision_at_k": {}, "recall_at_k": {}, "lift_at_k": {},
    }

    order = np.argsort(-sc)
    for k in k_list:
        kk = min(k, n_total)
        top = order[:kk]
        p_at_k = float(yt[top].mean()) if kk else 0.0
        r_at_k = float(yt[top].sum() / n_pos) if n_pos else 0.0
        lift = p_at_k / baseline if baseline else 0.0
        result["precision_at_k"][str(k)] = round(p_at_k, 6)
        result["recall_at_k"][str(k)] = round(r_at_k, 6)
        result["lift_at_k"][str(k)] = round(lift, 4)

    precisions, recalls, thresholds = precision_recall_curve(yt, sc)
    step = max(1, len(precisions) // 200)
    result["precision_recall_curve"] = {
        "precision": [round(float(p), 6) for p in precisions[::step]],
        "recall": [round(float(r), 6) for r in recalls[::step]],
    }
    return result


# ===================================================================
# 4. per_type_detection  (THE ANOMALY-TYPE x DETECTION-METHOD MATRIX)
# ===================================================================

def per_type_detection(
    eval_df: pd.DataFrame, method_binary: dict[str, pd.Series],
) -> pd.DataFrame:
    """Long-format anomaly-type x detection-method flagging matrix.

    Args:
        eval_df: output of load_evaluation_frame(), plus composite_risk.
        method_binary: {method_name: 0/1 Series aligned to eval_df.index}.

    Returns:
        Tidy DataFrame with columns anomaly_type, method, n_rows, n_caught,
        pct_caught, one row per (type, method) pair, plus ALL_INJECTED and
        REAL_ROWS sentinel rows. This is data/dashboard/method_comparison.csv.
    """
    types = [t for t in eval_df["anomaly_type"].unique() if t != "none"]
    row_labels = sorted(types) + ["ALL_INJECTED", "REAL_ROWS"]

    records = []
    for label in row_labels:
        if label == "ALL_INJECTED":
            subset_idx = eval_df.index[eval_df["is_synthetic_anomaly"] == 1]
        elif label == "REAL_ROWS":
            subset_idx = eval_df.index[eval_df["is_synthetic_anomaly"] == 0]
        else:
            subset_idx = eval_df.index[eval_df["anomaly_type"] == label]

        n_rows = len(subset_idx)
        for method, binary in method_binary.items():
            n_caught = int(binary.loc[subset_idx].sum()) if n_rows else 0
            pct = round(100 * n_caught / n_rows, 2) if n_rows else 0.0
            records.append({
                "anomaly_type": label, "method": method,
                "n_rows": n_rows, "n_caught": n_caught, "pct_caught": pct,
            })
    return pd.DataFrame(records)


def _wide_matrix(long_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long matrix to the wide display form used in the gate report."""
    order = [t for t in long_df["anomaly_type"].unique() if t not in ("ALL_INJECTED", "REAL_ROWS")]
    order = sorted(order) + ["ALL_INJECTED", "REAL_ROWS"]
    wide = long_df.pivot(index="anomaly_type", columns="method", values="pct_caught")
    return wide.reindex(order)


# ===================================================================
# 5. threshold_sweep / optimal_threshold
# ===================================================================

def threshold_sweep(y_true: np.ndarray, score: np.ndarray, n_points: int = 200) -> pd.DataFrame:
    """Precision/recall/F1/alert-count at n_points thresholds spanning score's range."""
    yt = np.asarray(y_true)
    sc = np.asarray(score)
    thresholds = np.linspace(sc.min(), sc.max(), n_points)
    rows = []
    for t in thresholds:
        preds = (sc >= t).astype(int)
        m = binary_metrics(yt, preds)
        rows.append({"threshold": round(float(t), 6), **{k: m[k] for k in ("precision", "recall", "f1", "alerts")}})
    return pd.DataFrame(rows).rename(columns={"alerts": "alert_count"})


def optimal_threshold(sweep: pd.DataFrame, criterion: str = "f1") -> float:
    """Threshold maximising *criterion* (a column of the sweep)."""
    if criterion not in sweep.columns:
        raise ValueError(f"Unknown criterion '{criterion}'")
    return float(sweep.loc[sweep[criterion].idxmax(), "threshold"])


# ===================================================================
# 6. bootstrap_ci
# ===================================================================

def bootstrap_ci(
    y_true: np.ndarray, score: np.ndarray,
    metric_fn: Callable[[np.ndarray, np.ndarray], float] = average_precision_score,
    n_boot: int = 200, seed: int = 42,
) -> tuple[float, float, float]:
    """Bootstrap the 95% CI of *metric_fn* by resampling rows with replacement.

    Returns:
        (point_estimate, ci_lower_95, ci_upper_95).
    """
    rng = np.random.RandomState(seed)
    yt = np.asarray(y_true)
    sc = np.asarray(score)
    n = len(yt)
    point = float(metric_fn(yt, sc))
    stats = []
    for _ in range(n_boot):
        idx = rng.randint(0, n, n)
        if yt[idx].sum() == 0 or yt[idx].sum() == n:
            continue
        stats.append(metric_fn(yt[idx], sc[idx]))
    if not stats:
        return round(point, 6), round(point, 6), round(point, 6)
    lo, hi = np.percentile(stats, [2.5, 97.5])
    return round(point, 6), round(float(lo), 6), round(float(hi), 6)


# ===================================================================
# Figures
# ===================================================================

def _fig_pr_curve(models: dict[str, dict], baseline: float) -> plt.Figure:
    fig, ax = plt.subplots(figsize=FIGSIZE)
    colors = [PALETTE["primary"], PALETTE["risk"], PALETTE["good"], PALETTE["warning"]]
    for (name, m), color in zip(models.items(), colors):
        curve = m.get("_pr_curve")
        if not curve:
            continue
        ax.plot(curve["recall"], curve["precision"], label=f"{name} (AP={m['average_precision']:.3f})",
                color=color, linewidth=2)
    ax.axhline(baseline, color=PALETTE["neutral"], linestyle="--", label=f"Random baseline ({baseline:.4f})")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall, all models")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig


def _fig_roc_curve(series: dict[str, tuple[np.ndarray, np.ndarray]]) -> plt.Figure:
    """series: {method_name: (y_true, score)} -- each method may use a different
    y_true, since LOF is only evaluated on the rows it actually scored."""
    fig, ax = plt.subplots(figsize=FIGSIZE)
    colors = [PALETTE["primary"], PALETTE["risk"], PALETTE["good"]]
    for (name, (yt, sc)), color in zip(series.items(), colors):
        fpr, tpr, _ = roc_curve(yt, sc)
        auc = roc_auc_score(yt, sc)
        ax.plot(fpr, tpr, label=f"{name} (AUC={auc:.3f})", color=color, linewidth=2)
    ax.plot([0, 1], [0, 1], "--", color=PALETTE["neutral"])
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC curve (optimistic under heavy class imbalance, see caveats)")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig


def _fig_precision_at_k(models: dict[str, dict]) -> plt.Figure:
    fig, ax = plt.subplots(figsize=FIGSIZE)
    colors = [PALETTE["primary"], PALETTE["risk"], PALETTE["good"], PALETTE["warning"]]
    for (name, m), color in zip(models.items(), colors):
        pk = m.get("precision_at_k")
        if not pk:
            continue
        ks = [int(k) for k in pk]
        ax.plot(ks, [pk[str(k)] for k in ks], marker="o", label=name, color=color)
    ax.set_xscale("log")
    ax.set_xlabel("k (transactions reviewed, log scale)")
    ax.set_ylabel("Precision@k")
    ax.set_title("Precision@k, the audit-relevant curve")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig


def _fig_confusion(y_true: np.ndarray, y_pred: np.ndarray, title: str) -> plt.Figure:
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    cm_pct = cm / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm_pct, cmap="Blues", vmin=0, vmax=1)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i, j]:,}\n({cm_pct[i, j]*100:.1f}%)", ha="center", va="center", fontsize=10)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["Predicted 0", "Predicted 1"])
    ax.set_yticks([0, 1]); ax.set_yticklabels(["Actual 0", "Actual 1"])
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    return fig


def _fig_method_heatmap(long_df: pd.DataFrame) -> plt.Figure:
    wide = _wide_matrix(long_df)
    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(wide.values, cmap="RdYlGn_r", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(wide.columns))); ax.set_xticklabels(wide.columns, rotation=30, ha="right")
    ax.set_yticks(range(len(wide.index))); ax.set_yticklabels(wide.index)
    for i in range(wide.shape[0]):
        for j in range(wide.shape[1]):
            v = wide.values[i, j]
            ax.text(j, i, f"{v:.1f}%", ha="center", va="center", fontsize=8,
                    color="white" if v > 60 else "black")
    ax.set_title("Method x anomaly-type detection matrix (% caught)")
    fig.colorbar(im, ax=ax, fraction=0.03)
    fig.tight_layout()
    return fig


def _fig_threshold_sweep(sweep: pd.DataFrame, opt: float) -> plt.Figure:
    fig, ax1 = plt.subplots(figsize=FIGSIZE)
    ax1.plot(sweep["threshold"], sweep["precision"], label="Precision", color=PALETTE["primary"])
    ax1.plot(sweep["threshold"], sweep["recall"], label="Recall", color=PALETTE["risk"])
    ax1.plot(sweep["threshold"], sweep["f1"], label="F1", color=PALETTE["good"], linewidth=2)
    ax1.axvline(opt, color=PALETTE["neutral"], linestyle="--", label=f"Chosen threshold ({opt:.3f})")
    ax1.set_xlabel("Composite risk threshold")
    ax1.set_ylabel("Precision / Recall / F1")
    ax2 = ax1.twinx()
    ax2.plot(sweep["threshold"], sweep["alert_count"], color=PALETTE["warning"], alpha=0.4, label="Alert count")
    ax2.set_ylabel("Alert count")
    ax1.set_title("Threshold sweep, composite risk score")
    ax1.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    return fig


def _fig_score_by_type(eval_df: pd.DataFrame) -> plt.Figure:
    types = sorted(t for t in eval_df["anomaly_type"].unique() if t != "none")
    order = ["none"] + types
    data = [eval_df.loc[eval_df["anomaly_type"] == t, "composite_risk"].values for t in order]
    fig, ax = plt.subplots(figsize=(11, 6))
    bp = ax.boxplot(data, patch_artist=True, tick_labels=order)
    for patch, t in zip(bp["boxes"], order):
        patch.set_facecolor(PALETTE["neutral"] if t == "none" else PALETTE["risk"])
        patch.set_alpha(0.6)
    ax.set_xticklabels(order, rotation=30, ha="right")
    ax.set_ylabel("Composite risk score")
    ax.set_title("Composite risk score distribution by anomaly type")
    fig.tight_layout()
    return fig


def _fig_recall_vs_effort(y_true: np.ndarray, score: np.ndarray) -> plt.Figure:
    n = len(y_true)
    order = np.argsort(-score)
    yt_sorted = np.asarray(y_true)[order]
    n_pos = yt_sorted.sum()
    cum_recall = np.cumsum(yt_sorted) / n_pos if n_pos else np.zeros(n)
    x = np.arange(1, n + 1)
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.plot(x, cum_recall * 100, color=PALETTE["primary"], linewidth=2, label="Composite risk ranking")
    ax.plot(x, np.minimum(x / n_pos, 1) * 100 if n_pos else x * 0, "--", color=PALETTE["neutral"], label="Random review order")
    ax.set_xlabel("Transactions reviewed")
    ax.set_ylabel("% of planted anomalies found")
    ax.set_title("Cumulative recall vs review effort")
    ax.legend()
    fig.tight_layout()
    return fig


# ===================================================================
# Main run function
# ===================================================================

def run(sample: bool = False) -> dict[str, Any]:
    """Stage 7 entry point. Writes model_metrics.json, method_comparison.csv, 8 figures."""
    logger = setup_logging("validate")

    with timed(logger, "stage7_validate"):
        from src.composite import compute_composite  # lazy: avoids import cycle

        eval_df = load_evaluation_frame()
        if sample:
            n = min(cfg.ingest.sample_size, len(eval_df))
            eval_df = eval_df.sample(n=n, random_state=cfg.project.seed).reset_index(drop=True)

        y_true = eval_df["is_synthetic_anomaly"].values
        n_total, n_pos = len(eval_df), int(y_true.sum())

        eval_df["composite_risk"] = compute_composite(eval_df)

        # --- Method scores / binary decisions ---
        # LOF only ever scores a bounded subsample of the population (it does not
        # scale to ~1M rows); rows outside it get a hard 0.0, which is NOT a real
        # "normal" verdict. Every LOF calculation below is therefore scoped to
        # lof_in_subsample==True so a coverage limit is never mistaken for a
        # quality result -- see the caveats list and DECISIONS.md.
        lof_mask = eval_df["lof_in_subsample"].astype(bool)
        lof_coverage = float(lof_mask.mean())

        contamination = float(cfg.model.contamination_primary)
        pct = 1 - contamination
        if_thresh = float(np.quantile(eval_df["if_score"], pct))
        lof_thresh = float(np.quantile(eval_df.loc[lof_mask, "lof_score"], pct)) if lof_mask.any() else 1.0
        comp_thresh = float(np.quantile(eval_df["composite_risk"], pct))

        method_binary = {
            "benford_any": eval_df["benford_flag"].astype(int),
            "rules_any": (eval_df["rule_flag_count"] >= 1).astype(int),
            "iforest": (eval_df["if_score"] >= if_thresh).astype(int),
            "lof": (lof_mask & (eval_df["lof_score"] >= lof_thresh)).astype(int),
            "composite": (eval_df["composite_risk"] >= comp_thresh).astype(int),
        }

        # --- model_metrics.json : models{} ---
        models: dict[str, Any] = {}
        for name in ("benford_any", "rules_any"):
            m = binary_metrics(y_true, method_binary[name].values)
            models[name] = m

        for name, score_col, thresh in [
            ("iforest", "if_score", if_thresh),
            ("lof", "lof_score", lof_thresh),
            ("composite", "composite_risk", comp_thresh),
        ]:
            if name == "lof":
                # Ranking quality is measured only on the rows LOF actually scored;
                # the binary confusion matrix still spans the full population, so
                # its recall correctly reflects the real-world coverage limit.
                score = eval_df.loc[lof_mask, "lof_score"].values
                y_true_m = eval_df.loc[lof_mask, "is_synthetic_anomaly"].values
            else:
                score = eval_df[score_col].values
                y_true_m = y_true
            rk = ranking_metrics(y_true_m, score)
            pr_curve = rk.pop("precision_recall_curve")
            point, lo, hi = bootstrap_ci(y_true_m, score)
            bm = binary_metrics(y_true, method_binary[name].values)
            models[name] = {
                **rk, "_pr_curve": pr_curve,
                "ap_ci95": [lo, hi],
                "threshold_used": round(thresh, 6), "threshold_criterion": "contamination_0.015",
                **{k: v for k, v in bm.items() if k in ("precision", "recall", "f1")},
                "confusion": {k: bm[k] for k in ("tp", "fp", "tn", "fn")},
            }
            if name == "lof":
                models[name]["note"] = (
                    f"Computed on a {int(lof_mask.sum()):,}-row stratified subsample "
                    f"({lof_coverage*100:.1f}% of the scored population); ranking metrics "
                    "(average_precision, roc_auc, precision_at_k) are scoped to that "
                    "subsample, but precision/recall/confusion span the full population, "
                    "so recall is capped by coverage, not just model quality."
                )

        # --- per-type detection matrix (long format) ---
        method_matrix_long = per_type_detection(eval_df, method_binary)

        # --- per-type binary metrics (for model_metrics.json "per_type") ---
        per_type: dict[str, Any] = {}
        for atype in sorted(t for t in eval_df["anomaly_type"].unique() if t != "none"):
            mask = eval_df["anomaly_type"] == atype
            n = int(mask.sum())
            per_type[atype] = {
                name: {
                    "n": n,
                    "pct_caught": round(100 * float(method_binary[name].loc[mask].mean()), 2) if n else 0.0,
                }
                for name in method_binary
            }

        # --- threshold sweep on the composite score (headline operating point) ---
        sweep = threshold_sweep(y_true, eval_df["composite_risk"].values, n_points=200)
        opt = optimal_threshold(sweep, criterion="f1")

        # --- complementarity assertion inputs ---
        wide = _wide_matrix(method_matrix_long)
        gaps = []
        type_rows = wide.drop(index=["ALL_INJECTED", "REAL_ROWS"], errors="ignore")
        if "rules_any" in type_rows.columns and "iforest" in type_rows.columns:
            diff = type_rows["rules_any"] - type_rows["iforest"]
            gaps = [("rules_any_beats_iforest", diff.idxmax(), float(diff.max())),
                    ("iforest_beats_rules_any", (-diff).idxmax(), float(-diff.min()))]

        output: dict[str, Any] = {
            "population": {
                "n_total": n_total, "n_injected": n_pos,
                "anomaly_rate": round(n_pos / n_total, 6) if n_total else 0.0,
            },
            "baseline_precision": round(n_pos / n_total, 6) if n_total else 0.0,
            "models": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in models.items()},
            "per_type": per_type,
            "threshold_sweep": {
                "optimal_threshold": round(opt, 6),
                "criterion": "f1",
                "metrics_at_optimal": binary_metrics(y_true, (eval_df["composite_risk"].values >= opt).astype(int)),
            },
            "complementarity_check": {
                "gaps_pct_points": gaps,
                "passes": bool(gaps and gaps[0][2] >= 20 and gaps[1][2] >= 20),
            },
            "caveats": CAVEATS,
        }

        out_path = cfg.paths.metrics_dir / "model_metrics.json"
        write_json(out_path, output)
        logger.info("Wrote %s", out_path)

        dashboard_csv = cfg.paths.dashboard_dir / "method_comparison.csv"
        method_matrix_long.to_csv(dashboard_csv, index=False)
        (cfg.paths.metrics_dir / "method_comparison.csv").write_text(method_matrix_long.to_csv(index=False))
        logger.info("Wrote %s (%d rows)", dashboard_csv, len(method_matrix_long))

        # thin PR-curve export for the dashboard / Power BI
        pr_points = pd.DataFrame({
            "recall": models["composite"]["_pr_curve"]["recall"],
            "precision": models["composite"]["_pr_curve"]["precision"],
        })
        pr_points.to_csv(cfg.paths.dashboard_dir / "pr_curve_points.csv", index=False)

        precision_at_k_rows = []
        for name, m in models.items():
            if "precision_at_k" not in m:
                continue
            for k, v in m["precision_at_k"].items():
                precision_at_k_rows.append({"method": name, "k": int(k), "precision_at_k": v})
        pd.DataFrame(precision_at_k_rows).to_csv(cfg.paths.dashboard_dir / "precision_at_k.csv", index=False)

        # --- Figures ---
        setup_style()
        save_fig(_fig_pr_curve({k: v for k, v in models.items() if "_pr_curve" in v}, output["baseline_precision"]),
                  "pr_curve.png", category="validation")
        save_fig(_fig_roc_curve({
            "iforest": (y_true, eval_df["if_score"].values),
            "lof": (eval_df.loc[lof_mask, "is_synthetic_anomaly"].values, eval_df.loc[lof_mask, "lof_score"].values),
            "composite": (y_true, eval_df["composite_risk"].values),
        }), "roc_curve.png", category="validation")
        save_fig(_fig_precision_at_k({k: v for k, v in models.items() if "precision_at_k" in v}),
                  "precision_at_k.png", category="validation")
        save_fig(_fig_confusion(y_true, method_binary["composite"].values, "Composite risk @ contamination threshold"),
                  "confusion_matrix.png", category="validation")
        save_fig(_fig_method_heatmap(method_matrix_long), "method_comparison_heatmap.png", category="validation")
        save_fig(_fig_threshold_sweep(sweep, opt), "threshold_sweep.png", category="validation")
        save_fig(_fig_score_by_type(eval_df), "score_by_type.png", category="validation")
        save_fig(_fig_recall_vs_effort(y_true, eval_df["composite_risk"].values), "recall_vs_effort.png", category="validation")
        logger.info("Saved 8 validation figures")

        logger.info(
            "Validation complete: composite AP=%.4f (baseline %.4f), iforest AP=%.4f, complementarity=%s",
            models["composite"]["average_precision"], output["baseline_precision"],
            models["iforest"]["average_precision"], output["complementarity_check"]["passes"],
        )

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 7: Validation against ground truth")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    run(sample=args.sample)
