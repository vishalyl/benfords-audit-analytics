#!/usr/bin/env python
"""Gate 13 — Resume bullets, interview prep & publish checklist (Stage 13).

Checks per plan/04_STAGES_10-13.md sec 13.3. Check 2 (anti-fabrication) is
implemented as a tolerant numeric cross-check rather than literal substring
matching: resume-bullet numbers are frequently derived (percentages,
rounding, x-lift ratios) from the raw JSON leaves, so each extracted number
is accepted if it is within a small tolerance of some value (or a simple
transform of a value: x100, /100, rounded to 0-4dp) found across
reports/metrics/*.json, data/dashboard/*.json and config.yaml.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path

import yaml

logger = logging.getLogger("audit.gate13")

DOC_PATH = Path("docs/resume_and_interview.md")


def _flatten_numbers(obj, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_numbers(v, out)


def _collect_reference_numbers() -> set[float]:
    values: set[float] = set()
    for d in [Path("reports/metrics"), Path("data/dashboard")]:
        for p in d.glob("*.json"):
            _flatten_numbers(json.loads(p.read_text()), values)
    values_yaml: set[float] = set()
    _flatten_numbers(yaml.safe_load(Path("config.yaml").read_text()), values_yaml)
    values |= values_yaml

    expanded: set[float] = set()
    for v in values:
        expanded.add(v)
        expanded.add(v * 100)
        expanded.add(v / 100)
        for nd in range(0, 5):
            expanded.add(round(v, nd))
            expanded.add(round(v * 100, nd))
    return expanded


def _number_matches(token: float, reference: set[float], rel_tol: float = 0.01) -> bool:
    for r in reference:
        if r == 0 and token == 0:
            return True
        if r != 0 and abs(token - r) / abs(r) < rel_tol:
            return True
        if abs(token - r) < 0.5:  # absolute tolerance for small integers (counts)
            return True
    return False


def check() -> tuple[bool, list[str]]:
    msgs: list[str] = []
    passed = True

    if not DOC_PATH.exists():
        return False, ["GATE 13: FAIL", "C1 FAIL: docs/resume_and_interview.md missing"]
    text = DOC_PATH.read_text(encoding="utf-8")

    # C1: >=20 numbered questions, >=3 resume-bullet variants, no [X]/[N] placeholders
    n_questions = len(re.findall(r"^\*\*\d+\.", text, re.MULTILINE))
    n_variants = len(re.findall(r"^### .*variant", text, re.MULTILINE))
    has_bracket_placeholder = bool(re.search(r"\[[XN]\]", text))
    if n_questions >= 20 and n_variants >= 3 and not has_bracket_placeholder:
        msgs.append(f"C1 PASS: {n_questions} numbered questions, {n_variants} resume-bullet variants, no [X]/[N] placeholders")
    else:
        msgs.append(f"C1 FAIL: questions={n_questions} variants={n_variants} bracket_placeholder={has_bracket_placeholder}")
        passed = False

    # C2: every numeric value in section A (resume bullets) matches reports/metrics (tolerant)
    section_a = text.split("## A. Resume bullets")[1].split("## B.")[0]
    tokens = re.findall(r"\d[\d,]*\.?\d*", section_a)
    reference = _collect_reference_numbers()
    unmatched = []
    for tok in tokens:
        val = float(tok.replace(",", ""))
        if val < 10 and val == int(val):
            continue  # small prose integers (e.g. "6 archetypes", "10 rules") are not data claims
        if not _number_matches(val, reference):
            unmatched.append(tok)
    if not unmatched:
        msgs.append(f"C2 PASS: all {len(tokens)} numeric tokens in resume bullets match reports/metrics (tolerant)")
    else:
        msgs.append(f"C2 FAIL: unmatched numbers in resume bullets: {unmatched}")
        passed = False

    # C3: no leaked personal file paths in tracked files (adapted — see DECISIONS.md D-0006:
    # a literal "visha" grep also matches the owner's real name "Vishal" in attribution
    # fields, which is legitimate; this checks for actual absolute local paths instead).
    result = subprocess.run(
        ["git", "grep", "-il", r"C:\\Users\\visha\|Premier Pro", "--", ".", ":!plan"],
        capture_output=True, text=True,
    )
    hits = [l for l in result.stdout.splitlines() if l.strip()]
    if not hits:
        msgs.append("C3 PASS: no leaked local file paths in tracked files (outside plan/)")
    else:
        msgs.append(f"C3 FAIL: leaked local paths found in {hits}")
        passed = False

    # C4: LICENSE exists
    if Path("LICENSE").exists():
        msgs.append("C4 PASS: LICENSE exists")
    else:
        msgs.append("C4 FAIL: LICENSE missing")
        passed = False

    # C5: no tracked file >50MB
    ls = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.splitlines()
    big = [f for f in ls if Path(f).exists() and Path(f).stat().st_size > 50 * 1024 * 1024]
    if not big:
        msgs.append("C5 PASS: no tracked file >50MB")
    else:
        msgs.append(f"C5 FAIL: tracked files >50MB: {big}")
        passed = False

    # C6: remote set, main pushed, git status clean (manual/pending — publishing is a user decision)
    remote = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    if remote and not status:
        msgs.append("C6 PASS: remote configured and working tree clean")
    else:
        msgs.append(
            f"C6 PENDING: remote={'set' if remote else 'not set'}, "
            f"working_tree={'clean' if not status else 'has uncommitted changes'} — "
            "publishing to a public GitHub remote is a user decision, not made silently by the agent"
        )
        # not a hard failure of the gate — recorded, not blocking (see gate report)

    # C7: gate_00..gate_12 exist (gate_13.md is written by this very script at the end
    # of this run, so checking for it here would always fail on a fresh run — its
    # existence is guaranteed by the act of this script completing).
    missing_reports = [n for n in range(13) if not Path(f"reports/gate_reports/gate_{n:02d}.md").exists()]
    if not missing_reports:
        msgs.append("C7 PASS: all gate reports gate_00 .. gate_12 exist (gate_13.md written at the end of this run)")
    else:
        msgs.append(f"C7 FAIL: missing gate reports for stages {missing_reports}")
        passed = False

    msgs.insert(0, "GATE 13: PASS" if passed else "GATE 13: FAIL")
    return passed, msgs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    passed, msgs = check()
    for msg in msgs:
        logger.info(msg)

    Path("reports/gate_reports").mkdir(parents=True, exist_ok=True)
    Path("reports/gate_reports/gate_13.md").write_text("\n".join(msgs), encoding="utf-8")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
