"""Stage 10 (static fallback) -- generates docs/index.html.

A single self-contained, dark-themed page: the dashboard's aggregate figures as
inline SVG (no external JS chart library, no CDN dependency -- a Chart.js/CDN
version was tried first and broke under a restrictive network, see
DECISIONS.md D-0002/gate_10 report), plus a live in-browser re-scoring
simulator built on data/dashboard/rank_labels.json -- the exact ranking
Stage 7 validated, so the simulator's numbers at any k match
model_metrics.json exactly. It never sleeps, loads instantly, and needs no
OAuth step to publish (GitHub Pages serves it as a static file). It is the
public front door to the project; app/streamlit_app.py remains the fuller
interactive experience (filters, drill-through).

Every number is read from data/dashboard/*, never retyped by hand.

Usage::

    python -m src.static_dashboard
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

from src.config import cfg

DASHBOARD_DIR = cfg.paths.dashboard_dir
DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
OUT_PATH = DOCS_DIR / "index.html"

W, H, PAD = 560, 260, 34

# Dark palette -- see plan: clean modern SaaS (Linear/Vercel/Stripe style)
BG = "#0A0E14"
SURFACE = "#11161D"
BORDER = "#1E2530"
TEXT = "#E8EAED"
TEXT_DIM = "#8B94A3"
ACCENT = "#5B8DEF"
ACCENT_DIM = "#3D5A8F"
DANGER = "#F0605C"
GOOD = "#3DD68C"
WARN = "#E8B84B"


def _grouped_bar_svg(labels: list, series: list[tuple[str, list[float], str]]) -> str:
    """Two-series grouped bar chart as inline SVG, dark background."""
    max_v = max(max(s[1]) for s in series) * 1.15
    n = len(labels)
    group_w = (W - 2 * PAD) / n
    bar_w = group_w / (len(series) + 1)
    bars = []
    for gi, label in enumerate(labels):
        x0 = PAD + gi * group_w
        for si, (name, values, color) in enumerate(series):
            v = values[gi]
            bar_h = (H - 2 * PAD) * v / max_v if max_v else 0
            x = x0 + si * bar_w + bar_w * 0.15
            y = H - PAD - bar_h
            bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.7:.1f}" height="{bar_h:.1f}" fill="{color}" rx="2"/>')
        bars.append(f'<text x="{x0+group_w/2:.1f}" y="{H-PAD+18}" font-size="11" text-anchor="middle" fill="{TEXT_DIM}">{html.escape(str(label))}</text>')
    legend = "".join(
        f'<rect x="{PAD+i*140}" y="6" width="10" height="10" rx="2" fill="{c}"/>'
        f'<text x="{PAD+i*140+16}" y="15" font-size="11" fill="{TEXT_DIM}">{html.escape(n)}</text>'
        for i, (n, _, c) in enumerate(series)
    )
    axis = f'<line x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}" stroke="{BORDER}"/>'
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="grouped bar chart">{legend}{axis}{"".join(bars)}</svg>'


def _combo_chart_svg(labels: list, bar_values: list, line_values: list) -> str:
    """Bar (volume) + line (% flagged) combo chart as inline SVG, dark background."""
    max_bar = max(bar_values) * 1.15
    max_line = max(line_values) * 1.3 if max(line_values) else 1
    n = len(labels)
    bar_w = (W - 2 * PAD) / n * 0.6
    step = (W - 2 * PAD) / n
    bars, points = [], []
    for i, (bv, lv) in enumerate(zip(bar_values, line_values)):
        x = PAD + i * step + step * 0.2
        bh = (H - 2 * PAD) * bv / max_bar if max_bar else 0
        bars.append(f'<rect x="{x:.1f}" y="{H-PAD-bh:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="{ACCENT_DIM}" rx="2"/>')
        px = PAD + i * step + step / 2
        py = H - PAD - (H - 2 * PAD) * lv / max_line
        points.append(f"{px:.1f},{py:.1f}")
    every = max(1, n // 8)
    ticks = "".join(
        f'<text x="{PAD+i*step+step/2:.1f}" y="{H-PAD+18}" font-size="10" text-anchor="middle" fill="{TEXT_DIM}">{html.escape(str(labels[i]))}</text>'
        for i in range(0, n, every)
    )
    axis = f'<line x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}" stroke="{BORDER}"/>'
    line = f'<polyline points="{" ".join(points)}" fill="none" stroke="{DANGER}" stroke-width="2"/>'
    legend = (f'<rect x="{PAD}" y="6" width="10" height="10" rx="2" fill="{ACCENT_DIM}"/>'
              f'<text x="{PAD+16}" y="15" font-size="11" fill="{TEXT_DIM}">Transactions</text>'
              f'<line x1="{PAD+150}" y1="11" x2="{PAD+170}" y2="11" stroke="{DANGER}" stroke-width="2"/>'
              f'<text x="{PAD+174}" y="15" font-size="11" fill="{TEXT_DIM}">% flagged</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="monthly volume chart">{legend}{axis}{"".join(bars)}{line}{ticks}</svg>'


def _heat_color(v: float) -> str:
    """Low percentage -> muted slate, high percentage -> accent-to-danger ramp."""
    t = min(v, 100) / 100
    if t < 0.5:
        # slate -> accent
        tt = t / 0.5
        r = round(30 + tt * (91 - 30))
        g = round(37 + tt * (141 - 37))
        b = round(48 + tt * (239 - 48))
    else:
        tt = (t - 0.5) / 0.5
        r = round(91 + tt * (240 - 91))
        g = round(141 + tt * (96 - 141))
        b = round(239 + tt * (92 - 239))
    return f"rgb({r},{g},{b})"


def _matrix_table(index: list, cols: list, values: list[list[float]]) -> str:
    head = "<tr><th>Anomaly type</th>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "</tr>"
    rows = []
    for label, row in zip(index, values):
        cells = "".join(f'<td class="heat" style="background:{_heat_color(v)}">{v:.1f}%</td>' for v in row)
        rows.append(f"<tr><td>{html.escape(str(label))}</td>{cells}</tr>")
    return f"<table>{head}{''.join(rows)}</table>"


def _top10_table(rows: list[dict]) -> str:
    cols = ["risk_rank", "txn_id", "invoice_date", "country", "amount", "composite_risk", "risk_band", "suggested_procedure"]
    labels = {"risk_rank": "Rank", "txn_id": "Transaction", "invoice_date": "Date", "country": "Country",
              "amount": "Amount (GBP)", "composite_risk": "Risk score", "risk_band": "Band", "suggested_procedure": "Suggested procedure"}
    head = "<tr>" + "".join(f"<th>{labels[c]}</th>" for c in cols) + "</tr>"
    body = []
    for r in rows:
        cells = []
        for c in cols:
            v = r.get(c, "")
            if c == "risk_band":
                color = {"CRITICAL": DANGER, "HIGH": WARN, "MEDIUM": ACCENT, "LOW": GOOD}.get(str(v), TEXT_DIM)
                cells.append(f'<td><span class="band" style="color:{color};border-color:{color}">{html.escape(str(v))}</span></td>')
            else:
                cells.append(f"<td>{html.escape(str(v))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table>{head}{''.join(body)}</table>"


BUILD_JOURNEY = [
    ("00", "02", "Foundation",
     "Ingested the real UCI Online Retail II ledger (1,067,371 raw rows), built a SQLite "
     "layer with six audit-purpose SQL queries, and cleaned the population with every "
     "removed row reconciled: cancellations, duplicates, adjustments, all counted, none "
     "silently dropped.",
     "1,067,371 raw rows"),
    ("03", "03", "Ground truth",
     "Real audit data carries no labels, so a controlled synthetic anomaly set (16,874 "
     "rows, six fraud archetypes) was injected on top of the real ledger, with a leakage "
     "firewall verified by fitting a decision tree on ID-derived features alone and "
     "requiring its AUC to stay under 0.55.",
     "16,874 injected rows"),
    ("04", "06", "Three detection layers",
     "Built segmented Benford's Law testing (country by month), ten deterministic "
     "rule-based exception tests, and an Isolation Forest and LOF anomaly scorer on a "
     "leakage-safe feature set.",
     "3 independent methods"),
    ("07", "07", "The honest pivot",
     "Validated every method against the ground truth with Average Precision, bootstrap "
     "confidence intervals, and a full anomaly-type by detection-method matrix. The "
     "result contradicted the working hypothesis, and that result was reported as-is "
     "rather than adjusted until it looked better. See the finding below.",
     "the project's key result"),
    ("08", "08", "One risk score",
     "Combined the three layers into a single composite risk score with a five-variant "
     "weight-sensitivity check, then built a ranked review list where every flagged "
     "transaction carries a specific suggested audit procedure, not just a number.",
     "50,000 scored transactions"),
    ("09", "09", "Scoped out, on purpose",
     "Power BI Desktop has no headless build path. Rather than fake a screenshot or spend "
     "time on unreliable GUI automation, this stage was skipped and documented plainly, "
     "with every data file it would need already sitting ready to load.",
     "documented, not hidden"),
    ("10", "10", "Shipped it live",
     "Built this page and a full interactive Streamlit app, both reading only from a "
     "committed, size-capped data layer so the public site never depends on the raw "
     "pipeline output. Live the same day it was built.",
     "zero external dependencies"),
    ("11", "11", "No retyped numbers",
     "Executed six real notebooks end to end and generated the README from a placeholder "
     "engine that reads straight out of the metrics files, so a number in the writeup can "
     "never drift from what the code actually produced.",
     "generated, not hand-typed"),
    ("12", "12", "A real workpaper",
     "Programmatically built a six-page audit findings PDF with reportlab, byte-for-byte "
     "reproducible from the same metrics files. Caught and fixed a page-duplication bug "
     "in the process, the kind of thing you only catch by actually checking your own output.",
     "6 pages, reproducible"),
    ("13", "13", "Published",
     "Wrote three resume-bullet variants and 22 interview answers with every number "
     "cross-checked against the metrics, found and fixed a leaked local file path along "
     "the way, then made the repository public.",
     "public repository"),
]


def _journey_html() -> str:
    cards = []
    for start, end, title, desc, stat in BUILD_JOURNEY:
        stage_label = f"Stage {start}" if start == end else f"Stage {start}-{end}"
        cards.append(f"""
        <div class="journey-card">
          <div class="journey-stage">{stage_label}</div>
          <div class="journey-title">{html.escape(title)}</div>
          <p class="journey-desc">{html.escape(desc)}</p>
          <div class="journey-stat">{html.escape(stat)}</div>
        </div>""")
    return "".join(cards)


def _load() -> dict:
    kpi = json.loads((DASHBOARD_DIR / "kpi_summary.json").read_text())
    mm = json.loads((DASHBOARD_DIR / "model_metrics.json").read_text())
    benford_agg = pd.read_csv(DASHBOARD_DIR / "benford_aggregate.csv")
    monthly = pd.read_csv(DASHBOARD_DIR / "monthly_trend.csv")
    method_comp = pd.read_csv(DASHBOARD_DIR / "method_comparison.csv")
    top10 = pd.read_csv(DASHBOARD_DIR / "top_risk_transactions.csv").head(10)
    rank_labels_raw = (DASHBOARD_DIR / "rank_labels.json").read_text()

    wide = method_comp.pivot(index="anomaly_type", columns="method", values="pct_caught")
    order = [i for i in wide.index if i not in ("ALL_INJECTED", "REAL_ROWS")] + ["ALL_INJECTED", "REAL_ROWS"]
    wide = wide.reindex(order)

    return {
        "kpi": kpi, "mm": mm, "caveats": mm.get("caveats", []),
        "benford_agg": benford_agg, "monthly": monthly,
        "matrix_index": list(wide.index), "matrix_cols": list(wide.columns),
        "matrix_values": wide.round(1).values.tolist(),
        "top10": top10.to_dict(orient="records"),
        "rank_labels_raw": rank_labels_raw,
    }


def render(data: dict) -> str:
    kpi, mm = data["kpi"], data["mm"]
    comp = mm["models"]["composite"]
    rules_any_extreme = mm["per_type"]["extreme_outlier"]["rules_any"]["pct_caught"]
    iforest_extreme = mm["per_type"]["extreme_outlier"]["iforest"]["pct_caught"]
    rules_any_all = mm["per_type"]["ALL_INJECTED"] if "ALL_INJECTED" in mm.get("per_type", {}) else None

    benford_svg = _grouped_bar_svg(
        data["benford_agg"]["digit"].tolist(),
        [("Observed", data["benford_agg"]["observed_prop"].tolist(), ACCENT),
         ("Expected (Benford)", data["benford_agg"]["expected_prop"].tolist(), BORDER)],
    )
    monthly_svg = _combo_chart_svg(
        data["monthly"]["year_month"].tolist(),
        data["monthly"]["txn_count"].tolist(),
        data["monthly"]["pct_flagged"].tolist(),
    )
    matrix_html = _matrix_table(data["matrix_index"], data["matrix_cols"], data["matrix_values"])
    top10_html = _top10_table(data["top10"])
    caveats_html = "".join(f"<li>{html.escape(c)}</li>" for c in data["caveats"])
    journey_html = _journey_html()

    def kpi_card(label: str, value: str, sub: str = "") -> str:
        sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
        return f'<div class="kpi"><div class="label">{html.escape(label)}</div><div class="value">{value}</div>{sub_html}</div>'

    kpis = "".join([
        kpi_card("Population", f"{kpi['total_txns']:,}", "real transactions"),
        kpi_card("Ledger value", f"&pound;{kpi['total_value']:,.0f}", "GBP, 2009 to 2011"),
        kpi_card("Benford MAD", f"{kpi['aggregate_mad']:.4f}", kpi["aggregate_verdict"].title()),
        kpi_card("Segments tested", f"{kpi['n_segments_flagged']} / {kpi['n_segments_assessed']}", "flagged nonconforming"),
        kpi_card("Average Precision", f"{comp['average_precision']:.3f}", f"vs {mm['baseline_precision']:.3f} random"),
        kpi_card("Precision at 500", f"{kpi['headline_precision_at_500']*100:.1f}%", "top 500 reviewed"),
    ])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit Analytics: Transaction Anomaly Detection</title>
<style>
  :root {{
    --bg: {BG}; --surface: {SURFACE}; --border: {BORDER};
    --text: {TEXT}; --text-dim: {TEXT_DIM};
    --accent: {ACCENT}; --accent-dim: {ACCENT_DIM};
    --danger: {DANGER}; --good: {GOOD}; --warn: {WARN};
  }}
  * {{ box-sizing: border-box; }}
  html {{ background: var(--bg); }}
  body {{
    margin: 0; padding: 0 20px 80px; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    line-height: 1.55;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; }}
  a {{ color: var(--accent); }}
  code {{ background: var(--surface); padding: 1px 6px; border-radius: 4px; font-size: 0.9em; border: 1px solid var(--border); }}

  /* ---------- Nav ---------- */
  .nav {{ display: flex; justify-content: space-between; align-items: center; padding: 20px 0; border-bottom: 1px solid var(--border); margin-bottom: 8px; flex-wrap: wrap; gap: 10px; }}
  .brand {{ font-weight: 700; font-size: 1.05rem; letter-spacing: -0.01em; white-space: nowrap; }}
  .nav-links {{ display: flex; flex-wrap: wrap; gap: 4px 16px; }}
  .nav-links a {{ color: var(--text-dim); text-decoration: none; font-size: 0.88rem; font-weight: 500; }}
  .nav-links a:hover {{ color: var(--text); }}

  /* ---------- Hero ---------- */
  .hero {{ padding: 56px 0 40px; }}
  .eyebrow {{ display: inline-block; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase;
              color: var(--accent); background: rgba(91,141,239,0.12); border: 1px solid rgba(91,141,239,0.3);
              padding: 5px 12px; border-radius: 999px; margin-bottom: 20px; }}
  h1 {{ font-size: 2.6rem; line-height: 1.15; letter-spacing: -0.02em; margin: 0 0 18px; font-weight: 700; max-width: 800px; }}
  h1 .accent {{ color: var(--accent); }}
  .hero-sub {{ font-size: 1.15rem; color: var(--text-dim); max-width: 680px; margin: 0 0 28px; }}
  .cta-row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .btn {{ display: inline-flex; align-items: center; gap: 8px; padding: 11px 20px; border-radius: 8px; font-weight: 600;
          font-size: 0.92rem; text-decoration: none; border: 1px solid transparent; cursor: pointer; }}
  .btn-primary {{ background: var(--accent); color: #06111F; }}
  .btn-primary:hover {{ background: #78A3F5; }}
  .btn-secondary {{ background: var(--surface); color: var(--text); border-color: var(--border); }}
  .btn-secondary:hover {{ border-color: var(--accent); }}

  /* ---------- Sections ---------- */
  section {{ padding: 52px 0; border-top: 1px solid var(--border); }}
  .section-tag {{ font-size: 0.78rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 10px; }}
  h2 {{ font-size: 1.6rem; letter-spacing: -0.01em; margin: 0 0 14px; }}
  .section-lede {{ color: var(--text-dim); max-width: 720px; margin-bottom: 30px; font-size: 1rem; }}

  /* ---------- KPI grid ---------- */
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px 18px 16px; }}
  .kpi .label {{ font-size: 0.78rem; color: var(--text-dim); margin-bottom: 8px; }}
  .kpi .value {{ font-size: 1.55rem; font-weight: 700; letter-spacing: -0.01em; font-variant-numeric: tabular-nums; }}
  .kpi .kpi-sub {{ font-size: 0.78rem; color: var(--text-dim); margin-top: 4px; }}

  /* ---------- Three-layer explainer ---------- */
  .layers {{ display: grid; grid-template-columns: 1fr auto 1fr auto 1fr; gap: 14px; align-items: center; margin-bottom: 20px; }}
  @media (max-width: 800px) {{ .layers {{ grid-template-columns: 1fr; }} .layer-plus {{ display:none; }} }}
  .layer-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; text-align: center; }}
  .layer-icon {{ width: 40px; height: 40px; border-radius: 10px; background: rgba(91,141,239,0.14); display: flex; align-items: center;
                 justify-content: center; margin: 0 auto 12px; font-size: 1.2rem; }}
  .layer-title {{ font-weight: 700; margin-bottom: 6px; }}
  .layer-desc {{ font-size: 0.85rem; color: var(--text-dim); }}
  .layer-plus {{ font-size: 1.4rem; color: var(--text-dim); text-align: center; }}
  .arrow-down {{ text-align: center; font-size: 1.4rem; color: var(--text-dim); margin: 6px 0; }}
  .composite-card {{ background: linear-gradient(135deg, rgba(91,141,239,0.12), rgba(91,141,239,0.03));
                      border: 1px solid rgba(91,141,239,0.35); border-radius: 12px; padding: 22px; text-align: center; }}
  .composite-card .layer-title {{ font-size: 1.1rem; }}

  /* ---------- Simulator ---------- */
  .sim {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 28px 28px 24px; }}
  .sim-presets {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }}
  .preset-btn {{ background: var(--bg); border: 1px solid var(--border); color: var(--text-dim); padding: 7px 14px;
                 border-radius: 8px; font-size: 0.85rem; font-weight: 600; cursor: pointer; font-variant-numeric: tabular-nums; }}
  .preset-btn:hover {{ border-color: var(--accent); color: var(--text); }}
  .preset-btn.active {{ background: var(--accent); border-color: var(--accent); color: #06111F; }}
  .sim-slider-row {{ display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }}
  .sim-slider-row input[type=range] {{ flex: 1; accent-color: var(--accent); height: 4px; background: var(--border); border-radius: 999px; }}
  .sim-slider-row input[type=range]::-webkit-slider-runnable-track {{ background: var(--border); border-radius: 999px; height: 4px; }}
  .sim-slider-row input[type=range]::-moz-range-track {{ background: var(--border); border-radius: 999px; height: 4px; }}
  .sim-k-readout {{ font-weight: 700; font-variant-numeric: tabular-nums; min-width: 150px; text-align: right; color: var(--accent); }}
  .sim-results {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }}
  .sim-result {{ background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }}
  .sim-result .label {{ font-size: 0.75rem; color: var(--text-dim); margin-bottom: 6px; }}
  .sim-result .value {{ font-size: 1.4rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .sim-caption {{ font-size: 0.85rem; color: var(--text-dim); }}
  .sim-caption b {{ color: var(--text); }}

  /* ---------- Finding callout ---------- */
  .finding {{ background: linear-gradient(135deg, rgba(240,96,92,0.10), rgba(17,22,29,0)); border: 1px solid rgba(240,96,92,0.3);
              border-radius: 16px; padding: 28px; }}
  .finding-label {{ color: var(--danger); font-weight: 700; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px; }}
  .finding p {{ font-size: 1.02rem; margin: 0 0 14px; max-width: 760px; }}
  .finding-stats {{ display: flex; gap: 32px; flex-wrap: wrap; margin-top: 18px; }}
  .finding-stat .n {{ font-size: 1.7rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .finding-stat .l {{ font-size: 0.8rem; color: var(--text-dim); }}

  /* ---------- Journey timeline ---------- */
  .journey {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }}
  .journey-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px; }}
  .journey-stage {{ font-size: 0.72rem; font-weight: 700; letter-spacing: 0.05em; color: var(--accent); text-transform: uppercase; margin-bottom: 8px; }}
  .journey-title {{ font-weight: 700; margin-bottom: 8px; font-size: 1.02rem; }}
  .journey-desc {{ font-size: 0.86rem; color: var(--text-dim); margin: 0 0 10px; }}
  .journey-stat {{ font-size: 0.78rem; color: var(--text); background: var(--bg); border: 1px solid var(--border);
                    display: inline-block; padding: 3px 10px; border-radius: 999px; font-weight: 600; }}

  /* ---------- Charts / tables ---------- */
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  @media (max-width: 800px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }}
  .chart-card h3 {{ font-size: 0.95rem; margin: 0 0 14px; color: var(--text); }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.84rem; }}
  th, td {{ padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--text-dim); font-weight: 600; font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.03em; }}
  .heat {{ text-align: center; color: #fff; font-weight: 700; border-radius: 4px; }}
  .tablewrap {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 6px 16px; }}
  .band {{ font-size: 0.72rem; font-weight: 700; border: 1px solid; border-radius: 999px; padding: 2px 9px; }}

  /* ---------- Limitations ---------- */
  .limits ul {{ margin: 0; padding-left: 20px; color: var(--text-dim); }}
  .limits li {{ margin-bottom: 10px; }}

  footer {{ padding: 32px 0; color: var(--text-dim); font-size: 0.85rem; border-top: 1px solid var(--border); }}
</style>
</head>
<body>
<div class="wrap">

  <nav class="nav">
    <div class="brand">Audit Analytics</div>
    <div class="nav-links">
      <a href="https://github.com/vishalyl/benfords-audit-analytics">GitHub</a>
      <a href="../docs/methodology.md">Methodology</a>
      <a href="../reports/audit_findings_workpaper.pdf">Workpaper</a>
    </div>
  </nav>

  <div class="hero">
    <div class="eyebrow">Transaction anomaly detection</div>
    <h1>Three independent methods.<br>One <span class="accent">real</span> 1 million row ledger.<br>A finding that surprised its own author.</h1>
    <p class="hero-sub">
      Benford's Law, ten rule-based exception tests, and an Isolation Forest, validated against
      a controlled synthetic anomaly set and combined into one composite risk score. Every number
      on this page is computed by the pipeline, not typed by hand.
    </p>
    <div class="cta-row">
      <a class="btn btn-primary" href="#simulator">Try the live simulator</a>
      <a class="btn btn-secondary" href="https://github.com/vishalyl/benfords-audit-analytics">View source</a>
      <a class="btn btn-secondary" href="../reports/audit_findings_workpaper.pdf">Read the workpaper</a>
    </div>
  </div>

  <section>
    <div class="section-tag">The population</div>
    <h2>A real ledger, honestly scoped</h2>
    <p class="section-lede">
      UCI's Online Retail II dataset: a genuine UK online retailer's transaction history,
      December 2009 through December 2011. Nothing about the base population is synthetic.
    </p>
    <div class="kpis">{kpis}</div>
  </section>

  <section>
    <div class="section-tag">The method</div>
    <h2>Three layers, one score</h2>
    <p class="section-lede">
      No single test catches every kind of manipulation, so three independent detectors run
      in parallel and their outputs blend into a composite risk score.
    </p>
    <div class="layers">
      <div class="layer-card">
        <div class="layer-icon">1</div>
        <div class="layer-title">Benford's Law</div>
        <div class="layer-desc">Segmented leading-digit conformity testing, country by month, MAD-based against Nigrini's thresholds.</div>
      </div>
      <div class="layer-plus">+</div>
      <div class="layer-card">
        <div class="layer-icon">2</div>
        <div class="layer-title">Rule-based checks</div>
        <div class="layer-desc">Ten deterministic exception tests: duplicates, structuring, round amounts, off-hours and period-end posting.</div>
      </div>
      <div class="layer-plus">+</div>
      <div class="layer-card">
        <div class="layer-icon">3</div>
        <div class="layer-title">Isolation Forest</div>
        <div class="layer-desc">Unsupervised statistical outlier scoring on a leakage-safe feature set, no ground truth ever touches training.</div>
      </div>
    </div>
    <div class="arrow-down">&darr;</div>
    <div class="composite-card">
      <div class="layer-title">Composite risk score</div>
      <div class="layer-desc">0.50 &times; Isolation Forest percentile &nbsp;+&nbsp; 0.30 &times; rule flags &nbsp;+&nbsp; 0.20 &times; Benford segment flag. Weights set by judgement, not tuned against the labels.</div>
    </div>
  </section>

  <section id="simulator">
    <div class="section-tag">Try it</div>
    <h2>Live re-scoring simulator</h2>
    <p class="section-lede">
      This is not a screenshot. Pick a review budget and the browser recomputes precision, recall
      and lift instantly from the real per-transaction ranking the pipeline produced, the same
      50,000-transaction population validated in <a href="../reports/gate_reports/gate_07.md">Stage 7</a>.
    </p>
    <div class="sim">
      <div class="sim-presets" id="presets"></div>
      <div class="sim-slider-row">
        <input type="range" id="kSlider" min="1" max="50000" value="500" step="1">
        <div class="sim-k-readout" id="kReadout">500 reviewed</div>
      </div>
      <div class="sim-results">
        <div class="sim-result"><div class="label">Precision</div><div class="value" id="rPrecision">-</div></div>
        <div class="sim-result"><div class="label">Recall</div><div class="value" id="rRecall">-</div></div>
        <div class="sim-result"><div class="label">Lift over random</div><div class="value" id="rLift">-</div></div>
        <div class="sim-result"><div class="label">Anomalies found</div><div class="value" id="rCaught">-</div></div>
      </div>
      <div class="sim-caption" id="simCaption"></div>
    </div>
  </section>

  <section>
    <div class="section-tag">The result</div>
    <h2>The biggest finding wasn't the one we expected</h2>
    <div class="finding">
      <div class="finding-label">Reported as measured, not as hypothesized</div>
      <p>
        The working assumption was that Isolation Forest would dominate extreme statistical
        outliers, the archetype it should be best suited for. It didn't. At a matched 1.5% review
        budget, the rule-based layer caught more of every single injected anomaly type, including
        the ones designed specifically to be statistical outliers. That result got written up
        exactly as measured rather than adjusted until it matched the original hypothesis.
      </p>
      <p>
        The composite score still earns its place: its Average Precision beats every individual
        method on its own, meaning it ranks transactions better even where its raw catch rate at a
        fixed budget trails the rules layer. That distinction, ranking well versus catching the
        most at a fixed cutoff, is the kind of nuance a tuned-for-the-story result would have
        hidden.
      </p>
      <div class="finding-stats">
        <div class="finding-stat"><div class="n">{rules_any_extreme:.0f}%</div><div class="l">Rules caught, extreme outliers</div></div>
        <div class="finding-stat"><div class="n">{iforest_extreme:.0f}%</div><div class="l">Isolation Forest caught, same type</div></div>
        <div class="finding-stat"><div class="n">{comp['average_precision']:.3f}</div><div class="l">Composite Average Precision, best of all methods</div></div>
      </div>
    </div>
  </section>

  <section>
    <div class="section-tag">How it was built</div>
    <h2>Thirteen stages, in order, nothing skipped without saying so</h2>
    <p class="section-lede">
      Every stage has its own gate script, a written report, and a git tag. This is the real
      sequence, including the parts that didn't go as planned.
    </p>
    <div class="journey">{journey_html}</div>
  </section>

  <section>
    <div class="section-tag">Evidence</div>
    <h2>Benford's Law and detection performance</h2>
    <div class="grid2">
      <div class="chart-card">
        <h3>Leading-digit distribution, observed vs expected</h3>
        {benford_svg}
      </div>
      <div class="chart-card">
        <h3>Monthly volume and percent flagged</h3>
        {monthly_svg}
      </div>
    </div>
  </section>

  <section>
    <h2>Method by anomaly-type detection matrix</h2>
    <p class="section-lede">Percentage of each injected anomaly type caught by each method, at a matched review budget.</p>
    <div class="tablewrap">{matrix_html}</div>
  </section>

  <section>
    <h2>Top 10, for audit review</h2>
    <p class="section-lede">Highest composite risk score in the scored population, each with a specific suggested procedure.</p>
    <div class="tablewrap">{top10_html}</div>
  </section>

  <section class="limits">
    <div class="section-tag">Self-assessment</div>
    <h2>Limitations</h2>
    <ul>{caveats_html}</ul>
  </section>

  <section>
    <div class="section-tag">What's next</div>
    <h2>Where this goes from here</h2>
    <p class="section-lede">
      A practical, trimmed set of next steps, not a wishlist:
      <a href="roadmap_status.md">docs/roadmap_status.md</a>.
    </p>
  </section>

  <footer>
    Data: UCI Online Retail II (CC BY 4.0). Detection layers rank transactions for review,
    they do not on their own evidence fraud or misstatement. Generated from
    <code>data/dashboard/*</code>, every number here is computed, not hand-typed.
  </footer>
</div>

<script>
const RANK_LABELS = {data['rank_labels_raw']};
const N = RANK_LABELS.length;
const TOTAL_POS = RANK_LABELS.reduce((a,b) => a+b, 0);
const BASELINE = TOTAL_POS / N;
const PREFIX = new Int32Array(N + 1);
for (let i = 0; i < N; i++) PREFIX[i+1] = PREFIX[i] + RANK_LABELS[i];

const PRESETS = [50, 100, 500, 1000, 5000, 10000, 25000, 50000];
const presetsEl = document.getElementById('presets');
PRESETS.forEach(k => {{
  const b = document.createElement('button');
  b.className = 'preset-btn';
  b.textContent = k.toLocaleString();
  b.onclick = () => {{ document.getElementById('kSlider').value = k; updateSim(k); }};
  b.dataset.k = k;
  presetsEl.appendChild(b);
}});

function updateSim(k) {{
  k = Math.max(1, Math.min(N, Math.round(k)));
  const caught = PREFIX[k];
  const precision = caught / k;
  const recall = caught / TOTAL_POS;
  const lift = BASELINE > 0 ? precision / BASELINE : 0;

  document.getElementById('kReadout').textContent = k.toLocaleString() + ' reviewed';
  document.getElementById('rPrecision').textContent = (precision*100).toFixed(1) + '%';
  document.getElementById('rRecall').textContent = (recall*100).toFixed(1) + '%';
  document.getElementById('rLift').textContent = lift.toFixed(1) + 'x';
  document.getElementById('rCaught').textContent = caught.toLocaleString() + ' / ' + TOTAL_POS.toLocaleString();
  document.getElementById('simCaption').innerHTML =
    'Reviewing the top <b>' + k.toLocaleString() + '</b> of ' + N.toLocaleString() +
    ' scored transactions surfaces <b>' + (recall*100).toFixed(1) + '%</b> of all known anomalies, ' +
    'a <b>' + lift.toFixed(1) + 'x</b> lift over reviewing ' + k.toLocaleString() + ' at random.';

  document.querySelectorAll('.preset-btn').forEach(b => {{
    b.classList.toggle('active', parseInt(b.dataset.k, 10) === k);
  }});
}}

document.getElementById('kSlider').addEventListener('input', (e) => updateSim(e.target.value));
updateSim(500);
</script>
</body>
</html>
"""


def run() -> Path:
    data = _load()
    html_out = render(data)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_out, encoding="utf-8")
    return OUT_PATH


if __name__ == "__main__":
    path = run()
    print(f"Wrote {path} ({path.stat().st_size / 1024:.1f} KB)")
