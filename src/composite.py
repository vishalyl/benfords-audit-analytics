"""Stage 8 — Composite risk score, risk banding, and weight sensitivity.

Single implementation of the composite score, imported by both Stage 7
(``src.validate``, for the "composite" column of the detection matrix) and
Stage 8's own export step — see plan/03_STAGES_7-9.md sec 7.3 note and 8.2.

    composite_risk = 0.50 * percentile_rank(if_score)
                   + 0.30 * (rule_flag_count / 5)
                   + 0.20 * benford_flag

Honesty note (plan sec 8.1.2): the PRIMARY weights above are set a priori by
audit judgement, not tuned against the ground truth. The weight-sensitivity
table in ``weight_sensitivity()`` is reported as a robustness check on that
choice, not as a search for the best-scoring weights.

Usage::

    python -m src.composite [--sample]
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import rankdata
from sklearn.metrics import average_precision_score

from src.config import cfg
from src.io_utils import write_json
from src.logging_setup import setup_logging, timed

logger = logging.getLogger("audit.composite")

BAND_EDGES = [-np.inf, 0.40, 0.60, 0.80, np.inf]
BAND_LABELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

WEIGHT_VARIANTS: dict[str, dict[str, float]] = {
    "Primary": {"if": 0.50, "rules": 0.30, "benford": 0.20},
    "IF-heavy": {"if": 0.70, "rules": 0.20, "benford": 0.10},
    "Rules-heavy": {"if": 0.20, "rules": 0.60, "benford": 0.20},
    "Equal": {"if": 0.34, "rules": 0.33, "benford": 0.33},
    "No-Benford": {"if": 0.60, "rules": 0.40, "benford": 0.00},
}

# rule_flags -> suggested audit procedure. First matching key wins.
_PROCEDURE_MAP: list[tuple[str, str]] = [
    ("DUPLICATE_INVOICE", "Agree to supporting sales order and despatch note; confirm not a duplicate of a prior invoice."),
    ("SPLIT_AMOUNT", "Obtain the approval matrix; confirm the authorisation limit and whether the item was split to avoid it."),
    ("LARGE_AMOUNT", "Obtain the approval matrix; confirm the authorisation limit applicable to this transaction."),
    ("ROUND_DOLLARS", "Inspect for evidence of manual entry; agree to third-party documentation."),
    ("ROUND_NUMBER", "Inspect for evidence of manual entry; agree to third-party documentation."),
    ("HIGH_QUANTITY", "Agree quantity to despatch note and inventory records."),
    ("ODD_QUANTITY", "Agree quantity to despatch note and inventory records."),
    ("OFF_HOUR", "Review system access logs for the posting user and time."),
    ("NEGATIVE_ADJUSTMENT", "Agree the credit note or adjustment to supporting documentation."),
    ("ZERO_QUANTITY", "Confirm whether the transaction represents a genuine sale."),
]


def percentile_rank(s: pd.Series) -> pd.Series:
    """Average-tie percentile rank of *s*, strictly in [0, 1]."""
    arr = s.fillna(0).to_numpy(dtype=float)
    n = len(arr)
    if n <= 1:
        return pd.Series(np.zeros(n), index=s.index)
    ranks = rankdata(arr, method="average")
    pct = (ranks - 1) / (n - 1)
    return pd.Series(pct, index=s.index)


def compute_composite(df: pd.DataFrame, weights: dict[str, float] | None = None) -> pd.Series:
    """Implements the composite formula in the module docstring.

    Args:
        df: must contain ``if_score``, ``rule_flag_count``, ``benford_flag``.
        weights: optional override of {"if", "rules", "benford"}; normalised
            to sum to 1 before use. Defaults to config.yaml composite.*.

    Returns:
        Series in [0, 1], no nulls — asserted before return.
    """
    w = weights or {
        "if": float(cfg.composite.weight_if),
        "rules": float(cfg.composite.weight_rules),
        "benford": float(cfg.composite.weight_benford),
    }
    total = sum(w.values())
    w = {k: v / total for k, v in w.items()}

    if_component = percentile_rank(df["if_score"])
    rules_component = (df["rule_flag_count"].clip(upper=5) / 5.0).fillna(0)
    benford_component = df["benford_flag"].fillna(0).astype(float)

    risk = (w["if"] * if_component + w["rules"] * rules_component + w["benford"] * benford_component).clip(0, 1)

    assert risk.between(0, 1).all(), "composite_risk left [0,1]"
    assert not risk.isna().any(), "nulls in composite_risk"
    return risk.round(6)


def assign_band(score: pd.Series) -> pd.Series:
    """LOW <0.40, MEDIUM [0.40,0.60), HIGH [0.60,0.80), CRITICAL >=0.80."""
    return pd.cut(score, bins=BAND_EDGES, labels=BAND_LABELS, right=False)


def weight_sensitivity(
    df: pd.DataFrame, y_true: np.ndarray, variants: dict[str, dict[str, float]] | None = None,
) -> pd.DataFrame:
    """AP, recall@1000, precision@100 for each weight variant.

    See module docstring's honesty note: this is a robustness check on the
    a-priori primary weights, not a tuning search.
    """
    variants = variants or WEIGHT_VARIANTS
    n_pos = int(np.asarray(y_true).sum())
    rows = []
    for name, w in variants.items():
        score = compute_composite(df, weights=w).to_numpy()
        ap = average_precision_score(y_true, score)
        order = np.argsort(-score)
        k1000 = order[: min(1000, len(score))]
        recall_1000 = float(np.asarray(y_true)[k1000].sum() / n_pos) if n_pos else 0.0
        k100 = order[: min(100, len(score))]
        precision_100 = float(np.asarray(y_true)[k100].mean())
        rows.append({
            "variant": name, "w_if": w["if"], "w_rules": w["rules"], "w_benford": w["benford"],
            "average_precision": round(float(ap), 6),
            "recall_at_1000": round(recall_1000, 6),
            "precision_at_100": round(precision_100, 6),
        })
    return pd.DataFrame(rows)


def _suggested_procedure(rule_flags: Any, benford_flag: int, if_pct: float) -> str:
    """Map the dominant signal on a row to an audit procedure — plan sec 8.4."""
    if isinstance(rule_flags, (list, np.ndarray)) and len(rule_flags):
        flags = set(rule_flags)
        for key, text in _PROCEDURE_MAP:
            if key in flags:
                return text
    if if_pct >= 0.985:
        return "Analytical review: compare to the customer's historic transaction profile; obtain an explanation for the variance."
    if benford_flag:
        return "Extend testing across the segment; the item is flagged by population-level analytics rather than item-level attributes."
    return "Analytical review recommended based on an elevated composite risk score."


def top_risk_list(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Top-*n* rows by composite_risk, reviewer-facing columns, ties -> amount desc.

    Requires df to carry: txn_id, invoice, invoice_date, customer_id, country,
    stock_code, description, quantity, price, amount, composite_risk,
    risk_band, rule_flag_names, rule_flags, benford_flag, if_pct.
    """
    ranked = df.sort_values(["composite_risk", "amount"], ascending=[False, False]).head(n).copy()
    ranked = ranked.reset_index(drop=True)
    ranked["risk_rank"] = np.arange(1, len(ranked) + 1)
    ranked["suggested_procedure"] = [
        _suggested_procedure(rf, bf, ip)
        for rf, bf, ip in zip(ranked["rule_flags"], ranked["benford_flag"], ranked["if_pct"])
    ]
    cols = [
        "risk_rank", "txn_id", "invoice", "invoice_date", "customer_id", "country", "stock_code",
        "description", "quantity", "price", "amount", "composite_risk", "risk_band",
        "rule_flag_names", "if_pct", "suggested_procedure",
    ]
    return ranked[[c for c in cols if c in ranked.columns]]


# ===================================================================
# Main run function
# ===================================================================

def run(sample: bool = False) -> dict[str, Any]:
    """Stage 8 entry point — composite score, banding, weight sensitivity, review list."""
    logger = setup_logging("composite")

    with timed(logger, "stage8_composite"):
        from src.validate import load_evaluation_frame  # lazy: avoids import cycle

        df = load_evaluation_frame()
        if sample:
            n = min(cfg.ingest.sample_size, len(df))
            df = df.sample(n=n, random_state=cfg.project.seed).reset_index(drop=True)

        y_true = df["is_synthetic_anomaly"].values

        df["composite_risk"] = compute_composite(df)
        df["risk_band"] = assign_band(df["composite_risk"])
        df["risk_rank"] = df["composite_risk"].rank(method="first", ascending=False).astype(int)
        df["if_pct"] = df["if_score"].rank(pct=True)

        band_counts = df["risk_band"].value_counts().reindex(BAND_LABELS, fill_value=0).to_dict()

        sens = weight_sensitivity(df, y_true)
        composite_ap = float(sens.loc[sens["variant"] == "Primary", "average_precision"].iloc[0])

        # Compare against the best SINGLE method (rules-only / benford-only / IF-only),
        # i.e. weight_if=1/rules=1/benford=1 corners, not the blended variants above.
        single_method_aps = {}
        for name, w in [("if_only", {"if": 1.0, "rules": 0.0, "benford": 0.0}),
                        ("rules_only", {"if": 0.0, "rules": 1.0, "benford": 0.0}),
                        ("benford_only", {"if": 0.0, "rules": 0.0, "benford": 1.0})]:
            score = compute_composite(df, weights=w)
            single_method_aps[name] = round(float(average_precision_score(y_true, score)), 6)
        best_single_ap = max(single_method_aps.values())

        summary: dict[str, Any] = {
            "n_rows": len(df),
            "composite_risk_mean": round(float(df["composite_risk"].mean()), 6),
            "composite_risk_std": round(float(df["composite_risk"].std()), 6),
            "n_distinct_scores": int(df["composite_risk"].nunique()),
            "band_counts": {k: int(v) for k, v in band_counts.items()},
            "weight_sensitivity": sens.to_dict(orient="records"),
            "primary_average_precision": round(composite_ap, 6),
            "single_method_average_precision": single_method_aps,
            "best_single_method_ap": best_single_ap,
            "composite_beats_best_single_method": composite_ap >= best_single_ap,
            "top_k_export": int(cfg.composite.top_n_export),
        }
        write_json(cfg.paths.metrics_dir / "composite_summary.json", summary)
        logger.info(
            "Composite: mean=%.4f AP=%.4f (best single method %.4f) bands=%s",
            summary["composite_risk_mean"], composite_ap, best_single_ap, summary["band_counts"],
        )

    return {"df": df, "summary": summary}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 8: Composite risk scoring")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    run(sample=args.sample)
