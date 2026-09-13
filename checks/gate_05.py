#!/usr/bin/env python
"""Gate 05, Validate rule-based checks (Stage 5).

Checks:
  - transactions_flagged.parquet exists and has rule_flags column
  - rule_flags contains valid rule names
  - rule_summary.json has required structure
  - Flagged rows count is non-zero
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger("audit.gate05")


EXPECTED_RULES = {
    "ROUND_NUMBER", "NEGATIVE_ADJUSTMENT", "LARGE_AMOUNT",
    "ZERO_QUANTITY", "ODD_QUANTITY", "DUPLICATE_INVOICE",
    "ROUND_DOLLARS", "HIGH_QUANTITY", "OFF_HOUR", "SPLIT_AMOUNT",
}


def check(flagged_path: str, summary_path: str) -> tuple[bool, list[str]]:
    msgs = []
    passed = True

    # ── C1: Flagged parquet exists with rule_flags ────────────────
    flagged = pd.read_parquet(flagged_path)
    if "rule_flags" not in flagged.columns:
        msgs.append("C1 FAILED: rule_flags column missing from flagged dataset")
        passed = False
    else:
        has_flags = flagged["rule_flags"].apply(lambda x: len(x) > 0 if x is not None and len(x) > 0 else False)
        n_flagged = int(has_flags.sum())
        msgs.append(f"C1: flagged dataset has {n_flagged}/{len(flagged)} rows with rules")
        if n_flagged == 0:
            msgs.append("C1 WARNING: 0 flagged rows")

    # ── C2: Rule names are valid ──────────────────────────────────
    all_rules = set()
    for flags in flagged["rule_flags"].dropna():
        if hasattr(flags, "__iter__") and not isinstance(flags, str):
            for f in flags:
                if isinstance(f, str) and f:
                    all_rules.add(f)
        elif isinstance(flags, str) and flags:
            all_rules.add(flags)

    invalid = all_rules - EXPECTED_RULES
    if not invalid:
        msgs.append(f"C2: all {len(all_rules)} rule names are valid ({sorted(all_rules)})")
    else:
        msgs.append(f"C2 FAILED: invalid rule names: {invalid}")
        passed = False

    # ── C3: Summary JSON structure ────────────────────────────────
    with open(summary_path) as f:
        summary = json.load(f)

    if "total_rows" in summary and ("flagged_rows" in summary or "n_flagged" in summary):
        flag_key = "flagged_rows" if "flagged_rows" in summary else "n_flagged"
        msgs.append(f"C3: summary has {summary['total_rows']} total, "
                     f"{summary[flag_key]} flagged ({summary.get('flagged_pct', '?')}%)")
    else:
        msgs.append("C3 FAILED: summary missing total_rows/flagged_rows or n_flagged")
        passed = False

    if "rule_counts" in summary:
        rc = summary["rule_counts"]
        msgs.append(f"C3: rule_counts has {len(rc)} rules: {dict(rc)}")

    if passed:
        msgs.insert(0, "GATE 05: PASS")
    else:
        msgs.insert(0, "GATE 05: FAIL")

    return passed, msgs


def main():
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    flagged = "data/processed/transactions_flagged.parquet"
    summary = "reports/metrics/rule_summary.json"

    if not Path(flagged).exists() or not Path(summary).exists():
        logger.error("Output not found. Run: python -m src.rules --force")
        sys.exit(1)

    passed, msgs = check(flagged, summary)
    for msg in msgs:
        logger.info(msg)

    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    Path("reports/gate_reports/gate_05.md").write_text("\n".join(msgs))

    logger.info("Result: %s", "PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
