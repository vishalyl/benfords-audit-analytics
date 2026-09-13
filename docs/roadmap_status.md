# Roadmap status and a practical next-step plan

`plan/05_FUTURE_ROADMAP.md` is the original Phase 2 planning document, an 11-track menu
written before Phase 1 existed. It stays untouched as the historical record. This file is
the practical version: where things actually stand today, and a short, realistic list of
what to build next if the goal is landing interviews soon rather than building the largest
possible portfolio project.

## Entry criteria, checked against the original roadmap

| Criterion | Status |
|---|---|
| `git tag v1.0` exists and is pushed | Not tagged as `v1.0` specifically, but every stage is tagged (`stage-00-02-bootstrap` through `stage-13-final`) and pushed |
| Public dashboard URL live | Yes: `https://vishalyl.github.io/benfords-audit-analytics/`, confirmed live |
| README read end to end by another person | Not yet, this is on you |
| 3-minute pitch deliverable without notes | The script exists in `docs/resume_and_interview.md`, rehearsal is on you |

Two of four are done. The other two are human tasks, not build tasks, so there is nothing
further to automate there.

## What's actually implemented from Phase 2 right now

Nothing, and that's correct. The original roadmap explicitly says not to start Phase 2
until Phase 1 is done and live, which only just happened. Every track A through K below is
still a proposal, not a claim.

## A practical fast track, not the full menu

The original roadmap sequences seven weeks of work across eleven tracks. If the actual goal
is applying for data-analyst and audit-analytics roles soon, most of that is more than you
need. Five items, roughly a week of focused work, cover the highest ratio of interview
credibility to effort:

### 1. GitHub Actions CI badge (half a day)
A green build badge in the README is disproportionately persuasive to anyone who actually
opens the repo, and it costs almost nothing: lint plus a smoke run of the gate scripts on
push. This is roadmap track E2.

### 2. Formal inter-method agreement statistics (half a day)
The site's hero finding, rules beating Isolation Forest on every injected type at a matched
budget, is currently reported from the raw matrix. Adding Cohen's kappa between each pair
of methods and a proper set-overlap breakdown turns that into a formally supported claim
instead of an eyeballed one. Roadmap track D5.

### 3. A one-page model card (half a day)
Intended use, out-of-scope uses, training data, evaluation data, metrics with confidence
intervals, known limitations, and the false-accusation risk of any flagged transaction.
Rare in portfolio projects and increasingly the first thing a technically serious
interviewer asks about. Roadmap track C4.

### 4. Stratified population view and a controls-mapping table (one day combined)
Standard audit stratification by value band (for example, "the top 2% of items by value
represent some concrete percent of revenue"), plus a short table mapping each detection
test to the control it addresses and the audit assertion it tests (occurrence, cut-off,
accuracy, completeness). Both are cheap and speak directly to an audit-analytics
interviewer's frame of reference. Roadmap tracks H2 and H3.

### 5. A five-minute recorded walkthrough (half a day)
The single highest-leverage item on this list. Many recruiters will watch a short video who
will not clone a repository. Screen-record the live dashboard and the simulator, narrate the
honest finding from Stage 7, link it in the README and wherever the project gets shared.
Roadmap track K2.

## What to deliberately skip for now

Everything else in the original roadmap: the synthetic general-ledger layer, the model
bake-off, SHAP explainability, the full engineering-rigor track, streaming and alert
triage. Each is a legitimate multi-day investment with a real payoff, but none of them
change whether this project is ready to show someone this week. Pick them up later if a
specific interview asks for exactly that depth, not before.

## A note on process

This file itself follows the same rule as everything else in the pipeline: every number in
it is either a status already verified in this repository's own gate reports, or an
explicit recommendation labeled as such. Nothing here is claimed as done unless it is done.
