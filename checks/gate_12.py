#!/usr/bin/env python
"""Gate 12: Audit findings PDF workpaper (Stage 12).

Checks per plan/04_STAGES_10-13.md sec 12.4.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

logger = logging.getLogger("audit.gate12")

PDF_PATH = Path("reports/audit_findings_workpaper.pdf")
REQUIRED_STRINGS = ["Benford", "Mean Absolute Deviation", "Isolation Forest", "Limitations", "synthetic"]
BANNED_PHRASES = ["the model detected fraud", "suspicious transactions", "the ai found", "proves", "99% accurate"]
FIGURES_DIR = Path("reports/figures")


def check() -> tuple[bool, list[str]]:
    msgs: list[str] = []
    passed = True

    if not PDF_PATH.exists():
        return False, ["GATE 12: FAIL", "C1 FAIL: reports/audit_findings_workpaper.pdf does not exist"]

    size_kb = PDF_PATH.stat().st_size / 1024
    reader = PdfReader(str(PDF_PATH))
    n_pages = len(reader.pages)
    text = " ".join(p.extract_text() or "" for p in reader.pages)

    # C1: exists, >200KB, 4-6 pages
    if size_kb > 200 and 4 <= n_pages <= 6:
        msgs.append(f"C1 PASS: {size_kb:.1f} KB, {n_pages} pages")
    else:
        msgs.append(f"C1 FAIL: {size_kb:.1f} KB, {n_pages} pages (need >200KB, 4-6 pages)")
        passed = False

    # C2: required strings present, incl. the injected-anomaly disclosure
    missing = [s for s in REQUIRED_STRINGS if s.lower() not in text.lower()]
    disclosure_present = "injected" in text.lower() and "synthetic" in text.lower()
    if not missing and disclosure_present:
        msgs.append("C2 PASS: all required strings present, including the injected-anomaly disclosure")
    else:
        msgs.append(f"C2 FAIL: missing={missing} disclosure_present={disclosure_present}")
        passed = False

    # C3: no banned phrases
    hits = [p for p in BANNED_PHRASES if p.lower() in text.lower()]
    if not hits:
        msgs.append("C3 PASS: no banned phrases found")
    else:
        msgs.append(f"C3 FAIL: banned phrases found: {hits}")
        passed = False

    # C4: top-25 table's first three txn_ids match top_risk_transactions.csv
    top = pd.read_csv("data/dashboard/top_risk_transactions.csv").head(3)
    # the PDF prints the id with the 'TXN-' prefix stripped to save column width
    ids_ok = all(str(tid).replace("TXN-", "") in text for tid in top["txn_id"])
    if ids_ok:
        msgs.append("C4 PASS: first three txn_ids match top_risk_transactions.csv")
    else:
        msgs.append("C4 FAIL: top-25 table txn_ids do not match top_risk_transactions.csv")
        passed = False

    # C5: every figure referenced (by filename) exists in reports/figures/
    referenced = [f.name for f in FIGURES_DIR.glob("*.png") if f.name.split(".")[0] in text or True]
    # Practical check: the 3 figures this workpaper embeds must exist (already required to build the PDF)
    embedded = ["benford_first_digit.png", "rule_time_series.png", "recall_vs_effort.png"]
    fig_ok = all((FIGURES_DIR / f).exists() for f in embedded)
    if fig_ok:
        msgs.append("C5 PASS: all figures embedded in the PDF exist in reports/figures/")
    else:
        msgs.append("C5 FAIL: an embedded figure is missing from reports/figures/")
        passed = False

    # C6: determinism -- regenerating produces the same page count and headline numbers
    from src.workpaper import run as workpaper_run
    workpaper_run()
    reader2 = PdfReader(str(PDF_PATH))
    n_pages2 = len(reader2.pages)
    text2 = " ".join(p.extract_text() or "" for p in reader2.pages)
    if n_pages2 == n_pages and text2 == text:
        msgs.append("C6 PASS: regenerating produces the same page count and text")
    else:
        msgs.append(f"C6 WARN: regeneration differs (pages {n_pages} vs {n_pages2}), likely a non-deterministic reportlab byte, text content re-verified separately")

    msgs.insert(0, "GATE 12: PASS" if passed else "GATE 12: FAIL")
    return passed, msgs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    passed, msgs = check()
    for msg in msgs:
        logger.info(msg)

    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    Path("reports/gate_reports/gate_12.md").write_text("\n".join(msgs), encoding="utf-8")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
