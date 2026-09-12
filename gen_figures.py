
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

labeled = pd.read_parquet("data/processed/transactions_labeled.parquet")
base = pd.read_parquet("data/interim/cleaned.parquet")

anomaly_mask = labeled["is_synthetic_anomaly"] == 1
real_mask = ~anomaly_mask

plt.rcParams.update({
    "figure.figsize": (12, 6), "figure.dpi": 120,
    "axes.grid": True, "grid.alpha": 0.3,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
})

figs_dir = Path("reports/figures")
figs_dir.mkdir(parents=True, exist_ok=True)

# 1. Count by type
tc = labeled.loc[anomaly_mask, "anomaly_type"].value_counts()
fig, ax = plt.subplots()
ax.bar(tc.index, tc.values, color="#4A90D9")
ax.set_ylabel("Injected rows"); ax.set_title("Injected anomaly count by type")
fig.savefig(str(figs_dir / "injection_by_type.png"), bbox_inches="tight"); plt.close()

# 2. Amount distribution
fig, ax = plt.subplots()
ra = labeled.loc[real_mask & (labeled["amount"] > 0), "amount"]
ia = labeled.loc[anomaly_mask & (labeled["amount"] > 0), "amount"]
ax.hist(np.log10(ra), bins=100, alpha=0.5, color="#4A90D9", label="Real")
ax.hist(np.log10(ia), bins=100, alpha=0.5, color="#D94A4A", label="Injected")
ax.set_xlabel("log10(amount)"); ax.set_ylabel("Density"); ax.legend()
ax.set_title("Amount: real vs injected (log scale)")
fig.savefig(str(figs_dir / "injection_amount_overlay.png"), bbox_inches="tight"); plt.close()

# 3. Hour distribution
fig, ax = plt.subplots()
ax.bar(range(24), real_mask.groupby(labeled["hour"]).sum().reindex(range(24), fill_value=0).values, alpha=0.5, color="#4A90D9", label="Real")
ax.bar(range(24), anomaly_mask.groupby(labeled["hour"]).sum().reindex(range(24), fill_value=0).values, alpha=0.5, color="#D94A4A", label="Injected")
ax.set_xlabel("Hour"); ax.set_ylabel("Count"); ax.set_title("Hour distribution"); ax.legend()
fig.savefig(str(figs_dir / "injection_hour_overlay.png"), bbox_inches="tight"); plt.close()

# 4. Day-of-month
fig, ax = plt.subplots()
ax.hist(labeled.loc[real_mask, "day"].dropna(), bins=range(1,32), alpha=0.5, color="#4A90D9", label="Real", edgecolor="none")
ax.hist(labeled.loc[anomaly_mask, "day"].dropna(), bins=range(1,32), alpha=0.5, color="#D94A4A", label="Injected", edgecolor="none")
ax.set_xlabel("Day of month"); ax.set_ylabel("Count"); ax.set_title("Day-of-month distribution"); ax.legend()
fig.savefig(str(figs_dir / "injection_dom_overlay.png"), bbox_inches="tight"); plt.close()

# 5. Leading digit
def leading_digit(s):
    return np.array([int(str(int(abs(v))).lstrip("0")[0]) if str(int(abs(v))) != "0" else 0 for v in s if v >= 1.0])
benford = np.array([np.log10(1 + 1/d) for d in range(1, 10)])
rd = pd.Series(leading_digit(ra)).value_counts(normalize=True).reindex(range(1,10), fill_value=0).values
id_ = pd.Series(leading_digit(ia)).value_counts(normalize=True).reindex(range(1,10), fill_value=0).values
fig, ax = plt.subplots()
x = np.arange(1, 10); w = 0.25
ax.bar(x-w, benford, w, label="Benford", color="#999")
ax.bar(x, rd, w, label="Real", color="#4A90D9")
ax.bar(x+w, id_, w, label="Injected", color="#D94A4A")
ax.set_xlabel("Leading digit"); ax.set_ylabel("Proportion"); ax.set_title("Leading digit distribution")
ax.legend(); fig.savefig(str(figs_dir / "injection_leading_digit.png"), bbox_inches="tight"); plt.close()

# 6. Position uniformity
fig, ax = plt.subplots()
pos = np.where(anomaly_mask.values)[0] / len(labeled)
sp = np.sort(pos)
ax.plot(sp, np.arange(1, len(sp)+1)/len(sp), color="#D94A4A", label="Injected (ECDF)")
ax.plot([0,1], [0,1], color="#999", linestyle="--", label="Uniform")
ax.set_xlabel("Position"); ax.set_ylabel("Cumulative proportion"); ax.set_title("Injected positions")
ax.legend(); fig.savefig(str(figs_dir / "injection_position_uniformity.png"), bbox_inches="tight"); plt.close()

print("All 6 figures written to reports/figures/")
