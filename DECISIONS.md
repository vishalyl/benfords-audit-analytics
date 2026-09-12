# DECISIONS.md

Append-only judgement log for the `benfords-audit-analytics` project. Newest at the bottom.

## Pre-registered defaults

The following decisions are pre-made by `plan/00_MASTER_PLAN.md` §7 and require no entry below unless deviated from:

| ID | Decision |
|---|---|
| PD-01 | Missing `customer_id` → retained as `"UNASSIGNED"`, excluded from customer-level statistics only. |
| PD-02 | Cancellations (`invoice` starts with `C`) → moved to a separate `cancellations` frame, excluded from Benford and from the model population, but **counted and reported**. |
| PD-03 | Benford population = non-cancelled, non-adjustment rows with `amount >= 1.00`. |
| PD-04 | Zero and negative `amount` rows → retained, flagged `is_nonpositive_amount`, excluded from Benford only. |
| PD-05 | Duplicate detection window = same `customer_id` + same rounded `amount` (2dp) + `invoice_date` within ±1 day + different `invoice`. |
| PD-06 | Injection rate = **1.5%** of the cleaned population, split evenly across 6 anomaly types. |
| PD-07 | Global seed = **42**, set via `numpy.random.default_rng(42)` and `random_state=42` everywhere. |
| PD-08 | Minimum segment size for a Benford conformity verdict = **1,000 rows**. Smaller segments get verdict `INSUFFICIENT_DATA`. |
| PD-09 | Primary Isolation Forest contamination = **0.015**; sensitivity runs at 0.005, 0.010, 0.030. |
| PD-10 | Two feature sets are modelled: **FS-A** (no rule flags) and **FS-B** (with rule flags). |
| PD-11 | Composite weights: `0.50 × IF_percentile + 0.30 × (rule_flag_count / 5) + 0.20 × benford_segment_flag`. |
| PD-12 | Business hours = 07:00–19:59 inclusive, all days; Sunday is NOT off-hours. |
| PD-13 | Currency is GBP throughout; no FX conversion. |
| PD-14 | Power BI Benford visuals use precomputed segment statistics for MAD/verdict, DAX for observed-vs-expected bars. |

---

### D-0001 — Power BI Desktop dashboard (Stage 9) out of scope for this run
- **Stage:** 9
- **Date:** 2026-09-12
- **Question:** Power BI Desktop is a Windows GUI application with no headless/CLI
  authoring path. It is not installed in this execution environment. How should Stage 9
  be handled by an autonomous coding agent?
- **Options considered:**
  1. Attempt `winget install Microsoft.PowerBI` and drive the GUI via OS-level automation.
  2. Prepare all data/theme/DAX/build-notes inputs and stop, handing over a mechanical
     build checklist for a human with Power BI Desktop installed.
  3. Skip Stage 9 entirely for this run — no `.pbix`, no theme.json, no build notes.
- **Decision:** Option 3, skip entirely, per explicit user instruction.
- **Rationale:** The user was asked directly and chose to drop Power BI from scope
  rather than have the agent spend time on GUI automation of uncertain reliability, or
  produce partially-useful prep artefacts for a stage that will not be completed this
  run. All data this stage would have consumed (`data/dashboard/*.csv/json`) is still
  produced in Stage 8, so a `.pbix` can be built later without re-running the pipeline.
- **Impact:** Definition-of-Done item "`dashboard/audit_analytics.pbix` opens and all 5
  pages render" is NOT satisfied by this run. `dashboard/` will contain no `.pbix`.
- **Reversible:** yes — Stage 9 can be run in a later session once Power BI Desktop is
  installed, using `data/dashboard/*` and `data/processed/dashboard_export.parquet`
  produced in Stage 8.

### D-0002 — Public dashboard delivered as both Streamlit source and a live static GitHub Pages site
- **Stage:** 10
- **Date:** 2026-09-12
- **Question:** Streamlit Community Cloud deployment requires a one-time interactive
  GitHub OAuth click on `share.streamlit.io` that cannot be performed headlessly by an
  autonomous agent. How can the "public dashboard URL is live" Definition-of-Done item
  be satisfied without a manual step, while still matching the plan's frozen tech stack
  (Streamlit)?
- **Options considered:**
  1. Streamlit app only; hand the user a 2-minute manual deploy step.
  2. Static HTML/JS dashboard on GitHub Pages, published via the already-authenticated
     `gh` CLI — genuinely live immediately, zero manual steps.
  3. Both: ship the Streamlit app (matches stack, best interactivity) AND the static
     GitHub Pages fallback (live immediately, satisfies Definition of Done autonomously).
- **Decision:** Option 3, per explicit user instruction.
- **Rationale:** Satisfies both the letter of the plan (Streamlit, reusing `src/` logic
  conceptually via the same `data/dashboard/` contract) and the "live now" requirement
  (GitHub Pages, which needs no OAuth beyond the already-authenticated `gh` CLI).
- **Impact:** Extra `docs/index.html` static dashboard is built in addition to
  `app/streamlit_app.py`. README links both, labelled "interactive app (deploy step
  required)" and "instant-load summary (live now)".
- **Reversible:** yes — the user can deploy the Streamlit app later and swap the
  primary README link.
