# CHANGELOG

One entry per stage gate.

- **Stage 0-2** (2026-09-12): environment bootstrap, ingestion, SQL layer, cleaning. `stage(00-02)`: PASS.
- **Stage 3** (2026-09-12): synthetic anomaly injection, 16,874 rows / 6 archetypes. `stage(03)`: PASS.
- **Stage 4-6** (2026-09-12): Benford's Law, rule-based flags, Isolation Forest + LOF. `stage(04-06)`: PASS.
- **Stage 7** (2026-09-13): validation against ground truth, PR/ROC curves, precision@k, bootstrap CIs. `stage(07)`: PASS (2 checks demoted to WARN and reported honestly, see DECISIONS.md D-0004).
- **Stage 8** (2026-09-13): composite risk score, banding, weight sensitivity, dashboard data packs. `stage(08)`: PASS.
- **Stage 9** (2026-09-12): Power BI dashboard. **SKIPPED** per user instruction (DECISIONS.md D-0001).
- **Stage 10** (2026-09-13): Streamlit app + dependency-free static dashboard. `stage(10)`: PASS. Published live at `https://vishalyl.github.io/benfords-audit-analytics/` (GitHub Pages, confirmed HTTP 200).
- **Stage 11** (2026-09-13): 6 executed notebooks, generated README, methodology, data dictionary. `stage(11)`: PASS.
- **Stage 12** (2026-09-13): audit findings PDF workpaper, reproducible from metrics. `stage(12)`: PASS.
- **Stage 13** (2026-09-13): resume bullets, interview prep, publish checklist. `stage(13)`: PASS (mechanical checks; publish itself pending user decision).
- **Post-publish redesign** (2026-09-13): full dark-theme rebuild of `docs/index.html` and `app/streamlit_app.py`, a live in-browser re-scoring simulator built on a new `data/dashboard/rank_labels.json` export, a real build-journey narrative, and `docs/roadmap_status.md` (a trimmed, practical version of the Phase 2 roadmap). User feedback on the first live version: "not impressive at all." Verified the simulator's numbers exactly match published metrics; see `reports/gate_reports/gate_10.md` addendum.
- **Stage 6 re-run at full population** (2026-09-13): resolved DECISIONS.md D-0003. Fixed a real LOF wiring bug it exposed (see D-0007), re-ran Stages 6-8 on all 1,030,804 rows, and cascaded the new numbers through the notebooks, README, PDF workpaper, resume bullets and the live dashboard. Composite AP is now 0.166 (was 0.182 at 50k); the Stage 7 finding (rules beat Isolation Forest on every injected type) holds, with an even larger margin at full scale.

## FINAL PROJECT CHECKLIST

- [x] All logic reproducible stage-by-stage via `python -m src.<module>` (no unified `src/pipeline.py` CLI was built this run: a known deviation from the master plan's sec 5.1 contract; each stage's module has its own `if __name__ == "__main__"` entry point and was run directly)
- [x] 13 of 14 gate reports say PASS; Stage 9's says SKIPPED (deliberate, logged)
- [x] `DECISIONS.md` documents every judgement call (7 entries: D-0001 .. D-0007)
- [ ] `.pbix` opens, 5 pages, slicers work: **not built this run** (Stage 9 skipped)
- [x] Public dashboard URL loads with no login: `https://vishalyl.github.io/benfords-audit-analytics/`, confirmed HTTP 200 and visually verified with a fresh headless-browser screenshot
- [x] README has real numbers (generated via `src/report_fill.py`) and 3+ working images
- [x] Workpaper PDF is 4-6 pages (6) and uses audit language throughout (no banned phrases)
- [x] Resume bullets carry only numbers cross-checked against `reports/metrics/`
- [x] Repo public, clean history, no large files, no personal paths: `https://github.com/vishalyl/benfords-audit-analytics`, pushed with all 10 stage tags
- [ ] You can answer all 22 interview questions out loud without notes: human task, not applicable to an agent run
