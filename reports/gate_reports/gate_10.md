# Gate 10 — Public Web Dashboard

**Stage:** 10 · **Date:** 2026-09-13 · **Gate:** `checks/gate_10.py` → **PASS** (automated checks)

## Two deliverables (per DECISIONS.md D-0002)

| Deliverable | File | Status |
|---|---|---|
| Interactive app (5 tabs mirroring the Power BI page spec) | `app/streamlit_app.py`, `app/requirements.txt`, `app/.streamlit/config.toml` | Built, smoke-tested (Streamlit `AppTest`, 0 exceptions) |
| Instant-load static summary (no server, no OAuth, always live) | `docs/index.html` | Built, generated from `data/dashboard/*` via `src/static_dashboard.py`, 15.6 KB, zero external dependencies (inline SVG, no CDN) |

## Why both

Streamlit Community Cloud deployment requires an interactive GitHub OAuth click on
`share.streamlit.io` that cannot be performed headlessly by an autonomous agent. The
static page needs no such step — it is a plain file GitHub Pages serves directly — so
the "public dashboard URL is live" requirement can be met without a manual step, while
the Streamlit app still ships as source (matching the plan's frozen tech stack) and can
be deployed by the user in ~2 minutes by clicking through `share.streamlit.io`.

**Note on the static page's charts:** an initial version used Chart.js from a CDN, but
in this execution sandbox the CDN request was blocked (`ERR_BLOCKED_BY_ORB`), which
would have shipped a page with silently blank charts to any visitor on a similarly
restrictive network. Rewrote the two charts as plain inline SVG generated server-side
in Python — zero external requests, verified with a headless-browser console-error
check (0 errors) and a full-page screenshot.

## Automated gate checks

```
GATE 10: PASS
C1 PASS: app/streamlit_app.py, app/requirements.txt and docs/index.html exist
C2 PASS: data/dashboard/ has 12 files, 1.37 MB < 25 MB
C3a PASS: app/streamlit_app.py parses as valid Python
C3b PASS: load_dashboard_data() returned all 10 expected keys
C4 PASS: no reference to data/processed or data/raw in app source
C5 PASS: app/requirements.txt excludes scikit-learn, openpyxl, jupyter
C6 PASS: 4 web_*.png screenshots >50KB
```

## Screenshots

`docs/screenshots/web_overview.png`, `web_benford.png`, `web_anomaly_explorer.png`,
`web_model_performance.png` — captured via Playwright (headless Chromium, 1920×1080)
against the app running locally (`streamlit run app/streamlit_app.py`).

## Manual items — pending user action

| Item | Status |
|---|---|
| Streamlit Community Cloud deploy (`share.streamlit.io`, GitHub OAuth) | **Not done** — requires an interactive click; user can do this in ~2 minutes once the repo is public |
| GitHub Pages publish of `docs/index.html` | **Not done in this session** — requires the repo to be pushed to GitHub and made public first; see the final publish decision at the end of this run |
| Live URL recorded here with an HTTP 200 timestamp | Pending the above |

**GATE: PASS** (automated checks only; live-URL manual check recorded above as pending,
consistent with DECISIONS.md D-0001/D-0002 — publishing the repo is a user decision,
not made silently by the agent).
