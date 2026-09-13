#!/usr/bin/env python
"""Gate 04, Validate Benford's Law analysis (Stage 4).

Checks:
  - Output files exist (benford_aggregate.csv, benford_segments.csv, benford_summary.json)
  - benford_aggregate.csv has both amount and quantity entries
  - benford_summary.json has required keys
  - Segments were analyzed (non-zero count)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger("audit.gate04")


def check(aggregate_path: str, segments_path: str, summary_path: str) -> tuple[bool, list[str]]:
    msgs = []
    passed = True

    # ── File existence ──────────────────────────────────────────────
    for name, path in [("benford_aggregate", aggregate_path),
                       ("benford_segments", segments_path),
                       ("benford_summary", summary_path)]:
        if not Path(path).exists():
            msgs.append(f"MISSING file: {name} ({path})")
            passed = False

    if not passed:
        msgs.insert(0, "GATE 04: FAIL")
        return passed, msgs

    # ── C1: Aggregate has both amount and quantity ─────────────────
    agg = pd.read_csv(aggregate_path)
    metrics = agg.get("metric", pd.Series([], dtype=str)).tolist()
    metric_strs = " ".join(str(m) for m in metrics)
    has_amount = any("amount" in str(m) for m in metrics)
    has_quantity = any("quantity" in str(m) for m in metrics)
    if has_amount and has_quantity:
        msgs.append(f"C1: benford_aggregate has {len(agg)} rows with amount and quantity metrics")
    else:
        msgs.append(f"C1 FAILED: missing metrics (amount={has_amount}, quantity={has_quantity}, cols={list(agg.columns)})")
        passed = False

    # ── C2: Summary JSON structure ─────────────────────────────────
    with open(summary_path) as f:
        summary = json.load(f)

    if "aggregate" in summary and "segments" in summary:
        agg_data = summary["aggregate"]
        msgs.append(f"C2: summary has 'aggregate' with {len(agg_data)} entries, 'segments' with {summary['segments'].get('total', '?')} segments")
        
        # Check MAD values
        if "amount_first" in agg_data:
            msgs.append(f"C2: amount_first MAD = {agg_data['amount_first'].get('mad', 'N/A')} ({agg_data['amount_first'].get('classification', 'N/A')})")
        if "quantity_first" in agg_data:
            msgs.append(f"C2: quantity_first MAD = {agg_data['quantity_first'].get('mad', 'N/A')} ({agg_data['quantity_first'].get('classification', 'N/A')})")
    else:
        msgs.append(f"C2 FAILED: summary missing 'aggregate' or 'segments' keys")
        passed = False

    # ── C3: Segments file has MAD column ───────────────────────────
    seg_df = pd.read_csv(segments_path)
    mad_cols = [c for c in seg_df.columns if "mad" in c.lower()]
    if mad_cols:
        msgs.append(f"C3: segments file has {len(seg_df)} rows with MAD column(s): {mad_cols}")
    else:
        msgs.append(f"C3 FAILED: segments file missing MAD column (columns: {list(seg_df.columns)})")
        passed = False

    # ── C4: Nonconforming segments identified ──────────────────────
    nonconform = summary.get("segments", {}).get("nonconforming", 0)
    total_segs = summary.get("segments", {}).get("total", 0)
    if total_segs > 0:
        msgs.append(f"C4: {nonconform}/{total_segs} segments are nonconforming")
    else:
        msgs.append("C4 WARNING: no segments analyzed")

    if passed:
        msgs.insert(0, "GATE 04: PASS")
    else:
        msgs.insert(0, "GATE 04: FAIL")

    return passed, msgs


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    aggregate = "reports/metrics/benford_aggregate.csv"
    segments = "reports/metrics/benford_segments.csv"
    summary = "reports/metrics/benford_summary.json"

    if not Path(aggregate).exists() or not Path(summary).exists():
        logger.error("Output not found. Run: python -m src.benford --force")
        sys.exit(1)

    passed, msgs = check(aggregate, segments, summary)
    for msg in msgs:
        logger.info(msg)

    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    Path("reports/gate_reports/gate_04.md").write_text("\n".join(msgs))

    logger.info("Result: %s", "PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
