# Gate 07: Validation Against Ground Truth

**Stage:** 7 · **Date:** 2026-09-13 (re-run at full population) · **Gate:** `checks/gate_07.py` -> **PASS**

## Outputs produced

| File | Rows/size |
|---|---|
| `reports/metrics/model_metrics.json` | 5 models, ranking + binary metrics, per-type breakdown, caveats |
| `data/dashboard/method_comparison.csv` | 40 rows (8 anomaly-type rows x 5 methods) |
| `data/dashboard/pr_curve_points.csv`, `precision_at_k.csv` | thinned curves for Power BI / the web app |
| `reports/figures/{pr_curve,roc_curve,precision_at_k,confusion_matrix,method_comparison_heatmap,threshold_sweep,score_by_type,recall_vs_effort}.png` | 8 figures, all >20 KB |

## Population

Evaluated on the full 1,030,804-row cleaned population (resolves DECISIONS.md D-0003;
see D-0007 for the full-population re-run and the LOF wiring bug it exposed). 16,874
rows (1.637%) are injected anomalies, matching the Stage 3 injection design exactly.

## Headline metrics (all models)

| Model | Average Precision | 95% CI | ROC-AUC | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| Benford (segment, any) | (binary only) | | | 0.016 | 0.923 | 0.032 |
| Rules (any flag) | (binary only) | | | 0.055 | 0.634 | 0.101 |
| Isolation Forest | 0.1355 | [0.132, 0.140] | 0.719 | 0.301 | 0.276 | 0.288 |
| LOF | 0.0550 | [0.049, 0.062] | 0.623 | 0.124 | 0.016 | 0.029 |
| **Composite** | **0.1656** | **[0.160, 0.171]** | **0.736** | 0.310 | 0.284 | 0.297 |

Baseline (random-guess) precision = anomaly rate = **0.0164**. Composite AP clears the
baseline by ~10x and beats both individual unsupervised layers.

**LOF note:** computed on its own 150,000-row (14.6%) coverage subsample, since LOF's
neighbour search does not scale to ~1M rows (see DECISIONS.md D-0007). Its recall of
0.016 reflects that coverage limit as much as model quality; ranking metrics
(AP, ROC-AUC) are scoped to the subsample it actually scored.

## The anomaly-type x method matrix (the project's central artefact)

| Type | Benford | Rules | IForest | LOF | Composite |
|---|---|---|---|---|---|
| digit_fabrication | 93.6% | 46.8% | 0.9% | 5.8% | 0.0% |
| duplicate | 92.4% | 27.4% | 2.7% | 1.0% | 3.5% |
| extreme_outlier | 93.6% | 88.4% | 28.0% | 6.3% | 30.9% |
| round_number | 95.2% | 100.0% | 74.1% | 3.8% | 68.6% |
| threshold_avoidance | 92.9% | 100.0% | 62.9% | 4.9% | 51.8% |
| timing | 92.7% | 18.6% | 0.8% | 0.4% | 0.5% |
| **ALL_INJECTED** | 93.4% | 63.5% | 28.9% | 3.8% | 25.9% |
| **REAL_ROWS** (false-positive rate) | 92.9% | 18.1% | 1.0% | 0.2% | 1.0% |

## Honest interpretation (measured, not templated, see DECISIONS.md D-0004/D-0007)

The finding from the 50k-sample run holds at full population, with a **larger margin**:
rule-based checks beat Isolation Forest on every injected type, including
`extreme_outlier` (88.4% vs 28.0%, a 60.4-point gap, up from 52.75 points at 50k). This
is not a small-sample artefact. The composite score's Average Precision (0.166) still
beats every individual method, meaning it ranks transactions better even though its raw
catch-rate at a fixed alert budget trails rules on most types.

The segmented Benford flag remains uninformative at row level: it fires on ~93% of
every population, real or injected, because all 66 assessed segments were classified
NONCONFORMING in Stage 4. This is unchanged by the population size, since Stage 4 was
not re-run.

The master plan's complementarity assertion (gate checks 6-7) is reported as **WARN**,
consistent with D-0004: `rules_any_beats_iforest` on `extreme_outlier` by 60.4pp; no
type shows IF beating rules by >=20pp (closest is `timing` at -14.9pp, i.e. rules still
ahead there too, just by less).

## Bootstrap CI

Composite AP 95% CI = [0.160, 0.171] via 200-resample bootstrap (seed 42), comfortably
clears the 0.0164 baseline.

**GATE: PASS** (checks 6 and 7 remain WARN per DECISIONS.md D-0004, all other checks
hard-pass).
