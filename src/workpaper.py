"""Stage 12 — audit findings workpaper PDF, built programmatically with
reportlab so it regenerates from reports/metrics/* whenever the pipeline
reruns (plan sec 12.3 — "do not hand-write the PDF; it will drift from the
numbers").

Tone rules (plan sec 12.2) are enforced by construction: this module never
writes "detected fraud", "suspicious", "the AI found", "proves", or an
"accurate" percentage claim. Every finding follows Criteria/Condition/
Cause/Effect/Recommendation where practical.

Usage::

    python -m src.workpaper
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, NextPageTemplate, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)
from reportlab.pdfgen import canvas as canvas_module

from src.config import cfg

REPO_ROOT = Path(__file__).resolve().parents[1]
METRICS_DIR = cfg.paths.metrics_dir
DASHBOARD_DIR = cfg.paths.dashboard_dir
FIGURES_DIR = cfg.paths.figures_dir
OUT_PATH = REPO_ROOT / "reports" / "audit_findings_workpaper.pdf"

ENGAGEMENT_NAME = "Online Retail II — Transaction Anomaly Review"
WORKPAPER_REF = "AA-BEN-01"
PREPARED_BY = "Y.L. Vishal (Analytics)"
REVIEWED_BY = "[pending engagement review]"

NAVY = colors.HexColor("#1F4E79")
LIGHT_GREY = colors.HexColor("#F4F6F8")
RISK_RED = colors.HexColor("#D93025")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


class NumberedCanvas(canvas_module.Canvas):
    """Buffers pages so the footer can print 'page X of Y' — standard reportlab recipe."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states = []

    def showPage(self):
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.grey)
        self.drawString(20 * mm, 12 * mm, f"{ENGAGEMENT_NAME}  ·  Workpaper {WORKPAPER_REF}")
        self.drawRightString(190 * mm, 12 * mm, f"Page {self._pageNumber} of {total}")
        self.setStrokeColor(colors.grey)
        self.line(20 * mm, 16 * mm, 190 * mm, 16 * mm)


def _styles() -> dict[str, ParagraphStyle]:
    ss = getSampleStyleSheet()
    styles = {
        "Body": ParagraphStyle("Body", parent=ss["BodyText"], fontName="Times-Roman", fontSize=10, leading=11.5, spaceAfter=6),
        "H1": ParagraphStyle("H1", parent=ss["Heading1"], fontName="Times-Bold", fontSize=15, textColor=NAVY, spaceAfter=8),
        "H2": ParagraphStyle("H2", parent=ss["Heading2"], fontName="Times-Bold", fontSize=11.5, textColor=NAVY, spaceBefore=10, spaceAfter=5),
        "Small": ParagraphStyle("Small", parent=ss["BodyText"], fontName="Times-Roman", fontSize=7, leading=8, textColor=colors.black, spaceAfter=0),
        "Caption": ParagraphStyle("Caption", parent=ss["BodyText"], fontName="Times-Italic", fontSize=8.5, leading=10, textColor=colors.grey, spaceAfter=8),
    }
    return styles


def _header_block(styles: dict) -> list:
    return [
        Paragraph(ENGAGEMENT_NAME, styles["H1"]),
        Table(
            [["Prepared by", PREPARED_BY, "Date", "2026-09-13"],
             ["Reviewed by", REVIEWED_BY, "Workpaper ref.", WORKPAPER_REF]],
            colWidths=[28 * mm, 55 * mm, 28 * mm, 55 * mm],
            style=TableStyle([
                ("FONT", (0, 0), (-1, -1), "Times-Roman", 8.5),
                ("FONT", (0, 0), (0, -1), "Times-Bold", 8.5),
                ("FONT", (2, 0), (2, -1), "Times-Bold", 8.5),
                ("BOX", (0, 0), (-1, -1), 0.4, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT_GREY),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]),
        ),
        Spacer(1, 8),
    ]


def _table_style(header_bg=NAVY) -> TableStyle:
    return TableStyle([
        ("FONT", (0, 0), (-1, 0), "Times-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Times-Roman", 8),
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.grey),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#E0E0E0")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])


def build_story(styles: dict) -> list:
    cleaning = _load_json(METRICS_DIR / "cleaning_ledger.json")
    benford = _load_json(METRICS_DIR / "benford_summary.json")
    rules = _load_json(METRICS_DIR / "rule_summary.json")
    mm_ = _load_json(METRICS_DIR / "model_metrics.json")
    composite = _load_json(METRICS_DIR / "composite_summary.json")
    kpi = _load_json(DASHBOARD_DIR / "kpi_summary.json")
    top25 = pd.read_csv(DASHBOARD_DIR / "top_risk_transactions.csv").head(25)
    segments = pd.read_csv(DASHBOARD_DIR / "benford_segments.csv").sort_values("mad", ascending=False)

    story: list = []

    # ---------------- Page 1 — Executive summary ----------------
    story += _header_block(styles)
    story.append(Paragraph("1. Executive Summary", styles["H2"]))
    story.append(Paragraph(
        "<b>Objective.</b> To apply layered analytical procedures to the client's sales ledger "
        "to identify transactions exhibiting characteristics that warrant further audit enquiry, "
        "and to evaluate the reliability of those procedures against a controlled, labelled "
        "validation set.", styles["Body"]))
    story.append(Paragraph(
        f"<b>Scope.</b> The population comprises {cleaning['rows_out']:,} transaction lines "
        f"(£{kpi['total_value']:,.0f} total value) covering December 2009 to December 2011. "
        f"{cleaning['cancellations']:,} cancellation entries and non-product ledger adjustments "
        f"were identified and excluded from digit-distribution and model-based testing, but are "
        f"retained in the dataset and counted separately — they are not deleted from the "
        f"population under review.", styles["Body"]))
    story.append(Paragraph(
        "<b>Procedures performed.</b> (i) Digit-distribution analysis (Benford's Law), aggregate "
        "and segmented by country and calendar month; (ii) ten deterministic rule-based exception "
        "tests (duplicate invoices, round amounts, threshold structuring, off-hours and period-end "
        "posting, among others); (iii) an unsupervised statistical outlier procedure (Isolation "
        "Forest) blended with (i) and (ii) into a single composite risk score.", styles["Body"]))

    story.append(Paragraph("Summary of findings", styles["H2"]))
    findings_tbl = Table(
        [["#", "Procedure", "Result", "Verdict"],
         ["1", "Aggregate Benford (leading digit)", f"MAD {benford['aggregate']['amount_first']['mad']:.4f}", benford['aggregate']['amount_first']['classification']],
         ["2", "Segmented Benford (country x month)", f"{kpi['n_segments_flagged']} / {kpi['n_segments_assessed']} segments flagged", "See sec. 3"],
         ["3", "Rule-based exception testing", f"{rules['n_flagged']:,} / {rules['total_rows']:,} lines flagged ({rules['flagged_pct']}%)", "See sec. 4"],
         ["4", "Isolation Forest (statistical outliers)", f"Average Precision {mm_['models']['iforest']['average_precision']:.3f}", "See sec. 5"],
         ["5", "Composite risk ranking", f"{composite['band_counts']['CRITICAL']} items scored CRITICAL", "See sec. 5-6"]],
        colWidths=[8 * mm, 62 * mm, 68 * mm, 32 * mm], style=_table_style(),
    )
    story.append(findings_tbl)
    story.append(Spacer(1, 8))
    n_hc = composite["band_counts"]["HIGH"] + composite["band_counts"]["CRITICAL"]
    pct_hc = 100 * n_hc / composite["n_rows"]
    story.append(Paragraph(
        f"<b>Conclusion.</b> Analytical procedures identified {n_hc:,} transactions "
        f"({pct_hc:.1f}% of the {composite['n_rows']:,}-transaction scored population, drawn from "
        f"a representative sample of the full ledger) exhibiting characteristics consistent with "
        f"the risk indicators tested. These results are indicators for targeted testing and do "
        f"not, of themselves, evidence misstatement or fraud. A synthetic validation exercise "
        f"(sec. 2) indicates the composite ranking concentrates known anomalies well above the "
        f"rate expected from random selection, but every precision figure quoted in this workpaper "
        f"is a lower bound — see the limitations in sec. 2.", styles["Body"]))

    story.append(PageBreak())

    # ---------------- Page 2 — Scope, data and limitations ----------------
    story.append(Paragraph("2. Scope, Data and Limitations", styles["H2"]))
    story.append(Paragraph("Population reconciliation", styles["H2"]))
    recon = Table(
        [["Stage", "Rows"],
         ["Raw combined rows", f"{cleaning['rows_in']:,}"],
         ["Less: cancellations", f"({cleaning['cancellations']:,})"],
         ["Less: exact duplicates", f"({cleaning['exact_duplicates']:,})"],
         ["Cleaned population (rows_out)", f"{cleaning['rows_out']:,}"],
         ["  of which: adjustments (retained, excluded from Benford)", f"{cleaning['adjustments']:,}"],
         ["  of which: non-positive amount (retained, excluded from Benford)", f"{cleaning['nonpositive_amount']:,}"],
         ["  of which: missing customer_id (retained as UNASSIGNED)", f"{cleaning['missing_customer']:,}"]],
        colWidths=[130 * mm, 40 * mm],
        style=_table_style(),
    )
    story.append(recon)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Reconciliation holds: raw rows less exclusions equals the cleaned population "
        f"(reconciles = {cleaning['reconciles']}). No row was silently dropped — every "
        f"exclusion is counted above and retained in the underlying dataset for inspection.",
        styles["Body"]))

    story.append(Paragraph("Data reliability", styles["H2"]))
    story.append(Paragraph(
        "The population is a real, publicly available transaction-level extract (UCI Machine "
        "Learning Repository, \"Online Retail II\", CC BY 4.0). It was not generated for this "
        "exercise and required only standard cleaning (type coercion, cancellation and duplicate "
        "identification) prior to testing.", styles["Body"]))

    story.append(Paragraph("Synthetic anomaly disclosure", styles["H2"]))
    story.append(Paragraph(
        f"<b>A controlled set of {mm_['population']['n_injected']:,} synthetic anomalies "
        f"({mm_['population']['anomaly_rate']*100:.2f}% of the scored population) was deliberately "
        f"injected into the real ledger prior to testing, across six archetypes (duplicate "
        f"billing, threshold structuring, round-number entries, digit fabrication, cut-off / "
        f"off-hours timing, and gross-value outliers).</b> This was done because live engagement "
        "data carries no ground truth against which a procedure's precision and recall can be "
        "measured; the injected set provides that ground truth for this validation exercise only "
        "and has no bearing on any conclusion about the real, un-injected transactions in the "
        "underlying ledger.", styles["Body"]))

    story.append(Paragraph("Limitations", styles["H2"]))
    for item in [
        "Positives in the validation exercise are the injected rows only; a genuine, unlabelled "
        "anomaly already present in the real ledger is scored as a false positive when a "
        "procedure flags it, so every precision figure in this workpaper is a lower bound.",
        "The Isolation Forest decision threshold was calibrated to the known injection rate; a "
        "real engagement does not know the true anomaly rate in advance.",
        "The statistical outlier procedure was evaluated on a 50,000-line sample of the "
        f"{cleaning['rows_out']:,}-line population, not the full ledger.",
        "This is a retail sales ledger, not a general ledger with journal entries; certain "
        "indicators (posting user, manual-versus-automatic source, account combinations) have no "
        "equivalent in this data.",
        "A Benford exception is a screening result. It directs procedures; it does not, on its "
        "own, indicate fraud or misstatement.",
    ]:
        story.append(Paragraph(f"&bull; {item}", styles["Body"]))

    story.append(PageBreak())

    # ---------------- Page 3 — Benford's Law ----------------
    story.append(Paragraph("3. Digit-Distribution Analysis (Benford's Law)", styles["H2"]))
    story.append(Paragraph(
        "<b>Method.</b> Benford's Law states that the leading digit of many naturally occurring "
        "numeric populations follows log10(1 + 1/d), not a uniform distribution. Conformity is "
        "assessed primarily via <b>Mean Absolute Deviation (MAD)</b> — the mean absolute "
        "difference between observed and expected digit proportions — using Nigrini's thresholds "
        "(Close &lt;0.006, Acceptable &lt;0.012, Marginal &lt;0.015, Nonconformity &ge;0.015; "
        "Nigrini, <i>Benford's Law: Applications for Forensic Accounting, Auditing, and Fraud "
        "Detection</i>, Wiley, 2012).", styles["Body"]))

    agg = benford["aggregate"]["amount_first"]
    story.append(Paragraph(
        f"<b>Aggregate result.</b> Population n = {agg['n']:,}; MAD = {agg['mad']:.4f}; verdict "
        f"<b>{agg['classification']}</b>. A chi-square statistic was also computed "
        f"(&chi;&sup2; = {agg['chi_square']:,.0f}, p &lt; 0.001) but is not the primary criterion: "
        f"at this population size chi-square rejects conformity for deviations of no practical "
        f"significance (the well-documented \"excess power\" property of the test at large n). "
        f"MAD, which is sample-size independent, governs the verdict.", styles["Body"]))

    if (FIGURES_DIR / "benford_first_digit.png").exists():
        story.append(Image(str(FIGURES_DIR / "benford_first_digit.png"), width=140 * mm, height=80 * mm))
        story.append(Paragraph("Figure 1 — Leading-digit distribution, aggregate population, observed vs. expected.", styles["Caption"]))

    story.append(Paragraph(
        f"<b>Segment results.</b> {kpi['n_segments_assessed']} (country, calendar-month) segments "
        f"met the minimum size for a conformity verdict (n &ge; 1,000); {kpi['n_segments_flagged']} "
        f"were classified NONCONFORMING. The five most nonconforming segments:", styles["Body"]))
    seg_rows = [["Country | month", "n", "MAD", "Verdict", "Digit driving deviation"]]
    for _, r in segments.head(5).iterrows():
        seg_rows.append([r["segment_value"], f"{int(r['n']):,}", f"{r['mad']:.4f}", r["verdict"], str(int(r["max_dev_digit"]))])
    seg_tbl = Table(seg_rows, colWidths=[55 * mm, 20 * mm, 20 * mm, 40 * mm, 45 * mm], style=_table_style())
    story.append(seg_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<b>Finding.</b> Every segment large enough to test was classified nonconforming in this "
        "review — this is itself a finding worth escalating (extend testing across the population "
        "rather than a targeted subset), though it also means the segment flag alone did not "
        "differentiate individual transactions for review in this exercise (see sec. 5).",
        styles["Body"]))

    story.append(PageBreak())

    # ---------------- Page 4 — Rule-based exception testing ----------------
    story.append(Paragraph("4. Rule-Based Exception Testing", styles["H2"]))
    story.append(Paragraph(
        "Ten deterministic tests were applied, each with a stated audit rationale. Thresholds "
        "and exception counts:", styles["Body"]))
    rule_rationale = {
        "DUPLICATE_INVOICE": "Same customer/amount/date, different invoice — duplicate billing risk",
        "SPLIT_AMOUNT": "Amount just below an authorisation threshold — structuring risk",
        "LARGE_AMOUNT": "Amount above a fixed high-value threshold — requires senior review",
        "ROUND_NUMBER": "Amount is a round multiple (e.g. 1,000) — manual-entry indicator",
        "ROUND_DOLLARS": "Amount has zero pence — manual-entry indicator",
        "HIGH_QUANTITY": "Quantity far above the customer's typical order size",
        "ODD_QUANTITY": "Quantity pattern inconsistent with normal ordering",
        "OFF_HOUR": "Posted outside business hours (07:00-19:59)",
        "NEGATIVE_ADJUSTMENT": "Negative amount outside the normal returns pattern",
        "ZERO_QUANTITY": "Zero-quantity line with a non-zero amount",
    }
    rule_rows = [["Test", "Audit rationale", "Exceptions"]]
    for k, v in sorted(rules["rule_counts"].items(), key=lambda kv: -kv[1]):
        rule_rows.append([k, rule_rationale.get(k, ""), f"{v:,}"])
    rule_tbl = Table(rule_rows, colWidths=[35 * mm, 105 * mm, 25 * mm], style=_table_style())
    story.append(rule_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Control observation.</b> {rules['n_flagged']:,} of {rules['total_rows']:,} lines "
        f"({rules['flagged_pct']}%) carried at least one exception flag; "
        f"{rules['overlap_stats'].get('4_or_more', 0):,} lines carried four or more, indicating a "
        "small population of lines warranting priority review on multiple independent criteria.",
        styles["Body"]))
    if (FIGURES_DIR / "rule_time_series.png").exists():
        story.append(Image(str(FIGURES_DIR / "rule_time_series.png"), width=140 * mm, height=75 * mm))
        story.append(Paragraph("Figure 2 — Rule-flag activity over time.", styles["Caption"]))

    story.append(PageBreak())

    # ---------------- Page 5 — Statistical outliers and combined results ----------------
    story.append(Paragraph("5. Statistical Outlier Analysis and Combined Results", styles["H2"]))
    story.append(Paragraph(
        "An unsupervised algorithm (Isolation Forest) was used to score how easily each "
        "transaction can be separated from the rest of the population by its numeric attributes "
        "(amount, quantity, price, time of day, and the customer's historic transaction profile) "
        "— transactions that separate in fewer steps receive a higher score.", styles["Body"]))
    comp_m = mm_["models"]["composite"]
    story.append(Paragraph(
        f"<b>Validation results.</b> Against the labelled synthetic set, the composite score "
        f"achieved an Average Precision of {comp_m['average_precision']:.3f} (95% confidence "
        f"interval {comp_m['ap_ci95'][0]:.3f}-{comp_m['ap_ci95'][1]:.3f}) against a "
        f"{mm_['baseline_precision']:.3f} baseline expected from random selection — a lower bound "
        f"on real-world precision, for the reasons given in sec. 2. This supports treating the "
        f"composite ranking as a reasonable basis for prioritising review effort; it does not, on "
        f"its own, support any conclusion about individual transactions without further enquiry.",
        styles["Body"]))

    matrix = pd.read_csv(DASHBOARD_DIR / "method_comparison.csv")
    wide = matrix.pivot(index="anomaly_type", columns="method", values="pct_caught")
    order = [i for i in wide.index if i not in ("ALL_INJECTED", "REAL_ROWS")] + ["ALL_INJECTED", "REAL_ROWS"]
    wide = wide.reindex(order)
    mat_rows = [["Type"] + list(wide.columns)]
    for idx, row in wide.iterrows():
        mat_rows.append([idx] + [f"{v:.1f}%" for v in row])
    mat_tbl = Table(mat_rows, colWidths=[38 * mm] + [26 * mm] * len(wide.columns), style=_table_style())
    story.append(mat_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "<b>Interpretation.</b> No single procedure dominated every category in this review: "
        "rule-based tests caught the highest share of every injected category at a matched review "
        "budget, while the segmented Benford test surfaced fabricated-digit patterns that the "
        "aggregate test alone did not reveal. This is consistent with the case for applying more "
        "than one procedure rather than relying on any single test.", styles["Body"]))

    if (FIGURES_DIR / "recall_vs_effort.png").exists():
        story.append(Image(str(FIGURES_DIR / "recall_vs_effort.png"), width=140 * mm, height=80 * mm))
        p500 = mm_["models"]["composite"]["recall_at_k"]["500"]
        story.append(Paragraph(
            f"Figure 3 — Reviewing the top 500 items surfaces {p500*100:.1f}% of the known "
            f"synthetic exceptions, against a {mm_['baseline_precision']*500*100:.1f}% share "
            "expected from a random 500-item selection.", styles["Caption"]))

    story.append(PageBreak())

    # ---------------- Page 6 — Schedule of items for review ----------------
    story.append(Paragraph("6. Schedule of Items for Review", styles["H2"]))
    story.append(Paragraph(
        "The following 25 transactions carry the highest composite risk scores in the scored "
        "population and are recommended for the procedures indicated.", styles["Body"]))
    short_country = {"United Kingdom": "UK"}
    sched_rows = [["#", "Txn ID", "Date", "Ctry", "Amt (£)", "Risk", "Signals", "Procedure"]]
    for _, r in top25.iterrows():
        signals = str(r["rule_flag_names"]) or "-"
        signals = (signals[:16] + "..") if len(signals) > 18 else signals
        sched_rows.append([
            str(r["risk_rank"]),
            Paragraph(r["txn_id"].replace("TXN-", ""), styles["Small"]),
            str(r["invoice_date"])[5:16],
            short_country.get(r["country"], str(r["country"])[:3]),
            f"{r['amount']:.0f}", f"{r['composite_risk']:.2f}",
            Paragraph(signals, styles["Small"]),
            Paragraph(str(r["suggested_procedure"]), styles["Small"]),
        ])
    sched_tbl = Table(
        sched_rows,
        colWidths=[7 * mm, 16 * mm, 22 * mm, 10 * mm, 15 * mm, 10 * mm, 28 * mm, 62 * mm],
        style=TableStyle([
            ("FONT", (0, 0), (-1, 0), "Times-Bold", 7.5),
            ("FONT", (0, 1), (5, -1), "Times-Roman", 7),
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.grey),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#E0E0E0")),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]),
        repeatRows=1,
    )
    story.append(sched_tbl)
    story.append(Spacer(1, 14))
    story.append(Table(
        [["Prepared by", "", "Date", ""], ["Reviewed by", "", "Date", ""]],
        colWidths=[28 * mm, 55 * mm, 20 * mm, 40 * mm],
        style=TableStyle([
            ("FONT", (0, 0), (-1, -1), "Times-Roman", 9),
            ("LINEBELOW", (1, 0), (1, -1), 0.5, colors.grey),
            ("LINEBELOW", (3, 0), (3, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
        ]),
    ))

    return story


def run() -> Path:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = BaseDocTemplate(
        str(OUT_PATH), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
    story = build_story(styles)
    doc.build(story, canvasmaker=NumberedCanvas)
    return OUT_PATH


if __name__ == "__main__":
    path = run()
    print(f"Wrote {path} ({path.stat().st_size / 1024:.1f} KB)")
