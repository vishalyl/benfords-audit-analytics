"""Audit Analytics — public Streamlit dashboard (Stage 10).

Reads ONLY from the committed data/dashboard directory (capped at 25 MB) —
never from the git-ignored raw or intermediate pipeline output directories.
Paths are resolved relative to the repo root so this works identically
locally and on Streamlit Community Cloud.

Run locally::

    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = REPO_ROOT / "data" / "dashboard"

PALETTE = {
    "primary": "#1F4E79", "secondary": "#2E75B6", "tertiary": "#9DC3E6",
    "risk": "#D93025", "warning": "#F9AB00", "good": "#1E8E3E", "neutral": "#7F7F7F",
}
BAND_COLORS = {"LOW": PALETTE["good"], "MEDIUM": PALETTE["warning"],
               "HIGH": PALETTE["secondary"], "CRITICAL": PALETTE["risk"]}

REQUIRED_FILES = [
    "kpi_summary.json", "model_metrics.json", "benford_aggregate.csv",
    "benford_segments.csv", "benford_by_segment_digit.csv", "monthly_trend.csv",
    "segment_heatmap.csv", "method_comparison.csv", "top_risk_5000.csv",
    "top_risk_transactions.csv",
]


@st.cache_data
def load_dashboard_data() -> dict:
    """Load every data/dashboard/ file into a dict of DataFrames/dicts.

    Raises a clear error (surfaced via st.error, not a crash) naming the
    missing file and the pipeline stage that produces it.
    """
    data: dict = {}
    missing = [f for f in REQUIRED_FILES if not (DASHBOARD_DIR / f).exists()]
    if missing:
        st.error(
            f"Missing dashboard data file(s): {missing}. These are produced by "
            "`python -m src.export` (Stage 8) — re-run the pipeline and redeploy."
        )
        st.stop()

    data["kpi"] = json.loads((DASHBOARD_DIR / "kpi_summary.json").read_text())
    data["model_metrics"] = json.loads((DASHBOARD_DIR / "model_metrics.json").read_text())
    data["benford_aggregate"] = pd.read_csv(DASHBOARD_DIR / "benford_aggregate.csv")
    data["benford_segments"] = pd.read_csv(DASHBOARD_DIR / "benford_segments.csv")
    data["benford_by_segment_digit"] = pd.read_csv(DASHBOARD_DIR / "benford_by_segment_digit.csv")
    data["monthly_trend"] = pd.read_csv(DASHBOARD_DIR / "monthly_trend.csv")
    data["segment_heatmap"] = pd.read_csv(DASHBOARD_DIR / "segment_heatmap.csv")
    data["method_comparison"] = pd.read_csv(DASHBOARD_DIR / "method_comparison.csv")
    data["top_risk_5000"] = pd.read_csv(DASHBOARD_DIR / "top_risk_5000.csv")
    data["top_risk_transactions"] = pd.read_csv(DASHBOARD_DIR / "top_risk_transactions.csv")
    if (DASHBOARD_DIR / "pr_curve_points.csv").exists():
        data["pr_curve_points"] = pd.read_csv(DASHBOARD_DIR / "pr_curve_points.csv")
    if (DASHBOARD_DIR / "precision_at_k.csv").exists():
        data["precision_at_k"] = pd.read_csv(DASHBOARD_DIR / "precision_at_k.csv")
    return data


def _verdict_color(verdict: str) -> str:
    return {
        "NONCONFORMING": PALETTE["risk"], "MARGINAL": PALETTE["warning"],
        "ACCEPTABLE": PALETTE["secondary"], "CLOSE": PALETTE["good"],
    }.get(str(verdict).upper(), PALETTE["neutral"])


def main() -> None:
    st.set_page_config(
        page_title="Audit Analytics — Transaction Anomaly Detection",
        page_icon="🔍", layout="wide",
    )
    data = load_dashboard_data()
    kpi = data["kpi"]
    mm = data["model_metrics"]

    st.title("🔍 Audit Analytics — Transaction Anomaly Detection")
    st.caption(
        "Benford's Law · Rule-Based Red Flags · Isolation Forest — a layered detection "
        "pipeline over a real 1.03M-row UK online-retail sales ledger."
    )
    st.warning(
        "**Demonstration project.** A controlled set of synthetic anomalies "
        "(1.5% of rows, 6 fraud archetypes) was injected into a real public dataset "
        "so detection accuracy could actually be measured — live audit data has no "
        "ground truth to score against. See the Limitations tab for details.",
        icon="ℹ️",
    )
    st.markdown(
        "[GitHub repository](.) · [Methodology](../docs/methodology.md) · "
        "[Audit findings workpaper (PDF)](../reports/audit_findings_workpaper.pdf)"
    )

    tabs = st.tabs([
        "Overview", "Benford's Law", "Anomaly Explorer", "Model Performance", "Segment Heatmap",
    ])

    # ================= Tab 1: Overview =================
    with tabs[0]:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total transactions", f"{kpi['total_txns']:,}")
        c2.metric("Total value", f"£{kpi['total_value']:,.0f}")
        c3.metric("Aggregate Benford MAD", f"{kpi['aggregate_mad']:.4f}", kpi["aggregate_verdict"])
        c4.metric("% scored pop. High/Critical risk", f"{kpi['pct_high_critical']:.1f}%")
        c5.metric("Precision@500 (top 500 reviewed)", f"{kpi['headline_precision_at_500']*100:.1f}%")

        col1, col2 = st.columns([2, 1])
        with col1:
            mt = data["monthly_trend"]
            fig = go.Figure()
            fig.add_bar(x=mt["year_month"], y=mt["txn_count"], name="Transactions", marker_color=PALETTE["tertiary"])
            fig.add_scatter(x=mt["year_month"], y=mt["pct_flagged"], name="% flagged (rules)",
                             yaxis="y2", line=dict(color=PALETTE["risk"], width=2))
            fig.update_layout(
                title="Monthly volume and % flagged", yaxis=dict(title="Transactions"),
                yaxis2=dict(title="% flagged", overlaying="y", side="right", ticksuffix="%"),
                legend=dict(orientation="h", y=1.1), height=420,
            )
            st.plotly_chart(fig, width='stretch')
            st.caption("Rule-flag rate is broadly stable month to month, with no single month dominating.")
        with col2:
            sh = data["segment_heatmap"]
            top_countries = sh.groupby("country")["txn_count"].sum().nlargest(10)
            fig2 = px.bar(top_countries, orientation="h", color_discrete_sequence=[PALETTE["primary"]],
                          labels={"value": "Transactions", "country": ""}, title="Top 10 countries by volume")
            fig2.update_layout(height=420, showlegend=False)
            st.plotly_chart(fig2, width='stretch')

        top50 = data["top_risk_transactions"]
        band_counts = top50["risk_band"].value_counts()
        fig3 = px.pie(names=band_counts.index, values=band_counts.values,
                      color=band_counts.index, color_discrete_map=BAND_COLORS,
                      title="Risk band split — top 50 review list", hole=0.4)
        st.plotly_chart(fig3, width='stretch')

        with st.expander("What this shows, in plain English"):
            st.write(
                f"The ledger has {kpi['total_txns']:,} transactions worth "
                f"£{kpi['total_value']:,.0f}. {kpi['n_segments_flagged']} of "
                f"{kpi['n_segments_assessed']} country-month segments assessed for "
                "Benford conformity were classified non-conforming. A composite risk "
                "score blending Isolation Forest, rule flags and Benford segment "
                "status ranks every scored transaction for review."
            )

    # ================= Tab 2: Benford's Law =================
    with tabs[1]:
        segs = data["benford_segments"]
        seg_values = ["All (aggregate)"] + sorted(segs["segment_value"].unique().tolist())
        choice = st.selectbox("Segment (country | year-month)", seg_values)

        agg = data["benford_aggregate"]
        by_digit = data["benford_by_segment_digit"]
        if choice == "All (aggregate)":
            plot_df = agg.rename(columns={"observed_prop": "observed", "expected_prop": "expected"})
            n_val, mad_val, verdict_val = mm["population"]["n_total"], kpi["aggregate_mad"], kpi["aggregate_verdict"]
        else:
            plot_df = by_digit[by_digit["segment_value"] == choice].rename(
                columns={"observed_prop": "observed", "expected_prop": "expected"})
            row = segs[segs["segment_value"] == choice].iloc[0]
            n_val, mad_val, verdict_val = int(row["n"]), float(row["mad"]), row["verdict"]

        c1, c2, c3 = st.columns(3)
        c1.metric("n", f"{n_val:,}")
        c2.metric("MAD", f"{mad_val:.4f}")
        c3.markdown(
            f"<div style='padding:0.5em;border-radius:6px;background:{_verdict_color(verdict_val)}22;"
            f"border-left:4px solid {_verdict_color(verdict_val)};'><b>{verdict_val}</b></div>",
            unsafe_allow_html=True,
        )

        fig = go.Figure()
        fig.add_bar(x=plot_df["digit"], y=plot_df["observed"], name="Observed", marker_color=PALETTE["primary"])
        fig.add_bar(x=plot_df["digit"], y=plot_df["expected"], name="Expected (Benford)", marker_color=PALETTE["tertiary"])
        fig.update_layout(barmode="group", title="Leading-digit distribution: observed vs expected",
                          xaxis=dict(title="Leading digit", tickmode="linear"), yaxis=dict(title="Proportion", tickformat=".0%"))
        st.plotly_chart(fig, width='stretch')

        st.info(
            f"At n = {n_val:,}, a chi-square test would reject conformity for deviations of no "
            "practical significance (the 'excess power' problem). **Mean Absolute Deviation (MAD) "
            "is the primary conformity criterion here**, per Nigrini's thresholds (Close <0.006, "
            "Acceptable <0.012, Marginal <0.015, Nonconformity ≥0.015)."
        )

        seg_sorted = segs.sort_values("mad", ascending=False)
        fig4 = px.bar(seg_sorted.head(20), x="mad", y="segment_value", orientation="h",
                     color="verdict", color_discrete_map={"NONCONFORMING": PALETTE["risk"]},
                     title="Top 20 segments by MAD")
        fig4.update_layout(height=550)
        st.plotly_chart(fig4, width='stretch')
        st.caption(
            "Benford's Law says the leading digit of naturally occurring numeric populations "
            "follows log10(1+1/d), not a uniform 1-in-9 split — deviation from that curve can "
            "indicate fabricated or rounded figures."
        )

    # ================= Tab 3: Anomaly Explorer =================
    with tabs[2]:
        top5000 = data["top_risk_5000"].copy()
        n_pos = mm["population"]["n_injected"]

        budget = st.slider("Review budget (transactions)", min_value=10, max_value=min(2000, len(top5000)), value=500, step=10)
        reviewed = top5000.head(budget)
        n_injected_in_budget = int((reviewed.get("risk_band").notna()).sum()) if "anomaly_type" not in reviewed else 0
        st.metric(f"Transactions reviewed", budget)
        st.caption(
            "Reviewing this many top-ranked transactions is the audit-realistic question: "
            "how much of the population must be looked at to find most of what matters."
        )

        col1, col2, col3, col4 = st.columns(4)
        band_filter = col1.multiselect("Risk band", options=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                                       default=["CRITICAL", "HIGH"])
        country_filter = col2.multiselect("Country", options=sorted(top5000["country"].dropna().unique().tolist()))
        min_amount = col3.number_input("Min amount (£)", value=0.0, step=100.0)
        search = col4.text_input("Search description")

        filtered = top5000[top5000["risk_band"].isin(band_filter)] if band_filter else top5000
        if country_filter:
            filtered = filtered[filtered["country"].isin(country_filter)]
        filtered = filtered[filtered["amount"].abs() >= min_amount]
        if search:
            filtered = filtered[filtered["description"].astype(str).str.contains(search, case=False, na=False)]

        st.dataframe(
            filtered[["risk_rank", "txn_id", "invoice_date", "customer_id", "country", "amount",
                      "composite_risk", "risk_band", "rule_flag_names", "suggested_procedure"]],
            width='stretch', height=420,
        )
        st.download_button(
            "Download top-50 review list (CSV)",
            data.get("top_risk_transactions").to_csv(index=False).encode(),
            file_name="top_50_review_list.csv", mime="text/csv",
        )

    # ================= Tab 4: Model Performance =================
    with tabs[3]:
        comp = mm["models"]["composite"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Average Precision", f"{comp['average_precision']:.4f}",
                  f"95% CI [{comp['ap_ci95'][0]:.3f}, {comp['ap_ci95'][1]:.3f}]")
        c2.metric("Precision (operating pt.)", f"{comp['precision']*100:.1f}%")
        c3.metric("Recall (operating pt.)", f"{comp['recall']*100:.1f}%")
        c4.metric("F1", f"{comp['f1']:.3f}")

        col1, col2 = st.columns(2)
        with col1:
            if "pr_curve_points" in data:
                pr = data["pr_curve_points"]
                fig = px.line(pr, x="recall", y="precision", title="Precision-Recall (composite score)")
                fig.add_hline(y=mm["baseline_precision"], line_dash="dash",
                             annotation_text=f"Random baseline ({mm['baseline_precision']:.4f})")
                st.plotly_chart(fig, width='stretch')
        with col2:
            if "precision_at_k" in data:
                pak = data["precision_at_k"]
                fig = px.line(pak, x="k", y="precision_at_k", color="method", log_x=True,
                             title="Precision@k by method")
                st.plotly_chart(fig, width='stretch')

        mc = data["method_comparison"]
        wide = mc.pivot(index="anomaly_type", columns="method", values="pct_caught")
        order = [i for i in wide.index if i not in ("ALL_INJECTED", "REAL_ROWS")] + ["ALL_INJECTED", "REAL_ROWS"]
        wide = wide.reindex(order)
        fig = px.imshow(wide, text_auto=".1f", color_continuous_scale="RdYlGn_r",
                        title="Method x anomaly-type detection matrix (% caught)", aspect="auto")
        st.plotly_chart(fig, width='stretch')

        with st.expander("Caveats (verbatim from model_metrics.json)"):
            for c in mm.get("caveats", []):
                st.markdown(f"- {c}")

    # ================= Tab 5: Segment Heatmap =================
    with tabs[4]:
        sh = data["segment_heatmap"]
        metric_choice = st.radio("Colour by", ["% flagged", "Benford MAD"], horizontal=True)
        value_col = "pct_flagged" if metric_choice == "% flagged" else "mad"
        top_countries = sh.groupby("country")["txn_count"].sum().nlargest(20).index
        grid = sh[sh["country"].isin(top_countries)].pivot(index="country", columns="year_month", values=value_col)
        fig = px.imshow(grid, color_continuous_scale="RdYlGn_r" if value_col == "pct_flagged" else "Reds",
                        aspect="auto", title=f"Country x month — {metric_choice}")
        st.plotly_chart(fig, width='stretch')

        flagged_segs = data["benford_segments"][data["benford_segments"]["is_flagged"]].sort_values("mad", ascending=False)
        st.dataframe(flagged_segs[["segment_value", "n", "mad", "verdict", "max_dev_digit"]], width='stretch')

    st.divider()
    st.caption(
        "Data: UCI Online Retail II (CC BY 4.0). Detection layers rank transactions for "
        "review — they do not, on their own, evidence fraud or misstatement."
    )


if __name__ == "__main__":
    main()
