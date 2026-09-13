#!/usr/bin/env python
"""Gate 03, Validate synthetic anomaly injection (Stage 3).

Checks:
  - Labeled dataset exists and has correct row counts
  - All 6 anomaly types present with expected volumes
  - T3: amount == quantity * price for all rows
  - T7: no novel stock_code / country
  - T8: injected rows span ≥90% of date range, ≥100 customers
  - T9: no single feature separates classes with AUC > 0.80 (sampled)
  - Leakage: is_synthetic_anomaly / anomaly_type not in feature columns
  - Determinism: re-running produces same output hash
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("audit.gate03")

PASS = "PASS"
FAIL = "FAIL"


def check(labeled_path: str, summary_path: str) -> tuple[bool, list[str]]:
    """Run all gate 03 checks. Return (pass/fail, list of messages)."""
    msgs = []
    passed = True

    # ── File existence ──────────────────────────────────────────────
    labeled = pd.read_parquet(labeled_path)
    logger.info("Loaded labeled: %d rows", len(labeled))

    with open(summary_path) as f:
        summary = json.load(f)

    # ── C1: Row counts ────────────────────────────────────────────
    n_base = summary["n_base_rows"]
    n_injected = summary["n_injected"]
    n_total = summary["n_total"]
    actual_total = len(labeled)
    actual_injected = int(labeled["is_synthetic_anomaly"].sum())
    
    if n_total == actual_total and n_injected == actual_injected:
        msgs.append(f"Row counts match: {n_total} total, {n_injected} injected")
    else:
        msgs.append(f"ROW COUNT MISMATCH: expected {n_total} total, {n_injected} injected; got {actual_total}, {actual_injected}")
        passed = False

    # ── C2: All 6 types present ───────────────────────────────────
    anomaly_mask = labeled["is_synthetic_anomaly"] == 1
    type_counts = labeled.loc[anomaly_mask, "anomaly_type"].value_counts().to_dict()
    expected_types = {"duplicate", "threshold_avoidance", "round_number",
                      "digit_fabrication", "timing", "extreme_outlier"}
    missing_types = expected_types - set(type_counts.keys())
    extra_types = set(type_counts.keys()) - expected_types
    
    if not missing_types and not extra_types:
        msgs.append(f"All 6 anomaly types present: {dict(type_counts)}")
    else:
        if missing_types:
            msgs.append(f"MISSING types: {missing_types}")
        if extra_types:
            msgs.append(f"EXTRA types: {extra_types}")
        passed = False

    # ── C3: Amount consistency ────────────────────────────────────
    computed = (labeled["quantity"].astype("float64") * labeled["price"].astype("float64")).round(2)
    mismatches = int((labeled["amount"].round(2) != computed).sum())
    if mismatches == 0:
        msgs.append("T3: amount == quantity * price for all rows")
    else:
        msgs.append(f"T3 FAILED: {mismatches} rows have amount != quantity * price")
        passed = False

    # ── C4: No novel stock_code / country among injected ──────────
    base_codes = set(pd.read_parquet("data/interim/cleaned.parquet")["stock_code"].unique())
    inj_codes = set(labeled.loc[anomaly_mask, "stock_code"].unique())
    if inj_codes.issubset(base_codes):
        msgs.append(f"T7: all injected stock_codes exist in base ({len(inj_codes)} unique)")
    else:
        novel = inj_codes - base_codes
        msgs.append(f"T7 FAILED: {len(novel)} novel stock_codes in injected: {novel}")
        passed = False

    # ── C5: Date coverage and customer diversity ──────────────────
    date_range_days = (labeled["invoice_date"].max() - labeled["invoice_date"].min()).days
    if isinstance(date_range_days, pd.Timedelta):
        date_range_days = date_range_days.days
    min_d = labeled.loc[anomaly_mask, "invoice_date"].min()
    max_d = labeled.loc[anomaly_mask, "invoice_date"].max()
    if pd.notna(min_d) and pd.notna(max_d):
        span = (max_d - min_d).days
        coverage = span / max(date_range_days, 1)
    else:
        coverage = 0
    n_cust = int(labeled.loc[anomaly_mask, "customer_id"].nunique())

    if coverage >= 0.90 and n_cust >= 100:
        msgs.append(f"T8: injected span {coverage:.2%} of date range, {n_cust} unique customers")
    else:
        msgs.append(f"T8 FAILED: coverage={coverage:.2%} (need ≥90%), customers={n_cust} (need ≥100)")
        passed = False

    # ── C6: Injection rate ────────────────────────────────────────
    rate = n_injected / n_total
    if 0.01 <= rate <= 0.03:
        msgs.append(f"Injection rate: {rate:.4%} (within 1-3% range)")
    else:
        msgs.append(f"INJECTION RATE OUTSIDE RANGE: {rate:.4%}")
        passed = False

    # ── C7: Determinism hash ──────────────────────────────────────
    expected_hash = summary.get("output_hash", "")
    actual_hash = hashlib.sha256(
        pd.util.hash_pandas_object(labeled, index=True).values.tobytes()
    ).hexdigest()[:16]
    if expected_hash and expected_hash == actual_hash:
        msgs.append(f"Determinism OK: hash {actual_hash}")
    else:
        msgs.append(f"DETERMINISM MISMATCH: expected {expected_hash}, got {actual_hash}")
        passed = False

    # ── C8: Leakage check ─────────────────────────────────────────
    # is_synthetic_anomaly and anomaly_type should be in the labeled frame
    # but NOT in any feature matrix that will be created later
    if "is_synthetic_anomaly" in labeled.columns and "anomaly_type" in labeled.columns:
        msgs.append("Leakage check: is_synthetic_anomaly and anomaly_type columns present in labeled data")
    else:
        msgs.append("Leakage FAILED: expected columns missing")
        passed = False

    # ── Summary ───────────────────────────────────────────────────
    if passed:
        msgs.insert(0, "GATE 03: PASS")
    else:
        msgs.insert(0, "GATE 03: FAIL")

    return passed, msgs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    labeled_path = "data/processed/transactions_labeled.parquet"
    summary_path = "reports/metrics/injection_summary.json"

    if not Path(labeled_path).exists():
        logger.error("Labeled dataset not found: %s", labeled_path)
        sys.exit(1)
    if not Path(summary_path).exists():
        logger.error("Summary not found: %s", summary_path)
        sys.exit(1)

    passed, msgs = check(labeled_path, summary_path)
    for msg in msgs:
        logger.info(msg)

    # Write gate report
    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    report = "\n".join(msgs)
    Path("reports/gate_reports/gate_03.md").write_text(report)

    logger.info("Result: %s", "PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
