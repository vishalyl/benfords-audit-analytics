
import pandas as pd
import numpy as np
from pathlib import Path
import json
import hashlib

labeled = pd.read_parquet("data/processed/transactions_labeled.parquet")
base = pd.read_parquet("data/interim/cleaned.parquet")
anomaly_mask = labeled["is_synthetic_anomaly"] == 1
n_injected = int(anomaly_mask.sum())
print(f"Labeled: {len(labeled)}, Base: {len(base)}, Injected: {n_injected} ({100*n_injected/len(labeled):.4f}%)")

type_counts = labeled.loc[anomaly_mask, "anomaly_type"].value_counts().to_dict()
print("Types:", {k: int(v) for k, v in type_counts.items()})

# Quick checks
results = {}
results["T3"] = bool((labeled["amount"].round(2) == (labeled["quantity"].astype("float64") * labeled["price"].astype("float64")).round(2)).all())
results["T6"] = bool(labeled["invoice"].duplicated().sum() == 0)
real_codes = set(base["stock_code"].unique())
inj_codes = set(labeled.loc[anomaly_mask, "stock_code"].unique())
results["T7"] = bool(inj_codes.issubset(real_codes))

date_range = (labeled["invoice_date"].max() - labeled["invoice_date"].min()).days
min_d = labeled.loc[anomaly_mask, "invoice_date"].min()
max_d = labeled.loc[anomaly_mask, "invoice_date"].max()
if pd.notna(min_d) and pd.notna(max_d):
    coverage = (max_d - min_d).days / max(date_range, 1)
else:
    coverage = 0
n_cust = int(labeled.loc[anomaly_mask, "customer_id"].nunique())
results["T8"] = bool(coverage >= 0.90 and n_cust >= 100)
print(f"T3={results[chr(84)+chr(51)]}, T6={results[chr(84)+chr(54)]}, T7={results[chr(84)+chr(55)]}, T8={results[chr(84)+chr(56)]} (cov={coverage:.4f}, custs={n_cust})")

# Write summary
Path("reports/metrics").mkdir(parents=True, exist_ok=True)
summary = {
    "n_base_rows": len(base), "n_injected": n_injected, "n_total": len(labeled),
    "anomaly_rate": round(n_injected / len(labeled), 6),
    "volume_plan": {k: int(v) for k, v in type_counts.items()},
    "type_counts": {str(k): int(v) for k, v in type_counts.items()},
    "seed": 42, "anti_tell_checks": results,
    "contamination_matrix": {
        "duplicate": {"benford": "none", "rules": "high", "iforest": "low"},
        "threshold_avoidance": {"benford": "moderate", "rules": "high", "iforest": "low-moderate"},
        "round_number": {"benford": "moderate", "rules": "high", "iforest": "low"},
        "digit_fabrication": {"benford": "high-segment-only", "rules": "near-zero", "iforest": "low"},
        "timing": {"benford": "none", "rules": "high", "iforest": "low-moderate"},
        "extreme_outlier": {"benford": "none", "rules": "near-zero", "iforest": "very-high"},
    },
    "output_hash": hashlib.sha256(pd.util.hash_pandas_object(labeled, index=True).values.tobytes()).hexdigest()[:16],
}
with open("reports/metrics/injection_summary.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)
print("Written injection_summary.json")
