# Stage 1 Gate Report — Ingestion & SQL Layer
Combined parquet rows: 1,067,371
Sample parquet rows: 50,000
SQLite rows: 1,067,371
Date range: 2009-12-01 07:45:00 to 2011-12-09 12:50:00
Top 10 countries:
  United Kingdom: 981,330
  EIRE: 17,866
  Germany: 17,624
  France: 14,330
  Netherlands: 5,140
  Spain: 3,811
  Switzerland: 3,189
  Belgium: 3,123
  Portugal: 2,620
  Australia: 1,913

## Checks

```
[PASS] raw_combined.parquet row count (1,067,371) expected 1,067,371, got 1,067,371, diff=0
[PASS] all required columns present
[PASS] invoice_date is datetime64
[PASS] date range [2009, 2011] min=2009-12-01 07:45:00, max=2011-12-09 12:50:00
[PASS] amount = quantity * price (max diff=0.00e+00) max diff=0.00e+00
[PASS] sample_50k.parquet row count expected 50000, got 50000
[PASS] sample country distribution within 2pp of full frame (top 5)
[PASS] SQLite row count (1,067,371) expected 1,067,371, got 1,067,371
[PASS] all 5 indexes present (missing: none)
[PASS] Q1 executes and returns >= 1 row rows=573
[PASS] Q2 executes and returns >= 1 row rows=20
[PASS] Q3 executes and returns >= 1 row rows=200
[PASS] Q4 executes and returns >= 1 row rows=25
[PASS] Q5 executes and returns >= 1 row rows=9
[PASS] Q6 executes and returns >= 1 row rows=25
[PASS] stage1_profile.json has 24-bucket hour histogram bucket count=24
```

## SQL Query Results (first 3 rows each)

### Q1 (SELECT...)

```
          country year_month  txn_count  total_value  avg_value  min_value  max_value
0  United Kingdom    2011-11      77475   1325346.20      17.11       0.06    4781.60
1  United Kingdom    2010-11      71117   1275581.14      17.94       0.00   15818.40
2  United Kingdom    2010-12      60093   1153350.42      19.19       0.14   13541.33
```

### Q2 (...)

```
  customer_id         country  invoice_count  line_count  total_value  avg_line_value            first_txn             last_txn
0        <NA>  United Kingdom           2995      233252   3148203.82           13.50  2009-12-01 11:49:00  2011-12-09 10:26:00
1     18102.0  United Kingdom            145        1058    608821.65          575.45  2009-12-01 09:24:00  2011-12-09 11:50:00
2     14646.0     Netherlands            151        3849    528602.52          137.34  2009-12-02 16:52:00  2011-12-08 12:12:00
```

### Q3 (...)

```
  customer_id    txn_date  amount_rounded  occurrences  distinct_invoices   invoice_list  total_exposure
0     15760.0  2010-03-19         6958.17            2                  2  501766,501768        13916.34
1     18102.0  2011-09-15         2290.00            5                  2  566934,566935        11450.00
2     12536.0  2011-10-27         4161.06            2                  2  573077,573080         8322.12
```

### Q4 (...)

```
  year_month  txn_count  total_value  last2day_count  pct_in_last_2_days
0    2009-12      43957    825685.76               0                0.00
1    2010-01      30638    652708.50            1393                4.55
2    2010-02      28282    553713.30            1282                4.53
```

### Q5 (...)

```
   lead_digit  observed_count  observed_pct
0           1          417487       41.5621
1           2          162781       16.2054
2           3          111995       11.1495
```

### Q6 (...)

```
  customer_id  txn_count  round_100_count  pct_round_100
0     17857.0         60                3           5.00
1     14163.0         58                2           3.45
2     18102.0       1058               31           2.93
```

## GATE: PASS
