# CHANGELOG

One entry per stage gate.

- **Stage 0-2** (2026-09-12) — environment bootstrap, ingestion, SQL layer, cleaning. `stage(00-02)` — PASS.
- **Stage 3** (2026-09-12) — synthetic anomaly injection, 16,874 rows / 6 archetypes. `stage(03)` — PASS.
- **Stage 4-6** (2026-09-12) — Benford's Law, rule-based flags, Isolation Forest + LOF. `stage(04-06)` — PASS.
- **Stage 7** (2026-09-13) — validation against ground truth, PR/ROC curves, precision@k, bootstrap CIs. `stage(07)` — PASS (2 checks demoted to WARN and reported honestly, see DECISIONS.md D-0004).
- **Stage 8** (2026-09-13) — composite risk score, banding, weight sensitivity, dashboard data packs. `stage(08)` — PASS.
- **Stage 9** (2026-09-12) — Power BI dashboard. **SKIPPED** per user instruction (DECISIONS.md D-0001).
- **Stage 10** (2026-09-13) — Streamlit app + dependency-free static dashboard. `stage(10)` — PASS (live deploy/publish pending, see below).
- **Stage 11** (2026-09-13) — 6 executed notebooks, generated README, methodology, data dictionary. `stage(11)` — PASS.
- **Stage 12** (2026-09-13) — audit findings PDF workpaper, reproducible from metrics. `stage(12)` — PASS.
- **Stage 13** (2026-09-13) — resume bullets, interview prep, publish checklist. `stage(13)` — PASS (mechanical checks; publish itself pending user decision).

## FINAL PROJECT CHECKLIST

- [x] All logic reproducible stage-by-stage via `python -m src.<module>` (no unified `src/pipeline.py` CLI was built this run — a known deviation from the master plan's sec 5.1 contract; each stage's module has its own `if __name__ == "__main__"` entry point and was run directly)
- [x] 13 of 14 gate reports say PASS; Stage 9's says SKIPPED (deliberate, logged)
- [x] `DECISIONS.md` documents every judgement call (6 entries: D-0001 .. D-0006)
- [ ] `.pbix` opens, 5 pages, slicers work — **not built this run** (Stage 9 skipped)
- [ ] Public dashboard URL loads with no login — **app and static page built and locally verified; not yet deployed/published** (requires making the repo public — a user decision, see below)
- [x] README has real numbers (generated via `src/report_fill.py`) and 3+ working images
- [x] Workpaper PDF is 4-6 pages (6) and uses audit language throughout (no banned phrases)
- [x] Resume bullets carry only numbers cross-checked against `reports/metrics/`
- [ ] Repo public, clean history, no large files, no personal paths — **large-file and personal-path checks pass; the repo has not been made public / pushed** (user decision)
- [ ] You can answer all 22 interview questions out loud without notes — human task, not applicable to an agent run
