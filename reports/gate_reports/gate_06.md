GATE 06: PASS
C1: scored parquet has all required columns (50000 rows)
C2: if_score range [0.0000, 1.0000] OK
C2: lof_score range [0.0000, 1.0000] OK
C2: risk_score range [0.0000, 0.7406] OK
C3: risk tier distribution: {'LOW': 46858, 'MEDIUM': 3051, 'HIGH': 91}
C3: 91 rows at HIGH+CRITICAL risk
C4: AUC-ROC = 0.7847 (>0.60 baseline)
C5: summary has 'n_rows' (total_rows) = 50000
C5: summary has 'feature_columns' (feature_columns) = ['amount', 'quantity', 'price', 'hour', 'day_of_week', 'cust_txn_count', 'cust_amount_mean', 'cust_amount_std']
C5: summary has 'tiers' (risk_tiers) = {'LOW': 46858, 'MEDIUM': 3051, 'HIGH': 91}
C5: summary has 'auc_roc' (auc_roc) = 0.784664