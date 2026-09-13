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

### D-0001: Power BI Desktop dashboard (Stage 9) out of scope for this run
- **Stage:** 9
- **Date:** 2026-09-12
- **Question:** Power BI Desktop is a Windows GUI application with no headless/CLI
  authoring path. It is not installed in this execution environment. How should Stage 9
  be handled by an autonomous coding agent?
- **Options considered:**
  1. Attempt `winget install Microsoft.PowerBI` and drive the GUI via OS-level automation.
  2. Prepare all data/theme/DAX/build-notes inputs and stop, handing over a mechanical
     build checklist for a human with Power BI Desktop installed.
  3. Skip Stage 9 entirely for this run. No `.pbix`, no theme.json, no build notes.
- **Decision:** Option 3, skip entirely, per explicit user instruction.
- **Rationale:** The user was asked directly and chose to drop Power BI from scope
  rather than have the agent spend time on GUI automation of uncertain reliability, or
  produce partially-useful prep artefacts for a stage that will not be completed this
  run. All data this stage would have consumed (`data/dashboard/*.csv/json`) is still
  produced in Stage 8, so a `.pbix` can be built later without re-running the pipeline.
- **Impact:** Definition-of-Done item "`dashboard/audit_analytics.pbix` opens and all 5
  pages render" is NOT satisfied by this run. `dashboard/` will contain no `.pbix`.
- **Reversible:** yes. Stage 9 can be run in a later session once Power BI Desktop is
  installed, using `data/dashboard/*` and `data/processed/dashboard_export.parquet`
  produced in Stage 8.

### D-0002: Public dashboard delivered as both Streamlit source and a live static GitHub Pages site
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
     `gh` CLI, genuinely live immediately, with zero manual steps.
  3. Both: ship the Streamlit app (matches stack, best interactivity) AND the static
     GitHub Pages fallback (live immediately, satisfies Definition of Done autonomously).
- **Decision:** Option 3, per explicit user instruction.
- **Rationale:** Satisfies both the letter of the plan (Streamlit, reusing `src/` logic
  conceptually via the same `data/dashboard/` contract) and the "live now" requirement
  (GitHub Pages, which needs no OAuth beyond the already-authenticated `gh` CLI).
- **Impact:** Extra `docs/index.html` static dashboard is built in addition to
  `app/streamlit_app.py`. README links both, labelled "interactive app (deploy step
  required)" and "instant-load summary (live now)".
- **Reversible:** yes. The user can deploy the Streamlit app later and swap the
  primary README link.

### D-0003: Stages 7 onward evaluate on the 50,000-row scored sample, not the full 1,030,804-row population
- **Stage:** 7
- **Date:** 2026-09-13
- **Question:** Stage 6 (`src/models.py`) was run with `--sample` and never re-run
  full-population; `transactions_scored.parquet` has 50,000 rows, one feature set, and
  one contamination level (not the FS-A/FS-B x 4-contamination grid the master plan
  specifies). Re-running Stage 6 full-population with the full grid was not requested
  and would cost significant additional time. How should Stage 7 (validation) proceed?
- **Options considered:**
  1. Stop and re-run Stage 6 full-population with the FS-A/FS-B x contamination grid
     before doing any validation.
  2. Proceed with Stage 7-13 using the 50,000-row scored sample as the evaluation
     population, disclosing this plainly everywhere the population size is quoted.
- **Decision:** Option 2, per explicit user instruction to proceed from Stage 7 onward.
- **Rationale:** The master plan's own contract (sec 0.2.3) is to decide and proceed
  rather than stall. The 50k sample does not contain all 16,874 injected rows, only the
  fraction that fell into the random 50k sample, so metrics describe detection
  performance on a genuine (if smaller) labelled population, not a toy one.
- **Impact:** Every population figure in Stages 7-13 (model_metrics.json,
  composite_summary.json, kpi_summary.json, README, PDF workpaper, resume bullets) is
  computed on n=50,000, not n=1,030,804. `data/dashboard/monthly_trend.csv` and
  `segment_heatmap.csv` are the exception. They are computed from the full
  1,030,804-row cleaned ledger because they need no model score.
- **Reversible:** yes. Re-running Stage 6 full-population and re-running
  `python -m src.validate && python -m src.export` would regenerate every downstream
  file against the full population without further code changes.

### D-0004: Complementarity assertion and the Benford segment flag, reported as found, not forced
- **Stage:** 7
- **Date:** 2026-09-13
- **Question:** Master plan gate_07 sec 7.7 checks 6-7 require (a) at least one anomaly
  type where `rules_any` beats `if_fsb_top` by >=20pp and vice versa, and (b)
  `benford_any`'s catch rate on `digit_fabrication` to clearly exceed its rate on
  `REAL_ROWS`. Actual computed numbers (`reports/metrics/model_metrics.json`,
  `data/dashboard/method_comparison.csv`) show neither holds: rules_any beats iforest
  on every single injected type (no type where IF wins by >=20pp), and `benford_any`
  flags 92-95% of rows almost uniformly, including 92.92% of REAL_ROWS, because all
  66 (country, year_month) segments assessed in Stage 4 were classified NONCONFORMING,
  so the segment flag carries almost no row-level discriminating power in this run.
- **Options considered:**
  1. Hard-fail gate 07 and go back to re-tune Stage 3 (injection design), Stage 5 (rule
     thresholds) and/or Stage 4 (segment classification thresholds) until the assertion
     passes.
  2. Report the true numbers, demote checks 6-7 to logged warnings rather than hard
     failures, and write the honest interpretation: in this run, rule-based checks are
     the strongest single layer at a matched 1.5% alert budget, Isolation Forest adds
     ranking value primarily through composite AP rather than raw catch-rate at that
     budget, and the segmented Benford test is population-level evidence of
     manipulation risk but is currently too sensitive to serve as a row-level flag.
- **Decision:** Option 2, per the master plan's own escape valve (plan sec 7.4: "If the
  measured numbers contradict that narrative, write what is true... A surprising result
  honestly explained is worth more than a tidy result") and the user's instruction to
  finish Stages 7-13 without looping back into earlier stages.
- **Rationale:** Re-tuning Stage 3-5 to force a specific assertion to pass, using the
  ground-truth labels as the tuning signal, is closer to fitting the test set than to
  honest validation. The master plan explicitly warns against exactly that pattern in
  a different context (sec 8.1.2). Reporting the real result is more defensible.
- **Impact:** `checks/gate_07.py` treats checks 6 and 7 as WARN (recorded, non-blocking)
  rather than FAIL. The README/PDF Key Findings section states the true finding (rules
  dominate catch-rate; Benford segment flag over-triggers in this run) instead of the
  plan's template narrative. This is itself a legitimate audit-analytics finding: it
  says the segment MAD/verdict thresholds inherited from Stage 4 need recalibration
  before the segment flag can be used as a review trigger, noted in Limitations.
- **Reversible:** yes. Revisiting Stage 4's classification thresholds or Stage 6's
  feature set is future work, tracked in the README "What I'd do next" section.

### D-0005: README numbers come from a placeholder template; narrative prose is hand-written but number-checked
- **Stage:** 11
- **Date:** 2026-09-13
- **Question:** Plan sec 11.3 requires `src/report_fill.py` to replace `{{metric.path}}`
  placeholders in `README.template.md` from `reports/metrics/*.json`, failing loudly on
  any unresolved placeholder. Should every single number anywhere in the README
  (including multi-sentence interpretive paragraphs) go through a `{{}}` placeholder, or
  only the headline stats table?
- **Options considered:**
  1. Placeholder-ize literally every digit in the README, including inside narrative
     sentences. That maximises mechanical enforcement but produces stilted, hard-to-read
     prose and placeholders for things like "which digit is driving a given segment"
     that live in CSVs, not the JSON files `report_fill.py` reads.
  2. Placeholder-ize the headline stats table and the single-sentence pull-quote (the
     numbers most likely to be copy-paste-drifted or hand-fabricated), and hand-write
     the surrounding interpretive prose, keeping every number in it manually verified
     against the same JSON files before writing.
- **Decision:** Option 2.
- **Rationale:** The plan's stated goal (sec 11.3) is eliminating "a README quoting
  numbers the code no longer produces", achieved by the table going through
  `report_fill.py` and failing the build on drift. `checks/gate_11.py` C4 verifies the
  generator actually ran (the `<!-- generated -->` marker) rather than trying to prove
  every prose sentence's provenance mechanically.
- **Impact:** `README.template.md` has ~25 `{{}}` placeholders across the stats table,
  the hook sentence and the method x anomaly-type matrix; narrative sections (Key
  Findings interpretation, Limitations, What I'd do next) are prose, hand-checked
  against `reports/metrics/model_metrics.json` and `data/dashboard/kpi_summary.json`.
- **Reversible:** yes. More of the prose could be placeholder-ized later if the
  narrative numbers ever need to change with the data.

### D-0006: Personal-path scrub check adapted, since the literal "visha" grep also matches the owner's real name
- **Stage:** 13
- **Date:** 2026-09-13
- **Question:** Plan sec 13.3 check 3 specifies a case-insensitive grep for the
  Windows username plus a generic `C:\Users` prefix, intended to catch leaked local
  absolute filesystem paths pointing into this machine's home directory. But the
  project owner's real name, "Y.L. Vishal", contains the username as a substring,
  the literal check would flag every legitimate authorship
  mention (`plan/00_MASTER_PLAN.md`'s own "Owner: Y.L. Vishal" line, `DECISIONS.md`,
  gate reports, `reports/audit_findings_workpaper.pdf`'s "Prepared by" field). Should
  the agent scrub the owner's name from the repo, or adapt the check?
- **Options considered:**
  1. Scrub "Vishal"/"visha" everywhere to satisfy the literal grep. This removes legitimate
     authorship attribution the user would presumably want kept.
  2. Adapt `checks/gate_13.py`'s check to search for the actual leaked-path pattern
     (this machine's home-directory prefix, e.g. the literal string baked into the
     regex in `checks/gate_13.py`) rather than the bare username, which catches the
     real privacy/security concern the check exists for without penalizing the
     person's name in an attribution field.
- **Decision:** Option 2.
- **Rationale:** The check's stated purpose (plan sec 13.2 publish checklist: "no
  personal paths anywhere") is about leaked local filesystem structure, not about
  removing the author's name from their own project. Running the adapted check did
  find one real leak: `reports/gate_reports/gate_00.md` had printed the absolute
  interpreter path from Stage 0, which was fixed (replaced with `<repo-root>\...`).
- **Impact:** `checks/gate_13.py` C3 greps for the actual leaked-path pattern rather
  than bare "visha", scoped to exclude `plan/` (which legitimately states the owner's
  name in its own header) and its own source file (which necessarily contains that
  pattern as a string literal to search for it). `checks/gate_00.py` was fixed to
  redact the repo-root prefix from `sys.executable` before writing it into
  `reports/gate_reports/gate_00.md`, since it had been silently re-leaking the
  absolute path on every re-run.
- **Reversible:** yes. The literal check can be restored if the user prefers the repo
  to carry no name at all, at the cost of also stripping the "Prepared by" field from
  the workpaper and the plan's own ownership line.

### D-0007: Stage 6 re-run at full population, resolving D-0003, and a LOF wiring bug it exposed
- **Stage:** 6-8 (re-run, post-publish)
- **Date:** 2026-09-13
- **Question:** D-0003 logged Stage 6 running on a 50,000-row sample as an accepted
  limitation. The user asked for it to be re-run at full population. Doing so
  immediately crashed `src/models.py`: `_compute_lof` subsamples internally to 150,000
  rows once the population exceeds that (via `cfg.model.lof_subsample_n`), but the
  caller assumed it returned a score for every input row. At 50,000 rows the subsample
  threshold was never hit, so this mismatch had never been exercised.
- **Options considered:**
  1. Raise `lof_subsample_n` above the full population size so the bug path is never
     hit, avoiding the fix but making LOF computationally unrealistic at scale.
  2. Fix `_compute_lof` to return a full-length array (0.0 outside the subsample) plus
     a new `lof_in_subsample` boolean, and scope every LOF-specific calculation
     (threshold, ranking metrics, bootstrap CI) to `lof_in_subsample == True`, while the
     binary catch-rate still spans the full population so it honestly reflects LOF's
     real coverage limit.
- **Decision:** Option 2.
- **Rationale:** The master plan's own schema (sec 8.3) already names a
  `lof_in_subsample` companion column for exactly this reason; the code had just never
  wired it through. Option 1 would have hidden a real scalability constraint rather
  than modelling it.
- **Impact:** `src/models.py`, `src/validate.py`, `src/export.py`,
  `src/data_dictionary.py` updated. Full-population results (n=1,030,804):
  composite AP 0.166 (was 0.182 at 50k), rules still beat Isolation Forest on every
  injected type at a matched budget (an even larger margin on `extreme_outlier`, 60.4pp
  vs 52.75pp at 50k), so D-0004's finding is not a small-sample artefact. LOF's own AP
  (0.055) is now computed only on its 150,000-row (14.6%) subsample, with a `note` field
  in `model_metrics.json` explaining the coverage/quality distinction. Also fixed:
  `load_evaluation_frame`'s Benford-flag join was a per-row `.apply`, too slow at
  1M-row scale, replaced with a vectorised membership test; and a spurious
  floating-point non-determinism in `if_pct` (from `IsolationForest(n_jobs=-1)`'s
  parallel score reduction differing in its last bit run to run) was fixed by rounding
  it to 6dp, matching every other score column's convention.
- **Reversible:** yes. `lof_subsample_n` in `config.yaml` can be raised if a future
  machine can afford full-population LOF; nothing else in the pipeline assumes 150,000.
