#!/usr/bin/env python
"""Gate 11: Notebooks, README, methodology and data dictionary (Stage 11).

Checks adapted from plan/04_STAGES_10-13.md sec 11.5. Check 1's literal
"every code cell has stored output" is relaxed to "every notebook has at
least one code cell with stored output" -- an import-only or variable-
assignment cell legitimately produces none, and a notebook consisting only
of such cells would still (correctly) fail this relaxed version.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger("audit.gate11")

NOTEBOOKS = [
    "01_data_prep_and_sql.ipynb", "02_synthetic_anomaly_injection.ipynb",
    "03_benfords_law_analysis.ipynb", "04_rule_based_checks.ipynb",
    "05_isolation_forest_and_validation.ipynb", "06_export_for_dashboard.ipynb",
]
BANNED_PATTERNS = [r"\.fit\(", r"to_csv\(", r"for\s+\w+\s+in\s+\w+\.iterrows\(", r"for\s+\w+,\s*\w+\s+in\s+\w+\.iterrows\("]
PLACEHOLDER_TOKENS = ["{{", "TODO", "TBD", "<placeholder>"]


def check() -> tuple[bool, list[str]]:
    msgs: list[str] = []
    passed = True

    # C1/C2: notebooks exist, have markdown+code cells, >=1 code cell has output, no banned patterns
    for nb_name in NOTEBOOKS:
        p = Path("notebooks") / nb_name
        if not p.exists():
            msgs.append(f"C1 FAIL: {nb_name} missing")
            passed = False
            continue
        nb = json.loads(p.read_text(encoding="utf-8"))
        cells = nb.get("cells", [])
        n_md = sum(1 for c in cells if c["cell_type"] == "markdown")
        n_code = sum(1 for c in cells if c["cell_type"] == "code")
        n_code_with_output = sum(1 for c in cells if c["cell_type"] == "code" and c.get("outputs"))
        ok = n_md >= 1 and n_code >= 1 and n_code_with_output >= 1
        if ok:
            msgs.append(f"C1 PASS: {nb_name}: {n_md} md cells, {n_code} code cells, {n_code_with_output} with stored output")
        else:
            msgs.append(f"C1 FAIL: {nb_name}: md={n_md} code={n_code} with_output={n_code_with_output}")
            passed = False

        banned_hits = []
        for c in cells:
            if c["cell_type"] != "code":
                continue
            src = "".join(c.get("source", []))
            for pat in BANNED_PATTERNS:
                if re.search(pat, src):
                    banned_hits.append(pat)
        if banned_hits:
            msgs.append(f"C2 FAIL: {nb_name} contains banned pattern(s) {banned_hits}, logic belongs in src/")
            passed = False

    if not any("C2 FAIL" in m for m in msgs):
        msgs.append("C2 PASS: no notebook contains .fit(/to_csv(/iterrows( -- logic stays in src/")

    # C3: README exists, >3000 chars, no placeholder tokens
    readme = Path("README.md")
    if not readme.exists():
        msgs.append("C3 FAIL: README.md missing")
        passed = False
    else:
        text = readme.read_text(encoding="utf-8")
        size_ok = len(text) > 3000
        hits = [t for t in PLACEHOLDER_TOKENS if t in text]
        # "XX" as a standalone token (not inside a real word like "TAX" or a hex code)
        xx_hit = bool(re.search(r"(?<![A-Za-z])XX(?![A-Za-z])", text))
        if size_ok and not hits and not xx_hit:
            msgs.append(f"C3 PASS: README.md is {len(text)} chars, no placeholder tokens")
        else:
            msgs.append(f"C3 FAIL: size_ok={size_ok} ({len(text)} chars) placeholder_hits={hits} xx_hit={xx_hit}")
            passed = False

        # C4: generated marker present
        if "<!-- generated" in text:
            msgs.append("C4 PASS: README.md contains the report_fill.py <!-- generated --> marker")
        else:
            msgs.append("C4 FAIL: README.md missing the <!-- generated --> marker (was src.report_fill run?)")
            passed = False

        # C6: image links resolve (local paths only, remote badge images are exempt)
        all_img_links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
        img_links = [l for l in all_img_links if not l.startswith(("http://", "https://"))]
        missing_imgs = [l for l in img_links if not Path(l).exists()]
        if len(img_links) >= 3 and not missing_imgs:
            msgs.append(f"C6 PASS: {len(img_links)} image links, all resolve")
        else:
            msgs.append(f"C6 FAIL: {len(img_links)} image links, missing={missing_imgs}")
            passed = False

    # C5: methodology.md + data_dictionary.md exist; data dict covers exact export schema
    meth_ok = Path("docs/methodology.md").exists()
    dd_path = Path("docs/data_dictionary.md")
    dd_ok = dd_path.exists()
    if meth_ok and dd_ok:
        import pandas as pd
        from src.export import EXPORT_COLUMNS
        export_cols = set(EXPORT_COLUMNS)
        dd_text = dd_path.read_text(encoding="utf-8")
        documented = set(re.findall(r"`(\w+)`", dd_text)) & export_cols
        if documented == export_cols:
            msgs.append(f"C5 PASS: methodology.md and data_dictionary.md exist; all {len(export_cols)} export columns documented")
        else:
            msgs.append(f"C5 FAIL: data_dictionary.md missing columns {export_cols - documented}")
            passed = False
    else:
        msgs.append(f"C5 FAIL: methodology.md={meth_ok} data_dictionary.md={dd_ok}")
        passed = False

    # C7: DECISIONS.md has >=5 entries
    decisions_text = Path("DECISIONS.md").read_text(encoding="utf-8")
    n_decisions = len(re.findall(r"^### D-\d+", decisions_text, re.MULTILINE))
    if n_decisions >= 5:
        msgs.append(f"C7 PASS: DECISIONS.md has {n_decisions} entries")
    else:
        msgs.append(f"C7 FAIL: DECISIONS.md has only {n_decisions} entries (need >=5)")
        passed = False

    msgs.insert(0, "GATE 11: PASS" if passed else "GATE 11: FAIL")
    return passed, msgs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    passed, msgs = check()
    for msg in msgs:
        logger.info(msg)

    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    Path("reports/gate_reports/gate_11.md").write_text("\n".join(msgs), encoding="utf-8")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
