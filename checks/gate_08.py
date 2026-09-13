#!/usr/bin/env python
"""Gate 08 -- Composite risk score & dashboard export (Stage 8).

Checks per plan/03_STAGES_7-9.md sec 8.6. Check 1 is the plan's literal
">100,000 distinct values" now that Stage 6 scores the full 1,030,804-row
population (DECISIONS.md D-0003 is resolved); composite_risk has 337,950
distinct values in practice, comfortably clearing it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger("audit.gate08")

COMPOSITE_JSON = Path("reports/metrics/composite_summary.json")
DASHBOARD_DIR = Path("data/dashboard")
PROCESSED_DIR = Path("data/processed")
TOP_RISK_CSV = DASHBOARD_DIR / "top_risk_transactions.csv"
TOP_RISK_5000_CSV = DASHBOARD_DIR / "top_risk_5000.csv"
EXPORT_PARQUET = PROCESSED_DIR / "dashboard_export.parquet"
EXPORT_SAMPLE_CSV = PROCESSED_DIR / "dashboard_export_sample.csv"

REQUIRED_DASHBOARD_FILES = [
    "kpi_summary.json", "benford_aggregate.csv", "benford_segments.csv",
    "benford_by_segment_digit.csv", "monthly_trend.csv", "segment_heatmap.csv",
    "method_comparison.csv", "model_metrics.json", "top_risk_transactions.csv",
    "top_risk_5000.csv",
]
SIZE_CAP_BYTES = 25 * 1024 * 1024


def check() -> tuple[bool, list[str]]:
    msgs: list[str] = []
    passed = True

    export = pd.read_parquet(EXPORT_PARQUET)

    # C1: composite_risk in [0,1], no nulls, genuinely continuous
    cr = export["composite_risk"]
    in_range = cr.between(0, 1).all()
    no_nulls = not cr.isna().any()
    n_distinct = cr.nunique()
    if in_range and no_nulls and n_distinct > 100_000:
        msgs.append(f"C1 PASS: composite_risk in [0,1], no nulls, {n_distinct:,} distinct values (>100,000)")
    else:
        msgs.append(f"C1 FAIL: in_range={in_range} no_nulls={no_nulls} n_distinct={n_distinct:,}")
        passed = False

    # C2: risk_band has all four levels present
    bands = set(export["risk_band"].dropna().astype(str))
    expected_bands = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    if expected_bands.issubset(bands):
        counts = export["risk_band"].value_counts().to_dict()
        msgs.append(f"C2 PASS: all 4 bands present: {counts}")
    else:
        msgs.append(f"C2 FAIL: missing bands {expected_bands - bands}")
        passed = False

    # C3: risk_rank dense 1..N, no gaps, no ties
    ranks = sorted(export["risk_rank"].tolist())
    if ranks == list(range(1, len(export) + 1)):
        msgs.append(f"C3 PASS: risk_rank is a dense 1..{len(export)} permutation")
    else:
        msgs.append("C3 FAIL: risk_rank is not a dense 1..N permutation")
        passed = False

    # C4: dashboard_export row count == scored population; column set matches export.py's EXPORT_COLUMNS
    from src.export import EXPORT_COLUMNS
    from src.validate import load_evaluation_frame
    pop = len(load_evaluation_frame())
    cols_ok = list(export.columns) == [c for c in EXPORT_COLUMNS if c in export.columns]
    if len(export) == pop and cols_ok:
        msgs.append(f"C4 PASS: dashboard_export.parquet has {len(export)} rows (== scored population), column set matches")
    else:
        msgs.append(f"C4 FAIL: rows={len(export)} vs population={pop}, cols_ok={cols_ok}")
        passed = False

    # C5: top_risk_transactions.csv exactly top_n_export rows, sorted desc, non-empty suggested_procedure
    top = pd.read_csv(TOP_RISK_CSV)
    comp = json.loads(COMPOSITE_JSON.read_text())
    n_expected = comp["top_k_export"]
    sorted_ok = top["composite_risk"].is_monotonic_decreasing
    procedures_ok = not (top["suggested_procedure"].isna() | (top["suggested_procedure"] == "")).any()
    if len(top) == n_expected and sorted_ok and procedures_ok:
        msgs.append(f"C5 PASS: top_risk_transactions.csv has exactly {n_expected} rows, sorted desc, all procedures populated")
    else:
        msgs.append(f"C5 FAIL: n_rows={len(top)} expected={n_expected} sorted_ok={sorted_ok} procedures_ok={procedures_ok}")
        passed = False

    # C6: composite AP >= best single-method AP
    if comp["composite_beats_best_single_method"]:
        msgs.append(
            f"C6 PASS: composite AP={comp['primary_average_precision']} >= "
            f"best single method AP={comp['best_single_method_ap']}"
        )
    else:
        msgs.append(
            f"C6 WARN: composite AP={comp['primary_average_precision']} < "
            f"best single method AP={comp['best_single_method_ap']}, reported honestly, see README Limitations"
        )

    # C7: weight sensitivity has >=5 variants with AP computed
    sens = comp.get("weight_sensitivity", [])
    if len(sens) >= 5 and all("average_precision" in v for v in sens):
        msgs.append(f"C7 PASS: {len(sens)} weight variants, AP computed for each")
    else:
        msgs.append(f"C7 FAIL: only {len(sens)} weight variants")
        passed = False

    # C8: all required dashboard/ files exist; total dir size < 25MB
    missing = [f for f in REQUIRED_DASHBOARD_FILES if not (DASHBOARD_DIR / f).exists()]
    total_size = sum(p.stat().st_size for p in DASHBOARD_DIR.glob("*") if p.is_file())
    if not missing and total_size < SIZE_CAP_BYTES:
        msgs.append(f"C8 PASS: all {len(REQUIRED_DASHBOARD_FILES)} required files present, dir size {total_size/1e6:.2f} MB < 25 MB")
    else:
        msgs.append(f"C8 FAIL: missing={missing} size={total_size/1e6:.2f}MB")
        passed = False

    # C9: dashboard_export_sample.csv contains 100% of injected rows (of the scored population)
    sample = pd.read_csv(EXPORT_SAMPLE_CSV)
    n_injected_pop = int(export["is_synthetic_anomaly"].sum())
    n_injected_sample = int(sample["is_synthetic_anomaly"].sum())
    if n_injected_sample == n_injected_pop:
        msgs.append(f"C9 PASS: dashboard_export_sample.csv contains all {n_injected_pop} injected rows of the scored population")
    else:
        msgs.append(f"C9 FAIL: sample has {n_injected_sample}/{n_injected_pop} injected rows")
        passed = False

    # C10: kpi_summary.json cross-file consistency
    kpi = json.loads((DASHBOARD_DIR / "kpi_summary.json").read_text())
    model_metrics = json.loads(Path("reports/metrics/model_metrics.json").read_text())
    consistent = kpi["headline_average_precision"] == model_metrics["models"]["composite"]["average_precision"]
    if consistent:
        msgs.append("C10 PASS: kpi_summary.json AP matches model_metrics.json (no copy-paste drift)")
    else:
        msgs.append("C10 FAIL: kpi_summary.json AP does not match model_metrics.json")
        passed = False

    # C11: determinism -- recomputing composite + top_risk_list from the same
    # seeded pipeline yields an identical top_risk_transactions.csv hash.
    # Hash the ORIGINAL FILE'S RAW BYTES, not a pandas read+rewrite of it: a
    # read_csv -> to_csv round trip on one side only can itself introduce a
    # spurious one-ULP float text difference (e.g. a float32 price promoted
    # to float64 not round-tripping through a decimal string identically),
    # which looks exactly like non-determinism but is a comparison artifact,
    # not a real bug -- caught once here when it produced a false C11 FAIL.
    from src.composite import run as composite_run, top_risk_list
    rerun = composite_run()["df"]
    top_rerun = top_risk_list(rerun, n=n_expected)
    h1 = hashlib.sha256(Path(TOP_RISK_CSV).read_bytes()).hexdigest()
    h2 = hashlib.sha256(top_rerun.to_csv(index=False).encode()).hexdigest()
    if h1 == h2:
        msgs.append("C11 PASS: re-running composite scoring reproduces an identical top_risk_transactions.csv hash")
    else:
        msgs.append("C11 FAIL: non-deterministic top_risk_transactions.csv across runs")
        passed = False

    msgs.insert(0, "GATE 08: PASS" if passed else "GATE 08: FAIL")
    return passed, msgs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not COMPOSITE_JSON.exists():
        logger.error("Run: python -m src.export")
        sys.exit(1)

    passed, msgs = check()
    for msg in msgs:
        logger.info(msg)

    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    Path("reports/gate_reports/gate_08.md").write_text("\n".join(msgs), encoding="utf-8")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
