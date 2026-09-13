# Stage 2 Gate Report: Cleaning

Rows in: 1,067,371
Rows out (cleaned): 1,013,930
Cancellations removed: 19,494
Exact duplicates removed: 33,947
Adjustments flagged: 4,580
Non-positive amounts: 6,037
Missing customer IDs (UNASSIGNED): 243,007
Date range: 2009-12-01 07:45:00 to 2011-12-09 12:50:00
N countries: 43
Sunday share: 13.01%
% rows outside 07:00-20:00: 0.19%

## Checks

```
[PASS] all cleaning columns present
[PASS] ledger reconciles: 1067371 = 1013930 + 19494 + 33947 rows_in=1067371, rows_out=1013930, cancels=19494, dups=33947
[PASS] cleaned.parquet row count matches ledger (1,013,930 == 1,013,930) parquet=1013930, ledger=1013930
[PASS] cancellations.parquet row count (19,494 == 19,494)
[PASS] no nulls in invoice/stock_code/invoice_date/amount
[PASS] amount has positive values pos=1,007,893
[PASS] amount has negative values (returns) neg count=5
[PASS] year_month column populated nulls=0
[PASS] hour column populated nulls=0
[PASS] figure exists: hour_distribution.png size=38,717 bytes
[PASS] figure exists: amount_distribution.png size=34,467 bytes
[PASS] figure exists: monthly_volume.png size=90,904 bytes
[PASS] figure exists: dow_distribution.png size=48,458 bytes
[PASS] figure exists: cleaning_waterfall.png size=36,277 bytes
[PASS] customer stats computed for some customers rows with stats=778,864
[PASS] all cancellations have C-prefix invoices non-C cancellations=0
```

## GATE: PASS
