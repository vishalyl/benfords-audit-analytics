# Gate 12 — Audit Findings PDF Workpaper

**Stage:** 12 · **Date:** 2026-09-13 · **Gate:** `checks/gate_12.py` → **PASS**

## Output

`reports/audit_findings_workpaper.pdf` — 268.6 KB, **6 pages**, built programmatically
with `src/workpaper.py` (reportlab platypus) so it regenerates from `reports/metrics/*`
and `data/dashboard/*` whenever the pipeline reruns — check 6 confirms byte-identical
regeneration (same page count, same extracted text).

## Structure (plan sec 12.1)

1. Executive summary — objective, scope, procedures, summary-of-findings table, worded conclusion
2. Scope, data and limitations — population reconciliation table, data reliability, synthetic-anomaly disclosure, limitations list
3. Digit-distribution analysis — method, aggregate result + figure, excess-power note, top-5 nonconforming segments table
4. Rule-based exception testing — all 10 rules with audit rationale and exception counts, activity-over-time figure
5. Statistical outlier analysis — plain-English IF description, validation results, the method x anomaly-type matrix, recall-vs-effort figure
6. Schedule of items for review — top 25 transactions with `suggested_procedure`, sign-off block

Header block (engagement name, Prepared by/Date/Reviewed by, workpaper ref `AA-BEN-01`)
and a "Page X of Y" footer appear on every page.

## Tone rules

Every finding follows Criteria/Condition/Cause/Effect/Recommendation where practical.
None of the banned phrases (§12.2) appear anywhere in the extracted text: "the model
detected fraud", "suspicious transactions", "the AI found", "proves", "99% accurate".
The conclusion uses the plan's own worded template almost verbatim: *"Analytical
procedures identified N transactions... exhibiting characteristics consistent with the
risk indicators tested. These results are indicators for targeted testing and do not,
of themselves, evidence misstatement or fraud."*

## A build bug caught and fixed during this stage

The first draft of `NumberedCanvas` (the "page X of Y" footer helper) called the base
`Canvas.showPage()` twice per page — once inside the overridden `showPage()` and once
again in `save()` — which silently duplicated the entire document (14 pages instead of
6, with an identical page 8 following page 7). Fixed by replacing the first call with
`self._startPage()` (buffer the page without flushing it), per the standard reportlab
recipe. Caught by simply counting pages before finalizing — a reminder that reportlab's
"page X of Y" pattern is easy to get subtly wrong.

## Gate check log

```
GATE 12: PASS
C1 PASS: 268.6 KB, 6 pages
C2 PASS: all required strings present, including the injected-anomaly disclosure
C3 PASS: no banned phrases found
C4 PASS: first three txn_ids match top_risk_transactions.csv
C5 PASS: all figures embedded in the PDF exist in reports/figures/
C6 PASS: regenerating produces the same page count and text
```

**GATE: PASS**
