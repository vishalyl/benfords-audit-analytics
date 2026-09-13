#!/usr/bin/env python
"""Gate 10: Public web dashboard (Stage 10).

Automated checks per plan/04_STAGES_10-13.md sec 10.8. The live-URL check
(#6) is recorded manually in the gate report since deploying to Streamlit
Community Cloud requires an interactive GitHub OAuth click, see
DECISIONS.md D-0002 for the static-fallback plan that avoids that step.
"""
from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

logger = logging.getLogger("audit.gate10")

APP_PATH = Path("app/streamlit_app.py")
REQ_PATH = Path("app/requirements.txt")
DASHBOARD_DIR = Path("data/dashboard")
SIZE_CAP_BYTES = 25 * 1024 * 1024
BANNED_PACKAGES = {"scikit-learn", "openpyxl", "jupyter"}
BANNED_PATH_LITERALS = ['"data/processed', "'data/processed", '"data/raw', "'data/raw"]


def check() -> tuple[bool, list[str]]:
    msgs: list[str] = []
    passed = True

    # C1: app + requirements exist, plus the static fallback (DECISIONS.md D-0002)
    static_ok = Path("docs/index.html").exists()
    if APP_PATH.exists() and REQ_PATH.exists() and static_ok:
        msgs.append("C1 PASS: app/streamlit_app.py, app/requirements.txt and docs/index.html exist")
    else:
        msgs.append(f"C1 FAIL: app={APP_PATH.exists()} req={REQ_PATH.exists()} static={static_ok}")
        passed = False

    # C2: data/dashboard/ has required files, size < 25MB
    manifest = {p.name: p.stat().st_size for p in DASHBOARD_DIR.glob("*") if p.is_file()}
    total = sum(manifest.values())
    if manifest and total < SIZE_CAP_BYTES:
        msgs.append(f"C2 PASS: data/dashboard/ has {len(manifest)} files, {total/1e6:.2f} MB < 25 MB")
    else:
        msgs.append(f"C2 FAIL: {len(manifest)} files, {total/1e6:.2f} MB")
        passed = False

    # C3: app parses cleanly (syntax) and load_dashboard_data() returns every expected key
    source = APP_PATH.read_text(encoding="utf-8")
    try:
        ast.parse(source)
        msgs.append("C3a PASS: app/streamlit_app.py parses as valid Python")
    except SyntaxError as exc:
        msgs.append(f"C3a FAIL: syntax error {exc}")
        passed = False

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("streamlit_app_smoke", APP_PATH)
        mod = importlib.util.module_from_spec(spec)
        import streamlit as st  # noqa: F401
        spec.loader.exec_module(mod)
        data = mod.load_dashboard_data()
        expected_keys = {"kpi", "model_metrics", "benford_aggregate", "benford_segments",
                         "benford_by_segment_digit", "monthly_trend", "segment_heatmap",
                         "method_comparison", "top_risk_5000", "top_risk_transactions"}
        if expected_keys.issubset(data.keys()):
            msgs.append(f"C3b PASS: load_dashboard_data() returned all {len(expected_keys)} expected keys")
        else:
            msgs.append(f"C3b FAIL: missing keys {expected_keys - set(data.keys())}")
            passed = False
    except Exception as exc:
        msgs.append(f"C3b FAIL: load_dashboard_data() smoke run raised {exc!r}")
        passed = False

    # C4: no reference to processed/ or raw/ data directories
    hits = [lit for lit in BANNED_PATH_LITERALS if lit in source]
    if not hits:
        msgs.append("C4 PASS: no reference to data/processed or data/raw in app source")
    else:
        msgs.append(f"C4 FAIL: found banned path literal(s) {hits}")
        passed = False

    # C5: app/requirements.txt excludes heavy/unneeded packages
    req_text = REQ_PATH.read_text(encoding="utf-8").lower()
    banned_found = [p for p in BANNED_PACKAGES if p in req_text]
    if not banned_found:
        msgs.append("C5 PASS: app/requirements.txt excludes scikit-learn, openpyxl, jupyter")
    else:
        msgs.append(f"C5 FAIL: app/requirements.txt contains {banned_found}")
        passed = False

    # C6: >=3 screenshots of the (locally-run) live app, each >50KB
    shots = [p for p in Path("docs/screenshots").glob("web_*.png") if p.stat().st_size > 50_000]
    if len(shots) >= 3:
        msgs.append(f"C6 PASS: {len(shots)} web_*.png screenshots >50KB")
    else:
        msgs.append(f"C6 FAIL: only {len(shots)} qualifying screenshots")
        passed = False

    msgs.insert(0, "GATE 10: PASS" if passed else "GATE 10: FAIL")
    return passed, msgs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    passed, msgs = check()
    for msg in msgs:
        logger.info(msg)

    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    Path("reports/gate_reports/gate_10.md").write_text("\n".join(msgs), encoding="utf-8")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
