# Resume Bullets & Interview Prep

Every number below is copied from `reports/metrics/*.json` and `data/dashboard/kpi_summary.json`
as of the 2026-09-13 run, cross-checked in `checks/gate_13.py`. No figure is invented.

---

## A. Resume bullets

### Audit / forensic analytics variant

- Built an end-to-end audit analytics pipeline (Python, SQL) applying Benford's Law,
  10 rule-based exception tests and unsupervised ML (Isolation Forest) to a
  1,013,930-line UK online-retail sales ledger, validating detection precision and
  recall against a 16,874-row labelled synthetic anomaly set (1.64% injection rate).
- Designed segment-level Benford conformity testing by country and calendar month
  that flagged 66 of 66 assessed segments as nonconforming, a finding the aggregate
  test alone also surfaced (MAD 0.0251), demonstrating why population-level testing
  alone cannot pinpoint which segments to extend procedures on.
- Produced a 6-page audit workpaper (reportlab, regenerates from computed metrics) and
  a composite risk-ranked review queue with per-transaction suggested procedures,
  achieving 50.8% precision in the top 500 reviewed items against a 1.64% random-
  selection baseline (a 31x lift), and 45.2% precision across the top 5,000.

### Data analyst / BI variant

- Designed a SQLite data model and 6 showcase SQL queries (population reconciliation,
  customer concentration, duplicate-candidate detection, cut-off/period-end analysis,
  Benford extraction) over a 1,013,930-row transaction ledger, each mapped to a stated
  audit purpose.
- Built a 5-tab interactive Streamlit dashboard (Plotly) and a dependency-free static
  summary page, both reading from a committed 1.37MB aggregate data layer capped for
  fast load and safe public hosting, with a live review-budget slider showing recall
  and precision at any review size.
- Prepared a full Power BI star-schema data model and paste-ready DAX measure set
  (dynamic Benford MAD/verdict, drill-through detail page, What-if review-budget
  parameter) ready for a five-page dashboard build.

### Data scientist variant

- Engineered a leakage-safe feature set (transaction, temporal and per-customer
  aggregate features) for Isolation Forest and LOF anomaly scoring, with an explicit
  leakage-firewall assertion preventing ground-truth columns from entering the feature
  matrix, verified by a decision-tree AUC guard on the injected-row identifiers.
- Computed Average Precision with 95% bootstrap confidence intervals (200 resamples)
  for every detection method, composite score AP 0.1656 [0.160, 0.171] vs. a 0.0164
  random baseline, beating both Isolation Forest (0.136) and LOF (0.055) individually
  (LOF evaluated on its own 150,000-row coverage subsample, disclosed as such).
- Ran a 5-variant weight-sensitivity analysis on a judgement-set composite score
  (0.50 IF / 0.30 rules / 0.20 Benford) rather than tuning weights against the labels,
  disclosing that two alternative weightings scored marginally higher AP (0.177, 0.174
  vs. 0.166) instead of silently switching to the best-scoring variant.

---

## B. The pitch

### 60-second version

"I built a fraud-analytics pipeline on a real 1-million-row UK retail sales ledger.
Because live audit data has no ground truth, I injected a controlled 1.6% set of
synthetic anomalies across six fraud archetypes, duplicates, structuring, round
numbers, digit fabrication, cut-off timing, and extreme outliers, so I could actually
measure detection accuracy. I ran three independent layers, segmented Benford's Law,
ten rule-based exception tests, and an Isolation Forest, and combined them into a
composite risk score. The headline number: the top 500 of 1,030,804 scored
transactions are 50.8% real planted anomalies, a 31x lift over random selection, and
the top 5,000 alone surface 13.4% of every known anomaly in the ledger. It's live at
[repo link]."

### 3-minute version

Add to the above: "The interesting part is the injection design. Each archetype
targets a different detection layer on purpose, duplicates and round numbers should
be easy for rules, digit fabrication should only show up in segmented Benford, extreme
outliers should be an Isolation Forest's specialty. When I actually measured it, the
result wasn't the tidy story I expected: rule-based checks ended up catching every
single injected type at a higher rate than Isolation Forest, at a matched alert budget.
I reported that honestly instead of tuning the injection or the models until the result
matched my hypothesis, that's the difference between validating a detection system and
fitting one to a story. The segmented Benford test also over-triggered in this run, 
every segment large enough to test came back nonconforming, which is itself a real
finding: it means the population-level exception is real, but the current thresholds
aren't sharp enough to say which individual transactions to pull. I documented that as
a limitation and a concrete next step rather than hiding it."

---

## C. Interview Q&A

### Method

**1. What is Benford's Law and why would it apply to a sales ledger?**
The leading digit of many naturally occurring numeric datasets follows log10(1+1/d), 
about 30.1% start with 1, only 4.6% with 9, because the values span multiple orders of
magnitude without a hard floor or ceiling. A sales ledger's transaction amounts
generally satisfy that condition, which is why forensic accountants use digit
distribution as a screening test: fabricated or manually adjusted figures tend to
deviate from the natural curve. In my aggregate test, MAD came out to 0.0251, beyond
Nigrini's Nonconformity threshold of 0.015.

**2. When does Benford's Law not apply?**
When numbers are assigned rather than generated (invoice numbers, IDs), bounded within
a narrow range (percentages, ages), subject to a fixed minimum or maximum, or the
population is too small to be statistically meaningful, I enforced a 1,000-row minimum
per segment for exactly this reason, returning `INSUFFICIENT_DATA` below it rather than
a false verdict.

**3. Why MAD rather than chi-square here?**
Chi-square's test statistic scales with n, so at my aggregate population of 990,028
rows it rejected conformity (p < 0.001) for deviations that are economically trivial, 
the well-known "excess power" problem. Mean Absolute Deviation is sample-size
independent, so I used it as the primary criterion and reported chi-square alongside
with that caveat rather than dropping it.

**4. What are Nigrini's thresholds and where do they come from?**
From Mark Nigrini's *Benford's Law: Applications for Forensic Accounting, Auditing, and
Fraud Detection* (Wiley, 2012): MAD < 0.006 is Close conformity, < 0.012 Acceptable,
< 0.015 Marginal, and ≥ 0.015 Nonconformity. I encoded these directly in `config.yaml`.

**5. Why segment the test? What did segmenting actually surface that aggregate testing missed?**
Aggregate testing tells you the population as a whole looks off; it can't tell you
where. Segmenting by (country, calendar month) is meant to localize the finding to
specific business units and periods for targeted follow-up. In this run, honestly, both
levels came back nonconforming, 66 of 66 assessed segments, so segmentation didn't
surface a *contrast* the way the textbook case does, but it did confirm the finding is
not isolated to one country or month, which is itself useful information for scoping a
review.

**6. What does the second-digit test add?**
The second digit's expected distribution is flatter (9.7%–11.97% depending on digit)
than the first digit's, so it's a complementary, slightly less powerful check that can
catch fabrication schemes designed to only respect the leading digit. I computed it in
Stage 4 (`amount_second`, MAD 0.0768 on the aggregate) alongside the primary
leading-digit test.

### ML

**7. How does Isolation Forest work, in one minute, without equations?**
It builds an ensemble of random decision trees that isolate each point by repeatedly
splitting on random features at random thresholds. Anomalies, points that are
different from the bulk of the data, tend to get isolated in fewer splits than normal
points, because there's less "typical" data around them to require narrowing down. The
average number of splits needed becomes the anomaly score; I normalized it to [0,1] so
higher always means more anomalous.

**8. Why unsupervised rather than supervised?**
Because in a real engagement there are no labels, you don't know which transactions
are fraudulent. Unsupervised anomaly detection doesn't require them; it only assumes
anomalies look different from the bulk of normal behavior. The synthetic labels I
generated exist purely to *validate* the unsupervised approach's ability to surface a
controlled set of known anomalies, not to train a supervised model.

**9. What is contamination and what would you do without knowing the true rate?**
Contamination is the assumed proportion of anomalies, used to set the score threshold
for a binary decision. I set it to 0.015, matching my known injection rate, which I
can only do because I know the ground truth here. In a real engagement I'd either pick
contamination from a fixed review-alert budget (e.g., "I can review 500 items a
period") or report the continuous score and let the reviewer choose the cut based on
capacity, which is exactly what the composite score and its risk-rank column are built
to support.

**10. Why average precision instead of accuracy or ROC-AUC on this problem?**
The anomaly rate is 1.6%, a model that predicts "normal" for everything is 98.4%
accurate and completely useless. Average Precision integrates precision across the full
recall range and is far more informative on this class imbalance. ROC-AUC is reported
too but flagged as optimistic under heavy imbalance, since the false-positive rate
denominator is dominated by the huge majority class.

**11. Why did you build two feature sets? (the rule-flag circularity answer)**
The master plan specifies FS-A (no rule flags) and FS-B (with `rule_flag_count` as a
feature) precisely to check whether the ML model is adding independent signal or just
re-deriving the rules. In this run, Stage 6 was executed with a single feature set
(including `rule_flag_count`) on the full 1,030,804-row population rather than the full
FS-A/FS-B comparison, a scope limitation I've disclosed rather than hidden (see
`DECISIONS.md` D-0007), and the next concrete step to close.

**12. How did you prevent label leakage?**
`is_synthetic_anomaly` and `anomaly_type` are excluded from every feature matrix by
construction, and `txn_id` is assigned only after injected and real rows are
concatenated and sorted by `(invoice_date, invoice, stock_code, line_no)`, so injected
rows interleave naturally with no ID- or order-based tell. `checks/gate_03.py` fits a
shallow decision tree on ID-derived features alone predicting the injection label; its
AUC has to stay below 0.55 or the gate fails.

### Audit judgement

**13. A segment fails the Benford test. What do you actually do next?**
It's a screening result, not evidence. I'd extend substantive testing on that segment, 
pull a sample of transactions, agree amounts to supporting documentation, and look
specifically at the digit driving the deviation (in my top nonconforming segments, it's
consistently digit 1, meaning an over-representation of amounts starting with 1, worth
checking for round-number entry or a specific pricing tier).

**14. How would you explain a false positive to an engagement partner?**
I'd say precision here is a *lower bound* by construction: any genuine, real anomaly
already in the ledger that a method correctly flags gets scored as a false positive
against my synthetic labels, because I don't have ground truth for real fraud. So the
true precision on well-formed findings is likely higher than the 30-55% figures I'm
reporting for the top-ranked items.

**15. What's the cost of a false negative versus a false positive here?**
A false negative means a genuinely problematic transaction goes unreviewed, potential
misstatement risk. A false positive costs reviewer time on a clean transaction. Given
the low base rate, I biased the design toward ranking (composite score, review-budget
slider) rather than a single hard threshold, so an audit team can tune the trade-off to
their actual capacity rather than accept whatever a fixed cutoff gives them.

**16. Is a Benford exception audit evidence?**
No. It directs procedures, it tells you where to look, but on its own it does not
evidence misstatement or fraud. My workpaper's conclusion is worded exactly this way:
"these results are indicators for targeted testing and do not, of themselves, evidence
misstatement or fraud."

**17. How would this change on a general ledger with journal entries instead of sales lines?**
I'd add posting-user and manual-vs-automatic-source fields to the rule set (this
dataset has neither), test account-code combinations for unusual pairings, and expect
the off-hours and period-end rules to matter more, since manual journal entries
concentrate there far more than routine sales postings do.

**18. How would you size the review sample?**
Directly from the recall-vs-effort chart: reviewing the top 5,000 of 1,030,804 scored
transactions surfaces about 13.4% of known anomalies (a 27.6x lift over random); reviewing
5,000 surfaces roughly 56%. I'd size the sample to the review budget available and use
that curve to set expectations on coverage, rather than picking an arbitrary sample
percentage.

### Project / integrity

**19. The anomalies are synthetic, doesn't that invalidate the results?**
It bounds what the results mean, but it doesn't invalidate them. Live audit data has no
labels, so there is no alternative way to measure precision/recall at all. The synthetic
set lets me measure detection performance on a controlled, known signal, a standard
technique in forensic-analytics model validation before deployment against real
engagement data. I'm explicit everywhere the results are quoted (README, dashboard
banner, workpaper page 2) that this is a demonstration, not a live-fraud claim.

**20. What would you do differently with more time?**
Add the FS-A/FS-B feature-set split and a contamination-sensitivity grid the design
specifies (Isolation Forest itself now runs full-population); recalibrate the Benford
segment classification thresholds so the flag stops over-triggering; and actually build
the Power BI `.pbix` from the already-prepared data.

**21. What is the weakest part of this project?**
The segmented Benford flag: every segment large enough to test came back nonconforming
in this run, which means it currently carries almost no row-level discriminating power
,  it fires on ~93% of real rows too. I reported that honestly rather than adjusting the
classification thresholds until it produced a cleaner-looking split, which would have
been fitting to the story rather than validating it.

**22. Walk me through your pipeline from raw file to dashboard.**
Ingest the UCI Online Retail II Excel file into Parquet and a SQLite database; clean it
(cancellations, duplicates, adjustments, missing customer IDs, every removed row
counted in a ledger); inject the synthetic anomaly set with a leakage firewall; run
Benford's Law (aggregate and segmented), the ten rule-based tests, and Isolation
Forest/LOF; validate every method against the injected ground truth with Average
Precision, precision@k and bootstrap confidence intervals; blend them into a composite
risk score with an audit-procedure map; and export the results to a committed
aggregate data layer that feeds a Streamlit app, a static instant-load page, a
reportlab-built PDF workpaper, and (data-ready, not yet built) a Power BI dashboard.

---

## D. The numbers sheet

| Figure | Value |
|---|---|
| Cleaned population | 1,013,930 transactions |
| Total ledger value | £37,645,678 |
| Date range | 2009-11-27 to 2011-12-31 |
| Injection rate | 1.64% (16,874 rows, 6 archetypes) |
| Aggregate Benford MAD (leading digit) | 0.0251, NONCONFORMING |
| Segments assessed / flagged | 66 / 66 |
| Rule-flagged lines | 194,792 / 1,030,804 (18.9%) |
| Scored (evaluation) population | 1,030,804 rows (full population) |
| Isolation Forest AP | 0.136 (95% CI 0.132–0.140) |
| LOF AP | 0.055 (95% CI 0.049–0.062), on its 150,000-row coverage subsample |
| Composite AP | 0.166 (95% CI 0.160–0.171) |
| Random baseline precision | 0.016 |
| Precision @ 500 reviewed | 50.8% (recall 1.5%) |
| Precision @ 5,000 reviewed | 45.2% (recall 13.4%) |
| Recall @ 500 reviewed | 25.1% |
| Composite risk bands (scored pop.) | LOW 21,162 · MEDIUM 18,681 · HIGH 9,435 · CRITICAL 722 |
| Composite weights | 0.50 IF / 0.30 rules / 0.20 Benford |

## E. LinkedIn post draft

> I built an audit-analytics pipeline on a real 1-million-row UK retail sales ledger, 
> and then I did the thing most portfolio projects skip: I injected a known, controlled
> set of anomalies (1.6%, six fraud archetypes) so I could actually measure whether my
> detection methods worked, instead of just asserting that they did.
>
> Three independent layers, segmented Benford's Law, ten rule-based exception tests,
> and an Isolation Forest, feed a composite risk score. Reviewing the top 500 of
> 1,030,804 ranked transactions, the top 5,000 alone surface ~13.4% of the planted
> anomalies, a 27.6x lift over
> random selection.
>
> The honest part: my hypothesis about which method would catch which fraud type didn't
> hold up. Rule-based checks ended up dominating every category at a matched review
> budget. I reported that as a finding, not a bug to hide.
>
> Live dashboard: [link] · Repo: [link] · Workpaper: [link]
>
> #auditanalytics #benfordslaw #fraudanalytics #python
