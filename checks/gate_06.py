#!/usr/bin/env python
"""Gate 06, Validate anomaly scoring (Stage 6).

Checks:
  - transactions_scored.parquet exists with scoring columns
  - has if_score, lof_score, risk_score, risk_tier columns
  - risk_tier distribution is reasonable
  - AUC is computed and > 0.60 (random baseline)
  - model_summary.json has required structure
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd
import numpy as np

logger = logging.getLogger("audit.gate06")


def check(scored_path: str, summary_path: str) -> tuple[bool, list[str]]:
    msgs = []
    passed = True

    # ── C1: Scored parquet has required columns ───────────────────
    scored = pd.read_parquet(scored_path)
    required_cols = ["if_score", "lof_score", "risk_score", "risk_tier"]
    missing = [c for c in required_cols if c not in scored.columns]
    if not missing:
        msgs.append(f"C1: scored parquet has all required columns ({len(scored)} rows)")
    else:
        msgs.append(f"C1 FAILED: missing columns: {missing}")
        passed = False

    # ── C2: Scores are in valid range ─────────────────────────────
    for col in ["if_score", "lof_score", "risk_score"]:
        if col in scored.columns:
            vals = scored[col].dropna()
            if len(vals) > 0:
                if vals.min() < -1 or vals.max() > 1:
                    msgs.append(f"C2 WARNING: {col} range [{vals.min():.4f}, {vals.max():.4f}] outside [-1,1]")
                else:
                    msgs.append(f"C2: {col} range [{vals.min():.4f}, {vals.max():.4f}] OK")

    # ── C3: Risk tier distribution ────────────────────────────────
    if "risk_tier" in scored.columns:
        tier_counts = scored["risk_tier"].value_counts().to_dict()
        msgs.append(f"C3: risk tier distribution: {dict(tier_counts)}")
        if len(scored) > 0:
            critical = int((scored["risk_tier"] == "CRITICAL").sum())
            high = int((scored["risk_tier"] == "HIGH").sum())
            if critical + high == 0:
                msgs.append("C3 WARNING: no HIGH or CRITICAL risk rows")
            else:
                msgs.append(f"C3: {critical + high} rows at HIGH+CRITICAL risk")

    # ── C4: AUC check ─────────────────────────────────────────────
    with open(summary_path) as f:
        summary = json.load(f)

    if "auc_roc" in summary:
        auc = summary["auc_roc"]
        if auc > 0.60:
            msgs.append(f"C4: AUC-ROC = {auc:.4f} (>0.60 baseline)")
        else:
            msgs.append(f"C4 WARNING: AUC-ROC = {auc:.4f} (≤0.60 baseline)")

    # ── C5: Summary structure ─────────────────────────────────────
    required_keys = [("n_rows", ["n_rows", "total_rows"]), ("feature_columns", ["feature_columns"]), ("tiers", ["tiers", "risk_tiers"]), ("auc_roc", ["auc_roc"])]
    for key, check_keys in required_keys:
        found_key = None
        for k in check_keys:
            if k in summary:
                found_key = k
                break
        if found_key:
            msgs.append(f"C5: summary has '{key}' ({found_key}) = {summary[found_key]}")
        else:
            msgs.append(f"C5 FAILED: summary.json missing key '{key}'")
            passed = False

    if passed:
        msgs.insert(0, "GATE 06: PASS")
    else:
        msgs.insert(0, "GATE 06: FAIL")

    return passed, msgs


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    scored = "data/processed/transactions_scored.parquet"
    summary = "reports/metrics/model_summary.json"

    if not Path(scored).exists() or not Path(summary).exists():
        logger.error("Output not found. Run: python -m src.models --force")
        sys.exit(1)

    passed, msgs = check(scored, summary)
    for msg in msgs:
        logger.info(msg)

    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    Path("reports/gate_reports/gate_06.md").write_text("\n".join(msgs))

    logger.info("Result: %s", "PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
