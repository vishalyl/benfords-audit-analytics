# PHASE 2A: Explainability, Economics, Ceiling Benchmark, Statistical Rigor

**Document ID:** `06_PHASE_2A_EXPLAINABILITY_ECONOMICS_RIGOR`
**Status:** Planning only. Nothing in this document has been built. The user builds it;
this document exists so building it is mechanical, not exploratory.
**Prerequisite:** Phase 1 (Stages 0-13) complete and live. True as of this writing:
`https://vishalyl.github.io/benfords-audit-analytics/`, all 14 gates PASS/SKIPPED per
plan, Stage 6 scored on the full 1,030,804-row population (see `DECISIONS.md` D-0007).
**Selects 4 of the 5 items proposed in conversation**, chosen for resume/interview
impact per hour of build time:

| # | Track | Resume payoff |
|---|---|---|
| 1 | SHAP explainability | "Every flagged transaction carries an auditable rationale, not just a score." |
| 2 | Cost-based economic threshold | "Identified the economically optimal review budget, not the F1-optimal one." |
| 3 | Supervised ceiling benchmark | "Quantified how much signal exists at all, and how close the unsupervised model gets." |
| 4 | Stability + Cohen's kappa | "AP = 0.166 ± 0.01 across 20 independent trials," not a single lucky run. |

(The 5th item discussed, pytest + CI, is intentionally out of this document. It's pure
engineering hygiene with no analytical content, wire it up separately whenever, it
doesn't need a design doc.)

Each track below is independently buildable and independently shippable. Build them in
any order; Track 3 (ceiling benchmark) has the strictest safety requirement (read it
even if building last).

---

## 0. Ground rules carried over from Phase 1

These are not optional just because this is "Phase 2":

- **The Leakage Firewall still applies to the production pipeline.** Track 3 is the one
  deliberate exception, it trains directly on labels, and it must be walled off so
  nothing it produces can ever reach `composite_risk`. See sec 3.4.
- **Every number reported must be computed, not estimated by the agent or the user.**
  Same rule as Phase 1's `checks/gate_NN.py` convention: each track gets a script that
  produces a metrics JSON, and a gate script that asserts it's sane.
- **No em dashes in any user-facing copy** (docs, dashboard text, resume bullets). Sweep
  before calling anything done. See `DECISIONS.md` and the redesign work already done
  for the established convention (comma, colon, or period instead).
- **No hand-typed numbers in the README, dashboard, or resume doc.** Every new figure
  flows through the same `src/report_fill.py` placeholder mechanism or an equivalent
  read-from-JSON pattern already used everywhere else in this repo.
- **First person on the live site.** Any new site copy follows the voice already
  established in `src/static_dashboard.py` ("I built", "I found"), not third person.
- **New gate numbering:** Phase 1 used `checks/gate_00.py` .. `gate_13.py`. Phase 2A
  tracks get `checks/gate_14.py` (SHAP), `gate_15.py` (economics), `gate_16.py`
  (ceiling), `gate_17.py` (stability). Same contract as Phase 1: exits non-zero on
  failure, writes `reports/gate_reports/gate_1N.md`.

---

## 1. Track 1: SHAP Explainability

**Goal:** every one of the top-25 (and ideally top-5,000) reviewed transactions carries
a specific, inspectable reason: which features pushed its score up, by how much.
**Effort estimate:** 1.5-2 days (SHAP/IsolationForest compatibility is the real risk
here, budget time for it, see 1.2).
**New dependency:** `shap>=0.45` (add to `requirements.txt`; do **not** add to
`app/requirements.txt`, the Streamlit app should read precomputed SHAP values from
`data/dashboard/`, never import `shap` itself, to keep the app's dependency footprint
light per the existing convention).

### 1.1 What SHAP explains here

Isolation Forest's `if_score` is the dominant term in the composite (weight 0.50), so
that's what gets explained. SHAP won't explain `rules_component` or
`benford_component`, those are already fully transparent (a rule either fired or it
didn't, `rule_flag_names` already says which; the Benford flag is just "segment
conformity, yes/no"). Explaining the opaque one is the point.

### 1.2 The compatibility risk (read this before starting)

`shap.TreeExplainer` has had version-sensitive support for scikit-learn's
`IsolationForest` (it isn't a standard supervised tree ensemble, so SHAP has to treat
its path-length scoring specially). Before writing any pipeline code:

```python
import shap, sklearn
print(shap.__version__, sklearn.__version__)
explainer = shap.TreeExplainer(if_model)  # if_model = the fitted IsolationForest
sv = explainer.shap_values(X_sample[:5])
print(sv.shape)  # sanity check against X_sample[:5].shape
```

Run this in isolation first, on 5 rows, before building anything else. If
`TreeExplainer` errors or produces nonsense (e.g. all-zero contributions), fall back to
`shap.Explainer(if_model.decision_function, X_background)` (the model-agnostic path,
slower but always works) or `shap.KernelExplainer`. Either fallback is fine, slower
computation on a background sample of ~200 rows is still fast enough for 25-100
transactions. Log whichever path was used in the output JSON's metadata so it's honest
about which method actually ran.

### 1.3 New module: `src/explain.py`

```python
def load_if_model_and_features() -> tuple[IsolationForest, pd.DataFrame, list[str]]:
    """Re-fits the IF model exactly as src/models.py does (same seed, same feature
    columns, same training subsample) so the explainer sees the same model that
    actually produced if_score. Do not try to serialize/reload the Stage 6 model
    object across runs, refitting deterministically is simpler and just as fast
    (Stage 6 full-population IF fit takes ~13s per the Stage 6 gate report)."""

def compute_shap_values(
    model: IsolationForest, X: pd.DataFrame, background_n: int = 200, seed: int = 42,
) -> tuple[np.ndarray, str]:
    """Returns (shap_values array shaped [n_rows, n_features], method_used).
    Tries TreeExplainer first, falls back per sec 1.2. method_used in
    {'tree_explainer', 'permutation_explainer', 'kernel_explainer'}."""

def global_importance(shap_values: np.ndarray, feature_names: list[str]) -> pd.DataFrame:
    """Mean |SHAP| per feature, sorted descending. Feeds the global bar chart."""

def per_row_explanation(
    shap_values: np.ndarray, X_row: pd.Series, feature_names: list[str], base_value: float,
) -> list[dict]:
    """One row's waterfall as a list of {feature, value, shap_contribution}, sorted by
    |shap_contribution| descending. This is what gets serialized per transaction."""

def run(top_n: int = 100) -> None:
    """Stage entry point. Explains the top_n transactions by composite_risk (not all
    1M+, that's expensive and pointless, nobody reviews rank 400,000). Writes:
      - reports/metrics/shap_summary.json (method_used, global_importance, n_explained)
      - data/dashboard/shap_explanations.json (list of {txn_id, base_value, contributions:[...]})
      - reports/figures/shap_global_importance.png (bar chart)
      - reports/figures/shap_beeswarm.png (if the fallback path supports it; TreeExplainer
        definitely does, KernelExplainer may not, handle gracefully)
    """
```

### 1.4 Output size discipline

`data/dashboard/shap_explanations.json` must stay small (same 25MB cap on
`data/dashboard/` as everything else). For `top_n=100` transactions x ~9 features x a
{feature, value, contribution} triple, this is a few hundred KB, comfortably fine. If
`top_n` is ever raised toward 5,000 to cover the full explorer table, re-check the size
and consider trimming to the top-3 contributing features per row instead of all 9.

### 1.5 Dashboard integration

**Static site (`docs/index.html` via `src/static_dashboard.py`):** in the existing "Top
10, for audit review" table, make each row expandable (a small disclosure triangle,
plain CSS/JS, no new dependency) revealing a horizontal bar per feature: green bars
push the score up, a muted color pushes it down, matching the existing dark palette.
This is inline SVG or a tiny CSS-bar approach, keep the zero-external-dependency rule
that already survived one CDN-blocking incident (see `DECISIONS.md` and the Stage 10
gate report).

**Streamlit app (`app/streamlit_app.py`):** in the "Anomaly Explorer" tab, add a
`st.selectbox` or row-click to pick a transaction from `top_risk_5000`, then render its
waterfall with `shap.plots.waterfall` if a matplotlib figure is acceptable, or a
Plotly horizontal bar built from `data/dashboard/shap_explanations.json` for
consistency with the app's existing Plotly-only chart convention (prefer the Plotly
version, don't introduce a second charting library into the app for one feature).

### 1.6 Gate 14 (`checks/gate_14.py`)

1. `reports/metrics/shap_summary.json` and `data/dashboard/shap_explanations.json` exist and parse.
2. `method_used` is one of the three known values, and is logged in the gate report (so a reader knows whether the "real" TreeExplainer path or a fallback ran).
3. Every explained transaction's per-feature contributions sum to approximately `if_score - base_value` (SHAP's additivity property), within a small numerical tolerance, this is the one mathematical sanity check that catches a badly wired explainer.
4. `global_importance` ranks `amount` or a customer-aggregate feature highly (a basic sanity check, if the top feature by mean |SHAP| is something implausible like `day_of_week`, investigate before shipping).
5. `data/dashboard/` total size still under 25MB.
6. No em dashes in any new file.

**Resume bullet once built:** *"Added SHAP-based explanations (TreeExplainer over
IsolationForest, with an additivity-property sanity check) so every one of the top 100
flagged transactions carries a specific, verifiable rationale rather than an opaque
score."*

---

## 2. Track 2: Cost-Based Economic Threshold Optimization

**Goal:** stop picking a threshold by F1 (a statistical convenience metric nobody
outside ML actually cares about) and instead find the review budget that maximizes
estimated net dollar benefit, the framing an actual audit manager or CFO thinks in.
**Effort estimate:** 1 day. No new dependencies, this is arithmetic over data you
already have.
**Honesty requirement:** every dollar figure here rests on assumptions (minutes per
review, recovered value per true positive). State them as assumptions, in the output
JSON and on the dashboard, not as measured facts. This is the same discipline already
applied to the composite weights (a-priori judgement, disclosed as such, not dressed up
as derived).

### 2.1 The cost model

```yaml
# config.yaml addition
economics:
  reviewer_minutes_per_item: 15        # assumption: time to review one flagged transaction
  reviewer_hourly_cost_gbp: 35         # assumption: fully-loaded cost of a reviewer's time
  recovery_rate: 0.6                   # assumption: fraction of a caught anomaly's value
                                        # actually recoverable/preventable once flagged
```

```
cost(k)    = k * (reviewer_minutes_per_item / 60) * reviewer_hourly_cost_gbp
benefit(k) = sum(amount for each true positive in top k) * recovery_rate
net(k)     = benefit(k) - cost(k)
```

`amount` for a true positive is already in `dashboard_export.parquet` (the ground-truth
join is legitimate here for the exact same reason it's legitimate in `top_risk_transactions.csv`,
this is an evaluation/economic-analysis artefact, never a model input; see
`plan/00_MASTER_PLAN.md` sec 8.3's reasoning, which already covers this case). Use
`|amount|` since some injected archetypes (e.g. extreme_outlier) can be large-magnitude
in either direction.

### 2.2 New module: `src/economics.py`

```python
def net_benefit_curve(
    ranked_labels: np.ndarray, ranked_amounts: np.ndarray, cfg_economics: dict,
) -> pd.DataFrame:
    """ranked_labels, ranked_amounts: same rank order as rank_labels.json (sorted by
    composite_risk descending). Returns a DataFrame with columns
    k, cost, benefit, net_benefit for k = 1..len(ranked_labels), or a sensible
    downsampled grid (every 10th k below 1000, every 100th above) to keep the
    output small, this does not need every single k plotted.
    """

def find_optimal_k(curve: pd.DataFrame) -> dict:
    """Returns {'optimal_k': int, 'net_benefit_at_optimal': float,
    'net_benefit_at_f1_optimal': float, 'f1_optimal_k': int} -- the last two fields
    are what make the finding interesting: how much better (or worse) is the
    economically optimal point than the F1-optimal one already computed in
    Stage 7's threshold_sweep()?"""

def run() -> None:
    """Writes reports/metrics/economic_optimum.json and
    reports/figures/net_benefit_curve.png (net benefit vs k, with both the economic
    optimum and the F1 optimum marked)."""
```

### 2.3 Why this needs `amount`, and where to get it cheaply

`data/dashboard/rank_labels.json` (built in Stage 8) is deliberately just a 0/1 array,
no other columns, to keep it tiny. For this track, add a sibling file
`data/dashboard/rank_amounts.json` (same rank order, one float per row, `|amount|`) in
`src/export.py` right next to where `rank_labels.json` is written. At ~9 significant
figures per float this is still well under a few MB for 1,030,804 rows (roughly the
same order of magnitude as `rank_labels.json` itself), stays inside the 25MB cap
comfortably.

### 2.4 Live simulator integration (the "more interactivity, nothing persistent" choice)

Extend the existing simulator in `docs/index.html` (built in `src/static_dashboard.py`)
with a 5th result tile: "Estimated net benefit," computed client-side in the same
`updateSim(k)` function using a new `RANK_AMOUNTS` array loaded alongside
`RANK_LABELS`, plus the three cost-model constants baked in as JS variables (read from
`economic_optimum.json` at page-generation time, not hardcoded). Add a one-line caption
under the tile stating the assumptions plainly: *"Assumes 15 minutes per review at
£35/hour, and that 60% of a caught anomaly's value is recoverable once flagged. Adjust
these in `config.yaml` and rebuild."* This keeps the honesty discipline visible right
where the number appears, not buried in a footnote.

### 2.5 Gate 15 (`checks/gate_15.py`)

1. `reports/metrics/economic_optimum.json` exists, `net_benefit_at_optimal >= net_benefit_at_f1_optimal` (the economic optimum should never be worse than the F1 one, if it is, the search has a bug, not a real finding).
2. `data/dashboard/rank_amounts.json` has the same length as `rank_labels.json` and both are in the same rank order (cross-check the injected-row count and total value against `kpi_summary.json`'s known totals).
3. The economics assumptions in `config.yaml` are present and are plain numbers (not accidentally left as a formula string or similar).
4. The dashboard caption stating assumptions is present verbatim in `docs/index.html` (grep for "Assumes").
5. No em dashes.

**Resume bullet once built:** *"Built a cost-based framework translating detection
thresholds into estimated reviewer-hours versus value-at-risk, identifying the
economically optimal review budget rather than the F1-optimal one, made interactively
explorable in the live dashboard."*

---

## 3. Track 3: Supervised Ceiling Benchmark

**Goal:** answer "why didn't you just train a classifier" before anyone asks it, by
training one anyway, purely as a diagnostic ceiling, and being explicit that it is
never deployed.
**Effort estimate:** 1 day.
**New dependency:** `lightgbm>=4.0` (prefer over `xgboost` on Windows: no separate
build toolchain requirement, pip-installs cleanly). Add to `requirements.txt` only, not
`app/requirements.txt`, the Streamlit app never needs to import this.

### 3.1 Framing, and why this is not a Leakage Firewall violation

The Leakage Firewall (`plan/00_MASTER_PLAN.md` sec 6) exists to stop
`is_synthetic_anomaly`/`anomaly_type` from reaching anything that scores a transaction
for real. This track deliberately trains on those labels, but the model it produces
**must never be called anywhere in the detection path** (`src/models.py`,
`src/composite.py`, `src/validate.py`, `src/export.py`). It exists to answer one
question, "given perfect knowledge of the labels, how separable are these features at
all," which upper-bounds what any unsupervised method (including the one actually
deployed) could achieve. Every real audit engagement lacks these labels, this is
explicitly diagnostic, not a deployable candidate, and every doc/UI surface that shows
this number must say so in the same sentence it's reported.

### 3.2 New module: `src/ceiling_benchmark.py`

```python
def build_ceiling_features(labeled_df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Same feature set as src/models.py's FEATURE_COLS (amount, quantity, price, hour,
    day_of_week, cust_txn_count, cust_amount_mean, cust_amount_std) plus
    rule_flag_count, i.e. exactly FS-B from the master plan's original spec. Returns
    (X, y) where y = is_synthetic_anomaly. This function is the ONLY place in the
    codebase allowed to return y alongside X; it lives in this module specifically so
    that fact is impossible to miss in a code review."""

def cross_validated_ceiling(
    X: pd.DataFrame, y: np.ndarray, n_splits: int = 5, seed: int = 42,
) -> dict:
    """StratifiedKFold (the anomaly rate is ~1.6%, a plain KFold risks a fold with too
    few positives). Trains lightgbm.LGBMClassifier per fold, scores held-out AP and
    ROC-AUC, returns per-fold and mean+-std results. Also returns global feature
    importance (gain-based) averaged across folds."""

def run() -> None:
    """Writes reports/metrics/ceiling_benchmark.json:
      {'cv_average_precision': {'mean':..., 'std':..., 'per_fold': [...]},
       'cv_roc_auc': {...},
       'feature_importance': {...},
       'composite_ap': <read from model_metrics.json, for the comparison>,
       'pct_of_ceiling_captured': composite_ap / cv_average_precision.mean}
    Also writes reports/figures/ceiling_vs_composite.png (a simple two-bar comparison:
    the deployed composite's AP next to the supervised ceiling's AP)."""
```

### 3.3 Expected result, and what to do if it's surprising

The ceiling should score meaningfully higher than the composite (it has the answer
key). If `pct_of_ceiling_captured` comes out above ~90%, that's a mildly suspicious
result worth double-checking the feature set doesn't leak something (e.g. accidentally
including a feature that's a near-perfect proxy for the injection archetype), not a
reason to celebrate. If it's very low (under ~20%), that's a genuinely interesting,
reportable finding about how hard this detection problem is on these features alone,
report it as such rather than tuning until it looks better, same discipline as
`DECISIONS.md` D-0004.

### 3.4 The safety guardrail this track needs, specifically

Add one line to `checks/common.py` or a new lightweight check:

```python
# In gate_16.py itself, and ideally as a standing repo-wide guard:
import ast
for path in ["src/models.py", "src/composite.py", "src/validate.py", "src/export.py"]:
    tree = ast.parse(Path(path).read_text())
    source = Path(path).read_text()
    assert "ceiling_benchmark" not in source, f"{path} must never import src.ceiling_benchmark"
```

This is cheap insurance against the most embarrassing possible mistake this track could
introduce: accidentally wiring the labeled-trained model into anything that touches a
real (future, unlabelled) transaction.

### 3.5 Gate 16 (`checks/gate_16.py`)

1. `reports/metrics/ceiling_benchmark.json` exists, all 5 folds present, `cv_average_precision.mean` is a plausible value in (0, 1).
2. The import guard in sec 3.4 passes for all four production modules.
3. `pct_of_ceiling_captured` is computed and present (whatever the value is, honestly reported per sec 3.3).
4. Every place this number is quoted (docs, dashboard, resume) includes the word "diagnostic" or "ceiling" within the same sentence, never presented as a deployable result. Grep-check this.
5. No em dashes.

**Resume bullet once built:** *"Benchmarked against a supervised ceiling (5-fold
cross-validated LightGBM on ground truth, used purely as an offline diagnostic) to
quantify what fraction of the available signal the deployed unsupervised pipeline
actually captures."*

---

## 4. Track 4: Stability Across Seeds + Cohen's Kappa Complementarity

**Goal:** replace "AP = 0.166" (one run, one seed) with "AP = 0.166 +/- 0.0N across 20
independent injections" (a real distribution), and replace the eyeballed "rules beat IF
by 60 points on extreme_outlier" with a formal Cohen's kappa agreement matrix between
every pair of methods.
**Effort estimate:** 1-1.5 days, mostly compute time (see 4.2), not code complexity.
**New dependency:** none, `sklearn.metrics.cohen_kappa_score` is already available via
the existing scikit-learn pin.

### 4.1 What actually needs to vary across the 20 seeds

Not the whole pipeline end to end, that would re-run ingestion and cleaning 20 times
for no reason (those steps have nothing seed-sensitive in them once the source data is
fixed). What genuinely depends on the seed:

- `src/inject.py` (which rows get picked for injection, and the specific perturbation values)
- `src/models.py` (IsolationForest's `random_state`, and its 50%-subsample training mask)
- `src/validate.py`'s bootstrap CI (already seeded internally, disable it for this track, see 4.2)

So the stability loop re-runs **inject -> models -> a lightweight scoring pass**, not
`clean` or `benford` or `rules` (rules and Benford results don't depend on the
injection seed's specific row choices in a way that needs re-testing here; if you
disagree and want full end-to-end stability, that's a valid heavier version of this
track, just budget accordingly, roughly 20x a full pipeline run).

### 4.2 The compute-time problem, and the fix

A single full `validate.py` run took **3m50s** at full population (see
`reports/gate_reports/gate_07.md`), almost all of it the 200-resample bootstrap CI
computed 3 times (IF, LOF, composite). Twenty of those, unmodified, is over an hour.
Fix: add a `skip_bootstrap: bool` parameter to `src.validate.run()` (default `False`,
so the real Stage 7 gate is unaffected) that skips `bootstrap_ci()` entirely, since the
whole point of this track is to get the cross-seed distribution instead, a per-seed
bootstrap CI would be redundant work measuring the same thing two different ways.

### 4.3 New module: `src/stability.py`

```python
def run_one_seed(seed: int) -> dict:
    """Temporarily overrides cfg.project.seed for the duration of this call (use a
    context manager that mutates and restores src.config.cfg._data['project']['seed'],
    since every downstream module reads it directly rather than accepting a parameter,
    see src/config.py). Re-runs src.inject.run(force=True), src.models.run(force=True),
    then src.validate.run(skip_bootstrap=True). Returns the key metrics: composite AP,
    iforest AP, lof AP, the full method_binary decisions (needed for kappa in 4.4)."""

def stability_summary(results: list[dict]) -> dict:
    """Across the 20 seeds' results: mean, std, min, max, and a 95% interval (either
    parametric via the std, or just the 2.5th/97.5th percentile of the 20 values,
    which is simpler to justify with n=20) for composite AP, IF AP, and LOF AP."""

def run(n_seeds: int = 20, base_seed: int = 42) -> None:
    """Seeds used: base_seed, base_seed+1, ..., base_seed+19 (42..61), so the original
    seed 42 run is always one of the 20, not a special case excluded from the
    distribution. Writes reports/metrics/stability_summary.json and
    reports/figures/ap_stability_boxplot.png (one box per method, composite/IF/LOF)."""
```

**A real time cost, budget for it:** even with bootstrap skipped, 20x (inject + models +
validate) at full population is still substantial. `models.py` full-population took 27s
(Stage 6 gate report), `inject.py` and a bootstrap-free `validate.py` are comparably
fast. Expect on the order of 20-40 minutes total, not 20 seconds. Run it in the
background, don't block on it interactively.

### 4.4 Cohen's kappa complementarity matrix

```python
def kappa_matrix(method_binary: dict[str, np.ndarray]) -> pd.DataFrame:
    """method_binary: the same dict validate.py already builds internally
    ({'benford_any':..., 'rules_any':..., 'iforest':..., 'lof':..., 'composite':...}),
    each a 0/1 array over the full population. Returns a symmetric DataFrame of
    pairwise sklearn.metrics.cohen_kappa_score values, one run (seed 42 is fine here,
    this doesn't need to be re-run across all 20 seeds, it's a property of the
    detection methods' agreement, not something that should vary much with the
    injection seed). Low kappa between two methods is the formal version of
    "complementary detection", exactly the claim the site's "biggest finding" section
    already makes informally."""
```

Expose `method_binary` from `src/validate.py`'s `run()` (it's currently a local
variable) as a return value or writes it to a small
`reports/metrics/method_binary_flags.parquet` so `src/stability.py` doesn't need to
recompute it.

### 4.5 Gate 17 (`checks/gate_17.py`)

1. `reports/metrics/stability_summary.json` has exactly 20 per-seed entries (or explicitly documents fewer with a reason, e.g. a seed that failed).
2. The seed-42 entry's composite AP matches (within float tolerance) the value already in the committed `reports/metrics/model_metrics.json`, this is the cross-check that the stability harness is actually running the same computation, not a subtly different one.
3. `reports/metrics/kappa_matrix.csv` exists, is symmetric, diagonal is exactly 1.0.
4. The kappa matrix shows at least one pair with kappa below some threshold (e.g. 0.3) as the formal complementarity evidence, if every pair has high kappa, the "layered detection" claim doesn't hold and that must be reported honestly (same discipline as D-0004), not hidden.
5. No em dashes.

**Resume bullet once built:** *"Validated detection stability across 20 independently
seeded trials (composite AP 0.166 +/- 0.0N) and formalized cross-method
complementarity with a Cohen's kappa agreement matrix."*

---

## 5. Suggested build order

Not a hard requirement, but this order minimizes wasted work:

1. **Track 4 first** (stability + kappa). It touches `src/validate.py` (the
   `skip_bootstrap` param and exposing `method_binary`) in ways Track 1 and Track 2
   might also want to reuse (Track 1's per-row explanation could eventually be
   seed-checked too; Track 2's `method_binary`-adjacent economics could reuse the same
   exposed data). Building it first avoids touching `validate.py` twice.
2. **Track 2 next** (economics). Cheapest, no new dependency, and it extends the
   simulator you already have, immediate visible payoff.
3. **Track 1** (SHAP). Budget the most calendar time for this one because of the
   compatibility risk in sec 1.2, don't schedule it the day before you need to show
   someone the site.
4. **Track 3 last** (ceiling benchmark). Fully independent of the other three, safe to
   slot in whenever, just don't skip the guardrail in sec 3.4.

## 6. Cross-cutting checklist before calling any track "done"

- [ ] New dependency added to `requirements.txt` (and explicitly NOT to
      `app/requirements.txt` unless the Streamlit app genuinely needs to import it,
      per the existing "keep the app's dependencies light" rule from Stage 10).
- [ ] New `config.yaml` section added, with every assumption a named, commented value,
      never a magic number buried in Python.
- [ ] New `src/<name>.py` module has a `run()` entry point matching the existing
      convention (`setup_logging`, `timed`, writes to `reports/metrics/` and/or
      `data/dashboard/`).
- [ ] New `checks/gate_1N.py` follows the existing gate script contract (exits
      non-zero on failure, writes `reports/gate_reports/gate_1N.md`).
- [ ] `docs/methodology.md` gets a new section for the track (formula, assumptions,
      source).
- [ ] `docs/resume_and_interview.md` gets the new bullet, inserted into the relevant
      variant(s), with the actual computed number substituted for the placeholder in
      this document.
- [ ] `DECISIONS.md` gets an entry for any judgement call made while building (the
      SHAP fallback path actually used, the specific cost assumptions chosen, etc.),
      same append-only convention as every decision so far.
- [ ] Site/app copy is first person, no em dashes, numbers pulled from JSON not typed
      by hand.
- [ ] `git commit` per track, tagged `phase2a-track-N-<name>` following the existing
      `stage-NN-<name>` tagging convention.

---

**END OF PLAN. Nothing above has been built. See section 5 for a suggested order.**
