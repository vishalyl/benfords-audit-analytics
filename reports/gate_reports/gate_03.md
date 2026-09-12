GATE 03: PASS
Row counts match: 1030804 total, 16874 injected
All 6 anomaly types present: {'threshold_avoidance': 3671, 'duplicate': 3067, 'timing': 2534, 'digit_fabrication': 2534, 'extreme_outlier': 2534, 'round_number': 2534}
T3: amount == quantity * price for all rows
T7: all injected stock_codes exist in base (3039 unique)
T8: injected span 100.00% of date range, 3403 unique customers
Injection rate: 1.6370% (within 1-3% range)
Determinism OK: hash cc0ad79b99e19483
Leakage check: is_synthetic_anomaly and anomaly_type columns present in labeled data