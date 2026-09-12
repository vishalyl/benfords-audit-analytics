# Agent operating instructions — benfords-audit-analytics

## Before anything
Read `plan/00_MASTER_PLAN.md` in full. Then read only the stage document you
are currently working in.

## Hard rules
1. All logic in `src/`. Notebooks call `src/`. No exceptions.
2. Never let `is_synthetic_anomaly` or `anomaly_type` into a feature matrix.
3. Seed is 42 everywhere. Never change it to improve a result.
4. Use `--sample` while iterating. Full runs only at stage gates.
5. Every stage ends with `python checks/gate_NN.py` passing, a written
   `reports/gate_reports/gate_NN.md`, and a git commit.
6. Ambiguity → decide, proceed, append to `DECISIONS.md`. Do not stall.
7. Never report a number you did not compute. Never fabricate a row count.
8. Never edit a generated data file by hand.

## Style
- Type hints on every public function.
- Google-style docstrings stating what the function returns and its assumptions.
- `logging` not `print` inside `src/`.
- No bare `except:`.
- pandas: prefer vectorised ops; `.copy()` on any slice you mutate;
  never chained assignment.
- Functions under ~50 lines. If longer, split.

## Performance guardrails
- The Excel read is the slow step (~60-120s). Cache to Parquet and never
  re-read the xlsx unless `--force`.
- Full-population Isolation Forest on 1.08M rows with n_estimators=200
  should take under 2 minutes. If it takes more than 10, something is wrong.
- If memory pressure appears, downcast: float64→float32, int64→int32,
  and make `country` / `stock_code` categorical.

## Known deviations from the master plan (see DECISIONS.md for full detail)
- Stage 9 (Power BI .pbix) is prepared-data-only in this run: Power BI Desktop
  is not installed in this environment and cannot be scripted headlessly.
  Data packs it would consume are still produced in Stage 8.
- Stage 10 ships both a Streamlit app (source, per the frozen stack) and a
  static GitHub Pages dashboard that is live without any manual OAuth step.
