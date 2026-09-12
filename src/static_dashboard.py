"""Stage 10 (static fallback) — generates docs/index.html.

A single self-contained page with the dashboard's aggregate figures rendered
as plain inline SVG (no external JS chart library, no CDN dependency, so it
never breaks under a restrictive network) — see DECISIONS.md D-0002 for why
this exists alongside the Streamlit app. It never sleeps, loads instantly,
and needs no OAuth step to publish (GitHub Pages serves it as a static
file). It is an "instant-load summary"; the Streamlit app
(`app/streamlit_app.py`) remains the full interactive experience with the
review-budget slider, filters and drill-through.

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


def _grouped_bar_svg(labels: list, series: list[tuple[str, list[float], str]], y_fmt=lambda v: f"{v*100:.0f}%") -> str:
    """Two-series grouped bar chart as inline SVG. series = [(name, values, color), ...]."""
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
            bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w*0.7:.1f}" height="{bar_h:.1f}" fill="{color}"/>')
        bars.append(f'<text x="{x0+group_w/2:.1f}" y="{H-PAD+16}" font-size="10" text-anchor="middle" fill="#555">{html.escape(str(label))}</text>')
    legend = "".join(
        f'<rect x="{PAD+i*120}" y="8" width="10" height="10" fill="{c}"/>'
        f'<text x="{PAD+i*120+14}" y="17" font-size="11" fill="#333">{html.escape(n)}</text>'
        for i, (n, _, c) in enumerate(series)
    )
    axis = f'<line x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}" stroke="#ccc"/>'
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="grouped bar chart">{legend}{axis}{"".join(bars)}</svg>'


def _combo_chart_svg(labels: list, bar_values: list, line_values: list) -> str:
    """Bar (volume) + line (% flagged) combo chart as inline SVG."""
    max_bar = max(bar_values) * 1.15
    max_line = max(line_values) * 1.3 if max(line_values) else 1
    n = len(labels)
    bar_w = (W - 2 * PAD) / n * 0.6
    step = (W - 2 * PAD) / n
    bars, points = [], []
    for i, (bv, lv) in enumerate(zip(bar_values, line_values)):
        x = PAD + i * step + step * 0.2
        bh = (H - 2 * PAD) * bv / max_bar if max_bar else 0
        bars.append(f'<rect x="{x:.1f}" y="{H-PAD-bh:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" fill="#9DC3E6"/>')
        px = PAD + i * step + step / 2
        py = H - PAD - (H - 2 * PAD) * lv / max_line
        points.append(f"{px:.1f},{py:.1f}")
    every = max(1, n // 8)
    ticks = "".join(
        f'<text x="{PAD+i*step+step/2:.1f}" y="{H-PAD+16}" font-size="9" text-anchor="middle" fill="#555">{html.escape(str(labels[i]))}</text>'
        for i in range(0, n, every)
    )
    axis = f'<line x1="{PAD}" y1="{H-PAD}" x2="{W-PAD}" y2="{H-PAD}" stroke="#ccc"/>'
    line = f'<polyline points="{" ".join(points)}" fill="none" stroke="#D93025" stroke-width="2"/>'
    legend = (f'<rect x="{PAD}" y="8" width="10" height="10" fill="#9DC3E6"/>'
              f'<text x="{PAD+14}" y="17" font-size="11" fill="#333">Transactions</text>'
              f'<line x1="{PAD+140}" y1="13" x2="{PAD+160}" y2="13" stroke="#D93025" stroke-width="2"/>'
              f'<text x="{PAD+164}" y="17" font-size="11" fill="#333">% flagged</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="monthly volume chart">{legend}{axis}{"".join(bars)}{line}{ticks}</svg>'


def _heat_color(v: float) -> str:
    t = min(v, 100) / 100
    r, g, b = round(217 - t * (217 - 30)), round(48 + t * (140 - 48)), 60
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
    head = "<tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
    body = []
    for r in rows:
        body.append("<tr>" + "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>")
    return f"<table>{head}{''.join(body)}</table>"


def _load() -> dict:
    kpi = json.loads((DASHBOARD_DIR / "kpi_summary.json").read_text())
    mm = json.loads((DASHBOARD_DIR / "model_metrics.json").read_text())
    benford_agg = pd.read_csv(DASHBOARD_DIR / "benford_aggregate.csv")
    monthly = pd.read_csv(DASHBOARD_DIR / "monthly_trend.csv")
    method_comp = pd.read_csv(DASHBOARD_DIR / "method_comparison.csv")
    top10 = pd.read_csv(DASHBOARD_DIR / "top_risk_transactions.csv").head(10)

    wide = method_comp.pivot(index="anomaly_type", columns="method", values="pct_caught")
    order = [i for i in wide.index if i not in ("ALL_INJECTED", "REAL_ROWS")] + ["ALL_INJECTED", "REAL_ROWS"]
    wide = wide.reindex(order)

    return {
        "kpi": kpi, "caveats": mm.get("caveats", []),
        "benford_agg": benford_agg, "monthly": monthly,
        "matrix_index": list(wide.index), "matrix_cols": list(wide.columns),
        "matrix_values": wide.round(1).values.tolist(),
        "top10": top10.to_dict(orient="records"),
    }


def render(data: dict) -> str:
    kpi = data["kpi"]
    benford_svg = _grouped_bar_svg(
        data["benford_agg"]["digit"].tolist(),
        [("Observed", data["benford_agg"]["observed_prop"].tolist(), "#1F4E79"),
         ("Expected (Benford)", data["benford_agg"]["expected_prop"].tolist(), "#9DC3E6")],
    )
    monthly_svg = _combo_chart_svg(
        data["monthly"]["year_month"].tolist(),
        data["monthly"]["txn_count"].tolist(),
        data["monthly"]["pct_flagged"].tolist(),
    )
    matrix_html = _matrix_table(data["matrix_index"], data["matrix_cols"], data["matrix_values"])
    top10_html = _top10_table(data["top10"])
    caveats_html = "".join(f"<li>{html.escape(c)}</li>" for c in data["caveats"])

    def kpi_card(label: str, value: str) -> str:
        return f'<div class="kpi"><div class="label">{html.escape(label)}</div><div class="value">{value}</div></div>'

    kpis = "".join([
        kpi_card("Total transactions", f"{kpi['total_txns']:,}"),
        kpi_card("Total value", f"£{kpi['total_value']:,.0f}"),
        kpi_card("Aggregate Benford MAD", f"{kpi['aggregate_mad']:.4f} ({kpi['aggregate_verdict']})"),
        kpi_card("Segments flagged", f"{kpi['n_segments_flagged']} / {kpi['n_segments_assessed']}"),
        kpi_card("Injected anomalies", f"{kpi['n_injected']:,} ({kpi['anomaly_rate']*100:.2f}%)"),
        kpi_card("Headline Average Precision", f"{kpi['headline_average_precision']:.4f} [{kpi['headline_ap_ci95'][0]:.3f}–{kpi['headline_ap_ci95'][1]:.3f}]"),
        kpi_card("Precision@500", f"{kpi['headline_precision_at_500']*100:.1f}%"),
        kpi_card("% scored pop. High/Critical", f"{kpi['pct_high_critical']:.1f}%"),
    ])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit Analytics — Transaction Anomaly Detection</title>
<style>
  :root {{ --primary:#1F4E79; --risk:#D93025; --bg:#FFFFFF; --fg:#1F1F1F; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:0 20px 60px; font-family:-apple-system,Segoe UI,Roboto,sans-serif;
          background:var(--bg); color:var(--fg); }}
  .wrap {{ max-width:1200px; margin:0 auto; }}
  h1 {{ font-size:1.9rem; margin-bottom:0.2rem; }}
  .sub {{ color:#555; margin-top:0; }}
  .banner {{ background:#FFF8E1; border:1px solid #F9AB00; border-radius:8px; padding:12px 16px; margin:16px 0; font-size:0.95rem; }}
  .links a {{ color:var(--primary); text-decoration:none; margin-right:14px; font-weight:600; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:24px 0; }}
  .kpi {{ border:1px solid #E0E0E0; border-radius:10px; padding:14px 16px; }}
  .kpi .label {{ font-size:0.8rem; color:#666; }}
  .kpi .value {{ font-size:1.4rem; font-weight:700; color:var(--primary); }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; margin:24px 0; }}
  @media (max-width:800px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  table {{ border-collapse:collapse; width:100%; font-size:0.82rem; }}
  th, td {{ border:1px solid #E0E0E0; padding:6px 8px; text-align:left; }}
  th {{ background:#F4F6F8; }}
  .heat {{ text-align:center; color:#fff; font-weight:600; }}
  .tablewrap {{ overflow-x:auto; }}
  footer {{ margin-top:40px; color:#777; font-size:0.85rem; border-top:1px solid #eee; padding-top:16px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🔍 Audit Analytics — Transaction Anomaly Detection</h1>
  <p class="sub">Benford's Law · Rule-Based Red Flags · Isolation Forest — instant-load summary (static, always live)</p>
  <div class="banner">
    <b>Demonstration project.</b> A controlled set of synthetic anomalies (1.5% of rows, 6 fraud archetypes)
    was injected into a real public dataset so detection accuracy could actually be measured.
    This page is a static, always-on summary; the full interactive app (filters, review-budget slider,
    drill-through) lives in the Streamlit source in this repository.
  </div>
  <p class="links">
    <a href="https://github.com/vishalyl/benfords-audit-analytics">GitHub repository</a>
    <a href="../docs/methodology.md">Methodology</a>
    <a href="../reports/audit_findings_workpaper.pdf">Audit findings workpaper (PDF)</a>
  </p>

  <div class="kpis">{kpis}</div>

  <div class="grid2">
    <div>
      <h3>Leading-digit distribution — observed vs expected</h3>
      {benford_svg}
    </div>
    <div>
      <h3>Monthly transaction volume &amp; % flagged</h3>
      {monthly_svg}
    </div>
  </div>

  <h3>Method × anomaly-type detection matrix (% caught)</h3>
  <div class="tablewrap">{matrix_html}</div>

  <h3>Top 10 — for audit review</h3>
  <div class="tablewrap">{top10_html}</div>

  <h3>Caveats</h3>
  <ul>{caveats_html}</ul>

  <footer>
    Data: UCI Online Retail II (CC BY 4.0). Detection layers rank transactions for review —
    they do not, on their own, evidence fraud or misstatement. Generated from
    <code>data/dashboard/*</code> — every number here is computed, not hand-typed.
  </footer>
</div>
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
