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

## Manual items

| Item | Status |
|---|---|
| Repo made public, pushed to GitHub | **Done** — `https://github.com/vishalyl/benfords-audit-analytics`, per explicit user confirmation |
| GitHub Pages publish of `docs/index.html` | **Done and live** — `https://vishalyl.github.io/benfords-audit-analytics/`, enabled via `gh api repos/.../pages` (source: `main` branch, `/docs` path) |
| Live URL check | **HTTP 200 confirmed** 2026-09-13 05:34 UTC, and re-verified visually with a fresh headless-browser screenshot from the actual public URL (not a local run) — `docs/screenshots/web_live_github_pages.png` |
| Streamlit Community Cloud deploy (`share.streamlit.io`, GitHub OAuth) | **Not done** — requires an interactive click the agent cannot perform; the repo is now public so the user can do this in ~2 minutes whenever they choose |

## Live-URL check (plan sec 10.8 check 6)

```
$ curl -s -o /dev/null -w "HTTP %{http_code}\n" https://vishalyl.github.io/benfords-audit-analytics/
HTTP 200
```
Confirmed 2026-09-13 05:34 UTC, plus a full-page Playwright screenshot taken directly
against the live public URL in a fresh headless browser session (not the local dev
server) — all KPI cards, both SVG charts, the method x anomaly-type matrix, the top-10
table and the caveats list rendered correctly with zero console errors.

**GATE: PASS** — all automated checks pass, and the live-URL manual check is now
confirmed (previously recorded as pending user action per DECISIONS.md D-0001/D-0002).
