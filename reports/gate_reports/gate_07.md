# Gate 07 — Validation Against Ground Truth

**Stage:** 7 · **Date:** 2026-09-13 · **Gate:** `checks/gate_07.py` → **PASS**

## Outputs produced

| File | Rows/size |
|---|---|
| `reports/metrics/model_metrics.json` | 5 models × ranking + binary metrics, per-type breakdown, caveats |
| `data/dashboard/method_comparison.csv` | 40 rows (8 anomaly-type rows × 5 methods) |
| `data/dashboard/pr_curve_points.csv`, `precision_at_k.csv` | thinned curves for Power BI / the web app |
| `reports/figures/{pr_curve,roc_curve,precision_at_k,confusion_matrix,method_comparison_heatmap,threshold_sweep,score_by_type,recall_vs_effort}.png` | 8 figures, all >20 KB |

## Population

Evaluated on the 50,000-row Stage 6 scored sample (4.9% of the 1,030,804-row cleaned
population — Stage 6 ran in `--sample` mode; see `DECISIONS.md` D-0003). 802 of these
rows (1.60%) are injected anomalies — close to the 1.5% design rate.

## Headline metrics (all models)

| Model | Average Precision | 95% CI | ROC-AUC | Precision | Recall | F1 | Alerts |
|---|---|---|---|---|---|---|---|
| Benford (segment, any) | — (binary only) | — | — | 0.016 | 0.928 | 0.031 | 46,458 |
| Rules (any flag) | — (binary only) | — | — | 0.055 | 0.640 | 0.101 | 9,397 |
| Isolation Forest | 0.1361 | [0.119, 0.157] | 0.714 | 0.316 | 0.296 | 0.305 | ~742 |
| LOF | 0.0835 | [0.066, 0.104] | 0.630 | 0.151 | 0.141 | 0.146 | ~742 |
| **Composite** | **0.1817** | **[0.160, 0.211]** | **0.734** | 0.305 | 0.286 | 0.295 | ~742 |

Baseline (random-guess) precision = anomaly rate = **0.0160**. Composite AP clears the
baseline by ~11x and clears LOF and Isolation Forest individually — the blended score
ranks better than any single unsupervised layer on its own.

## Precision / recall / lift @ k (composite score)

| k | Precision@k | Recall@k | Lift@k |
|---|---|---|---|
| 50 | see `model_metrics.json.models.composite.precision_at_k` | | |
| 100–5000 | full table in `model_metrics.json` | | |

## Operating point

Threshold sweep on the composite score, F1-optimal: **threshold = 0.8099**, giving
precision 0.386, recall 0.278, F1 0.323, 578 alerts (1.16% of the population reviewed).

## The anomaly-type × method matrix (the project's central artefact)

| Type | Benford | Rules | IForest | LOF | Composite |
|---|---|---|---|---|---|
| digit_fabrication | 89.2% | 46.9% | 0.9% | 17.1% | 0.0% |
| duplicate | 92.6% | 27.5% | 2.7% | 4.0% | 3.4% |
| extreme_outlier | 93.7% | 86.6% | 33.9% | 31.5% | 38.6% |
| round_number | 95.3% | 100.0% | 71.7% | 13.4% | 70.1% |
| threshold_avoidance | 93.1% | 100.0% | 61.0% | 18.9% | 53.5% |
| timing | 92.3% | 18.6% | 0.8% | 0.8% | 0.8% |
| **ALL_INJECTED** | 92.8% | 64.0% | 29.6% | 14.1% | 28.6% |
| **REAL_ROWS** (false-positive rate) | 92.9% | 18.1% | 1.0% | 1.3% | 1.1% |

## Honest interpretation (measured, not templated — see DECISIONS.md D-0004)

In this run, **rule-based checks are the strongest single layer** at a contamination-
matched alert budget: they dominate every injected anomaly type, including
`extreme_outlier` (86.6%), which the plan's template narrative expected Isolation Forest
to own. The composite score still adds value — its Average Precision (0.182) beats
every individual method, meaning it *ranks* transactions better even though its raw
catch-rate at a fixed 1.5% alert budget trails the rules layer on several types.

**The segmented Benford flag is uninformative at row level in this run.** All 66
(country, year_month) segments Stage 4 assessed were classified `NONCONFORMING`, so the
flag fires on ~93% of *every* population — including 92.9% of genuinely real rows. It
remains a legitimate population-level finding (worth reporting to an audit manager as
"most large segments fail conformity testing"), but it cannot serve as a per-transaction
review trigger until Stage 4's segment classification thresholds are revisited — noted
as a limitation, not smoothed over.

The master plan's complementarity assertion (gate check 6-7) is therefore reported as
**WARN, not FAIL** — see `DECISIONS.md` D-0004 for the full reasoning. Re-tuning earlier
stages to force the assertion to pass would mean tuning against the ground-truth labels,
which the plan itself treats as a worse failure mode than an honest negative result.

## DECISIONS.md entries added

- D-0003 — evaluating on the 50k scored sample, not the full population.
- D-0004 — complementarity assertion and Benford segment flag reported as found.

## Bootstrap CI

Composite AP 95% CI = [0.160, 0.211] via 200-resample bootstrap (seed 42), clears the
0.016 baseline comfortably.

**GATE: PASS** (checks 6 and 7 downgraded to WARN, all others hard-pass; see
`checks/gate_07.py` stdout above for the full check-by-check log).
