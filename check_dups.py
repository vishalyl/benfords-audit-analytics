
import pandas as pd
labeled = pd.read_parquet("data/processed/transactions_labeled.parquet")
dups = labeled[labeled["invoice"].astype(str).duplicated(keep=False)]
print(f"Duplicate invoices: {len(dups)}")
print(f"Total rows: {len(labeled)}")
print(dups[["invoice", "is_synthetic_anomaly", "anomaly_type"]].head(20))
