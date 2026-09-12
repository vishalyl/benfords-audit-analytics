# PHASE 2 — FUTURE ROADMAP (the advanced build)

**Document ID:** `05_FUTURE_ROADMAP`
**Status:** DO NOT START until every Phase 1 gate (00–13) has passed and v1.0 is tagged and public.
**Purpose:** absorb every "wouldn't it be great if" so it does not contaminate Phase 1.

---

## 0. Entry criteria

Phase 2 begins only when **all** of these are true:

- [ ] `git tag v1.0` exists and is pushed
- [ ] The public dashboard URL has been live and working for at least 48 hours
- [ ] The README has been read end-to-end by at least one other person
- [ ] You can deliver the 3-minute pitch without notes

If any is unticked, finishing Phase 1 is worth more than starting Phase 2. A complete
modest project beats an abandoned ambitious one, every time.

## 0.1 How to pick what to do next

Phase 2 is a menu, not a sequence. Choose by what the role you are applying for rewards:

| If you are targeting… | Do these tracks, in this order |
|---|---|
| Big 4 / forensic audit | A (GL data), F (workpaper automation), C (explainability), H (sampling & materiality) |
| Data analyst / BI | E (engineering rigour), I (semantic model & richer BI), J (alt dashboards) |
| Data science / ML | B (model depth), C (explainability), D (evaluation depth) |
| Fintech risk / fraud ops | D (evaluation depth), G (streaming & alert triage), C (explainability) |

Each track below lists: the goal, the work, the new resume line it earns, and a rough
effort estimate.

---

# TRACK A — Make the data look like a real audit population

**Why:** the biggest honest weakness in Phase 1 is that a retail sales ledger has no
journal entries, no posting user, no account codes, and no approval workflow — so
several of the most important real-world red flags cannot be tested.

### A1. Synthetic general ledger layer *(2–3 days)*
Generate a plausible GL on top of the transactions: account codes (revenue, receivables,
VAT, discounts), debit/credit pairs, journal IDs, posting user IDs, posting timestamps
distinct from transaction timestamps, source system (`AUTO` vs `MANUAL`), and approval
status. Every sales line becomes a balanced journal. Now you can test:
- Entries posted by a user who also approves them (segregation of duties)
- Manual entries to revenue accounts
- Entries posted after period close but dated before it (**the single most valuable
  real-world red flag, and it is impossible in Phase 1**)
- Round-number journals to unusual account combinations
- Entries by users with no other activity that month
- Entries posted on weekends or holidays by specific users

**Earns:** "Designed a synthetic general-ledger layer enabling journal-entry testing
(segregation of duties, post-close postings, manual-entry concentration) consistent with
ISA 240 journal-entry procedures."

### A2. Vendor / payables mirror *(1–2 days)*
Re-cast the same engine against a synthetic accounts-payable population: vendors, POs,
invoices, payments, bank details. Enables duplicate-payment testing, vendor-employee
address matching, ghost-vendor detection, and split-PO structuring — the classic
procurement fraud suite.

### A3. Multi-entity / multi-currency *(1 day)*
Add entity and currency dimensions with FX rates. Enables intercompany anomaly testing
and shows you can handle a consolidation.

### A4. Adversarial anomaly injection *(2 days)*
Add a seventh archetype: anomalies designed *specifically to evade* your Phase 1
detectors — amounts just outside the threshold bands, duplicates with a 3-day gap,
fabricated digits spread thinly across many segments. Then measure how much recall drops.
This is the most intellectually honest thing you can add, and it is a genuinely
interesting interview story: "I tried to beat my own model, and here is by how much it
won."

---

# TRACK B — Model depth

### B1. Model bake-off *(2 days)*
Add and compare, on identical features and the same evaluation harness:
`OneClassSVM` (on a subsample — it does not scale), `EllipticEnvelope`, `HBOS`,
`COPOD` and `ECOD` (from `pyod`), and a shallow **autoencoder** (Keras or PyTorch) scored
by reconstruction error. Report AP, precision@k and runtime for each, in one table.
Conclude with which you would actually deploy and why — runtime and explainability
usually beat a 0.01 AP gain, and saying so is the mature answer.

### B2. Supervised benchmark as an upper bound *(1 day)*
Train `LogisticRegression` and `LightGBM`/`XGBoost` on the labels with proper
cross-validation. This is **not** a deployable model (real engagements have no labels) —
it is the *ceiling*. Framing it as "here is how much signal exists in these features at
all, and my unsupervised model captures x% of that ceiling" is a strong, unusual
analysis.

### B3. Ensembling *(1 day)*
Rank-average the unsupervised models; compare to the best single model and to the
Phase 1 composite. Report whether ensembling helps, honestly.

### B4. Time-series anomaly detection *(2 days)*
Move from row-level to series-level: per customer and per (country, month), detect level
shifts, seasonality breaks and volume spikes (STL decomposition, Prophet, or a simple
rolling z-score). Audit-relevant because revenue manipulation often shows up as a
pattern break, not a single odd row.

### B5. Graph analysis *(2–3 days)*
Build a customer–product (or, with Track A2, vendor–invoice–payment) bipartite graph.
Look for unusual communities, customers whose purchase mix suddenly matches another's,
and circular flows. `networkx` is enough at this scale. Visually spectacular in a
dashboard and rare in a portfolio.

---

# TRACK C — Explainability

### C1. SHAP for Isolation Forest *(1 day)*
`shap.TreeExplainer` supports Isolation Forest. Produce: a global bar of mean |SHAP| per
feature, a beeswarm, and — most importantly — a **per-transaction waterfall** for each of
the top 25 review items. Embed these in the drill-through page and the workpaper.

**Earns:** "Added SHAP-based per-transaction explanations so every flagged item carries
an auditable rationale rather than an opaque score."

### C2. Natural-language finding generator *(1 day)*
A template engine that turns each flagged transaction's signals into a sentence an
auditor could paste into a workpaper. Rules-based (not an LLM) so it is deterministic
and defensible. Phase 1's `suggested_procedure` is the seed; this extends it to a full
finding narrative with criteria/condition/effect.

### C3. Counterfactuals *(1 day)*
For each top item: "this transaction would drop out of the top 500 if its amount were
below £X" — computed by perturbing one feature at a time. Makes the score tangible.

### C4. Model card *(half day)*
A one-page model card: intended use, out-of-scope uses, training data, evaluation data,
metrics with CIs, known limitations, and ethical considerations (false-accusation risk,
the need for human review before any action). Rare in portfolios and increasingly asked
about.

---

# TRACK D — Evaluation depth

### D1. Repeated-seed stability *(1 day)*
Re-run injection + detection across 20 seeds; report mean and 95% interval for every
headline metric. Turns "AP = 0.41" into "AP = 0.41 ± 0.03 across 20 independent
injections", which is a materially stronger claim.

### D2. Injection-rate sensitivity *(1 day)*
Sweep the injection rate 0.1% → 5%. Detection gets harder as anomalies get rarer; show
the curve. Directly addresses "but real fraud is much rarer than 1.5%".

### D3. Cost-based evaluation *(1 day)*
Attach a cost model: reviewer time per item (say 15 minutes), and a loss avoided per
anomaly caught (say the transaction value). Compute expected net benefit vs review
budget and find the optimal alert threshold *economically* rather than by F1. This is the
single most persuasive analysis for a manager audience, and almost nobody does it.

### D4. Drift and temporal validation *(1 day)*
Train on 2009–2010, score 2011. Real deployments train on history and score the future;
random splits flatter the model. Report the degradation.

### D5. Inter-method agreement statistics *(half day)*
Cohen's kappa between each pair of methods, plus a proper upset/Venn analysis of which
anomalies only one method catches. Formalises the Phase 1 complementarity claim.

---

# TRACK E — Engineering rigour

### E1. pytest suite *(2 days)*
Target ≥80% coverage on `src/`. Must include: the Benford constants, digit extraction
edge cases (0.99, 1.00, 9.99, negative, null), each rule's boundary conditions, the
leakage guard, the composite score range, and a golden-file test on a 1,000-row fixture
that catches any silent numeric change.

### E2. GitHub Actions CI *(half day)*
On push: ruff + black --check + mypy + pytest on the fixture. A green badge in the README
is disproportionately persuasive to engineering reviewers.

### E3. Data validation with Pandera or Great Expectations *(1 day)*
Declarative schema contracts at every stage boundary, replacing ad-hoc assertions. Emit a
data-quality report as an artefact — which doubles as audit evidence of data reliability,
so it serves both audiences.

### E4. Orchestration *(1–2 days)*
Convert `pipeline.py` into a Prefect or Dagster flow with task-level retries, caching and
a visual DAG. Screenshot the DAG for the README.

### E5. Containerisation *(half day)*
A Dockerfile plus `docker compose up` that runs the pipeline and serves the dashboard.
Removes every "works on my machine" objection.

### E6. dbt on DuckDB *(2 days)*
Re-implement the SQL layer as dbt models on DuckDB (far faster than SQLite here), with
`dbt test` assertions and auto-generated lineage docs. dbt appears in a large share of
analytics job descriptions and is the highest-ROI single tool to add.

### E7. Performance pass *(1 day)*
Profile the pipeline; move the heavy joins and the duplicate detection to Polars or
DuckDB; report the before/after runtime table. "Reduced end-to-end runtime from 22 to 6
minutes" is a concrete engineering bullet.

---

# TRACK F — Workpaper and reporting automation

### F1. Parameterised workpapers *(1 day)*
Generate a per-segment workpaper PDF for every flagged segment automatically, each with
its own charts, exception schedule and sign-off block. Demonstrates you can industrialise
a deliverable, not just produce one.

### F2. Excel exception pack *(1 day)*
The output format audit teams actually use: a formatted `.xlsx` with a summary tab, one
tab per test, conditional formatting, freeze panes, filters, and a tab for reviewer
sign-off with data-validation dropdowns.

### F3. Executive one-pager *(half day)*
A single A4 page for a partner: three numbers, one chart, three recommendations.

### F4. Scheduled monitoring *(1 day)*
A scheduled job that re-runs detection on the latest period and emails a delta report —
"14 new items above threshold this month, 3 in segments newly classified nonconforming."
Shows you think in terms of continuous auditing, not one-off analysis.

---

# TRACK G — Streaming and alert triage

### G1. Near-real-time scoring *(2 days)*
A FastAPI service exposing `POST /score` that accepts a transaction and returns a risk
score plus reasons, with the model loaded once at startup. Add a latency benchmark.

### G2. Alert triage workflow *(2 days)*
A queue UI: reviewers see items ranked, mark each `True issue / Explained / False
positive`, and their dispositions are stored. Then feed those dispositions back as labels
for a supervised re-ranker — the real lifecycle of a detection system.

### G3. Feedback loop and threshold auto-tuning *(1 day)*
Adjust the alert threshold to hold a target precision as dispositions accumulate.

---

# TRACK H — Audit methodology depth

### H1. Materiality and sampling *(1 day)*
Set a performance materiality figure, compute which flagged items are individually
material, and implement **monetary unit sampling (MUS)** over the population as a
complementary selection method. Compare MUS selections against risk-score selections — a
genuinely audit-specific analysis that a forensic interviewer will recognise instantly.

### H2. Stratified population analysis *(half day)*
Standard audit stratification by value band, with coverage percentages (e.g. "the top 2%
of items by value represent 47% of revenue").

### H3. Controls mapping *(half day)*
Map each detection test to the control it tests and the assertion it addresses
(occurrence, cut-off, accuracy, completeness). A short table; enormous credibility.

### H4. ISA 240 alignment note *(half day)*
One page mapping the procedures to the journal-entry testing requirements of ISA 240 /
AU-C 240. Cite the standard correctly and do not overclaim compliance — frame it as
"procedures consistent with".

### H5. Second-partner review simulation *(half day)*
A reviewer's checklist applied to your own workpaper, with your responses. Shows you
understand the review process, not just the analysis.

---

# TRACK I — Richer BI

### I1. Power BI semantic model polish *(1 day)*
Proper hierarchies, display folders, field descriptions, format strings, KPI definitions,
row-level security demo, and a bookmark-driven navigation bar.

### I2. Performance tuning *(1 day)*
Replace the heavy dynamic MAD measure with aggregation tables; document the before/after
with Performance Analyzer timings. A real BI-engineering skill.

### I3. Paginated report *(half day)*
A Power BI paginated report (or a Report Builder equivalent) for the exception schedule —
the print-ready format audit teams file.

### I4. Tableau parallel build *(1–2 days)*
The same five views in Tableau Public — which *is* publicly shareable for free, giving a
second live link and a second tool keyword.

---

# TRACK J — Alternative front-ends

### J1. Static HTML/JS dashboard on GitHub Pages *(1–2 days)*
Never sleeps, instant load, no platform dependency. Good insurance for the resume link.

### J2. Quarto or Jupyter Book site *(1 day)*
Publish the notebooks as a navigable documentation site with executed outputs.

### J3. Interactive notebook on Binder or Colab *(half day)*
A "Run this yourself" badge in the README, pointed at a sampled dataset.

---

# TRACK K — Communication assets

### K1. A written case study *(1 day)*
A 1,500-word article on the method, aimed at auditors rather than engineers. Publish on
LinkedIn or a personal site. Explaining a technical method to a non-technical audience is
the exact skill both target roles hire for.

### K2. A 5-minute recorded walkthrough *(half day)*
Screen recording of the dashboards with narration. Link it in the README and on LinkedIn.
Many recruiters will watch a video who would not clone a repo.

### K3. A conference-style deck *(1 day)*
10 slides: problem, data, method, the complementarity finding, the economics, limitations.
Doubles as interview presentation material if asked to "walk us through a project".

---

## Suggested Phase 2 sequencing (if you want one path rather than a menu)

| Week | Focus | Deliverable |
|---|---|---|
| 1 | E1 + E2 + D1 | Tests, CI, stability intervals — makes everything else trustworthy |
| 2 | C1 + C2 + D3 | SHAP explanations, finding narratives, cost-based thresholds |
| 3 | A1 | Synthetic GL layer with journal-entry tests |
| 4 | A4 + D4 | Adversarial anomalies and temporal validation |
| 5 | H1 + H3 + F2 | Materiality, MUS, controls mapping, Excel exception pack |
| 6 | E6 + I2 | dbt/DuckDB rebuild, BI performance tuning |
| 7 | K1 + K2 + K3 | Case study, video, deck |

After week 3 the project is materially stronger than almost anything else in an entry-
level audit-analytics portfolio. After week 5 it is a genuine talking point with a senior
manager.

---

## What to deliberately NOT do

Recorded here so the temptation is dealt with once:

- **A large language model somewhere in the pipeline** because it is fashionable. There
  is no step here an LLM improves, and a reviewer will read it as decoration. (The one
  defensible use is drafting finding narratives — and even then a deterministic template
  is more auditable, which is why C2 is rules-based.)
- **Deep learning for the anomaly detection itself.** At this scale and feature count, a
  tree ensemble wins on accuracy, runtime and explainability. Add the autoencoder in B1
  only as a comparison, and expect it to lose.
- **Chasing a higher AP by tuning against the labels.** That is fitting to the test set.
  Every number in this project is credible precisely because it was not tuned.
- **More anomaly archetypes for their own sake.** Six well-designed ones beat fifteen
  sloppy ones. Add the seventh (adversarial) only because it answers a real objection.
- **Rewriting the whole thing in a new framework.** Track E improvements are incremental
  by design for a reason.

---

**END OF ROADMAP**
